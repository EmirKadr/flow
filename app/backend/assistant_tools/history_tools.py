"""Tools för Historik: audit-sök, felstatistik, väntetider och interaktioner.

Payloads i audit_log är redan sanerade vid skrivning; här kortas de dessutom
innan de skickas till modellen.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import AuditLog, User, UserInteractionEvent, UserWaitMetric
from .common import clamp_limit, parse_period_arg, resolve_business_id
from .registry import register_tool

_PERIOD_PARAM = {
    "type": "string",
    "description": "Period bakåt i tiden: 1h, 24h, 7d eller 30d. Default 24h.",
}
_BUSINESS_PARAM = {
    "type": "string",
    "description": "Verksamhet som id, kod eller namn. Utelämna för användarens egen verksamhet.",
}

_PAYLOAD_CHAR_LIMIT = 300


def _short_payload(value: dict | None) -> str | None:
    if not value:
        return None
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text[:_PAYLOAD_CHAR_LIMIT]


def _scoped_audit_query(db: Session, business_id: int | None):
    query = db.query(AuditLog)
    if business_id is not None:
        query = query.filter(AuditLog.business_id == business_id)
    return query


@register_tool(
    name="search_audit_log",
    title="Sök i Historik",
    description=(
        "Sök i audit-loggen (Historik): vem gjorde vad och när. "
        "Filtrerbart på entitetstyp (t.ex. schedule_cell, person, mcp_query), action och användarnamn."
    ),
    parameters={
        "type": "object",
        "properties": {
            "entity_type": {"type": "string", "description": "Filtrera på entitetstyp."},
            "action": {"type": "string", "description": "Filtrera på action (delsträng, t.ex. update eller failed)."},
            "username": {"type": "string", "description": "Filtrera på användarnamn."},
            "period": _PERIOD_PARAM,
            "business": _BUSINESS_PARAM,
            "limit": {"type": "integer", "description": "Max antal rader (default 25, max 200)."},
        },
    },
    view_id="analytics",
)
def search_audit_log_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    period, since = parse_period_arg(args.get("period"))
    limit = clamp_limit(args.get("limit"), default=25)
    query = _scoped_audit_query(db, business_id).filter(AuditLog.created_at >= since)
    entity_type = str(args.get("entity_type") or "").strip()
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    action = str(args.get("action") or "").strip()
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    username = str(args.get("username") or "").strip()
    if username:
        query = query.join(User, AuditLog.user_id == User.id).filter(User.username.ilike(f"%{username}%"))
    entries = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    user_ids = {entry.user_id for entry in entries if entry.user_id is not None}
    usernames = (
        {row.id: row.username for row in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids
        else {}
    )
    return {
        "period": period,
        "entries": [
            {
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
                "action": entry.action,
                "username": usernames.get(entry.user_id),
                "payload": _short_payload(entry.new_value),
            }
            for entry in entries
        ],
        "count": len(entries),
    }


@register_tool(
    name="audit_action_stats",
    title="Historikstatistik",
    description="Antal audit-händelser per entitetstyp och action under en period.",
    parameters={
        "type": "object",
        "properties": {"period": _PERIOD_PARAM, "business": _BUSINESS_PARAM},
    },
    view_id="analytics",
)
def audit_action_stats_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    period, since = parse_period_arg(args.get("period"))
    rows = (
        _scoped_audit_query(db, business_id)
        .with_entities(AuditLog.entity_type, AuditLog.action, func.count(AuditLog.id))
        .filter(AuditLog.created_at >= since)
        .group_by(AuditLog.entity_type, AuditLog.action)
        .order_by(func.count(AuditLog.id).desc())
        .limit(60)
        .all()
    )
    return {
        "period": period,
        "stats": [
            {"entity_type": entity_type, "action": action, "count": int(count or 0)}
            for entity_type, action, count in rows
        ],
    }


@register_tool(
    name="recent_errors",
    title="Senaste felen",
    description="Lista audit-händelser som ser ut som fel (failed/error) under en period.",
    parameters={
        "type": "object",
        "properties": {
            "period": _PERIOD_PARAM,
            "business": _BUSINESS_PARAM,
            "limit": {"type": "integer", "description": "Max antal rader (default 20, max 200)."},
        },
    },
    view_id="analytics",
)
def recent_errors_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    period, since = parse_period_arg(args.get("period"))
    limit = clamp_limit(args.get("limit"), default=20)
    entries = (
        _scoped_audit_query(db, business_id)
        .filter(
            AuditLog.created_at >= since,
            AuditLog.action.ilike("%fail%") | AuditLog.action.ilike("%error%"),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "period": period,
        "errors": [
            {
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "entity_type": entry.entity_type,
                "action": entry.action,
                "payload": _short_payload(entry.new_value),
            }
            for entry in entries
        ],
        "count": len(entries),
    }


@register_tool(
    name="wait_metrics_summary",
    title="Väntetider",
    description=(
        "Summera uppmätta väntetider per vy/mål under en period: antal, snitt och max i millisekunder. "
        "Bra för frågor om seghet och prestanda."
    ),
    parameters={
        "type": "object",
        "properties": {"period": _PERIOD_PARAM, "business": _BUSINESS_PARAM},
    },
    view_id="analytics",
)
def wait_metrics_summary_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    period, since = parse_period_arg(args.get("period"))
    query = db.query(
        UserWaitMetric.view_id,
        UserWaitMetric.target,
        func.count(UserWaitMetric.id),
        func.avg(UserWaitMetric.duration_ms),
        func.max(UserWaitMetric.duration_ms),
    ).filter(UserWaitMetric.created_at >= since)
    if business_id is not None:
        query = query.filter(UserWaitMetric.business_id == business_id)
    rows = (
        query.group_by(UserWaitMetric.view_id, UserWaitMetric.target)
        .order_by(func.avg(UserWaitMetric.duration_ms).desc())
        .limit(40)
        .all()
    )
    return {
        "period": period,
        "waits": [
            {
                "view_id": view_id,
                "target": target,
                "count": int(count or 0),
                "avg_ms": int(avg_ms or 0),
                "max_ms": int(max_ms or 0),
            }
            for view_id, target, count, avg_ms, max_ms in rows
        ],
    }


@register_tool(
    name="interaction_summary",
    title="Använda funktioner",
    description="Vilka knappar/kontroller som använts mest under en period, per vy.",
    parameters={
        "type": "object",
        "properties": {"period": _PERIOD_PARAM, "business": _BUSINESS_PARAM},
    },
    view_id="analytics",
)
def interaction_summary_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    period, since = parse_period_arg(args.get("period"))
    query = db.query(
        UserInteractionEvent.view_id,
        UserInteractionEvent.control_id,
        func.max(UserInteractionEvent.control_label),
        func.count(UserInteractionEvent.id),
    ).filter(UserInteractionEvent.created_at >= since)
    if business_id is not None:
        query = query.filter(UserInteractionEvent.business_id == business_id)
    rows = (
        query.group_by(UserInteractionEvent.view_id, UserInteractionEvent.control_id)
        .order_by(func.count(UserInteractionEvent.id).desc())
        .limit(40)
        .all()
    )
    return {
        "period": period,
        "interactions": [
            {
                "view_id": view_id,
                "control_id": control_id,
                "control_label": control_label,
                "count": int(count or 0),
            }
            for view_id, control_id, control_label, count in rows
        ],
    }

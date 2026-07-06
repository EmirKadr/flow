"""Tools för Historik: audit-sök, felstatistik, väntetider och interaktioner.

Payloads i audit_log är redan sanerade vid skrivning; här kortas de dessutom
innan de skickas till modellen.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import AuditLog, RfidScanEvent, User, UserInteractionEvent, UserWaitMetric
from .common import clamp_limit, parse_period_arg, percentile, resolve_business_id
from .common import ToolInputError
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


_FETCH_CAP = 20000  # dialektsäker dag-gruppering sker i Python; taket skyddar minnet


def _error_audit_filter(query):
    return query.filter(AuditLog.action.ilike("%fail%") | AuditLog.action.ilike("%error%"))


@register_tool(
    name="error_trend",
    title="Feltrend",
    description=(
        "Fel per dag under en period, uppdelat på källa: audit-fel (failed/error), "
        "API-/väntetidsfel och interaktionsfel. Bra för frågan om felen ökar eller minskar."
    ),
    parameters={
        "type": "object",
        "properties": {"period": _PERIOD_PARAM, "business": _BUSINESS_PARAM},
    },
    view_id="analytics",
)
def error_trend_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    period, since = parse_period_arg(args.get("period"), default="7d")

    audit_times = [
        row[0]
        for row in _error_audit_filter(_scoped_audit_query(db, business_id))
        .with_entities(AuditLog.created_at)
        .filter(AuditLog.created_at >= since)
        .limit(_FETCH_CAP)
        .all()
    ]
    wait_query = db.query(UserWaitMetric.created_at).filter(
        UserWaitMetric.created_at >= since, UserWaitMetric.status != "ok"
    )
    if business_id is not None:
        wait_query = wait_query.filter(UserWaitMetric.business_id == business_id)
    wait_times = [row[0] for row in wait_query.limit(_FETCH_CAP).all()]
    interaction_query = db.query(UserInteractionEvent.created_at).filter(
        UserInteractionEvent.created_at >= since, UserInteractionEvent.status != "ok"
    )
    if business_id is not None:
        interaction_query = interaction_query.filter(UserInteractionEvent.business_id == business_id)
    interaction_times = [row[0] for row in interaction_query.limit(_FETCH_CAP).all()]

    days: dict[str, dict[str, int]] = {}
    for source, times in (("audit", audit_times), ("waits", wait_times), ("interactions", interaction_times)):
        for stamp in times:
            if stamp is None:
                continue
            key = stamp.date().isoformat()
            bucket = days.setdefault(key, {"audit": 0, "waits": 0, "interactions": 0})
            bucket[source] += 1
    return {
        "period": period,
        "days": [
            {"date": day, **counts, "total": sum(counts.values())}
            for day, counts in sorted(days.items())
        ],
        "total": sum(sum(counts.values()) for counts in days.values()),
    }


@register_tool(
    name="error_top_endpoints",
    title="Fel per endpoint",
    description="Vilka vyer/API-mål som gett flest fel (status != ok) under en period.",
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
def error_top_endpoints_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    period, since = parse_period_arg(args.get("period"), default="7d")
    limit = clamp_limit(args.get("limit"), default=20)
    query = db.query(
        UserWaitMetric.view_id,
        UserWaitMetric.target,
        func.count(UserWaitMetric.id),
    ).filter(UserWaitMetric.created_at >= since, UserWaitMetric.status != "ok")
    if business_id is not None:
        query = query.filter(UserWaitMetric.business_id == business_id)
    rows = (
        query.group_by(UserWaitMetric.view_id, UserWaitMetric.target)
        .order_by(func.count(UserWaitMetric.id).desc())
        .limit(limit)
        .all()
    )
    return {
        "period": period,
        "endpoints": [
            {"view_id": view_id, "target": target, "error_count": int(count or 0)}
            for view_id, target, count in rows
        ],
    }


@register_tool(
    name="audit_entity_history",
    title="Ändringshistorik för entitet",
    description=(
        "Kronologisk ändringshistorik för en specifik entitet i Historik: "
        "vem ändrade vad och när. Kräver entity_type (t.ex. person, schedule_cell, user) och entity_id."
    ),
    parameters={
        "type": "object",
        "properties": {
            "entity_type": {"type": "string", "description": "Entitetstyp, t.ex. person eller schedule_cell."},
            "entity_id": {"type": "integer", "description": "Entitetens id."},
            "business": _BUSINESS_PARAM,
            "limit": {"type": "integer", "description": "Max antal rader (default 50, max 200)."},
        },
        "required": ["entity_type", "entity_id"],
    },
    view_id="analytics",
)
def audit_entity_history_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    entity_type = str(args.get("entity_type") or "").strip()
    if not entity_type:
        raise ToolInputError("Ange entity_type, t.ex. person eller schedule_cell.")
    try:
        entity_id = int(args.get("entity_id"))
    except (TypeError, ValueError) as exc:
        raise ToolInputError("Ange entity_id som heltal.") from exc
    limit = clamp_limit(args.get("limit"))
    entries = (
        _scoped_audit_query(db, business_id)
        .filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.created_at.asc())
        .limit(limit)
        .all()
    )
    user_ids = {entry.user_id for entry in entries if entry.user_id is not None}
    usernames = (
        {row.id: row.username for row in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids
        else {}
    )
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entries": [
            {
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "action": entry.action,
                "username": usernames.get(entry.user_id),
                "old_value": _short_payload(entry.old_value),
                "new_value": _short_payload(entry.new_value),
            }
            for entry in entries
        ],
        "count": len(entries),
    }


@register_tool(
    name="wait_metrics_by_endpoint",
    title="Väntetidspercentiler",
    description=(
        "Svarstider per vy/mål under en period med median (p50), p95 och max i millisekunder. "
        "Mer detaljerad än wait_metrics_summary."
    ),
    parameters={
        "type": "object",
        "properties": {
            "period": _PERIOD_PARAM,
            "business": _BUSINESS_PARAM,
            "target": {"type": "string", "description": "Filtrera på mål/endpoint (delsträng)."},
        },
    },
    view_id="analytics",
)
def wait_metrics_by_endpoint_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    period, since = parse_period_arg(args.get("period"))
    query = db.query(
        UserWaitMetric.view_id, UserWaitMetric.target, UserWaitMetric.duration_ms
    ).filter(UserWaitMetric.created_at >= since)
    if business_id is not None:
        query = query.filter(UserWaitMetric.business_id == business_id)
    target_filter = str(args.get("target") or "").strip()
    if target_filter:
        query = query.filter(UserWaitMetric.target.ilike(f"%{target_filter}%"))
    rows = query.limit(_FETCH_CAP).all()

    groups: dict[tuple[str | None, str | None], list[int]] = {}
    for view_id, target, duration_ms in rows:
        groups.setdefault((view_id, target), []).append(int(duration_ms or 0))
    ranked = sorted(groups.items(), key=lambda item: len(item[1]), reverse=True)[:25]
    return {
        "period": period,
        "endpoints": [
            {
                "view_id": view_id,
                "target": target,
                "count": len(durations),
                "p50_ms": int(percentile(durations, 50)),
                "p95_ms": int(percentile(durations, 95)),
                "max_ms": max(durations) if durations else 0,
            }
            for (view_id, target), durations in ranked
        ],
    }


@register_tool(
    name="user_activity_summary",
    title="Användaraktivitet",
    description=(
        "Sammanfatta en användares aktivitet under en period: audit-händelser per action, "
        "mest använda vyer och senaste aktivitet. Inga fritextpayloads."
    ),
    parameters={
        "type": "object",
        "properties": {
            "username": {"type": "string", "description": "Användarnamn (delsträng räcker om unik)."},
            "period": _PERIOD_PARAM,
            "business": _BUSINESS_PARAM,
        },
        "required": ["username"],
    },
    view_id="analytics",
)
def user_activity_summary_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    username = str(args.get("username") or "").strip()
    if not username:
        raise ToolInputError("Ange username.")
    user_query = db.query(User).filter(User.username.ilike(f"%{username}%"))
    if business_id is not None:
        user_query = user_query.filter(User.business_id == business_id)
    matches = user_query.order_by(User.username).limit(6).all()
    if not matches:
        raise ToolInputError(f"Ingen användare matchade '{username}'.")
    exact = [row for row in matches if row.username.lower() == username.lower()]
    if len(exact) == 1:
        target_user = exact[0]
    elif len(matches) == 1:
        target_user = matches[0]
    else:
        names = ", ".join(row.username for row in matches)
        raise ToolInputError(f"Flera användare matchade '{username}': {names}. Ange exakt namn.")

    period, since = parse_period_arg(args.get("period"), default="7d")
    audit_rows = (
        _scoped_audit_query(db, business_id)
        .with_entities(AuditLog.entity_type, AuditLog.action, func.count(AuditLog.id), func.max(AuditLog.created_at))
        .filter(AuditLog.created_at >= since, AuditLog.user_id == target_user.id)
        .group_by(AuditLog.entity_type, AuditLog.action)
        .order_by(func.count(AuditLog.id).desc())
        .limit(15)
        .all()
    )
    view_query = db.query(
        UserInteractionEvent.view_id, func.count(UserInteractionEvent.id), func.max(UserInteractionEvent.created_at)
    ).filter(UserInteractionEvent.created_at >= since, UserInteractionEvent.user_id == target_user.id)
    if business_id is not None:
        view_query = view_query.filter(UserInteractionEvent.business_id == business_id)
    view_rows = (
        view_query.group_by(UserInteractionEvent.view_id)
        .order_by(func.count(UserInteractionEvent.id).desc())
        .limit(15)
        .all()
    )
    last_seen_candidates = [row[3] for row in audit_rows if row[3] is not None]
    last_seen_candidates += [row[2] for row in view_rows if row[2] is not None]
    return {
        "username": target_user.username,
        "period": period,
        "audit_actions": [
            {"entity_type": entity_type, "action": action, "count": int(count or 0)}
            for entity_type, action, count, _ in audit_rows
        ],
        "views_used": [
            {"view_id": view_id, "count": int(count or 0)} for view_id, count, _ in view_rows
        ],
        "last_seen": max(last_seen_candidates).isoformat() if last_seen_candidates else None,
    }


@register_tool(
    name="rfid_error_summary",
    title="RFID-fel och status",
    description=(
        "RFID-stämplingar per status under en period, med nedbrytning per modul "
        "för stämplingar som inte kunnat tillämpas."
    ),
    parameters={
        "type": "object",
        "properties": {"period": _PERIOD_PARAM, "business": _BUSINESS_PARAM},
    },
    view_id="analytics",
)
def rfid_error_summary_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    period, since = parse_period_arg(args.get("period"), default="7d")
    status_query = db.query(RfidScanEvent.status, func.count(RfidScanEvent.id)).filter(
        RfidScanEvent.scan_time >= since
    )
    if business_id is not None:
        status_query = status_query.filter(RfidScanEvent.business_id == business_id)
    status_rows = status_query.group_by(RfidScanEvent.status).order_by(func.count(RfidScanEvent.id).desc()).all()

    module_query = db.query(
        RfidScanEvent.module_name, RfidScanEvent.status, func.count(RfidScanEvent.id)
    ).filter(RfidScanEvent.scan_time >= since, RfidScanEvent.status != "applied")
    if business_id is not None:
        module_query = module_query.filter(RfidScanEvent.business_id == business_id)
    module_rows = (
        module_query.group_by(RfidScanEvent.module_name, RfidScanEvent.status)
        .order_by(func.count(RfidScanEvent.id).desc())
        .limit(30)
        .all()
    )
    return {
        "period": period,
        "by_status": [
            {"status": status, "count": int(count or 0)} for status, count in status_rows
        ],
        "not_applied_by_module": [
            {"module": module, "status": status, "count": int(count or 0)}
            for module, status, count in module_rows
        ],
    }

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import audit as audit_writer
from ..deps import get_current_user, get_db, require_super_user
from ..models import AuditLog, User
from ..schemas import (
    AuditClientErrorIn,
    AuditEntryOut,
    AuditErrorEventOut,
    AuditErrorSummaryOut,
    AuditSummaryBucket,
    AuditSummaryOut,
)

router = APIRouter(prefix="/api/audit", tags=["audit"])
logger = logging.getLogger(__name__)

ERROR_ACTION_PATTERNS = ("%failed%", "%error%", "%exception%")


def _apply_filters(query, *, user_id: int | None, entity_type: str | None, action: str | None,
                   entity_id: int | None, from_at: datetime | None, to_at: datetime | None):
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    if entity_id is not None:
        query = query.where(AuditLog.entity_id == entity_id)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type.strip())
    if action:
        query = query.where(AuditLog.action.ilike(f"%{action.strip()}%"))
    if from_at is not None:
        query = query.where(AuditLog.created_at >= from_at)
    if to_at is not None:
        query = query.where(AuditLog.created_at <= to_at)
    return query


def _bucket(key: str | None, label: str | None, count: int) -> AuditSummaryBucket:
    normalized_key = key or "system"
    normalized_label = label or ("System" if normalized_key == "system" else normalized_key)
    return AuditSummaryBucket(key=normalized_key, label=normalized_label, count=int(count))


def _error_filter():
    return or_(
        AuditLog.entity_type == "client_error",
        *(AuditLog.action.ilike(pattern) for pattern in ERROR_ACTION_PATTERNS),
    )


def _clean_text(value: Any, *, max_length: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return None
    return text[: max_length - 3] + "..." if len(text) > max_length else text


def _detail_summary(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, list):
        return f"{len(value)} detaljer"
    if isinstance(value, dict):
        message = value.get("message") or value.get("detail") or value.get("error")
        if isinstance(message, str):
            return _clean_text(message)
        keys = ", ".join(sorted(str(key) for key in value.keys())[:6])
        return f"Detaljfält: {keys}" if keys else None
    return _clean_text(value)


def _safe_path(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0].split("#", 1)[0]
    cleaned = "/" + path.lstrip("/")
    return _clean_text(cleaned, max_length=300)


def _as_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _error_payload(audit: AuditLog) -> dict[str, Any]:
    payload = audit.new_value or audit.old_value or {}
    return payload if isinstance(payload, dict) else {}


def _error_event(audit: AuditLog, username: str | None, display_name: str | None) -> AuditErrorEventOut:
    payload = _error_payload(audit)
    status_code = _as_int(payload.get("status_code") if "status_code" in payload else payload.get("status"))
    error_type = (
        _clean_text(payload.get("error_type"), max_length=120)
        or _clean_text(payload.get("error_code"), max_length=120)
        or (f"HTTP {status_code}" if status_code is not None else None)
        or audit.action
    )
    error_code = (
        _clean_text(payload.get("error_code"), max_length=120)
        or _clean_text(payload.get("error_id"), max_length=120)
        or error_type
        or (f"HTTP {status_code}" if status_code is not None else None)
    )
    message = _clean_text(payload.get("message")) or _detail_summary(payload.get("detail"))
    return AuditErrorEventOut(
        id=audit.id,
        created_at=audit.created_at,
        user_id=audit.user_id,
        username=username,
        display_name=display_name,
        entity_type=audit.entity_type,
        entity_id=audit.entity_id,
        action=audit.action,
        error_code=error_code,
        error_type=error_type,
        status_code=status_code,
        path=_safe_path(payload.get("path") or payload.get("page_path")),
        message=message,
    )


def _counter_buckets(counter: Counter[str], *, empty_label: str = "-") -> list[AuditSummaryBucket]:
    return [
        _bucket(key or empty_label, key or empty_label, count)
        for key, count in counter.most_common(8)
    ]


def _client_error_payload(payload: AuditClientErrorIn) -> dict[str, Any]:
    status_code = payload.status if payload.status is not None else 0
    error_code = _clean_text(payload.error_code, max_length=120) or (
        f"HTTP {status_code}" if status_code else "client_error"
    )
    return {
        "path": _safe_path(payload.path),
        "method": _clean_text(payload.method.upper(), max_length=10) or "GET",
        "status_code": status_code,
        "error_code": error_code,
        "message": _clean_text(payload.message),
        "detail": _detail_summary(payload.detail),
        "page_path": _safe_path(payload.page_path),
    }


@router.get("", response_model=list[AuditEntryOut])
def list_audit_entries(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user_id: int | None = Query(None),
    entity_type: str | None = Query(None),
    action: str | None = Query(None),
    entity_id: int | None = Query(None),
    from_at: datetime | None = Query(None),
    to_at: datetime | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> list[AuditEntryOut]:
    query = (
        select(AuditLog, User.username, User.display_name)
        .outerjoin(User, User.id == AuditLog.user_id)
    )
    query = _apply_filters(
        query,
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        from_at=from_at,
        to_at=to_at,
    )
    query = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(offset).limit(limit)

    rows = db.execute(query).all()
    return [
        AuditEntryOut(
            id=audit.id,
            entity_type=audit.entity_type,
            entity_id=audit.entity_id,
            action=audit.action,
            old_value=audit.old_value,
            new_value=audit.new_value,
            user_id=audit.user_id,
            username=username,
            display_name=display_name,
            created_at=audit.created_at,
        )
        for audit, username, display_name in rows
    ]


@router.get("/summary", response_model=AuditSummaryOut)
def audit_summary(
    user_id: int | None = Query(None),
    entity_type: str | None = Query(None),
    action: str | None = Query(None),
    entity_id: int | None = Query(None),
    from_at: datetime | None = Query(None),
    to_at: datetime | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> AuditSummaryOut:
    base = select(AuditLog.id).select_from(AuditLog)
    base = _apply_filters(
        base,
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        from_at=from_at,
        to_at=to_at,
    )

    total_events = int(db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0)

    last_24_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_query = _apply_filters(
        select(func.count()).select_from(AuditLog),
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        from_at=from_at,
        to_at=to_at,
    ).where(AuditLog.created_at >= last_24_cutoff)
    events_last_24h = int(db.execute(recent_query).scalar() or 0)

    distinct_users_query = _apply_filters(
        select(func.count(func.distinct(AuditLog.user_id))).select_from(AuditLog),
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        from_at=from_at,
        to_at=to_at,
    ).where(AuditLog.user_id.is_not(None))
    unique_users = int(db.execute(distinct_users_query).scalar() or 0)

    users_query = (
        select(AuditLog.user_id, User.username, User.display_name, func.count().label("count"))
        .select_from(AuditLog)
        .outerjoin(User, User.id == AuditLog.user_id)
    )
    users_query = _apply_filters(
        users_query,
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        from_at=from_at,
        to_at=to_at,
    )
    users_query = (
        users_query
        .group_by(AuditLog.user_id, User.username, User.display_name)
        .order_by(func.count().desc(), User.username.asc())
        .limit(8)
    )
    top_users = [
        _bucket(
            str(row.user_id) if row.user_id is not None else "system",
            row.display_name or row.username or "System",
            row.count,
        )
        for row in db.execute(users_query)
    ]

    actions_query = _apply_filters(
        select(AuditLog.action, func.count().label("count")).select_from(AuditLog),
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        from_at=from_at,
        to_at=to_at,
    )
    actions_query = actions_query.group_by(AuditLog.action).order_by(func.count().desc(), AuditLog.action.asc()).limit(8)
    top_actions = [_bucket(row.action, row.action, row.count) for row in db.execute(actions_query)]

    entities_query = _apply_filters(
        select(AuditLog.entity_type, func.count().label("count")).select_from(AuditLog),
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        from_at=from_at,
        to_at=to_at,
    )
    entities_query = (
        entities_query
        .group_by(AuditLog.entity_type)
        .order_by(func.count().desc(), AuditLog.entity_type.asc())
        .limit(8)
    )
    top_entities = [_bucket(row.entity_type, row.entity_type, row.count) for row in db.execute(entities_query)]

    return AuditSummaryOut(
        total_events=total_events,
        events_last_24h=events_last_24h,
        unique_users=unique_users,
        top_users=top_users,
        top_actions=top_actions,
        top_entities=top_entities,
    )


@router.get("/errors", response_model=AuditErrorSummaryOut)
def audit_errors(
    limit: int = Query(100, ge=1, le=500),
    scan_limit: int = Query(5000, ge=100, le=20000),
    user_id: int | None = Query(None),
    entity_type: str | None = Query(None),
    action: str | None = Query(None),
    entity_id: int | None = Query(None),
    from_at: datetime | None = Query(None),
    to_at: datetime | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> AuditErrorSummaryOut:
    base = _apply_filters(
        select(AuditLog.id).select_from(AuditLog),
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        from_at=from_at,
        to_at=to_at,
    ).where(_error_filter())
    total_errors = int(db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0)

    last_24_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_count_query = _apply_filters(
        select(func.count()).select_from(AuditLog),
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        from_at=from_at,
        to_at=to_at,
    ).where(_error_filter(), AuditLog.created_at >= last_24_cutoff)
    events_last_24h = int(db.execute(recent_count_query).scalar() or 0)

    unique_users_query = _apply_filters(
        select(func.count(func.distinct(AuditLog.user_id))).select_from(AuditLog),
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        from_at=from_at,
        to_at=to_at,
    ).where(_error_filter(), AuditLog.user_id.is_not(None))
    unique_users = int(db.execute(unique_users_query).scalar() or 0)

    rows_query = (
        select(AuditLog, User.username, User.display_name)
        .outerjoin(User, User.id == AuditLog.user_id)
    )
    rows_query = _apply_filters(
        rows_query,
        user_id=user_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        from_at=from_at,
        to_at=to_at,
    ).where(_error_filter())
    rows_query = rows_query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(scan_limit)
    events = [_error_event(audit, username, display_name) for audit, username, display_name in db.execute(rows_query)]

    user_counter: Counter[str] = Counter(
        event.display_name or event.username or "System"
        for event in events
    )
    return AuditErrorSummaryOut(
        total_errors=total_errors,
        events_last_24h=events_last_24h,
        unique_users=unique_users,
        scanned_events=len(events),
        truncated=total_errors > len(events),
        top_error_codes=_counter_buckets(Counter(event.error_code for event in events)),
        top_actions=_counter_buckets(Counter(event.action for event in events)),
        top_paths=_counter_buckets(Counter(event.path or "-" for event in events)),
        top_users=_counter_buckets(user_counter),
        recent=events[:limit],
    )


@router.post("/client-error", status_code=status.HTTP_204_NO_CONTENT)
def report_client_error(
    payload: AuditClientErrorIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    sanitized = _client_error_payload(payload)
    audit_writer.log_and_commit(
        db,
        entity_type="client_error",
        entity_id=_as_int(sanitized.get("status_code")) or 0,
        action="client_error",
        old_value=None,
        new_value=sanitized,
        user_id=user.id,
        business_id=user.business_id,
        logger=logger,
        context="client error audit event",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

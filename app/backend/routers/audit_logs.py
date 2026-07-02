from __future__ import annotations

import logging
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import audit as audit_writer
from ..config import settings
from ..deps import get_current_user, get_db, require_super_user
from ..models import AuditLog, User, UserInteractionEvent
from ..observability import attach_trace_context, current_trace_id, normalize_trace_id
from ..schemas import (
    AuditClientErrorIn,
    AuditClientEventIn,
    AuditEntryOut,
    AuditErrorEventOut,
    AuditErrorSummaryOut,
    AuditLocalRunIn,
    AuditSummaryBucket,
    AuditSummaryOut,
    InteractionChatRequest,
    InteractionChatResponse,
    InteractionCoverageOut,
    InteractionEventBatchIn,
    InteractionEventOut,
    InteractionSummaryOut,
)
from .assistant import _call_minimax

from .audit_logs_helpers import (  # noqa: F401
    ERROR_ACTION_PATTERNS,
    INTERACTION_PERIODS,
    INTERACTION_SENSITIVE_KEY_PARTS,
    INTERACTION_VALUE_SAMPLE_KEY_PARTS,
    INTERACTION_PUBLIC_EVENT_TYPES,
    KNOWN_INTERACTION_CONTROLS,
    AUDIT_ENTITY_LABELS,
    _apply_filters,
    _bucket,
    _entity_label,
    _error_filter,
    _clean_text,
    _detail_summary,
    _safe_path,
    _as_int,
    _bounded_int,
    _period_start,
    _interaction_created_after,
    _safe_key,
    _is_sensitive_interaction_key,
    _is_value_sample_key,
    _sanitize_interaction_detail_value,
    _sanitize_interaction_detail,
    _interaction_payload,
    _interaction_row,
    _apply_interaction_filters,
    _interaction_bucket_key,
    _buckets_from_rows,
    _error_payload,
    _error_event,
    _counter_buckets,
    _client_error_payload,
    _client_event_payload,
    _safe_name_list,
    _safe_counter_map,
    _local_run_payload,
    _interaction_chat_context,
)

router = APIRouter(prefix="/api/audit", tags=["audit"])
logger = logging.getLogger(__name__)

@router.get("", response_model=list[AuditEntryOut])
def list_audit_entries(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    business_id: int | None = Query(None),
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
        business_id=business_id,
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
            business_id=audit.business_id,
            user_id=audit.user_id,
            username=username,
            display_name=display_name,
            created_at=audit.created_at,
        )
        for audit, username, display_name in rows
    ]


@router.get("/summary", response_model=AuditSummaryOut)
def audit_summary(
    business_id: int | None = Query(None),
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
        business_id=business_id,
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
        business_id=business_id,
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
        business_id=business_id,
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
        business_id=business_id,
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
        business_id=business_id,
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
        business_id=business_id,
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
    top_entities = [_bucket(row.entity_type, _entity_label(row.entity_type), row.count) for row in db.execute(entities_query)]

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
    business_id: int | None = Query(None),
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
        business_id=business_id,
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
        business_id=business_id,
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
        business_id=business_id,
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
        business_id=business_id,
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


@router.post("/interactions", status_code=status.HTTP_204_NO_CONTENT)
def record_interactions(
    payload: InteractionEventBatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    rows = []
    for item in payload.items[:100]:
        sanitized = _interaction_payload(item)
        rows.append(
            UserInteractionEvent(
                business_id=user.business_id,
                user_id=user.id,
                **sanitized,
            )
        )
    if rows:
        db.add_all(rows)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/interactions/public", status_code=status.HTTP_204_NO_CONTENT)
def record_public_interactions(
    payload: InteractionEventBatchIn,
    db: Session = Depends(get_db),
) -> Response:
    rows = []
    for item in payload.items[:100]:
        if item.event_type not in INTERACTION_PUBLIC_EVENT_TYPES:
            continue
        sanitized = _interaction_payload(item)
        sanitized["view_id"] = "metaUpload"
        sanitized["client_surface"] = sanitized.get("client_surface") or "public"
        rows.append(UserInteractionEvent(business_id=None, user_id=None, **sanitized))
    if rows:
        db.add_all(rows)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/interactions", response_model=list[InteractionEventOut])
def list_interactions(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    business_id: int | None = Query(None),
    user_id: int | None = Query(None),
    view_id: str | None = Query(None),
    event_type: str | None = Query(None),
    feature: str | None = Query(None),
    flow_id: str | None = Query(None),
    control_id: str | None = Query(None),
    q: str | None = Query(None, max_length=120),
    from_at: datetime | None = Query(None),
    to_at: datetime | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> list[InteractionEventOut]:
    query = (
        select(UserInteractionEvent, User.username, User.display_name)
        .outerjoin(User, User.id == UserInteractionEvent.user_id)
    )
    query = _apply_interaction_filters(
        query,
        business_id=business_id,
        user_id=user_id,
        view_id=view_id,
        event_type=event_type,
        feature=feature,
        flow_id=flow_id,
        control_id=control_id,
        q=q,
        from_at=from_at,
        to_at=to_at,
    )
    query = query.order_by(UserInteractionEvent.created_at.desc(), UserInteractionEvent.id.desc()).offset(offset).limit(limit)
    return [_interaction_row(row, username, display_name) for row, username, display_name in db.execute(query).all()]


@router.get("/interactions/summary", response_model=InteractionSummaryOut)
def interaction_summary(
    limit: int = Query(5000, ge=100, le=20000),
    business_id: int | None = Query(None),
    user_id: int | None = Query(None),
    view_id: str | None = Query(None),
    event_type: str | None = Query(None),
    feature: str | None = Query(None),
    flow_id: str | None = Query(None),
    control_id: str | None = Query(None),
    q: str | None = Query(None, max_length=120),
    from_at: datetime | None = Query(None),
    to_at: datetime | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> InteractionSummaryOut:
    base = _apply_interaction_filters(
        select(UserInteractionEvent).order_by(UserInteractionEvent.created_at.desc()).limit(limit),
        business_id=business_id,
        user_id=user_id,
        view_id=view_id,
        event_type=event_type,
        feature=feature,
        flow_id=flow_id,
        control_id=control_id,
        q=q,
        from_at=from_at,
        to_at=to_at,
    )
    rows = list(db.execute(base).scalars())
    ids = {row.user_id for row in rows if row.user_id is not None}
    users_by_id = {
        user.id: user.display_name or user.username or str(user.id)
        for user in db.execute(select(User).where(User.id.in_(ids))).scalars()
    } if ids else {}
    last_24_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    return InteractionSummaryOut(
        total_events=len(rows),
        events_last_24h=sum(1 for row in rows if _interaction_created_after(row.created_at, last_24_cutoff)),
        unique_users=len(ids),
        top_users=_buckets_from_rows(rows, "users", users_by_id),
        top_views=_buckets_from_rows(rows, "views"),
        top_features=_buckets_from_rows(rows, "features"),
        top_controls=_buckets_from_rows(rows, "controls"),
        top_flows=_buckets_from_rows(rows, "flows"),
        top_columns=_buckets_from_rows(rows, "columns"),
        top_surfaces=_buckets_from_rows(rows, "surfaces"),
        copy_patterns=_buckets_from_rows(rows, "copy_patterns"),
        recent=[_interaction_row(row) for row in rows[:50]],
    )


@router.get("/interactions/coverage", response_model=InteractionCoverageOut)
def interaction_coverage(
    business_id: int | None = Query(None),
    user_id: int | None = Query(None),
    period: str = Query("30d"),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> InteractionCoverageOut:
    since = _period_start(period)
    query = select(UserInteractionEvent).select_from(UserInteractionEvent)
    query = _apply_interaction_filters(
        query,
        business_id=business_id,
        user_id=user_id,
        view_id=None,
        event_type=None,
        feature=None,
        flow_id=None,
        control_id=None,
        q=None,
        from_at=since,
        to_at=None,
    )
    rows = list(db.execute(query).scalars())
    used = {(row.view_id or "", row.control_id or "") for row in rows if row.view_id and row.control_id}
    known = {(item["view_id"], item["control_id"]) for item in KNOWN_INTERACTION_CONTROLS}
    unused = [
        item
        for item in KNOWN_INTERACTION_CONTROLS
        if (item["view_id"], item["control_id"]) not in used
    ]
    unknown_counter = Counter(
        f"{row.view_id or '-'} / {row.control_id or '-'}"
        for row in rows
        if row.view_id and row.control_id and (row.view_id, row.control_id) not in known
    )
    return InteractionCoverageOut(
        total_known_controls=len(KNOWN_INTERACTION_CONTROLS),
        used_controls=len(used & known),
        unused_controls=unused[:80],
        used_unknown_controls=_counter_buckets(unknown_counter),
    )


@router.post("/interactions/chat", response_model=InteractionChatResponse)
async def interaction_chat(
    payload: InteractionChatRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> InteractionChatResponse:
    if not settings.MINIMAX_API_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Historik-chatten saknar MINIMAX_API_KEY i servermiljon.",
        )
    since = _period_start(payload.period)
    query = _apply_interaction_filters(
        select(UserInteractionEvent).order_by(UserInteractionEvent.created_at.desc()).limit(1000),
        business_id=payload.business_id,
        user_id=payload.user_id,
        view_id=None,
        event_type=None,
        feature=None,
        flow_id=None,
        control_id=None,
        q=payload.q,
        from_at=since,
        to_at=None,
    )
    rows = list(db.execute(query).scalars())
    system_prompt = (
        "Du ar Historik-analytiker for flow. Svara bara pa fragor om tracking, "
        "historik, anvandning, knappar, funktioner, vyer, kolumner, flows, fel "
        "och vantetider. Svara pa svenska. Anvand bara datan i kontexten. "
        "Om fragan ber om hemligheter, API-detaljer, filnamn, privata URL:er, "
        "losenord, tokens eller fulla request bodies ska du vagra kort och "
        "forklara att Historik inte far visa sadant. Var konkret och namnge "
        "vyer, knappar, flows, tabeller och kolumner nar datan visar dem."
    )
    minimax_payload = {
        "model": settings.MINIMAX_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Fraga: {payload.question}\n\nTrackingdata:\n{_interaction_chat_context(rows)}"},
        ],
        "max_tokens": settings.MINIMAX_MAX_TOKENS,
        "temperature": 0.15,
        "reasoning_split": True,
    }
    answer = await run_in_threadpool(_call_minimax, minimax_payload)
    return InteractionChatResponse(answer=answer, model=settings.MINIMAX_MODEL, event_count=len(rows))


@router.post("/interactions/chat/clear")
def clear_interaction_chat(_: User = Depends(require_super_user)) -> dict[str, bool]:
    return {"ok": True}


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


@router.post("/client-event", status_code=status.HTTP_204_NO_CONTENT)
def report_client_event(
    payload: AuditClientEventIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    sanitized = _client_event_payload(payload)
    event_type = sanitized.get("event_type") or "client_event"
    is_view_open = event_type == "view_open"
    audit_writer.log_and_commit(
        db,
        entity_type="view" if is_view_open else "client_event",
        entity_id=0,
        action="open" if is_view_open else event_type,
        old_value=None,
        new_value=sanitized,
        user_id=user.id,
        business_id=user.business_id,
        logger=logger,
        context="client event audit event",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/local-run", status_code=status.HTTP_204_NO_CONTENT)
def report_local_run(
    payload: AuditLocalRunIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    sanitized = _local_run_payload(payload)
    feature = sanitized.get("feature") or "local"
    flow_id = sanitized.get("flow_id") or feature
    status_text = sanitized.get("status") or "ok"
    audit_writer.log_and_commit(
        db,
        entity_type="desktop_local_run",
        entity_id=0,
        action=f"{feature}_{status_text}",
        old_value=None,
        new_value=sanitized,
        user_id=user.id,
        business_id=user.business_id,
        logger=logger,
        context=f"desktop local run audit event flow={flow_id}",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

"""Hjalpfunktioner for Historik/Analys: filtrering, sanering av interaction-detaljer, bucket-aggregering och payload-byggare.

Utflyttat ur routers/audit_logs.py for radtaket i arkitektur-kontraktet.
Routern importerar namnen har ifran, sa tester kan fortsatta patcha
audit_logs.<namn> pa routermodulen.
"""
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


ERROR_ACTION_PATTERNS = ("%failed%", "%error%", "%exception%")
INTERACTION_PERIODS = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
INTERACTION_SENSITIVE_KEY_PARTS = (
    "password",
    "losenord",
    "token",
    "secret",
    "cookie",
    "authorization",
    "api_key",
    "apikey",
    "header",
    "endpoint",
    "request_body",
    "body",
    "localref",
    "local_ref",
    "filename",
    "file_name",
    "filepath",
    "file_path",
    "path",
    "url",
)
INTERACTION_VALUE_SAMPLE_KEY_PARTS = (
    "value",
    "values",
    "sample",
    "samples",
    "text",
    "clipboard",
    "copied",
    "cell",
    "row",
)
INTERACTION_PUBLIC_EVENT_TYPES = {
    "public_meta_file_select",
    "public_meta_upload_start",
    "public_meta_upload_progress",
    "public_meta_upload_success",
    "public_meta_upload_error",
}
KNOWN_INTERACTION_CONTROLS = [
    {"view_id": "schedule", "control_id": "clearBtn", "label": "Rensa dag"},
    {"view_id": "schedule", "control_id": "copyBtn", "label": "Kopiera dag"},
    {"view_id": "schedule", "control_id": "undoBtn", "label": "Angra"},
    {"view_id": "schedule", "control_id": "redoBtn", "label": "Gor om"},
    {"view_id": "schedule", "control_id": "schedule_cell_select", "label": "Bemanningscell"},
    {"view_id": "overview", "control_id": "overview_day_select", "label": "Oversiktsdag"},
    {"view_id": "overview", "control_id": "undoBtn", "label": "Angra"},
    {"view_id": "overview", "control_id": "redoBtn", "label": "Gor om"},
    {"view_id": "persons", "control_id": "new-person", "label": "Ny person"},
    {"view_id": "persons", "control_id": "bulk-persons", "label": "Flera nya personer"},
    {"view_id": "persons", "control_id": "import-persons", "label": "Importera personer"},
    {"view_id": "activities", "control_id": "new-act", "label": "Ny aktivitet"},
    {"view_id": "activities", "control_id": "bulk-activities", "label": "Flera nya aktiviteter"},
    {"view_id": "users", "control_id": "new-user", "label": "Ny anvandare"},
    {"view_id": "users", "control_id": "role-view-access", "label": "Vybehorigheter"},
    {"view_id": "businesses", "control_id": "new-business", "label": "Ny verksamhet"},
    {"view_id": "productivity", "control_id": "productivityOverviewPrevDate", "label": "Foregaende datum"},
    {"view_id": "productivity", "control_id": "productivityOverviewNextDate", "label": "Nasta datum"},
    {"view_id": "dataFetch", "control_id": "dataFetchPlan", "label": "Tolka"},
    {"view_id": "dataFetch", "control_id": "dataFetchRun", "label": "Hamta data"},
    {"view_id": "dataFetch", "control_id": "dataFetchExport", "label": "Exportera Excel"},
    {"view_id": "mcp", "control_id": "mcp-query-send", "label": "Skicka MCP-fraga"},
    {"view_id": "allocationUploads", "control_id": "allocation-upload-all", "label": "Valj filer"},
    {"view_id": "allocationUploads", "control_id": "allocation-clear-all-files", "label": "Rensa alla"},
    {"view_id": "allocationProcess", "control_id": "allocation-flow-run", "label": "Kor flode"},
    {"view_id": "allocationProcess", "control_id": "allocation-copy-column", "label": "Kopiera kolumn"},
    {"view_id": "allocationProcess", "control_id": "allocation-open-excel", "label": "Oppna i Excel"},
    {"view_id": "allocationProcess", "control_id": "allocation-download-csv", "label": "Ladda ner CSV"},
    {"view_id": "allocationSettings", "control_id": "data-map-save", "label": "Spara ytkarta"},
    {"view_id": "allocationSplit", "control_id": "split-values", "label": "Dela varden"},
    {"view_id": "meta", "control_id": "metaRefresh", "label": "Uppdatera Meta"},
    {"view_id": "metaUpload", "control_id": "metaUploadForm", "label": "Meta-uppladdning"},
    {"view_id": "analytics", "control_id": "refreshAuditBtn", "label": "Uppdatera Historik"},
    {"view_id": "analytics", "control_id": "historyTrackingChatForm", "label": "Historik-AI"},
]

AUDIT_ENTITY_LABELS = {
    "coredata_file": "Karnfil",
    "mcp_query": "MCP-fraga",
    "meta_media_upload": "Meta-uppladdning",
    "rfid_scan_event": "RFID-stämpel",
    "workflow_source": "Workflow-underlag",
}


def _apply_filters(query, *, business_id: int | None, user_id: int | None, entity_type: str | None, action: str | None,
                   entity_id: int | None, from_at: datetime | None, to_at: datetime | None):
    if not isinstance(business_id, int):
        business_id = None
    if business_id is not None:
        query = query.where(AuditLog.business_id == business_id)
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


def _entity_label(entity_type: str | None) -> str | None:
    if not entity_type:
        return None
    return AUDIT_ENTITY_LABELS.get(entity_type, entity_type)


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


def _bounded_int(value: Any, *, minimum: int = 0, maximum: int = 10_000_000) -> int | None:
    number = _as_int(value)
    if number is None:
        return None
    return min(maximum, max(minimum, number))


def _period_start(period: str) -> datetime | None:
    if period == "all":
        return None
    return datetime.now(timezone.utc) - INTERACTION_PERIODS.get(period, INTERACTION_PERIODS["30d"])


def _interaction_created_after(value: datetime | None, cutoff: datetime) -> bool:
    if value is None:
        return False
    comparable = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return comparable >= cutoff


def _safe_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _is_sensitive_interaction_key(key: str) -> bool:
    safe_key = _safe_key(key)
    if safe_key in {"page_path"}:
        return False
    return any(part in safe_key for part in INTERACTION_SENSITIVE_KEY_PARTS)


def _is_value_sample_key(key: str) -> bool:
    safe_key = _safe_key(key)
    safe_allowed = {
        "column_label",
        "table_label",
        "control_label",
        "view_label",
        "selected_option_label",
        "label",
        "row_count",
        "rows",
    }
    if safe_key in safe_allowed:
        return False
    return any(part in safe_key for part in INTERACTION_VALUE_SAMPLE_KEY_PARTS)


def _sanitize_interaction_detail_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        return None
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return _clean_text(value, max_length=500)
    if isinstance(value, list):
        cleaned = [
            _sanitize_interaction_detail_value(item, depth=depth + 1)
            for item in value[:30]
        ]
        return [item for item in cleaned if item is not None]
    if isinstance(value, dict):
        return _sanitize_interaction_detail(value, depth=depth + 1)
    return _clean_text(value, max_length=200)


def _sanitize_interaction_detail(detail: Any, *, depth: int = 0) -> dict[str, Any] | None:
    if not isinstance(detail, dict):
        return None
    cleaned: dict[str, Any] = {}
    for raw_key, value in list(detail.items())[:80]:
        key = _clean_text(raw_key, max_length=80)
        if not key:
            continue
        if _is_sensitive_interaction_key(key):
            continue
        if _is_value_sample_key(key) and not settings.TRACKING_ALLOW_VALUE_SAMPLES:
            if isinstance(value, str):
                cleaned[f"{key}_length"] = len(value)
            elif isinstance(value, list):
                cleaned[f"{key}_count"] = len(value)
            continue
        safe_value = _sanitize_interaction_detail_value(value, depth=depth)
        if safe_value is not None:
            cleaned[key] = safe_value
    return cleaned or None


def _interaction_payload(payload) -> dict[str, Any]:
    detail = _sanitize_interaction_detail(payload.detail)
    if current_trace_id():
        detail = attach_trace_context(detail or {})
    return {
        "event_type": _clean_text(payload.event_type, max_length=80) or "interaction",
        "view_id": _clean_text(payload.view_id, max_length=80),
        "page_path": _safe_path(payload.page_path),
        "control_id": _clean_text(payload.control_id, max_length=160),
        "control_label": _clean_text(payload.control_label, max_length=180),
        "control_role": _clean_text(payload.control_role, max_length=80),
        "feature": _clean_text(payload.feature, max_length=80),
        "flow_id": _clean_text(payload.flow_id, max_length=120),
        "table_key": _clean_text(payload.table_key, max_length=120),
        "table_label": _clean_text(payload.table_label, max_length=160),
        "column_index": _bounded_int(payload.column_index, minimum=0, maximum=500),
        "column_label": _clean_text(payload.column_label, max_length=180),
        "row_count": _bounded_int(payload.row_count, minimum=0, maximum=10_000_000),
        "client_surface": _clean_text(payload.client_surface, max_length=40) or "web",
        "interaction_id": _clean_text(payload.interaction_id, max_length=80),
        "status": (_clean_text(payload.status, max_length=20) or "ok").lower(),
        "detail": detail,
    }


def _interaction_row(row: UserInteractionEvent, username: str | None = None, display_name: str | None = None) -> InteractionEventOut:
    return InteractionEventOut(
        id=row.id,
        created_at=row.created_at,
        business_id=row.business_id,
        user_id=row.user_id,
        username=username,
        display_name=display_name,
        event_type=row.event_type,
        view_id=row.view_id,
        page_path=row.page_path,
        control_id=row.control_id,
        control_label=row.control_label,
        control_role=row.control_role,
        feature=row.feature,
        flow_id=row.flow_id,
        table_key=row.table_key,
        table_label=row.table_label,
        column_index=row.column_index,
        column_label=row.column_label,
        row_count=row.row_count,
        client_surface=row.client_surface,
        interaction_id=row.interaction_id,
        status=row.status,
        detail=row.detail,
    )


def _apply_interaction_filters(
    query,
    *,
    business_id: int | None,
    user_id: int | None,
    view_id: str | None,
    event_type: str | None,
    feature: str | None,
    flow_id: str | None,
    control_id: str | None,
    q: str | None,
    from_at: datetime | None,
    to_at: datetime | None,
):
    if isinstance(business_id, int):
        query = query.where(UserInteractionEvent.business_id == business_id)
    if isinstance(user_id, int):
        query = query.where(UserInteractionEvent.user_id == user_id)
    if view_id:
        query = query.where(UserInteractionEvent.view_id == view_id.strip())
    if event_type:
        query = query.where(UserInteractionEvent.event_type.ilike(f"%{event_type.strip()}%"))
    if feature:
        query = query.where(UserInteractionEvent.feature == feature.strip())
    if flow_id:
        query = query.where(UserInteractionEvent.flow_id == flow_id.strip())
    if control_id:
        query = query.where(UserInteractionEvent.control_id.ilike(f"%{control_id.strip()}%"))
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(or_(
            UserInteractionEvent.event_type.ilike(pattern),
            UserInteractionEvent.view_id.ilike(pattern),
            UserInteractionEvent.control_id.ilike(pattern),
            UserInteractionEvent.control_label.ilike(pattern),
            UserInteractionEvent.feature.ilike(pattern),
            UserInteractionEvent.flow_id.ilike(pattern),
            UserInteractionEvent.table_key.ilike(pattern),
            UserInteractionEvent.table_label.ilike(pattern),
            UserInteractionEvent.column_label.ilike(pattern),
        ))
    if from_at is not None:
        query = query.where(UserInteractionEvent.created_at >= from_at)
    if to_at is not None:
        query = query.where(UserInteractionEvent.created_at <= to_at)
    return query


def _interaction_bucket_key(row: UserInteractionEvent, kind: str) -> str:
    if kind == "users":
        return str(row.user_id or "system")
    if kind == "views":
        return row.view_id or "-"
    if kind == "features":
        return row.feature or "-"
    if kind == "controls":
        return row.control_label or row.control_id or "-"
    if kind == "flows":
        return row.flow_id or "-"
    if kind == "columns":
        if row.column_label:
            return f"{row.flow_id or '-'} / {row.table_label or row.table_key or '-'} / {row.column_label}"
        return "-"
    if kind == "surfaces":
        return row.client_surface or "-"
    if kind == "copy_patterns":
        if row.event_type not in {"copy_column", "auto_copy_column", "copy_text", "download", "export"}:
            return "-"
        if row.event_type in {"copy_column", "auto_copy_column"}:
            detail = row.detail if isinstance(row.detail, dict) else {}
            copy_mode = _clean_text(detail.get("copy_mode"), max_length=80) if detail else ""
            prefix = copy_mode or row.event_type
            return f"{prefix}: {row.flow_id or '-'} / {row.table_label or row.table_key or '-'} / {row.column_label or row.column_index or '-'}"
        return row.event_type
    return "-"


def _buckets_from_rows(rows: list[UserInteractionEvent], kind: str, users_by_id: dict[int, str] | None = None) -> list[AuditSummaryBucket]:
    counter = Counter(_interaction_bucket_key(row, kind) for row in rows)
    counter.pop("-", None)
    if kind == "users" and users_by_id:
        return [
            _bucket(key, users_by_id.get(_as_int(key) or -1, "System" if key == "system" else key), count)
            for key, count in counter.most_common(8)
        ]
    return _counter_buckets(counter)


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
    result = {
        "path": _safe_path(payload.path),
        "method": _clean_text(payload.method.upper(), max_length=10) or "GET",
        "status_code": status_code,
        "error_code": error_code,
        "message": _clean_text(payload.message),
        "detail": _detail_summary(payload.detail),
        "page_path": _safe_path(payload.page_path),
    }
    trace_id = normalize_trace_id(payload.trace_id)
    if trace_id:
        result["trace_id"] = trace_id
    return result


def _client_event_payload(payload: AuditClientEventIn) -> dict[str, Any]:
    return {
        "event_type": _clean_text(payload.event_type, max_length=80) or "client_event",
        "view_id": _clean_text(payload.view_id, max_length=80),
        "view_label": _clean_text(payload.view_label, max_length=120),
        "page_path": _safe_path(payload.page_path),
    }


def _safe_name_list(values: list[str], *, max_items: int = 40, max_length: int = 80) -> list[str]:
    cleaned: list[str] = []
    for value in values[:max_items]:
        text = _clean_text(value, max_length=max_length)
        if text:
            cleaned.append(text)
    return cleaned


def _safe_counter_map(values: dict[str, int], *, max_items: int = 40) -> dict[str, int]:
    cleaned: dict[str, int] = {}
    for key, value in list((values or {}).items())[:max_items]:
        name = _clean_text(key, max_length=80)
        if not name:
            continue
        try:
            cleaned[name] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return cleaned


def _local_run_payload(payload: AuditLocalRunIn) -> dict[str, Any]:
    return {
        "source": "desktop",
        "feature": _clean_text(payload.feature, max_length=40) or "local",
        "flow_id": _clean_text(payload.flow_id, max_length=120),
        "status": _clean_text(payload.status, max_length=20) or "ok",
        "error_type": _clean_text(payload.error_type, max_length=120),
        "duration_ms": payload.duration_ms,
        "file_types": _safe_name_list(payload.file_types),
        "row_counts": _safe_counter_map(payload.row_counts),
        "result_counts": _safe_counter_map(payload.result_counts),
    }


def _interaction_chat_context(rows: list[UserInteractionEvent]) -> str:
    raw_events = []
    for row in rows[:200]:
        raw_events.append({
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "event_type": row.event_type,
            "view_id": row.view_id,
            "control": row.control_label or row.control_id,
            "feature": row.feature,
            "flow_id": row.flow_id,
            "table": row.table_label or row.table_key,
            "column": row.column_label,
            "row_count": row.row_count,
            "client_surface": row.client_surface,
            "status": row.status,
            "detail": row.detail or {},
        })
    summary = {
        "event_count": len(rows),
        "top_views": Counter(row.view_id or "-" for row in rows).most_common(12),
        "top_controls": Counter(row.control_label or row.control_id or "-" for row in rows).most_common(12),
        "top_flows": Counter(row.flow_id or "-" for row in rows).most_common(12),
        "top_columns": Counter(row.column_label or "-" for row in rows if row.column_label).most_common(12),
        "top_surfaces": Counter(row.client_surface or "-" for row in rows).most_common(8),
        "copy_events": Counter(_interaction_bucket_key(row, "copy_patterns") for row in rows).most_common(12),
    }
    return json.dumps({"summary": summary, "raw_events": raw_events}, ensure_ascii=False, default=str)

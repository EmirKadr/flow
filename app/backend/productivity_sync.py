from __future__ import annotations

import gzip
import csv
import json
import logging
import os
import shutil
import threading
import time
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import audit
from .compiled_data_paths import compiled_data_root
from .database import SessionLocal
from .external_data_client import ExternalDataClient
from .business_scope import DEFAULT_BUSINESS_CODE, default_business_tenant
from .models import Business
from .productivity_service import ProductivitySourceError, find_kpi_file
from .workflow_data import (
    WorkflowDataError,
    fetch_source_to_temp,
    productivity_api_source_map,
    source_spec,
    sources_available,
)


logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo("Europe/Berlin")
PRODUCTIVITY_BOOTSTRAP_DAYS_BACK = 13
PRODUCTIVITY_HISTORY_BACKFILL_DAYS_PER_RUN = 1
SNAPSHOT_SOURCE_KEYS = (
    "pick",
    "trans",
    "pallet",
    "receive",
    "order_log",
    "sort",
    "base_pallet",
    "kpi",
)
EVENT_SOURCE_KEYS = ("pick", "trans", "pallet", "receive", "order_log", "sort", "base_pallet")
SNAPSHOT_STATUS: dict[str, Any] = {
    "status": "not_started",
    "last_sync_at": None,
    "next_sync_at": None,
    "source": "api_snapshot",
}
_SYNC_LOCK = threading.Lock()
_SCHEDULER_STARTED = False


class ProductivitySyncError(RuntimeError):
    pass


def productivity_snapshot_root(reference_dir: Path | str | None = None) -> Path:
    base = Path(reference_dir) if reference_dir is not None else compiled_data_root()
    return base / "productivity_snapshots"


def productivity_snapshot_dir(snapshot_date: date, reference_dir: Path | str | None = None) -> Path:
    return productivity_snapshot_root(reference_dir) / snapshot_date.isoformat()


def productivity_snapshot_metadata_path(snapshot_date: date, reference_dir: Path | str | None = None) -> Path:
    return productivity_snapshot_dir(snapshot_date, reference_dir) / "metadata.json"


def productivity_snapshot_error_path(snapshot_date: date, reference_dir: Path | str | None = None) -> Path:
    return productivity_snapshot_dir(snapshot_date, reference_dir) / "last_error.json"


def productivity_backfill_state_path(reference_dir: Path | str | None = None) -> Path:
    return productivity_snapshot_root(reference_dir) / "backfill.json"


def productivity_prebuild_state_path(reference_dir: Path | str | None = None) -> Path:
    return productivity_snapshot_root(reference_dir) / "prebuild.json"


def productivity_snapshot_source_path(
    snapshot_date: date,
    source_key: str,
    reference_dir: Path | str | None = None,
) -> Path:
    return productivity_snapshot_dir(snapshot_date, reference_dir) / f"{source_key}.csv.gz"


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _gzip_csv_copy(source_path: Path, target_path: Path) -> int:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.{os.getpid()}.tmp")
    row_count = 0
    with source_path.open("rt", encoding="utf-8-sig", newline="") as source, gzip.open(
        tmp_path,
        "wt",
        encoding="utf-8",
        newline="",
    ) as target:
        for index, line in enumerate(source):
            if index > 0 and line.strip():
                row_count += 1
            target.write(line)
    tmp_path.replace(target_path)
    return row_count


def _read_tsv_rows(source_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with source_path.open("rt", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        headers = list(reader.fieldnames or [])
        rows = [{str(key or ""): str(value or "") for key, value in row.items()} for row in reader]
    return headers, rows


def _gzip_csv_rows(headers: list[str], rows: list[dict[str, str]], target_path: Path) -> int:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.{os.getpid()}.tmp")
    with gzip.open(tmp_path, "wt", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=headers, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    tmp_path.replace(target_path)
    return len(rows)


def _row_text(row: dict[str, str], *names: str) -> str:
    lower = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        value = row.get(name)
        if value:
            return str(value).strip()
        value = lower.get(str(name).strip().lower())
        if value:
            return str(value).strip()
    return ""


def _parse_row_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _source_row_date(source_key: str, row: dict[str, str]) -> date | None:
    if source_key in {"pick", "pallet"}:
        timestamp = _parse_row_timestamp(_row_text(row, "Ändrad", "Andrad", "timestamp", "Timestamp"))
    else:
        timestamp = _parse_row_timestamp(_row_text(row, "Timestamp", "timestamp", "Ändrad", "Andrad"))
    if timestamp is None:
        return None
    return timestamp.astimezone(LOCAL_TZ).date() if timestamp.tzinfo else timestamp.date()


def next_productivity_sync_at(now: datetime | None = None) -> datetime:
    current = now.astimezone(LOCAL_TZ) if now else datetime.now(LOCAL_TZ)
    minute = 30 if current.minute < 30 else 60
    if minute == 60:
        next_time = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_time = current.replace(minute=30, second=0, microsecond=0)
    if next_time <= current:
        next_time += timedelta(minutes=30)
    return next_time


def previous_productivity_sync_boundary(now: datetime | None = None) -> datetime:
    current = now.astimezone(LOCAL_TZ) if now else datetime.now(LOCAL_TZ)
    minute = 30 if current.minute >= 30 else 0
    return current.replace(minute=minute, second=0, microsecond=0)


def _date_filters(snapshot_date: date) -> list[dict[str, Any]]:
    start = datetime.combine(snapshot_date, datetime_time.min).strftime("%Y-%m-%d %H:%M:%S")
    end = datetime.combine(snapshot_date + timedelta(days=1), datetime_time.min).strftime("%Y-%m-%d %H:%M:%S")
    return [ExternalDataClient.between("timestamp", start, end)]


def _date_range_filters(start_date: date, end_date: date) -> list[dict[str, Any]]:
    start = datetime.combine(start_date, datetime_time.min).strftime("%Y-%m-%d %H:%M:%S")
    end = datetime.combine(end_date + timedelta(days=1), datetime_time.min).strftime("%Y-%m-%d %H:%M:%S")
    return [ExternalDataClient.between("timestamp", start, end)]


def _source_filters(source_key: str, snapshot_date: date) -> list[dict[str, Any]] | None:
    return _date_filters(snapshot_date) if source_key in EVENT_SOURCE_KEYS else None


def _source_range_filters(source_key: str, start_date: date, end_date: date) -> list[dict[str, Any]] | None:
    return _date_range_filters(start_date, end_date) if source_key in EVENT_SOURCE_KEYS else None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _history_start_date() -> date | None:
    return _parse_date(os.getenv("PRODUCTIVITY_HISTORY_START_DATE"))


def _snapshot_dates(reference_dir: Path | str | None = None) -> list[date]:
    root = productivity_snapshot_root(reference_dir)
    if not root.is_dir():
        return []
    dates: list[date] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        snapshot_date = _parse_date(child.name)
        if snapshot_date is not None:
            dates.append(snapshot_date)
    return sorted(dates)


def productivity_backfill_status(reference_dir: Path | str | None = None) -> dict[str, Any]:
    state = _read_json(productivity_backfill_state_path(reference_dir)) or {}
    return {
        "source": "api_snapshot_backfill",
        "status": state.get("status") or "not_started",
        "last_run_date": state.get("last_run_date"),
        "last_sync_at": state.get("last_sync_at"),
        "next_cursor_date": state.get("next_cursor_date"),
        "days_per_run": int(state.get("days_per_run") or PRODUCTIVITY_HISTORY_BACKFILL_DAYS_PER_RUN),
        "history_start_date": state.get("history_start_date"),
        "dates": state.get("dates") or [],
        "errors": state.get("errors") or [],
    }


def productivity_prebuild_status(reference_dir: Path | str | None = None) -> dict[str, Any]:
    state = _read_json(productivity_prebuild_state_path(reference_dir)) or {}
    return {
        "source": "person_productivity_prebuild",
        "status": state.get("status") or "not_started",
        "last_run_date": state.get("last_run_date"),
        "last_sync_at": state.get("last_sync_at"),
        "dates": state.get("dates") or [],
        "results": state.get("results") or [],
        "errors": state.get("errors") or [],
    }


def productivity_snapshot_status(
    snapshot_date: date | None = None,
    *,
    reference_dir: Path | str | None = None,
) -> dict[str, Any]:
    day = snapshot_date or datetime.now(LOCAL_TZ).date()
    metadata = _read_json(productivity_snapshot_metadata_path(day, reference_dir)) or {}
    error = _read_json(productivity_snapshot_error_path(day, reference_dir)) or {}
    files_ready = all(productivity_snapshot_source_path(day, key, reference_dir).is_file() for key in SNAPSHOT_SOURCE_KEYS)
    status_text = str(metadata.get("status") or SNAPSHOT_STATUS.get("status") or "missing")
    if status_text == "ok" and not files_ready:
        status_text = "missing"
    return {
        "source": "api_snapshot" if metadata else SNAPSHOT_STATUS.get("source", "api_snapshot"),
        "date": day.isoformat(),
        "status": status_text,
        "ready": status_text == "ok" and files_ready,
        "last_sync_at": metadata.get("last_sync_at") or SNAPSHOT_STATUS.get("last_sync_at"),
        "next_sync_at": SNAPSHOT_STATUS.get("next_sync_at") or next_productivity_sync_at().isoformat(timespec="seconds"),
        "sources": metadata.get("sources") or [],
        "last_error": error.get("message") if error else None,
        "failed_source": error.get("failed_source") if error else None,
    }


def _next_backfill_dates(
    *,
    now: datetime,
    reference_dir: Path | str | None = None,
    days_per_run: int = PRODUCTIVITY_HISTORY_BACKFILL_DAYS_PER_RUN,
    state: dict[str, Any] | None = None,
) -> list[date]:
    configured_start = _history_start_date()
    stored_start = _parse_date((state or {}).get("history_start_date"))
    start_limit = configured_start or stored_start
    cursor = _parse_date((state or {}).get("next_cursor_date"))
    if cursor is None:
        snapshot_dates = _snapshot_dates(reference_dir)
        cursor = (snapshot_dates[0] - timedelta(days=1)) if snapshot_dates else (now.date() - timedelta(days=1))

    dates: list[date] = []
    current = cursor
    max_days = max(1, int(days_per_run or 1))
    while len(dates) < max_days:
        if start_limit is not None and current < start_limit:
            break
        if not productivity_snapshot_status(current, reference_dir=reference_dir).get("ready"):
            dates.append(current)
        current -= timedelta(days=1)
    return dates


def ensure_productivity_historical_backfill(
    *,
    now: datetime | None = None,
    days_per_run: int = PRODUCTIVITY_HISTORY_BACKFILL_DAYS_PER_RUN,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    db: Session | None = None,
    user_id: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    current = (now or datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
    today_key = current.date().isoformat()
    state = productivity_backfill_status(reference_dir)
    if not force and state.get("last_run_date") == today_key:
        return {**state, "status": state.get("status") or "ok", "skipped": True}

    if not sources_available(tuple(productivity_api_source_map().values())):
        payload = {
            "source": "api_snapshot_backfill",
            "status": "not_configured",
            "last_run_date": today_key,
            "last_sync_at": None,
            "next_cursor_date": state.get("next_cursor_date"),
            "days_per_run": max(1, int(days_per_run or 1)),
            "history_start_date": _history_start_date().isoformat() if _history_start_date() else state.get("history_start_date"),
            "dates": [],
            "errors": [],
        }
        atomic_write_json(productivity_backfill_state_path(reference_dir), payload)
        return payload

    dates = _next_backfill_dates(
        now=current,
        reference_dir=reference_dir,
        days_per_run=days_per_run,
        state=state,
    )
    if not dates:
        payload = {
            "source": "api_snapshot_backfill",
            "status": "complete",
            "last_run_date": today_key,
            "last_sync_at": current.isoformat(timespec="seconds"),
            "next_cursor_date": state.get("next_cursor_date"),
            "days_per_run": max(1, int(days_per_run or 1)),
            "history_start_date": _history_start_date().isoformat() if _history_start_date() else state.get("history_start_date"),
            "dates": [],
            "errors": [],
        }
        atomic_write_json(productivity_backfill_state_path(reference_dir), payload)
        return payload

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    next_cursor = dates[0]
    for snapshot_date in dates:
        try:
            result = sync_productivity_snapshot(
                snapshot_date,
                reference_dir=reference_dir,
                business_code=business_code,
                db=db,
                user_id=user_id,
            )
            if str(result.get("status") or "") == "running":
                errors.append({"date": snapshot_date.isoformat(), "error_type": "running"})
                break
            results.append(result)
            next_cursor = snapshot_date - timedelta(days=1)
        except ProductivitySyncError as exc:
            errors.append(
                {
                    "date": snapshot_date.isoformat(),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            break

    synced_at = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
    payload = {
        "source": "api_snapshot_backfill",
        "status": "error" if errors else "ok",
        "last_run_date": today_key,
        "last_sync_at": synced_at if results else state.get("last_sync_at"),
        "next_cursor_date": next_cursor.isoformat(),
        "days_per_run": max(1, int(days_per_run or 1)),
        "history_start_date": _history_start_date().isoformat() if _history_start_date() else state.get("history_start_date"),
        "dates": [item.isoformat() for item in dates],
        "results": results,
        "errors": errors,
    }
    atomic_write_json(productivity_backfill_state_path(reference_dir), payload)
    return payload


def productivity_snapshot_is_stale(
    snapshot_date: date | None = None,
    *,
    now: datetime | None = None,
    reference_dir: Path | str | None = None,
) -> bool:
    current = now.astimezone(LOCAL_TZ) if now else datetime.now(LOCAL_TZ)
    day = snapshot_date or current.date()
    status = productivity_snapshot_status(day, reference_dir=reference_dir)
    if not status.get("ready"):
        return True
    if day != current.date():
        return False
    last_sync = status.get("last_sync_at")
    if not last_sync:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last_sync))
    except ValueError:
        return True
    boundary = previous_productivity_sync_boundary(now)
    return last_dt.astimezone(LOCAL_TZ) < boundary


def productivity_snapshot_files(
    snapshot_date: date,
    *,
    reference_dir: Path | str | None = None,
) -> dict[str, Path]:
    status = productivity_snapshot_status(snapshot_date, reference_dir=reference_dir)
    if not status.get("ready"):
        raise ProductivitySyncError("Produktivitetens API-snapshot saknas eller är inte komplett.")
    return {
        key: productivity_snapshot_source_path(snapshot_date, key, reference_dir)
        for key in SNAPSHOT_SOURCE_KEYS
    }


def productivity_bootstrap_dates(
    end_date: date | None = None,
    *,
    days_back: int = PRODUCTIVITY_BOOTSTRAP_DAYS_BACK,
) -> list[date]:
    day = end_date or datetime.now(LOCAL_TZ).date()
    span = max(0, int(days_back))
    return [day - timedelta(days=offset) for offset in range(span, -1, -1)]


def _sync_audit_payload(
    *,
    snapshot_date: date,
    status_text: str,
    sources: list[dict[str, Any]] | None = None,
    error_type: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "date": snapshot_date.isoformat(),
        "status": status_text,
        "sources": [
            {
                "key": str(item.get("key") or ""),
                "view": str(item.get("view") or ""),
                "status": str(item.get("status") or ""),
                "rows": int(item.get("rows") or 0),
            }
            for item in (sources or [])
        ],
    }
    if error_type:
        payload["error_type"] = error_type
    return payload


def _audit_sync(
    db: Session | None,
    *,
    snapshot_date: date,
    status_text: str,
    sources: list[dict[str, Any]] | None = None,
    error_type: str | None = None,
    user_id: int | None = None,
) -> None:
    if db is None:
        return
    audit.log_and_commit(
        db,
        entity_type="productivity_sync",
        entity_id=0,
        action="sync",
        old_value=None,
        new_value=_sync_audit_payload(
            snapshot_date=snapshot_date,
            status_text=status_text,
            sources=sources,
            error_type=error_type,
        ),
        user_id=user_id,
        logger=logger,
        context="productivity sync audit",
    )


def _productivity_cache_business_id(db: Session | None, business_code: str | None) -> int | None:
    if db is None:
        return None
    code = str(business_code or DEFAULT_BUSINESS_CODE or "").strip().lower()
    if not code:
        return None
    return db.execute(select(Business.id).where(func.lower(Business.code) == code)).scalar()


def _productivity_data_source_tenant(db: Session | None, business_code: str | None) -> str | None:
    code = str(business_code or DEFAULT_BUSINESS_CODE or "").strip().lower()
    if not code:
        return None
    if db is None:
        return None
    fallback = default_business_tenant(code)
    try:
        return db.execute(select(Business.tenant).where(func.lower(Business.code) == code)).scalar() or fallback
    except Exception:
        rollback = getattr(db, "rollback", None)
        if callable(rollback):
            rollback()
        logger.warning("Could not resolve productivity data-source tenant from database; using default tenant.")
        return fallback


def _warm_person_productivity_daily_cache(
    db: Session | None,
    snapshot_date: date,
    *,
    reference_dir: Path | str | None,
    business_code: str | None,
    sync: dict[str, Any],
) -> dict[str, Any] | None:
    if db is None:
        return None
    try:
        from .person_productivity_cache import ensure_person_productivity_daily_cache

        return ensure_person_productivity_daily_cache(
            db,
            productivity_snapshot_files(snapshot_date, reference_dir=reference_dir),
            report_date=snapshot_date,
            business_id=_productivity_cache_business_id(db, business_code),
            sync=sync,
        )
    except Exception as exc:
        logger.warning("Could not warm person productivity daily cache.", exc_info=True)
        return {
            "date": snapshot_date.isoformat(),
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }


def prebuild_ready_productivity_days(
    *,
    now: datetime | None = None,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    db: Session | None = None,
    force: bool = False,
) -> dict[str, Any]:
    current = (now or datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
    today = current.date()
    today_key = today.isoformat()
    state = productivity_prebuild_status(reference_dir)
    if not force and state.get("last_run_date") == today_key:
        return {**state, "status": state.get("status") or "ok", "skipped": True}
    if db is None:
        payload = {
            "source": "person_productivity_prebuild",
            "status": "not_configured",
            "last_run_date": today_key,
            "last_sync_at": None,
            "dates": [],
            "results": [],
            "errors": [{"message": "database session missing"}],
        }
        atomic_write_json(productivity_prebuild_state_path(reference_dir), payload)
        return payload

    ready_dates = [
        snapshot_date
        for snapshot_date in _snapshot_dates(reference_dir)
        if snapshot_date < today
        and productivity_snapshot_status(snapshot_date, reference_dir=reference_dir).get("ready")
    ]
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for snapshot_date in ready_dates:
        sync = productivity_snapshot_status(snapshot_date, reference_dir=reference_dir)
        result = _warm_person_productivity_daily_cache(
            db,
            snapshot_date,
            reference_dir=reference_dir,
            business_code=business_code,
            sync=sync,
        )
        if result is None:
            continue
        result = {"date": snapshot_date.isoformat(), **result}
        if str(result.get("status") or "") == "error":
            errors.append(result)
        else:
            results.append(result)

    payload = {
        "source": "person_productivity_prebuild",
        "status": "error" if errors else "ok",
        "last_run_date": today_key,
        "last_sync_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        "dates": [item.isoformat() for item in ready_dates],
        "results": results,
        "errors": errors,
    }
    atomic_write_json(productivity_prebuild_state_path(reference_dir), payload)
    return payload


def sync_productivity_snapshot(
    snapshot_date: date | None = None,
    *,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    db: Session | None = None,
    user_id: int | None = None,
    warm_cache: bool = True,
) -> dict[str, Any]:
    day = snapshot_date or datetime.now(LOCAL_TZ).date()
    if not sources_available(tuple(productivity_api_source_map().values())):
        status_payload = {
            "date": day.isoformat(),
            "status": "not_configured",
            "source": "api_snapshot",
            "sources": [],
            "last_sync_at": None,
            "next_sync_at": next_productivity_sync_at().isoformat(timespec="seconds"),
        }
        SNAPSHOT_STATUS.update(status_payload)
        return status_payload
    if not _SYNC_LOCK.acquire(blocking=False):
        status = productivity_snapshot_status(day, reference_dir=reference_dir)
        status["status"] = "running"
        return status

    temp_paths: list[Path] = []
    source_entries: list[dict[str, Any]] = []
    current_source: dict[str, Any] | None = None
    snapshot_dir = productivity_snapshot_dir(day, reference_dir)
    staging_dir = snapshot_dir / f".staging-{os.getpid()}-{int(time.time() * 1000)}"
    try:
        source_map = productivity_api_source_map()
        tenant = _productivity_data_source_tenant(db, business_code)
        staging_dir.mkdir(parents=True, exist_ok=True)
        for file_key in SNAPSHOT_SOURCE_KEYS:
            source_key = source_map[file_key]
            spec = source_spec(source_key)
            current_source = {"key": file_key, "view": spec.view}
            source_status = "api"
            fallback_reason = None
            try:
                if tenant:
                    temp_path, entry = fetch_source_to_temp(
                        source_key,
                        filters=_source_filters(file_key, day),
                        tenant=tenant,
                    )
                else:
                    temp_path, entry = fetch_source_to_temp(source_key, filters=_source_filters(file_key, day))
                temp_paths.append(temp_path)
                view = entry.view
            except WorkflowDataError as exc:
                if file_key != "kpi":
                    raise
                try:
                    temp_path = find_kpi_file(
                        reference_dir,
                        business_code or DEFAULT_BUSINESS_CODE,
                        db=db,
                    )
                except ProductivitySourceError:
                    raise exc
                view = "v_ask_kpi_target"
                source_status = "coredata_fallback"
                fallback_reason = str(exc)
            target_path = staging_dir / f"{file_key}.csv.gz"
            row_count = _gzip_csv_copy(temp_path, target_path)
            source_entry = {
                "key": file_key,
                "view": view,
                "status": source_status,
                "rows": row_count,
            }
            if fallback_reason:
                source_entry["fallback_reason"] = fallback_reason
            source_entries.append(source_entry)

        synced_at = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
        metadata = {
            "date": day.isoformat(),
            "status": "ok",
            "source": "api_snapshot",
            "last_sync_at": synced_at,
            "next_sync_at": next_productivity_sync_at().isoformat(timespec="seconds"),
            "sources": source_entries,
        }
        for file_key in SNAPSHOT_SOURCE_KEYS:
            (staging_dir / f"{file_key}.csv.gz").replace(
                productivity_snapshot_source_path(day, file_key, reference_dir)
            )
        atomic_write_json(productivity_snapshot_metadata_path(day, reference_dir), metadata)
        productivity_snapshot_error_path(day, reference_dir).unlink(missing_ok=True)
        SNAPSHOT_STATUS.update(metadata)
        if warm_cache:
            _warm_person_productivity_daily_cache(
                db,
                day,
                reference_dir=reference_dir,
                business_code=business_code,
                sync=metadata,
            )
        _audit_sync(db, snapshot_date=day, status_text="ok", sources=source_entries, user_id=user_id)
        return metadata
    except Exception as exc:
        error_payload = {
            "date": day.isoformat(),
            "status": "error",
            "message": "Extern datakälla kunde inte synkas.",
            "error_type": type(exc).__name__,
            "updated_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
            "next_sync_at": next_productivity_sync_at().isoformat(timespec="seconds"),
        }
        if current_source:
            error_payload["failed_source"] = current_source
        atomic_write_json(productivity_snapshot_error_path(day, reference_dir), error_payload)
        SNAPSHOT_STATUS.update(
            {
                "status": "error",
                "last_sync_at": productivity_snapshot_status(day, reference_dir=reference_dir).get("last_sync_at"),
                "next_sync_at": error_payload["next_sync_at"],
                "source": "api_snapshot",
            }
        )
        _audit_sync(
            db,
            snapshot_date=day,
            status_text="error",
            sources=source_entries,
            error_type=type(exc).__name__,
            user_id=user_id,
        )
        if isinstance(exc, WorkflowDataError):
            raise ProductivitySyncError(str(exc)) from exc
        raise ProductivitySyncError("Extern datakälla kunde inte synkas.") from exc
    finally:
        for temp_path in temp_paths:
            temp_path.unlink(missing_ok=True)
        shutil.rmtree(staging_dir, ignore_errors=True)
        _SYNC_LOCK.release()


def sync_productivity_snapshot_history(
    end_date: date | None = None,
    *,
    days_back: int = PRODUCTIVITY_BOOTSTRAP_DAYS_BACK,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    db: Session | None = None,
    user_id: int | None = None,
    warm_cache: bool = True,
) -> dict[str, Any]:
    dates = productivity_bootstrap_dates(end_date, days_back=days_back)
    if not dates:
        return {"status": "ok", "source": "api_snapshot_history", "dates": [], "results": [], "errors": []}
    start_date = dates[0]
    final_date = dates[-1]
    if not sources_available(tuple(productivity_api_source_map().values())):
        status_payload = {
            "status": "not_configured",
            "source": "api_snapshot_history",
            "dates": [item.isoformat() for item in dates],
            "results": [],
            "errors": [],
            "last_sync_at": None,
            "next_sync_at": next_productivity_sync_at().isoformat(timespec="seconds"),
        }
        SNAPSHOT_STATUS.update(
            {
                "status": "not_configured",
                "source": "api_snapshot",
                "last_sync_at": None,
                "next_sync_at": status_payload["next_sync_at"],
            }
        )
        return status_payload
    if not _SYNC_LOCK.acquire(blocking=False):
        return {
            "status": "running",
            "source": "api_snapshot_history",
            "dates": [item.isoformat() for item in dates],
            "results": [],
            "errors": [],
            "next_sync_at": next_productivity_sync_at().isoformat(timespec="seconds"),
        }

    temp_paths: list[Path] = []
    staging_dirs: list[Path] = []
    current_source: dict[str, Any] | None = None
    try:
        source_map = productivity_api_source_map()
        tenant = _productivity_data_source_tenant(db, business_code)
        source_payloads: dict[str, dict[str, Any]] = {}
        for file_key in SNAPSHOT_SOURCE_KEYS:
            source_key = source_map[file_key]
            spec = source_spec(source_key)
            current_source = {"key": file_key, "view": spec.view}
            source_status = "api"
            fallback_reason = None
            try:
                if tenant:
                    temp_path, entry = fetch_source_to_temp(
                        source_key,
                        filters=_source_range_filters(file_key, start_date, final_date),
                        tenant=tenant,
                    )
                else:
                    temp_path, entry = fetch_source_to_temp(
                        source_key,
                        filters=_source_range_filters(file_key, start_date, final_date),
                    )
                temp_paths.append(temp_path)
                view = entry.view
            except WorkflowDataError as exc:
                if file_key != "kpi":
                    raise
                try:
                    temp_path = find_kpi_file(
                        reference_dir,
                        business_code or DEFAULT_BUSINESS_CODE,
                        db=db,
                    )
                except ProductivitySourceError:
                    raise exc
                view = "v_ask_kpi_target"
                source_status = "coredata_fallback"
                fallback_reason = str(exc)

            headers, rows = _read_tsv_rows(temp_path)
            rows_by_date = {snapshot_date: [] for snapshot_date in dates}
            if file_key in EVENT_SOURCE_KEYS:
                for row in rows:
                    row_date = _source_row_date(file_key, row)
                    if row_date in rows_by_date:
                        rows_by_date[row_date].append(row)
            else:
                rows_by_date = {snapshot_date: list(rows) for snapshot_date in dates}
            source_payloads[file_key] = {
                "headers": headers,
                "rows_by_date": rows_by_date,
                "view": view,
                "status": source_status,
                "fallback_reason": fallback_reason,
            }

        synced_at = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
        results: list[dict[str, Any]] = []
        metadata_by_date: dict[date, dict[str, Any]] = {}
        for snapshot_date in dates:
            snapshot_dir = productivity_snapshot_dir(snapshot_date, reference_dir)
            staging_dir = snapshot_dir / f".staging-history-{os.getpid()}-{int(time.time() * 1000)}"
            staging_dirs.append(staging_dir)
            staging_dir.mkdir(parents=True, exist_ok=True)
            source_entries: list[dict[str, Any]] = []
            for file_key in SNAPSHOT_SOURCE_KEYS:
                payload = source_payloads[file_key]
                row_count = _gzip_csv_rows(
                    payload["headers"],
                    payload["rows_by_date"].get(snapshot_date, []),
                    staging_dir / f"{file_key}.csv.gz",
                )
                source_entry = {
                    "key": file_key,
                    "view": payload["view"],
                    "status": payload["status"],
                    "rows": row_count,
                }
                if payload.get("fallback_reason"):
                    source_entry["fallback_reason"] = payload["fallback_reason"]
                source_entries.append(source_entry)
            metadata = {
                "date": snapshot_date.isoformat(),
                "status": "ok",
                "source": "api_snapshot",
                "last_sync_at": synced_at,
                "next_sync_at": next_productivity_sync_at().isoformat(timespec="seconds"),
                "sources": source_entries,
            }
            metadata_by_date[snapshot_date] = metadata

        for snapshot_date in dates:
            metadata = metadata_by_date[snapshot_date]
            staging_dir = next(path for path in staging_dirs if path.parent == productivity_snapshot_dir(snapshot_date, reference_dir))
            for file_key in SNAPSHOT_SOURCE_KEYS:
                (staging_dir / f"{file_key}.csv.gz").replace(
                    productivity_snapshot_source_path(snapshot_date, file_key, reference_dir)
                )
            atomic_write_json(productivity_snapshot_metadata_path(snapshot_date, reference_dir), metadata)
            productivity_snapshot_error_path(snapshot_date, reference_dir).unlink(missing_ok=True)
            _audit_sync(
                db,
                snapshot_date=snapshot_date,
                status_text="ok",
                sources=metadata["sources"],
                user_id=user_id,
            )
            if warm_cache:
                _warm_person_productivity_daily_cache(
                    db,
                    snapshot_date,
                    reference_dir=reference_dir,
                    business_code=business_code,
                    sync=metadata,
                )
            results.append(metadata)

        SNAPSHOT_STATUS.update(metadata_by_date[final_date])
        return {
            "status": "ok",
            "source": "api_snapshot_history",
            "days_back": max(0, int(days_back)),
            "dates": [item.isoformat() for item in dates],
            "results": results,
            "errors": [],
            "last_sync_at": synced_at,
            "next_sync_at": next_productivity_sync_at().isoformat(timespec="seconds"),
        }
    except Exception as exc:
        error_payload = {
            "status": "error",
            "message": "Extern datakälla kunde inte synkas.",
            "error_type": type(exc).__name__,
            "updated_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
            "next_sync_at": next_productivity_sync_at().isoformat(timespec="seconds"),
        }
        if current_source:
            error_payload["failed_source"] = current_source
        for snapshot_date in dates:
            atomic_write_json(
                productivity_snapshot_error_path(snapshot_date, reference_dir),
                {**error_payload, "date": snapshot_date.isoformat()},
            )
        SNAPSHOT_STATUS.update(
            {
                "status": "error",
                "last_sync_at": productivity_snapshot_status(final_date, reference_dir=reference_dir).get("last_sync_at"),
                "next_sync_at": error_payload["next_sync_at"],
                "source": "api_snapshot",
            }
        )
        if isinstance(exc, WorkflowDataError):
            raise ProductivitySyncError(str(exc)) from exc
        raise ProductivitySyncError("Extern datakälla kunde inte synkas.") from exc
    finally:
        for temp_path in temp_paths:
            temp_path.unlink(missing_ok=True)
        for staging_dir in staging_dirs:
            shutil.rmtree(staging_dir, ignore_errors=True)
        _SYNC_LOCK.release()


def ensure_productivity_snapshot(
    snapshot_date: date | None = None,
    *,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    db: Session | None = None,
    user_id: int | None = None,
    wait_seconds: float = 0,
    warm_cache: bool = True,
) -> dict[str, Any]:
    day = snapshot_date or datetime.now(LOCAL_TZ).date()
    if productivity_snapshot_is_stale(day, reference_dir=reference_dir):
        deadline = time.monotonic() + max(0.0, wait_seconds)
        while True:
            status = sync_productivity_snapshot(
                day,
                reference_dir=reference_dir,
                business_code=business_code,
                db=db,
                user_id=user_id,
                warm_cache=warm_cache,
            )
            if str(status.get("status") or "") != "running":
                return status
            ready_status = productivity_snapshot_status(day, reference_dir=reference_dir)
            if ready_status.get("ready"):
                return ready_status
            if time.monotonic() >= deadline:
                raise ProductivitySyncError("Produktivitetens API-snapshot synkas fortfarande. Försök igen om en liten stund.")
            time.sleep(0.5)
    return productivity_snapshot_status(day, reference_dir=reference_dir)


def ensure_productivity_snapshot_history(
    end_date: date | None = None,
    *,
    days_back: int = PRODUCTIVITY_BOOTSTRAP_DAYS_BACK,
    reference_dir: Path | str | None = None,
    business_code: str | None = None,
    db: Session | None = None,
    user_id: int | None = None,
    warm_cache: bool = True,
) -> dict[str, Any]:
    dates = productivity_bootstrap_dates(end_date, days_back=days_back)
    needs_sync = any(productivity_snapshot_is_stale(snapshot_date, reference_dir=reference_dir) for snapshot_date in dates)
    if needs_sync:
        return sync_productivity_snapshot_history(
            end_date,
            days_back=days_back,
            reference_dir=reference_dir,
            business_code=business_code,
            db=db,
            user_id=user_id,
            warm_cache=warm_cache,
        )
    results = [productivity_snapshot_status(snapshot_date, reference_dir=reference_dir) for snapshot_date in dates]
    return {
        "status": "ok",
        "source": "api_snapshot_history",
        "days_back": max(0, int(days_back)),
        "dates": [item.isoformat() for item in dates],
        "results": results,
        "errors": [],
    }


def _bootstrap_productivity_snapshot_history() -> None:
    db = SessionLocal()
    try:
        end_date = datetime.now(LOCAL_TZ).date() - timedelta(days=1)
        ensure_productivity_snapshot_history(
            end_date,
            business_code=DEFAULT_BUSINESS_CODE,
            db=db,
        )
    finally:
        db.close()


def _scheduler_loop() -> None:
    try:
        _bootstrap_productivity_snapshot_history()
    except Exception:
        logger.warning("Productivity API snapshot history bootstrap failed.", exc_info=True)
    while True:
        try:
            now = datetime.now(LOCAL_TZ)
            SNAPSHOT_STATUS["next_sync_at"] = next_productivity_sync_at(now).isoformat(timespec="seconds")
            if productivity_snapshot_is_stale(now.date(), now=now):
                db = SessionLocal()
                try:
                    ensure_productivity_snapshot(
                        now.date(),
                        business_code=DEFAULT_BUSINESS_CODE,
                        db=db,
                        warm_cache=False,
                    )
                finally:
                    db.close()
            backfill_state = productivity_backfill_status()
            if backfill_state.get("last_run_date") != now.date().isoformat():
                db = SessionLocal()
                try:
                    ensure_productivity_historical_backfill(
                        now=now,
                        business_code=DEFAULT_BUSINESS_CODE,
                        db=db,
                    )
                finally:
                    db.close()
            prebuild_state = productivity_prebuild_status()
            if prebuild_state.get("last_run_date") != now.date().isoformat():
                db = SessionLocal()
                try:
                    prebuild_ready_productivity_days(
                        now=now,
                        business_code=DEFAULT_BUSINESS_CODE,
                        db=db,
                    )
                finally:
                    db.close()
            next_run = next_productivity_sync_at(datetime.now(LOCAL_TZ))
            SNAPSHOT_STATUS["next_sync_at"] = next_run.isoformat(timespec="seconds")
            sleep_seconds = max(1.0, (next_run - datetime.now(LOCAL_TZ)).total_seconds())
            time.sleep(sleep_seconds)
        except Exception:
            logger.warning("Productivity API snapshot scheduler failed.", exc_info=True)
            time.sleep(60)


def start_productivity_sync_scheduler() -> None:
    global _SCHEDULER_STARTED
    if _SCHEDULER_STARTED:
        return
    _SCHEDULER_STARTED = True
    threading.Thread(
        target=_scheduler_loop,
        name="ProductivityApiSnapshotSync",
        daemon=True,
    ).start()

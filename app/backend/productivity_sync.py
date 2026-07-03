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

from .productivity_sync_paths import (  # noqa: F401
    SNAPSHOT_STATUS,
    LOCAL_TZ,
    PRODUCTIVITY_BOOTSTRAP_DAYS_BACK,
    PRODUCTIVITY_HISTORY_BACKFILL_DAYS_PER_RUN,
    SNAPSHOT_SOURCE_KEYS,
    EVENT_SOURCE_KEYS,
    ProductivitySyncError,
    productivity_snapshot_root,
    productivity_snapshot_dir,
    productivity_snapshot_metadata_path,
    productivity_snapshot_error_path,
    productivity_backfill_state_path,
    productivity_prebuild_state_path,
    productivity_snapshot_source_path,
    atomic_write_json,
    _gzip_csv_copy,
    _read_tsv_rows,
    _gzip_csv_rows,
    _row_text,
    _parse_row_timestamp,
    _source_row_date,
    next_productivity_sync_at,
    previous_productivity_sync_boundary,
    _date_filters,
    _date_range_filters,
    _source_filters,
    _source_range_filters,
    _read_json,
    _parse_date,
    _history_start_date,
    _snapshot_dates,
    productivity_backfill_status,
    productivity_prebuild_status,
    productivity_snapshot_status,
    productivity_overview_report_path,
    overview_report_cache_is_current,
    read_overview_report_cache,
    write_overview_report_cache,
)


logger = logging.getLogger(__name__)
_SYNC_LOCK = threading.Lock()
_SCHEDULER_STARTED = False


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
        from .productivity_cache_warm import ensure_person_and_overview_caches

        return ensure_person_and_overview_caches(
            db,
            productivity_snapshot_files(snapshot_date, reference_dir=reference_dir),
            report_date=snapshot_date,
            business_id=_productivity_cache_business_id(db, business_code),
            sync=sync,
            reference_dir=reference_dir,
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
        cache_result = None
        if warm_cache:
            cache_result = _warm_person_productivity_daily_cache(
                db,
                day,
                reference_dir=reference_dir,
                business_code=business_code,
                sync=metadata,
            )
        _audit_sync(db, snapshot_date=day, status_text="ok", sources=source_entries, user_id=user_id)
        result = dict(metadata)
        if cache_result is not None:
            result["person_cache"] = cache_result
        return result
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
    skip_ready: bool = False,
) -> dict[str, Any]:
    requested_dates = productivity_bootstrap_dates(end_date, days_back=days_back)
    if not requested_dates:
        return {"status": "ok", "source": "api_snapshot_history", "dates": [], "results": [], "errors": []}
    dates = requested_dates
    skipped_dates: list[date] = []
    skipped_results: list[dict[str, Any]] = []
    if skip_ready:
        stale_dates: list[date] = []
        for snapshot_date in requested_dates:
            if productivity_snapshot_is_stale(snapshot_date, reference_dir=reference_dir):
                stale_dates.append(snapshot_date)
            else:
                skipped_dates.append(snapshot_date)
        dates = stale_dates
        if warm_cache and db is not None:
            for snapshot_date in skipped_dates:
                sync = productivity_snapshot_status(snapshot_date, reference_dir=reference_dir)
                result = _warm_person_productivity_daily_cache(
                    db,
                    snapshot_date,
                    reference_dir=reference_dir,
                    business_code=business_code,
                    sync=sync,
                )
                if result is not None:
                    skipped_results.append({"date": snapshot_date.isoformat(), "snapshot": "ready", **result})
        if not dates:
            return {
                "status": "ok",
                "source": "api_snapshot_history",
                "days_back": max(0, int(days_back)),
                "dates": [item.isoformat() for item in requested_dates],
                "synced_dates": [],
                "skipped_dates": [item.isoformat() for item in skipped_dates],
                "results": skipped_results,
                "errors": [],
            }
    start_date = dates[0]
    final_date = dates[-1]
    if not sources_available(tuple(productivity_api_source_map().values())):
        status_payload = {
            "status": "not_configured",
            "source": "api_snapshot_history",
            "dates": [item.isoformat() for item in requested_dates],
            "synced_dates": [item.isoformat() for item in dates],
            "skipped_dates": [item.isoformat() for item in skipped_dates],
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
            "dates": [item.isoformat() for item in requested_dates],
            "synced_dates": [item.isoformat() for item in dates],
            "skipped_dates": [item.isoformat() for item in skipped_dates],
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
        results: list[dict[str, Any]] = list(skipped_results)
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
            cache_result = None
            if warm_cache:
                cache_result = _warm_person_productivity_daily_cache(
                    db,
                    snapshot_date,
                    reference_dir=reference_dir,
                    business_code=business_code,
                    sync=metadata,
                )
            result_entry = dict(metadata)
            if cache_result is not None:
                result_entry["person_cache"] = cache_result
            results.append(result_entry)

        SNAPSHOT_STATUS.update(metadata_by_date[final_date])
        return {
            "status": "ok",
            "source": "api_snapshot_history",
            "days_back": max(0, int(days_back)),
            "dates": [item.isoformat() for item in requested_dates],
            "synced_dates": [item.isoformat() for item in dates],
            "skipped_dates": [item.isoformat() for item in skipped_dates],
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
            skip_ready=True,
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

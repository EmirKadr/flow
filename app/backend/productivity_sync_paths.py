"""Sokvagar, atomisk IO, datum- och statushjalpare for produktivitetssynken.

Utdelat ur productivity_sync.py for radtaket i arkitektur-kontraktet.
"""
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

SNAPSHOT_STATUS: dict[str, Any] = {
    "status": "not_started",
    "last_sync_at": None,
    "next_sync_at": None,
    "source": "api_snapshot",
}

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

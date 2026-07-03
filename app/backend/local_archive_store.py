"""Per-tenant local DuckDB cache of the ASK/WMS archive (``dblog_*``) views.

Purpose: when running locally we mirror the archive logs into a DuckDB file per
tenant so Sankey / Produktivitet / Hämta data can read historical rows straight
from disk instead of paying the slow, fragile ``dblog_*`` API path (row-cap window
splitting, occasional 403/500). This module owns the storage layer only; the fill
logic (seed once from dblog, top up daily from the live views) lives in
``archive_cache_sync.py``.

Design notes:
- One ``<tenant>.duckdb`` file. One table per archive view id (e.g.
  ``dblog_pick_log``), columns = union of the archive view's and its live partner's
  catalog columns (the live view is richer), all stored as VARCHAR plus a derived
  ``_row_date DATE`` used for fast, type-safe window queries.
- Reads reuse ``apply_local_filters`` so every operator behaves exactly like the
  API/local-filter path elsewhere.
- ``query_rows`` returns ``None`` (never partial data) whenever the cache is
  disabled, the view is not seeded, or the requested window is not fully covered —
  that ``None`` is the signal for callers to fall back to the existing dblog/API
  path.
"""
from __future__ import annotations

import contextlib
import logging
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .compiled_data_paths import compiled_data_root
from .config import settings
from .data_fetch_service import (
    ARCHIVE_TO_LIVE,
    DATE_COLUMN_PRIORITY,
    LIVE_ARCHIVE_PAIRS,
    _parse_plan_date_bound,
    _preferred_date_column,
    apply_local_filters,
    load_catalog,
)
from .external_data_client import clean_data_source_tenant

logger = logging.getLogger(__name__)

_ROW_DATE_COLUMN = "_row_date"
_SYNC_LOG_TABLE = "_archive_sync_log"
_SNAPSHOT_META_TABLE = "_archive_snapshot_meta"
_COVERAGE_TABLE = "_archive_coverage"
# DuckDB tillåter bara en öppen anslutning per fil i taget (separata connect() till samma
# fil krockar). En lås per DB-fil serialiserar därför ALL anslutning (läs som skriv) så att
# parallella seed-trådar (per vy) kan hämta samtidigt men aldrig öppnar filen dubbelt.
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _path_lock(path: Path) -> threading.RLock:
    key = str(path)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
        return lock


@contextlib.contextmanager
def _connection(path: Path, *, read_only: bool):
    """Öppna en DuckDB-anslutning under filens lås. Yields None om read_only och filen saknas."""
    lock = _path_lock(path)
    lock.acquire()
    con = None
    try:
        con = _connect(path, read_only=read_only)
        yield con
    finally:
        if con is not None:
            con.close()
        lock.release()


def is_enabled() -> bool:
    return bool(getattr(settings, "ARCHIVE_CACHE_ENABLED", False))


def _cache_dir() -> Path:
    configured = str(getattr(settings, "ARCHIVE_CACHE_DIR", "") or "").strip()
    base = Path(configured) if configured else (compiled_data_root() / "archive_cache")
    return base


def _safe_tenant(tenant: str | None) -> str | None:
    try:
        cleaned = clean_data_source_tenant(tenant)
    except ValueError:
        return None
    return cleaned


def db_path(tenant: str | None) -> Path | None:
    cleaned = _safe_tenant(tenant)
    if not cleaned:
        return None
    return _cache_dir() / f"{cleaned}.duckdb"


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def archive_view_ids() -> tuple[str, ...]:
    """Arkivvyer (dblog_*) som har en live-partner och alltså kan seedas/toppas."""
    return tuple(ARCHIVE_TO_LIVE.keys())


def columns_for_view(archive_view_id: str) -> list[str]:
    """Union av arkivvyns och dess live-partners katalogkolumner (live är rikare)."""
    catalog = load_catalog()
    ordered: list[str] = []
    seen: set[str] = set()
    view_ids = [archive_view_id]
    partner = ARCHIVE_TO_LIVE.get(archive_view_id)
    if partner:
        view_ids.append(partner[1])
    for view_id in view_ids:
        try:
            view = catalog.view(view_id)
        except Exception:
            continue
        for column in view.columns:
            if column.id not in seen:
                seen.add(column.id)
                ordered.append(column.id)
    return ordered


def columns_for_snapshot_view(view_id: str) -> list[str]:
    """Catalog columns for a full-replace, date-less snapshot view."""
    try:
        view = load_catalog().view(view_id)
    except Exception:
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for column in view.columns:
        if column.id not in seen:
            seen.add(column.id)
            ordered.append(column.id)
    return ordered


def _date_column_candidates(archive_view_id: str) -> list[str]:
    """Kolumn-id att prova (i ordning) för att härleda en rads datum."""
    candidates: list[str] = []
    catalog = load_catalog()
    for view_id in (archive_view_id, (ARCHIVE_TO_LIVE.get(archive_view_id) or (0, ""))[1]):
        if not view_id:
            continue
        try:
            column = _preferred_date_column(catalog.view(view_id))
        except Exception:
            column = None
        if column and column.id not in candidates:
            candidates.append(column.id)
    for column_id in DATE_COLUMN_PRIORITY:
        if column_id not in candidates:
            candidates.append(column_id)
    return candidates


def _row_value(row: dict[str, Any], column_id: str) -> Any:
    if column_id in row:
        return row.get(column_id)
    lower = {str(key).lower(): key for key in row}
    actual = lower.get(column_id.lower())
    return row.get(actual) if actual is not None else None


def _row_date(row: dict[str, Any], date_candidates: list[str]) -> date | None:
    for column_id in date_candidates:
        parsed = _parse_plan_date_bound(_row_value(row, column_id))
        if parsed is not None:
            return parsed
    return None


def _connect(path: Path, *, read_only: bool):
    import duckdb  # lazy: bara ett lokalt dev-beroende

    if read_only and not path.exists():
        return None
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def _table_exists(con, view_id: str) -> bool:
    result = con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
        [view_id],
    ).fetchone()
    return result is not None


def _existing_columns(con, view_id: str) -> set[str]:
    rows = con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
        [view_id],
    ).fetchall()
    return {str(row[0]) for row in rows}


def _ensure_table(
    con,
    view_id: str,
    extra_keys: list[str] | None = None,
    *,
    include_row_date: bool = True,
    base_columns: list[str] | None = None,
) -> list[str]:
    columns = list(base_columns) if base_columns is not None else columns_for_view(view_id)
    for key in extra_keys or []:
        if key not in columns:
            columns.append(key)
    if not _table_exists(con, view_id):
        cols_sql = ", ".join(f"{_quote_ident(col)} VARCHAR" for col in columns)
        if include_row_date:
            con.execute(
                f"CREATE TABLE {_quote_ident(view_id)} ({cols_sql}, {_ROW_DATE_COLUMN} DATE)"
            )
            con.execute(
                f"CREATE INDEX {_quote_ident(view_id + '__row_date')} "
                f"ON {_quote_ident(view_id)} ({_ROW_DATE_COLUMN})"
            )
        else:
            con.execute(f"CREATE TABLE {_quote_ident(view_id)} ({cols_sql})")
        return columns
    existing = _existing_columns(con, view_id)
    for col in columns:
        if col not in existing:
            con.execute(
                f"ALTER TABLE {_quote_ident(view_id)} ADD COLUMN {_quote_ident(col)} VARCHAR"
            )
    return columns


def _bulk_insert(con, view_id: str, columns: list[str], batch: list[list[Any]]) -> None:
    """Snabb bulk-insert via en registrerad DataFrame (row-by-row är oanvändbart här)."""
    import pandas as pd

    frame_columns = list(columns)
    frame = pd.DataFrame(batch, columns=frame_columns)
    target_cols = ", ".join(_quote_ident(col) for col in frame_columns)
    con.register("_archive_incoming", frame)
    try:
        con.execute(
            f"INSERT INTO {_quote_ident(view_id)} ({target_cols}) "
            f"SELECT {target_cols} FROM _archive_incoming"
        )
    finally:
        con.unregister("_archive_incoming")


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def append_day(tenant: str | None, archive_view_id: str, day: date, rows: list[dict[str, Any]]) -> int:
    """Idempotent: ersätt allt lagrat för ``day`` med ``rows``.

    Rader utan härledbart datum hoppas över. Att köra om samma dag skriver aldrig
    dubletter eftersom dagen först raderas.
    """
    if archive_view_id not in ARCHIVE_TO_LIVE:
        raise ValueError(f"{archive_view_id} är inte en känd arkivvy.")
    path = db_path(tenant)
    if path is None:
        return 0
    date_candidates = _date_column_candidates(archive_view_id)
    extra_keys = sorted({str(key) for row in rows for key in row.keys()})
    with _connection(path, read_only=False) as con:
        columns = _ensure_table(con, archive_view_id, extra_keys=extra_keys)
        con.execute(
            f"DELETE FROM {_quote_ident(archive_view_id)} WHERE {_ROW_DATE_COLUMN} = ?",
            [day],
        )
        batch: list[list[Any]] = []
        for row in rows:
            # Bara rader som faktiskt hör till dagen lagras under dagen.
            if _row_date(row, date_candidates) != day:
                continue
            batch.append([_to_text(_row_value(row, col)) for col in columns] + [day])
        if batch:
            _bulk_insert(con, archive_view_id, columns + [_ROW_DATE_COLUMN], batch)
        return len(batch)


def append_rows_by_date(tenant: str | None, archive_view_id: str, rows: list[dict[str, Any]]) -> dict[date, int]:
    """Gruppera rader på härlett datum och skriv alla berörda dagar i EN anslutning.

    Idempotent: de berörda dagarna raderas först, sedan bulk-insertas allt på en gång.
    Att öppna DuckDB en gång per chunk (istället för en gång per dag) är avgörande för
    seed-farten – anslutningsoverhead × hundratals dagar blir annars dominerande.
    """
    if archive_view_id not in ARCHIVE_TO_LIVE:
        raise ValueError(f"{archive_view_id} är inte en känd arkivvy.")
    path = db_path(tenant)
    if path is None:
        return {}
    date_candidates = _date_column_candidates(archive_view_id)
    grouped: dict[date, list[dict[str, Any]]] = {}
    for row in rows:
        row_date = _row_date(row, date_candidates)
        if row_date is None:
            continue
        grouped.setdefault(row_date, []).append(row)
    if not grouped:
        return {}
    extra_keys = sorted({str(key) for row in rows for key in row.keys()})
    day_list = list(grouped.keys())
    with _connection(path, read_only=False) as con:
        columns = _ensure_table(con, archive_view_id, extra_keys=extra_keys)
        placeholders = ", ".join(["?"] * len(day_list))
        con.execute(
            f"DELETE FROM {_quote_ident(archive_view_id)} WHERE {_ROW_DATE_COLUMN} IN ({placeholders})",
            day_list,
        )
        batch: list[list[Any]] = []
        written: dict[date, int] = {}
        for day, day_rows in grouped.items():
            for row in day_rows:
                batch.append([_to_text(_row_value(row, col)) for col in columns] + [day])
            written[day] = len(day_rows)
        if batch:
            _bulk_insert(con, archive_view_id, columns + [_ROW_DATE_COLUMN], batch)
    return written


def _ensure_snapshot_meta(con) -> None:
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {_quote_ident(_SNAPSHOT_META_TABLE)} ("
        "view VARCHAR PRIMARY KEY, refreshed_at TIMESTAMP, rows BIGINT)"
    )


def replace_snapshot_rows(tenant: str | None, view_id: str, rows: list[dict[str, Any]]) -> int:
    """Full-replace a date-less support view snapshot."""
    if not is_enabled():
        return 0
    path = db_path(tenant)
    if path is None:
        return 0
    extra_keys = sorted({str(key) for row in rows for key in row.keys()})
    base_columns = columns_for_snapshot_view(view_id)
    with _connection(path, read_only=False) as con:
        columns = _ensure_table(
            con,
            view_id,
            extra_keys=extra_keys,
            include_row_date=False,
            base_columns=base_columns,
        )
        con.execute(f"DELETE FROM {_quote_ident(view_id)}")
        batch = [[_to_text(_row_value(row, col)) for col in columns] for row in rows]
        if batch:
            _bulk_insert(con, view_id, columns, batch)
        _ensure_snapshot_meta(con)
        con.execute(
            f"INSERT OR REPLACE INTO {_quote_ident(_SNAPSHOT_META_TABLE)} VALUES (?, ?, ?)",
            [view_id, datetime.now(), len(batch)],
        )
        return len(batch)


def snapshot_status(tenant: str | None, view_id: str) -> dict[str, Any]:
    path = db_path(tenant)
    if path is None:
        return {"view": view_id, "ready": False, "rows": 0, "refreshed_at": None}
    with _connection(path, read_only=True) as con:
        if con is None or not _table_exists(con, view_id):
            return {"view": view_id, "ready": False, "rows": 0, "refreshed_at": None}
        row_count = con.execute(f"SELECT count(*) FROM {_quote_ident(view_id)}").fetchone()
        meta = None
        if _table_exists(con, _SNAPSHOT_META_TABLE):
            meta = con.execute(
                f"SELECT refreshed_at, rows FROM {_quote_ident(_SNAPSHOT_META_TABLE)} WHERE view = ?",
                [view_id],
            ).fetchone()
        return {
            "view": view_id,
            "ready": True,
            "rows": int((meta[1] if meta else (row_count[0] if row_count else 0)) or 0),
            "refreshed_at": meta[0] if meta else None,
        }


def _actual_ingested_range(con, archive_view_id: str) -> tuple[date | None, date | None]:
    if con is None or not _table_exists(con, archive_view_id):
        return None, None
    row = con.execute(
        f"SELECT min({_ROW_DATE_COLUMN}), max({_ROW_DATE_COLUMN}) "
        f"FROM {_quote_ident(archive_view_id)}"
    ).fetchone()
    if not row:
        return None, None
    return row[0], row[1]


def ingested_range(tenant: str | None, archive_view_id: str) -> tuple[date | None, date | None]:
    path = db_path(tenant)
    if path is None:
        return None, None
    with _connection(path, read_only=True) as con:
        return _actual_ingested_range(con, archive_view_id)


def _ensure_coverage_table(con) -> None:
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {_quote_ident(_COVERAGE_TABLE)} ("
        "view VARCHAR PRIMARY KEY, covered_start DATE, covered_end DATE, "
        "updated_at TIMESTAMP, detail VARCHAR)"
    )


def _coverage_state_range(con, archive_view_id: str) -> tuple[date | None, date | None]:
    if con is None or not _table_exists(con, _COVERAGE_TABLE):
        return None, None
    row = con.execute(
        f"SELECT covered_start, covered_end FROM {_quote_ident(_COVERAGE_TABLE)} WHERE view = ?",
        [archive_view_id],
    ).fetchone()
    if not row:
        return None, None
    return row[0], row[1]


def _merge_ranges(
    ranges: list[tuple[date | None, date | None]]
) -> list[tuple[date, date]]:
    valid = sorted((start, end) for start, end in ranges if start is not None and end is not None)
    merged: list[tuple[date, date]] = []
    for start, end in valid:
        if not merged or start > merged[-1][1] + timedelta(days=1):
            merged.append((start, end))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _covered_intervals_from_connection(con, archive_view_id: str) -> list[tuple[date, date]]:
    return _merge_ranges(
        [
            _coverage_state_range(con, archive_view_id),
            _actual_ingested_range(con, archive_view_id),
        ]
    )


def mark_covered_range(
    tenant: str | None,
    archive_view_id: str,
    start: date,
    end: date,
    *,
    detail: str = "",
) -> None:
    """Markera ett lyckat API-fonster som tackt aven om det saknade rader."""
    if archive_view_id not in ARCHIVE_TO_LIVE:
        raise ValueError(f"{archive_view_id} ar inte en kand arkivvy.")
    if start > end:
        return
    path = db_path(tenant)
    if path is None:
        return
    with _connection(path, read_only=False) as con:
        _ensure_coverage_table(con)
        current_start, current_end = _coverage_state_range(con, archive_view_id)
        covered_start = min(current_start, start) if current_start is not None else start
        covered_end = max(current_end, end) if current_end is not None else end
        con.execute(
            f"INSERT OR REPLACE INTO {_quote_ident(_COVERAGE_TABLE)} VALUES (?, ?, ?, ?, ?)",
            [archive_view_id, covered_start, covered_end, datetime.now(), detail],
        )


def covered_range(tenant: str | None, archive_view_id: str) -> tuple[date | None, date | None]:
    """Datumspannet cachen kan svara for: faktiska rader + tomma men kontrollerade dagar."""
    path = db_path(tenant)
    if path is None:
        return None, None
    with _connection(path, read_only=True) as con:
        intervals = _covered_intervals_from_connection(con, archive_view_id)
        if not intervals:
            return None, None
        return intervals[0][0], intervals[-1][1]


def is_window_covered(tenant: str | None, archive_view_id: str, start: date, end: date) -> bool:
    path = db_path(tenant)
    if path is None or start > end:
        return False
    with _connection(path, read_only=True) as con:
        return any(lo <= start and end <= hi for lo, hi in _covered_intervals_from_connection(con, archive_view_id))


def has_view(tenant: str | None, archive_view_id: str) -> bool:
    start, _end = covered_range(tenant, archive_view_id)
    return start is not None


def _window_from_filters(filters: list[dict[str, Any]] | None) -> tuple[date, date] | None:
    for item in filters or []:
        if str(item.get("operator") or "") != "Between":
            continue
        value = item.get("value")
        if not isinstance(value, list) or len(value) != 2:
            continue
        start = _parse_plan_date_bound(value[0])
        end = _parse_plan_date_bound(value[1])
        if start and end and start <= end:
            return start, end
    return None


def _ensure_sync_log(con) -> None:
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {_quote_ident(_SYNC_LOG_TABLE)} ("
        "ts TIMESTAMP, view VARCHAR, source VARCHAR, "
        "start_date DATE, end_date DATE, rows BIGINT, status VARCHAR, detail VARCHAR)"
    )


def record_sync(
    tenant: str | None,
    view: str,
    source: str,
    *,
    start: date | None,
    end: date | None,
    rows: int,
    status: str = "ok",
    detail: str = "",
) -> None:
    """Persistera en rad i tenantens synk-logg (i samma DuckDB-fil).

    Så kan vi efter en eller flera natters nedtid se exakt vilka dagar/vyer som
    hämtades vid uppstart, och per källa (seed/live/gap_dblog).
    """
    path = db_path(tenant)
    if path is None:
        return
    with _connection(path, read_only=False) as con:
        _ensure_sync_log(con)
        con.execute(
            f"INSERT INTO {_quote_ident(_SYNC_LOG_TABLE)} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [datetime.now(), view, source, start, end, int(rows or 0), status, detail],
        )


def read_sync_log(tenant: str | None, limit: int = 50) -> list[dict[str, Any]]:
    path = db_path(tenant)
    if path is None:
        return []
    with _connection(path, read_only=True) as con:
        if con is None or not _table_exists(con, _SYNC_LOG_TABLE):
            return []
        cursor = con.execute(
            f"SELECT ts, view, source, start_date, end_date, rows, status, detail "
            f"FROM {_quote_ident(_SYNC_LOG_TABLE)} ORDER BY ts DESC LIMIT ?",
            [max(1, int(limit))],
        )
        names = [desc[0] for desc in cursor.description]
        return [dict(zip(names, record)) for record in cursor.fetchall()]


def window_from_filters(filters: list[dict[str, Any]] | None) -> tuple[date, date] | None:
    """Publik: härled ett datumfönster (start, end) ur ett Between-filter, annars None."""
    return _window_from_filters(filters)


def query_rows(
    tenant: str | None,
    archive_view_id: str,
    filters: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Läs cachade rader för en arkivvy, eller ``None`` om cachen inte kan svara.

    ``None`` = fall tillbaka till API/dblog. Vi svarar bara när: cachen är på, vyn
    är seedad, och (om filtren har ett datumfönster) hela fönstret ligger inom det
    tackta intervallet (faktiska rader + kontrollerat tomma dagar). Aldrig partiell data.
    """
    if not is_enabled() or archive_view_id not in ARCHIVE_TO_LIVE:
        return None
    path = db_path(tenant)
    if path is None:
        return None
    with _connection(path, read_only=True) as con:
        window = _window_from_filters(filters)
        table_exists = con is not None and _table_exists(con, archive_view_id)
        if window is not None:
            intervals = _covered_intervals_from_connection(con, archive_view_id)
            if not any(lo <= window[0] and window[1] <= hi for lo, hi in intervals):
                # Fönstret täcks inte helt av cachen -> låt fallback hämta.
                return None
            if not table_exists:
                return apply_local_filters([], filters)
            sql = (
                f"SELECT * FROM {_quote_ident(archive_view_id)} "
                f"WHERE {_ROW_DATE_COLUMN} BETWEEN ? AND ?"
            )
            cursor = con.execute(sql, [window[0], window[1]])
        else:
            if not table_exists:
                return None
            cursor = con.execute(f"SELECT * FROM {_quote_ident(archive_view_id)}")
        column_names = [desc[0] for desc in cursor.description]
        rows = [
            {name: value for name, value in zip(column_names, record) if name != _ROW_DATE_COLUMN}
            for record in cursor.fetchall()
        ]
    # Exakt filtrering (bolag, textoperatorer, precisa datumgränser) via delad logik.
    return apply_local_filters(rows, filters)


def query_snapshot_rows(
    tenant: str | None,
    view_id: str,
    filters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    """Read a full-replace snapshot view, or None when unavailable."""
    if not is_enabled():
        return None
    path = db_path(tenant)
    if path is None:
        return None
    with _connection(path, read_only=True) as con:
        if con is None or not _table_exists(con, view_id):
            return None
        cursor = con.execute(f"SELECT * FROM {_quote_ident(view_id)}")
        column_names = [desc[0] for desc in cursor.description]
        rows = [
            {name: value for name, value in zip(column_names, record)}
            for record in cursor.fetchall()
        ]
    return apply_local_filters(rows, filters)


__all__ = [
    "is_enabled",
    "db_path",
    "archive_view_ids",
    "columns_for_view",
    "columns_for_snapshot_view",
    "append_day",
    "append_rows_by_date",
    "replace_snapshot_rows",
    "snapshot_status",
    "ingested_range",
    "mark_covered_range",
    "covered_range",
    "is_window_covered",
    "has_view",
    "record_sync",
    "read_sync_log",
    "window_from_filters",
    "query_rows",
    "query_snapshot_rows",
]

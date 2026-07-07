"""Server-side trace-rader: tokenlagring, filtrering, räkning och CSV-export."""
from __future__ import annotations

import gzip
import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..config import settings
from ..settings_service import clean_productivity_finance_company_code

logger = logging.getLogger(__name__)


# Spårnings-rader (trace_rows) lazy-laddas: de skickas INTE i huvud-payloaden (för ett
# helår blir de hundratals MB och spränger webbläsarfliken). Istället lagras de här
# server-side under en token; frontend hämtar dem paginerat per nod/länk och exporterar
# via en streamad CSV. TTL alltid på (även lokalt), och få poster hålls samtidigt.
#
# Lagringen är tvåskiktad sedan 2026-07-07:
# - _TRACE_CACHE är processlokal L1 (snabb, samma beteende som förr).
# - Varje token spills även till disk (gzip-JSON under media-roten, som delas
#   av alla workers i podden). En GET som landar i en annan process hittar då
#   raderna på disk i stället för att ge 410 — det var den enda blockeraren
#   för --workers 2 enligt prestanda-sidan i wikin. DB valdes medvetet bort:
#   trace-rader för ett helår är hundratals MB och hör inte hemma i MSSQL.
_TRACE_CACHE_LOCK = threading.Lock()
_TRACE_CACHE_TTL_SECONDS = 30 * 60
_TRACE_CACHE_MAX_ITEMS = 4
_TRACE_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_TRACE_DISK_MAX_ITEMS = 8
_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _trace_disk_dir() -> Path:
    root = (settings.MEDIA_STORE_ROOT or "").strip()
    base = Path(root) if root else Path(tempfile.gettempdir()) / "flow_media_store"
    path = base / "trace_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _disk_prune(now: float) -> None:
    entries = sorted(_trace_disk_dir().glob("*.json.gz"), key=lambda item: item.stat().st_mtime)
    for path in entries:
        if path.stat().st_mtime + _TRACE_CACHE_TTL_SECONDS <= now:
            path.unlink(missing_ok=True)
    entries = [path for path in entries if path.exists()]
    for path in entries[: max(0, len(entries) - _TRACE_DISK_MAX_ITEMS)]:
        path.unlink(missing_ok=True)


def _disk_write(token: str, rows: list[dict[str, Any]], now: float) -> None:
    """Bästa-försök: disk-spill får aldrig fälla huvudflödet (L1 täcker 1 worker)."""
    try:
        path = _trace_disk_dir() / f"{token}.json.gz"
        tmp_path = path.with_suffix(".tmp")
        with gzip.open(tmp_path, "wt", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, default=str)
        os.replace(tmp_path, path)
        _disk_prune(now)
    except Exception:  # noqa: BLE001
        logger.warning("Trace-cache: kunde inte spilla till disk.", exc_info=True)


def _disk_read(token: str, now: float) -> list[dict[str, Any]] | None:
    if not _TOKEN_PATTERN.fullmatch(token):
        return None  # tokens är alltid uuid4-hex; allt annat avvisas (path-säkerhet)
    try:
        path = _trace_disk_dir() / f"{token}.json.gz"
        if not path.is_file():
            return None
        if path.stat().st_mtime + _TRACE_CACHE_TTL_SECONDS <= now:
            path.unlink(missing_ok=True)
            return None
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            rows = json.load(handle)
        return rows if isinstance(rows, list) else None
    except Exception:  # noqa: BLE001
        logger.warning("Trace-cache: kunde inte läsa disk-spill.", exc_info=True)
        return None

# Kolumner + svenska rubriker för trace-CSV (speglar frontendens tidigare klient-CSV).
_TRACE_CSV_BASE_COLUMNS = (
    "company", "received_date", "origin_pall", "current_pall", "current_location", "item",
    "order_number", "pick_zone", "picked_qty", "purchase_number", "purchase_line",
    "source_row_id", "status_label", "qty_remaining", "revenue", "label_revenue",
    "purchase_line_revenue", "outbound_revenue", "label_fraction", "confidence", "path",
)
_TRACE_CSV_LABELS = {
    "company": "Bolag", "received_date": "Mottagningsdatum", "origin_pall": "Ursprungspallid",
    "current_pall": "Nuvarande pallid", "current_location": "Nuvarande plats", "item": "Artikel",
    "order_number": "Ordernummer", "pick_zone": "Zon", "picked_qty": "Plockat",
    "purchase_number": "Inköpsnummer", "purchase_line": "Radnummer", "source_row_id": "Mottagningsrad",
    "status_label": "Status", "qty_remaining": "Kolli kvar", "revenue": "Intäkt",
    "label_revenue": "Etikettintäkt", "purchase_line_revenue": "Inköpsradsintäkt",
    "outbound_revenue": "Outboundintäkt", "label_fraction": "Etikettandel",
    "confidence": "Spårningssäkerhet", "path": "Väg",
}


def _prune_trace_cache(now: float) -> None:
    for token, (expires_at, _rows) in list(_TRACE_CACHE.items()):
        if expires_at <= now:
            _TRACE_CACHE.pop(token, None)
    if len(_TRACE_CACHE) > _TRACE_CACHE_MAX_ITEMS:
        for token, _entry in sorted(_TRACE_CACHE.items(), key=lambda item: item[1][0])[: len(_TRACE_CACHE) - _TRACE_CACHE_MAX_ITEMS]:
            _TRACE_CACHE.pop(token, None)


def store_trace_rows(rows: list[dict[str, Any]]) -> str:
    """Lagra trace_rows server-side och returnera en token att hämta dem med."""
    token = uuid.uuid4().hex
    now = time.time()
    with _TRACE_CACHE_LOCK:
        _TRACE_CACHE[token] = (now + _TRACE_CACHE_TTL_SECONDS, rows)
        _prune_trace_cache(now)
    _disk_write(token, rows, now)
    return token


def get_trace_rows(token: str) -> list[dict[str, Any]] | None:
    """Hämta lagrade trace_rows, eller None om token saknas/gått ut.

    L1 (processminne) först; miss faller tillbaka på disk-spillet så att
    drill-down överlever att requesten landar i en annan worker-process.
    """
    now = time.time()
    cleaned = str(token or "")
    with _TRACE_CACHE_LOCK:
        entry = _TRACE_CACHE.get(cleaned)
        if entry:
            expires_at, rows = entry
            if expires_at <= now:
                _TRACE_CACHE.pop(cleaned, None)
            else:
                return rows
    rows = _disk_read(cleaned, now)
    if rows is None:
        return None
    with _TRACE_CACHE_LOCK:
        _TRACE_CACHE[cleaned] = (now + _TRACE_CACHE_TTL_SECONDS, rows)
        _prune_trace_cache(now)
    return rows


def _trace_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def filter_trace_rows(rows: list[dict[str, Any]], scope: str, id_value: str | None, *, company: str | None = None, start_date: date | str | None = None, end_date: date | str | None = None, only_consumed: bool | None = None) -> list[dict[str, Any]]:
    """Filtrera trace_rows på vald nod (node_ids) eller länk (link_keys)."""
    scope = str(scope or "all").strip().lower()
    company_filter = clean_productivity_finance_company_code(company)
    if company_filter == "ALL":
        company_filter = None
    start = _trace_date(start_date)
    end = _trace_date(end_date)

    def _matches_view(row: dict[str, Any]) -> bool:
        if company_filter and (clean_productivity_finance_company_code(row.get("company")) or "") != company_filter:
            return False
        row_date = _trace_date(row.get("received_date"))
        if start and (row_date is None or row_date < start):
            return False
        if end and (row_date is None or row_date > end):
            return False
        if only_consumed is True and not bool(row.get("consumed")):
            return False
        return True

    filtered = [row for row in rows if _matches_view(row)]
    if scope == "node" and id_value:
        return [row for row in filtered if id_value in (row.get("node_ids") or [])]
    if scope == "link" and id_value:
        return [row for row in filtered if id_value in (row.get("link_keys") or [])]
    return filtered


def compute_trace_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Antal pallgrenar per nod-id och per länk-nyckel (för direkt visning i UI:t)."""
    nodes: dict[str, int] = {}
    links: dict[str, int] = {}
    for row in rows:
        for node_id in row.get("node_ids") or []:
            nodes[node_id] = nodes.get(node_id, 0) + 1
        for link_key in row.get("link_keys") or []:
            links[link_key] = links.get(link_key, 0) + 1
    return {"nodes": nodes, "links": links}


def _csv_cell(value: Any) -> str:
    if value is None:
        text = ""
    elif isinstance(value, (list, tuple)):
        text = " | ".join(str(item) for item in value)
    elif isinstance(value, dict):
        import json as _json

        text = _json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace('"', '""')
    return f'"{text}"' if any(ch in text for ch in ';"\r\n') else text


def trace_rows_to_csv_lines(rows: list[dict[str, Any]]):
    """Generator som streamar CSV (BOM + ';'-separerat) för trace_rows, inkl. dynamiska step_N."""
    max_step = 0
    for row in rows:
        for key in row.keys():
            if key.startswith("step_"):
                suffix = key[5:]
                if suffix.isdigit():
                    max_step = max(max_step, int(suffix))
    columns = [*_TRACE_CSV_BASE_COLUMNS[:-1], *[f"step_{i}" for i in range(1, max_step + 1)], "path"]
    labels = {**_TRACE_CSV_LABELS, **{f"step_{i}": f"Steg {i}" for i in range(1, max_step + 1)}}
    yield "﻿" + ";".join(_csv_cell(labels.get(col, col)) for col in columns) + "\r\n"
    for row in rows:
        yield ";".join(_csv_cell(row.get(col)) for col in columns) + "\r\n"

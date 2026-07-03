"""Server-side trace-rader: tokenlagring, filtrering, räkning och CSV-export."""
from __future__ import annotations

from datetime import date, datetime
import threading
import time
import uuid
from typing import Any

from ..settings_service import clean_productivity_finance_company_code


# Spårnings-rader (trace_rows) lazy-laddas: de skickas INTE i huvud-payloaden (för ett
# helår blir de hundratals MB och spränger webbläsarfliken). Istället lagras de här
# server-side under en token; frontend hämtar dem paginerat per nod/länk och exporterar
# via en streamad CSV. TTL alltid på (även lokalt), och få poster hålls samtidigt.
_TRACE_CACHE_LOCK = threading.Lock()
_TRACE_CACHE_TTL_SECONDS = 30 * 60
_TRACE_CACHE_MAX_ITEMS = 4
_TRACE_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}

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
    return token


def get_trace_rows(token: str) -> list[dict[str, Any]] | None:
    """Hämta lagrade trace_rows, eller None om token saknas/gått ut."""
    now = time.time()
    with _TRACE_CACHE_LOCK:
        entry = _TRACE_CACHE.get(str(token or ""))
        if not entry:
            return None
        expires_at, rows = entry
        if expires_at <= now:
            _TRACE_CACHE.pop(str(token), None)
            return None
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

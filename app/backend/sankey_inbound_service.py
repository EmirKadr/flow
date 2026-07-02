from __future__ import annotations

from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import logging
import threading
import time
import uuid
from typing import Any, Callable

from . import local_archive_store
from .config import settings
from .data_fetch_service import (
    ARCHIVE_TO_LIVE,
    DataFetchConfigError,
    DataFetchPlanError,
    LIVE_ARCHIVE_PAIRS,
    PACKAGE_ALIAS_VIEW,
    PACKAGE_BASE_UNIT_LABEL,
    _date_period_payload,
    _period_values_for_column,
    _preferred_date_column,
    build_package_ladders,
    load_catalog,
    split_quantity_into_packages,
)
from .external_data_client import ExternalDataClient, ExternalDataClientError, data_source_base_url_for_tenant
from .productivity_kpi_rules import (
    SQL_REFERENCE_KPI_RULE_ROWS,
    normalize_process,
    parse_kpi_rule_rows,
    parse_kpi_targets,
)
from .business_scope import DEFAULT_BUSINESS_CODE
from .productivity_service import (
    ProductivitySourceError,
    _number,
    _read_csv,
    _read_csv_rows_with_headers,
    find_kpi_file,
)
from .productivity_sync import productivity_snapshot_source_path, productivity_snapshot_status
from .settings_service import (
    clean_productivity_finance_company_code,
    productivity_finance_default_invoice_rows,
)


logger = logging.getLogger(__name__)


EXCLUDED_RECEIVE_TYPES = {"23", "45", "46", "47", "63", "81", "91", "100"}
ZEROING_RECEIVE_TYPE = "100"
BUFFER_UPDATE_RECEIVE_TYPE = "91"
INBOUND_LABEL_ROW_ID = "inbound_labels"
INBOUND_PURCHASE_LINE_ROW_ID = "inbound_article_rows"
OUTBOUND_STORE_ORDER_PREFIX = "TO"
OUTBOUND_ECOM_ORDER_PREFIX = "PR"
OUTBOUND_METRICS = (
    {"id": "store_picked_orders", "branch": "store", "branch_label": "Butik", "prefix": OUTBOUND_STORE_ORDER_PREFIX, "label": "Plockade orders", "unit": "orders"},
    {"id": "store_picked_rows", "branch": "store", "branch_label": "Butik", "prefix": OUTBOUND_STORE_ORDER_PREFIX, "label": "Plockade rader", "unit": "rader"},
    {"id": "store_picked_pcs", "branch": "store", "branch_label": "Butik", "prefix": OUTBOUND_STORE_ORDER_PREFIX, "label": "Plockade pcs", "unit": "plockenheter"},
    {"id": "store_full_pallets", "branch": "store", "branch_label": "Butik", "prefix": OUTBOUND_STORE_ORDER_PREFIX, "label": "Antal helpallar", "unit": "helpallar"},
    {"id": "store_loaded_pallets", "branch": "store", "branch_label": "Butik", "prefix": OUTBOUND_STORE_ORDER_PREFIX, "label": "Utlastade pallar", "unit": "pallar"},
    {"id": "ecom_picked_orders", "branch": "ecom", "branch_label": "E-handel", "prefix": OUTBOUND_ECOM_ORDER_PREFIX, "label": "Plockade orders", "unit": "orders"},
    {"id": "ecom_picked_rows", "branch": "ecom", "branch_label": "E-handel", "prefix": OUTBOUND_ECOM_ORDER_PREFIX, "label": "Plockade rader", "unit": "rader"},
    {"id": "ecom_picked_pcs", "branch": "ecom", "branch_label": "E-handel", "prefix": OUTBOUND_ECOM_ORDER_PREFIX, "label": "Plockade pcs", "unit": "plockenheter"},
    {"id": "ecom_pallet", "branch": "ecom", "branch_label": "E-handel", "prefix": OUTBOUND_ECOM_ORDER_PREFIX, "label": "Antal helpallar", "unit": "helpallar"},
)

SANKEY_SOURCE_VIEWS = {
    "receive": "v_ask_receive_log",
    "trans": "v_ask_trans_log",
    "pick": "v_ask_pick_log_full",
    "dispatch": "dispatch_pallet_log",
    "buffer": "v_ask_article_buffertpallet",
    "kpi": "v_ask_kpi_target",
    "item_alias": PACKAGE_ALIAS_VIEW,
}

REQUIRED_SOURCE_KEYS = {"receive", "trans", "pick"}
DEGRADABLE_SOURCE_KEYS = {"pick"}
CURRENT_STATE_SOURCE_KEYS = {"buffer", "kpi", "item_alias"}
PRODUCTIVITY_SNAPSHOT_REUSE_SOURCE_KEYS = {"receive", "trans"}
PERIOD_ONLY_SOURCE_KEYS = {"dispatch"}
CLIENT_FILTER_PREBUILD_MAX_SOURCE_ROWS = 75_000
CLIENT_FILTER_PREBUILD_MAX_VIEWS = 512

# Naturliga steg i SSE-progressloggen: en hämtning per källa + ett bygg-steg.
ProgressCallback = Callable[[dict[str, Any]], None]


def _emit_progress(callback: ProgressCallback | None, **event: Any) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except Exception:
        # Progressrapportering får aldrig fälla själva hämtningen.
        pass
SOURCE_LABELS = {
    "receive": "Varumottagningslogg",
    "trans": "Translogg",
    "pick": "Plocklogg Full",
    "dispatch": "Dispatchpallslogg",
    "buffer": "Buffertpall",
    "item_alias": "Item Alias",
    "kpi": "KPI-mål",
}

PROCESS_LABELS = {
    "RECEIVING": "Receiving",
    "DECANTING": "AutoStore / Decanting",
    "HBW": "HBW",
    "MANUAL_BUFFER": "Manual Buffer",
    "PUTAWAY_PICK": "Plockplats",
    "BUFFER_UPDATE": "Buffer Update",
}

PROCESS_DEFAULT_METRIC = {
    "RECEIVING": "rows",
    "DECANTING": "packages",
    "HBW": "pallets",
    "MANUAL_BUFFER": "pallets",
    "PUTAWAY_PICK": "pallets",
    "BUFFER_UPDATE": "pallets",
}

PROCESS_POINT_ALIASES = {
    "AUTOSTORE": "DECANTING",
    "AUTOSTORE / DECANTING": "DECANTING",
    "MANUAL BUFFER": "MANUAL_BUFFER",
    "PUTAWAY PICK": "PUTAWAY_PICK",
    "PICK_LOCATION": "PUTAWAY_PICK",
    "PLOCKPLATS": "PUTAWAY_PICK",
    "BUFFER UPDATE": "BUFFER_UPDATE",
}

OPEN_STATUS_LABELS = {
    "consumed": "Förverkad / plockad",
    "open_autostore": "Kvar i AutoStore",
    "open_hbw": "Kvar i HBW",
    "open_buffer": "Kvar i buffert",
    "open_pick_location": "Kvar på plockplats",
    "open_not_putaway": "Ej inlagrad / okänd",
}


class SankeyInboundError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502, source_status: list[dict] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.source_status = list(source_status or [])


@dataclass
class ProcessVisit:
    key: str
    label: str
    points: float
    source: str


@dataclass
class TraceBranch:
    id: str
    origin_id: str
    company: str
    warehouse: str
    item: str
    current_pall: str
    qty: float
    revenue: float
    label_fraction: float
    label_revenue: float = 0.0
    purchase_line_revenue: float = 0.0
    origin_pall: str = ""
    source_row_id: str = ""
    purchase_number: str = ""
    purchase_line: str = ""
    received_date: date | None = None
    trace_steps: list[str] = field(default_factory=list)
    processes: list[ProcessVisit] = field(default_factory=list)
    status: str = "open_not_putaway"
    location: str = ""
    consumed: bool = False
    active: bool = True
    confidence: str = "high"


@dataclass
class PickQueueEntry:
    branch_id: str | None
    qty: float


_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 15 * 60 if settings.is_production else 0
_CACHE_MAX_ITEMS = 64
_CACHE: dict[tuple[Any, ...], tuple[float, dict]] = {}
SANKEY_INBOUND_PAYLOAD_SCHEMA = "client_filters_v7"

# Källrads-cache (oberoende av only_consumed). only_consumed är bara ett efterfilter
# i bygget – samma rader hämtas oavsett – så vi cachar de dyra hämtningarna separat
# med en kort, alltid påslagen TTL. Det gör att t.ex. "Visa endast förverkade"
# kan togglas utan att hämta om allt, även lokalt där payload-cachen har TTL 0.
_SOURCE_CACHE_LOCK = threading.Lock()
_SOURCE_CACHE_TTL_SECONDS = 120
_SOURCE_CACHE_MAX_ITEMS = 64
_SOURCE_CACHE: dict[tuple[Any, ...], tuple[float, tuple[dict, list, list]]] = {}

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


def sankey_period_bounds(period: str, anchor: date | None = None) -> tuple[date, date, str]:
    selected = anchor or date.today()
    normalized = str(period or "day").strip().lower()
    if normalized == "day":
        return selected, selected, "Dag"
    if normalized == "week":
        start = selected - timedelta(days=selected.weekday())
        return start, start + timedelta(days=6), "Vecka"
    if normalized == "month":
        start = selected.replace(day=1)
        return start, selected.replace(day=monthrange(selected.year, selected.month)[1]), "Månad"
    if normalized == "year":
        return selected.replace(month=1, day=1), selected.replace(month=12, day=31), "År"
    raise ValueError("Okänd period")


def _period_label(period: str) -> str:
    return {
        "day": "Dag",
        "week": "Vecka",
        "month": "Månad",
        "year": "År",
    }.get(str(period or "").strip().lower(), "Period")


def _client_filter_view_key(period: str, period_start: date, company: str | None, only_consumed: bool) -> str:
    company_key = clean_productivity_finance_company_code(company) or "ALL"
    return f"{str(period or 'day').strip().lower()}|{period_start.isoformat()}|{company_key}|{1 if only_consumed else 0}"


def _client_filter_period_specs(period: str, period_start: date, period_end: date) -> list[tuple[str, date, date]]:
    normalized = str(period or "day").strip().lower()
    specs: list[tuple[str, date, date]] = [(normalized, period_start, period_end)]
    if normalized == "year":
        cursor = period_start.replace(day=1)
        while cursor <= period_end:
            month_end = cursor.replace(day=monthrange(cursor.year, cursor.month)[1])
            specs.append(("month", cursor, min(month_end, period_end)))
            if cursor.month == 12:
                cursor = cursor.replace(year=cursor.year + 1, month=1, day=1)
            else:
                cursor = cursor.replace(month=cursor.month + 1, day=1)
    elif normalized in {"week", "month"}:
        cursor = period_start
        while cursor <= period_end:
            specs.append(("day", cursor, cursor))
            cursor += timedelta(days=1)

    unique: list[tuple[str, date, date]] = []
    seen: set[tuple[str, date, date]] = set()
    for item in specs:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _round_money(value: float) -> float:
    return round(float(value or 0.0), 2)


def _round_qty(value: float) -> float:
    return round(float(value or 0.0), 4)


def _normalize_type(value: Any) -> str:
    text = str(value or "").strip()
    try:
        number = float(text.replace(",", "."))
    except ValueError:
        return text.upper()
    return str(int(number)) if number.is_integer() else text.upper()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _row_value(row: dict[str, Any], *names: str) -> Any:
    if not isinstance(row, dict):
        return ""
    for name in names:
        if name in row:
            return row.get(name)
    wanted = {str(name).strip().casefold() for name in names}
    for key, value in row.items():
        if str(key).strip().casefold() in wanted:
            return value
    return ""


def _row_text(row: dict[str, Any], *names: str) -> str:
    return _clean_text(_row_value(row, *names))


def _row_number(row: dict[str, Any], *names: str) -> float:
    return _number(_row_text(row, *names))


def _row_company(row: dict[str, Any]) -> str:
    return clean_productivity_finance_company_code(_row_text(row, "company", "Company", "Bolag", "bolag"))


def _row_warehouse(row: dict[str, Any]) -> str:
    return _row_text(row, "wareh_num", "warehouse", "Lager", "lager").upper()


def _row_item(row: dict[str, Any]) -> str:
    return _row_text(row, "item_num", "Artikel", "Artikelnr", "article", "item").upper()


def _row_pall(row: dict[str, Any]) -> str:
    return _row_text(row, "pall_num", "Pallid", "Pall ID", "Pall Num", "pallid").upper()


def _row_purchase_number(row: dict[str, Any]) -> str:
    return _row_text(
        row,
        "book_num",
        "Book Num",
        "Inköpsnr",
        "Inkopsnr",
        "purchase_num",
        "purchase_number",
        "po_num",
        "po_number",
    ).upper()


def _row_purchase_line(row: dict[str, Any]) -> str:
    return _row_text(
        row,
        "line_num",
        "Line Num",
        "Rad",
        "rad",
        "radnummer",
        "Radnummer",
        "book_line",
        "order_line_num",
        "row_num",
    ).upper()


def _purchase_line_key(row: dict[str, Any]) -> tuple[str, str, str] | None:
    company = _row_company(row)
    purchase = _row_purchase_number(row)
    line = _row_purchase_line(row)
    if not company or not purchase or not line:
        return None
    return company, purchase, line


def _normalize_pall(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text[2:] if text.startswith("AS") and len(text) > 2 else text


def _pall_aliases(value: Any) -> set[str]:
    text = str(value or "").strip().upper()
    aliases = {text, _normalize_pall(text)}
    if text and not text.startswith("AS"):
        aliases.add(f"AS{text}")
    aliases.discard("")
    return aliases


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = str(value).strip()
    if not text:
        return None
    digits = text.replace("-", "").replace(":", "").replace(" ", "").replace("T", "")[:14]
    if len(digits) >= 8 and digits[:8].isdigit():
        try:
            if len(digits) >= 14 and digits[:14].isdigit():
                return datetime.strptime(digits[:14], "%Y%m%d%H%M%S")
            return datetime.strptime(digits[:8], "%Y%m%d")
        except ValueError:
            pass
    normalized = text.replace("Z", "+00:00")
    for candidate in (normalized, normalized.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            continue
    return None


def _row_datetime(row: dict[str, Any]) -> datetime | None:
    return (
        _parse_datetime(_row_value(row, "timestamp", "Timestamp", "Andrad", "Ändrad"))
        or _parse_datetime(_row_value(row, "date_time", "Datum/tid", "Datum"))
        or _parse_datetime(_row_value(row, "time_stamp_int"))
        or _parse_datetime(_row_value(row, "date_outgo"))
    )


def _row_id(row: dict[str, Any], fallback_index: int) -> str:
    value = _row_text(row, "rowid", "Rowid", "Radid", "id")
    if value:
        return value
    parts = [
        _row_company(row),
        _row_pall(row),
        _row_item(row),
        str(_row_datetime(row) or ""),
        str(fallback_index),
    ]
    return "|".join(parts)


def _is_in_date_window(row: dict[str, Any], start: date, end: date) -> bool:
    stamp = _row_datetime(row)
    if stamp is None:
        return False
    return start <= stamp.date() <= end


def _company_allowed(company: str, allowed: set[str]) -> bool:
    return not allowed or company in allowed


def _invoice_row_prices(
    finance_settings: dict,
    company_codes: list[str],
    row_id: str,
    *,
    warning_code: str,
    description: str,
) -> tuple[dict[str, float], list[dict]]:
    warnings: list[dict] = []
    rows_by_company = finance_settings.get("invoice_rows_by_company") if isinstance(finance_settings, dict) else {}
    rows_by_company = rows_by_company if isinstance(rows_by_company, dict) else {}
    prices: dict[str, float] = {}
    for code in company_codes:
        company = clean_productivity_finance_company_code(code)
        if not company:
            continue
        rows = rows_by_company.get(company)
        if rows is None:
            rows = productivity_finance_default_invoice_rows(company)
        row = next((item for item in rows or [] if str(item.get("id") or "") == row_id), None)
        price = float(row.get("price") or 0.0) if isinstance(row, dict) else 0.0
        prices[company] = price
        if price <= 0:
            warnings.append(
                {
                    "code": warning_code,
                    "company": company,
                    "message": f"{company} saknar pris för {description} ({row_id}).",
                }
            )
    return prices, warnings


def _inbound_prices(finance_settings: dict, company_codes: list[str]) -> tuple[dict[str, float], dict[str, float], list[dict]]:
    label_prices, label_warnings = _invoice_row_prices(
        finance_settings,
        company_codes,
        INBOUND_LABEL_ROW_ID,
        warning_code="missing_inbound_label_price",
        description="mottagna etiketter",
    )
    purchase_line_prices, purchase_line_warnings = _invoice_row_prices(
        finance_settings,
        company_codes,
        INBOUND_PURCHASE_LINE_ROW_ID,
        warning_code="missing_inbound_purchase_line_price",
        description="mottagna inköpsrader",
    )
    return label_prices, purchase_line_prices, [*label_warnings, *purchase_line_warnings]


def _outbound_prices(finance_settings: dict, company_codes: list[str]) -> tuple[dict[str, dict[str, float]], list[dict]]:
    prices: dict[str, dict[str, float]] = {}
    for metric in OUTBOUND_METRICS:
        row_id = str(metric["id"])
        metric_prices, _metric_warnings = _invoice_row_prices(
            finance_settings,
            company_codes,
            row_id,
            warning_code="missing_outbound_price",
            description=f"{metric['branch_label']} {metric['label']}".lower(),
        )
        prices[row_id] = metric_prices
    return prices, []


def _row_order_number(row: dict[str, Any]) -> str:
    return _row_text(row, "order_num", "Ordernr", "Order nr", "ordernr").upper()


def _row_pick_zone(row: dict[str, Any]) -> str:
    return _row_text(row, "pick_zone", "Zon", "zone").upper()


def _row_picked_qty(row: dict[str, Any]) -> float:
    return _row_number(row, "qty_suf", "Plockat", "picked_qty", "qty")


def _row_parent_pick_pall(row: dict[str, Any]) -> str:
    return _row_text(row, "parent_pick_pall_num", "Pappapallsnr", "Pappapallsnr.")


def _row_pick_pall(row: dict[str, Any]) -> str:
    return _row_text(row, "pick_pall_num", "Plockpallsnr", "Plockpallsnr.", "Pallid", "pall_num").upper()


def _order_starts_with(row: dict[str, Any], prefix: str) -> bool:
    return bool(prefix) and _row_order_number(row).startswith(str(prefix).upper())


def _outbound_trace_row(
    row: dict[str, Any],
    *,
    metric: dict[str, str],
    company: str,
    amount: float,
    revenue: float,
    node_ids: list[str],
    link_keys: list[str],
) -> dict[str, Any]:
    stamp = _row_datetime(row)
    order_number = _row_order_number(row)
    current_pall = _normalize_pall(_row_pick_pall(row) or _row_pall(row))
    current_location = _row_text(row, "location", "Lokation", "Plats").upper()
    source_row_id = _row_text(row, "rowid", "Rowid", "Radid", "id") or order_number or current_pall
    path_steps = ["Outbound", str(metric["branch_label"]), str(metric["label"])]
    trace: dict[str, Any] = {
        "branch_id": f"outbound:{metric['id']}:{source_row_id}",
        "origin_id": source_row_id,
        "trace_type": "outbound",
        "company": company,
        "warehouse": _row_warehouse(row),
        "item": _row_item(row),
        "origin_pall": current_pall,
        "current_pall": current_pall,
        "current_location": current_location,
        "purchase_number": "",
        "purchase_line": "",
        "order_number": order_number,
        "pick_zone": _row_pick_zone(row),
        "picked_qty": _round_qty(_row_picked_qty(row)),
        "received_date": stamp.date().isoformat() if stamp else "",
        "source_row_id": source_row_id,
        "qty_remaining": _round_qty(amount),
        "revenue": _round_money(revenue),
        "label_revenue": 0.0,
        "purchase_line_revenue": 0.0,
        "outbound_revenue": _round_money(revenue),
        "label_fraction": _round_qty(amount),
        "status": f"outbound:{metric['id']}",
        "status_label": f"{metric['branch_label']} - {metric['label']}",
        "consumed": True,
        "confidence": "high",
        "path": " -> ".join(path_steps),
        "node_ids": list(node_ids),
        "link_keys": list(link_keys),
    }
    for index, step in enumerate(path_steps, start=1):
        trace[f"step_{index}"] = step
    return trace


def _build_outbound_sankey(
    *,
    pick_rows: list[dict[str, Any]],
    dispatch_rows: list[dict[str, Any]],
    alias_rows: list[dict[str, Any]],
    prices: dict[str, dict[str, float]],
    allowed_companies: set[str],
    view_company_filter: str,
    view_period_start: date,
    view_period_end: date,
    include_trace_details: bool = True,
) -> dict[str, Any]:
    target_companies = (
        {view_company_filter}
        if view_company_filter != "ALL"
        else {company for company in allowed_companies if company}
    )
    if not target_companies:
        row_companies = {_row_company(row) for row in pick_rows + dispatch_rows if _row_company(row)}
        target_companies = row_companies

    nodes: dict[str, dict] = {}
    links: dict[tuple[str, str, str], dict] = {}
    trace_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    summary: dict[str, float] = {
        "outbound_income": 0.0,
        "outbound_store_income": 0.0,
        "outbound_ecom_income": 0.0,
        "outbound_picked_orders": 0.0,
        "outbound_picked_rows": 0.0,
        "outbound_picked_pcs": 0.0,
        "outbound_full_pallets": 0.0,
        "outbound_loaded_pallets": 0.0,
    }
    company_summaries: dict[str, dict[str, Any]] = {}
    package_ladders = build_package_ladders(alias_rows)
    default_package_ladder = [(PACKAGE_BASE_UNIT_LABEL, 1)]

    def _row_in_view(row: dict[str, Any], company: str) -> bool:
        return (
            _row_company(row) == company
            and _is_in_date_window(row, view_period_start, view_period_end)
        )

    pick_rows_by_company: dict[str, list[dict[str, Any]]] = {company: [] for company in target_companies}
    dispatch_rows_by_company: dict[str, list[dict[str, Any]]] = {company: [] for company in target_companies}
    for row in pick_rows:
        company = _row_company(row)
        if company in target_companies and _is_in_date_window(row, view_period_start, view_period_end):
            pick_rows_by_company.setdefault(company, []).append(row)
    for row in dispatch_rows:
        company = _row_company(row)
        if company in target_companies and _is_in_date_window(row, view_period_start, view_period_end):
            dispatch_rows_by_company.setdefault(company, []).append(row)

    def _metric_rows_for_company(metric: dict[str, str], company: str) -> list[dict[str, Any]]:
        row_id = str(metric["id"])
        prefix = str(metric.get("prefix") or "")
        company_pick_rows = pick_rows_by_company.get(company, [])
        if row_id.endswith("_picked_orders"):
            by_order: dict[str, dict[str, Any]] = {}
            for row in company_pick_rows:
                order = _row_order_number(row)
                if order.startswith(prefix) and _row_picked_qty(row) >= 1 and order not in by_order:
                    by_order[order] = row
            return list(by_order.values())
        if row_id.endswith("_picked_rows") or row_id.endswith("_picked_pcs"):
            return [
                row
                for row in company_pick_rows
                if _order_starts_with(row, prefix)
                and _row_pick_zone(row) != "H"
                and _row_picked_qty(row) >= 1
            ]
        if row_id in {"store_full_pallets", "ecom_pallet"}:
            return [
                row
                for row in company_pick_rows
                if _order_starts_with(row, prefix)
                and _row_pick_zone(row) == "H"
                and _row_picked_qty(row) >= 1
            ]
        if row_id == "store_loaded_pallets":
            return [
                row
                for row in dispatch_rows_by_company.get(company, [])
                if not _row_parent_pick_pall(row)
            ]
        return []

    def _package_count_for_pick_row(row: dict[str, Any]) -> float:
        item = _row_text(row, "item_num", "Artikel", "Artikelnr", "article", "item").strip()
        raw_company = _row_text(row, "company", "Company", "Bolag", "bolag").strip()
        company = _row_company(row)
        ladder = (
            package_ladders.get((item, raw_company))
            or package_ladders.get((item, company))
            or package_ladders.get((item.upper(), company))
            or package_ladders.get((item, ""))
            or package_ladders.get((item.upper(), ""))
            or default_package_ladder
        )
        packages = split_quantity_into_packages(_row_picked_qty(row), ladder)
        return float(sum(packages.values()))

    def _metric_trace_amounts(row_id: str, rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], float]]:
        if row_id.endswith("_picked_pcs"):
            return [(row, amount) for row in rows if (amount := _package_count_for_pick_row(row)) > 0]
        return [(row, 1.0) for row in rows]

    for company in sorted(target_companies):
        if not company:
            continue
        for metric in OUTBOUND_METRICS:
            row_id = str(metric["id"])
            rows = _metric_rows_for_company(metric, company)
            trace_amounts = _metric_trace_amounts(row_id, rows)
            count = float(sum(amount for _row, amount in trace_amounts)) if row_id.endswith("_picked_pcs") else float(len(rows))
            price = float((prices.get(row_id) or {}).get(company) or 0.0)
            revenue = count * price
            branch_key = str(metric["branch"])
            branch_summary_key = f"outbound_{branch_key}_income"

            metric_rows.append(
                {
                    "company": company,
                    "branch": branch_key,
                    "branch_label": metric["branch_label"],
                    "metric_id": row_id,
                    "label": metric["label"],
                    "unit": metric["unit"],
                    "count": _round_qty(count),
                    "price": _round_money(price),
                    "revenue": _round_money(revenue),
                }
            )
            summary["outbound_income"] += revenue
            summary[branch_summary_key] = summary.get(branch_summary_key, 0.0) + revenue
            if row_id.endswith("_picked_orders"):
                summary["outbound_picked_orders"] += count
            elif row_id.endswith("_picked_rows"):
                summary["outbound_picked_rows"] += count
            elif row_id.endswith("_picked_pcs"):
                summary["outbound_picked_pcs"] += count
            elif row_id in {"store_full_pallets", "ecom_pallet"}:
                summary["outbound_full_pallets"] += count
            elif row_id == "store_loaded_pallets":
                summary["outbound_loaded_pallets"] += count

            company_summary = company_summaries.setdefault(
                company,
                {
                    "company": company,
                    "outbound_income": 0.0,
                    "outbound_store_income": 0.0,
                    "outbound_ecom_income": 0.0,
                    "outbound_picked_orders": 0.0,
                    "outbound_picked_rows": 0.0,
                    "outbound_picked_pcs": 0.0,
                    "outbound_full_pallets": 0.0,
                    "outbound_loaded_pallets": 0.0,
                },
            )
            company_summary["outbound_income"] += revenue
            company_summary[branch_summary_key] = company_summary.get(branch_summary_key, 0.0) + revenue
            if row_id.endswith("_picked_orders"):
                company_summary["outbound_picked_orders"] += count
            elif row_id.endswith("_picked_rows"):
                company_summary["outbound_picked_rows"] += count
            elif row_id.endswith("_picked_pcs"):
                company_summary["outbound_picked_pcs"] += count
            elif row_id in {"store_full_pallets", "ecom_pallet"}:
                company_summary["outbound_full_pallets"] += count
            elif row_id == "store_loaded_pallets":
                company_summary["outbound_loaded_pallets"] += count

            if count <= 0 and revenue <= 0:
                continue
            start_node = _add_node(nodes, company, "outbound:start", "Outbound", "outbound_source", 0)
            branch_node = _add_node(nodes, company, f"outbound:{branch_key}", str(metric["branch_label"]), "outbound_branch", 1)
            metric_node = _add_node(nodes, company, f"outbound:{row_id}", str(metric["label"]), "outbound_metric", 2)
            for node in (start_node, branch_node, metric_node):
                node["value"] += revenue
                node["revenue"] += revenue
                node["outbound_revenue"] += revenue
                node["labels"] += count
                node["unit_label"] = "st"
            start_link_key = f'{start_node["id"]}->{branch_node["id"]}'
            metric_link_key = f'{branch_node["id"]}->{metric_node["id"]}'
            _add_link(links, start_node["id"], branch_node["id"], company, revenue, count, outbound_revenue=revenue)
            _add_link(links, branch_node["id"], metric_node["id"], company, revenue, count, outbound_revenue=revenue)
            for row, amount in trace_amounts:
                node_ids = [start_node["id"], branch_node["id"], metric_node["id"]]
                link_keys = [start_link_key, metric_link_key]
                if include_trace_details:
                    trace_rows.append(
                        _outbound_trace_row(
                            row,
                            metric=metric,
                            company=company,
                            amount=amount,
                            revenue=amount * price,
                            node_ids=node_ids,
                            link_keys=link_keys,
                        )
                    )
                else:
                    stamp = _row_datetime(row)
                    trace_rows.append(
                        _minimal_trace_row(
                            company=company,
                            received_date=stamp.date().isoformat() if stamp else "",
                            consumed=True,
                            node_ids=node_ids,
                            link_keys=link_keys,
                            trace_type="outbound",
                        )
                    )

    node_rows: list[dict] = []
    for node in nodes.values():
        node["value"] = _round_money(node["value"])
        node["revenue"] = _round_money(node["revenue"])
        node["outbound_revenue"] = _round_money(node["outbound_revenue"])
        node["labels"] = _round_qty(node["labels"])
        node_rows.append(node)
    node_rows.sort(key=lambda item: (item["company"], item["stage"], item["label"]))

    link_rows: list[dict] = []
    for link in links.values():
        link["value"] = _round_money(link["value"])
        link["revenue"] = _round_money(link["revenue"])
        link["outbound_revenue"] = _round_money(link["outbound_revenue"])
        link["labels"] = _round_qty(link["labels"])
        if link["outbound_revenue"] > 0:
            link["unit_label"] = "st"
        link_rows.append(link)
    link_rows.sort(key=lambda item: (item["company"], item["source"], item["target"]))

    for key in list(summary):
        summary[key] = _round_money(summary[key]) if "income" in key or "revenue" in key else _round_qty(summary[key])
    for row in company_summaries.values():
        for key in list(row):
            if key == "company":
                continue
            row[key] = _round_money(row[key]) if "income" in key or "revenue" in key else _round_qty(row[key])

    return {
        "nodes": node_rows,
        "links": link_rows,
        "trace_rows": trace_rows,
        "metrics": sorted(metric_rows, key=lambda item: (item["company"], item["branch"], item["label"])),
        "summary": summary,
        "companies": sorted(company_summaries.values(), key=lambda item: item["company"]),
    }


def _sync_branch_revenue(branch: TraceBranch) -> None:
    branch.revenue = max(0.0, float(branch.label_revenue or 0.0) + float(branch.purchase_line_revenue or 0.0))


def _normalize_process_point_key(value: Any) -> str:
    key = normalize_process(value).replace(" ", "_")
    return PROCESS_POINT_ALIASES.get(key, key)


def _process_points_from_kpi(rows: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    points: dict[tuple[str, str], float] = {}
    targets = parse_kpi_targets([dict(row) for row in rows or []])
    rules = parse_kpi_rule_rows([dict(row) for row in SQL_REFERENCE_KPI_RULE_ROWS])
    rule_metrics: dict[str, set[str]] = {}
    for rule in rules:
        rule_metrics.setdefault(_normalize_process_point_key(rule.process_key), set()).add(rule.metric)

    for (company, raw_process), target in targets.items():
        process = _normalize_process_point_key(raw_process)
        metric = PROCESS_DEFAULT_METRIC.get(process)
        if metric not in (target.points or {}) or float((target.points or {}).get(metric) or 0.0) <= 0:
            candidates = rule_metrics.get(process, set())
            if candidates:
                metric = next(
                    (
                        candidate
                        for candidate in ("rows", "packages", "pallets", "orders")
                        if candidate in candidates and float((target.points or {}).get(candidate) or 0.0) > 0
                    ),
                    metric,
                )
        value = float((target.points or {}).get(metric or "") or 0.0)
        if value > 0:
            points[(company, process)] = value
            points.setdefault(("", process), value)
    return points


def _process_point_value(point_map: dict[tuple[str, str], float], company: str, process_key: str) -> float:
    key = _normalize_process_point_key(process_key)
    company_key = clean_productivity_finance_company_code(company)
    return float(point_map.get((company_key, key)) or point_map.get(("", key)) or 0.0)


def _append_process(
    branch: TraceBranch,
    process_key: str,
    point_map: dict[tuple[str, str], float],
    warnings: list[dict],
    *,
    source: str,
) -> None:
    key = _normalize_process_point_key(process_key)
    if not key:
        return
    if branch.processes and branch.processes[-1].key == key:
        return
    points = _process_point_value(point_map, branch.company, key)
    if points <= 0:
        warnings.append(
            {
                "code": "missing_process_points",
                "process_key": key,
                "process_label": PROCESS_LABELS.get(key, key),
                "message": f"Saknar KPI-poäng för {PROCESS_LABELS.get(key, key)}.",
            }
        )
    label = PROCESS_LABELS.get(key, key)
    branch.processes.append(ProcessVisit(key=key, label=label, points=points, source=source))
    branch.trace_steps.append(label)


def _classify_trans(row: dict[str, Any]) -> tuple[str | None, str]:
    trans_type = _normalize_type(_row_value(row, "type", "Typ"))
    loc_to = _row_text(row, "loc_to", "Till").upper()
    if trans_type == "26" and loc_to.startswith("AS"):
        return "DECANTING", "open_autostore"
    if trans_type == "111" and loc_to.startswith("HBW"):
        return "HBW", "open_hbw"
    if trans_type == "22":
        return "MANUAL_BUFFER", "open_buffer"
    if trans_type in {"21", "27", "29"}:
        return "PUTAWAY_PICK", "open_pick_location"
    return None, ""


def _pick_location_key(company: str, warehouse: str, item: str, location: str) -> tuple[str, str, str, str]:
    return (company.upper(), warehouse.upper(), item.upper(), location.upper())


def _consume_pick_queue(
    queues: dict[tuple[str, str, str, str], list[PickQueueEntry]],
    branches: dict[str, TraceBranch],
    key: tuple[str, str, str, str],
    qty: float,
    *,
    mark_consumed: bool,
) -> list[tuple[TraceBranch, float]]:
    consumed: list[tuple[TraceBranch, float]] = []
    remaining = max(0.0, float(qty or 0.0))
    queue = queues.setdefault(key, [])
    while remaining > 0 and queue:
        entry = queue[0]
        take = min(entry.qty, remaining)
        entry.qty -= take
        remaining -= take
        if entry.branch_id and entry.branch_id in branches:
            branch = branches[entry.branch_id]
            consumed.append((branch, take))
            if mark_consumed:
                branch.qty = max(0.0, branch.qty - take)
                if branch.qty <= 0.0001:
                    branch.qty = 0.0
                    branch.consumed = True
                    branch.status = "consumed"
        if entry.qty <= 0.0001:
            queue.pop(0)
    return consumed


def _branch_matches_pall(branch: TraceBranch, pall: str) -> bool:
    if not branch.active or branch.revenue <= 0:
        return False
    return bool(_pall_aliases(branch.current_pall) & _pall_aliases(pall))


def _event_sort_key(row: dict[str, Any]) -> tuple[datetime, str]:
    stamp = _row_datetime(row) or datetime.min
    return stamp, _row_id(row, 0)


def _build_current_pallet_locations(rows: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for row in rows or []:
        company = _row_company(row)
        pall = _row_pall(row)
        location = _row_text(row, "location", "Lagerplats", "loc", "Lokation").upper()
        if company and pall and location:
            result[(company, _normalize_pall(pall))] = location
    return result


def _status_from_current_location(branch: TraceBranch, current_locations: dict[tuple[str, str], str]) -> str:
    if branch.consumed:
        return "consumed"
    if branch.status == "open_pick_location":
        return branch.status
    location = current_locations.get((branch.company, _normalize_pall(branch.current_pall)), "").upper()
    probe = location or branch.location.upper() or branch.current_pall.upper()
    if probe.startswith("AS"):
        return "open_autostore"
    if probe.startswith("HBW"):
        return "open_hbw"
    if branch.status in {"open_autostore", "open_hbw", "open_buffer"}:
        return branch.status
    if location:
        return "open_buffer"
    return branch.status or "open_not_putaway"


def _node_id(company: str, key: str) -> str:
    return f"{company}:{key}"


def _add_node(nodes: dict[str, dict], company: str, key: str, label: str, node_type: str, stage: int) -> dict:
    node_id = _node_id(company, key)
    node = nodes.setdefault(
        node_id,
        {
            "id": node_id,
            "company": company,
            "key": key,
            "label": label,
            "type": node_type,
            "stage": stage,
            "value": 0.0,
            "revenue": 0.0,
            "label_revenue": 0.0,
            "purchase_line_revenue": 0.0,
            "outbound_revenue": 0.0,
            "labels": 0.0,
            "points": 0.0,
            "confidence": "high",
        },
    )
    return node


def _add_link(
    links: dict[tuple[str, str, str], dict],
    source: str,
    target: str,
    company: str,
    revenue: float,
    labels: float,
    *,
    label_revenue: float = 0.0,
    purchase_line_revenue: float = 0.0,
    outbound_revenue: float = 0.0,
) -> None:
    if revenue <= 0 and labels <= 0:
        return
    key = (source, target, company)
    link = links.setdefault(
        key,
        {
            "source": source,
            "target": target,
            "company": company,
            "value": 0.0,
            "revenue": 0.0,
            "label_revenue": 0.0,
            "purchase_line_revenue": 0.0,
            "outbound_revenue": 0.0,
            "labels": 0.0,
            "confidence": "high",
        },
    )
    link["value"] += revenue
    link["revenue"] += revenue
    link["label_revenue"] += label_revenue
    link["purchase_line_revenue"] += purchase_line_revenue
    link["outbound_revenue"] += outbound_revenue
    link["labels"] += labels


def _trace_path_steps(branch: TraceBranch, terminal_label: str) -> list[str]:
    steps = [f"Mottagning {branch.origin_pall or branch.current_pall}".strip()]
    steps.extend(branch.trace_steps or [visit.label for visit in branch.processes])
    steps.append(terminal_label)
    deduped: list[str] = []
    for step in steps:
        text = _clean_text(step)
        if text and (not deduped or deduped[-1] != text):
            deduped.append(text)
    return deduped


def _trace_row_for_branch(
    branch: TraceBranch,
    *,
    terminal_key: str,
    terminal_label: str,
    current_locations: dict[tuple[str, str], str],
    node_ids: list[str],
    link_keys: list[str],
) -> dict[str, Any]:
    current_location = current_locations.get((branch.company, _normalize_pall(branch.current_pall)), "") or branch.location
    path_steps = _trace_path_steps(branch, terminal_label)
    row: dict[str, Any] = {
        "branch_id": branch.id,
        "origin_id": branch.origin_id,
        "company": branch.company,
        "warehouse": branch.warehouse,
        "item": branch.item,
        "origin_pall": branch.origin_pall or branch.current_pall,
        "current_pall": branch.current_pall,
        "current_location": current_location,
        "purchase_number": branch.purchase_number,
        "purchase_line": branch.purchase_line,
        "received_date": branch.received_date.isoformat() if branch.received_date else "",
        "source_row_id": branch.source_row_id,
        "qty_remaining": _round_qty(branch.qty),
        "revenue": _round_money(branch.revenue),
        "label_revenue": _round_money(branch.label_revenue),
        "purchase_line_revenue": _round_money(branch.purchase_line_revenue),
        "label_fraction": _round_qty(branch.label_fraction),
        "status": terminal_key,
        "status_label": terminal_label,
        "consumed": bool(branch.consumed),
        "confidence": branch.confidence,
        "path": " -> ".join(path_steps),
        "node_ids": list(node_ids),
        "link_keys": list(link_keys),
    }
    for index, step in enumerate(path_steps, start=1):
        row[f"step_{index}"] = step
    return row


def _minimal_trace_row(
    *,
    company: str,
    received_date: date | str | None,
    consumed: bool,
    node_ids: list[str],
    link_keys: list[str],
    trace_type: str = "inbound",
) -> dict[str, Any]:
    if isinstance(received_date, date):
        received = received_date.isoformat()
    else:
        received = str(received_date or "")
    return {
        "trace_type": trace_type,
        "company": company,
        "received_date": received,
        "consumed": bool(consumed),
        "node_ids": list(node_ids),
        "link_keys": list(link_keys),
    }


def _finalize_sankey(
    branches: list[TraceBranch],
    *,
    only_consumed: bool,
    warnings: list[dict],
    current_locations: dict[tuple[str, str], str],
    branch_predicate: Callable[[TraceBranch], bool] | None = None,
    include_trace_details: bool = True,
) -> tuple[list[dict], list[dict], list[dict], dict, list[dict]]:
    nodes: dict[str, dict] = {}
    links: dict[tuple[str, str, str], dict] = {}
    process_rows: dict[tuple[str, str], dict] = {}
    trace_rows: list[dict] = []
    summary = {
        "gross_income": 0.0,
        "gross_income_labels": 0.0,
        "gross_income_purchase_lines": 0.0,
        "labels_traced": 0.0,
        "labels_consumed": 0.0,
        "labels_open": 0.0,
        "unallocated_revenue": 0.0,
    }
    warned_missing_points: set[str] = set()

    for branch in branches:
        if not branch.active or branch.revenue <= 0:
            continue
        if branch_predicate is not None and not branch_predicate(branch):
            continue
        if only_consumed and not branch.consumed:
            continue
        company = branch.company or "OKANT"
        status_key = _status_from_current_location(branch, current_locations)
        terminal_key = status_key
        terminal_label = OPEN_STATUS_LABELS.get(status_key, OPEN_STATUS_LABELS["open_not_putaway"])
        summary["gross_income"] += branch.revenue
        summary["gross_income_labels"] += branch.label_revenue
        summary["gross_income_purchase_lines"] += branch.purchase_line_revenue
        summary["labels_traced"] += branch.label_fraction
        if branch.consumed:
            summary["labels_consumed"] += branch.label_fraction
        else:
            summary["labels_open"] += branch.label_fraction

        start_node = _add_node(nodes, company, "start", "Mottaget inbound", "source", 0)
        start_node["value"] += branch.revenue
        start_node["revenue"] += branch.revenue
        start_node["label_revenue"] += branch.label_revenue
        start_node["purchase_line_revenue"] += branch.purchase_line_revenue
        start_node["labels"] += branch.label_fraction

        previous_node_id = start_node["id"]
        path_node_ids = [previous_node_id]
        path_link_keys: list[str] = []
        total_points = sum(max(0.0, visit.points) for visit in branch.processes)
        if total_points <= 0 and branch.processes:
            summary["unallocated_revenue"] += branch.revenue
            for visit in branch.processes:
                if visit.key not in warned_missing_points:
                    warned_missing_points.add(visit.key)
                    warnings.append(
                        {
                            "code": "unallocated_process_revenue",
                            "process_key": visit.key,
                            "message": f"Intäkt kunde inte fördelas för {visit.label} eftersom poäng saknas.",
                        }
                    )

        for index, visit in enumerate(branch.processes, start=1):
            node = _add_node(nodes, company, f"process:{visit.key}", visit.label, "process", index)
            share = (visit.points / total_points) if total_points > 0 and visit.points > 0 else 0.0
            allocated_label_revenue = branch.label_revenue * share
            allocated_purchase_line_revenue = branch.purchase_line_revenue * share
            allocated = allocated_label_revenue + allocated_purchase_line_revenue
            node["value"] += branch.revenue
            node["revenue"] += allocated
            node["label_revenue"] += allocated_label_revenue
            node["purchase_line_revenue"] += allocated_purchase_line_revenue
            node["labels"] += branch.label_fraction
            node["points"] += visit.points
            process_key = (company, visit.key)
            process = process_rows.setdefault(
                process_key,
                {
                    "company": company,
                    "process_key": visit.key,
                    "label": visit.label,
                    "points": 0.0,
                    "revenue": 0.0,
                    "label_revenue": 0.0,
                    "purchase_line_revenue": 0.0,
                    "labels": 0.0,
                    "share": 0.0,
                },
            )
            process["points"] += visit.points
            process["revenue"] += allocated
            process["label_revenue"] += allocated_label_revenue
            process["purchase_line_revenue"] += allocated_purchase_line_revenue
            process["labels"] += branch.label_fraction
            link_key = f'{previous_node_id}->{node["id"]}'
            _add_link(
                links,
                previous_node_id,
                node["id"],
                company,
                branch.revenue,
                branch.label_fraction,
                label_revenue=branch.label_revenue,
                purchase_line_revenue=branch.purchase_line_revenue,
            )
            path_link_keys.append(link_key)
            previous_node_id = node["id"]
            path_node_ids.append(previous_node_id)

        terminal = _add_node(nodes, company, f"terminal:{terminal_key}", terminal_label, "terminal", 99)
        terminal["value"] += branch.revenue
        terminal["label_revenue"] += branch.label_revenue
        terminal["purchase_line_revenue"] += branch.purchase_line_revenue
        terminal["labels"] += branch.label_fraction
        if branch.confidence != "high":
            terminal["confidence"] = branch.confidence
        terminal_link_key = f'{previous_node_id}->{terminal["id"]}'
        _add_link(
            links,
            previous_node_id,
            terminal["id"],
            company,
            branch.revenue,
            branch.label_fraction,
            label_revenue=branch.label_revenue,
            purchase_line_revenue=branch.purchase_line_revenue,
        )
        path_link_keys.append(terminal_link_key)
        path_node_ids.append(terminal["id"])
        if include_trace_details:
            trace_rows.append(
                _trace_row_for_branch(
                    branch,
                    terminal_key=terminal_key,
                    terminal_label=terminal_label,
                    current_locations=current_locations,
                    node_ids=path_node_ids,
                    link_keys=path_link_keys,
                )
            )
        else:
            trace_rows.append(
                _minimal_trace_row(
                    company=company,
                    received_date=branch.received_date,
                    consumed=branch.consumed,
                    node_ids=path_node_ids,
                    link_keys=path_link_keys,
                )
            )

    gross = summary["gross_income"]
    for process in process_rows.values():
        process["revenue"] = _round_money(process["revenue"])
        process["label_revenue"] = _round_money(process["label_revenue"])
        process["purchase_line_revenue"] = _round_money(process["purchase_line_revenue"])
        process["points"] = _round_qty(process["points"])
        process["labels"] = _round_qty(process["labels"])
        process["share"] = round((process["revenue"] / gross) if gross > 0 else 0.0, 4)

    node_rows = []
    for node in nodes.values():
        node["value"] = _round_money(node["value"])
        node["revenue"] = _round_money(node["revenue"])
        node["label_revenue"] = _round_money(node["label_revenue"])
        node["purchase_line_revenue"] = _round_money(node["purchase_line_revenue"])
        node["outbound_revenue"] = _round_money(node["outbound_revenue"])
        node["labels"] = _round_qty(node["labels"])
        node["points"] = _round_qty(node["points"])
        node_rows.append(node)
    node_rows.sort(key=lambda item: (item["company"], item["stage"], item["label"]))

    link_rows = []
    for link in links.values():
        link["value"] = _round_money(link["value"])
        link["revenue"] = _round_money(link["revenue"])
        link["label_revenue"] = _round_money(link["label_revenue"])
        link["purchase_line_revenue"] = _round_money(link["purchase_line_revenue"])
        link["outbound_revenue"] = _round_money(link["outbound_revenue"])
        link["labels"] = _round_qty(link["labels"])
        link_rows.append(link)
    link_rows.sort(key=lambda item: (item["company"], item["source"], item["target"]))

    for key in list(summary):
        summary[key] = _round_money(summary[key]) if "revenue" in key or "income" in key else _round_qty(summary[key])
    return node_rows, link_rows, sorted(process_rows.values(), key=lambda item: (item["company"], item["label"])), summary, trace_rows


def build_sankey_inbound_payload(
    *,
    source_rows: dict[str, list[dict[str, Any]]],
    finance_settings: dict,
    company_codes: list[str],
    period_start: date,
    period_end: date,
    follow_until: date,
    period_type: str = "cohort",
    period_label: str | None = None,
    company_filter: str | None = None,
    only_consumed: bool = False,
    process_points: dict[str, float] | None = None,
    source_status: list[dict] | None = None,
    warnings: list[dict] | None = None,
) -> dict:
    normalized_company_filter = clean_productivity_finance_company_code(company_filter)
    allowed_companies = {clean_productivity_finance_company_code(code) for code in company_codes if clean_productivity_finance_company_code(code)}
    if normalized_company_filter and normalized_company_filter != "ALL":
        allowed_companies = {normalized_company_filter}
    receive_rows = source_rows.get("receive") or []
    trans_rows = source_rows.get("trans") or []
    pick_rows = source_rows.get("pick") or []
    dispatch_rows = source_rows.get("dispatch") or []
    buffer_rows = source_rows.get("buffer") or []
    kpi_rows = source_rows.get("kpi") or []
    alias_rows = source_rows.get("item_alias") or []
    warnings_out = list(warnings or [])

    row_companies = sorted({_row_company(row) for row in receive_rows + trans_rows + pick_rows + dispatch_rows if _row_company(row)})
    if not allowed_companies:
        allowed_companies = set(row_companies)
    all_company_codes = sorted(allowed_companies or set(row_companies))
    label_prices, purchase_line_prices, price_warnings = _inbound_prices(finance_settings, all_company_codes)
    outbound_prices, outbound_price_warnings = _outbound_prices(finance_settings, all_company_codes)
    warnings_out.extend(price_warnings)
    warnings_out.extend(outbound_price_warnings)

    point_map = {
        ("", _normalize_process_point_key(key)): float(value or 0.0)
        for key, value in (process_points or {}).items()
    }
    if not point_map:
        point_map = _process_points_from_kpi(kpi_rows)

    zeroing_by_pall: dict[tuple[str, str], list[datetime]] = {}
    for row in receive_rows:
        if _normalize_type(_row_value(row, "type", "Typ")) != ZEROING_RECEIVE_TYPE:
            continue
        company = _row_company(row)
        pall = _normalize_pall(_row_pall(row))
        stamp = _row_datetime(row)
        if company and pall and stamp:
            zeroing_by_pall.setdefault((company, pall), []).append(stamp)

    branches: list[TraceBranch] = []
    branch_map: dict[str, TraceBranch] = {}
    # Index (bolag, pall-alias) -> positioner i branches, så vi slipper skanna hela
    # branches-listan per trans/pick-event (tidigare O(events × grenar)). Vi indexerar
    # under alla pall-alias och lägger till nya alias när current_pall ändras; läsning
    # dedupar via set och filtrerar med _branch_matches_pall, så resultatet blir
    # identiskt med den tidigare linjära skanningen men i global gren-ordning.
    pall_index: dict[tuple[str, str], list[int]] = {}
    branch_index: dict[str, int] = {}

    def _register_pall(idx: int, branch: TraceBranch) -> None:
        for alias in _pall_aliases(branch.current_pall):
            pall_index.setdefault((branch.company, alias), []).append(idx)

    def _index_branch(branch: TraceBranch) -> None:
        idx = len(branches)
        branches.append(branch)
        branch_map[branch.id] = branch
        branch_index[branch.id] = idx
        _register_pall(idx, branch)

    def _matching_branches(company: str, pall: str) -> list[TraceBranch]:
        candidate_indices: set[int] = set()
        for alias in _pall_aliases(pall):
            candidate_indices.update(pall_index.get((company, alias), ()))
        result: list[TraceBranch] = []
        for idx in sorted(candidate_indices):
            branch = branches[idx]
            if branch.company == company and _branch_matches_pall(branch, pall):
                result.append(branch)
        return result

    excluded_zeroed = 0
    filtered_receives: list[dict[str, Any]] = []
    purchase_line_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    missing_purchase_line_rows = 0
    for index, row in enumerate(receive_rows):
        company = _row_company(row)
        if not _company_allowed(company, allowed_companies):
            continue
        if not _is_in_date_window(row, period_start, period_end):
            continue
        receive_type = _normalize_type(_row_value(row, "type", "Typ"))
        if receive_type in EXCLUDED_RECEIVE_TYPES:
            continue
        qty = _row_number(row, "qty_suf", "Mottaget", "received_qty")
        if qty <= 0:
            continue
        pall = _normalize_pall(_row_pall(row))
        stamp = _row_datetime(row)
        zeroings = zeroing_by_pall.get((company, pall), [])
        if stamp and any(zero_stamp >= stamp for zero_stamp in zeroings):
            excluded_zeroed += 1
            continue
        origin_id = _row_id(row, index)
        entry = {
            "index": index,
            "row": row,
            "company": company,
            "warehouse": _row_warehouse(row),
            "item": _row_item(row),
            "pall": pall,
            "qty": qty,
            "origin_id": origin_id,
            "received_date": stamp.date() if stamp else None,
        }
        filtered_receives.append(entry)
        purchase_line_key = _purchase_line_key(row)
        if purchase_line_key:
            purchase_line_groups.setdefault(purchase_line_key, []).append(entry)
        else:
            missing_purchase_line_rows += 1

    purchase_line_revenue_by_origin: dict[str, float] = {}
    for key, entries in purchase_line_groups.items():
        if not entries:
            continue
        purchase_line_revenue = float(purchase_line_prices.get(key[0], 0.0))
        if purchase_line_revenue <= 0:
            continue
        share = purchase_line_revenue / len(entries)
        for entry in entries:
            origin_id = str(entry["origin_id"])
            purchase_line_revenue_by_origin[origin_id] = purchase_line_revenue_by_origin.get(origin_id, 0.0) + share

    if missing_purchase_line_rows and any(float(value or 0.0) > 0 for value in purchase_line_prices.values()):
        warnings_out.append(
            {
                "code": "missing_inbound_purchase_line_key",
                "count": missing_purchase_line_rows,
                "message": f"{missing_purchase_line_rows} mottagningar saknar inköpsnr eller rad och fick ingen inköpsradsintäkt.",
            }
        )

    for entry in filtered_receives:
        row = entry["row"]
        company = str(entry["company"])
        origin_id = str(entry["origin_id"])
        label_revenue = float(label_prices.get(company, 0.0))
        purchase_line_revenue = float(purchase_line_revenue_by_origin.get(origin_id, 0.0))
        branch = TraceBranch(
            id=f"{origin_id}:0",
            origin_id=origin_id,
            company=company,
            warehouse=str(entry["warehouse"]),
            item=str(entry["item"]),
            current_pall=str(entry["pall"]),
            qty=float(entry["qty"]),
            revenue=label_revenue + purchase_line_revenue,
            label_fraction=1.0,
            label_revenue=label_revenue,
            purchase_line_revenue=purchase_line_revenue,
            origin_pall=str(entry["pall"]),
            source_row_id=_row_text(row, "rowid", "Rowid", "Radid", "radid", "id") or origin_id,
            purchase_number=_row_purchase_number(row),
            purchase_line=_row_purchase_line(row),
            received_date=entry["received_date"],
        )
        _append_process(branch, "RECEIVING", point_map, warnings_out, source="receive")
        _index_branch(branch)

    if excluded_zeroed:
        warnings_out.append(
            {
                "code": "type_100_zeroed_receipts",
                "count": excluded_zeroed,
                "message": f"{excluded_zeroed} mottagningar exkluderades av typ 100-nollstallning.",
            }
        )

    decant_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in trans_rows:
        process_key, _status_key = _classify_trans(row)
        if process_key != "DECANTING":
            continue
        company = _row_company(row)
        if not _company_allowed(company, allowed_companies):
            continue
        pall = _normalize_pall(_row_pall(row))
        if company and pall:
            decant_groups.setdefault((company, pall), []).append(row)
    for rows in decant_groups.values():
        rows.sort(key=_event_sort_key)

    processed_decant_branches: set[tuple[str, str]] = set()
    pick_queues: dict[tuple[str, str, str, str], list[PickQueueEntry]] = {}

    events = []
    events.extend(("trans", row) for row in trans_rows if _company_allowed(_row_company(row), allowed_companies))
    events.extend(("receive", row) for row in receive_rows if _company_allowed(_row_company(row), allowed_companies))
    events.extend(("pick", row) for row in pick_rows if _company_allowed(_row_company(row), allowed_companies))
    events.sort(key=lambda item: _event_sort_key(item[1]))

    for source_key, row in events:
        if source_key == "trans":
            pall = _normalize_pall(_row_pall(row))
            company = _row_company(row)
            process_key, status_key = _classify_trans(row)
            if not process_key or not pall:
                continue
            matching = _matching_branches(company, pall)
            if process_key == "DECANTING":
                for branch in list(matching):
                    split_key = (branch.id, pall)
                    if split_key in processed_decant_branches:
                        continue
                    processed_decant_branches.add(split_key)
                    group = decant_groups.get((company, pall), [row])
                    total_child_qty = sum(max(0.0, _row_number(item, "qty", "Antal", "qty_suf")) for item in group)
                    has_remaining = branch.qty > total_child_qty + 0.0001
                    child_count = len(group) + (1 if has_remaining else 0)
                    if child_count <= 0:
                        continue
                    share_label_revenue = branch.label_revenue / child_count
                    share_purchase_line_revenue = branch.purchase_line_revenue / child_count
                    share_revenue = share_label_revenue + share_purchase_line_revenue
                    share_label = branch.label_fraction / child_count
                    original_revenue = branch.revenue
                    original_label = branch.label_fraction
                    if has_remaining:
                        branch.label_revenue = share_label_revenue
                        branch.purchase_line_revenue = share_purchase_line_revenue
                        _sync_branch_revenue(branch)
                        branch.label_fraction = share_label
                        branch.qty = max(0.0, branch.qty - total_child_qty)
                    else:
                        branch.active = False
                        branch.revenue = 0.0
                        branch.label_revenue = 0.0
                        branch.purchase_line_revenue = 0.0
                        branch.label_fraction = 0.0
                        branch.qty = 0.0
                    for child_index, item in enumerate(group, start=1):
                        child_pall = _normalize_pall(_row_text(item, "loc_to", "Till") or _row_pall(item))
                        child_qty = max(0.0, _row_number(item, "qty", "Antal", "qty_suf"))
                        child = TraceBranch(
                            id=f"{branch.id}:AS{child_index}",
                            origin_id=branch.origin_id,
                            company=branch.company,
                            warehouse=branch.warehouse,
                            item=branch.item,
                            current_pall=child_pall,
                            qty=child_qty,
                            revenue=share_revenue,
                            label_fraction=share_label,
                            label_revenue=share_label_revenue,
                            purchase_line_revenue=share_purchase_line_revenue,
                            origin_pall=branch.origin_pall,
                            source_row_id=branch.source_row_id,
                            purchase_number=branch.purchase_number,
                            purchase_line=branch.purchase_line,
                            received_date=branch.received_date,
                            trace_steps=list(branch.trace_steps),
                            processes=list(branch.processes),
                            status="open_autostore",
                        )
                        _append_process(child, "DECANTING", point_map, warnings_out, source="trans")
                        _index_branch(child)
                    if child_count > 1 and original_revenue > 0:
                        warnings_out.append(
                            {
                                "code": "equal_split_applied",
                                "origin_id": branch.origin_id,
                                "branches": child_count,
                                "message": "Inboundintäkt delades lika mellan split-grenar.",
                            }
                        )
                        if original_label <= 0:
                            branch.label_fraction = 0.0
                continue
            for branch in matching:
                _append_process(branch, process_key, point_map, warnings_out, source="trans")
                branch.status = status_key or branch.status
                loc_to = _row_text(row, "loc_to", "Till").upper()
                if loc_to:
                    branch.location = loc_to
                if status_key == "open_pick_location":
                    key = _pick_location_key(branch.company, branch.warehouse, branch.item, loc_to)
                    queue = pick_queues.setdefault(key, [])
                    prior_qty = max(0.0, _row_number(row, "qty_pre", "Saldo före", "Saldo fore", "saldo_pre"))
                    if prior_qty > 0 and not queue:
                        queue.append(PickQueueEntry(None, prior_qty))
                        branch.confidence = "partial_fifo"
                    queue.append(PickQueueEntry(branch.id, branch.qty))
                elif loc_to and loc_to.startswith("AS"):
                    new_current = _normalize_pall(loc_to)
                    if new_current != branch.current_pall:
                        branch.current_pall = new_current
                        _register_pall(branch_index[branch.id], branch)

        elif source_key == "receive":
            if _normalize_type(_row_value(row, "type", "Typ")) != BUFFER_UPDATE_RECEIVE_TYPE:
                continue
            company = _row_company(row)
            location = _row_text(row, "location", "Lokation", "loc_from", "Fran", "Från").upper()
            item = _row_item(row)
            warehouse = _row_warehouse(row)
            new_pall = _normalize_pall(_row_pall(row))
            qty = max(0.0, _row_number(row, "qty_suf", "Mottaget", "qty"))
            if location and item and qty > 0:
                key = _pick_location_key(company, warehouse, item, location)
                moved = _consume_pick_queue(pick_queues, branch_map, key, qty, mark_consumed=False)
                for move_index, (branch, moved_qty) in enumerate(moved, start=1):
                    if branch.revenue <= 0:
                        continue
                    if moved_qty >= branch.qty - 0.0001:
                        child_revenue = branch.revenue
                        child_label_revenue = branch.label_revenue
                        child_purchase_line_revenue = branch.purchase_line_revenue
                        child_label = branch.label_fraction
                        branch.active = False
                        branch.revenue = 0.0
                        branch.label_revenue = 0.0
                        branch.purchase_line_revenue = 0.0
                        branch.label_fraction = 0.0
                        branch.qty = 0.0
                    else:
                        child_revenue = branch.revenue / 2
                        child_label_revenue = branch.label_revenue / 2
                        child_purchase_line_revenue = branch.purchase_line_revenue / 2
                        child_label = branch.label_fraction / 2
                        branch.label_revenue -= child_label_revenue
                        branch.purchase_line_revenue -= child_purchase_line_revenue
                        _sync_branch_revenue(branch)
                        branch.label_fraction -= child_label
                        branch.qty = max(0.0, branch.qty - moved_qty)
                    child = TraceBranch(
                        id=f"{branch.id}:BU{move_index}",
                        origin_id=branch.origin_id,
                        company=branch.company,
                        warehouse=branch.warehouse,
                        item=branch.item,
                        current_pall=new_pall,
                        qty=moved_qty,
                        revenue=child_revenue,
                        label_fraction=child_label,
                        label_revenue=child_label_revenue,
                        purchase_line_revenue=child_purchase_line_revenue,
                        origin_pall=branch.origin_pall,
                        source_row_id=branch.source_row_id,
                        purchase_number=branch.purchase_number,
                        purchase_line=branch.purchase_line,
                        received_date=branch.received_date,
                        trace_steps=list(branch.trace_steps),
                        processes=list(branch.processes),
                        status="open_buffer",
                        confidence=branch.confidence,
                    )
                    _append_process(child, "BUFFER_UPDATE", point_map, warnings_out, source="receive")
                    _index_branch(child)
                if not moved and new_pall:
                    for branch in _matching_branches(company, new_pall):
                        _append_process(branch, "BUFFER_UPDATE", point_map, warnings_out, source="receive")
                        branch.status = "open_buffer"
            elif new_pall:
                for branch in _matching_branches(company, new_pall):
                    _append_process(branch, "BUFFER_UPDATE", point_map, warnings_out, source="receive")
                    branch.status = "open_buffer"

        elif source_key == "pick":
            company = _row_company(row)
            warehouse = _row_warehouse(row)
            item = _row_item(row)
            location = _row_text(row, "location", "Lokation", "pick_loc").upper()
            qty = max(0.0, _row_number(row, "qty_suf", "Plockat", "picked_qty", "qty"))
            if qty <= 0:
                continue
            pall = _normalize_pall(_row_pall(row))
            direct = _matching_branches(company, pall) if pall else []
            if direct:
                remaining = qty
                for branch in direct:
                    if remaining <= 0:
                        break
                    take = min(branch.qty, remaining) if branch.qty > 0 else remaining
                    branch.qty = max(0.0, branch.qty - take)
                    remaining -= take
                    if branch.qty <= 0.0001:
                        branch.qty = 0.0
                        branch.consumed = True
                        branch.status = "consumed"
                continue
            if location:
                key = _pick_location_key(company, warehouse, item, location)
                if key not in pick_queues:
                    warnings_out.append(
                        {
                            "code": "pick_location_owner_unknown",
                            "company": company,
                            "message": "Plockrad saknar känd inbound-agare i vald period.",
                        }
                    )
                _consume_pick_queue(pick_queues, branch_map, key, qty, mark_consumed=True)

    current_locations = _build_current_pallet_locations(buffer_rows)
    requested_period_type = str(period_type or "cohort").strip().lower()
    requested_period_label = period_label or _period_label(requested_period_type)

    def _view_period(period_name: str, start: date, end: date) -> dict[str, Any]:
        return {
            "type": period_name,
            "label": requested_period_label if period_name == requested_period_type else _period_label(period_name),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "follow_until": follow_until.isoformat(),
        }

    def _matches_view_company(company: str, view_company: str) -> bool:
        return view_company == "ALL" or company == view_company

    def _entry_matches_view(entry: dict[str, Any], view_company: str, view_start: date, view_end: date) -> bool:
        received_date = entry.get("received_date")
        return (
            isinstance(received_date, date)
            and view_start <= received_date <= view_end
            and _matches_view_company(str(entry.get("company") or ""), view_company)
        )

    def _build_view_payload(
        view_only_consumed: bool,
        view_warnings: list[dict],
        *,
        view_company_filter: str,
        view_period_type: str,
        view_period_start: date,
        view_period_end: date,
        trace_detail: bool = True,
    ) -> dict:
        def _branch_matches_view(branch: TraceBranch) -> bool:
            return (
                branch.received_date is not None
                and view_period_start <= branch.received_date <= view_period_end
                and _matches_view_company(branch.company, view_company_filter)
            )

        nodes, links, processes, traced_summary, trace_rows = _finalize_sankey(
            branches,
            only_consumed=view_only_consumed,
            warnings=view_warnings,
            current_locations=current_locations,
            branch_predicate=_branch_matches_view,
            include_trace_details=trace_detail,
        )
        outbound = _build_outbound_sankey(
            pick_rows=pick_rows,
            dispatch_rows=dispatch_rows,
            alias_rows=alias_rows,
            prices=outbound_prices,
            allowed_companies=all_company_codes,
            view_company_filter=view_company_filter,
            view_period_start=view_period_start,
            view_period_end=view_period_end,
            include_trace_details=trace_detail,
        )

        view_receive_entries = [
            entry
            for entry in filtered_receives
            if _entry_matches_view(entry, view_company_filter, view_period_start, view_period_end)
        ]
        view_purchase_keys = {
            key
            for key in (_purchase_line_key(entry["row"]) for entry in view_receive_entries)
            if key is not None
        }
        view_purchase_lines_by_company: dict[str, int] = {}
        for company, _purchase, _line in view_purchase_keys:
            view_purchase_lines_by_company[company] = view_purchase_lines_by_company.get(company, 0) + 1

        company_summaries: dict[str, dict] = {}
        for branch in branches:
            if not branch.active or branch.revenue <= 0:
                continue
            if not _branch_matches_view(branch):
                continue
            if view_only_consumed and not branch.consumed:
                continue
            company = branch.company or "OKANT"
            row = company_summaries.setdefault(
                company,
                {
                    "company": company,
                    "gross_income": 0.0,
                    "gross_income_labels": 0.0,
                    "gross_income_purchase_lines": 0.0,
                    "labels": 0.0,
                    "purchase_lines": 0.0,
                    "consumed_labels": 0.0,
                    "open_labels": 0.0,
                },
            )
            row["gross_income"] += branch.revenue
            row["gross_income_labels"] += branch.label_revenue
            row["gross_income_purchase_lines"] += branch.purchase_line_revenue
            row["labels"] += branch.label_fraction
            if branch.consumed:
                row["consumed_labels"] += branch.label_fraction
            else:
                row["open_labels"] += branch.label_fraction

        for company, count in view_purchase_lines_by_company.items():
            if company not in company_summaries:
                continue
            company_summaries[company]["purchase_lines"] = count

        summary = {
            "gross_income": _round_money(traced_summary["gross_income"] + outbound["summary"]["outbound_income"]),
            "inbound_income": _round_money(traced_summary["gross_income"]),
            "gross_income_labels": _round_money(traced_summary["gross_income_labels"]),
            "gross_income_purchase_lines": _round_money(traced_summary["gross_income_purchase_lines"]),
            "labels_received": len(view_receive_entries),
            "purchase_lines_received": len(view_purchase_keys),
            "labels_traced": _round_qty(traced_summary["labels_traced"]),
            "labels_consumed": _round_qty(traced_summary["labels_consumed"]),
            "labels_open": _round_qty(traced_summary["labels_open"]),
            "branches": len([
                branch
                for branch in branches
                if branch.active
                and branch.revenue > 0
                and _branch_matches_view(branch)
                and (not view_only_consumed or branch.consumed)
            ]),
            "unallocated_revenue": _round_money(traced_summary["unallocated_revenue"]),
            "only_consumed": bool(view_only_consumed),
            **outbound["summary"],
        }
        companies = []
        for row in company_summaries.values():
            row["gross_income"] = _round_money(row["gross_income"])
            row["gross_income_labels"] = _round_money(row["gross_income_labels"])
            row["gross_income_purchase_lines"] = _round_money(row["gross_income_purchase_lines"])
            row["labels"] = _round_qty(row["labels"])
            row["purchase_lines"] = _round_qty(row["purchase_lines"])
            row["consumed_labels"] = _round_qty(row["consumed_labels"])
            row["open_labels"] = _round_qty(row["open_labels"])
            companies.append(row)
        companies_by_code = {row["company"]: row for row in companies}
        for outbound_company in outbound["companies"]:
            code = outbound_company["company"]
            row = companies_by_code.setdefault(
                code,
                {
                    "company": code,
                    "gross_income": 0.0,
                    "gross_income_labels": 0.0,
                    "gross_income_purchase_lines": 0.0,
                    "labels": 0.0,
                    "purchase_lines": 0.0,
                    "consumed_labels": 0.0,
                    "open_labels": 0.0,
                },
            )
            for key, value in outbound_company.items():
                if key != "company":
                    row[key] = value
        companies = list(companies_by_code.values())
        companies.sort(key=lambda item: item["company"])
        return {
            "summary": summary,
            "companies": companies,
            "nodes": [*nodes, *outbound["nodes"]],
            "links": [*links, *outbound["links"]],
            "processes": processes,
            "outbound_metrics": outbound["metrics"],
            "trace_rows": [*trace_rows, *outbound["trace_rows"]],
            "period": _view_period(view_period_type, view_period_start, view_period_end),
            "filters": {
                "company": view_company_filter,
                "only_consumed": bool(view_only_consumed),
            },
        }

    current_view_company = normalized_company_filter if normalized_company_filter and normalized_company_filter != "ALL" else "ALL"
    view_payload = _build_view_payload(
        bool(only_consumed),
        warnings_out,
        view_company_filter=current_view_company,
        view_period_type=requested_period_type,
        view_period_start=period_start,
        view_period_end=period_end,
        trace_detail=True,
    )
    available_companies = sorted({branch.company for branch in branches if branch.company} | set(all_company_codes))
    if current_view_company != "ALL":
        client_companies = [current_view_company]
    else:
        client_companies = ["ALL", *available_companies]
    client_period_specs = _client_filter_period_specs(
        requested_period_type,
        period_start,
        period_end,
    )
    source_row_count = sum(len(rows or []) for rows in source_rows.values())
    estimated_client_views = len(client_period_specs) * len(client_companies) * 2
    interactive_period = requested_period_type in {"day", "week", "month"}
    prebuild_client_filters = (
        (interactive_period or source_row_count <= CLIENT_FILTER_PREBUILD_MAX_SOURCE_ROWS)
        and estimated_client_views <= CLIENT_FILTER_PREBUILD_MAX_VIEWS
    )
    alternate_key = "all" if only_consumed else "only_consumed"
    alternate_payload = None
    if prebuild_client_filters:
        alternate_payload = _build_view_payload(
            not bool(only_consumed),
            list(warnings_out),
            view_company_filter=current_view_company,
            view_period_type=requested_period_type,
            view_period_start=period_start,
            view_period_end=period_end,
            trace_detail=bool(only_consumed),
        )

    client_views: dict[str, dict] = {}
    if prebuild_client_filters:
        for view_period_type, view_period_start, view_period_end in client_period_specs:
            for view_company in client_companies:
                for view_only_consumed in (False, True):
                    key = _client_filter_view_key(view_period_type, view_period_start, view_company, view_only_consumed)
                    if key in client_views:
                        continue
                    client_views[key] = _build_view_payload(
                        view_only_consumed,
                        list(warnings_out),
                        view_company_filter=view_company,
                        view_period_type=view_period_type,
                        view_period_start=view_period_start,
                        view_period_end=view_period_end,
                        trace_detail=False,
                    )

    unique_warnings: list[dict] = []
    seen_warnings: set[tuple] = set()
    for warning in warnings_out:
        key = (
            warning.get("code"),
            warning.get("company"),
            warning.get("process_key"),
            warning.get("origin_id"),
            warning.get("message"),
        )
        if key in seen_warnings:
            continue
        seen_warnings.add(key)
        unique_warnings.append(warning)

    client_filters = {
        "schema": "views_v1",
        "views": client_views,
        "prebuilt": prebuild_client_filters,
        "estimated_views": estimated_client_views,
        "source_rows": source_row_count,
    }
    if alternate_payload is not None:
        client_filters[alternate_key] = alternate_payload
    if not prebuild_client_filters:
        client_filters["omitted_reason"] = "too_many_views" if estimated_client_views > CLIENT_FILTER_PREBUILD_MAX_VIEWS else "large_payload"

    return {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "period": _view_period(requested_period_type, period_start, period_end),
        "filters": {
            "company": current_view_company,
            "only_consumed": bool(only_consumed),
        },
        "schema_version": SANKEY_INBOUND_PAYLOAD_SCHEMA,
        "currency": "SEK",
        **view_payload,
        "client_filters": client_filters,
        "warnings": unique_warnings[:100],
        "source_status": list(source_status or []),
    }


def _api_client(tenant: str | None = None) -> ExternalDataClient:
    missing = [
        name
        for name in (
            "DATA_SOURCE_API_BASE_URL",
            "DATA_SOURCE_API_KEY",
            "DATA_SOURCE_API_CLIENT",
            "DATA_SOURCE_API_KEY_HEADER",
            "DATA_SOURCE_API_CLIENT_HEADER",
            "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE",
        )
        if not str(getattr(settings, name, "")).strip()
    ]
    if missing:
        raise SankeyInboundError(f"Saknar {', '.join(missing)} i servermiljon.", status_code=503)
    try:
        base_url = data_source_base_url_for_tenant(settings.DATA_SOURCE_API_BASE_URL, tenant)
    except ValueError as exc:
        raise SankeyInboundError(str(exc), status_code=503) from exc
    return ExternalDataClient(
        base_url=base_url,
        api_key=settings.DATA_SOURCE_API_KEY.strip() or None,
        api_client=settings.DATA_SOURCE_API_CLIENT.strip() or None,
        api_key_header=settings.DATA_SOURCE_API_KEY_HEADER.strip() or None,
        api_client_header=settings.DATA_SOURCE_API_CLIENT_HEADER.strip() or None,
        view_data_path_template=settings.DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE.strip(),
        timeout=settings.DATA_SOURCE_TIMEOUT_SECONDS,
        verify_ssl=settings.DATA_SOURCE_VERIFY_SSL,
        ca_bundle=settings.DATA_SOURCE_CA_BUNDLE.strip() or None,
        response_row_cap=int(getattr(settings, "DATA_SOURCE_RESPONSE_ROW_CAP", 0) or 0),
    )


def _company_filter(company_filter: str | None, company_codes: list[str]) -> list[dict[str, Any]]:
    company = clean_productivity_finance_company_code(company_filter)
    if company and company != "ALL":
        return [{"id": "company", "operator": "EQ", "value": company}]
    codes = [clean_productivity_finance_company_code(code) for code in company_codes]
    codes = [code for code in codes if code]
    if len(codes) == 1:
        return [{"id": "company", "operator": "EQ", "value": codes[0]}]
    if len(codes) > 1:
        return [{"id": "company", "operator": "Terms", "value": codes}]
    return []


def _date_filter_for_view(view_id: str, period_start: date, period_end: date) -> dict[str, Any] | None:
    try:
        view = load_catalog().view(view_id)
    except (DataFetchConfigError, DataFetchPlanError):
        return None
    column = _preferred_date_column(view)
    if column is None:
        return None
    period = _date_period_payload("sankey", period_start, period_end)
    return {"id": column.id, "operator": "Between", "value": _period_values_for_column(period, column)}


def _segments_for_view(view_id: str, period_start: date, period_end: date, today: date) -> tuple[list[tuple[str, date, date]], list[dict]]:
    if view_id not in LIVE_ARCHIVE_PAIRS:
        return [(view_id, period_start, period_end)], []
    days, archive_id = LIVE_ARCHIVE_PAIRS[view_id]
    cutoff = today - timedelta(days=days)
    warnings = []
    if period_start >= cutoff:
        return [(view_id, period_start, period_end)], warnings
    warnings.append(
        {
            "code": "archive_retention_used",
            "view": view_id,
            "archive_view": archive_id,
            "message": f"{view_id} använder dblog-arkiv före {cutoff.isoformat()}.",
        }
    )
    if period_end < cutoff:
        return [(archive_id, period_start, period_end)], warnings
    return [
        (archive_id, period_start, cutoff - timedelta(days=1)),
        (view_id, cutoff, period_end),
    ], warnings


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _segment_kind(segment_view: str) -> str:
    return "arkiv" if segment_view in ARCHIVE_TO_LIVE else "live"


def _fetch_segment_rows(
    client: ExternalDataClient,
    *,
    segment_view: str,
    segment_start: date | None,
    segment_end: date | None,
    company_codes: list[str],
    company_filter: str | None,
    tenant: str | None = None,
) -> list[dict[str, Any]]:
    rows, _source = _fetch_segment_rows_with_source(
        client,
        segment_view=segment_view,
        segment_start=segment_start,
        segment_end=segment_end,
        company_codes=company_codes,
        company_filter=company_filter,
        tenant=tenant,
    )
    return rows


def _fetch_segment_rows_with_source(
    client: ExternalDataClient,
    *,
    segment_view: str,
    segment_start: date | None,
    segment_end: date | None,
    company_codes: list[str],
    company_filter: str | None,
    tenant: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    filters = _company_filter(company_filter, company_codes)
    if segment_start and segment_end:
        date_filter = _date_filter_for_view(segment_view, segment_start, segment_end)
        if date_filter:
            filters.append(date_filter)
    # Lokal arkiv-cache först för dblog-segment; None => fall tillbaka till API/dblog.
    if segment_view in ARCHIVE_TO_LIVE and local_archive_store.is_enabled():
        try:
            cached = local_archive_store.query_rows(tenant, segment_view, filters or None)
        except Exception:  # noqa: BLE001 – cache-fel får aldrig fälla Sankey
            logger.warning("Lokal arkiv-cache misslyckades för %s, faller tillbaka.", segment_view, exc_info=True)
            cached = None
        if cached is not None:
            return cached, "local_archive"
    return client.fetch_all(segment_view, filters=filters or None), "api"


def _query_local_archive_segment(
    *,
    archive_view: str,
    segment_start: date,
    segment_end: date,
    company_codes: list[str],
    company_filter: str | None,
    tenant: str | None = None,
) -> list[dict[str, Any]] | None:
    if not local_archive_store.is_enabled() or archive_view not in ARCHIVE_TO_LIVE:
        return None
    filters = _company_filter(company_filter, company_codes)
    date_filter = _date_filter_for_view(archive_view, segment_start, segment_end)
    if date_filter:
        filters.append(date_filter)
    try:
        return local_archive_store.query_rows(tenant, archive_view, filters or None)
    except Exception:  # noqa: BLE001 – cache-fel får aldrig fälla Sankey
        logger.warning("Lokal arkiv-cache misslyckades för %s, faller tillbaka.", archive_view, exc_info=True)
        return None


def _date_span(start: date, end: date) -> list[date]:
    if start > end:
        return []
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _fetch_productivity_snapshot_rows(
    *,
    key: str,
    view_id: str,
    period_start: date,
    period_end: date,
) -> tuple[list[dict[str, Any]], list[dict], list[dict]] | None:
    if key not in PRODUCTIVITY_SNAPSHOT_REUSE_SOURCE_KEYS:
        return None
    days = _date_span(period_start, period_end)
    if not days:
        return None

    paths = []
    for day in days:
        status = productivity_snapshot_status(day)
        if not status.get("ready"):
            return None
        path = productivity_snapshot_source_path(day, key)
        if not path.is_file():
            return None
        paths.append((day, path))

    rows: list[dict[str, Any]] = []
    try:
        for _day, path in paths:
            _headers, day_rows = _read_csv_rows_with_headers(path, compressed=True)
            rows.extend(dict(row) for row in day_rows)
    except Exception:
        logger.warning("Could not reuse productivity snapshot rows for Sankey source %s.", key, exc_info=True)
        return None

    return (
        rows,
        [
            {
                "key": key,
                "view": view_id,
                "segment": "productivity_snapshot",
                "status": "productivity_snapshot",
                "rows": len(rows),
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "days": len(days),
            }
        ],
        [],
    )


def _source_failure_message(
    *,
    key: str,
    view: str,
    kind: str,
    start: date | None,
    end: date | None,
    company_filter: str | None,
    exc: Exception,
    archive_view: str | None = None,
    archive_exc: Exception | None = None,
) -> str:
    label = SOURCE_LABELS.get(key, key)
    span = f"{start.isoformat()}–{end.isoformat()}" if start and end else "hela perioden"
    company = clean_productivity_finance_company_code(company_filter) or "ALLA"
    detail = f"{label} ({key}) kunde inte hämtas — vy {view} [{kind}], period {span}, bolag {company}: {exc}"
    if archive_view is not None and archive_exc is not None:
        detail += f" · arkivet {archive_view} svarade också: {archive_exc}"
    return detail


def _degraded_source_warning(*, key: str, view: str, message: str) -> dict[str, Any]:
    return {
        "code": "degraded_source_segment_unavailable",
        "source": key,
        "view": view,
        "message": (
            f"{message}. Rapporten fortsätter med tillgängliga segment, "
            "men förverkade/plockade grenar kan vara underskattade."
        ),
    }


def _fetch_snapshot_rows(
    client: ExternalDataClient,
    *,
    key: str,
    view_id: str,
    company_codes: list[str],
    company_filter: str | None,
    tenant: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict], list[dict]]:
    """Hämtar en datumlös nulägeskälla (buffer/saldo/kpi).

    Sådana vyer kan inte datum-chunkas. Om svaret slår i radtaket delar vi per bolag
    så att vi inte tyst tappar rader (t.ex. buffertpall som kapas vid 50 000).
    """
    cap = int(getattr(settings, "DATA_SOURCE_RESPONSE_ROW_CAP", 0) or 0)
    rows = _fetch_segment_rows(
        client, segment_view=view_id, segment_start=None, segment_end=None,
        company_codes=company_codes, company_filter=company_filter,
    )
    if not cap or len(rows) < cap:
        return rows, [{"key": key, "view": view_id, "segment": "snapshot", "status": "api", "rows": len(rows)}], []

    cleaned_filter = clean_productivity_finance_company_code(company_filter)
    if cleaned_filter and cleaned_filter != "ALL":
        codes = [cleaned_filter]
    else:
        codes = [c for c in (clean_productivity_finance_company_code(x) for x in company_codes) if c]
    statuses: list[dict] = []
    warnings: list[dict] = []
    if len(codes) > 1:
        combined: list[dict[str, Any]] = []
        for code in codes:
            part = _fetch_segment_rows(
                client, segment_view=view_id, segment_start=None, segment_end=None,
                company_codes=[code], company_filter=code,
            )
            statuses.append({"key": key, "view": view_id, "segment": f"snapshot:{code}", "status": "api", "rows": len(part)})
            combined.extend(part)
            if cap and len(part) >= cap:
                warnings.append({
                    "code": "snapshot_truncated", "source": key, "view": view_id, "company": code,
                    "message": f"{SOURCE_LABELS.get(key, key)} för {code} nådde fortfarande radtaket ({cap}) och kan vara ofullständig.",
                })
        warnings.insert(0, {
            "code": "snapshot_chunked_by_company", "source": key, "view": view_id,
            "message": f"{SOURCE_LABELS.get(key, key)} nådde radtaket ({cap}) – hämtade per bolag istället ({len(combined)} rader totalt).",
        })
        logger.warning("Sankey snapshot %s nådde radtaket %d – chunkade per bolag till %d rader.", key, cap, len(combined))
        return combined, statuses, warnings

    # Ett enda bolag som ändå slår i taket – inget mer att dela på.
    warnings.append({
        "code": "snapshot_truncated", "source": key, "view": view_id,
        "message": f"{SOURCE_LABELS.get(key, key)} nådde radtaket ({cap}) utan datum- eller bolagsaxel att dela på och kan vara ofullständig.",
    })
    logger.warning("Sankey snapshot %s nådde radtaket %d och kunde inte delas.", key, cap)
    return rows, [{"key": key, "view": view_id, "segment": "snapshot", "status": "api", "rows": len(rows), "truncated": True}], warnings


def _fetch_item_alias_rows(
    client: ExternalDataClient,
    *,
    view_id: str,
    company_codes: list[str],
    company_filter: str | None,
    tenant: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict], list[dict]]:
    """Hämta item_alias fullständigt trots datakällans radtak.

    item_alias är en nulägeskälla utan datumaxel i Sankey, men vyn har en timestamp-
    kolumn (utan tomma värden). Ett brett timestamp-Between låter ``fetch_all`` dela ner
    under radtaket – annars kapas svaret vid ~50k/bolag och faktorer tappas, vilket ger
    fel förpacknings-ladders. Ingen bolagschunkning behövs då.
    """
    filters = _company_filter(company_filter, company_codes)
    if local_archive_store.is_enabled():
        try:
            cached = local_archive_store.query_snapshot_rows(tenant, view_id, filters or None)
        except Exception:  # noqa: BLE001 - cache faults must not break Sankey
            logger.warning("Lokal snapshot-cache misslyckades för %s, faller tillbaka.", view_id, exc_info=True)
            cached = None
        if cached is not None:
            status = [{
                "key": "item_alias",
                "view": view_id,
                "segment": "snapshot",
                "status": "local_snapshot",
                "rows": len(cached),
            }]
            return cached, status, []
    date_filter = _date_filter_for_view(view_id, date(2000, 1, 1), date.today())
    if date_filter:
        filters.append(date_filter)
    rows = client.fetch_all(view_id, filters=filters or None)
    status = [{"key": "item_alias", "view": view_id, "segment": "timestamp-split", "status": "api", "rows": len(rows)}]
    return rows, status, []


def _fetch_view_rows(
    client: ExternalDataClient,
    *,
    key: str,
    view_id: str,
    period_start: date | None,
    period_end: date | None,
    company_codes: list[str],
    company_filter: str | None,
    today: date,
    tenant: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict], list[dict]]:
    rows: list[dict[str, Any]] = []
    statuses: list[dict] = []
    warnings: list[dict] = []
    company = clean_productivity_finance_company_code(company_filter) or "ALLA"
    if not (period_start and period_end):
        # Datumlös nulägeskälla – egen väg med bolagschunkning vid radtak.
        try:
            if key == "item_alias":
                # item_alias är för stor för bolagschunkning (>50k/bolag) – timestamp-split
                # istället så inga omräkningsfaktorer kapas bort.
                return _fetch_item_alias_rows(
                    client, view_id=view_id, company_codes=company_codes, company_filter=company_filter, tenant=tenant,
                )
            return _fetch_snapshot_rows(
                client, key=key, view_id=view_id, company_codes=company_codes, company_filter=company_filter,
            )
        except ExternalDataClientError as exc:
            message = _source_failure_message(
                key=key, view=view_id, kind="snapshot", start=None, end=None,
                company_filter=company_filter, exc=exc,
            )
            statuses.append({"key": key, "view": view_id, "segment": "snapshot", "status": "error", "rows": 0, "company": company, "message": message})
            logger.error("Sankey-källa misslyckades: %s", message)
            if key in REQUIRED_SOURCE_KEYS:
                raise SankeyInboundError(message, status_code=502, source_status=statuses) from exc
            warnings.append({"code": "optional_source_unavailable", "source": key, "view": view_id, "message": message})
            return rows, statuses, warnings
    if period_start and period_end:
        reused = _fetch_productivity_snapshot_rows(
            key=key,
            view_id=view_id,
            period_start=period_start,
            period_end=period_end,
        )
        if reused is not None:
            return reused
        segments, warnings = _segments_for_view(view_id, period_start, period_end, today)
    else:
        segments = [(view_id, None, None)]
    for segment_view, segment_start, segment_end in segments:
        kind = _segment_kind(segment_view)
        fetch_start = segment_start
        if (
            segment_view in LIVE_ARCHIVE_PAIRS
            and segment_start is not None
            and segment_end is not None
            and local_archive_store.is_enabled()
        ):
            archive_view = LIVE_ARCHIVE_PAIRS[segment_view][1]
            min_cached, max_cached = local_archive_store.covered_range(tenant, archive_view)
            if min_cached is not None and max_cached is not None and min_cached <= segment_start <= max_cached:
                cached_end = min(segment_end, max_cached)
                cached_rows = _query_local_archive_segment(
                    archive_view=archive_view,
                    segment_start=segment_start,
                    segment_end=cached_end,
                    company_codes=company_codes,
                    company_filter=company_filter,
                    tenant=tenant,
                )
                if cached_rows is not None:
                    rows.extend(cached_rows)
                    statuses.append({
                        "key": key,
                        "view": archive_view,
                        "live_view": segment_view,
                        "segment": "lokal_cache",
                        "status": "local_archive",
                        "rows": len(cached_rows),
                        "start": _iso(segment_start),
                        "end": _iso(cached_end),
                    })
                    fetch_start = cached_end + timedelta(days=1)
                    if fetch_start > segment_end:
                        continue
        try:
            segment_rows, segment_source = _fetch_segment_rows_with_source(
                client,
                segment_view=segment_view,
                segment_start=fetch_start,
                segment_end=segment_end,
                company_codes=company_codes,
                company_filter=company_filter,
                tenant=tenant,
            )
        except ExternalDataClientError as exc:
            archive_pair = LIVE_ARCHIVE_PAIRS.get(segment_view)
            # Live-vyn svarade inte (t.ex. kortare faktisk retention än konfigurerat,
            # eller 403 på äldre data) – prova dblog-arkivet innan vi ger upp.
            if archive_pair is not None:
                archive_view = archive_pair[1]
                logger.warning(
                    "Sankey-källa '%s': live-vy %s misslyckades (%s) för %s–%s bolag %s – provar arkiv %s.",
                    key, segment_view, exc, _iso(segment_start), _iso(segment_end), company, archive_view,
                )
                try:
                    segment_rows, segment_source = _fetch_segment_rows_with_source(
                        client,
                        segment_view=archive_view,
                        segment_start=fetch_start,
                        segment_end=segment_end,
                        company_codes=company_codes,
                        company_filter=company_filter,
                        tenant=tenant,
                    )
                except ExternalDataClientError as archive_exc:
                    message = _source_failure_message(
                        key=key, view=segment_view, kind=kind, start=fetch_start, end=segment_end,
                        company_filter=company_filter, exc=exc, archive_view=archive_view, archive_exc=archive_exc,
                    )
                    statuses.append({
                        "key": key, "view": segment_view, "archive_view": archive_view, "segment": kind,
                        "status": "error", "rows": 0, "start": _iso(fetch_start), "end": _iso(segment_end),
                        "company": company, "message": message,
                    })
                    logger.error("Sankey-källa misslyckades (även arkiv): %s", message)
                    if key in REQUIRED_SOURCE_KEYS:
                        if key in DEGRADABLE_SOURCE_KEYS:
                            warnings.append(_degraded_source_warning(key=key, view=segment_view, message=message))
                            continue
                        raise SankeyInboundError(message, status_code=502, source_status=statuses) from archive_exc
                    warnings.append({"code": "optional_source_unavailable", "source": key, "view": segment_view, "message": message})
                    continue
                fallback_message = (
                    f"{SOURCE_LABELS.get(key, key)}: live-vyn {segment_view} svarade '{exc}'. "
                    f"Hämtade {len(segment_rows)} rader från arkivet {archive_view} istället."
                )
                warnings.append({
                    "code": "archive_fallback_used", "source": key, "view": segment_view,
                    "archive_view": archive_view, "message": fallback_message,
                })
                statuses.append({
                    "key": key, "view": archive_view, "segment": "arkiv (fallback)", "status": segment_source,
                    "rows": len(segment_rows), "start": _iso(fetch_start), "end": _iso(segment_end),
                })
                logger.warning("Sankey-källa '%s': arkiv-fallback via %s lyckades (%d rader).", key, archive_view, len(segment_rows))
                rows.extend(segment_rows)
                continue
            # Ingen arkivpartner – misslyckas direkt, men med full kontext.
            message = _source_failure_message(
                key=key, view=segment_view, kind=kind, start=fetch_start, end=segment_end,
                company_filter=company_filter, exc=exc,
            )
            statuses.append({
                "key": key, "view": segment_view, "segment": kind, "status": "error", "rows": 0,
                "start": _iso(fetch_start), "end": _iso(segment_end), "company": company, "message": message,
            })
            logger.error("Sankey-källa misslyckades: %s", message)
            if key in REQUIRED_SOURCE_KEYS:
                if key in DEGRADABLE_SOURCE_KEYS:
                    warnings.append(_degraded_source_warning(key=key, view=segment_view, message=message))
                    continue
                raise SankeyInboundError(message, status_code=502, source_status=statuses) from exc
            warnings.append({"code": "optional_source_unavailable", "source": key, "view": segment_view, "message": message})
            continue
        rows.extend(segment_rows)
        statuses.append({
            "key": key, "view": segment_view, "segment": kind, "status": segment_source,
            "rows": len(segment_rows), "start": _iso(fetch_start), "end": _iso(segment_end),
        })
    return rows, statuses, warnings


def _load_kpi_fallback_rows(
    *,
    business_code: str | None,
    db: Any = None,
) -> tuple[list[dict[str, Any]], list[dict], list[dict]]:
    """Läs KPI-mål från Produktivitetens coredata-fil.

    Sankey använder coredata som förstahandskälla eftersom v_ask_kpi_target inte
    är en tillgänglig API-källa i detta flöde. Det speglar Produktivitetens
    fallbackfil så processpoängen hålls gemensamma.
    """
    try:
        path = find_kpi_file(None, business_code or DEFAULT_BUSINESS_CODE, db=db)
        rows = [dict(row) for row in _read_csv(path)]
    except (ProductivitySourceError, OSError):
        return [], [], []
    if not rows:
        return [], [], []
    status = [
        {
            "key": "kpi",
            "view": SANKEY_SOURCE_VIEWS["kpi"],
            "status": "coredata_primary",
            "rows": len(rows),
        }
    ]
    warning = [
        {
            "code": "kpi_coredata_fallback",
            "source": "kpi",
            "message": f"{SOURCE_LABELS['kpi']} hämtades från Produktivitetens coredata-fil.",
        }
    ]
    return rows, status, warning


def fetch_sankey_inbound_sources(
    *,
    period_start: date,
    period_end: date | None = None,
    follow_until: date,
    company_codes: list[str],
    company_filter: str | None = None,
    tenant: str | None = None,
    business_code: str | None = None,
    db: Any = None,
    progress_callback: ProgressCallback | None = None,
    total_steps: int | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict], list[dict]]:
    try:
        load_catalog()
    except DataFetchConfigError as exc:
        raise SankeyInboundError(str(exc), status_code=503) from exc
    except DataFetchPlanError as exc:
        raise SankeyInboundError(str(exc), status_code=503) from exc
    all_rows: dict[str, list[dict[str, Any]]] = {}
    source_status: list[dict] = []
    warnings: list[dict] = []
    today = date.today()
    total = total_steps or (len(SANKEY_SOURCE_VIEWS) + 1)
    steps = {key: index for index, key in enumerate(SANKEY_SOURCE_VIEWS, start=1)}

    def _fetch_source(key: str, view_id: str) -> tuple[str, list[dict[str, Any]], list[dict], list[dict]]:
        is_current = key in CURRENT_STATE_SOURCE_KEYS
        _emit_progress(progress_callback, step=steps[key], total=total, key=key, label=f"Hämtar {SOURCE_LABELS.get(key, key)}")
        started = time.perf_counter()
        if key == "kpi":
            rows, statuses, source_warnings = _load_kpi_fallback_rows(business_code=business_code, db=db)
            if not statuses:
                statuses = [{"key": key, "view": view_id, "status": "coredata_missing", "rows": 0}]
                source_warnings = [
                    {
                        "code": "kpi_coredata_missing",
                        "source": "kpi",
                        "message": f"{SOURCE_LABELS['kpi']} saknas i Produktivitetens coredata-fil.",
                    }
                ]
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            for status in statuses:
                status.setdefault("ms", elapsed_ms)
            _emit_progress(progress_callback, step=steps[key], total=total, key=key, label=f"{SOURCE_LABELS.get(key, key)} klar", rows=len(rows), done=True, ms=elapsed_ms)
            return key, rows, statuses, source_warnings
        client = _api_client(tenant=tenant)
        source_period_end = period_end if key in PERIOD_ONLY_SOURCE_KEYS and period_end is not None else follow_until
        rows, statuses, source_warnings = _fetch_view_rows(
            client,
            key=key,
            view_id=view_id,
            period_start=None if is_current else period_start,
            period_end=None if is_current else source_period_end,
            company_codes=company_codes,
            company_filter=company_filter,
            today=today,
            tenant=tenant,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        for status in statuses:
            status.setdefault("ms", elapsed_ms)
        _emit_progress(progress_callback, step=steps[key], total=total, key=key, label=f"{SOURCE_LABELS.get(key, key)} klar", rows=len(rows), done=True, ms=elapsed_ms)
        return key, rows, statuses, source_warnings

    # Loggkällorna (receive/trans/pick) är oberoende och tunga – hämta dem parallellt.
    # Nulägeskällorna (buffer/kpi) körs sekventiellt eftersom kpi-fallbacken rör DB-sessionen.
    parallel_views = [(k, v) for k, v in SANKEY_SOURCE_VIEWS.items() if k not in CURRENT_STATE_SOURCE_KEYS]
    sequential_views = [(k, v) for k, v in SANKEY_SOURCE_VIEWS.items() if k in CURRENT_STATE_SOURCE_KEYS]
    results: dict[str, tuple[list[dict[str, Any]], list[dict], list[dict]]] = {}
    required_error: SankeyInboundError | None = None

    if parallel_views:
        with ThreadPoolExecutor(max_workers=min(4, len(parallel_views)), thread_name_prefix="sankey-fetch") as pool:
            futures = {pool.submit(_fetch_source, key, view_id): key for key, view_id in parallel_views}
            for future in as_completed(futures):
                try:
                    key, rows, statuses, source_warnings = future.result()
                    results[key] = (rows, statuses, source_warnings)
                except SankeyInboundError as exc:
                    required_error = required_error or exc
    if required_error is not None:
        raise required_error

    for key, view_id in sequential_views:
        _, rows, statuses, source_warnings = _fetch_source(key, view_id)
        results[key] = (rows, statuses, source_warnings)

    for key in SANKEY_SOURCE_VIEWS:
        rows, statuses, source_warnings = results[key]
        all_rows[key] = rows
        source_status.extend(statuses)
        warnings.extend(source_warnings)

    warnings.append(
        {
            "code": "pick_location_log_retention",
            "message": "Plockplatsloggen har begransad historik och saknar kvantitet; aldre saldo-FIFO markeras med lagre confidence.",
        }
    )
    return all_rows, source_status, warnings


def _cache_key(
    *,
    business_id: int | None,
    period: str,
    selected_date: date,
    company_filter: str | None,
    only_consumed: bool,
    company_codes: list[str],
    tenant: str | None,
) -> tuple[Any, ...]:
    return (
        SANKEY_INBOUND_PAYLOAD_SCHEMA,
        business_id,
        str(period or "day").lower(),
        selected_date.isoformat(),
        clean_productivity_finance_company_code(company_filter) or "ALL",
        bool(only_consumed),
        tuple(sorted(clean_productivity_finance_company_code(code) for code in company_codes)),
        tenant or "",
    )


def get_cached_sankey_payload(key: tuple[Any, ...]) -> dict | None:
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if not cached:
            return None
        expires_at, payload = cached
        if expires_at <= now:
            _CACHE.pop(key, None)
            return None
        return payload


def set_cached_sankey_payload(key: tuple[Any, ...], payload: dict) -> None:
    now = time.time()
    with _CACHE_LOCK:
        _CACHE[key] = (now + _CACHE_TTL_SECONDS, payload)
        if len(_CACHE) <= _CACHE_MAX_ITEMS:
            return
        for stale_key, (expires_at, _payload) in sorted(_CACHE.items(), key=lambda item: item[1][0])[: len(_CACHE) - _CACHE_MAX_ITEMS]:
            _CACHE.pop(stale_key, None)


def _source_cache_key(
    *,
    business_id: int | None,
    period: str,
    selected_date: date,
    company_filter: str | None,
    company_codes: list[str],
    tenant: str | None,
) -> tuple[Any, ...]:
    # Medvetet utan only_consumed: samma rader hämtas oavsett filtret.
    return (
        SANKEY_INBOUND_PAYLOAD_SCHEMA,
        business_id,
        str(period or "day").lower(),
        selected_date.isoformat(),
        clean_productivity_finance_company_code(company_filter) or "ALL",
        tuple(sorted(clean_productivity_finance_company_code(code) for code in company_codes)),
        tenant or "",
    )


def _get_cached_sankey_sources(key: tuple[Any, ...]) -> tuple[dict, list, list] | None:
    now = time.time()
    with _SOURCE_CACHE_LOCK:
        cached = _SOURCE_CACHE.get(key)
        if not cached:
            return None
        expires_at, value = cached
        if expires_at <= now:
            _SOURCE_CACHE.pop(key, None)
            return None
        return value


def _set_cached_sankey_sources(key: tuple[Any, ...], value: tuple[dict, list, list]) -> None:
    now = time.time()
    with _SOURCE_CACHE_LOCK:
        _SOURCE_CACHE[key] = (now + _SOURCE_CACHE_TTL_SECONDS, value)
        if len(_SOURCE_CACHE) <= _SOURCE_CACHE_MAX_ITEMS:
            return
        for stale_key, (expires_at, _value) in sorted(_SOURCE_CACHE.items(), key=lambda item: item[1][0])[: len(_SOURCE_CACHE) - _SOURCE_CACHE_MAX_ITEMS]:
            _SOURCE_CACHE.pop(stale_key, None)


def _trace_filter_for_payload(payload: dict) -> dict[str, Any]:
    period = payload.get("period") if isinstance(payload.get("period"), dict) else {}
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    company = clean_productivity_finance_company_code(filters.get("company")) or "ALL"
    return {
        "company": company,
        "start_date": period.get("start_date"),
        "end_date": period.get("end_date"),
        "only_consumed": bool(filters.get("only_consumed")),
    }


def _set_trace_metadata(payload: dict, trace_rows: list[dict[str, Any]], token: str) -> None:
    payload["trace_total"] = len(trace_rows)
    payload["trace_counts"] = compute_trace_counts(trace_rows)
    payload["trace_filter"] = _trace_filter_for_payload(payload)
    payload["trace_token"] = token


def _client_filter_payloads(payload: dict):
    client_filters = payload.get("client_filters")
    if not isinstance(client_filters, dict):
        return
    for key in ("all", "only_consumed"):
        variant = client_filters.get(key)
        if isinstance(variant, dict):
            yield variant
    views = client_filters.get("views")
    if isinstance(views, dict):
        for variant in views.values():
            if isinstance(variant, dict):
                yield variant


def _attach_trace_token(payload: dict) -> None:
    """Flytta trace_rows från payloaden till server-side cache; lämna token + antal kvar.

    Håller huvud-payloaden liten (kraschar aldrig fliken); frontend lazy-laddar raderna
    per nod/länk via /inbound/trace och exporterar via /inbound/trace.csv.
    """
    trace_rows = payload.pop("trace_rows", None) or []
    token_rows = trace_rows
    client_filters = payload.get("client_filters")
    all_variant = client_filters.get("all") if isinstance(client_filters, dict) else None
    if isinstance(all_variant, dict) and all_variant.get("trace_rows") is not None:
        token_rows = all_variant.get("trace_rows") or []
    token = store_trace_rows(token_rows)
    _set_trace_metadata(payload, trace_rows, token)
    for variant in _client_filter_payloads(payload) or ():
        variant_rows = variant.pop("trace_rows", None) or []
        _set_trace_metadata(variant, variant_rows, token)


def load_sankey_inbound_payload(
    *,
    finance_settings: dict,
    company_codes: list[str],
    period: str,
    selected_date: date,
    business_id: int | None = None,
    business_code: str | None = None,
    company_filter: str | None = None,
    only_consumed: bool = False,
    tenant: str | None = None,
    db: Any = None,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    period_start, period_end, period_label = sankey_period_bounds(period, selected_date)
    today = date.today()
    if period_end > today:
        period_end = today
    if period_start > period_end:
        period_start = period_end
    cache_key = _cache_key(
        business_id=business_id,
        period=period,
        selected_date=selected_date,
        company_filter=company_filter,
        only_consumed=only_consumed,
        company_codes=company_codes,
        tenant=tenant,
    )
    cached = get_cached_sankey_payload(cache_key)
    if cached:
        return {**cached, "cache": {"status": "hit", "ttl_seconds": _CACHE_TTL_SECONDS}}
    total_steps = len(SANKEY_SOURCE_VIEWS) + 1
    source_key = _source_cache_key(
        business_id=business_id,
        period=period,
        selected_date=selected_date,
        company_filter=company_filter,
        company_codes=company_codes,
        tenant=tenant,
    )
    cached_sources = _get_cached_sankey_sources(source_key)
    fetch_started = time.perf_counter()
    sources_cached = cached_sources is not None
    if cached_sources is not None:
        # Källraderna finns redan – bara efterfiltret (only_consumed) skiljer.
        # Hoppa över hämtningen och gå direkt till bygget.
        source_rows, source_status, warnings = cached_sources
        warnings = list(warnings)
    else:
        source_rows, source_status, warnings = fetch_sankey_inbound_sources(
            period_start=period_start,
            period_end=period_end,
            follow_until=today,
            company_codes=company_codes,
            company_filter=company_filter,
            tenant=tenant,
            business_code=business_code,
            db=db,
            progress_callback=progress_callback,
            total_steps=total_steps,
        )
        _set_cached_sankey_sources(source_key, (source_rows, source_status, list(warnings)))
    fetch_ms = round((time.perf_counter() - fetch_started) * 1000, 1)
    _emit_progress(
        progress_callback,
        step=total_steps,
        total=total_steps,
        key="build",
        label="Bygger flöde",
    )
    build_started = time.perf_counter()
    payload = build_sankey_inbound_payload(
        source_rows=source_rows,
        finance_settings=finance_settings,
        company_codes=company_codes,
        period_start=period_start,
        period_end=period_end,
        follow_until=today,
        period_type=str(period or "day").strip().lower(),
        period_label=period_label,
        company_filter=company_filter,
        only_consumed=only_consumed,
        source_status=source_status,
        warnings=warnings,
    )
    build_ms = round((time.perf_counter() - build_started) * 1000, 1)
    payload["period"]["type"] = str(period or "day").strip().lower()
    payload["period"]["label"] = period_label
    payload["date"] = selected_date.isoformat()
    payload["cache"] = {"status": "miss", "ttl_seconds": _CACHE_TTL_SECONDS}
    timing = {
        "fetch_ms": fetch_ms,
        "build_ms": build_ms,
        "total_ms": round(fetch_ms + build_ms, 1),
        "sources_cached": sources_cached,
        "rows_by_source": {key: len(rows or []) for key, rows in source_rows.items()},
        "sources": [
            {"key": item.get("key"), "view": item.get("view"), "segment": item.get("segment"), "rows": item.get("rows"), "ms": item.get("ms")}
            for item in source_status
            if isinstance(item, dict)
        ],
    }
    payload["timing"] = timing
    logger.info(
        "Sankey inbound klar: period=%s datum=%s bolag=%s only_consumed=%s fetch=%sms build=%sms total=%sms cache=%s rader=%s",
        period, selected_date.isoformat(), clean_productivity_finance_company_code(company_filter) or "ALLA",
        only_consumed, fetch_ms, build_ms, timing["total_ms"], sources_cached, timing["rows_by_source"],
    )
    _attach_trace_token(payload)
    set_cached_sankey_payload(cache_key, payload)
    return payload

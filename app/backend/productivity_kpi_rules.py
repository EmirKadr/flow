from __future__ import annotations

import gzip
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .home_activity import build_home_activity_resolver
from .models import Activity, Area, Person, ScheduleCell
from .productivity_service import (
    HOURS,
    SOURCE_SPECS,
    SOURCE_SPEC_BY_KEY,
    ProductivitySourceError,
    _detect_dialect,
    _format_size,
    _get,
    _number,
    _source_payload,
    _timestamp,
)
from .template_service import get_template_hours_map_for_dates


METRIC_TARGET_COLUMNS = {
    "rows": ("Rader", "rows"),
    "packages": ("Kollin", "Kolli", "package", "packages"),
    "pallets": ("Pallar", "pallets"),
    "orders": ("Order", "orders"),
}

METRIC_POINT_COLUMNS = {
    "rows": ("PoÃ¤ng rader", "Poang rader", "PoÃƒÂ¤ng rader", "loaded_rows"),
    "packages": ("PoÃ¤ng kolli", "Poang kolli", "PoÃƒÂ¤ng kolli", "loaded_packages"),
    "pallets": ("PoÃ¤ng pallar", "Poang pallar", "PoÃƒÂ¤ng pallar", "loaded_pallets"),
    "orders": ("PoÃ¤ng order", "Poang order", "PoÃƒÂ¤ng order", "loaded_orders"),
}

EVENT_DATE_SOURCE_KEYS = {"pick", "trans", "pallet", "receive", "order_log", "sort"}
KPI_LOGIC_SOURCE_KEY = "kpi_sql"
KPI_LOGIC_SOURCE_LABEL = "KPI-logik"


SQL_REFERENCE_KPI_RULE_ROWS: tuple[dict[str, str], ...] = (
    {"flow": "OUTBOUND", "process": "Manual_Pick", "source": "pick", "metric": "rows", "zone": "A", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Manual_Pick", "source": "pick", "metric": "packages", "zone": "A", "positive_column": "Plockat", "value_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "E_Commerce", "source": "pick", "metric": "rows", "zone": "E", "exclude_company": "MG", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "E_Commerce", "source": "pick", "metric": "packages", "zone": "E", "exclude_company": "MG", "positive_column": "Plockat", "value_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "E_Commerce", "source": "pick", "metric": "rows", "company": "MG", "zone": "Q", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "E_Commerce", "source": "pick", "metric": "packages", "company": "MG", "zone": "Q", "positive_column": "Plockat", "value_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Chair_Zone", "source": "pick", "metric": "rows", "zone": "G", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Chair_Zone", "source": "pick", "metric": "packages", "zone": "G", "positive_column": "Plockat", "value_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Bulky_Pick", "source": "pick", "metric": "rows", "zone": "S", "exclude_company": "MG", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Bulky_Pick", "source": "pick", "metric": "packages", "zone": "S", "exclude_company": "MG", "positive_column": "Plockat", "value_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Bulky_Pick", "source": "pick", "metric": "rows", "company": "MG", "zone": "O", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Bulky_Pick", "source": "pick", "metric": "packages", "company": "MG", "zone": "O", "positive_column": "Plockat", "value_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Marble", "source": "pick", "metric": "rows", "zone": "Q", "exclude_company": "MG", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Marble", "source": "pick", "metric": "packages", "zone": "Q", "exclude_company": "MG", "positive_column": "Plockat", "value_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Autostore", "source": "pick", "metric": "rows", "zone": "R", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Autostore", "source": "pick", "metric": "packages", "zone": "R", "positive_column": "Plockat", "value_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Outdoor_Furniture", "source": "pick", "metric": "rows", "zone": "U", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Outdoor_Furniture", "source": "pick", "metric": "packages", "zone": "U", "positive_column": "Plockat", "value_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Small_Pick", "source": "pick", "metric": "rows", "zone": "Z", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Small_Pick", "source": "pick", "metric": "packages", "zone": "Z", "positive_column": "Plockat", "value_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Flammable", "source": "pick", "metric": "rows", "zone": "F", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Flammable", "source": "pick", "metric": "packages", "zone": "F", "positive_column": "Plockat", "value_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Full_Pallet_From_HBW", "source": "pick", "metric": "pallets", "zone": "H", "location_starts": "UT", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Full_Manual_Buffer", "source": "pick", "metric": "pallets", "zone": "H", "location_not_starts": "UT", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Sort_Ecom", "source": "sort", "metric": "pallets", "sscc_length_lt": "12"},
    {"flow": "OUTBOUND", "process": "Sort_Store", "source": "sort", "metric": "pallets", "sscc_length_gte": "12"},
    {"flow": "OUTBOUND", "process": "Ecom_Pack", "source": "pallet", "metric": "pallets", "type": "220", "distinct_key": "Plockpallsnr.;Pallid;pall_num"},
    {"flow": "OUTBOUND", "process": "Campaign", "source": "pick", "metric": "rows", "company": "GG", "zone": "K", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Campaign", "source": "pick", "metric": "packages", "company": "GG", "zone": "K", "positive_column": "Plockat", "value_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Order_Split", "source": "pick", "metric": "rows", "company": "GG", "zone": "B", "positive_column": "Plockat"},
    {"flow": "OUTBOUND", "process": "Order_Split", "source": "pick", "metric": "packages", "company": "GG", "zone": "B", "positive_column": "Plockat", "value_column": "Plockat"},
    {"flow": "INTERNT", "process": "Refill_Manual_HBW", "source": "trans", "metric": "pallets", "type": "31;51", "loc_from_starts": "AA"},
    {"flow": "INTERNT", "process": "Refill_Manual_HBW", "source": "trans", "metric": "pallets", "type": "31;51", "loc_from_equals": "Transit"},
    {"flow": "INTERNT", "process": "Refill_Manual_HBW", "source": "trans", "metric": "pallets", "type": "31;51", "loc_from_starts": "UT"},
    {"flow": "INTERNT", "process": "Refill_Manual_Rack", "source": "trans", "metric": "pallets", "type": "31", "loc_from_not_starts": "AA;UT", "loc_from_not_equals": "Transit"},
    {"flow": "INTERNT", "process": "Buffer_Update", "source": "receive", "metric": "pallets", "type": "91"},
    {"flow": "INBOUND", "process": "Decanting", "source": "trans", "metric": "packages", "type": "26", "loc_to_starts": "AS", "value_column": "Antal"},
    {"flow": "INBOUND", "process": "Decanting", "source": "trans", "metric": "rows", "type": "26", "loc_to_starts": "AS"},
    {"flow": "INBOUND", "process": "HBW", "source": "trans", "metric": "pallets", "type": "111", "loc_to_starts": "HBW", "distinct_key": "Pallid;pall_num;Pall Num"},
    {"flow": "INBOUND", "process": "Manual_Buffer", "source": "trans", "metric": "pallets", "type": "22", "exclude_trans_type_66_pall": "1"},
    {"flow": "INBOUND", "process": "Putaway_Pick", "source": "trans", "metric": "pallets", "type": "21;27;29"},
    {"flow": "INBOUND", "process": "Receiving", "source": "receive", "metric": "rows", "type": "11;12;61;62;71", "status": "20;30"},
)

@dataclass(frozen=True)
class KpiTarget:
    company: str
    warehouse: str
    process: str
    description: str
    targets: dict[str, float] = field(default_factory=dict)
    points: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class KpiLogEvent:
    source: str
    user: str
    company: str
    warehouse: str
    timestamp: datetime
    row: dict[str, str]
    row_index: int


@dataclass(frozen=True)
class KpiPointEvent:
    user: str
    user_key: str
    company: str
    warehouse: str
    process: str
    process_key: str
    metric: str
    value: float
    points: float
    timestamp: datetime
    source: str
    rule_key: str


@dataclass(frozen=True)
class KpiRule:
    process: str
    metric: str
    source: str
    sql_key: str
    predicate: Callable[[KpiLogEvent, dict[str, Any]], bool]
    value: Callable[[KpiLogEvent, dict[str, Any]], float] = lambda _event, _context: 1.0
    distinct_key: Callable[[KpiLogEvent, dict[str, Any]], str] | None = None
    company_override: str | None = None

    @property
    def process_key(self) -> str:
        return normalize_process(self.process)


def normalize_process(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_name(value: Any) -> str:
    return str(value or "").strip().casefold()


def split_process_names(value: str | None) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in str(value or "").split(","):
        name = item.strip()
        key = normalize_process(name)
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _canonical_header(value: Any) -> str:
    text = str(value or "").strip().lstrip("\ufeff")
    if "Ãƒ" in text:
        try:
            text = text.encode("latin1").decode("utf-8")
        except UnicodeError:
            pass
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _row_text(row: dict[str, str], *names: str) -> str:
    direct = _get(row, *names)
    if direct:
        return direct
    aliases = {_canonical_header(name) for name in names}
    for header, value in row.items():
        if _canonical_header(header) in aliases:
            return str(value or "").strip()
    return ""


def _row_number(row: dict[str, str], *names: str) -> float:
    return _number(_row_text(row, *names))


def _row_upper(row: dict[str, str], *names: str) -> str:
    return _row_text(row, *names).upper()


def _row_int_text(row: dict[str, str], *names: str) -> str:
    value = _row_text(row, *names)
    try:
        number = float(str(value).replace(",", "."))
    except ValueError:
        return value.strip()
    return str(int(number)) if number.is_integer() else value.strip()


def _company(event: KpiLogEvent) -> str:
    return event.company.strip().upper()


def _warehouse(event: KpiLogEvent) -> str:
    return event.warehouse.strip().upper()


def _one(_event: KpiLogEvent, _context: dict[str, Any]) -> float:
    return 1.0


def _pall_num(event: KpiLogEvent, _context: dict[str, Any]) -> str:
    return _row_text(event.row, "Pallid", "pall_num", "Pall Num")


def _sort_company(event: KpiLogEvent) -> str:
    if event.company:
        return event.company
    parts = _row_text(event.row, "SÃ¤ndningsnr", "Sandningsnr", "shipment_id").split("-")
    return parts[0] if len(parts) >= 3 else ""


def _sort_warehouse(event: KpiLogEvent) -> str:
    if event.warehouse:
        return event.warehouse
    parts = _row_text(event.row, "SÃ¤ndningsnr", "Sandningsnr", "shipment_id").split("-")
    return parts[1] if len(parts) >= 3 else ""


RULE_METRIC_ALIASES = {
    "rows": "rows",
    "row": "rows",
    "rader": "rows",
    "packages": "packages",
    "package": "packages",
    "kolli": "packages",
    "kollin": "packages",
    "pallets": "pallets",
    "pallet": "pallets",
    "pallar": "pallets",
    "pall": "pallets",
    "orders": "orders",
    "order": "orders",
}

RULE_SOURCE_ALIASES = {
    "pick": "pick",
    "plock": "pick",
    "trans": "trans",
    "transport": "trans",
    "pallet": "pallet",
    "pall": "pallet",
    "pallastning": "pallet",
    "receive": "receive",
    "receiving": "receive",
    "mottag": "receive",
    "varumottagning": "receive",
    "sort": "sort",
    "sortering": "sort",
    "order_log": "order_log",
    "orderlog": "order_log",
    "base_pallet": "base_pallet",
}


def _split_rule_values(value: Any) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text:
        return ()
    return tuple(part.strip() for part in re.split(r"[;,|]", text) if part.strip())


def _upper_values(value: Any) -> set[str]:
    return {part.upper() for part in _split_rule_values(value)}


def _rule_bool(row: dict[str, str], *names: str) -> bool:
    text = _row_text(row, *names).strip().casefold()
    return text in {"1", "true", "yes", "ja", "x", "y"}


def _normalize_rule_metric(value: Any) -> str:
    key = str(value or "").strip().casefold()
    return RULE_METRIC_ALIASES.get(key, key)


def _normalize_rule_source(value: Any) -> str:
    key = str(value or "").strip().casefold()
    return RULE_SOURCE_ALIASES.get(key, key)


def _row_config_value(row: dict[str, str], *names: str) -> str:
    return _row_text(row, *names).strip()


def _starts_any(value: str, prefixes: Iterable[str]) -> bool:
    upper = str(value or "").upper()
    return any(upper.startswith(prefix.upper()) for prefix in prefixes)


def _column_value_getter(column_config: str) -> Callable[[KpiLogEvent, dict[str, Any]], float]:
    columns = _split_rule_values(column_config)

    def value(event: KpiLogEvent, _context: dict[str, Any]) -> float:
        return _row_number(event.row, *columns)

    return value


def _distinct_key_getter(column_config: str) -> Callable[[KpiLogEvent, dict[str, Any]], str]:
    columns = _split_rule_values(column_config)

    def value(event: KpiLogEvent, context: dict[str, Any]) -> str:
        if any(column.casefold() == "pall_num" for column in columns):
            return _pall_num(event, context)
        return _row_text(event.row, *columns)

    return value


def _rule_value_getter(row: dict[str, str]) -> Callable[[KpiLogEvent, dict[str, Any]], float]:
    value_column = _row_config_value(row, "value_column", "VÃ¤rdekolumn", "Vardekolumn", "value_from")
    if value_column:
        return _column_value_getter(value_column)
    constant = _row_config_value(row, "value", "constant_value", "Konstant vÃ¤rde", "Konstant varde")
    if constant:
        amount = _number(constant)
        return lambda _event, _context: amount
    return _one


def _rule_predicate(row: dict[str, str]) -> Callable[[KpiLogEvent, dict[str, Any]], bool]:
    company_values = _upper_values(_row_config_value(row, "company", "Bolag"))
    exclude_company_values = _upper_values(_row_config_value(row, "exclude_company", "Exkludera bolag"))
    zones = _upper_values(_row_config_value(row, "zone", "Zon", "pick_zone"))
    types = _upper_values(_row_config_value(row, "type", "Typ"))
    statuses = _upper_values(_row_config_value(row, "status", "Status"))
    loc_from_equals = _upper_values(_row_config_value(row, "loc_from_equals", "FrÃ¥n Ã¤r", "Fran ar"))
    loc_from_not_equals = _upper_values(_row_config_value(row, "loc_from_not_equals", "FrÃ¥n Ã¤r inte", "Fran ar inte"))
    loc_to_equals = _upper_values(_row_config_value(row, "loc_to_equals", "Till Ã¤r", "Till ar"))
    loc_to_not_equals = _upper_values(_row_config_value(row, "loc_to_not_equals", "Till Ã¤r inte", "Till ar inte"))
    loc_from_starts = _split_rule_values(_row_config_value(row, "loc_from_starts", "FrÃ¥n startar med", "Fran startar med"))
    loc_from_not_starts = _split_rule_values(_row_config_value(row, "loc_from_not_starts", "FrÃ¥n startar inte med", "Fran startar inte med"))
    loc_to_starts = _split_rule_values(_row_config_value(row, "loc_to_starts", "Till startar med"))
    loc_to_not_starts = _split_rule_values(_row_config_value(row, "loc_to_not_starts", "Till startar inte med"))
    location_starts = _split_rule_values(_row_config_value(row, "location_starts", "Lokation startar med"))
    location_not_starts = _split_rule_values(_row_config_value(row, "location_not_starts", "Lokation startar inte med"))
    positive_columns = _split_rule_values(_row_config_value(row, "positive_column", "Positiv kolumn"))
    sscc_length_lt = _number(_row_config_value(row, "sscc_length_lt", "SSCC lÃ¤ngd under", "SSCC langd under"))
    sscc_length_gte = _number(_row_config_value(row, "sscc_length_gte", "SSCC lÃ¤ngd minst", "SSCC langd minst"))
    exclude_trans_type_66_pall = _rule_bool(
        row,
        "exclude_trans_type_66_pall",
        "exclude_type_66_pall",
        "Exkludera trans typ 66 pall",
    )

    def predicate(event: KpiLogEvent, context: dict[str, Any]) -> bool:
        if company_values and _company(event) not in company_values:
            return False
        if exclude_company_values and _company(event) in exclude_company_values:
            return False
        if zones and _row_upper(event.row, "Zon", "pick_zone") not in zones:
            return False
        if types and _row_int_text(event.row, "Typ", "type").upper() not in types:
            return False
        if statuses and _row_int_text(event.row, "Status", "status").upper() not in statuses:
            return False
        loc_from = _row_text(event.row, "FrÃ¥n", "Fran", "loc_from")
        loc_to = _row_text(event.row, "Till", "loc_to")
        location = _row_text(event.row, "Lokation", "Lagerplats", "location")
        if loc_from_equals and loc_from.upper() not in loc_from_equals:
            return False
        if loc_from_not_equals and loc_from.upper() in loc_from_not_equals:
            return False
        if loc_to_equals and loc_to.upper() not in loc_to_equals:
            return False
        if loc_to_not_equals and loc_to.upper() in loc_to_not_equals:
            return False
        if loc_from_starts and not _starts_any(loc_from, loc_from_starts):
            return False
        if loc_from_not_starts and _starts_any(loc_from, loc_from_not_starts):
            return False
        if loc_to_starts and not _starts_any(loc_to, loc_to_starts):
            return False
        if loc_to_not_starts and _starts_any(loc_to, loc_to_not_starts):
            return False
        if location_starts and not _starts_any(location, location_starts):
            return False
        if location_not_starts and _starts_any(location, location_not_starts):
            return False
        if positive_columns and any(_row_number(event.row, column) <= 0 for column in positive_columns):
            return False
        sscc = _row_text(event.row, "SSCC", "sscc")
        if sscc_length_lt > 0 and len(sscc) >= int(sscc_length_lt):
            return False
        if sscc_length_gte > 0 and len(sscc) < int(sscc_length_gte):
            return False
        if exclude_trans_type_66_pall and _pall_num(event, context) in context.get("trans_type_66_pall_nums", set()):
            return False
        return True

    return predicate


def parse_kpi_rule_rows(rows: list[dict[str, str]]) -> tuple[KpiRule, ...]:
    rules: list[KpiRule] = []
    for index, row in enumerate(rows, start=1):
        process = _row_config_value(row, "Processnamn", "process", "action_id")
        source = _normalize_rule_source(_row_config_value(row, "source", "KÃ¤lla", "Kalla", "Logg"))
        metric = _normalize_rule_metric(_row_config_value(row, "metric", "MÃ¥tt", "Matt", "Enhet"))
        if not source and not metric:
            continue
        if not process or not source or not metric:
            raise ProductivitySourceError(f"KPI-mÃ¥lregel rad {index} saknar process, kÃ¤lla eller mÃ¥tt.")
        if metric not in METRIC_TARGET_COLUMNS:
            raise ProductivitySourceError(f"KPI-mÃ¥lregel rad {index} har okÃ¤nt mÃ¥tt: {metric}")
        if source not in SOURCE_SPEC_BY_KEY:
            raise ProductivitySourceError(f"KPI-mÃ¥lregel rad {index} har okÃ¤nd kÃ¤lla: {source}")
        sql_key = _row_config_value(row, "sql_key", "rule_key", "Regelnyckel")
        if not sql_key:
            flow = _row_config_value(row, "FlÃ¶desnamn", "Flodesnamn", "flow", "flow_name")
            sql_key = "_".join(part for part in (flow, process, metric, source, str(index)) if part)
        distinct_column = _row_config_value(row, "distinct_key", "distinct_column", "Unik kolumn")
        rules.append(
            KpiRule(
                process=process,
                metric=metric,
                source=source,
                sql_key=sql_key,
                predicate=_rule_predicate(row),
                value=_rule_value_getter(row),
                distinct_key=_distinct_key_getter(distinct_column) if distinct_column else None,
            )
        )
    return tuple(rules)


def rules_by_process(rules: Iterable[KpiRule]) -> dict[str, list[KpiRule]]:
    result: dict[str, list[KpiRule]] = defaultdict(list)
    for rule in rules:
        result[rule.process_key].append(rule)
    return result


def kpi_rule_contract(rules: Iterable[KpiRule] | None = None) -> list[dict[str, str]]:
    return [
        {
            "process": rule.process,
            "metric": rule.metric,
            "source": rule.source,
            "sql_key": rule.sql_key,
        }
        for rule in (rules or ())
    ]


def _sql_reference_kpi_rule_source() -> dict[str, Any]:
    return {
        "key": KPI_LOGIC_SOURCE_KEY,
        "label": KPI_LOGIC_SOURCE_LABEL,
        "required": False,
        "visible": False,
        "uploaded": False,
        "name": "referens/kpi.sql",
        "path": "referens/kpi.sql",
        "rows": len(SQL_REFERENCE_KPI_RULE_ROWS),
        "modified_at": None,
        "size": None,
        "size_label": None,
        "status": "internal",
        "kind": "internal",
        "message": "KPI-mal kommer fran v_ask_kpi_target; logik for hur loggar raknas kommer fran referens/kpi.sql.",
    }
def load_kpi_rules(
    db: Session,
    *,
    business_id: int | None = None,
    files: dict[str, Path] | None = None,
    allow_empty: bool = False,
) -> tuple[tuple[KpiRule, ...], dict[str, Any]]:
    rules = parse_kpi_rule_rows([dict(row) for row in SQL_REFERENCE_KPI_RULE_ROWS])
    if not rules:
        if not allow_empty:
            raise ProductivitySourceError("Saknar intern KPI-logik fran referens/kpi.sql.")
        return (), _sql_reference_kpi_rule_source()
    return rules, _sql_reference_kpi_rule_source()


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        dialect = _detect_dialect(sample)
        import csv

        reader = csv.DictReader(handle, dialect=dialect)
        headers = [str(header or "").strip().lstrip("\ufeff") for header in (reader.fieldnames or [])]
        rows: list[dict[str, str]] = []
        for row in reader:
            cleaned = {
                str(header or "").strip().lstrip("\ufeff"): "" if value is None else str(value)
                for header, value in row.items()
                if header is not None
            }
            if any(value.strip() for value in cleaned.values()):
                rows.append(cleaned)
        return headers, rows


def _status_payload_for_path(key: str, path: Path, rows: int) -> dict[str, Any]:
    spec = SOURCE_SPEC_BY_KEY.get(key)
    if spec is not None:
        payload = _source_payload(spec, path, rows)
    else:
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone()
        payload = {
            "key": key,
            "label": key,
            "visible": True,
            "name": path.name,
            "path": str(path),
            "rows": rows,
            "modified_at": modified.isoformat(timespec="seconds"),
        }
    payload["size"] = path.stat().st_size
    payload["size_label"] = _format_size(path.stat().st_size)
    return payload


def parse_kpi_targets(rows: list[dict[str, str]]) -> dict[tuple[str, str], KpiTarget]:
    targets: dict[tuple[str, str], KpiTarget] = {}
    for row in rows:
        company = _row_text(row, "Bolag", "company").strip().upper()
        process = _row_text(row, "Processnamn", "action_id").strip()
        process_key = normalize_process(process)
        if not company or not process_key:
            continue
        metric_targets: dict[str, float] = {}
        metric_points: dict[str, float] = {}
        for metric, aliases in METRIC_TARGET_COLUMNS.items():
            metric_targets[metric] = _row_number(row, *aliases)
        for metric, aliases in METRIC_POINT_COLUMNS.items():
            metric_points[metric] = _row_number(row, *aliases)
            if metric_points[metric] <= 0 and metric_targets.get(metric, 0) > 0:
                metric_points[metric] = 100.0 / metric_targets[metric]
        targets[(company, process_key)] = KpiTarget(
            company=company,
            warehouse=_row_text(row, "Lager", "wareh_num"),
            process=process.strip(),
            description=_row_text(row, "Beskrivning", "description"),
            targets=metric_targets,
            points=metric_points,
        )
    return targets


def _event_user(row: dict[str, str], source: str) -> str:
    if source == "sort":
        return _row_text(row, "AnvÃ¤ndare", "Anvandare", "username", "user_id")
    return _row_text(row, "AnvÃ¤ndare", "Anvandare", "user_id")


def _event_timestamp(row: dict[str, str], source: str) -> datetime | None:
    if source in {"pick", "pallet"}:
        return _timestamp(_row_text(row, "Ã„ndrad", "Andrad", "timestamp"))
    return _timestamp(_row_text(row, "Timestamp", "timestamp", "Ã„ndrad", "Andrad"))


def _event_company(row: dict[str, str], source: str) -> str:
    if source == "sort":
        event = KpiLogEvent(source, "", "", "", datetime.now(), row, 0)
        return _sort_company(event)
    return _row_text(row, "Bolag", "company").strip().upper()


def _event_warehouse(row: dict[str, str], source: str) -> str:
    if source == "sort":
        event = KpiLogEvent(source, "", "", "", datetime.now(), row, 0)
        return _sort_warehouse(event)
    return _row_text(row, "Lager", "wareh_num").strip().upper()


def _events_from_rows(source: str, rows: list[dict[str, str]], report_date: date) -> list[KpiLogEvent]:
    events: list[KpiLogEvent] = []
    for index, row in enumerate(rows):
        user = _event_user(row, source)
        timestamp = _event_timestamp(row, source)
        if not user or timestamp is None or timestamp.date() != report_date:
            continue
        event = KpiLogEvent(
            source=source,
            user=user.strip(),
            company=_event_company(row, source),
            warehouse=_event_warehouse(row, source),
            timestamp=timestamp,
            row=row,
            row_index=index,
        )
        if event.company:
            events.append(event)
    return events


def _rule_applies_for_target(rule: KpiRule, event: KpiLogEvent, targets: dict[tuple[str, str], KpiTarget]) -> KpiTarget | None:
    process_key = rule.process_key
    return targets.get((_company(event), process_key))


def _rule_context(events_by_source: dict[str, list[KpiLogEvent]]) -> dict[str, Any]:
    trans_events = events_by_source.get("trans", [])
    type_66_pall_nums = {
        _pall_num(event, {})
        for event in trans_events
        if _row_int_text(event.row, "Typ", "type") == "66" and _pall_num(event, {})
    }
    return {"trans_type_66_pall_nums": type_66_pall_nums}


def score_kpi_events(
    *,
    rows_by_source: dict[str, list[dict[str, str]]],
    targets: dict[tuple[str, str], KpiTarget],
    rules: Iterable[KpiRule],
    report_date: date,
) -> tuple[list[KpiPointEvent], dict[str, Any]]:
    rules = tuple(rules)
    rule_map = rules_by_process(rules)
    events_by_source = {
        source: _events_from_rows(source, rows, report_date)
        for source, rows in rows_by_source.items()
        if source in EVENT_DATE_SOURCE_KEYS
    }
    context = _rule_context(events_by_source)
    scored: list[KpiPointEvent] = []
    seen_distinct: set[tuple[str, str, str, str, str]] = set()
    missing_rule_processes = sorted(
        {
            target.process
            for (_company_key, process_key), target in targets.items()
            if process_key not in rule_map
        },
        key=str.upper,
    )

    for rule in rules:
        for event in events_by_source.get(rule.source, []):
            if rule.company_override and _company(event) != rule.company_override.upper():
                continue
            target = _rule_applies_for_target(rule, event, targets)
            if target is None:
                continue
            if not rule.predicate(event, context):
                continue
            if rule.distinct_key is not None:
                distinct_value = rule.distinct_key(event, context)
                if not distinct_value:
                    continue
                distinct_key = (_company(event), _warehouse(event), rule.process_key, rule.metric, distinct_value)
                if distinct_key in seen_distinct:
                    continue
                seen_distinct.add(distinct_key)
            value = float(rule.value(event, context) or 0)
            point_per_unit = float(target.points.get(rule.metric) or 0)
            points = value * point_per_unit
            if value <= 0 or points <= 0:
                continue
            scored.append(
                KpiPointEvent(
                    user=event.user,
                    user_key=normalize_name(event.user),
                    company=_company(event),
                    warehouse=_warehouse(event),
                    process=target.process or rule.process,
                    process_key=rule.process_key,
                    metric=rule.metric,
                    value=value,
                    points=points,
                    timestamp=event.timestamp,
                    source=event.source,
                    rule_key=rule.sql_key,
                )
            )

    return scored, {
        "missing_rule_processes": missing_rule_processes,
        "rules": len(rules),
    }


def _minute_of_day(hour: int, minute: int) -> int:
    return int(hour) * 60 + int(minute)


def _time_label(minute_of_day: int) -> str:
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def _covered_intervals(cells: list[ScheduleCell]) -> list[tuple[int, int]]:
    intervals = sorted(
        (
            max(0, int(cell.minute_start)),
            min(60, int(cell.minute_end)),
        )
        for cell in cells
        if cell.activity_id is not None or cell.empty_override
    )
    merged: list[tuple[int, int]] = []
    for start, end in intervals:
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _uncovered_intervals(covered: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    cursor = 0
    for start, end in covered:
        if start > cursor:
            result.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < 60:
        result.append((cursor, 60))
    return result


def _segment_kind(activity: Activity | None, processes: list[str], source: str) -> str:
    process_keys = {normalize_process(process) for process in processes}
    if activity is not None and activity.category == "absence":
        return "absence"
    if "ABSENCE" in process_keys:
        return "absence"
    if source == "off":
        return "off"
    if not process_keys or process_keys & {"STOD", "STÃ–D", "SUPPORT"}:
        return "support"
    return "kpi"


def _segment_display(activity: Activity | None, processes: list[str], kind: str) -> str:
    if kind == "absence":
        return "absence"
    if kind == "support":
        return "STÃ–D"
    if kind == "off":
        return "Ledig"
    return ", ".join(processes) or (activity.label if activity is not None else "KPI")


def _activity_segment(
    *,
    hour: int,
    start: int,
    end: int,
    activity: Activity | None,
    source: str,
) -> dict[str, Any]:
    processes = split_process_names(getattr(activity, "kpi_process_name", None))
    kind = _segment_kind(activity, processes, source)
    start_minute = _minute_of_day(hour, start)
    end_minute = _minute_of_day(hour, end)
    area = getattr(activity, "area", None) if activity is not None else None
    return {
        "activity_id": getattr(activity, "id", None),
        "activity_label": getattr(activity, "label", None) or "OkÃ¤nd aktivitet",
        "activity_area_id": getattr(activity, "area_id", None),
        "activity_area_code": getattr(area, "code", None),
        "activity_area_name": getattr(area, "name", None),
        "category": getattr(activity, "category", None),
        "kind": kind,
        "display": _segment_display(activity, processes, kind),
        "processes": processes,
        "process_keys": [normalize_process(process) for process in processes],
        "start": _time_label(start_minute),
        "end": _time_label(end_minute),
        "start_minute": start_minute,
        "end_minute": end_minute,
        "minutes": max(0, end_minute - start_minute),
        "source": source,
        "color": getattr(activity, "color", None),
    }


def _off_segment(hour: int, start: int, end: int) -> dict[str, Any]:
    start_minute = _minute_of_day(hour, start)
    end_minute = _minute_of_day(hour, end)
    return {
        "activity_id": None,
        "activity_label": "Ledig",
        "category": None,
        "kind": "off",
        "display": "Ledig",
        "processes": [],
        "process_keys": [],
        "start": _time_label(start_minute),
        "end": _time_label(end_minute),
        "start_minute": start_minute,
        "end_minute": end_minute,
        "minutes": max(0, end_minute - start_minute),
        "source": "off",
        "color": None,
    }


def _merge_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for segment in sorted(segments, key=lambda item: (item["start_minute"], item["end_minute"], item["display"])):
        if segment["minutes"] <= 0 or segment["kind"] == "off":
            continue
        if (
            merged
            and merged[-1]["end_minute"] == segment["start_minute"]
            and merged[-1]["activity_id"] == segment["activity_id"]
            and merged[-1]["kind"] == segment["kind"]
            and merged[-1]["process_keys"] == segment["process_keys"]
        ):
            merged[-1]["end_minute"] = segment["end_minute"]
            merged[-1]["end"] = segment["end"]
            merged[-1]["minutes"] += segment["minutes"]
        else:
            merged.append(dict(segment))
    return merged


def _find_segment(segments: list[dict[str, Any]], timestamp: datetime) -> dict[str, Any] | None:
    minute = timestamp.hour * 60 + timestamp.minute
    return next((segment for segment in segments if segment["start_minute"] <= minute < segment["end_minute"]), None)


def _event_matches_segment(event: KpiPointEvent, segment: dict[str, Any] | None) -> bool:
    if not segment or segment.get("kind") != "kpi":
        return False
    expected_keys = {normalize_process(process) for process in (segment.get("processes") or [])}
    return event.process_key in expected_keys


def _event_should_warn_as_diff(event: KpiPointEvent, segment: dict[str, Any] | None) -> bool:
    if segment is not None and segment.get("kind") != "kpi":
        return False
    return not _event_matches_segment(event, segment)


def _segment_time_cells(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for segment in segments:
        start = int(segment.get("start_minute") or 0)
        end = int(segment.get("end_minute") or 0)
        current = start
        while current < end:
            next_hour = ((current // 60) + 1) * 60
            cell_end = min(end, next_hour if next_hour > current else current + 60)
            cells.append(
                {
                    "hour": current // 60,
                    "minute_start": current % 60,
                    "minute_end": cell_end % 60 if cell_end % 60 else 60,
                    "start": _time_label(current),
                    "end": _time_label(cell_end),
                    "start_minute": current,
                    "end_minute": cell_end,
                    "minutes": max(0, cell_end - current),
                    "kind": segment.get("kind"),
                    "display": segment.get("display"),
                    "activity_id": segment.get("activity_id"),
                    "activity_label": segment.get("activity_label"),
                    "activity_area_id": segment.get("activity_area_id"),
                    "activity_area_code": segment.get("activity_area_code"),
                    "activity_area_name": segment.get("activity_area_name"),
                    "points": 0.0,
                    "expected_points": round(((cell_end - current) / 60.0) * 100.0, 2)
                    if segment.get("kind") == "kpi"
                    else 0.0,
                    "event_count": 0,
                    "diff_count": 0,
                    "diffs": [],
                    "_process_points": {},
                }
            )
            current = cell_end
    return cells


def _build_time_cells(segments: list[dict[str, Any]], events: list[KpiPointEvent]) -> list[dict[str, Any]]:
    cells = _segment_time_cells(segments)
    for event in events:
        minute = event.timestamp.hour * 60 + event.timestamp.minute
        cell = next((item for item in cells if item["start_minute"] <= minute < item["end_minute"]), None)
        if cell is None:
            continue
        segment = _find_segment(segments, event.timestamp)
        cell["points"] += event.points
        cell["event_count"] += 1
        process_label = event.process or "OkÃ¤nd process"
        process_points = cell["_process_points"].setdefault(
            process_label,
            {"process": process_label, "points": 0.0, "event_count": 0},
        )
        process_points["points"] += event.points
        process_points["event_count"] += 1
        if _event_should_warn_as_diff(event, segment):
            cell["diff_count"] += 1
            cell["diffs"].append(
                {
                    "time": event.timestamp.isoformat(timespec="minutes"),
                    "scheduled_display": segment.get("display") if segment else "Ej schemalagd",
                    "actual_process": event.process,
                    "company": event.company,
                    "points": round(event.points, 2),
                }
            )
    return [
        {
            **{key: value for key, value in cell.items() if key != "_process_points"},
            "points": round(float(cell["points"]), 2),
            "score_pct": (
                round((float(cell["points"]) / float(cell["expected_points"])) * 100.0, 1)
                if float(cell.get("expected_points") or 0) > 0
                else None
            ),
            "score_status": (
                "low"
                if float(cell.get("expected_points") or 0) > 0
                and (float(cell["points"]) / float(cell["expected_points"])) * 100.0 < 80
                else "warn"
                if float(cell.get("expected_points") or 0) > 0
                and (float(cell["points"]) / float(cell["expected_points"])) * 100.0 < 100
                else "good"
                if float(cell.get("expected_points") or 0) > 0
                else None
            ),
            "process_points": [
                {
                    "process": payload["process"],
                    "points": round(float(payload["points"]), 2),
                    "event_count": int(payload["event_count"]),
                }
                for payload in sorted(
                    cell["_process_points"].values(),
                    key=lambda item: str(item["process"]).upper(),
                )
            ],
        }
        for cell in cells
    ]


def _planned_process_status(
    segments: list[dict[str, Any]],
    targets: dict[tuple[str, str], KpiTarget],
    rule_map: dict[str, list[KpiRule]],
) -> tuple[list[str], list[str]]:
    missing_targets: set[str] = set()
    missing_rules: set[str] = set()
    target_process_keys = {process_key for _company, process_key in targets}
    for segment in segments:
        if segment["kind"] != "kpi":
            continue
        for process in segment["processes"]:
            process_key = normalize_process(process)
            if process_key not in target_process_keys:
                missing_targets.add(process)
            if process_key not in rule_map:
                missing_rules.add(process)
    return sorted(missing_targets, key=str.upper), sorted(missing_rules, key=str.upper)


def build_schedule_segments(
    db: Session,
    report_date: date,
    *,
    business_id: int | None,
) -> dict[int, dict[str, Any]]:
    persons_query = (
        select(Person)
        .where(
            Person.is_active.is_(True),
            func.trim(func.coalesce(Person.noman, "")) != "",
        )
        .order_by(Person.sort_order, Person.name)
    )
    activities_query = select(Activity).where(Activity.is_active.is_(True)).order_by(Activity.sort_order, Activity.label)
    areas_query = select(Area).where(Area.is_active.is_(True)).order_by(Area.sort_order, Area.name)
    if business_id is not None:
        persons_query = persons_query.where(Person.business_id == business_id)
        activities_query = activities_query.where(Activity.business_id == business_id)
        areas_query = areas_query.where(Area.business_id == business_id)

    persons = db.execute(persons_query).scalars().all()
    activities = db.execute(activities_query).scalars().all()
    areas = db.execute(areas_query).scalars().all()
    activities_by_id = {activity.id: activity for activity in activities}
    home_activity_for = build_home_activity_resolver(activities, areas)
    person_ids = [person.id for person in persons]
    iso = report_date.isocalendar()
    template_hours_map = get_template_hours_map_for_dates(db, person_ids, [report_date])

    cells_by_person_hour: dict[tuple[int, int], list[ScheduleCell]] = defaultdict(list)
    if person_ids:
        cells = db.execute(
            select(ScheduleCell).where(
                ScheduleCell.year == iso.year,
                ScheduleCell.week == iso.week,
                ScheduleCell.weekday == iso.weekday,
                ScheduleCell.person_id.in_(person_ids),
            )
        ).scalars().all()
        for cell in cells:
            cells_by_person_hour[(cell.person_id, cell.hour)].append(cell)

    result: dict[int, dict[str, Any]] = {}
    for person in persons:
        segments: list[dict[str, Any]] = []
        home_activity_id = home_activity_for(person)
        template_hours = template_hours_map.get((person.id, report_date))
        for hour in HOURS:
            hour_cells = sorted(cells_by_person_hour.get((person.id, hour), []), key=lambda cell: (cell.minute_start, cell.minute_end))
            for cell in hour_cells:
                if cell.activity_id is not None:
                    segments.append(
                        _activity_segment(
                            hour=hour,
                            start=cell.minute_start,
                            end=cell.minute_end,
                            activity=activities_by_id.get(cell.activity_id),
                            source="registered",
                        )
                    )
                elif cell.empty_override:
                    segments.append(_off_segment(hour, cell.minute_start, cell.minute_end))
            if template_hours is not None and hour in template_hours and home_activity_id is not None:
                covered = _covered_intervals(hour_cells)
                for start, end in _uncovered_intervals(covered):
                    segments.append(
                        _activity_segment(
                            hour=hour,
                            start=start,
                            end=end,
                            activity=activities_by_id.get(home_activity_id),
                            source="default",
                        )
                    )
        result[person.id] = {
            "person": person,
            "segments": _merge_segments(segments),
        }
    return result


def _empty_sync() -> dict[str, Any]:
    return {"source": "fallback", "last_sync_at": None, "next_sync_at": None, "status": "not_configured"}


def _available_dates_from_sources(rows_by_source: dict[str, list[dict[str, str]]]) -> list[date]:
    dates: set[date] = set()
    for source, rows in rows_by_source.items():
        if source not in EVENT_DATE_SOURCE_KEYS:
            continue
        for row in rows:
            timestamp = _event_timestamp(row, source)
            if timestamp is not None:
                dates.add(timestamp.date())
    return sorted(dates)


def build_person_productivity_report_from_files(
    db: Session,
    files: dict[str, Path],
    *,
    report_date: date | str | None = None,
    business_id: int | None = None,
    sync: dict[str, Any] | None = None,
) -> dict[str, Any]:
    requested_date = date.fromisoformat(str(report_date)) if report_date is not None and not isinstance(report_date, date) else report_date

    headers_by_source: dict[str, list[str]] = {}
    rows_by_source: dict[str, list[dict[str, str]]] = {}
    for key, path in files.items():
        if key not in {"pick", "trans", "pallet", "receive", "order_log", "sort", "base_pallet", "kpi"}:
            continue
        headers, rows = _read_csv_rows(Path(path))
        headers_by_source[key] = headers
        rows_by_source[key] = rows

    if "kpi" not in rows_by_source:
        raise ProductivitySourceError("Saknar KPI-mÃ¥l")

    available_dates = _available_dates_from_sources(rows_by_source)
    selected_date = requested_date or (available_dates[-1] if available_dates else date.today())
    if requested_date is not None and available_dates and selected_date not in available_dates:
        raise ProductivitySourceError(f"Saknar produktivitetsdata fÃ¶r {selected_date.isoformat()}")

    targets = parse_kpi_targets(rows_by_source["kpi"])
    kpi_rules, _kpi_logic_source = load_kpi_rules(db, business_id=business_id, files=files, allow_empty=True)
    kpi_rules_by_process = rules_by_process(kpi_rules)
    point_events, event_status = score_kpi_events(
        rows_by_source=rows_by_source,
        targets=targets,
        rules=kpi_rules,
        report_date=selected_date,
    )
    schedule_by_person = build_schedule_segments(db, selected_date, business_id=business_id)
    person_by_noman = {
        normalize_name(data["person"].noman): data["person"]
        for data in schedule_by_person.values()
        if normalize_name(data["person"].noman)
    }
    events_by_person_id: dict[int, list[KpiPointEvent]] = defaultdict(list)
    unmatched_event_count = 0
    for event in point_events:
        person = person_by_noman.get(event.user_key)
        if person is None:
            unmatched_event_count += 1
            continue
        events_by_person_id[person.id].append(event)

    people: list[dict[str, Any]] = []
    total_points = 0.0
    total_planned = 0.0
    total_kpi_minutes = 0
    total_support_minutes = 0
    total_absence_minutes = 0
    diff_count = 0
    missing_target_processes: set[str] = set()
    missing_rule_processes: set[str] = set(event_status.get("missing_rule_processes") or [])

    for person_id, data in schedule_by_person.items():
        person: Person = data["person"]
        segments = data["segments"]
        kpi_minutes = sum(segment["minutes"] for segment in segments if segment["kind"] == "kpi")
        support_minutes = sum(segment["minutes"] for segment in segments if segment["kind"] == "support")
        absence_minutes = sum(segment["minutes"] for segment in segments if segment["kind"] == "absence")
        if kpi_minutes <= 0 and support_minutes <= 0:
            continue
        planned_points = (kpi_minutes / 60.0) * 100.0
        person_points = 0.0
        diffs: list[dict[str, Any]] = []

        person_missing_targets, person_missing_rules = _planned_process_status(segments, targets, kpi_rules_by_process)
        missing_target_processes.update(person_missing_targets)
        missing_rule_processes.update(person_missing_rules)

        person_events = sorted(events_by_person_id.get(person_id, []), key=lambda item: item.timestamp)
        for event in person_events:
            person_points += event.points
            segment = _find_segment(segments, event.timestamp)
            expected = list(segment.get("processes") or []) if segment else []
            if not _event_should_warn_as_diff(event, segment):
                continue
            diffs.append(
                {
                    "time": event.timestamp.isoformat(timespec="minutes"),
                    "scheduled_activity": segment.get("activity_label") if segment else "Ej schemalagd",
                    "scheduled_display": segment.get("display") if segment else "Ej schemalagd",
                    "scheduled_processes": expected,
                    "actual_process": event.process,
                    "company": event.company,
                    "warehouse": event.warehouse,
                    "points": round(event.points, 2),
                    "source": event.source,
                }
            )

        productivity_pct = person_points / planned_points if planned_points > 0 else None
        total_points += person_points
        total_planned += planned_points
        total_kpi_minutes += kpi_minutes
        total_support_minutes += support_minutes
        total_absence_minutes += absence_minutes
        diff_count += len(diffs)
        people.append(
            {
                "person_id": person.id,
                "name": person.name,
                "home_area": getattr(person.home_area, "name", None),
                "productivity_pct": productivity_pct,
                "kpi_points": round(person_points, 2),
                "planned_kpi_points": round(planned_points, 2),
                "kpi_minutes": kpi_minutes,
                "support_minutes": support_minutes,
                "absence_minutes": absence_minutes,
                "segments": [
                    {key: value for key, value in segment.items() if key != "process_keys"}
                    for segment in segments
                ],
                "time_cells": _build_time_cells(segments, person_events),
                "diffs": diffs,
                "missing_target_processes": person_missing_targets,
                "missing_rule_processes": person_missing_rules,
            }
        )

    productivity_values = [
        person["productivity_pct"]
        for person in people
        if person["productivity_pct"] is not None
    ]
    sources = {
        key: _status_payload_for_path(key, Path(files[key]), len(rows_by_source.get(key, [])))
        for key in sorted(rows_by_source)
        if key in files
    }
    return {
        "generated_at": datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds"),
        "date": selected_date.isoformat(),
        "available_dates": [item.isoformat() for item in available_dates] or [selected_date.isoformat()],
        "hours": list(HOURS),
        "sources": sources,
        "people": people,
        "summary": {
            "people": len(people),
            "kpi_points": round(total_points, 2),
            "planned_kpi_points": round(total_planned, 2),
            "kpi_minutes": total_kpi_minutes,
            "support_minutes": total_support_minutes,
            "absence_minutes": total_absence_minutes,
            "average_productivity_pct": total_points / total_planned if total_planned > 0 else None,
            "person_average_productivity_pct": (
                sum(productivity_values) / len(productivity_values)
                if productivity_values
                else None
            ),
            "diff_count": diff_count,
            "unmatched_event_count": unmatched_event_count,
            "missing_target_processes": sorted(missing_target_processes, key=str.upper),
            "missing_rule_processes": sorted(missing_rule_processes, key=str.upper),
            "scored_event_count": len(point_events),
        },
        "sync": sync or _empty_sync(),
    }

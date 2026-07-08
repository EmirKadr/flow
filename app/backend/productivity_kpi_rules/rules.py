"""KPI-regler: konstanter, dataklasser, parsning och predikat."""
from __future__ import annotations

import gzip
import re
import unicodedata
from collections import defaultdict
from functools import lru_cache
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..home_activity import build_home_activity_resolver
from ..models import Activity, Area, Person, ScheduleCell
from ..productivity_service import (
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
from ..template_service import get_template_hours_map_for_dates

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
    criteria: dict[str, tuple[str, ...]] = field(default_factory=dict)

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


# Ren str->str-transform som anropas miljontals ganger per bygge (samma handful
# kolumnnamn per rad). Memoisering pa modulniva kollapsar ~4M anrop till nagra
# hundra unika och delar cachen mellan bolag/byggen. Se wiki/prestanda-optimeringar.md.
@lru_cache(maxsize=8192)
def _canonical_header_cached(text: str) -> str:
    text = text.strip().lstrip("\ufeff")
    if "Ãƒ" in text:
        try:
            text = text.encode("latin1").decode("utf-8")
        except UnicodeError:
            pass
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _canonical_header(value: Any) -> str:
    # Coerce utanfor cachen sa nyckeln alltid ar hashbar (str); beteendet blir
    # identiskt med tidigare str(value or "").strip()...
    return _canonical_header_cached(str(value or ""))


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


def _rule_criteria(row: dict[str, str]) -> dict[str, tuple[str, ...]]:
    criteria = {
        "company": tuple(_upper_values(_row_config_value(row, "company", "Bolag"))),
        "zone": tuple(_upper_values(_row_config_value(row, "zone", "Zon", "pick_zone"))),
        "type": tuple(_upper_values(_row_config_value(row, "type", "Typ"))),
        "status": tuple(_upper_values(_row_config_value(row, "status", "Status"))),
        "loc_from_equals": tuple(_upper_values(_row_config_value(row, "loc_from_equals", "Från är", "Fran ar"))),
        "loc_to_equals": tuple(_upper_values(_row_config_value(row, "loc_to_equals", "Till är", "Till ar"))),
        "location_starts": tuple(_split_rule_values(_row_config_value(row, "location_starts", "Lokation startar med"))),
    }
    return {key: value for key, value in criteria.items() if value}


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
                criteria=_rule_criteria(row),
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

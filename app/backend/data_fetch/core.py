"""Delad grund för Hämta data: konstanter, fel, katalogtyper och primitiver."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_CATALOG_PATH = ROOT_DIR / "data" / "external_data_catalog.json"
ALLOWED_OPERATORS = (
    "EQ",
    "NE",
    "GT",
    "GTE",
    "LT",
    "LTE",
    "Terms",
    "Between",
    "StartsWith",
    "EndsWith",
    "Contains",
    "Like",
)
TEXT_FILTER_OPERATORS = frozenset({"StartsWith", "EndsWith", "Contains", "Like"})
LOCAL_FILTER_OPERATORS = frozenset({"NE", "GT", "GTE", "LT", "LTE"} | set(TEXT_FILTER_OPERATORS))
ALLOWED_CALCULATION_METRICS = ("count", "count_distinct", "sum", "avg", "min", "max", "package_breakdown")
CALCULATION_METRIC_ALIASES = {
    "antal": "count",
    "antal_rader": "count",
    "count": "count",
    "count_rows": "count",
    "rows": "count",
    "count_distinct": "count_distinct",
    "distinct": "count_distinct",
    "unique": "count_distinct",
    "unika": "count_distinct",
    "sum": "sum",
    "summa": "sum",
    "total": "sum",
    "avg": "avg",
    "average": "avg",
    "snitt": "avg",
    "medel": "avg",
    "min": "min",
    "minimum": "min",
    "max": "max",
    "maximum": "max",
    "package_breakdown": "package_breakdown",
    "packages": "package_breakdown",
    "forpackningar": "package_breakdown",
    "forpackning": "package_breakdown",
    "antal_forpackningar": "package_breakdown",
    "kollin": "package_breakdown",
    "colli": "package_breakdown",
}

# Förpacknings-uppdelning: slår upp omräkningsfaktorer per artikel i en alias-vy och
# delar upp ett antal i förpackningar (störst först). Vy- och kolumnnamn är samlade
# här så att samma logik kan peka mot en annan källa utan kodändring i övrigt.
PACKAGE_ALIAS_VIEW = "item_alias"
PACKAGE_ALIAS_ITEM_FIELD = "item_num"
PACKAGE_ALIAS_COMPANY_FIELD = "company"
PACKAGE_ALIAS_UNIT_FIELD = "unit"
PACKAGE_ALIAS_FACTOR_FIELD = "conversion_factor"
PACKAGE_JOIN_ITEM_FIELD = "item_num"
PACKAGE_JOIN_COMPANY_FIELD = "company"
PACKAGE_BASE_UNIT_LABEL = "ST"
PACKAGE_UNIT_RESULT_FIELD = "unit"
OPERATOR_ALIASES = {
    "eq": "EQ",
    "=": "EQ",
    "==": "EQ",
    "ne": "NE",
    "!=": "NE",
    "<>": "NE",
    "gt": "GT",
    ">": "GT",
    "gte": "GTE",
    ">=": "GTE",
    "lt": "LT",
    "<": "LT",
    "lte": "LTE",
    "<=": "LTE",
    "terms": "Terms",
    "in": "Terms",
    "one_of": "Terms",
    "between": "Between",
    "mellan": "Between",
    "startswith": "StartsWith",
    "starts_with": "StartsWith",
    "starts with": "StartsWith",
    "begins_with": "StartsWith",
    "begins with": "StartsWith",
    "prefix": "StartsWith",
    "borjar_pa": "StartsWith",
    "borjar pa": "StartsWith",
    "börjar_på": "StartsWith",
    "börjar på": "StartsWith",
    "borjar_med": "StartsWith",
    "borjar med": "StartsWith",
    "börjar_med": "StartsWith",
    "börjar med": "StartsWith",
    "startar_med": "StartsWith",
    "startar med": "StartsWith",
    "endswith": "EndsWith",
    "ends_with": "EndsWith",
    "ends with": "EndsWith",
    "suffix": "EndsWith",
    "slutar_pa": "EndsWith",
    "slutar pa": "EndsWith",
    "slutar_på": "EndsWith",
    "slutar på": "EndsWith",
    "contains": "Contains",
    "innehaller": "Contains",
    "innehåller": "Contains",
    "like": "Like",
    "ilike": "Like",
}
STOP_WORDS = {
    "alla",
    "att",
    "och",
    "eller",
    "för",
    "for",
    "från",
    "fran",
    "hämta",
    "hamta",
    "med",
    "som",
    "till",
    "visa",
    "vyer",
    "vy",
}
MONTH_ALIASES = {
    "januari": 1,
    "jan": 1,
    "februari": 2,
    "feb": 2,
    "mars": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "apil": 4,
    "maj": 5,
    "juni": 6,
    "jun": 6,
    "juli": 7,
    "jul": 7,
    "augusti": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "oktober": 10,
    "okt": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
MONTH_PATTERN = re.compile(
    r"\b(?:(?P<month>"
    + "|".join(sorted((re.escape(key) for key in MONTH_ALIASES), key=len, reverse=True))
    + r")\s+(?P<year>20\d{2}|\d{2})|(?P<year2>20\d{2}|\d{2})\s+(?P<month2>"
    + "|".join(sorted((re.escape(key) for key in MONTH_ALIASES), key=len, reverse=True))
    + r"))\b",
    re.IGNORECASE,
)
DATE_COLUMN_PRIORITY = (
    "time_stamp_int",
    "date",
    "timestamp",
    "order_date",
    "order_date_time",
    "created_at",
    "changed_date",
    "date_time",
)
PREFERRED_DATE_COLUMNS_BY_VIEW = {
    "dispatch_pallet_log": "created",
    "dblog_dispatch_pallet_log": "created",
}
RELATIVE_DAYS_PATTERN = re.compile(
    r"\b(?:senaste|sista)\s+(?P<days>\d{1,3})\s+dag(?:en|ar|arna)?\b",
    re.IGNORECASE,
)
TODAY_PATTERN = re.compile(r"\b(?:idag|dagens(?:\s+(?:datum|timestamp|tid))?)\b", re.IGNORECASE)
CODE_VALUE_COLUMNS = {"company"}

class DataFetchConfigError(Exception):
    """Raised when the private external data catalog or API settings are missing."""


class DataFetchPlanError(Exception):
    """Raised when MiniMax returns a plan that cannot be safely executed."""


@dataclass(frozen=True)
class DataColumn:
    id: str
    label_en: str
    label_sv: str
    order: int

    @property
    def label(self) -> str:
        return self.label_sv or self.label_en or self.id


@dataclass(frozen=True)
class DataView:
    id: str
    label_en: str
    label_sv: str
    columns: tuple[DataColumn, ...]

    @property
    def label(self) -> str:
        return self.label_sv or self.label_en or self.id

    @property
    def column_by_id(self) -> dict[str, DataColumn]:
        return {column.id: column for column in self.columns}


@dataclass(frozen=True)
class DataCatalog:
    views: dict[str, DataView]

    def view(self, view_id: str) -> DataView:
        try:
            return self.views[view_id]
        except KeyError as exc:
            raise DataFetchPlanError(f"Okänd vy: {view_id}") from exc

    def candidate_views(self, prompt: str, limit: int = 12) -> list[DataView]:
        prompt_norm = _normalize(prompt)
        prompt_tokens = _tokens(prompt)
        scored: list[tuple[int, str, DataView]] = []
        for view in self.views.values():
            score = _match_score(prompt_norm, prompt_tokens, view.id, view.label_en, view.label_sv) * 4
            for column in view.columns:
                column_score = _match_score(prompt_norm, prompt_tokens, column.id, column.label_en, column.label_sv)
                if column_score:
                    score += min(column_score, 6)
            if score:
                scored.append((score, view.label.lower(), view))

        if not scored:
            return sorted(self.views.values(), key=lambda item: item.label.lower())[:limit]
        scored.sort(key=lambda item: (-item[0], item[1], item[2].id))
        return [view for _score, _label, view in scored[:limit]]

def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower().replace("_", " "))


def _tokens(value: object) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_åäöÅÄÖ-]{2,}", str(value or "").lower())
        if token not in STOP_WORDS
    }


def _match_score(prompt_norm: str, prompt_tokens: set[str], *values: object) -> int:
    score = 0
    for value in values:
        text = str(value or "")
        if not text:
            continue
        normalized = _normalize(text)
        if normalized and normalized in prompt_norm:
            score += 20
        score += 2 * len(prompt_tokens & _tokens(text))
        if str(value).lower() in prompt_norm:
            score += 8
    return score


def _app_now() -> datetime:
    return datetime.now().astimezone()

def _date_period_payload(kind: str, start_date: date, end_date: date, **extra: Any) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": f"{start_date.isoformat()}..{end_date.isoformat()}",
        "start_yyyymmdd": start_date.year * 10000 + start_date.month * 100 + start_date.day,
        "end_yyyymmdd": end_date.year * 10000 + end_date.month * 100 + end_date.day,
        "start_iso": start_date.isoformat(),
        "end_iso": end_date.isoformat(),
        **extra,
    }


def infer_prompt_period(prompt: object, today: date | None = None) -> dict[str, Any] | None:
    normalized = _normalize(prompt)
    match = MONTH_PATTERN.search(normalized)
    if match:
        month_key = (match.group("month") or match.group("month2") or "").lower()
        year_text = match.group("year") or match.group("year2") or ""
        month = MONTH_ALIASES.get(month_key)
        if not month:
            return None
        year = int(year_text)
        if year < 100:
            year += 2000
        last_day = calendar.monthrange(year, month)[1]
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)
        return _date_period_payload("month", start_date, end_date, year=year, month=month)

    relative_match = RELATIVE_DAYS_PATTERN.search(normalized)
    if relative_match:
        days = max(1, int(relative_match.group("days")))
        end_date = today or _app_now().date()
        start_date = end_date - timedelta(days=days - 1)
        return _date_period_payload("relative_days", start_date, end_date, days=days)

    if TODAY_PATTERN.search(normalized):
        end_date = today or _app_now().date()
        return _date_period_payload("today", end_date, end_date)

    if re.search(r"\big[aå]r\b", normalized):
        end_date = (today or _app_now().date()) - timedelta(days=1)
        return _date_period_payload("yesterday", end_date, end_date)

    return None


def _preferred_date_column(view: DataView) -> DataColumn | None:
    columns_by_id = view.column_by_id
    preferred_for_view = PREFERRED_DATE_COLUMNS_BY_VIEW.get(getattr(view, "id", ""))
    if preferred_for_view:
        column = columns_by_id.get(preferred_for_view)
        if column:
            return column
    for column_id in DATE_COLUMN_PRIORITY:
        column = columns_by_id.get(column_id)
        if column:
            return column
    for column in view.columns:
        text = _normalize(f"{column.id} {column.label_en} {column.label_sv}")
        if any(token in text for token in ("date", "datum", "timestamp", "skapad", "andrad")):
            return column
    return None


def _period_values_for_column(period: dict[str, Any], column: DataColumn) -> list[Any]:
    text = _normalize(f"{column.id} {column.label_en} {column.label_sv}")
    if column.id.endswith("_int") or "int" in text:
        return [period["start_yyyymmdd"], period["end_yyyymmdd"]]
    if "timestamp" in text or column.id in {"date_time", "order_date_time", "created_at", "changed_date", "created"}:
        return [f"{period['start_iso']}T00:00:00", f"{period['end_iso']}T23:59:59"]
    return [period["start_iso"], period["end_iso"]]


def _normalize_filter_value(column_id: str, operator: str, value: Any) -> Any:
    if column_id not in CODE_VALUE_COLUMNS:
        return value
    if operator == "Terms" and isinstance(value, list):
        return [str(item).strip().upper() if isinstance(item, str) else item for item in value]
    if isinstance(value, str):
        return value.strip().upper()
    return value

def _row_value(row: dict[str, Any], column_id: str) -> Any:
    if column_id in row:
        return row.get(column_id)
    lower_map = {str(key).lower(): key for key in row}
    actual_key = lower_map.get(column_id.lower())
    return row.get(actual_key) if actual_key is not None else None

def _stable_value_key(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _number_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\u00a0", "").replace(" ", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _compact_number(value: float | int | None) -> float | int:
    if value is None:
        return 0
    number = float(value)
    return int(number) if number.is_integer() else number

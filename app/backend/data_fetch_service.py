from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
from typing import Any

from .config import settings


ROOT_DIR = Path(__file__).resolve().parents[2]
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
PACKAGE_ALIAS_VIEW = "asw_item_alias"
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


_CATALOG_CACHE: tuple[str, DataCatalog] | None = None


def clear_catalog_cache() -> None:
    global _CATALOG_CACHE
    _CATALOG_CACHE = None


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
    if "timestamp" in text or column.id in {"date_time", "order_date_time", "created_at", "changed_date"}:
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


def _catalog_source() -> tuple[str, str]:
    raw_json = settings.DATA_SOURCE_CATALOG_JSON.strip()
    if raw_json:
        return "env:DATA_SOURCE_CATALOG_JSON", raw_json

    configured_path = settings.DATA_SOURCE_CATALOG_PATH.strip()
    path = Path(configured_path) if configured_path else DEFAULT_CATALOG_PATH
    if not path.is_absolute():
        path = ROOT_DIR / path
    if not path.is_file():
        raise DataFetchConfigError("Extern datakatalog saknas i servermiljön.")
    try:
        return str(path), path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DataFetchConfigError(f"Kunde inte läsa extern datakatalog: {exc}") from exc


def load_catalog() -> DataCatalog:
    global _CATALOG_CACHE
    source, raw = _catalog_source()
    signature = f"{source}:{hash(raw)}"
    if _CATALOG_CACHE and _CATALOG_CACHE[0] == signature:
        return _CATALOG_CACHE[1]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DataFetchConfigError("Extern datakatalog är inte giltig JSON.") from exc
    catalog = catalog_from_payload(payload)
    _CATALOG_CACHE = (signature, catalog)
    return catalog


def catalog_from_payload(payload: dict[str, Any]) -> DataCatalog:
    views_payload = payload.get("views") if isinstance(payload, dict) else None
    if not isinstance(views_payload, list):
        raise DataFetchConfigError("Extern datakatalog måste innehålla listan 'views'.")

    views: dict[str, DataView] = {}
    for view_payload in views_payload:
        if not isinstance(view_payload, dict):
            continue
        view_id = str(view_payload.get("id") or "").strip()
        if not view_id:
            continue
        columns: list[DataColumn] = []
        for column_payload in view_payload.get("columns") or []:
            if not isinstance(column_payload, dict):
                continue
            column_id = str(column_payload.get("id") or "").strip()
            if not column_id:
                continue
            columns.append(
                DataColumn(
                    id=column_id,
                    label_en=str(column_payload.get("label_en") or "").strip(),
                    label_sv=str(column_payload.get("label_sv") or "").strip(),
                    order=int(column_payload.get("order") or len(columns) + 1),
                )
            )
        columns.sort(key=lambda item: item.order)
        views[view_id] = DataView(
            id=view_id,
            label_en=str(view_payload.get("label_en") or "").strip(),
            label_sv=str(view_payload.get("label_sv") or "").strip(),
            columns=tuple(columns),
        )
    if not views:
        raise DataFetchConfigError("Extern datakatalog innehåller inga vyer.")
    return DataCatalog(views=views)


def catalog_summary(catalog: DataCatalog) -> dict[str, int]:
    return {
        "views": len(catalog.views),
        "columns": sum(len(view.columns) for view in catalog.views.values()),
    }


def build_catalog_context(prompt: str, catalog: DataCatalog, limit: int = 12) -> dict[str, Any]:
    views = []
    candidate_views = catalog.candidate_views(prompt, limit=limit)
    app_now = _app_now()
    for view in candidate_views:
        views.append(
            {
                "view_id": view.id,
                "name_sv": view.label_sv,
                "name_en": view.label_en,
                "columns": [
                    {
                        "column_id": column.id,
                        "name_sv": column.label_sv,
                        "name_en": column.label_en,
                    }
                    for column in view.columns
                ],
            }
        )
    context: dict[str, Any] = {
        "operators": list(ALLOWED_OPERATORS),
        "current_date": app_now.date().isoformat(),
        "current_datetime": app_now.isoformat(timespec="seconds"),
        "candidate_views": views,
    }
    period = infer_prompt_period(prompt, app_now.date())
    if period:
        period_hint = dict(period)
        period_hint["preferred_date_columns"] = {
            view.id: column.id
            for view in candidate_views
            if (column := _preferred_date_column(view)) is not None
        }
        context["detected_period"] = period_hint
    return context


def build_data_fetch_minimax_payload(prompt: str, catalog_context: dict[str, Any]) -> dict[str, Any]:
    system_prompt = """
Du tolkar en användares svenska önskan till en säker fråga mot en extern datakälla.

Du får bara använda vyer och kolumner i katalogutdraget. Du får aldrig hitta på
endpoint, URL, API-nyckel, token, servernamn eller hemliga anslutningsuppgifter.
Du ska bara returnera JSON, utan markdown.

Katalogutdraget innehaller appens interna current_date och current_datetime.
Anvand dem for uttryck som idag, dagens datum, dagens timestamp och senaste N
dagarna. Gissa aldrig datum for relativa tidsuttryck.

Om katalogutdraget innehaller detected_period ska perioden anvandas som
datumfilter. Valj preferred_date_columns[view_id] om den finns. For int-baserade
datumkolumner som time_stamp_int anvander du start_yyyymmdd och end_yyyymmdd
med Between. For timestamp-kolumner anvander du hela dagens intervall
YYYY-MM-DDT00:00:00 till YYYY-MM-DDT23:59:59. Lagg aldrig en tidsperiod i
order_num eller kundref.

Välj exakt en view_id. Använd alltid tekniska column_id i output_columns,
filters och identifiers. Svenska namn i katalogen är alias för användaren.
Använd identifiers bara när användaren anger konkreta identifierarvärden som ska
hämtas från API:t. Använd aldrig identifiers för dubletter, unika rader,
gruppering eller beräkningar.

Tillåtna filteroperatorer:
- EQ, NE, GT, GTE, LT, LTE
- Terms: value ska vara en lista
- Between: value ska vara en lista med två värden
- StartsWith: för "börjar på/med X", exempelvis ordernummer som börjar på TO
- EndsWith: för "slutar på X"
- Contains: för "innehåller X"
- Like: för explicita SQL-like-mönster med % eller _, exempelvis TO%
För "exkludera A, B och C" ska du returnera ett separat NE-filter per värde.
För "börjar på TO" ska du returnera
{"field":"order_num","operator":"StartsWith","value":"TO"}, aldrig NE eller <>.

Om användaren ber om antal, summa, snitt, min, max, grupperingar, topp-listor
eller att ta bort dubletter ska du fylla i calculation. Tillåtna beräkningar:
- count: antal rader
- count_distinct: antal unika kombinationer, kräver distinct_by
- sum, avg, min, max: kräver field
- package_breakdown: antal förpackningar. När användaren vill veta hur många
  förpackningar, kollin, kartonger, lådor, displayer, rullar eller liknande som
  plockats/beställts (oavsett vad förpackningen kallas) ska du välja denna. Kräver
  field = antalskolumnen som ska delas upp (t.ex. qty_pre/Beställt). Lägg artikeln
  i group_by (t.ex. item_num). Backend slår själv upp omräkningsfaktorerna per
  artikel och delar upp antalet i förpackningar (störst först) – du ska INTE
  försöka joina, räkna faktorer eller lista enhetsnamn själv.
Valfria calculation-fält:
- group_by: lista med column_id för "per X" eller gruppering
- sort_by: {"field": "value" eller column_id, "direction": "asc|desc"}
- limit: heltal för topp/första N
"Ta bort dubletter per inköpsnummer och artikelnummer" betyder
{"metric":"count_distinct","distinct_by":["book_num","item_num"]}.

Returnera detta format:
{
  "status": "ok",
  "view": "view_id",
  "output_columns": ["column_id"],
  "filters": [{"field": "column_id", "operator": "EQ", "value": "x"}],
  "identifiers": [],
  "calculation": null,
  "reason": "kort svensk förklaring"
}

Om frågan är för otydlig, returnera:
{
  "status": "needs_clarification",
  "question": "kort fråga på svenska"
}
""".strip()
    return {
        "model": settings.MINIMAX_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "prompt": prompt,
                        "catalog": catalog_context,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "max_tokens": max(settings.MINIMAX_MAX_TOKENS, 1200),
        "temperature": 0.0,
        "reasoning_split": True,
    }


def parse_minimax_plan(raw_answer: str) -> dict[str, Any]:
    text = str(raw_answer or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise DataFetchPlanError("MiniMax returnerade inte ett JSON-objekt.")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise DataFetchPlanError("MiniMax returnerade ogiltig JSON.") from exc
    if not isinstance(payload, dict):
        raise DataFetchPlanError("MiniMax-planen måste vara ett JSON-objekt.")
    return payload


def _normalize_operator(value: object) -> str:
    key = str(value or "").strip()
    alias_key = re.sub(r"\s+", " ", key.lower().replace("-", "_"))
    normalized = OPERATOR_ALIASES.get(alias_key)
    if normalized:
        return normalized
    if key in ALLOWED_OPERATORS:
        return key
    raise DataFetchPlanError(f"Otillåten filteroperator: {key}")


def _normalize_calculation_metric(value: object) -> str:
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    folded = key.translate(str.maketrans("åäö", "aao"))
    metric = CALCULATION_METRIC_ALIASES.get(key) or CALCULATION_METRIC_ALIASES.get(folded, folded)
    if metric in ALLOWED_CALCULATION_METRICS:
        return metric
    raise DataFetchPlanError(f"Otillåten beräkning: {value}")


def _assert_column(view: DataView, column_id: str) -> DataColumn:
    column = view.column_by_id.get(column_id)
    if not column:
        raise DataFetchPlanError(f"Kolumnen '{column_id}' finns inte i vyn {view.id}.")
    return column


def _normalize_output_columns(raw: Any, view: DataView) -> list[str]:
    incoming = raw if isinstance(raw, list) else []
    result: list[str] = []
    for item in incoming:
        column_id = str(item or "").strip()
        if not column_id or column_id in result:
            continue
        _assert_column(view, column_id)
        result.append(column_id)
    if not result:
        result = [column.id for column in view.columns[:20]]
    return result


def _column_id_list(raw: Any, view: DataView, *, field_name: str, limit: int = 20) -> list[str]:
    if raw in (None, ""):
        return []
    incoming = raw if isinstance(raw, list) else [raw]
    result: list[str] = []
    for item in incoming[:limit]:
        column_id = str(item or "").strip()
        if not column_id or column_id in result:
            continue
        _assert_column(view, column_id)
        result.append(column_id)
    if raw not in (None, "") and not result:
        raise DataFetchPlanError(f"{field_name} måste innehålla minst en kolumn.")
    return result


def _normalize_filters(raw: Any, view: DataView) -> list[dict[str, Any]]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise DataFetchPlanError("filters måste vara en lista.")
    filters: list[dict[str, Any]] = []
    for item in raw[:20]:
        if not isinstance(item, dict):
            raise DataFetchPlanError("Varje filter måste vara ett objekt.")
        field = str(item.get("field") or item.get("id") or item.get("column") or "").strip()
        if not field:
            raise DataFetchPlanError("Filter saknar field.")
        _assert_column(view, field)
        operator = _normalize_operator(item.get("operator"))
        value = item.get("value")
        if operator == "Terms" and not isinstance(value, list):
            value = [value]
        if operator == "NE" and isinstance(value, list):
            for single_value in value:
                filters.append({"id": field, "operator": operator, "value": single_value})
            continue
        if operator == "Between":
            if not isinstance(value, list):
                value = [item.get("from"), item.get("to")]
            if len(value) != 2:
                raise DataFetchPlanError("Between-filter måste ha två värden.")
        if operator in TEXT_FILTER_OPERATORS:
            if isinstance(value, list):
                raise DataFetchPlanError(f"{operator}-filter måste ha ett textvärde.")
            value = str(value or "").strip()
            if not value:
                raise DataFetchPlanError(f"{operator}-filter saknar värde.")
        filters.append({"id": field, "operator": operator, "value": value})
    return filters


def _identifiers_are_column_list(raw: Any, view: DataView) -> bool:
    if not isinstance(raw, list) or not raw:
        return False
    for item in raw:
        if not isinstance(item, str):
            return False
        try:
            _assert_column(view, item.strip())
        except DataFetchPlanError:
            return False
    return True


def _normalize_identifiers(raw: Any, view: DataView) -> list[dict[str, Any]]:
    if raw in (None, "", []):
        return []
    items = [raw] if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise DataFetchPlanError("identifiers måste vara ett objekt eller en lista.")
    result: list[dict[str, Any]] = []
    for item in items[:20]:
        if not isinstance(item, dict):
            raise DataFetchPlanError("Varje identifierare måste vara ett objekt.")
        if "field" in item and "value" in item:
            item = {str(item["field"]): item["value"]}
        row: dict[str, Any] = {}
        for key, value in item.items():
            column_id = str(key or "").strip()
            if not column_id:
                continue
            _assert_column(view, column_id)
            row[column_id] = value
        if row:
            result.append(row)
    return result


def _normalize_sort_by(raw: Any, view: DataView) -> dict[str, str] | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, str):
        field = raw.strip()
        direction = "desc"
    elif isinstance(raw, dict):
        field = str(raw.get("field") or raw.get("id") or raw.get("column") or "value").strip()
        direction = str(raw.get("direction") or raw.get("order") or "desc").strip().lower()
    else:
        raise DataFetchPlanError("sort_by måste vara ett objekt eller en kolumn.")
    if field not in {"value", "metric", "count"}:
        _assert_column(view, field)
    if direction not in {"asc", "desc"}:
        raise DataFetchPlanError("sort_by.direction måste vara asc eller desc.")
    return {"field": "value" if field in {"metric", "count"} else field, "direction": direction}


def _normalize_calculation(raw: Any, view: DataView, raw_identifiers: Any = None) -> dict[str, Any] | None:
    if raw in (None, "", [], {}):
        if _identifiers_are_column_list(raw_identifiers, view):
            return {
                "metric": "count_distinct",
                "distinct_by": _column_id_list(raw_identifiers, view, field_name="distinct_by"),
                "group_by": [],
                "sort_by": None,
                "limit": None,
            }
        return None
    if not isinstance(raw, dict):
        raise DataFetchPlanError("calculation måste vara ett objekt.")

    metric = _normalize_calculation_metric(raw.get("metric") or raw.get("type") or raw.get("operation"))
    field = str(raw.get("field") or raw.get("value_field") or raw.get("column") or "").strip()
    if metric in {"sum", "avg", "min", "max", "package_breakdown"}:
        if not field:
            raise DataFetchPlanError(f"Beräkningen {metric} kräver field.")
        _assert_column(view, field)
    elif field:
        _assert_column(view, field)

    distinct_by = _column_id_list(
        raw.get("distinct_by") or raw.get("deduplicate_by") or raw.get("unique_by"),
        view,
        field_name="distinct_by",
    )
    if metric == "count_distinct" and not distinct_by:
        if field:
            distinct_by = [field]
        else:
            raise DataFetchPlanError("count_distinct kräver distinct_by.")

    group_by = _column_id_list(raw.get("group_by") or raw.get("groups"), view, field_name="group_by")
    sort_by = _normalize_sort_by(raw.get("sort_by") or raw.get("order_by"), view)
    limit_value = raw.get("limit")
    limit: int | None = None
    if limit_value not in (None, ""):
        try:
            limit = min(5000, max(1, int(limit_value)))
        except (TypeError, ValueError) as exc:
            raise DataFetchPlanError("calculation.limit måste vara ett heltal.") from exc

    return {
        "metric": metric,
        "field": field or None,
        "distinct_by": distinct_by,
        "group_by": group_by,
        "sort_by": sort_by,
        "limit": limit,
    }


def validate_plan_payload(payload: dict[str, Any], catalog: DataCatalog) -> dict[str, Any]:
    status = str(payload.get("status") or "ok").strip()
    if status == "needs_clarification":
        return {
            "status": "needs_clarification",
            "question": str(payload.get("question") or "Vilken vy och vilka filter vill du använda?").strip(),
        }
    if status != "ok":
        raise DataFetchPlanError("MiniMax-planen har okänd status.")

    view_id = str(payload.get("view") or payload.get("view_id") or "").strip()
    if not view_id:
        raise DataFetchPlanError("MiniMax-planen saknar view.")
    view = catalog.view(view_id)
    output_columns = _normalize_output_columns(
        payload.get("output_columns") or payload.get("columns"),
        view,
    )
    filters = _normalize_filters(payload.get("filters") or payload.get("userFilter"), view)
    raw_identifiers = payload.get("identifiers")
    calculation = _normalize_calculation(
        payload.get("calculation") or payload.get("aggregation") or payload.get("aggregate"),
        view,
        raw_identifiers=raw_identifiers,
    )
    identifiers = [] if _identifiers_are_column_list(raw_identifiers, view) else _normalize_identifiers(raw_identifiers, view)
    label_column_ids = list(output_columns)
    if calculation:
        for column_id in [
            calculation.get("field"),
            *(calculation.get("distinct_by") or []),
            *(calculation.get("group_by") or []),
        ]:
            if column_id and column_id not in label_column_ids:
                label_column_ids.append(str(column_id))
    selected_columns = [_assert_column(view, column_id) for column_id in label_column_ids]

    return {
        "status": "ok",
        "view": view.id,
        "view_label": view.label,
        "output_columns": output_columns,
        "output_column_labels": {column.id: column.label for column in selected_columns},
        "filters": filters,
        "identifiers": identifiers,
        "calculation": calculation,
        "reason": str(payload.get("reason") or "").strip(),
    }


def apply_prompt_period_hint(plan: dict[str, Any], prompt: str, catalog: DataCatalog) -> dict[str, Any]:
    app_today = _app_now().date()
    period = infer_prompt_period(prompt, app_today)
    if plan.get("status") != "ok":
        return plan
    try:
        view = catalog.view(str(plan.get("view") or ""))
    except DataFetchPlanError:
        return plan
    date_column = _preferred_date_column(view)

    filters: list[dict[str, Any]] = []
    for item in plan.get("filters") or []:
        column_id = item.get("id")
        operator = str(item.get("operator") or "")
        value = item.get("value")
        if period and date_column and column_id == date_column.id:
            continue
        if period and column_id != getattr(date_column, "id", None) and infer_prompt_period(value, app_today):
            continue
        filters.append({**item, "value": _normalize_filter_value(str(column_id or ""), operator, value)})

    plan = dict(plan)
    if period and date_column:
        filters.append(
            {
                "id": date_column.id,
                "operator": "Between",
                "value": _period_values_for_column(period, date_column),
            }
        )
        reason = str(plan.get("reason") or "").strip()
        suffix = "Datumperioden tolkades fran prompten."
        plan["reason"] = f"{reason} {suffix}".strip()
    plan["filters"] = filters
    return plan


# Live radnivå-vy -> (retention-dagar i operativa WManFrey, arkivvy-id i log_wmanfrey).
# Endast tabeller som har archive="true" i rensnings-/arkiveringsjobbet OCH bade en
# live- och en dblog-vy i katalogen. Se wiki/ask-datalagring.md.
LIVE_ARCHIVE_PAIRS: dict[str, tuple[int, str]] = {
    "v_ask_pick_log_full": (40, "dblog_pick_log"),
    "v_ask_trans_log": (60, "dblog_trans_log"),
    "v_ask_order_log": (80, "dblog_order_log"),
    "v_ask_palletloading_log": (60, "dblog_loading_log"),
    "v_ask_receive_log": (60, "dblog_receive_log"),
    "v_ask_correct_log": (60, "dblog_correct_log"),
    "v_ask_count_log": (90, "dblog_count_log"),
    "v_ask_login_log": (60, "dblog_login_log"),
    "v_ask_robot_pick_log": (30, "dblog_robot_pick_log"),
    "v_ask_pick_rest_log": (60, "dblog_pick_rest_log"),
    "v_ask_return_order_log": (60, "dblog_return_order_log"),
    "v_ask_trace_log": (60, "dblog_trace_log"),
    "v_ask_fill_rate_log": (30, "dblog_fill_rate_log"),
    "v_ask_pallet_rent_log_raw": (3, "dblog_pallet_rent_log_raw"),
}
ARCHIVE_TO_LIVE: dict[str, tuple[int, str]] = {
    archive_id: (days, live_id) for live_id, (days, archive_id) in LIVE_ARCHIVE_PAIRS.items()
}


def _parse_plan_date_bound(value: Any) -> date | None:
    """Tolka ett Between-gränsvärde (YYYYMMDD-int, ISO-datum eller ISO-datetime) som datum."""
    if isinstance(value, bool) or value is None:
        return None
    text = str(int(value)) if isinstance(value, (int, float)) else str(value).strip()
    if not text:
        return None
    digits = text.split("T", 1)[0].replace("-", "")
    if len(digits) >= 8 and digits[:8].isdigit():
        try:
            return datetime.strptime(digits[:8], "%Y%m%d").date()
        except ValueError:
            return None
    return None


def _plan_date_window(plan: dict[str, Any], view: DataView) -> tuple[int, date, date] | None:
    """Hitta planens Between-datumfilter på vyns föredragna datumkolumn."""
    date_column = _preferred_date_column(view)
    if date_column is None:
        return None
    for index, item in enumerate(plan.get("filters") or []):
        if str(item.get("operator") or "") != "Between":
            continue
        if (item.get("id") or item.get("field")) != date_column.id:
            continue
        value = item.get("value")
        if not isinstance(value, list) or len(value) != 2:
            continue
        start = _parse_plan_date_bound(value[0])
        end = _parse_plan_date_bound(value[1])
        if start and end and start <= end:
            return index, start, end
    return None


def _segment_plan(
    plan: dict[str, Any],
    target_view: DataView,
    period_start: date,
    period_end: date,
    *,
    source_date_column_id: str | None,
) -> dict[str, Any]:
    """Bygg en minimal hämtningsplan för target_view begränsad till [start, end].

    Behåller bara filter vars kolumn finns i target_view och ersätter källans
    datumfilter med target_view:s egen datumkolumn för delperioden.
    """
    filters: list[dict[str, Any]] = []
    for item in plan.get("filters") or []:
        column_id = item.get("id") or item.get("field")
        operator = str(item.get("operator") or "")
        if operator == "Between" and column_id == source_date_column_id:
            continue
        if column_id in target_view.column_by_id:
            filters.append(dict(item))
    target_date_column = _preferred_date_column(target_view)
    if target_date_column is not None:
        period = _date_period_payload("segment", period_start, period_end)
        filters.append(
            {
                "id": target_date_column.id,
                "operator": "Between",
                "value": _period_values_for_column(period, target_date_column),
            }
        )
    identifiers = [
        row
        for row in (plan.get("identifiers") or [])
        if isinstance(row, dict) and row and all(key in target_view.column_by_id for key in row)
    ]
    return {
        "status": "ok",
        "view": target_view.id,
        "view_label": target_view.label,
        "filters": filters,
        "identifiers": identifiers,
    }


def build_retention_segments(
    plan: dict[str, Any],
    catalog: DataCatalog,
    today: date | None = None,
) -> dict[str, Any] | None:
    """Avgör om planens datumperiod kräver arkivvyn och/eller live-vyn.

    Returnerar None när planen ska köras oförändrad (en vy), annars en dict med
    ``segments`` (1–2 hämtningsplaner att slå ihop), ``notice`` (svensk text till
    användaren) och ``fetched_views`` (vy-id som faktiskt hämtas).
    """
    if plan.get("status") != "ok":
        return None
    view_id = str(plan.get("view") or "")
    is_live = view_id in LIVE_ARCHIVE_PAIRS
    is_archive = view_id in ARCHIVE_TO_LIVE
    if not (is_live or is_archive):
        return None
    try:
        source_view = catalog.view(view_id)
    except DataFetchPlanError:
        return None
    window = _plan_date_window(plan, source_view)
    if window is None:
        return None
    _index, start, end = window
    source_date_id = getattr(_preferred_date_column(source_view), "id", None)
    today = today or _app_now().date()

    def _label(view: DataView) -> str:
        return f"”{view.label}”"

    if is_live:
        days, archive_id = LIVE_ARCHIVE_PAIRS[view_id]
        try:
            archive_view = catalog.view(archive_id)
        except DataFetchPlanError:
            return None
        cutoff = today - timedelta(days=days)
        if start >= cutoff:
            return None  # hela perioden ryms i aktiv data
        if end < cutoff:
            segment = _segment_plan(plan, archive_view, start, end, source_date_column_id=source_date_id)
            notice = (
                f"{_label(source_view)} behålls bara ~{days} dagar i den aktiva databasen. "
                f"Hela perioden {start.isoformat()}–{end.isoformat()} hämtades därför från "
                f"arkivet {_label(archive_view)}. Kolumnerna skiljer sig från live-vyn, så "
                f"vissa fält kan vara tomma."
            )
            return {"segments": [segment], "notice": notice, "fetched_views": [archive_view.id]}
        live_segment = _segment_plan(plan, source_view, cutoff, end, source_date_column_id=source_date_id)
        archive_segment = _segment_plan(
            plan, archive_view, start, cutoff - timedelta(days=1), source_date_column_id=source_date_id
        )
        notice = (
            f"Perioden {start.isoformat()}–{end.isoformat()} spänner över gränsen för aktiv "
            f"data (~{days} dagar). Hämtade både {_label(source_view)} (från {cutoff.isoformat()}) "
            f"och arkivet {_label(archive_view)} (till {(cutoff - timedelta(days=1)).isoformat()}) "
            f"och slog ihop resultaten. Kolumnerna skiljer sig, så vissa fält kan vara tomma."
        )
        return {
            "segments": [live_segment, archive_segment],
            "notice": notice,
            "fetched_views": [source_view.id, archive_view.id],
        }

    days, live_id = ARCHIVE_TO_LIVE[view_id]
    try:
        live_view = catalog.view(live_id)
    except DataFetchPlanError:
        return None
    cutoff = today - timedelta(days=days)
    if end < cutoff:
        return None  # hela perioden ligger i arkivet, inget att lägga till
    archive_segment = _segment_plan(plan, source_view, start, end, source_date_column_id=source_date_id)
    live_start = max(start, cutoff)
    live_segment = _segment_plan(plan, live_view, live_start, end, source_date_column_id=source_date_id)
    notice = (
        f"Perioden {start.isoformat()}–{end.isoformat()} ligger delvis i den aktiva databasen "
        f"(~{days} dagar). Hämtade därför även {_label(live_view)} (från {live_start.isoformat()}) "
        f"utöver arkivet {_label(source_view)}. Kolumnerna skiljer sig, så vissa fält kan vara tomma."
    )
    return {
        "segments": [archive_segment, live_segment],
        "notice": notice,
        "fetched_views": [source_view.id, live_view.id],
    }


def _row_value(row: dict[str, Any], column_id: str) -> Any:
    if column_id in row:
        return row.get(column_id)
    lower_map = {str(key).lower(): key for key in row}
    actual_key = lower_map.get(column_id.lower())
    return row.get(actual_key) if actual_key is not None else None


def external_filters_for_api(filters: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in (filters or [])
        if str(item.get("operator") or "") not in LOCAL_FILTER_OPERATORS
    ]


def _like_pattern_to_regex(pattern: str) -> re.Pattern[str]:
    parts: list[str] = []
    for char in pattern:
        if char == "%":
            parts.append(".*")
        elif char == "_":
            parts.append(".")
        else:
            parts.append(re.escape(char))
    return re.compile("^" + "".join(parts) + "$", re.IGNORECASE)


def _values_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    left_number = _number_value(left)
    right_number = _number_value(right)
    if left_number is not None and right_number is not None:
        return left_number == right_number
    return str(left).strip().casefold() == str(right).strip().casefold()


def _compare_values(left: Any, right: Any) -> int | None:
    if left is None or right is None:
        return None
    left_number = _number_value(left)
    right_number = _number_value(right)
    if left_number is not None and right_number is not None:
        if left_number == right_number:
            return 0
        return -1 if left_number < right_number else 1
    left_text = str(left).strip().casefold()
    right_text = str(right).strip().casefold()
    if left_text == right_text:
        return 0
    return -1 if left_text < right_text else 1


def _local_filter_matches(value: Any, operator: str, expected: Any) -> bool:
    if operator == "EQ":
        return _values_equal(value, expected)
    if operator == "NE":
        return value is not None and not _values_equal(value, expected)
    if operator == "Terms":
        values = expected if isinstance(expected, list) else [expected]
        return any(_values_equal(value, item) for item in values)
    if operator == "Between" and isinstance(expected, list) and len(expected) == 2:
        lower = _compare_values(value, expected[0])
        upper = _compare_values(value, expected[1])
        return lower is not None and upper is not None and lower >= 0 and upper <= 0
    if operator in {"GT", "GTE", "LT", "LTE"}:
        compared = _compare_values(value, expected)
        if compared is None:
            return False
        return {
            "GT": compared > 0,
            "GTE": compared >= 0,
            "LT": compared < 0,
            "LTE": compared <= 0,
        }[operator]
    if operator not in TEXT_FILTER_OPERATORS or value is None:
        return False
    text = str(value).strip()
    pattern = str(expected or "").strip()
    if not pattern:
        return False
    if operator == "StartsWith":
        return text.casefold().startswith(pattern.rstrip("%").casefold())
    if operator == "EndsWith":
        return text.casefold().endswith(pattern.lstrip("%").casefold())
    if operator == "Contains":
        return pattern.strip("%").casefold() in text.casefold()
    if operator == "Like":
        return bool(_like_pattern_to_regex(pattern).match(text))
    return True


def apply_local_filters(rows: list[dict[str, Any]], filters: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized_filters = list(filters or [])
    if not normalized_filters:
        return rows
    return [
        row
        for row in rows
        if all(
            _local_filter_matches(
                _row_value(row, str(item.get("id") or item.get("field") or "")),
                str(item.get("operator") or ""),
                item.get("value"),
            )
            for item in normalized_filters
        )
    ]


def project_rows(rows: list[dict[str, Any]], output_columns: list[str], max_rows: int | None) -> list[dict[str, Any]]:
    limited = rows if max_rows is None else rows[: max(0, max_rows)]
    return [
        {column_id: _row_value(row, column_id) for column_id in output_columns}
        for row in limited
    ]


def plan_with_default_calculation(plan: dict[str, Any], metric: str = "count") -> dict[str, Any]:
    if plan.get("calculation"):
        return plan
    return {
        **plan,
        "calculation": {
            "metric": _normalize_calculation_metric(metric),
            "field": None,
            "distinct_by": [],
            "group_by": [],
            "sort_by": None,
            "limit": None,
        },
    }


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


def _calculation_label(plan: dict[str, Any], calculation: dict[str, Any]) -> str:
    labels = plan.get("output_column_labels") or {}
    metric = calculation.get("metric")
    field = calculation.get("field")
    distinct_by = calculation.get("distinct_by") or []
    if metric == "count":
        return "Antal rader"
    if metric == "count_distinct":
        joined = " + ".join(str(labels.get(column) or column) for column in distinct_by)
        return f"Antal unika {joined}" if joined else "Antal unika"
    if metric == "sum":
        return f"Summa {labels.get(field) or field}"
    if metric == "avg":
        return f"Snitt {labels.get(field) or field}"
    if metric == "min":
        return f"Min {labels.get(field) or field}"
    if metric == "max":
        return f"Max {labels.get(field) or field}"
    if metric == "package_breakdown":
        return f"Antal förpackningar ({labels.get(field) or field})"
    return "Beräkning"


def _metric_value(rows: list[dict[str, Any]], calculation: dict[str, Any]) -> Any:
    metric = str(calculation.get("metric") or "count")
    field = calculation.get("field")
    if metric == "count":
        return len(rows)
    if metric == "count_distinct":
        columns = calculation.get("distinct_by") or ([field] if field else [])
        seen = {
            _stable_value_key([_row_value(row, column_id) for column_id in columns])
            for row in rows
        }
        return len(seen)
    if metric in {"sum", "avg"}:
        values = [
            number
            for row in rows
            if (number := _number_value(_row_value(row, str(field or "")))) is not None
        ]
        if not values:
            return 0
        total = sum(values)
        return _compact_number(total if metric == "sum" else total / len(values))
    if metric in {"min", "max"}:
        values = [
            _row_value(row, str(field or ""))
            for row in rows
            if _row_value(row, str(field or "")) not in (None, "")
        ]
        if not values:
            return None
        numeric_values = [_number_value(value) for value in values]
        if all(value is not None for value in numeric_values):
            selected = min(numeric_values) if metric == "min" else max(numeric_values)
            return _compact_number(selected)
        return (min if metric == "min" else max)(str(value) for value in values)
    if metric == "package_breakdown":
        raise DataFetchPlanError(
            "Förpacknings-uppdelning körs via en egen väg som även hämtar faktorerna i "
            f"{PACKAGE_ALIAS_VIEW}, inte via vanliga beräkningar."
        )
    raise DataFetchPlanError(f"Otillåten beräkning: {metric}")


def execute_calculation(rows: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any] | None:
    calculation = plan.get("calculation")
    if not calculation:
        return None

    label = _calculation_label(plan, calculation)
    value = _metric_value(rows, calculation)
    group_by = calculation.get("group_by") or []
    result: dict[str, Any] = {
        "metric": calculation.get("metric"),
        "label": label,
        "value": value,
        "field": calculation.get("field"),
        "distinct_by": calculation.get("distinct_by") or [],
        "group_by": group_by,
    }
    if not group_by:
        return result

    groups: dict[str, tuple[list[Any], list[dict[str, Any]]]] = {}
    for row in rows:
        values = [_row_value(row, column_id) for column_id in group_by]
        key = _stable_value_key(values)
        if key not in groups:
            groups[key] = (values, [])
        groups[key][1].append(row)

    group_rows: list[dict[str, Any]] = []
    for values, group_items in groups.values():
        item = {column_id: values[index] for index, column_id in enumerate(group_by)}
        item["value"] = _metric_value(group_items, calculation)
        group_rows.append(item)

    sort_by = calculation.get("sort_by") or {"field": "value", "direction": "desc"}
    sort_field = sort_by.get("field") or "value"
    reverse = sort_by.get("direction") != "asc"
    group_rows.sort(
        key=lambda item: (
            (0, _number_value(item.get(sort_field)))
            if _number_value(item.get(sort_field)) is not None
            else (1, str(item.get(sort_field) or ""))
        ),
        reverse=reverse,
    )
    group_rows.sort(key=lambda item: item.get(sort_field) is None)
    if calculation.get("limit"):
        group_rows = group_rows[: int(calculation["limit"])]

    labels = plan.get("output_column_labels") or {}
    result["rows"] = group_rows
    result["columns"] = [
        {"id": column_id, "label": str(labels.get(column_id) or column_id)}
        for column_id in group_by
    ] + [{"id": "value", "label": label}]
    return result


def _package_factor(value: Any) -> int | None:
    number = _number_value(value)
    if number is None:
        return None
    factor = int(round(number))
    return factor if factor >= 1 else None


def build_package_ladders(alias_rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[tuple[str, int]]]:
    """Bygg per (artikel, bolag) en lista (enhet, faktor) sorterad störst först.

    En bas-enhet med faktor 1 garanteras alltid finnas så att resten av en
    uppdelning alltid går jämnt ut.
    """
    grouped: dict[tuple[str, str], dict[int, str]] = {}
    for row in alias_rows or []:
        item = str(_row_value(row, PACKAGE_ALIAS_ITEM_FIELD) or "").strip()
        if not item:
            continue
        company = str(_row_value(row, PACKAGE_ALIAS_COMPANY_FIELD) or "").strip()
        factor = _package_factor(_row_value(row, PACKAGE_ALIAS_FACTOR_FIELD))
        if factor is None:
            continue
        unit = str(_row_value(row, PACKAGE_ALIAS_UNIT_FIELD) or "").strip() or PACKAGE_BASE_UNIT_LABEL
        units_by_factor = grouped.setdefault((item, company), {})
        units_by_factor.setdefault(factor, unit)

    ladders: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for key, units_by_factor in grouped.items():
        units_by_factor.setdefault(1, PACKAGE_BASE_UNIT_LABEL)
        ladders[key] = sorted(
            ((unit, factor) for factor, unit in units_by_factor.items()),
            key=lambda pair: pair[1],
            reverse=True,
        )
    return ladders


def split_quantity_into_packages(quantity: Any, ladder: list[tuple[str, int]]) -> dict[str, int]:
    """Greedy-uppdelning av ett antal i förpackningar, störst faktor först."""
    number = _number_value(quantity)
    if number is None:
        return {}
    remaining = int(number)
    if remaining <= 0:
        return {}
    steps = ladder or [(PACKAGE_BASE_UNIT_LABEL, 1)]
    result: dict[str, int] = {}
    for unit, factor in steps:
        if factor < 1 or remaining < factor:
            continue
        count = remaining // factor
        if count:
            result[unit] = result.get(unit, 0) + count
            remaining -= count * factor
        if remaining <= 0:
            break
    return result


def execute_package_breakdown(
    pick_rows: list[dict[str, Any]],
    alias_rows: list[dict[str, Any]],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Dela upp `field`-antalet per rad i förpackningar och summera per grupp + enhet.

    Uppdelningen sker per plockrad innan summering, så att t.ex. 15 + 15 med
    faktor 10 ger 2 storförpackningar + 10 styck, inte 3 av en hopslagen total.
    """
    calculation = plan.get("calculation") or {}
    field = str(calculation.get("field") or "")
    group_by = [str(column_id) for column_id in (calculation.get("group_by") or []) if str(column_id).strip()]
    ladders = build_package_ladders(alias_rows)
    default_ladder = [(PACKAGE_BASE_UNIT_LABEL, 1)]

    totals: dict[str, int] = {}
    groups: dict[str, tuple[list[Any], dict[str, int]]] = {}
    for row in pick_rows:
        item = str(_row_value(row, PACKAGE_JOIN_ITEM_FIELD) or "").strip()
        company = str(_row_value(row, PACKAGE_JOIN_COMPANY_FIELD) or "").strip()
        ladder = ladders.get((item, company)) or ladders.get((item, "")) or default_ladder
        packages = split_quantity_into_packages(_row_value(row, field), ladder)
        if not packages:
            continue
        group_values = [_row_value(row, column_id) for column_id in group_by]
        key = _stable_value_key(group_values)
        if key not in groups:
            groups[key] = (group_values, {})
        bucket = groups[key][1]
        for unit, count in packages.items():
            bucket[unit] = bucket.get(unit, 0) + count
            totals[unit] = totals.get(unit, 0) + count

    group_rows: list[dict[str, Any]] = []
    for group_values, bucket in groups.values():
        base = {column_id: group_values[index] for index, column_id in enumerate(group_by)}
        for unit, count in bucket.items():
            group_rows.append({**base, PACKAGE_UNIT_RESULT_FIELD: unit, "value": count})

    group_rows.sort(key=lambda item: str(item.get(PACKAGE_UNIT_RESULT_FIELD) or ""))
    group_rows.sort(key=lambda item: _number_value(item.get("value")) or 0, reverse=True)
    if calculation.get("limit"):
        group_rows = group_rows[: int(calculation["limit"])]

    labels = plan.get("output_column_labels") or {}
    label = _calculation_label(plan, calculation)
    columns = (
        [{"id": column_id, "label": str(labels.get(column_id) or column_id)} for column_id in group_by]
        + [{"id": PACKAGE_UNIT_RESULT_FIELD, "label": "Förpackning"}, {"id": "value", "label": "Antal"}]
    )
    return {
        "metric": "package_breakdown",
        "label": label,
        "value": sum(totals.values()),
        "field": field or None,
        "distinct_by": [],
        "group_by": group_by,
        "unit_totals": dict(sorted(totals.items(), key=lambda pair: pair[1], reverse=True)),
        "rows": group_rows,
        "columns": columns,
    }


def _sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "(" + ", ".join(_sql_literal(item) for item in value) + ")"
    return "'" + str(value).replace("'", "''") + "'"


def _like_pattern_for_operator(operator: str, value: object) -> str:
    text = str(value or "")
    if operator == "StartsWith":
        return f"{text.rstrip('%')}%"
    if operator == "EndsWith":
        return f"%{text.lstrip('%')}"
    if operator == "Contains":
        return f"%{text.strip('%')}%"
    return text


def _sql_where_clauses(plan: dict[str, Any]) -> list[str]:
    clauses: list[str] = []
    for item in plan.get("filters") or []:
        field = str(item.get("id") or item.get("field") or "").strip()
        operator = str(item.get("operator") or "EQ").strip()
        value = item.get("value")
        if not field:
            continue
        if operator == "Between" and isinstance(value, list) and len(value) == 2:
            clauses.append(f"{field} BETWEEN {_sql_literal(value[0])} AND {_sql_literal(value[1])}")
        elif operator == "Terms":
            values = value if isinstance(value, list) else [value]
            clauses.append(f"{field} IN {_sql_literal(values)}")
        elif operator in TEXT_FILTER_OPERATORS:
            clauses.append(f"{field} LIKE {_sql_literal(_like_pattern_for_operator(operator, value))}")
        else:
            sql_operator = {
                "EQ": "=",
                "NE": "<>",
                "GT": ">",
                "GTE": ">=",
                "LT": "<",
                "LTE": "<=",
            }.get(operator, "=")
            clauses.append(f"{field} {sql_operator} {_sql_literal(value)}")
    return clauses


def _sql_metric_expression(calculation: dict[str, Any]) -> str:
    metric = str(calculation.get("metric") or "count")
    field = str(calculation.get("field") or "").strip()
    if metric == "count":
        return "COUNT(*)"
    if metric == "count_distinct":
        columns = [str(column_id) for column_id in (calculation.get("distinct_by") or []) if str(column_id).strip()]
        if len(columns) == 1:
            return f"COUNT(DISTINCT {columns[0]})"
        return f"COUNT(DISTINCT ({', '.join(columns)}))"
    if metric == "sum":
        return f"SUM({field})"
    if metric == "avg":
        return f"AVG({field})"
    if metric == "min":
        return f"MIN({field})"
    if metric == "max":
        return f"MAX({field})"
    return "COUNT(*)"


def calculation_query_text(plan: dict[str, Any]) -> str:
    calculation = (plan.get("calculation") or {"metric": "count", "group_by": []})
    if str(calculation.get("metric") or "") == "package_breakdown":
        field = str(calculation.get("field") or "")
        group_by = [str(column_id) for column_id in (calculation.get("group_by") or []) if str(column_id).strip()]
        clauses = _sql_where_clauses(plan)
        where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        per = ", ".join([*group_by, PACKAGE_UNIT_RESULT_FIELD]) or PACKAGE_UNIT_RESULT_FIELD
        return (
            f"-- Förpacknings-uppdelning av {field} per rad.\n"
            f"-- Hämtar {plan.get('view')}{where_clause}, joinar mot {PACKAGE_ALIAS_VIEW} på "
            f"{PACKAGE_JOIN_ITEM_FIELD}+{PACKAGE_JOIN_COMPANY_FIELD}, delar upp {field} efter "
            f"{PACKAGE_ALIAS_FACTOR_FIELD} (störst först, faktor 1 = {PACKAGE_BASE_UNIT_LABEL}).\n"
            f"-- Summerar antal förpackningar per {per}."
        )
    group_by = [str(column_id) for column_id in (calculation.get("group_by") or []) if str(column_id).strip()]
    metric_expression = _sql_metric_expression(calculation)
    select_columns = [*group_by, f"{metric_expression} AS value"]
    clauses = _sql_where_clauses(plan)
    where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    group_clause = f" GROUP BY {', '.join(group_by)}" if group_by else ""
    sort_by = calculation.get("sort_by") or None
    order_clause = ""
    if isinstance(sort_by, dict):
        sort_field = str(sort_by.get("field") or "value")
        direction = str(sort_by.get("direction") or "desc").upper()
        if direction not in {"ASC", "DESC"}:
            direction = "DESC"
        order_clause = f" ORDER BY {sort_field} {direction}"
    elif group_by:
        order_clause = " ORDER BY value DESC"
    limit_clause = f" LIMIT {int(calculation['limit'])}" if calculation.get("limit") else ""
    return f"SELECT {', '.join(select_columns)} FROM {plan.get('view')}{where_clause}{group_clause}{order_clause}{limit_clause};"


def columns_for_response(plan: dict[str, Any]) -> list[dict[str, str]]:
    labels = plan.get("output_column_labels") or {}
    return [
        {"id": column_id, "label": str(labels.get(column_id) or column_id)}
        for column_id in plan.get("output_columns", [])
    ]

"""MiniMax-payload, plan-parsning och planvalidering för Hämta data."""
from __future__ import annotations

import json
import re
from typing import Any

from ..config import settings
from . import core
from .core import (
    ALLOWED_CALCULATION_METRICS,
    ALLOWED_OPERATORS,
    CALCULATION_METRIC_ALIASES,
    OPERATOR_ALIASES,
    TEXT_FILTER_OPERATORS,
    DataCatalog,
    DataColumn,
    DataFetchPlanError,
    DataView,
    _normalize_filter_value,
    _period_values_for_column,
    _preferred_date_column,
    infer_prompt_period,
)


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
    app_today = core._app_now().date()
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

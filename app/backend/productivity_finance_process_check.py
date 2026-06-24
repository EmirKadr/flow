from __future__ import annotations

from calendar import monthrange
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from typing import Any, Callable

from sqlalchemy.orm import Session

from .data_fetch_service import (
    DataFetchConfigError,
    DataFetchPlanError,
    _date_period_payload,
    _period_values_for_column,
    _preferred_date_column,
    apply_local_filters,
    calculation_query_text,
    execute_calculation,
    load_catalog,
    plan_with_default_calculation,
)
from .models import Business
from .productivity_kpi_rules import (
    KpiLogEvent,
    _event_company,
    _event_timestamp,
    _event_warehouse,
    _rule_context,
    load_kpi_rules,
)
from .productivity_service import SOURCE_SPEC_BY_KEY
from .settings_service import clean_productivity_finance_company_code


FetchRows = Callable[[dict, str, str | None], list[dict[str, Any]]]

DIAGNOSTIC_COLUMNS = (
    "order_num",
    "Ordernr",
    "Order nr",
    "Order",
    "company",
    "Bolag",
    "wareh_num",
    "Lager",
    "pick_zone",
    "Zon",
    "type",
    "Typ",
    "status",
    "Status",
)

RULE_CRITERIA_COLUMNS = {
    "company": ("Bolag", ("company", "Bolag")),
    "zone": ("Zon", ("pick_zone", "Zon")),
    "type": ("Typ", ("type", "Typ")),
    "status": ("Status", ("status", "Status")),
    "loc_from_equals": ("Från", ("loc_from", "Från", "Fran")),
    "loc_to_equals": ("Till", ("loc_to", "Till")),
    "location_starts": ("Lagerplats", ("location", "Lagerplats", "Lokation")),
}


@dataclass(frozen=True)
class RowHit:
    source: str
    row_key: str
    row: dict[str, Any]


def _comparison_columns_for_plan(plan: dict[str, Any]) -> list[str]:
    calculation = plan.get("calculation") or {}
    metric = str(calculation.get("metric") or "")
    columns = calculation.get("distinct_by") or []
    if metric == "count_distinct" and not columns and calculation.get("field"):
        columns = [calculation.get("field")]
    if metric != "count_distinct":
        return []
    return [str(column).strip() for column in columns if str(column).strip()]


def _comparison_key_label(columns: list[str]) -> str:
    return " + ".join(columns) if columns else "rad"


def _comparison_key_for_hit(hit: RowHit, columns: list[str]) -> str:
    if not columns:
        return hit.row_key
    values = [str(_column_value(hit.row, column) or "").strip() for column in columns]
    if not any(values):
        return hit.row_key
    return f"{_comparison_key_label(columns)}:{json.dumps(values, ensure_ascii=False, default=str)}"


def _period_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _safe_row_key(row: dict[str, Any], index: int) -> str:
    for key in ("rowid", "row_id", "id"):
        value = row.get(key)
        if value not in (None, ""):
            return f"{key}:{value}"
    try:
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        payload = str(sorted((str(key), str(value)) for key, value in row.items()))
    return f"row:{payload}"


def _column_value(row: dict[str, Any], *names: str) -> Any:
    normalized = {str(key).strip().casefold(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(str(name).strip().casefold())
        if value not in (None, ""):
            return value
    return ""


def _criterion_text(value: Any) -> str:
    if isinstance(value, bool) or value in (None, ""):
        return ""
    try:
        number = float(str(value).replace(",", "."))
    except ValueError:
        return str(value).strip().upper()
    return str(int(number)) if number.is_integer() else str(value).strip().upper()


def _criterion_sort_key(value: str) -> tuple[int, float | str]:
    try:
        return (0, float(value))
    except ValueError:
        return (1, value)


def _event_from_row(source: str, row: dict[str, Any], index: int, fallback_date: date) -> KpiLogEvent:
    string_row = {str(key): "" if value is None else str(value) for key, value in row.items()}
    timestamp = _event_timestamp(string_row, source)
    if timestamp is None:
        timestamp = datetime.combine(fallback_date, datetime.min.time(), tzinfo=timezone.utc)
    return KpiLogEvent(
        source=source,
        user=str(_column_value(string_row, "Användare", "Anvandare", "user_id", "username") or ""),
        company=_event_company(string_row, source),
        warehouse=_event_warehouse(string_row, source),
        timestamp=timestamp,
        row=string_row,
        row_index=index,
    )


def _source_for_view(view_id: object) -> str | None:
    view = str(view_id or "").strip()
    for source, spec in SOURCE_SPEC_BY_KEY.items():
        if spec.prefix == view:
            return source
    return None


def _company_column_id(view: Any) -> str | None:
    for column_id in ("company", "company_code", "bolag", "Bolag"):
        if column_id in getattr(view, "column_by_id", {}):
            return column_id
    for column in getattr(view, "columns", ()):
        label = f"{getattr(column, 'id', '')} {getattr(column, 'label_en', '')} {getattr(column, 'label_sv', '')}".lower()
        if "company" in label or "bolag" in label:
            return str(getattr(column, "id", "") or "")
    return None


def _replace_period_and_company_filters(plan: dict, *, company_code: str, start: date, end: date) -> dict:
    result = deepcopy(plan)
    catalog = load_catalog()
    view = catalog.view(str(result.get("view") or ""))
    date_column = _preferred_date_column(view)
    company_column = _company_column_id(view)
    period = _date_period_payload("month", start, end)
    filters: list[dict[str, Any]] = []
    period_added = False
    company_added = False
    for item in result.get("filters") or []:
        column_id = item.get("id") or item.get("field")
        operator = str(item.get("operator") or "")
        if date_column is not None and column_id == date_column.id and operator == "Between":
            if not period_added:
                filters.append({**item, "id": date_column.id, "operator": "Between", "value": _period_values_for_column(period, date_column)})
                period_added = True
            continue
        if company_column and column_id == company_column and company_code:
            if not company_added:
                filters.append({"id": company_column, "operator": "EQ", "value": company_code})
                company_added = True
            continue
        filters.append(dict(item))
    if date_column is not None and not period_added:
        filters.append({"id": date_column.id, "operator": "Between", "value": _period_values_for_column(period, date_column)})
    if company_column and company_code and not company_added:
        filters.append({"id": company_column, "operator": "EQ", "value": company_code})
    result["filters"] = filters
    return plan_with_default_calculation(result, "count")


def _source_plan(source: str, *, company_code: str, start: date, end: date) -> dict:
    spec = SOURCE_SPEC_BY_KEY[source]
    plan = {
        "status": "ok",
        "view": spec.prefix,
        "view_label": spec.label,
        "output_columns": [],
        "filters": [],
        "identifiers": [],
    }
    return _replace_period_and_company_filters(plan, company_code=company_code, start=start, end=end)


def _rule_filter_column(criterion: str) -> tuple[str, str] | None:
    if criterion == "company":
        return "company", "Terms"
    if criterion == "zone":
        return "pick_zone", "Terms"
    if criterion == "type":
        return "type", "Terms"
    if criterion == "status":
        return "status", "Terms"
    if criterion == "loc_from_equals":
        return "loc_from", "Terms"
    if criterion == "loc_to_equals":
        return "loc_to", "Terms"
    if criterion == "location_starts":
        return "location", "StartsWith"
    return None


def _rule_filter_items(rule: Any) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []
    for criterion, values in (getattr(rule, "criteria", {}) or {}).items():
        mapping = _rule_filter_column(str(criterion))
        cleaned_values = sorted(
            (str(value).strip() for value in (values or []) if str(value).strip()),
            key=_criterion_sort_key,
        )
        if mapping is None or not cleaned_values:
            continue
        column_id, operator = mapping
        if operator == "StartsWith":
            filters.append({"id": column_id, "operator": operator, "value": cleaned_values[0]})
        else:
            filters.append({
                "id": column_id,
                "operator": "Terms" if len(cleaned_values) > 1 else "EQ",
                "value": cleaned_values if len(cleaned_values) > 1 else cleaned_values[0],
            })
    return filters


def _process_sql_for_rules(source: str, rules: list[Any], *, company_code: str, start: date, end: date) -> str:
    statements: list[str] = []
    for rule in rules:
        plan = _source_plan(source, company_code=company_code, start=start, end=end)
        plan["filters"] = [*list(plan.get("filters") or []), *_rule_filter_items(rule)]
        plan["calculation"] = {"metric": "count", "field": None, "distinct_by": [], "group_by": [], "sort_by": None, "limit": None}
        metric = str(getattr(rule, "metric", "") or "rows")
        statements.append(f"-- {getattr(rule, 'process', None) or rule.process_key} / {metric}\n{calculation_query_text(plan)}")
    return "\n\n".join(statements)


def _row_hits(source: str, rows: list[dict[str, Any]]) -> dict[str, RowHit]:
    return {
        _safe_row_key(row, index): RowHit(source=source, row_key=_safe_row_key(row, index), row=row)
        for index, row in enumerate(rows)
    }


def _diagnostic_summary(hits: list[RowHit], *, limit: int = 8) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for hit in hits:
        values = []
        for column in DIAGNOSTIC_COLUMNS:
            value = _column_value(hit.row, column)
            if value not in (None, ""):
                values.append((column, str(value)))
        key = json.dumps(values, ensure_ascii=False, sort_keys=True)
        bucket = buckets.setdefault(key, {"count": 0, "values": {column: value for column, value in values}})
        bucket["count"] += 1
    return sorted(buckets.values(), key=lambda item: (-int(item["count"]), str(item["values"])))[:limit]


def _rule_gap_summary(rules: list[Any], hits: list[RowHit], *, limit: int = 8) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for rule in rules:
        criteria = getattr(rule, "criteria", {}) or {}
        if not criteria:
            continue
        for hit in hits:
            for criterion, expected_values in criteria.items():
                label, columns = RULE_CRITERIA_COLUMNS.get(str(criterion), (str(criterion), (str(criterion),)))
                actual = _criterion_text(_column_value(hit.row, *columns))
                expected = tuple(
                    sorted(
                        (str(value).strip().upper() for value in expected_values if str(value).strip()),
                        key=_criterion_sort_key,
                    )
                )
                if not actual or not expected:
                    continue
                if criterion == "location_starts":
                    matches = any(actual.startswith(value) for value in expected)
                else:
                    matches = actual in expected
                if matches:
                    continue
                key = json.dumps(
                    {
                        "process_key": rule.process_key,
                        "criterion": criterion,
                        "expected": expected,
                        "actual": actual,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                bucket = buckets.setdefault(
                    key,
                    {
                        "count": 0,
                        "process": rule.process,
                        "process_key": rule.process_key,
                        "field": label,
                        "expected": "/".join(expected),
                        "actual": actual,
                    },
                )
                bucket["count"] += 1
    return sorted(buckets.values(), key=lambda item: (-int(item["count"]), str(item["process"]), str(item["field"])))[:limit]


def _exception_message(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        message = detail.get("message") or detail.get("detail") or detail.get("error")
    elif detail not in (None, ""):
        message = detail
    else:
        message = str(exc)
    return str(message or "Källan kunde inte hämtas.").strip()


def _source_display_name(source: str | None, plan: dict | None = None) -> str:
    if plan:
        view_label = str(plan.get("view_label") or "").strip()
        if view_label:
            return view_label
    spec = SOURCE_SPEC_BY_KEY.get(str(source or ""))
    if spec is not None:
        return spec.label
    if plan:
        view = str(plan.get("view") or "").strip()
        if view:
            return view
    return str(source or "källan")


def _revenue_label(row: dict[str, Any]) -> str:
    return " | ".join(
        part
        for part in (
            str(row.get("service") or "").strip(),
            str(row.get("description") or "").strip(),
            str(row.get("unit") or "").strip(),
        )
        if part
    ) or str(row.get("id") or "Intäktsrad")


def _rule_assignments(
    db: Session,
    *,
    business_id: int | None,
    rows_by_source: dict[str, list[dict[str, Any]]],
    start: date,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, RowHit]]]:
    rules, _source = load_kpi_rules(db, business_id=business_id, allow_empty=True)
    events_by_source = {
        source: [
            _event_from_row(source, row, index, start)
            for index, row in enumerate(rows)
        ]
        for source, rows in rows_by_source.items()
    }
    context = _rule_context(events_by_source)
    hits_by_source = {source: _row_hits(source, rows) for source, rows in rows_by_source.items()}
    assignments: dict[str, list[dict[str, Any]]] = {}
    for source, events in events_by_source.items():
        for index, event in enumerate(events):
            row_key = _safe_row_key(rows_by_source[source][index], index)
            for rule in rules:
                if rule.source != source:
                    continue
                if rule.predicate(event, context):
                    assignments.setdefault(row_key, []).append(
                        {
                            "process": rule.process,
                            "process_key": rule.process_key,
                            "metric": rule.metric,
                            "source": rule.source,
                            "rule_key": rule.sql_key,
                        }
                    )
    return assignments, hits_by_source


def _distinct_processes(assignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for item in assignments:
        key = str(item.get("process_key") or "")
        if not key:
            continue
        by_key.setdefault(
            key,
            {
                "process": item.get("process") or key,
                "process_key": key,
                "source": item.get("source"),
                "metrics": sorted({str(entry.get("metric") or "") for entry in assignments if entry.get("process_key") == key}),
            },
        )
    return sorted(by_key.values(), key=lambda item: str(item["process"]).upper())


def build_productivity_finance_process_check(
    db: Session,
    *,
    business: Business | None,
    finance_settings: dict[str, Any],
    month: int,
    year: int,
    company_code: str | None,
    fetch_rows: FetchRows,
    tenant: str | None,
    row_id: str | None = None,
) -> dict[str, Any]:
    start, end = _period_bounds(year, month)
    allowed_codes = [
        clean_productivity_finance_company_code(code)
        for code in (getattr(business, "company_codes", None) or [])
        if clean_productivity_finance_company_code(code)
    ]
    selected_code = clean_productivity_finance_company_code(company_code)
    company_codes = [selected_code] if selected_code else allowed_codes
    selected_row_id = str(row_id or "").strip()
    invoice_rows_by_company = finance_settings.get("invoice_rows_by_company") or {}
    source_rows: dict[str, list[dict[str, Any]]] = {}
    source_payloads: dict[str, dict[str, Any]] = {}
    source_errors: dict[str, str] = {}
    broad_sources: set[str] = set()
    revenue_checks: list[dict[str, Any]] = []
    revenue_hits_by_source: dict[str, dict[str, list[dict[str, Any]]]] = {}
    warnings: list[str] = []
    candidate_revenue_rows: list[tuple[str, dict[str, Any], dict[str, Any], str | None, str]] = []
    target_sources: set[str] = set()

    for company in company_codes:
        for row in invoice_rows_by_company.get(company) or []:
            if selected_row_id and str(row.get("id") or "") != selected_row_id:
                continue
            if row.get("collar_type") or row.get("vas_rate_type"):
                continue
            plan = row.get("calculation_plan")
            if not isinstance(plan, dict) or not plan.get("view"):
                continue
            source = _source_for_view(plan.get("view"))
            label = _revenue_label(row)
            candidate_revenue_rows.append((company, row, plan, source, label))
            if source:
                target_sources.add(source)

    def fetch_source(source: str, plan: dict) -> list[dict[str, Any]]:
        if source in source_rows:
            return source_rows[source]
        if source in source_errors:
            return []
        rows = fetch_rows(plan, "finance-process-check", tenant)
        source_rows[source] = rows
        source_payloads[source] = {
            "source": source,
            "view": plan.get("view"),
            "view_label": _source_display_name(source, plan),
            "rows": len(rows),
            "status": "ok",
        }
        broad_sources.add(source)
        return rows

    kpi_rules, _rule_source = load_kpi_rules(db, business_id=getattr(business, "id", None), allow_empty=True)
    rules_by_source_process: dict[tuple[str, str], list[Any]] = {}
    for rule in kpi_rules:
        rules_by_source_process.setdefault((rule.source, rule.process_key), []).append(rule)
    sources_to_fetch = target_sources if selected_row_id else {rule.source for rule in kpi_rules}
    for source in sorted(sources_to_fetch):
        try:
            fetch_source(source, _source_plan(source, company_code=selected_code, start=start, end=end))
        except (DataFetchConfigError, DataFetchPlanError, KeyError) as exc:
            source_payloads[source] = {
                "source": source,
                "view": getattr(SOURCE_SPEC_BY_KEY.get(source), "prefix", source),
                "view_label": _source_display_name(source),
                "rows": 0,
                "status": "skipped",
                "message": _exception_message(exc),
            }
        except Exception as exc:
            message = _exception_message(exc)
            source_errors[source] = message
            source_payloads[source] = {
                "source": source,
                "view": getattr(SOURCE_SPEC_BY_KEY.get(source), "prefix", source),
                "view_label": _source_display_name(source),
                "rows": 0,
                "status": "error",
                "message": message,
            }
            warnings.append(f"Kunde inte hämta KPI-källa {_source_display_name(source)}: {message}")

    for company, row, plan, source, label in candidate_revenue_rows:
            check = {
                "company": company,
                "row_id": row.get("id"),
                "label": label,
                "view": plan.get("view"),
                "view_label": _source_display_name(source, plan),
                "source": source,
                "price": float(row.get("price") or 0.0),
                "quantity": 0.0,
                "revenue": 0.0,
                "row_count": 0,
                "calculation_prompt": str(row.get("calculation_prompt") or ""),
                "saved_calculation_sql": str(row.get("calculation_sql") or ""),
                "calculation_sql": "",
                "comparison_key_columns": [],
                "comparison_key_label": "rad",
                "comparison_key_count": 0,
                "matched_processes": [],
                "combined_process_coverage": None,
                "same_view_processes": [],
                "missing_in_kpi_count": 0,
                "missing_in_kpi": [],
                "rule_gaps": [],
                "status": "info",
                "messages": [],
            }
            if source is None:
                check["messages"].append("Intäktsraden använder en källa som inte finns i KPI-processerna.")
                revenue_checks.append(check)
                continue
            if source_errors.get(source):
                check["status"] = "error"
                check["messages"].append(
                    f"Kontrollen hoppades över eftersom {_source_display_name(source, plan)} inte kunde hämtas."
                )
                revenue_checks.append(check)
                continue
            try:
                period_plan = _replace_period_and_company_filters(plan, company_code=company, start=start, end=end)
                if source in broad_sources and not period_plan.get("identifiers"):
                    rows = apply_local_filters(source_rows.get(source, []), period_plan.get("filters") or [])
                else:
                    rows = fetch_rows(period_plan, "finance-process-check-revenue", tenant)
                calculation = execute_calculation(rows, period_plan)
                quantity = calculation.get("value") if calculation else len(rows)
                if not isinstance(quantity, (int, float)):
                    quantity = len(rows)
                row_hits = _row_hits(source, rows)
                comparison_columns = _comparison_columns_for_plan(period_plan)
                revenue_hits_by_source.setdefault(source, {})[str(row.get("id") or label)] = [
                    {
                        "company": company,
                        "label": label,
                        "row_key": row_key,
                        "comparison_key": _comparison_key_for_hit(hit, comparison_columns),
                    }
                    for row_key, hit in row_hits.items()
                ]
                check.update(
                    {
                        "quantity": float(quantity),
                        "revenue": round(float(quantity) * float(row.get("price") or 0.0), 2),
                        "row_count": len(rows),
                        "comparison_key_columns": comparison_columns,
                        "comparison_key_label": _comparison_key_label(comparison_columns),
                        "comparison_key_count": len({
                            _comparison_key_for_hit(hit, comparison_columns)
                            for hit in row_hits.values()
                        }),
                        "calculation_sql": calculation_query_text(period_plan),
                    }
                )
                if source not in source_rows:
                    source_rows[source] = rows
                revenue_checks.append(check)
            except Exception as exc:
                message = _exception_message(exc)
                source_errors[source] = message
                source_payloads[source] = {
                    "source": source,
                    "view": plan.get("view"),
                    "view_label": _source_display_name(source, plan),
                    "rows": 0,
                    "status": "error",
                    "message": message,
                }
                check["status"] = "error"
                check["messages"].append(f"Källan {_source_display_name(source, plan)} kunde inte hämtas: {message}")
                revenue_checks.append(check)

    assignments, source_hits = _rule_assignments(
        db,
        business_id=getattr(business, "id", None),
        rows_by_source=source_rows,
        start=start,
    )
    all_revenue_row_keys_by_source = {
        source: {
            item["row_key"]
            for rows in by_row.values()
            for item in rows
        }
        for source, by_row in revenue_hits_by_source.items()
    }
    process_row_keys: dict[tuple[str, str], set[str]] = {}
    for row_key, row_assignments in assignments.items():
        for assignment in row_assignments:
            source = str(assignment.get("source") or "")
            process_key = str(assignment.get("process_key") or "")
            if source and process_key:
                process_row_keys.setdefault((source, process_key), set()).add(row_key)

    def assignments_for(source: str, row_key: str) -> list[dict[str, Any]]:
        return [
            assignment
            for assignment in assignments.get(row_key, [])
            if str(assignment.get("source") or "") == source
        ]

    def comparison_key_for_row_key(source: str, row_key: str, columns: list[str]) -> str:
        hit = source_hits.get(source, {}).get(row_key)
        return _comparison_key_for_hit(hit, columns) if hit is not None else row_key

    def representative_hits_for_comparison_keys(
        source: str,
        row_keys: set[str],
        columns: list[str],
        comparison_keys: set[str],
    ) -> list[RowHit]:
        hits_by_key: dict[str, RowHit] = {}
        for row_key in row_keys:
            hit = source_hits.get(source, {}).get(row_key)
            if hit is None:
                continue
            key = _comparison_key_for_hit(hit, columns)
            hits_by_key.setdefault(key, hit)
        return [hits_by_key[key] for key in sorted(comparison_keys) if key in hits_by_key]

    def public_process_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in candidate.items() if not key.startswith("_")}

    def process_summary(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "process": candidate.get("process"),
            "process_key": candidate.get("process_key"),
            "source": candidate.get("source"),
            "metrics": candidate.get("metrics") or [],
            "process_sql": candidate.get("process_sql") or "",
        }

    def best_process_combination(candidates: list[dict[str, Any]], revenue_keys: set[str]) -> dict[str, Any]:
        remaining = set(revenue_keys)
        selected: list[dict[str, Any]] = []
        selected_keys: set[str] = set()
        while remaining:
            best: dict[str, Any] | None = None
            best_new_keys: set[str] = set()
            best_score: tuple[int, int, int, str] | None = None
            for candidate in candidates:
                process_key = str(candidate.get("process_key") or "")
                if not process_key or process_key in selected_keys:
                    continue
                process_keys = set(candidate.get("_comparison_keys") or set())
                new_keys = remaining & process_keys
                if not new_keys:
                    continue
                score = (
                    len(new_keys),
                    -len(process_keys - revenue_keys),
                    len(process_keys),
                    str(candidate.get("process") or process_key).upper(),
                )
                if best_score is None or score > best_score:
                    best = candidate
                    best_new_keys = new_keys
                    best_score = score
            if best is None:
                break
            selected.append(best)
            selected_keys.add(str(best.get("process_key") or ""))
            remaining -= best_new_keys
        union_keys = set()
        for candidate in selected:
            union_keys.update(set(candidate.get("_comparison_keys") or set()))
        covered_keys = revenue_keys & union_keys
        return {
            "processes": [process_summary(candidate) for candidate in selected],
            "covered_keys": covered_keys,
            "process_keys": union_keys,
        }

    def same_view_processes(source: str, revenue_keys: set[str], comparison_columns: list[str]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for (rule_source, process_key), rules in rules_by_source_process.items():
            if rule_source != source or not process_key:
                continue
            process_row_key_set = process_row_keys.get((source, process_key), set())
            process_keys = {
                comparison_key_for_row_key(source, row_key, comparison_columns)
                for row_key in process_row_key_set
            }
            overlap_count = len(revenue_keys & process_keys)
            row_count = len(revenue_keys)
            process_count = len(process_keys)
            first_rule = rules[0]
            metrics = sorted({str(getattr(rule, "metric", "") or "") for rule in rules if getattr(rule, "metric", "")})
            candidates.append(
                {
                    "process": getattr(first_rule, "process", None) or process_key,
                    "process_key": process_key,
                    "source": source,
                    "metrics": metrics,
                    "process_sql": _process_sql_for_rules(source, list(rules), company_code=selected_code, start=start, end=end),
                    "comparison_key_label": _comparison_key_label(comparison_columns),
                    "revenue_row_count": row_count,
                    "process_row_count": process_count,
                    "overlap_count": overlap_count,
                    "missing_from_process_count": max(row_count - overlap_count, 0),
                    "extra_in_process_count": max(process_count - overlap_count, 0),
                    "count_difference": process_count - row_count,
                    "_row_keys": process_row_key_set,
                    "_comparison_keys": process_keys,
                }
            )
        return sorted(
            candidates,
            key=lambda item: (
                -int(item["overlap_count"]),
                -int(item["process_row_count"]),
                str(item["process"]).upper(),
            ),
        )

    for check in revenue_checks:
        if check.get("status") == "error":
            continue
        source = check.get("source")
        if not source:
            continue
        row_items = revenue_hits_by_source.get(str(source), {}).get(str(check.get("row_id") or check.get("label")), [])
        row_keys = {item["row_key"] for item in row_items}
        comparison_columns = [str(column) for column in (check.get("comparison_key_columns") or []) if str(column).strip()]
        comparison_label = _comparison_key_label(comparison_columns)
        revenue_keys = {
            str(item.get("comparison_key") or item.get("row_key") or "")
            for item in row_items
            if item.get("comparison_key") or item.get("row_key")
        }
        same_view_candidates = same_view_processes(str(source), revenue_keys, comparison_columns)
        overlapping_candidates = [
            candidate
            for candidate in same_view_candidates
            if int(candidate.get("overlap_count") or 0) > 0
        ]
        combination = best_process_combination(overlapping_candidates, revenue_keys)
        combination_processes = combination["processes"]
        covered_keys = set(combination["covered_keys"])
        process_keys_for_combination = set(combination["process_keys"])
        matched = [process_summary(candidate) for candidate in overlapping_candidates]
        missing_keys = revenue_keys - covered_keys
        selected_process_row_keys = {
            row_key
            for candidate in overlapping_candidates
            if any(str(process.get("process_key") or "") == str(candidate.get("process_key") or "") for process in combination_processes)
            for row_key in set(candidate.get("_row_keys") or set())
        }
        missing_hits = representative_hits_for_comparison_keys(str(source), row_keys, comparison_columns, missing_keys)
        matched_rules = [
            rule
            for process in matched
            for rule in rules_by_source_process.get((str(source), str(process.get("process_key") or "")), [])
        ]
        extra_keys = process_keys_for_combination - revenue_keys
        extra_hits = representative_hits_for_comparison_keys(
            str(source),
            selected_process_row_keys,
            comparison_columns,
            extra_keys,
        )
        check["matched_processes"] = matched
        check["same_view_processes"] = [public_process_candidate(candidate) for candidate in same_view_candidates]
        check["comparison_key_count"] = len(revenue_keys)
        check["combined_process_coverage"] = {
            "key_label": comparison_label,
            "revenue_key_count": len(revenue_keys),
            "covered_key_count": len(covered_keys),
            "missing_key_count": len(missing_keys),
            "extra_key_count": len(extra_keys),
            "coverage_pct": round((len(covered_keys) / len(revenue_keys)) * 100.0, 1) if revenue_keys else 0.0,
            "processes": combination_processes,
        } if combination_processes or revenue_keys else None
        check["missing_in_kpi_count"] = len(missing_keys)
        check["missing_in_kpi"] = _diagnostic_summary(missing_hits)
        check["rule_gaps"] = _rule_gap_summary(matched_rules, missing_hits)
        check["process_extra_count"] = len(extra_keys)
        check["process_extra"] = _diagnostic_summary(extra_hits)
        if missing_keys:
            check["status"] = "warning"
            if matched:
                check["messages"].append("Intäktsraden är delvis täckt av KPI-processer, men några rader faller utanför regelvillkoren.")
            else:
                check["messages"].append("Intäktsraden har rader som ingen KPI-process verkar räkna.")
        elif matched:
            check["status"] = "ok"
            check["messages"].append("Intäktsraden verkar täckas av KPI-processer.")
            if len(matched) > 1:
                check["messages"].append("Flera KPI-processer verkar tillsammans täcka intäktsraden.")
            if extra_keys:
                check["messages"].append("Matchande KPI-processer räknar även rader utanför den här intäktsraden.")
        elif same_view_candidates:
            check["status"] = "warning"
            check["messages"].append("KPI-processer anvÃ¤nder samma vy, men filtren gav inget tydligt radÃ¶verlapp.")
        else:
            check["status"] = "info"
            check["messages"].append("Ingen tydlig KPI-processmatch hittades.")

    duplicate_kpi: list[dict[str, Any]] = []
    process_rows: dict[str, dict[str, Any]] = {}
    for source, hits in source_hits.items():
        for row_key, hit in hits.items():
            processes = _distinct_processes(assignments_for(source, row_key))
            if len(processes) > 1:
                duplicate_kpi.append(
                    {
                        "source": source,
                        "processes": processes,
                        "count": 1,
                        "rows": _diagnostic_summary([hit], limit=1),
                    }
                )
            for process in processes:
                key = f"{source}:{process['process_key']}"
                bucket = process_rows.setdefault(
                    key,
                    {
                        "source": source,
                        "process": process["process"],
                        "process_key": process["process_key"],
                        "row_count": 0,
                        "missing_in_revenue_count": 0,
                        "missing_in_revenue": [],
                    },
                )
                bucket["row_count"] += 1
                if row_key not in all_revenue_row_keys_by_source.get(source, set()):
                    bucket.setdefault("_missing_hits", []).append(hit)
    for bucket in process_rows.values():
        missing_hits = bucket.pop("_missing_hits", [])
        bucket["missing_in_revenue_count"] = len(missing_hits)
        bucket["missing_in_revenue"] = _diagnostic_summary(missing_hits)

    duplicate_revenue: list[dict[str, Any]] = []
    for source, by_row in revenue_hits_by_source.items():
        row_map: dict[str, list[dict[str, Any]]] = {}
        for rows in by_row.values():
            for item in rows:
                row_map.setdefault(item["row_key"], []).append(item)
        for row_key, rows in row_map.items():
            labels = sorted({str(row["label"]) for row in rows})
            if len(labels) <= 1:
                continue
            hit = source_hits.get(source, {}).get(row_key)
            duplicate_revenue.append(
                {
                    "source": source,
                    "revenue_rows": labels,
                    "count": 1,
                    "rows": _diagnostic_summary([hit], limit=1) if hit is not None else [],
                }
            )

    summary = {
        "revenue_rows": len(revenue_checks),
        "matched_revenue_rows": len([item for item in revenue_checks if item.get("status") == "ok"]),
        "warning_revenue_rows": len([item for item in revenue_checks if item.get("status") == "warning"]),
        "error_revenue_rows": len([item for item in revenue_checks if item.get("status") == "error"]),
        "missing_in_kpi": sum(int(item.get("missing_in_kpi_count") or 0) for item in revenue_checks),
        "missing_in_revenue": sum(int(item.get("missing_in_revenue_count") or 0) for item in process_rows.values()),
        "duplicate_kpi": len(duplicate_kpi),
        "duplicate_revenue": len(duplicate_revenue),
    }
    return {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "period": {"year": year, "month": month, "start_date": start.isoformat(), "end_date": end.isoformat()},
        "company_codes": company_codes,
        "target_row_id": selected_row_id or None,
        "sources": sorted(source_payloads.values(), key=lambda item: str(item.get("source") or "")),
        "summary": summary,
        "revenue_checks": revenue_checks,
        "process_checks": sorted(process_rows.values(), key=lambda item: (str(item["source"]), str(item["process"]).upper())),
        "duplicates": {
            "kpi": duplicate_kpi[:50],
            "revenue": duplicate_revenue[:50],
        },
        "warnings": warnings,
    }

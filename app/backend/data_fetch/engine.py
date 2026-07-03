"""Deterministisk beräkningsmotor: lokala filter, metrik och package breakdown.

Detta är mattan som MiniMax aldrig gör själv - all beräkning sker i testad kod.
"""
from __future__ import annotations

import re
from typing import Any

from .core import (
    LOCAL_FILTER_OPERATORS,
    PACKAGE_ALIAS_COMPANY_FIELD,
    PACKAGE_ALIAS_FACTOR_FIELD,
    PACKAGE_ALIAS_ITEM_FIELD,
    PACKAGE_ALIAS_UNIT_FIELD,
    PACKAGE_ALIAS_VIEW,
    PACKAGE_BASE_UNIT_LABEL,
    PACKAGE_JOIN_COMPANY_FIELD,
    PACKAGE_JOIN_ITEM_FIELD,
    PACKAGE_UNIT_RESULT_FIELD,
    TEXT_FILTER_OPERATORS,
    DataFetchPlanError,
    _compact_number,
    _number_value,
    _row_value,
    _stable_value_key,
)
from .plan import _normalize_calculation_metric


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

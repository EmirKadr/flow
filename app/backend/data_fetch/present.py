"""SQL-beskrivningstext och kolumnpresentation för Hämta data-svar."""
from __future__ import annotations

from typing import Any

from .core import (
    PACKAGE_ALIAS_FACTOR_FIELD,
    PACKAGE_ALIAS_VIEW,
    PACKAGE_BASE_UNIT_LABEL,
    PACKAGE_JOIN_COMPANY_FIELD,
    PACKAGE_JOIN_ITEM_FIELD,
    PACKAGE_UNIT_RESULT_FIELD,
    TEXT_FILTER_OPERATORS,
)


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

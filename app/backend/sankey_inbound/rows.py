"""Radnormalisering och perioder för Sankey Inbound: kolumnuppslag, datum, priser."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..productivity_service import _number
from ..settings_service import (
    clean_productivity_finance_company_code,
    productivity_finance_default_invoice_rows,
)
from .common import (
    INBOUND_LABEL_ROW_ID,
    INBOUND_PURCHASE_LINE_ROW_ID,
    OUTBOUND_METRICS,
)


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

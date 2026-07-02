"""Finans- och business-summary-hjalpare for produktivitetsrouten.

Utdelat ur productivity_helpers.py for radtaket i arkitektur-kontraktet.
"""
import asyncio
import json
import queue
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import logging
from pathlib import Path
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from .. import audit
from ..business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code, scoped_get, user_business_id
from ..database import SessionLocal
from ..deps import get_db, require_view_access
from ..models import Activity, Business, Person, User
from ..productivity_service import (
    ProductivitySourceError,
    _number,
    _read_csv_rows_with_headers,
    _row_value,
)
from ..productivity_kpi_rules import build_person_productivity_report_from_files, normalize_process
from ..productivity_sync import (
    LOCAL_TZ,
    ProductivitySyncError,
    ensure_productivity_snapshot,
    productivity_backfill_status,
    productivity_prebuild_status,
    productivity_snapshot_files,
    productivity_snapshot_status,
    sync_productivity_snapshot,
)
from ..settings_service import (
    PRODUCTIVITY_FINANCE_COLLAR_TYPES,
    PRODUCTIVITY_FINANCE_DEFAULT_VAS_RATE_TYPE,
    PRODUCTIVITY_FINANCE_VAS_RATE_TYPES,
    clean_productivity_finance_company_code,
    get_productivity_finance_settings,
    get_role_view_access,
    normalize_productivity_finance_collar_type,
    productivity_finance_default_invoice_rows,
    productivity_finance_vas_rates_from_invoice_rows,
)
from ..user_access import can_access_view
from ..workflow_data import productivity_api_source_map, sources_available


logger = logging.getLogger(__name__)


def _round_money(value: float) -> float:
    return round(float(value or 0.0), 2)


def _productivity_business_code(db: Session, user: User) -> str:
    try:
        business_id = user_business_id(db, user)
        business = db.get(Business, business_id) if business_id is not None else None
        return normalize_business_code(getattr(business, "code", None)) or DEFAULT_BUSINESS_CODE
    except Exception:
        return DEFAULT_BUSINESS_CODE


def _productivity_business_id(db: Session, user: User) -> int | None:
    try:
        return user_business_id(db, user)
    except Exception:
        return getattr(user, "business_id", None)


def _can_view_productivity_finance(db: Session, user: User) -> bool:
    if getattr(user, "is_super_user", False):
        return True
    if not hasattr(user, "role"):
        return False
    try:
        return can_access_view(user, get_role_view_access(db), "productivityFinance", "view")
    except Exception:
        return False


def _productivity_finance_business_company_codes(business: Business | None) -> list[str]:
    codes = []
    for raw_code in (getattr(business, "company_codes", None) or []):
        code = clean_productivity_finance_company_code(raw_code)
        if code and code not in codes:
            codes.append(code)
    return codes


def _productivity_finance_row_label(row: dict) -> str:
    return " | ".join(
        part
        for part in (
            str(row.get("service") or "").strip(),
            str(row.get("description") or "").strip(),
            str(row.get("unit") or "").strip(),
        )
        if part
    ) or str(row.get("id") or "Intaktsrad")


def _productivity_finance_process_revenue_rows(settings_payload: dict, company_codes: list[str]) -> list[dict]:
    allowed_company_codes = set(company_codes)
    rows_by_company = settings_payload.get("invoice_rows_by_company") or {}
    revenue_rows: list[dict] = []
    for company, rows in rows_by_company.items():
        company_code = clean_productivity_finance_company_code(company)
        if company_code not in allowed_company_codes:
            continue
        for row in rows or []:
            if row.get("collar_type") or row.get("vas_rate_type"):
                continue
            process_key = normalize_process(row.get("linked_process_key"))
            if not process_key:
                continue
            price = float(row.get("price") or 0.0)
            quantity = float(row.get("quantity") or 0.0)
            revenue = _round_money(price * quantity)
            if abs(revenue) <= 0.001:
                continue
            revenue_rows.append(
                {
                    "company": company_code,
                    "row_id": str(row.get("id") or ""),
                    "label": _productivity_finance_row_label(row),
                    "process_key": process_key,
                    "process_label": str(row.get("linked_process_label") or process_key),
                    "quantity": quantity,
                    "price": price,
                    "revenue": revenue,
                    "currency": "SEK",
                }
            )
    return revenue_rows


def _productivity_finance_company_for_activity(
    activity: Activity | None,
    business: Business | None,
    company_codes: set[str] | None = None,
) -> str:
    allowed_codes = company_codes if company_codes is not None else set(_productivity_finance_business_company_codes(business))
    if not allowed_codes:
        return ""
    area = getattr(activity, "area", None) if activity is not None else None
    for candidate in (
        getattr(area, "code", None),
        str(getattr(activity, "code", "") or "").split("_", 1)[0],
        str(getattr(activity, "label", "") or "").split(" ", 1)[0],
    ):
        code = clean_productivity_finance_company_code(candidate)
        if code in allowed_codes:
            return code
    return ""


def _productivity_finance_vas_rate_amounts(value: object) -> dict[str, float]:
    amounts = {rate_type: 0.0 for rate_type in PRODUCTIVITY_FINANCE_VAS_RATE_TYPES}
    if isinstance(value, dict):
        for rate_type in PRODUCTIVITY_FINANCE_VAS_RATE_TYPES:
            amounts[rate_type] = float(value.get(rate_type, 0.0) or 0.0)
        return amounts
    amounts[PRODUCTIVITY_FINANCE_DEFAULT_VAS_RATE_TYPE] = float(value or 0.0)
    return amounts


def _productivity_finance_collar_rates(value: object) -> dict[str, dict[str, float]]:
    if isinstance(value, dict):
        blue_value = value.get("blue_collar", value.get("blueCollar", value.get("blue")))
        white_value = value.get("white_collar", value.get("whiteCollar", value.get("white")))
        if blue_value is not None or white_value is not None:
            return {
                "blue_collar": _productivity_finance_vas_rate_amounts(blue_value),
                "white_collar": _productivity_finance_vas_rate_amounts(white_value),
            }
        rate_amounts = _productivity_finance_vas_rate_amounts(value)
        return {collar_type: dict(rate_amounts) for collar_type in PRODUCTIVITY_FINANCE_COLLAR_TYPES}
    rate_amounts = _productivity_finance_vas_rate_amounts(value)
    return {collar_type: dict(rate_amounts) for collar_type in PRODUCTIVITY_FINANCE_COLLAR_TYPES}


def _productivity_finance_person_collars(db: Session, business_id: int | None) -> dict[int, str]:
    query = db.query(Person.id, Person.collar_type)
    if business_id is not None:
        query = query.filter(Person.business_id == business_id)
    collars: dict[int, str] = {}
    for person_id, collar_type in query.all():
        try:
            key = int(person_id)
        except (TypeError, ValueError):
            continue
        collars[key] = normalize_productivity_finance_collar_type(collar_type)
    return collars


def _productivity_finance_context(db: Session, user: User, business_id: int | None) -> dict:
    if not _can_view_productivity_finance(db, user):
        return {"visible": False}
    settings_payload = get_productivity_finance_settings(db, business_id=business_id)
    business = db.get(Business, business_id) if business_id is not None else None
    company_codes = _productivity_finance_business_company_codes(business)
    allowed_company_codes = set(company_codes)
    invoice_rows_by_company = settings_payload.get("invoice_rows_by_company") or {}
    rates = {
        company: _productivity_finance_collar_rates(amount)
        for company, amount in (settings_payload.get("vas_hourly_revenue_by_company") or {}).items()
        if company in allowed_company_codes
    }
    for company in company_codes:
        if company in rates:
            continue
        rows = invoice_rows_by_company.get(company) or productivity_finance_default_invoice_rows(company)
        rates[company] = _productivity_finance_collar_rates(productivity_finance_vas_rates_from_invoice_rows(rows))
    query = db.query(Activity).filter(Activity.is_active.is_(True))
    if business_id is not None:
        query = query.filter(Activity.business_id == business_id)
    activities = query.all()
    activity_meta = {
        int(activity.id): {
            "is_vas": str(activity.work_type or "").strip().lower() == "vas",
            "company": _productivity_finance_company_for_activity(activity, business, allowed_company_codes),
        }
        for activity in activities
        if getattr(activity, "id", None) is not None
    }
    return {
        "visible": True,
        "currency": "SEK",
        "hourly_cost": float(settings_payload.get("hourly_cost") or 0.0),
        "vas_hourly_revenue_by_company": rates,
        "process_revenue_rows": _productivity_finance_process_revenue_rows(settings_payload, company_codes),
        "company_codes": company_codes,
        "activity_meta": activity_meta,
        "person_collar_by_id": _productivity_finance_person_collars(db, business_id),
    }


def _productivity_cell_work_minutes(cell: dict) -> int:
    if cell.get("kind") in {"kpi", "support"}:
        return int(cell.get("minutes") or 0)
    if float(cell.get("expected_points") or 0) > 0:
        return int(cell.get("minutes") or 0)
    return 0


def _empty_productivity_finance_summary(*, visible: bool = True, currency: str = "SEK") -> dict:
    return {
        "visible": visible,
        "currency": currency,
        "revenue": 0.0,
        "cost": 0.0,
        "result": 0.0,
        "work_minutes": 0,
        "vas_minutes": 0,
    }


def _add_productivity_finance_summary(target: dict, source: dict) -> None:
    target["revenue"] = _round_money(float(target.get("revenue") or 0) + float(source.get("revenue") or 0))
    target["cost"] = _round_money(float(target.get("cost") or 0) + float(source.get("cost") or 0))
    target["result"] = _round_money(float(target.get("result") or 0) + float(source.get("result") or 0))
    target["work_minutes"] = int(target.get("work_minutes") or 0) + int(source.get("work_minutes") or 0)
    target["vas_minutes"] = int(target.get("vas_minutes") or 0) + int(source.get("vas_minutes") or 0)


def _add_productivity_finance_process_revenues(target: dict, rows: list[dict] | None) -> None:
    cleaned_rows = [row for row in (rows or []) if abs(float(row.get("revenue") or 0.0)) > 0.001]
    if not cleaned_rows:
        return
    target["process_revenues"] = cleaned_rows
    for row in cleaned_rows:
        revenue = float(row.get("revenue") or 0.0)
        target["revenue"] = _round_money(float(target.get("revenue") or 0.0) + revenue)
        target["result"] = _round_money(float(target.get("result") or 0.0) + revenue)


def _productivity_finance_rate_for_company(context: dict, company: str, collar_type: str) -> float:
    rates = context.get("vas_hourly_revenue_by_company") or {}
    company_rates = rates.get(company, 0.0)
    if isinstance(company_rates, dict):
        collar_rates = company_rates.get(collar_type, company_rates.get("blue_collar", 0.0))
        if isinstance(collar_rates, dict):
            return float(collar_rates.get(PRODUCTIVITY_FINANCE_DEFAULT_VAS_RATE_TYPE, 0.0) or 0.0)
        return float(collar_rates or 0.0)
    return float(company_rates or 0.0)


def _finance_for_productivity_cell(cell: dict, context: dict, collar_type: str) -> dict | None:
    work_minutes = _productivity_cell_work_minutes(cell)
    if work_minutes <= 0:
        return None
    activity_id = cell.get("activity_id")
    try:
        activity_key = int(activity_id) if activity_id is not None else None
    except (TypeError, ValueError):
        activity_key = None
    meta = (context.get("activity_meta") or {}).get(activity_key, {}) if activity_key is not None else {}
    is_vas = bool(meta.get("is_vas"))
    allowed_company_codes = set(context.get("company_codes") or [])
    company = clean_productivity_finance_company_code(meta.get("company") if meta else cell.get("activity_area_code"))
    if company not in allowed_company_codes:
        company = ""
    hourly_cost = float(context.get("hourly_cost") or 0.0)
    hours = work_minutes / 60.0
    cost = hours * hourly_cost
    rate = _productivity_finance_rate_for_company(context, company, collar_type) if is_vas and company else 0.0
    revenue = hours * rate
    return {
        "visible": True,
        "currency": context.get("currency") or "SEK",
        "revenue": _round_money(revenue),
        "cost": _round_money(cost),
        "result": _round_money(revenue - cost),
        "work_minutes": work_minutes,
        "vas_minutes": work_minutes if is_vas else 0,
        "is_vas": is_vas,
        "company": (company or None) if is_vas else None,
        "collar_type": collar_type,
        "rate_type": PRODUCTIVITY_FINANCE_DEFAULT_VAS_RATE_TYPE if is_vas else None,
    }


def _productivity_finance_person_collar(person: dict, context: dict) -> str:
    raw_collar_type = person.get("collar_type")
    if not raw_collar_type:
        try:
            person_id = int(person.get("person_id"))
        except (TypeError, ValueError):
            person_id = None
        raw_collar_type = (context.get("person_collar_by_id") or {}).get(person_id)
    return normalize_productivity_finance_collar_type(raw_collar_type)


def _attach_productivity_finance(report: dict, context: dict, *, include_process_revenues: bool = True) -> dict:
    if not context.get("visible"):
        report["finance"] = {"visible": False}
        return report
    report_finance = _empty_productivity_finance_summary(currency=str(context.get("currency") or "SEK"))
    for person in report.get("people") or []:
        collar_type = _productivity_finance_person_collar(person, context)
        person_finance = _empty_productivity_finance_summary(currency=report_finance["currency"])
        for cell in person.get("time_cells") or []:
            cell_finance = _finance_for_productivity_cell(cell, context, collar_type)
            if cell_finance is None:
                continue
            cell["finance"] = cell_finance
            _add_productivity_finance_summary(person_finance, cell_finance)
        if person_finance["work_minutes"] > 0:
            person["finance"] = person_finance
            _add_productivity_finance_summary(report_finance, person_finance)
    if include_process_revenues:
        _add_productivity_finance_process_revenues(report_finance, context.get("process_revenue_rows") or [])
    report["finance"] = report_finance
    return report


def _productivity_business_summary_company_label(company: str) -> str:
    return company or "Okänt bolag"


def _empty_productivity_business_company_summary(
    company: str,
    *,
    currency: str = "SEK",
    finance_visible: bool = True,
) -> dict:
    return {
        "company": company,
        "company_label": _productivity_business_summary_company_label(company),
        "finance_visible": finance_visible,
        "currency": currency,
        "revenue": 0.0,
        "vas_revenue": 0.0,
        "process_revenue": 0.0,
        "cost": 0.0,
        "result": 0.0,
        "work_minutes": 0,
        "vas_minutes": 0,
        "zero_pick_rows": 0,
    }


def _ensure_productivity_business_company_summary(
    summaries: dict[str, dict],
    company: str,
    *,
    currency: str,
    finance_visible: bool,
) -> dict:
    company_code = clean_productivity_finance_company_code(company)
    if company_code not in summaries:
        summaries[company_code] = _empty_productivity_business_company_summary(
            company_code,
            currency=currency,
            finance_visible=finance_visible,
        )
    return summaries[company_code]


def _productivity_activity_meta_for_cell(cell: dict, context: dict) -> dict:
    activity_id = cell.get("activity_id")
    try:
        activity_key = int(activity_id) if activity_id is not None else None
    except (TypeError, ValueError):
        activity_key = None
    if activity_key is None:
        return {}
    return (context.get("activity_meta") or {}).get(activity_key, {}) or {}


def _productivity_business_summary_company_for_cell(cell: dict, context: dict) -> str:
    allowed_company_codes = set(context.get("company_codes") or [])
    finance = cell.get("finance") or {}
    meta = _productivity_activity_meta_for_cell(cell, context)
    for candidate in (finance.get("company"), meta.get("company")):
        company = clean_productivity_finance_company_code(candidate)
        if company and (not allowed_company_codes or company in allowed_company_codes):
            return company
    area_company = clean_productivity_finance_company_code(cell.get("activity_area_code"))
    if area_company and area_company in allowed_company_codes:
        return area_company
    return ""


def _add_productivity_business_company_cell_finance(
    summaries: dict[str, dict],
    cell: dict,
    context: dict,
    *,
    currency: str,
    finance_visible: bool,
) -> None:
    finance = cell.get("finance") or {}
    if not finance.get("visible"):
        return
    summary = _ensure_productivity_business_company_summary(
        summaries,
        _productivity_business_summary_company_for_cell(cell, context),
        currency=currency,
        finance_visible=finance_visible,
    )
    revenue = float(finance.get("revenue") or 0.0)
    cost = float(finance.get("cost") or 0.0)
    summary["revenue"] = _round_money(float(summary.get("revenue") or 0.0) + revenue)
    summary["cost"] = _round_money(float(summary.get("cost") or 0.0) + cost)
    summary["work_minutes"] = int(summary.get("work_minutes") or 0) + int(finance.get("work_minutes") or 0)
    summary["vas_minutes"] = int(summary.get("vas_minutes") or 0) + int(finance.get("vas_minutes") or 0)
    if finance.get("is_vas"):
        summary["vas_revenue"] = _round_money(float(summary.get("vas_revenue") or 0.0) + revenue)


def _add_productivity_business_company_report_finance(
    summaries: dict[str, dict],
    report: dict,
    context: dict,
    *,
    currency: str,
    finance_visible: bool,
) -> None:
    for person in report.get("people") or []:
        for cell in person.get("time_cells") or []:
            _add_productivity_business_company_cell_finance(
                summaries,
                cell,
                context,
                currency=currency,
                finance_visible=finance_visible,
            )


def _add_productivity_business_company_process_revenues(
    summaries: dict[str, dict],
    rows: list[dict] | None,
    *,
    currency: str,
    finance_visible: bool,
) -> None:
    for row in rows or []:
        revenue = float(row.get("revenue") or 0.0)
        if abs(revenue) <= 0.001:
            continue
        summary = _ensure_productivity_business_company_summary(
            summaries,
            str(row.get("company") or ""),
            currency=currency,
            finance_visible=finance_visible,
        )
        summary["revenue"] = _round_money(float(summary.get("revenue") or 0.0) + revenue)
        summary["process_revenue"] = _round_money(float(summary.get("process_revenue") or 0.0) + revenue)


def _productivity_zero_pick_rows_by_company(files: dict[str, Path]) -> dict[str, int]:
    path = files.get("pick")
    if path is None:
        return {}
    try:
        _headers, rows = _read_csv_rows_with_headers(Path(path), compressed=str(path).lower().endswith(".gz"))
    except Exception:
        logger.warning("Kunde inte läsa plocklogg för nollade rader i produktivitetssummering.", exc_info=True)
        return {}

    counts: dict[str, int] = {}
    for row in rows:
        picked_raw = _row_value(row, "qty_suf", "Plockat", "plockat", "Picked", "picked")
        if not str(picked_raw or "").strip():
            continue
        if abs(_number(picked_raw)) > 0.001:
            continue
        company = clean_productivity_finance_company_code(_row_value(row, "company", "Company", "Bolag", "bolag"))
        counts[company] = counts.get(company, 0) + 1
    return counts


def _add_productivity_zero_pick_rows(
    summaries: dict[str, dict],
    counts: dict[str, int],
    *,
    currency: str,
    finance_visible: bool,
) -> None:
    for company, count in counts.items():
        if int(count or 0) <= 0:
            continue
        summary = _ensure_productivity_business_company_summary(
            summaries,
            company,
            currency=currency,
            finance_visible=finance_visible,
        )
        summary["zero_pick_rows"] = int(summary.get("zero_pick_rows") or 0) + int(count or 0)


def _productivity_business_company_summary_has_values(summary: dict) -> bool:
    return (
        abs(float(summary.get("revenue") or 0.0)) > 0.001
        or abs(float(summary.get("cost") or 0.0)) > 0.001
        or int(summary.get("work_minutes") or 0) > 0
        or int(summary.get("zero_pick_rows") or 0) > 0
    )


def _finalize_productivity_business_company_summaries(
    summaries: dict[str, dict],
    *,
    company_codes: list[str],
    currency: str,
    finance_visible: bool,
) -> tuple[list[dict], dict]:
    company_order = {company: index for index, company in enumerate(company_codes or [])}
    rows = [
        summary
        for summary in summaries.values()
        if _productivity_business_company_summary_has_values(summary)
    ]
    for row in rows:
        row["revenue"] = _round_money(row.get("revenue") or 0.0)
        row["vas_revenue"] = _round_money(row.get("vas_revenue") or 0.0)
        row["process_revenue"] = _round_money(row.get("process_revenue") or 0.0)
        row["cost"] = _round_money(row.get("cost") or 0.0)
        row["result"] = _round_money(float(row.get("revenue") or 0.0) - float(row.get("cost") or 0.0))

    rows.sort(
        key=lambda item: (
            company_order.get(str(item.get("company") or ""), len(company_order)),
            str(item.get("company_label") or ""),
        )
    )
    totals = _empty_productivity_business_company_summary("", currency=currency, finance_visible=finance_visible)
    totals["company_label"] = "Totalt"
    for row in rows:
        totals["revenue"] = _round_money(float(totals.get("revenue") or 0.0) + float(row.get("revenue") or 0.0))
        totals["vas_revenue"] = _round_money(float(totals.get("vas_revenue") or 0.0) + float(row.get("vas_revenue") or 0.0))
        totals["process_revenue"] = _round_money(float(totals.get("process_revenue") or 0.0) + float(row.get("process_revenue") or 0.0))
        totals["cost"] = _round_money(float(totals.get("cost") or 0.0) + float(row.get("cost") or 0.0))
        totals["work_minutes"] = int(totals.get("work_minutes") or 0) + int(row.get("work_minutes") or 0)
        totals["vas_minutes"] = int(totals.get("vas_minutes") or 0) + int(row.get("vas_minutes") or 0)
        totals["zero_pick_rows"] = int(totals.get("zero_pick_rows") or 0) + int(row.get("zero_pick_rows") or 0)
    totals["result"] = _round_money(float(totals.get("revenue") or 0.0) - float(totals.get("cost") or 0.0))
    return rows, totals


def _productivity_business_payload(db: Session, user: User, business_id: int | None) -> dict:
    business = None
    try:
        business = db.get(Business, business_id) if business_id is not None else None
    except Exception:
        business = None
    return {
        "id": business_id,
        "code": _productivity_business_code(db, user),
        "name": getattr(business, "name", None) or getattr(user, "business_name", None),
    }

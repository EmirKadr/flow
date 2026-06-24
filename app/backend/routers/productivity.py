from calendar import monthrange
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import logging
from pathlib import Path
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from .. import audit
from ..business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code, scoped_get, user_business_id
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


router = APIRouter(prefix="/api/productivity", tags=["productivity"])
logger = logging.getLogger(__name__)
_PERSON_REPORT_CACHE_TTL_SECONDS = 2 * 60
_PERSON_REPORT_CACHE_MAX_ITEMS = 256
_PERSON_REPORT_CACHE_LOCK = threading.Lock()
_PERSON_REPORT_CACHE: dict[tuple, tuple[float, dict]] = {}


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


def _audit_productivity_report_sources(
    db: Session,
    user: User,
    *,
    status_text: str,
    source_status: list[dict] | None = None,
    error_type: str | None = None,
    status_code: int | None = None,
) -> None:
    payload: dict[str, object] = {
        "status": status_text,
        "source_status": source_status or [],
    }
    if error_type:
        payload["error_type"] = error_type
    if status_code is not None:
        payload["status_code"] = status_code
    audit.log_and_commit(
        db,
        entity_type="productivity_report",
        entity_id=0,
        action="run",
        old_value=None,
        new_value=payload,
        user_id=getattr(user, "id", None),
        logger=logger,
        context="productivity report source audit",
    )


def _daily_report_cache_key(
    files: dict[str, Path],
    report_date: date | None,
    business_id: int | None,
    sync: dict | None,
) -> tuple:
    parts: list[tuple] = [
        ("date", report_date.isoformat() if isinstance(report_date, date) else ""),
        ("business_id", business_id if business_id is not None else ""),
        ("sync", str((sync or {}).get("last_sync_at") or "")),
        ("builder", id(build_person_productivity_report_from_files)),
    ]
    for key, path in sorted(files.items()):
        resolved = Path(path)
        try:
            stat = resolved.stat()
            parts.append((key, str(resolved.resolve()), stat.st_mtime_ns, stat.st_size))
        except OSError:
            parts.append((key, str(resolved), None, None))
    return tuple(parts)


def _build_cached_person_productivity_report(
    db: Session,
    files: dict[str, Path],
    *,
    report_date: date | None,
    business_id: int | None,
    sync: dict | None,
) -> dict:
    key = _daily_report_cache_key(files, report_date, business_id, sync)
    now = time.monotonic()
    with _PERSON_REPORT_CACHE_LOCK:
        cached = _PERSON_REPORT_CACHE.get(key)
        if cached and cached[0] > now:
            return deepcopy(cached[1])
        if cached:
            _PERSON_REPORT_CACHE.pop(key, None)

    report = build_person_productivity_report_from_files(
        db,
        files,
        report_date=report_date,
        business_id=business_id,
        sync=sync,
    )
    with _PERSON_REPORT_CACHE_LOCK:
        if len(_PERSON_REPORT_CACHE) >= _PERSON_REPORT_CACHE_MAX_ITEMS:
            _PERSON_REPORT_CACHE.pop(next(iter(_PERSON_REPORT_CACHE)), None)
        _PERSON_REPORT_CACHE[key] = (
            now + _PERSON_REPORT_CACHE_TTL_SECONDS,
            deepcopy(report),
        )
    return report


@router.post("/sync")
def sync_productivity(
    date_filter: date | None = Query(default=None, alias="date"),
    user: User = Depends(require_view_access("productivity", "edit")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return sync_productivity_snapshot(
            date_filter,
            business_code=_productivity_business_code(db, user),
            db=db,
            user_id=getattr(user, "id", None),
        )
    except ProductivitySyncError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


def _period_bounds(
    period: str,
    *,
    anchor_date: date | None,
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date, str]:
    today = date.today()
    anchor = anchor_date or end_date or start_date or today
    normalized = str(period or "week").strip().lower()
    if normalized == "day":
        return anchor, anchor, "Dag"
    if normalized == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6), "Vecka"
    if normalized == "month":
        start = anchor.replace(day=1)
        return start, anchor.replace(day=monthrange(anchor.year, anchor.month)[1]), "Månad"
    if normalized == "year":
        return anchor.replace(month=1, day=1), anchor.replace(month=12, day=31), "År"
    if normalized == "custom":
        start = start_date or anchor
        end = end_date or start
        return start, end, "Datum"
    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Okänd period")


def _date_span(start_date: date, end_date: date) -> list[date]:
    if end_date < start_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Slutdatum måste vara samma dag eller efter startdatum")
    days = (end_date - start_date).days
    if days > 370:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Välj högst 371 dagar åt gången")
    return [start_date + timedelta(days=offset) for offset in range(days + 1)]


def _activity_bucket(activity: dict[str, float | int | str], cell: dict) -> None:
    points = float(cell.get("points") or 0)
    expected = float(cell.get("expected_points") or 0)
    minutes = int(cell.get("minutes") or 0)
    activity["kpi_points"] = float(activity["kpi_points"]) + points
    activity["planned_kpi_points"] = float(activity["planned_kpi_points"]) + expected
    activity["kpi_minutes"] = int(activity["kpi_minutes"]) + minutes
    activity["periods"] = int(activity["periods"]) + 1
    activity["event_count"] = int(activity["event_count"]) + int(cell.get("event_count") or 0)
    activity["diff_count"] = int(activity["diff_count"]) + int(cell.get("diff_count") or 0)


def _finalize_activity_stats(activity: dict[str, float | int | str]) -> dict[str, float | int | str | None]:
    points = float(activity["kpi_points"])
    planned = float(activity["planned_kpi_points"])
    minutes = int(activity["kpi_minutes"])
    hours = minutes / 60.0 if minutes else 0.0
    return {
        "activity": str(activity["activity"]),
        "productivity_pct": points / planned if planned > 0 else None,
        "points_per_hour": points / hours if hours > 0 else None,
        "kpi_points": round(points, 2),
        "planned_kpi_points": round(planned, 2),
        "kpi_minutes": minutes,
        "kpi_hours": round(hours, 2),
        "periods": int(activity["periods"]),
        "event_count": int(activity["event_count"]),
        "diff_count": int(activity["diff_count"]),
    }


def _aggregate_person_activity_stats(reports: list[dict], person_id: int) -> dict:
    activities: dict[str, dict[str, float | int | str]] = {}
    used_dates: set[str] = set()
    days_with_activity: set[str] = set()
    total_points = 0.0
    total_planned = 0.0
    total_minutes = 0
    total_support_minutes = 0
    total_absence_minutes = 0
    diff_count = 0
    event_count = 0

    for report in reports:
        report_date = str(report.get("date") or "")
        person = next((item for item in report.get("people") or [] if int(item.get("person_id") or 0) == int(person_id)), None)
        if person is None:
            continue
        used_dates.add(report_date)
        total_support_minutes += int(person.get("support_minutes") or 0)
        total_absence_minutes += int(person.get("absence_minutes") or 0)
        for cell in person.get("time_cells") or []:
            if cell.get("kind") != "kpi":
                continue
            expected = float(cell.get("expected_points") or 0)
            if expected <= 0:
                continue
            label = str(cell.get("activity_label") or cell.get("display") or "Okänd aktivitet")
            bucket = activities.setdefault(
                label,
                {
                    "activity": label,
                    "kpi_points": 0.0,
                    "planned_kpi_points": 0.0,
                    "kpi_minutes": 0,
                    "periods": 0,
                    "event_count": 0,
                    "diff_count": 0,
                },
            )
            _activity_bucket(bucket, cell)
            total_points += float(cell.get("points") or 0)
            total_planned += expected
            total_minutes += int(cell.get("minutes") or 0)
            diff_count += int(cell.get("diff_count") or 0)
            event_count += int(cell.get("event_count") or 0)
            if report_date:
                days_with_activity.add(report_date)

    activity_rows = [_finalize_activity_stats(activity) for activity in activities.values()]
    activity_rows.sort(key=lambda item: (-float(item["kpi_minutes"] or 0), str(item["activity"]).upper()))
    hours = total_minutes / 60.0 if total_minutes else 0.0
    return {
        "activities": activity_rows,
        "summary": {
            "days_with_data": len(used_dates),
            "days_with_activity": len(days_with_activity),
            "kpi_points": round(total_points, 2),
            "planned_kpi_points": round(total_planned, 2),
            "productivity_pct": total_points / total_planned if total_planned > 0 else None,
            "points_per_hour": total_points / hours if hours > 0 else None,
            "kpi_minutes": total_minutes,
            "kpi_hours": round(hours, 2),
            "support_minutes": total_support_minutes,
            "absence_minutes": total_absence_minutes,
            "event_count": event_count,
            "diff_count": diff_count,
        },
    }


def _person_productivity_files_for_date(request: Request, db: Session, user: User, report_date: date) -> tuple[dict[str, Path], dict]:
    business_code = _productivity_business_code(db, user)
    if not sources_available(tuple(productivity_api_source_map().values())):
        raise ProductivitySyncError("Produktivitetens globala API-källor är inte konfigurerade.")
    snapshot_status = productivity_snapshot_status(report_date)
    if not snapshot_status.get("ready"):
        raise ProductivitySyncError("Produktivitetens API-snapshot saknas eller är inte komplett.")
    return productivity_snapshot_files(report_date), snapshot_status


def _build_productivity_report_for_date(
    request: Request,
    db: Session,
    user: User,
    report_date: date | None,
    *,
    ensure_snapshot: bool = True,
    wait_seconds: float = 10,
) -> tuple[dict, list[dict]]:
    business_code = _productivity_business_code(db, user)
    business_id = _productivity_business_id(db, user)
    source_status: list[dict] = []
    if not sources_available(tuple(productivity_api_source_map().values())):
        raise ProductivitySyncError("Produktivitetens globala API-källor är inte konfigurerade.")
    if ensure_snapshot:
        sync_status = ensure_productivity_snapshot(
            report_date,
            business_code=business_code,
            db=db,
            user_id=getattr(user, "id", None),
            wait_seconds=wait_seconds,
        )
    else:
        sync_status = productivity_snapshot_status(report_date)
        if not sync_status.get("ready"):
            raise ProductivitySyncError("Produktivitetens API-snapshot saknas eller är inte komplett.")
    snapshot_date = report_date or date.fromisoformat(str(sync_status.get("date") or date.today().isoformat()))
    files = productivity_snapshot_files(snapshot_date)
    source_status = list(sync_status.get("sources") or [])
    report = _build_cached_person_productivity_report(
        db,
        files,
        report_date=snapshot_date,
        business_id=business_id,
        sync=productivity_snapshot_status(snapshot_date),
    )
    report["source_status"] = source_status
    return report, source_status


@router.get("/persons/{person_id}")
def get_person_productivity(
    person_id: int,
    request: Request,
    period: str = Query(default="week"),
    date_filter: date | None = Query(default=None, alias="date"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    user: User = Depends(require_view_access("productivity", "view")),
    db: Session = Depends(get_db),
) -> dict:
    person = scoped_get(db, Person, person_id, user, detail="Person hittades inte")
    period_start, period_end, period_label = _period_bounds(
        period,
        anchor_date=date_filter,
        start_date=start_date,
        end_date=end_date,
    )
    days = _date_span(period_start, period_end)
    reports: list[dict] = []
    missing_dates: list[str] = []
    errors: list[dict] = []
    source_status: list[dict] = []

    for day in days:
        try:
            files, sync_status = _person_productivity_files_for_date(request, db, user, day)
            report = _build_cached_person_productivity_report(
                db,
                files,
                report_date=day,
                business_id=person.business_id,
                sync=sync_status,
            )
            reports.append(report)
            source_status.append({"date": day.isoformat(), "status": "ok", "source": sync_status.get("source")})
        except (ProductivitySourceError, ProductivitySyncError) as exc:
            missing_dates.append(day.isoformat())
            errors.append({"date": day.isoformat(), "error_type": type(exc).__name__, "message": str(exc)})

    aggregate = _aggregate_person_activity_stats(reports, person.id)
    return {
        "person": {
            "id": person.id,
            "name": person.name,
            "noman": person.noman,
            "business_id": person.business_id,
        },
        "period": {
            "type": str(period or "week").strip().lower(),
            "label": period_label,
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
            "requested_days": len(days),
        },
        "dates": [str(report.get("date") or "") for report in reports],
        "missing_dates": missing_dates,
        "source_status": source_status,
        "errors": errors[:20],
        "backfill": productivity_backfill_status(),
        **aggregate,
    }


def _overview_period_bounds(
    period: str,
    *,
    anchor_date: date | None,
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date, str]:
    period_start, period_end, period_label = _period_bounds(
        period,
        anchor_date=anchor_date,
        start_date=start_date,
        end_date=end_date,
    )
    today = datetime.now(LOCAL_TZ).date()
    if period_end > today:
        period_end = today
    if period_start > period_end:
        period_start = period_end
    return period_start, period_end, period_label


def _overview_period_summary(reports: list[dict], requested_days: int) -> dict:
    kpi_points = 0.0
    planned_points = 0.0
    kpi_minutes = 0
    diff_count = 0
    unmatched_event_count = 0
    people: set[int | str] = set()
    for report in reports:
        summary = report.get("summary") or {}
        kpi_points += float(summary.get("kpi_points") or 0)
        planned_points += float(summary.get("planned_kpi_points") or 0)
        kpi_minutes += int(summary.get("kpi_minutes") or 0)
        diff_count += int(summary.get("diff_count") or 0)
        unmatched_event_count += int(summary.get("unmatched_event_count") or 0)
        for person in report.get("people") or []:
            people.add(person.get("person_id") or person.get("name") or "")
    hours = kpi_minutes / 60.0 if kpi_minutes else 0.0
    return {
        "requested_days": requested_days,
        "days_with_data": len(reports),
        "people": len([item for item in people if item]),
        "kpi_points": round(kpi_points, 2),
        "planned_kpi_points": round(planned_points, 2),
        "average_productivity_pct": kpi_points / planned_points if planned_points > 0 else None,
        "points_per_hour": kpi_points / hours if hours > 0 else None,
        "kpi_minutes": kpi_minutes,
        "diff_count": diff_count,
        "unmatched_event_count": unmatched_event_count,
    }


@router.get("/overview/business-summary")
def get_productivity_overview_business_summary(
    request: Request,
    period: str = Query(default="day"),
    date_filter: date | None = Query(default=None, alias="date"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    user: User = Depends(require_view_access("productivity", "view")),
    db: Session = Depends(get_db),
) -> dict:
    normalized_period = str(period or "day").strip().lower()
    period_start, period_end, period_label = _overview_period_bounds(
        normalized_period,
        anchor_date=date_filter,
        start_date=start_date,
        end_date=end_date,
    )
    days = _date_span(period_start, period_end)
    business_id = _productivity_business_id(db, user)
    finance_context = _productivity_finance_context(db, user, business_id)
    finance_visible = bool(finance_context.get("visible"))
    currency = str(finance_context.get("currency") or "SEK")
    summaries: dict[str, dict] = {}
    errors: list[dict] = []
    reports: list[dict] = []
    source_status: list[dict] = []

    for day in days:
        try:
            report, day_source_status = _build_productivity_report_for_date(
                request,
                db,
                user,
                day,
                ensure_snapshot=False,
                wait_seconds=0,
            )
            if finance_visible:
                _attach_productivity_finance(report, finance_context, include_process_revenues=False)
                _add_productivity_business_company_report_finance(
                    summaries,
                    report,
                    finance_context,
                    currency=currency,
                    finance_visible=finance_visible,
                )
            _add_productivity_zero_pick_rows(
                summaries,
                _productivity_zero_pick_rows_by_company(productivity_snapshot_files(day)),
                currency=currency,
                finance_visible=finance_visible,
            )
            reports.append(report)
            source_status.append({
                "date": day.isoformat(),
                "status": "ok",
                "source": (report.get("sync") or {}).get("source"),
                "sources": day_source_status,
            })
        except (ProductivitySourceError, ProductivitySyncError) as exc:
            errors.append({"date": day.isoformat(), "error_type": type(exc).__name__, "message": str(exc)})

    if not reports and errors:
        first_error = errors[0]
        status_code = (
            status.HTTP_502_BAD_GATEWAY
            if first_error.get("error_type") == "ProductivitySyncError"
            else status.HTTP_404_NOT_FOUND
        )
        raise HTTPException(
            status_code,
            detail=str(first_error.get("message") or "Produktivitetsperioden kunde inte hämtas."),
        )

    if finance_visible:
        _add_productivity_business_company_process_revenues(
            summaries,
            finance_context.get("process_revenue_rows") or [],
            currency=currency,
            finance_visible=finance_visible,
        )

    companies, totals = _finalize_productivity_business_company_summaries(
        summaries,
        company_codes=list(finance_context.get("company_codes") or []),
        currency=currency,
        finance_visible=finance_visible,
    )
    missing_dates = [
        day.isoformat()
        for day in days
        if not any(str(report.get("date") or "") == day.isoformat() for report in reports)
    ]
    return {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "business": _productivity_business_payload(db, user, business_id),
        "period": {
            "type": normalized_period,
            "label": period_label,
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
            "requested_days": len(days),
            "days_with_data": len(reports),
        },
        "finance_visible": finance_visible,
        "currency": currency,
        "companies": companies,
        "totals": totals,
        "source_status": source_status,
        "missing_dates": missing_dates,
        "errors": errors[:20],
    }


@router.get("/overview")
def get_productivity_overview(
    request: Request,
    period: str = Query(default="day"),
    date_filter: date | None = Query(default=None, alias="date"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    user: User = Depends(require_view_access("productivity", "view")),
    db: Session = Depends(get_db),
) -> dict:
    normalized_period = str(period or "day").strip().lower()
    period_start, period_end, period_label = _overview_period_bounds(
        normalized_period,
        anchor_date=date_filter,
        start_date=start_date,
        end_date=end_date,
    )
    days = _date_span(period_start, period_end)
    business_id = _productivity_business_id(db, user)
    finance_context = _productivity_finance_context(db, user, business_id)
    errors: list[dict] = []
    reports: list[dict] = []
    source_status: list[dict] = []
    for day in days:
        try:
            report, day_source_status = _build_productivity_report_for_date(
                request,
                db,
                user,
                day,
                ensure_snapshot=False,
                wait_seconds=0,
            )
            _attach_productivity_finance(report, finance_context, include_process_revenues=False)
            reports.append(report)
            source_status.append({
                "date": day.isoformat(),
                "status": "ok",
                "source": (report.get("sync") or {}).get("source"),
                "sources": day_source_status,
            })
        except (ProductivitySourceError, ProductivitySyncError) as exc:
            errors.append({"date": day.isoformat(), "error_type": type(exc).__name__, "message": str(exc)})

    if not reports and errors:
        first_error = errors[0]
        status_code = status.HTTP_502_BAD_GATEWAY if first_error.get("error_type") == "ProductivitySyncError" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code, detail=str(first_error.get("message") or "Produktivitetsperioden kunde inte hämtas."))

    available_dates = sorted({
        str(item)
        for report in reports
        for item in (report.get("available_dates") or [report.get("date")])
        if item
    })
    missing_dates = [day.isoformat() for day in days if not any(str(report.get("date") or "") == day.isoformat() for report in reports)]
    sync = productivity_snapshot_status(period_end) if days else productivity_snapshot_status(date_filter)
    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "date": (date_filter or period_end).isoformat(),
        "available_dates": available_dates or [day.isoformat() for day in days],
        "period": {
            "type": normalized_period,
            "label": period_label,
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
            "requested_days": len(days),
            "days_with_data": len(reports),
        },
        "reports": reports,
        "summary": _overview_period_summary(reports, len(days)),
        "source_status": source_status,
        "missing_dates": missing_dates,
        "errors": errors[:20],
        "sync": sync,
        "backfill": productivity_backfill_status(),
    }
    if finance_context.get("visible"):
        finance_summary = _empty_productivity_finance_summary(currency=str(finance_context.get("currency") or "SEK"))
        for report in reports:
            _add_productivity_finance_summary(finance_summary, report.get("finance") or {})
        _add_productivity_finance_process_revenues(finance_summary, finance_context.get("process_revenue_rows") or [])
        payload["finance"] = finance_summary
    else:
        payload["finance"] = {"visible": False}
    _audit_productivity_report_sources(db, user, status_text="ok", source_status=source_status)
    return payload


@router.get("")
def get_productivity(
    request: Request,
    date_filter: date | None = Query(default=None, alias="date"),
    user: User = Depends(require_view_access("productivity", "view")),
    db: Session = Depends(get_db),
) -> dict:
    source_status: list[dict] = []
    try:
        selected_date_filter = date_filter if isinstance(date_filter, date) else None
        business_code = _productivity_business_code(db, user)
        business_id = _productivity_business_id(db, user)
        finance_context = _productivity_finance_context(db, user, business_id)
        if not sources_available(tuple(productivity_api_source_map().values())):
            raise ProductivitySyncError("Produktivitetens globala API-källor är inte konfigurerade.")
        sync_status = ensure_productivity_snapshot(
            selected_date_filter,
            business_code=business_code,
            db=db,
            user_id=getattr(user, "id", None),
            wait_seconds=10,
        )
        snapshot_date = selected_date_filter or date.fromisoformat(str(sync_status.get("date") or date.today().isoformat()))
        files = productivity_snapshot_files(snapshot_date)
        source_status = list(sync_status.get("sources") or [])
        report = _build_cached_person_productivity_report(
            db,
            files,
            report_date=snapshot_date,
            business_id=business_id,
            sync=productivity_snapshot_status(snapshot_date),
        )
        _attach_productivity_finance(report, finance_context)
        report["source_status"] = source_status
        report["backfill"] = productivity_backfill_status()
        _audit_productivity_report_sources(db, user, status_text="ok", source_status=source_status)
        return report
    except ProductivitySyncError as exc:
        _audit_productivity_report_sources(
            db,
            user,
            status_text="error",
            source_status=source_status,
            error_type=type(exc).__name__,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ProductivitySourceError as exc:
        _audit_productivity_report_sources(
            db,
            user,
            status_text="error",
            source_status=source_status,
            error_type=type(exc).__name__,
            status_code=status.HTTP_404_NOT_FOUND,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        _audit_productivity_report_sources(
            db,
            user,
            status_text="error",
            source_status=source_status,
            error_type=type(exc).__name__,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte läsa produktivitetsunderlag: {exc}",
        ) from exc
    except Exception as exc:
        _audit_productivity_report_sources(
            db,
            user,
            status_text="error",
            source_status=source_status,
            error_type=type(exc).__name__,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte beräkna produktivitet: {exc}",
        ) from exc

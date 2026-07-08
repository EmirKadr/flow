"""Hjalpfunktioner for produktivitetsrouten: finans-kontext och -aggregering, business-summeringar, rapportbyggen, overview-korning och cachar.

Utflyttat ur routers/productivity.py for radtaket i arkitektur-kontraktet.
Routern importerar namnen har ifran, sa tester kan fortsatta patcha
productivity.<namn> pa routermodulen.
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
from ..person_productivity_cache import (
    productivity_cache_schedule_signature,
    productivity_snapshot_signature,
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
    read_overview_report_cache,
    sync_productivity_snapshot,
    write_overview_report_cache,
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

from . import productivity_finance_helpers


logger = logging.getLogger(__name__)

_PERSON_REPORT_CACHE_TTL_SECONDS = 2 * 60
_PERSON_REPORT_CACHE_MAX_ITEMS = 256
_PRODUCTIVITY_OVERVIEW_DAY_WORKERS = 4
_PRODUCTIVITY_OVERVIEW_DAY_SNAPSHOT_WAIT_SECONDS = 180
_PERSON_REPORT_CACHE_LOCK = threading.Lock()
_PERSON_REPORT_CACHE: dict[tuple, tuple[float, dict]] = {}


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
    business_code = productivity_finance_helpers._productivity_business_code(db, user)
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
    business_code = productivity_finance_helpers._productivity_business_code(db, user)
    business_id = productivity_finance_helpers._productivity_business_id(db, user)
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
    if not ensure_snapshot and report_date is not None:
        # I else-grenen ovan är sync_status redan productivity_snapshot_status(
        # report_date), och snapshot_date == report_date här — läs inte om samma
        # snapshot-JSON en gång till.
        current_sync = sync_status
    else:
        current_sync = productivity_snapshot_status(snapshot_date)
    source_status = list(sync_status.get("sources") or [])

    # Las den forbyggda fulldetaljerade dagrapporten fran disk nar snapshot- och
    # schemasignatur fortfarande stammer, sa ar-/manadsvyn slipper bygga om varje
    # dag fran CSV. Miss (saknad eller foraldrad) faller tillbaka pa CSV-bygget
    # och skriver om cachen (self-heal). Signaturberakningen ar defensiv sa en
    # fake-session/patchad miljo bara faller tillbaka pa CSV-bygget som forr.
    report = None
    snapshot_signature = ""
    schedule_signature = ""
    cache_ready = False
    try:
        snapshot_signature = productivity_snapshot_signature(current_sync)
        schedule_signature = productivity_cache_schedule_signature(db, snapshot_date, business_id=business_id)
        cache_ready = True
        report = read_overview_report_cache(
            snapshot_date,
            business_id,
            snapshot_signature=snapshot_signature,
            schedule_signature=schedule_signature,
        )
    except Exception:
        logger.debug("Forbyggd oversiktsrapport otillganglig for %s; bygger fran CSV.", snapshot_date, exc_info=True)
        report = None
        cache_ready = False

    if report is None:
        files = productivity_snapshot_files(snapshot_date)
        report = _build_cached_person_productivity_report(
            db,
            files,
            report_date=snapshot_date,
            business_id=business_id,
            sync=current_sync,
        )
        if cache_ready:
            try:
                write_overview_report_cache(
                    snapshot_date,
                    business_id,
                    report,
                    snapshot_signature=snapshot_signature,
                    schedule_signature=schedule_signature,
                )
            except Exception:
                logger.warning("Kunde inte skriva forbyggd oversiktsrapport for %s.", snapshot_date, exc_info=True)
    report["source_status"] = source_status
    return report, source_status


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


def _emit_overview_progress(callback, **event) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except Exception:
        # Progressrapportering får aldrig fälla själva hämtningen.
        pass


def _productivity_overview_day_worker_count(day_count: int, db: Session) -> int:
    if day_count < 2 or not isinstance(db, Session):
        return 1
    try:
        bind = db.get_bind()
        dialect_name = str(bind.dialect.name or "").lower()
    except Exception:
        return 1
    if dialect_name == "sqlite":
        database_name = str(getattr(getattr(bind, "url", None), "database", "") or "")
        if not database_name or database_name == ":memory:":
            return 1
    return min(_PRODUCTIVITY_OVERVIEW_DAY_WORKERS, day_count)


def _productivity_overview_day_session_factory(db: Session):
    bind = db.get_bind()
    return sessionmaker(bind=bind, autoflush=False, autocommit=False)


def _build_productivity_overview_day(
    request: Request,
    db: Session,
    user: User,
    day: date,
    finance_context: dict,
    *,
    ensure_snapshot: bool = False,
    wait_seconds: float = 0,
) -> tuple[dict, dict]:
    report, day_source_status = _build_productivity_report_for_date(
        request,
        db,
        user,
        day,
        ensure_snapshot=ensure_snapshot,
        wait_seconds=wait_seconds,
    )
    productivity_finance_helpers._attach_productivity_finance(report, finance_context, include_process_revenues=False)
    source_entry = {
        "date": day.isoformat(),
        "status": "ok",
        "source": (report.get("sync") or {}).get("source"),
        "sources": day_source_status,
    }
    return report, source_entry


def _run_productivity_overview(
    request: Request,
    db: Session,
    user: User,
    *,
    period: str,
    date_filter: date | None,
    start_date: date | None,
    end_date: date | None,
    progress_callback=None,
) -> dict:
    normalized_period = str(period or "day").strip().lower()
    period_start, period_end, period_label = _overview_period_bounds(
        normalized_period,
        anchor_date=date_filter,
        start_date=start_date,
        end_date=end_date,
    )
    days = _date_span(period_start, period_end)
    business_id = productivity_finance_helpers._productivity_business_id(db, user)
    finance_context = productivity_finance_helpers._productivity_finance_context(db, user, business_id)
    errors_by_day: dict[date, dict] = {}
    reports_by_day: dict[date, dict] = {}
    source_status_by_day: dict[date, dict] = {}
    total_steps = len(days) + 1
    completed_steps = 0
    progress_lock = threading.Lock()
    day_steps = {day: index for index, day in enumerate(days, start=1)}
    ensure_day_snapshot = normalized_period == "day" and len(days) == 1
    day_snapshot_wait_seconds = (
        _PRODUCTIVITY_OVERVIEW_DAY_SNAPSHOT_WAIT_SECONDS
        if ensure_day_snapshot
        else 0
    )

    def emit_day_started(day: date) -> None:
        with progress_lock:
            completed = completed_steps
        _emit_overview_progress(
            progress_callback,
            step=day_steps[day],
            total=total_steps,
            key=day.isoformat(),
            label=f"Hämtar {day.isoformat()}",
            completed=completed,
        )

    def emit_day_done(day: date, *, missing: bool = False) -> None:
        nonlocal completed_steps
        with progress_lock:
            completed_steps += 1
            completed = completed_steps
        _emit_overview_progress(
            progress_callback,
            step=day_steps[day],
            total=total_steps,
            key=day.isoformat(),
            label=f"{day.isoformat()} {'saknas' if missing else 'klar'}",
            done=True,
            completed=completed,
        )

    def record_day_result(day: date, report: dict, source_entry: dict) -> None:
        reports_by_day[day] = report
        source_status_by_day[day] = source_entry

    def record_day_error(day: date, exc: Exception) -> None:
        errors_by_day[day] = {"date": day.isoformat(), "error_type": type(exc).__name__, "message": str(exc)}

    day_workers = _productivity_overview_day_worker_count(len(days), db)
    if day_workers <= 1:
        for day in days:
            emit_day_started(day)
            try:
                report, source_entry = _build_productivity_overview_day(
                    request,
                    db,
                    user,
                    day,
                    finance_context,
                    ensure_snapshot=ensure_day_snapshot,
                    wait_seconds=day_snapshot_wait_seconds,
                )
                record_day_result(day, report, source_entry)
                emit_day_done(day)
            except (ProductivitySourceError, ProductivitySyncError) as exc:
                record_day_error(day, exc)
                emit_day_done(day, missing=True)
    else:
        try:
            session_factory = _productivity_overview_day_session_factory(db)
        except Exception:
            session_factory = None

        if session_factory is None:
            for day in days:
                emit_day_started(day)
                try:
                    report, source_entry = _build_productivity_overview_day(
                        request,
                        db,
                        user,
                        day,
                        finance_context,
                        ensure_snapshot=ensure_day_snapshot,
                        wait_seconds=day_snapshot_wait_seconds,
                    )
                    record_day_result(day, report, source_entry)
                    emit_day_done(day)
                except (ProductivitySourceError, ProductivitySyncError) as exc:
                    record_day_error(day, exc)
                    emit_day_done(day, missing=True)
        else:
            def build_day_in_worker(day: date) -> tuple[date, dict, dict]:
                emit_day_started(day)
                worker_db = session_factory()
                try:
                    report, source_entry = _build_productivity_overview_day(
                        request,
                        worker_db,
                        user,
                        day,
                        finance_context,
                        ensure_snapshot=ensure_day_snapshot,
                        wait_seconds=day_snapshot_wait_seconds,
                    )
                    return day, report, source_entry
                finally:
                    worker_db.close()

            with ThreadPoolExecutor(max_workers=day_workers, thread_name_prefix="productivity-overview-day") as executor:
                future_by_day = {executor.submit(build_day_in_worker, day): day for day in days}
                for future in as_completed(future_by_day):
                    day = future_by_day[future]
                    try:
                        result_day, report, source_entry = future.result()
                        record_day_result(result_day, report, source_entry)
                        emit_day_done(result_day)
                    except (ProductivitySourceError, ProductivitySyncError) as exc:
                        record_day_error(day, exc)
                        emit_day_done(day, missing=True)

    reports = [reports_by_day[day] for day in days if day in reports_by_day]
    source_status = [source_status_by_day[day] for day in days if day in source_status_by_day]
    errors = [errors_by_day[day] for day in days if day in errors_by_day]

    if not reports and errors:
        first_error = errors[0]
        status_code = status.HTTP_502_BAD_GATEWAY if first_error.get("error_type") == "ProductivitySyncError" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code, detail=str(first_error.get("message") or "Produktivitetsperioden kunde inte hämtas."))

    _emit_overview_progress(
        progress_callback,
        step=total_steps,
        total=total_steps,
        key="build",
        label="Bygger översikt",
        completed=len(days),
    )
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
        "prebuild": productivity_prebuild_status(),
    }
    if finance_context.get("visible"):
        finance_summary = productivity_finance_helpers._empty_productivity_finance_summary(currency=str(finance_context.get("currency") or "SEK"))
        for report in reports:
            productivity_finance_helpers._add_productivity_finance_summary(finance_summary, report.get("finance") or {})
        productivity_finance_helpers._add_productivity_finance_process_revenues(finance_summary, finance_context.get("process_revenue_rows") or [])
        payload["finance"] = finance_summary
    else:
        payload["finance"] = {"visible": False}
    _audit_productivity_report_sources(db, user, status_text="ok", source_status=source_status)
    return payload


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def build_business_summary_payload(
    db: Session,
    user: User,
    *,
    period: str = "day",
    anchor_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Bolagsindelad intäkt/kostnad-summering för en period.

    Delad implementation för endpointen /productivity/overview/business-summary
    och apphjälpens finance_summary-tool. Request-objektet behövs inte —
    rapportbyggaren använder det inte.
    """
    normalized_period = str(period or "day").strip().lower()
    period_start, period_end, period_label = _overview_period_bounds(
        normalized_period,
        anchor_date=anchor_date,
        start_date=start_date,
        end_date=end_date,
    )
    days = _date_span(period_start, period_end)
    business_id = productivity_finance_helpers._productivity_business_id(db, user)
    finance_context = productivity_finance_helpers._productivity_finance_context(db, user, business_id)
    finance_visible = bool(finance_context.get("visible"))
    currency = str(finance_context.get("currency") or "SEK")
    summaries: dict[str, dict] = {}
    errors: list[dict] = []
    reports: list[dict] = []
    source_status: list[dict] = []

    for day in days:
        try:
            report, day_source_status = _build_productivity_report_for_date(
                None,
                db,
                user,
                day,
                ensure_snapshot=False,
                wait_seconds=0,
            )
            if finance_visible:
                productivity_finance_helpers._attach_productivity_finance(report, finance_context, include_process_revenues=False)
                productivity_finance_helpers._add_productivity_business_company_report_finance(
                    summaries,
                    report,
                    finance_context,
                    currency=currency,
                    finance_visible=finance_visible,
                )
            productivity_finance_helpers._add_productivity_zero_pick_rows(
                summaries,
                productivity_finance_helpers._productivity_zero_pick_rows_by_company(productivity_snapshot_files(day)),
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
        productivity_finance_helpers._add_productivity_business_company_process_revenues(
            summaries,
            finance_context.get("process_revenue_rows") or [],
            currency=currency,
            finance_visible=finance_visible,
        )

    companies, totals = productivity_finance_helpers._finalize_productivity_business_company_summaries(
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
        "business": productivity_finance_helpers._productivity_business_payload(db, user, business_id),
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

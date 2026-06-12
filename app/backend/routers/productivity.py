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
from ..models import Business, Person, User
from ..productivity_service import (
    ProductivitySourceError,
)
from ..productivity_kpi_rules import build_person_productivity_report_from_files
from ..productivity_sync import (
    LOCAL_TZ,
    ProductivitySyncError,
    ensure_productivity_snapshot,
    productivity_backfill_status,
    productivity_snapshot_files,
    productivity_snapshot_status,
    sync_productivity_snapshot,
)
from ..workflow_data import productivity_api_source_map, sources_available


router = APIRouter(prefix="/api/productivity", tags=["productivity"])
logger = logging.getLogger(__name__)
_PERSON_REPORT_CACHE_TTL_SECONDS = 2 * 60
_PERSON_REPORT_CACHE_MAX_ITEMS = 256
_PERSON_REPORT_CACHE_LOCK = threading.Lock()
_PERSON_REPORT_CACHE: dict[tuple, tuple[float, dict]] = {}


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

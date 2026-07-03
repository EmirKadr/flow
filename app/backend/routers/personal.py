from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
from pathlib import Path
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..home_activity import build_home_activity_resolver
from ..models import Activity, Area, Business, Person, ScheduleCell, User
from ..person_productivity_cache import (
    person_productivity_daily_report_if_current,
    person_productivity_period_stats_if_current,
)
from ..productivity_kpi_rules import build_person_productivity_report_from_files
from ..productivity_service import ProductivitySourceError
from ..productivity_sync import (
    ProductivitySyncError,
    productivity_backfill_status,
    productivity_snapshot_files,
    productivity_snapshot_status,
)
from ..schemas import (
    PersonalActivityTotal,
    PersonalPersonOut,
    PersonalProductivityOut,
    PersonalScheduleDay,
    PersonalScheduleOut,
    PersonalScheduleSegment,
    PersonalWeekSummary,
)
from ..template_service import get_template_hours_map_for_dates
from ..user_access import PERSON_ROLE, can_view_personal_pages, is_super_user, user_roles
from ..workflow_data import productivity_api_source_map, sources_available
from .productivity_helpers import _aggregate_person_activity_stats, _date_span, _period_bounds
from .schedule import HOURS, _covered_intervals, _schedule_date, _uncovered_intervals

router = APIRouter(prefix="/api/personal", tags=["personal"])
_PERSONAL_PRODUCTIVITY_REPORT_CACHE_TTL_SECONDS = 2 * 60
_PERSONAL_PRODUCTIVITY_REPORT_CACHE_MAX_ITEMS = 256
_PERSONAL_PRODUCTIVITY_REPORT_CACHE_LOCK = threading.Lock()
_PERSONAL_PRODUCTIVITY_REPORT_CACHE: dict[tuple, tuple[float, dict]] = {}

WEEKDAY_LABELS = {
    1: "Måndag",
    2: "Tisdag",
    3: "Onsdag",
    4: "Torsdag",
    5: "Fredag",
    6: "Lördag",
    7: "Söndag",
}


def _hours(minutes: int) -> float:
    return round(float(minutes) / 60.0, 2)


def _segment_time(hour: int, minute: int) -> str:
    return f"{int(hour):02d}:{int(minute):02d}"


def _person_query(db: Session):
    return select(Person).where(Person.is_active.is_(True)).order_by(Person.business_id, Person.sort_order, Person.name)


def _person_out(person: Person, businesses_by_id: dict[int, Business], areas_by_id: dict[int, Area]) -> PersonalPersonOut:
    business = businesses_by_id.get(person.business_id)
    area = areas_by_id.get(person.home_area_id)
    return PersonalPersonOut(
        id=person.id,
        name=person.name,
        noman=person.noman,
        business_id=person.business_id,
        business_name=business.name if business is not None else None,
        home_area_id=person.home_area_id,
        home_area=area.name if area is not None else None,
    )


def _person_maps(db: Session) -> tuple[dict[int, Business], dict[int, Area]]:
    businesses = db.execute(select(Business)).scalars().all()
    areas = db.execute(select(Area)).scalars().all()
    return {business.id: business for business in businesses}, {area.id: area for area in areas}


def _match_person_by_noman(db: Session, username: str) -> Person | None:
    cleaned = username.strip()
    if not cleaned:
        return None
    matches = (
        db.query(Person)
        .filter(Person.is_active.is_(True), func.lower(func.trim(Person.noman)) == cleaned.lower())
        .order_by(Person.id.asc())
        .all()
    )
    if len(matches) > 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Flera personer har samma Noman-namn. Be en administratör rätta personregistret.",
        )
    return matches[0] if matches else None


def _resolve_person(db: Session, user: User, person_id: int | None) -> Person:
    if not can_view_personal_pages(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Sidan kräver personlig vy-behörighet")

    if is_super_user(user):
        target_id = person_id if person_id is not None else user.person_id
        if target_id is not None:
            person = db.get(Person, target_id)
            if person is None or person.is_active is not True:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person hittades inte")
            return person
        person = db.execute(_person_query(db)).scalars().first()
        if person is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ingen aktiv person hittades")
        return person

    if PERSON_ROLE not in user_roles(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Sidan kräver rollen Person")

    person = db.get(Person, user.person_id) if user.person_id is not None else None
    if person is None:
        person = _match_person_by_noman(db, user.username)
        if person is not None:
            user.person_id = person.id
            user.business_id = person.business_id
            user.area_id = person.home_area_id
            db.commit()
            db.refresh(user)
    if person is None or person.is_active is not True:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Personkoppling saknas")
    if person_id is not None and person_id != person.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Du kan bara se ditt eget schema")
    return person


def _activities_for_business(db: Session, business_id: int | None) -> list[Activity]:
    query = select(Activity).where(Activity.is_active.is_(True))
    if business_id is not None:
        query = query.where(Activity.business_id == business_id)
    return db.execute(query.order_by(Activity.sort_order, Activity.label)).scalars().all()


def _areas_for_business(db: Session, business_id: int | None) -> list[Area]:
    query = select(Area).where(Area.is_active.is_(True))
    if business_id is not None:
        query = query.where(Area.business_id == business_id)
    return db.execute(query.order_by(Area.sort_order, Area.name)).scalars().all()


def _activity_total_list(totals: dict[tuple[int | None, str, str | None, str | None], int]) -> list[PersonalActivityTotal]:
    rows: list[PersonalActivityTotal] = []
    for (activity_id, label, color, category), minutes in totals.items():
        if minutes <= 0:
            continue
        rows.append(
            PersonalActivityTotal(
                activity_id=activity_id,
                label=label,
                color=color,
                category=category,
                minutes=minutes,
                hours=_hours(minutes),
            )
        )
    return sorted(rows, key=lambda row: (-row.minutes, row.label.lower()))


def _total_key(
    *,
    activity_id: int | None,
    label: str,
    color: str | None,
    category: str | None,
) -> tuple[int | None, str, str | None, str | None]:
    return (activity_id, label, color, category)


def _make_segment(
    *,
    hour: int,
    minute_start: int,
    minute_end: int,
    label: str,
    source: str,
    activity_id: int | None = None,
    color: str | None = None,
    category: str | None = None,
) -> PersonalScheduleSegment:
    minutes = max(0, int(minute_end) - int(minute_start))
    return PersonalScheduleSegment(
        hour=hour,
        minute_start=minute_start,
        minute_end=minute_end,
        start=_segment_time(hour, minute_start),
        end=_segment_time(hour if minute_end < 60 else hour + 1, 0 if minute_end == 60 else minute_end),
        label=label,
        activity_id=activity_id,
        color=color,
        category=category,
        source=source,
        minutes=minutes,
    )


def _build_schedule_payload(db: Session, person: Person, year: int, week: int) -> PersonalScheduleOut:
    businesses_by_id, areas_by_id = _person_maps(db)
    activities = _activities_for_business(db, person.business_id)
    areas = _areas_for_business(db, person.business_id)
    activities_by_id = {activity.id: activity for activity in activities}
    home_activity_id = build_home_activity_resolver(activities, areas)(person)
    week_dates = {weekday: _schedule_date(year, week, weekday) for weekday in range(1, 8)}
    template_hours_map = get_template_hours_map_for_dates(db, [person.id], week_dates.values())

    cells = (
        db.execute(
            select(ScheduleCell).where(
                ScheduleCell.year == year,
                ScheduleCell.week == week,
                ScheduleCell.person_id == person.id,
            )
        )
        .scalars()
        .all()
    )
    cells_by_weekday_hour: dict[tuple[int, int], list[ScheduleCell]] = defaultdict(list)
    for cell in cells:
        cells_by_weekday_hour[(cell.weekday, cell.hour)].append(cell)

    days: list[PersonalScheduleDay] = []
    week_totals: dict[tuple[int | None, str, str | None, str | None], int] = defaultdict(int)
    summary_total = 0
    summary_work = 0
    summary_absence = 0
    scheduled_days = 0

    for weekday in range(1, 8):
        selected_date = _schedule_date(year, week, weekday)
        template_hours = template_hours_map.get((person.id, week_dates[weekday]))
        segments: list[PersonalScheduleSegment] = []
        day_totals: dict[tuple[int | None, str, str | None, str | None], int] = defaultdict(int)

        for hour in HOURS:
            hour_cells = sorted(cells_by_weekday_hour.get((weekday, hour), []), key=lambda cell: (cell.minute_start, cell.minute_end))
            for cell in hour_cells:
                if cell.activity_id is not None:
                    activity = activities_by_id.get(cell.activity_id)
                    label = activity.label if activity is not None else "Okänd aktivitet"
                    color = activity.color if activity is not None else None
                    category = activity.category if activity is not None else "work"
                    segment = _make_segment(
                        hour=hour,
                        minute_start=cell.minute_start,
                        minute_end=cell.minute_end,
                        label=label,
                        source="registrerad",
                        activity_id=cell.activity_id,
                        color=color,
                        category=category,
                    )
                    segments.append(segment)
                    key = _total_key(activity_id=cell.activity_id, label=label, color=color, category=category)
                    day_totals[key] += segment.minutes
                    week_totals[key] += segment.minutes
                elif cell.empty_override:
                    segments.append(
                        _make_segment(
                            hour=hour,
                            minute_start=cell.minute_start,
                            minute_end=cell.minute_end,
                            label="Ledig",
                            source="ledig",
                        )
                    )

            if template_hours is not None and hour in template_hours:
                covered = _covered_intervals(hour_cells)
                for start, end in _uncovered_intervals(covered):
                    if home_activity_id is not None:
                        activity = activities_by_id.get(home_activity_id)
                        label = activity.label if activity is not None else "Standardtid"
                        color = activity.color if activity is not None else None
                        category = activity.category if activity is not None else "work"
                        activity_id = home_activity_id
                    else:
                        label = "Standardtid"
                        color = None
                        category = "work"
                        activity_id = None
                    segment = _make_segment(
                        hour=hour,
                        minute_start=start,
                        minute_end=end,
                        label=label,
                        source="standard",
                        activity_id=activity_id,
                        color=color,
                        category=category,
                    )
                    segments.append(segment)
                    key = _total_key(activity_id=activity_id, label=label, color=color, category=category)
                    day_totals[key] += segment.minutes
                    week_totals[key] += segment.minutes

        segments.sort(key=lambda segment: (segment.hour, segment.minute_start, segment.minute_end, segment.label))
        total_minutes = sum(segment.minutes for segment in segments if segment.source != "ledig")
        work_minutes = sum(
            segment.minutes
            for segment in segments
            if segment.source != "ledig" and segment.category != "absence"
        )
        absence_minutes = sum(
            segment.minutes
            for segment in segments
            if segment.source != "ledig" and segment.category == "absence"
        )
        if work_minutes and absence_minutes:
            status_label = "Blandat"
        elif work_minutes:
            status_label = "Planerad"
        elif absence_minutes:
            status_label = "Frånvaro"
        else:
            status_label = "Ledig"
        if total_minutes > 0:
            scheduled_days += 1
        summary_total += total_minutes
        summary_work += work_minutes
        summary_absence += absence_minutes

        days.append(
            PersonalScheduleDay(
                date=selected_date.isoformat(),
                weekday=weekday,
                weekday_label=WEEKDAY_LABELS[weekday],
                status=status_label,
                total_minutes=total_minutes,
                work_minutes=work_minutes,
                absence_minutes=absence_minutes,
                segments=segments,
                activities=_activity_total_list(day_totals),
            )
        )

    return PersonalScheduleOut(
        year=year,
        week=week,
        person=_person_out(person, businesses_by_id, areas_by_id),
        days=days,
        summary=PersonalWeekSummary(
            total_minutes=summary_total,
            work_minutes=summary_work,
            absence_minutes=summary_absence,
            scheduled_days=scheduled_days,
            activities=_activity_total_list(week_totals),
        ),
    )


@router.get("/persons", response_model=list[PersonalPersonOut])
def list_personal_persons(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PersonalPersonOut]:
    if not can_view_personal_pages(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Sidan kräver personlig vy-behörighet")
    businesses_by_id, areas_by_id = _person_maps(db)
    if is_super_user(user):
        persons = db.execute(_person_query(db)).scalars().all()
        return [_person_out(person, businesses_by_id, areas_by_id) for person in persons]
    return [_person_out(_resolve_person(db, user, None), businesses_by_id, areas_by_id)]


@router.get("/schedule", response_model=PersonalScheduleOut)
def get_personal_schedule(
    year: int | None = Query(None, ge=2000, le=2100),
    week: int | None = Query(None, ge=1, le=53),
    person_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PersonalScheduleOut:
    today = date.today()
    current_iso = today.isocalendar()
    selected_year = year or current_iso.year
    selected_week = week or current_iso.week
    person = _resolve_person(db, user, person_id)
    return _build_schedule_payload(db, person, selected_year, selected_week)


def _empty_personal_productivity_stats(
    *,
    period_type: str,
    period_label: str,
    period_start: date,
    period_end: date,
    requested_days: int,
    status_text: str,
    missing_dates: list[str],
    errors: list[dict],
) -> dict:
    return {
        "status": status_text,
        "period": {
            "type": period_type,
            "label": period_label,
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
            "requested_days": requested_days,
        },
        "dates": [],
        "missing_dates": missing_dates,
        "source_status": [],
        "errors": errors[:20],
        "activities": [],
        "summary": {},
    }


def _personal_productivity_report_cache_key(
    files: dict[str, Path],
    report_date: date,
    business_id: int | None,
    sync: dict,
) -> tuple:
    parts: list[tuple] = [
        ("date", report_date.isoformat()),
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


def _build_cached_personal_productivity_report(
    db: Session,
    files: dict[str, Path],
    *,
    report_date: date,
    business_id: int | None,
    sync: dict,
) -> dict:
    key = _personal_productivity_report_cache_key(files, report_date, business_id, sync)
    now = time.monotonic()
    with _PERSONAL_PRODUCTIVITY_REPORT_CACHE_LOCK:
        cached = _PERSONAL_PRODUCTIVITY_REPORT_CACHE.get(key)
        if cached and cached[0] > now:
            return deepcopy(cached[1])
        if cached:
            _PERSONAL_PRODUCTIVITY_REPORT_CACHE.pop(key, None)

    report = build_person_productivity_report_from_files(
        db,
        files,
        report_date=report_date,
        business_id=business_id,
        sync=sync,
    )
    with _PERSONAL_PRODUCTIVITY_REPORT_CACHE_LOCK:
        if len(_PERSONAL_PRODUCTIVITY_REPORT_CACHE) >= _PERSONAL_PRODUCTIVITY_REPORT_CACHE_MAX_ITEMS:
            _PERSONAL_PRODUCTIVITY_REPORT_CACHE.pop(next(iter(_PERSONAL_PRODUCTIVITY_REPORT_CACHE)), None)
        _PERSONAL_PRODUCTIVITY_REPORT_CACHE[key] = (
            now + _PERSONAL_PRODUCTIVITY_REPORT_CACHE_TTL_SECONDS,
            deepcopy(report),
        )
    return report


def _personal_productivity_report_for_day(
    db: Session,
    person: Person,
    day: date,
    sync_status: dict,
    report_cache: dict[date, dict] | None,
) -> dict:
    if report_cache is not None and day in report_cache:
        return report_cache[day]

    report = person_productivity_daily_report_if_current(
        db,
        day,
        business_id=person.business_id,
        person_id=person.id,
        sync=sync_status,
    )
    if report is None:
        report = _build_cached_personal_productivity_report(
            db,
            productivity_snapshot_files(day),
            report_date=day,
            business_id=person.business_id,
            sync=sync_status,
        )
    if report_cache is not None:
        report_cache[day] = report
    return report


def _personal_productivity_stats(
    db: Session,
    person: Person,
    *,
    period: str,
    anchor_date: date,
    report_cache: dict[date, dict] | None = None,
) -> dict:
    period_start, period_end, period_label = _period_bounds(
        period,
        anchor_date=anchor_date,
        start_date=None,
        end_date=None,
    )
    days = _date_span(period_start, period_end)
    period_type = str(period or "week").strip().lower()

    api_sources_ready = sources_available(tuple(productivity_api_source_map().values()))
    if not api_sources_ready:
        return _empty_personal_productivity_stats(
            period_type=period_type,
            period_label=period_label,
            period_start=period_start,
            period_end=period_end,
            requested_days=len(days),
            status_text="unavailable",
            missing_dates=[day.isoformat() for day in days],
            errors=[],
        )

    reports: list[dict] = []
    ready_days: list[date] = []
    sync_by_day: dict[date, dict] = {}
    missing_dates: list[str] = []
    errors: list[dict] = []
    source_status: list[dict] = []

    for day in days:
        sync_status = productivity_snapshot_status(day)
        sync_by_day[day] = sync_status
        if not sync_status.get("ready"):
            missing_dates.append(day.isoformat())
            source_status.append({"date": day.isoformat(), "status": "missing", "source": sync_status.get("source")})
            continue
        ready_days.append(day)

    cached_aggregate = person_productivity_period_stats_if_current(
        db,
        ready_days,
        business_id=person.business_id,
        person_id=person.id,
        sync_by_date=sync_by_day,
    )
    if cached_aggregate is not None:
        if ready_days and missing_dates:
            status_text = "partial"
        elif ready_days:
            status_text = "ok"
        else:
            status_text = "missing"
        return {
            "status": status_text,
            "period": {
                "type": period_type,
                "label": period_label,
                "start_date": period_start.isoformat(),
                "end_date": period_end.isoformat(),
                "requested_days": len(days),
            },
            "dates": cached_aggregate["dates"],
            "missing_dates": missing_dates,
            "source_status": [
                *source_status,
                *[
                    {"date": day.isoformat(), "status": "ok", "source": sync_by_day[day].get("source")}
                    for day in ready_days
                ],
            ],
            "errors": [],
            "activities": cached_aggregate["activities"],
            "summary": cached_aggregate["summary"],
        }

    for day in ready_days:
        sync_status = sync_by_day[day]
        try:
            report = _personal_productivity_report_for_day(db, person, day, sync_status, report_cache)
            reports.append(report)
            source_status.append({"date": day.isoformat(), "status": "ok", "source": sync_status.get("source")})
        except (ProductivitySourceError, ProductivitySyncError, OSError, ValueError) as exc:
            missing_dates.append(day.isoformat())
            source_status.append({"date": day.isoformat(), "status": "error", "source": sync_status.get("source")})
            errors.append({"date": day.isoformat(), "error_type": type(exc).__name__, "message": str(exc)})

    aggregate = _aggregate_person_activity_stats(reports, person.id)
    if reports and missing_dates:
        status_text = "partial"
    elif reports:
        status_text = "ok"
    else:
        status_text = "missing"
    return {
        "status": status_text,
        "period": {
            "type": period_type,
            "label": period_label,
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
            "requested_days": len(days),
        },
        "dates": [str(report.get("date") or "") for report in reports],
        "missing_dates": missing_dates,
        "source_status": source_status,
        "errors": errors[:20],
        **aggregate,
    }


def _personal_productivity_data(db: Session, person: Person, selected_date: date) -> dict:
    report_cache: dict[date, dict] = {}
    return {
        "day": _personal_productivity_stats(
            db,
            person,
            period="day",
            anchor_date=selected_date,
            report_cache=report_cache,
        ),
        "week": _personal_productivity_stats(
            db,
            person,
            period="week",
            anchor_date=selected_date,
            report_cache=report_cache,
        ),
        "backfill": productivity_backfill_status(),
    }


@router.get("/productivity", response_model=PersonalProductivityOut)
def get_personal_productivity(
    selected_date: date | None = Query(None, alias="date"),
    person_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PersonalProductivityOut:
    day = selected_date or date.today()
    iso = day.isocalendar()
    person = _resolve_person(db, user, person_id)
    schedule = _build_schedule_payload(db, person, iso.year, iso.week)
    matching_day = next(item for item in schedule.days if item.weekday == iso.weekday)
    return PersonalProductivityOut(
        date=day.isoformat(),
        year=iso.year,
        week=iso.week,
        weekday=iso.weekday,
        person=schedule.person,
        day=matching_day,
        summary=schedule.summary,
        productivity=_personal_productivity_data(db, person, day),
    )

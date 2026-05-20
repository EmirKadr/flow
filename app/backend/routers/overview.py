import logging
import traceback
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..deps import get_db, require_view_access
from ..home_activity import build_home_activity_resolver, person_out_with_home_activity
from ..models import Activity, Area, Person, ScheduleCell, User
from ..schedule_locks import assert_can_modify_schedule_cells, foreign_schedule_cell_lock_applies
from ..schemas import PersonOut
from ..template_service import get_template_hours_map

logger = logging.getLogger("overview")

router = APIRouter(prefix="/api/overview", tags=["overview"])


class OverviewCell(BaseModel):
    person_id: int
    weekday: int
    activity_id: int | None
    mixed: bool
    hours_total: float
    template_hours: int


class OverviewOut(BaseModel):
    year: int
    week: int
    persons: list[PersonOut]
    matrix: list[OverviewCell]


class MonthDay(BaseModel):
    date: str
    year: int
    week: int
    weekday: int


class MonthOverviewCell(BaseModel):
    person_id: int
    date: str
    activity_id: int | None
    mixed: bool
    hours_total: float
    template_hours: int


class MonthOverviewOut(BaseModel):
    year: int
    month: int
    days: list[MonthDay]
    persons: list[PersonOut]
    matrix: list[MonthOverviewCell]


class OverviewDayRequest(BaseModel):
    person_id: int
    year: int
    week: int
    weekday: int
    activity_id: int | None


class OverviewBulkDayRequest(BaseModel):
    days: list[OverviewDayRequest]
    atomic: bool = False


def _hours_from_minutes(total_minutes: int) -> float:
    return round(float(total_minutes) / 60.0, 2)


def _effective_minutes_by_activity(
    *,
    explicit_minutes: dict[int, int],
    covered_minutes: dict[int, int],
    template: set[int] | None,
    home_activity_id: int | None,
) -> dict[int, int]:
    minutes_by_activity = dict(explicit_minutes)
    if template is None or home_activity_id is None:
        return minutes_by_activity

    for hour in template:
        remaining = 60 - covered_minutes.get(hour, 0)
        if remaining <= 0:
            continue
        minutes_by_activity[home_activity_id] = minutes_by_activity.get(home_activity_id, 0) + remaining

    return minutes_by_activity


def _summarize_day(minutes_by_activity: dict[int, int]) -> tuple[int | None, bool, int]:
    total_minutes = sum(minutes_by_activity.values())
    if not minutes_by_activity:
        return None, False, total_minutes

    dominant = max(minutes_by_activity.items(), key=lambda item: item[1])[0]
    mixed = len(minutes_by_activity) > 1
    return dominant, mixed, total_minutes


def _sorted_segments(cells: list[ScheduleCell]) -> list[ScheduleCell]:
    return sorted(cells, key=lambda cell: (cell.minute_start, cell.minute_end))


def _segment_snapshot(cell: ScheduleCell) -> dict:
    return {
        "minute_start": cell.minute_start,
        "minute_end": cell.minute_end,
        "activity_id": cell.activity_id,
        "empty_override": cell.empty_override,
        "version": cell.version,
    }


def _hour_snapshot(
    *,
    payload: OverviewDayRequest,
    hour: int,
    cells: list[ScheduleCell],
) -> dict:
    return {
        "person_id": payload.person_id,
        "year": payload.year,
        "week": payload.week,
        "weekday": payload.weekday,
        "hour": hour,
        "segments": [_segment_snapshot(cell) for cell in _sorted_segments(cells)],
    }


def _day_hour_snapshots(
    *,
    payload: OverviewDayRequest,
    template_hours: set[int],
    cells_by_hour: dict[int, list[ScheduleCell]],
) -> list[dict]:
    return [
        _hour_snapshot(
            payload=payload,
            hour=hour,
            cells=cells_by_hour.get(hour, []),
        )
        for hour in sorted(template_hours)
    ]


def _load_day_cells_by_hour(
    db: Session,
    payload: OverviewDayRequest,
    template_hours: set[int],
) -> dict[int, list[ScheduleCell]]:
    if not template_hours:
        return {}
    rows = db.execute(
        select(ScheduleCell).where(
            ScheduleCell.year == payload.year,
            ScheduleCell.week == payload.week,
            ScheduleCell.weekday == payload.weekday,
            ScheduleCell.person_id == payload.person_id,
            ScheduleCell.hour.in_(sorted(template_hours)),
        )
    ).scalars().all()
    cells_by_hour: dict[int, list[ScheduleCell]] = defaultdict(list)
    for cell in rows:
        cells_by_hour[cell.hour].append(cell)
    return cells_by_hour


def _day_cell_payload(
    payload: OverviewDayRequest,
    template_hours: set[int] | None,
    *,
    written: int,
    deleted: int,
) -> dict:
    template_count = 0 if template_hours is None else len(template_hours)
    hours_total = 0 if payload.activity_id is None else float(template_count)
    return {
        "person_id": payload.person_id,
        "year": payload.year,
        "week": payload.week,
        "weekday": payload.weekday,
        "activity_id": payload.activity_id,
        "mixed": False,
        "hours_total": hours_total,
        "template_hours": template_count,
        "written": written,
        "deleted": deleted,
    }


def _bulk_error_payload(payload: OverviewDayRequest, exc: HTTPException) -> dict:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return {
        "person_id": payload.person_id,
        "year": payload.year,
        "week": payload.week,
        "weekday": payload.weekday,
        "status": exc.status_code,
        "detail": detail,
    }


def _apply_day_impl(
    payload: OverviewDayRequest,
    db: Session,
    user: User,
    *,
    template_hours: set[int] | None,
    owner_lock_enabled: bool,
) -> dict:
    if template_hours is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                "Personen är markerad som ledig denna dag. "
                "Ändra schemat först eller bemanna i bemanningsvyn."
            ),
        )
    if not template_hours:
        cell = _day_cell_payload(payload, template_hours, written=0, deleted=0)
        return {"written": 0, "deleted": 0, "cell": cell, "before_hours": [], "after_hours": []}

    existing = db.execute(
        select(ScheduleCell).where(
            ScheduleCell.year == payload.year,
            ScheduleCell.week == payload.week,
            ScheduleCell.weekday == payload.weekday,
            ScheduleCell.person_id == payload.person_id,
            ScheduleCell.hour.in_(sorted(template_hours)),
        )
    ).scalars().all()
    existing_by_hour: dict[int, list[ScheduleCell]] = defaultdict(list)
    for cell in existing:
        existing_by_hour[cell.hour].append(cell)
    assert_can_modify_schedule_cells(existing, user, owner_lock_enabled)
    before_hours = _day_hour_snapshots(
        payload=payload,
        template_hours=template_hours,
        cells_by_hour=existing_by_hour,
    )

    written = 0
    deleted = 0

    for hour in sorted(template_hours):
        cells_for_hour = _sorted_segments(existing_by_hour.get(hour, []))

        if payload.activity_id is None:
            if (
                len(cells_for_hour) == 1
                and cells_for_hour[0].minute_start == 0
                and cells_for_hour[0].minute_end == 60
            ):
                cell = cells_for_hour[0]
                if cell.activity_id is None and cell.empty_override:
                    continue
                old = {
                    "minute_start": cell.minute_start,
                    "minute_end": cell.minute_end,
                    "activity_id": cell.activity_id,
                    "empty_override": cell.empty_override,
                    "version": cell.version,
                }
                cell.activity_id = None
                cell.empty_override = True
                cell.version += 1
                cell.updated_by = user.id
                audit_log(
                    db,
                    entity_type="schedule_cell",
                    entity_id=cell.id,
                    action="overview_day_clear",
                    old_value=old,
                    new_value={
                        "minute_start": cell.minute_start,
                        "minute_end": cell.minute_end,
                        "activity_id": cell.activity_id,
                        "empty_override": cell.empty_override,
                        "version": cell.version,
                    },
                    user_id=user.id,
                )
                written += 1
                continue

            if cells_for_hour:
                for cell in cells_for_hour:
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=cell.id,
                        action="overview_day_clear",
                        old_value={
                            "minute_start": cell.minute_start,
                            "minute_end": cell.minute_end,
                            "activity_id": cell.activity_id,
                            "empty_override": cell.empty_override,
                            "version": cell.version,
                        },
                        new_value=None,
                        user_id=user.id,
                    )
                    db.delete(cell)
                    deleted += 1
                db.flush()

            cell = ScheduleCell(
                year=payload.year,
                week=payload.week,
                weekday=payload.weekday,
                hour=hour,
                minute_start=0,
                minute_end=60,
                person_id=payload.person_id,
                activity_id=None,
                empty_override=True,
                version=1,
                updated_by=user.id,
            )
            db.add(cell)
            db.flush()
            audit_log(
                db,
                entity_type="schedule_cell",
                entity_id=cell.id,
                action="overview_day_clear",
                old_value=None,
                new_value={
                    "minute_start": cell.minute_start,
                    "minute_end": cell.minute_end,
                    "activity_id": cell.activity_id,
                    "empty_override": cell.empty_override,
                    "version": 1,
                },
                user_id=user.id,
            )
            written += 1
            continue

        if (
            len(cells_for_hour) == 1
            and cells_for_hour[0].minute_start == 0
            and cells_for_hour[0].minute_end == 60
        ):
            cell = cells_for_hour[0]
            if cell.activity_id == payload.activity_id and not cell.empty_override:
                continue
            old = {
                "minute_start": cell.minute_start,
                "minute_end": cell.minute_end,
                "activity_id": cell.activity_id,
                "empty_override": cell.empty_override,
                "version": cell.version,
            }
            cell.activity_id = payload.activity_id
            cell.empty_override = False
            cell.version += 1
            cell.updated_by = user.id
            audit_log(
                db,
                entity_type="schedule_cell",
                entity_id=cell.id,
                action="overview_day_assign",
                old_value=old,
                new_value={
                    "minute_start": cell.minute_start,
                    "minute_end": cell.minute_end,
                    "activity_id": cell.activity_id,
                    "empty_override": cell.empty_override,
                    "version": cell.version,
                },
                user_id=user.id,
            )
            written += 1
            continue

        if cells_for_hour:
            for cell in cells_for_hour:
                audit_log(
                    db,
                    entity_type="schedule_cell",
                    entity_id=cell.id,
                    action="overview_day_clear",
                    old_value={
                        "minute_start": cell.minute_start,
                        "minute_end": cell.minute_end,
                        "activity_id": cell.activity_id,
                        "empty_override": cell.empty_override,
                        "version": cell.version,
                    },
                    new_value=None,
                    user_id=user.id,
                )
                db.delete(cell)
                deleted += 1
            db.flush()

        cell = ScheduleCell(
            year=payload.year,
            week=payload.week,
            weekday=payload.weekday,
            hour=hour,
            minute_start=0,
            minute_end=60,
            person_id=payload.person_id,
            activity_id=payload.activity_id,
            empty_override=False,
            version=1,
            updated_by=user.id,
        )
        db.add(cell)
        db.flush()
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=cell.id,
            action="overview_day_assign",
            old_value=None,
            new_value={
                "minute_start": cell.minute_start,
                "minute_end": cell.minute_end,
                "activity_id": cell.activity_id,
                "empty_override": cell.empty_override,
                "version": 1,
            },
            user_id=user.id,
        )
        written += 1

    db.flush()
    after_hours = _day_hour_snapshots(
        payload=payload,
        template_hours=template_hours,
        cells_by_hour=_load_day_cells_by_hour(db, payload, template_hours),
    )

    return {
        "written": written,
        "deleted": deleted,
        "cell": _day_cell_payload(payload, template_hours, written=written, deleted=deleted),
        "before_hours": before_hours,
        "after_hours": after_hours,
    }


@router.get("", response_model=OverviewOut)
def get_overview(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    area_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_view_access("overview", "view")),
) -> OverviewOut:
    persons_q = select(Person).where(Person.is_active.is_(True))
    if area_id is not None:
        persons_q = persons_q.where(Person.home_area_id == area_id)
    persons_q = persons_q.order_by(Person.sort_order, Person.name)
    persons = db.execute(persons_q).scalars().all()
    person_ids = [p.id for p in persons]

    explicit_minutes: dict[tuple[int, int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    covered_minutes: dict[tuple[int, int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    if person_ids:
        rows = db.execute(
            select(
                ScheduleCell.person_id,
                ScheduleCell.weekday,
                ScheduleCell.hour,
                ScheduleCell.activity_id,
                ScheduleCell.empty_override,
                func.sum(ScheduleCell.minute_end - ScheduleCell.minute_start),
            )
            .where(
                ScheduleCell.year == year,
                ScheduleCell.week == week,
                ScheduleCell.person_id.in_(person_ids),
            )
            .group_by(
                ScheduleCell.person_id,
                ScheduleCell.weekday,
                ScheduleCell.hour,
                ScheduleCell.activity_id,
                ScheduleCell.empty_override,
            )
        ).all()
        for pid, wd, hour, aid, empty_override, cnt in rows:
            if aid is not None:
                explicit_minutes[(pid, wd)][aid] += int(cnt)
            if aid is not None or empty_override:
                covered_minutes[(pid, wd)][hour] = min(
                    60,
                    covered_minutes[(pid, wd)].get(hour, 0) + int(cnt),
                )

    home_activity_for = build_home_activity_resolver(db.query(Activity).all(), db.query(Area).all())
    template_hours_map = get_template_hours_map(db, person_ids, range(1, 8))
    matrix: list[OverviewCell] = []
    for person in persons:
        home_activity_id = home_activity_for(person)
        for weekday in range(1, 8):
            template_hours = template_hours_map.get((person.id, weekday))
            template_count = 0 if template_hours is None else len(template_hours)
            minutes_by_activity = _effective_minutes_by_activity(
                explicit_minutes=explicit_minutes.get((person.id, weekday), {}),
                covered_minutes=covered_minutes.get((person.id, weekday), {}),
                template=template_hours,
                home_activity_id=home_activity_id,
            )
            dominant, mixed, total_minutes = _summarize_day(minutes_by_activity)
            matrix.append(
                OverviewCell(
                    person_id=person.id,
                    weekday=weekday,
                    activity_id=dominant,
                    mixed=mixed,
                    hours_total=_hours_from_minutes(total_minutes),
                    template_hours=template_count,
                )
            )

    return OverviewOut(
        year=year,
        week=week,
        persons=[person_out_with_home_activity(person, home_activity_for(person)) for person in persons],
        matrix=matrix,
    )


@router.get("/month", response_model=MonthOverviewOut)
def get_month_overview(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    area_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_view_access("overview", "view")),
) -> MonthOverviewOut:
    first = date(year, month, 1)
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    days_list: list[MonthDay] = []
    current_day = first
    while current_day < next_month:
        iso_year, iso_week, iso_weekday = current_day.isocalendar()
        days_list.append(
            MonthDay(
                date=current_day.isoformat(),
                year=iso_year,
                week=iso_week,
                weekday=iso_weekday,
            )
        )
        current_day += timedelta(days=1)

    persons_q = select(Person).where(Person.is_active.is_(True))
    if area_id is not None:
        persons_q = persons_q.where(Person.home_area_id == area_id)
    persons_q = persons_q.order_by(Person.sort_order, Person.name)
    persons = db.execute(persons_q).scalars().all()
    person_ids = [p.id for p in persons]

    explicit_minutes: dict[tuple[int, int, int, int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    covered_minutes: dict[tuple[int, int, int, int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    if person_ids and days_list:
        ywd_tuples = list({(day.year, day.week, day.weekday) for day in days_list})
        rows = db.execute(
            select(
                ScheduleCell.person_id,
                ScheduleCell.year,
                ScheduleCell.week,
                ScheduleCell.weekday,
                ScheduleCell.hour,
                ScheduleCell.activity_id,
                ScheduleCell.empty_override,
                func.sum(ScheduleCell.minute_end - ScheduleCell.minute_start),
            )
            .where(
                ScheduleCell.person_id.in_(person_ids),
                tuple_(ScheduleCell.year, ScheduleCell.week, ScheduleCell.weekday).in_(ywd_tuples),
            )
            .group_by(
                ScheduleCell.person_id,
                ScheduleCell.year,
                ScheduleCell.week,
                ScheduleCell.weekday,
                ScheduleCell.hour,
                ScheduleCell.activity_id,
                ScheduleCell.empty_override,
            )
        ).all()
        for pid, iso_year, iso_week, iso_weekday, hour, aid, empty_override, cnt in rows:
            if aid is not None:
                explicit_minutes[(pid, iso_year, iso_week, iso_weekday)][aid] += int(cnt)
            if aid is not None or empty_override:
                covered_minutes[(pid, iso_year, iso_week, iso_weekday)][hour] = min(
                    60,
                    covered_minutes[(pid, iso_year, iso_week, iso_weekday)].get(hour, 0) + int(cnt),
                )

    home_activity_for = build_home_activity_resolver(db.query(Activity).all(), db.query(Area).all())
    template_hours_map = get_template_hours_map(db, person_ids, range(1, 8))
    matrix: list[MonthOverviewCell] = []
    for person in persons:
        home_activity_id = home_activity_for(person)
        for day_info in days_list:
            template_hours = template_hours_map.get((person.id, day_info.weekday))
            template_count = 0 if template_hours is None else len(template_hours)
            minutes_by_activity = _effective_minutes_by_activity(
                explicit_minutes=explicit_minutes.get((person.id, day_info.year, day_info.week, day_info.weekday), {}),
                covered_minutes=covered_minutes.get((person.id, day_info.year, day_info.week, day_info.weekday), {}),
                template=template_hours,
                home_activity_id=home_activity_id,
            )
            dominant, mixed, total_minutes = _summarize_day(minutes_by_activity)
            matrix.append(
                MonthOverviewCell(
                    person_id=person.id,
                    date=day_info.date,
                    activity_id=dominant,
                    mixed=mixed,
                    hours_total=_hours_from_minutes(total_minutes),
                    template_hours=template_count,
                )
            )

    return MonthOverviewOut(
        year=year,
        month=month,
        days=days_list,
        persons=[person_out_with_home_activity(person, home_activity_for(person)) for person in persons],
        matrix=matrix,
    )


@router.post("/day")
def set_day(
    payload: OverviewDayRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("overview", "edit")),
) -> dict:
    try:
        if not db.get(Person, payload.person_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person hittades inte")
        if payload.activity_id is not None and not db.get(Activity, payload.activity_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Aktivitet hittades inte")

        template_hours = get_template_hours_map(
            db,
            [payload.person_id],
            [payload.weekday],
        ).get((payload.person_id, payload.weekday))
        result = _apply_day_impl(
            payload,
            db,
            user,
            template_hours=template_hours,
            owner_lock_enabled=foreign_schedule_cell_lock_applies(db, user),
        )
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        tb = traceback.format_exc()
        print("ERROR in /api/overview/day:", tb, flush=True)
        logger.error("set_day failed: %s\n%s", exc, tb)
        raise HTTPException(
            status_code=500,
            detail=f"Serverfel: {type(exc).__name__}: {exc}",
        )


@router.post("/days/bulk")
def set_days_bulk(
    payload: OverviewBulkDayRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("overview", "edit")),
) -> dict:
    if not payload.days:
        return {"applied": [], "errors": [], "written": 0, "deleted": 0}
    if len(payload.days) > 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="För många dagar (max 100)")

    person_ids = {item.person_id for item in payload.days}
    activity_ids = {item.activity_id for item in payload.days if item.activity_id is not None}
    weekdays = {item.weekday for item in payload.days}

    existing_person_ids = set(
        db.execute(select(Person.id).where(Person.id.in_(person_ids))).scalars().all()
    )
    missing_person_ids = sorted(person_ids - existing_person_ids)
    if missing_person_ids:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Person {missing_person_ids[0]} hittades inte",
        )

    if activity_ids:
        existing_activity_ids = set(
            db.execute(select(Activity.id).where(Activity.id.in_(activity_ids))).scalars().all()
        )
        missing_activity_ids = sorted(activity_ids - existing_activity_ids)
        if missing_activity_ids:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Aktivitet {missing_activity_ids[0]} hittades inte",
            )

    template_hours_map = get_template_hours_map(db, person_ids, weekdays)
    applied: list[dict] = []
    errors: list[dict] = []
    total_written = 0
    total_deleted = 0
    owner_lock_enabled = foreign_schedule_cell_lock_applies(db, user)

    try:
        for item in payload.days:
            template_hours = template_hours_map.get((item.person_id, item.weekday))
            if payload.atomic:
                result = _apply_day_impl(
                    item,
                    db,
                    user,
                    template_hours=template_hours,
                    owner_lock_enabled=owner_lock_enabled,
                )
                applied.append({
                    **result["cell"],
                    "before_hours": result["before_hours"],
                    "after_hours": result["after_hours"],
                })
                total_written += result["written"]
                total_deleted += result["deleted"]
                continue

            try:
                with db.begin_nested():
                    result = _apply_day_impl(
                        item,
                        db,
                        user,
                        template_hours=template_hours,
                        owner_lock_enabled=owner_lock_enabled,
                    )
                applied.append({
                    **result["cell"],
                    "before_hours": result["before_hours"],
                    "after_hours": result["after_hours"],
                })
                total_written += result["written"]
                total_deleted += result["deleted"]
            except HTTPException as exc:
                errors.append(_bulk_error_payload(item, exc))

        db.commit()
        return {
            "applied": applied,
            "errors": errors,
            "written": total_written,
            "deleted": total_deleted,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        tb = traceback.format_exc()
        print("ERROR in /api/overview/days/bulk:", tb, flush=True)
        logger.error("set_days_bulk failed: %s\n%s", exc, tb)
        raise HTTPException(
            status_code=500,
            detail=f"Serverfel: {type(exc).__name__}: {exc}",
        )

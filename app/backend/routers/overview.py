import logging
import traceback
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

logger = logging.getLogger("overview")

from ..audit import log as audit_log
from ..deps import get_current_user, get_db
from ..models import Activity, Person, ScheduleCell, User
from ..schemas import PersonOut
from ..template_service import get_template_hours

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
    date: str            # YYYY-MM-DD
    year: int            # ISO-year
    week: int            # ISO-week
    weekday: int         # 1=mån..7=sön


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


@router.get("", response_model=OverviewOut)
def get_overview(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    area_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
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

    matrix: list[OverviewCell] = []
    for p in persons:
        for wd in range(1, 8):
            template = get_template_hours(db, p.id, wd)
            template_hours = 0 if template is None else len(template)
            minutes_by_activity = _effective_minutes_by_activity(
                explicit_minutes=explicit_minutes.get((p.id, wd), {}),
                covered_minutes=covered_minutes.get((p.id, wd), {}),
                template=template,
                home_activity_id=p.home_activity_id,
            )
            dominant, mixed, total_minutes = _summarize_day(minutes_by_activity)

            matrix.append(OverviewCell(
                person_id=p.id, weekday=wd,
                activity_id=dominant, mixed=mixed,
                hours_total=_hours_from_minutes(total_minutes), template_hours=template_hours,
            ))

    return OverviewOut(
        year=year, week=week,
        persons=[PersonOut.model_validate(p) for p in persons],
        matrix=matrix,
    )


@router.get("/month", response_model=MonthOverviewOut)
def get_month_overview(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    area_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MonthOverviewOut:
    # Generera alla dagar i månaden
    first = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    days_list: list[MonthDay] = []
    d = first
    while d < next_month:
        iso_y, iso_w, iso_wd = d.isocalendar()
        days_list.append(MonthDay(date=d.isoformat(), year=iso_y, week=iso_w, weekday=iso_wd))
        d += timedelta(days=1)

    # Hämta personer
    persons_q = select(Person).where(Person.is_active.is_(True))
    if area_id is not None:
        persons_q = persons_q.where(Person.home_area_id == area_id)
    persons_q = persons_q.order_by(Person.sort_order, Person.name)
    persons = db.execute(persons_q).scalars().all()
    person_ids = [p.id for p in persons]

    # Hämta alla cells för ALLA dagar i månaden i ETT query
    explicit_minutes: dict[tuple[int, int, int, int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    covered_minutes: dict[tuple[int, int, int, int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    if person_ids and days_list:
        ywd_tuples = list({(d.year, d.week, d.weekday) for d in days_list})
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
        for pid, y, w, wd, hour, aid, empty_override, cnt in rows:
            if aid is not None:
                explicit_minutes[(pid, y, w, wd)][aid] += int(cnt)
            if aid is not None or empty_override:
                covered_minutes[(pid, y, w, wd)][hour] = min(
                    60,
                    covered_minutes[(pid, y, w, wd)].get(hour, 0) + int(cnt),
                )

    matrix: list[MonthOverviewCell] = []
    for p in persons:
        for d_info in days_list:
            template = get_template_hours(db, p.id, d_info.weekday)
            template_hours = 0 if template is None else len(template)
            minutes_by_activity = _effective_minutes_by_activity(
                explicit_minutes=explicit_minutes.get((p.id, d_info.year, d_info.week, d_info.weekday), {}),
                covered_minutes=covered_minutes.get((p.id, d_info.year, d_info.week, d_info.weekday), {}),
                template=template,
                home_activity_id=p.home_activity_id,
            )
            dominant, mixed, total_minutes = _summarize_day(minutes_by_activity)
            matrix.append(MonthOverviewCell(
                person_id=p.id, date=d_info.date,
                activity_id=dominant, mixed=mixed,
                hours_total=_hours_from_minutes(total_minutes), template_hours=template_hours,
            ))

    return MonthOverviewOut(
        year=year, month=month, days=days_list,
        persons=[PersonOut.model_validate(p) for p in persons],
        matrix=matrix,
    )


@router.post("/day")
def set_day(
    payload: OverviewDayRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return _set_day_impl(payload, db, user)
    except HTTPException:
        raise
    except Exception as exc:
        tb = traceback.format_exc()
        print("ERROR in /api/overview/day:", tb, flush=True)
        logger.error("set_day failed: %s\n%s", exc, tb)
        raise HTTPException(
            status_code=500,
            detail=f"Serverfel: {type(exc).__name__}: {exc}",
        )


def _set_day_impl(payload: "OverviewDayRequest", db: Session, user: User) -> dict:
    if not db.get(Person, payload.person_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person hittades inte")
    if payload.activity_id is not None and not db.get(Activity, payload.activity_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Aktivitet hittades inte")

    template = get_template_hours(db, payload.person_id, payload.weekday)
    if template is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Personen är markerad som ledig denna dag. Ändra schemat först eller bemanna i bemanningsvyn.",
        )
    if not template:
        return {"written": 0, "deleted": 0}

    # Hämta befintliga cells INOM template-fönstret
    template_list = sorted(template)
    existing = db.execute(
        select(ScheduleCell).where(
            ScheduleCell.year == payload.year,
            ScheduleCell.week == payload.week,
            ScheduleCell.weekday == payload.weekday,
            ScheduleCell.person_id == payload.person_id,
            ScheduleCell.hour.in_(template_list),
        )
    ).scalars().all()
    existing_by_hour: dict[int, list[ScheduleCell]] = defaultdict(list)
    for cell in existing:
        existing_by_hour[cell.hour].append(cell)

    written = 0
    deleted = 0

    for hour in sorted(template):
        cells_for_hour = sorted(existing_by_hour.get(hour, []), key=lambda cell: (cell.minute_start, cell.minute_end))
        if payload.activity_id is None:
            if (
                len(cells_for_hour) == 1
                and cells_for_hour[0].minute_start == 0
                and cells_for_hour[0].minute_end == 60
            ):
                cell = cells_for_hour[0]
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
                db.flush()
                audit_log(
                    db, entity_type="schedule_cell", entity_id=cell.id,
                    action="overview_day_clear", old_value=old,
                    new_value={
                        "minute_start": cell.minute_start,
                        "minute_end": cell.minute_end,
                        "activity_id": cell.activity_id,
                        "empty_override": cell.empty_override,
                        "version": cell.version,
                    }, user_id=user.id,
                )
                written += 1
                continue

            for cell in cells_for_hour:
                audit_log(
                    db, entity_type="schedule_cell", entity_id=cell.id,
                    action="overview_day_clear",
                    old_value={
                        "minute_start": cell.minute_start,
                        "minute_end": cell.minute_end,
                        "activity_id": cell.activity_id,
                        "empty_override": cell.empty_override,
                        "version": cell.version,
                    },
                    new_value=None, user_id=user.id,
                )
                db.delete(cell)
                deleted += 1

            cell = ScheduleCell(
                year=payload.year, week=payload.week, weekday=payload.weekday,
                hour=hour, minute_start=0, minute_end=60, person_id=payload.person_id,
                activity_id=None, empty_override=True, version=1, updated_by=user.id,
            )
            db.add(cell)
            db.flush()
            audit_log(
                db, entity_type="schedule_cell", entity_id=cell.id,
                action="overview_day_clear", old_value=None,
                new_value={
                    "minute_start": cell.minute_start,
                    "minute_end": cell.minute_end,
                    "activity_id": cell.activity_id,
                    "empty_override": cell.empty_override,
                    "version": 1,
                }, user_id=user.id,
            )
            written += 1
            continue

        if (
            len(cells_for_hour) == 1
            and cells_for_hour[0].minute_start == 0
            and cells_for_hour[0].minute_end == 60
        ):
            cell = cells_for_hour[0]
            if cell.activity_id != payload.activity_id:
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
                db.flush()
                audit_log(
                    db, entity_type="schedule_cell", entity_id=cell.id,
                    action="overview_day_assign", old_value=old,
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
                    db, entity_type="schedule_cell", entity_id=cell.id,
                    action="overview_day_clear",
                    old_value={
                        "minute_start": cell.minute_start,
                        "minute_end": cell.minute_end,
                        "activity_id": cell.activity_id,
                        "empty_override": cell.empty_override,
                        "version": cell.version,
                    },
                    new_value=None, user_id=user.id,
                )
                db.delete(cell)
                deleted += 1

        if not cells_for_hour or len(cells_for_hour) != 1 or cells_for_hour[0].minute_end != 60:
            cell = ScheduleCell(
                year=payload.year, week=payload.week, weekday=payload.weekday,
                hour=hour, minute_start=0, minute_end=60, person_id=payload.person_id,
                activity_id=payload.activity_id, empty_override=False, version=1, updated_by=user.id,
            )
            db.add(cell)
            db.flush()
            audit_log(
                db, entity_type="schedule_cell", entity_id=cell.id,
                action="overview_day_assign", old_value=None,
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

    db.commit()
    return {"written": written, "deleted": deleted}

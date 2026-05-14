"""Public read-only-endpoints för Excel/extern integration.

Alla skyddas med EXCEL_API_TOKEN (env-variabel) via ?token=...

Endpoints:
  /api/public/hours          – timmar för EN aktivitet, EN dag
  /api/public/hours/week     – timmar för EN aktivitet, HELA veckan
  /api/public/persons        – heltidsekvivalenter (timmar/8) för EN aktivitet, EN dag
  /api/public/persons/week   – heltidsekvivalenter, HELA veckan
  /api/public/summary        – CSV med alla aktiviteter, EN dag
  /api/public/summary/week   – CSV med alla aktiviteter, HELA veckan
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import get_db
from ..models import Activity, Person, ScheduleCell
from ..template_service import get_template_hours

router = APIRouter(prefix="/api/public", tags=["public"])

HOURS_PER_FTE = 8


def _verify_token(token: str) -> None:
    expected = (settings.EXCEL_API_TOKEN or "").strip()
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Token not configured")
    if not token or token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _format_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}"


def _calc_activity_hours(
    db: Session,
    year: int,
    week: int,
    weekdays: list[int],
    activity_id: int | None = None,
) -> dict[int, float]:
    """Returnerar {activity_id: hours} aggregerat över givna weekdays.

    Inkluderar både explicit ifyllda cells OCH implicit standardschema
    (personer med home_activity_id som är schemalagda men saknar explicit cell).
    """
    if not weekdays:
        return {}

    # 1. Explicit minuter per aktivitet
    explicit_q = select(
        ScheduleCell.activity_id,
        func.coalesce(func.sum(ScheduleCell.minute_end - ScheduleCell.minute_start), 0),
    ).where(
        ScheduleCell.year == year,
        ScheduleCell.week == week,
        ScheduleCell.weekday.in_(weekdays),
        ScheduleCell.activity_id.is_not(None),
    ).group_by(ScheduleCell.activity_id)
    if activity_id is not None:
        explicit_q = explicit_q.where(ScheduleCell.activity_id == activity_id)

    minutes_by_activity: dict[int, int] = {}
    for aid, minutes in db.execute(explicit_q).all():
        minutes_by_activity[aid] = (minutes_by_activity.get(aid, 0) + (minutes or 0))

    # 2. Implicit standard per (person, weekday) - täcker timmar utan explicit segment
    persons_q = select(Person).where(
        Person.is_active.is_(True),
        Person.home_activity_id.is_not(None),
    )
    if activity_id is not None:
        persons_q = persons_q.where(Person.home_activity_id == activity_id)

    for person in db.execute(persons_q).scalars().all():
        for weekday in weekdays:
            template = get_template_hours(db, person.id, weekday)
            if not template:
                continue
            for hour in template:
                covered = db.execute(
                    select(
                        func.coalesce(func.sum(ScheduleCell.minute_end - ScheduleCell.minute_start), 0)
                    ).where(
                        ScheduleCell.year == year,
                        ScheduleCell.week == week,
                        ScheduleCell.weekday == weekday,
                        ScheduleCell.person_id == person.id,
                        ScheduleCell.hour == hour,
                    )
                ).scalar() or 0
                gap = max(0, 60 - covered)
                if gap > 0:
                    aid = person.home_activity_id
                    minutes_by_activity[aid] = minutes_by_activity.get(aid, 0) + gap

    return {aid: m / 60.0 for aid, m in minutes_by_activity.items()}


def _resolve_activity(db: Session, code: str) -> Activity:
    act = db.query(Activity).filter_by(code=code).one_or_none()
    if not act:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Aktivitet '{code}' hittades inte")
    return act


# ---------- Hours ----------

@router.get("/hours", response_class=PlainTextResponse)
def get_hours_day(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    activity: str = Query(..., description="Aktivitetskod, t.ex. GG_PLOCK"),
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> str:
    _verify_token(token)
    act = db.query(Activity).filter_by(code=activity).one_or_none()
    if not act:
        return "0"
    result = _calc_activity_hours(db, year, week, [weekday], activity_id=act.id)
    return _format_number(result.get(act.id, 0.0))


@router.get("/hours/week", response_class=PlainTextResponse)
def get_hours_week(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    activity: str = Query(...),
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> str:
    _verify_token(token)
    act = db.query(Activity).filter_by(code=activity).one_or_none()
    if not act:
        return "0"
    result = _calc_activity_hours(db, year, week, [1, 2, 3, 4, 5, 6, 7], activity_id=act.id)
    return _format_number(result.get(act.id, 0.0))


# ---------- Persons (heltidsekvivalenter = timmar/8) ----------

@router.get("/persons", response_class=PlainTextResponse)
def get_persons_day(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    activity: str = Query(...),
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> str:
    _verify_token(token)
    act = db.query(Activity).filter_by(code=activity).one_or_none()
    if not act:
        return "0"
    result = _calc_activity_hours(db, year, week, [weekday], activity_id=act.id)
    return _format_number(result.get(act.id, 0.0) / HOURS_PER_FTE)


@router.get("/persons/week", response_class=PlainTextResponse)
def get_persons_week(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    activity: str = Query(...),
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> str:
    _verify_token(token)
    act = db.query(Activity).filter_by(code=activity).one_or_none()
    if not act:
        return "0"
    result = _calc_activity_hours(db, year, week, [1, 2, 3, 4, 5, 6, 7], activity_id=act.id)
    return _format_number(result.get(act.id, 0.0) / HOURS_PER_FTE)


# ---------- Summary (CSV, alla aktiviteter) ----------

def _build_summary_csv(db: Session, hours_by_activity: dict[int, float]) -> str:
    if not hours_by_activity:
        return "activity_code,activity_label,hours,persons\n"
    activities = {a.id: a for a in db.query(Activity).all()}
    rows = ["activity_code,activity_label,hours,persons"]
    sorted_items = sorted(
        hours_by_activity.items(),
        key=lambda kv: (activities.get(kv[0]).sort_order if activities.get(kv[0]) else 999, kv[0]),
    )
    for aid, hours in sorted_items:
        act = activities.get(aid)
        if not act:
            continue
        persons = hours / HOURS_PER_FTE
        rows.append(f"{act.code},\"{act.label}\",{_format_number(hours)},{_format_number(persons)}")
    return "\n".join(rows) + "\n"


@router.get("/summary", response_class=PlainTextResponse)
def get_summary_day(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> str:
    _verify_token(token)
    result = _calc_activity_hours(db, year, week, [weekday])
    return _build_summary_csv(db, result)


@router.get("/summary/week", response_class=PlainTextResponse)
def get_summary_week(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> str:
    _verify_token(token)
    result = _calc_activity_hours(db, year, week, [1, 2, 3, 4, 5, 6, 7])
    return _build_summary_csv(db, result)

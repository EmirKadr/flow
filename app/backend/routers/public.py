"""Public read-only-endpoints för Excel/extern integration.

Alla skyddas med EXCEL_API_TOKEN (env-variabel) via ?token=...

Endpoints:
  /api/public/hours          – timmar för EN aktivitet, EN dag
  /api/public/hours/week     – timmar för EN aktivitet, HELA veckan
  /api/public/persons        – heltidsekvivalenter (timmar/8) för EN aktivitet, EN dag
  /api/public/persons/week   – heltidsekvivalenter, HELA veckan
  /api/public/summary        – CSV med alla aktiviteter, EN dag
  /api/public/summary/week   – CSV med alla aktiviteter, HELA veckan

Dag-endpoints kan anropas med date=YYYY-MM-DD, gamla year/week/weekday,
eller utan datumparametrar för dagens datum i svensk tid.
Vecko-endpoints kan anropas med date=YYYY-MM-DD, gamla year/week,
eller utan datumparametrar för aktuell ISO-vecka i svensk tid.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..business_scope import DEFAULT_BUSINESS_CODE, get_business_by_input
from ..config import settings
from ..deps import get_db
from ..models import Activity, Person, ScheduleCell
from ..template_service import get_template_hours

router = APIRouter(prefix="/api/public", tags=["public"])

HOURS_PER_FTE = 8
LOCAL_TIMEZONE = ZoneInfo("Europe/Stockholm")


def _verify_token(token: str) -> None:
    expected = (settings.EXCEL_API_TOKEN or "").strip()
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Token not configured")
    if not token or token.strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _today_local() -> date:
    return datetime.now(LOCAL_TIMEZONE).date()


def _iso_year_week_weekday(value: date) -> tuple[int, int, int]:
    iso = value.isocalendar()
    return iso.year, iso.week, iso.weekday


def _resolve_day_params(
    day: date | None,
    year: int | None,
    week: int | None,
    weekday: int | None,
) -> tuple[int, int, int]:
    legacy_values = (year, week, weekday)
    has_legacy = any(value is not None for value in legacy_values)

    if day is not None:
        if has_legacy:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ange antingen date eller year/week/weekday, inte båda.",
            )
        return _iso_year_week_weekday(day)

    if has_legacy:
        if not all(value is not None for value in legacy_values):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ange year, week och weekday tillsammans.",
            )
        return year, week, weekday

    return _iso_year_week_weekday(_today_local())


def _resolve_week_params(
    day: date | None,
    year: int | None,
    week: int | None,
) -> tuple[int, int]:
    has_legacy = year is not None or week is not None

    if day is not None:
        if has_legacy:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ange antingen date eller year/week, inte båda.",
            )
        iso_year, iso_week, _ = _iso_year_week_weekday(day)
        return iso_year, iso_week

    if has_legacy:
        if year is None or week is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ange year och week tillsammans.",
            )
        return year, week

    iso_year, iso_week, _ = _iso_year_week_weekday(_today_local())
    return iso_year, iso_week


def _format_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}"


def _resolve_public_business_id(db: Session, business: str | int | float | None) -> int:
    resolved = get_business_by_input(db, business or DEFAULT_BUSINESS_CODE)
    if resolved is None or not resolved.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Business not found")
    return resolved.id


def _calc_activity_hours(
    db: Session,
    year: int,
    week: int,
    weekdays: list[int],
    business_id: int,
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
        ScheduleCell.activity_id.in_(select(Activity.id).where(Activity.business_id == business_id)),
    ).group_by(ScheduleCell.activity_id)
    if activity_id is not None:
        explicit_q = explicit_q.where(ScheduleCell.activity_id == activity_id)

    minutes_by_activity: dict[int, int] = {}
    for aid, minutes in db.execute(explicit_q).all():
        minutes_by_activity[aid] = (minutes_by_activity.get(aid, 0) + (minutes or 0))

    # 2. Implicit standard per (person, weekday) - täcker timmar utan explicit segment
    persons_q = select(Person).where(
        Person.is_active.is_(True),
        Person.business_id == business_id,
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


def _resolve_activity(db: Session, code: str, business_id: int) -> Activity:
    act = db.query(Activity).filter_by(business_id=business_id, code=code).one_or_none()
    if not act:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Aktivitet '{code}' hittades inte")
    return act


# ---------- Hours ----------

@router.get("/hours", response_class=PlainTextResponse)
def get_hours_day(
    day: date | None = Query(None, alias="date", description="Datum i format YYYY-MM-DD"),
    year: int | None = Query(None, ge=2000, le=2100),
    week: int | None = Query(None, ge=1, le=53),
    weekday: int | None = Query(None, ge=1, le=7),
    activity: str = Query(..., description="Aktivitetskod, t.ex. GG_PLOCK"),
    business: str | None = Query(None),
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> str:
    _verify_token(token)
    business_id = _resolve_public_business_id(db, business)
    resolved_year, resolved_week, resolved_weekday = _resolve_day_params(day, year, week, weekday)
    act = db.query(Activity).filter_by(business_id=business_id, code=activity).one_or_none()
    if not act:
        return "0"
    result = _calc_activity_hours(db, resolved_year, resolved_week, [resolved_weekday], business_id, activity_id=act.id)
    return _format_number(result.get(act.id, 0.0))


@router.get("/hours/week", response_class=PlainTextResponse)
def get_hours_week(
    day: date | None = Query(None, alias="date", description="Datum i veckan, format YYYY-MM-DD"),
    year: int | None = Query(None, ge=2000, le=2100),
    week: int | None = Query(None, ge=1, le=53),
    activity: str = Query(...),
    business: str | None = Query(None),
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> str:
    _verify_token(token)
    business_id = _resolve_public_business_id(db, business)
    resolved_year, resolved_week = _resolve_week_params(day, year, week)
    act = db.query(Activity).filter_by(business_id=business_id, code=activity).one_or_none()
    if not act:
        return "0"
    result = _calc_activity_hours(db, resolved_year, resolved_week, [1, 2, 3, 4, 5, 6, 7], business_id, activity_id=act.id)
    return _format_number(result.get(act.id, 0.0))


# ---------- Persons (heltidsekvivalenter = timmar/8) ----------

@router.get("/persons", response_class=PlainTextResponse)
def get_persons_day(
    day: date | None = Query(None, alias="date", description="Datum i format YYYY-MM-DD"),
    year: int | None = Query(None, ge=2000, le=2100),
    week: int | None = Query(None, ge=1, le=53),
    weekday: int | None = Query(None, ge=1, le=7),
    activity: str = Query(...),
    business: str | None = Query(None),
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> str:
    _verify_token(token)
    business_id = _resolve_public_business_id(db, business)
    resolved_year, resolved_week, resolved_weekday = _resolve_day_params(day, year, week, weekday)
    act = db.query(Activity).filter_by(business_id=business_id, code=activity).one_or_none()
    if not act:
        return "0"
    result = _calc_activity_hours(db, resolved_year, resolved_week, [resolved_weekday], business_id, activity_id=act.id)
    return _format_number(result.get(act.id, 0.0) / HOURS_PER_FTE)


@router.get("/persons/week", response_class=PlainTextResponse)
def get_persons_week(
    day: date | None = Query(None, alias="date", description="Datum i veckan, format YYYY-MM-DD"),
    year: int | None = Query(None, ge=2000, le=2100),
    week: int | None = Query(None, ge=1, le=53),
    activity: str = Query(...),
    business: str | None = Query(None),
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> str:
    _verify_token(token)
    business_id = _resolve_public_business_id(db, business)
    resolved_year, resolved_week = _resolve_week_params(day, year, week)
    act = db.query(Activity).filter_by(business_id=business_id, code=activity).one_or_none()
    if not act:
        return "0"
    result = _calc_activity_hours(db, resolved_year, resolved_week, [1, 2, 3, 4, 5, 6, 7], business_id, activity_id=act.id)
    return _format_number(result.get(act.id, 0.0) / HOURS_PER_FTE)


# ---------- Summary (CSV, alla aktiviteter) ----------

def _build_summary_csv(db: Session, hours_by_activity: dict[int, float], business_id: int) -> str:
    if not hours_by_activity:
        return "activity_code,activity_label,hours,persons\n"
    activities = {a.id: a for a in db.query(Activity).filter(Activity.business_id == business_id).all()}
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
    day: date | None = Query(None, alias="date", description="Datum i format YYYY-MM-DD"),
    year: int | None = Query(None, ge=2000, le=2100),
    week: int | None = Query(None, ge=1, le=53),
    weekday: int | None = Query(None, ge=1, le=7),
    business: str | None = Query(None),
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> str:
    _verify_token(token)
    business_id = _resolve_public_business_id(db, business)
    resolved_year, resolved_week, resolved_weekday = _resolve_day_params(day, year, week, weekday)
    result = _calc_activity_hours(db, resolved_year, resolved_week, [resolved_weekday], business_id)
    return _build_summary_csv(db, result, business_id)


@router.get("/summary/week", response_class=PlainTextResponse)
def get_summary_week(
    day: date | None = Query(None, alias="date", description="Datum i veckan, format YYYY-MM-DD"),
    year: int | None = Query(None, ge=2000, le=2100),
    week: int | None = Query(None, ge=1, le=53),
    business: str | None = Query(None),
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> str:
    _verify_token(token)
    business_id = _resolve_public_business_id(db, business)
    resolved_year, resolved_week = _resolve_week_params(day, year, week)
    result = _calc_activity_hours(db, resolved_year, resolved_week, [1, 2, 3, 4, 5, 6, 7], business_id)
    return _build_summary_csv(db, result, business_id)

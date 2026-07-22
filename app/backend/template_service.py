"""Hjälpfunktioner för person_schedule_templates."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Person, PersonScheduleTemplate, ScheduleFreezeState

DEFAULT_START = 7
LOCAL_TIMEZONE = ZoneInfo("Europe/Stockholm")
DEFAULT_END = 16          # exklusiv → timslots 7..15
LUNCH_OFFSET = 5          # lunchen sätts 5 timmar in i passet (start_hour + 5)


_FREEZE_HORIZON_CACHE_KEY = "schedule_freeze_horizon"


def get_schedule_freeze_horizon(db: Session) -> date | None:
    """Senaste materialiserade datum, eller None om frysning inte initierats.

    Datum <= horisonten är historik: implicita malltimmar är redan skrivna som
    explicita celler (is_template_fill) och mallen får inte appliceras vid
    läsning, annars skulle senare malländringar ändra förfluten tid.

    Cachas per session (db.info) så upprepade uppslag i samma request inte
    kostar en SQL-fråga var — särskilt viktigt innan frysraden finns, då
    db.get inte kan träffa identity map.
    """
    info = getattr(db, "info", None)
    if info is not None and _FREEZE_HORIZON_CACHE_KEY in info:
        return info[_FREEZE_HORIZON_CACHE_KEY]
    row = db.get(ScheduleFreezeState, 1)
    horizon = row.frozen_until if row is not None else None
    if info is not None:
        info[_FREEZE_HORIZON_CACHE_KEY] = horizon
    return horizon


def set_cached_freeze_horizon(db: Session, horizon: date | None) -> None:
    """Uppdatera sessionscachen när frysgränsen flyttas i samma session."""
    info = getattr(db, "info", None)
    if info is not None:
        info[_FREEZE_HORIZON_CACHE_KEY] = horizon


def is_date_frozen(db: Session, target_date: date) -> bool:
    horizon = get_schedule_freeze_horizon(db)
    return horizon is not None and target_date <= horizon


def _hours_with_lunch_removed(start: int, end: int) -> set[int]:
    """Returnera arbetstimmar inom [start, end) med lunchtimmen borttagen.

    Lunch = en timme, placerad 5 timmar in i passet. Om passet är kortare
    än så att lunchen inte ryms inom fönstret, ingen lunch dras av.
    """
    hours = set(range(start, end))
    lunch_hour = start + LUNCH_OFFSET
    hours.discard(lunch_hour)
    return hours


def _default_hours_for_weekday(weekday: int) -> set[int] | None:
    if weekday <= 5:
        return _hours_with_lunch_removed(DEFAULT_START, DEFAULT_END)
    return None


def _created_local_date(created_at: datetime | date | None) -> date | None:
    if created_at is None:
        return None
    if isinstance(created_at, datetime):
        if created_at.tzinfo is not None:
            return created_at.astimezone(LOCAL_TIMEZONE).date()
        return created_at.date()
    return created_at


def _apply_person_start_date(
    hours: set[int] | None,
    *,
    created_at: datetime | date | None,
    target_date: date | None,
) -> set[int] | None:
    if hours is None or target_date is None:
        return hours
    created_date = _created_local_date(created_at)
    if created_date is not None and target_date < created_date:
        return None
    return hours


def _hours_from_template_rows(rows: list[PersonScheduleTemplate], weekday: int) -> set[int] | None:
    row = next((item for item in rows if int(item.weekday) == int(weekday)), None)
    if row is None:
        return None if rows else _default_hours_for_weekday(weekday)
    if row.is_off:
        return None
    return _hours_with_lunch_removed(row.start_hour, row.end_hour)


def get_template_hours(
    db: Session,
    person_id: int,
    weekday: int,
    *,
    target_date: date | None = None,
) -> set[int] | None:
    """Returnera set av timmar (6..23) som personen ska bemannas på den dagen.

    None = ledig.
    Om personen saknar egen mall: vardagar default 07..15 minus lunch, helg ledig.
    Om personen har en egen mall men saknar rad för dagen: ledig.
    """
    if target_date is not None and is_date_frozen(db, target_date):
        return None

    person = db.get(Person, person_id)
    if person is not None and not person.has_fixed_schedule:
        return None

    rows = db.execute(
        select(PersonScheduleTemplate).where(
            PersonScheduleTemplate.person_id == person_id
        )
    ).scalars().all()
    hours = _hours_from_template_rows(rows, weekday)
    return _apply_person_start_date(
        hours,
        created_at=person.created_at if person is not None else None,
        target_date=target_date,
    )


def get_template_hours_for_date(db: Session, person_id: int, target_date: date) -> set[int] | None:
    return get_template_hours(db, person_id, target_date.isoweekday(), target_date=target_date)


def get_template_hours_map(
    db: Session,
    person_ids: Iterable[int],
    weekdays: Iterable[int],
) -> dict[tuple[int, int], set[int] | None]:
    """Batchhämta schema för flera personer/veckodagar.

    Nyckeln i resultatet är ``(person_id, weekday)``.
    Om en rad saknas används samma defaultbeteende som i ``get_template_hours``.

    OBS: datumlös och därför utan både frysgräns och ``created_at``-vakt. Får
    inte användas i läsvägar som visar ett konkret datum — då skulle
    veckomallen rita om fryst historik igen. Använd
    ``get_template_hours_map_for_dates``.
    """
    unique_person_ids = sorted({int(person_id) for person_id in person_ids})
    unique_weekdays = sorted({int(weekday) for weekday in weekdays})
    if not unique_person_ids or not unique_weekdays:
        return {}

    rows = db.execute(
        select(PersonScheduleTemplate).where(
            PersonScheduleTemplate.person_id.in_(unique_person_ids),
        )
    ).scalars().all()
    fixed_schedule_by_person = {
        int(person_id): bool(has_fixed_schedule)
        for person_id, has_fixed_schedule in db.execute(
            select(Person.id, Person.has_fixed_schedule).where(Person.id.in_(unique_person_ids))
        ).all()
    }

    template_map: dict[tuple[int, int], set[int] | None] = {}
    for row in rows:
        if int(row.weekday) not in unique_weekdays:
            continue
        key = (int(row.person_id), int(row.weekday))
        if fixed_schedule_by_person.get(int(row.person_id), True) is False:
            template_map[key] = None
            continue
        if row.is_off:
            template_map[key] = None
        else:
            template_map[key] = _hours_with_lunch_removed(row.start_hour, row.end_hour)

    person_ids_with_custom_template = {int(row.person_id) for row in rows}
    for person_id in unique_person_ids:
        for weekday in unique_weekdays:
            if (person_id, weekday) in template_map:
                continue
            if fixed_schedule_by_person.get(person_id, True) is False:
                template_map[(person_id, weekday)] = None
                continue
            if person_id in person_ids_with_custom_template:
                template_map[(person_id, weekday)] = None
            else:
                template_map[(person_id, weekday)] = _default_hours_for_weekday(weekday)

    return template_map


def get_template_hours_map_for_dates(
    db: Session,
    person_ids: Iterable[int],
    target_dates: Iterable[date],
) -> dict[tuple[int, date], set[int] | None]:
    """Batchhamta schemamallar for faktiska datum.

    Nyckeln i resultatet ar ``(person_id, target_date)``. En person far inga
    implicita malltimmar for datum fore sitt skapandedatum.
    """
    unique_person_ids = sorted({int(person_id) for person_id in person_ids})
    unique_dates = sorted({target_date for target_date in target_dates})
    if not unique_person_ids or not unique_dates:
        return {}

    freeze_horizon = get_schedule_freeze_horizon(db)

    rows = db.execute(
        select(PersonScheduleTemplate).where(
            PersonScheduleTemplate.person_id.in_(unique_person_ids),
        )
    ).scalars().all()
    rows_by_person: dict[int, list[PersonScheduleTemplate]] = {}
    for row in rows:
        rows_by_person.setdefault(int(row.person_id), []).append(row)

    person_info_by_id = {
        int(person_id): (bool(has_fixed_schedule), created_at)
        for person_id, has_fixed_schedule, created_at in db.execute(
            select(Person.id, Person.has_fixed_schedule, Person.created_at).where(Person.id.in_(unique_person_ids))
        ).all()
    }

    template_map: dict[tuple[int, date], set[int] | None] = {}
    for person_id in unique_person_ids:
        has_fixed_schedule, created_at = person_info_by_id.get(person_id, (True, None))
        person_rows = rows_by_person.get(person_id, [])
        for target_date in unique_dates:
            if freeze_horizon is not None and target_date <= freeze_horizon:
                # Fryst datum: implicita timmar ligger redan som explicita
                # is_template_fill-celler; mallen får inte skriva om historik.
                template_map[(person_id, target_date)] = None
                continue
            if not has_fixed_schedule:
                template_map[(person_id, target_date)] = None
                continue
            hours = _hours_from_template_rows(person_rows, target_date.isoweekday())
            template_map[(person_id, target_date)] = _apply_person_start_date(
                hours,
                created_at=created_at,
                target_date=target_date,
            )

    return template_map


def get_all_default_days() -> list[dict]:
    """Standard-veckomall för en person som saknar sparade rader: vardagar 07-16, helg ledig."""
    days = []
    for wd in range(1, 8):
        if wd <= 5:
            days.append({"weekday": wd, "is_off": False, "start_hour": DEFAULT_START, "end_hour": DEFAULT_END})
        else:
            days.append({"weekday": wd, "is_off": True, "start_hour": None, "end_hour": None})
    return days

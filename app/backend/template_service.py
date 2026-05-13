"""Hjälpfunktioner för person_schedule_templates."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PersonScheduleTemplate

DEFAULT_START = 7
DEFAULT_END = 16          # exklusiv → timslots 7..15
LUNCH_OFFSET = 5          # lunchen sätts 5 timmar in i passet (start_hour + 5)


def _hours_with_lunch_removed(start: int, end: int) -> set[int]:
    """Returnera arbetstimmar inom [start, end) med lunchtimmen borttagen.

    Lunch = en timme, placerad 5 timmar in i passet. Om passet är kortare
    än så att lunchen inte ryms inom fönstret, ingen lunch dras av.
    """
    hours = set(range(start, end))
    lunch_hour = start + LUNCH_OFFSET
    hours.discard(lunch_hour)
    return hours


def get_template_hours(db: Session, person_id: int, weekday: int) -> set[int] | None:
    """Returnera set av timmar (6..23) som personen ska bemannas på den dagen.

    None = ledig.
    Om ingen rad finns: default 07..15 minus lunch på 12.
    """
    row = db.execute(
        select(PersonScheduleTemplate).where(
            PersonScheduleTemplate.person_id == person_id,
            PersonScheduleTemplate.weekday == weekday,
        )
    ).scalar_one_or_none()

    if row is None:
        return _hours_with_lunch_removed(DEFAULT_START, DEFAULT_END)
    if row.is_off:
        return None
    return _hours_with_lunch_removed(row.start_hour, row.end_hour)


def get_all_default_days() -> list[dict]:
    """Standard-veckomall för en person som saknar sparade rader: vardagar 07-16, helg ledig."""
    days = []
    for wd in range(1, 8):
        if wd <= 5:
            days.append({"weekday": wd, "is_off": False, "start_hour": DEFAULT_START, "end_hour": DEFAULT_END})
        else:
            days.append({"weekday": wd, "is_off": True, "start_hour": None, "end_hour": None})
    return days

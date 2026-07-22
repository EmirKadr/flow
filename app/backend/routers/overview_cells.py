from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ScheduleCell


def overview_day_key(payload: Any) -> tuple[int, int, int, int]:
    return (payload.person_id, payload.year, payload.week, payload.weekday)


def hours_from_minutes(total_minutes: int) -> float:
    return round(float(total_minutes) / 60.0, 2)


def template_hours_count(
    template_hours: set[int] | None,
    *,
    target_date: date,
    freeze_horizon: date | None,
    covered_hours: dict[int, int],
) -> int:
    """Antal schemalagda timmar for en cell i Oversikt.

    Pa en fryst dag returnerar mallen inget (historiken ar en logg), sa antalet
    harleds ur de materialiserade cellerna i stallet: timmar med aktivitet
    eller uttryckligt tom markering. Utan det skulle klienten se
    `template_hours == 0` och rita hela historiken som "Ledig".
    """
    if freeze_horizon is not None and target_date <= freeze_horizon:
        return len(covered_hours)
    return 0 if template_hours is None else len(template_hours)


def effective_minutes_by_activity(
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


def summarize_day(minutes_by_activity: dict[int, int]) -> tuple[int | None, bool, int]:
    total_minutes = sum(minutes_by_activity.values())
    if not minutes_by_activity:
        return None, False, total_minutes

    dominant = max(minutes_by_activity.items(), key=lambda item: item[1])[0]
    mixed = len(minutes_by_activity) > 1
    return dominant, mixed, total_minutes


def load_day_cells_by_hour(
    db: Session,
    payload: Any,
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


def load_bulk_day_cells_by_key(
    db: Session,
    days: list[Any],
    template_hours_by_key: dict[tuple[int, int, int, int], set[int] | None],
) -> dict[tuple[int, int, int, int], dict[int, list[ScheduleCell]]]:
    result: dict[tuple[int, int, int, int], dict[int, list[ScheduleCell]]] = {
        overview_day_key(item): {} for item in days
    }
    keys_by_date: dict[tuple[int, int, int], dict[str, set[int]]] = defaultdict(
        lambda: {"person_ids": set(), "hours": set()}
    )
    for item in days:
        key = overview_day_key(item)
        template_hours = template_hours_by_key.get(key)
        if not template_hours:
            continue
        group = keys_by_date[(item.year, item.week, item.weekday)]
        group["person_ids"].add(item.person_id)
        group["hours"].update(template_hours)

    for (year, week, weekday), values in keys_by_date.items():
        rows = db.execute(
            select(ScheduleCell).where(
                ScheduleCell.year == year,
                ScheduleCell.week == week,
                ScheduleCell.weekday == weekday,
                ScheduleCell.person_id.in_(values["person_ids"]),
                ScheduleCell.hour.in_(values["hours"]),
            )
        ).scalars().all()
        for cell in rows:
            key = (cell.person_id, cell.year, cell.week, cell.weekday)
            if key in result:
                result[key].setdefault(cell.hour, []).append(cell)

    return result

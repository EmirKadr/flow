from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ScheduleCell


def overview_day_key(payload: Any) -> tuple[int, int, int, int]:
    return (payload.person_id, payload.year, payload.week, payload.weekday)


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

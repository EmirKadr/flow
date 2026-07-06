"""Tools för schemat: dagsvyer, personscheman och bemanningssummeringar."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from ..models import Activity, Area, Person, ScheduleCell, User
from .common import (
    WEEKDAY_LABELS,
    ToolInputError,
    clamp_limit,
    iso_parts,
    parse_date_arg,
    person_row,
    resolve_area,
    resolve_business_id,
    resolve_person,
    truncation_note,
)
from .registry import register_tool

_BUSINESS_PARAM = {
    "type": "string",
    "description": "Verksamhet som id, kod eller namn. Utelämna för användarens egen verksamhet.",
}
_DATE_PARAM = {
    "type": "string",
    "description": "Datum (YYYY-MM-DD) eller idag/igår/imorgon. Default idag.",
}

MAX_SCHEDULE_PERSONS = 80


def _cells_for_day(db: Session, day: date, business_id: int | None):
    year, week, weekday = iso_parts(day)
    query = (
        db.query(ScheduleCell, Person)
        .join(Person, ScheduleCell.person_id == Person.id)
        .filter(ScheduleCell.year == year, ScheduleCell.week == week, ScheduleCell.weekday == weekday)
    )
    if business_id is not None:
        query = query.filter(Person.business_id == business_id)
    return query.order_by(Person.name, ScheduleCell.hour, ScheduleCell.minute_start).all()


def _activity_lookup(db: Session, cells) -> dict[int, Activity]:
    ids = {cell.activity_id for cell, _person in cells if cell.activity_id is not None}
    if not ids:
        return {}
    return {activity.id: activity for activity in db.query(Activity).filter(Activity.id.in_(ids)).all()}


def _segment(cell: ScheduleCell, activity: Activity | None, loan_area: Area | None) -> dict[str, Any]:
    segment: dict[str, Any] = {
        "hour": cell.hour,
        "minutes": f"{cell.minute_start:02d}-{cell.minute_end:02d}",
        "activity": activity.label if activity is not None else None,
        "activity_code": activity.code if activity is not None else None,
        "category": activity.category if activity is not None else None,
    }
    if loan_area is not None:
        segment["loan_area"] = loan_area.code
    if cell.remark:
        segment["remark"] = str(cell.remark)[:120]
    return segment


@register_tool(
    name="get_schedule_day",
    title="Dagens schema",
    description=(
        "Hämta schemalagda personer för ett datum med deras aktiviteter per timme. "
        "Filtrerbart per område (personens hemområde) och verksamhet."
    ),
    parameters={
        "type": "object",
        "properties": {
            "date": _DATE_PARAM,
            "area": {"type": "string", "description": "Område som id, kod eller namn."},
            "business": _BUSINESS_PARAM,
        },
    },
    view_id="schedule",
)
def get_schedule_day_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    day = parse_date_arg(args.get("date"), default_today=True)
    business_id = resolve_business_id(db, user, args)
    area = resolve_area(db, user, args, business_id=business_id)
    cells = _cells_for_day(db, day, business_id)
    if area is not None:
        cells = [(cell, person) for cell, person in cells if person.home_area_id == area.id]
    activities = _activity_lookup(db, cells)
    area_ids = {cell.loan_area_id for cell, _person in cells if cell.loan_area_id is not None}
    loan_areas = (
        {row.id: row for row in db.query(Area).filter(Area.id.in_(area_ids)).all()} if area_ids else {}
    )

    persons: dict[int, dict[str, Any]] = {}
    for cell, person in cells:
        entry = persons.setdefault(person.id, {**person_row(person), "segments": []})
        if cell.empty_override:
            continue
        entry["segments"].append(
            _segment(cell, activities.get(cell.activity_id or -1), loan_areas.get(cell.loan_area_id or -1))
        )
    rows = list(persons.values())[:MAX_SCHEDULE_PERSONS]
    year, week, weekday = iso_parts(day)
    result: dict[str, Any] = {
        "date": day.isoformat(),
        "iso_week": week,
        "weekday_label": WEEKDAY_LABELS[weekday],
        "persons": rows,
        "person_count": len(persons),
    }
    note = truncation_note(len(persons), len(rows))
    if note:
        result["note"] = note
    return result


@register_tool(
    name="get_person_schedule",
    title="Personens schema",
    description="Hämta en persons schema för en vecka (default veckan som innehåller angivet datum).",
    parameters={
        "type": "object",
        "properties": {
            "person": {"type": "string", "description": "Person som id eller namn."},
            "date": _DATE_PARAM,
            "business": _BUSINESS_PARAM,
        },
        "required": ["person"],
    },
    view_id="schedule",
)
def get_person_schedule_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    person = resolve_person(db, user, args, business_id=business_id)
    day = parse_date_arg(args.get("date"), default_today=True)
    year, week, _weekday = iso_parts(day)
    cells = (
        db.query(ScheduleCell)
        .filter(
            ScheduleCell.person_id == person.id,
            ScheduleCell.year == year,
            ScheduleCell.week == week,
        )
        .order_by(ScheduleCell.weekday, ScheduleCell.hour, ScheduleCell.minute_start)
        .all()
    )
    activity_ids = {cell.activity_id for cell in cells if cell.activity_id is not None}
    activities = (
        {row.id: row for row in db.query(Activity).filter(Activity.id.in_(activity_ids)).all()}
        if activity_ids
        else {}
    )
    days: dict[int, list[dict[str, Any]]] = {}
    for cell in cells:
        if cell.empty_override:
            continue
        days.setdefault(cell.weekday, []).append(_segment(cell, activities.get(cell.activity_id or -1), None))
    return {
        "person": person_row(person),
        "iso_year": year,
        "iso_week": week,
        "days": [
            {"weekday": weekday, "weekday_label": WEEKDAY_LABELS[weekday], "segments": segments}
            for weekday, segments in sorted(days.items())
        ],
    }


@register_tool(
    name="schedule_staffing_summary",
    title="Bemanningssummering",
    description=(
        "Summera bemanningen för ett datum: antal schemalagda personer per område och per timme. "
        "Bra för frågor som 'hur många jobbar på X idag?'."
    ),
    parameters={
        "type": "object",
        "properties": {"date": _DATE_PARAM, "business": _BUSINESS_PARAM},
    },
    view_id="schedule",
)
def schedule_staffing_summary_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    day = parse_date_arg(args.get("date"), default_today=True)
    business_id = resolve_business_id(db, user, args)
    cells = _cells_for_day(db, day, business_id)
    activities = _activity_lookup(db, cells)
    areas = {area.id: area for area in db.query(Area).all()}

    per_area: dict[str, set[int]] = {}
    per_hour: dict[int, set[int]] = {}
    absence_persons: set[int] = set()
    for cell, person in cells:
        if cell.empty_override:
            continue
        activity = activities.get(cell.activity_id or -1)
        if activity is not None and activity.category == "absence":
            absence_persons.add(person.id)
            continue
        area = areas.get(cell.loan_area_id) if cell.loan_area_id else areas.get(person.home_area_id or -1)
        area_key = area.code if area is not None else "okänt område"
        per_area.setdefault(area_key, set()).add(person.id)
        per_hour.setdefault(cell.hour, set()).add(person.id)

    year, week, weekday = iso_parts(day)
    return {
        "date": day.isoformat(),
        "iso_week": week,
        "weekday_label": WEEKDAY_LABELS[weekday],
        "persons_per_area": {key: len(ids) for key, ids in sorted(per_area.items())},
        "persons_per_hour": {str(hour): len(ids) for hour, ids in sorted(per_hour.items())},
        "persons_with_absence": len(absence_persons),
        "scheduled_persons_total": len({person.id for _cell, person in cells}),
    }


@register_tool(
    name="find_scheduled_persons",
    title="Vem gör aktiviteten",
    description="Lista vilka personer som är schemalagda på en viss aktivitet ett visst datum.",
    parameters={
        "type": "object",
        "properties": {
            "activity": {"type": "string", "description": "Aktivitet som id, kod eller label."},
            "date": _DATE_PARAM,
            "business": _BUSINESS_PARAM,
            "limit": {"type": "integer", "description": "Max antal personer (default 50, max 200)."},
        },
        "required": ["activity"],
    },
    view_id="schedule",
)
def find_scheduled_persons_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    requested = str(args.get("activity") or "").strip()
    if not requested:
        raise ToolInputError("Ange aktivitet som id, kod eller label.")
    day = parse_date_arg(args.get("date"), default_today=True)
    business_id = resolve_business_id(db, user, args)
    limit = clamp_limit(args.get("limit"))

    activity_query = db.query(Activity)
    if business_id is not None:
        activity_query = activity_query.filter(Activity.business_id == business_id)
    if requested.isdigit():
        activity = activity_query.filter(Activity.id == int(requested)).one_or_none()
    else:
        activity = (
            activity_query.filter(
                (func.upper(Activity.code) == requested.upper())
                | (func.upper(Activity.label) == requested.upper())
                | Activity.label.ilike(f"%{requested}%")
            )
            .order_by(Activity.sort_order, Activity.id)
            .first()
        )
    if activity is None:
        raise ToolInputError(f"Aktiviteten '{requested}' hittades inte.")

    cells = _cells_for_day(db, day, business_id)
    persons: dict[int, dict[str, Any]] = {}
    hours: dict[int, list[int]] = {}
    for cell, person in cells:
        if cell.empty_override or cell.activity_id != activity.id:
            continue
        persons.setdefault(person.id, person_row(person))
        hours.setdefault(person.id, []).append(cell.hour)
    rows = [
        {**row, "hours": sorted(set(hours.get(person_id, [])))}
        for person_id, row in list(persons.items())[:limit]
    ]
    return {
        "date": day.isoformat(),
        "activity": {"id": activity.id, "code": activity.code, "label": activity.label},
        "persons": rows,
        "person_count": len(persons),
    }


@register_tool(
    name="schedule_week_overview",
    title="Veckoöversikt",
    description="Antal schemalagda personer per dag för en vecka (default veckan som innehåller angivet datum).",
    parameters={
        "type": "object",
        "properties": {"date": _DATE_PARAM, "business": _BUSINESS_PARAM},
    },
    view_id="schedule",
)
def schedule_week_overview_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    day = parse_date_arg(args.get("date"), default_today=True)
    business_id = resolve_business_id(db, user, args)
    year, week, _weekday = iso_parts(day)
    query = (
        db.query(ScheduleCell.weekday, func.count(func.distinct(ScheduleCell.person_id)))
        .join(Person, ScheduleCell.person_id == Person.id)
        .filter(ScheduleCell.year == year, ScheduleCell.week == week, ~ScheduleCell.empty_override)
    )
    if business_id is not None:
        query = query.filter(Person.business_id == business_id)
    counts = dict(query.group_by(ScheduleCell.weekday).all())
    monday = date.fromisocalendar(year, week, 1)
    return {
        "iso_year": year,
        "iso_week": week,
        "days": [
            {
                "date": (monday + timedelta(days=weekday - 1)).isoformat(),
                "weekday_label": WEEKDAY_LABELS[weekday],
                "scheduled_persons": int(counts.get(weekday, 0)),
            }
            for weekday in range(1, 8)
        ],
    }


def _cell_minutes(cell: ScheduleCell) -> int:
    start = cell.minute_start if cell.minute_start is not None else 0
    end = cell.minute_end if cell.minute_end is not None else 60
    return max(0, int(end) - int(start))


def _week_pair_filter(pairs: set[tuple[int, int]]):
    """OR-kedja av (year, week)-par — aldrig tuple-IN, som inte fungerar i MSSQL."""
    return or_(*(and_(ScheduleCell.year == year, ScheduleCell.week == week) for year, week in sorted(pairs)))


@register_tool(
    name="schedule_coverage_gaps",
    title="Bemanningsluckor",
    description=(
        "Hitta timmar per område där bemanningen ett datum är under en miniminivå "
        "(default 1, dvs. helt obemannat), inom dagens faktiska bemanningsspann. "
        "Frånvaroaktiviteter räknas inte som bemanning."
    ),
    parameters={
        "type": "object",
        "properties": {
            "date": _DATE_PARAM,
            "business": _BUSINESS_PARAM,
            "min_persons": {"type": "integer", "description": "Miniminivå per timme (default 1)."},
        },
    },
    view_id="schedule",
)
def schedule_coverage_gaps_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    day = parse_date_arg(args.get("date"), default_today=True)
    business_id = resolve_business_id(db, user, args)
    try:
        min_persons = max(1, int(args.get("min_persons") or 1))
    except (TypeError, ValueError):
        min_persons = 1
    cells = _cells_for_day(db, day, business_id)
    activities = _activity_lookup(db, cells)
    areas = {area.id: area for area in db.query(Area).all()}

    staffing: dict[str, dict[int, set[int]]] = {}
    hours_in_use: set[int] = set()
    for cell, person in cells:
        if cell.empty_override:
            continue
        activity = activities.get(cell.activity_id or -1)
        if activity is None or activity.category == "absence":
            continue
        area = areas.get(cell.loan_area_id) if cell.loan_area_id else areas.get(person.home_area_id or -1)
        area_key = area.code if area is not None else "okänt område"
        staffing.setdefault(area_key, {}).setdefault(cell.hour, set()).add(person.id)
        hours_in_use.add(cell.hour)

    year, week, weekday = iso_parts(day)
    if not hours_in_use:
        return {
            "date": day.isoformat(),
            "weekday_label": WEEKDAY_LABELS[weekday],
            "note": "Ingen bemanning alls är schemalagd detta datum.",
            "areas": [],
        }
    span = range(min(hours_in_use), max(hours_in_use) + 1)
    return {
        "date": day.isoformat(),
        "weekday_label": WEEKDAY_LABELS[weekday],
        "hour_span": f"{span.start:02d}-{span.stop - 1:02d}",
        "min_persons": min_persons,
        "areas": [
            {
                "area": area_key,
                "gap_hours": [
                    hour for hour in span if len(hours.get(hour, set())) < min_persons
                ],
                "max_persons": max((len(ids) for ids in hours.values()), default=0),
            }
            for area_key, hours in sorted(staffing.items())
        ],
    }


@register_tool(
    name="person_utilization",
    title="Persons schemalagda tid",
    description=(
        "Summera en persons schemalagda tid per ISO-vecka i ett datumintervall "
        "(default 4 veckor bakåt): arbetstimmar, frånvarotimmar och schemalagda dagar."
    ),
    parameters={
        "type": "object",
        "properties": {
            "person": {"type": "string", "description": "Person som id eller namn."},
            "date_from": {"type": "string", "description": "Från-datum (YYYY-MM-DD)."},
            "date_to": _DATE_PARAM,
            "business": _BUSINESS_PARAM,
        },
        "required": ["person"],
    },
    view_id="schedule",
)
def person_utilization_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    person = resolve_person(db, user, args, business_id=business_id)
    date_to = parse_date_arg(args.get("date_to") or args.get("date"), default_today=True)
    raw_from = args.get("date_from")
    date_from = parse_date_arg(raw_from) if raw_from not in (None, "") else date_to - timedelta(days=27)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days + 1 > 92:
        raise ToolInputError("Välj högst 92 dagar åt gången.")

    wanted: set[tuple[int, int, int]] = set()
    pairs: set[tuple[int, int]] = set()
    for offset in range((date_to - date_from).days + 1):
        year, week, weekday = iso_parts(date_from + timedelta(days=offset))
        wanted.add((year, week, weekday))
        pairs.add((year, week))
    cells = (
        db.query(ScheduleCell)
        .filter(ScheduleCell.person_id == person.id, _week_pair_filter(pairs), ~ScheduleCell.empty_override)
        .all()
    )
    cells = [cell for cell in cells if (cell.year, cell.week, cell.weekday) in wanted]
    activities = {
        activity.id: activity
        for activity in db.query(Activity)
        .filter(Activity.id.in_({cell.activity_id for cell in cells if cell.activity_id is not None}))
        .all()
    }

    weeks: dict[str, dict[str, Any]] = {}
    for cell in cells:
        key = f"{cell.year}-V{cell.week:02d}"
        bucket = weeks.setdefault(key, {"work_minutes": 0, "absence_minutes": 0, "days": set()})
        activity = activities.get(cell.activity_id or -1)
        minutes = _cell_minutes(cell)
        if activity is not None and activity.category == "absence":
            bucket["absence_minutes"] += minutes
        else:
            bucket["work_minutes"] += minutes
        bucket["days"].add((cell.year, cell.week, cell.weekday))
    total_work = sum(bucket["work_minutes"] for bucket in weeks.values())
    total_absence = sum(bucket["absence_minutes"] for bucket in weeks.values())
    return {
        "person": person_row(person),
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "weeks": [
            {
                "week": week_key,
                "work_hours": round(bucket["work_minutes"] / 60, 1),
                "absence_hours": round(bucket["absence_minutes"] / 60, 1),
                "days_scheduled": len(bucket["days"]),
            }
            for week_key, bucket in sorted(weeks.items())
        ],
        "total_work_hours": round(total_work / 60, 1),
        "total_absence_hours": round(total_absence / 60, 1),
    }


@register_tool(
    name="schedule_period_compare",
    title="Jämför två veckor",
    description=(
        "Jämför bemanningen mellan två ISO-veckor (veckorna som innehåller de två datumen): "
        "timmar per aktivitet, totalsummor och antal schemalagda personer."
    ),
    parameters={
        "type": "object",
        "properties": {
            "date_a": {"type": "string", "description": "Datum i första veckan (YYYY-MM-DD)."},
            "date_b": {"type": "string", "description": "Datum i andra veckan (YYYY-MM-DD eller idag)."},
            "business": _BUSINESS_PARAM,
        },
        "required": ["date_a"],
    },
    view_id="schedule",
)
def schedule_period_compare_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    day_a = parse_date_arg(args.get("date_a"))
    day_b = parse_date_arg(args.get("date_b"), default_today=True)
    year_a, week_a, _ = iso_parts(day_a)
    year_b, week_b, _ = iso_parts(day_b)
    if (year_a, week_a) == (year_b, week_b):
        raise ToolInputError("Datumen ligger i samma ISO-vecka — välj två olika veckor.")

    def week_stats(year: int, week: int) -> tuple[dict[str, int], set[int], int]:
        query = (
            db.query(ScheduleCell, Person)
            .join(Person, ScheduleCell.person_id == Person.id)
            .filter(ScheduleCell.year == year, ScheduleCell.week == week, ~ScheduleCell.empty_override)
        )
        if business_id is not None:
            query = query.filter(Person.business_id == business_id)
        rows = query.all()
        activities = _activity_lookup(db, rows)
        minutes_per_activity: dict[str, int] = {}
        persons: set[int] = set()
        absence_minutes = 0
        for cell, person in rows:
            activity = activities.get(cell.activity_id or -1)
            minutes = _cell_minutes(cell)
            if activity is not None and activity.category == "absence":
                absence_minutes += minutes
                continue
            label = activity.label if activity is not None else "Utan aktivitet"
            minutes_per_activity[label] = minutes_per_activity.get(label, 0) + minutes
            persons.add(person.id)
        return minutes_per_activity, persons, absence_minutes

    minutes_a, persons_a, absence_a = week_stats(year_a, week_a)
    minutes_b, persons_b, absence_b = week_stats(year_b, week_b)
    labels = sorted(
        set(minutes_a) | set(minutes_b),
        key=lambda label: abs(minutes_b.get(label, 0) - minutes_a.get(label, 0)),
        reverse=True,
    )[:30]
    label_a = f"{year_a}-V{week_a:02d}"
    label_b = f"{year_b}-V{week_b:02d}"
    return {
        "week_a": label_a,
        "week_b": label_b,
        "activities": [
            {
                "activity": label,
                "hours_a": round(minutes_a.get(label, 0) / 60, 1),
                "hours_b": round(minutes_b.get(label, 0) / 60, 1),
                "diff_hours": round((minutes_b.get(label, 0) - minutes_a.get(label, 0)) / 60, 1),
            }
            for label in labels
        ],
        "totals": {
            "work_hours_a": round(sum(minutes_a.values()) / 60, 1),
            "work_hours_b": round(sum(minutes_b.values()) / 60, 1),
            "absence_hours_a": round(absence_a / 60, 1),
            "absence_hours_b": round(absence_b / 60, 1),
            "persons_a": len(persons_a),
            "persons_b": len(persons_b),
        },
    }

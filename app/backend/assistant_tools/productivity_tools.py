"""Tools för produktivitet: aggregat ur person_productivity_daily.

Endast aggregerade summeringar exponeras — inga råa händelserader.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Person, PersonProductivityDaily, User
from .common import (
    clamp_limit,
    parse_date_arg,
    person_row,
    resolve_business_id,
    resolve_person,
)
from .registry import register_tool

_BUSINESS_PARAM = {
    "type": "string",
    "description": "Verksamhet som id, kod eller namn. Utelämna för användarens egen verksamhet.",
}
_DATE_FROM_PARAM = {"type": "string", "description": "Från-datum (YYYY-MM-DD). Default samma som till-datum."}
_DATE_TO_PARAM = {"type": "string", "description": "Till-datum (YYYY-MM-DD) eller idag/igår. Default idag."}


def _date_range(args: dict[str, Any]):
    date_to = parse_date_arg(args.get("date_to") or args.get("date"), default_today=True)
    raw_from = args.get("date_from")
    date_from = parse_date_arg(raw_from) if raw_from not in (None, "") else date_to
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


def _scoped_query(db: Session, business_id: int | None):
    query = db.query(PersonProductivityDaily)
    if business_id is not None:
        query = query.filter(PersonProductivityDaily.business_id == business_id)
    return query


@register_tool(
    name="productivity_summary",
    title="Produktivitetssummering",
    description=(
        "Summera produktivitet (KPI-poäng, KPI-minuter, support- och frånvarominuter) "
        "per dag för ett datumintervall."
    ),
    parameters={
        "type": "object",
        "properties": {"date_from": _DATE_FROM_PARAM, "date_to": _DATE_TO_PARAM, "business": _BUSINESS_PARAM},
    },
    view_id="productivity",
)
def productivity_summary_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    date_from, date_to = _date_range(args)
    rows = (
        _scoped_query(db, business_id)
        .with_entities(
            PersonProductivityDaily.snapshot_date,
            func.count(func.distinct(PersonProductivityDaily.person_id)),
            func.sum(PersonProductivityDaily.kpi_points),
            func.sum(PersonProductivityDaily.kpi_minutes),
            func.sum(PersonProductivityDaily.support_minutes),
            func.sum(PersonProductivityDaily.absence_minutes),
        )
        .filter(
            PersonProductivityDaily.snapshot_date >= date_from,
            PersonProductivityDaily.snapshot_date <= date_to,
        )
        .group_by(PersonProductivityDaily.snapshot_date)
        .order_by(PersonProductivityDaily.snapshot_date)
        .all()
    )
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "days": [
            {
                "date": snapshot_date.isoformat(),
                "persons": int(persons or 0),
                "kpi_points": round(float(points or 0.0), 1),
                "kpi_minutes": int(kpi_minutes or 0),
                "support_minutes": int(support_minutes or 0),
                "absence_minutes": int(absence_minutes or 0),
            }
            for snapshot_date, persons, points, kpi_minutes, support_minutes, absence_minutes in rows
        ],
    }


@register_tool(
    name="productivity_person_day",
    title="Persons produktivitet",
    description="Hämta en persons produktivitet per dag i ett datumintervall (KPI-poäng och minuter).",
    parameters={
        "type": "object",
        "properties": {
            "person": {"type": "string", "description": "Person som id eller namn."},
            "date_from": _DATE_FROM_PARAM,
            "date_to": _DATE_TO_PARAM,
            "business": _BUSINESS_PARAM,
        },
        "required": ["person"],
    },
    view_id="productivity",
)
def productivity_person_day_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    person = resolve_person(db, user, args, business_id=business_id)
    date_from, date_to = _date_range(args)
    rows = (
        db.query(
            PersonProductivityDaily.snapshot_date,
            func.sum(PersonProductivityDaily.kpi_points),
            func.sum(PersonProductivityDaily.kpi_minutes),
            func.sum(PersonProductivityDaily.support_minutes),
            func.sum(PersonProductivityDaily.absence_minutes),
        )
        .filter(
            PersonProductivityDaily.person_id == person.id,
            PersonProductivityDaily.snapshot_date >= date_from,
            PersonProductivityDaily.snapshot_date <= date_to,
        )
        .group_by(PersonProductivityDaily.snapshot_date)
        .order_by(PersonProductivityDaily.snapshot_date)
        .all()
    )
    return {
        "person": person_row(person),
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "days": [
            {
                "date": snapshot_date.isoformat(),
                "kpi_points": round(float(points or 0.0), 1),
                "kpi_minutes": int(kpi_minutes or 0),
                "support_minutes": int(support_minutes or 0),
                "absence_minutes": int(absence_minutes or 0),
            }
            for snapshot_date, points, kpi_minutes, support_minutes, absence_minutes in rows
        ],
    }


@register_tool(
    name="productivity_top_persons",
    title="Toppersoner produktivitet",
    description="Lista personer med högst KPI-poäng i ett datumintervall.",
    parameters={
        "type": "object",
        "properties": {
            "date_from": _DATE_FROM_PARAM,
            "date_to": _DATE_TO_PARAM,
            "business": _BUSINESS_PARAM,
            "limit": {"type": "integer", "description": "Max antal personer (default 10, max 200)."},
        },
    },
    view_id="productivity",
)
def productivity_top_persons_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    date_from, date_to = _date_range(args)
    limit = clamp_limit(args.get("limit"), default=10)
    rows = (
        _scoped_query(db, business_id)
        .with_entities(
            PersonProductivityDaily.person_id,
            func.sum(PersonProductivityDaily.kpi_points),
            func.sum(PersonProductivityDaily.kpi_minutes),
        )
        .filter(
            PersonProductivityDaily.snapshot_date >= date_from,
            PersonProductivityDaily.snapshot_date <= date_to,
        )
        .group_by(PersonProductivityDaily.person_id)
        .order_by(func.sum(PersonProductivityDaily.kpi_points).desc())
        .limit(limit)
        .all()
    )
    person_ids = [person_id for person_id, _points, _minutes in rows]
    persons = (
        {person.id: person for person in db.query(Person).filter(Person.id.in_(person_ids)).all()}
        if person_ids
        else {}
    )
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "persons": [
            {
                "person": person_row(persons[person_id]) if person_id in persons else {"id": person_id},
                "kpi_points": round(float(points or 0.0), 1),
                "kpi_minutes": int(minutes or 0),
            }
            for person_id, points, minutes in rows
        ],
    }


@register_tool(
    name="productivity_process_summary",
    title="Processummering",
    description="Summera produktivitet per process (t.ex. plock, mottag) i ett datumintervall.",
    parameters={
        "type": "object",
        "properties": {
            "date_from": _DATE_FROM_PARAM,
            "date_to": _DATE_TO_PARAM,
            "business": _BUSINESS_PARAM,
            "limit": {"type": "integer", "description": "Max antal processer (default 25, max 200)."},
        },
    },
    view_id="productivity",
)
def productivity_process_summary_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    date_from, date_to = _date_range(args)
    limit = clamp_limit(args.get("limit"), default=25)
    rows = (
        _scoped_query(db, business_id)
        .with_entities(
            PersonProductivityDaily.process_key,
            func.max(PersonProductivityDaily.process_label),
            func.count(func.distinct(PersonProductivityDaily.person_id)),
            func.sum(PersonProductivityDaily.kpi_points),
            func.sum(PersonProductivityDaily.units),
        )
        .filter(
            PersonProductivityDaily.snapshot_date >= date_from,
            PersonProductivityDaily.snapshot_date <= date_to,
            PersonProductivityDaily.process_key.isnot(None),
        )
        .group_by(PersonProductivityDaily.process_key)
        .order_by(func.sum(PersonProductivityDaily.kpi_points).desc())
        .limit(limit)
        .all()
    )
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "processes": [
            {
                "process_key": process_key,
                "process_label": process_label,
                "persons": int(persons or 0),
                "kpi_points": round(float(points or 0.0), 1),
                "units": round(float(units or 0.0), 1),
            }
            for process_key, process_label, persons, points, units in rows
        ],
    }

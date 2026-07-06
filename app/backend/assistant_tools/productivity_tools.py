"""Tools för produktivitet: aggregat ur person_productivity_daily.

Endast aggregerade summeringar exponeras — inga råa händelserader.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Person, PersonProductivityDaily, User
from .common import (
    WEEKDAY_LABELS,
    ToolInputError,
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


def _range_with_default_span(args: dict[str, Any], *, days: int):
    """Datumintervall där date_from defaultar till N dagar före date_to."""
    date_to = parse_date_arg(args.get("date_to") or args.get("date"), default_today=True)
    raw_from = args.get("date_from")
    date_from = parse_date_arg(raw_from) if raw_from not in (None, "") else date_to - timedelta(days=days - 1)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


@register_tool(
    name="productivity_trend",
    title="Produktivitetstrend per vecka",
    description=(
        "Produktivitet per ISO-vecka över en längre period (default 8 veckor bakåt): "
        "KPI-poäng, KPI-minuter och antal aktiva personer per vecka."
    ),
    parameters={
        "type": "object",
        "properties": {"date_from": _DATE_FROM_PARAM, "date_to": _DATE_TO_PARAM, "business": _BUSINESS_PARAM},
    },
    view_id="productivity",
)
def productivity_trend_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    date_from, date_to = _range_with_default_span(args, days=56)
    rows = (
        _scoped_query(db, business_id)
        .with_entities(
            PersonProductivityDaily.snapshot_date,
            PersonProductivityDaily.person_id,
            func.sum(PersonProductivityDaily.kpi_points),
            func.sum(PersonProductivityDaily.kpi_minutes),
        )
        .filter(
            PersonProductivityDaily.snapshot_date >= date_from,
            PersonProductivityDaily.snapshot_date <= date_to,
        )
        .group_by(PersonProductivityDaily.snapshot_date, PersonProductivityDaily.person_id)
        .all()
    )
    weeks: dict[str, dict[str, Any]] = {}
    for snapshot_date, person_id, points, minutes in rows:
        iso = snapshot_date.isocalendar()
        key = f"{iso[0]}-V{iso[1]:02d}"
        bucket = weeks.setdefault(key, {"kpi_points": 0.0, "kpi_minutes": 0, "person_ids": set()})
        bucket["kpi_points"] += float(points or 0.0)
        bucket["kpi_minutes"] += int(minutes or 0)
        bucket["person_ids"].add(person_id)
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "weeks": [
            {
                "week": week,
                "kpi_points": round(bucket["kpi_points"], 1),
                "kpi_minutes": bucket["kpi_minutes"],
                "persons": len(bucket["person_ids"]),
            }
            for week, bucket in sorted(weeks.items())
        ],
    }


@register_tool(
    name="productivity_person_compare",
    title="Person mot snittet",
    description=(
        "Jämför en persons produktivitet mot snittet av alla personer med data i samma "
        "verksamhet under ett datumintervall: KPI-poäng, minuter, poäng/timme och placering."
    ),
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
def productivity_person_compare_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    person = resolve_person(db, user, args, business_id=business_id)
    date_from, date_to = _range_with_default_span(args, days=7)
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
        .all()
    )
    totals = {
        person_id: (float(points or 0.0), int(minutes or 0))
        for person_id, points, minutes in rows
    }
    if person.id not in totals:
        return {
            "person": person_row(person),
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "note": "Ingen produktivitetsdata för personen i intervallet.",
        }
    own_points, own_minutes = totals[person.id]
    peer_points = [points for pid, (points, _minutes) in totals.items()]
    average = sum(peer_points) / len(peer_points)
    ranked = sorted(totals.items(), key=lambda item: item[1][0], reverse=True)
    rank = next(index for index, (pid, _vals) in enumerate(ranked, start=1) if pid == person.id)

    def per_hour(points: float, minutes: int) -> float | None:
        return round(points / (minutes / 60), 1) if minutes else None

    return {
        "person": person_row(person),
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "kpi_points": round(own_points, 1),
        "kpi_minutes": own_minutes,
        "points_per_hour": per_hour(own_points, own_minutes),
        "average_kpi_points": round(average, 1),
        "diff_vs_average": round(own_points - average, 1),
        "rank": rank,
        "persons_with_data": len(totals),
    }


@register_tool(
    name="productivity_process_trend",
    title="Processtrend",
    description=(
        "En process produktivitet per dag över ett datumintervall (default 30 dagar): "
        "KPI-poäng, enheter och antal personer. Ange process som nyckel eller del av namnet."
    ),
    parameters={
        "type": "object",
        "properties": {
            "process": {"type": "string", "description": "Processnyckel eller del av processnamn."},
            "date_from": _DATE_FROM_PARAM,
            "date_to": _DATE_TO_PARAM,
            "business": _BUSINESS_PARAM,
        },
        "required": ["process"],
    },
    view_id="productivity",
)
def productivity_process_trend_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    requested = str(args.get("process") or "").strip()
    if not requested:
        raise ToolInputError("Ange process som nyckel eller del av namnet.")
    date_from, date_to = _range_with_default_span(args, days=30)
    base = _scoped_query(db, business_id).filter(
        PersonProductivityDaily.snapshot_date >= date_from,
        PersonProductivityDaily.snapshot_date <= date_to,
        PersonProductivityDaily.process_key.isnot(None),
    )
    matched = (
        base.with_entities(PersonProductivityDaily.process_key)
        .filter(
            (func.lower(PersonProductivityDaily.process_key) == requested.lower())
            | PersonProductivityDaily.process_label.ilike(f"%{requested}%")
        )
        .distinct()
        .limit(6)
        .all()
    )
    keys = [row[0] for row in matched]
    if not keys:
        available = [row[0] for row in base.with_entities(PersonProductivityDaily.process_key).distinct().limit(10).all()]
        raise ToolInputError(
            f"Ingen process matchade '{requested}'. Processer med data i intervallet: {', '.join(available) or 'inga'}."
        )
    if len(keys) > 1:
        raise ToolInputError(f"Flera processer matchade '{requested}': {', '.join(keys)}. Ange exakt nyckel.")
    rows = (
        base.with_entities(
            PersonProductivityDaily.snapshot_date,
            func.max(PersonProductivityDaily.process_label),
            func.count(func.distinct(PersonProductivityDaily.person_id)),
            func.sum(PersonProductivityDaily.kpi_points),
            func.sum(PersonProductivityDaily.units),
        )
        .filter(PersonProductivityDaily.process_key == keys[0])
        .group_by(PersonProductivityDaily.snapshot_date)
        .order_by(PersonProductivityDaily.snapshot_date)
        .all()
    )
    return {
        "process_key": keys[0],
        "process_label": rows[0][1] if rows else None,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "days": [
            {
                "date": snapshot_date.isoformat(),
                "persons": int(persons or 0),
                "kpi_points": round(float(points or 0.0), 1),
                "units": round(float(units or 0.0), 1),
            }
            for snapshot_date, _label, persons, points, units in rows
        ],
    }


@register_tool(
    name="productivity_anomalies",
    title="Avvikande dagar",
    description=(
        "Hitta dagar vars totala KPI-poäng avviker mest från periodens snitt "
        "(default 30 dagar), mätt i standardavvikelser. Deterministisk beräkning."
    ),
    parameters={
        "type": "object",
        "properties": {
            "date_from": _DATE_FROM_PARAM,
            "date_to": _DATE_TO_PARAM,
            "business": _BUSINESS_PARAM,
            "threshold": {
                "type": "number",
                "description": "Lägsta avvikelse i standardavvikelser för att listas (default 2.0, minst 1.0).",
            },
        },
    },
    view_id="productivity",
)
def productivity_anomalies_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    date_from, date_to = _range_with_default_span(args, days=30)
    try:
        threshold = max(1.0, float(args.get("threshold") or 2.0))
    except (TypeError, ValueError):
        threshold = 2.0
    rows = (
        _scoped_query(db, business_id)
        .with_entities(
            PersonProductivityDaily.snapshot_date,
            func.sum(PersonProductivityDaily.kpi_points),
        )
        .filter(
            PersonProductivityDaily.snapshot_date >= date_from,
            PersonProductivityDaily.snapshot_date <= date_to,
        )
        .group_by(PersonProductivityDaily.snapshot_date)
        .order_by(PersonProductivityDaily.snapshot_date)
        .all()
    )
    day_points = [(snapshot_date, float(points or 0.0)) for snapshot_date, points in rows]
    if len(day_points) < 3:
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "note": "För få dagar med data för avvikelseanalys (minst 3 krävs).",
            "anomalies": [],
        }
    values = [points for _day, points in day_points]
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    std = variance**0.5
    if std == 0:
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "mean_kpi_points": round(mean, 1),
            "note": "Alla dagar ligger på exakt samma nivå — inga avvikelser.",
            "anomalies": [],
        }
    anomalies = [
        {
            "date": day.isoformat(),
            "kpi_points": round(points, 1),
            "z_score": round((points - mean) / std, 2),
            "weekday": WEEKDAY_LABELS.get(day.isocalendar()[2]),
        }
        for day, points in day_points
        if abs(points - mean) / std >= threshold
    ]
    anomalies.sort(key=lambda row: abs(row["z_score"]), reverse=True)
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "mean_kpi_points": round(mean, 1),
        "std_kpi_points": round(std, 1),
        "threshold": threshold,
        "days_with_data": len(day_points),
        "anomalies": anomalies[:20],
    }

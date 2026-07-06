"""Tools för personer: sökning, detaljer, kompetenser och schemamallar."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Activity, Area, Person, PersonScheduleTemplate, User
from .common import (
    WEEKDAY_LABELS,
    area_row,
    clamp_limit,
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


@register_tool(
    name="search_persons",
    title="Sök personer",
    description="Sök personer på namnfragment, filtrerbart per område och verksamhet.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Del av personens namn. Utelämna för att lista alla."},
            "area": {"type": "string", "description": "Område som id, kod eller namn."},
            "business": _BUSINESS_PARAM,
            "competency": {"type": "string", "description": "Filtrera på kompetens (exakt kod/namn)."},
            "include_inactive": {"type": "boolean", "description": "Ta även med inaktiva personer."},
            "limit": {"type": "integer", "description": "Max antal rader (default 50, max 200)."},
        },
    },
    view_id="persons",
)
def search_persons_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    area = resolve_area(db, user, args, business_id=business_id)
    limit = clamp_limit(args.get("limit"))
    query = db.query(Person).order_by(Person.name)
    if business_id is not None:
        query = query.filter(Person.business_id == business_id)
    if area is not None:
        query = query.filter(Person.home_area_id == area.id)
    text = str(args.get("query") or "").strip()
    if text:
        query = query.filter(Person.name.ilike(f"%{text}%"))
    if not args.get("include_inactive"):
        query = query.filter(Person.is_active)
    competency = str(args.get("competency") or "").strip().lower()
    persons = query.limit(500).all()
    if competency:
        persons = [
            person
            for person in persons
            if competency in {str(item or "").strip().lower() for item in (person.competencies or [])}
        ]
    total = len(persons)
    rows = [person_row(person) for person in persons[:limit]]
    result: dict[str, Any] = {"persons": rows, "count": total}
    note = truncation_note(total, len(rows))
    if note:
        result["note"] = note
    return result


@register_tool(
    name="get_person",
    title="Persondetaljer",
    description=(
        "Hämta detaljer om en person via id eller namn: hemområde, hemaktivitet, "
        "kompetenser, kragtyp och om personen har fast schema."
    ),
    parameters={
        "type": "object",
        "properties": {
            "person": {"type": "string", "description": "Person som id eller namn."},
            "business": _BUSINESS_PARAM,
        },
        "required": ["person"],
    },
    view_id="persons",
)
def get_person_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    person = resolve_person(db, user, args, business_id=business_id)
    row = person_row(person, include_details=True)
    if person.home_area_id is not None:
        area = db.get(Area, person.home_area_id)
        if area is not None:
            row["home_area"] = area_row(area)
    if person.home_activity_id is not None:
        activity = db.get(Activity, person.home_activity_id)
        if activity is not None:
            row["home_activity"] = {"id": activity.id, "code": activity.code, "label": activity.label}
    return row


@register_tool(
    name="list_competencies",
    title="Lista kompetenser",
    description="Lista alla kompetenser som förekommer bland aktiva personer och hur många som har varje.",
    parameters={
        "type": "object",
        "properties": {"business": _BUSINESS_PARAM},
    },
    view_id="persons",
)
def list_competencies_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    query = db.query(Person).filter(Person.is_active)
    if business_id is not None:
        query = query.filter(Person.business_id == business_id)
    counts: dict[str, int] = {}
    for person in query.all():
        for item in person.competencies or []:
            key = str(item or "").strip()
            if key:
                counts[key] = counts.get(key, 0) + 1
    rows = [
        {"competency": name, "persons": count}
        for name, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]
    return {"competencies": rows, "count": len(rows)}


@register_tool(
    name="get_person_schedule_template",
    title="Personens veckomall",
    description="Hämta personens fasta veckoschema-mall (starttid, sluttid eller ledig per veckodag).",
    parameters={
        "type": "object",
        "properties": {
            "person": {"type": "string", "description": "Person som id eller namn."},
            "business": _BUSINESS_PARAM,
        },
        "required": ["person"],
    },
    view_id="persons",
)
def get_person_schedule_template_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    person = resolve_person(db, user, args, business_id=business_id)
    templates = (
        db.query(PersonScheduleTemplate)
        .filter(PersonScheduleTemplate.person_id == person.id)
        .order_by(PersonScheduleTemplate.weekday)
        .all()
    )
    rows = [
        {
            "weekday": template.weekday,
            "weekday_label": WEEKDAY_LABELS.get(template.weekday, str(template.weekday)),
            "is_off": bool(template.is_off),
            "start_hour": template.start_hour,
            "end_hour": template.end_hour,
        }
        for template in templates
    ]
    return {
        "person": person_row(person),
        "has_fixed_schedule": bool(person.has_fixed_schedule),
        "template": rows,
    }

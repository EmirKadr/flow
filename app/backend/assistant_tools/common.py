"""Delade hjälpare för apphjälpens tools: datum, scoping och serialisering.

Alla tools är read-only och verksamhetsscopas alltid via business_scope.
Vybehörighet per tool är förberedd som metadata i registret men enforcement
styrs av ASSISTANT_TOOLS_ENFORCE_VIEW_ACCESS (default av).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..business_scope import get_business_by_input, visible_business_id
from ..models import Activity, Area, Business, Person, User

WEEKDAY_LABELS = {
    1: "måndag",
    2: "tisdag",
    3: "onsdag",
    4: "torsdag",
    5: "fredag",
    6: "lördag",
    7: "söndag",
}

PERIODS = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

DEFAULT_ROW_LIMIT = 50
MAX_ROW_LIMIT = 200


class ToolInputError(ValueError):
    """Fel i tool-argument som ska förklaras för modellen, inte krascha anropet."""


def parse_date_arg(value: Any, *, default_today: bool = False) -> date:
    if value is None or str(value).strip() == "":
        if default_today:
            return date.today()
        raise ToolInputError("Ange datum som YYYY-MM-DD.")
    text = str(value).strip().lower()
    if text in {"idag", "today"}:
        return date.today()
    if text in {"igår", "igar", "yesterday"}:
        return date.today() - timedelta(days=1)
    if text in {"imorgon", "tomorrow"}:
        return date.today() + timedelta(days=1)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ToolInputError(f"Ogiltigt datum '{value}'. Använd formatet YYYY-MM-DD.") from exc


def iso_parts(value: date) -> tuple[int, int, int]:
    iso = value.isocalendar()
    return iso[0], iso[1], iso[2]


def parse_period_arg(value: Any, *, default: str = "24h") -> tuple[str, datetime]:
    text = str(value or "").strip().lower() or default
    if text not in PERIODS:
        raise ToolInputError(f"Ogiltig period '{value}'. Välj en av: {', '.join(PERIODS)}.")
    return text, datetime.now(timezone.utc) - PERIODS[text]


def clamp_limit(value: Any, *, default: int = DEFAULT_ROW_LIMIT, maximum: int = MAX_ROW_LIMIT) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(limit, maximum))


def resolve_business_id(db: Session, user: User, args: dict, *, key: str = "business") -> int | None:
    """Verksamhet ur tool-argument, alltid begränsad till vad användaren får se."""
    requested = args.get(key)
    requested_id: int | None = None
    if requested not in (None, ""):
        business = get_business_by_input(db, requested)
        if business is None:
            raise ToolInputError(f"Verksamheten '{requested}' hittades inte.")
        requested_id = business.id
    return visible_business_id(db, user, requested_id)


def resolve_area(db: Session, user: User, args: dict, *, key: str = "area", business_id: int | None = None) -> Area | None:
    requested = args.get(key)
    if requested in (None, ""):
        return None
    query = db.query(Area)
    if business_id is not None:
        query = query.filter(Area.business_id == business_id)
    text = str(requested).strip()
    if text.isdigit():
        area = query.filter(Area.id == int(text)).one_or_none()
    else:
        area = (
            query.filter(or_(func.upper(Area.code) == text.upper(), func.upper(Area.name) == text.upper()))
            .order_by(Area.sort_order, Area.id)
            .first()
        )
    if area is None:
        raise ToolInputError(f"Området '{requested}' hittades inte i vald verksamhet.")
    if business_id is None:
        # Utan uttrycklig verksamhet får området inte peka utanför användarens scope.
        visible = visible_business_id(db, user, None)
        if visible is not None and area.business_id not in (None, visible):
            raise ToolInputError(f"Området '{requested}' hittades inte i vald verksamhet.")
    return area


def resolve_person(db: Session, user: User, args: dict, *, key: str = "person", business_id: int | None = None) -> Person:
    requested = args.get(key)
    if requested in (None, ""):
        raise ToolInputError("Ange person som id eller namn.")
    scope_id = business_id if business_id is not None else visible_business_id(db, user, None)
    query = db.query(Person)
    if scope_id is not None:
        query = query.filter(Person.business_id == scope_id)
    text = str(requested).strip()
    if text.isdigit():
        person = query.filter(Person.id == int(text)).one_or_none()
        if person is None:
            raise ToolInputError(f"Personen med id {text} hittades inte.")
        return person
    matches = (
        query.filter(Person.name.ilike(f"%{text}%"))
        .order_by(Person.is_active.desc(), Person.name)
        .limit(6)
        .all()
    )
    if not matches:
        raise ToolInputError(f"Ingen person matchade '{requested}'.")
    exact = [person for person in matches if person.name.strip().lower() == text.lower()]
    if len(exact) == 1:
        return exact[0]
    if len(matches) == 1:
        return matches[0]
    names = ", ".join(f"{person.name} (id {person.id})" for person in matches)
    raise ToolInputError(f"Flera personer matchade '{requested}': {names}. Ange id.")


def business_row(business: Business) -> dict[str, Any]:
    return {
        "id": business.id,
        "code": business.code,
        "name": business.name,
        "is_active": bool(business.is_active),
    }


def area_row(area: Area) -> dict[str, Any]:
    return {
        "id": area.id,
        "code": area.code,
        "name": area.name,
        "business_id": area.business_id,
        "is_active": bool(area.is_active),
    }


def activity_row(activity: Activity) -> dict[str, Any]:
    return {
        "id": activity.id,
        "code": activity.code,
        "label": activity.label,
        "category": activity.category,
        "work_type": activity.work_type,
        "area_id": activity.area_id,
        "business_id": activity.business_id,
        "required_competency": activity.required_competency,
        "is_active": bool(activity.is_active),
    }


def person_row(person: Person, *, include_details: bool = False) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": person.id,
        "name": person.name,
        "business_id": person.business_id,
        "home_area_id": person.home_area_id,
        "is_active": bool(person.is_active),
    }
    if include_details:
        row.update(
            {
                "collar_type": person.collar_type,
                "home_activity_id": person.home_activity_id,
                "competencies": list(person.competencies or []),
                "has_fixed_schedule": bool(person.has_fixed_schedule),
                "comment": (person.comment or "")[:300] or None,
            }
        )
    return row


def truncation_note(total: int, shown: int) -> str | None:
    if total <= shown:
        return None
    return f"Visar {shown} av {total} rader. Förfina filtren för att se fler."


def percentile(values: list[int | float], p: float) -> float:
    """Deterministisk percentil (närmaste rang, p i 0-100) utan numpy-beroende."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = max(1, -(-int(p) * len(ordered) // 100))  # ceil(p/100 * n), minst 1
    return float(ordered[min(rank, len(ordered)) - 1])

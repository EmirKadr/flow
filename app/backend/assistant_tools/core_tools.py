"""Tools för grunddata: verksamheter, områden, aktiviteter och datumhjälp."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Activity, Area, Business, Person, User
from .common import (
    WEEKDAY_LABELS,
    activity_row,
    area_row,
    business_row,
    clamp_limit,
    iso_parts,
    parse_date_arg,
    resolve_area,
    resolve_business_id,
    truncation_note,
)
from .registry import register_tool

_BUSINESS_PARAM = {
    "type": "string",
    "description": "Verksamhet som id, kod eller namn (t.ex. STIGAMO). Utelämna för användarens egen verksamhet.",
}
_AREA_PARAM = {
    "type": "string",
    "description": "Område som id, kod eller namn (t.ex. GG).",
}
_INCLUDE_INACTIVE_PARAM = {
    "type": "boolean",
    "description": "Ta även med inaktiva rader. Default false.",
}


@register_tool(
    name="resolve_date",
    title="Datumhjälp",
    description=(
        "Slå upp vilket ISO-år, vecka och veckodag ett datum motsvarar i schemat. "
        "Stöder YYYY-MM-DD samt 'idag', 'igår' och 'imorgon'. Använd detta först när frågan gäller schemadata."
    ),
    parameters={
        "type": "object",
        "properties": {"date": {"type": "string", "description": "Datum (YYYY-MM-DD) eller idag/igår/imorgon."}},
    },
    view_id="schedule",
)
def resolve_date_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    value = parse_date_arg(args.get("date"), default_today=True)
    year, week, weekday = iso_parts(value)
    return {
        "date": value.isoformat(),
        "iso_year": year,
        "iso_week": week,
        "weekday": weekday,
        "weekday_label": WEEKDAY_LABELS[weekday],
    }


@register_tool(
    name="list_businesses",
    title="Lista verksamheter",
    description="Lista verksamheter användaren har åtkomst till, med id, kod och namn.",
    view_id="businesses",
)
def list_businesses_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    scope_id = resolve_business_id(db, user, {})
    query = db.query(Business).order_by(Business.sort_order, Business.id)
    if scope_id is not None:
        query = query.filter(Business.id == scope_id)
    rows = [business_row(business) for business in query.all()]
    return {"businesses": rows, "count": len(rows)}


@register_tool(
    name="list_areas",
    title="Lista områden",
    description="Lista områden med kod och namn, filtrerbart per verksamhet.",
    parameters={
        "type": "object",
        "properties": {"business": _BUSINESS_PARAM, "include_inactive": _INCLUDE_INACTIVE_PARAM},
    },
    view_id="areas",
)
def list_areas_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    query = db.query(Area).order_by(Area.sort_order, Area.id)
    if business_id is not None:
        query = query.filter(Area.business_id == business_id)
    if not args.get("include_inactive"):
        query = query.filter(Area.is_active)
    rows = [area_row(area) for area in query.all()]
    return {"areas": rows, "count": len(rows)}


@register_tool(
    name="list_activities",
    title="Lista aktiviteter",
    description=(
        "Lista aktiviteter med kod, label och kategori (work/absence). "
        "Filtrerbart per verksamhet, område och kategori."
    ),
    parameters={
        "type": "object",
        "properties": {
            "business": _BUSINESS_PARAM,
            "area": _AREA_PARAM,
            "category": {"type": "string", "description": "Filtrera på kategori, t.ex. work eller absence."},
            "include_inactive": _INCLUDE_INACTIVE_PARAM,
            "limit": {"type": "integer", "description": "Max antal rader (default 50, max 200)."},
        },
    },
    view_id="activities",
)
def list_activities_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    business_id = resolve_business_id(db, user, args)
    area = resolve_area(db, user, args, business_id=business_id)
    limit = clamp_limit(args.get("limit"))
    query = db.query(Activity).order_by(Activity.sort_order, Activity.id)
    if business_id is not None:
        query = query.filter(Activity.business_id == business_id)
    if area is not None:
        query = query.filter(Activity.area_id == area.id)
    category = str(args.get("category") or "").strip().lower()
    if category:
        query = query.filter(func.lower(Activity.category) == category)
    if not args.get("include_inactive"):
        query = query.filter(Activity.is_active)
    total = query.count()
    rows = [activity_row(activity) for activity in query.limit(limit).all()]
    result: dict[str, Any] = {"activities": rows, "count": total}
    note = truncation_note(total, len(rows))
    if note:
        result["note"] = note
    return result


@register_tool(
    name="get_activity",
    title="Aktivitetsdetaljer",
    description="Hämta detaljer om en aktivitet via id, kod eller label, inklusive område och kompetenskrav.",
    parameters={
        "type": "object",
        "properties": {
            "activity": {"type": "string", "description": "Aktivitet som id, kod eller label."},
            "business": _BUSINESS_PARAM,
        },
        "required": ["activity"],
    },
    view_id="activities",
)
def get_activity_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    from .common import ToolInputError

    requested = str(args.get("activity") or "").strip()
    if not requested:
        raise ToolInputError("Ange aktivitet som id, kod eller label.")
    business_id = resolve_business_id(db, user, args)
    query = db.query(Activity)
    if business_id is not None:
        query = query.filter(Activity.business_id == business_id)
    if requested.isdigit():
        activity = query.filter(Activity.id == int(requested)).one_or_none()
    else:
        activity = (
            query.filter(
                (func.upper(Activity.code) == requested.upper())
                | (func.upper(Activity.label) == requested.upper())
            )
            .order_by(Activity.sort_order, Activity.id)
            .first()
        )
    if activity is None:
        raise ToolInputError(f"Aktiviteten '{requested}' hittades inte.")
    row = activity_row(activity)
    if activity.area_id is not None:
        area = db.get(Area, activity.area_id)
        if area is not None:
            row["area"] = area_row(area)
    return row


@register_tool(
    name="data_counts",
    title="Dataöversikt",
    description="Antal aktiva områden, aktiviteter och personer per verksamhet användaren ser.",
    view_id="overview",
)
def data_counts_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    scope_id = resolve_business_id(db, user, {})
    business_query = db.query(Business).order_by(Business.sort_order, Business.id)
    if scope_id is not None:
        business_query = business_query.filter(Business.id == scope_id)
    rows: list[dict[str, Any]] = []
    for business in business_query.all():
        rows.append(
            {
                "business": business_row(business),
                "active_areas": db.query(func.count(Area.id)).filter(Area.business_id == business.id, Area.is_active).scalar() or 0,
                "active_activities": db.query(func.count(Activity.id)).filter(Activity.business_id == business.id, Activity.is_active).scalar() or 0,
                "active_persons": db.query(func.count(Person.id)).filter(Person.business_id == business.id, Person.is_active).scalar() or 0,
            }
        )
    return {"summary": rows}

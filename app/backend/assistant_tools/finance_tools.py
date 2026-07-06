"""Tools för ekonomi: intäkt/kostnad ur produktivitetens finanslager.

Återanvänder samma beräkning som Produktivitets periodöversikt
(build_business_summary_payload) — ingen egen pengamatte här. Ekonomidata
är känslig: toolen kräver alltid vybehörighet productivityFinance i runtime,
oavsett den globala enforcement-flaggan.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import User
from .common import ToolInputError, parse_date_arg
from .registry import register_tool

_MAX_CUSTOM_DAYS = 92


@register_tool(
    name="finance_summary",
    title="Intäkt och kostnad",
    description=(
        "Summera intäkt, VAS-intäkt, processintäkt, bemanningskostnad och resultat "
        "per bolag för en period (dag, vecka, månad eller eget datumintervall). "
        "Samma siffror som Produktivitets periodöversikt. Kräver behörighet till Intäkt/utgift."
    ),
    parameters={
        "type": "object",
        "properties": {
            "period": {
                "type": "string",
                "description": "day, week, month eller custom. Default day.",
            },
            "date": {
                "type": "string",
                "description": "Ankardatum (YYYY-MM-DD, idag eller igår). Default idag.",
            },
            "start_date": {"type": "string", "description": "Startdatum vid period=custom."},
            "end_date": {"type": "string", "description": "Slutdatum vid period=custom."},
        },
    },
    view_id="productivityFinance",
    min_level="view",
    tags=("finance",),
)
def finance_summary_tool(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    # Lazy import: drar in produktivitetsstacken först när toolet faktiskt körs.
    from ..routers.productivity_finance_helpers import _can_view_productivity_finance
    from ..routers.productivity_helpers import build_business_summary_payload

    if not _can_view_productivity_finance(db, user):
        raise ToolInputError(
            "Intäkt/utgift kräver behörighet till vyn Intäkt/utgift — svaret kan inte lämnas ut."
        )
    period = str(args.get("period") or "day").strip().lower()
    if period not in {"day", "week", "month", "custom"}:
        raise ToolInputError("Ogiltig period. Välj day, week, month eller custom.")
    anchor = parse_date_arg(args.get("date"), default_today=True)
    start = end = None
    if period == "custom":
        start = parse_date_arg(args.get("start_date"))
        end = parse_date_arg(args.get("end_date"))
        if end < start:
            start, end = end, start
        if (end - start).days + 1 > _MAX_CUSTOM_DAYS:
            raise ToolInputError(f"Välj högst {_MAX_CUSTOM_DAYS} dagar åt gången.")
    payload = build_business_summary_payload(
        db,
        user,
        period=period,
        anchor_date=anchor,
        start_date=start,
        end_date=end,
    )
    if not payload.get("finance_visible"):
        raise ToolInputError("Intäkt/utgift är inte synligt för din användare.")
    return {
        "period": payload.get("period"),
        "currency": payload.get("currency"),
        "business": payload.get("business"),
        "companies": payload.get("companies"),
        "totals": payload.get("totals"),
        "missing_dates_count": len(payload.get("missing_dates") or []),
        "errors_count": len(payload.get("errors") or []),
    }

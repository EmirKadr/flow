"""Public read-only-endpoint för Excel/extern integration.

Skyddas med EXCEL_API_TOKEN (env-variabel). Returnerar bara talet
som plain text så Excel WEBSERVICE() / Power Query enkelt kan läsa det.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import get_db
from ..models import Activity, Person, ScheduleCell
from ..template_service import get_template_hours

router = APIRouter(prefix="/api/public", tags=["public"])


def _verify_token(token: str) -> None:
    expected = (settings.EXCEL_API_TOKEN or "").strip()
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Token not configured")
    if not token or token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


@router.get("/hours", response_class=PlainTextResponse)
def get_hours(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    activity: str = Query(..., description="Activity code (t.ex. GG_PLOCK)"),
    token: str = Query(..., description="API-token från EXCEL_API_TOKEN"),
    db: Session = Depends(get_db),
) -> str:
    _verify_token(token)

    act = db.query(Activity).filter_by(code=activity).one_or_none()
    if not act:
        return "0"

    # 1. Explicit ifyllda minuter med denna aktivitet
    explicit_minutes = db.execute(
        select(func.coalesce(func.sum(ScheduleCell.minute_end - ScheduleCell.minute_start), 0))
        .where(
            ScheduleCell.year == year,
            ScheduleCell.week == week,
            ScheduleCell.weekday == weekday,
            ScheduleCell.activity_id == act.id,
        )
    ).scalar() or 0

    # 2. Implicit standard: personer med home_activity_id == act.id som är schemalagda
    #    den dagen, för timslots utan explicit segment (varken fyllt eller tömt).
    implicit_minutes = 0
    matching_persons = db.execute(
        select(Person).where(
            Person.home_activity_id == act.id,
            Person.is_active.is_(True),
        )
    ).scalars().all()

    for p in matching_persons:
        template_hours_set = get_template_hours(db, p.id, weekday)
        if not template_hours_set:
            continue
        for hour in template_hours_set:
            covered = db.execute(
                select(
                    func.coalesce(func.sum(ScheduleCell.minute_end - ScheduleCell.minute_start), 0)
                ).where(
                    ScheduleCell.year == year,
                    ScheduleCell.week == week,
                    ScheduleCell.weekday == weekday,
                    ScheduleCell.person_id == p.id,
                    ScheduleCell.hour == hour,
                )
            ).scalar() or 0
            implicit_minutes += max(0, 60 - covered)

    total_hours = (explicit_minutes + implicit_minutes) / 60.0
    # Returnera utan trailing .0 om heltal
    if total_hours == int(total_hours):
        return str(int(total_hours))
    return f"{total_hours:.2f}"

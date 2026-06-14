from .schedule_shared import *

router = APIRouter()

@router.get("/productivity-summary")
def get_schedule_productivity_summary(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
    _productivity_user: User = Depends(require_view_access("productivity", "view")),
) -> dict:
    return schedule_productivity_summary(
        db,
        user,
        year=year,
        week=week,
        weekday=weekday,
    )



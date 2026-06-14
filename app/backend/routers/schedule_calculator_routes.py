from .schedule_shared import *

router = APIRouter()

@router.get("/calculator-profile")
def get_calculator_profile(
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict:
    return _calculator_profile_response(db, user)


@router.put("/calculator-profile")
def update_calculator_profile(
    payload: StaffingCalculatorProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict:
    before = _user_calculator_profile(db, user)
    after = _set_user_calculator_profile(db, user, payload.profile)
    if before != after:
        audit_log(
            db,
            entity_type="staffing_calculator_profile",
            entity_id=int(getattr(user, "id", 0) or 0),
            action="update_staffing_calculator_profile",
            old_value={"calculator_count": staffing_calculator_profile_count(before)},
            new_value={"calculator_count": staffing_calculator_profile_count(after)},
            user_id=getattr(user, "id", None),
            business_id=getattr(user, "business_id", None),
        )
    db.commit()
    return _calculator_profile_response(db, user)


@router.post("/calculator-profile/import")
def import_calculator_profile(
    payload: StaffingCalculatorProfileImport,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict:
    source_user = _assert_calculator_profile_source_allowed(db, user, payload.user_id)
    source_profile = _user_calculator_profile(db, source_user)
    if staffing_calculator_profile_count(source_profile) <= 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Anvandaren har inga sparade bemanningskalkyler")
    before = _user_calculator_profile(db, user)
    after = _set_user_calculator_profile(db, user, source_profile)
    audit_log(
        db,
        entity_type="staffing_calculator_profile",
        entity_id=int(getattr(user, "id", 0) or 0),
        action="import_staffing_calculator_profile",
        old_value={"calculator_count": staffing_calculator_profile_count(before)},
        new_value={
            "calculator_count": staffing_calculator_profile_count(after),
            "source_user_id": getattr(source_user, "id", None),
        },
        user_id=getattr(user, "id", None),
        business_id=getattr(user, "business_id", None),
    )
    db.commit()
    return _calculator_profile_response(db, user)


@router.get("/calculator/automatic")
def get_automatic_calculator_results(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict:
    return calculate_staffing_automatic(
        db,
        user,
        _user_calculator_profile(db, user),
        year=year,
        week=week,
        weekday=weekday,
    )


@router.get("/activity-capacity")
def get_activity_capacity(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict:
    return schedule_activity_capacity(
        db,
        user,
        year=year,
        week=week,
        weekday=weekday,
    )


@router.get("/activity-capacity/cell")
def get_activity_capacity_cell(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    person_id: int = Query(..., ge=1),
    activity_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict:
    return schedule_activity_capacity_cell(
        db,
        user,
        year=year,
        week=week,
        weekday=weekday,
        person_id=person_id,
        activity_id=activity_id,
    )



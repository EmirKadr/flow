from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..business_scope import filter_query_for_business, resolve_write_business_id, scoped_get
from ..code_utils import code_part
from ..deps import get_current_user, get_db, require_view_access
from ..models import Activity, Area, Person, ScheduleCell, User
from ..schemas import AreaCreate, AreaOut, AreaUpdate

router = APIRouter(prefix="/api/areas", tags=["areas"])


def _area_snapshot(area: Area) -> dict:
    return {
        "id": area.id,
        "business_id": area.business_id,
        "code": area.code,
        "name": area.name,
        "sort_order": area.sort_order,
        "is_active": area.is_active,
    }


def _clean_area_code(value: str | None) -> str:
    code = code_part(value)
    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Områdeskod saknar giltiga tecken")
    return code[:20]


def _unique_area_code(db: Session, *, business_id: int | None, base: str) -> str:
    base = (base or "OMRADE")[:20].rstrip("_") or "OMRADE"
    candidate = base
    suffix = 2
    while db.query(Area).filter_by(business_id=business_id, code=candidate).first():
        suffix_text = f"_{suffix}"
        candidate = f"{base[:20 - len(suffix_text)].rstrip('_')}{suffix_text}"
        suffix += 1
    return candidate


def _resolve_area_code(db: Session, payload: AreaCreate, business_id: int | None) -> str:
    provided = (payload.code or "").strip()
    if provided:
        code = _clean_area_code(provided)
        if db.query(Area).filter_by(business_id=business_id, code=code).first():
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Område med samma kod finns redan")
        return code
    return _unique_area_code(db, business_id=business_id, base=code_part(payload.name))


def _area_has_linked_data(db: Session, area_id: int) -> bool:
    return any(
        query.first() is not None
        for query in (
            db.query(Person.id).filter(Person.home_area_id == area_id),
            db.query(Activity.id).filter(Activity.area_id == area_id),
            db.query(User.id).filter(User.area_id == area_id),
            db.query(ScheduleCell.id).filter(ScheduleCell.loan_area_id == area_id),
        )
    )


def _detach_area_references(db: Session, area_id: int) -> dict[str, int]:
    """Koppla loss framtiden från området; historiska schemaceller bevaras.

    Historiska celler (t.o.m. idag) är en frusen logg: lånemarkeringar och
    aktivitetsceller i förfluten tid rörs inte. Bara framtida celler töms.
    Ofrysta gårdagar materialiseras först så inga implicita malltimmar hinner
    tappas när huvudaktiviteter nollas.
    """
    from ..schedule_freeze import (
        clear_future_cells_for_activities,
        clear_future_loan_markers,
        freeze_pending_for_request,
    )

    freeze_pending_for_request(db)
    activity_ids = [
        activity_id
        for (activity_id,) in db.query(Activity.id).filter(Activity.area_id == area_id).all()
    ]
    detached: dict[str, int] = {
        "persons": db.query(Person)
        .filter(Person.home_area_id == area_id)
        .update({Person.home_area_id: None}, synchronize_session=False),
        "users": db.query(User)
        .filter(User.area_id == area_id)
        .update({User.area_id: None}, synchronize_session=False),
        "activities": 0,
        "home_activities": 0,
        "summary_activities": 0,
        "schedule_cells": 0,
        "loan_schedule_cells": clear_future_loan_markers(db, area_id),
    }
    if activity_ids:
        detached["home_activities"] = db.query(Person).filter(Person.home_activity_id.in_(activity_ids)).update(
            {Person.home_activity_id: None},
            synchronize_session=False,
        )
        detached["summary_activities"] = db.query(Activity).filter(Activity.summary_activity_id.in_(activity_ids)).update(
            {Activity.summary_activity_id: None},
            synchronize_session=False,
        )
        detached["schedule_cells"] = clear_future_cells_for_activities(db, activity_ids)
        detached["activities"] = db.query(Activity).filter(Activity.id.in_(activity_ids)).update(
            {Activity.area_id: None, Activity.is_active: False},
            synchronize_session=False,
        )
    return detached


@router.get("", response_model=list[AreaOut])
def list_areas(
    include_inactive: bool = False,
    business_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Area]:
    q = db.query(Area)
    q = filter_query_for_business(q, Area, db, user, business_id)
    if not include_inactive:
        q = q.filter(Area.is_active)
    return q.order_by(Area.sort_order, Area.name).all()


@router.post("", response_model=AreaOut, status_code=status.HTTP_201_CREATED)
def create_area(payload: AreaCreate, db: Session = Depends(get_db), admin: User = Depends(require_view_access("areas", "edit"))) -> Area:
    business_id = resolve_write_business_id(db, admin, requested_business_id=payload.business_id)
    data = payload.model_dump()
    data["business_id"] = business_id
    data["code"] = _resolve_area_code(db, payload, business_id)
    data["name"] = payload.name.strip() or data["code"]
    area = Area(**data)
    db.add(area)
    db.flush()
    audit_log(
        db,
        entity_type="area",
        entity_id=area.id,
        action="create",
        old_value=None,
        new_value=_area_snapshot(area),
        user_id=admin.id,
        business_id=area.business_id,
    )
    db.commit()
    db.refresh(area)
    return area


@router.put("/{area_id}", response_model=AreaOut)
def update_area(
    area_id: int,
    payload: AreaUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("areas", "edit")),
) -> Area:
    area = scoped_get(db, Area, area_id, admin, detail="Område hittades inte")
    if not area:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Område hittades inte")
    before = _area_snapshot(area)
    data = payload.model_dump(exclude_unset=True)
    if "business_id" in data and data["business_id"] != area.business_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Område kan inte flyttas mellan verksamheter")
    if "code" in data:
        if data["code"] is None:
            data.pop("code")
        else:
            data["code"] = _clean_area_code(data["code"])
            existing = (
                db.query(Area)
                .filter(Area.business_id == area.business_id, Area.code == data["code"], Area.id != area.id)
                .first()
            )
            if existing:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="Område med samma kod finns redan")
    for key, value in data.items():
        setattr(area, key, value)
    audit_log(
        db,
        entity_type="area",
        entity_id=area.id,
        action="update",
        old_value=before,
        new_value=_area_snapshot(area),
        user_id=admin.id,
        business_id=area.business_id,
    )
    db.commit()
    db.refresh(area)
    return area


@router.delete("/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_area(
    area_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("areas", "edit")),
) -> None:
    area = scoped_get(db, Area, area_id, admin, detail="Område hittades inte")
    if not area:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Område hittades inte")
    before = _area_snapshot(area)
    if _area_has_linked_data(db, area_id):
        detached = _detach_area_references(db, area_id)
        area.is_active = False
        audit_log(
            db,
            entity_type="area",
            entity_id=area.id,
            action="update",
            old_value=before,
            new_value={**_area_snapshot(area), "detached": detached},
            user_id=admin.id,
            business_id=area.business_id,
        )
    else:
        db.delete(area)
        audit_log(
            db,
            entity_type="area",
            entity_id=area.id,
            action="delete",
            old_value=before,
            new_value=None,
            user_id=admin.id,
            business_id=area.business_id,
        )
    db.commit()

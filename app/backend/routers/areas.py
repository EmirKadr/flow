from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..business_scope import filter_query_for_business, resolve_write_business_id, scoped_get
from ..deps import get_current_user, get_db, require_view_access
from ..models import Activity, Area, Person, User
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


def _area_has_linked_data(db: Session, area_id: int) -> bool:
    return any(
        query.first() is not None
        for query in (
            db.query(Person.id).filter(Person.home_area_id == area_id),
            db.query(Activity.id).filter(Activity.area_id == area_id),
            db.query(User.id).filter(User.area_id == area_id),
        )
    )


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
        q = q.filter(Area.is_active.is_(True))
    return q.order_by(Area.sort_order, Area.name).all()


@router.post("", response_model=AreaOut, status_code=status.HTTP_201_CREATED)
def create_area(payload: AreaCreate, db: Session = Depends(get_db), admin: User = Depends(require_view_access("areas", "edit"))) -> Area:
    business_id = resolve_write_business_id(db, admin, requested_business_id=payload.business_id)
    if db.query(Area).filter_by(business_id=business_id, code=payload.code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Område med samma kod finns redan")
    data = payload.model_dump()
    data["business_id"] = business_id
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
        area.is_active = False
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

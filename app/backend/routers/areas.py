from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..deps import get_current_user, get_db, require_view_access
from ..models import Area, User
from ..schemas import AreaCreate, AreaOut, AreaUpdate

router = APIRouter(prefix="/api/areas", tags=["areas"])


def _area_snapshot(area: Area) -> dict:
    return {
        "id": area.id,
        "code": area.code,
        "name": area.name,
        "sort_order": area.sort_order,
        "is_active": area.is_active,
    }


@router.get("", response_model=list[AreaOut])
def list_areas(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> list[Area]:
    q = db.query(Area)
    if not include_inactive:
        q = q.filter(Area.is_active.is_(True))
    return q.order_by(Area.sort_order, Area.name).all()


@router.post("", response_model=AreaOut, status_code=status.HTTP_201_CREATED)
def create_area(payload: AreaCreate, db: Session = Depends(get_db), admin: User = Depends(require_view_access("areas", "edit"))) -> Area:
    if db.query(Area).filter_by(code=payload.code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Område med samma kod finns redan")
    area = Area(**payload.model_dump())
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
    area = db.get(Area, area_id)
    if not area:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Område hittades inte")
    before = _area_snapshot(area)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(area, key, value)
    audit_log(
        db,
        entity_type="area",
        entity_id=area.id,
        action="update",
        old_value=before,
        new_value=_area_snapshot(area),
        user_id=admin.id,
    )
    db.commit()
    db.refresh(area)
    return area

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..business_scope import normalize_business_code
from ..deps import get_db, require_super_user
from ..models import Business, User
from ..schemas import BusinessCreate, BusinessOut, BusinessUpdate


router = APIRouter(prefix="/api/businesses", tags=["businesses"])


def _business_snapshot(business: Business) -> dict:
    return {
        "id": business.id,
        "code": business.code,
        "name": business.name,
        "sort_order": business.sort_order,
        "is_active": business.is_active,
    }


def _clean_code(value: str) -> str:
    code = normalize_business_code(value)
    code = re.sub(r"[^A-Z0-9_]+", "_", code).strip("_")
    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Verksamhetskod krävs")
    return code[:20]


@router.get("", response_model=list[BusinessOut])
def list_businesses(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> list[Business]:
    query = db.query(Business)
    if not include_inactive:
        query = query.filter(Business.is_active.is_(True))
    return query.order_by(Business.sort_order, Business.name).all()


@router.post("", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
def create_business(
    payload: BusinessCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_super_user),
) -> Business:
    code = _clean_code(payload.code)
    if db.query(Business).filter(Business.code == code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Verksamhet med samma kod finns redan")
    business = Business(
        code=code,
        name=payload.name.strip() or code,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    db.add(business)
    db.flush()
    audit_log(
        db,
        entity_type="business",
        entity_id=business.id,
        action="create",
        old_value=None,
        new_value=_business_snapshot(business),
        user_id=user.id,
        business_id=business.id,
    )
    db.commit()
    db.refresh(business)
    return business


@router.put("/{business_id}", response_model=BusinessOut)
def update_business(
    business_id: int,
    payload: BusinessUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_super_user),
) -> Business:
    business = db.get(Business, business_id)
    if not business:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Verksamhet hittades inte")
    before = _business_snapshot(business)
    data = payload.model_dump(exclude_unset=True)
    if "code" in data and data["code"] is not None:
        code = _clean_code(data["code"])
        existing = db.query(Business).filter(Business.code == code, Business.id != business_id).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Verksamhet med samma kod finns redan")
        business.code = code
    if "name" in data and data["name"] is not None:
        business.name = data["name"].strip() or business.code
    if "sort_order" in data and data["sort_order"] is not None:
        business.sort_order = data["sort_order"]
    if "is_active" in data and data["is_active"] is not None:
        business.is_active = data["is_active"]
    audit_log(
        db,
        entity_type="business",
        entity_id=business.id,
        action="update",
        old_value=before,
        new_value=_business_snapshot(business),
        user_id=user.id,
        business_id=business.id,
    )
    db.commit()
    db.refresh(business)
    return business

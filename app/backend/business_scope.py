from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Activity, Area, Business, Person, User
from .user_access import is_super_user


DEFAULT_BUSINESS_CODE = "STIGAMO"
DEFAULT_BUSINESS_NAME = "Stigamo"
R3_BUSINESS_CODE = "R3"
R3_BUSINESS_NAME = "R3"


def normalize_business_code(value: str | None) -> str:
    return str(value or "").strip().upper()


def get_business_by_code(db: Session, code: str) -> Business | None:
    normalized = normalize_business_code(code)
    if not normalized:
        return None
    return db.query(Business).filter(Business.code == normalized).one_or_none()


def get_business_by_input(db: Session, value: object) -> Business | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        return db.get(Business, value)
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return db.get(Business, int(text))
    normalized = normalize_business_code(text)
    return (
        db.query(Business)
        .filter((Business.code == normalized) | (func.upper(Business.name) == normalized))
        .one_or_none()
    )


def default_business(db: Session) -> Business | None:
    try:
        return get_business_by_code(db, DEFAULT_BUSINESS_CODE) or db.query(Business).order_by(Business.sort_order, Business.id).first()
    except Exception:
        return None


def ensure_seed_businesses(db: Session) -> dict[str, Business]:
    specs = [
        {"code": DEFAULT_BUSINESS_CODE, "name": DEFAULT_BUSINESS_NAME, "sort_order": 1},
        {"code": R3_BUSINESS_CODE, "name": R3_BUSINESS_NAME, "sort_order": 2},
    ]
    result: dict[str, Business] = {}
    for spec in specs:
        business = get_business_by_code(db, spec["code"])
        if business is None:
            business = Business(**spec, is_active=True)
            db.add(business)
        else:
            business.name = spec["name"]
            business.sort_order = spec["sort_order"]
            business.is_active = True
        result[spec["code"]] = business
    db.flush()
    return result


def user_business_id(db: Session, user: User) -> int | None:
    if getattr(user, "business_id", None) is not None:
        return user.business_id
    business = default_business(db)
    return business.id if business is not None else None


def visible_business_id(
    db: Session,
    user: User,
    requested_business_id: int | None = None,
    *,
    require_for_super_user: bool = False,
) -> int | None:
    if requested_business_id is not None and not isinstance(requested_business_id, int):
        requested_business_id = None
    if not hasattr(user, "role"):
        return requested_business_id
    if is_super_user(user):
        if requested_business_id is not None:
            if not db.get(Business, requested_business_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Verksamhet hittades inte")
            return requested_business_id
        if require_for_super_user:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Super User måste välja verksamhet")
        return None

    business_id = user_business_id(db, user)
    if requested_business_id is not None and business_id is not None and requested_business_id != business_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Verksamhet hittades inte")
    return business_id


def filter_query_for_business(query, model, db: Session, user: User, requested_business_id: int | None = None):
    business_id = visible_business_id(db, user, requested_business_id)
    if business_id is None:
        return query
    return query.filter(model.business_id == business_id)


def filter_select_for_business(statement, model, db: Session, user: User, requested_business_id: int | None = None):
    business_id = visible_business_id(db, user, requested_business_id)
    if business_id is None:
        return statement
    return statement.where(model.business_id == business_id)


def assert_user_can_access_business(db: Session, user: User, business_id: int | None) -> None:
    if business_id is None or not hasattr(user, "role") or is_super_user(user):
        return
    if user_business_id(db, user) != business_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Objekt hittades inte")


def assert_scoped_object(db: Session, user: User, obj, *, detail: str = "Objekt hittades inte"):
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=detail)
    assert_user_can_access_business(db, user, getattr(obj, "business_id", None))
    return obj


def scoped_get(db: Session, model, object_id: int, user: User, *, detail: str = "Objekt hittades inte"):
    return assert_scoped_object(db, user, db.get(model, object_id), detail=detail)


def related_business_ids(*objects) -> set[int]:
    return {
        int(getattr(obj, "business_id"))
        for obj in objects
        if obj is not None and getattr(obj, "business_id", None) is not None
    }


def resolve_write_business_id(
    db: Session,
    user: User,
    *,
    requested_business_id: int | None = None,
    related_ids: set[int] | None = None,
) -> int | None:
    if requested_business_id is not None and not isinstance(requested_business_id, int):
        requested_business_id = None
    ids = set(related_ids or set())
    if requested_business_id is not None:
        if not db.get(Business, requested_business_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Verksamhet hittades inte")
        ids.add(requested_business_id)

    if len(ids) > 1:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Objekten tillhör olika verksamheter")

    inferred = next(iter(ids), None)
    if is_super_user(user):
        if inferred is not None:
            return inferred
        if default_business(db) is None:
            return None
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Super User måste välja verksamhet")

    business_id = user_business_id(db, user)
    if inferred is not None and business_id is not None and inferred != business_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Objekt hittades inte")
    return business_id


def business_for_area(db: Session, area_id: int | None) -> Area | None:
    return db.get(Area, area_id) if area_id is not None else None


def business_for_activity(db: Session, activity_id: int | None) -> Activity | None:
    return db.get(Activity, activity_id) if activity_id is not None else None


def business_for_person(db: Session, person_id: int | None) -> Person | None:
    return db.get(Person, person_id) if person_id is not None else None

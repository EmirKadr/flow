from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .business_scope import default_business
from .models import AppSetting
from .user_access import normalize_role_view_access_ids, normalize_role_view_id


LOCK_FOREIGN_SCHEDULE_CELLS_KEY = "lock_foreign_schedule_cells"
SIDEBAR_LAYOUT_KEY = "sidebar_layout"
ROLE_VIEW_ACCESS_KEY = "role_view_access"


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "ja"}


def _business_id(db: Session, business_id: int | None = None) -> int:
    if business_id is not None:
        return business_id
    try:
        business = default_business(db)
        return int(business.id) if business is not None else 1
    except Exception:
        return 1


def _get_setting(db: Session, key: str, business_id: int | None = None) -> AppSetting | None:
    return db.get(AppSetting, {"business_id": _business_id(db, business_id), "key": key})


def get_bool_setting(db: Session, key: str, *, default: bool = False, business_id: int | None = None) -> bool:
    row = _get_setting(db, key, business_id)
    return _parse_bool(row.value if row else None, default=default)


def set_bool_setting(
    db: Session,
    key: str,
    value: bool,
    *,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    scoped_business_id = _business_id(db, business_id)
    row = _get_setting(db, key, scoped_business_id)
    if row is None:
        row = AppSetting(business_id=scoped_business_id, key=key, value=_bool_text(value), updated_by=user_id)
        db.add(row)
    else:
        row.value = _bool_text(value)
        row.updated_by = user_id
    db.flush()
    return row


def get_json_setting(db: Session, key: str, *, default=None, business_id: int | None = None):
    row = _get_setting(db, key, business_id)
    if row is None:
        return default
    try:
        return json.loads(row.value)
    except json.JSONDecodeError:
        return default


def set_json_setting(
    db: Session,
    key: str,
    value,
    *,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    scoped_business_id = _business_id(db, business_id)
    row = _get_setting(db, key, scoped_business_id)
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if row is None:
        row = AppSetting(business_id=scoped_business_id, key=key, value=text, updated_by=user_id)
        db.add(row)
    else:
        row.value = text
        row.updated_by = user_id
    db.flush()
    return row


def get_lock_foreign_schedule_cells(db: Session, business_id: int | None = None) -> bool:
    return get_bool_setting(db, LOCK_FOREIGN_SCHEDULE_CELLS_KEY, default=False, business_id=business_id)


def set_lock_foreign_schedule_cells(
    db: Session,
    value: bool,
    *,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    return set_bool_setting(db, LOCK_FOREIGN_SCHEDULE_CELLS_KEY, value, user_id=user_id, business_id=business_id)


def get_sidebar_layout(db: Session, business_id: int | None = None) -> list[dict]:
    value = get_json_setting(db, SIDEBAR_LAYOUT_KEY, default=[], business_id=business_id)
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value:
        if not isinstance(item, dict):
            continue
        parent_id = item.get("parent_id")
        normalized.append({
            **item,
            "id": normalize_role_view_id(item.get("id")),
            "parent_id": normalize_role_view_id(parent_id) if parent_id else None,
        })
    return normalized


def set_sidebar_layout(
    db: Session,
    items: list[dict],
    *,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    return set_json_setting(db, SIDEBAR_LAYOUT_KEY, items, user_id=user_id, business_id=business_id)


def get_role_view_access(db: Session, business_id: int | None = None) -> dict:
    value = get_json_setting(db, ROLE_VIEW_ACCESS_KEY, default={}, business_id=business_id)
    return normalize_role_view_access_ids(value) if isinstance(value, dict) else {}


def set_role_view_access(
    db: Session,
    access: dict,
    *,
    user_id: int | None = None,
    business_id: int | None = None,
) -> AppSetting:
    return set_json_setting(db, ROLE_VIEW_ACCESS_KEY, access, user_id=user_id, business_id=business_id)

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .models import AppSetting


LOCK_FOREIGN_SCHEDULE_CELLS_KEY = "lock_foreign_schedule_cells"
SIDEBAR_LAYOUT_KEY = "sidebar_layout"


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "ja"}


def get_bool_setting(db: Session, key: str, *, default: bool = False) -> bool:
    row = db.get(AppSetting, key)
    return _parse_bool(row.value if row else None, default=default)


def set_bool_setting(db: Session, key: str, value: bool, *, user_id: int | None = None) -> AppSetting:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=_bool_text(value), updated_by=user_id)
        db.add(row)
    else:
        row.value = _bool_text(value)
        row.updated_by = user_id
    db.flush()
    return row


def get_json_setting(db: Session, key: str, *, default=None):
    row = db.get(AppSetting, key)
    if row is None:
        return default
    try:
        return json.loads(row.value)
    except json.JSONDecodeError:
        return default


def set_json_setting(db: Session, key: str, value, *, user_id: int | None = None) -> AppSetting:
    row = db.get(AppSetting, key)
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if row is None:
        row = AppSetting(key=key, value=text, updated_by=user_id)
        db.add(row)
    else:
        row.value = text
        row.updated_by = user_id
    db.flush()
    return row


def get_lock_foreign_schedule_cells(db: Session) -> bool:
    return get_bool_setting(db, LOCK_FOREIGN_SCHEDULE_CELLS_KEY, default=False)


def set_lock_foreign_schedule_cells(db: Session, value: bool, *, user_id: int | None = None) -> AppSetting:
    return set_bool_setting(db, LOCK_FOREIGN_SCHEDULE_CELLS_KEY, value, user_id=user_id)


def get_sidebar_layout(db: Session) -> list[dict]:
    value = get_json_setting(db, SIDEBAR_LAYOUT_KEY, default=[])
    return value if isinstance(value, list) else []


def set_sidebar_layout(db: Session, items: list[dict], *, user_id: int | None = None) -> AppSetting:
    return set_json_setting(db, SIDEBAR_LAYOUT_KEY, items, user_id=user_id)

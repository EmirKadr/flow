from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..audit import log as audit_log
from ..deps import get_current_user, get_db, require_view_access
from ..models import User
from ..schemas import (
    AppSettingsOut,
    AppSettingsUpdate,
    RoleViewAccessOut,
    RoleViewAccessUpdate,
    SidebarLayoutOut,
    SidebarLayoutUpdate,
)
from ..settings_service import (
    LOCK_FOREIGN_SCHEDULE_CELLS_KEY,
    ROLE_VIEW_ACCESS_KEY,
    SIDEBAR_LAYOUT_KEY,
    get_lock_foreign_schedule_cells,
    get_role_view_access,
    get_sidebar_layout,
    set_role_view_access,
    set_lock_foreign_schedule_cells,
    set_sidebar_layout,
)
from ..user_access import BASE_ROLES, ROLE_ACCESS_LEVEL_RANK, ROLE_VIEW_IDS, normalize_role_view_id

router = APIRouter(prefix="/api/settings", tags=["settings"])

ROLE_VIEW_ACCESS_ROLES = BASE_ROLES
ROLE_VIEW_ACCESS_VIEWS = ROLE_VIEW_IDS
ROLE_VIEW_ACCESS_LEVELS = set(ROLE_ACCESS_LEVEL_RANK)


def _settings_out(db: Session) -> AppSettingsOut:
    return AppSettingsOut(
        lock_foreign_schedule_cells=get_lock_foreign_schedule_cells(db),
    )


def _sidebar_layout_out(db: Session) -> SidebarLayoutOut:
    return SidebarLayoutOut(items=get_sidebar_layout(db))


def _role_view_access_out(db: Session) -> RoleViewAccessOut:
    return RoleViewAccessOut(access=get_role_view_access(db))


def _audit_setting_change(
    db: Session,
    *,
    key: str,
    action: str,
    old_value: dict,
    new_value: dict,
    user_id: int,
) -> None:
    if old_value == new_value:
        return
    audit_log(
        db,
        entity_type="app_setting",
        entity_id=0,
        action=action,
        old_value={"key": key, "value": old_value},
        new_value={"key": key, "value": new_value},
        user_id=user_id,
    )


def _clean_sidebar_layout(payload: SidebarLayoutUpdate) -> list[dict]:
    seen: set[str] = set()
    cleaned: list[dict] = []
    for item in payload.items:
        item_id = normalize_role_view_id(item.id)
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        heading = item.heading.strip()[:80]
        parent_id = normalize_role_view_id(item.parent_id) if item.parent_id else None
        cleaned.append({
            "id": item_id,
            "heading": heading,
            "parent_id": parent_id if parent_id and parent_id != item_id else None,
        })

    ids = {item["id"] for item in cleaned}
    for item in cleaned:
        if item["parent_id"] not in ids:
            item["parent_id"] = None
    for item in cleaned:
        visited = {item["id"]}
        parent_id = item["parent_id"]
        while parent_id:
            if parent_id in visited:
                item["parent_id"] = None
                break
            visited.add(parent_id)
            parent = next((candidate for candidate in cleaned if candidate["id"] == parent_id), None)
            parent_id = parent["parent_id"] if parent else None
    return cleaned


def _clean_role_view_access(payload: RoleViewAccessUpdate) -> dict[str, dict[str, str]]:
    cleaned: dict[str, dict[str, str]] = {}
    for role, views in (payload.access or {}).items():
        role_key = role.strip()
        if role_key not in ROLE_VIEW_ACCESS_ROLES or not isinstance(views, dict):
            continue
        role_views: dict[str, str] = {}
        for view_id, level in views.items():
            view_key = normalize_role_view_id(view_id)
            level_key = level.strip()
            if view_key not in ROLE_VIEW_ACCESS_VIEWS or level_key not in ROLE_VIEW_ACCESS_LEVELS:
                continue
            role_views[view_key] = level_key
        cleaned[role_key] = role_views
    return cleaned


@router.get("", response_model=AppSettingsOut)
def get_app_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_view_access("appSettings", "view")),
) -> AppSettingsOut:
    return _settings_out(db)


@router.put("", response_model=AppSettingsOut)
def update_app_settings(
    payload: AppSettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("appSettings", "edit")),
) -> AppSettingsOut:
    before = _settings_out(db).model_dump()
    set_lock_foreign_schedule_cells(
        db,
        payload.lock_foreign_schedule_cells,
        user_id=admin.id,
    )
    after = _settings_out(db).model_dump()
    _audit_setting_change(
        db,
        key=LOCK_FOREIGN_SCHEDULE_CELLS_KEY,
        action="update_lock",
        old_value=before,
        new_value=after,
        user_id=admin.id,
    )
    db.commit()
    return _settings_out(db)


@router.get("/sidebar", response_model=SidebarLayoutOut)
def get_sidebar_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SidebarLayoutOut:
    return _sidebar_layout_out(db)


@router.put("/sidebar", response_model=SidebarLayoutOut)
def update_sidebar_settings(
    payload: SidebarLayoutUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("sidebarLayout", "edit")),
) -> SidebarLayoutOut:
    before = {"items": get_sidebar_layout(db)}
    set_sidebar_layout(db, _clean_sidebar_layout(payload), user_id=admin.id)
    after = {"items": get_sidebar_layout(db)}
    _audit_setting_change(
        db,
        key=SIDEBAR_LAYOUT_KEY,
        action="update_sidebar_layout",
        old_value=before,
        new_value=after,
        user_id=admin.id,
    )
    db.commit()
    return _sidebar_layout_out(db)


@router.get("/role-access", response_model=RoleViewAccessOut)
def get_role_access_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> RoleViewAccessOut:
    return _role_view_access_out(db)


@router.put("/role-access", response_model=RoleViewAccessOut)
def update_role_access_settings(
    payload: RoleViewAccessUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("roleAccess", "edit")),
) -> RoleViewAccessOut:
    before = {"access": get_role_view_access(db)}
    set_role_view_access(db, _clean_role_view_access(payload), user_id=admin.id)
    after = {"access": get_role_view_access(db)}
    _audit_setting_change(
        db,
        key=ROLE_VIEW_ACCESS_KEY,
        action="update_role_access",
        old_value=before,
        new_value=after,
        user_id=admin.id,
    )
    db.commit()
    return _role_view_access_out(db)

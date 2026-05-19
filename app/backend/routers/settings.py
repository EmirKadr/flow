from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, require_admin, require_super_user
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
    get_lock_foreign_schedule_cells,
    get_role_view_access,
    get_sidebar_layout,
    set_role_view_access,
    set_lock_foreign_schedule_cells,
    set_sidebar_layout,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

ROLE_VIEW_ACCESS_ROLES = {
    "leader",
    "staffing_manager",
    "admin",
    "warehouse_clerk",
    "article_placer",
    "viewer",
}
ROLE_VIEW_ACCESS_VIEWS = {
    "schedule",
    "overview",
    "productivity",
    "allocationUploads",
    "allocationProcess",
    "allocationSplit",
    "allocationTrace",
    "persons",
    "stallen",
    "analytics",
    "users",
}
ROLE_VIEW_ACCESS_LEVELS = {"none", "view", "edit"}


def _settings_out(db: Session) -> AppSettingsOut:
    return AppSettingsOut(
        lock_foreign_schedule_cells=get_lock_foreign_schedule_cells(db),
    )


def _sidebar_layout_out(db: Session) -> SidebarLayoutOut:
    return SidebarLayoutOut(items=get_sidebar_layout(db))


def _role_view_access_out(db: Session) -> RoleViewAccessOut:
    return RoleViewAccessOut(access=get_role_view_access(db))


def _clean_sidebar_layout(payload: SidebarLayoutUpdate) -> list[dict]:
    seen: set[str] = set()
    cleaned: list[dict] = []
    for item in payload.items:
        item_id = item.id.strip()
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        heading = item.heading.strip()[:80]
        parent_id = item.parent_id.strip() if item.parent_id else None
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
            view_key = view_id.strip()
            level_key = level.strip()
            if view_key not in ROLE_VIEW_ACCESS_VIEWS or level_key not in ROLE_VIEW_ACCESS_LEVELS:
                continue
            role_views[view_key] = level_key
        cleaned[role_key] = role_views
    return cleaned


@router.get("", response_model=AppSettingsOut)
def get_app_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> AppSettingsOut:
    return _settings_out(db)


@router.put("", response_model=AppSettingsOut)
def update_app_settings(
    payload: AppSettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AppSettingsOut:
    set_lock_foreign_schedule_cells(
        db,
        payload.lock_foreign_schedule_cells,
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
    admin: User = Depends(require_super_user),
) -> SidebarLayoutOut:
    set_sidebar_layout(db, _clean_sidebar_layout(payload), user_id=admin.id)
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
    admin: User = Depends(require_super_user),
) -> RoleViewAccessOut:
    set_role_view_access(db, _clean_role_view_access(payload), user_id=admin.id)
    db.commit()
    return _role_view_access_out(db)

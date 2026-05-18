from __future__ import annotations

from .config import settings
from .models import User
from .schemas import UserAdminOut, UserOut


SUPER_USER_ROLE = "super_user"
LEGACY_SUPER_USER_ROLE = "super" + "_admin"
VIEWER_ROLE = "viewer"
STAFFING_MANAGER_ROLE = "staffing_manager"
WAREHOUSE_CLERK_ROLE = "warehouse_clerk"
ARTICLE_PLACER_ROLE = "article_placer"
ADMIN_ROLES = {"admin", SUPER_USER_ROLE, LEGACY_SUPER_USER_ROLE}
EDITOR_ROLES = {"leader", STAFFING_MANAGER_ROLE, *ADMIN_ROLES}
ALLOCATION_TOOL_ROLES = {WAREHOUSE_CLERK_ROLE, ARTICLE_PLACER_ROLE}
PLANNING_VIEW_ROLES = {VIEWER_ROLE, *EDITOR_ROLES}
BASE_ROLES = {"admin", "leader", STAFFING_MANAGER_ROLE, VIEWER_ROLE, WAREHOUSE_CLERK_ROLE, ARTICLE_PLACER_ROLE}


def user_roles(user: User) -> list[str]:
    raw_roles = user.roles if isinstance(getattr(user, "roles", None), list) else []
    roles: list[str] = []
    for role in [*raw_roles, user.role]:
        normalized = str(role or "").strip().lower()
        if normalized and normalized not in roles:
            roles.append(normalized)
    return roles or ["leader"]


def primary_role(roles: list[str]) -> str:
    for candidate in ("admin", STAFFING_MANAGER_ROLE, "leader", WAREHOUSE_CLERK_ROLE, ARTICLE_PLACER_ROLE, VIEWER_ROLE):
        if candidate in roles:
            return candidate
    return roles[0] if roles else "leader"


def normalize_user_roles(roles: list[str] | None, fallback_role: str = "leader") -> list[str]:
    raw = roles if roles is not None else [fallback_role]
    normalized: list[str] = []
    for role in raw:
        value = str(role or "").strip().lower()
        if value in BASE_ROLES and value not in normalized:
            normalized.append(value)
    if not normalized:
        normalized = ["leader"]
    return normalized


def is_super_user(user: User) -> bool:
    roles = user_roles(user)
    if {SUPER_USER_ROLE, LEGACY_SUPER_USER_ROLE} & set(roles):
        return True
    if "admin" not in roles:
        return False
    return user.username.strip().lower() in settings.super_user_usernames


def user_needs_password_setup(user: User) -> bool:
    return user.password_hash is None or bool(user.must_change_password)


def is_viewer(user: User) -> bool:
    roles = user_roles(user)
    return VIEWER_ROLE in roles and not any(role in EDITOR_ROLES for role in roles)


def can_edit_planning(user: User) -> bool:
    return bool(set(user_roles(user)) & EDITOR_ROLES)


def can_view_planning(user: User) -> bool:
    return bool(set(user_roles(user)) & PLANNING_VIEW_ROLES)


def can_admin(user: User) -> bool:
    return bool(set(user_roles(user)) & ADMIN_ROLES)


def can_use_allocation_tools(user: User) -> bool:
    return bool(set(user_roles(user)) & ALLOCATION_TOOL_ROLES) or is_super_user(user)


def can_use_allocation_process(user: User) -> bool:
    return is_super_user(user)


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=primary_role(user_roles(user)),
        roles=[role for role in user_roles(user) if role in BASE_ROLES],
        area_id=user.area_id,
        must_change_password=user_needs_password_setup(user),
        is_super_user=is_super_user(user),
    )


def user_admin_out(user: User) -> UserAdminOut:
    return UserAdminOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=primary_role(user_roles(user)),
        roles=[role for role in user_roles(user) if role in BASE_ROLES],
        area_id=user.area_id,
        is_active=user.is_active,
        must_change_password=user_needs_password_setup(user),
        created_at=user.created_at,
        is_super_user=is_super_user(user),
    )

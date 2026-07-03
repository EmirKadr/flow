from __future__ import annotations

from .config import settings
from .models import User
from .schemas import UserAdminOut, UserOut


SUPER_USER_ROLE = "super_user"
LEGACY_SUPER_USER_ROLE = "super" + "_admin"
DEMO_ROLE = "demo"
VIEWER_ROLE = "viewer"
STAFFING_MANAGER_ROLE = "staffing_manager"
WAREHOUSE_CLERK_ROLE = "warehouse_clerk"
ARTICLE_PLACER_ROLE = "article_placer"
PERSON_ROLE = "person"
ADMIN_ROLES = {"admin", SUPER_USER_ROLE, LEGACY_SUPER_USER_ROLE}
EDITOR_ROLES = {"leader", STAFFING_MANAGER_ROLE, *ADMIN_ROLES}
PERSON_SORT_ORDER_ROLES = {STAFFING_MANAGER_ROLE, "admin"}
ALLOCATION_TOOL_ROLES = {WAREHOUSE_CLERK_ROLE, ARTICLE_PLACER_ROLE}
PLANNING_VIEW_ROLES = {VIEWER_ROLE, *EDITOR_ROLES}
PERSONAL_VIEW_IDS = {"mySchedule", "myProductivity"}
BASE_ROLES = {"admin", "leader", STAFFING_MANAGER_ROLE, VIEWER_ROLE, WAREHOUSE_CLERK_ROLE, ARTICLE_PLACER_ROLE, PERSON_ROLE}
ROLE_VIEW_ROLES = {*BASE_ROLES, DEMO_ROLE}
ASSIGNABLE_ROLES = {*BASE_ROLES, SUPER_USER_ROLE}
ROLE_ACCESS_LEVEL_RANK = {"none": 0, "view": 1, "edit": 2}
ROLE_VIEW_ID_ALIASES = {
    "stallen": "activities",
    "stallenImport": "activityImport",
}
ROLE_VIEW_ORDER = (
    "mySchedule",
    "myProductivity",
    "schedule",
    "overview",
    "productivity",
    "sankeyInbound",
    "productivityFinance",
    "dataFetch",
    "mcp",
    "labelEditor",
    "allocationUploads",
    "allocationProcess",
    "allocationProcessMatrix",
    "allocationSettings",
    "allocationSplit",
    "staffingSettings",
    "productivityFinanceSettings",
    "persons",
    "personSortOrder",
    "personImport",
    "activities",
    "activityImport",
    "areas",
    "analytics",
    "meta",
    "archiveStatus",
    "users",
    "userImport",
    "businesses",
    "appSettings",
    "sidebarLayout",
    "roleAccess",
)
ROLE_VIEW_IDS = set(ROLE_VIEW_ORDER)
ROLE_VIEW_LABELS = {
    "mySchedule": "Mitt schema",
    "myProductivity": "Min produktivitet",
    "schedule": "Bemanning",
    "overview": "Översikt",
    "productivity": "Produktivitet",
    "sankeyInbound": "Sankey - Inbound",
    "productivityFinance": "Intäkt/utgift",
    "dataFetch": "Hämta data",
    "mcp": "MCP",
    "labelEditor": "Etiketter",
    "allocationUploads": "Uppladdningar",
    "allocationProcess": "Bearbeta",
    "allocationProcessMatrix": "Bearbeta-matris",
    "allocationSettings": "Inställningar",
    "allocationSplit": "Dela",
    "staffingSettings": "Bemanningsinställningar",
    "productivityFinanceSettings": "Intäkt/utgift-inställningar",
    "persons": "Personer",
    "personSortOrder": "Personsortering",
    "personImport": "Personimport",
    "activities": "Aktiviteter",
    "activityImport": "Aktivitetsimport",
    "areas": "Områden",
    "analytics": "Historik",
    "meta": "Meta",
    "archiveStatus": "Arkivstatus",
    "users": "Användare",
    "userImport": "Användarimport",
    "businesses": "Verksamheter",
    "appSettings": "Appinställningar",
    "sidebarLayout": "Menyordning",
    "roleAccess": "Vybehörigheter",
}
ROLE_OPTION_LABELS = {
    SUPER_USER_ROLE: "Super User",
    DEMO_ROLE: "Demo",
    "leader": "Arbetsledare",
    STAFFING_MANAGER_ROLE: "Bemanningsansvarig",
    "admin": "Administratör",
    WAREHOUSE_CLERK_ROLE: "Lagerkontorist",
    ARTICLE_PLACER_ROLE: "Artikelplacerare",
    PERSON_ROLE: "Person",
    VIEWER_ROLE: "Visning",
}
ROLE_OPTION_ORDER = (
    SUPER_USER_ROLE,
    DEMO_ROLE,
    "leader",
    STAFFING_MANAGER_ROLE,
    "admin",
    WAREHOUSE_CLERK_ROLE,
    ARTICLE_PLACER_ROLE,
    PERSON_ROLE,
    VIEWER_ROLE,
)
ROLE_ACCESS_LEVEL_OPTIONS = (
    {"value": "none", "label": "Ingen"},
    {"value": "view", "label": "Visa"},
    {"value": "edit", "label": "Redigera"},
)
SIDEBAR_DEFAULT_LAYOUT = (
    {"id": "staffing"},
    {"id": "tools"},
    {"id": "allocationProcess"},
    {"id": "allocationSettings"},
)
ROLE_VIEW_DEFAULT_ACCESS = {
    "leader": {
        "schedule": "edit",
        "overview": "edit",
        "persons": "edit",
        "personImport": "edit",
        "activities": "edit",
        "activityImport": "edit",
    },
    STAFFING_MANAGER_ROLE: {
        "schedule": "edit",
        "overview": "edit",
        "persons": "edit",
        "personSortOrder": "edit",
        "personImport": "edit",
        "activities": "edit",
        "activityImport": "edit",
    },
    "admin": {
        "schedule": "edit",
        "overview": "edit",
        "persons": "edit",
        "personSortOrder": "edit",
        "personImport": "edit",
        "activities": "edit",
        "activityImport": "edit",
        "areas": "edit",
        "users": "edit",
        "appSettings": "edit",
        "mcp": "edit",
        "staffingSettings": "edit",
        "allocationProcessMatrix": "edit",
        "allocationSettings": "edit",
    },
    DEMO_ROLE: {
        "schedule": "edit",
        "overview": "edit",
        "persons": "edit",
        "personSortOrder": "edit",
        "personImport": "edit",
        "activities": "edit",
        "activityImport": "edit",
        "areas": "edit",
        "users": "edit",
        "appSettings": "edit",
        "mcp": "edit",
        "staffingSettings": "edit",
        "allocationProcessMatrix": "edit",
        "allocationSettings": "edit",
    },
    WAREHOUSE_CLERK_ROLE: {
        "allocationUploads": "edit",
        "allocationSplit": "edit",
    },
    ARTICLE_PLACER_ROLE: {
        "allocationUploads": "edit",
        "allocationSplit": "edit",
    },
    VIEWER_ROLE: {
        "schedule": "view",
        "overview": "view",
    },
    PERSON_ROLE: {
        "mySchedule": "view",
        "myProductivity": "view",
    },
}


def user_roles(user: User) -> list[str]:
    raw_roles = user.roles if isinstance(getattr(user, "roles", None), list) else []
    roles: list[str] = []
    for role in [*raw_roles, user.role]:
        normalized = str(role or "").strip().lower()
        if normalized and normalized not in roles:
            roles.append(normalized)
    return roles or ["leader"]


def primary_role(roles: list[str]) -> str:
    for candidate in (SUPER_USER_ROLE, "admin", STAFFING_MANAGER_ROLE, "leader", WAREHOUSE_CLERK_ROLE, ARTICLE_PLACER_ROLE, VIEWER_ROLE, PERSON_ROLE):
        if candidate in roles:
            return candidate
    return roles[0] if roles else "leader"


def normalize_user_roles(roles: list[str] | None, fallback_role: str = "leader") -> list[str]:
    raw = roles if roles is not None else [fallback_role]
    normalized: list[str] = []
    for role in raw:
        value = str(role or "").strip().lower()
        if value in ASSIGNABLE_ROLES and value not in normalized:
            normalized.append(value)
    if not normalized:
        normalized = ["leader"]
    return normalized


def role_view_default_access() -> dict[str, dict[str, str]]:
    return {role: dict(ROLE_VIEW_DEFAULT_ACCESS.get(role, {})) for role in ROLE_VIEW_ROLES}


def feature_registry_payload() -> dict:
    default_access = role_view_default_access()
    default_access[SUPER_USER_ROLE] = {view_id: "edit" for view_id in ROLE_VIEW_ORDER}
    return {
        "version": 1,
        "views": [
            {"id": view_id, "label": ROLE_VIEW_LABELS.get(view_id, view_id)}
            for view_id in ROLE_VIEW_ORDER
        ],
        "roles": [
            {
                "value": role,
                "label": ROLE_OPTION_LABELS.get(role, role),
                **({"lockedLevel": "edit"} if role == SUPER_USER_ROLE else {}),
            }
            for role in ROLE_OPTION_ORDER
        ],
        "levels": [dict(option) for option in ROLE_ACCESS_LEVEL_OPTIONS],
        "aliases": dict(ROLE_VIEW_ID_ALIASES),
        "default_access": default_access,
        "sidebar_default_layout": [dict(item) for item in SIDEBAR_DEFAULT_LAYOUT],
    }


def normalize_role_view_id(view_id: str | None) -> str:
    view_key = str(view_id or "").strip()
    return ROLE_VIEW_ID_ALIASES.get(view_key, view_key)


def normalize_role_view_access_ids(access: dict | None) -> dict[str, dict[str, str]]:
    incoming = access if isinstance(access, dict) else {}
    normalized: dict[str, dict[str, str]] = {}
    for role, views in incoming.items():
        role_key = str(role or "").strip()
        if not isinstance(views, dict):
            continue
        role_views = normalized.setdefault(role_key, {})
        for view_id, level in views.items():
            role_views[normalize_role_view_id(str(view_id or ""))] = str(level or "").strip()
    return normalized


def normalize_role_view_access(access: dict | None) -> dict[str, dict[str, str]]:
    normalized = role_view_default_access()
    incoming = access if isinstance(access, dict) else {}
    for role, views in incoming.items():
        role_key = str(role or "").strip()
        if role_key not in ROLE_VIEW_ROLES or not isinstance(views, dict):
            continue
        role_views = normalized.setdefault(role_key, {})
        for view_id, level in views.items():
            view_key = normalize_role_view_id(str(view_id or ""))
            level_key = str(level or "").strip()
            if view_key in ROLE_VIEW_IDS and level_key in ROLE_ACCESS_LEVEL_RANK:
                role_views[view_key] = level_key
    return normalized


def is_super_user(user: User) -> bool:
    roles = user_roles(user)
    if {SUPER_USER_ROLE, LEGACY_SUPER_USER_ROLE} & set(roles):
        return True
    username = str(getattr(user, "username", "") or "").strip().lower()
    return bool(username and username in settings.super_user_usernames)


def user_needs_password_setup(user: User) -> bool:
    return user.password_hash is None or bool(user.must_change_password)


def is_viewer(user: User) -> bool:
    roles = user_roles(user)
    return VIEWER_ROLE in roles and not any(role in EDITOR_ROLES for role in roles)


def can_edit_planning(user: User) -> bool:
    return is_super_user(user) or bool(set(user_roles(user)) & EDITOR_ROLES)


def can_view_planning(user: User) -> bool:
    return is_super_user(user) or bool(set(user_roles(user)) & PLANNING_VIEW_ROLES)


def can_admin(user: User) -> bool:
    return is_super_user(user) or bool(set(user_roles(user)) & ADMIN_ROLES)


def can_sort_person_order(user: User) -> bool:
    return is_super_user(user) or is_demo_user(user) or bool(set(user_roles(user)) & PERSON_SORT_ORDER_ROLES)


def role_view_access_level(user: User, access: dict | None, view_id: str) -> str:
    if is_super_user(user):
        return "edit"
    view_key = normalize_role_view_id(view_id)
    if view_key in PERSONAL_VIEW_IDS:
        return "view" if PERSON_ROLE in user_roles(user) else "none"
    normalized = normalize_role_view_access(access)
    best = "none"
    roles = user_roles(user)
    if is_demo_user(user) and DEMO_ROLE not in roles:
        roles = [*roles, DEMO_ROLE]
    for role in roles:
        role_access = normalized.get(role, {})
        level = role_access.get(view_key)
        level = level or "none"
        if ROLE_ACCESS_LEVEL_RANK.get(level, 0) > ROLE_ACCESS_LEVEL_RANK.get(best, 0):
            best = level
    return best


def can_access_view(user: User, access: dict | None, view_id: str, min_level: str = "view") -> bool:
    wanted = ROLE_ACCESS_LEVEL_RANK.get(min_level, ROLE_ACCESS_LEVEL_RANK["view"])
    actual = ROLE_ACCESS_LEVEL_RANK.get(role_view_access_level(user, access, view_id), 0)
    return actual >= wanted


def can_view_personal_pages(user: User) -> bool:
    return is_super_user(user) or PERSON_ROLE in user_roles(user)


def can_use_allocation_tools(user: User, access: dict | None = None) -> bool:
    return any(
        can_access_view(user, access, view_id)
        for view_id in ("allocationUploads", "allocationSplit", "allocationProcess")
    )


def can_use_allocation_process(user: User, access: dict | None = None) -> bool:
    return can_access_view(user, access, "allocationProcess", "edit")


def is_demo_user(user: User) -> bool:
    from .demo_session import DEMO_USERNAME

    username = str(getattr(user, "username", "") or "").strip().lower()
    return username == DEMO_USERNAME


def user_out(user: User) -> UserOut:
    business = getattr(user, "business", None)
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=primary_role(user_roles(user)),
        roles=[role for role in user_roles(user) if role in ASSIGNABLE_ROLES],
        business_id=user.business_id,
        business_code=getattr(business, "code", None),
        business_name=getattr(business, "name", None),
        area_id=user.area_id,
        person_id=user.person_id,
        must_change_password=user_needs_password_setup(user),
        is_super_user=is_super_user(user),
        is_demo=is_demo_user(user),
    )


def user_admin_out(user: User) -> UserAdminOut:
    business = getattr(user, "business", None)
    return UserAdminOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=primary_role(user_roles(user)),
        roles=[role for role in user_roles(user) if role in ASSIGNABLE_ROLES],
        business_id=user.business_id,
        business_code=getattr(business, "code", None),
        business_name=getattr(business, "name", None),
        area_id=user.area_id,
        person_id=user.person_id,
        is_active=user.is_active,
        must_change_password=user_needs_password_setup(user),
        created_at=user.created_at,
        is_super_user=is_super_user(user),
        is_demo=is_demo_user(user),
    )

import re
from pathlib import Path

from app.backend.user_access import (
    BASE_ROLES,
    ROLE_ACCESS_LEVEL_RANK,
    ROLE_VIEW_DEFAULT_ACCESS,
    ROLE_VIEW_ID_ALIASES,
    ROLE_VIEW_IDS,
    ROLE_VIEW_ROLES,
)
from tools.terminology_contracts import forbidden_terms_in_text, role_access_required_terms


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "app" / "frontend"


def read_frontend(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def extract_const_block(source: str, const_name: str, opener: str, closer: str) -> str:
    marker = f"const {const_name} = {opener}"
    start = source.find(marker)
    assert start != -1, f"Missing const {const_name}"
    index = start + len(marker)
    depth = 1
    while index < len(source):
        char = source[index]
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return source[start + len(marker) : index]
        index += 1
    raise AssertionError(f"Unclosed const {const_name}")


def extract_js_string_array(source: str, const_name: str) -> list[str]:
    block = extract_const_block(source, const_name, "[", "]")
    return re.findall(r'"([^"]+)"', block)


def extract_ids_from_object_array(source: str, const_name: str) -> list[str]:
    block = extract_const_block(source, const_name, "[", "]")
    return re.findall(r'\bid:\s*"([^"]+)"', block)


def extract_labels_from_object_array(source: str, const_name: str) -> list[str]:
    block = extract_const_block(source, const_name, "[", "]")
    return re.findall(r'\blabel:\s*"([^"]+)"', block)


def extract_values_from_object_array(source: str, const_name: str) -> list[str]:
    block = extract_const_block(source, const_name, "[", "]")
    return re.findall(r'\bvalue:\s*"([^"]+)"', block)


def extract_js_alias_object(source: str, const_name: str) -> dict[str, str]:
    block = extract_const_block(source, const_name, "{", "}")
    return dict(re.findall(r'\b([A-Za-z0-9_]+):\s*"([^"]+)"', block))


def extract_js_nested_access_object(source: str, const_name: str) -> dict[str, dict[str, str]]:
    block = extract_const_block(source, const_name, "{", "}")
    access: dict[str, dict[str, str]] = {}
    for role, role_block in re.findall(r"\b([A-Za-z0-9_]+):\s*\{([^}]*)\}", block):
        access[role] = dict(re.findall(r'\b([A-Za-z0-9_]+):\s*"([^"]+)"', role_block))
    return access


def test_backend_frontend_and_user_admin_view_ids_match():
    common = read_frontend("js/common.js")
    users = read_frontend("js/users.js")

    common_view_ids = extract_js_string_array(common, "ROLE_VIEW_IDS")
    admin_view_ids = extract_ids_from_object_array(users, "VIEW_ACCESS_OPTIONS")

    assert common_view_ids == admin_view_ids
    assert set(common_view_ids) == ROLE_VIEW_IDS
    assert "activities" in common_view_ids
    assert "stallen" not in common_view_ids
    assert "stallenImport" not in common_view_ids


def test_user_admin_role_access_labels_follow_terminology_contracts():
    users = read_frontend("js/users.js")
    labels = extract_labels_from_object_array(users, "VIEW_ACCESS_OPTIONS")
    label_text = "\n".join(labels)

    for expected in role_access_required_terms():
        assert expected in labels
    assert forbidden_terms_in_text(label_text) == []


def test_sidebar_layout_only_uses_known_canonical_views():
    common = read_frontend("js/common.js")
    sidebar_view_ids = extract_ids_from_object_array(common, "SIDEBAR_DEFAULT_LAYOUT")

    assert set(sidebar_view_ids) <= ROLE_VIEW_IDS
    assert "activities" in sidebar_view_ids
    assert "stallen" not in sidebar_view_ids
    assert len(sidebar_view_ids) == len(set(sidebar_view_ids))


def test_legacy_view_aliases_match_between_frontend_and_backend():
    common = read_frontend("js/common.js")
    aliases = extract_js_alias_object(common, "VIEW_ID_ALIASES")

    assert aliases == ROLE_VIEW_ID_ALIASES
    assert set(aliases.values()) <= ROLE_VIEW_IDS


def test_role_default_access_matches_between_frontend_and_backend():
    common = read_frontend("js/common.js")
    frontend_access = extract_js_nested_access_object(common, "ROLE_VIEW_DEFAULT_ACCESS")

    assert frontend_access == ROLE_VIEW_DEFAULT_ACCESS
    assert set(frontend_access) <= ROLE_VIEW_ROLES
    for role_access in frontend_access.values():
        assert set(role_access) <= ROLE_VIEW_IDS
        assert set(role_access.values()) <= set(ROLE_ACCESS_LEVEL_RANK)


def test_productivity_page_uses_view_access_not_super_user_gate():
    productivity = read_frontend("js/productivity.js")

    assert 'initPage("productivity")' in productivity
    assert 'initPage("productivity", { requireSuperUser: true })' not in productivity


def test_role_lists_match_backend_roles_and_show_virtual_access_roles():
    common = read_frontend("js/common.js")
    users = read_frontend("js/users.js")

    common_roles = extract_values_from_object_array(common, "ROLE_VIEW_ROLES")
    users_roles = extract_values_from_object_array(users, "ROLE_OPTIONS")

    assert set(users_roles) == BASE_ROLES
    assert set(common_roles) == ROLE_VIEW_ROLES | {"super_user"}
    assert common_roles[:2] == ["super_user", "demo"]
    assert 'const SUPER_USER_ROLE_OPTION = { value: "super_user"' in users


def test_activities_route_contract_is_canonical_with_legacy_redirect_page():
    common = read_frontend("js/common.js")
    activities_html = read_frontend("aktiviteter.html")
    legacy_html = read_frontend("stallen.html")
    activities_js = read_frontend("js/activities.js")

    assert 'id: "activities"' in common
    assert 'href: "/aktiviteter.html"' in common
    assert 'visible: canViewPage(user, "activities")' in common
    assert 'activePage === "stallen"' not in common
    assert 'initPage("activities")' in activities_js
    assert "/js/activities.js" in activities_html
    assert 'url=/aktiviteter.html' in legacy_html
    assert "window.location.replace" in legacy_html
    assert "/aktiviteter.html?legacy=stallen" in legacy_html

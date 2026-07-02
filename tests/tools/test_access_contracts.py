import re
from pathlib import Path

from app.backend.user_access import (
    BASE_ROLES,
    ROLE_ACCESS_LEVEL_RANK,
    ROLE_VIEW_DEFAULT_ACCESS,
    ROLE_VIEW_ID_ALIASES,
    ROLE_VIEW_IDS,
    ROLE_VIEW_ORDER,
    ROLE_VIEW_ROLES,
    feature_registry_payload,
)
from tools.terminology_contracts import forbidden_terms_in_text, role_access_required_terms


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "app" / "frontend"
COMMON_SCRIPT_FILES = [
    "js/common/foundation.js",
    "js/common/theme.js",
    "js/common/area_focus.js",
    "js/common/runtime.js",
    "js/common/app_log.js",
    "js/common/telemetry.js",
    "js/common/access.js",
    "js/common/sidebar.js",
    "js/common/uploads.js",
    "js/common/demo_prefetch_init.js",
    "js/common/import_tools.js",
    "js/common/table_sort.js",
    "js/common/date_state.js",
    "js/common.js",
]
ALLOCATION_SCRIPT_FILES = [
    "js/allocation/state.js",
    "js/allocation/state_carrier_clusters.js",
    "js/allocation/state_filters.js",
    "js/allocation/files.js",
    "js/allocation/api.js",
    "js/allocation/uploads_view.js",
    "js/allocation/results.js",
    "js/allocation/results_flows.js",
    "js/allocation/results_warehouse_map.js",
    "js/allocation/results_carrier_clusters.js",
    "js/allocation/process_view.js",
    "js/allocation/process_matrix.js",
    "js/allocation/map_settings.js",
    "js/allocation/settings_view.js",
    "js/allocation/split_view.js",
    "js/allocation/boot.js",
    "js/allocation_tools.js",
]


def read_frontend(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def read_allocation_frontend() -> str:
    return "\n".join(read_frontend(path) for path in ALLOCATION_SCRIPT_FILES)


def read_common_frontend() -> str:
    return "\n".join(read_frontend(path) for path in COMMON_SCRIPT_FILES)


def extract_const_block(source: str, const_name: str, opener: str, closer: str) -> str:
    markers = [f"const {const_name} = {opener}", f"let {const_name} = {opener}"]
    marker = next((candidate for candidate in markers if candidate in source), "")
    start = source.find(marker) if marker else -1
    assert start != -1, f"Missing declaration {const_name}"
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
    common = read_common_frontend()
    users = read_frontend("js/users.js")

    common_view_ids = extract_js_string_array(common, "ROLE_VIEW_IDS")
    admin_view_ids = extract_ids_from_object_array(users, "VIEW_ACCESS_OPTIONS")

    assert common_view_ids == admin_view_ids
    assert set(common_view_ids) == ROLE_VIEW_IDS
    assert "activities" in common_view_ids
    assert "stallen" not in common_view_ids
    assert "stallenImport" not in common_view_ids


def test_backend_feature_registry_matches_frontend_access_contracts():
    common = read_common_frontend()
    users = read_frontend("js/users.js")
    registry = feature_registry_payload()

    common_view_ids = extract_js_string_array(common, "ROLE_VIEW_IDS")
    admin_view_ids = extract_ids_from_object_array(users, "VIEW_ACCESS_OPTIONS")
    registry_view_ids = [view["id"] for view in registry["views"]]
    registry_view_labels = [view["label"] for view in registry["views"]]
    registry_roles = [role["value"] for role in registry["roles"]]

    assert registry_view_ids == list(ROLE_VIEW_ORDER)
    assert registry_view_ids == common_view_ids == admin_view_ids
    assert set(registry["default_access"]) == ROLE_VIEW_ROLES | {"super_user"}
    assert registry["default_access"]["super_user"] == {view_id: "edit" for view_id in registry_view_ids}
    assert registry_roles[:2] == ["super_user", "demo"]
    assert set(registry_roles) == ROLE_VIEW_ROLES | {"super_user"}
    assert "Vybehörigheter" in registry_view_labels
    assert "feature-registry" in users


def test_user_admin_role_access_labels_follow_terminology_contracts():
    users = read_frontend("js/users.js")
    labels = extract_labels_from_object_array(users, "VIEW_ACCESS_OPTIONS")
    label_text = "\n".join(labels)

    for expected in role_access_required_terms():
        assert expected in labels
    assert forbidden_terms_in_text(label_text) == []


def test_sidebar_layout_only_uses_known_canonical_views():
    common = read_common_frontend()
    sidebar_view_ids = extract_ids_from_object_array(common, "SIDEBAR_DEFAULT_LAYOUT")
    virtual_sidebar_ids = {"tools", "staffing"}

    assert set(sidebar_view_ids) <= ROLE_VIEW_IDS | virtual_sidebar_ids
    assert "staffing" in sidebar_view_ids
    assert "tools" in sidebar_view_ids
    assert "schedule" not in sidebar_view_ids
    assert "overview" not in sidebar_view_ids
    assert "productivity" not in sidebar_view_ids
    assert "allocationSplit" not in sidebar_view_ids
    assert "labelEditor" not in sidebar_view_ids
    assert "mcp" not in sidebar_view_ids
    assert "dataFetch" not in sidebar_view_ids
    assert "activities" not in sidebar_view_ids
    assert "stallen" not in sidebar_view_ids
    assert len(sidebar_view_ids) == len(set(sidebar_view_ids))


def test_sidebar_main_menus_render_tabs_and_context_menus():
    common = read_common_frontend()
    split_html = read_frontend("dela.html")
    label_html = read_frontend("label-editor.html")
    mcp_html = read_frontend("mcp.html")
    data_fetch_html = read_frontend("hamta-data.html")
    history_html = read_frontend("historik.html")
    meta_html = read_frontend("meta.html")
    schedule_html = read_frontend("index.html")
    overview_html = read_frontend("overblick.html")
    productivity_html = read_frontend("produktivitet.html")
    sankey_html = read_frontend("sankey-inbound.html")
    activities_html = read_frontend("aktiviteter.html")
    persons_html = read_frontend("personer.html")
    users_html = read_frontend("anvandare.html")
    businesses_html = read_frontend("verksamheter.html")
    my_schedule_html = read_frontend("mitt-schema.html")
    my_productivity_html = read_frontend("min-produktivitet.html")

    assert 'id: "staffing"' in common
    assert 'label: "Bemanning"' in common
    assert 'id: "tools"' in common
    assert 'label: "Verktyg"' in common
    assert "function sidebarToolsHref" in common
    assert "function sidebarStaffingHref" in common
    assert "function sidebarSettingsHref" in common
    assert "contextMenuViewIds: SIDEBAR_TOOLS_TAB_VIEW_IDS" in common
    assert "contextMenuViewIds: SIDEBAR_STAFFING_TAB_VIEW_IDS" in common
    assert "contextMenuViewIds: SIDEBAR_SETTINGS_TAB_VIEW_IDS" in common
    assert '"allocationMapSettings"' in common
    assert 'href: SIDEBAR_VIEW_HREFS.allocationMapSettings' in common
    assert 'href: SIDEBAR_VIEW_HREFS.allocationProcessMatrix' in common
    assert 'href: SIDEBAR_VIEW_HREFS.staffingSettings' in common
    assert 'href: SIDEBAR_VIEW_HREFS.productivityFinanceSettings' in common
    assert '"/installningar.html?tab=map"' in common
    assert '"/installningar.html?tab=process-matrix"' in common
    assert '"/installningar.html?tab=staffing"' in common
    assert '"/installningar.html?tab=productivity-finance"' in common
    assert "function openSidebarContextMenu" in common
    assert 'data-sidebar-context-menu="true"' in common
    assert ".sidebar-context-menu" in read_frontend("css/styles.css")
    assert 'sidebar: false' in common
    for html in (split_html, label_html, mcp_html, data_fetch_html, history_html, meta_html):
        assert 'data-tools-tab-view="allocationSplit"' in html
        assert 'data-tools-tab-view="labelEditor"' in html
        assert 'data-tools-tab-view="mcp"' in html
        assert 'data-tools-tab-view="dataFetch"' in html
        assert 'data-tools-tab-view="analytics"' in html
        assert 'data-tools-tab-view="meta"' in html
    staffing_html_pages = (
        schedule_html,
        overview_html,
        productivity_html,
        sankey_html,
        activities_html,
        persons_html,
        users_html,
        businesses_html,
        my_schedule_html,
        my_productivity_html,
    )
    for html in staffing_html_pages:
        assert 'data-staffing-tab-view="schedule"' in html
        assert 'data-staffing-tab-view="overview"' in html
        assert 'data-staffing-tab-view="productivity"' in html
        assert 'data-staffing-tab-view="sankeyInbound"' in html
        assert 'data-staffing-tab-view="activities"' in html
        assert 'data-staffing-tab-view="persons"' in html
        assert 'data-staffing-tab-view="users"' in html
        assert 'data-staffing-tab-view="businesses"' in html
        assert 'data-staffing-tab-view="mySchedule"' in html
        assert 'data-staffing-tab-view="myProductivity"' in html
    assert 'class="staffing-tab active" href="/sankey-inbound.html" aria-current="page" data-staffing-tab-view="sankeyInbound"' in sankey_html
    assert "function syncViewTabs" in common
    assert "function syncToolsTabs" in common


def test_legacy_view_aliases_match_between_frontend_and_backend():
    common = read_common_frontend()
    aliases = extract_js_alias_object(common, "VIEW_ID_ALIASES")

    assert aliases == ROLE_VIEW_ID_ALIASES
    assert set(aliases.values()) <= ROLE_VIEW_IDS


def test_role_default_access_matches_between_frontend_and_backend():
    common = read_common_frontend()
    frontend_access = extract_js_nested_access_object(common, "ROLE_VIEW_DEFAULT_ACCESS")

    assert frontend_access == ROLE_VIEW_DEFAULT_ACCESS
    assert set(frontend_access) <= ROLE_VIEW_ROLES
    for role_access in frontend_access.values():
        assert set(role_access) <= ROLE_VIEW_IDS
        assert set(role_access.values()) <= set(ROLE_ACCESS_LEVEL_RANK)


def test_productivity_page_uses_view_access_not_super_user_gate():
    productivity = read_frontend("js/productivity_overview.js")

    assert 'initPage("productivity")' in productivity
    assert 'initPage("productivity", { requireSuperUser: true })' not in productivity


def test_role_lists_match_backend_roles_and_show_virtual_access_roles():
    common = read_common_frontend()
    users = read_frontend("js/users.js")

    common_roles = extract_values_from_object_array(common, "ROLE_VIEW_ROLES")
    users_roles = extract_values_from_object_array(users, "ROLE_OPTIONS")

    assert set(users_roles) == BASE_ROLES
    assert set(common_roles) == ROLE_VIEW_ROLES | {"super_user"}
    assert common_roles[:2] == ["super_user", "demo"]
    assert 'const SUPER_USER_ROLE_OPTION = { value: "super_user"' in users


def test_activities_route_contract_is_canonical_with_legacy_redirect_page():
    common = read_common_frontend()
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


def test_frontend_prefetch_cache_is_available_for_visible_pages_and_uploads():
    api_js = read_frontend("js/api.js")
    common = read_common_frontend()
    allocation = read_allocation_frontend()

    assert "prefetchGet" in api_js
    assert "clearGetCache" in api_js
    assert "sessionStorage" in api_js
    assert "flow-api-get-cache-v1" in api_js
    assert "enqueueVisiblePagePrefetches" in common
    assert "scheduleNextBackgroundPrefetch" in common
    assert "BACKGROUND_PREFETCH_ERROR_DEDUPE_MS" in common
    assert "shouldLogBackgroundPrefetchError" in common
    assert "backgroundPrefetchErrorMessage" in common
    assert 'console.warn("Bakgrundsladdning misslyckades"' in common
    assert "if (areaQuery) {" in common
    assert "`/api/schedule?year=${year}&week=${week}&weekday=${weekday}`" in common
    assert "`/api/overview?year=${year}&week=${week}`" in common
    assert "waitForBackgroundPrefetchIdle" in common
    assert "window.flowBackgroundPrefetch" in common
    assert "warmSharedAllocationMetadataCache" in common
    assert "/api/allokering/flows" in common
    assert "/api/coredata/files" in common
    assert "flow-allocation-file-metadata-v1" in allocation
    assert "restoreAllocationBootData" in allocation
    assert "Promise.all([" in allocation

import inspect
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from tools import interactive_e2e
from tools import desktop_app_probe
from tools import visual_smoke


ROOT = Path(__file__).resolve().parents[2]


def test_visual_smoke_covers_expected_routes():
    pages_by_name = {page.name: page for page in visual_smoke.PAGES}

    assert set(pages_by_name) == {
        "login",
        "bemanning",
        "oversikt",
        "produktivitet",
        "personer",
        "stallen",
        "historik",
        "anvandare",
        "uppladdningar",
        "bearbeta",
        "dela",
        "harleda",
    }
    assert pages_by_name["bemanning"].roles == ("admin", "leader", "staffing", "viewer")
    assert pages_by_name["personer"].roles == ("admin", "leader", "staffing")
    assert pages_by_name["produktivitet"].roles == ("admin",)
    assert pages_by_name["anvandare"].roles == ("admin",)
    assert pages_by_name["uppladdningar"].roles == ("admin", "warehouse", "article")
    assert pages_by_name["bearbeta"].roles == ("admin",)
    assert pages_by_name["dela"].roles == ("admin", "warehouse", "article")
    assert pages_by_name["harleda"].roles == ("admin", "warehouse", "article")


def test_visual_smoke_covers_critical_scenarios():
    state_names = {state.name for state in visual_smoke.STATES}

    assert {
        "bemanning-mestergruppen",
        "bemanning-autostore",
        "bemanning-kopiera-dag-modal",
        "bemanning-kalkyl-alla",
        "bemanning-fokus-mestergruppen",
        "oversikt-fokus-mestergruppen",
        "produktivitet-fokus-mestergruppen",
        "personer-fokus-mestergruppen",
        "stallen-fokus-mestergruppen",
        "oversikt-manad-mestergruppen",
        "personer-veckomall-modal",
        "stallen-import-hjalp",
        "stallen-redigera-aktivitet-modal",
        "anvandare-redigera-anvandare-modal",
        "historik-filter",
        "viewer-nekad-personer",
        "viewer-nekad-produktivitet",
        "leader-nekad-historik",
        "leader-nekad-produktivitet",
        "leader-nekad-uppladdningar",
        "staffing-nekad-anvandare",
        "staffing-nekad-historik",
        "staffing-nekad-produktivitet",
        "staffing-nekad-uppladdningar",
        "viewer-nekad-uppladdningar",
    }.issubset(state_names)


def test_interactive_e2e_covers_mutating_workflows():
    assert {
        "create_user",
        "edit_user",
        "toggle_user_setting",
        "toggle_user_active",
        "create_activity",
        "edit_activity",
        "deactivate_activity",
        "create_person",
        "edit_person_inline",
        "edit_person_fields_inline",
        "edit_person_week_template",
        "edit_person_hourly_schedule",
        "edit_schedule_cell",
        "split_schedule_cell",
        "copy_paste_schedule_cell",
        "copy_day",
        "clear_day",
        "undo_redo",
        "overview_edit",
        "history_filter",
        "viewer_read_only",
        "role_access_guards",
    }.issubset(set(interactive_e2e.WEB_WORKFLOW_STEPS))


def test_interactive_e2e_records_every_expected_workflow_step():
    source = inspect.getsource(interactive_e2e.InteractiveRun)
    recorded = set(re.findall(r"self\.record\(\"([^\"]+)\"", source))

    assert set(interactive_e2e.WEB_WORKFLOW_STEPS).issubset(recorded)


def test_desktop_app_probe_has_safe_and_real_modes():
    args = desktop_app_probe.parse_args(["--real-webengine"])

    assert args.real_webengine is True
    assert hasattr(desktop_app_probe, "run_shell_probe")
    assert hasattr(desktop_app_probe, "run_real_webengine_probe")
    source = inspect.getsource(desktop_app_probe.run_real_webengine_child)
    assert "real-webengine-child.stdout.log" in source
    assert "real-webengine-child.stderr.log" in source


def test_visual_smoke_has_handler_for_every_state_action():
    source = inspect.getsource(visual_smoke._apply_state)
    handled_actions = set(re.findall(r"state\.action == \"([^\"]+)\"", source))
    configured_actions = {state.action for state in visual_smoke.STATES}

    assert configured_actions <= handled_actions


def test_visual_smoke_can_capture_through_desktop_local_proxy():
    args = visual_smoke.parse_args(["--via-desktop-proxy", "--roles", "public"])
    source = inspect.getsource(visual_smoke.main)

    assert args.via_desktop_proxy is True
    assert "LocalAppServer" in source
    assert "via_desktop_proxy" in source


def test_testprotocol_documents_agent_test_tools():
    protocol = (ROOT / "TESTPROTOCOL.md").read_text(encoding="utf-8")

    for command in (
        "python -m pytest",
        "python -m tools.bemanning_cli routes --format table",
        "python desktop\\main.py --smoke-test",
        "python -m tools.visual_smoke",
        "python -m tools.interactive_e2e",
        "python -m tools.desktop_shell_screens",
        "python -m tools.desktop_app_probe",
        "python -m tools.release_check",
        "cmd /c build_windows.bat",
    ):
        assert command in protocol


def test_allocation_observations_github_sync_is_wired():
    workflow = (ROOT / ".github" / "workflows" / "merge-observations.yml").read_text(encoding="utf-8")
    main = (ROOT / "app" / "backend" / "main.py").read_text(encoding="utf-8")
    engine = (ROOT / "warehouse_tools" / "vendor" / "allokering12.1.py").read_text(encoding="utf-8")

    assert "data/community-observations" in workflow
    assert "warehouse_tools/vendor/lowfreqdata/buffertpall/observations_*.csv.gz" in workflow
    assert "warehouse_tools/vendor/lowfreqdata/buffertpall/" in workflow
    assert "artikel_max.csv" in workflow
    assert "np.percentile(group['antal'], [25, 75])" in workflow
    assert "Nya pallid från sessionsfiler" in workflow
    assert "Ändrade maxvärden" in workflow
    assert "GITHUB_STEP_SUMMARY" in workflow
    assert "fetch_observations_from_github()" in main
    assert "sync_allocation_observations_on_startup" in main
    assert '"OBSERVATIONS_GITHUB_TOKEN"' in engine
    assert '"BEMANNING_GITHUB_TOKEN"' in engine
    assert "github_sent_rows" in engine
    assert "article_max_changed_rows" in engine


def test_app_migration_plan_documents_high_risk_workflows():
    plan = (ROOT / "APP_MIGRATION_PLAN.md").read_text(encoding="utf-8")

    for required in (
        "Inloggning, session och roller",
        "Bemanning: dagsschema",
        "Översikt",
        "Produktivitet",
        "Desktop/Windows-app",
        "Lokalt appskal med central API-proxy",
        "Stopplista",
    ):
        assert required in plan


def test_desktop_build_bundles_local_frontend():
    spec = (ROOT / "Bemanning.spec").read_text(encoding="utf-8")

    assert "app/frontend" in spec
    assert "frontend_dir" in spec
    assert 'excludes=["pytest", "tests"]' in spec


def test_desktop_web_view_accepts_file_downloads():
    web_view = (ROOT / "desktop" / "web_view.py").read_text(encoding="utf-8")

    assert "downloadRequested.connect" in web_view
    assert "setDownloadDirectory" in web_view
    assert "StandardLocation.DownloadLocation" in web_view
    assert "download.accept()" in web_view


def test_visual_smoke_outputs_have_unique_names():
    names = []
    for viewport in visual_smoke.VIEWPORTS:
        for role in ("public", "admin", "leader", "staffing", "viewer", "warehouse", "article"):
            for page in visual_smoke.PAGES:
                if role in page.roles:
                    names.append(visual_smoke._safe_name(viewport.name, role, page.name))
            for state in visual_smoke.STATES:
                if role in state.roles:
                    names.append(visual_smoke._safe_name(viewport.name, role, state.name))

    assert len(names) == len(set(names))


def test_visual_data_seeds_disposable_sqlite_database(tmp_path):
    db_path = tmp_path / "visual.sqlite"
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "SECRET_KEY": "test-secret",
            "SUPER_USER_USERNAMES": "admin,emikad",
        }
    )

    subprocess.run(
        [sys.executable, "-m", "app.backend.bootstrap_local"],
        cwd=ROOT,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [sys.executable, "-m", "tools.visual_data"],
        cwd=ROOT,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )

    with sqlite3.connect(db_path) as connection:
        users = connection.execute(
            "select username, role from users where username in ('visual_leader', 'visual_staffing', 'visual_viewer', 'visual_lager', 'visual_artikel')"
        ).fetchall()
        visual_people = connection.execute(
            "select count(*) from persons where name like 'Visual %'"
        ).fetchone()[0]
        schedule_cells = connection.execute("select count(*) from schedule_cells").fetchone()[0]
        audit_rows = connection.execute(
            "select count(*) from audit_log where entity_type = 'visual_test'"
        ).fetchone()[0]

    assert sorted(users) == [
        ("visual_artikel", "article_placer"),
        ("visual_lager", "warehouse_clerk"),
        ("visual_leader", "leader"),
        ("visual_staffing", "staffing_manager"),
        ("visual_viewer", "viewer"),
    ]
    assert visual_people >= 6
    assert schedule_cells > 0
    assert audit_rows == 1


def test_local_bootstrap_upgrades_existing_persons_table(tmp_path):
    db_path = tmp_path / "old-local.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            create table persons (
                id integer primary key,
                name varchar(120) not null,
                home_area_id integer,
                home_activity_id integer,
                competencies json not null default '[]',
                comment text,
                is_active boolean not null default 1,
                sort_order integer not null default 0,
                created_at datetime,
                updated_at datetime
            )
            """
        )
        connection.execute(
            "insert into persons (name, competencies, is_active, sort_order) values ('Legacy Person', '[]', 1, 0)"
        )

    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "SECRET_KEY": "test-secret",
            "SUPER_USER_USERNAMES": "admin,emikad",
        }
    )

    subprocess.run(
        [sys.executable, "-m", "app.backend.bootstrap_local"],
        cwd=ROOT,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("pragma table_info(persons)").fetchall()}
        fixed_schedule = connection.execute(
            "select has_fixed_schedule from persons where name = 'Legacy Person'"
        ).fetchone()[0]

    assert "has_fixed_schedule" in columns
    assert fixed_schedule == 1


def test_frontend_icon_assets_are_referenced_and_present():
    frontend = ROOT / "app" / "frontend"
    expected_links = [
        '<link rel="icon" href="/favicon.ico" sizes="any" />',
        '<link rel="apple-touch-icon" href="/app-icon-192.png" />',
        '<link rel="manifest" href="/manifest.webmanifest" />',
    ]

    for html_path in frontend.glob("*.html"):
        html = html_path.read_text(encoding="utf-8")
        for link in expected_links:
            assert link in html, f"{html_path.name} saknar {link}"

    for asset in ("favicon.ico", "app-icon-192.png", "app-icon-512.png", "manifest.webmanifest"):
        assert (frontend / asset).is_file()


def test_frontend_theme_toggle_is_wired_globally():
    frontend = ROOT / "app" / "frontend"
    common = (frontend / "js" / "common.js").read_text(encoding="utf-8")
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")
    api_js = (frontend / "js" / "api.js").read_text(encoding="utf-8")
    productivity = (frontend / "js" / "productivity.js").read_text(encoding="utf-8")
    productivity_uploads = (frontend / "js" / "productivity_uploads.js").read_text(encoding="utf-8")
    allocation_tools = (frontend / "js" / "allocation_tools.js").read_text(encoding="utf-8")
    users = (frontend / "js" / "users.js").read_text(encoding="utf-8")
    productivity_html = (frontend / "produktivitet.html").read_text(encoding="utf-8")
    uploads_html = (frontend / "uppladdningar.html").read_text(encoding="utf-8")

    assert "bemanning-theme" in common
    assert "bemanning-sidebar-user" in common
    assert "bemanning-sidebar-layout" in common
    assert "bemanning-role-view-access" in common
    assert "ROLE_VIEW_DEFAULT_ACCESS" in common
    assert "ROLE_VIEW_IDS" in common
    assert "new Set(ROLE_VIEW_IDS)" in common
    assert "roleViewAccessLevel" in common
    assert "refreshRoleViewAccess" in common
    assert 'api.get("/api/settings/role-access")' in common
    assert 'api.put("/api/settings/role-access"' in users
    assert "readCachedSidebarUser" in common
    assert "sidebar-initializing" in common
    assert "id=\"theme-toggle\"" in common
    assert 'id="sidebar-edit"' in common
    assert "SIDEBAR_MOVE_UP_ICON" in common
    assert "SIDEBAR_MOVE_DOWN_ICON" in common
    assert "LOG_ICON" in common
    assert 'api.get("/api/settings/sidebar")' in common
    assert 'api.put("/api/settings/sidebar"' in common
    assert "renderSidebarNav" in common
    assert "renderAllocationUploadUtility" in common
    assert "renderLogUtility" in common
    assert 'id="log-toggle"' in common
    assert 'panel.id = "log-sidebar"' in common
    assert 'id="log-sidebar-close"' in common
    assert "ensureLogSidebar" in common
    assert "appendAppLog" in common
    assert "log-entry" in styles
    assert "${logUtility}\n        ${uploadUtility}" in common
    assert 'class="database-toggle${activeClass}"' in common
    assert "openUploadContextMenu" in common
    assert "Rensa filer" in common
    assert "clearAllUploadedFiles" in common
    assert "bemanning:uploadsCleared" in common
    assert 'className: "sidebar-upload-link"' not in common
    assert "openSidebarEditor" in common
    assert "sidebar-subview" in common
    assert "parent_id" in common
    assert "THEME_ICONS" in common
    assert ':root[data-theme="dark"]' in styles
    assert ".theme-toggle" in styles
    assert ".log-toggle" in styles
    assert ".log-sidebar" in styles
    assert ".log-sidebar[hidden]" in styles
    assert ".log-sidebar-close" in styles
    assert ".sidebar-heading" in styles
    assert ".sidebar-subviews" in styles
    assert ".sidebar-editor-row" in styles
    assert ".sidebar-editor-move button svg" in styles
    assert ".role-access-table" in styles
    assert ".role-access-toggle" in styles
    assert ".role-access-toggle.is-view" in styles
    assert ".role-access-toggle.is-edit" in styles
    assert ".role-access-table select" not in styles
    assert ".upload-context-menu" in styles
    assert ".sidebar.collapsed .sidebar-edit" in styles
    assert ".app.sidebar-initializing" in styles
    assert "postFile" in api_js
    assert "/api/productivity/files/raw" in productivity_uploads
    assert "productivityLocalFiles" in productivity
    assert "syncProductivityLocalFilesFromStore" in productivity
    assert "renderProductivityFileRequirements" in productivity
    assert 'id="productivityFileRequirements"' in productivity_html
    assert "window.productivityUploads.loadFiles()" in productivity
    assert "productivityUploads?.setupPanel" not in allocation_tools
    assert "data-productivity-upload-panel" not in allocation_tools
    assert "PRODUCTIVITY_UPLOAD_SLOTS" in allocation_tools
    assert "productivity_pallet" in allocation_tools
    assert "Palllastningslogg" in allocation_tools
    assert "PRODUCTIVITY_SHARED_UPLOAD_WORDS" in allocation_tools
    assert "v_ask_booking_putaway" in allocation_tools
    assert "ALLOCATION_SLOT_MIRRORS" in allocation_tools
    assert 'wms_booking: ["not_putaway"]' in allocation_tools
    assert "v_ask_receive_log" in allocation_tools
    assert "v_ask_palletloading_log" in allocation_tools
    assert "routeProductivityFilesFromSharedUpload" in allocation_tools
    assert "reportUnknown: false" in allocation_tools
    assert "statusItems" in productivity_uploads
    assert "clearFiles" in productivity_uploads
    assert "deleteFile" in productivity_uploads
    assert "saveFiles" in productivity_uploads
    assert "recognized" in productivity_uploads
    assert "refreshPanels" in productivity_uploads
    assert "setupDropTarget" in productivity_uploads
    assert "productivity-file-slot[data-file-key]" in productivity_uploads
    assert "Permanent målfil inlagd" in productivity_uploads
    assert "allocation-file-tag" in productivity_uploads
    assert "allocation-file-tag" in productivity
    assert "setupProductivityPageDrop" in productivity
    assert "handleProductivityDroppedFiles" in productivity
    assert "handleProductivityUploadsCleared" in productivity
    assert "data-productivity-file-key" in productivity
    assert ".productivity-page.is-file-dragging" in styles
    assert ".productivity-requirement-file.drag-over" in styles
    assert "/js/productivity_uploads.js" in productivity_html
    assert "/js/productivity_uploads.js" in uploads_html
    assert 'id="productivityUploadBtn"' not in productivity_html
    assert 'id="productivityUploadPanel"' not in productivity_html
    assert "buildProductivityReportFromLocalDataset" in productivity
    assert "prefetchAdjacentReports" in productivity
    assert 'id="productivityPrevDate"' in productivity_html
    assert 'id="productivityNextDate"' in productivity_html
    assert 'id="productivityDateDisplayText"' in productivity_html
    assert 'class="date-display-overlay"' in productivity_html
    assert "shiftProductivityDate(-1)" in productivity
    assert "shiftProductivityDate(1)" in productivity
    assert "updateProductivityDateDisplay" in productivity
    assert "availableProductivityDates" in productivity
    assert ".date-display-wrap" in styles
    assert "refreshProductivityBtn" not in productivity_html

    for html_path in frontend.glob("*.html"):
        html = html_path.read_text(encoding="utf-8")
        assert "/js/common.js" in html


def test_area_focus_toggle_is_wired_to_views():
    frontend = ROOT / "app" / "frontend"
    common = (frontend / "js" / "common.js").read_text(encoding="utf-8")
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")
    schedule = (frontend / "js" / "schedule.js").read_text(encoding="utf-8")
    overview = (frontend / "js" / "overview.js").read_text(encoding="utf-8")
    productivity = (frontend / "js" / "productivity.js").read_text(encoding="utf-8")
    persons = (frontend / "js" / "persons.js").read_text(encoding="utf-8")
    activities = (frontend / "js" / "activities.js").read_text(encoding="utf-8")

    assert "bemanning-area-focus" in common
    assert '<button class="area-focus-toggle" id="area-focus-toggle"' in common
    assert '<select class="area-focus-toggle"' not in common
    assert "AREA_FOCUS_OPTIONS" in common
    assert 'label: "∞"' in common
    assert "function nextAreaFocus" in common
    assert 'toggle.addEventListener("click", () => writeAreaFocus(nextAreaFocus()))' in common
    assert "preferredAreaIdFromFocus" in common
    assert "compareActivitiesForAreaFocus" in common
    assert "comparePersonsForAreaFocus" in common
    assert ".area-focus-toggle" in styles

    assert 'const CALC_AREA_KEYS = ["GG", "MG", "AS", "EH"]' in schedule
    assert 'typeof areaFocusCode === "function" && areaFocusCode()' in schedule
    assert 'typeof areaFocusCode === "function" && areaFocusCode()' in overview
    assert '"bemanning:areaFocusChanged"' in schedule
    assert '"bemanning:areaFocusChanged"' in overview
    assert '"bemanning:areaFocusChanged"' in productivity
    assert '"bemanning:areaFocusChanged"' in persons
    assert '"bemanning:areaFocusChanged"' in activities
    assert '{ id: "eh", title: "E-Handel" }' in productivity


def test_frontend_knows_bemanningsansvarig_role():
    frontend = ROOT / "app" / "frontend"
    common = (frontend / "js" / "common.js").read_text(encoding="utf-8")
    users = (frontend / "js" / "users.js").read_text(encoding="utf-8")

    assert '{ value: "staffing_manager", label: "Bemanningsansvarig" }' in users
    assert 'roles.includes("staffing_manager")' in users
    assert "staffing_manager:" in common
    assert "roleViewAccessLevel" in common


def test_frontend_only_shows_super_user_role_to_super_users():
    users = (ROOT / "app" / "frontend" / "js" / "users.js").read_text(encoding="utf-8")

    assert 'const SUPER_USER_ROLE_OPTION = { value: "super_user", label: "Super User" };' in users
    assert "currentUser?.is_super_user ? USER_ROLE_OPTIONS : ROLE_OPTIONS" in users
    assert 'if (roles.includes("super_user")) return "super_user";' in users
    assert 'selectedRoles.includes("super_user")' in users


def test_frontend_keeps_lager_and_artikelplacering_out_of_bemanning_and_bearbeta():
    frontend = ROOT / "app" / "frontend"
    common = (frontend / "js" / "common.js").read_text(encoding="utf-8")
    schedule = (frontend / "js" / "schedule.js").read_text(encoding="utf-8")
    allocation = (frontend / "js" / "allocation_tools.js").read_text(encoding="utf-8")

    assert 'article_placer: {' in common
    assert 'id: "schedule"' in common
    assert 'visible: canViewPage(user, "schedule")' in common
    assert 'id: "allocationProcess"' in common
    assert 'visible: canViewPage(user, "allocationProcess")' in common
    assert '"allocationUploads",' in common
    assert 'canViewPage(user, "allocationUploads")' in common
    assert 'initPage("schedule", { requirePlanningView: true, denyRedirect: "/overblick.html" })' in schedule
    assert "pageOptions.requireAllocationProcess = true" in allocation
    assert 'pageOptions.denyRedirect = "/dela.html"' in allocation


def test_import_views_have_templates_and_help_buttons():
    frontend = ROOT / "app" / "frontend"
    common = (frontend / "js" / "common.js").read_text(encoding="utf-8")
    api_js = (frontend / "js" / "api.js").read_text(encoding="utf-8")
    persons_html = (frontend / "personer.html").read_text(encoding="utf-8")
    persons_js = (frontend / "js" / "persons.js").read_text(encoding="utf-8")
    users_html = (frontend / "anvandare.html").read_text(encoding="utf-8")
    users_js = (frontend / "js" / "users.js").read_text(encoding="utf-8")
    activities_html = (frontend / "stallen.html").read_text(encoding="utf-8")
    activities_js = (frontend / "js" / "activities.js").read_text(encoding="utf-8")

    assert "setupImportHelpButton" in common
    assert "Ladda ner importmallen" in common
    assert "async function download" in api_js
    assert "URL.createObjectURL(blob)" in api_js

    assert 'id="download-person-template"' in persons_html
    assert 'id="person-import-help"' in persons_html
    assert 'setupImportHelpButton("person-import-help", "Importera personer")' in persons_js
    assert 'api.download("/api/persons/import-template", "personer-importmall.xlsx")' in persons_js
    assert 'window.location.href = "/api/persons/import-template"' not in persons_js

    assert 'id="download-user-template"' in users_html
    assert 'id="role-view-access"' in users_html
    assert 'id="user-import-help"' in users_html
    assert 'setupImportHelpButton("user-import-help", "Importera användare")' in users_js
    assert 'api.download("/api/users/import-template", "anvandare-importmall.xlsx")' in users_js
    assert 'window.location.href = "/api/users/import-template"' not in users_js
    assert "openRoleAccessModal" in users_js
    assert "ROLE_ACCESS_LEVEL_OPTIONS" in users_js
    assert "ROLE_ACCESS_LEVEL_ORDER" in users_js
    assert "roleAccessToggle" in users_js
    assert "nextRoleAccessLevel" in users_js
    assert "select[data-role][data-view]" not in users_js

    assert 'id="download-activity-template"' in activities_html
    assert 'id="import-activities"' in activities_html
    assert 'id="activity-import-help"' in activities_html
    assert "/api/activities/import-template" in activities_js
    assert 'api.download("/api/activities/import-template", "stallen-importmall.xlsx")' in activities_js
    assert 'window.location.href = "/api/activities/import-template"' not in activities_js
    assert "/api/activities/import" in activities_js
    assert 'canEditPage(currentUser, "stallen")' in activities_js
    assert 'setupImportHelpButton("activity-import-help", "Importera ställen")' in activities_js


def test_sidebar_pages_reserve_layout_before_auth_finishes():
    frontend = ROOT / "app" / "frontend"
    public_pages = {"login.html", "set-password.html"}

    for html_path in frontend.glob("*.html"):
        html = html_path.read_text(encoding="utf-8")
        if html_path.name in public_pages:
            assert '<body class="with-sidebar">' not in html
        else:
            assert '<body class="with-sidebar">' in html, f"{html_path.name} saknar sidebar-reservering"

    common = (frontend / "js" / "common.js").read_text(encoding="utf-8")
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    assert 'document.body.classList.add("sidebar-hydrated")' in common
    assert "sessionStorage.setItem(SIDEBAR_USER_CACHE_KEY" in common
    assert "localStorage.setItem(SIDEBAR_USER_CACHE_KEY" in common
    assert "sessionStorage.getItem(SIDEBAR_USER_CACHE_KEY) || localStorage.getItem(SIDEBAR_USER_CACHE_KEY)" in common
    assert "body.with-sidebar:not(.sidebar-hydrated)" in styles
    assert "grid-template-columns: var(--sidebar-w) 1fr" in styles


def test_allocation_pages_are_wired_to_shared_tool_shell():
    frontend = ROOT / "app" / "frontend"
    allocation_pages = {
        "uppladdningar.html": "uploads",
        "bearbeta.html": "process",
        "dela.html": "split",
        "harleda.html": "trace",
    }

    for filename, view in allocation_pages.items():
        html = (frontend / filename).read_text(encoding="utf-8")
        assert '<body class="with-sidebar">' in html
        assert 'id="allocationRoot"' in html
        assert f'data-allocation-view="{view}"' in html
        assert "/js/api.js" in html
        assert "/js/common.js" in html
        assert "/js/allocation_tools.js" in html


def test_allocation_frontend_uses_local_file_store_and_upload_indicator():
    frontend = ROOT / "app" / "frontend"
    common = (frontend / "js" / "common.js").read_text(encoding="utf-8")
    allocation = (frontend / "js" / "allocation_tools.js").read_text(encoding="utf-8")
    productivity_uploads = (frontend / "js" / "productivity_uploads.js").read_text(encoding="utf-8")
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")
    catalog = (ROOT / "warehouse_tools" / "catalog.py").read_text(encoding="utf-8")
    flows = (ROOT / "warehouse_tools" / "flows.py").read_text(encoding="utf-8")

    assert 'const ALLOCATION_API = "/api/allokering"' in allocation
    assert 'const ALLOCATION_DB_NAME = "bemanning-allokering-files"' in allocation
    assert "indexedDB.open(ALLOCATION_DB_NAME" in allocation
    assert "window.allocationUploadActivity?.start()" in allocation
    assert "window.allocationUploadActivity?.finish(uploadedNames.size)" in allocation
    assert "observationsUpdateStatusText" in allocation
    assert "observationsUpdateLogText" in allocation
    assert "github_sent_rows" in allocation
    assert "article_max_changed_rows" in allocation
    assert "allocationState.files = await loadStoredAllocationFiles()" in allocation
    assert 'id="allocation-clear-all-files"' in allocation
    assert "Rensa alla" in allocation
    assert "window.clearAllUploadedFiles" in allocation
    assert 'window.addEventListener("bemanning:uploadsCleared"' in allocation
    assert 'window.addEventListener("bemanning:allocationFilesChanged"' in allocation
    assert "productivityUploads?.syncAllocationUploads" in allocation
    assert "Kunde inte synka produktivitetsfiler till Uppladdningar." in allocation
    assert "PRODUCTIVITY_UPLOAD_SLOTS" in allocation
    assert "Palllastningslogg" in allocation
    assert "data-productivity-upload-panel" not in allocation
    assert "allocationDropSlotsForTarget" in allocation
    assert "data-drop-slot" in allocation
    assert "fallbackSlotKey" in allocation
    assert 'data-allocation-drop data-drop-scope="flow"' in allocation
    assert "event.stopPropagation()" in allocation
    assert "Detalj Kundorder(alla)" in allocation
    assert "Detalj Kundorder(alla)" in catalog
    assert "Detalj Kundorder(alla)" in flows
    assert "Beställningslinjer" not in catalog
    assert "Beställningslinjer" not in flows
    assert "Saldo ink. Automation" in allocation
    assert "Saldo ink. Automation" in catalog
    assert "Saldo / automation" not in catalog
    assert '"not_putaway", "wms_booking"' in catalog
    assert '"not_putaway", "wms_booking"' in flows
    assert "ALLOCATION_CORE_FILES" in allocation
    assert "allocationCoreFile" in allocation
    assert "Kärnfil" in allocation
    assert '" (kärnfil)"' in allocation
    assert "artikel_max.csv (kärnfil)" in catalog

    assert "DATABASE_ICON" in common
    assert "ALLOCATION_UPLOAD_NOTICE_KEY" in common
    assert "SHARED_ALLOCATION_FILE_TYPE_KEYS" in common
    assert "SHARED_ALLOCATION_SLOT_MIRRORS" in common
    assert "productivity_pallet" in common
    assert "saveSharedAllocationFiles" in common
    assert "storeSharedAllocationFile" in common
    assert 'new CustomEvent("bemanning:allocationFilesChanged"' in common
    assert "window.sharedAllocationUploads" in common
    assert "addAllocationUploadNotice(count)" in common
    assert "isAllocationUploadsPage()" in common
    assert "window.allocationUploadActivity" in common
    assert "clearAllocationUploadNotice()" in common
    assert "trackUploadActivity" in productivity_uploads
    assert "syncAllocationUploads" in productivity_uploads
    assert "syncAllocationUploadsFromStore" in productivity_uploads
    assert "lastAllocationSyncSignature" in productivity_uploads
    assert "window.sharedAllocationUploads?.saveFiles" in productivity_uploads
    assert "window.allocationUploadActivity?.start()" in productivity_uploads
    assert "window.allocationUploadActivity?.finish(activityCount)" in productivity_uploads
    assert "syncAllocationUploads: false" in allocation
    assert "allocationResultSummaryEntries" in allocation
    assert "data.display_summary" in allocation
    assert 'data.flow_id === "allocate"' in allocation
    assert 'entry.key !== "result"' in allocation
    assert "data-download-csv" in allocation
    assert "api.download(`${ALLOCATION_API}/download/" in allocation
    assert 'href="${ALLOCATION_API}/download/' not in allocation

    assert ".database-toggle.uploading .upload-arrow" in styles
    assert "@keyframes uploadArrowRise" in styles
    assert ".database-toggle .upload-notice" in styles
    assert "left: -6px;" in styles
    assert ".sidebar-upload-link" not in styles
    assert ".allocation-file-slot.drag-over" in styles
    assert ".allocation-flow-chip.drag-over .allocation-flow-chip-row" in styles

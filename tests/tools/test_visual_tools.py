import inspect
import os
import re
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from tools import interactive_e2e
from tools import desktop_app_probe
from tools import visual_smoke


ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPT_FILES = [
    "foundation.js",
    "theme.js",
    "area_focus.js",
    "runtime.js",
    "app_log.js",
    "telemetry.js",
    "access.js",
    "sidebar.js",
    "uploads.js",
    "demo_prefetch_init.js",
    "import_tools.js",
    "table_sort.js",
    "date_state.js",
]
ALLOCATION_SCRIPT_FILES = [
    "state.js",
    "files.js",
    "api.js",
    "uploads_view.js",
    "results.js",
    "process_view.js",
    "process_matrix.js",
    "map_settings.js",
    "settings_view.js",
    "split_view.js",
    "boot.js",
]
SCHEDULE_SCRIPT_FILES = [
    "state.js",
    "ui_core.js",
    "activity_capacity.js",
    "loan.js",
    "person_order.js",
    "segments_undo.js",
    "calculator.js",
    "rendering.js",
    "summary.js",
    "editing.js",
    "data.js",
    "rfid.js",
    "copy_modal.js",
    "boot.js",
]


def read_allocation_frontend(frontend: Path | None = None) -> str:
    frontend = frontend or ROOT / "app" / "frontend"
    allocation_dir = frontend / "js" / "allocation"
    parts = [(allocation_dir / filename).read_text(encoding="utf-8") for filename in ALLOCATION_SCRIPT_FILES]
    parts.append((frontend / "js" / "allocation_tools.js").read_text(encoding="utf-8"))
    return "\n".join(parts)


def read_common_frontend(frontend: Path | None = None) -> str:
    frontend = frontend or ROOT / "app" / "frontend"
    common_dir = frontend / "js" / "common"
    parts = [(common_dir / filename).read_text(encoding="utf-8") for filename in COMMON_SCRIPT_FILES]
    parts.append((frontend / "js" / "common.js").read_text(encoding="utf-8"))
    return "\n".join(parts)


def read_schedule_frontend(frontend: Path | None = None) -> str:
    frontend = frontend or ROOT / "app" / "frontend"
    schedule_dir = frontend / "js" / "schedule"
    parts = [(schedule_dir / filename).read_text(encoding="utf-8") for filename in SCHEDULE_SCRIPT_FILES]
    parts.append((frontend / "js" / "schedule.js").read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_visual_smoke_covers_expected_routes():
    pages_by_name = {page.name: page for page in visual_smoke.PAGES}

    assert set(pages_by_name) == {
        "login",
        "mitt-schema",
        "min-produktivitet",
        "flow",
        "oversikt",
        "produktivitet",
        "personer",
        "aktiviteter",
        "historik",
        "anvandare",
        "verksamheter",
        "hamta-data",
        "mcp",
        "uppladdningar",
        "bearbeta",
        "dela",
    }
    assert pages_by_name["mitt-schema"].roles == ("admin", "person")
    assert pages_by_name["min-produktivitet"].roles == ("admin", "person")
    assert pages_by_name["flow"].roles == ("admin", "leader", "staffing", "viewer", "r3")
    assert pages_by_name["personer"].roles == ("admin", "leader", "staffing")
    assert pages_by_name["produktivitet"].roles == ("admin",)
    assert pages_by_name["anvandare"].roles == ("admin",)
    assert pages_by_name["verksamheter"].roles == ("admin",)
    assert pages_by_name["hamta-data"].roles == ("admin",)
    assert pages_by_name["mcp"].roles == ("admin",)
    assert pages_by_name["uppladdningar"].roles == ("admin", "warehouse", "article")
    assert pages_by_name["bearbeta"].roles == ("admin",)
    assert pages_by_name["dela"].roles == ("admin", "warehouse", "article")


def test_schedule_view_uses_bemanning_label_in_visible_navigation():
    common = read_common_frontend()
    users = (ROOT / "app" / "frontend" / "js" / "users.js").read_text(encoding="utf-8")
    index = (ROOT / "app" / "frontend" / "index.html").read_text(encoding="utf-8")
    assistant = (ROOT / "app" / "backend" / "routers" / "assistant.py").read_text(encoding="utf-8")

    assert 'id: "schedule",\n      label: "Bemanning",' in common
    assert '{ id: "schedule", label: "Bemanning" }' in users
    assert "<title>Bemanning - flow</title>" in index
    assert 'id="sectionTitle">Bemanning</div>' in index
    assert '"schedule": "Bemanning"' in assistant

    assert 'label: "flow"' not in common
    assert 'label: "flow"' not in users


def test_history_view_has_error_dashboard_and_client_error_logging():
    html = (ROOT / "app" / "frontend" / "historik.html").read_text(encoding="utf-8")
    analytics = (ROOT / "app" / "frontend" / "js" / "analytics.js").read_text(encoding="utf-8")
    api = (ROOT / "app" / "frontend" / "js" / "api.js").read_text(encoding="utf-8")
    allocation = read_allocation_frontend()
    common = read_common_frontend()
    meta_upload = (ROOT / "app" / "frontend" / "js" / "meta_upload.js").read_text(encoding="utf-8")
    desktop_bridge = (ROOT / "app" / "frontend" / "js" / "desktop_bridge.js").read_text(encoding="utf-8")
    desktop_app = (ROOT / "desktop" / "app.py").read_text(encoding="utf-8")

    assert 'data-history-mode="history"' in html
    assert 'data-history-mode="analysis"' in html
    assert 'data-history-mode="functions"' in html
    assert 'data-history-mode="buttons"' in html
    assert 'data-history-mode="columns"' in html
    assert 'data-history-mode="flows"' in html
    assert 'data-history-mode="tracking-ai"' in html
    assert 'data-history-mode="errors"' in html
    assert 'data-history-mode="waits"' in html
    assert 'data-history-mode="health"' in html
    assert 'id="businessFilter"' in html
    assert 'id="recentErrorBody"' in html
    assert 'id="slowWaitBody"' in html
    assert 'id="healthChecksBody"' in html
    assert 'id="trackingTopFeaturesBody"' in html
    assert 'id="trackingTopControlsBody"' in html
    assert 'id="trackingTopColumnsBody"' in html
    assert 'id="trackingTopFlowsBody"' in html
    assert 'id="historyTrackingChatForm"' in html
    assert 'api.get("/api/businesses?include_inactive=true")' in analytics
    assert 'params.set("business_id", businessId)' in analytics
    assert 'api.get(`/api/audit/errors?${params.toString()}`)' in analytics
    assert 'api.get(`/api/healthcheck/wait-metrics/summary?${waitMetricParams().toString()}`)' in analytics
    assert 'api.get("/api/healthcheck?include_render=true"' in analytics
    assert "function renderErrorDashboard" in analytics
    assert "function renderWaitMetrics" in analytics
    assert "function renderHealthReport" in analytics
    assert 'coredata_file: "Kärnfil"' in analytics
    assert 'meta_media_upload: "Meta-uppladdning"' in analytics
    assert 'rfid_scan_event: "RFID-stämpel"' in analytics
    assert 'mcp_query: "MCP-fråga"' in analytics
    assert 'workflow_source: "Workflow-underlag"' in analytics
    assert 'entry.entity_type === "coredata_file"' in analytics
    assert 'entry.entity_type === "meta_media_upload"' in analytics
    assert 'entry.entity_type === "rfid_scan_event"' in analytics
    assert 'entry.entity_type === "mcp_query"' in analytics
    assert 'entry.entity_type === "workflow_source"' in analytics
    assert "Tagg:" in analytics
    assert "TRACKING_HISTORY_MODES" in analytics
    assert "function interactionParams" in analytics
    assert 'api.get(`/api/audit/interactions/summary?${trackingParams.toString()}`)' in analytics
    assert 'api.get(`/api/audit/interactions/coverage?${interactionCoverageParams().toString()}`)' in analytics
    assert 'api.get(`/api/audit/interactions?${interactionParams(200).toString()}`)' in analytics
    assert 'api.post("/api/audit/interactions/chat"' in analytics
    assert 'api.post("/api/audit/interactions/chat/clear"' in analytics
    assert 'const CLIENT_ERROR_REPORT_PATH = "/api/audit/client-error";' in api
    assert 'const WAIT_METRIC_REPORT_PATH = "/api/healthcheck/wait-metrics";' in api
    assert 'const INTERACTION_EVENT_REPORT_PATH = "/api/audit/interactions";' in api
    assert "function reportApiInteraction" in api
    assert "function reportApiWaitMetric" in api
    assert "function reportApiError" in api
    assert "window.reportApiError = reportApiError;" in api
    assert 'const CLIENT_EVENT_REPORT_PATH = "/api/audit/client-event";' in api
    assert "function reportClientEvent" in api
    assert "window.reportClientEvent = reportClientEvent;" in api
    assert "function isLikelyHtmlDocument" in api
    assert "function htmlErrorMessage" in api
    assert 'link.dataset.trackIgnore = "true";' in api
    assert "Servern svarade med ${httpStatusLabel(status)}" in api
    assert "HTML-felsida fran servern" in api
    assert "logApiSuccess" in api
    assert "logApiFailure" in api
    assert "apiResultSummary" in api
    assert "window.reportApiError?.(path" in allocation
    assert "appendAppLog(message" in common
    assert "APP_LOG_STORAGE_KEY" in common
    assert "APP_LOG_UNREAD_STORAGE_KEY" in common
    assert "triggerAppLogSignal" in common
    assert "appLogSignalTimer" in common
    assert "readStoredAppLogUnreadCount" not in common
    assert "persistAppLogUnreadCount" not in common
    assert "incrementAppLogNotice" not in common
    assert "function recordWaitMetric" in common
    assert "window.flowRecordWaitMetric = recordWaitMetric;" in common
    assert 'const COMMON_INTERACTION_EVENT_REPORT_PATH = "/api/audit/interactions";' in common
    assert "function flowTrack" in common
    assert "function initInteractionAutoCapture" in common
    assert "window.flowTrack = flowTrack;" in common
    assert "window.flowCurrentInteractionContext = currentInteractionContext;" in common
    assert "client_long_task" in common
    assert "reportPageOpen(user, activePage)" in common
    assert "reportPageLoadWaitMetric(activePage)" in common
    assert 'appendAppLog(`Öppnade vy:' not in common
    assert "window.flowLog" in common
    assert "clearAppLog" in common
    assert "pathWithoutQuery(path)" in api
    assert "allocationTrack(\"flow_run_start\"" in allocation
    assert "allocationTrack(\"copy_column\"" in allocation
    assert "allocationTrack(\"auto_copy_column\"" in allocation
    assert "allocationTableEventMeta(key, columnIndex)" in allocation
    assert "copy_mode: \"manual\"" in allocation
    public_summary = meta_upload.split("function publicMetaFileSummary", 1)[1].split("function publicMetaTrack", 1)[0]
    assert "publicMetaTrack(\"public_meta_file_select\"" in meta_upload
    assert "public_meta_upload_success" in meta_upload
    assert "file.name" not in public_summary
    assert "client_surface: \"desktop\"" in desktop_bridge
    assert "desktop_file_select" in desktop_bridge
    assert "desktop_update_check_start" in desktop_app
    assert "desktop_update_download_success" in desktop_app


def test_known_interaction_controls_match_frontend_control_ids():
    from app.backend.routers.audit_logs import KNOWN_INTERACTION_CONTROLS

    frontend_text = "\n".join(
        path.read_text(encoding="utf-8")
        for pattern in ("*.html", "*.js")
        for path in (ROOT / "app" / "frontend").rglob(pattern)
    )
    semantic_controls = {
        ("schedule", "schedule_cell_select"),
        ("overview", "overview_day_select"),
    }
    missing = [
        (item["view_id"], item["control_id"])
        for item in KNOWN_INTERACTION_CONTROLS
        if item["control_id"] not in frontend_text and (item["view_id"], item["control_id"]) not in semantic_controls
    ]

    assert not missing
    control_ids = {item["control_id"] for item in KNOWN_INTERACTION_CONTROLS}
    assert control_ids.isdisjoint({"newPerson", "bulkPersons", "importPersons", "newActivity", "bulkActivities", "newUser", "roleAccess"})
    assert {"new-person", "bulk-persons", "import-persons", "new-act", "bulk-activities", "new-user", "role-view-access"} <= control_ids


def test_visual_smoke_covers_critical_scenarios():
    state_names = {state.name for state in visual_smoke.STATES}

    assert {
        "flow-mestergruppen",
        "flow-autostore",
        "flow-stigamo-infinity",
        "flow-r3-toggle",
        "flow-superuser-global-infinity",
        "flow-kopiera-dag-modal",
        "flow-kalkyl-alla",
        "flow-fokus-mestergruppen",
        "oversikt-fokus-mestergruppen",
        "produktivitet-fokus-mestergruppen",
        "personer-fokus-mestergruppen",
        "aktiviteter-fokus-mestergruppen",
        "oversikt-manad-mestergruppen",
        "personer-veckomall-modal",
        "aktiviteter-import-hjalp",
        "aktiviteter-redigera-aktivitet-modal",
        "anvandare-redigera-anvandare-modal",
        "anvandare-vybehorigheter-modal",
        "verksamheter-ny-verksamhet-modal",
        "historik-filter",
        "historik-funktioner",
        "historik-knappar",
        "historik-kolumner",
        "historik-floden",
        "historik-ai-analys",
        "historik-vantetider",
        "historik-halsa",
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
        "download_import_templates",
        "create_business",
        "edit_business",
        "create_user",
        "edit_user",
        "import_user",
        "toggle_user_setting",
        "delete_user",
        "create_activity",
        "edit_activity",
        "delete_activity",
        "import_activity",
        "import_person",
        "create_person",
        "edit_person_inline",
        "edit_person_fields_inline",
        "edit_person_activity_inline",
        "edit_person_week_template",
        "edit_person_hourly_schedule",
        "schedule_person_activity",
        "edit_schedule_cell",
        "split_schedule_cell",
        "copy_paste_schedule_cell",
        "drag_fill_schedule_cells",
        "copy_day",
        "clear_day",
        "undo_redo",
        "overview_person_activity",
        "overview_edit",
        "history_filter",
        "role_access_click_cycle",
        "role_access_view_level",
        "role_access_edit_level",
        "role_access_none_level",
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


def test_visual_smoke_fails_if_forbidden_terminology_is_rendered():
    source = inspect.getsource(visual_smoke._capture_for_role)

    assert hasattr(visual_smoke, "assert_no_forbidden_terminology")
    assert "assert_no_forbidden_terminology(page)" in source


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
        "python -m tools.flow_cli routes --format table",
        "python desktop\\main.py --smoke-test",
        "python -m tools.visual_smoke",
        "python -m tools.interactive_e2e",
        "python -m tools.performance_benchmark",
        "python -m tools.healthcheck report --local --no-render",
        "python -m tools.healthcheck waits --local --period 24h",
        "python -m tools.desktop_shell_screens",
        "python -m tools.desktop_app_probe",
        "python -m tools.release_check",
        "cmd /c build_windows.bat",
    ):
        assert command in protocol


def test_project_protocol_documents_healthcheck_workflow():
    docs = {
        "AGENTS.md": (ROOT / "AGENTS.md").read_text(encoding="utf-8"),
        "TESTPROTOCOL.md": (ROOT / "TESTPROTOCOL.md").read_text(encoding="utf-8"),
        "wiki/AGENTS.md": (ROOT / "wiki" / "AGENTS.md").read_text(encoding="utf-8"),
        "wiki/testing-release.md": (ROOT / "wiki" / "testing-release.md").read_text(encoding="utf-8"),
    }

    for name, text in docs.items():
        assert "tools.healthcheck report" in text, name
        assert "tools.healthcheck waits" in text, name
        assert "Halsa" in text, name
        assert "Vantetider" in text, name

    assert "Halsa och vantetider ar ett arbetssatt" in docs["AGENTS.md"]
    assert "storre push" in docs["AGENTS.md"]
    assert "error" in docs["AGENTS.md"]
    assert "warn" in docs["AGENTS.md"]


def test_project_protocol_documents_release_polling_policy():
    docs = {
        "AGENTS.md": (ROOT / "AGENTS.md").read_text(encoding="utf-8"),
        "TESTPROTOCOL.md": (ROOT / "TESTPROTOCOL.md").read_text(encoding="utf-8"),
        "wiki/testing-release.md": (ROOT / "wiki" / "testing-release.md").read_text(encoding="utf-8"),
    }

    for name, text in docs.items():
        assert "Releasepolling" in text, name
        assert "workflowen har startat" in text, name
        assert "be agenten kolla releasen senare" in text, name
        assert "15 minuter" in text, name
        assert "2 minuter" in text, name
        assert "1 minut" in text, name
        assert "30:e sekund" in text, name

    testprotocol_one_line = re.sub(r"\s+", " ", docs["TESTPROTOCOL.md"])
    assert "Ingen ny release eller tagg ska skapas om anvandaren bara ber om backend-push" in testprotocol_one_line


def test_allocation_observations_github_sync_is_wired():
    workflow = (ROOT / ".github" / "workflows" / "merge-observations.yml").read_text(encoding="utf-8")
    main = (ROOT / "app" / "backend" / "main.py").read_text(encoding="utf-8")
    engine = (ROOT / "warehouse_tools" / "vendor" / "allokering12.1.py").read_text(encoding="utf-8")

    assert "data/community-observations" in workflow
    assert "warehouse_tools/vendor/lowfreqdata/buffertpall/observations_*.csv.gz" in workflow
    assert "warehouse_tools/vendor/lowfreqdata/buffertpall/*/observations_*.csv.gz" in workflow
    assert "root_data_dir / 'stigamo'" in workflow
    assert "Moved legacy root session file" in workflow
    assert "warehouse_tools/vendor/lowfreqdata/buffertpall/" in workflow
    assert "artikel_max.csv" in workflow
    assert "np.percentile(group['antal'], [25, 75])" in workflow
    assert "Nya pallid från sessionsfiler" in workflow
    assert "Ändrade maxvärden" in workflow
    assert "GITHUB_STEP_SUMMARY" in workflow
    assert "fetch_observations_from_github(business_code=business_code)" in main
    assert "ALLOCATION_OBSERVATIONS_STARTUP_DELAY_SECONDS" in main
    assert "ALLOCATION_OBSERVATIONS_STARTUP_SPACING_SECONDS" in main
    assert "_allocation_observation_business_codes" in main
    assert "sync_allocation_observations_on_startup" in main
    assert '"OBSERVATIONS_GITHUB_TOKEN"' in engine
    assert '"FLOW_GITHUB_TOKEN"' in engine
    assert "github_sent_rows" in engine
    assert "article_max_changed_rows" in engine
    assert "business_observations_path" in engine
    assert "business_artikel_max_path" in engine
    assert "ensure_business_allocation_data_files" in engine


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
    spec = (ROOT / "flow.spec").read_text(encoding="utf-8")

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
        for role in ("public", "admin", "leader", "staffing", "viewer", "warehouse", "article", "r3"):
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
            "select username, role from users where username in ('visual_leader', 'visual_staffing', 'visual_viewer', 'visual_lager', 'visual_artikel', 'visual_r3_admin')"
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
        ("visual_r3_admin", "admin"),
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
        business_columns = {row[1] for row in connection.execute("pragma table_info(businesses)").fetchall()}
        fixed_schedule = connection.execute(
            "select has_fixed_schedule from persons where name = 'Legacy Person'"
        ).fetchone()[0]

    assert "has_fixed_schedule" in columns
    assert "noman" in columns
    assert "rfid_code" in columns
    assert "company_codes" in business_columns
    assert fixed_schedule == 1


def test_frontend_icon_assets_are_referenced_and_present():
    frontend = ROOT / "app" / "frontend"
    expected_links = [
        '<link rel="icon" href="/favicon.svg" type="image/svg+xml" />',
        '<link rel="alternate icon" href="/favicon.ico" sizes="any" />',
        '<link rel="apple-touch-icon" href="/app-icon-192.png" />',
        '<link rel="manifest" href="/manifest.webmanifest" />',
    ]

    for html_path in frontend.glob("*.html"):
        html = html_path.read_text(encoding="utf-8")
        for link in expected_links:
            assert link in html, f"{html_path.name} saknar {link}"

    assert 'src="/flow-logo.svg"' in (frontend / "login.html").read_text(encoding="utf-8")
    assert 'src="/flow-logo.svg"' in (frontend / "set-password.html").read_text(encoding="utf-8")
    assert "flow-logo.png" not in "\n".join(
        path.read_text(encoding="utf-8") for path in frontend.glob("*.html")
    )

    for asset in (
        "favicon.svg",
        "favicon.ico",
        "app-icon.svg",
        "app-icon-192.png",
        "app-icon-512.png",
        "flow-logo.svg",
        "manifest.webmanifest",
    ):
        assert (frontend / asset).is_file()

    for asset in ("favicon.svg", "app-icon.svg", "flow-logo.svg"):
        root = ET.parse(frontend / asset).getroot()
        assert root.tag.endswith("svg")

    manifest = (frontend / "manifest.webmanifest").read_text(encoding="utf-8")
    assert '"src": "/app-icon.svg"' in manifest
    assert '"sizes": "any"' in manifest
    assert '"type": "image/svg+xml"' in manifest


def test_frontend_theme_toggle_is_wired_globally():
    frontend = ROOT / "app" / "frontend"
    common = read_common_frontend(frontend)
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")
    api_js = (frontend / "js" / "api.js").read_text(encoding="utf-8")
    productivity_overview = (frontend / "js" / "productivity_overview.js").read_text(encoding="utf-8")
    allocation_tools = read_allocation_frontend(frontend)
    users = (frontend / "js" / "users.js").read_text(encoding="utf-8")
    productivity_html = (frontend / "produktivitet.html").read_text(encoding="utf-8")
    uploads_html = (frontend / "uppladdningar.html").read_text(encoding="utf-8")

    assert "flow-theme" in common
    assert "flow-app-zoom" in common
    assert "flow-sidebar-user" in common
    assert "flow-sidebar-layout" in common
    assert "flow-role-view-access" in common
    assert "ROLE_VIEW_DEFAULT_ACCESS" in common
    assert "ROLE_VIEW_IDS" in common
    assert '"staffingSettings"' in common
    assert '{ id: "staffingSettings", label: "Bemanningsinställningar" }' in users
    assert "new Set(ROLE_VIEW_IDS)" in common
    assert "roleViewAccessLevel" in common
    assert "refreshRoleViewAccess" in common
    assert '{ value: "super_user", label: "Super User", lockedLevel: "edit" }' in common
    assert '{ value: "demo", label: "Demo" }' in common
    assert 'api.get("/api/settings/role-access", { cacheTtlMs: 5 * 60 * 1000 })' in common
    assert "function hasCachedRoleViewAccess" in common
    assert "shouldBlockForRoleAccess" in common
    assert 'api.put("/api/settings/role-access"' in users
    assert "readCachedSidebarUser" in common
    assert "sidebar-initializing" in common
    assert "id=\"theme-toggle\"" in common
    assert 'id="app-zoom-control"' in common
    assert 'id="app-zoom-out"' in common
    assert 'id="app-zoom-in"' in common
    assert 'id="app-zoom-reset"' not in common
    assert 'cx="10.5"' in common
    assert 'cy="10.5"' in common
    assert "Ctrl++" in common
    assert 'key === "0"' in common
    assert 'window.addEventListener("wheel"' in common
    assert 'id="sidebar-edit"' in common
    assert "SIDEBAR_MOVE_UP_ICON" in common
    assert "SIDEBAR_MOVE_DOWN_ICON" in common
    assert "LOG_ICON" in common
    assert 'id="assistant-chat-input"' in common
    assert "event.shiftKey" in common
    assert "requestSubmit()" in common
    assert 'api.get("/api/settings/sidebar", { cacheTtlMs: 5 * 60 * 1000 })' in common
    assert 'api.put("/api/settings/sidebar"' in common
    assert "renderSidebarNav" in common
    assert "function sidebarRoleLabel" in common
    assert 'role === "super_user"' in common
    assert 'class="sidebar-role"' in common
    assert "renderAllocationUploadUtility" in common
    assert "renderLogUtility" in common
    assert 'id="log-toggle"' in common
    assert 'class="log-arrow"' in common
    assert 'id="log-notice"' in common
    assert "updateAppLogNotice" in common
    assert "clearAppLogNotice" in common
    assert "triggerAppLogSignal" in common
    assert "log-signal" in common
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
    assert "flow:uploadsCleared" in common
    assert 'className: "sidebar-upload-link"' not in common
    assert "openSidebarEditor" in common
    assert "sidebar-subview" in common
    assert "parent_id" in common
    assert "THEME_ICONS" in common
    assert ':root[data-theme="dark"]' in styles
    assert ".theme-toggle" in styles
    assert ".app-zoom-control" in styles
    assert ".sidebar.collapsed .app-zoom-control" in styles
    assert "[hidden] { display: none !important; }" in styles
    assert ".log-toggle" in styles
    assert ".log-toggle .log-notice" in styles
    assert ".log-toggle .log-arrow" in styles
    assert "@keyframes logArrowRise" in styles
    assert "@keyframes logBubbleBurst" in styles
    assert "animation: logBubbleBurst" in styles
    assert ".log-sidebar" in styles
    assert ".log-sidebar[hidden]" in styles
    assert ".log-sidebar-close" in styles
    assert ".sidebar-heading" in styles
    assert ".sidebar-subviews" in styles
    assert ".sidebar-bottom .sidebar-role" in styles
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
    assert "--sidebar-top:" in styles
    assert re.search(
        r"\.sidebar\s*\{[^}]*position:\s*fixed;[^}]*top:\s*var\(--sidebar-top\);[^}]*width:\s*var\(--sidebar-w\);",
        styles,
        re.S,
    )
    assert re.search(r"\.app > main\s*\{[^}]*grid-column:\s*2;", styles, re.S)
    assert "body.demo-mode .sidebar" in styles
    assert "postFile" in api_js
    assert "/api/productivity/files" not in api_js
    assert not (frontend / "js" / "productivity.js").exists()
    assert not (frontend / "js" / "productivity_uploads.js").exists()
    assert 'id="productivityFileRequirements"' not in productivity_html
    assert "/js/productivity_overview.js" in productivity_html
    assert "/js/productivity.js" not in productivity_html
    assert "/js/productivity_uploads.js" not in productivity_html
    assert "/js/productivity_uploads.js" not in uploads_html
    assert "productivityUploads" not in allocation_tools
    assert "data-productivity-upload-panel" not in allocation_tools
    assert "PRODUCTIVITY_UPLOAD_SLOTS" not in allocation_tools
    assert "productivity_pallet" not in allocation_tools
    assert "PRODUCTIVITY_SHARED_UPLOAD_WORDS" not in allocation_tools
    assert "v_ask_booking_putaway" in allocation_tools
    assert "ALLOCATION_SLOT_MIRRORS" in allocation_tools
    assert 'wms_booking: ["not_putaway"]' in allocation_tools
    assert "v_ask_receive_log" not in allocation_tools
    assert "v_ask_palletloading_log" not in allocation_tools
    assert "routeProductivityFilesFromSharedUpload" not in allocation_tools
    assert "input.apiPreferred" in allocation_tools
    assert "Prognosfil eller Kampanjfil" in allocation_tools
    assert "reportUnknown: false" not in allocation_tools
    assert 'id="productivityUploadBtn"' not in productivity_html
    assert 'id="productivityUploadPanel"' not in productivity_html
    assert ".productivity-matrix-wrap" in styles
    assert "table.productivity-matrix" in styles
    assert ".productivity-hour-cell" in styles
    assert ".productivity-cell-diff-button" in styles
    assert ".productivity-points-menu" not in styles
    assert ".productivity-hour-cell.kpi.score-low" in styles
    assert ".productivity-hour-cell.kpi.score-warn" in styles
    assert ".productivity-hour-cell.kpi.score-good" in styles
    assert ".productivity-diff-pill" in styles
    assert 'id="productivityPrevDate"' not in productivity_html
    assert 'id="productivityNextDate"' not in productivity_html
    assert 'id="productivityDateDisplayText"' not in productivity_html
    assert 'id="productivityOverviewPrevDate"' in productivity_html
    assert 'id="productivityOverviewNextDate"' in productivity_html
    assert 'id="productivityOverviewDateDisplayText"' in productivity_html
    assert 'class="date-display-overlay"' in productivity_html
    assert ".date-display-wrap" in styles
    assert ".productivity-date-field .date-display-wrap" in styles
    assert "refreshProductivityBtn" not in productivity_html
    assert "productivityOverview" not in common
    assert "productivityOverview" not in users
    assert "/oversikt-produktivitet.html" not in common
    assert not (frontend / "oversikt-produktivitet.html").exists()
    assert 'data-period="day"' in productivity_html
    assert 'data-period="week"' in productivity_html
    assert 'data-period="month"' in productivity_html
    assert 'data-period="year"' in productivity_html
    assert 'id="productivityOverviewExportFlowchart"' in productivity_html
    assert 'id="productivityOverviewTree"' in productivity_html
    assert 'initPage("productivity")' in productivity_overview
    assert "`/api/productivity/overview${query}`" in productivity_overview
    assert "PRODUCTIVITY_OVERVIEW_CACHE_TTL_MS" in productivity_overview
    assert "productivityOverviewReportCache" in productivity_overview
    assert "cacheTtlMs: PRODUCTIVITY_OVERVIEW_CACHE_TTL_MS" in productivity_overview
    assert "skipCache: true" not in productivity_overview
    assert "productivityOverviewPeriodValue" in productivity_overview
    assert "productivityOverviewPeriodDisplayLabel" in productivity_overview
    assert "productivityOverviewIsoWeekParts" in productivity_overview
    assert "`Vecka ${parts.week}`" in productivity_overview
    assert 'toLocaleDateString("sv-SE", { month: "long" })' in productivity_overview
    assert "toLocaleUpperCase(\"sv-SE\")" in productivity_overview
    assert "return String(year);" in productivity_overview
    assert "addProductivityOverviewMonths" in productivity_overview
    assert "addProductivityOverviewYears" in productivity_overview
    assert "productivityOverviewReports" in productivity_overview
    assert "exportProductivityOverviewFlowchart" in productivity_overview
    assert "openProductivityOverviewExportDialog" in productivity_overview
    assert "performProductivityOverviewFlowchartExport" in productivity_overview
    assert "PRODUCTIVITY_OVERVIEW_EXPORT_LEVELS" in productivity_overview
    assert "flow-productivity-overview-export-levels" in productivity_overview
    assert 'name="export-level"' in productivity_overview
    assert "data-productivity-export-form" in productivity_overview
    assert "buildProductivityOverviewFlowchartSvg" in productivity_overview
    assert "downloadProductivityOverviewText" in productivity_overview
    assert "function productivityOverviewAreaLabelForCell" in productivity_overview
    assert "productivityOverviewAreaKeyForCell(cell)" in productivity_overview
    assert 'person.home_area || "Utan avdelning"' not in productivity_overview
    assert "image/svg+xml" in productivity_overview
    assert "productivity-overview-export-flowchart" in productivity_overview
    assert "completedProductivityOverviewCutoffMinute" in productivity_overview
    assert "new Date().getHours() * 60" in productivity_overview
    assert "Number(cell?.end_minute || 0) <= cutoffMinute" in productivity_overview
    assert "productivityOverviewCellWorkMinutes" in productivity_overview
    assert "productivityOverviewCellKpiMinutes" in productivity_overview
    assert "addProductivityOverviewKpiMinutes" in productivity_overview
    assert "kpiMinutes: 0" in productivity_overview
    assert "Number(node?.kpiMinutes || 0) <= 0" in productivity_overview
    assert "productivityOverviewSourceWarnings" in productivity_overview
    assert "fallback_reason" in productivity_overview
    assert 'cell?.kind === "support"' in productivity_overview
    assert "productivityOverviewPointsPerHour" in productivity_overview
    assert "productivityOverviewScoreClass" in productivity_overview
    assert 'if (Number(value) >= 80) return "good";' in productivity_overview
    assert 'if (Number(value) >= 70) return "warn";' in productivity_overview
    assert "formatProductivityOverviewNumber(value, 1)" in productivity_overview
    assert "p/tim" not in productivity_overview
    assert 'cell?.kind === "kpi"' in productivity_overview
    assert "Poäng / timmar" in productivity_overview
    assert "hourNode.startMinute" in productivity_overview
    assert "formatProductivityOverviewHours" in productivity_overview
    assert "process_points" in productivity_overview
    assert "process_key" in productivity_overview
    assert "normalizeProductivityOverviewProcessKey" in productivity_overview
    assert "applyProductivityOverviewProcessRevenues" in productivity_overview
    assert "finance?.process_revenues" in productivity_overview
    assert "buildProductivityOverviewTree" in productivity_overview
    assert "focusProductivityOverviewNode" in productivity_overview
    assert "openProductivityOverviewContextMenu" in productivity_overview
    assert 'addEventListener("contextmenu"' in productivity_overview
    assert "data-productivity-business-summary" in productivity_overview
    assert "`/api/productivity/overview/business-summary${query}`" in productivity_overview
    assert "productivity-overview-branch" in productivity_overview
    assert "renderProductivityOverviewShell" in productivity_overview
    assert "waitForProductivityOverviewPaint" in productivity_overview
    assert "  void loadProductivityOverview();\n}\n\ndocument.addEventListener" in productivity_overview
    assert "Beräknar och ritar produktivitet" in productivity_overview
    assert 'setAttribute("aria-busy", "true")' in productivity_overview
    assert 'src="/js/productivity_overview.js?v=20260625-productivity-parallel-days"' in productivity_html
    assert "productivity-overview-tree-wrap" in styles
    assert ".productivity-overview-export-modal" in styles
    assert ".productivity-overview-export-levels" in styles
    assert ".productivity-overview-context-menu" in styles
    assert ".productivity-overview-summary-modal" in styles
    assert ".productivity-overview-summary-table" in styles
    assert ".productivity-overview-period-toggle" in styles
    assert "grid-auto-flow: column" in styles
    assert ".productivity-overview-branch::before" in styles
    assert ".productivity-overview-branch::after" in styles
    assert ".productivity-overview-node" in styles
    assert ".productivity-overview-node-rate.good" in styles
    assert ".productivity-overview-node-rate.warn" in styles
    assert ".productivity-overview-node-rate.low" in styles
    assert ".productivity-overview-summary-rate.good" in styles
    assert ".productivity-overview-process-row" in styles

    public_standalone_pages = {"meta-upload.html"}
    for html_path in frontend.glob("*.html"):
        if html_path.name in public_standalone_pages:
            continue
        html = html_path.read_text(encoding="utf-8")
        assert "/js/common.js" in html
        assert 'src="/js/common.js?v=20260616-speed-common"' in html
        common_script_order = [
            "/js/common/foundation.js",
            "/js/common/theme.js",
            "/js/common/area_focus.js",
            "/js/common/runtime.js",
            "/js/common/app_log.js",
            "/js/common/telemetry.js",
            "/js/common/access.js",
            "/js/common/sidebar.js",
            "/js/common/uploads.js",
            "/js/common/demo_prefetch_init.js",
            "/js/common/import_tools.js",
            "/js/common/table_sort.js",
            "/js/common/date_state.js",
            "/js/common.js",
        ]
        positions = [html.index(script) for script in common_script_order]
        assert positions == sorted(positions)


def test_uploads_file_actions_are_explicit_download_or_open():
    frontend = ROOT / "app" / "frontend"
    allocation_tools = read_allocation_frontend(frontend)
    coredata_router = (ROOT / "app" / "backend" / "routers" / "coredata.py").read_text(encoding="utf-8")

    assert "data-preview-file-key" not in allocation_tools
    assert "data-preview-file-source" not in allocation_tools
    assert "data-download-persistent-file" in allocation_tools
    assert "data-download-local-file" in allocation_tools
    assert "data-open-local-ref" in allocation_tools
    assert "data-open-local-folder" in allocation_tools
    assert "/api/desktop/files/${encodeURIComponent(entry.localRef)}/open" in allocation_tools
    assert '@router.get("/files/{file_key}/download")' in coredata_router
    assert "download_coredata_file" in coredata_router


def test_data_fetch_plan_columns_are_user_editable():
    frontend = ROOT / "app" / "frontend"
    html = (frontend / "hamta-data.html").read_text(encoding="utf-8")
    data_fetch = (frontend / "js" / "data_fetch.js").read_text(encoding="utf-8")
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    assert ">Tolka</button>" in html
    assert "Tolka med MiniMax</button>" not in html
    assert 'id="dataFetchMaxRows" type="number" min="1" max="5000" />' in html
    assert 'id="dataFetchMaxRows" type="number" min="1" max="5000" value=' not in html
    assert 'src="/js/data_fetch.js?v=20260615-calculation"' in html
    assert 'id="dataFetchRun" type="button" disabled' in html
    assert 'id="dataFetchExport" type="button" disabled' in html
    assert "dataFetchUpdateActions" in data_fetch
    assert 'document.getElementById("dataFetchMaxRows").value || 500' not in data_fetch
    assert "if (!rawValue) return null;" in data_fetch
    assert "dataFetchBusinessId" in data_fetch
    assert "payload.business_id = businessId" in data_fetch
    assert "resetDataFetchForPromptEdit" in data_fetch
    assert '!dataFetchState.result?.session_id' in data_fetch
    assert "pendingRemovedColumns" in data_fetch
    assert "data-remove-column" in data_fetch
    assert "data-update-columns" in data_fetch
    assert "updateDataFetchPlanColumns" in data_fetch
    assert "renderDataFetchResult(null)" in data_fetch
    assert "renderDataFetchCalculationPlan" in data_fetch
    assert "renderDataFetchCalculationResult" in data_fetch
    assert "Minst en kolumn måste vara kvar." in data_fetch
    assert ".data-fetch-chip.is-removing" in styles
    assert ".data-fetch-column-actions" in styles
    assert ".data-fetch-calculation-result" in styles


def test_area_focus_toggle_is_wired_to_views():
    frontend = ROOT / "app" / "frontend"
    common = read_common_frontend(frontend)
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")
    schedule = read_schedule_frontend(frontend)
    overview = (frontend / "js" / "overview.js").read_text(encoding="utf-8")
    productivity_overview = (frontend / "js" / "productivity_overview.js").read_text(encoding="utf-8")
    persons = (frontend / "js" / "persons.js").read_text(encoding="utf-8")
    activities = (frontend / "js" / "activities.js").read_text(encoding="utf-8")
    users = (frontend / "js" / "users.js").read_text(encoding="utf-8")
    schedule_html = (frontend / "index.html").read_text(encoding="utf-8")
    overview_html = (frontend / "overblick.html").read_text(encoding="utf-8")
    productivity_html = (frontend / "produktivitet.html").read_text(encoding="utf-8")

    assert "flow-area-focus" in common
    assert '<button class="area-focus-toggle" id="area-focus-toggle"' in common
    assert '<select class="area-focus-toggle"' not in common
    assert "AREA_FOCUS_OPTIONS" not in common
    assert "AREA_FOCUS_FALLBACK_NAMES" not in common
    assert 'const AREA_FOCUS_ALL_OPTION = { value: "ALLT"' in common
    assert 'const preferredOrder = ["MG", "GG", "AS", "EH", "R3"]' not in common
    assert 'label: "∞"' in common
    assert "function nextAreaFocus" in common
    assert 'toggle.addEventListener("click", () => writeAreaFocus(nextAreaFocus()))' in common
    assert 'toggle.addEventListener("contextmenu", (event) => openAreaFocusMenu(event, user))' in common
    assert 'menu.className = "area-focus-menu"' in common
    assert "handleAreaFocusMenuDocumentClick" in common
    assert "handleAreaFocusMenuWindowScroll" in common
    assert 'menu.addEventListener("click", (event) => event.stopPropagation())' in common
    assert 'menu.addEventListener("wheel", (event) => event.stopPropagation(), { passive: true })' in common
    assert "areaFocusMenuOptions" in common
    assert 'loadAreaFocusAreas(user)' in common
    assert "preferredAreaIdFromFocus" in common
    assert "function areaFocusValueForArea" in common
    assert 'writeAreaFocus("ALLT")' not in common
    assert 'writeAreaFocus(normalizeAreaFocus(""))' in common
    assert "visibleAreas.some((area) => Number(area?.id) === areaId)" in common
    assert "buildAreaFocusOptions" in common
    assert "function isAllAreasMarker" in common
    assert "function hasAllAreasMarker" in common
    assert ".filter((area) => !isAllAreasMarker(area))" in common
    assert "hasAllAreasMarker(activeAreas)" in common
    assert 'code: null, areaId: null' in common
    assert 'value: "ALLT"' in common
    assert 'areaFocusLoadState = "error"' in common
    assert "dynamicAreaFocusOptions = []" in common
    assert "toggle.disabled = disabled" in common
    assert 'window.areaFocusAreaId = areaFocusAreaId' in common
    assert "preferredActivityAreaId" in common
    assert "return preferredAreaIdFromFocus(areas);" in common
    assert "compareActivitiesForAreaFocus" in common
    assert "comparePersonsForAreaFocus" in common
    assert ".area-focus-toggle" in styles
    assert ".area-focus-toggle:disabled" in styles
    assert ".area-focus-toggle.is-error" in styles
    assert ".area-focus-menu" in styles
    assert "overscroll-behavior: contain" in styles
    assert ".area-focus-menu button[aria-checked=\"true\"]" in styles

    assert "CALC_AREA_FALLBACK_KEYS" not in schedule
    assert "function calcAreaKeys" not in schedule
    assert "calc-panel-manual" in schedule
    assert "Manuell</div>" in schedule
    assert "function openCalculatorModal" in schedule
    calculator_modal = schedule.split("function openCalculatorModal", 1)[1].split("async function deleteAutomaticCalculator", 1)[0]
    assert 'backdrop.querySelector("#calcCancel").addEventListener("click", close);' in calculator_modal
    assert "event.target === backdrop" not in calculator_modal
    assert "function setupCalculatorToolbar" in schedule
    assert 'id="calcAddAutomaticBtn"' in schedule_html
    assert 'id="calcImportUser"' in schedule_html
    assert '"/api/schedule/calculator-profile"' in schedule
    assert "`/api/schedule/calculator/automatic" in schedule
    assert "`/api/schedule/activity-capacity/cell?${params.toString()}`" in schedule
    assert "SCHEDULE_ACTIVITY_CAPACITY_HOVER_DELAY_MS = 250" in schedule
    assert "function attachActivityCapacityHover" in schedule
    assert "function scheduleActivityCapacityHover" in schedule
    assert "function loadActivityCapacityTooltip" in schedule
    assert "function setupActivityCapacityHover" in schedule
    assert 'id="capacityToggleBtn"' not in schedule_html
    assert "V+H" not in schedule_html
    assert "button.capacity-toggle.active" not in styles
    assert ".schedule-capacity-tooltip" in styles
    assert 'preferredAreaIdFromFocus(state.areas) : null' in schedule
    assert 'preferredAreaIdFromFocus(state.areas) : null' in overview
    assert "setAreaFocusAreas(areas, state.currentUser)" in schedule
    assert "setAreaFocusAreas(areas, state.currentUser)" in overview
    assert "compareActivitiesForAreaFocus(a, b, state.areas, state.currentUser?.area_id)" in schedule
    assert "compareActivitiesForAreaFocus(a, b, state.areas, state.currentUser?.area_id)" in overview
    assert "const scheduleAreaCache = new Map();" in schedule
    assert "function scheduleAreaCacheKey" in schedule
    assert "function renderScheduleFromCache" in schedule
    assert "api.get(scheduleUrl(null), { signal: controller.signal, cacheTtlMs: 25 * 1000 })" in schedule
    assert "setScheduleAllCache(baseKey, allData)" in schedule
    assert "setScheduleAreaCache(scheduleAreaCacheKey(requestedAreaId, baseKey), cachedData)" in schedule
    assert "applyScheduleData(cachedData)" in schedule
    assert 'class="productivity-col"' in schedule_html
    assert "function loadScheduleProductivity" in schedule
    assert "`/api/schedule/productivity-summary?year=${state.year}&week=${state.week}&weekday=${state.weekday}`" in schedule
    assert "function buildScheduleProductivityMapFromSummary" in schedule
    assert "scheduleProductivityStatusClass(percent)" in schedule
    assert "function shouldShowScheduleProductivityValue" in schedule
    assert "percent > 0" in schedule
    assert "!value || !shouldShowScheduleProductivityValue(value)" in schedule
    assert ".schedule-productivity-value.low" in styles
    assert ".schedule-productivity-value.warn" in styles
    assert ".schedule-productivity-value.good" in styles
    assert "function openScheduleLoanMenu" in schedule
    assert "function scheduleLoanTargetOptions" in schedule
    assert "function scheduleLoanStartHour" in schedule
    assert "function localYmdString" in schedule
    assert "function selectedScheduleYmdString" in schedule
    assert "function scheduleLoanStartHint" in schedule
    assert "return HOURS[0]" not in schedule
    assert "Klicka först på timmen där flytten ska börja" in schedule
    assert "function scheduleLoanCellsForHour(personId, hour, areaId)" in schedule
    assert "selectedPersonId" in schedule
    assert "function selectPersonRow" in schedule
    assert "person-row-selected" in schedule
    assert "selectedPersonId" in overview
    assert "function selectPersonRow" in overview
    assert "person-row-selected" in overview
    assert "tr.person-row-selected" in styles
    assert "async function sendPersonToArea" in schedule
    assert 'action: "loan_to_area"' in schedule
    assert "loan_area_id" in schedule
    assert "Number(cell.loan_area_id) === selectedAreaId" in schedule
    assert "loan_area_id: Number(areaId)" in schedule
    assert "Tomt från" in schedule
    assert "Skicka till" in schedule
    assert "schedule-loan-enabled" in schedule
    assert ".schedule-loan-menu" in styles
    assert "const overviewAreaCache = new Map();" in overview
    assert "function overviewAreaCacheKey" in overview
    assert "function renderOverviewFromCache" in overview
    assert "api.get(overviewUrl(null), { signal: controller.signal, cacheTtlMs: 25 * 1000 })" in overview
    assert "setOverviewAllCache(baseKey, allData)" in overview
    assert "setOverviewAreaCache(overviewAreaCacheKey(requestedAreaId, baseKey), cachedData)" in overview
    assert "applyOverviewData(cachedData)" in overview
    assert '"flow:areaFocusChanged"' in schedule
    assert '"flow:areaFocusChanged"' in overview
    assert '"flow:areaFocusChanged"' in persons
    assert '"flow:areaFocusChanged"' in activities
    assert '"flow:areaFocusChanged"' in users
    assert "matchesAreaFocus" in activities
    assert "matchesAreaFocus" in persons
    assert "matchesAreaFocus" in users
    assert 'params.set("area_id", String(areaId))' in persons
    assert 'api.get(`/api/persons${query ? `?${query}` : ""}`)' in persons
    assert 'window.addEventListener("flow:areaFocusChanged", () => loadPersons())' in persons
    assert "PRODUCTIVITY_GROUPS" not in productivity_overview
    assert "productivity-matrix" not in productivity_overview
    assert 'id="areaSelect"' not in schedule_html
    assert 'id="areaSelect"' not in overview_html
    assert 'id="productivityGroupFilter"' not in productivity_html
    assert 'id="calcAreaSelect"' not in schedule_html
    assert "productivityGroupFilter" not in productivity_overview


def test_plain_view_tables_get_clickable_sort_headers():
    frontend = ROOT / "app" / "frontend"
    common = read_common_frontend(frontend)
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    assert "function setupClientSortableTable" in common
    assert "function sortClientTableByHeader" in common
    assert "function clientTableSortToken" in common
    assert "function scheduleClientTableResort" in common
    assert "cell.style.background || cell.style.backgroundColor" in common
    assert "setupClientSortableTables(document)" in common
    assert "new MutationObserver" in common
    assert "window.setupClientSortableTables = setupClientSortableTables" in common
    assert "client-sortable-table" in common
    assert "client-sortable-header" in common
    assert "aria-sort" in common
    assert 'table.matches(CLIENT_TABLE_SORT_EXCLUDE_SELECTOR)' in common
    assert '"table.matrix"' in common
    assert '"table.overview"' in common
    assert '"table.businesses-table"' in common
    assert '"table.business-areas-table"' in common
    assert '"table.bulk-import-table"' in common
    assert '"table.role-access-table"' in common
    assert '"table.meta-admin-table"' in common
    assert 'table.querySelector("tr.sort-row")' in common
    assert 'table.closest(".modal, [class*=\'allocation-\']")' in common
    assert "table.client-sortable-table th.client-sortable-header" in styles
    assert "table.client-sortable-table th.client-sortable-header:hover" in styles


def test_bearbeta_area_focus_filter_contract():
    allocation = read_allocation_frontend()
    common = read_common_frontend()
    styles = (ROOT / "app" / "frontend" / "css" / "styles.css").read_text(encoding="utf-8")
    settings_html = (ROOT / "app" / "frontend" / "installningar.html").read_text(encoding="utf-8")
    terminology_wiki = (ROOT / "wiki" / "terminology.md").read_text(encoding="utf-8")
    warehouse_wiki = (ROOT / "wiki" / "warehouse-tools.md").read_text(encoding="utf-8")
    staffing_wiki = (ROOT / "wiki" / "bemanning-schedule.md").read_text(encoding="utf-8")

    assert "ALLOCATION_PROCESS_MATRIX" in allocation
    assert 'const ALLOCATION_PROCESS_AREA_OPTIONS = [\n  { code: "ALLT", label: "Alla" },\n];' in allocation
    assert 'GG: {' not in allocation
    assert "Filter: Bolag GG, exkl. kundnr 6005" not in allocation
    assert "Filter: Bolag MG, exkl. kundnr 40002 och 90002" not in allocation
    assert "data-matrix-company" not in allocation
    assert "data-matrix-exclude" not in allocation
    assert 'const ALLOCATION_PROCESS_AREA_PARAM = "__process_area_focus"' in allocation
    assert 'const ALLOCATION_USER_FILTERS_PARAM = "__allocation_user_filters_json"' in allocation
    assert 'areaCode === "MG" ? 205' not in allocation
    assert 'MG: allocationDefaultYtgenereringAreaRule("MG")' not in allocation
    assert 'rows.push([areas, "MG", orderNumber, "A"])' not in allocation
    assert "orderCompanies" in allocation
    assert "formData.append(ALLOCATION_PROCESS_AREA_PARAM, focusCode)" in allocation
    assert "appendAllocationFilterProfile(fd)" in allocation
    assert "appendAllocationAreaFocus(fd)" in allocation
    assert 'allocationJson(`${ALLOCATION_API}/process-matrix${query}`)' in allocation
    assert 'allocationJson(`${ALLOCATION_API}/process-matrix${query}`, {' in allocation
    assert "function allocationScopedQuery" in allocation
    assert "window.areaFocusBusinessId = areaFocusBusinessId" in common
    assert 'allocationJson(`${ALLOCATION_API}/filter-profile`)' in allocation
    assert 'allocationJson(`${ALLOCATION_API}/filter-profile/import`, {' in allocation
    assert 'canViewPage?.(allocationState.user, "allocationProcessMatrix")' in allocation
    assert 'canEditPage?.(allocationState.user, "allocationProcessMatrix")' in allocation
    assert 'id="allocation-process-matrix">Matris</button>' not in allocation
    assert '{ id: "process-matrix", label: "Bearbeta" }' in allocation
    assert "renderAllocationProcessMatrixSettingsPanel" in allocation
    assert 'id="allocation-process-matrix-settings-editor"' in allocation
    assert 'id="allocation-process-matrix-settings-save">Spara</button>' in allocation
    assert 'canViewPage(user, "allocationSettings")' in common
    assert 'canViewPage(user, "staffingSettings")' in common
    assert 'canViewPage(user, "allocationProcessMatrix")' in common
    assert 'canViewPage(user, "productivityFinanceSettings")' in common
    assert 'data-flow-filter="${allocationEscape(flow.id)}"' in allocation
    assert "allocation-flow-filter" in allocation
    assert "allocation-filter-modal" in styles
    assert "allocation-filter-layout" in styles
    assert "allocation-source-mode-toggle" in styles
    assert "allocation-source-switch-track" in styles
    assert "allocation-source-switch-knob" in styles
    assert "input:checked + .allocation-source-switch-track" in styles
    assert "data-filter-source-mode-toggle" in allocation
    assert "normalizeAllocationSourceModes" in allocation
    assert "function allocationProcessToggleCode" in allocation
    assert "function allocationYtgenereringEditableAreasForCurrentToggle" in allocation
    assert "allocationSourceModeForFile" in allocation
    assert "allocationSourceUsesUpload" in allocation
    assert "allocationVisibleFlowsNeedCoreDataStatus" in allocation
    assert "allocationVisibleFlowsNeedStoredFiles" in allocation
    assert 'draft.flows[flowId].sources[source.key] = "upload"' in allocation
    assert 'const entry = apiReady ? null : allocationState.files[key]' in allocation
    assert 'const entry = apiReady ? null : allocationPersistentStatusFile(input.key)' in allocation
    assert "width: min(1480px, calc(100vw - 96px));" in styles
    assert "grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);" in styles
    assert "title=\"${allocationEscape(columnType)}\"" in allocation
    assert "${allocationEscape(columnLabel)} ${column.type" not in allocation
    assert "openAllocationFlowFilterModal" in allocation
    assert '"settings") return "allocationSettings"' in allocation
    assert "renderAllocationMapSettingsView" in allocation
    assert 'const STAFFING_SETTINGS_API = "/api/settings/staffing"' in allocation
    assert 'const PRODUCTIVITY_FINANCE_SETTINGS_API = "/api/settings/productivity-finance"' in allocation
    assert "Avancerad filfiltrering" in terminology_wiki
    assert "openAllocationFlowFilterModal" in terminology_wiki
    assert "__allocation_user_filters_json" in terminology_wiki
    assert "/api/allokering/filter-profile/import" in terminology_wiki
    assert "allocation_bridge.apply_user_flow_filters" in terminology_wiki
    assert "Avancerad filfiltrering" in warehouse_wiki
    assert "Avancerad filfiltrering" in staffing_wiki
    assert "API/Uppladdning-val" in staffing_wiki
    assert 'data-settings-tab="${allocationEscape(tab.id)}"' in allocation
    assert 'data-staffing-history-hours' in allocation
    assert "activity_capacity_activity_ids" in allocation
    assert "loadStaffingActivities" in allocation
    assert "data-staffing-capacity-all" in allocation
    assert "data-staffing-capacity-activity" in allocation
    assert "staffing-capacity-activity-grid" in styles
    assert 'anyViewIds: ["allocationSettings", "staffingSettings", "allocationProcessMatrix", "productivityFinanceSettings"]' in allocation
    assert "canEditStaffingSettings" in allocation
    assert "canEditProductivityFinanceSettings" in allocation
    assert '{ id: "productivity-finance", label: "Intäkt/utgift" }' in allocation
    assert "data-productivity-finance-hourly-cost" in allocation
    assert "productivity-finance-settings-heading" in allocation
    assert "productivity-finance-settings-actions" in allocation
    assert "data-productivity-finance-company-rate" in allocation
    assert "data-productivity-finance-invoice-row" in allocation
    assert "data-productivity-finance-row-price" in allocation
    assert "data-productivity-finance-row-quantity" in allocation
    assert "openProductivityFinanceContextMenu" in allocation
    assert "data-action=\"calculation\"" in allocation
    assert "data-action=\"check\"" in allocation
    assert "data-action=\"link-process\"" in allocation
    assert "openProductivityFinanceProcessLinkDialog" in allocation
    assert "openProductivityFinanceProcessCheckDialog" in allocation
    assert "requestProductivityFinanceProcessCheck" in allocation
    assert "data-linked-process-key" in allocation
    assert "linked_process_key" in allocation
    assert "productivityFinanceProcessCheckSameView" in allocation
    assert "data-productivity-finance-calculation-month" in allocation
    assert "company_code: companyCode" in allocation
    assert "data-productivity-finance-process-check" in allocation
    assert "data-productivity-finance-process-check-dialog-month" in allocation
    assert "data-productivity-finance-process-check-dialog-company" in allocation
    assert "data-productivity-finance-process-check-dialog-result" in allocation
    assert "data-productivity-finance-process-check-link-save" in allocation
    assert "data-productivity-finance-check-link-process" in allocation
    assert "data-productivity-finance-process-combobox" in allocation
    assert "renderProductivityFinanceProcessDatalist" in allocation
    assert "data-productivity-finance-process-check-sql-details" in allocation
    assert "renderProductivityFinanceProcessCheckSqlDetails" in allocation
    assert "productivityFinanceProcessCheckCombinedCoverage" in allocation
    assert "Processkombination" in allocation
    assert "combined_process_coverage" in allocation
    assert "Process-SQL" in allocation
    assert "Intäkts-SQL" in allocation
    assert "productivity-finance-process-check-modal-head" in allocation
    assert "productivity-finance-process-check-x" in allocation
    assert 'aria-label="Stäng"' in allocation
    assert 'class="secondary" data-productivity-finance-process-check-close>Stäng</button>' not in allocation
    assert "${PRODUCTIVITY_FINANCE_SETTINGS_API}/process-check" in allocation
    assert "productivity-finance-process-check-result" in styles
    assert "productivity-finance-process-check-modal" in styles
    assert "productivity-finance-process-check-modal-head" in styles
    assert "productivity-finance-process-check-modal-tools" in styles
    assert "productivity-finance-process-check-x" in styles
    assert "productivity-finance-process-check-link-panel" in styles
    assert "productivity-finance-process-check-link-chip" in styles
    assert "productivity-finance-process-check-sql-panel" in styles
    assert "productivity-finance-process-check-combination" in styles
    assert "productivity-finance-row-context-menu" in styles
    assert "productivity-finance-process-link-modal" in styles
    assert "productivity-finance-row-check-button" not in styles
    assert "data-productivity-finance-row-process-check" not in allocation
    assert "${renderProductivityFinanceProcessCheckResult()}" not in allocation
    assert "productivity-finance-process-check-same-view" in styles
    finance_calculation_dialog = allocation.split("function openProductivityFinanceCalculationDialog", 1)[1].split(
        "function renderProductivityFinanceSettingsPanel",
        1,
    )[0]
    assert "event.target === backdrop" not in finance_calculation_dialog
    assert "Dialogregel for frontend" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "ST / Antal" in allocation
    assert "invoice_rows_by_company" in allocation
    assert "Blue collar" in allocation
    assert "White collar" in allocation
    assert "productivity-finance-company-grid" in styles
    assert "productivity-finance-invoice-table" in styles
    assert "ytgenerering-map-layout" in allocation
    assert "availableLocations" in allocation
    assert "allocationMapLayoutSaveSignature" in allocation
    assert "Servern bekräftade inte ytkartsändringarna" in allocation
    assert "allocationMapLayoutSeriesRows" in allocation
    assert "function allocationMapLayoutSizeForCapacity" in allocation
    assert "data-map-add-series" in allocation
    assert "data-map-add-location" in allocation
    assert "application/x-flow-yt-location" in allocation
    assert "addLocationRowAt" in allocation
    assert "data-map-zoom-in" in allocation
    assert "data-map-zoom-out" in allocation
    assert "data-map-fit" in allocation
    assert "data-map-settings-fullscreen" in allocation
    assert "data-map-snap-guides" in allocation
    assert "function clampMapSettingsViewBox" in allocation
    assert "Math.min(bounds.width, current.width * factor)" in allocation
    assert "viewBox = clampMapSettingsViewBox(viewBox)" in allocation
    assert "function snapTargetsForDrag" in allocation
    assert "function applySnapToDrag" in allocation
    assert "function mapSettingRowAtClientPoint" in allocation
    assert "const MAP_SNAP_SCREEN_PX = 4" in allocation
    assert "updateMapSnapGuides(guides, dragState.viewBox)" in allocation
    assert "snapTargets: snapTargetsForDrag()" in allocation
    assert "data-map-selection-count" in allocation
    assert "handleMapSettingsKeydown" in allocation
    assert "selectedLocations" in allocation
    assert "allocation-map-settings-svg" in allocation
    assert ".allocation-map-settings-page-panel" in styles
    assert ".allocation-settings-tabs" in styles
    assert ".allocation-staffing-settings-panel" in styles
    assert ".allocation-map-settings-fullscreen-button" in styles
    assert ".allocation-map-settings-canvas.is-drop-target" in styles
    assert ".allocation-map-settings-guide-line" in styles
    assert "function allocationMapSettingLabelAttrs" in allocation
    assert "const ALLOCATION_MAP_LOAD_DIRECTIONS" in allocation
    assert "function allocationNormalizeMapLoadDirection" in allocation
    assert "function allocationMapLoadDirectionsForRow" in allocation
    assert 'horizontal: ["right", "left"]' in allocation
    assert 'vertical: ["down", "up"]' in allocation
    assert "function allocationMapLoadOriginSide" in allocation
    assert "allocationMapShortLocation(row.location)" in allocation
    assert "row.w >= row.h" in allocation
    assert "allocationMapClamp(shortSide * 0.58, 16, 48)" in allocation
    assert "function allocationMapSettingDirectionMarkerBand" in allocation
    assert "const cx = row.x + row.w / 2" in allocation
    assert "const maxWidth = Math.max(8, longSide - 8)" in allocation
    assert 'rotate(-90, ${cx}, ${cy})' in allocation
    assert "L${row.x + band} ${cy}Z" in allocation
    assert "allocationRenderMapSettingLabel(item)" in allocation
    assert "allocationUpdateMapSettingLabelElement(item.label, item.row)" in allocation
    assert "allocationRenderMapSettingDirectionArrow(item)" in allocation
    assert "allocationRotateMapLoadDirectionLeft" in allocation
    assert "function rotateLocationLeft" in allocation
    assert "function cycleSelectedLoadDirections" in allocation
    assert "data-map-context-direction" in allocation
    assert "function positionMapSettingsContextMenu" in allocation
    assert 'menu.style.position = "absolute"' in allocation
    assert "workspace.appendChild(menu)" in allocation
    assert "document.body.appendChild(menu)" not in allocation
    assert "allocation_tools.js?v=20260614-allocation-modules" in settings_html
    assert 'svg?.addEventListener("contextmenu"' in allocation
    assert "allocationNextMapLoadDirection(row.loadDirection, row)" in allocation
    assert "allocationMapLoadOriginSide(loc.loadDirection, loc)" in allocation
    assert ".allocation-map-setting-label" in styles
    assert ".allocation-map-setting-label {\n  dominant-baseline: middle;\n  font-family: inherit;\n  fill: var(--text);\n  font-size: 32px;\n  font-weight: 400;" in styles
    assert ".allocation-map-setting-direction-arrow" in styles
    assert ".allocation-map-settings-context-menu" in styles
    assert ".allocation-map-settings-context-menu {\n  position: absolute;" in styles
    assert "fill: #94a3b8;" in styles
    assert "allocation-process-matrix-table" in allocation
    assert "Ytgenerering UTL" not in allocation
    assert "data-matrix-utl-min" not in allocation
    assert "data-matrix-utl-max" not in allocation
    assert "ALLOCATION_YTGENERERING_SETTINGS_SOURCE" in allocation
    assert "data-ytgenerering-utl-min" in allocation
    assert "data-ytgenerering-carrier-add" in allocation
    assert "host.__allocationYtgenereringBaseAreas = areas" in allocation
    assert "editableCarrier: true" in allocation
    assert ".allocation-ytgenerering-utl-grid" in styles
    assert "allocationResultMaps" in allocation
    assert "setupAllocationWarehouseMap" in allocation
    assert "data-map-export-ask" in allocation
    assert "requestFullscreen" in allocation
    assert "minScale: 0.05" in allocation
    assert "function fittedMapScale" in allocation
    assert "function clampTransform" in allocation
    assert "state.transform.scale = allocationMapClamp(state.transform.scale || state.minScale, state.minScale, 5)" in allocation
    assert "const nextScale = allocationMapClamp(state.transform.scale * factor, state.minScale, 5)" in allocation
    assert "minmax(340px, 440px)" in styles
    assert "max-width: 260px" in styles
    assert "allocation-map-fullscreen-button" in allocation
    assert ".allocation-map-fullscreen-button" in styles
    assert "data-map-unused-stripes" in allocation
    assert "allocation-map-unused" in allocation
    assert ".allocation-map-unused" in styles
    assert "allocationMapShortLocation" in allocation
    assert "allocationMapMixHexColor" in allocation
    assert "unusedPatternBase" in allocation
    assert "unusedPatternBand" in allocation
    assert "ALLOCATION_CARRIER_CLUSTER_DEFAULTS" in allocation
    assert "allocationRegisterCarrierClusterDefaults([39, 40]" in allocation
    assert 'clusterGroup: "Freja", assignmentOrder: "10", startSeq: "600", endSeq: "652"' in allocation
    assert 'asn: "09:00", arrive: "11:00", depart: "13:00", color: "#c4b5fd"' in allocation
    assert "allocationCarrierClusterDefaults" in allocation
    assert "allocationCarrierClusterIdentifier" in allocation
    assert "allocationMapLabelLines" in allocation
    assert 'document.createElementNS(ALLOCATION_MAP_NS, "tspan")' in allocation
    assert "const contentRect = { x: loc.x, y: loc.y, w: loc.w, h: loc.h }" in allocation
    assert "horizontal ? contentRect.w - 10 : contentRect.h - 10" in allocation
    assert 'elements.mainText.setAttribute("transform", `rotate(-90, ${contentX}, ${contentY})`)' in allocation
    assert "allocation-map-label-edge" in allocation
    assert ".allocation-map-label-edge" in styles
    assert "paint-order: stroke" not in styles
    assert "stroke: rgba(255, 255, 255" not in styles
    assert 'elements.metaText.textContent = "";' in allocation
    assert '${assignment.placedPallets}/${assignment.maxPall || "?"} pall' not in allocation
    assert 'unusedPattern.setAttribute("patternTransform", "rotate(45)")' in allocation
    assert 'allocationMapMixHexColor(color, "#ffffff", 0.72)' in allocation
    assert 'allocationMapMixHexColor(color, "#ffffff", 0.36)' in allocation
    assert 'fill="#ffffff" opacity="0.78"' not in allocation
    assert "M-5 18L18 -5" not in allocation
    assert "Återställ vy" in allocation
    assert "Fullskärm" in allocation
    assert ">Fullskärm</button>" not in allocation
    assert "Sök UTL, sändning eller transportör" in allocation
    assert "Över kapacitet" in allocation
    assert "Lediga pallplatser" in allocation
    assert "Lediga ytor" in allocation
    assert "Sändningsnr" in allocation
    assert "Transportör" in allocation
    assert "Okänd" in allocation
    for missing_swedish in ("Aterstall vy", "Fullskarm", "Sok UTL", "Over kapacitet", "Sandningsnr", "Transportor"):
        assert missing_swedish not in allocation
    assert 'aria-keyshortcuts="Control+C Control+X Control+V Control+Z"' in allocation
    assert "function copySelectedAssignment" in allocation
    assert "function pasteMapClipboard" in allocation
    assert "function undoMapMutation" in allocation
    assert 'host.addEventListener("keydown", handleMapShortcut)' in allocation
    assert ".allocation-map-block:focus-visible .allocation-warehouse-map" in styles
    assert ".allocation-map-loc.is-clipboard-source" in styles
    assert "Redigera kluster" in allocation
    assert "carrier_clusters_json" in allocation
    assert "openAllocationCarrierClusterModal" in allocation
    assert "allocationCarrierClustersFromForecastTable" in allocation
    assert "generated: true" in allocation
    # Kluster-popupen: drag-sortering, tidskolumner och färgväljare.
    assert "allocation-cluster-advanced-table" in allocation
    assert "initAllocationCarrierClusterDrag" in allocation
    for advanced_header in (">ASN<", ">Arrive<", ">Depart<", ">Group<", ">Start seq<", ">End seq<", ">Color<"):
        assert advanced_header in allocation
    assert 'type="color" class="adv-color"' in allocation
    assert "ALLOCATION_CLUSTER_DEFAULT_TIMES" in allocation
    # Kundnamn på ytor + klusterfärger med nyanser per transportör.
    assert "assignment.customer || assignment.carrier" in allocation
    assert "function allocationClusterColorMap" in allocation
    assert "function allocationHslToHex" in allocation
    # Saknade kunder-panelen byggd från ej placerade sändningar.
    assert "Saknade kunder" in allocation
    assert "data-map-missing-panel" in allocation
    assert "function renderMissingPanel" in allocation
    assert ".allocation-map-missing-panel" in styles
    assert "function copyMapOverviewShipment" in allocation
    assert "writeClipboardText(assignment.shipment)" in allocation
    assert "Sändningsnummer kopierat" in allocation
    assert "function allocationFlowsForCurrentView" in allocation
    assert 'window.addEventListener("flow:areaFocusChanged", handleAllocationAreaFocusChanged)' in allocation


def test_planning_views_cache_all_scope_and_have_top_scrollbars():
    frontend = ROOT / "app" / "frontend"
    common = read_common_frontend(frontend)
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")
    schedule = read_schedule_frontend(frontend)
    overview = (frontend / "js" / "overview.js").read_text(encoding="utf-8")
    schedule_html = (frontend / "index.html").read_text(encoding="utf-8")
    overview_html = (frontend / "overblick.html").read_text(encoding="utf-8")

    assert "function setupSyncedHorizontalScroll" in common
    assert "window.setupSyncedHorizontalScroll = setupSyncedHorizontalScroll" in common
    assert ".synced-scrollbar-top" in styles
    assert "synced-scrollbar-spacer" in styles
    assert '<table class="matrix" id="scheduleTable">' in schedule_html
    assert '<table class="overview" id="overviewTable">' in overview_html
    assert "function summaryRefreshErrorMessage" in schedule
    assert "summaryRefreshErrorMessage(err)" in schedule
    assert "Orsak:" in schedule
    assert "Kontext:" in schedule

    for source, prefix in ((schedule, "Schedule"), (overview, "Overview")):
        assert f"filter{prefix}DataForArea" in source
        assert f"prefetchAll{prefix}" in source
        if prefix == "Schedule":
            assert "renderScheduleFromCache" in source
            assert "scheduleAreaCache" in source
        else:
            assert "renderOverviewFromCache" in source
            assert "overviewAreaCache" in source
        assert f"invalidate{prefix}AllCache" in source
        assert f"revalidate{prefix}" in source
        assert "function canSortPersonsAcrossAreas" in source
        assert "user.is_super_user || user.is_demo" in source
        assert "setupSyncedHorizontalScroll(document.getElementById" in source
        assert "user.business_id ?? \"global\"" in source
        assert "user.is_super_user ? \"super\" : \"scoped\"" in source

    assert "scheduleUrl(null)" in schedule
    assert "scheduleRevisionUrl(null)" in schedule
    assert "SCHEDULE_REVALIDATE_ACTIVE_MS = 10000" in schedule
    assert "SCHEDULE_REVALIDATE_IDLE_MS = 30000" in schedule
    assert "patchScheduleFromAllData" in schedule
    assert "selectedAreaCellPersonIds" in schedule
    assert "Number(activity.area_id) === selectedAreaId" in schedule
    assert "overviewUrl(null)" in overview
    assert "overviewRevisionUrl(null)" in overview
    assert "OVERVIEW_REVALIDATE_ACTIVE_MS = 10000" in overview
    assert "OVERVIEW_REVALIDATE_IDLE_MS = 30000" in overview
    assert "patchOverviewFromAllData" in overview
    assert "function renderOverviewDayHeader" in overview
    assert 'weekLabel.textContent = `Vecka ${week}`' in overview
    assert "overview-week-label" in styles
    assert "Number(person.home_area_id) === selectedAreaId" in schedule
    assert "Number(person.home_area_id) === selectedAreaId" in overview


def test_presence_print_is_wired_to_both_planning_views():
    frontend = ROOT / "app" / "frontend"
    schedule_html = (frontend / "index.html").read_text(encoding="utf-8")
    overview_html = (frontend / "overblick.html").read_text(encoding="utf-8")
    schedule = read_schedule_frontend(frontend)
    overview = (frontend / "js" / "overview.js").read_text(encoding="utf-8")
    presence = (frontend / "js" / "presence_print.js").read_text(encoding="utf-8")
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    assert '<button id="presenceBtn" type="button">Närvarande</button>' in schedule_html
    assert '<button id="printBtn" type="button">Skriv ut</button>' in schedule_html
    assert '<button id="presenceBtn" type="button">Närvarande</button>' in overview_html
    assert schedule_html.index('id="presenceBtn"') < schedule_html.index('id="undoBtn"')
    assert schedule_html.index('id="presenceBtn"') < schedule_html.index('id="printBtn"') < schedule_html.index('id="undoBtn"')
    assert overview_html.index('id="presenceBtn"') < overview_html.index('id="undoBtn"')
    assert '<script src="/js/presence_print.js"></script>' in schedule_html
    assert '<script src="/js/presence_print.js"></script>' in overview_html
    schedule_script_order = [
        "/js/common.js",
        "/js/presence_print.js",
        "/js/schedule/state.js",
        "/js/schedule/ui_core.js",
        "/js/schedule/activity_capacity.js",
        "/js/schedule/loan.js",
        "/js/schedule/person_order.js",
        "/js/schedule/segments_undo.js",
        "/js/schedule/calculator.js",
        "/js/schedule/rendering.js",
        "/js/schedule/summary.js",
        "/js/schedule/editing.js",
        "/js/schedule/data.js",
        "/js/schedule/rfid.js",
        "/js/schedule/copy_modal.js",
        "/js/schedule/boot.js",
        "/js/schedule.js",
    ]
    positions = [schedule_html.index(script) for script in schedule_script_order]
    assert positions == sorted(positions)
    assert "setupPresencePrintButton(\"presenceBtn\"" in schedule
    assert "setupSchedulePrintButton(\"printBtn\"" in schedule
    assert "getSchedulePrintSelection" in schedule
    assert "ensureActivitySelectOptionsLoaded" in schedule
    assert 'select.dataset.activityOptionsLoaded = "0"' in schedule
    assert 'select.dataset.activityOptionsLoaded === "1"' in schedule
    assert 'empty.textContent = "-";' in schedule
    assert "â€“" not in schedule
    assert "appendActivityOptions(select, includeIds)" in schedule
    assert "setupPresencePrintButton(\"presenceBtn\"" in overview
    assert "function overviewPresenceSelection" in overview
    assert "writeOverviewSelectedDate(selectedDate)" in overview
    assert 'const PRESENCE_API_PATH = "/api/schedule/presence";' in presence
    assert 'value="all" checked' in presence
    assert 'value="current"' in presence
    assert 'params.set("area_id"' in presence
    assert 'params.set("business_id"' in presence
    assert "api.get(presenceQuery(selection, scope)" in presence
    assert "function setupSchedulePrintButton" in presence
    assert 'value="staffing" checked' in presence
    assert 'value="evacuation"' in presence
    assert "Bemanning" in presence
    assert "Utrymning" in presence
    assert "schedulePrintIsInferredLunch" in presence
    assert "schedule-print-cell-text" in presence
    assert "includeSplitTimes: false" in presence
    assert "schedule-print-evacuation-table" in presence
    assert "window.setupSchedulePrintButton = setupSchedulePrintButton;" in presence
    assert "Alla områden" in presence
    assert "groups.map((group)" in presence
    assert "presence-print-group" in presence
    assert "group.business_name" in presence
    assert "window.print()" in presence
    assert "@media print" in styles
    assert "size: A4 landscape" in styles
    assert "body.presence-printing" in styles
    assert ".schedule-print-staffing .schedule-print-matrix" in styles
    assert "white-space: nowrap" in styles
    assert ".schedule-print-summary" in styles
    assert ".schedule-print-status.sick" in styles


def test_super_user_business_fields_are_wired_in_register_ui():
    frontend = ROOT / "app" / "frontend"
    persons = (frontend / "js" / "persons.js").read_text(encoding="utf-8")
    activities = (frontend / "js" / "activities.js").read_text(encoding="utf-8")
    users = (frontend / "js" / "users.js").read_text(encoding="utf-8")
    activities_html = (frontend / "aktiviteter.html").read_text(encoding="utf-8")
    users_html = (frontend / "anvandare.html").read_text(encoding="utf-8")
    businesses = (frontend / "js" / "businesses.js").read_text(encoding="utf-8")
    businesses_html = (frontend / "verksamheter.html").read_text(encoding="utf-8")

    for source in (persons, activities, users):
        assert 'api.get("/api/businesses")' in source
        assert "function businessName" in source
        assert 'label>Verksamhet</label>' in source
        assert 'id="m-business"' in source
        assert "payload.business_id" in source
        assert 'key: "business", label: "Verksamhet"' in source
        assert 'value: business.code' in source

    assert "<th>Verksamhet</th>" in activities_html
    assert "<th>Verksamhet</th>" in users_html
    assert "businessName(a.business_id)" in activities
    assert "businessName(user)" in users
    assert 'initPage("businesses", { requireSuperUser: true })' in businesses
    assert 'api.get("/api/businesses?include_inactive=true")' in businesses
    assert 'api.get("/api/areas?include_inactive=true")' in businesses
    assert 'api.post("/api/businesses", payload)' in businesses
    assert 'api.put(`/api/businesses/${record.id}`, payload)' in businesses
    assert 'class="modal-checkbox"><input id="m-active"' in businesses
    assert 'class="modal-checkbox"><input id="m-area-active"' in businesses
    assert "Kod och namn krävs." not in businesses
    assert "function renderAreasTable" in businesses
    assert "function openAreaModal" in businesses
    assert "function startInlineEdit" in businesses
    assert "function ensureAllAreasMarker" in businesses
    assert 'data-inline-edit="${entityType}"' in businesses
    assert 'data-add-all-areas="${business.id}"' in businesses
    assert 'data-${scope}-sort="${key}"' in businesses
    assert 'data-business-sort="code"' in businesses_html
    assert 'data-business-sort="name"' in businesses_html
    assert 'data-business-sort="company_codes"' in businesses_html
    assert 'data-business-sort="tenant"' in businesses_html
    assert 'editableCell("business", business, "company_codes")' in businesses
    assert 'editableCell("business", business, "tenant")' in businesses
    assert "normalizeCompanyCodes" in businesses
    assert "normalizeTenant" in businesses
    assert 'company_codes: companyCodes' in businesses
    assert 'tenant: tenant || null' in businesses
    assert '/js/businesses.js?v=20260624-showinactive-clientfilter' in businesses_html
    assert 'data-new-area="${business.id}"' in businesses
    assert 'api.post("/api/areas", payload)' in businesses
    assert 'api.put(`/api/areas/${record.id}`, payload)' in businesses
    assert 'api.del(`/api/areas/${area.id}`)' in businesses
    assert "data-edit-business" not in businesses
    assert "data-edit-area" not in businesses
    assert "setAreaFocusAreas(loadedAreas, currentUser)" in businesses
    assert 'id="businesses-body"' in businesses_html
    assert 'id="new-business"' in businesses_html
    assert "Verksamheter och områden" in businesses_html


def test_frontend_knows_bemanningsansvarig_role():
    frontend = ROOT / "app" / "frontend"
    common = read_common_frontend(frontend)
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


def test_frontend_keeps_lager_and_artikelplacering_out_of_flow_and_bearbeta():
    frontend = ROOT / "app" / "frontend"
    common = read_common_frontend(frontend)
    schedule = read_schedule_frontend(frontend)
    allocation = read_allocation_frontend(frontend)

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


def test_frontend_denied_view_redirect_uses_accessible_page_not_fixed_loop():
    common = read_common_frontend()

    assert "refreshRoleViewAccessForRouting" in common
    assert "firstAccessiblePageHref" in common
    assert "resolvePostAuthPage" in common
    assert "clearAuthNavigationCache" in common
    assert "redirectAfterDeniedAccess" in common
    assert 'redirectAfterDeniedAccess(user, "Sidan kräver behörighet", activePage)' in common
    assert 'window.location.href = options.denyRedirect || "/index.html"' not in common
    assert 'window.location.href = options.denyRedirect || "/overblick.html"' not in common


def test_login_pages_resolve_first_authorized_view_after_auth():
    frontend = ROOT / "app" / "frontend"
    login = (frontend / "login.html").read_text(encoding="utf-8")
    set_password = (frontend / "set-password.html").read_text(encoding="utf-8")

    assert "async function nextPage(user)" in login
    assert "await resolvePostAuthPage(user)" in login
    assert "window.location.href = await nextPage(user)" in login
    assert 'return user?.must_change_password ? "/set-password.html" : "/index.html";' not in login
    assert "await resolvePostAuthPage(user)" in set_password


def test_import_views_have_templates_and_help_buttons():
    frontend = ROOT / "app" / "frontend"
    common = read_common_frontend(frontend)
    api_js = (frontend / "js" / "api.js").read_text(encoding="utf-8")
    persons_html = (frontend / "personer.html").read_text(encoding="utf-8")
    persons_js = (frontend / "js" / "persons.js").read_text(encoding="utf-8")
    users_html = (frontend / "anvandare.html").read_text(encoding="utf-8")
    users_js = (frontend / "js" / "users.js").read_text(encoding="utf-8")
    activities_html = (frontend / "aktiviteter.html").read_text(encoding="utf-8")
    activities_js = (frontend / "js" / "activities.js").read_text(encoding="utf-8")

    assert "setupImportHelpButton" in common
    assert "openBulkImportGrid" in common
    assert "bulkImportRequirementMeta" in common
    assert "bulkImportRequirementLabel" in common
    assert 'label: required ? "Obligatoriskt" : "Frivilligt"' in common
    assert "bulk-import-head-requirement" in common
    assert 'aria-required="true"' in common
    assert "Importen kan göras via Excel-mallen eller direkt i vyn" in common
    assert "async function download" in api_js
    assert "URL.createObjectURL(blob)" in api_js

    assert 'id="bulk-persons"' in persons_html
    assert 'id="download-person-template"' in persons_html
    assert 'id="person-import-help"' in persons_html
    assert "/api/persons/import-rows" in persons_js
    assert "openBulkPersonsModal" in persons_js
    assert re.search(r'key:\s*"name",\s*label:\s*"Namn",\s*required:\s*true', persons_js)
    assert re.search(r'key:\s*"noman",\s*label:\s*"NoMan",\s*required:\s*true', persons_js)
    assert re.search(r'key:\s*"rfid_code",\s*label:\s*"RFID",\s*required:\s*false', persons_js)
    assert re.search(r'key:\s*"home_area",\s*label:\s*"[^"]+",\s*required:\s*false', persons_js)
    assert 'setupImportHelpButton("person-import-help", "Importera personer")' in persons_js
    assert 'api.download("/api/persons/import-template", "personer-importmall.xlsx")' in persons_js
    assert 'window.location.href = "/api/persons/import-template"' not in persons_js

    assert 'id="bulk-users"' in users_html
    assert "+ Flera nya användare" in users_html
    assert 'id="download-user-template"' in users_html
    assert 'id="role-view-access"' in users_html
    assert 'id="user-import-help"' in users_html
    assert "/api/users/import-rows" in users_js
    assert "openBulkUsersModal" in users_js
    assert re.search(r'key:\s*"username",\s*label:\s*"[^"]+",\s*required:\s*true', users_js)
    assert re.search(r'key:\s*"role",\s*label:\s*"Roll",\s*required:\s*true,\s*type:\s*"select"', users_js)
    assert re.search(r'key:\s*"display_name",\s*label:\s*"Visningsnamn",\s*required:\s*false', users_js)
    assert 'setupImportHelpButton("user-import-help", "Importera användare")' in users_js
    assert 'api.download("/api/users/import-template", "anvandare-importmall.xlsx")' in users_js
    assert 'window.location.href = "/api/users/import-template"' not in users_js
    assert "openRoleAccessModal" in users_js
    assert "ROLE_ACCESS_LEVEL_OPTIONS" in users_js
    assert "ROLE_ACCESS_LEVEL_ORDER" in users_js
    assert "roleAccessToggle" in users_js
    assert 'role.lockedLevel || ""' in users_js
    assert "if (button.disabled) return;" in users_js
    assert "nextRoleAccessLevel" in users_js
    assert "select[data-role][data-view]" not in users_js

    assert 'id="bulk-activities"' in activities_html
    assert 'id="download-activity-template"' in activities_html
    assert 'id="import-activities"' in activities_html
    assert 'id="activity-import-help"' in activities_html
    assert "<th>KPI Mål</th>" in activities_html
    assert "<th>Arbetstyp</th>" in activities_html
    assert '/js/activities.js?v=20260624-areafocus-clientfilter' in activities_html
    assert "/api/activities/kpi-process-options" in activities_js
    assert "/api/activities/import-template" in activities_js
    assert "/api/activities/import-rows" in activities_js
    assert "openBulkActivitiesModal" in activities_js
    assert re.search(r'key:\s*"label",\s*label:\s*"Etikett",\s*required:\s*true', activities_js)
    assert re.search(r'key:\s*"area",\s*label:\s*"[^"]+",\s*required:\s*false', activities_js)
    assert re.search(r'key:\s*"kpi_process_name",\s*label:\s*"KPI Mål",\s*required:\s*false', activities_js)
    assert re.search(r'key:\s*"work_type",\s*label:\s*"Arbetstyp",\s*required:\s*false', activities_js)
    assert 'id="m-kpi-process-picker"' in activities_js
    assert 'id="m-kpi-process-toggle"' in activities_js
    assert 'id="m-kpi-process-menu"' in activities_js
    assert 'id="m-kpi-process-name" type="hidden"' in activities_js
    assert "data-kpi-process" in activities_js
    assert "selectedKpiProcessNames" in activities_js
    assert "setupKpiProcessPicker" in activities_js
    assert 'id="m-work-type"' in activities_js
    assert "KPI Mål får vara max 255 tecken" in activities_js
    assert "kpi_process_name" in activities_js
    assert "activityWorkTypeLabel" in activities_js
    assert "syncWorkTypeState" in activities_js
    assert "workTypeSelect.disabled = isAbsence" in activities_js
    assert "work_type: category === \"absence\" ? \"normal\"" in activities_js
    assert "KPI Mål ska bara vara processnamn, utan bolag" in activities_js
    assert 'api.download("/api/activities/import-template", "aktiviteter-importmall.xlsx")' in activities_js
    assert 'window.location.href = "/api/activities/import-template"' not in activities_js
    assert "/api/activities/import" in activities_js
    assert 'canEditPage(currentUser, "activities")' in activities_js
    assert 'id="show-inactive"' not in activities_html
    assert "<th>Aktiv</th>" not in activities_html
    assert "m-active" not in activities_js
    assert "Inaktivera" not in activities_js
    assert "Ta bort" in activities_js
    assert 'setupImportHelpButton("activity-import-help", "Importera aktiviteter")' in activities_js


def test_new_user_creation_uses_single_role_select_but_edit_keeps_multiple_roles():
    users = (ROOT / "app" / "frontend" / "js" / "users.js").read_text(encoding="utf-8")

    assert "function roleFieldHtml" in users
    assert '<label>Roll</label>' in users
    assert 'id="m-role"' in users
    assert "roleSelect.value ? [roleSelect.value] : []" in users
    assert 'showToast(isEdit ? "Välj minst en roll" : "Välj en roll", "error")' in users
    assert '<label>Roller</label>' in users
    assert 'type="checkbox" name="m-role"' in users


def test_modal_enter_key_uses_primary_dialog_action():
    common = read_common_frontend()

    assert "function handleModalEnterKeydown" in common
    assert 'event.key !== "Enter"' in common
    assert 'event.target?.closest?.(".modal")' in common
    assert ".actions button.primary:not(:disabled)" in common
    assert "document.addEventListener(\"keydown\", handleModalEnterKeydown)" in common
    assert "target.matches(\"textarea\")" in common
    assert "input[type='checkbox'], input[type='radio']" in common


def test_api_fetch_failures_get_clear_swedish_message():
    api_js = (ROOT / "app" / "frontend" / "js" / "api.js").read_text(encoding="utf-8")

    assert "function connectionError" in api_js
    assert "function isAbortError" in api_js
    assert "if (isAbortError(error)) throw error;" in api_js
    assert "API_NETWORK_ERROR_REPORT_DEDUPE_MS" in api_js
    assert "apiNetworkErrorReportLastAt" in api_js
    assert "const useSharedInFlight = useGetCache && !rest.signal;" in api_js
    assert "Kunde inte ansluta till servern" in api_js
    assert "Appen måste öppnas via servern" in api_js
    assert "const err = connectionError(path, error)" in api_js
    assert 'error_code: "network_error"' in api_js
    assert "originalError" in api_js


def test_sidebar_pages_reserve_layout_before_auth_finishes():
    frontend = ROOT / "app" / "frontend"
    public_pages = {"login.html", "set-password.html", "stallen.html", "meta-upload.html"}

    for html_path in frontend.glob("*.html"):
        html = html_path.read_text(encoding="utf-8")
        if html_path.name in public_pages:
            assert '<body class="with-sidebar">' not in html
        else:
            assert '<body class="with-sidebar">' in html, f"{html_path.name} saknar sidebar-reservering"

    common = read_common_frontend(frontend)
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    assert 'document.body.classList.add("sidebar-hydrated")' in common
    assert "sessionStorage.setItem(SIDEBAR_USER_CACHE_KEY" in common
    assert "localStorage.setItem(SIDEBAR_USER_CACHE_KEY" in common
    assert "sessionStorage.getItem(SIDEBAR_USER_CACHE_KEY) || localStorage.getItem(SIDEBAR_USER_CACHE_KEY)" in common
    assert "body.with-sidebar:not(.sidebar-hydrated)" in styles
    assert "grid-template-columns: var(--sidebar-w) minmax(0, 1fr)" in styles


def test_public_meta_upload_page_is_standalone_and_mobile_focused():
    frontend = ROOT / "app" / "frontend"
    html = (frontend / "meta-upload.html").read_text(encoding="utf-8")
    js = (frontend / "js" / "meta_upload.js").read_text(encoding="utf-8")
    css = (frontend / "css" / "meta-upload.css").read_text(encoding="utf-8")

    assert '<body class="with-sidebar">' not in html
    assert "/js/common.js" not in html
    assert '<link rel="icon" href="/favicon.svg" type="image/svg+xml" />' in html
    assert '<link rel="alternate icon" href="/favicon.ico" sizes="any" />' in html
    assert '<link rel="apple-touch-icon" href="/app-icon-192.png" />' in html
    assert '<link rel="manifest" href="/manifest.webmanifest" />' in html
    assert 'type="file" accept="image/*,video/*" multiple' in html
    assert "uppladdningen kör en fil i taget" in html
    assert "metaUploadButton" not in html
    assert 'id="metaProgress"' in html
    assert 'role="progressbar"' in html
    assert 'XMLHttpRequest' in js
    assert "META_UPLOAD_FILES_PER_REQUEST = 1" in js
    assert "start += META_UPLOAD_FILES_PER_REQUEST" in js
    assert "uploadWithProgress(batch" in js
    assert "formatEta" in js
    assert "uploadStartedAtMs" in js
    assert "fil ${activeIndex + 1} av ${selectedFiles.length}" in js
    assert 'xhr.upload.addEventListener("progress"' in js
    assert 'xhr.open("POST", "/api/meta/uploads")' in js
    assert "FormData" in js
    assert "files.forEach((file) => formData.append" in js
    assert "selectedFiles.forEach" in js
    assert "updateProgress" in js
    assert "loadSelectedVideoDurations" in js
    assert "readSelectedVideoDuration" in js
    assert "await readSelectedVideoDuration" in js
    assert "failed.length" in js
    assert "typeof payload.detail" in js
    assert "typeof payload.message" in js
    assert "startUpload" in js
    assert "void startUpload()" in js
    assert "metaUploadButton" not in js
    assert "data-file-duration-label" in js
    assert "skipped_count" in js
    assert "dubbletter hoppades över" in js
    assert "min-height: 100dvh" in css
    assert ".meta-progress-panel" in css
    assert ".meta-file-progress-bar" in css
    assert ".meta-file-state.success" in css
    assert ".meta-file-state.error" in css
    assert ".meta-upload-button" not in css
    assert "@media (max-width: 520px)" in css


def test_super_user_meta_view_lists_shipment_analysis_without_media_grid():
    frontend = ROOT / "app" / "frontend"
    html = (frontend / "meta.html").read_text(encoding="utf-8")
    js = (frontend / "js" / "meta.js").read_text(encoding="utf-8")
    api_js = (frontend / "js" / "api.js").read_text(encoding="utf-8")
    common = read_common_frontend(frontend)
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    assert '<body class="with-sidebar">' in html
    assert "/js/common.js" in html
    assert "/js/meta.js" in html
    assert 'id="metaShipmentTitle"' in html
    assert 'id="metaSearch"' in html
    assert 'id="metaExportFiltered"' in html
    assert 'id="metaExportAll"' in html
    assert 'data-sort-key="shipment_number"' in html
    assert 'data-sort-key="updated_at"' in html
    assert 'data-sort-key="video_size_bytes"' in html
    assert 'data-sort-key="label_status"' in html
    assert "Längd" in html
    assert "Storlek" in html
    assert "Uppdaterad" in html
    assert "Rad-ID" in html
    assert 'id="metaShipmentRows"' in html
    assert 'id="metaGrid"' not in html
    assert 'id="metaMediaType"' not in html
    assert 'id: "meta"' in common
    assert 'label: "Meta"' in common
    assert 'href: "/meta.html"' in common
    assert 'visible: Boolean(user?.is_super_user)' in common
    assert 'initPage("meta", { requireSuperUser: true })' in js
    assert 'api.get(`/api/meta/uploads?${params.toString()}`' in js
    assert 'api.get("/api/meta/shipment-observations?limit=200"' in js
    assert "function filteredShipmentItems" in js
    assert "function exportShipmentRows" in js
    assert "/api/meta/shipment-observations/export" in js
    assert "metaSortState" in js
    assert "function formatBytes" in js
    assert 'key === "video_size_bytes"' in js
    assert "item.video_size_label" in js
    assert "/api/meta/uploads/${encodeURIComponent(item.media_upload_id)}/analyze" in js
    assert "appendQuery" in js
    assert 'download: "1"' in js
    assert "{ direct: true }" not in js
    assert "META_DOWNLOAD_CONCURRENCY = 1" in js
    assert "function enqueueMetaDownload" in js
    assert 'downloadShipmentMedia(item, "video", button)' in js
    assert 'downloadShipmentMedia(item, "label", button)' in js
    assert "variant: kind === \"video\" ? \"playable\" : \"\"" in js
    assert "function downloadDirect" in api_js
    assert 'method: "HEAD"' in api_js
    assert 'credentials: "include"' in api_js
    assert "withTraceHeaders({}, requestTraceParent)" in api_js
    assert "Ladda ner" in js
    assert "Analysera" in js
    assert "shipment_number" in js
    assert 'key === "label_status"' in js
    assert "formatTimestamp(item.updated_at || item.created_at)" in js
    assert "meta-admin-timestamp" in js
    assert "formatDuration" in js
    assert "data-duration-for" in js
    assert "metaGrid" not in js
    assert "metaMediaType" not in js
    assert "mediaUrl" not in js
    assert "downloadMetaItem" not in js
    assert "deleteMetaItem" not in js
    assert "data-open-media" not in js
    assert "data-delete-media" not in js
    assert "Öppna" not in js
    assert "openMediaModal" not in js
    assert ".meta-admin-grid" not in styles
    assert ".meta-admin-controls" in styles
    assert ".meta-sort-button" in styles
    assert ".meta-admin-table" in styles
    assert ".meta-icon-button" in styles
    assert ".meta-icon-button.is-download-queued" in styles
    assert ".meta-icon-button.is-download-running" in styles
    assert ".meta-status-pill" in styles
    assert ".meta-preview-frame video" not in styles


def test_allocation_pages_are_wired_to_shared_tool_shell():
    frontend = ROOT / "app" / "frontend"
    allocation_pages = {
        "uppladdningar.html": "uploads",
        "bearbeta.html": "process",
        "installningar.html": "settings",
        "dela.html": "split",
    }

    for filename, view in allocation_pages.items():
        html = (frontend / filename).read_text(encoding="utf-8")
        assert '<body class="with-sidebar">' in html
        assert 'id="allocationRoot"' in html
        assert f'data-allocation-view="{view}"' in html
        assert "/js/api.js" in html
        assert "/js/common.js" in html
        assert "/js/allocation/state.js" in html
        assert "/js/allocation/boot.js" in html
        assert "/js/allocation_tools.js" in html
        script_order = [
            "/js/common.js",
            "/js/allocation/state.js",
            "/js/allocation/files.js",
            "/js/allocation/api.js",
            "/js/allocation/uploads_view.js",
            "/js/allocation/results.js",
            "/js/allocation/process_view.js",
            "/js/allocation/process_matrix.js",
            "/js/allocation/map_settings.js",
            "/js/allocation/settings_view.js",
            "/js/allocation/split_view.js",
            "/js/allocation/boot.js",
            "/js/allocation_tools.js",
        ]
        positions = [html.index(script) for script in script_order]
        assert positions == sorted(positions)


def test_allocation_frontend_uses_local_file_store_and_upload_indicator():
    frontend = ROOT / "app" / "frontend"
    common = read_common_frontend(frontend)
    allocation = read_allocation_frontend(frontend)
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")
    catalog = (ROOT / "warehouse_tools" / "catalog.py").read_text(encoding="utf-8")
    flows = (ROOT / "warehouse_tools" / "flows.py").read_text(encoding="utf-8")

    assert 'const ALLOCATION_API = "/api/allokering"' in allocation
    assert 'const ALLOCATION_DB_NAME = "flow-allokering-files"' in allocation
    assert "indexedDB.open(ALLOCATION_DB_NAME" in allocation
    assert "window.allocationUploadActivity?.start()" in allocation
    assert "window.allocationUploadActivity?.finish(uploadedNames.size)" in allocation
    assert "observationsUpdateStatusText" in allocation
    assert "observationsUpdateLogText" in allocation
    assert '"inte aktuell (0 nya pallid)"' in allocation
    assert "function appendAllocationAreaFocus(formData)" in allocation
    assert 'appendAllocationAreaFocus(fd);\n  fd.append("file", file, entry.name);' in allocation
    assert "appendAllocationAreaFocus(fd);" in allocation
    assert "github_sent_rows" in allocation
    assert "article_max_changed_rows" in allocation
    assert "allocationState.files = await loadStoredAllocationFiles()" in allocation
    assert "ALLOCATION_WORK_STATE_PREFIX" in allocation
    assert "persistAllocationWorkState" in allocation
    assert "restoreAllocationWorkState()" in allocation
    assert "sessionStorage.setItem(key" in allocation
    assert 'id="allocation-clear-all-files"' in allocation
    assert "Rensa alla" in allocation
    assert "window.clearAllUploadedFiles" in allocation
    assert 'window.addEventListener("flow:uploadsCleared"' in allocation
    assert 'window.addEventListener("flow:allocationFilesChanged"' in allocation
    assert "productivityUploads?.syncAllocationUploads" not in allocation
    assert "Kunde inte synka produktivitetsfiler till Uppladdningar." not in allocation
    assert "PRODUCTIVITY_UPLOAD_SLOTS" not in allocation
    assert "Pallastningslogg" not in allocation
    assert "data-productivity-upload-panel" not in allocation
    assert "allocationDropSlotsForTarget" in allocation
    assert "data-drop-slot" in allocation
    assert "fallbackSlotKey" in allocation
    assert 'data-allocation-drop data-drop-scope="flow"' in allocation
    assert "event.stopPropagation()" in allocation
    assert "Detalj Kundorder (Alla)" in allocation
    assert "Detalj Kundorder (Alla)" in catalog
    assert "Detalj Kundorder (Alla)" in flows
    assert "Detalj Kundorder (Alla) (kundnamn)" not in catalog
    assert "Detalj Kundorder (Alla) (kundnamn)" not in flows
    assert "Buffertpall" in allocation
    assert "Buffertpall" in catalog
    assert "Buffertpall" in flows
    assert "Ej Inlagrade Artiklar" in allocation
    assert "Ej Inlagrade Artiklar" in catalog
    assert "Ej Inlagrade Artiklar" in flows
    assert "Pallastningslogg" not in allocation
    assert "Palllastningslogg" not in allocation
    assert '"pallastningslogg"' not in allocation
    assert '"pallastningslogg"' not in common
    assert "Plocklogg Full" in allocation
    assert "ALLOCATION_SLOT_LABEL_ALIASES" in allocation
    assert "function allocationUploadSlotLabel(slot)" in allocation
    assert "allocationUploadSlotLabel({ key, label: input.label })" in allocation
    assert "<h3>${allocationEscape(allocationUploadSlotLabel(slot))}</h3>" in allocation
    assert "<h3>${allocationEscape(slot.label)}</h3>" not in allocation
    assert '"customer_order_details_all"' in allocation
    assert '"detalj kundorder(alla)"' in common
    assert "Beställningslinjer" not in catalog
    assert "Beställningslinjer" not in flows
    assert "Saldo Inkl. Automation" in allocation
    assert "Saldo Inkl. Automation" in catalog
    assert "Saldo Inkl. Automation" in flows
    assert "Saldo Inkl. Automation (Utbest" not in catalog
    assert "Saldo Inkl. Automation (Utbest" not in flows
    assert "Item Option" in allocation
    assert "Item Option" in catalog
    assert "Item Option" in flows
    assert "Saldo / automation" not in catalog
    assert '"not_putaway", "wms_booking"' in catalog
    assert '"not_putaway", "wms_booking"' in flows
    assert "v_ask_receive_log" not in allocation
    assert "v_ask_correct_log" not in allocation
    assert "ALLOCATION_PERSISTENT_DATA_FILES" in allocation
    assert "allocationPersistentDataFile" in allocation
    assert "lastForecastSessionId" in allocation
    assert "allocationRequiredSessionId" in allocation
    assert 'fd.append("forecast_session_id"' in allocation
    assert '"id": "forecast"' in catalog
    assert '"id": "ytgenerering"' in catalog
    assert '"hidden": True' in catalog
    assert '"location", "label": "Lagerplatser", "required": False' in catalog
    assert '"requiresSessionFlow": {"flowId": "forecast"' not in catalog
    assert "flow_forecast" in flows
    assert "flow_ytgenerering" in flows
    assert "Sammanställd data" in allocation
    assert "productivity_pick_observations" not in allocation
    assert "productivity_trans_observations" not in allocation
    assert "productivity_pallet_observations" not in allocation
    assert "allocationDataSuffixLabel" in allocation
    assert '"kärnfil"' in allocation
    assert "artikel_max.csv (sammanställd data)" in catalog
    assert "copyAutoFlowColumn" in allocation
    assert "copyOrdersaldoCompleteOrders" not in allocation
    assert '"goods-declaration"' in allocation
    assert "clear_orders" in allocation
    assert "custom_adr" in allocation
    assert "item_security_info" in allocation
    assert "dispatch_template" in allocation
    assert "trans_agency" in allocation
    assert "transportorer" in allocation
    assert '{ key: "location", prefix: "lagerplats" }' in allocation
    assert '{ key: "location", prefix: "lagerplatser" }' in allocation
    assert "const skipCache = options.skipCache === true" in allocation
    assert 'loadAllocationCoreDataStatus({ skipCache: true })' in allocation
    assert 'window.api?.clearGetCache?.((key) => String(key || "").includes("/api/coredata/files"))' in allocation
    assert "Alternativ Leveransadress" in allocation
    assert "Godsdeklaration" in catalog
    assert "Godsdeklaration" in flows
    assert "Orderöversikt (adressnummer)" in catalog
    assert "Alternativ Leveransadress" in catalog
    assert "item_security_info" in catalog
    assert "flow_goods_declaration" in flows

    assert "DATABASE_ICON" in common
    assert "ALLOCATION_UPLOAD_NOTICE_KEY" in common
    assert "ALLOCATION_PROTECTED_UPLOAD_KEYS" in common
    assert "SHARED_ALLOCATION_FILE_TYPE_KEYS" in common
    assert "SHARED_ALLOCATION_SLOT_MIRRORS" in common
    assert "productivity_pallet" not in common
    assert "saveSharedAllocationFiles" in common
    assert "storeSharedAllocationFile" in common
    assert "protectedKeys" in common
    assert "store.openCursor()" in common
    assert "cursor.delete()" in common
    assert "Kärnfiler och sammanställd data ligger kvar" in common
    assert "item_security_info" in common
    assert "dispatch_template" in common
    assert "trans_agency" in common
    assert "custom_adr" in common
    assert 'new CustomEvent("flow:allocationFilesChanged"' in common
    assert "window.sharedAllocationUploads" in common
    assert "addAllocationUploadNotice(count)" in common
    assert "isAllocationUploadsPage()" in common
    assert "window.allocationUploadActivity" in common
    assert "clearAllocationUploadNotice()" in common
    assert "allocationTrace" not in common
    assert "harleda.html" not in common
    assert "eftersok" not in allocation
    assert "clearGeneration" in common
    assert not (frontend / "js" / "productivity_uploads.js").exists()
    assert "syncAllocationUploads: false" not in allocation
    assert "allocationResultSummaryEntries" in allocation
    assert "data.display_summary" in allocation
    assert 'entry.key !== "result"' not in allocation
    assert "data-download-csv" in allocation
    assert "api.download(`${ALLOCATION_API}/download/" in allocation
    assert 'href="${ALLOCATION_API}/download/' not in allocation
    assert "Excel öppnas" in allocation
    assert "ALLOCATION_AUTO_COPY_COLUMN_RULES" in allocation
    assert "copyAutoFlowColumn" in allocation
    assert 'tableKey: "complete"' in allocation
    assert "entry.key === rule.tableKey" in allocation
    assert "${orderCount} ${rule.successLabel} kopierade" in allocation
    assert "renderTextResult" in allocation
    assert 'class="allocation-copy-text"' in allocation
    assert "data-copy-text-result" in allocation
    assert "data-result-text" in allocation
    assert "ALLOCATION_COPY_ICON" in allocation
    assert "Text kopierad" in allocation
    assert 'class="allocation-column-head"' in allocation
    assert 'class="allocation-copy-column"' in allocation
    assert 'data-copy-column="${index}"' in allocation
    assert 'aria-label="Kopiera kolumn ${allocationEscape(column)}"' in allocation
    assert "/table-column/" in allocation
    assert "writeClipboardText" in allocation
    assert 'document.execCommand("copy")' in allocation
    assert "Kolumn kopierad" in allocation

    assert ".database-toggle.uploading .upload-arrow" in styles
    assert "@keyframes uploadArrowRise" in styles
    assert ".database-toggle .upload-notice" in styles
    assert "left: -6px;" in styles
    assert ".sidebar-upload-link" not in styles
    assert ".allocation-file-slot.drag-over" in styles
    assert ".allocation-flow-chip.drag-over .allocation-flow-chip-row" in styles
    assert "flex-wrap: nowrap;\n  gap: 20px 24px;\n  overflow-x: auto;" in styles
    assert ".allocation-flow-chip {\n  position: relative;\n  width: 260px;" in styles
    assert ".allocation-flow-chip-row {\n  display: flex;\n  align-items: stretch;\n  min-height: 40px;" in styles
    assert "overflow: hidden;\n  text-overflow: ellipsis;\n  white-space: nowrap;" in styles
    assert "flex: 0 0 38px;\n  min-width: 38px;" in styles
    assert ".allocation-column-head" in styles
    assert ".allocation-text-result-wrap" in styles
    assert ".allocation-copy-text" in styles
    assert ".allocation-copy-column" in styles
    assert "text-decoration: none;" in styles

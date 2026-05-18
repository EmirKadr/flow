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
    assert pages_by_name["bemanning"].roles == ("admin", "leader", "viewer")
    assert pages_by_name["produktivitet"].roles == ("admin",)
    assert pages_by_name["anvandare"].roles == ("admin",)
    assert pages_by_name["uppladdningar"].roles == ("admin", "warehouse")
    assert pages_by_name["bearbeta"].roles == ("admin", "warehouse")


def test_visual_smoke_covers_critical_scenarios():
    state_names = {state.name for state in visual_smoke.STATES}

    assert {
        "bemanning-mestergruppen",
        "bemanning-autostore",
        "bemanning-kopiera-dag-modal",
        "bemanning-kalkyl-alla",
        "oversikt-manad-mestergruppen",
        "personer-veckomall-modal",
        "stallen-redigera-aktivitet-modal",
        "anvandare-redigera-anvandare-modal",
        "historik-filter",
        "viewer-nekad-personer",
        "viewer-nekad-produktivitet",
        "leader-nekad-historik",
        "leader-nekad-produktivitet",
        "leader-nekad-uppladdningar",
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


def test_visual_smoke_outputs_have_unique_names():
    names = []
    for viewport in visual_smoke.VIEWPORTS:
        for role in ("public", "admin", "leader", "viewer", "warehouse"):
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
            "select username, role from users where username in ('visual_leader', 'visual_viewer', 'visual_lager')"
        ).fetchall()
        visual_people = connection.execute(
            "select count(*) from persons where name like 'Visual %'"
        ).fetchone()[0]
        schedule_cells = connection.execute("select count(*) from schedule_cells").fetchone()[0]
        audit_rows = connection.execute(
            "select count(*) from audit_log where entity_type = 'visual_test'"
        ).fetchone()[0]

    assert sorted(users) == [
        ("visual_lager", "warehouse_clerk"),
        ("visual_leader", "leader"),
        ("visual_viewer", "viewer"),
    ]
    assert visual_people >= 6
    assert schedule_cells > 0
    assert audit_rows == 1


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
    productivity_html = (frontend / "produktivitet.html").read_text(encoding="utf-8")

    assert "bemanning-theme" in common
    assert "bemanning-sidebar-user" in common
    assert "readCachedSidebarUser" in common
    assert "sidebar-initializing" in common
    assert "id=\"theme-toggle\"" in common
    assert "THEME_ICONS" in common
    assert ':root[data-theme="dark"]' in styles
    assert ".theme-toggle" in styles
    assert ".app.sidebar-initializing" in styles
    assert "postFile" in api_js
    assert "/api/productivity/files/raw" in productivity
    assert "productivityLocalFiles" in productivity
    assert "buildProductivityReportFromLocalDataset" in productivity
    assert "prefetchAdjacentReports" in productivity
    assert "refreshProductivityBtn" not in productivity_html

    for html_path in frontend.glob("*.html"):
        html = html_path.read_text(encoding="utf-8")
        assert "/js/common.js" in html


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
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    assert 'const ALLOCATION_API = "/api/allokering"' in allocation
    assert 'const ALLOCATION_DB_NAME = "bemanning-allokering-files"' in allocation
    assert "indexedDB.open(ALLOCATION_DB_NAME" in allocation
    assert "window.allocationUploadActivity?.start()" in allocation
    assert "window.allocationUploadActivity?.finish(assigned.length)" in allocation
    assert "allocationState.files = await loadStoredAllocationFiles()" in allocation

    assert "DATABASE_ICON" in common
    assert "ALLOCATION_UPLOAD_NOTICE_KEY" in common
    assert "writeAllocationUploadNotice({ count, at: Date.now() })" in common
    assert "window.allocationUploadActivity" in common
    assert "clearAllocationUploadNotice()" in common

    assert ".database-toggle.uploading .upload-arrow" in styles
    assert "@keyframes uploadArrowRise" in styles
    assert ".database-toggle .upload-notice" in styles

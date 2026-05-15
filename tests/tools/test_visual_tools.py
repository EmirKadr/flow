import os
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
        "personer",
        "stallen",
        "historik",
        "anvandare",
    }
    assert pages_by_name["bemanning"].roles == ("admin", "leader", "viewer")
    assert pages_by_name["anvandare"].roles == ("admin",)


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
        "leader-nekad-historik",
    }.issubset(state_names)


def test_interactive_e2e_covers_mutating_workflows():
    assert {
        "create_user",
        "edit_user",
        "create_activity",
        "edit_activity",
        "create_person",
        "edit_person_inline",
        "edit_person_week_template",
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


def test_desktop_app_probe_has_safe_and_real_modes():
    args = desktop_app_probe.parse_args(["--real-webengine"])

    assert args.real_webengine is True
    assert hasattr(desktop_app_probe, "run_shell_probe")
    assert hasattr(desktop_app_probe, "run_real_webengine_probe")


def test_visual_smoke_outputs_have_unique_names():
    names = []
    for viewport in visual_smoke.VIEWPORTS:
        for role in ("public", "admin", "leader", "viewer"):
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
            "select username, role from users where username in ('visual_leader', 'visual_viewer')"
        ).fetchall()
        visual_people = connection.execute(
            "select count(*) from persons where name like 'Visual %'"
        ).fetchone()[0]
        schedule_cells = connection.execute("select count(*) from schedule_cells").fetchone()[0]
        audit_rows = connection.execute(
            "select count(*) from audit_log where entity_type = 'visual_test'"
        ).fetchone()[0]

    assert sorted(users) == [("visual_leader", "leader"), ("visual_viewer", "viewer")]
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

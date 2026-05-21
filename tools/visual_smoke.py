"""Capture visual smoke screenshots for the Bemanning web UI.

Default mode creates a disposable SQLite database, seeds representative data,
starts a local FastAPI server, logs in with test users, and screenshots the
important views in desktop and mobile viewport sizes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

from tools.terminology_contracts import assert_no_forbidden_terms_in_text


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "visual"
VISUAL_PASSWORD = "visual12345"


@dataclass(frozen=True)
class Viewport:
    name: str
    width: int
    height: int


@dataclass(frozen=True)
class VisualPage:
    name: str
    path: str
    wait_for: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class VisualState:
    name: str
    path: str
    wait_for: str
    action: str
    roles: tuple[str, ...] = ("admin",)


VIEWPORTS: tuple[Viewport, ...] = (
    Viewport("desktop", 1440, 1000),
    Viewport("mobile", 390, 844),
)

TEST_USERS: dict[str, tuple[str, str]] = {
    "admin": ("admin", "admin123"),
    "leader": ("visual_leader", VISUAL_PASSWORD),
    "staffing": ("visual_staffing", VISUAL_PASSWORD),
    "viewer": ("visual_viewer", VISUAL_PASSWORD),
    "warehouse": ("visual_lager", VISUAL_PASSWORD),
    "article": ("visual_artikel", VISUAL_PASSWORD),
}

PAGES: tuple[VisualPage, ...] = (
    VisualPage("login", "/login.html", "#login-form", ("public",)),
    VisualPage("bemanning", "/index.html", "#scheduleTable", ("admin", "leader", "staffing", "viewer")),
    VisualPage("oversikt", "/overblick.html", "#overviewTable", ("admin", "leader", "staffing", "viewer")),
    VisualPage("produktivitet", "/produktivitet.html", "#productivityStatus", ("admin",)),
    VisualPage("personer", "/personer.html", "#persons-table", ("admin", "leader", "staffing")),
    VisualPage("aktiviteter", "/aktiviteter.html", "#acts-body", ("admin", "leader", "staffing")),
    VisualPage("historik", "/historik.html", "#auditBody", ("admin",)),
    VisualPage("anvandare", "/anvandare.html", "#users-body", ("admin",)),
    VisualPage("hamta-data", "/hamta-data.html", "#dataFetchPrompt", ("admin",)),
    VisualPage("uppladdningar", "/uppladdningar.html", "#allocationRoot .allocation-panel", ("admin", "warehouse", "article")),
    VisualPage("bearbeta", "/bearbeta.html", "#allocationRoot .allocation-panel", ("admin",)),
    VisualPage("dela", "/dela.html", "#allocationRoot .allocation-panel", ("admin", "warehouse", "article")),
    VisualPage("harleda", "/harleda.html", "#allocationRoot .allocation-panel", ("admin", "warehouse", "article")),
)

STATES: tuple[VisualState, ...] = (
    VisualState("bemanning-alla-omraden", "/index.html", "#scheduleTable", "schedule_area_all", ("admin", "leader", "staffing")),
    VisualState("bemanning-mestergruppen", "/index.html", "#scheduleTable", "schedule_area_mg", ("admin", "leader", "staffing")),
    VisualState("bemanning-autostore", "/index.html", "#scheduleTable", "schedule_area_as", ("admin",)),
    VisualState("bemanning-tomt-filter", "/index.html", "#scheduleTable", "schedule_empty_filter", ("admin",)),
    VisualState("bemanning-kopiera-dag-modal", "/index.html", "#scheduleTable", "schedule_copy_modal", ("admin", "leader", "staffing")),
    VisualState("bemanning-kalkyl-alla", "/index.html", "#scheduleTable", "schedule_calc_all", ("admin",)),
    VisualState("bemanning-sidebar-kompakt", "/index.html", "#scheduleTable", "sidebar_collapsed", ("admin", "viewer")),
    VisualState("oversikt-mestergruppen", "/overblick.html", "#overviewTable", "overview_area_mg", ("admin", "leader", "staffing")),
    VisualState("oversikt-manad", "/overblick.html", "#overviewTable", "overview_month"),
    VisualState("oversikt-manad-mestergruppen", "/overblick.html", "#overviewTable", "overview_month_mg"),
    VisualState("oversikt-tomt-filter", "/overblick.html", "#overviewTable", "overview_empty_filter", ("admin",)),
    VisualState("personer-veckomall-modal", "/personer.html", "#persons-body button[data-schedule]", "person_schedule_modal"),
    VisualState("personer-ny-person-modal", "/personer.html", "#new-person", "click_new_person"),
    VisualState("aktiviteter-import-hjalp", "/aktiviteter.html", "#activity-import-help", "activity_import_help", ("admin",)),
    VisualState("aktiviteter-ny-aktivitet-modal", "/aktiviteter.html", "#new-act", "click_new_activity"),
    VisualState("aktiviteter-redigera-aktivitet-modal", "/aktiviteter.html", "#acts-body button[data-edit]", "activity_edit_modal"),
    VisualState("anvandare-ny-anvandare-modal", "/anvandare.html", "#new-user", "click_new_user"),
    VisualState("anvandare-redigera-anvandare-modal", "/anvandare.html", "#users-body button[data-edit]", "user_edit_modal"),
    VisualState("anvandare-vybehorigheter-modal", "/anvandare.html", "#role-view-access", "role_access_modal"),
    VisualState("historik-filter", "/historik.html", "#auditBody", "analytics_filter", ("admin",)),
    VisualState("viewer-nekad-personer", "/personer.html", "#scheduleTable", "noop", ("viewer",)),
    VisualState("viewer-nekad-aktiviteter", "/aktiviteter.html", "#scheduleTable", "noop", ("viewer",)),
    VisualState("viewer-nekad-anvandare", "/anvandare.html", "#scheduleTable", "noop", ("viewer",)),
    VisualState("viewer-nekad-historik", "/historik.html", "#scheduleTable", "noop", ("viewer",)),
    VisualState("viewer-nekad-produktivitet", "/produktivitet.html", "#scheduleTable", "noop", ("viewer",)),
    VisualState("leader-nekad-anvandare", "/anvandare.html", "#scheduleTable", "noop", ("leader",)),
    VisualState("leader-nekad-historik", "/historik.html", "#scheduleTable", "noop", ("leader",)),
    VisualState("leader-nekad-produktivitet", "/produktivitet.html", "#scheduleTable", "noop", ("leader",)),
    VisualState("leader-nekad-uppladdningar", "/uppladdningar.html", "#scheduleTable", "noop", ("leader",)),
    VisualState("staffing-nekad-anvandare", "/anvandare.html", "#scheduleTable", "noop", ("staffing",)),
    VisualState("staffing-nekad-historik", "/historik.html", "#scheduleTable", "noop", ("staffing",)),
    VisualState("staffing-nekad-produktivitet", "/produktivitet.html", "#scheduleTable", "noop", ("staffing",)),
    VisualState("staffing-nekad-uppladdningar", "/uppladdningar.html", "#scheduleTable", "noop", ("staffing",)),
    VisualState("viewer-nekad-uppladdningar", "/uppladdningar.html", "#scheduleTable", "noop", ("viewer",)),
    VisualState("bemanning-fokus-mestergruppen", "/index.html", "#scheduleTable", "area_focus_mg", ("admin", "leader", "staffing")),
    VisualState("oversikt-fokus-mestergruppen", "/overblick.html", "#overviewTable", "area_focus_mg", ("admin", "leader", "staffing")),
    VisualState("produktivitet-fokus-mestergruppen", "/produktivitet.html", "#productivityStatus", "area_focus_mg", ("admin",)),
    VisualState("personer-fokus-mestergruppen", "/personer.html", "#persons-table", "area_focus_mg", ("admin", "leader", "staffing")),
    VisualState("aktiviteter-fokus-mestergruppen", "/aktiviteter.html", "#acts-body", "area_focus_mg", ("admin", "leader", "staffing")),
)


class ServerProcess:
    def __init__(self, process: subprocess.Popen, env: dict[str, str]):
        self.process = process
        self.env = env

    def close(self) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=8)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str, process: subprocess.Popen, timeout_s: int = 30) -> None:
    deadline = time.monotonic() + timeout_s
    health_url = f"{base_url}/api/health"
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited early with code {process.returncode}")
        try:
            with urlopen(health_url, timeout=2) as response:
                if response.status == 200:
                    return
        except URLError as exc:
            last_error = str(exc)
        except TimeoutError as exc:
            last_error = str(exc)
        time.sleep(0.3)
    raise RuntimeError(f"Server did not become healthy at {health_url}: {last_error}")


def _run_python_module(module: str, env: dict[str, str]) -> None:
    subprocess.run([sys.executable, "-m", module], cwd=ROOT, env=env, check=True)


def start_local_server(output_dir: Path) -> tuple[str, ServerProcess]:
    port = _free_port()
    db_path = output_dir / "visual-smoke.sqlite"
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "SECRET_KEY": "visual-smoke-secret",
            "ENVIRONMENT": "development",
            "SUPER_USER_USERNAMES": "admin,emikad",
            "BEMANNING_DISABLE_UPDATE_CHECK": "1",
        }
    )
    _run_python_module("app.backend.bootstrap_local", env)
    _run_python_module("tools.visual_data", env)

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    _wait_for_health(base_url, process)
    return base_url, ServerProcess(process, env)


def _load_playwright():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright saknas. Kör: python -m pip install -r requirements-dev.txt "
            "och sedan: python -m playwright install chromium"
        ) from exc
    return sync_playwright, PlaywrightTimeoutError


def _safe_name(*parts: str) -> str:
    return "__".join(part.strip("/").replace("/", "-") for part in parts if part)


def _page_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def _screenshot(page, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=True)


def _wait_for_page(page, selector: str) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(selector, timeout=15000)


def _select_by_label(page, selector: str, label: str) -> None:
    page.locator(selector).select_option(label=label)
    page.wait_for_load_state("networkidle")


def _wait_for_table_rows(page, selector: str) -> None:
    page.wait_for_selector(selector, timeout=15000)
    page.wait_for_timeout(300)


def assert_no_forbidden_terminology(page) -> None:
    title = page.title()
    body_text = page.locator("body").inner_text(timeout=15000)
    assert_no_forbidden_terms_in_text(f"{title}\n{body_text}", context=f"rendered UI at {page.url}")


def assert_no_legacy_activity_labels(page) -> None:
    assert_no_forbidden_terminology(page)


def _login(page, base_url: str, role: str) -> None:
    username, password = TEST_USERS[role]
    page.goto(_page_url(base_url, "/login.html"), wait_until="networkidle")
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("button.primary")
    page.wait_for_url("**/index.html", timeout=15000)
    _wait_for_page(page, "#scheduleTable")


def _apply_state(page, state: VisualState) -> None:
    if state.action == "noop":
        page.wait_for_timeout(500)
        return
    if state.action == "sidebar_collapsed":
        page.click("#sidebar-toggle")
        page.wait_for_timeout(500)
        return
    if state.action == "area_focus_mg":
        page.evaluate(
            """() => {
                localStorage.setItem('bemanning-area-focus', 'MG');
                localStorage.removeItem('sidebar-collapsed');
            }"""
        )
        page.reload(wait_until="networkidle")
        _wait_for_page(page, state.wait_for)
        page.wait_for_timeout(500)
        return
    if state.action == "schedule_area_all":
        _select_by_label(page, "#areaSelect", "Alla")
        _wait_for_table_rows(page, "#scheduleBody tr")
        return
    if state.action == "schedule_area_mg":
        _select_by_label(page, "#areaSelect", "Mestergruppen")
        _wait_for_table_rows(page, "#scheduleBody tr")
        return
    if state.action == "schedule_area_as":
        _select_by_label(page, "#areaSelect", "Autostore")
        _wait_for_table_rows(page, "#scheduleBody tr")
        return
    if state.action == "schedule_empty_filter":
        page.fill("#nameFilter", "matchar-inte-nagon")
        page.wait_for_timeout(300)
        return
    if state.action == "schedule_copy_modal":
        page.click("#copyBtn")
        page.wait_for_selector(".modal-backdrop .modal", timeout=15000)
        return
    if state.action == "schedule_calc_all":
        page.select_option("#calcAreaSelect", "ALL")
        page.wait_for_timeout(300)
        return
    if state.action == "overview_area_mg":
        _select_by_label(page, "#areaSelect", "Mestergruppen")
        _wait_for_table_rows(page, "#overviewBody tr")
        return
    if state.action == "overview_month":
        page.select_option("#viewMode", "month")
        page.wait_for_timeout(500)
        page.wait_for_selector("#overviewBody tr", timeout=15000)
        return
    if state.action == "overview_month_mg":
        page.select_option("#viewMode", "month")
        _select_by_label(page, "#areaSelect", "Mestergruppen")
        _wait_for_table_rows(page, "#overviewBody tr")
        return
    if state.action == "overview_empty_filter":
        page.fill("#nameFilter", "matchar-inte-nagon")
        page.wait_for_timeout(300)
        return
    if state.action == "person_schedule_modal":
        page.locator("#persons-body button[data-schedule]").first.click()
        page.wait_for_selector(".modal-backdrop .modal", timeout=15000)
        return
    if state.action == "click_new_person":
        page.click("#new-person")
        page.wait_for_selector(".modal-backdrop .modal", timeout=15000)
        return
    if state.action == "click_new_activity":
        page.click("#new-act")
        page.wait_for_selector(".modal-backdrop .modal", timeout=15000)
        return
    if state.action == "activity_import_help":
        page.click("#activity-import-help")
        page.wait_for_selector(".modal-backdrop .modal", timeout=15000)
        return
    if state.action == "activity_edit_modal":
        page.locator("#acts-body button[data-edit]").first.click()
        page.wait_for_selector(".modal-backdrop .modal", timeout=15000)
        return
    if state.action == "click_new_user":
        page.click("#new-user")
        page.wait_for_selector(".modal-backdrop .modal", timeout=15000)
        return
    if state.action == "user_edit_modal":
        page.locator("#users-body button[data-edit]").first.click()
        page.wait_for_selector(".modal-backdrop .modal", timeout=15000)
        return
    if state.action == "role_access_modal":
        page.click("#role-view-access")
        page.wait_for_selector(".role-access-modal", timeout=15000)
        return
    if state.action == "analytics_filter":
        page.select_option("#periodSelect", "all")
        page.fill("#actionFilter", "visual_seed")
        page.click("#refreshAuditBtn")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        return
    raise ValueError(f"Unknown visual state action: {state.action}")


def _capture_for_role(context, base_url: str, output_dir: Path, role: str, viewport: Viewport) -> list[dict]:
    artifacts: list[dict] = []
    page = context.new_page()
    try:
        if role != "public":
            _login(page, base_url, role)

        for target in PAGES:
            if role not in target.roles:
                continue
            page.goto(_page_url(base_url, target.path), wait_until="networkidle")
            _wait_for_page(page, target.wait_for)
            assert_no_forbidden_terminology(page)
            screenshot_path = output_dir / f"{_safe_name(viewport.name, role, target.name)}.png"
            _screenshot(page, screenshot_path)
            artifacts.append(
                {
                    "viewport": viewport.name,
                    "role": role,
                    "target": target.name,
                    "path": str(screenshot_path.relative_to(output_dir)),
                }
            )

        if role != "public":
            for state in STATES:
                if role not in state.roles:
                    continue
                page.goto(_page_url(base_url, state.path), wait_until="networkidle")
                _wait_for_page(page, state.wait_for)
                _apply_state(page, state)
                assert_no_forbidden_terminology(page)
                screenshot_path = output_dir / f"{_safe_name(viewport.name, role, state.name)}.png"
                _screenshot(page, screenshot_path)
                artifacts.append(
                    {
                        "viewport": viewport.name,
                        "role": role,
                        "target": state.name,
                        "path": str(screenshot_path.relative_to(output_dir)),
                    }
                )
    finally:
        page.close()
    return artifacts


def capture_visuals(
    *,
    base_url: str,
    output_dir: Path,
    roles: Iterable[str],
    headful: bool = False,
) -> list[dict]:
    sync_playwright, _ = _load_playwright()
    artifacts: list[dict] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headful)
        try:
            for viewport in VIEWPORTS:
                for role in roles:
                    context = browser.new_context(
                        viewport={"width": viewport.width, "height": viewport.height},
                        device_scale_factor=1,
                        locale="sv-SE",
                    )
                    try:
                        artifacts.extend(_capture_for_role(context, base_url, output_dir, role, viewport))
                    finally:
                        context.close()
        finally:
            browser.close()
    return artifacts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Use an already running server instead of starting a disposable local one.")
    parser.add_argument("--output", type=Path, help="Screenshot output directory.")
    parser.add_argument(
        "--roles",
        default="public,admin,leader,staffing,viewer",
        help="Comma-separated roles to capture: public, admin, leader, staffing, viewer, warehouse, article.",
    )
    parser.add_argument("--headful", action="store_true", help="Show the browser while capturing screenshots.")
    parser.add_argument(
        "--via-desktop-proxy",
        action="store_true",
        help="Serve the same frontend through the desktop local app server and proxy API calls to the test backend.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = args.output or (DEFAULT_OUTPUT_ROOT / run_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    roles = tuple(role.strip() for role in args.roles.split(",") if role.strip())
    unknown = sorted(set(roles) - {"public", *TEST_USERS.keys()})
    if unknown:
        raise SystemExit(f"Unknown roles: {', '.join(unknown)}")

    server: ServerProcess | None = None
    desktop_proxy = None
    upstream_base_url = None
    base_url = args.base_url
    try:
        if not base_url:
            base_url, server = start_local_server(output_dir)
        upstream_base_url = base_url
        if args.via_desktop_proxy:
            from desktop.local_app_server import LocalAppServer

            desktop_proxy = LocalAppServer(upstream_base_url=base_url)
            base_url = desktop_proxy.start().rstrip("/")
        artifacts = capture_visuals(base_url=base_url, output_dir=output_dir, roles=roles, headful=args.headful)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if desktop_proxy:
            desktop_proxy.stop()
        if server:
            server.close()

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "upstream_base_url": upstream_base_url,
        "via_desktop_proxy": bool(args.via_desktop_proxy),
        "roles": roles,
        "viewports": [asdict(viewport) for viewport in VIEWPORTS],
        "artifacts": artifacts,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Visual screenshots written to {output_dir}")
    print(f"Summary written to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

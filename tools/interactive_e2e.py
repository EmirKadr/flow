"""Run an interactive end-to-end exercise of the Bemanning web app.

This is the "let an agent poke around" tool. It creates a disposable local
database, starts the app, clicks through important workflows, creates records,
edits schedule cells, verifies role restrictions, and saves screenshots plus a
JSON report.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from tools import visual_smoke


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "interactive"
AGENT_PASSWORD = "AgentTest123"


WEB_WORKFLOW_STEPS = (
    "login_admin",
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
)


@dataclass
class StepResult:
    name: str
    ok: bool
    screenshot: str | None = None
    detail: str = ""


class InteractiveRun:
    def __init__(self, page, base_url: str, output_dir: Path, run_id: str):
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.output_dir = output_dir
        self.run_id = run_id
        self.results: list[StepResult] = []
        self.agent_user = f"agent_user_{run_id}"
        self.agent_person = f"Agent Person {run_id}"
        self.agent_person_updated = f"Agent Person Redigerad {run_id}"
        self.agent_activity = f"Agent Aktivitet {run_id}"
        self.agent_activity_updated = f"Agent Aktivitet Redigerad {run_id}"

    def url(self, path: str) -> str:
        return self.base_url + path

    def screenshot(self, name: str) -> str:
        path = self.output_dir / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(path), full_page=True)
        return str(path.relative_to(self.output_dir))

    def record(self, name: str, *, screenshot: str | None = None, detail: str = "") -> None:
        self.results.append(StepResult(name=name, ok=True, screenshot=screenshot, detail=detail))

    def click_and_expect_api(self, selector: str, url_part: str, method: str) -> None:
        with self.page.expect_response(
            lambda response: url_part in response.url and response.request.method == method,
            timeout=15000,
        ) as response_info:
            self.page.click(selector)
        response = response_info.value
        if not response.ok:
            body = response.text()
            self.screenshot(f"error-{method.lower()}-{url_part.strip('/').replace('/', '-')}")
            raise RuntimeError(f"{method} {url_part} failed with {response.status}: {body}")

    def goto(self, path: str, selector: str) -> None:
        self.page.goto(self.url(path), wait_until="networkidle")
        self.page.wait_for_selector(selector, timeout=15000)

    def login(self, username: str, password: str) -> None:
        self.goto("/login.html", "#login-form")
        self.page.fill("#username", username)
        self.page.fill("#password", password)
        self.page.click("button.primary")
        self.page.wait_for_url("**/index.html", timeout=15000)
        self.page.wait_for_selector("#scheduleTable", timeout=15000)

    def logout(self) -> None:
        self.page.click("#logout-link")
        self.page.wait_for_url("**/login.html", timeout=15000)

    def wait_for_text(self, text: str) -> None:
        self.page.get_by_text(text, exact=False).first.wait_for(state="attached", timeout=15000)

    def set_color(self, selector: str, value: str) -> None:
        self.page.eval_on_selector(
            selector,
            """(el, value) => {
                el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            value,
        )

    def dismiss_dialogs(self) -> None:
        self.page.on("dialog", lambda dialog: dialog.accept())

    def run(self) -> list[StepResult]:
        self.dismiss_dialogs()
        self.login("admin", "admin123")
        self.record("login_admin", screenshot=self.screenshot("01-admin-login"))

        self.create_user()
        self.edit_user()
        self.toggle_user_setting()
        self.toggle_user_active()
        self.create_activity()
        self.edit_activity()
        self.deactivate_activity()
        self.create_person()
        self.edit_person_inline()
        self.edit_person_fields_inline()
        self.edit_person_week_template()
        self.edit_schedule()
        self.exercise_overview()
        self.exercise_history()
        self.exercise_viewer_and_guards()
        return self.results

    def create_user(self) -> None:
        self.goto("/anvandare.html", "#users-body")
        self.page.click("#new-user")
        self.page.wait_for_selector("#m-username", timeout=15000)
        self.page.fill("#m-username", self.agent_user)
        self.page.fill("#m-display-name", "Agent Test User")
        self.page.locator('input[name="m-role"][value="leader"]').set_checked(True)
        self.page.locator("#m-area").select_option(label="Mestergruppen")
        self.page.fill("#m-password", AGENT_PASSWORD)
        before = self.screenshot("02-create-user-modal")
        self.click_and_expect_api("#m-save", "/api/users", "POST")
        self.wait_for_text(self.agent_user)
        self.record("create_user", screenshot=before, detail=self.agent_user)
        self.record("create_user_saved", screenshot=self.screenshot("03-user-created"))

    def edit_user(self) -> None:
        row = self.page.locator("#users-body tr", has_text=self.agent_user)
        row.locator("button[data-edit]").click()
        self.page.wait_for_selector("#m-display-name", timeout=15000)
        self.page.fill("#m-display-name", "Agent Test User Redigerad")
        self.page.locator('input[name="m-role"][value="leader"]').set_checked(False)
        self.page.locator('input[name="m-role"][value="viewer"]').set_checked(True)
        self.page.locator("#m-area").select_option(label="Granngården")
        modal = self.screenshot("04-edit-user-modal")
        self.page.click("#m-save")
        self.wait_for_text("Agent Test User Redigerad")
        self.record("edit_user", screenshot=modal)
        self.record("edit_user_saved", screenshot=self.screenshot("05-user-edited"))

    def toggle_user_setting(self) -> None:
        checkbox = self.page.locator("#lock-foreign-schedule-cells")
        initial = checkbox.is_checked()
        checkbox.set_checked(not initial)
        self.page.wait_for_timeout(500)
        checkbox.set_checked(initial)
        self.page.wait_for_timeout(500)
        self.record("toggle_user_setting", screenshot=self.screenshot("06-user-setting-toggled"))

    def toggle_user_active(self) -> None:
        row = self.page.locator("#users-body tr", has_text=self.agent_user)
        row.locator("button[data-toggle]").click()
        self.page.wait_for_timeout(700)
        show_inactive = self.page.locator("#show-inactive")
        if not show_inactive.is_checked():
            show_inactive.check()
        self.wait_for_text(self.agent_user)
        row = self.page.locator("#users-body tr", has_text=self.agent_user)
        row.locator("button[data-toggle]").click()
        self.page.wait_for_timeout(700)
        self.record("toggle_user_active", screenshot=self.screenshot("07-user-active-toggled"))

    def create_activity(self) -> None:
        self.goto("/stallen.html", "#acts-body")
        self.page.click("#new-act")
        self.page.wait_for_selector("#m-label", timeout=15000)
        self.page.fill("#m-label", self.agent_activity)
        self.page.locator("#m-area").select_option(label="Granngården")
        self.set_color("#m-color", "#34d399")
        self.page.select_option("#m-cat", "work")
        self.page.fill("#m-sort", "998")
        modal = self.screenshot("06-create-activity-modal")
        self.page.click("#m-save")
        self.wait_for_text(self.agent_activity)
        self.record("create_activity", screenshot=modal)
        self.record("create_activity_saved", screenshot=self.screenshot("07-activity-created"))

    def edit_activity(self) -> None:
        row = self.page.locator("#acts-body tr", has_text=self.agent_activity)
        row.locator("button[data-edit]").click()
        self.page.wait_for_selector("#m-label", timeout=15000)
        self.page.fill("#m-label", self.agent_activity_updated)
        self.set_color("#m-color", "#60a5fa")
        modal = self.screenshot("08-edit-activity-modal")
        self.page.click("#m-save")
        self.wait_for_text(self.agent_activity_updated)
        self.record("edit_activity", screenshot=modal)
        self.record("edit_activity_saved", screenshot=self.screenshot("09-activity-edited"))

    def deactivate_activity(self) -> None:
        row = self.page.locator("#acts-body tr", has_text=self.agent_activity_updated)
        row.locator("button[data-delete]").click()
        self.page.wait_for_timeout(700)
        show_inactive = self.page.locator("#show-inactive")
        if not show_inactive.is_checked():
            show_inactive.check()
        self.wait_for_text(self.agent_activity_updated)
        self.record("deactivate_activity", screenshot=self.screenshot("10-activity-deactivated"))

    def create_person(self) -> None:
        self.goto("/personer.html", "#persons-body")
        self.page.click("#new-person")
        self.page.wait_for_selector("#m-name", timeout=15000)
        self.page.fill("#m-name", self.agent_person)
        self.page.locator("#m-area").select_option(label="Mestergruppen")
        self.page.locator("#m-activity").select_option(label="MG VM")
        self.page.fill("#m-sort", "997")
        modal = self.screenshot("10-create-person-modal")
        self.page.click("#m-save")
        self.wait_for_text(self.agent_person)
        self.record("create_person", screenshot=modal)
        self.record("create_person_saved", screenshot=self.screenshot("11-person-created"))

    def edit_person_inline(self) -> None:
        row = self.page.locator("#persons-body tr", has_text=self.agent_person)
        row.locator("td").nth(0).click()
        self.page.wait_for_selector("#persons-body input.inline-input", timeout=15000)
        self.page.fill("#persons-body input.inline-input", self.agent_person_updated)
        self.page.keyboard.press("Enter")
        self.wait_for_text(self.agent_person_updated)
        self.record("edit_person_inline", screenshot=self.screenshot("12-person-inline-edited"))

    def edit_person_fields_inline(self) -> None:
        row = self.page.locator("#persons-body tr", has_text=self.agent_person_updated)
        row.locator("td").nth(1).click()
        self.page.wait_for_selector("#persons-body select.inline-input", timeout=15000)
        self.page.locator("#persons-body select.inline-input").select_option(label="Autostore")
        self.page.wait_for_timeout(700)

        row = self.page.locator("#persons-body tr", has_text=self.agent_person_updated)
        row.locator("td").nth(1).click()
        self.page.wait_for_selector("#persons-body select.inline-input", timeout=15000)
        self.page.locator("#persons-body select.inline-input").select_option(label="Mestergruppen")
        self.page.wait_for_timeout(700)

        row = self.page.locator("#persons-body tr", has_text=self.agent_person_updated)
        row.locator("td").nth(4).click()
        self.page.wait_for_selector("#persons-body input.inline-input", timeout=15000)
        self.page.fill("#persons-body input.inline-input", "996")
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(700)

        row = self.page.locator("#persons-body tr", has_text=self.agent_person_updated)
        row.locator("td").nth(3).click()
        self.page.wait_for_timeout(700)
        show_inactive = self.page.locator("#show-inactive")
        if not show_inactive.is_checked():
            show_inactive.check()
        self.wait_for_text(self.agent_person_updated)
        row = self.page.locator("#persons-body tr", has_text=self.agent_person_updated)
        row.locator("td").nth(3).click()
        self.page.wait_for_timeout(700)
        self.record("edit_person_fields_inline", screenshot=self.screenshot("13-person-fields-inline-edited"))

    def edit_person_week_template(self) -> None:
        row = self.page.locator("#persons-body tr", has_text=self.agent_person_updated)
        row.locator("button[data-schedule]").click()
        self.page.wait_for_selector(".modal-backdrop .modal", timeout=15000)
        first_row = self.page.locator(".modal-backdrop tr[data-weekday='1']")
        first_row.locator(".m-from").select_option("8")
        first_row.locator(".m-to").select_option("17")
        self.page.locator(".modal-backdrop tr[data-weekday='6'] .m-off").check()
        self.page.locator(".modal-backdrop tr[data-weekday='7'] .m-off").check()
        modal = self.screenshot("13-week-template-modal")
        self.page.click("#sch-save")
        self.page.wait_for_selector(".modal-backdrop", state="detached", timeout=15000)
        self.record("edit_person_week_template", screenshot=modal)

        row = self.page.locator("#persons-body tr", has_text=self.agent_person_updated)
        row.locator("button[data-schedule]").click()
        self.page.wait_for_selector("#sch-hourly", timeout=15000)
        self.page.check("#sch-hourly")
        hourly_modal = self.screenshot("14-week-template-hourly")
        self.page.click("#sch-save")
        self.page.wait_for_selector(".modal-backdrop", state="detached", timeout=15000)
        self.record("edit_person_hourly_schedule", screenshot=hourly_modal)

        row = self.page.locator("#persons-body tr", has_text=self.agent_person_updated)
        row.locator("button[data-schedule]").click()
        self.page.wait_for_selector("#sch-hourly", timeout=15000)
        self.page.uncheck("#sch-hourly")
        self.page.click("#sch-default")
        self.page.click("#sch-save")
        self.page.wait_for_selector(".modal-backdrop", state="detached", timeout=15000)

    def schedule_row(self):
        return self.page.locator("#scheduleBody tr", has_text=self.agent_person_updated)

    def schedule_cell(self, hour: int):
        return self.schedule_row().locator(f"td[data-hour='{hour}']")

    def edit_schedule(self) -> None:
        self.goto("/index.html", "#scheduleTable")
        self.page.locator("#areaSelect").select_option(label="Mestergruppen")
        self.page.wait_for_selector("#scheduleBody tr", timeout=15000)
        self.page.fill("#nameFilter", self.agent_person_updated)
        self.wait_for_text(self.agent_person_updated)

        self.schedule_cell(8).locator("select").first.select_option(label="MG VM")
        self.page.wait_for_timeout(700)
        self.record("edit_schedule_cell", screenshot=self.screenshot("14-schedule-cell-edited"))

        self.schedule_cell(9).dblclick()
        self.page.wait_for_selector(
            f"#scheduleBody tr:has-text('{self.agent_person_updated}') td[data-hour='9'][data-split='1']",
            timeout=15000,
        )
        self.schedule_cell(9).locator("select").nth(0).select_option(label="MG VM")
        self.page.wait_for_timeout(300)
        self.schedule_cell(9).locator("select").nth(1).select_option(label="MG Stöd")
        self.page.wait_for_timeout(700)
        self.record("split_schedule_cell", screenshot=self.screenshot("15-schedule-cell-split"))

        self.schedule_cell(8).click(position={"x": 8, "y": 8})
        self.page.keyboard.press("Control+C")
        self.schedule_cell(10).click(position={"x": 8, "y": 8})
        self.page.keyboard.press("Control+V")
        self.page.wait_for_timeout(700)
        self.record("copy_paste_schedule_cell", screenshot=self.screenshot("16-schedule-copy-paste"))

        self.page.click("#copyBtn")
        self.page.wait_for_selector("#cp-td", timeout=15000)
        self.page.select_option("#cp-td", "5")
        self.page.check("#cp-ow")
        modal = self.screenshot("17-copy-day-modal-filled")
        self.page.click("#cp-go")
        self.page.wait_for_selector(".modal-backdrop", state="detached", timeout=15000)
        self.page.wait_for_timeout(700)
        self.record("copy_day", screenshot=modal)
        self.record("copy_day_done", screenshot=self.screenshot("18-copy-day-done"))

        self.page.click("#clearBtn")
        self.page.wait_for_timeout(700)
        self.record("clear_day", screenshot=self.screenshot("19-clear-day-done"))

        self.page.click("#undoBtn")
        self.page.wait_for_timeout(700)
        undo_shot = self.screenshot("20-undo-after-clear")
        self.page.click("#redoBtn")
        self.page.wait_for_timeout(700)
        self.record("undo_redo", screenshot=undo_shot)
        self.record("redo_done", screenshot=self.screenshot("21-redo-after-clear"))

    def exercise_overview(self) -> None:
        self.goto("/overblick.html", "#overviewTable")
        self.page.locator("#areaSelect").select_option(label="Mestergruppen")
        self.page.wait_for_selector("#overviewBody tr", timeout=15000)
        self.page.fill("#nameFilter", self.agent_person_updated)
        self.wait_for_text(self.agent_person_updated)
        first_day_select = self.schedule_like_overview_select()
        first_day_select.select_option(label="MG VM")
        self.page.wait_for_timeout(700)
        self.record("overview_edit", screenshot=self.screenshot("22-overview-day-edited"))
        self.page.select_option("#viewMode", "month")
        self.page.wait_for_timeout(700)
        self.record("overview_month", screenshot=self.screenshot("23-overview-month-after-edit"))

    def schedule_like_overview_select(self):
        return self.page.locator("#overviewBody tr", has_text=self.agent_person_updated).locator("td.day select").first

    def exercise_history(self) -> None:
        self.goto("/historik.html", "#auditBody")
        self.page.select_option("#periodSelect", "all")
        self.page.fill("#actionFilter", "create")
        self.page.click("#refreshAuditBtn")
        self.page.wait_for_timeout(700)
        self.record("history_filter", screenshot=self.screenshot("24-history-filtered"))

    def exercise_viewer_and_guards(self) -> None:
        self.logout()
        self.login("visual_viewer", visual_smoke.VISUAL_PASSWORD)
        self.page.locator("#areaSelect").select_option(label="Mestergruppen")
        self.page.wait_for_selector("#scheduleBody tr", timeout=15000)
        if not self.page.locator("#copyBtn").is_disabled():
            raise AssertionError("Viewer should not be able to copy schedule days")
        if self.page.locator("#scheduleBody select:not(:disabled)").count() != 0:
            raise AssertionError("Viewer should not have editable schedule selects")
        self.record("viewer_read_only", screenshot=self.screenshot("25-viewer-read-only"))

        for path, name in (
            ("/personer.html", "viewer_blocked_personer"),
            ("/stallen.html", "viewer_blocked_stallen"),
            ("/anvandare.html", "viewer_blocked_anvandare"),
            ("/historik.html", "viewer_blocked_historik"),
        ):
            self.page.goto(self.url(path), wait_until="networkidle")
            self.page.wait_for_selector("#scheduleTable", timeout=15000)
            self.record(name, screenshot=self.screenshot(f"26-{name}"))

        self.logout()
        self.login("visual_leader", visual_smoke.VISUAL_PASSWORD)
        for path, name in (
            ("/anvandare.html", "leader_blocked_anvandare"),
            ("/historik.html", "leader_blocked_historik"),
        ):
            self.page.goto(self.url(path), wait_until="networkidle")
            self.page.wait_for_selector("#scheduleTable", timeout=15000)
            self.record(name, screenshot=self.screenshot(f"27-{name}"))
        self.record("role_access_guards", detail="viewer and leader blocked pages verified")


def _load_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright saknas. Kör: python -m pip install -r requirements-dev.txt "
            "och sedan: python -m playwright install chromium"
        ) from exc
    return sync_playwright


def run_web_interactive(*, base_url: str, output_dir: Path, headful: bool = False) -> list[StepResult]:
    sync_playwright = _load_playwright()
    run_id = datetime.now().strftime("%H%M%S")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headful)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            device_scale_factor=1,
            locale="sv-SE",
        )
        try:
            page = context.new_page()
            runner = InteractiveRun(page, base_url, output_dir, run_id)
            return runner.run()
        finally:
            context.close()
            browser.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Use an already running server instead of starting a disposable local one.")
    parser.add_argument("--output", type=Path, help="Output directory for screenshots and report.")
    parser.add_argument("--headful", action="store_true", help="Show the browser while running the workflow.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output or (DEFAULT_OUTPUT_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S"))
    output_dir.mkdir(parents=True, exist_ok=True)

    server = None
    base_url = args.base_url
    try:
        if not base_url:
            base_url, server = visual_smoke.start_local_server(output_dir)
        results = run_web_interactive(base_url=base_url, output_dir=output_dir, headful=args.headful)
    finally:
        if server:
            server.close()

    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "expected_steps": WEB_WORKFLOW_STEPS,
        "results": [result.__dict__ for result in results],
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Interactive E2E completed: {len(results)} steps")
    print(f"Output written to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

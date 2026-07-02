from pathlib import Path
import tempfile
from uuid import uuid4

import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="module")
def local_label_editor_server():
    output_dir = Path(tempfile.gettempdir()) / f"flow-label-editor-browser-{uuid4().hex}"
    output_dir.mkdir(parents=True, exist_ok=True)
    base_url, server = visual_smoke.start_local_server(output_dir)
    try:
        yield base_url
    finally:
        server.close()


@pytest.fixture(scope="module")
def chromium_browser():
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                pytest.skip("Playwright Chromium is not installed")
            raise
        try:
            yield browser
        finally:
            browser.close()


def login_admin(page, base_url: str) -> None:
    page.goto(f"{base_url}/login.html", wait_until="networkidle")
    page.fill("#username", "admin")
    page.fill("#password", "admin123")
    page.click("button.primary")
    page.wait_for_url("**/index.html", timeout=15000)
    page.wait_for_selector("#scheduleTable", timeout=15000)


def test_label_editor_keyboard_shortcuts_and_symbol_picker(local_label_editor_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    objects = page.locator("#labelCanvas .label-object")
    try:
        login_admin(page, local_label_editor_server)
        page.goto(f"{local_label_editor_server}/label-editor.html", wait_until="networkidle")
        page.wait_for_selector("#labelCanvas .label-object", timeout=15000)

        expect(objects).to_have_count(1)
        page.keyboard.press("Delete")
        expect(objects).to_have_count(0)
        page.keyboard.press("Control+Z")
        expect(objects).to_have_count(1)

        page.keyboard.press("Control+C")
        page.keyboard.press("Control+V")
        expect(objects).to_have_count(2)
        page.keyboard.press("Control+X")
        expect(objects).to_have_count(1)
        page.keyboard.press("Control+Z")
        expect(objects).to_have_count(2)

        page.keyboard.press("Backspace")
        expect(objects).to_have_count(1)
        page.keyboard.press("Control+Z")
        expect(objects).to_have_count(2)
        page.keyboard.press("Control+Y")
        expect(objects).to_have_count(1)
        page.keyboard.press("Control+Z")
        expect(objects).to_have_count(2)
        page.keyboard.press("Control+Shift+Z")
        expect(objects).to_have_count(1)

        page.click("#labelCanvas .label-object")
        page.fill("#labelObjectValue", "ABC")
        page.focus("#labelObjectValue")
        page.keyboard.press("End")
        page.keyboard.press("Backspace")
        expect(page.locator("#labelObjectValue")).to_have_value("AB")
        expect(objects).to_have_count(1)

        page.get_by_role("button", name="Symbol").click()
        expect(page.locator(".label-symbol-picker")).to_be_visible()
        expect(page.locator(".label-symbol-choice")).to_have_count(40)
        page.get_by_role("button", name="Paket").click()
        expect(objects).to_have_count(2)
        expect(page.locator("#labelCanvas .label-object").last).to_contain_text("📦")
    finally:
        context.close()

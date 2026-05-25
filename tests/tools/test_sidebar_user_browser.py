import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="module")
def local_sidebar_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("sidebar-user-browser")
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


def test_sidebar_footer_shows_role_between_name_and_logout(local_sidebar_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        page.goto(f"{local_sidebar_server}/login.html", wait_until="networkidle")
        page.fill("#username", "admin")
        page.fill("#password", "admin123")
        page.click("button.primary")
        page.wait_for_url("**/index.html", timeout=15000)
        page.wait_for_selector(".sidebar-bottom .sidebar-role", timeout=15000)

        expect(page.locator(".sidebar-bottom .who")).to_have_text("Visual Admin")
        expect(page.locator(".sidebar-bottom .sidebar-role")).to_have_text("Super User, Administratör")
        expect(page.locator(".sidebar-bottom .logout")).to_have_text("Logga ut")

        order = page.locator(".sidebar-bottom > div:not(.avatar)").evaluate(
            """(container) => Array.from(container.children).map((child) => child.className || child.id)"""
        )
        assert order == ["who", "sidebar-role", "logout"]
    finally:
        context.close()


def test_sidebar_log_persists_across_view_navigation(local_sidebar_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        page.goto(f"{local_sidebar_server}/login.html", wait_until="networkidle")
        page.fill("#username", "admin")
        page.fill("#password", "admin123")
        page.click("button.primary")
        page.wait_for_url("**/index.html", timeout=15000)
        page.wait_for_selector("#log-toggle", timeout=15000)

        page.evaluate("() => window.flowLog.success('Testlogg sparad över vybyte', 'Test')")
        page.goto(f"{local_sidebar_server}/personer.html", wait_until="networkidle")
        page.wait_for_selector("#persons-body tr", timeout=15000)
        page.click("#log-toggle")

        expect(page.locator("#log-sidebar")).to_be_visible()
        expect(page.locator("#log-sidebar")).to_contain_text("Testlogg sparad över vybyte")
        expect(page.locator("#log-sidebar")).to_contain_text("Öppnade vy")
        page.click("#log-sidebar-clear")
        expect(page.locator("#log-sidebar")).to_contain_text("Ingen logg")
    finally:
        context.close()

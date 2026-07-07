"""Browsertester för stale-while-revalidate-piloten (Personer + Översikt).

Kontrakten (uppgift 3C i nattplanen, godkänd av Emir 2026-07-07):
1. Ett sidbesök lämnar en SWR-snapshot i sessionStorage.
2. Vid nästa sidladdning renderas innehållet från snapshoten även om
   API:et är helt onåbart — det är själva löftet "visa cachat direkt".
3. En mutation (POST) rensar snapshots så inaktuellt data aldrig
   överlever en ändring.
"""
import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="module")
def local_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("swr-pilot-browser")
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


def login(page, base_url):
    page.goto(f"{base_url}/login.html", wait_until="load")
    page.fill("#username", "admin")
    page.fill("#password", "admin123")
    page.click("button.primary")
    page.wait_for_url("**/index.html", timeout=15000)


def swr_keys(page):
    return page.evaluate(
        """() => {
          const keys = [];
          for (let i = 0; i < sessionStorage.length; i += 1) {
            const key = sessionStorage.key(i);
            if (key && key.startsWith("flow-api-swr:")) keys.push(key);
          }
          return keys;
        }"""
    )


def test_persons_page_renders_from_snapshot_when_api_is_down(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login(page, local_server)

        # 1) Första besöket skapar snapshot.
        page.goto(f"{local_server}/personer.html", wait_until="load")
        page.wait_for_selector("#persons-body tr", timeout=15000)
        keys = swr_keys(page)
        assert any("/api/persons" in key for key in keys), keys

        # 2) API:et släcks — sidan ska ändå rendera personerna från snapshoten.
        page.route("**/api/persons*", lambda route: route.abort())
        page.goto(f"{local_server}/personer.html", wait_until="load")
        page.wait_for_selector("#persons-body tr", timeout=15000)
        rows = page.locator("#persons-body tr").count()
        assert rows >= 1
        page.unroute("**/api/persons*")

        # 3) En mutation rensar snapshots (api.post -> clearGetCache -> SWR).
        page.evaluate("() => window.api.post('/api/auth/logout')")
        page.wait_for_function(
            """() => {
              for (let i = 0; i < sessionStorage.length; i += 1) {
                const key = sessionStorage.key(i);
                if (key && key.startsWith("flow-api-swr:")) return false;
              }
              return true;
            }""",
            timeout=15000,
        )
    finally:
        context.close()


def test_overview_renders_matrix_from_snapshot_when_api_is_down(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login(page, local_server)

        page.goto(f"{local_server}/overblick.html", wait_until="load")
        page.wait_for_selector("#overviewBody tr", timeout=15000)
        keys = swr_keys(page)
        assert any("/api/overview" in key for key in keys), keys

        page.route("**/api/overview?*", lambda route: route.abort())
        page.goto(f"{local_server}/overblick.html", wait_until="load")
        page.wait_for_selector("#overviewBody tr", timeout=15000)
        assert page.locator("#overviewBody tr").count() >= 1
    finally:
        context.close()

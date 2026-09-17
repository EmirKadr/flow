from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.backend.main import app
from app.backend.routers import public_dpak
from app.backend.site_migration import TARGET_ORIGIN


playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(headless=True)
        except playwright_api.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip("Playwright Chromium is not installed")
            raise
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, public_dpak.get_db, lambda: None)
    monkeypatch.setattr(public_dpak, "dataset_status", lambda *_: {"ready": True})
    monkeypatch.setattr(public_dpak, "_public_dpak_model_config", lambda: SimpleNamespace(model="test", max_tokens=50))
    monkeypatch.setattr(public_dpak, "run_public_dpak_agent", lambda *_, **__: {"answer": "D-pak fungerar fortfarande.", "table": []})
    client = TestClient(app, follow_redirects=False)
    context = browser.new_context(locale="sv-SE")

    def route_request(route):
        request = route.request
        if request.url.startswith(TARGET_ORIGIN + "/"):
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body="<h1>Nya flow</h1>")
            return
        response = client.request(request.method, request.url, content=request.post_data_buffer, headers=request.headers)
        route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)

    context.route("**/*", route_request)
    page = context.new_page()
    yield page
    context.close()
    client.close()


def test_cached_page_uses_migration_guard_to_move_with_query_and_fragment(page):
    def cached_page(route):
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body='''
            <html><head><script src="/js/site_migration.js" defer></script></head>
            <body>Gammal cachad vy</body></html>
        ''')

    page.route("**/historik.html?tab=health", cached_page)
    page.goto("https://stigamo.nu/historik.html?tab=health#waits")
    expect(page).to_have_url(TARGET_ORIGIN + "/historik.html?tab=health#waits")


def test_previously_open_tab_cannot_save_after_migration(page):
    # Simulate HTML loaded before deployment, with the existing shared API wrapper.
    def old_page(route):
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body='''
            <html><body><button id="save">Spara</button><p id="result"></p>
            <script src="/js/api.js"></script><script>
              document.querySelector('#save').onclick = async () => {
                try { await api.post('/api/schedule/cells', {}); }
                catch (error) { document.querySelector('#result').textContent = error.message; }
              };
            </script></body></html>
        ''')

    api_source = (Path(__file__).resolve().parents[2] / "app/frontend/js/api.js").read_text(encoding="utf-8")
    page.route("**/old-tab.html", old_page)
    page.route("**/js/api.js", lambda route: route.fulfill(status=200, content_type="text/javascript", body=api_source))
    page.goto("https://stigamo.nu/old-tab.html")
    page.click("#save")
    expect(page.locator("#result")).to_contain_text(TARGET_ORIGIN)
    expect(page.locator("#result")).to_contain_text("flow har flyttat")


@pytest.mark.parametrize("path", ["/d-pak", "/d-pak/", "/dpak-fraga.html"])
def test_dpak_chat_remains_usable_on_the_old_domain(page, path):
    page.goto("https://stigamo.nu" + path + "?business=TEST")
    expect(page.locator("#publicDpakStatus")).to_contain_text("Underlag klart")
    page.fill("#publicDpakInput", "En testfråga")
    page.click("#publicDpakSend")
    expect(page.locator(".public-dpak-message.assistant p")).to_have_text("D-pak fungerar fortfarande.")
    assert urlsplit(page.url).hostname == "stigamo.nu"


def test_guard_leaves_local_development_on_its_own_origin(page):
    page.route("**/local-test.html", lambda route: route.fulfill(status=200, content_type="text/html; charset=utf-8", body='''
        <html><head><script src="/js/site_migration.js" defer></script></head><body>Lokal app</body></html>
    '''))
    with page.expect_response("**/api/site-migration") as response:
        page.goto("http://127.0.0.1/local-test.html")
    assert response.value.json()["active"] is False
    expect(page).to_have_url("http://127.0.0.1/local-test.html")

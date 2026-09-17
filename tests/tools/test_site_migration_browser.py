from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.backend.main import app
from app.backend.routers import public_dpak


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
        if urlsplit(request.url).hostname not in {"stigamo.nu", "127.0.0.1"}:
            route.abort()
            return
        response = client.request(request.method, request.url, content=request.post_data_buffer, headers=request.headers)
        route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)

    context.route("**/*", route_request)
    page = context.new_page()
    yield page
    context.close()
    client.close()


def test_cached_page_stays_on_stigamo_with_query_and_fragment(page):
    def cached_page(route):
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body='''
            <html><head><script src="/js/site_migration.js" defer></script></head>
            <body>Gammal cachad vy</body></html>
        ''')

    page.route("**/historik.html?tab=health", cached_page)
    page.goto("https://stigamo.nu/historik.html?tab=health#waits")
    expect(page).to_have_url("https://stigamo.nu/historik.html?tab=health#waits")
    expect(page.locator("body")).to_have_text("Gammal cachad vy")


def test_previously_loaded_migration_client_receives_inactive_status(page):
    # Simulate the previous bundle's status contract, even when that JS is cached.
    def old_page(route):
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body='''
            <html><body><p id="result"></p><script>
              fetch('/api/site-migration', {cache: 'no-store'})
                .then(response => response.json()).then(state => {
                  if (state.active) window.location.replace(state.target_origin);
                  else document.querySelector('#result').textContent = 'Appen kan användas';
                });
            </script></body></html>
        ''')

    page.route("**/old-tab.html", old_page)
    page.goto("https://stigamo.nu/old-tab.html")
    expect(page.locator("#result")).to_have_text("Appen kan användas")
    expect(page).to_have_url("https://stigamo.nu/old-tab.html")


def test_login_page_remains_on_stigamo(page):
    page.goto("https://stigamo.nu/login.html", wait_until="networkidle")
    expect(page.locator("#login-form")).to_be_visible()
    expect(page.locator("#login-form button[type=submit]")).to_be_enabled()
    expect(page).to_have_url("https://stigamo.nu/login.html")


@pytest.mark.parametrize("path", ["/d-pak", "/d-pak/", "/dpak-fraga.html"])
def test_dpak_chat_remains_usable_on_the_old_domain(page, path):
    page.goto("https://stigamo.nu" + path + "?business=TEST")
    expect(page.locator("#publicDpakStatus")).to_contain_text("Underlag klart")
    page.fill("#publicDpakInput", "En testfråga")
    page.click("#publicDpakSend")
    expect(page.locator(".public-dpak-message.assistant p")).to_have_text("D-pak fungerar fortfarande.")
    assert urlsplit(page.url).hostname == "stigamo.nu"


def test_cached_script_leaves_local_development_on_its_own_origin(page):
    page.route("**/local-test.html", lambda route: route.fulfill(status=200, content_type="text/html; charset=utf-8", body='''
        <html><head><script src="/js/site_migration.js" defer></script></head><body>Lokal app</body></html>
    '''))
    page.goto("http://127.0.0.1/local-test.html")
    expect(page.locator("body")).to_have_text("Lokal app")
    expect(page).to_have_url("http://127.0.0.1/local-test.html")

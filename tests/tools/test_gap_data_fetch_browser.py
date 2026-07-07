"""Browsertester för datahämtnings-gatingen (W18, 2026-07-07).

Sidan `hamta-data.html` drivs av `data_fetch.js`. Testerna skyddar de
strukturella gating-kontrakten UTAN att bero på riktig seed-data eller en
konfigurerad MiniMax/katalog — health/plan/run/export mockas via page.route:

1. Gating-states på knapparna:
   - `#dataFetchPlan` (Tolka) blir aktiv när katalog + MiniMax är redo.
   - `#dataFetchRun` är låst tills planen har `status === "ok"`.
   - `#dataFetchExport` är låst tills körningen gett ett `session_id`.
2. Kolumn-chips (`[data-remove-column]`) renderas ur planen och den sista
   kolumnen kan inte tas bort (toast "Minst en kolumn måste vara kvar.").
3. Run -> resultattabell, Export -> rätt export-URL med session-id.

Kräver att den inloggade användaren har dataFetch-behörighet. Saknas den
(sidan redirectar bort) skippas testet i stället för att fälla CI.
"""
import json

import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


HEALTH_BODY = {
    "ok": True,
    "catalog_configured": True,
    "api_configured": True,
    "minimax_configured": True,
    "catalog": {"views": 3, "columns": 12},
    "api_missing": [],
}

PLAN_BODY = {
    "plan": {
        "status": "ok",
        "view": "activity_log",
        "view_label": "Aktivitetslogg",
        "output_columns": ["col_type", "col_article", "col_date"],
        "output_column_labels": {
            "col_type": "Typ",
            "col_article": "Artikel",
            "col_date": "Datum",
        },
        "filters": [],
        "reason": "Mockad plan för browsertest.",
    }
}

RUN_BODY = {
    "columns": [
        {"id": "col_type", "label": "Typ"},
        {"id": "col_article", "label": "Artikel"},
        {"id": "col_date", "label": "Datum"},
    ],
    "rows": [
        {"col_type": "korrigering", "col_article": "A-1", "col_date": "2026-01-01"},
    ],
    "session_id": "sess-abc-123",
    "shown_rows": 1,
    "total_rows": 1,
    "truncated": False,
}


@pytest.fixture(scope="module")
def local_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("data-fetch-browser")
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


def install_query_data_routes(page, export_urls):
    """Mockar query-data-endpoints; övriga requests går till lokala servern."""

    def fulfill_json(route, body):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(body),
        )

    page.route("**/api/query-data/health", lambda route: fulfill_json(route, HEALTH_BODY))
    page.route("**/api/query-data/plan", lambda route: fulfill_json(route, PLAN_BODY))
    page.route("**/api/query-data/run", lambda route: fulfill_json(route, RUN_BODY))

    def handle_export(route):
        export_urls.append(route.request.url)
        route.fulfill(
            status=200,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"content-disposition": 'attachment; filename="hamta-data.xlsx"'},
            body=b"PK\x03\x04mock-xlsx",
        )

    page.route("**/api/query-data/export/**", handle_export)


def open_data_fetch(page, base_url):
    """Navigerar till hamta-data.html; returnerar True om sidan är åtkomlig."""
    page.goto(f"{base_url}/hamta-data.html", wait_until="load")
    try:
        page.wait_for_selector("#dataFetchPlan", timeout=10000)
    except PlaywrightError:
        return False
    # Redirect vid nekad behörighet landar på annan sida.
    return page.url.endswith("/hamta-data.html")


def test_data_fetch_gating_and_flow(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE", accept_downloads=True)
    page = context.new_page()
    export_urls = []
    try:
        try:
            login(page, local_server)
        except PlaywrightError as exc:
            pytest.skip(f"Kunde inte logga in på lokala seeden: {exc}")

        install_query_data_routes(page, export_urls)

        if not open_data_fetch(page, local_server):
            pytest.skip("Inloggad användare saknar dataFetch-behörighet i seeden.")

        run_button = page.locator("#dataFetchRun")
        export_button = page.locator("#dataFetchExport")
        plan_button = page.locator("#dataFetchPlan")

        # 1) Startläge: health mockad som redo -> Tolka aktiv, Run/Export låsta.
        expect(plan_button).to_be_enabled(timeout=10000)
        expect(run_button).to_be_disabled()
        expect(export_button).to_be_disabled()

        # 2) Tolka -> plan (status ok). Run låses upp, kolumn-chips renderas.
        page.fill("#dataFetchPrompt", "Exportera aktivitetsloggen. Visa typ, artikel och datum.")
        plan_button.click()
        page.wait_for_selector("#dataFetchPlanPanel:not([hidden])", timeout=15000)
        page.wait_for_selector("[data-remove-column]", timeout=15000)
        expect(page.locator("[data-remove-column]")).to_have_count(3)
        expect(run_button).to_be_enabled()
        # Export fortfarande låst innan körning.
        expect(export_button).to_be_disabled()

        # 3) Run -> resultattabell. Export låses upp när session_id finns.
        run_button.click()
        page.wait_for_selector("#dataFetchResultPanel:not([hidden]) table", timeout=15000)
        expect(page.locator("#dataFetchResultPanel table tbody")).to_contain_text("korrigering")
        expect(export_button).to_be_enabled()

        # 4) Export -> rätt URL med session-id.
        export_button.click()

        # Polla tills route-handlern fångat export-requesten.
        for _ in range(50):
            if export_urls:
                break
            page.wait_for_timeout(100)
        assert export_urls, "Export-requesten träffade aldrig endpointen."
        assert export_urls[-1].endswith("/api/query-data/export/sess-abc-123"), export_urls[-1]

        # 5) Sista kolumnen kan inte tas bort -> toast.
        page.click('[data-remove-column="col_type"]')
        page.click('[data-remove-column="col_article"]')
        # Nu återstår bara col_date; att ta bort den ska nekas.
        page.click('[data-remove-column="col_date"]')
        toast = page.locator(".toast", has_text="Minst en kolumn")
        expect(toast).to_be_visible(timeout=5000)
        # Alla tre chips finns kvar (den sista togs inte bort).
        expect(page.locator("[data-remove-column]")).to_have_count(3)
    finally:
        context.close()

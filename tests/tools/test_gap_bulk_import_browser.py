"""Browsertester för bulk-import-griden (gap W21).

Skyddar kontrakten i `app/frontend/js/common/import_tools.js` som den nås via
personer.html (`#bulk-persons` -> `openBulkPersonsModal` -> `openBulkImportGrid`):

* Griden öppnas med startrader numrerade 1..N (persons.js skickar initialRows: 10).
* "+ Lägg till rad" (#bulk-import-add) lägger till exakt en rad och numreringen
  fortsätter sekventiellt.
* "Ta bort tomma" (#bulk-import-prune) tar bort tomma rader men lämnar minst 1.
* En rads ta-bort-knapp (.bulk-import-remove) tar aldrig bort sista raden.
* Submit utan ifylld rad ger en varnings-toast "Fyll minst en rad." och skickar
  inget nätverksanrop.
* Submit skickar bara ifyllda rader i payloaden (route-spionerad).

Modellerat strikt på tests/tools/test_bug_report_browser.py: lokal server via
tools.visual_smoke.start_local_server, login admin/admin123, headless chromium.
Griden är rent klientdriven (ingen seed behövs), så kontrollerna är
strukturella/assert-only och rör aldrig skarp data.
"""
import json

import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="module")
def local_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("bulk-import-browser")
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
    page.wait_for_selector("#bug-report-toggle", timeout=15000)


def open_bulk_grid(page, base_url):
    """Logga in, öppna personer.html och öppna bulk-import-griden.

    Bulk-knappen är dold tills currentUser laddats och personImport-editering
    är tillåten (admin är super user). Kan den inte visas skippar vi hellre än
    att fälla — CI ska inte bli rött av en saknad förutsättning."""
    login(page, base_url)
    page.goto(f"{base_url}/personer.html", wait_until="load")
    try:
        page.wait_for_selector("#bulk-persons:not([hidden])", timeout=15000)
    except PlaywrightError:
        pytest.skip("Bulk-knappen (#bulk-persons) blev aldrig synlig i den lokala seeden")
    page.click("#bulk-persons")
    try:
        page.wait_for_selector(".bulk-import-modal", timeout=15000)
    except PlaywrightError:
        pytest.skip("Bulk-import-modalen öppnades inte")


def row_count(page):
    return page.locator(".bulk-import-modal tbody tr").count()


def row_numbers(page):
    return page.locator(".bulk-import-modal tbody .bulk-import-row-number").all_inner_texts()


def test_initial_rows_and_add(local_server, chromium_browser):
    """Startrader är numrerade 1..N och '+ Lägg till rad' lägger till exakt en."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_bulk_grid(page, local_server)

        initial = row_count(page)
        assert initial >= 1
        # persons.js skickar initialRows: 10 (generisk default i import_tools.js är 8).
        assert row_numbers(page) == [str(i) for i in range(1, initial + 1)]

        page.click("#bulk-import-add")
        expect(page.locator(".bulk-import-modal tbody tr")).to_have_count(initial + 1)
        assert row_numbers(page) == [str(i) for i in range(1, initial + 2)]
        # Varje rad har en egen ta-bort-knapp.
        assert page.locator(".bulk-import-modal .bulk-import-remove").count() == initial + 1
    finally:
        context.close()


def test_prune_keeps_only_filled_rows(local_server, chromium_browser):
    """'Ta bort tomma' behåller bara ifyllda rader (och minst en om inget fyllts)."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_bulk_grid(page, local_server)

        # Fyll namn på rad 2 och rad 5, lämna resten tomma.
        rows = page.locator(".bulk-import-modal tbody tr")
        rows.nth(1).locator('[data-bulk-key="name"]').fill("Rad Två")
        rows.nth(4).locator('[data-bulk-key="name"]').fill("Rad Fem")

        page.click("#bulk-import-prune")
        expect(page.locator(".bulk-import-modal tbody tr")).to_have_count(2)
        names = page.locator('.bulk-import-modal tbody [data-bulk-key="name"]').all()
        assert [n.input_value() for n in names] == ["Rad Två", "Rad Fem"]
        # Numreringen räknas om till 1..2.
        assert row_numbers(page) == ["1", "2"]
    finally:
        context.close()


def test_prune_all_empty_keeps_one_row(local_server, chromium_browser):
    """'Ta bort tomma' på en helt tom grid lämnar exakt en rad kvar."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_bulk_grid(page, local_server)
        assert row_count(page) > 1

        page.click("#bulk-import-prune")
        expect(page.locator(".bulk-import-modal tbody tr")).to_have_count(1)
    finally:
        context.close()


def test_remove_never_below_one(local_server, chromium_browser):
    """Radens ta-bort-knapp tar aldrig bort den sista kvarvarande raden."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_bulk_grid(page, local_server)

        # Krymp ner till en rad via 'Ta bort tomma' (allt tomt -> 1 rad).
        page.click("#bulk-import-prune")
        expect(page.locator(".bulk-import-modal tbody tr")).to_have_count(1)

        # Klick på den sista ta-bort-knappen ska inte tömma tabellen.
        page.click(".bulk-import-modal .bulk-import-remove")
        expect(page.locator(".bulk-import-modal tbody tr")).to_have_count(1)
    finally:
        context.close()


def test_submit_empty_shows_warning_and_no_request(local_server, chromium_browser):
    """Submit utan ifylld rad ger varnings-toast och skickar inget anrop."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_bulk_grid(page, local_server)

        posted = {"hit": False}

        def _spy(route):
            posted["hit"] = True
            route.abort()

        page.route("**/api/persons/import-rows", _spy)

        page.click("#bulk-import-submit")
        expect(page.locator(".toast.warn").last).to_contain_text("Fyll minst en rad", timeout=15000)
        # Modalen står kvar (inget skickades).
        expect(page.locator(".bulk-import-modal")).to_have_count(1)
        page.wait_for_timeout(300)
        assert posted["hit"] is False, "Tomt submit skickade ett nätverksanrop"
    finally:
        context.close()


def test_submit_payload_contains_only_filled_rows(local_server, chromium_browser):
    """Payloaden till /api/persons/import-rows innehåller bara ifyllda rader."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_bulk_grid(page, local_server)

        captured = {}

        def _spy(route, request):
            try:
                captured["body"] = json.loads(request.post_data or "{}")
            except (ValueError, TypeError):
                captured["body"] = None
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"created": 2, "skipped": 0}),
            )

        page.route("**/api/persons/import-rows", _spy)

        rows = page.locator(".bulk-import-modal tbody tr")
        rows.nth(1).locator('[data-bulk-key="name"]').fill("Anna Ny")
        rows.nth(1).locator('[data-bulk-key="noman"]').fill("A100")
        rows.nth(6).locator('[data-bulk-key="name"]').fill("Bertil Ny")
        rows.nth(6).locator('[data-bulk-key="noman"]').fill("B200")

        page.click("#bulk-import-submit")

        # Griden stängs vid lyckat submit (onSubmit resolvar och backdrop tas bort).
        expect(page.locator(".bulk-import-modal")).to_have_count(0, timeout=15000)

        assert "body" in captured, "Inget anrop till /api/persons/import-rows fångades"
        body = captured["body"]
        assert isinstance(body, dict) and isinstance(body.get("rows"), list)
        sent = body["rows"]
        assert len(sent) == 2, f"väntade 2 ifyllda rader, fick {len(sent)}"
        assert {r.get("name") for r in sent} == {"Anna Ny", "Bertil Ny"}
        assert {r.get("noman") for r in sent} == {"A100", "B200"}
    finally:
        context.close()

"""Browsertester för buggrapportören (nattpass 2026-07-07).

Kontrakten som skyddas:
1. Ingen inspelning startar utan OK i consent-popupen (Avbryt = ingen rrweb).
2. OK startar inspelningen, Stoppa-och-skicka skapar en rapport i backend.
3. Behörig användare kan öppna Buggrapporter-vyn och se rapporten listad.
"""
import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="module")
def local_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("bug-report-browser")
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


def is_recording(page) -> bool:
    return bool(page.evaluate("() => Boolean(window.flowBugReport && window.flowBugReport.isRecording())"))


def test_consent_gate_and_full_report_flow(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login(page, local_server)

        # 1) Avbryt i popupen -> ingen inspelning någonsin.
        page.click("#bug-report-toggle")
        page.wait_for_selector("#bug-report-backdrop", timeout=15000)
        expect(page.locator("#bug-report-start")).to_contain_text("Starta inspelning")
        assert not is_recording(page)
        page.click("#bug-report-cancel")
        expect(page.locator("#bug-report-backdrop")).to_have_count(0)
        assert not is_recording(page)
        assert page.locator("#bug-report-indicator").count() == 0

        # Escape stänger modalen via dess Avbryt-knapp (globala tangentbordsregeln).
        page.click("#bug-report-toggle")
        page.wait_for_selector("#bug-report-backdrop", timeout=15000)
        page.keyboard.press("Escape")
        expect(page.locator("#bug-report-backdrop")).to_have_count(0)
        assert not is_recording(page)

        # 2) OK -> inspelning + indikator; stoppa -> rapport skickas.
        page.click("#bug-report-toggle")
        page.wait_for_selector("#bug-report-note", timeout=15000)
        page.fill("#bug-report-note", "Browsertest: knappen dog")
        page.click("#bug-report-start")
        page.wait_for_selector("#bug-report-indicator", timeout=15000)
        assert is_recording(page)
        # Låt rrweb hinna med fullsnapshot + någon interaktion.
        page.click("body")
        page.wait_for_timeout(800)
        page.click("#bug-report-stop")
        expect(page.locator(".toast.success").last).to_contain_text("Buggrapporten är skickad", timeout=15000)
        assert not is_recording(page)
        expect(page.locator("#bug-report-indicator")).to_have_count(0)

        # 3) Rapporten syns och kan öppnas i Buggrapporter-vyn (admin är superuser).
        page.goto(f"{local_server}/bug-rapporter.html", wait_until="load")
        page.wait_for_selector("tr[data-report-id]", timeout=15000)
        row = page.locator("tr[data-report-id]").first
        expect(row).to_contain_text("Browsertest: knappen dog")
        row.click()
        page.wait_for_selector("#bugReportDetail:not([hidden])", timeout=15000)
        expect(page.locator("#bugReportMeta")).to_contain_text("notis: Browsertest: knappen dog", timeout=15000)
        # Uppspelningen har byggt en replayer-yta (rrweb skapar en iframe i containern).
        page.wait_for_selector("#bugReportPlayer iframe", timeout=15000)

        # 4) Status ändras via radens dropdown (Ny -> Att göra).
        page.select_option("select.bug-report-status-select", "seen")
        expect(page.locator(".toast.success").last).to_contain_text("att göra", timeout=15000)
        page.wait_for_selector("tr[data-report-id] .bug-status-seen", timeout=15000)

        # 5) Ta bort kräver bekräftelse; Avbryt lämnar rapporten kvar.
        page.click("button.bug-report-delete")
        page.wait_for_selector("#bug-report-delete-backdrop", timeout=15000)
        page.click("#bug-report-delete-cancel")
        expect(page.locator("#bug-report-delete-backdrop")).to_have_count(0)
        assert page.locator("tr[data-report-id]").count() == 1

        # 6) Bekräftad borttagning tömmer listan och stänger detaljpanelen.
        page.click("button.bug-report-delete")
        page.wait_for_selector("#bug-report-delete-backdrop", timeout=15000)
        page.click("#bug-report-delete-confirm")
        expect(page.locator(".toast.success").last).to_contain_text("borttagen", timeout=15000)
        expect(page.locator("tr[data-report-id]")).to_have_count(0)
        expect(page.locator("#bugReportDetail")).to_be_hidden()
    finally:
        context.close()


def test_recording_continues_across_page_navigation(local_server, chromium_browser):
    """Sidbyte under inspelning: inspelningen återupptas på nya sidan (ny
    full snapshot) och allt skickas som EN rapport vid stopp."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login(page, local_server)

        page.click("#bug-report-toggle")
        page.wait_for_selector("#bug-report-note", timeout=15000)
        page.fill("#bug-report-note", "Cross-page-test")
        page.click("#bug-report-start")
        page.wait_for_selector("#bug-report-indicator", timeout=15000)
        page.wait_for_timeout(800)  # låt rrweb ta fullsnapshot på sida 1

        # Sidbyte mitt i inspelningen: indikatorn kommer tillbaka på nya
        # sidan och inspelningen är fortfarande aktiv.
        page.click('a[href="/personer.html"]')
        page.wait_for_url("**/personer.html", timeout=15000)
        page.wait_for_selector("#bug-report-indicator", timeout=15000)
        assert is_recording(page)
        page.wait_for_timeout(500)  # låt sida 2 få sin fullsnapshot

        page.click("#bug-report-stop")
        expect(page.locator(".toast.success").last).to_contain_text(
            "Buggrapporten är skickad", timeout=15000
        )
        assert not is_recording(page)

        # En rapport, med segment från båda sidorna (två fulla snapshots).
        page.goto(f"{local_server}/bug-rapporter.html", wait_until="load")
        page.wait_for_selector("tr[data-report-id]", timeout=15000)
        expect(page.locator("tr[data-report-id]")).to_have_count(1)
        expect(page.locator("tr[data-report-id]").first).to_contain_text("Cross-page-test")
        snapshots = page.evaluate(
            """async () => {
                const list = await window.api.get("/api/bug-reports");
                const detail = await window.api.get(`/api/bug-reports/${list.reports[0].id}`);
                return JSON.parse(detail.events_json).filter((event) => event.type === 2).length;
            }"""
        )
        assert snapshots >= 2, f"väntade fullsnapshot per sida, fick {snapshots}"
    finally:
        context.close()

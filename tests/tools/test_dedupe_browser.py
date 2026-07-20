"""Browsertester for verktyget Dubbletter (dubbletter.html + js/dubbletter.js).

Anvandarperspektivet: klistra in varden, tryck pa knappen och se att ratt
rader kommer tillbaka, att sammanfattningen stammer och att en toast bekraftar
vad som hande. Kolumnvalet ska bara dyka upp nar det faktiskt finns flera
kolumner, och verktygsfliken ska ta anvandaren hit fran de andra verktygen.

Verktyget ar helt klientsidigt - inga API-mockar behovs.
"""
import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="module")
def local_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("dedupe-browser")
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


def open_dedupe(page, base_url):
    login(page, base_url)
    page.goto(f"{base_url}/dubbletter.html", wait_until="load")
    page.wait_for_selector("#dedupeInput", timeout=15000)


def test_single_column_paste_removes_duplicates(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_dedupe(page, local_server)

        page.fill("#dedupeInput", "banan\napple\nBANAN\ncitron\n apple ")
        expect(page.locator("#dedupeInputCount")).to_have_text("5 rader")
        # Bara en kolumn -> inget kolumnval visas.
        expect(page.locator("#dedupeColumnsBox")).to_be_hidden()

        page.click("#dedupeRun")

        expect(page.locator("#dedupeResultPanel")).to_be_visible()
        expect(page.locator("#dedupeOutput")).to_have_value("banan\napple\ncitron")
        expect(page.locator("#dedupeSummary")).to_contain_text("3 unika")
        expect(page.locator("#dedupeSummary")).to_contain_text("2 borttagna")
        expect(page.locator(".toast.success").last).to_contain_text("Tog bort 2 dubbletter")

        # Borttagna dubbletter listas med antal forekomster.
        expect(page.locator("#dedupeRemovedBox")).to_be_visible()
        expect(page.locator("#dedupeRemoved")).to_contain_text("banan")
        expect(page.locator("#dedupeRemoved")).to_contain_text("2 ggr")
    finally:
        context.close()


def test_excel_columns_show_column_picker_and_respect_selection(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_dedupe(page, local_server)

        page.fill("#dedupeInput", "A1\tRöd\t10\nA2\tBlå\t20\nA1\tGrön\t99")
        expect(page.locator("#dedupeInputCount")).to_have_text("3 rader, 3 kolumner")
        expect(page.locator("#dedupeColumnsBox")).to_be_visible()
        expect(page.locator("#dedupeColumns input")).to_have_count(3)

        # Hela raden jamfors som default -> alla tre ar unika.
        page.click("#dedupeRun")
        expect(page.locator("#dedupeSummary")).to_contain_text("3 unika")
        expect(page.locator(".toast").last).to_contain_text("Inga dubbletter")

        # Jamfor bara kolumn 1 -> A1 forekommer tva ganger.
        page.click("#dedupeColumnsNone")
        page.check('#dedupeColumns input[data-dedupe-column="0"]')
        page.click("#dedupeRun")
        expect(page.locator("#dedupeOutput")).to_have_value("A1\tRöd\t10\nA2\tBlå\t20")
        expect(page.locator("#dedupeSummary")).to_contain_text("1 borttagna")
    finally:
        context.close()


def test_no_selected_column_is_blocked_with_a_warning(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_dedupe(page, local_server)

        page.fill("#dedupeInput", "A1\tRöd\nA2\tBlå")
        page.click("#dedupeColumnsNone")
        page.click("#dedupeRun")

        expect(page.locator(".toast.warn").last).to_contain_text("minst en kolumn")
        expect(page.locator("#dedupeResultPanel")).to_be_hidden()
    finally:
        context.close()


def test_empty_input_warns_and_clear_resets_the_view(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_dedupe(page, local_server)

        page.click("#dedupeRun")
        expect(page.locator(".toast.warn").last).to_contain_text("Klistra in värden först")
        expect(page.locator("#dedupeResultPanel")).to_be_hidden()

        page.fill("#dedupeInput", "a\na\nb")
        page.click("#dedupeRun")
        expect(page.locator("#dedupeResultPanel")).to_be_visible()

        page.click("#dedupeClear")
        expect(page.locator("#dedupeInput")).to_have_value("")
        expect(page.locator("#dedupeResultPanel")).to_be_hidden()
        expect(page.locator("#dedupeInputCount")).to_have_text("0 rader")
    finally:
        context.close()


def test_tools_tab_navigates_from_another_tool(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login(page, local_server)
        page.goto(f"{local_server}/mcp.html", wait_until="load")
        page.click('.tools-tab[data-tools-tab-view="removeDuplicates"]')
        page.wait_for_url("**/dubbletter.html", timeout=15000)
        page.wait_for_selector("#dedupeInput", timeout=15000)
        expect(page.locator('.tools-tab[data-tools-tab-view="removeDuplicates"]')).to_have_class(
            "tools-tab active"
        )
    finally:
        context.close()

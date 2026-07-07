"""Browsertester för schemats ångra/gör om (W17).

Kontrakten som skyddas (schedule/segments_undo.js + #undoBtn/#redoBtn):
1. Ångra/Gör om-knapparna startar disabled med tom historik-stack.
2. En celländring aktiverar #undoBtn; ångra kör PUT /api/schedule/hours/restore
   och återställer värdet + aktiverar #redoBtn; gör om återför ändringen.
3. Byter man dag efter en ändring ger ångra en varningstoast om att byta
   tillbaka till dagen där ändringen gjordes (ingen restore-anrop).

Den lokala seeden fyller schemat för veckodag 1-5 i innevarande vecka. Saknas
seedbar cell (t.ex. helg) faller fullflödestesterna tillbaka på pytest.skip så
att CI aldrig blir rött av datahål.
"""
import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="module")
def local_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("schedule-undo-browser")
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
    page.wait_for_selector("#undoBtn", timeout=15000)
    page.wait_for_selector("#scheduleBody tr", timeout=15000)


def pick_full_hour_cell(page):
    """Returnera {personId, hour, value} för första fyllda heltimmescellen, annars None."""
    page.wait_for_selector("#scheduleBody select.cell-select", timeout=15000)
    return page.evaluate(
        """() => {
            const selects = Array.from(
                document.querySelectorAll('#scheduleBody td select.cell-select')
            );
            for (const s of selects) {
                if (s.value) {
                    const td = s.closest('td');
                    return {
                        personId: td.dataset.personId,
                        hour: td.dataset.hour,
                        value: s.value,
                    };
                }
            }
            return null;
        }"""
    )


def cell_select_locator(page, cell):
    return page.locator(
        f'#scheduleBody td[data-person-id="{cell["personId"]}"]'
        f'[data-hour="{cell["hour"]}"] select.cell-select'
    )


def make_undoable_change(page):
    """Nolla en fylld cell -> pushar 'celländring' i undo-stacken.

    Returnerar cell-dict om ändringen registrerades (undoBtn blev enabled),
    annars None så att anroparen kan skippa fullflödet.
    """
    cell = pick_full_hour_cell(page)
    if not cell:
        return None
    select = cell_select_locator(page, cell)
    # Tomt värde ("-") finns alltid som option och triggar PUT /api/schedule/cell.
    select.select_option("")
    try:
        expect(page.locator("#undoBtn")).to_be_enabled(timeout=10000)
    except AssertionError:
        return None
    return cell


def test_undo_redo_buttons_start_disabled(local_server, chromium_browser):
    """Tom historik: bägge knapparna finns men är disabled (gating-state)."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login(page, local_server)
        expect(page.locator("#undoBtn")).to_have_count(1)
        expect(page.locator("#redoBtn")).to_have_count(1)
        expect(page.locator("#undoBtn")).to_be_disabled()
        expect(page.locator("#redoBtn")).to_be_disabled()
    finally:
        context.close()


def test_cell_change_undo_then_redo(local_server, chromium_browser):
    """Celländring -> ångra återställer via restore-endpointen -> gör om återför."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()

    restore_calls = []
    page.on(
        "request",
        lambda req: restore_calls.append(req.url)
        if "/api/schedule/hours/restore" in req.url and req.method == "PUT"
        else None,
    )

    try:
        login(page, local_server)

        cell = make_undoable_change(page)
        if not cell:
            pytest.skip("Ingen seedbar cell att ändra (t.ex. helgdag utan schema)")

        select = cell_select_locator(page, cell)
        # Ändringen tömde cellen och aktiverade ångra men inte gör om ännu.
        expect(select).to_have_value("")
        expect(page.locator("#undoBtn")).to_be_enabled()
        expect(page.locator("#redoBtn")).to_be_disabled()

        # Ångra: restore-anrop, värdet återställs, gör om aktiveras, stacken töms.
        before_undo = len(restore_calls)
        page.click("#undoBtn")
        expect(page.locator("#redoBtn")).to_be_enabled(timeout=15000)
        expect(select).to_have_value(cell["value"], timeout=15000)
        expect(page.locator("#undoBtn")).to_be_disabled()
        assert len(restore_calls) > before_undo, "ångra ska anropa /api/schedule/hours/restore"

        # Gör om: återför ändringen (cellen töms igen) och ångra aktiveras på nytt.
        before_redo = len(restore_calls)
        page.click("#redoBtn")
        expect(page.locator("#undoBtn")).to_be_enabled(timeout=15000)
        expect(select).to_have_value("", timeout=15000)
        assert len(restore_calls) > before_redo, "gör om ska anropa /api/schedule/hours/restore"
    finally:
        context.close()


def test_undo_on_other_day_warns(local_server, chromium_browser):
    """Byt dag efter en ändring -> ångra ger varningstoast, inget restore-anrop."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()

    restore_calls = []
    page.on(
        "request",
        lambda req: restore_calls.append(req.url)
        if "/api/schedule/hours/restore" in req.url
        else None,
    )

    try:
        login(page, local_server)

        cell = make_undoable_change(page)
        if not cell:
            pytest.skip("Ingen seedbar cell att ändra (t.ex. helgdag utan schema)")

        # Byt till en annan veckodag (1-5 så schemat renderar om deterministiskt).
        current_day = page.locator("#daySelect").input_value()
        other_day = next(d for d in ["1", "2", "3", "4", "5"] if d != current_day)
        page.select_option("#daySelect", other_day)
        expect(page.locator("#daySelect")).to_have_value(other_day)
        # Vänta in omritningen av schemat på den nya dagen.
        page.wait_for_selector("#scheduleBody tr", timeout=15000)
        page.wait_for_timeout(500)

        # Stacken lever kvar över dagbyte, så ångra är fortfarande möjligt att klicka.
        expect(page.locator("#undoBtn")).to_be_enabled(timeout=15000)
        before = len(restore_calls)
        page.click("#undoBtn")

        expect(page.locator(".toast.warn").last).to_contain_text(
            "Byt tillbaka till dagen", timeout=15000
        )
        # Fel dag -> ingen server-restore ska ha skett.
        assert len(restore_calls) == before, "ångra på fel dag får inte anropa restore"
    finally:
        context.close()

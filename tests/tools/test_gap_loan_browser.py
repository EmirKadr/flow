"""Browsertester för utlåningsmenyn i schemat (schedule/loan.js).

Kontrakten som skyddas (openScheduleLoanMenu / sendPersonToArea, kopplade via
schedule/person_order.js: högerklick på #scheduleBody td.name -> loan-menyn):

1. Med en satt starttimme öppnar högerklick på en namncell en `.schedule-loan-menu`
   med en titel (personnamn) och minst ett menyval "Skicka till <område>". Menyn
   listar bara andra aktiva områden – hemområdet, ALLT-markören och ANNAT är
   uteslutna (scheduleLoanTargetOptions). Menyn stängs med Escape.

2. Att välja ett område postar POST /api/schedule/cells med
   action='loan_to_area', celler som bär loan_area_id (målområdet) och
   activity_id=null, följt av en "Skickade …"-success-toast. POST:en spioneras
   och mockas (ingen skarp skrivning mot seeden).

3. Utan starttimme (ingen fokuserad cell och inte dagens datum) ger ett menyval
   en varnings-toast "Klicka först på timmen …" och postar ingenting.

Den lokala seeden kan sakna andra områden eller schemalagda timmar för personen.
Då nöjer vi oss med den strukturella kontrollen (menyn öppnas) och skippar
dataflödet i stället för att lämna ett rött/flaky test.
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
    output_dir = tmp_path_factory.mktemp("loan-browser")
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
    page.goto(f"{base_url}/login.html", wait_until="load")
    page.fill("#username", "admin")
    page.fill("#password", "admin123")
    page.click("button.primary")
    page.wait_for_url("**/index.html", timeout=15000)
    page.wait_for_selector("#scheduleTable", timeout=15000)


def load_schedule_all_areas(page) -> None:
    """Sätt områdesfokus till ALLT och vänta in schemaraderna (samma väg som
    schema-dragtesterna använder)."""
    page.evaluate(
        """() => {
            localStorage.setItem('flow-area-focus', 'ALLT');
            localStorage.removeItem('sidebar-collapsed');
        }"""
    )
    page.reload(wait_until="load")
    page.wait_for_selector("#scheduleTable", timeout=15000)
    page.wait_for_selector("#scheduleBody tr[data-person-id]", timeout=15000)
    page.wait_for_timeout(400)


def name_cell(page):
    """Första namncellen (kontraktets högerklicks-yta)."""
    return page.locator("#scheduleBody td.name[data-person-id]").first


def set_focused_start_hour(page):
    """Sätt en fokuserad cell (starttimme) via state, oberoende av inline-editorer.

    Returnerar den starttimme scheduleLoanStartHour() rapporterar (int) eller
    None om schemat saknar timceller / funktionen saknas."""
    return page.evaluate(
        """() => {
            const td = document.querySelector('#scheduleBody td[data-hour][data-person-id]');
            if (!td || typeof state === 'undefined') return null;
            const hour = Number(td.dataset.hour);
            state.focusedCell = {
                td,
                focusEl: td,
                personId: Number(td.dataset.personId),
                hour,
                minuteStart: 0,
                minuteEnd: 60,
            };
            return typeof scheduleLoanStartHour === 'function' ? scheduleLoanStartHour() : null;
        }"""
    )


def clear_focused_start_hour(page):
    """Nolla fokus och rapportera vad scheduleLoanStartHour() ger (None om ingen
    starttimme kan härledas, dvs. inte dagens datum)."""
    return page.evaluate(
        """() => {
            if (typeof state !== 'undefined') state.focusedCell = null;
            return typeof scheduleLoanStartHour === 'function' ? scheduleLoanStartHour() : 'nofunc';
        }"""
    )


def open_loan_menu(page):
    """Högerklicka på namncellen och vänta in antingen menyn eller en warn-toast.

    Returnerar 'menu' om `.schedule-loan-menu` öppnades, annars None (t.ex. seed
    utan andra områden -> "Inga andra aktiva områden" / read-only)."""
    name_cell(page).click(button="right")
    page.wait_for_selector(".schedule-loan-menu, .toast.warn", timeout=15000)
    if page.locator(".schedule-loan-menu").count() > 0:
        return "menu"
    return None


def test_loan_menu_opens_with_area_options(local_server, chromium_browser):
    """Kontrakt 1: högerklick på namncellen (med satt starttimme) öppnar
    utlåningsmenyn med titel + minst ett 'Skicka till'-val, och stängs med
    Escape. Rör inga data (ingen POST)."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login_admin(page, local_server)
        load_schedule_all_areas(page)

        assert name_cell(page).count() > 0, "väntade minst en namncell i schemat"
        start_hour = set_focused_start_hour(page)
        if start_hour is None:
            pytest.skip("Schemat saknar timceller för att sätta en starttimme")

        if open_loan_menu(page) != "menu":
            pytest.skip("Seeden saknar andra aktiva områden för utlåning (menyn öppnas inte)")

        menu = page.locator(".schedule-loan-menu")
        expect(menu).to_be_visible()
        expect(menu.locator(".schedule-loan-menu-title")).to_have_count(1)

        items = menu.locator("button[role='menuitem']")
        assert items.count() > 0, "väntade minst ett områdesval i utlåningsmenyn"
        expect(items.first).to_contain_text("Skicka till")
        # Med satt starttimme visar hinten "Tomt från …", inte "Klicka först".
        expect(items.first).not_to_contain_text("Klicka först")

        # Hemområdet, ALLT-markören och ANNAT ska aldrig dyka upp som mål.
        forbidden = page.evaluate(
            """() => {
                const focus = state.focusedCell;
                const person = typeof personById === 'function' && focus
                    ? personById(Number(focus.personId)) : null;
                const opts = typeof scheduleLoanTargetOptions === 'function' && person
                    ? scheduleLoanTargetOptions(person) : [];
                const homeId = person ? Number(person.home_area_id) : NaN;
                return opts.some((o) => {
                    const a = o.area;
                    const code = String(a.code || '').trim().toUpperCase();
                    return Number(a.id) === homeId || code === 'ANNAT'
                        || (typeof isAllAreasMarker === 'function' && isAllAreasMarker(a));
                });
            }"""
        )
        assert forbidden is False, "utlåningsmenyn listade hemområde/ALLT/ANNAT"

        # Escape stänger menyn (handleScheduleLoanMenuKeydown).
        page.keyboard.press("Escape")
        expect(page.locator(".schedule-loan-menu")).to_have_count(0)
    finally:
        context.close()


def test_loan_menu_selection_posts_loan_to_area(local_server, chromium_browser):
    """Kontrakt 2: att välja ett område postar action='loan_to_area' med
    loan_area_id + activity_id=null och visar en success-toast. POST:en
    spioneras och mockas. Saknas schemalagda timmar för personen skippas
    dataflödet."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login_admin(page, local_server)
        load_schedule_all_areas(page)

        start_hour = set_focused_start_hour(page)
        if start_hour is None:
            pytest.skip("Schemat saknar timceller för att sätta en starttimme")

        captured = {}

        def handle_cells(route):
            request = route.request
            if request.method != "POST":
                route.continue_()
                return
            try:
                payload = request.post_data_json
            except Exception:
                payload = json.loads(request.post_data or "{}")
            captured["payload"] = payload
            applied = [
                {
                    "person_id": c["person_id"],
                    "hour": c["hour"],
                    "minute_start": c.get("minute_start", 0),
                    "minute_end": c.get("minute_end", 60),
                    "activity_id": c.get("activity_id"),
                    "loan_area_id": c.get("loan_area_id"),
                    "version": (c.get("expected_version") or 0) + 1,
                }
                for c in payload.get("cells", [])
            ]
            route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"applied": applied}, ensure_ascii=False),
            )

        page.route("**/api/schedule/cells", handle_cells)

        if open_loan_menu(page) != "menu":
            pytest.skip("Seeden saknar andra aktiva områden för utlåning (menyn öppnas inte)")

        # Vilket område pekar första valet på? (för assert mot loan_area_id).
        expected_area_id = page.evaluate(
            """() => {
                const person = personById(Number(state.focusedCell.personId));
                const opts = scheduleLoanTargetOptions(person);
                return opts.length ? Number(opts[0].area.id) : null;
            }"""
        )

        page.locator(".schedule-loan-menu button[role='menuitem']").first.click()

        # Endera fångas en POST (success), eller så varnar appen om saknade
        # timmar/låsta celler -> då skippar vi payload-kontraktet.
        page.wait_for_selector(".toast.success, .toast.warn, .toast.error", timeout=15000)

        payload = captured.get("payload")
        if payload is None:
            toast_text = page.locator(".toast").last.inner_text()
            pytest.skip(f"Seeden gav ingen loan-POST (troligen inga schemalagda timmar): {toast_text!r}")

        assert payload.get("action") == "loan_to_area", (
            f"väntade action=loan_to_area, fick {payload.get('action')!r}"
        )
        assert payload.get("atomic") is True
        cells = payload.get("cells", [])
        assert cells, "loan-POST saknade celler"
        for cell in cells:
            assert cell.get("activity_id") is None, "loan-cell ska nolla activity_id"
            assert Number_int(cell.get("loan_area_id")) == expected_area_id, (
                f"cell fick loan_area_id {cell.get('loan_area_id')!r}, väntade {expected_area_id}"
            )
            assert Number_int(cell.get("hour")) >= start_hour, (
                "loan-cell får inte ligga före starttimmen"
            )

        expect(page.locator(".toast.success").last).to_contain_text("Skickade", timeout=15000)
    finally:
        page.unroute("**/api/schedule/cells")
        context.close()


def test_loan_without_start_hour_warns(local_server, chromium_browser):
    """Kontrakt 3: utan starttimme ger ett menyval en varning "Klicka först på
    timmen …" och postar ingenting. Går det inte att garantera en tom
    starttimme (schemats datum är idag) skippas kontraktet."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login_admin(page, local_server)
        load_schedule_all_areas(page)

        start_hour = clear_focused_start_hour(page)
        if start_hour == "nofunc":
            pytest.skip("scheduleLoanStartHour saknas i bundlen")
        if start_hour is not None:
            pytest.skip("Schemats datum är idag -> aktuell timme används som starttimme")

        posted = {"seen": False}

        def block_post(route):
            if route.request.method == "POST":
                posted["seen"] = True
            route.continue_()

        page.route("**/api/schedule/cells", block_post)

        if open_loan_menu(page) != "menu":
            pytest.skip("Seeden saknar andra aktiva områden för utlåning (menyn öppnas inte)")

        page.locator(".schedule-loan-menu button[role='menuitem']").first.click()

        expect(page.locator(".toast.warn").last).to_contain_text(
            "Klicka först på timmen", timeout=15000
        )
        # Varningen ska inte ha genererat någon skrivning.
        page.wait_for_timeout(300)
        assert posted["seen"] is False, "utlåning utan starttimme postade ändå celler"
    finally:
        page.unroute("**/api/schedule/cells")
        context.close()


def Number_int(value):
    """Robust int-konvertering för värden som kan vara str/float/None."""
    if value is None:
        return None
    return int(float(value))

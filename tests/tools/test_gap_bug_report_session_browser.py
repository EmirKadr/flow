"""Browsertester för buggrapportens sessionskontinuitet över sidbyten (W24).

Skyddar kontrakten i common/bug_report.js (resumeStoredSession ~294,
takeStoredSession ~265, SESSION_MAX_AGE_MS) och sidebar.js
(initBugReportButton eager-load när en session väntar):

(a) En pågående inspelning överlever ett sidbyte: indikatorn/nedräkningen
    kommer tillbaka på nya sidan och isRecording() är fortfarande true.
(b) En session vars deadline redan passerat återupptar INTE inspelningen —
    den skickas som EXAKT en rapport (POST /api/bug-reports) och ingen ny
    inspelning startar.
(c) En övergiven session (savedAt äldre än SESSION_MAX_AGE_MS) skickas inte
    alls: ingen POST, och sessionsnyckeln städas bort.

Modellerad på tests/tools/test_bug_report_browser.py (local_server- och
chromium_browser-fixturerna, admin/admin123). Kontrollerna är avsiktligt
strukturella (route-spionering, gating-states) snarare än fulla dataflöden,
så testet är robust även om den lokala seeden saknar innehåll.
"""
import json

import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


SESSION_KEY = "flow-bug-report-session"
BUG_REPORTS_GLOB = "**/api/bug-reports"


@pytest.fixture(scope="module")
def local_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("bug-report-session-browser")
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
    return bool(
        page.evaluate(
            "() => Boolean(window.flowBugReport && window.flowBugReport.isRecording())"
        )
    )


def spy_on_bug_report_posts(page):
    """Räknar POST /api/bug-reports och svarar 200 så api.post resolvar.

    Returnerar en lista som fylls på (en post per fångad POST). Räkningen sker
    på request, oberoende av svaret, så antalet är korrekt även om svaret
    ignoreras av klienten.
    """
    posts = []

    def handler(route):
        request = route.request
        if request.method == "POST":
            posts.append(request.url)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"id": 1, "status": "new"}),
            )
            return
        route.continue_()

    page.route(BUG_REPORTS_GLOB, handler)
    return posts


def inject_session(page, *, saved_at_ms, deadline_ms, page_path="/index.html"):
    """Skriver en inspelningssession direkt i sessionStorage (som pagehide
    skulle ha gjort), med en icke-tom segmentlista så combinedEvents() har
    något att skicka."""
    session = {
        "savedAt": saved_at_ms,
        "deadline": deadline_ms,
        "note": "W24 session-continuity",
        "viewId": None,
        "pagePath": page_path,
        "segments": [[{"type": 2, "data": {}, "timestamp": saved_at_ms}]],
        "consoleErrors": [],
        "jsErrors": [],
    }
    page.evaluate(
        "([key, value]) => sessionStorage.setItem(key, value)",
        [SESSION_KEY, json.dumps(session)],
    )


def wait_until(page, predicate, *, timeout_ms=10000, step_ms=100):
    waited = 0
    while waited < timeout_ms:
        if predicate():
            return True
        page.wait_for_timeout(step_ms)
        waited += step_ms
    return predicate()


def test_active_recording_survives_navigation(local_server, chromium_browser):
    """(a) Eager-resume: en pågående inspelning fortsätter efter sidbyte till
    /personer.html — indikatorn kommer tillbaka och isRecording() är true."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login(page, local_server)

        page.click("#bug-report-toggle")
        page.wait_for_selector("#bug-report-note", timeout=15000)
        page.fill("#bug-report-note", "W24 eager-resume")
        page.click("#bug-report-start")
        page.wait_for_selector("#bug-report-indicator", timeout=15000)
        assert is_recording(page)
        page.wait_for_timeout(600)  # låt rrweb ta fullsnapshot på sida 1

        page.click('a[href="/personer.html"]')
        page.wait_for_url("**/personer.html", timeout=15000)

        # Eager-resume: sidebar.js laddar modulen igen och inspelningen
        # återupptas med en ny full snapshot -> indikator + isRecording().
        page.wait_for_selector("#bug-report-indicator", timeout=15000)
        expect(page.locator("#bug-report-countdown")).to_contain_text(
            "Spelar in bugg", timeout=15000
        )
        assert wait_until(page, lambda: is_recording(page), timeout_ms=15000)
    finally:
        context.close()


def test_expired_deadline_flushes_exactly_one_report(local_server, chromium_browser):
    """(b) En session vars deadline passerat skickas som EXAKT en rapport och
    startar ingen ny inspelning."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login(page, local_server)
        posts = spy_on_bug_report_posts(page)

        now_ms = page.evaluate("() => Date.now()")
        # Deadline i det förflutna, men savedAt färskt (inom SESSION_MAX_AGE_MS)
        # så sessionen inte förkastas som övergiven.
        inject_session(page, saved_at_ms=now_ms, deadline_ms=now_ms - 1000)

        page.goto(f"{local_server}/personer.html", wait_until="load")
        page.wait_for_selector("#bug-report-toggle", timeout=15000)
        # sidebar.js eager-laddar modulen eftersom en session väntar.
        assert wait_until(
            page,
            lambda: page.evaluate("() => Boolean(window.flowBugReport)"),
            timeout_ms=15000,
        ), "bug_report.js eager-laddades inte trots väntande session"

        # Exakt EN rapport skickas (route-spionerad POST).
        assert wait_until(page, lambda: len(posts) >= 1, timeout_ms=15000), (
            "väntade en POST /api/bug-reports från den förfallna sessionen"
        )
        page.wait_for_timeout(500)  # fånga ev. en oönskad andra POST
        assert len(posts) == 1, f"väntade exakt en rapport, fick {len(posts)}"

        # Ingen ny inspelning: deadline var passerad -> ingen re-record.
        assert not is_recording(page)
        assert page.locator("#bug-report-indicator").count() == 0
        # Sessionen är konsumerad och borttagen.
        assert page.evaluate(
            "(key) => sessionStorage.getItem(key)", SESSION_KEY
        ) is None
    finally:
        context.close()


def test_abandoned_session_is_discarded_without_post(local_server, chromium_browser):
    """(c) En session äldre än SESSION_MAX_AGE_MS (savedAt = now-6min)
    förkastas: ingen POST och nyckeln städas bort."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login(page, local_server)
        posts = spy_on_bug_report_posts(page)

        now_ms = page.evaluate("() => Date.now()")
        six_min_ms = 6 * 60 * 1000
        # savedAt äldre än 5 min -> takeStoredSession förkastar (men tar bort
        # nyckeln först). deadline i framtiden för att visa att åldern gatar.
        inject_session(
            page,
            saved_at_ms=now_ms - six_min_ms,
            deadline_ms=now_ms + 60 * 1000,
        )

        page.goto(f"{local_server}/personer.html", wait_until="load")
        page.wait_for_selector("#bug-report-toggle", timeout=15000)
        assert wait_until(
            page,
            lambda: page.evaluate("() => Boolean(window.flowBugReport)"),
            timeout_ms=15000,
        ), "bug_report.js eager-laddades inte trots väntande session"

        # Nyckeln tas alltid bort av takeStoredSession, även när den förkastas.
        assert wait_until(
            page,
            lambda: page.evaluate("(key) => sessionStorage.getItem(key)", SESSION_KEY)
            is None,
            timeout_ms=15000,
        ), "den övergivna sessionsnyckeln städades inte bort"

        # Ge en förfallen session gott om tid att (felaktigt) posta.
        page.wait_for_timeout(800)
        assert len(posts) == 0, f"övergiven session skickades: {len(posts)} POST"
        assert not is_recording(page)
        assert page.locator("#bug-report-indicator").count() == 0
    finally:
        context.close()

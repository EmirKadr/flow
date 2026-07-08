"""Browsertester for Sankey - Inbound-filtren (nattpass W22, 2026-07-07).

Kontrakten som skyddas (strukturellt/route-spionering, ingen seed kravs):
1. Periodknapp -> .active och nasta GET mot /api/sankey/inbound bar period + datum.
2. Nasta-datum-knappen flyttar datumfaltet exakt ett steg.
3. "Visa endast forverkade" -> aria-pressed=true och rendering UTAN ny GET.
4. Bolagsvaljaren fylls fran payloadens business.company_codes.

/api/sankey/inbound mockas via page.route. Sidan foredrar EventSource-strom
(/api/sankey/inbound/stream) och faller tillbaka pa en vanlig GET nar strommen
inte gar att etablera - darfor abortar vi stromroutet sa GET-vagen alltid tas.
"""
import datetime as _dt
import json
import re

import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


STREAM_RE = re.compile(r"/api/sankey/inbound/stream")
GET_RE = re.compile(r"/api/sankey/inbound\?")
COMPANY_CODES = ["ABC", "DEF"]


@pytest.fixture(scope="module")
def local_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("gap-sankey-browser")
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


def _query(url):
    tail = url.split("?", 1)[1] if "?" in url else ""
    out = {}
    for part in tail.split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        out[key] = value
    return out


def _build_payload(period, date, company, only_consumed):
    """Speglar tillbaka begart urval sa klientens 'matchar-mitt-state'-logik
    kan rendera lokalt (period/start_date/company/only_consumed maste stamma)."""
    nodes = [
        {"id": "s1", "stage": 0, "label": "Kalla", "value": 1000, "company": "ABC", "type": "source", "labels": 20},
        {"id": "p1", "stage": 1, "label": "Mottagning", "value": 600, "revenue": 600,
         "company": "ABC", "type": "RECEIVING", "labels": 12, "points": 6},
        {"id": "t1", "stage": 2, "label": "Terminal", "value": 400, "company": "ABC", "type": "terminal", "labels": 8},
    ]
    links = [
        {"source": "s1", "target": "p1", "value": 600, "company": "ABC", "labels": 12},
        {"source": "p1", "target": "t1", "value": 400, "company": "ABC", "labels": 8},
    ]
    summary = {
        "gross_income": 1000, "inbound_income": 800, "outbound_income": 200,
        "gross_income_labels": 500, "gross_income_purchase_lines": 500,
        "labels_received": 20, "purchase_lines_received": 10,
        "outbound_picked_orders": 5, "branches": 2, "unallocated_revenue": 0,
    }
    return {
        "currency": "SEK",
        "period": {"type": period, "start_date": date, "end_date": date,
                   "label": period.upper(), "follow_until": date},
        "filters": {"company": company or "ALL", "only_consumed": bool(only_consumed)},
        "business": {"company_codes": list(COMPANY_CODES)},
        "companies": [],
        "summary": summary,
        "nodes": nodes,
        "links": links,
        "processes": [],
        "outbound_metrics": [],
        "warnings": [],
        # Ger klienten en lokal only_consumed-variant sa toggeln slipper natet.
        "client_filters": {
            "all": {"summary": summary},
            "only_consumed": {"summary": summary},
            "views": {},
        },
        "cache": {"status": "miss"},
        "timing": {"fetch_ms": 4, "build_ms": 3},
    }


def _install_routes(page):
    """Abortar SSE-strommen och mockar GET:en. Returnerar listan med GET-urler."""
    get_urls = []

    def on_request(request):
        url = request.url
        if "/api/sankey/inbound?" in url:
            get_urls.append(url)

    def handle_get(route, request):
        q = _query(request.url)
        payload = _build_payload(
            q.get("period", "day"),
            q.get("date", ""),
            q.get("company", "ALL"),
            q.get("only_consumed", "") == "true",
        )
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.on("request", on_request)
    page.route(STREAM_RE, lambda route: route.abort())
    page.route(GET_RE, handle_get)
    return get_urls


def _login(page, base_url):
    page.goto(f"{base_url}/login.html", wait_until="load")
    page.fill("#username", "admin")
    page.fill("#password", "admin123")
    page.click("button.primary")
    page.wait_for_url("**/index.html", timeout=15000)


def _open_sankey(context, base_url):
    page = context.new_page()
    get_urls = _install_routes(page)
    _login(page, base_url)
    page.goto(f"{base_url}/sankey-inbound.html", wait_until="load")
    # Initial laddning gar via strom-abort -> fallback-GET -> rendering.
    page.wait_for_selector("#sankeyInboundChart .sankey-inbound-svg", timeout=20000)
    return page, get_urls


def test_period_button_activates_and_refetches(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    try:
        page, get_urls = _open_sankey(context, local_server)
        # Initial GET (period=day) ska ha skett.
        assert get_urls, "forvantade en initial GET mot /api/sankey/inbound"
        assert "period=day" in get_urls[0]

        week = page.locator('[data-sankey-period="week"]')
        day = page.locator('[data-sankey-period="day"]')

        # Byte till vecka ska trigga en ny GET som bar period=week + ett datum.
        with page.expect_request(
            lambda r: "/api/sankey/inbound?" in r.url and "period=week" in r.url,
            timeout=15000,
        ) as req_info:
            week.click()
        req = req_info.value
        assert "period=week" in req.url
        q = _query(req.url)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", q.get("date", "")), q.get("date")

        # Vecka blev aktiv, dag tappade aktiv.
        expect(week).to_have_class(re.compile(r"\bactive\b"))
        expect(day).not_to_have_class(re.compile(r"\bactive\b"))
    finally:
        context.close()


def test_next_date_shifts_one_step(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    try:
        page, _ = _open_sankey(context, local_server)
        date_input = page.locator("#sankeyInboundDate")
        before = date_input.input_value()
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", before), before

        page.click("#sankeyInboundNextDate")
        # Datumfaltet ska ha flyttat exakt ett dygn (dag ar default-perioden).
        expect(date_input).not_to_have_value(before)
        after = date_input.input_value()
        d_before = _dt.date.fromisoformat(before)
        d_after = _dt.date.fromisoformat(after)
        assert (d_after - d_before).days == 1, f"{before} -> {after}"
    finally:
        context.close()


def test_only_consumed_toggles_without_new_get(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    try:
        page, get_urls = _open_sankey(context, local_server)
        toggle = page.locator("#sankeyInboundOnlyConsumed")
        expect(toggle).to_have_attribute("aria-pressed", "false")

        gets_before = len(get_urls)
        toggle.click()

        # Kontraktet: forverkad-filtret renderas lokalt utan ny hamtning.
        expect(toggle).to_have_attribute("aria-pressed", "true")
        page.wait_for_timeout(700)
        assert len(get_urls) == gets_before, (
            f"forverkad-toggeln ska rendera lokalt, men {len(get_urls) - gets_before} "
            "ny(a) GET skickades"
        )
        # Diagrammet ligger kvar renderat.
        expect(page.locator("#sankeyInboundChart .sankey-inbound-svg").first).to_be_visible()
    finally:
        context.close()


def test_company_select_populated_from_company_codes(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    try:
        page, _ = _open_sankey(context, local_server)
        select = page.locator("#sankeyInboundCompany")
        # ALL finns alltid + en per company_code fran payloaden.
        expect(select.locator('option[value="ALL"]')).to_have_count(1)
        for code in COMPANY_CODES:
            expect(select.locator(f'option[value="{code}"]')).to_have_count(1)
        values = page.eval_on_selector(
            "#sankeyInboundCompany",
            "el => Array.from(el.options).map(o => o.value)",
        )
        assert values[:1] == ["ALL"]
        for code in COMPANY_CODES:
            assert code in values
    finally:
        context.close()

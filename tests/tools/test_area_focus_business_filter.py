"""Fokusfiltrets verksamhetsdimension (Emirs regel 2026-07-07):

- Verksamhet vald + områden ∞  -> bara den verksamheten syns (business_id).
- Alla verksamheter + områden ∞ -> allt syns (inga filterparametrar).
- Specifikt område valt         -> area_id, verksamheten följer av området.
- Verksamhetsbyte ska alltid trigga omhämtning i vyerna (areaFocusChanged),
  även när områdesfokus står kvar på ∞.

Kör area_focus.js + foundation.js i JS-harnessen (global-script-läge, samma
mönster som test_js_unit_harness.py).
"""
from __future__ import annotations

from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
sync_playwright = playwright_api.sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FOUNDATION_JS = ROOT / "app" / "frontend" / "js" / "common" / "foundation.js"
AREA_FOCUS_JS = ROOT / "app" / "frontend" / "js" / "common" / "area_focus.js"

AREAS = [
    {"id": 1, "code": "A1", "name": "Alfa", "business_id": 1, "is_active": True, "sort_order": 1},
    {"id": 2, "code": "B1", "name": "Beta", "business_id": 2, "is_active": True, "sort_order": 2},
]
BUSINESSES = [
    {"id": 1, "code": "STIGAMO", "name": "Stigamo", "sort_order": 1, "is_active": True},
    {"id": 2, "code": "R3", "name": "R3", "sort_order": 2, "is_active": True},
]


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


@pytest.fixture()
def js_page(chromium_browser):
    page = chromium_browser.new_page()
    # localStorage kräver en riktig origin — data:/about:blank är opaka.
    page.route(
        "**/*",
        lambda route: route.fulfill(status=200, content_type="text/html", body="<html><body></body></html>"),
    )
    page.goto("http://flow-focus-harness.local/")
    page.add_script_tag(content=FOUNDATION_JS.read_text(encoding="utf-8"))
    page.add_script_tag(content=AREA_FOCUS_JS.read_text(encoding="utf-8"))
    yield page
    page.close()


def setup_focus(page, *, super_user: bool, area_focus: str, business_focus: str | None):
    page.evaluate(
        """([areas, businesses, superUser, areaFocus, businessFocus]) => {
            try { localStorage.clear(); } catch (e) {}
            if (businessFocus) {
                try { localStorage.setItem("flow-business-focus", businessFocus); } catch (e) {}
            }
            try { localStorage.setItem("flow-area-focus", areaFocus); } catch (e) {}
            setBusinessFocusBusinesses(businesses);
            setAreaFocusAreas(areas, { is_super_user: superUser });
        }""",
        [AREAS, BUSINESSES, super_user, area_focus, business_focus],
    )


def list_params(page) -> str:
    return page.evaluate("([areas]) => areaFocusListParams(areas).toString()", [AREAS])


def test_business_focus_filters_when_all_areas(js_page):
    setup_focus(js_page, super_user=True, area_focus="ALLT", business_focus="BIZ:1")
    assert list_params(js_page) == "business_id=1"


def test_all_businesses_and_all_areas_shows_everything(js_page):
    setup_focus(js_page, super_user=True, area_focus="ALLT", business_focus="ALLT")
    assert list_params(js_page) == ""


def test_specific_area_wins_over_business_param(js_page):
    setup_focus(js_page, super_user=True, area_focus="AREA:2", business_focus="BIZ:2")
    assert list_params(js_page) == "area_id=2"


def test_non_super_user_never_sends_business_param(js_page):
    setup_focus(js_page, super_user=False, area_focus="AREA:1", business_focus="BIZ:2")
    assert list_params(js_page) == "area_id=1"


def test_matches_area_focus_business_contract(js_page):
    setup_focus(js_page, super_user=True, area_focus="ALLT", business_focus="BIZ:1")
    results = js_page.evaluate(
        """() => [
            matchesAreaFocusBusiness(1),
            matchesAreaFocusBusiness(2),
            matchesAreaFocusBusiness(null),
        ]"""
    )
    assert results == [True, False, True]

    setup_focus(js_page, super_user=True, area_focus="ALLT", business_focus="ALLT")
    assert js_page.evaluate("() => matchesAreaFocusBusiness(2)") is True


def test_business_switch_always_dispatches_area_focus_changed(js_page):
    setup_focus(js_page, super_user=True, area_focus="ALLT", business_focus="BIZ:1")
    events = js_page.evaluate(
        """() => {
            let count = 0;
            window.addEventListener("flow:areaFocusChanged", () => { count += 1; });
            writeBusinessFocus("BIZ:2");   // områdesfokus förblir ∞ — eventet ska ändå skickas
            writeBusinessFocus("ALLT");
            return count;
        }"""
    )
    assert events >= 2

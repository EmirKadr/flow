"""Fokus + Översikt-regression (2026-07-01-buggen).

Scenariot: en Super User står med områdesfokus på ett specifikt område i EN
verksamhet (AREA:2 -> biz 2) och byter sedan verksamhetsfokus till en ANNAN
verksamhet (BIZ:1). Området finns inte längre i den nya verksamheten, så
områdesfokus måste falla tillbaka till ∞ (ALLT) och listornas serverparametrar
byta från area_id=2 till business_id=1 — annars målar vyn kvar data från fel
verksamhet (regressionen). Samtidigt måste Översiktens cache-nyckel och URL
följa med verksamhetsbytet, och områdesfiltret får aldrig mutera serverns rådata.

Kör foundation.js + area_focus.js + overview_state.js i JS-harnessen
(global-script-läge, samma buildlösa mönster som test_js_unit_harness.py).
localStorage kräver riktig origin -> http-route-tricket från
test_area_focus_business_filter.py.
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
OVERVIEW_STATE_JS = ROOT / "app" / "frontend" / "js" / "overview_state.js"

# Två verksamheter, ett område i vardera. AREA:2 hör till biz 2, så ett byte
# till biz 1 måste kasta ut det ur områdesalternativen.
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
    page.goto("http://flow-overview-harness.local/")
    # Ordning: foundation (globaler/konstanter) -> area_focus (fokuslogik) ->
    # overview_state (bygger på areaFocusBusinessId/preferredAreaIdFromFocus).
    page.add_script_tag(content=FOUNDATION_JS.read_text(encoding="utf-8"))
    page.add_script_tag(content=AREA_FOCUS_JS.read_text(encoding="utf-8"))
    page.add_script_tag(content=OVERVIEW_STATE_JS.read_text(encoding="utf-8"))
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


def prime_overview_state(page, *, area_id):
    """Sätter det minimala overviewState som cache-nyckeln/URL:en läser."""
    page.evaluate(
        """([areaId]) => {
            overviewState.currentUser = { id: 42, is_super_user: true, business_id: null };
            overviewState.view = "week";
            overviewState.year = 2026;
            overviewState.week = 28;
            overviewState.month = 7;
            overviewState.areaId = areaId;
        }""",
        [area_id],
    )


# ---------------------------------------------------------------------------
# Kärnregressionen: byte till annan verksamhet slår ut det specifika området,
# områdesfokus faller till ∞ och parametrarna byter från area_id -> business_id.
# ---------------------------------------------------------------------------

def test_business_switch_out_of_area_falls_back_to_all_and_business_param(js_page):
    setup_focus(js_page, super_user=True, area_focus="AREA:2", business_focus="ALLT")

    result = js_page.evaluate(
        """([areas]) => {
            let changed = 0;
            window.addEventListener("flow:areaFocusChanged", () => { changed += 1; });
            const before = readAreaFocus();
            writeBusinessFocus("BIZ:1");   // AREA:2 (biz 2) finns inte i biz 1
            return {
                before,
                after: readAreaFocus(),
                params: areaFocusListParams(areas).toString(),
                changed,
            };
        }""",
        [AREAS],
    )

    assert result["before"] == "AREA:2"
    # Området föll tillbaka till ∞ när det inte längre finns i verksamheten.
    assert result["after"] == "ALLT"
    # Parametern är business_id=1 — INTE area_id=2 (kärnan i 2026-07-01-buggen).
    assert result["params"] == "business_id=1"
    # Vyerna måste få veta att filtreringen ändrats trots att området "bara" blev ∞.
    assert result["changed"] >= 1


# ---------------------------------------------------------------------------
# Översiktens cache-nyckel + URL följer verksamhetsfokus vid ∞-område.
# ---------------------------------------------------------------------------

def test_overview_cache_key_and_url_track_business_focus(js_page):
    setup_focus(js_page, super_user=True, area_focus="ALLT", business_focus="BIZ:1")
    prime_overview_state(js_page, area_id=None)

    first = js_page.evaluate(
        "() => ({ key: overviewCacheKey(), url: overviewUrl() })"
    )
    assert "biz:1" in first["key"]
    assert "business_id=1" in first["url"]
    assert "area_id=" not in first["url"]

    # Byt verksamhet -> både nyckel och URL måste ändras (annars målas fel data).
    second = js_page.evaluate(
        """() => {
            writeBusinessFocus("BIZ:2");
            return { key: overviewCacheKey(), url: overviewUrl() };
        }"""
    )
    assert "biz:2" in second["key"]
    assert "business_id=2" in second["url"]
    assert second["key"] != first["key"]
    assert second["url"] != first["url"]


def test_overview_url_uses_area_id_and_omits_business_when_area_selected(js_page):
    setup_focus(js_page, super_user=True, area_focus="ALLT", business_focus="BIZ:1")
    prime_overview_state(js_page, area_id=5)

    url = js_page.evaluate("() => overviewUrl()")
    # Ett valt område pekar redan ut verksamheten -> area_id, inget business_id.
    assert "area_id=5" in url
    assert "business_id" not in url


# ---------------------------------------------------------------------------
# filterOverviewDataForArea: droppar celler för personer utanför området och
# muterar aldrig serverns rådata (annars förgiftas cachen mellan områdesbyten).
# ---------------------------------------------------------------------------

def test_filter_overview_data_drops_foreign_cells_without_mutating_source(js_page):
    result = js_page.evaluate(
        """() => {
            const data = {
                persons: [
                    { id: 10, name: "Anna", home_area_id: 1 },
                    { id: 20, name: "Bob", home_area_id: 2 },
                ],
                matrix: [
                    { person_id: 10, weekday: 1, activity_id: 5 },
                    { person_id: 20, weekday: 1, activity_id: 6 },
                    { person_id: 10, weekday: 2, activity_id: 7 },
                ],
                days: [{ date: "2026-07-06", weekday: 1 }],
            };
            const snapshot = JSON.stringify(data);
            const filtered = filterOverviewDataForArea(data, 1);
            return {
                personIds: filtered.persons.map((p) => p.id),
                cellPersonIds: filtered.matrix.map((c) => c.person_id),
                sourceUnchanged: JSON.stringify(data) === snapshot,
                distinctPersons: filtered.persons[0] !== data.persons[0],
                distinctCells: filtered.matrix[0] !== data.matrix[0],
            };
        }"""
    )

    # Bara person 10 (område 1) överlever; person 20:s cell droppas.
    assert result["personIds"] == [10]
    assert result["cellPersonIds"] == [10, 10]
    # Ursprungsobjektet är orört (djup-jämförelse via JSON-snapshot).
    assert result["sourceUnchanged"] is True
    # De returnerade posterna är kopior, inte referenser till källan.
    assert result["distinctPersons"] is True
    assert result["distinctCells"] is True


def test_filter_overview_data_null_area_copies_everything(js_page):
    result = js_page.evaluate(
        """() => {
            const data = {
                persons: [{ id: 10, home_area_id: 1 }, { id: 20, home_area_id: 2 }],
                matrix: [{ person_id: 10, weekday: 1 }, { person_id: 20, weekday: 1 }],
                days: [{ date: "2026-07-06" }],
            };
            const snapshot = JSON.stringify(data);
            const filtered = filterOverviewDataForArea(data, null);
            return {
                personCount: filtered.persons.length,
                cellCount: filtered.matrix.length,
                sourceUnchanged: JSON.stringify(data) === snapshot,
                distinct: filtered.persons[0] !== data.persons[0],
            };
        }"""
    )
    # areaId == null -> allt kopieras oförändrat men fortfarande som nya objekt.
    assert result["personCount"] == 2
    assert result["cellCount"] == 2
    assert result["sourceUnchanged"] is True
    assert result["distinct"] is True

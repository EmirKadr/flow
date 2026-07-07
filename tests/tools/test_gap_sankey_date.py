"""JS-enhetstest: sankey_inbound_state.js datum- och nyckelmatematik.

Buildlöst mönster (jfr tests/tools/test_js_unit_harness.py): filen injiceras i
en tom about:blank-sida i global-script-läge och funktionerna anropas direkt
via page.evaluate. Funktionerna är rena funktionsdeklarationer utan externa
beroenden, så ingen ytterligare fil behöver injiceras.

Testade funktioner (bekräftade i app/frontend/js/sankey_inbound_state.js):
  sankeyPeriodStartDate(period, value)  - week -> måndag, month -> dag 1, year -> 01-01
  sankeyShiftDate(value, direction, period) - stega ±1 över årsskiften
  sankeyClientViewKey(period, date, company, onlyConsumed) - "period|start|company|0/1"
  sankeyNormalizeCompany(value) - trim+upper, ''/'all'/null -> 'ALL'
  sankeyDisplayText(value) - lagar mojibake (Ã¥ -> å m.fl.)
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
sync_playwright = playwright_api.sync_playwright

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SANKEY_STATE_JS = ROOT / "app" / "frontend" / "js" / "sankey_inbound_state.js"


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


@pytest.fixture(scope="module")
def sankey_page(chromium_browser):
    page = chromium_browser.new_page()
    page.goto("about:blank")
    page.add_script_tag(content=SANKEY_STATE_JS.read_text(encoding="utf-8"))
    yield page
    page.close()


# ---------------------------------------------------------------------------
# sankeyPeriodStartDate: normalisering av periodens startdatum.
# ---------------------------------------------------------------------------

def test_period_start_date_named_edges(sankey_page):
    """Namngivna kantfall enligt spec: vecka->måndag, månad->dag 1, år->01-01."""
    cases = {
        ("week", "2026-07-08"): "2026-07-06",   # onsdag -> måndagen i veckan
        ("month", "2026-07-08"): "2026-07-01",  # första i månaden
        ("year", "2026-07-08"): "2026-01-01",   # första i året
        ("day", "2026-07-08"): "2026-07-08",    # dag rör sig inte
    }
    for (period, value), expected in cases.items():
        result = sankey_page.evaluate(
            "([p, v]) => sankeyPeriodStartDate(p, v)", [period, value]
        )
        assert result == expected, f"{period}/{value}: {result} != {expected}"


def test_period_start_date_week_matches_python_monday(sankey_page):
    """400 dagar över två årsskiften: veckostart == Pythons måndag (weekday()==0)."""
    start = date(2025, 11, 1)
    days = [start + timedelta(days=offset) for offset in range(400)]
    results = sankey_page.evaluate(
        "(days) => days.map((d) => sankeyPeriodStartDate('week', d))",
        [day.isoformat() for day in days],
    )
    mismatches = []
    for day, js_start in zip(days, results):
        monday = day - timedelta(days=day.weekday())
        if js_start != monday.isoformat():
            mismatches.append(f"{day}: js={js_start} python={monday.isoformat()}")
    assert mismatches == [], mismatches[:10]


def test_period_start_date_week_start_stays_start(sankey_page):
    """Idempotens: en måndag som redan är veckostart flyttas inte."""
    result = sankey_page.evaluate(
        "() => sankeyPeriodStartDate('week', '2026-07-06')"
    )
    assert result == "2026-07-06"


def test_period_start_date_month_and_year_across_boundary(sankey_page):
    """Månad/år-start funkar även på årets sista dag."""
    assert sankey_page.evaluate("() => sankeyPeriodStartDate('month', '2025-12-31')") == "2025-12-01"
    assert sankey_page.evaluate("() => sankeyPeriodStartDate('year', '2025-12-31')") == "2025-01-01"


# ---------------------------------------------------------------------------
# sankeyShiftDate: stega period ±1 över årsskiften.
# ---------------------------------------------------------------------------

def test_shift_date_across_year_boundary(sankey_page):
    """prev/next (direction -1/+1) korsar årsskiftet korrekt per period."""
    cases = [
        ("2026-01-01", -1, "day", "2025-12-31"),
        ("2025-12-31", 1, "day", "2026-01-01"),
        ("2026-01-01", -1, "week", "2025-12-25"),
        ("2025-12-29", 1, "week", "2026-01-05"),
        ("2026-01-15", -1, "month", "2025-12-15"),
        ("2025-12-15", 1, "month", "2026-01-15"),
        ("2026-06-15", -1, "year", "2025-06-15"),
        ("2025-06-15", 1, "year", "2026-06-15"),
    ]
    for value, direction, period, expected in cases:
        result = sankey_page.evaluate(
            "([v, dir, p]) => sankeyShiftDate(v, dir, p)", [value, direction, period]
        )
        assert result == expected, f"{value} {direction:+d} {period}: {result} != {expected}"


def test_shift_date_day_roundtrips_matches_python(sankey_page):
    """Daglig stegning ±1 speglar Pythons timedelta över ett brett spann."""
    start = date(2025, 12, 20)
    days = [start + timedelta(days=offset) for offset in range(30)]
    forward = sankey_page.evaluate(
        "(days) => days.map((d) => sankeyShiftDate(d, 1, 'day'))",
        [day.isoformat() for day in days],
    )
    for day, js_next in zip(days, forward):
        assert js_next == (day + timedelta(days=1)).isoformat(), day


# ---------------------------------------------------------------------------
# sankeyClientViewKey: stabil nyckel "period|start|company|0/1".
# ---------------------------------------------------------------------------

def test_client_view_key_shape_and_normalization(sankey_page):
    """Nyckeln normaliserar period/start/company och kodar onlyConsumed 0/1."""
    key = sankey_page.evaluate(
        "() => sankeyClientViewKey('week', '2026-07-08', '  volvo ', false)"
    )
    assert key == "week|2026-07-06|VOLVO|0"

    key_consumed = sankey_page.evaluate(
        "() => sankeyClientViewKey('week', '2026-07-08', '  volvo ', true)"
    )
    assert key_consumed == "week|2026-07-06|VOLVO|1"


def test_client_view_key_stable_across_equivalent_inputs(sankey_page):
    """Olika men ekvivalenta datum i samma vecka ger identisk nyckel."""
    keys = sankey_page.evaluate(
        """() => ['2026-07-06', '2026-07-08', '2026-07-12'].map(
             (d) => sankeyClientViewKey('WEEK', d, 'all', 0)
           )"""
    )
    assert keys == ["week|2026-07-06|ALL|0"] * 3


# ---------------------------------------------------------------------------
# sankeyNormalizeCompany: trim + upper, tomt/'all'/null -> 'ALL'.
# ---------------------------------------------------------------------------

def test_normalize_company(sankey_page):
    checks = sankey_page.evaluate(
        """() => ({
          padded: sankeyNormalizeCompany('  abc '),
          empty: sankeyNormalizeCompany(''),
          all_lower: sankeyNormalizeCompany('all'),
          all_padded: sankeyNormalizeCompany('  All  '),
          nullish: sankeyNormalizeCompany(null),
          undef: sankeyNormalizeCompany(undefined),
          mixed: sankeyNormalizeCompany(' Volvo '),
        })"""
    )
    assert checks["padded"] == "ABC"
    assert checks["empty"] == "ALL"
    assert checks["all_lower"] == "ALL"
    assert checks["all_padded"] == "ALL"
    assert checks["nullish"] == "ALL"
    assert checks["undef"] == "ALL"
    assert checks["mixed"] == "VOLVO"


# ---------------------------------------------------------------------------
# sankeyDisplayText: reparerar dubbelenkodad UTF-8 (mojibake).
# ---------------------------------------------------------------------------

def test_display_text_fixes_mojibake(sankey_page):
    checks = sankey_page.evaluate(
        """() => ({
          aring: sankeyDisplayText('Ã¥'),
          goteborg: sankeyDisplayText('GÃ¶teborg'),
          malmo: sankeyDisplayText('MalmÃ¶'),
          caps: sankeyDisplayText('Ã…ngest'),
          dash: sankeyDisplayText('a â€“ b'),
          clean: sankeyDisplayText('Stockholm'),
          nullish: sankeyDisplayText(null),
        })"""
    )
    assert checks["aring"] == "å"
    assert checks["goteborg"] == "Göteborg"
    assert checks["malmo"] == "Malmö"
    assert checks["caps"] == "Ångest"
    assert checks["dash"] == "a – b"
    assert checks["clean"] == "Stockholm"
    assert checks["nullish"] == ""

"""JS-enhetstestpilot: ren frontendlogik testad i en Playwright-sida.

Buildlöst mönster: skriptfilen injiceras i en tom sida (global-script-läge,
precis som i produktion) och funktionerna anropas direkt med page.evaluate.
En browserinstans, många asserts - snabbt nog för enhetstestkänsla utan
att ändra frontendarkitekturen.

Pilotmodul: currentIsoWeekParts i demo_prefetch_init.js. ISO-veckologik är
klassisk fällmark (årsskiften, vecka 52/53, söndag=7) och prefetchens
schema-/översikts-URL:er byggs av den — fel vecka betyder att cachen värms
med fel data. Kontraktet verifieras exakt mot Pythons date.isocalendar().
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
sync_playwright = playwright_api.sync_playwright

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO_PREFETCH_JS = ROOT / "app" / "frontend" / "js" / "common" / "demo_prefetch_init.js"


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
def js_page(chromium_browser):
    page = chromium_browser.new_page()
    page.goto("about:blank")
    page.add_script_tag(content=DEMO_PREFETCH_JS.read_text(encoding="utf-8"))
    yield page
    page.close()


def test_current_iso_week_parts_matches_python_isocalendar(js_page):
    """400 dagar från 2024-12-01 täcker två årsskiften inkl. vecka 52->1-
    övergångar; varje dag jämförs exakt mot Pythons isocalendar()."""
    start = date(2024, 12, 1)
    days = [start + timedelta(days=offset) for offset in range(400)]

    results = js_page.evaluate(
        """(dayStrings) => dayStrings.map((day) => {
             const [y, m, d] = day.split("-").map(Number);
             const parts = currentIsoWeekParts(new Date(y, m - 1, d, 12, 0, 0));
             return [parts.year, parts.week, parts.weekday];
           })""",
        [day.isoformat() for day in days],
    )

    mismatches = []
    for day, (js_year, js_week, js_weekday) in zip(days, results):
        iso = day.isocalendar()
        if (js_year, js_week, js_weekday) != (iso.year, iso.week, iso.weekday):
            mismatches.append(
                f"{day}: js=({js_year}, v{js_week}, dag {js_weekday}) "
                f"python=({iso.year}, v{iso.week}, dag {iso.weekday})"
            )
    assert mismatches == [], mismatches[:10]


def test_current_iso_week_parts_week53_and_sunday_edges(js_page):
    """Namngivna kantfall så en regression pekar ut exakt vilken kant som brast."""
    cases = {
        "2020-12-31": (2020, 53, 4),  # år med vecka 53
        "2021-01-01": (2020, 53, 5),  # nyår som tillhör föregående ISO-år
        "2024-12-30": (2025, 1, 1),   # måndag som tillhör nästa ISO-år
        "2026-01-04": (2026, 1, 7),   # söndag = veckodag 7, aldrig 0
        "2026-07-06": (2026, 28, 1),  # dagens release-vecka (2026.28.x)
    }
    for day, expected in cases.items():
        result = js_page.evaluate(
            """(day) => {
                 const [y, m, d] = day.split("-").map(Number);
                 const parts = currentIsoWeekParts(new Date(y, m - 1, d, 12, 0, 0));
                 return [parts.year, parts.week, parts.weekday];
               }""",
            day,
        )
        assert tuple(result) == expected, f"{day}: {result} != {expected}"

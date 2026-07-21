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


# ---------------------------------------------------------------------------
# normalizeAppZoom (theme.js): klampning, stegning och skräptålighet.
# Zoomvärdet skrivs till localStorage och styr hela appens skala — ett
# ogiltigt värde får aldrig ge NaN-zoom. (Nattpass 2026-07-07.)
# ---------------------------------------------------------------------------

THEME_JS = ROOT / "app" / "frontend" / "js" / "common" / "theme.js"


FOUNDATION_JS = ROOT / "app" / "frontend" / "js" / "common" / "foundation.js"


def _app_zoom_constants_prelude() -> str:
    """Plocka APP_ZOOM_*-konstanterna ur foundation.js så testet följer källan."""
    import re as _re

    source = FOUNDATION_JS.read_text(encoding="utf-8")
    lines = _re.findall(r"^const APP_ZOOM_\w+ = .*$", source, _re.M)
    assert len(lines) >= 4, "APP_ZOOM-konstanterna hittades inte i foundation.js"
    return "\n".join(lines)


@pytest.fixture(scope="module")
def theme_page(chromium_browser):
    page = chromium_browser.new_page()
    page.goto("about:blank")
    page.add_script_tag(content=_app_zoom_constants_prelude())
    page.add_script_tag(content=THEME_JS.read_text(encoding="utf-8"))
    yield page
    page.close()


def test_normalize_app_zoom_clamps_steps_and_survives_garbage(theme_page):
    checks = theme_page.evaluate(
        """() => ({
          min: normalizeAppZoom(-500),
          max: normalizeAppZoom(9999),
          step: normalizeAppZoom(101),
          nullish: normalizeAppZoom(null),
          empty: normalizeAppZoom(""),
          garbage: normalizeAppZoom("hejsan"),
          nan: normalizeAppZoom(NaN),
          bounds: [APP_ZOOM_MIN, APP_ZOOM_MAX, APP_ZOOM_STEP, APP_ZOOM_DEFAULT],
        })"""
    )
    zoom_min, zoom_max, zoom_step, zoom_default = checks["bounds"]
    assert checks["min"] == zoom_min
    assert checks["max"] == zoom_max
    assert checks["step"] % zoom_step == 0  # 101 stegas till närmaste steg
    assert checks["nullish"] == zoom_default
    assert checks["empty"] == zoom_default
    assert checks["garbage"] == zoom_default
    assert checks["nan"] == zoom_default
    # Idempotens: ett normaliserat värde ändras inte av en andra normalisering.
    assert theme_page.evaluate(
        "() => [...Array(40)].every((_, i) => { const v = normalizeAppZoom(i * 17 - 100); return normalizeAppZoom(v) === v; })"
    )


# ---------------------------------------------------------------------------
# Tabellsorteringens tokenlogik (table_sort.js): svenska tal (mellanslag +
# decimalkomma) sorterar numeriskt, tomma celler sist, ISO-datum kronologiskt
# och text i svensk teckenordning (å/ä/ö efter z).
# ---------------------------------------------------------------------------

TABLE_SORT_JS = ROOT / "app" / "frontend" / "js" / "common" / "table_sort.js"


@pytest.fixture(scope="module")
def table_sort_page(chromium_browser):
    page = chromium_browser.new_page()
    page.goto("about:blank")
    page.add_script_tag(content=TABLE_SORT_JS.read_text(encoding="utf-8"))
    yield page
    page.close()


def _sort_values(page, values):
    return page.evaluate(
        """(values) => {
          const tokens = values.map((value) => {
            const cell = document.createElement("td");
            cell.textContent = value;
            return { value, token: clientTableSortToken(cell) };
          });
          tokens.sort((a, b) => compareClientTableSortTokens(a.token, b.token));
          return tokens.map((entry) => entry.value);
        }""",
        values,
    )


def test_swedish_numbers_sort_numerically(table_sort_page):
    result = _sort_values(table_sort_page, ["1 000,5", "999,9", "12", "2,25", "-3"])
    assert result == ["-3", "2,25", "12", "999,9", "1 000,5"]


def test_empty_cells_always_sort_last(table_sort_page):
    result = _sort_values(table_sort_page, ["-", "b", "", "a"])
    assert result[-2:] == ["-", ""] or result[-2:] == ["", "-"]
    assert result[:2] == ["a", "b"]


def test_iso_dates_sort_chronologically(table_sort_page):
    result = _sort_values(table_sort_page, ["2026-01-15", "2025-12-31", "2026-01-02"])
    assert result == ["2025-12-31", "2026-01-02", "2026-01-15"]


def test_swedish_text_order_places_aao_after_z(table_sort_page):
    result = _sort_values(table_sort_page, ["Örebro", "Arlöv", "Zinkgruvan", "Åmål", "Ängelholm"])
    assert result == ["Arlöv", "Zinkgruvan", "Åmål", "Ängelholm", "Örebro"]


# ---------------------------------------------------------------------------
# Dedupe-kärnan (dubbletter.js): parsning av inklistrad Excel-text och själva
# dubblettborttagningen. Regelvalen (trim, skiftläge, tomma rader, vilka
# kolumner som jämförs) avgör vad användaren får tillbaka — fel här ger tyst
# dataförlust, därför enhetstestas de i stället för bara via UI:t.
# ---------------------------------------------------------------------------

DEDUPE_JS = ROOT / "app" / "frontend" / "js" / "dubbletter.js"


@pytest.fixture(scope="module")
def dedupe_page(chromium_browser):
    page = chromium_browser.new_page()
    page.goto("about:blank")
    # initDedupePage() körs vid laddning och kan inte nå initPage här; det är
    # en avvisad promise och stoppar inte funktionsdefinitionerna.
    page.add_script_tag(content=DEDUPE_JS.read_text(encoding="utf-8"))
    yield page
    page.close()


def _dedupe(page, text, *, trim=True, ignore_case=True, skip_empty=True, columns=None):
    return page.evaluate(
        """({ text, trim, ignoreCase, skipEmpty, columns }) => {
             const rows = dedupeParseRows(text);
             const width = rows.reduce((max, row) => Math.max(max, row.length), 0);
             const selected = columns || Array.from({ length: width }, () => true);
             const result = dedupeRows(rows, { trim, ignoreCase, skipEmpty, columns: selected });
             return {
               unique: result.unique.map((row) => row.join("\\t")),
               removedCount: result.removedCount,
               skippedEmpty: result.skippedEmpty,
               duplicates: result.duplicates,
             };
           }""",
        {
            "text": text,
            "trim": trim,
            "ignoreCase": ignore_case,
            "skipEmpty": skip_empty,
            "columns": columns,
        },
    )


def test_dedupe_keeps_first_occurrence_and_input_order(dedupe_page):
    result = _dedupe(dedupe_page, "banan\napple\nbanan\ncitron\napple")
    assert result["unique"] == ["banan", "apple", "citron"]
    assert result["removedCount"] == 2


def test_dedupe_parses_windows_and_mac_line_endings(dedupe_page):
    assert _dedupe(dedupe_page, "a\r\nb\r\na")["unique"] == ["a", "b"]
    assert _dedupe(dedupe_page, "a\rb\ra")["unique"] == ["a", "b"]
    # En avslutande radbrytning ska inte bli en extra tom rad.
    assert _dedupe(dedupe_page, "a\nb\n", skip_empty=False)["unique"] == ["a", "b"]


def test_dedupe_trim_and_case_rules_are_independent(dedupe_page):
    text = "  A1\nA1  \na1"
    assert _dedupe(dedupe_page, text)["unique"] == ["  A1"]
    only_trim = _dedupe(dedupe_page, text, ignore_case=False)
    assert only_trim["unique"] == ["  A1", "a1"]
    only_case = _dedupe(dedupe_page, text, trim=False)
    assert only_case["unique"] == ["  A1", "A1  ", "a1"]
    neither = _dedupe(dedupe_page, text, trim=False, ignore_case=False)
    assert neither["unique"] == ["  A1", "A1  ", "a1"]


def test_dedupe_skip_empty_rows(dedupe_page):
    text = "a\n\nb\n   \na"
    skipped = _dedupe(dedupe_page, text)
    assert skipped["unique"] == ["a", "b"]
    assert skipped["skippedEmpty"] == 2
    assert skipped["removedCount"] == 1

    kept = _dedupe(dedupe_page, text, skip_empty=False)
    # Tomraderna blir ett eget värde som i sin tur kan vara en dubblett.
    assert kept["unique"] == ["a", "", "b"]
    assert kept["skippedEmpty"] == 0


def test_dedupe_compares_whole_row_across_columns(dedupe_page):
    text = "A1\tRöd\t10\nA2\tBlå\t20\nA1\tRöd\t10\nA1\tGrön\t10"
    result = _dedupe(dedupe_page, text)
    assert result["unique"] == ["A1\tRöd\t10", "A2\tBlå\t20", "A1\tGrön\t10"]
    assert result["removedCount"] == 1


def test_dedupe_respects_selected_columns_only(dedupe_page):
    text = "A1\tRöd\t10\nA2\tBlå\t20\nA1\tGrön\t99"
    first_column = _dedupe(dedupe_page, text, columns=[True, False, False])
    assert first_column["unique"] == ["A1\tRöd\t10", "A2\tBlå\t20"]
    assert first_column["removedCount"] == 1

    last_column = _dedupe(dedupe_page, text, columns=[False, False, True])
    assert last_column["unique"] == ["A1\tRöd\t10", "A2\tBlå\t20", "A1\tGrön\t99"]


def test_dedupe_ragged_rows_do_not_collide(dedupe_page):
    """En rad med färre celler är inte samma sak som en med tomma celler."""
    result = _dedupe(dedupe_page, "A1\nA1\tRöd", skip_empty=False)
    assert result["unique"] == ["A1", "A1\tRöd"]
    assert result["removedCount"] == 0


def test_dedupe_key_does_not_collide_across_column_boundaries(dedupe_page):
    """En rad med mellanslag är inte samma sak som två celler.

    Med en join-separator i nyckeln blev "a b" och cellerna "a" + "b" samma
    värde och den ena raden försvann tyst.
    """
    result = _dedupe(dedupe_page, "a b\na\tb")
    assert result["unique"] == ["a b", "a\tb"]
    assert result["removedCount"] == 0


def test_dedupe_reports_duplicate_counts(dedupe_page):
    result = _dedupe(dedupe_page, "a\nb\na\na\nb")
    counts = {entry["label"]: entry["count"] for entry in result["duplicates"]}
    assert counts == {"a": 3, "b": 2}
    assert result["removedCount"] == 3

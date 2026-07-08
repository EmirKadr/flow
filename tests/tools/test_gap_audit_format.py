"""JS-enhetstest för audit-formatterarna i analytics.js.

analytics.js är en IIFE. Bara `setHistoryMode` och `submitTrackingChat`
exponeras på window — audit-formatterarna (periodStartIso, objectSummary,
detailSummary, summarizeChanges, formatFieldValue) är inkapslade och går inte
att nå utifrån. Vi testar dem ändå mot den *riktiga källan* genom att injicera
hela filen och programmatiskt lägga till en enda export-rad precis innan den
yttre IIFE:n stängs (samma lexikala scope → closures ser persons/activities/
areas-arrayerna). En liten `initPage`-stub gör att boot-IIFE:n returnerar
tidigt så ingen DOM-åtkomst sker.

Följer det buildlösa harness-mönstret i test_js_unit_harness.py
(page.add_script_tag(content=...) + page.evaluate).
"""
from __future__ import annotations

from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
sync_playwright = playwright_api.sync_playwright

ROOT = Path(__file__).resolve().parents[2]
ANALYTICS_JS = ROOT / "app" / "frontend" / "js" / "analytics.js"

MIDDOT = "·"  # objectSummary för rfid_scan_event separerar med " · "

# Den unika raden precis innan yttre IIFE:n stängs; vi hänger på en export.
_ANCHOR = "window.submitTrackingChat = submitTrackingChat;"
_EXPORT = (
    _ANCHOR
    + "\nwindow.__audit = {"
    + " periodStartIso, objectSummary, detailSummary, summarizeChanges, formatFieldValue,"
    + " setPersons: (v) => { persons = v; },"
    + " setActivities: (v) => { activities = v; },"
    + " setAreas: (v) => { areas = v; } };"
)


def _instrumented_source() -> str:
    source = ANALYTICS_JS.read_text(encoding="utf-8")
    assert source.count(_ANCHOR) == 1, "förankringsraden för export saknas/är inte unik"
    return source.replace(_ANCHOR, _EXPORT)


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
def audit_page(chromium_browser):
    page = chromium_browser.new_page()
    page.goto("about:blank")
    # Stubba initPage så boot-IIFE:n returnerar tidigt (currentUser = null).
    page.add_script_tag(content="window.initPage = async () => null;")
    page.add_script_tag(content=_instrumented_source())
    exposed = page.evaluate("() => typeof window.__audit")
    if exposed != "object":
        pytest.skip(f"__audit exponerades inte (typeof = {exposed})")
    yield page
    page.close()


def _summary(page, entry):
    return page.evaluate("(e) => window.__audit.objectSummary(e)", entry)


def _detail(page, entry):
    return page.evaluate("(e) => window.__audit.detailSummary(e)", entry)


# ---------------------------------------------------------------------------
# periodStartIso: 24h / 7d / 30d ger ISO-tidsstämpel bakåt; okänt/'all' → null.
# ---------------------------------------------------------------------------

def test_period_start_iso_windows_and_all(audit_page):
    res = audit_page.evaluate(
        """() => {
          const A = window.__audit;
          const before = Date.now();
          const r24 = A.periodStartIso("24h");
          const r7 = A.periodStartIso("7d");
          const r30 = A.periodStartIso("30d");
          return {
            d24: before - Date.parse(r24),
            d7: before - Date.parse(r7),
            d30: before - Date.parse(r30),
            iso24: r24,
            all: A.periodStartIso("all"),
            unknown: A.periodStartIso("nonsense"),
            empty: A.periodStartIso(""),
          };
        }"""
    )
    hour = 60 * 60 * 1000
    assert abs(res["d24"] - 24 * hour) <= 2000
    assert abs(res["d7"] - 7 * 24 * hour) <= 2000
    assert abs(res["d30"] - 30 * 24 * hour) <= 2000
    # ISO-8601 UTC-sträng.
    assert res["iso24"].endswith("Z") and "T" in res["iso24"]
    # Allt som inte matchar 24h/7d/30d faller igenom till null.
    assert res["all"] is None
    assert res["unknown"] is None
    assert res["empty"] is None


# ---------------------------------------------------------------------------
# formatFieldValue: null → "-", bool-fält → Ja/Nej, id-fält slår upp namn,
# arrayer joinas, annat blir String(value).
# ---------------------------------------------------------------------------

def test_format_field_value_variants(audit_page):
    res = audit_page.evaluate(
        """() => {
          const A = window.__audit;
          A.setAreas([{ id: 3, name: "Kyl A" }]);
          A.setActivities([{ id: 7, label: "Plock" }]);
          return {
            nullv: A.formatFieldValue("whatever", null),
            undef: A.formatFieldValue("whatever", undefined),
            areaKnown: A.formatFieldValue("area_id", 3),
            homeAreaUnknown: A.formatFieldValue("home_area_id", 99),
            activityKnown: A.formatFieldValue("activity_id", 7),
            summaryActivity: A.formatFieldValue("summary_activity_id", 7),
            boolTrue: A.formatFieldValue("is_active", true),
            boolFalseZero: A.formatFieldValue("is_off", 0),
            emptyOverride: A.formatFieldValue("empty_override", 1),
            arr: A.formatFieldValue("tags", ["a", "b", "c"]),
            arrEmpty: A.formatFieldValue("tags", []),
            plain: A.formatFieldValue("note", 12),
          };
        }"""
    )
    assert res["nullv"] == "-"
    assert res["undef"] == "-"
    assert res["areaKnown"] == "Kyl A"
    assert res["homeAreaUnknown"] == "Område #99"
    assert res["activityKnown"] == "Plock"
    assert res["summaryActivity"] == "Plock"
    assert res["boolTrue"] == "Ja"
    assert res["boolFalseZero"] == "Nej"
    assert res["emptyOverride"] == "Ja"
    assert res["arr"] == "a, b, c"
    assert res["arrEmpty"] == "-"
    assert res["plain"] == "12"


# ---------------------------------------------------------------------------
# summarizeChanges: bara ändrade fält, max 6 nycklar, null/undefined kastar ej.
# ---------------------------------------------------------------------------

def test_summarize_changes_marks_only_changed(audit_page):
    out = audit_page.evaluate(
        """() => window.__audit.summarizeChanges(
             { a: 1, b: 2, c: 3 },
             { a: 1, b: 99, c: 3 }
           )"""
    )
    # Endast b ändrades (a och c oförändrade → uteslutna).
    assert out == "b: 2 -> 99"


def test_summarize_changes_clips_to_six_keys(audit_page):
    segments = audit_page.evaluate(
        """() => {
          const before = {};
          const after = {};
          for (let i = 0; i < 10; i++) { before["k" + i] = i; after["k" + i] = i + 100; }
          return window.__audit.summarizeChanges(before, after).split(" | ");
        }"""
    )
    # 10 ändrade fält men formatteraren klipper till 6.
    assert len(segments) == 6


def test_summarize_changes_empty_and_nullish(audit_page):
    res = audit_page.evaluate(
        """() => {
          const A = window.__audit;
          return {
            same: A.summarizeChanges({ a: 1 }, { a: 1 }),
            bothNull: A.summarizeChanges(null, null),
            undefArgs: A.summarizeChanges(undefined, undefined),
            nullFieldValues: A.summarizeChanges({ x: 1 }, { x: null }),
            keyOnlyInAfter: A.summarizeChanges({}, { y: 5 }),
          };
        }"""
    )
    assert res["same"] == "Ingen detalj"
    assert res["bothNull"] == "Ingen detalj"
    assert res["undefArgs"] == "Ingen detalj"
    # null-värde formatteras som "-" utan att kasta.
    assert res["nullFieldValues"] == "x: 1 -> -"
    # Nyckel som bara finns i after → before-värdet är undefined → "-".
    assert res["keyOnlyInAfter"] == "y: - -> 5"


# ---------------------------------------------------------------------------
# objectSummary per entity_type.
# ---------------------------------------------------------------------------

def test_object_summary_schedule_cell(audit_page):
    audit_page.evaluate("() => window.__audit.setPersons([{ id: 5, name: 'Anna' }])")
    with_person = _summary(
        audit_page,
        {"entity_type": "schedule_cell", "entity_id": 42, "new_value": {"person_id": 5, "hour": 8}},
    )
    assert with_person == "Anna 08:00"
    # Utan person_id → fallback till Cell #<id>, hour saknas → ingen tidsdel.
    no_person = _summary(
        audit_page,
        {"entity_type": "schedule_cell", "entity_id": 42, "new_value": {}},
    )
    assert no_person == "Cell #42"


def test_object_summary_mcp_query(audit_page):
    assert _summary(
        audit_page,
        {"entity_type": "mcp_query", "entity_id": 1, "new_value": {"model": "minimax-01"}},
    ) == "minimax-01"
    # Ingen model → tool; ingen tool → server; inget → fallbacktext.
    assert _summary(
        audit_page,
        {"entity_type": "mcp_query", "entity_id": 1, "new_value": {"tool": "search"}},
    ) == "search"
    assert _summary(
        audit_page,
        {"entity_type": "mcp_query", "entity_id": 1, "new_value": {}},
    ) == "MCP-fråga"


def test_object_summary_allocation_flow(audit_page):
    assert _summary(
        audit_page,
        {"entity_type": "allocation_flow", "entity_id": 1, "new_value": {"flow_id": "F-123"}},
    ) == "F-123"
    assert _summary(
        audit_page,
        {"entity_type": "allocation_flow", "entity_id": 1, "new_value": {}},
    ) == "Lagerverktyg"


def test_object_summary_rfid_scan_event(audit_page):
    full = _summary(
        audit_page,
        {
            "entity_type": "rfid_scan_event",
            "entity_id": 1,
            "new_value": {"person_name": "Björn", "activity_label": "Ankomst", "local_time": "08:30"},
        },
    )
    assert full == f"Björn {MIDDOT} Ankomst 08:30"
    # Fallbacks: okänd person + module_name som aktivitet, ingen tid.
    fallback = _summary(
        audit_page,
        {"entity_type": "rfid_scan_event", "entity_id": 1, "new_value": {"module_name": "Port 3"}},
    )
    assert fallback == f"Okänd person {MIDDOT} Port 3"


# ---------------------------------------------------------------------------
# detailSummary per entity_type.
# ---------------------------------------------------------------------------

def test_detail_summary_schedule_cell(audit_page):
    audit_page.evaluate("() => window.__audit.setActivities([{ id: 7, label: 'Plock' }])")
    detail = _detail(
        audit_page,
        {
            "entity_type": "schedule_cell",
            "entity_id": 1,
            "new_value": {"hour": 8, "minute_start": 15, "minute_end": 45, "activity_id": 7},
        },
    )
    assert detail == "08:00 15-45, aktivitet: Plock"
    # Defaults (minute_start ?? 0, minute_end ?? 60), null activity → "-", empty_override-flagga.
    defaults = _detail(
        audit_page,
        {
            "entity_type": "schedule_cell",
            "entity_id": 1,
            "new_value": {"hour": 6, "activity_id": None, "empty_override": True},
        },
    )
    assert defaults == "06:00 0-60, aktivitet: - (tom override)"


def test_detail_summary_mcp_query(audit_page):
    detail = _detail(
        audit_page,
        {
            "entity_type": "mcp_query",
            "entity_id": 1,
            "new_value": {
                "status": "ok",
                "tool": "search",
                "model": "m1",
                "question_chars": 10,
                "answer_chars": 20,
                "tools_used": ["a", "b"],
                "missing": ["x"],
                "error_type": "Timeout",
            },
        },
    )
    assert detail == (
        "Status: ok | Verktyg: search | Modell: m1 | 10 tecken fråga | "
        "20 tecken svar | Tools: a, b | Saknar: x | Fel: Timeout"
    )
    assert _detail(
        audit_page,
        {"entity_type": "mcp_query", "entity_id": 1, "new_value": {}},
    ) == "MCP-fråga"


def test_detail_summary_allocation_flow(audit_page):
    detail = _detail(
        audit_page,
        {
            "entity_type": "allocation_flow",
            "entity_id": 1,
            "new_value": {
                "business_code": "DOLE",
                "stage": "match",
                "file_keys": ["a", "b"],
                "table_count": 3,
                "status_code": 200,
                "message": "klart",
            },
        },
    )
    assert detail == "Verksamhet: DOLE | Steg: match | 2 filslotar | 3 tabeller | HTTP 200 | klart"
    assert _detail(
        audit_page,
        {"entity_type": "allocation_flow", "entity_id": 1, "new_value": {}},
    ) == "Lagerverktyg"


def test_detail_summary_rfid_scan_event(audit_page):
    detail = _detail(
        audit_page,
        {
            "entity_type": "rfid_scan_event",
            "entity_id": 1,
            "new_value": {
                "module_name": "Port 3",
                "tag_code": "TAG-9",
                "local_date": "2026-07-07",
                "local_time": "08:30",
                "status": "ok",
                "scan_count": 5,
            },
        },
    )
    assert detail == "Modul: Port 3 | Tagg: TAG-9 | Tid: 2026-07-07 08:30 | Status: ok | Scan #5"
    assert _detail(
        audit_page,
        {"entity_type": "rfid_scan_event", "entity_id": 1, "new_value": {}},
    ) == "RFID-stämpel"

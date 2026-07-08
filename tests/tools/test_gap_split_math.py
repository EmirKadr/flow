"""JS-enhetstest för split-matten i schedule/segments_undo.js.

Buildlöst mönster (jfr tests/tools/test_js_unit_harness.py): konstant-blocket
ur state.js injiceras först (så MIN/MAX_SPLIT_PARTS, DEFAULT_SPLIT_BOUNDARIES
m.fl. finns som globaler), därefter hela segments_undo.js. Split-funktionerna
är rena funktionsdeklarationer och anropas direkt via page.evaluate.

Split-logiken avgör hur en timcell delas i 2-4 delar. Fel gränser eller
osorterade/ovaliderade gränser skulle ge överlappande eller icke-kontinuerliga
segment i schemat — därför spikas kontrakten exakt här.
"""
from __future__ import annotations

import re

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
sync_playwright = playwright_api.sync_playwright

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_JS = ROOT / "app" / "frontend" / "js" / "schedule" / "state.js"
SEGMENTS_UNDO_JS = ROOT / "app" / "frontend" / "js" / "schedule" / "segments_undo.js"


def _split_constants_prelude() -> str:
    """Plocka split-konstanterna ur state.js så testet följer källan."""
    source = STATE_JS.read_text(encoding="utf-8")
    names = [
        "FULL_SEGMENT",
        "HALF_SEGMENTS",
        "DEFAULT_SPLIT_MINUTES",
        "DEFAULT_SPLIT_BOUNDARIES",
        "MIN_SPLIT_PARTS",
        "MAX_SPLIT_PARTS",
    ]
    # HALF_SEGMENTS och DEFAULT_SPLIT_BOUNDARIES sträcker sig över flera rader.
    pattern = re.compile(
        r"^const (?:" + "|".join(names) + r") = .*?(?:\n(?!const ).*?)*?;?\s*$",
        re.M,
    )
    blocks = []
    for name in names:
        m = re.search(
            r"^const " + name + r" = [\s\S]*?;\s*$",
            source,
            re.M,
        )
        assert m, f"konstanten {name} hittades inte i state.js"
        blocks.append(m.group(0))
    return "\n".join(blocks)


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
def split_page(chromium_browser):
    page = chromium_browser.new_page()
    page.goto("about:blank")
    page.add_script_tag(content=_split_constants_prelude())
    page.add_script_tag(content=SEGMENTS_UNDO_JS.read_text(encoding="utf-8"))
    # Sanity: funktionerna som testas ska existera efter injektion.
    missing = page.evaluate(
        """() => [
             "defaultSplitBoundaries",
             "normalizeSplitPartCount",
             "splitSegmentsForBoundaries",
             "orderedSplitBoundariesAreValid",
             "splitRangesFromRanges",
           ].filter((name) => typeof window[name] !== "function")"""
    )
    assert missing == [], f"saknade funktioner efter injektion: {missing}"
    yield page
    page.close()


def test_default_split_boundaries(split_page):
    result = split_page.evaluate(
        """() => ({
             three: defaultSplitBoundaries(3),
             four: defaultSplitBoundaries(4),
             twoWithFirst: defaultSplitBoundaries(2, 45),
           })"""
    )
    assert result["three"] == [20, 40]
    assert result["four"] == [15, 30, 45]
    assert result["twoWithFirst"] == [45]


def test_normalize_split_part_count_clamps(split_page):
    result = split_page.evaluate(
        """() => ({
             low: normalizeSplitPartCount(1),
             high: normalizeSplitPartCount(9),
             garbage: normalizeSplitPartCount("x"),
           })"""
    )
    assert result["low"] == 2   # klampas upp till MIN_SPLIT_PARTS
    assert result["high"] == 4  # klampas ner till MAX_SPLIT_PARTS
    assert result["garbage"] == 2  # ogiltigt -> MIN_SPLIT_PARTS


def test_split_segments_for_boundaries_three_continuous(split_page):
    result = split_page.evaluate("() => splitSegmentsForBoundaries([20, 40], 3)")
    assert result == [
        {"minute_start": 0, "minute_end": 20},
        {"minute_start": 20, "minute_end": 40},
        {"minute_start": 40, "minute_end": 60},
    ]


def test_ordered_split_boundaries_validation(split_page):
    result = split_page.evaluate(
        """() => ({
             unsorted: orderedSplitBoundariesAreValid([40, 20]),
             outOfRange: orderedSplitBoundariesAreValid([60]),
             valid: orderedSplitBoundariesAreValid([30]),
           })"""
    )
    assert result["unsorted"] is False  # fel antal för partCount=2 + osorterat
    assert result["outOfRange"] is False  # 60 är inte < 60
    assert result["valid"] is True


def test_split_ranges_from_ranges_reconstructs_full_from_partial(split_page):
    result = split_page.evaluate(
        "() => splitRangesFromRanges([{ minute_start: 0, minute_end: 45 }])"
    )
    assert result == [
        {"minute_start": 0, "minute_end": 45},
        {"minute_start": 45, "minute_end": 60},
    ]

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_schedule_split_modal_prefills_and_selects_default_minutes():
    schedule = (ROOT / "app" / "frontend" / "js" / "schedule.js").read_text(encoding="utf-8")

    assert "function requestScheduleSplitMinutes" in schedule
    assert "DEFAULT_SPLIT_BOUNDARIES" in schedule
    assert 'data-split-parts="3"' in schedule
    assert 'data-split-parts="4"' in schedule
    assert "Början del ${index + 2}" in schedule
    assert "input.focus();" in schedule
    assert "input.select();" in schedule
    assert "data-enter-default" in schedule
    assert "split_segments: requestedSplitRanges.map" in schedule


def test_schedule_split_rendering_uses_dynamic_segment_ranges():
    schedule = (ROOT / "app" / "frontend" / "js" / "schedule.js").read_text(encoding="utf-8")

    assert "function splitRangesForSegments" in schedule
    assert "function splitSegmentsForBoundaries" in schedule
    assert "function isCompleteSplitRangeList" in schedule
    assert "part.style.flex = `${Math.max(1, minute_end - minute_start)} 1 0`;" in schedule
    assert "Cellen delades i ${formatMinuteList(splitDurationsForRanges(ranges))} minuter." in schedule
    assert "segments[0].minute_end === 30" not in schedule
    assert "focusMatchingSegment(td, 0, 30)" not in schedule

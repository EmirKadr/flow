from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEDULE_SCRIPT_FILES = [
    "state.js",
    "ui_core.js",
    "activity_capacity.js",
    "loan.js",
    "person_order.js",
    "segments_undo.js",
    "calculator.js",
    "rendering.js",
    "summary.js",
    "editing.js",
    "data.js",
    "copy_modal.js",
    "boot.js",
]


def read_schedule_frontend() -> str:
    frontend = ROOT / "app" / "frontend"
    schedule_dir = frontend / "js" / "schedule"
    parts = [(schedule_dir / filename).read_text(encoding="utf-8") for filename in SCHEDULE_SCRIPT_FILES]
    parts.append((frontend / "js" / "schedule.js").read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_schedule_split_modal_prefills_and_selects_default_minutes():
    schedule = read_schedule_frontend()

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
    schedule = read_schedule_frontend()

    assert "function splitRangesForSegments" in schedule
    assert "function splitSegmentsForBoundaries" in schedule
    assert "function isCompleteSplitRangeList" in schedule
    assert "part.style.flex = `${Math.max(1, minute_end - minute_start)} 1 0`;" in schedule
    assert "Cellen delades i ${formatMinuteList(splitDurationsForRanges(ranges))} minuter." in schedule
    assert "segments[0].minute_end === 30" not in schedule
    assert "focusMatchingSegment(td, 0, 30)" not in schedule

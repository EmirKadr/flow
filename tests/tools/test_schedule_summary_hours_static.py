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


def test_schedule_summary_hours_use_up_to_two_decimals():
    schedule = read_schedule_frontend()
    format_hours = schedule.split("function formatHours", 1)[1].split("function ensureManualCalcInput", 1)[0]

    assert "Math.round((num + Number.EPSILON) * 100) / 100" in format_hours
    assert "rounded.toFixed(2)" in format_hours
    assert 'replace(/\\.?0+$/, "")' in format_hours
    assert "toFixed(1)" not in format_hours
    assert "hours.textContent = formatHours(row.hours)" in schedule


def test_schedule_summary_supports_copy_group_split_and_local_undo():
    schedule = read_schedule_frontend()

    assert "writeSummaryClipboardText" in schedule
    assert "navigator.clipboard.writeText" in schedule
    assert 'hours.dataset.summaryHours = "1"' in schedule
    assert "summaryGroupsByScope" in schedule
    assert "selectedScheduleYmdString()" in schedule
    assert "summarizeSelectedSummaryRows" in schedule
    assert "splitSummaryGroup" in schedule
    assert 'kind: "summary"' in schedule
    assert "applySummaryHistoryAction(action, \"undo\")" in schedule
    assert "applySummaryHistoryAction(action, \"redo\")" in schedule
    assert "readOnlyAllowsHistoryShortcut" in schedule
    assert "historyShortcutAction(key, shiftKey)?.kind === \"summary\"" in schedule
    assert "summaryContextMenuHost" in schedule
    assert "host.appendChild(menu)" in schedule
    assert "openSummaryContextMenu(event, found.row, found.tr)" in schedule
    assert "summaryDragSelection" in schedule
    assert "handleSummaryMouseDown" in schedule
    assert "selectSummaryRowRange" in schedule

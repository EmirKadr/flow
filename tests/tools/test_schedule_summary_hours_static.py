from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_schedule_summary_hours_use_up_to_two_decimals():
    schedule = (ROOT / "app" / "frontend" / "js" / "schedule.js").read_text(encoding="utf-8")
    format_hours = schedule.split("function formatHours", 1)[1].split("function ensureManualCalcInput", 1)[0]

    assert "Math.round((num + Number.EPSILON) * 100) / 100" in format_hours
    assert "rounded.toFixed(2)" in format_hours
    assert 'replace(/\\.?0+$/, "")' in format_hours
    assert "toFixed(1)" not in format_hours
    assert "<td>${formatHours(row.hours)}</td>" in schedule

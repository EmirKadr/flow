from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_my_productivity_view_renders_global_person_productivity_stats():
    frontend = ROOT / "app" / "frontend"
    personal_js = (frontend / "js" / "personal_views.js").read_text(encoding="utf-8")
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    assert "const dayStats = payload.productivity?.day || null;" in personal_js
    assert "const weekStats = payload.productivity?.week || null;" in personal_js
    assert "function productivityActivityTable(stats)" in personal_js
    assert "Dagens produktivitet" in personal_js
    assert "Veckans produktivitet" in personal_js
    assert "personal-productivity-table" in personal_js
    assert ".personal-productivity-table" in styles
    assert ".personal-productivity-score.good" in styles

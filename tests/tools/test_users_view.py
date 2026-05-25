from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_users_view_uses_delete_button_without_active_toggle():
    frontend = ROOT / "app" / "frontend"
    users_html = (frontend / "anvandare.html").read_text(encoding="utf-8")
    users_js = (frontend / "js" / "users.js").read_text(encoding="utf-8")

    assert 'id="show-inactive"' not in users_html
    assert "<th>Aktiv</th>" not in users_html
    assert "data-toggle" not in users_js
    assert "m-active" not in users_js
    assert "Inaktivera" not in users_js
    assert "Aktivera" not in users_js
    assert 'api.get("/api/users")' in users_js
    assert 'api.del(`/api/users/${user.id}`)' in users_js
    assert "Ta bort användaren permanent?" in users_js

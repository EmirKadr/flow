from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import User
from app.backend.routers import public_dpak
from app.backend.security import verify_password


FRONTEND = Path(__file__).resolve().parents[2] / "app" / "frontend"
APP_PAGES = sorted("/" + path.name for path in FRONTEND.glob("*.html") if path.name != "stallen.html")


@pytest.mark.parametrize("path", ["/", *APP_PAGES])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_all_app_views_are_available_on_stigamo(path, method):
    client = TestClient(app, base_url="https://stigamo.nu", follow_redirects=False)
    response = client.request(method, path + "?week=2026-38&area=R%2F3")
    assert response.status_code == 200
    assert "location" not in response.headers


@pytest.mark.parametrize("path,target", [
    ("/stallen", "/aktiviteter.html"), ("/stallen.html", "/aktiviteter.html"),
    ("/meta", "/meta-upload.html"), ("/meta-upload", "/meta-upload.html"),
])
def test_legacy_aliases_redirect_within_the_same_site(path, target):
    client = TestClient(app, base_url="https://stigamo.nu", follow_redirects=False)
    response = client.get(path)
    assert response.status_code == 308
    assert response.headers["location"] == target
    assert client.get(target).status_code == 200


@pytest.mark.parametrize("host", [
    "stigamo.nu", "www.stigamo.nu", "STIGAMO.NU", "stigamo.nu.", "stigamo.nu:443",
    "flow.nowastelogistics.com", "localhost", "127.0.0.1", "testserver",
])
def test_hosts_and_cached_clients_are_not_redirected(host):
    client = TestClient(app, base_url=f"https://{host}", follow_redirects=False)
    assert client.get("/login.html").status_code == 200
    response = client.get("/api/site-migration")
    assert response.json() == {"active": False, "target_origin": "https://stigamo.nu"}
    assert response.headers["cache-control"] == "no-store"
    assert client.head("/api/site-migration").status_code == 200


@pytest.mark.parametrize("host", ["stigamo.nu", "www.stigamo.nu"])
def test_login_session_and_writes_work_again_without_bypassing_auth(monkeypatch, host):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            user = User(username="restoration-test", display_name="Test User", role="admin", roles=["admin"],
                        is_active=True, must_change_password=True, password_hash=None)
            db.add(user)
            db.commit()
            monkeypatch.setitem(app.dependency_overrides, get_db, lambda: db)
            client = TestClient(app, base_url=f"https://{host}", follow_redirects=False)
            assert client.get("/api/auth/me").status_code == 401
            assert client.post("/api/auth/login", json={"username": user.username, "password": ""}).status_code == 200
            assert client.get("/api/auth/me").json()["username"] == user.username
            response = client.post("/api/auth/set-password", json={"password": "test-restored-password"})
            assert response.status_code == 200
            db.refresh(user)
            assert verify_password("test-restored-password", user.password_hash)
            assert user.must_change_password is False
            assert client.post("/api/auth/logout").status_code == 204
            assert client.get("/api/auth/me").status_code == 401
            assert client.post("/api/auth/set-password", json={"password": "test-other-password"}).status_code == 401
    finally:
        engine.dispose()


@pytest.mark.parametrize("path", ["/d-pak", "/d-pak/", "/dpak-fraga.html"])
def test_dpak_page_and_all_its_assets_stay_on_old_domain(path):
    import re

    client = TestClient(app, base_url="https://stigamo.nu", follow_redirects=False)
    response = client.get(path + "?business=TEST")
    assert response.status_code == 200
    assert 'id="publicDpakForm"' in response.text
    for asset in re.findall(r'(?:src|href)="(/[^"#]+)"', response.text):
        assert client.get(asset).status_code == 200, asset
    assert client.head(path).status_code == 200


def test_dpak_status_and_chat_still_reach_their_handlers(monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, public_dpak.get_db, lambda: None)
    monkeypatch.setattr(public_dpak, "dataset_status", lambda *_: {"ready": True})
    monkeypatch.setattr(public_dpak, "_public_dpak_model_config", lambda: SimpleNamespace(model="test", max_tokens=50))
    seen = []

    def answer(_db, **kwargs):
        seen.append(kwargs["messages"])
        return {"answer": "Testsvaret", "table": [], "model": "test"}

    monkeypatch.setattr(public_dpak, "run_public_dpak_agent", answer)
    client = TestClient(app, base_url="https://stigamo.nu", follow_redirects=False)
    assert client.get("/api/public/dpak-chat/status?business_code=TEST").json() == {"ready": True}
    messages = [{"role": "user", "content": "En testfråga"}]
    response = client.post("/api/public/dpak-chat/message", json={"messages": messages})
    assert response.status_code == 200
    assert response.json()["answer"] == "Testsvaret"
    assert seen == [messages]


def test_app_pages_no_longer_load_the_retired_redirect_script():
    for page in FRONTEND.glob("*.html"):
        assert '/js/site_migration.js' not in page.read_text(encoding="utf-8"), page.name
    client = TestClient(app, base_url="https://stigamo.nu")
    # Cached HTML can still request the old asset without a 404 or a redirect.
    assert client.get("/js/site_migration.js").status_code == 200
    assert client.get("/api/health").status_code == 200

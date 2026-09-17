from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.backend.main import app
from app.backend.routers import public_dpak
from app.backend.site_migration import TARGET_ORIGIN, enforce_site_migration


FRONTEND = Path(__file__).resolve().parents[2] / "app" / "frontend"
APP_PAGES = sorted("/" + path.name for path in FRONTEND.glob("*.html") if path.name != "dpak-fraga.html")


@pytest.mark.parametrize("path", ["/", *APP_PAGES, "/meta", "/meta-upload", "/stallen", "/unknown-view", "/docs"])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_every_old_view_redirects_immediately_with_query_preserved(path, method):
    client = TestClient(app, base_url="https://stigamo.nu", follow_redirects=False)
    response = client.request(method, path + "?week=2026-38&area=R%2F3")
    assert response.status_code == 302
    assert response.headers["location"] == TARGET_ORIGIN + path + "?week=2026-38&area=R%2F3"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize("host", ["stigamo.nu", "www.stigamo.nu", "STIGAMO.NU", "stigamo.nu.", "stigamo.nu:443"])
def test_old_host_aliases_are_retired(host):
    response = TestClient(app).get("/", headers={"Host": host}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == TARGET_ORIGIN + "/"


@pytest.mark.parametrize("host", ["flow.nowastelogistics.com", "localhost", "127.0.0.1", "testserver", "stigamo.nu.example.org"])
def test_new_domain_and_local_clients_are_not_redirected(host):
    client = TestClient(app, base_url=f"https://{host}", follow_redirects=False)
    assert client.get("/login.html").status_code == 200
    assert client.get("/api/site-migration").json()["active"] is False


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/auth/me"), ("HEAD", "/api/export"),
    ("POST", "/api/auth/login"), ("PUT", "/api/schedule/1"),
    ("DELETE", "/api/persons/1"), ("PATCH", "/api/settings"),
    ("POST", "/api/meta/uploads"), ("POST", "/login.html"),
    ("GET", "/api"), ("POST", "/d-pak"),
    ("POST", "/api/public/dpak-chat/message/other"),
    ("DELETE", "/api/public/dpak-chat/message"),
])
def test_old_api_and_writes_are_blocked_before_handlers_run(method, path):
    probe = FastAPI()
    probe.middleware("http")(enforce_site_migration)
    called = []

    @probe.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"])
    async def handler(request: Request):
        called.append(request.url.path)
        return {"saved": True}

    response = TestClient(probe, base_url="https://stigamo.nu").request(method, path)
    assert response.status_code == 410
    assert "location" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    assert called == []
    if method != "HEAD":
        assert response.json()["code"] == "site_moved"
        assert TARGET_ORIGIN in response.json()["detail"]


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


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_health_and_migration_status_remain_available_without_auth(method):
    client = TestClient(app, base_url="https://stigamo.nu", follow_redirects=False)
    assert client.get("/api/health").status_code == 200
    response = client.request(method, "/api/site-migration")
    assert response.status_code == 200
    if method == "GET":
        assert response.json() == {"active": True, "target_origin": TARGET_ORIGIN}
    else:
        assert response.content == b""
    assert response.headers["cache-control"] == "no-store"


def test_redirect_cannot_be_changed_by_query_or_forwarded_host():
    client = TestClient(app, base_url="https://stigamo.nu", follow_redirects=False)
    response = client.get("/login.html?next=https%3A%2F%2Fexample.org", headers={"X-Forwarded-Host": "example.org"})
    assert response.headers["location"].startswith(TARGET_ORIGIN + "/login.html?")


def test_every_app_page_loads_the_cached_page_migration_guard():
    for page in APP_PAGES:
        source = (FRONTEND / page.lstrip("/")).read_text(encoding="utf-8")
        assert '<script src="/js/site_migration.js" defer></script>' in source, page

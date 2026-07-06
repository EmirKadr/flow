"""Leveranslagret: gzip-komprimering, cache-headers för statiska filer och
ETag/304 på API-GET. Kontrakten här skyddar prestandaoptimeringarna från
2026-07 (se wiki/prestanda-leveranslager.md) mot tyst regression."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import StreamingResponse

from app.backend.config import settings
from app.backend.main import app


def test_large_json_response_is_gzip_compressed():
    client = TestClient(app)

    response = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"


def test_large_static_js_is_gzip_compressed():
    client = TestClient(app)

    response = client.get("/js/api.js", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"


def test_small_json_response_is_not_compressed():
    client = TestClient(app)

    response = client.get("/api/health", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert "content-encoding" not in response.headers


def test_gzip_middleware_leaves_sse_streams_alone():
    """SSE-progressströmmarna (produktivitet/sankey) får aldrig komprimeras —
    komprimering buffrar och bryter progressuppdateringarna. Starlette undantar
    text/event-stream som standard; det här låser antagandet vår konfig vilar på."""
    sse_app = FastAPI()
    sse_app.add_middleware(GZipMiddleware, minimum_size=1024)

    @sse_app.get("/stream")
    def stream():
        def events():
            yield ("data: " + "x" * 4096 + "\n\n").encode()

        return StreamingResponse(events(), media_type="text/event-stream")

    response = TestClient(sse_app).get("/stream", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert "content-encoding" not in response.headers


def test_api_get_json_gets_weak_etag_and_revalidation_headers():
    client = TestClient(app)

    response = client.get("/api/health")

    etag = response.headers.get("etag")
    assert etag and etag.startswith('W/"')
    assert response.headers.get("cache-control") == "private, no-cache"


def test_api_get_with_matching_if_none_match_returns_304_without_body():
    client = TestClient(app)

    first = client.get("/api/health")
    etag = first.headers["etag"]

    second = client.get("/api/health", headers={"If-None-Match": etag})

    assert second.status_code == 304
    assert second.headers["etag"] == etag
    assert second.content == b""


def test_api_get_with_stale_if_none_match_returns_full_body():
    client = TestClient(app)

    response = client.get("/api/health", headers={"If-None-Match": 'W/"gammal"'})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_production_versioned_static_assets_get_immutable_cache(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    client = TestClient(app)

    response = client.get("/js/common.js?v=abc123")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_production_unversioned_static_assets_revalidate(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    client = TestClient(app)

    js_response = client.get("/js/common.js")
    html_response = client.get("/aktiviteter.html")
    root_response = client.get("/")

    assert js_response.headers["cache-control"] == "no-cache"
    assert html_response.headers["cache-control"] == "no-cache"
    assert root_response.headers["cache-control"] == "no-cache"


def test_production_html_never_gets_immutable_cache_even_with_v(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    client = TestClient(app)

    response = client.get("/aktiviteter.html?v=abc123")

    assert response.headers["cache-control"] == "no-cache"

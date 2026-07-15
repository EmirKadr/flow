"""Leveranslagret: gzip-komprimering, cache-headers för statiska filer och
ETag/304 på API-GET. Kontrakten här skyddar prestandaoptimeringarna från
2026-07 (se wiki/prestanda-leveranslager.md) mot tyst regression."""
import hashlib

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import StreamingResponse

from app.backend.config import settings
from app.backend.main import api_get_etag, app


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


def test_gzip_middleware_pins_compresslevel_to_6():
    """Nivån måste vara EXPLICIT satt till 6, inte ärvd från Starlette.

    Starlettes default är compresslevel=9 — den dyraste zlib-nivån — och
    GZipResponder komprimerar synkront på event-loopen i vår enda uvicorn-worker.
    Nivå 9 kostar 3-4x CPU mot nivå 6 för nästan identisk storlek. Utan det här
    kontraktet driver nivån tyst tillbaka till library-defaulten så fort någon
    tar bort argumentet eller uppgraderar starlette.
    """
    gzip_layers = [m for m in app.user_middleware if m.cls is GZipMiddleware]

    assert len(gzip_layers) == 1, "förväntar exakt en GZipMiddleware i kedjan"
    kwargs = gzip_layers[0].kwargs
    assert kwargs.get("compresslevel") == 6, (
        "GZipMiddleware måste sätta compresslevel=6 explicit; "
        f"fick {kwargs.get('compresslevel')!r} (Starlettes default är 9)"
    )
    assert kwargs.get("minimum_size") == 1024


def test_gzip_response_decompresses_to_the_identical_uncompressed_body():
    """Gzip är transparent transportkodning: klienten får byte-identisk payload
    med och utan komprimering, och komprimeringen är faktiskt PÅ.

    OBS: det här testet säger MEDVETET ingenting om compresslevel — det passerar
    lika grönt vid nivå 1, 6 och 9, eftersom alla ger samma dekomprimerade bytes.
    Nivå-pinningen (=6) bevisas av test_gzip_middleware_pins_compresslevel_to_6,
    inte här. Det här testet vaktar att gzip är aktivt och inte korrumperar bodyn
    (byt ut/ta bort GZipMiddleware → content-encoding-assertionen rodnar)."""
    client = TestClient(app)

    compressed = client.get("/js/api.js", headers={"Accept-Encoding": "gzip"})
    plain = client.get("/js/api.js", headers={"Accept-Encoding": "identity"})

    assert compressed.headers.get("content-encoding") == "gzip"
    assert "content-encoding" not in plain.headers
    # httpx avkodar gzip transparent -> .content är den dekomprimerade bodyn.
    assert compressed.content == plain.content


def test_gzip_middleware_is_outermost_relative_to_api_get_etag():
    """Hela beteendeargumentet för compresslevel=6 vilar på att ETag hashas på
    den OKOMPRIMERADE bodyn. Det kräver att GZipMiddleware ligger YTTERST och
    api_get_etag INNANFÖR: på svarsvägen bygger api_get_etag ETag:en först
    (okomprimerad body), sedan komprimerar gzip. add_middleware infogar först i
    listan och stacken byggs i reversed ordning → lägre index i user_middleware
    = längre ut. Kastas ordningen om skulle api_get_etag hasha gzip-bytes och
    ETag:en bli innehållsberoende av komprimeringsnivån."""
    gzip_index = next(
        i for i, m in enumerate(app.user_middleware) if m.cls is GZipMiddleware
    )
    etag_index = next(
        i
        for i, m in enumerate(app.user_middleware)
        if m.kwargs.get("dispatch") is api_get_etag
    )
    assert gzip_index < etag_index, (
        "GZipMiddleware måste ligga ytterst om api_get_etag "
        f"(gzip index {gzip_index}, etag index {etag_index}); annars hashas ETag "
        "på den komprimerade bodyn och 304-revalideringen blir nivåberoende."
    )


def test_etag_is_the_hash_of_the_uncompressed_body_for_gzipped_api_json():
    """Den otestade invarianten: ett API-JSON-svar >1024 B ska BÅDE gzippas OCH
    få en ETag, och ETag:en ska vara hashen av den OKOMPRIMERADE bodyn (inte av
    gzip-strömmen). Alla andra ETag-test använder /api/health, som är <1024 B och
    aldrig gzippas — kombinationen 'gzippat API-JSON MED ETag' saknades helt.

    Sonden monteras temporärt på den riktiga appen (framför StaticFiles-mounten
    på '/') så den går genom den skarpa middleware-kedjan; en omkastning av
    gzip/etag-ordningen i main.py får den här att rodna."""
    probe_path = "/api/_gzip_etag_probe_tmp"
    payload = {"rows": [{"i": n, "blob": "x" * 40} for n in range(60)]}

    def _probe():
        return payload

    app.add_api_route(probe_path, _probe, methods=["GET"])
    # add_api_route lägger sonden SIST, dvs efter StaticFiles-mounten på '/' som
    # annars fångar allt → flytta den främst så den matchas.
    app.router.routes.insert(0, app.router.routes.pop())
    try:
        client = TestClient(app)
        response = client.get(probe_path, headers={"Accept-Encoding": "gzip"})

        assert response.status_code == 200
        assert response.headers.get("content-encoding") == "gzip", (
            "sonden måste vara stor nog att gzippas för att bevisa något"
        )
        # httpx avkodar gzip transparent → .content är den okomprimerade bodyn.
        uncompressed = response.content
        assert len(uncompressed) > 1024
        # Wire-storleken (content-length) < okomprimerad → gzip slog verkligen till.
        assert int(response.headers["content-length"]) < len(uncompressed)

        etag = response.headers.get("etag")
        expected = 'W/"' + hashlib.sha256(uncompressed).hexdigest()[:32] + '"'
        assert etag == expected, (
            f"ETag {etag!r} != hash av okomprimerad body {expected!r}. Om gzip "
            "ligger innanför api_get_etag hashas gzip-strömmen i stället."
        )

        conditional = client.get(
            probe_path,
            headers={"Accept-Encoding": "gzip", "If-None-Match": etag},
        )
        assert conditional.status_code == 304
        assert conditional.content == b""
    finally:
        app.router.routes[:] = [
            r for r in app.router.routes if getattr(r, "path", None) != probe_path
        ]


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

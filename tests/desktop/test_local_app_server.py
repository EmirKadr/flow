import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import requests

from desktop import local_runtime
from desktop.local_app_server import LocalAppServer, localize_set_cookie
from desktop.local_runtime import LOCAL_REF_PREFIX, DesktopLocalRuntime


class FakeUpstreamHandler(BaseHTTPRequestHandler):
    seen_accept_encoding = ""

    def log_message(self, _format, *_args):  # noqa: A002
        return

    def do_GET(self):  # noqa: N802
        if self.path == "/api/login":
            type(self).seen_accept_encoding = self.headers.get("Accept-Encoding", "")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header(
                "Set-Cookie",
                "flow_session=abc; Path=/; SameSite=lax; Secure",
            )
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        if self.path == "/api/cookie":
            body = json.dumps({"cookie": self.headers.get("Cookie", "")}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


def start_upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def start_workflow_source_upstream(requests_seen):
    class WorkflowSourceHandler(FakeUpstreamHandler):
        def do_POST(self):  # noqa: N802
            if self.path == "/api/workflow-data/source":
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                requests_seen.append({"payload": payload, "cookie": self.headers.get("Cookie", "")})
                body = "Artikel\tRobot\nA100\tY\n".encode("utf-8-sig")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Flow-Source-Rows", "1")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), WorkflowSourceHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_localize_set_cookie_removes_remote_only_attributes():
    cookie = localize_set_cookie(
        "flow_session=abc; Path=/; Domain=stigamo.nu; SameSite=lax; Secure"
    )

    assert "Secure" not in cookie
    assert "Domain=" not in cookie
    assert "flow_session=abc" in cookie


def test_local_app_server_serves_frontend_and_proxies_api(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<h1>flow</h1>", encoding="utf-8")

    upstream, upstream_thread = start_upstream()
    local = None
    try:
        upstream_url = f"http://127.0.0.1:{upstream.server_address[1]}"
        local = LocalAppServer(
            upstream_base_url=upstream_url,
            frontend_dir=frontend,
            preferred_port=0,
        )
        local_url = local.start()

        assert requests.get(local_url, timeout=5).text == "<h1>flow</h1>"

        client = requests.Session()
        login = client.get(
            f"{local_url}api/login",
            headers={"Accept-Encoding": "br, gzip, deflate, zstd"},
            timeout=5,
        )
        assert login.status_code == 200
        assert "Secure" not in login.headers["Set-Cookie"]
        assert FakeUpstreamHandler.seen_accept_encoding == "identity"

        cookie_echo = client.get(f"{local_url}api/cookie", timeout=5).json()
        assert cookie_echo["cookie"] == "flow_session=abc"
    finally:
        if local is not None:
            local.stop()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=3)


def test_desktop_proxy_streams_media_and_forwards_range_without_buffering(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<h1>flow</h1>", encoding="utf-8")
    calls = []

    class StreamingResponse:
        status_code = 206
        headers = {
            "Content-Type": "video/quicktime",
            "Content-Length": "6",
            "Content-Range": "bytes 0-5/29",
            "Accept-Ranges": "bytes",
        }
        raw = SimpleNamespace(headers={})

        @property
        def content(self):
            raise AssertionError("Desktop-proxyn får inte buffra response.content")

        def iter_content(self, chunk_size):
            assert chunk_size == 64 * 1024
            yield b"abc"
            yield b"def"

        def close(self):
            calls.append({"closed": True})

    class StreamingSession:
        def __init__(self):
            self.cookies = requests.cookies.RequestsCookieJar()

        def request(self, method, url, **kwargs):
            calls.append({
                "method": method,
                "url": url,
                "range": kwargs["headers"].get("Range"),
                "stream": kwargs.get("stream"),
            })
            return StreamingResponse()

        def close(self):
            return

    local = LocalAppServer(
        upstream_base_url="https://flow.example/",
        frontend_dir=frontend,
        preferred_port=0,
    )
    local._session.close()
    local._session = StreamingSession()
    try:
        local_url = local.start()
        response = requests.get(
            f"{local_url}api/meta/uploads/155/content?variant=original",
            headers={"Range": "bytes=0-5"},
            timeout=5,
        )

        assert response.status_code == 206
        assert response.content == b"abcdef"
        assert response.headers["Content-Range"] == "bytes 0-5/29"
        assert response.headers["Content-Length"] == "6"
        assert calls[0]["method"] == "GET"
        assert calls[0]["range"] == "bytes=0-5"
        assert calls[0]["stream"] is True
        assert calls[-1] == {"closed": True}
    finally:
        local.stop()


def test_desktop_allocation_flow_fetches_central_workflow_source(monkeypatch, tmp_path):
    requests_seen = []
    upstream, upstream_thread = start_workflow_source_upstream(requests_seen)
    runtime = DesktopLocalRuntime(tmp_path)
    captured = {}

    def fake_run_flow_handler(flow_id, files, params, default_max_csv_path=None):
        captured["flow_id"] = flow_id
        captured["saldo"] = files["saldo"].read_text(encoding="utf-8-sig")
        return {"tables": {}, "log": []}

    monkeypatch.setattr(local_runtime.allocation, "run_flow_handler", fake_run_flow_handler)

    try:
        upstream_url = f"http://127.0.0.1:{upstream.server_address[1]}/"
        result = runtime.run_allocation_flow(
            "lyx",
            {},
            {},
            upstream_root=upstream_url,
            headers={"Cookie": "flow_session=abc"},
        )
    finally:
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=3)

    assert captured == {"flow_id": "lyx", "saldo": "Artikel\tRobot\nA100\tY\n"}
    assert requests_seen == [
        {
            "payload": {"feature": "allocation", "flow_id": "lyx", "source_key": "saldo"},
            "cookie": "flow_session=abc",
        }
    ]
    assert result["source_status"][0]["status"] == "api"


def test_desktop_productivity_report_proxies_central_server(monkeypatch, tmp_path):
    runtime = DesktopLocalRuntime(tmp_path)
    calls = []
    audits = []

    monkeypatch.setattr(
        runtime,
        "enqueue_local_audit",
        lambda **kwargs: audits.append(kwargs["payload"]),
    )

    def fake_upstream(upstream_root, path, headers):
        calls.append({"root": upstream_root, "path": path, "headers": headers})
        return {"people": [{"name": "Alvin"}], "summary": {"people": 1}}

    monkeypatch.setattr(local_runtime, "_upstream_json", fake_upstream)

    response = local_runtime.local_response_for_request(
        runtime,
        SimpleNamespace(command="GET", headers={"Cookie": "flow_session=abc"}),
        parsed=SimpleNamespace(path="/api/productivity", query="date=2026-06-08"),
        upstream_root="https://flow.example/",
    )

    assert response is not None
    status_code, content_type, body = response
    assert status_code == 200
    assert content_type.startswith("application/json")
    assert json.loads(body.decode("utf-8"))["people"] == [{"name": "Alvin"}]
    assert calls == [
        {
            "root": "https://flow.example/",
            "path": "/api/productivity?date=2026-06-08",
            "headers": {"Cookie": "flow_session=abc"},
        }
    ]
    assert audits[0]["status"] == "ok"


def test_desktop_person_productivity_proxies_central_server(monkeypatch, tmp_path):
    runtime = DesktopLocalRuntime(tmp_path)
    calls = []

    monkeypatch.setattr(runtime, "enqueue_local_audit", lambda **_kwargs: None)

    def fake_upstream(upstream_root, path, headers):
        calls.append({"root": upstream_root, "path": path, "headers": headers})
        return {"person": {"id": 4, "name": "Alvin"}, "activities": []}

    monkeypatch.setattr(local_runtime, "_upstream_json", fake_upstream)

    response = local_runtime.local_response_for_request(
        runtime,
        SimpleNamespace(command="GET", headers={"Cookie": "flow_session=abc"}),
        parsed=SimpleNamespace(path="/api/productivity/persons/4", query="period=week&date=2026-06-09"),
        upstream_root="https://flow.example/",
    )

    assert response is not None
    status_code, content_type, body = response
    assert status_code == 200
    assert content_type.startswith("application/json")
    assert json.loads(body.decode("utf-8"))["person"]["name"] == "Alvin"
    assert calls == [
        {
            "root": "https://flow.example/",
            "path": "/api/productivity/persons/4?period=week&date=2026-06-09",
            "headers": {"Cookie": "flow_session=abc"},
        }
    ]


def test_desktop_schedule_productivity_summary_proxies_central_server(monkeypatch, tmp_path):
    runtime = DesktopLocalRuntime(tmp_path)
    calls = []

    monkeypatch.setattr(runtime, "enqueue_local_audit", lambda **_kwargs: None)

    def fake_upstream(upstream_root, path, headers):
        calls.append({"root": upstream_root, "path": path, "headers": headers})
        return {"people": {"4": {"percent": 88}}}

    monkeypatch.setattr(local_runtime, "_upstream_json", fake_upstream)

    response = local_runtime.local_response_for_request(
        runtime,
        SimpleNamespace(command="GET", headers={"Cookie": "flow_session=abc"}),
        parsed=SimpleNamespace(path="/api/schedule/productivity-summary", query="year=2026&week=24&weekday=2"),
        upstream_root="https://flow.example/",
    )

    assert response is not None
    status_code, content_type, body = response
    assert status_code == 200
    assert content_type.startswith("application/json")
    assert json.loads(body.decode("utf-8"))["people"]["4"]["percent"] == 88
    assert calls == [
        {
            "root": "https://flow.example/",
            "path": "/api/schedule/productivity-summary?year=2026&week=24&weekday=2",
            "headers": {"Cookie": "flow_session=abc"},
        }
    ]


def test_desktop_productivity_report_requires_central_server(monkeypatch, tmp_path):
    runtime = DesktopLocalRuntime(tmp_path)
    audits = []

    monkeypatch.setattr(runtime, "enqueue_local_audit", lambda **kwargs: audits.append(kwargs["payload"]))
    monkeypatch.setattr(local_runtime, "_upstream_json", lambda *_args, **_kwargs: None)

    response = local_runtime.local_response_for_request(
        runtime,
        SimpleNamespace(command="GET", headers={}),
        parsed=SimpleNamespace(path="/api/productivity", query=""),
        upstream_root="",
    )

    assert response is not None
    status_code, _content_type, body = response
    payload = json.loads(body.decode("utf-8"))
    assert status_code == 503
    assert "central serverdata" in payload["detail"]
    assert audits[0]["status"] == "error"


def test_desktop_allocation_flow_falls_back_to_local_ref(monkeypatch, tmp_path):
    runtime = DesktopLocalRuntime(tmp_path)
    fallback = tmp_path / "saldo.csv"
    fallback.write_text("Artikel\tRobot\nLOCAL\tN\n", encoding="utf-8")
    entry = runtime.register_path(fallback)
    captured = {}

    def fail_download(**_kwargs):
        raise RuntimeError("Extern datakälla kunde inte nås.")

    def fake_run_flow_handler(flow_id, files, params, default_max_csv_path=None):
        captured["saldo"] = files["saldo"]
        return {"tables": {}, "log": []}

    monkeypatch.setattr(runtime, "_download_workflow_source", fail_download)
    monkeypatch.setattr(local_runtime.allocation, "run_flow_handler", fake_run_flow_handler)

    result = runtime.run_allocation_flow(
        "lyx",
        {"saldo": f"{LOCAL_REF_PREFIX}{entry['localRef']}"},
        {},
        upstream_root="http://127.0.0.1:1/",
        headers={},
    )

    assert captured["saldo"] == fallback.resolve()
    assert result["source_status"][0]["status"] == "local_ref_fallback"


def test_desktop_allocation_flow_skips_api_for_upload_source_mode(monkeypatch, tmp_path):
    runtime = DesktopLocalRuntime(tmp_path)
    details = tmp_path / "details.csv"
    overview = tmp_path / "overview.csv"
    details.write_text("Ordernr\n1\n", encoding="utf-8")
    overview.write_text("Ordernr\n1\n", encoding="utf-8")
    profile = {
        "flows": {
            "hib-koppling": {
                "sources": {"details": "upload", "overview": "upload"},
            }
        }
    }
    captured = {}

    def fake_download(**_kwargs):
        raise AssertionError("API-kalla ska inte hamtas nar uppladdning ar vald")

    def fake_run_flow_handler(flow_id, files, params, default_max_csv_path=None):
        captured["flow_id"] = flow_id
        captured["files"] = dict(files)
        return {"tables": {}, "log": []}

    monkeypatch.setattr(runtime, "_download_workflow_source", fake_download)
    monkeypatch.setattr(local_runtime.allocation, "run_flow_handler", fake_run_flow_handler)

    result = runtime.run_allocation_flow(
        "hib-koppling",
        {local_runtime.allocation.USER_FILTERS_PARAM: json.dumps(profile)},
        {"details": details, "overview": overview},
        upstream_root="http://127.0.0.1:1/",
        headers={},
    )

    assert captured["flow_id"] == "hib-koppling"
    assert captured["files"] == {"details": details, "overview": overview}
    assert "source_status" not in result


def test_desktop_allocation_flow_applies_user_filter_profile(monkeypatch, tmp_path):
    runtime = DesktopLocalRuntime(tmp_path)
    orders = tmp_path / "orders.csv"
    orders.write_text(
        "Bolag\tKund\tArtikel\n"
        "GG\t6005\tA1\n"
        "GG\t1234\tA2\n"
        "MG\t1234\tA3\n",
        encoding="utf-8",
    )
    profile = {
        "flows": {
            "vecka27-check": {
                "files": {
                    "orders": [
                        {"column": "Bolag", "operator": "EQ", "value": "GG"},
                        {"column": "Kund", "operator": "NotIn", "value": ["6005"]},
                    ]
                }
            }
        }
    }
    captured = {}

    def fake_run_flow_handler(flow_id, files, params, default_max_csv_path=None):
        captured["flow_id"] = flow_id
        captured["params"] = dict(params)
        captured["text"] = files["orders"].read_text(encoding="utf-8-sig")
        return {"tables": {}, "log": ["handler"]}

    monkeypatch.setattr(local_runtime.workflow_data, "allocation_api_source_map", lambda _flow_id: {})
    monkeypatch.setattr(local_runtime.allocation, "run_flow_handler", fake_run_flow_handler)

    result = runtime.run_allocation_flow(
        "vecka27-check",
        {local_runtime.allocation.USER_FILTERS_PARAM: json.dumps(profile)},
        {"orders": orders},
    )

    assert captured["flow_id"] == "vecka27-check"
    assert captured["params"] == {}
    assert "A2" in captured["text"]
    assert "A1" not in captured["text"]
    assert "A3" not in captured["text"]
    assert result["user_filter"]["lines"] == ["Anvandarfilter orders: 3 -> 1 rader (2 villkor)."]


def test_desktop_ytgenerering_applies_user_settings_profile(monkeypatch, tmp_path):
    runtime = DesktopLocalRuntime(tmp_path)
    location = tmp_path / "location.csv"
    location.write_text("Lagerplats\tTyp\tMax pall\nUTL205\tU\t1\n", encoding="utf-8")
    profile = {
        "flows": {
            "ytgenerering": {
                "settings": {
                    "ytgenerering": {
                        "areas": {"MG": {"utlMin": 310, "utlMax": 330}},
                        "carrierClusters": {
                            "rows": [{"carrierNum": "39", "clusterGroup": "Freja", "startSeq": "600", "endSeq": "652"}]
                        },
                    }
                }
            }
        }
    }
    captured = {}

    def fake_run_flow_handler(flow_id, files, params, default_max_csv_path=None):
        captured["flow_id"] = flow_id
        captured["files"] = dict(files)
        captured["params"] = dict(params)
        return {"tables": {}, "log": []}

    monkeypatch.setattr(local_runtime.workflow_data, "allocation_api_source_map", lambda _flow_id: {})
    monkeypatch.setattr(local_runtime.allocation, "run_flow_handler", fake_run_flow_handler)

    runtime.run_allocation_flow(
        "ytgenerering",
        {
            local_runtime.allocation.PROCESS_AREA_FOCUS_PARAM: "MG",
            local_runtime.allocation.USER_FILTERS_PARAM: json.dumps(profile),
        },
        {"location": location},
    )

    assert captured["flow_id"] == "ytgenerering"
    assert captured["files"]["location"] == location
    assert captured["params"][local_runtime.allocation.YTGENERERING_UTL_MIN_PARAM] == "310"
    assert captured["params"][local_runtime.allocation.YTGENERERING_UTL_MAX_PARAM] == "330"
    assert '"Freja"' in captured["params"]["__carrier_clusters_json"]

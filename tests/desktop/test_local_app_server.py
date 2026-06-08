import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from desktop import local_runtime
from desktop.local_app_server import LocalAppServer, localize_set_cookie
from desktop.local_runtime import LOCAL_REF_PREFIX, DesktopLocalRuntime


class FakeUpstreamHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):  # noqa: A002
        return

    def do_GET(self):  # noqa: N802
        if self.path == "/api/login":
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
        login = client.get(f"{local_url}api/login", timeout=5)
        assert login.status_code == 200
        assert "Secure" not in login.headers["Set-Cookie"]

        cookie_echo = client.get(f"{local_url}api/cookie", timeout=5).json()
        assert cookie_echo["cookie"] == "flow_session=abc"
    finally:
        if local is not None:
            local.stop()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=3)


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

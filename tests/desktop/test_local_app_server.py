import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from desktop.local_app_server import LocalAppServer, localize_set_cookie


class FakeUpstreamHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):  # noqa: A002
        return

    def do_GET(self):  # noqa: N802
        if self.path == "/api/login":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header(
                "Set-Cookie",
                "bemanning_session=abc; Path=/; SameSite=lax; Secure",
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


def test_localize_set_cookie_removes_remote_only_attributes():
    cookie = localize_set_cookie(
        "bemanning_session=abc; Path=/; Domain=stigamo.nu; SameSite=lax; Secure"
    )

    assert "Secure" not in cookie
    assert "Domain=" not in cookie
    assert "bemanning_session=abc" in cookie


def test_local_app_server_serves_frontend_and_proxies_api(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<h1>Bemanning</h1>", encoding="utf-8")

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

        assert requests.get(local_url, timeout=5).text == "<h1>Bemanning</h1>"

        client = requests.Session()
        login = client.get(f"{local_url}api/login", timeout=5)
        assert login.status_code == 200
        assert "Secure" not in login.headers["Set-Cookie"]

        cookie_echo = client.get(f"{local_url}api/cookie", timeout=5).json()
        assert cookie_echo["cookie"] == "bemanning_session=abc"
    finally:
        if local is not None:
            local.stop()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=3)


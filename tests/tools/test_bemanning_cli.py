import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.routing import APIRoute

from app.backend.main import app
from tools import bemanning_cli


class CliTestHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):  # noqa: A002
        return

    def do_GET(self):  # noqa: N802
        if self.path == "/api/health":
            body = json.dumps({"status": "ok", "environment": "cli-test"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


def start_cli_test_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), CliTestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_cli_route_registry_covers_every_fastapi_api_route():
    app_routes = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/"):
            continue
        for method in route.methods or set():
            if method in {"HEAD", "OPTIONS"}:
                continue
            app_routes.add((method, route.path))

    cli_routes = {(route.method, route.path) for route in bemanning_cli.ROUTES}

    assert app_routes - cli_routes == set()


def test_cli_routes_outputs_markdown(capsys):
    result = bemanning_cli.main(["routes", "--format", "markdown"])
    output = capsys.readouterr().out

    assert result == 0
    assert "| `schedule.set_cell` | `PUT` | `/api/schedule/cell` |" in output
    assert "| `productivity.report` | `GET` | `/api/productivity` |" in output


def test_api_routes_document_covers_cli_routes():
    doc = (bemanning_cli.ROOT / "API_ROUTES.md").read_text(encoding="utf-8")

    for route in bemanning_cli.ROUTES:
        assert f"`{route.name}`" in doc
        assert f"`{route.path}`" in doc


def test_cli_can_call_generic_health_endpoint(tmp_path, capsys):
    server, thread = start_cli_test_server()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        result = bemanning_cli.main(
            [
                "--base-url",
                base_url,
                "--cookie-jar",
                str(tmp_path / "cookies.txt"),
                "api",
                "GET",
                "/api/health",
            ]
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    output = capsys.readouterr().out
    assert result == 0
    assert '"status": "ok"' in output


def test_cli_accepts_base_url_after_subcommand():
    args = bemanning_cli.parse_args(["api", "GET", "/api/health", "--base-url", "http://127.0.0.1:1"])

    assert args.base_url == "http://127.0.0.1:1"
    assert args.command == "api"

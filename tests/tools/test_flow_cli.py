import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.routing import APIRoute

from app.backend.main import app
from tools import flow_cli
from tools import visual_smoke


class CliTestHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):  # noqa: A002
        return

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/api/health":
            self._json({"status": "ok", "environment": "cli-test"})
            return
        if self.path == "/api/allokering/flows":
            self._json({"flows": [{"id": "split-values", "label": "Dela varden"}]})
            return
        if self.path == "/api/allokering/pool":
            self._json({"pool": [{"key": "orders", "label": "Detalj Kundorder"}]})
            return
        if self.path == "/api/allokering/download/abc/result":
            body = b"Kolumn 1,Kolumn 2\nA,C\nB,\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length:
            self.rfile.read(length)
        if self.path == "/api/allokering/detect":
            self._json({"file_type": "orders"})
            return
        if self.path == "/api/allokering/flow/split-values":
            self._json(
                {
                    "flow_id": "split-values",
                    "session_id": "abc",
                    "summary": {"Antal varden": 3},
                    "tables": [
                        {
                            "key": "result",
                            "label": "Delade varden",
                            "table": {"columns": ["Kolumn 1"], "rows": [["A"]], "row_count": 1},
                        }
                    ],
                    "log": [],
                }
            )
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

    cli_routes = {(route.method, route.path) for route in flow_cli.ROUTES}

    assert app_routes - cli_routes == set()


def test_cli_routes_outputs_markdown(capsys):
    result = flow_cli.main(["routes", "--format", "markdown"])
    output = capsys.readouterr().out

    assert result == 0
    assert "| `schedule.set_cell` | `PUT` | `/api/schedule/cell` |" in output
    assert "| `productivity.report` | `GET` | `/api/productivity` |" in output


def test_api_routes_document_covers_cli_routes():
    doc = (flow_cli.ROOT / "API_ROUTES.md").read_text(encoding="utf-8")

    for route in flow_cli.ROUTES:
        assert f"`{route.name}`" in doc
        assert f"`{route.path}`" in doc


def test_cli_can_call_generic_health_endpoint(tmp_path, capsys):
    server, thread = start_cli_test_server()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        result = flow_cli.main(
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
    args = flow_cli.parse_args(["api", "GET", "/api/health", "--base-url", "http://127.0.0.1:1"])

    assert args.base_url == "http://127.0.0.1:1"
    assert args.command == "api"


def test_cli_command_groups_work_against_local_app(tmp_path, capsys):
    base_url, server = visual_smoke.start_local_server(tmp_path)
    cookie_jar = tmp_path / "cli-cookies.txt"
    common = ["--base-url", base_url, "--cookie-jar", str(cookie_jar)]
    try:
        assert flow_cli.main([*common, "routes", "--format", "json"]) == 0
        assert flow_cli.main([*common, "call", "health"]) == 0
        assert flow_cli.main(
            [*common, "auth", "login", "--username", "admin", "--password", "admin123"]
        ) == 0
        assert flow_cli.main([*common, "auth", "me"]) == 0
        assert flow_cli.main([*common, "api", "GET", "/api/activities"]) == 0
        assert flow_cli.main([*common, "auth", "logout"]) == 0
    finally:
        server.close()

    output = capsys.readouterr().out
    assert '"status": "ok"' in output
    assert '"username": "admin"' in output
    assert "GG Plock" in output


def test_cli_allocation_aliases_can_run_and_download_results(tmp_path, capsys):
    server, thread = start_cli_test_server()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        common = ["--base-url", base_url, "--cookie-jar", str(tmp_path / "cookies.txt")]
        assert flow_cli.main([*common, "allocation", "flows"]) == 0
        result = flow_cli.main(
            [
                *common,
                "allocation",
                "run",
                "split-values",
                "--param",
                "values=A\nB\nC",
                "--out",
                str(tmp_path / "out"),
                "--json",
            ]
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    output = capsys.readouterr().out
    assert result == 0
    assert '"session_id": "abc"' in output
    assert '"downloads"' in output
    assert (tmp_path / "out" / "result.csv").read_text(encoding="utf-8") == "Kolumn 1,Kolumn 2\nA,C\nB,\n"


def test_cli_db_lookup_finds_hidden_people_users_and_activities(tmp_path, capsys):
    db_path = tmp_path / "lookup.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            create table areas (
                id integer primary key,
                name text not null
            );
            create table users (
                id integer primary key,
                username text not null,
                display_name text,
                role text not null,
                area_id integer,
                is_active integer not null
            );
            create table activities (
                id integer primary key,
                code text not null,
                label text not null,
                category text not null,
                area_id integer,
                summary_activity_id integer,
                is_active integer not null
            );
            create table persons (
                id integer primary key,
                name text not null,
                home_area_id integer,
                home_activity_id integer,
                is_active integer not null
            );
            insert into areas (id, name) values (1, 'Mestergruppen');
            insert into activities (id, code, label, category, area_id, summary_activity_id, is_active)
            values (1, 'MG_PLOCK', 'MG Plock', 'work', 1, null, 1);
            insert into users (id, username, display_name, role, area_id, is_active)
            values (1, 'antonh', 'Anton Holmqvist', 'leader', 1, 0);
            insert into persons (id, name, home_area_id, home_activity_id, is_active)
            values (1, 'Anton Holmqvist', 1, 1, 0);
            """
        )

    database_url = f"sqlite:///{db_path.as_posix()}"
    result = flow_cli.main(
        [
            "db",
            "lookup",
            "all",
            "--database-url",
            database_url,
            "--q",
            "Anton Holmqvist",
            "--json",
        ]
    )
    output = capsys.readouterr().out

    assert result == 0
    payload = json.loads(output)
    assert payload["count"] == 2
    assert {row["type"] for row in payload["results"]} == {"person", "user"}
    assert all(row["is_active"] == 0 for row in payload["results"])

    active_result = flow_cli.main(
        [
            "db",
            "lookup",
            "all",
            "--database-url",
            database_url,
            "--q",
            "Anton Holmqvist",
            "--active-only",
        ]
    )
    active_output = capsys.readouterr().out

    assert active_result == 1
    assert "Inga traffar." in active_output

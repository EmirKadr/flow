import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tools.desktop_app_probe import run_shell_probe


class ProbeUpstreamHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):  # noqa: A002
        return

    def do_GET(self):  # noqa: N802
        if self.path == "/api/health":
            body = json.dumps({"status": "ok", "environment": "probe-test"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


def start_probe_upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProbeUpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_desktop_app_probe_exercises_local_app_server_and_writes_screenshots(tmp_path):
    upstream, thread = start_probe_upstream()
    try:
        base_url = f"http://127.0.0.1:{upstream.server_address[1]}"
        steps = run_shell_probe(output_dir=tmp_path, base_url=base_url)
    finally:
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=3)

    names = [step.name for step in steps]
    assert names == ["desktop_loading", "desktop_error", "desktop_loaded_shell"]
    assert steps[-1].detail.startswith("http://127.0.0.1:")
    assert f"-> {base_url}" in steps[-1].detail

    for step in steps:
        assert step.screenshot
        assert (tmp_path / step.screenshot).is_file()


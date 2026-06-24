import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tools.rfid_serial_bridge import (
    RfidScan,
    build_parser,
    console_text,
    parse_scan_line,
    post_scan,
    scan_payload,
    serial_open_error_message,
    should_post_scan,
)


def test_parse_scan_line_with_module_from_esp32_output():
    scan = parse_scan_line(
        "[MG Plock] RFID HEX=00a1b2c3 DEC=10597059 count=75",
        default_module_name="Fallback",
    )

    assert scan == RfidScan(
        module_name="MG Plock",
        tag_hex="00A1B2C3",
        tag_dec="10597059",
        scan_count=75,
    )


def test_parse_scan_line_uses_default_module_for_plain_output():
    scan = parse_scan_line("RFID HEX=ABC123 DEC=12345 count=2", default_module_name="MG Plock")

    assert scan == RfidScan(
        module_name="MG Plock",
        tag_hex="ABC123",
        tag_dec="12345",
        scan_count=2,
    )


def test_parse_scan_line_can_force_default_module():
    scan = parse_scan_line(
        "[MG Plock] RFID HEX=ABC123 DEC=12345 count=2",
        default_module_name="MG VM",
        force_module_name=True,
    )

    assert scan == RfidScan(
        module_name="MG VM",
        tag_hex="ABC123",
        tag_dec="12345",
        scan_count=2,
    )


def test_parse_scan_line_ignores_non_scan_output():
    assert parse_scan_line("POST http://example.test/api/rfid/scans -> HTTP -1", default_module_name="MG Plock") is None


def test_scan_payload_matches_rfid_api_contract():
    payload = scan_payload(
        RfidScan(module_name="MG Plock", tag_hex="00A1B2C3", tag_dec="10597059", scan_count=7),
        device_id="usb-rfid-bridge",
    )

    assert payload == {
        "device_id": "usb-rfid-bridge",
        "module_name": "MG Plock",
        "tag_hex": "00A1B2C3",
        "tag_dec": "10597059",
        "scan_count": 7,
    }


def test_serial_open_error_explains_locked_port():
    message = serial_open_error_message("COM9", "PermissionError(13, 'Åtkomst nekad.', None, 5)")

    assert "COM9" in message
    assert "Arduino Serial Monitor" in message
    assert "starta sedan bryggan igen" in message


def test_parser_supports_retry_open_for_autostart():
    args = build_parser().parse_args(["--port", "COM10", "--retry-open", "--retry-delay", "0.2"])

    assert args.port == "COM10"
    assert args.retry_open is True
    assert args.retry_delay == 0.2
    assert args.dedupe_window == 3.0


def test_bridge_dedupes_same_tag_on_same_module_inside_window():
    recent = {}
    scan = RfidScan(module_name="MG Plock", tag_hex="00A1B2C3", tag_dec="10597059", scan_count=1)

    assert should_post_scan(scan, device_id="usb-rfid-mg-plock", now=10.0, recent_scans=recent, dedupe_window=3.0) is True
    assert should_post_scan(scan, device_id="usb-rfid-mg-plock", now=11.0, recent_scans=recent, dedupe_window=3.0) is False
    assert should_post_scan(scan, device_id="usb-rfid-mg-plock", now=14.1, recent_scans=recent, dedupe_window=3.0) is True

    other_module = RfidScan(module_name="MG VM", tag_hex="00A1B2C3", tag_dec="10597059", scan_count=2)
    other_tag = RfidScan(module_name="MG Plock", tag_hex="00FFFEEE", tag_dec="16776942", scan_count=3)
    assert should_post_scan(other_module, device_id="usb-rfid-mg-plock", now=14.2, recent_scans=recent, dedupe_window=3.0) is True
    assert should_post_scan(other_tag, device_id="usb-rfid-mg-plock", now=14.3, recent_scans=recent, dedupe_window=3.0) is True


def test_console_text_replaces_unprintable_serial_noise(monkeypatch):
    class Stdout:
        encoding = "cp1252"

    monkeypatch.setattr("sys.stdout", Stdout())

    assert console_text("\ufffd boot") == "? boot"


def test_post_scan_posts_json_and_optional_token_to_local_backend():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            requests.append(
                {
                    "path": self.path,
                    "token": self.headers.get("X-Flow-RFID-Token"),
                    "body": body,
                }
            )
            self.send_response(201)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, format, *args):  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        status = post_scan(
            base_url,
            {"device_id": "usb-rfid-bridge", "module_name": "MG Plock", "tag_hex": "ABC", "tag_dec": "123"},
            token="test-token",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 201
    assert requests == [
        {
            "path": "/api/rfid/scans",
            "token": "test-token",
            "body": {
                "device_id": "usb-rfid-bridge",
                "module_name": "MG Plock",
                "tag_hex": "ABC",
                "tag_dec": "123",
            },
        }
    ]

"""Tester för desktop-serverns multipart-parsning.

Skyddar Python 3.13-migreringen bort från cgi.FieldStorage: fält, filuppladdning,
tomma värden och icke-multipart-kroppar ska bete sig som tidigare.
"""
import io
from pathlib import Path

from desktop.local_runtime import parse_multipart


class _FakeHeaders(dict):
    def get(self, key, default=None):  # BaseHTTPRequestHandler.headers.get är case-insensitive
        for existing, value in self.items():
            if existing.lower() == key.lower():
                return value
        return default


class _FakeHandler:
    def __init__(self, body: bytes, content_type: str):
        self.rfile = io.BytesIO(body)
        self.headers = _FakeHeaders(
            {
                "Content-Type": content_type,
                "Content-Length": str(len(body)),
            }
        )
        self.command = "POST"


def _multipart_body(boundary: str) -> bytes:
    parts = [
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="flow_id"\r\n\r\n'
        "allocation_split\r\n",
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="blank_field"\r\n\r\n'
        "   \r\n",
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="details"; filename="detaljer.csv"\r\n'
        "Content-Type: text/csv\r\n\r\n"
        "ordernr;artikel\r\n123;A-1\r\n",
        f"--{boundary}--\r\n",
    ]
    return "".join(parts).encode("utf-8")


def test_parse_multipart_extracts_fields_and_uploads(tmp_path):
    boundary = "flowtestboundary"
    handler = _FakeHandler(
        _multipart_body(boundary),
        f"multipart/form-data; boundary={boundary}",
    )

    fields, uploads, temp_paths = parse_multipart(handler)

    try:
        assert fields == {"flow_id": "allocation_split"}
        assert set(uploads) == {"details"}
        upload_path = uploads["details"]
        assert upload_path.suffix == ".csv"
        # Byte-exakt: CRLF i filinnehallet far inte normaliseras till LF.
        assert upload_path.read_bytes() == b"ordernr;artikel\r\n123;A-1"
        assert temp_paths == [upload_path]
    finally:
        for path in temp_paths:
            Path(path).unlink(missing_ok=True)


def test_parse_multipart_preserves_binary_upload_bytes():
    boundary = "binboundary"
    binary_content = b"PK\x03\x04\x00\r\n\x1a\n\x00\xff\xfe\r\nrest"
    head = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="workbook"; filename="data.xlsx"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    )
    body = (
        head.encode("latin-1")
        + binary_content
        + f"\r\n--{boundary}--\r\n".encode("latin-1")
    )
    handler = _FakeHandler(body, f"multipart/form-data; boundary={boundary}")

    fields, uploads, temp_paths = parse_multipart(handler)

    try:
        assert set(uploads) == {"workbook"}
        assert uploads["workbook"].suffix == ".xlsx"
        assert uploads["workbook"].read_bytes() == binary_content
    finally:
        for path in temp_paths:
            Path(path).unlink(missing_ok=True)


def test_parse_multipart_ignores_non_multipart_body():
    handler = _FakeHandler(b'{"key": "value"}', "application/json")

    fields, uploads, temp_paths = parse_multipart(handler)

    assert fields == {}
    assert uploads == {}
    assert temp_paths == []


def test_parse_multipart_handles_missing_content_length():
    handler = _FakeHandler(b"", "multipart/form-data; boundary=x")
    handler.headers = _FakeHeaders({"Content-Type": "multipart/form-data; boundary=x"})

    fields, uploads, temp_paths = parse_multipart(handler)

    assert fields == {}
    assert uploads == {}
    assert temp_paths == []


def test_desktop_runtime_does_not_import_removed_cgi_module():
    source = (Path(__file__).resolve().parents[2] / "desktop" / "local_runtime.py").read_text(
        encoding="utf-8"
    )
    assert "import cgi" not in source

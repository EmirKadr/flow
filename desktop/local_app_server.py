"""Local desktop app surface with a proxy to the central API."""
from __future__ import annotations

import mimetypes
import json
import sys
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urljoin, urlsplit

import requests

from core.app_info import DESKTOP_LOCAL_HOST, DESKTOP_LOCAL_PORT, SERVER_BASE_URL


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

RESPONSE_HEADERS_TO_REWRITE = {
    "content-encoding",
    "content-length",
    "set-cookie",
    "transfer-encoding",
}


def default_frontend_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "app" / "frontend"


def _set_cookie_values(response: requests.Response) -> list[str]:
    raw_headers = getattr(getattr(response, "raw", None), "headers", None)
    if hasattr(raw_headers, "getlist"):
        values = raw_headers.getlist("Set-Cookie")
        if values:
            return list(values)
    if hasattr(raw_headers, "get_all"):
        values = raw_headers.get_all("Set-Cookie")
        if values:
            return list(values)
    value = response.headers.get("Set-Cookie")
    return [value] if value else []


def localize_set_cookie(value: str) -> str:
    parts = []
    for part in value.split(";"):
        stripped = part.strip()
        lowered = stripped.lower()
        if lowered == "secure":
            continue
        if lowered.startswith("domain="):
            continue
        parts.append(stripped)
    return "; ".join(parts)


def _iter_forward_request_headers(headers) -> Iterable[tuple[str, str]]:
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP_HEADERS or lowered == "host":
            continue
        yield key, value


def _clear_session_cookies(session: requests.Session) -> None:
    cookies = getattr(session, "cookies", None)
    if cookies is not None and hasattr(cookies, "clear"):
        cookies.clear()


def make_handler(frontend_dir: Path, upstream_base_url: str, session: requests.Session):
    frontend_root = frontend_dir.resolve()
    upstream_root = upstream_base_url.rstrip("/") + "/"

    class LocalAppRequestHandler(BaseHTTPRequestHandler):
        server_version = "BemanningLocalApp/1.0"

        def log_message(self, _format: str, *_args) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:  # noqa: N802
            self._handle_request(with_body=False)

        def do_HEAD(self) -> None:  # noqa: N802
            self._handle_request(with_body=False, head_only=True)

        def do_POST(self) -> None:  # noqa: N802
            self._handle_request(with_body=True)

        def do_PUT(self) -> None:  # noqa: N802
            self._handle_request(with_body=True)

        def do_DELETE(self) -> None:  # noqa: N802
            self._handle_request(with_body=False)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._handle_request(with_body=False)

        def _handle_request(self, *, with_body: bool, head_only: bool = False) -> None:
            parsed = urlsplit(self.path)
            if parsed.path == "/api" or parsed.path.startswith("/api/"):
                self._proxy_api(parsed, with_body=with_body, head_only=head_only)
                return
            self._serve_static(parsed.path, head_only=head_only)

        def _serve_static(self, raw_path: str, *, head_only: bool = False) -> None:
            path = unquote(raw_path or "/")
            relative = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (frontend_root / relative).resolve()
            if not target.is_file() or not target.is_relative_to(frontend_root):
                self._send_text(404, "Sidan hittades inte.")
                return

            body = b"" if head_only else target.read_bytes()
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(target.stat().st_size if head_only else len(body)))
            self.end_headers()
            if not head_only:
                self.wfile.write(body)

        def _proxy_api(self, parsed, *, with_body: bool, head_only: bool = False) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if with_body and length else None
            upstream_url = urljoin(upstream_root, parsed.path.lstrip("/"))
            if parsed.query:
                upstream_url = f"{upstream_url}?{parsed.query}"

            headers = dict(_iter_forward_request_headers(self.headers))
            try:
                _clear_session_cookies(session)
                response = session.request(
                    self.command,
                    upstream_url,
                    data=body,
                    headers=headers,
                    allow_redirects=False,
                    timeout=(8, 180),
                )
                _clear_session_cookies(session)
            except requests.RequestException as exc:
                self._send_json(502, f"Kunde inte na central server: {exc}")
                return

            content = b"" if head_only else response.content
            self.send_response(response.status_code)
            for key, value in response.headers.items():
                lowered = key.lower()
                if lowered in HOP_BY_HOP_HEADERS or lowered in RESPONSE_HEADERS_TO_REWRITE:
                    continue
                self.send_header(key, value)
            for cookie in _set_cookie_values(response):
                self.send_header("Set-Cookie", localize_set_cookie(cookie))
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if not head_only:
                self.wfile.write(content)

        def _send_json(self, status_code: int, detail: str) -> None:
            body = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, status_code: int, text: str) -> None:
            body = text.encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return LocalAppRequestHandler


@dataclass
class LocalAppServer:
    upstream_base_url: str = SERVER_BASE_URL
    frontend_dir: Path | None = None
    host: str = DESKTOP_LOCAL_HOST
    preferred_port: int = DESKTOP_LOCAL_PORT

    def __post_init__(self) -> None:
        self.frontend_dir = (self.frontend_dir or default_frontend_dir()).resolve()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._session = requests.Session()

    @property
    def url(self) -> str:
        if not self._httpd:
            return f"http://{self.host}:{self.preferred_port}/"
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}/"

    def start(self) -> str:
        if self._httpd:
            return self.url
        if not self.frontend_dir or not self.frontend_dir.is_dir():
            raise RuntimeError(f"Frontend saknas: {self.frontend_dir}")

        handler = make_handler(
            frontend_dir=self.frontend_dir,
            upstream_base_url=self.upstream_base_url,
            session=self._session,
        )
        self._httpd = self._bind_server(handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="BemanningLocalAppServer",
            daemon=True,
        )
        self._thread.start()
        return self.url

    def _bind_server(self, handler) -> ThreadingHTTPServer:
        ports = [self.preferred_port]
        if self.preferred_port != 0:
            ports.append(0)
        last_error: OSError | None = None
        for port in ports:
            try:
                return ReusableThreadingHTTPServer((self.host, port), handler)
            except OSError as exc:
                last_error = exc
        raise RuntimeError(f"Kunde inte starta lokal appserver: {last_error}") from last_error

    def stop(self) -> None:
        if not self._httpd:
            return
        httpd = self._httpd
        self._httpd = None
        httpd.shutdown()
        httpd.server_close()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None
        self._session.close()

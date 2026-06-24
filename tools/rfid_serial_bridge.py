"""Bridge ESP32 RFID serial output to a local Flow backend.

This is the no-admin fallback for machines where Windows firewall blocks LAN
posts from the ESP32. The ESP32 stays connected over USB, this process reads
the serial monitor line and posts the scan to localhost.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request


SCAN_LINE_RE = re.compile(
    r"(?:\[(?P<module>[^\]]+)\]\s*)?"
    r"RFID\s+HEX=(?P<tag_hex>[0-9a-f]+)\s+DEC=(?P<tag_dec>\d+)\s+count=(?P<count>\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RfidScan:
    module_name: str
    tag_hex: str
    tag_dec: str
    scan_count: int


def console_text(value: str) -> str:
    encoding = sys.stdout.encoding or "utf-8"
    return str(value).encode(encoding, errors="replace").decode(encoding, errors="replace")


def parse_scan_line(line: str, *, default_module_name: str, force_module_name: bool = False) -> RfidScan | None:
    match = SCAN_LINE_RE.search(line or "")
    if match is None:
        return None
    module_name = (
        default_module_name
        if force_module_name
        else match.group("module") or default_module_name or ""
    ).strip()
    if not module_name:
        return None
    return RfidScan(
        module_name=module_name,
        tag_hex=match.group("tag_hex").upper(),
        tag_dec=match.group("tag_dec"),
        scan_count=int(match.group("count")),
    )


def scan_payload(scan: RfidScan, *, device_id: str) -> dict[str, Any]:
    return {
        "device_id": device_id,
        "module_name": scan.module_name,
        "tag_hex": scan.tag_hex,
        "tag_dec": scan.tag_dec,
        "scan_count": scan.scan_count,
    }


def scan_dedupe_key(scan: RfidScan, *, device_id: str) -> tuple[str, str, str]:
    return (str(device_id or "").strip().lower(), scan.module_name.strip().lower(), scan.tag_hex.strip().upper())


def should_post_scan(
    scan: RfidScan,
    *,
    device_id: str,
    now: float,
    recent_scans: dict[tuple[str, str, str], float],
    dedupe_window: float,
) -> bool:
    if dedupe_window <= 0:
        return True
    key = scan_dedupe_key(scan, device_id=device_id)
    previous = recent_scans.get(key)
    recent_scans[key] = now
    return previous is None or now - previous >= dedupe_window


def prune_scan_dedupe_cache(recent_scans: dict[tuple[str, str, str], float], *, now: float, dedupe_window: float) -> None:
    if dedupe_window <= 0 or len(recent_scans) < 200:
        return
    cutoff = now - max(dedupe_window * 4, 30)
    stale = [key for key, seen_at in recent_scans.items() if seen_at < cutoff]
    for key in stale:
        recent_scans.pop(key, None)


def post_scan(base_url: str, payload: dict[str, Any], *, token: str = "", timeout: float = 8.0) -> int:
    url = base_url.rstrip("/") + "/api/rfid/scans"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Flow-RFID-Token"] = token
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            response.read()
            return int(response.status)
    except error.HTTPError as exc:
        exc.read()
        return int(exc.code)


def _open_serial(port: str, baud: int):
    try:
        import serial
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "pyserial saknas. Installera utan admin med: python -m pip install --user pyserial"
        ) from exc
    try:
        return serial.Serial(port, baudrate=baud, timeout=1)
    except serial.SerialException as exc:
        raise OSError(serial_open_error_message(port, str(exc))) from exc


def serial_open_error_message(port: str, error_text: str) -> str:
    if "Access is denied" in error_text or "Åtkomst nekad" in error_text or "PermissionError" in error_text:
        return (
            f"Kunde inte oppna {port}: porten ar upptagen eller blockerad. "
            "Stang Arduino Serial Monitor/Serial Plotter och andra program som kan lasa ESP32-porten, "
            "och starta sedan bryggan igen."
        )
    return f"Kunde inte oppna {port}: {error_text}"


def _list_ports() -> int:
    try:
        from serial.tools import list_ports
    except ModuleNotFoundError:
        print("pyserial saknas. Installera utan admin med: python -m pip install --user pyserial")
        return 2
    ports = list(list_ports.comports())
    if not ports:
        print("Inga serieportar hittades.")
        return 1
    for item in ports:
        print(f"{item.device}\t{item.description}")
    return 0


def run(args: argparse.Namespace) -> int:
    if args.list_ports:
        return _list_ports()
    if not args.port:
        print("Ange serieport, till exempel --port COM5, eller kor --list-ports.", file=sys.stderr)
        return 2
    token = args.token or os.environ.get("RFID_DEVICE_TOKEN", "")
    print(
        f"Lyssnar pa {args.port} @ {args.baud}. "
        f"Postar till {args.base_url.rstrip('/')}/api/rfid/scans. "
        "Stang Arduino Serial Monitor medan bryggan kor."
    )
    recent_scans: dict[tuple[str, str, str], float] = {}
    while True:
        try:
            with _open_serial(args.port, args.baud) as serial_port:
                while True:
                    raw_line = serial_port.readline()
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if args.echo:
                        print(console_text(line))
                    scan = parse_scan_line(
                        line,
                        default_module_name=args.module_name,
                        force_module_name=args.force_module_name,
                    )
                    if scan is None:
                        continue
                    now = time.monotonic()
                    if not should_post_scan(
                        scan,
                        device_id=args.device_id,
                        now=now,
                        recent_scans=recent_scans,
                        dedupe_window=args.dedupe_window,
                    ):
                        continue
                    prune_scan_dedupe_cache(recent_scans, now=now, dedupe_window=args.dedupe_window)
                    payload = scan_payload(scan, device_id=args.device_id)
                    if args.dry_run:
                        print(f"RFID {scan.module_name} #{scan.scan_count}: dry-run {json.dumps(payload, sort_keys=True)}")
                        continue
                    try:
                        status = post_scan(args.base_url, payload, token=token, timeout=args.timeout)
                        print(f"RFID {scan.module_name} #{scan.scan_count} -> HTTP {status}")
                    except OSError as exc:
                        print(f"RFID {scan.module_name} #{scan.scan_count} -> FEL {exc}", file=sys.stderr)
        except OSError as exc:
            if not args.retry_open:
                raise SystemExit(str(exc)) from exc
            print(f"{exc} Forsoker igen om {args.retry_delay} sekunder.", file=sys.stderr, flush=True)
            time.sleep(args.retry_delay)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Las RFID-scans fran ESP32 USB-serieport och posta till Flow.")
    parser.add_argument("--port", help="Serieport, till exempel COM5.")
    parser.add_argument("--list-ports", action="store_true", help="Visa tillgangliga serieportar och avsluta.")
    parser.add_argument("--baud", type=int, default=115200, help="Baudrate for ESP32 serial output.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Flow-backend, normalt localhost.")
    parser.add_argument("--device-id", default="usb-rfid-bridge", help="Device-id som sparas i Flow.")
    parser.add_argument("--module-name", default="MG Plock", help="Fallback-modul om serialraden saknar [modul].")
    parser.add_argument("--force-module-name", action="store_true", help="Anvand --module-name aven om serialraden innehaller [modul].")
    parser.add_argument("--token", default="", help="RFID device-token. Kan ocksa lasas fran RFID_DEVICE_TOKEN.")
    parser.add_argument("--timeout", type=float, default=8.0, help="HTTP-timeout i sekunder.")
    parser.add_argument("--retry-open", action="store_true", help="Forsok oppna serieporten igen om den ar upptagen.")
    parser.add_argument("--retry-delay", type=float, default=5.0, help="Sekunder mellan forsok med --retry-open.")
    parser.add_argument("--dedupe-window", type=float, default=3.0, help="Sekunder dar samma tagg pa samma modul filtreras bort innan POST.")
    parser.add_argument("--dry-run", action="store_true", help="Tolka serialrader utan att posta till Flow.")
    parser.add_argument("--echo", action="store_true", help="Skriv ut alla inkommande serialrader.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())

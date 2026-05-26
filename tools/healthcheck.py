"""Health and wait-time diagnostics for flow.

Examples:
  python -m tools.healthcheck report --local
  python -m tools.healthcheck waits --local --period 24h
  python -m tools.healthcheck report --base-url https://stigamo.nu --username admin --password ***
"""
from __future__ import annotations

import argparse
import json
import sys
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COOKIE_JAR = ROOT / ".flow-cli-cookies.txt"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_cookie_jar(path: Path) -> MozillaCookieJar:
    jar = MozillaCookieJar(str(path))
    if path.exists():
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass
    return jar


def session_for(args: argparse.Namespace) -> requests.Session:
    session = requests.Session()
    session.cookies = load_cookie_jar(args.cookie_jar)
    if args.username:
        response = session.post(
            f"{args.base_url.rstrip('/')}/api/auth/login",
            json={"username": args.username, "password": args.password or ""},
            timeout=20,
        )
        response.raise_for_status()
        session.cookies.save(ignore_discard=True, ignore_expires=True)
    return session


def get_remote(args: argparse.Namespace, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not args.base_url:
        raise SystemExit("--base-url kravs for remote healthcheck")
    session = session_for(args)
    clean_params = {key: value for key, value in (params or {}).items() if value is not None}
    response = session.get(f"{args.base_url.rstrip('/')}{path}", params=clean_params, timeout=args.timeout)
    response.raise_for_status()
    return response.json()


def local_report(args: argparse.Namespace) -> dict[str, Any]:
    from app.backend.database import SessionLocal
    from app.backend.healthcheck_service import run_healthcheck

    db = SessionLocal()
    try:
        return run_healthcheck(db=db, include_render=args.include_render, base_url=args.public_url)
    finally:
        db.close()


def local_waits(args: argparse.Namespace) -> dict[str, Any]:
    from app.backend.database import SessionLocal
    from app.backend.routers.healthcheck import wait_metrics_summary

    db = SessionLocal()
    try:
        return wait_metrics_summary(period=args.period, limit=args.limit, user_id=args.user_id, q=args.query, db=db, _=None)
    except Exception as exc:
        return {
            "period": args.period,
            "count": 0,
            "avg_ms": 0,
            "p95_ms": 0,
            "max_ms": 0,
            "by_target": [],
            "slow_events": [],
            "analysis": [{"severity": "error", "message": f"Kunde inte lasa vantetider: {exc}"}],
        }
    finally:
        db.close()


def print_report(report: dict[str, Any]) -> None:
    print(f"Status: {str(report.get('status') or '-').upper()}")
    database = report.get("database") or {}
    if database:
        print(f"Databas: {database.get('dialect', '-')} {database.get('latency_ms', '-')} ms")
    print("\nKontroller")
    for item in report.get("checks") or []:
        print(f"- {item.get('status', '-').upper():7} {item.get('name', '-')}: {item.get('message', '-')}")
    print("\nRekommendationer")
    for item in report.get("recommendations") or []:
        print(f"- {item.get('severity', '-').upper():7} {item.get('message', '-')}")


def print_waits(summary: dict[str, Any]) -> None:
    print(f"Matningar: {summary.get('count', 0)}")
    print(f"Snitt: {summary.get('avg_ms', 0)} ms")
    print(f"P95: {summary.get('p95_ms', 0)} ms")
    print("\nTyngsta steg")
    for item in (summary.get("by_target") or [])[:10]:
        print(f"- {item.get('key', '-')}: p95 {item.get('p95_ms', 0)} ms, n={item.get('count', 0)}")
    print("\nAnalys")
    for item in summary.get("analysis") or []:
        print(f"- {item.get('severity', '-').upper():7} {item.get('message', '-')}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("report", "waits"), nargs="?", default="report")
    parser.add_argument("--local", action="store_true", help="Kor mot lokal databas direkt.")
    parser.add_argument("--base-url", help="Remote flow-bas-URL, t.ex. https://stigamo.nu.")
    parser.add_argument("--cookie-jar", type=Path, default=DEFAULT_COOKIE_JAR)
    parser.add_argument("--username", help="Logga in innan remote-anrop.")
    parser.add_argument("--password", help="Losenord for --username.")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--json", action="store_true", help="Skriv full JSON.")
    parser.add_argument("--no-render", dest="include_render", action="store_false", help="Hoppa over Render API.")
    parser.add_argument("--public-url", help="Publik URL for lokal extern ping.")
    parser.add_argument("--period", default="24h", choices=("1h", "24h", "7d", "30d", "all"))
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--user-id", type=int)
    parser.add_argument("--query", help="Filtrera vantetider pa vy/steg/event.")
    parser.set_defaults(include_render=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.local:
        payload = local_waits(args) if args.command == "waits" else local_report(args)
    elif args.command == "waits":
        payload = get_remote(args, "/api/healthcheck/wait-metrics/summary", {
            "period": args.period,
            "limit": args.limit,
            "user_id": args.user_id,
            "q": args.query,
        })
    else:
        payload = get_remote(args, "/api/healthcheck", {"include_render": args.include_render})

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    elif args.command == "waits":
        print_waits(payload)
    else:
        print_report(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

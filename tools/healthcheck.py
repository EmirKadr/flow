"""Health and wait-time diagnostics for flow.

Examples:
  python -m tools.healthcheck report --local
  python -m tools.healthcheck report --local --skip-db
  python -m tools.healthcheck waits --local --period 24h
  python -m tools.healthcheck report --base-url https://stigamo.nu --username admin --password ***
  python -m tools.healthcheck duckdb --local
  python -m tools.healthcheck duckdb --base-url https://flow-development.nowastelogistics.com --username admin --password ***

`duckdb` ar matpunkten for optimeringskandidat #08: den visar vilka defaults DuckDB
faktiskt valde (threads/memory_limit) och jamfor dem med poddens cgroup-limits.
Utan --local hamtas siffrorna ur den KORANDE poddens `GET /api/healthcheck`, vilket
ar det enda sattet att lasa dem utan kubectl-atkomst.
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
    from app.backend.healthcheck_service import run_healthcheck

    if args.skip_db:
        return run_healthcheck(db=None, base_url=args.public_url)

    from app.backend.database import SessionLocal

    db = SessionLocal()
    try:
        return run_healthcheck(db=db, base_url=args.public_url)
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


def local_duckdb(_args: argparse.Namespace) -> dict[str, Any]:
    from app.backend.duckdb_diagnostics import duckdb_diagnostics

    return duckdb_diagnostics()


def remote_duckdb(args: argparse.Namespace) -> dict[str, Any]:
    """Poddens DuckDB-defaults via den befintliga Super User-healthchecken (ingen kubectl behovs)."""
    report = get_remote(args, "/api/healthcheck")
    duckdb = report.get("duckdb")
    if not isinstance(duckdb, dict) or not duckdb:
        raise SystemExit(
            "Svaret saknar duckdb-blocket. Kor miljon en version som har matpunkten? "
            "(GET /api/healthcheck ska ha ett 'duckdb'-falt.)"
        )
    return duckdb


def print_duckdb(report: dict[str, Any]) -> None:
    settings = report.get("settings") or {}
    cgroup = report.get("cgroup") or {}
    host = report.get("host") or {}
    print(f"DuckDB-version: {report.get('version') or '-'}")
    print(f"Kalla: {report.get('source') or '-'}")
    print("\nInstallningar (current_setting)")
    for name in ("threads", "memory_limit", "external_threads", "temp_directory"):
        if name in settings:
            print(f"- {name:16} {settings.get(name)}")
    print("\nPoddens/maskinens verklighet")
    print(f"- cgroup          {cgroup.get('version') or 'ingen hittad'}")
    print(f"- cpu_limit       {cgroup.get('cpu_limit_cores') if cgroup.get('cpu_limit_cores') is not None else '-'} karnor")
    memory_limit = cgroup.get("memory_limit_bytes")
    print(f"- memory_limit    {round(memory_limit / 1024**3, 2) if memory_limit else '-'} GiB")
    print(f"- nodens karnor   {host.get('cpu_count')} (affinity: {host.get('affinity_cpus')})")
    total = host.get("memory_total_bytes")
    print(f"- nodens RAM      {round(total / 1024**3, 1) if total else '-'} GiB")
    print("\nBedomning")
    for item in report.get("verdicts") or []:
        print(f"- {str(item.get('status') or '-').upper():7} {item.get('message', '-')}")
    if report.get("error"):
        print(f"\nFel: {report['error']}")


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
    parser.add_argument("command", choices=("report", "waits", "duckdb"), nargs="?", default="report")
    parser.add_argument("--local", action="store_true", help="Kor mot lokal databas direkt.")
    parser.add_argument("--base-url", help="Remote flow-bas-URL, t.ex. https://stigamo.nu.")
    parser.add_argument("--cookie-jar", type=Path, default=DEFAULT_COOKIE_JAR)
    parser.add_argument("--username", help="Logga in innan remote-anrop.")
    parser.add_argument("--password", help="Losenord for --username.")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--json", action="store_true", help="Skriv full JSON.")
    parser.add_argument("--skip-db", action="store_true", help="Hoppa over lokal databaskoppling.")
    parser.add_argument("--public-url", help="Publik URL for lokal extern ping.")
    parser.add_argument("--period", default="24h", choices=("1h", "24h", "7d", "30d", "all"))
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--user-id", type=int)
    parser.add_argument("--query", help="Filtrera vantetider pa vy/steg/event.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        # Windows-konsolen ar cp1252: annars blir a/a/o i bedomningstexterna sopor.
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass
    args = parse_args(argv)
    if args.local:
        if args.command == "waits":
            payload = local_waits(args)
        elif args.command == "duckdb":
            payload = local_duckdb(args)
        else:
            payload = local_report(args)
    elif args.command == "waits":
        payload = get_remote(args, "/api/healthcheck/wait-metrics/summary", {
            "period": args.period,
            "limit": args.limit,
            "user_id": args.user_id,
            "q": args.query,
        })
    elif args.command == "duckdb":
        payload = remote_duckdb(args)
    else:
        payload = get_remote(args, "/api/healthcheck")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    elif args.command == "waits":
        print_waits(payload)
    elif args.command == "duckdb":
        print_duckdb(payload)
    else:
        print_report(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

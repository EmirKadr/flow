"""Before/after-benchmark av API-endpoints mot en körande flow-miljö.

Loggar in, mäter varje endpoint N gånger och skriver en JSON-rapport som kan
jämföras med en tidigare körning via --compare. Används före och efter varje
prestandapåverkande ändring så effekten blir mätbar istället för gissad
(regel i AGENTS.md).

Exempel:
    # Baslinje fore andring
    python -m tools.api_benchmark --base-url https://flow-development.nowastelogistics.com \
        --username emikad --password *** --label fore-pool-fix

    # Efter andring: jamfor direkt mot baslinjen
    python -m tools.api_benchmark --base-url ... --username ... --password *** \
        --label efter-pool-fix --compare artifacts/api_benchmark/fore-pool-fix.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

import requests

# Kärnendpoints som speglar de mest använda vyerna. Frågetunga och lätta
# blandade med flit: skillnaden mellan dem avslöjar per-fråga-latens.
DEFAULT_ENDPOINTS = (
    "/api/areas",
    "/api/activities",
    "/api/persons",
    "/api/schedule?year=2026&week=27&weekday=5",
    "/api/schedule/summary?year=2026&week=27&weekday=5",
    "/api/overview?year=2026&week=27",
)


def measure(session: requests.Session, base_url: str, endpoint: str, samples: int) -> dict:
    times: list[float] = []
    status = None
    for _ in range(samples):
        started = time.perf_counter()
        try:
            response = session.get(f"{base_url}{endpoint}", timeout=120)
            status = response.status_code
            if response.ok:
                times.append((time.perf_counter() - started) * 1000)
        except requests.RequestException as exc:
            status = f"fel: {type(exc).__name__}"
    return {
        "endpoint": endpoint,
        "samples_ms": [round(value, 1) for value in times],
        "best_ms": round(min(times), 1) if times else None,
        "median_ms": round(statistics.median(times), 1) if times else None,
        "status": status,
    }


def run_benchmark(base_url: str, username: str, password: str, endpoints: tuple[str, ...], samples: int) -> dict:
    session = requests.Session()
    response = session.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    results = [measure(session, base_url, endpoint, samples) for endpoint in endpoints]
    return {
        "base_url": base_url,
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "samples": samples,
        "results": results,
    }


def print_report(report: dict, compare: dict | None) -> None:
    compare_by = {}
    if compare:
        compare_by = {row["endpoint"]: row for row in compare.get("results", [])}
        print(f"Jämför mot: {compare.get('label') or compare.get('ran_at')} ({compare.get('base_url')})")
    header = f"{'endpoint':52s} {'bästa':>9s} {'median':>9s}"
    if compare_by:
        header += f" {'förut':>9s} {'diff':>12s}"
    print(header)
    for row in report["results"]:
        best = row["best_ms"]
        line = f"{row['endpoint'][:52]:52s} {best if best is not None else 'FEL':>9} {row['median_ms'] if row['median_ms'] is not None else '-':>9}"
        previous = compare_by.get(row["endpoint"])
        if previous:
            prev_best = previous.get("best_ms")
            if best is not None and prev_best:
                delta = best - prev_best
                pct = (delta / prev_best) * 100
                line += f" {prev_best:>9} {delta:>+7.0f}ms {pct:>+.0f}%"
            else:
                line += f" {prev_best if prev_best is not None else 'FEL':>9} {'-':>12s}"
        print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--label", help="Namn på körningen; blir filnamn i output-katalogen.")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--endpoints", help="Kommaseparerad endpointlista som ersätter standarduppsättningen.")
    parser.add_argument("--compare", help="Sökväg till tidigare rapport-JSON att diffa mot.")
    parser.add_argument("--output", default="artifacts/api_benchmark")
    args = parser.parse_args()

    endpoints = tuple(item.strip() for item in args.endpoints.split(",")) if args.endpoints else DEFAULT_ENDPOINTS
    report = run_benchmark(args.base_url, args.username, args.password, endpoints, max(1, args.samples))
    report["label"] = args.label or None

    compare = None
    if args.compare:
        compare = json.loads(Path(args.compare).read_text(encoding="utf-8"))

    print_report(report, compare)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    name = args.label or datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = output_dir / f"{name}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRapport: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

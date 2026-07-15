"""Before/after-benchmark av API-endpoints mot en körande flow-miljö.

Loggar in, mäter varje endpoint N gånger och skriver en JSON-rapport som kan
jämföras med en tidigare körning via --compare. Används före och efter varje
prestandapåverkande ändring så effekten blir mätbar istället för gissad
(regel i AGENTS.md).

Mäter både latens och payload:

* `content_length_bytes` = DEKOMPRIMERAD storlek (`len(response.content)`;
  requests packar upp gzip automatiskt). Det är den siffra som avslöjar en
  payload som svällt, oberoende av komprimeringsnivå.
* `wire_bytes` = bytes på tråden, läst ur Content-Length-headern. Skiljer sig
  från `content_length_bytes` exakt när komprimering är på.
* `content_encoding` = svarets Content-Encoding (`gzip` eller None).

Detta mäter INTE SSE. Strömmade svar (produktivitet, sankey) ingår inte i
DEFAULT_ENDPOINTS och skickas chunked utan Content-Length — `wire_bytes` blir
None där, och den okomprimerade SSE-payloaden syns inte i den här rapporten.

Byte-taket för pre-push ligger i tests/tools/test_gap_payload_budget.py
(TestClient, ingen miljö behövs). --payload-budget här är komplementet som
körs manuellt mot en riktig miljö med riktig datamängd.

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

# GZipMiddleware i app/backend/main.py komprimerar svar från och med den här
# storleken. Starlette skippar komprimering bara när `len(body) < minimum_size`
# (GZipResponder), alltså är EXAKT minimum_size redan komprimerat — gränsen
# nedan måste därför jämföras med `>=`, inte `>`. Ett svar från och med taket
# som saknar `content-encoding: gzip` betyder att komprimeringen slutat fungera.
# Kontraktet i tests/tools/test_gap_payload_budget.py läser siffran ur appens
# faktiska middleware-konfiguration (inte ur källtexten) och låser gränsfallet.
GZIP_MINIMUM_SIZE_BYTES = 1024

GZIP_ENCODING = "gzip"
IDENTITY_ENCODING = "identity"

# Marginal för det föreslagna byte-taket vid kalibrering (samma metod som
# latency_budgets.json: 60-80 % ovanför uppmätt median).
PAYLOAD_BUDGET_MARGIN = 1.8


def _wire_bytes(response: requests.Response) -> int | None:
    """Bytes på tråden = Content-Length-headern (komprimerad storlek).

    None när headern saknas — t.ex. chunked/strömmade svar (SSE)."""
    raw = response.headers.get("Content-Length")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _median_bytes(values: list[int | None]) -> int | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return int(round(statistics.median(usable)))


def _normalize_encoding(value: str | None) -> str:
    """Saknat/tomt Content-Encoding betyder okomprimerat = 'identity'."""
    return (value or "").strip().lower() or IDENTITY_ENCODING


def _content_encoding(encodings: list[str | None]) -> str | None:
    """Ett värde när alla sample var lika, annars ALLA distinkta värden.

    Blandade sample är i sig ett fynd: några svar kom komprimerade och andra
    inte. Strängen behåller därför varje distinkt värde (kommaseparerat), och
    check_payload_budgets skiljer på "alla sample gzippade" och "några" via
    _encoding_tokens — aldrig via substrängmatchning, som hade låtit ETT enda
    gzippat sample maskera att resten levererades okomprimerade."""
    if not encodings:
        return None
    unique = sorted({_normalize_encoding(value) for value in encodings})
    if unique == [IDENTITY_ENCODING]:
        return None  # okomprimerat rapporteras som None, som tidigare
    return ",".join(unique)


def _encoding_tokens(row: dict) -> list[str]:
    """Per-sample-encodings för en rapportrad, normaliserade.

    Nya rapporter har `content_encoding_samples` (ett värde per sample). Äldre
    rapporter och den sammanslagna strängen faller tillbaka på att splitta
    `content_encoding` — då blir ett blandat svar minst två tokens, vilket är
    allt kontrollen behöver för att inte godta det som "gzippat"."""
    samples = row.get("content_encoding_samples")
    if samples:
        return [_normalize_encoding(item) for item in samples]
    encoding = row.get("content_encoding")
    if not encoding:
        return [IDENTITY_ENCODING]
    return [_normalize_encoding(part) for part in str(encoding).split(",")]


def measure(session: requests.Session, base_url: str, endpoint: str, samples: int) -> dict:
    times: list[float] = []
    body_bytes: list[int | None] = []
    wire: list[int | None] = []
    encodings: list[str | None] = []
    status = None
    for _ in range(samples):
        started = time.perf_counter()
        try:
            response = session.get(f"{base_url}{endpoint}", timeout=120)
            status = response.status_code
            if response.ok:
                times.append((time.perf_counter() - started) * 1000)
                # requests har redan buffrat och dekomprimerat bodyn i get()
                # (stream=False), så .content här kostar inget och påverkar
                # inte latenssiffran ovanför.
                body_bytes.append(len(response.content))
                wire.append(_wire_bytes(response))
                encodings.append(response.headers.get("Content-Encoding"))
        except requests.RequestException as exc:
            status = f"fel: {type(exc).__name__}"
    return {
        "endpoint": endpoint,
        "samples_ms": [round(value, 1) for value in times],
        "best_ms": round(min(times), 1) if times else None,
        "median_ms": round(statistics.median(times), 1) if times else None,
        "content_bytes_samples": body_bytes,
        "content_length_bytes": _median_bytes(body_bytes),
        "wire_bytes_samples": wire,
        "wire_bytes": _median_bytes(wire),
        "content_encoding": _content_encoding(encodings),
        "content_encoding_samples": [_normalize_encoding(value) for value in encodings],
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
    # OBS: allt läses med .get. Både gamla baslinjefiler i artifacts/ och
    # rapporter från äldre versioner av verktyget saknar bytefälten.
    compare_by = {}
    if compare:
        compare_by = {row["endpoint"]: row for row in compare.get("results", [])}
        print(f"Jämför mot: {compare.get('label') or compare.get('ran_at')} ({compare.get('base_url')})")
    header = f"{'endpoint':52s} {'bästa':>9s} {'median':>9s} {'bytes':>9s} {'wire':>9s} {'enc':>14s}"
    if compare_by:
        header += f" {'förut':>9s} {'diff':>12s} {'bytes förut':>13s}"
    print(header)
    for row in report.get("results", []):
        best = row.get("best_ms")
        median = row.get("median_ms")
        size = row.get("content_length_bytes")
        wire = row.get("wire_bytes")
        encoding = row.get("content_encoding") or "-"
        line = (
            f"{row['endpoint'][:52]:52s}"
            f" {best if best is not None else 'FEL':>9}"
            f" {median if median is not None else '-':>9}"
            f" {size if size is not None else '-':>9}"
            f" {wire if wire is not None else '-':>9}"
            f" {encoding[:8]:>8s}"
        )
        previous = compare_by.get(row["endpoint"])
        if previous:
            prev_best = previous.get("best_ms")
            if best is not None and prev_best:
                delta = best - prev_best
                pct = (delta / prev_best) * 100
                line += f" {prev_best:>9} {delta:>+7.0f}ms {pct:>+.0f}%"
            else:
                line += f" {prev_best if prev_best is not None else 'FEL':>9} {'-':>12s}"
            prev_size = previous.get("content_length_bytes")
            if size is not None and prev_size:
                byte_pct = ((size - prev_size) / prev_size) * 100
                line += f" {prev_size:>8}B {byte_pct:>+3.0f}%"
            else:
                line += f" {'-':>13s}"
        print(line)


def check_budgets(report: dict, budgets: dict) -> list[str]:
    """Jämför medianer mot latensbudgeten; returnerar överträdelser."""
    breaches: list[str] = []
    limits = {k: v for k, v in budgets.items() if not str(k).startswith("_")}
    for row in report["results"]:
        limit = limits.get(row["endpoint"])
        if limit is None:
            continue
        median = row.get("median_ms")
        if median is None:
            breaches.append(f"{row['endpoint']}: inget lyckat svar (status {row.get('status')})")
        elif median > float(limit):
            breaches.append(f"{row['endpoint']}: median {median} ms > budget {limit} ms")
    return breaches


def check_payload_budgets(report: dict, budgets: dict) -> list[str]:
    """Jämför DEKOMPRIMERAD payloadstorlek mot byte-budgeten.

    Fångar två fel: (1) en payload som svällt, (2) en komprimering som slutat
    fungera (svar från och med GZIP_MINIMUM_SIZE_BYTES utan
    `content-encoding: gzip`).

    Gränsen är `>=`, inte `>`: Starlettes GZipMiddleware komprimerar vid
    `len(body) >= minimum_size`, så ett svar på EXAKT minimum_size ska redan
    vara gzippat. Med `>` var kontrollen fel på precis den gräns den kodar.

    ALLA sample måste vara gzippade. Substrängmatchning ("gzip" in encoding)
    hade låtit ett enda gzippat sample maskera att övriga levererades
    okomprimerade — ett falskt negativt i just den kontroll som är hela poängen.
    Blandade sample rapporteras med mängd (N av M).

    Ett `null`-tak betyder "nyckeln finns, taket är inte kalibrerat än" — då
    kontrolleras bara att svaret kom fram och att det fortfarande komprimeras.
    Endpoints utan budgetnyckel hoppas över, precis som i check_budgets.

    Gäller inte SSE: strömmade svar ingår inte i DEFAULT_ENDPOINTS och saknar
    Content-Length."""
    breaches: list[str] = []
    limits = {k: v for k, v in budgets.items() if not str(k).startswith("_")}
    for row in report.get("results", []):
        endpoint = row.get("endpoint")
        if endpoint not in limits:
            continue
        limit = limits[endpoint]
        size = row.get("content_length_bytes")
        if size is None:
            breaches.append(f"{endpoint}: ingen payloadstorlek uppmätt (status {row.get('status')})")
            continue
        if limit is not None and size > float(limit):
            breaches.append(f"{endpoint}: payload {size} B > budget {limit} B")
        if size >= GZIP_MINIMUM_SIZE_BYTES:
            encoding = row.get("content_encoding")
            tokens = _encoding_tokens(row)
            gzipped = sum(1 for token in tokens if token == GZIP_ENCODING)
            if gzipped == 0:
                breaches.append(
                    f"{endpoint}: {size} B levereras utan gzip (content-encoding {encoding!r}) "
                    "- komprimeringen verkar ha slutat fungera"
                )
            elif gzipped < len(tokens):
                breaches.append(
                    f"{endpoint}: {size} B levereras bara delvis gzippat - {gzipped} av "
                    f"{len(tokens)} sample hade gzip (content-encoding {encoding!r}). "
                    "Komprimeringen är instabil; ett gzippat sample räknas inte som OK."
                )
    return breaches


def payload_budget_suggestions(report: dict, budgets: dict) -> list[str]:
    """Föreslaget byte-tak för budgetnycklar som ännu är okalibrerade (null)."""
    limits = {k: v for k, v in budgets.items() if not str(k).startswith("_")}
    lines: list[str] = []
    for row in report.get("results", []):
        endpoint = row.get("endpoint")
        if endpoint not in limits or limits[endpoint] is not None:
            continue
        size = row.get("content_length_bytes")
        if size is None:
            continue
        lines.append(
            f"{endpoint}: uppmätt {size} B -> föreslaget tak {int(size * PAYLOAD_BUDGET_MARGIN)} B"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--label", help="Namn på körningen; blir filnamn i output-katalogen.")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--endpoints", help="Kommaseparerad endpointlista som ersätter standarduppsättningen.")
    parser.add_argument("--compare", help="Sökväg till tidigare rapport-JSON att diffa mot.")
    parser.add_argument(
        "--budget",
        help="Sökväg till latensbudget-JSON (endpoint -> max median-ms). Avslutar med kod 2 vid överträdelse.",
    )
    parser.add_argument(
        "--payload-budget",
        help=(
            "Sökväg till payloadbudget-JSON (endpoint -> max dekomprimerade bytes, null = okalibrerad). "
            "Avslutar med kod 2 vid överträdelse. Vanligen tools/payload_budgets.json."
        ),
    )
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

    exit_code = 0
    if args.budget:
        budgets = json.loads(Path(args.budget).read_text(encoding="utf-8"))
        breaches = check_budgets(report, budgets)
        if breaches:
            print("\nLATENSBUDGET ÖVERSKRIDEN:")
            for breach in breaches:
                print(f"  - {breach}")
            exit_code = 2
        else:
            print("Latensbudget: OK.")

    if args.payload_budget:
        payload_budgets = json.loads(Path(args.payload_budget).read_text(encoding="utf-8"))
        payload_breaches = check_payload_budgets(report, payload_budgets)
        if payload_breaches:
            print("\nPAYLOADBUDGET ÖVERSKRIDEN:")
            for breach in payload_breaches:
                print(f"  - {breach}")
            exit_code = 2
        else:
            print("Payloadbudget: OK.")
        suggestions = payload_budget_suggestions(report, payload_budgets)
        if suggestions:
            print("\nOkalibrerade byte-tak (null i budgetfilen) - fyll i dessa:")
            for suggestion in suggestions:
                print(f"  - {suggestion}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

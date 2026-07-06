"""Post-deploy-gate: verifiera att appen svarar efter en deploy.

Tänkt att köras som sista steg i Octopus (eller manuellt efter en release):

    python -m tools.post_deploy_check --base-url https://<server> [--attempts 12] [--delay 5]

Exit 0 när /api/health svarar 200 (efter ev. omförsök under uppstart),
exit 1 annars — så deployn blir röd i Octopus i stället för att upptäckas
av en användare. k8s kör strategy: Recreate, så några sekunders väntan i
början är förväntat.
"""
from __future__ import annotations

import argparse
import sys
import time

import requests


def check_health(base_url: str, attempts: int, delay_seconds: float) -> bool:
    url = base_url.rstrip("/") + "/api/health"
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                print(f"OK: {url} svarade 200 (försök {attempt}/{attempts}).")
                return True
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last_error = type(exc).__name__
        print(f"Väntar: {url} -> {last_error} (försök {attempt}/{attempts}).")
        if attempt < attempts:
            time.sleep(delay_seconds)
    print(f"FEL: {url} svarade aldrig 200. Senaste fel: {last_error}.")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Serverns bas-URL, t.ex. https://example")
    parser.add_argument("--attempts", type=int, default=12, help="Antal försök (default 12)")
    parser.add_argument("--delay", type=float, default=5.0, help="Sekunder mellan försök (default 5)")
    args = parser.parse_args(argv)
    return 0 if check_health(args.base_url, args.attempts, args.delay) else 1


if __name__ == "__main__":
    sys.exit(main())

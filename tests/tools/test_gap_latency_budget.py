"""Latensbudget-kontrakt (W26): tools/latency_budgets.json <-> api_benchmark.

(a) Varje budgetnyckel som inte börjar med '_' måste finnas EXAKT som en
    DEFAULT_ENDPOINTS-post. Annars kontrollerar budgeten en endpoint som
    benchmarken aldrig mäter (död budget) eller stavar fel.
(b) check_budgets ska flagga över-budget och saknat svar (median_ms=None)
    men inte under-budget; main() ska avsluta med kod 2 vid överträdelse.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import api_benchmark

BUDGETS_PATH = Path(api_benchmark.__file__).resolve().parent / "latency_budgets.json"


def _load_budgets() -> dict:
    return json.loads(BUDGETS_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# (a) budget-nycklar <-> DEFAULT_ENDPOINTS
# --------------------------------------------------------------------------- #
def test_budget_file_exists_and_parses():
    budgets = _load_budgets()
    assert isinstance(budgets, dict)
    # Minst en riktig endpoint-budget, inte bara kommentarer.
    assert any(not str(k).startswith("_") for k in budgets)


def test_every_budget_key_is_exactly_a_default_endpoint():
    budgets = _load_budgets()
    default_endpoints = set(api_benchmark.DEFAULT_ENDPOINTS)
    budget_keys = [k for k in budgets if not str(k).startswith("_")]

    assert budget_keys, "budgetfilen saknar riktiga endpoint-nycklar"
    for key in budget_keys:
        assert key in default_endpoints, (
            f"budgetnyckel {key!r} finns inte exakt i DEFAULT_ENDPOINTS "
            f"(död/felstavad budget); DEFAULT_ENDPOINTS={sorted(default_endpoints)}"
        )


def test_budget_values_are_positive_numbers():
    budgets = _load_budgets()
    for key, value in budgets.items():
        if str(key).startswith("_"):
            continue
        assert isinstance(value, (int, float)) and not isinstance(value, bool), (
            f"budget för {key!r} är inte ett tal: {value!r}"
        )
        assert value > 0, f"budget för {key!r} måste vara > 0, är {value!r}"


# --------------------------------------------------------------------------- #
# (b) check_budgets-enhet
# --------------------------------------------------------------------------- #
def _synthetic_report() -> dict:
    """En rapport med: över budget, under budget, saknat svar (median None)."""
    return {
        "results": [
            {"endpoint": "/api/areas", "median_ms": 900.0, "best_ms": 850.0, "status": 200},
            {"endpoint": "/api/activities", "median_ms": 50.0, "best_ms": 45.0, "status": 200},
            {"endpoint": "/api/persons", "median_ms": None, "best_ms": None, "status": "fel: Timeout"},
        ]
    }


def test_check_budgets_flags_first_and_last_only():
    budgets = _load_budgets()
    breaches = api_benchmark.check_budgets(_synthetic_report(), budgets)

    # Exakt två överträdelser: /api/areas (över) + /api/persons (inget svar).
    assert len(breaches) == 2, breaches
    joined = " | ".join(breaches)
    assert "/api/areas" in joined
    assert "/api/persons" in joined
    # Under-budget-endpointen får INTE rapporteras.
    assert "/api/activities" not in joined


def test_check_budgets_none_median_is_reported_as_no_response():
    budgets = _load_budgets()
    report = {
        "results": [
            {"endpoint": "/api/persons", "median_ms": None, "status": "fel: Timeout"},
        ]
    }
    breaches = api_benchmark.check_budgets(report, budgets)
    assert len(breaches) == 1
    assert "/api/persons" in breaches[0]
    # Meddelandet ska handla om uteblivet svar, inte om medianjämförelse.
    assert "budget" not in breaches[0] or "inget" in breaches[0].lower()


def test_check_budgets_ignores_underscore_keys_and_unbudgeted_endpoints():
    # En endpoint utan budget ska hoppas över (limit is None -> continue),
    # även om den vore långsam.
    report = {
        "results": [
            {"endpoint": "/api/unbudgeted", "median_ms": 99999.0, "status": 200},
        ]
    }
    budgets = {"_kommentar": "x", "/api/areas": 400}
    assert api_benchmark.check_budgets(report, budgets) == []


def test_check_budgets_empty_when_all_within_budget():
    report = {
        "results": [
            {"endpoint": "/api/areas", "median_ms": 10.0, "status": 200},
            {"endpoint": "/api/activities", "median_ms": 10.0, "status": 200},
        ]
    }
    assert api_benchmark.check_budgets(report, _load_budgets()) == []


# --------------------------------------------------------------------------- #
# (b) main() exit-kod 2 vid överträdelse
# --------------------------------------------------------------------------- #
def test_main_returns_2_on_budget_breach(monkeypatch, tmp_path):
    """main() ska avsluta med kod 2 när budgeten överskrids, utan nätverk."""

    def fake_run_benchmark(base_url, username, password, endpoints, samples):
        # Syntetisk rapport med garanterad överträdelse mot verklig budget.
        return {
            "base_url": base_url,
            "ran_at": "2026-07-07T00:00:00",
            "samples": samples,
            "results": [
                {"endpoint": "/api/areas", "median_ms": 99999.0, "best_ms": 99999.0, "status": 200},
                {"endpoint": "/api/activities", "median_ms": 5.0, "best_ms": 5.0, "status": 200},
            ],
        }

    monkeypatch.setattr(api_benchmark, "run_benchmark", fake_run_benchmark)
    argv = [
        "api_benchmark",
        "--base-url", "http://example.invalid",
        "--username", "u",
        "--password", "p",
        "--budget", str(BUDGETS_PATH),
        "--output", str(tmp_path / "out"),
        "--label", "unittest",
    ]
    monkeypatch.setattr("sys.argv", argv)

    assert api_benchmark.main() == 2


def test_main_returns_0_when_within_budget(monkeypatch, tmp_path):
    def fake_run_benchmark(base_url, username, password, endpoints, samples):
        return {
            "base_url": base_url,
            "ran_at": "2026-07-07T00:00:00",
            "samples": samples,
            "results": [
                {"endpoint": "/api/areas", "median_ms": 5.0, "best_ms": 5.0, "status": 200},
                {"endpoint": "/api/activities", "median_ms": 5.0, "best_ms": 5.0, "status": 200},
            ],
        }

    monkeypatch.setattr(api_benchmark, "run_benchmark", fake_run_benchmark)
    argv = [
        "api_benchmark",
        "--base-url", "http://example.invalid",
        "--username", "u",
        "--password", "p",
        "--budget", str(BUDGETS_PATH),
        "--output", str(tmp_path / "out"),
        "--label", "unittest-ok",
    ]
    monkeypatch.setattr("sys.argv", argv)

    assert api_benchmark.main() == 0

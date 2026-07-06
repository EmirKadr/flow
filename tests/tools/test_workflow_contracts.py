"""Kontrakt för GitHub Actions-workflows.

Fångar klassen "workflow ser giltig ut men beter sig fel i GitHub" innan den
mejlar spök-failures. Lärt 2026-07-06: ett schemalagt workflow (bara
`schedule`/`workflow_dispatch`, inget `push`) får GitHub att skapa en tom
"No jobs were run"-körning för push-eventet som rapporteras som FAILURE och
mejlar vid varje push. Det här testet hade fällt nightly-flake-hunt.yml direkt
i pre-push i stället för efter fyra pushar.

Regel: ett workflow som är schemalagt (`schedule`) måste också deklarera
`push`, OCH minst ett jobb måste faktiskt köra på push (inget `if` på
JOBB-nivå som exkluderar push). Annars kör GitHub noll jobb → "No jobs were
run" = FAILURE. Gardera de dyra stegen på STEG-nivå i stället; låt jobbet
alltid instansieras så push-körningen blir grön.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".github" / "workflows"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _on_block(workflow: dict):
    # YAML 1.1 (PyYAML) tolkar den nakna nyckeln `on:` som boolean True,
    # inte strängen "on". Hantera båda.
    if "on" in workflow:
        return workflow["on"]
    if True in workflow:
        return workflow[True]
    return None


def _triggers(on_block) -> set[str]:
    if on_block is None:
        return set()
    if isinstance(on_block, str):
        return {on_block}
    if isinstance(on_block, list):
        return set(on_block)
    if isinstance(on_block, dict):
        return set(on_block.keys())
    return set()


def _workflow_files() -> list[Path]:
    return sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))


def test_workflows_parse_and_have_jobs():
    """Varje workflow ska vara giltig YAML med minst ett jobb och ett on-block."""
    files = _workflow_files()
    assert files, "inga workflow-filer hittades"
    for path in files:
        workflow = _load(path)
        assert isinstance(workflow, dict), f"{path.name}: kunde inte parsas som mapping"
        assert _on_block(workflow) is not None, f"{path.name}: saknar on-trigger"
        assert workflow.get("jobs"), f"{path.name}: saknar jobs"


def _job_runs_on_push(job: dict) -> bool:
    """Ett jobb körs på push om det saknar `if` på jobb-nivå, eller om if:t
    inte exkluderar push. Ett `if` som innehåller `github.event_name != 'push'`
    filtrerar bort hela jobbet på push (→ zero-jobs failure)."""
    guard = str(job.get("if", "")).replace('"', "'")
    if not guard:
        return True
    return "github.event_name != 'push'" not in guard


def test_scheduled_workflows_survive_push_without_ghost_failure():
    """Schemalagda workflows måste (1) deklarera `push` och (2) ha minst ett
    jobb som faktiskt körs på push, annars blir push-körningen en tom
    "No jobs were run"-failure som mejlar vid varje push."""
    offenders: list[str] = []
    for path in _workflow_files():
        workflow = _load(path)
        triggers = _triggers(_on_block(workflow))
        if "schedule" not in triggers:
            continue
        if "push" not in triggers:
            offenders.append(
                f"{path.name}: schemalagt men deklarerar inte `push` - GitHub "
                f"skapar en tom failure-körning för push-eventet."
            )
            continue
        jobs = workflow.get("jobs") or {}
        if not any(_job_runs_on_push(job) for job in jobs.values()):
            offenders.append(
                f"{path.name}: alla jobb har `if` som exkluderar push → noll "
                f"jobb körs → 'No jobs were run'-failure. Flytta garderingen "
                f"till STEG-nivå så jobbet alltid instansieras och blir grönt."
            )
    assert offenders == [], "Workflows med push-spök-failure-risk:\n" + "\n".join(offenders)

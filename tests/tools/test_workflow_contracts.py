"""Kontrakt för GitHub Actions-workflows.

Fångar klassen "workflow ser giltig ut men beter sig fel i GitHub" innan den
mejlar spök-failures. Lärt 2026-07-06: ett schemalagt workflow (bara
`schedule`/`workflow_dispatch`, inget `push`) får GitHub att skapa en tom
"No jobs were run"-körning för push-eventet som rapporteras som FAILURE och
mejlar vid varje push. Det här testet hade fällt nightly-flake-hunt.yml direkt
i pre-push i stället för efter fyra pushar.

Regel: ett workflow som är schemalagt (`schedule`) måste också deklarera
`push` OCH skippa varje jobb på push (`if: github.event_name != 'push'`), så
att push-körningen blir ett rent skip (grön) i stället för en tom failure.
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


def test_scheduled_workflows_skip_on_push():
    """Schemalagda workflows måste garderas mot push-spök-failures:
    deklarera `push` och skippa alla jobb på push."""
    offenders: list[str] = []
    for path in _workflow_files():
        workflow = _load(path)
        triggers = _triggers(_on_block(workflow))
        if "schedule" not in triggers:
            continue
        if "push" not in triggers:
            offenders.append(
                f"{path.name}: schemalagt men deklarerar inte `push` - GitHub "
                f"skapar en tom failure-körning för push. Lägg till `push:` + "
                f"`if: github.event_name != 'push'` på jobben."
            )
            continue
        jobs = workflow.get("jobs") or {}
        for job_name, job in jobs.items():
            guard = str(job.get("if", ""))
            if "github.event_name != 'push'" not in guard.replace('"', "'"):
                offenders.append(
                    f"{path.name}:{job_name}: saknar push-gardering "
                    f"(`if: github.event_name != 'push'`) - push-körningen blir "
                    f"en spök-failure."
                )
    assert offenders == [], "Workflows utan push-gardering:\n" + "\n".join(offenders)

# Agent-audit

Agent-audit ar lokal observability for kodande agenter. Runtime-OTel visar vad
Flow gor nar appen kor. Agent-audit visar vad en agent gjorde i repot: mal,
gren, commit, filer, testkommandon och en lokal span-liknande tidslinje.

## Snabbstart

Installera hooks i repot:

```powershell
python -m tools.agent_audit install-hooks --agent codex --auto
```

Efter det lagger Git automatiskt till metadata i commitmeddelanden:

```text
Agent: codex
Agent-Run-Id: 20260614T170000Z-ab12cd34
Agent-Goal: Commit: Add local agent audit
```

Varje automatisk run sparas lokalt under `artifacts/agent_runs/`. Den katalogen
ar gitignorerad och ska inte pushas.

## Manuellt lage

For langre arbeten kan agenten starta en aktiv run innan kodandringen:

```powershell
python -m tools.agent_audit start --goal "Lagg till lokal agent-observability"
python -m tools.agent_audit record --event note --message "Laste befintliga hooks och testmonster"
python -m tools.agent_audit exec -- python -m pytest tests/tools/test_agent_audit.py
python -m tools.agent_audit finish --summary "Agent-audit, hooks och tester tillagda"
```

Visa historik:

```powershell
python -m tools.agent_audit list
python -m tools.agent_audit show <run-id>
```

## Vad sparas

- `runs/<run-id>.json`: sammanfattning, branch, base commit, commits, filer,
  testkommandon och status.
- `events/<run-id>.jsonl`: handelser som task_start, note, command_start,
  test_run och commit_created.
- `otel/<run-id>.jsonl`: lokal OTel-liknande span-tidslinje med trace_id,
  span_id, agentnamn och gitmetadata.

## Integritet

Spara inte prompts, svarstext, kunddata, tokens, privata URL:er, filinnehall
eller request bodies i event-attribut. Verktyget kortar ner text och commit-hooks
skriver bara agent, run-id och commitmal, men manuella `record`-anrop ska fortsatt
hallla sig till sanerade sammanfattningar.

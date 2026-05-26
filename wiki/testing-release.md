---
title: Test och release
status: aktiv
updated: 2026-05-26
tags: [test, release, agent]
---

# Test och release

Kort svar: vid produktbeteende ska agenten testa både webb och Windows-paritet sa langt rimligt. Dokumentationsandringar som bara lagger till wiki kraver normalt ingen testsvit, men kan verifieras med fil-/lankkontroll.

## Snabbtest for kodandringar

```powershell
python -m pytest
Get-ChildItem -Path app\frontend\js -Filter *.js | ForEach-Object { node --check $_.FullName }
python -m tools.flow_cli routes --format table
python desktop\main.py --smoke-test
python -m tools.healthcheck report --local --no-render
python -m tools.healthcheck waits --local --period 24h
```

## Visuella tester

```powershell
python -m tools.visual_smoke
python -m tools.visual_smoke --via-desktop-proxy --roles admin,warehouse
python -m tools.interactive_e2e
python -m tools.performance_benchmark --runs 1
python -m tools.desktop_shell_screens
python -m tools.desktop_app_probe
```

## Nar olika tester behovs

| Andring | Minsta rimliga verifiering |
| --- | --- |
| Backendregel/API | Relevant `pytest` + `flow_cli routes` om API-vag andras |
| Frontend-JS | `node --check`, visuell smoke eller interaktiv E2E beroende pa risk |
| Laddning/cache/UX-hastighet | `tools.performance_benchmark` for kall/varm navigation, bakgrundsladdning, toggle, import, drag och copy |
| Anvandarsynlig loggning | `tests/tools/test_sidebar_user_browser.py` for dokumentlogg i browser + `tests/tools/test_visual_tools.py` for global logg-/API-wiring |
| Halsa/vantetid/drift | `tools.healthcheck report --local --no-render` + `tools.healthcheck waits --local --period 24h`; efter deploy aven servercheck med `--base-url` nar auth och Render-secrets finns |
| flow/Oversikt | Interaktiv E2E for celler, drag, undo/redo och roller |
| Sidebar/roller | Rolltester + visual smoke for flera roller |
| Produktivitet/lager | `tests/services/test_warehouse_tools_local_data.py` och relevanta UI-screenshots |
| Nytt Bearbeta-flode | Register-/handler-test i `tests/services/test_warehouse_tools_local_data.py`, API/sessiontest i `tests/services/test_allocation_bridge.py`, statiskt UI-kontrakt i `tests/tools/test_visual_tools.py` och Playwright-test i `tests/tools/test_allocation_split_browser.py` om knappar eller readiness andras |
| Bearbeta-flode med sessionberoende | Testa att forsta flodet sparar artifact/session, att nasta flode kraver den, och att frontend skickar session-id:t vidare |
| Desktop-app | `desktop\main.py --smoke-test`, desktop probe/shell screens |
| Dokumentation/wiki | Kontrollera att nya wiki-lankar finns och att `index.md`/`log.md` ar uppdaterade |

## Driftgrind for agenter

Halsa och Vantetider ar ett permanent arbetssatt. Efter storre pushar, deploys,
databas-/Render-andringar, cache/bakgrundsladdning, import/export, Bearbeta-floden
eller releasefiler ska agenten kontrollera lokal halsa och anvandarvantetider:

```powershell
python -m tools.healthcheck report --local --no-render
python -m tools.healthcheck waits --local --period 24h
```

Produktionens databas ar Postgres. Nar production/Render kontrolleras ska
`DATABASE_URL` peka mot Render Postgres eller sa ska serverns `/api/healthcheck`
anvandas efter deploy. SQLite anvands bara for lokal utveckling och temporara
tester. Om agenten bara ska hamta Render deploy/loggar utan databaskoppling kan
den kora:

```powershell
python -m tools.healthcheck report --local --skip-db
```

Efter deploy ska agenten dessutom kora servercheck nar auth och Render-secrets
finns:

```powershell
python -m tools.healthcheck report --base-url <url>
python -m tools.healthcheck waits --base-url <url> --period 24h
```

`error` eller tydliga `warn` ska fixas eller rapporteras med kommando, tidpunkt
och feltext innan arbetet betraktas som klart. Nar Historik paverkas ska flikarna
`Halsa` och `Vantetider` verifieras visuellt eller via API.

## Releasekontroll

For release: folj `TESTPROTOCOL.md` och `RELEASE.md`. Kort version:

1. Full testsvit.
2. JS-syntaxkontroll.
3. Desktop smoke/probe.
4. Visual smoke for huvudroller.
5. Interaktiv E2E.
6. Healthcheck lokalt och, efter deploy, mot servern.
7. Build Windows.
8. Release check.

## Kallor

- `../TESTPROTOCOL.md`
- `../BUILD.md`
- `../RELEASE.md`
- `../tools/visual_smoke.py`
- `../tools/interactive_e2e.py`
- `../tools/performance_benchmark.py`
- `../tools/healthcheck.py`

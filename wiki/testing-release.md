---
title: Test och release
status: aktiv
updated: 2026-07-03
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
python -m tools.healthcheck report --local
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
| Databas/Alembic/CI | `tests/tools/test_alembic_migrations.py` for revisionslangd, unikhet, down_revision-kedja och head; `tests/tools/test_ci_workflows.py` for Postgres- **och MSSQL-simulering** av alembic-bygget (CI-jobbet `mssql-gate` bygger schemat fran noll mot riktig SQL Server 2022) samt k8s-secretmallen; `tests/tools/test_mssql_compat.py` for dialektforbjudna monster (`.is_(True)`, tuple-IN); `tests/tools/test_model_migration_parity.py` for att varje modellkolumn har en migration; `tests/tools/test_startup_migrations.py` for att appstarten kor `alembic upgrade head` mot delade databaser. Vid ny migration ska ett test laggas for den felklass som annars skulle kunna stoppa `alembic upgrade head`. Ny migration maste vara dialektsaker: inga `true/false`-literaler, inga PG-autonamn (`*_pkey`/`*_key`), citera reserverade ord (`"key"`), och `alter_column` behover `existing_type` for MSSQL. |
| Frontend-JS | `node --check`, visuell smoke eller interaktiv E2E beroende pa risk |
| Laddning/cache/UX-hastighet | `tools.performance_benchmark` for kall/varm navigation, bakgrundsladdning, toggle, import, drag och copy |
| Anvandarsynlig loggning | `tests/tools/test_sidebar_user_browser.py` for dokumentlogg i browser + `tests/tools/test_visual_tools.py` for global logg-/API-wiring |
| Halsa/vantetid/drift | `tools.healthcheck report --local` + `tools.healthcheck waits --local --period 24h`; efter deploy aven servercheck med `--base-url` nar agenten har inloggning. Kontrollera `Serverminne` efter cache-, Bearbeta-, Meta- eller Forecast-andringar. |
| flow/Oversikt | Interaktiv E2E for celler, drag, undo/redo och roller |
| Sidebar/roller | Rolltester + visual smoke for flera roller |
| Ny handelse/integration/hardvara | API-/domantest for handelsen, audit-test for `entity_type`/`action`, obligatorisk Historik/Analys-label i frontend/backend, verksamhetsscope och minst ett fel-/okant-lage. Hardvara far mockas; manuell scanning ar bara komplement. |
| Nytt dataandrande flode | Bevisa att flodet skapar sparad audit-rad med ratt scope och sanerad payload, samt att raden har begriplig Historik/Analys-label eller backend-summary. Om flodet ar read-only och saknar audit ska undantaget vara dokumenterat och testat. |
| Produktivitet/lager | `tests/services/test_warehouse_tools_local_data.py` och relevanta UI-screenshots. Forecast-regler for orderoversikt, till exempel att status `11` filtrerar bort samma ordernummer ur detaljkundorder, ska ha riktat handler-/domantest. Ytgenereringens enknappsflode ska testas for bade komplett ytdel nar `location` finns och Forecast-only nar `location` saknas. ASK-import for order/yta ska verifiera att `company` kommer fran forecastens `Bolag`, att `pick_zone` ar `A`, och att kartans lokala justerade ASK-export foljer samma kontrakt. Ytgenereringens ytkartsinstallningar ska testas bade som handlerkapacitet/koordinater och som API-parametrar i `tests/services/test_allocation_bridge.py`. |
| Uppladdningar/filpreview | `tests/services/test_coredata_service.py` for serverlagrad karn-/sammanstalld preview, `tests/tools/test_visual_tools.py` for UI-kontrakt och `node --check app/frontend/js/allocation_tools.js` for modal-JS |
| Nytt Bearbeta-flode | Register-/handler-test i `tests/services/test_warehouse_tools_local_data.py`, API/sessiontest i `tests/services/test_allocation_bridge.py`, statiskt UI-kontrakt i `tests/tools/test_visual_tools.py` och Playwright-test i `tests/tools/test_allocation_split_browser.py` om knappar eller readiness andras |
| Nytt Bearbeta-flode med karnfil | Testa bade flodesdefault i `tests/services/test_allocation_bridge.py`, att uppladdning av karnfilen ersatter tidigare fil for samma verksamhet i `tests/services/test_coredata_service.py`, och att frontend laser karnfilstatus utan GET-cache |
| Bearbeta-flode med sessionberoende | Testa att forsta flodet sparar artifact/session, att nasta flode kraver den, och att frontend skickar session-id:t vidare. Om sessionberoendet blir legacy eller frivilligt ska testet ocksa verifiera att nya normalvagen inte skickar session-id. Om flodet ocksa styrs av omradestoggle, till exempel Ytgenerering for MG, testa att toggle-parametern gar fran frontend/API till handler och paverkar resultatet. Om anvandaren kan redigera en artifact mellan flodena, till exempel transportorskluster efter Forecast, testa bade backend-overriden och att Playwright ser den redigerade JSON-parametern. |
| Desktop-app | `desktop\main.py --smoke-test`, desktop probe/shell screens |
| Dokumentation/wiki | Kontrollera att nya wiki-lankar finns och att `index.md`/`log.md` ar uppdaterade |

## Driftgrind for agenter

Halsa och Vantetider ar ett permanent arbetssatt. Efter storre pushar, deploys,
databas-/driftandringar, cache/bakgrundsladdning, import/export, Bearbeta-floden
eller releasefiler ska agenten kontrollera lokal halsa och anvandarvantetider:

```powershell
python -m tools.healthcheck report --local
python -m tools.healthcheck waits --local --period 24h
```

Officiell drift ar sedan 2026-07 foretagets k8s (nowasteserver) med MSSQL
(`mssql+pyodbc://...`) enligt `DEPLOY.md` och `k8s/README.md`; Render-driften
ar avvecklad. Efter deploy kontrolleras servern via `/api/healthcheck`
(kraver inloggning) och pod-loggar via `kubectl -n flow logs deploy/flow-web`.
Nar K8s kontrolleras ska startup inte logga `PostgreSQL: kor alembic upgrade head`
om malmiljon ar Azure SQL. SQLite anvands bara for lokal utveckling och
temporara tester. Utan lokal databaskoppling kan agenten kora:

```powershell
python -m tools.healthcheck report --local --skip-db
```

Efter deploy ska agenten dessutom kora servercheck nar auth finns:

```powershell
python -m tools.healthcheck report --base-url <url>
python -m tools.healthcheck waits --base-url <url> --period 24h
```

`error` eller tydliga `warn` ska fixas eller rapporteras med kommando, tidpunkt
och feltext innan arbetet betraktas som klart. Nar Historik paverkas ska flikarna
`Halsa` och `Vantetider` verifieras visuellt eller via API.

## Releasekontroll

Sedan 2026-07 ar den officiella driftvagen NoWaste-servern: releaser byggs
automatiskt i Octopus av commits till `release/*`-branchar och deployas via
Octopus-projektet Flow till development/production. Branchmodell och
steg-for-steg-flode finns i [nowaste-git-release.md](nowaste-git-release.md).

For release: folj `TESTPROTOCOL.md` och `RELEASE.md`. Kort version:

1. Full testsvit.
2. JS-syntaxkontroll.
3. Desktop smoke/probe.
4. Visual smoke for huvudroller.
5. Interaktiv E2E.
6. Healthcheck lokalt och, efter deploy, mot servern.
7. Build Windows.
8. Release check.

## Releasepolling

Efter push/tagg for release ska agenten som standard bara verifiera att GitHub
Actions-workflowen har startat, ge lank till run/workflow och saga att det ar
okej att avsluta har och be agenten kolla releasen senare. Om anvandaren
uttryckligen ber agenten vanta kvar ska statuskoll ske enligt pollingtrappan:
vanta 15 minuter, sedan 2 minuter, sedan 1 minut och darefter var 30:e sekund
tills workflowen ar bekraftat klar eller failad. Syftet ar att undvika onodiga
statusanrop, logghamtningar och token-/kontextkostnad medan GitHub/Octopus jobbar
asynkront.

## Kallor

- `../TESTPROTOCOL.md`
- `../BUILD.md`
- `../RELEASE.md`
- `../tools/visual_smoke.py`
- `../tools/interactive_e2e.py`
- `../tools/performance_benchmark.py`
- `../tools/healthcheck.py`

---
title: Arkitektur
status: aktiv
updated: 2026-07-03
tags: [arkitektur, backend, frontend, desktop]
---

# Arkitektur

Kort svar: `app/` ar FastAPI + statisk vanilla JS. `desktop/` ar ett PyQt6-skal som startar en lokal appyta och proxar `/api/*` till samma centrala backend. `warehouse_tools/` innehaller lagerverktyg som exponeras via backendens allokeringsbrygga.

## Webbapp

- Backend: Python, FastAPI, SQLAlchemy 2, Alembic.
- Frontend: statiska HTML/CSS/JS-filer utan buildsteg.
- Auth: session-cookie via FastAPI `SessionMiddleware`.
- Databas: MSSQL (`mssql+pyodbc`) pa foretagets k8s-drift; SQLite anvands for lokal test/probe.
- Static serving: FastAPI serverar `app/frontend`.
- Webbfavicon och brandlogga ar SVG som primarkalla. PNG/ICO ligger kvar som fallback for PWA, Apple touch och aldre plattformar.

## Windows-app

- `desktop/app.py` skapar PyQt6-fonster, laddningsvy, felvy, meny och updateflode.
- `desktop/local_app_server.py` serverar den lokala frontendmappen och proxar `/api/*` till `SERVER_BASE_URL`. Proxyn skickar `Accept-Encoding: identity` mot central server sa Windows-webviewen alltid far okomprimerade JSON-/CSV-svar.
- Desktop ska bete sig som webben eftersom den anvander samma frontend och samma API.
- Fonsterikonen laddas primart fran `desktop/assets/flow_icon.svg`. `.ico` ligger kvar for exe-/genvagsikon och fallback.
- Tillatna desktop-specifika skillnader ar installation, auto-update, genvagar, lokalt skal och serverdrift.

## Backend-paket och fasader

De tre storsta servicefilerna ar uppdelade i paket med bakatkompatibla fasader
(2026-07-02). Fasaden (gamla modulvagen) re-exporterar alla namn sa befintliga
imports fungerar, men ny kod ska importera direkt fran paketet och tester ska
monkeypatcha implementationsmodulen, inte fasaden.

- `app/backend/data_fetch/`: `core` (konstanter, katalogtyper, primitiver),
  `catalog` (katalogladdning/kontext), `plan` (MiniMax-payload och validering),
  `segments` (retention-/arkivsegmentering), `engine` (deterministiska filter
  och berakningar inkl. package breakdown), `present` (SQL-text och kolumner).
  Fasad: `data_fetch_service.py`.
- `app/backend/mcp/`: `protocol` (MCP-konfig, fel, HTTP-session), `tooling`
  (tool-/resurs-/promptsummering och kontextinsamling), `providers`
  (LLM-providerval), `chat` (provideranrop och meddelandebyggare), `service`
  (orkestrering `ask_mcp`/`list_mcp_tools`). Fasad: `mcp_service.py`.
- `app/backend/sankey_inbound/`: `common` (konstanter, dataklasser), `cache`
  (payload-/kallradscache), `trace` (trace-tokens och CSV), `rows`
  (radnormalisering, perioder, priser), `build` (grafbygget), `fetch`
  (datahamtning/segment/snapshots), `service` (orkestrering
  `load_sankey_inbound_payload`). Fasad: `sankey_inbound_service.py`.

## Bakgrundsjobb

Alla uppstartsjobb registreras i `BACKGROUND_JOBS` i `app/backend/main.py` och
startas av FastAPI-lifespan via runnern i `app/backend/background.py`. Runnern
ager tradar, felhantering och status; jobbstatus visas i healthcheck-rapporten
under `background_jobs`. Nya bakgrundsjobb ska registreras dar, inte skapas som
egna tradar eller startup-hooks. Registret antar exakt en uvicorn-worker -
kontraktstest skyddar Dockerfile-CMD mot `--workers`.

## Arkitektur-kontraktstester

`tests/tools/test_architecture_contracts.py` haller tre invariants:

- Radtak (1000) for backend-Python och frontend-JS, med undantagslista dar
  befintliga for stora filer far krympa men inte vaxa.
- Dockerfile-CMD far inte fa `--workers`/gunicorn utan ledarlas for schedulerna.
- Domangranser: servicemoduler far importera delad grund och sin egen doman;
  nya beroenden mellan domaner maste laggas till medvetet i
  `ALLOWED_DOMAIN_EDGES`.

## Backend-routerkarta

- `auth.py`: login, logout, aktuell anvandare, satt forsta losenord.
- `schedule.py` och `bulk.py`: dagsschema, celler, split, bulk, restore, summary, copy, clear, fill-from-left.
- `overview.py`: vecka/manad och heldagsandringar.
- `persons.py` och `person_schedules.py`: personregister, import och veckomall.
- `activities.py`, `areas.py`: aktiviteter och omraden.
- `users.py`, `settings.py`: anvandare, appsettings, sidebar och roll-vyatkomst.
- `audit_logs.py`: historik och summering.
- `data_fetch.py`: MiniMax-planerad datahamtning fran extern datakalla, katalogstatus och Excel-export.
- `productivity.py`: produktivitetsstatus, KPI-fil, personrapport och manuell API-snapshot-sync.
- `productivity_sync.py`: global schemalagd Produktivitet-snapshot vid startup och varje hel-/halvtimme samt daglig historik-backfill bakat.
- `productivity_kpi_rules.py`: KPI-mal fran `v_ask_kpi_target`, intern `kpi.sql`-baserad logik, personmatchning och schedule-aware rapportmodell.
- `allocation.py`: lagerverktyg, filidentifiering, kor flode, resultat, Excel/CSV.
- `public.py`: enkla publika text/CSV-varden for timmar, personer och summering.

## Klientlagring

- `localStorage`: tema, sidebar-collapse, sidebar-layout-cache, role-view-access-cache.
- `sessionStorage`: vald datumkontext, sidebar-user-cache, upload notice, dokumentlogg och kortlivad GET-/vycache for snabb navigation.
- IndexedDB `flow-allokering-files`: lokala filer for lagerverktyg.
- Sidinit anvander cachad roll-/menylayout for att rita sidebar och kontrollera vyatkomst utan att blockera varje sidbyte pa `/api/settings/role-access` och `/api/settings/sidebar`. Servern friskas fortfarande upp i bakgrunden och mutationer rensar GET-cachen via `api.js`.

## Deployment och lokal drift

- Officiell drift sedan 2026-07 ar foretagets Kubernetes (nowasteserver):
  manifest i `k8s/` (namespace `flow`, 1 replika, PVC:er for data/media),
  deploy via Octopus-projektet **Flow**, databas MSSQL. Development-miljon ar
  `flow-development.nowastelogistics.com`. Release- och branchmodellen
  beskrivs i [nowaste-git-release.md](nowaste-git-release.md).
- **Miljotopologi och DB-latens (viktigt for prestandabedomning):**
  development-miljons k8s-kluster kor i **Proacts datacenter** medan SQL
  Servern (tst-effect40) ligger i **Azure northeurope** → ~37 ms natverkslatens
  per databasfraga. I **produktionsmiljon ligger bada i samma datacenter**
  (bekraftat av Mikael Hallin 2026-07-04), sa latensskatten finns inte dar.
  Konsekvens: development ar 3–8× langsammare an prod pa fragetunga endpoints
  (uppmatt 2026-07-04: `/api/schedule` 177 ms pa Render vs 1 007 ms i dev-k8s) —
  extrapolera aldrig prestanda fran development till prod. Fragetunga vyer
  (20+ sekventiella DB-fragor per klick) bor anda batchas pa sikt.
  Benchmarka med `tools.api_benchmark` (se [testing-release.md](testing-release.md)).
- **Octopus-projektvariabler blir inte automatiskt env i podden** — deploy-
  processen maste mappa in dem (Mickes doman). Symptom nar mappning saknas:
  `SUPER_USER_USERNAMES`/`ARCHIVE_CACHE_*` utan effekt, tom Seq (OTel-env).
- Render-driften ar avvecklad (2026-07-03); `render.yaml` och
  `backend.migrate_pg_to_mssql` ar borttagna ur repot och finns i git-historiken.
- `scripts\start_local.bat` startar lokal SQLite-baserad testmiljo i snabbt anvandarlage utan `uvicorn --reload` och utan implicit live-sync.
- `scripts\start_dev.bat` startar samma lokala server med `uvicorn --reload` nar kod utvecklas.
- `scripts\sync_live_local.bat` gor en explicit env-styrd live-till-SQLite-kopia innan lokal start. Bara att `LIVE_DATABASE_URL` finns i miljön ska inte langre gora vanlig start langsam eller forsoka ersatta en last `flow_local.db`.
- `tools.visual_smoke`, `tools.interactive_e2e` och desktop-prober skapar temporara databaser for tester.

## Kallor

- `../app/backend/main.py`
- `../desktop/app.py`
- `../desktop/local_app_server.py`
- `../app/README.md`
- `../APP_MIGRATION_PLAN.md`

---
title: Arkitektur
status: aktiv
updated: 2026-07-02
tags: [arkitektur, backend, frontend, desktop]
---

# Arkitektur

Kort svar: `app/` ar FastAPI + statisk vanilla JS. `desktop/` ar ett PyQt6-skal som startar en lokal appyta och proxar `/api/*` till samma centrala backend. `warehouse_tools/` innehaller lagerverktyg som exponeras via backendens allokeringsbrygga.

## Webbapp

- Backend: Python, FastAPI, SQLAlchemy 2, Alembic.
- Frontend: statiska HTML/CSS/JS-filer utan buildsteg.
- Auth: session-cookie via FastAPI `SessionMiddleware`.
- Databas: PostgreSQL i produktion; SQLite anvands for lokal test/probe.
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
kontraktstest skyddar `render.yaml` mot `--workers`.

## Arkitektur-kontraktstester

`tests/tools/test_architecture_contracts.py` haller tre invariants:

- Radtak (1000) for backend-Python och frontend-JS, med undantagslista dar
  befintliga for stora filer far krympa men inte vaxa.
- `render.yaml` far inte fa `--workers`/gunicorn utan ledarlas for schedulerna.
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

- `render.yaml` beskriver Render-drift.
- `start_local.bat` startar lokal SQLite-baserad testmiljo i snabbt anvandarlage utan `uvicorn --reload` och utan implicit live-sync.
- `start_dev.bat` startar samma lokala server med `uvicorn --reload` nar kod utvecklas.
- `sync_live_local.bat` gor en explicit env-styrd live-till-SQLite-kopia innan lokal start. Bara att `LIVE_DATABASE_URL` finns i miljön ska inte langre gora vanlig start langsam eller forsoka ersatta en last `flow_local.db`.
- `tools.visual_smoke`, `tools.interactive_e2e` och desktop-prober skapar temporara databaser for tester.

## Kallor

- `../app/backend/main.py`
- `../desktop/app.py`
- `../desktop/local_app_server.py`
- `../app/README.md`
- `../APP_MIGRATION_PLAN.md`

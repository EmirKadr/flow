---
title: Arkitektur
status: aktiv
updated: 2026-09-17
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

## Backend-routerkarta

- `auth.py`: login, logout, aktuell anvandare, satt forsta losenord.
- `schedule.py` och `bulk.py`: dagsschema, celler, split, bulk, restore, summary, copy, clear, fill-from-left.
- `overview.py`: vecka/manad och heldagsandringar.
- `persons.py` och `person_schedules.py`: personregister, import och veckomall.
- `activities.py`, `areas.py`: aktiviteter och omraden.
- `users.py`, `settings.py`: anvandare, appsettings, sidebar och roll-vyatkomst.
- `audit_logs.py`: historik och summering.
- `data_fetch.py`: MiniMax-planerad datahamtning fran extern datakalla, katalogstatus och Excel-export.
- `productivity.py`: produktivitetsstatus, KPI-fil, rapport och session/loggfiler.
- `allocation.py`: lagerverktyg, filidentifiering, kor flode, resultat, Excel/CSV.
- `public.py`: enkla publika text/CSV-varden for timmar, personer och summering.

## Klientlagring

- `localStorage`: tema, sidebar-collapse, sidebar-layout-cache, role-view-access-cache.
- `sessionStorage`: vald datumkontext, sidebar-user-cache, upload notice, dokumentlogg och kortlivad GET-/vycache for snabb navigation.
- IndexedDB `flow-allokering-files`: lokala filer for lagerverktyg.
- IndexedDB `flow-productivity-files`: lokala produktivitetsloggar.

## Deployment och lokal drift

- `render.yaml` beskriver Render-drift.
- `start_local.bat` startar lokal SQLite-baserad testmiljo och kan kopiera live-data till lokal DB om `LIVE_DATABASE_URL` finns.
- `tools.visual_smoke`, `tools.interactive_e2e` och desktop-prober skapar temporara databaser for tester.

## Byte av publik adress

Den 17 september 2026 återställs `https://stigamo.nu` som huvudadress.
Alla appvyer och API:er är åter tillgängliga enligt vanliga inloggnings- och
behörighetsregler. Gårdagens domänomdirigering och 410-spärr är borttagna.
Gamla sidalias som `/stallen` omdirigeras fortsatt inom samma domän.
`/d-pak`, `/d-pak/` och `/dpak-fraga.html` fortsätter öppna den publika chatten.

Appvyerna laddar inte längre `site_migration.js`. Filen finns kvar som ett
tomt kompatibilitetsskript för cachad HTML. Redan laddade äldre skript kan
fortfarande fråga `GET /api/site-migration`; endpointen svarar alltid
`active: false`, `target_origin: https://stigamo.nu` och `Cache-Control: no-store`.
Det hindrar kvarvarande migrationskod i öppna flikar från att flytta användaren.
En flik som redan finns på den andra domänen behöver öppnas på stigamo.nu igen.

Windows-klientens standardserver och CLI/hjälplänkar använder stigamo.nu igen.
`FLOW_SERVER_BASE_URL` kan fortsatt ange en annan server. Äldre installationer
som redan använder stigamo.nu fungerar igen utan ny installerare. Den här
återställningen flyttar inga användardata, cookies eller lokala filer mellan
domäner och ändrar inte den andra domänens drift. Vanlig loggning av inloggning,
fel och sparningar gäller igen; inget flyttbesked visas.

Källor: `../app/backend/main.py`, `../app/frontend/js/site_migration.js`,
`../core/app_info.py` och `../desktop/local_app_server.py`.

## Kallor

- `../app/backend/main.py`
- `../desktop/app.py`
- `../desktop/local_app_server.py`
- `../app/README.md`
- `../APP_MIGRATION_PLAN.md`

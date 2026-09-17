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

Den 17 september 2026 aktiveras domänflytten igen efter den tillfälliga återställningen.
Från driftsättningen skickas besök på `stigamo.nu` och
`www.stigamo.nu` direkt till `https://flow.nowastelogistics.com` med samma sökväg
och query. Omdirigeringen är HTTP 302 med `Cache-Control: no-store`. Regeln
ligger före autentisering och gäller samtliga roller och vyer, även login,
Meta-uppladdning, gamla alias och okända sidlänkar. Den nya domänen och lokal
utveckling omdirigeras inte.

Undantaget är D-pak: `/d-pak`, `/d-pak/`, `/dpak-fraga.html`, chattens exakta
status-/meddelandeendpoints och dess statiska resurser stannar kvar.
`/api/health` och `/api/site-migration` är också tillgängliga för drift respektive
klientens adresskontroll. Andra API-anrop och alla övriga skrivningar mot den
gamla domänen stoppas före handlern med HTTP 410, `code: site_moved` och den nya
adressen i feltexten. Detta gäller även integrationer och tidigare öppnade flikar.
Skrivningar, lösenord och uppladdningar skickas aldrig vidare automatiskt.

Alla appvyer laddar `site_migration.js`, som flyttar även cachad HTML och
kontrollerar adressen igen när fliken visas. En flik som laddades före deploy
saknar denna kod men kan inte läsa/spara via det gamla API:t; dess befintliga
felhantering visar flyttbeskedet. Vid klientstyrd flytt visas en blockerande
länk till den nya adressen medan navigationen pågår. Ingen ny auditmutation
görs på den avstängda domänen.

Windows-klientens standardserver är den nya domänen. `FLOW_SERVER_BASE_URL`
kan fortsatt ange en lokal testserver. Den delade frontendkontrollen fungerar
även genom desktop-proxyn när den är konfigurerad mot gamla domänen. Redan
installerade äldre Windows-versioner får samma 410-besked tills de uppdateras
eller konfigureras för den nya servern; en kodpush publicerar ingen installerare.
Cookies och lokalt lagrade filer/inställningar flyttas inte mellan domäner;
användaren kan behöva logga in och välja lokala filer igen.

Källor: `../app/backend/site_migration.py`, `../app/frontend/js/site_migration.js`,
`../core/app_info.py` och `../desktop/local_app_server.py`.

## Kallor

- `../app/backend/main.py`
- `../desktop/app.py`
- `../desktop/local_app_server.py`
- `../app/README.md`
- `../APP_MIGRATION_PLAN.md`

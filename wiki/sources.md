---
title: Kallmanifest
status: aktiv
updated: 2026-05-22
tags: [wiki, kallor]
---

# Kallmanifest

Kort svar: wikin ar syntetiserad fran repo-filerna nedan. Raa kallor ska normalt inte redigeras som del av wikiunderhall, utom nar uppgiften faktiskt ar att andra produkten.

## Extern strukturkalla

- Karpathy gist `llm-wiki.md`: beskriver iden med en persistent LLM-underhallen markdown-wiki, med `index.md`, `log.md`, kallor och schema/agentregler.

## Repo-regler och befintlig dokumentation

- `../AGENTS.md` - paritetsregel: webbappen och Windows-appen ar samma produkt.
- `../app/README.md` - produkt, stack, lokal utveckling och multi-user-modell.
- `../API_ROUTES.md` - namngivna API-vagar och CLI-kontrakt.
- `../APP_MIGRATION_PLAN.md` - nulage, risker och appmigreringsplan.
- `../TESTPROTOCOL.md` - testkommandon, visuella tester och releasekontroll.
- `../../ALLOKERING_FILKUNSKAP.md` - gemensam fil- och kolumnkunskap for ASK/WMS/Excel-underlag.

## Frontend-kallor

- `../app/frontend/index.html`, `../app/frontend/js/schedule.js` - Bemanning dagsschema.
- `../app/frontend/overblick.html`, `../app/frontend/js/overview.js` - Oversikt.
- `../app/frontend/personer.html`, `../app/frontend/js/persons.js` - Personregister och veckomallar.
- `../app/frontend/aktiviteter.html`, `../app/frontend/js/activities.js` - Aktiviteter.
- `../app/frontend/anvandare.html`, `../app/frontend/js/users.js` - Anvandare, settings och vybehorigheter.
- `../app/frontend/verksamheter.html`, `../app/frontend/js/businesses.js` - Super User-vyn for verksamheter.
- `../app/frontend/historik.html`, `../app/frontend/js/analytics.js` - Historik/audit.
- `../app/frontend/produktivitet.html`, `../app/frontend/js/productivity.js`, `../app/frontend/js/productivity_uploads.js` - Produktivitet och filval.
- `../app/frontend/uppladdningar.html`, `../app/frontend/bearbeta.html`, `../app/frontend/dela.html`, `../app/frontend/js/allocation_tools.js` - lagerverktyg.
- `../app/frontend/js/common.js` - sidebar, tema, omradesfokus, toast, logg, gemensam filuppladdning och auth-guard.
- `../app/frontend/js/api.js` - fetch-wrapper, auth-redirects och nedladdningar.

## Backend-kallor

- `../app/backend/main.py` - FastAPI-app, statiska filer, middleware och router-mounts.
- `../app/backend/models.py` - SQLAlchemy-tabeller.
- `../app/backend/schemas.py` - Pydantic-kontrakt.
- `../app/backend/deps.py`, `../app/backend/user_access.py` - auth, roller och vyatkomst.
- `../app/backend/business_scope.py`, `../app/backend/routers/businesses.py`, `../app/alembic/versions/0018_businesses.py` - verksamheter, isolering och backfill.
- `../app/backend/settings_service.py`, `../app/backend/routers/settings.py` - verksamhetsspecifika settings.
- `../app/backend/routers/schedule.py`, `../app/backend/routers/bulk.py`, `../app/backend/routers/overview.py` - schema och oversikt.
- `../app/backend/routers/persons.py`, `../app/backend/routers/person_schedules.py`, `../app/backend/routers/activities.py`, `../app/backend/routers/areas.py`, `../app/backend/routers/users.py` - register.
- `../app/backend/routers/audit_logs.py`, `../app/backend/audit.py` - auditlogg.
- `../app/backend/productivity_service.py`, `../app/backend/routers/productivity.py`, `../app/backend/routers/public.py` - produktivitet och publika CSV/API-varden.
- `../app/backend/allocation_bridge.py`, `../app/backend/routers/allocation.py` - lagerverktygens API-brygga.

## Desktop- och verktygskallor

- `../desktop/app.py`, `../desktop/local_app_server.py`, `../desktop/web_view.py`, `../desktop/main.py` - Windows-skal och lokal appserver.
- `../warehouse_tools/catalog.py`, `../warehouse_tools/flows.py`, `../warehouse_tools/detect.py` - lagerfloden, filslotar och filidentifiering.
- `../tools/flow_cli.py`, `../tools/visual_smoke.py`, `../tools/interactive_e2e.py`, `../tools/desktop_app_probe.py` - agentverktyg och teststod.

## Testkallor

- `../tests/services/test_business_scope.py` - verksamhetsisolering mellan Stigamo och R3.
- `../tests/tools/test_visual_tools.py` - visuella kontrakt for dynamisk toggle, Verksamheter-vyn och Super User-falt.

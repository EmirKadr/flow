---
title: API-karta
status: aktiv
updated: 2026-05-25
tags: [api, backend]
---

# API-karta

Kort svar: `API_ROUTES.md` ar kontraktslistan och testas mot FastAPI-appen via `tools.flow_cli`. Denna sida grupperar API:t efter anvandarfloden.

## Auth och halsa

- `GET /api/health` - serverstatus.
- `POST /api/auth/login` - logga in.
- `POST /api/auth/logout` - logga ut.
- `GET /api/auth/me` - aktuell anvandare, roller, Super User-status och verksamhet.
- `POST /api/auth/set-password` - satt forsta losenord.
- `POST /api/assistant/chat` - skickar hela apphjalpsdialogen och aktuell sida till MiniMax via backend.
- `POST /api/assistant/clear` - nollstaller apphjalpens serverkvot i aktuell session.
- `GET /api/query-data/health` - kontrollerar extern datakatalog och om API/MiniMax ar konfigurerade; returnerar `api_missing` med saknade env-namn.
- `POST /api/query-data/catalog/reload` - rensar katalogcache och laser om vy-/kolumnkatalogen.
- `POST /api/query-data/plan` - tolkar en svensk datafraga med MiniMax till validerad vy/filter/kolumn-plan.
- `POST /api/query-data/run` - kor en validerad plan mot extern datakälla och returnerar tabellpreview.
- `GET /api/query-data/export/{session_id}` - laddar ner senaste datahamtning som Excel.

## Bemanning och oversikt

- `GET /api/schedule` - hamta dagsschema, scopeat till anvandarens verksamhet eller `business_id` for Super User.
- `PUT /api/schedule/cell` - satt en cell/ett segment.
- `PUT /api/schedule/cell/split` - dela eller sla ihop timme.
- `POST /api/schedule/cells` - bulk-satt flera celler, anvands vid drag.
- `PUT /api/schedule/hours/restore` - undo/redo for Bemanning och Oversikt.
- `GET /api/schedule/summary` - summering per aktivitet.
- `GET /api/schedule/revision` - latt revisionsnyckel for aktuell schemaperiod, anvands for tyst bakgrundsrefresh.
- `POST /api/schedule/copy` - kopiera dag/vecka.
- `POST /api/schedule/clear` - rensa schema.
- `POST /api/schedule/fill-from-left` - fyll tomma celler fran vanster.
- `GET /api/overview` - veckoversikt, scopead per verksamhet.
- `GET /api/overview/month` - manadsoversikt, scopead per verksamhet.
- `GET /api/overview/revision`, `/api/overview/revision/month` - latta revisionsnycklar for tyst bakgrundsrefresh.
- `POST /api/overview/day` - satt en hel dag.
- `POST /api/overview/days/bulk` - satt flera dagar via drag.

## Register och settings

- `GET/POST/PUT/DELETE /api/persons...`, `POST /api/persons/import-rows` - personregister, Excelimport och direktimport fran tabellrader.
- `GET/PUT /api/persons/{id}/schedule` - veckomall.
- `GET/POST/PUT/DELETE /api/activities...`, `POST /api/activities/import-rows` - aktivitetsregister, Excelimport och direktimport fran tabellrader.
- `GET/POST/PUT/DELETE /api/areas...` - omraden. Delete tar bort tomma omraden men inaktiverar omradet om personer, aktiviteter eller anvandare redan pekar pa det.
- `GET/POST/PUT/DELETE /api/users...`, `POST /api/users/import-rows` - anvandare, Excelimport, direktimport fran tabellrader och permanent borttagning.
- `GET/POST/PUT /api/businesses...` - Super User-vy for verksamheter.
- `GET/PUT /api/settings` - appsettings per verksamhet.
- `GET/PUT /api/settings/sidebar` - sidebar per verksamhet.
- `GET/PUT /api/settings/role-access` - roll-vyatkomst per verksamhet.

Alla registerlistor ovan ar verksamhetsscopeade. Icke-Super Users far bara egen
verksamhet. Super User kan anvanda `business_id` dar API:t accepterar filter
eller skapa/importera med explicit verksamhet.

## Historik, produktivitet och lager

- `GET /api/audit`, `GET /api/audit/summary`, `GET /api/audit/errors` - historik, analytics och felkodsdashboard.
- `POST /api/audit/client-error` - tyst klientrapportering av API-fel som anvandaren traffar; sparar sanerad path/status/felkod utan request body eller queryvarden.
- `GET /api/productivity/files`, `GET /api/productivity/targets`, `POST /api/productivity/files`, `POST /api/productivity/files/raw`, `DELETE /api/productivity/files/{file_type}`, `GET /api/productivity` - produktivitet.
- `GET /api/allokering/health`, `/flows`, `/pool`, `POST /detect`, `POST /flow/{flow_id}`, `POST /open-excel`, `GET /table-column/...`, `GET /download/...` - lagerverktyg.
- `GET /api/public/...` - publika text/CSV-summeringar for timmar/personer. Queryparametern `business` defaultar till `STIGAMO`; publika endpoints summerar inte globalt.

## Agentkommandon

```powershell
python -m tools.flow_cli routes --format table
python -m tools.flow_cli routes --format markdown
python -m tools.flow_cli api GET /api/health
```

## Kallor

- `../API_ROUTES.md`
- `../tools/flow_cli.py`
- `../app/backend/business_scope.py`
- `../tests/tools/test_flow_cli.py`

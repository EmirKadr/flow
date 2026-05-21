---
title: API-karta
status: aktiv
updated: 2026-05-21
tags: [api, backend]
---

# API-karta

Kort svar: `API_ROUTES.md` ar kontraktslistan och testas mot FastAPI-appen via `tools.bemanning_cli`. Denna sida grupperar API:t efter anvandarfloden.

## Auth och halsa

- `GET /api/health` - serverstatus.
- `POST /api/auth/login` - logga in.
- `POST /api/auth/logout` - logga ut.
- `GET /api/auth/me` - aktuell anvandare och roller.
- `POST /api/auth/set-password` - satt forsta losenord.
- `POST /api/assistant/chat` - skickar hela apphjalpsdialogen och aktuell sida till MiniMax via backend.
- `POST /api/assistant/clear` - nollstaller apphjalpens serverkvot i aktuell session.
- `GET /api/query-data/health` - kontrollerar privat extern datakatalog och om API/MiniMax ar konfigurerade.
- `POST /api/query-data/catalog/reload` - rensar katalogcache och laser om vy-/kolumnkatalogen.
- `POST /api/query-data/plan` - tolkar en svensk datafraga med MiniMax till validerad vy/filter/kolumn-plan.
- `POST /api/query-data/run` - kor en validerad plan mot extern datakälla och returnerar tabellpreview.
- `GET /api/query-data/export/{session_id}` - laddar ner senaste datahamtning som Excel.

## Bemanning och oversikt

- `GET /api/schedule` - hamta dagsschema.
- `PUT /api/schedule/cell` - satt en cell/ett segment.
- `PUT /api/schedule/cell/split` - dela eller sla ihop timme.
- `POST /api/schedule/cells` - bulk-satt flera celler, anvands vid drag.
- `PUT /api/schedule/hours/restore` - undo/redo for Bemanning och Oversikt.
- `GET /api/schedule/summary` - summering per aktivitet.
- `POST /api/schedule/copy` - kopiera dag/vecka.
- `POST /api/schedule/clear` - rensa schema.
- `POST /api/schedule/fill-from-left` - fyll tomma celler fran vanster.
- `GET /api/overview` - veckoversikt.
- `GET /api/overview/month` - manadsoversikt.
- `POST /api/overview/day` - satt en hel dag.
- `POST /api/overview/days/bulk` - satt flera dagar via drag.

## Register och settings

- `GET/POST/PUT/DELETE /api/persons...` - personregister och import.
- `GET/PUT /api/persons/{id}/schedule` - veckomall.
- `GET/POST/PUT/DELETE /api/activities...` - aktivitetsregister och import.
- `GET/POST/PUT /api/areas...` - omraden.
- `GET/POST/PUT /api/users...` - anvandare och import.
- `GET/PUT /api/settings` - appsettings.
- `GET/PUT /api/settings/sidebar` - global sidebar.
- `GET/PUT /api/settings/role-access` - global roll-vyatkomst.

## Historik, produktivitet och lager

- `GET /api/audit`, `GET /api/audit/summary` - historik och analytics.
- `GET /api/productivity/files`, `GET /api/productivity/targets`, `POST /api/productivity/files`, `POST /api/productivity/files/raw`, `DELETE /api/productivity/files/{file_type}`, `GET /api/productivity` - produktivitet.
- `GET /api/allokering/health`, `/flows`, `/pool`, `POST /detect`, `POST /flow/{flow_id}`, `POST /open-excel`, `GET /table-column/...`, `GET /download/...` - lagerverktyg.
- `GET /api/public/...` - publika text/CSV-summeringar for timmar/personer.

## Agentkommandon

```powershell
python -m tools.bemanning_cli routes --format table
python -m tools.bemanning_cli routes --format markdown
python -m tools.bemanning_cli api GET /api/health
```

## Kallor

- `../API_ROUTES.md`
- `../tools/bemanning_cli.py`
- `../tests/tools/test_bemanning_cli.py`

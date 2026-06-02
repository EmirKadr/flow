---
title: API-karta
status: aktiv
updated: 2026-06-02
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
- `GET /api/schedule/presence` - narvarolista for utskrift fran Bemanning/Oversikt. `area_id` begransar till omrade; utan `area_id` grupperas svaret per verksamhet.
- `POST /api/schedule/copy` - kopiera dag/vecka.
- `POST /api/schedule/clear` - rensa schema.
- `POST /api/schedule/fill-from-left` - fyll tomma celler fran vanster.
- `GET /api/overview` - veckoversikt, scopead per verksamhet.
- `GET /api/overview/month` - manadsoversikt, scopead per verksamhet.
- `GET /api/overview/revision`, `/api/overview/revision/month` - latta revisionsnycklar for tyst bakgrundsrefresh.
- `POST /api/overview/day` - satt en hel dag.
- `POST /api/overview/days/bulk` - satt flera dagar via drag.
- `PUT /api/persons/sort-order` - sparar ny personordning nar personnamn dras i Bemanning eller Oversikt. Vanliga admin/bemanningsansvariga sorterar eget omrade; Super User och demo kan sortera alla synliga personer med `personSortOrder=edit`.
- `GET /api/personal/persons` - personval for Mitt schema/Min produktivitet. Super User far alla aktiva personer; rollen `person` far bara sin egen kopplade person.
- `GET /api/personal/schedule` - veckopayload for en persons schema med dagar, segment, status och aktivitetssummering. `person_id` accepteras bara for Super User.
- `GET /api/personal/productivity` - dagsvy for en persons produktivitet/schematid baserad pa samma personliga schemapayload. `date` valjer dag.

## Register och settings

- `GET/POST/PUT/DELETE /api/persons...`, `POST /api/persons/import-rows`, `PUT /api/persons/sort-order` - personregister med obligatoriskt `NoMan` for nya personer och import, Excelimport, direktimport fran tabellrader och begransad sortering fran planeringsvyerna.
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
- `POST /api/audit/client-error` - tyst klientrapportering av API-fel som anvandaren traffar, inklusive sidmoduler med egen fetch-wrapper via `window.reportApiError`; sparar sanerad path/status/felkod utan request body eller queryvarden.
- `POST /api/audit/client-event` - tyst klientrapportering av auditbara UI-handlingar som sidoppning; sparar sanerad path och vyinfo utan att skriva i dokumentloggen.
- `GET /api/healthcheck` - Super User-halsa for app, databas och Render-koppling. Render-data hamtas bara nar `RENDER_API_KEY` och resurs-id finns i secrets; build-loggar anvander Render `ownerId` + service-id och kan falla tillbaka pa `RENDER_OWNER_ID`.
- `POST /api/healthcheck/wait-metrics` - tyst insamling av anvandarens vantetider for vyload, API-anrop, nedladdningar och bakgrundsladdning. Payloaden ar sanerad till event, vy, steg, duration, status och begransad teknisk detalj.
- `GET /api/healthcheck/wait-metrics/summary` - Super User-summering for Historik-fliken `Vantetider` och CLI-verktyget `tools.healthcheck`.
- `GET /api/productivity/files`, `GET /api/productivity/targets`, `GET /api/productivity` - produktivitet, kraver `productivity=view`.
- `POST /api/productivity/files`, `POST /api/productivity/files/raw`, `DELETE /api/productivity/files/{file_type}` - serverhanterade produktivitetsfiler, kraver `productivity=edit`. Raw-upload av Plocklogg, Translogg och Palllastningslogg uppdaterar dessutom verksamhetens sammanstallda csv.gz-observationer.
- `GET /api/coredata/files` - listar verksamhetens permanenta coredata-karnfiler fran Postgres-tabellen `coredata_files` med filbaserad fallback, samt sammanstalld data som `artikel_max.csv`, `productivity_pick_observations`, `productivity_trans_observations` och `productivity_pallet_observations`.
- `GET /api/coredata/files/{file_key}/preview` - forhandsvisar en serverlagrad coredata-karnfil eller sammanstalld datafil for anvandarens verksamhet. Svaret innehaller begransad textpreview, filnamn, storlek och metadata men ska inte anvandas for full nedladdning.
- `POST /api/coredata/files/raw` - laddar upp en coredata-karnfil eller sammanstalld datafil till anvandarens verksamhet och ersatter aldre fil med samma prefix, kraver `allocationUploads=edit`. Coredata-karnfiler sparas som blobbar i Postgres; sammanstalld data behaller sitt befintliga lagringsflode.
- `GET /api/allokering/health`, `/flows`, `/pool`, `GET/PUT /process-matrix`, `GET/PUT /ytgenerering-map-layout`, `POST /detect`, `POST /flow/{flow_id}`, `POST /open-excel`, `GET /table-column/...`, `GET /download/...` - lagerverktyg. `ytgenerering-map-layout` kraver `allocationSettings` och returnerar aven `available_locations` fran aktiv verksamhets `location`-karnfil.
- `GET /api/public/...` - publika text/CSV-summeringar for timmar/personer. Queryparametern `business` defaultar till `STIGAMO`; publika endpoints summerar inte globalt.
- `POST /api/meta/uploads` - publik multipart-uppladdning for flera bilder/videor utan inloggning. Sparar filer i `meta_media_uploads` med tidsstamplat `stored_filename`, `content_hash`, eventuell `duration_seconds` och status `pending_analysis`. Exakta dubbletter hoppas over och returneras i `skipped`. Fel som hinner na backend loggas sanerat som `meta_media_upload/upload_failed`, sa anonyma 4xx/5xx fran den publika sidan syns i Historik > Felkoder utan filnamn eller filinnehall.
- `GET /api/meta/uploads`, `GET /api/meta/uploads/{upload_id}/content`, `DELETE /api/meta/uploads/{upload_id}` - Super User-endpoints for Meta-vyn. Listan returnerar metadata utan blobbinnehall, inklusive hash och videolangd nar den finns; content-endpointen kan visa/ladda ner bild/video och stoder byte-range for videospelning. Delete-endpointen raderar raden och blobben.
- `GET /api/meta/shipment-observations`, `POST /api/meta/uploads/{upload_id}/analyze` - Super User-endpoints for sändningsanalys av Meta-videor. Analyslistan returnerar ordernummer, sändningsnummer, videons filnamn, Video-ID/hash och langd via kopplad media-rad. Analysen använder Gemini när `GEMINI_API_KEY` finns och ska väga ihop både video, ljud, transportetikett och innehållsförteckning.

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
- `../app/backend/routers/coredata.py`
- `../tests/tools/test_flow_cli.py`

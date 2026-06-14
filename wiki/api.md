---
title: API-karta
status: aktiv
updated: 2026-06-14
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
- `GET/PUT /api/schedule/calculator-profile` - hamta/spara anvandarens automatiska bemanningskalkyler och tillgangliga processval.
- `POST /api/schedule/calculator-profile/import` - kopiera automatiska bemanningskalkyler fran annan atkomlig anvandare.
- `GET /api/schedule/calculator/automatic` - beraknar automatiska bemanningskalkyler for vald ISO-dag med orderrader, kvarvarande schematid och historiskt processnitt.
- `GET /api/schedule/activity-capacity` - returnerar historiskt snitt per person och vald bemanningsaktivitet. Svaret grupperas per `person_id` och `activity_id`, bygger pa aktivitetens KPI-process, KPI-malens matetal och historikgransen i `staffing_history_hours` (default 40 timmar), och respekterar `staffing_activity_capacity_activity_ids`.
- `GET /api/schedule/activity-capacity/cell` - returnerar historiskt snitt for en person och en aktivitet vid hover i Bemanning. Klienten skickar `year`, `week`, `weekday`, `person_id` och `activity_id`; svaret innehaller antingen `capacity` med enheter per timme eller en kort `reason`.
- `GET /api/schedule/productivity-summary` - returnerar en latt personprocentkarta for Bemannings produktivitetskolumn. Den laser materialiserade `person_productivity_daily`-cellrader och skickar bara `people.{person_id}` med procent, poang, planpoang och KPI-minuter.
- `POST /api/schedule/copy` - kopiera dag/vecka.
- `POST /api/schedule/clear` - rensa schema.
- `POST /api/schedule/fill-from-left` - fyll tomma celler fran vanster.
- `POST /api/rfid/scans` - tar emot scan fran en fysisk RFID-modul. Payloaden innehaller `module_name`, brickkod och valfritt device-id; backend matchar modulnamnet mot aktivitet och brickkoden mot `Person.rfid_code`. Om `RFID_DEVICE_TOKEN` ar satt maste modulen skicka samma varde i `X-Flow-RFID-Token`.
- `GET /api/rfid/events` - listar RFID-stamplingar for vald ISO-dag i Bemanning, filtrerat pa anvandarens verksamhet och valfritt `area_id`.
- `POST /api/rfid/events/{event_id}/apply` - applicerar en pending RFID-stampling i Bemanning fran scannad minut till timslut och returnerar de nya schemasegmenten.
- `POST /api/rfid/events/{event_id}/ignore` - satter RFID-stamplingen som ignorerad utan att radera den fran historik eller Bemanningsmarkeringar.
- `GET /api/overview` - veckoversikt, scopead per verksamhet.
- `GET /api/overview/month` - manadsoversikt, scopead per verksamhet.
- `GET /api/overview/revision`, `/api/overview/revision/month` - latta revisionsnycklar for tyst bakgrundsrefresh.
- `POST /api/overview/day` - satt en hel dag.
- `POST /api/overview/days/bulk` - satt flera dagar via drag.
- `PUT /api/persons/sort-order` - sparar ny personordning nar personnamn dras i Bemanning eller Oversikt. Vanliga admin/bemanningsansvariga sorterar eget omrade; Super User och demo kan sortera alla synliga personer med `personSortOrder=edit`.
- `GET /api/personal/persons` - personval for Mitt schema/Min produktivitet. Super User far alla aktiva personer; rollen `person` far bara sin egen kopplade person.
- `GET /api/personal/schedule` - veckopayload for en persons schema med dagar, segment, status och aktivitetssummering. `person_id` accepteras bara for Super User.
- `GET /api/personal/productivity` - dagsvy for en persons schema plus global personproduktivitet. `date` valjer dag; svaret innehaller `productivity.day` och `productivity.week` med aktivitetssnitt, poang, saknade snapshots och backfillstatus.

## Register och settings

- `GET/POST/PUT/DELETE /api/persons...`, `POST /api/persons/import-rows`, `PUT /api/persons/sort-order` - personregister med obligatoriskt `NoMan` for nya personer och import, valfri `rfid_code` for brickkoppling, Excelimport, direktimport fran tabellrader och begransad sortering fran planeringsvyerna.
- `GET/PUT /api/persons/{id}/schedule` - veckomall.
- `GET/POST/PUT/DELETE /api/activities...`, `POST /api/activities/import-rows` - aktivitetsregister med valfria kommaseparerade `kpi_process_name`/KPI Mal-processnamn, `work_type` (`normal` eller `vas`), Excelimport och direktimport fran tabellrader. Listan accepterar `business_id` och `area_focus` sa settingsvyer kan hamta aktiviteter for vald verksamhet.
- `GET/POST/PUT/DELETE /api/areas...` - omraden. Delete tar bort tomma omraden men inaktiverar omradet om personer, aktiviteter eller anvandare redan pekar pa det.
- `GET/POST/PUT/DELETE /api/users...`, `POST /api/users/import-rows` - anvandare, Excelimport, direktimport fran tabellrader och permanent borttagning.
- `GET/PUT /api/settings/staffing` - hamta/spara `staffing_history_hours`, historiktimmarna for historiskt snitt och automatisk bemanningskalkyl, samt `activity_capacity_activity_ids` for vilka aktiviteter som far visa hover-snitt. Accepterar `business_id` eller `area_focus`; `null` betyder alla KPI-aktiviteter och `[]` betyder inga. Lasning kraver `staffingSettings=view`, sparning kraver `staffingSettings=edit`.
- `GET/POST/PUT /api/businesses...` - Super User-vy for verksamheter med `company_codes` som verksamhetens bolagslista.
- `GET/PUT /api/settings` - appsettings per verksamhet.
- `GET/PUT /api/settings/sidebar` - sidebar per verksamhet.
- `GET/PUT /api/settings/role-access` - global roll-vyatkomst for alla verksamheter.

Alla registerlistor ovan ar verksamhetsscopeade. Icke-Super Users far bara egen
verksamhet. Super User kan anvanda `business_id` dar API:t accepterar filter
eller skapa/importera med explicit verksamhet.

## Historik, produktivitet och lager

- `GET /api/audit`, `GET /api/audit/summary`, `GET /api/audit/errors` - historik, analytics och felkodsdashboard. Super User kan filtrera med `business_id`.
- `POST /api/audit/client-error` - tyst klientrapportering av API-fel som anvandaren traffar, inklusive sidmoduler med egen fetch-wrapper via `window.reportApiError`; sparar sanerad path/status/felkod utan request body eller queryvarden.
- `POST /api/audit/client-event` - tyst klientrapportering av auditbara UI-handlingar som sidoppning; sparar sanerad path och vyinfo utan att skriva i dokumentloggen.
- `POST /api/audit/local-run` - tar emot sanerad Windows-metadata for lokala Bearbeta-/Produktivitet-korningar: feature, flode, status, filslotar, varaktighet och rad-/resultatraknare utan localRef, sokvag, filnamn eller filinnehall.
- `POST /api/audit/interactions` - batchar inloggade UI-interaktioner fran webb och desktop. Backend satter `business_id`/`user_id`, sanerar detail och sparar i `user_interaction_events`.
- `POST /api/audit/interactions/public` - allowlistad anonym tracking for den publika Meta-uppladdningen. Endast `public_meta_*`-events sparas och payloaden far inte innehalla filnamn, filvagar eller request body.
- `GET /api/audit/interactions`, `GET /api/audit/interactions/summary`, `GET /api/audit/interactions/coverage` - Super User-endpoints for Historik > Funktioner/Knappar/Kolumner/Floden med filter for period, verksamhet, anvandare, vy, eventtyp, feature, flow och fritext.
- `POST /api/audit/interactions/chat`, `POST /api/audit/interactions/chat/clear` - Historik-AI via MiniMax for trackingfragor. Chatten far aggregeringar och raw events inom limit men ska bara svara om historik/tracking och inte visa hemligheter eller blockerade falt.
- `TRACKING_ALLOW_VALUE_SAMPLES=false` ar default. Om flaggan inte satts till true strippar backend klartext-vardeprover eller ersatter dem med langd/antal aven om klienten skickar dem.
- `GET /api/healthcheck` - Super User-halsa for app, databas och Render-koppling. Render-data hamtas bara nar `RENDER_API_KEY` och resurs-id finns i secrets; build-loggar anvander Render `ownerId` + service-id och kan falla tillbaka pa `RENDER_OWNER_ID`.
- `POST /api/healthcheck/wait-metrics` - tyst insamling av anvandarens vantetider for vyload, API-anrop, nedladdningar och bakgrundsladdning. Payloaden ar sanerad till event, vy, steg, duration, status och begransad teknisk detalj.
- `GET /api/healthcheck/wait-metrics/summary` - Super User-summering for Historik-fliken `Vantetider` och CLI-verktyget `tools.healthcheck`; accepterar `business_id`.
- `GET /api/productivity` - produktivitet, kraver `productivity=view` for lasning. Rapporten anvander serverns globala personbaserade API-snapshot for pick/trans/pallet/receive/order_log/sort/base_pallet/kpi och returnerar `backfill` for historikhamtning.
- `GET /api/productivity/persons/{person_id}` - personens aktivitetssnitt for `period=week|month|year|custom`. `date` styr vecka/manad/ar och `start_date`/`end_date` styr custom. Svaret innehaller `activities[]`, totalsummering, `missing_dates` och `backfill`.
- `GET /api/productivity/overview` - periodpayload for Produktivitet med dag/vecka/manad/ar/custom, underliggande dagsrapporter, periodsummary, saknade datum och global backfillstatus.
- `POST /api/productivity/sync` - manuell sync av Produktivitetens API-snapshot for valt datum eller dagens datum, kraver `productivity=edit`.
- Produktivitetsfilroutes ar borttagna: `/api/productivity/files`, `/api/productivity/files/raw`, `/api/productivity/files/{file_type}` och `/api/productivity/targets` finns inte langre.
- `POST /api/rfid/scans`, `GET /api/rfid/events`, `POST /api/rfid/events/{id}/apply|ignore` - RFID-flodet for Bemanning. Device-endpointen ar avsiktligt separat fran inloggad UI, men kan skyddas med `RFID_DEVICE_TOKEN`; inloggade apply/ignore kraver `schedule=edit`.
- `GET /api/coredata/files` - listar verksamhetens permanenta coredata-karnfiler fran Postgres-tabellen `coredata_files` med filbaserad fallback, samt sammanstalld data som `artikel_max.csv`. Bearbeta anropar den bara for Uppladdningar eller synliga floden dar kallvalet kraver `Uppladdning`; API-installda kallor behover inte uppladdningsstatus.
- `GET /api/coredata/files/{file_key}/preview` - forhandsvisar en serverlagrad coredata-karnfil eller sammanstalld datafil for anvandarens verksamhet. Svaret innehaller begransad textpreview, filnamn, storlek och metadata men ska inte anvandas for full nedladdning.
- `GET /api/coredata/files/{file_key}/download` - laddar ner serverlagrad coredata-karnfil eller sammanstalld data forst nar anvandaren klickar explicit nedladdning.
- `POST /api/coredata/files/raw` - laddar upp en coredata-karnfil eller sammanstalld datafil till anvandarens verksamhet och ersatter aldre fil med samma prefix, kraver `allocationUploads=edit`. Coredata-karnfiler sparas som blobbar i Postgres; sammanstalld data behaller sitt befintliga lagringsflode.
- `GET /api/allokering/health`, `/flows`, `/pool`, `GET/PUT /process-matrix`, `GET/PUT /filter-profile`, `POST /filter-profile/import`, `GET/PUT /ytgenerering-map-layout`, `POST /detect`, `POST /flow/{flow_id}`, `POST /open-excel`, `GET /table-column/...`, `GET /download/...` - lagerverktyg. `GET /process-matrix` kan lasas av Bearbeta (`allocationProcess=view`) eller Installningars Bearbeta-flik (`allocationProcessMatrix=view`), medan `PUT /process-matrix` kraver `allocationProcessMatrix=edit`; bada accepterar `business_id` eller `area_focus` och sparar `allocation_process_matrix` per verksamhet. `filter-profile` sparar personliga Bearbeta-källval, filtreringar per anvandare och Ytgenereringens personliga UTL-/transportorsinstallningar; import-endpointen kopierar en annan atkomlig anvandares profil. `ytgenerering-map-layout` kraver `allocationSettings`, accepterar `business_id`/`area_focus`, sparar kartan per verksamhet och returnerar aven `available_locations` fran samma verksamhets `location`-karnfil.
- `POST /api/workflow-data/source` - desktop/runtime-endpoint som returnerar en temporar CSV for en tillaten workflow-kalla. Body ar `{ feature, flow_id, source_key }`. Behorighet styrs av malfunktionen (`allocationProcess` eller `productivity`) och svaret innehaller bara CSV + sanerade source-headers, inte privata API-detaljer.
- Desktop-only lokala endpoints finns bara i Windows-proxyn: `/api/desktop/capabilities`, `/api/desktop/jobs`, `/api/desktop/cache/sync`, `/api/desktop/files/{ref}/detect|open|open-folder` och `/api/desktop/sync/coredata`. De proxas inte som centrala serverkontrakt.
- `GET /api/public/...` - publika text/CSV-summeringar for timmar/personer. Queryparametern `business` defaultar till `STIGAMO`; publika endpoints summerar inte globalt.
- `POST /api/meta/uploads` - publik multipart-uppladdning for flera bilder/videor utan inloggning. Sparar filer i `meta_media_uploads` med tidsstamplat `stored_filename`, `content_hash`, eventuell `duration_seconds` och status `pending_analysis`. Exakta dubbletter hoppas over och returneras i `skipped`. Fel som hinner na backend loggas sanerat som `meta_media_upload/upload_failed`, sa anonyma 4xx/5xx fran den publika sidan syns i Historik > Felkoder utan filnamn eller filinnehall.
- `GET /api/meta/uploads`, `HEAD/GET /api/meta/uploads/{upload_id}/content`, `DELETE /api/meta/uploads/{upload_id}` - Super User-endpoints for Meta-vyn. Listan returnerar metadata utan blobbinnehall, inklusive hash, storlek och videolangd nar den finns; content-endpointen kan visa bild/video inline, ladda ner med `download=1` och stoder byte-range for videospelning. Delete-endpointen raderar raden och blobben.
- `GET /api/meta/shipment-observations`, `GET /api/meta/shipment-observations/export`, `POST /api/meta/uploads/{upload_id}/analyze` - Super User-endpoints for Meta-videoanalys. LLM fyller `pallet_id` och `deviations` fran extraherat ljud; efter analys forsoker backend hamta ASK Dispatchpallar (`v_ask_dispatch_pallet`) med filter pa `pick_pall_num=pallet_id` och fyller `order_number`, `shipment_number`, `username` och `customer_name` fran svaret. Exportendpointen laddar ner hela listan eller filtrerade `ids` som Excel. Videons filnamn, Video-ID/hash, langd och storlek returneras fortsatt via kopplad media-rad.

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
- `../app/backend/routers/productivity.py`
- `../app/backend/productivity_sync.py`
- `../app/backend/routers/workflow_data.py`
- `../app/backend/routers/rfid.py`
- `../app/backend/workflow_data.py`
- `../tests/tools/test_flow_cli.py`

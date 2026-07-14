---
title: API-karta
status: aktiv
updated: 2026-07-14
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
- `POST /api/query-data/catalog/reload` - rensar katalogcache och laser om vy-/kolumnkatalogen; OTel-spanen `data_fetch.catalog_reload` satter antal vyer/kolumner.
- `POST /api/query-data/plan` - tolkar en svensk datafraga med MiniMax till validerad vy/filter/kolumn-plan och eventuell whitelistad `calculation`; OTel-spanen `data_fetch.plan` sparar bara inputlangd, vy och status.
- `POST /api/query-data/run` - kor en validerad plan mot extern datakalla, applicerar lokala exkluderingar/jamforelser/textfilter som `NE`, `GTE`, `StartsWith` och `Like`, returnerar tabellpreview och eventuell berakning (`count`, `count_distinct`, `sum`, `avg`, `min`, `max`, grupper/sortering/limit). Accepterar valfritt `business_id` sa verksamhetens `tenant` kan styra extern API-bas. Audit skriver `data_fetch/fetch_success|fetch_failed`; OTel markerar planstatus, extern fetch, radantal, berakningsflagga och felstatus utan prompt eller raddata.
- `GET /api/query-data/export/{session_id}` - laddar ner senaste datahamtning som Excel och satter OTel-spanen `data_fetch.export`.
- `GET /api/mcp/status` - kontrollerar tenant-baserad Noeffect-MCP-konfiguration och vald LLM-hjarna; kraver `mcp=view` och returnerar bara env-namn/status, tenant, provider-/modell-/thinking-alternativ och sanerad MCP-metadata, inte token eller serveradress.
- `POST /api/mcp/query` - hamtar MCP-kontext, ger vald LLM-hjarna read-only MCP-tools och skickar en textfraga till modellen. Body kan ange `provider`, `model` och `thinking_mode`; kraver `mcp=edit` och auditloggar `mcp_query/query_success|query_failed` med langder, status, modell, hjarna och antal tool-anrop utan prompt, svar, token eller privat URL.

## Bemanning och oversikt

- `GET /api/schedule` - hamta dagsschema, scopeat till anvandarens verksamhet eller `business_id` for Super User.
- `PUT /api/schedule/cell` - satt en cell/ett segment.
- `PUT /api/schedule/cell/split` - dela eller sla ihop timme.
- `PUT /api/schedule/cell/remark` - spara eller ta bort anmarkning pa hel timme eller vald del av delad timme. Audit sparar bara om text finns och textlangd, inte sjalva anmarkningen.
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
- `GET /api/schedule/productivity-summary` - returnerar en latt personprocentkarta for Bemannings produktivitetskolumn. Den laser materialiserade `person_productivity_daily`-cellrader och skickar bara `people.{person_id}` med procent, poang, planpoang och KPI-minuter. Om extern snapshot-sync misslyckas returnerar endpointen fortfarande 200 med `cache.status=source_unavailable` och eventuell befintlig cache i stallet for att stoppa Bemanning med 502.
- `POST /api/schedule/copy` - kopiera dag/vecka.
- `POST /api/schedule/clear` - rensa schema.
- `POST /api/schedule/fill-from-left` - fyll tomma celler fran vanster.
- `POST /api/rfid/scans` - tar emot scan fran en fysisk RFID-modul. Payloaden innehaller `module_name`, brickkod och valfritt device-id; backend matchar modulnamnet mot aktivitet och brickkoden mot `Person.rfid_code`. Ny registrerad stampling ger `HTTP 201`; direkt dubblett for samma person och aktivitet ger `HTTP 200` med `registered=false` och skapar ingen `rfid_scan_events`-rad. Om `RFID_DEVICE_TOKEN` ar satt maste modulen skicka samma varde i `X-Flow-RFID-Token`.
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

- `GET/POST/PUT/DELETE /api/persons...`, `POST /api/persons/import-rows`, `PUT /api/persons/sort-order` - personregister med obligatoriskt `NoMan` for nya personer och import, valfri `rfid_code` for brickkoppling, `collar_type` for `blue_collar`/`white_collar`, Excelimport, direktimport fran tabellrader och begransad sortering fran planeringsvyerna.
- `GET/PUT /api/persons/{id}/schedule` - veckomall.
- `GET/POST/PUT/DELETE /api/activities...`, `POST /api/activities/import-rows` - aktivitetsregister med valfria kommaseparerade `kpi_process_name`/KPI Mal-processnamn, `work_type` (`normal` eller `vas`), Excelimport och direktimport fran tabellrader. Listan accepterar `business_id` och `area_focus` sa settingsvyer kan hamta aktiviteter for vald verksamhet. `GET /api/activities/kpi-process-options` returnerar valbara KPI-processnamn for aktivitetsmodalens multival.
- `GET/POST/PUT/DELETE /api/areas...` - omraden. Delete tar bort tomma omraden men inaktiverar omradet om personer, aktiviteter eller anvandare redan pekar pa det.
- `GET/POST/PUT/DELETE /api/users...`, `POST /api/users/import-rows` - anvandare, Excelimport, direktimport fran tabellrader och permanent borttagning.
- `GET/PUT /api/settings/staffing` - hamta/spara `staffing_history_hours`, historiktimmarna for historiskt snitt och automatisk bemanningskalkyl, samt `activity_capacity_activity_ids` for vilka aktiviteter som far visa hover-snitt. Accepterar `business_id` eller `area_focus`; `null` betyder alla KPI-aktiviteter och `[]` betyder inga. Lasning kraver `staffingSettings=view`, sparning kraver `staffingSettings=edit`.
- `GET/POST/PUT /api/businesses...` - Super User-vy for verksamheter med `company_codes` som verksamhetens bolagslista och `tenant` for extern datakalla.
- `GET/PUT /api/settings` - appsettings per verksamhet.
- `GET/PUT /api/settings/sidebar` - sidebar per verksamhet.
- `GET/PUT /api/settings/role-access` - global roll-vyatkomst for alla verksamheter.
- `GET/PUT /api/settings/productivity-finance` - Produktivitetens Intakt/utgift-installningar per verksamhet: kostnad per timme, VAS-intakt per bolag, intaktsrader per bolag, sparade utrakningsplaner och valfri `linked_process_key`/`linked_process_label` per rad for att visa intakt pa KPI-processer.

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
- `GET /api/healthcheck` - Super User-halsa for app, databas, bakgrundsjobb och publik ping (`HEALTHCHECK_PUBLIC_URL`). Render-integrationen togs bort 2026-07-03 nar Render-driften avvecklades; serverloggar hamtas nu med `kubectl -n flow logs deploy/flow-web`.
- `POST /api/healthcheck/wait-metrics` - tyst insamling av anvandarens vantetider for vyload, API-anrop, nedladdningar och bakgrundsladdning. Payloaden ar sanerad till event, vy, steg, duration, status och begransad teknisk detalj.
- `GET /api/healthcheck/wait-metrics/summary` - Super User-summering for Historik-fliken `Vantetider` och CLI-verktyget `tools.healthcheck`; accepterar `business_id`.
- `GET /api/productivity` - produktivitet, kraver `productivity=view` for lasning. Rapporten anvander serverns globala personbaserade API-snapshot for pick/trans/pallet/receive/order_log/sort/base_pallet/kpi och returnerar `backfill` for historikhamtning.
- `GET /api/productivity/persons/{person_id}` - personens aktivitetssnitt for `period=week|month|year|custom`. `date` styr vecka/manad/ar och `start_date`/`end_date` styr custom. Svaret innehaller `activities[]`, totalsummering, `missing_dates` och `backfill`.
- `GET /api/productivity/overview` - periodpayload for Produktivitet med dag/vecka/manad/ar/custom, underliggande dagsrapporter, periodsummary, saknade datum och global backfillstatus. Med `productivityFinance=view` innehaller periodens `finance` aven `process_revenues` for intaktsrader som kopplats till KPI-processer i Intakt/utgift. Nar databasen stodjer det byggs dagsrapporterna med hogst fyra parallella dagjobb och egen DB-session per dag; payloaden sorteras per datum innan svar.
- `GET /api/productivity/overview/stream` - SSE-variant for Produktivitet som skickar progress under periodhamtningen och faller tillbaka till vanliga overview-payloaden i sista eventet. Progress-event kan innehalla `completed` som antal fardiga dagar.
- `GET /api/productivity/overview/business-summary` - verksamhetssummering for samma `date`/`period`/`start_date`/`end_date` som Produktivitet. Svaret grupperar intakt, kostnad, resultat och antal plockloggsrader med `Plockat`/`qty_suf = 0` per bolag och total.
- `GET /api/sankey/inbound` - separat Sankey - Inbound/Outbound-rapport, kräver `sankeyInbound=view`. Query `period=day|week|month|year`, `date`, valfri `company` och `only_consumed` väljer inboundkohort, outboundperiod och om öppna inboundetiketter ska visas. Backend följer inboundetiketter från mottagning fram till idag via receive/trans/pick live- och `dblog_*`-vyer samt aktuell buffertpallstatus. Outbound räknas från Plocklogg Full och Dispatchpallslogg (`dispatch_pallet_log`/`dblog_dispatch_pallet_log`) med Butik/TO och E-handel/PR enligt Intäkt/utgift-raderna. Svaret returnerar `nodes`, `links`, `processes`, `outbound_metrics`, `trace_rows`, `summary`, `companies`, `warnings` och `source_status`, inklusive `gross_income_labels`, `gross_income_purchase_lines`, `outbound_income`, `label_revenue`, `purchase_line_revenue`, `outbound_revenue` samt spårningsrader med pallid, inköp/rad, ordernummer, `received_date` och stegvis väg för klick/export i UI. Standardpayloaden innehåller normalt även `client_filters.only_consumed`, direkt `only_consumed=true` innehåller normalt `client_filters.all`, och nyare svar innehåller `client_filters.views` för lokala bolags-, dag- och månadsväxlingar utan ny hämtning när urvalet ryms i redan hämtad period. Stora payloads kan sätta `client_filters.prebuilt=false` och `omitted_reason=large_payload`; klienten hämtar då nästa filtervariant via API/SSE. Körningar auditloggas som `sankey_inbound_report/run|run_failed` utan pallid/order/radpayload.
- `GET /api/sankey/inbound/stream` - SSE-variant for Sankey - Inbound som skickar progress per kallsteg och samma slutpayload som `/api/sankey/inbound`.
- `source_status.status=productivity_snapshot` i Sankey - Inbound betyder att backend ateranvande Produktivitetens lokala snapshotfiler for `receive` eller `trans` i stallet for att hamta samma vy fran extern API igen.
- `POST /api/productivity/sync` - manuell sync av Produktivitetens API-snapshot for valt datum eller dagens datum, kraver `productivity=edit`.
- `POST /api/settings/productivity-finance/calculation/test` - testar en Intakt/utgift-rads utrakning for vald startad manad i innevarande ar. Endpointen kraver `productivityFinanceSettings=edit`, tolkar prompten via MiniMax/Hamta data, lagger automatiskt pa aktuell `company_code` som `company`/Bolag-filter nar vald ASK-vy har bolagskolumn, kor validerad plan mot extern datakalla, applicerar lokala exkluderingar/jamforelser/textfilter, beraknar eventuell `calculation` lokalt pa raderna och returnerar `quantity`, periodneutral plan och sparbar SQL/querytext utan testmanadens datumfilter.
- `POST /api/settings/productivity-finance/process-check` - jamfor sparade Intakt/utgift-utrakningar med KPI-processregler for vald manad. Body accepterar `month`, valfri `year`, valfri `company_code` och valfri `row_id`. Med `row_id` kontrolleras bara den intaktsraden och backend hamtar bara radens relevanta Mammur-/ASK-vy. Svaret listar matchade KPI-processer, processer pa samma vy med intaktsantal/processantal/overlapp/diff, saknade rader eller unika berakningsnycklar, bredare processer och mojlig dubbelrakning. Vid `count_distinct`, till exempel unika `order_num`, jamfor kontrollen processernas samlade nycklar mot intaktens nycklar och returnerar `comparison_key_columns`, `comparison_key_label`, `comparison_key_count` samt `combined_process_coverage` med foreslagen processkombination, tackta/saknade/extra nycklar och tackningsprocent. Radsvaret innehaller aven `calculation_prompt`, sparad/periodiserad intakts-SQL och `process_sql` pa processerna i samma vy, sa UI:t kan visa prompt, intakts-SQL och vald process-SQL i kontroll-dialogen. Endpointen kraver `productivityFinanceSettings=view` och auditloggar sanerad period/bolag/rad/summering.
- Produktivitetsfilroutes ar borttagna: `/api/productivity/files`, `/api/productivity/files/raw`, `/api/productivity/files/{file_type}` och `/api/productivity/targets` finns inte langre.
- `POST /api/rfid/scans`, `GET /api/rfid/events`, `POST /api/rfid/events/{id}/apply|ignore` - RFID-flodet for Bemanning. Device-endpointen ar avsiktligt separat fran inloggad UI, men kan skyddas med `RFID_DEVICE_TOKEN`; inloggade apply/ignore kraver `schedule=edit`.
- `GET /api/coredata/files` - listar verksamhetens permanenta coredata-karnfiler fran Postgres-tabellen `coredata_files` med filbaserad fallback, samt sammanstalld data som `artikel_max.csv`. Bearbeta anropar den bara for Uppladdningar eller synliga floden dar kallvalet kraver `Uppladdning`; API-installda kallor behover inte uppladdningsstatus.
- `GET /api/coredata/files/{file_key}/preview` - forhandsvisar en serverlagrad coredata-karnfil eller sammanstalld datafil for anvandarens verksamhet. Svaret innehaller begransad textpreview, filnamn, storlek och metadata men ska inte anvandas for full nedladdning.
- `GET /api/coredata/files/{file_key}/download` - laddar ner serverlagrad coredata-karnfil eller sammanstalld data forst nar anvandaren klickar explicit nedladdning.
- `POST /api/coredata/files/raw` - laddar upp en coredata-karnfil eller sammanstalld datafil till anvandarens verksamhet och ersatter aldre fil med samma prefix, kraver `allocationUploads=edit`. Coredata-karnfiler sparas som blobbar i Postgres; sammanstalld data behaller sitt befintliga lagringsflode.
- `GET /api/allokering/health`, `/flows`, `/pool`, `GET/PUT /process-matrix`, `GET/PUT /filter-profile`, `POST /filter-profile/import`, `GET/PUT /ytgenerering-map-layout`, `POST /detect`, `POST /flow/{flow_id}`, `POST /open-excel`, `GET /table-column/...`, `GET /download/...` - lagerverktyg. `GET /process-matrix` kan lasas av Bearbeta (`allocationProcess=view`) eller Installningars Bearbeta-flik (`allocationProcessMatrix=view`), medan `PUT /process-matrix` kraver `allocationProcessMatrix=edit`; bada accepterar `business_id` eller `area_focus` och sparar `allocation_process_matrix` per verksamhet. `filter-profile` sparar personliga Bearbeta-källval, filtreringar per anvandare och Ytgenereringens personliga UTL-/transportorsinstallningar; import-endpointen kopierar en annan atkomlig anvandares profil. `ytgenerering-map-layout` kraver `allocationSettings`, accepterar `business_id`/`area_focus`, sparar kartan per verksamhet och returnerar aven `available_locations` fran samma verksamhets `location`-karnfil.
- `POST /api/workflow-data/source` - desktop/runtime-endpoint som returnerar en temporar CSV for en tillaten workflow-kalla. Body ar `{ feature, flow_id, source_key }`. Behorighet styrs av malfunktionen (`allocationProcess` eller `productivity`) och anvandarens verksamhet kan styra tenant for extern API-bas. Svaret innehaller bara CSV + sanerade source-headers, inte privata API-detaljer. Forsok audit-loggas som `workflow_source/source_fetch` eller `workflow_source/source_fetch_failed` med sanerad payload och OTel-spanen `workflow_data.source`.
- Desktop-only lokala endpoints finns bara i Windows-proxyn: `/api/desktop/capabilities`, `/api/desktop/jobs`, `/api/desktop/cache/sync`, `/api/desktop/files/{ref}/detect|open|open-folder` och `/api/desktop/sync/coredata`. De proxas inte som centrala serverkontrakt.
- `GET /api/public/...` - publika text/CSV-summeringar for timmar/personer. Queryparametern `business` defaultar till `STIGAMO`; publika endpoints summerar inte globalt.
- `POST /api/meta/uploads` - publik multipart-uppladdning for flera bilder/videor utan inloggning. Sparar filer i `meta_media_uploads` med tidsstamplat `stored_filename`, `content_hash`, eventuell `duration_seconds` och status `pending_analysis`. Exakta dubbletter hoppas over och returneras i `skipped`. Lyckade forsok loggas som `meta_media_upload/upload_success`; fel som hinner na backend loggas sanerat som `meta_media_upload/upload_failed`, sa anonyma 4xx/5xx fran den publika sidan syns i Historik > Felkoder utan filnamn eller filinnehall. OTel-attributen ar bara antal, status, storlek och analysstatus.
- `GET /api/meta/uploads`, `HEAD/GET /api/meta/uploads/{upload_id}/content`, `DELETE /api/meta/uploads/{upload_id}` - Super User-endpoints for Meta-vyn. Listan returnerar metadata utan blobbinnehall, inklusive hash, storlek och videolangd nar den finns; content-endpointen kan visa bild/video inline, ladda ner med `download=1` och stoder byte-range for videospelning. `variant=playable` ar av bakatkompatibilitet ett alias till den strommade originalfilen och svarar med `X-Flow-Media-Variant: original`; endpointen startar aldrig videotranskodning. Delete-endpointen raderar raden och blobben.
- `GET /api/meta/shipment-observations`, `GET /api/meta/shipment-observations/export`, `POST /api/meta/uploads/{upload_id}/analyze`, `PATCH /api/meta/shipment-observations/{observation_id}/dispatch-lookup` - Super User-endpoints for Meta-videoanalys. LLM fyller `pallet_id` och `deviations` fran extraherat ljud; efter analys forsoker backend hamta ASK Dispatchpallar (`v_ask_dispatch_pallet`) med filter pa `pick_pall_num=pallet_id` och fyller `order_number`, `shipment_number`, `username` och `customer_name` fran svaret. Patch-endpointen tar sanerade lookup-falt fran `flow_cli --local-dispatch-lookup` nar servermiljon inte far hamta ASK sjalv. Exportendpointen laddar ner hela listan eller filtrerade `ids` som Excel. Videons filnamn, Video-ID/hash, langd och storlek returneras fortsatt via kopplad media-rad.

## Buggrapporter

| Metod | Path | Behorighet | Beskrivning |
| --- | --- | --- | --- |
| POST | `/api/bug-reports` | Inloggad | Skicka in 30 s rrweb-inspelning + kontext. Tak: `BUG_REPORTS_MAX_EVENTS_BYTES`, rate limit per anvandare/timme. |
| GET | `/api/bug-reports` | vy `bugReports` (view) | Lista rapporter (utan blob), verksamhetsscopad. |
| GET | `/api/bug-reports/{id}` | vy `bugReports` (view) | Hamta rapport inkl. `events_json` for uppspelning. |
| PATCH | `/api/bug-reports/{id}/status` | vy `bugReports` (edit) | Satt status new/seen/done. Auditloggas. |

Se [Buggrapporter](bug-reports.md).

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
- `../app/backend/routers/mcp.py`
- `../app/backend/mcp_service.py`
- `../tests/tools/test_flow_cli.py`

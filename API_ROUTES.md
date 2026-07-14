# API-vÃ¤gar och CLI

Det hÃ¤r Ã¤r den fulla API-tÃ¤ckningen som `tools.flow_cli` kÃ¤nner till.
Testen `tests/tools/test_flow_cli.py` jÃ¤mfÃ¶r listan mot FastAPI-appen sÃ¥
nya `/api/*`-vÃ¤gar inte tappas bort.

Vanliga kommandon:

```powershell
python -m tools.flow_cli routes --format table
python -m tools.flow_cli routes --format markdown
python -m tools.flow_cli --base-url http://127.0.0.1:8000 auth login --username admin --password admin123
python -m tools.flow_cli call schedule.get --query year=2026 --query week=21 --query weekday=1
python -m tools.flow_cli call persons.import --file file=personer.xlsx
python -m tools.flow_cli call activities.import --file file=aktiviteter.xlsx
python -m tools.flow_cli api GET /api/health
python -m tools.flow_cli allocation flows
python -m tools.flow_cli allocation run split-values --param "values=A`nB`nC" --out artifacts\split
```

`call` anvÃ¤nder namngivna API-vÃ¤gar. `api` kan anropa valfri vÃ¤g manuellt, Ã¤ven
om en ny vÃ¤g Ã¤nnu inte fÃ¥tt ett namn i CLI:t.

Lagerverktygen har tvÃ¥ CLI-lager:

- `python -m tools.flow_cli allocation ...` kÃ¶r samma `/api/allokering`-vÃ¤gar som webb/desktop, inklusive auth-cookie, sessionsresultat och CSV-nedladdning.
- `python -m warehouse_tools.cli ...` kÃ¶r Bearbeta/Dela lokalt utan server, IndexedDB eller cookies. Det Ã¤r snabbast fÃ¶r regressions- och paritytester.

Exempel:

```powershell
python -m warehouse_tools.cli list-flows
python -m warehouse_tools.cli schema allocate
python -m warehouse_tools.cli detect .\testdata\warehouse_tools\v_ask_customer_order_details_all-20260317145125.csv
python -m warehouse_tools.cli allocate --auto-file orders.csv --auto-file buffer.csv --format both --out artifacts\allocate
python -m tools.compare_warehouse_results --left .\Resultat.csv --right .\allocated_orders.xlsx
```

AnvÃ¤ndar-API:t Ã¤r bakÃ¥tkompatibelt med `role`, men nya klienter kan skicka
`roles`, t.ex. `{"username":"anna","roles":["viewer","leader"]}`,
`{"username":"petra","roles":["staffing_manager"]}` fÃ¶r Bemanningsansvarig,
`{"username":"lina","roles":["warehouse_clerk"]}` fÃ¶r Lagerkontorist och
`{"username":"arvid","roles":["article_placer"]}` fÃ¶r Artikelplacerare.

## Verksamhetsscope

`/api/auth/me` returnerar aktuell anvandares `business_id`, verksamhetskod och
verksamhetsnamn. Icke-Super Users filtreras alltid till sin egen verksamhet i
listor och detail/update/delete-svar. Super User kan anvanda `business_id` pa
scopebara listor som personer, aktiviteter, omraden, anvandare, schema,
oversikt och settings; utan filter betyder `âˆž` globalt dar API:t tillater det.

Publika `/api/public/*` tar queryparametern `business` och defaultar till
`STIGAMO` for bakatkompatibilitet. De summerar aldrig globalt over flera
verksamheter.

| Namn | Metod | VÃ¤g | Beskrivning |
| --- | --- | --- | --- |
| `health` | `GET` | `/api/health` | Server health |
| `healthcheck.report` | `GET` | `/api/healthcheck` | Server- och databashalsa |
| `healthcheck.wait_metrics` | `POST` | `/api/healthcheck/wait-metrics` | Samla vantetidsmatningar |
| `healthcheck.wait_summary` | `GET` | `/api/healthcheck/wait-metrics/summary` | Analysera anvandarvantetider |
| `businesses.list` | `GET` | `/api/businesses` | Lista verksamheter |
| `businesses.create` | `POST` | `/api/businesses` | Skapa verksamhet |
| `businesses.update` | `PUT` | `/api/businesses/{business_id}` | Uppdatera verksamhet |
| `auth.login` | `POST` | `/api/auth/login` | Logga in |
| `auth.logout` | `POST` | `/api/auth/logout` | Logga ut |
| `auth.me` | `GET` | `/api/auth/me` | Aktuell anvÃ¤ndare |
| `auth.set_password` | `POST` | `/api/auth/set-password` | SÃ¤tt fÃ¶rsta lÃ¶senord |
| `assistant.chat` | `POST` | `/api/assistant/chat` | FrÃ¥ga apphjÃ¤lpen |
| `assistant.clear` | `POST` | `/api/assistant/clear` | Rensa apphjÃ¤lpens dialogkvot |
| `query_data.health` | `GET` | `/api/query-data/health` | DatahÃ¤mtning health |
| `query_data.reload_catalog` | `POST` | `/api/query-data/catalog/reload` | LÃ¤s om extern datakatalog |
| `query_data.plan` | `POST` | `/api/query-data/plan` | Tolka datafrÃ¥ga med MiniMax |
| `query_data.run` | `POST` | `/api/query-data/run` | HÃ¤mta data frÃ¥n extern datakÃ¤lla med tenant per verksamhet, lokala exkluderingar/jÃ¤mfÃ¶relser/textfilter och validerad berÃ¤kning |
| `query_data.export` | `GET` | `/api/query-data/export/{session_id}` | Exportera datahÃ¤mtning till Excel |
| `query_data.archive_cache_status` | `GET` | `/api/query-data/archive-cache/status` | Status fÃ¶r lokal arkiv-cache |
| `mcp.status` | `GET` | `/api/mcp/status` | MCP- och LLM-status |
| `mcp.query` | `POST` | `/api/mcp/query` | Skicka frÃ¥ga till MCP via vald LLM-hjÃ¤rna |
| `allocation.health` | `GET` | `/api/allokering/health` | Lagerverktyg health |
| `allocation.flows` | `GET` | `/api/allokering/flows` | Lista lagerverktygsflÃ¶den |
| `allocation.pool` | `GET` | `/api/allokering/pool` | Lista lagerverktygens uppladdningsslots |
| `allocation.process_matrix_get` | `GET` | `/api/allokering/process-matrix` | HÃ¤mta Bearbeta-matris |
| `allocation.process_matrix_update` | `PUT` | `/api/allokering/process-matrix` | Uppdatera Bearbeta-matris |
| `allocation.filter_profile_get` | `GET` | `/api/allokering/filter-profile` | Hamta personliga Bearbeta-profiler |
| `allocation.filter_profile_update` | `PUT` | `/api/allokering/filter-profile` | Spara personliga Bearbeta-profiler |
| `allocation.filter_profile_import` | `POST` | `/api/allokering/filter-profile/import` | Kopiera Bearbeta-profil fran anvandare |
| `allocation.map_layout_get` | `GET` | `/api/allokering/ytgenerering-map-layout` | Hamta Ytgenerering-kartlayout |
| `allocation.map_layout_update` | `PUT` | `/api/allokering/ytgenerering-map-layout` | Uppdatera Ytgenerering-kartlayout |
| `allocation.map_location_options` | `GET` | `/api/allokering/ytgenerering-location-options` | Hamta Ytgenerering U-platslista |
| `allocation.detect` | `POST` | `/api/allokering/detect` | Identifiera lagerverktygsfil |
| `allocation.observations_update` | `POST` | `/api/allokering/observations/update` | Uppdatera observations frÃ¥n buffert |
| `allocation.run_flow` | `POST` | `/api/allokering/flow/{flow_id}` | KÃ¶r lagerverktygsflÃ¶de |
| `allocation.open_excel` | `POST` | `/api/allokering/open-excel` | Ã–ppna lagerverktygsresultat i Excel |
| `allocation.table_column` | `GET` | `/api/allokering/table-column/{session_id}/{key}/{column_index}` | HÃ¤mta resultatkolumn |
| `allocation.download` | `GET` | `/api/allokering/download/{session_id}/{key}` | Ladda ner Allokering-resultat |
| `workflow_data.source` | `POST` | `/api/workflow-data/source` | Hamta workflow-kalla som temporar CSV med tenant per verksamhet |
| `coredata.files` | `GET` | `/api/coredata/files` | Coredata-karnfiler fran Postgres/fallback och sammanstalld data for verksamheten |
| `coredata.preview` | `GET` | `/api/coredata/files/{file_key}/preview` | Forhandsvisa coredata-karnfil eller sammanstalld data |
| `coredata.download` | `GET` | `/api/coredata/files/{file_key}/download` | Ladda ner coredata-karnfil eller sammanstalld data |
| `coredata.upload_raw` | `POST` | `/api/coredata/files/raw` | Ladda upp coredata-karnfil till Postgres eller sammanstalld datafil |
| `areas.list` | `GET` | `/api/areas` | Lista omrÃ¥den |
| `areas.create` | `POST` | `/api/areas` | Skapa omrÃ¥de |
| `areas.update` | `PUT` | `/api/areas/{area_id}` | Uppdatera omrÃ¥de |
| `areas.delete` | `DELETE` | `/api/areas/{area_id}` | Ta bort eller inaktivera omrÃ¥de |
| `activities.list` | `GET` | `/api/activities` | Lista aktiviteter med KPI Mal-processnamn och arbetstyp |
| `activities.kpi_process_options` | `GET` | `/api/activities/kpi-process-options` | Lista valbara KPI-processer |
| `activities.import_template` | `GET` | `/api/activities/import-template` | HÃ¤mta importmall fÃ¶r aktiviteter |
| `activities.import` | `POST` | `/api/activities/import` | Importera aktiviteter |
| `activities.import_rows` | `POST` | `/api/activities/import-rows` | Importera aktivitetsrader med valfria KPI Mal-processnamn och arbetstyp (`normal`/`VAS`) |
| `activities.create` | `POST` | `/api/activities` | Skapa aktivitet med valfria KPI Mal-processnamn och arbetstyp |
| `activities.update` | `PUT` | `/api/activities/{activity_id}` | Uppdatera aktivitet med valfria KPI Mal-processnamn och arbetstyp |
| `activities.delete` | `DELETE` | `/api/activities/{activity_id}` | Ta bort aktivitet |
| `settings.get` | `GET` | `/api/settings` | HÃ¤mta verksamhetens instÃ¤llningar |
| `settings.update` | `PUT` | `/api/settings` | Uppdatera verksamhetens instÃ¤llningar |
| `settings.staffing_get` | `GET` | `/api/settings/staffing` | HÃ¤mta bemanningens historiktimmar och val fÃ¶r historiskt snitt |
| `settings.staffing_update` | `PUT` | `/api/settings/staffing` | Uppdatera bemanningens historiktimmar och val fÃ¶r historiskt snitt |
| `settings.productivity_finance_get` | `GET` | `/api/settings/productivity-finance` | HÃ¤mta produktivitetens intÃ¤kt/utgift |
| `settings.productivity_finance_update` | `PUT` | `/api/settings/productivity-finance` | Uppdatera produktivitetens intÃ¤kt/utgift |
| `settings.productivity_finance_calculation_test` | `POST` | `/api/settings/productivity-finance/calculation/test` | Testa utrÃ¤kning fÃ¶r produktivitetens intÃ¤kt/utgift |
| `settings.productivity_finance_process_check` | `POST` | `/api/settings/productivity-finance/process-check` | Kontrollera intÃ¤ktsrader eller vald `row_id` mot KPI-processer |
| `settings.sidebar_get` | `GET` | `/api/settings/sidebar` | HÃ¤mta verksamhetens sidomeny |
| `settings.sidebar_update` | `PUT` | `/api/settings/sidebar` | Uppdatera verksamhetens sidomeny |
| `settings.role_access_get` | `GET` | `/api/settings/role-access` | HÃ¤mta verksamhetens roll-vyÃ¥tkomst |
| `settings.role_access_update` | `PUT` | `/api/settings/role-access` | Uppdatera verksamhetens roll-vyÃ¥tkomst |
| `settings.feature_registry` | `GET` | `/api/settings/feature-registry` | HÃ¤mta backend-Ã¤gd produktkarta |
| `audit.list` | `GET` | `/api/audit` | Lista auditlogg |
| `audit.summary` | `GET` | `/api/audit/summary` | Audit-summering |
| `audit.errors` | `GET` | `/api/audit/errors` | Felkodsdashboard |
| `audit.client_error` | `POST` | `/api/audit/client-error` | Logga anvÃ¤ndarens API-fel |
| `audit.client_event` | `POST` | `/api/audit/client-event` | Logga tysta UI-hÃ¤ndelser som vyÃ¶ppning |
| `audit.local_run` | `POST` | `/api/audit/local-run` | Logga sanerad Windows-korning |
| `audit.interactions` | `POST` | `/api/audit/interactions` | Logga batchade anvandarinteraktioner |
| `audit.interactions_public` | `POST` | `/api/audit/interactions/public` | Logga allowlistad publik meta-tracking |
| `audit.interactions_list` | `GET` | `/api/audit/interactions` | Lista trackingevents |
| `audit.interactions_summary` | `GET` | `/api/audit/interactions/summary` | Summera trackingevents |
| `audit.interactions_coverage` | `GET` | `/api/audit/interactions/coverage` | Visa trackingtackning |
| `audit.interactions_chat` | `POST` | `/api/audit/interactions/chat` | Fraga MiniMax om trackinghistorik |
| `audit.interactions_chat_clear` | `POST` | `/api/audit/interactions/chat/clear` | Rensa Historik-AI |
| `persons.list` | `GET` | `/api/persons` | Lista personer |
| `persons.import_template` | `GET` | `/api/persons/import-template` | HÃ¤mta importmall fÃ¶r personer |
| `persons.import` | `POST` | `/api/persons/import` | Importera personer |
| `persons.import_rows` | `POST` | `/api/persons/import-rows` | Importera personrader |
| `persons.create` | `POST` | `/api/persons` | Skapa person |
| `persons.sort_order` | `PUT` | `/api/persons/sort-order` | Sortera personer inom anvandarens omrade |
| `persons.get` | `GET` | `/api/persons/{person_id}` | HÃ¤mta person |
| `persons.update` | `PUT` | `/api/persons/{person_id}` | Uppdatera person |
| `persons.delete` | `DELETE` | `/api/persons/{person_id}` | Ta bort person |
| `person_schedules.get` | `GET` | `/api/persons/{person_id}/schedule` | HÃ¤mta veckomall |
| `person_schedules.update` | `PUT` | `/api/persons/{person_id}/schedule` | Uppdatera veckomall |
| `schedule.get` | `GET` | `/api/schedule` | HÃ¤mta dagsschema |
| `schedule.set_cell` | `PUT` | `/api/schedule/cell` | SÃ¤tt schemacell |
| `schedule.split_cell` | `PUT` | `/api/schedule/cell/split` | Dela/slÃ¥ ihop schemacell |
| `schedule.bulk_cells` | `POST` | `/api/schedule/cells` | SÃ¤tt flera schemaceller |
| `schedule.restore_hours` | `PUT` | `/api/schedule/hours/restore` | Ã…terstÃ¤ll timmar |
| `schedule.summary` | `GET` | `/api/schedule/summary` | Schema-summering |
| `schedule.revision` | `GET` | `/api/schedule/revision` | Schema-revision |
| `schedule.presence` | `GET` | `/api/schedule/presence` | NÃƒÂ¤rvarolista fÃƒÂ¶r utskrift |
| `schedule.calculator_profile` | `GET` | `/api/schedule/calculator-profile` | Hamta personliga automatiska bemanningskalkyler |
| `schedule.cell_remark` | `PUT` | `/api/schedule/cell/remark` | Spara eller ta bort anmarkning pa schemacell |
| `schedule.calculator_profile_update` | `PUT` | `/api/schedule/calculator-profile` | Spara personliga automatiska bemanningskalkyler |
| `schedule.calculator_profile_import` | `POST` | `/api/schedule/calculator-profile/import` | Kopiera bemanningskalkyler fran anvandare |
| `schedule.calculator_automatic` | `GET` | `/api/schedule/calculator/automatic` | Berakna automatiska bemanningskalkyler |
| `schedule.activity_capacity` | `GET` | `/api/schedule/activity-capacity` | Historiskt snitt per person och vald bemanningsaktivitet |
| `schedule.activity_capacity_cell` | `GET` | `/api/schedule/activity-capacity/cell` | Historiskt snitt fÃ¶r en person och aktivitet vid cell-hover |
| `schedule.productivity_summary` | `GET` | `/api/schedule/productivity-summary` | Latt produktivitetsprocent per person for Bemanning |
| `schedule.copy` | `POST` | `/api/schedule/copy` | Kopiera dag/vecka |
| `schedule.clear` | `POST` | `/api/schedule/clear` | Rensa schema |
| `schedule.fill_from_left` | `POST` | `/api/schedule/fill-from-left` | Fyll frÃ¥n vÃ¤nster |
| `rfid.scans` | `POST` | `/api/rfid/scans` | Ta emot RFID-scan fran fysisk modul |
| `rfid.events` | `GET` | `/api/rfid/events` | Lista RFID-stamplingar for Bemanning |
| `rfid.ignore` | `POST` | `/api/rfid/events/{event_id}/ignore` | Ignorera RFID-stampling |
| `rfid.apply` | `POST` | `/api/rfid/events/{event_id}/apply` | Applicera RFID-stampling i Bemanning |

Schema-celler i svar fran `schedule.get`, `schedule.bulk_cells`,
`schedule.set_cell` och `schedule.restore_hours` kan ha `loan_area_id`.
`schedule.bulk_cells` och `schedule.restore_hours` kan ocksa satta faltet.
Det anvands for tomma utlanade timmar: `activity_id=null` och
`loan_area_id=<omrade>` gor personen synlig i mottagande omrade utan att skapa
aktivitetstimmar.

`PUT /api/schedule/cell/remark` sparar fri anmarkning pa hel timme eller
delad cell. Svar fran schemaendpoints kan darfor ocksa innehalla `remark`.
| `personal.persons` | `GET` | `/api/personal/persons` | Personval fÃ¶r personliga vyer |
| `personal.schedule` | `GET` | `/api/personal/schedule` | Mitt schema fÃ¶r en person |
| `personal.productivity` | `GET` | `/api/personal/productivity` | Min produktivitet med schema och global personproduktivitet |
| `overview.week` | `GET` | `/api/overview` | Ã–versikt vecka |
| `overview.month` | `GET` | `/api/overview/month` | Ã–versikt mÃ¥nad |
| `overview.revision` | `GET` | `/api/overview/revision` | Ã–versikt revision |
| `overview.revision_month` | `GET` | `/api/overview/revision/month` | Ã–versikt mÃ¥nadsrevision |
| `overview.set_day` | `POST` | `/api/overview/day` | SÃ¤tt dag i Ã¶versikt |
| `overview.bulk_days` | `POST` | `/api/overview/days/bulk` | SÃ¤tt flera dagar i Ã¶versikt |
| `users.list` | `GET` | `/api/users` | Lista anvÃ¤ndare |
| `users.import_template` | `GET` | `/api/users/import-template` | HÃ¤mta importmall fÃ¶r anvÃ¤ndare |
| `users.import` | `POST` | `/api/users/import` | Importera anvÃ¤ndare |
| `users.import_rows` | `POST` | `/api/users/import-rows` | Importera anvÃ¤ndarrader |
| `users.create` | `POST` | `/api/users` | Skapa anvÃ¤ndare |
| `users.update` | `PUT` | `/api/users/{user_id}` | Uppdatera anvÃ¤ndare |
| `users.delete` | `DELETE` | `/api/users/{user_id}` | Ta bort anvÃ¤ndare |
| `productivity.sync` | `POST` | `/api/productivity/sync` | Synka valt datum, eller dagens produktivitetsdata om datum saknas |
| `productivity.person` | `GET` | `/api/productivity/persons/{person_id}` | Personens produktivitetssnitt per aktivitet for vecka/manad/ar/datumperiod |
| `productivity.overview` | `GET` | `/api/productivity/overview` | Produktivitetsoversikt for dag/vecka/manad/ar/datumperiod |
| `productivity.overview_stream` | `GET` | `/api/productivity/overview/stream` | Streama produktivitetsoversikt med progress |
| `productivity.overview_business_summary` | `GET` | `/api/productivity/overview/business-summary` | Verksamhetssummering per bolag for samma periodurval som Produktivitet |
| `productivity.report` | `GET` | `/api/productivity` | Produktivitetsrapport; lasning ar tillaten for `productivity=view` |
| `sankey.inbound` | `GET` | `/api/sankey/inbound` | Sankey - Inbound/Outbound fÃ¶r mottagna etiketter, outbounddebitering, processintÃ¤kt och Ã¶ppna/fÃ¶rverkade flÃ¶den |
| `sankey.inbound_stream` | `GET` | `/api/sankey/inbound/stream` | Streama Sankey - Inbound med progress |
| `sankey.inbound_trace` | `GET` | `/api/sankey/inbound/trace` | HÃ¤mta trace-rader fÃ¶r Sankey - Inbound via token |
| `sankey.inbound_trace_csv` | `GET` | `/api/sankey/inbound/trace.csv` | Streama trace-rader fÃ¶r Sankey - Inbound som CSV |

Produktivitetens API-snapshot anvÃ¤nder kÃ¤llorna `pick`, `trans`, `pallet`
(`LOADING_LOG`), `receive`, `order_log`, `sort`, `base_pallet` och `kpi`.
Schedulerstart fyller 13 dagar bakÃ¥t plus idag; dÃ¤refter uppdateras bara dagens
snapshot vid varje hel- och halvtimme. En global historik-backfill hamtar sedan
en aldre dag per kalenderdag och sparar snapshots permanent i serverns
produktivitetsdata.

`GET /api/schedule/productivity-summary` returnerar en mindre Bemanning-specifik
personkarta byggd fran materialiserade `person_productivity_daily`-cellrader.
Om extern snapshot-sync misslyckas returnerar endpointen fortsatt 200 med
`cache.status=source_unavailable` och laser eventuell befintlig cache, sa
Bemanning inte stoppas av Produktivitetens externa kallfel.

`GET /api/productivity` returnerar personrader med `time_cells[]`. Cellerna har
`points`, `expected_points`, `score_status`, `process_points[]`, `diff_count`
och `diffs[]`. Personer utan KPI-kopplad tid, till exempel heldags STOD/absence,
ingar inte i rapporten.

`GET /api/productivity/overview?period=day|week|month|year&date=YYYY-MM-DD`
returnerar periodmetadata och `reports[]` for tradvyn. Dagens datum raknas bara
till senaste avslutade heltimme i klienten; servern klipper innevarande
vecka/manad/ar vid dagens datum och returnerar `missing_dates` om en dag saknar
snapshot/fallback. Periodvyn laser befintliga snapshots och triggar inte extern
historikhamtning vid varje periodbyte; schemalagd sync/backfill ansvarar for att
fylla pa data. Pa Postgres byggs dagsrapporterna med hogst fyra parallella
dagjobb, var och en med egen DB-session, och payloaden sorteras per datum innan
den returneras. `GET /api/productivity/overview/stream` skickar samma slutpayload
som `done`-event; progress-event kan innehalla `completed` som antal fardiga
dagar sa klienten kan visa ratt framdrift nar flera dagar ar aktiva samtidigt.

`GET /api/productivity/overview/business-summary` accepterar samma `date`,
`period`, `start_date` och `end_date` och returnerar `companies[]` plus
`totals` med intakt, kostnad, resultat och antal plockloggsrader dar
`Plockat`/`qty_suf` ar `0`.

`GET /api/sankey/inbound?period=day|week|month|year&date=YYYY-MM-DD`
returnerar Sankey - Inbound/Outbound. Inbounddelen utgÃ¥r frÃ¥n
mottagningskohorten och fÃ¶ljer raderna fram till dagens datum; outbounddelen
rÃ¤knar periodens Butik-/E-handelsdebitering frÃ¥n Plocklogg Full och
Dispatchpallar. Queryn accepterar valfri `company` och `only_consumed=true`.
Svaret innehÃ¥ller `summary`, `companies`, `nodes`, `links`, `processes`,
`outbound_metrics`, `trace_total`, `trace_counts`, `trace_token`, `trace_filter`, `warnings`,
`source_status` och `client_filters.views` fÃ¶r lokala bolags-/periodvÃ¤xlingar
nÃ¤r bredare data redan Ã¤r hÃ¤mtad. SjÃ¤lva spÃ¥rningsraderna skickas inte i
huvudpayloaden utan hÃ¤mtas via
`GET /api/sankey/inbound/trace?token=&scope=all|node|link&id=&company=&start_date=&end_date=&only_consumed=&offset=&limit=`
eller streamas som CSV via
`GET /api/sankey/inbound/trace.csv?token=&scope=&id=&company=&start_date=&end_date=&only_consumed=&name=`. Dag/vecka/manad
forbygger lokala klientvyer nar vyantalet ryms. Stora svar kan
sÃ¤tta `client_filters.prebuilt=false` och lÃ¥ta klienten hÃ¤mta nÃ¤sta
filtervariant via API/SSE i stÃ¤llet fÃ¶r att fÃ¶rbygga alla lokala vyer.

| `public.hours` | `GET` | `/api/public/hours` | Publika timmar fÃ¶r dag |
| `public.hours_week` | `GET` | `/api/public/hours/week` | Publika timmar fÃ¶r vecka |
| `public.persons` | `GET` | `/api/public/persons` | Publika FTE fÃ¶r dag |
| `public.persons_week` | `GET` | `/api/public/persons/week` | Publika FTE fÃ¶r vecka |
| `public.summary` | `GET` | `/api/public/summary` | Publik CSV-summering fÃ¶r dag |
| `public.summary_week` | `GET` | `/api/public/summary/week` | Publik CSV-summering fÃ¶r vecka |
| `meta.uploads` | `POST` | `/api/meta/uploads` | Publik meta-uppladdning av bilder och videor; backendfel auditloggas sanerat som `meta_media_upload/upload_failed` |
| `meta.list_uploads` | `GET` | `/api/meta/uploads` | Super User-lista Ã¶ver meta-uppladdningar med hash, storlek och videolÃ¤ngd |
| `meta.shipment_observations` | `GET` | `/api/meta/shipment-observations` | SÃ¤ndningsanalys fÃ¶r Meta-videor med video-ID, lÃ¤ngd och storlek |
| `meta.shipment_observations_export` | `GET` | `/api/meta/shipment-observations/export` | Excel-export for Meta-sandningsanalys med videostorlek |
| `meta.analyze` | `POST` | `/api/meta/uploads/{upload_id}/analyze` | Analysera Meta-video |
| `meta.shipment_status` | `PATCH` | `/api/meta/shipment-observations/{observation_id}/status` | Uppdatera status for Meta-rad |
| `meta.shipment_dispatch_lookup` | `PATCH` | `/api/meta/shipment-observations/{observation_id}/dispatch-lookup` | Skriv tillbaka lokalt ASK-uppslag for Meta-rad |
| `meta.content` | `GET` | `/api/meta/uploads/{upload_id}/content` | Visa eller spela upp meta-uppladdning |
| `meta.delete` | `DELETE` | `/api/meta/uploads/{upload_id}` | Radera meta-uppladdning |

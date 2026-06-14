# API-vägar och CLI

Det här är den fulla API-täckningen som `tools.flow_cli` känner till.
Testen `tests/tools/test_flow_cli.py` jämför listan mot FastAPI-appen så
nya `/api/*`-vägar inte tappas bort.

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

`call` använder namngivna API-vägar. `api` kan anropa valfri väg manuellt, även
om en ny väg ännu inte fått ett namn i CLI:t.

Lagerverktygen har två CLI-lager:

- `python -m tools.flow_cli allocation ...` kör samma `/api/allokering`-vägar som webb/desktop, inklusive auth-cookie, sessionsresultat och CSV-nedladdning.
- `python -m warehouse_tools.cli ...` kör Bearbeta/Dela lokalt utan server, IndexedDB eller cookies. Det är snabbast för regressions- och paritytester.

Exempel:

```powershell
python -m warehouse_tools.cli list-flows
python -m warehouse_tools.cli schema allocate
python -m warehouse_tools.cli detect .\testdata\warehouse_tools\v_ask_customer_order_details_all-20260317145125.csv
python -m warehouse_tools.cli allocate --auto-file orders.csv --auto-file buffer.csv --format both --out artifacts\allocate
python -m tools.compare_warehouse_results --left .\Resultat.csv --right .\allocated_orders.xlsx
```

Användar-API:t är bakåtkompatibelt med `role`, men nya klienter kan skicka
`roles`, t.ex. `{"username":"anna","roles":["viewer","leader"]}`,
`{"username":"petra","roles":["staffing_manager"]}` för Bemanningsansvarig,
`{"username":"lina","roles":["warehouse_clerk"]}` för Lagerkontorist och
`{"username":"arvid","roles":["article_placer"]}` för Artikelplacerare.

## Verksamhetsscope

`/api/auth/me` returnerar aktuell anvandares `business_id`, verksamhetskod och
verksamhetsnamn. Icke-Super Users filtreras alltid till sin egen verksamhet i
listor och detail/update/delete-svar. Super User kan anvanda `business_id` pa
scopebara listor som personer, aktiviteter, omraden, anvandare, schema,
oversikt och settings; utan filter betyder `∞` globalt dar API:t tillater det.

Publika `/api/public/*` tar queryparametern `business` och defaultar till
`STIGAMO` for bakatkompatibilitet. De summerar aldrig globalt over flera
verksamheter.

| Namn | Metod | Väg | Beskrivning |
| --- | --- | --- | --- |
| `health` | `GET` | `/api/health` | Server health |
| `healthcheck.report` | `GET` | `/api/healthcheck` | Server-, Render- och databashalsa |
| `healthcheck.wait_metrics` | `POST` | `/api/healthcheck/wait-metrics` | Samla vantetidsmatningar |
| `healthcheck.wait_summary` | `GET` | `/api/healthcheck/wait-metrics/summary` | Analysera anvandarvantetider |
| `businesses.list` | `GET` | `/api/businesses` | Lista verksamheter |
| `businesses.create` | `POST` | `/api/businesses` | Skapa verksamhet |
| `businesses.update` | `PUT` | `/api/businesses/{business_id}` | Uppdatera verksamhet |
| `auth.login` | `POST` | `/api/auth/login` | Logga in |
| `auth.logout` | `POST` | `/api/auth/logout` | Logga ut |
| `auth.me` | `GET` | `/api/auth/me` | Aktuell användare |
| `auth.set_password` | `POST` | `/api/auth/set-password` | Sätt första lösenord |
| `assistant.chat` | `POST` | `/api/assistant/chat` | Fråga apphjälpen |
| `assistant.clear` | `POST` | `/api/assistant/clear` | Rensa apphjälpens dialogkvot |
| `query_data.health` | `GET` | `/api/query-data/health` | Datahämtning health |
| `query_data.reload_catalog` | `POST` | `/api/query-data/catalog/reload` | Läs om extern datakatalog |
| `query_data.plan` | `POST` | `/api/query-data/plan` | Tolka datafråga med MiniMax |
| `query_data.run` | `POST` | `/api/query-data/run` | Hämta data från extern datakälla |
| `query_data.export` | `GET` | `/api/query-data/export/{session_id}` | Exportera datahämtning till Excel |
| `allocation.health` | `GET` | `/api/allokering/health` | Lagerverktyg health |
| `allocation.flows` | `GET` | `/api/allokering/flows` | Lista lagerverktygsflöden |
| `allocation.pool` | `GET` | `/api/allokering/pool` | Lista lagerverktygens uppladdningsslots |
| `allocation.process_matrix_get` | `GET` | `/api/allokering/process-matrix` | Hämta Bearbeta-matris |
| `allocation.process_matrix_update` | `PUT` | `/api/allokering/process-matrix` | Uppdatera Bearbeta-matris |
| `allocation.filter_profile_get` | `GET` | `/api/allokering/filter-profile` | Hamta personliga Bearbeta-profiler |
| `allocation.filter_profile_update` | `PUT` | `/api/allokering/filter-profile` | Spara personliga Bearbeta-profiler |
| `allocation.filter_profile_import` | `POST` | `/api/allokering/filter-profile/import` | Kopiera Bearbeta-profil fran anvandare |
| `allocation.map_layout_get` | `GET` | `/api/allokering/ytgenerering-map-layout` | Hamta Ytgenerering-kartlayout |
| `allocation.map_layout_update` | `PUT` | `/api/allokering/ytgenerering-map-layout` | Uppdatera Ytgenerering-kartlayout |
| `allocation.map_location_options` | `GET` | `/api/allokering/ytgenerering-location-options` | Hamta Ytgenerering U-platslista |
| `allocation.detect` | `POST` | `/api/allokering/detect` | Identifiera lagerverktygsfil |
| `allocation.observations_update` | `POST` | `/api/allokering/observations/update` | Uppdatera observations från buffert |
| `allocation.run_flow` | `POST` | `/api/allokering/flow/{flow_id}` | Kör lagerverktygsflöde |
| `allocation.open_excel` | `POST` | `/api/allokering/open-excel` | Öppna lagerverktygsresultat i Excel |
| `allocation.table_column` | `GET` | `/api/allokering/table-column/{session_id}/{key}/{column_index}` | Hämta resultatkolumn |
| `allocation.download` | `GET` | `/api/allokering/download/{session_id}/{key}` | Ladda ner Allokering-resultat |
| `workflow_data.source` | `POST` | `/api/workflow-data/source` | Hamta workflow-kalla som temporar CSV |
| `coredata.files` | `GET` | `/api/coredata/files` | Coredata-karnfiler fran Postgres/fallback och sammanstalld data for verksamheten |
| `coredata.preview` | `GET` | `/api/coredata/files/{file_key}/preview` | Forhandsvisa coredata-karnfil eller sammanstalld data |
| `coredata.download` | `GET` | `/api/coredata/files/{file_key}/download` | Ladda ner coredata-karnfil eller sammanstalld data |
| `coredata.upload_raw` | `POST` | `/api/coredata/files/raw` | Ladda upp coredata-karnfil till Postgres eller sammanstalld datafil |
| `areas.list` | `GET` | `/api/areas` | Lista områden |
| `areas.create` | `POST` | `/api/areas` | Skapa område |
| `areas.update` | `PUT` | `/api/areas/{area_id}` | Uppdatera område |
| `areas.delete` | `DELETE` | `/api/areas/{area_id}` | Ta bort eller inaktivera område |
| `activities.list` | `GET` | `/api/activities` | Lista aktiviteter med KPI Mal-processnamn och arbetstyp |
| `activities.import_template` | `GET` | `/api/activities/import-template` | Hämta importmall för aktiviteter |
| `activities.import` | `POST` | `/api/activities/import` | Importera aktiviteter |
| `activities.import_rows` | `POST` | `/api/activities/import-rows` | Importera aktivitetsrader med valfria KPI Mal-processnamn och arbetstyp (`normal`/`VAS`) |
| `activities.create` | `POST` | `/api/activities` | Skapa aktivitet med valfria KPI Mal-processnamn och arbetstyp |
| `activities.update` | `PUT` | `/api/activities/{activity_id}` | Uppdatera aktivitet med valfria KPI Mal-processnamn och arbetstyp |
| `activities.delete` | `DELETE` | `/api/activities/{activity_id}` | Ta bort aktivitet |
| `settings.get` | `GET` | `/api/settings` | Hämta verksamhetens inställningar |
| `settings.update` | `PUT` | `/api/settings` | Uppdatera verksamhetens inställningar |
| `settings.staffing_get` | `GET` | `/api/settings/staffing` | Hämta bemanningens historiktimmar och val för historiskt snitt |
| `settings.staffing_update` | `PUT` | `/api/settings/staffing` | Uppdatera bemanningens historiktimmar och val för historiskt snitt |
| `settings.sidebar_get` | `GET` | `/api/settings/sidebar` | Hämta verksamhetens sidomeny |
| `settings.sidebar_update` | `PUT` | `/api/settings/sidebar` | Uppdatera verksamhetens sidomeny |
| `settings.role_access_get` | `GET` | `/api/settings/role-access` | Hämta verksamhetens roll-vyåtkomst |
| `settings.role_access_update` | `PUT` | `/api/settings/role-access` | Uppdatera verksamhetens roll-vyåtkomst |
| `settings.feature_registry` | `GET` | `/api/settings/feature-registry` | Hämta backend-ägd produktkarta |
| `audit.list` | `GET` | `/api/audit` | Lista auditlogg |
| `audit.summary` | `GET` | `/api/audit/summary` | Audit-summering |
| `audit.errors` | `GET` | `/api/audit/errors` | Felkodsdashboard |
| `audit.client_error` | `POST` | `/api/audit/client-error` | Logga användarens API-fel |
| `audit.client_event` | `POST` | `/api/audit/client-event` | Logga tysta UI-händelser som vyöppning |
| `audit.local_run` | `POST` | `/api/audit/local-run` | Logga sanerad Windows-korning |
| `audit.interactions` | `POST` | `/api/audit/interactions` | Logga batchade anvandarinteraktioner |
| `audit.interactions_public` | `POST` | `/api/audit/interactions/public` | Logga allowlistad publik meta-tracking |
| `audit.interactions_list` | `GET` | `/api/audit/interactions` | Lista trackingevents |
| `audit.interactions_summary` | `GET` | `/api/audit/interactions/summary` | Summera trackingevents |
| `audit.interactions_coverage` | `GET` | `/api/audit/interactions/coverage` | Visa trackingtackning |
| `audit.interactions_chat` | `POST` | `/api/audit/interactions/chat` | Fraga MiniMax om trackinghistorik |
| `audit.interactions_chat_clear` | `POST` | `/api/audit/interactions/chat/clear` | Rensa Historik-AI |
| `persons.list` | `GET` | `/api/persons` | Lista personer |
| `persons.import_template` | `GET` | `/api/persons/import-template` | Hämta importmall för personer |
| `persons.import` | `POST` | `/api/persons/import` | Importera personer |
| `persons.import_rows` | `POST` | `/api/persons/import-rows` | Importera personrader |
| `persons.create` | `POST` | `/api/persons` | Skapa person |
| `persons.sort_order` | `PUT` | `/api/persons/sort-order` | Sortera personer inom anvandarens omrade |
| `persons.get` | `GET` | `/api/persons/{person_id}` | Hämta person |
| `persons.update` | `PUT` | `/api/persons/{person_id}` | Uppdatera person |
| `persons.delete` | `DELETE` | `/api/persons/{person_id}` | Ta bort person |
| `person_schedules.get` | `GET` | `/api/persons/{person_id}/schedule` | Hämta veckomall |
| `person_schedules.update` | `PUT` | `/api/persons/{person_id}/schedule` | Uppdatera veckomall |
| `schedule.get` | `GET` | `/api/schedule` | Hämta dagsschema |
| `schedule.set_cell` | `PUT` | `/api/schedule/cell` | Sätt schemacell |
| `schedule.split_cell` | `PUT` | `/api/schedule/cell/split` | Dela/slå ihop schemacell |
| `schedule.bulk_cells` | `POST` | `/api/schedule/cells` | Sätt flera schemaceller |
| `schedule.restore_hours` | `PUT` | `/api/schedule/hours/restore` | Återställ timmar |
| `schedule.summary` | `GET` | `/api/schedule/summary` | Schema-summering |
| `schedule.revision` | `GET` | `/api/schedule/revision` | Schema-revision |
| `schedule.presence` | `GET` | `/api/schedule/presence` | NÃ¤rvarolista fÃ¶r utskrift |
| `schedule.calculator_profile` | `GET` | `/api/schedule/calculator-profile` | Hamta personliga automatiska bemanningskalkyler |
| `schedule.calculator_profile_update` | `PUT` | `/api/schedule/calculator-profile` | Spara personliga automatiska bemanningskalkyler |
| `schedule.calculator_profile_import` | `POST` | `/api/schedule/calculator-profile/import` | Kopiera bemanningskalkyler fran anvandare |
| `schedule.calculator_automatic` | `GET` | `/api/schedule/calculator/automatic` | Berakna automatiska bemanningskalkyler |
| `schedule.activity_capacity` | `GET` | `/api/schedule/activity-capacity` | Historiskt snitt per person och vald bemanningsaktivitet |
| `schedule.activity_capacity_cell` | `GET` | `/api/schedule/activity-capacity/cell` | Historiskt snitt för en person och aktivitet vid cell-hover |
| `schedule.productivity_summary` | `GET` | `/api/schedule/productivity-summary` | Latt produktivitetsprocent per person for Bemanning |
| `schedule.copy` | `POST` | `/api/schedule/copy` | Kopiera dag/vecka |
| `schedule.clear` | `POST` | `/api/schedule/clear` | Rensa schema |
| `schedule.fill_from_left` | `POST` | `/api/schedule/fill-from-left` | Fyll från vänster |
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
| `personal.persons` | `GET` | `/api/personal/persons` | Personval för personliga vyer |
| `personal.schedule` | `GET` | `/api/personal/schedule` | Mitt schema för en person |
| `personal.productivity` | `GET` | `/api/personal/productivity` | Min produktivitet med schema och global personproduktivitet |
| `overview.week` | `GET` | `/api/overview` | Översikt vecka |
| `overview.month` | `GET` | `/api/overview/month` | Översikt månad |
| `overview.revision` | `GET` | `/api/overview/revision` | Översikt revision |
| `overview.revision_month` | `GET` | `/api/overview/revision/month` | Översikt månadsrevision |
| `overview.set_day` | `POST` | `/api/overview/day` | Sätt dag i översikt |
| `overview.bulk_days` | `POST` | `/api/overview/days/bulk` | Sätt flera dagar i översikt |
| `users.list` | `GET` | `/api/users` | Lista användare |
| `users.import_template` | `GET` | `/api/users/import-template` | Hämta importmall för användare |
| `users.import` | `POST` | `/api/users/import` | Importera användare |
| `users.import_rows` | `POST` | `/api/users/import-rows` | Importera användarrader |
| `users.create` | `POST` | `/api/users` | Skapa användare |
| `users.update` | `PUT` | `/api/users/{user_id}` | Uppdatera användare |
| `users.delete` | `DELETE` | `/api/users/{user_id}` | Ta bort användare |
| `productivity.sync` | `POST` | `/api/productivity/sync` | Synka valt datum, eller dagens produktivitetsdata om datum saknas |
| `productivity.person` | `GET` | `/api/productivity/persons/{person_id}` | Personens produktivitetssnitt per aktivitet for vecka/manad/ar/datumperiod |
| `productivity.overview` | `GET` | `/api/productivity/overview` | Produktivitetsoversikt for dag/vecka/manad/ar/datumperiod |
| `productivity.report` | `GET` | `/api/productivity` | Produktivitetsrapport; lasning ar tillaten for `productivity=view` |

Produktivitetens API-snapshot använder källorna `pick`, `trans`, `pallet`
(`LOADING_LOG`), `receive`, `order_log`, `sort`, `base_pallet` och `kpi`.
Schedulerstart fyller 13 dagar bakåt plus idag; därefter uppdateras bara dagens
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
fylla pa data.

| `public.hours` | `GET` | `/api/public/hours` | Publika timmar för dag |
| `public.hours_week` | `GET` | `/api/public/hours/week` | Publika timmar för vecka |
| `public.persons` | `GET` | `/api/public/persons` | Publika FTE för dag |
| `public.persons_week` | `GET` | `/api/public/persons/week` | Publika FTE för vecka |
| `public.summary` | `GET` | `/api/public/summary` | Publik CSV-summering för dag |
| `public.summary_week` | `GET` | `/api/public/summary/week` | Publik CSV-summering för vecka |
| `meta.uploads` | `POST` | `/api/meta/uploads` | Publik meta-uppladdning av bilder och videor; backendfel auditloggas sanerat som `meta_media_upload/upload_failed` |
| `meta.list_uploads` | `GET` | `/api/meta/uploads` | Super User-lista över meta-uppladdningar med hash, storlek och videolängd |
| `meta.shipment_observations` | `GET` | `/api/meta/shipment-observations` | Sändningsanalys för Meta-videor med video-ID, längd och storlek |
| `meta.shipment_observations_export` | `GET` | `/api/meta/shipment-observations/export` | Excel-export for Meta-sandningsanalys med videostorlek |
| `meta.analyze` | `POST` | `/api/meta/uploads/{upload_id}/analyze` | Analysera Meta-video |
| `meta.content` | `GET` | `/api/meta/uploads/{upload_id}/content` | Visa eller spela upp meta-uppladdning |
| `meta.delete` | `DELETE` | `/api/meta/uploads/{upload_id}` | Radera meta-uppladdning |

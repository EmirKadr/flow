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
| `allocation.detect` | `POST` | `/api/allokering/detect` | Identifiera lagerverktygsfil |
| `allocation.observations_update` | `POST` | `/api/allokering/observations/update` | Uppdatera observations från buffert |
| `allocation.run_flow` | `POST` | `/api/allokering/flow/{flow_id}` | Kör lagerverktygsflöde |
| `allocation.open_excel` | `POST` | `/api/allokering/open-excel` | Öppna lagerverktygsresultat i Excel |
| `allocation.table_column` | `GET` | `/api/allokering/table-column/{session_id}/{key}/{column_index}` | Hämta resultatkolumn |
| `allocation.download` | `GET` | `/api/allokering/download/{session_id}/{key}` | Ladda ner Allokering-resultat |
| `areas.list` | `GET` | `/api/areas` | Lista områden |
| `areas.create` | `POST` | `/api/areas` | Skapa område |
| `areas.update` | `PUT` | `/api/areas/{area_id}` | Uppdatera område |
| `areas.delete` | `DELETE` | `/api/areas/{area_id}` | Ta bort eller inaktivera område |
| `activities.list` | `GET` | `/api/activities` | Lista aktiviteter |
| `activities.import_template` | `GET` | `/api/activities/import-template` | Hämta importmall för aktiviteter |
| `activities.import` | `POST` | `/api/activities/import` | Importera aktiviteter |
| `activities.import_rows` | `POST` | `/api/activities/import-rows` | Importera aktivitetsrader |
| `activities.create` | `POST` | `/api/activities` | Skapa aktivitet |
| `activities.update` | `PUT` | `/api/activities/{activity_id}` | Uppdatera aktivitet |
| `activities.delete` | `DELETE` | `/api/activities/{activity_id}` | Ta bort aktivitet |
| `settings.get` | `GET` | `/api/settings` | Hämta verksamhetens inställningar |
| `settings.update` | `PUT` | `/api/settings` | Uppdatera verksamhetens inställningar |
| `settings.sidebar_get` | `GET` | `/api/settings/sidebar` | Hämta verksamhetens sidomeny |
| `settings.sidebar_update` | `PUT` | `/api/settings/sidebar` | Uppdatera verksamhetens sidomeny |
| `settings.role_access_get` | `GET` | `/api/settings/role-access` | Hämta verksamhetens roll-vyåtkomst |
| `settings.role_access_update` | `PUT` | `/api/settings/role-access` | Uppdatera verksamhetens roll-vyåtkomst |
| `audit.list` | `GET` | `/api/audit` | Lista auditlogg |
| `audit.summary` | `GET` | `/api/audit/summary` | Audit-summering |
| `audit.errors` | `GET` | `/api/audit/errors` | Felkodsdashboard |
| `audit.client_error` | `POST` | `/api/audit/client-error` | Logga användarens API-fel |
| `persons.list` | `GET` | `/api/persons` | Lista personer |
| `persons.import_template` | `GET` | `/api/persons/import-template` | Hämta importmall för personer |
| `persons.import` | `POST` | `/api/persons/import` | Importera personer |
| `persons.import_rows` | `POST` | `/api/persons/import-rows` | Importera personrader |
| `persons.create` | `POST` | `/api/persons` | Skapa person |
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
| `schedule.copy` | `POST` | `/api/schedule/copy` | Kopiera dag/vecka |
| `schedule.clear` | `POST` | `/api/schedule/clear` | Rensa schema |
| `schedule.fill_from_left` | `POST` | `/api/schedule/fill-from-left` | Fyll från vänster |
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
| `productivity.files` | `GET` | `/api/productivity/files` | Produktivitetsfilstatus |
| `productivity.targets` | `GET` | `/api/productivity/targets` | Hämta KPI-mål |
| `productivity.upload` | `POST` | `/api/productivity/files` | Ladda upp produktivitetsfil(er) |
| `productivity.upload_raw` | `POST` | `/api/productivity/files/raw` | Ladda upp rå produktivitetsfil |
| `productivity.delete_file` | `DELETE` | `/api/productivity/files/{file_type}` | Ta bort produktivitetsfil |
| `productivity.report` | `GET` | `/api/productivity` | Produktivitetsrapport |
| `public.hours` | `GET` | `/api/public/hours` | Publika timmar för dag |
| `public.hours_week` | `GET` | `/api/public/hours/week` | Publika timmar för vecka |
| `public.persons` | `GET` | `/api/public/persons` | Publika FTE för dag |
| `public.persons_week` | `GET` | `/api/public/persons/week` | Publika FTE för vecka |
| `public.summary` | `GET` | `/api/public/summary` | Publik CSV-summering för dag |
| `public.summary_week` | `GET` | `/api/public/summary/week` | Publik CSV-summering för vecka |

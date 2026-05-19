# API-vägar och CLI

Det här är den fulla API-täckningen som `tools.bemanning_cli` känner till.
Testen `tests/tools/test_bemanning_cli.py` jämför listan mot FastAPI-appen så
nya `/api/*`-vägar inte tappas bort.

Vanliga kommandon:

```powershell
python -m tools.bemanning_cli routes --format table
python -m tools.bemanning_cli routes --format markdown
python -m tools.bemanning_cli --base-url http://127.0.0.1:8000 auth login --username admin --password admin123
python -m tools.bemanning_cli call schedule.get --query year=2026 --query week=21 --query weekday=1
python -m tools.bemanning_cli call persons.import --file file=personer.xlsx
python -m tools.bemanning_cli call activities.import --file file=stallen.xlsx
python -m tools.bemanning_cli api GET /api/health
```

`call` använder namngivna API-vägar. `api` kan anropa valfri väg manuellt, även
om en ny väg ännu inte fått ett namn i CLI:t.

Användar-API:t är bakåtkompatibelt med `role`, men nya klienter kan skicka
`roles`, t.ex. `{"username":"anna","roles":["viewer","leader"]}`,
`{"username":"petra","roles":["staffing_manager"]}` för Bemanningsansvarig,
`{"username":"lina","roles":["warehouse_clerk"]}` för Lagerkontorist och
`{"username":"arvid","roles":["article_placer"]}` för Artikelplacerare.

| Namn | Metod | Väg | Beskrivning |
| --- | --- | --- | --- |
| `health` | `GET` | `/api/health` | Server health |
| `auth.login` | `POST` | `/api/auth/login` | Logga in |
| `auth.logout` | `POST` | `/api/auth/logout` | Logga ut |
| `auth.me` | `GET` | `/api/auth/me` | Aktuell användare |
| `auth.set_password` | `POST` | `/api/auth/set-password` | Sätt första lösenord |
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
| `activities.list` | `GET` | `/api/activities` | Lista aktiviteter |
| `activities.import_template` | `GET` | `/api/activities/import-template` | Hämta importmall för ställen |
| `activities.import` | `POST` | `/api/activities/import` | Importera ställen |
| `activities.create` | `POST` | `/api/activities` | Skapa aktivitet |
| `activities.update` | `PUT` | `/api/activities/{activity_id}` | Uppdatera aktivitet |
| `activities.delete` | `DELETE` | `/api/activities/{activity_id}` | Inaktivera aktivitet |
| `settings.get` | `GET` | `/api/settings` | Hämta inställningar |
| `settings.update` | `PUT` | `/api/settings` | Uppdatera inställningar |
| `settings.sidebar_get` | `GET` | `/api/settings/sidebar` | Hämta global sidomeny |
| `settings.sidebar_update` | `PUT` | `/api/settings/sidebar` | Uppdatera global sidomeny |
| `settings.role_access_get` | `GET` | `/api/settings/role-access` | Hämta rollernas vyåtkomst |
| `settings.role_access_update` | `PUT` | `/api/settings/role-access` | Uppdatera rollernas vyåtkomst |
| `audit.list` | `GET` | `/api/audit` | Lista auditlogg |
| `audit.summary` | `GET` | `/api/audit/summary` | Audit-summering |
| `persons.list` | `GET` | `/api/persons` | Lista personer |
| `persons.import_template` | `GET` | `/api/persons/import-template` | Hämta importmall för personer |
| `persons.import` | `POST` | `/api/persons/import` | Importera personer |
| `persons.create` | `POST` | `/api/persons` | Skapa person |
| `persons.get` | `GET` | `/api/persons/{person_id}` | Hämta person |
| `persons.update` | `PUT` | `/api/persons/{person_id}` | Uppdatera person |
| `persons.delete` | `DELETE` | `/api/persons/{person_id}` | Inaktivera person |
| `person_schedules.get` | `GET` | `/api/persons/{person_id}/schedule` | Hämta veckomall |
| `person_schedules.update` | `PUT` | `/api/persons/{person_id}/schedule` | Uppdatera veckomall |
| `schedule.get` | `GET` | `/api/schedule` | Hämta dagsschema |
| `schedule.set_cell` | `PUT` | `/api/schedule/cell` | Sätt schemacell |
| `schedule.split_cell` | `PUT` | `/api/schedule/cell/split` | Dela/slå ihop schemacell |
| `schedule.bulk_cells` | `POST` | `/api/schedule/cells` | Sätt flera schemaceller |
| `schedule.restore_hours` | `PUT` | `/api/schedule/hours/restore` | Återställ timmar |
| `schedule.summary` | `GET` | `/api/schedule/summary` | Schema-summering |
| `schedule.copy` | `POST` | `/api/schedule/copy` | Kopiera dag/vecka |
| `schedule.clear` | `POST` | `/api/schedule/clear` | Rensa schema |
| `schedule.fill_from_left` | `POST` | `/api/schedule/fill-from-left` | Fyll från vänster |
| `overview.week` | `GET` | `/api/overview` | Översikt vecka |
| `overview.month` | `GET` | `/api/overview/month` | Översikt månad |
| `overview.set_day` | `POST` | `/api/overview/day` | Sätt dag i översikt |
| `overview.bulk_days` | `POST` | `/api/overview/days/bulk` | Sätt flera dagar i översikt |
| `users.list` | `GET` | `/api/users` | Lista användare |
| `users.import_template` | `GET` | `/api/users/import-template` | Hämta importmall för användare |
| `users.import` | `POST` | `/api/users/import` | Importera användare |
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

---
title: Verksamheter och isolering
status: aktiv
updated: 2026-05-25
tags: [verksamheter, behorighet, isolering, super-user]
---

# Verksamheter och isolering

Kort svar: Verksamhet är isoleringsnivån ovanför område. Vanliga användare, även admins, ska bara se sin egen verksamhet. Super User ser alla verksamheter, får vyn Verksamheter och kan använda `∞` som globalt läge.

## Användarflöde

1. Användaren loggar in och `/api/auth/me` returnerar `business_id`, verksamhetskod, verksamhetsnamn och Super User-status.
2. Sidebarens områdestoggle byggs från verksamheten:
   - Stigamo visar Stigamos områden plus `∞`, där `∞` betyder alla Stigamo-områden.
   - R3 visar bara R3-toggle.
   - Super User kan använda `∞` som globalt allt.
3. När en vanlig användare skapar person, aktivitet, användare, schemacell eller settingsrad väljer användaren inte verksamhet. Backend använder användarens verksamhet.
4. När Super User skapar eller importerar något som inte kan härledas från område, person eller aktivitet måste Super User välja verksamhet.
5. Vanliga användare ska inte se att andra verksamheter finns. Främmande id ska ge nekad eller saknad resurs utan att visa data från den andra verksamheten.

## Knappar och kontroller

| Kontroll | Var | Vem får | Vad händer | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- | --- |
| Områdestoggle | Sidebar footer | Alla inloggade | Filtrerar vyer efter synliga områden och verksamhet | `common.js`, `flow-area-focus` | Gammalt lokalt fokus migreras från områdeskod till `AREA:<id>`. |
| `∞` | Områdestoggle | Alla, men med olika scope | Vanliga användare ser alla områden i egen verksamhet; Super User ser globalt allt | `areaFocusOptions`, business-scopeade API | En R3-användare ska inte få global `∞`. |
| Verksamheter | Sidebar | Super User | Oppnar lista over verksamheter och deras omraden | `verksamheter.html`, `businesses.js` | Saknas korrekt for vanliga anvandare. |
| Ny verksamhet | Verksamheter | Super User | Skapar verksamhet med kod, namn, sortering och aktiv-status | `POST /api/businesses` | Kod krävs och måste vara unik globalt. |
| Redigera | Verksamheter | Super User | Uppdaterar namn, sortering eller aktiv-status | `PUT /api/businesses/{business_id}` | Inaktiv verksamhet döljs i normal lista. |
| Nytt omrade | Verksamheter, under vald verksamhet | Super User | Skapar omrade pa vald verksamhet | `POST /api/areas` med `business_id` | Omradeskod far ateranvandas i annan verksamhet men inte inom samma. |
| Redigera omrade | Verksamheter, under Omraden | Super User | Uppdaterar kod, namn, sortering och aktiv-status | `PUT /api/areas/{area_id}` | Omrade kan inte flyttas mellan verksamheter. |
| Ta bort omrade | Verksamheter, under Omraden | Super User | Tar bort tomt omrade eller inaktiverar om det anvands | `DELETE /api/areas/{area_id}` | Kopplade personer, aktiviteter eller anvandare gor att omradet inaktiveras i stallet. |
| Verksamhetsfält | Personer, Aktiviteter, Användare | Super User vid create/import | Sätter explicit `business_id` eller skickar verksamhetskod i import/direkttabell | `persons.js`, `activities.js`, `users.js` | Super User får 400 om verksamhet inte kan härledas. |

## Tekniskt flöde

- `businesses` innehåller `code`, `name`, `sort_order` och `is_active`.
- `verksamheter.html` visar varje verksamhet med en undersektion Omraden. Den hamtar `/api/businesses` och `/api/areas?include_inactive=true`, grupperar omradena pa `business_id` och uppdaterar sidebarens omradesfokus efter andringar.
- `users`, `areas`, `persons`, `activities`, `audit_log` och verksamhetsspecifika `app_settings` har `business_id`.
- `STIGAMO` är bakåtkompatibel default. Migration och seed kopplar befintliga användare, områden, personer, aktiviteter, historik och settings dit.
- `R3` seedas separat med verksamhet `R3`, område `R3` och egna frånvaroaktiviteter. Stigamos personer, användare och arbetsaktiviteter kopieras inte.
- Unika regler för område, person och aktivitet är verksamhetsscopeade där samma namn/kod får finnas i flera verksamheter. Användarnamn är fortsatt globalt unika.
- `business_scope.py` är den gemensamma spärren för listfilter, detail/update/delete och write-inferens.
- Schemaceller pekar fortfarande på person och aktivitet, men writes validerar att person och aktivitet tillhör samma verksamhet.
- `app_settings` är per verksamhet. Sidebar, vybehörigheter och cell-lås kan därför skilja mellan Stigamo och R3.
- Publika `/api/public/*` tar `business` och defaultar till `STIGAMO`; de får inte summera globalt utan verksamhet.
- Webben och Windows-appen använder samma frontend via `app/`, så desktop-paritet kontrolleras med `tools.visual_smoke --via-desktop-proxy`.

- Lagerverktygens buffertpall-observations och framraknade `artikel_max.csv` ar verksamhetsseparerade. Stigamo anvander legacy-filerna i `warehouse_tools/vendor/lowfreqdata/buffertpall/`; R3 anvander egna filer under `warehouse_tools/vendor/lowfreqdata/buffertpall/r3/`. Ordersaldo, LYX och Pafyllnadsprio anvander verksamhetens karnfil nar anvandaren inte laddar upp en egen `artikel_max.csv`.

## Testkontrakt

Minsta regression när verksamhetsscope påverkas:

```powershell
python -m pytest tests/services/test_business_scope.py -q
python -m pytest tests/services/test_person_import.py tests/services/test_activity_import.py tests/services/test_user_import.py -q
python -m pytest tests/tools/test_visual_tools.py tests/tools/test_api_route_contracts.py -q
python -m tools.visual_smoke --roles admin,leader,r3 --output artifacts\visual\business-scope
python -m tools.visual_smoke --via-desktop-proxy --roles admin,r3 --output artifacts\visual\business-scope-desktop
```

`tests/services/test_business_scope.py` ska täcka många användare i båda verksamheterna, listfilter, främmande id, create/update/delete, omraden per verksamhet, dubbletter per verksamhet, settings per verksamhet, publika defaultvärden och Super User-krav på verksamhetsval.

## Felsökningssvar för framtida chat

| Fråga | Svar |
| --- | --- |
| "Varför ser jag inte R3?" | Om du inte är Super User är det korrekt. Vanliga användare ska bara se sin egen verksamhet. |
| "Varför finns bara R3 i togglen?" | Användaren tillhör R3. R3 har bara R3-toggle. |
| "Varför betyder `∞` olika saker?" | För vanliga användare betyder `∞` alla områden i egen verksamhet. För Super User betyder `∞` globalt allt. |
| "Varför måste Super User välja verksamhet?" | Backend kan inte alltid härleda verksamhet från område/person/aktivitet. Då krävs ett explicit val för att undvika fel verksamhet. |
| "Varför hittas inte ett id som jag vet finns?" | Det kan tillhöra en annan verksamhet. API:t svarar då som saknad resurs för att inte avslöja annan verksamhet. |
| "Varför påverkar inte vybehörigheten den andra verksamheten?" | Vybehörigheter och sidebar sparas per verksamhet. Ändringen gäller verksamheten som settings anropades för. |

## Källor

- `../app/backend/business_scope.py`
- `../app/backend/routers/businesses.py`
- `../app/backend/routers/persons.py`
- `../app/backend/routers/activities.py`
- `../app/backend/routers/users.py`
- `../app/backend/routers/schedule.py`
- `../app/backend/routers/public.py`
- `../app/alembic/versions/0018_businesses.py`
- `../app/frontend/js/common.js`
- `../app/frontend/js/businesses.js`
- `../app/frontend/js/persons.js`
- `../app/frontend/js/activities.js`
- `../app/frontend/js/users.js`
- `../tests/services/test_business_scope.py`
- `../TESTPROTOCOL.md`

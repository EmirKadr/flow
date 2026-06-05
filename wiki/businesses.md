---
title: Verksamheter och isolering
status: aktiv
updated: 2026-06-01
tags: [verksamheter, behorighet, isolering, super-user]
---

# Verksamheter och isolering

Kort svar: Verksamhet är isoleringsnivån ovanför område. Vanliga användare, även admins, ska bara se sin egen verksamhet. Super User ser alla verksamheter, får vyn Verksamheter och kan använda `∞` som globalt läge. En verksamhet kan också få ett eget `∞` för alla sina områden genom området `ANNAT`/`Annat`.

## Användarflöde

1. Användaren loggar in och `/api/auth/me` returnerar `business_id`, verksamhetskod, verksamhetsnamn och Super User-status.
2. Sidebarens områdestoggle byggs från verksamheten:
   - En vanlig användare ser sin verksamhets aktiva områden.
   - Om verksamheten har ett aktivt område med kod `ANNAT` visas `∞`, där `∞` betyder alla områden i den verksamheten.
   - R3 visar bara R3-toggle tills `ANNAT` läggs till för R3.
   - Super User kan använda `∞` som globalt allt.
   - Hogerklick pa togglen oppnar en direktmeny med samma scope: vanliga anvandare far omradena i egen verksamhet och Super User far alla aktiva omraden.
3. När en vanlig användare skapar person, aktivitet, användare, schemacell eller settingsrad väljer användaren inte verksamhet. Backend använder användarens verksamhet.
4. När Super User skapar eller importerar något som inte kan härledas från område, person eller aktivitet måste Super User välja verksamhet.
5. Vanliga användare ska inte se att andra verksamheter finns. Främmande id ska ge nekad eller saknad resurs utan att visa data från den andra verksamheten.

## Knappar och kontroller

| Kontroll | Var | Vem får | Vad händer | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- | --- |
| Områdestoggle | Sidebar footer | Alla inloggade | Vanligt klick stegar mellan fokuslagen; hogerklick oppnar omradesmenyn. Menyn kan scrollas nar manga omraden finns och stangs inte av scroll inne i menyn. Filtrerar vyer efter synliga områden och verksamhet | `common.js`, `flow-area-focus`, `/api/areas` | Gammalt lokalt fokus migreras från områdeskod till `AREA:<id>`. |
| `∞` | Områdestoggle | Alla, men med olika scope | Vanliga användare får `∞` när egen verksamhet har aktivt `ANNAT`; Super User ser globalt allt | `areaFocusOptions`, `ANNAT`, business-scopeade API | Om `∞` saknas för en verksamhet: lägg till `ANNAT` i Verksamheter-vyn. |
| Verksamheter | Sidebar | Super User | Oppnar lista over verksamheter och deras omraden | `verksamheter.html`, `businesses.js` | Saknas korrekt for vanliga anvandare. |
| Ny verksamhet | Verksamheter | Super User | Skapar verksamhet med namn, sortering och aktiv-status. Kod skapas automatiskt från namnet | `POST /api/businesses` | Namn krävs. Om koden redan finns får den automatiskt suffix. |
| Klickbar verksamhetscell | Verksamheter | Super User | Klicka i kod, namn, sortering eller aktiv-status för att ändra direkt i tabellen | `PUT /api/businesses/{business_id}` | Inaktiv verksamhet döljs i normal lista om `Visa inaktiva` inte är vald. |
| Rubriker | Verksamheter | Super User | Klick sorterar verksamheter eller områden efter kolumnen | `businesses.js` | Sorteringen är bara visuell och ändrar inte sparad sorteringsordning. |
| Nytt omrade | Verksamheter, under vald verksamhet | Super User | Skapar omrade pa vald verksamhet. Kod skapas automatiskt från namnet | `POST /api/areas` med `business_id` | Namn krävs. Områdeskod får återanvändas i annan verksamhet men inte inom samma. |
| Lägg till `∞` | Verksamheter, under Omraden | Super User | Skapar eller återaktiverar området `ANNAT`/`Annat` på vald verksamhet | `POST /api/areas`, `PUT /api/areas/{area_id}` | Om `ANNAT` redan finns aktivt visas `∞ aktiv`. |
| Klickbar områdescell | Verksamheter, under Omraden | Super User | Uppdaterar kod, namn, sortering och aktiv-status direkt i tabellen | `PUT /api/areas/{area_id}` | Omrade kan inte flyttas mellan verksamheter. Kodkrock inom samma verksamhet ger konflikt. |
| Ta bort omrade | Verksamheter, under Omraden | Super User | Tar bort tomt omrade eller inaktiverar om det anvands | `DELETE /api/areas/{area_id}` | Kopplade personer, aktiviteter eller anvandare gor att omradet inaktiveras i stallet. |
| Verksamhetsfält | Personer, Aktiviteter, Användare | Super User vid create/import | Sätter explicit `business_id` eller skickar verksamhetskod i import/direkttabell | `persons.js`, `activities.js`, `users.js` | Super User får 400 om verksamhet inte kan härledas. |

## Tekniskt flöde

- `businesses` innehåller `code`, `name`, `sort_order` och `is_active`.
- `verksamheter.html` visar varje verksamhet med en undersektion Omraden. Den hamtar `/api/businesses` och `/api/areas?include_inactive=true`, grupperar omradena pa `business_id` och uppdaterar sidebarens omradesfokus efter andringar.
- Celler i Verksamheter-vyn är inline-redigerbara. Text- och sifferceller sparas på Enter eller när fältet tappar fokus. Aktiv-status sparas direkt via checkbox. API-success/fel visas med toast och dokumentlogg.
- Området `ANNAT` är verksamhetens markör för eget alla-områden-läge. `common.js` filtrerar bort `ANNAT` som vanligt områdesval men lägger till `∞` när markören är aktiv.
- `POST /api/businesses` och `POST /api/areas` kan ta emot kod, men Verksamheter-vyn skickar normalt bara namn/sortering/aktiv-status. Backend skapar då en sanerad versal kod från namnet och lägger till `_2`, `_3` osv vid krock.
- `users`, `areas`, `persons`, `activities`, `audit_log` och verksamhetsspecifika `app_settings` har `business_id`.
- `STIGAMO` är bakåtkompatibel default. Migrationen kopplar befintliga användare, områden, personer, aktiviteter, historik och settings dit när verksamhetskolumnen införs.
- `R3` skapas av verksamhetsmigrationen. Lokal/dev-seed kan fylla R3-område och frånvaroaktiviteter, men seed körs inte och är spärrad mot production/live.
- Unika regler för område, person och aktivitet är verksamhetsscopeade där samma namn/kod får finnas i flera verksamheter. Användarnamn är fortsatt globalt unika.
- `business_scope.py` är den gemensamma spärren för listfilter, detail/update/delete och write-inferens.
- Schemaceller pekar fortfarande på person och aktivitet, men writes validerar att person och aktivitet tillhör samma verksamhet.
- `app_settings` är normalt per verksamhet. Sidebar och cell-lås kan därför skilja mellan Stigamo och R3, men `role_view_access` behandlas som global rollmatris.
- Publika `/api/public/*` tar `business` och defaultar till `STIGAMO`; de får inte summera globalt utan verksamhet.
- Webben och Windows-appen använder samma frontend via `app/`, så desktop-paritet kontrolleras med `tools.visual_smoke --via-desktop-proxy`.

- Lagerverktygens buffertpall-observations och framraknade `artikel_max.csv` ar verksamhetsseparerade pa persistent disk via `PRODUCTIVITY_DATA_DIR` eller `MEDIA_STORE_ROOT/flow-data`, normalt `flow-data/buffertpall/<verksamhetskod>/`. `artikel_max.csv` behandlas som sammanstalld data, inte som en vanlig coredata-karnfil. Gamla filer under `warehouse_tools/vendor/lowfreqdata/buffertpall/` ar bara legacy-seed tills datan migrerats. Ordersaldo, LYX och Pafyllnadsprio anvander verksamhetens sammanstallda data nar anvandaren inte laddar upp en egen `artikel_max.csv`; om observationshistorik saknas ska anvandaren ladda upp buffertpall for verksamheten forst. For Super User styr sidebarens omradestoggle vilken verksamhet lagerverktygen skriver/laster: R3-toggle ger R3, Stigamo-omraden ger Stigamo och `∞` faller tillbaka till kontots egen verksamhet.
- Gemensamma coredata-karnfiler ar verksamhetsseparerade i Postgres-tabellen `coredata_files`. Varje verksamhet har en egen rad per filtyp, identifierad med `business_code + file_type`. En ny uppladdning ersatter bara gamla DB-raden med samma prefix i anvandarens egen verksamhet. Gamla filer under `data/coredata/<verksamhetskod>/` kan fortfarande lasas som fallback tills de laddas upp igen, men verksamhetsscopeade floden laser inte langre Stigamos gamla root-KPI som specialfall.
- De kanda karnfilsprefixen i Uppladdningar ar `custom`, `dimension`, `dispatch_template`, `item`, `item_alias`, `item_attribute`, `item_option`, `item_security_info`, `kpi_target_rule`, `location`, `location_cost`, `pallet_type`, `trans_agency` och produktivitetens `v_ask_kpi_target`. `artikel_max` och produktivitetens `productivity_pick_observations`, `productivity_trans_observations`, `productivity_pallet_observations` ar sammanstalld data i samma verksamhetsscope. Samma filtyper far finnas i alla verksamheter, men datan far aldrig blandas mellan katalogerna.

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
| "Varför finns bara R3 i togglen?" | R3 saknar aktivt `ANNAT`. Lägg till `∞` i Verksamheter-vyn om R3 också ska ha alla-områden-läge. |
| "Varför betyder `∞` olika saker?" | För vanliga användare betyder `∞` alla områden i egen verksamhet när `ANNAT` finns där. För Super User betyder `∞` globalt allt. |
| "Varför måste Super User välja verksamhet?" | Backend kan inte alltid härleda verksamhet från område/person/aktivitet. Då krävs ett explicit val för att undvika fel verksamhet. |
| "Varför finns ingen kodruta när jag skapar verksamhet eller område?" | Koden skapas automatiskt från namnet när du sparar. Vid krock får den ett nummersuffix. |
| "Hur ändrar jag ett värde i Verksamheter?" | Klicka direkt i cellen, ändra värdet och tryck Enter eller klicka utanför. Aktiv-status ändras med checkboxen. |
| "Varför hittas inte ett id som jag vet finns?" | Det kan tillhöra en annan verksamhet. API:t svarar då som saknad resurs för att inte avslöja annan verksamhet. |
| "Varför påverkar vybehörigheten även den andra verksamheten?" | Vybehörigheter är globala per roll. Menyordning och vissa settings kan vara verksamhetsspecifika, men rollens vyåtkomst är samma i Stigamo och R3. |

## Källor

- `../app/backend/business_scope.py`
- `../app/backend/routers/businesses.py`
- `../app/backend/coredata_service.py`
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

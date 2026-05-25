---
title: Anvandare och installningar
status: aktiv
updated: 2026-05-25
tags: [anvandare, settings, roller, ui]
---

# Anvandare och installningar

Kort svar: Anvandare-sidan hanterar konton, roller, omrade, forsta losenord, verksamhetsspecifik cell-lasning och rollernas globala vyatkomst. Anvandare ar alltid aktiva; konton som inte ska finnas kvar tas bort. Super User har dessutom vyn Verksamheter dar verksamheter och deras omraden administreras.

Omradesfokus i sidebar filtrerar anvandarlistan inom anvandarens verksamhet. `∞` visar alla omraden i den verksamheten; for Super User betyder `∞` globalt allt. Nar en ny anvandare skapas forvalt valt omradesfokus som anvandarens omrade, men omradet kan fortfarande andras i modalen eller lamnas tomt.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Ny anvandare | Oppnar modal | Skapar konto med en roll | `POST /api/users` | Anvandarnamn och en roll kravs. |
| Flera nya anvandare | Oppnar tabellmodal | Skapar flera konton direkt i appen med en roll per rad | `POST /api/users/import-rows` | Dubbletter, okanda roller och okanda omraden visas i resultatmodal. |
| Ladda ner importmall | Hamter Excelmall | Laddar ner mall | `GET /api/users/import-template` | Kräver `userImport` edit/super user enligt backend. |
| Importera Excel | Oppnar filval | Importerar anvandare | `POST /api/users/import` | Importerade utan losenord far `must_change_password=true`. |
| Vybehorigheter | Oppnar rollmatris | Sparar global vyatkomst for roller | `GET/PUT /api/settings/role-access` | Fel matris kan dolja vyer for rollen i alla verksamheter. |
| Import-hjalp | Oppnar hjalpmodal | Visar importstod | `setupImportHelpButton` | Ingen serverkoppling. |
| Las bemanningsceller... | Checkbox | Sparar setting per verksamhet | `PUT /api/settings` | Nar aktiv kan ledare stoppas fran celler andra fyllt i aktuell verksamhet. |
| Redigera | Oppnar modal | Uppdaterar konto | `PUT /api/users/{id}` | Sista admin kan inte nedgraderas. |
| Ta bort | Bekraftar borttagning | Tar bort konto permanent och nollar gamla `updated_by`/audit-referenser | `DELETE /api/users/{id}` | Eget konto, sista admin i en verksamhet och demo-användaren skyddas. |
| Verksamheter | Sidebar-vy for Super User | Skapar/redigerar verksamheter och omraden | `GET/POST/PUT /api/businesses`, `GET/POST/PUT/DELETE /api/areas` | Vanliga anvandare ser inte vyn. Omraden med kopplad data inaktiveras i stallet for att hardraderas. |

Andringar i anvandare, forsta losenord och verksamhetens installningar skrivs till Historik. Loggen visar till exempel `user/set_password`, `app_setting/update_lock`, `app_setting/update_sidebar_layout` och `app_setting/update_role_access`, men aldrig sjalva losenordet.

## Ny/redigera anvandare-modal

Falt:

- Anvandarnamn.
- Visningsnamn.
- Roll som ett val nar kontot skapas.
- Roller som checkboxar nar ett befintligt konto redigeras.
- Omrade.
- Verksamhet visas bara for Super User nar den inte kan harledas.
- Losenord.

Validering:

- Anvandarnamn kravs.
- En roll kravs vid skapande. Vid redigering kravs minst en roll.
- Losenord, om ifyllt, maste vara minst 8 tecken.
- Super-user-rollandring skyddas av backendregler.
- Vanliga admins kan bara skapa/andra anvandare i sin egen verksamhet. Super User maste valja verksamhet eller ett omrade som harleder verksamheten.
- `is_active=false` accepteras inte vid uppdatering; ta bort kontot i stallet.

Knappar:

- `Avbryt`: stanger utan att spara.
- `Spara`: skickar `POST` eller `PUT`.

### Demo-anvandaren

Det fasta `demo`-kontot (se [demo-laget](demo-mode.md)) visas med en `DEMO`-pill i listan, har dold delete-knapp och har disablade `Anvandarnamn` + `Roller` i edit-modalen. Lösenord, visningsnamn och omrade kan fortfarande andras av super_user — backend nekar 409 om någon försoker dopa om, ta bort admin-rollen eller inaktivera kontot. Konton skapas och uppdateras automatiskt vid varje deploy av `seed_demo_user()`.

## Vybehorigheter-modal

Rollmatrisen visar vyer som rader och roller som kolumner. Matrisen ar global, sa samma roll far samma vyatkomst i Stigamo och R3. Super User-kolumnen visas som last `Redigera` eftersom rollen alltid har full atkomst. Demo-kolumnen styr extra vyatkomst for det fasta `demo`-kontot, som fortfarande ar skyddat som admin-konto. Varje vanlig knapp cyklar:

`Ingen` -> `Visa` -> `Redigera` -> `Ingen`

Raden `Personsortering` (`personSortOrder`) styr om Bemanningsansvarig/admin kan dra personnamn i Bemanning och Oversikt for att uppdatera sorteringsnumret i Personer. Super User har alltid edit via backendens Super User-regel, men sorteringen kraver fortfarande att anvandaren har ett omrade och att personen har samma hemomrade.

Knappar:

- `Standard`: aterstaller modalens draft till defaultmatris.
- `Avbryt`: stanger utan att spara.
- `Spara`: skickar `PUT /api/settings/role-access` och galler alla verksamheter.

## Importregler

- Direktimporten `Flera nya anvandare` har falten anvandarnamn, visningsnamn, roll, omrade och vid behov verksamhet. Roll ar ett dropdown-val och bara en roll kan valjas per ny anvandare.
- Varje kolumn i direkttabellen visar om faltet ar `Obligatoriskt` eller `Frivilligt` i rubriken.
- Excelimporten accepterar fortfarande samma svenska rollnamn och kan lasa flera roller separerade med komma.
- Importerade anvandare skapas aktiva utan losenord och far `must_change_password=true`.
- Dubbletter i fil, i direkttabellen eller mot befintliga anvandare stoppas och visas i resultatmodalen. Anvandarnamn ar globalt unika aven over verksamheter.

## Verksamheter-vy

Vyn finns bara for Super User och visar `code`, `name`, `sort_order` och aktiv-status for verksamheter. Under varje verksamhet visas dess omraden.

Knappar:

- `Ny verksamhet`: oppnar modal och skapar via `POST /api/businesses`.
- `Redigera`: uppdaterar namn, sortering eller aktiv-status via `PUT /api/businesses/{business_id}`.
- `Nytt omrade`: skapar omrade pa vald verksamhet via `POST /api/areas` med `business_id`.
- `Redigera` under Omraden: uppdaterar kod, namn, sortering eller aktiv-status via `PUT /api/areas/{area_id}`.
- `Ta bort` under Omraden: anropar `DELETE /api/areas/{area_id}`. Tomma omraden tas bort; omradet inaktiveras om personer, aktiviteter eller anvandare redan ar kopplade till det.
- `Visa inaktiva`: laddar aven inaktiva verksamheter och omraden.

Supportregel: vanliga anvandare ska inte veta att andra verksamheter finns. Om en Stigamo- eller R3-anvandare saknar Verksamheter-vyn ar det korrekt beteende.

## Menyeditor per verksamhet

Denna finns i sidebar, inte i `anvandare.html`, men hor till settings:

- Pennikonen oppnar "Redigera meny".
- Varje rad har flytta upp/ned, rubrik ovanfor och "Under" for undervy.
- `Standard` aterstaller defaultlayout.
- `Spara` skickar `PUT /api/settings/sidebar` och galler aktuell verksamhet. Super User kan styra annan verksamhet genom API-filter.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor syns inte en sida for en roll?" | Kontrollera `Vybehorigheter`; vyn kan sta pa `Ingen` globalt for rollen. |
| "Varfor finns ingen aktiv-checkbox?" | Anvandare ar alltid aktiva. Konton som inte ska vara kvar tas bort med `Ta bort`. |
| "Varfor kan jag inte ta bort anvandaren?" | Backend hindrar borttagning av eget konto och sista admin i en verksamhet. |
| "Varfor maste anvandaren skapa losenord?" | Kontot skapades/importerades utan losenord och har `must_change_password=true`. |
| "Varfor kan arbetsledare inte andra vissa bemanningsceller?" | Settingen `Las bemanningsceller som andra anvandare har fyllt i` ar troligen aktiv. |
| "Varfor ser jag inte Verksamheter?" | Vyn finns bara for Super User. Vanliga anvandare ska bara se sin egen verksamhet. |

## Kallor

- `../app/frontend/anvandare.html`
- `../app/frontend/js/users.js`
- `../app/frontend/js/businesses.js`
- `../app/frontend/js/common.js`
- `../app/backend/routers/users.py`
- `../app/backend/routers/businesses.py`
- `../app/backend/routers/settings.py`
- `../app/backend/settings_service.py`

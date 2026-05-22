---
title: Anvandare och installningar
status: aktiv
updated: 2026-05-22
tags: [anvandare, settings, roller, ui]
---

# Anvandare och installningar

Kort svar: Anvandare-sidan hanterar konton, roller, omrade, aktiv-status, forsta losenord, verksamhetsspecifik cell-lasning och rollernas vyatkomst. Super User har dessutom vyn Verksamheter dar verksamheter och deras omraden administreras.

Omradesfokus i sidebar filtrerar anvandarlistan inom anvandarens verksamhet. `∞` visar alla omraden i den verksamheten; for Super User betyder `∞` globalt allt. Nar en ny anvandare skapas forvalt valt omradesfokus som anvandarens omrade, men omradet kan fortfarande andras i modalen eller lamnas tomt.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Ny anvandare | Oppnar modal | Skapar konto | `POST /api/users` | Anvandarnamn och minst en roll kravs. |
| Flera nya anvandare | Oppnar tabellmodal | Skapar flera konton direkt i appen med samma falt som importmallen | `POST /api/users/import-rows` | Dubbletter, okanda roller och okanda omraden visas i resultatmodal. |
| Ladda ner importmall | Hamter Excelmall | Laddar ner mall | `GET /api/users/import-template` | Kräver `userImport` edit/super user enligt backend. |
| Importera Excel | Oppnar filval | Importerar anvandare | `POST /api/users/import` | Importerade utan losenord far `must_change_password=true`. |
| Vybehorigheter | Oppnar rollmatris | Sparar vyatkomst per verksamhet | `GET/PUT /api/settings/role-access` | Fel matris kan dolja vyer for roller i aktuell verksamhet. |
| Import-hjalp | Oppnar hjalpmodal | Visar importstod | `setupImportHelpButton` | Ingen serverkoppling. |
| Las bemanningsceller... | Checkbox | Sparar setting per verksamhet | `PUT /api/settings` | Nar aktiv kan ledare stoppas fran celler andra fyllt i aktuell verksamhet. |
| Visa inaktiva | Checkbox | Laddar anvandare med/utan inaktiva | `GET /api/users?include_inactive=` | Inaktiva visas inte utan checkbox. |
| Redigera | Oppnar modal | Uppdaterar konto | `PUT /api/users/{id}` | Sista admin kan inte nedgraderas/inaktiveras. |
| Aktivera/Inaktivera | Bekraftar | Satter `is_active` | `PUT /api/users/{id}` | Sista aktiva admin skyddas. |
| Verksamheter | Sidebar-vy for Super User | Skapar/redigerar verksamheter och omraden | `GET/POST/PUT /api/businesses`, `GET/POST/PUT/DELETE /api/areas` | Vanliga anvandare ser inte vyn. Omraden med kopplad data inaktiveras i stallet for att hardraderas. |

Andringar i anvandare, forsta losenord och verksamhetens installningar skrivs till Historik. Loggen visar till exempel `user/set_password`, `app_setting/update_lock`, `app_setting/update_sidebar_layout` och `app_setting/update_role_access`, men aldrig sjalva losenordet.

## Ny/redigera anvandare-modal

Falt:

- Anvandarnamn.
- Visningsnamn.
- Roller som checkboxar.
- Omrade.
- Verksamhet visas bara for Super User nar den inte kan harledas.
- Losenord.
- Aktiv.

Validering:

- Anvandarnamn kravs.
- Minst en roll kravs.
- Losenord, om ifyllt, maste vara minst 8 tecken.
- Super-user-rollandring skyddas av backendregler.
- Vanliga admins kan bara skapa/andra anvandare i sin egen verksamhet. Super User maste valja verksamhet eller ett omrade som harleder verksamheten.

Knappar:

- `Avbryt`: stanger utan att spara.
- `Spara`: skickar `POST` eller `PUT`.

## Vybehorigheter-modal

Rollmatrisen visar vyer som rader och roller som kolumner for aktuell verksamhet. Varje knapp cyklar:

`Ingen` -> `Visa` -> `Redigera` -> `Ingen`

Knappar:

- `Standard`: aterstaller modalens draft till defaultmatris.
- `Avbryt`: stanger utan att spara.
- `Spara`: skickar `PUT /api/settings/role-access`.

## Importregler

- Direktimporten `Flera nya anvandare` har samma falt som Excelmallen: anvandarnamn, visningsnamn, roller, omrade och vid behov verksamhet.
- Rollfaltet accepterar samma svenska rollnamn som Excelimporten. Flera roller kan separeras med komma.
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
| "Varfor syns inte en sida for en roll?" | Kontrollera `Vybehorigheter`; vyn kan sta pa `Ingen`. |
| "Varfor kan jag inte inaktivera anvandaren?" | Backend hindrar inaktivering/nedgradering av sista aktiva admin. |
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

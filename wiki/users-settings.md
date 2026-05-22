---
title: Anvandare och installningar
status: aktiv
updated: 2026-05-22
tags: [anvandare, settings, roller, ui]
---

# Anvandare och installningar

Kort svar: Anvandare-sidan hanterar konton, roller, omrade, aktiv-status, forsta losenord, global cell-lasning och rollernas vyatkomst.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Ny anvandare | Oppnar modal | Skapar konto | `POST /api/users` | Anvandarnamn och minst en roll kravs. |
| Ladda ner importmall | Hamter Excelmall | Laddar ner mall | `GET /api/users/import-template` | Kräver `userImport` edit/super user enligt backend. |
| Importera Excel | Oppnar filval | Importerar anvandare | `POST /api/users/import` | Importerade utan losenord far `must_change_password=true`. |
| Vybehorigheter | Oppnar rollmatris | Sparar global vyatkomst | `GET/PUT /api/settings/role-access` | Fel matris kan dolja vyer for roller. |
| Import-hjalp | Oppnar hjalpmodal | Visar importstod | `setupImportHelpButton` | Ingen serverkoppling. |
| Las bemanningsceller... | Checkbox | Sparar global setting | `PUT /api/settings` | Nar aktiv kan ledare stoppas fran celler andra fyllt. |
| Visa inaktiva | Checkbox | Laddar anvandare med/utan inaktiva | `GET /api/users?include_inactive=` | Inaktiva visas inte utan checkbox. |
| Redigera | Oppnar modal | Uppdaterar konto | `PUT /api/users/{id}` | Sista admin kan inte nedgraderas/inaktiveras. |
| Aktivera/Inaktivera | Bekraftar | Satter `is_active` | `PUT /api/users/{id}` | Sista aktiva admin skyddas. |

Andringar i anvandare, forsta losenord och globala installningar skrivs till Historik. Loggen visar till exempel `user/set_password`, `app_setting/update_lock`, `app_setting/update_sidebar_layout` och `app_setting/update_role_access`, men aldrig sjalva losenordet.

## Ny/redigera anvandare-modal

Falt:

- Anvandarnamn.
- Visningsnamn.
- Roller som checkboxar.
- Omrade.
- Losenord.
- Aktiv.

Validering:

- Anvandarnamn kravs.
- Minst en roll kravs.
- Losenord, om ifyllt, maste vara minst 8 tecken.
- Super-user-rollandring skyddas av backendregler.

Knappar:

- `Avbryt`: stanger utan att spara.
- `Spara`: skickar `POST` eller `PUT`.

## Vybehorigheter-modal

Rollmatrisen visar vyer som rader och roller som kolumner. Varje knapp cyklar:

`Ingen` -> `Visa` -> `Redigera` -> `Ingen`

Knappar:

- `Standard`: aterstaller modalens draft till defaultmatris.
- `Avbryt`: stanger utan att spara.
- `Spara`: skickar `PUT /api/settings/role-access`.

## Global menyeditor

Denna finns i sidebar, inte i `anvandare.html`, men hor till settings:

- Pennikonen oppnar "Redigera meny".
- Varje rad har flytta upp/ned, rubrik ovanfor och "Under" for undervy.
- `Standard` aterstaller defaultlayout.
- `Spara` skickar `PUT /api/settings/sidebar` och galler alla.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor syns inte en sida for en roll?" | Kontrollera `Vybehorigheter`; vyn kan sta pa `Ingen`. |
| "Varfor kan jag inte inaktivera anvandaren?" | Backend hindrar inaktivering/nedgradering av sista aktiva admin. |
| "Varfor maste anvandaren skapa losenord?" | Kontot skapades/importerades utan losenord och har `must_change_password=true`. |
| "Varfor kan arbetsledare inte andra vissa bemanningsceller?" | Settingen `Las bemanningsceller som andra anvandare har fyllt i` ar troligen aktiv. |

## Kallor

- `../app/frontend/anvandare.html`
- `../app/frontend/js/users.js`
- `../app/frontend/js/common.js`
- `../app/backend/routers/users.py`
- `../app/backend/routers/settings.py`
- `../app/backend/settings_service.py`

---
title: Historik och audit
status: aktiv
updated: 2026-05-25
tags: [historik, audit, ui]
---

# Historik och audit

Kort svar: Historik har tre lagen: anvandarhistorik, analys och felkoder. Den ar byggd for Super User och hjalper till att forklara vem som andrade vad, vilka handelser som ar vanligast och vilka API-/felkoder anvandare faktiskt traffar.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Vy-toggle | Valjer `Anvandarhistorik`, `Analys` eller `Felkoder` | Visar ratt panel utan sidbyte | `history-mode-btn`, `setHistoryMode` | Alla filter ovanfor galler for alla tre lagen. |
| Period | Valjer 24h, 7d, 30d, all | Raknar `start_at` for query | `periodStartIso`, `/api/audit*` | "All historik" kan bli tung om mycket data finns. |
| Anvandare | Filtrerar pa user | Skickar user-filter | `userFilter` | Listan laddas fran `/api/users`; anvandare som finns kvar ar alltid aktiva. |
| Typ | Filtrerar entity type | Skickar `entity_type` | `entityFilter` | Typnamn ar tekniska, t.ex. `schedule_cell`, `app_setting`, `productivity_file`, `allocation_flow`. |
| Atgard | Skriver action | Skickar action-filter | `actionFilter` | Exempel: `update`, `clear`, `drag_fill`. |
| Objekt-id | Skriver id | Skickar `entity_id` | `entityIdFilter` | Maste vara numeriskt. |
| Uppdatera | Klickar knapp | Hamter summary, rader och felkodsdashboard igen | `GET /api/audit/summary`, `GET /api/audit`, `GET /api/audit/errors` | Nekas om saknar Super User. |
| Enter i textfilter | Trycker Enter | Trigger refresh | `keydown` handlers | Change pa select refreshar direkt. |

## Vad som visas

- `Anvandarhistorik`: tabell med tid, anvandare, typ, atgard, objekt och detalj.
- `Analys`: statkort for antal handelser, senaste 24 h och unika anvandare samt topplistor for anvandare, atgarder och typer.
- `Felkoder`: statkort for felkoder, topplistor for felkod, vy/API och felatgard samt senaste felhandelser.
- Detalj byggs av old/new snapshots och forsoker oversatta person, aktivitet och omrade via lookups.
- Loggade floden omfattar nu register/schema, anvandare/forsta losenord, globala installningar, Hamta data, serverhanterade produktivitetsfiler och korda lagerverktygsfloden.
- Misslyckade filuppladdningar som hinner na backend loggas som `productivity_file/upload_failed`, `allocation_flow/upload_failed` eller `allocation_flow/detect_failed` med steg, feltyp, kort felmeddelande och eventuell HTTP-status.
- Bearbeta-fel som sker efter att flodet startat loggas som `allocation_flow/flow_failed` med `flow_id`, statuskod, felkod, feltyp, kort felmeddelande, tekniskt meddelande nar det skiljer sig, verksamhet, toggle och eventuella filterradantal. Filnamn och inskickade parametervarden sparas inte.
- API-fel som frontend far tillbaka fran backend rapporteras tyst som `client_error/client_error`. Payloaden sparar metod, path utan querystring, HTTP-status, felkod, kort meddelande och aktuell sida. Det galler aven Bearbetas egna fetch-wrapper. Request body, losenord, cookies, queryvarden och filnamn ska inte sparas.
- Dokument-loggen i sidebaren ar separat fran auditloggen och fylls klient-side av toastar, API-success/failure, bakgrundsvarningar och `window.flowLog`: success, info, warn och error. Den sparas i `sessionStorage`, foljer med vid sidbyte i samma browserflik och kan rensas av anvandaren; historiska/auditbara handelser finns i Historik.
- Auditpayloadar ska vara felsokningsbara men inte innehalla losenord, API-detaljer, sessionscookies eller privata filnamn.

## Tekniskt flode

- `GET /api/audit` listar radvis auditlogg for anvandarhistorik.
- `GET /api/audit/summary` summerar auditlogg for analyslagen.
- `GET /api/audit/errors` filtrerar auditlogg till felhandelser: `client_error` samt actions som innehaller `failed`, `error` eller `exception`.
- `POST /api/audit/client-error` tar emot klientrapporter fran `api.js`. Endpointen kraver inloggad anvandare men inte Super User, sa vanliga anvandares fel kan felsokas i efterhand.
- Frontendens `api.js` rapporterar 4xx/5xx och natverksfel fire-and-forget och exponerar `window.reportApiError` for sidmoduler med egna wrappers. Den hoppar over `/api/auth/me`, 401 och sjalva rapporteringsendpointen for att undvika brus och loopar.
- Samma `api.js` skriver anvandarnara dokumentlogg for mutationer, nedladdningar och markerade GET-floden. Sidmoduler som anvander egna wrappers, till exempel Bearbeta, ska logga success/failure sjalva eller anropa `window.flowLog`.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor kommer jag inte in pa Historik?" | Historik kraver super-user/vyatkomst till `analytics`. |
| "Varfor syns inte min andring?" | Kontrollera periodfilter och att flodet gar via backend. Lokala IndexedDB-handlingar som aldrig skickas till servern kan fortfarande sakna auditrad. |
| "Vad betyder Typ/Atgard?" | Typ ar databasenheten, atgard ar backendens audit-action. |
| "Varfor saknas anvandarnamn?" | Auditloggar kan ha `user_id=null` for system/seed eller gammal data. |
| "Varfor syns inte ett fel i Felkoder?" | Felkodsvyn visar klientrapporter och auditrader med fel-liknande action. Gamla fel innan klientrapporteringen fanns kan saknas om flodet inte skrev `*_failed`. |

## Kallor

- `../app/frontend/historik.html`
- `../app/frontend/js/api.js`
- `../app/frontend/js/analytics.js`
- `../app/backend/routers/audit_logs.py`
- `../app/backend/audit.py`

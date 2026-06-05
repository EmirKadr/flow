---
title: Historik och audit
status: aktiv
updated: 2026-06-04
tags: [historik, audit, ui]
---

# Historik och audit

Kort svar: Historik har nu auditlagen plus ett separat interaction-trackinglager. Super User kan se anvandarhistorik, analys, Funktioner, Knappar, Kolumner, Floden, AI-analys, felkoder, vantetider och Halsa for att forsta vilka funktioner som anvands, vilka knappar som aldrig anvands, hur resultatkolumner kopieras och vilka klick som leder till API, fel eller nedladdning.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Vy-toggle | Valjer `Anvandarhistorik`, `Analys`, `Funktioner`, `Knappar`, `Kolumner`, `Floden`, `AI-analys`, `Felkoder`, `Vantetider` eller `Halsa` | Visar ratt panel utan sidbyte | `history-mode-btn`, `setHistoryMode` | Period och anvandare galler aven tracking och vantetider. Halsa hamtas med kort cache. |
| Period | Valjer 24h, 7d, 30d, all | Raknar `start_at` for query | `periodStartIso`, `/api/audit*` | "All historik" kan bli tung om mycket data finns. |
| Verksamhet | Valjer Alla eller en verksamhet | Skickar `business_id` till audit-, felkods- och vantetidsendpoints och filtrerar anvandarlistan i klienten | `businessFilter`, `/api/businesses`, `business_id` | Galler inte Halsa-fliken, som visar global driftstatus. Systemrader utan verksamhet syns bara i Alla. |
| Anvandare | Filtrerar pa user | Skickar user-filter | `userFilter` | Listan laddas fran `/api/users` och smalnas av nar verksamhet valjs. |
| Typ | Filtrerar entity type | Skickar `entity_type` | `entityFilter` | Typnamn ar tekniska, t.ex. `schedule_cell`, `app_setting`, `productivity_file`, `allocation_flow`. |
| Atgard | Skriver action | Skickar action-filter | `actionFilter` | Exempel: `update`, `clear`, `drag_fill`. |
| Objekt-id | Skriver id | Skickar `entity_id` | `entityIdFilter` | Maste vara numeriskt. |
| Uppdatera | Klickar knapp | Hamter summary, rader och felkodsdashboard igen | `GET /api/audit/summary`, `GET /api/audit`, `GET /api/audit/errors` | Nekas om saknar Super User. |
| Enter i textfilter | Trycker Enter | Trigger refresh | `keydown` handlers | Change pa select refreshar direkt. |
| Historik-AI | Skriver en fraga om tracking | Skickar filtrerad historik, aggregeringar och raw events inom limit till MiniMax | `POST /api/audit/interactions/chat` | Svarar bara pa fragor om historik/tracking och vagrar hemligheter eller blockerade falt. |
| Rensa AI | Klickar Rensa i AI-analys | Rensar aktuell chattvy | `POST /api/audit/interactions/chat/clear` | Sparar ingen separat chatthistorik. |

## Vad som visas

- `Anvandarhistorik`: tabell med tid, anvandare, typ, atgard, objekt och detalj.
- `Analys`: statkort for antal handelser, senaste 24 h och unika anvandare samt topplistor for anvandare, atgarder och typer.
- `Funktioner`: interaction-summary for mest anvanda funktioner, vyer och klientytor samt coverage for kanda knappar som inte anvants i urvalet. Coverage-kontraktet anvander frontendens faktiska kontroll-id:n sa gamla alias inte smyger in igen.
- `Knappar`: topplista for kontroller och senaste trackingevents med vy, eventtyp, kontroll och status.
- `Kolumner`: copy/export/download-monster och kolumnkopiering per flow, resultattabell, kolumnindex och kolumnnamn. Copy-monster anvander `detail.copy_mode` nar det finns, sa auto-copy av forsta kolumnen kan skiljas fran manuell/multikolumn-kopiering.
- `Floden`: flow-anvandning och vilka resultatkolumner som kopieras per flow. Pa `pafyllnadsprio` gar det att se om anvandaren bara kopierar forsta kolumnen via auto-copy eller manuellt kopierar flera kolumner i samma resultat/session.
- `AI-analys`: MiniMax-fragor om trackinghistorik, till exempel "Vilka funktioner anvands minst?", "Kopierar folk forsta kolumnen i Pafyllnadsprio eller flera?" och "Vilka vyer anvands i Windows men inte webben?".
- `Felkoder`: statkort for felkoder, topplistor for felkod, vy/API och felatgard samt senaste felhandelser.
- `Vantetider`: p50/p95/max for vyload, API-anrop, nedladdningar och bakgrundsladdning, sa flaskhalsar syns utan manuell magkansla.
- `Halsa`: app-, databas- och Render-status for lokal/serverdrift; samma signal anvands av `tools.healthcheck` och kan lasa Render build-loggar nar API-nyckel, service-id och ownerId finns.
- Detalj byggs av old/new snapshots och forsoker oversatta person, aktivitet och omrade via lookups.
- Loggade floden omfattar nu register/schema, anvandare/forsta losenord, globala installningar, Hamta data, serverhanterade produktivitetsfiler och korda lagerverktygsfloden.
- Misslyckade filuppladdningar som hinner na backend loggas som `productivity_file/upload_failed`, `allocation_flow/upload_failed` eller `allocation_flow/detect_failed` med steg, feltyp, kort felmeddelande och eventuell HTTP-status.
- Misslyckade publika Meta-uppladdningar som hinner na backend loggas som `meta_media_upload/upload_failed` utan inloggad anvandare. Felkoder visar dem som systemhandelser med path `/api/meta/uploads`, HTTP-status, feltyp, antal filer och total uppladdad storlek, men utan filnamn eller filinnehall.
- Bearbeta-fel som sker efter att flodet startat loggas som `allocation_flow/flow_failed` med `flow_id`, statuskod, felkod, feltyp, kort felmeddelande, tekniskt meddelande nar det skiljer sig, verksamhet, toggle och eventuella filterradantal. Filnamn och inskickade parametervarden sparas inte.
- Windows-lokala Bearbeta-/Produktivitet-korningar loggas som `desktop_local_run` via `/api/audit/local-run`. Payloaden innehaller feature, flode, status, feltyp, varaktighet, filslotar och rad-/resultatraknare, men aldrig lokal sokvag, localRef, filnamn eller filinnehall.
- API-fel som frontend far tillbaka fran backend rapporteras tyst som `client_error/client_error`. Payloaden sparar metod, path utan querystring, HTTP-status, felkod, kort meddelande och aktuell sida. Om server/proxy skickar en HTML-felsida sanerar `api.js` detaljen till kort status, t.ex. `HTML-felsida fran servern: HTTP 502 (Bad Gateway)`, i stallet for att spara HTML. Det galler aven Bearbetas egna fetch-wrapper. Request body, losenord, cookies, queryvarden och filnamn ska inte sparas.
- Sidoppningar rapporteras tyst som `view/open` via `/api/audit/client-event`. De syns i Historik, men ska inte fylla dokumentloggen.
- Dokument-loggen i sidebaren ar separat fran auditloggen och fylls klient-side av funktioner, toastar, API-success/failure, bakgrundsvarningar och `window.flowLog`: success, info, warn och error. Den sparas i `sessionStorage`, foljer med vid sidbyte i samma browserflik och kan rensas av anvandaren; vanliga sidbyten filtreras bort. Bakgrundsladdning dolder likadana fel i 60 sekunder efter forsta warn-raden for att undvika spam vid serverfel. Ikonen visar bara en kort pil- och bubbelsignal nar en ny rad skrivs, inte en sparad olast-raknare.
- Audit- och trackingpayloadar ska vara felsokningsbara men inte innehalla losenord, API-detaljer, sessionscookies, privata URL:er, filnamn, filvagar, request bodies eller provider-detaljer.
- Smal tracking-exception: klartext-vardeprov far bara sparas for uttryckligt trackade anvandarinteraktioner och bara nar `TRACKING_ALLOW_VALUE_SAMPLES=true`. Default ar false och backend ersatter da prover med langd/antal. Undantaget galler aldrig losenord, cookies, tokens, API-nycklar, privata URL:er, filnamn, filvagar, request bodies eller provider-detaljer.
- Efter storre push/deploy ska agenter anvanda `tools.healthcheck report` och
  `tools.healthcheck waits` som driftgrind. Tydliga `warn`/`error` ska fixas
  eller rapporteras med kommando, tidpunkt och feltext.

## Tekniskt flode

- `GET /api/audit` listar radvis auditlogg for anvandarhistorik.
- `GET /api/audit/summary` summerar auditlogg for analyslagen.
- `GET /api/audit/errors` filtrerar auditlogg till felhandelser: `client_error` samt actions som innehaller `failed`, `error` eller `exception`.
- Audit-endpoints accepterar `business_id` for Super User. Frontend hamtar verksamheter fran `/api/businesses?include_inactive=true` och skickar samma filter till anvandarhistorik, analys och felkoder.
- `POST /api/audit/client-error` tar emot klientrapporter fran `api.js`. Endpointen kraver inloggad anvandare men inte Super User, sa vanliga anvandares fel kan felsokas i efterhand.
- `POST /api/audit/client-event` tar emot tysta klienthandelser som `view_open` och sparar dem som `view/open` utan queryvarden.
- `POST /api/audit/local-run` tar emot sanerad metadata fran Windows desktop-servern for lokala Bearbeta-/Produktivitet-korningar.
- `POST /api/audit/interactions` tar emot batchade inloggade interaction-events fran `common.js`, `api.js` och sidmoduler. Rows sparas i `user_interaction_events` med index for tid, verksamhet, anvandare, vy, eventtyp, kontroll, feature, flow, tabell och kolumn.
- `POST /api/audit/interactions/public` tar bara emot allowlistade publika Meta-events utan anvandare/verksamhet. Klienten skickar antal, storlek och media-typ men aldrig filnamn.
- `GET /api/audit/interactions`, `/summary` och `/coverage` driver de nya trackingpanelerna i Historik.
- `POST /api/audit/interactions/chat` bygger en sanerad MiniMax-kontext av aggregeringar och raw events inom query-limit. Den far anvanda raw trackingevents men systemprompten forbjuder fragor om hemligheter, provider-detaljer, filnamn, filvagar och request bodies.
- `POST /api/audit/interactions/chat/clear` rensar chattvyn.
- `GET /api/healthcheck` visar Halsa-fliken med app-, databas- och Render-status for Super User.
- `POST /api/healthcheck/wait-metrics` samlar tysta vantetidsmatningar fran klienten utan att skriva i dokumentloggen.
- `GET /api/healthcheck/wait-metrics/summary` driver Vantetider-fliken och CLI-analys for var anvandare vantar mest. Historik skickar valt `business_id` hit, men `GET /api/healthcheck` for Halsa forblir global.
- Frontendens `api.js` rapporterar 4xx/5xx och natverksfel fire-and-forget och exponerar `window.reportApiError` for sidmoduler med egna wrappers. Den hoppar over `/api/auth/me`, 401 och sjalva rapporteringsendpointen for att undvika brus och loopar. Icke-JSON/HTML-felsidor visas som kort HTTP-status och lagras inte som raw HTML.
- Samma `api.js` skriver anvandarnara dokumentlogg for mutationer, nedladdningar och markerade GET-floden. Den interna, dolda download-lanken markeras med `data-track-ignore` sa exporttracking kopplas till anvandarens riktiga knappklick. Sidmoduler som anvander egna wrappers, till exempel Bearbeta, ska logga success/failure sjalva eller anropa `window.flowLog`.
- `common.js` exponerar `window.flowTrack` och auto-capturar klick, submit, change, contextmenu, sidebar, tema, zoom, apphjalp, loggpanel och modaler. `api.js` kopplar API-resultat till senaste interaction-id sa dashboards kan visa vilka knappar som leder till API, fel, vantan och nedladdning.
- Windows-appen anvander samma frontendtracking via QWebEngine och markerar `client_surface=desktop`. Desktop-bryggan trackar appstart, lokala filval och uppdateringsfloden med sanerad metadata.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor kommer jag inte in pa Historik?" | Historik kraver super-user/vyatkomst till `analytics`. |
| "Varfor syns inte min andring?" | Kontrollera periodfilter och att flodet gar via backend. Lokala IndexedDB-handlingar som aldrig skickas till servern kan fortfarande sakna auditrad. |
| "Varfor forsvinner systemrader nar jag valjer verksamhet?" | Vissa gamla/systemskapade auditrader saknar `business_id`. De visas i Alla men inte nar du filtrerar pa en specifik verksamhet. |
| "Vad betyder Typ/Atgard?" | Typ ar databasenheten, atgard ar backendens audit-action. |
| "Varfor saknas anvandarnamn?" | Auditloggar kan ha `user_id=null` for system/seed eller gammal data. |
| "Varfor syns inte ett fel i Felkoder?" | Felkodsvyn visar klientrapporter och auditrader med fel-liknande action. Gamla fel innan klientrapporteringen fanns kan saknas om flodet inte skrev `*_failed`. Om felet stoppas av proxy/natverk innan backend tar emot requesten kan servern inte skriva auditrad. |

## Kallor

- `../app/frontend/historik.html`
- `../app/frontend/js/api.js`
- `../app/frontend/js/common.js`
- `../app/frontend/js/analytics.js`
- `../app/frontend/js/allocation_tools.js`
- `../app/frontend/js/desktop_bridge.js`
- `../app/backend/routers/audit_logs.py`
- `../app/backend/models.py`
- `../app/alembic/versions/0032_user_interaction_events.py`
- `../app/backend/routers/healthcheck.py`
- `../app/backend/audit.py`
- `../desktop/app.py`
- `../tools/healthcheck.py`

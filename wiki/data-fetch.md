---
title: Hämta data
status: aktiv
updated: 2026-06-08
tags: [datahamtning, extern-data, minimax, api]
---

# Hämta data

Kort svar: Hämta data är en skyddad vy där en användare beskriver på svenska
vilken extern datavy som ska hämtas, vilka kolumner som ska visas och vilka
filter som ska användas. MiniMax får bara en publicerbar vy-/kolumnkatalog. URL:er,
API-nycklar, headernamn, endpointmallar och klientnycklar ligger i
miljövariabler och skickas aldrig till modellen.

## Användarflöde

1. Användaren öppnar `hamta-data.html`.
2. Användaren skriver en prompt, till exempel vilken vy, kolumner och filter som önskas.
3. `Tolka` skickar prompten och ett begränsat katalogutdrag till MiniMax.
4. Backend validerar MiniMax-planen mot katalogen.
5. Användaren ser vald vy, tekniska kolumner och filter.
6. Användaren kan klicka bort utdataplanens kolumner och trycka `Uppdatera plan`.
7. Användaren kan fylla `Max rader` för att begränsa resultatet, eller lämna fältet tomt för att ta med alla hämtade rader.
8. `Hämta data` kör API-anropet från backend.
9. Resultatet visas som tabell och kan exporteras till Excel.

## Knappar och kontroller

| Kontroll | Var | Vem får | Vad händer | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- | --- |
| Hämta data | Sidebar | Super User eller roll med vyåtkomst `dataFetch` | Öppnar datahämtningsvyn | `common.js`, `hamta-data.html` | Om vyn saknas: kontrollera Vybehörigheter. |
| Tolka | Promptpanelen | `dataFetch` view | Skickar prompt + katalogutdrag till MiniMax och visar validerad plan | `POST /api/query-data/plan` | Fel om `MINIMAX_API_KEY` saknas eller modellen väljer okänd vy/kolumn. |
| Max rader | Promptpanelen | `dataFetch` view | Valfritt tal som begränsar tabell och Excel-export. Tomt fält betyder alla hämtade rader. | `data_fetch.js`, `POST /api/query-data/run` | Ogiltiga eller för stora tal normaliseras innan körning. |
| Kolumnchip | Planpanelen | `dataFetch` view | Markerar kolumn för borttagning ur `output_columns` | `data_fetch.js` | Minst en kolumn måste vara kvar. |
| Uppdatera plan | Planpanelen | `dataFetch` view | Skriver om planen lokalt med kvarvarande kolumner och rensar gammalt resultat | `data_fetch.js` | Knappen är spärrad tills minst en kolumn markerats. |
| Hämta data | Promptpanelen | `dataFetch` view | Kör validerad plan mot extern datakälla | `POST /api/query-data/run` | Fel om `DATA_SOURCE_API_BASE_URL`, `DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE` eller nyckel-/header-env saknas/fel. |
| Exportera Excel | Resultatpanelen | `dataFetch` view | Laddar ner senaste begränsade resultat som `.xlsx` | `GET /api/query-data/export/{session_id}` | Fel om resultatet har gått förlorat och hämtningen måste köras igen. |

## Säkerhetsmodell

- Hemliga anslutningsvärden ligger i serverns miljövariabler med generiska `DATA_SOURCE_*`-namn.
- Endpointmall och headernamn ligger också i miljövariabler, så repot inte dokumenterar leverantörens privata API-kontrakt.
- Katalogen med vyer och kolumner ska finnas uppladdad i servermiljön och läses automatiskt från `data/external_data_catalog.json`, `DATA_SOURCE_CATALOG_JSON` eller `DATA_SOURCE_CATALOG_PATH`.
- MiniMax-prompten byggs av `data_fetch_service.py` och innehåller bara användarens prompt, appens aktuella `current_date`/`current_datetime`, tillåtna operatorer, kandidatvyer, kolumn-id:n och kolumnnamn.
- MiniMax får inte URL, endpoint-bas, headernamn, API-token, sessioncookie eller databasinfo.
- Backend validerar alltid att vald vy och alla filter-/utdatakolumner finns i katalogen innan API-anropet körs.
- Om prompten innehåller månad + år, `idag`, `dagens` eller `senaste N dagarna`, skickas en periodhint till MiniMax och backend reparerar uppenbara misstolkningar där perioden hamnat i fel fält eller fått fel datum.
- `GET /api/query-data/health` använder inte MiniMax. Om katalog, API-env eller
  MiniMax-nyckel saknas rapporterar den status till UI:t så `Tolka`
  och `Hämta data` kan spärras innan någon AI-fråga eller extern API-fråga skickas.
- Om extern datahämtning misslyckas loggar backend `error_id`, vy och filterstruktur
  i serverloggen utan URL:er eller hemligheter. Frontend visar samma fel-id i
  Hämta data-panelen så felet går att hitta i Render-loggarna.

## Teknisk modell

- `tools/build_external_data_catalog.py` bygger katalogen från lokala Excel-filer.
- `.gitignore` ignorerar `private-data/` och lokala katalogvarianter som `data/external_data_catalog.local*.json`; standardkatalogen `data/external_data_catalog.json` commitas.
- `app/backend/external_data_client.py` är en generisk fetch-klient där provider-specifika detaljer kommer från env. Den skickar JSON-payload, förväntar JSON-svar och kan styras med `DATA_SOURCE_VERIFY_SSL`/`DATA_SOURCE_CA_BUNDLE` för lokala certifikatkedjor.
- `app/backend/data_fetch_service.py` laddar katalog, bygger MiniMax-prompt, lägger till appklocka/periodhints, normaliserar koder som `company=GG` och validerar plan.
- `app/frontend/js/data_fetch.js` låter användaren ta bort kolumner ur MiniMax-planens `output_columns` innan `/api/query-data/run` körs. Servern validerar fortfarande den inskickade planen vid hämtning.
- `app/backend/routers/data_fetch.py` kör planering, datahämtning och Excel-export.
- `max_rows` i `/api/query-data/run` är valfritt. `null` eller utelämnat värde betyder att backend inte beskär raderna efter fetch; ett ifyllt tal begränsas fortfarande av serverns maxinställning.
- Resultatens export-rader skrivs till temporara serverfiler per `session_id` med TTL, maxantal och byte-budget. Sessionens RAM-del haller bara anvandarkoppling, plan, kolumner, radantal och filreferens; Excel-exporten laser filen vid behov.
- `app/backend/workflow_data.py` ateranvander `ExternalDataClient` for Bearbeta och Produktivitet, men utan MiniMax-plan, utan prompt och utan radbegransning. Den hamtar en bestamd katalogvy, materialiserar raderna till temporar tabbseparerad CSV och later workflowt avgora behorighet/fallback. Det ar inte samma anvandarflode som Hamta data och kraver inte `dataFetch`.

## Felsökningssvar för framtida chat

Fråga: Varför ser jag inte Hämta data?
Svar: Vyn kräver Super User eller vyåtkomst till `dataFetch`. Be admin/Super User kontrollera Vybehörigheter.

Fråga: Får MiniMax se API-länken?
Svar: Nej. Backend skickar bara vy-/kolumnstruktur och JSON-formatet som modellen ska returnera. URL, endpointmall, headernamn och nycklar läses från serverns miljövariabler när API-anropet körs.

Fråga: Varför säger den att katalog saknas?
Svar: Servern hittar inte `data/external_data_catalog.json` och har inte `DATA_SOURCE_CATALOG_JSON`. Kontrollera att katalogfilen är committad/deployad eller bygg den lokalt med `python tools/build_external_data_catalog.py --views <views.xlsx> --columns <columns.xlsx>`. Detta fel skapar ingen MiniMax-usage.

Fråga: Varför går det inte att klicka på Tolka?
Svar: Knappen spärras när katalogen saknas eller när `MINIMAX_API_KEY` inte är satt. Då skickas ingen AI-fråga och ingen MiniMax-usage skapas.

Fråga: Varför går det inte att klicka på Hämta data?
Svar: Knappen kräver en godkänd plan från `Tolka` och att den externa datakällan är konfigurerad med alla obligatoriska `DATA_SOURCE_*`-värden i servermiljön: bas-URL, API-nyckel, klientvärde, headernamn för nyckel/klient och endpointmall. Health-raden visar exakt vilka variabelnamn som saknas.

Fråga: Hur hämtar jag alla rader?
Svar: Lämna `Max rader` tomt och klicka `Hämta data`. Då skickas inget radtak till backend, så tabellen och Excel-exporten innehåller alla rader som den externa datakällan returnerar.

Fråga: Hur tar jag bort kolumner från resultatet?
Svar: Klicka på kolumnchippen i planpanelen och tryck `Uppdatera plan`. Då tas kolumnerna bort från `output_columns`, gammalt resultat rensas och nästa `Hämta data` använder den uppdaterade planen. Det går inte att ta bort alla kolumner.

Fråga: Varför fick jag HTTP 500/502 när planen såg rätt ut?
Svar: Planen kan vara korrekt men externa datakällan kan ändå neka, stänga anslutningen, vara nere eller svara med fel. Vid sådana fel visar Hämta data ett fel-id. Leta på samma fel-id i Render-loggarna för att se vilken vy som kördes och om felet var nätåtkomst, endpointmall, SSL-verifiering eller HTTP-status från datakällan.

Fråga: Varför blev `april 2026` ett ordernummerfilter?
Svar: Hämta data försöker nu känna igen svensk månad + år, `idag`, `dagens` och `senaste N dagarna` innan MiniMax-anropet. För loggvyer ska perioden användas på bästa datumkolumn, till exempel `time_stamp_int` i plockloggen eller `timestamp` i transloggen. Om modellen ändå lägger perioden i `order_num` eller hittar på fel datum reparerar backend filtret innan anropet körs.

Fråga: Varför stoppas en MiniMax-plan?
Svar: Backend accepterar bara vyer, kolumner och filteroperatorer som finns i katalogen. Om modellen hittar på något stoppas körningen innan extern datakälla anropas.

## Källor

- `../app/frontend/hamta-data.html`
- `../app/frontend/js/data_fetch.js`
- `../app/backend/routers/data_fetch.py`
- `../app/backend/data_fetch_service.py`
- `../app/backend/external_data_client.py`
- `../app/backend/workflow_data.py`
- `../tools/build_external_data_catalog.py`

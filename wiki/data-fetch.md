---
title: Hämta data
status: aktiv
updated: 2026-05-21
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
3. `Tolka med MiniMax` skickar prompten och ett begränsat katalogutdrag till MiniMax.
4. Backend validerar MiniMax-planen mot katalogen.
5. Användaren ser vald vy, tekniska kolumner och filter.
6. `Hämta data` kör API-anropet från backend.
7. Resultatet visas som tabell och kan exporteras till Excel.

## Knappar och kontroller

| Kontroll | Var | Vem får | Vad händer | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- | --- |
| Hämta data | Sidebar | Super User eller roll med vyåtkomst `dataFetch` | Öppnar datahämtningsvyn | `common.js`, `hamta-data.html` | Om vyn saknas: kontrollera Vybehörigheter. |
| Läs om katalog | Vyns topp | `dataFetch` edit | Rensar backendens katalogcache och läser katalogen igen | `POST /api/query-data/catalog/reload` | Fel om katalogfil/env saknas. |
| Tolka med MiniMax | Promptpanelen | `dataFetch` view | Skickar prompt + katalogutdrag till MiniMax och visar validerad plan | `POST /api/query-data/plan` | Fel om `MINIMAX_API_KEY` saknas eller modellen väljer okänd vy/kolumn. |
| Hämta data | Promptpanelen | `dataFetch` view | Kör validerad plan mot extern datakälla | `POST /api/query-data/run` | Fel om `DATA_SOURCE_API_BASE_URL`, `DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE` eller nyckel-/header-env saknas/fel. |
| Exportera Excel | Resultatpanelen | `dataFetch` view | Laddar ner senaste begränsade resultat som `.xlsx` | `GET /api/query-data/export/{session_id}` | Fel om resultatet har gått förlorat och hämtningen måste köras igen. |

## Säkerhetsmodell

- Hemliga anslutningsvärden ligger i serverns miljövariabler med generiska `DATA_SOURCE_*`-namn.
- Endpointmall och headernamn ligger också i miljövariabler, så repot inte dokumenterar leverantörens privata API-kontrakt.
- Katalogen med vyer och kolumner läses normalt från den committade filen `data/external_data_catalog.json`. Drift kan även override:a med `DATA_SOURCE_CATALOG_JSON` eller `DATA_SOURCE_CATALOG_PATH`.
- MiniMax-prompten byggs av `data_fetch_service.py` och innehåller bara användarens prompt, tillåtna operatorer, kandidatvyer, kolumn-id:n och kolumnnamn.
- MiniMax får inte URL, endpoint-bas, headernamn, API-token, sessioncookie eller databasinfo.
- Backend validerar alltid att vald vy och alla filter-/utdatakolumner finns i katalogen innan API-anropet körs.
- `GET /api/query-data/health` använder inte MiniMax. Om katalog, API-env eller
  MiniMax-nyckel saknas rapporterar den status till UI:t så `Tolka med MiniMax`
  och `Hämta data` kan spärras innan någon AI-fråga eller extern API-fråga skickas.

## Teknisk modell

- `tools/build_external_data_catalog.py` bygger katalogen från lokala Excel-filer.
- `.gitignore` ignorerar `private-data/` och lokala katalogvarianter som `data/external_data_catalog.local*.json`; standardkatalogen `data/external_data_catalog.json` commitas.
- `app/backend/external_data_client.py` är en generisk fetch-klient där provider-specifika detaljer kommer från env.
- `app/backend/data_fetch_service.py` laddar katalog, bygger MiniMax-prompt och validerar plan.
- `app/backend/routers/data_fetch.py` kör planering, datahämtning och Excel-export.
- Resultat hålls i minne per `session_id`, på samma sätt som lagerverktygens exportflöden.

## Felsökningssvar för framtida chat

Fråga: Varför ser jag inte Hämta data?
Svar: Vyn kräver Super User eller vyåtkomst till `dataFetch`. Be admin/Super User kontrollera Vybehörigheter.

Fråga: Får MiniMax se API-länken?
Svar: Nej. Backend skickar bara vy-/kolumnstruktur och JSON-formatet som modellen ska returnera. URL, endpointmall, headernamn och nycklar läses från serverns miljövariabler när API-anropet körs.

Fråga: Varför säger den att katalog saknas?
Svar: Servern hittar inte `data/external_data_catalog.json` och har inte `DATA_SOURCE_CATALOG_JSON`. Kontrollera att katalogfilen är committad/deployad eller bygg den lokalt med `python tools/build_external_data_catalog.py --views <views.xlsx> --columns <columns.xlsx>`. Detta fel skapar ingen MiniMax-usage.

Fråga: Varför går det inte att klicka på Tolka med MiniMax?
Svar: Knappen spärras när katalogen saknas eller när `MINIMAX_API_KEY` inte är satt. Då skickas ingen AI-fråga och ingen MiniMax-usage skapas.

Fråga: Varför går det inte att klicka på Hämta data?
Svar: Knappen kräver en godkänd plan och att den externa datakällan är konfigurerad med alla obligatoriska `DATA_SOURCE_*`-värden i servermiljön: bas-URL, API-nyckel, klientvärde, headernamn för nyckel/klient och endpointmall. Health-raden visar exakt vilka variabelnamn som saknas.

Fråga: Varför stoppas en MiniMax-plan?
Svar: Backend accepterar bara vyer, kolumner och filteroperatorer som finns i katalogen. Om modellen hittar på något stoppas körningen innan extern datakälla anropas.

## Källor

- `../app/frontend/hamta-data.html`
- `../app/frontend/js/data_fetch.js`
- `../app/backend/routers/data_fetch.py`
- `../app/backend/data_fetch_service.py`
- `../app/backend/external_data_client.py`
- `../tools/build_external_data_catalog.py`

---
title: Hämta data
status: aktiv
updated: 2026-06-15
tags: [datahamtning, extern-data, minimax, api]
---

# Hämta data

Kort svar: Hämta data är en skyddad vy där en användare beskriver på svenska
vilken extern datavy som ska hämtas, vilka kolumner som ska visas, vilka filter
som ska användas och eventuell beräkning som ska köras. MiniMax får bara en
publicerbar vy-/kolumnkatalog och ett strikt JSON-format. URL:er, API-nycklar,
headernamn, endpointmallar och klientnycklar ligger i miljövariabler och skickas
aldrig till modellen.

> Hur långt bak en `v_ask_*`-vy ger träffar styrs av ASK/WMan:s rensnings- och
> arkiveringsjobb. Se [ASK datalagring](ask-datalagring.md) innan du lovar
> historik bakåt i tiden.

## Användarflöde

1. Användaren öppnar `hamta-data.html`.
2. Användaren skriver en prompt, till exempel vilken vy, kolumner och filter som önskas.
3. `Tolka` skickar prompten och ett begränsat katalogutdrag till MiniMax.
4. Backend validerar MiniMax-planen mot katalogen.
5. Användaren ser vald vy, tekniska kolumner, filter och eventuell beräkning.
6. Användaren kan klicka bort utdataplanens kolumner och trycka `Uppdatera plan`.
7. Användaren kan fylla `Max rader` för att begränsa resultatet, eller lämna fältet tomt för att ta med alla hämtade rader.
8. `Hämta data` kör API-anropet från backend. Om en verksamhet är vald via områdesfokus skickar klienten `business_id` så backend kan använda verksamhetens `tenant`.
9. Resultatet visas som tabell med eventuell beräkningsruta och kan exporteras till Excel.

## Knappar och kontroller

| Kontroll | Var | Vem får | Vad händer | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- | --- |
| Hämta data | Sidebar | Super User eller roll med vyåtkomst `dataFetch` | Öppnar datahämtningsvyn | `common.js`, `hamta-data.html` | Om vyn saknas: kontrollera Vybehörigheter. |
| Tolka | Promptpanelen | `dataFetch` view | Skickar prompt + katalogutdrag till MiniMax och visar validerad plan | `POST /api/query-data/plan` | Fel om `MINIMAX_API_KEY` saknas eller modellen väljer okänd vy/kolumn. |
| Max rader | Promptpanelen | `dataFetch` view | Valfritt tal som begränsar tabell och Excel-export. Tomt fält betyder alla hämtade rader. | `data_fetch.js`, `POST /api/query-data/run` | Ogiltiga eller för stora tal normaliseras innan körning. |
| Kolumnchip | Planpanelen | `dataFetch` view | Markerar kolumn för borttagning ur `output_columns` | `data_fetch.js` | Minst en kolumn måste vara kvar. |
| Uppdatera plan | Planpanelen | `dataFetch` view | Skriver om planen lokalt med kvarvarande kolumner och rensar gammalt resultat | `data_fetch.js` | Knappen är spärrad tills minst en kolumn markerats. |
| Hämta data | Promptpanelen | `dataFetch` view | Kör validerad plan mot extern datakälla, applicerar lokala exkluderingar/textfilter och beräknar eventuell `calculation` lokalt på raderna | `POST /api/query-data/run` | Fel om `DATA_SOURCE_API_BASE_URL`, `DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE` eller nyckel-/header-env saknas/fel. |
| Exportera Excel | Resultatpanelen | `dataFetch` view | Laddar ner senaste begränsade resultat som `.xlsx` | `GET /api/query-data/export/{session_id}` | Fel om resultatet har gått förlorat och hämtningen måste köras igen. |
| Resultatrubriker | Resultattabellen | `dataFetch` view | Sorterar de synliga resultatraderna stigande/fallande klient-side | `common.js` klienttabellsortering | Skickar inte ny fråga och påverkar inte Excel-exportens serverurval. |

## Säkerhetsmodell

- Hemliga anslutningsvärden ligger i serverns miljövariabler med generiska `DATA_SOURCE_*`-namn.
- Verksamhetens `tenant` styr bara backendens val av extern API-bas. `DATA_SOURCE_API_BASE_URL` kan innehålla `{tenant}` eller ett tenantled i hostens första bindestrecksdel; om verksamheten saknar tenant används bas-URL:n oförändrad.
- Endpointmall och headernamn ligger också i miljövariabler, så repot inte dokumenterar leverantörens privata API-kontrakt.
- Katalogen med vyer och kolumner ska finnas uppladdad i servermiljön och läses automatiskt från `data/external_data_catalog.json`, `DATA_SOURCE_CATALOG_JSON` eller `DATA_SOURCE_CATALOG_PATH`.
- MiniMax-prompten byggs av `data_fetch_service.py` och innehåller bara användarens prompt, appens aktuella `current_date`/`current_datetime`, tillåtna operatorer, kandidatvyer, kolumn-id:n och kolumnnamn.
- MiniMax får inte URL, endpoint-bas, headernamn, API-token, sessioncookie eller databasinfo.
- Backend validerar alltid att vald vy och alla filter-/utdata-/beräkningskolumner finns i katalogen innan API-anropet körs.
- Exkluderande `NE`-filter, numeriska jämförelser som `GT`/`GTE`/`LT`/`LTE` och textfilter som `StartsWith`, `EndsWith`, `Contains` och `Like` är tillåtna i planen men skickas inte vidare som riskabla/okända operatorer till externa API:t. Backend hämtar med stabila urvalsfilter och filtrerar sedan raderna lokalt, till exempel `type <> 45` för "exkludera typ 45", `qty_suf >= 1` för "plockat minst 1" och `order_num LIKE 'TO%'` för "börjar på TO".
- MiniMax får inte skriva fri SQL som körs. Modellen returnerar i stället en `calculation` med tillåtna operationer: `count`, `count_distinct`, `sum`, `avg`, `min`, `max`, valfri `group_by`, `sort_by` och `limit`. Backend kör beräkningen lokalt på API-raderna och genererar bara en läsbar SQL/querytext från den validerade planen.
- `identifiers` betyder konkreta API-identifierarvärden och används inte för dubletter. Om modellen ändå returnerar en ren kolumnlista i `identifiers` tolkar backend den säkert som `count_distinct.distinct_by` i stället för att skicka den till externa API:t.
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
- `app/backend/external_data_client.py` är en generisk fetch-klient där provider-specifika detaljer kommer från env. Den skickar JSON-payload, förväntar JSON-svar, kan bygga tenant-specifik bas-URL från `Business.tenant` och kan styras med `DATA_SOURCE_VERIFY_SSL`/`DATA_SOURCE_CA_BUNDLE` för lokala certifikatkedjor.
- `app/backend/data_fetch_service.py` laddar katalog, bygger MiniMax-prompt, lägger till appklocka/periodhints, normaliserar koder som `company=GG`, validerar plan, delar upp externa/lokala filter och kör whitelistade beräkningar ovanpå hämtade rader.
- `data_fetch_service.build_retention_segments` läser planens Between-datumfilter och avgör, via tabellen `LIVE_ARCHIVE_PAIRS` (live-vy → retention-dagar → `dblog_*`-arkivvy), om hämtningen ska gå mot live-vyn, arkivvyn eller båda. Routern (`_apply_retention` + `_fetch_rows_with_segments`) sätter `plan.notice`/`plan.fetched_views` och slår ihop raderna före projektion och beräkning. Arkivsegmentets filter mappas om till arkivvyns datumkolumn och behåller bara filter vars kolumn finns i målvyn. Se [ASK datalagring](ask-datalagring.md).
- `app/frontend/js/data_fetch.js` låter användaren ta bort kolumner ur MiniMax-planens `output_columns` innan `/api/query-data/run` körs. Servern validerar fortfarande den inskickade planen vid hämtning. `plan.notice` visas som en gul notisruta i planpanelen.
- `app/backend/routers/data_fetch.py` kör planering, datahämtning och Excel-export. `/api/query-data/run` accepterar valfritt `business_id`; vanliga användare scopeas ändå till egen verksamhet och Super User kan låta områdesfokus välja verksamhet.
- `max_rows` i `/api/query-data/run` är valfritt. `null` eller utelämnat värde betyder att backend inte beskär raderna efter fetch; ett ifyllt tal begränsas fortfarande av serverns maxinställning.
- Hämtningen mot extern datakälla går via `ExternalDataClient.fetch_all` (delad `fetch_all_rows`). Om datakällan kapar svaret vid sitt radtak (`DATA_SOURCE_RESPONSE_ROW_CAP`, default 50000) delas frågan automatiskt upp i mindre datumfönster på planens Between-datumfilter och slås ihop, så hela perioden hämtas. Saknas ett splittbart datumfilter returneras de kapade raderna och en varning loggas. Samma `fetch_all` används av Hämta data, Inställningar-uträkningen, Produktivitet och Bearbeta — en enda sanning för "hämta komplett resultatmängd".
- Beräkningar körs alltid på hela API-svaret innan `max_rows` beskär tabellpreviewn. En prompt som "ta bort dubletter för artikelnummer per inköpsnummer" blir `count_distinct` med `distinct_by=["book_num","item_num"]`, inte fri SQL och inte externa `identifiers`.
- Live-kontroll mot riktig extern datakälla finns som opt-in-test i `tests/integration/test_data_source_live.py`. Det körs bara med `RUN_DATA_SOURCE_INTEGRATION=1`, använder `DATA_SOURCE_*` och kan jämföra resultatet mot `LIVE_DATA_SOURCE_EXPECTED_PICK_COUNT` eller mot eget SQL-facit via `LIVE_DATA_SOURCE_SQL_URL` + `LIVE_DATA_SOURCE_SQL`.
- Resultatens export-rader skrivs till temporara serverfiler per `session_id` med TTL, maxantal och byte-budget. Sessionens RAM-del haller bara anvandarkoppling, plan, kolumner, radantal och filreferens; Excel-exporten laser filen vid behov.
- `app/backend/workflow_data.py` ateranvander `ExternalDataClient` for Bearbeta och Produktivitet, men utan MiniMax-plan, utan prompt och utan radbegransning. Bearbeta hamtar valda kallor vid korning; Produktivitet anvander samma materialisering for sin schemalagda API-snapshot med pick/trans/pallet/receive/sort/kpi. Dessa kallor anvander ocksa verksamhetens tenant nar backend kanner till verksamheten. Det ar inte samma anvandarflode som Hamta data och kraver inte `dataFetch`.

- Vid API-first/workflow-materialisering ar tekniskt kolumn-id i katalogen primar kontraktssanning. Svenska och engelska labels ar presentation eller CSV-rubrik. Om en gammal motor kraver svensk rubrik ska `workflow_data.py` mappa fran tekniskt id till legacy-rubrik med explicita alias; om svensk rubrik inte hittas far agenten inte anta att kolumnen saknas innan tekniskt id och engelsk label har kontrollerats.

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
Svar: Lämna `Max rader` tomt och klicka `Hämta data`. Då skickas inget radtak till backend. Backend hämtar dessutom hela perioden även om den överstiger datakällans radtak: `fetch_all` delar automatiskt upp frågan i datumfönster (kräver ett datumfilter) och slår ihop resultaten, så du inte tyst fastnar på t.ex. 50000 rader. Saknas datumfilter kan resultatet kapas vid radtaket — lägg då till en period.

Fråga: Hur tar jag bort kolumner från resultatet?
Svar: Klicka på kolumnchippen i planpanelen och tryck `Uppdatera plan`. Då tas kolumnerna bort från `output_columns`, gammalt resultat rensas och nästa `Hämta data` använder den uppdaterade planen. Det går inte att ta bort alla kolumner.

Fråga: Hur räknar jag ordernummer som börjar på TO?
Svar: Skriv till exempel "antal unika ordernummer i plocklogg full som börjar på TO". MiniMax ska returnera `StartsWith` på `order_num`, backend visar querytext som `order_num LIKE 'TO%'` och filtrerar raderna lokalt innan beräkningen körs.

Fråga: Varför fick jag HTTP 500/502 när planen såg rätt ut?
Svar: Planen kan vara korrekt men externa datakällan kan ändå neka, stänga anslutningen, vara nere eller svara med fel. Vid sådana fel visar Hämta data ett fel-id. Leta på samma fel-id i Render-loggarna för att se vilken vy som kördes och om felet var nätåtkomst, endpointmall, SSL-verifiering eller HTTP-status från datakällan.

Fråga: Hur kontrollerar jag en uträkning mot riktig extern data?
Svar: Kör live-testet opt-in, till exempel `RUN_DATA_SOURCE_INTEGRATION=1 LIVE_DATA_SOURCE_EXPECTED_PICK_COUNT=45945 python -m pytest tests/integration/test_data_source_live.py -q -s`. Standardfallet testar `v_ask_pick_log_full` för maj 2026, `GG`, `pick_zone <> H`, `qty_suf >= 1` och `time_stamp_int` som datumfält. Byt vid behov med `LIVE_DATA_SOURCE_YEAR`, `LIVE_DATA_SOURCE_MONTH`, `LIVE_DATA_SOURCE_COMPANY`, `LIVE_DATA_SOURCE_DATE_FIELD`, `LIVE_DATA_SOURCE_TENANT`, `LIVE_DATA_SOURCE_EXCLUDE_ZONE` och `LIVE_DATA_SOURCE_MIN_PICKED`.

Fråga: Varför blev `april 2026` ett ordernummerfilter?
Svar: Hämta data försöker nu känna igen svensk månad + år, `idag`, `dagens` och `senaste N dagarna` innan MiniMax-anropet. För loggvyer ska perioden användas på bästa datumkolumn, till exempel `time_stamp_int` i plockloggen eller `timestamp` i transloggen. Om modellen ändå lägger perioden i `order_num` eller hittar på fel datum reparerar backend filtret innan anropet körs.

Fråga: Hur räknar jag bort dubletter?
Svar: Beskriv nyckeln i prompten, till exempel "ta bort dubletter för artikelnummer per inköpsnummer". MiniMax ska då returnera `calculation.metric=count_distinct` med `distinct_by` på de tekniska kolumnerna, och backend räknar unika kombinationer efter hämtning.

Fråga: Varför stoppas en MiniMax-plan?
Svar: Backend accepterar bara vyer, kolumner, filteroperatorer och beräkningsoperationer som finns i kontraktet/katalogen. Om modellen hittar på något stoppas körningen innan extern datakälla anropas.

Fråga: Varför blir "plocklogg full för januari" tomt fem månader senare?
Svar: Det ska det inte längre. "Plocklogg Full" (`v_ask_pick_log_full`) läser `PICK_LOG` som bara behålls ~40 dagar operativt, men sedan 2026-06 dirigerar Hämta data automatiskt om gamla perioder till arkivvyn `dblog_pick_log` (`log_wmanfrey`, ~800 dagar). Spänner perioden över gränsen hämtas båda och slås ihop. En notis i planpanelen talar om vad som hämtades. Kolumnerna i arkivvyn skiljer sig, så vissa fält kan vara tomma. Se [ASK datalagring](ask-datalagring.md) för de 14 mappade vyerna och retention per vy.

Fråga: Varför står det att data hämtades från arkivet / att två vyer slogs ihop?
Svar: Den valda live-vyn behålls bara ett begränsat antal dagar operativt (retention). När din period ligger helt eller delvis bortom det byter Hämta data automatiskt till `dblog_*`-arkivvyn, eller hämtar både live och arkiv och slår ihop dem. Notisen visar exakt vilka vyer och datumintervall som användes. Eftersom live- och arkivvy har olika kolumnuppsättning blir sammanslagningen inte exakt likadan — saknade fält visas tomma.

## Källor

- `../app/frontend/hamta-data.html`
- `../app/frontend/js/data_fetch.js`
- `../app/backend/routers/data_fetch.py`
- `../app/backend/data_fetch_service.py`
- `../app/backend/external_data_client.py`
- `../app/backend/workflow_data.py`
- `../tools/build_external_data_catalog.py`

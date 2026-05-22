---
title: Wiki-logg
status: aktiv
updated: 2026-05-22
tags: [wiki, logg]
---

# Wiki-logg

## [2026-05-22] feature | Felkodsdashboard i Historik

Historik har nu tre lagen: Anvandarhistorik, Analys och Felkoder. Frontend rapporterar API-fel tyst till `/api/audit/client-error` nar en inloggad anvandare traffar 4xx/5xx eller natverksfel, och Super User kan summera dem via `/api/audit/errors`. Felpayloaden saneras till metod, path utan querystring, status/felkod och kort meddelande for att ge felsokningssignal utan request body, cookies, losenord, filnamn eller queryvarden.

## [2026-05-22] feature | Omraden i Verksamheter-vyn

Verksamheter-vyn for Super User visar nu omraden under varje verksamhet. Super User kan skapa, redigera och ta bort/inaktivera omraden via `/api/areas`; tomma omraden hardraderas medan omraden med kopplade personer, aktiviteter eller anvandare inaktiveras. Lade ocksa till regressionstester som fangar R3-fokus i Personer-vyn, sa Super User inte ser Stigamo-personer nar fokus star pa R3.

## [2026-05-22] perf | Snabbare omradesvaxling i planeringsvyer

Bemanning och Oversikt forhamtar nu alla synliga omraden for aktuell period i bakgrunden och filtrerar omradesfokus klient-side nar cachen finns. Cachen ar verksamhets- och anvandarscopead via de API-svar anvandaren redan far se, och ogiltigforklaras vid schema-/oversiktsandringar for att undvika gammal data. Klienten kontrollerar dessutom latta revision-endpoints tyst i bakgrunden, normalt var 10:e sekund vid aktiv anvandning och var 30:e sekund vid idle, och patchar bara andrade synliga celler nar ny serverdata finns. Bada breda planeringsmatriserna har ocksa en synkad horisontell scrollbar ovanfor tabellen nar nedersta scrollen annars hamnar langt bort.

## [2026-05-22] feature | Fyller auditluckor for anvandarfloden

Utökade Historik/audit-dokumentationen för nya auditrader: första lösenord på konto, globala inställningar, serverhanterade produktivitetsfiler och körda lagerverktygsflöden. Misslyckade uppladdningar som når backend loggas nu också som `upload_failed`/`detect_failed`. Loggarna ska ge felsökningssignal men undvika lösenord, API-detaljer och privata filnamn/listvärden.

## [2026-05-22] rename | Bytte programnamn fran Bemanning till flow

Programmet bytte namn fran "Bemanning" till "flow" (sma bokstaver). Bevarade
termer: Bemanningsvy/Bemanningsvyn (vyn), Bemanningsansvarig (rollen),
Bemanningskalkyl/Bemanningsmatris/bemanningsceller (vy-relaterade features),
wiki/bemanning-schedule.md (filnamn for vyns dokumentation). Ikon for
fonster/desktop bytt till allokeringsprojektets app.ico (-> flow_icon.ico).
Installer-ikonen for releases bevarad (ingen SetupIconFile finns i .iss).

## [2026-05-21] ingest | Initial projektwiki

Skapade forsta LLM-wikin for flow enligt Karpathy-modellen: index, agentregler, kallmanifest, arkitektur, datamodell, rollmodell, API-karta, UI- och funktionssidor samt felsokningssida for framtida LLM-chat.

Kallor som lastes: `AGENTS.md`, `app/README.md`, `API_ROUTES.md`, `APP_MIGRATION_PLAN.md`, `TESTPROTOCOL.md`, frontend-HTML, frontend-JS, backend-routers, datamodeller, lagerverktygskatalog och produktivitetsservice. Karpathy-gisten anvandes som strukturmonster for persistent wiki, index och logg.

## [2026-05-21] expand | Anvandarhandbok, handelser och felkoder

Lade till `user-guide.md`, `user-events.md` och `error-reference.md` med mer detaljer om hur programmet anvands, vad anvandaren kan se i olika lagen, vanliga toastar/confirm-dialoger, HTTP-statuskoder och backendens viktigaste felmeddelanden. Uppdaterade `index.md` och `troubleshooting-chat.md` sa framtida LLM-chat hittar materialet.

## [2026-05-21] feature | Apphjalp och MiniMax-chatt

Dokumenterade den nya pratbubbelknappen under omradesfokus/infinity, sessionssparad dialog, 10-fragorsgrans, `Rensa dialog`, MiniMax-konfiguration och nya API-vagar i `app-chat.md`. Uppdaterade index, UI-karta, API-karta, anvandarhandelser, felreferens och felsokningssidan sa framtida LLM-chat kan forklara hur apphjalpen fungerar och varfor den kan stoppa.

## [2026-05-21] polish | Chattformat i smal panel

Uppdaterade apphjalpens prompt och frontendrendering sa svaren passar den lilla dialogrutan battre. Modellen instrueras att undvika markdown-tabeller och skriva korta block/listor; frontend renderar enklare Markdown som rubriker, fetstil, kod, listor och tabeller snyggare om det anda kommer.

## [2026-05-21] polish | Chattikon och laddning

Justerade apphjalpens pratbubbel-SVG sa den inte klipps i sidebarens 40px-knapp och lade till en rund spinner i chattflodet medan API-svar hamtas.

## [2026-05-21] policy | Hardare chattsanning och repo-sok

Skarpte apphjalpens prompt: wikin ar normalfragornas grans, sa om wikin inte sager att en funktion finns ska chatten svara nej/inte dokumenterat i stallet for att spekulera. Lade till repo-sok-kontext nar anvandaren invander eller ber chatten kolla koden, samt instruktion om korrekt svenska med `å`, `ä` och `ö`.

## [2026-05-21] fix | Tydligare SQLite-lås vid lokal start

Uppdaterade lokal databasforberedelse sa `PermissionError` vid ersattning av `app/flow_local.db` blir ett tydligt meddelande om gammal `start_local.bat`/`uvicorn` i stallet for en lang Python-traceback. Dokumenterade handelsen i `user-events.md`.

## [2026-05-21] polish | Behorighetsrad och chattraknare

Fortydligade att `Vybehorigheter`, rollandringar och Super User-kontroller kraver admin-/Super User-atkomst och inte ska beskrivas som sjalvservice for vanliga anvandare. Dokumenterade ocksa att apphjalpens `x/10`-raknare visar anvanda fragor i hela aktuell server-/browser-session, inte bara fragorna som syns i panelen.

## [2026-05-21] fix | Rensa apphjalp vid logout

Frontend rensar nu apphjalpens lokala `sessionStorage` vid logout, inklusive dialog, utkast, oppet lage och lokal frageraknare. Detta matchar backendens `request.session.clear()` sa ny inloggning inte visar gammal lokal `6/10`-raknare. Lokal chattdata har ocksa en versionsnyckel sa gammal sessiondata fran tidigare implementation rensas automatiskt vid nasta sidladdning.

## [2026-05-21] feature | Anvandarkontext i apphjalpen

Apphjalpens backend skickar nu begransad supportkontext om inloggad anvandare till MiniMax: visningsnamn, anvandarnamn, roller, Super User-status, omrade och effektiva vybehorigheter per vy. Syftet ar att chatten ska kunna saga exakt om anvandaren saknar `Harleda`, bara har `view` eller saknar `Bearbeta`. Känslig information som losenord, hashes, sessioncookies, tokens och API-nycklar skickas inte.

## [2026-05-21] feature | Hamta data via extern datakalla och MiniMax

Lade till `Hamta data` som skyddad vy och API-flode for promptstyrd extern dataexport. MiniMax far bara vy-/kolumnkatalog och planformat; URL, endpointmall, headernamn, API-nycklar och klientnycklar ligger i servermiljon. Dokumenterade `data-fetch.md`, nya API-vagar, vybehorigheten `dataFetch`, katalogbyggnad och Excel-export.

## [2026-05-21] hardening | Gommer privata dataflodets leverantorsdetaljer

Bytte Hämta data-flodet till generiska `DATA_SOURCE_*`-miljovariabler, neutral API-route `/api/query-data`, generisk klient `external_data_client.py` och katalogfil `data/external_data_catalog.json`. Endpointmall och headernamn ligger nu i env i stallet for kod/wiki, och dokumentationen beskriver bara extern datakalla.

## [2026-05-21] fix | Spärrar Hämta data utan konfiguration

Hämta data-health returnerar nu status utan att kasta 503 nar katalog/env saknas. Frontend spärrar `Tolka med MiniMax` och `Hämta data` tills katalog, MiniMax och extern API-konfiguration finns, sa saknad katalog inte kan skapa AI-usage eller en missvisande arbetsyta.

## [2026-05-21] config | Publicerar Hämta data-katalogen

Katalogen `data/external_data_catalog.json` bedomdes inte vara hemlig och ska commitas sa Render har vy-/kolumnstruktur direkt. API-nycklar, URL:er, headernamn och endpointmallar stannar fortsatt i `.env`/Render secrets.

## [2026-05-21] support | Stoppa lokal server

Lade till `stop_local.bat` for att stanga gamla lokala `start_local.bat`/uvicorn-processer och frigora port `8000` nar `app/flow_local.db` ar last. Uppdaterade README och anvandarhandelser med kommandot.

## [2026-05-21] polish | Enter skickar apphjalp

Apphjalpens textfalt skickar nu fragan med Enter. `Shift+Enter` finns kvar for ny rad, och frontend ignorerar extra submit medan ett svar redan hamtas.

## [2026-05-22] fix | Stabilare Hamta data-API

Hämta data-klienten kan nu styras med `DATA_SOURCE_VERIFY_SSL` och `DATA_SOURCE_CA_BUNDLE` for lokala certifikatkedjor. Dokumenterade att bas-URL och sökvägsmall hålls separata, och lade till appklocka/periodhints så månad + år, dagens datum och senaste N dagarna styrs mot datumfält i stället for ordernummer eller hallucinerade datum.

## [2026-05-22] feature | Redigerbara Hamta data-kolumner

Planpanelen i Hämta data låter nu användaren markera MiniMax-valda kolumner för borttagning och trycka `Uppdatera plan`. Planens `output_columns` skrivs om lokalt, gammalt resultat rensas och nästa hämtning/export använder bara kvarvarande kolumner.

## [2026-05-22] polish | Tar bort Las om katalog

Tog bort den manuella `Läs om katalog`-knappen från Hämta data. Katalogen förväntas alltid finnas uppladdad i servermiljön och läses automatiskt av backend.

## [2026-05-22] polish | Tydligare Hamta data-flode

Bytte knapptexten från `Tolka med MiniMax` till `Tolka`. Hämta data och Excel-export räknar nu knappstatus från samma frontend-state: hämta kräver en godkänd tolkning, export kräver ett hämtat resultat, och ändrad prompt rensar gammal plan/resultat.

## [2026-05-22] fix | Visar allokerade pallar i Bearbeta

Allokeringsflodets huvudresultat visas nu som `Allokerade pallar` i Bearbeta och kan oppnas i Excel eller laddas ner som CSV. Frontenden filtrerar inte langre bort resultattabellen `result` for Allokering.

## [2026-05-22] fix | Hardar Oppna i Excel

Lagerverktygens `Oppna i Excel` anvander nu flows egen Excel-skrivare med sakra blad- och filnamn, i stallet for den gamla allokeringsmotorns tysta OS-oppnare. Om Windows/Excel inte kan oppna filen kommer felet tillbaka som toast, och lyckad start visar `Excel oppnas`.

## [2026-05-22] fix | Normaliserar lagerverktygens CSV-export

CSV-exporten for lagerverktygsresultat skriver nu celler via samma visningsnormalisering som previewn: heltalslika floats blir `1` i stallet for `1.0`, och NaN/None blir tomma celler. Det gor jamforelser mot Excel-exporten fran allokeringsprogrammet stabilare.

## [2026-05-22] change | Tar bort Harleda

Harleda-vyn och Eftersok-flodet ar borttagna fran aktiv webb/desktop-yta, sidebar, vybehorigheter, Apphjalpens kontext, lagerverktygens flodeskatalog och tester. Lagerroller har nu sjalvservice via Uppladdningar och Dela; Bearbeta ar fortsatt Super User-/processvyn.

## [2026-05-22] feature | CLI for Bearbeta och Dela

Lade till `warehouse_tools.cli` for lokal korning av alla lagerfloden utan server, browser, IndexedDB eller cookies. CLI:t har flodeslista, schema, filidentifiering, generisk `run`, scenariofiler, scenario-validering och egna subcommands per flode, inklusive `allocate` och `split-values`. Filinputs kan anges explicit eller matchas automatiskt med samma filtypdetektor som UI:t.

## [2026-05-22] feature | API-CLI for lagerverktyg och parityjamforelse

`tools.flow_cli` har nu `allocation`-subcommands for `/api/allokering`: `flows`, `pool`, `detect`, `run`, `observations-update`, `download`, `column` och `open-excel`. `allocation run` kan ladda ner fulla resultat-CSV:er fran sessionssvaret. Lade ocksa till `tools.compare_warehouse_results` for Flow-vs-Allokera-jamforelser av CSV/XLSX med normalisering av exportbrus som `1.0` mot `1` och NaN mot tomt.

## [2026-05-22] polish | Kopiera fritextrapport i lagerresultat

Fritextrutor i lagerverktygens resultat, till exempel Vecka 27-rapporten, har nu en kopieringsikon uppe till hoger. Knappen kopierar hela rutans text till urklipp och visar toasten `Text kopierad`.

## [2026-05-22] feature | Direktimport for flera registerrader

Personer, Aktiviteter och Anvandare har nu knapparna `Flera nya personer`, `Flera nya aktiviteter` och `Flera nya anvandare`. Varje knapp oppnar en tabellmodal som skickar samma falt som Excelmallarna till nya `/import-rows`-endpoints och ateranvander importernas validering, auditlogg och resultatmodal. Excelimporten finns kvar.

## [2026-05-22] polish | Enter aktiverar dialogers primarknapp

Alla frontendmodaler far nu gemensamt Enter-beteende via `common.js`: Enter i ett vanligt modalfalt klickar primarknappen, till exempel `Spara`, `Skapa` eller `Stang`. Flerradiga textfalt, checkboxar och knappar med eget fokus undantas.

## [2026-05-22] rename | Byter flow-vyn till Bemanning

Den anvandarsynliga planeringsvyn heter nu `Bemanning` i sidebar, sidtitel, vybehorigheter, Apphjalpens vyetiketter och wiki. Tekniskt view-id och API ligger kvar som `schedule` och `/api/schedule`.

## [2026-05-22] change | Omradesfokus ersatter omradesrullistor

Omradestogglen i sidebar styr nu Bemanning, Oversikt, Produktivitet, Aktiviteter och Anvandare. `∞` betyder alla omraden. De separata omrades-/blockrullistorna i Bemanning, Oversikt, Produktivitet och Bemanningskalkylen ar borttagna; omradesfalt som satter data i modaler och import finns kvar.

## [2026-05-22] fix | Visar Avvikelsetyp i orderkontroll

Bearbeta-resultat visar nu kolumnnamn i tabellhuvudet med en kopieringsikon bredvid. Orderoversiktkontroll har regressionstest som sakrar att `Avvikelsetyp` finns kvar i Flow/API-resultat och exportkontraktet for `Orderkontroll`, samma som i Allokera.

## [2026-05-22] fix | Matchar Allokera for pallplatser

Flow raknar nu pallplatser som Allokera: zon `F` blir separat `HIB`-kolumn med 20 rader per toppall, medan `autostore` bara raknar zon `R`. Detta gor `Topp Pallar`, `Totalt Pallar` och `Pallplatser` lika i Flow och Allokera for samma allokeringsunderlag.

## [2026-05-22] feature | Ordersaldo kopierar och visar helpall

Ordersaldo kopierar nu `Kompletta ordrar` automatiskt nar flodet ar klart. `Underskott` far kolumnen `Antal pa Helpall` fran `artikel_max.csv`, med karnfilen som fallback om anvandaren inte laddar upp en egen.

## [2026-05-22] perf | Cachar Bearbeta-filer i Flow

Bearbeta i Flow sparar nu uppladdade filer med innehallshash, utan originalfilnamn, och ateranvander samma serverfil nar samma underlag skickas igen. Cachen rensas opportunistiskt med tidsgrans och maxantal filer sa verksamhetsisolerad drift inte far langlivade uppladdningar. `warehouse_tools.flows` har dessutom en LRU-cache for inlasta tabeller baserad pa sokvag, storlek och modifieringstid, sa upprepade floden mot samma filer slipper lasa om stora CSV:er.

Bearbeta-resultatsessioner binds samtidigt till anvandaren som korde flodet. `Oppna i Excel`, `Ladda ner CSV` och kolumnkopiering svarar som saknat resultat om en annan anvandare forsoker anvanda session-id:t.

Cacheindexet ar scopeat per anvandare, uppladdningsslot och filnamn. Om samma anvandare laddar upp samma slot/filnamn med nytt innehall tas den tidigare cachefilen bort direkt; om filens path redan saknas skrivs den om fran den nya uppladdningen.

## [2026-05-22] feature | Verksamheter som isoleringsniva

Lade till Verksamheter som ny niva ovanfor omrade. Stigamo ar bakatkompatibel standard, R3 seedas separat med eget R3-omrade och egna franvaroaktiviteter, och icke-Super Users scopeas till sin egen verksamhet i register, schema, oversikt, settings och toggles. Super User far nya vyn Verksamheter och kan anvanda `∞` globalt.

## [2026-05-22] test | Stor verksamhetskontroll

Utökade verksamhetstestningen med många användare i Stigamo/R3, korsverksamhetsförsök, Super User-create, dubbletter per verksamhet, settingsisolering, public API-defaults och frontendkontrakt för dynamisk toggle och verksamhetsfält. Lade till en egen wikisida för Verksamheter och uppdaterade testprotokollet med obligatoriska regressionskommandon för webb och desktop-proxy.

## [2026-05-22] fix | Lokal verksamhetsbootstrap och tecken

Fixade lokal SQLite-bootstrap så äldre `app/flow_local.db` med globala unika områdes-/aktivitetskoder migreras till verksamhetsscope utan att radera lokal data. Tog också bort felkodade tecken i användarsynliga frontend/backend-strängar i Bemanning/Översikt efter verksamhetsändringen.

## [2026-05-22] fix | Personer följer R3-fokus

Fixade Personer-vyn så Super User inte längre ser global personlista när områdestogglen står på R3. Vyn skickar nu valt `area_id` till `/api/persons`, filtrerar även klient-side och laddar om listan när områdesfokus ändras.

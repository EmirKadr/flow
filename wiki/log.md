---
title: Wiki-logg
status: aktiv
updated: 2026-06-04
tags: [wiki, logg]
---

# Wiki-logg

## [2026-06-04] fix | Meta-download och frontend-boot

Meta-vyn laddar nu ner bilder och videor via browserns direkta
nedladdningsflode med HEAD-kontroll och download=1, i stallet for att
forst lasa hela mediafilen som JS-blob. Det minskar RAM-risk for stora videor
och stoppar HTML-felsvar fran att visas som lang raw markup i en toast.
Samtidigt namespacades common.js interaction-endpoints sa de inte krockar med
api.js globala konstanter; krockan gjorde att vanliga sidor kunde sluta boota
efter login och fallerade Playwright-testerna.

## [2026-06-04] fix | Historik-kontroller matchar frontend-idn

Interaction-coverage i Historik anvander nu samma faktiska kontroll-id:n som
frontendens personer-, aktiviteter- och anvandarvyer. Det gor att
known-controls-kontraktet i CI inte faller pa gamla camelCase-alias.

## [2026-06-04] fix | Flyttar legacy-data mot DB och persistent disk

Legacy-karnfiler och KPI kan nu migreras till `coredata_files` med
`python -m backend.scripts.migrate_legacy_data_to_truth`, utan att scriptet
raderar gamla repo-filer. Sammanstalld produktivitetsdata, buffertpall-
observations och `artikel_max.csv` pekar mot `PRODUCTIVITY_DATA_DIR` eller
`MEDIA_STORE_ROOT/flow-data`; lokal/dev faller tillbaka till den projektlokala
ignorerade mappen `local_media/flow-data` i stallet for repo-kataloger.
Release-checken kraver inte langre att gamla buffertpall-datafiler paketeras i
Windows-bygget.

## [2026-06-05] fix | Buffertpallhistorik kravs innan artikel_max anvands

Lagerfloden som behover `artikel_max.csv` accepterar inte langre en tom/header-only
fallback som giltig sammanstalld data. Saknas observationshistorik for
verksamheten stoppas flodet med krav pa buffertpalluppladdning; observations kan
starta tomt, men `artikel_max.csv` byggs forst nar buffertpallhistorik finns.

## [2026-06-04] feature | Windows kor Bearbeta och Produktivitet lokalt

Windows-appen registrerar nu filval som lokala referenser via Qt-bron och later
desktop-local-servern fanga Bearbeta- och Produktivitet-endpoints. Berakningen
laser aktuell fil fran disk och koar bakgrundssync av karnfiler/KPI och
sammanstalld data utan att starta alla tunga jobb samtidigt. Uppladdningars
`Visa`-preview ar ersatt av explicita `Ladda ner`, `Oppna fil` och `Mapp`-
atgarder sa filer bara hamtas eller oppnas nar anvandaren klickar. Lokala
korningar auditloggas centralt som sanerad metadata utan sokvagar eller
filinnehall.

## [2026-06-03] fix | Minskar 502 vid Render-OOM

Render-startsyncen for allokeringsobservationer ar nu avstangd som standard med
`ALLOCATION_OBSERVATIONS_STARTUP_SYNC=false`, sa servern inte gor tung
observationssync direkt efter omstart. Coredata-status for `artikel_max.csv`
raknar sin path utan att ladda legacy-lagerbryggan, och Windows-klientens
health check forsoker om korta 502/503/504-fonster innan felvyn visas.

## [2026-06-03] fix | Gor Forecast-CLI mappbaserad

`warehouse_tools.cli forecast` kan nu ta Forecasts coredata-filer som egna
argument och `--auto-dir` for att matcha en hel testdatamapp. Orelaterade filer
i mappen ignoreras och tidigare matchade inputs behalls, sa en aktuell
`item_option` i testmappen vinner over fallbacken i `data/coredata/Stigamo`.

## [2026-06-03] fix | Minskar Forecast-minne efter korning

Bearbeta-uppladdningar streamas nu till serverns temporara cache i bitar i
stallet for att lasas som en enda bytes-klump. Forecast sparar fortsatt
resultatet som sessionstabell for Ytgenerering, men skapar inte langre en full
`forecast_json`-kopia av alla rader bredvid DataFrame-tabellen. Gamla
Bearbeta-resultatsessioner stadas opportunistiskt for att minska risken for
Render-minnesspik efter flera stora korningar.

## [2026-06-03] fix | Sanerar 502-HTML i dokumentloggen

Frontendens `api.js` visar inte langre raw HTML nar server/proxy svarar med en
HTML-felsida, utan kort status som `HTTP 502 (Bad Gateway)`. Bakgrundsprefetch
dolder likadana fel i 60 sekunder efter forsta warn-raden, sa dokumentloggen
inte fylls av samma serverfel nar flera forvarmda API:er misslyckas samtidigt.
`user-events.md`, `history-audit.md` och `error-reference.md` beskriver det nya
felsokningsbeteendet.

## [2026-06-02] fix | Synkar uppladdningsnamn mot filkunskap

Uppladdningar, Bearbeta och Produktivitet använder nu svenska `label_sv` från
filkunskapen för kända vyfiler. Exempel: `v_ask_booking_putaway` visas som
`Ej Inlagrade Artiklar`, `v_ask_customer_order_details_all` som
`Detalj Kundorder (Alla)` och `v_ask_palletloading_log` som
`Pallastningslogg`. Prognosfil, Kampanjfil och Textfil med värden lämnas som
Flow-egna namn eftersom de inte finns i filkunskapen.

## [2026-06-02] docs | Synkar releasepolling for agenter

Releasepolling-regeln ar nu dokumenterad i `AGENTS.md`, `TESTPROTOCOL.md` och
`wiki/testing-release.md`: efter push/tagg verifierar agenten normalt bara att
workflowen startat och delar lank. Om anvandaren ber agenten vanta kvar galler
pollingtrappan 15 minuter, 2 minuter, 1 minut och darefter 30 sekunder tills
workflowen ar klar eller failad.

## [2026-06-02] fix | Uppladdningar visar svenska filnamn

Uppladdningars filrader normaliserar nu rubriken via filkunskapen innan den
ritas. Tekniska alias som `customer_order_details_all` visas darfor som
`Detalj Kundorder (Alla)` i stallet for databasnamnet.

## [2026-06-02] change | Samma datamappar for alla verksamheter

Stigamo anvander nu samma buffertpall-upplagg som R3/T3 med egen undermapp
under `warehouse_tools/vendor/lowfreqdata/buffertpall/stigamo/`.
Observations-startup-syncen laser aktiva verksamheter fran databasen i stallet
for en hardkodad Stigamo/R3-lista, och nya verksamheter provisionerar egna
coredata-/sammanstalld-data-roots vid skapande. Produktivitetens
verksamhetsscopeade KPI-lasning har inte langre Stigamo-root som specialfall.

## [2026-06-02] fix | Forsenad observations-sync vid serverstart

Render-starten laddar inte langre lagerverktygens observations-sync direkt.
Startup-hooken finns kvar men vantar nu enligt
`ALLOCATION_OBSERVATIONS_STARTUP_DELAY_SECONDS` och syncar verksamheterna en i
taget med paus enligt `ALLOCATION_OBSERVATIONS_STARTUP_SPACING_SECONDS`.
Automatiken kan stangas av med `ALLOCATION_OBSERVATIONS_STARTUP_SYNC=false`.

## [2026-06-02] fix | Ytkartans hjalplinjer blir mjukare

Installningar for Ytgenereringens ytkarta har nu ett tajtare snap-avstand och
diskretare hjalplinjer vid dragning. Vanliga klick ritar inte langre om kartan
direkt, sa dubbelklick pa en yta fungerar igen for att rotera den 90 grader.

## [2026-06-02] feature | Hjalplinjer vid ytdragning

Installningar for Ytgenereringens ytkarta visar nu hjalplinjer medan en yta
dras. Dragningen snappar mot andra ytors vansterkant, mitt, hoger kant,
topp, mitt och botten sa det blir lattare att hamna i samma hojd eller kolumn.

## [2026-06-02] fix | Ytkartans hogerklicksmeny foljer klicket

Hogerklicksmenyn `Byt riktning` i Installningar for Ytgenereringens ytkarta
positioneras nu lokalt i kartans workspace och kompenserar for appzoom. Den
ska darfor hamna vid hogerklicket i stallet for att flyta ut mot sidopanelen.
Installningar-sidan har ocksa ny script-version sa browsern inte fortsatter
ladda cachad kartkod.

## [2026-06-02] polish | Loggikon signalerar utan raknare

Dokument-/loggikonen i sidebaren visar nu en kort pil upp och en bubbla som
tonar ut varje gang en loggrad skrivs. Den gamla olast-raknaren visas inte
langre och gammalt sessionStorage-varde for raknaren rensas nar ikonen
initialiseras eller signalerar.

## [2026-06-02] fix | Ytkartor skalar nya ytor efter pallplatser

Nar en ledig U-plats laggs till i Installningar for Ytgenereringens ytkarta
skalas ytan nu efter sin `Max pall`. Formen behaller samma kortsidesbredd som
basytan men forlangas langs langssidan, sa en 7-palls-yta blir 3,5 ganger
langre an en 2-palls-yta.

## [2026-06-02] fix | Ytkartsfalt foljer markerad yta

Installningar for Ytgenereringens ytkarta synkar nu sidopanelens falt direkt
nar anvandaren markerar en yta pa kartan. `Yta`, koordinater, storlek och
kapacitet visar darfor den senast markerade ytan aven nar markeringen sker utan
en full omritning av kartan.

## [2026-06-02] feature | Verksamhetsfilter i Historik

Historik har nu ett filter for `Verksamhet` i toppraden. Super User kan valja
Alla eller en specifik verksamhet; valet skickas som `business_id` till
anvandarhistorik, analys, felkoder och Vantetider. Anvandarlistan smalnas av
nar verksamhet valjs. Halsa-fliken fortsatter visa global driftstatus.

## [2026-06-02] polish | Ytkarta roterar med dubbelklick

Installningar for Ytgenereringens ytkarta anvander nu dubbelklick pa en yta
for att rotera ytan 90 grader at vanster runt sin mittpunkt. Lastningsriktning
byts i stallet via hogerklicksmenyn `Byt riktning`, som fungerar for bade en
markerad yta och flera markerade ytor samtidigt.

## [2026-06-02] fix | Korta UTL-ytor visas i Installningar

Ytgenereringens lagerplatsfilter accepterar nu `Typ=U`-ytor med UTL-nummer
1-652 oavsett om numret ar skrivet med inledande nollor. Det gor att
`UTL01`-`UTL99` syns i Installningars lista over lediga U-platser och kan
anvandas i Ytgenerering pa samma satt som `UTL100` och uppat.

## [2026-06-02] feature | Lanar person via hogerklick i Bemanning

Bemanning har nu en hogerklicksmeny pa personnamn med `Skicka till <omrade>`.
Valet skriver personens schemalagda timmar for aktuell dag till malomradets
aktiva standardaktivitet via `POST /api/schedule/cells` med `action=loan_to_area`.
Personens hemomrade andras inte; samma omradesfilter som tidigare gor att
personen syns bade i hemomradet och i omradet som lanar in personen.

## [2026-06-02] fix | Ytkarta sparas per verksamhet

Ytgenereringens ytkartsinstallningar laser och sparar nu `ytgenerering_map_layout`
i samma verksamhetsscope som vald Bearbeta-toggle. Sparsvaret returnerar samma
scopade layout, sa lastningsriktning och andra andringar inte hoppar tillbaka
direkt efter `Spara`. Frontend visar inte langre sparat om serversvaret saknar
samma ytor, koordinater, kapacitet och lastningsriktningar som skickades.

## [2026-06-02] polish | Lastningspil blir diskretare

Installningar-vyn for Ytgenereringens ytkarta visar nu lastningsriktningen som
en diskret fylld pilkil i ytans kant i stallet for en stor streckpil. Ytkoden
ligger kvar centrerad i hela ytan nar riktningen byts.

## [2026-06-02] fix | Lastningsriktning foljer langsta sidan

Ytgenereringens ytkartsinstallningar vaxlar nu bara mellan tva
lastningsriktningar per yta. Breda ytor kan bara ga hoger/vanster och smala ytor
kan bara ga ned/upp, sa pilen, ytkoden och den randiga outnyttjade kapaciteten
alltid ligger parallellt med ytans langsta sida.

## [2026-06-02] feature | Lastningsriktning styr ytkarta

Installningar-vyn for Ytgenereringens ytkarta visar nu en pil pa varje yta.
Dubbelklick pa ytan byter lastningsriktning mellan hoger, ned, vanster och upp.
Riktningen sparas i `ytgenerering_map_layout` och styr i Ytgenerering var
ytkoden visas samt vilken sida som blir randig vid outnyttjad kapacitet.

## [2026-06-02] polish | Ytkartan visar ledig total kapacitet

Ytgenereringens ytkarta visar nu `Lediga pallplatser` och `Lediga ytor` i
sidopanelens totalsiffror. Vardena raknas om efter manuella kartflyttar, klistra
in och angra, sa anvandaren ser hur mycket kapacitet och hur manga fysiska ytor
som fortfarande ar lediga.

## [2026-06-02] polish | Installningar-kartan matchar ytkartans etiketter

Installningar-vyn for Ytgenereringens ytkarta visar nu ytans korta kod utan
`UTL` med samma fontstorlekslogik och riktning som Ytgenereringens ytkarta.
Texten ligger parallellt med ytans langsta sida och ar inte fetstild, aven nar
ytan flyttas med drag. Ytkoden anvander en storre storlekskurva an tidigare sa
den utnyttjar tomma ytor battre i redigeringskartan.

## [2026-06-02] feature | Lediga U-platser dras till ytkartan

Installningar-vyn for Ytgenereringens ytkarta later nu anvandaren dra en ledig
`Typ=U`-lagerplats fran sidolistan direkt till kartan. Droppunkten oversatts
till kartkoordinater, ytan far kapacitet fran `location`-underlaget och sparas
som vanlig global `ytgenerering_map_layout`.

## [2026-06-02] fix | Transportorskluster fylls med standardvarden

Transportorskluster-popupen i Forecast fyller nu tomma kluster-, start- och
slutsekvensfalt med inbyggda standardvarden for kanda transportorsnummer.
Rader med transportorsnummer 39 och 40 far till exempel `Freja`, 600-652,
09:00/11:00/13:00 och standardfargen. Backendnormaliseringen anvander samma
defaults sa Ytgenerering far reglerna aven om flodet kors via API.

## [2026-06-02] polish | Ytkartans kundtext foljer langsidan

Kundnamn i Ytgenereringens ytkarta roteras nu pa staende ytor, sa huvudtexten
alltid ligger parallellt med ytans langsta sida. Textbredden beraknas mot
langsidan, vilket ger smala staende ytor mer anvandbart textutrymme.

## [2026-06-01] polish | Ytkartan prioriterar kundnamn

Ytgenereringens ytkarta visar nu kort ytkod utan `UTL` i ytans kortsida,
kundnamn i mitten som kan brytas pa tva rader utan halo, ingen pallrad inne pa
ytan och fargade ljusare rander for outnyttjad kapacitet proportionellt mot
ledig andel.

## [2026-06-01] feature | Ytkarta far egen Installningar-vy

Ytgenereringens ytkarta redigeras nu i sidebar-vyn `Installningar` i stallet
for via en knapp i Bearbeta. Vyn kraver `allocationSettings`, har fast
arbetsbredd med fullskarmsknapp, kan panorera och zooma i samma kartcanvas,
och visar lediga `Typ=U`-lagerplatser fran aktiv
verksamhets `location` som inte redan finns pa kartan. Nar anvandaren lagger
till en yta raknas koordinaterna fram fran vald yta, riktning och gap, och
sparas globalt i `ytgenerering_map_layout`. Kartan stoder ocksa multiurval med
Ctrl/Shift, gruppdrag, piltangentsflytt, Delete och Ctrl+C/X/V/Z/A sa flera
ytor kan flyttas, kopieras, klippas, klistras in och angra som en samlad
redigering.

## [2026-05-29] fix | Verksamhetskoder skapas automatiskt

Verksamheter-vyn kräver inte längre att användaren fyller i kod när en ny
verksamhet eller ett nytt område skapas. Backend skapar kod från namnet och
lägger till suffix vid krock. Modalens aktiv-checkbox använder nu modalens
checkboxlayout så etiketten inte glider isär från rutan.

## [2026-05-26] feature | Produktivitetsloggar sammanstalls

Produktivitet uppdaterar nu tre verksamhetsscopeade csv.gz-filer nar Plocklogg,
Translogg eller Palllastningslogg laddas upp. Plocklogg tar nya `Radid`
(kolumn-id `rowid`) och Translogg nya `Rowid`, medan Palllastningslogg tar
rader nyare an senaste sparade `Ändrad`/timestamp och tillater dubbletter inom de nya raderna. Uppladdningar visar de
tre filerna som `Sammanstalld data` ihop med `artikel_max.csv`.

## [2026-05-26] feature | Godsdeklaration i Bearbeta

Bearbeta har fatt flodet `Godsdeklaration`. Flodet anvander Detalj Kundorder,
Orderoversikt och Alternativ leveransadress ihop med verksamhetens
`item_security_info`-karnfil. DG-rader blir klara direkt, LQ-rader blir bara
klara nar adressen gar till Gotlandspostnummer 620-624, och klara ordernummer
kopieras automatiskt nar korningen ar klar. Ny uppladdad `item_security_info`
ersatter tidigare fil for samma verksamhet pa samma satt som andra karnfiler.

## [2026-05-26] fix | Artikel_max visas som sammanstalld data

Uppladdningar skiljer nu pa coredata-karnfiler och den framraknade
`artikel_max.csv`. Artikel_max visas som `Sammanstalld data`, flowkatalogen
markerar den som `sammanstalld data`, och rensa-alla-texterna sager att bade
karnfiler och sammanstalld data ligger kvar.

## [2026-05-26] fix | Forecast laddar paketerad modell i prod

Forecastens prediktering laddar nu en paketerad kalibreringsartefakt i
`warehouse_tools/mg_forecast/calibration.pkl` innan den forsoker bygga om
traningsdata. Det gor Render/prod oberoende av lokal raw historik och hindrar
`No objects to concatenate` nar `data/history/orders` saknas i servermiljon.

## [2026-05-26] fix | Narvarande ligger fore Undo/Redo

Knappen `Narvarande` ligger nu till vanster om Undo/Redo i bade Bemanning och
Oversikt, sa utskriftsflodet hamnar fore historikknapparna i verktygsraden.

## [2026-05-26] feature | Narvarande-lista for utskrift

Bemanning och Oversikt har nu knappen `Narvarande`. Den hamtar en serverraknad
narvarolista fran `/api/schedule/presence`, valjer Alla omraden eller nuvarande
omrade fore utskrift och grupperar Alla per verksamhet sa Super User inte far
blandade verksamheter i samma lista. Windows-appen anvander en QWebEngine-
printbrygga for samma printflode.

## [2026-05-26] feature | Ytgenerering laddar ASK-import

Ytgenerering skapar nu en tabbseparerad ASK-importfil for order/yta nar alla
sandningar ar placerade och Forecast-resultatet innehaller `Ordernummer`. Varje
ordernummer far en rad med sandningens UTL-ytor i `area_num`, `company=MG` och
`pick_zone=A`; frontend laddar ner filen automatiskt efter klart flode.

## [2026-05-26] fix | Observations foljer R3-toggle

Automatisk observations-uppdatering fran buffertfil skickar nu med samma
omradesfokus som ovriga Bearbeta-anrop. Nar Super User star pa R3 anvands
darmed R3:s observations och `artikel_max.csv` i stallet for kontots
standardverksamhet. Dokumentloggen skiljer ocksa pa 0 nya pallid, dar GitHub-
push inte ar aktuell, och nya pallid dar GitHub inte bekraftade pushen.

## [2026-05-26] fix | Forecast tal saknad transportor

Forecast faller nu tillbaka till default-transportoren `Schenker` internt for
modellens transportorsignal nar en sandningsgrupp finns men orderoversikten
saknar transportorvarde for gruppen. Forecast-resultatet och Ytgenerering far
i stallet `Okand`, sa fallbacken inte styr ytregler. Det hindrar att
Bearbeta/Forecast stoppar pa `mode().iloc[0]` nar underlaget i ovrigt ar giltigt.

## [2026-05-26] fix | Ytgenerering tydliggor sandningsplacering

Ytgenereringens logg, tabellnamn och dokumentation forklarar nu att placeringen
sker per sandning. Transportor anvands for sortering och
`Transportorsoversikt`, men en lagerplats delas inte mellan flera sandningar.

## [2026-05-26] fix | Stoppa vy-redirect-loop

Sidinitiering hamtar nu farsk vybehorighet innan redirect-beslut tas. Om en
anvandare saknar behorighet till aktuell vy skickas den till forsta vy kontot
faktiskt far se, och om ingen vy finns visas ett stoppmeddelande i stallet for
att studsa mellan Bemanning och Oversikt.

## [2026-05-26] fix | Healthcheck laser Render build-loggar

Render-loggar i Halsa anvander nu Render Logs API med `ownerId`, service-id och
`type=build`. `ownerId` forsoker lasas fran service-svaret och kan annars sattas
som `RENDER_OWNER_ID`, sa deployfel kan hamtas utan att blanda ihop Postgres med
lokal SQLite.

## [2026-05-26] fix | Healthcheck skiljer Postgres och lokal test

`tools.healthcheck` har fatt `--skip-db` sa agenter kan hamta Render deploy/loggar
utan att fejka lokal SQLite eller koppla upp mot en databas. Dokumentationen
fortydligar att produktionens databas ar Render Postgres; SQLite anvands bara
for lokal utveckling och temporara tester.

## [2026-05-26] fix | Coredata följer med deploy

`data/coredata/` är inte längre ignorerad av git, så verksamhetens kärnfiler kan
versionshanteras och följa med deploy när de läggs till i en commit. CI:s
Render-simulering kör nu samma produktionssteg som `render.yaml`: migrations och
app-start utan `backend.seed`.

## [2026-05-26] process | Halsa som driftregel

Halsa och Vantetider ar nu dokumenterat som permanent agentarbetsregel i
`AGENTS.md`, `TESTPROTOCOL.md` och `wiki/testing-release.md`. Efter storre
pushar/deploys ska agenter kora eller verifiera `tools.healthcheck report` och
`tools.healthcheck waits` for lokal/serverdrift, databas och anvandarvantetider,
och tydligt fixa eller rapportera kvarvarande `warn`/`error`.

## [2026-05-26] fix | Seed och lokal bootstrap spärras mot live

`backend.seed` stoppar nu körning mot `ENVIRONMENT=production` och Render-databas-URL:er. `backend.bootstrap_local` vägrar köra mot annat än SQLite, så lokal schema-/seedbootstrap inte kan råka skriva till live-Postgres om `DATABASE_URL` pekar fel. Dokumentationen skiljer nu på engångsmigrationer, lokal/dev-seed och production-deploy.

## [2026-05-26] fix | Production kör inte seed vid deploy

Render-builden kör nu bara `pip install` och `alembic upgrade head`. `backend.seed` är kvar för lokal/dev-bootstrap och manuell engångsseed, men körs inte längre automatiskt i produktion. Därmed återskapas inte raderade verksamheter, områden, aktiviteter, personer eller användare vid nästa deploy.

## [2026-05-26] feature | Halsa och vantetidsanalys i Historik

Historik har fatt flikarna `Vantetider` och `Halsa`. Klienten matar vyload, API-vantan, nedladdningar och idle-prefetch utan att skriva brus i dokumentloggen; backend sparar sanerade rader i `user_wait_metrics` och summerar p50/p95/max per vy, steg och event. `GET /api/healthcheck` samlar app-, databas- och Render-status for Super User nar Render-secrets finns, och `tools.healthcheck` kan kora samma halsa/vantetidsanalys lokalt eller mot en inloggad server.

## [2026-05-26] fix | Snabbare omradestoggle i planeringsvyer

Bemanning och Oversikt anvander nu en exakt kortlivad cache per omrade/period utöver all-cache. Om anvandaren vaxlar tillbaka till ett omrade som redan hamtats ritas vyn direkt utan nytt API-anrop, medan all-data fortsatter forvarmas och revisionskontrolleras i bakgrunden. Aborts fran egna snabba omladdningar rapporteras inte langre som `network_error | HTTP 0`, och riktiga natverksfel dedupliceras per path en kort stund for att inte fylla Historik.

Planeringsvyerna prioriterar nu all-data direkt nar cache saknas: Bemanning hamtar hela dagen for verksamheten och Oversikt hamtar hela veckan/manaden, filtrerar valt omrade lokalt och fyller cachelagren innan anvandaren togglar vidare. Det minskar risken att forsta omradesbytet hamnar pa ett kallt API-anrop.

## [2026-05-26] polish | Mindre brus i dokumentloggen

Sidoppningar skrivs inte langre i dokumentloggen och gamla `Oppnade vy`-rader filtreras bort fran sessionloggen. Samma handelse rapporteras i stallet tyst till Historik som `view/open` via `/api/audit/client-event`. Bemanningens summeringsvarning visar nu orsak och kontext, till exempel HTTP-/natverksfel, vecka, dag och omrade, sa anvandaren far mer felsokningsbar information utan att loggen fylls av vanliga sidbyten.

## [2026-05-25] feature | NoMan pa personer

Personregistret har fatt ett frivilligt `NoMan`-falt for WMS-anvandarnamn per person. Faltet syns och kan filtreras/sorteras i Personer, kan redigeras inline, finns i Ny person, direktimport och Excelmallen, och sparas via `/api/persons`; det anvands inte i planering eller forecast annu.

## [2026-05-25] fix | Toastar och Bearbeta-fel syns i loggar

Dokument-loggen i sidebaren fylls nu av alla toastar, inklusive lyckade, varningar och fel, och ovantade klientfel hamnar dar direkt. Bearbetas egna API-wrapper rapporterar nu fel till samma `client_error`-audit som resten av appen, och `allocation_flow/flow_failed` sparar statuskod, felkod, kort felmeddelande, tekniskt meddelande nar det skiljer sig, verksamhet, toggle och filterradantal utan filnamn eller inskickade parametervarden. Forecast-felet `No objects to concatenate` visas som att flodet fick noll rader att sammanstalla efter filer/filter.

## [2026-05-25] change | Super User och demo kan personsortera alla synliga personer

Personsorteringen i Bemanning/Oversikt behaller kravet `personSortOrder=edit`, men Super User och demo ar inte langre lasta till eget anvandaromrade. De kan dra och spara sortering for alla synliga aktiva personer; vanliga admin/bemanningsansvariga ar fortsatt begransade till eget hemomrade.

## [2026-05-25] change | Veckonummer i Oversikt

Oversiktens daghuvuden visar nu datum pa forsta raden och `Vecka XX` pa en mindre rad under. Det galler bade veckovy och manadsvy, sa man ser veckonummer per dagkolumn.

## [2026-05-25] change | Ny anvandare valjer en roll

Skapa-flodet for Anvandare valjer nu exakt en roll: `Ny anvandare` visar ett roll-dropdown och `Flera nya anvandare` visar en `Roll`-kolumn som dropdown. Befintliga anvandare kan fortsatt ha flera roller via redigera-modalen och backend/import kan fortsatt lagra `roles` som lista.

## [2026-05-25] change | Super User och Demo syns i Vybehorigheter

Vybehorigheter-modalens rollmatris visar nu `Super User` som en last `Redigera`-kolumn och `Demo` som en egen sparbar kolumn. Backend accepterar demo-rollens vyatkomst och raknar in den for det fasta `demo`-kontot, medan Super User fortsatt alltid far full atkomst via serverregeln.

## [2026-05-25] fix | Sidebar ar fast vid skroll

Sidebaren ar nu en fast vansterpanel i webb och desktop-frontend. Huvudytan reserverar sidebar-kolumnen separat, demo-bannern ger fast offset, och bara menylistan inuti sidebaren skrollar nar det finns fler menyval an vad som ryms.

## [2026-05-25] feature | Forecast och Ytgenerering i Bearbeta

Bearbeta har fatt `Forecast` och `Ytgenerering`. Forecast kor den portade prognosmotorn fristaende i Flow, grupperar per `Sandningsnr`, anvander verksamhetens coredata (`custom`, `item`, `item_alias`, `dimension`, `pallet_type`, `item_option`) och sparar resultatet bade som tabell/Excel och som temporar sessiondata. Ytgenerering kraver verksamhetens `location` och en kord forecast-session, anvander forecastens DataFrame direkt for snabbaste kedja med JSON-artifact som fallback, cachar fardigfiltrerade lagerplatser per `location`-filversion, filtrerar lagerplatser pa `Typ=U`, UTL-nummer 1-652 och `Max pall > 0`, och placerar sandningar transportorsvis utan att dela en lagerplats mellan flera sandningar. Ny `location`-uppladdning raderar den gamla verksamhetsfilen, rensar location-cachen och forvarmer den nya ytlistan direkt. Teststodet omfattar handler-/domantester, API/session/coredata-tester, statiska UI-kontrakt och Playwright-test for att Forecast aktiverar Ytgenerering och skickar `forecast_session_id`.

Allokering anvander nu samma filversionsprincip for snabb upprepad korning: hela outputpaketet med allokerade rader, near-miss, refill och pallplatser cachas per orders-/buffert-/saldo-/item-version. Omradesfiltren for GG/MG sparar ocksa filtrerade kopior per originalfilversion och regel, sa samma resultat ateranvands utan att berakningsresultatet andras.

Synliga vyer for aktuell anvandare forvarms nu gradvis i frontenden via en idle-ko och en kort GET-cache som sparas i sessionen, sa uppvarmningen finns kvar efter sidbyte i samma flik. Uppladdningar har dessutom en separat metadata-cache for IndexedDB-filerna, sa vyn kan visa filrutor direkt och hamta stora blobbar/coredata i bakgrunden. POST/PUT/DELETE rensar GET-cachen, och sena bakgrundssvar ignoreras efter en sadan andring, sa ny uppladdad/raderad data tvingar ny hamtning.

`tools.performance_benchmark` mater nu kall/varm sidvaxling, bakgrunds-prefetch, Uppladdningar, omradestoggle, schema select/drag/copy, Dela-korningar och Excel-importer. Rapporten sparas som JSON under `artifacts/performance/` for fore/efter-jamforelse nar cache eller UX-hastighet andras.

## [2026-05-25] feature | Demo-läge med per-session SQLite-sandbox

flow har fått ett fast `demo`-konto för säljpresentationer. Vid inloggning snapshottas live-databasen till en privat SQLite-fil i temp-mappen och en privat datakatalog skapas. Alla skrivningar routas dit via `get_db()` (engine-byte) och `demo_data_root_var` (filsystem). Vid utloggning raderas SQLite-filen och datakatalogen så nästa demo startar rent. Frontend visar gul/röd `DEMO`-banner och en valbar guidad rundtur genom alla synliga vyer (state via `sessionStorage`). Demo-användaren är låst i Användare-vyn — kan inte tas bort, döpas om eller fråntas admin-rollen, men lösenord/visningsnamn/område kan rotateras. Se [demo-laget](demo-mode.md).

## [2026-05-25] feature | Drag-sortering av personer i planeringsvyer

Bemanning och Oversikt kan nu dra personnamn for att uppdatera personernas `sort_order` i Personer. Ny behorighet `personSortOrder` visas som Personsortering i Vybehorigheter och backend kraver Bemanningsansvarig/admin/Super User, `edit`-atkomst, anvandaromrade och samma hemomrade pa personerna.

## [2026-05-25] change | Bearbeta-matris far egen behorighet

Matris-knappen i Bearbeta styrs nu av `allocationProcessMatrix`: `view` kan oppna matrisen lasande och `edit` kan spara. Admin har `edit` som standard och Super User har fortsatt alltid full atkomst.

## [2026-05-25] feature | Redigerbar Bearbeta-matris

Bearbeta har nu knappen `Matris` for roller med `allocationProcessMatrix=view`; `allocationProcessMatrix=edit` kravs for att spara. Matrisen sparas globalt som `allocation_process_matrix` och styr per toggle bade radfilter (`Bolag`, exkluderade kundnummer) och vilka Bearbeta-funktioner som syns. Standard ar fortsatt GG=`Bolag GG` utan kund 6005, MG=`Bolag MG` utan 40002/90002 och ovriga toggles ser allt.

## [2026-05-25] fix | Lagerverktyg foljer verksamhetstoggle

Super User styr nu lagerverktygens verksamhet via sidebarens omradestoggle. Buffertpall-observations, verksamhetens `artikel_max.csv` och Bearbetas coredata-defaults anvander R3 nar togglen star pa R3 och Stigamo nar togglen star pa ett Stigamo-omrade; `∞` faller tillbaka till kontots egen verksamhet.

## [2026-05-25] fix | Vybehorigheter ar globala

Rollernas `Vybehorigheter` laser och sparar nu en global matris i stallet for en separat matris per verksamhet. Det gor att exempelvis `Lagerkontorist = Bearbeta/Redigera` galler bade Stigamo och R3, medan verksamhetsspecifika settings som cell-lasning och menyordning fortsatt kan vara separata.

## [2026-05-25] feature | Coredata-karnfiler ar verksamhetsseparerade

Filerna under `data/coredata/` hanteras nu per verksamhet for prefixen `custom`, `dimension`, `item`, `item_alias`, `item_attribute`, `item_option`, `kpi_target_rule`, `location`, `location_cost`, `pallet_type` och `v_ask_kpi_target`. `artikel_max.csv` visas i samma karnfilslista och sparas till lagerverktygens verksamhetsspecifika artikel_max-sokvag. Ny uppladdning ersatter bara gammal fil med samma prefix i anvandarens egen verksamhet. Allokering anvander dessutom verksamhetens `item_option` som karnfil nar ingen lokal Item option-fil laddats upp.

## [2026-05-25] fix | Verksamhetsseparerar produktivitetens KPI-karnfil

Produktivitetens permanenta KPI-mal (`v_ask_kpi_target*.csv`) sparas och lases nu per verksamhet, pa samma princip som lagerverktygens `artikel_max.csv`. Stigamo, R3 och nya verksamheter far separata kataloger under `data/coredata/`; Stigamo har en bakatkompatibel fallback till den gamla root-filen tills en Stigamo-scopead KPI-fil finns.

## [2026-05-25] fix | Produktivitet foljer vybehorigheter

Produktivitetssidan kraver inte langre hard Super User-flagga i frontend. Sidan och API:t styrs av `productivity=view` for lasning och `productivity=edit` for serverhanterade produktivitetsfiler, sa admin kan ge atkomst via Vybehorigheter utan att ge Super User-roll.

## [2026-05-25] fix | Bearbeta följer vybehörigheter

Bearbeta använder nu samma `allocationProcess=edit`-behörighet i backend som i menyn. Det gör att exempelvis Lagerkontorist kan se och köra Bearbeta när rollen satts till Redigera i Vybehörigheter. Utan edit-behörighet visas fortsatt bara självserviceflöden som Dela.

## [2026-05-25] change | Anvandare ar alltid aktiva

Anvandare-sidan har inte langre aktiv/inaktiv-lage, aktiv-kolumn eller "Visa inaktiva". Alla konton halls aktiva av backend och gamla inaktiva rader backfylls via migration/bootstrap. Konton som inte ska finnas kvar tas bort via `DELETE /api/users/{user_id}`; backend skyddar eget konto och sista admin samt nollar gamla anvandarreferenser innan hard delete.

## [2026-05-25] change | Verksamhetsseparerar observations

Lagerverktygens buffertpall-observations och `artikel_max.csv` ar nu separata per verksamhet. Stigamo behaller legacy-filerna medan R3 skriver och laser under `warehouse_tools/vendor/lowfreqdata/buffertpall/r3/`; Ordersaldo, LYX och Pafyllnadsprio anvander verksamhetens karnfil nar egen fil inte laddas upp.

## [2026-05-25] fix | Bevarar lagerverktygens arbetslage vid vybyte

Bearbeta och Dela sparar nu faltvarden, status och senaste resultatpreview per inloggad anvandare i aktuell browser-/desktop-session. Nar anvandaren byter till en annan vy och gar tillbaka finns Allokering, Dela varden och andra lagerfloden kvar visuellt; serverns temporara `session_id` kravs fortfarande for Excel/CSV/kolumnhamtning.

## [2026-05-25] change | Allokering ignorerar orderstatus over 33

Lagerverktygets Allokering filtrerar nu bort orderrader med status over 33 innan pallmatchning, i bade Flow och den vendrade Allokera-motorn. Buffertstatusreglerna ar oforandrade: 29/30/32 for allokering och 29/30 for refill.

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

## [2026-05-25] change | GG/MG-filter i Bearbeta

Bearbeta skickar nu aktuell omradestoggle till `/api/allokering/flow/*`. Backend filtrerar tabellfiler per korning for GG (`Bolag=GG`, exkl. kundnr `6005`) och MG (`Bolag=MG`, exkl. kundnr `40002` och `90002`) nar filen har Bolag-/Kundnr-kolumner. Ovriga toggles ser hela underlaget. Frontenden har en processmatris for framtida flodessynlighet per toggle.

## [2026-05-25] polish | Markerar krav i Flera nya-dialoger

Direktimporttabellerna for Personer, Aktiviteter och Anvandare visar nu `Obligatoriskt` eller `Frivilligt` i varje kolumnrubrik. Den gemensamma bulkimportkomponenten markerar omarkta kolumner som frivilliga som fallback, sa framtida `Flera nya ...`-dialoger inte blir utan faltstatus.

## [2026-05-25] fix | Rensa alla bevarar karnfiler

`Rensa alla` i Uppladdningar tar nu bara bort vanliga lokala filval. Skyddade karnposter som `artikel_max.csv`, coredata-nycklar och KPI-mal bevaras i IndexedDB/serverstatus, och anvandartexten sager att karnfiler ligger kvar.

## [2026-05-25] polish | Synlig dokumentlogg for fler floden

Dokumentloggen i sidebaren sparas nu i browsersessionen, foljer med mellan vyer och kan rensas. `api.js` loggar anvandarnara success/failure for mutationer och nedladdningar, bakgrundsladdning varnar vid misslyckad forvarmning och Bearbeta-floden med egen fetch-wrapper skriver tydligare lyckat-/felstatus. Agents/wiki/testprotokoll har uppdaterats sa nya funktioner maste ta med synlig loggning, audit och teststod.

## [2026-05-26] polish | Vectorikoner for webb och desktop

Webben anvander nu SVG for favicon och brandlogga, med PNG/ICO kvar som fallback for plattformar som kraver raster. Desktop-fonstret foredrar `flow_icon.svg`, medan `.ico` fortfarande finns kvar for exe-/genvagsikon och fallback i Windows-bygget.

## [2026-05-26] fix | Ogiltigt omradesfokus faller tillbaka

Bemanning och Oversikt friskar nu upp den gemensamma omradestogglen fran sidans egna `/api/areas`-svar och validerar sparade `AREA:<id>` mot aktuella aktiva omraden. Om ett omrade raderats medan en browserflik hade det valt faller fokus tillbaka till Alla i stallet for att skicka dod `area_id` och visa 404/tom vy.

## [2026-05-31] polish | Hogerklicksmeny for omradesfokus

Sidebarens omradestoggle har nu en hogerklicksmeny for direkt val av omrade. Menyn anvander samma `/api/areas`-scope som ovriga vyer: vanliga anvandare ser omraden i egen verksamhet, medan Super User ser alla aktiva omraden och globalt `∞`.

## [2026-05-31] feature | Publik meta-uppladdning

Lade till `/meta` och `meta-upload.html` som en fristaende publik mobilvy utan sidebar och utan inloggning. Anvandaren kan valja flera bilder/videor pa Android, iPhone eller desktop och ladda upp dem till `POST /api/meta/uploads`; backend sparar varje fil i `meta_media_uploads` med gemensamt batch-id och status `pending_analysis` for senare LLM-analys.

## [2026-05-31] feature | Meta-progress och Super User-vy

Meta-uppladdningen visar nu total progress, kvarvarande mangd och status per fil under pagaende uppladdning. Backend sparar nya meta-filer med tidsstamplat `stored_filename`, och Super User far sidebarvyn `Meta` dar alla uppladdade bilder/videor kan listas, filtreras och visas via skyddade `/api/meta/uploads`-endpoints.

## [2026-05-31] feature | Stoppa dubbletter i Meta

Meta-uppladdningen beraknar nu SHA-256 `content_hash` for varje bild/video och sparar inte exakta dubbletter igen. Migrationen fyller hash for befintliga meta-rader och tar bort duplicate blobbar innan ett unikt index skapas; uppladdningssvaret visar `skipped_count` sa anvandaren ser hur manga dubbletter som hoppades over.

## [2026-05-31] feature | Meta-nedladdning och radering

Super User-vyn `Meta` visar nu knappen `Ladda ner` i stallet for `Oppna` och har en ny `Radera`-knapp per mediafil. Radering gar via `DELETE /api/meta/uploads/{upload_id}`, tar bort raden/blobben och audit-loggar metadata utan filinnehall.

## [2026-05-31] feature | Gemini-analys for Meta-videor

Meta skapar nu sändningsrader for uppladdade videor i `meta_shipment_observations` med video-hash, radhash, ordernummer, användarnamn, kund, pall-id, avvikelser, videolank och eventuell etikettstillbild. Backend kan använda `GEMINI_API_KEY` och standardmodellen `gemini-2.5-pro` for att analysera både video och ljud; osäkra svar hamnar i manuell kontroll i Meta-vyn.

## [2026-05-31] feature | Meta Video-ID och videolangd

Meta-vyn visar nu samma korta Video-ID i sändningstabellen och i videokorten, plus videons langd i tabellen, korten och den publika filväljaren nar metadata kan lasas. Backend sparar `duration_seconds` for nya videos nar `ffprobe` finns, och frontenden kan fylla i langden via browserns videometadata for befintliga uppladdningar. Media-korten har kompakta ikonknappar sa Visa, Ladda ner och Radera far plats pa samma rad.

## [2026-06-01] feature | Automatisk Meta-uppladdning

Den publika Meta-uppladdningen startar nu direkt nar anvandaren valt eller dragit in filer. Den separata `Ladda upp`-knappen ar borttagen, medan progress, kvarvarande mangd, per-filstatus, dubblettbesked och felmeddelanden fortsatter visas pa samma sida.

## [2026-06-01] change | NoMan kravs for nya personer

Personregistret kraver nu `NoMan` nar en ny person skapas via modal, direktimport eller Excelimport. Personvyn visar toasten `NoMan kravs` vid tomt falt, importresultat visar radfelet `NoMan saknas`, och backend stoppar nya personer utan NoMan samt rensning av ett redan satt NoMan-varde.

## [2026-06-01] polish | Verksamhet i Personer

Personregistret visar nu kolumnen `Verksamhet` mellan NoMan och Hemomrade. Kolumnen kan sorteras och filtreras, anvander personens `business_id` mot verksamhetslistan eller aktuell anvandares verksamhet, och visar `Utan verksamhet` for gamla rader som saknar verksamhet.

## [2026-06-01] feature | Per-verksamhet infinity och inline Verksamheter

Verksamheters `∞`-lage styrs nu av ett aktivt omrade med kod `ANNAT` i respektive verksamhet, i stallet for en hardkodad Stigamo-regel. Verksamheter-vyn har fatt `Lagg till ∞`, klickbara celler for kod/namn/sortering/aktiv-status och rubriksortering for bade verksamheter och omraden.

## [2026-06-01] feature | Meta sändningsnummer från etiketter

Meta-analysen har fått `shipment_number`/sändningsnummer i `meta_shipment_observations`, API-svaret och Super User-tabellen. Gemini-prompten beskriver nu både transportetikett och innehållsförteckning: `Sändnings-ID` på transportetiketten blir sändningsnummer, `Avs. ref.` kan bli ordernummer, `Godsmärks`/`Box ID` kan bli pall-id och innehållsförteckningens ordernummerlista kan användas när den är tydligare. `record_hash` räknas om med sändningsnummer så tabellraden fortsatt kopplas till rätt video och etikettdata.

## [2026-06-01] fix | Scrollbar omradestoggle

Sidebarens omradesmeny kan nu scrollas utan att stangas. `common.js` ignorerar scroll-event som kommer fran sjalva `.area-focus-menu`, stoppar klick/scroll inne i menyn fran att trigga dokumentets utanfor-klick och behaller stangning vid sidscroll, resize, Escape eller klick utanfor.

## [2026-06-01] feature | Appzoom i sidebar

Sidebaren har fatt en global zoomkontroll mellan hamburgaren och menyredigering. Kontrollen visas nu som tva forstoringsglas med minus/plus utan siffra i mitten. Zoomnivan sparas lokalt i `flow-app-zoom`, styr hela appytan i bade webb och Windows-app och kan aven andras med `Ctrl+-`, `Ctrl++`, `Ctrl+0` och `Ctrl+scroll`. Alla skyddade HTML-sidor har ny cache-bust for `common.js`.

## [2026-06-01] polish | Loggikon visar nya loggrader

Dokument-/loggikonen i sidebaren visar nu en badge med antal nya loggrader i aktuell session, på samma sätt som uppladdningsikonen visar antal uppladdningar. Räknaren sparas i `sessionStorage`, följer med vid sidbyte och nollas när användaren öppnar eller rensar loggpanelen.

## [2026-06-01] fix | Rensa alla stoppar gammal produktivitetssynk

Uppladdningars `Rensa alla` markerar nu en ny rensningsgeneration. Produktivitetens bakgrundssynk skickar med den generationen när loggfiler speglas till Uppladdningar, och en gammal synk som startade före rensningen får inte skriva tillbaka exempelvis `Palllastningslogg` efter att användaren rensat filerna.

## [2026-06-01] fix | Forecast undviker sklearn get_params-fel

Forecastens paketerade LightGBM-/XGBoost-artefakt predikterar nu via underliggande boosterobjekt i stallet for sklearn-wrapperns `predict`. Det gor att Bearbeta/Forecast inte faller pa miljoer dar wrapperns `get_params` ger felet `'super' object has no attribute 'get_params'`.

## [2026-06-01] feature | Forecast visar Ytgenerering som nasta steg

Forecast-resultatet i Bearbeta visar nu en foljdknapp `Kor Ytgenerering` direkt i resultatpanelen. Knappen anvander samma readiness-regler som den vanliga Ytgenerering-knappen, skickar vidare `forecast_session_id` och gor kedjan Forecast -> Ytgenerering tydligare utan att anvandaren maste leta i flodeskartan.

## [2026-06-01] feature | MG begransar Ytgenerering till UTL205-UTL652

Ytgenereringens Bearbeta-korning far nu vald omradestoggle vidare till flodeshandlern. Nar togglen ar MG filtreras lagerplatsunderlaget efter den vanliga Typ U/Max pall-regeln och darefter till UTL205-UTL652, medan andra toggles fortsatt kan anvanda UTL1-UTL652.

## [2026-06-01] feature | Bearbeta-matris styr UTL for Ytgenerering

Bearbeta-matrisen har nu ett globalt `Ytgenerering UTL`-intervall per toggle. Intervallet sparas i `allocation_process_matrix`, visas som `Fran`/`Till` i matrisdialogen och skickas till Ytgenerering vid korning sa varje toggle kan styra vilka UTL-ytor som raknas. Standard ar MG UTL205-UTL652 och ovriga toggles UTL1-UTL652.

## [2026-06-01] feature | Ytgenerering visar interaktiv ytkarta

Ytgenerering-resultatet skickar nu med en kartpayload byggd fran Flow-placeringarna och sparade Flow-koordinater. Bearbeta visar kartan som ett stort resultatblock med pan/zoom/rotation/fullskarm, drag for att flytta eller byta UTL-placeringar, kapacitetsvarningar samt lokala nedladdningar for justerad karta-CSV och justerad ASK-import.

## [2026-06-01] feature | Coredata sparas i Postgres

Nya coredata-karnfiler sparas nu i Postgres-tabellen `coredata_files` med unik rad per verksamhet och filtyp. Backend later DB-raden vinna over gamla filer, men kan fortfarande lasa `data/coredata/` som fallback tills en filtyp laddats upp igen. Bearbeta och Produktivitet materialiserar DB-raden till en temporar backendfil nar berakningsmotorerna behover en CSV-sokvag, sa webb och Windows-app delar samma centrala sanning.

## [2026-06-01] feature | Nya karnfilstyper for dispatch och transportor

Uppladdningar kanner nu igen `dispatch_template-*.csv` som karnfilstypen `dispatch_template` och `trans_agency-*.csv` som karnfilstypen `trans_agency`. Bada visas bland permanenta karnfiler, skyddas vid `Rensa alla` och sparas i Postgres per verksamhet pa samma satt som ovrig coredata.

## [2026-06-01] fix | Publika Meta-fel syns i Felkoder

Publika Meta-uppladdningar loggar nu misslyckade backend-forsok som `meta_media_upload/upload_failed`, aven utan inloggad anvandare. Auditpayloaden ar sanerad till metod, path, HTTP-status, feltyp, antal valda/accepterade/overhoppade filer och total uppladdad storlek, utan filnamn eller filinnehall. Den publika XHR-klienten visar dessutom backendens feltext nar den finns i svaret.

## [2026-06-01] fix | Meta laddar upp manga filer stegvis

Den publika Meta-uppladdningen later anvandaren valja manga bilder/videor pa en gang men skickar dem nu en och en till `/api/meta/uploads`. Total progress och per-filstatus finns kvar, dubbletter summeras fortsatt, videolangd lases sekventiellt, och om en fil misslyckas markeras den som `Fel` medan klienten fortsatter med nasta fil.

## [2026-06-01] feature | Transportorskluster styr Ytgenerering

Forecast laser nu verksamhetens `trans_agency`-karnfil som transportorskluster och skickar klustren som `carrier_clusters` i Forecast-sessionen. Forecast-resultatet visar `Redigera kluster`, dar anvandaren kan andra kluster, UTL-fran/till och ordning innan `Kor Ytgenerering`. Ytgenerering tar emot den redigerade `carrier_clusters_json`, grupperar transportorer med samma `cluster_group` och placerar sandningar inom respektive klusters UTL-intervall innan kartan visas.

## [2026-06-01] fix | Forecast ignorerar orderstatus 11

Forecast filtrerar nu orderoversikten sa hela ordernumret ignoreras om nagon orderhuvudrad for samma `Ordernr` har `Status=11`, oavsett om en annan rad/snapshot har annan status. Det gor att matchande rader i Detalj Kundorder ocksa faller bort nar Forecast inner-joinar orderdetaljer mot orderoversikten, sa stoppade/avvikande status-11-ordrar inte skapar sandningar eller pallplatsprognos.

## [2026-06-01] feature | Kortkommandon i Ytgenerering-kartan

Ytgenerering-kartan i Bearbeta kan nu fa fokus och hanterar `Ctrl+C`, `Ctrl+X`, `Ctrl+V` och `Ctrl+Z` for att kopiera/klippa vald placering, klistra in den pa vald UTL-yta och angra senaste kartandringen. Kortkommandona anvander samma flytt-/byteslogik som drag i kartan och visar toastar nar anvandaren kopierar, klipper, klistrar in eller angrar.

## [2026-06-01] fix | Klusterknapp visas utan trans_agency-rader

Forecast-resultatet bygger nu en redigerbar klusterlista fran Forecast-tabellens unika transportorer nar `carrier_clusters` saknas i svaret. Det gor att `Redigera kluster` visas aven om transportorsfilen inte gav klusterrader, och sparade andringar skickas fortsatt som `carrier_clusters_json` till Ytgenerering.

## [2026-06-01] fix | Svenska tecken i Ytgenerering-kartan

Ytgenerering-kartans knappar, sökfält, detaljrad, översikt, toastar och justerade karta-CSV använder nu svenska tecken i texter som `Återställ vy`, `Fullskärm`, `Sök UTL, sändning eller transportör`, `Över kapacitet`, `Sändningsnr` och `Transportör`.

## [2026-06-01] fix | Kärnfiler blir serverns sanning

Kärnfiluppladdningar känner nu igen `location-...`, `lagerplats-...` och `lagerplatser-...` som samma `location`-underlag. När en ny kärnfil sparas i databasen tas äldre lokala fallbackfiler för samma verksamhet och filtyp bort, och Uppladdningar läser kärnfilstatus från servern utan GET-cache så gamla lokala filer inte kan se ut som sanning.

## [2026-06-01] fix | Bemanning visar lånade personer per aktivitetsområde

Bemanningens områdesfilter visar nu en person i valt område om personen antingen har hemområdet där eller har en schemacell samma dag med en aktivitet som tillhör området. Summeringen räknar lånade personer på de explicita cellerna i valt område utan att dra med personens hemområdesmall till fel områdessummering.

## [2026-06-01] feature | Ytgenerering: kundnamn, klusterfärger och saknade kunder

Ytgenerering-kartan visar nu kundnamn (största kunden per sändning) som huvudtext på ytorna med en vit kontrast-halo för bättre läsbarhet. Forecast-tabellen får en `Kundnamn`-kolumn och kartans payload bär `customer`/`customerNum` per placering och i listan över ej placerade sändningar. Färgen baseras på transportör men ett kluster delar basnyans och varje transportör i klustret får en egen ljushet (`allocationClusterColorMap`). Kluster-editorn (`Redigera kluster`) har drag-sortering, ASN/Arrive/Depart, Group, Start/End seq och färgväljare; tiderna seedas med standardvärden och sparas i `carrier_clusters`. En `Saknade kunder`-panel listar ej placerade sändningar.

## [2026-06-01] feature | Uppladdningar kan forhandsvisa filer

Denna historiska andring lade till `Visa` for filrader. Funktionen ersattes 2026-06-04 av explicita download/open-atgarder, sa dagens Uppladdningar forhandsvisar inte langre filinnehall.

## [2026-06-01] feature | Installningar for Ytgenereringens ytkarta

Bearbeta har nu knappen `Installningar` for roller med `allocationProcessMatrix=view`, med sparande for `allocationProcessMatrix=edit`. Dialogen visar Ytgenereringens UTL-karta som en redigerbar SVG: anvandaren kan dra ytor, andra koordinater/storlek/max pall och lagga till en hel UTL-serie som autoplaceras fran vald yta. Sparade ytor lagras globalt som `ytgenerering_map_layout`, anvands av Ytgenerering for koordinater och kapacitet, och kan komplettera saknade `Typ=U`-platser inom UTL1-UTL652. Om ingen ytkarta ar sparad anvands standardkoordinaterna bara for visualisering.

## [2026-06-01] polish | Fullskarm ar kartikon

Ytgenereringens fullskarmskontroll ar flyttad fran verktygsradens textknapp till en liten ikon i kartans ovre hogra horn. Export- och vyknapparna ligger kvar ovanfor kartan.

## [2026-06-01] fix | Sidolista kopierar sandningsnummer

Ytgenerering-kartans sidolista kopierar nu radens sandningsnummer till urklipp nar anvandaren klickar pa raden, aven nar listan visar kundnamn eller transportor i stallet for sifferstrangen.

## [2026-06-01] fix | AllocationSettings ar separat behorighet

`allocationSettings` raknas inte langre som generell lagerverktygsatkomst. Vanlig admin kan fortsatt ha settings-/matrisbehorighet via vyregler, men `require_allocation_tools_user` kraver fortfarande Lagerkontorist, Artikelplacerare eller Super User for de vanliga lagerverktygen.

## [2026-06-02] feature | Personliga schema- och produktivitetsvyer

Flow har nu rollen `person`, vyerna `Mitt schema` och `Min produktivitet` samt `/api/personal/...`-endpoints. En person kan logga in med sitt `noman`-namn; om anvandaren saknas skapas kontot automatiskt med `person_id`, verksamhet och hemomrade fran personregistret och skickas till forsta losenord. Personrollen ser bara sin egen vy, medan Super User kan valja person i rullista.

## [2026-06-04] feature | Meta-analys anvander bara rost

Meta-videoanalysen extraherar nu en temporar ljudfil fran videon och skickar bara rosten till Gemini. Analysen fyller ett tydligast hort pall-id och avvikelser, medan ordernummer, sandningsnummer, anvandarnamn och kund lamnas tomma tills de kan hamtas via pall-id fran uppladdad data. Autoanalys ar fortsatt ko-ad med en video i taget, delay/spacing-settings och best-effort stillbild fran video.

## [2026-06-04] fix | Meta-video laddas ner som video

Meta-uppladdningar normaliserar nu videoandelse + ljud-MIME, till exempel `.mp4` med `audio/mp4`, till video-MIME vid sparande. Content-endpointen normaliserar ocksa befintliga rader vid streaming, sa live-rader som sparats med fel MIME laddas ner och spelas som video.

## [2026-06-04] fix | Meta-videopil laddar spelbar MP4

Videopilen i Meta-analystabellen anvander nu `variant=playable` pa content-endpointen. Backend transkodar da temporart originalvideon till H.264/AAC-MP4 och raderar tempfilen efter svaret, sa filmer fran Meta-glasogon som annars bara ger ljudikon i Windows Media Player kan ses utan att originalfilen skrivs over.

## [2026-06-04] feature | Meta-uppladdning koar obegransat klientval

Meta-uppladdningssidan later anvandaren valja hela filkon pa en gang och visar total progress med aktuell fil, filnummer, kvarvarande mangd och ETA. Klienten skickar fortsatt en fil per request och backend streamar varje fil i chunks till MediaStore, sa langa koer inte kraver att hela batchen ligger i RAM. Standard-rate-limit for Meta-uppladdning ar avstangd for att sekventiella koer inte ska stoppas efter ett visst antal filer per minut.

## [2026-06-04] feature | Historik far interaction-tracking

Historik har nu ett separat `user_interaction_events`-lager bredvid audit och vantetider. Webben batchar klick, submit, change/contextmenu, API-resultat, nedladdningar och semantiska Bearbeta-events via `flowTrack`; desktop markerar `client_surface=desktop` och trackar appstart, lokala filval och update-floden. Historik har nya lagen Funktioner, Knappar, Kolumner, Floden och AI-analys med endpoints for raw events, summary, coverage och MiniMax-fragor. Backend sanerar payloaden och `TRACKING_ALLOW_VALUE_SAMPLES=false` strippar klartextprover som default; secrets, filnamn, filvagar, privata URL:er, request bodies och provider-detaljer far aldrig sparas.

## [2026-06-04] test | Interaction-tracking far browserkontrakt

Trackinglagret har nu Playwright-tester for auto-capture av klick/change/submit, API-koppling, nedladdning/export, Historik-dashboardens Funktioner/Knappar/Kolumner/Floden, Historik-AI och desktop-surface. Tester fangade och skyddar att interna download-lankar ignoreras av auto-tracking, att Pafyllnadsprio copy-patterns anvander `copy_mode`, och att kanda kontroll-id:n i coverage matchar frontendens faktiska id:n.

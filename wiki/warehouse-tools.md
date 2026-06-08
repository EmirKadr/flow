---
title: Lagerverktyg
status: aktiv
updated: 2026-06-08
tags: [lagerverktyg, allokering, filer, ui]
---

# Lagerverktyg

Kort svar: Lagerverktygen ar fyra vyer ovanpa `warehouse_tools`: Uppladdningar for filval, Bearbeta for floden, Installningar for lager-/ytkarta och Dela for listdelning. I webben sparas vanliga filval i IndexedDB och skickas som uploads nar servern behover dem. I Windows-appen sparas i stallet lokala filreferenser for Bearbeta/Produktivitet, och den lokala desktop-servern kor berakningarna mot filerna pa disk. Ovriga vyer fortsatter ga mot central server. Bearbeta och Dela behaller faltvarden, status och senaste resultat i aktuell browser-/desktop-session nar anvandaren byter vy och kommer tillbaka.

## Vyer

| Vy | Fil | Syfte | Behorighet |
| --- | --- | --- | --- |
| Uppladdningar | `uppladdningar.html` | Lagg in ASK/WMS/Excel-filer i lokalt filpool | `allocationUploads` |
| Bearbeta | `bearbeta.html` | Kor kombinerade lagerfloden som Allokering, Ordersaldo, kontroller | `allocationProcess` |
| Installningar | `installningar.html` | Bygg vidare Ytgenereringens UTL-karta och kapacitet | `allocationSettings` |
| Dela | `dela.html` | Dela lang lista i kolumner | `allocationSplit` |

## Gemensamma filkontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Valj filer | Valjer en eller flera filer | Webben identifierar filtyp och sparar filen i IndexedDB; Windows registrerar lokal path som `localRef` med metadata | `routeAllocationFiles`, `DesktopFileBridge` | Okand filtyp om namn/header inte matchar. |
| Drag-drop | Drar filer till panel/slot/flode | Samma som Valj filer, med fallback till slot. I Windows registreras filerna snabbt och tung sync sker koat | `routeAllocationFiles` | Om flera filer okanda visas toast "Kunde inte sortera". |
| Välj per slot | Valjer fil for en specifik slot | Forsoker detektera men fallbackar till sloten | `fallbackSlotKey` | Bra nar automatisk identifiering missar. |
| Ladda ner/Oppna | Klickar explicit filatgard | Webben laddar ned sparad fil forst vid klick; Windows oppnar lokal fil eller mapp via desktop bridge | `data-download-*`, `/api/desktop/files/{ref}/open` | Ingen fil hamtas eller lases i forvag bara for att listan visas. |
| X per slot | Rensar slot | Tar bort lokal IndexedDB-post eller lokal referens | `deleteAllocationFile` | Sammanstalld data som `artikel_max.csv` kan laddas ned utan att vara uppladdad i sessionen. |
| Rensa alla | Rensar vanliga lokala filval | Tar bort icke-skyddade filer ur allokerings- och produktivitetsstores, stoppar gammal produktivitetssynk fran att skriva tillbaka rensade loggar, men bevarar karnfiler, sammanstalld data som `artikel_max.csv` och KPI-mal | `clearAllUploadedFiles`, `syncAllocationUploadsFromStore` | Bekraftelse sager att karnfiler och sammanstalld data ligger kvar. |
| Uppladdningsbadge | Visar antal nya filer | Lagrar notice i sessionStorage | `allocationUploadActivity` | Badge rensas nar Uppladdningar oppnas. |

## Karnfiler och sammanstalld data

Uppladdningar visar separata listor for permanenta karnfiler och sammanstalld data. Vanliga filrader visar alltid det svenska vy-/slotnamnet fran filkunskapens `label_sv` som fet rubrik, sa tekniska alias som `customer_order_details_all` visas som `Detalj Kundorder (Alla)` och `v_ask_booking_putaway` visas som `Ej Inlagrade Artiklar`. Prognosfil, Kampanjfil och Textfil med varden ar Flow-egna namn och normaliseras inte mot filkunskapen. `artikel_max.csv` ar sammanstalld data och uppdaterar samma verksamhetsfil som Ordersaldo, LYX och Pafyllnadsprio anvander. Produktivitetens tre sammanstallda loggfiler visas ocksa har: `productivity_pick_observations`, `productivity_trans_observations` och `productivity_pallet_observations`. Coredata-prefixen `custom`, `dimension`, `dispatch_template`, `item`, `item_alias`, `item_attribute`, `item_option`, `item_security_info`, `kpi_target_rule`, `location`, `location_cost`, `pallet_type` och `trans_agency` sparas som blobbar i Postgres-tabellen `coredata_files` med unik nyckel per verksamhet och filtyp. `trans_agency` ar transportors-/agency-karnfilen och kan aven laddas upp med filnamn som borjar pa `transportorer`, `transportor` eller `agency`. Om en anvandare laddar upp en ny fil med samma prefix for sin verksamhet ersatts DB-raden och den nya blir sanningen for alla anvandare i verksamheten. Andra verksamheters filer rors inte. Gamla filer under `data/coredata/<verksamhetskod>/` kan fortfarande lasas som fallback tills de laddas upp igen.

Uppladdningar forhandsvisar inte langre filinnehall. Fyllda filrader visar bara metadata och explicita atgarder: `Ladda ner` for web/serverlagrade filer och `Oppna fil`/`Mapp` for Windows-local refs. Det gor att listan kan visas utan att ladda ned eller lasa alla filer i forvag.

Allokering anvander verksamhetens `item_option`-karnfil nar anvandaren inte laddat upp en egen Item Option-fil. En uppladdad lokal fil i sloten vinner for den korningen, men den permanenta karnfilen ligger kvar som verksamhetens fallback.

Forecast anvander verksamhetens karnfiler `custom`, `item`, `item_alias`, `dimension`, `pallet_type`, `item_option` och den frivilliga transportorsfilen `trans_agency` som standard. Ytgenerering anvander verksamhetens `location` som lagerplatsunderlag. Anvandaren kan fortfarande ladda upp egna lokala filer for en korning nar flodet har en motsvarande filslot, men karnfilen ligger kvar som verksamhetens fallback.

Godsdeklaration anvander verksamhetens `item_security_info` som artikelns farligt gods-underlag. En ny uppladdad `item_security_info-*.csv` ersatter tidigare `item_security_info` for samma verksamhet pa samma satt som andra karnfiler.

Nar en slot redan har verksamhetens karnfil eller sammanstallda data, till exempel `item_option` eller `artikel_max.csv`, visas den i respektive permanent lista i stallet for att dubbelvisas i Filer. Om anvandaren laddar upp en lokal override i sessionen visas sloten i Filer igen.

`Rensa alla` i Uppladdningar tar bara bort vanliga lokala filval. Permanenta karnfiler, sammanstalld data och skyddade poster ligger kvar, sa anvandaren kan rensa order-/buffert-/loggfiler utan att tappa verksamhetens standardunderlag. Om en bakgrundssynk fran Produktivitet redan ar igang ignoreras dess gamla filkopior efter rensningen, sa till exempel Pallastningslogg inte dyker upp igen.

Produktivitetens sammanstallda loggar skapas nar Plocklogg Full, Translogg eller Pallastningslogg laddas upp i Produktivitet. Plocklogg Full tar bara in nya `Radid` (kolumn-id `rowid`) och Translogg tar bara in nya `Rowid`; Pallastningslogg tar bara in rader nyare an senaste `Andrad`/`timestamp` i den befintliga csv.gz-filen. I produktion skrivs de verksamhetsscopeade csv.gz-filerna till persistent disk via `PRODUCTIVITY_DATA_DIR` eller `MEDIA_STORE_ROOT/flow-data`, inte till repot. Lokalt/dev kan fortfarande falla tillbaka till gamla `data/coredata`-vagar.

## API-first for Bearbeta

Bearbeta hamtar nu flera vanliga underlag direkt fran extern datakalla nar anvandaren klickar pa flodesknappen. Det galler bade webb och Windows, men Windows gar via den centrala serverns `/api/workflow-data/source` sa den lokala appen inte behover privata API-detaljer. Endpointen anvander flodets behorighet (`allocationProcess`) och inte `dataFetch`.

API-kallan vinner alltid for API-preferred slots. Om extern datakalla inte kan nas, katalogen saknas eller API-svaret ar ogiltigt anvands befintlig uppladdad fil eller Windows `localRef` som fallback. Om varken API eller fallback finns stoppas flodet med en begriplig text, till exempel `Extern datakalla kunde inte nas... Ladda upp Saldo Inkl. Automation och kor igen.` Resultatloggen och Historik/audit markerar varje kallstatus som `api`, `upload_fallback`, `local_ref_fallback`, `missing` eller `optional_skipped`, men sparar inte URL:er, headers, nycklar, request bodies, filnamn, lokala sokvagar eller raddata.

API-first-kartor:

- `buffer` -> `v_ask_article_buffertpallet`.
- `saldo` -> `v_ask_item_summary_stock_automation`, med gamla rubrikalias som `Robot`, `Saldo autoplock`, `Plocksaldo` och `Plockplats`. Om API-rader saknar `robot_ind` underkanns API-saldot och fallback anvands.
- `orders`/`details` -> `v_ask_customer_order_details_all`.
- `overview` -> `v_ask_order_overview`.
- `dispatch` -> `v_ask_dispatch_pallet`.
- `custom_adr` -> `v_ask_custom_adr`.
- `not_putaway` -> `v_ask_booking_putaway`.
- karnfiler som `custom`, `item`, `item_alias`, `dimension`, `pallet_type`, `item_option`, `trans_agency`, `location` och `item_security_info` kan hamtas API-first nar flodet kraver dem.

## Bearbeta-floden

Bearbeta ar en egen sidebar-vy (`bearbeta.html`). Den ska inte beskrivas som en flik inne i Dela. Om anvandaren inte ser Bearbeta i menyn, eller ser vyn men inte kan kora floden, beror det normalt pa att rollen saknar `allocationProcess=edit` i vyatkomst. Vanliga lagerroller ser som standard Uppladdningar och Dela, men kan fa Bearbeta via Vybehorigheter.

Att andra `allocationProcess` eller `Vybehorigheter` kraver admin-/Super User-atkomst till Anvandare/installningar. En vanlig anvandare ska kontakta admin eller Super User, inte sjalv ga till Vybehorigheter.

Bearbeta lyssnar pa sidebarens omradestoggle nar floden kors. Rollen maste ha `allocationProcessMatrix=view` for att se knappen `Matris` i Bearbeta och `allocationProcessMatrix=edit` for att spara matrisandringar. Super User har alltid full atkomst, och admin har `Redigera` som standard. Matrisen oppnar en global Bearbeta-matris dar varje toggle kan fa bolagsfilter, exkluderade kundnummer och en lista over vilka Bearbeta-funktioner som ska synas for togglen. Valet `Alla` betyder att togglen ser alla funktioner. `Installningar` ar en egen sidebar-vy med behorigheten `allocationSettings`; dar kan behoriga anvandare panorera/zooma i Ytgenereringens ytkarta, dra ytor, andra storlek/kapacitet och lagga till ytor fran verksamhetens lediga `Typ=U`-lagerplatser.

Matrisen sparas i appsettings som `allocation_process_matrix` via `GET/PUT /api/allokering/process-matrix`. Ytkartans redigerbara UTL-ytor sparas per verksamhet som `ytgenerering_map_layout` via `GET/PUT /api/allokering/ytgenerering-map-layout`; vald Bearbeta-toggle (`area_focus`) styr vilket business-scope som lases och skrivs. Bada galler for bade webb och desktop eftersom desktop servar samma frontend och API. Standardmatrisen ar:

- GG filtrerar tabellfiler som har Bolag-/Kundnr-kolumner till `Bolag = GG` och exkluderar `Kundnr = 6005`.
- MG filtrerar tabellfiler som har Bolag-/Kundnr-kolumner till `Bolag = MG`, exkluderar `Kundnr = 40002` och `90002`, och later Ytgenerering anvanda UTL205-UTL652.
- Ovriga toggles, inklusive AS, EH, R3 och `∞`, skickar inte nagot radfilter, ser hela underlaget och later Ytgenerering anvanda UTL1-UTL652.

Reglerna normaliseras server-side i `allocation_bridge.normalize_process_matrix` sa de galler alla Bearbeta-floden oavsett vilken filslot som anvands. Ytgenereringens UTL-intervall anges per toggle i matrisen med `Fran`/`Till` och sparas ihop med ovriga regler. Frontendens `ALLOCATION_PROCESS_MATRIX` ar bara fallback/standard om API:t inte kan lasa matrisen. Radfiltrering sker pa temporara kopior per korning; originaluppladdningen i cache/IndexedDB andras inte.

| Flode | Kraver | Resultat |
| --- | --- | --- |
| Allokering | Detalj Kundorder (Alla), Buffertpall; valfritt Saldo Inkl. Automation, Item Option, Ej Inlagrade Artiklar | Allokerade pallar, near-miss, refill, pallplatser |
| Ordersaldo | Detalj Kundorder (Alla); valfritt Saldo Inkl. Automation, verksamhetens `artikel_max.csv` | Kompletta ordrar kopieras automatiskt och underskott visas med Antal pa Helpall |
| LYX-artiklar | Saldofil; valfritt verksamhetens `artikel_max.csv` | Lista LYX-artiklar |
| Pafyllnadsprio | Detalj Kundorder (Alla); valfritt Saldo Inkl. Automation, Orderöversikt, verksamhetens `artikel_max.csv` | Pafyllnadsprio, ev. lastningsfonster |
| HIB-koppling | Detalj Kundorder (Alla), Orderöversikt | Andringar och missade avgangar |
| Orderoversiktkontroll | Orderöversikt; valfritt Detalj Kundorder (Alla) | Sändnings-/HIB-kontroller |
| Dispatchkontroll | Orderöversikt, Dispatchpallar; valfritt Detalj Kundorder (Alla) | Dispatchavvikelser |
| Godsdeklaration | Detalj Kundorder (Alla), Orderöversikt, Alternativ Leveransadress och verksamhetens `item_security_info` | DG-order blir klara direkt, LQ-order blir bara klara vid Gotlandspostnummer 620-624 och klara ordernummer kopieras automatiskt |
| Vecka 27-kontroll | Detalj Kundorder (Alla) | Avvikelser/text |
| Prognosrapport | Prognos eller kampanj, samt Saldo; valfritt Buffert | Prognos vs Autoplock |
| Forecast | Detalj Kundorder (Alla), Orderöversikt, Buffertpall, karnfilerna `custom`, `item`, `item_alias`, `dimension`, `pallet_type`, `item_option` och frivillig `trans_agency` | Forecast per `Sandningsnr`, Excel/CSV-tabell, transportorskluster och sessiondata for Ytgenerering |
| Ytgenerering | Verksamhetens `location` och att Forecast har korts i samma session | Placering av forecastens sandningar pa `Typ=U`-lagerplatser inom vald toggles globala UTL-intervall och transportorsklustrens UTL-intervall, samt interaktiv ytkarta |

Godsdeklaration kopplar orderrader via `Detalj Kundorder.Order nr` till `Orderöversikt.Ordernr`. `Orderöversikt.Alt adress` ar adressnumret som matchas mot `Alternativ Leveransadress.Adr num` tillsammans med kundnumret. Flodet filtrerar forst bort artiklar som saknar `DG` eller `LQ` i `item_security_info.Farligt gods nivå`. DG-rader ar alltid klara. LQ-rader ar bara klara nar den alternativa leveransadressens `Post nr` ligger i Gotlandsintervallet 62000-62499. Resultatet visar `Klara ordernummer`, `Klara rader`, `LQ ej klara` och en liten referenstabell for Gotlands postnummerintervall.

Forecastmotorn ligger fristaende i Flow under `warehouse_tools/mg_forecast/`. Den anvander ingen runtime-sokvag till det gamla forecastprojektet och laddar en paketerad kalibreringsartefakt (`calibration.pkl`) sa Render/prod inte behover lokal raw historik for att prediktera. Nar Forecast laser orderoversikten ignoreras hela ordernumret om nagon orderhuvudrad for samma `Ordernr` har `Status` `11`; forst darefter dedupeas senaste orderhuvud per `Ordernr`. Eftersom orderdetaljerna sedan inner-joinas mot den filtrerade orderoversikten forsvinner aven detaljkundorderrader med samma ordernummer. Prediktionen gar direkt via LightGBM-/XGBoost-boosterobjekten i artefakten, sa sklearn-wrapperns `get_params`-vag inte kan stoppa Forecast i miljoer dar wrappern och sklearn skiljer sig. Forecast-tabellen far ocksa en `Kundnamn`-kolumn med den dominanta kunden per sandning (storst andel pallplatser), som Ytgenerering anvander for kundetiketterna pa kartan. Forecast-resultatet sparas som temporar tabellfil i serversessionen, och Ytgenerering laser in filen via session-id nar foljdflodet kors. Backend skapar inte langre en full `forecast_json`-kopia av alla rader bredvid tabellen; det haller serverminnet lagre efter stora Forecast-korningar. Om Forecast far `trans_agency` med kolumner som `agency_alias`, `cluster_group`, `assignment_order`, `start_seq` och `end_seq` sparas ocksa `carrier_clusters` i sessionen. Efter Forecast kan anvandaren klicka `Redigera kluster` i resultatpanelen och andra kluster, UTL-fran/till och ordning for den aktuella kedjan innan Ytgenerering kors; om `carrier_clusters` saknas byggs en redigerbar lista fran Forecast-tabellens unika transportorer. Om orderoversikten saknar transportor pa en sandning anvander Forecast default-transportoren `Schenker` internt for modellens transportorsignal, men resultatet och Ytgenerering far transportoren `Okand` sa fallbacken inte styr ytregler. Ytgenerering cachar ocksa den fardigfiltrerade `location`-ytlistan per filversion med TTL/maxbudget. Nar en ny `location`-karnfil laddas upp sparas den i Postgres, aldre lokala fallbackfiler for samma verksamhet och filtyp tas bort, filen materialiseras till en temporar backendfil for berakningsmotorn, den gamla location-cachen rensas och den nya ytlistan forvarms direkt. Uppladdningar laser karnfilstatus fran servern utan GET-cache, sa upprepade placeringar slipper lasa och filtrera lagerplatser igen utan att riskera gammalt underlag.

Transportorskluster har inbyggda standardvarden nar karnfilen eller Forecast bara ger transportorsnummer och saknar klusterfalt. Defaults fyller tider, `clusterGroup`, `assignmentOrder`, `startSeq`, `endSeq` och farg for kanda transportorsnummer; till exempel fylls 39/40 som Freja, 600-652, 09:00/11:00/13:00 och `#c4b5fd`. Tomma standardgrupper lamnas tomma men far fortfarande standardens ordning och UTL-intervall.

Ytgenerering sorterar transportorer efter Forecast-klustren nar de finns: rader med samma `cluster_group` behandlas som en gemensam placeringsenhet, `assignment_order` styr ordningen och `start_seq`/`end_seq` styr vilket UTL-intervall enheten far anvanda. Om en transportor saknar klusterrad faller den tillbaka till tidigare transportorssortering. Placeringen sker fortfarande per sandning: en lagerplats delas aldrig mellan flera sandningar, och en sandning kan spanna over flera lagerplatser om forecasten kraver mer kapacitet an en enskild yta har. Vilka UTL-ytor som overhuvudtaget far raknas styrs forst av vald Bearbeta-toggles globala `Fran`/`Till`-intervall i matrisen; standard ar MG UTL205-UTL652 och ovriga toggles UTL1-UTL652. Ytkartsinstallningen kompletterar sedan kart- och kapacitetsunderlaget for aktivt sparade ytor: varje sparad UTL-yta har koordinater, storlek och `maxPall`, kan uppdatera kapaciteten pa en befintlig `location`-rad och kan lagga till en saknad `Typ=U`-yta inom UTL1-UTL652. Den egna vyn `Installningar` hamtar dessutom alla `Typ=U`-lagerplatser med UTL-nummer 1-652 fran aktiv verksamhets `location`, aven koder som `UTL01` med inledande nollor, och visar bara de UTL-platser som inte redan finns pa kartan, sa anvandaren kan bygga vidare lagret utan att skriva koordinater for hand. I Installningar kan anvandaren markera flera ytor med Ctrl/Shift, flytta gruppen ihop med drag eller piltangenter och anvanda `Delete`, `Ctrl+C`, `Ctrl+X`, `Ctrl+V`, `Ctrl+Z` och `Ctrl+A`; inklistrade kopior hamnar pa lediga U-platser for att undvika dubbletter. Om ingen karta ar sparad anvands standardkoordinaterna bara for visualisering och inga extra lagerplatser skapas. Resultatet innehaller ocksa en interaktiv SVG-karta: kartan kan pannas, zoomas, roteras och anvandas for att dra en placerad sandning till en annan UTL-yta eller byta plats med en annan sandning. Fullskarm oppnas via en liten ikon i kartans ovre hogra horn. Nar kartan har fokus kan anvandaren ocksa anvanda `Ctrl+C`, `Ctrl+X`, `Ctrl+V` och `Ctrl+Z` for att kopiera/klippa en vald placering, klistra in den pa vald malyta och angra senaste kartandringen. Ytans etikett visar kort ytkod utan `UTL` i kortsidan och kundnamn som huvudtext; kundnamn med flera ord bryts pa max tva rader, pallrad visas inte inne pa ytan och texten har ingen halo/outline. Fargen baseras pa transportor men ett kluster delar basnyans och varje transportor i klustret far en egen ljushet (`allocationClusterColorMap`); manuell farg i kluster-editorn vinner over auto. En knapp `Saknade kunder` uppe till vanster oppnar en panel som listar ej placerade sandningar med kundnamn, transportor och saknade pallplatser. Sidolistans rader markerar ytan och kopierar samtidigt radens sandningsnummer till urklipp, aven nar sifferserien inte visas direkt i listan. Kartan visar aktuella pallplatser, kapacitet och overkapacitet efter manuella flyttar och kan ladda ner en justerad karta-CSV eller justerad ASK-import lokalt i webblasaren. Nar alla sandningar ar placerade och Forecast-resultatet innehaller `Ordernummer` skapas fortsatt den servergenererade `ASK-import order/yta` och laddas ner automatiskt som `v_ask_order_overview_order_set_area_execute_command.csv`. Importfilen ar tabbseparerad med kolumnerna `area_num`, `company`, `order_num`, `pick_zone`; `area_num` innehaller sandningens UTL-ytor kommaseparerade, `company` ar `MG` och `pick_zone` ar `A`.

Ytgenerering-kartans sidopanel visar `Lediga pallplatser` som total kapacitet minus placerade pallplatser och `Lediga ytor` som antalet kartytor utan placering. Bada vardena raknas om nar anvandaren flyttar, klistrar in eller angrar placeringar pa kartan.

I `Installningar` kan lediga U-platser ocksa dras fran sidolistan direkt till kartan. Droppunkten blir ytans koordinat, och ytan far sin `maxPall` fran verksamhetens `location`-underlag innan layouten sparas for aktiv verksamhet. Nya ytor fran listan behaller basytans kortsidesbredd men skalar langssidan efter kapacitet, sa exempelvis en 7-palls-yta blir 3,5 ganger langre an en 2-palls-yta. Kartans ytetiketter visar kort kod utan `UTL`, foljer ytans langsta sida och anvander samma normalviktade fontstil som Ytgenereringens ytkarta, men med storre ytkod eftersom redigeringsytorna saknar kundtext. Nar en yta dras visar kartan diskreta hjalplinjer och snappar bara nara andra ytors kanter och mittlinjer for enklare linjering. Varje yta visar ocksa en diskret fylld lastningspil i ytans kant; dubbelklick pa ytan roterar den 90 grader at vanster, medan hogerklicksmenyn `Byt riktning` vaxlar lastningsriktning for en eller flera markerade ytor och sparar `loadDirection`. Menyn positioneras lokalt i kartans workspace vid hogerklickspunkten, sa den foljer musen aven nar appen eller kartan ar zoomad. I Ytgenerering styr riktningen var ytkoden visas och vilken sida som blir randig vid outnyttjad kapacitet.

Ytkartan visar nu en kort ytkod utan `UTL` i ytans kortsida, sa kundnamnet kan ligga storre i mitten av ytan utan pallrad under. Kundnamnet bryts pa max tva rader nar det innehaller flera ord, visas utan halo/outline och ligger alltid parallellt med ytans langsta sida. Det ersatter den tidigare centrerade UTL-raden i varje kartkort. Outnyttjad kapacitet visas som ljusare fargnyanser av samma ytfarg, proportionellt mot ledig andel, till exempel 50 procent randigt vid 5 av 10 placerade pallplatser.

Dolda/tekniska floden finns for observations-update, observations-sync och update-check. Observations kan aven triggas automatiskt nar ny buffertfil laggs in. Startup-sync for observations ar avstangd som standard i Render med `ALLOCATION_OBSERVATIONS_STARTUP_SYNC=false`, eftersom jobbet laddar legacy-lagerverktyget, pandas och observationsdata och kan ge minnesspikar efter omstart. Om syncen slas pa vantar den forst `ALLOCATION_OBSERVATIONS_STARTUP_DELAY_SECONDS` och kor sedan alla aktiva verksamheter fran databasen en i taget med `ALLOCATION_OBSERVATIONS_STARTUP_SPACING_SECONDS` mellan varje. Anvand manuell eller schemalagd observations-sync nar Render-minne ar trangt. Observations och den framraknade sammanstallda datan `artikel_max.csv` ar verksamhetsseparerade pa persistent disk via `PRODUCTIVITY_DATA_DIR` eller `MEDIA_STORE_ROOT/flow-data`, normalt `flow-data/buffertpall/stigamo/`, `flow-data/buffertpall/r3/`, `flow-data/buffertpall/t3/` och sa vidare. Gamla vendor/root-filer kan endast anvandas som seed/legacy-ingang tills datan migrerats; aktiva las- och skrivvagar gar via persistent disk. Om en verksamhet saknar observationshistorik ska anvandaren ladda upp buffertpall forst. Tom `observations.csv.gz` far skapas som startlage, men tom/header-only `artikel_max.csv` far inte behandlas som klar data for Ordersaldo, LYX eller Pafyllnadsprio.

For Super User foljer lagerverktygens verksamhet sidebarens omradestoggle. R3-toggle skriver/laser R3:s observations, `artikel_max.csv` och coredata; Stigamo-omraden som GG/MG/AS/EH skriver/laser Stigamo. `∞` faller tillbaka till Super User-kontots egen verksamhet.

Allokering anvander bara orderrader med status 33 eller lagre. Orderrader med status over 33 ignoreras innan pallar matchas. Buffertpall-rader filtreras separat till status 29, 30 och 32 for allokering, och refill anvander status 29 och 30.

## Dela

Kontroller:

- Textarea "Varden" for en rad per varde.
- Alternativ filslot for textfil.
- Antal per kolumn.
- Knappen "Dela varden".

API: `POST /api/allokering/flow/split-values`.

Korda lagerverktygsfloden auditloggas i Historik som `allocation_flow`. Lyckade korningar sparar flodes-id, vilka filslotar/parameternamn som anvandes, verksamhet, vald toggle/filter och hur manga resultattabeller som skapades, men inte filnamn eller inskickade listvarden. Om uppladdningen inte kan sparas, multipart-formularet inte kan lasas eller filen inte kan bearbetas loggas `upload_failed` med steg, feltyp, kort felmeddelande och eventuell HTTP-status. Om automatisk filidentifiering kraschar loggas `detect_failed`. Om sjalva flodet kraschar loggas `flow_failed` med statuskod, felkod, feltyp, anvandarvanligt meddelande och tekniskt meddelande nar backend har ett. `No objects to concatenate` fran Forecast betyder normalt att flodet fick noll rader att sammanstalla efter inlagda filer och vald toggle/filter.

Interaction-tracking for Bearbeta och Dela ligger bredvid auditloggen. `allocation_tools.js` skickar sanerade events for flodesstart, blockerade krav, lyckad/felad korning, foljdfloden, auto-download, Excel, CSV, textkopiering och kolumnkopiering. Events innehaller flow-id, resultatsessionens narvaro, tabellnyckel, tabellnamn, kolumnindex, kolumnnamn, radantal och `copy_mode`, men inte kopierade cellvarden, filnamn eller lokala sokvagar. Pa Pafyllnadsprio kan Historik > Kolumner/AI-analys darfor svara om anvandare normalt bara anvander auto-copy av forsta kolumnen eller manuellt kopierar flera kolumner i samma resultat.

Bearbeta-uppladdningar sparas content-addressed i serverns temporara cachekatalog utan originalfilnamn. Nar samma fil skickas igen far den samma sokvag, och `warehouse_tools.flows` ateranvander inlast DataFrame sa lange filens storlek och modifieringstid ar oforandrade. Allokering cachar dessutom hela berakningspaketet per filversion: allokerade rader, near-miss, refill Huvudplock/AutoStore och pallplatser. GG/MG-radfilter cachas per originalfilversion och filterregel, sa samma filtrerade underlag kan ateranvandas mellan Bearbeta-korningar utan att originaluppladdningen i cache/IndexedDB andras. Servercacherna har TTL, maxantal och byte-/storleksbudget: uppladdningscache rensas pa alder, antal och total storlek; runtime-cacher i `warehouse_tools.flows` trimmas pa alder och ungefarlig storlek; Bearbeta-resultat ligger som temporara filer i stallet for fulla DataFrames i `allocation_bridge.SESSIONS`. Frontenden forvarmer synliga vyers GET-data i en idle-ko med session-cache och sparar Uppladdningars filmetadata separat, sa Uppladdningar kan ritas fran cache medan stora IndexedDB-blobbar och coredata-status laddas i bakgrunden. Cachelagret rensas opportunistiskt, behaller bara ett begransat antal filer och ska bara paverka hastighet, inte resultat eller verksamhetsscope. Om samma anvandare laddar upp samma slot/filnamn med nytt innehall ersatts den tidigare cacheposten direkt.

I Windows-appen skickar Bearbeta inte vanliga korfiler till central server for sjalva berakningen. Filval via Qt-bron sparar en `localRef`, den lokala desktop-servern fangar `/api/allokering/flow/*`, laser aktuell fil fran disk och kor samma `warehouse_tools`-motor lokalt. Bara sanerad historik skickas centralt: feature/flode/status, filslotar, varaktighet och rad-/resultatraknare, aldrig lokal sokvag eller filinnehall. Karnfiler/KPI och sammanstalld data kan fortfarande syncas centralt i bakgrundsko.

Nar ett Bearbeta-flode har API-first-kallor provar desktop-servern forst att hamta motsvarande temporara CSV fran central server. Vid fel fortsatter den med localRef-filen om den finns. Det gor att Windows och webb far samma API-prioritet men behaller samma fallback som tidigare vid driftstorning.

Bearbeta-resultat lagras som temporara serversessioner med TTL och maxantal. Sessionens RAM-del innehaller flow-id, agare, labels, artifact-nycklar och filreferenser; fulla tabeller, stora artifacts och auto-download-filer ligger i temporara serverfiler. Sessionen binds till anvandaren som korde flodet, sa `Oppna i Excel`, `Ladda ner CSV` och kolumnkopiering inte kan hamta en annan anvandares resultat aven om ett session-id skulle delas. Om servern startas om eller sessionen hinner rensas kan previewn finnas kvar i klienten, men export/kopiering kraver ny korning.

Bearbeta och Dela sparar samtidigt arbetslaget klient-side i `sessionStorage` per inloggad anvandare och vy. Det gor att Dela-listan, antal per kolumn, Bearbetas senaste status och den senaste resultatpreviewn finns kvar nar anvandaren gar till en annan vy och sedan tillbaka i samma session. Fulla Excel-/CSV- och kolumnhamtningar anvander fortfarande serverns temporara `session_id`; om servern har startats om kan previewn synas men export/kolumnkopiering krava ny korning.

## Resultatkontroller

| Kontroll | Vad hander |
| --- | --- |
| Flodesknapp | Disabled tills kravda filer/falt finns. Visar "Kor..." medan API jobbar. |
| Info `i` | Visar flodesbeskrivning och kravda filer i popover. |
| Foljdknapp efter Forecast | Nar Forecast ar klart visas `Kor Ytgenerering` direkt i resultatpanelen om Ytgenerering finns i Bearbeta. Knappen ar disabled tills Forecast-sessionen och verksamhetens `location` finns, och skickar samma `forecast_session_id` som den vanliga Ytgenerering-knappen. Om Forecast har transportorskluster skickas aven `carrier_clusters_json` vidare. |
| Redigera kluster | Visas i Forecast-resultatet nar Forecast har transportorer. Oppnar en modal med drag-sortering (radordningen satter `assignment_order`), index, Transportor och kolumnerna ASN/Arrive/Depart, Group (`cluster_group`), Start seq/End seq och en fargvaljare. ASN/Arrive/Depart seedas med standardtider (11:00/12:00/14:00) och sparas i `carrier_clusters` som metadata (styr inte placeringen). Om `trans_agency` inte gav klusterrader skapas raderna fran Forecast-tabellens unika transportorer. |
| Kopiera text | Fritextrutor, till exempel Vecka 27-rapporten, har en kopieringsikon uppe till hoger som kopierar hela rutans text och visar toasten "Text kopierad". |
| Resultattabell | Visar kolumnnamn i headern och en kopieringsikon per kolumn. Orderoversiktkontroll behaller `Avvikelsetyp` for samma Excel-/CSV-kontrakt som Allokera. Kolumnkopiering trackas med tabell, kolumnindex, kolumnnamn och radantal. |
| Oppna i Excel | Skickar session_id och tabellnyckel till `/api/allokering/open-excel`. Vid lyckad OS-start visas toasten "Excel oppnas"; om Windows/Excel inte kan oppna filen visas feltoast. |
| Ladda ner CSV | Hamter `/api/allokering/download/{session_id}/{key}`. Exporten normaliserar cellvarden som preview/Excel, t.ex. `1.0` skrivs som `1` och tomma NaN-varden blir tomma celler. |

For Allokering visas huvudtabellen `Allokerade pallar` som en vanlig resultattabell med `Oppna i Excel` och `Ladda ner CSV`, samma session som near-miss, refill och pallplatser.

Pallplatser foljer Allokeras berakning: zon `R` raknas som `autostore`, zon `F` raknas separat som `HIB` med 20 rader per toppall, och `Topp Pallar`, `Totalt Pallar` och `Pallplatser` inkluderar HIB-delen.

For Ordersaldo kopieras listan `Kompletta ordrar` till urklipp direkt nar flodet ar klart. Tabellen `Underskott` far kolumnen `Antal pa Helpall` fran `artikel_max.csv`; om anvandaren inte laddar upp en egen fil anvands verksamhetens sammanstallda data. For Godsdeklaration kopieras tabellen `Klara ordernummer` pa samma satt nar flodet ar klart.

## CLI och paritytester

Bearbeta och Dela kan koras pa tva satt fran terminalen:

- `python -m warehouse_tools.cli ...` kor flodena direkt mot `warehouse_tools/flows.py` utan server, browser, IndexedDB eller cookies. Kommandot har `list-flows`, `schema`, `detect`, `run`, `run-scenario`, `validate-scenario` och egna subcommands for varje flode, till exempel `allocate` och `split-values`.
- `python -m tools.flow_cli allocation ...` kor samma `/api/allokering`-endpoints som webb/desktop. Det anvander CLI:ns cookie jar, kan logga in med `auth login`, kor floden med multipart-filer och laddar ner fulla resultat-CSV:er fran sessionen.

Vanliga regressionskommandon:

```powershell
python -m warehouse_tools.cli list-flows
python -m warehouse_tools.cli allocate --auto-file orders.csv --auto-file buffer.csv --auto-file item_option.csv --format both --out artifacts\allocate
python -m warehouse_tools.cli forecast --auto-dir "C:\Users\emikad\Downloads\testdata 20260603" --auto-dir data\coredata\Stigamo --format csv --out artifacts\forecast-local
python -m warehouse_tools.cli split-values --values "A`nB`nC" --chunk-size 2 --out artifacts\split
python -m tools.flow_cli allocation run allocate --file orders=orders.csv --file buffer=buffer.csv --file items=item_option.csv --out artifacts\api-allocate
python -m tools.compare_warehouse_results --left .\Resultat.csv --right .\tmp6jj8twk6_allocated_orders.xlsx
```

`tools.compare_warehouse_results` normaliserar exportbrus innan jamforelse: `1.0` jamfors som `1`, och NaN/None/tomma celler blir tomma strängar. Det gor Flow-CSV mot Allokera-XLSX anvandbart som sanningskontroll.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor ar flodesknappen gra?" | Kravda filer eller textfalt saknas, eller ett annat flode kor. Klicka `i` for att se krav. |
| "Varfor hamnar filen i fel ruta?" | Automatisk detektion bygger pa filnamn/header. Anvand Välj pa exakt slot for att styra. |
| "Varfor ser jag inte Bearbeta i menyn?" | Rollen saknar normalt `allocationProcess=edit`. Be admin/Super User kontrollera Vybehorigheter. |
| "Varfor oppnas inte Excel?" | Funktionen kraver lokal desktop/OS-stod och servern maste ha kvar resultat-sessionen. Om servern startade om med `--reload`, kor flodet igen. Om Windows/Excel inte kan oppna filen automatiskt visas feltoast; testa Ladda ner CSV. |
| "Vad betyder karnfil?" | En karnfil ar permanent serverdata for anvandarens verksamhet. Nya coredata-karnfiler sparas i Postgres och materialiseras bara temporart till fil nar backend-motorn behover lasa CSV. `artikel_max.csv` ar sammanstalld data, medan coredata-filer som `item_option` ar karnfiler. Bada kan anvandas aven om anvandaren inte laddat upp en lokal fil i sessionen. |
| "Vad hander om jag laddar upp ny item_option?" | Den gamla `item_option`-raden for din verksamhet ersatts i Postgres och den nya blir sanningen. R3, Stigamo och framtida verksamheter paverkar inte varandra. |
| "Vad hander om jag laddar upp ny artikel sakerhetsinformation?" | Den gamla `item_security_info`-filen for din verksamhet tas bort och den nya anvands av Godsdeklaration. Andra karnfiler, till exempel `item_option`, rors inte. |
| "Vad hander om jag laddar upp nya lagerplatser/location?" | Den gamla `location`-filen for verksamheten tas bort, location-cachen rensas och den nya fardigfiltrerade ytlistan byggs direkt for Ytgenerering. |
| "Hur styr jag var transportorer placeras i Ytgenerering?" | Ladda upp transportorsfilen som `trans_agency`, `transportorer` eller `agency`. Kor Forecast, klicka `Redigera kluster`, justera `Kluster`, `Fran`, `Till` och `Ordning`, och kor sedan Ytgenerering. |

## Kallor

- `../app/frontend/js/allocation_tools.js`
- `../app/backend/routers/allocation.py`
- `../app/backend/workflow_data.py`
- `../app/backend/routers/workflow_data.py`
- `../app/backend/allocation_bridge.py`
- `../desktop/local_runtime.py`
- `../app/backend/coredata_service.py`
- `../app/backend/routers/coredata.py`
- `../warehouse_tools/catalog.py`
- `../warehouse_tools/cli.py`
- `../warehouse_tools/flows.py`
- `../warehouse_tools/carrier_clusters.py`
- `../warehouse_tools/surface_generation.py`
- `../warehouse_tools/mg_forecast/forecast.py`
- `../warehouse_tools/vendor/allokering12.1.py`
- `../tools/flow_cli.py`
- `../tools/compare_warehouse_results.py`
- `../../ALLOKERING_FILKUNSKAP.md`

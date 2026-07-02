---
title: Produktivitet
status: aktiv
updated: 2026-07-02
tags: [produktivitet, kpi, ui, api-snapshot]
---

# Produktivitet

Kort svar: Produktivitet ar nu den tidigare oversiktsvyn, men med Produktivitets
befintliga menyplats, namn och ikon. Vyn visar globalt sparad
produktivitetsdata som ett fokuserbart trad for verksamhet, omrade,
aktivitet, person, timme och processpoang. Produktivitetsdata hamtas inte per
anvandare och laddas inte upp manuellt i vyn.

## Behorighet

Rollen behover minst `productivity=view` for att oppna Produktivitet och lasa
rapporterna. `productivity=edit` kravs bara for manuell drift/test-sync via
`POST /api/productivity/sync`. Den separata vyn/behorigheten
`productivityOverview` finns inte langre. Gamla `/oversikt-produktivitet.html`
ar borttagen och ska inte langre anvandas.

Rollen kan dessutom fa `productivityFinance=view`. Da visar Produktivitet
intakt, utgift och resultat pa varje kort i hierarkitradet. Utan den
behorigheten returnerar API:t bara `finance.visible=false` och inga belopp
laggs pa cellerna. Berakningsreglerna styrs av
`productivityFinanceSettings`, som ligger under Installningar och bara ar
seedad till Super User tills en admin uttryckligen ger andra roller atkomst.

## Vad vyn visar

- Periodval for `Dag`, `Vecka`, `Manad` och `Ar`.
- Datum-/periodruta med foregaende/nasta. I daglage visas datumet, i veckolage
  visas `Vecka N`, i manadslage visas manadens namn och i arslage visas artalet.
- `Helbild`, som fokuserar tradet tillbaka till verksamhetsroten.
- `Exportera flowchart`, som oppnar en dialog for val av exportnivaer och
  laddar ner aktuell fokuserad vy som SVG.
- Verksamhetsnoden har hogerklickskommandot `Summering`. Dialogen anvander
  samma datum-/periodurval som vyn och visar intakt, kostnad, resultat och
  nollade plockrader per bolag. Nollade rader ar poster i plockloggen dar
  `Plockat`/`qty_suf` ar `0`.
- Verksamhetsnoden har ocksa hogerklickskommandot `Sankey - Inbound` om rollen
  har `sankeyInbound=view`. Kommandot oppnar en separat vy och skickar med
  Produktivitetens period/datum som starturval.
- Vyn renderar kontroller, sammanfattningsskal och tradyta direkt. Rapporten
  hamtas sedan i bakgrunden och statusraden visar forst hamtning och sedan
  berakning/ritning innan korten fylls pa. Detta ar medvetet read-only
  laddbeteende och skapar ingen ny audit-rad; befintlig produktivitetsrapport-
  audit och vantetidsmatning fortsatter galla.
- Periodoversikten bygger dagrapporter fran befintliga snapshotfiler.
  `person_productivity_daily` anvands inte som fullrapport for tradet, eftersom
  Produktivitet behover komplett tim-/processdetalj per dag. Postgres och
  filbaserad SQLite bygger dagar med begransad parallellism, hogst fyra dagar
  samtidigt; in-memory SQLite och fake-sessioner kor seriellt. Progressen raknar
  fardiga dagar, sa dagar kan bli klara i annan ordning utan att slutresultatet
  andrar ordning.
- Noder for verksamhet, omrade, aktivitet, person, timme och processpoang.
- Barnnoder visas som en sammanhangande horisontell tradgren. Nar det finns
  manga barn scrollas tradytan i sidled i stallet for att bryta upp grenlinjen.
- Snittet visas som poang per arbetad timme med en decimal. Stodtid raknas som
  verklig arbetstid i tradets timmar och rullar upp till omrade/helbild, men
  en ren stodnod saknar egen KPI-tid och visar darfor `-` efter likhetstecknet.
  Fargskalan ar rod under 70, orange 70-79,9 och gron fran 80.
- Omradesnivan i tradet bygger pa schemacellens aktivitetomrade, inte
  personens hemomrade. En person med hemomrade Autostore som bemannas pa en
  GG-aktivitet ger darfor KPI-tid och poang under GG.
- En person med bara stodtid syns i tradet under stodaktiviteten med sina
  poang och timmar. Personens egen produktivitetsvy fortsatter daremot att
  visa bara KPI-aktiviteter.
- Med `productivityFinance=view` visas en extra rad pa korten:
  `Intakt`, `Utgift` och `Resultat`. Utgift ar arbetad tid multiplicerad med
  installningen `kostnad per timme`. Intakt raknas bara for VAS-aktiviteter:
  VAS-minuter multipliceras med verksamhetens VAS-intakt per timme for
  aktivitetens bolag och personens arbetstyp (`blue_collar` eller
  `white_collar`). Berakningen anvander VAS-raden `Normal`; Overtid/OB-raderna
  sparas i intaktsunderlaget for senare bruk. Tillatna bolag hamtas fran
  Verksamheter-vyns `company_codes`, till exempel `GG` och `MG` for Stigamo. En
  aktivitets omrade, kod eller etikett far bara anvandas om koden matchar ett
  av dessa bolag; vanliga omraden som inte ar bolag ger ingen VAS-intakt. Om en
  person saknar arbetstyp raknas den som `blue_collar`.
  Timkort rullar upp exakt till person, aktivitet, omrade och verksamhet.
  Processkorten far en proportionell andel av timkortets belopp utifran
  processpoangens andel av timmens processpoang.
  I Intakt/utgift kan en vanlig intaktsrad dessutom kopplas till en
  KPI-process. Da laggs radens `pris * ST / Antal` till periodens intakt och
  resultat, och Produktivitet fordelar beloppet till matchande processnoder
  utifran deras processpoang. Om vald process inte finns i aktuell vy hamnar
  intakten bara pa periodens total.

Dagens datum raknas bara till och med senaste avslutade heltimme. Aldre datum i
vald period raknar hela dagen. Innevarande vecka, manad och ar klipps vid dagens
datum sa framtida dagar inte ingar.

## Global snapshot

Nar `DATA_SOURCE_*` och extern datakatalog ar konfigurerade ar serverns globala
API-snapshot primar sanning. Forsta startup-syncen fyller bootstrap-historiken
till och med gardagens datum. Efter det uppdateras dagens snapshot vid varje
hel- och halvtimme i Europe/Berlin-tid, men dagens `person_productivity_daily`
byggs inte av bakgrundsjobbet utan nar anvandaren oppnar dagens datum. En global
historik-backfill hamtar sedan en aldre dag per kalenderdag tills historiken ar
fylld.

Snapshotens API-kallor (`pick`, `trans`, `pallet`, `receive`, `order_log` m.fl.)
hamtas via `ExternalDataClient.fetch_all` (delad `fetch_all_rows`). Nar en dag
overstiger datakallans radtak (`DATA_SOURCE_RESPONSE_ROW_CAP`) delas hamtningen
upp i datumfonster och slas ihop, sa stora dagar/perioder inte tyst trunkeras.
Det ar samma logik som Hamta data och Bearbeta anvander.

Servern lagrar snapshots under
`compiled_data_root()/productivity_snapshots/` som gzip-CSV plus metadata per
datum. Mappen ar global for programmet, inte per anvandare eller session. Gamla
dagsmappar rensas inte av produktivitetsflodet; dagens filer kan ersattas
atomiskt nar dagens data uppdateras, medan aldre datum ligger kvar.
`backfill.json` i samma rot sparar hur langt den langsamma historikhamtningen
har kommit.
`prebuild.json` sparar nattjobbet som bygger `person_productivity_daily` for
alla snapshotdatum som redan finns och ar aldre an idag. Eftersom
cache-current-kontrollen jamfor snapshot- och schemasignatur byggs bara datum
om nar underlaget har andrats.

Samma fyllning kan koras manuellt via arkivcache-CLI:t nar DB:n ska fyllas:
`python -m app.backend.archive_cache_cli --tenant frey --with-productivity --business-code STIGAMO`
hamtar standardfonstret fran `ARCHIVE_CACHE_SEED_DAYS`, till och med igar, och
bygger normalt `person_productivity_daily` direkt.
`python -m app.backend.archive_cache_cli --productivity-only --productivity-start 2025-01-01 --business-code STIGAMO`
hamtar ett explicit API-dagintervall fran startdatumet till och med igar och bygger normalt
`person_productivity_daily` direkt. Intervallkörningen går från slutdatumet
bakåt i chunkar, hoppar över snapshotdagar som redan är kompletta och använder
cache-current-kontrollen innan personcachen byggs. Det betyder att en omkörning
inte hämtar eller materialiserar datum som redan är aktuella. `--productivity-no-prebuild`
hamtar bara filerna och kraver inte att appdatabasen kan skriva personcachen.
Bygglaget kraver fungerande `DATABASE_URL`; om DB:n ar nere stoppar CLI:t innan
den hamtar en lang period. `--productivity-prebuild-existing` kor gamla prebuild-laget
for alla snapshotdagar som redan finns, ar kompletta och ar aldre an dagens datum,
utan att hamta ett seed-intervall.
Produktivitets-CLI:n skriver en chunk-progressbar och visar per intervall hur
manga snapshotdagar som redan hittades sparade, hur manga som saknas/ar gamla,
hur manga rader som finns i sparade snapshotmetadata, om API hamtades, samt hur
manga `person_productivity_daily`-dagar som redan var aktuella eller byggdes.
Det ar medvetet formulerat som sparade snapshots/persondagar i stallet for
generell cache, eftersom snapshotfilerna ligger pa disk och persondagarna ligger
i appdatabasen.

Sankey - Inbound kan ateranvanda samma snapshotfiler for de gemensamma
datumstyrda loggkallorna `receive` och `trans` nar hela Sankeys foljfonster
redan finns lokalt. `pick` gar via Sankeys egen live-/arkivhamtning for att
behalla outboundavstamningen mot WMS. Saknas nagon dag gar Sankey tillbaka till
sin egen live-/arkivhamtning for att undvika halva underlag.

Nar en vy behover snabba person-/dagssvar kan backend materialisera snapshoten
till `person_productivity_daily`. Det ar beraknad cache, inte masterdata pa
personen. Bemanningens cell-hover-snitt och produktivitetskolumn laser denna
cache och bygger om en dag nar snapshot- eller schemasignaturen andras.
Nattjobbet prebygger historiska snapshotdagar efter backfill/snapshot-sync.
Dagens datum ar undantaget: dagens snapshot far vara farskt, men dagens
personcache byggs on-demand nar dagrapporten eller bemanningssammanfattningen
begar den.

Snapshoten innehaller kallorna:

| Nyckel | API-vy | Anvands till |
| --- | --- | --- |
| `pick` | `v_ask_pick_log_full` | Plockrader, kollin och helpallsregler |
| `trans` | `v_ask_trans_log` | Dekantering, HBW, buffer och pafyllnad |
| `pallet` | `v_ask_palletloading_log` / `LOADING_LOG` | Pack/pallastning |
| `receive` | `v_ask_receive_log` | Receiving och buffer update |
| `order_log` | `v_ask_order_log` | Orderlogg for KPI-regler som kopplar order till pall |
| `sort` | `sort_conveyor_log` | Sortering e-com/store |
| `base_pallet` | `v_ask_article_buffertpallet` | Base pallet-/buffertpallsunderlag |
| `kpi` | `v_ask_kpi_target` | KPI-mal och poangkolumner |

KPI-mal hamtas som API-kalla fran `v_ask_kpi_target`. Om just KPI-kallan inte
kan hamtas via API kan permanent KPI-coredata for verksamheten anvandas som
fallback i snapshotbygget. Snapshotens `source_status` visar da `kpi` med
`status=coredata_fallback`; nar API-felet ar kant skickas aven
`fallback_reason`, till exempel HTTP 403 om API-klienten saknar behorighet till
KPI-vyn.

KPI-malet fran `v_ask_kpi_target` ar den enda externa KPI-kallan som kravs for
poang. Hur loggrader klassificeras till processer och matt (rader, kolli,
pallar eller order) ligger i kodens interna standardlogik baserad pa
`referens/kpi.sql`. Det finns ingen anvandaruppladdad separat regelfil i
Produktivitet.

## API-kontrakt

- `GET /api/productivity` returnerar personbaserad dagrapport med `people[]`,
  `summary`, `sync`, `backfill`, `prebuild`, `available_dates` och `source_status`.
- `GET /api/productivity/overview` returnerar periodpaketet som
  `produktivitet.html` anvander: `reports[]`, `period`, `summary`,
  `missing_dates`, `source_status`, `sync`, `backfill` och `prebuild`. Daglage for ett
  enskilt datum kan trigga och vanta upp till nagra minuter pa just den dagens
  snapshot, sa Produktivitet inte faller direkt nar anvandaren oppnar vyn
  precis efter lokal/server-start. Vecka, manad, ar och custom-perioder laser
  fortsatt befintliga snapshots for perioden och triggar inte extern
  historikhamtning vid varje periodbyte. Varje dagsrapport byggs fran
  snapshotfilerna, inte fran `person_productivity_daily`, sa full tim- och
  processdetalj finns kvar. Nar databasen stodjer det byggs dagrapporterna med
  max fyra parallella dagjobb; varje jobb har egen session och payloaden ordnas
  per datum innan den returneras.
  Med `productivityFinance=view` innehaller payloaden aven `finance` pa
  periodniva, personniva och relevanta `time_cells`; kopplade intaktsrader
  visas som `finance.process_revenues` pa periodniva. Utan behorighet ar
  `finance.visible=false`.
- `GET /api/productivity/overview/business-summary` anvander samma `date`,
  `period`, `start_date` och `end_date` som overview-endpointen. Svaret
  grupperar periodens intakt, kostnad, resultat och antal nollade plockrader
  per bolag samt en totalrad. Intakter inkluderar VAS-intakt fran
  produktivitetsceller och kopplade intaktsrader; kostnader kommer fran
  arbetad tid per bolag.
- `GET /api/productivity/persons/{person_id}` returnerar personens snitt per
  aktivitet for `period=week|month|year|custom`. Dagar som inte hunnit
  backfillas returneras i `missing_dates`.
- `GET /api/personal/productivity` anvander samma globala snapshotberakning for
  Min produktivitet, men personrollen far bara se sin egen kopplade person.
- `GET /api/schedule/productivity-summary` returnerar en mindre
  Bemanning-specifik personkarta fran `person_productivity_daily`.
- `POST /api/productivity/sync` kor manuell snapshot-sync for drift/test och
  kraver `productivity=edit`.
- `GET/PUT /api/settings/productivity-finance` laser/sparar
  produktivitetens ekonomiberakning per verksamhet. Den styr `hourly_cost`,
  `invoice_rows_by_company` och `vas_hourly_revenue_by_company`, dar varje
  bolag far ett eget intaktsunderlag med rubriken som bolagskod. En
  intaktsrad kan spara `linked_process_key` och `linked_process_label` for att
  visa radens intakt i Produktivitetens processnoder. `GG` fylls
  forvalt med Grann-garden-priserna for Inbound, BUTIK, E-handel, VAS, IT och
  Ovrigt. `GG` har forifylld utrakningsprompt, plan och SQL/querytext for
  `Mottagna etiketter`, `Mottagna artikelrader`, BUTIK-raderna `Plockade
  orders`, `Plockade rader`, `Antal helpallar` och `Utlastade pallar`, samt
  E-handel-raderna `Plockade orders`, `Plockade rader` och `Antal helpallar`.
  `Utlastade pallar` raknar Dispatchpallslogg (`dispatch_pallet_log` och vid
  aldre perioder `dblog_dispatch_pallet_log`) dar `parent_pick_pall_num` ar tomt.
  `MG` fylls bara med VAS-raderna, med samma VAS-priser som `GG`, plus
  IT-raden som defaultar till 0 kr i repot och far riktiga priser via
  lokal/secret overlay. VAS-raderna har separata `blue_collar`- och `white_collar`-varden for
  `normal`, `ot_50`, `ob1_40`, `ob2_70` och `ob3_100`. Endpointen kraver
  `productivityFinanceSettings=view|edit` och foljer samma `business_id` /
  `area_focus`-scope som Bemanningens installningar.
- `POST /api/settings/productivity-finance/calculation/test` testar en
  intaktsrads utrakning for vald manad. Dialogen skickar anvandarens
  utrakningstext, manad och aktuell bolagskod till MiniMax/Hamta data-planen.
  Nar den valda ASK-vyn har kolumnen `company`/Bolag lagger backend pa
  bolagsfiltret automatiskt innan planen kors mot extern datakalla. Svaret
  returnerar `quantity`, plan och en sparbar SQL/querytext. Testmanaden anvands
  bara for provhamtningen; sparad plan och SQL/querytext ar periodneutrala och
  far periodfilter forst nar kontroll/rapport kors for vald period. Bara manader
  som har startat i innevarande ar far testas.
- `POST /api/settings/productivity-finance/process-check` kor knappen
  `Kontrollera intakter/processer` i Intakt/utgift-installningarna. Den laser
  sparade intaktsplaner for vald manad/bolag, hamtar samma Mammur-/ASK-kallor som
  KPI-processerna anvander, kor KPI-reglernas filter mot raderna och jamfor
  faktisk radtackning. Svaret visar foreslagna processmatchningar, intaktsrader
  som har rader utan KPI-process, KPI-processer som saknar intaktsrad samt mojlig
  dubbelrakning. En intaktsrad raknas som matchad nar alla rader, eller vid
  `count_distinct` alla unika berakningsnycklar som `order_num`, traffar minst
  en KPI-process, aven om flera KPI-processer tillsammans behovs. Om matchande
  KPI-processer ocksa tacker rader eller nycklar utanfor den intaktsraden
  returneras det som granskningsnotis, inte som underkand match. Radsvaret
  innehaller `combined_process_coverage`, som visar foreslagen processkombination,
  antal intaktsnycklar, tackta nycklar, saknade nycklar, extra nycklar och
  tackningsprocent.
  Body kan aven innehalla `row_id`. Da kors kontrollen bara for den
  intaktsraden, och UI:ts radkommando `Kontroll` oppnar en dialog dar
  anvandaren valjer kontrollmanad, ser resultatet och kan koppla intaktsraden
  till en KPI-process via en sokbar rullista. Dialogen visar aven radens
  prompt, intakts-SQL/querytext och process-SQL for vald KPI-process. Resultatet visar vilka KPI-processer som
  anvander samma vy samt intaktsantal, processantal, overlapp och diff. Det
  hjalper anvandaren se om skillnaden sitter i filtreringen, till exempel
  status/zon/typ, utan att behova lasa hela globala kontrollen.
  Kallor som `v_ask_pick_log_full` hamtas en gang per manad/bolag for kontrollen
  och ateranvands sedan lokalt for flera intaktsutrakningar, sa lange planen inte
  kraver API-identifiers.
  Nar en intaktsrad bara ar delvis tackt visar resultatet aven vilket
  KPI-villkor som faller for de saknade raderna, till exempel Receiving med
  `Status` vantat `20/30` men hittat `0`.
  Radexempel saneras till tekniska kontrollvarden som bolag, lager, zon, typ och
  status; ordernummer, anvandare och hela radpayloads returneras inte. Endpointen skapar audit-raden
  `productivity_finance_process_check/run` med period, bolag och summerade
  raknetal.

Produktivitetsfilroutes ar borttagna: det finns inte langre
`/api/productivity/files`, `/api/productivity/files/raw`,
`/api/productivity/files/{file_type}` eller `/api/productivity/targets`.
Produktivitet laddar inte heller `productivity.js` eller
`productivity_uploads.js`.

## Desktop

Windows-appen anvander central `/api/productivity`,
`/api/productivity/overview`, `/api/productivity/persons/{id}` och
`/api/schedule/productivity-summary` som sanning.
Den lokala desktop-proxyn har inte langre produktivitetsspecifika endpoints for
filregistrering eller produktivitetsfil-sync. Om central server inte kan nas
returnerar desktop-proxyn ett 503-svar som sager att rapporten kraver central
serverdata for schema och KPI-snapshot.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor |
| --- | --- | --- |
| Period | Valjer Dag, Vecka, Manad eller Ar | Hamtar periodpayload fran `/api/productivity/overview` |
| Datum-/periodruta | Valjer ankardatum for rapporten | Visar datum, vecka, manad eller ar beroende pa periodlage |
| Foregaende/nasta datum | Klickar pilar | Hoppar inom tillgangliga datum eller kalenderdagar |
| Helbild | Klickar knappen | Fokuserar tradet tillbaka till verksamhetsroten |
| Nod | Klickar verksamhet, omrade, aktivitet eller person | Flyttar fokus och visar nasta niva i hierarkin |
| Summering | Hogerklickar verksamhetsnoden och valjer Summering | Oppnar bolagssummering for samma datum-/periodurval med intakt, kostnad, resultat och nollade plockrader |
| Sankey - Inbound | Hogerklickar verksamhetsnoden och valjer Sankey - Inbound | Oppnar `sankey-inbound.html` med samma period/datum, dar inbound-intakt foljs fran mottagna etiketter till oppna eller forverkade floden |
| Exportera flowchart | Klickar knappen, valjer nivaer och klickar Exportera | Laddar ner aktuell fokuserad vy som SVG med valda nivaer |
| Kontrollera intakter/processer | Klickar knappen i Installningar -> Intakt/utgift, valjer manad/bolag i dialogen och klickar Kontrollera | Jamfor sparade intaktsutrakningar med KPI-processregler for vald manad/bolag och visar matchningar, processkombinationer, luckor, bredare processer och dubbelrakning i dialogen |
| Utrakning | Hogerklickar en intaktsrad i Installningar -> Intakt/utgift och valjer Utrakning | Oppnar radens utrakningsdialog for test och sparning av prompt, plan och SQL/querytext |
| Kontroll | Hogerklickar en intaktsrad i Installningar -> Intakt/utgift, valjer Kontroll och valjer manad i dialogen | Kor samma kontroll bara for den radens sparade utrakning, visar processer pa samma vy, processkombinationens tackning och later anvandaren koppla radens intakt till en KPI-process |
| Koppla process | Hogerklickar en intaktsrad i Installningar -> Intakt/utgift och valjer Koppla process | Oppnar processval med alla KPI-processer och sparar kopplingen sa radens intakt kan visas i Produktivitet |

Produktivitet anvander ett progressivt laddmonster: `produktivitet.html`
renderar statiskt skal och `productivity_overview.js` kor
`renderProductivityOverviewShell()` fore API-svaret. `loadProductivityOverview`
vantar in minst en browser-paint fore `/api/productivity/overview` hamtas och
en till paint fore den tunga tradberakningen/ritningen, sa anvandaren ser vyn
och statusen aven nar rapporten ar tung.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor saknas dagar?" | Historik-backfillen har inte hunnit hamta alla datum an. Saknade dagar visas i `missing_dates`. |
| "Hamtas data varje gang jag oppnar en person?" | Nej. Persondialogen laser sparade globala snapshots och klienten cachar nyligen hamtade perioder kort. Om datum saknas beror det pa att backfill/snapshot inte ar klar. |
| "Varfor visar Produktivitet fel direkt efter start local?" | Dagvyn vantar nu pa dagens startup-snapshot i stallet for att direkt visa saknad API-snapshot. Om fel anda visas ar snapshot-syncen antingen fortfarande upptagen for lange eller sa felar extern datakalla. |
| "Varfor kan Manad ta langre tid lokalt?" | Periodoversikten bygger fulla dagsrapporter fran snapshotfiler for att behalla komplett tim- och processdata. Filbaserad SQLite far anvanda samma begransade dagparallellism som Postgres, men `person_productivity_daily` anvands inte som ersattning for hela Produktivitetstradet. |
| "Varfor ska periodbyte i Produktivitet inte starta en stor API-korning?" | Vecka, manad, ar och custom-perioder ska bara lasa de snapshots som redan finns. API-syncen sker vid startup, hel-/halvtimme, manuell sync eller historik-backfill. Daglage kan bara sakra den enskilda dagens snapshot. |
| "Varfor gar det inte att ladda upp produktivitetsfiler?" | Den manuella produktivitetsuppladdningen ar borttagen. Produktivitet bygger pa global API-snapshot. |
| "Vilken KPI-fil kravs for poang?" | `v_ask_kpi_target`/`kpi` kravs. Den gamla separata regelfilen anvands inte. |
| "Varfor kan desktop inte visa rapport offline?" | Den nya rapporten kraver central schema- och snapshotdata. |

## Kallor

- `../app/backend/productivity_kpi_rules.py`
- `../app/backend/productivity_sync.py`
- `../app/backend/routers/productivity.py`
- `../app/backend/routers/settings.py`
- `../app/backend/settings_service.py`
- `../app/backend/workflow_data.py`
- `../app/frontend/produktivitet.html`
- `../app/frontend/js/productivity_overview.js`
- `../desktop/local_runtime.py`

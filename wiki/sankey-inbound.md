---
title: Sankey - Inbound
status: aktiv
updated: 2026-07-02
tags: [sankey, inbound, produktivitet, ask, ekonomi]
---

# Sankey - Inbound

Kort svar: `Sankey - Inbound` är en separat vy för att följa inbound-intäkten
från mottagna etiketter och unika inköpsrader genom pall-/saldokedjan tills
pengarna är förverkade i plock, och från 2026-07-01 även outbounddebiteringen
för Butik och E-handel. Den öppnas från Bemanning-fliken `Sankey`, från
högerklicksmenyn på `Produktivitet` i vänstermenyn eller på Produktivitetens
verksamhetsnod och kräver egen vybehörighet `sankeyInbound=view`.

## UI och behörighet

Vyn ligger på `sankey-inbound.html` och använder samma skyddade webb/desktop-
frontend som övriga sidor. Den visas som `Sankey` i Bemanning-flikarna när
rollen har `sankeyInbound=view`. Alternativa ingångar finns kvar:
`Produktivitet` -> högerklick i vänstermenyn eller högerklick på verksamheten i
Produktivitetsträdet -> `Sankey - Inbound`.

Kontroller:

- period: `Dag`, `Vecka`, `Månad`, `År`
- datum med föregående/nästa
- bolagsval med `Alla bolag`
- `Visa endast förverkade`, som filtrerar bort öppna etikettgrenar
- `Återställ vy`, `Exportera SVG` och `Exportera spårning`

Diagramytan visar två separata kartor: `Inbound` för mottagning, processer och
status, och `Outbound` som egen karta där flödet delar sig i `Butik` och
`E-handel` innan debiteringsraderna. Klick på nod eller länk visar detaljer om
intäkt, etiketter, poäng, processandel och de pallgrenar som ligger bakom
urvalet. `Exportera urval` i detaljpanelen laddar ner just de
bakomliggande spårningsraderna; toppknappen `Exportera spårning` laddar ner
hela rapportens spårningsunderlag. Processintäkt visas också i tabellen under
diagrammet. Under den visas outboundtabellen med Butik/E-handel, debiteringsrad,
antal, pris och intäkt.

Sankey försöker återanvända redan hämtad data innan den startar en ny hämtning.
`Visa endast förverkade` gör ingen ny API-hämtning och påverkar bara
inboundgrenarna; outbound räknas periodbaserat oavsett om öppna inboundetiketter
visas. Om användaren först har
hämtat `Alla bolag` kan bolagsväljaren växla till ett enskilt bolag lokalt. Om
en månad eller vecka är hämtad kan en dag i samma period visas lokalt, och om ett
år är hämtat kan en månad i året visas lokalt. Saknas den begärda klientvyn
faller frontend tillbaka till vanlig API/SSE-hämtning.

Varningsrutan normaliserar även äldre mojibake-strängar för vanliga svenska
tecken, så varningar som kommit in som `Ã¥/Ã¤/Ã¶` visas som `å/ä/ö`.

Backend ateranvander dessutom Produktivitetens fardiga API-snapshots for
datumstyrda loggkallor nar hela Sankey-fonstret redan finns lokalt. Det galler
`receive` och `trans`. Plocklogg Full (`pick`) hamtas via Sankeys live-/
`dblog_*`-vag, eftersom Produktivitetens dags-snapshots kan sakna plockrader som
behivs for outboundavstamning mot WMS. Nulageskallan `buffer` hamtas fortfarande
via Sankeys egen vag, sa aktuell pallplats inte blir beroende av en aldre
produktivitetssnapshot.
Nar lokal DuckDB-arkivcache ar pa laser Sankey dblog-segment fran cachen och
ateranvander aven toppade live-dagar som redan finns i arkivtabellen. I
`source_status` syns detta som `status=local_archive`; annars faller kallan
tillbaka till live-/dblog-API.
`item_alias` ar en datumslos stodkalla och laser forst nattens DuckDB-snapshot
(`status=local_snapshot`). Saknas snapshoten faller Sankey tillbaka till samma
timestamp-split via API som tidigare. Buffertpall (`buffer` /
`v_ask_article_buffertpallet`) hamtas alltid live vid berakning och ingar inte i
00:01-snapshoten.

## API

`GET /api/sankey/inbound` kräver `sankeyInbound=view`.

Query:

- `period=day|week|month|year`
- `date=YYYY-MM-DD`
- `company=GG|MG|...` valfritt; saknas betyder alla bolag i verksamheten
- `only_consumed=true|false`

Perioden väljer mottagningskohorten för inbound och räkneperioden för outbound.
Backend följer inboundetiketter från periodstart fram till dagens datum via
live-vyer och `dblog_*`-arkiv. Outbound räknas i vald period från Plocklogg Full
och Dispatchpallslogg (`dispatch_pallet_log`/`dblog_dispatch_pallet_log`).
Svaret innehåller `summary`, `companies`, `nodes`, `links`,
`processes`, `outbound_metrics`, `trace_total`, `trace_counts`, `trace_token`, `trace_filter`,
`warnings`, `source_status`, `period`, `filters`, `business` och `cache`.
`trace_rows` ingår inte längre i huvudsvaret, eftersom helår kan ge mycket stora
spårningsunderlag. Frontend visar antal direkt från `trace_total`/`trace_counts`
och hämtar rader först när användaren öppnar detaljpanelen eller exporterar.
`source_status` kan visa `status=productivity_snapshot` for `receive` och
`trans` nar backend har ateranvant Produktivitetens snapshotfiler i stallet for
att anropa extern API for samma vyer igen.
`source_status` kan aven visa `status=local_snapshot` for `item_alias` nar
forpackningsfaktorerna kommer fran nattens DuckDB-snapshot.
`summary` innehåller bland annat `gross_income`, `inbound_income`,
`outbound_income`, `gross_income_labels`, `gross_income_purchase_lines`,
`labels_received`, `purchase_lines_received`, `outbound_picked_orders`,
`outbound_picked_rows`, `outbound_picked_pcs`, `outbound_full_pallets` och
`outbound_loaded_pallets`.
Noder, länkar och processrader har motsvarande `label_revenue`,
`purchase_line_revenue` och `outbound_revenue` så UI:t kan visa breakdown utan
att behöva räkna om.
`GET /api/sankey/inbound/trace?token=&scope=all|node|link&id=&company=&start_date=&end_date=&only_consumed=&offset=&limit=`
returnerar paginerade spårningsrader för huvudrapporten eller vald nod/länk.
`GET /api/sankey/inbound/trace.csv?token=&scope=&id=&company=&start_date=&end_date=&only_consumed=&name=` streamar samma
urval som semikolonseparerad CSV med Excel-vänliga svenska rubriker. Om
spårningstoken har gått ut svarar API:t med HTTP 410 och användaren behöver köra
rapporten igen.
När `only_consumed=false` innehåller svaret även `client_filters.only_consumed`
med `summary`, `companies`, `nodes`, `links`, `processes` och `outbound_metrics`
för förverkad-vyn. Vid direkt `only_consumed=true` finns motsvarande
`client_filters.all` för att kunna växla tillbaka lokalt.
Nyare svar innehåller dessutom `client_filters.views`, en karta med
färdigräknade klientvyer från samma branchunderlag. Nyckeln har formatet
`period|periodstart|bolag|0/1`, till exempel `day|2026-06-25|GG|0`.
All-bolag-payloads får vyer för `ALL` och varje bolag i underlaget. Månad och
vecka får dagsvyer. År prioriterar alltid årsvyn och därefter månadsvyer för
`ALL` och varje bolag, inklusive både standardvyn och `Visa endast
förverkade`, så ett hämtat helår normalt kan byta bolag, månadsdatum och
förverkad-filter lokalt. `0/1` anger om vyn är standard eller `Visa endast
förverkade`. Stora rapporter kan sätta `client_filters.prebuilt=false`,
`views={}` och `omitted_reason=too_many_views` eller `large_payload`.
Dag/vecka/manad/ar prioriterar lokala klientvyer aven nar kallaraderna ar
manga, sa lange vyantalet ryms.
Det betyder att backend har byggt aktuell vy men hoppat över de extra
klientvyerna; frontend faller då tillbaka till vanlig API/SSE-hämtning om
användaren byter bolag, periodnivå eller `Visa endast förverkade`.

Varje lyckad körning auditloggas som
`sankey_inbound_report/run`. Misslyckad källhämtning auditloggas som
`sankey_inbound_report/run_failed`. Auditpayloaden är sanerad till period,
filter, summerade räknetal, källstatus och varningskoder; den sparar inte pallid,
order, rad-id eller radpayload.

## Beräkningsregler

`Mottagna etiketter` kommer från `v_ask_receive_log` och `dblog_receive_log`.
En mottagningsrad räknas som fakturerbar etikett när:

- `type` inte är `23`, `45`, `46`, `47`, `63`, `81`, `91` eller `100`
- `qty_suf` / `Mottaget` är större än `0`
- samma `company + pall_num` inte senare har en `type = 100`-rad som nollställer
  mottaget

`type = 91` räknas alltså inte som en ny mottagen etikett, men kan lägga till
processen `Buffer Update` på en befintlig inboundgren. Först försöker Sankey
matcha raden mot plockplats-FIFO via `company + warehouse + item + location`.
Om den nyckeln inte träffar används pallnumret som fallback, så en buffert-
uppdatering inte tappas bara för att platsfältet inte är exakt samma som i
plockplatskön.

Gross income består av två inbound-intäkter:

- etikettintäkt = antal fakturerbara mottagningsrader * priset på finance-raden
  `inbound_labels` för bolaget
- inköpsradsintäkt = antal unika `company + book_num + line_num` efter samma
  mottagningsfilter * priset på finance-raden `inbound_article_rows` för
  bolaget

Inköpsradsintäkten delas lika över de fakturerbara mottagningsrader som hör till
samma `company + book_num + line_num`. Därefter följer den med samma branch som
etikettintäkten och delas på processerna med samma poängmodell. Om bolaget
saknar prisrad för `inbound_labels` eller `inbound_article_rows` visas varning
och just den intäktsdelen blir `0` tills priset konfigureras.

Outbound består av två grenar:

- Butik (`TO`): `store_picked_orders` räknar unika `order_num` som börjar på
  `TO` och har minst en rad med `qty_suf`/`Plockat >= 1`;
  `store_picked_rows` räknar plockloggsrader där `order_num` börjar på
  `TO`, `pick_zone` inte är `H` och `qty_suf`/`Plockat` är minst `1`;
  `store_picked_pcs` använder samma radfilter men delar upp `qty_suf` per
  `item_num` via `item_alias.conversion_factor` störst först, med faktor `1`
  som `ST`;
  `store_full_pallets` räknar plockloggsrader där `pick_zone = H`, plockat är
  minst `1` och ordern börjar på `TO`; `store_loaded_pallets` räknar
  Dispatchpallslogg där `parent_pick_pall_num`/`Pappapallsnr` är tomt.
- E-handel (`PR`): `ecom_picked_orders` räknar unika `order_num` som börjar på
  `PR` och har minst en rad med `qty_suf`/`Plockat >= 1`;
  `ecom_picked_rows` räknar plockloggsrader där `order_num` börjar på
  `PR`, `pick_zone` inte är `H` och plockat är minst `1`;
  `ecom_picked_pcs` använder samma `package_breakdown`-logik som butik fast för
  `PR`-ordrar; `ecom_pallet` räknar helpallsrader där `pick_zone = H`,
  plockat är minst `1` och ordern börjar på `PR`.

Outboundintäkt per rad är `antal * pris` från motsvarande
`invoice_rows_by_company`-rad i `Intäkt/utgift`. `gross_income` i Sankey är
inbound plus outbound, medan `inbound_income` och `outbound_income` visar
delarna separat.

Processpoäng hämtas via samma KPI-target-parser som Produktivitet använder,
inklusive `action_id`/`Processnamn` och API-kolumner som `loaded_rows`,
`loaded_packages`, `loaded_pallets` och `loaded_orders`. Sankey väljer samma
primära mått per inboundprocess som spårningsreglerna använder, till exempel
Receiving på rader och HBW på pallar. Om en process saknar poäng visas varning
och intäkten lämnas ofördelad i stället för att Flow gissar.

Processintäkt per branch:

```text
processintäkt = (processpoäng / total poäng på branchen) * branchens intäkt
```

Vid split, till exempel AutoStore-dekantering till flera bins, delas etikettens
och inköpsradsdelens pengapott lika mellan grenarna. Kolliantalet används
fortfarande för saldo/FIFO och förbrukning, men inte för hur intäkten delas
mellan splitgrenarna.

Öppna etiketter ingår som standard och fördelas över de processer som hittills
har synts. `Visa endast förverkade` tar bara med grenar som har slutat i plock.

Diagrammet skiljer på genomflöde och processintäkt. Länkar och statusnoder har
ett flödesvärde (`value`) så man kan se var pengapotten ligger, men de får ingen
processintäkt (`revenue`). Bara processnoder som Receiving, HBW, AutoStore,
buffert och plockplats delar på branchens intäkt enligt poängmodellen. Om en
process saknar poäng hamnar intäkten i `Ofördelad intäkt` i stället för att
visas som intäkt på noden.

## Spårning

Backend följer:

- mottagning: `v_ask_receive_log` / `dblog_receive_log`
- transaktioner: `v_ask_trans_log` / `dblog_trans_log`
- plock: `v_ask_pick_log_full` / `dblog_pick_log`
- outbound dispatch: `dispatch_pallet_log` / `dblog_dispatch_pallet_log`
- aktuell buffert: `v_ask_article_buffertpallet`
- forpackningsfaktorer: `item_alias` (nattlig DuckDB-snapshot, API fallback)
- KPI-poäng: Produktivitetens coredata-/fallbackfil för `v_ask_kpi_target`

AutoStore-normalisering: transloggen kan visa `loc_to = AS1000160101`, medan
buffertpall-vyn visar `1000160101`. Sankey matchar båda formerna.

Varje aktiv branch lagras som en spårningsrad bakom rapportens `trace_token`.
Raden innehåller bland annat `origin_pall`, `current_pall`, eventuell
`current_location`, `purchase_number`, `purchase_line`, `source_row_id`, status,
intäktsdelar, `received_date`, `path` och dynamiska `step_1`, `step_2` osv.
`node_ids` och `link_keys` anger vilka diagramnoder/länkar branchen passerar.
Frontend använder `trace_counts` för att visa antal utan att ladda alla rader,
hämtar en liten preview via `/api/sankey/inbound/trace`, och låter
CSV-exporten streamas från `/api/sankey/inbound/trace.csv` så stora helår inte
behöver serialiseras som en enda JSON-payload. CSV-exporten är avsedd för snabb
felsökning i Excel. Pallid och rad-id ligger i trace-API/exporten men sparas
inte i auditloggen.

Datakällejämförelse 2026-06-24 visade att `v_ask_palletloading_log` och
`v_ask_item_summary_stock_automation` inte påverkade Sankey-resultatet och inte
lästes av beräkningsmodellen; de hämtas därför inte längre för denna vy.
`pick_stock` innehåller bara artikel/kvantitet och saknar pallid/plats, så den
kan inte ersätta pallspårning. `v_ask_item_balance_list` innehåller pallid,
plats och saldo, men var större/långsammare, slog i radtaket för GG och saknade
cirka 12 % av pallid som fanns i `v_ask_article_buffertpallet`. Därför behålls
buffertpall som aktuell pall-/platskälla tills balance-list kan hämtas komplett
och valideras över fler perioder.

`v_ask_kpi_target` hämtas inte via extern API i Sankey. KPI-steget använder
Produktivitetens redan hanterade coredatafil som förstahandskälla, eftersom
API-vyn inte är tillgänglig för detta flöde.

Plockplats är saldobaserad, inte pallbaserad. När pallid läggs på plockplats
dör pallidet och Flow använder en FIFO-liknande ägarkö per
`company + warehouse + item + location`. Om platsen redan har okänt saldo före
inläggning förbrukas det okända saldot först och den egna etiketten markeras med
lägre confidence tills den faktiskt är helt plockad.

## Begränsningar

`v_ask_pick_location_log` verkar sakna kvantitet/pallid och har bara cirka 40
dagars operativ historik utan arkiv. Därför är exakt historisk FIFO på
plockplats osäkrare för äldre perioder. Diagrammet visar varningar och
confidence i stället för att dölja denna begränsning.

`dblog_*`-arkiven ger djupare historik för receive/trans/pick/loading, men inte
obegränsad historik. Analyser längre bak än arkivretentionen kan sakna rader.
Om `dblog_pick_log` nekar ett äldre segment, till exempel HTTP 403, fortsätter
rapporten med tillgängliga plocksegment i stället för att stoppa hela diagrammet.
Det ger varningen `degraded_source_segment_unavailable`; antal förverkade/plockade
grenar kan då vara underskattat och öppna grenar kan i praktiken redan vara
plockade.

Felsökning 2026-06-24 mot Stigamo/Frey visade att nuvarande integrationnyckel
kan läsa `dblog_trans_log`, men får HTTP 403 redan på metadata/dataroute för
`dblog_pick_log`, `dblog_receive_log`, `dblog_pick_list_log`,
`dblog_pick_rest_log` och `dblog_robot_pick_log`, även helt utan filter. Det är
därför inte ett datumkolumn- eller formatfel i Flow utan en extern
vybehörighet/nyckelexponering. Äldre mottagningskohorter kräver åtkomst till
`dblog_receive_log`; utan den kan Flow inte bygga fakturerbara inbound-etiketter
för perioden.

Första versionen är read/report-only: inga nya databastabeller, inga migreringar
och ingen persistent materialisering. Endast korta in-memory-cacher används för
tunga rapportfrågor och för de spårningsrader som hör till en färsk
`trace_token`.

## Källor

- `../app/backend/sankey_inbound_service.py`
- `../app/backend/routers/sankey.py`
- `../app/backend/settings_service.py`
- `../app/frontend/sankey-inbound.html`
- `../app/frontend/js/sankey_inbound.js`
- [Produktivitet](productivity.md)
- [ASK datalagring](ask-datalagring.md)
- [ASK statuskoder](ask-statuskoder.md)

---
title: Sankey - Inbound
status: aktiv
updated: 2026-06-25
tags: [sankey, inbound, produktivitet, ask, ekonomi]
---

# Sankey - Inbound

Kort svar: `Sankey - Inbound` är en separat vy för att följa inbound-intäkten
från mottagna etiketter och unika inköpsrader genom pall-/saldokedjan tills
pengarna är förverkade i plock. Den öppnas från högerklicksmenyn på
`Produktivitet` i vänstermenyn eller på Produktivitetens verksamhetsnod och
kräver egen vybehörighet `sankeyInbound=view`.

## UI och behörighet

Vyn ligger på `sankey-inbound.html` och använder samma skyddade webb/desktop-
frontend som övriga sidor. Den läggs inte i standardmenyn; ingång är
`Produktivitet` -> högerklick i vänstermenyn eller högerklick på verksamheten i
Produktivitetsträdet -> `Sankey - Inbound`.

Kontroller:

- period: `Dag`, `Vecka`, `Månad`, `År`
- datum med föregående/nästa
- bolagsval med `Alla bolag`
- `Visa endast förverkade`, som filtrerar bort öppna etikettgrenar
- `Återställ vy`, `Exportera SVG` och `Exportera spårning`

Diagrammet visar noder och flöden per bolag. Klick på nod eller länk visar
detaljer om intäkt, etiketter, poäng, processandel och de pallgrenar som ligger
bakom urvalet. `Exportera urval` i detaljpanelen laddar ner just de
bakomliggande spårningsraderna; toppknappen `Exportera spårning` laddar ner
hela rapportens spårningsunderlag. Processintäkt visas också i tabellen under
diagrammet.

Sankey försöker återanvända redan hämtad data innan den startar en ny hämtning.
`Visa endast förverkade` gör ingen ny API-hämtning. Om användaren först har
hämtat `Alla bolag` kan bolagsväljaren växla till ett enskilt bolag lokalt. Om
en månad eller vecka är hämtad kan en dag i samma period visas lokalt, och om ett
år är hämtat kan en månad i året visas lokalt. Saknas den begärda klientvyn
faller frontend tillbaka till vanlig API/SSE-hämtning.

Varningsrutan normaliserar även äldre mojibake-strängar för vanliga svenska
tecken, så varningar som kommit in som `Ã¥/Ã¤/Ã¶` visas som `å/ä/ö`.

## API

`GET /api/sankey/inbound` kräver `sankeyInbound=view`.

Query:

- `period=day|week|month|year`
- `date=YYYY-MM-DD`
- `company=GG|MG|...` valfritt; saknas betyder alla bolag i verksamheten
- `only_consumed=true|false`

Perioden väljer mottagningskohorten. Backend följer sedan samma etiketter från
periodstart fram till dagens datum via live-vyer och `dblog_*`-arkiv. Svaret
innehåller `summary`, `companies`, `nodes`, `links`, `processes`,
`trace_rows`, `warnings`, `source_status`, `period`, `filters`, `business` och
`cache`.
`summary` innehåller bland annat `gross_income`, `gross_income_labels`,
`gross_income_purchase_lines`, `labels_received` och
`purchase_lines_received`. Noder, länkar och processrader har motsvarande
`label_revenue` och `purchase_line_revenue` så UI:t kan visa breakdown utan att
behöva räkna om.
När `only_consumed=false` innehåller svaret även `client_filters.only_consumed`
med `summary`, `companies`, `nodes`, `links`, `processes` och `trace_rows` för
förverkad-vyn. Vid direkt `only_consumed=true` finns motsvarande
`client_filters.all` för att kunna växla tillbaka lokalt.
Nyare svar innehåller dessutom `client_filters.views`, en karta med
färdigräknade klientvyer från samma branchunderlag. Nyckeln har formatet
`period|periodstart|bolag|0/1`, till exempel `day|2026-06-25|GG|0`.
All-bolag-payloads får vyer för `ALL` och varje bolag i underlaget. Månad och
vecka får dagsvyer; år får månadsvyer. `0/1` anger om vyn är standard eller
`Visa endast förverkade`.

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
- aktuell buffert: `v_ask_article_buffertpallet`
- KPI-poäng: Produktivitetens coredata-/fallbackfil för `v_ask_kpi_target`

AutoStore-normalisering: transloggen kan visa `loc_to = AS1000160101`, medan
buffertpall-vyn visar `1000160101`. Sankey matchar båda formerna.

Varje aktiv branch skickas också som en rad i `trace_rows`. Raden innehåller
bland annat `origin_pall`, `current_pall`, eventuell `current_location`,
`purchase_number`, `purchase_line`, `source_row_id`, status, intäktsdelar,
`received_date`, `path` och dynamiska `step_1`, `step_2` osv. `node_ids` och
`link_keys` anger vilka diagramnoder/länkar branchen passerar, så frontend kan filtrera
spårningslistan när användaren klickar på en misstänkt nod eller länk.
CSV-exporten använder samma rader och är avsedd för snabb felsökning i Excel.
Pallid och rad-id ligger i API-svaret/exporten men sparas inte i auditloggen.

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
och ingen persistent materialisering. Endast en kort in-memory cache används för
tunga rapportfrågor.

## Källor

- `../app/backend/sankey_inbound_service.py`
- `../app/backend/routers/sankey.py`
- `../app/frontend/sankey-inbound.html`
- `../app/frontend/js/sankey_inbound.js`
- [Produktivitet](productivity.md)
- [ASK datalagring](ask-datalagring.md)
- [ASK statuskoder](ask-statuskoder.md)

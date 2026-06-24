---
title: ASK statuskoder och kodbetydelser
status: utkast
updated: 2026-06-24
tags: [ask, statuskoder, datakatalog, lager]
---

# ASK statuskoder och kodbetydelser

Kort svar: `data/external_data_catalog.json` sager vilka vyer och kolumner som
finns. Statuskodsunderlaget forklarar vad vardena i kolumner som `status`,
`type`, `depart_code`, `location.type` och liknande betyder. Det bor darfor bli
en separat ASK-kodkatalog, inte blandas in direkt i vy-/kolumnkatalogen.

## Kallunderlag

Kallan ar projektkopian
`referens/ask-statuskoder/NOWASTE-Statuskoder-240626-085153.pdf`. Den beskriver
hur Nowaste/ASK anvander status- och typkoder inom bland annat varumottagning,
koer, kranlager/robotplock, lager, order, tillverkning, korrektioner,
inventering, loggar och sandningar.

PDF:en ar ett forklarande verksamhetsunderlag. Den innehaller inga API-nycklar,
URL:er eller headernamn, men den kan anda vara intern kunskap. Om den byggs om
till datafil ska bara kodstruktur och forklaringar sparas, inte absoluta lokala
sokvagar utanfor projektet.

## Rekommenderad katalogmodell

Skapa en separat genererad katalog, till exempel:

- `referens/ask-statuskoder/NOWASTE-Statuskoder-240626-085153.pdf` - lokal
  projektkopia av kallunderlaget, git-ignorerad via `referens/*`.
- `data/ask_status_catalog.json` - genererad kodkatalog, om informationen far
  folja med till servern.
- `tools/build_ask_status_catalog.py` - framtida byggscript fran PDF/Excel till
  JSON, motsvarande `tools/build_external_data_catalog.py`.

Exempel pa postformat:

```json
{
  "namespace": "receive_log",
  "field": "type",
  "code": "91",
  "label_sv": "Flytta plocksaldo",
  "description_sv": "Flyttar plocksaldo till inlagringsko eller bufferplats",
  "source": "referens/ask-statuskoder/NOWASTE-Statuskoder-240626-085153.pdf"
}
```

`namespace` ska vara tekniskt stabilt och helst matcha API-vyn/tabellen i
katalogen, till exempel `receive_log`, `trans_log`, `pick_log`,
`order_header`, `dispatch_pallet` eller `loading_log`. `field` ska skilja pa
`status`, `type`, `depart_code`, `queue`, `flagga` och andra kodfalt.

## Skillnad mot vy-/kolumnkatalogen

| Katalog | Svarar pa | Exempel |
| --- | --- | --- |
| Vy-/kolumnkatalog | Vilken data kan hamtas? | `v_ask_receive_log` har kolumnerna `type`, `status`, `pall_num`, `item_num`. |
| ASK-kodkatalog | Vad betyder vardet? | `receive_log.type = 91` betyder flytt av plocksaldo. |

Det gor att Hamta data, pallspårning och framtida LLM-chat kan kombinera bada:
forst hitta ratt vy och kolumn, sedan forklara vardet for anvandaren.

## Viktigt for pallspårning

PDF:en forklarar flera koder som ar centrala nar ett pall-id ska foljas fran
start till slut.

| Omrade | Kod | Betydelse for sparning |
| --- | --- | --- |
| `RECEIVE_LOG (TYPE)` | `45` | Ny pall skapad via saldojustering. Ska visas som skapande/specialhandelse, inte raknas som vanlig inbound. |
| `RECEIVE_LOG (TYPE)` | `81` | Producerad via CoPack. Bor kopplas mot tillverkningsflodet nar pallkedjan byggs. |
| `RECEIVE_LOG (TYPE)` | `91` | Flytt av plocksaldo till inlagringsko eller bufferplats. Ska med i tidslinjen, men markeras separat fran vanlig mottagning. |
| `RECEIVE_LOG (TYPE)` | `100` | Nollstallt mottag. Befintlig TrackItemReport exkluderar pallen nar denna typ finns. |
| `TRANS_LOG (TYPE)` | `62`/`66` | Ny pall skapad och etikett utskriven. Kan vara viktig for framtida pallkedjeutokning om bara translogg visar skapandet. |
| `TRANS_LOG (TYPE)` | `71`-`75` | Mixpall-/pallflyttar mellan inlagringsko, buffert, pallethantering och plockplats. Viktigt nar pall-id byter fysisk kontext. |
| `PICK_LOG (TYPE)` | `46` | Omklassificering. Bor visas som specialplock/omklassning. |
| `LOADING_LOG` | `100`, `190`, `200`, `220`, `222` | Skapad/raderad/placerad/packad/ompackad plockpall. Bra for outbound-tidslinje. |

Konsekvens: pallspårningen ska inte bara filtrera bort eller rakna koder.
Den ska klassificera dem: vanlig mottagning, specialmottagning, ny pall,
omklassificering, copack, flytt, plock, packning och nollstallning.

## Flow-regel for Sankey - Inbound

`Sankey - Inbound` anvander en faktureringsregel for `Mottagna etiketter`.
Den ar en Flow-tolkning av inboundintakt: diagrammet ska bara borja med det
kunden faktiskt faktureras for.

For `v_ask_receive_log.type` och `dblog_receive_log.type` galler:

- exkludera `23`, `45`, `46`, `47`, `63`, `81`, `91` och `100`
- exkludera rader dar `qty_suf` / `Mottaget` ar `0`
- om samma `company + pall_num` senare har `type = 100`, exkluderas den
  ursprungliga mottagningsraden eftersom typ 100 nollstaller mottaget och pallen
  inte ska faktureras som mottagen etikett

Typ `91` ar inte en vanlig mottagen etikett i Sankey-starten. Den kan daremot
anvandas senare i sparningen som `Buffer Update`, eftersom den flyttar saldo
fran plockplats till ny foljbar pall/buffertkontext.

## Dokumentationsregel for filter och undantag

Nar Flow bygger logik som skippar, exkluderar, grupperar eller sarklassar en
ASK-kod ska wikin beskriva bade vad regeln gor och varfor den finns. Det racker
inte att skriva "exkludera type 45" eller "skip status 100".

Minsta dokumentation for varje sadan regel:

- vilken vy/tabell och kolumn regeln galler, till exempel `v_ask_receive_log.type`
- vilka koder/statusar som paverkas
- om raden helt exkluderas, visas separat, raknas separat eller bara far en label
- varfor regeln finns, till exempel nollstallt mottag, specialmottagning,
  saldojustering, buffertuppdatering, angerrad, arkivskydd eller rad som inte
  motsvarar fysisk pallrorelse
- om regeln ar hard kodad i befintlig Nowaste-logik, kommer fran
  statuskodsunderlaget eller ar en Flow-tolkning

Exempel: `RECEIVE_LOG.type = 100` far exkluderas i pallspårning eftersom
statuskodsunderlaget beskriver det som nollstallt mottag och befintlig
TrackItemReport-logik redan tar bort pallar med denna typ for att undvika att en
nollstalld mottagning behandlas som aktiv kedja.

## Anvandning i Flow

ASK-kodkatalogen kan anvandas pa tre nivaer:

1. I Hamta data: nar en tabell har `type` eller `status` kan UI:t visa en
   hover/forklaring eller extra kolumn med kodtext.
2. I pallspårning: tidslinjen kan visa `receive_log.type = 91` som
   `Flytta plocksaldo` i stallet for bara `91`.
3. I framtida apphjalp/LLM-chat: modellen kan fa en sanerad kodkatalog som
   kontext och svara pa fragor som "vad betyder type 45 i receive log?" utan att
   gissa.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Ar statuskoderna samma sak som API-katalogen?" | Nej. API-katalogen sager vilka vyer/kolumner som finns. Statuskodskatalogen forklarar vad vardena i dessa kolumner betyder. |
| "Varfor raknas inte type 91 som vanlig mottagning?" | PDF:en beskriver `RECEIVE_LOG (TYPE) 91` som flytt av plocksaldo till inlagringsko eller bufferplats. Den ska synas i sparning men klassas separat fran vanlig inbound. |
| "Vad betyder type 45 i receive log?" | Den beskriver att en ny pall skapats via saldojustering. I pallspårning ska den visas som specialhandelse/skapande av pall, inte blandas ihop med normal varumottagning. |
| "Varfor exkluderas type 100?" | `RECEIVE_LOG (TYPE) 100` ar nollstallt mottag. Den befintliga TrackItemReport-logiken exkluderar pallar med denna typ for att undvika att nollstallda mottag tolkas som aktiv kedja. |

## Kallor

- `data/external_data_catalog.json`
- `tools/build_external_data_catalog.py`
- `wiki/data-fetch.md`
- `wiki/ask-datalagring.md`
- `referens/ask-statuskoder/NOWASTE-Statuskoder-240626-085153.pdf`

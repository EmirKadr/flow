---
title: ASK datalagring (rensning och arkivering)
status: aktiv
updated: 2026-07-10
tags: [ask, datalagring, historik, rensning, arkivering, vyer, natverk, diagnostik]
---

# ASK datalagring (rensning och arkivering)

Kort svar: ASK/WMan kör ett schemalagt jobb som **rensar** (raderar) eller
**arkiverar** (flyttar till en separat logg-databas) tabeller i WManFrey efter ett
visst antal dagar. Det avgör hur långt bak i tiden historisk data finns kvar för
varje `v_ask_*`-vy. Reglerna ligger i
[`../referens/vyer-kolumner/ask_rensning_och_arkivering.xml`](../referens/vyer-kolumner/ask_rensning_och_arkivering.xml).
Den här sidan ska läsas innan någon agent lovar historik längre bak än
retentionen tillåter, eller felsöker varför gammal data "saknas".

## Varför detta är viktigt för historisk data

`Hämta data`, `Bearbeta`, `Produktivitet` och `Sankey - Inbound` läser `v_ask_*`-vyer som i sin tur
sitter ovanpå WManFrey-tabellerna. Jobbet sätter alltså ett tak för hur långt
bak en fråga kan ge träffar:

- **`archive="true"`** – raden flyttas från `WManFrey.dbo` till
  `log_wmanfrey.dbo` efter `days` dagar. Historiken finns kvar, men i
  arkiv-databasen, och rensas där efter ~**800 dagar** (vissa kortare). En vy som
  bara läser den operativa tabellen ser då bara de senaste `days` dagarna; äldre
  data måste hämtas ur logg-databasen.
- **`archive="false"`** – raden **raderas permanent** efter `days` dagar. Ingen
  återställning. Det här är den vanligaste orsaken till att "gammal data inte
  går att hämta".
- **`noTimeColumn="true"`** – tabellen har ingen tidskolumn och beskärs inte på
  tid (rensas på annat sätt eller inte alls i tidsled).
- **`timeColumn="..."`** – anger vilken kolumn som styr åldern när den inte är
  standardkolumnen.

Tumregel: tillgänglig historik = `days` i den operativa tabellen för
read-only-vyer; för arkiverade tabeller finns djupare historik i
`log_wmanfrey` (~800 dagar) om frågan riktas dit.

## Två databaser

| Databas | Roll | Retention |
| --- | --- | --- |
| `WManFrey.dbo` | Operativ databas. Vyerna `v_ask_*` läser primärt härifrån. | Rensas eller arkiveras efter `days` per tabell. |
| `log_wmanfrey.dbo` | Arkiv-/loggdatabas. Hit flyttas `archive="true"`-tabeller. | Rensas efter ~800 dagar (PALLET_RENT_LOG_RAW: 120). |

## Retention för tabeller bakom flows ASK-vyer

De vyer flow faktiskt använder och deras underliggande retention:

| Vy (flow) | WManFrey-tabell | Operativ retention | Arkiveras? | Historik totalt |
| --- | --- | --- | --- | --- |
| `v_ask_pick_log_full` | `PICK_LOG` | 40 dagar | Ja → `log_wmanfrey` | ~800 dagar i arkivet |
| `v_ask_trans_log` | `TRANS_LOG` | 60 dagar | Ja → `log_wmanfrey` | ~800 dagar i arkivet |
| `v_ask_palletloading_log` | `LOADING_LOG` | 60 dagar | Ja → `log_wmanfrey` | ~800 dagar i arkivet |
| `v_ask_order_log` | `ORDER_LOG` | 80 dagar | Ja → `log_wmanfrey` | ~800 dagar i arkivet |
| `dispatch_pallet_log` | `DISPATCH_PALLET_LOG` | 14 dagar | Ja → `log_wmanfrey` | ~800 dagar i arkivet |
| `v_ask_pick_location_log` | `PICKLOCATION_LOG` | **40 dagar** | **Nej (endast rensning)** | **Endast 40 dagar – raderas permanent** |

> Obs: `PICKLOCATION_LOG` (plockplatsbyten) är `archive="false"`. Plockplats-
> historik finns alltså bara **40 dagar** bak och går inte att återskapa. Detta
> är viktigt för platsanalys och all historisk plockplatsuppföljning.

## Arkivvyer i katalogen (`dblog_*`)

Den externa datakatalogen (`data/external_data_catalog.json`) innehåller separata
arkivvyer för de tabeller som arkiveras. Konventionen är:

- **Live/operativ vy** – t.ex. `v_ask_pick_log_full` ("Plocklogg Full"), läser
  `WManFrey` → bara `days` dagar bak.
- **Arkivvy** – prefix **`dblog_`** och svensk label **`Arkiv …`**, t.ex.
  `dblog_pick_log` ("Arkiv Plocklogg"), läser `log_wmanfrey` → ~800 dagar bak.

Det finns 28 `dblog_*`-vyer, en per `archive="true"`-tabell (Arkiv Plocklogg,
Arkiv Translogg, Arkiv Orderlogg, Arkiv Pallastningslogg osv.).

Obs att kolumnuppsättningen skiljer sig: `dblog_pick_log` är den råa
`PICK_LOG`-arkivvyn (~35 kolumner), medan `v_ask_pick_log_full` är berikad
(~48 kolumner). Den "fulla" berikningen finns alltså inte nödvändigtvis i
arkivvyn.

## Gäller detta automatiskt i Hämta data? (Ja, sedan 2026-06)

`Hämta data` dirigerar nu automatiskt mellan live-vy och arkivvy utifrån
periodens datum. Logiken finns i `data_fetch_service.build_retention_segments`
och styrs av tabellen `LIVE_ARCHIVE_PAIRS` (live-vy → retention-dagar →
arkivvy). Beteendet (exempel `v_ask_pick_log_full`, retention 40 dagar,
cutoff = idag − 40):

| Du frågar | Period | Vad som händer | Notis |
| --- | --- | --- | --- |
| Plocklogg full | helt inom 40 dagar | live, oförändrat | ingen |
| Plocklogg full | helt äldre än 40 dagar | **byter till** `dblog_pick_log` | "…hämtades från arkivet Arkiv Plocklogg…" |
| Plocklogg full | spänner över cutoff | hämtar **båda**, slår ihop (union) | "…spänner över gränsen…hämtade både…" |
| Arkiv Plocklogg | datum inom aktiv period | hämtar **även** live-vyn | "…ligger delvis i aktiv databas…hämtade även…" |

Detaljer:
- **Split vid cutoff.** Vid spann hämtas live för `datum ≥ cutoff` och arkiv för
  `datum < cutoff`, så rader inte dubbelräknas vid gränsen.
- **Union av kolumner.** Resultatet behåller den valda vyns `output_columns`;
  rader från den andra vyn fyller bara de kolumn-id som matchar. Kolumnerna
  skiljer sig (t.ex. 48 vs 35 för plock), så vissa fält blir tomma. Detta är
  medvetet.
- **Notis åt båda håll** sätts på planen (`plan.notice`) och visas i planpanelen
  redan vid `Tolka`, samt vilka vyer som faktiskt hämtas (`plan.fetched_views`).
- **Bara de 15 mappade vyerna** (radnivå-vyer med både live- och `dblog_`-vy i
  katalogen). Aggregat-/statistikvyer och arkivtabeller utan live-vy auto-byts
  inte.

Mappade par: `v_ask_pick_log_full`↔`dblog_pick_log` (40 d), `v_ask_trans_log`
(60), `v_ask_order_log` (80), `v_ask_palletloading_log`↔`dblog_loading_log`
(60), `dispatch_pallet_log`↔`dblog_dispatch_pallet_log` (14),
`v_ask_receive_log` (60), `v_ask_correct_log` (60), `v_ask_count_log`
(90), `v_ask_login_log` (60), `v_ask_robot_pick_log` (30), `v_ask_pick_rest_log`
(60), `v_ask_return_order_log` (60), `v_ask_trace_log` (60), `v_ask_fill_rate_log`
(30), `v_ask_pallet_rent_log_raw` (3).

## Gäller detta i Sankey - Inbound?

Ja. `Sankey - Inbound` hämtar mottagningskohorten från `v_ask_receive_log` och
följer sedan etiketter fram till idag via receive/trans/pick/loading live-vyer
och deras `dblog_*`-arkiv när perioden går utanför operativ retention. Det gör
att en gammal mottagningsperiod kan ge bättre bild än bara dagens live-vyer,
men den kan fortfarande inte se längre bak än arkivretentionen.
Outbounddelen hämtar utlastade pallar från `dispatch_pallet_log` och byter till
`dblog_dispatch_pallet_log` för dagar äldre än 14 dagar. Periodfiltret använder
kolumnen `created`, samma tidskolumn som arkiveringsjobbet använder för
`DISPATCH_PALLET_LOG`.

Viktigt undantag: `v_ask_pick_location_log` är fortfarande bara cirka 40 dagar
och arkiveras inte. Eftersom plockplatser är saldobaserade markeras äldre
plockplats-FIFO i Sankey med varning/lägre confidence när exakt platsägande inte
kan rekonstrueras.

## Hur man läser konfigfilen

Filen är en XML-konfiguration (filändelsen var ursprungligen `.html` men
innehållet är `<table .../>`-element). Den är indelad i tre block via kommentarer:

1. `<!-- Tables that should be archived -->` – `archive="true"`, flyttas till logg-DB.
2. `<!-- Tables that should only be cleaned -->` – `archive="false"`, raderas.
3. `<!-- Clear log database -->` – retention i `log_wmanfrey` (oftast 800 dagar).

Varje rad: `server`, `database`, `schema`, `name` (tabell), `days` (ålder innan
åtgärd), `archive` (true/false), och valfritt `timeColumn`/`noTimeColumn`.

## Regel: läs filterkolumn ur katalogen — hårdkoda aldrig `created`

Lärdom från ett statustest 2026-07-09 där 36 av 40 vyer felaktigt såg ut att
returnera HTTP 500. Rotorsaken var **inte** providern utan testscriptet: det
hårdkodade `created` som datumfilter för alla vyer. Endast **3 vyer** har en
`created`-kolumn (`dispatch_pallet_log`, `dblog_dispatch_pallet_log`,
`v_ask_order_log`); resten filtrerades på en kolumn som inte finns → SQL-fel på
servern → 500. Just de 3 `created`-vyerna var gröna — vilket i efterhand var
själva beviset.

Regler för alla agenter/verktyg som anropar externa vyer:

- **Välj datumkolumn per vy ur katalogen**, aldrig hårdkodat. Använd
  produktionens funktion `app.backend.data_fetch.core._preferred_date_column`
  (special-fall `dispatch_pallet_log`/`dblog_dispatch_pallet_log` → `created`,
  annars prioritetsordningen `time_stamp_int, date, timestamp, order_date, …`).
  De flesta vyer använder `timestamp`.
- **Skilj tidsfönster på arkiv och live.** `dblog_*` läser arkivet
  (`log_wmanfrey`, ~800 d) → äldre datum; `v_ask_*`/övrigt läser operativa DB:n
  (retention 3–90 d) → färskt datum. Samma datum för båda ger tomma/felaktiga
  svar för live.
- **Katalogen beskriver kontraktet, inte providerns vy-hälsa.** Katalogen listar
  t.ex. `rowid`/`order_type` som giltiga kolumner. Om providerns vy-SQL refererar
  en kolumn som saknas i bastabellen (`Invalid column 'ORDER_TYPE'`) syns det
  **bara i ett live-anrop** — aldrig i katalogen. Sådana 500 är intermittenta och
  ska rapporteras till ASK/provider-sidan, inte felsökas som vårt fel.

Snabb sanity-check innan man drar slutsatser om "API:t är nere": nå två vyer med
rätt kolumn — om någon svarar 200 är nätet/åtkomsten frisk och resten är
kontrakt-/behörighets-/providerfel per vy.

## Regel: de tre `DATA_SOURCE_API_BASE_URL`-variablerna nås bara från specifika nät

Lärdom från ett diagnostiktest 2026-07-10 (`arkiv-status.html`, ASK-vy-diagnostik)
där samma 32 vyer × 13 tenants kördes mot alla tre bas-URL:er från samma klient
(Emirs dator) och gav helt olika resultatmönster. Slutsats: **var och en av de
tre URL:erna är bara nåbar från en specifik nätverksplacering** — inte ett
generellt API-fel, inte trasig ASK-provider:

| Variabel | URL-mönster | Nåbar från | Symptom vid test utanför sitt nät |
| --- | --- | --- | --- |
| `DATA_SOURCE_API_BASE_URL` | `https://noeffectui-{tenant}.nowastelogistics.com` | Företagsnätverket (publik gateway) | 0/32 OK på alla tenants: `nås ej`/`TIMEOUT` efter ~30 s, enstaka 502/503. |
| `DATA_SOURCE_API_BASE_URL2` | `http://noeffectapi-development-{tenant}.dev-{tenant}.svc.cluster.local/api` | En **development**-server i klustret | Fungerar bra (t.ex. frey 28/32 OK). Kvarvarande fel är riktiga vy-/schemafel (HTTP 500, snabbt svar) hos providern, inte nätverksfel. |
| `DATA_SOURCE_API_BASE_URL3` | `http://noeffectapi-{tenant}.dev-{tenant}.svc.cluster.local/api` | En **prod**-server i klustret | 0/32 OK på alla tenants: `nås ej` med mycket korta svarstider (<300 ms) — anslutningen avvisas direkt, ingen timeout. |

Hur man skiljer "fel nätverksplacering" från "riktigt providerfel" i en
diagnostikrapport:

- **Konsekvent `nås ej`/`TIMEOUT` över alla vyer och tenants** på en URL, medan
  en annan URL samtidigt ger blandade OK/500 → nätverksplacering, inte API-fel.
  Testklienten stod helt enkelt på fel nät för den URL:en.
- **Snabba `nås ej`-svar (under ~300 ms)** = anslutningen avvisas direkt
  (fel nät/DNS/brandvägg). **`TIMEOUT` efter full timeout-tid (~30 s)** = kan
  nå ett hopp men inget svar kommer — kan också vara fel nät, men med en
  mellanserver som inte svarar.
- **HTTP-koder (500/502/503) med rimlig svarstid** betyder anropet nådde
  providern — det är ett providersidans fel (vy-SQL, tenant-specifikt schema),
  inte ett nätverks- eller konfigurationsfel hos oss.
- Enskild tenant med `nås ej` medan resten av samma URL ger OK (t.ex.
  `mestergruppen` mot URL2) pekar på att den tenanten saknas/är feldeployad i
  just det nätet, inte ett generellt URL-problem.

Praktisk konsekvens: kör alltid diagnostiken **från den nätverksplacering som
matchar den URL man vill testa** (företagsnät för URL1, en development-pod för
URL2, en prod-pod för URL3). Att köra alla tre från samma plats ger falska
"API är nere"-slutsatser för två av tre URL:er.

## Felsökningssvar för framtida chat

Fråga: Varför hittar jag ingen plockdata äldre än ~40 dagar i en `v_ask_pick_log_full`-fråga?
Svar: `PICK_LOG` rensas/arkiveras ur den operativa databasen efter 40 dagar. Äldre rader ligger kvar i `log_wmanfrey` i ~800 dagar men måste hämtas därifrån, inte ur den operativa vyn.

Fråga: Går det att få tillbaka plockplatsbyten från i fjol?
Svar: Nej. `PICKLOCATION_LOG` är `archive="false"` med 40 dagars retention och raderas permanent. Ingen arkivkopia finns.

Fråga: Hur långt bak kan jag i praktiken analysera plock och transporter?
Svar: Operativt så långt som tabellens `days` (t.ex. PICK_LOG 40, TRANS_LOG 60, ORDER_LOG 80). För arkiverade tabeller finns ~800 dagar i `log_wmanfrey`. För `archive="false"`-tabeller finns inget bortom `days`.

Fråga: Var ser jag exakt vilken tabell som har vilken retention?
Svar: I [`../referens/vyer-kolumner/ask_rensning_och_arkivering.xml`](../referens/vyer-kolumner/ask_rensning_och_arkivering.xml). `days` + `archive` per tabell.

Fråga: ASK-vy-diagnostiken visar "nås ej" på alla vyer för en URL men OK för en annan — är API:t nere?
Svar: Troligen inte. De tre `DATA_SOURCE_API_BASE_URL`-variablerna nås bara från olika nät (företagsnät/development-pod/prod-pod). Kör om testet från rätt nätverksplacering för den URL:en innan du drar slutsatsen att providern är nere. Se avsnittet ovan om de tre bas-URL:erna.

## Källor

- `../referens/vyer-kolumner/ask_rensning_och_arkivering.xml` – själva rensnings-/arkiveringskonfigurationen för WMan.
- `../app/backend/data_fetch_service.py` – `LIVE_ARCHIVE_PAIRS` och `build_retention_segments` (auto-byte/merge).
- `../app/backend/routers/data_fetch.py` – `_apply_retention` och `_fetch_rows_with_segments`.
- [data-fetch.md](data-fetch.md) – hur `v_ask_*`-vyer hämtas via katalog och MiniMax.
- `../referens/vyer-kolumner/views_summary_20260521_154102.xlsx` – vy-katalog.
- `../referens/vyer-kolumner/views_swedish_columns_commands_20260521_155519.xlsx` – kolumn-katalog.

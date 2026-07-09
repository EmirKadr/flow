---
title: Publik D-pak-chatt
status: aktiv
updated: 2026-07-09
tags: [publik, dpak, chat, postgres]
---

# Publik D-pak-chatt

`/dpak-fraga.html` är en fristående chatvy för kundfrågor om D-pak, zon R, AUTOSTORE, leverantörer och lådor. Sidan kräver inte inloggning och läggs inte i sidomenyn; den nås bara via direktlänk. Om `PUBLIC_DPAK_LINK_TOKEN` är satt måste både status- och meddelandeendpointen få samma token.

## Svarstid och datalager

Kunden ska aldrig trigga en picklogg-hämtning. Frågan går mot färdiga Postgres-tabeller:

- `public_dpak_pick_rows` för persistenta råplockrader från API-synken.
- `public_dpak_order_article_facts` för order/artikel-beräkningar som D-pak sålda och onödigt brutna.
- `public_dpak_order_supplier_box_facts` för zon R och lådspridning per order/leverantör.
- `public_dpak_sync_chunks` för återupptagningsbar chunk-status.
- `public_dpak_datasets` för aktuell täckning och status.

Frågan analyseras av D-pak-agenten via DeepSeek Pro när `DEEPSEEK_API_KEY` är satt. Om DeepSeek-nyckeln saknas används `MINIMAX_API_KEY`/`MINIMAX_*` som bakåtkompatibel fallback. Agenten får bara sanerad dialog, datasetstatus och resultat från sina egna verktygssteg. Den kan lista råfiler, läsa exempelrader, hämta beräkningsregler och köra validerade `SELECT`/`WITH`-frågor mot de tre råa D-pak-tabellerna. Den får inte skriva SQL utanför råtabellerna eller köra mutationer.

D-pak kräver normalt bara en egen modellvariabel i drift:

- `DEEPSEEK_API_KEY` - DeepSeek-nyckel för D-pak-agenten.
- `MINIMAX_API_KEY`/`MINIMAX_*` - fallback om DeepSeek-nyckeln saknas.

Om modellendpointen nekar, timeouter eller returnerar felaktigt svar visas en begriplig 502-feltext från backend i chatten. Feltexten ska inte bara säga `HTTPException`.

## Lokal synk

Picklogg-API:t kan inte användas från driftservern. Därför ska den tunga synken köras från en lokal dator som når API:t, men med `DATABASE_URL` satt till den Postgres-databas som ska fyllas. Servern på Render gör ingen startup-synk.

```powershell
cd app
$env:DATABASE_URL = "postgresql://..."
$env:PUBLIC_DPAK_SUPPORT_DIR = "C:\Users\emikad\OneDrive - Dole Nordic AB\Skrivbordet\projects\D-pak"
python -m backend.public_dpak_sync --from-api --start 2025-07-01 --end 2026-07-01
python -m backend.public_dpak_sync status
```

Kommandot visar en terminal-progressbar med antal chunks, procent, rader, elapsed time, ETA och aktuell vy/intervall. Det delar perioden enligt ASK-retention: gamla datum hämtas från `dblog_pick_log`, färska datum från `v_ask_pick_log_full`. Sätt `PUBLIC_DPAK_ARCHIVE_DUCKDB` eller `--archive-duckdb` för att läsa arkivdelen från lokal DuckDB-cache, samma idé som Produktivitet/Sankey använder när dblog-API:t är långsamt eller trasigt. Varje chunk sparas direkt i Postgres och markeras `complete`. Om körningen bryts fortsätter nästa körning genom att hoppa över klara chunks. `--force` hämtar om även klara chunks. `PUBLIC_DPAK_COMPANY_CODES` styr bolagsfilter och är `GG` som standard. `item_alias` och `item_attribute` läses från `PUBLIC_DPAK_SUPPORT_DIR` eller `--support-dir`.

Om terminalen inte redan har Nowaste/ASK-konfigurationen kan `--env-file` läsa en lokal fil med `DATA_SOURCE_API_BASE_URL`, `DATA_SOURCE_API_KEY`, `DATA_SOURCE_API_CLIENT`, `DATA_SOURCE_API_KEY_HEADER`, `DATA_SOURCE_API_CLIENT_HEADER` och `DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE`.

## Beräkningar

D-pak-faktor tas från `item_alias` som lägsta faktor större än 1 där enheten inte är `PAL`. Leverantör tas från `item_attribute` där `name`/`Namn` är `LastSupplierName`.

För varje plockrad räknas hela D-pak som `Plockat // Faktor`. Per order/artikel räknas `Dpak_sålda = Plockat // Faktor` och `Dpak_brutna = Dpak_sålda - Hela_Dpak`. `Dpak_brutna > 0` är onödigt brutet. Lådfrågor byggs på zon R och distinkta `pick_pall_num` per order/leverantör.

Live- och arkivrader dedupliceras innan faktatabellerna byggs, så överlapp mellan `v_ask_pick_log_full` och `dblog_pick_log` inte dubbelräknas.

## API

- `GET /api/public/dpak-chat/status`
- `POST /api/public/dpak-chat/message`

Båda är publika och får inte använda `get_current_user`. Payloaden för meddelande innehåller löpande dialoghistorik, valfri `business_code`, valfri `token` och valfri `voice`.

## Röstinspelning

Sidan har en mikrofonikon bredvid `Rensa` och `Skicka`. Ikonen har tooltip/tillgänglig etikett och byter till stoppikon medan inspelning pågår. Webbläsaren spelar in kort ljud med `MediaRecorder` och försöker samtidigt tolka svenskt tal till text med `SpeechRecognition` när webbläsaren stödjer det. Texten fylls i frågefältet så användaren kan kontrollera och redigera innan frågan skickas.

När användaren klickar `Skicka` skickas ljudet som `voice` i samma `POST /api/public/dpak-chat/message`-anrop:

- `mime_type` måste vara `audio/*`.
- `data_base64` är själva inspelningen och får vara högst 3 MB dekodat.
- `duration_ms` är inspelningens längd.
- `transcript` är webbläsarens texttolkning om den finns.

Backend validerar röstbilagan men sparar den inte. Rå base64-ljud skickas inte vidare till modellen; agenten får bara den vanliga textfrågan samt sanerad röstmetadata och eventuell texttolkning. Om webbläsaren inte kan tolka talet behöver användaren skriva frågan i fältet innan skick.

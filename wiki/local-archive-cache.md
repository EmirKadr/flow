---
title: Lokal arkiv-cache (DuckDB)
status: aktiv
updated: 2026-07-02
tags: [ask, arkiv, dblog, duckdb, cache, lokal, sankey, produktivitet, hamta-data, retention]
---

# Lokal arkiv-cache (DuckDB)

Kort svar: en **per-tenant DuckDB-databas** som speglar ASK/WMS-arkivvyerna
(`dblog_*`) så att **Sankey**, **Produktivitet** och **Hämta data** läser
historik från disk istället för via NoWaste-API:t. Opt-in via
`ARCHIVE_CACHE_ENABLED` – sedan 2026-07-04 även i **deployade miljöer**
(DuckDB-filerna ligger på flow-media-PVC:n och överlever poddomstarter);
API/dblog finns kvar som fallback. Utan cachen drar Sankeys månad/år-vyer hela
arkivet i minnet och OOM-dödar podden (1 Gi-tak), vilket var motivet för
produktionspåslaget. Läs denna sida innan du felsöker "varför läser den inte
lokalt" eller ändrar seed/topp-på-logiken.

## Varför

Live-vyerna (`v_ask_*`, 30–90 dgr) är snabba, men arkivvyerna (`dblog_*`, ~800 dgr)
är den långsamma, sköra delen: de slår i API:ts 50k-radtak (rekursiv datumfönster-
uppdelning = många sekventiella POST) och har tidvis gett 403/500. Varje historisk
fråga betalar det priset om och om igen, och `fetch_source_to_temp` (produktivitetens
hämtväg) är dessutom inte retention-medveten – den läser bara live-vyn, så snapshots
för dagar äldre än retentionen blir i praktiken tomma. Se [ask-datalagring.md](ask-datalagring.md).

## Så funkar den

- **En enda entrypoint per vy:** `run_view` bringar vyn till full täckning
  `[idag − SEED_DAYS .. igår]` och hämtar bara det som saknas i ändarna. `dblog_*`
  för datum < `cutoff = idag − retention`, **live-vyn** för datum ≥ cutoff (rikare
  kolumner, ~48 vs 35). Efter första seeden rörs `dblog_*` bara vid glapp > retention.
- **Chunkat och återupptagningsbart.** Hämtas/skrivs i bitar om `ARCHIVE_CACHE_CHUNK_DAYS`
  (default 14) och **varje chunk persisteras direkt**. Ett avbrott (appen stängs mitt i
  seeden) tappar bara den pågående biten – nästa start fortsätter där den slutade, aldrig
  en full omhämtning. Fyllning växer sammanhängande (framåt från max, bakåt från min).
- **Tom historik stoppar djup-seed.** Vid bakåtseed räknas sammanhängande datum där
  API:t inte returnerar några rader. När `ARCHIVE_CACHE_EMPTY_STOP_DAYS` nås (default
  300) markeras resten av det begärda äldre intervallet som kontrollerat/tomt och vyn
  anses klar. Det gör att ett stort `ARCHIVE_CACHE_SEED_DAYS`, t.ex. 10 000, inte behöver
  fråga hela vägen bak när datan uppenbart tagit slut.
- **Djup-seeden körs via CLI lokalt, via `ARCHIVE_CACHE_SEED_ON_START=1` i deployade
  miljöer.** Lokalt görs den tunga initiala hämtningen med
  `python -m app.backend.archive_cache_cli` (se nedan). Serverns schemaläggare kör
  annars med `deep_seed=False` och **toppar bara på redan seedade vyer framåt**.
  I k8s (där ingen kör CLI:t) sätts `ARCHIVE_CACHE_SEED_ON_START=1` i configmappen:
  första passet djup-seedar chunkat/återupptagbart, och när täckningen är komplett
  är passet en billig no-op. En poddomstart mitt i seeden tappar bara pågående chunk.
- **Ingen omseed vid varje start.** DuckDB-filen ligger kvar på disk; `run_view` ser att
  intervallet redan finns och gör inget (eller bara dagens nya dygn).
- **Parallellt och snabbt.** CLI:t hämtar varje vy i egen tråd (nätverket parallelliseras);
  DuckDB-skrivningar serialiseras per fil av ett lås och görs i **en anslutning per chunk**
  (inte per dag) – avgörande för farten.
- DuckDB:s `_row_date`-intervall plus `_archive_coverage` per vy **är** watermarken.
  `_archive_coverage` markerar lyckat hämtade datumfönster även när de saknade rader.
  Påfyllnad är idempotent (`append_rows_by_date` ersätter berörda dagar).
- **Aldrig partiell data:** en läsning svarar bara när hela det begärda datumfönstret
  ligger inom det täckta intervallet, annars returneras `None` → fallback till
  API/dblog.

Datumslosa stodvyer kan lagras som full-replace snapshots i samma DuckDB-fil.
`item_alias` uppdateras av nattjobbet och lases sedan lokalt av Sankey.
Buffertpall (`v_ask_article_buffertpallet`) ar medvetet inte en snapshot har,
eftersom den ska hamtas live vid berakning.

## Vilka vyer

Union av arkivvyer som Sankey + Produktivitet använder:
`dblog_pick_log`, `dblog_trans_log`, `dblog_receive_log`, `dblog_loading_log`,
`dblog_dispatch_pallet_log`, `dblog_order_log` (retention 40/60/60/14/80 dgr).
Definieras i
`archive_cache_sync.SYNC_ARCHIVE_VIEWS`.

Snapshotvyer: `item_alias` i `archive_cache_sync.SYNC_SNAPSHOT_VIEWS`.
Den refreshas som full replace vid samma 00:01-jobb/CLI-korning och syns i
statuspayloadens `snapshot_views`/`snapshots`. CLI:ns default kor bade
`SYNC_ARCHIVE_VIEWS` och `SYNC_SNAPSHOT_VIEWS`; `--snapshots-only` kor bara
snapshotdelen. Buffertpall ingar inte har.

## Kod

- `app/backend/local_archive_store.py` – DuckDB-lagret (schema per vy = union av
  arkiv- och live-katalogkolumner, `query_rows` återanvänder `apply_local_filters`,
  bulk-insert via registrerad DataFrame). Datumslosa snapshots anvander
  `replace_snapshot_rows`/`query_snapshot_rows`.
- `app/backend/archive_cache_cli.py` – CLI-seed med live progressbar (parallellt).
- `app/backend/archive_cache_sync.py` – `run_view` (chunkad, återupptagningsbar fyllning
  fram/bak), `_fill_range`/`_fill_one_chunk`, `seed_all` (parallell orkestrering),
  `sync_tenant` / `sync_all_tenants` och den dagliga schemaläggaren (`start_archive_cache_scheduler`,
  gate:ad på `ARCHIVE_CACHE_ENABLED` + ej produktion).
- Konsument-inkoppling (lokal-DB först, dblog/API som fallback):
  `routers/data_fetch.py:_fetch_rows`, `sankey_inbound_service.py:_fetch_segment_rows`,
  `workflow_data.py:_archive_cached_rows` (produktivitet).
- Sankey använder även arkivcachen för den del av ett live-retention-segment som
  redan är toppad till DuckDB, till exempel fram till igår. Då hämtas bara den
  återstående färska delen från live-API:t, ofta bara dagens datum. `source_status`
  visar `status=local_archive` för cacheträffar.
- Bygger på `LIVE_ARCHIVE_PAIRS` / `ARCHIVE_TO_LIVE` / `build_retention_segments` i
  `data_fetch_service.py` – gränsen (`cutoff`) är exakt densamma, så inget dygn
  dubbelräknas eller tappas i skarven.

## Konfig

| Nyckel | Default | Roll |
| --- | --- | --- |
| `ARCHIVE_CACHE_ENABLED` | `false` | Slår på cachen + schemaläggaren (lokalt och deployat; i k8s via configmappen). |
| `ARCHIVE_CACHE_DIR` | `<compiled_data_root>/archive_cache` | Var `.duckdb`-filerna ligger. |
| `ARCHIVE_CACHE_SEED_DAYS` | `400` | Hur långt bak den initiala dblog-seeden går. |
| `ARCHIVE_CACHE_CHUNK_DAYS` | `14` | Chunkstorlek för seed/topp-på (mindre = mer återupptagningsbart, fler API-anrop). |
| `ARCHIVE_CACHE_EMPTY_STOP_DAYS` | `300` | Stoppar bakåtseed när så många kalenderdagar i rad saknar rader och markerar äldre begärt intervall som täckt/tomt. `0` stänger av stoppregeln. |
| `ARCHIVE_CACHE_SEED_ON_START` | `false` | Låt servern göra den tunga djup-seeden vid start (annars gör CLI:t det, servern toppar bara på). Sätts till `1` i k8s-configmappen där ingen kör CLI:t. |
| `ARCHIVE_CACHE_SEED_WORKERS` | `5` | Parallella hämtningar (vyer/tenants) i CLI-seeden. |
| `ARCHIVE_CACHE_SYNC_HOUR` / `_MINUTE` | `0` / `1` | Daglig topp-på-tid (Europe/Berlin). |

`.duckdb`-filerna är gitignorerade och hamnar aldrig i repo.

## Synk-logg och täckning (efter nedtid)

Varje hämtning loggas i en tabell `_archive_sync_log` i tenantens DuckDB-fil
(`ts, view, source, start_date, end_date, rows, status, detail`) **och** till Python-
loggen (`logger.info`). `source`:
- `plan` – vad som ska hämtas (innan hämtning), t.ex. vilka dagar som saknas efter nedtid.
- `dblog` / `live` – en **chunk** hämtad från arkiv- respektive live-vyn (en rad per chunk).
- `empty_stop` – bakåtseed hittade `ARCHIVE_CACHE_EMPTY_STOP_DAYS` tomma dagar i rad och
  markerade det äldre begärda intervallet som täckt/tomt.
- `complete` – **hela vyns intervall är på plats** (klarmarkering när seeden blev färdig).
- `snapshot` - full-replace av en datumslos stodvy, i dag `item_alias`.

Så ser du både när varje chunk hämtas och när en vy är färdigseedad. När alla vyer för en
tenant är klara loggas dessutom `tenant=… KLAR – alla N vyer fullständigt hämtade lokalt`.

Se täckning + senaste synkar:
- **Endpoint:** `GET /api/data-fetch/archive-cache/status` (kräver `dataFetch: view`).
  Ger per tenant/vy: `ingested_start/end` (faktiska rader), `covered_start/end`
  (rader + kontrollerat tomma dagar), `missing_start/end`, `missing_days`, samt `recent_syncs`.
- **CLI:** `python -m app.backend.archive_cache_sync status`.

`missing_days` = hela dygn mellan senaste täckta dag och igår som ännu inte
fyllts på. Den dagliga schemaläggaren (och första passet vid appstart) tar
automatiskt igen glappet: dagar inom retentionen ur live, äldre glappdagar ur dblog.

## CLI-seed med live progressbar

Fyll DuckDB **utan att starta servern**, parallellt och med progressbar per tenant/vy:

```
python -m app.backend.archive_cache_cli                # alla aktiva tenants
python -m app.backend.archive_cache_cli --tenant frey  # en tenant
python -m app.backend.archive_cache_cli --tenant frey --view dblog_dispatch_pallet_log
python -m app.backend.archive_cache_cli --tenant frey --view item_alias
python -m app.backend.archive_cache_cli --tenant frey --snapshots-only
python -m app.backend.archive_cache_cli --productivity-only --productivity-start 2025-01-01 --business-code STIGAMO
python -m app.backend.archive_cache_cli --tenant frey --with-productivity --business-code STIGAMO
# Utan --productivity-start använder produktiviteten samma ARCHIVE_CACHE_SEED_DAYS-fönster till igår.
# Utan --productivity-end slutar ett explicit produktivitetsintervall igar, aldrig idag.
# Produktivitetsintervallet kors fran slutdatumet bakat och skippar redan klara snapshots/personcache.
# Produktivitetsbygget kraver fungerande DATABASE_URL. Anvand --productivity-no-prebuild for att bara hamta snapshotfiler.
python -m app.backend.archive_cache_cli --productivity-prebuild-existing  # bygg bara befintliga snapshots
# Produktivitetsloggen visar sparade snapshotdagar, API-hamtning och persondagar per chunk.
python -m app.backend.archive_cache_cli --workers 8    # fler parallella hämtningar
python -m app.backend.archive_cache_cli --status       # bara täckning + logg
```

Kräver `ARCHIVE_CACHE_ENABLED=1` och API-uppgifter i `app/.env`. Varje rad visar
tenant/vy, andel hämtat, dagar klara/totalt, rader och vilken chunk som hämtas just nu,
plus en TOTALT-rad. **Ctrl+C** avbryter; redan hämtade chunkar är sparade och nästa körning
fortsätter där den slutade (återupptagningsbart).
Produktivitetsdelen har egen chunk-progress: varje intervall visar sparade
snapshotdagar före start, saknade/gamla dagar, om API hämtades eller inte,
rader i sparade snapshots/API-svar och om persondagar redan var aktuella eller
byggdes.
Om en arkivvy stoppas av tom-historikregeln skriver CLI-slutrapporten en `INFO`-rad med
antal tomma dagar och att äldre intervall markerats som klart/tomt.

## Förbyggd översiktsrapport (overview-report)

Produktivitets **periodöversikt** (Bemanning → Produktivitet, år/månad-läge)
behöver komplett tim-/process-/diff-detalj per dag och kan därför inte läsa
`person_productivity_daily` som fullrapport. För att slippa räkna om varje dag
från snapshot-CSV vid varje öppning persisteras den **exakta** dagrapporten (samma
byggare som dag-vyn, `build_person_productivity_report_from_files`) som en gzip-JSON
bredvid snapshoten: `productivity_snapshots/<datum>/overview-report-<business_id>.json.gz`.

- **Byggs i förväg, kräver ingen live-data.** Warm-vägen
  (`productivity_cache_warm.ensure_person_and_overview_caches`) bygger dagrapporten
  **en gång** och matar både `person_productivity_daily` (Bemanning) och
  `overview-report` (Produktivitet). Alla produktivitets-CLI-lägen som redan bygger
  personcachen (`--with-productivity`, `--productivity-only`,
  `--productivity-prebuild-existing`) och nattjobbet
  (`prebuild_ready_productivity_days`) skriver därmed även `overview-report`.
- **Signaturvakt.** Kuvertet lagrar `snapshot_signature` (snapshotens `last_sync_at`)
  och `schedule_signature` (schemats antal/version/uppdaterad). Läsningen ger bara
  träff när båda fortfarande stämmer; annars miss → CSV-ombyggnad → omskrivning
  (self-heal). Så en ny snapshot-sync eller schemaändring invaliderar automatiskt.
- **Skrivs bara bredvid en faktisk snapshot-katalog** (fil ligger i snapshotens
  datummapp), aldrig som lös katalog på default-roten.
- **Läsväg:** `routers/productivity_helpers._build_productivity_report_for_date`
  läser cachen först och bygger bara om vid miss. Signaturberäkningen är defensiv,
  så en fake-session i test faller tillbaka på CSV-bygget som förr.
- IO + path: `productivity_sync_paths.productivity_overview_report_path` /
  `read_overview_report_cache` / `write_overview_report_cache` /
  `overview_report_cache_is_current`.

## Manuell körning / felsökning

- CLI-seed (rekommenderat): se ovan. Serverns schemaläggare gör **inte** den tunga seeden –
  den toppar bara på redan seedade vyer (om du vill att servern seedar vid start:
  `ARCHIVE_CACHE_SEED_ON_START=1`).
- Snabb synk utan progress: `python -m app.backend.archive_cache_sync` (sync) eller
  `... status`.
- Med cachen **av** är beteendet identiskt med tidigare (allt via API/dblog).
- Mätt lokalt: läsning ur cachen ~9× snabbare än dblog-API för en dags plock, och
  helt immun mot dblog-403/500.

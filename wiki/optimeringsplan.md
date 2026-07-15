---
title: Optimeringsplan - verifierad kandidatlista
status: aktiv
updated: 2026-07-14
tags: [prestanda, plan, oom, guardrail, llm, frontend, drift, verifierad]
---

# Optimeringsplan: verifierad kandidatlista

Kort svar: **52 kodkandidater** hittades med taxonomins feltyper som sokmonster, och
**varje enskild har granskats av en egen skeptiker** vars uppdrag var att forsoka avfarda
den. Utfall: **20 bekraftade, 17 osakra, 15 avfardade**. Dessutom **49 omvarldstekniker**
avvagda mot Flows faktiska arkitektur: **35 tillampliga, 3 delvis, 11 avfardade**.

> **Status 2026-07-14/15 - steg 0-5 byggda och matta.** Steg 1-motorerna
> (#41/#45/#42/#40) ar bit-identiska (golden oforandrade, KPI-utdatan sha256-
> identisk) med uppmatta vinster: HIB-flodet **-79 %**, `calculate_refill`
> **-63 %**, `score_kpi_events` **-26 %**, `fifo_for_art` borta ur profilen,
> allokeringsflodet kallt **-19 %**. Aven #52 (payloadmatning), #02 (gzip
> `compresslevel=6`) och #31 (`startupProbe`) byggda; steg 4 mater #08/#46/#28
> utan att fixa dem; steg 5 rattade `DEPLOY.md`. En adversariell granskning
> underkande tva blockerare och ett dussin guardrails som inte bet - alla
> atgardade i en foljandrunda (mutationstestade). **Annu inte commitat/pushat.**
> Gjorda poster markeras med [KLAR] nedan. Se [prestandasidan](prestanda-optimeringar.md)
> (kronologin) och `wiki/log.md`.

**Las detta forst - tre saker skeptikerna larde oss:**

1. **Svepagenternas siffror holl inte.** Nastan varje uppmatt vinst skrevs ned av
   granskaren. Flera var rent fabricerade. Reglen "mat, gissa inte" galler aven vara
   egna kandidater - darfor ar **0.1 (payloadmatning) ett hart forkrav**, inte en
   trevlighet.
2. **Gzip-9 doljer orjson.** `orjson` avfardades (#48) just for att `compresslevel=9`
   pa **samma event-loop** kostar ~40 ms dar json.dumps kostar ~5,8 ms. Fixa gzip forst,
   mat om, och utvardera orjson darefter - inte tvartom.
3. **`readinessProbe.initialDelaySeconds: 15` ater upp ALLA uppstartsvinster.** Tre
   kandidater (#33 prestart, #34 openpyxl, #37 compileall) ar var for sig verkliga men
   ger **0 sekunder anvandarsynlig vinst** sa lange proben har ett 15-sekundersgolv.
   **#31 (startupProbe) ar ett forkrav for att de tre ska vara vart nagot alls.**

Bakgrund: [Effektiviseringar - taxonomi](effektivisering-taxonomi.md).
Monsterkatalog och "INTE monstret om"-kriterier: [Prestandaoptimeringar](prestanda-optimeringar.md).

---

## Niva A: Bekraftade (20)

Skeptikern forsokte avfarda och misslyckades. Mekanismen ar verifierad i koden.
Vinstsiffrorna nedan ar **granskarens**, inte svepagentens.

### A1. Uppmatta vinster i berakningsmotorerna (bygg dessa forst)

| # | Fynd | Plats | Granskad vinst |
| --- | --- | --- | --- |
| **41** | `fifo_for_art` gor full boolean-scan av hela bufferten **per artikel** (kvadratisk). Hoista filtrering + sortering ut ur loopen. | `warehouse_tools/engine_core/allocation.py:730-734` | **UPPMATT: fifo-delen 1,63 s -> 0,02-0,20 s.** Hela allocate-flodet 6,6 s -> 5,1 s (~20-25 %). |
| **42** | HIB-koppling: `iterrows` + skalar `pd.to_datetime` 2x per rad; kundgruppen omfiltreras per HIB-order. Granskaren hittade **samma monster i `compute_missed_departures`** som svepet missade. | `warehouse_tools/engine_core/hib.py:195-217, 251, 299-308, 340` | **UPPMATT: ~3,3 s -> under 0,5 s** for flodet (~10x). |
| **45** | `groupby().apply(lambda)` (tappar pandas C-vag) + `iterrows` i saldo-/NPU-forarbetet. | `allocation.py:706-714, 725, 805-807` | **UPPMATT: 0,40-0,55 s** per allokerings-cache-miss (7x resp 15x - inte 100x). |
| **40** | KPI-predikatet slar upp Fran/Till/Lokation **ovillkorligt** for varje (regel, handelse). Granskaren hittade en **fjarde** ovillkorlig lookup (`sscc`, rad 430) som svepet missade. | `productivity_kpi_rules/rules.py:405-407, 430` | **UPPMATT: -23 % CPU** i `score_kpi_events` (syntetisk 60k-raders plocklogg, differentialtest bit-identiskt). |
| **39** | Sankey parsar om bolag och tidsstampel **per klientfiltervy** (upp till 512 vyer x alla rader). Forberakna en gang fore vy-loopen. | `sankey_inbound/build_outbound.py:145-152, 189-207` | Formel uppmatt: `(pick+dispatch rader) x (vyer-1) x ~5,3 us`. Vid 256 vyer: **~1,3 s per 1 000 rader** (~13 s vid 10k). |

### A2. Databas och rundresor

| # | Fynd | Plats | Granskad vinst |
| --- | --- | --- | --- |
| **21** | Vybehorighetskollen (`require_view_access`, dependency pa **96 routes**) gor 2 extra DB-rundresor pa i princip varje autentiserad request. Rollmatrisen ar **global** - varde identiskt for alla anvandare. | `deps.py:113`, `settings_service.py:937-939` | **Deterministiskt: 4 -> 2 queries** pa `/api/persons`. Latens pa dev ~40-75 ms/request (granskaren kapade svepets 74 ms). **Risk: hog** - cache-invalidering maste vara vattentat. |
| **22** | `GET /api/rfid/events` har N+1 via lazy-loadade person/activity - **och pollas var 7:e sekund** medan Bemanning ar oppen. | `rfid.py:301-305` | Verklig men **liten**: ~5-10 sparade rundresor per poll vid dagens pilot (3-8 taggade personer). Vaxer med antalet taggade. |
| **09** | SQLAlchemy-poolen kor pa defaults (`pool_size=5`, `max_overflow=10`). Granskaren: kandidaten **underskattar** problemet - 3 samtidiga produktivitetsstrommar tar 6 utcheckningar var. | `database.py:20` | Latens ej kvantifierbar utan matning. **Tillforlitlighetsvinst ar den verkliga:** QueuePool-timeout (30 s -> 500) elimineras. |
| **11** | Arkiv-cachen kor `SELECT *` utan LIMIT nar datumfilter saknas. | `local_archive_store.py:617-628` | **Ingen latensvinst** - det ar en **guardrail**. Med datumfilter (>99 % av anropen) ar fixen en no-op. Vardet ar att stanga en obunden minnesvag. |

### A3. Event-loop (C1)

| # | Fynd | Plats | Granskad vinst |
| --- | --- | --- | --- |
| **01** | Karnfils-uppladdningen kor hela spara-vagen synkront pa loopen: `read_bytes` + sha256 av 15 MB + ODBC-blobinsert + garanterat kall pandas-parse. **Mönstret ar redan tillampat pa 6 andra routrar** - coredata missades. | `coredata.py:313-386` | Ej kvantifierbar. Granskaren: fixen gor ovriga requests **FRYSTA -> LANGSAMMA** (inte opaverkade - traden delar samma 300m CPU). Kall vag, men billig och konsekvent. |
| **03** | Alla tre Excel-importvagarna parsar och skriver pa loopen. Systerrutterna `/import-rows` ar redan vanliga `def` - **asymmetrin visar att `async def` ar oavsiktligt**. | `users.py:451-462`, `persons.py:593-604`, `activities.py:686-697` | Ej kvantifierbar. Enklaste fixen: gor rutterna till vanliga `def` (FastAPI kor dem da i threadpoolen). |

### A4. Ovrigt bekraftat

| # | Fynd | Plats | Granskad vinst |
| --- | --- | --- | --- |
| **02/47** | **GZip kor pa `compresslevel=9`** (Starlettes default) synkront pa event-loopen. Ett radbyte till 6. | `main.py:319` | Mekanism bekraftad, **magnitud kraftigt nedskriven**: ~45 ms sparad CPU **per MB** gzippad body; realistiskt nagra ms till ~15 ms per API-GET, dvs 1-3 % av requestlatensen. Inte 88 ms. |
| **23** | `GET /api/bug-reports` drar hela `events_json` (rrweb-blob, tak 4 MiB) for att rita en metadatalista. Modellen sager sjalv att blobben aldrig ska fragas pa. | `bug_reports.py:179-191` | **Ingen trovardig latensvinst** pa dagens (lilla) tabell. Vardet ar att stanga en **obunden** minnesvag innan tabellen vaxer. |
| **29** | `/api/allocation/open-excel` ar web-registrerad **utan desktop-guard**: bygger hela arbetsboken i podden och **kraschar sedan alltid** (den vill oppna Excel pa servern). | `allocation.py:620-627` | **Noll ms** - ren riskreduktion. En inloggad anvandare kan med ett klick tvinga podden att materialisera hela resultattabellen som openpyxl-celler. Ta bort routen. |
| **14** | Personer: refetch + full tabellombyggnad **aven vid Escape** och ovandrat varde. | `persons_table.js:141, 175, 208, 242` | Commit-vagen: 2 -> 1 rundresa. Escape: 1 sparad GET per klick. Liten men gratis. |
| **15** | Bemanning saknar SWR trots att den ar **den mest oppnade vyn**; cachen ar en modul-`Map` som dor vid varje sidbyte (MPA). | `schedule/state.js:125-126` | **~0,8 s** (median-serversvar for `/api/schedule`) ur kritiska renderingskedjan vid kalla sidbyten. **Insats uppskriven till L.** |
| **17** | Meta-soket saknar debounce: ~800 `addEventListener` + 200 soktrangsbyggen per tangenttryck. | `meta.js:503-506` | Liten, ren klient-UX: ~10-30 ms per tecken. Ingen serverpaverkan. |
| **19** | Personliga vyer saknar AbortController/sekvensvakt. | `personal_views.js:404-436` | **Ingen prestandavinst** (backend avbryts inte av disconnect). Ren **korrekthetsfix** - fel datum kan renderas. |
| **52** | `api_benchmark` mater **aldrig payloadstorlek** - hela D-familjen (transport) ar osynlig for guardrailen. | `tools/api_benchmark.py` | **Guardrail.** Detta ar forkravet for att #02, #46 och #49 alls ska ga att bevisa. |

---

## Niva B: Osakra (17) - mat forst, bygg sedan

Mekanismen finns i koden, men vinsten ar **obevisad**. Granskaren kunde varken bekrafta
eller avfarda utan matning eller produktionsdata. **Bygg inte dessa pa gott hopp.**

| # | Fynd | Plats | Vad som saknas |
| --- | --- | --- | --- |
| **08** | **DuckDB oppnas med vardens defaults** - `duckdb.connect()` utan en enda `SET`, sa threads = **nodens** karnor och memory_limit ~80 % av **nodens** RAM, i en 300m/1Gi-podd. Samma feltyp som ffmpeg-incidenten. | `local_archive_store.py:187-194` | **Kor `SELECT current_setting('memory_limit'), current_setting('threads')` i den korande podden.** Det avgor om risken ar verklig. DuckDB kan redan lasa cgroup-limits i nyare versioner. |
| **46** | **SSE-strommarna komprimeras aldrig.** Bade Sankey och Produktivitetsoversikten laddas i praktiken **alltid** via SSE (GET ar bara fallback), och SSE ar undantaget fran gzip. Appens tva storsta JSON-svar gzippas alltsa aldrig. | `sankey.py:271-279`, `productivity.py:240-248` | **Logga `len(json.dumps(payload))` i prod.** Vinsten ligger mellan "forsumbar" (liten payload + LAN) och "flera hundra ms" (500-800 KiB + VPN). |
| **28** | **Hamta data-exporten har inget radtak alls** (`max_rows=None` -> clampningen hoppas over) och bygger hela arbetsboken i RAM. | `data_fetch.py:497-522`, rotorsak `:189-193` | **Dra `data_fetch.shown_rows` ur Seq for 90 dagar.** Ar verkliga exporter <5 000 rader ar vinsten noll och kandidaten ska avfardas. |
| **27** | Arkiv-cachens lasvag obunden. **OBS: svepets barande evidens var FALSK** - `DATA_SOURCE_RESPONSE_ROW_CAP` cappar inte API-vagen, den ar en avtrappningsgrans. Halva forslaget var direkt skadligt. | `local_archive_store.py:587-651` | `SELECT count(*) FROM dblog_trans_log` - hur stort ar arkivet egentligen? |
| **43** | Arkivcachen: `SELECT *` + all filtrering i Python (A1 i cachelagret). | `local_archive_store.py:613-628` | Granskaren: pushdown ar **inte beteendebevarande** rakt av (SQL vs Python-semantik pa NULL/case). Kraver differentialtest. |
| **31** | **Ingen `startupProbe`**; `readinessProbe.initialDelaySeconds: 15`. **Detta ar forkravet for #33/#34/#37.** | `k8s/flow.yml:229-236` | Granskaren: **0-10 s**, inte 10-20 s. Mat faktisk time-to-listen i containern (`docker run --cpus=0.3 -m 1g`). |
| **33** | `prestart` ar en hel extra Python-process, no-op efter forsta deployen. | `Dockerfile:54` | Vinst ~2-2,5 s CPU, men **0 s nedtid** sa lange #31 inte ar gjord. |
| **34** | `openpyxl` importeras ivrigt i 5 routers. | 5 routers | **272 ms** importtid + ~23,5 MB RSS. **0 s nedtid** utan #31. |
| **37** | `PYTHONDONTWRITEBYTECODE=1` utan `compileall`. | `Dockerfile:6-10` | **~190 ms CPU/process** (uppmatt). **0 s anvandarsynligt** utan #31. |
| **12** | Import-endpoints laser hela bodyn (nginx tillater 256 MB) fore storlekskollen. | `persons.py:598-600` | Robusthet, ej prestanda. Granskaren: peaken efter fix bestams av openpyxl-expansionen, inte av 5 MB. |
| **16** | Produktivitetsoversiktens cache ar en modul-`Map` som toms vid varje sidladdning -> SSE-bygget kors om vid varje besok. | `productivity_overview_core.js:24` | Ovre grans = serversvarstiden. Dagvyn ar redan forvarmd av schemalaggaren -> kanske liten vinst just dar den behovs. |
| **18** | Oversikts namnfilter bygger om hela manadsrutnatet per tangenttryck. | `overview.js:744-750` | Rutnatet byggs over den **redan filtrerade** listan -> arbetet krymper per tecken. Realistiskt 1-2 fullgrids, inte 5-8. |
| **49** | Brotli. | `main.py:319`, `Dockerfile:40-43` | Granskaren: statik-forkomprimeringen ar **kall vag**; kvar blir bara gzip 9->6, som redan ar #02. |
| **50** | `stamp_asset_versions` stamplar bara `.js`/`.css` - ikoner far `no-cache`. | `tools/stamp_asset_versions.py:31-33` | **Marginell:** ~1 (inte 3) lagprioriterad villkorad request per navigering, utanfor kritiska vagen. |
| **05** | MCP-status gor 3 oberoende RPC-anrop i serie. | `mcp/service.py:381-386` | Granskaren: naken `asyncio.gather` pa HTTP/1.1 byter 2 request-RTT mot 2 TLS-handskakningar -> **sannolikt ingen vinst**. |
| **32** | Desktop: hela backend-importkedjan (1,3 s) kors innan `QApplication` finns. | `desktop/app.py:103-108` | **Ingen vinst i total starttid** (kandidaten medger det). Andelen Python-import vs PyInstaller-boot ar omatt pa den frysta exe:n. |
| **36** | Uvicorn saknar `--timeout-graceful-shutdown`. | `Dockerfile:54` | Ovre grans ~15-25 s (inte 30 - kubelet SIGKILL:ar redan). Frekvensen omatt. |

---

## Niva C: Avfardade (15) - bygg INTE dessa

Skeptikern lyckades. Skalen ar lika larorika som fynden.

| # | Kandidat | Varfor den foll |
| --- | --- | --- |
| **48** | **orjson / ORJSONResponse** | **Den viktigaste avfardningen.** Vinsten ar ~5,8 ms pa de storsta payloads (<1 % av `/api/schedule`:s 765 ms) - medan **gzip level 9 pa samma event-loop kostar ~40 ms**. Fixar man inte gzip forst optimerar man fel sak. Dessutom 0 ms pa SSE-vagen som kandidaten sjalv aberopade. |
| **13** | Sankey-SSE avbryts aldrig | **Backend avbryts inte av att klienten stanger strommen** - bygget fortsatter oavsett. Noll serverprestandavinst. Aterstar som **korrekthetsbugg** (stale render), ska hanteras som bugg. |
| **35** | Sankey-payloadcache L2 | TTL:n (15 min) gor L2 nastan vardelos - den kan bara radda poster yngre an 15 min vid omstartsogonblicket. Anvandaren betalar redan bygget var 15:e minut. |
| **24** | Meta drar hela LLM-rasvaret | **Faktafel:** `llm_raw_response` ar inte hela Gemini-svaret utan `_extract_json_candidate` - **~0,3 kB/rad**. `analysis`-kolumnen ar dessutom alltid NULL. |
| **20** | Hamta data renderar 5000 rader som innerHTML | **Premissen ar fel** och den pekar pa fel lager. Backend-taket (#28) ar den riktiga fixen. |
| **25** | Index pa `meta_shipment_observations.updated_at` | **30 dagars retention bindar tabellen.** A5 galler *vaxande* tabeller. Mätbart 0. |
| **26** | RFID dubbel query per scan | Kall vag, indexerad TOP 1-seek. Ren dodkodstadning, inte optimering. |
| **06** | Meta-uppladdningens dubblettkoll per fil | `MAX_META_UPLOAD_FILES = 6` (inte 10+). Worst case ~0,22 s pa dev, ~10-25 ms i prod - under brusnivan. |
| **07** | Historik-chattens ORM-materialisering | Kall vag (nagra ggr/dygn, super-user). ~50-90 ms. Faller pa wikins **egna** acceptanskriterium. |
| **10** | Settings-valideringens `fullmatch` | Mekanismen ar **verklig** (inbaddade `#{VAR}` overlever!) men det ar **ingen prestandakandidat** - felet blockerar inte requests. Bygg den som robusthetsharding, inte som optimering. |
| **04** | data_fetch seriell extern I/O | **Faktafel:** `build_retention_segments` ger 1-2 planer, inte N. Alias-loopen ar 1-3 batchar pa en kall vag. |
| **44** | `_row_value` bygger om header-map per rad | Snabbvagen (`if column_id in row`) **traffar i praktiken** - kostnaden ar noll da. |
| **51** | Service workerns cache utan tak | Magnituden fel med 1-2 storleksordningar. Webblasaren evictar langt innan det blir ett problem. |
| **38** | `allocation_bridge` `exec()` | **0 ms i dagens produktion** - `PYTHONDONTWRITEBYTECODE=1` betyder att det inte finns nagon .pyc-cache att forbiga. |
| **30** | Meta-exportens kolumnbredder | Taken haller (5 000/10 000 rader, 500 vid filtrerad). Kandidaten avfardar sig sjalv. |

---

## Omvarldstekniker (49)

### Tillampliga (35) - grupperade

**Backend/DB**
- `raiseload("*")` + `load_only` - gor N+1 till ett **hart fel** i stallet for tyst latensregression. Kompletterar fragebudgettesten (som bara tacker vissa endpoints). `M/lag`
- `fast_executemany=True` pa mssql+pyodbc - batch-vagarna (produktivitetsbygget, audit) gar via ORM `add_all()` utan MSSQL-installningar. Storleksordning 10x pa bulk-insert. `M/medel`
- **Query Store + SQLCommenter** (`enable_commenter=True`) - gar fran "/api/overview tar 970 ms" till "den har SELECT:en star for 600 ms och saknar index". `S/lag`
- Pure ASGI-middleware i stallet for `BaseHTTPMiddleware` - **fem** ar staplade i `main.py`; varje request betalar anyio-maskineriet fem ganger, aven `/api/health`. `M/medel`
- Nonclustered columnstore index (NCCI) pa `user_interaction_events`, `audit_log`, `person_productivity_daily` - de append-only-och-aggregera-tabeller som vaxer obundet. `M/medel`
- Rikta SQLAlchemy-poolen mot anyio-tradpoolen (~616 av 639 handlers ar synkrona `def`). `S/lag`
- `query_cache_size`-tuning - **mat forst**, hoj inte blint. `S/lag`

**Data/berakning**
- **DuckDB som berakningsmotor**, inte bara lager - push filter/aggregering till SQL i stallet for `apply_local_filters` i Python. `M/medel`
- **DuckDB-config i container** (`threads`, `memory_limit`, `temp_directory`) - se #08. `S/lag`
- Streamad Excel-export (`openpyxl write_only` / `xlsxwriter constant_memory`). `S/lag`
- Parquet (ZSTD) i stallet for gzip-CSV for snapshots - 2-3x mindre disk, kolumnprojektion. `L/medel`
- Arrow-transport mellan DuckDB och Python. `M/lag`

**Frontend (upplevd hastighet)**
- **Speculation Rules API (prerender)** - storsta posten. Flow ar en akta MPA, ingen CSP i vagen. Sidbytet upplevs som **noll vantan**. `L/medel`
- `document.prerendering`-guards - **obligatoriskt** fore prerender, annars falsk telemetri i Historik + dubblerad backend-last. `M/lag`
- Cross-document View Transitions - **en at-rule** i `styles.css` (alla 26 sidor delar den). Noll byggsteg, noll JS. `S/lag`
- `BroadcastChannel` for cache-invalidering mellan flikar - `clearApiGetCache()` rensar bara i den flik som muterade. Sarskilt viktigt nu nar SWR **avsiktligt** serverar inaktuell data. `S/lag`
- `scheduler.yield()` for chunkad rendering. `M/lag`
- DOM-windowing / virtuell scroll utan ramverk. `L/medel`
- `CompressionStream` for rrweb-buggrapporter (JSON komprimerar 10-20x). `S/lag`

**Drift**
- `startupProbe` - se #31. `S/lag`
- `preStop` + `terminationGracePeriodSeconds` + uvicorn graceful shutdown. `S/lag`
- **Hoj/ta bort CPU-limit `300m`** - CFS-throttling. Repot **erkanner det sjalvt** i en kommentar: "en ffmpeg-korning CFS-stryper hela cgroupen". `S/medel`
- Forkomprimerad Brotli i Docker-bygget (inte ingress-brotli - ni ager inte den ConfigMapen). `M/lag`
- VPA i recommendation-only mode for att sluta gissa `JOB_MEMORY_MAX`. `S/lag`
- `gunicorn --preload` **om** ni nagonsin gar till 2 workers - sparar ~150-190 MB mot `uvicorn --workers 2`. `M/medel`
- **KRITISKT: `DEPLOY.md:293-299` har fel.** Den pastar att Sankeys `_TRACE_CACHE` var enda blockeraren for fler workers. Det stammer inte - **DuckDB-arkivcachens single-writer-fillas** ar nu den faktiska blockeraren. Hojs `--workers` idag: tyst korruption. **Ratta dokumentationen.** `L/medel`

**LLM**
- **Modellkaskad** flash-lite -> pro vid lag confidence. `GEMINI_MODEL` ar hardkodat till **dyraste** modellen for en uppgift som ar "transkribera 30 s tal". **~55 % lagre ljudkostnad.** `M/medel`
- `responseSchema` (constrained decoding) - idag satts bara `response_mime_type`, darfor maste `normalize_meta_analysis()` leta `pallet_id` bland **15 alias**. Ett schema **laser upp kaskaden** (palitligt confidence-falt). `S/lag`
- **LjudLANGD styr kostnaden, inte bitrate.** Dagens 32 kbit/s sparar uppladdningstid men **noll tokens**. Nasta besparing ar att **klippa tystnad** (`-af silenceremove`) - 40 % bortklippt = 40 % farre tokens, linjart. `S/medel`
- Prefix-cache i Apphjalpen - systemprompten blandar statiskt med `current_date`/`user_context`/`wiki_context` -> cache-hit-rate **strukturellt noll**. `M/lag`
- Token-telemetri (`usageMetadata`) - **noll traffar** i repot. Vi mater inte en enda token. Forkrav for allt ovan. `S/lag`
- Files API-ateranvandning (spara `file_uri` 48 h) - ett omtag kor idag om **hela** ffmpeg-kedjan. `M/lag`
- Kontextreduktion: `build_repo_context()` laser **hela repot** (`rglob("*")` + lowercase) varje gang anvandaren sager "du har fel". `M/lag`
- Streama LLM-svar via SSE - hela kedjan finns redan i repot. `M/lag`

### Delvis (3)
- **pandas 3 / Arrow-dtypes** - redan delvis skordad (repot kor pandas 3.0.3 + pyarrow). Kvar: byt `engine='python'` i CSV-parsningen.
- **Gemini Batch API** - 24 h-fonster ar oforenligt med att lotsvakten vantar. **Behall for backfill/omanalys enbart.**
- **`content-visibility`** - fungerar **inte** pa tabeller (size containment galler inte `<tbody>`/`<tr>`/`<td>`). Anvand windowing i stallet.

### Avfardade (11) - gor INTE detta
| Teknik | Varfor |
| --- | --- |
| **Redis/Valkey** | 1 replica, `Recreate`, RWO-volymer - ingen andra process att dela cachen med. En processlokal dict ger samma traff till noll natverkskostnad. |
| **CDN/edge-cache** | Intern app, handfull anvandare. Statiska filer **redan** optimalt cachade. Skulle **bryta** den publika 256 MB-uppladdningen. |
| **103 Early Hints** | Uvicorn implementerar inte ASGI-extensionen. Vinsten ar dessutom redan tagen av SW-cachen. |
| **modulepreload / preconnect** | Kraver `type="module"` - Flow har **noll** ES-moduler. Inga externa origins. |
| **Polars** | Flows **heta vag anvander inte pandas alls** (`csv.DictReader` + Python-loopar). |
| **`np.vectorize`** | **Noll forekomster** i repot. Fallan finns inte. |
| **Gemini context caching** | Prompten ar ~400 tokens - **under** implicit-troskeln 2 048. Inget att cacha. |
| **PodDisruptionBudget** | Vid `replicas: 1` skulle `minAvailable: 1` **blockera klusterteamets nodunderhall**. |
| **RollingUpdate (nu)** | Blockerad av DuckDB-laset. 5 s nedtid pa en intern app ar billigt. |
| **uvloop + httptools** | **Redan aktivt** via `uvicorn[standard]`. |
| **`navigator.sendBeacon`** | **Redan infort** i `telemetry.js`. |

---

## Foreslagen ordning

**Steg 0 - las upp matningen (forkrav for allt i transportlagret)**
- **[KLAR] #52** payloadmatning i `api_benchmark` + `tools/payload_budgets.json`
  + pytest-kontrakt i pre-push (`tests/tools/test_gap_payload_budget.py`).
- Token-telemetri i LLM-lagret. *(ej gjort)*
- SQLCommenter + Query Store. *(ej gjort)*

**Steg 1 - de uppmatta vinsterna (bygg direkt, siffrorna finns)** - **[KLAR]**
- **[KLAR] #41** fifo-delen 1,28 s -> borta ur profilen (allokeringsflodet kallt -19 %).
- **[KLAR] #42** flodet 2,07 s -> 0,43 s (-79 %); `compute_hib_koppling` 7,2x.
- **[KLAR] #45** `calculate_refill` 1,49 s -> 0,55 s (-63 %).
- **[KLAR] #40** `score_kpi_events` -26 %; `_canonical_header` 4,2M -> 0 anrop.
- Alla fyra bit-identiska (golden oforandrade, KPI sha256-identisk). Matt fore/efter
  pa verklig testdata; siffrorna ovan ar granskade eftermatningar, inte svepets.

**Steg 2 - ett radbyte** - **[KLAR]**
- **[KLAR] #02** gzip `compresslevel=6` + kontraktstest som laser nivan. orjson
  fortsatt avfardat tills gzip-CPU:n matts om i prod.

**Steg 3 - forkravskedjan for uppstart** - **[KLAR]**
- **[KLAR] #31** `startupProbe` i `k8s/flow.yml`, budget 180 s (>= dagens ~120 s
  sa en kall Azure SQL-start inte ger CrashLoopBackOff) + k8s-kontraktstest.
  **#33/#34/#37** darmed upplasta men annu ej byggda.

**Steg 4 - mat de osakra innan de byggs** - **[KLAR] (matning byggd, fixarna medvetet EJ byggda)**
- **[KLAR] #08** DuckDB-defaults exponeras som ren *information* i healthchecken
  (`GET /api/healthcheck` -> falt `duckdb`; CLI `python -m tools.healthcheck duckdb`).
  Far aldrig lyfta global status. Las av poddvardet innan #08-fixen byggs.
- **[KLAR] #46** SSE-payloadstorlek (ra + gzip-6) loggas till Seq. Beslutstroskel:
  ra >= ~300 KiB **och** overforingstid >= ~150 ms.
- **[KLAR] #28** `data_fetch.shown_rows` avlases ur Seq (P95 < 5000 => avfarda).

**Steg 5 - rakta dokumentationen** - **[KLAR]**
- **[KLAR] `DEPLOY.md`** - den verkliga blockeraren for fler workers ar DuckDB-
  arkivcachens single-writer-fillas (`sankey_inbound/fetch.py` anropar
  `covered_range()` utan try/except), plus processlokala `_RATE_HITS` och
  `background._STATUS` - inte Sankeys trace-cache.

## Kallor

- [Effektiviseringar - taxonomi](effektivisering-taxonomi.md)
- [Prestandaoptimeringar](prestanda-optimeringar.md) - "INTE monstret om"-kriterierna
- [Prestanda - leveranslagret](prestanda-leveranslager.md)
- Kartlaggning 2026-07-14: 10 kodsvep + 5 omvarldsagenter + **52 adversariella skeptiker** (en per kandidat)

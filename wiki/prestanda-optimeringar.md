---
title: Prestandaoptimeringar - monster, vinster och revisionschecklista
status: aktiv
updated: 2026-07-08
tags: [prestanda, latens, databas, cache, vektorisering, revision, checklista]
---

# Prestandaoptimeringar: monster, vinster och revisionschecklista

Kort svar: den har sidan ar en **kunskapsbas over prestandamonster** vi
faktiskt tjanat sekunder/millisekunder pa i Flow. Den har tva syften:

1. **Framatbyggnad** - lar oss undvika samma misstag nar vi bygger nytt.
2. **Revision** - varje monster har en *signatur* (hur man hittar det med
   `grep`) sa vi kan svepa hela koden och kontrollera om vi gor liknande
   missar igen.

Alla vinster nedan ar **beteende-bevarande** - ingen optimering andrar vilken
data anvandaren ser (verifierat med golden-karakterisering, differentialtester
och full testsvit). Leveranslagret (gzip/ETag/service worker) har en egen sida:
[Prestanda - leveranslagret](prestanda-leveranslager.md). Arkivcachen har sin:
[Lokal arkiv-cache (DuckDB)](local-archive-cache.md).

## Viktig kontext innan du tolkar siffror

- **Dev-latens != prod-latens.** Development-klustret kor hos Proact med SQL i
  Azure northeurope: **~37 ms per DB-fraga** ren rundresa. I produktion ligger
  app och DB i samma datacenter, sa siffran ar mycket lagre. Extrapolera aldrig
  dev-matningar rakt till prod (kalla: Mikael Hallin, 2026-07-04).
- **Foljden:** pa dev domineras latensen ofta av **antal rundresor x 37 ms**,
  inte av datamangden. Darfor ar N+1 och onodiga per-request-queries sarskilt
  dyra just dar - och en fix som tar bort rundresor syns tydligt.
- **Mat, gissa inte.** Kor `python -m tools.api_benchmark --base-url <miljo>
  ... --label fore-X` fore och `--compare` efter deploy. Baslinjer ligger i
  `artifacts/api_benchmark/`.

---

## Anti-monster-katalog

Varje post: **signaturen** (hur den ser ut / hur man greppar den), **fixen**,
**exempel** med datum och uppmatt vinst, och **nar den INTE galler**.

### A. Databas och API-latens

#### A1. Ladda hela tabellen och reducera i Python

Det enskilt dyraste monstret vi hittat. En query drar in manga/alla rader och
Python raknar/deduplicerar/summerar dem - jobb som databasen kunde gjort och
returnerat ett litet resultat.

- **Signatur:** `rows = list(db.execute(select(Model)...).scalars())` eller
  `.scalars().all()` / `db.query(M).all()` **foljt av** `set(...)`, `Counter(...)`,
  `sum(r.x for r in rows)`, `len([...])`, `max/min(...)`, eller en dict-rakning.
  Grep: `\.scalars\(\)\.all\(\)|list\(db\.execute` och `Counter\(|sum\(|= set\(`.
- **Fix:** flytta reduktionen till SQL - `GROUP BY` + `COUNT`/`SUM`,
  `DISTINCT`, `EXISTS`/`.first()`/`LIMIT 1`. Databasen returnerar ett litet
  resultat i stallet for hela tabellen.
- **Exempel:** `audit_logs.interaction_coverage` laddade hela
  `user_interaction_events` (obundet, `period=all`) for att bygga en mangd
  distinkta (vy, kontroll)-par + rakna. Ersatt med `GROUP BY view_id,
  control_id`. **3910 ms -> 173 ms (-96 %, ~23x)** mot riktig dev-data
  (2026-07-08).
- **INTE monstret om:** raderna faktiskt behovs (serialiseras/returneras till
  klienten), mangden ar redan `.limit()`:ad och liten, eller reduktionen inte
  gar att uttrycka i SQL (Python-normalisering, JSON-harledda falt, cross-row-
  tillstand). Ett 28-filers svep 2026-07-08 bekraftade att `coverage` var den
  **unika** obundna boven - alla andra "ladda-och-reducera" var bundna
  (en dag/vecka/`.limit()`), behovde raderna, eller var ej SQL-uttryckbara.

#### A2. N+1: en query per rad i en loop

- **Signatur:** `db.query(...)`/`db.execute(...)`/ORM-relationsaccess **inuti**
  en `for`-loop; en DB-rundresa per person/order/dag.
- **Fix:** en bulk-query med `IN (...)` + join, slut sedan upp i en dict i
  Python. `for pid in ids: q(pid)` -> `q(ids)` + `{row.id: row}`.
- **Exempel:** personliga schemat (`public.py`) korde en mall-query per
  person x veckodag + en tackningsquery per person x veckodag x timme
  (~antal_personer x 63 queries). Batchat till ~3 queries (2026-07-08).
  Staffing-kalkylatorn byggde schemasegmenten pa nytt per kalkylator - byggs nu
  en gang (2026-07-08).
- **Exempel:** buggrapport #1 (2026-07-07) visade att drag-kopiering i
  Bemanning blev seg i development. Vantetider runt rapporten visade
  `POST /api/schedule/cells` pa **16,96 s** och senare 7-dagarsdata hade
  max **60,0 s/504**. Rotorsaken i fixbar kod var inte radvolym utan att bulk-
  mutationerna laste aktuell timme/dag i en separat DB-rundresa per mal.
  `/api/schedule/cells`, `/api/schedule/hours/restore` och
  `/api/overview/days/bulk` batchlaser nu befintliga schemaceller per datum och
  bygger efter-snapshots fran minnet. Pa dev-topologin betyder det ungefar
  `(antal mal - antal datum) * 36-37 ms` sparad vagtid bara pa las-sidan:
  30 timmar/dagar sparar cirka **1,0 s**, 100 sparar **3,6 s**, 200 sparar
  **7,2 s**, innan minskad lock-/flush- och timeout-risk raknas. Nar app och DB
  flyttas narmare blir varje rundresa billigare, men batchningen tar bort den
  multiplicerande kostnaden och ar beteendebevarande.
- **INTE monstret om:** loopen redan ar en bulk-query som just eliminerar N+1.

#### A3. Over-fetch: hamta kolumner/rader som inte anvands

- **Signatur:** `SELECT`/ORM som drar in stora kolumner (t.ex. `LargeBinary`,
  hela CSV-/JSON-blobbar) nar bara metadata/nagra falt anvands.
- **Fix:** `defer(Model.stor_kolumn)` eller `select(bara, de, kolumner, som,
  behovs)`. Ingen lazy-load kan triggas om ORM-objekten inte lacker ut.
- **Exempel:** `coredata_service._coredata_db_rows_by_type` drog hela
  `data`-kolumnen (tiotals MB binar CSV per filtyp: item ~9,5 MB, item_attribute
  ~15 MB) bara for att visa filstatus. `defer(CoreDataFile.data)`:
  **615 ms -> 384 ms (-38 %)** mot dev (2026-07-08).

#### A4. Per-request DB-rundresa for "liveness"

- **Signatur:** nagot som pingar databasen vid **varje** anslutningsuttag/request.
- **Fix:** ta bort det och skydda pa annat satt.
- **Exempel:** `pool_pre_ping` korde `SELECT 1` vid varje connection-checkout -
  **~37 ms per request** fran k8s-podd till Azure SQL. Borttaget, ersatt med
  `pool_recycle=1500` (haller anslutningar yngre an Azure-gatewayens
  30-min idle-timeout) (2026-07-04).

#### A5. Saknat index pa het filter-/sort-kolumn

- **Signatur:** `filter(created_at >= X)` / `order_by(created_at.desc())` /
  join/`group_by` pa en kolumn utan index, pa en **vaxande** tabell.
- **Fix:** composite-index i en Alembic-migration (matcha WHERE + ORDER BY).
  Hoppa index pa kolumner som bara filtreras med ledande-wildcard
  `ilike('%x%')` - de ar osargbara for B-tree.
- **Exempel:** `audit_log` saknade allt utom `(entity_type, entity_id)` trots
  att systertabellerna (`user_wait_metrics`, `user_interaction_events`) redan
  hade `created_at`/`business_id`/`user_id`-index. Migration `0048` la till
  `(created_at)`, `(business_id, created_at)`, `(user_id, created_at)`
  (2026-07-08). **Skalforsakring:** effekten vaxer med tabellstorleken; syns
  svagt sa lange tabellen ar liten.

### B. CPU, minne och compute

#### B1. pandas: iterrows / apply(axis=1) / loop-over-grupper

- **Signatur:** `for _, row in df.iterrows()`, `df.apply(..., axis=1)`,
  `for key, grp in df.groupby(...)` som bygger en subframe per grupp, eller en
  `groupby().agg()` med **Python-callable/lambda** (tappar pandas kompilerade
  C-vag och looper i ren Python per grupp).
- **Fix:** vektorisera - masker, `.map()`, inbyggda strang-aggregeringar
  (`"first"/"sum"/"max"`), `groupby().transform()`/`.idxmax()`.
- **Exempel (2026-07-07/08):**
  - Dispatchkontroll: `iterrows` + per-grupp-loop -> vektoriserade mask/`.map()`
    / `groupby().first()`. **1,60 s -> 0,016 s (-99 %, ~100x).**
  - `observations._recompute_artikel_max`: per-artikel outlier-max i en
    Python-loop -> `groupby.quantile` + `idxmax`. **8,3 s -> 0,20 s (~41x)**
    vid 40k artiklar.
  - (Systerverktyget D-pak: `groupby().agg()` med egen `def first`/lambda over
    ~130k grupper: **52 s -> 0,4 s (~130x)** - ursprunget till hela den har
    jakten.)
- **Kritiskt:** verifiera att den inbyggda aggregeringen har **exakt** samma
  semantik (t.ex. `"first"` = forsta icke-NaN, `idxmax` = forsta forekomsten;
  akta flyttalsassociativitet nar Python-summa byts mot SQL/pandas-`SUM`).

#### B2. Ladda hela arkivet/historiken i minnet

- **Signatur:** en vy laser hela ett arkiv/en stor historik till minne per
  anrop utan cache.
- **Fix:** on-disk cache (DuckDB / gzip-JSON) som delas mellan workers och
  overlever omstart.
- **Exempel:** Sankeys manad/ar-vyer utan cache drog hela dblog-arkivet i
  minnet (lokal repro: 132 -> 449+ MB pa 20 s) och **OOM-dodade podden**
  (1 Gi-tak) -> 502 pa hela appen. Lost med DuckDB-arkivcache pa PVC
  (2026-07-03/04). Se [Lokal arkiv-cache](local-archive-cache.md).
- **Beslaktat:** trace-cachen gjordes tvaskiktad (L1 processlokal + L2 gzip-JSON
  pa disk delad av alla workers) sa drill-down overlever processbyte utan att
  flytta hundratals MB till MSSQL (2026-07-07).

#### B3. Rakna om samma sak per anrop/vy

- **Signatur:** en dyr berakning kors om fran grunden i en loop/per vy trots att
  indata ar oforandrat.
- **Fix:** berakna en gang, aterananvand (hoista ut ur loopen, `cached_property`
  pa objekt som byts vid omladdning, eller forbyggd cache med signaturvakt).
- **Exempel (2026-07-08):**
  - Sankey `build_package_ladders` (over >50k alias-rader) byggdes om i varje
    `_build_outbound_sankey` - upp till **512x per cache-miss**. Hoistat till
    en gang per payload.
  - Hamta data-katalogens matchning (regex-tung `_normalize`/`_tokens` pa
    statisk katalogtext) precomputas nu via `cached_property`:
    **26 ms -> 4 ms per plan.**
  - Produktivitetsbygget: `_canonical_header` (unicode-NFKD + strip-combining +
    regex) kanoniserade om samma handfull kolumnnamn i `_row_text` for **varje
    rad** -> ~4M anrop per dagsbygge (CPU-bundet). `lru_cache(maxsize=8192)` pa
    modulniva - coerce till `str` utanfor cachen sa nyckeln ar hashbar och
    beteendet identiskt - kollapsar anropen till nagra hundra unika och **delar
    cachen mellan bolag/byggen**: **~10 s -> ~1,7 s per bygge (~6x)**, 3 bolag i
    serie **~30,5 s -> ~5,2 s** (2026-07-08). En 0-personers-tenant foll ocksa
    9,8 s -> 1,4 s, vilket bevisade att kostnaden var den delade kanoniseringen,
    inte per-person-arbete.
  - **Motforsok som mattes langsammare och forkastades (mat, gissa inte):** att
    cacha `(kanonisk, verklig header)` per kolumnuppsattning i `_row_text` med
    `tuple(row.keys())` som nyckel. Tuple-bygget + hashningen per anrop (343k
    ggr) kostade **mer** an den redan billiga per-header-cachen: 5,2 s -> 8,8 s
    for 3 bolag. Reverterat. Lardom: nar hotspoten forst ar memoiserad ar nasta
    lager ofta call-overhead, inte berakning - en till cache kan gora det varre.
- **Beslaktat (cache-lager, 2026-07-03):** forbyggd `overview-report`-cache
  (gzip-JSON med snapshot+schema-signatur) sa ar/manad-vyn slipper rakna om fran
  CSV; `productivity_cache_warm` bygger dagrapporten en gang och matar bade
  `person_productivity_daily` och `overview-report`.

#### B4. Compute-then-filter: dyrt jobb for hela datat, bara delmangd visas

- **Signatur:** en dyr berakning gors for **alla** rader/grupper men resultatet
  konsumeras bara for en liten filtrerad delmangd.
- **Fix:** skjut upp/forfiltrera sa den dyra logiken bara kors for det som visas.
- **Exempel:** orderkontrollen byggde en dyr kund/transportor/orders-lista for
  **varje** sandningsgrupp men behovde den bara for de fa som **flaggas**.
  Forfiltrerat vektoriserat. **0,255 s -> 0,033 s (-87 %)** (2026-07-08).
  (Samma insikt fran D-pak: en dyr Lokationer-join flyttades sa den bara korde
  for de ~900 rader som faktiskt visades.)

### C. Event-loop och samtidighet

#### C1. Blockerande arbete i en `async def`-route

Storst systemeffekt: appen kor **en uvicorn-worker**, sa tungt synkront arbete
pa event-loopen fryser **alla** requests medan det pagar.

- **Signatur:** i en `async def`-route kors synkront tung CPU, pandas, `requests`
  / `urllib`, `subprocess.run`, eller fil-I/O **utan** avlastning.
- **Fix:** `await run_in_threadpool(fn, ...)` eller `await asyncio.to_thread(fn,
  ...)`. Behall try/except **runt** await:t sa felmappningen bevaras.
- **Exempel (2026-07-08):** allocation (pandas-CSV + GitHub-PUT +
  `resolve_sources` externa hamtningar), meta_uploads (`ffprobe`, 20 s-tak),
  data_fetch (O(N)-aggregering over upp till 50k rader), assistant (laser alla
  wiki-filer + hela repo-tradet). Alla flyttade till trad.
- **Notera:** en request-bunden SQLAlchemy-Session far bara anvandas fran en
  trad i taget (sekventiellt, aldrig samtidigt).

### D. Transport och upplevd hastighet (frontend)

Har finns en egen sida - [Prestanda - leveranslagret](prestanda-leveranslager.md).
I korthet, monstren:

- **D1. Okomprimerad/ocachad leverans** -> gzip-middleware + innehalls-hash-
  stamplade statiska filer med ett ars immutable-cache + ETag/304 pa API-GET +
  service worker (cache-first for `?v=`-filer) (2026-07-06).
- **D2. Vit skarm vid sidbyte** -> SWR (stale-while-revalidate): mala cachad
  snapshot direkt, revalidera i bakgrunden. Pilot: Personer + Oversikt
  (2026-07-07).
- **D3. Refetch av redan hamtad data** -> aterananvand client-side (Sankeys
  helarsfilter aterananvander redan hamtad data i stallet for ny fetch).

### E. Guardrails - forebygg regressioner

Optimering ar fardskrivbord; det verkliga vardet ar att inte tappa vinsten igen.

- **E1. Frageburget-kontrakt per endpoint.** Kontraktstest laser antalet SQL-
  frager per karnendpoint (marginal +2). En N+1 over personerna ger +30 och
  **sprANger taket i pre-push** innan det nar prod (2026-07-07).
- **E2. Latensbudgetar.** `tools/latency_budgets.json` + `api_benchmark
  --budget` (avslutar med kod 2 vid overtradelse); dragna till 60-80 % marginal
  over uppmatta medianer.
- **E3. Before/after-benchmark.** `tools.api_benchmark` mot en korande miljo -
  regel i AGENTS.md for prestandapaverkande andringar. Effekt ska matas, inte
  gissas.

---

## Snabb revisionschecklista (grep-signaturer)

Kor dessa mot `app/backend` nar du vill svepa efter nya forekomster:

| Monster | Grep-signatur (startpunkt) |
| --- | --- |
| A1 ladda+reducera | `\.scalars\(\)\.all\(\)` / `list\(db\.execute` naragranns `Counter\(|sum\(|= set\(|len\(\[` |
| A2 N+1 | `db\.(query\|execute\|get)\(` inuti en `for`-loop |
| A3 over-fetch | `LargeBinary`/blob-kolumn laddad dar bara metadata lases |
| A4 per-request-ping | `pool_pre_ping` / `SELECT 1` per request |
| A5 saknat index | `order_by(...created_at` / `filter(...created_at` mot vaxande tabell utan `Index(...)` i modellen |
| B1 pandas-loop | `iterrows\(\|itertuples\(\|apply\(.*axis=1\|groupby\(.*\)\.agg\(` med lambda/def |
| B2 minnesladdning | hela arkiv/historik last per anrop utan cache |
| B3 omrakning | dyr berakning i loop/per vy utan hoisting/cache; ren `str`-transform (unicode-normalize/regex/parse) anropad per rad utan `lru_cache` |
| B4 compute-then-filter | dyrt per-rad-jobb dar resultatet bara anvands for en flaggad delmangd |
| C1 blocking-in-async | `async def`-route med `subprocess`/`requests`/`urllib`/pandas/tung CPU utan `run_in_threadpool`/`to_thread` |

Nar du hittar en kandidat: bekrafta att (1) mangden/kostnaden ar **verklig**
(stor/obunden × het vag - inte en engangs-batch), och (2) fixen ar **bit-
identisk** (NaN/tom-strang, ordning, dtype, flyttalsassociativitet,
transaktioner). Verifiera med differentialtest eller golden-karakterisering.

## Kronologi (kort)

- **2026-07-03/04:** DuckDB-arkivcache pa i deployade miljoer (Sankey OOM-fix);
  forbyggd overview-report-cache + `productivity_cache_warm`; `pool_pre_ping`
  bort (-37 ms/req); API-benchmark-verktyg + AGENTS.md-regel; miljotopologi/DB-
  latens dokumenterad.
- **2026-07-06:** Leveranslagret - gzip, immutable-cache, ETag/304, service
  worker, latensbudget.
- **2026-07-07:** SWR-pilot (Personer/Oversikt); frageburget-kontrakt + atdragna
  latensbudgetar; trace-cache tvaskiktad.
- **2026-07-07/08:** Warehouse-vektorisering (dispatch -99 %, observations ~41x,
  orderkontroll -87 %, ordersaldo O(N²)->O(N)); backend-latenssvep - SQL-agg
  (coverage -96 %), `defer` (coredata -38 %), audit-index (0048), blocking-in-
  async -> trad, N+1-batchning, omrakning-en-gang; 28-filers svep som bekraftade
  att coverage var den unika ladda-hela-tabellen-boven.
- **2026-07-08:** Bemanning drag-fyll, undo/redo och Oversikt dagdrag
  batchlaser aktuella schemaceller i stallet for en rundresa per mal. Guardrail:
  fragebudgettest for `/api/schedule/cells` och SELECT-budget for
  `/api/overview/days/bulk`.
- **2026-07-08:** Produktivitetsbygget - `_canonical_header`-memoisering
  (B3, ~10 s -> ~1,7 s/bygge, ~6x; ett per-kolumnuppsattnings-motforsok mattes
  langsammare och forkastades). Schemalaggaren forbygger nu **idag for alla
  aktiva bolag** varje 30-min-pass (staggrat, egen kortlivad session per bolag)
  sa personalen aldrig triggar on-demand-bygge kl 05; on-demand kvar som matbar
  fallback (loggtagg `productivity_overview_ondemand_build`). Se
  [Produktivitet](productivity.md).

## Kallor

- `../app/backend/routers/audit_logs.py` (A1: interaction_coverage SQL-agg)
- `../app/backend/coredata_service.py` (A3: defer)
- `../app/backend/models.py`, `../app/alembic/versions/0048_audit_log_indexes.py` (A5)
- `../warehouse_tools/engine_core/reports.py`, `observations.py`, `ordersaldo.py` (B1/B4)
- `../app/backend/sankey_inbound/build.py`, `build_outbound.py`, `trace.py` (B2/B3)
- `../app/backend/routers/allocation.py`, `meta_uploads.py`, `data_fetch.py`, `assistant.py` (C1)
- `../app/backend/routers/public.py`, `staffing_calculator_service.py` (A2)
- `../app/backend/routers/schedule_shared.py`,
  `../app/backend/routers/schedule_mutation_routes.py`,
  `../app/backend/routers/overview.py`,
  `../tests/services/test_query_count_budgets.py` (A2: schema/oversikt-bulk)
- `../tools/api_benchmark.py`, `../tools/latency_budgets.json` (E)
- `prestanda-leveranslager.md`, `local-archive-cache.md` (D, B2)

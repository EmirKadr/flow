---
title: Wiki-logg
status: aktiv
updated: 2026-07-10
tags: [wiki, logg]
---

# Wiki-logg

## [2026-07-10] ingest | Meta: Dispatchpallar-uppslag fick aldrig tenant, fixat med tenant-fallback

Emir korde `meta process-queue` mot flow-development och fick tva rader med
ratt pall-id/avvikelser men tom Ordernummer/Sandningsnummer/Anvandare/Kund och
status `Kontrollera`. Grundorsak: `lookup_dispatch_pallet_fields()` i
`meta_analysis_service.py` anropade `_api_client()` utan tenant. Nar
`DATA_SOURCE_API_BASE_URL` ar en multi-tenant-mall (`.../noeffectui-{tenant}...`,
sant pa flow-development) blev anropet ett bokstavligt vardnamn med `{tenant}`
kvar i strangen — alltid DNS-fel, alltid `ExternalDataClientError`, for alla
pall-id. Meta-uppladdningar ar publika/inloggningsfria och saknar
`business_id`, sa det finns ingen inloggad anvandare att harleda tenant fran
(sa som t.ex. Hamta data gor via `Business.tenant`).

Fix: ny installning `META_ANALYSIS_DATA_SOURCE_TENANT` (default `frey`, den
enda verksamheten som anvander Meta just nu), skickas in i
`_api_client(tenant=...)`. Hardkodat i `k8s/flow.yml` (inte en hemlighet, ingen
Octopus-platshallare). Om fler verksamheter borjar anvanda Meta racker inte en
global tenant langre. Detaljer i `meta-upload.md`.

## [2026-07-10] ingest | Meta: fjarrtriggad analys via flow_cli.py meta process-queue

Emir ville kunna kora sandningsanalysen fran sin egen dator utan att klicka
`Analysera` rad for rad i UI:t. `tools/meta_analysis_worker.py` kravde direkt
DB-atkomst sa den passar inte fran en extern dator; losningen blev istallet
ett nytt subkommando i `tools/flow_cli.py` (`meta process-queue`) som
ateranvander CLI:ts befintliga inloggning/cookie-jar, hamtar sandningsrader
per status och anropar den redan befintliga `/api/meta/uploads/{id}/analyze`
for varje — samma serverflode som `Analysera`-knappen, ingen ny backend-kod.
Knappen finns kvar oforandrad. `auth login` faller dessutom tillbaka pa
`FLOW_E2E_USERNAME`/`FLOW_E2E_PASSWORD` (samma env-konvention som
`tools/e2e/env.py`) om `--username`/`--password` inte anges. Detaljer i
`meta-upload.md`.

## [2026-07-10] ingest | ASK-vy-diagnostik: varje ASK-länk är bunden till ett eget nät

Nya ASK-vy-diagnostiken i `arkiv-status.html` kördes mot tre olika ASK-bas-URL:er
(satta via `DATA_SOURCE_API_BASE_URL`/`2`/`3`) från samma klient (Emirs dator) och
gav helt olika mönster: den publika gatewayen (`noeffectui-{tenant}...`) 0/32 OK
på alla tenants (`nås ej`/TIMEOUT), development-klustret
(`noeffectapi-development-{tenant}...svc.cluster.local`) 22–28/32 OK,
prod-klustret (`noeffectapi-{tenant}...svc.cluster.local`) 0/32 OK med mycket
snabba `nås ej`-svar. Slutsats: varje länk är bara nåbar från sin egen
nätverksplacering (företagsnät / development-pod / prod-pod) — inte ett
generellt API- eller providerfel. Viktigt: lärdomen är knuten till **länkarna**,
inte till vilken variabel-slot (`_BASE_URL`/`_2`/`_3`) som råkar peka på dem —
de variablerna pekas om över tid. Dokumenterat i `ask-datalagring.md` med tabell
per länk + hur man skiljer "fel nät" (konsekvent nås-ej över alla vyer) från
"riktigt providerfel" (HTTP-kod med rimlig svarstid på enstaka vyer).

## [2026-07-09] lint | ASK-vystatus: hårdkodat `created` gav 36/40 falska 500

Statustest över 40 vyer × 13 tenants såg först ut att visa 36/40 trasiga (HTTP
500). Rotorsak: testscriptet hårdkodade `created` som filterkolumn, men bara 3
vyer har den. Med rätt kolumn per vy (`_preferred_date_column`) och skilda
arkiv/live-fönster föll felen till en handfull genuina providerfel (`Invalid
column 'ORDER_TYPE'` m.fl., intermittenta) + `v_ask_kpi_target` 403 + Mestergruppen
404. Regeln "läs filterkolumn ur katalogen, hårdkoda aldrig `created`" tillagd i
`ask-datalagring.md`.

## [2026-07-09] ingest | Meta: stadmigration for label-kolumnerna planerad till efter 2026-08-10

Beslut Emir: de historiska `label_image_*`-kolumnerna droppas forst nar
retentionen (30 dagar) tomt alla referenser — efter 2026-08-10 ar det en ren
no-data-migration. Omfattning och verifieringssteg dokumenterade som TODO
hogst upp i `meta-upload.md`.

## [2026-07-09] ingest | Meta: stillbildsfunktionen borttagen + ASK-uppslag alltid till anteckning

Beslut av Emir: etikettstillbilden anvandes inte och dess videoavkodning var
OOM-boven — funktionen ar helt borttagen (backend-generering, Etikett-kolumn,
stillbildsnedladdning, `META_LABEL_STILL_TIME_SECONDS`, export-kolumn).
Analysens ffmpeg ror nu bara ljudsparet. Historiska `label_image_*`-kolumner
ligger kvar i DB men fylls aldrig; radering/retention stadar dem fortfarande.
Dispatchpallar-uppslaget ar harddat: ingen traff, API-fel, ovantat fel eller
okonfigurerad datakalla blir alltid en osakerhetsanteckning med pall-id
(status Kontrollera) — aldrig analysis_failed. Uppdaterade meta-upload.md,
ui-map.md och data-model.md.

## [2026-07-09] ingest | Meta-analys del 2: ffmpeg-tradar grupp-OOM-dodade podden

Efter deploy av platshallar-fixen kraschade podden IGEN vid Analysera (502,
inget i Seq). Seq-tracen visade att Gemini-analysen nu LYCKAS (upload + 10 s
generateContent) och att doden intraffade direkt efter Dispatchpallar-
uppslaget — dvs. i etikettstillbilds-steget. Lokal matning pa samma video
(1488x1984@120fps h264): ffmpeg-avkodning med default-tradar toppar ~254 MB,
med `-threads 1` ~60 MB. Cgroup v2 grupp-OOM-dodar hela containern, inte bara
ffmpeg. Fix: tradtak pa alla tre ffmpeg-anropen (ljud 1, stillbild 1,
playable-transkodning 2) + kontraktstest som lasar flaggorna. Uppdaterade
felsokningsraden i `meta-upload.md` med bekraftad orsak.

## [2026-07-09] ingest | Meta-analys: Octopus-platshallare kraschade Gemini-anropet

Analysera video pa /meta gav `analysis_failed` (och en poddomstart/503 i samband
med forsta forsoket). Rotorsak: Octopus-variabeln `GEMINI_API_BASE_URL` saknades
i Octopus-projektet, sa manifest-platshallaren `#{GEMINI_API_BASE_URL}` blev
ordagrant settings-varde -> `ValueError: unknown url type` som dessutom lackte
API-nyckeln (`?key=...`) i `analysis_error`. Fix i tre lager (Settings blankar
`#{VAR}`-varden, base-URL-fallback, nyckel i `x-goog-api-key`-header + sanering)
plus hardkodad standard-URL i `k8s/flow.yml` och probe-`timeoutSeconds: 5`.
Uppdaterade `meta-upload.md` (teknik + tva felsokningsrader).

## [2026-07-08] perf | Bemanning drag-fyll batchar schemaceller

Buggrapport #1 pekade pa att drag-kopiering av en cell till flera var mycket
langsammare i Flow development an tidigare pa stigamo.nu. Vantetidsdata visade
`POST /api/schedule/cells` runt rapporttiden pa cirka 17 s. Backend batchlaser
nu befintliga schemaceller per datum for `/api/schedule/cells` och
`/api/schedule/hours/restore` i stallet for en separat lasning per mal-timme.
Samma monster hittades i Oversikt: `/api/overview/days/bulk` batchlaser nu
befintliga dagceller och bygger efter-snapshots fran minnet i stallet for att
lasa om per dag. Intjaning i development-topologin: ungefar `(antal mal -
antal datum) * 36-37 ms` sparad vagtid pa las-sidan, t.ex. cirka 1,0 s vid 30
mal, 3,6 s vid 100 och 7,2 s vid 200, plus lagre lock-/timeout-risk. Audit-
rader far dessutom verksamhet direkt fran personen sa audit inte gor extra
user-lookup. Regressionsskydd:
`test_schedule_bulk_cells_batches_current_hour_lookup` och
`test_overview_bulk_days_batches_current_day_lookup` i
`tests/services/test_query_count_budgets.py`. Dokumenterat i
[bemanning-schedule.md](bemanning-schedule.md),
[overview-page.md](overview-page.md) och
[prestanda-optimeringar.md](prestanda-optimeringar.md).

## [2026-07-08] process | Buggrapportfixar far branchregel och synligt ID

Buggrapporter hade redan ett stabilt `bug_reports.id`; Buggrapporter-vyn visar
nu `#<id>` direkt i listan. Agentregeln ar uppdaterad: nar en agent pushar en
fix som utgar fran en buggrapport ska branchen heta `bug_report_<id>`, och om
fixen medvetet innehaller mer an den rapporterade buggen ska commit-meddelandet
namnge rapporten och beskriva extra scope. Buggrapport #1-fixen far avvika om
den redan pagar eftersom regeln skapades under arbetet. Dokumenterat i
`AGENTS.md` och [bug-reports.md](bug-reports.md).

## [2026-07-08] perf | Produktivitetsbygget ~6x + forbygg alla bolag varje pass

`_canonical_header` memoiserades (`lru_cache` pa modulniva) - den kanoniserade
om samma kolumnnamn per rad i `_row_text`, ~4M anrop/dagsbygge: **~10 s -> ~1,7 s
per bygge**, 3 bolag ~30,5 s -> ~5,2 s. Ett per-kolumnuppsattnings-motforsok
mattes langsammare och forkastades (mat, gissa inte). Med billiga byggen
forbygger 30-min-schedulern nu **dagens** dag for **alla aktiva bolag** varje
pass (`warm_today_for_businesses`, staggrat), sa personalen aldrig triggar
on-demand-bygge kl 05; on-demand kvar som matbar fallback (loggtagg
`productivity_overview_ondemand_build`). Dokumenterat i
[prestanda-optimeringar.md](prestanda-optimeringar.md) (B3) och
[productivity.md](productivity.md).

## [2026-07-08] fix | Buggrapport-inspelning tål dubbel modul-load

`common/bug_report.js` har nu en idempotensspärr så lazy/eager-laddning av
buggrapportmodulen inte kan skriva över en redan aktiv `window.flowBugReport`
efter sidbyte. Det skyddar inspelning som fortsätter mellan sidor och tar bort
en fullsvit-race där indikatorn syntes men `isRecording()` hade blivit false.

## [2026-07-08] observability | Seq far operation-id och domanhandelser

Seq-handelserna har utokats med `operation.id` fran frontend till backend,
response-headern `X-Flow-Operation-Id` och dokumentloggens
`Felsoknings-ID`. Client-error, vantetider, interaction-events och
buggrapporter bar samma sanerade korrelations-id. Hogvarde-floden loggar nu
egna events for `allocation_run`, `data_fetch_run`, `meta_upload` och
`meta_analyze` med `outcome=started|ok|blocked|failed`, duration, statuskod,
feltyp och raknare utan filnamn, sokvagar, request bodies eller privata varden.
Dokumenterat i `history-audit.md`.

## [2026-07-08] observability | Flow blir lattare att folja i Seq

Backendens OTel-konfiguration exporterar nu sanerade Python-loggar till Seq via
`/v1/logs` nar `OTEL_LOGS_ENABLED=true`. API-anrop far egna sokbara events med
`flow_event=http_request`, metod, route, status, duration, endpointgrupp och
`flow_trace_id`; querystring/request body/cookies/filnamn loggas inte. K8s-mallen
satter `OTEL_REQUEST_LOG_ENABLED=true`, `OTEL_LOG_LEVEL=INFO` och stanger av
SQLAlchemy-autospans med `OTEL_SQLALCHEMY_ENABLED=false` sa `SELECT flow` inte
dominerar Seq-vyn. Dokumenterat i `history-audit.md`.

## [2026-07-08] feature | Meta: byt status och radera rader i sandningsanalysen

Super User kan nu i `meta.html` byta `analysis_status` per rad via en dropdown
(alla sju statusar) och radera en rad helt. Radering oppnar en bekraftelsemodal
och tar bort hela videon och alla spar: sandningsraden, videoblobben ur
MediaStore (om ingen annan rad delar innehallshashen) och etikettreferenser.

- Backend: nytt `PATCH /api/meta/shipment-observations/{observation_id}/status`
  (`EDITABLE_SHIPMENT_STATUSES`, audit `update_status`). Delete-endpointen fanns
  redan (`DELETE /api/meta/uploads/{upload_id}`) och gjorde redan full radering.
- Frontend: status-dropdown + papperskorg-knapp i atgardskolumnen, delete-modal
  enligt dialogregeln (`meta.js`, ny `.meta-status-select` i `styles.css`).
- Desktop far andringen automatiskt (PyQt-WebEngine laddar samma frontend).
- Test: `test_super_user_can_change_shipment_status_and_audit` (24 grona).
- Dokumenterat i `wiki/meta-upload.md` (kontroll-tabell + endpoints).

## [2026-07-06] ingest | Apphjalpen far read-only-tools (function calling mot live-data)

Ny sida `assistant-tools.md`; `app-chat.md` och `index.md` uppdaterade. Nytt
paket `app/backend/assistant_tools/` med ~30 read-only-tools (grunddata,
personer, schema, produktivitet, Historik, system) + providerneutral tool-loop
i `runtime.py`. Apphjalpen (`assistant.py`) skickar toolsen till MiniMax som
function calling; svar med tool-anrop visar meta-rad i bubblan och skriver
auditraden `assistant_chat`/`tools_used` (label `Apphjalp-fraga` i Historik,
payload utan fraga/svar). Verksamhetsscope alltid pa via `business_scope`;
vybehorighet per tool ar metadata bakom `ASSISTANT_TOOLS_ENFORCE_VIEW_ACCESS`
(default av — beslut 2026-08-01). Tester: `test_assistant_tools.py`.

## [2026-07-06] ingest | Leveransoptimering: gzip, immutable-cache, ETag/304, service worker, latensbudget

Ny sida `prestanda-leveranslager.md`. Backend gzippar sjalv (GZipMiddleware,
SSE undantas av Starlette), `tools/stamp_asset_versions.py` stamplar
`?v=<innehalls-hash>` pa alla script/link-taggar i Docker-bygget och
`static_cache_headers` ger dem ett ars immutable-cache (HTML alltid
`no-cache`), `api_get_etag` ger 304 utan payload pa oforandrade API-GET-svar,
och `app/frontend/sw.js` cache-first:ar enbart versionsstamplade filer
(registreras bara over https). Latensbudget: `tools/latency_budgets.json` +
`api_benchmark --budget` (rutin i DEPLOY.md). Workers-audit: 1 worker star
fast — sankeys `_TRACE_CACHE` ar processlokal (410-risk vid >1 worker);
eskaleringsvag dokumenterad i DEPLOY.md. Konstaterat under arbetet:
idle-prefetch for alla sidor fanns redan (`enqueueVisiblePagePrefetches`) och
"morgonvarmning" tacks av produktivitetens snapshot-scheduler.

## [2026-07-06] arkitektur | RFID gar WiFi-only, USB-brygga avvecklad

`MG_Plock.ino`/`MG_VM.ino` postar nu direkt over WiFi
(`WiFiClientSecure`/`HTTPClient`) till `POST /api/rfid/scans` istallet for att
skriva Serial-rader for en lokal USB-brygga. `tools/rfid_serial_bridge.py`,
`tools/start_rfid_bridges.ps1` och deras tester togs bort;
`scripts/start_local.bat`/`start_dev.bat` startar inte langre nagon COM-brygga
(bara `--host 0.0.0.0` sa ESP32 nar backend over LAN). Testkontraktet
`tests/tools/test_rfid_firmware_contracts.py` kraver nu WiFi-inkludering
istallet for att forbjuda den. Upptackte under felsokning: Octopus-variabler
snapshotas vid releaseskapande, inte vid omdeploy av en befintlig release -
en `RFID_DEVICE_TOKEN`-andring kravde darfor en ny release for att sla
igenom. `k8s/flow.yml` kor `strategy: Recreate`, sa en deploy ger nagra
sekunders synligt `network_error`/`HTTP 0` i Historik - forvantat, inte ett
fel. Se `rfid.md` for hela floden och felsokningssvaren.

## [2026-07-04] feature | Arkivstatus-dashboard (superuser) + seed-konfig som lokalt

Ny vy **Arkivstatus** (`/arkiv-status.html`, vy-id `archiveStatus`, Super
User-gated, Verktyg-menyn): täckning per tenant/vy, saknade dagar, synk-logg
och produktivitetsbygget (snapshotdagar, förbyggda rapporter, backfill,
nattligt förbygge). `GET /api/query-data/archive-cache/status` utökad med
`productivity`-block. k8s-configen ändrad till `ARCHIVE_CACHE_SEED_DAYS=10000`
+ `ARCHIVE_CACHE_EMPTY_STOP_DAYS=300` (samma som lokalt — empty-stop-regeln
avgör hur långt bak, inte ett fast dagantal). Verifierad live mot riktig data
(10005 snapshotdagar, 21 täckningsrader). Se [local-archive-cache.md](local-archive-cache.md).

## [2026-07-04] feature | Arkiv-cachen (DuckDB) påslagen i deployade miljöer

Produktionsspärren i `start_archive_cache_scheduler` borttagen — cachen är
opt-in via `ARCHIVE_CACHE_ENABLED` överallt. k8s-configmappen sätter
`ARCHIVE_CACHE_ENABLED=1`, `ARCHIVE_CACHE_SEED_ON_START=1` (chunkad,
återupptagbar djup-seed vid poddstart; billig no-op när täckningen är klar)
och `ARCHIVE_CACHE_SEED_DAYS=400`. DuckDB-filerna hamnar på flow-media-PVC:n
(`/var/flow-media/flow-data/archive_cache`) och överlever omstarter. Motiv:
Sankeys månad/år-vyer utan cache drar hela dblog-arkivet i minnet och
OOM-dödar podden. Obs: Octopus-miljön måste också få env-variablerna om den
inte använder repo-configmappen. Se [local-archive-cache.md](local-archive-cache.md).

## [2026-07-04] fix | Serversmoke-verktyg, Översiktens skriptordning och Sankey-OOM-diagnos

Nytt läs-bara verktyg `tools.server_smoke` (loggar in mot riktig miljö, öppnar
alla vyer i sidregistret, rapporterar JS-fel/HTTP>=400/skärmdumpar; se
[testing-release.md](testing-release.md)). Första körningen mot
flow-development hittade två skarpa fel: (1) `overblick.html` laddade
`overview.js` före `overview_state.js` — IIFE:n i overview.js kräver `state`
vid laddning → `ReferenceError: state is not defined` och sidan dog; ordningen
rättad + cache-busting tillagd på overview.js. (2) Sankey — Inbound utan lokal
DuckDB-arkivcache (produktionsläget) drar hela dblog/live-datat i minnet:
lokal repro visade 132→449+ MB på 20 s för ett dagsanrop → podden (1 Gi-tak)
OOM-dödas och allt svarar 502. Åtgärdsbeslut kvarstår: arkivcache i prod (PVC
finns), minnesbudget i sankey-hämtningen, eller höjt poddtak.

## [2026-07-03] fix | MSSQL-härdning: dialektsäkra migrationer, startup-migrering och CI-gate

Tre produktionskrascher mot MSSQL (Azure) åtgärdade i grunden: (1) tuple-IN i
`routers/overview.py` ersatt med `_ywd_filter` (OR-kedja av AND-tripplar);
(2) schema-drift (`schedule_cells.remark` saknades) löst med `alembic upgrade
head` + ny `_run_startup_migrations` i `main.py` som kör alembic vid appstart
för icke-SQLite (av med `RUN_DB_MIGRATIONS_ON_START=0`); (3) unika constraints
på nullbara kolumner gav NULL-dubblettfel — fem index i MSSQL omgjorda till
filtrerade unika index med PG-semantik. Migrationskedjan 0001–0045 dialektsäkrad
(0002 CHECK-literaler, 0014/0016/0019 TRUE-literaler, 0015 expressionsindex,
0017 reserverat ord "key", 0018 PG-autonamn + INSERT-literaler + existing_type)
och verifierad från noll mot SQL Server 2022 i Docker. Tre index som prod
saknade skapade (`ix_schedule_cells_ywd` m.fl.). Nya CI-jobbet `mssql-gate`
bygger schemat från noll mot riktig MSSQL vid varje push. Nya kontraktstester:
`test_mssql_compat.py` (utökad med tuple-IN), `test_model_migration_parity.py`,
`test_startup_migrations.py`, `test_ci_workflows.py::test_push_ci_runs_mssql_alembic_gate`.
Se [testing-release.md](testing-release.md) och [nowaste-git-release.md](nowaste-git-release.md)
(nya branch-regler: alltid ny feature-branch, alltid ny release-branch per deploy).

## [2026-07-03] refactor | Render-sanering: legacy-drift borttagen ur repot

Migreringen till nowasteserver (k8s + MSSQL via Octopus) ar klar och verifierad,
sa all Render-specifik kod och konfiguration togs bort: `render.yaml` och
`backend.migrate_pg_to_mssql` raderade (finns i git-historiken),
RenderClient/deploy-/logg-/metrics-checks borttagna ur `healthcheck_service.py`,
`RENDER_*`-settings ur `config.py`/`.env.example`, `--no-render`-flaggan ur
`tools.healthcheck`, `include_render` ur `/api/healthcheck`, och Render-kortet/
tabellen ur Historik-Halsa (`historik.html` + `analytics.js`). Single-worker-
kontraktet vaktar nu Dockerfile-CMD i stallet for `render.yaml`; CI-steget heter
`Simulate Alembic build (Postgres)`. Alembic + Postgres-simuleringen i CI ar
kvar (schemahistorik och dialektneutral migrationsvag). k8s/-manifesten och
`APP_MIGRATION_PLAN.md` behalls. Uppdaterade sidor: [api.md](api.md),
[architecture.md](architecture.md), [history-audit.md](history-audit.md),
[testing-release.md](testing-release.md), [data-fetch.md](data-fetch.md),
[error-reference.md](error-reference.md), [meta-upload.md](meta-upload.md),
[nowaste-git-release.md](nowaste-git-release.md) samt root-dokumenten
`AGENTS.md`, `TESTPROTOCOL.md`, `DEPLOY.md`, `app/README.md`, `k8s/README.md`.

## [2026-07-03] ingest | NoWaste kallkodshantering och release via Octopus

Ingest av internt NoWaste-dokument "Kallkodshantering (GitHub)" (PDF) plus
muntlig releaseinstruktion: commits till `release/*`-branchar bygger
automatiskt releaser i Octopus; releaser deployas darifran till
development/production. Flow har officiellt gatt over till NoWaste-servern
(k8s, Octopus-projektet Flow, MSSQL). Ny sida
[nowaste-git-release.md](nowaste-git-release.md) med branchmodell
(master/develop/feature/release/hotfix/patch), releaseflode steg 1-10 och
Flow-specifika avvikelser (huvudbranch `main`, processen ar vagledande, inte
tvingande). Uppdaterade: [index.md](index.md),
[architecture.md](architecture.md) (drift + databas till k8s/MSSQL, Render
legacy), [testing-release.md](testing-release.md) (releasekontroll +
driftgrind) samt root-`AGENTS.md` (ny sektion om NoWaste-release).

## [2026-07-03] fix | Forbyggd overview-report-cache for Produktivitets periodoversikt

Produktivitets ar-/manadsvy raknade om varje dag fran snapshot-CSV vid varje
oppning, aven for dagar som redan byggts via produktivitets-CLI:t. Orsak:
overview-vyn kan inte anvanda `person_productivity_daily` som fullrapport (saknar
komplett tim-/process-/diff-detalj) och hade ingen persistent cache av det tunga
dagbygget. Losning: persistera den exakta dagrapporten (samma byggare som dag-vyn)
som gzip-JSON bredvid snapshoten (`overview-report-<business_id>.json.gz`),
signaturvaktad pa snapshot- + schemasignatur. Warm-vagen
(`productivity_cache_warm.ensure_person_and_overview_caches`) bygger dagrapporten
en gang och matar bade `person_productivity_daily` och `overview-report`, sa
CLI:ts `--with-productivity`/prebuild och nattjobbet forbygger aven oversikten.
Overview-lasvagen laser cachen forst och self-healar vid miss. Berorda sidor:
[productivity.md](productivity.md), [local-archive-cache.md](local-archive-cache.md),
[index.md](index.md).

## [2026-07-02] fix | Sankey helarsfilter ateranvander hamtad data

Sankey - Inbound forbattrar client_filters for helarsrapporter: arsvyn och
manadsvyer per bolag och `Visa endast forverkade` byggs fran samma branchunderlag
nar vybudgeten racker. Det gor att bolag, manadsdatum och forverkad-filter kan
vaxla lokalt efter att hela aret har hamtats, i stallet for att starta en ny
API/SSE-hamtning. Payloadschemat ar bumpat sa gamla servercacher inte ateranvands.

## [2026-07-02] ux | Sankey som Bemanning-flik

Sankey - Inbound ligger nu som fliken `Sankey` i Bemanning-gruppen och visas
for anvandare med `sankeyInbound=view`. Hogerklicksvagen fran Produktivitet
finns kvar, men normal ingang ar nu Bemanning -> Sankey.

## [2026-07-02] ux | Installningar i sidebarens hogerklicksmeny

Hogerklick pa `Installningar` i sidebaren visar nu installningssidans flikar:
Ytkarta, Bearbeta, Bemanning och Intakt/utgift, filtrerat efter vybehorighet.
Menyvalen oppnar `installningar.html` direkt pa vald flik via `tab`-parametern.

## [2026-07-02] ux | Profilnamnsfalt borttaget i label editor

Etiketteditorns mattpanel har inte langre ett separat profilnamnsfalt. `Spara`
skapar fortsatt en lokal profil, men namnet tas automatiskt fran aktuellt matt,
till exempel `104 x 200 mm`.

## [2026-07-02] ux | Resize-handtag i label editor

Etiketteditorn visar nu resize-handtag runt valt objekt. Anvandaren kan dra i
sidor eller horn for att andra bredd och hojd direkt i etikettytan; B/H-falten
uppdateras live och andringen kan backas via `Ctrl+Z`. Bakgrunds- och ritlager forblir
helcanvas-lager utan resize-handtag.

## [2026-07-02] lint | Arkitektursanering: vendor-krympning och radtaksfria splittar

Stor refaktorserie utan produktbeteendeandringar (18 commits). Vendor-motorn
warehouse_tools/vendor/allokering12.1.py sanerad fran dott Tkinter-GUI,
analytics och CLI-wrappers: 9490 -> 4250 rader, skyddad av nya
karakteriseringstester (10 floden mot lokala golden-snapshots) och en
krympnings-ratchet i arkitektur-kontraktet. wms_sok79.py och headless_tk.py
raderade (eftersok fanns aldrig i FLOW_BY_ID). Alla sju backendfiler pa
radtaksundantagslistan splittade (routrar till *_helpers-moduler med
kvalificerade patch-seams; productivity_kpi_rules till paket;
productivity_sync till modul + paths-modul). Sju av atta frontendfiler
splittade i globala moduler med script-taggar i alla berorda sidor;
map_settings.js kvar pa sankt tak 1060 (en enda mount-funktion, closure-lyft
ar uppfoljning). Statiska frontendtester laser nu via kanoniska fillistor i
tools/frontend_sources.py. Repo-roten stadad (pag.docx avsparad, tmp-filer
borta, pytest-tempkataloger gitignorerade).


## [2026-07-02] ux | Huvudmenyer for Bemanning och Verktyg

Sidebaren samlar nu bemanningsrelaterade vyer under huvudmenyn `Bemanning`
och verktygsrelaterade vyer under `Verktyg`. Sidorna visar flikar for sina
grupper, filtrerade efter vybehorighet. Hogerklick pa `Bemanning` visar
Bemanning, Oversikt, Produktivitet, Sankey, Aktiviteter, Personer, Anvandare,
Verksamheter, Mitt schema och Min produktivitet. Hogerklick pa `Verktyg`
visar Dela, Etiketter, MCP, Hamta data, Historik och Meta.

## [2026-07-02] feature | Anmarkning pa bemanningscell

Bemanningens hogerklicksmeny for celler har nu `Anmarkning`. Valet oppnar en
modal for fri text pa hel timme eller vald del av en delad timme. Texten sparas
i `schedule_cells.remark`, visas med en liten hornmarkering i cellen och foljer
med vid split, merge, copy och undo/redo. API:t ar
`PUT /api/schedule/cell/remark`. Audit sparar bara `remark_present` och
`remark_length`, inte sjalva anmarkningstexten.

## [2026-07-02] ux | Bemanningscell delar via hogerklicksmeny

Bemanningens timceller har bytt klickmonster: hogerklick oppnar nu en
cellmeny med `Dela` for hel timme och `Sla ihop` for redan delad timme.
Dubbelklick oppnar i stallet cellens aktivitetsdropdown for vald timme eller
del. Split-dialogen, minutvalen och samma `/api/schedule/cell/split`-mutation
anvands fortfarande.

## [2026-07-02] change | Tydligare produktivitetslogg i arkiv-CLI

Produktivitetsdelen i `archive_cache_cli` skriver nu chunk-progressbar och
visar fore varje intervall hur manga snapshotdagar som redan finns sparade,
hur manga som saknas/ar gamla och hur manga rader som finns i sparad metadata.
Efter varje chunk visas om API hamtades, hur manga sparade snapshotdatum som
ateranvandes och hur manga `person_productivity_daily`-dagar som redan var
aktuella eller byggdes. History-syncens resultat skickar nu med personcache-
utfallet sa CLI:n kan skilja pa sparad snapshot och byggd persondag.

## [2026-07-02] change | Produktivitets-CLI använder seed-fönster som default

`archive_cache_cli --with-productivity` och `--productivity-only` använder nu
`ARCHIVE_CACHE_SEED_DAYS` när inget produktivitetsdatum anges: intervallet går
till och med igår och bakåt lika långt som arkivseedens standardfönster. Gamla
läget "bygg bara befintliga snapshots" finns kvar som
`--productivity-prebuild-existing`.

## [2026-07-02] fix | Produktivitets-CLI återupptar utan dubbeljobb

Produktivitetsdelen i `archive_cache_cli` går nu från slutdatumet bakåt i
chunkar och skickar `skip_ready=True` till history-syncen. Redan kompletta
snapshotdagar hämtas inte om; personcachen i appdatabasen kontrolleras via
`person_productivity_daily`-signatur och byggs bara om när snapshot eller schema
har ändrats. CLI-raden visar `hämtar`, `kontrollerar sparade snapshots/persondagar` eller `redan klar`
per chunk.

## [2026-07-02] ingest | Strukturrefaktorering: paketsplit, bakgrundsregister och arkitekturkontrakt

De tre storsta servicefilerna ar uppdelade i paket med bakatkompatibla fasader:
`data_fetch_service` -> `app/backend/data_fetch/`, `mcp_service` ->
`app/backend/mcp/`, `sankey_inbound_service` -> `app/backend/sankey_inbound/`.
Alla uppstartsjobb gar nu via jobbregistret i `app/backend/background.py` och
FastAPI-lifespan (deprecated `on_event` borta); jobbstatus syns i healthcheck.
Nya kontraktstester i `tests/tools/test_architecture_contracts.py` haller
radtak per fil, skyddar single-worker-antagandet i `render.yaml` och vaktar
domangranser mellan servicemoduler. Se [Arkitektur](architecture.md).
Wikisidornas `status`-falt anvands nu som funktionslivscykel:
`aktiv` / `experiment` / `frys` / `avveckla` (se index och AGENTS.md).

## [2026-07-02] fix | Arkivcache stoppar efter lång tom historik

Bakåtseed i lokal DuckDB-arkivcache räknar nu tomma kalenderdagar och stoppar
när `ARCHIVE_CACHE_EMPTY_STOP_DAYS` nås (default 300). Vyn markeras då som
täckt/tom för det äldre begärda intervallet, så stora seeds som 10 000 dagar
inte behöver hämta hela vägen bak när API:t slutat hitta rader. Status visar nu
både `ingested_start/end` (faktiska rader) och `covered_start/end` (rader plus
kontrollerat tomma dagar). CLI-slutrapporten skriver dessutom en `INFO`-rad med
antal tomma dagar när tomstoppet används.

## [2026-07-02] feature | Arkivcache-CLI kan fylla produktivitet

`python -m app.backend.archive_cache_cli` kan nu aven kora Produktivitetens
API-dagfyllning: `--productivity-start` utan `--productivity-end` hamtar till
och med igar, aldrig dagens datum, och bygger normalt
`person_productivity_daily`. `--with-productivity` kor produktiviteten efter
DuckDB-arkivseed. `item_alias` ligger kvar som DuckDB-stodvy i samma CLI.
CLI:t chunkar produktivitetsintervall (default 31 dagar), faller tillbaka till
standardtenant nar DB-uppslag for tenant inte svarar och stoppar tydligt fore
lang hamtning om `person_productivity_daily` ska byggas men `DATABASE_URL` inte
gar att ansluta.

## [2026-07-02] fix | Arkivcache-CLI kan koera snapshotdelen separat

`python -m app.backend.archive_cache_cli` fyller nu tydligt bade arkivvyer och
snapshotvyer som default. CLI-hjalpen namner `item_alias`, och nya
`--snapshots-only` kor bara snapshotrefreshen for att fylla DuckDB med nattens
stoddata utan att starta en arkivseed.

## [2026-07-01] perf | Sankey alias-snapshot och nattlig produktivitets-prebuild

Den lokala DuckDB-cachen har nu datumslosa snapshots for stodvyer. `item_alias`
refreshas av archive-cache-jobbet/CLI och Sankey laser den lokalt som
`local_snapshot`, medan buffertpall fortsatt hamtas live vid berakning.
Produktivitetens scheduler hamtar dagens snapshot utan att bygga dagens
personcache; historiska snapshotdagar prebyggs i `person_productivity_daily`
en gang per dag efter backfill/snapshot-sync och dagens datum byggs on-demand.

## [2026-07-01] fix | Sankey behaller lokala filtervyer for manad/vecka/dag

Sankey - Inbound prebygger ater lokala `client_filters.views` for interaktiva
dag-/vecko-/manadsladdningar aven nar kallaraderna ar manga, sa bolagsbyte och
datumbyte inom redan hamtat omfang inte triggar en ny full hamtning. Trace-
lazyloaden behaller en server-side radtoken men skickar nu `trace_filter`
(`company`, `start_date`, `end_date`, `only_consumed`) till `/trace` och
`/trace.csv`, sa drilldown/export foljer den lokalt valda vyn utan att
`trace_rows` skickas i huvudpayloaden.

## [2026-07-01] perf | Sankey använder toppad arkiv-cache

Sankey - Inbound läser nu även den toppade delen av live-retention-segment från
lokal DuckDB-arkivcache. För en äldre inboundkohort betyder det att receive,
trans och pick kan tas lokalt fram till cache-max (normalt igår) och bara den
färska resten hämtas via live-API. Cacheträffar syns i `source_status` som
`local_archive`. `dblog_dispatch_pallet_log` ingår nu också i
`archive_cache_sync.SYNC_ARCHIVE_VIEWS`, så Dispatchpallslogg kan seedas lokalt
i stället för att varje historisk Sankey-körning går mot dblog/API. CLI:t har
även `--view`, till exempel
`python -m app.backend.archive_cache_cli --tenant frey --view dblog_dispatch_pallet_log`.

## [2026-07-01] fix | Sankey lazy-laddar spårningsrader

Sankey - Inbound skickar inte längre spårningsraderna som en stor JSON-del i
huvudpayloaden. Rapporten får `trace_token`, `trace_total` och `trace_counts`;
detaljpanelen hämtar en liten preview via `/api/sankey/inbound/trace`, och
exporten går via streamad `/api/sankey/inbound/trace.csv`. Om trace-cachen har
gått ut visar UI:t att rapporten behöver köras om.

## [2026-07-01] feature | CLI-seed med progressbar + parallell/återupptagningsbar fyllning

Djup-seeden av DuckDB-cachen körs nu via CLI (`python -m app.backend.archive_cache_cli`)
istället för vid serverstart: parallellt per vy, chunkat, med live progressbar per
tenant/vy (visar hämtade dagar, rader och pågående chunk) + TOTALT-rad. Återupptagningsbart
(Ctrl+C → kör igen). Servern seedar inte längre tungt vid start – schemaläggaren toppar bara
på redan seedade vyer (`ARCHIVE_CACHE_SEED_ON_START`, default av). Store gjord parallell-säker
(lås per DB-fil runt varje anslutning) och `append_rows_by_date` skriver en hel chunk i EN
anslutning (seed ~9× snabbare). Ny fil `archive_cache_cli.py`; nya settings
`ARCHIVE_CACHE_SEED_ON_START`/`_SEED_WORKERS`. Se [local-archive-cache.md](local-archive-cache.md).

## [2026-07-01] feature | Lokal arkiv-cache (DuckDB)

Ny per-tenant DuckDB-cache som speglar `dblog_*`-arkiven lokalt: seed en gång från
dblog, topp-på dagligen ur live-vyerna (rikare kolumner, dblog rörs inte i normal drift).
Sankey, Produktivitet och Hämta data läser lokal-DB först och faller tillbaka till dblog/API.
Endast lokal dev (`ARCHIVE_CACHE_ENABLED`), startar aldrig i produktion. Kod i
`local_archive_store.py` + `archive_cache_sync.py`; synk-logg + status-endpoint/CLI.
Dessutom: förpacknings-uppdelningens item_alias-hämtning smalnas nu av till plockradernas
item_num (batchat) så datakällans 50k-tak inte längre kapar bort faktorer. Se
[local-archive-cache.md](local-archive-cache.md) och [data-fetch.md](data-fetch.md).

## [2026-07-01] change | Dispatchlogg ersatter Dispatchpallar i outbound

Produktivitetens forifyllda intaktsrad `Utlastade pallar` och Sankeys outbound-
hamtning laser nu `dispatch_pallet_log` i stallet for nulagesvyn
`v_ask_dispatch_pallet`. `DISPATCH_PALLET_LOG` har 14 dagars operativ retention
pa `created` och arkiveras till `dblog_dispatch_pallet_log`; Flow har darfor
lagt till paret i live-/arkivstyrningen sa aldre perioder hamtas fran arkivet. Warehouse-
flodet Dispatchkontroll och Meta-uppslag behaller `v_ask_dispatch_pallet`.

## [2026-07-01] fix | Sankey hämtar plocklogg live igen

Sankey - Inbound återanvänder inte längre Produktivitetens dags-snapshots för
`pick`/Plocklogg Full. Juniavstämning visade att snapshots kunde sakna PR-rader
för vissa datum trots att live-vyn hade dem, vilket gjorde E-handelns plockade
orders för låga mot WMS. `receive` och `trans` kan fortsatt återanvända
snapshots, men Plocklogg Full går via Sankeys live-/`dblog_*`-hämtning.

## [2026-07-01] fix | Sankey orders kräver plockat antal

Outboundmåtten `store_picked_orders` och `ecom_picked_orders` räknar nu bara
unika ordernummer där minst en plockloggsrad har `qty_suf`/`Plockat >= 1`.
Regeln är synkad mellan Sankeys backendräkning och de seedade
Intäkt/utgift-planerna. Orders har fortfarande inget zonfilter, så helpallsrader
med plockat antal räknas som plockade orders.

## [2026-07-01] fix | Sankey matchar buffertuppdatering via pall

Sankey - Inbound tappar inte längre en `type = 91`-buffertuppdatering bara för
att plats-/artikelnyckeln inte träffar plockplats-FIFO. Om raden har ett
pallnummer som redan finns i den spårade inboundkedjan används pallmatchning som
fallback och processen `Buffer Update` får då intäktsandel enligt KPI-poängen.

## [2026-07-01] feature | Sankey outbound visar plockade pcs

Outbound-kartan i Sankey - Inbound har nu `Plockade pcs` för både Butik och
E-handel. Backend hämtar `item_alias` som stöddata och använder samma
`package_breakdown`-logik som Intäkt/utgift: `qty_suf` delas upp per plockrad
med `conversion_factor` störst först och faktor `1` som `ST`, innan priset
multipliceras mot antalet plockenheter.

## [2026-07-01] change | Sankey visar outbound som egen karta

Sankey - Inbound renderar nu inbound och outbound som separata kartor i samma
vy. Inbound-kartan visar mottagning, processer och statusar. Outbound-kartan
borjar pa `Outbound` och delar sig till `Butik` och `E-handel` innan
debiteringsraderna, sa outboundflodet inte blandas visuellt med inboundkedjan.

## [2026-07-01] fix | Produktivitet bygger manad fran snapshots igen

Produktivitetens periodoversikt anvander inte langre `person_productivity_daily`
som full dagsrapport. Den snabba cachevagen kunde gora manadsvyn for tunn i
process-/timdetalj, sa `/api/productivity/overview` bygger ater fulla
dagsrapporter fran snapshotfilerna. Filbaserad SQLite behaller begransad
dagparallellism och daglage vantar fortsatt pa dagens startup-snapshot.

## [2026-07-01] perf | Sankey hoppar tunga klientvyer

Sankey - Inbound/Outbound bygger inte langre alla lokala `client_filters.views`
for stora payloads. Nar kallaraderna eller antalet filtervyer blir for stort
returnerar API:t aktuell vy med `client_filters.prebuilt=false` och
`omitted_reason=large_payload`; frontend hamtar da nasta bolags-/period- eller
forverkad-variant via vanlig API/SSE-fallback. Juni-test med cirka 39k receive,
124k trans, 234k pick, 37k dispatch och 57k buffer gick fran att inte bli klart
efter drygt 10 minuter i byggfasen till 32,7 sekunder.

## [2026-07-01] feature | Sankey foljer outbound

Sankey - Inbound visar nu aven outbounddebitering for Butik och E-handel.
Backend hamtar `v_ask_dispatch_pallet` som extra kalla, bygger noder for
`Outbound -> Butik/E-handel -> debiteringsrad` och returnerar
`outbound_metrics`, `outbound_income` och outboundspår i `trace_rows`. Reglerna
foljer Plocklogg Full med `TO` for Butik, `PR` for E-handel, zon `H` for
helpallar, `qty_suf`/`Plockat >= 1` for rad/helpall och Dispatchpallar med tomt
`parent_pick_pall_num` for utlastade pallar. Intakt/utgift-defaultsen har samma
berakningsplaner for GG och E-handel-raderna ar forifyllda.

## [2026-06-30] perf | Sankey ateranvander Produktivitetens snapshots

Sankey - Inbound laser nu Produktivitetens befintliga API-snapshotfiler for
`receive` och `trans` nar hela foljfonstret redan finns lokalt. Om nagon
dag saknas faller Sankey tillbaka till sin tidigare live-/`dblog_*`-hamtning.
Kallstatus markerar ateranvandningen med `status=productivity_snapshot`, sa
Historik/audit och felsokning kan se nar extern API-hamtning undveks.

## [2026-06-30] perf | Produktivitetens manadsoversikt laser dags-cache

`GET /api/productivity/overview` ateranvander nu aktuell
`person_productivity_daily` for varje dag i perioden innan den faller tillbaka
till snapshotfilerna. Den materialiserade cachen sparar aven timcellernas
processpoang som `cell_process`, sa framtida cachetraffar kan rita samma
processnoder utan att bygga om dagen. Filbaserad lokal SQLite far dessutom
anvanda samma begransade dagparallellism som Postgres, medan in-memory
testsessioner kor seriellt.

## [2026-06-30] fix | Produktivitet vantar pa dags-snapshot efter lokal start

Produktivitetens daglage invantar nu den begarda dagens API-snapshot innan
periodtradet byggs. Det gor att `/produktivitet.html` inte direkt visar
"Produktivitetens API-snapshot saknas eller ar inte komplett" nar anvandaren
oppnar vyn precis efter `start_local.bat` och startup-synken fortfarande haller
pa. Vecka, manad, ar och custom-perioder fortsatter lasa befintliga snapshots
utan att trigga historikhamtning vid periodbyte.

## [2026-06-26] fix | MCP/OpenAI far separata env-namn

MCP-vyn visar nu NoWaste och OpenAI som separata providers. NoWaste anvander den
OpenAI-kompatibla `MCP_LLM_OPENAI_API_KEY`, `MCP_LLM_OPENAI_MODEL` och
`MCP_LLM_OPENAI_API_BASE_URL`, men far bara sin defaultmodell, normalt `gpt-4o`.
OpenAI anvander separat `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_API_BASE_URL`
och modellistan `MCP_OPENAI_MODELS`. Ingen provider faller tillbaka till den
andras nyckel. OpenAI-modellistan ar en inbyggd standardlista, inte en livefraga
mot OpenAI `/models`, sa statusvyn gor inga extra provideranrop for att bygga
dropdownen. Standardlistan innehaller nu aven GPT-5-serien (`gpt-5.5`,
`gpt-5.4`, `gpt-5.2`, `gpt-5`) sa nyare modeller syns utan liveanrop.

## [2026-07-01] fix | CI-kontrakt for Personer och Produktivitet

Personer-vyn hamtar ater om listan med `area_id` nar omradesfokus andras, sa
Super User inte ser personer fran fel verksamhet nar fokus star pa ett specifikt
omrade. Wikin markerar ocksa att Produktivitetens MG/IT-rad defaultar till 0 kr
i repot och far riktiga priser via lokal/secret overlay.

## [2026-06-25] fix | Produktivitet bygger perioddagar parallellt

Produktivitetens periodoversikt bygger nu dagrapporter fran befintliga
snapshots med begransad parallellism pa Postgres, max fyra dagar samtidigt.
Varje dagjobb far en egen kort DB-session och slutpayloaden sorteras fortfarande
per datum. SQLite och fake-sessioner faller tillbaka till seriell byggning, och
SSE-progressen raknar fardiga dagar via `completed` sa UI:t inte overdriver
framdriften nar flera dagar ar aktiva samtidigt.

## [2026-06-25] feature | MCP kan använda DeepSeek som hjärna

MCP-vyn väljer nu LLM-hjärna via `MCP_LLM_PROVIDER`. Default `auto` använder
DeepSeek när `DEEPSEEK_API_KEY` finns och faller annars tillbaka till Gemini.
Backend skickar read-only MCP-tools som function declarations till DeepSeek,
bevarar `reasoning_content` mellan tool-anrop när thinking mode är aktivt och
returnerar bara sanerad provider/modell/tool-metadata till frontend och audit.
Efter långsamma MCP-frågor och ett läckt pseudo-tool-svar är
`DEEPSEEK_THINKING_ENABLED=false` default. `DEEPSEEK_REASONING_EFFORT=high` gäller
när thinking slås på, och `max` finns kvar för tyngre fler-stegsfrågor.

Utökade därefter MCP-vyn med separata rullistor för `Företag`, `Modell` och
`Thinking mode`. Backend exponerar bara providers med konfigurerad API-nyckel
och stöder DeepSeek, OpenAI, Gemini och MiniMax. Modellistorna styrs via
`MCP_DEEPSEEK_MODELS`, `MCP_OPENAI_MODELS`, `MCP_GEMINI_MODELS` och
`MCP_MINIMAX_MODELS`, medan thinking-val bara visas för providers där backend
har explicit stöd.

## [2026-06-25] fix | Sankey återanvänder bredare urval lokalt

Sankey - Inbound skickar nu `client_filters.views` med färdigräknade lokala
vyer från samma branchunderlag. När `Alla bolag` är hämtat kan frontend byta
bolag utan ny hämtning. När månad/vecka är hämtad kan en dag i samma period
visas lokalt, och när år är hämtat kan en månad i året visas lokalt. Spårningen
har fått `received_date` så mottagningskohorten kan filtreras korrekt, och
varningsrutan normaliserar äldre mojibake för svenska tecken.

## [2026-06-24] feature | MCP använder Gemini som hjärna

MCP-vyn kräver inte längre ett MCP-tool för frågor. Backend hämtar i stället
tenant-baserad MCP-kontext via resources/prompts och skickar användarens fråga
till Gemini `generateContent` med modellen från `GEMINI_MODEL`. Status-API:t
visar nu MCP- och Gemini-konfiguration, UI:t visar `Hjärna` i stället för
verktygsval och audit fortsätter spara bara sanerad metadata med modell,
status och teckenantal.

Utökade därefter samma flöde med Gemini function calling mot MCP-tools.
Read-only tools som `get_views`, `search_views`, `get_view_schema`,
`get_view_columns`, `query_view` och `aggregate_view` kan nu anropas av Gemini
via backend. Svaret och auditpayloaden innehåller `tool_calls`, och backend kan
läsa dynamiska tenant-tokenvärden från lokal `.env`/`app/.env` utan att de
exponeras i frontend.

## [2026-06-24] feature | MCP-vy for tenant-fragor

Lade till MCP-vyn i wikin: anvandarflode, kontroller, backendproxy,
behorigheten `mcp`, API-rutterna `GET /api/mcp/status` och
`POST /api/mcp/query`, samt Historik/Analys-sparet `mcp_query` med sanerad
payload. Dokumentationen beskriver ocksa att URL/token inte ska exponeras i
frontend eller wiki, och att lokal utveckling kan lasa tenant-baserad
serveradress-template fran ignorerad Codex-konfiguration medan token kommer
fran miljo via `NOEFFECT_<TENANT>_TOKEN`.

## [2026-06-24] feature | Sankey - Inbound vy och beräkningsregler

Dokumenterade den nya separata vyn `Sankey - Inbound`, API:t
`GET /api/sankey/inbound`, behörigheten `sankeyInbound`, auditposterna
`sankey_inbound_report/run|run_failed`, mottagningsfilter för fakturerbara
etiketter och begränsningar kring `dblog_*` samt plockplats-FIFO. Uppdaterade
index, UI-karta, API-karta, Produktivitet, roller/behörighet,
ASK-statuskoder och ASK-datalagring.

Förtydligade även att Sankey-statusnoder bara visar flödespott/placering, inte
processintäkt. Processintäkt visas bara på processnoder och saknade KPI-poäng
hamnar i `Ofördelad intäkt`.

Fixade därefter KPI-poängläsningen så Sankey använder Produktivitetens
KPI-target-parser för `action_id`/`Processnamn` och `loaded_*`-kolumner.
Processintäkten ska därför inte bli `0 kr` när KPI-målen finns i
`v_ask_kpi_target`.

Utökade inbound-intäkten med `inbound_article_rows`: efter samma mottagnings-
filter räknas unika `company + book_num + line_num`, potten delas lika över de
mottagningsrader som hör till inköpsraden och följer sedan samma branch- och
processpoängsfördelning som etikettintäkten. API och UI visar nu breakdown för
etikettintäkt respektive inköpsradsintäkt.

Lade till felsökningsunderlag för pallgrenar i Sankey - Inbound. API:t returnerar
nu `trace_rows` med ursprungspallid, nuvarande pallid, inköp/rad, status,
diagrammedlemskap och `step_1..N` för spårad väg. UI:t visar matchande
pallgrenar när användaren klickar på nod eller länk och kan exportera hela
underlaget eller bara urvalet som CSV. Auditloggen fortsätter vara sanerad utan
pallid/order/radpayload.

Testade även Sankey-källorna mot `pick_stock` och `v_ask_item_balance_list`.
`pick_stock` saknade pallid/plats. `v_ask_item_balance_list` matchade
buffertpall på gemensamma pallid men saknade 6 995 buffertpall-pallid i dagens
prov och slog i radtaket för GG. Sankey behåller därför
`v_ask_article_buffertpallet`, men slutar hämta de oanvända källorna
`v_ask_palletloading_log` och `v_ask_item_summary_stock_automation`.

Ändrade KPI-steget i Sankey så `v_ask_kpi_target` inte längre provas via extern
API. KPI-poäng läses direkt från Produktivitetens coredata-/fallbackfil som
förstahandskälla, vilket tar bort den återkommande 403-kostnaden och varningen.

Gjorde `Visa endast förverkade` till en ren klientväxling. API:t skickar nu med
en färdigräknad `client_filters.only_consumed`-vy i standardpayloaden, byggd
från samma branchunderlag, så frontend inte gör en ny GET/SSE-hämtning när
användaren bara filtrerar bort öppna grenar.

Ändrade även felhanteringen för `dblog_pick_log`: om ett äldre plocksegment
nekas av extern datakälla, till exempel HTTP 403, stoppar inte Sankey hela
rapporten. Den fortsätter med tillgängliga segment och skickar varningen
`degraded_source_segment_unavailable`, eftersom förverkade/plockade grenar då kan
vara underskattade.

Felsökte Stigamo/Frey-arkiven direkt mot extern API med samma integrationnyckel.
`dblog_trans_log` svarar 200, men `dblog_pick_log`, `dblog_receive_log` och
närliggande plockarkiv svarar 403 även utan filter och syns inte i API:ts
tillgängliga vylista. Det är alltså extern vybehörighet/nyckelexponering, inte
fel datumkolumn eller datumformat. Sankey-UI rensar nu gamla KPI-kort/spårning
när en källhämtning failar, så en misslyckad äldre period inte visar stale data.

## [2026-06-24] docs | ASK-statuskoder far egen katalogplan

Lade till `ask-statuskoder.md` som beskriver hur PDF-underlaget med
Nowaste/ASK-statuskoder bor hanteras som en separat kodkatalog bredvid
`data/external_data_catalog.json`. Sidan forklarar skillnaden mellan
vy-/kolumnkatalog och kodbetydelser samt lyfter centrala pallspårningskoder
som `RECEIVE_LOG` type `45`, `81`, `91` och `100`. Kallunderlaget ligger som
projektkopia under `referens/ask-statuskoder/` sa wikin inte pekar pa filer
utanfor projektet.

Kompletterade ocksa wiki-regeln: nar Flow i framtiden skippar, exkluderar eller
sarklassar ASK-koder ska dokumentationen beskriva varfor, inte bara vilken kod
som filtreras.

## [2026-06-17] feature | Produktivitet far verksamhetssummering

Verksamhetsnoden i Produktivitet har nu hogerklickskommandot `Summering`.
Dialogen anvander samma datum-/periodurval som produktivitetsvyn och visar
intakt, kostnad, resultat och antal nollade plockrader per bolag. Nollade
plockrader raknas fran plockloggens poster dar `Plockat`/`qty_suf` ar `0`.

## [2026-06-17] feature | Kontroll visar processkombination per intaktsnyckel

Intakt/utgiftens processkontroll jamfor nu `count_distinct`-utrakningar pa
intaktsradens berakningsnyckel, till exempel `order_num`, i stallet for bara
enskilda loggrader. Kontrollmodalen visar en egen processkombination med antal
intaktsnycklar, tackta nycklar, saknade nycklar, extra nycklar och
tackningsprocent, sa anvandaren kan se om flera KPI-processer tillsammans kan
samla posterna bakom en intakt.

## [2026-06-17] ux | Kontrollmodal visar prompt och process-SQL

Processkopplingen i Intakt/utgiftens kontrollmodal ar nu en sokbar rullista i
stallet for en lang radiolista. Samma modal visar radens prompt, intakts-SQL och
process-SQL for vald KPI-process, och bottenknappen `Stang` ar borttagen eftersom
dialogen har X i topphuvudet.

## [2026-06-17] ux | Intakt/process-kontroll flyttar in i dialog

`Kontrollera intakter/processer` och radkommandot `Kontroll` oppnar nu en
dialog med manadsval innan kontrollen kors. Resultatet renderas i dialogen i
stallet for inline i Intakt/utgift-fliken, och radkontrollen kan samtidigt
koppla intaktsraden till en KPI-process.

## [2026-06-17] fix | RFID-brygga filtrerar upprepade taggar

USB-bryggan for RFID har nu ett 3-sekunders debounce-fonster per device,
modul och tagg innan den postar till `/api/rfid/scans`. Autostartkommandot
anvander `--dedupe-window 3` och skriver inte langre alla ra serialrader med
`--echo`, sa en bricka som ligger kvar vid lasaren inte fyller loggen eller
backend med upprepade lokala POST-anrop. Backendens dubblettskydd finns kvar som
sista skydd om en upprepning anda nar API:t.

## [2026-06-17] change | Intaktsrader far hogerklick och processkoppling

Intakt/utgift-tabellen har inte langre en egen kolumn for radknappar.
`Utrakning`, `Kontroll` och nya `Koppla process` ligger i stallet som
hogerklickskommandon pa intaktsraden. Processkopplingen sparas pa raden och
Produktivitet visar radens intakt pa matchande KPI-processer nar rollen har
`productivityFinance=view`.

## [2026-06-17] fix | RFID-bryggor vantar pa upptagen COM-port

USB-bryggorna for RFID startas nu med `--retry-open`, sa COM9/COM10-processerna
ligger kvar och provar igen om Arduino Serial Monitor, Serial Plotter eller
Arduino IDE tillfalligt haller porten last. Serial-eko sanerar ocksa
oskrivbara uppstartsbytes fran ESP32 sa bryggan inte kraschar pa Windows-loggen.

## [2026-06-17] change | RFID gar via USB/COM utan WiFi

MG Plock- och MG VM-sketcherna ar nu USB/Serial-only: de laser RDM6300 och
skriver RFID-rader pa Serial utan WiFi, HTTP eller lokal serveradress.
`start_local.bat` och `start_dev.bat` startar automatiskt COM-bryggor for
`COM9 -> MG Plock` och `COM10 -> MG VM`, sa anvandaren normalt bara behover
starta Flow och ha ESP32-modulerna anslutna pa ratt USB-port.

## [2026-06-17] change | MG VM far egen RFID-modul

RFID-hardvaran har nu en lokal `MG_VM`-sketch med unikt device-id
`esp32-mg-vm-01` och modulnamn `MG VM`, vilket matchas mot aktiviteten
`MG_VM`/`MG VM` i Bemanning. USB-bryggans dokumenterade COM10-kommando tvingar
modulnamnet till MG VM via `--force-module-name`, och de lokala `.ino`-filerna
for MG Plock/MG VM ar git-ignorerade eftersom de innehaller
WiFi/server/token-konfiguration.

## [2026-06-15] change | GG far utlastade pallar-default

Intakt/utgift-defaulten for `GG` har nu forifylld `Utrakning` for BUTIK-raden
`Utlastade pallar`: Dispatchpallar med `parent_pick_pall_num <> ''`,
maj-intervall och `company = 'GG'`.

## [2026-06-15] change | GG far helpalls-default

Intakt/utgift-defaulten for `GG` har nu forifylld `Utrakning` for BUTIK-raden
`Antal helpallar`: plocklogg full, zon `H`, minst 1 i `qty_suf`, ordernummer
som borjar pa `TO`, juni-intervall och `company = 'GG'`.

## [2026-06-15] change | GG far plockade rader-default

Intakt/utgift-defaulten for `GG` har nu ocksa forifylld `Utrakning` for
BUTIK-raden `Plockade rader`: plocklogg full, ordernummer som borjar pa `TO`,
utan zon `H`, minst 1 i `qty_suf`, datumintervall och `company = 'GG'`.

## [2026-06-15] change | GG far forifyllda utrakningar

Intakt/utgift-defaulten for `GG` har nu forifyllda `Utrakning`-prompter,
validerade planer och SQL/querytext for `Mottagna etiketter`, `Mottagna
artikelrader` och BUTIK-raden `Plockade orders`.

## [2026-06-15] fix | Hamta data far sakra textfilter

Hamta data och Intakt/utgift-utrakningar accepterar nu validerade textfilter
som `StartsWith`, `EndsWith`, `Contains` och `Like`. Filter som "ordernummer
borjar pa TO" visas som `LIKE 'TO%'` i SQL/querytexten, men skickas inte som
okanda operatorer till extern API-kalla; backend applicerar dem lokalt pa
hamtade rader innan berakning och tabellpreview.

## [2026-06-15] fix | Exkludera-filter kor lokalt

`NE`-filter, till exempel "exkludera typ 45, 91 och 100", skickas inte langre
till extern API-kalla. Backend hamtar med ovriga filter och tar sedan bort
exkluderade varden lokalt, sa SQL/querytexten `type <> 45` motsvarar faktisk
exkludering aven om provider-API:t tolkar `NE` annorlunda.

## [2026-06-15] fix | Jamforelsefilter kor lokalt

Numeriska jamforelsefilter som `qty_suf >= 1` skickas inte langre till extern
API-kalla. Backend pushar fortfarande stabila urval som datumperiod och bolag,
men applicerar `GT`, `GTE`, `LT` och `LTE` lokalt pa hamtade rader innan
berakning.

## [2026-06-15] test | Live-test for extern datakalla

Det finns nu ett opt-in integrationstest for riktig `DATA_SOURCE_*`-datakalla:
`tests/integration/test_data_source_live.py`. Testet kor inte i standard-sviten
utan kraver `RUN_DATA_SOURCE_INTEGRATION=1`, hamtar plocklogg for vald manad och
bolag, applicerar lokala filter och kan jamfora mot
`LIVE_DATA_SOURCE_EXPECTED_PICK_COUNT` eller ett eget SQL-facit via
`LIVE_DATA_SOURCE_SQL_URL` + `LIVE_DATA_SOURCE_SQL`.

## [2026-06-15] feature | Hamta data far validerade berakningar

Hamta data-planen kan nu innehalla en whitelistad `calculation` ovanpa samma
externa API-hamtning: `count`, `count_distinct`, `sum`, `avg`, `min`, `max`,
valfri gruppering, sortering och limit. Backend validerar alla berakningskolumner
mot katalogen och kor berakningen lokalt pa hamtade rader; MiniMax skriver inte
fri SQL. Intakt/utgift-radernas `Utrakning` ateranvander samma motor och kan nu
rakna exempelvis unika artikelnummer per inkopsnummer utan att missbruka
`identifiers`.

## [2026-06-15] fix | Intakt/utgift far toppsparning och stabil dialog

Intakt/utgift-flikens `Spara`-knapp ligger nu over intaktstabellerna. Dialogen
for radens `Utrakning` stangs inte langre av backdrop-klick, sa textmarkering
eller drag ut ur textarea inte kan stanga dialogen av misstag. Repo-reglerna har
en frontendregel som forbjuder enkelt backdrop-`click`-monster for framtida
text- och formulardialoger.

## [2026-06-15] fix | Utrakningstest filtrerar pa bolag

Intakt/utgift-radernas `Utrakning`-test skickar nu med aktuell bolagskod fran
bolagsrutan. Backend lagger automatiskt pa `company`/Bolag-filter i den
validerade Hamta data-planen och i sparad SQL/querytext nar den valda ASK-vyn
har en bolagskolumn.

## [2026-06-15] change | MG-underlag begransas till VAS och IT

Intakt/utgift-defaulten for bolaget `MG` visar nu bara VAS-rader och IT-raden.
VAS far samma forifyllda varden som `GG`, medan IT-raden defaultar till 445 kr
per timme. Gamla sparade MG-rader utanfor VAS/IT filtreras bort nar
installningen visas eller sparas igen.

## [2026-06-15] feature | Intaktsrader far utrakningstest

Intakt/utgift-underlaget har nu kolumnen `ST / Antal` och en `Utrakning`-knapp
per rad. Dialogen testar anvandarens utrakning mot valbar startad manad i
innevarande ar via samma MiniMax/Hamta data-plan som `hamta-data.html`, visar
radantalet och sparar prompt, validerad plan och SQL/querytext pa raden.

## [2026-06-15] feature | Intakt/utgift far GG-underlag

Intakt/utgift-fliken visar nu intaktsunderlag per bolag med bolagskoden som
rubrik, till exempel `GG` i stallet for faktureringsunderlagets fulla namn.
`GG` ar forifyllt med Grann-garden-priser for Inbound, BUTIK, E-handel, VAS,
IT och Ovrigt. De sparade VAS-raderna matar fortsatt Produktivitetens
intaktsberakning via Normal-raden per Blue/White collar.

## [2026-06-15] feature | VAS-intakt per bolag far Blue/White collar

Intakt/utgift-installningen sparar nu separat VAS-intakt per timme for
Blue collar och White collar per bolag. Produktivitetens intakt pa
hierarkikorten valjer rate efter aktivitetens bolag och personens arbetstyp,
med `blue_collar` som fallback for personer utan explicit arbetstyp.

## [2026-06-15] feature | Verksamheter far Tenant for extern API-bas

Verksamheter har nu faltet `tenant`. Verksamheter-vyn visar och redigerar
Tenant inline, Stigamo defaultar till `frey`, R3 till `loki` och T3 till `itworks`.
Hamta data, Bearbeta-kallor och Produktivitetens API-snapshot bygger extern
API-bas fran verksamhetens tenant nar backend kanner till vald verksamhet.

## [2026-06-15] change | RFID-sketch provar flera WiFi

Den lokala RFID-sketchens WiFi-konfiguration har fyra slots. Tomma slots hoppas
over och ESP32 provar varje ifyllt nat med timeout innan den gar vidare till
nasta.

## [2026-06-14] process | Agentregler kraver Historik/Analys for nya handelser

Agent- och testreglerna kraver nu att nya anvandarsynliga handelser,
integrationer och hardvarufloden har auditplan, Historik/Analys-labels,
sanerade detaljer och automatiska fullkedjetester. Manuell scanning eller
klickning far bara vara komplement.

## [2026-06-14] change | Historik visar RFID-stamplingar tydligare

RFID-auditposter etiketteras nu som `RFID-stämpel` i Historik/Analys i stallet
for tekniska `rfid_scan_event`. Radvis Historik visar modul, tagg, tid, status
och scanraknare nar backend har tagit emot en scan.

## [2026-06-14] change | RFID-sketch ar lokal och ignorerad

ESP32/RDM6300-sketchfilen `rfid_esp32_flow.ino` trackas inte langre i git.
Den ar git-ignorerad som lokal hardware-konfig eftersom den innehaller WiFi,
serveradress och eventuell RFID-token direkt i Arduino-filen.

## [2026-06-14] fix | Lokal server lyssnar pa LAN for RFID

`start_local.bat` startar nu uvicorn med `--host 0.0.0.0` sa ESP32-moduler pa
samma WiFi kan posta RFID-scans till datorns LAN-IP. Browsern oppnas fortsatt
pa `localhost:8000`, och RFID-wikin beskriver att saknad `POST /api/rfid/scans`
i terminalen betyder att scannen inte natt backend.

## [2026-06-14] security | RFID-firmware flyttar lokal konfig ur ino

ESP32/RDM6300-firmware laser nu lokal konfig fran
`rfid_esp32_flow.local.h`, som ignoreras av git. Den committade `.ino`-filen
har bara generiska fallback-varden och en example-header visar vilka varden som
ska fyllas lokalt.

## [2026-06-14] fix | Bemanning tolererar produktivitetssync-fel

`GET /api/schedule/productivity-summary` returnerar nu samma svarshape med
`cache.status=source_unavailable` nar extern Produktivitet-snapshot inte kan
synkas. Bemanning kan da fortsatta visa schema och eventuell redan
materialiserad produktivitetscache i stallet for att fa 502.

## [2026-06-14] change | Verksamheter far bolag och personer far RFID

Verksamheter har nu `company_codes` for bolagskoder per verksamhet. Super User
kan skriva bolag i Verksamheter-vyn, till exempel `BOLAG1, BOLAG2, BOLAG3`,
och API:t normaliserar listan. Personer har nu valfri `rfid_code` for
brickkoppling i Personer-vyn, ny person-modal, direktimport och Excelmall.
RFID-koder normaliseras till versaler och far inte dubbletteras inom samma
verksamhet.

## [2026-06-14] change | Bemanning visar historiskt snitt vid hover

Bemanning har inte langre en `V+H`-knapp som laddar hela dagens kapacitetskarta
och skriver snitt i alla cellnamn. I stallet visar cell-hover ett debouncat
tooltip-anrop till `GET /api/schedule/activity-capacity/cell` for aktuell
person och aktivitet. Tooltipen cachar svaret per dag/person/aktivitet och
anvander fortsatt `staffing_history_hours` och
`staffing_activity_capacity_activity_ids` fran `Installningar > Bemanning`.

## [2026-06-11] fix | Installningars ytkarta stoppar max-utzoomning

Ytgenereringens ytkarta i `Installningar` har nu samma max-utzoomning som
resultatkartan i Bearbeta. `0` aterstaller fit-vyn och minusknapp eller mushjul
kan inte zooma ut langre an den vyn.

## [2026-06-11] fix | Ytgenerering visar bara aktiv toggle i UTL-editorn

Ytgenereringens filtermodal i Bearbeta visar nu bara `Utlastningsytor`-raden
for aktiv omradestoggle. `Alla` visar bara `Alla`, medan exempelvis `AS` visar
bara `AS`. Sparning behaller redan sparade UTL-intervall for andra toggles, sa
anvandaren kan byta toggle for att andra nasta omrade utan att nollstalla resten.

## [2026-06-11] performance | Bearbeta skippar filstatus for API-kallor

Bearbeta hamtar inte langre uppladdnings-/coredatastatus for synliga floden nar
kallvalet star pa `API`. `/api/coredata/files` och IndexedDB/localRef-status
behovs bara i `Uppladdningar` eller for Bearbeta-knappar dar anvandaren valt
`Uppladdning` som kallval. API-kallor visas darfor som redo utan att lokala
eller serverlagrade filstatusar kontrolleras vid sidstart.

## [2026-06-11] change | V+H-aktiviteter valjs i Installningar

Bemanningens `V+H` visar nu parentesvarden bara for de KPI-aktiviteter som ar
valda i `Installningar > Bemanning`. Settingen sparas som
`staffing_activity_capacity_activity_ids`: `null` betyder alla KPI-aktiviteter,
en lista betyder bara dessa aktiviteter och `[]` betyder inga. Backendens
`GET /api/schedule/activity-capacity` filtrerar kapacitetssvaret enligt valet.

## [2026-06-10] performance | Bemanning laser materialiserad personproduktivitet

Bemanning har nu en materialiserad cachetabell, `person_productivity_daily`,
som byggs fran global Produktivitet-snapshot, schema och KPI-regler. V+H laser
historiska processrader fran cachen i stallet for att klassificera om gamla
snapshotfiler vid varje visning. Produktivitetskolumnen i Bemanning hamtar nu
`GET /api/schedule/productivity-summary`, ett litet person-id-till-procent-svar,
i stallet for hela `/api/productivity`-rapporten.

## [2026-06-10] change | Bemanningscell kan delas i fler delar

`Dela timme` i Bemanning har nu val for `1/2`, `1/3` och `1/4`. Vid `1/3`
anges minutstarterna `20` och `40`, och vid `1/4` anges `15`, `30`, `45`.
Backendens split-endpoint accepterar nu 2-4 sammanhangande minutsegment som
tacker `0-60`, och merge tillbaka till hel timme raderar alla extra delar.

## [2026-06-10] fix | Bemanningssummering visar decimaler

`Summering per aktivitet` i Bemanning visar nu heltal utan decimaler men
icke-heltal med upp till tva decimaler. Det gor delade celler med udda minuter,
till exempel 17/43, synliga som faktiska timandelar i stallet for avrundade
heltal.

## [2026-06-10] fix | Produktivitet anvander kpi.sql som intern logik

Produktivitet och Bemannings kapacitetsberakning laser inte langre nagon
separat malregelfil. KPI-malen kommer fran `v_ask_kpi_target`/`kpi`, medan
klassificeringen av loggrader till processer och matt bygger pa den interna
standardlogiken fran `referens/kpi.sql`.

## [2026-06-10] fix | Bemanningens V+H anvander ratt verksamhet

Bemanningens aktivitetskapacitet anvander nu anvandarens standardverksamhet for
historikinstallning nar Super User star i alla-verksamheter-lage. Produktivitet
visar dessutom KPI-coredatafallback i statusraden nar snapshoten bar med sig
`fallback_reason`.

## [2026-06-10] fix | Produktivitet visar fallbackorsak for KPI-API

Produktivitetens snapshot-metadata sparar nu `fallback_reason` nar `kpi`
(`v_ask_kpi_target`) inte kan hamtas via API men lokal KPI-coredata kan anvandas
i stallet. Produktivitetstradet visar schemalagda timmar/stod med 0 poang
nar KPI-output saknas och markerar KPI-processerna i `missing_rule_processes`.

## [2026-06-10] change | KPI-mal och KPI-logik separeras

Produktivitetens KPI-mal kommer fran `v_ask_kpi_target`/`kpi`. Klassificeringen
av loggrader till processer och matt ligger i den interna logiken baserad pa
`referens/kpi.sql`, och samma logik anvands av Produktivitet, Personer-dialogen,
Min produktivitet och Bemannings kapacitetsberakning. Den gamla sektionsbaserade
produktivitetsrapporten i `productivity_service.py` och dess legacytester ar
borttagna, medan filstatus, KPI-mal, snapshots och sammanstallda loggar finns
kvar.

## [2026-06-10] change | Bemanningscell kan delas med valfri minut

Dubbelklick pa en hel cell i Bemanning oppnar nu en minutfraga dar `30` ar
forifyllt och markerat. Enter fortsatter direkt med 30 eller med inskriven
minut, till exempel 17 som sparas som segmenten `0-17` och `17-60`.
Backendens split-endpoint, rendering och draglogik accepterar nu tva
sammanhangande minutdelar i stallet for bara fasta 30/30-halvor.

## [2026-06-10] fix | Omradesfokus slutar falla tillbaka till Stigamo-koder

Sidebarens omradesfokus bygger nu bara valbara omraden fran `/api/areas`.
`sort_order` fran Area styr ordningen och `∞` laggs bara till som filterlage
for Super User eller verksamheter med aktiv `ANNAT`-markor. Om `/api/areas`
misslyckas visas en disabled toggle med feltext i stallet for fallback till
hardkodade MG/GG/AS/EH/R3-varden.

## [2026-06-10] fix | Stodtimmar raknas i Produktivitetstradet

Produktivitetens tradvy raknar nu stodceller som arbetade timmar i
verksamhet/omrade/aktivitet/person. Noder med stod men utan KPI-tid visar
fortfarande `-` som egen kvot, medan blandade omrades- och helbildsnivaer
raknar poang per alla arbetade timmar. Stod-only-personer behalls i
dagrapportens `people[]`, men personens egen produktivitetsvy fortsatter
filtrera pa KPI-celler.

## [2026-06-10] fix | ASK-import anvander forecastens bolag

Ytgenereringens servergenererade ASK-import och kartans lokala justerade
ASK-export hamtar nu `company` fran Forecast-/orderkolumnen `Bolag` i stallet
for ett hardkodat `MG`. `pick_zone` ar fortsatt alltid `A`. Om bolag saknas
stoppas exporten med synlig feltext i stallet for att skriva fel bolag.

## [2026-06-10] fix | Ytgenerering tar bort MG-hardkodad UTL-start

Ytgenereringens osparade UTL-standard ar nu 1-652 for alla toggles. MG eller
andra omraden som ska borja pa exempelvis 205 styrs i stallet av den personliga
Ytgenerering-installningen i Bearbetas filtermodal och sparas i
`allocation_user_filter_profiles`.

## [2026-06-10] fix | Bearbeta-matrisen använder aktiva områden

Bearbeta-matrisens `GET /api/allokering/process-matrix` bygger nu rader från
aktiva `Area`-poster i databasen i stället för en hårdkodad GG/MG/AS/EH/R3-lista.
Frontendens fallback innehåller bara `Alla`/default, och `PUT` mergar bara de
rader användaren kan se så andra verksamheters sparade matrisregler inte raderas.

## [2026-06-10] fix | Bemanningskalkylens dialog stangs inte av bakgrundsklick

Dialogen for ny/andrad automatisk bemanningskalkyl stangs nu bara via
`Avbryt` eller efter lyckad `Spara`. Klick utanfor rutan stanger inte langre
modalen, sa anvandaren inte tappar ifyllda falt vid felklick eller textmarkering.

## [2026-06-10] feature | Aktiviteter far separat VAS-arbetstyp

Aktiviteter har nu `work_type` med vardena `normal` och `vas`. VAS visas och
sparas separat fran `category`, sa kategorin fortsatt kan betyda arbete eller
franvaro for bemanning, produktivitet och andra berakningar. Importmallen,
direktimporten och aktivitetsmodalen har faltet `Arbetstyp`; befintliga
aktiviteter far `normal` via migration.

## [2026-06-10] polish | Produktivitetstradet anvander Omrade

Produktivitetstradet visar nu nivan `Omrade` i stallet for `Avdelning`, i linje
med resten av Flow-terminologin. Underliggande data ar fortsatt aktivitetens
omrade fran schemacellen.

## [2026-06-10] docs | Avancerad filfiltrering blir agentbegrepp

Begreppet `Avancerad filfiltrering` finns nu i agentordlistan och betyder
Bearbetas filterdialog fran edit-ikonen: per fil/API-kalla, API/Uppladdning,
flera villkor, personlig sparning och import fran annan anvandare. Bemanningens
kalkyldokumentation pekar pa samma begrepp for framtida ateranvandning i nya
bemanningskalkylens underlag.

## [2026-06-10] polish | Produktivitetstradet far sammanhangande grenar

Produktivitetens tradvy ritar nu barnnoder med gren-wrappers i stallet for
fristaende kortlinjer. Roten kopplas till en horisontell gren och varje barn
har en egen lodrat anslutning; nar det finns manga barn scrollas tradytan i
sidled sa grenlinjen inte bryts upp.

## [2026-06-09] fix | Windows-login via desktop-proxy

Windows-appens lokala API-proxy skickar nu `Accept-Encoding: identity` till
central server i stallet for att vidarebefordra webviewens komprimeringslista.
Det skyddar login och andra JSON-svar fran att visas som trasiga bytes i
desktop-webviewen nar den paketerade appen saknar samma dekodning som servern
eller utvecklingsmiljon.

## [2026-06-09] polish | Produktivitetens periodruta visar valt lage

Datumrutan i Produktivitet visar nu olika kort etikett beroende pa periodval:
dag visar datum som tidigare, vecka visar `Vecka N`, manad visar manadens namn
och ar visar artalet. Sjalva datumet anvands fortsatt som ankare for perioden
och pilarna hoppar en dag, vecka, manad eller ar beroende pa lage.

## [2026-06-09] polish | Produktivitetens flowchart-export far nivaval

`Exportera flowchart` i Produktivitet oppnar nu forst en dialog med checkboxar
for vilka nivaer som ska inga i SVG-exporten. Valet sparas lokalt i browsern
och den fokuserade nodens egen niva tas alltid med sa exporten behaller en
tydlig rot.

## [2026-06-09] fix | Produktivitet grupperar pa aktivitetens omrade

Produktivitetens tradvy anvander nu aktivitetens omrade fran schemacellen for
avdelningsnivan, inte personens hemomrade. Det hindrar till exempel att GG
Helpall/GG Pafyll hamnar under Autostore bara for att personen har hemomrade AS.
Backend skickar `activity_area_id`, `activity_area_code` och
`activity_area_name` pa segment/time cells.

## [2026-06-09] change | Bemanningens historiktimmar blir installning

Historikfonstret for V+H-kapacitet och automatiska bemanningskalkyler ar nu
`staffing_history_hours` i `app_settings`, default 40 timmar. `installningar.html`
har en Bemanning-flik dar behoriga anvandare kan lasa/andra vardet via
`GET/PUT /api/settings/staffing`. Egen vybehorighet `staffingSettings` styr
lasning och sparning.

## [2026-06-09] feature | Automatisk bemanningskalkyl per anvandare

Bemanningskalkylen har nu alltid en fast `Manuell` panel och kan kompletteras
med personliga automatiska kalkyler. Plusknappen oppnar dialog for Namn,
Process, Bolag, Zon och Plockdagar. Profilen sparas per anvandare i
`staffing_calculator_profiles` och kan importeras fran annan atkomlig anvandare.
Automatkalkylen hamtar `Detalj Kundorder (Alla)`, filtrerar orderrader med
`line_status < 34`, bolag, zon och orderdatum fran Plockdagar, och visar bara
`Rader kvar efter schemalagd tid` baserat pa kvarvarande schemalagda timmar och
personernas konfigurerade historikfonster pa samma process (default 40 timmar).

## [2026-06-09] feature | Min produktivitet visar personens KPI-data

`Min produktivitet` visar nu faktisk personproduktivitet fran den globala
produktivitetscache som Personer-dialogen anvander. `/api/personal/productivity`
returnerar fortsatt schema for valt datum, men innehaller ocksa
`productivity.day` och `productivity.week` med aktivitetssnitt, KPI-poang,
poang per timme, saknade snapshotdatum och backfillstatus. Personrollen ser
bara sin egen person; Super User kan fortsatt valja person.

## [2026-06-09] feature | Personer visar produktivitetssnitt

Produktivitetsdata behandlas som global programdata: API-snapshots ligger kvar
per datum och en daglig backfill hamtar en aldre dag i taget. Produktivitetens
status visar nu backfill-laget. Personer-vyn har fatt dubbelklick pa personrad
som oppnar en dialog for aktivitetssnitt per vecka, manad, ar eller datumperiod
via `GET /api/productivity/persons/{person_id}`. Windows desktop proxar samma
centrala endpoint.

## [2026-06-09] change | Produktivitetens diff-ikon visar poang direkt

Diff-`!` i Produktivitetens timceller markerar nu att hela cellen kan
vansterklickas for samma summerade processpoang som tidigare fanns bakom
hoger-klick -> `Visa poang`.
Hoger-klickmenyn ar borttagen eftersom den gamla vansterklicksdetaljen var
mindre anvandbar.

## [2026-06-09] change | Produktivitet visar bemanningsmatris med poang

Personraderna i Produktivitet visas nu som en Bemanning-lik matris fram till
aktuell timme for dagens datum. Hela schematimmar visas som hela celler,
halvtimmesbemanning som splittrade celler, och cellen visar aktivitet plus
samlade KPI-poang. Processnamnet visas inte i celltexten; diffar markeras med
`!` i cellen och klick visar vilken faktisk process som diffade.

## [2026-06-09] fix | Produktivitet historik och NoMan-matchning

Produktivitetens scheduler gor nu en forsta API-snapshotfyllnad for 13 dagar
bakat plus dagens datum via en intervallhamtning per kalla som splittas till
dagsmappar. Darefter uppdateras bara dagens datum vid varje hel- och halvtimme,
sa dagens filer ersatts medan aldre dagsmappar sparas. Rapporten matchar nu
loggens `Anvandare`/`user_id` mot personens `NoMan`; visat namn ar fortsatt
personens `Namn`, och personer utan `NoMan` ingar inte i Produktivitet.

## [2026-06-09] fix | Bearbeta-knappar haller flodesnamn pa en rad

Bearbeta-flodesknapparna ar nu bredare fasta chip i desktopvyn och tavlan haller
kolumnerna pa en rad med sidledsscroll vid behov. Langa flodesnamn som
`Orderoversiktkontroll` bryts inte langre mitt i ordet i normal desktopvy.

## [2026-06-09] fix | Produktivitet kan byta API-datum

Produktivitetens datumfalt laser inte langre sig till den enda dagen som finns i
en dagsbaserad API-snapshot. Nar rapporten bara har ett datum kan anvandaren nu
valja ett annat datum eller klicka foregaende/nasta kalenderdag, och backend
forsoker da hamta snapshot for det valda datumet.

## [2026-06-09] fix | Produktivitet synkar hela KPI-underlaget

Produktivitetens API-snapshot hamtar nu hela loggfamiljen som KPI-reglerna bygger
pa: pick, trans, loading/pallet, receive, order_log, sort, base_pallet och kpi.
`base_pallet` hamtas som buffertpallsunderlag utan dagfilter, medan dagsloggarna
filtreras pa dagens timestamp nar API:t stoder det. Om KPI-mal-API:t svarar 403
kan snapshoten anvanda permanent KPI-coredata for verksamheten som fallback.

## [2026-06-09] polish | Storre Bearbeta-knappar

Bearbeta-flodesknapparna ar bredare, har hogre klickyta och fasta edit-/infoikonsegment.
Langa flodesnamn far brytas pa knappen i stallet for att tryckas in mot ikonerna.
Samma frontend-CSS anvands av webb och Windows-appen.

## [2026-06-08] feature | Videostorlek i Meta

Meta-vyn visar nu videostorlek i sandningsanalysen, sorterar pa faktiska bytes
och inkluderar storlek i Excel-exporten. Sammanfattningen visar aven total
videomangd for de laddade Meta-uppladdningarna.

## [2026-06-08] feature | Produktivitet visar personbaserad dags-KPI

Produktivitet ar ombyggd fran fasta plock-/dekanteringssektioner till en
personrad per schemalagd person. Backend synkar dagens API-snapshot for
pick/trans/loading/receive/order/sort/base pallet/kpi vid startup och vid varje hel- och halvtimme,
beraknar KPI-poang via kodade regler fran `referens/kpi.sql`, visar STOD och
absence utan att de drar ner procenten och markerar diffar nar faktisk KPI-process
inte matchar schemat. Desktop proxar nu central `/api/productivity` som sanning
for rapporten.

## [2026-06-09] fix | Produktivitet visar fallback nar API-snapshot felar

Produktivitetens filstatus markerar inte langre API-first som klar nar senaste
API-snapshot-sync har felat och ingen serverfallback finns. Frontenden visar nu
en tydlig fallbackstatus med filkrav efter exempelvis extern `HTTP 403`, i
stallet for att lamna rapportytan tom med bara en toast.

## [2026-06-08] docs | Tog bort projektkarta Mermaid

Tog bort den separata sidan `project-mermaid.md` och lankningen fran
`index.md`, sa wikin inte listar en fristaende Mermaid-projektkarta.

## [2026-06-08] feature | KPI Mal processnamn pa aktiviteter

Aktiviteter har nu ett valfritt `kpi_process_name` som visas som `KPI Mal` i
Aktiviteter. Faltet finns i ny/redigera-dialogen, Excelmallen och direktimporten
`Flera nya aktiviteter`. Anvandaren skriver bara processnamn, till exempel
`dekant, plock`; kommaseparerade varden normaliseras och format med bolag som
`GG:decanting` stoppas eftersom verksamheten redan kommer fran aktiviteten.

## [2026-06-08] data | Fyller KPI Mal pa befintliga aktiviteter

Alembic-revision `0036_activity_kpi_backfill` fyller en gang i
`kpi_process_name` for befintliga aktiviteter utifran verksamhetens processlista.
Migrationen skapar inga aktiviteter och skriver bara i tomma KPI Mal-falt, sa
anvandarnas senare andringar i Aktiviteter fortsatter vara vanliga sparade
registerandringar.

## [2026-06-08] test | Driftkontrakt for Alembic och Render

Testerna skyddar nu deploykritiska kontrakt som annars kan falla forst efter push:
Alembic-revisioner far plats i `alembic_version.version_num`, ar unika, har
giltig `down_revision`-kedja och exakt en head. CI-/Render-kontraktet verifierar
dessutom att push-workflowen simulerar Render-build mot Postgres, att
`alembic upgrade head` kors fore pytest och att hemliga Render-envs ar
secret-backed i stallet for literalvarden.

## [2026-06-08] feature | Verksamhet i registertabeller

Anvandare- och Aktiviteter-vyerna visar nu en egen `Verksamhet`-kolumn i
huvudtabellen. Kolumnen bygger pa befintligt `business_id` i API-svaren, anvander
verksamhetsnamn nar det finns och kan sorteras via de klickbara tabellrubrikerna.

## [2026-06-08] feature | Klickbara tabellrubriker

Vanliga list- och rapporttabeller far nu gemensam klient-side sortering via
`common.js`: klick pa en rubrik sorterar synliga rader stigande/fallande och
visar en diskret indikator. Specialtabeller med egen logik, till exempel
Bemanning, Oversikt, Personer, Verksamheter, Meta, modaler och Bearbeta-
editorer, undantas for att inte fa dubbel sortering. Meta behaller sin egen
sortering, och Etikett-kolumnen ar nu ocksa sorteringsbar dar.

## [2026-06-08] feature | Personliga Bearbeta-filtreringar

Bearbeta-matrisen filtrerar inte langre uppladdade filer, API-kallor eller
tabellrader. Matrisen styr nu bara vilka Bearbeta-floden som syns per toggle.
Varje Bearbeta-funktion har i stallet en edit-ikon till vanster om info-ikonen
dar anvandaren sparar egna filter per fil/API-kalla. For `Ytgenerering` sparar
samma editmodal ocksa UTL-intervall per toggle och transportorskluster
inklusive grupp, start/end seq, ordning och tider. Profilen lagras per
anvandare i `allocation_user_filter_profiles`, foljer med efter logout/login
och kan kopieras fran en annan atkomlig anvandare via rullista i modalen.

## [2026-06-08] change | Ytgenerering-installningar flyttas fran matrisen

Ytgenereringens utlastningsytor (`Fran`/`Till`) och transportorsgruppering har
flyttats fran den globala Bearbeta-matrisen till Ytgenereringens personliga
editprofil. Matrisdialogen visar nu bara toggle + funktioner. Backend och
desktop-runtime applicerar `settings.ytgenerering` fran samma
`filter-profile`-payload som filfiltren innan `warehouse_tools` kor flodet.

## [2026-06-08] feature | Bearbeta-edit valjer API eller uppladdning

Editmodalen for Bearbeta-funktioner visar nu en källtoggle for filer och
karnfiler som kan hamtas API-first. Standard ar fortsatt API, men anvandaren
kan valja `Uppladdning`; valet sparas per anvandare i `filter-profile` som
`sources` och gor filen kravd i Bearbeta tills en uppladdad/localRef/coredata-
fil finns. Backend och desktop-runtime filtrerar bort de API-kallor som
anvandaren valt som uppladdning innan source-resolvern kor.

## [2026-06-08] polish | Bearbeta-kallval visas som switch

Kallvalet i Bearbeta-edit visas nu som en kompakt pill-switch: gront `API`-lage
nar API-first-hamtning anvands och gratt `Fil`-lage nar anvandaren vill krava
uppladdning. Samma personliga `sources`-varde sparas fortsatt i
`filter-profile`, sa andringen ar visuell och paverkar bade webb och desktop via
samma frontend.

## [2026-06-08] fix | Skicka person skyddar tidigare timmar

Bemanningsflodet `Skicka till <omrade>` stoppar nu om klienten inte kan avgora
en saker starttimme. Starttimmen jamfors mot valt datum med lokal datumstrang
och kan annars tas fran fokuserad timcell; flodet faller inte langre tillbaka
till 06:00. Det skyddar redan satta tidigare timmar fran att tommas av misstag.

## [2026-06-08] feature | Klick markerar personrad

Bemanning och Oversikt markerar nu hela personraden diskret nar anvandaren
klickar pa personen eller en cell i raden. Markeringen ar lokal och visuell,
sparas inte i databasen och paverkar inte schema, filter, sortering eller
dragfyllning.

## [2026-06-08] fix | Skicka person lamnar tomma lanetimmar

Hogerklicksflodet `Skicka till <omrade>` i Bemanning fyller inte langre hela
dagen med malomradets standardaktivitet. Personen markeras i stallet med
`loan_area_id` och tomma schemaceller fran aktuell timme och framat, sa
mottagande omrade kan valja aktivitet sjalv. Tidigare timmar bevaras och tomma
lanemarkeringar raknas inte som aktivitetstimmar i summeringen.

## [2026-06-08] fix | Påfyllnadsprio får API-källor

Påfyllnadsprio ingår nu i Bearbetas API-first-karta med `orders`, `saldo` och
`overview` som krav. Det hindrar `KeyError: 'orders'` när flödet körs utan
uppladdade filer och låter lastningsfönsterläget använda API-hämtad
orderöversikt på samma sätt som tidigare uppladdat underlag.

## [2026-06-08] fix | Nya personer schemalaggs inte bakat

Implicita veckomalltimmar for personer raknas nu bara fran personens
skapandedatum och framat. Bemanning, Oversikt, Narvarande, Mitt schema och
publika timmar/personer anvander samma datumstyrda mallservice, sa en ny person
inte far standardtimmar pa gamla veckor om det saknas explicita schemaceller.

## [2026-06-08] docs | Bearbeta kodsokvagar

Lade till en praktisk kodkarta i `warehouse-tools.md` for hur man foljer ett
Bearbeta-`flow_id` fran knapp till frontend, API, desktop local runtime,
API-first/fallback, `warehouse_tools`-handler, motor, resultat och tester.
Sektionen innehaller ocksa `rg`-kommandon och en tabell over vanliga flow-id.

## [2026-06-08] docs | Bearbeta-vyn i Mermaid

Lade in en egen Mermaid-sektion i `warehouse-tools.md` for Bearbeta-vyn. Den
visar hur vyn bootar, hur omradestoggle, Bearbeta-matris, filstatus,
karnfiler och API-first styr flodesknapparnas readiness, samt hur webb och
Windows delar korflode men skiljer sig genom desktop localRef och lokal runtime.

## [2026-06-08] docs | Fordjupad projektkarta

Byggde ut `project-mermaid.md` med en enklare mental modell, nyckelbegrepp,
sekvensdiagram for skyddade webbsidor, Windows-start, desktop localRef,
Bearbeta/Ytgenerering, Produktivitet, Meta och personliga vyer. Sidan har nu
ocksa en lasguide for var man bor borja i koden samt en tydligare karta over
datatyper, primar lagring och fallback.

## [2026-06-08] fix | Ytgenerering accepterar API-Item Option

API-materialiseringen for `item_option` kraver nu tekniska katalog-id:n
`not_stackable` och `whole_pallet_near_miss_percent`, och mappar dem till
Forecastens gamla CSV-rubriker `Ej staplingsbar` och `Helpalls avvikelse %`.
Om API-vyn saknar tekniska id:n underkanns API-kallan och Ytgenerering faller
tillbaka till uppladdad eller verksamhetens karnfil, i stallet for att tolka
saknade regler som tomma varden. `data-fetch.md` och `wiki/AGENTS.md`
dokumenterar att tekniskt id ska kontrolleras fore svenska labels.

## [2026-06-08] feature | Ytgenerering kor Forecast i samma knapp

Bearbeta visar nu `Ytgenerering` som den publika Forecast & yta-knappen. Flodet
hamtar Forecast-underlagen API-first, kor Forecast internt och lagger till
ytkarta, ytgenereringstabeller och automatisk ASK-import nar `location` finns.
Om `location` saknas eller inte kan hamtas visas Forecast-resultatet anda med
loggrad om att lagerplatser saknas. Den tekniska `forecast`-handlern och gamla
sessionbaserade Ytgenerering-anrop finns kvar for legacy, men nya webb- och
desktopklick skickar normalt inte `forecast_session_id`.

## [2026-06-08] feature | Meta-tabell med ASK-uppslag och export

Meta-analysen tolkar nu "pall", "godsmärkning"/"godsmarkning" och
"godsmärke" som pall-id i audio-only-prompten. Efter analys berikas raden fran
ASK Dispatchpallar via pall-id med ordernummer, sandningsnummer, anvandare och
kund. Super User-vyn for Meta har sok, sortering, Excel-export for alla eller
filtrerade rader, klientko for nedladdningar och backend-ko for playable-video-
transkodning.

## [2026-06-08] docs | Projektkarta i Mermaid

Lade till `project-mermaid.md` med helhetsdiagram for webbapp, Windows-app,
backend, lagerverktyg, data, test, drift och wiki. Sidan markerar ocksa filer
och mappar som inte verkar inga i ordinarie runtime eller som bara anvands som
legacy-/fallback-/releaseartefakter, utan att behandla dem som sakra
raderingskandidater.

## [2026-06-08] polish | Meta-vyn visar bara sandningsanalysen

Meta-vyn har inte langre den nedre kortgridden for uppladdade bilder och videor.
Super User arbetar i stallet direkt i sandningsanalystabellen, dar video,
etikettstillbild, timestamp, nedladdning och analys finns samlade per rad.

## [2026-06-05] fix | Minska serverminne for Bearbeta och Meta

Bearbeta-resultat skrivs nu till temporara serverfiler i stallet for att fulla
DataFrames ligger kvar i `allocation_bridge.SESSIONS`; sessionen haller metadata,
filreferenser och agare med TTL/maxantal/byte-budget. Warehouse runtime-cacher,
Bearbeta-uppladdningscache och Hamta data-exportsessioner har striktare
rensning. Meta-autostart ar avstangd som standard med
`META_ANALYSIS_AUTO_START=false`, och `tools/meta_analysis_worker.py` kan plocka
koade audio-only-analyser utanfor web request-flodet nar lagringen stods.
Halsa/healthcheck visar processminne och prioriterar Render app-loggar.

## [2026-06-05] fix | Tomt Max rader hamtar alla rader

Hamta data har nu tomt `Max rader` som standard. Nar faltet lamnas tomt skickar
frontend `max_rows=null` och backend begransar inte resultatet efter extern
fetch, sa tabell och Excel-export innehaller alla rader som datakallan
returnerar. Ifyllt tal fungerar fortsatt som manuell begransning.

## [2026-06-04] fix | Meta-download och frontend-boot

Meta-vyn laddar nu ner bilder och videor via browserns direkta
nedladdningsflode med HEAD-kontroll och download=1, i stallet for att
forst lasa hela mediafilen som JS-blob. Det minskar RAM-risk for stora videor
och stoppar HTML-felsvar fran att visas som lang raw markup i en toast.
Samtidigt namespacades common.js interaction-endpoints sa de inte krockar med
api.js globala konstanter; krockan gjorde att vanliga sidor kunde sluta boota
efter login och fallerade Playwright-testerna.

## [2026-06-04] fix | Historik-kontroller matchar frontend-idn

Interaction-coverage i Historik anvander nu samma faktiska kontroll-id:n som
frontendens personer-, aktiviteter- och anvandarvyer. Det gor att
known-controls-kontraktet i CI inte faller pa gamla camelCase-alias.

## [2026-06-04] fix | Flyttar legacy-data mot DB och persistent disk

Legacy-karnfiler och KPI kan nu migreras till `coredata_files` med
`python -m backend.scripts.migrate_legacy_data_to_truth`, utan att scriptet
raderar gamla repo-filer. Sammanstalld produktivitetsdata, buffertpall-
observations och `artikel_max.csv` pekar mot `PRODUCTIVITY_DATA_DIR` eller
`MEDIA_STORE_ROOT/flow-data`; lokal/dev faller tillbaka till den projektlokala
ignorerade mappen `local_media/flow-data` i stallet for repo-kataloger.
Release-checken kraver inte langre att gamla buffertpall-datafiler paketeras i
Windows-bygget.

## [2026-06-05] fix | Buffertpallhistorik kravs innan artikel_max anvands

Lagerfloden som behover `artikel_max.csv` accepterar inte langre en tom/header-only
fallback som giltig sammanstalld data. Saknas observationshistorik for
verksamheten stoppas flodet med krav pa buffertpalluppladdning; observations kan
starta tomt, men `artikel_max.csv` byggs forst nar buffertpallhistorik finns.

## [2026-06-04] feature | Windows kor Bearbeta och Produktivitet lokalt

Windows-appen registrerar nu filval som lokala referenser via Qt-bron och later
desktop-local-servern fanga Bearbeta- och Produktivitet-endpoints. Berakningen
laser aktuell fil fran disk och koar bakgrundssync av karnfiler/KPI och
sammanstalld data utan att starta alla tunga jobb samtidigt. Uppladdningars
`Visa`-preview ar ersatt av explicita `Ladda ner`, `Oppna fil` och `Mapp`-
atgarder sa filer bara hamtas eller oppnas nar anvandaren klickar. Lokala
korningar auditloggas centralt som sanerad metadata utan sokvagar eller
filinnehall.

## [2026-06-03] fix | Minskar 502 vid Render-OOM

Render-startsyncen for allokeringsobservationer ar nu avstangd som standard med
`ALLOCATION_OBSERVATIONS_STARTUP_SYNC=false`, sa servern inte gor tung
observationssync direkt efter omstart. Coredata-status for `artikel_max.csv`
raknar sin path utan att ladda legacy-lagerbryggan, och Windows-klientens
health check forsoker om korta 502/503/504-fonster innan felvyn visas.

## [2026-06-03] fix | Gor Forecast-CLI mappbaserad

`warehouse_tools.cli forecast` kan nu ta Forecasts coredata-filer som egna
argument och `--auto-dir` for att matcha en hel testdatamapp. Orelaterade filer
i mappen ignoreras och tidigare matchade inputs behalls, sa en aktuell
`item_option` i testmappen vinner over fallbacken i `data/coredata/Stigamo`.

## [2026-06-03] fix | Minskar Forecast-minne efter korning

Bearbeta-uppladdningar streamas nu till serverns temporara cache i bitar i
stallet for att lasas som en enda bytes-klump. Forecast sparar fortsatt
resultatet som sessionstabell for Ytgenerering, men skapar inte langre en full
`forecast_json`-kopia av alla rader bredvid DataFrame-tabellen. Gamla
Bearbeta-resultatsessioner stadas opportunistiskt for att minska risken for
Render-minnesspik efter flera stora korningar.

## [2026-06-03] fix | Sanerar 502-HTML i dokumentloggen

Frontendens `api.js` visar inte langre raw HTML nar server/proxy svarar med en
HTML-felsida, utan kort status som `HTTP 502 (Bad Gateway)`. Bakgrundsprefetch
dolder likadana fel i 60 sekunder efter forsta warn-raden, sa dokumentloggen
inte fylls av samma serverfel nar flera forvarmda API:er misslyckas samtidigt.
`user-events.md`, `history-audit.md` och `error-reference.md` beskriver det nya
felsokningsbeteendet.

## [2026-06-02] fix | Synkar uppladdningsnamn mot filkunskap

Uppladdningar, Bearbeta och Produktivitet använder nu svenska `label_sv` från
filkunskapen för kända vyfiler. Exempel: `v_ask_booking_putaway` visas som
`Ej Inlagrade Artiklar`, `v_ask_customer_order_details_all` som
`Detalj Kundorder (Alla)` och `v_ask_palletloading_log` som
`Pallastningslogg`. Prognosfil, Kampanjfil och Textfil med värden lämnas som
Flow-egna namn eftersom de inte finns i filkunskapen.

## [2026-06-02] docs | Synkar releasepolling for agenter

Releasepolling-regeln ar nu dokumenterad i `AGENTS.md`, `TESTPROTOCOL.md` och
`wiki/testing-release.md`: efter push/tagg verifierar agenten normalt bara att
workflowen startat och delar lank. Om anvandaren ber agenten vanta kvar galler
pollingtrappan 15 minuter, 2 minuter, 1 minut och darefter 30 sekunder tills
workflowen ar klar eller failad.

## [2026-06-02] fix | Uppladdningar visar svenska filnamn

Uppladdningars filrader normaliserar nu rubriken via filkunskapen innan den
ritas. Tekniska alias som `customer_order_details_all` visas darfor som
`Detalj Kundorder (Alla)` i stallet for databasnamnet.

## [2026-06-02] change | Samma datamappar for alla verksamheter

Stigamo anvander nu samma buffertpall-upplagg som R3/T3 med egen undermapp
under `warehouse_tools/vendor/lowfreqdata/buffertpall/stigamo/`.
Observations-startup-syncen laser aktiva verksamheter fran databasen i stallet
for en hardkodad Stigamo/R3-lista, och nya verksamheter provisionerar egna
coredata-/sammanstalld-data-roots vid skapande. Produktivitetens
verksamhetsscopeade KPI-lasning har inte langre Stigamo-root som specialfall.

## [2026-06-02] fix | Forsenad observations-sync vid serverstart

Render-starten laddar inte langre lagerverktygens observations-sync direkt.
Startup-hooken finns kvar men vantar nu enligt
`ALLOCATION_OBSERVATIONS_STARTUP_DELAY_SECONDS` och syncar verksamheterna en i
taget med paus enligt `ALLOCATION_OBSERVATIONS_STARTUP_SPACING_SECONDS`.
Automatiken kan stangas av med `ALLOCATION_OBSERVATIONS_STARTUP_SYNC=false`.

## [2026-06-02] fix | Ytkartans hjalplinjer blir mjukare

Installningar for Ytgenereringens ytkarta har nu ett tajtare snap-avstand och
diskretare hjalplinjer vid dragning. Vanliga klick ritar inte langre om kartan
direkt, sa dubbelklick pa en yta fungerar igen for att rotera den 90 grader.

## [2026-06-02] feature | Hjalplinjer vid ytdragning

Installningar for Ytgenereringens ytkarta visar nu hjalplinjer medan en yta
dras. Dragningen snappar mot andra ytors vansterkant, mitt, hoger kant,
topp, mitt och botten sa det blir lattare att hamna i samma hojd eller kolumn.

## [2026-06-02] fix | Ytkartans hogerklicksmeny foljer klicket

Hogerklicksmenyn `Byt riktning` i Installningar for Ytgenereringens ytkarta
positioneras nu lokalt i kartans workspace och kompenserar for appzoom. Den
ska darfor hamna vid hogerklicket i stallet for att flyta ut mot sidopanelen.
Installningar-sidan har ocksa ny script-version sa browsern inte fortsatter
ladda cachad kartkod.

## [2026-06-02] polish | Loggikon signalerar utan raknare

Dokument-/loggikonen i sidebaren visar nu en kort pil upp och en bubbla som
tonar ut varje gang en loggrad skrivs. Den gamla olast-raknaren visas inte
langre och gammalt sessionStorage-varde for raknaren rensas nar ikonen
initialiseras eller signalerar.

## [2026-06-02] fix | Ytkartor skalar nya ytor efter pallplatser

Nar en ledig U-plats laggs till i Installningar for Ytgenereringens ytkarta
skalas ytan nu efter sin `Max pall`. Formen behaller samma kortsidesbredd som
basytan men forlangas langs langssidan, sa en 7-palls-yta blir 3,5 ganger
langre an en 2-palls-yta.

## [2026-06-02] fix | Ytkartsfalt foljer markerad yta

Installningar for Ytgenereringens ytkarta synkar nu sidopanelens falt direkt
nar anvandaren markerar en yta pa kartan. `Yta`, koordinater, storlek och
kapacitet visar darfor den senast markerade ytan aven nar markeringen sker utan
en full omritning av kartan.

## [2026-06-02] feature | Verksamhetsfilter i Historik

Historik har nu ett filter for `Verksamhet` i toppraden. Super User kan valja
Alla eller en specifik verksamhet; valet skickas som `business_id` till
anvandarhistorik, analys, felkoder och Vantetider. Anvandarlistan smalnas av
nar verksamhet valjs. Halsa-fliken fortsatter visa global driftstatus.

## [2026-06-02] polish | Ytkarta roterar med dubbelklick

Installningar for Ytgenereringens ytkarta anvander nu dubbelklick pa en yta
for att rotera ytan 90 grader at vanster runt sin mittpunkt. Lastningsriktning
byts i stallet via hogerklicksmenyn `Byt riktning`, som fungerar for bade en
markerad yta och flera markerade ytor samtidigt.

## [2026-06-02] fix | Korta UTL-ytor visas i Installningar

Ytgenereringens lagerplatsfilter accepterar nu `Typ=U`-ytor med UTL-nummer
1-652 oavsett om numret ar skrivet med inledande nollor. Det gor att
`UTL01`-`UTL99` syns i Installningars lista over lediga U-platser och kan
anvandas i Ytgenerering pa samma satt som `UTL100` och uppat.

## [2026-06-02] feature | Lanar person via hogerklick i Bemanning

Bemanning har nu en hogerklicksmeny pa personnamn med `Skicka till <omrade>`.
Valet skriver personens schemalagda timmar for aktuell dag till malomradets
aktiva standardaktivitet via `POST /api/schedule/cells` med `action=loan_to_area`.
Personens hemomrade andras inte; samma omradesfilter som tidigare gor att
personen syns bade i hemomradet och i omradet som lanar in personen.

## [2026-06-02] fix | Ytkarta sparas per verksamhet

Ytgenereringens ytkartsinstallningar laser och sparar nu `ytgenerering_map_layout`
i samma verksamhetsscope som vald Bearbeta-toggle. Sparsvaret returnerar samma
scopade layout, sa lastningsriktning och andra andringar inte hoppar tillbaka
direkt efter `Spara`. Frontend visar inte langre sparat om serversvaret saknar
samma ytor, koordinater, kapacitet och lastningsriktningar som skickades.

## [2026-06-02] polish | Lastningspil blir diskretare

Installningar-vyn for Ytgenereringens ytkarta visar nu lastningsriktningen som
en diskret fylld pilkil i ytans kant i stallet for en stor streckpil. Ytkoden
ligger kvar centrerad i hela ytan nar riktningen byts.

## [2026-06-02] fix | Lastningsriktning foljer langsta sidan

Ytgenereringens ytkartsinstallningar vaxlar nu bara mellan tva
lastningsriktningar per yta. Breda ytor kan bara ga hoger/vanster och smala ytor
kan bara ga ned/upp, sa pilen, ytkoden och den randiga outnyttjade kapaciteten
alltid ligger parallellt med ytans langsta sida.

## [2026-06-02] feature | Lastningsriktning styr ytkarta

Installningar-vyn for Ytgenereringens ytkarta visar nu en pil pa varje yta.
Dubbelklick pa ytan byter lastningsriktning mellan hoger, ned, vanster och upp.
Riktningen sparas i `ytgenerering_map_layout` och styr i Ytgenerering var
ytkoden visas samt vilken sida som blir randig vid outnyttjad kapacitet.

## [2026-06-02] polish | Ytkartan visar ledig total kapacitet

Ytgenereringens ytkarta visar nu `Lediga pallplatser` och `Lediga ytor` i
sidopanelens totalsiffror. Vardena raknas om efter manuella kartflyttar, klistra
in och angra, sa anvandaren ser hur mycket kapacitet och hur manga fysiska ytor
som fortfarande ar lediga.

## [2026-06-02] polish | Installningar-kartan matchar ytkartans etiketter

Installningar-vyn for Ytgenereringens ytkarta visar nu ytans korta kod utan
`UTL` med samma fontstorlekslogik och riktning som Ytgenereringens ytkarta.
Texten ligger parallellt med ytans langsta sida och ar inte fetstild, aven nar
ytan flyttas med drag. Ytkoden anvander en storre storlekskurva an tidigare sa
den utnyttjar tomma ytor battre i redigeringskartan.

## [2026-06-02] feature | Lediga U-platser dras till ytkartan

Installningar-vyn for Ytgenereringens ytkarta later nu anvandaren dra en ledig
`Typ=U`-lagerplats fran sidolistan direkt till kartan. Droppunkten oversatts
till kartkoordinater, ytan far kapacitet fran `location`-underlaget och sparas
som vanlig global `ytgenerering_map_layout`.

## [2026-06-02] fix | Transportorskluster fylls med standardvarden

Transportorskluster-popupen i Forecast fyller nu tomma kluster-, start- och
slutsekvensfalt med inbyggda standardvarden for kanda transportorsnummer.
Rader med transportorsnummer 39 och 40 far till exempel `Freja`, 600-652,
09:00/11:00/13:00 och standardfargen. Backendnormaliseringen anvander samma
defaults sa Ytgenerering far reglerna aven om flodet kors via API.

## [2026-06-02] polish | Ytkartans kundtext foljer langsidan

Kundnamn i Ytgenereringens ytkarta roteras nu pa staende ytor, sa huvudtexten
alltid ligger parallellt med ytans langsta sida. Textbredden beraknas mot
langsidan, vilket ger smala staende ytor mer anvandbart textutrymme.

## [2026-06-01] polish | Ytkartan prioriterar kundnamn

Ytgenereringens ytkarta visar nu kort ytkod utan `UTL` i ytans kortsida,
kundnamn i mitten som kan brytas pa tva rader utan halo, ingen pallrad inne pa
ytan och fargade ljusare rander for outnyttjad kapacitet proportionellt mot
ledig andel.

## [2026-06-01] feature | Ytkarta far egen Installningar-vy

Ytgenereringens ytkarta redigeras nu i sidebar-vyn `Installningar` i stallet
for via en knapp i Bearbeta. Vyn kraver `allocationSettings`, har fast
arbetsbredd med fullskarmsknapp, kan panorera och zooma i samma kartcanvas,
och visar lediga `Typ=U`-lagerplatser fran aktiv
verksamhets `location` som inte redan finns pa kartan. Nar anvandaren lagger
till en yta raknas koordinaterna fram fran vald yta, riktning och gap, och
sparas globalt i `ytgenerering_map_layout`. Kartan stoder ocksa multiurval med
Ctrl/Shift, gruppdrag, piltangentsflytt, Delete och Ctrl+C/X/V/Z/A sa flera
ytor kan flyttas, kopieras, klippas, klistras in och angra som en samlad
redigering.

## [2026-05-29] fix | Verksamhetskoder skapas automatiskt

Verksamheter-vyn kräver inte längre att användaren fyller i kod när en ny
verksamhet eller ett nytt område skapas. Backend skapar kod från namnet och
lägger till suffix vid krock. Modalens aktiv-checkbox använder nu modalens
checkboxlayout så etiketten inte glider isär från rutan.

## [2026-05-26] feature | Produktivitetsloggar sammanstalls

Produktivitet uppdaterar nu tre verksamhetsscopeade csv.gz-filer nar Plocklogg,
Translogg eller Palllastningslogg laddas upp. Plocklogg tar nya `Radid`
(kolumn-id `rowid`) och Translogg nya `Rowid`, medan Palllastningslogg tar
rader nyare an senaste sparade `Ändrad`/timestamp och tillater dubbletter inom de nya raderna. Uppladdningar visar de
tre filerna som `Sammanstalld data` ihop med `artikel_max.csv`.

## [2026-05-26] feature | Godsdeklaration i Bearbeta

Bearbeta har fatt flodet `Godsdeklaration`. Flodet anvander Detalj Kundorder,
Orderoversikt och Alternativ leveransadress ihop med verksamhetens
`item_security_info`-karnfil. DG-rader blir klara direkt, LQ-rader blir bara
klara nar adressen gar till Gotlandspostnummer 620-624, och klara ordernummer
kopieras automatiskt nar korningen ar klar. Ny uppladdad `item_security_info`
ersatter tidigare fil for samma verksamhet pa samma satt som andra karnfiler.

## [2026-05-26] fix | Artikel_max visas som sammanstalld data

Uppladdningar skiljer nu pa coredata-karnfiler och den framraknade
`artikel_max.csv`. Artikel_max visas som `Sammanstalld data`, flowkatalogen
markerar den som `sammanstalld data`, och rensa-alla-texterna sager att bade
karnfiler och sammanstalld data ligger kvar.

## [2026-05-26] fix | Forecast laddar paketerad modell i prod

Forecastens prediktering laddar nu en paketerad kalibreringsartefakt i
`warehouse_tools/mg_forecast/calibration.pkl` innan den forsoker bygga om
traningsdata. Det gor Render/prod oberoende av lokal raw historik och hindrar
`No objects to concatenate` nar `data/history/orders` saknas i servermiljon.

## [2026-05-26] fix | Narvarande ligger fore Undo/Redo

Knappen `Narvarande` ligger nu till vanster om Undo/Redo i bade Bemanning och
Oversikt, sa utskriftsflodet hamnar fore historikknapparna i verktygsraden.

## [2026-05-26] feature | Narvarande-lista for utskrift

Bemanning och Oversikt har nu knappen `Narvarande`. Den hamtar en serverraknad
narvarolista fran `/api/schedule/presence`, valjer Alla omraden eller nuvarande
omrade fore utskrift och grupperar Alla per verksamhet sa Super User inte far
blandade verksamheter i samma lista. Windows-appen anvander en QWebEngine-
printbrygga for samma printflode.

## [2026-05-26] feature | Ytgenerering laddar ASK-import

Ytgenerering skapar nu en tabbseparerad ASK-importfil for order/yta nar alla
sandningar ar placerade och Forecast-resultatet innehaller `Ordernummer`. Varje
ordernummer far en rad med sandningens UTL-ytor i `area_num`, `company=MG` och
`pick_zone=A`; frontend laddar ner filen automatiskt efter klart flode.

## [2026-05-26] fix | Observations foljer R3-toggle

Automatisk observations-uppdatering fran buffertfil skickar nu med samma
omradesfokus som ovriga Bearbeta-anrop. Nar Super User star pa R3 anvands
darmed R3:s observations och `artikel_max.csv` i stallet for kontots
standardverksamhet. Dokumentloggen skiljer ocksa pa 0 nya pallid, dar GitHub-
push inte ar aktuell, och nya pallid dar GitHub inte bekraftade pushen.

## [2026-05-26] fix | Forecast tal saknad transportor

Forecast faller nu tillbaka till default-transportoren `Schenker` internt for
modellens transportorsignal nar en sandningsgrupp finns men orderoversikten
saknar transportorvarde for gruppen. Forecast-resultatet och Ytgenerering far
i stallet `Okand`, sa fallbacken inte styr ytregler. Det hindrar att
Bearbeta/Forecast stoppar pa `mode().iloc[0]` nar underlaget i ovrigt ar giltigt.

## [2026-05-26] fix | Ytgenerering tydliggor sandningsplacering

Ytgenereringens logg, tabellnamn och dokumentation forklarar nu att placeringen
sker per sandning. Transportor anvands for sortering och
`Transportorsoversikt`, men en lagerplats delas inte mellan flera sandningar.

## [2026-05-26] fix | Stoppa vy-redirect-loop

Sidinitiering hamtar nu farsk vybehorighet innan redirect-beslut tas. Om en
anvandare saknar behorighet till aktuell vy skickas den till forsta vy kontot
faktiskt far se, och om ingen vy finns visas ett stoppmeddelande i stallet for
att studsa mellan Bemanning och Oversikt.

## [2026-05-26] fix | Healthcheck laser Render build-loggar

Render-loggar i Halsa anvander nu Render Logs API med `ownerId`, service-id och
`type=build`. `ownerId` forsoker lasas fran service-svaret och kan annars sattas
som `RENDER_OWNER_ID`, sa deployfel kan hamtas utan att blanda ihop Postgres med
lokal SQLite.

## [2026-05-26] fix | Healthcheck skiljer Postgres och lokal test

`tools.healthcheck` har fatt `--skip-db` sa agenter kan hamta Render deploy/loggar
utan att fejka lokal SQLite eller koppla upp mot en databas. Dokumentationen
fortydligar att produktionens databas ar Render Postgres; SQLite anvands bara
for lokal utveckling och temporara tester.

## [2026-05-26] fix | Coredata följer med deploy

`data/coredata/` är inte längre ignorerad av git, så verksamhetens kärnfiler kan
versionshanteras och följa med deploy när de läggs till i en commit. CI:s
Render-simulering kör nu samma produktionssteg som `render.yaml`: migrations och
app-start utan `backend.seed`.

## [2026-05-26] process | Halsa som driftregel

Halsa och Vantetider ar nu dokumenterat som permanent agentarbetsregel i
`AGENTS.md`, `TESTPROTOCOL.md` och `wiki/testing-release.md`. Efter storre
pushar/deploys ska agenter kora eller verifiera `tools.healthcheck report` och
`tools.healthcheck waits` for lokal/serverdrift, databas och anvandarvantetider,
och tydligt fixa eller rapportera kvarvarande `warn`/`error`.

## [2026-05-26] fix | Seed och lokal bootstrap spärras mot live

`backend.seed` stoppar nu körning mot `ENVIRONMENT=production` och Render-databas-URL:er. `backend.bootstrap_local` vägrar köra mot annat än SQLite, så lokal schema-/seedbootstrap inte kan råka skriva till live-Postgres om `DATABASE_URL` pekar fel. Dokumentationen skiljer nu på engångsmigrationer, lokal/dev-seed och production-deploy.

## [2026-05-26] fix | Production kör inte seed vid deploy

Render-builden kör nu bara `pip install` och `alembic upgrade head`. `backend.seed` är kvar för lokal/dev-bootstrap och manuell engångsseed, men körs inte längre automatiskt i produktion. Därmed återskapas inte raderade verksamheter, områden, aktiviteter, personer eller användare vid nästa deploy.

## [2026-05-26] feature | Halsa och vantetidsanalys i Historik

Historik har fatt flikarna `Vantetider` och `Halsa`. Klienten matar vyload, API-vantan, nedladdningar och idle-prefetch utan att skriva brus i dokumentloggen; backend sparar sanerade rader i `user_wait_metrics` och summerar p50/p95/max per vy, steg och event. `GET /api/healthcheck` samlar app-, databas- och Render-status for Super User nar Render-secrets finns, och `tools.healthcheck` kan kora samma halsa/vantetidsanalys lokalt eller mot en inloggad server.

## [2026-05-26] fix | Snabbare omradestoggle i planeringsvyer

Bemanning och Oversikt anvander nu en exakt kortlivad cache per omrade/period utöver all-cache. Om anvandaren vaxlar tillbaka till ett omrade som redan hamtats ritas vyn direkt utan nytt API-anrop, medan all-data fortsatter forvarmas och revisionskontrolleras i bakgrunden. Aborts fran egna snabba omladdningar rapporteras inte langre som `network_error | HTTP 0`, och riktiga natverksfel dedupliceras per path en kort stund for att inte fylla Historik.

Planeringsvyerna prioriterar nu all-data direkt nar cache saknas: Bemanning hamtar hela dagen for verksamheten och Oversikt hamtar hela veckan/manaden, filtrerar valt omrade lokalt och fyller cachelagren innan anvandaren togglar vidare. Det minskar risken att forsta omradesbytet hamnar pa ett kallt API-anrop.

## [2026-05-26] polish | Mindre brus i dokumentloggen

Sidoppningar skrivs inte langre i dokumentloggen och gamla `Oppnade vy`-rader filtreras bort fran sessionloggen. Samma handelse rapporteras i stallet tyst till Historik som `view/open` via `/api/audit/client-event`. Bemanningens summeringsvarning visar nu orsak och kontext, till exempel HTTP-/natverksfel, vecka, dag och omrade, sa anvandaren far mer felsokningsbar information utan att loggen fylls av vanliga sidbyten.

## [2026-05-25] feature | NoMan pa personer

Personregistret har fatt ett frivilligt `NoMan`-falt for WMS-anvandarnamn per person. Faltet syns och kan filtreras/sorteras i Personer, kan redigeras inline, finns i Ny person, direktimport och Excelmallen, och sparas via `/api/persons`; det anvands inte i planering eller forecast annu.

## [2026-05-25] fix | Toastar och Bearbeta-fel syns i loggar

Dokument-loggen i sidebaren fylls nu av alla toastar, inklusive lyckade, varningar och fel, och ovantade klientfel hamnar dar direkt. Bearbetas egna API-wrapper rapporterar nu fel till samma `client_error`-audit som resten av appen, och `allocation_flow/flow_failed` sparar statuskod, felkod, kort felmeddelande, tekniskt meddelande nar det skiljer sig, verksamhet, toggle och filterradantal utan filnamn eller inskickade parametervarden. Forecast-felet `No objects to concatenate` visas som att flodet fick noll rader att sammanstalla efter filer/filter.

## [2026-05-25] change | Super User och demo kan personsortera alla synliga personer

Personsorteringen i Bemanning/Oversikt behaller kravet `personSortOrder=edit`, men Super User och demo ar inte langre lasta till eget anvandaromrade. De kan dra och spara sortering for alla synliga aktiva personer; vanliga admin/bemanningsansvariga ar fortsatt begransade till eget hemomrade.

## [2026-05-25] change | Veckonummer i Oversikt

Oversiktens daghuvuden visar nu datum pa forsta raden och `Vecka XX` pa en mindre rad under. Det galler bade veckovy och manadsvy, sa man ser veckonummer per dagkolumn.

## [2026-05-25] change | Ny anvandare valjer en roll

Skapa-flodet for Anvandare valjer nu exakt en roll: `Ny anvandare` visar ett roll-dropdown och `Flera nya anvandare` visar en `Roll`-kolumn som dropdown. Befintliga anvandare kan fortsatt ha flera roller via redigera-modalen och backend/import kan fortsatt lagra `roles` som lista.

## [2026-05-25] change | Super User och Demo syns i Vybehorigheter

Vybehorigheter-modalens rollmatris visar nu `Super User` som en last `Redigera`-kolumn och `Demo` som en egen sparbar kolumn. Backend accepterar demo-rollens vyatkomst och raknar in den for det fasta `demo`-kontot, medan Super User fortsatt alltid far full atkomst via serverregeln.

## [2026-05-25] fix | Sidebar ar fast vid skroll

Sidebaren ar nu en fast vansterpanel i webb och desktop-frontend. Huvudytan reserverar sidebar-kolumnen separat, demo-bannern ger fast offset, och bara menylistan inuti sidebaren skrollar nar det finns fler menyval an vad som ryms.

## [2026-05-25] feature | Forecast och Ytgenerering i Bearbeta

Bearbeta har fatt `Forecast` och `Ytgenerering`. Forecast kor den portade prognosmotorn fristaende i Flow, grupperar per `Sandningsnr`, anvander verksamhetens coredata (`custom`, `item`, `item_alias`, `dimension`, `pallet_type`, `item_option`) och sparar resultatet bade som tabell/Excel och som temporar sessiondata. Ytgenerering kraver verksamhetens `location` och en kord forecast-session, anvander forecastens DataFrame direkt for snabbaste kedja med JSON-artifact som fallback, cachar fardigfiltrerade lagerplatser per `location`-filversion, filtrerar lagerplatser pa `Typ=U`, UTL-nummer 1-652 och `Max pall > 0`, och placerar sandningar transportorsvis utan att dela en lagerplats mellan flera sandningar. Ny `location`-uppladdning raderar den gamla verksamhetsfilen, rensar location-cachen och forvarmer den nya ytlistan direkt. Teststodet omfattar handler-/domantester, API/session/coredata-tester, statiska UI-kontrakt och Playwright-test for att Forecast aktiverar Ytgenerering och skickar `forecast_session_id`.

Allokering anvander nu samma filversionsprincip for snabb upprepad korning: hela outputpaketet med allokerade rader, near-miss, refill och pallplatser cachas per orders-/buffert-/saldo-/item-version. Omradesfiltren for GG/MG sparar ocksa filtrerade kopior per originalfilversion och regel, sa samma resultat ateranvands utan att berakningsresultatet andras.

Synliga vyer for aktuell anvandare forvarms nu gradvis i frontenden via en idle-ko och en kort GET-cache som sparas i sessionen, sa uppvarmningen finns kvar efter sidbyte i samma flik. Uppladdningar har dessutom en separat metadata-cache for IndexedDB-filerna, sa vyn kan visa filrutor direkt och hamta stora blobbar/coredata i bakgrunden. POST/PUT/DELETE rensar GET-cachen, och sena bakgrundssvar ignoreras efter en sadan andring, sa ny uppladdad/raderad data tvingar ny hamtning.

`tools.performance_benchmark` mater nu kall/varm sidvaxling, bakgrunds-prefetch, Uppladdningar, omradestoggle, schema select/drag/copy, Dela-korningar och Excel-importer. Rapporten sparas som JSON under `artifacts/performance/` for fore/efter-jamforelse nar cache eller UX-hastighet andras.

## [2026-05-25] feature | Demo-läge med per-session SQLite-sandbox

flow har fått ett fast `demo`-konto för säljpresentationer. Vid inloggning snapshottas live-databasen till en privat SQLite-fil i temp-mappen och en privat datakatalog skapas. Alla skrivningar routas dit via `get_db()` (engine-byte) och `demo_data_root_var` (filsystem). Vid utloggning raderas SQLite-filen och datakatalogen så nästa demo startar rent. Frontend visar gul/röd `DEMO`-banner och en valbar guidad rundtur genom alla synliga vyer (state via `sessionStorage`). Demo-användaren är låst i Användare-vyn — kan inte tas bort, döpas om eller fråntas admin-rollen, men lösenord/visningsnamn/område kan rotateras. Se [demo-laget](demo-mode.md).

## [2026-05-25] feature | Drag-sortering av personer i planeringsvyer

Bemanning och Oversikt kan nu dra personnamn for att uppdatera personernas `sort_order` i Personer. Ny behorighet `personSortOrder` visas som Personsortering i Vybehorigheter och backend kraver Bemanningsansvarig/admin/Super User, `edit`-atkomst, anvandaromrade och samma hemomrade pa personerna.

## [2026-05-25] change | Bearbeta-matris far egen behorighet

Matris-knappen i Bearbeta styrs nu av `allocationProcessMatrix`: `view` kan oppna matrisen lasande och `edit` kan spara. Admin har `edit` som standard och Super User har fortsatt alltid full atkomst.

## [2026-05-25] feature | Redigerbar Bearbeta-matris

Bearbeta har nu knappen `Matris` for roller med `allocationProcessMatrix=view`; `allocationProcessMatrix=edit` kravs for att spara. Matrisen sparas globalt som `allocation_process_matrix` och styr per toggle bade radfilter (`Bolag`, exkluderade kundnummer) och vilka Bearbeta-funktioner som syns. Standard ar fortsatt GG=`Bolag GG` utan kund 6005, MG=`Bolag MG` utan 40002/90002 och ovriga toggles ser allt.

## [2026-05-25] fix | Lagerverktyg foljer verksamhetstoggle

Super User styr nu lagerverktygens verksamhet via sidebarens omradestoggle. Buffertpall-observations, verksamhetens `artikel_max.csv` och Bearbetas coredata-defaults anvander R3 nar togglen star pa R3 och Stigamo nar togglen star pa ett Stigamo-omrade; `∞` faller tillbaka till kontots egen verksamhet.

## [2026-05-25] fix | Vybehorigheter ar globala

Rollernas `Vybehorigheter` laser och sparar nu en global matris i stallet for en separat matris per verksamhet. Det gor att exempelvis `Lagerkontorist = Bearbeta/Redigera` galler bade Stigamo och R3, medan verksamhetsspecifika settings som cell-lasning och menyordning fortsatt kan vara separata.

## [2026-05-25] feature | Coredata-karnfiler ar verksamhetsseparerade

Filerna under `data/coredata/` hanteras nu per verksamhet for prefixen `custom`, `dimension`, `item`, `item_alias`, `item_attribute`, `item_option`, `location`, `location_cost`, `pallet_type` och `v_ask_kpi_target`. `artikel_max.csv` visas i samma karnfilslista och sparas till lagerverktygens verksamhetsspecifika artikel_max-sokvag. Ny uppladdning ersatter bara gammal fil med samma prefix i anvandarens egen verksamhet. Allokering anvander dessutom verksamhetens `item_option` som karnfil nar ingen lokal Item option-fil laddats upp.

## [2026-05-25] fix | Verksamhetsseparerar produktivitetens KPI-karnfil

Produktivitetens permanenta KPI-mal (`v_ask_kpi_target*.csv`) sparas och lases nu per verksamhet, pa samma princip som lagerverktygens `artikel_max.csv`. Stigamo, R3 och nya verksamheter far separata kataloger under `data/coredata/`; Stigamo har en bakatkompatibel fallback till den gamla root-filen tills en Stigamo-scopead KPI-fil finns.

## [2026-05-25] fix | Produktivitet foljer vybehorigheter

Produktivitetssidan kraver inte langre hard Super User-flagga i frontend. Sidan och API:t styrs av `productivity=view` for lasning och `productivity=edit` for serverhanterade produktivitetsfiler, sa admin kan ge atkomst via Vybehorigheter utan att ge Super User-roll.

## [2026-05-25] fix | Bearbeta följer vybehörigheter

Bearbeta använder nu samma `allocationProcess=edit`-behörighet i backend som i menyn. Det gör att exempelvis Lagerkontorist kan se och köra Bearbeta när rollen satts till Redigera i Vybehörigheter. Utan edit-behörighet visas fortsatt bara självserviceflöden som Dela.

## [2026-05-25] change | Anvandare ar alltid aktiva

Anvandare-sidan har inte langre aktiv/inaktiv-lage, aktiv-kolumn eller "Visa inaktiva". Alla konton halls aktiva av backend och gamla inaktiva rader backfylls via migration/bootstrap. Konton som inte ska finnas kvar tas bort via `DELETE /api/users/{user_id}`; backend skyddar eget konto och sista admin samt nollar gamla anvandarreferenser innan hard delete.

## [2026-05-25] change | Verksamhetsseparerar observations

Lagerverktygens buffertpall-observations och `artikel_max.csv` ar nu separata per verksamhet. Stigamo behaller legacy-filerna medan R3 skriver och laser under `warehouse_tools/vendor/lowfreqdata/buffertpall/r3/`; Ordersaldo, LYX och Pafyllnadsprio anvander verksamhetens karnfil nar egen fil inte laddas upp.

## [2026-05-25] fix | Bevarar lagerverktygens arbetslage vid vybyte

Bearbeta och Dela sparar nu faltvarden, status och senaste resultatpreview per inloggad anvandare i aktuell browser-/desktop-session. Nar anvandaren byter till en annan vy och gar tillbaka finns Allokering, Dela varden och andra lagerfloden kvar visuellt; serverns temporara `session_id` kravs fortfarande for Excel/CSV/kolumnhamtning.

## [2026-05-25] change | Allokering ignorerar orderstatus over 33

Lagerverktygets Allokering filtrerar nu bort orderrader med status over 33 innan pallmatchning, i bade Flow och den vendrade Allokera-motorn. Buffertstatusreglerna ar oforandrade: 29/30/32 for allokering och 29/30 for refill.

## [2026-05-22] feature | Felkodsdashboard i Historik

Historik har nu tre lagen: Anvandarhistorik, Analys och Felkoder. Frontend rapporterar API-fel tyst till `/api/audit/client-error` nar en inloggad anvandare traffar 4xx/5xx eller natverksfel, och Super User kan summera dem via `/api/audit/errors`. Felpayloaden saneras till metod, path utan querystring, status/felkod och kort meddelande for att ge felsokningssignal utan request body, cookies, losenord, filnamn eller queryvarden.

## [2026-05-22] feature | Omraden i Verksamheter-vyn

Verksamheter-vyn for Super User visar nu omraden under varje verksamhet. Super User kan skapa, redigera och ta bort/inaktivera omraden via `/api/areas`; tomma omraden hardraderas medan omraden med kopplade personer, aktiviteter eller anvandare inaktiveras. Lade ocksa till regressionstester som fangar R3-fokus i Personer-vyn, sa Super User inte ser Stigamo-personer nar fokus star pa R3.

## [2026-05-22] perf | Snabbare omradesvaxling i planeringsvyer

Bemanning och Oversikt forhamtar nu alla synliga omraden for aktuell period i bakgrunden och filtrerar omradesfokus klient-side nar cachen finns. Cachen ar verksamhets- och anvandarscopead via de API-svar anvandaren redan far se, och ogiltigforklaras vid schema-/oversiktsandringar for att undvika gammal data. Klienten kontrollerar dessutom latta revision-endpoints tyst i bakgrunden, normalt var 10:e sekund vid aktiv anvandning och var 30:e sekund vid idle, och patchar bara andrade synliga celler nar ny serverdata finns. Bada breda planeringsmatriserna har ocksa en synkad horisontell scrollbar ovanfor tabellen nar nedersta scrollen annars hamnar langt bort.

## [2026-05-22] feature | Fyller auditluckor for anvandarfloden

Utökade Historik/audit-dokumentationen för nya auditrader: första lösenord på konto, globala inställningar, serverhanterade produktivitetsfiler och körda lagerverktygsflöden. Misslyckade uppladdningar som når backend loggas nu också som `upload_failed`/`detect_failed`. Loggarna ska ge felsökningssignal men undvika lösenord, API-detaljer och privata filnamn/listvärden.

## [2026-05-22] rename | Bytte programnamn fran Bemanning till flow

Programmet bytte namn fran "Bemanning" till "flow" (sma bokstaver). Bevarade
termer: Bemanningsvy/Bemanningsvyn (vyn), Bemanningsansvarig (rollen),
Bemanningskalkyl/Bemanningsmatris/bemanningsceller (vy-relaterade features),
wiki/bemanning-schedule.md (filnamn for vyns dokumentation). Ikon for
fonster/desktop bytt till allokeringsprojektets app.ico (-> flow_icon.ico).
Installer-ikonen for releases bevarad (ingen SetupIconFile finns i .iss).

## [2026-05-21] ingest | Initial projektwiki

Skapade forsta LLM-wikin for flow enligt Karpathy-modellen: index, agentregler, kallmanifest, arkitektur, datamodell, rollmodell, API-karta, UI- och funktionssidor samt felsokningssida for framtida LLM-chat.

Kallor som lastes: `AGENTS.md`, `app/README.md`, `API_ROUTES.md`, `APP_MIGRATION_PLAN.md`, `TESTPROTOCOL.md`, frontend-HTML, frontend-JS, backend-routers, datamodeller, lagerverktygskatalog och produktivitetsservice. Karpathy-gisten anvandes som strukturmonster for persistent wiki, index och logg.

## [2026-05-21] expand | Anvandarhandbok, handelser och felkoder

Lade till `user-guide.md`, `user-events.md` och `error-reference.md` med mer detaljer om hur programmet anvands, vad anvandaren kan se i olika lagen, vanliga toastar/confirm-dialoger, HTTP-statuskoder och backendens viktigaste felmeddelanden. Uppdaterade `index.md` och `troubleshooting-chat.md` sa framtida LLM-chat hittar materialet.

## [2026-05-21] feature | Apphjalp och MiniMax-chatt

Dokumenterade den nya pratbubbelknappen under omradesfokus/infinity, sessionssparad dialog, 10-fragorsgrans, `Rensa dialog`, MiniMax-konfiguration och nya API-vagar i `app-chat.md`. Uppdaterade index, UI-karta, API-karta, anvandarhandelser, felreferens och felsokningssidan sa framtida LLM-chat kan forklara hur apphjalpen fungerar och varfor den kan stoppa.

## [2026-05-21] polish | Chattformat i smal panel

Uppdaterade apphjalpens prompt och frontendrendering sa svaren passar den lilla dialogrutan battre. Modellen instrueras att undvika markdown-tabeller och skriva korta block/listor; frontend renderar enklare Markdown som rubriker, fetstil, kod, listor och tabeller snyggare om det anda kommer.

## [2026-05-21] polish | Chattikon och laddning

Justerade apphjalpens pratbubbel-SVG sa den inte klipps i sidebarens 40px-knapp och lade till en rund spinner i chattflodet medan API-svar hamtas.

## [2026-05-21] policy | Hardare chattsanning och repo-sok

Skarpte apphjalpens prompt: wikin ar normalfragornas grans, sa om wikin inte sager att en funktion finns ska chatten svara nej/inte dokumenterat i stallet for att spekulera. Lade till repo-sok-kontext nar anvandaren invander eller ber chatten kolla koden, samt instruktion om korrekt svenska med `å`, `ä` och `ö`.

## [2026-05-21] fix | Tydligare SQLite-lås vid lokal start

Uppdaterade lokal databasforberedelse sa `PermissionError` vid ersattning av `app/flow_local.db` blir ett tydligt meddelande om gammal `start_local.bat`/`uvicorn` i stallet for en lang Python-traceback. Dokumenterade handelsen i `user-events.md`.

## [2026-05-21] polish | Behorighetsrad och chattraknare

Fortydligade att `Vybehorigheter`, rollandringar och Super User-kontroller kraver admin-/Super User-atkomst och inte ska beskrivas som sjalvservice for vanliga anvandare. Dokumenterade ocksa att apphjalpens `x/10`-raknare visar anvanda fragor i hela aktuell server-/browser-session, inte bara fragorna som syns i panelen.

## [2026-05-21] fix | Rensa apphjalp vid logout

Frontend rensar nu apphjalpens lokala `sessionStorage` vid logout, inklusive dialog, utkast, oppet lage och lokal frageraknare. Detta matchar backendens `request.session.clear()` sa ny inloggning inte visar gammal lokal `6/10`-raknare. Lokal chattdata har ocksa en versionsnyckel sa gammal sessiondata fran tidigare implementation rensas automatiskt vid nasta sidladdning.

## [2026-05-21] feature | Anvandarkontext i apphjalpen

Apphjalpens backend skickar nu begransad supportkontext om inloggad anvandare till MiniMax: visningsnamn, anvandarnamn, roller, Super User-status, omrade och effektiva vybehorigheter per vy. Syftet ar att chatten ska kunna saga exakt om anvandaren saknar `Harleda`, bara har `view` eller saknar `Bearbeta`. Känslig information som losenord, hashes, sessioncookies, tokens och API-nycklar skickas inte.

## [2026-05-21] feature | Hamta data via extern datakalla och MiniMax

Lade till `Hamta data` som skyddad vy och API-flode for promptstyrd extern dataexport. MiniMax far bara vy-/kolumnkatalog och planformat; URL, endpointmall, headernamn, API-nycklar och klientnycklar ligger i servermiljon. Dokumenterade `data-fetch.md`, nya API-vagar, vybehorigheten `dataFetch`, katalogbyggnad och Excel-export.

## [2026-05-21] hardening | Gommer privata dataflodets leverantorsdetaljer

Bytte Hämta data-flodet till generiska `DATA_SOURCE_*`-miljovariabler, neutral API-route `/api/query-data`, generisk klient `external_data_client.py` och katalogfil `data/external_data_catalog.json`. Endpointmall och headernamn ligger nu i env i stallet for kod/wiki, och dokumentationen beskriver bara extern datakalla.

## [2026-05-21] fix | Spärrar Hämta data utan konfiguration

Hämta data-health returnerar nu status utan att kasta 503 nar katalog/env saknas. Frontend spärrar `Tolka med MiniMax` och `Hämta data` tills katalog, MiniMax och extern API-konfiguration finns, sa saknad katalog inte kan skapa AI-usage eller en missvisande arbetsyta.

## [2026-05-21] config | Publicerar Hämta data-katalogen

Katalogen `data/external_data_catalog.json` bedomdes inte vara hemlig och ska commitas sa Render har vy-/kolumnstruktur direkt. API-nycklar, URL:er, headernamn och endpointmallar stannar fortsatt i `.env`/Render secrets.

## [2026-05-21] support | Stoppa lokal server

Lade till `stop_local.bat` for att stanga gamla lokala `start_local.bat`/uvicorn-processer och frigora port `8000` nar `app/flow_local.db` ar last. Uppdaterade README och anvandarhandelser med kommandot.

## [2026-05-21] polish | Enter skickar apphjalp

Apphjalpens textfalt skickar nu fragan med Enter. `Shift+Enter` finns kvar for ny rad, och frontend ignorerar extra submit medan ett svar redan hamtas.

## [2026-05-22] fix | Stabilare Hamta data-API

Hämta data-klienten kan nu styras med `DATA_SOURCE_VERIFY_SSL` och `DATA_SOURCE_CA_BUNDLE` for lokala certifikatkedjor. Dokumenterade att bas-URL och sökvägsmall hålls separata, och lade till appklocka/periodhints så månad + år, dagens datum och senaste N dagarna styrs mot datumfält i stället for ordernummer eller hallucinerade datum.

## [2026-05-22] feature | Redigerbara Hamta data-kolumner

Planpanelen i Hämta data låter nu användaren markera MiniMax-valda kolumner för borttagning och trycka `Uppdatera plan`. Planens `output_columns` skrivs om lokalt, gammalt resultat rensas och nästa hämtning/export använder bara kvarvarande kolumner.

## [2026-05-22] polish | Tar bort Las om katalog

Tog bort den manuella `Läs om katalog`-knappen från Hämta data. Katalogen förväntas alltid finnas uppladdad i servermiljön och läses automatiskt av backend.

## [2026-05-22] polish | Tydligare Hamta data-flode

Bytte knapptexten från `Tolka med MiniMax` till `Tolka`. Hämta data och Excel-export räknar nu knappstatus från samma frontend-state: hämta kräver en godkänd tolkning, export kräver ett hämtat resultat, och ändrad prompt rensar gammal plan/resultat.

## [2026-05-22] fix | Visar allokerade pallar i Bearbeta

Allokeringsflodets huvudresultat visas nu som `Allokerade pallar` i Bearbeta och kan oppnas i Excel eller laddas ner som CSV. Frontenden filtrerar inte langre bort resultattabellen `result` for Allokering.

## [2026-05-22] fix | Hardar Oppna i Excel

Lagerverktygens `Oppna i Excel` anvander nu flows egen Excel-skrivare med sakra blad- och filnamn, i stallet for den gamla allokeringsmotorns tysta OS-oppnare. Om Windows/Excel inte kan oppna filen kommer felet tillbaka som toast, och lyckad start visar `Excel oppnas`.

## [2026-05-22] fix | Normaliserar lagerverktygens CSV-export

CSV-exporten for lagerverktygsresultat skriver nu celler via samma visningsnormalisering som previewn: heltalslika floats blir `1` i stallet for `1.0`, och NaN/None blir tomma celler. Det gor jamforelser mot Excel-exporten fran allokeringsprogrammet stabilare.

## [2026-05-22] change | Tar bort Harleda

Harleda-vyn och Eftersok-flodet ar borttagna fran aktiv webb/desktop-yta, sidebar, vybehorigheter, Apphjalpens kontext, lagerverktygens flodeskatalog och tester. Lagerroller har nu sjalvservice via Uppladdningar och Dela; Bearbeta ar fortsatt Super User-/processvyn.

## [2026-05-22] feature | CLI for Bearbeta och Dela

Lade till `warehouse_tools.cli` for lokal korning av alla lagerfloden utan server, browser, IndexedDB eller cookies. CLI:t har flodeslista, schema, filidentifiering, generisk `run`, scenariofiler, scenario-validering och egna subcommands per flode, inklusive `allocate` och `split-values`. Filinputs kan anges explicit eller matchas automatiskt med samma filtypdetektor som UI:t.

## [2026-05-22] feature | API-CLI for lagerverktyg och parityjamforelse

`tools.flow_cli` har nu `allocation`-subcommands for `/api/allokering`: `flows`, `pool`, `detect`, `run`, `observations-update`, `download`, `column` och `open-excel`. `allocation run` kan ladda ner fulla resultat-CSV:er fran sessionssvaret. Lade ocksa till `tools.compare_warehouse_results` for Flow-vs-Allokera-jamforelser av CSV/XLSX med normalisering av exportbrus som `1.0` mot `1` och NaN mot tomt.

## [2026-05-22] polish | Kopiera fritextrapport i lagerresultat

Fritextrutor i lagerverktygens resultat, till exempel Vecka 27-rapporten, har nu en kopieringsikon uppe till hoger. Knappen kopierar hela rutans text till urklipp och visar toasten `Text kopierad`.

## [2026-05-22] feature | Direktimport for flera registerrader

Personer, Aktiviteter och Anvandare har nu knapparna `Flera nya personer`, `Flera nya aktiviteter` och `Flera nya anvandare`. Varje knapp oppnar en tabellmodal som skickar samma falt som Excelmallarna till nya `/import-rows`-endpoints och ateranvander importernas validering, auditlogg och resultatmodal. Excelimporten finns kvar.

## [2026-05-22] polish | Enter aktiverar dialogers primarknapp

Alla frontendmodaler far nu gemensamt Enter-beteende via `common.js`: Enter i ett vanligt modalfalt klickar primarknappen, till exempel `Spara`, `Skapa` eller `Stang`. Flerradiga textfalt, checkboxar och knappar med eget fokus undantas.

## [2026-05-22] rename | Byter flow-vyn till Bemanning

Den anvandarsynliga planeringsvyn heter nu `Bemanning` i sidebar, sidtitel, vybehorigheter, Apphjalpens vyetiketter och wiki. Tekniskt view-id och API ligger kvar som `schedule` och `/api/schedule`.

## [2026-05-22] change | Omradesfokus ersatter omradesrullistor

Omradestogglen i sidebar styr nu Bemanning, Oversikt, Produktivitet, Aktiviteter och Anvandare. `∞` betyder alla omraden. De separata omrades-/blockrullistorna i Bemanning, Oversikt, Produktivitet och Bemanningskalkylen ar borttagna; omradesfalt som satter data i modaler och import finns kvar.

## [2026-05-22] fix | Visar Avvikelsetyp i orderkontroll

Bearbeta-resultat visar nu kolumnnamn i tabellhuvudet med en kopieringsikon bredvid. Orderoversiktkontroll har regressionstest som sakrar att `Avvikelsetyp` finns kvar i Flow/API-resultat och exportkontraktet for `Orderkontroll`, samma som i Allokera.

## [2026-05-22] fix | Matchar Allokera for pallplatser

Flow raknar nu pallplatser som Allokera: zon `F` blir separat `HIB`-kolumn med 20 rader per toppall, medan `autostore` bara raknar zon `R`. Detta gor `Topp Pallar`, `Totalt Pallar` och `Pallplatser` lika i Flow och Allokera for samma allokeringsunderlag.

## [2026-05-22] feature | Ordersaldo kopierar och visar helpall

Ordersaldo kopierar nu `Kompletta ordrar` automatiskt nar flodet ar klart. `Underskott` far kolumnen `Antal pa Helpall` fran `artikel_max.csv`, med karnfilen som fallback om anvandaren inte laddar upp en egen.

## [2026-05-22] perf | Cachar Bearbeta-filer i Flow

Bearbeta i Flow sparar nu uppladdade filer med innehallshash, utan originalfilnamn, och ateranvander samma serverfil nar samma underlag skickas igen. Cachen rensas opportunistiskt med tidsgrans och maxantal filer sa verksamhetsisolerad drift inte far langlivade uppladdningar. `warehouse_tools.flows` har dessutom en LRU-cache for inlasta tabeller baserad pa sokvag, storlek och modifieringstid, sa upprepade floden mot samma filer slipper lasa om stora CSV:er.

Bearbeta-resultatsessioner binds samtidigt till anvandaren som korde flodet. `Oppna i Excel`, `Ladda ner CSV` och kolumnkopiering svarar som saknat resultat om en annan anvandare forsoker anvanda session-id:t.

Cacheindexet ar scopeat per anvandare, uppladdningsslot och filnamn. Om samma anvandare laddar upp samma slot/filnamn med nytt innehall tas den tidigare cachefilen bort direkt; om filens path redan saknas skrivs den om fran den nya uppladdningen.

## [2026-05-22] feature | Verksamheter som isoleringsniva

Lade till Verksamheter som ny niva ovanfor omrade. Stigamo ar bakatkompatibel standard, R3 seedas separat med eget R3-omrade och egna franvaroaktiviteter, och icke-Super Users scopeas till sin egen verksamhet i register, schema, oversikt, settings och toggles. Super User far nya vyn Verksamheter och kan anvanda `∞` globalt.

## [2026-05-22] test | Stor verksamhetskontroll

Utökade verksamhetstestningen med många användare i Stigamo/R3, korsverksamhetsförsök, Super User-create, dubbletter per verksamhet, settingsisolering, public API-defaults och frontendkontrakt för dynamisk toggle och verksamhetsfält. Lade till en egen wikisida för Verksamheter och uppdaterade testprotokollet med obligatoriska regressionskommandon för webb och desktop-proxy.

## [2026-05-22] fix | Lokal verksamhetsbootstrap och tecken

Fixade lokal SQLite-bootstrap så äldre `app/flow_local.db` med globala unika områdes-/aktivitetskoder migreras till verksamhetsscope utan att radera lokal data. Tog också bort felkodade tecken i användarsynliga frontend/backend-strängar i Bemanning/Översikt efter verksamhetsändringen.

## [2026-05-22] fix | Personer följer R3-fokus

Fixade Personer-vyn så Super User inte längre ser global personlista när områdestogglen står på R3. Vyn skickar nu valt `area_id` till `/api/persons`, filtrerar även klient-side och laddar om listan när områdesfokus ändras.

## [2026-05-25] change | GG/MG-filter i Bearbeta

Bearbeta skickar nu aktuell omradestoggle till `/api/allokering/flow/*`. Backend filtrerar tabellfiler per korning for GG (`Bolag=GG`, exkl. kundnr `6005`) och MG (`Bolag=MG`, exkl. kundnr `40002` och `90002`) nar filen har Bolag-/Kundnr-kolumner. Ovriga toggles ser hela underlaget. Frontenden har en processmatris for framtida flodessynlighet per toggle.

## [2026-05-25] polish | Markerar krav i Flera nya-dialoger

Direktimporttabellerna for Personer, Aktiviteter och Anvandare visar nu `Obligatoriskt` eller `Frivilligt` i varje kolumnrubrik. Den gemensamma bulkimportkomponenten markerar omarkta kolumner som frivilliga som fallback, sa framtida `Flera nya ...`-dialoger inte blir utan faltstatus.

## [2026-05-25] fix | Rensa alla bevarar karnfiler

`Rensa alla` i Uppladdningar tar nu bara bort vanliga lokala filval. Skyddade karnposter som `artikel_max.csv`, coredata-nycklar och KPI-mal bevaras i IndexedDB/serverstatus, och anvandartexten sager att karnfiler ligger kvar.

## [2026-05-25] polish | Synlig dokumentlogg for fler floden

Dokumentloggen i sidebaren sparas nu i browsersessionen, foljer med mellan vyer och kan rensas. `api.js` loggar anvandarnara success/failure for mutationer och nedladdningar, bakgrundsladdning varnar vid misslyckad forvarmning och Bearbeta-floden med egen fetch-wrapper skriver tydligare lyckat-/felstatus. Agents/wiki/testprotokoll har uppdaterats sa nya funktioner maste ta med synlig loggning, audit och teststod.

## [2026-05-26] polish | Vectorikoner for webb och desktop

Webben anvander nu SVG for favicon och brandlogga, med PNG/ICO kvar som fallback for plattformar som kraver raster. Desktop-fonstret foredrar `flow_icon.svg`, medan `.ico` fortfarande finns kvar for exe-/genvagsikon och fallback i Windows-bygget.

## [2026-05-26] fix | Ogiltigt omradesfokus faller tillbaka

Bemanning och Oversikt friskar nu upp den gemensamma omradestogglen fran sidans egna `/api/areas`-svar och validerar sparade `AREA:<id>` mot aktuella aktiva omraden. Om ett omrade raderats medan en browserflik hade det valt faller fokus tillbaka till Alla i stallet for att skicka dod `area_id` och visa 404/tom vy.

## [2026-05-31] polish | Hogerklicksmeny for omradesfokus

Sidebarens omradestoggle har nu en hogerklicksmeny for direkt val av omrade. Menyn anvander samma `/api/areas`-scope som ovriga vyer: vanliga anvandare ser omraden i egen verksamhet, medan Super User ser alla aktiva omraden och globalt `∞`.

## [2026-05-31] feature | Publik meta-uppladdning

Lade till `/meta` och `meta-upload.html` som en fristaende publik mobilvy utan sidebar och utan inloggning. Anvandaren kan valja flera bilder/videor pa Android, iPhone eller desktop och ladda upp dem till `POST /api/meta/uploads`; backend sparar varje fil i `meta_media_uploads` med gemensamt batch-id och status `pending_analysis` for senare LLM-analys.

## [2026-05-31] feature | Meta-progress och Super User-vy

Meta-uppladdningen visar nu total progress, kvarvarande mangd och status per fil under pagaende uppladdning. Backend sparar nya meta-filer med tidsstamplat `stored_filename`, och Super User far sidebarvyn `Meta` dar alla uppladdade bilder/videor kan listas, filtreras och visas via skyddade `/api/meta/uploads`-endpoints.

## [2026-05-31] feature | Stoppa dubbletter i Meta

Meta-uppladdningen beraknar nu SHA-256 `content_hash` for varje bild/video och sparar inte exakta dubbletter igen. Migrationen fyller hash for befintliga meta-rader och tar bort duplicate blobbar innan ett unikt index skapas; uppladdningssvaret visar `skipped_count` sa anvandaren ser hur manga dubbletter som hoppades over.

## [2026-05-31] feature | Meta-nedladdning och radering

Super User-vyn `Meta` visar nu knappen `Ladda ner` i stallet for `Oppna` och har en ny `Radera`-knapp per mediafil. Radering gar via `DELETE /api/meta/uploads/{upload_id}`, tar bort raden/blobben och audit-loggar metadata utan filinnehall.

## [2026-05-31] feature | Gemini-analys for Meta-videor

Meta skapar nu sändningsrader for uppladdade videor i `meta_shipment_observations` med video-hash, radhash, ordernummer, användarnamn, kund, pall-id, avvikelser, videolank och eventuell etikettstillbild. Backend kan använda `GEMINI_API_KEY` och standardmodellen `gemini-2.5-pro` for att analysera både video och ljud; osäkra svar hamnar i manuell kontroll i Meta-vyn.

## [2026-05-31] feature | Meta Video-ID och videolangd

Meta-vyn visar nu samma korta Video-ID i sändningstabellen och i videokorten, plus videons langd i tabellen, korten och den publika filväljaren nar metadata kan lasas. Backend sparar `duration_seconds` for nya videos nar `ffprobe` finns, och frontenden kan fylla i langden via browserns videometadata for befintliga uppladdningar. Media-korten har kompakta ikonknappar sa Visa, Ladda ner och Radera far plats pa samma rad.

## [2026-06-01] feature | Automatisk Meta-uppladdning

Den publika Meta-uppladdningen startar nu direkt nar anvandaren valt eller dragit in filer. Den separata `Ladda upp`-knappen ar borttagen, medan progress, kvarvarande mangd, per-filstatus, dubblettbesked och felmeddelanden fortsatter visas pa samma sida.

## [2026-06-01] change | NoMan kravs for nya personer

Personregistret kraver nu `NoMan` nar en ny person skapas via modal, direktimport eller Excelimport. Personvyn visar toasten `NoMan kravs` vid tomt falt, importresultat visar radfelet `NoMan saknas`, och backend stoppar nya personer utan NoMan samt rensning av ett redan satt NoMan-varde.

## [2026-06-01] polish | Verksamhet i Personer

Personregistret visar nu kolumnen `Verksamhet` mellan NoMan och Hemomrade. Kolumnen kan sorteras och filtreras, anvander personens `business_id` mot verksamhetslistan eller aktuell anvandares verksamhet, och visar `Utan verksamhet` for gamla rader som saknar verksamhet.

## [2026-06-01] feature | Per-verksamhet infinity och inline Verksamheter

Verksamheters `∞`-lage styrs nu av ett aktivt omrade med kod `ANNAT` i respektive verksamhet, i stallet for en hardkodad Stigamo-regel. Verksamheter-vyn har fatt `Lagg till ∞`, klickbara celler for kod/namn/sortering/aktiv-status och rubriksortering for bade verksamheter och omraden.

## [2026-06-01] feature | Meta sändningsnummer från etiketter

Meta-analysen har fått `shipment_number`/sändningsnummer i `meta_shipment_observations`, API-svaret och Super User-tabellen. Gemini-prompten beskriver nu både transportetikett och innehållsförteckning: `Sändnings-ID` på transportetiketten blir sändningsnummer, `Avs. ref.` kan bli ordernummer, `Godsmärks`/`Box ID` kan bli pall-id och innehållsförteckningens ordernummerlista kan användas när den är tydligare. `record_hash` räknas om med sändningsnummer så tabellraden fortsatt kopplas till rätt video och etikettdata.

## [2026-06-01] fix | Scrollbar omradestoggle

Sidebarens omradesmeny kan nu scrollas utan att stangas. `common.js` ignorerar scroll-event som kommer fran sjalva `.area-focus-menu`, stoppar klick/scroll inne i menyn fran att trigga dokumentets utanfor-klick och behaller stangning vid sidscroll, resize, Escape eller klick utanfor.

## [2026-06-01] feature | Appzoom i sidebar

Sidebaren har fatt en global zoomkontroll mellan hamburgaren och menyredigering. Kontrollen visas nu som tva forstoringsglas med minus/plus utan siffra i mitten. Zoomnivan sparas lokalt i `flow-app-zoom`, styr hela appytan i bade webb och Windows-app och kan aven andras med `Ctrl+-`, `Ctrl++`, `Ctrl+0` och `Ctrl+scroll`. Alla skyddade HTML-sidor har ny cache-bust for `common.js`.

## [2026-06-01] polish | Loggikon visar nya loggrader

Dokument-/loggikonen i sidebaren visar nu en badge med antal nya loggrader i aktuell session, på samma sätt som uppladdningsikonen visar antal uppladdningar. Räknaren sparas i `sessionStorage`, följer med vid sidbyte och nollas när användaren öppnar eller rensar loggpanelen.

## [2026-06-01] fix | Rensa alla stoppar gammal produktivitetssynk

Uppladdningars `Rensa alla` markerar nu en ny rensningsgeneration. Produktivitetens bakgrundssynk skickar med den generationen när loggfiler speglas till Uppladdningar, och en gammal synk som startade före rensningen får inte skriva tillbaka exempelvis `Palllastningslogg` efter att användaren rensat filerna.

## [2026-06-01] fix | Forecast undviker sklearn get_params-fel

Forecastens paketerade LightGBM-/XGBoost-artefakt predikterar nu via underliggande boosterobjekt i stallet for sklearn-wrapperns `predict`. Det gor att Bearbeta/Forecast inte faller pa miljoer dar wrapperns `get_params` ger felet `'super' object has no attribute 'get_params'`.

## [2026-06-01] feature | Forecast visar Ytgenerering som nasta steg

Forecast-resultatet i Bearbeta visar nu en foljdknapp `Kor Ytgenerering` direkt i resultatpanelen. Knappen anvander samma readiness-regler som den vanliga Ytgenerering-knappen, skickar vidare `forecast_session_id` och gor kedjan Forecast -> Ytgenerering tydligare utan att anvandaren maste leta i flodeskartan.

## [2026-06-01] feature | MG begransar Ytgenerering till UTL205-UTL652

Ytgenereringens Bearbeta-korning far nu vald omradestoggle vidare till flodeshandlern. Nar togglen ar MG filtreras lagerplatsunderlaget efter den vanliga Typ U/Max pall-regeln och darefter till UTL205-UTL652, medan andra toggles fortsatt kan anvanda UTL1-UTL652.

## [2026-06-01] feature | Bearbeta-matris styr UTL for Ytgenerering

Bearbeta-matrisen har nu ett globalt `Ytgenerering UTL`-intervall per toggle. Intervallet sparas i `allocation_process_matrix`, visas som `Fran`/`Till` i matrisdialogen och skickas till Ytgenerering vid korning sa varje toggle kan styra vilka UTL-ytor som raknas. Standard ar MG UTL205-UTL652 och ovriga toggles UTL1-UTL652.

## [2026-06-01] feature | Ytgenerering visar interaktiv ytkarta

Ytgenerering-resultatet skickar nu med en kartpayload byggd fran Flow-placeringarna och sparade Flow-koordinater. Bearbeta visar kartan som ett stort resultatblock med pan/zoom/rotation/fullskarm, drag for att flytta eller byta UTL-placeringar, kapacitetsvarningar samt lokala nedladdningar for justerad karta-CSV och justerad ASK-import.

## [2026-06-01] feature | Coredata sparas i Postgres

Nya coredata-karnfiler sparas nu i Postgres-tabellen `coredata_files` med unik rad per verksamhet och filtyp. Backend later DB-raden vinna over gamla filer, men kan fortfarande lasa `data/coredata/` som fallback tills en filtyp laddats upp igen. Bearbeta och Produktivitet materialiserar DB-raden till en temporar backendfil nar berakningsmotorerna behover en CSV-sokvag, sa webb och Windows-app delar samma centrala sanning.

## [2026-06-01] feature | Nya karnfilstyper for dispatch och transportor

Uppladdningar kanner nu igen `dispatch_template-*.csv` som karnfilstypen `dispatch_template` och `trans_agency-*.csv` som karnfilstypen `trans_agency`. Bada visas bland permanenta karnfiler, skyddas vid `Rensa alla` och sparas i Postgres per verksamhet pa samma satt som ovrig coredata.

## [2026-06-01] fix | Publika Meta-fel syns i Felkoder

Publika Meta-uppladdningar loggar nu misslyckade backend-forsok som `meta_media_upload/upload_failed`, aven utan inloggad anvandare. Auditpayloaden ar sanerad till metod, path, HTTP-status, feltyp, antal valda/accepterade/overhoppade filer och total uppladdad storlek, utan filnamn eller filinnehall. Den publika XHR-klienten visar dessutom backendens feltext nar den finns i svaret.

## [2026-06-01] fix | Meta laddar upp manga filer stegvis

Den publika Meta-uppladdningen later anvandaren valja manga bilder/videor pa en gang men skickar dem nu en och en till `/api/meta/uploads`. Total progress och per-filstatus finns kvar, dubbletter summeras fortsatt, videolangd lases sekventiellt, och om en fil misslyckas markeras den som `Fel` medan klienten fortsatter med nasta fil.

## [2026-06-01] feature | Transportorskluster styr Ytgenerering

Forecast laser nu verksamhetens `trans_agency`-karnfil som transportorskluster och skickar klustren som `carrier_clusters` i Forecast-sessionen. Forecast-resultatet visar `Redigera kluster`, dar anvandaren kan andra kluster, UTL-fran/till och ordning innan `Kor Ytgenerering`. Ytgenerering tar emot den redigerade `carrier_clusters_json`, grupperar transportorer med samma `cluster_group` och placerar sandningar inom respektive klusters UTL-intervall innan kartan visas.

## [2026-06-01] fix | Forecast ignorerar orderstatus 11

Forecast filtrerar nu orderoversikten sa hela ordernumret ignoreras om nagon orderhuvudrad for samma `Ordernr` har `Status=11`, oavsett om en annan rad/snapshot har annan status. Det gor att matchande rader i Detalj Kundorder ocksa faller bort nar Forecast inner-joinar orderdetaljer mot orderoversikten, sa stoppade/avvikande status-11-ordrar inte skapar sandningar eller pallplatsprognos.

## [2026-06-01] feature | Kortkommandon i Ytgenerering-kartan

Ytgenerering-kartan i Bearbeta kan nu fa fokus och hanterar `Ctrl+C`, `Ctrl+X`, `Ctrl+V` och `Ctrl+Z` for att kopiera/klippa vald placering, klistra in den pa vald UTL-yta och angra senaste kartandringen. Kortkommandona anvander samma flytt-/byteslogik som drag i kartan och visar toastar nar anvandaren kopierar, klipper, klistrar in eller angrar.

## [2026-06-01] fix | Klusterknapp visas utan trans_agency-rader

Forecast-resultatet bygger nu en redigerbar klusterlista fran Forecast-tabellens unika transportorer nar `carrier_clusters` saknas i svaret. Det gor att `Redigera kluster` visas aven om transportorsfilen inte gav klusterrader, och sparade andringar skickas fortsatt som `carrier_clusters_json` till Ytgenerering.

## [2026-06-01] fix | Svenska tecken i Ytgenerering-kartan

Ytgenerering-kartans knappar, sökfält, detaljrad, översikt, toastar och justerade karta-CSV använder nu svenska tecken i texter som `Återställ vy`, `Fullskärm`, `Sök UTL, sändning eller transportör`, `Över kapacitet`, `Sändningsnr` och `Transportör`.

## [2026-06-01] fix | Kärnfiler blir serverns sanning

Kärnfiluppladdningar känner nu igen `location-...`, `lagerplats-...` och `lagerplatser-...` som samma `location`-underlag. När en ny kärnfil sparas i databasen tas äldre lokala fallbackfiler för samma verksamhet och filtyp bort, och Uppladdningar läser kärnfilstatus från servern utan GET-cache så gamla lokala filer inte kan se ut som sanning.

## [2026-06-01] fix | Bemanning visar lånade personer per aktivitetsområde

Bemanningens områdesfilter visar nu en person i valt område om personen antingen har hemområdet där eller har en schemacell samma dag med en aktivitet som tillhör området. Summeringen räknar lånade personer på de explicita cellerna i valt område utan att dra med personens hemområdesmall till fel områdessummering.

## [2026-06-01] feature | Ytgenerering: kundnamn, klusterfärger och saknade kunder

Ytgenerering-kartan visar nu kundnamn (största kunden per sändning) som huvudtext på ytorna med en vit kontrast-halo för bättre läsbarhet. Forecast-tabellen får en `Kundnamn`-kolumn och kartans payload bär `customer`/`customerNum` per placering och i listan över ej placerade sändningar. Färgen baseras på transportör men ett kluster delar basnyans och varje transportör i klustret får en egen ljushet (`allocationClusterColorMap`). Kluster-editorn (`Redigera kluster`) har drag-sortering, ASN/Arrive/Depart, Group, Start/End seq och färgväljare; tiderna seedas med standardvärden och sparas i `carrier_clusters`. En `Saknade kunder`-panel listar ej placerade sändningar.

## [2026-06-01] feature | Uppladdningar kan forhandsvisa filer

Denna historiska andring lade till `Visa` for filrader. Funktionen ersattes 2026-06-04 av explicita download/open-atgarder, sa dagens Uppladdningar forhandsvisar inte langre filinnehall.

## [2026-06-01] feature | Installningar for Ytgenereringens ytkarta

Bearbeta har nu knappen `Installningar` for roller med `allocationProcessMatrix=view`, med sparande for `allocationProcessMatrix=edit`. Dialogen visar Ytgenereringens UTL-karta som en redigerbar SVG: anvandaren kan dra ytor, andra koordinater/storlek/max pall och lagga till en hel UTL-serie som autoplaceras fran vald yta. Sparade ytor lagras globalt som `ytgenerering_map_layout`, anvands av Ytgenerering for koordinater och kapacitet, och kan komplettera saknade `Typ=U`-platser inom UTL1-UTL652. Om ingen ytkarta ar sparad anvands standardkoordinaterna bara for visualisering.

## [2026-06-01] polish | Fullskarm ar kartikon

Ytgenereringens fullskarmskontroll ar flyttad fran verktygsradens textknapp till en liten ikon i kartans ovre hogra horn. Export- och vyknapparna ligger kvar ovanfor kartan.

## [2026-06-01] fix | Sidolista kopierar sandningsnummer

Ytgenerering-kartans sidolista kopierar nu radens sandningsnummer till urklipp nar anvandaren klickar pa raden, aven nar listan visar kundnamn eller transportor i stallet for sifferstrangen.

## [2026-06-01] fix | AllocationSettings ar separat behorighet

`allocationSettings` raknas inte langre som generell lagerverktygsatkomst. Vanlig admin kan fortsatt ha settings-/matrisbehorighet via vyregler, men `require_allocation_tools_user` kraver fortfarande Lagerkontorist, Artikelplacerare eller Super User for de vanliga lagerverktygen.

## [2026-06-02] feature | Personliga schema- och produktivitetsvyer

Flow har nu rollen `person`, vyerna `Mitt schema` och `Min produktivitet` samt `/api/personal/...`-endpoints. En person kan logga in med sitt `noman`-namn; om anvandaren saknas skapas kontot automatiskt med `person_id`, verksamhet och hemomrade fran personregistret och skickas till forsta losenord. Personrollen ser bara sin egen vy, medan Super User kan valja person i rullista.

## [2026-06-04] feature | Meta-analys anvander bara rost

Meta-videoanalysen extraherar nu en temporar ljudfil fran videon och skickar bara rosten till Gemini. Analysen fyller ett tydligast hort pall-id och avvikelser, medan ordernummer, sandningsnummer, anvandarnamn och kund lamnas tomma tills de kan hamtas via pall-id fran uppladdad data. Autoanalys ar fortsatt ko-ad med en video i taget, delay/spacing-settings och best-effort stillbild fran video.

## [2026-06-04] fix | Meta-video laddas ner som video

Meta-uppladdningar normaliserar nu videoandelse + ljud-MIME, till exempel `.mp4` med `audio/mp4`, till video-MIME vid sparande. Content-endpointen normaliserar ocksa befintliga rader vid streaming, sa live-rader som sparats med fel MIME laddas ner och spelas som video.

## [2026-06-04] fix | Meta-videopil laddar spelbar MP4

Videopilen i Meta-analystabellen anvander nu `variant=playable` pa content-endpointen. Backend transkodar da temporart originalvideon till H.264/AAC-MP4 och raderar tempfilen efter svaret, sa filmer fran Meta-glasogon som annars bara ger ljudikon i Windows Media Player kan ses utan att originalfilen skrivs over.

## [2026-06-04] feature | Meta-uppladdning koar obegransat klientval

Meta-uppladdningssidan later anvandaren valja hela filkon pa en gang och visar total progress med aktuell fil, filnummer, kvarvarande mangd och ETA. Klienten skickar fortsatt en fil per request och backend streamar varje fil i chunks till MediaStore, sa langa koer inte kraver att hela batchen ligger i RAM. Standard-rate-limit for Meta-uppladdning ar avstangd for att sekventiella koer inte ska stoppas efter ett visst antal filer per minut.

## [2026-06-04] feature | Historik far interaction-tracking

Historik har nu ett separat `user_interaction_events`-lager bredvid audit och vantetider. Webben batchar klick, submit, change/contextmenu, API-resultat, nedladdningar och semantiska Bearbeta-events via `flowTrack`; desktop markerar `client_surface=desktop` och trackar appstart, lokala filval och update-floden. Historik har nya lagen Funktioner, Knappar, Kolumner, Floden och AI-analys med endpoints for raw events, summary, coverage och MiniMax-fragor. Backend sanerar payloaden och `TRACKING_ALLOW_VALUE_SAMPLES=false` strippar klartextprover som default; secrets, filnamn, filvagar, privata URL:er, request bodies och provider-detaljer far aldrig sparas.

## [2026-06-04] test | Interaction-tracking far browserkontrakt

Trackinglagret har nu Playwright-tester for auto-capture av klick/change/submit, API-koppling, nedladdning/export, Historik-dashboardens Funktioner/Knappar/Kolumner/Floden, Historik-AI och desktop-surface. Tester fangade och skyddar att interna download-lankar ignoreras av auto-tracking, att Pafyllnadsprio copy-patterns anvander `copy_mode`, och att kanda kontroll-id:n i coverage matchar frontendens faktiska id:n.

## [2026-06-08] polish | Meta-tabellen visar uppdaterad timestamp

Sändningsanalysen i Meta-vyn visar nu kolumnen `Uppdaterad`, baserad på `meta_shipment_observations.updated_at` med `created_at` som fallback. Hover-title visar både skapad och uppdaterad tid, så Super User kan skilja historiska etikettanalyser från nya audio-only-rader där bara pall-id och avvikelser ska fyllas.

## [2026-06-08] feature | API-first for Bearbeta och Produktivitet

Bearbeta och Produktivitet kan nu hamta valda underlag direkt fran extern datakalla vid knapptryck, utan MiniMax och utan radbegransning. Uppladdade filer och Windows `localRef` anvands som fallback nar API eller katalog inte kan nas. Wikin dokumenterar source-mapping, `/api/workflow-data/source`, Produktivitetens `api_first`-status, sanerad source-audit och nya fallbackfel.

## [2026-06-09] polish | Produktivitetens celler visar poangstatus

Produktivitetsmatrisen fargmarkerar nu KPI-celler efter cellens poangniva, visar diff-`!` bara for KPI-forvantade perioder och later STOD/absence-celler med poang visa en hoger-klicksmeny med `process = poang`-summering. Personer som bara har STOD eller absence hela dagen filtreras bort fran Produktivitet.

## [2026-06-09] feature | Bemanning visar avslutad produktivitet

Bemanning har nu en fast kolumn `Produktivitet` efter Hemomrade. Kolumnen hamtar vald dags personrapport fran `/api/productivity`, raknar bara avslutade KPI-timmar fram till timmen fore pagaende timme for dagens datum och visar heltalsprocent med samma fargskala som Produktivitet: rod under 80, orange 80-99 och gron fran 100. Personer med bara STOD/absence hittills far tom cell.

## [2026-06-09] feature | Oversikt produktivitet visar KPI-trad

Ny vy `Oversikt produktivitet` finns pa `/oversikt-produktivitet.html`. Den laser samma `/api/productivity`-rapport, raknar dagens poang bara till och med senaste avslutade heltimme och visar ett fokuserbart trad: verksamhet -> avdelning -> aktivitet -> person -> timme/processpoang. Vyn har egen `productivityOverview`-behorighet som arver befintlig `productivity`-atkomst nar den inte ar uttryckligen satt.

## [2026-06-09] polish | Oversikt produktivitet visar p/tim

Noderna i `Oversikt produktivitet` visar nu `totalpoang / KPI-timmar = p/tim` i stallet for bara totalpoang. KPI-timmar bygger pa avslutad schemalagd work/KPI-tid, sa KPI-celler med 0 poang syns och drar ner snittet medan STOD/absence inte raknas i namnaren. Snittet fargmarkeras med samma skala som Bemanning: rod under 80, orange 80-99 och gron fran 100.

## [2026-06-09] feature | Oversikt produktivitet far periodval

`Oversikt produktivitet` har nu periodval for Dag, Vecka, Manad och Ar. Vyn hamtar `GET /api/productivity/overview`, summerar dagsrapporterna i samma hierarkitrad och visar hur manga dagar i perioden som ingar. Dagens datum raknas fortsatt bara till senaste avslutade heltimme, och servern klipper innevarande vecka/manad/ar vid dagens datum.

## [2026-06-09] feature | Oversikt produktivitet exporterar flowchart

`Oversikt produktivitet` har nu knappen `Exportera flowchart`. Den skapar en lokal SVG-export av aktuell fokuserad vy och vald period. I `Helbild` exporteras hela verksamhetstradet ner till personniva; i person-/timfokus exporteras detaljgrenen med timme och processpoang.

## [2026-06-09] polish | Oversikt produktivitet kortar snittvarde

Snittvarden i `Oversikt produktivitet` visas nu utan suffixet `p/tim` och med en decimal, till exempel `67,0`. Formeln med totalpoang och KPI-timmar visas fortsatt pa raden ovanfor och fargskalan ar oforandrad.

## [2026-06-09] polish | Oversikt produktivitet far egna farggranser

`Oversikt produktivitet` anvander nu en egen snittskala: gron fran 80 och uppat, orange 70-79,9 och rod under 70. Bemanningens produktivitetskolumn behaller sin tidigare skala.

## [2026-06-09] performance | Produktivitet periodbyte anvander cache

Produktivitetens period-/tradvy och Personer-dialogens produktivitetsmodal cachar nu nyligen hamtade perioder kort i klienten. Backend ateranvander dessutom fardigbyggda dagsrapporter kort baserat pa snapshotfilernas version. `GET /api/productivity/overview` laser befintliga snapshots for vald period och triggar inte langre extern historik-sync nar anvandaren byter dag, vecka, manad eller ar; schemalagd sync och backfill ansvarar for API-hamtning.

## [2026-06-09] feature | Bemanning far V+H-kapacitet i celler

Bemanning har nu en valfri `V+H`-visning som lagger personens historiska snitt pa aktivitetsetiketten i celler, till exempel `GG Plock(70)`. Snittet hamtas fran nya `GET /api/schedule/activity-capacity`, valjer matetal via KPI-regler/KPI-mal och anvander Bemanningens konfigurerade historikfonster pa samma KPI-process.

## [2026-06-09] change | Produktivitet ersatts av tradoversikt

`Produktivitet` pa `/produktivitet.html` anvander nu trad-/periodvyn som tidigare lag pa `Oversikt produktivitet`, men behaller Produktivitets befintliga namn, menyplats och ikon. Separat `productivityOverview`-behorighet togs bort och `/oversikt-produktivitet.html` redirectar till Produktivitet. Gammal manuell produktivitetsfiluppladdning togs bort fran frontend, API och desktop-proxy; vyn bygger pa sparade globala API-snapshots och backfill.

## [2026-06-09] change | Gammal produktivitetsadress borttagen

`/oversikt-produktivitet.html` ar borttagen i stallet for att redirecta. Produktivitet ska bara oppnas via `/produktivitet.html`, med Produktivitets befintliga namn och ikon.

## [2026-06-09] fix | Ytgenerering begransar max utzoomning

Ytgenereringens resultatkarta i Bearbeta anvander nu `Aterstall vy` som minsta tillatna zoomskala. Anvandaren kan zooma in och panorera inom kartans granser, men mushjul/trackpad kan inte zooma ut forbi fit-vyn.

## [2026-06-11] change | Bearbeta-matris flyttad till Installningar

Bearbeta-vyn visar inte langre en egen Matris-knapp. Bearbeta-matrisen ligger nu i `installningar.html` under fliken `Bearbeta`, syns med `allocationProcessMatrix=view` och sparas med `allocationProcessMatrix=edit`. `GET /api/allokering/process-matrix` kan fortfarande lasas av Bearbeta-vyn for flodessynlighet, men kan ocksa lasas av matrisfliken i Installningar.

## [2026-06-14] change | Installningar verksamhetsseparerade

Installningar skickar nu vald verksamhet fran omradesfokus till Ytkarta, Bearbeta-matris och Bemanning. `allocation_process_matrix`, `ytgenerering_map_layout`, `staffing_history_hours` och hover-aktiviteternas settings sparas/lases per verksamhet, medan Vybehorigheter fortsatt ar global rollatkomst. Frontendens bootcache scopeas sa matris/coredata inte ateranvands mellan verksamheter.

## [2026-06-14] feature | RFID-stamplingar till Bemanning

Flow har nu ett RFID-flode for ESP32/RDM6300-moduler: `POST /api/rfid/scans` tar emot fysisk stampel, Bemanning visar markeringar per person/timme och `OK` applicerar aktiviteten fran scannad minut medan `Ignorera` sparar status utan att radera markeringen. Samma person och aktivitet tva ganger i rad sparas som dubblett och kan inte appliceras. Firmwaremappen i Flow ar satt for testmodulen `MG Plock` med generiska WiFi/server/token-placeholders.

## [2026-06-14] fix | RFID far USB-brygga utan admin

RFID-felsokningen har nu ett no-admin-lage for datorer dar Windows-brandvaggen blockerar ESP32 over WiFi. `python -m tools.rfid_serial_bridge` laser ESP32 serial output via USB och postar scannen lokalt till `127.0.0.1`, sa Bemanning och Historik kan testas utan inbound firewall-regel. Parsern och POST-kontraktet har eget teststod och testprotokollet pekar ut bryggan.

## [2026-06-14] process | Audit och Historik-label blir obligatoriskt

Agentreglerna sager nu uttryckligt att nya floden som skapar, andrar, synkar eller tar emot data ska leverera sparad audit-rad och begriplig Historik/Analys-label som acceptanskriterium. Read-only-undantag maste vara dokumenterade och testade. Kontraktstestet for agentregler skyddar formuleringen.

## [2026-06-14] fix | RFID-brygga forklarar last COM-port

USB-bryggan for RFID visar nu ett begripligt fel om COM-porten ar last av Arduino Serial Monitor eller annat program. RFID-wikin och firmware-README beskriver att serialfonstret maste stangas innan bryggan startas.

## [2026-06-14] change | RFID-dubbletter droppas

RFID-scans for samma person och samma aktivitet tva ganger i rad sparas inte langre som `duplicate_ignored`. Backend uppdaterar device-senast-sedd men returnerar `registered=false` utan ny `rfid_scan_events`-rad, Bemanningsmarkering eller Historik-rad.

## [2026-06-14] observability | Workflow, Meta och Data-fetch far bredare signal

Workflow-kallor audit-loggas nu som `workflow_source/source_fetch` eller `source_fetch_failed` med sanerad payload, och publika Meta-uppladdningar loggar aven lyckade forsok som `meta_media_upload/upload_success`. Historik/Analys har labels for `workflow_source`, `meta_media_upload` och `coredata_file`. OTel har nya spans/attribut for workflow-kallor, Data-fetch plan/run/export samt Meta-export/manuell analys utan prompts, filnamn, sokvagar eller raddata. Tester skyddar auditkedjan och Historik-labels.

## [2026-06-15] feature | Produktivitet far behorighetsstyrd intakt/utgift

Produktivitet kan nu visa intakt, utgift och resultat pa varje kort i hierarkitradet nar rollen har `productivityFinance=view`. Beloppen beraknas server-side fran arbetade minuter, kostnad per timme och VAS-intakt per timme per bolag. Nya Installningar-fliken `Intakt/utgift` sparar vardena per verksamhet via `GET/PUT /api/settings/productivity-finance` och styrs av `productivityFinanceSettings`; bada nya behorigheter ar bara seedade till Super User tills de delas ut i Vybehorigheter.

## [2026-06-15] fix | Intakt/utgift anvander bolag fran Verksamheter

Intakt/utgift-fliken listar nu bara verksamhetens `company_codes`, till exempel `GG` och `MG` for Stigamo. VAS-omraden som `AS` och verksamhetskoden `STIGAMO` visas inte langre som egna intaktsrader, och backend filtrerar bort sparade VAS-intakter som inte matchar verksamhetens bolag.

## [2026-06-15] feature | Personer far Blue/White collar

Personregistret har nu faltet `collar_type` med vardena `blue_collar` och `white_collar`. Personer visar kolumnen `Arbetstyp`, kan redigera den inline eller i Ny person-modal, och direkt-/Excelimport kan fylla den via `arbetstyp` med alias som `Blue collar`, `Blue color`, `White collar` och `White color`. Befintliga och nya personer defaultar till `Blue collar`.

## [2026-06-15] feature | Aktiviteter far KPI-processval

Aktivitetsmodalen har nu en multival-rullista for KPI Mal dar anvandaren kan bocka i flera kanda KPI-processer. `GET /api/activities/kpi-process-options` hamtar processnamn fran KPI-mal, intern KPI-logik och befintliga aktiviteter; sparningen fortsatter skriva kommaseparerat `kpi_process_name` via befintliga create/update-endpoints.

## [2026-06-15] ingest | ASK datalagring (rensning och arkivering)

Lade till `vyer & kolumner/ask_rensning_och_arkivering.xml` (tidigare felnamnda `clean_clear_archive.html` i repo-roten) som kalla for ASK/WMan:s schemalagda rensnings-/arkiveringsjobb. Ny wiki-sida `ask-datalagring.md` forklarar `archive="true"` (flyttas till `log_wmanfrey`, ~800 dagar) vs `archive="false"` (raderas permanent efter `days`) och kopplar retention till flows `v_ask_*`-vyer. Viktigt fynd: `PICKLOCATION_LOG` (plockplatsbyten via `v_ask_pick_location_log`) ar `archive="false"` med 40 dagars retention och kan inte aterstallas. Korslankad fran `index.md` och `data-fetch.md`.

## [2026-06-15] gap | Hamta data dirigerar inte gammal period till arkivvy

Verifierade att `Hamta data` inte automatiskt valjer arkivvyn for perioder bortom live-vyns retention: `data_fetch_service.py` har ingen retention-/`dblog`-logik. En prompt som "plocklogg full for januari" matchar `v_ask_pick_log_full` (40 dagar) och blir tom utan varning. Katalogen har 28 `dblog_*`-arkivvyer (prefix `dblog_`, label "Arkiv ..."), en per `archive="true"`-tabell, som laser `log_wmanfrey` (~800 dagar). Dokumenterade konventionen och luckan i `ask-datalagring.md` och ett felsokningssvar i `data-fetch.md`. Foreslagen kodatgard: hint nar detekterad period ligger utanfor en live-vys retention och en `dblog_*`-motsvarighet finns.

## [2026-06-15] feature | Hamta data auto-dirigerar mellan live- och arkivvy

Implementerade auto-byte/merge i `data_fetch_service.build_retention_segments` + `LIVE_ARCHIVE_PAIRS` (14 radniva-vyer med bade live- och `dblog_`-vy). Routern (`_apply_retention`, `_fetch_rows_with_segments`) lar planens Between-datumfilter avgora: helt inom retention -> live; helt aldre -> byt till `dblog_*`; spann -> hamta bada och sla ihop (split vid cutoff, union av kolumner, saknade falt tomma). Aven omvant: arkiv-fraga med datum i aktiv period hamtar aven live. `plan.notice`/`plan.fetched_views` sätts och visas som gul notisruta i planpanelen (`data_fetch.js` + CSS). 6 nya enhetstester i `test_data_fetch_service.py` (alla 39 passerar). Utelamnade par: `customs_dispatched_log`/`item_log` finns inte i archive="true"-blocket. Uppdaterade `ask-datalagring.md` och `data-fetch.md`.

## [2026-06-15] refactor | Delad fetch_all (fonstring) for alla externa hamtningar

Flyttade "hamta alla rader, dela upp i datumfonster nar API:t kapar svaret" fran routern `data_fetch.py` ned till `ExternalDataClient` (`fetch_all` + fri funktion `fetch_all_rows`, `response_row_cap` i konstruktorn). `data_fetch._fetch_external_rows` delegerar nu dit, och `workflow_data.fetch_source_to_temp` bytte fran `fetch_data` till `fetch_all` sa Produktivitet och Bearbeta ocksa fonstrar (tidigare kapades de tyst vid radtaket, t.ex. vid helar). Inställningar-uträkningen arver via `_fetch_rows`. En enda sanning for komplett resultatmangd. Tester: behöll fonstrings-testerna + 3 nya (fetch_all_rows utan cap, med cap, samt klientmetoden); workflow-fejkklienten fick `fetch_all`. Registrerade aven WIP-routen `POST /api/settings/productivity-finance/calculation/test` i `flow_cli.ROUTES` sa CLI-registertestet blir gront. Uppdaterade `data-fetch.md`, `productivity.md`, `warehouse-tools.md`.

## [2026-06-16] perf | Lokal start blir snabbare

`start_local.bat` ar nu snabbt anvandarlage utan `uvicorn --reload` och utan implicit live-sync. Live-till-SQLite-kopia flyttades till `sync_live_local.bat` och kraver `FLOW_SYNC_LIVE_ON_START=1`, sa en kvarliggande `LIVE_DATABASE_URL` inte langre gor vanlig lokal start langsam eller forsoker ersatta en last `flow_local.db`. `start_dev.bat` finns kvar for kodlage med reload.

## [2026-06-16] perf | Bemanning och vybyte laddar snabbare

Gemensam sidinit anvander nu cachad roll-/menydata for snabbare vybyte och friska upp serverdata i bakgrunden. Bemanning bygger aktiviteternas cell-dropdowns lazy: cellerna renderas med tomval och aktuell aktivitet, och hela aktivitetslistan fylls forst nar anvandaren oppnar en cell. Lokal Playwright-matning pa 173 personer/79 aktiviteter gick fran cirka 4,7 s till cirka 0,9 s for Bemanningens forsta anvandbara rader.

## [2026-06-16] perf | Produktivitet renderar skal fore rapportdata

Produktivitet visar nu kontroller, sammanfattningsskal och tradyta direkt och
hamtar `/api/productivity/overview` efter forsta paint. Nar payloaden kommit
vantar vyn en ny paint innan tradet beraknas och ritas, sa tunga
periodrapporter inte blockerar forsta anvandbara sidan. Benchmark/smoke-
verktygen vantar pa `#productivityOverviewStatus`, inte det borttagna
`#productivityStatus`.

## [2026-06-16] change | Bemanning doljer 0% produktivitet

Bemanning visar inte langre `0%` i produktivitetskolumnen. Backendens
`/api/schedule/productivity-summary` filtrerar bort personer som har planerad
KPI-tid men 0 faktisk KPI-poang/process den dagen, och frontend har samma
skydd om ett gammalt/cachat svar anda innehaller `0`.

## [2026-06-16] feature | Intakt/process-kontroll

Intakt/utgift-installningarna har nu knappen `Kontrollera intakter/processer`.
Den kor `POST /api/settings/productivity-finance/process-check` for vald
manad/bolag, hamtar de Mammur-/ASK-kallor som sparade intaktsplaner och
KPI-processregler anvander, och jamfor faktisk radtackning. Resultatet visar
foreslagna processmatchningar, intaktsrader som saknar KPI-process, KPI-processer
som saknar intakt samt mojlig dubbelrakning. Radexempel ar sanerade till
kontrollvarden som bolag/lager/zon/typ/status. Backend auditloggar
`productivity_finance_process_check/run` med period, bolag och summerade
raknetal. Matchningen godkanner aven intaktsrader som tacks av flera
KPI-processer tillsammans och markerar bredare KPI-processer som granskningsnotis
i stallet for att underkanna intaktsraden. Kallfel fran Mammur/ASK visas nu per
kalla med sanerad feltext och utan falsk "ingen tydlig process"-matchning.

## [2026-06-16] observability | Lokal TLS-varning tystas per process

Nar `DATA_SOURCE_VERIFY_SSL=false` anvands lokalt dampar `ExternalDataClient`
upprepade `urllib3 InsecureRequestWarning`-rader och skriver bara en Flow-loggrad
om att TLS-verifiering ar avstangd. Sjalva requests-anropen fortsatter anvanda
`verify=False`; CA-bundle-laget paverkas inte.

## [2026-06-16] polish | Intakt/process-kontroll forklarar delvisa matcher

KPI-reglerna bar nu med sina filtervillkor som metadata sa
Intakt/process-kontrollen kan forklara varfor en intaktsrad bara ar delvis
tackt. Exempel: en rad kan matcha processen `Receiving`, men saknade
receive-rader visar nu att KPI-regeln vantade `Status` 20/30 medan raderna hade
status 0. KPI-berakningens predicate-logik ar oforandrad.

## [2026-06-16] fix | Intaktsutrakning sparar inte testmanad

`POST /api/settings/productivity-finance/calculation/test` anvander fortfarande
vald manad nar utrakningen provkors, men svaret som sparas pa raden tar bort
testmanadens datumfilter fran plan och SQL/querytext. Standardraderna for GG och
rensningen av befintliga sparade intaktsrader tar ocksa bort gamla
`timestamp`/`time_stamp_int BETWEEN ...`-filter sa utrakningarna ar
periodneutrala tills kontroll/rapport lagger pa vald period.

## [2026-06-16] ux | Radvis Intakt/process-kontroll

Intakt/utgift-rader med sparad utrakningsplan har nu en egen `Kontroll`-knapp.
Knappen kor `/api/settings/productivity-finance/process-check` med `row_id`, sa
backend bara kontrollerar den intaktsraden och hamtar radens relevanta
Mammur-/ASK-vy. Resultatet visar KPI-processer som anvander samma vy med
intaktsantal, processantal, overlapp och diff, vilket gor filteravvikelsen
lattare att granska utan att kora igenom hela bolagets kontroll.

## [2026-06-17] ux | Tomma Ytgenerering-ytor far storre text

Ytgenereringens interaktiva resultatkarta visar nu ytkoden pa lediga ytor med
samma dynamiska textstorlek som kundnamn pa placerade ytor. Staende lediga ytor
roterar ytkoden langs ytan, sa platsnumret forblir tydligt vid utzoomad karta.
Skyddas av riktat Playwright-test i `test_allocation_split_browser.py`.

## [2026-06-29] docs | K8s-databasfel pekar mot fel DATABASE_URL

K8s-secretmallen visar nu Azure SQL-URL aven i kubectl-kommandot, sa den inte
langre ger en Postgres-URL som kopieringsforslag. `k8s/README.md` och
`DEPLOY.md` forklarar att loggen `PostgreSQL: kor alembic upgrade head ...` i
K8s betyder att `DATABASE_URL` fortfarande ar Postgres, ofta en Render-intern
URL som inte kan slas upp utanfor Render. `wiki/testing-release.md` skiljer nu
pa Render/Postgres och K8s/Azure SQL vid driftkontroller.

## [2026-07-01] fix | Tom huvudaktivitet forblir tom i Bemanning

Schemalagda malltimmar far inte langre en automatisk huvudaktivitet fran
personens hemomrade. Om personen saknar huvudaktivitet visas timmen tom med
diskret schemalagd-markering; explicit huvudaktivitet och explicita celler
fungerar fortsatt som tidigare. Seed/backfill lamnar befintliga tomma
huvudaktiviteter tomma sa valet styrs fran Personer.

## [2026-07-01] ux | Summering per aktivitet kan kopiera och lokalgruppera

Bemanningens `Summering per aktivitet` kopierar nu timtalet till clipboard nar
anvandaren klickar i `Timmar`-kolumnen. Aktivitetsrader kan markeras med
vanligt klick, Ctrl-/Cmd-klick och Shift-klick; hogerklick visar `Summera` for
flera markerade aktiviteter och `Dela` pa en summerad rad. Grupperingen ar lokal
for aktuell anvandare, dag och omradesvy, gar att angra med Ctrl+Z och skriver
ingen backend-audit eftersom den inte andrar schema eller serverdata.

## [2026-07-01] fix | Summeringsmeny foljer musklicket

Kontextmenyn for `Summering per aktivitet` positioneras nu i dokumentets
koordinatsystem med scroll-offset och faller tillbaka till den hogerklickade
raden om browsern ger ett avvikande contextmenu-varde. Det gor att `Summera`
och `Dela` oppnas vid raden i stallet for hogt upp i Bemanning.

## [2026-07-01] ux | Summeringsrader kan markeras med drag

`Summering per aktivitet` har nu klick-drag over rader for att markera flera
aktiviteter utan Ctrl-/Cmd-klick. Kontextmenyn monteras i summary-kortet och
positioneras fran den hogerklickade radens nederkant, sa `Summera`/`Dela` inte
langre hamnar vid schematabellens scrollbar.

## [2026-07-02] ux | Etiketter som experimentvy

Lade till `Etiketter` som skyddad experimentvy (`labelEditor`) for lokal
label-design med millimetermatt, text, QR, Code128, former, symboler, drag och
utskrift. Vyn ar Super User/opt-in via Vybehorigheter och skriver ingen sparad
audit-logg eftersom etikettlayout och streckkodsvarden inte skickas till
backend; dokumentloggen visar lokala tillagg/rensning/utskrift.

## [2026-07-02] ux | Etikettprofiler och A-format

Etiketter har nu standardprofiler for `104 x 199`, vanliga fraktetiketter samt
A6/A5/A4/A3 i staende och liggande lage. Anvandaren kan spara egna lokala
profiler i browserns `localStorage` och ta bort sparade profiler utan att
etikettmatt eller profilnamn skickas till backend.

## [2026-07-02] ux | Etikettkortkommandon

Etiketter kan nu ta bort valt objekt med `Delete`/`Backspace`, kopiera/klippa
ut/klistra in objekt med `Ctrl+C`/`Ctrl+X`/`Ctrl+V` och angra/gora om lokala
layoutandringar med `Ctrl+Z`, `Ctrl+Y` eller `Ctrl+Shift+Z`. Kortkommandona
ignoreras i redigerbara falt sa textredigering fungerar normalt, och
etikettvarden skickas fortsatt inte till backend eller system-clipboard.

## [2026-07-02] ux | Etiketter far symbol- och emojivaljare

`Symbol` i Etiketter oppnar nu en dialog med flera SVG-symboler och emojis.
Valet laggs in som ett vanligt symbolobjekt, kan andras i egenskapspanelen och
foljer samma lokala dokumentlogg, kortkommandon och read-only/audit-undantag som
ovriga etikettobjekt.

## [2026-07-06] underhall | Repo-stadning: scripts/, tempkataloger, branchar

Repo-roten stadad. De sex .bat-filerna (start, start_dev, start_local,
stop_local, sync_live_local, build_windows) ligger nu i `scripts/` och deras
`%~dp0`-sokvagar ar justerade; alla referenser i BUILD.md, RELEASE.md,
TESTPROTOCOL.md, app/README.md, hardware-README, CI-workflown och tester ar
uppdaterade. Kallmaterialet i `vyer & kolumner/` har flyttats till
`referens/vyer-kolumner/` och `ask-datalagring.md` pekar dit. Pytest stadar nu
bort `tmp_screenshots/` och `.pytest-tmp*`-kataloger efter korning
(`FLOW_KEEP_TEST_ARTIFACTS=1` behaller dem). 22 helt mergade arbetsbranchar
plus doda `in_wait` raderades lokalt och pa origin; `release/*` och omergade
`migration` behalls.

## [2026-07-06] arkitektur | Vendor-motorn uppdelad i engine_core/

`warehouse_tools/vendor/allokering12.1.py` (4 250 rader) ar borttagen.
Den levande logiken (134 definitioner, ~3 500 rader) ligger nu i nio moduler
under `warehouse_tools/engine_core/` (constants, runtime_paths, io_utils, hib,
ordersaldo, observations, allocation, reports, filetypes), alla under
1000-raderstaket. Dod kod (18 funktioner: CLI-writers, sales-metrics,
analytics_store m.m.) raderades. Fasaden `warehouse_tools/engine.py` behaller
samma API sa flows/bryggan/tester ar oforandrade; golden-karakteriserings-
testerna bekraftade identiska utdata fore/efter. Resursdata
(`vendor/lowfreqdata/buffertpall/`) och legacy-modulerna `app_info`/
`update_service` ligger kvar under `vendor/`. Tester ska monkeypatcha
implementationsmodulen (t.ex. `engine_core.runtime_paths`), inte fasaden.
Krympnings-ratcheten i arkitekturkontraktet ar avslutad.

## [2026-07-06] arkitektur | Frontend-typning: JSDoc + tsc + ESLint utan byggsteg

Frontendens vanilla JS har nu maskinkontrollerade kontrakt: JSDoc-typer
verifierade av tsc (npm run typecheck; jsconfig.json, checkJs via // @ts-check
per fil) och ESLint med korrekthetsregler (npm run lint). Bada kors i CI
(test.yml) och i pre-push-hooken. Ingen build - servad JS ar oforandrad.
Nya filer: package.json, jsconfig.json, eslint.config.js,
app/frontend/js/types/flow-globals.d.ts, wiki/frontend-typing.md.
api.js ar forsta @ts-check-filen. Forsta korningarna hittade och fixade:
global namnkollision (PUBLIC_INTERACTION_EVENT_REPORT_PATH i api.js vs
meta_upload.js, omdopt), dod mojibake-kod i settings_finance_check.js och
oatkomlig return i overview.js. Arkitekturkontraktet fick frontend-
domangranser: ALLOWED_PAGE_DOMAINS (en sida = common/ + hogst en doman).
Regler tillagda i AGENTS.md (utrullning, @ts-ignore, backend-synk).

## [2026-07-06] arkitektur | Kvalitetspaket 2-7: typer, ledarlas, syntetisk data, flows-paket

Sex forbattringar i en insats (feature/kvalitet-2-7):

- **API-typer fran OpenAPI**: `tools/generate_api_types.py` genererar
  `app/frontend/js/types/api-schema.d.ts` (~9300 rader) ur FastAPI-schemat;
  CI regenererar och failar pa diff, sa frontendtyper kan inte drifta fran
  `schemas.py`. @ts-check aven i `common/foundation.js` och
  `sankey_inbound_state.js` (overview kraver namnrymdsflytt forst).
- **ESLint/tsc-fynd fixade**: DOM-casts i sankey, inga nya fel.
- **Ledarlas**: `app/backend/leader_lock.py` + tabellen `leader_leases`
  (migration 0046). Bakgrundsjobben startas nu bara av ledarprocessen;
  single-worker-taket ar darmed ett medvetet val, inte ett krav.
  `FLOW_DISABLE_LEADER_LOCK=1` ar felsokningsventil.
- **Syntetisk testdata i CI**: `tools/make_synthetic_testdata.py` +
  `tests/services/fixtures/synthetic/` + `golden_synthetic/` gor att
  karakteriseringstesterna (8 floden) aven kor i CI dar privat testdata
  saknas. Determinismtest binder incheckad data till generatorn.
- **Buggfix fangad av golden**: `normalize_saldo` gjorde tomma
  Plockplats-celler till strangen "nan" under pandas 2.2.x (pinnad version =
  CI/prod; lokal pandas hade driftat). Fix i `engine_core/io_utils.py` +
  vakt i `allocation.py`.
- **flows.py uppdelad**: paketet `warehouse_tools/flows/` (shared,
  allocation_flows, goods_declaration, report_flows, forecast_flows;
  registryt i `__init__`). Sista radtaksundantaget borta. Tester patchar
  implementationsmodulen (`flows.shared._read`,
  `flows.forecast_flows.flow_forecast`).
- **Beroendebevakning**: dependabot.yml (pip/npm/actions) + pip-audit och
  npm audit blockerande i CI. Sarbarhetsbumpar: fastapi 0.139.0,
  starlette 1.3.1, python-multipart 0.0.31, requests 2.33.0.
- **Deploy-verifiering**: kontraktstest for k8s-proberna +
  `tools/post_deploy_check.py` som Octopus-slutsteg (se DEPLOY.md).


## [2026-07-06] ux | Verksamhetsfokus-toggle for Super User i sidebaren

- Ny toggle bredvid omradestogglen i sidebar-footern, endast synlig for
  Super User: vanligt klick stegar mellan aktiva verksamheter och `∞`,
  hogerklick oppnar meny (`/api/businesses`). Valet sparas i
  `flow-business-focus` (localStorage) och synkas mellan flikar.
- Vald verksamhet filtrerar omradestogglens alternativ till verksamhetens
  omraden; omradesfokus som inte tillhor verksamheten nollstalls till `∞`.
- `areaFocusBusinessId` faller for Super User tillbaka pa verksamhetsfokus
  nar omradesfokus ar `∞`, sa lagerverktyg/Hamta data foljer valet.
- Implementation i `js/common/area_focus.js` (nu `// @ts-check`),
  `sidebar.js`, `foundation.js`, `styles.css`. Playwright-tester i
  `tests/tools/test_sidebar_user_browser.py`. Uppdaterade sidor:
  `businesses.md`, `ui-map.md`.

## [2026-07-06] ingest | Nattpass: apphjälpen växer till ~45 tools (Historik, produktivitet, ekonomi, schema, system)

Uppgift 1 i OVERNIGHT_PLAN.md (nattagent, branch feature/nightly-quality-20260706).
16 nya read-only-tools i fem batchar, alla med egna servicetester:

- Historik/fel: error_trend, error_top_endpoints, audit_entity_history,
  wait_metrics_by_endpoint (p50/p95), user_activity_summary, rfid_error_summary.
- Produktivitet: productivity_trend (ISO-veckor), productivity_person_compare,
  productivity_process_trend, productivity_anomalies (z-score, deterministisk).
- Ekonomi: finance_summary — återanvänder periodöversiktens beräkning via nya
  build_business_summary_payload (utbruten ur endpointen, som nu delegerar).
  Kräver ALLTID productivityFinance-behörighet i runtime. Övriga ekonomi-tools
  medvetet strukna (ingen andra sanning om pengar) — se NIGHTLY_NOTES.md.
- Schema: schedule_coverage_gaps, person_utilization, schedule_period_compare.
  (year, week)-filter som OR-kedja, aldrig tuple-IN (MSSQL-lärdomen).
- System: archive_cache_status (trimmad coverage_report), data_fetch_catalog
  (kort default-lista pga 4000-teckenstaket; sankey_inbound_summary struken —
  ingen garanterat billig väg utan OOM-risk).

Ny hjälpare percentile() i assistant_tools/common.py. Dag-/veckogruppering
sker i Python för dialektsäkerhet med _FETCH_CAP som minnesskydd.
Uppdaterat: assistant-tools.md (tool-tabell + kort svar).

## [2026-07-07] ingest | Nattpass: säkerhetshärdning + buggrapportör med 30 s inspelning

Nattagentens uppgift 4 och 7 (OVERNIGHT_PLAN.md, branch feature/nightly-quality-20260706):

- **Säkerhetshärdning**: security_headers-middleware (nosniff, X-Frame-Options
  DENY, Referrer-Policy, HSTS endast över https), rate limiting på
  /api/auth/login (login_rate_limit.py, fast fönster per användarnamn+IP,
  AUTH_LOGIN_RATE_LIMIT_*, auditrader login_failed/login_rate_limited utan
  kontoavslöjande), cookieflaggor kontraktstestade. CSP: endast analys —
  stegplan i NIGHTLY_NOTES.md. Tester: test_security_hardening.py.
- **Buggrapporter** (ny sida bug-reports.md, experiment, beslut 2026-08-07):
  🐞-knapp i sidebar-footern → consent-popup → 30 s DOM-inspelning via vendrad
  rrweb (lazy-laddad) → POST /api/bug-reports (tak/rate limit/retention/audit)
  → uppspelning i nya vyn Buggrapporter (bug-rapporter.html, vy-id bugReports,
  default endast Super User). Migration 0047, api.patch tillagd i js/api.js,
  vendor-undantag i ALLOWED_PAGE_DOMAINS. Tester: test_bug_reports.py.
- **@ts-check-utrullning** (uppgift 2, delvis): 4 → 26 av 82 filer, bl.a. hela
  js/common/. Fynd utan beteendeändring; nya window-globaler deklarerade.

## [2026-07-07] test/prestanda | Pass 2: buggrapportören browsertestad + trace-cachens disk-spill

- Browsertest (test_bug_report_browser.py): consent-gaten (Avbryt = aldrig
  inspelning), inspelning→skicka→uppspelning verifierat i Chromium;
  desktop-smoke exit 0. Buggrapportören därmed komplett testad.
- Trace-cachen tvåskiktad (sankey_inbound/trace.py): L1 processminne +
  gzip-JSON-spill under media-roten. Drill-down överlever processbyte
  (test_sankey_trace_cache.py) — workers-blockeraren borta, workers
  förblir 1. DB medvetet bortvalt (hundratals MB). Prestanda-sidan
  uppdaterad.
- @ts-check: 34 av 82 filer.

## [2026-07-07] test | Pass 3: bulk-rutterna kontraktsskyddade + a11y-svep

routers/bulk.py (copy/clear/fill-from-left) hade 12 % täckning — nu fem
kontraktstester (test_schedule_bulk_routes.py): overwrite-semantik,
weekday-validering, scope, audit med sanerad payload, fyllmönstret till
kl 23. A11y-svepet visade att ikonknappar redan får title+aria-label
dynamiskt; tematogglens tomma initialläge fixat. Benchmark-baslinjen
flyttad till driftmiljön (lokal syntetisk data ger inte meningsfulla
medianer) — se NIGHTLY_NOTES.md.

## [2026-07-07] test/kvalitet | Pass 4: @ts-check 75/84, properties, harness, overview-tester

Slutspurten på nattplanen (branch feature/nightly-quality-20260706):

- **@ts-check: 34 → 75 av 84 frontendfiler.** Codemod + fel-driven patchning
  + handfixar. Riktiga fynd: fyra kopior av veckoberäkningen subtraherade
  Date-objekt, dataset/setAttribute med nummer, död dialogargument i
  presence_print, fel aritet på onProgress-default. Kvarvarande 9 filer
  (overview.js + 8 sidfiler) delar toppnivåvariabler och kräver
  namnrymdsflytt — eget arbete, se NIGHTLY_NOTES.md.
- **Hypothesis**: to_num total/ändlig + svensk sifferform, find_col
  case-insensitivt kontrakt (Hypothesis hittade ß→SS-fällan själv),
  smart_to_datetime rundresa ISO + ÅÅÅÅMMDD.
- **JS-harnessen**: normalizeAppZoom (klampning/stegning/skräp) och
  tabellsorteringens tokenlogik (svenska tal, tomma sist, ISO-datum,
  å/ä/ö efter z).
- **Översikt-routern** (27 % täckning): åtta kontraktstester; tre
  produktregler dokumenterade (dag utan mall = ledig, mallar kräver
  has_fixed_schedule, mallar gäller inte före created_at).
- **Etiketter**: beslutsdatum 2026-08-07 satt (saknades, indexregeln).
- Uppgift 12-analyserna (MCP-server, Sankey-minnesbudget, mutations-
  testning) skissade i NIGHTLY_NOTES.md.

## [2026-07-07] kvalitet | Pass 6: @ts-check 100 %, SWR-pilot, frågebudgetar, mobilfix

Nattplanens slutförande (feature/nightly-quality-20260706, Emirs godkännanden):

- **@ts-check: 85 av 85 frontendfiler.** Fem standalone-sidor via IIFE
  (analytics exponerar setHistoryMode/submitTrackingChat för tester),
  overview-sidans globaler döpta till overviewState/overviewDrag/
  overviewPersonOrderDrag, presence_print läser explicit rätt sidas state.
- **SWR-piloten** (Personer + Översikt): snapshot i sessionStorage målas
  direkt vid sidbyte, färskt hämtas i bakgrunden med Uppdaterar…-pill.
  Nya js/common/api_swr.js (radtakssplit). Se prestanda-leveranslager.md.
- **Frågebudget-kontrakt**: ingen N+1 fanns (10 frågor konstant för
  tyngsta endpointen); test_query_count_budgets.py låser antalet och
  latensbudgetarna åtdragna mot Emirs driftbaslinje.
- **UX/a11y**: tomma lägen i Personer/Användare/Aktiviteter, global
  Escape-stängning av modaler (klickar modalens egen Avbryt-knapp),
  mobiloverflow 96-723px på 13 sidor fixad med en scrollregel i main.

## [2026-07-07] bygge | Buggrapporter: Ta bort + Att göra-status + agent-påminnelse

Emirs önskemål efter första skarpa testet på flow-development:

- **Ta bort**: ny `DELETE /api/bug-reports/{id}` (bugReports edit, scopad,
  auditrad `bug_report`/`delete` utan inspelningsinnehåll). Ta bort-knapp
  per rad och i detaljpanelen, bekräftelsemodal enligt dialogregeln
  (Escape via Avbryt-knappen).
- **Status i vyn**: dropdown per rad + detaljknappar; `seen` omdöpt i UI
  till "Att göra" (DB-värden oförändrade new/seen/done).
- **Agent-påminnelse**: nytt verktyg `tools.bug_reports_status` (best
  effort, healthcheck-cookiejar, mjuk exit utan inloggning) + AGENTS.md-
  regel: påminn Emir om öppna buggrapporter vid arbetsstart i repot.
- Tester: delete-kontrakt (behörighet, audit, 404), summarize/soft-exit
  för verktyget, browsertestet utökat med statusdropdown + ta bort-flödet
  (kört grönt lokalt). API-typer regenererade.

## [2026-07-07] bygge | Fokustogglar: vertikal stapling + verksamhetsfilter vid ∞-områden

Emirs önskemål: togglarna i sidebar-footern var horisontella med öppen
sidebar (nu staplade vertikalt, som i ihopfällt läge), och verksamhets-
togglen filtrerade inte när områdesfokus stod på ∞.

- **Filterregeln**: vald verksamhet + ∞ områden = bara den verksamheten;
  ∞ + ∞ = allt. Nya helpers `areaFocusListParams` (Personer skickar
  business_id serverledes; Översikt vecko-/månads-URL:er + revision) och
  `matchesAreaFocusBusiness` (aktiviteter/användare/personalvyer klient-
  ledes). Översiktens cache-nycklar inkluderar verksamhetsfokus så
  toggle-byte aldrig målar cachat data från fel verksamhet.
- **Omhämtning**: writeBusinessFocus skickar alltid flow:areaFocusChanged
  (tidigare bara när områdesfokus ändrades) så alla vyer laddar om vid
  verksamhetsbyte.
- Kontrakt: tests/tools/test_area_focus_business_filter.py (JS-harness,
  6 tester). Backend oförändrad — alla endpoints tog redan business_id.

## [2026-07-07] bygge | Etiketter: namngivna storleksprofiler, etikettprofiler + copy/paste-feedback

Emirs önskemål i Etiketter-vyn:

- **Namn på etikettstorlekar**: `Spara` i måttpanelen frågar nu efter namn
  (måttet, t.ex. `104 x 200 mm`, är förslag) i stället för att alltid döpa
  profilen till måttet.
- **Etikettprofiler**: ny panelsektion som sparar hela etiketten (mått +
  alla objekt) lokalt i `flow-label-editor-designs-v1` via nya
  `label_editor/designs.js` (max 20, sanering vid läsning, quota-fel ger
  synlig loggrad). Ladda via dropdown (ångringsbart med Ctrl+Z), ta bort
  med bekräftelse.
- **"Kopierade en Code128 men inget hände"**: Ctrl+C/X utan markerat objekt
  och Ctrl+V utan internt kopierat objekt var helt tysta – nu skriver de en
  hjälprad i dokumentloggen. Trolig orsak till buggen: Ctrl+C med fokus i
  Värde-textarean kopierar text, inte objektet.

Tester: kontraktstest utökat (designs.js, nya id:n, promptar, hjälprader),
nytt browsertest spara/ladda/ångra/ta bort etikettprofil + namnprompt för
storleksprofil (kört grönt lokalt). Desktop = samma frontend via QWebEngine
(prompt/confirm stöds) så pariteten håller.

## [2026-07-07] bygge | Buggrapporter: sidbytesräddning + navigeringsvarning

Emirs fråga "du sa att jag inte kunde byta sida under inspelning" — luckan
är täppt (alternativ 1+2; cross-page-inspelning väntar till beslutsdatumet):

- **Räddning**: pagehide sparar events+kontext i sessionStorage
  (flow-bug-report-salvage, 5 min TTL, per flik); sidebar.js eagerladdar
  bug_report.js vid nästa sidladdning som skickar rapporten märkt
  "(inspelningen avbröts av sidbyte)". sendBeacon/keepalive valdes bort
  (64 kB-tak < inspelningsstorlek).
- **Varning**: länk-klick under inspelning fångas i capture-fas och ger
  modal "Stanna kvar"/"Byt sida och skicka" (Escape via Avbryt-mönstret).
- Browsertest: test_page_navigation_salvages_recording (grönt lokalt).

## [2026-07-07] bygge | Buggrapporter: inspelningen fortsätter över sidbyten (alt 3)

Emirs beslut: hoppa direkt på cross-page-inspelning i stället för
räddningsflödet (som blev en mellanlandning samma dag, aldrig deployad):

- pagehide sparar segmentet i sessionStorage (flow-bug-report-session);
  nästa sida återupptar inspelningen med ny full snapshot och nedräkningen
  fortsätter där den var. EN rapport med "scenbyte" per sida —
  rrweb-Replayer hanterar flera fulla snapshots i samma ström.
- Varningsmodalen vid navigering togs bort (sidbyten är nu naturliga);
  consent-texten säger att inspelningen fortsätter över sidbyten.
- Deadline som passeras under sidbytet ⇒ det inspelade skickas direkt.
- Browsertest: test_recording_continues_across_page_navigation verifierar
  indikator + isRecording på sida 2 och ≥2 fulla snapshots i rapporten.

## [2026-07-07] bygge | Vybehörigheter flyttad från Användare till Inställningar

Emirs önskemål: rollmatrisen (roll × vy, Ingen/Visa/Redigera) skulle ligga
under Inställningar i stället för som knapp/modal i Användare.

- **Ny delad modul** `js/common/role_access.js` (`window.flowRoleAccess.
  renderRoleAccessPanel`) med matris-render, registry-laddning, toggle-cykling
  och spara/standard. Laddas i `installningar.html`.
- **Ny flik** `Vybehörigheter` i `allocation/settings_view.js`
  (`?tab=role-access`), gated på `canViewPage(user,"roleAccess")`; `view` ger
  låst matris, `edit` får spara. `boot.js` lade `roleAccess` i
  settings-sidans `anyViewIds`.
- **Borttaget från Användare**: knappen `#role-view-access` i `anvandare.html`
  och all matris-/modal-kod + `VIEW_ACCESS_OPTIONS`/`ROLE_ACCESS_LEVEL_*` i
  `users.js` (registry-rollladdning för användarmodalen kvar). Demo-tourtexten
  i `demo_prefetch_init.js` pekar nu på Inställningar.
- **Tester ompekade**: visual_smoke (`installningar-vybehorigheter`,
  `role_access_panel`), interactive_e2e (panel i stället för modal),
  audit_logs_helpers KNOWN_INTERACTION_CONTROLS (`role-access-save` under
  allocationSettings), test_visual_tools/test_access_contracts/
  test_label_editor_frontend läser matris-labels från role_access.js,
  test_legacy_activity_browser verifierar panelen + att knappen är borta.
  Assistant-systemprompt nämner att Vybehörigheter är en flik under
  Inställningar.
- Desktop = samma frontend (QWebEngine) så pariteten håller automatiskt.

## [2026-07-07] bygge | E2E-undersökningsverktyg (tools/e2e)

Emirs önskemål efter den lyckade screenshot-verifieringen av release 2026.28.7:
utveckla screenshot-skriptet till ett generellt browser-undersökningsverktyg
och lägg kunskapen i repot.

- **tools/e2e/**-paket: env (FLOW_E2E_* ur .env/app/.env, hoppar tomma), session
  (FlowSession: login/goto/screenshot/interaktioner + konsol-/nätverksfångst/
  DOM-läsning), report (md+json, agent-läsbar), scenarios (registry), CLI
  (python -m tools.e2e, UTF-8-stdout mot cp1252-krasch).
- **Scenarier**: smoke, inspect (--page, undersök vad som helst), sweep (--pages,
  hälsosvep), bug-reports, role-access, business-filter.
- **tools/e2e_screenshots.py** kvar som bakåtkompatibel genväg (kör smoke).
- Non-browser-kontrakt: tests/tools/test_e2e_investigation.py (12 tester, gröna).
- Dokumenterat i wiki/e2e-investigation.md + index. AGENTS-note om att köra
  verktyget vid undersökningar. Utdata i artifacts/e2e/ (gitignorerad).

## [2026-07-08] ingest | Prestandaoptimeringar: kunskapsbas + revisionschecklista

Ny sida `prestanda-optimeringar.md` som samlar ALLA prestandavinster vi mätt
(historiskt + denna vecka) som en anti-mönster-katalog med två syften:
framåtbyggnad och revision. Varje mönster har en grep-signatur så koden kan
svepas efter nya förekomster.

Mönster med uppmätta vinster: A1 ladda-hela-tabellen-och-reducera-i-Python
(coverage 3910→173ms, −96%), A2 N+1 (personliga schemat, staffing), A3
over-fetch (coredata defer, −38%), A4 per-request-ping (pool_pre_ping −37ms/req),
A5 saknat index (audit_log 0048), B1 pandas-loop/vektorisering (dispatch −99%,
observations ~41×), B2 minnesladdning (Sankey OOM → DuckDB, trace tvåskikt),
B3 omräkning (sankey package_ladders 512×→1×, katalog 26→4ms, prebuilt-cacher),
B4 compute-then-filter (orderkontroll −87%), C1 blocking-in-async → tråd,
D1–D3 transport/SWR (egen sida), E1–E3 guardrails (frågebudget, latensbudget,
benchmark). Grävde git-historiken (72 perf-commits) för de historiska.

Länkar till prestanda-leveranslager.md och local-archive-cache.md i stället för
att dubblera. Indexpost tillagd. Kontext-varning: dev-latens (~37ms/DB-fråga
Azure) != prod (samma DC) — extrapolera inte.

## [2026-07-08] fix | Meta: dialog ESC/ENTER + robust analys-felhantering (branch bug_fixar)

Raderingsmodalen i `meta.html` kan nu stangas med `ESC` och bekraftas med
`ENTER` (Radera-knappen fokuseras); ingen backdrop-klick-stangning enligt
dialogregeln. Bug: `Analysera` kunde ge `Internal Server Error` (500) och lamna
raden last i `Analyserar` for alltid (Analysera-knappen disablas nar
`status === "analyzing"`). Rotorsak: `analyze_meta_upload` fangade bara
`MetaAnalysisFailed`/`IntegrityError` — ett ovantat undantag (t.ex.
`subprocess.TimeoutExpired`/`OSError` fran `extract_label_still_bytes`, som
saknade try/except) studsade ut som 500 efter att "analyzing" redan committats.
Fix: (1) `extract_label_still_bytes` fangar nu ffmpeg-fel/timeout och returnerar
None (stillbilden ar valfri); (2) `analyze_meta_upload` har en bred
`except Exception` som loggar full traceback (`logger.exception`), satter
`analysis_failed` med felet synligt i UI:t och committar sa raden kan koras om.
Nytt e2e-scenario `meta-analyze` + regressionstest
`test_analyze_meta_upload_marks_unexpected_error_instead_of_leaking_500`.
Sidor: `meta-upload.md`, `e2e-investigation.md`.

## [2026-07-09] ingest | Multi-agent-arbetsmodell (plan)

Ny sida `multi-agent-arbetsmodell.md`: beslutad men ej genomförd plan för
parallellt agentarbete. Underlag: 9-agenters rekognosering + panel
(fork 3/10, worktree 8/10, klon 7/10). Beslut: flytt ur OneDrive +
en worktree per agent; forks förkastade (EmirKadr/flow är prod-infra för
desktop-updatern). Fyra faser: flytt, provisioneringsskript, AGENTS.md-regler,
strukturella spärrar (branch protection på main, wiki/log.md merge=union).
Index uppdaterat.

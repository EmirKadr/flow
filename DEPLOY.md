# Flow – deployment till Kubernetes

Det här dokumentet beskriver hur appen `flow` paketeras som en Docker-image
och vad som krävs för att köra den i ett Kubernetes-kluster. Riktar sig till
den som sätter upp deploymenten på företagets sida.

**Miljöstatus (2026-07-10):** manifesten nedan täcker tre nivåer — lokal
(utvecklarens dator), development och production. Development kör i
företagets Kubernetes sedan 2026-07 (namespace `flow`, manifest i `k8s/`)
med en **MSSQL/Azure SQL**-databas, deployas via Octopus-projektet Flow (se
`wiki/nowaste-git-release.md`). **Production finns ännu inte** — samma
manifest är förberett för den men ingen prod-deploy har gjorts än. Se
miljötabellen i `wiki/architecture.md`. Databasdrivern är ODBC Driver 18 och
ingår i imagen.

---

## 1. Snabbfakta

| Sak | Värde |
|---|---|
| Runtime | Python 3.12 |
| Web-server | uvicorn (ASGI), lyssnar på `$PORT` (default `8000`) |
| Healthcheck | `GET /api/health` → `{"status": "ok", ...}` |
| Databas | Azure SQL Database (Microsoft SQL Server). ODBC Driver 18 ingår i imagen |
| Migrationer | `backend.prestart` vid start: skapar schemat från modellerna + alembic-stamp (se avsnitt 4) |
| Persistens utöver DB | `/repo/data` (uppladdade kärnfiler, se avsnitt 5) |
| Image-användare | `flow` (uid 1000), kör inte som root |
| Statiska filer | Serveras av appen själv från `/repo/app/frontend` |

---

## 2. Bygga imagen

Från repo-roten (där `Dockerfile` ligger):

```bash
docker build -t flow:latest .
```

Bygget tar med:
- `app/` – FastAPI-koden, alembic-migrationer, frontend
- `data/` – initial referensdata (kärnfiler per affärsenhet, m.m.)
- `warehouse_tools/` – allokeringsmotorn som `allocation_bridge.py` läser

`.dockerignore` exkluderar lokala loggar, byggartefakter, desktop-paketering,
stora CSV-exporter och miljöfiler med hemligheter.

Lokal smoke-test:

```bash
docker run --rm -p 8000:8000 \
  -e DATABASE_URL='mssql+pyodbc://USER:PASS@SERVER.database.windows.net:1433/DBNAME?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no' \
  -e SECRET_KEY='något-långt-och-slumpat' \
  -e ENVIRONMENT='production' \
  flow:latest
```

När `GET http://localhost:8000/api/health` svarar `200 ok` är imagen frisk.

---

## 3. Miljövariabler

### Obligatoriska

| Variabel | Beskrivning |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL till Azure SQL. Format: `mssql+pyodbc://user:pass@server.database.windows.net:1433/dbname?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no` |
| `SECRET_KEY` | Hemlig nyckel för session-cookies. Generera med `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ENVIRONMENT` | Sätt till `production` (aktiverar https-only-cookies och cache-headers) |

### Rekommenderade

| Variabel | Beskrivning |
|---|---|
| `SUPER_USER_USERNAMES` | Komma-separerade användarnamn som får admin-rättigheter. Default: `emikad,mikhal` |
| `EXCEL_API_TOKEN` | Token för extern Excel-export-endpoint. Generera slumpmässigt om funktionen ska användas |
| `PORT` | Port uvicorn lyssnar på. Default `8000` |

### Integration: extern datakälla (ASK / Nowaste)

Krävs för att appen ska kunna hämta livedata från ASK WMS.

| Variabel | Beskrivning |
|---|---|
| `DATA_SOURCE_API_BASE_URL` | Bas-URL for extern datakalla. Kan vara tenantmall, t.ex. `https://data-{tenant}.example.test`, eller en tenant-host dar backend byter hostens tenantled. |
| `DATA_SOURCE_API_KEY` | API-nyckel |
| `DATA_SOURCE_API_CLIENT` | Klient-ID |
| `DATA_SOURCE_API_KEY_HEADER` | Header-namn för API-nyckel. Vanligen `x-api-key` |
| `DATA_SOURCE_API_CLIENT_HEADER` | Header-namn för klient. Vanligen `x-api-key-client` |
| `DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE` | T.ex. `/api/integration/views/{view}/data` |
| `DATA_SOURCE_VERIFY_SSL` | `true` i produktion. `false` endast för utveckling mot self-signed cert |
| `DATA_SOURCE_CA_BUNDLE` | Sökväg till CA-bundle om ni har intern PKI. Tomt om standard-CA fungerar |
| `DATA_SOURCE_MAX_ROWS` | Default `1000` |
| `DATA_SOURCE_CATALOG_JSON` | JSON-sträng med view-katalog. Tomt om defaulten räcker |

### Integration: AI-assistent (MiniMax)

Aktiverar in-app-assistenten. Hela blocket kan utelämnas om assistenten inte
ska användas.

| Variabel | Beskrivning |
|---|---|
| `MINIMAX_API_KEY` | API-nyckel |
| `MINIMAX_MODEL` | T.ex. `MiniMax-M2.7` |
| `MINIMAX_API_URL` | Default `https://api.minimax.io/v1/chat/completions` |
| `MINIMAX_MAX_TOKENS` | Default `700` |
| `MINIMAX_TIMEOUT_SECONDS` | Default `30` |

### Observability: OpenTelemetry

OpenTelemetry är avstängt som default. Slå bara på det när en intern collector
finns och attributsaneringen är godkänd.

| Variabel | Beskrivning |
|---|---|
| `OTEL_ENABLED` | `true` aktiverar tracing/instrumentering |
| `OTEL_SERVICE_NAME` | Service-namn, default `flow-web` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Intern collector-endpoint, t.ex. `http://otel-collector:4318/v1/traces` |
| `OTEL_EXPORTER_OTLP_HEADERS` | Kommaseparerade headers om collectorn kräver dem |
| `OTEL_TRACES_SAMPLE_RATE` | Andel lyckade traces, default `0.1` |
| `OTEL_CONSOLE_EXPORTER` | `true` skriver traces till serverloggen i lokal felsökning |

Spans får inte innehålla promptar, svarstext, request bodies, tokens, cookies,
filnamn/filsökvägar, order-/kunddata eller privata externa URL:er. Använd
`trace_id` i Historik/Hälsa för att koppla användarhändelser till tekniska traces.

### Hantering i K8s

Allt som är hemligt (`SECRET_KEY`, `DATABASE_URL`, alla `*_API_KEY`)
hanteras som `Secret`. Det icke-känsliga (`ENVIRONMENT`, `PORT`,
`SUPER_USER_USERNAMES`, modellnamn, max_rows) kan ligga i en `ConfigMap`.

---

## 4. Databas

### Krav

- Azure SQL Database (Microsoft SQL Server)
- Tom databas vid första start (`backend.prestart` skapar schemat)
- Användare med rättighet att skapa tabeller och index

### Schema skapas vid start (inte via PG-migrationer)

Container-entrypoint kör `python -m backend.prestart` före uvicorn. Mot
Azure SQL skapas schemat **från ORM-modellerna** (`Base.metadata.create_all`),
inte genom att spela upp Alembic-migrationerna — migrationerna är skrivna för
PostgreSQL (JSONB, `jsonb_build_array`, m.m.) och replikeras inte rent på
SQL Server. Efter create_all sätts `alembic stamp head` så framtida
migration-spårning fungerar. Operationen är idempotent: finns schemat redan
görs ingenting.

> **Obs för framtida migrationer:** nya Alembic-revisioner måste skrivas
> dialekt-neutralt (undvik `JSONB`, `jsonb_build_array`, `USING`-clauses)
> för att kunna köras mot Azure SQL.

Om K8s-podden loggar `PostgreSQL: kör alembic upgrade head ...` är
`DATABASE_URL` fel för den här målmiljön eller så kör ni avsiktligt Postgres.
Standardvägen för företagsservern är Azure SQL (`mssql+pyodbc://...`).

> Historik: datan migrerades från den tidigare Render-Postgres-driften till
> MSSQL i juli 2026 (radvis kopiering med bevarade id:n). Migrationsskriptet
> `backend.migrate_pg_to_mssql` togs bort ur repot efter verifierad cut-over —
> finns vid behov i git-historiken.

---

## 5. Persistens utöver databasen

Appen läser och **skriver** filer till `/repo/data/` (uppladdade kärnfiler:
artikelregister, kollistor, m.m. per affärsenhet). Initial referensdata
ligger bundlad i imagen, men nya uppladdningar via UI:t måste överleva
container-omstarter.

**Krav:** mounta en `PersistentVolumeClaim` på `/repo/data`.

Storleksuppskattning: ~500 MB räcker länge. Kärnfiler är CSV/Excel i
storleksordningen några MB per affärsenhet.

Om volymen är tom vid första start (vanligt scenario) ersätter den den
inbäddade referensdatan. Det är OK — uppladdning från UI:t fyller på.
Behövs den initiala datan i den persistenta volymen, kopiera in den från
imagen vid första start med en `initContainer`:

```yaml
initContainers:
  - name: seed-data
    image: flow:latest
    command: ["sh", "-c", "cp -rn /repo/data/. /persistent-data/"]
    volumeMounts:
      - name: flow-data
        mountPath: /persistent-data
```

Demo-användarens sandbox skrivs till `/tmp/flow_demo_sessions/` och rensas
automatiskt — den behöver ingen persistens.

---

## 6. Resurser och skalning

Riktvärden (tidigare drift klarade nuvarande last på 0.5 CPU, 512 MB):

| Resurs | Request | Limit |
|---|---|---|
| CPU | 250m | 1000m |
| Memory | 512Mi | 1Gi |

Appen är stateful via DB + persistent volym → börja med **1 replika**.
Horisontell skalning kräver att data-volymen är `ReadWriteMany`, vilket
sällan är värt det. Vertikalt har funkat bra hittills.

Startup tar typiskt 5–15 sekunder (prestart + alembic + uvicorns importkedja —
allt körs *före* socketen binds). Startgrinden är en **startupProbe**, inte ett
`initialDelaySeconds`-golv på readiness. Se avsnitt 7.

---

## 7. Healthcheck och probes

Detta är konfigurationen som ligger i `k8s/flow.yml` och `k8s/deployment.yaml`.
Den är kontraktstestad i `tests/tools/test_gap_k8s_contracts.py` — avvik inte
från den här utan att ändra kontraktet i samma commit, annars faller pre-push.

```yaml
# startupProbe äger hela startfönstret: kubelet håller tillbaka BÅDE liveness
# och readiness tills den passerat. Budget 2s × 90 = 180s.
startupProbe:
  httpGet:
    path: /api/health
    port: 8000
  periodSeconds: 2
  failureThreshold: 90
  timeoutSeconds: 5
livenessProbe:
  httpGet:
    path: /api/health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 30
  timeoutSeconds: 5
readinessProbe:
  httpGet:
    path: /api/health
    port: 8000
  # Inget initialDelaySeconds — startupProbe är startgrinden. Ett golv här är
  # ren nedtid vid varje deploy (strategy: Recreate + replicas: 1).
  periodSeconds: 2
  # 2s × 30 = 60s unready-tolerans, exakt som gamla 10s × 6. NotReady med
  # replicas: 1 = noll Service-endpoints = 503 för alla, så en snabbare cykel
  # får inte krympa toleransen.
  failureThreshold: 30
  timeoutSeconds: 5
```

`timeoutSeconds: 5` på alla tre är medvetet: default (1 s) är för snålt när en
ffmpeg-körning (meta-analysen) CFS-stryper hela cgroupen vid cpu-limit 300m —
kubelet dödar då podden på en tillfälligt långsam proba.

Endpointen kollar inte DB-anslutning — den svarar bara `ok` om processen
lever. Det räcker för K8s-probes; DB-fel ger 500 på andra endpoints, vilket
syns i loggar och dashboards i stället.

---

## 8. Övrigt att veta

- **Cookies / session.** I `ENVIRONMENT=production` sätts session-cookien
  som `Secure` (https-only) och `SameSite=Lax`. Det kräver att appen nås
  via HTTPS bakom Ingress.
- **Statiska filer.** Inget CDN behövs — appen monterar `/repo/app/frontend`
  som `StaticFiles` på `/`. Filerna är små.
- **Ingen extern volym för loggar.** Loggning går till stdout/stderr →
  K8s-loggdrivern fångar det.
- **Inga cron-jobs i appen.** Inga side-effects vid start utöver alembic
  och en bakgrundstråd som synkar allokeringsobservationer från GitHub
  (best-effort, fail-silent).

---

## 9. Kontakt

Frågor om appen, schemat, eller migrationen — kontakta Emir (kadric.emir1@outlook.com).

## Post-deploy-verifiering

Efter varje deploy ska hälsan verifieras maskinellt, inte av första användaren:

1. k8s-proberna (liveness + readiness mot `/api/health`) är kontraktstestade i
   `tests/tools/test_deploy_verification.py` och får inte tas bort.
2. Lägg (engångsjobb för Emir) ett sista steg i Octopus-projektet Flow som kör:

       python -m tools.post_deploy_check --base-url https://<server>

   Steget failar releasen om `/api/health` inte svarar 200 inom ~1 minut
   (12 försök à 5 s; k8s `strategy: Recreate` ger normalt några sekunders
   väntan i början). Vid behov: `--attempts`/`--delay`.
3. För djupare kontroll efter större releaser: `python -m tools.healthcheck
   report --base-url <url>` och Historik-flikarna Hälsa/Väntetider.
4. Latensbudget efter prestandapåverkande releaser:

       python -m tools.api_benchmark --base-url https://<server> \
           --username <user> --password <pass> \
           --label efter-<release> --budget tools/latency_budgets.json

   Avslutar med kod 2 om någon endpoints median överskrider budgeten i
   `tools/latency_budgets.json`. Budgetarna är medvetet generösa i starten —
   dra åt dem allteftersom riktiga rapporter samlas i `artifacts/api_benchmark/`.

## Leveransoptimering (2026-07) och workers

- Appen gzippar själv (GZipMiddleware) och stämplar statiska filer med
  `?v=<innehålls-hash>` i Docker-bygget (`tools/stamp_asset_versions.py`) →
  ett års immutable-cache + service worker-cache. Ingen gzip- eller
  cache-konfiguration behövs i ingressen.
- **Workers: kör 1 (`uvicorn` utan `--workers`).** Ledarlåset
  (`backend/leader_lock.py`) gör flera workers *tillåtna* för bakgrundsjobben,
  men det finns **minst tre processlokala tillstånd** kvar som var för sig
  blockerar `--workers > 1`. Flera oberoende fixar krävs alltså — inte en.

  **1. DuckDB-arkivcachen** (`backend/local_archive_store.py`). Filåtkomsten
  serialiseras med ett **processlokalt** `threading.RLock` (`_LOCKS`), och
  DuckDB tar ett OS-filås på `<tenant>.duckdb`. Cachen är på i drift
  (`ARCHIVE_CACHE_ENABLED=1`, `ARCHIVE_CACHE_SEED_ON_START=1`, `k8s/flow.yml`)
  och bara ledaren skriver (seed/topp-på via `BACKGROUND_JOBS`). Medan ledaren
  håller sitt read-write-handtag kan en annan process **inte ens öppna filen
  `read_only`** — den får `duckdb.IOException` ("Could not set lock on file").
  Bevisat av
  `tests/services/test_local_archive_store.py::test_duckdb_file_lock_blocks_a_second_process`.

  **Detta failar HÖGLJUTT, inte tyst.** `_query_local_archive_segment` fångar
  visserligen cache-fel och faller tillbaka, men
  `backend/sankey_inbound/fetch.py` anropar `local_archive_store.covered_range()`
  **utan `try/except`** — och det anropet körs *före* den skyddade vägen. En
  icke-ledar-worker får därmed `IOException` rakt upp genom anropskedjan och
  **hela Sankey-rapporten svarar 500**. Det är huvudvägen, inte en sidoflik.
  `GET /api/data-fetch/archive-cache/status` (Arkivstatus) svarar också 500.
  Räkna alltså inte med en långsam-men-fungerande fallback.

  **2. Rate-limiten på den publika uppladdningsendpointen** (`_RATE_HITS` i
  `backend/routers/meta_uploads_helpers.py`). `POST /api/meta/uploads` kräver
  **ingen inloggning** — `META_UPLOAD_RATE_LIMIT_PER_MINUTE` är enda skyddet, och
  räknaren är per process. Med N workers blir den faktiska gränsen **N × limit
  per IP**. Det är en säkerhetsregression, inte en prestandanyans.

  **3. Bakgrundsjobbens status** (`_STATUS` i `backend/background.py`), som
  `healthcheck_service.collect_background_jobs()` läser. Bara ledaren startar
  jobben, så en icke-ledar-worker har tom `_STATUS` och rapporterar "Inga
  bakgrundsjobb registrerade i den här processen". Hälsa-rapporten blir då
  beroende av vilken worker som råkar svara — det krockar med hälsoregeln i
  AGENTS.md.

  Sankeys `_TRACE_CACHE` är INTE längre en blockerare: den spills sedan
  2026-07-07 till disk som alla workers delar (`backend/sankey_inbound/trace.py`).

  **Obs — `read_only` för läsarna är INTE fixen för (1).** Alla läsvägar i
  `local_archive_store` öppnar redan `read_only=True`, och testet ovan visar att
  en read_only-öppning ändå kastar `IOException` medan ledaren skriver. Den
  åtgärden är alltså både redan gjord och otillräcklig. Det som faktiskt krävs är
  att läsarna aldrig rör filen ledaren skriver i: skriv till en temporär fil och
  byt in den atomiskt med `os.replace()` (läsarna öppnar sin egen ögonblicksbild),
  eller flytta cachen till en processöverskridande lagring.

  Kriterium för att ta worker-frågan: Historik → Väntetider visar stigande p95
  vid samtidig last (köbildning). Åtgärden är då, i ordning: (a) atomisk
  snapshot-växling för arkivcachen — och gör `covered_range()`-anropet i
  `fetch.py` lika felsäkert som `_query_local_archive_segment`, (b) delad
  rate-limit (DB/Redis) för uppladdningsendpointen, (c) processöverskridande
  jobbstatus för Hälsa. Först därefter höja `--workers`. Kontraktet
  `tests/tools/test_architecture_contracts.py::test_container_start_command_keeps_single_worker`
  håller Dockerfile-CMD:t vid en worker tills dess.


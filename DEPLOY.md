# Flow – deployment till Kubernetes

Det här dokumentet beskriver hur appen `flow` paketeras som en Docker-image
och vad som krävs för att köra den i ett Kubernetes-kluster. Riktar sig till
den som sätter upp deploymenten på företagets sida.

Nuvarande produktion ligger på [Render](render.yaml) (Python web service +
managed Postgres). Migrationen byter ut Render mot Kubernetes + en Postgres
som ni tillhandahåller. Koden är oförändrad — bara packaging och
miljövariabler skiljer sig.

---

## 1. Snabbfakta

| Sak | Värde |
|---|---|
| Runtime | Python 3.12 |
| Web-server | uvicorn (ASGI), lyssnar på `$PORT` (default `8000`) |
| Healthcheck | `GET /api/health` → `{"status": "ok", ...}` |
| Databas | PostgreSQL 14+ (testat mot Render managed Postgres) |
| Migrationer | Alembic, körs automatiskt vid container-start |
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
  -e DATABASE_URL='postgresql+psycopg://USER:PASS@HOST:5432/flow' \
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
| `DATABASE_URL` | SQLAlchemy URL till Postgres. Format: `postgresql+psycopg://user:pass@host:5432/dbname` |
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
| `DATA_SOURCE_API_BASE_URL` | T.ex. `https://noeffectui-frey-development.nowastelogistics.com` |
| `DATA_SOURCE_API_KEY` | API-nyckel |
| `DATA_SOURCE_API_CLIENT` | Klient-ID, t.ex. `nowaste-internal-emir` |
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

### Får inte tas med

`RENDER_*`-variablerna används bara av administrativa endpoints som pratar
med Renders eget API (omstart, db-status). De är meningslösa i K8s och kan
hoppas över.

### Hantering i K8s

Allt som är hemligt (`SECRET_KEY`, `DATABASE_URL`, alla `*_API_KEY`)
hanteras som `Secret`. Det icke-känsliga (`ENVIRONMENT`, `PORT`,
`SUPER_USER_USERNAMES`, modellnamn, max_rows) kan ligga i en `ConfigMap`.

---

## 4. Databas

### Krav

- PostgreSQL 14 eller senare
- Tom databas vid första start (Alembic skapar schemat)
- Användare med rättighet att skapa tabeller och index

### Migrationer

`alembic upgrade head` körs automatiskt i container-entrypoint vid varje
start. Det är idempotent. Vid skarp omstart efter migration-tillägg behövs
inget extra steg.

### Migrera data från Render

För att flytta över befintlig data från nuvarande produktion:

1. **Dumpa från Render** (från en maskin som når Render-DBn):

   ```bash
   pg_dump --no-owner --no-privileges --format=custom \
     "postgresql://USER:PASS@HOST:5432/flow" \
     > flow-render.dump
   ```

   Connection-strängen hämtas från Renders dashboard under `flow-db` →
   "External Database URL".

2. **Restore till nya DBn** (mot K8s-Postgres):

   ```bash
   pg_restore --no-owner --no-privileges --clean --if-exists \
     -d "postgresql://USER:PASS@HOST:5432/flow" \
     flow-render.dump
   ```

3. **Starta containern.** Alembic kör `upgrade head` men det är en no-op om
   schemat redan är på senaste revisionen (vilket det är efter ett färskt
   pg_restore från produktion).

### Tidsplan för cut-over

Eftersom restore lägger in *en ögonblicksbild* av Render-databasen är det
viktigt att inte ta dumpen för tidigt — annars förloras allt som skrivs
under tiden. Föreslagen ordning:

1. K8s-deploymenten reses upp med en *tom* databas och röktestas.
2. När allt fungerar: stoppa Render-instansen (eller frys via ett
   "underhåll pågår"-meddelande), ta pg_dump, kör pg_restore, starta K8s.
3. Pekas DNS/intern URL om från Render till K8s-tjänsten.

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

Riktvärden baserat på Render Starter-planen (0.5 CPU, 512 MB) som klarar
nuvarande last:

| Resurs | Request | Limit |
|---|---|---|
| CPU | 250m | 1000m |
| Memory | 512Mi | 1Gi |

Appen är stateful via DB + persistent volym → börja med **1 replika**.
Horisontell skalning kräver att data-volymen är `ReadWriteMany`, vilket
sällan är värt det. Vertikalt har funkat bra hittills.

Startup tar typiskt 5–15 sekunder (alembic + import av frontend-mounten).
Sätt `readinessProbe.initialDelaySeconds: 15` och `failureThreshold: 6`.

---

## 7. Healthcheck och probes

```yaml
livenessProbe:
  httpGet:
    path: /api/health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 30
readinessProbe:
  httpGet:
    path: /api/health
    port: 8000
  initialDelaySeconds: 15
  periodSeconds: 10
```

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

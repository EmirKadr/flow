# Kubernetes-manifest för Flow

Färdiga manifest för att köra Flow i Kubernetes. Komplement till
[../DEPLOY.md](../DEPLOY.md), som har den fulla bakgrunden (env-variabler,
databasmigrering från Render, resurser m.m.).

## Filer

| Fil | Vad |
|---|---|
| `namespace.yaml` | Namespace `flow` |
| `configmap.yaml` | Icke-känslig runtime-config |
| `secret.example.yaml` | **Mall** för hemligheter — kopiera till `secret.yaml` |
| `pvc.yaml` | Volymer: `flow-data` (/repo/data) och `flow-media` (/var/flow-media) |
| `deployment.yaml` | Web-podden (1 replika, non-root, seed-initContainer, probes) |
| `service.yaml` | ClusterIP på port 80 → 8000 |
| `ingress.yaml` | HTTPS-exponering (kräver ingress-controller + cert) |
| `kustomization.yaml` | Samlar allt utom secret för `kubectl apply -k` |

## Innan ni applicerar — fyll i tre saker

1. **Image-referensen.** I `deployment.yaml` (på två ställen — initContainer
   och main-container) byt `REGISTRY/flow:latest` till ert registry, t.ex.
   `ghcr.io/dole/flow:latest`. Bygg och pusha imagen dit först:
   ```bash
   docker build -t ghcr.io/dole/flow:latest .
   docker push ghcr.io/dole/flow:latest
   ```
2. **Hostname.** I `ingress.yaml` byt `flow.example.com` till er URL.
3. **StorageClass.** Om klustret saknar en default-storageClass, avkommentera
   och sätt `storageClassName` i `pvc.yaml`.

## Deploy

```bash
# 1. Skapa hemligheterna (hamnar inte i git):
kubectl create namespace flow
kubectl -n flow create secret generic flow-secrets \
  --from-literal=DATABASE_URL='mssql+pyodbc://USER:PASS@SERVER.database.windows.net:1433/DBNAME?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no' \
  --from-literal=SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')" \
  --from-literal=EXCEL_API_TOKEN="$(python -c 'import secrets;print(secrets.token_hex(32))')"
#   ...lägg till DATA_SOURCE_* / MINIMAX_API_KEY med fler --from-literal vid behov.
#   (Alternativt: kopiera secret.example.yaml -> secret.yaml, fyll i, kubectl apply -f.)

# 2. Applicera resten:
kubectl apply -k k8s/

# 3. Följ utrullningen:
kubectl -n flow rollout status deployment/flow-web
kubectl -n flow logs -f deployment/flow-web
```

Vid start kör containern `python -m backend.prestart`, som mot Azure SQL
skapar schemat från modellerna och stämplar alembic (migrationerna är
PG-specifika och spelas inte upp mot MSSQL). För att flytta över befintlig
data från Render-Postgres — se [../DEPLOY.md](../DEPLOY.md) avsnitt 4
(skriptet `backend.migrate_pg_to_mssql`, eftersom pg_restore inte funkar mot
SQL Server).

## Verifiera

```bash
kubectl -n flow port-forward svc/flow-web 8080:80
curl http://localhost:8080/api/health    # ska ge {"status":"ok",...}
```

## Felsökning: startup försöker nå PostgreSQL

Om podloggen visar `PostgreSQL: kör alembic upgrade head ...` i K8s betyder
det att `DATABASE_URL` börjar med `postgres...`. Den här K8s-deployen är
skriven för Azure SQL, så `flow-secrets` ska i normalfallet innehålla en
`mssql+pyodbc://...`-URL och podden ska startas om efter ändringen.

En Render-Postgres intern URL fungerar bara inne i Render. Utanför Render ger
den ofta `psycopg.OperationalError: [Errno -2] Name or service not known`
eftersom företagets kluster inte kan slå upp Renders interna databas-host. Om
ni avsiktligt kör Postgres på företagsservern behöver ni i stället skapa en
nåbar Postgres-instans och peka `DATABASE_URL` på dess service/DNS-namn.

## Att tänka på

- **1 replika.** Volymerna är `ReadWriteOnce`. Horisontell skalning kräver
  `ReadWriteMany` — sällan värt det (se DEPLOY.md avsnitt 6).
- **HTTPS krävs.** I `ENVIRONMENT=production` är session-cookien `Secure`;
  utan HTTPS bakom ingressen fungerar inte inloggning.
- **Seed-data.** initContainern kopierar bundlad referensdata till volymen
  vid första start med `cp -rn` (skriver aldrig över senare uppladdningar).

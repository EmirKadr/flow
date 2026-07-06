# flow

Webbaserad ersättning för Excel-bemanningsfilen. Arbetsledare planerar flow per vecka/dag/område i en matris (personer × timmar) där varje cell anger aktivitet.

## Funktioner i MVP

- **Bemanningsvy** – matris med personer som rader och 06:00–23:00 som kolumner. Välj år/vecka/dag/område. Cellerna är dropdowns med alla aktiva aktiviteter (färgkodade).
- **Personregister** – lägg till, redigera och inaktivera personer.
- **Aktivitetsregister** – lägg till, redigera och ta bort aktiviteter med egen färg och sortering.
- **Summering** – visar timmar och uppskattat antal personer per aktivitet för vald dag.
- **Kopiera dag** – kopiera bemanningen från en dag till en annan, valfritt inom samma område.
- **Rensa dag** – tömmer alla celler för vald dag/område.
- **Fyll från vänster** – fyller tomma celler med samma aktivitet som föregående timme för varje person.
- **Multi-user-säkerhet** – varje cell har en versionskolumn. Två arbetsledare kan jobba samtidigt; om samma cell ändras visas ett meddelande och dagen läses om.
- **Historik förberedd** – alla ändringar loggas i `audit_log` (historik-vy byggs i v1.1).

- **Apphjälp** – sessionssparad chatt i sidomenyn som använder projektwikin och MiniMax via backend.
- **Hämta data** – promptstyrd datahämtning där MiniMax väljer vy, kolumner och filter från en publicerbar katalog. Resultat visas i tabell och kan exporteras till Excel.

## Stack

- **Backend:** Python 3 + FastAPI + SQLAlchemy 2 + Alembic
- **Databas:** MSSQL/Azure SQL i produktion (SQLite lokalt)
- **Frontend:** Vanilla HTML/CSS/JS, ingen build-process
- **Auth:** Session-cookie (FastAPI SessionMiddleware) + bcrypt
- **Hosting:** Företagets Kubernetes via Octopus (manifest i `../k8s/`, se `../DEPLOY.md`)

## Windows-klient

Repo-roten innehaller nu aven en PyQt6-baserad Windows-klient som laddar den
centralt hostade appen i ett eget skrivbordsfonster.

- **Desktop shell:** PyQt6 + Qt WebEngine
- **Uppdateringar:** GitHub Releases + `Setup.exe`
- **Build docs:** `..\BUILD.md`
- **Release docs:** `..\RELEASE.md`

Desktop-klienten innehaller ingen lokal databas och ingen lokal FastAPI-server i
steg 1. All affarslogik, auth och delad data ligger fortsatt i den centrala
servermiljon.

## Apphjälp / MiniMax

Chattknappen i sidomenyn fungerar när backend har en MiniMax-nyckel. Sätt `MINIMAX_API_KEY` i `.env` lokalt eller som hemlighet i driftens secret store. Standardmodellen är `MiniMax-M2.7` och endpointen är `https://api.minimax.io/v1/chat/completions`.

## Meta-analys / Gemini

Meta-vyn kan skapa sändningsrader för uppladdade videor och skicka dem till
Gemini. Analysen är audio-only: backend extraherar en temporär ljudfil ur
videon och Gemini ska bara tolka rösten för pall-id och avvikelser. Ordernummer,
sändningsnummer, användarnamn och kund lämnas tomma tills de kan fyllas från
uppladdad data. Automatisk analys efter upload är avstängd som standard med
`META_ANALYSIS_AUTO_START=false`; köade analyser kan startas manuellt i Meta-vyn
eller plockas av `python -m tools.meta_analysis_worker --loop --limit 1` när
driftmiljön har lagring som workern kan läsa.
Lägg Gemini-nyckeln i `.env` lokalt eller i
driftens secret store:

- `GEMINI_API_KEY`
- `GEMINI_MODEL` (standard `gemini-2.5-pro`)
- `GEMINI_API_BASE_URL`
- `META_ANALYSIS_TIMEOUT_SECONDS`
- `META_ANALYSIS_AUTO_START`
- `META_ANALYSIS_MAX_VIDEO_BYTES`

Nya videos får även `duration_seconds` när servern kan läsa längden med
`ffprobe`. Meta-vyn visar samma korta Video-ID i sändningstabellen och
videokortet, så tabellrad och video går att matcha visuellt.

## Hämta data

Datahämtningsvyn använder samma MiniMax-konfiguration, men skickar aldrig API-länkar, headernamn eller nycklar till modellen. Lägg anslutningen till den externa datakällan i miljövariabler:

- `DATA_SOURCE_API_BASE_URL`
- `DATA_SOURCE_API_KEY`
- `DATA_SOURCE_API_CLIENT`
- `DATA_SOURCE_API_KEY_HEADER`
- `DATA_SOURCE_API_CLIENT_HEADER`
- `DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE`
- `DATA_SOURCE_VERIFY_SSL` (standard `true`; kan sättas till `false` lokalt om certifikatkedjan saknas)
- `DATA_SOURCE_CA_BUNDLE` (valfri sökväg till CA-bundle när SSL ska verifieras med intern CA)

Bas-URL och sökvägsmall hålls separata: bas-URL ska normalt bara vara hosten,
medan sökvägsmallen innehåller hela API-sökvägen och `{view}`-platsen. Klienten
kan byta verksamhetens tenant i bas-URL via `{tenant}` eller hostens tenantled.
Om en verksamhet saknar tenant används bas-URL:n oförändrad. Klienten skickar
JSON-payload och förväntar JSON-svar; CSV-läge används inte av appen.
Prompten får appens aktuella datum/tid via backend, och backend efterkorrigerar
relativa datum som `idag`, `dagens` och `senaste N dagarna` innan extern hämtning.

Bygg vy-/kolumnkatalogen med:

```powershell
python tools/build_external_data_catalog.py --views <views.xlsx> --columns <columns.xlsx>
```

Den skriver `data/external_data_catalog.json`, som commitas så servern får katalogen direkt. Endast riktiga API-värden, endpointmallar och headernamn ska ligga i `.env`/driftens secret store.

## RFID-moduler

Fysiska ESP32/RDM6300-moduler postar direkt over WiFi till
`POST /api/rfid/scans`, ingen USB-brygga eller COM-port kravs. Se
`../hardware/MG_Plock/README.md` och `../hardware/MG_VM/README.md` for
WiFi-, server- och tokenkonfiguration.

## Halsa

Historik-fliken Halsa kor server- och databaskontroller samt vantetidsanalys.
Lokalt fungerar app- och databaskontroller utan extra nycklar.
`HEALTHCHECK_PUBLIC_URL` (valfri) later rapporten aven pinga en publik URL.

Efter storre pushar/deploys ska agenter anvanda samma signaler via CLI:

```powershell
python -m tools.healthcheck report --local
python -m tools.healthcheck waits --local --period 24h
```

Produktionens databas ar MSSQL pa foretagets k8s. SQLite anvands bara for lokal
utveckling och temporara tester. Utan lokal databaskoppling kan du kora:

```powershell
python -m tools.healthcheck report --local --skip-db
```

Serverloggar hamtas med `kubectl -n flow logs deploy/flow-web`.

## Lokal seed-inlogg

När du kör `python -m backend.seed` lokalt skapas en admin-användare:
- **Användarnamn:** `admin`
- **Lösenord:** `admin123`

**Byt lösenordet direkt efter första inloggning** och lägg gärna upp minst en extra administratör i adminvyn.

I produktion körs inte seed. Live-data är användarstyrd och första admin-kontot ska redan finnas eller skapas via en kontrollerad engångsbootstrap.
`backend.seed` stoppar dessutom körning när `ENVIRONMENT=production`.

## Deploya till produktion (k8s via Octopus)

Deployen sker via Octopus-projektet **Flow** till företagets Kubernetes.
Commits till en `release/*`-branch bygger automatiskt en release i Octopus,
som sedan deployas till development respektive production därifrån. Se
`../DEPLOY.md` för imagen/miljövariabler, `../k8s/README.md` för manifesten
och `../wiki/nowaste-git-release.md` för hela releaseflödet. Seed körs inte i
produktion — schema skapas av `backend.prestart` vid containerstart.

## Lokal utveckling (kräver Python + Docker)

```powershell
# Starta Postgres
docker run -d --name flow-pg -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=flow postgres:16

cd app
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
python -m backend.seed
uvicorn backend.main:app --reload
```
Öppna http://localhost:8000.

### Lokal testmiljö med live-data

`scripts\start_local.bat` använder alltid SQLite-filen `app/flow_local.db`, så lokala ändringar kan inte påverka live-databasen.
Scriptet startar backend pa port `8000` med `--host 0.0.0.0`, sa ESP32-moduler
pa samma natverk kan na den direkt over WiFi utan nagon lokal brygga. Browsern
oppnas pa `http://localhost:8000`.

Normal lokal start är ett snabbt användarläge utan `uvicorn --reload` och utan
automatisk live-sync. Vid schemaändringar kör starten en lätt lokal bootstrap som behåller befintliga
rader, lägger till saknade kolumner/tabeller och backfyller äldre lokal data till
standardverksamheten `STIGAMO`. Om något ser fel ut lokalt, stäng den gamla
servern med `scripts\stop_local.bat`, starta `scripts\start_local.bat` igen och ladda om
browsern hårt.
Den lokala bootstrappen vägrar köra mot annat än SQLite, så den kan inte råka
skriva seed/backfill till live-Postgres.

Om du utvecklar kod och vill att servern ska ladda om automatiskt använder du
`scripts\start_dev.bat`, som kor backend med `uvicorn --reload`.

Om du vill att den lokala testmiljön ska börja med en färsk kopia av live-data, sätt live-databasens externa URL som en lokal miljövariabel och kör den explicita syncen medan lokal server är stängd:

```powershell
setx LIVE_DATABASE_URL "postgresql://..."
scripts\sync_live_local.bat
```

`scripts\start_local.bat` försöker inte längre ersätta `app/flow_local.db` bara för att
`LIVE_DATABASE_URL` råkar finnas i miljön. Det undviker långsam start och låsta
SQLite-filer i vardagskörning.

Kör `scripts\stop_local.bat` från projektroten om en gammal lokal server fortfarande håller `app/flow_local.db` eller port `8000` låst.

## Mappstruktur

```
app/
├── backend/                FastAPI-app
│   ├── main.py             app, middleware, router-mounts
│   ├── config.py           env-variabler
│   ├── database.py         engine + session
│   ├── models.py           SQLAlchemy-modeller
│   ├── schemas.py          Pydantic request/response
│   ├── deps.py             get_db, get_current_user
│   ├── security.py         bcrypt
│   ├── audit.py            audit_log-helper
│   ├── seed.py             initial data (idempotent)
│   └── routers/
│       ├── auth.py         /api/auth/{login,logout,me}
│       ├── areas.py        /api/areas
│       ├── activities.py   /api/activities
│       ├── persons.py      /api/persons
│       ├── schedule.py     /api/schedule + cell-PUT + summary
│       └── bulk.py         /api/schedule/{copy,clear,fill-from-left}
├── frontend/               statiska filer (serveras av FastAPI)
│   ├── index.html          bemanningsvyn
│   ├── personer.html
│   ├── aktiviteter.html
│   ├── login.html
│   ├── css/styles.css
│   └── js/{api,common,schedule,persons,activities}.js
├── alembic/                migrations
└── requirements.txt
```

## Multi-user-modell

Varje cell i `schedule_cells` har en `version`-kolumn. Klienten skickar `expected_version` vid varje cell-uppdatering. Servern kör `UPDATE … WHERE version = expected_version` (under `SELECT … FOR UPDATE`). Om versionen inte matchar returneras `409 Conflict` med serverns aktuella cell. Klienten visar en toast och läser in dagen igen.

Detta innebär:
- Två arbetsledare på olika celler arbetar parallellt utan att märka varandra.
- Två arbetsledare som ändrar exakt samma cell samtidigt → den senare får ett meddelande och ser den första ändringen.
- Bulk-operationer (kopiera, rensa, fyll-från-vänster) skriver utan version-check men kräver UI-bekräftelse innan de körs.

## Status

- [x] Steg 1: Skelett + deploy-pipeline
- [x] Steg 2: Modeller + migrations + seed
- [x] Steg 3: Auth + personregister
- [x] Steg 4: Bemanningsvyn med multi-user-säkerhet
- [x] Steg 5: Bulk-operationer + aktivitetsregister + audit_log
- [x] Steg 6: README + polish

## Skjutet till v1.1 / v2

Schemat är förberett för dessa funktioner – de kräver bara nytt UI, inte refactor:

- Historikvy ("vem ändrade vad och när?") – läs `audit_log`
- Kompetensvalidering – `persons.competencies` och `activities.required_competency` finns redan
- Realtidsuppdateringar via WebSockets
- Rapporter (timmar per person/månad, närvarostatistik)
- Excel-import från `flow Huset - 2026.xlsx`
- Halvtimmar/kvartstimmar (kräver migration)
- Tauri/Electron Windows-app (frontend/ är redan statisk)

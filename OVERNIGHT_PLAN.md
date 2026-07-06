# Nattplan: kvalitetsgrind för Flow

Detta är en arbetsplan för en autonom Claude-session över natten. Arbeta
igenom uppgifterna i ordning. Läs `AGENTS.md` och `wiki/index.md` FÖRST.

Planen är större än en natt – det är avsiktligt. Varje delmoment
committas och pushas för sig, så natten kan sluta var som helst utan
förlorat arbete. Vid start: läs `NIGHTLY_NOTES.md` om den finns och
fortsätt där förra passet slutade i stället för att börja om. Om
startprompten pekar ut en specifik uppgift gäller den före ordningen.

## Absoluta regler

1. **Branch**: Skapa `feature/nightly-quality-<datum>` från `main` innan
   något ändras. Committa ALDRIG på `release/*` (commits där bygger
   automatiskt releaser i Octopus) eller direkt på `main`.
2. **Commit-rytm**: En commit per avslutat delmoment (t.ex. per typad fil
   eller per testmodul). Kör före varje commit:
   `npm run typecheck && npm run lint && python -m pytest -m "not browser" -n auto`.
   Pusha feature-branchen efter varje commit.
3. **Sänk aldrig ribban**: inga `@ts-ignore` utan motivering enligt
   AGENTS.md, inga skippade/försvagade tester, ingen regenerering av
   golden-filer (`FLOW_GOLDEN_UPDATE=1`) om inte en avsiktlig
   beteendeändring kräver det – och då ska diffen granskas och motiveras
   i commitmeddelandet.
4. **Ingen beteendeändring i produkten** utom buggfixar som tsc/ESLint/
   tester avslöjar. Buggfix = egen commit med förklaring.
5. **Fastnar du** på en fil/uppgift >30 min: anteckna den i
   `NIGHTLY_NOTES.md` (skapa i repo-roten, committas på branchen) och gå
   vidare. Aldrig tyst övergiven uppgift.
6. **Avsluta passet** med wiki-uppdatering (uppgift 11) och en
   sammanfattning överst i `NIGHTLY_NOTES.md`: vad gjordes, vad hittades,
   vad återstår.

## Uppgift 1 (huvudjobb A): bygg ut apphjälpens tool-katalog

Apphjälpen har ~30 read-only-tools i `app/backend/assistant_tools/`
(function calling via MiniMax). Läs `wiki/assistant-tools.md` och
`registry.py` FÖRST och följ det etablerade mönstret exakt:

- Varje tool: read-only handler + registerpost med `view_id` och
  `min_level` + verksamhetsscope via `resolve_business_id` + radtak
  (default 50, max 200) + sanering (aldrig hashar, hemligheter,
  fritextpayloads).
- **All matematik är deterministisk backend-kod.** Modellen routar bara –
  aldrig beräkningar i LLM:en (stående designbeslut).
- Tunga frågor ska gå via arkiv-cachen/befintliga snapshots där sådana
  finns (Sankey-OOM-lärdomen: dra aldrig hela dblog-arkiv i minnet).
- Tester per tool i stil med `tests/services/test_assistant_tools.py`:
  registerkontrakt, scope, handler-logik, felvägar.
- En commit per domänbatch. Uppdatera tool-tabellen i
  `wiki/assistant-tools.md` i samma commit.

Nya tools per domän (verifiera mot datamodellen att datat finns innan du
bygger – bygg ALDRIG ett tool på antagen data; stryk och anteckna i
NIGHTLY_NOTES.md om underlaget saknas):

**Historik och fel** (`analytics`):
- `error_trend` – fel per dag/vecka över en period, per felkod/endpoint.
- `error_top_endpoints` – endpoints med flest fel i perioden.
- `audit_entity_history` – ändringshistorik för en given entitet
  (person/cell/användare): vem, när, vad.
- `wait_metrics_by_endpoint` – svarstids-/väntetidspercentiler per endpoint.
- `user_activity_summary` – en användares aktivitet över tid (auditlogg +
  interaktioner, aggregerat).
- `rfid_error_summary` – misslyckade/ignorerade scans per enhet och dag.

**Produktivitet och processer** (`productivity`):
- `productivity_trend` – utveckling per vecka/månad för verksamhet/område.
- `productivity_person_compare` – person mot områdes-/aktivitetssnitt.
- `productivity_process_trend` – processers utveckling över tid.
- `productivity_anomalies` – dagar/personer som avviker mest från rullande
  snitt (ren deterministisk beräkning, t.ex. avvikelse i standardavvikelser).

**Ekonomi** (underlag finns i `routers/productivity_finance_helpers.py`,
`productivity_finance_process_check.py` och `StaffingCalculatorProfile`):
- `finance_summary` – intäkt vs bemanningskostnad per period och verksamhet.
- `finance_process_breakdown` – intäkt/kostnad nedbrutet per process.
- `staffing_cost_summary` – bemanningskostnad per dag/vecka/område.
- `calc_vs_actual` – kalkylprofil (StaffingCalculatorProfile) mot faktisk
  bemanning: över-/underbemanning i timmar och kronor.
- Sätt `min_level` restriktivt på ekonomi-tools (ledare/admin-nivå,
  följ hur finance-endpoints redan behörighetsskyddas).

**Schema och bemanning** (`schedule`):
- `schedule_coverage_gaps` – pass/dagar där bemanning saknas eller
  understiger kalkyl, per område.
- `person_utilization` – schemalagd tid per person över en period,
  inkl. frånvaromönster om datat finns.
- `schedule_period_compare` – jämför två perioder (bemanning per
  aktivitet/område).

**Flöden och system**:
- `sankey_inbound_summary` – inboundflödets huvudsiffror för en period
  (mottaget, plockat, öppet) via befintlig cache/service – ingen egen
  tung hämtning.
- `archive_cache_status` – täckning per tenant/vy (återanvänd
  `/api/query-data/archive-cache/status`-logiken).
- `data_fetch_catalog` – lista publicerade Hämta data-frågor med
  beskrivning, så chatten kan hänvisa till dem.

Kvalitet före kvantitet: varje tool ska besvara en fråga en ledare
faktiskt ställer. Hellre 10 skarpa tools med bra tester än 25 tunna.
Radtak och teckentak gäller alla svar.

## Uppgift 2 (huvudjobb B): rulla ut `// @ts-check` i frontend

Läge vid planens skapande: 82 JS-filer under `app/frontend/js/`, endast 4
har `@ts-check` (api.js, foundation.js, sankey_inbound_state.js,
area_focus.js). Utrullningsreglerna står i `AGENTS.md` och
`wiki/frontend-typing.md` – följ dem.

Per fil:
1. Lägg till `// @ts-check` överst.
2. Kör `npm run typecheck` och `npm run lint`, fixa alla fynd i filen.
   Typfel löses i första hand med JSDoc-annoteringar och riktiga fixar,
   inte casts. Globala typer finns i `app/frontend/js/types/`.
3. Hittas en riktig bugg (död kod, namnkollision, oåtkomlig gren, fel
   argument): fixa i egen commit, och lägg till/uppdatera test om ytan är
   testbar (JS-harnessen `tests/tools/test_js_unit_harness.py` för ren
   logik, browsertest bara om flödet redan har en testfil).
4. Commit per fil eller per liten grupp närbesläktade filer.

Ordning: börja med `js/common/`, sedan sidfiler i storleksordning
(minst först så rytmen sätts). `overview.js` kräver namnrymdsflytt enligt
wiki-loggen 2026-07-06 – ta den sist, och hoppa över den om flytten växer;
anteckna i så fall i NIGHTLY_NOTES.md.

Målet är INTE nödvändigtvis alla 78 filerna på en natt – målet är stadig
takt utan kvalitetstapp. Varje färdig fil är ett bestående framsteg.

## Uppgift 3 (huvudjobb C): snabbare upplevelse – mindre väntan

Leveranslagret är redan optimerat (gzip, immutable-cache, ETag/304,
service worker – läs `wiki/prestanda-leveranslager.md` FÖRST så du inte
gör om det). Nästa vinster ligger i frågetider och upplevd rendering.
Järnregel för hela uppgiften: **mät före och efter varje ändring** och
skriv siffrorna i commitmeddelandet. Ingen optimering får ändra vilken
data användaren ser.

**A. Mät först.** Starta lokal server med syntetisk/seedad data och kör
`python -m tools.api_benchmark ... --budget tools/latency_budgets.json`.
Ranka endpoints mot budgetarna. Mät alltid före/efter i samma session
(OneDrive/CPU-brus gör absoluta tal opålitliga – jämför medianer relativt).

**B. Backend-frågetider.** För de långsammaste endpointsen:
- Leta N+1-mönster (SQLAlchemy lazy loads i loopar) → eager load eller
  batchhämtning.
- Leta saknade index: jämför frågornas WHERE/JOIN/ORDER mot befintliga
  index i `models.py`/migrationerna. Nya index = ny alembic-migration som
  ska gå igenom BÅDE Postgres- och MSSQL-gaten i CI.
- Leta onödig serialisering (fält som skickas men aldrig läses av
  frontend – verifiera med grep i `app/frontend/js/` innan något tas
  bort; osäker → låt vara).
- Efter varje verifierad förbättring: dra åt motsvarande budget i
  `tools/latency_budgets.json` så vinsten låses av benchmark-rutinen.

**C. Visa cachat direkt (stale-while-revalidate).** Frontend har redan
GET-cache med TTL, in-flight-delning och mutationsinvalidering i
`js/api.js` samt idle-prefetch. Bygg vidare på det: read-tunga vyer som
idag blockerar på fetch vid sidbyte ska rendera cachat innehåll direkt
och uppdatera i bakgrunden när svaret kommer. Krav:
- Aldrig cachat data över verksamhets-/områdesbyte (scope-byte =
  invalidering).
- En diskret "uppdaterar..."-indikator medan bakgrundshämtningen pågår,
  konsekvent med befintliga mönster i `wiki/user-events.md`.
- Playwright-test per konverterad vy: cachat visas direkt, färskt data
  ersätter, mutation invaliderar.
- Börja med 1–2 vyer (t.ex. Personer eller Översikt), utvärdera mönstret
  i NIGHTLY_NOTES.md, fortsätt bara om det bär.

**D. Upplevd rendering.** Svep vyerna efter blockerande spinners där
skelett eller partiell rendering är möjlig, och stora tabeller (Historik)
som bygger hela DOM:en på en gång – mät renderingstid i JS-harnessen/
Playwright innan du ändrar; virtualisera/paginera bara det som bevisat
är långsamt.

**E. Trace-cachen till DB.** Dokumenterad eskaleringsväg i
`wiki/prestanda-leveranslager.md`: sankeys `_TRACE_CACHE`
(`backend/sankey_inbound/trace.py`) är processlokal och blockerar
`--workers 2`. Flytta den till DB (med TTL/städning) så blockeraren
försvinner. **Workers förblir 1** – det beslutet ändras inte i natt;
detta är förberedelse. Kontraktstest på att drill-down överlever
processbyte (simulera med två TestClient-instanser mot samma DB).

## Uppgift 4: säkerhetshärdning

Verifierat läge vid planens skapande: backend sätter INGA
säkerhetsheaders och inloggningen har INGEN rate limiting (bara
meta-upload har en, default av). Åtgärder, i ordning:

1. **Säkerhetsheaders-middleware** i `app/backend/main.py`:
   `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` (eller
   SAMEORIGIN om någon vy behöver iframe – verifiera meta-upload och
   label-editor först), `Referrer-Policy: strict-origin-when-cross-origin`,
   samt HSTS endast när svaret går över https (dev/desktop kör http och
   får inte påverkas). Kontraktstest i stil med `test_http_delivery.py`.
2. **Rate limiting på `/api/auth/login`**: enkel deterministisk limiter
   (per användarnamn + IP, exponentiell backoff eller fast fönster).
   In-memory räcker – appen kör 1 worker (dokumenterat beslut) – men lägg
   den bakom en setting i `config.py` och skriv testet så att det inte
   antar processlokalt läge. Misslyckade försök ska auditloggas utan att
   avslöja om kontot finns. Servicetester för spärr, återhämtning och att
   lyckad inloggning nollställer räknaren.
3. **Sessionscookien**: verifiera `HttpOnly`, `SameSite` och `Secure`
   (Secure bara i produktion/https). Saknas flaggor: fixa + test.
4. **CSP endast som analys**: inventera inline-scripts/styles och skriv i
   NIGHTLY_NOTES.md vad en `Content-Security-Policy` (report-only först)
   skulle kräva. Implementera INTE i natt – fel CSP släcker appen.

## Uppgift 5: tillgänglighet och mobil

1. **Tangentbordssvep**: alla dialoger/menyer ska gå att öppna, navigera
   och stänga (Escape) med tangentbord; fokus ska vara synligt och
   återvända rätt när en dialog stängs. Playwright-test per fixat flöde.
2. **Ikonknappar utan namn**: svep alla 24 HTML-sidorna efter knappar/
   kontroller utan text eller `aria-label`; komplettera. Kontraktstest
   som failar på namnlösa knappar i sidregistret om det går att göra
   robust – annars per-sida-tester.
3. **Kontrast och fokusindikatorer** i `styles.css`: kontrollera mot
   WCAG AA; rätta uppenbara brott (grå-på-grått, borttagen outline).
4. **Mobilsvep**: kör sidregistret i mobil-viewport (mönster finns i
   `tools.server_smoke`/visual-artefakterna): horisontell overflow,
   för små touchytor, tabeller som inte går att scrolla. Fixa det
   entydiga, anteckna det tveksamma i NIGHTLY_NOTES.md.

## Uppgift 6: UX-svep – felmeddelanden, tomma lägen, paritet

1. **Felmeddelanden**: svep frontend efter generiska fel ("Något gick
   fel", råa HTTP-koder mot användare). Gör dem specifika och
   handlingsbara i linje med `wiki/error-reference.md`; uppdatera
   wikisidan när texter ändras.
2. **Tomma lägen och laddlägen**: gå igenom vyerna mot
   `wiki/user-events.md` – varje lista/tabell ska ha ett tydligt tomt
   läge (inte bara tom yta) och ett laddläge. Komplettera det som saknas,
   uppdatera wikisidan.
3. **Desktop-paritet**: paritetsregeln i AGENTS.md säger webb och desktop
   i takt. Kör `python desktop/main.py --smoke-test` och gå igenom de
   senaste veckornas features (verksamhetsfokus-toggle, apphjälpens
   tools, arkivstatus-vyn) i desktop-skalet: fungerar de, saknas något?
   Fixa små avvikelser, anteckna stora.
4. **Experimentstatus**: `wiki/label-editor.md` är `experiment` utan
   beslutsdatum – sätt ett förslag på datum i sidan och lyft det i
   NIGHTLY_NOTES.md (index-regeln kräver beslutsdatum; beslutet är Emirs).

## Uppgift 7 (feature): buggrapportering med 30 sekunders inspelning

Ny funktion, Emirs idé: en "Bugg"-knapp i sidebar-footern (vid
områdes-/verksamhetstogglarna). Klick → förklarande popup → OK → 30
sekunders inspelning av användarens aktivitet i appen → rapporten
skickas in och kan spelas upp av admin. Syfte: användare rapporterar
buggar utan att kunna beskriva dem.

**Teknikval (rekommenderat, avvik bara med motivering i NIGHTLY_NOTES):**
DOM-replay (rrweb eller motsvarande vendorat bibliotek), INTE
`getDisplayMedia`-video. Skäl: ingen webbläsardialog ("välj skärm") som
förvirrar användaren, spelar aldrig in något utanför Flow-fliken,
fungerar i desktop-skalets QtWebEngine, ger små payloads (komprimerade
DOM-events i stället för video) och kan spelas upp pixelnära i en
admin-vy. Vendora biblioteket lokalt (ingen CDN), kör det genom
npm audit-gaten.

**Flöde:**
1. Knapp "Bugg" i sidebar-footern, synlig för alla inloggade roller.
2. Popup före start: förklara att de kommande 30 sekunderna av vad de
   ser och gör i appen spelas in och skickas till administratören, be
   dem återskapa buggen, valfritt textfält "Vad hände?". OK startar,
   Avbryt stänger.
3. Under inspelning: diskret indikator med nedräkning + "Stoppa och
   skicka nu"-knapp (buggen kanske tar 8 sekunder att visa).
4. Vid stopp: paketera inspelningen + kontext som fångas parallellt:
   aktuell sida, användare/verksamhet (från sessionen), konsolfel,
   senaste ~50 flowTrack-händelserna och API-fel under inspelningen.
   POST till ny endpoint, toast "Tack, buggrapporten är skickad".

**Backend:**
- Ny tabell `bug_reports` (migration, dialektsäker PG+MSSQL): användare,
  verksamhet, sida, notis, skapad, status (ny/sedd/klar), pekare till
  inspelningsblob på media-PVC:n (mönstret finns i meta-upload).
- `POST /api/bug-reports`: autentiserad, storlekstak (t.ex. 5 MB),
  rate limit (t.ex. max 3/användare/timme – återanvänd limiter-mönstret
  från uppgift 4), auditrad utan inspelningsinnehåll.
- `GET`-endpoints scopade: admin ser sin verksamhets rapporter,
  Super User allt. Behörighetssvepet fångar rutterna automatiskt.
- Retention: nattlig städning raderar inspelningar äldre än 30 dagar
  (samma jobb-mönster som övriga bakgrundsjobb, bakom ledarlåset).

**Admin-vy:** ny flik/sektion i Historik ("Buggrapporter"): lista med
status, användare, sida, notis; klick öppnar uppspelning + kontextdata.
Statusknappar (sedd/klar).

**Sanering och integritet:** inspelningen visar person-/schemadata som
användaren själv såg – det är acceptabelt (samma data, samma verksamhet),
men maska lösenordsfält (rrweb har maskering inbyggd; verifiera med
test att input type=password aldrig hamnar i inspelningen). Ingen
inspelning får starta utan OK i popupen – Playwright-test på det.

**Livscykel:** lansera som `experiment` enligt wikins statusmodell:
synlig först bakom setting `BUG_REPORTS_ENABLED` (default på i dev,
beslut om prod är Emirs). Ny wikisida `wiki/bug-reports.md` +
uppdatera `ui-map.md`, `user-events.md`, `api.md`, `index.md`.

**Tester:** service (endpoint, scope, rate limit, retention),
kontrakt (auth-svep, migration), Playwright (popup-consent, inspelning
skapas, admin kan spela upp), desktop-paritet (knappen fungerar i
skalet – TESTPROTOCOL gäller).

## Uppgift 8: täck mörka hörn i backend med servicetester

1. Kör: `python -m pytest -m "not browser" -n auto --cov=app/backend --cov-report=term-missing:skip-covered`
2. Lista de 10 sämst täckta modulerna (exkludera alembic-migrationer och
   rena schemafiler).
3. Skriv servicetester enligt `wiki/test-strategi.md` ("Nya tester – var
   hör de hemma?"): backendlogik → `tests/services/`, beteenderegler →
   kontraktstest i `tests/tools/`. Prioritera felvägar (4xx, valideringar,
   scope-/behörighetsgrenar) före happy paths.
4. En commit per testmodul. Hittade buggar fixas i egna commits.

## Uppgift 9: fler Hypothesis-property-tester på motorn

`tests/services/test_engine_properties.py` finns. Gå igenom rena
funktioner i `warehouse_tools/engine_core/` och `warehouse_tools/flows/`
och identifiera invarianter (t.ex. summor bevaras vid chunkning,
normalisering är idempotent, inga NaN-strängar läcker ut). Lägg till
properties för de tydligaste. Kvalitet före kvantitet – en property med
skarp invariant slår fem triviala.

## Uppgift 10: utöka JS-unit-harnessen

Piloten testar ISO-veckologik. Leta upp fler rena funktioner i frontend
(datum-, formaterings-, parsning-, sorteringslogik – gärna sådana som
uppgift 1 gjort typade) och lägg till harness-tester som låser dem.
Web/desktop- eller JS/Python-paritet (som veckopiloten) är extra värdefullt.

## Uppgift 11: wiki-underhåll (avslut)

1. Uppdatera `wiki/assistant-tools.md` med den utökade tool-katalogen
   (om inte redan gjort per batch i uppgift 1).
2. Uppdatera `wiki/frontend-typing.md` med nytt utrullningsläge
   (antal typade filer, kvarvarande undantag).
3. Uppdatera `wiki/test-strategi.md` om nya testklasser tillkommit.
4. Uppdatera `wiki/prestanda-leveranslager.md` med prestandaändringar
   från uppgift 3 (nya budgetvärden, stale-while-revalidate-mönstret,
   trace-cachens nya hemvist).
5. Kör en mini-lint på wikin: sidor som motsäger nattens ändringar,
   inaktuella påståenden i berörda sidor. Rätta det du hittar.
6. Logga hela passet i `wiki/log.md` (append-only, formatet
   `## [ÅÅÅÅ-MM-DD] operation | Titel`).

## Uppgift 12 (endast om tid finns): analys, ingen kod

Utred och skriv rekommendation i NIGHTLY_NOTES.md – implementera inte:
- **Exponera tool-registret som MCP-server**: kunde Flow servera samma
  read-only-tools via MCP så externa klienter (Claude, Codex) kan fråga
  live-data? Utred auth (session/token), tenant-scope, vilka tools som
  är lämpliga, och hur det förhåller sig till befintliga MCP-vyn
  (`wiki/mcp.md`). Endast skiss + säkerhetsanalys.
- Minnesbudget i Sankey-hämtningen (öppen punkt från wiki-loggen
  2026-07-04, delvis avlastad av arkiv-cachen 2026-07-04).
- Mutationstestning (mutmut eller motsvarande) på
  `warehouse_tools/engine_core/` – är det värt att lägga in som
  nattligt CI-jobb?

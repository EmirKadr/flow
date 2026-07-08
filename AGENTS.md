# AGENTS.md

## Syfte

Detta repo innehaller tva forstaklassiga klienter for samma produkt:

- `app/` = webbappen
- `desktop/` = Windows-appen

De ska utvecklas som **en och samma produkt**, inte som tva separata varianter.

## Projektwiki

Det finns en LLM-underhallen projektwiki i `wiki/`.

- Las `wiki/index.md` tidigt nar du behover forsta projektet, anvandarfloden,
  knappar, behorigheter, API:er eller felsokning.
- Folj `wiki/AGENTS.md` nar du uppdaterar wikin.
- Nar en kodandring paverkar produktbeteende, knappar, vyer, roller, API eller
  felmeddelanden ska relevant wiki-sida och `wiki/log.md` uppdateras i samma
  arbetsinsats.

## Kallkodshantering och release (NoWaste)

Flow driftas sedan 2026-07 officiellt pa NoWaste-servern: GitHub-orgen
`nowastelogistics`, deploy via Octopus-projektet **Flow** till foretagets
Kubernetes (`k8s/`, namespace `flow`, MSSQL-databas). NoWaste har en egen
branch- och releasemodell (master/develop/feature/release/hotfix/patch) som
finns sammanfattad i `wiki/nowaste-git-release.md`.

- Viktigast: **commits till en `release/*`-branch bygger automatiskt en
  release i Octopus**. Feature mergas till release-branchen, eller `main`
  mergas dit om andringen redan ar i main.
- **Pusha ALDRIG direkt till `main`. Alltid feature-branch.** Skapa alltid en
  ny feature-branch for nytt arbete och pusha den (oppna PR for merge). Enda
  undantaget: om arbetet ar en direkt fortsattning pa en nyligen skapad
  feature-branch som ANNU INTE mergats in i nagon annan branch, far du pusha
  vidare pa samma branch. Nytt arbete -> ny branch; uppfoljning pa en
  omergad branch -> samma branch. Aterupplivade arbetsbranchar ersatter inte
  en riktig feature-branch. Branchen `in_wait` ar **dod** (2026-07-03) och far
  aldrig anvandas igen - varken for commits, merges eller releaser.
  (En agent bröt denna regel 2026-07-08 genom att pusha rakt pa `main`.)
- **Varje deploy far en ny `release/*`-branch** (namnschema
  `release/{ar}.{vecka}.{sekvens}`, nasta lediga sekvens). Aterandvand aldrig
  en gammal release-branch for en ny deploy - Octopus bygger per branch och
  historiken ska visa exakt vad varje release innehall.
- **Pusha release-branchen i en EGEN `git push`, inte buntad med feature +
  main.** `Flow Docker`-workflowen (som bygger imagen och skapar
  Octopus-releasen) har ett `paths`-filter; pushar man flera nya refs
  samtidigt och de delar commits (t.ex. main i samma push) ser GitHub inga
  nya andrade filer unika for release-refen och **hoppar over imagebygget** -
  da skapas ingen Octopus-release trots gron push. Hande 2026-07-06 med
  `release/2026.28.2`. **Gron `Tests`-workflow bevisar INTE att imagen byggts**
  (Tests saknar paths-filter, Flow Docker har det - olika workflows). Verifiera
  alltid efter release-push: `gh run list --workflow=flow-docker.yml` ska visa
  en korning for release-refen. Saknas den: `gh workflow run flow-docker.yml
  --ref release/<ver>` (workflow_dispatch ar en sanktionerad vag - t.ex.
  `release/2026.27.4` skapades sa). Se `wiki/nowaste-git-release.md`.
- **Nytt/andrat GitHub-workflow: verifiera dess EGEN korning gron efter push**
  (`gh run list --workflow=<fil>`), inte bara de workflows du forvantade dig.
  Lart 2026-07-06: nightly-flake-hunt.yml failade pa varje push med "No jobs
  were run" for att GitHub inte kunde PARSA filen - en oindenterad rad (kolumn
  0) i en flerradig `--body`-strang avslutade block-scalarn (`run: |`) for
  tidigt. **PyYAML var slapphant och parsade den anda → falsk trygghet lokalt;
  GitHubs parser ar strangare.** Fallgropar: undvik inbaddade radbrytningar i
  shell-strangar inuti `run:` (skriv pa en rad), och om ett jobb ska skippas pa
  push - gardera pa STEG-niva (job-level `if` som exkluderar allt ger noll jobb
  = failure). Kontraktet `tests/tools/test_workflow_contracts.py` haller bada
  (strolinjer vid kolumn 0 + push-overlevnad) och hade fangat det i pre-push.
- **Kor testsviten fore push.** Pre-push-hooken (`.githooks/pre-push`) kor
  typkontroll, lint och `pytest -m "not browser"` automatiskt; kringga den
  aldrig slentrianmassigt (nodfall: `FLOW_SKIP_PREPUSH_TESTS=1`, motivera i
  commit-texten). Browsertesterna (`-m browser`, Playwright) ar lastkansliga
  pa utvecklarmaskinen och gate:as i CI med max 2 omkorningar; en nattlig
  flake-jakt kor dem 3x utan omkorningar och oppnar issue vid instabilitet.
  Aterkommande omkorningar ska rotorsakas, inte normaliseras - se
  `wiki/test-strategi.md`. CI ar skyddsnatet, inte forsta forsvarslinjen.
- **Benchmarka fore och efter vid stora/prestandapaverkande andringar**
  (query-/cache-/anslutnings-/arkitekturandringar): kor
  `python -m tools.api_benchmark --label fore-<andring> ...` mot miljon innan,
  samma med `--compare` efterat, och redovisa diffen i PR/commit-texten.
  Effekt ska vara matt, inte gissad. Baslinjer ligger i `artifacts/api_benchmark/`.
- Emir behover inte folja NoWaste-processen till punkt och pricka i detta
  repo (huvudbranchen heter `main`), men agenter ska kanna till modellen,
  anvanda dess begrepp korrekt och hjalpa till nar releaser gors mot
  NoWaste-miljoerna (development/production via Octopus).
- Render-driften ar avvecklad (juli 2026). `render.yaml`, RENDER_*-settings
  och migreringsskriptet `backend.migrate_pg_to_mssql` ar borttagna ur repot;
  historiken finns i git.

## Buggrapport-paminnelse vid arbetsstart

Anvandare rapporterar buggar via Bugg-knappen (vyn Buggrapporter, se
`wiki/bug-reports.md`). Agenter ska hjalpa till att inga rapporter blir
liggande:

- Nar en agent borjar en ny arbetsinsats i repot ska den kora
  `python -m tools.bug_reports_status` och, om det finns oppna rapporter,
  paminna Emir tidigt i konversationen: "Du har X oppna buggrapporter
  (Y nya, Z att gora)".
- Verktyget ar best effort: det ateranvander healthcheck-cookiejaren
  (`.flow-cli-cookies.txt`) och hoppar mjukt over sig sjalvt om inloggning
  saknas eller miljon inte nas. Paminnelsen far aldrig blockera eller
  fordroja det egentliga arbetet, och agenten ska inte jaga inloggning
  enbart for paminnelsens skull.
- Paminn en gang per arbetsinsats, inte vid varje meddelande. Om Emir redan
  pratar om buggrapporterna behover de inte paminnas.

## E2E-undersökningar i webbläsaren

För att verifiera att UI:t faktiskt fungerar live (inte bara att testerna är
gröna) finns `python -m tools.e2e` — ett Playwright-baserat undersökningsverktyg
som loggar in mot en körande miljö och kör scenarier (skärmbilder, konsol-/
nätverksfelsfångst, DOM-inspektion, assertions) och skriver en agent-läsbar
rapport. Se `wiki/e2e-investigation.md`.

- Kör `python -m tools.e2e --list` för scenarier; `inspect --page /x.html` för
  en godtycklig sida, `sweep` för hälsosvep, `smoke` för de nya funktionerna.
- Inloggning läses ur `FLOW_E2E_*` i `app/.env` (gitignorerad). Verktyget hoppar
  mjukt över sig självt om uppgifterna saknas. Lösenordet loggas/committas aldrig.
- Utdata i `artifacts/e2e/` (gitignorerad): läs `report.md` och skärmbilderna.
- Verktyget är read-only; det ska aldrig trigga destruktiva åtgärder (t.ex. ta
  bort buggrapporter eller starta en riktig inspelning).

## Hemligheter, commits och pushar

`AGENTS.md` ska vara kvar i git. Den ar till for att framtida agenter och
utvecklare ska se reglerna innan de gor commits. Att gitignora den vore
overdrivet och skulle gora skyddet svagare. Skriv reglerna generiskt; lagg aldrig
riktiga nycklar, privata URL:er, headernamn, endpointmallar, kataloginnehall eller
kund-/lagerdata i `AGENTS.md`.

## Lokal agent-observability

Kodande agenter ska anvanda `tools.agent_audit` nar de gor kodandringar i repot.
Detta ar ett lokalt komplement till runtime-OTel: det sparar vilken agent/run som
gjorde en commit, vilka filer som andrades, vilka testkommandon som kordes och en
lokal span-liknande tidslinje under `artifacts/agent_runs/`.

- Kor `python -m tools.agent_audit install-hooks --agent codex --auto` om hooks
  inte redan ar installerade.
- For langre arbeten: starta med `python -m tools.agent_audit start --goal "..."`
  och avsluta med `python -m tools.agent_audit finish --summary "..."`.
- Kor testkommandon via `python -m tools.agent_audit exec -- <kommando>` nar det
  ar rimligt, sa testresultat hamnar i agenthistoriken.
- Spara aldrig prompts, svarstext, kunddata, tokens, privata URL:er, filinnehall
  eller request bodies i manuella agent-audit-event.
- `artifacts/agent_runs/` ar lokal historik och ska inte commitas.

Fore varje commit och push ska agenten kontrollera att inga hemligheter eller
privata data foljer med:

- Kor `git status --short` och granska alla staged och unstaged filer.
- Kor `git status --short --ignored app/.env data private-data` nar andringen
  ror API, import/export, datahamtning eller miljokonfiguration.
- Kor `git diff --cached --name-only` och stoppa om listan innehaller `.env`,
  lokala databaser, genererade kataloger, privata Excel/CSV-underlag eller andra
  filer som bara ska finnas lokalt.
- Sok staged diffen efter hemlighetsmonster och gamla provider-detaljer innan
  push. Minst kontrollera ord som `API_KEY`, `SECRET`, `TOKEN`, `PASSWORD`,
  `PRIVATE`, samt provider-specifika namn, URL:er, headernamn och endpointmallar.
- `.env.example`, README, wiki och `k8s/secret.example.yaml` far bara innehalla
  tomma eller generiska variabelnamn/platshallare for hemligheter. De far inte
  innehalla riktiga varden eller leverantorens privata API-kontrakt.
- Backend ska lasa privata anslutningsdetaljer fran miljo variabler eller
  driftens secret store. Frontend far aldrig prata direkt med privata externa API:er.
- Privata dataunderlag ska vara ignorerade i git. En genererad katalog far
  commitas om Emir uttryckligen bedomer att vy-/kolumnnamnen inte ar hemliga,
  som `data/external_data_catalog.json` for Hämta data. Katalogen far aldrig
  innehalla nycklar, URL:er, headernamn, endpointmallar eller rad-/kunddata.
- Om en hemlighet redan har blivit staged: avbryt committen, unstagea filen och
  flytta vardet till `.env` eller driftens secret store.
- Om en hemlighet redan har pushats: pusha inte mer ovanpa i panik. Skriv tydligt
  till Emir att nyckeln maste roteras och att historiken kan behova saneras.
  Historikradering eller force-push far bara goras efter uttrycklig instruktion.

Nar Hämta data eller andra externa datafloden andras ska kod och dokumentation
fortsatta anvanda generiska namn som `DATA_SOURCE_*`, `external_data_client` och
`/api/query-data`. Provider-specifika sokvagar, headernamn, URL:er och nycklar
ska stanna i lokala ignorerade filer eller i driftens secrets. Den publika
standardkatalogen far ligga i `data/external_data_catalog.json` nar den bara
innehaller vy-/kolumnstruktur.

## Huvudregel: strikt funktionsparitet

Alla agenter som arbetar i detta repo ska utga fran att:

- allt som byggs eller andras i webbappen ocksa ska finnas i Windows-appen
- allt som byggs eller andras i Windows-appen ocksa ska finnas i webbappen

Detta galler bland annat:

- funktioner
- arbetsfloden
- knappar och menyval
- validering och regler
- vyer och navigering
- viktiga texter, varningar och anvandarbesked

Ingen agent far medvetet lamna webb och Windows ur synk utan uttrycklig instruktion
fran Emir.

## Praktisk tolkning

Nar du andrar nagot, kontrollera alltid konsekvensen for bada klienterna:

1. Om en ny funktion laggs i webbappen, lagg ocksa till den i Windows-appen.
2. Om en ny funktion laggs i Windows-appen, lagg ocksa till den i webbappen.
3. Om ett arbetsflode andras i ena klienten, uppdatera den andra klienten i samma arbete.
4. Om exakt samma implementation inte ar mojlig, los det med olika teknik men samma beteende for anvandaren.

## Tillatna undantag

Foljande far vara klientspecifikt utan att bryta mot paritetsregeln:

- Windows-installation, `Setup.exe`, auto-update och genvagar
- serverdrift, deployment och backend-infrastruktur
- andra rent plattformsspecifika detaljer som inte motsvarar en anvandarfunktion

Om du tror att nagot annat maste vara olika mellan klienterna ska det ses som ett
blockerande beslut och inte antas tyst.

## Arbetsregel for agenter

Vid varje andring som paverkar produktbeteende ska agenten:

- aktivt kontrollera bada klienterna
- uppdatera bada sidor i samma arbetsinsats nar paritet kravs
- uppdatera tester och dokumentation nar det ar relevant
- tydligt saga till om full paritet inte hanns med eller om nagot blockerar den

## Dialogregel for frontend

Dialoger och modaler som innehaller textfalt, textarea, tabeller eller andra
markerbara ytor far inte stangas med ett enkelt backdrop-`click`-monster som
`event.target === backdrop`. Det kan stanga dialogen nar anvandaren markerar text
och slapper musen utanfor rutan. Anvand en explicit `Avbryt`/`Stang`-knapp som
grundregel. Om en dialog verkligen ska kunna stangas genom klick utanfor ska
implementationen skilja pa klick och drag/textmarkering, till exempel genom att
krava att bade pointerdown och pointerup startar/slutar pa backdropen, och ett
test ska skydda beteendet.

## Frontend-typning och lint (JSDoc + tsc + ESLint)

Frontendens vanilla JS ar buildlos och ska forbli det - inga ramverk, ingen
bundler. Typsakerheten kommer fran JSDoc-typer verifierade av TypeScript-
kompilatorn som ren checker plus ESLint med korrekthetsregler. CI och
pre-push-hooken kor `npm run typecheck` och `npm run lint`; bada ska vara
grona fore push. Konfig: `jsconfig.json`, `eslint.config.js`,
`app/frontend/js/types/flow-globals.d.ts`. Se `wiki/frontend-typing.md`.

- **Utrullningsregel:** en JS-fil som andras vasentligt ska fa `// @ts-check`
  hogst upp innan arbetet lamnas, och dess typfel ska fixas. Tackningen vaxer
  organiskt - ingen stor migrering, men heller ingen ny ocheckad kod.
- **Flyktvagsregel:** `@ts-ignore`/`@ts-expect-error` kraver en motivering pa
  samma rad och ska behandlas som radtaksundantagen: tillatet men synligt och
  ifragasatt. Sprid dem inte.
- **Synkregel mot backend:** nar ett Pydantic-schema i `app/backend/schemas.py`
  andras ska motsvarande `@typedef`/interface i frontendens typer uppdateras i
  samma arbetsinsats - samma princip som paritetsregeln webb/desktop.
- **Domangranser:** en HTML-sida laddar script fran `js/common/` plus hogst en
  domankatalog (`js/allocation/`, `js/schedule/`, ...). Kontraktet ligger i
  `tests/tools/test_architecture_contracts.py::ALLOWED_PAGE_DOMAINS` och nya
  korsberoenden ar medvetna beslut, precis som `ALLOWED_DOMAIN_EDGES`.

## Loggregel for agenter

Anvandaren ska kunna se vad som lyckades, vad som misslyckades och vad systemet
gjorde i bakgrunden utan att oppna utvecklarverktyg. Varje ny eller andrad
anvandarhandling ska darfor ha synlig loggning nar det ar relevant:

- lyckade muteringar, importer, exporter, bakgrundsladdningar och Bearbeta-floden
  ska ge toast eller dokument-/sidebarlogg
- fel, delvisa fel, blockerade floden och bakgrundsfel ska ge warn/error-logg med
  begriplig anvandartext
- nya API-mutationer och nedladdningar ska helst ga via `app/frontend/js/api.js`
  sa de far standardloggning; egna `fetch`-wrappers ska uttryckligen logga
  success/failure
- loggar far inte innehalla losenord, cookies, API-nycklar, privata URL:er,
  request bodies eller privata rad-/kunddata

Smal tracking-exception for Historik/interaction-events: klartext-vardeprov far
bara sparas for uttryckligt trackade anvandarinteraktioner och bara nar
backend-flaggan `TRACKING_ALLOW_VALUE_SAMPLES=true` ar satt. Default ar false
och backend ska da strippa eller ersatta vardeprover med langd/antal aven om
klienten skickar dem. Undantaget galler aldrig losenord, cookies, tokens,
API-nycklar, privata URL:er, filnamn, filvagar, request bodies,
provider-detaljer eller privata externa API-kontrakt.

Backend-audit och frontendens dokumentlogg ar olika saker. Audit ar sparad
historik for felsokning och uppfoljning. Dokumentloggen ar anvandarnara feedback
i aktuell browser/session. Nar ett flode paverkar anvandaren ska bada anvandas
om bada perspektiven ar relevanta.

Nya anvandarsynliga handelser, integrationer och bakgrundsfloden ska ha en
explicit Historik/Analys-plan innan arbetet anses klart. Agenten ska bestamma
vilken `audit_log.entity_type`, `action`, `business_id`, `user_id` och sanerad
payload som skrivs, samt hur raden blir begriplig i Historik/Analys med
anvandarlabel i frontend och vid behov backend-summary. Det galler aven
hardvara och externa system: om requesten aldrig nar backend ska agenten bygga
eller dokumentera en synlig diagnostik som visar var kedjan brister.

Nar en agent skapar ett nytt flode, en API-mutation, import/export, integration,
bakgrundsjobb eller hardvaruhandelse som skapar, andrar, synkar eller tar emot
data ar sparad audit-rad och begriplig Historik/Analys-label obligatoriska
leverabler. Det racker inte att funktionen fungerar i UI:t. Det ska finnas en
sparad auditrad med ratt scope och sanerad payload, plus en label/summary som
gor raden begriplig for anvandaren i Historik/Analys. Om ett nytt flode ar
medvetet read-only eller inte ska auditloggas ska undantaget dokumenteras och
testas, sa det inte kan vara en tyst miss.

Vantetidsmatningar ar ett tredje spar: tyst prestandatelemetri for hur lange
anvandaren faktiskt vantar pa vyer, API:er, nedladdningar och bakgrundsladdning.
Den ska vara sanerad, kortfattad och synas i Historik/Halsa-analys, inte i
dokumentloggen.

## Halsa- och driftregel for agenter

Halsa och vantetider ar ett arbetssatt, inte en engangsfeature. Nar en agent gor
en storre andring, pushar backend/frontend-beteende, andrar cache/bakgrundsladdning,
databas, drift-/k8s-konfiguration, import/export, Bearbeta-floden eller releasefiler
ska agenten aktivt kontrollera systemhalsan.

Fore slutrapport efter storre push ska agenten normalt kora eller verifiera:

- `python -m tools.healthcheck report --local` for lokal app- och
  databassignal.
- `python -m tools.healthcheck waits --local --period 24h` nar vantetidsdata finns.
- `python -m tools.healthcheck report --base-url <url>` mot servern efter deploy
  nar agenten har inloggning/cookie.
- Historik-flikarna `Halsa` och `Vantetider` visuellt eller via API nar UI:t
  paverkas.

Om healthcheck visar `error` eller tydliga `warn` efter en stor andring ska
agenten inte behandla arbetet som fardigt utan att antingen fixa orsaken eller
tydligt rapportera kvarvarande risk, exakt kommando, tidpunkt och feltext.

## Releasepolling for agenter

Efter push/tagg for release ska agenten normalt bara verifiera att GitHub
Actions-workflowen har startat, ge anvandaren lank till workflow/run och saga
att det ar okej att avsluta har och be agenten kolla releasen senare.

Agenten ska inte sitta och poll:a releasejobbet tatt om anvandaren inte
uttryckligen ber om att vanta kvar. Om anvandaren ber agenten vanta kvar galler
denna pollingtrappa:

- vanta 15 minuter innan forsta statuskollen
- om inte klart: vanta 2 minuter och kolla igen
- om inte klart: vanta 1 minut och kolla igen
- darefter kolla var 30:e sekund tills workflowen ar bekraftat klar eller failad

Detta ar for att undvika onodiga statusanrop, logghamtningar och
kontext-/tokenkostnad nar GitHub/Octopus anda arbetar asynkront.

## Testregel for agenter

Varje gang en agent bygger nytt, andrar befintligt beteende eller lagger till ett
nytt arbetsflode ska agenten ocksa se till att det finns relevanta tester for
det nya. Befintliga tester ska uppdateras nar de gamla antagandena inte langre
stammer med hur appen fungerar.

Agenten ska inte lamna ett nytt beteende utan teststod om det gar att testa
rimligt med befintlig teststack. Om nagot inte gar att automatisera ska agenten
skriva tydligt vad som testats manuellt och varfor automatiskt test saknas.

Tester ska tankas fran tva perspektiv:

- anvandarperspektiv: ett test ska, nar det ar rimligt, klicka eller kora samma
  flode som en riktig anvandare och verifiera synligt resultat
- utvecklarperspektiv: ett test ska ocksa skydda kontrakt, regler, dataformat,
  behorigheter, API-svar eller andra interna antaganden som gor felet latt att
  hitta tidigt

For nya Bearbeta-/lagerfloden ska agenten normalt lagga teststod i flera lager:
handler-/domantest for `warehouse_tools`, API-/session-/coredata-test for
allokeringsbryggan och ett anvandarnara frontendtest nar knappar, readiness eller
flodesberoenden andras. Om ett flode bygger pa ett tidigare resultat, till
exempel en session-artifact, ska testet verifiera bade att artifacten sparas och
att nasta knapp skickar ratt session-id.

Nar en andring byter namn, begrepp, menyval, roll, vy eller annat sprak i
produkten ska agenten inte skriva ett engangstest for bara den texten. Lagg eller
uppdatera i stallet ett ateranvandbart kontrakt, till exempel i
`tools/terminology_contracts.py`, och lat bade statiska tester och renderade
UI-tester anvanda samma kontrakt.

Nar beteende tas bort eller byts ut ska agenten aktivt leta efter gamla tester
som bara skyddar det borttagna beteendet. Sadana tester ska tas bort eller
skrivas om, sa testsviten inte tvingar kvar gammal produktlogik av misstag.

Nar en ny handelse eller integration laggs till ska testerna tacka hela kedjan,
inte bara huvudfunktionen: mottagande API/domantest, sparad audit-rad,
Historik/Analys-label eller frontendkontrakt, behorighet/verksamhetsscope samt
minst ett relevant fel- eller okant-lage. Fysisk hardvara eller externa system
far mockas, men testet ska bevisa att systemet hade visat det for anvandaren
nar backend tar emot handelsen. Manuell scanning eller klickning far bara vara
komplement, inte enda verifieringen.

Tester for nya dataandrande floden ska ocksa bevisa att audit och
Historik/Analys-labels faktiskt finns. Minimikravet ar ett doman-/API-test som
visar auditposten eller ett kontraktstest som binder `entity_type`/`action` till
frontend-/backend-labeln. Om flodet saknar audit pa grund av ett avsiktligt
read-only-undantag ska testet bevisa just det undantaget.

Nar en andring ror databas, Alembic, Docker-build, CI-workflows, secret/env-
konfiguration eller deploy ska agenten ocksa lagga eller uppdatera kontraktstester
for de driftbegransningar som kan fa push/deploy att falla. Testa inte bara den
nya funktionen utan aven de invariants som miljoerna kraver, till exempel
Alembic-revisioners maxlangd, unikhet, down_revision-kedja, exakt en head,
att CI simulerar alembic-bygget mot Postgres och att `k8s/secret.example.yaml`
bara har platshallare. Om ett deployfel upptacks efter push ska nasta fix helst
lagga ett test som hade fangat just den felklassen fore push.

## Arkitekturkontrakt

`tests/tools/test_architecture_contracts.py` haller tre invariants som agenter
ska respektera i stallet for att kringga:

- **Radtak per fil.** Backend-Python och frontend-JS har tak (1000 rader).
  Blir en fil for stor ska den splittas i ett paket med bakatkompatibel fasad,
  som `app/backend/data_fetch/`, `app/backend/mcp/` och
  `app/backend/sankey_inbound/`. Hoj aldrig taket eller lagg till undantag
  utan uttrycklig instruktion fran Emir. Nar en undantagsfil splittas ska
  dess undantag tas bort.
- **Single-worker + ledarlas.** Bakgrundsjobben i `app/backend/background.py`
  och schedulerna startas via DB-ledarlaset i `app/backend/leader_lock.py` -
  bara ledarprocessen kor dem. Dockerfile kor fortfarande en uvicorn-worker;
  att hoja `--workers` ar ett medvetet beslut som kraver verifierat ledarlas
  i drift och uppdaterat arkitekturkontrakt i samma andring.
- **Domangranser.** Servicemoduler far importera delad grund och sin egen
  doman. Ett nytt beroende mellan domaner ar ett medvetet beslut: lagg till
  kanten i `ALLOWED_DOMAIN_EDGES` i samma andring och motivera i
  commit-meddelandet.

Nya bakgrundsjobb registreras i `BACKGROUND_JOBS` i `app/backend/main.py`,
aldrig som egna tradar eller startup-hooks. Ny kod ska importera fran paketen
direkt; tester ska monkeypatcha implementationsmodulen, inte fasaden.

## Livscykel for funktioner

Varje funktionssida i `wiki/` har ett `status`-falt som ar funktionens
livscykel: `aktiv`, `experiment`, `frys` eller `avveckla` (se `wiki/index.md`).

- Nya funktioner borjar normalt som `experiment`: gate:ade bakom Super User
  eller vy-/verksamhetstoggles, avstangda som default for vanliga anvandare.
- Ett experiment ska ha ett beslutsdatum. Nar det passerats ska agenten lyfta
  fragan till Emir: slapp till alla, forlang med nytt datum, eller ta bort.
- `frys` betyder buggfixar men inga nya features - ifragasatt onskemal som
  bygger ut en fryst funktion innan de genomfors.
- Slapp till alla ska ske via toggle/rollaccess (runtime), inte kodandring,
  sa rollback ar en flip och inte en deploy.

## Riskgenomgang efter nytt bygge

Nar en agent anser sig klar med ett nytt bygge, stor andring eller nytt
arbetsflode ska agenten stanna upp innan slutrapport och fraga sig:

- Vad kan ga fel for en riktig anvandare?
- Vilka roller, verksamheter, vyer, importer, toggles, cachelagen eller
  klientskillnader kan paverkas?
- Finns det gamla antaganden i tester, dokumentation, lokal data eller
  desktop/webb-paritet som nu kan vara fel?
- Vilka fel skulle vara svara att upptacka visuellt eller manuellt?

Agenten ska sedan anvanda tillgangliga verktyg for att undersoka de riskerna,
till exempel `rg`, riktade enhetstester, API-kontraktstester, full pytest,
Playwright/visual smoke, desktop-proxy, lokal databasinspektion eller CLI-verktyg.

Om ett rimligt felutfall inte redan tacks av tester ska agenten lagga till eller
uppdatera tester innan arbetet lamnas. Testerna ska vara formulerade sa att de
hade fangat felet om andringen hade gjorts fel. Om nagot inte gar att testa
automatiskt ska agenten skriva vad som undersoktes manuellt, vilket verktyg som
anvandes och vilken kvarvarande risk som finns.

## Beslutsregel

Om en uppgift verkar bara namna `app/` eller bara `desktop/`, men andringen
egentligen paverkar anvandarflodet, ska agenten anda behandla den som en
paritetsandring for bada klienterna om inte Emir uttryckligen sagt annat.

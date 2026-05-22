# Testprotokoll

Det har protokollet beskriver hur en agent ska testa flow efter andringar.
Appen finns i tva klienter som ska hallas i paritet:

- `app/` ar webbappen.
- `desktop/` ar Windows-appen som startar en lokal app-yta i ett PyQt-skal och
  proxar API-anrop till samma centrala backend som hemsidan.

## Grundregel

Varje andring som paverkar anvandarupplevelsen ska testas i bade webbappen och
Windows-appen. Webbscreenshots granskar sjalva produktvyerna. Desktop-screenshots
granskar Windows-skalet runt webbappen.

## Snabbtest

Kor detta fore commit nar andringen inte ar rent dokumentar:

```powershell
python -m pytest
Get-ChildItem -Path app\frontend\js -Filter *.js | ForEach-Object { node --check $_.FullName }
python -m tools.flow_cli routes --format table
python desktop\main.py --smoke-test
```

Samma skydd finns i GitHub Actions pa varje push och pull request via
`.github/workflows/test.yml`. Den kor pytest, JS-syntaxkontroll, desktop smoke
och en Render-liknande build med Alembic + seed.

For release eller desktop-andringar:

```powershell
cmd /c build_windows.bat
python -m tools.release_check
```

## Automatiska tester som finns

- `tests/services/` testar backendregler, roller, import, schema, mallar,
  updater och public API.
- `tests/services/test_business_scope.py` testar verksamhetsisolering, många
  användare, korsverksamhetsvalidering, settings, Super User och public API.
- `tests/desktop/test_app.py` testar Windows-skalets health check,
  fellage och uppdateringsflode.
- `tests/tools/test_visual_tools.py` testar att visuella verktyg fortfarande
  tacker viktiga vyer och att ikon-/manifest-assets finns pa alla HTML-sidor.

## Testkarta for agenter

Den har kartan forklarar vad testfilerna skyddar. Nar en agent andrar kod ska
den valja minsta relevanta testurval fran tabellen och sedan lagga till bredare
tester om andringen ror delad logik, API-kontrakt, behorighet eller UI.

| Testfil | Syfte | Kor nar du andrar |
| --- | --- | --- |
| `tests/conftest.py` | Delad testinfrastruktur, Qt-appfixture och testmiljo. | Testfixtures, Qt/desktop-teststod eller global testkonfiguration. |
| `tests/desktop/test_app.py` | Windows-skalets startup, health check, felvy, stangning och updateflode. | `desktop/app.py`, update-kod, health check eller desktop-start. |
| `tests/desktop/test_local_app_server.py` | Desktopens lokala frontendserver, API-proxy och cookie-omskrivning. | `desktop/local_app_server.py`, cookies, proxy eller paketerad frontend. |
| `tests/services/test_activity_codes.py` | Stabil kodgenerering for aktivitetsnamn och omradesprefix. | Aktivitetsetiketter, kodnormalisering eller omradeskod. |
| `tests/services/test_activity_import.py` | Aktivitetsimportmallar, Excel-parsning, validering, roller och borttagning. | Aktivitetsimport, aktivitets-CRUD eller importmallar. |
| `tests/services/test_allocation_bridge.py` | Backendbryggan till lagerverktyg, filidentifiering, sessionsresultat och rollbegransade floden. | `allocation_bridge`, allokeringsrouter, filuppladdning eller lagerfloden. |
| `tests/services/test_assistant_chat.py` | Apphjalpens MiniMax-konfiguration, promptregler, repo-/wiki-kontext, anvandarkontext och kvot. | Apphjalp, MiniMax, wiki-kontext, behorighetssvar eller chattsession. |
| `tests/services/test_business_scope.py` | Verksamhetsisolering, många användare, listfilter, främmande id, korsverksamhetswrites, Super User-create, settings och public API. | `business_scope`, schemawrites, registerfilter, Super User-filter, settings eller nya verksamheter. |
| `tests/services/test_data_fetch_service.py` | Hamta data-flodets katalog, LLM-plan, hemlighetsbarriar, extern datahamtning och Excel-export. | `Hamta data`, extern datakalla, katalogbyggnad, MiniMax-planering eller export. |
| `tests/services/test_health_service.py` | Desktop/klient-health URL och felhantering. | Health service eller anslutningskontroll. |
| `tests/services/test_legacy_activity_routes.py` | Gamla aktivitetsvagar redirectar till nya aktivitetsvyn och statiska filer cachas ratt i dev. | Legacy-redirects, statisk frontendservering eller aktivitetsrutter. |
| `tests/services/test_live_local_sync.py` | Lokal SQLite-sync fran live-databas och skydd mot fel target. | `prepare_local_database`, live/local sync eller `start_local.bat`-dataflode. |
| `tests/services/test_person_import.py` | Personimportmallar, Excel-parsning, dubblettskydd, skapa/uppdatera/ta bort person. | Personimport, person-CRUD eller namnvalidering. |
| `tests/services/test_person_schedules.py` | Timmis/fast schema-regler for personers veckomallar. | Personschema, timmisflagga eller veckomalllogik. |
| `tests/services/test_productivity_service.py` | Produktivitetsfilstatus, filidentifiering, rapportgruppering och tillgangliga datum. | Produktivitet, plock-/pallloggar, KPI-filer eller rapportbyggnad. |
| `tests/services/test_public_api.py` | Public API:s datum-/vecko-tolkning och tokenhantering. | Public endpoints, datumparametrar eller publika tokenregler. |
| `tests/services/test_role_access.py` | Roll- och vybehorighet, Super User, starkaste roll och view/edit-nivaer. | Roller, `user_access`, vybehorigheter eller sidebar-atkomst. |
| `tests/services/test_schedule_locks.py` | Lasning av schemaceller mellan anvandare och admin-/bemanningsansvarig-bypass. | Schemalas, celluppdatering eller installningen for lasning. |
| `tests/services/test_seed_data.py` | Seed-data, lokal SQLite-bootstrap, verksamhetsbackfill och dubblettsanering. | `backend.seed`, `bootstrap_local`, verksamheter eller standarddata. |
| `tests/services/test_sidebar_settings.py` | Sidebar-layout och rollbaserad vybehorighet sparas och saneras ratt. | Sidebarinställningar, roll-vy-access eller settingsrouter. |
| `tests/services/test_template_service.py` | Standardveckomall, saknade dagar och timmis utan ledigmall. | Veckomallar eller schema-template-logik. |
| `tests/services/test_update_service.py` | Versionsjamforelse och hamtning av release-installationsfil. | Update-check, GitHub release-logik eller installer-download. |
| `tests/services/test_user_creation.py` | Skapa/uppdatera anvandare, roller, Super User-skydd och passwordless-login. | Anvandare, roller, losenord eller auth-relaterad user-CRUD. |
| `tests/services/test_user_import.py` | Anvandarimportmallar, svensk rollparsning, flera roller och radfel. | Anvandarimport eller rollformat i Excel. |
| `tests/services/test_warehouse_tools_local_data.py` | Lagerverktygens lokala fixture-data, flodesregister och regressionsresultat. | `warehouse_tools`, allocate/refill/pallet-space eller lagerfixtures. |
| `tests/tools/test_access_contracts.py` | Backend/frontend-kontrakt for vy-ID:n, rollistor, default access och legacy-alias. | Vybehorigheter, sidebar pages, roller eller legacy view mapping. |
| `tests/tools/test_activity_terminology.py` | Terminologikontrakt sa gamla aktivitetsord inte smyger in. | UI-text, docs eller migration fran gammal terminologi. |
| `tests/tools/test_allocation_split_browser.py` | Playwright-test for Dela-resultattabell och kolumnkopiering. | `dela.html`, split values, tabellrendering eller clipboard for lagerverktyg. |
| `tests/tools/test_compare_warehouse_results.py` | CSV/XLSX-jamforelse for Flow mot Allokera, inklusive exportnormalisering. | `tools/compare_warehouse_results.py`, parityjamforelser eller lagerexportformat. |
| `tests/tools/test_api_route_contracts.py` | Frontendens hardkodade API-anrop finns i FastAPI med ratt metod. | Nya/andrade API-anrop i JS eller backend-rutter. |
| `tests/tools/test_flow_cli.py` | CLI-routekatalog, API_ROUTES-dokumentation, generiska API-call och DB-lookup. | `tools/flow_cli.py`, API-rutter, CLI-adapter eller API-dokumentation. |
| `tests/tools/test_warehouse_cli.py` | Lokal Bearbeta/Dela-CLI, scenariofiler, automatisk filmatchning och outputfiler. | `warehouse_tools/cli.py`, lagerflodes-CLI eller lokala regressionskommandon. |
| `tests/tools/test_ci_workflows.py` | CI och release workflows kor ratt grindar fore build/deploy. | `.github/workflows/*` eller releasepipeline. |
| `tests/tools/test_desktop_app_probe_runtime.py` | Desktop-proben kan starta lokal server/proxy och skriva runtime-artifacts. | `tools/desktop_app_probe.py` eller desktop-proxytest. |
| `tests/tools/test_legacy_activity_browser.py` | Browserkontrakt for legacy-aktivitetssidor och vybehorighetsmodalens text. | Legacy aktivitetssidor, aktivitets-UI eller rollaccessmodal. |
| `tests/tools/test_persons_view.py` | Personvyns frontendkontrakt: delete-knapp, Ctrl+Z och ingen aktiv/inaktiv-toggle. | `personer.html` eller `persons.js`. |
| `tests/tools/test_release_check.py` | Release-zippen innehaller nodvandiga filer och frontend. | `tools/release_check.py`, packaging eller release-artefakter. |
| `tests/tools/test_sidebar_user_browser.py` | Sidebarens footer visar namn, roll och logout i ratt ordning i browser. | Sidebar footer, anvandarvisning eller logoutknapp. |
| `tests/tools/test_visual_tools.py` | Kontrakt for visual smoke, interaktiv E2E, desktop probes, frontend assets, global UI-wiring och kritiska vyer. | Sidebar/global frontend, visuella verktyg, assets, imports, allokerings-UI eller testprotokoll. |

Om en ny testfil laggs till ska den in i tabellen ovan. Om en testfil byter
ansvar ska beskrivningen uppdateras i samma commit som testandringen.

## Visuellt webbscreeningverktyg

Verktyg:

```powershell
python -m tools.visual_smoke
```

Det gor detta:

1. Skapar en temporar SQLite-databas under `artifacts/visual/<timestamp>/`.
2. Kor lokal schema/bootstrap och `tools.visual_data`.
3. Startar en lokal FastAPI-server pa ledig port.
4. Loggar in som testroller.
5. Tar screenshots i desktop- och mobilstorlek.
6. Skriver `summary.json` med alla filer som skapades.

Forsta gangen pa en ny maskin kan Playwright behova installeras:

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
```

Vanliga varianter:

```powershell
python -m tools.visual_smoke --roles public,admin,leader,staffing,viewer
python -m tools.visual_smoke --roles admin,warehouse
python -m tools.visual_smoke --base-url http://127.0.0.1:8000 --roles admin
python -m tools.visual_smoke --via-desktop-proxy --roles public,admin,warehouse
python -m tools.visual_smoke --output artifacts\visual\manual-check
```

## Lagerverktyg / lokal flow-data

Bearbeta och Dela kor flows egna `warehouse_tools`-paket.
Lagerflodena testas mot lokal fixture-data i `testdata/warehouse_tools`, sa
testsviten inte kraver nagot sibling-projekt.

```powershell
python -m pytest tests\services\test_warehouse_tools_local_data.py
python -m pytest tests\tools\test_warehouse_cli.py tests\tools\test_compare_warehouse_results.py tests\tools\test_flow_cli.py
```

Testet kontrollerar publikt flodesregister, datapool, summaries, tabellnycklar,
radantal och representativa cellvarden for de deterministiska flodena.

For manuell parity mot gamla Allokera-CLI:t finns tre terminalspår:

```powershell
python -m warehouse_tools.cli list-flows
python -m warehouse_tools.cli allocate --auto-file orders.csv --auto-file buffer.csv --auto-file item_option.csv --format both --out artifacts\allocate
python -m tools.flow_cli allocation run allocate --file orders=orders.csv --file buffer=buffer.csv --file items=item_option.csv --out artifacts\api-allocate
python -m tools.compare_warehouse_results --left .\Resultat.csv --right .\tmp6jj8twk6_allocated_orders.xlsx
```

`warehouse_tools.cli` kor flodet lokalt utan server. `tools.flow_cli allocation`
kor samma API som webb/desktop. `compare_warehouse_results` jamfor CSV/XLSX
efter normalisering av typiskt exportbrus som `1.0` mot `1` och NaN mot tomt.

## Read-only databasuppslag

Nar man behover svara pa fragor som "finns den har anvandaren/personen i
databasen?" ska man anvanda CLI:ns read-only-uppslag i stallet for att skriva
egna SQL-snuttar:

```powershell
python -m tools.flow_cli db lookup all --q "Anton Holmqvist"
python -m tools.flow_cli db lookup users --q "emikad" --json
python -m tools.flow_cli db lookup persons --q "Henrik" --database-url "sqlite:///app/flow_local.db"
```

Kommandot laser bara fran databasen och visar aven inaktiva/dolda rader som
standard. Anvand `--active-only` om bara aktiva rader ska visas.

`--via-desktop-proxy` testar samma frontend via desktop-appens lokala appserver
och proxar API-anrop till testbackend. Anvand den nar en andring paverkar
Windows-appens lokala appyta, cookies, API-proxy eller paketerad frontend.

Bas-screenshots som ska granskas:

- Login.
- Bemanning i admin-, arbetsledar- och visningsroll.
- Oversikt i admin-, arbetsledar- och visningsroll.
- Personer.
- Aktiviteter.
- Historik.
- Anvandare.
- Uppladdningar och Dela for Lagerkontorist samt Bearbeta for admin/super user.

Scenario-screenshots som ska granskas:

- Bemanning med Alla områden.
- Bemanning som Stigamo-användare med `∞`, där bara Stigamo-data syns.
- Bemanning som R3-användare, där bara R3-toggle finns.
- Bemanning som Super User med globalt `∞` och verksamhetsfilter.
- Bemanning med Mestergruppen.
- Bemanning med Autostore.
- Bemanning med tomt personfilter.
- Kopiera dag-modal.
- Bemanningskalkyl med Alla.
- Kompakt/sidebar-collapse.
- Oversikt med Mestergruppen.
- Oversikt i manadslage.
- Oversikt i manadslage med Mestergruppen.
- Oversikt med tomt personfilter.
- Veckomall-modal.
- Ny person-modal.
- Ny aktivitet-modal.
- Redigera aktivitet-modal.
- Ny anvandare-modal.
- Redigera anvandare-modal.
- Verksamheter-vyn for Super User, inklusive omraden per verksamhet.
- Historik med filter.
- Nekad atkomst for visningsroll till Personer, Aktiviteter, Anvandare och Historik.
- Nekad atkomst for arbetsledare till Anvandare och Historik.
- Nekad atkomst for arbetsledare och visningsroll till Uppladdningar.

Granska visuellt att:

- Text inte kapas eller overlappar.
- Sidebar, kontroller och tabeller ligger ratt i desktop och mobil.
- Rollerna visar ratt navigation och ratt vyer.
- Otillgangliga sidor skickar anvandaren till Bemanning och visar feltoast.
- Databasikonen, uppladdningsnotis och uppladdningspilen syns pa Lager-sidorna.
- Lagerverktygsvyerna kan visas via desktop-proxyn utan att sidebar blinkar bort.
- Farger, halvceller, schemalagda/lediga celler och kalkyl syns begripligt.
- Modaler far plats och har fungerande primar/sekundar-knappar.

## Interaktivt E2E-verktyg for webben

Verktyg:

```powershell
python -m tools.interactive_e2e
```

Det har ar verktyget som en agent ska anvanda nar den behover testa att det gar
att klicka runt och faktiskt gora saker i appen. Det skapar en temporar databas,
startar en lokal server, kor Playwright och sparar screenshots + `report.json`
under `artifacts/interactive/<timestamp>/`.

Det testar bland annat:

- Logga in som admin.
- Skapa och redigera anvandare, inklusive roll och område.
- Andra installningscheckbox och aktivera/inaktivera anvandare.
- Skapa och redigera aktivitet.
- Ta bort aktivitet och verifiera att den försvinner.
- Skapa person, redigera namn inline och andra veckomall.
- Vaxla person mellan fast schemamall och timmis utan att rakna timmis som ledig.
- Redigera personens omrade, sortering och aktiv-status inline.
- Andra bemanningscell, dela halvcell och kopiera/klistra in cell.
- Kopiera dag, rensa dag, angra och gor om.
- Andra i Oversikt och byta till manadsvy.
- Filtrera Historik.
- Logga in som visningsroll och verifiera att den ar read-only.
- Verifiera att visningsroll och arbetsledare stoppas fran otillatna sidor.

## Verksamhetsscope

När en ändring rör personer, aktiviteter, användare, schema, översikt,
settings, public API eller områdestoggle ska relevanta tester bevisa:

- Stigamo-användare ser inte R3-data och R3-användare ser inte Stigamo-data.
- Flera användare i Stigamo respektive R3 är dolda för varandra i listor och
  detail/update/delete.
- En vanlig admin behöver inte välja verksamhet vid create/import; backend
  använder användarens verksamhet.
- Super User kan lista allt med `∞`, filtrera med `business_id` och måste välja
  verksamhet när den inte kan härledas.
- Områden, personer, aktiviteter och settings är scopeade per verksamhet, medan
  användarnamn är globalt unika.
- R3 kan fa nya omraden utan att Stigamo paverkas, samma omradeskod kan finnas i
  olika verksamheter och omraden med kopplad data inaktiveras vid delete.
- Publika `/api/public/*` defaultar till `STIGAMO`, kan köras explicit mot `R3`
  och gör aldrig global summering utan verksamhet.

Obligatoriska regressioner för verksamhetsscope:

```powershell
python -m pytest tests\services\test_business_scope.py -q
python -m pytest tests\services\test_person_import.py tests\services\test_activity_import.py tests\services\test_user_import.py -q
python -m pytest tests\tools\test_visual_tools.py tests\tools\test_api_route_contracts.py -q
python -m tools.visual_smoke --roles admin,leader,r3 --output artifacts\visual\business-scope
python -m tools.visual_smoke --via-desktop-proxy --roles admin,r3 --output artifacts\visual\business-scope-desktop
```

`test_business_scope.py` ska skapa data i båda verksamheterna och täcka många
användare, listfilter, främmande id, korsverksamhetswrites, dubbletter per
verksamhet, Super User-create, settings per verksamhet och public API-defaults.
`test_persons_view.py` ska skydda att Personer-vyn skickar `area_id` och laddar
om vid områdesfokus, så Super User inte kan se Stigamo-personer när fokus står
på R3. `test_visual_tools.py` ska skydda dynamisk area focus, R3-toggle,
Super User-`∞`, Verksamheter-vyn med omraden samt verksamhetsfält i Personer,
Aktiviteter och Användare.

Vanliga varianter:

```powershell
python -m tools.interactive_e2e --headful
python -m tools.interactive_e2e --base-url http://127.0.0.1:8000 --output artifacts\interactive\manual
```

Nar verktyget faller ska agenten oppna screenshoten narmast felet och lasa
`report.json` for att se sista lyckade steg.

## Visuella Windows-skalbilder

Verktyg:

```powershell
python -m tools.desktop_shell_screens
```

Det skapar screenshots under `artifacts/desktop-shell/`:

- `desktop-loading.png`
- `desktop-error.png`
- `desktop-loaded-shell.png`

De bilderna visar desktop-specifika tillstand. Sjalva bemanningsvyerna testas
med `tools.visual_smoke`, eftersom Windows-appen använder samma frontendkod som
webben men servar den lokalt.

## Desktop-app-probe

Verktyg:

```powershell
python -m tools.desktop_app_probe
```

Detta testar Windows-appens PyQt-skal mot en riktig lokal testserver utan att
krava att Qt WebEngine kan rendera i en headless agent-session. Det verifierar
att desktop-skalet:

- visar laddning
- visar anslutningsfel
- laddar den lokala appytan nar central server ar frisk
- sparar `report.json` och screenshots under `artifacts/desktop-app/<timestamp>/`

Pa en maskin dar Qt WebEngine kan rendera kan agenten aven kora:

```powershell
python -m tools.desktop_app_probe --real-webengine
```

Om `--real-webengine` misslyckas i en agentmiljo ska det rapporteras tydligt,
men det blockerar inte de vanliga webbarbetsflodena. Anvand da:

1. `python -m tools.interactive_e2e` for alla webbfloden.
2. `python -m tools.desktop_app_probe` for Windows-skalet.
3. En manuell Windows-korning om felet specifikt verkar handla om WebEngine.

## Testdata for visuella tester

`tools.visual_data` lagger in:

- admin, arbetsledare, Bemanningsansvarig, visningsroll och Lagerkontorist
- personer i flera områden
- veckomallar med ledig helg
- schemaceller med heldagar och halvtimmar
- auditlogg for Historik

Verktyget ska bara koras mot en lokal eller temporar databas. `tools.visual_smoke`
gor detta automatiskt.

## Nar nagot ser fel ut

1. Spara screenshot-mappen som bevis.
2. Ange filnamn, viewport och roll fran `summary.json`.
3. Beskriv faktisk vy och onskat lage.
4. Korrigera kod.
5. Kor snabbtesterna igen.
6. Kor om relevant screenshot-urval, till exempel:

```powershell
python -m tools.visual_smoke --roles admin --output artifacts\visual\recheck
```

## Releasekontroll

Innan ny release:

1. `python -m pytest`
2. JS-syntaxkontroll
3. `python desktop\main.py --smoke-test`
4. `python -m tools.visual_smoke --roles public,admin,leader,staffing,viewer`
   Kor ocksa `python -m tools.visual_smoke --via-desktop-proxy --roles admin,warehouse`
   nar Lager/Allokering, sidebar, filuppladdning eller desktop-appytan har andrats.
5. `python -m pytest tests\services\test_warehouse_tools_local_data.py`
6. `python -m tools.interactive_e2e`
7. `python -m tools.desktop_shell_screens`
8. `python -m tools.desktop_app_probe`
9. `cmd /c build_windows.bat`
10. Skapa och pusha release-tagg enligt `RELEASE.md`.

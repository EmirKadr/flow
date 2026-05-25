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

## Hemligheter, commits och pushar

`AGENTS.md` ska vara kvar i git. Den ar till for att framtida agenter och
utvecklare ska se reglerna innan de gor commits. Att gitignora den vore
overdrivet och skulle gora skyddet svagare. Skriv reglerna generiskt; lagg aldrig
riktiga nycklar, privata URL:er, headernamn, endpointmallar, kataloginnehall eller
kund-/lagerdata i `AGENTS.md`.

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
- `.env.example`, README, wiki och `render.yaml` far bara innehalla tomma eller
  generiska variabelnamn och `sync: false` for hemligheter. De far inte innehalla
  riktiga varden eller leverantorens privata API-kontrakt.
- Backend ska lasa privata anslutningsdetaljer fran miljo variabler eller
  driftens secret store. Frontend far aldrig prata direkt med privata externa API:er.
- Privata dataunderlag ska vara ignorerade i git. En genererad katalog far
  commitas om Emir uttryckligen bedomer att vy-/kolumnnamnen inte ar hemliga,
  som `data/external_data_catalog.json` for Hämta data. Katalogen far aldrig
  innehalla nycklar, URL:er, headernamn, endpointmallar eller rad-/kunddata.
- Om en hemlighet redan har blivit staged: avbryt committen, unstagea filen och
  flytta vardet till `.env` eller Render/secret store.
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
- Render-/serverdrift, deployment och backend-infrastruktur
- andra rent plattformsspecifika detaljer som inte motsvarar en anvandarfunktion

Om du tror att nagot annat maste vara olika mellan klienterna ska det ses som ett
blockerande beslut och inte antas tyst.

## Arbetsregel for agenter

Vid varje andring som paverkar produktbeteende ska agenten:

- aktivt kontrollera bada klienterna
- uppdatera bada sidor i samma arbetsinsats nar paritet kravs
- uppdatera tester och dokumentation nar det ar relevant
- tydligt saga till om full paritet inte hanns med eller om nagot blockerar den

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

Backend-audit och frontendens dokumentlogg ar olika saker. Audit ar sparad
historik for felsokning och uppfoljning. Dokumentloggen ar anvandarnara feedback
i aktuell browser/session. Nar ett flode paverkar anvandaren ska bada anvandas
om bada perspektiven ar relevanta.

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

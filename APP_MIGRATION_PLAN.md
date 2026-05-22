# App-migrering: risker, nulage och plan

Målet är att bygga flow som en riktig app, jämföra den mot hemsidan medan
allt fortfarande använder samma centrala API/databas, och först därefter ändra
hemsidan. Hemsidan ska alltså vara facit under övergången.

## Princip

- App och hemsida ska använda samma backend, samma PostgreSQL och samma
  endpoints tills vi aktivt beslutar något annat.
- Windows-appen ska inte längre vara beroende av att rendera
  `https://stigamo.nu` som sida. Den ska köra en lokal app-yta och prata med
  den centrala servern via API.
- All gemensam sanning ligger kvar centralt: användare, roller, schema,
  personer, aktiviteter, historik, inställningar och KPI-mål.
- Verksamhet är ny isoleringsnivå ovanför område. Webben och Windows-appen ska
  alltid få samma verksamhetsscope från API:t; en Stigamo-användare ska inte se
  R3 och tvärtom.
- Stora produktivitetsloggar är lokala i klienten tills vi bygger planerad
  API-hämtning/import.
- Ingen riskfylld funktion får tas bort för att appen byggs om. Om appen och
  hemsidan beter sig olika ska vi stoppa och jämföra mot denna fil.

## Saker i risk: exakt nulage att skydda

### Inloggning, session och roller

- `/api/auth/login` loggar in aktiva användare och lägger `user_id` i sessionen.
- Användare utan lösenord måste först gå igenom lösenordssättning.
- `/api/auth/me` används av varje sida för att rita sidebar, rollstyrning och
  rätt användarnamn. Svaret innehåller också `business_id`, verksamhetskod och
  verksamhetsnamn.
- Icke-Super Users, inklusive admins, är låsta till sin egen verksamhet i API
  och vyer. Försök att komma åt främmande verksamhets id ska nekas utan att
  avslöja datan.
- Super User kan se alla verksamheter och använder `∞` som globalt läge, men
  måste välja verksamhet vid skapande/import när den inte kan härledas.
- `viewer` får läsa schema/översikt men inte ändra.
- `leader` får ändra planering men får inte gå in i adminhistorik/användare.
- `admin` får administrera vanliga objekt.
- `super_user` krävs för produktivitet och auditlogg.
- Om API svarar `401` skickas användaren till `login.html`.
- Om API svarar `403 password_setup_required` skickas användaren till
  `set-password.html`.

Extra test senare: logga in som admin, leader, viewer och super_user i både
hemsida och app. Kontrollera att varje roll ser samma menyer och nekas samma
sidor.

Extra verksamhetstest: logga in som Stigamo-admin och R3-admin och verifiera att
toggle, register, schema, översikt, historik och settings bara visar respektive
verksamhet. Logga sedan in som Super User och verifiera globalt `∞` samt filter
per verksamhet.

### Sidebar, tema och datum

- Sidebar ritas av `common.js` på alla sidor.
- Sidebar cacheas i `sessionStorage` som `flow-sidebar-user` för att slippa
  blink när man byter vy.
- Tema sparas i `localStorage` som `flow-theme`.
- Sidebar collapse sparas i `localStorage` som `sidebar-collapsed`.
- Valt datum i Bemanning/Oversikt sparas i `sessionStorage` som
  `flow-selected-date`.
- Logout rensar sidebar-cache och skickar användaren till login.

Extra test senare: byt mellan alla vyer snabbt, växla ljust/mörkt tema,
collapsa sidebar, logga ut och logga in igen. App och hemsida ska kännas lika.

### Bemanning: dagsschema

- `GET /api/schedule` hämtar aktiva personer, explicita celler, schemalagda
  standardtider och låsflagga.
- Svaret är verksamhetsscopeat: vanliga användare får bara egen verksamhet,
  Super User kan filtrera med `business_id` eller se globalt `∞`.
- Timmar är 06-23.
- En cell kan vara hel timme `0-60` eller två halvor `0-30` och `30-60`.
- Om en person har fast schemamall visas mallens aktivitet även utan explicit
  cell.
- Om användaren tömmer en schemalagd malltimme skapas en explicit cell med
  `activity_id = null` och `empty_override = true`.
- Varje explicit cell har `version`; ändring skickar `expected_version`.
- Vid versionskrock returnerar API `409` med aktuella segment.
- Om inställningen `lock_foreign_schedule_cells` är aktiv får ledare inte
  ändra celler som en annan användare har fyllt. Admin kan passera låset.
- Split/merge går via `/api/schedule/cell/split` och validerar aktuell
  segmentsignatur.
- Drag, copy/paste och flera celler går via `/api/schedule/cells` med
  `atomic=true` för vissa flöden.
- Undo/redo återställer timmar via `/api/schedule/hours/restore`.
- Kopiera dag/vecka går via `/api/schedule/copy`.
- Rensa går via `/api/schedule/clear`.
- Fill-from-left finns via `/api/schedule/fill-from-left`.
- Summering/kalkyl hämtas via `/api/schedule/summary` och räknar både explicita
  celler och kvarvarande malltider.

Extra test senare: helcell, halvcell, split/merge, drag över flera personer,
copy/paste, rensa, kopiera dag, undo/redo, konflikt mellan två sessioner och
låst cell skapad av annan användare.

### Översikt

- `GET /api/overview` visar vecka.
- `GET /api/overview/month` visar månad.
- Översikt räknar ihop explicita celler och kvarvarande malltider per dag.
- Dominant aktivitet visas om dagen inte är blandad.
- Blandad dag markeras som mixed.
- `POST /api/overview/day` sätter eller tömmer en hel dag på personens
  schematimmar.
- Om personen är timmis utan schemamall betraktas den som ledig i översikt och
  API stoppar hel-dagsändring.
- `POST /api/overview/days/bulk` används vid drag över flera dagar.
- Översiktens undo/redo använder också `/api/schedule/hours/restore`.

Extra test senare: veckovy, månadsvy, områdesfilter, ändra hel dag, dra över
flera dagar, timmis utan mall, undo/redo och jämför timmar mot Bemanning.

### Personer och veckomallar

- `GET /api/persons` kräver planeringsrätt och visar aktiva personer om inte
  `include_inactive=true`.
- Personer tillhör alltid en verksamhet. Vanliga användare skapar i egen
  verksamhet utan extra val; Super User måste välja eller låta området/aktivitet
  härleda verksamheten.
- Excelimport max 5 MB och matchar svenska/alternativa rubriker.
- Import skapar aktiva personer och standardkompetenser.
- Dubbletter i fil eller mot befintliga personer stoppar import.
- Borttagning är inaktivering, inte fysisk delete.
- Veckomall hämtas via `GET /api/persons/{id}/schedule`.
- Om person saknar egna mallrader visas standarddagar.
- Om person har någon egen mallrad blir saknade dagar lediga.
- Veckomallens tider måste ligga 06-24 och start < slut.

Extra test senare: importmall, import med dubblett, skapa person, ändra inline,
inaktivera, visa inaktiva, ändra veckomall, timmis utan fast schema.

### Aktiviteter och områden

- `GET /api/areas` och `GET /api/activities` kräver inloggning.
- Skapa/ändra/inaktivera kräver admin eller Super User med rätt vyåtkomst. Super User administrerar områden under Verksamheter-vyn.
- `DELETE /api/areas/{area_id}` hårdraderar tomma områden men inaktiverar områden som redan används av personer, aktiviteter eller användare.
- Områden och aktiviteter är unika per verksamhet, inte globalt. Samma kod eller
  namn kan återanvändas i Stigamo och R3.
- Aktivitetskod skapas automatiskt om den inte anges.
- Endast `super_user` får sätta/ändra aktivitetskod manuellt.
- Dubblettkod stoppas.
- Sammanfattningsaktivitet får inte skapa loop.
- Inaktivering är mjuk delete.

Extra test senare: skapa/ändra/inaktivera aktivitet, visa inaktiva, kod som
super_user, kod spärrad för vanlig admin, summary activity utan loop.

### Användare och inställningar

- `GET /api/users` kräver admin.
- Användarnamn är fortsatt globalt unikt, men användarlistan och områdeval är
  verksamhetsscopeade för alla som inte är Super User.
- Import kräver `super_user`, max 5 MB.
- Importerade användare utan lösenord får `must_change_password=true`.
- Skapa användare kan ske med eller utan lösenord.
- Rollerna är `admin`, `leader`, `viewer`.
- Det går inte att inaktivera eller nedgradera sista aktiva admin.
- Användarinställningar, sidebar-layout, vybehörigheter och cell-lås hämtas och
  sparas per verksamhet via `/api/settings`.

Extra test senare: skapa användare, skapa utan lösenord, lösenordssättning,
ändra roll, inaktivera, sista-admin-spärr, importmall/import.

### Historik/audit

- Historik kräver `super_user`.
- Listan kan filtreras på user, entity, action, entity_id och datumintervall.
- Summary visar total, senaste 24h, unika användare, topp användare/actions och
  entities.
- Muterande API-flöden loggar audit så långt de är byggda idag.

Extra test senare: gör ändringar i schema/person/aktivitet/användare och bekräfta
att de syns med rätt filter.

### Produktivitet

- Produktivitet kräver `super_user`.
- Plocklogg, translogg och pallastningslogg väljs lokalt i klienten.
- Dessa tre stora filer sparas inte centralt och skickas normalt inte till
  servern.
- Filerna identifieras via filnamn och kolumner.
- KPI-mål är permanent central sanning.
- `GET /api/productivity/targets` hämtar KPI-mål från servern.
- Om en KPI-fil laddas upp ersätter den gamla och gäller alla användare.
- Beräkning startar automatiskt när de tre lokala loggfilerna finns.
- Vald dag, dagen före och dagen efter förberäknas/cachas i klienten.
- Endast kolumner som används i beräkningen ska läsas i klienten.

Extra test senare: välj tre loggar, kontrollera att UI blir redo direkt,
byt dag fram/bak utan ny uppladdning, byt KPI-fil och bekräfta att den ligger
kvar efter omloggning/annan session.

### Desktop/Windows-app

- Före migreringen laddade Windows-appen `https://stigamo.nu` direkt i
  QWebEngine.
- Health check gick mot `/api/health`.
- Appens cookies/localStorage låg i QWebEngine persistent profile.
- Uppdatering kontrolleras via GitHub Releases.
- Windows-skalet visar loading, felvy och laddad vy.

Extra test senare: server nere, server uppe, login i app, starta om app och
kontrollera session/tema/sidebar, uppdateringsdialog, öppna i webbläsare.

## Genomförandeplan

### Fas 1: Lokalt appskal med central API-proxy

- Lägg till en lokal server i desktopappen som servar `app/frontend`.
- Proxy:a `/api/*` från den lokala servern till `SERVER_BASE_URL`.
- Strippa `Secure` på proxade session cookies så lokal app-origin kan lagra
  sessionen, men skicka själva API-trafiken vidare till Render över HTTPS.
- Låt health check fortsätta gå mot Render.
- Låt appen öppna lokal URL, inte `https://stigamo.nu`.
- Paketera frontendfilerna i PyInstaller.
- Uppdatera tester och dokumentation.

Klart när appen kan starta lokal app-yta, logga in mot central backend och
använda samma API som hemsidan.

### Fas 2: Paritetstest mot hemsidan

- Kör automatiska tester.
- Kör webbscreenshots med `tools.visual_smoke`.
- Kör interaktivt E2E på webben.
- Kör desktop-probe mot lokalt appskal.
- Manuellt jämför de riskflöden som står ovan.

Klart när app och hemsida ger samma resultat på samma databas.

### Fas 3: Produktivitet och lokal filhantering

- Behåll lokal filhantering för stora loggar.
- Säkerställ att appen inte skickar plock/trans/pall till Render.
- Mät att dagbyte använder cache.
- Om lokal sökväg behövs senare: lägg Qt-brygga för filval så appen kan läsa
  sökväg direkt, men låt hemsidan fortsätta använda browser File-objekt.

Klart när produktivitet känns lika snabb i appen som i lokal webview och inte
orsakar Render memory-spikar.

### Fas 4: Framtida planerad API-hämtning

- Bygg import som separat backend-jobb eller worker, inte i användarens request.
- Hämta färskdata på schema, till exempel var 5:e eller 30:e minut.
- Läs in ny snapshot i staging-tabeller/filer.
- Validera komplett dataset innan gammal aktiv sanning ersätts.
- Byt aktiv snapshot atomiskt.
- Behåll senaste fungerande snapshot om API-hämtning misslyckas.
- Exponera importstatus i appen: senaste lyckade hämtning, fel och antal rader.

Klart när användaren inte behöver välja stora filer alls och gammal data aldrig
raderas innan ny data är validerad.

### Fas 5: Hemsidan efter appen

- När appen är testad mot hemsidan kan hemsidan få samma förbättringar.
- Om appen blir primär kan hemsidan behållas som admin/fallback.
- Om hemsidan tas bort publikt måste API:t ändå ligga kvar centralt.

## Stopplista

Vi ska inte gå vidare till nästa fas om något av detta händer:

- App och hemsida visar olika schema för samma datum/användare.
- Rollstyrning skiljer sig.
- Viewer kan ändra data.
- Produktivitet skickar stora loggar till Render av misstag.
- KPI-mål blir lokal istället för central sanning.
- Undo/redo eller versionskonflikter beter sig olika.
- En import ersätter gammal sanning innan ny data är validerad.

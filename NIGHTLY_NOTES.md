# Nattpass-anteckningar

Arbetslogg för OVERNIGHT_PLAN.md. Nyaste passet överst.

## Pass 2026-07-06 (branch feature/nightly-quality-20260706)

### PASS 3, morgonen 2026-07-07 ("kör igen")

**Klart och pushat:**
- Uppgift 8 påbörjad med värsta mörka hörnet: routers/bulk.py (12 % →
  täckt). Fem kontraktstester för copy/clear/fill-from-left inkl. audit,
  overwrite-semantik och scope. Nästa mörka hörn i tur:
  routers/overview.py (27 %), assistant_tools/core_tools.py (38 %),
  allocation_bridge_parts/export.py (45 %).
- Uppgift 5.2 avklarad snabbare än väntat: svep visade att ikonknappar
  redan får title+aria-label dynamiskt (theme/area_focus/zoom). Enda
  luckan (tematogglens tomma initialläge) fixad.
- Uppgift 3A MEDVETET SKIPPAD lokalt: benchmark mot syntetisk lokal data
  ger inte meningsfulla medianer mot budgetarna (de är satta för
  driftmiljön). Kör i stället api_benchmark mot flow-development enligt
  DEPLOY.md-rutinen när du är inloggad — eller låt nästa nattpass göra
  N+1-jakten statiskt per endpoint.

**Kvarvarande topp-3:** overview.py-tester, stale-while-revalidate-piloten
(3C), @ts-check (48 filer kvar).

### PASS 2, morgonen 2026-07-07 ("gör det nu")

**Klart och pushat (4 commits till, totalt 18):**
- Buggrapportören FÄRDIG: browsertest för consent-gaten och hela flödet
  (Avbryt = aldrig inspelning; OK → inspelning → skicka → uppspelning i
  admin-vyn med rrweb-iframe) + desktop-smoke exit 0.
- Uppgift 3E KLAR: trace-cachen tvåskiktad (L1 processminne + gzip-JSON
  disk-spill under media-roten). Workers-blockeraren borta — medvetet
  disk i stället för DB (hundratals MB hör inte hemma i MSSQL), tokens
  path-valideras. Kontraktstest simulerar processbyte. Workers förblir 1.
- @ts-check: 26 → 34 av 82 (allocation- och schedule-batchar). Fynd:
  nummer-till-.value-tilldelningar, otypade drag&drop-kedjor.

**Kvar (prioritetsordning för nästa pass):**
1. Uppgift 3 A/B/C/D: benchmark-körning, N+1/index-jakt,
   stale-while-revalidate-pilot, spinner-svep. (3E är klar.)
2. @ts-check: 48 filer kvar.
3. Uppgift 5 (a11y/mobil), 6 (UX-svep), 8-10 (coverage/Hypothesis/JS-harness).
4. Uppgift 12-analyserna (MCP-server, Sankey-minnesbudget, mutationstestning).

### SAMMANFATTNING AV PASSET (skrivet vid avslut, natt mot 2026-07-07)

**Klart och pushat (13 commits, hela icke-browser-sviten grön i pre-push):**
1. **Uppgift 1 KLAR** — apphjälpen 30→~45 tools: 6 Historik/fel + 4
   produktivitet + finance_summary (med refaktor av business-summary-
   endpointen till delad byggare) + 3 schema-analys + 2 systemstatus.
   Alla med egna servicetester och wiki-uppdateringar.
2. **Uppgift 2 DELVIS** — @ts-check: 4→26 av 82 filer (hela js/common/ +
   10 sidfiler). Alla fynd fixade utan beteendeändring.
3. **Uppgift 4 KLAR** — säkerhetsheaders på alla svar, rate limit på
   login (fönster per användarnamn+IP, auditloggad), cookieflaggor
   kontraktstestade, CSP-stegplan nedan.
4. **Uppgift 7 KLAR (backend+frontend)** — Buggrapportören: 🐞-knapp →
   consent → 30 s rrweb-inspelning → POST med skyddsräcken → vyn
   Buggrapporter med uppspelning + status. Experiment, beslut 2026-08-07.

**Återstår till nästa pass (i prioritetsordning):**
- Buggrapportören: Playwright-test för consent-flödet ("ingen inspelning
  utan OK" är servicetestat men inte browsertestat) + desktop-smoke
  (knappen bör verifieras i PyQt-skalet: python desktop/main.py --smoke-test).
- Uppgift 3 (prestanda): inget påbörjat — benchmark först, sedan
  stale-while-revalidate-pilot och trace-cache→DB. Bra huvudjobb nästa natt.
- Uppgift 2: 56 filer kvar utan @ts-check (fortsätt minsta först;
  overview.js kräver namnrymdsflytt — ta sist).
- Uppgifterna 5, 6, 8, 9, 10 (a11y/mobil, UX-svep, coverage, Hypothesis,
  JS-harness): ej påbörjade.
- MERGE-BESLUT ÅT EMIR: branchen är feature/nightly-quality-20260706;
  inget har mergats till main eller release/* — det är ditt beslut på
  morgonen. Migration 0047 ingår (kör automatiskt vid appstart).


### Beslut och avvikelser

- **Ekonomi-tools, medvetet strukna ur batchen** (uppgift 1): planen föreslog
  fyra ekonomi-tools men bara `finance_summary` byggdes. Skäl:
  - `finance_process_breakdown` och `staffing_cost_summary`: pengamatten
    ligger djupt i produktivitetsrapportens cellstruktur
    (`_finance_for_productivity_cell` per tidscell). En egen aggregering vid
    sidan av skulle bli en andra sanning om pengar — mot planens regel.
    `finance_summary` återanvänder i stället hela den befintliga beräkningen
    via nya `build_business_summary_payload` (utbruten ur endpointen, delad).
  - `calc_vs_actual` (kalkyl mot faktisk bemanning): kräver förståelse av
    `StaffingCalculatorProfile`-semantiken och hur kalkylen mappar mot
    schema-celler. Osäkert underlag kl 22 — hellre stryka än gissa.
    FÖRSLAG till Emir: bygg den som deklarativ backend-funktion med egna
    tester först, sedan tool ovanpå.
- **Superuser-scope i error_trend**: super user utan verksamhetsfilter ser
  globalt (visible_business_id=None). Första testantagandet var fel; testet
  rättat, beteendet är dokumenterat och avsiktligt.

### Klart

- Uppgift 1 batch 1: 6 Historik/fel-tools + tester (commit ea58626-ish).
- Uppgift 1 batch 2: 4 produktivitets-tools + tester.
- Uppgift 1 batch 3: finance_summary + refaktor av
  /productivity/overview/business-summary till delad
  build_business_summary_payload + tester (94 produktivitets-/finanstester gröna).
- **sankey_inbound_summary struken**: load_sankey_inbound_payload är den dokumenterade OOM-vägen utan arkiv-cache; det finns ingen garanterat billig summeringsväg idag. FÖRSLAG: bygg aggregat i arkiv-cachen först.

### CSP-analys (uppgift 4, punkt 4 — endast analys)

Frontendens HTML-sidor använder inline `<script>`-block (bl.a. sidinit) och
inline-styles, så en enforcing CSP kräver antingen nonce-stämpling i
Docker-byggets stamp_asset_versions-steg (naturlig plats — den skriver redan
om taggarna) eller flytt av inline-koden till filer. Rekommendation:
1) börja med `Content-Security-Policy-Report-Only: default-src 'self';
img-src 'self' data:; style-src 'self' 'unsafe-inline'` + rapport-endpoint,
2) inventera träffarna i Historik, 3) nonce-stämpla script-taggar i bygget,
4) slå på enforcing. Uppskattning: en egen kväll. INTE gjort i natt —
fel CSP släcker appen.

### Avvikelse: uppgiftsordning

Uppgift 3 (prestanda) sköts efter uppgift 4 (säkerhet) och 7 (buggrapportör):
säkerhetshålen var verifierade och små att täppa, och buggrapportören är
nattens huvudleverans. Prestandan kräver benchmark-servrar och är bättre som
nästa natts huvudjobb.

## PASS 4, 2026-07-07 ("kör igenom alla 100")

### Uppgift 12: analyser (endast skisser — inga beslut fattade åt Emir)

**A. Exponera tool-registret som MCP-server.** Genomförbart med måttlig
insats: registret (assistant_tools) är redan providerneutralt med JSON-
schemadeklarationer. Skiss: ny endpoint-familj /api/mcp-server/* som talar
MCP:s JSON-RPC (tools/list, tools/call) och mappar 1:1 mot
allowed_tools_for(user). Kritiska frågor före bygge: (1) auth — session-
cookien fungerar inte för externa klienter; kräver PAT-tokens (ny tabell,
revokerbara, scopade till användare) — egen säkerhetsdesign; (2) enforcement
måste vara PÅ för MCP-klienter oavsett ASSISTANT_TOOLS_ENFORCE_VIEW_ACCESS;
(3) rate limiting per token. Uppskattning: 2-3 kvällar. Rekommendation:
vänta tills apphjälps-toolsen passerat sitt beslutsdatum 2026-08-01.

**B. Sankey-minnesbudget.** Arkiv-cachen (påslagen i prod 2026-07-04) har
avlastat OOM-vägen; kvarvarande risk är kallstart/cache-miss på månads-/
årsvyer. Skiss: räknare i sankey_inbound/fetch.py som avbryter hämtningen
med begripligt 413-fel när radantalet passerar tak (setting, t.ex. 2M rader)
i stället för att podden OOM-dödas. Litet ingrepp (~50 rader + test).
Rekommendation: värt att göra nästa kodpass.

**C. Mutationstestning på engine_core.** mutmut kräver POSIX-miljö för full
effekt; på Windows/CI är cosmic-ray alternativet. Nyttan: golden- och
property-testerna för motorn är redan starka — mutationstestning skulle
främst bekräfta det. Rekommendation: lågprio; kör som engångsanalys i CI
(ubuntu-runner, nattligt manuellt trigger-jobb) om nyfikenheten finns.

### Kvarvarande efter pass 4 (ärlig restlista)

- Uppgift 3B/C/D: N+1-jakt (kräver driftbenchmark först),
  stale-while-revalidate-piloten, spinner-svepet. Största kvarvarande posten.
- Uppgift 5.1/5.3/5.4: tangentbordssvep av dialoger, WCAG-kontrastkontroll,
  mobilviewport-svep. (5.2 ikonknappar: klar — läget var redan bra.)
- Uppgift 6.1/6.2/6.3: felmeddelande-svep, tomma lägen-svep, djup
  desktop-paritetsgenomgång. (6.4 label-editor beslutsdatum: klar.)
- Namnrymdsflytt för de 9 sista @ts-check-filerna (overview.js + 8
  kolliderande sidfiler).
- Historik-vyn (analytics.js, 36 fel) ingick i de reverterade.

## PASS 5, 2026-07-07 (Emirs tre svar: benchmark klar, ja+ja, release sist)

### Klart och pushat

- **3B KLAR**: Emirs baslinje analyserad (overview 970 ms, schedule 765 ms,
  summary 631 ms). Empirisk frågeräkning med 30 seedade personer: INGEN N+1
  existerar — tyngsta endpointen kör konstant 10 frågor; latensen är
  rundresor × Azure-latens. Leverans: test_query_count_budgets.py (låser
  frågeantal per endpoint, spränger vid framtida N+1) + latensbudgetar
  åtdragna till 60-80 % marginal över uppmätta medianer.
- **3C KLAR**: SWR-piloten live på Personer + Översikt. Nya
  js/common/api_swr.js (api.js slog i radtaket → split med typeof-guards;
  splitten tog först clearApiGetCache med sig av misstag — fångat av
  browsertest + felsökning, återställt). Browsertest: API:et helt nedsläckt
  → båda sidorna renderar ändå från snapshot; POST rensar snapshots.
  Fyra källsträngskontrakt uppdaterade (persons_view ×3, visual_tools ×1).

### ÅTERSTÅR till sista passet (kör i FÄRSK session: "kör igen")

1. **Namnrymdsflytten (Emirs JA)**: 9 filer. VARNING till nästa pass:
   schedule/state.js delar toppnivåtillstånd med hela schedule/-katalogen
   och persons-sidan är en trio (persons/persons_table/persons_productivity)
   med delade globaler — kartlägg VILKA symboler som delas per sida innan
   någon rename (grep varje kolliderande symbol över sidans script-lista
   i HTML:en). Standalone-sidorna (businesses, meta, users, activities,
   analytics) är enklast — börja där. overview_state/overview sist.
2. **Svepen**: 5.1 tangentbord i dialoger, 5.3 WCAG-kontrast, 5.4
   mobilviewport, 6.1 felmeddelanden, 6.2 tomma lägen, 3D spinnersvep.
3. **SIST (Emirs ordning)**: release — NÄSTA LEDIGA sekvens (28.4 och 28.5
   är redan tagna på origin → release/2026.28.6 eller 2026.29.x beroende på
   vecka), mergea feature-branchen dit, EGEN push av release-refen,
   verifiera `gh run list --workflow=flow-docker.yml`, därefter merga
   release → main och pusha main separat.

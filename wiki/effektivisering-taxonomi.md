---
title: Effektiviseringar - taxonomi over vara missar och vara losningar
status: aktiv
updated: 2026-07-14
tags: [prestanda, retrospektiv, taxonomi, guardrail, arkitektur, larande]
---

# Effektiviseringar: vilka missar vi gjorde och vad som faktiskt fixade dem

Kort svar: vi har gjort **476 belagda effektiviserande andringar**, varav 86 med
uppmatt vinst. Nastan ingen av dem ar ett algoritmiskt genombrott. Nastan alla ar
**placeringsoptimeringar** - arbetet var ratt, men det lag pa fel *lager*, vid fel
*tidpunkt*, i fel *granularitet* eller med fel *frekvens*. Och den vanligaste
"losningen" i materialet ar inte en optimering alls: det ar en **guardrail** som
gor om-misstaget omojligt.

Den har sidan ar meta-nivan ovanfor
[Prestandaoptimeringar](prestanda-optimeringar.md). Den sidan ar en *monsterkatalog
for latens* (A1-E3, med grep-signaturer). Den har sidan svarar pa den storre fragan:
**vilken sorts misstag ar vi benagna att gora, och vilken sorts fix loser dem?**
Den tacker alla fyra som tjanar tid, inte bara slutanvandaren.

## Underlaget

Kartlagt 2026-07-14 med 15 parallella lasare over wiki, hela git-historiken,
incidenter, guardrails, UX-floden, verktyg, CI, desktop, LLM-lagret, migrationer
och koden sjalv. 476 poster, klassade pa feltyp och losningstyp.

**Vem tjanade tiden:**

| Formansstagare | Poster |
| --- | --- |
| Slutanvandaren | 229 |
| Utvecklare/agent | 93 |
| Systemstabilitet (appen slutade do) | 82 |
| Drift | 72 |

Att bara 48 % av vinsterna gar till slutanvandaren ar viktigt: halften av arbetet
handlar om att *vi* ska kunna rora oss snabbare och att appen ska sluta ramla.

## De fem sorters optimeringar vi faktiskt gor

Nastan allt vi kallar "optimering" ar en av dessa fem. Ingen av dem andrar vilken
data anvandaren ser - de ar **beteendebevarande**.

1. **Flytta arbetet till ratt lager.** Samma arbete, annan plats. Python -> SQL
   (`interaction_coverage`, 3910 ms -> 173 ms). Webprocess -> trad/worker
   (blocking-in-async). Databas -> fillager (blobbarna ur `meta_media_uploads`).
   Server -> browser (Meta laddar ner originalet i stallet for att ffmpeg-transkoda).
   Server -> klient (sok/sortering klient-side, 0 API-anrop).
2. **Flytta arbetet till ratt tidpunkt.** Samma arbete, men inte medan anvandaren
   vantar. Forbygg dagens produktivitet var 30:e minut i stallet for on-demand kl 05.
   Prefetch under idle. Backfill i bakgrunden.
3. **Flytta arbetet till ratt granularitet.** En rundresa per mal -> en batch.
   Bemannings drag-fyll: 200 mal x 37 ms -> ett anrop. Personliga schemat:
   N x 63 queries -> 3.
4. **Flytta arbetet till ratt frekvens.** Rakna en gang i stallet for varje gang.
   `lru_cache` pa `_canonical_header` (~4M anrop -> nagra hundra, ~10 s -> 1,7 s).
   Hoista `build_package_ladders` ur loopen (upp till 512x farre byggen).
5. **Inte gora arbetet alls.** Den underskattade kategorin: 39 poster ar "onodigt
   arbete/dod kod" och 8 losningar ar bokstavligen *ta bort funktionen*.
   Etikettstillbilden (OOM-boven, anvandes inte). `pool_pre_ping` (-37 ms/request).
   Vendor-motorns Tkinter-GUI (4 100 rader). Playable-transkodningen i
   nedladdningsknappen.

En sjatte klass ar inte optimering av *arbetet* utan av *upplevelsen* av det:
SWR som malar cachad snapshot direkt, progressiva skal fore API-svaret, progress
med ETA i Meta-uppladdningen. Arbetet tar lika lang tid - vantan gor det inte.

## Misstagskatalogen: vad vi ar benagna att gora fel

Rankad efter antal poster.

### 1. Manuellt steg (89) - vi byggde funktionen men inte flodet runt den

Storst i antal, minst dramatisk. Funktionen fanns, men nagon manniska maste knuffa
den. En `Ladda upp`-knapp som inte behovdes (uppladdningen kan starta sjalv). Ingen
CLI, sa varje API-anrop kravde inloggning i browsern. Manuell release. Manuell
verifiering efter deploy. Manuell distribution av desktop-exe:n.

**Signatur:** finns det ett steg dar en manniska bara *bekraftar* nagot systemet
redan vet? Da ar det ett manuellt steg.

### 2. Omrakning och saknad cache (81) - vi raknade om samma sak

Samma varde berakades per rad, per anrop eller per vy trots oforandrat indata.
Osynligt tills datat vaxte. `_canonical_header` kanoniserade om samma handfull
kolumnnamn ~4 miljoner ganger per bygge.

### 3. Konfig-antagande (49) - vi arvde en default som var fel i **var** topologi

**Den farligaste klassen.** Det ar den enda som gav skarpa produktionsincidenter,
och varje enskilt fall var "ratt" enligt dokumentationen och fel i just var
cgroup/podd/gateway:

- ffmpeg anvander alla karnor som default -> grupp-OOM dodade hela podden (2026-07-09)
- `pool_pre_ping` ar pa som default -> 37 ms extra per request till Azure SQL
- Octopus-platshallaren `#{GEMINI_API_BASE_URL}` antogs alltid substituerad -> varje
  analys kraschade, och felet lackte API-nyckeln
- `DATA_SOURCE_API_BASE_URL` ar en multi-tenant-mall -> uppslag gick mot det
  bokstavliga vardnamnet `noeffectui-{tenant}...` och failade i DNS for *alla* pall-id
- probe-timeout default antogs racka i en CPU-strypt cgroup som kor subprocesser
- MSSQL-dialekt != dev-dialekt
- pytest-xdist kraschar pa Windows -> parallellisering bara i CI

**Signatur:** "det ar ju standardvardet". Standardvardet ar satt for nagon annans
maskin. Varje default som ror **minne, tradar, samtidighet, timeouts eller URL:er**
ar ett antagande tills du mater det i din egen miljo.

### 4. Fel lager (48) - vi lat fel komponent gora jobbet

Python gjorde databasens jobb (ladda-och-reducera). Webprocessen gjorde en workers
jobb (ffmpeg, pandas, externa hamtningar i `async def`). Databasen var fillager
(blobbar i `meta_media_uploads.data`). Servern gjorde browserns jobb (transkodning
fore nedladdning).

### 5. Ingen budget eller tak (39) - vi byggde obundna vagar

Ingen grans pa rader, minne, samtidighet, tokens, loopvarv eller inloggningsforsok.
**Nastan varje tak sattes efter en incident, inte fore.** `period=all` drog hela
tabellen. Sankey drog hela arkivet i minnet (132 -> 449+ MB pa 20 s -> OOM).
Login hade ingen rate limit. MCP hade ingen kontextbudget.

### 6. Ingen matning (27) - metamisstaget bakom alla andra

Vi visste inte att nagot var langsamt forran en anvandare klagade eller podden dog.
Det ar darfor `api_benchmark`, latensbudgetarna och fragebudget-kontrakten ar de
viktigaste sakerna pa hela listan: de gor de fem andra klasserna *synliga innan de
gor ont*.

### Svansen (16 N+1, 16 over-fetch, 11 radvis loop, 6 saknat index)

De klassiska larobokfelen ar forvanansvart **fa**. De ar valdokumenterade i
[Prestandaoptimeringar](prestanda-optimeringar.md) med grep-signaturer och greppas
numera bort systematiskt. Det ar inte dar var risk ligger.

## Losningskatalogen: vad som faktiskt fungerade

**Den enskilt vanligaste losningstypen ar `guardrail` - 63 av 476.** Det ar det mest
utmarkande draget i hela materialet, och det ar ovanligt moget. Vi fixar inte bara
buggen; vi bygger sparren som gor om-misstaget omojligt:

- **Fragebudget per endpoint** - en ny N+1 ger +30 queries och spranger taket i pre-push
- **Latensbudget** (`tools/latency_budgets.json`, exit 2 vid overtradelse)
- **Kontraktstest som laser `-threads`-flaggorna** pa ffmpeg - OOM-fixen kan inte
  reverteras av misstag
- **Modell/migration-paritet** - varje ORM-kolumn maste namnas i en migration
- **Radtak, formelinjektionssanering och nedladdningsko** pa exportvagarna
- **Golden-karakterisering** - bevisar att en optimering ar beteendebevarande

Utover guardrails ar receptet forvanansvart litet. Fem grepp tacker det mesta:

| Grepp | Nar | Exempel |
| --- | --- | --- |
| Flytta lagret | Arbetet gors av fel komponent | SQL `GROUP BY` (-96 %); `run_in_threadpool` |
| Batcha | En rundresa per mal | Bemannings drag-fyll (200 mal: 7,2 s sparat) |
| Memoisera/forbygg | Samma resultat raknas om | `lru_cache` (~6x); forbyggd `overview-report` |
| Vektorisera | Python-loop over pandas | Dispatchkontroll (-99 %, ~100x) |
| **Ta bort** | Kostnaden overstiger vardet | Stillbilden, `pool_pre_ping`, playable-transkodningen |

Tre mognadsdrag varda att namna:

- **Cache med signaturvakt, inte TTL.** `person_productivity_daily` och
  `overview-report` invalideras pa *innehallssignatur* (snapshot + schema), inte pa
  tid. Oforandrade dagar blir gratis no-ops; andrade dagar byggs om automatiskt
  (self-heal). Det ar strikt battre an en TTL-gissning.
- **Fallback framfor retry.** SSE faller tillbaka pa GET. Arkivet faller tillbaka
  pa live. ASK-uppslag som failar blir en osakerhetsanteckning, aldrig ett analysfel.
  Kill-switchen stanger av i stallet for att lata anropen fortsatta smalla.
- **Mat, gissa inte - och spara det negativa resultatet.** Ett andra cachelager i
  `_row_text` mattes **langsammare** (5,2 s -> 8,8 s) och reverterades. Att det star
  i wikin ar mer vardefullt an de flesta vinsterna: lardomen ar att nar hotspoten val
  ar memoiserad ar nasta lager ofta call-overhead, inte berakning.

## Vad materialet sager om oss

- **Nastan allt hande pa fem dagar (2026-07-03..08)**, utlost av *smarta*: OOM-doden
  i Sankey, buggrapport #1 (drag-kopiering 17 s -> 60 s/504), en wiki-push som tog
  2 h 17 min. Optimering var reaktiv, inte planerad.
- **Alla missar var osynliga i liten skala.** Varenda en blev ett problem forst nar
  rader/anvandare/videor vaxte. Det ar exakt darfor guardrails slar fixar: fixen
  loser dagens instans, sparren loser hela klassen.
- **Var farligaste kodrad ar en default vi inte skrev.** Fyra av vara skarpa
  incidenter kom fran ett arvt standardvarde, inte fran var egen logik.

## Oppna luckor (2026-07-14)

Fran kartlaggningen, inte atgardat:

- **CI cachar ingenting.** pip, npm och Playwright-browsers laddas ner fran noll i
  varje korning. Den storsta okravda vinsten i utvecklarloopen.
- **Excel-exporterna bygger hela arbetsboken i minnet** (openpyxl utan `write_only`,
  `data_fetch.py:520`, `meta_uploads_helpers.py:441`, `export.py:34`). Radtak anvands
  som skydd i stallet for streaming. Givet var OOM-historik ar det ett latent B2.
- **`wiki/test-strategi.md` ar en orphan** - saknas i `index.md` och i `log.md` trots
  att den ar kanonisk kalla for testsvitens design.
- **`migrate_postgres_to_mssql.py:31-52` har DB-losenord i klartext.** Verifierat
  2026-07-14: filen ar medvetet gitignorerad (`.gitignore:85`) och har **aldrig**
  funnits i git-historiken (`git log --all -S <losenord>` ar tom) - hemligheten har
  alltsa inte lackt till repot. Kvarvarande risk ar bara att klartexten ligger pa
  disk i en **OneDrive-synkad** projektmapp. Render-losenordet ar dott (driften
  avvecklad juli 2026); Azure-losenordet (`flow`@`tst-effect40`) kan fortfarande
  vara giltigt och bor roteras eller flyttas till miljovariabler.
- **Stadmigrationen for `label_image_*`** ligger kvar som TODO efter 2026-08-10, se
  [Meta-uppladdning](meta-upload.md).

## Kallor

- [Prestandaoptimeringar](prestanda-optimeringar.md) - monsterkatalogen med grep-signaturer
- [Prestanda - leveranslagret](prestanda-leveranslager.md) - gzip, immutable-cache, ETag, SWR
- [Lokal arkiv-cache (DuckDB)](local-archive-cache.md) - B2-fixen
- [Produktivitet](productivity.md) - forbygg + signaturvakt
- [Meta-uppladdning](meta-upload.md) - ffmpeg-incidenterna och konfig-antagandena
- [Logg](log.md) - kronologin 2026-07-03..14
- `../tools/api_benchmark.py`, `../tools/latency_budgets.json`
- `../tests/services/test_query_count_budgets.py`

---
title: Optimeringsplan - detaljbilaga (alla 52 verdikt + alla 49 tekniker)
status: aktiv
updated: 2026-07-14
tags: [prestanda, plan, detalj, verifierad, referens]
---

# Optimeringsplan: detaljbilaga

Fullstandig rådata bakom [optimeringsplan.md](optimeringsplan.md). Har ligger **varje**
kandidat med hela skeptikerns motivering, den justerade vinsten, exakt vilken matning
som ska koras, och vilka forutsattningar som maste hallas. Ingen information ar
bortklippt - det ar dit du gar nar du ska bygga en specifik post.

Kartlagt 2026-07-14: 10 kodsvep + 5 omvarldsagenter + 52 adversariella skeptiker.

**20 bekraftade · 17 osakra · 15 avfardade** (av 52 kandidater)

---

# BEKRAFTADE (20)

Skeptikern forsokte avfarda och misslyckades. Mekanismen ar verifierad i koden.

## #01 — Kärnfils-uppladdningen (coredata /files/raw) kör hela spara-vägen synkront på event-loopen

- **Plats:** `app/backend/routers/coredata.py:313-386`
- **Monster:** C1
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> `upload_coredata_file_raw` är `async def`. Efter att request-strömmen skrivits till temp-fil (`_save_raw_upload_temp`, rad 231-240, som dessutom gör blockerande `tmp.write(chunk)` per chunk) anropas **utan avlastning**: `save_coredata_file(...)` (coredata_service.py:339-372: `source_path.read_bytes()` av hela filen, `hashlib.sha256(data)` över samma bytes, blob-skrivning till `CoreDataFile.data` (LargeBinary), `remove_existing_coredata_files` + `_materialize_coredata_row` till disk), alternativt `_save_article_max_file` (coredata.py:195-212: `shutil.copyfile` + glob/unlink), och slutligen `_warm_coredata_caches` (rad 386 -> forecast_flows.warm_prepared_locations -> pandas-läsning av hela location-CSV:n). Wikin dokumenterar själv att dessa filer är stora: item ~9,5 MB, item_attribute ~15 MB (A3-exemplet i prestanda-optimeringar.md). Hela det arbetet — filläsning, sha256 av 15 MB, ODBC-blo…

**Foreslagen atgard:**

> Flytta blocket rad 345-360 (`_save_article_max_file` / `save_coredata_file`) samt `_warm_coredata_caches`-anropet på rad 386 till `await run_in_threadpool(...)`. Behåll `try/except CoreDataError` runt await:et så felmappningen till 400 bevaras. Obs: `save_coredata_file` tar request-sessionen `db` — kör den i **en** tråd sekventiellt (aldrig parallellt med annan användning av samma Session), precis som noteringen under C1 i wikin säger. `_save_raw_upload_temp` kan lämnas (chunk-loopen ger await-punkter) eller flyttas till aiofiles om man vill vara noggrann.

**Skeptikerns granskning:**

Jag försökte avfärda den och misslyckades på varje punkt.

(1) Koden gör vad som påstås. coredata.py:313 är `async def upload_coredata_file_raw`. Rad 346-360 anropar `_save_article_max_file(...)` / `save_coredata_file(...)` rakt av, rad 386 anropar `_warm_coredata_caches(...)` rakt av. Inga await, ingen avlastning. `grep -c "run_in_threadpool|to_thread" app/backend/routers/coredata.py` = 0.

(2) Arbetet är verkligt tungt. coredata_service.py:339 `data = source_path.read_bytes()`; :351 och :363 `hashlib.sha256(data).hexdigest()`; :352/:364 `row.data = data` (LargeBinary); :368 `db.flush()` = ODBC-blobinsert av hela filen mot MSSQL; :370-371 `remove_existing_coredata_files` + `_materialize_coredata_row` = disk-I/O. För location tillkommer forecast_flows.py: `_warm_coredata_caches` (coredata.py:215-228) anropar FÖRST `clear_prepared_location_cache()` och SEDAN `warm_prepared_locations()` -> `_read_prepared_locations` -> `prepare_locations(shared._read(Path(path)))`. Cachen är alltså garanterat kall — full pandas-parse körs varje gång, på event-loopen.

(3) Inte redan fixat. `git log --oneline -- app/backend/routers/coredata.py` visar ingen threadpool-commit. wiki/prestanda-optimeringar.md rad 230-233 och 323 listar C1-fixarna: allocation, meta_uploads, data_fetch, assistant (+ settings, audit_logs enligt grep). coredata.py saknas i listan. Mönstret är alltså etablerat, accepterat och tillämpat på 6 andra routrar — men inte här.

(4) "INTE mönstret om"-kriterierna slår INTE till. Datat behövs (filen ska sparas), men mängden är stor och obunden av användaren (wikins A3-exempel: item ~9,5 MB, item_attribute ~15 MB). Reduktionen går inte att uttrycka i SQL — det är inte en A1/A3-fråga utan en C1-avlastning. Det är inte en engångsbatch: uppladdning sker återkommande via allocation-vyn.

(5) Anropsvägen finns och är sekventiell. app/frontend/js/allocation/uploads_view.js:107 -> `api.postFile("/api/coredata/files/raw?...")`. `routeAllocationFiles` (rad 131-141) loopar `for (const file of dropped)` med `await uploadAllocationCoreDataFile(file)` — en drop av item + item_attribute + location ger TRE blockeringsfönster i rad, inte ett.

DÄR JAG UNDERKÄNNER SVEPAGENTENS VINSTPÅSTÅENDE: den skriver "övriga requests slutar frysa". Det är för generöst. Appen har CPU-limit 300m. En threadpool-tråd konkurrerar om samma CPU-kvot som event-loopen. Fixen konverterar en HÅRD frysning (loopen kan inte ens läsa av socketen eller skicka svar — även sync `def`-routes stallar i I/O-lagret) till CONTENTION (övriga requests går långsamt, men lever). Det är fortfarande en stor förbättring, men inte "noll påverkan". Svepagentens "1-5 s" är dessutom ogrundad gissning — jag vägrar skriva under på den siffran utan mätning.

Vägen är dessutom KALL (kandidaten medger det själv: het_vag = nej). Det sänker prioriteten. Men C1 är enligt wikin "störst systemeffekt" just för att en enda kall-men-tung request fryser alla andra — och det argumentet accepterades redan för meta_uploads (som också är en sällan-körd uppladdning). Konsekvens talar för att göra samma sak här.

Slutsats: kandidaten håller. Låg risk, liten insats, etablerat mönster, befintliga tester skyddar. Men vinsten är kvalitativ (samtidighet), inte kvantifierad — och jag kan inte kvantifiera den utan att mäta.

**Justerad vinst (granskarens, inte svepagentens):**

Kan INTE kvantifieras utan mätning — jag vägrar upprepa svepagentens "1-5 s". Vad jag kan säga med säkerhet: event-loopen blockeras idag under hela spara-vägen (read_bytes + 15 MB sha256 + ODBC-blobinsert + diskskrivning + för location även en garanterat kall pandas-parse). Under 300m CPU-limit tar enbart sha256 av 15 MB storleksordningen 150-300 ms; blobinserten är sannolikt den dominerande posten men är omätt. Uppskattat blockeringsfönster: hundratals ms till några sekunder per fil, gånger antal droppade filer (frontend laddar upp sekventiellt). Fixens vinst är att övriga requests går från FRYSTA till LÅNGSAMMA (inte till opåverkade — tråden konkurrerar om samma 300m CPU). Uppladdningen själv blir inte snabbare. Prioritet: modest, eftersom vägen är kall — men billig och konsekvent med 6 redan gjorda C1-fixar.

**Matning som ska bekrafta vinsten:**

tools/api_benchmark.py kan INTE mäta detta direkt — den gör bara GET (se `session.get(...)` på rad 46). Rätt mätning är ett samtidighetsexperiment i två delar:

1. BAKGRUNDSLAST: kör `python -m tools.api_benchmark --endpoints /api/coredata/files --samples 40` (billig GET, träffar samma router) mot en körande miljö, och spara rapporten som baseline-referens med --compare.
2. STÖRNING: medan benchmarken löper, POSTa en riktig item_attribute.csv (~15 MB) och en location.csv till `/api/coredata/files/raw?filename=...` via curl/requests.
3. AVLÄSNING: jämför **max** och **p95** för GET-endpointen med och utan samtidig upload, före vs efter fixen. Före fixen ska GET-latensen ha en tydlig spik som motsvarar uploadens varaktighet; efter fixen ska spiken krympa kraftigt (men inte försvinna — CPU-contention kvarstår). Median är fel mått här; det är svansen som är hela poängen.
4. KOMPLETTERANDE: tidsätt uploadens serverdel isolerat (t.ex. logga wall-clock runt rad 345-386) för att få den faktiska storleken på blockeringsfönstret — det är siffran som saknas idag och som avgör om detta är värt att bygga alls.

Om steg 4 visar ett blockeringsfönster < ~200 ms bör kandidaten nedgraderas till "ej värd insatsen".

**Forutsattningar innan bygge:**

Måste verifieras/hållas innan fixen byggs:

1. BETEENDEBEVARANDE — kritiska punkter:
   - `try/except CoreDataError` (rad 363) och `except Exception` (rad 374) måste ligga RUNT await:et, annars tappas felmappningen till 400 och `_audit_coredata_file(action="upload_failed")`.
   - `finally: temp_path.unlink(missing_ok=True)` (rad 361-362) måste fortsatt köra även när tråden kastar.
   - `_warm_coredata_caches` sväljer redan alla fel (`except Exception` + logger.warning, rad 227-228). Det beteendet får inte ändras när den flyttas till tråd.

2. SQLAlchemy-SESSION — den skarpaste risken. `save_coredata_file` tar request-bundna `db` (rad 358) och gör `db.flush()`. Sessionen får användas från EN tråd i taget, sekventiellt, aldrig parallellt (wikins egen notering, prestanda-optimeringar.md rad 234-235). Rutten är `async def` och gör inget annat DB-arbete samtidigt, så ett enkelt `await run_in_threadpool(...)` är säkert — men det måste vara ETT anrop, inte flera parallella. Även `_warm_coredata_caches(file_type, business_code, db)` tar `db` (den skickas vidare till `find_coredata_file(..., db=db)`), så den får INTE köras parallellt med spara-anropet — kör dem sekventiellt, gärna i samma threadpool-anrop.
   Notera också: `save_coredata_file` gör bara `flush()`, inte `commit()`. Committen sker i `_audit_coredata_file` -> `audit.log_and_commit` (rad 260) som ligger kvar på loopen. Den ordningen måste bevaras.

3. BEFINTLIGA TESTER SOM SKYDDAR (tests/services/test_coredata_service.py):
   - `test_coredata_router_saves_article_max_to_business_path` (rad 315) — täcker ARTICLE_MAX-grenen (rad 346-351).
   - `test_coredata_router_warms_location_cache_after_upload` (rad 337) — täcker att `_warm_coredata_caches` faktiskt körs efter upload (rad 386). Detta är det viktigaste skyddsnätet vid flytten.
   - `test_coredata_router_only_warms_location_cache` (rad 358) — täcker att warm INTE körs för andra filtyper (rad 216-217).
   - `test_coredata_postgres_row_becomes_source_of_truth` (rad 157), `test_coredata_postgres_replaces_same_type_only_for_business` (rad 216) — täcker `save_coredata_file`-grenen.
   Dessa kör mot routern och räcker som karakterisering. Ingen ny golden-karakterisering krävs, MEN: lägg till ett test som verifierar att ett `CoreDataError` från tråden fortfarande blir HTTP 400 + audit-post `upload_failed` — den vägen är den lättaste att bryta vid en threadpool-flytt och verkar inte täckas idag.

4. UTANFÖR SCOPE MEN UPPTÄCKT: `/api/desktop/sync/coredata` (uploads_view.js:99) är en andra väg in i samma spara-logik. Om den också är `async def` utan avlastning har den samma problem — bör kontrolleras separat, inte buntas in i denna fix.

---

## #02 — GZipMiddleware kör med compresslevel=9 (Starlettes default) på event-loopen — 124 ms CPU-frys per 2 MB-svar

- **Plats:** `app/backend/main.py:319`
- **Monster:** konfig-antagande
- **Het vag:** okänt · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> `app.add_middleware(GZipMiddleware, minimum_size=1024)` anger ingen `compresslevel`. Starlette 1.3.1:s default är **9** (verifierat: `inspect.signature(GZipMiddleware.__init__)` -> `compresslevel: int = 9`). Komprimeringen sker synkront i ASGI-middlewaren, alltså på event-loopen, för **varje** svar >1 kB — inklusive de tunga JSON-payloaderna (Sankey, översikt, produktivitet, data_fetch-rader). Nivå 9 är zlibs dyraste läge och ger nästan ingenting extra jämfört med 6. Detta är exakt taxonomins "farligaste klass": en ärvd default som rör CPU och som är fel i vår topologi (en worker, stora JSON-svar). Relaterat i samma kedja: `api_get_etag` (main.py:279-311) sha256:ar dessutom hela body:n på loopen för varje API-GET, vilket adderar ~10 ms per 5 MB.

**Foreslagen atgard:**

> `app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)`. Ett rad-byte. Lägg gärna ett kontraktstest i tests/services/test_http_delivery.py som låser nivån (guardrail, samma mönster som ffmpeg `-threads`-testet).

**Skeptikerns granskning:**

Mekanismen är verklig och verifierad av mig — men svepagentens motivering och siffror faller.

HÅLLER:
- main.py:319 är exakt `app.add_middleware(GZipMiddleware, minimum_size=1024)`, ingen compresslevel.
- Installerad starlette 1.3.1: `compresslevel: int = 9`. Jag läste källan till `GZipResponder.apply_compression` — den skriver till `gzip.GzipFile` INLINE i ASGI-send-vägen, ingen threadpool. Alltså äkta event-loop-blockering i en pod med 1 worker och CPU-limit 300m (som dessutom förlänger wall-clock genom throttling).
- `git log -S "compresslevel"` = 0 träffar. Inte fixat.
- Beteendebevarande: GZip adderas SIST = ytterst; `api_get_etag` (main.py:278-313) ligger innanför, så ETag sha256:as på OKOMPRIMERAD body och påverkas inte av nivåbytet. Befintliga tester (`tests/services/test_http_delivery.py:13,22,31,40`) asserterar bara `content-encoding == gzip` + mindre än rå body — nivå 6 klarar båda.

FALLER:
- Het-väg-påståendet är fel. "Sankey-/översikts-/produktivitetssvaren är flera MB och passerar middlewaren" stämmer inte: sankey och produktivitet är `text/event-stream` (routers/sankey.py, routers/productivity.py) och undantas av Starlette — kontraktstestat i test_http_delivery.py:40. Enligt wiki/optimeringsplan.md:88-91 är de appens TVÅ STÖRSTA JSON-svar (705 KiB) och de gzippas ALDRIG. De tyngsta payloaderna i påståendet rör alltså aldrig den kod som ska fixas.
- "data_fetch-rader" är redan bundna: data_fetch.py:192 `max(1, int(settings.DATA_SOURCE_MAX_ROWS or 1000))` — preview-JSON takas vid ~1000 rader. Benchmarkpayloaden (1,93 MB / 20k rader) är syntetisk och motsvarar inget känt gzippat svar i appen.
- "grep wiki = 0 träffar, alltså okänt" är FALSKT: wiki/optimeringsplan.md:28 och :67 samt wiki/log.md:28-29 innehåller redan exakt detta fynd med exakt samma siffror (124 -> 36 ms). Det är en redan dokumenterad, oåtgärdad planpost — inte ny evidens.
- Vinsten går inte att kvantifiera idag. wiki/optimeringsplan.md:40 (post 0.1) konstaterar själv: "api_benchmark mäter aldrig payloadstorlek — hela mönsterfamilj D (transport) har noll mätning idag."

Sidofynd (stärker fixen, ej nämnt): /api/data-fetch/export/{session_id} (data_fetch.py:843-861) returnerar en FileResponse med xlsx — redan zip-komprimerade bytes som gzippas om på nivå 9 med ~0 storleksvinst. Ren CPU-förlust, men kall väg.

Slutsats: jag bekräftar defekten och fixen (en rad, låg risk, beteendebevarande), men AVFÄRDAR vinstuppskattningen. Rätt sätt att sälja in den är "gratis borttagning av en ärvd, ogrundad CPU-default", inte "88 ms per svar".

**Justerad vinst (granskarens, inte svepagentens):**

Mekanism bekräftad, magnitud kraftigt nedskriven. Sveptalen skalar om till ca 45 ms sparad event-loop-CPU PER MB gzippad body (nivå 9 ~64 ms/MB vs nivå 6 ~18 ms/MB), mot +3 % payload. De påstådda 88 ms förutsätter ett 1,93 MB-svar som ingen har visat existerar — appens två största payloader (sankey/produktivitet, 705 KiB) är SSE och gzippas aldrig, och data_fetch är takat till 1000 rader. Realistiskt gzippade svar (/api/overview, /api/persons, openapi.json, statisk JS) är sannolikt tiotals till några hundra KB, vilket ger storleksordningen 1-15 ms sparad event-loop-tid per svar (möjligen 2-3x i wall-clock under 300m CPU-throttling). Jag kan INTE kvantifiera bättre än så utan att först mäta faktiska payloadstorlekar — den mätningen finns inte i repot idag. Vinsten är alltså liten men praktiskt taget gratis; motivera fixen som "ta bort en ogrundad ärvd default", inte med ett ms-tal.

**Matning som ska bekrafta vinsten:**

Tvåstegs, och steg 1 är obligatoriskt eftersom vinsten annars inte går att belägga:

1. PAYLOADMÄTNING FÖRST (= optimeringsplan-post 0.1, finns ej idag). Utöka tools/api_benchmark.py att registrera `content_length` + `content-encoding` per sample. Kör mot prod-lik data för de sex endpoints i tools/latency_budgets.json (/api/areas, /api/activities, /api/persons, /api/schedule, /api/schedule/summary, /api/overview?year=2026&week=27). Detta ger den enda siffra som avgör om fixen är värd något: den RÅA bodystorleken på det största gzippade svaret.

2. MIKROBENCHMARK PÅ RIKTIGA BYTES, inte syntetiska. Dumpa den råa (okomprimerade) body:n från /api/overview?year=2026&week=27 till fil och tidsätt `gzip.compress(body, 9)` vs `gzip.compress(body, 6)` på den exakta byten, N=20, median. Rapportera ms-delta OCH storleksdelta i procent. Det är den siffra som får citeras — svepets 1,93 MB-payload får inte återanvändas.

3. FÖRE/EFTER-BEKRÄFTELSE: `python -m tools.api_benchmark ... --budget tools/latency_budgets.json` mot samma miljö före och efter radbytet; median-ms för /api/overview (baslinje 970 ms, budget 1700) ska inte försämras och bör förbättras med mikrobenchmarkens delta. Förvänta dig att deltat DRUNKNAR i brus om payloaden är liten — det är i sig ett giltigt resultat och ska då redovisas som "ingen mätbar vinst, behåll ändå ändringen som korrekt default".

**Forutsattningar innan bygge:**

BETEENDEBEVARANDE: ja, och det är verifierat i koden, inte antaget.
- Middleware-ordning: GZip adderas sist (main.py:319) = ytterst; api_get_etag (main.py:278) ligger innanför och sha256:ar OKOMPRIMERAD body (main.py:297-298). Nivåbytet kan därför inte ändra någon ETag och kan inte orsaka felaktiga 304:or. Detta är den enda reella korrekthetsrisken och den är utesluten.
- gzip-ström på nivå 6 avkodas bit-identiskt av alla klienter; endast byte-storlek ändras.
- Desktop påverkas inte alls: desktop/local_app_server.py skickar `Accept-Encoding: identity` mot central server (wiki/architecture.md:24), så webviewen får ändå okomprimerat. Paritetsregeln webb/desktop är alltså inte i spel.

SKYDDANDE TESTER (befintliga, räcker):
- tests/services/test_http_delivery.py:13 (stor JSON gzippas), :22 (statisk JS gzippas), :31 (små svar gzippas ej), :40 (SSE lämnas orörd), :60/:70/:83 (ETag + 304 + stale-If-None-Match). Ingen av dem låser en byte-storlek eller en komprimeringsnivå, så nivå 6 passerar alla. Ingen golden-karakterisering behövs.

MÅSTE VERIFIERAS INNAN BYGGE:
1. Att det faktiskt FINNS ett gzippat svar värt att optimera (steg 1 i mätningen). Om största rå body är <100 KB är vinsten under brusnivån — bygg då fixen ändå som hygien, men skriv INTE in någon ms-vinst i loggen.
2. Att kandidaten inte förväxlas med den mycket större närliggande posten: SSE-strömmarna (sankey/produktivitet, 705 KiB -> 93 KiB) komprimeras ALDRIG (optimeringsplan.md:88-91). Där ligger den verkliga transportvinsten. Om någon bara har tid för en sak i leveranslagret är det den, inte den här.
3. Lägg till kontraktstestet som låser compresslevel=6 i tests/services/test_http_delivery.py (samma guardrail-mönster som ffmpeg -threads), annars återinförs Starlettes default vid nästa uppgradering.

DOKUMENTATION: fyndet är redan skrivet i wiki/optimeringsplan.md:67 och wiki/log.md:29 — uppdatera de posterna vid fix i stället för att skapa nya sidor, och korrigera samtidigt den felaktiga het-väg-motiveringen där.

---

## #03 — Alla tre Excel-importvägarna (aktiviteter, personer, användare) parsar och skriver på event-loopen

- **Plats:** `app/backend/routers/users.py:451-462 (samt persons.py:593-604, activities.py:686-697)`
- **Monster:** C1
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> Alla tre är `async def` som gör `content = await file.read()` (bra) och sedan anropar `parse_*_import_excel(content)` — openpyxl-parse av upp till `MAX_IMPORT_BYTES = 5 MB` xlsx — och därefter `_import_*_rows(...)` **synkront på loopen**. `_import_user_rows` (users.py:351-430) kör dessutom `_find_username_conflict(db, row.username)` **per rad** och `get_business_by_input(db, row.business)` per rad, plus `db.add`/`db.flush`/`audit.log` per rad. På dev-topologin (~37 ms/DB-rundresa enligt wikins mätning) betyder en import på 300 rader ~11 s DB-väntan **på event-loopen**, ovanpå openpyxl-parsen. `persons._import_person_rows` (persons.py:456-520) har cachade lookups men fortfarande `get_business_by_input` per rad. Notera att systerrutterna `/import-rows` är vanliga `def` — de körs i FastAPI:s threadpool och är alltså redan säkra. Asymmetrin visar att `async def` här är oavsiktlig.

**Foreslagen atgard:**

> Enklast och mest beteendebevarande: gör rutterna till vanliga `def` och läs filen med `file.file.read()` (FastAPI kör då hela rutten i threadpoolen, precis som `/import-rows` redan gör). Alternativt behåll `async def` och kör `rows, errors = await run_in_threadpool(parse_*_import_excel, content)` + `return await run_in_threadpool(_import_*_rows, ...)`. (Separat A2-uppföljning: batcha `_find_username_conflict`/`get_business_by_input` till en query över alla rader.)

**Skeptikerns granskning:**

Koden gör exakt vad som påstås. users.py:451 `async def import_users` → `content = await file.read()` (ok), sedan `parse_user_import_excel(content)` (users.py:460) och `_import_user_rows(...)` (users.py:461) — båda synkrona på loopen. `_import_user_rows` (users.py:365-423) kör per rad: `_find_username_conflict(db, ...)` (372), `get_business_by_input(db, ...)` (377), `resolve_write_business_id(db, ...)` (390), `db.add`+`db.flush` (408-409) och `audit.log(db, ...)` (411). Session är en synkron SQLAlchemy-Session → varje anrop är en blockerande DB-rundresa på event-loopen. Samma sak i activities.py:686-696 och persons.py (per-rad `get_business_by_input(db, row.business)` på persons.py:489, plus `_existing_person_names(db, ...)`/`_next_sort_order(db, ...)` per ny business_id på 502/511/521 — dock cachade per business, så persons är mildare). Grep: 0 träffar på run_in_threadpool/to_thread i alla tre filerna, medan allocation.py, meta_uploads.py, data_fetch.py, assistant.py och settings.py redan använder mönstret. Asymmetri-argumentet håller: `/import-rows`-tvillingarna (users.py:465, activities.py:700) är vanliga `def` och kör samma `_import_*_rows` i threadpoolen. Rutten är levande: frontenden anropar den (users.js:440, persons.js:60, activities.js:411 via `api.postForm`). Inte fixat: `git log -S "async def import_users"` ger bara ursprungscommiten 63b6f60. Ingen radgräns finns — bara MAX_IMPORT_BYTES (5 MB). Två avfärdanden prövade och förkastade: (a) "kall väg" avfärdar INTE C1 — wikin (prestanda-optimeringar.md:221-235) säger uttryckligen att C1:s skada är kollateral (en uvicorn-worker → tungt synkront arbete fryser ALLA requests), och de redan åtgärdade C1-exemplen (meta_uploads/ffprobe, assistant) är själva lågfrekventa rutter; (b) "engångsbatch" gäller A/B-mönstren, inte C1. MEN svepagentens siffror är uppblåsta, se justerad_vinst.

**Justerad vinst (granskarens, inte svepagentens):**

Jag kan INTE kvantifiera vinsten utan produktionsdata, och jag skär ned svepagentens siffror kraftigt. Två fel i deras uppskattning: (1) "openpyxl på 5 MB = flera sekunder CPU" är inte belagt — users.py:317 kör `load_workbook(..., read_only=True, data_only=True)`, dvs strömmande läge utan full cell-träd-materialisering, och en realistisk användar-/person-/aktivitetsimport är tiotals KB (några hundra rader), inte 5 MB. 5 MB-taket är ett skydd, inte ett typfall. Realistisk parse-kostnad: tiotals till ett par hundra ms. (2) "300 rader ≈ 11 s" bygger på wikins 37 ms RTT som är en DEV-topologisiffra; i prod ligger app och MSSQL i samma region (låg ensiffrig ms). Min egen uppskattning: ~3-5 DB-rundresor per rad → 300 rader × 4 × ~3 ms ≈ 3-4 s loopfrysning i värsta realistiska fall, typiskt (20-50 rader) 0,2-0,7 s. Vinsten för den importerande admin är NOLL (samma väggtid). Hela vinsten är att den frysningen försvinner från event-loopen, dvs svanslatens för samtidiga användare under en sällan förekommande adminoperation. Förväntat värde: modest, men insatsen är S och risken låg, och fixen följer ett mönster som redan är etablerat på fem andra ställen i repot. Bonus: tar bort en självförvållad DoS-yta (en admin som laddar upp en 5 MB-fil fryser hela podden).

**Matning som ska bekrafta vinsten:**

Ingen befintlig api_benchmark-endpoint mäter detta (benchmarken kör GET:ar, inte multipart-POST). Rätt mätning är en event-loop-lag-probe, inte importens egen väggtid (den ändras inte): (1) Kör en jämn ström av billiga GET:ar mot en lätt endpoint (t.ex. GET /api/users eller hälsoendpointen) med fast intervall under 60 s. (2) Mitt i strömmen: POST:a en representativ importfil till /api/users/import — kör tre storlekar: 20 rader (typfall), 300 rader (värsta realistiska), och en 5 MB-fil (taket). (3) Mät p95 och MAX för GET-strömmen under importfönstret, före och efter fixen. Förväntning: MAX faller från ~importens hela varaktighet till nära baslinjens p95. Om MAX inte faller mätbart för 20-radersfallet är fixen inte värd att motivera på annat än DoS-ytan. (4) Sekundärt: verifiera att UserImportResult (created/skipped/errors, inkl. ordning på errors-listan) är bit-identiskt före/efter.

**Forutsattningar innan bygge:**

Beteendebevarande: ja, om man väljer run_in_threadpool-varianten (behåll `async def`, behåll 413-kontrollen på loopen, wrappa `parse_*_import_excel` och `_import_*_rows` var för sig i `await run_in_threadpool(...)`). Sessionen används då sekventiellt från en tråd i taget, aldrig samtidigt — vilket är exakt vad wikins C1-notering (prestanda-optimeringar.md:234-235) kräver. HTTPException som reses inuti threadpool-funktionen propagerar korrekt. Jag AVRÅDER från svepagentens förstahandsförslag (`async def` → `def` + `file.file.read()`): det ändrar hur multipart-strömmen konsumeras och är en större semantisk förändring än nödvändigt för samma vinst. Skyddande tester som finns: tests/services/test_user_import.py, test_person_import.py, test_activity_import.py — dessa täcker `parse_*_import_excel` och importlogiken, och är den golden-karakterisering som behövs (kör dem före/efter; resultatet ska vara identiskt eftersom ingen logik rörs, bara var den körs). Måste verifieras innan bygge: att audit.log-anropen och db.commit() ligger kvar inuti den funktion som flyttas till tråden (så transaktionen inte splittras över loop/tråd-gränsen) — de gör det idag (users.py:411-423), men kontrollera samma sak i persons.py och activities.py. Öppen fråga jag inte kunde besvara: faktiska filstorlekar/radantal i prod — det avgör om vinsten är 0,2 s eller 4 s.

---

## #09 — SQLAlchemy-poolen kör på create_engine-defaults (pool_size=5, max_overflow=10, pool_timeout=30) mot Azure SQL

- **Plats:** `app/backend/database.py:20`
- **Monster:** konfig-antagande
- **Het vag:** ja · **Insats:** S · **Risk:** medel

**Problem (svepagentens beskrivning):**

> `create_engine(url, pool_recycle=1500)` sätter bara recycle. Allt annat är QueuePool-defaults: pool_size=5, max_overflow=10 (tak 15), pool_timeout=30 s. Två konsekvenser i vår topologi: (1) Overflow-anslutningar POOLAS INTE — de stängs vid retur. Så fort mer än 5 sessioner är igång samtidigt betalar varje extra request en helt ny Azure SQL-anslutning (TCP + TLS + auth via pyodbc/ODBC 18, hundratals ms mot ~37 ms RTT-nätet) och slänger den sedan. (2) Taket 15 är lägre än vad appen kan begära: Starlettes trådpool tar 40 samtidiga sync-anrop, productivity-översikten öppnar 4 egna sessioner (ThreadPoolExecutor, _PRODUCTIVITY_OVERVIEW_DAY_WORKERS=4, egen session_factory per tråd) och Sankey 4 trådar. Vid burst -> QueuePool timeout efter 30 s -> 500 för användaren som redan väntat en halv minut.

**Foreslagen atgard:**

> Sätt medvetna värden: `create_engine(url, pool_recycle=1500, pool_size=20, max_overflow=5, pool_timeout=10, pool_use_lifo=True)`. pool_size ska täcka den samtidighet appen faktiskt kan generera (trådpool + productivity/sankey-workers); LIFO håller anslutningar varma. Mät före/efter med tools.api_benchmark på en samtidighetsburst.

**Skeptikerns granskning:**

Jag försökte avfärda den och misslyckades — mekanismen är verklig och kandidaten UNDERSKATTAR den snarare än överdriver.

1) Koden stämmer. `app/backend/database.py:20`: `engine = create_engine(_normalize_url(settings.DATABASE_URL), pool_recycle=1500)` — inga pool-parametrar alls. Kommentaren ovanför (rad 16-19) handlar bara om borttaget `pool_pre_ping`. Alltså QueuePool-defaults: pool_size=5, max_overflow=10, pool_timeout=30. Overflow-anslutningar poolas inte — de stängs vid retur (SQLAlchemy-semantik), så varje uttag över 5 samtidiga betalar en full Azure SQL-connect (TCP+TLS+login via pyodbc/msodbcsql18). Ingen ODBC-driver-pooling finns som räddar oss: `grep -i pooling|odbcinst` mot Dockerfile och k8s/ ger noll träffar, och unixODBC har pooling AV som default.

2) Redan fixat? Nej. `git log --oneline -- app/backend/database.py` ger bara 3 commits (40a949a tar bort pool_pre_ping, 6def6b5, c5ae7d6). `git log -S pool_recycle` bekräftar samma. Wikin (`wiki/prestanda-optimeringar.md` A4, kronologin) nämner bara pool_pre_ping-borttaget, aldrig pool-storleken. Kandidaten är identisk med `wiki/optimeringsplan.md:145-149` (post 4.9), som explicit är märkt OVERIFIERAD — så detta är just den granskning som saknades.

3) Kall väg? Nej — och här är den värsta detaljen som svepagenten missade. `routers/productivity.py:180-240` (`GET /overview/stream`, SSE) håller SAMTIDIGT: (a) request-sessionen från `get_db` (deps.py:30-40) som `require_view_access` redan har tvingat ut en anslutning ur (2 DB-rundresor per request enligt optimeringsplan 4.6) och som är utcheckad HELA strömmens livslängd (autocommit=False → transaktion hålls), (b) en egen `worker_db = SessionLocal()` (rad 205), (c) upp till 4 dag-worker-sessioner via `productivity_helpers.py:483/486-488/649` (`_PRODUCTIVITY_OVERVIEW_DAY_WORKERS = 4`, `sessionmaker(bind=db.get_bind())` → SAMMA engine/pool). Det blir upp till 6 utcheckade anslutningar per pågående översiktsström, i sekunder-till-minuter — inte i millisekunder. EN användare på Produktivitet mättar alltså redan pool_size=5. Tre samtidiga → 18 > taket 15 → QueuePool-timeout 30 s → 500. Och enligt optimeringsplan 5.2 är översiktscachen alltid kall → ny SSE-ström vid varje besök. Dessutom: ~96 routes har `require_view_access` som dependency, och en sidladdning gör 5-10 API-anrop parallellt (plan 5.1) → >5 samtidiga sessioner är vardag, inte "burst".

Sankey-tråden (`sankey_inbound/fetch.py:690`) hämtar externa ASK-källor, inte DB — den delen av svepagentens evidens bär inte, men den behövs inte.

4) Där kandidaten är FEL: den föreslagna kodraden är INTE beteendebevarande. Jag körde den: `create_engine("sqlite:///:memory:", pool_size=20, max_overflow=5, pool_timeout=10, pool_use_lifo=True)` → `TypeError: Invalid argument(s) 'max_overflow','pool_timeout','pool_use_lifo' ... SingletonThreadPool`. Fil-sqlite blir QueuePool och funkar (SQLAlchemy 2.0.51), och app-engine körs i praktiken mot fil-sqlite lokalt/desktop/visual-tools, men fixen MÅSTE dialekt-gardera pool-argumenten (bara för icke-sqlite, eller bara mssql/postgresql) — annars kan lokal/desktop/typgen-vägen krascha vid import.

5) Där kandidatens vinstpåstående är för optimistiskt: översiktsströmmens egen latens domineras av externa källhämtningar (sekunder), så 5 × 200 ms är inte "halva svarstiden". Den verkliga vinsten ligger i (a) att pool-utsvältning/30 s-timeouts/500 försvinner, och (b) att de SMÅ, snabba requesterna som köar bakom en översiktsström slipper en full Azure-connect (där 100-300 ms är en stor relativ andel).

**Justerad vinst (granskarens, inte svepagentens):**

Latensvinsten per request kan jag INTE kvantifiera utan mätning — connect-kostnaden mot Azure SQL (TLS+login, uppskattat 5-10 rundresor à ~37 ms ≈ 200-370 ms) är ouppmätt i repot. Det jag kan hävda på kodläsning: (1) tillförlitlighetsvinst — 3 samtidiga produktivitetsströmmar (6 utcheckningar var) spränger taket 15 och ger 30 s QueuePool-timeout → 500; den felklassen elimineras. (2) Latensvinst för alla requests som idag hamnar i overflow (dvs. i praktiken varje request som körs samtidigt som en översiktsström): en sparad Azure-connect, storleksordning 0,1-0,3 s. Ingen vinst alls på enanvändar-sekventiell trafik.

**Matning som ska bekrafta vinsten:**

OBS: `tools/api_benchmark.py` kan INTE mäta detta som den ser ut — den är sekventiell (`--samples`, ingen samtidighetsflagga). Krävs:
1. Utöka api_benchmark med `--concurrency N` (eller ett engångsskript) och kör N=1,6,12,18 mot `GET /api/productivity/overview/stream` (dag- och veckoperiod) PARALLELLT med en billig, `require_view_access`-skyddad endpoint (t.ex. `/api/users/me` eller sidebar-endpointen). Mät p50/p95 för den billiga endpointen och antal 500/timeouts. Före: p95 ska stiga kraftigt och 500 dyka upp vid N≥3 strömmar. Efter: platt p95, noll timeouts.
2. Instrumentera poolen i samma körning: `engine.pool.status()` samt `sqlalchemy.pool`-events (`connect` vs `checkout`) → räkna FAKTISKA nya DBAPI-connects före/efter. Det är den enda siffra som direkt bevisar "sparad Azure-connect".
3. Mät connect-kostnaden separat från podden: 20 × `pyodbc.connect()` mot Azure SQL, ta medianen. Utan den siffran är vinstuppskattningen ren gissning.

**Forutsattningar innan bygge:**

1. Dialekt-gardering är OBLIGATORISK innan bygge: pool-argumenten får bara skickas när dialekten inte är sqlite-in-memory (verifierat: TypeError annars). Skriv ett litet enhetstest som anropar engine-fabriken med `sqlite:///:memory:`, `sqlite:///fil.db` och `mssql+pyodbc://...` och kontrollerar att create_engine inte kastar samt att QueuePool-argumenten faktiskt sätts för mssql.
2. Beteendebevarande i övrigt: ja — pool-storlek ändrar inte SQL, transaktioner eller resultat. `pool_use_lifo=True` ändrar bara vilken anslutning som återanvänds; kombinerat med befintlig `pool_recycle=1500` (< Azures 30-min idle-timeout) finns ingen ny risk för döda anslutningar. Verifiera att recycle-skyddet fortfarande gäller för de LIFO-"kalla" anslutningarna i svansen (de kan bli >30 min gamla utan att användas — pool_recycle hanterar det vid checkout, men bekräfta i test).
3. Befintligt skydd: hela tests/services-sviten kör mot egna sqlite-engines (inte app-engine), så den fångar INTE en pool-regression. Skyddet som faktiskt betyder något är tests/tools/test_visual_tools.py och visual_smoke (startar appen med sqlite-fil-DATABASE_URL) samt tools/generate_api_types.py — alla tre skulle krascha vid import om garderingen glöms. Kör dem explicit.
4. Överväg samtidigt (men i separat ändring) rotorsaken: översiktsströmmen håller 6 anslutningar i minuter. Att stänga/frigöra request-sessionen innan strömmen startar minskar behovet av en stor pool. Om det görs kan pool_size sättas lägre.
5. Sätt inte pool_size=20 utan att kolla Azure SQL-databasens max samtidiga sessioner för aktuell servicenivå (Basic/S0 har låga tak) — 1 podd × 25 (20+5) bör vara ok, men bekräfta.

---

## #11 — Arkiv-cachen kör `SELECT *` över hela vyn när planen saknar datumfilter — inget radtak, materialiseras till Python-dicts

- **Plats:** `app/backend/local_archive_store.py:617-628`
- **Monster:** inget-tak
- **Het vag:** nej · **Insats:** S · **Risk:** medel

**Problem (svepagentens beskrivning):**

> I query_rows: om `_window_from_filters(filters)` returnerar None (inget Between-datumfilter) hoppas hela täckningskontrollen över och koden kör `SELECT * FROM <arkivvy>` utan LIMIT, läser `cursor.fetchall()` och bygger en dict per rad. Arkivet innehåller upp till ARCHIVE_CACHE_SEED_DAYS=400 dagars dblog-historik. DATA_SOURCE_RESPONSE_ROW_CAP=50000 skyddar BARA API-vägen (external_data_client.fetch_all); cache-vägen har inget tak alls. Planen i Hämta data byggs av en LLM (data_fetch/plan.py) som *instrueras* att sätta datumfilter men där inget kod-lager tvingar det — en plan utan Between-filter går rakt in i den obundna grenen. Samma sak i query_snapshot_rows:645 som alltid gör full-table SELECT *. Detta är B2-mönstret (ladda hela arkivet i minnet) som en gång OOM-dödade podden — cachen löste API-varianten men införde en ny obunden väg.

**Foreslagen atgard:**

> Returnera None (= fall tillbaka till API-vägen, som har radtaket) när inget datumfönster kan härledas, ELLER sätt ett hårt `LIMIT <cap+1>` och kasta/degradera om taket nås. Streama med `cursor.fetchmany()` i stället för fetchall(). Lägg samma tak i query_snapshot_rows.

**Skeptikerns granskning:**

Koden gör det som påstås — men bara halva kandidaten håller, och den är en GUARDRAIL, inte en latensoptimering.

HÅLLER (query_rows else-grenen): `local_archive_store.py:618-626` — när `_window_from_filters(filters)` (rad 517-528) returnerar None hoppas hela täckningskontrollen över och koden kör `con.execute(f"SELECT * FROM {_quote_ident(archive_view_id)}")` utan LIMIT, följt av `cursor.fetchall()` + en dict per rad. Vyerna i `ARCHIVE_TO_LIVE` (data_fetch/segments.py:21-40) är enbart stora loggvyer (dblog_pick_log, dblog_trans_log, dblog_order_log ...). Cachen är PÅ i produktion: `k8s/configmap.yaml:39 ARCHIVE_CACHE_ENABLED: "1"` och `:45 ARCHIVE_CACHE_SEED_DAYS: "10000"` — alltså i praktiken hela historiken på disk. Grenen är en full scan av hela loggarkivet till Python-dicts i en 1 Gi-podd.

Regressionen är verklig, inte hypotetisk: motsvarande API-väg ÄR bunden. `external_data_client.fetch_all_rows:343-378` — när svaret når `response_row_cap` (50 000, data_fetch.py:319-336) och inget Between-filter finns att dela på, loggas en varning och de KAPADE raderna returneras. Cache-vägen tog alltså bort det enda taket som fanns. Det är exakt B2-mönstret i wiki/prestanda-optimeringar.md:161-170 (132 -> 449+ MB på 20 s -> OOMKill), fast infört på nytt i den lösning som skulle fixa B2.

Reachability: `validate_plan_payload` (data_fetch/plan.py:341-388) kräver INTE ett datumfilter; `apply_prompt_period_hint` (:391-426) lägger bara till ett om prompten antyder en period. LLM-prompten (plan.py:42) *instruerar* Between men inget kodlager tvingar det, och användaren kan dessutom skicka en redigerad plan via `_validate_submitted_plan`. Även `sankey_inbound/fetch.py:176-189` bygger filters utan datumfilter om `segment_start/segment_end` är None. Ingen guard.

Stark motevidens FÖR fixen: `workflow_data.py:404-406` gör redan precis det kandidaten föreslår — `window = window_from_filters(filters); if window is None: return None`. Konventionen finns alltså redan i repot; data_fetch- och sankey-vägarna saknar den.

FALLER (query_snapshot_rows:645): avfärdas. `SYNC_SNAPSHOT_VIEWS = (PACKAGE_ALIAS_VIEW,)` (archive_cache_sync.py:57) — en enda liten dimensionsvy (item_alias), enda anroparen är sankey_inbound/fetch.py:385 som behöver hela tabellen och vars API-alternativ också hämtar hela vyn. "Datat behövs faktiskt / mängden är liten" slår till.

Git: `git log -- app/backend/local_archive_store.py` ger en enda commit (9d71d6f) — inte fixat.

**Justerad vinst (granskarens, inte svepagentens):**

Ingen mätbar latensvinst i normalfallet — det ska sägas rakt ut. Med datumfilter (>99 % av anropen) är fixen en no-op. Vinsten är eliminering av en obunden minnesväg: ett enda filterlöst plan-anrop mot dblog_pick_log/trans_log kan i värsta fall dra hela ~10 000 dagars logghistorik till Python-dicts och OOM-döda den enda uvicorn-workern i 1 Gi-podden -> 502 för alla användare. Jag kan INTE kvantifiera MB utan att veta radantalet i en riktig tenant-duckdb (se "mätning"). Snapshot-delen av kandidaten ger noll vinst.

**Matning som ska bekrafta vinsten:**

Ingen api_benchmark-endpoint kommer visa skillnad — mät inte latens, mät minne och radvolym.
1) Radvolym först (avgör om risken är reell): på en podd/lokal tenant-fil, kör `SELECT COUNT(*) FROM dblog_pick_log` och `... FROM dblog_trans_log` i tenant-duckdb:n (`archive_cache_cli` / arkiv-status-vyn). Under ~200k rader är OOM osannolikt; över ~1M är det akut.
2) Före/efter-repro: seeda en duckdb med N rader, anropa `POST /api/data-fetch/run` (routers/data_fetch.py `_fetch_rows`) med en plan mot dblog_pick_log UTAN Between-filter, och mät process-RSS (t.ex. `psutil.Process().memory_info().rss` runt anropet, eller `tracemalloc` kring `query_rows`). Före: RSS växer linjärt med tabellstorleken. Efter: konstant (fallback till API-vägens 50k-tak, eller hårt LIMIT).
3) Regressionsvakt: nytt test som seedar > cap rader och asserterar att `query_rows(tenant, view, filters_utan_datum)` returnerar None (eller kapar), inte hela tabellen.

**Forutsattningar innan bygge:**

1) Fixen är INTE beteendebevarande och det måste redovisas: med `return None` i else-grenen ändras resultatet för en filterlös plan från "hela cachens historik" till "API-svaret, kapat vid 50 000 rader (fetch_all_rows loggar varning) eller 502 om dblog-API:t är nere". Det är i praktiken ett återställande av beteendet före cachen — men det är en beteendeändring och ska stå i commit/wiki.
2) Skyddande tester: tests/services/test_local_archive_store.py (rad 59-104, 146-191) och test_archive_cache_sync.py använder ALLA Between-filter — ingen test täcker den filterlösa grenen idag. Den är alltså oskyddad; ett golden-/karakteriseringstest för else-grenen måste skrivas FÖRE ändringen. test_sankey_inbound_service.py:304 monkeypatchar query_rows och påverkas inte.
3) Verifiera att `_query_local_archive_segment` (fetch.py:192-211) alltid har datumfilter (den tar start/end som argument) så att retention-vägen inte tappar cache-träffar; det är bara `_fetch_segment_rows_with_source` (fetch.py:176) med None-datum och data_fetch.py:346 som berörs.
4) Bekräfta att arkiv-cachen faktiskt är seedad i prod (arkiv-status-vyn) — om tabellerna är tomma i k8s är hela risken teoretisk och kandidaten degraderas till "lägg in taket innan seeden når prod".

---

## #14 — Personer: varje inline-cellredigering gör full refetch + full tabellombyggnad — även vid Escape och oförändrat värde

- **Plats:** `app/frontend/js/persons_table.js:141 (även 175, 208, 242, 130)`
- **Monster:** D
- **Het vag:** nej · **Insats:** S · **Risk:** medel

**Problem (svepagentens beskrivning):**

> editText/editNumber/editSelect/editChoice avslutar alla med `await loadPersons()` UTANFÖR if-satsen som kontrollerar `commit && värdet ändrats`. Alltså: klicka i en cell och tryck Escape, eller blur:a utan att ändra något -> ändå en GET /api/persons + renderRows() som river och bygger om HELA tabellen (persons.filter().sort() + en <tr> med ~10 <td> och click-lyssnare per rad, persons_table.js:253-386). Vid en riktig ändring är det dessutom onödigt: `person[field] = value` är redan satt lokalt (rad 138/239) och servern returnerar samma sak. api.getSwr hjälper inte här — mutationen rensar snapshot/GET-cachen (api.js:224-240), så det blir en riktig rundresa varje gång.

**Foreslagen atgard:**

> 1) Flytta `await loadPersons()` in i commit-grenen så Escape/oförändrat värde inte kostar något. 2) Ersätt refetch med lokal radpatch: uppdatera persons-posten (görs delvis redan) och rendera om bara den <tr>:en, eller kalla renderRows() utan nätverk. Behåll refetch enbart efter import/undo/delete där servern kan ha ändrat mer än fältet.

**Skeptikerns granskning:**

Kodfaktumet stämmer. `await loadPersons()` ligger utanför commit-grenen i alla fyra editorerna (persons_table.js:141, 175, 208, 242) och loadPersons går alltid till nätet (persons_table.js:394 -> api.getSwr -> request(), api_swr.js:87). PUT går via api.put som kör clearApiGetCache() i .finally (api.js:986, 224-240), vilket även rensar SWR-snapshots (api_swr.js:49) — så efter en riktig ändring finns ingen snapshot och getSwr blockerar på en hel GET-rundresa. Commit-vägen kostar alltså 2 seriella rundresor (PUT + GET) innan cellen visar sitt nya värde, trots att PUT redan returnerar hela objektet (`@router.put("/{person_id}", response_model=PersonOut)`, persons.py:780) med samma schema som listan (persons.py:563 `response_model=list[PersonOut]`). Det är precis mönster D3 i wiki/prestanda-optimeringar.md:248 ("Refetch av redan hämtad data"), och Personer nämns inte där.

MEN svepagenten har fel på två punkter, och det ändrar både fixen och vinsten:

1) Den föreslagna åtgärd 1 ("flytta await loadPersons() in i commit-grenen") är INTE beteendebevarande — den är en bugg. editText m.fl. gör `td.innerHTML = ""` och stoppar in ett <input> (rad 117-118). Vid Escape/oförändrat värde är loadPersons() -> renderRows() det ENDA som återställer cellens text. Tar man bort anropet står ett dött <input> kvar i cellen. Den icke-committande grenen måste anropa `renderRows()` (utan nätverk), inte ingenting. Då försvinner heller inte "hela tabellombyggnaden" som påstås — bara nätanropet.

2) "Escape-fallet är 100 % bortkastat" överdriver den upplevda kostnaden. Vid Escape har ingen mutation skett, så SWR-snapshoten lever kvar och getSwr målar cellen direkt från snapshot (api_swr.js:79-85) innan nätanropet ens returnerar. Användaren väntar inte; det som slösas är en bakgrunds-GET (server-jobb + payload), inte latens.

En lokal patch måste dessutom använda PUT-svarets body, inte klientvärdet: `person[field] = value` (rad 138/239) sätter det oNORMALISERADE värdet, medan servern kör `_noman_for_update` / `_clean_rfid_code` (persons.py:797-802). Idag döljs det av refetchen; tar man bort refetchen utan att patcha från svaret får man en synlig värde-regression (t.ex. otrimmad RFID).

Vägens temperatur: Personer är registervård — en admin, en cell i taget, sekunder mellan redigeringarna. Ingen server-het väg, ingen CPU/minnes-vinst i podden, inget som syns i api_benchmark-medianer. Det är enbart en UI-latensputs.

**Justerad vinst (granskarens, inte svepagentens):**

Commit-vägen: 2 seriella rundresor -> 1 per cellredigering (PUT-svaret räcker). På dev är den sparade GET:en storleksordningen ~37 ms DB-rundresa + HTTP-overhead; i prod (app och DB samma DC) sannolikt bara några tiotal ms totalt. Escape/oförändrat: 1 sparad bakgrunds-GET per klick, ingen upplevd latensvinst (snapshot målas ändå direkt). DOM-ombyggnaden försvinner INTE — renderRows() måste köras ändå för att återställa cellen. Serverbesparing: en GET /api/persons per cellklick, försumbart i podd-budgeten. Kan inte kvantifieras skarpare utan mätning; storleksordningen är "halverad klick-till-uppdaterad-cell", inte "20 hämtningar bort" i någon meningsfull kostnadsmening.

**Matning som ska bekrafta vinsten:**

1) `python -m tools.api_benchmark --base-url <dev> --label persons-refetch` för GET /api/persons + PUT /api/persons/{id} — ger kostnaden per sparad rundresa (baslinje i artifacts/api_benchmark/). 2) Manuell DevTools-mätning på Personer: räkna nätverksanrop och mät median-tid blur -> uppdaterad cell över 10 redigeringar, före/efter. Förväntat: commit 2 requests -> 1; Escape 1 request -> 0. 3) Performance-panel: bekräfta att renderRows() (persons_table.js:253-386) inte är den dominerande kostnaden vid realistiskt antal personer — om den är det faller halva argumentet, eftersom fixen behåller den.

**Forutsattningar innan bygge:**

Före bygge måste verifieras: (a) Den icke-committande grenen måste anropa renderRows() — annars blir cellen tom med ett kvarglömt <input>. (b) Commit-grenen måste patcha persons-posten från PUT-svarets body (PersonOut), inte från klientens råvärde, annars regression på server-normaliserade fält (noman, rfid_code). (c) Områdesfokus-paritet: servern filtrerar på home_area_id (persons.py:575-579), klienten på matchesAreaFocus/home_area_id — kontrollera att en person som byter hemområde försvinner ur listan lika i båda vägarna. (d) Behåll refetch efter import/undo/delete (persons_table.js:90, 368) — där kan servern ha ändrat mer än ett fält. Skyddande tester: endast statiska källkodstester (tests/tools/test_persons_view.py:166,178 greppar loadPersons-kroppen; tests/tools/test_visual_tools.py). Ingen DOM/e2e-täckning finns för editText/editNumber/editSelect/editChoice — golden-karakterisering av alla fyra editorerna (commit, Escape, blur utan ändring, valideringsfelet "NoMan krävs" på rad 128-131, undo efteråt) krävs manuellt eller som nytt test innan ändringen.

---

## #15 — Bemanning saknar SWR trots att den är den mest öppnade vyn — cachen är in-memory och dör vid sidbyte

- **Plats:** `app/frontend/js/schedule/state.js:125-126`
- **Monster:** D
- **Het vag:** ja · **Insats:** L · **Risk:** medel

**Problem (svepagentens beskrivning):**

> scheduleAllCache/scheduleAreaCache är rena `new Map()` i modulscope. Appen är en MPA (riktiga sidladdningar mellan bemanning.html/overblick.html/...), så cachen är TOM varje gång användaren går in i Bemanning. Kvar finns bara api.get-cachen med cacheTtlMs 25 s (schedule/data.js:229) som skrivs till sessionStorage — dvs. återbesök inom 25 s är snabbt, allt äldre ger vit skärm + full väntan på hela schemapayloaden (persons + cells + scheduled_hours + scheduled_defaults för hela veckan). Bemanning har dessutom REDAN allt som krävs för billig SWR: en revision-endpoint (scheduleRevisionUrl, data.js:186) och en patch-funktion (patchScheduleFromAllData).

**Foreslagen atgard:**

> Utvidga SWR-piloten till bemanning.html: ladda common/api_swr.js, spara scheduleUrl(null)-svaret som snapshot, måla det direkt vid sidöppning (applyScheduleData) och revalidera i bakgrunden med revision_key-jämförelsen som redan finns — bara vid ändrad nyckel hämtas full payload.

**Skeptikerns granskning:**

Kodläsningen bekräftar mekaniken, men svepagenten har flera sakfel som ändrar bilden.

VAD SOM STÄMMER:
- state.js:125-126 är rena `new Map()` i modulscope (LRU-gränser 4/24 i state.js:140-141). MPA → tom vid varje sidöppning. Bekräftat.
- data.js:229 hämtar `scheduleUrl(null)` med `cacheTtlMs: 25*1000`. api.js:writeApiGetCache skriver TTL-posten till sessionStorage (`API_GET_CACHE_STORAGE_PREFIX`), så återbesök inom 25 s överlever sidbytet — allt äldre är kallt. Bekräftat.
- SWR-lagret finns (`js/common/api_swr.js`, laddas bara i overblick.html:118 och personer.html:75). `git log -- api_swr.js` → enda commit b4c8952 "SWR-pilot: Personer och Översikt". Bemanning är alltså INTE fixad.
- Revisionsvägen finns redan (data.js:186 scheduleRevisionUrl, 188 revision_key-jämförelse, patchScheduleFromAllData) — integrationen är realistisk.
- Vägen är het: /api/schedule median 765 ms i k8s-baslinjen (tools/latency_budgets.json-kommentaren), budget 1300 ms — näst tyngsta operativa GET efter /api/overview (970).
- Wiki/optimeringsplan.md:162 ("5.2 SWR till Bemanning och Produktivitet") listar redan detta som planerat, och prestanda-leveranslager.md:57-68 säger att piloten ska utvidgas först när den bekräftats i drift. Kandidaten är alltså giltig men INTE ny.

VAD SOM INTE STÄMMER (och som sänker den påstådda vinsten):
1. Payloaden är INTE "hela veckan". schedule_query_routes.py:163-227 hämtar EN weekday (`ScheduleCell.weekday == weekday`). Mindre än påstått.
2. "Tar bort vit skärm" är fel. boot.js:3-52 är strikt seriell: initPage(auth/me) → await loadAreasAndActivities() (3 GET: areas/activities/activities?include_inactive) → await loadCalculatorProfile() → buildHeader() → await loadSchedule(). Ett schema-snapshot kortar bara sista ledet. Dessutom KRÄVER renderingen state.areas/state.activities (data.js:105 areaName, rendering.js:867 home_area_id) — man kan alltså inte måla snapshoten före areas/activities. För att verkligen få bort vita skärmen måste även areas/activities (+ kalkylatorprofilen) SWR:as och boot-kedjan parallelliseras. Det gör insatsen L, inte M.
3. demo_prefetch_init.js:413-421 förhämtar redan /api/schedule (25 s TTL) och areas/activities (60 s) på VARJE sidladdning till sessionStorage — så det finns en icke-försumbar andel sidbyten (snabb navigering inom TTL) som redan är varma. Vinsten gäller "har suttit >25–60 s på förra sidan", vilket förvisso är vanligt men inte "nästan alla" utan mätning.

**Justerad vinst (granskarens, inte svepagentens):**

Tar bort ~0,8 s (median-serversvar för /api/schedule) + payload-överföring ur den kritiska renderingskedjan vid kalla sidbyten in i Bemanning, och byter ut den mot en revisionskoll (/api/schedule/revision, billig) i bakgrunden. MEN: den totala upplevda inladdningen kortas bara delvis — auth/me + areas + activities + kalkylatorprofil ligger kvar seriellt före första schemaraden. Realistisk gräns om ENDAST schemat SWR:as: ca 40-60 % av tiden-till-första-rad vid kall sidöppning. Vill man ha nära noll väntan måste areas/activities/profil SWR:as i samma pass. Exakta ms kan inte anges utan mätning — det finns ingen befintlig mätpunkt för "tid till första schemarad".

**Matning som ska bekrafta vinsten:**

1) Klientmätning (den enda som fångar vinsten): utöka mönstret i tests/tools/test_swr_pilot_browser.py till bemanning.html — mät tid från navigation start till första renderade rad i schematabellen, före/efter, i två lägen: (a) kall session (tom sessionStorage), (b) "snapshot finns men TTL-cachen är utgången" (simulera genom att låta 25 s passera / rensa api-get-nycklarna men behålla snapshot-nyckeln). Kravet från piloten — sidan ska rendera även med API:et helt släckt — ska gälla även Bemanning.
2) Serversidan förändras inte av fixen; kör ändå `python -m tools.api_benchmark --budget tools/latency_budgets.json` för /api/schedule och /api/schedule/revision för att visa att revisionskollen är signifikant billigare än full payload (dvs. att bakgrundsrevalideringen inte kostar mer än den sparar). Om revision inte är klart billigare faller hela ROI:n.
3) Räkna antal backend-anrop per sidöppning före/efter (nätverkspanel/kontraktstest) — SWR får inte ADDERA en tredje /api/schedule-hämtning ovanpå demo_prefetch_init.js:417-421.

**Forutsattningar innan bygge:**

Före bygget måste följande verifieras, annars är fixen INTE beteendebevarande:
1. BEHÖRIGHET I SNAPSHOTEN. ScheduleOut innehåller `lock_foreign_schedule_cells` (schedule_query_routes.py:227) och personurvalet är scope-filtrerat (_visible_schedule_persons). En snapshot utan läs-TTL kan måla ett gammalt låsläge/persondelmängd. Krav: (a) snapshotnyckeln bakar in scheduleScopeKey() (state.js:161) + year/week/weekday, (b) drag/redigering (setupDrag, editing.js) gate:as tills revalideringen landat, ELLER låsflaggan/rollen tas alltid från färsk auth/me — annars kan en användare börja redigera celler som servern nu låser.
2. INVALIDERING. clearApiGetCache() anropar clearSwrSnapshots endast om api_swr.js är laddad (api.js:227) — bemanning.html måste ladda modulen, annars rensar mutationer inte snapshoten. Verifiera att alla schema-mutationer går via api-lagret.
3. DUBBELRENDER. applyScheduleData (data.js:109-119) triggar buildRows + RFID + produktivitet + summary + kalkylator. Snapshot-paint följt av full applyScheduleData på färskt data kör allt två gånger. Färsk data måste gå via patchScheduleFromAllData (finns redan, data.js:175/199), inte via full omrendering.
4. RENDERINGSBEROENDEN. Snapshot av /api/schedule ensamt räcker inte — state.areas/state.activities krävs för att måla (rendering.js:867). Antingen SWR:a även /api/areas + /api/activities, eller acceptera att vinsten begränsas till sista ledet i boot-kedjan.
Skyddande tester idag: tests/tools/test_swr_pilot_browser.py (SWR-kontraktet), test_gap_schedule_drag_browser.py och test_gap_schedule_undo_browser.py (redigeringsflödet — dessa måste köras gröna mot den nya snapshot-vägen). Golden-karakterisering behövs inte på backend (ingen serverändring), men en karakterisering av tiden-till-första-rad före fixen krävs, eftersom mätpunkten saknas idag.

---

## #17 — Meta sändningsanalys: sökfältet saknar debounce och bygger om hela tabellen + ~800 event-lyssnare per tangenttryck

- **Plats:** `app/frontend/js/meta.js:503-506`
- **Monster:** NYTT:saknad-debounce
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> input-lyssnaren kallar renderShipmentRows() direkt vid varje tangenttryck. renderShipmentRows (meta.js:364-454) gör tre dyra saker per anrop: (1) filteredShipmentItems() bygger om söksträngen för ALLA rader via shipmentSearchText() — 15 fält joinas + toLocaleLowerCase('sv-SE') per rad, varje tangenttryck (B3-omräkning av statisk text); (2) hela tbody sätts om med en innerHTML-sträng på upp till 200 rader × 14 kolumner; (3) fyra querySelectorAll-loopar fäster om en <select>-change-lyssnare + tre knapplyssnare per rad — ~800 addEventListener per tangenttryck, där varje callback dessutom gör en linjär `shipmentItems.find()`.

**Foreslagen atgard:**

> Debounce input ~150 ms; precomputa item._searchText en gång i loadMetaItems() i stället för per tangenttryck; ersätt de fyra per-rad-loopariterna med EN delegerad click/change-lyssnare på tbody (data-attributen finns redan). Sorteringsklick kan använda samma render utan omprecompute.

**Skeptikerns granskning:**

Koden gör det som påstås. meta.js:503-506 anropar renderShipmentRows() synkront på varje input-event. renderShipmentRows (:364-454) kör filteredShipmentItems() (:336-343) som bygger shipmentSearchText() för ALLA rader per anrop, sätter om hela tbody.innerHTML (:383-427) och fäster om fyra lyssnare per rad (:429-453). Ingen debounce finns någonstans i app/frontend/js/ (grep: 0 träffar). Git-historiken för filen (b33d2dd, f048df1, 55e898e, 98f66ab, 6472cb1) innehåller ingen fix. Wiki/prestanda-optimeringar.md har inget frontend-render-mönster (avsnitt D täcker bara transport D1-D3) — mönstret är alltså genuint nytt och inget "INTE mönstret om"-kriterium slår till på mekanismen. MEN svepagentens kostnadsbild är fel viktad och jag skriver ned vinsten hårt: (a) de ~800 addEventListener på redan parsade noder kostar i storleksordningen 1 ms totalt, inte "tiotals ms" — det är teater; (b) 200 st toLocaleLowerCase på en joinad sträng är också ~1 ms; (c) den reella kostnaden är innerHTML-parse + style/layout av ~4000 noder (200 rader × 14 celler, varje rad med ett <select> med options, statusSelect :238-247), grovt 10-30 ms i Chromium/QtWebEngine; (d) kostnaden decimeras redan efter första tecknet eftersom visibleItems krymper — bara tecken 1-2 är dyra; (e) input-eventet fyller redan fältet innan lyssnaren körs, så inga tecken tappas — det är en stutter, inte förlorad inmatning. Vägen är dessutom ljummen: meta.html är superuser-only (initPage(..., { requireSuperUser: true }) :499), raderna är hårt serverbundna till 200 (loadMetaItems :481, :487) och ingen server-/API-latens berörs.

**Justerad vinst (granskarens, inte svepagentens):**

Liten, rent klientsidig UX-vinst på en admin-sida. Realistiskt: ~10-30 ms blockerande render tas bort för de 1-2 första tecknen i sökningen (senare tecken är redan billiga eftersom träffmängden krympt). Ingen server-, latens- eller minnesvinst — inget som syns i api_benchmark. Jag kan inte kvantifiera exakt utan mätning i QtWebEngine/Chromium; jag avfärdar uttryckligen svepagentens "800 addEventListener + 200 söksträngsbyggen" som den dominerande kostnaden (den är ~2 ms av totalen). Rekommenderad scope: ENDAST debounce (~5 rader). Precompute av _searchText och delegerade lyssnare ger försumbar extra vinst när debouncen väl finns och bär onödig regressionsrisk.

**Matning som ska bekrafta vinsten:**

api_benchmark är irrelevant (ingen backend berörs). Mät i webbläsaren: instrumentera renderShipmentRows med performance.now() och kör Playwright-scenariot i tests/tools/test_meta_browser.py med en fixture på 200 sändningsrader (dagens fixture har bara 2 — den måste utökas, annars mäter man ingenting). Före/efter: summan av renderShipmentRows-tid vid inmatning av 5 tecken i #metaSearch, samt antal renderanrop (ska gå från 5 till 1). Alternativt Chrome DevTools Performance-trace: scripting + layout under 5 keydown.

**Forutsattningar innan bygge:**

1) Beteendebevarande i resultat men INTE i timing — det bryter ett befintligt test: tests/tools/test_meta_browser.py:128-129 gör page.fill("#metaSearch", "2") följt av omedelbar `assert visible_ids() == ["#2"]` utan retry. Med 150 ms debounce failar detta. Testet måste skrivas om till en pollande assertion (expect(...).to_have_count / expect_poll) INNAN fixen mergas — annars ser det ut som en regression. 2) Sorteringsklicken (:507-517) och loadMetaItems (:494) måste fortsatt rendera OMEDELBART — debouncen får bara sitta på input-lyssnaren, annars känns sortering trög. 3) tests/tools/test_visual_tools.py:2146 källinspekterar renderShipmentRows-kroppen (analysId-uttrycket, colspan="14") — det skyddar mot att man råkar riva sönder renderfunktionen, och är ett skäl att INTE göra delegations-refaktorn i samma svep. 4) Verifiera att exportShipmentRows(true) (:461-478) fortfarande exporterar mot det senaste sökordet, dvs. att metaSearchTerm sätts synkront (utanför debouncen) även om renderingen fördröjs. 5) Golden-karakterisering behövs inte — resultatmängden är oförändrad.

---

## #19 — Personliga vyer: schema-/produktivitetshämtning utan AbortController eller sekvensvakt vid datum-/personbyte

- **Plats:** `app/frontend/js/personal_views.js:404-436`
- **Monster:** NYTT:saknad-avbrytning
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> loadSchedule() och loadProductivity() kör `await api.get(...)` utan signal och utan requestSeq/token. Båda triggas av change på datumfältet och personväljaren (personal_views.js:391-402). Byter användaren datum snabbt (eller person) ligger flera hämtningar i luften samtidigt och den som svarar sist renderar — ett äldre datum kan skriva över det nyare. Bemanning (schedule/data.js) och Översikt (overview.js:488-570) har båda AbortController + seq-vakt; den här vyn har ingen.

**Foreslagen atgard:**

> Lägg till samma mönster som schedule/data.js: modulnivå-controller som abort:as vid ny laddning + `++requestSeq`-vakt innan render. Billigt och isolerat till två funktioner.

**Skeptikerns granskning:**

Koden gör det som påstås. personal_views.js:404-419 (loadSchedule) och :421-436 (loadProductivity) anropar api.get med enbart cacheTtlMs — ingen signal, ingen seq/key-vakt före renderSchedule/renderProductivity. Samtliga triggers anropar load-funktionerna direkt utan debounce eller knapp-disable: prev/next-dag (:379-386), datumfältets change (:391-394), person-select i bindCommonControls (:398-401), prev/next-vecka (:305-318). Referensmönstren finns och stämmer: schedule/data.js:52-86 (controller.abort() + scheduleProductivityLoadState.key-vakt + AbortError-swallow + controller-identitetskoll i finally) och overview.js:484-570 (controller + ++loadState.requestSeq / overviewCacheKey()-vakt). tests/tools/test_performance_contracts.py:124 (test_heavy_views_render_incrementally_and_cancel_stale_work) kräver uttryckligen AbortController i schedule.js och overview.js — personal_views.js är inte täckt, dvs. projektet har redan kodifierat konventionen men den här vyn följer den inte. Racet är dessutom MER sannolikt än genomsnittligt: api.js:604-639 dedupar in-flight enbart per identisk path, och olika datum ger olika paths, samtidigt som 25 s-cachen gör redan besökta datum nära nollatenta medan nya datum kräver fullt rapportbygge i backend (app/backend/routers/personal.py:653-674 → _personal_productivity_data → _personal_productivity_stats:514+ som bygger både dag och hela veckan). Snabb/långsam-asymmetrin är precis det som producerar out-of-order-svar: bläddra till ett ocachat datum (långsamt) och sedan vidare till ett cachat (snabbt) → det äldre svaret landar sist och renderar över, medan state.date och datumfältet visar det nyare datumet. Inget i git-historiken (git log på personal_views.js: 2e5c350, c3fadd7, c15f88d, af04bdc) rör avbrytning, och wiki/prestanda-optimeringar.md saknar mönstret helt — inte redan fixat. MEN jag avfärdar halva vinstpåståendet: "sparar bortkastade requests" ger ingen serverbesparing. get_personal_productivity är en synkron def (personal.py:654) och körs i anyio-threadpoolen; FastAPI avbryter inte threadpool-arbete vid client disconnect. En abort:ad fetch stoppar alltså inte podden från att räkna färdigt. Vinsten är korrekthet, inte prestanda.

**Justerad vinst (granskarens, inte svepagentens):**

Ingen mätbar prestandavinst — nedgraderad från svepagentens påstående. Serverarbetet sparas INTE av en abort (synkron def-endpoint i threadpool; FastAPI avbryter inte vid disconnect), så CPU-lasten på den 300m-begränsade podden är oförändrad. Latensvinsten är noll för användaren. Vinsten är enbart korrekthet: eliminerar ett reellt och nåbart stale-render-race där ett äldre datum/en äldre person renderas över det nyare samtidigt som datumfältet visar det nyare värdet (inkonsistent vy). Sannolikheten är icke-trivial p.g.a. cache-asymmetrin (cachat datum = snabbt, nytt datum = tungt rapportbygge). Jag kan inte kvantifiera hur ofta detta faktiskt drabbar användare utan telemetri — det är en korrekthetsbugg med okänd frekvens, inte en optimering. Motiveringen för att bygga fixen är att den är billig (S) och att projektet redan har mönstret kodifierat i ett prestandakontraktstest som den här vyn av misstag inte täcks av.

**Matning som ska bekrafta vinsten:**

Ingen api_benchmark-endpoint är relevant — vinsten är inte latens, så mät inte latens. Bekräfta i stället beteendet: (1) Manuell repro före/efter med DevTools Network throttling (Slow 3G) på /my-productivity: nollställ sessionStorage, gå till ett nytt (ocachat) datum, klicka ‹ igen direkt till ett datum som redan ligger i 25 s-cachen. FÖRE: headern (payload.date, personal_views.js:347) visar ett annat datum än inputfältet (state.date, :327) när det långsamma svaret landar sist. EFTER: headern och inputfältet visar alltid samma datum, och det avbrutna anropet visas som "canceled" i Network. (2) Statiskt kontraktstest: utöka tests/tools/test_performance_contracts.py:124 (test_heavy_views_render_incrementally_and_cancel_stale_work) så att personal_views.js också måste innehålla "AbortController" + signal-vidarebefordran, på samma sätt som assert på rad 137/148 gör för schedule/overview. Det testet är den enda regression som faktiskt låser fast fixen. (3) Räkna fetch-anrop i Network vid fem snabba ‹-klick: antalet requests ska vara oförändrat (de startar ändå) men fyra ska vara canceled och exakt en render ska ske — inte fem.

**Forutsattningar innan bygge:**

Fixen är beteendebevarande för normalflödet (ett klick i taget) men ändrar med flit beteendet vid snabba klick — det är hela poängen och måste redovisas. Två sätt fixen kan REGRESSERA om den byggs naivt, båda måste hanteras: (a) catch-grenen i loadSchedule/loadProductivity går idag till renderError (:414, :431). En abort kastar AbortError → utan `if (error?.name === "AbortError") return;` skulle snabb datumbläddring börja visa felsidan "Kunde inte ladda vyn". schedule/data.js:72 gör exakt den kontrollen — kopiera den. (b) `finally { app.classList.remove("is-loading") }` (:417, :434) måste controller-identitetskollas (som schedule/data.js:80-84), annars släcker den avbrutna requesten laddindikatorn för den nya som fortfarande är i luften. Verifiera också: api.js:605 sätter useSharedInFlight = useGetCache && !rest.signal, dvs. att skicka en signal STÄNGER AV den delade in-flight-dedupen för dessa paths. Här är det ofarligt (en enda anropare per sida) men det måste konstateras, inte antas. Skyddande tester idag: tests/tools/test_personal_views_static.py (endast ett test, om global personproduktivitet — skyddar inte load-vägen) och tests/services/test_personal_views.py (backend). Ingen befintlig frontend-test täcker avbrytning i denna vy — golden-karakterisering behövs inte, men det nya kontraktstestet enligt punkt (2) i mätningen måste läggas till samtidigt som fixen, annars finns inget som hindrar regression.

---

## #21 — Vybehörighetskollen kostar 2 extra DB-rundresor på i princip varje autentiserad request

- **Plats:** `app/backend/deps.py:113 (+126, 85); app/backend/settings_service.py:937-939, 663-664, 653-660; app/backend/business_scope.py:57-59`
- **Monster:** A4
- **Het vag:** ja · **Insats:** M · **Risk:** hög

**Problem (svepagentens beskrivning):**

> `require_view_access(view, level)` är dependency på 96 route-deklarationer (25 routers). Varje anrop kör `get_role_view_access(db, ...)` -> `get_json_setting()` -> `_get_setting()` -> `_business_id(db, None)` -> `default_business(db)` som gör `SELECT ... FROM businesses WHERE code='STIGAMO'` (ren db.query, aldrig identity-map-cachad), och därefter `db.get(AppSetting, {...})` = `SELECT ... FROM app_settings`. Ingen cache någonstans (grep på lru/cache i settings_service/business_scope ger noll träffar). Rollmatrisen är dessutom *global* — `get_role_view_access` skickar aldrig vidare `business_id` till `get_json_setting`, och wiki/auth-roles-access.md:50 bekräftar "Vybehorigheter ar globala for rollen och galler over verksamheter" — så värdet är detsamma för alla användare och ändras bara när en admin sparar matrisen. Schemavägarna dubblar dessutom mönstret: `foreign_schedule_cell_lock_appl…

**Foreslagen atgard:**

> Processlokal cache av (a) `default_business().id` och (b) `role_view_access`-dicten, invaliderad i `set_role_view_access`/`set_json_setting` (appen kör 1 uvicorn-worker per podd; vid >1 replik räcker en kort TTL, t.ex. 15-30 s, eller en `version`-räknare i app_settings). Alternativt minimalt: slå ihop de två queries till en (app_settings joinat mot businesses) så kostnaden halveras utan cachesemantik. Guardrail: sänk fragebudgetarna i tests/services/test_query_count_budgets.py (t.ex. /api/persons 6 -> 4) så regressionen fastnar i pre-push.

**Skeptikerns granskning:**

Jag försökte avfärda den och lyckades inte — koden gör exakt det som påstås.

VERIFIERAT I KODEN:
- deps.py:113 och :126 anropar `get_role_view_access(db, business_id=user.business_id)` per request.
- settings_service.py:937-939: `get_role_view_access` **kastar bort** business_id och anropar `get_json_setting(db, ROLE_VIEW_ACCESS_KEY, default={})` utan business_id. Det matchar wiki/auth-roles-access.md ("Vybehorigheter ar globala for rollen och galler over verksamheter") — alltså avsiktligt, inte en bugg.
- settings_service.py:730-731 -> :663-664 -> :653-660: `_business_id(db, None)` -> `default_business(db)` -> business_scope.py:57-59 -> `db.query(Business).filter(Business.code=='STIGAMO').one_or_none()`. Det är en `db.query`, inte `db.get` — den går **aldrig** via identity map, dvs alltid en rundresa, även om Business redan är laddad i sessionen.
- Därefter `db.get(AppSetting, {"business_id": ..., "key": ...})` = en andra rundresa (identity-map-miss på färsk request-session).
- Ingen cache finns: `grep` på lru_cache/_cache i settings_service.py ger noll träffar. `git log -S "default_business"` visar ingen tidigare cacheåtgärd. Alltså INTE redan fixat.

HET VÄG: `require_view_access`/`require_any_view_access` förekommer 118 gånger i 26 filer under app/backend — det är i praktiken varje autentiserad API-route. Användaren väntar.

STORLEKEN ÄR OBEROENDE BEKRÄFTAD: tests/services/test_query_count_budgets.py:35 dokumenterar "areas 2, ..., persons 4". /api/areas har bara `get_current_user` (2 queries), /api/persons har `require_view_access` (4). Delta = exakt de två konfig-queries kandidaten pekar ut. 50 % av frågorna på ett enkelt listanrop är ren behörighetskonfiguration.

INGEN "INTE mönstret om" slår till: datat behövs (det är auktoriseringen), men det är *invariant* mellan requests — det är därför det är cachebart. Ingen engångsbatch, ingen liten/kall väg.

MEN — svepagenten missar två saker som jag skärper nedan:

(1) VINSTEN ÄR ÖVERDRIVEN. "~74 ms rakt av på nästan alla API-anrop" är en ren dev-siffra, och wiki/prestanda-optimeringar.md:35 säger uttryckligen "Extrapolera aldrig dev-matningar rakt till prod" — i prod ligger app och DB i samma DC. Se justerad_vinst.

(2) DEN "UPPENBARA" MINIMALA FIXEN ÄR EN SÄKERHETSREGRESSION. Att bara låta `get_role_view_access` skicka vidare `business_id` (raden ser ju ut som en glömska) tar bort businesses-queryn — men matrisen skulle då läsas per verksamhet. För R3/T3-användare finns sannolikt ingen sådan app_settings-rad -> default `{}` -> alla tappar vyåtkomst. Den vägen får INTE tas.

(3) DEMOLÄGET ÄR EN FÄLLA FÖR EN PROCESSCACHE. deps.py:30-36 väljer `demo_session.get_demo_session_local()` — en **separat SQLite-databas per demo-inloggning** (demo_session.py:74-84), och demokontot har admin-roll och kan alltså spara Vybehörigheter i sin sandlåda. En processglobal cache keyad enbart på nyckelnamn skulle låta en demoanvändares matris/business-id läcka till riktiga användare (och tvärtom). Cachen MÅSTE keyas på bind/engine-URL, och invalidering måste täcka demo-vägen. Det är därför jag höjer risken till hög.

k8s/deployment.yaml:10 och k8s/flow.yml:14 har `replicas: 1`, så en processlokal cache med invalidering i `set_json_setting` är semantiskt hållbar (ingen TTL strikt nödvändig) — men den förutsätter att inget skriver app_settings utanför appen.

**Justerad vinst (granskarens, inte svepagentens):**

Jag kapar svepagentens siffra.

Säkert: -2 SQL-queries per autentiserad request (från 4 till 2 på /api/persons — verifierbart och deterministiskt).

Latens: på DEV (~37 ms/rundresa, Proact->Azure) ~40-75 ms/request. Jag säger inte 74 ms rakt av: de två frågorna är triviala indexerade lookups på en redan uthämtad connection, så rundresetiden dominerar men 2 x 37 ms är ett tak, inte ett golv.

I PROD (app + DB i samma DC) är rundresan "mycket lägre" enligt wikin — realistiskt 1-3 ms styck, dvs ~2-6 ms/request. Det är INTE en användarmärkbar vinst per anrop i prod. Det verkliga prod-värdet är i stället: 2 färre queries x varje request = mindre DB-last och kortare occupancy i connection-poolen med EN uvicorn-worker, vilket betyder mest under samtidig last. Den effekten kan jag inte kvantifiera utan lasttest.

Sammanfattat: tydlig och mätbar vinst på dev, blygsam per-request-vinst i prod, potentiellt värdefull throughput-vinst i prod under last. Halva vinsten (1 rundresa) går att ta med noll cachesemantik och nära noll risk via en enda join/subselect-query.

**Matning som ska bekrafta vinsten:**

1) Frågeräkning (billigast, deterministisk, kör först): `pytest tests/services/test_query_count_budgets.py` — logga faktiskt `used` per endpoint före/efter. Förväntan: /api/persons 4 -> 2, /api/areas oförändrat 2 (den saknar require_view_access och är därmed en bra kontrollgrupp som visar att inget nytt tillkommit). Sänk sedan budgetarna i QUERY_BUDGETS (persons 6 -> 4, schedule 12 -> 10, summary 11 -> 9, overview 12 -> 10) så en regression fastnar i pre-push.

2) Latens mot dev: `python -m tools.api_benchmark --base-url <dev> --label fore-k21` före deploy och `--compare` efter. Endpoints som ska röra sig: /api/persons, /api/activities, /api/schedule, /api/schedule/summary, /api/overview (alla har require_view_access). /api/areas är kontroll och ska INTE röra sig nämnvärt. Baslinjer i artifacts/api_benchmark/.

3) Prod-vinsten ska INTE hävdas utan mätning: kör samma api_benchmark mot prod före/efter. Om deltat där är inom brus — redovisa det ärligt som "vinst på dev + minskad DB-last", inte som latensvinst.

**Forutsattningar innan bygge:**

FÖRE bygget måste följande verifieras:

1. BETEENDEBEVARANDE — golden-karakterisering av auktorisering. Detta är auktoriseringsmatrisen; en stale eller korskontaminerad cache är en säkerhetsbugg (fel användare får/nekas åtkomst), inte en kosmetisk regression. Kör hela auth-/behörighetssviten och karakterisera per (roll, vy, min_level) -> tillåten/nekad före och efter. Sök upp och kör befintliga tester: allt som rör require_view_access, can_access_view, user_access, role_view_access och settings-routern.

2. DEMOLÄGET. deps.py:30-36 + demo_session.py:74-84: demo kör en egen SQLite-DB via en annan sessionmaker. Cachen MÅSTE keyas på engine/bind-URL (inte bara settingsnyckeln), annars kan en demoadmin som sparar Vybehörigheter i sin sandlåda poisona cachen för riktiga användare. Skriv ett test som: (a) fyller cachen som riktig användare, (b) startar demo-session, ändrar matrisen där, (c) verifierar att riktig användares åtkomst är oförändrad — och tvärtom.

3. INVALIDERING. Alla skrivvägar måste invalidera: set_role_view_access (settings_service.py:942-949) OCH set_json_setting (:740-758) generellt, plus ensure_seed_businesses / alla ställen som kan skapa/ändra Business. Kolla även att inga migrationer/seed-skript eller externa jobb skriver app_settings.businesses utanför appprocessen — om de gör det krävs TTL trots replicas=1.

4. FÖRBJUDEN GENVÄG. Låt INTE get_role_view_access (settings_service.py:937-939) börja skicka vidare business_id till get_json_setting. Matrisen är global per design (wiki/auth-roles-access.md); en per-verksamhet-läsning ger tom matris för R3/T3 och låser ute användare.

5. ÖVERVÄG DEN LÅGRISKVARIANTEN FÖRST. En enda query (app_settings med business_id via subselect mot businesses.code='STIGAMO') tar bort 1 av 2 rundresor, är strikt beteendebevarande, kräver ingen cachesemantik, ingen demo-keying och ingen invalidering. Halva vinsten till ~en tiondel av risken. Bygg den först, mät, och ta cachen bara om mätningen motiverar den.

---

## #22 — GET /api/rfid/events: N+1 via lazy-loadade person/activity — och endpointen pollas var 7:e sekund

- **Plats:** `app/backend/routers/rfid.py:301-305 (serialisering i 160-189)`
- **Monster:** A2
- **Het vag:** ja · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> `list_rfid_events` hämtar dagens `RfidScanEvent`-rader och kör `_serialize_event(event)` utan att skicka med person/activity. `_serialize_event` gör då `event.person` och `event.activity` (relationship, models.py:227-228) -> en lazy-load per distinkt person och per distinkt aktivitet. Ingen `joinedload`/`selectinload` finns i rfid.py. Endpointen är inte en admin-engångsvy: `app/frontend/js/schedule/rfid.js:2` sätter `SCHEDULE_RFID_REFRESH_MS = 7000` och `scheduleNextRfidRefresh()` pollar `loadScheduleRfidEvents()` var 7:e sekund så länge Bemanning är öppen och fliken är synlig, med `skipCache: true` — alltså träffar varje poll databasen. Antalet event växer med antalet personer × aktivitetsbyten per dag, så N+1:et växer med bemanningens storlek.

**Foreslagen atgard:**

> `query.options(joinedload(RfidScanEvent.person), joinedload(RfidScanEvent.activity))` på queryn i rfid.py:301 (samma grepp som redan används i meta_uploads.py:460). Beteendebevarande — samma fält, samma ordning. Lägg in /api/rfid/events i test_query_count_budgets.py med tak 4-5 så N+1:et inte kan smyga tillbaka.

**Skeptikerns granskning:**

Koden gör det som påstås. rfid.py:304 anropar `_serialize_event(event)` utan kwargs; rfid.py:161-162 faller då tillbaka på `event.person` / `event.activity`, som är rena `relationship()` utan lazy-strategi (models.py:227-228) → en lazy-load per distinkt person och per distinkt aktivitet i sessionens identity map. Ingen `joinedload`/`selectinload` finns i rfid.py, och `git log -S "joinedload" -- app/backend/routers/rfid.py` ger noll träffar → inte redan fixat. Ingen "INTE mönstret om"-kriterie slår till: loopen är inte redan en bulk-query (wiki/prestanda-optimeringar.md:102), fälten behövs faktiskt (person_name/activity_label/activity_code går till klienten) och reduktionen är trivialt SQL-uttryckbar. Vägen är inte kall: rfid.js:2 (`SCHEDULE_RFID_REFRESH_MS = 7000`), rfid.js:192-201 och 211-216 (`skipCache: true`) pollar per öppen Bemanning-flik; wiki/rfid.md:71 dokumenterar samma sak.

MEN: svepagentens vinstuppskattning är kraftigt uppblåst och avvisas. Den bygger på "~40 distinkta personer och ~15 aktiviteter". wiki/rfid.md:73-78 listar exakt TVÅ moduler i drift (MG Plock, MG VM), och `_activity_for_module` (rfid.py:76-93) mappar ett modulnamn till EN aktivitet → antalet distinkta aktiviteter per dag är ~2, inte 15. Antalet distinkta personer begränsas av hur många som faktiskt har `Person.rfid_code` satt (RFID är en pilot, inte utrullat på hela bemanningen). Dessutom: för varje verksamhet utan RFID är `events` tom → noll extra rundresor och noll vinst. Prob-siffran (40 event/10 personer/10 aktiviteter → 24 queries) är ett syntetiskt seed-scenario, inte en produktionsprofil.

Notera också att apply/ignore-vägarna (rfid.py:324, 337, 343, 475, 546) lazy-loadar via `_serialize_event`, men det är enstaka rader per anrop — försumbart, ingen del av fixen.

**Justerad vinst (granskarens, inte svepagentens):**

Mekanismen är verklig men vinsten är LITEN och jag kan inte kvantifiera den utan produktionsdata (hur många personer har `rfid_code`?). Realistiskt tak givet 2 moduler i drift: ~2 aktivitets-loads + N distinkta person-loads. Med en pilot om 3-8 taggade personer = ~5-10 sparade rundresor per poll → på dev-topologin (~37 ms/rundresa, wiki/prestanda-optimeringar.md:33-39) ~185-370 ms; i prod (app + DB i samma DC) väsentligt mindre, sannolikt tvåsiffriga ms. Svepagentens "~2 s per poll" avvisas som ogrundad. Det verkliga värdet är främst att lasta av den enda uvicorn-workern (300m CPU) från 8,5 onödiga rundresekluster/minut per öppen flik och att guardrail:a mot att N+1:et växer när RFID rullas ut brett — inte en mätbar UX-vinst i dag (pollen är `silent`/bakgrund, ingen användare väntar på svaret).

**Matning som ska bekrafta vinsten:**

1) Frågeräkning (primär, deterministisk): lägg `/api/rfid/events?year=..&week=..&weekday=3` i `QUERY_BUDGETS` i tests/services/test_query_count_budgets.py:38-45 och utöka seed:en där med RFID-event för de 30 seedade personerna. Mät antal SQL-frågor före (förväntat ~4 + antal distinkta personer + antal distinkta aktiviteter) och efter (förväntat 4-5). Detta är den enda mätning som ärligt bevisar effekten. 2) Sekundärt, om latens ska redovisas: `python -m tools.api_benchmark --base-url <dev> --label fore-k22` / `--compare` med /api/rfid/events som fall — men förvänta dig ett litet delta och rapportera det som sådant, inte som ett sekundvärde.

**Forutsattningar innan bygge:**

1) GOLDEN SAKNAS: tests/services/test_rfid_events.py innehåller endast fyra tester (duplicate-drop, device-token, MG VM-scan, apply-split) — INGET test träffar `GET /api/rfid/events`. Endpointen är alltså oskyddad. Skriv först ett karakteriseringstest som låser hela payloaden (`date` + `events`-listan med person_name/activity_label/activity_code/status, ordning `scan_time ASC, id ASC`) för minst tre fall: event med person+aktivitet, event med person_id/activity_id = NULL (unknown_person/unknown_activity — `_serialize_event` ska ge None, inte krascha), och `area_id`-filtrerat anrop. 2) BETEENDEBEVARANDE-RISK ATT VERIFIERA: när `area_id` är satt gör rfid.py:296-300 redan explicita `outerjoin(Person)`/`outerjoin(Activity)` för filtrering. `joinedload` lägger till EGNA anonymt aliasade LEFT OUTER JOINs och ska inte kollidera med filtret — men detta måste bevisas av area_id-testet ovan, inte antas. Många-till-en-relationer kan inte fan-outa rader, så radantalet ska vara oförändrat. 3) Verifiera att fixen inte gör `.filter(Person.home_area_id == area_id)` tvetydig (SQLAlchemy kan välja fel entitet) — kör testet, läs inte bara koden.

---

## #23 — GET /api/bug-reports drar upp till 200 rrweb-inspelningar (4 MiB var) ur DB för att visa en metadatalista

- **Plats:** `app/backend/routers/bug_reports.py:179-191 (även 194-199, 247-276)`
- **Monster:** A3
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> `list_bug_reports` kör `db.query(BugReport)` (hela entiteten) med `.limit(200)`. `BugReport.events_json` är en `Text`-kolumn som medvetet lagrar hela rrweb-DOM-inspelningen som rå JSON — modellen säger själv "blobben ska aldrig frågas på, bara lagras och spelas upp" (models.py:393-395). Taket är `BUG_REPORTS_MAX_EVENTS_BYTES = 4 * 1024 * 1024` (config.py:129), plus `context`-JSON på upp till 20 000 tecken. `_report_row()` (rad 157-169) rör aldrig `events_json` eller `context` — den returnerar bara id/created_at/username/view_id/note/status/events_bytes. Alltså SELECT:as upp till 200 × 4 MiB = ~800 MB i värsta fall, och realistiskt tiotals-hundratals MB, bara för att rita en tabell. Podden har 1 Gi-tak — det är exakt samma OOM-profil som Sankey-incidenten (B2) i wikin. Samma över-hämtning sker i `_visible_report_or_404` (`db.get(BugReport, id)`) som används av PATCH /status och DELETE: he…

**Foreslagen atgard:**

> På listan: `db.query(BugReport).options(defer(BugReport.events_json), defer(BugReport.context))` — eller ännu tydligare, byt till en explicit kolumnlista med `with_entities(...)` av just de fält `_report_row` använder. Samma `defer` i `_visible_report_or_404` (detalj-GET:en kan hämta blobben separat via `db.get` när den faktiskt behövs, rad 215). Exakt samma grepp som `coredata_service.py:147` redan använder (`defer(CoreDataFile.data)`, 615 ms -> 384 ms).

**Skeptikerns granskning:**

Mekanismen stämmer, men svepagentens hotness-påstående gör det inte. VERIFIERAT: bug_reports.py:179 `db.query(BugReport)` laddar hela entiteten, :184 `.limit(200)`, och `_report_row` (157-169) rör varken `events_json` eller `context` — den returnerar bara id/created_at/username/business_id/view_id/page_path/note/status/events_bytes/handled_at. models.py:393-395 säger uttryckligen "blobben ska aldrig frågas på, bara lagras och spelas upp" (`events_json: Text`, NOT NULL). config.py: `BUG_REPORTS_MAX_EVENTS_BYTES = 4*1024*1024`, `BUG_REPORTS_RETENTION_DAYS = 30`, `BUG_REPORTS_RATE_LIMIT_PER_HOUR = 3`. Ingen `defer`/`load_only`/`with_entities` finns i filen, och `git log -- app/backend/routers/bug_reports.py` visar bara tre commits (8d93b86 introduktion, df56575 delete/status, edfc7af Seq) — INTE fixat. Mönstret är exakt A3 i wiki/prestanda-optimeringar.md:104-113, och A3 saknar helt "INTE mönstret om"-kriterier — inget av dem slår till: datat behövs bevisligen inte, och mängden är bara .limit():ad i RADER, inte i BYTES (200 rader × obunden blob upp till 4 MiB = teoretiskt 800 MB in i en 1 Gi-podd med EN worker).

DÄR SVEPAGENTEN ÖVERDRIVER: (1) Vägen är KALL, inte het. GET "" anropas bara från bug_reports_admin.js:42 när en admin/Super User öppnar vyn Buggrapporter (`require_view_access("bugReports","view")`) — ingen polling, ingen loop — plus från tools/bug_reports_status.py:36 som agenter kör vid arbetsstart. Ingen slutanvändare i produktion kör detta i volym. (2) Tabellen är sannolikt liten idag: funktionen är ett uttalat experiment (docstring rad 1), 30 dagars retention och 3 rapporter/timme/användare. Realistiskt handlar det om enstaka till tiotals rader, dvs. kanske 5-50 MB per anrop — obehagligt men inte dagens Sankey-OOM. Den påstådda "800 MB" är en pappersgräns, inte ett observerat värde.
(3) `_visible_report_or_404` (194-199) drar mycket riktigt blobben även för PATCH/status och DELETE, men det är ETT rad-hämt per anrop och de anropen är extremt sällsynta. Marginellt.

Jag bekräftar ändå för att fixen är trivial, dokumenterad, beteendebevarande och tar bort en obunden byte-mängd som växer med adoptionen — men den ska prioriteras som hygien/riskbegränsning, inte som latensvinst.

**Justerad vinst (granskarens, inte svepagentens):**

Ingen trovärdig latensvinst att utlova idag — troligen 0-200 ms mot en liten tabell, och jag vägrar sätta en siffra utan produktionsdata (coredata-exemplets -38 % går INTE att överföra: den tabellen har garanterat stora rader, denna kanske inte har några alls än). Den verkliga vinsten är att en obunden per-rad-byte-mängd (200 × upp till 4 MiB) tas ur SELECT + nätverk + Python-heap i en 1 Gi-podd. Med 30 rapporter à ~1 MB (rimlig 30 s rrweb-inspelning) sparas ~30 MB per listanrop; skalar linjärt med hur mycket funktionen används. PATCH/DELETE sparar 1 blobläsning var (försumbart).

**Matning som ska bekrafta vinsten:**

Ingen api_benchmark-endpoint täcker /api/bug-reports (den saknas i tools/latency_budgets.json och tools/api_benchmark.py — grep gav noll träffar). Mät därför så här: (1) Bytes-mätningen är den bindande: skriv ett test i stil med tests/services/test_query_count_budgets.py som seedar N=50 BugReport med ~1 MB events_json var, kör GET /api/bug-reports och asserterar via SQLAlchemy-event `before_cursor_execute` att SELECT:en INTE innehåller kolumnen `events_json`/`context` — plus `tracemalloc`/`resource`-peak före/efter (förväntan: från ~50 MB peak till ~0). Det är den enda mätning som faktiskt bevisar vinsten och som inte kräver produktionsdata. (2) Latens: kör `python -m tools.bug_reports_status --base-url <dev>` med timing före/efter mot en dev-DB som fyllts med samma seed. (3) Om man vill ha en riktig siffra i produktion: kör `SELECT COUNT(*), SUM(events_bytes), MAX(events_bytes) FROM bug_reports` först — om SUM är i ensiffriga MB är hela kandidaten en icke-fråga i praktiken och bör nedprioriteras.

**Forutsattningar innan bygge:**

1) Beteendebevarande: JA för listan — `_report_row` konsumerar ORM-objektet direkt i samma funktion och returnerar en dict, så inga ORM-objekt läcker ut och ingen lazy-load kan triggas. `defer(BugReport.events_json)` + `defer(BugReport.context)` på query:n på rad 179 är därmed bit-identiskt. 2) VARNING på `_visible_report_or_404`: `get_bug_report` (202-217) läser `report.events_json` och `report.context` EFTER anropet — en defer där ger fortfarande korrekt svar men konverterar detaljvyn till 2 rundresor (lazy-load). Det är beteendebevarande på API-nivå men inte gratis; svepagenten redovisar det halvt. Rekommendation: defer:a bara i `_visible_report_or_404` om man samtidigt låter `get_bug_report` hämta blobben explicit (t.ex. egen `db.get(..., options=[undefer(...)])`) — annars rör den inte alls. Notera också att `db.get()` träffar identity-map:en, så options kan tystas ned om objektet redan är i sessionen. 3) Skyddande tester som redan finns och MÅSTE gå gröna: tests/services/test_bug_reports.py, tests/services/test_gap_bug_reports_contract.py (kontraktet för svarets fält), tests/services/test_gap_bug_reports_scoping.py (business_id-scoping), tests/tools/test_bug_reports_status.py, tests/tools/test_bug_report_browser.py. Kontraktstestet är det viktiga: det fångar om defer råkar ändra svarsformen. 4) Kör `SELECT COUNT(*), SUM(events_bytes) FROM bug_reports` i prod INNAN bygget — utfaller den till nästan noll ska kandidaten läggas i backloggen, inte byggas nu.

---

## #29 — /api/allocation/open-excel är web-registrerad utan desktop-guard: bygger hela arbetsboken i podden och kraschar SEDAN alltid

- **Plats:** `app/backend/routers/allocation.py:620-627 → app/backend/allocation_bridge_parts/flow_execution.py:98-115 → app/backend/allocation_bridge_parts/export.py:1-60`
- **Monster:** fel-lager
- **Het vag:** nej · **Insats:** S · **Risk:** medel

**Problem (svepagentens beskrivning):**

> Wikin listar export.py:34 som en tredje "openpyxl utan write_only"-export. Den är något annat och mer intressant: en desktop-funktion som ligger oskyddad i web-API:et.
> 
> open_excel_result anropar först write_table_to_excel(table, ...) — som bygger HELA openpyxl-Workbooken (eller en pandas ExcelWriter för icke-simpla tabeller) i minnet och sparar till temp — och DÄREFTER open_path(path). open_path gör os.startfile på Windows, annars `subprocess.Popen(["xdg-open", path])`. I Linux-podden finns ingen xdg-open och ingen desktop-session → RuntimeError → 500.
> 
> Nettoeffekten är det värsta av två världar: hela minnestoppen betalas, och sedan failar anropet ändå. Routen har ingen desktop-gate — bara require_allocation_tools_user — så vilken inloggad allokeringsanvändare som helst kan trigga den mot podden. Tabellen kommer från allokerings-SESSIONS (plockplan/orderkontroll/refill) och har inget rad…

**Foreslagen atgard:**

> Gate routen till desktop-runtime (eller registrera den bara när local_runtime är aktiv), och/eller ersätt open_path-beteendet i web med en FileResponse så funktionen faktiskt fungerar där i stället för att bara kosta minne. Om web aldrig ska ha den: ta bort routen ur allocation.py — det är "ta bort"-greppet ur wikins lösningskatalog, och det eliminerar hela minnesvägen i stället för att optimera den.

**Skeptikerns granskning:**

Mekaniken stämmer exakt, verifierad rad för rad. (1) allocation.py:620-627: `@router.post("/open-excel")` med enda dependency `require_allocation_tools_user` — noll träffar på is_desktop/local_runtime/DESKTOP i hela app/ (grep), alltså finns ingen gate-mekanism i backend över huvud taget. (2) flow_execution.py:106-107: `path = write_table_to_excel(table, label, ...)` KÖRS FÖRE `open_path(path)`. `table` kommer från `session_table()` (serialization.py:107-113) som gör `pd.read_pickle(path)` på HELA resultattabellen — inte previewen (df_to_table klipper till 1000 rader bara till klienten). Alltså laddas full DF + full openpyxl-Workbook (export.py:45-52, en `sheet.append` per rad, ingen write_only) i podden. (3) export.py:1-10: på icke-Windows/icke-macOS blir det `subprocess.Popen(["xdg-open", path])`. Dockerfile:1 = `python:3.12-slim-bookworm` och apt-raden (rad 13-27) installerar bara curl/gnupg/ca-certificates/libgomp1/tini/msodbcsql18 — **inget xdg-utils**. Popen kastar FileNotFoundError → RuntimeError → HTTPException 500. Web-vägen betalar alltså hela minnestoppen och returnerar sedan alltid 500. (4) Knappen är INTE dold i web: results_flows.js:451 renderar `<button data-open-excel=...>Öppna i Excel</button>` villkorslöst för varje resultattabell, och results.js:112-138 postar till `/open-excel`. (5) Inte fixat: `git log -S "open_path(path)"` senaste träff 7c35c85 (modularisering), wiki/optimeringsplan.md:59 listar det fortfarande som öppen punkt 1.6. EXTRA FYND som ändrar åtgärden: desktop-vägen är också trasig. desktop/local_runtime.py:764/800/805 intercept:ar bara `/api/allokering/flow/` (POST), `table-column` och `download` — `/open-excel` intercept:as INTE och proxas därför upstream (local_app_server.py:138-157) till podden, där sessionen inte existerar (SESSIONS är processlokal och flödet kördes lokalt) → 404 "Resultatet hittades inte". Att bara "gate:a till desktop" gör alltså INTE att funktionen börjar fungera; en desktop-fix kräver att open-excel läggs till i local_runtime. Avfärdande-kriterierna slår inte till: koden gör vad som påstås, det är inte fixat, och datat behövs inte (anropet kan aldrig lyckas i podden).

**Justerad vinst (granskarens, inte svepagentens):**

Ingen latensvinst — noll ms sparas på någon fungerande väg. Vinsten är riskreduktion: en inloggad allokeringsanvändare kan i dag med ett klick tvinga podden att materialisera hela resultattabellen som openpyxl-celler (obundet tak) i en 1 Gi-podd med en uvicorn-worker — samma klass av OOM-hazard som Sankey-incidenten (wiki B2), där en OOM tar ned hela appen för alla (502). Jag kan INTE kvantifiera toppen utan mätning: den beror på radantalet i plockplan/orderkontroll-tabellerna, vilket koden inte begränsar. Svepagentens "tiotals till hundratals MB" är en gissning — behandla den som ospecificerad tills den mätts. Säkert är däremot att 100 % av web-anropen i dag slutar i 500, dvs. all minnes-/CPU-kostnad är ren förlust, samt att en död knapp visas för alla web-användare (UX-bugg).

**Matning som ska bekrafta vinsten:**

Två mätningar, ingen av dem api_benchmark (latens är inte poängen): (1) RAM-tak: kör `write_table_to_excel` mot en representativ pickle från allocation_bridge session-cachen (t.ex. en plockplan) och mät `tracemalloc.get_traced_memory()` + RSS före/efter — det ger det faktiska taket per klick och avgör om OOM-risken är verklig eller marginell. (2) Frekvens: fråga `user_interaction_events` på `control_id='allocation-open-excel'` (registrerad i audit_logs_helpers.py:104) uppdelat på web vs desktop och status ok/error — det visar exakt hur ofta knappen faktiskt trycks i prod och bekräftar 500/404-hypotesen mot loggarna i stället för mot min kodläsning. Kompletterande: verifiera 500 direkt med `python -m tools.flow_cli allocation open-excel` mot en deployad miljö efter ett web-kört flöde.

**Forutsattningar innan bygge:**

Fixen är INTE beteendebevarande — den tar bort (eller ersätter) en synlig knapp, så den kan inte smygas in under "prestandasvep"-flaggan. Måste beslutas med Emir: (a) ta bort routen + knappen i web och behålla "Ladda ner CSV" (finns redan bredvid, results_flows.js:452, och download_result fungerar), eller (b) byt open_path mot FileResponse i web — men notera att (b) INTE tar bort minnestoppen, bara gör att den ger något tillbaka; vill man båda krävs `Workbook(write_only=True)`. Innan bygget: (1) bekräfta att desktop faktiskt är trasig i dag (404-hypotesen ovan) — om ja måste local_runtime-intercept läggas till, annars dödar man en funktion som redan är död och det är fortfarande rätt, men det ska redovisas; (2) skyddande tester i dag är bara enhetstesterna tests/services/test_allocation_bridge.py:2091 och :2117 (`test_open_excel_result_writes_safe_xlsx_and_opens_path` / `..._reports_open_failure`) — de monkeypatchar open_path och måste skrivas om/tas bort med routen; (3) API_ROUTES.md:94, tools/flow_cli.py:650-656/989-993, app/frontend/js/types/api-schema.d.ts och wiki (warehouse-tools.md:374, user-events.md:118, api.md) refererar routen och måste följa med; (4) audit-kontrollen `allocation-open-excel` i audit_logs_helpers.py:104 påverkar täckningsvyn om kontrollen försvinner.

---

## #39 — Sankey: bolag och tidsstämpel parsas om per klientfiltervy (upp till 512 vyer × alla rader)

- **Plats:** `app/backend/sankey_inbound/build_outbound.py:145-152, 189-207 (anropad från app/backend/sankey_inbound/build.py:581-592 i vy-loopen 758-773)`
- **Monster:** B3
- **Het vag:** ja · **Insats:** M · **Risk:** låg

**Problem (svepagentens beskrivning):**

> build_sankey_inbound_payload förbygger klientfiltervyer: `for view_period_type... for view_company... for view_only_consumed:` → `_build_view_payload(...)` (build.py:758-773), med tak CLIENT_FILTER_PREBUILD_MAX_VIEWS = 512 och CLIENT_FILTER_PREBUILD_MAX_SOURCE_ROWS = 75 000 (common.py). Varje `_build_view_payload` anropar `_build_outbound_sankey`, som i sin tur gör en **full omscanning av samtliga pick_rows och dispatch_rows** (build_outbound.py:145-152): `company = _row_company(row)` och `_is_in_date_window(row, ...)`. `_is_in_date_window` → `_row_datetime` → upp till 4 st `_row_value`-uppslag + `_parse_datetime` (strängmanipulation + `strptime`/`fromisoformat`). Ingen av dessa beror på vyn — bolagskoden och tidsstämpeln för en rad är samma i alla 512 vyer. Samma sak i build.py:599-603: `_purchase_line_key(entry["row"])` (= 3 kedjade `_row_value`-uppslag + upper()) räknas om per vy för …

**Foreslagen atgard:**

> Förberäkna en gång per payload, före vy-loopen: bygg `pick_meta = [(row, _row_company(row), _row_datetime(row)) for row in pick_rows]` (och motsvarande för dispatch_rows). Skicka in de dekorerade listorna till `_build_outbound_sankey` så att `pick_rows_by_company`-bygget bara gör två billiga jämförelser per rad (`company in target_companies` och `start <= d <= end`) i stället för en datumparsning. Alternativt: gruppera raderna en gång per (bolag, datum) och låt varje vy bara plocka de nycklar som ligger i sitt fönster — då blir vy-kostnaden O(antal bolag × antal dagar) i stället för O(antal ra…

**Skeptikerns granskning:**

Jag försökte avfärda den och misslyckades på varje punkt.

1) Koden gör det som påstås. build_outbound.py:145-152 scannar hela pick_rows och dispatch_rows i varje anrop: `company = _row_company(row)` + `_is_in_date_window(row, view_period_start, view_period_end)`. Båda är rent vy-oberoende per rad — bolagskoden och tidsstämpeln för en given rad är identiska i alla vyer; bara jämförelsen mot fönstret varierar. rows.py:216-222 visar att `_row_datetime` gör upp till 4 `_row_value`-uppslag + `_parse_datetime`, och rows.py:188-213 att `_parse_datetime` för strängar går via `strptime`/`fromisoformat`. Källraderna ÄR strängar: de kommer som JSON från ExternalDataClient (fetch.py:406-417, `_fetch_view_rows`), och testfixturerna använder `timestamp="2026-06-01T10:00:00"` (tests/services/test_sankey_inbound_service.py:860). Alltså träffar vi strptime-vägen, inte den billiga `isinstance(value, datetime)`-genvägen.

2) Kostnaden är mätt, inte gissad. timeit mot de faktiska helperna med en representativ plockrad: `_row_company` 0,67 µs, `_is_in_date_window` 4,64 µs (varav `_parse_datetime` 4,06 µs) = **5,3 µs per rad och vy**. Den föreslagna billiga jämförelsen (`company in target_companies` + `start <= d <= end` mot förberäknade värden) mäter 0,05 µs. Reduktionen är ~100x på just detta arbete. Svepagentens 2-5 µs var om något i underkant.

3) Multiplikatorn är verklig. `_client_filter_period_specs` (rows.py:50-75) ger för `month` 1 + upp till 31 dagsspecar = 32 st; vyer = specs × (1 + antal bolag) × 2. Med 3 bolag: 32 × 4 × 2 = 256 vyer. `week` ≈ 64 vyer, `year` ≈ 104, tak CLIENT_FILTER_PREBUILD_MAX_VIEWS = 512. Viktigt: build.py:735-743 sätter `interactive_period = requested_period_type in {"day","week","month"}`, och 75k-radtaket (CLIENT_FILTER_PREBUILD_MAX_SOURCE_ROWS) gäller ENDAST om perioden inte är interaktiv — för month prebyggs alltså alla 256 vyerna oavsett hur många plockrader det finns. Radmängden är därmed obunden på just den väg som kostar mest.

4) Vägen är het. Bygget körs synkront inne i requesten vid cache-miss (service.py:152-166, med SSE-progresssteget "Bygger flöde"). Användaren väntar. Detta är inte en engångsbatch.

5) Det är inte redan fixat. `git log -S "_is_in_date_window(row, view_period_start" -- app/backend/sankey_inbound/` ger bara 0c7d84b (filsplitten) och ba7438d — ingen optimering. Tvärtom bekräftar wiki/prestanda-optimeringar.md:181-184 (B3) att man vid 2026-07-08 hoistade `build_package_ladders` ur *exakt denna loop* ("upp till 512x per cache-miss") men lämnade radscanningen kvar. Kommentaren i build_outbound.py:131-134 ("Beräknas normalt en gång i build_sankey_inbound_payload och skickas in; fallback om funktionen anropas fristående") är dessutom en färdig mall för hur fixen ska se ut.

Inget av "INTE mönstret om"-kriterierna slår till: datat behövs (filtreringen måste ske), men *parsningen* behöver inte upprepas; mängden är inte bunden (radtaket är avstängt för day/week/month); reduktionen kan inte flyttas till SQL (raderna kommer från ett externt API, inte MSSQL); och det är en het request-väg, inte en batch.

Två invändningar jag ändå har mot svepagentens förslag:
- Att byta signatur på `_build_outbound_sankey` till "dekorerade listor" är onödigt riskabelt — funktionen re-exporteras via sankey_inbound/__init__.py:110-området och sankey_inbound_service.py. Gör i stället som `package_ladders`: lägg till valfria förberäknade parametrar (t.ex. `pick_meta`/`dispatch_meta`) med fallback när de är None. Då bevaras alla befintliga anropare.
- `_row_company` används även i fallbacken på build_outbound.py:113 (`pick_rows + dispatch_rows` — som dessutom allokerar en ny lista per vy). Den bör dela samma förberäkning.

Ett billigare komplement (inte ersättning) är `lru_cache` på sträng-grenen i `_parse_datetime` — samma trick som wikin redan belönar för `_canonical_header`. Samma tidsstämpelsträngar återkommer i alla 256 vyerna, så träffgraden blir ~255/256. Men det kräver en inre hjälpfunktion som bara tar hashbara `str` (annars TypeError på ohashbara värden) och en maxsize som inte spränger 1 Gi-podden. Hoisting är den rena fixen; cachen är plåster.

**Justerad vinst (granskarens, inte svepagentens):**

Kan inte kvantifieras i absoluta tal utan produktionens radantal — det säger jag rakt ut. Formeln är däremot mätt och exakt: sparad CPU ≈ (len(pick_rows) + len(dispatch_rows)) × (antal_vyer − 1) × ~5,3 µs. Med 256 vyer (month, 3 bolag) blir det ~1,3 s per 1 000 rader, dvs ~13 s vid 10k rader och ~27 s vid 20k rader — men bara ~0,3 s om månaden bara har 250 rader. Jag avvisar svepagentens "minuter vid taken" som teoretisk: den kombinerar 75k rader med 512 vyer, vilket build.py:735-743 aldrig ger samtidigt för icke-interaktiva perioder. Realistiskt spann jag vågar stå för: **några sekunder till ett par tiotals sekunder CPU per cache-miss på week/month/year**, och efter fixen återstår en enda parsning per rad (~0,3 s vid 50k rader). Vinsten är noll på period=day (bara ~8 vyer) — den vägen är kall.

**Matning som ska bekrafta vinsten:**

Det finns INGEN sankey-endpoint i tools/api_benchmark.py eller tools/latency_budgets.json (verifierat med grep) — så api_benchmark duger inte här. Mät i stället:

1. Primär mätning: `build_ms` i loggraden i app/backend/sankey_inbound/service.py:185-189 ("Sankey inbound klar: ... build=%sms"). Tvinga fram en cache-miss (ny cache_key) och kör period=month med ALL-bolag. Notera build_ms före och efter fixen, samt `rows_by_source` från samma loggrad — det ger de faktiska len(pick)/len(dispatch) som hela vinstuppskattningen hänger på. Kör detta FÖRST: om build_ms redan är < 1 s betyder det att radantalen i prod är små och kandidaten degraderas till kosmetisk.

2. Bekräfta att kostnaden ligger där jag påstår: cProfile på ett enda `build.build_sankey_inbound_payload`-anrop med period="month" och verkliga källrader; kontrollera att `_parse_datetime` + `_row_value` står för den andel av cumtime som formeln förutsäger, och att antalet `_parse_datetime`-anrop faller från ~(rader × vyer) till ~(rader) efteråt.

3. Mät alla tre perioderna (day/week/month) — day ska vara oförändrad, week/month ska falla. Om day också faller kraftigt har jag missförstått vy-budgeten.

**Forutsattningar innan bygge:**

Beteendebevarande: ja, men tre fällor måste hanteras explicit.
- `_row_datetime` kan returnera None. `_is_in_date_window` returnerar då False. Den förberäknade varianten måste bevara det: `d is not None and start <= d <= end` — inte `start <= d <= end` mot ett defaultdatum.
- `_is_in_date_window` jämför på `stamp.date()`, inte på datetime. Förberäkna alltså `.date()`, annars ändras gränsfallen vid periodens sista dag.
- `pick_rows_by_company`/`dispatch_rows_by_company` måste fortfarande byggas per vy (target_companies varierar) och radordningen inom varje bolagslista måste bevaras — trace_rows och nodordning hänger på den. Gör hoistningen till en dekorerad lista i samma ordning som originalet.
- Behåll signaturen på `_build_outbound_sankey` bakåtkompatibel (valfria parametrar med None-fallback, precis som `package_ladders` på rad 131-134), eftersom funktionen re-exporteras via sankey_inbound/__init__.py och sankey_inbound_service.py.

Skyddande tester som redan finns (kör dessa som differentialtest före/efter):
- tests/services/test_sankey_inbound_service.py — särskilt raderna ~860-872, som bygger en payload och sedan hävdar att `all_payload["client_filters"]["only_consumed"]["summary"|"nodes"|"links"]` är IDENTISKA med en separat, direktbyggd `consumed_payload`. Det är precis den golden-karakterisering som behövs: den fångar varje avvikelse mellan en prebyggd vy och en direktbyggd. Utöka den med ett fall där en rad saknar tidsstämpel (timestamp="") och ett där tidsstämpeln ligger utanför fönstret, så None-fällan ovan täcks.
- tests/tools/test_sankey_frontend_contracts.py och tests/tools/test_gap_sankey_browser.py skyddar payload-formen mot frontend.

Innan fixen byggs: kör mätning 1 ovan och läs av rows_by_source. Om pick+dispatch i prod är i storleksordningen hundratals rader, inte tusentals, är vinsten en bråkdel av en sekund och kandidaten bör nedprioriteras trots att mönstret är korrekt identifierat.

---

## #40 — KPI-regelmotorn: predikatet slår upp Från/Till/Lokation ovillkorligt för varje (regel, händelse)

- **Plats:** `app/backend/productivity_kpi_rules/rules.py:405-407 (i predikatet 394-437)`
- **Monster:** B4
- **Het vag:** ja · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> `_rule_predicate` bygger ett closure-predikat som körs för varje (regel, händelse)-par i `score_kpi_events` (scoring.py:236-243). Efter bolags-/zon-/typ-/statuskontrollerna gör det **ovillkorligt** tre uppslag: `loc_from = _row_text(event.row, "Från", "Fran", "loc_from")`, `loc_to = _row_text(...)`, `location = _row_text(...)` — även när regeln inte har några loc-kriterier alls. Av de 44 reglerna i SQL_REFERENCE_KPI_RULE_ROWS (rules.py:53-96) har ~34 inga loc_*-kriterier; för alla pick-baserade rows/packages-regler (~22 st) är alla tre uppslagen ren spillan. Värre: när kolumnen inte finns i loggen (plockloggen har varken "Från", "Till" eller "loc_from") tar `_row_text` sin **dyra miss-väg** — `_get` returnerar "", sedan byggs ett alias-set och alla radens headers scannas med `_canonical_header` per header (rules.py:195-203). Detta är kvarvarande kostnad **efter** den redan gjorda `_canon…

**Foreslagen atgard:**

> Beräkna loc-värdena lat, bara när motsvarande kriterier finns:
> ```python
> if loc_from_equals or loc_from_not_equals or loc_from_starts or loc_from_not_starts:
>     loc_from = _row_text(event.row, "Från", "Fran", "loc_from")
>     ...kontrollerna...
> ```
> Samma för loc_to och location. Ännu renare: komponera vid parsningen (`parse_kpi_rule_rows`) en lista av check-closures som bara innehåller de kontroller regeln faktiskt har, och kör `all(check(event, context) for check in checks)`. Beteendet är identiskt — värdena används i dag bara i grenar som är döda när kriterielistan är tom. OBS: den redan för…

**Skeptikerns granskning:**

Koden gör exakt det som påstås. rules.py:405-407 slår ovillkorligt upp loc_from/loc_to/location innan någon av grenarna 408-427 ens kollas, och grenarna är döda när kriterielistan är tom. Svepagenten MISSADE dessutom en fjärde ovillkorlig lookup: rules.py:430 `sscc = _row_text(event.row, "SSCC", "sscc")` — den körs för alla 44 regler fast bara 2 (Sort_Ecom/Sort_Store, rules.py:78-79) har sscc-kriterier. _row_text (rules.py:195-203) har den dyra miss-vägen: `_get` (productivity_service.py:711) → tom → alias-set + scan av alla radens headers via _canonical_header. Plockloggen har varken Från/Till eller SSCC → tre garanterade missar per (matchande regel, plockhändelse). Predikatet körs i score_kpi_events (scoring.py:236-243) som rules × events-of-that-source, efter zon-/typ-filtret — så bara zonmatchande händelser når rad 405, men det är fortfarande ~2 rules/event för plock (rows+packages per zon). Vägen är INTE kall: score_kpi_events körs både i bakgrundsbygget (person_productivity_cache.py:837, productivity_cache_warm) OCH i request-vägen vid cache-miss (routers/personal.py:467 och routers/productivity.py via build_person_productivity_report_from_files) — en användare väntar, på den enda uvicorn-workern. Redan fixat? Nej: git log på filen visar bara 141b4cc (_canonical_header-memoisering) och ea258ab (paketering). Wikin (prestanda-optimeringar.md:188-202) dokumenterar memoiseringen och en FÖRKASTAD per-kolumnuppsättnings-cache i _row_text — lärdomen där ("nästa lager är call-overhead, inte beräkning") talar FÖR den här fixen, som tar bort anropen i stället för att lägga på en cache till. Inga "INTE mönstret om"-kriterier slår till: datat behövs faktiskt inte, mängden är obunden (växer med plockloggen), reduktionen kan inte uttryckas i SQL (CSV-loggar in-memory). Jag byggde och mätte fixen: syntetisk plocklogg 60k rader (20 kolumner) + 10k transrader, alla 44 referensregler, targets för 2 bolag. Differentialtest: identisk lista KpiPointEvent (108788 st, `a == b` True). Tid: baseline min 5,70 s → lat loc+sscc min 4,38 s = **-23 %**. Antal _row_text-anrop per bygge: 2,10M varav 338k missar.

**Justerad vinst (granskarens, inte svepagentens):**

~20-25 % av CPU-tiden i score_kpi_events (mätt: -23 % på syntetisk 60k-raders plocklogg, differentialtest bit-identiskt). Absolut vinst i prod kan jag INTE kvantifiera — den beror helt på verklig plockloggsstorlek per dag, som jag inte har. Kandidatens "flera hundra ms" är plausibel men obekräftad; jag garanterar bara den relativa vinsten. Notera att fixen måste omfatta ÄVEN sscc-uppslaget (rules.py:430), annars blir vinsten mindre än min mätning. Vinsten träffar både bakgrundsbygget och cache-miss i /api/productivity + personal-rapporten.

**Matning som ska bekrafta vinsten:**

1) Mikro/differential: kör om mitt skript (scratchpad/bench40b.py) — score_kpi_events med alla 44 SQL_REFERENCE_KPI_RULE_ROWS mot samma rows_by_source före/efter; assert att listan KpiPointEvent är identisk och mät min-tid över 3 körningar. 2) Realistisk: cProfile på build_person_productivity_report_from_files mot en riktig dagssnapshot (productivity_snapshot_files) — jämför kumulativ tid i rules.predicate och _row_text före/efter. 3) End-to-end: `python -m tools.api_benchmark` mot produktivitets-/personal-endpointen med tömd _PERSONAL_PRODUCTIVITY_REPORT_CACHE (cache-miss = worst case) och jämför median mot tools/latency_budgets.json.

**Forutsattningar innan bygge:**

Beteendebevarande: ja, verifierat — loc_from/loc_to/location/sscc används enbart i grenar som är no-ops när respektive kriterielista är tom, och _row_text är biverkningsfri läsning. Kravet är att gate-villkoren matchar EXAKT de grenar som använder värdet (loc_from: equals/not_equals/starts/not_starts; loc_to: dito; location: starts/not_starts; sscc: length_lt>0 or length_gte>0). Före bygge: (a) kör golden-/differentialtest enligt ovan på en riktig dagssnapshot, inte bara syntetisk data (regelbladet kan i en kundmiljö komma från annan källa än SQL_REFERENCE_KPI_RULE_ROWS — load_kpi_rules returnerar dock idag alltid de interna raderna, rules.py:519, så kriteriemängden är i praktiken låst); (b) skyddande tester som måste vara gröna: tests/services/test_productivity_v2.py (pick/trans-CSV-fixturer → processrader), tests/services/test_productivity_service.py, test_productivity_router.py, test_gap_productivity_finance_guards.py. Om man går på den "renare" varianten (lista av check-closures) ökar risken för beteendedrift genom ändrad kontrollordning — ordningen spelar roll först när en check har biverkningar, vilket ingen har, men gör då diffen större än S. Rekommendation: gör den enkla if-gaten.

---

## #41 — Allokering/refill: fifo_for_art gör en full boolean-scan av hela bufferten per artikel (kvadratisk)

- **Plats:** `warehouse_tools/engine_core/allocation.py:730-734 (anropad i loopen 745-766 och 810-812)`
- **Monster:** B4
- **Het vag:** ja · **Insats:** S · **Risk:** medel

**Problem (svepagentens beskrivning):**

> `fifo_for_art(art_key)` gör `d = b[b["_artikel"] == art_key].copy()`, därefter `d[~d["_source_id"].astype(str).isin(used_help_ids)].copy()` och `d.sort_values("_received")`. Den anropas **en gång per artikel** i huvudplock-loopen (`for art_key, grp_art in needs.groupby("_art")`, rad 745 → 766) och en gång till per artikel i autostore-loopen (rad 810-812). Varje anrop är en full scan av hela buffertramen `b` + två `.copy()` + en `astype(str)` + en sort. Med A artiklar och B buffertrader blir det O(A × B) — och `astype(str)`-konverteringen av `_source_id` görs om från grunden A gånger fastän `used_help_ids` är konstant genom hela loopen (B3 inuti kvadraten). Artiklar som förekommer i både huvudplock och autostore får dessutom samma FIFO-ram byggd två gånger.

**Foreslagen atgard:**

> Hoista ut det artikel-oberoende arbetet en gång före loopen: (1) filtrera bort använda helpallar en gång — `b_avail = b[~b["_source_id"].astype(str).isin(used_help_ids)]` (skippa om `used_help_ids` är tom); (2) sortera en gång med stabil sort — `b_sorted = b_avail.sort_values("_received", kind="mergesort")`; (3) gruppera en gång — `fifo_by_art = dict(tuple(b_sorted.groupby("_artikel", sort=False)))` och byt `fifo_for_art(art)` mot `fifo_by_art.get(art)` (guarda mot None, precis som ordersaldo-fixen redan gör i ordersaldo.py:391-414). Samma mönster, samma vaktkommentar. Ta även `_qty`-summan pe…

**Skeptikerns granskning:**

Koden gör exakt det som påstås: allocation.py:730-734 `d = b[b["_artikel"] == art_key].copy()` + `.isin(used_help_ids)` + `.sort_values("_received")`, anropad per artikel på rad 766 (huvudplock) och 812 (autostore). `used_help_ids` sätts på rad 697-699 före loopen och muteras aldrig. Inte fixat: git log på filen visar bara 2 commits (55ef3b2, 5906d03), båda strukturella, och posten ligger kvar som öppen punkt 4.2 i wiki/optimeringsplan.md:120-123.

MEN svepagentens siffror är fel, och jag mätte i stället skarpt mot testdata/warehouse_tools (v_ask_customer_order_details_all-20260519090642.csv, 18 382 orderrader + v_ask_article_buffertpallet-20260519090645.csv, 57 532 buffertrader):
- Buffert efter statusfilter {29,30}: 22 830 rader (inte 30 000). used_help_ids = 401.
- fifo_for_art anropas 278 ggr, INTE 3 000 — de flesta artiklar `continue`:ar på rad 751 (adjusted_total <= 0) innan anropet. "90M elementjämförelser / 6 000 kopior" är alltså ~5x överdrivet.
- Svepagentens B3-poäng ("astype(str) görs om A gånger") är i praktiken irrelevant: `astype(str)` körs på delmängden `d`, inte på hela `b`, och `_source_id` är redan str (rad 689).

Kostnaden är ändå verklig: cProfile ger fifo_for_art 2,32 s cumtime av calculate_refill:s 5,94 s (under profiler); ren wall-clock är calculate_refill 3,00 s varav de 268 verkliga anropen mäter 1,63 s. Hela allocate-flödet är ~6,6 s (allocate 3,55 s + refill 3,00 s). Vägen är användarväntande: calculate_refill körs i `_allocation_outputs_cached` (allocation_flows.py:78-102), dvs. en gång per filversionsuppsättning — men det är precis den körningen användaren står och väntar på efter uppladdning. Varma omkörningar är gratis (lru_cache).

VIKTIGT — svepagentens föreslagna åtgärd är INTE beteendebevarande, och det redovisas bara som "risk medel". Jag testade den: global `sort_values("_received", kind="mergesort")` + groupby ändrar radordningen för 136 av 2 406 artiklar och ändrar utdatakolumnen "FIFO-baserad beräkning" för 1 av 268 verkliga artiklar. Golden-testet tests/services/golden/warehouse_flows/allocate.json innehåller refill_hp med just den kolumnen och skulle brinna.

Dessutom: den naiva `dict(tuple(b_sorted.groupby("_artikel")))` på hela 31-kolumnsramen kostar 1,47 s och äter upp nästan hela vinsten. Fixen måste (a) gruppera en slimmad projektion (['_artikel','_qty','_received','_source_id']) → 0,196 s, eller helst bygga dict art -> numpy-array av _qty → 0,022 s, och (b) BEHÅLLA per-grupp `sort_values("_received")` med pandas default (quicksort) i stället för en global stabil sort. Eftersom groupby bevarar originalradordningen inom gruppen får per-grupp-argsorten exakt samma indataarray som idag → bit-exakt utdata, och den kvadratiska delen (boolean-scanen över hela b per artikel) försvinner ändå.

**Justerad vinst (granskarens, inte svepagentens):**

Mätt på största verkliga testdatan: ~1,4-1,6 s bort av calculate_refill:s 3,0 s (fifo-delen 1,63 s -> 0,02-0,20 s). Hela allocate-flödets kalla körning ~6,6 s -> ~5,1 s, dvs ~20-25 %. Skalar med buffertstorlek × antal bristartiklar, så vinsten är större på tyngre dagar och nära noll på små uppladdningar. Bara första körningen per filversion (lru_cache), inte per request.

**Matning som ska bekrafta vinsten:**

Ingen api_benchmark-endpoint behövs — mät direkt i motorn. Före/efter: tidta `E.calculate_refill(result_df, buffer_raw, saldo_df=saldo_norm)` med testdata/warehouse_tools/v_ask_article_buffertpallet-20260519090645.csv + v_ask_customer_order_details_all-20260519090642.csv + v_ask_item_summary_stock_automation-20260519090648.csv (baslinje jag mätte: 3,00 s wall, fifo-andel 1,63 s / 268 anrop). Komplettera med cProfile sorterad på cumulative och kontrollera att allocation.py:730 försvinner ur topplistan. Rapportera även totaltid för flow_allocate kallt (baslinje ~6,6 s).

**Forutsattningar innan bygge:**

1) Fixen MÅSTE vara bit-exakt: behåll per-grupp `sort_values("_received")` (pandas default quicksort) — byt INTE till global mergesort, det ändrar "FIFO-baserad beräkning" för minst 1 av 268 artiklar på verklig data. 2) Guarda mot att groupby aldrig ger tomma grupper: `fifo_by_art.get(art)` kan bli None (inte tom DataFrame) — samma vakt som ordersaldo.py:408-414. 3) Skyddande tester som måste gå igenom oförändrade: tests/services/test_warehouse_flow_characterization.py mot golden tests/services/golden/warehouse_flows/allocate.json (innehåller refill_hp + FIFO-kolumnen) och golden_synthetic/warehouse_flows/allocate.json, samt tests/services/test_warehouse_tools_local_data.py. 4) Gruppera en slimmad kolumnprojektion — groupby på hela 31-kolumnsramen kostar 1,47 s och neutraliserar vinsten. 5) Rör inte `used_help_ids`-semantiken (tom mängd = ingen filtrering).

---

## #42 — HIB-koppling: pd.to_datetime per rad + omfiltrering av kundgruppen per HIB-order

- **Plats:** `warehouse_tools/engine_core/hib.py:195-217 (_choose_earliest), 251, 299-308, 340`
- **Monster:** B1
- **Het vag:** ja · **Insats:** L · **Risk:** medel

**Problem (svepagentens beskrivning):**

> `compute_hib_koppling` (kör via flödet `hib-koppling`, warehouse_tools/flows/report_flows.py:30-33, registrerat i flows/__init__.py:196 och app/backend/workflow_data.py:171 — dvs. en användare klickar och väntar) har fyra staplade problem inuti en `for kund_nr, kund_df in ov.groupby("Kund nr")`-loop:
> 1. `_choose_earliest` (195-217) itererar med `df.iterrows()` och anropar **`pd.to_datetime` på en skalär två gånger per rad** (rad 202-203). Skalär `pd.to_datetime` kostar ~50-100 µs. Funktionen anropas dessutom en gång per HIB-order (rad 305/310), inte bara en gång per kund → O(hib-ordrar × butiksordrar) skalära datumparsningar.
> 2. Rad 299-308: bool-masken `store_df["Sändningsnr"].astype(str).str.strip() == cur_ship` plus `store_df["Ordernr"].map(lambda x: _store_kname(x) == hib_kundnamn)` byggs om **per HIB-order** över hela store_df — samma `astype(str).str.strip()` görs om varje varv (B3…

**Foreslagen atgard:**

> (a) Ersätt `details["Status"].apply(to_status_numeric)` med `pd.to_numeric(details["Status"], errors="coerce").fillna(9999).astype(int)` (semantik: `int(float(x))` → trunkering; använd `.astype(int)` efter fillna, verifiera mot golden). (b) Parsa `Orderdatum` **en gång** för hela `ov` med `smart_to_datetime` till en `_orderdatum_dt`-kolumn och byt `_choose_earliest` mot `df.loc[df["_orderdatum_dt"].idxmin()]` med NaT-fallback på strängjämförelse — samma vinnare, noll skalära `pd.to_datetime`. (c) Förnormalisera `Sändningsnr`, `Zon` och `Ordernr` som egna kolumner en gång före loopen; bygg per …

**Skeptikerns granskning:**

Koden finns och är B1 — men svepagentens diagnos och aritmetik är i huvudsak fabricerad, och jag skriver ner den kraftigt.

VAD SOM STÄMMER: hib.py:195-217 itererar med `df.iterrows()` och kallar `pd.to_datetime` skalärt två gånger per rad; hib.py:299-308 bygger om `store_df["Sändningsnr"].astype(str).str.strip() == cur_ship` + `.map(lambda...)` per HIB-order; hib.py:251 och :340 omfiltrerar `kund_df` per HIB-order. Anropskedjan stämmer (report_flows.py:30-33 → flows/__init__.py:196 → workflow_data.py:171), dvs. användare klickar och väntar.

VAD SOM INTE STÄMMER (mätt, inte gissat — profilerat mot den riktiga regressionsdatan testdata/warehouse_tools/v_ask_order_overview-20260519090657.csv + v_ask_customer_order_details_all-20260519090642.csv):
- Overview = 1570 rader, 175 kunder, **max 2 butiksordrar per kund** (median 1). Svepagentens scenario "500 kunder à 10 HIB-ordrar och 20 butiksordrar" existerar inte.
- `_choose_earliest` anropas **153 gånger** totalt, inte O(100k). Varje anrop itererar över 1-2 rader → ~600 skalära `pd.to_datetime`, inte 200k. Påståendet "5-10 s bara där" är fel med ~en tiopotens.
- Föreslagen åtgärd (a) — byta `details["Status"].apply(to_status_numeric)` mot `pd.to_numeric` — är **värdelös**: apply:t över 18382 rader mätte **0,013 s**. Den delen av fixen ska strykas (och den är dessutom inte semantiskt gratis: `int(float("inf"))` → 9999 i dag, men `astype(int)` på inf ger skräp).

VAD SOM FAKTISKT ÄR DYRT (cProfile, tottime/cumtime):
- Totalt: `compute_hib_koppling` ~2,5 s, `compute_missed_departures` ~0,8 s → flödet ~3,3 s CPU för en 1570-radersfil. Det är absurt långsamt för datamängden, så kostnaden är verklig även om orsaken inte är den påstådda.
- `_hib_orders_with_today_origin` (hib.py:32): ~0,68 s cum, anropas **en gång per kund (175x)** och kör `smart_to_datetime` på gruppens `Ursprungsdatum` varje gång. Ren B3 — svepagenten nämner den inte alls, men det är den enskilt största posten.
- `iterrows`/`.values` över en 45-kolumners arrow-string-backad frame: `_interleave` + `take_nd` ~0,7 s. Kostnaden ligger i radmaterialiseringen, inte i datumparsningen.
- Bool-mask-omfiltrering per HIB-order (818 `_getitem_bool_array`): ~1,26 s cum. Det är den delen av påståendet som håller.
- `order_zones = groupby(...).apply(lambda ...)` (hib.py:146): 0,135 s — modest men gratis att fixa.

INTE-MÖNSTRET-KRITERIER slår INTE till: datat är inte redan bundet till en trivial mängd (2,5 s för 1570 rader visar att kostnaden är per-rad-overhead, inte volym), det är ingen engångsbatch, och användaren väntar. C1 är redan hanterad (allocation.py:520 kör handlern via `run_in_threadpool`), så det fryser inte event-loopen — men användaren väntar fortfarande, och podden har CPU-limit 300m vilket sannolikt gör det värre i prod än på min maskin. `git log` på filen visar bara flytten ur vendor-monoliten (5906d03) — aldrig optimerad.

**Justerad vinst (granskarens, inte svepagentens):**

~2,5 s → uppskattningsvis 0,1-0,3 s för `compute_hib_koppling` (~10x), och ytterligare ~0,7 s om `compute_missed_departures` (samma B1-mönster, samma flöde, ignorerad av kandidaten) tas med. Total realistisk vinst för flödet: **~3,3 s → under 0,5 s**. Detta är mätt på min dev-maskin med den riktiga regressionsfilen; under poddens 300m CPU-limit är absolutsiffrorna sannolikt högre men relationen densamma. Svepagentens "5-10 s bara i _choose_earliest" avvisas — den posten är ~0,6 s cum totalt.

**Matning som ska bekrafta vinsten:**

Ingen api_benchmark-endpoint täcker detta (flödet går via POST /api/allocation/flows/hib-koppling med uppladdade filer). Mät i stället direkt:

1. Före/efter-timing av `warehouse_tools.flows.report_flows.flow_hib_koppling` med `testdata/warehouse_tools/v_ask_customer_order_details_all-20260519090642.csv` (details) + `v_ask_order_overview-20260519090657.csv` (overview), 3 körningar, rapportera median för `compute_hib_koppling` och `compute_missed_departures` separat. Baslinje som jag mätt: 2,5 s respektive 0,8 s.
2. cProfile före/efter och kontrollera att `_hib_orders_with_today_origin`, `_getitem_bool_array` och `frame.values/_interleave` försvinner ur toppen — det är dessa som ska dö, inte `pd.to_datetime`.
3. Beteendekontroll: `pytest tests/services/test_warehouse_flow_characterization.py -k hib` måste passera oförändrad (golden mot exakt samma filer).

**Forutsattningar innan bygge:**

1. GOLDEN FINNS REDAN: `tests/services/test_warehouse_flow_characterization.py` kör hib-koppling mot exakt de två filer jag profilerade — det är skyddet. `tests/services/test_warehouse_tools_local_data.py` (förväntar 49 ändringar / 1 missad) **skippar lokalt** eftersom 20260317-fixturerna inte finns i repot; förlita dig inte på den utan verifiera i CI.

2. `_choose_earliest` är INTE trivialt utbytbar mot `idxmin`. Nuvarande semantik: (a) första raden är default; (b) en icke-NaT slår alltid en NaT; (c) om BÅDA är NaT jämförs **rådatumsträngarna** lexikografiskt; (d) strikt `<` → vid lika datum vinner den FÖRSTA raden. `idxmin` hoppar över NaT helt och har ingen strängfallback. En naiv ersättning ändrar vinnare när alla datum i en kandidatmängd är oparsbara. Kräver differentialtest över permuterade indata (inkl. tomma/skräpdatum och lika datum) innan bytet.

3. `_hib_orders_with_today_origin` beror på `pd.Timestamp.now().date()` — golden-testet är tidsberoende. Hoista datumparsningen till hela `ov` en gång, men bevara try/except-fallbacken till strängjämförelse mot `%Y-%m-%d` exakt.

4. Stryk delen (a) av föreslagen åtgärd (Status.apply) — mätt till 0,013 s, ingen vinst och en semantikrisk utan uppsida.

5. Ta med `compute_missed_departures` (hib.py:368-482) i samma fix — samma mönster, samma flöde, och dess `except Exception: return tom DataFrame` runt hela kroppen döljer regressioner tyst. Verifiera att den swallow:en inte börjar maskera nya buggar.

---

## #45 — Allokering: groupby().apply(lambda) och iterrows i saldo-/NPU-förarbetet

- **Plats:** `warehouse_tools/engine_core/allocation.py:706-714, 725, 805-807`
- **Monster:** B1
- **Het vag:** ja · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> Tre direkta träffar på B1-signaturen i refill-förarbetet, alla i samma funktion som kandidat 3:
> - Rad 725: `npu.groupby(...)[qty_col].apply(lambda s: float(pd.to_numeric(s, errors="coerce").fillna(0).sum()))` — groupby med Python-callable; pandas tappar den kompilerade C-vägen och kör `pd.to_numeric` per grupp.
> - Rad 805-807: identiskt mönster för autostore-behovet.
> - Rad 706-714: `for _, r in s_norm.iterrows():` över hela saldofilen (en Series per rad, ~50-100x dyrare än vektoriserat) för att bygga `saldo_sum` (summa per artikel) och `plockplats_by_art` (första icke-tomma plockplats per artikel).

**Foreslagen atgard:**

> Rad 725/805: konvertera först, gruppera sedan — `pd.to_numeric(npu[qty_col], errors="coerce").fillna(0).groupby(npu[art_col].astype(str).str.strip()).sum().to_dict()`. Samma resultat, inbyggd C-aggregering. Rad 706-714: `saldo_sum = pd.to_numeric(s_norm["Plocksaldo"], errors="coerce").fillna(0).groupby(art).sum().to_dict()` och `plockplats_by_art` via mask på icke-tom/icke-NaN Plockplats + `groupby(art).first()` (matcha semantiken: originalet tar *första icke-tomma* i radordning, inte första raden). Vakta NaN → "" precis som kommentaren på rad 710-711 påminner om.

**Skeptikerns granskning:**

Koden finns exakt som påstått: allocation.py:706 `for _, r in s_norm.iterrows():`, :725 `npu.groupby(...)[qty].apply(lambda s: float(pd.to_numeric(...).fillna(0).sum()))`, :805-807 samma mönster för autostore. Git-historiken visar bara två commits på filen (5906d03 uppdelning, 55ef3b2 kvalitetspaket) — inget vektoriseringssvep har rört calculate_refill, till skillnad från reports.py/observations.py/ordersaldo.py som listas i wiki/prestanda-optimeringar.md. Alltså INTE redan fixat.

MEN svepagenten har fel om VARFÖR det kostar. Enda anroparen är warehouse_tools/flows/allocation_flows.py:98, som skickar in `saldo_norm` — dvs saldo är REDAN normaliserat (en rad per artikel) via `_normalized_saldo_cached`. calculate_refill:705 kör `normalize_saldo` en ANDRA gång på redan normaliserad data. iterrows-loopen itererar därför inte "hela saldofilen per plockplats" utan en rad per artikel — och accumuleringen `saldo_sum[art] = saldo_sum.get(art,0)+...` är strukturellt en no-op (aldrig fler än en rad per nyckel). Loopen är i praktiken bara DataFrame→dict.

Mätt på riktig testdata (testdata/warehouse_tools/v_ask_item_summary_stock_automation, 21 669 rader/artiklar; v_ask_booking_putaway, 581 rader/438 grupper):
- iterrows-loopen 706-714: 0,36-0,50 s → vektoriserat 0,052 s (~7x)
- groupby-apply 725 (NPU): 0,035 s → 0,0023 s (~15x)
Differentialtest: saldo_sum identisk (21 669 nycklar), plockplats_by_art identisk (7 896 nycklar), npu_sum identisk. Bit-identiskt.

Rad 805-807 kunde jag INTE mäta utan en full allokeringskörning (grupperna = distinkta AUTOSTORE-artiklar i resultatet). Antar tiotals ms — låg konfidens där.

Sidofynd, större än en av B1-träffarna: den redundanta `normalize_saldo(saldo_df)` på rad 705 kostar ytterligare ~0,39 s på redan normaliserad indata (B3 omräkning). Den bör tas i samma svep — men den är inte denna kandidat.

Ingen "INTE mönstret om"-kriterium slår till: datat är inte litet (21,7k), vägen är inte kall (allokeringsflödet är användarvänt, redan flyttat till trådpool per wiki C1), och det är inte en engångsbatch. Cachen (`_allocation_outputs_cached`, lru maxsize=16) dämpar dock: kostnaden betalas per unik filversionskombination — dvs vid varje ny uppladdning, vilket är normalfallet.

**Justerad vinst (granskarens, inte svepagentens):**

~0,40-0,55 s sparad wall-clock per allokerings-cache-miss (mätt: 0,36-0,50 s → 0,05 s på saldo-loopen, 0,035 s → 0,002 s på NPU). Inte "100x" som wikins dispatch-/D-pak-exempel — det är 7x resp. 15x, för att grupp-/radantalen är 1-2 storleksordningar mindre. Andelen av total flow_allocate-tid kan jag INTE kvantifiera utan full körning; `fifo_for_art` (rad 730-734: boolean-mask + copy + sort över hela buffertfilen, 57k rader, per artikel) dominerar sannolikt funktionen och gör den relativa vinsten mindre imponerande än den absoluta. Tar man även den redundanta normalize_saldo på rad 705 blir totalen ~0,8-0,9 s.

**Matning som ska bekrafta vinsten:**

Ingen api_benchmark-endpoint täcker warehouse-flödena (tools/latency_budgets.json saknar allocation; tools/performance_benchmark.py rör inte flows). Mät i stället end-to-end: skript som anropar `warehouse_tools.flows.allocation_flows.FLOW_BY_ID["allocate"]["handler"]` mot testdata/warehouse_tools (orders=v_ask_customer_order_details_all, buffer=v_ask_article_buffertpallet, saldo=v_ask_item_summary_stock_automation, not_putaway=v_ask_booking_putaway) med `flows.clear_allocation_cache()` före varje körning, 5 varv, median före/efter. Komplettera med cProfile på calculate_refill för att bekräfta att posterna 706/725/805 faller ur toppen och att fifo_for_art blir den nya toppen.

**Forutsattningar innan bygge:**

1) Golden-karakterisering finns redan och skyddar: tests/services/golden/warehouse_flows/allocate.json och tests/services/golden_synthetic/warehouse_flows/allocate.json innehåller refill_hp- och refill_autostore-tabellerna. Kör båda före/efter — de måste vara oförändrade. Även tests/services/test_warehouse_tools_local_data.py och test_engine_properties.py (test_normalize_saldo_never_leaks_nan_and_sums_per_article).
2) Beteendebevarande kräver fyra saker: (a) behåll `groupby(..., sort=True)` — `behov_per_art_as` (rad 810) ITERERAS och matar rows_as, som sedan sorteras stabilt på rad 836; ändrad nyckelordning ändrar tie-break-ordningen i utdatatabellen. (b) Behåll NaN→"" -vakten (rad 710-712, kommenterad buggfix, se wiki/log.md:2912) — bygg plockplats_by_art via mask på icke-tom sträng + `groupby().first()`, inte `first()` på hela kolumnen. (c) Behåll try/except-fallbacken till tomma dictar. (d) Flyttalsassociativitet är INTE en risk här eftersom s_norm har exakt en rad per artikel — men det gäller bara så länge rad 705 kvarstår; tar man bort den redundanta normalize_saldo måste summeringen verifieras om.
3) Verifiera att ingen annan anropare skickar in ORMnormaliserad saldo_df — grep visar bara allocation_flows.py:98 och tester.

---

## #47 — GZipMiddleware kör på Starlettes default compresslevel=9 — 4x CPU på event-loopen för 7 % färre bytes

- **Plats:** `app/backend/main.py:319`
- **Monster:** konfig-antagande
- **Het vag:** ja · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> `app.add_middleware(GZipMiddleware, minimum_size=1024)` sätter bara minimum_size. Starlettes signatur är `__init__(self, app, minimum_size=500, compresslevel=9)` (verifierat mot installerad starlette 1.3.1), så vi kör på **nivå 9** — deflate-nivån med brantast avtagande avkastning. GZipResponder komprimerar synkront i ASGI-send-vägen, alltså **på event-loopen**. Appen kör 1 uvicorn-worker (arkitekturkontraktet), så varje komprimering fryser alla andra requests medan den pågår — samma systemeffekt som mönster C1. Ingen har mätt valet; det är library-defaulten som fått stå.

**Foreslagen atgard:**

> `app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)` (eller 5). En rad. Verifiera med `python -m tools.api_benchmark --budget` före/efter. minimum_size=1024 är däremot rimligt satt och behöver inte röras.

**Skeptikerns granskning:**

Koden gör exakt det som påstås. app/backend/main.py:319 är `app.add_middleware(GZipMiddleware, minimum_size=1024)`, och installerad starlette 1.3.1 har `def __init__(self, app, minimum_size: int = 500, compresslevel: int = 9)` (verifierat med inspect.signature + källan till GZipResponder.__init__, som skapar `gzip.GzipFile(..., compresslevel=compresslevel)`). Grep på `compresslevel` ger noll träffar i app/, tests/ och k8s/ — bara wiki/optimeringsplan.md:67 (punkt 2.1) och wiki/log.md nämner det som ETT ÖPPET FÖRSLAG. `git log --oneline -- app/backend/main.py` visar att raden kommer från 1793f32 (leveransoptimeringen) och aldrig rörts. Alltså inte fixat. Middleware-ordningen är också som påstås: gzip läggs sist (rad 319) efter alla @app.middleware("http") (127/146/241/261/278), dvs YTTERST. Det betyder att api_get_etag-middlewaren (278-313) hashar den OKOMPRIMERADE bodyn — ett nivåbyte kan därför inte ändra ETags eller trigga cache-missar. Fixen är beteendebevarande mot klienten (gzip-strömmen är självbeskrivande; bara Content-Length ändras). Egen mätning bekräftar avvägningen kvalitativt: app/frontend/css/styles.css (207 KiB) lvl9 = 7,7 ms/31 KiB vs lvl6 = 3,6 ms/31 KiB (IDENTISK output-storlek); rrweb.min.js (259 KiB) lvl9 = 9,7 ms/80 KiB vs lvl6 = 7,1 ms/81 KiB; syntetisk 427 KiB JSON lvl9 = 11,3 ms/36 KiB vs lvl6 = 3,0 ms/39 KiB. Mönstret (3-4x CPU för 0-8 % bytes) håller. MEN svepagentens vinstsiffror är kontextuellt uppblåsta: de bygger på 705 KiB/1,93 MB-payloads som appen till stor del INTE gzippar — Sankey och Produktivitetsöversikten levereras via SSE, som Starlette undantar från GZipMiddleware (wiki/prestanda-leveranslager.md:20-23, wiki/optimeringsplan.md:88-95). Och de statiska filerna är immutable-cachade + service-worker-cachade (samma wiki-sida punkt 2 och 4), så de komprimeras nästan bara vid första besök/efter deploy. Kvar som verkligt gzip-flöde: vanliga API-GET >1024 B (overview/schedule/persons/summary/meta-listan), vars faktiska storlek är OMÄTT — tools/api_benchmark.py registrerar varken content_length eller content-encoding (plan-punkt 0.1 i wiki/optimeringsplan.md:40).

**Justerad vinst (granskarens, inte svepagentens):**

Storleksordning mindre än påstått. Realistiskt: några ms till ~15 ms mindre event-loop-blockering per gzippad API-GET på podd-CPU (300m), mot en /api/overview-median på 970 ms som är DB-dominerad — dvs ~1-3 % latens per request, inte "30 ms per stor JSON-respons". Kostnad: +2-8 % bytes över nätet, 0 % på CSS (identisk output-storlek vid lvl6). Det verkliga värdet är systemiskt, inte per-request: mindre synkron CPU på event-loopen i EN uvicorn-worker, dvs mindre head-of-line-blockering för samtidiga requests. Kan inte kvantifieras skarpare utan att veta de faktiska payloadstorlekarna i drift — de mäts inte idag. Rekommenderas ändå eftersom insatsen är ett radbyte och nedsidan i praktiken är noll.

**Matning som ska bekrafta vinsten:**

1) Först plan-punkt 0.1: låt tools/api_benchmark.py registrera content_length + content-encoding per sample (utan det går vinsten inte att bevisa). 2) Kör `python -m tools.api_benchmark --budget tools/latency_budgets.json` mot /api/overview?year=2026&week=27, /api/schedule?year=2026&week=27&weekday=5, /api/schedule/summary och /api/persons före/efter radbytet, i podden (300m CPU), och jämför medianer + p95 mot artifacts/api_benchmark/efter-perf-sweep.json. 3) Komplettera med en mikrobenchmark på de FAKTISKA bodies som benchmarken fångar (gzip lvl 9 vs 6, tid + storlek) — det är där effekten faktiskt syns, eftersom den totala medianen domineras av DB-tid. 4) Kontrollera i samma körning att svarens content-encoding fortfarande är gzip och att ETag-värdena är oförändrade före/efter (bevis på att inget cache-beteende ändrats).

**Forutsattningar innan bygge:**

Beteendebevarande: ja, verifierat i koden — gzip är ytterst i kedjan, så api_get_etag (main.py:278-313) hashar den okomprimerade bodyn; compresslevel kan därmed inte ändra ETags, 304-logiken eller service-worker-cachen. Klienter dekomprimerar gzip oberoende av nivå. Skyddande tester: tests/services/test_http_delivery.py (kontraktstest på att SSE/text-event-stream inte gzippas och att minimum_size=1024 gäller) samt ETag/304-testerna i samma fil. Lägg till ett kontraktstest som låser compresslevel=6 explicit (wiki/optimeringsplan.md:241 föreslår redan detta) så att nivån inte tyst driftar tillbaka till library-defaulten vid en starlette-uppgradering. Ingen golden-karakterisering behövs — payloadens innehåll är oförändrat, bara antalet bytes på tråden. OBS: gör INTE detta som ersättning för punkt 3.1 (SSE komprimeras aldrig) eller 3.3 (brotli-förkomprimering av statiska filer i Docker-bygget) — de har större transportvinst, och 3.3 gör dessutom compresslevel irrelevant för just de statiska filerna.

---

## #52 — api_benchmark mäter bara latens, aldrig payloadstorlek — leveranslagrets regressioner är osynliga för guardrailen

- **Plats:** `tools/api_benchmark.py (hela; artifacts/api_benchmark/baslinje-20260707.json)`
- **Monster:** ingen-matning
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> Baslinjefilerna innehåller `endpoint, samples_ms, best_ms, median_ms, status` — inga bytes. Grep efter `bytes|size` i tools/api_benchmark.py ger 0 träffar. Wikin (prestanda-optimeringar.md, E3) säger "Effekt ska mätas, inte gissas" och latensbudgetarna finns i tools/latency_budgets.json — men hela mönsterfamiljen D (transport) har alltså ingen mätning alls. Det är precis därför gzip-nivå 9, avsaknaden av orjson och den okomprimerade SSE-payloaden kunnat ligga obemärkta: ingen siffra i repot skulle ha visat dem.

**Foreslagen atgard:**

> Registrera `content_length` (och `content-encoding`) per sample i api_benchmark och skriv ut dem i rapport-JSON:en. Lägg en byte-budget bredvid latency_budgets.json (`tools/payload_budgets.json`) med exit 2 vid överträdelse — samma mönster som E2. Då fångas både en payload som svällt och en komprimering som slutat fungera.

**Skeptikerns granskning:**

Faktapåståendet stämmer. `measure()` (tools/api_benchmark.py:40-58) tidtar bara `session.get(...)` och returnerar endast endpoint/samples_ms/best_ms/median_ms/status — `response`-objektet slängs utan att någon storlek eller header läses. `check_budgets()` (rad 102-115) jämför enbart `median_ms` mot tools/latency_budgets.json, som bara innehåller ms-tak. tools/latency_budgets.json och tests/tools/test_gap_latency_budget.py innehåller inte ett enda byte-begrepp. Inte redan fixat: `git log --oneline -- tools/api_benchmark.py` ger bara två commits (2aa5e5b "API-benchmark-verktyg", 1793f32 "Leveransoptimering: gzip, immutable-cache..., latensbudget") — leveransoptimeringen införde gzip/ETag men lade INTE till någon payloadmätning. Wiki/prestanda-optimeringar.md E1-E3 (rad 255-263) bekräftar: frågebudget + latensbudget finns, ingen payloadbudget. MEN tre viktiga skärpningar mot svepagentens framställning: (1) Vinsten är noll runtime — detta är ett verktyg, inte en optimering; värdet realiseras bara om D-fixarna faktiskt byggs och verifieras. (2) Guardrailen blir SVAG i den föreslagna formen: api_benchmark kräver `--base-url/--username/--password` mot en körande miljö och körs inte i CI (grep i .github/, scripts/, Makefile ger 0 träffar; AGENTS.md:86 beskriver den som en manuell rutin). En payloadbudget med exit 2 fångar alltså bara det någon minns att köra — till skillnad från E1 (frågebudget) som är ett pytest-kontrakt i pre-push. (3) Förslaget fångar INTE den SSE-payload det utlovar: SSE ingår inte i DEFAULT_ENDPOINTS (rad 30-37) och strömmade svar saknar Content-Length (chunked), så `content_length` blir None just där. Rekommendation: bygg mätningen som `len(response.content)` + `content-encoding`-header i measure(), OCH lägg själva byte-taket som ett pytest-kontraktstest med TestClient mot kärnendpoints (kör i pre-push, ingen miljö behövs) — inte enbart som en manuell benchmark-flagga.

**Justerad vinst (granskarens, inte svepagentens):**

Ingen latens- eller minnesvinst alls. Guardrail-värde: gör D-familjen (transport) mätbar. Realistiskt värde begränsat till att (a) upptäcka en payload som svällt och (b) upptäcka att gzip/ETag slutat fungera — men bara om taket landar i ett pre-push-test, inte enbart i den manuellt körda benchmarken. Kan inte kvantifieras i ms.

**Matning som ska bekrafta vinsten:**

Verktyget ÄR mätningen; det som ska verifieras är att den fungerar: kör `python -m tools.api_benchmark --base-url <dev> --label payload-check` och kontrollera att varje result-post får `content_length_bytes` och `content_encoding: "gzip"` för /api/schedule, /api/overview, /api/persons. Sanity: `curl -H "Accept-Encoding: gzip" -o /dev/null -w "%{size_download}"` mot samma endpoints ska ge samma storleksordning. Byte-taket sätts från baslinjen med samma marginal-metod som latency_budgets.json (60-80 %).

**Forutsattningar innan bygge:**

Beteendebevarande på produktionskoden: ja — ändringen rör bara tools/, ingen app-kod. Rapport-JSON:ens schema utökas dock, så: (1) `print_report`/`--compare` måste tåla gamla baslinjefiler i artifacts/api_benchmark/ som saknar de nya fälten (använd .get med default None, aldrig direkt indexering). (2) tests/tools/test_gap_latency_budget.py är skyddsnätet — dess syntetiska rapporter saknar de nya fälten och MÅSTE fortsätta passera; det verifierar bakåtkompatibiliteten. (3) Om en payload_budgets.json läggs till bör motsvarande kontrakt som test_every_budget_key_is_exactly_a_default_endpoint skrivas, annars uppstår döda budgetnycklar. (4) Innan arbete: bekräfta att measure() mäter DEKOMPRIMERAD storlek via len(response.content) (requests dekomprimerar automatiskt) — vill man ha wire-bytes måste Content-Length-headern läsas separat och båda bör sparas, annars mäts fel sak.

---

# OSAKRA (17)

Mekanismen finns, men vinsten ar obevisad. **Mat innan du bygger.**

## #05 — MCP-status gör tre oberoende RPC-anrop (tools/resources/prompts) i serie

- **Plats:** `app/backend/mcp/service.py:381-386 (anropas från app/backend/routers/mcp.py:91)`
- **Monster:** NYTT:seriell-oberoende-extern-io
- **Het vag:** nej · **Insats:** S · **Risk:** medel

**Problem (svepagentens beskrivning):**

> `list_mcp_tools` gör `await session.initialize()` och därefter `list_tools_optional()`, `list_resources()`, `list_prompts()` **sekventiellt**. De tre är oberoende JSON-RPC-anrop mot samma MCP-server över samma `httpx.AsyncClient` (protocol.py:296-402). Efter `initialize()` är session-id:t satt, så de tre kan skickas parallellt. Rutten är korrekt async (ingen C1 — httpx är async hela vägen), men den betalar 3 seriella nätverks-RTT:er där 1 räcker. Samma seriella mönster upprepas i `ask_mcp` (service.py:435).

**Foreslagen atgard:**

> Efter `initialize()`: `tools, resources, prompts = await asyncio.gather(session.list_tools_optional(), session.list_resources(), session.list_prompts())`. Kontrollera först att MCP-servern tål samtidiga requests på samma Mcp-Session-Id — `_next_id` inkrementeras i `rpc()` utan lås men Python-GIL gör inkrementet i praktiken atomiskt här; sätt annars ett `asyncio.Lock` runt id-tilldelningen. Om servern inte tål det: lämna som är.

**Skeptikerns granskning:**

Premissen stämmer delvis, men vinstlogiken faller på ett faktum svepagenten missade i koden den själv säger sig ha läst.

1) SANT: service.py:382-385 gör `initialize()` → `list_tools_optional()` → `list_resources()` → `list_prompts()` sekventiellt, och de tre är oberoende (protocol.py:381-400, alla tre går via `optional_rpc`, dvs. sväljer redan McpProtocolError var för sig — det gör gather relativt riskfritt just felsemantiskt).

2) FALSKT: påståendet "samma seriella mönster upprepas i ask_mcp (service.py:435)". På service.py:434-435 finns bara ETT anrop efter initialize (`list_tools_optional`) — inget att parallellisera. Resten är en genuint sekventiell LLM-tool-loop. Halva kandidaten är hallucinerad.

3) VINSTEN ÄR SANNOLIKT NÄRA NOLL SOM FÖRESLAGET: `protocol.py:302` skapar `httpx.AsyncClient(timeout=...)` **utan `http2=True`**. Alltså HTTP/1.1 — ingen multiplexing. Tre samtidiga POST:ar kan inte dela den varma connection som `initialize()` etablerade; httpx öppnar två NYA TCP+TLS-connections. Varje ny HTTPS-connection kostar ~2 RTT (TCP + TLS1.3-handshake) innan requesten ens går ut, plus 1 RTT för själva anropet. Serial ≈ 3×RTT (requestbunden). Parallell ≈ 2×RTT handshake + 1×RTT request ≈ 3×RTT (handshakebunden). Kvarvarande vinst är i praktiken bara MCP-serverns *processeringstid* för två av anropen — inte 2 nätverks-RTT:er. Påståendet "0,4-1,0 s snabbare" är därmed obelagt och byggt på en modell som koden motsäger.

4) VÄGEN ÄR LJUM: `/api/mcp/status` hämtas en gång när MCP-vyn öppnas och vid "Uppdatera" (mcp.js:236, `cacheTtlMs: 0`). En användare, en request, trivial datamängd. Användaren väntar — men det är ingen genomströmningsväg.

5) Inte redan fixat: `git log -- app/backend/mcp/service.py protocol.py` visar bara ba7438d (paketsplit). Ingen gather någonstans i app/backend.

Om något ska göras är den RIKTIGA åtgärden en annan än den föreslagna: `initialize()` (protocol.py:360-367) kastar bort serverns `capabilities` ur svaret. Gate:a `resources/list` och `prompts/list` på att servern faktiskt annonserar `resources`/`prompts` — det TAR BORT rundresor istället för att överlappa dem, och kostar inga extra TLS-handshakes. Alternativt/dessutom `http2=True` på klienten (kräver `httpx[http2]` + att noeffect-servern talar h2), och först DÅ är asyncio.gather meningsfullt.

**Justerad vinst (granskarens, inte svepagentens):**

Som föreslagen (naken asyncio.gather på en HTTP/1.1-klient): sannolikt 0-200 ms, dvs. i praktiken ingen mätbar vinst — de två sparade request-RTT:erna byts mot två TLS-handshakes. Med capability-gating från initialize-svaret: 2 borttagna RPC-rundresor mot MCP-servern, men bara på servrar som inte annonserar resources/prompts — okänt om noeffect gör det. Jag kan inte kvantifiera utan att mäta mot en riktig noeffect-endpoint. Kandidatens "0,4-1,0 s" avvisar jag som obelagd.

**Matning som ska bekrafta vinsten:**

Ingen api_benchmark-endpoint täcker detta (kostnaden är extern nätverks-I/O). Mät istället via befintlig OTel-instrumentering: spanen `mcp.http` (protocol.py:316, har redan attributet `mcp.method`) och föräldraspanet `mcp.status` (routers/mcp.py:96). Kör `GET /api/mcp/status` mot en riktig tenant (frey) 10 ggr, ta median per `mcp.method` (initialize, tools/list, resources/list, prompts/list) och total `mcp.status`-duration, före/efter. Kör DESSUTOM först en förmätning som avgör om vinsten alls kan existera: (a) tala om ifall noeffect-MCP svarar med ALPN h2 (`curl -sI --http2 <MCP_URL>` / `openssl s_client -alpn h2`), (b) mät TLS-handshake-kostnaden mot MCP-värden (`curl -w "%{time_connect} %{time_appconnect} %{time_starttransfer}"`). Om handshake ~= request-RTT och servern inte talar h2 → bygg inte fixen.

**Forutsattningar innan bygge:**

1. Verifiera att MCP-servern (noeffect) tål samtidiga POST:ar på samma `Mcp-Session-Id` — annars faller hela idén. Streamable-HTTP-servrar varierar här.
2. Verifiera h2-stöd (se mätning). Utan h2 måste `http2=True` läggas till på protocol.py:302 för att gather ska ge något — det ändrar transporten och kräver `httpx[http2]`/h2-beroende i requirements: inte en S-ändring längre.
3. Racekontroll: `_post` skriver `self.session_id` och `self.protocol_version` från svaren (protocol.py:328-330). Vid gather skriver tre coroutines samma fält — benignt (samma värde) men måste konstateras, inte antas. `_next_id`-inkrementet (protocol.py:337-338) är faktiskt atomiskt i asyncio (ingen await mellan läs och skriv) — kandidatens GIL-resonemang är fel argument men rätt slutsats.
4. Beteendebevarande: JA på felsidan, eftersom alla tre redan går via `optional_rpc` som sväljer fel. MEN: idag stoppar ett hårt fel i tools/list inte de efterföljande anropen heller, så ingen semantikändring där.
5. Skyddande tester: bara `tests/services/test_mcp_service.py:364` (`test_mcp_status_is_ready_with_gemini_even_without_tools`) — den mockar hela `McpHttpSession` med en FakeSession och skulle passera oförändrad även om gather-fixen vore trasig på nätverksnivå. Den skyddar alltså INGENTING här. Ett nytt test som mockar `httpx` på transportnivå (t.ex. `httpx.MockTransport`) och verifierar antal öppnade connections/anropsordning krävs innan man tror på en grön svit.

---

## #08 — DuckDB öppnas med värdens defaults (threads = alla kärnor, memory_limit = 80 % av värdens RAM) i en 300m/1Gi-podd

- **Plats:** `app/backend/local_archive_store.py:187-194`
- **Monster:** konfig-antagande
- **Het vag:** ja · **Insats:** S · **Risk:** medel

**Problem (svepagentens beskrivning):**

> _connect() gör `duckdb.connect(str(path), read_only=read_only)` utan en enda SET. DuckDB härleder då sina defaults från VÄRDEN, inte från cgroupen: threads = antal kärnor på noden och memory_limit ≈ 80 % av nodens RAM. Podden har CPU-limit 300m och memory-limit #{JOB_MEMORY_MAX} (~1 Gi). Detta är exakt samma feltyp som ffmpeg-incidenten 2026-07-09 (ffmpeg default = alla kärnor -> grupp-OOM dödade podden), men DuckDB fick aldrig motsvarande behandling — det finns inget `-threads`-motsvarande kontraktstest och ingen SET någonstans i repot. Anslutningen öppnas dessutom på nytt vid VARJE fråga (via `_connection`-context managern), så defaults gäller varje gång.

**Foreslagen atgard:**

> Direkt efter connect: `con.execute("SET threads=1")`, `con.execute("SET memory_limit='256MB'")` och `SET temp_directory='<ARCHIVE_CACHE_DIR>/tmp'` (så spill går till PVC:n, inte till RAM/rootfs). Gör värdena till settings (ARCHIVE_CACHE_DUCKDB_THREADS / _MEMORY_LIMIT). Lägg ett kontraktstest som läser SET-anropen, i samma anda som ffmpeg -threads-testet, så fixen inte kan reverteras av misstag.

**Skeptikerns granskning:**

KODPÅSTÅENDET STÄMMER. local_archive_store.py:187-194 `_connect()` gör exakt `duckdb.connect(str(path), read_only=read_only)` utan en enda SET/PRAGMA. `grep "memory_limit|SET threads|PRAGMA|duckdb.connect" app tools tests` ger EN träff: raden 194. `_connection` (rad 67-79) öppnar och stänger anslutningen per fråga, så defaults sätts om varje gång. Vägen är HET i prod: k8s/flow.yml:152-153 sätter ARCHIVE_CACHE_ENABLED=1, limits cpu 300m / memory #{JOB_MEMORY_MAX}Mi, och `query_rows` anropas per användarrequest från data_fetch.py:346 (_fetch_rows), sankey_inbound/fetch.py:183/208/385 och workflow_data.py:412. Inte fixat: git log för filen visar en enda commit (9d71d6f), inget SET har någonsin funnits. Det är dessutom redan känt — det ÄR punkt 1.1 i wiki/optimeringsplan.md:54, ordagrant. Svepagentens "evidens" är alltså delvis cirkulär (den har troligen läst planen), men koden bekräftar den oberoende.

MEN JAG KAN INTE BEKRÄFTA VINSTEN, och tre delar av påståendet håller inte:

1) Den bärande premissen är overifierad. "DuckDB härleder defaults från VÄRDEN, inte cgroupen" är sannolikt sant (DuckDB använder hardware_concurrency() och sysconf-fysminne, inte cgroup-limits — jag känner inte till någon cgroup-medvetenhet ens i 1.x; app/requirements.txt:27 låser duckdb>=1.5.4,<2). Men jag kan INTE verifiera det från repot. Hela kandidatens allvarlighetsgrad hänger på nodens faktiska kärnantal och RAM, som inte finns i repot.

2) "En stor arkivfråga kan idag be om flera GB" är fel resonemang. memory_limit är ett TAK, inte en reservation — DuckDB allokerar inte 80 % av nodens RAM, det tillåter det bara. Frågan i query_rows (rad 613-621) är en ren streaming-scan (`SELECT * ... WHERE _row_date BETWEEN ? AND ?`), utan join/sort/aggregering — inga blockerande operatorer som växer mot taket. Det som faktiskt spränger 1 Gi är Python-sidan direkt efter: rad 622-628 materialiserar HELA resultatet som en list-of-dicts, och `apply_local_filters` kopierar det igen. Den delen skyddas inte av memory_limit alls. Detta är i själva verket optimeringsplanens punkt 1.2 (obundet `SELECT *` utan LIMIT) — det är DEN som är den verkliga OOM-boven, och k08 riskerar att maskera den snarare än fixa den.

3) `SET temp_directory=<PVC>` är sannolikt en NO-OP. För en fil-backad DuckDB-databas är default-temp_directory `<dbfil>.tmp/` bredvid databasfilen — dvs. redan /var/flow-media/archive_cache på PVC:n. Påståendet "spill går till RAM/rootfs" gäller in-memory-databaser, inte den här.

4) Risken är felklassad. `SET memory_limit='256MB'` är INTE beteendebevarande: en fråga eller en seed-insert (_bulk_insert registrerar en pandas-DataFrame, ARCHIVE_CACHE_CHUNK_DAYS=15 i prod) som idag lyckas kan efter fixen kasta "Out of Memory Error". Svepagentens "Risk: låg" håller inte för den delen. `SET threads=N` är däremot beteendebevarande.

Det som ÅTERSTÅR som en trolig, försvarbar vinst är trådtaket: DuckDB skapar en task-scheduler-trådpool per databasinstans, och eftersom anslutningen öppnas/stängs per fråga betalas trådskapandet varje gång. Med CPU-limit 300m bränner N parallella trådar CFS-kvoten på bråkdelen av en 100 ms-period och stryper HELA cgroupen — inklusive den enda uvicorn-workern, dvs. alla andra requests. Det är samma systemeffekt som mönster C1 i wiki/prestanda-optimeringar.md. Men storleken är okänd utan mätning.

**Justerad vinst (granskarens, inte svepagentens):**

Ingen mätbar latensvinst är visad — svepagentens egen "Okänd i ms" är ärlig och jag skärper den nedåt. Det som återstår, uppdelat: (a) `SET threads` = trolig men okvantifierad vinst i p95 för Sankey/Hämta data via mindre trådskapande per fråga och mindre CFS-strypning av den enda uvicorn-workern; jag gissar storleksordningen tiotals ms per fråga plus minskad korsstörning på samtidiga requests, men det är en gissning tills det mätts. (b) `SET memory_limit` = ingen prestandavinst alls, bara ett skyddsräcke — och ett halvt sådant, eftersom Python-materialiseringen i query_rows:622-628 är den dominerande minnestermen och inte skyddas. (c) `SET temp_directory` = sannolikt noll (redan default till PVC:n för en fil-backad DB). Rekommendation: bygg (a) fristående, och lyft (b) till optimeringsplanens punkt 1.2 (radtak/LIMIT på den obundna läsvägen) i stället — det är där den verkliga OOM-vinsten finns.

**Matning som ska bekrafta vinsten:**

FÖRE ALLT ANNAT (detta avgör om kandidaten över huvud taget är verklig): kör i den körande podden `SELECT current_setting('memory_limit'), current_setting('threads'), current_setting('temp_directory')` mot en av tenant-DuckDB-filerna, plus `nproc` och nodens totala RAM. Om threads redan är litet och memory_limit redan är cgroup-anpassat faller kandidaten helt. FÖR VINSTEN: (1) `python -m tools.api_benchmark --base-url <miljö> --label fore-duckdb-threads` och `--compare` efter, med fokus på Sankey-endpointen och `POST /api/data-fetch/run` för en dblog-vy med Between-fönster (de vägar som går genom data_fetch.py:346 / sankey_inbound/fetch.py:183). (2) Mät samma sak med hög samtidighet — hela poängen med trådtaket är att en DuckDB-fråga inte ska strypa cgroupen för ÖVRIGA requests; en enkelbenchmark kommer visa nära noll. (3) Kolla CFS-throttling före/efter: container_cpu_cfs_throttled_seconds_total för podden. (4) Minnestoppen mäts med `kubectl top pod` / lastState=OOMKilled, inte med api_benchmark.

**Forutsattningar innan bygge:**

1. VERIFIERA PREMISSEN FÖRST i podden (se mätning) — utan nodens kärnantal/RAM och DuckDB:s faktiska current_setting är hela kandidaten spekulation. 2. Dela upp fixen: `SET threads` är beteendebevarande och kan byggas direkt; `SET memory_limit` är det INTE (kan förvandla en lyckad stor fråga eller seed-insert till ett OOM-fel) och kräver att man först vet hur stora de faktiska resultatmängderna och seed-chunkarna (CHUNK_DAYS=15) är i prod — annars sätter man ett tak som fäller legitima frågor. Bygg inte memory_limit förrän optimeringsplanens 1.2 (radtak på den obundna läsvägen) är löst; annars maskerar taket symptomet på fel ställe. 3. Släpp `SET temp_directory` tills det bevisats att default INTE redan pekar på PVC:n. 4. Skyddande tester som finns: tests/services/test_local_archive_store.py och tests/services/test_archive_cache_sync.py — kör båda; de täcker läs-/seed-semantiken men INTE konfigen, så ett nytt kontraktstest behövs som läser SET-anropen (samma anda som ffmpeg `-threads 1`-testet i tests/services/test_meta_uploads.py, jfr meta_analysis_service.py:106). 5. Ingen golden-karakterisering behövs för threads (beteendebevarande); för memory_limit krävs en explicit redovisning av att felbeteendet ändras.

---

## #12 — Import-endpoints läser hela request-bodyn i RAM INNAN storlekskontrollen (nginx tillåter 256 MB)

- **Plats:** `app/backend/routers/persons.py:598-600`
- **Monster:** inget-tak
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> Tre importvägar gör `content = await file.read()` och kontrollerar `len(content) > MAX_IMPORT_BYTES` (5 MB) FÖRST DÄREFTER. Kontrollen kommer alltså efter att hela filen redan ligger som ett bytes-objekt i processminnet. Ingressen tillåter proxy-body-size: 256m (k8s/flow.yml:317), så en 256 MB-body allokeras i sin helhet i en 1 Gi-podd innan 413:an returneras. Samma mönster i users.py:456-458 och activities.py:691-693. Jämför med meta-uppladdningen som gör rätt (strömmar chunkat till media store med batch-tak) — importvägarna fick aldrig samma behandling.

**Foreslagen atgard:**

> Kontrollera `file.size` (Starlette sätter den från Content-Length) före read och avvisa 413 direkt; alternativt läs chunkat (`await file.read(64*1024)` i loop) och avbryt så fort MAX_IMPORT_BYTES + 1 byte passerats. Lägg ett test som postar en för stor fil och verifierar att den aldrig materialiseras.

**Skeptikerns granskning:**

Koden finns och ser ut som påstått. persons.py:598-600, users.py:456-457 och activities.py:691-692 gör alla `content = await file.read()` följt av `if len(content) > MAX_IMPORT_BYTES` (5 MB, definierat på persons.py:39, users.py:35, activities.py:50). k8s/flow.yml:317 sätter proxy-body-size: "256m". `git log -S "MAX_IMPORT_BYTES"` visar bara 63b6f60/fa225a7 (införandet) — inte fixat. Inget test i tests/ träffar 413-vägen.

MEN kandidatens vinstbild och mönsterklassning håller inte:

1) "Mönstret inget-tak" existerar inte i wiki/prestanda-optimeringar.md. Katalogen är A1–A5, B1–B4, C1, D1–D3, E1–E3. Svepagenten har uppfunnit mönsternamnet. Detta är en robusthets-/minnessäkerhetsfråga, inte en prestandaoptimering i katalogens mening.

2) "256 MB allokeras i RAM" är fel i mekanismen. Starlette (installerad version 1.3.1) parsar multipart till en SpooledTemporaryFile med spool_max_size ~1 MB — allt över det spoolas redan till en temp-fil på disk. Bodyn buffras alltså INTE i RAM under mottagningen. Det som faktiskt allokerar är `await file.read()` utan argument, som drar in hela temp-filen som ett bytes-objekt. RAM-peaken finns alltså, men den uppstår i routen, inte i ingressen/parsern som kandidaten beskriver.

3) "Peak-minne per import går från 256 MB till 5 MB" är inte sant ens efter fix. parse_person_import_excel (persons.py:326) gör `load_workbook(io.BytesIO(content), ...)` — en 5 MB xlsx är en zip och expanderar till betydligt mer i RAM under openpyxl-parsningen. 5 MB-taket är ett tak på *bytes-objektet*, inte på minnespeaken. Peaken domineras av parsningen, inte av content.

4) Vägen är kall och autentiserad. Import kräver require_view_access("personImport"/"userImport"/"activityImport", "edit") — intern admin, manuell körning, sällan. Ingen throughput- eller latensvinst för någon användare i normal drift. Kandidaten medger själv att det är en footgun, inte publik DoS.

Varför jag ändå inte avfärdar helt: appen kör EN uvicorn-worker i en 1 Gi-podd. En OOM dödar podden för alla samtidiga användare, inte bara den som postade filen. En admin som råkar dra in en 200 MB-fil är ett realistiskt olycksfall. Fixen (kolla `file.size` före read, fallback till chunkad läsning om size är None) är S/låg risk och beteendebevarande för allt < 5 MB.

Sidoobservation som är MER intressant än kandidaten: alla tre importvägarna är `async def` och kör openpyxl-parsning + hela import-transaktionen synkront på event-loopen utan run_in_threadpool. Det är C1 (blocking-in-async) i katalogen och fryser samtliga requests under importen. Om någon rör dessa endpoints bör det åtgärdas i samma svep.

**Justerad vinst (granskarens, inte svepagentens):**

Ingen mätbar prestandavinst i normal drift. Vinsten är robusthet: eliminerar ett bytes-objekt på upp till ~256 MB i en 1 Gi-podd med en worker, dvs stänger en OOM-väg som skulle ta ned podden för alla. Kandidatens "256 MB → 5 MB peak" är felaktig — peaken efter fix bestäms av openpyxl-expansionen av xlsx:en, inte av 5 MB-taket. Kan inte kvantifieras i ms eller RPS; det är riskreduktion, inte hastighet.

**Matning som ska bekrafta vinsten:**

Ingen api_benchmark-endpoint är relevant (kall väg). Rätt mätning är RSS-peak, inte latens: kör importvägen mot en lokal uvicorn och mät process-RSS med tracemalloc/resource under (a) POST av en ~200 MB dummyfil och (b) en normal 200 kB xlsx, före och efter fixen. Före ska (a) visa en RSS-spik i storleksordningen filens storlek; efter ska den vara platt och svaret 413. Fall (b) ska vara oförändrat i både RSS och svarskropp.

**Forutsattningar innan bygge:**

1) Verifiera att `UploadFile.size` faktiskt är satt i den installerade Starlette-versionen (1.3.1) för multipart-filer — den räknas upp per chunk i parsern, inte tas från Content-Length som kandidaten skriver. Om size kan vara None måste en chunkad fallback (`await file.read(64*1024)` i loop med early abort) finnas, annars smiter stora filer förbi taket. 2) Beteendebevarande: filer < 5 MB måste ge bit-identiskt svar; filer > 5 MB måste fortfarande ge 413 med exakt samma detail ("Excel-filen är för stor"). 3) Skyddande tester: det finns INGA idag för 413-vägen — tests/ har inga träffar på MAX_IMPORT_BYTES eller 413 på import. Ett nytt test per endpoint (persons, users, activities) som postar en för stor fil och verifierar 413 måste skrivas som del av fixen, plus ett som verifierar att en normal fil fortfarande importeras. 4) Alla tre ställena måste ändras samtidigt, annars uppstår divergerande beteende mellan importvägarna.

---

## #16 — Produktivitet-översikt: rapportcachen är en modul-Map som töms vid varje sidladdning -> SSE-bygget körs om vid varje besök

- **Plats:** `app/frontend/js/productivity_overview_core.js:24`
- **Monster:** D
- **Het vag:** ja · **Insats:** M · **Risk:** medel

**Problem (svepagentens beskrivning):**

> productivityOverviewReportCache = new Map() med 2 min TTL. Stream-vägen (productivity_overview.js:490-499) läser/skriver ENBART den Map:en — till skillnad från fetch-fallbacken går den aldrig via api.get, så inget hamnar i sessionStorage. Eftersom varje vybyte är en riktig sidladdning betyder det att cachen alltid är kall när användaren kommer in i vyn: en ny EventSource startas och hela rapporten byggs om (progressloggen visar 30+ steg för månad). Att gå till Bemanning och tillbaka = nytt fullt bygge, även 5 sekunder senare.

**Foreslagen atgard:**

> Skriv done-payloaden till en SWR-snapshot (sessionStorage, samma nyckel som cacheUrl, scope-suffix som api_swr.js) och måla den direkt vid sidöppning innan strömmen startas; låt strömmen/revalideringen ersätta vyn först när payloaden faktiskt skiljer sig (getSwr gör redan den jämförelsen).

**Skeptikerns granskning:**

Faktapåståendena stämmer, men vinsten är obevisad och två motverkande omständigheter gör den möjligen liten just där den behövs.

VAD SOM STÄMMER (läst kod):
- productivity_overview_core.js:24 `const productivityOverviewReportCache = new Map()` — ren modul-Map, TTL 2 min (core.js:14). Nollställs vid varje sidladdning.
- Flow är en MPA (app/frontend/*.html, en fil per vy) → vybyte = riktig sidladdning → Map:en är alltid kall vid inträde. Korrekt.
- Ström-vägen är default: loadProductivityOverview() (productivity_overview.js:553-564) går alltid via loadProductivityOverviewViaStream() när EventSource finns (alltid i Chrome/Edge/QtWebEngine). Den läser/skriver ENBART Map:en (rad 493-499 + 533 -> applyProductivityOverviewReport(..., {cacheUrl}) -> rad 444-449). Ingen sessionStorage.
- Fetch-fallbacken (rad 385) anropar api.get(url, {cacheTtlMs}) och api.js:196-209 writeApiGetCache skriver till sessionStorage med TTL, dvs. den vägen ÖVERLEVER sidladdning. Ström-vägen gör alltså inte det. Asymmetrin är verklig. (Not: fetch-vägen skickar inte swrSnapshot:true, så det är GET-cachen med TTL, inte SWR-snapshot — svepagentens formulering är lite slarvig men slutsatsen densamma.)
- Inte redan fixat: `git log` på productivity_overview*.js visar bara arkitektursplit/@ts-check sedan SSE-införandet. SWR-pilot är enligt wiki/prestanda-optimeringar.md:245-247 begränsad till Personer + Översikt, och produktivitet.html (rad 65-85) laddar inte ens js/common/api_swr.js — getSwr/writeSwrSnapshot finns inte på sidan idag.

VARFÖR JAG INTE BEKRÄFTAR:
1. Serversidan är sannolikt redan varm i standardfallet. Default är period=day, och enligt wiki/prestanda-optimeringar.md:308-314 + wiki/productivity.md:163-174 förbygger 30-min-schemaläggaren *dagens* dag för alla aktiva bolag, och wiki/productivity.md:229-230 säger att redan byggda dagar "laddas i princip momentant". "30+ steg" gäller månad/år — inte den dagliga öppningen. Den påstådda flersekunders-väntan är alltså inte belagd för den heta vägen.
2. Snapshot-vägen kan slå i sessionStorage-kvoten exakt i det långsamma fallet. Payloaden innehåller `"reports": reports` — hela per-dags-rapporterna (person/aktivitet/timme/process) för hela perioden (productivity_helpers.py:686-705). För månad/år blir JSON:en sannolikt flera MB; writeSwrSnapshot sväljer kvotfel tyst (api_swr.js:46). Alltså: den period där bygget är dyrt är också den period där snapshoten troligen inte får plats. Ingen mätning av payloadstorleken finns.
3. Vinsten är inte "omedelbar rendering". Snapshoten sparar server + nätverk, men buildProductivityOverviewTree/indexProductivityOverviewTree/renderProductivityOverviewTree (productivity_overview.js:357-361) körs ändå. Hur mycket av väntan som är klientens trädbygge är okänt.

Det finns inget mätvärde att luta sig mot: tools/latency_budgets.json har ingen /api/productivity/*-endpoint alls.

**Justerad vinst (granskarens, inte svepagentens):**

Kan inte kvantifieras utan mätning. Övre gräns = serversvarstiden för /api/productivity/overview (dag: sannolikt låg, förvärmd av 30-min-schemaläggaren; månad/år: potentiellt flera sekunder — men där riskerar snapshoten kvotfel). Klientens trädbygge + render sparas inte. Realistiskt: märkbar vinst främst för dag/vecka vid snabba fram-och-tillbaka-byten, i storleksordningen en serverrundresa (~0,3-1,5 s), inte "flersekunders progress-bar borta".

**Matning som ska bekrafta vinsten:**

FÖRE fixen (avgör om den ska byggas alls):
1. Lägg till /api/productivity/overview?period=day&date=<idag> och ?period=month i tools/latency_budgets.json och kör `python -m tools.api_benchmark` mot prod-lik miljö med förvärmd cache. Om dag-medianen är låg (<400 ms) faller den heta vägen.
2. Mät payloadstorlek (Content-Length) för period=day/week/month/year för ett riktigt bolag. >~2 MB ⇒ sessionStorage-kvoten spricker och fixen ger noll för den perioden.
3. Klientprofilering i DevTools: dela upp tiden från navigation till färdig träd-render i (a) SSE/server, (b) JSON-parse, (c) buildProductivityOverviewTree+render. Bara (a)+(b) kan snapshoten ta bort.

EFTER fixen: samma DevTools-mätning (tid till första målade träd) på en varm sessionStorage, vy Bemanning -> Produktivitet, samt kontroll i loggen att `productivity_overview_ondemand_build` inte ökar.

**Forutsattningar innan bygge:**

- Beteendebevarande kräver: (a) snapshot-nyckeln måste innehålla både date OCH period (cacheUrl gör det, productivity_overview.js:492) plus scope-suffix för verksamhets-/områdesfokus som api_swr.js:14-26 redan gör, annars kan fel bolags data målas; (b) strömmen måste ALLTID köras efter snapshot-målningen (revalidering), annars visas gammal data utan uppdatering; (c) setProductivityOverviewLoading/progressloggen får inte blanka den redan målade vyn — dagens ström-väg sätter loading-overlay direkt, det måste ändras till en diskret "Uppdaterar…"-pill (api_swr.js:62-76).
- produktivitet.html måste börja ladda js/common/api_swr.js (finns inte där idag).
- Utloggning: api.post -> clearApiGetCache() rensar även SWR-snapshots (api.js:224-232, 975) — läckagerisken är samma som för befintlig pilot, men verifiera att logout verkligen går via api.post.
- Skyddande tester idag: tests/services/test_productivity_router.py och test_productivity_v2.py (backend, berörs inte). Frontend-kontrakten i tests/tools/ (t.ex. test_persons_view.py, test_sankey_frontend_contracts.py) skyddar INTE produktivitetsvyn — ett nytt kontraktstest för snapshot-nyckeln (period+date+scope) bör skrivas innan fixen.

---

## #18 — Översikt: namnfiltret bygger om hela månadsrutnätet (personer × 31 celler) per tangenttryck

- **Plats:** `app/frontend/js/overview.js:744-750`
- **Monster:** NYTT:saknad-debounce
- **Het vag:** okänt · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> input-lyssnaren kör refreshPersons() (filtrerar + sorterar hela personlistan med comparePersonsForAreaFocus, overview_dates_cells.js:172-192) och därefter buildMonthBody()/buildWeekBody() som replaceChildren:ar hela tbody: en <tr> + en <td> per person och dag, med setupPersonOrderNameCell() (drag/contextmenu-lyssnare) per rad och renderDayCell()/styleCell() per cell. I månadsvyn är det persons × ~31 celler — vid 150 personer ~4 700 element som skapas om vid VARJE tecken i filtret. Filtret påverkar bara vilka RADER som syns; hela rutnätet behöver aldrig byggas om.

**Foreslagen atgard:**

> Antingen debounce ~120 ms på input, eller (bättre) håll rutnätet byggt och toggla radernas display via en CSS-klass utifrån namnmatchning — då blir filtrering O(antal rader) klasstoggling i stället för O(rader × dagar) DOM-skapande.

**Skeptikerns granskning:**

Mekanismen finns och är inte hallucinerad. overview.js:744-750 kör refreshPersons() + buildMonthBody()/buildWeekBody() direkt på varje 'input'-event, utan debounce, och buildMonthBody (overview_grid.js:111-146) replaceChildren:ar hela tbody. Ingen debounce finns i overview*.js. git log -S "nameFilter" visar att beteendet är oförändrat sedan fcde102 (senare bara filsplitten 19012b0) — alltså INTE redan fixat. Mönsterkatalogen (wiki/prestanda-optimeringar.md) saknar debounce-post; sektion D täcker bara transport/SWR. "NYTT" stämmer.

MEN svepagenten har tre fel, varav ett allvarligt:

(1) Kostnaden är UNDERSKATTAD, inte överskattad. styleCell (overview_dates_cells.js:472-520) bygger ett <select> per cell via buildActivitySelect (overview_dates_cells.js:133-163), som kopierar+sorterar overviewState.activitiesActive och skapar ett <option> per aktivitet, plus fyra event-lyssnare per cell. Full månadsgrid = personer × 31 × (2 + antal aktiviteter) element, inte × 1. Med 20 aktiviteter är det ~20x mer arbete per cell än svepagenten räknade.

(2) "persons × 31 vid VARJE tecken" är FEL. buildMonthBody itererar overviewState.persons (overview_grid.js:117) — den REDAN FILTRERADE listan som refreshPersons just satte (overview_dates_cells.js:175,187). Arbetet krymper alltså snabbt för varje tecken; bara första 1-2 tecknen är nära fullstorlek. "5-8 fulla rebuilds" är i praktiken ~1-2 fullgridsekvivalenter totalt.

(3) DEN REKOMMENDERADE ÅTGÄRDEN ÄR INTE BETEENDEBEVARANDE. Drag-fyll-markeringen (overview.js:219-223) itererar alla "#overviewBody td.day" och använder td.parentElement.rowIndex — fysiskt DOM-radindex. Om filtrerade rader ligger kvar i DOM:en med display:none räknas de ändå av rowIndex, så en drag-fyll mellan två SYNLIGA rader skulle tyst skriva aktiviteter även på DOLDA personers celler. Drag-fyll persisteras via /api/overview/days/bulk (overview.js:12) — det är datakorruption, inte "Risk: låg". Svepagenten missade detta helt.

Varför "osaker" och inte "bekraftad": jag kan inte kvantifiera vinsten utan profilering med produktionslika datamängder. Antal personer per område är okänt från repot; _visible_overview_persons (app/backend/routers/overview.py:75-88) har area_id som valfri — area_id=None ger ALLA aktiva personer i business (Översiktens "Alla"-läge för super/demo-användare), vilket är det enda klart stora fallet. Vid ett normalt område på 20-40 personer är en rebuild sannolikt några ms och hela kandidaten är kall.

**Justerad vinst (granskarens, inte svepagentens):**

Kan inte kvantifieras utan profilering — säger det rakt ut. Riktningen: en debounce sparar de mellanliggande rebuildsen i en snabb tangentburst. Eftersom rutnätet byggs över den REDAN FILTRERADE listan krymper arbetet per tecken, så realistisk besparing är ~1-2 fullgridsekvivalenter per sökning, inte 5-8. Å andra sidan är varje fullgrid dyrare än påstått (ett <select> med ett <option> per aktivitet + 4 lyssnare PER CELL), så en fullgrid vid stora personantal kan mycket väl vara 100-300 ms snarare än "tiotals ms". Nettot: sannolikt en märkbar input-lagg-reduktion vid de första 1-2 tecknen i "Alla"-vyn (area_id=None), och troligen försumbar i ett normalstort område. Jag vägrar sätta en siffra utan mätning.

**Matning som ska bekrafta vinsten:**

api_benchmark är INTE användbart här — det mäter serversidan och detta är ren klient-rendering (inga nätverksanrop i input-handlern). Mätningen måste göras i webbläsaren:
1. Chrome DevTools Performance-profil av Översikt i månadsvy, area = "Alla" (area_id=None → största personantalet), med produktionslik data. Spela in medan man skriver ett 8-teckens namn i #nameFilter.
2. Läs av: total scripting-tid samt längsta long task per keystroke. Före/efter debounce.
3. Alternativt en billig in-page-mätning: `performance.mark`/`measure` runt refreshPersons()+buildMonthBody() i input-handlern, logga varaktighet per tecken. Om en enskild rebuild är <16 ms vid verkligt personantal → avfärda kandidaten, då finns ingen upplevd lagg att vinna.
4. Räkna även faktiskt personantal (overviewState.allPersons.length) och overviewState.activitiesActive.length i prod — de två talen avgör hela kalkylen och är okända idag.
Tröskel för att gå vidare: en rebuild måste kosta >50 ms vid realistiskt personantal, annars är vägen kall.

**Forutsattningar innan bygge:**

1. MÄT FÖRST (se ovan). Antal personer per område och antal aktiva aktiviteter är okända — utan dem går vinsten inte att bedöma. Är en rebuild <16 ms ska kandidaten avfärdas.

2. VÄLJ RÄTT VARIANT. Endast debounce-varianten (~120 ms på input) är rimligt beteendebevarande, och även den ändrar timing: filtret uppdateras inte längre synkront efter keystroke. Den föreslagna "bättre" varianten — behåll rutnätet och toggla display via CSS-klass — är INTE beteendebevarande och ska avvisas som den är beskriven: overview.js:219-223 använder td.parentElement.rowIndex för drag-fyll-markeringen, och dolda (display:none) rader räknas fortfarande in i rowIndex. En drag-fyll över två synliga rader skulle då skriva till dolda personers celler och persistera via /api/overview/days/bulk. Ska den vägen ändå väljas måste drag-fyll först skrivas om att arbeta mot en logisk radlista i stället för rowIndex — det gör insatsen M/L och risken hög, inte S/låg.

3. TESTSKYDD SAKNAS HELT. grep över tests/ ger noll träffar på "nameFilter" — ingen befintlig test skyddar filtrets beteende. Innan någon ändring krävs golden-karakterisering av: (a) att filtret matchar case-insensitivt på substring (overview_dates_cells.js:173-175), (b) att sortering + områdesprioritering via comparePersonsForAreaFocus bevaras, (c) att applySelectedPersonRow och drag-fyll fortsätter fungera efter filtrering, (d) att pending-save-celler (overview_state.js:207) inte tappas av en rebuild mitt i en debounce-fönster.

4. RACE MED PENDING SAVES. Med debounce hinner en användare skriva medan en cell har pending-save; kontrollera att den fördröjda rebuilden inte river en cell vars sparning är i flykt (overview_state.js:207 och renderDayCell:442 rör pending-save).

---

## #27 — Arkiv-cachens läsväg är helt obunden: SELECT * + fetchall utan datumfönster (bypassar 50k-taket)

- **Plats:** `app/backend/local_archive_store.py:587-651 (grenen på 620-626 + query_snapshot_rows 645-650); anropas från app/backend/routers/data_fetch.py:346, app/backend/sankey_inbound/fetch.py:183/208/385, app/backend/workflow_data…`
- **Monster:** B2
- **Het vag:** okänt · **Insats:** S · **Risk:** medel

**Problem (svepagentens beskrivning):**

> query_rows härleder ett datumfönster ur filtren via _window_from_filters, som BARA tittar efter ett Between-filter. Saknas Between (window=None) faller den till `cursor = con.execute(f"SELECT * FROM {view}")` + `.fetchall()` → hela arkivtabellen materialiseras som en list[dict] i Python, och filtreringen görs DÄREFTER i Python med apply_local_filters (även A1: ladda-hela-tabellen-och-reducera). query_snapshot_rows är värre: den gör ALLTID `SELECT *` utan något fönster alls.
> 
> Det kritiska: 50k-taket (DATA_SOURCE_RESPONSE_ROW_CAP) appliceras bara på API-vägen, via fetch_all_rows(..., response_row_cap=_response_row_cap()) i _fetch_external_rows. Arkivgrenen i _fetch_rows returnerar `cached` RAKT AV, utan cap. Arkivvägen är alltså den enda oskyddade av de två — och den är den som prioriteras (cachen frågas först).
> 
> Detta är samma mönster som en gång OOM-dödade podden (Sankeys månad/år-vyer, …

**Foreslagen atgard:**

> Två steg. (1) Hårt tak: lägg `LIMIT {_response_row_cap()+1}` på båda SELECT-satserna så arkivvägen får samma cap-semantik som API-vägen (+1 för att kunna upptäcka trunkering och flagga den, precis som fetch_all_rows gör). (2) Push-down: flytta apply_local_filters bort från Python till en WHERE-klausul i DuckDB, så bara de rader som faktiskt behövs korsar processgränsen. Om (2) bedöms för riskabel semantiskt (NaN/tomsträng/textoperatorer måste matcha bit-identiskt — exakt fällan wikin varnar för), gör åtminstone (1) plus: returnera None (→ fallback till API, som ÄR capad) när inget datumfönster…

**Skeptikerns granskning:**

Koden finns som beskriven (local_archive_store.py:621 `SELECT * FROM {view}` utan LIMIT i else-grenen; :645 samma ovillkorligt), MEN kandidatens bärande evidens är felaktig och halva förslaget är direkt skadligt.

1) FALSKT: "50k-taket (DATA_SOURCE_RESPONSE_ROW_CAP) skyddar API-vägen; arkivvägen är den enda oskyddade". Läs external_data_client.py:343-378: `fetch_all_rows` använder cap:en som *avtrunkeringströskel*, inte som minnestak. Om `len(rows) >= cap` DELAS hämtningen i datumfönster och `left + right` slås ihop (:338-340) — API-vägen hämtar alltså medvetet MER än 50k. Cap:en är datakällans egen svarsgräns, inte vårt skydd. API-vägen är därmed också obunden i minne; det är precis den vägen som OOM-dödade podden, och arkivcachen infördes som *mitigering* av den (wiki B2). Asymmetrin finns bara i specialfallet "inget Between-filter": då kapar källan tyst vid 50k (:365-370, med varning), medan arkivet returnerar allt — dvs. arkivvägen är mer minneshungrig men MER korrekt.

2) AVFÄRDAT för query_snapshot_rows: enda snapshot-vyn är item_alias, och sankey_inbound/fetch.py:375-380 dokumenterar uttryckligen att hela tabellen KRÄVS: "annars kapas svaret vid ~50k/bolag och faktorer tappas, vilket ger fel förpacknings-ladders". API-vägen lägger på ett brett timestamp-Between (:398) enbart för att kringgå cap:en. Att lägga `LIMIT cap` här skulle återinföra exakt den bugg API-vägen går ur vägen för. "INTE mönstret om: raderna behövs faktiskt" slår till fullt ut. Kandidatens påstående att snapshot-vägen är "värre" är bakvänt.

3) Föreslagen åtgärd (1) `LIMIT cap+1` är INTE beteendebevarande: den byter komplett data mot tyst trunkering, och `query_rows` har ingen kanal att flagga trunkering (returnerar `list[dict]`; varken data_fetch._fetch_rows eller sankey kan ta emot en varning). Det redovisas inte i kandidaten.

4) Räckvidden är mycket smalare än påstått. workflow_data.py:404-406 returnerar redan None när `window is None` — else-grenen är oåtkomlig därifrån. Sankey fetch.py:208 (_query_local_archive_segment) och :183 bifogar alltid ett Between via `_date_filter_for_view`, och arkivvyerna har per konstruktion en preferred date column (local_archive_store.py:156-164, `_ROW_DATE_COLUMN` härleds ur den). Kvar som faktiskt nåbar väg är ENDAST data_fetch.py:346: en Hämta data-plan på en arkivvy utan datumperiod (apply_prompt_period_hint, data_fetch/plan.py:414, injicerar bara period om prompten antyder en).

5) Det som ÄR ett verkligt fynd — och som kandidaten bara nämner i förbigående — är att else-grenen hoppar över täckningskontrollen helt (jfr :606-610) och därmed bryter modulens egen kontraktsdocstring "Aldrig partiell data" (:596). Rätt åtgärd är alltså `return None` när fönster saknas (fall tillbaka till API), av KORREKTHETSskäl — inte `LIMIT`. Det ger som bieffekt en bunden minnesprofil.

6) Kandidaten är dessutom en dubblett av en redan känd, oåtgärdad planpost: wiki/optimeringsplan.md rad 55 (post 1.2) beskriver samma sak, med samma felaktiga cap-motivering. Git-historiken (`git log -- app/backend/local_archive_store.py`) visar en enda commit (9d71d6f) — inget är fixat.

Varför "osaker" och inte "avfardad": risken i den enda nåbara grenen (400 dagars dblog-arkiv, ARCHIVE_CACHE_SEED_DAYS=400, som list[dict] i en 1 Gi-podd) är reell OM en plan på en arkivvy utan datumfilter faktiskt förekommer. Det kan jag inte avgöra från koden.

**Justerad vinst (granskarens, inte svepagentens):**

Ingen mätbar latensvinst — och ingen bevisad minnesvinst. Kandidatens "OOM-risk" vilar på ett felaktigt antagande (att API-vägen är capad; den är den inte). Det som återstår är en smal härdning av ETT kodfall: `query_rows` utan datumfönster, nåbart enbart via data_fetch.py:346. Där är worst-case ett fullt 400-dagars dblog-arkiv som list[dict] (samma storleksordning som den bekräftade 449+ MB-incidenten), men jag kan inte kvantifiera sannolikheten eller radantalet utan produktionsdata. Kandidatens andra halva (LIMIT på query_snapshot_rows) har vinst = ingen, den har negativt värde (bryter item_alias-ladders). Push-down av apply_local_filters till DuckDB: vinsten är oestimerad och bär exakt den NaN/tomsträng/textoperator-risk wikin varnar för — bör inte byggas på denna grund.

**Matning som ska bekrafta vinsten:**

Ingen befintlig api_benchmark-endpoint täcker detta — vinsten är minne, inte ms, så api_benchmark är fel verktyg. Krävs: (1) Radantal och bredd i verkligheten: `SELECT count(*) FROM dblog_trans_log` mot den seedade DuckDB-filen på PVC per tenant (frey/loki/itworks) — utan detta är "449 MB" ren spekulation. (2) Minnesprofil (tracemalloc peak + RSS före/efter) av `_fetch_rows` i data_fetch.py:339 mot en seedad 400-dagars arkivfil, kört två gånger: plan MED Between-filter vs plan UTAN. Skillnaden är hela den påstådda vinsten. (3) Loggmätning i drift: räkna hur ofta else-grenen (window is None) faktiskt träffas — lägg en `logger.warning` med view+tenant på :619 och kör en vecka. Om räknaren är noll är kandidaten död och ska stängas.

**Forutsattningar innan bygge:**

Innan något byggs: (a) Bekräfta med mätning (3) ovan att else-grenen överhuvudtaget nås i drift — annars är detta dödkod-härdning. (b) Notera att fixen INTE är beteendebevarande oavsett variant: `LIMIT` inför tyst trunkering (avrådes), `return None` byter cache-svar mot API-svar som källan kapar vid 50k. Den senare är dock behavior-*restoring* (återställer läget före cachen) och fixar samtidigt att täckningskontrollen hoppas över i den grenen — men det måste redovisas som en avsiktlig beteendeändring, inte smygas in som "optimering". (c) Rör INTE query_snapshot_rows utan att först läsa sankey_inbound/fetch.py:375-380 — full läsning av item_alias är ett dokumenterat krav. (d) Skyddande tester som måste gå gröna: tests/services/test_local_archive_store.py (:63-191, särskilt :104/:134/:143 som låser None-fallbackens semantik och :146-173 för snapshot), tests/services/test_archive_cache_sync.py:138/:652, tests/services/test_sankey_inbound_service.py:304/:336/:367. Ett nytt test måste låsa exakt vad else-grenen ska göra. (e) Golden-karakterisering krävs ENDAST om push-down (fix 2) byggs — differentialtest apply_local_filters(Python) vs WHERE(DuckDB) över NaN/tomsträng/Terms/NE/textoperatorer. Rekommendation: bygg inte push-down på denna kandidat.

---

## #28 — Hämta data-exporten har inget radtak alls (max_rows=None ⇒ ingen cap) och bygger hela arbetsboken + hela JSON-filen i RAM

- **Plats:** `app/backend/routers/data_fetch.py:497-522 (_write_excel), rotorsak i 773 (_max_rows(payload.max_rows)) + 189-193 (_max_rows) + app/backend/data_fetch/engine.py:135 (project_rows)`
- **Monster:** inget-tak
- **Het vag:** nej · **Insats:** M · **Risk:** medel

**Problem (svepagentens beskrivning):**

> Wikin listar den här som en öppen lucka men antar att "radtak används som skydd i stället för streaming". Det stämmer inte — det finns inget radtak på exportvägen.
> 
> Kedjan: DataFetchRunRequest.max_rows har default None. _max_rows(None) returnerar None (rad 189-190: `if value is None: return None` — clampningen mot DATA_SOURCE_MAX_ROWS=1000 hoppas alltså helt över). project_rows(rows, cols, None) gör `limited = rows if max_rows is None else rows[:max_rows]` → ingen cap. Så projected_rows blir allt som hämtades: upp till response_row_cap=50 000 rader från API-vägen, och OBEGRÄNSAT från arkivvägen (se det andra fyndet — de två multiplicerar varandra).
> 
> Sedan gör _write_excel två fulla materialiseringar i rad: _read_data_fetch_rows kör `json.loads(path.read_text())` på hela sessionsfilen (list[dict] i RAM), och openpyxl Workbook() utan write_only håller varje cell som ett objekt tills workbo…

**Foreslagen atgard:**

> (1) Sätt ett hårt exportradtak (återanvänd _response_row_cap eller en egen EXPORT_ROW_CAP) och clampa i _max_rows så None inte betyder oändligt — `return configured if value is None else min(value, configured)`. (2) Streama arbetsboken: `Workbook(write_only=True)` + `ws.append(...)` (openpyxl skriver då rad för rad till disk i stället för att hålla Cell-objekt), alternativt xlsxwriter med `{'constant_memory': True}`. (3) Skriv sessionsraderna som NDJSON i _write_data_fetch_rows så _write_excel kan strömma rad för rad i stället för json.loads av hela filen. Verifiera med golden-karakterisering …

**Skeptikerns granskning:**

Kodfakta stämmer, jag har verifierat varje påstående: data_fetch.py:189-191 är bevisligen `if value is None: return None` (clampningen mot DATA_SOURCE_MAX_ROWS=1000 hoppas över); data_fetch.py:71 har `max_rows: int | None = Field(default=None, ...)` och frontend (app/frontend/js/data_fetch.js:171-177) skickar `null` när rutan är tom — vilket är normalfallet; engine.py:135 `limited = rows if max_rows is None else rows[: max(0, max_rows)]` cappar inte; data_fetch.py:497-523 använder `Workbook()` UTAN write_only och `_read_data_fetch_rows` (111-121) gör `json.loads(path.read_text())`. `git log -S "write_only"` ger noll träffar → inte fixat, och wiki/optimeringsplan.md:56 listar det som öppet.

MEN kandidatens ramning faller på tre punkter:

(a) Åtgärd (1) — clampa så None betyder 1000 — är INTE beteendebevarande, tvärtemot "Risk: låg". `projected_rows` går både till sessionsfilen OCH till HTTP-svaret (data_fetch.py:833) och till DOM-tabellen. Ett tak på 1000 kapar alltså varje hämtning, inte bara exporten. Det är ett produktbeslut (kräver egen EXPORT_ROW_CAP + tydlig truncation-signal), inte en optimering.

(b) Exporten är inte den första minnestoppen. /run materialiserar redan `rows` (rått), `projected_rows`, json.dump till disk och returnerar hela listan i svaret; frontend renderar dessutom VARENDA rad i en tabell utan slice (data_fetch.js:306-310). Om 50k-rads-hämtningar vore vardag skulle UI:t redan vara obrukbart — vilket är indicium på att den påstådda worst-casen sällan inträffar. Exportens topp är en separat, senare topp i samma podd, men den kommer aldrig utan att /run först överlevt samma datamängd.

(c) Kandidatens siffror (50k × 20 kol → 300-500 MB) är en uppskattning utan mätning. Dessutom är 50k inte ens ett tak: fetch_all_rows (external_data_client.py:343-378) fönsterdelar på Between-datumfilter och slår ihop, så `rows` kan överstiga response_row_cap.

Kvar som verkligt och rent beteendebevarande: `Workbook(write_only=True)` (openpyxl Cell-objekt är den enskilt största multiplikatorn per rad, grovt 5-10x rad-dictens storlek). Men jag kan inte avgöra om vinsten är verklig eller teoretisk utan att veta faktiska radantal i drift. Vägen är dessutom ljummen: ett användarklick per hämtning, ingen loop, ingen bakgrundsfrekvens.

**Justerad vinst (granskarens, inte svepagentens):**

Kan inte kvantifieras utan produktionsdata — jag vägrar signera "300-500 MB". Om verkliga exporter är <5 000 rader (vilket DATA_SOURCE_MAX_ROWS=1000 och den ocappade DOM-tabellen antyder) är vinsten i praktiken noll och kandidaten ska avfärdas. Om exporter på 20k+ rader faktiskt förekommer är `write_only=True` värt grovt 100-250 MB peak-minne i exportsteget (openpyxl Cell-overhead), vilket är materiellt i en 1 Gi-podd. NDJSON-delen ger marginellt (~samma storleksordning som listan som /run redan höll). Radtaket ger ingen prestandavinst alls — det är ett skydd, och ett beteendebrott.

**Matning som ska bekrafta vinsten:**

Steg 0 (avgör om kandidaten alls är värd något): dra `data_fetch.shown_rows`/`total_rows` från Seq/span-attributen (sätts i data_fetch.py:806-812 och 852-857) för de senaste 90 dagarnas `data_fetch.export`-spans. P95 av shown_rows < 5000 ⇒ avfärda hela kandidaten.
Steg 1 (om P95 är stor): mät peak RSS runt `_write_excel` med `tracemalloc.get_traced_memory()` eller `resource`/psutil före/efter, i ett riktat testfall som bygger en session med N=50 000 syntetiska rader × 20 kolumner och anropar `_write_excel(session)` direkt. Jämför `Workbook()` mot `Workbook(write_only=True)`. Rapportera peak-MB före/efter, inte tid.
Steg 2: verifiera att XLSX-utdata är bit-ekvivalent i värden (inte bytes) — läs tillbaka båda med openpyxl och diffa cell för cell inkl. båda bladen ("Data" + "Fråga").

**Forutsattningar innan bygge:**

1) Radtaks-delen (åtgärd 1) får INTE byggas som "beteendebevarande fix". `_max_rows(None) → DATA_SOURCE_MAX_ROWS` kapar hela /run-svaret, inte bara exporten, och tests/services/test_data_fetch_service.py:388 (som monkeypatchar DATA_SOURCE_MAX_ROWS=1) visar att semantiken är testad. Kräver produktbeslut från Emir + ett separat EXPORT_ROW_CAP + att `truncated`-flaggan i svaret/UI:t (data_fetch.js:318) faktiskt speglar exportens tak.
2) write_only-delen: `Workbook(write_only=True)` har INGEN `.active`-sheet — rad 499 `workbook.active` blir None och måste bli `create_sheet("Data")`. Bladordningen (Data före Fråga) och `_safe_cell`-typerna måste bevaras.
3) Skyddande tester: kartlägg vilka test i tests/services/test_data_fetch_service.py som rör /export/{session_id} och _write_excel. Om ingen läser tillbaka arbetsboken behövs en golden-karakterisering först (bygg XLSX på nuvarande kod, spara cellvärden som JSON, jämför efter ändringen).
4) NDJSON-delen ändrar sessionsfilens format — `_read_data_fetch_rows` används på fler ställen än exporten? (Grep bekräftar bara data_fetch.py, men rows_size_bytes-budgeten DATA_FETCH_SESSION_MAX_BYTES=128 MB bygger på filstorlek och påverkas.)
5) Rangordna mot kandidat 1.2 (arkiv-cachens obundna SELECT, local_archive_store.py:617-628) — den är den faktiska OOMKill-incidenten (132 → 449+ MB enligt wiki/optimeringsplan.md:55) och matar dessutom exakt de rader som denna kandidat sedan får i knäet. Fixa 1.2 först; den kan göra denna kandidat irrelevant.

---

## #31 — readinessProbe: initialDelaySeconds 15 + periodSeconds 10, ingen startupProbe — ren extra nedtid vid varje deploy

- **Plats:** `k8s/flow.yml:229-236 (samma i k8s/deployment.yaml:69-76)`
- **Monster:** konfig-antagande
- **Het vag:** nej · **Insats:** S · **Risk:** medel

**Problem (svepagentens beskrivning):**

> Deployen kör strategy: Recreate med replicas: 1 — gamla podden dödas helt innan den nya startar, så varje sekund innan den nya podden blir Ready är nedtid för alla användare. readinessProbe har initialDelaySeconds: 15, vilket betyder att kubelet inte ens FRÅGAR /api/health förrän 15 s efter containerstart, oavsett om appen svarat sedan sekund 5. Därefter är periodSeconds: 10, så om appen blir klar strax efter en missad proba väntar man ytterligare upp till 10 s. Det finns ingen startupProbe som skulle tillåta både en snabb readiness-cykel och tålamod med en långsam start. Sekvensen är dessutom längre än man tror: prestart-processen + uvicorns importkedja + alembic upgrade head körs alla FÖRE socketen börjar lyssna, och CPU-limiten är 300m (k8s/flow.yml:217), så importarbetet CFS-strypas. Nettot: 15 s garanterad väntan + upp till 10 s kvantiseringsförlust ovanpå den verkliga starttiden.

**Foreslagen atgard:**

> Lägg till startupProbe (httpGet /api/health, periodSeconds: 2, failureThreshold: 45 → 90 s tålamod) och sätt readinessProbe till initialDelaySeconds: 0, periodSeconds: 2, failureThreshold: 3. livenessProbe får initialDelaySeconds: 0 när startupProbe finns (kubelet håller tillbaka liveness tills startup passerat). Ändringen är ren konfig och kan inte göra starten långsammare.

**Skeptikerns granskning:**

Faktabasen stämmer: k8s/flow.yml:228-236 har readiness initialDelaySeconds 15 / periodSeconds 10 / failureThreshold 6, ingen startupProbe finns i repot, replicas 1 + Recreate (flow.yml:14-16), cpu-limit 300m (flow.yml:217). /api/health (app/backend/main.py:322-324) är DB-fri. Uvicorn kör lifespan (main.py:92-98, _run_startup_migrations → alembic upgrade head) FÖRE socket-bind, så 200 från /api/health betyder verkligen redo — ingen false-ready-risk. Inte fixat (öppen post 2.7 i wiki/optimeringsplan.md:73; git log -S "initialDelaySeconds" -- k8s/ visar bara de två ursprungliga commitsen).

MEN vinstaritmetiken håller inte. "15 s garanterad väntan" gäller bara om appen lyssnar före 15 s. Startkedjan är: prestart som egen Python-process (app/backend/prestart.py importerar SQLAlchemy + alla modeller, connectar Azure SQL, inspect) → uvicorn importerar backend.main (pandas, DuckDB, OTel-instrumentering, hela routerträdet) → alembic upgrade head i lifespan → först DÄREFTER bind. Allt vid 0,3 kärnor (varje CPU-sekund ≈ 3,3 s väggtid). Time-to-listen är med all sannolikhet > 15 s, och då kostar initialDelaySeconds: 15 exakt noll — proban hade fallerat ändå. Kvar blir bara periodSeconds-kvantiseringen: ~5 s i snitt.

Kandidaten ignorerar dessutom att de sekunderna ligger i ett mycket större fönster: Recreate kräver att gamla podden dör helt först och terminationGracePeriodSeconds är inte satt (default 30 s), plus schemaläggning, plus seed-data-initContainern (cp -rn över hela datakatalogen på RWO-PVC), plus alembic. Realistiskt fönster 60-120 s → besparingen är ~5 %.

Påståendet "kan inte göra starten långsammare" är dessutom vilseledande: den kan göra DEPLOYEN sämre. Idag dödas en långsam podd bara av liveness (initialDelay 30 + period 30 + default failureThreshold 3 ≈ 120 s budget; readiness failureThreshold 6 dödar inget). Den föreslagna startupProbe (45 × 2 s = 90 s) KRYMPER budgeten → vid kall Azure SQL / förstagångs-create_all / tung migration blir det CrashLoopBackOff och havererad release. Oredovisad beteendeförändring.

Sidonot: k8s/deployment.yaml är inte prod-manifestet (REGISTRY/flow:latest-platshållare, namespace flow, cpu 1000m — generiska kubectl apply -k-vägen enligt k8s/README.md). Bara k8s/flow.yml går via Octopus; att ändra deployment.yaml ger noll produktionseffekt.

Mönstret finns inte i katalogen: wiki/prestanda-optimeringar.md har A (DB/API-latens), B (CPU/minne), C (event-loop), D (transport), E (guardrails) — inget "konfig-antagande". Detta är deploy-ops, ingen het väg.

**Justerad vinst (granskarens, inte svepagentens):**

0-10 s per deploy, förväntat ~5 s (enbart periodSeconds-kvantiseringen) — INTE 10-20 s. De 15 s fast delay är sannolikt helt uppslukade av verklig starttid vid 300m CPU. Vinsten utgör ~5 % av ett totalt nedtidsfönster på uppskattningsvis 60-120 s (dominerat av terminationGracePeriod 30 s + initContainer + import/migration). Kan inte kvantifieras säkrare utan att mäta faktisk time-to-listen. Om det verkliga målet är kortare deploy-nedtid ligger de stora posterna någon annanstans (terminationGracePeriodSeconds, seed-initContainern, importkedjan) — probe-finjusteringen är den minsta av dem.

**Matning som ska bekrafta vinsten:**

1) FÖRST, avgörande för om kandidaten alls är värd något: mät faktisk time-to-listen. Kör produktionsimagen lokalt med `docker run --cpus=0.3 -m 1g` mot en Azure SQL-lik databas och tidsstämpla från containerstart till första 200-svaret från /api/health i en 1-sekunds-pollningsloop. Är den > 15 s är hela "15 s fast delay"-vinsten noll och bara kvantiseringen (~5 s) återstår. Alternativt i dev-namespacet: diffa pod-eventens `Started`-timestamp mot första lyckade readiness-proba.
2) Före/efter på det som faktiskt räknas: `kubectl get pod -w` och mät väggtiden från att gamla podden går Terminating till att nya podden går Ready, över minst 3 deployer före och 3 efter. Det är den enda siffra som motsvarar upplevd nedtid.
3) Ingen api_benchmark-endpoint är relevant — detta rör inte någon request-väg.

**Forutsattningar innan bygge:**

1) Mät time-to-listen (se mätning) INNAN något byggs. Är den > 15 s ska kandidaten skalas ned till "sänk periodSeconds" och startupProbe-delen omprövas.
2) Om startupProbe ändå införs: dess budget får INTE understiga dagens effektiva startbudget (liveness initialDelay 30 + periodSeconds 30 × failureThreshold 3 ≈ 120 s). Föreslagna 45 × 2 s = 90 s är en REGRESSION → använd minst failureThreshold 90 × periodSeconds 2 = 180 s. Annars riskerar en långsam Azure SQL-start / förstagångs-create_all i prestart att ge CrashLoopBackOff och havererad release — långt värre än 5 s nedtid.
3) Behåll timeoutSeconds: 5 på både liveness och readiness. Kommentaren i flow.yml:222-225 säger explicit att default 1 s är för snålt: ffmpeg (meta-analys/transkodning) CFS-stryper hela cgroupen vid 300m. Den härdningen får inte råka rullas tillbaka.
4) Ändra ENDAST k8s/flow.yml. k8s/deployment.yaml deployas inte i produktion (generisk mall med REGISTRY-platshållare).
5) Beteendebevarande: ja för själva app-koden (ingen kodändring), men NEJ för deployens felbeteende om startupProbe-budgeten krymps — det måste redovisas.
6) Testskydd: INGET. Inga tester täcker k8s-manifest. Därför måste ändringen först verifieras i Octopus dev-miljön (namespace dev-common, deployment flow-development) över minst en full deploycykel innan den går mot release/*.

---

## #32 — Desktop: hela backend-importkedjan (1,3 s) körs innan QApplication ens finns — tom skärm under uppstart

- **Plats:** `desktop/app.py:103-108 → desktop/local_runtime.py:23-26`
- **Monster:** B3
- **Het vag:** nej · **Insats:** L · **Risk:** medel

**Problem (svepagentens beskrivning):**

> desktop/main.py importerar desktop.app, som på modulnivå importerar desktop.local_runtime och desktop.web_view. local_runtime importerar i sin tur app.backend.allocation_bridge, app.backend.workflow_data, app.backend.productivity_service och app.backend.coredata_service — dvs. hela SQLAlchemy-, FastAPI- och OTel-kedjan. Allt detta körs FÖRE main() ens hinner anropa QApplication(sys.argv), så användaren ser ingenting alls (inget fönster, ingen laddvy) medan det pågår. Ironiskt nog finns redan en färdig _loading_view i MainWindow._setup_content — men den kan inte visas förrän importerna är klara. Extra pikant: observability.py:47-60 drar in hela OTel-SDK:t (~334 ms i kedjan) trots att OTEL_ENABLED är False som default (config.py:180) och desktopen aldrig sätter den.

**Foreslagen atgard:**

> Flytta `from desktop.local_runtime import DesktopLocalRuntime` och `from desktop.web_view import create_web_view` från modulnivå till funktionsnivå (inne i MainWindow._setup_content / factory-lambdorna). Visa loading-vyn först, konstruera DesktopLocalRuntime + webbvyn i en QTimer.singleShot(0, ...). Alternativt/dessutom: gör OTel-importblocket i observability.py lazy bakom settings.OTEL_ENABLED (webben sätter OTEL_ENABLED=true och påverkas inte, desktop/tester slipper 334 ms).

**Skeptikerns granskning:**

KOSTNADEN ÄR VERKLIG, MEN ÅTGÄRDEN ÄR FELSPECIFICERAD OCH VINSTEN ÄR INTE VISAD.

1) Reproducerat: `python -X importtime -c "import desktop.local_runtime"` = 1 368 004 µs kumulativt (allocation_bridge 769 ms, workflow_data 394 ms). Så själva importkostnaden finns. desktop/app.py:570-576: `main()` skapar QApplication först på rad 571 — modulimporterna på 103-108 har redan körts. Så påståendet "inget visas" stämmer på ytan.

2) MEN den föreslagna fixen fungerar inte som skriven. Att flytta `from desktop.local_runtime import DesktopLocalRuntime` (app.py:103) till funktionsnivå ändrar ingenting, eftersom app.py:104 importerar `desktop.local_app_server`, som på modulnivå gör `from desktop.local_runtime import DesktopLocalRuntime, local_response_for_request` (local_app_server.py:17). Samma sak för web_view.py:19. Hela kedjan dras in ändå. Svepagenten har missat detta.

3) Även med alla tre importerna lata: MainWindow.__init__ konstruerar `DesktopLocalRuntime()` direkt på app.py:152 och `_setup_content()` (rad 186) bygger webbvyn via browser_factory (rad 210) — allt före `window.showMaximized()` (rad 575). Kostnaden flyttas alltså bara från import till konstruktor; fortfarande före första pixel. För att faktiskt visa laddvyn först måste fönstrets livscykel struktureras om (splash eller show → processEvents → QTimer bygger innehåll). Det är inte "M / låg risk": tests/desktop/test_app.py:125/167/201 förutsätter att `_stack`, `_browser` och `_error_view` finns direkt efter __init__.

4) Vinsten är noll i total tid — kandidaten medger det själv ("utan att den totala tiden till användbar app ändras nämnvärt"). Det är en ren UX/upplevelse-ändring. Och 1,3 s är ett TAK, inte en vinst: i den frysta exe:n (flow.spec, onedir, PyQt6-WebEngine) domineras tiden till första pixel sannolikt av PyInstaller-boot + Chromium/QtWebEngine-init, inte av Python-importen. Ingen har mätt det på den byggda artefakten.

5) Mönsterklassningen B3 ("räkna om samma sak per anrop/vy") är fel — detta är importkostnad vid engångsuppstart, inte omräkning. Katalogen har inget mönster för detta, och "het väg"-kriteriet ("stor/obunden × het väg — inte en engångs-batch") talar snarast emot: desktopstart är en gång per session, ingen datamängd.

6) DELEN SOM HÅLLER (och som borde brytas ut som egen, mindre kandidat): lazy OTel i app/backend/observability.py:47-61. Verifierat: OTEL_ENABLED default False (config.py) och desktopen sätter den aldrig; app/requirements.txt rad 18-24 installerar OTel, och windows-release.yml installerar app/requirements.txt → paketen ÄR med i exe:n, så try-blocket lyckas och betalar full kostnad. Min mätning: `import app.backend.observability` = 1,08 s standalone, varav fastapi (405 ms) + sqlalchemy (226 ms) behövs ändå av de andra backend-modulerna → OTel:s egen marginalkostnad ≈ 0,3–0,4 s. Webben (OTEL_ENABLED=true) påverkas inte. MEN: `trace`/`Status` används som modulglobaler i current_trace_id (rad 141), current_span_id (152), add_span_attributes (202) och start_span (289) — att sätta dem till None när OTel är avstängt byter gren i dessa funktioner. Måste bevisas beteendebevarande, inte antas.

7) Git-historik: inget spår av tidigare försök (`git log --oneline -- desktop/app.py desktop/local_runtime.py` visar bara funktionella commits), och wiki/prestanda-optimeringar.md nämner inte desktop-uppstart alls. Så det är inte redan fixat.

Jag kan inte avgöra om vinsten är värd insatsen utan en mätning på den faktiskt byggda Windows-exe:n.

**Justerad vinst (granskarens, inte svepagentens):**

Ingen vinst i total starttid (kandidaten medger detta). Upplevd vinst: OKÄND — de 1,3 s är ett tak, inte en mätt vinst; andelen av "tid till första pixel" som är Python-import vs PyInstaller-boot vs QtWebEngine-init är omätt på den frysta exe:n. Den enda delvinst jag själv kan kvantifiera är lazy OTel: ~0,3–0,4 s kortare importtid för desktop, testsvit och lokal dev (webben opåverkad). Det räcker inte för att motivera en omstrukturering av fönstrets livscykel; en QSplashScreen direkt efter QApplication(sys.argv) skulle ge samma upplevelsevinst till en bråkdel av risken.

**Matning som ska bekrafta vinsten:**

api_benchmark är irrelevant här (ingen HTTP-endpoint). Krävs istället:
1) FÖRE-MÄTNING PÅ BYGGD ARTEFAKT (obligatorisk, saknas idag): kör Windows-release-exe:n och logga perf_counter vid processtart (desktop/main.py:1) → QApplication skapad → MainWindow.showEvent (app.py:195). Nedbrytning: PyInstaller-boot / Python-import / Qt+WebEngine-init. Om Python-importen är <20 % av tiden till första pixel faller kandidaten definitivt.
2) Importdel isolerat: `python -X importtime -c "import desktop.app"` — kumulativt totalvärde, före/efter, 3 körningar (kall + varm FS-cache).
3) Lazy-OTel-delen: `python -X importtime -c "import app.backend.observability"` före/efter (baslinje: 1 079 819 µs), plus total pytest-collect-tid.
4) Regression: `pytest tests/desktop/` måste vara grön; webbens OTel-spans måste fortfarande dyka upp med OTEL_ENABLED=true.

**Forutsattningar innan bygge:**

Innan något byggs:
1) Mät tid-till-första-pixel på den FRYSTA exe:n (flow.spec, onedir, upx) — inte i dev-python. Utan den siffran vet vi inte om 1,3 s är 80 % eller 8 % av väntetiden.
2) Åtgärden måste omfatta ALLA tre importvägarna: desktop/app.py:103, :104 (local_app_server → local_runtime.py-import på rad 17) och :105 (web_view.py:19). Att bara flytta rad 103, som kandidaten föreslår, ger noll.
3) Fönstrets livscykel: DesktopLocalRuntime() (app.py:152) och browser_factory (app.py:210) måste flyttas ut ur __init__/_setup_content till en QTimer.singleShot efter show(). Skyddande tester: tests/desktop/test_app.py:125/167/201 läser `window._stack.currentWidget()`, `_browser` och `_error_view` direkt efter konstruktion — de går sönder och måste anpassas (medvetet, inte tyst).
4) Beteendebevarande för OTel-delen: `trace`/`Status` som None när OTEL_ENABLED=False byter gren i observability.py:141, 152, 202, 289. Kräver ett karakteriseringstest som visar att current_trace_id/current_span_id/emit_flow_event ger identisk output med OTEL_ENABLED=False före och efter (fallback-trace-id-vägen).
5) Överväg först det billiga alternativet: QSplashScreen/tidig show före de tunga importerna, eller att bara göra OTel lazy. Båda ger merparten av upplevelsevinsten utan att röra MainWindow-kontraktet.

---

## #33 — `python -m backend.prestart` är en hel extra process som är en no-op efter första deployen

- **Plats:** `Dockerfile:54 + app/backend/prestart.py:29-45`
- **Monster:** manuellt-steg
- **Het vag:** nej · **Insats:** M · **Risk:** medel

**Problem (svepagentens beskrivning):**

> Container-CMD:t är `python -m backend.prestart && exec uvicorn backend.main:app`. prestart startar en egen Python-tolk, importerar backend.database + backend.models (uppmätt 575 ms importtid), öppnar en pyodbc-anslutning till Azure SQL, kör `inspect(engine).has_table("alembic_version")`, skriver ut "Schema finns redan" och dör. Först DÄREFTER startar uvicorn-processen som importerar allt igen från noll. Efter den allra första deployen mot en tom databas gör prestart alltså ingenting — och lifespan i main.py:61-89 kör redan `alembic upgrade head` för alla icke-SQLite-dialekter, så migreringen är täckt där. Kvarvarande unika jobb i prestart är bara jungfru-DB-bootstrappen (Base.metadata.create_all + alembic stamp head). Med CPU-limit 300m betalas hela tolkstarten + importerna CFS-strypt.

**Foreslagen atgard:**

> Flytta prestart-logiken in i _run_startup_migrations() i main.py: om alembic_version-tabellen saknas → create_all + `command.stamp(config, "head")` in-process (alembic.command finns redan importerad där), annars `command.upgrade(config, "head")`. Ta bort `python -m backend.prestart &&` ur Dockerfile-CMD:t. Behåll prestart-modulen som CLI för manuell körning om det behövs.

**Skeptikerns granskning:**

Faktabeskrivningen stämmer, men vinsten gör det förmodligen inte.

VERIFIERAT I KODEN:
- Dockerfile:54 = `CMD ["sh","-c","python -m backend.prestart && exec uvicorn backend.main:app ..."]` — separat tolk före uvicorn. Bekräftat.
- prestart.py:37-40: mot MSSQL görs `inspect(engine).has_table("alembic_version")` → finns den, printas "Schema finns redan" och processen dör. Efter första deployen är den alltså en ren no-op med kostnad (tolkstart + import av `backend.database`+`models` + TLS-login mot Azure SQL + en metadata-query). Bekräftat.
- main.py:61-89 `_run_startup_migrations()` kör `command.upgrade(config,"head")` för ALLA dialekter utom sqlite, in-process, med absolut script_location. Migreringstäckningen är alltså redundant. `git log -S "_run_startup_migrations"` → b3b2510 "MSSQL-härdning: dialektsäkra migrationer, startup-migrering..." — dvs prestart lämnades kvar när startup-migreringen infördes, och prestarts docstring ("migrationerna spelar inte upp rent mot MSSQL") är sannolikt inaktuell. Redundansen är alltså genuin.
- Unikt kvar i prestart = jungfru-DB-vägen (create_all + `alembic stamp head` via subprocess) + postgres-grenen.

VARFÖR JAG INTE KÖPER VINSTEN "1,5–3 s kortare nedtid":
1. Kvantisering av readiness. k8s/flow.yml: `readinessProbe.initialDelaySeconds: 15`, `periodSeconds: 10`, ingen `startupProbe`. Kubelet frågar första gången vid ~15 s och sedan var 10:e s. Att ta bort 2 s ur startsekvensen ger nedtidsvinst BARA om det flyttar podden över en probgräns — annars exakt 0 s. Utfallet är binärt (0 s eller ~10 s) och beror helt på var totala starttiden ligger, vilket ingen har mätt. Svepagentens "1,5–3 s kortare nedtid" är alltså en icke-härledd siffra: den mäter processtid, inte nedtid.
2. Vinsten är dessutom underordnad kandidat 2.7 i wiki/optimeringsplan.md (saknad startupProbe, "10–20 s"). Med en startupProbe med t.ex. periodSeconds 2 blir prestart-borttagningen värd ~1 probperiod; utan den ofta noll.
3. Nedtidsfönstret domineras av Recreate + RWO-PVC-detach/attach + image-pull + init-containern `cp -rn` över PVC:n + uvicorns egen import av pandas/duckdb/alla routers. 2 s prestart är några procent av det.
4. Vägen körs vid poddstart (deploy/omstart), inte per request. "Användaren väntar" bara i den mån Recreate-nedtiden märks.

BETEENDEBEVARANDE-INVÄNDNING (redovisas inte i kandidaten):
`prestart && exec uvicorn` ger fail-fast: misslyckas schema-setup startar uvicorn aldrig. `_run_startup_migrations()` (main.py:86-89) sväljer däremot ALLA exceptions och loggar bara. Flyttas jungfru-bootstrappen dit rakt av får man en podd som startar och serverar 500:or mot ett tomt schema. Att i stället låta lifespan kasta byter fail-fast mot att en transient Azure SQL-blipp CrashLoopBackOff:ar podden — också en beteendeändring. Det måste designas explicit.

DOKUMENTATIONSSKULD (höjer insatsen från S/M): DEPLOY.md:26,142,147, k8s/README.md:64, app/README.md:146, TESTPROTOCOL.md:33, app/backend/bootstrap_local.py:8 och kommentaren k8s/flow.yml:78 beskriver alla prestart som schemakällan.

Jag kan inte avfärda mekanismen (den är verklig och koden är genuint redundant), men jag kan inte bekräfta någon nedtidsvinst utan mätning. Detta är i första hand en arkitektur-/städkandidat, inte en prestandavinst.

**Justerad vinst (granskarens, inte svepagentens):**

Processtid: ~2–2,5 s mindre CPU-arbete per poddstart (575 ms importtid × ~3,3 CFS-faktor vid 300m + tolkstart + TLS-login + metadata-query) — plausibelt men ej mätt i containern. Faktisk NEDTIDSVINST: sannolikt 0 s i dagens uppsättning (readinessProbe initialDelay 15 s / period 10 s kvantiserar bort den); i bästa fall ett helt 10 s-hopp om totala starttiden råkar ligga precis över 15 s. Kan inte kvantifieras utan mätning. Värdet ligger i städningen (en dubblerad schema-väg bort), inte i prestanda.

**Matning som ska bekrafta vinsten:**

1) FÖRE: mät i containern tiden från processtart till första 200 på /api/health. Enklast: kör `time python -m backend.prestart` i den deployade podden (eller logga tidsstämplar runt CMD:t) och lägg till en loggrad med `time.monotonic()` i lifespan efter `_run_startup_migrations()`. 2) Mät nedtiden som faktiskt räknas: tiden från att gamla podden termineras till att nya podden blir Ready (kubectl get events / Octopus deploy-logg, eller pod `status.conditions[type=Ready].lastTransitionTime` minus `startTime`) — över minst 3 deployer före och efter. 3) Om (2) inte minskar är fixen värdelös som prestandaåtgärd → gör om den till en ren städ-PR och prioritera 2.7 (startupProbe) i stället. Ingen api_benchmark-endpoint är relevant; detta är inte en request-väg.

**Forutsattningar innan bygge:**

1) Bekräfta att `alembic upgrade head` mot en TOM MSSQL-databas faktiskt går igenom (prestarts docstring hävdar motsatsen). Om den inte gör det MÅSTE has_table-grenen (create_all + stamp head) bevaras — annars är fixen inte beteendebevarande för jungfru-DB.
2) Bestäm felsemantiken explicit: nuvarande `&&` är fail-fast; `_run_startup_migrations()` sväljer exceptions (main.py:86-89). Välj en och dokumentera den — annars byter man tyst en hård start-krasch mot tyst 500:or.
3) Golden-karakterisering krävs: ett test som startar appen mot en tom MSSQL/annan icke-sqlite-DB (containeriserad) och verifierar att alla tabeller + `alembic_version` = head skapas via lifespan. Idag skyddas denna väg av INGET test — tests/tools/test_architecture_contracts.py:142 listar bara `prestart` som tillåten modul, och sqlite-vägen (bootstrap_local) tar aldrig grenen. Utan ett sådant test bygger man om jungfru-bootstrappen blint.
4) `alembic stamp head` körs idag som subprocess (`alembic` på PATH, cwd=/repo/app). In-process `command.stamp(config,"head")` måste använda samma absoluta script_location som main.py:83.
5) Följdändringar i DEPLOY.md, k8s/README.md, app/README.md, TESTPROTOCOL.md, bootstrap_local.py-docstring och kommentaren k8s/flow.yml:78.
6) Bör bedömas TILLSAMMANS med kandidat 2.7 (startupProbe) — ensam ger den sannolikt ingen mätbar nedtidsvinst.

---

## #34 — openpyxl importeras ivrigt i 5 routers men används bara i export/import-endpoints

- **Plats:** `app/backend/routers/activities.py:8-9, persons.py:8-9, users.py:10-11, data_fetch.py:13, meta_uploads_helpers.py:28`
- **Monster:** B3
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> Fem routers har `from openpyxl import Workbook, load_workbook` på modulnivå. Alla faktiska användningar ligger inuti funktionskroppar (activities.py:354/382, persons.py:296/326, users.py:299/317, data_fetch.py:498, meta_uploads_helpers.py:429) — dvs. i Excel-export-/importvägar som körs sällan. openpyxl finns därför i importträdet för backend.main och kostar tid vid VARJE poddstart, men används bara när någon faktiskt klickar Exportera. pandas är redan lazy-importerat överallt i backend (kontrollerat), så openpyxl är den kvarvarande tunga ivriga importen. Detta är inte samma sak som den redan dokumenterade openpyxl-luckan i taxonomin (den handlar om write_only/streaming vid själva exporten, inte om importtiden).

**Foreslagen atgard:**

> Flytta importen in i respektive funktion (`from openpyxl import Workbook` precis där arbetsboken byggs; `load_workbook` + `InvalidFileException` i import-funktionen). Rent mekaniskt, ingen beteendeändring.

**Skeptikerns granskning:**

KODOBSERVATIONEN STÄMMER, VINSTPÅSTÅENDET GÖR DET INTE.

Verifierat i koden: alla fem modulnivå-importer finns (activities.py:8-9, persons.py:8-9, users.py:10-11, data_fetch.py:13, meta_uploads_helpers.py:28) och samtliga användningar ligger inne i funktionskroppar (Workbook: activities.py:354, persons.py:296, users.py:299, data_fetch.py:498, meta_uploads_helpers.py:429; load_workbook: activities.py:382, persons.py:326, users.py:317; InvalidFileException enbart i except-satser). allocation_bridge_parts/export.py:41 gör redan lazy-import — så mönstret är känt i repot. Git-historiken visar ingen tidigare lazy-import-fix (`git log -S "import openpyxl"` tomt).

Egna mätningar (inte svepagentens): `python -X importtime -c "import backend.main"` = 2 001 903 µs totalt, openpyxl-grenen = 271 805 µs (13,6 %). Jag bekräftade dessutom det svepagenten INTE nämner: numpy (82 573 µs, 23,5 MB RSS) dras in ENBART av openpyxl.compat.numbers i main:s importträd — inget annat importerar numpy eller pandas ivrigt. Så hela 272 ms + ~24 MB RSS är genuint borttagbart.

MEN: den påstådda vinsten "0,8–1,0 s kortare Recreate-nedtid" är i praktiken noll. k8s/flow.yml:229-234 sätter readinessProbe med `initialDelaySeconds: 15` och `periodSeconds: 10`. Podden kan inte markeras Ready före t=15 s oavsett hur snabbt processen startar. Nedtiden vid Recreate bestäms av terminering + schemaläggning + image-start + 15 s readiness-golv — inte av 0,27 s CPU i importträdet. Dessutom kör lifespan (`main.py:93-97`) `_run_startup_migrations()` mot Azure-MSSQL INNAN socketen börjar serva, vilket dominerar startfönstret långt mer än importerna. Att kapa 0,9 s wall-tid i en fas som redan är klar långt före t=15 s ger exakt 0 s kortare nedtid. Bara om nuvarande time-to-ready redan överskrider 15 s kan 0,9 s spela roll — och då är granulariteten 10 s per missad proba, dvs. ett lotteri, inte en förutsägbar vinst. Time-to-ready i podden är omätt.

Mönsteretiketten är också fel: B3 i wiki/prestanda-optimeringar.md:175 är "Räkna om samma sak per anrop/vy". Importtid finns inte alls i mönsterkatalogen — kandidaten är inte ett katalogiserat mönster.

Kvarvarande försvarbar vinst: ~23,5 MB RSS (mätt lokalt, mest numpy) i en podd med 1 Gi-tak och dokumenterad OOM-historik (Sankey, 2026-07-03/04). Men det är UPPSKJUTET, inte eliminerat: första Excel-export drar in openpyxl+numpy permanent i en långlivad podd. Ingen mätning finns på hur ofta poddar lever hela sin livstid utan en enda export.

Fixen är i sig trivial, S-insats och beteendebevarande (enda semantiska skillnaden: en saknad openpyxl skulle failas vid request istället för vid import — irrelevant, openpyxl är hård dep). Jag avfärdar inte kandidaten helt, men den ska INTE säljas in som nedtidsfix.

**Justerad vinst (granskarens, inte svepagentens):**

0 s kortare nedtid (readiness-golvet 15 s absorberar hela vinsten). Realistiskt: 272 ms kortare importtid (13,6 % av importträdet) — osynlig för användare — och ~23,5 MB lägre RSS i poddar som aldrig gör Excel-export. Den ursprungliga siffran 0,8–1,0 s nedtid är felaktig.

**Matning som ska bekrafta vinsten:**

Innan något byggs: mät faktisk time-to-ready i podden (`kubectl get events` / containerns startlogg → tidsstämpel för uvicorn "Application startup complete" minus containerstart). Om den är < 15 s är kandidaten värdelös som nedtidsfix och ska stängas. Om den är > 15 s: mät istället var tiden går (troligen `_run_startup_migrations` mot MSSQL, main.py:97), inte importerna.

För RSS-spåret: mät RSS i podden direkt efter startup (`/api/health` + container-metrics eller psutil-endpoint) före/efter, samt efter första Excel-export, för att visa att vinsten faktiskt består. Lokalt reproducerbart: `python -X importtime -c "import backend.main"` (272 ms openpyxl-gren) och RSS-delta 23,5 MB.

api_benchmark är irrelevant här — ingen request-latens påverkas.

**Forutsattningar innan bygge:**

1) Mät time-to-ready i podd först (se ovan). Utan den siffran är hela premissen ogrundad.
2) Beteendebevarande: ja, mekaniskt. Enda skillnaden är att ImportError skulle uppstå vid request istället för vid appstart — acceptabelt, openpyxl är en hård dependency.
3) Skyddande tester finns redan och täcker alla fem vägarna: tests/services/test_activity_import.py, test_person_import.py, test_user_import.py, test_data_fetch_service.py:822, test_meta_uploads.py:1024. De skulle fånga en trasig lazy-import direkt. Ingen golden-karakterisering behövs.
4) Om fixen görs: flytta även `InvalidFileException` in i funktionen (används bara i except-satser) — annars sitter openpyxl kvar i importträdet ändå och hela vinsten uteblir.
5) Rätta mönsteretiketten — B3 är fel; importtid saknas i wiki/prestanda-optimeringar.md och bör antingen läggas till som eget mönster eller så bör kandidaten inte kategoriseras alls.

---

## #36 — Uvicorn saknar --timeout-graceful-shutdown; ett pågående SSE-bygge kan hålla gamla podden vid liv hela terminationGracePeriod

- **Plats:** `Dockerfile:54 + k8s/flow.yml:29-36 (ingen terminationGracePeriodSeconds/preStop)`
- **Monster:** konfig-antagande
- **Het vag:** nej · **Insats:** S · **Risk:** medel

**Problem (svepagentens beskrivning):**

> Uvicorns default för timeout_graceful_shutdown är None = vänta obegränsat på att pågående requests avslutas. Appen har två långlivade SSE-strömmar (routers/sankey.py:271 och routers/productivity.py:242) som kan pågå i tiotals sekunder medan bygget körs i en arbetartråd. Får podden SIGTERM mitt i ett sådant bygge slutar uvicorn ta emot nya anslutningar men avslutar inte — kubelet väntar då hela terminationGracePeriodSeconds (default 30 s, inte satt i manifestet) innan SIGKILL. Med strategy: Recreate startas den NYA podden inte förrän den gamla är helt borta, så varje sådan sekund är extra nedtid ovanpå startsekvensen. Ingen preStop-hook och ingen explicit grace-period finns.

**Foreslagen atgard:**

> Lägg `--timeout-graceful-shutdown 5` på uvicorn-kommandot i Dockerfile-CMD:t och sätt `terminationGracePeriodSeconds: 15` på pod-specen i k8s/flow.yml. SSE-klienterna återansluter/faller redan tillbaka på GET, så en avbruten ström är inte ett datafel.

**Skeptikerns granskning:**

Koden stämmer, men vinsten är obevisad och kandidaten är en återupptäckt wiki-post.

VERIFIERAT: Dockerfile:54 kör `exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}` utan --timeout-graceful-shutdown. k8s/flow.yml:14-16 har replicas:1 + strategy: Recreate, och pod-specen (rad 29-36) saknar terminationGracePeriodSeconds och preStop. sankey.py:262-279: event_source() blockerar på `await loop.run_in_executor(None, events.get)` tills workern lägger None i kön (rad 258) — anslutningen lever så länge bygget lever, så uvicorns default (timeout_graceful_shutdown=None) väntar. `git log -S "graceful"` och `-S "terminationGracePeriodSeconds"` över alla brancher ger NOLL träffar. Inte fixat.

MEN TRE INVÄNDNINGAR:

1) Inte en ny upptäckt. wiki/optimeringsplan.md:218-222 ÄR punkt 7.3 — ordagrant samma påstående, samma filer ("Uvicorns default ar att vanta obegransat ... ett pagaende SSE-bygge kan halla gamla podden vid liv hela grace-perioden. Dockerfile:54, k8s/flow.yml"). Svepagentens "evidens" är delvis cirkulär.

2) "Upp till ~30 s" är fel tak. Att terminationGracePeriodSeconds saknas betyder inte obegränsat — k8s default är 30 s, sedan SIGKILL. Föreslagen fix (grace 15 s) sparar max ~15-25 s, och BARA i sammanträffandet deploy ∧ pågående bygge.

3) Odeklarerad blast radius: --timeout-graceful-shutdown 5 gäller ALLA pågående svar, inte bara SSE. meta_uploads_helpers.py:581,591 strömmar media via store.open_range/open_all (ingress tillåter 256 MB body) och productivity_finance_helpers.py exporterar CSV. En 5 s-cap kapar en pågående videonedladdning vid deploy. Det sker redan idag vid 30 s-SIGKILL, så det är försämring 30 s → 5 s, inte ny felklass — men det ska redovisas, inte förbigås med "SSE-klienterna återansluter ändå".

KALL VÄG + REPOTS EGEN PRISSÄTTNING: wiki/optimeringsplan.md:263 avfärdar RollingUpdate med "5 s nedtid pa en intern app ar billigt". wiki/rfid.md:114 dokumenterar network_error efter deploy som förväntat och ofarligt. Nedtiden domineras dessutom av poster som slår vid VARJE deploy — prestart som egen process (wiki 2.5, 1,5-3 s) och readinessProbe initialDelaySeconds:15 + periodSeconds:10 utan startupProbe (wiki 2.7, 10-20 s) — medan denna post bara betalar ut vid ett sammanträffande vars frekvens ingen mätt. Prioriteringen är fel även om mekanismen är sann.

**Justerad vinst (granskarens, inte svepagentens):**

Kan inte kvantifieras utan produktionsdata. Övre gräns är INTE 30 s utan ~15-25 s (kubelet SIGKILL:ar redan idag vid default 30 s), och den realiseras bara när en Octopus-deploy råkar landa mitt i ett Sankey-/Produktivitetsbygge. Frekvensen är omätt; med en handfull interna användare är förväntat värde nära noll per deploy. Vanlig deploy: 0 s vinst.

**Matning som ska bekrafta vinsten:**

Går inte att mäta med api_benchmark — detta är deploy-nedtid, inte request-latens. Krävs: (1) frekvensbevis — korsa Octopus deploy-tidsstämplar mot audit_log-rader från _audit_sankey_report (action="run"/"run_failed", sankey.py:225,250) och motsvarande produktivitetskörningar; om noll överlapp historiskt är vinsten noll. (2) effektmätning — tid från SIGTERM till pod borta (kubectl get events / poddens deletionTimestamp vs faktisk terminering) före/efter, framprovocerad genom att starta ett Sankey-bygge och deploya mitt i. Baslinjen ska tas i samma testfall.

**Forutsattningar innan bygge:**

1) Frekvensbevis först (se mätning) — utan det bygger man en fix mot en hypotetisk händelse.
2) Beteendebevarande? NEJ för --timeout-graceful-shutdown 5: den kapar även mediaströmning (meta_uploads_helpers.py:581,591, upp till 256 MB) och CSV-export vid deploy. Måste redovisas; överväg ett högre värde eller att bara sätta terminationGracePeriodSeconds (den ofarliga halvan).
3) preStop behövs inte — replicas:1 + Recreate innebär ingen endpoint-drain-race att lösa.
4) Skyddande tester: inga. Varken Dockerfile-CMD eller k8s/flow.yml täcks av testsviten (jfr det befintliga ffmpeg--threads-kontraktstestet — motsvarande kontraktstest saknas här). Ett nytt test som asserterar flaggorna i Dockerfile/manifestet bör läggas till med fixen.
5) Workertråden är daemon och skriver audit-rader med egen session (sankey.py:207,257) — vid SIGKILL/forcerad exit dör den mitt i. Det gäller redan idag vid 30 s, men en kortare grace gör fönstret vanligare. Bör bekräftas att en avbruten audit-skrivning inte lämnar halvskrivet tillstånd.

---

## #37 — PYTHONDONTWRITEBYTECODE=1 utan compileall — 220 egna .py-filer kompileras från källkod vid varje processtart, två gånger per poddstart

- **Plats:** `Dockerfile:6-10`
- **Monster:** konfig-antagande
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> Dockerfilen sätter PYTHONDONTWRITEBYTECODE=1 (ett standard-recept från Python-image-guider). pip kompilerar visserligen site-packages till .pyc vid install, men projektets EGNA 220 .py-filer i /repo/app och /repo/warehouse_tools får aldrig någon .pyc — de parsas och kompileras från källkod vid varje tolkstart, och det sker två gånger per poddstart (prestart-processen och uvicorn-processen). Med CPU-limit 300m är detta rent CPU-arbete i den dyraste delen av startfönstret. Detta är exakt taxonomins "konfig-antagande"-klass: en ärvd default som är rätt på nån annans maskin (skrivskyddad rootfs, image-storlek) och fel i vår CFS-strypta cgroup.

**Foreslagen atgard:**

> Lägg till `RUN python -m compileall -q /repo/app /repo/warehouse_tools` efter COPY-stegen i Dockerfile. compileall skriver .pyc explicit och ignorerar PYTHONDONTWRITEBYTECODE, så env-varen kan lämnas kvar (den skyddar fortfarande mot runtime-skrivningar). Verifiera vinsten genom att tidsätta `python -c "import backend.main"` i containern före/efter.

**Skeptikerns granskning:**

MEKANISMEN STÄMMER, MEN VINSTEN ÄR SANNOLIKT MASKERAD.

1) Koden gör vad som påstås. Dockerfile:6 sätter PYTHONDONTWRITEBYTECODE=1, inget compileall-steg finns (Dockerfile:33-43), och Dockerfile:54 startar två Python-processer (`python -m backend.prestart && exec uvicorn ...`) — plus en tredje, för prestart.py:22 kör `alembic` via subprocess.

2) Siffran 220 är uppblåst. 220 .py-filer finns, men bara 120 moduler under backend./warehouse_tools. laddas faktiskt av `import backend.main` (mätt via sys.modules). Resten (bl.a. delar av warehouse_tools) kompileras aldrig vid start.

3) Jag KÖRDE den mätning svepagenten föreslog, lokalt (Py 3.12, deps installerade), kall (__pycache__ raderat, DONTWRITEBYTECODE=1) vs. varm (compileall körd först), 3 varv var, `-X importtime`, summerad self-tid för våra egna moduler:
   - kall:  753 / 772 / 783 ms egen self-tid, total 2360-2391 ms
   - varm:  559 / 588 / 562 ms egen self-tid, total 2149-2218 ms
   => ca 190 ms CPU sparat per uvicorn-process. Total importtid faller ~2,37 s -> ~2,19 s (~8 %). Naiv väggklocka på `import backend.main` visade INGEN skillnad alls (2244 ms kall vs. 2365 ms varm) — vinsten drunknar i filsystemsbrus. Detta är alltså 1/2 till 1/4 av svepagentens "100-400 ms x2".

4) DÖDSSTÖTEN — det verkliga manifestet. Svepagenten resonerade om nedtidsfönstret utan att läsa probarna. `k8s/flow.yml:229-234`: readinessProbe initialDelaySeconds: 15, periodSeconds: 10, och `grep -c startupProbe k8s/flow.yml` = 0. Podden läggs in i Service:n tidigast t=15 s, därefter på ett 10-sekundersraster (15, 25, 35...). Att spara ~0,5-0,9 s väggklocka (190 ms CPU x ~3,3 CFS-stretch vid 300m, x processerna) ger DÅ NOLL sekunders kortare nedtid — om inte nuvarande starttid råkar ligga precis över en rastergräns, vilket är ett lotteri jag inte kan avgöra utan att mäta i klustret. Rätt ordning är alltså: gör optimeringsplanens punkt 2.7 (startupProbe) FÖRST; först därefter konverteras start-CPU-arbete (7.4, 2.5, 2.6) till riktiga nedtidssekunder.

5) Bekräftat att CPU-limit 300m gäller: k8s/flow.yml:216-218 (obs: k8s/deployment.yaml säger 1000m — det är inte manifestet Octopus deployar). Recreate + replicas: 1 => varje deploy ÄR nedtid. Så vägen är inte helt kall — men den är deploy-tid, inte request-tid.

6) Inget nyhetsvärde: kandidaten finns redan ordagrant som punkt 7.4 i wiki/optimeringsplan.md:223-224 ("PYTHONDONTWRITEBYTECODE=1 utan compileall — 220 egna .py-filer ... två gånger per poddstart. Dockerfile:6-10"). Svepagenten har med all sannolikhet läst wikin, inte kodat fram fyndet. `git log -S compileall` = tomt, så den är inte fixad, bara känd. Angränsande punkt 2.5 föreslår dessutom att ta bort prestart-processen helt — genomförs den halveras kandidatens egen premiss ("två gånger per poddstart").

SLUTSATS: inte avfärdad (koden stämmer, ~190 ms CPU/process är verkligt uppmätt, åtgärden är ett radbyte), men inte heller bekräftad som en vinst — den användarsynliga effekten är strukturellt sannolikt 0 s så länge readiness-golvet på 15 s står kvar, och jag kan inte falsifiera det utan att mäta i podden.

**Justerad vinst (granskarens, inte svepagentens):**

~190 ms CPU per uvicorn-process (UPPMÄTT lokalt, inte gissat), mindre för prestart/alembic som importerar färre moduler. Vid 300m CFS-throttling motsvarar det grovt 0,5-0,9 s väggklocka summerat över poddstarten. ANVÄNDARSYNLIG VINST: troligen 0 sekunder, eftersom readinessProbe.initialDelaySeconds=15 + periodSeconds=10 (utan startupProbe) sätter ett golv som ligger långt över besparingen. Vinsten realiseras först om optimeringsplanens 2.7 (startupProbe) görs först — och då är den fortfarande under 1 s.

**Matning som ska bekrafta vinsten:**

Två mätningar krävs, båda I CONTAINERN (inte på laptop):
1) CPU-vinsten (bekräftar mekanismen): `docker run --cpus=0.3 <image> python -X importtime -c "import backend.main"` — summera self-tiden för moduler som börjar på backend./warehouse_tools., kall (utan compileall) vs. varm (med compileall). Förväntat: ~750 ms -> ~560 ms egen self-tid, dvs. ~190 ms. Kör 3+ varv; väggklockan ensam är för brusig för att visa något.
2) DEN AVGÖRANDE mätningen (bekräftar att vinsten är verklig för användaren): tid från containerstart till första 200 på /api/health, dvs. tidsstämpeln för uvicorns "Application startup complete" minus poddens startTime, före/efter. Ligger totalen under 15 s är vinsten definitionsmässigt noll — då ska 7.4 läggas på is bakom optimeringsplanens 2.7. Ingen api_benchmark-endpoint är relevant: detta rör inte request-latens alls.

**Forutsattningar innan bygge:**

1) Mät poddens faktiska starttid först (se ovan). Är den < 15 s: bygg INTE fixen, den är ren no-op bakom readiness-golvet. Gör 2.7 (startupProbe) i stället — den ger enligt planen 10-20 s, dvs. en storleksordning mer.
2) Beteendebevarande, med ett förbehåll: compileall körs som root före `USER flow` (Dockerfile:45), så __pycache__ ägs av root. Det är ofarligt för läsning, och PYTHONDONTWRITEBYTECODE=1 hindrar ändå runtime-skrivning — men .pyc-invalideringen är timestamp-baserad by default och beror på att COPY bevarar .py-filernas mtime. Använd `python -m compileall -q --invalidation-mode checked-hash /repo/app /repo/warehouse_tools` för att göra invalideringen innehållsbaserad och immun mot mtime-skew. Vid miss faller Python tyst tillbaka på källkompilering — ingen kraschrisk, bara utebliven vinst (vilket också gör felet osynligt: verifiera med mätning 1, inte med antaganden).
3) Steget måste ligga EFTER COPY-stegen (rad 36-38). Ordningen relativt stamp_asset_versions (rad 43) spelar ingen roll — det verktyget rör bara frontend-HTML/JS.
4) Inga befintliga tester skyddar detta (det är ett build-steg, inte kod) — enda skyddsnätet är att imagen bygger och att HEALTHCHECK/readiness går grön. Ingen golden-karakterisering behövs; bytekod är per definition semantiskt identisk med källan.
5) Notera beroendet till punkt 2.5: tas prestart-processen bort försvinner halva den påstådda premissen.

---

## #43 — Arkivcachen: SELECT * ur DuckDB och all filtrering i Python

- **Plats:** `app/backend/local_archive_store.py:613-628 (query_archive_rows), 645-651 (query_snapshot_rows)`
- **Monster:** A1
- **Het vag:** okänt · **Insats:** L · **Risk:** medel

**Problem (svepagentens beskrivning):**

> `query_archive_rows` skickar bara datumfönstret till DuckDB (`WHERE row_date BETWEEN ? AND ?`), materialiserar **varje rad i fönstret som en Python-dict** (rad 623-626) och kör därefter `apply_local_filters(rows, filters)` — som via `_local_filter_matches` (data_fetch/engine.py:77-131) hanterar *alla* operatorer, inklusive EQ, Terms och Between. Alltså: bolags-, typ- och statusfilter som DuckDB kunde ha kört som en WHERE-klausul körs i stället i ren Python över hela fönstret, efter att alla rader redan konverterats till dicts. `query_snapshot_rows` gör samma sak utan ens ett fönster (`SELECT *` över hela snapshot-tabellen). Dessutom: `_like_pattern_to_regex` (engine.py:39-48) bygger om mönstersträngen tecken för tecken **per rad** för Like-filter, och `apply_local_filters` gör om `str(item.get("id")...)`/`str(item.get("operator")...)` per (rad, filter) i stället för en gång per filter. D…

**Foreslagen atgard:**

> Pusha ned de operatorer som är trivialt SQL-uttryckbara (EQ, NE, Terms→IN, Between, GT/GTE/LT/LTE, StartsWith/Contains/EndsWith→LIKE) till DuckDB:s WHERE-klausul med parametrar, och låt `apply_local_filters` bara köra kvarvarande (icke-uttryckbara) filter som en säkerhetsnät-passning. DuckDB filtrerar kolumnärt utan att materialisera dicts. Hoista dessutom per-filter-konstanterna (`id`, `operator`, kompilerad Like-regex) ut ur radloopen i `apply_local_filters` — de är identiska för alla rader.

**Skeptikerns granskning:**

Beskrivningen av koden stämmer i sak, men både vinstpåståendet och "beteendebevarande" faller vid granskning.

VAD SOM STÄMMER: Funktionen heter `query_rows` (inte `query_archive_rows`), men raderna är rätt. local_archive_store.py:613-617 skickar bara `WHERE row_date BETWEEN ? AND ?` till DuckDB; :623-626 bygger en dict per rad ur `fetchall()`; :628 kör `apply_local_filters`. `query_snapshot_rows`:645 kör `SELECT *` helt obundet. `apply_local_filters` (engine.py:116-131) härleder `str(item.get("id"))` och `str(item.get("operator"))` per (rad, filter), och `_like_pattern_to_regex` (engine.py:39-48) bygger om mönstersträngen tecken för tecken per rad.

VARFÖR JAG INTE BEKRÄFTAR:

1) Pushdown är INTE trivialt beteendebevarande. `_values_equal` (engine.py:51-58) numerisk-koercerar båda sidor via `_number_value` (core.py:435-449 — strippar NBSP och blanksteg, tolkar "," som decimaltecken) och faller annars tillbaka på `str(x).strip().casefold()`. `_row_value` (core.py:421-426) gör dessutom skiftlägesokänslig kolumnuppslagning. Ett naivt `WHERE company = ?` matchar alltså INTE samma rader som EQ i Python (" mg " vs "MG", "007" vs 7, "1,5" vs "1.5"). Contains/StartsWith gör `pattern.strip("%")` — kvarvarande `_`/`%` är literaler i Python men wildcards i SQL LIKE. En trogen pushdown måste byggas som en strikt SUPERSET-prefiltrering (t.ex. `lower(trim(CAST(col AS VARCHAR))) = lower(trim(?)) OR TRY_CAST(col AS DOUBLE) = TRY_CAST(? AS DOUBLE)`) med `apply_local_filters` kvar som exakt efterpass. Det gör insatsen L, inte M — och kandidaten redovisar inte detta.

2) Vinsten "10-100x" är obelagd. Reduktionen = fönstrets rader / matchande rader. Selektiviteten styrs i praktiken av bolagsfiltret, och en tenants arkivcache innehåller bara den tenantens bolag (en handfull). Realistiskt 2-5x färre dicts, inte 10-100x. Kandidatens påstående att "vinsten är noll för Sankey" är dessutom fel: `_company_filter` (sankey_inbound/fetch.py:86-96) skickar EQ/Terms till både `query_rows` (:183, :208) och `query_snapshot_rows` (:385). Omvänt gäller att vid "ALL" eller flera bolag blir filterlistan tom -> exakt noll vinst.

3) Raderna behövs delvis. På Hämta data-vägen (routers/data_fetch.py:346) ÄR de filtrerade raderna svaret till klienten — pushdown krymper bara mellanmaterialiseringen, inte resultatet. Det är gränsfallet i "INTE mönstret om"-kriteriet för A1.

4) Överlapp: exakt samma rader står redan som plan 1.2 i wiki/optimeringsplan.md ("arkiv-cachens läsväg är helt obunden", :617-628 och :587-651) med högre prioritet och EN ANNAN fix (bindning/LIMIT mot OOM). Den fixen rör samma kod och bör landa först. Git-historiken (git log på local_archive_store.py: ba7438d, 9d71d6f) visar att ingen pushdown gjorts ännu — problemet finns, men är inte fixat och inte heller mätt.

DEN DEL SOM HÅLLER UTAN FÖRBEHÅLL är den mindre: hoista per-filter-konstanterna (id, operator, kompilerad Like-regex) ut ur radloopen i `apply_local_filters`. Det är rent beteendebevarande, S-insats, låg risk — men vinsten är också liten (två korta `str()` per rad och filter), utom för Like-filter, och jag hittar ingen anropsväg i produktion som faktiskt skickar Like till cachen.

Utan produktionsdata kan jag inte avgöra fönstrets radantal, item_alias-snapshotens storlek eller hur ofta ett enskilt bolag väljs. Därför osäker, inte bekräftad.

**Justerad vinst (granskarens, inte svepagentens):**

Delad. (a) Hoisting i apply_local_filters: säker men liten — jag uppskattar några procent av filterloopen, inte mätbart på endpoint-nivå. (b) Pushdown till DuckDB: potentiellt 2-5x färre materialiserade dicts NÄR ett enskilt bolag valts (noll vinst vid ALL/flera bolag). Kandidatens 10-100x kan jag inte belägga och tror inte på. Starkast case är query_snapshot_rows (item_alias, potentiellt 100k+ rader, SELECT * utan gräns) — där är dock den verkliga vinsten toppminne, vilket redan täcks av plan 1.2.

**Matning som ska bekrafta vinsten:**

Före/efter på tre nivåer: (1) Mikrobenchmark direkt mot local_archive_store.query_rows på en seedad DuckDB-fil med realistiskt fönster (t.ex. 90 dagar) × selektivitet {1 bolag av N, ALL} — mät wall-time och tracemalloc-topp; detta är den enda mätning som isolerar just denna kod. (2) cProfile på Sankey inbound-hämtningen med DUCKDB-cachen på, för att se hur stor andel apply_local_filters + dict-bygget faktiskt är av requesten (om det är under ~10 % ska kandidaten avfärdas). (3) tools/api_benchmark.py mot Hämta data-körningen och Sankey inbound-endpointen, med cachen på, för att visa att endpointlatensen faktiskt rör sig. Krav: (2) måste visa >10 % andel innan (1) och (3) är värda att köra.

**Forutsattningar innan bygge:**

1) Golden-karakterisering av apply_local_filters MÅSTE finnas före pushdown: samma rad-uppsättning in, jämför Python-resultat mot pushdown-resultat rad för rad, för varje operator, med de kända fallgroparna: skiftlägesokänslig kolumnuppslagning (_row_value), strip+casefold, numerisk koercering ("007" vs 7, "1,5" vs "1.5", NBSP), tomma strängar/None, och Like/Contains-mönster som innehåller _ och %. Utan detta är fixen inte beteendebevarande.
2) Designkrav: SQL-predikatet ska vara en garanterad SUPERSET av Python-matchningen och apply_local_filters ska ligga kvar som exakt efterpass. Då kan ett fel i pushdown aldrig ge fel svar, bara mindre vinst.
3) Befintligt skydd: tests/services/test_local_archive_store.py (:63-191, inkl. Terms och NE på company) och tests/services/test_data_fetch_service.py (:188, :314, :343, :376) plus tests/services/test_sankey_inbound_service.py (:304, :336). De täcker operatorerna på ytan men INTE koerceringsfallen ovan — de måste utökas.
4) Ordningsfråga: plan 1.1 (DuckDB-config threads/memory_limit) och 1.2 (bindning av den obundna läsvägen) rör samma rader och är OOM-kritiska. De ska landa först; denna pushdown byggs ovanpå deras kod, annars slås ändringarna ihjäl.
5) Hoisting-delen (per-filter-konstanter ur radloopen) kan brytas ut som en separat, riskfri commit och landa oberoende av pushdown.

---

## #46 — SSE-strömmarna levererar hela slutpayloaden okomprimerad — appens två största JSON-svar gzippas aldrig

- **Plats:** `app/backend/routers/sankey.py:271-279 (+ app/backend/routers/productivity.py:240-248, app/backend/main.py:319)`
- **Monster:** D
- **Het vag:** okänt · **Insats:** M · **Risk:** medel

**Problem (svepagentens beskrivning):**

> Både Sankey - Inbound och Produktivitetsöversikten laddas i praktiken ALLTID via SSE (app/frontend/js/sankey_inbound.js:568-577 och js/productivity_overview.js:490-503 väljer EventSource; vanlig GET är bara fallback när EventSource saknas eller strömmen inte etableras). SSE-strömmens sista event är `{"type":"done","payload": <hela rapporten>}` (sankey.py:223, productivity.py:219). Starlettes GZipMiddleware har `DEFAULT_EXCLUDED_CONTENT_TYPES = ("text/event-stream",)` — verifierat i installerad starlette 1.3.1 — så hela slutpayloaden går RÅ över nätet. Wikin (prestanda-leveranslager.md rad 20-23) beskriver undantaget som ofarligt ("SSE-progressströmmarna påverkas inte"), men ingen har noterat att det är just den vägen slutpayloaden tar. Payloaden är inte liten: den innehåller `client_filters.views` med upp till CLIENT_FILTER_PREBUILD_MAX_VIEWS = 512 färdigbyggda vyer (app/backend/sankey_i…

**Foreslagen atgard:**

> Två vägar. (a) Lägst risk och samma mönster som redan finns i repot: låt `done`-eventet bara bära en kort token och låt frontend hämta payloaden med vanlig GET (`/api/sankey/inbound/payload?token=...`) — då passerar den gzip + ETag-middlewaren. Server-side-lagringen finns redan färdig i app/backend/sankey_inbound/trace.py (store_trace_rows/get_trace_rows, uuid4-hex-validering, L1+gzip-JSON-disk). Kostnad: en extra RTT, som mer än betalas av 85 % mindre överföring. (b) Alternativt: komprimera strömmen själv (StreamingResponse med `Content-Encoding: gzip` + zlib.compressobj(wbits=31) och Z_SYNC_…

**Skeptikerns granskning:**

Mekanismen stämmer — jag hittade inget att avfärda på kodnivå:
(1) sankey.py:223 lägger hela rapporten i `events.put({"type": "done", "payload": payload})` och sankey.py:271-279 returnerar den som `StreamingResponse(media_type="text/event-stream")`. productivity.py:219/240-248 gör exakt samma sak.
(2) main.py:316-319 lägger GZipMiddleware ytterst — men kommentaren där ("Starlette undantar text/event-stream automatiskt, så SSE-progressströmmarna påverkas inte") är skriven som om SSE bara bar progress. Slutpayloaden går samma väg. Kontraktstestet tests/services/test_http_delivery.py:40 (`test_gzip_middleware_leaves_sse_streams_alone`) låser dessutom fast undantaget, så en fix måste förhålla sig till det testet.
(3) SSE är default-vägen, inte fallback: sankey_inbound.js:568-577 (`loadSankeyInbound` → EventSource; `loadSankeyInboundFallback` bara när EventSource saknas eller onerror). Samma i productivity_overview.js.
(4) Datat behövs faktiskt (INTE "hämta mindre"-mönstret): client_filters.views (build.py:757-773, upp till CLIENT_FILTER_PREBUILD_MAX_VIEWS = 512, common.py:46) är hela poängen med designen — frontend byter period/bolag/only_consumed utan ny rundtur. Så det är rent leveranslager (D), inte reduktion.
(5) Inte redan fixat: `git log -S '"type": "done", "payload"'` ger bara 1f5dcf4 (införandet). Ingen k8s-ingress gzippar (inga gzip-annotationer i k8s/), så ingen kompression sker någon annanstans.

Varför ändå OSÄKER, inte bekräftad:
- **Vinsten är helt omätt.** "705 KiB → 93 KiB" är svepagentens SYNTETISKA payload, inte en riktig. Ingen instrumentering finns (ingen loggning av payload-bytes i app/backend). Utan verklig payloadstorlek per vanlig periodval (dag/vecka/månad, 1-N bolag) och utan att veta om användarna sitter på LAN (då är 700 KiB ≈ 60 ms = irrelevant) eller VPN/4G, går vinsten inte att avgöra. Kräver produktionsdata.
- **"Appens två största JSON-svar" är överdrivet.** Sankey-payloaden är stor pga 512 prebyggda vyer; produktivitetsöversiktens payload har ingen motsvarande vy-prebuild och är sannolikt en storleksordning mindre. Den delen av påståendet är obelagd.
- **Åtgärd (b) (Content-Encoding: gzip på strömmen) är riskabel** — EventSource + gzip + proxies är känsligt och skulle bryta det befintliga kontraktstestet.
- **Åtgärd (a) har en dold fälla svepagenten missar:** payload-cachen (sankey_inbound/cache.py:15) har `_CACHE_TTL_SECONDS = 0` utanför produktion. Om "done"-token-vägen bygger på att en efterföljande GET träffar den cachen, kommer desktop/dev att BYGGA OM hela payloaden (inkl. alla 512 vyer) en andra gång — dubbel byggtid. Fixen måste därför lagra payloaden explicit under token (som trace.py store_trace_rows), inte lita på TTL-cachen.
- **CPU-kostnaden är inte gratis:** Starlettes GZipMiddleware kör compresslevel=9 synkront i event-loopen. På en podd med CPU-limit 300m kan gzip av ~700 KiB kosta tiondels sekunder wall-time under throttling och blockerar den enda uvicorn-workern — vilket äter en del av den påstådda nätvinsten. Bör mätas, och ev. sänkt compresslevel övervägas.

**Justerad vinst (granskarens, inte svepagentens):**

Kan inte kvantifieras utan mätning. Mekanismen (okomprimerad leverans av appens största payload) är verklig, men vinsten kan ligga var som helst mellan "försumbar" (liten payload + LAN) och "flera hundra ms per rapportladdning" (500-800 KiB + VPN/mobil). Gzip på en JSON av den här typen ger typiskt 85-90 % reduktion, så OM payloaden verkligen är >300 KiB och användarna inte sitter på LAN är vinsten reell — men netto minus gzip-CPU på 300m-limiten.

**Matning som ska bekrafta vinsten:**

Innan något byggs — två mätningar, båda billiga:
1. **Verklig payloadstorlek:** logga (eller mät engångs i prod-podden) `len(json.dumps(payload).encode())` respektive gzip-6-storleken i sankey.py:223 och productivity.py:219, för de vanligaste periodvalen (day/week/month, ALL + enskilt bolag). Alternativt: öppna Sankey - Inbound i Chrome DevTools mot prod och läs "Transferred" för `/api/sankey/inbound/stream`.
2. **Nätverksverklighet:** mät faktisk TTFB→complete för samma request från en typisk användarklient (kontor/VPN), inte från servern.
Beslutströskel: bygg bara fixen om rå payload ≥ ~300 KiB OCH mätt överföringstid ≥ ~150 ms.
Efter fix: samma DevTools-mätning (transferred bytes + total tid för rapportladdning), plus tools/api_benchmark.py mot `/api/sankey/inbound` (GET-vägen) för att fånga gzip-CPU-kostnaden på servern.

**Forutsattningar innan bygge:**

1. Beteendebevarande kräver att client_filters.views levereras OFÖRÄNDRAT — hela klientfiltreringen (sankey_inbound.js) hänger på den. Ingen bantning av payloaden får smygas in i "leverans"-fixen.
2. Om token+GET väljs: payloaden måste lagras EXPLICIT (mönstret i app/backend/sankey_inbound/trace.py — store_trace_rows/get_trace_rows, uuid4-hex-validering, L1+gzip-disk), inte via cache.py:15-cachen som har TTL 0 utanför produktion. Annars dubbelbyggs payloaden i desktop/dev.
3. `cache: {status: hit}`-fältet (service.py:112) sätts vid cacheträff — kontrollera att frontendens cache-indikator inte börjar visa "hit" på varje laddning som bieffekt.
4. Skyddande tester som måste hållas gröna/uppdateras medvetet: tests/services/test_http_delivery.py (test_gzip_middleware_leaves_sse_streams_alone — låser SSE-undantaget), samt sankey-router-/service-testerna (grep tests/ efter `inbound/stream` och `client_filters`). En golden-karakterisering av payloadens JSON (byte-identisk före/efter) bör tas fram innan omflyttningen.
5. Auditloggen (_audit_sankey_report, sankey.py:225) körs i worker-tråden med payloaden — den får inte tappas när payloaden flyttas ut ur done-eventet.

---

## #49 — Brotli slår gzip på BÅDA axlarna — mindre payload OCH mindre CPU; statiska filer bör dessutom förkomprimeras i bygget

- **Plats:** `app/backend/main.py:319 + Dockerfile:40-43`
- **Monster:** D
- **Het vag:** ja · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> Appen komprimerar allt själv med gzip; ingressen (k8s/ingress.yaml, k8s/flow.yml:314-317) har inga komprimeringsannoteringar alls, bara proxy-buffer-inställningar. Brotli stöds av alla webbläsare över https (= produktion). Det intressanta: brotli på KVALITET 5 producerar mindre output än gzip-9 och gör det 5,5x snabbare — det är alltså inte en avvägning utan en ren förbättring. Och eftersom de statiska filerna redan har innehålls-hash + ett års immutable-cache kan de förkomprimeras med brotli-11 i Docker-bygget (dyrt en gång, gratis för alltid) i stället för att komprimeras om vid varje cache-miss.

**Foreslagen atgard:**

> Två steg, oberoende av varandra. (1) Runtime: ersätt GZipMiddleware med en middleware som förhandlar `br` och faller tillbaka på gzip (t.ex. `brotli-asgi`), eller behåll gzip men med compresslevel=6 om brotli-beroendet inte önskas. (2) Statiskt: lägg ett brotli-11-steg i Dockerfile direkt efter `python -m tools.stamp_asset_versions` (rad 43) som skriver `.br`-varianter, och låt static-vägen servera dem vid `Accept-Encoding: br`. Behöver INTE röra ingressen — nginx-ingress komprimerar inte om svar som redan har Content-Encoding.

**Skeptikerns granskning:**

Kodbeskrivningen stämmer, men kandidatens två halvor faller olika ut.

FAKTA SOM HÅLLER:
- app/backend/main.py:319 `app.add_middleware(GZipMiddleware, minimum_size=1024)` — inget `compresslevel`. Verifierat i installerad starlette 1.3.1: `def __init__(self, app, minimum_size=500, compresslevel: int = 9)`. Alltså zlib-nivå 9 på VARJE svar >1 KiB, i event-loopen (GZipResponder är ren ASGI, ingen threadpool), i EN uvicorn-worker med 300m CPU-limit. Det är en het väg (varje request, användaren väntar).
- Ingen brotli finns (`brotli_asgi` är inte ens installerad), Dockerfile:40-43 gör bara stamp_asset_versions, ingressen komprimerar inte. Inte redan fixat: `git log -S GZipMiddleware -- app/backend/main.py` ger bara 1793f32 (leveransoptimeringen 2026-07-06).

VARFÖR JAG INTE BEKRÄFTAR DEN SOM SKRIVEN:

1) Statik-halvan är kall och till stor del redan neutraliserad. wiki/prestanda-leveranslager.md punkt 2 + 4: alla `?v=<hash>`-filer får `public, max-age=31536000, immutable` OCH cache-first i service workern (app/frontend/sw.js). En användare hämtar alltså varje statisk fil ÉN gång per innehållshash. -19…-31 % på en engångshämtning i en intern app är ingen mätbar användarvinst. Värst är att kandidatens största siffra (rrweb.min.js, -31 %) är dess svagaste: `grep -rln rrweb app/frontend --include=*.html` → ENBART bug-rapporter.html. En sida som laddas nästan aldrig. Att bygga en .br-servande StaticFiles-subklass (ETag, Content-Length, Range, samspel med static_cache_headers och sw.js) för det är insats utan avkastning.

2) Den föreslagna brotli-asgi-swappen är INTE beteendebevarande, och det redovisas inte. Starlette-gzipen har `DEFAULT_EXCLUDED_CONTENT_TYPES = ("text/event-stream",)` — det är exakt det antagande som SSE-strömmarna vilar på (productivity.py, sankey.py, mcp/protocol.py; låst av tests/services/test_http_delivery.py:40). brotli-asgi har ingen content-type-exkludering. En swap skulle komprimera/buffra progress-strömmarna. Värre: testet på rad 40 bygger sin EGEN app med GZipMiddleware, så det skulle inte ens fånga en swap i main.py. Guardrail-hål.

3) CPU-halvan är plausibel men outsourcad till en påhittad siffra. Kandidatens 43,9 ms gzip-9 gäller en "syntetisk 652 KiB JSON". Inget i repot visar att sådana svar finns: api_benchmark mäter bara ms, inte bytes (artifacts/api_benchmark/baslinje-20260707.json innehåller inga storlekar), och wikin dokumenterar inga payload-storlekar. Dessutom har API-GET redan ETag/304 + klientcache + SWR, så kroppen skickas ofta inte alls. Jag kan inte utan mätning avgöra om gzip-9 kostar 2 ms eller 40 ms per svar.

DET SOM ÖVERLEVER: en enradare — `compresslevel=5` (eller 6). Ingen ny dependency, ingen SSE-risk, dekomprimerad kropp bit-identisk. Men jag vägrar sätta en procentsiffra på den innan payload-storlekarna är mätta.

**Justerad vinst (granskarens, inte svepagentens):**

Statik-förkomprimering + brotli-swap: ingen (kall väg / ej beteendebevarande). Kvar: gzip compresslevel 9→5-6, en rad. Uppskattad CPU-besparing några ms per stort JSON-svar i event-loopen; sannolikt <1-2 % av medianlatensen för /api/overview (970 ms) och /api/schedule (765 ms), som domineras av DB. Kan inte kvantifieras hårdare — repot mäter inte svarens byte-storlekar någonstans, så kandidatens 36 ms-vinst är en gissning på en syntetisk payload.

**Matning som ska bekrafta vinsten:**

Steg 0 (obligatoriskt, avgör om fixen är värd något): utöka `tools/api_benchmark` att logga `Content-Length` (komprimerat) och dekomprimerad storlek per endpoint mot flow-development för de 6 endpoints i tools/latency_budgets.json. Mät sedan `zlib.compress(body, 9)` vs `(body, 5)` (tid + bytes) på de VERKLIGA kropparna. Är största kroppen <100 KiB och deltat <5 ms → lägg ner kandidaten helt.
Steg 1 (före/efter): `python -m tools.api_benchmark --base-url https://flow-development.nowastelogistics.com --budget tools/latency_budgets.json`, jämför median_ms för /api/overview?year=2026&week=27, /api/schedule?...&weekday=5 och /api/persons mot artifacts/api_benchmark/baslinje-20260707.json. Vinsten ska synas som lägre median vid oförändrad DB-tid, plus lägre pod-CPU.

**Forutsattningar innan bygge:**

Beteendebevarande för compresslevel: ja — dekomprimerad kropp är identisk, endast Content-Length ändras. Skyddande tester som redan finns: tests/services/test_http_delivery.py (gzip på stor JSON/JS, ingen gzip på små svar, SSE lämnas orörd, ETag/304, immutable-cache-headers) och tests/tools/test_stamp_asset_versions.py. Ingen golden-karakterisering behövs för nivåbytet.
OM någon ändå vill driva brotli-spåret måste FÖRST: (a) ett app-nivå-SSE-test läggas till som går genom main.py:s RIKTIGA middleware-stack (dagens test bygger en egen app och skyddar därför inte mot en swap), (b) det verifieras att den valda middlewaren exkluderar text/event-stream, (c) Brotli-wheel finnas för python:3.12-slim-bookworm (ingen kompilering i imagen), (d) ETag-middlewaren (main.py:280-313) kontrolleras — den ligger innanför komprimeringen och får inte se Content-Encoding.

---

## #50 — stamp_asset_versions stämplar bara .js/.css — ikoner och manifest får no-cache och cachas aldrig av service workern

- **Plats:** `tools/stamp_asset_versions.py:31-33`
- **Monster:** D
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> Regexen är `(?:src|href)="(/[^"?]+\.(?:js|css))` — bara .js och .css. Men backendens `_IMMUTABLE_STATIC_SUFFIXES` (main.py:238) täcker redan `.js .css .svg .png .ico .woff .woff2` och service workern (sw.js:9) har `VERSIONED_ASSET_RE = /\.(?:js|css|svg|png|ico|woff2?)$/`. Infrastrukturen finns alltså — men stämplingen levererar aldrig ett `?v=` för något annat än JS/CSS. Följden: varje HTML-sida (samtliga 25 har raderna) refererar `/favicon.svg` (27 KB), `/favicon.ico` (123 KB), `/app-icon-192.png` (50 KB) och `/manifest.webmanifest` UTAN `?v=` → static_cache_headers-middlewaren faller till `Cache-Control: no-cache` (main.py:257) → webbläsaren revaliderar dem vid varje sidnavigering, och service workerns fetch-handler hoppar över dem helt (sw.js:33 kräver `?v=`). Sidbyten i Flow är riktiga sidladdningar, så detta återkommer varje gång användaren byter vy.

**Foreslagen atgard:**

> Utöka `_ASSET_TAG_RE` till att även matcha `.svg|.png|.ico|.woff2?|.webmanifest` i src/href. Middleware och SW behöver inte ändras — de stödjer redan suffixen (lägg bara till `.webmanifest` i `_IMMUTABLE_STATIC_SUFFIXES` om manifestet ska med). Kontraktstestet tests/tools/test_stamp_asset_versions.py fångar redan taggar som inte går att stämpla, så utvidgningen är självförsvarande. Sidoobservation: favicon.ico på 123 KB och favicon.svg på 27 KB är i sig absurt stora för ikoner — värt en separat städning.

**Skeptikerns granskning:**

Grundpremissen HÅLLER vid läsning. tools/stamp_asset_versions.py:31-33 matchar faktiskt bara `(?:js|css)`, medan app/backend/main.py:238 (INTE `main.py:238` som kandidaten skriver) har `_IMMUTABLE_STATIC_SUFFIXES = (".js", ".css", ".svg", ".png", ".ico", ".woff", ".woff2")` och sw.js:9 har `VERSIONED_ASSET_RE = /\.(?:js|css|svg|png|ico|woff2?)$/`. Infrastrukturen finns men matas aldrig. Grep bekräftar 25 HTML-sidor med alla fyra taggarna (+ /flow-logo.svg på login/set-password/meta-upload), och filstorlekarna stämmer (favicon.ico 123135 B, favicon.svg 26953 B, app-icon-192.png 50377 B). `git log` visar att bara 1793f32 rört filen — inte fixat.

MEN tre bärande delar av kandidaten är FEL:

1. Manifest-benet kollapsar. `.webmanifest` finns INTE i `_IMMUTABLE_STATIC_SUFFIXES` och är inte `.html`, så `elif` på main.py:253 träffar aldrig — middlewaren sätter INGEN Cache-Control alls, inte `no-cache` som påstås (main.py:257 nås aldrig). StaticFiles ETag/Last-Modified gör att webbläsaren heuristikcachar den. Den är dessutom 443 B. sw.js:9 saknar också `webmanifest`. Påståendet "middleware och SW behöver inte ändras" är alltså falskt för manifestet.

2. "Kontraktstestet ... är självförsvarande" är falskt — fixen SÖNDRAR testet. tests/tools/test_stamp_asset_versions.py:72 hårdkodar `(?:js|css)` i `raw_reference_re`. Breddas `_ASSET_TAG_RE` får `stamped_refs` (rad 79) med ikonerna medan `raw_refs` inte gör det → assertionen `raw_refs == stamped_refs` (rad 80) failar. Testet måste ändras i samma commit.

3. "Het väg: ja" håller inte. Ikoner/manifest hämtas med LÄGSTA prioritet, är inte renderblockerande, och är — som kandidaten själv medger — redan 304 utan payload. Inget blockerar FCP/LCP eller någon API-latens; ingen användare väntar. Chrome hämtar dessutom typiskt bara en ikon per `rel` och hoppar över `rel="alternate icon"` när SVG:n funkar, så realistisk besparing är ~1 villkorad request per navigering, inte 3. SW:n registreras bara över https (foundation.js:356) → desktop och dev får noll oavsett. 123 KB-favicon.ico kostar bara vid kall cache, och immutable-stämpling minskar inte förstagångsbytes alls.

Defekten är alltså äkta (ikoner får aldrig `?v=` och blir aldrig SW-cacheträffar) men det är en oavslutad implementation / konsistensstädning, inte den RTT-vinst den säljs som. Jag kan inte från repot avgöra om Chrome faktiskt återhämtar de tre ikonerna vid varje navigering eller heuristikcachar/hoppar över dem — det kräver en riktig nätverkswaterfall mot den deployade https-appen.

**Justerad vinst (granskarens, inte svepagentens):**

Marginell. Realistiskt ~1 (inte 3) lågprioriterad villkorad request per sidnavigering som försvinner, helt utanför kritiska vägen — 0 ms på FCP/LCP/API-latens, ~0 sparade bytes (redan 304). Serversidan sparar några requests genom den enda uvicorn-workern (300m CPU), men vid Flows användarantal är det brus. Gäller dessutom BARA webb-prod över https (SW registreras inte på http → desktop/dev får noll). Kan inte kvantifieras i ms utan waterfall mot prod. Värdet är främst korrekthet/konsistens: infrastrukturen i main.py:238 och sw.js:9 är byggd för ikonerna men får dem aldrig. Den STÖRRE vinsten kandidaten nämner i förbigående — favicon.ico 123 KB, favicon.svg 27 KB, app-icon-192.png 50 KB, flow-logo.png 1,1 MB — är kall-cache-bytes och en helt separat, mer värd städning.

**Matning som ska bekrafta vinsten:**

INTE api_benchmark/latency_budgets — de mäter API-endpoints och ser inte statiska filer alls; denna kandidat är osynlig där. Rätt mätning: (1) DevTools nätverkswaterfall mot den deployade https-appen (SW aktiv, "Disable cache" AV, warm cache): navigera mellan 5 sidor och räkna antal requests + Priority + status för /favicon.svg, /favicon.ico, /app-icon-192.png, /manifest.webmanifest, före vs efter. Detta är också det som avgör om kandidaten alls är verklig — om Chrome redan hoppar över .ico/apple-touch-icon är vinsten noll. (2) Serversidan: räkna requests per statisk ikon-path i åtkomstloggen (http_route/endpoint_group, app/backend/main.py:224-227) över ett arbetspass, före/efter. (3) Bekräfta i DevTools > Application > Cache Storage att flow-static-v1 faktiskt får ikonerna efter fixen.

**Forutsattningar innan bygge:**

1. Mät FÖRST (se mätning) — bygg inte fixen förrän waterfallen visar att ikonerna verkligen revalideras per navigering. Är de heuristikcachade eller överhoppade av webbläsaren är vinsten noll och kandidaten ska avfärdas.
2. tests/tools/test_stamp_asset_versions.py MÅSTE ändras i samma commit: `raw_reference_re` (rad 72) och slut-assertionen (rad 83) hårdkodar `(?:js|css)` och failar annars när `_ASSET_TAG_RE` breddas. Detta är skyddet — men det skyddar bara stämplingen, inte cache-beteendet.
3. Beslut om manifestet: att bara lägga `.webmanifest` i regexen är verkningslöst. Ska det med krävs ÄVEN `.webmanifest` i `_IMMUTABLE_STATIC_SUFFIXES` (app/backend/main.py:238) OCH i `VERSIONED_ASSET_RE` (sw.js:9). Rekommendation: lämna manifestet (443 B, redan heuristikcachat) och ta bara ikonerna — då gäller kandidatens "middleware/SW behöver inte ändras" faktiskt.
4. Beteendebevarande: ja för ikonerna, förutsatt att hash-URL:en byter när filen byter (den gör det — sha256 av innehållet). Verifiera att sw.js:s cache-first inte kan låsa fast en gammal ikon: URL:en byter vid innehållsbyte, så OK.
5. Paritet webb/desktop: desktop läser ostämplade repofiler över http och påverkas inte — men verifiera att `/flow-logo.svg` på login/set-password/meta-upload fortfarande laddas i PyQt-appen efter breddad regex (repofilerna stämplas aldrig, så det bör vara en no-op — bekräfta).
6. Kör `python -m tools.stamp_asset_versions --check` samt Docker-bygget efteråt: stämplingen failar hårt (returkod 1) om någon ny matchad tagg pekar på en fil som inte finns.

---

# AVFARDADE (15)

Skeptikern lyckades. Bygg INTE dessa. Skalen ar lika larorika som fynden.

## #04 — data_fetch hämtar oberoende externa API-segment och item_alias-batchar helt seriellt

- **Plats:** `app/backend/routers/data_fetch.py:391-400 och 456-468`
- **Monster:** NYTT:seriell-oberoende-extern-io
- **Het vag:** nej · **Insats:** M · **Risk:** medel

**Problem (svepagentens beskrivning):**

> `_fetch_rows_with_segments` loopar retention-segment och gör `rows.extend(_fetch_rows(segment, ...))` — ett externt HTTP-anrop per segment, i serie. `_fetch_package_alias_rows` gör samma sak värre: den delar upp distinkta item_num i batchar om `PACKAGE_ALIAS_ITEM_BATCH = 400` och kör `alias_rows.extend(_fetch_rows(alias_plan, ...))` per batch, i serie. Anropen är helt oberoende (ren läsning, resultaten konkateneras). Med de radvolymer koden själv säger sig hantera (kommentaren på rad 413-416: item_alias >50k rader/bolag; wikin: aggregering över upp till 50k plockrader) blir det lätt 5-20 batchar × extern RTT mot datakällans API. Hela kedjan körs redan korrekt i threadpool (`run_in_threadpool` på rad 702 och 484-487) så event-loopen är fri — men **användaren väntar** seriellt på N rundresor som kunde gjorts parallellt. Det finns noll `asyncio.gather` i hela app/backend (grep: 0 träffar).

**Foreslagen atgard:**

> Parallellisera batcharna/segmenten. Två varianter: (a) inuti den befintliga sync-funktionen, `concurrent.futures.ThreadPoolExecutor(max_workers=4)` + `executor.map(...)` och konkatenera i ursprunglig ordning (`list(map)` bevarar ordningen); eller (b) i async-lagret, bygg planerna först och kör `await asyncio.gather(*[run_in_threadpool(_fetch_rows, p, ...) for p in plans])`. Sätt ett tak (4-6 samtidiga) så datakällans API inte överbelastas, och behåll ordningen så `execute_package_breakdown` får bit-identisk indata.

**Skeptikerns granskning:**

Kandidaten faller på tre punkter, varav två är rena faktafel i svepagentens läsning.

(1) SEGMENT-HALVAN ÄR FALSK. `_fetch_rows_with_segments` (data_fetch.py:391-400) loopar över `segments["segments"]`, som byggs av `build_retention_segments`. Dess docstring säger uttryckligen "1–2 hämtningsplaner att slå ihop" (app/backend/data_fetch/segments.py:130-131) och samtliga return-vägar (segments.py:165, 172-176, 199+) returnerar en lista med exakt 1 eller 2 segment. Det finns ingen väg till "5-20 batchar". Dessutom är det ena segmentet alltid en `dblog_*`-arkivvy, och `_fetch_rows` (data_fetch.py:344) kortsluter arkivvyer mot den lokala DuckDB-cachen: `if view in ARCHIVE_TO_LIVE and local_archive_store.is_enabled()`. Cachen är PÅ i produktion (`k8s/configmap.yaml:39`: `ARCHIVE_CACHE_ENABLED: "1"`). I prod är alltså typfallet ett lokalt DuckDB-anrop + ett externt live-anrop. Att parallellisera två anrop varav ett är lokalt är brus.

(2) ALIAS-HALVAN ÄR VERKLIG MEN ÅTGÄRDEN ÄR FEL FIX. `_fetch_package_alias_rows` (438-468) gör mycket riktigt ett externt Terms-anrop per 400 item_num, seriellt. MEN: `item_alias` är redan synkad till den lokala DuckDB-cachen — `app/backend/archive_cache_sync.py:57`: `SYNC_SNAPSHOT_VIEWS: tuple[str, ...] = (PACKAGE_ALIAS_VIEW,)` — och Sankey läser den redan lokalt via `local_archive_store.query_snapshot_rows(tenant, view_id, filters)` (`app/backend/sankey_inbound/fetch.py:385`). Anledningen till att data_fetch missar den är att `_fetch_rows` bara konsulterar cachen för `ARCHIVE_TO_LIVE`-vyer (dblog_*), och `item_alias` är en snapshot-vy, inte en arkivvy (`data_fetch/segments.py:38`). Rätt åtgärd är alltså att ELIMINERA de externa anropen (ett lokalt `query_snapshot_rows` + `apply_local_filters`, N -> 0 rundresor), inte att köra dem parallellt (N -> ceil(N/4)). Att bygga en ThreadPoolExecutor-fan-out mot datakällans API på en väg som i prod inte borde röra API:et alls är att optimera bort fel kostnad — och det tillför risk: `_api_client_or_503` (data_fetch.py:214-226) konstruerar en NY `ExternalDataClient` per `_fetch_rows`-anrop, så 4-6 parallella batchar blir 4-6 samtidiga klienter/auth-vägar mot datakällan.

(3) VÄGEN ÄR INTE HET. Bara två anropare: `data_fetch.py:776` (Hämta data — ett ad-hoc-frågeverktyg vars request redan domineras av ett MiniMax-LLM-anrop, `_call_minimax` på rad 303) och `settings.py:472` (`POST /productivity-finance/calculation/test` — en admin-knapp bakom `require_view_access("productivityFinanceSettings", "edit")`). Ingen av dem körs ofta. Och antalet batchar är okänt men troligen litet: `item_nums` = distinkta item_num i plockraderna, batchstorlek 400 (rad 417) — vid ett normalt bolagssortiment blir det ofta 1-3 batchar, inte 10. Svepagentens "10 batchar × 1 s" är ren gissning som varken koden eller wikin stöder.

Enligt "INTE mönstret om"-kriterierna i wiki/prestanda-optimeringar.md: mängden är redan bunden och liten (≤2 segment; batchning införd med flit i 9d71d6f för att undvika radtaks-trunkering), vägen är kall, och den påstådda kostnaden är delvis redan borttagen av arkivcachen.

SPIN-OFF (egen kandidat, inte denna): "data_fetch:_fetch_package_alias_rows använder inte den lokala item_alias-snapshoten som Sankey redan använder". Den är värd att formulera separat — men den ska mätas, inte antas, och den har sin egen minnesfråga (>50k alias-rader/bolag in i minnet i en 1 Gi-podd, vilket Sankey redan gör).

**Justerad vinst (granskarens, inte svepagentens):**

Ingen för den föreslagna åtgärden (parallellisering). Segment-loopen är hårt bunden till ≤2 anrop varav det ena är lokalt i prod; alias-loopen är oftast 1-3 batchar på en kall väg. En parallellisering skulle i bästa fall spara någon sekund i ett sällsynt worst-case, till priset av samtidiga klienter mot datakällan. Den enda potentiellt riktiga vinsten ligger i en ANNAN fix (läs item_alias från den befintliga DuckDB-snapshoten, N externa anrop -> 0), och den kan jag inte kvantifiera utan att mäta datakällans svarstid.

---

## #06 — Meta-uppladdningen gör en DB-dubblettkoll per fil på event-loopen

- **Plats:** `app/backend/routers/meta_uploads.py:214`
- **Monster:** C1
- **Het vag:** nej · **Insats:** M · **Risk:** medel

**Problem (svepagentens beskrivning):**

> `upload_meta_media` är `async def`. ffprobe-blockeraren är redan fixad (rad 233-241, `asyncio.to_thread` — dokumenterat i wikin). Men kvar i samma per-fil-loop ligger `existing = db.query(MetaMediaUpload).filter(MetaMediaUpload.content_hash == content_hash).first()` — en synkron ODBC-rundresa **per fil**, på event-loopen, för upp till `MAX_META_UPLOAD_FILES` filer. Dessutom skriver `_stream_upload_to_store` (meta_uploads_helpers.py:466-497) varje 1 MB-chunk med blockerande `writer.write(chunk)` + sha256-uppdatering (media_store.py:57-73) — den loopen har visserligen en `await upload.read()` per varv som ger en yield-punkt, så den är mildare, men sha256+diskskrivning av en 500 MB-video är ändå hundratals ms ackumulerad CPU på loopen. Detta är C1-rester som överlevde ffprobe-fixen.

**Foreslagen atgard:**

> (1) Lyft ut dubblettkollen ur loopen: samla alla `content_hash` och gör **en** `WHERE content_hash IN (...)`-query i `run_in_threadpool` (löser både C1 och en A2-N+1 i samma grepp). (2) Eventuellt flytta chunk-skrivningen till `await run_in_threadpool(writer.write, chunk)` — mät först, det kan vara call-overhead-negativt (jfr wikins reverterade _row_text-motförsök).

**Skeptikerns granskning:**

Koden finns där svepagenten säger — meta_uploads.py:214 kör `db.query(MetaMediaUpload).filter(content_hash == ...).first()` per fil i en `async def`-loop. Men vinsten bygger på tre felaktiga premisser.

(1) MÄNGDEN ÄR BUNDEN TILL 6, INTE 10+. config.py:118 sätter `MAX_META_UPLOAD_FILES: int = 6`, och routen avvisar fler (meta_uploads.py:186-190). Svepagentens räkneexempel "10 filer ≈ 0,4 s" är omöjligt. Taket är 6 rundresor ≈ 0,22 s på dev-topologin (37 ms/RTT) och klart lägre i prod där app+DB delar datacenter. Wikins krav (prestanda-optimeringar.md:284) är att kostnaden ska vara "stor/obunden × het väg" — här är den bunden och liten. Detta är exakt "mängden är redan bunden/liten"-kriteriet.

(2) FRÅGAN ÄR EN UNIK INDEXERAD SEEK. models.py:435: `Index("ux_meta_media_uploads_content_hash", "content_hash", unique=True)`. Ingen scan, inget DB-arbete att spara — bara ren RTT.

(3) CPU-PÅSTÅENDET BYGGER PÅ EN FIL SOM INTE KAN EXISTERA. Svepagenten räknar på "en 500 MB-video". config.py:119-120 sätter MAX_META_UPLOAD_FILE_BYTES = 96 MB och MAX_META_UPLOAD_BATCH_BYTES = 192 MB, och `_stream_upload_to_store` (meta_uploads_helpers.py:472-489) tvingar gränserna *under* strömningen (413 vid överskridande). Premissen är ~5x överdriven.

CHUNK-LOOPEN ÄR INTE ETT C1. meta_uploads_helpers.py:478: `while chunk := await upload.read(UPLOAD_CHUNK_BYTES)` ger en yield-punkt per 1 MB; sha256+write av 1 MB är ~3-5 ms, så loopen blockerar aldrig sammanhängande utan interfolieras i små skivor. Att flytta `writer.write` till threadpool = ~192 threadpool-hopp per batch — exakt den call-overhead-fälla wikin redan mätt och reverterat en gång (B3, `_row_text`-motförsöket 5,2 s -> 8,8 s, rad 197-202). Svepagenten flaggar själv detta som osäkert.

VÄGEN ÄR SVAL. Meta-upload saknas helt i tools/latency_budgets.json och tools/api_benchmark.py — den är inte klassad som het väg. Väntetiden domineras av nätverksöverföring av upp till 192 MB; 6 indexerade seek är brus i jämförelse.

ÅTGÄRDEN ÄR INTE HELLER GRATIS. Hashen är känd först *efter* strömningen (rad 199, `content_hash = stored.sha256`), så en `IN (...)`-batchning kräver tvåpass-omskrivning av routen. `index` från `enumerate` (rad 192) matar `_stored_filename` (rad 228) och räknar idag alla filer inklusive dubbletter — en omstrukturering riskerar tyst ändra lagrade filnamn. Icke-trivial refaktor av en 100-radersroute för att spara några indexerade rundresor.

Den verkliga boven i denna route (ffprobe-subprocess, 20 s-tak) är REDAN fixad med `asyncio.to_thread` (rad 233-235, dokumenterat i wikin rad 231). Det som är kvar är rester under mätbarhetströskeln.

**Justerad vinst (granskarens, inte svepagentens):**

ingen. Worst case ~0,22 s event-loop-tid på dev (6 filer × 37 ms), sannolikt 10-25 ms i prod — i en request som ändå strömmar upp till 192 MB. Ligger under brusnivån och saknar mätinstrument. Chunk-skrivnings-delen bedöms som negativ (call-overhead).

---

## #07 — Historik-chatten materialiserar 1000 ORM-rader och bygger LLM-kontext på event-loopen

- **Plats:** `app/backend/routers/audit_logs.py:552-568`
- **Monster:** C1
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> `interaction_chat` är `async def`. MiniMax-anropet är korrekt avlastat (`await run_in_threadpool(_call_minimax, ...)`, rad 570). Men **före** det körs `rows = list(db.execute(query).scalars())` — en blockerande ODBC-rundresa som materialiserar upp till 1000 `UserInteractionEvent`-ORM-objekt — och därefter `_interaction_chat_context(rows)` som bygger en stor kontextsträng, allt på event-loopen. Liten i absoluta tal men helt onödig: hela pre-processingen kunde legat i samma tråd.

**Foreslagen atgard:**

> Flytta `db.execute(...)` + `_interaction_chat_context(rows)` in i en `run_in_threadpool`-funktion (samma tråd, sekventiellt, så request-sessionen aldrig används från två trådar samtidigt).

**Skeptikerns granskning:**

Koden ÄR som svepagenten beskriver — ingen hallucination. audit_logs.py:528 är `async def interaction_chat`, `rows = list(db.execute(query).scalars())` på rad 552 ligger på event-loopen, `_interaction_chat_context(rows)` anropas inline i f-strängen på rad 566, och bara `_call_minimax` är avlastat (rad 572). Formellt är det C1. Kandidaten faller ändå på wikins EGNA acceptanskriterium (wiki/prestanda-optimeringar.md:284-286): "bekrafta att mangden/kostnaden ar verklig (stor/obunden × HET VAG)". Båda faktorerna är små här.

(1) MÄNGDEN ÄR REDAN BUNDEN. audit_logs.py:540 har `.limit(1000)`, och `_interaction_chat_context` (app/backend/routers/audit_logs_helpers.py:554) klipper dessutom råeventen till `rows[:200]`. Resten är sex `Counter`-svep över max 1000 rader + en `json.dumps`. Inget obundet, inget som växer med datamängden.

(2) VÄGEN ÄR ISKALL. Endpointen är `require_super_user`-gatead (rad 531) och triggas av att en admin manuellt skriver en chattfråga. Den finns varken i tools/api_benchmark.py eller tools/latency_budgets.json — den har aldrig betraktats som latenskritisk.

(3) INGEN ANVÄNDARE VINNER NÅGOT. Requestens wall-clock domineras av MiniMax-anropet (sekunder), som redan är avlastat. Att flytta DB-läsningen till tråden gör anropet noll millisekunder snabbare för anroparen — arbetet är sekventiellt oavsett. Enda effekten är att samtidiga requests slipper head-of-line-blockering under ett ~60 ms-fönster, några gånger per dygn på en enda uvicorn-worker. Total borttagen loop-blockering: långt under en sekund per dag.

(4) INTE REDAN FIXAT, men det är medvetet lämnat: tests/tools/test_performance_contracts.py:183 pinnar exakt `"await run_in_threadpool(_call_minimax" in audit_logs` — kontraktet täcker LLM-anropet, inte DB-läsningen. Jämför data_fetch.py:303 som avlastar BÅDE `_fetch_rows` och `_call_minimax` (rad 178-179 i contract-testet) — där är vägen het och datamängden upp till 50k rader. Kontrasten är precis poängen: teamet har redan gjort avvägningen per endpoint.

Avfärdas som prestandaoptimering. Den kan möjligen motiveras som ren hygien/konsekvens, men får då inte säljas in som en mätbar vinst — det finns ingen.

**Justerad vinst (granskarens, inte svepagentens):**

ingen (mätbart). Det som faktiskt flyttas är ~37 ms DB-RTT (wiki/prestanda-optimeringar.md:34, Azure northeurope) + ORM-materialisering av <=1000 rader + strängbygge ≈ 50-90 ms loop-blockering per anrop — inte svepagentens 50-200 ms. Anropsfrekvens: några gånger per dygn (super-user, manuell chatt). Total borttagen event-loop-blockering: <1 s/dygn. Anroparens egen latens förbättras med exakt 0 ms.

---

## #10 — Settings-valideringen blankar bara HELSTRÄNGS-platshållare — inbäddade #{VAR} överlever (OTEL-endpoint och -header)

- **Plats:** `app/backend/config.py:48-59`
- **Monster:** konfig-antagande
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> Guardrailen efter GEMINI_API_BASE_URL-incidenten är `_UNSUBSTITUTED_PLACEHOLDER.fullmatch(value.strip())`. fullmatch betyder att bara värden som ÄR exakt en platshållare blankas. I k8s/flow.yml finns tre värden där platshållaren är INBÄDDAD i en längre sträng: OTEL_EXPORTER_OTLP_ENDPOINT="#{OPENTELEMETRY_URL}/v1/traces" (rad 192), OTEL_EXPORTER_OTLP_LOGS_ENDPOINT="#{OPENTELEMETRY_URL}/v1/logs" (rad 194) och OTEL_EXPORTER_OTLP_HEADERS="X-Seq-ApiKey=#{OPENTELEMETRY_TOKEN}" (rad 196). Saknas/omdöps OPENTELEMETRY_URL i Octopus lämnas texten ordagrant kvar, passerar valideringen orörd och matas rakt in i OTLPSpanExporter(endpoint=...) (observability.py:431-435) och OTLPLogExporter (:377). Med OTEL_ENABLED=true och TRACES_SAMPLE_RATE=0.5 innebär det att BatchSpanProcessor-tråden försöker exportera mot en ogiltig URL vid varje batch, med exporterns inbyggda retry-backoff, i en 300m-cgroup. Prec…

**Foreslagen atgard:**

> Byt fullmatch mot en söknings-/substitutionsvariant: om `_UNSUBSTITUTED_PLACEHOLDER.search(value)` träffar någonstans i strängen -> blanka hela värdet (eller substituera bort platshållaren) och logga en WARNING vid start med fältnamnet. Lägg ett test som matar in "#{X}/v1/traces" och "H=#{Y}" och kräver tom sträng.

**Skeptikerns granskning:**

Mekanismen stämmer, men prestandapåståendet gör det inte. VERIFIERAT: config.py:57 använder `_UNSUBSTITUTED_PLACEHOLDER.fullmatch(value.strip())`, OTEL-fälten ÄR deklarerade Settings-fält (config.py:180-190) så validatorn träffar dem, och k8s/flow.yml:191-196 har de tre inbäddade platshållarna. Jag körde regexen: '#{OPENTELEMETRY_URL}/v1/traces' och 'X-Seq-ApiKey=#{OPENTELEMETRY_TOKEN}' ÖVERLEVER, '#{GEMINI_API_BASE_URL}' blankas. Svepagenten har alltså inte hallucinerat. MEN kandidaten faller på fyra punkter: (1) KALL VÄG. Validatorn körs en gång vid Settings-instansiering (importtid) och configure_observability() en gång vid uppstart (observability.py:414-418, skyddad av _otel_configured). Ingen användare väntar, ingen datamängd skalar. "Het väg: ja" är fel. (2) KOSTNADEN ÄR ÖVERDRIVEN. BatchSpanProcessor/BatchLogRecordProcessor exporterar på en bakgrunds-daemontråd enligt schema — inte "per request" som påstås. Dessutom filtrerar _OtelLogFilter (observability.py:351-359) bort opentelemetry.*-poster, så den loggspam-återkopplingsloop kandidaten antyder kan inte uppstå. (3) VINSTEN ÄR VILLKORAD AV ETT FEL SOM INTE INTRÄFFAR, och det scenariot har REDAN en guardrail: samma commit som införde validatorn (15b8fd3) lade till tests/tools/test_gap_k8s_contracts.py:251-269, som assertar att varje #{VAR} i flow.yml finns i OCTOPUS_PROJECT_VARIABLES — och både OPENTELEMETRY_URL och OPENTELEMETRY_TOKEN står i allowlisten (rad 55-56). (4) MÖNSTRET FINNS INTE I KATALOGEN. wiki/prestanda-optimeringar.md har kategori A-E (DB/API-latens, CPU/minne, event-loop, transport, guardrails); "konfig-antagande" är ingen av dem. Kvarstår: fullmatch-vs-search-glappet är en äkta och billig härdning (kategori E, guardrails) — men den ska in i robusthetsbackloggen med ärlig etikett "ingen mätbar prestandavinst", inte i en prestandasvep där en före/efter-mätning per definition visar noll.

**Justerad vinst (granskarens, inte svepagentens):**

Ingen mätbar prestandavinst. Noll i normaldrift (platshållarna substitueras — OPENTELEMETRY_URL/TOKEN finns i Octopus-allowlisten). Även i det latenta felfallet är kostnaden en bakgrunds-daemontråd som misslyckas med OTLP-export mot en ogiltig URL — den blockerar inte requests. Restvärdet är robusthet/felklass-stängning, inte prestanda.

---

## #13 — Sankey Inbound: SSE-strömmen avbryts aldrig vid period-/datum-/bolagsbyte (parallella tunga byggen + race)

- **Plats:** `app/frontend/js/sankey_inbound.js:568-612`
- **Monster:** NYTT:saknad-avbrytning
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> loadSankeyInbound() skapar `const source = new EventSource('/api/sankey/inbound/stream?...')` i en LOKAL variabel — det finns ingen modulnivå-handle och ingen loadToken. Varje filterbyte som inte kan serveras lokalt (datum, period, bolag när client_filters saknar vyn) går via renderSankeyCurrentView() -> loadSankeyInbound() (sankey_inbound_state.js:265-275, anropas från sankey_inbound.js:681-729). Klickar användaren datum-pilen två gånger startas TVÅ SSE-strömmar mot samma podd; den första stängs aldrig. Sankey-byggaren är appens tyngsta jobb (den som OOM-dödade podden 2026-07-03) och appen kör 1 uvicorn-worker, så två parallella byggen konkurrerar om samma event-loop/minne. Dessutom finns ingen sekvensvakt: det svar som råkar bli klart SIST vinner och renderas — ett gammalt datum kan skriva över det nya. Jämför productivity_overview.js:553-564 som gör exakt rätt (modulnivå-handle + `++l…

**Foreslagen atgard:**

> Kopiera mönstret från productivity_overview.js: modulnivå-variabel `sankeyInboundEventSource` + `sankeyInboundLoadToken`. I loadSankeyInbound(): stäng ev. befintlig källa, öka token, och droppa alla onmessage/done-händelser vars token inte matchar. Ge även loadSankeyInboundFallback() samma token-vakt (den saknar också AbortController på api.get).

**Skeptikerns granskning:**

Koddelen stämmer: sankey_inbound.js:577 skapar `const source = new EventSource(...)` i en lokal variabel, det finns ingen modulnivå-handle och ingen loadToken, och renderSankeyCurrentView (sankey_inbound_state.js:265-275) kallar loadSankeyInbound() varje gång client_filters saknar vyn. Men den PÅSTÅDDA VINSTEN faller när man läser backenden. app/backend/routers/sankey.py:178-279: endpointen startar bygget i en `threading.Thread(target=worker, ..., daemon=True)` (rad 260) med egen SessionLocal, och SSE-generatorn (rad 262-269) bara läser ur en queue. Det finns INGEN request.is_disconnected()-koll, ingen cancel-flagga och inget avbrott i load_sankey_inbound_payload (grep på is_disconnected|cancel|threading.Event i sankey.py: 0 träffar). Att stänga EventSource i webbläsaren river alltså bara TCP-strömmen — worker-tråden kör vidare till done och gör hela det tunga bygget ändå. Föreslagen åtgärd (close + loadToken i frontend) tar därför bort NOLL server-CPU/minne: efter två snabba datumklick körs två byggen på podden oavsett. "Tar bort 1-2 parallella tunga rapportbyggen per snabbt filterbyte" är helt enkelt fel. Det som ÅTERSTÅR är (a) en äkta korrekthetsbugg — det svar som blir klart sist renderas, och t.ex. år→dag kan ge att det långsammare år-bygget skriver över dagvyn — och (b) marginella klientbesparingar (en färre öppen SSE-connection, ingen JSON.parse+render av en förbrukad payload). Det är en buggfix, inte en prestandaoptimering, och den hör hemma i en buggrapport snarare än i optimeringslistan. Vill man ha den påstådda server-vinsten krävs backend-arbete: en threading.Event som sätts vid klientdisconnect + avbrottskoll mellan källstegen i load_sankey_inbound_payload (större insats, medelrisk, och nyttan är oklar eftersom stegen är få och grova). Inget av detta är fixat: git log på sankey_inbound.js visar inget avbrytningsarbete, git log -S "sankeyInboundEventSource" ger 0 träffar, och wiki/prestanda-optimeringar.md D3 (rad 248-249) dokumenterar bara client_filters-återanvändningen.

**Justerad vinst (granskarens, inte svepagentens):**

Ingen server-prestandavinst (backend-tråden avbryts inte av att klienten stänger strömmen). Klientvinst: undviker sällsynt dubbelrendering av en stor payload — inte mätbar i api_benchmark. Kvarvarande värde är en korrekthetsfix (stale render), som bör hanteras som bugg, inte som optimering.

---

## #20 — Hämta data: resultattabellen renderar upp till 5000 rader som en enda innerHTML-sträng utan pagination

- **Plats:** `app/frontend/js/data_fetch.js:296-330`
- **Monster:** inget-tak
- **Het vag:** nej · **Insats:** M · **Risk:** medel

**Problem (svepagentens beskrivning):**

> renderDataFetchResult bygger `rows` genom att string-konkatenera <tr> för alla result.rows och sätter panel.innerHTML på hela panelen (inkl. thead + kalkylresultat). Backend tillåter max_rows upp till 5000 (data_fetch.py:71, default DATA_SOURCE_MAX_ROWS=1000) och frontend clampar också till 5000 (data_fetch.js:171-177). 5000 rader × 10-15 kolumner = 50-75k celler i en enda innerHTML-parse; ingen virtualisering, ingen pagination, ingen chunkad rendering. Backend har alltså ett tak, men DOM-sidan har inget skydd mot det taket.

**Foreslagen atgard:**

> Rendera bara de första ~200 raderna och lägg till "Visa fler"/enkel pagination (payloaden finns redan i minnet — ingen ny fetch), eller chunk:a inmatningen med requestAnimationFrame. Exporten (Excel) är redan den rätta vägen för hela datamängden.

**Skeptikerns granskning:**

Koden på platsen stämmer: `renderDataFetchResult` (data_fetch.js:306-310) string-konkatenerar en `<tr>` per rad och sätter `panel.innerHTML` på hela panelen (:312-329). Men kandidatens PREMISS är fel, och den pekar på fel lager.

1) "Backend tillåter max 5000" är osant i den faktiska anropsvägen. `dataFetchMaxRows()` (data_fetch.js:171-177) returnerar `null` när fältet är tomt — och `hamta-data.html:46` är `<input id="dataFetchMaxRows" type="number" min="1" max="5000" />` UTAN `value`, dvs. normalfallet är tomt → `max_rows: null`. Backend: `_max_rows(None)` returnerar `None` (data_fetch.py:189-190) och `project_rows` gör `limited = rows if max_rows is None else rows[:max_rows]` (app/backend/data_fetch/engine.py:135). Alltså skickas ALLA rader — inte 5000. Taket är i praktiken `DATA_SOURCE_RESPONSE_ROW_CAP=50000` (config.py:148) på API-vägen, och på arkiv-cache-vägen (`_fetch_rows` → `local_archive_store.query_rows`, data_fetch.py:344-351) finns inget tak alls. Svepagentens 5000 är alltså 10x för optimistiskt i ena riktningen och helt fel i andra.

2) Det verkliga problemet är REDAN dokumenterat på rätt lager. wiki/optimeringsplan.md:56 punkt 1.3: "Hamta data-exporten har INGET radtak. max_rows default None -> _max_rows(None) returnerar None -> clampningen mot DATA_SOURCE_MAX_ROWS hoppas helt over" med rotorsak `data_fetch.py:773` + `:189-193`. Punkt 1.2 täcker den obundna arkiv-cache-läsningen. Backend-fixen (clampa default till DATA_SOURCE_MAX_ROWS=1000) binder JSON-payloaden, sessionsfilen, Excel-arbetsboken OCH DOM:en på ett ställe. Frontend-pagination fixar bara det billigaste ledet och lämnar 50k-rads-JSON:en, `JSON.parse` i browsern, `_write_data_fetch_rows`-filskrivningen och RAM-spiken i podden (~1 Gi) helt orörda.

3) Efter 1.3 är kandidatens egen vinst borta. Vid default 1000 rader × ~10 kolumner = ~10k celler — en innerHTML-parse i storleksordning tiotals ms, inte "den sista onödiga sekunden". Kandidaten medger själv: "Vid default 1000 rader är vinsten liten."

4) Kall väg. Hämta data körs en gång per LLM-planerad fråga, en användare i taget, och väntetiden domineras av MiniMax-planeringen (`_call_minimax`, data_fetch.py:303) plus den fönstrade externa API-hämtningen (`fetch_all_rows`, :330-336) och ev. `package_breakdown`-aggregeringen. DOM-renderingen är svansen.

5) Åtgärden är inte beteendebevarande utan att det redovisats. Att bara rendera 200 rader tar bort användarens möjlighet att Ctrl+F i tabellen och att markera/kopiera hela resultatet från sidan. Svepagenten avfärdar det med "Exporten (Excel) är redan den rätta vägen" — men det är en beteendeförändring som inte är redovisad.

Notera också: "inget-tak" finns inte som mönster i wiki/prestanda-optimeringar.md; frontend-sektionen D (:237-249) handlar om transport (gzip/SWR/refetch), inte DOM-rendering. Etiketten är svepagentens egen.

**Justerad vinst (granskarens, inte svepagentens):**

ingen — som separat åtgärd. Vid det radantal som gäller efter den redan planerade backend-fixen (optimeringsplan 1.3, default 1000 rader) är innerHTML-parsen i storleksordning tiotals ms och osynlig bredvid MiniMax- och API-latensen. Vid dagens obundna läge (upp till 50k rader) är DOM:en det minsta problemet — servern OOM:ar eller bygger en 300-500 MB arbetsbok först. Rätt åtgärd är backend-clampen, inte frontend-pagination.

---

## #24 — Meta-vyns listor och Excel-export drar hela LLM-råsvaret (llm_raw_response) som aldrig används

- **Plats:** `app/backend/routers/meta_uploads.py:452-470 (lista) och 472-501 (export); serialiserare i meta_uploads_helpers.py:313-376`
- **Monster:** A3
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> `list_meta_shipment_observations` och `export_meta_shipment_observations` kör `db.query(MetaShipmentObservation)` som hela entiteter. `MetaShipmentObservation.llm_raw_response` är en `JsonField` som lagrar hela Gemini-svaret för videoanalysen (meta_analysis_service.py:728-737: `raw_response = _call_meta_analysis_provider(upload)` -> `observation.llm_raw_response = raw_response`). `_shipment_observation_out()` (meta_uploads_helpers.py:349-376) läser aldrig `llm_raw_response` — den plockar bara order/shipment/customer/pallet/deviations/status/video-metadata. Samma sak på uppladdningslistan: `list_meta_media_uploads` (rad 432-450) drar hela `MetaMediaUpload` inkl. `analysis: JsonField` som `_media_upload_out()` (helpers 313-330) heller aldrig rör. Listan hämtas med limit 200 vid varje sidladdning av Meta (`app/frontend/js/meta.js:480-495`, `skipCache: true`, båda listorna parallellt), och e…

**Foreslagen atgard:**

> `.options(defer(MetaShipmentObservation.llm_raw_response))` på lista + export, och `.options(defer(MetaMediaUpload.analysis))` på uppladdningslistan. Om detaljvyn någon gång behöver råsvaret hämtas det per rad. Beteendebevarande — inga fält i svaret ändras.

**Skeptikerns granskning:**

Kandidaten faller på två oberoende faktafel, plus en kall väg.

1) `llm_raw_response` är INTE "hela Gemini-svaret". `meta_analysis_service.py:728` sätter `raw_response = _call_meta_analysis_provider(upload)`, och den funktionen (rad 555-563) returnerar `_extract_json_candidate(response)` — inte HTTP-envelopen. `_extract_json_candidate` (rad 304-326) plockar ut `candidates[0].content.parts[*].text` och kör `json.loads` på den. Det som lagras är alltså enbart modellens JSON-utdata. Och prompten (rad 156-157) säger: "Returnera ett JSON-objekt med dessa falt: pallet_id, deviations, uncertainty_notes, confidence." Fyra fält. Ingen usage-metadata, inga safety-ratings, ingen transkription (prompten säger uttryckligen "Fyll aldrig order_number, shipment_number, username eller customer_name"). Kolumnen är i praktiken en dublett av `deviations` + `uncertainty_notes` som redan selekteras, plus en float. Storleksordning några hundra byte per rad — inte en blob. Wikins A3-signatur (`wiki/prestanda-optimeringar.md:106-113`) kräver "stora kolumner (t.ex. LargeBinary, hela CSV-/JSON-blobbar)"; referensexemplet är `CoreDataFile.data` på 9,5–15 MB. Ett 4-nyckels-dict är inte samma djur. "INTE mönstret om"-kriteriet "mängden är redan bunden/liten" slår till.

2) `MetaMediaUpload.analysis` (models.py:452) skrivs ALDRIG. Grep på `.analysis = ` / `analysis=` i `meta_uploads.py` och `meta_analysis_service.py` ger noll träffar; alla träffar på "analysis" i routern är `analysis_status`/`analysis_error`, som är egna kolumner. Kolumnen är en död, alltid-NULL-rest. `defer(MetaMediaUpload.analysis)` sparar exakt 0 byte. Halva den föreslagna åtgärden är ren no-op.

3) Vägen är kall. Båda endpoints är `require_super_user`. Meta-sidan laddas av en handfull superusers; exporten är ett manuellt knapptryck. Ingen bakgrundsjobb eller poll-loop anropar dem (`meta.js:479-494` kör bara vid sidladdning/refresh-klick).

Nettot om man ändå byggde defer på `llm_raw_response`: ~200 × ~0,3 kB = tiotals kB per sidladdning, ~3 MB i värsta export om 10 000 rader någonsin fanns. Det försvinner i brus mot att raden ändå bär `deviations`-JSON + `uncertainty_notes`-Text, och mot att openpyxl bygger arbetsboken i minnet. Åtgärden är billig och beteendebevarande, men vinsten är inte mätbar — det är städning, inte optimering. Notera också att `defer` på ett ORM-objekt som lever kvar i sessionen skulle ge lazy-load-risk om detaljvyn någon gång rör kolumnen; idag rör ingen den, men det är en extra fälla för noll vinst.

**Justerad vinst (granskarens, inte svepagentens):**

ingen (mätbart). `analysis`-delen är 0 byte (kolumnen är alltid NULL). `llm_raw_response`-delen är ~0,3 kB/rad → tiotals kB per sidladdning på en superuser-only, klick-driven väg. Under mätbrus.

---

## #25 — meta_shipment_observations saknar index på updated_at trots att det är enda sortkolumnen i listan och exporten

- **Plats:** `app/backend/models.py:456-463 (__table_args__) vs app/backend/routers/meta_uploads.py:465-467 och 490-493`
- **Monster:** A5
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> Både `list_meta_shipment_observations` och `export_meta_shipment_observations` sorterar `ORDER BY updated_at DESC, id DESC`, och listan filtrerar valfritt på `analysis_status`. Modellens `__table_args__` har bara `ix_..._status`, `ix_..._video_hash` och unika index på `record_hash`/`media_upload_id` — inget på `updated_at`. Kontrollerat mot migrationerna: `0025_meta_shipment_observations.py` skapar exakt de tre indexen, och de enda index-migrationerna som finns i repot är 0008 (schedule), 0040 (wait metrics) och 0048 (audit log). Tabellen växer med en rad per analyserad sändningsvideo, dvs monotont med användningen — samma skalprofil som `audit_log` hade före 0048. Utan index måste MSSQL sortera hela tabellen per anrop.

**Foreslagen atgard:**

> Alembic-migration som lägger `Index("ix_meta_shipment_observations_updated_at", "updated_at")` och `Index("ix_meta_shipment_observations_status_updated", "analysis_status", "updated_at")` (matchar WHERE + ORDER BY, precis som 0048 gjorde för audit_log). Lägg samma index i models.py __table_args__ så modell/migration-pariteten (guardrail i AGENTS.md) håller.

**Skeptikerns granskning:**

Faktabeskrivningen stämmer men slutsatsen gör det inte. Koden är som påstått: models.py:458-463 har bara status/video_hash/record_hash-index, och meta_uploads.py:464 respektive :491 sorterar `order_by(updated_at.desc(), id.desc())`. Migration 0025_meta_shipment_observations.py:65-72 skapar exakt de tre indexen, inget på updated_at. Så långt korrekt.

Men A5 i wiki/prestanda-optimeringar.md:124-136 kräver uttryckligen en **växande** tabell ("Skalforsakring: effekten vaxer med tabellstorleken"). Svepagentens bärande antagande — "tabellen växer monotont med användningen, samma skalprofil som audit_log" — är falskt. `meta_shipment_observations` har 30 dagars retention som raderar observationsraderna, inte bara mediabytena:
- app/backend/config.py:116 `META_MEDIA_RETENTION_DAYS: int = 30`
- app/backend/meta_analysis_service.py:842-857: purge:ar `MetaMediaUpload.created_at < cutoff` och gör för varje sådan rad `db.query(MetaShipmentObservation).filter(media_upload_id == row.id).delete(...)`
- app/backend/main.py:432-471: jobbet `meta_media_retention_purge` är registrerat i BACKGROUND_JOBS och körs vid varje uppstart (dvs. vid varje deploy/podd-omstart).
Tabellen är alltså hårt bunden till ~30 dagars manuella lotsvideor. Wiki/meta-upload.md:14-16 bekräftar retentionen som en levande mekanism (städmigrationen planeras efter 2026-08-10 just för att retentionen då hunnit rensa allt).

Dessutom är vägen kall: båda endpoints är `require_super_user`, listan anropas en gång vid sidladdning av meta.html (app/frontend/js/meta.js:487, `?limit=200`) — ingen polling, inga setInterval/setTimeout i meta.js. Exportens `limit=5000/10000` är teoretisk; tabellen kan i praktiken inte nå den storleken under 30 dagar. Kostnaden i exporten domineras av joinedload + Excel-skrivning (`_write_shipment_observations_excel`), inte av en top-N-sort över några hundra rader. Ingen ingång i tools/latency_budgets.json eller tools/api_benchmark.py — den är inte ens ansedd som en latensyta.

Kvarvarande halmstrå: rader vars video aldrig blir färdiganalyserad (status utanför `done_statuses`, meta_analysis_service.py:850-853) sparas från purge och kan i teorin ackumulera. Det är en fastnad kö som ska åtgärdas operativt, inte ett indexproblem. Ett index skulle kosta insert-overhead och en migration för en tabell som normalt håller sig i storleksordningen hundratals rader.

**Justerad vinst (granskarens, inte svepagentens):**

ingen (mätbart 0 på nuvarande och förväntad tabellstorlek — bunden av 30 dagars retention)

---

## #26 — POST /api/rfid/scans kör identisk "senaste stämpling"-query två gånger per scan

- **Plats:** `app/backend/routers/rfid.py:132-157, anropade från 218 och 228`
- **Monster:** A2
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> `receive_rfid_scan` anropar först `_is_consecutive_duplicate_scan(db, person, activity)` (rad 218), som kör `SELECT ... FROM rfid_scan_events WHERE person_id=? AND activity_id IS NOT NULL ORDER BY scan_time DESC, id DESC LIMIT 1`. Om det INTE är en dubblett anropas direkt därefter `_event_status_for(db, person, activity)` (rad 228), vars kropp (rad 149-154) kör exakt samma query igen och gör exakt samma jämförelse `latest.activity_id == activity.id` — som per konstruktion redan är känd som False, eftersom vi bara kommer hit när `_is_consecutive_duplicate_scan` returnerade False. Den andra rundresan kan alltså aldrig ändra utfallet. Det är dubbelarbete i en väg som körs en gång per fysisk brickstämpling.

**Foreslagen atgard:**

> Slå ihop till ett anrop: låt `_is_consecutive_duplicate_scan` returnera `latest` (eller låt `_event_status_for` ta emot den redan hämtade `latest` som argument) och återanvänd resultatet. STATUS_DUPLICATE_IGNORED-grenen i `_event_status_for` blir då död kod och kan tas bort — dubbletter fångas redan vid rad 218.

**Skeptikerns granskning:**

Faktapåståendet om koden stämmer, men vägen är kall och vinsten är brus. VERIFIERAT: rfid.py:135-140 (_is_consecutive_duplicate_scan) och rfid.py:149-154 (_event_status_for) har bokstavligt identiska query-kroppar (samma filter person_id + activity_id.isnot(None), samma order_by scan_time.desc()/id.desc(), samma .first()). Grep bekräftar att _event_status_for INTE har någon annan anropare än rad 228, och att dess STATUS_DUPLICATE_IGNORED-gren (rad 155-156) därmed är oåtkomlig — en rest från commit 86d1bd0 "Drop consecutive duplicate RFID scans" som lade till den tidiga returen på rad 218-227 utan att städa upp den gamla grenen. AVFÄRDAS ÄNDÅ, fyra skäl: (1) KALL VÄG. POST /api/rfid/scans anropas av två fysiska ESP32-moduler (MG Plock, MG VM) vid brickstämpling, med 3 s debounce i firmware (wiki/rfid.md:59-62). Storleksordning tiotal-hundratal POST per dygn, och ingen människa väntar på HTTP-svaret — ESP32 postar fire-and-forget. Wikins "INTE mönstret om"-kriterium om het väg vs. sällan-körd väg slår till. (2) QUERYN ÄR BILLIG. Den är index-täckt av ix_rfid_scan_events_person_scan_time (models.py:197) och är en TOP 1-seek, inte en scan. (3) SIFFRAN ÄR LÅNAD. "~37 ms" är dev-topologins generella rundresekostnad (prestanda-optimeringar.md:34-39), inte en mätning på denna endpoint. Även rakt av: 37 ms × ~100 scans/dygn ≈ 3,7 s/dygn totalt, spritt över en väg utan väntande användare. (4) FEL SAK ATT OPTIMERA I SAMMA FUNKTION. receive_rfid_scan gör redan två fulltabellsladdningar med Python-reduktion: _activity_for_module (rad 80: db.query(Activity).filter(Activity.is_active).all()) och _person_for_tag (rad 126: alla aktiva personer med rfid_code, jämförs i Python). De dominerar totalt över en LIMIT 1-seek. Mönsterklassificeringen A2 är dessutom fel — det finns ingen loop; det är närmast B3 (samma beräkning två gånger). Det som återstår är en ren kodstädning (ta bort dubbelqueryn + den döda grenen), S/låg risk, men det är hygien — inte en optimering. Statuskonstanten STATUS_DUPLICATE_IGNORED måste behållas: ignore_rfid_event (rad 325) och apply_rfid_event (rad 434) läser den för legacy-rader (bekräftat i tests/services/test_gap_rfid_conflicts.py:179, 312).

**Justerad vinst (granskarens, inte svepagentens):**

Ingen mätbar prestandavinst. En indexerad TOP 1-seek bort per RFID-scan på en väg som körs tiotal-hundratal ggr/dygn utan väntande användare. Kvarstår enbart som valfri dödkodstädning (S, låg risk) — inte som optimering.

---

## #30 — Meta-exportens radtak räcker — men kolumnbredds-passet blockerar framtida streaming

- **Plats:** `app/backend/routers/meta_uploads_helpers.py:428-443 (_write_shipment_observations_excel), tak i app/backend/routers/meta_uploads.py:474-497`
- **Monster:** B2
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> Detta är den svagaste av de tre exporterna wikin flaggar, och jag rapporterar den främst för att AVFÄRDA den som OOM-bov — taket håller.
> 
> Vägen är faktiskt bunden i båda ändar: `limit: int = Query(5000, ge=1, le=10000)` för ofiltrerad export, och _parse_export_ids kastar 400 vid >500 ids för filtrerad. 13 kolumner. Worst-case 10 000 × 13 = 130k celler ≈ 15-30 MB openpyxl + 10k ORM-objekt med joinedload(media_upload). Det är en storleksordning under Hämta data-exporten och långt från 1 Gi-taket.
> 
> Det enda som är värt att åtgärda är att `for column_cells in sheet.columns:` (auto-kolumnbredd) itererar över varje cell i hela arket en extra gång. Den är billig här, men den är exakt det som gör en write_only-migrering omöjlig (write_only-ark exponerar inte sheet.columns), så om man streamar de andra exporterna bör man droppa den samtidigt.

**Foreslagen atgard:**

> Lämna radtaket som det är — det är tillräckligt skydd. Om/när exporterna standardiseras på write_only: ersätt sheet.columns-passet med fasta kolumnbredder (headerlängd + en rimlig marginal) satta i förväg, så arket kan streamas. Ingen brådska; gör det som en följdändring till Hämta data-fixen, inte som ett eget arbete.

**Skeptikerns granskning:**

Koden är korrekt beskriven, men kandidaten är ingen optimeringspost — den avfärdar sig själv och jag bekräftar avfärdandet.

1) Taken finns och håller. meta_uploads.py:477 `limit: int = Query(5000, ge=1, le=10000)` och :490-494 `.order_by(...).limit(limit).all()` i else-grenen. Filtrerad gren: meta_uploads_helpers.py:461-462 `if len(result) > 500: raise HTTPException(400, "Du kan exportera max 500 filtrerade rader åt gången.")`. Datamängden är alltså hårt bunden i BÅDA grenarna. META_SHIPMENT_EXPORT_HEADERS är 13 kolumner (helpers:380-393). Worst case 10 000 x 13 = 130k celler.

2) Mönstermärkningen är fel. wiki/prestanda-optimeringar.md:161-170 definierar B2 som "en vy läser hela ett arkiv/en stor historik till minne per anrop utan cache" (exemplet: dblog-arkivet, 132 -> 449+ MB, OOM-dödade podden). Här läses en radbunden slice av EN tabell med `.limit()`. "INTE mönstret om"-kriteriet 'mängden är redan bunden/liten' slår till rakt av.

3) Vägen är kall. Endpointen är `require_super_user` (meta_uploads.py:479) och triggas bara av en manuell knapp i UI:t (app/frontend/js/meta.js:474 `api.download(...)`, dokumenterad som "Exportera alla"/"Exportera filtrerade" i wiki/meta-upload.md:50-51). Ingen bakgrundsjobb-anropare, ingen loop, ingen het väg. Användaren väntar visserligen, men på en handfull sekunder på en operation som körs sällan.

4) Det som "föreslås" är ingen åtgärd. Kandidatens egen slutsats är "Lämna radtaket som det är" och "Ingen brådska; gör det som en följdändring till Hämta data-fixen". `for column_cells in sheet.columns:` (helpers:435-437) itererar 130k celler i värsta fall — det är tiotals ms, försumbart mot `workbook.save()` på samma ark. Att byta till fasta kolumnbredder är dessutom INTE beteendebevarande: kolumnbredderna i den nedladdade filen ändras, vilket är en synlig UX-regression utan motsvarande vinst.

Kandidaten bör noteras i wikin som "undersökt, ej ett problem" — inte planeras som arbete.

**Justerad vinst (granskarens, inte svepagentens):**

ingen

---

## #35 — Sankey-payloadcachen är process-lokal utan L2 eller förvärmning — tom efter varje omstart

- **Plats:** `app/backend/sankey_inbound/cache.py:13-16`
- **Monster:** B2
- **Het vag:** nej · **Insats:** L · **Risk:** hög

**Problem (svepagentens beskrivning):**

> _CACHE är en ren in-process-dict med 15 min TTL i produktion och max 64 poster. Den överlever inte en processomstart. Trace-cachen fick uttryckligen ett tvåskiktat upplägg (L1 process + L2 gzip-JSON på disk) just för att drill-down skulle överleva processbyte (dokumenterat i wiki/prestanda-optimeringar.md, B2), men payloadcachen — som cachar det DYRA bygget, inte drill-downen — lämnades enskiktad. Efter varje deploy betalar första Sankey-användaren hela bygget: att endpointen har SSE-progress med stegräknare (routers/sankey.py:262-279) är i sig beviset på att bygget är långsamt nog att behöva progressindikator. Det finns inget förvärmningsjobb för Sankey motsvarande warm_today_for_businesses för produktiviteten (som redan körs direkt i schedulerns första varv, productivity_sync.py:918-981).

**Foreslagen atgard:**

> Antingen (a) lägg ett L2-lager på flow-media-PVC:n med samma mönster som trace-cachens gzip-JSON (nyckeln är redan en deterministisk tuple i _cache_key), eller (b) registrera ett BackgroundJob som efter uppstart bygger dagens/aktuell periods Sankey för aktiva bolag — staggrat, exakt som warm_today_for_businesses gör. (a) är bättre eftersom den även löser 15-min-TTL:ens vanliga cache-missar, inte bara kallstarten.

**Skeptikerns granskning:**

Koden stämmer i sak (cache.py:13-16 är en modul-dict, ingen disk), men premissen om vinsten håller inte.

1) TTL:n gör L2 nästan värdelös. `_CACHE_TTL_SECONDS = 15*60` (cache.py:14) och `_SOURCE_CACHE_TTL_SECONDS = 120` (cache.py:24). En L2 som respekterar samma TTL kan bara rädda poster som är yngre än 15 min vid omstartsögonblicket. Användaren betalar redan bygget om och om igen var 15:e minut i normal drift — kallstarten efter deploy är alltså inte en särskild kostnad utan en av många. Svepagentens påstående att L2 "även löser 15-min-TTL:ens vanliga cache-missar" är direkt fel: en disk-L2 med samma TTL löser inga TTL-missar. Att i stället förlänga TTL:n är en FÄRSKHETSÄNDRING (Sankey för idag ändras löpande när pallar tas emot/plockas) — alltså inte beteendebevarande, och det redovisas inte i kandidaten.

2) Det verkligt dyra är redan persistent. Enligt wiki/local-archive-cache.md ligger DuckDB-arkivcachen på flow-media-PVC:n sedan 2026-07-04 och "överlever poddomstarter" — det var just den som löste Sankeys OOM. Källhämtningen (fetch.py, det som SSE-stegen räknar: `total_steps = len(SANKEY_SOURCE_VIEWS) + 1`, routers/sankey.py:199) läser alltså redan från disk efter omstart. Kandidaten motiverar B2 med OOM-historiken, men den B2-fixen är redan gjord.

3) SSE-progress är inget bevis på att bygget är långsamt — stegen är per KÄLLA (`SANKEY_SOURCE_VIEWS`) plus ett enda "build"-steg (service.py:113, 145-151). Progressen finns för hämtningen, inte för bygget.

4) Nyckelkardinaliteten dödar förvärmning. `_cache_key` (cache.py:29-48) innehåller business_id, period, selected_date, company_filter, only_consumed, company_codes och tenant. Ett warm-jobb måste gissa exakt kombination; träffar den, är den ändå död efter 15 min. Vinsten finns alltså bara om en användare öppnar Sankey inom 15 min efter deploy — och kostnaden är att köra det tyngsta bygget i podden (300m CPU, 1 Gi, samma bygge som en gång OOM-dödade podden) samtidigt som uppstarten och `ARCHIVE_CACHE_SEED_ON_START`-passet. Om arkivseeden inte är klar faller bygget dessutom tillbaka på API/dblog = värsta minnesvägen. Jämförelsen med `warm_today_for_businesses` (productivity_prebuild.py:60) haltar: den värmer en förbyggd cache med signaturvakt, inte en 15-minuters TTL-dict.

5) Korrekthetsfälla i (a) som kandidaten missar: payloaden innehåller `trace_token` (service.py:190, `_attach_trace_token`). En payload som återuppstår från disk-L2 pekar på trace-rader vars disk-spill bara har `_TRACE_DISK_MAX_ITEMS = 8` och 30 min TTL (trace.py:37-39). Naiv L2 ger alltså 410 på drill-down = beteendeändring.

Dessutom täcks flera filterbyten redan klientsidigt av `client_filters`/`client_filters.views` (wiki/api.md:100), vilket sänker frekvensen av riktiga byggen ytterligare.

Kvarvarande, legitim men ANNAN kandidat: gör bygget billigare, eller inför längre TTL med explicit invalidering. Det är inte det kandidaten påstår.

**Justerad vinst (granskarens, inte svepagentens):**

ingen (som föreslagen). En L2 med bevarad 15-min-TTL sparar i praktiken bara de sekunder-till-minuter-gamla posterna som råkar finnas vid omstart; förvärmning ger vinst enbart i ett 15-minutersfönster efter deploy och bara om filterkombinationen gissas rätt.

---

## #38 — allocation_bridge exec:ar 7 källfiler (1815 rader) vid import — förbigår bytecode-cachen permanent, i både webb och desktop

- **Plats:** `app/backend/allocation_bridge.py:16-26`
- **Monster:** B3
- **Het vag:** nej · **Insats:** L · **Risk:** hög

**Problem (svepagentens beskrivning):**

> allocation_bridge.py är inte en vanlig modul: den läser sju filer ur allocation_bridge_parts/ som text och kör exec(compile(...)) på dem in i sin egen globals(). Eftersom compile() anropas manuellt på en sträng kan CPython aldrig cacha bytekoden för de filerna — de parsas och kompileras från källkod vid varje processtart, oavsett .pyc-inställningar (och överlever alltså inte ens en compileall-fix). Sammanlagt 1 815 rader. Modulen importeras ivrigt av både app/backend/main.py:14 (webben) och desktop/local_runtime.py:23 (desktopen), så kostnaden betalas i båda kallstarterna.

**Foreslagen atgard:**

> Gör de sju delarna till riktiga submoduler och importera dem normalt (`from .allocation_bridge_parts.registry import *` etc., eller explicita namn). Kräver att man reder ut det delade globals()-namnrymden mellan delarna — de skriver just nu in i samma dict, så vissa delar kan förlita sig på namn som en tidigare del definierat. Ett kontraktstest som jämför `dir(allocation_bridge)` före/efter bevisar att exporterna är oförändrade.

**Skeptikerns granskning:**

Mekanismen stämmer, men vinsten är noll och risken är felbedömd.

1) KODEN ÄR SOM PÅSTÅS. allocation_bridge.py:16-26 kör mycket riktigt exec(compile(path.read_text(), ...), globals(), globals()) i en loop över 7 filer. `wc -l` bekräftar 1 815 rader. Jag mätte compile() av de sju källorna lokalt (varm CPU): 12,3-15,9 ms. Svepagentens 18,4 ms egentid är alltså till största delen kompileringsarbete. Så långt håller påståendet.

2) MEN VINSTEN ÄR 0 MS IDAG — DETTA ÄR DÖDSSTÖTEN. Dockerfile:6 sätter PYTHONDONTWRITEBYTECODE=1, och det finns INGEN `compileall` någonstans i Dockerfile eller k8s/ (grep: noll träffar). Alltså existerar ingen .pyc-cache för NÅGON modul i produktionsimagen — hela kodbasen kompileras från källkod vid varje poddstart. allocation_bridge "förbigår" alltså inte en cache som finns; cachen finns inte. Att göra delarna till riktiga submoduler sparar exakt noll millisekunder tills kandidat 7 (compileall) landat först. Kandidaten erkänner detta i förbifarten ("den blockerar dessutom att compileall-fixen täcker den här koden") utan att inse att det reducerar dess EGET fristående värde till noll. Detta är en följdåtgärd till k7, inte en självständig optimering.

3) VÄGEN ÄR KALL. Även EFTER att compileall landat är vinsten ~13-16 ms wall (kanske 50-60 ms vid 300m CPU), EN gång per processtart. Den kallstarten domineras redan av pandas + duckdb + sqlalchemy + pyodbc-importer (hundratals ms till sekunder). Ingen användare väntar på detta — det är k8s-uppstart, inte en request-väg.

4) RISKEN ÄR "medel" I FILEN MEN ÄR I VERKLIGHETEN HÖG, OCH DEN FÖRESLAGNA BEVISNINGEN DUGER INTE. Sex av sju delar har NOLL import-satser (grep -c "^import|^from" ger 0 för alla utom registry.py som har 23). export.py:1-10 anropar os.startfile, sys.platform och subprocess.Popen helt utan importer — den förlitar sig på att registry.py injicerat dem i den delade globals(). AST-analys hittar 93 bekräftade korsreferenser mellan delarna (7-26 per fil) UTÖVER alla implicita stdlib-namn. Dessa binds SENT, vid anropstillfället. Därför skulle svepagentens föreslagna kontraktstest — jämför dir(allocation_bridge) före/efter — passera grönt medan ett missat namn ändå exploderar som NameError i någon sällan körd export-väg i produktion. Bevisningen bevisar alltså inte det den påstår.

Sammanfattning: en beteenderiskabel L-refaktorering av en 1 815-raders delad namnrymd, för 0 ms vinst idag och ~15 ms på en kall startväg sedan. Avfärdas. Om compileall (k7) någon gång landar och man ändå vill städa exec-hacket bör det motiveras som underhållbarhet/läsbarhet, inte som prestanda.

**Justerad vinst (granskarens, inte svepagentens):**

Ingen. 0 ms i nuvarande produktion (PYTHONDONTWRITEBYTECODE=1 + ingen compileall ⇒ ingen .pyc-cache finns att förbigå). Även villkorat på att kandidat 7 landar först blir vinsten ~13-16 ms wall (~50-60 ms vid 300m CPU) en gång per processtart, på en kallstart som redan domineras av pandas/duckdb/sqlalchemy-importer. Ingen användare väntar.

---

## #44 — data_fetch: _row_value bygger om hela case-insensitive header-mappen per rad

- **Plats:** `app/backend/data_fetch/core.py:421-426`
- **Monster:** B3
- **Het vag:** nej · **Insats:** S · **Risk:** låg

**Problem (svepagentens beskrivning):**

> `_row_value(row, column_id)` gör snabbvägen `if column_id in row: return row.get(column_id)`. Missas den bygger den `lower_map = {str(key).lower(): key for key in row}` — en full dict-comprehension över radens alla nycklar — **för varje rad och varje kolumn**. Kartan är identisk för alla rader i samma resultatmängd (samma vy → samma kolumnnamn). `_row_value` anropas i `project_rows` (engine.py:134-139) en gång per (rad × utkolumn), i `apply_local_filters` per (rad × filter), i `_metric_value` (två gånger per rad för min/max, engine.py:202-207) och i `execute_package_breakdown` per rad. Wikin anger att data_fetch aggregerar över upp till 50k rader.

**Foreslagen atgard:**

> Bygg header-mappen en gång per resultatmängd och skicka in den, eller memoisera på nyckeluppsättningen: `_lower_map = lru_cache`-cachad funktion på `frozenset(row)`/`tuple(row)`. OBS: den enklaste varianten (tuple(row.keys()) som cache-nyckel) är exakt den som mättes **långsammare** i produktivitetsbygget (wiki: 5,2 s → 8,8 s) — så gör inte det. Rätt fix här är att resolva kolumn-id → faktiskt radnyckel **en gång per anrop till project_rows/apply_local_filters/_metric_value** (kolumnlistan är känd i förväg) och sedan använda direkta dict-uppslag i radloopen.

**Skeptikerns granskning:**

Koden stämmer bokstavligt (core.py:421-426: fast path `if column_id in row`, annars `lower_map = {str(key).lower(): key for key in row}`), och anropsställena stämmer (engine.py:125, 137, 188, 196, 204-206, 244, 296-303, 359-365). Men kostnaden är HELT villkorad av att snabbvägen missar, och det finns starka bevis för att den inte gör det i praktiken:

1) Radernas nycklar kommer antingen (a) rått från API-svaret (external_data_client.py:231-251 returnerar `body["rows"]` orört) eller (b) från DuckDB-arkivet (local_archive_store.query_rows), vars tabellkolumner ÄR katalog-id:na. Katalogen (data/external_data_catalog.json, 426 vyer) använder API:ets egna snake_case-id:n (`item_num`, `book_num`, `qty`...). Snabbvägen träffar alltså.

2) Funktionellt motbevis: om miss-vägen sköt brett skulle `project_rows` (engine.py:137) returnera enbart None-värden och `apply_local_filters` (engine.py:120-131) filtrera bort ALLA rader (jfr `_local_filter_matches` med value=None). Hämta data fungerar i drift → miss-vägen kan per definition inte vara bred. Kvar blir bara enstaka kolumner som ibland saknas i raden, där None ändå är rätt svar.

3) Wikin (wiki/prestanda-optimeringar.md:197-202) dokumenterar explicit ett nära nog identiskt motförsök — cacha (kanonisk, verklig header) per kolumnuppsättning — som MÄTTES långsammare (5,2 s → 8,8 s för 3 bolag) och reverterades. Lärdomen där ("nästa lager är ofta call-overhead, inte beräkning") gäller även här: snabbvägen är redan en enda dict-hash.

4) Git: `git log -S "lower_map"` visar att fallbacken finns sedan ursprungscommiten a1b7b9a ("Add secure external data fetch"), dvs. defensiv från dag ett — inte tillagd som fix på en observerad kolumnmismatch. Inget test i tests/services/test_data_fetch_service.py asserterar case-okänslighet; alla testrader använder exakta katalog-id:n.

5) Även i det värsta realistiska scenariot (en enskild kolumn saknas i raderna) blir kostnaden ~50k dict-comprehensions över ~20-40 nycklar ≈ 0,1-0,2 s, inuti ett anrop som domineras av HTTP-hämtning + JSON-parse av upp till 50k rader (sekunder) och redan är avlastat till trådpool (routers/data_fetch.py:487-488). Det är brus, inte en optimeringsmöjlighet.

Kandidaten erkänner själv "Noll när API:ets kolumnnamn matchar katalogens exakt" — och det är precis vad som gäller. En latent, obevisad, ej mätbar kostnad är inte en optimeringskandidat. (Att hoista kolumn→nyckel-resolveringen ur radloopen vore ofarligt städ, men får inte säljas som prestandavinst.)

**Justerad vinst (granskarens, inte svepagentens):**

ingen (mätbar vinst kan inte påvisas; snabbvägen träffar i praktiken och kostnaden är noll då)

---

## #48 — Ingen orjson/ORJSONResponse — alla API-svar serialiseras med stdlib json (5x långsammare)

- **Plats:** `app/backend/main.py:114`
- **Monster:** NYTT:standard-json-serialisering
- **Het vag:** ja · **Insats:** M · **Risk:** medel

**Problem (svepagentens beskrivning):**

> `FastAPI(title="flow", version="0.1.5", lifespan=lifespan)` — ingen `default_response_class`. Alla routes går alltså via Starlettes JSONResponse → `json.dumps(..., ensure_ascii=False, allow_nan=False, separators=(",",":"))` i C-loopen. orjson/ujson finns inte i app/requirements.txt och nämns inte någonstans i koden (grep över hela repot: 0 träffar). Serialiseringen sker synkront på event-loopen i en enda worker. Endpoints som `/api/sankey/inbound`, `/api/productivity/overview`, `/api/schedule` (765 ms median i artifacts/api_benchmark/baslinje-20260707.json) och SSE:s `_sse_event` (json.dumps per event, sankey.py:174) betalar detta.

**Foreslagen atgard:**

> Lägg `orjson` i app/requirements.txt och sätt `FastAPI(..., default_response_class=ORJSONResponse)`. Semantiken är nära nog identisk: både json.dumps(allow_nan=False) och orjson höjer på NaN/Inf, och separatorerna matchar orjsons kompakta utdata. Två saker MÅSTE verifieras innan: (1) routes som returnerar numpy/pandas-skalärer (produktivitet, sankey) — orjson kräver `OPT_SERIALIZE_NUMPY` eller en `default=`-hook; (2) datetime-formatering (orjson skriver RFC 3339 direkt medan FastAPIs jsonable_encoder redan har konverterat på response_model-routes). Kör golden-karakterisering på sankey- och pro…

**Skeptikerns granskning:**

Faktapåståendena stämmer, men slutsatsen faller. Verifierat: main.py:114 `FastAPI(title="flow", version="0.1.5", lifespan=lifespan)` har inget default_response_class; app/requirements.txt saknar orjson/ujson; `git log -S "orjson"` och `-S "default_response_class"` över --all ger 0 träffar (inte redan fixat). Kandidaten faller ändå på tre punkter:

1) DEN DOMINERANDE KOSTNADEN PÅ SAMMA EVENT-LOOP ÄR INTE json.dumps, UTAN GZIP. main.py:319 har `app.add_middleware(GZipMiddleware, minimum_size=1024)`. Starlettes GZipMiddleware-signatur är `(app, minimum_size=500, compresslevel=9)` — koden överskriver inte compresslevel, så produktionen komprimerar på nivå 9. Mätt lokalt på en syntetisk sankey-liknande payload (533 KiB): json.dumps = 7,2 ms, gzip(level 9) = 40,5 ms. Gzip kostar alltså ~5,6x MER än serialiseringen, på exakt samma event-loop, i samma request. Svepagenten mikrobänkade dumps() isolerat och missade elefanten bredvid. Hela argumentet "varje sparad ms är tid andra requests inte köar" pekar, om man tar det på allvar, mot compresslevel — inte mot orjson.

2) VINSTEN DRUNKNAR I ENDPOINTENS EGEN LATENS. De 765 ms för /api/schedule i artifacts/api_benchmark/baslinje-20260707.json är mätta över HTTPS mot flow-development ("base_url": "https://flow-development.nowastelogistics.com") och innehåller nätverks-RTT, TLS och MSSQL-tid. orjson tar bort ~4/5 av 7,2 ms ≈ 5,8 ms, dvs under 1 % av endpointens median. Ingen mätning i kandidaten kopplar serialisering till de 765 ms.

3) FIXEN RÖR INTE ETT AV DE ÅBEROPADE STÄLLENA. Kandidaten anför SSE:s `_sse_event` (sankey.py:174: `f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"`) som evidens, men `default_response_class=ORJSONResponse` påverkar inte den raden alls — den anropar json.dumps direkt och skulle kräva separat ändring. Dessutom går de flesta routes via `response_model=` (activities.py:659, areas.py:105, auth.py:98, audit_logs.py:81 m.fl.), där pydantic-validering + jsonable_encoder körs FÖRE serialiseringen; ORJSONResponse tar inte bort det arbetet, bara det avslutande dumps-steget.

Kostnad/nytta går alltså åt fel håll: M insats + medel risk (ny C-extension, numpy-skalärer kräver OPT_SERIALIZE_NUMPY, datetime-semantik ändras) för <1 % latensvinst, medan en enrads-sänkning av gzip compresslevel ligger orörd bredvid med ~5x större effekt. Sidoiakttagelse värd en egen kandidat: `GZipMiddleware(..., compresslevel=6)` eller lägre — level 9 ger typiskt <5 % mindre payload än level 6 men kostar mångdubbelt mer CPU.

**Justerad vinst (granskarens, inte svepagentens):**

Ingen i praktiken. ~5,8 ms sparad CPU på de största payloads (>500 KiB), dvs <1 % av /api/schedule:s 765 ms median, och 0 ms på SSE-vägen som kandidaten själv åberopar. Den verkliga event-loop-kostnaden på samma väg — gzip level 9, ~40 ms på 533 KiB — lämnas orörd.

---

## #51 — Service workerns statiska cache har inget tak — gamla hash-URL:er rensas aldrig, den växer med varje deploy

- **Plats:** `app/frontend/sw.js:15-25`
- **Monster:** inget-tak
- **Het vag:** nej · **Insats:** S · **Risk:** medel

**Problem (svepagentens beskrivning):**

> `activate`-handlern rensar bara cachar vars NAMN inte är `flow-static-v1`. Inuti `flow-static-v1` läggs varje `?v=<hash>`-URL till permanent. Eftersom hashen byter vid varje innehållsändring får varje deploy en ny uppsättning URL:er — de gamla ligger kvar för alltid. Med ~30 JS-filer + styles.css per sida × N deployer växer cachen obundet. Ingen `cache.delete()` av inaktuella entries finns någonstans i filen. Webbläsaren evictar visserligen vid kvotbrist, men då slås HELA origin-cachen ut (inklusive de aktuella filerna), vilket ger en oväntad kall första laddning — precis motsatsen till vad SW:n är till för.

**Foreslagen atgard:**

> I `activate`: hämta cachens keys och radera entries vars URL inte finns bland de aktuella (t.ex. genom att SW:n vid install hämtar en liten manifest-fil med aktuella `?v=`-URL:er som bygget genererar, eller enklare: radera entries som är äldre än X dagar / begränsa till N poster med LRU). Alternativt: bumpa `STATIC_CACHE`-namnet vid varje deploy (byggt av samma innehålls-hash) — då rensar den befintliga activate-logiken automatiskt. Det sista är minst kod men slänger även oförändrade filer.

**Skeptikerns granskning:**

Koden är korrekt beskriven: sw.js:18-21 filtrerar enbart på cache-NAMN (`names.filter((name) => name !== STATIC_CACHE)`), och sw.js:42 gör `cache.put(request, response.clone())` utan någon eviction. Grep bekräftar att ingen annan frontend-kod rör `caches.` (endast sw.js:18, 20, 37). Mekanismen "inget tak" finns alltså formellt. Kandidaten faller ändå på tre punkter.

(1) Magnituden är fel med 1-2 storleksordningar. `tools/stamp_asset_versions.py:38-39` hashar PER FIL (`hashlib.sha256(file_path.read_bytes()).hexdigest()[:_HASH_LENGTH]`), och filens egen docstring rad 11-12 säger: "Innehålls-hash ... är deterministisk: oförändrade filer behåller sin hash mellan deployer". Alltså får endast de filer som FAKTISKT ÄNDRATS en ny `?v=`-URL vid ett deploy — inte "varje deploy en ny uppsättning URL:er" som kandidaten påstår. Hela frontend-korpusen är 2,0 MB över 92 js/css-filer (mätt); ett typiskt deploy rör en handfull filer, dvs tiotals KB nya entries, och bara för de filer användaren faktiskt laddar. Kandidatens "~1 MB per deploy-generation" är alltså en övre gräns som bara gäller om varje deploy skriver om halva kodbasen.

(2) Kvottaket nås aldrig i praktiken. Cache Storage delar origin-kvoten, som i Chromium-baserade webbläsare ligger i storleksordningen tiotals GB (andel av ledigt diskutrymme). Vid ~50 KB/deploy krävs storleksordningen 10^5-10^6 deployer. Även i det absurda värsta fallet (varje deploy skriver om alla 92 filer = 2 MB) krävs tusentals deployer på samma klientmaskin. Den påstådda skadan — kvotbrist → eviction av hela origin-cachen → kall laddning — är hypotetisk bortom systemets livstid. Kandidaten medger själv: "Ingen latensvinst i normalfallet".

(3) Den enklaste föreslagna åtgärden är ett DOKUMENTERAT ANTIMÖNSTER. Att bumpa `STATIC_CACHE`-namnet per deploy slänger cache-entries även för OFÖRÄNDRADE filer varje deploy och river därmed sönder exakt den vinst som den deterministiska innehålls-hashen är byggd för. `wiki/prestanda-leveranslager.md:102-103` under "Fallgropar" varnar ordagrant: "Bumpa `STATIC_CACHE`-namnet i `sw.js` bara vid avsiktligt cache-byte; gamla cachar rensas i activate." Manifest-alternativet kräver ett nytt byggsteg (manifest-generering i Dockerfile) + en extra fetch i SW:ns install-handler — reell komplexitet och en ny felkälla i leveranslagret, för noll mätbar vinst.

Mot mönsterkatalogens "INTE mönstret om"-kriterier: vägen är kall (SW-cachen växer på klienten, ingen användare väntar, ingen serverkostnad), mängden är i praktiken bunden (deterministisk per-fil-hash + 2 MB korpus + GB-kvot), och det finns ingen latensvinst att mäta. Nuvarande design är dessutom ett medvetet, dokumenterat val (git 1793f32, "Leveransoptimering ... service worker") — inte ett förbiseende. Notera också att webbläsarens vanliga HTTP-cache redan håller samma filer med `max-age=31536000, immutable` och har sin egen inbyggda eviction; SW-cachen är en andra kopia, inte ensam skyddslinje.

Rekommendation: låt ligga. Om någon ändå vill härda detta är den enda beteendebevarande varianten en LRU/åldersgräns inuti `flow-static-v1` — men det är hygien, inte prestandaoptimering, och hör inte hemma i en latensjakt.

**Justerad vinst (granskarens, inte svepagentens):**

ingen

---

# OMVARLDSTEKNIKER (49)

Avvagda mot Flows faktiska arkitektur (1 uvicorn-worker, 1 Gi-podd, 300m CPU, MSSQL,
vanilla JS utan byggsteg, MPA). Klassade som tillamplig / delvis / avfardad.

## TILLAMPLIGA (35)

Passar Flow. Verifierade mot repot.

### DuckDB som beräkningsmotor (inte bara lagring) – push filter/aggregering till SQL

- **Lager:** ? · **Insats:** M · **Risk:** medel

**Vad tekniken ar:** Teamen som kör tunga tabelljobb i en process (utan Spark/Postgres) använder i växande grad DuckDB som *compute*: vektoriserad, kolumnär, multi-core exekvering in-process, utan serverhopp, och den kan köra SQL direkt mot befintliga DataFrames/Arrow-tabeller. Typiska rapporter: 2,5x på single-key group-by och stora vinster på filter-tunga läsningar jämfört med pandas, och ännu större mot rena Python-loopar.

**Passar Flow?** Flow HAR DuckDB (duckdb>=1.5.4, ARCHIVE_CACHE_ENABLED=1 även i k8s) men använder den bara som rad-lager. `local_archive_store.query_rows` gör `SELECT * FROM <vy> WHERE _row_date BETWEEN ? AND ?`, `fetchall()`, bygger en dict per rad och skickar sedan alltihop till `apply_local_filters` i Python. Bolagsfilter, textoperatorer och exakta datumgränser körs alltså i Python på material som redan ligger i en kolumnär motor. Samma sak i `data_fetch/engine.execute_calculation`: group-by görs med en Python-dict över upp till 50k rader (kommentar i data_fetch.py:485 medger 'CPU-bunden O(N)-aggregering'). Detta är den enskilt mest konkreta möjligheten – ingen ny dependency, inget byggsteg, ingen extra p…

**Var i Flow:** app/backend/local_archive_store.py:587-651 (query_rows/query_snapshot_rows – översätt apply_local_filters-operatorerna till WHERE + kolumnprojektion, och byt fetchall()+dict-comprehension mot .arrow()/fetch_record_batch när bara aggregat behövs); app/backend/sankey_inbound/fetch.py:196-211 (_query_l…

**Vinst:** Minne först och främst: Sankeys månads-/årsvyer materialiserar idag hela arkivet som list[dict] (≈10x rådatans storlek) i en podd med 1 Gi-tak – wiki/local-archive-cache.md säger rakt ut att det OOM-dödade podden. Aggregat i SQL returnerar hundratals rader i stället för miljoner. Tid: 2-5x på group-…

**Kallor:** https://www.sqlservercentral.com/blogs/stop-using-pandas-for-aggregations-try-duckdb-instead · https://duckdb.org/docs/current/guides/performance/environment · https://www.digitalocean.com/community/tutorials/duckdb-complements-pandas-for-large-scale-analytics


### DuckDB-konfiguration i container: threads + memory_limit vid connect()

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** Känd fallgrop hos alla som kör DuckDB i k8s: DuckDB sätter default memory_limit till ~80 % av *värdens* RAM (inte poddens) och threads till värdens kärnor, och har haft buggar med att läsa cgroup v2-gränser. DuckDB kräver dessutom minst ~125 MB per tråd. DuckDB:s egen guide rekommenderar att sänka thread-antalet före memory_limit i minnesknappa miljöer, och att sätta memory_limit till 50-60 % av tillgängligt minne om OOM-killern slår till.

**Passar Flow?** Direkt tillämplig och ett latent produktionsproblem. `local_archive_store._connect` (rad 187-194) anropar `duckdb.connect(str(path), read_only=read_only)` helt utan config. Podden har `limits: cpu 300m / memory 1Gi` (k8s/flow.yml, k8s/deployment.yaml) men DuckDB ser nodens kärnor och nodens RAM. På en 8-kärnig nod startar den 8 trådar (≈1 GB minimibehov ur en 1 Gi-podd, på 0,3 CPU) och tror att den får använda 80 % av nodens minne.

**Var i Flow:** app/backend/local_archive_store.py:187-194 (_connect) – `duckdb.connect(path, read_only=..., config={'threads': 1, 'memory_limit': '256MB', 'temp_directory': <PVC-sökväg>})`, gärna styrt av settings så desktop/lokalt får högre tak.

**Vinst:** Tar bort en trolig OOM-/CPU-svältkälla i produktion (seeden kör dessutom 5 parallella trådar, ARCHIVE_CACHE_SEED_WORKERS=5). Nästan gratis: några rader kod.

**Kallor:** https://duckdb.org/docs/current/guides/performance/environment · https://duckdb.org/docs/current/guides/performance/oom · https://github.com/duckdb/duckdb/issues/14966


### Parquet (ZSTD) i stället för gzip-TSV för produktivitets-snapshots

- **Lager:** ? · **Insats:** L · **Risk:** medel

**Vad tekniken ar:** Standardvalet i moderna Python-pipelines: kolumnär fil med min/max-statistik per row group ⇒ kolumnprojektion och predicate pushdown. Gzippad CSV är typiskt 2-3x större än motsvarande Parquet och kan inte frågas alls utan full dekomprimering – DuckDB stödjer filter pushdown i Parquet-läsaren men *inte* i CSV-läsaren (projection pushdown funkar i båda).

**Passar Flow?** Passar Flows snapshotlayout perfekt: en katalog per dag med 8 filer (`productivity_snapshots/<datum>/<key>.csv.gz`, skrivna som TAB-separerad CSV i gzip, productivity_sync_paths.py:137-146). Sankeys årsvy läser idag 365 dagar × en fil via `_read_csv_rows_with_headers(..., compressed=True)` och konkatenerar allt till list[dict] i RAM (sankey_inbound/fetch.py:246-254); person-cachen läser alla 8 källor per dag (person_productivity_cache.py:602-609). Med Parquet blir det ETT anrop: `read_parquet('productivity_snapshots/*/pick.parquet')` med bara de kolumner som faktiskt används. Katalogen är dessutom redan hive-liknande (datum som katalognamn) → `hive_partitioning=true` ger datumfilter gratis. …

**Var i Flow:** app/backend/productivity_sync_paths.py:96-146 (skrivvägen `_gzip_csv_rows`/`_gzip_csv_copy` + productivity_snapshot_source_path) och läsvägarna i app/backend/sankey_inbound/fetch.py:246, app/backend/person_productivity_cache.py:602, app/backend/productivity_kpi_rules/scoring.py:78. Mellansteg med no…

**Vinst:** Disk: 2-3x mindre (PVC:n är 10Gi). Läsning av årsvyer: kolumnprojektion tar bort de ~40 kolumner Sankey inte använder, och Arrow-typer i stället för dict-per-rad tar bort den 5-10x Python-objektoverheaden. Det är samma OOM-yta som drev fram arkiv-cachen.

**Kallor:** https://duckdb.org/2024/12/05/csv-files-dethroning-parquet-or-not · https://motherduck.com/learn/why-choose-parquet-table-file-format/ · https://duckdb.org/docs/current/data/partitioning/hive_partitioning


### Streamad Excel-export: openpyxl write_only / xlsxwriter constant_memory

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** Båda biblioteken har ett läge som håller minnet konstant: openpyxl `Workbook(write_only=True)` håller sig under ~10 MB oavsett datamängd, xlsxwriter `{'constant_memory': True}` spolar ut varje rad så bara en rad hålls i minnet. Rapporterade fall: 200k rader × 52 kolumner från 9 min (openpyxl default) till 3 min. Baksidan av constant_memory: inga efterhandsändringar av celler, add_table() funkar inte, merge_range/set_row bara på aktuell rad.

**Passar Flow?** Flow använder openpyxl i *default*-läge överallt – hela arket byggs som Python-objekt i minnet innan save(), i en podd med 1 Gi-tak. Kritiska ställen är de exporter som kan bli stora: Hämta data (upp till 50k rader × alla kolumner) och Meta-sändningsanalysen. Importmallarna (persons/users/activities) är små och kan lämnas som de är. xlsxwriter finns inte i app/requirements.txt (bara openpyxl==3.1.5) – därför är openpyxl write_only=True nollkostnadsvalet: samma dependency, samma `sheet.append(...)`-API, ingen ny bygg- eller paketeringsrisk för PyQt-desktopens flow.spec.

**Var i Flow:** app/backend/routers/data_fetch.py:497-523 (_write_excel – Workbook() → Workbook(write_only=True), skapa arken med create_sheet och append rad för rad); app/backend/routers/meta_uploads_helpers.py:429; app/backend/allocation_bridge_parts/export.py:45-59 (både openpyxl-grenen och pd.ExcelWriter-grenen…

**Vinst:** Konstant minne i stället för O(rader) i den podd som redan OOM-riskerar; snabbare export. Om ni vill åt hastigheten också: lägg till xlsxwriter och byt prioritet i excel_writer_engine() – men openpyxl write_only är det riskfria första steget.

**Kallor:** https://openpyxl.readthedocs.io/en/3.1/optimized.html · https://openpyxl.readthedocs.io/en/3.1/performance.html · https://xlsxwriter.readthedocs.io/working_with_memory.html


### Arrow-transport i stället för list[dict] mellan DuckDB och Python

- **Lager:** ? · **Insats:** M · **Risk:** låg

**Vad tekniken ar:** DuckDB:s Python-API kan lämna resultat som Arrow (`.arrow()`, `.fetch_record_batch()`) i stället för Python-tupler. En dict per rad med str-nycklar kostar typiskt 5-10x rådatans storlek i CPython (varje dict ≈ 200+ bytes plus str-objekt per cell); Arrow-buffertar är kolumnära och nästan overheadfria, och pandas 3/pyarrow kan konsumera dem utan kopiering.

**Passar Flow?** Tillämplig i cache-läsvägen och i bulk-inserten. `query_rows` bygger `{name: value for ...}` för varje rad i resultatet (local_archive_store.py:622-626) och `_bulk_insert` går via en pandas-DataFrame av Python-listor (rad 247-261) – båda kan gå via Arrow. Kräver dock att konsumenterna (apply_local_filters, sankey_inbound/rows._row_value) fortfarande vill ha dictar – därför lönar sig detta bäst tillsammans med punkt 1 (aggregera i SQL så att bara små resultat behöver bli Python-objekt). Som isolerad åtgärd: begränsad vinst, eftersom raderna ändå ska bli dictar i slutänden.

**Var i Flow:** app/backend/local_archive_store.py:247-261 (_bulk_insert) och 603-628 (query_rows)

**Vinst:** Minne i seed-/läsvägen; störst effekt i kombination med SQL-aggregering. Ensamt: marginellt.

**Kallor:** https://duckdb.org/docs/stable/data/csv/overview.md · https://pandas.pydata.org/docs/user_guide/pyarrow.html


### startupProbe i stället för initialDelaySeconds (kortar deploy-gapet)

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** K8s startupProbe kör tätt (t.ex. periodSeconds: 2) tills appen svarar första gången, och lämnar sedan över till liveness/readiness. K8s egen dokumentation rekommenderar det explicit för appar med variabel starttid, i stället för en stor initialDelaySeconds. Poängen: readiness/liveness slipper vänta ut en fast delay, podden blir Ready i samma sekund som porten svarar.

**Passar Flow?** Passar direkt. k8s/flow.yml rad 219-236 har INGEN startupProbe utan `livenessProbe.initialDelaySeconds: 30` och `readinessProbe.initialDelaySeconds: 15`. Med `strategy: Recreate` (rad 16) är hela deploy-nedtiden = gamla poddens död + nya poddens starttid, och de 15 sekunderna i readiness läggs ovanpå den faktiska starttiden ÄVEN om appen är uppe på 6 s. DEPLOY.md avsnitt 6 säger 5-15 s startup, men den siffran är från Render-tiden och gäller inte längre: main.py lifespan kör nu `_run_startup_migrations()` (alembic upgrade head mot Azure SQL) FÖRE uvicorn tar emot trafik, och CMD kör dessutom `python -m backend.prestart` innan uvicorn ens startar. Starttiden är alltså variabel — precis fallet…

**Var i Flow:** k8s/flow.yml rad 219-236 (probe-blocket). Ingen kodändring i appen.

**Vinst:** Kortare deploy-nedtid (Recreate-gapet minskar med ~10-15 s i typfallet) och bort med gissad initialDelaySeconds. Bevarar samtidigt skyddet mot att kubelet dödar en långsamt startande podd.

**Kallor:** https://kubernetes.io/docs/concepts/workloads/pods/probes/ · https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/ · https://oneuptime.com/blog/post/2026-02-09-startup-probes-slow-starting/view


### preStop-hook + terminationGracePeriodSeconds + uvicorn graceful shutdown

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** Standardmönstret mot 502/503 vid poddbyte: SIGTERM och borttagning ur Endpoints sker parallellt i k8s, så ingress-nginx kan hinna skicka requests till en podd som redan stänger. En `preStop: exec sleep 5-10` gör att podden markeras Terminating och plockas ur upstream INNAN SIGTERM går in, och pågående requests får avslutas.

**Passar Flow?** Passar direkt och saknas helt. Grep över hela k8s/ + Dockerfile ger noll träffar på `preStop`, `terminationGracePeriodSeconds` eller SIGTERM-hantering. wiki/rfid.md rad 114 dokumenterar exakt symptomet: "network_error/HTTP 0 i Historik precis efter en Octopus-deploy" och avfärdar det som förväntat. Det är delvis onödigt — en del av de felen är requests som dödades mitt i, inte gapet. Två åtgärder: (1) `terminationGracePeriodSeconds: 30` + `preStop: ["sh","-c","sleep 8"]` i k8s/flow.yml, (2) uvicorn `--timeout-graceful-shutdown 20` i Dockerfile CMD (rad 54). Notera att tini redan är entrypoint (rad 53), så SIGTERM propageras korrekt till uvicorn — halva jobbet är gjort.

**Var i Flow:** k8s/flow.yml containers-blocket (efter rad 74), samt Dockerfile rad 54 (`exec uvicorn ... --timeout-graceful-shutdown 20`).

**Vinst:** Slipper avbrutna requests vid varje deploy och vid varje node-drain. Gör Historik/Hälsa-datat ärligare (mindre brus av network_error kring deploys).

**Kallor:** https://blog.sebastian-daschner.com/entries/zero-downtime-updates-kubernetes · https://medium.com/codecademy-engineering/kubernetes-nginx-and-zero-downtime-in-production-2c910c6a5ed8 · https://github.com/kubernetes/ingress-nginx/issues/6928


### DuckDB:s single-writer-fillås är den faktiska blockeraren för --workers 2 (inte trace-cachen)

- **Lager:** ? · **Insats:** L · **Risk:** medel

**Vad tekniken ar:** DuckDB tillåter en enda read-write-process per databasfil; andra processer får låsfel. Team som kör DuckDB som läscache i flerprocessmiljö löser det med "en skrivare, atomisk filbytesnapshot, alla läsare read_only" — skriv till en temporär fil och `os.replace()` in den, läsarna öppnar alltid read_only.

**Passar Flow?** Kritiskt fynd. DEPLOY.md rad 293-299 påstår att sankeys `_TRACE_CACHE` var den enda blockeraren för fler workers, och att disk-spillet (app/backend/sankey_inbound/trace.py rad 61-89) därmed löst det. Det stämmer inte längre. app/backend/local_archive_store.py rad 50-79 och 187-194: DuckDB-arkivcachen (`/var/flow-media/archive_cache`, aktiv i drift via ARCHIVE_CACHE_ENABLED=1, flow.yml rad 152) serialiserar all filåtkomst med ett PROCESSLOKALT `threading.RLock` (`_LOCKS`, rad 53). Det låset skyddar inte mot en andra worker-process. `_connection(..., read_only=False)` anropas på 6 ställen (rad 287, 327, 361, 481, 558). Med `--workers 2` skulle worker B:s read_only-läsning krocka med worker A:s…

**Var i Flow:** app/backend/local_archive_store.py rad 50-79 + 187-194 (låset och _connect). DEPLOY.md rad 293-299 (felaktig text som bör rättas). app/backend/leader_lock.py (mönstret att återanvända).

**Vinst:** Undanröjer en tyst korruptions-/kraschrisk som annars slår till första gången någon höjer --workers. Är förutsättningen för både fler workers OCH för RollingUpdate med överlappande poddar.

**Kallor:** https://duckdb.org/docs/stable/connect/concurrency.html · https://archmonger.github.io/ServeStatic/latest/


### gunicorn --preload med UvicornWorker i stället för uvicorn --workers (om ni någonsin går till 2)

- **Lager:** ? · **Insats:** M · **Risk:** medel

**Vad tekniken ar:** uvicorn:s `--workers` använder multiprocessing SPAWN (medvetet, för Windows-kompatibilitet) — varje worker importerar hela appen från noll, ingen copy-on-write-delning. gunicorn med `--preload` forkar EFTER import, så alla forkade workers delar de importerade sidorna via COW. Skillnaden är stor för appar med tunga import-grafer (pandas/numpy/ML).

**Passar Flow?** Relevant men villkorat. app/requirements.txt drar in pandas 3.0.3, numpy, pyarrow, duckdb, xgboost-cpu 3.3.0 OCH lightgbm 4.6.0 — en fet importgraf. wiki/meta-upload.md rad 116 dokumenterar att appen ligger på ~150-190 MB RSS och att containern OOM-dödades vid ~1 Gi när ffmpeg toppade ~254 MB. Med spawn-baserade `uvicorn --workers 2` betalar ni ~150-190 MB EN GÅNG TILL, utan COW — det äter upp precis den marginal som redan OOM-dödade er. gunicorn --preload med UvicornWorker delar de sidorna. MEN: notera att FastAPIs egen deployment-dok uttryckligen säger "när du kör på Kubernetes vill du troligen INTE använda workers, utan en uvicorn-process per container" — och att gunicorn --preload gör ba…

**Var i Flow:** Dockerfile rad 54 (CMD), app/requirements.txt (skulle behöva gunicorn). DEPLOY.md rad 287-299.

**Vinst:** Om worker 2 blir nödvändig: ~150-190 MB sparat minne jämfört med uvicorn --workers 2, dvs skillnaden mellan att rymmas och att OOM:a i 1 Gi.

**Kallor:** https://fastapi.tiangolo.com/deployment/server-workers/ · https://github.com/Kludex/uvicorn/discussions/2463 · https://www.uvicorn.org/deployment/


### Ta bort (eller höj kraftigt) CPU-limit 300m — CFS-throttling

- **Lager:** ? · **Insats:** S · **Risk:** medel

**Vad tekniken ar:** CPU-limits i k8s implementeras som CFS-kvot: 300m = 30 ms CPU per 100 ms-fönster. När kvoten är slut throttlas cgroupen till nästa fönster. Latensskadan är proportionell mot ANTALET fönster som slår i taket, inte mot total CPU-tid — en podd kan vara 99 % idle och ändå throttla en tredjedel av requesten. Rådet (Tim Hockin, Robusta, Numerator m.fl.): sätt CPU-*requests* korrekt, ta bort CPU-*limits* för latenskänsliga tjänster.

**Passar Flow?** Passar, och ni har redan bevis i repot. k8s/flow.yml rad 216-218 sätter `limits.cpu: "300m"` (hårdkodat, inte ens en Octopus-variabel som memory). Kommentaren rad 225-228 säger rakt ut: "Default (1s) är för snålt med CPU-limit 300m: en ffmpeg-körning CFS-stryper hela cgroupen och en tillfälligt långsam proba får annars kubelet att döda podden" — ni har alltså redan höjt `timeoutSeconds` till 5 för att KOMPENSERA för throttlingen i stället för att ta bort orsaken. Samma sak i flow.yml rad 135-143 (kill-switch motiveras delvis med "CPU-limiten 300m gör dev-podden instabil"). Realistiskt i NoWaste-klustret: en LimitRange kan tvinga fram en limit — då är höjning till 1000-1500m (DEPLOY.md avsnit…

**Var i Flow:** k8s/flow.yml rad 212-218 (containerns resources) samt rad 52-58 (initContainerns).

**Vinst:** Bort med throttling-inducerad p95-latens vid pandas-/ffmpeg-/DuckDB-tunga anrop. Låter er sänka probe-timeouts igen och gör Väntetider-mätningen ärlig. Nollkostnad i pengar — requests, inte limits, styr schemaläggning och nodkostnad.

**Kallor:** https://home.robusta.dev/blog/stop-using-cpu-limits · https://www.numeratorengineering.com/requests-are-all-you-need-cpu-limits-and-throttling-in-kubernetes/ · https://erickhun.com/posts/kubernetes-faster-services-no-cpu-limits/


### Förkomprimerad Brotli vid Docker-build + ServeStatic/PreCompressedStaticFiles (i stället för ingress-brotli)

- **Lager:** ? · **Insats:** M · **Risk:** låg

**Vad tekniken ar:** ServeStatic är en ASGI-fork av WhiteNoise som serverar förkomprimerade `.br`/`.gz`-filer bredvid originalen, med korrekt Accept-Encoding-förhandling och Vary-header; komprimeringen görs en gång vid build via dess CLI, inte per request. `starlette-precompressed-static` gör samma sak minimalt. Brotli ger typiskt 15-30 % mindre än gzip på JS/CSS.

**Passar Flow?** Passar Flows mönster nästan exakt — och är BÄTTRE än ingress-brotli av två skäl. (1) `enable-brotli` är en GLOBAL ConfigMap på själva ingress-nginx-controllern, delad av alla NoWaste-appar; ni deployar bara era egna manifest via Octopus i namespacet prod-common och äger inte den ConfigMapen. (2) Även om klusterteamet slog på den skulle den inte göra något: app/backend/main.py rad 319 lägger `GZipMiddleware` ytterst, så ingressen får redan `Content-Encoding: gzip` från upstream och komprimerar inte om. Ingress-brotli skulle alltså kräva att ni STÄNGER AV er egen gzip — sämre affär. Förkomprimering vid build passar däremot in i ett mönster ni redan har: Dockerfile rad 42-43 kör redan `python -…

**Var i Flow:** Dockerfile rad 42-43 (nytt komprimeringssteg), app/backend/main.py rad 510-512 (StaticFiles-mounten) samt rad 316-319 (GZipMiddleware kan behållas för API-JSON).

**Vinst:** 15-30 % mindre JS/CSS-overföring än dagens gzip, plus lägre CPU per statisk request (förkomprimerat, inte on-the-fly). Träffar även PyQt-desktopen som laddar samma frontend och den publika uppladdningssidan.

**Kallor:** https://pypi.org/project/servestatic/ · https://archmonger.github.io/ServeStatic/latest/ · https://pypi.org/project/starlette-precompressed-static/


### VPA i recommendation-only mode (updateMode: Off) för rätt-dimensionering av JOB_MEMORY/JOB_MEMORY_MAX

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** Vertical Pod Autoscaler i `updateMode: Off` startar aldrig om något — den observerar faktisk användning i en vecka och skriver rekommenderade requests/limits till VPA-objektets status. Standardarbetsflödet är: deploya VPA i Off, låt den samla data 1 vecka, läs `kubectl describe vpa`, applicera manuellt.

**Passar Flow?** Passar, MEN kräver att VPA-CRD:erna finns i NoWaste-klustret — det äger inte ni, så det är en fråga till klusterteamet, inte en PR. Behovet är reellt och dokumenterat: k8s/flow.yml sätter memory via Octopus-variablerna `#{JOB_MEMORY}` / `#{JOB_MEMORY_MAX}` (rad 214-218) — värdena syns alltså inte ens i repot, och wiki/meta-upload.md rad 116 avslutar med "överväg höjd JOB_MEMORY_MAX i Octopus", dvs ni gissar idag. VPA i Off-läge ger er siffran i stället. Om VPA inte finns i klustret: fråga efter `container_memory_working_set_bytes` från deras befintliga metrics-stack — ni har redan OTEL mot Seq (flow.yml rad 187-206) men det är traces/logs, inte container-metrics. Relaterat, för framtiden: In…

**Var i Flow:** k8s/flow.yml rad 212-218 (resources) + Octopus-variablerna JOB_MEMORY/JOB_MEMORY_MAX. Nytt VPA-manifest i k8s/ om klustret stödjer det.

**Vinst:** Slutar gissa minnesgränsen efter OOM-incidenter. Rätt request = bättre schemaläggning; rätt limit = färre OOM-kills av typen 2026-07-09 (ffmpeg + app > 1 Gi).

**Kallor:** https://kubernetes.io/docs/concepts/workloads/autoscaling/vertical-pod-autoscale/ · https://oneuptime.com/blog/post/2026-02-09-vpa-recommendation-mode-sizing/view · https://kubernetes.io/blog/2025/12/19/kubernetes-v1-35-in-place-pod-resize-ga/


### Strukturerad output med responseSchema (constrained decoding) i stället för response_mime_type + fritextparsning

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** Gemini generateContent tar generationConfig.responseSchema (JSON Schema). Modellen tvingas dekoda till schemat: garanterade fältnamn, garanterade typer, required-fält. Team som gör extraktion i produktion använder detta i stället för att JSON-parsa fritext och sedan gissa fältnamn med aliaslistor. Google är tydliga: output blir syntaktiskt korrekt JSON enligt schemat, men värdena måste fortfarande valideras i appen.

**Passar Flow?** Passar direkt. Flow sätter idag BARA response_mime_type: application/json (meta_analysis_service.py rad 541-545) — inget schema. Konsekvensen syns i koden: normalize_meta_analysis() måste leta pallet_id bland 15 alias (pallet_id, pallid, pall_id, pall, godsmärkning, godsmarkning, godsmärke, goodsmarking, marking...) och _clean_single_text() måste hantera att modellen returnerar list/dict/kommaseparerad sträng. Hela den defensiva parsningen finns för att schemat saknas. Prompten ber redan om fältet confidence, men normalize_meta_analysis() slänger det — med responseSchema + required blir confidence garanterat och kan användas som eskaleringssignal (se model cascade).

**Var i Flow:** app/backend/meta_analysis_service.py: _gemini_generate_content() (body["generationConfig"], rad 541-545) — lägg till responseSchema med pallet_id: string, deviations: array[string], uncertainty_notes: string, confidence: number. Därefter kan _field()/_clean_single_text()-aliasen i normalize_meta_ana…

**Vinst:** Färre analysis_failed pga "Gemini-svaret kunde inte tolkas som JSON", färre manual_review pga fältnamn som inte matchade aliaslistan, och ett tillförlitligt confidence-fält som låser upp modellkaskaden. Ingen kostnadsökning.

**Kallor:** https://ai.google.dev/gemini-api/docs/structured-output · https://ai.google.dev/gemini-api/docs/caching


### Modellkaskad: flash/flash-lite först, eskalera till pro vid låg confidence

- **Lager:** ? · **Insats:** M · **Risk:** medel

**Vad tekniken ar:** Standardmönstret för kostnadsstyrning i produktions-LLM: kör den billigaste modellen först, eskalera bara när svaret är osäkert. Rapporterade besparingar i produktion är 50-80 procent med marginell kvalitetsförlust. Varningen från litteraturen: LLM:ers självrapporterade confidence är dåligt kalibrerad — tröskeln måste tunas mot verklig data, inte gissas.

**Passar Flow?** Passar mycket väl, och Flow har redan halva mekaniken. Priser (Gemini Developer API, juli 2026) för ljudinput per 1M tokens: gemini-2.5-pro 1,25 USD, gemini-2.5-flash 1,00 USD, gemini-2.5-flash-lite 0,30 USD. Flows default är GEMINI_MODEL = "gemini-2.5-pro" (config.py:92) — dyraste modellen för en uppgift som är "transkribera 30 sekunder svenskt tal och plocka ut ett pall-id". flash-lite är 4x billigare på ljud. Eskaleringssignalen finns redan gratis: _status_for_analysis() sätter manual_review när pallet_id eller deviations saknas, eller när uncertainty_notes är ifyllt — exakt de rader där ett pro-omtag är värt pengarna. Kaskaden blir alltså: kör flash-lite, och kör om med pro i stället för…

**Var i Flow:** app/backend/meta_analysis_service.py: _call_meta_analysis_provider() (rad 555-563) — kör _gemini_generate_content() med en billig modell, kör om med settings.GEMINI_MODEL om _status_for_analysis() ger manual_review eller confidence < tröskel. Kräver att _gemini_generate_content() tar model som argum…

**Vinst:** Grovt: om 80 procent av videorna klaras av flash-lite blir ljudkostnaden ~0,3*0,8 + 1,55*0,2 = ~0,55 mot 1,25 idag, dvs runt 55 procent lägre. flash-lite är dessutom snabbare, vilket kortar den serialiserade kön (META_ANALYSIS_MAX_CONCURRENCY=1).

**Kallor:** https://ai.google.dev/gemini-api/docs/pricing · https://tianpan.co/blog/2025-11-03-llm-routing-model-cascades · https://arxiv.org/pdf/2605.18796


### Prefix-cache för Apphjälpens systemprompt (DeepSeek/MiniMax automatisk KV-cache)

- **Lager:** ? · **Insats:** M · **Risk:** låg

**Vad tekniken ar:** DeepSeek har on-disk KV-cache påslagen som standard: identiska prompt-prefix återanvänds och rapporteras som prompt_cache_hit_tokens / prompt_cache_miss_tokens i usage. Cachen kräver EXAKT prefixmatchning — minsta skillnad i whitespace, datum eller ordning nollar träffen. Samma static-first/dynamic-last-regel gäller för Gemini implicit caching.

**Passar Flow?** Passar — och Flow bryter mot regeln på tre ställen samtidigt, vilket gör cache-hit-raten strukturellt noll. I build_minimax_payload() (routers/assistant.py:674-691) sätts ETT system-meddelande av SYSTEM_PROMPT_TEMPLATE där de statiska reglerna (~2 500 tecken) blandas med (a) current_date, (b) user_context, (c) wiki_context på upp till MAX_CONTEXT_CHARS = 24 000 tecken, (d) repo_context på upp till 14 000. Värst är wiki_context: _ranked_wiki_docs() rankar om wikin mot SENASTE frågan (rad 363-388), så systemprompten ändras mellan varje tur i SAMMA dialog. Resultatet är att upp till 38 000 tecken kontext skickas om vid varje tur, varje gång som cache-miss. Fixen är strukturell, inte ny teknik: …

**Var i Flow:** app/backend/routers/assistant.py: SYSTEM_PROMPT_TEMPLATE (rad 208-264) och build_minimax_payload() (rad 651-691); _ranked_wiki_docs() (rad 363-388). Sekundärt app/backend/mcp/chat.py:113-136.

**Vinst:** Den enskilt största kostnadsposten i LLM-lagret: en 10-frågors dialog (MAX_QUESTIONS_PER_SESSION) skickar idag upp till 10 x 38 000 tecken som färsk input. Med stabil prefix betalas den statiska delen till cache-hit-pris. Kortar även TTFT.

**Kallor:** https://api-docs.deepseek.com/guides/kv_cache · https://ai.google.dev/gemini-api/docs/caching · https://www.digitalocean.com/community/tutorials/prompt-caching-explained


### Token- och cache-telemetri (usageMetadata / usage.prompt_cache_hit_tokens) i spans

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** Alla leverantörer returnerar förbrukningen i svaret: Gemini i usageMetadata (promptTokenCount, cachedContentTokenCount, candidatesTokenCount), DeepSeek/OpenAI-kompatibla i usage (prompt_cache_hit_tokens, prompt_cache_miss_tokens). Team som optimerar LLM-kostnad loggar detta per anrop innan de rör något annat.

**Passar Flow?** Passar, och det är en förutsättning för punkterna ovan. Grep över meta_analysis_service.py, mcp/ och assistant.py ger NOLL träffar på usageMetadata, usage, prompt_tokens eller total_tokens — Flow mäter inte en enda token idag. Infrastrukturen finns redan: observability.py med start_span/add_span_attributes används överallt i LLM-vägarna (external.gemini.request, agent.llm_call, external.{provider}.chat_completion) och sätter redan llm.model, llm.answer_chars, mcp.context_items. Det är bara att plocka ut usage-blocket ur svaret och lägga till attributen.

**Var i Flow:** app/backend/meta_analysis_service.py: _request_json() (rad 359-383) och _gemini_generate_content() (rad 521-552). app/backend/mcp/chat.py: _gemini_generate_content() (rad 164-198) och _provider_chat_completion() (rad 289-326). app/backend/routers/assistant.py: _minimax_response() (rad 572-627, spane…

**Vinst:** Utan detta går kaskadens tröskel och prefix-cachens träffgrad inte att bevisa — man optimerar blint. Med det: cache-hit-rate och kostnad per analys blir mätbar per rad.

**Kallor:** https://api-docs.deepseek.com/guides/kv_cache · https://ai.google.dev/gemini-api/docs/caching · https://ai.google.dev/gemini-api/docs/tokens


### Files API-återanvändning: spara file_uri i 48 h i stället för att köra om ffmpeg

- **Lager:** ? · **Insats:** M · **Risk:** låg

**Vad tekniken ar:** Gemini Files API lagrar uppladdade filer i 48 timmar, upp till 20 GB per projekt, och är GRATIS (ingen kostnad för uppladdning eller lagring). Samma file_uri kan refereras i flera generateContent-anrop under fönstret.

**Passar Flow?** Passar direkt och löser ett konkret resursproblem i podden. Idag gör varje analys om HELA kedjan: extract_audio_file() startar en ffmpeg-subprocess (60 s timeout, -threads 1 just för att hålla nere minnet i podden), materialize_to_temp() skriver ut videon till disk, och ljudet laddas upp på nytt. Det sker igen vid varje omtag — och omtag är inbyggt i flödet: analysis_failed-rader har en Analysera-knapp, och run_queued_meta_analysis_once() plockar upp queued-rader. Med en kolumn för Gemini-file_uri + expires_at (Files API-svaret innehåller båda) på MetaShipmentObservation hoppar ett omtag inom 48 h direkt till generateContent. Detta är också det som gör modellkaskaden nästan gratis: pro-eskal…

**Var i Flow:** app/backend/meta_analysis_service.py: _gemini_upload_audio() (rad 442-493) och _call_meta_analysis_provider() (rad 555-563); ny kolumn på MetaShipmentObservation i models.py. Gemini-svaret från Files API innehåller redan expirationTime — bara att spara.

**Vinst:** Ett omtag går från ffmpeg (upp till 60 s CPU, subprocess-minne i en ~1 Gi-podd) + uppladdning + _gemini_wait_file_active()-polling (upp till 24 x 5 s) ner till ett enda generateContent-anrop. Klart snabbaste vägen till lägre latens vid omanalys, och gratis (Files API kostar inget).

**Kallor:** https://ai.google.dev/gemini-api/docs/files


### LjudLÄNGD, inte bitrate, styr Gemini-kostnaden — trimma tystnad med ffmpeg

- **Lager:** ? · **Insats:** S · **Risk:** medel

**Vad tekniken ar:** Gemini tokeniserar ljud till 32 tokens per sekund, dvs 1 920 tokens per minut. Taxan är oberoende av bitrate — Gemini nedsamplar internt till 16 kbps mono. Kostnaden är alltså en ren funktion av ljudets längd i sekunder.

**Passar Flow?** Viktig korrigering av en antagen optimering. Flows extract_audio_file() (rad 103-119) kodar till 32 kbit/s mono 16 kHz — det sparar uppladdningstid och tempfilstorlek, men NOLL tokens: Gemini hade tagit betalt exakt lika mycket för 128 kbit/s stereo. Nästa faktiska besparing i Meta-kedjan är därför att korta sekunderna, inte bitarna. En lotsvakts-inspelning består till stor del av tystnad, gångljud och hantering av pallen mellan det att hen säger pall-id och beskriver avvikelsen. ffmpeg silenceremove-filtret (och ev. atempo) tar bort den tysta tiden i samma subprocess som redan körs — ingen ny infrastruktur, inget nytt beroende. Måste mätas mot kvalitet: klipper man för hårt försvinner börja…

**Var i Flow:** app/backend/meta_analysis_service.py: extract_audio_file(), ffmpeg-kommandot rad 103-119 — lägg till -af silenceremove=... Bitraten -b:a 32k kan lämnas som den är (den sparar bandbredd, inte tokens).

**Vinst:** Direkt linjär: 40 procent bortklippt tystnad = 40 procent färre audio-tokens och 40 procent kortare inferens. Multiplicerar med modellkaskaden.

**Kallor:** https://ai.google.dev/gemini-api/docs/audio · https://ai.google.dev/gemini-api/docs/tokens


### Streaming av LLM-svar till UI via SSE (mönstret finns redan i repot)

- **Lager:** ? · **Insats:** M · **Risk:** låg

**Vad tekniken ar:** Standardgrepp för upplevd latens: strömma tokens i stället för att blockera tills hela svaret är klart. OpenAI-kompatibla API:er (MiniMax, DeepSeek) tar stream: true; Gemini har streamGenerateContent.

**Passar Flow?** Passar, och kräver noll ny infrastruktur — Flow har redan hela SSE-kedjan byggd och beprövad. Backend: routers/productivity.py:240-245 och routers/sankey.py:271-276 returnerar StreamingResponse med media_type=text/event-stream och headern X-Accel-Buffering: no. Frontend: js/productivity_overview.js:503 och js/sankey_inbound.js:577 konsumerar med EventSource — ren vanilla JS, inget byggsteg. Att kopiera mönstret till /api/assistant/chat och MCP är alltså inkrementellt, inte nytt. Två saker att hålla reda på: (1) GZipMiddleware (main.py:319) komprimerar inte StreamingResponse i Starlette — det är ett känt beteende och här är det till vår fördel, streamen buffras inte av middlewaren. (2) Apphjä…

**Var i Flow:** app/backend/routers/assistant.py: chat_with_assistant() (rad 694-808) → ny /api/assistant/chat/stream efter mallen i routers/productivity.py:240. Frontend: motsvarande EventSource-klient efter mallen i app/frontend/js/productivity_overview.js:503. Sekundärt app/backend/routers/mcp.py.

**Vinst:** Time-to-first-token i stället för time-to-full-answer. Störst effekt just i Flow, där EN uvicorn-worker + run_in_threadpool + en tool-loop gör att användaren idag sitter framför en tyst spinner i flera sekunder. Kostar inget extra i tokens.

**Kallor:** https://github.com/fastapi/fastapi/issues/4739 · https://github.com/sysid/sse-starlette · https://api-docs.deepseek.com/guides/kv_cache


### Kontextreduktion i Apphjälpen: chunk-nivå-retrieval i stället för hela dokument, och avveckla full repo-scan

- **Lager:** ? · **Insats:** M · **Risk:** låg

**Vad tekniken ar:** Prompt-komprimering med modeller (LLMLingua m.fl.) döms ut direkt — det kräver en lokal modell i podden och Flow har ~1 Gi och en worker. Det som fungerar i produktion utan extra infrastruktur är billigare retrieval: skicka relevanta stycken, inte hela filer.

**Passar Flow?** Passar, och den akuta delen är inte ens LLM-kostnad utan CPU. build_repo_context() (assistant.py:424-466) gör ROOT_DIR.rglob("*") och läser in OCH lowercase:ar varje textfil i hela repot — synkront, i podden, varje gång CHALLENGE_RE matchar ("du har fel", "jo", "visst", "kolla koden"...). Det körs i run_in_threadpool, men konkurrerar ändå om CPU och minne med den enda workern och med ffmpeg-subprocessen från Meta-analysen. Ett kommentarsblock på rad 721-724 erkänner redan problemet. Retrieval-sidan: build_wiki_context() klipper hela dokument på MAX_DOC_CHARS = 5 200 tecken och fyller upp till 24 000 — dvs stora block irrelevant text hamnar i prompten för att ett token råkade matcha. Byt till…

**Var i Flow:** app/backend/routers/assistant.py: build_wiki_context() (rad 391-406) och _ranked_wiki_docs() (rad 363-388) → chunka på ## -rubriker i stället för att klippa på 5 200 tecken. build_repo_context() (rad 424-466) → ersätt rglob-scanningen med en förbyggd fil-/rubrikindex eller ett anrop till git grep, a…

**Vinst:** Färre input-tokens per tur (kombinerat med prefix-cachen ovan: mindre ocachad svans), högre precision i svaren, och framför allt att en enda 'jo, du har fel'-fråga inte längre läser hela repot i den podd som samtidigt kör uvicorn och ffmpeg.

**Kallor:** https://ai.google.dev/gemini-api/docs/caching · https://api-docs.deepseek.com/guides/kv_cache


### Speculation Rules API — prerender med moderate eagerness (+ prefetch som säkert första steg)

- **Lager:** ? · **Insats:** L · **Risk:** medel

**Vad tekniken ar:** Deklarativ `<script type="speculationrules">` som säger åt Chrome/Edge att för-rendera nästa sida (full sidladdning inkl. JS + fetch) i en dold flik, som aktiveras instant vid klick. Eagerness styr triggern: conservative = pointerdown, moderate = 200 ms hover, eager = 10 ms hover, immediate = direkt. Chrome-gränser: max 2 samtidiga prerenders vid hover-baserad eagerness (FIFO), 10 vid immediate. Ray-Ban körde prerender med moderate eagerness på p…

**Passar Flow?** JA — och det här är den enskilt största posten i listan. Flow är en äkta MPA: sidbyten sker via riktiga `<a href>` i sidebaren (`js/common/sidebar.js:20`) och `window.location.href` (rad 75, 178, 938). Ingen CSP sätts någonstans (verifierat: `security_headers` i `app/backend/main.py` säger uttryckligen "CSP är medvetet INTE med här"), så inline speculation rules kräver noll policyarbete. Regler kan injiceras från JS och plockas upp även för dynamiskt tillagda länkar — passar att lägga i sidebar-renderingen. MEN: ren prefetch ger nästan ingenting i Flow, eftersom HTML:en är en statisk fil (`StaticFiles`, `main.py:512`) med `no-cache` och kostnaden i ett sidbyte ligger i 16-31 klassiska `<scri…

**Var i Flow:** Regler injiceras i `app/frontend/js/common/sidebar.js` (renderSidebar). Guards krävs i `app/frontend/js/common/telemetry.js` (reportClientEvent/flushWaitMetrics) och `app/frontend/js/common/demo_prefetch_init.js` (`reportPageOpen`, `enqueueVisiblePagePrefetches`, `reportPageLoadWaitMetric`) — inget …

**Vinst:** Sidbyte upplevs som noll väntan: JS-parsning, sidebar-rendering och alla API-anrop är redan gjorda vid klick. Störst effekt på Översikt/Bemanning/Historik som idag laddar 16-31 script + 5-10 API-anrop per navigering.

**Kallor:** https://web.dev/case-studies/rayban-speculation-rules · https://web.dev/case-studies/monrif-cwv · https://developer.chrome.com/docs/web-platform/prerender-pages


### document.prerendering + prerenderingchange-guards (förutsättning för prerender)

- **Lager:** ? · **Insats:** M · **Risk:** låg

**Vad tekniken ar:** Prerendrade sidor kör JavaScript FÖRE aktivering. Chrome exponerar `document.prerendering` (boolean) och event `prerenderingchange` så att sidan kan skjuta upp analytics, polling och sidoeffekter till aktivering. Chrome-dokumentationen är explicit: sidor ska fördröja analytics-events till aktivering för att inte blåsa upp mätvärden.

**Passar Flow?** JA — och det är obligatoriskt innan prerender aktiveras, annars blir det aktiv skada. Konkret i Flow: (1) `reportPageOpen()` i `demo_prefetch_init.js` skickar `view_open`-telemetri vid varje `initPage` → prerender av en sida användaren aldrig klickar på skulle registrera falska vy-öppningar i Historik/Analys. (2) `enqueueVisiblePagePrefetches()` köar ~10-25 bakgrunds-GET per sida → ett prerender av overblick.html triggar hela den kön mot backend. Med 1 uvicorn-worker i EN podd är det en reell lastfråga: moderate eagerness tillåter 2 samtidiga prerenders, dvs. worst case ~2 extra fulla sidladdningar med sina API-kaskader per hover. (3) Polling/auto-refresh finns redan bakom `document.hidden` …

**Var i Flow:** `app/frontend/js/common/demo_prefetch_init.js` (initPage: wrappa reportPageOpen + enqueueVisiblePagePrefetches i `if (document.prerendering) addEventListener('prerenderingchange', …)`), `app/frontend/js/common/telemetry.js` (buffra kön), `app/frontend/js/overview.js` + `js/schedule/data.js` (byt `do…

**Vinst:** Gör prerender säkert: ingen falsk telemetri, ingen dubblerad backend-last från idle-prefetch-kön, ingen polling mot en sida som ingen tittar på.

**Kallor:** https://developer.chrome.com/docs/web-platform/prerender-pages · https://developer.mozilla.org/en-US/docs/Web/API/Speculation_Rules_API


### Cross-document View Transitions (@view-transition { navigation: auto })

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** En CSS at-rule som ger animerade övergångar mellan HTML-dokument vid samma-origin-navigering, helt utan JavaScript. Båda sidorna måste opta in. Default är en cross-fade. Chrome 126+ och Safari 18.2+. Om navigeringen tar >4 s hoppas övergången över (TimeoutError).

**Passar Flow?** JA, med reservation. Flow har EN delad stylesheet (`app/frontend/css/styles.css`, 212 KB) som alla 26 HTML-sidorna länkar → en enda at-rule opt:ar in hela appen på en gång, noll byggsteg, noll JS. Samma origin genomgående (enda externa URL i frontend är en länk till stigamo.nu). Kombinerat med prerender ovan blir sidbytet både omedelbart OCH visuellt sammanhängande. RESERVATION: desktop-skalet kör `PyQt6-WebEngine==6.8.0` → QtWebEngine 6.8 → Chromium ~122, alltså UNDER Chrome 126-gränsen. Cross-document view transitions kommer helt enkelt inte att aktiveras i PyQt-appen. Det degraderar tyst (bara ingen animation), så det bryter ingenting — men paritetsregeln webb/desktop betyder att desktop …

**Var i Flow:** `app/frontend/css/styles.css` (en at-rule), eventuellt `view-transition-name` på sidebar + huvudrubrik så bara innehållsytan cross-fadar.

**Vinst:** Sidbyten känns som en app istället för fulla dokumentladdningar. Extremt låg insats i förhållande till upplevd polish.

**Kallor:** https://developer.chrome.com/docs/web-platform/view-transitions/cross-document · https://developer.mozilla.org/en-US/docs/Web/CSS/@view-transition


### scheduler.yield() för chunkad rendering av stora tabeller (INP)

- **Lager:** ? · **Insats:** M · **Risk:** låg

**Vad tekniken ar:** `await scheduler.yield()` bryter en lång task och lämnar tillbaka till huvudtråden, men lägger fortsättningen FRÄMST i kön — till skillnad från requestIdleCallback (lägsta prioritet, kan aldrig köras på en upptagen tråd) och setTimeout(0) (hamnar sist i kön). Stabilt i Chrome/Edge 129+ sedan sept 2024. Inte Baseline → kräver feature-check + fallback.

**Passar Flow?** JA för renderingen, med fallback. Flow bygger tabeller rad-för-rad med `document.createElement("tr")` + `appendChild` i en enda synkron loop (`analytics.js` ~10 sådana ställen, `overview_grid.js`, `persons_table.js`), och `data_fetch.js` bygger hela resultatet som en `innerHTML`-sträng (rad 306-326) med upp till 5000 rader (`data_fetch.py:71`: `le=5000`). Det är per definition en lång task som blockerar input → dålig INP. Flows befintliga `requestIdleCallback` (i `demo_prefetch_init.js:scheduleNextBackgroundPrefetch`) är helt rätt använd — den kör bakgrunds-prefetch, precis det rIC är till för. Men den är FEL verktyg för renderingsarbete som användaren väntar på. VIKTIG RESERVATION: Chromium…

**Var i Flow:** `app/frontend/js/analytics.js` (rad-loopar ~366-564), `app/frontend/js/data_fetch.js` (rad 306), `app/frontend/js/overview_grid.js`, `app/frontend/js/persons_table.js`. Lämpligen en delad `yieldToMain()`-helper i `js/common/foundation.js`.

**Vinst:** Tabellen börjar synas direkt och sidan slutar frysa vid stora resultat. Direkt effekt på INP i Historik och Hämta data.

**Kallor:** https://developer.chrome.com/blog/use-scheduler-yield · https://developer.mozilla.org/en-US/docs/Web/API/Scheduler/yield


### BroadcastChannel för cache-invalidering mellan flikar/fönster

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** Enkel pub/sub mellan samma-origin-kontexter (flikar, fönster, iframes, service worker). Standardmönstret: en lyckad mutation i flik A broadcastar "stale: orders", flik B slänger sin cache och hämtar om istället för att servera gammal data. Snabbare än storage-events eftersom inget skrivs till disk. Fire-and-forget — flikar som inte är öppna missar meddelandet, så en reconcile på focus behövs.

**Passar Flow?** JA, och Flow har exakt buggen mönstret löser. `api.js` har en in-memory GET-cache (`const apiGetCache = new Map()`, rad 91) som rensas vid varje mutation (`clearApiGetCache()` anropas i post/put/delete, rad 975-986) — men BARA i den flik som gjorde mutationen. SWR-snapshotsen ligger i `sessionStorage` (`api_swr.js`), som per definition är isolerad per flik. Resultat: har en arbetsledare Flow öppet i både webbläsaren och PyQt-desktopen (eller två flikar — realistiskt givet Bemanning + Översikt sida vid sida), så visar den andra vyn gammal data efter en ändring, och SWR-snapshoten gör det VÄRRE eftersom den serveras direkt vid nästa sidbyte. Ett `postMessage` från `clearApiGetCache` som får öv…

**Var i Flow:** `app/frontend/js/api.js` (`clearApiGetCache`, rad 224 — broadcasta + lyssna) och `app/frontend/js/common/api_swr.js` (`clearSwrSnapshots` — lyssna på samma kanal).

**Vinst:** Eliminerar en klass av "varför ser jag gammal bemanning?"-buggar utan en enda extra request mot backend — särskilt värdefullt eftersom SWR-piloten aktivt serverar avsiktligt inaktuell data.

**Kallor:** https://developer.mozilla.org/en-US/docs/Web/API/BroadcastChannel · https://stevekinney.com/courses/enterprise-ui/broadcast-channel


### CompressionStream (gzip i webbläsaren) för rrweb-buggrapporter

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** Inbyggd gzip/deflate-komprimering av strömmar i webbläsaren, utan bibliotek. Baseline sedan maj 2023. Vanligaste produktionsanvändningen: komprimera stora payloads klientsidan före upload för att komma under storleksgränser hos proxy/gratisnivåer.

**Passar Flow?** JA — för EN specifik, verklig payload i Flow. `js/common/bug_report.js` spelar in 30 sekunders DOM med rrweb och skickar `events_json: JSON.stringify(events)` som JSON-body (rad 206-227). Backend har en hård gräns: `BUG_REPORTS_MAX_EVENTS_BYTES` (`app/backend/routers/bug_reports.py:93-94`) → stora inspelningar avvisas. rrweb-events är repetitiv JSON och komprimerar typiskt 10-20x. Gzippa klientsidan, skicka som binär body med `Content-Encoding: gzip`, dekomprimera i FastAPI → fler rapporter går igenom, snabbare upload på lagernät. DÖM UT för de andra uppladdningarna: meta-upload tar `accept="image/*,video/*"` (redan komprimerat, gzip ger ~0), och allokerings-XLSX är redan en zip. CSV-uppladd…

**Var i Flow:** `app/frontend/js/common/bug_report.js` (`buildPayload`/`submitReport`, rad 206-227) + motsvarande dekomprimering i `app/backend/routers/bug_reports.py`.

**Vinst:** Buggrapporter med längre/tyngre inspelningar slutar avvisas mot storleksgränsen; snabbare inskick.

**Kallor:** https://developer.chrome.com/blog/compression-streams-api/ · https://web.dev/blog/compressionstreams · https://developer.mozilla.org/en-US/docs/Web/API/Compression_Streams_API


### DOM-windowing / virtuell scroll utan ramverk

- **Lager:** ? · **Insats:** L · **Risk:** medel

**Vad tekniken ar:** Rendera bara de rader som syns i viewporten plus en buffert; håll scrollhöjden med spacer-element (eller en `translateY`-offset) och räkna om start/slut-index från `scrollTop / rowHeight`. Går att göra i ~150 rader vanilla JS. IntersectionObserver är alternativet för enklare infinite-scroll-fall.

**Passar Flow?** JA, men bara där radantalet faktiskt är stort — och det är det på två ställen. `data_fetch.py:71` tillåter `max_rows` upp till 5000 och `data_fetch.js:306` bygger ALLA rader som en innerHTML-sträng; Historik (`analytics.js`) bygger likaså hela audit-loggen rad för rad. 5000 `<tr>` med flera `<td>` = 20-50k DOM-noder → tung style/layout och lång initial task. Det här är också det ENDA riktiga svaret för Flows tabeller, eftersom content-visibility inte fungerar på tabellrader (se nästa post). Kräver noll byggsteg och inget bibliotek. DÖM UT för Bemanning/Översikt: de tabellerna har sticky header + sticky namnkolumn och ett radantal som styrs av personallistan (tiotal, inte tusental) — windowin…

**Var i Flow:** `app/frontend/js/data_fetch.js` (renderingen kring rad 306-326) och `app/frontend/js/analytics.js` (tabellbyggarna). Inte `overview_grid.js`/`schedule`.

**Vinst:** Hämta data med 5000 rader går från flera sekunders frysning till omedelbar rendering; minnesavtrycket i fliken sjunker kraftigt.

**Kallor:** https://stackfull.dev/implementing-virtual-scroll-for-web-from-scratch-in-less-than-150-lines-of-code · https://dev.to/lalitkhu/rendering-massive-tables-at-lightning-speed-virtualization-with-virtual-scrolling-2dpp


### orjson + ORJSONResponse på de tunga payload-endpointsen

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** orjson serialiserar JSON i Rust, 2–6x snabbare än stdlib json. FastAPI-team sätter antingen `default_response_class=ORJSONResponse` eller returnerar `ORJSONResponse(payload)` direkt från handlern. Viktig nyans från FastAPI:s egen dokumentation: om man returnerar en Pydantic-modell med `response_model` går serialiseringen redan via Pydantic v2:s Rust-kärna — då tillför orjson inget. Vinsten uppstår när handlern returnerar en rå dict/list, för då k…

**Passar Flow?** Passar — och Flow ligger exakt i det fall där orjson faktiskt ger något. `orjson` finns INTE i app/requirements.txt. Endast 76 `response_model` i app/backend/routers/ mot ~616 synkrona handlers, dvs den dominerande vägen är rå dict → jsonable_encoder → json.dumps. De tunga endpointsen (/api/overview 970 ms median, /api/schedule 765 ms, /api/schedule/summary 631 ms enligt tools/latency_budgets.json) bygger stora nästlade dict-strukturer. Fungerar ihop med befintlig ETag-middleware (den läser response.body_iterator, vilket ett Response-objekt har) och GZipMiddleware. Varning: vinsten är i tiotals ms, inte hundratals — DB och compute dominerar fortfarande. Mät med tools.api_benchmark --compare …

**Var i Flow:** app/backend/main.py rad 114 (`FastAPI(...)` → lägg `default_response_class=ORJSONResponse`) samt returnera `ORJSONResponse(payload)` direkt i app/backend/routers/overview.py, schedule_query_routes.py, schedule_summary_routes.py och sankey.py för att även slippa jsonable_encoder. Ny rad i app/require…

**Vinst:** 2–6x snabbare JSON-dumps + helt bortfall av jsonable_encoder-passet på de största svaren. Störst effekt på /api/overview och /api/schedule där payloaden är stor och nästlad.

**Kallor:** https://fastapi.tiangolo.com/advanced/custom-response/ · https://github.com/ijl/orjson · https://kisspeter.github.io/fastapi-performance-optimization/json_response_class.html


### Pure ASGI-middleware istället för BaseHTTPMiddleware (@app.middleware("http"))

- **Lager:** ? · **Insats:** M · **Risk:** medel

**Vad tekniken ar:** Starlettes BaseHTTPMiddleware — som `@app.middleware("http")` skapar — allokerar per request: ett nytt Request-objekt, ett anyio-event, en memory-channel, en task group, och kör route-handlern som en separat bakgrundstask vars svar strömmas tillbaka genom kanalen och paketeras om i en StreamingResponse. Team som mätt detta (LiteLLM m.fl.) rapporterar ~1,8x throughput och upp till 40 % lägre middleware-overhead när de skriver om till ren ASGI-midd…

**Passar Flow?** Passar mycket väl. Flow har FEM BaseHTTPMiddleware staplade på varandra i app/backend/main.py: security_headers (rad 127), trace_context_middleware (146), static_cache_headers (241), demo_session_context_middleware (261), api_get_etag (278). Varje request betalar den anyio-maskineriet fem gånger, även /api/health. Tre av dem (security_headers, static_cache_headers, api_get_etag) rör bara headers/body och är triviala att skriva som ren ASGI-middleware som muterar `message["headers"]` i send-wrappern. api_get_etag är den dyraste: den materialiserar hela bodyn via `b"".join([chunk async for chunk in response.body_iterator])` och bygger ett helt nytt Response — i ren ASGI blir det en buffert + s…

**Var i Flow:** app/backend/main.py rad 127–319 (de fem @app.middleware("http")-dekoratorerna).

**Vinst:** Ingen DB-tid sparas, men per-request-overhead (objektallokering + task groups) faller kraftigt — publicerade mätningar visar ~1,8x throughput. Extra värdefullt just för Flow som kör EN uvicorn-worker: mindre event-loop-arbete per request = mer huvudutrymme åt de tunga handlarna.

**Kallor:** https://docs.litellm.ai/blog/fastapi-middleware-performance · https://github.com/Kludex/starlette/discussions/2160 · https://github.com/Kludex/starlette/discussions/1729


### Rikta in SQLAlchemy-poolen mot anyio-trådpoolen (pool_size / max_overflow / total_tokens)

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** FastAPI kör `def`-endpoints i anyio:s trådpool, som default har 40 tokens (40 samtidiga trådar). SQLAlchemys QueuePool har default pool_size=5 + max_overflow=10 = 15 anslutningar. Standardpraxis i FastAPI-team med synkrona endpoints är att göra dessa två tal medvetet kompatibla: antingen höja poolen till trådtaket eller sänka trådtaket till poolen. Annars köar överskjutande trådar i `pool.connect()` med 30 s timeout och man får `QueuePool limit .…

**Passar Flow?** Passar — och det här är en verklig, overifierad risk i Flow just nu. app/backend/database.py rad 20: `create_engine(url, pool_recycle=1500)` — inga pool_size/max_overflow satta alls, alltså default 5+10=15. Samtidigt är ~616 av ~639 route-handlers synkrona `def` (bara 23 `async def`), och `get_db` i app/backend/deps.py är en synkron generator som öppnar en Session vid requestens början och stänger den i finally — anslutningen hålls alltså under hela requestens livstid. Vid 40 samtidiga requests konkurrerar 40 trådar om 15 anslutningar. Med /api/overview på ~1 s median betyder det att ett tjugotal parallella användare räcker för att bygga kö. Åtgärd: sätt pool_size≈20, max_overflow≈10, pool_t…

**Var i Flow:** app/backend/database.py rad 20 (create_engine) och app/backend/main.py lifespan (rad ~95–111) för `anyio.to_thread.current_default_thread_limiter().total_tokens`.

**Vinst:** Tar bort en dold seriell flaskhals under samtidig last. Påverkar inte p50 för en ensam användare men skyddar p95/p99 och eliminerar QueuePool-timeouts när flera planerare jobbar samtidigt.

**Kallor:** https://dpdzero.com/blogs/fixing-fastapi-throughput-without-going-fully-async/ · https://github.com/fastapi/fastapi/discussions/8690 · https://docs.sqlalchemy.org/en/20/core/pooling.html


### raiseload("*") + load_only/defer som permanent N+1-skydd

- **Lager:** ? · **Insats:** M · **Risk:** låg

**Vad tekniken ar:** SQLAlchemy 2:s `raiseload()` / `lazy="raise_on_sql"` kastar InvalidRequestError i det ögonblick en lazy-load skulle ha skett. Team använder det som defaultstrategi i read-vägar: allt som ska användas måste vara explicit eager-laddat (selectinload för kollektioner, joinedload för many-to-one), annars smäller det i testet i stället för att tyst bli N+1 i prod. Kombineras med `load_only()` för att bara hämta de kolumner som serialiseras.

**Passar Flow?** Passar väl och kompletterar exakt det Flow redan byggt. wiki/prestanda-optimeringar.md dokumenterar N+1 (A2) som näst dyraste mönstret och Flow har redan frågebudget-kontraktstest (tests/services/test_query_count_budgets.py, regel E1). Men budgettesten upptäcker N+1 först i pre-push och bara på de endpoints som täcks; raiseload gör det omöjligt att införa i första hand och täcker ALLA vägar. Repot använder i dag `joinedload` på precis två ställen (app/backend/routers/meta_uploads.py rad 460/483, korrekt val för many-to-one mot media_upload) och `selectinload` inte alls — övriga relationsaccesser är implicit lazy. Rekommenderad utrullning: börja med `.options(raiseload("*"))` i de endpoints s…

**Var i Flow:** app/backend/routers/schedule_query_routes.py, overview.py, persons.py, activities.py — lägg `.options(load_only(...), raiseload("*"))` på read-queries. Modellrelationerna i app/backend/models.py om ni senare vill göra det till default.

**Vinst:** Gör N+1 till ett hårt fel i stället för en tyst latensregression. På dev-topologin (37 ms/rundresa enligt wiki/prestanda-optimeringar.md) är varje förhindrad N+1 direkt sekunder.

**Kallor:** https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html#preventing-unwanted-lazy-loads-using-raiseload · https://github.com/sqlalchemy/sqlalchemy/discussions/7044 · https://docs.sqlalchemy.org/en/20/orm/queryguide/columns.html


### fast_executemany=True på mssql+pyodbc-engine (bulk-insert)

- **Lager:** ? · **Insats:** M · **Risk:** medel

**Vad tekniken ar:** pyodbc:s `fast_executemany` skickar EN förberedd INSERT (sp_prepare) plus alla rader som en binär ODBC-parameterarray i stället för en rundresa per rad. Rapporterad mätning från SQLAlchemy-diskussion #9436: 5 000 rader på 4,0 s med fast_executemany=True/use_insertmanyvalues=False mot 62,7 s med tvärtom. Sedan SQLAlchemy 2.0.9 får `fast_executemany` sin avsedda effekt för alla multi-parameter-INSERTs UTAN RETURNING; insertmanyvalues (SQLAlchemys d…

**Passar Flow?** Passar för Flows batch-vägar, som i dag går via ORM `add_all()` utan någon MSSQL-specifik inställning: app/backend/person_productivity_cache.py rad 947 (dagligt produktivitetsbygge, potentiellt tusentals rader per bolag), app/backend/routers/audit_logs.py rad 355/374, healthcheck.py rad 110, meta_uploads.py rad 270. Engine skapas helt utan dialektflaggor (app/backend/database.py rad 20). Viktig nyans: ORM-inserts med autogenererad PK använder RETURNING → där slår insertmanyvalues in och fast_executemany hoppas över. Största vinsten får ni genom att köra bulk-vägarna som Core-insert utan RETURNING (`db.execute(insert(Model), [dict, ...])`) på en engine med `fast_executemany=True`. Sätt flagga…

**Var i Flow:** app/backend/database.py rad 20: `create_engine(url, pool_recycle=1500, fast_executemany=True)` villkorat på mssql-dialekt; sedan Core-insert i person_productivity_cache.py:947 och audit_logs.py:355/374.

**Vinst:** Storleksordning på batch-insert (10x+ i publicerade mätningar). Kortar det nattliga/30-min produktivitetsbygget och gör audit-skrivningarna billigare — och därmed även transaktionens låstid.

**Kallor:** https://github.com/sqlalchemy/sqlalchemy/discussions/9436 · https://github.com/sqlalchemy/sqlalchemy/issues/9586 · https://docs.sqlalchemy.org/en/20/dialects/mssql.html#fast-executemany-mode


### Query Store + SQLCommenter: attribuera dyra SQL-frågor till rätt endpoint

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** Query Store lagrar per fråga: CPU-tid, duration, logiska läsningar, plan-historik. Team använder "Top Resource Consuming Queries" (sys.query_store_query + query_store_runtime_stats) för att hitta de faktiska värstingarna server-side i stället för att gissa från klienten. Kombineras med SQLCommenter, som stoppar in nyckel-värde-taggar i SQL-texten (t.ex. route/controller) så att man kan gå från en dyr fråga tillbaka till exakt vilken endpoint som …

**Passar Flow?** Passar direkt — Flow har redan `opentelemetry-instrumentation-sqlalchemy` i app/requirements.txt och anropar `SQLAlchemyInstrumentor().instrument(engine=engine)` i app/backend/observability.py rad 453, men UTAN enable_commenter. Query Store är dessutom påslagen som standard på Azure SQL Database (secret.example.yaml visar `SERVER.database.windows.net`), så inget behöver aktiveras databassidan. Detta fyller ett verkligt hål: Flows enda prestandamätning i dag är klientsidig (tools/api_benchmark.py) och säger vilken ENDPOINT som är seg — inte vilken FRÅGA inuti den som kostar. KRITISK CAVEAT: SQL Server hashar hela frågetexten inklusive kommentaren, så en unik `traceparent` per anrop skapar en …

**Var i Flow:** app/backend/observability.py rad 452–453 (instrument-anropet). Analysen körs mot Azure SQL med en SELECT mot sys.query_store_runtime_stats.

**Vinst:** Går från "/api/overview tar 970 ms" till "den här SELECT:en står för 600 ms av dem, och den saknar index". Gör A1/A5-mönstren i wiki/prestanda-optimeringar.md hittbara utan manuell greppning.

**Kallor:** https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlalchemy/sqlalchemy.html · https://learn.microsoft.com/en-us/sql/relational-databases/performance/best-practice-with-the-query-store · https://learn.microsoft.com/en-us/sql/relational-databases/performance/monitoring-performance-by-using-the-query-store


### Nonclustered columnstore index (NCCI) på de aggregattunga tabellerna

- **Lager:** ? · **Insats:** M · **Risk:** medel

**Vad tekniken ar:** En NCCI på en rowstore-OLTP-tabell ger "real-time operational analytics" (HTAP): batch-mode-exekvering och kolumnkomprimering för GROUP BY/SUM/COUNT-frågor, medan punktuppslag fortsätter gå via B-tree-indexen. Microsofts designvägledning rekommenderar det för tabeller där både transaktionella och analytiska frågor körs, med `COMPRESSION_DELAY` för att låta färska rader stabilisera sig och ett filtrerat villkor för att bara indexera "kall" data.

**Passar Flow?** Passar för ett fåtal tabeller — inte generellt. Kandidaterna i app/backend/models.py är de append-only-och-aggregera-tabeller som växer obundet: `user_interaction_events` (rad 345 — här låg den värsta A1-boven, coverage 3910→173 ms enligt wiki/prestanda-optimeringar.md, och tabellen växer med varje klick), `audit_log` (rad 298) och `person_productivity_daily` (rad 250). Alla tre läses med GROUP BY/COUNT över tidsintervall och skrivs med add_all-batchar — precis NCCI:s use case. Passar INTE på schedule_cells (rad 145), persons eller activities: de är punktuppdaterade rad-för-rad i Bemanning/Översikt och skulle bara betala NCCI:ns delete-bitmap-kostnad. Förkastad systeralternativ: indexed view…

**Var i Flow:** Ny Alembic-migration i app/alembic/versions/ (nästa efter 0048_audit_log_indexes) med CREATE NONCLUSTERED COLUMNSTORE INDEX på user_interaction_events, audit_log, person_productivity_daily — villkorad på mssql-dialekt (SQLite i lokal test stöder det inte).

**Vinst:** Batch-mode + kolumnkomprimering på aggregatfrågorna över de växande tabellerna. Skalförsäkring: audit-indexen (0048) hjälper WHERE/ORDER BY, NCCI hjälper själva aggregeringen — de kompletterar varandra.

**Kallor:** https://learn.microsoft.com/en-us/sql/relational-databases/indexes/columnstore-indexes-design-guidance · https://learn.microsoft.com/en-us/sql/relational-databases/indexes/get-started-with-columnstore-for-real-time-operational-analytics · https://learn.microsoft.com/en-us/sql/relational-databases/indexes/columnstore-indexes-overview


### query_cache_size-tuning + mätning av compiled-cache-missar

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** SQLAlchemy 2 cachar kompilerade satser i en LRUCache med default 500 poster (`create_engine(..., query_cache_size=...)`). Cachen får växa till 150 % av taket innan den prunas. Vid "cache thrashing" — fler distinkta satsstrukturer än 500 — kompileras samma frågor om och om igen i ren Python. Man mäter det genom att titta i `engine._compiled_cache` eller genom SQLAlchemys cache-statistik i loggen. Ungefärlig minneskostnad: ~12 KB per Core-sats, ~20…

**Passar Flow?** Passar att MÄTA, inte att blint höja. Flow har 165 distinkta query-konstruktioner i routers (107 `db.query(...)` + 58 `select(...)`) plus servicelagret — troligen under 500-taket i dag, men de dynamiskt byggda frågorna (filter som varierar med business/area/roll) kan multiplicera antalet cachenycklar. Med bara 1 Gi minne i podden (k8s/deployment.yaml limits.memory) måste en höjning vägas mot OOM-risken — Flow har redan OOM-dödat podden en gång (Sankey, wiki/prestanda-optimeringar.md B2). Rätt ordning: mät först (räkna poster i engine._compiled_cache under en api_benchmark-körning), höj bara om cachen faktiskt prunar. Detta är en "verifiera-hypotesen"-punkt, inte en färdig fix — och wiki-sida…

**Var i Flow:** app/backend/database.py rad 20 (create_engine, saknar query_cache_size helt → default 500). Mätning via tools/api_benchmark.py-körning + inspektion av engine._compiled_cache.

**Vinst:** Om cachen thrashar: bort med per-request-kompilering av ORM-satser (ren CPU på event-loopen/trådpoolen). Om den inte thrashar: noll — och det är i sig ett värdefullt svar.

**Kallor:** https://docs.sqlalchemy.org/en/20/core/connections.html#configuring-caching · https://github.com/sqlalchemy/sqlalchemy/discussions/10722 · https://github.com/sqlalchemy/sqlalchemy/discussions/7881


## DELVIS TILLAMPLIGA (3)

Passar med reservation - las villkoret.

### pandas 3 / Arrow-backade dtypes (PyArrow-strängar) som mellansteg utan omskrivning

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** pandas 3.0 (släppt 2026-01-21) gör en dedikerad `str`-dtype till default, backad av PyArrow när det finns installerat (PDEP-14). Strängkolumner blir därmed kraftigt mindre och snabbare utan kodändring. Vidare kan `pd.read_csv(..., dtype_backend='pyarrow')` ge Arrow-backade kolumner rakt igenom.

**Passar Flow?** Delvis redan skördad: app/requirements.txt kör pandas==3.0.3 med pyarrow>=14 → alla `dtype=str`-läsningar i engine_core får redan Arrow-strängar. Det som återstår är (a) att verifiera att engine_core inte lutar sig på object-dtype-semantik (NaN vs None, `.astype(str)` på blandade kolumner) – det finns mycket `astype(str).str.strip()` i allocation.py, och (b) `dtype_backend='pyarrow'` i io_utils/process_matrix-läsningarna. Vinsten är en minnesbesparing på pandas-lagret, som i Flow inte är den heta vägen – därför medelvärde, inte huvudspår.

**Var i Flow:** warehouse_tools/engine_core/io_utils.py, app/backend/allocation_bridge_parts/process_matrix.py:286-299 (pd.read_csv med dtype=str, engine='python' – Python-parsern är dessutom den långsammaste; sätt explicit sep och släpp engine='python' där sniffing inte behövs)

**Vinst:** Gratis minnesvinst är redan tagen via pandas 3. Aktiv insats: mindre RAM i warehouse_tools + snabbare CSV-parsning genom att slippa engine='python'. Låg men billig vinst.

**Kallor:** https://pandas.pydata.org/docs/whatsnew/v3.0.0.html · https://pandas.pydata.org/pdeps/0014-string-dtype.html · https://pandas.pydata.org/docs/user_guide/migration-3-strings.html


### Gemini Batch API (50 procent rabatt) för köade analyser

- **Lager:** ? · **Insats:** L · **Risk:** medel

**Vad tekniken ar:** Batch API kör asynkrona jobb till 50 procent av standardpriset med en målsättning på 24 timmars turnaround (ofta snabbare). Jobben skickas som JSONL via Files API (upp till 2 GB) och kan referera uppladdade filer.

**Passar Flow?** DELVIS — döm ut för normalflödet, behåll för backfill. Flows Meta-analys är asynkron i implementationen (run_meta_analysis_background, analysis_status queued → analyzing → analyzed) men INTE i användarupplevelsen: UI:t pollar statusen och lotsvakten väntar på att pall-id och avvikelser ska dyka upp. Ett 24-timmarsfönster är oförenligt med det. Två skarpa undantag där batch däremot passar: (1) omanalys/backfill när prompt eller modell ändras och en hög gamla videor ska köras om — där finns ingen som väntar; (2) om kön växer (META_ANALYSIS_MAX_CONCURRENCY = 1, semafor + META_ANALYSIS_SPACING_SECONDS gör att kön redan serialiseras) kan queued-rader äldre än X minuter dumpas till batch i stället…

**Var i Flow:** app/backend/meta_analysis_service.py: run_queued_meta_analysis_once() (rad 804-818) och queued_meta_analysis_upload_ids() (rad 793-801) — en separat batch-väg, INTE analyze_meta_upload() som anropas från UI. Kräver ny status (t.ex. batched) på MetaShipmentObservation.

**Vinst:** 50 procent på det som körs i batch. Realistiskt bara omanalys/backfill idag, alltså begränsad total effekt — modellkaskaden ger mer för mindre arbete. Prioritera den först.

**Kallor:** https://ai.google.dev/gemini-api/docs/batch-api · https://ai.google.dev/gemini-api/docs/pricing · https://ai.google.dev/gemini-api/docs/files


### content-visibility: auto + contain-intrinsic-size

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** CSS-property som låter webbläsaren hoppa över rendering (style/layout/paint) av innehåll utanför viewporten tills det scrollas fram; `contain-intrinsic-size` reserverar plats så inget layoutskift uppstår. web.dev mäter renderingstider ned mot en fjärdedel på DOM-tunga sidor. Innehållet finns kvar i DOM och tillgänglighetsträdet.

**Passar Flow?** DELVIS — och specifikt INTE där Flows problem sitter. Verifierat mot spec: content-visibility "applies to: elements for which size containment can apply", och layout containment har ingen effekt på interna tabellboxar andra än table-cell (CSS Containment L2 / W3C). `<tbody>`, `<tr>` och `<td>` kan alltså inte få content-visibility — tabellens layoutalgoritm tillåter inte att boxar blir mindre än sitt innehåll. Flows tunga vyer ÄR äkta `<table>` (`table.overview` i overblick.html, Historik, Hämta data), så den populära "lägg content-visibility på raderna"-tricket fungerar helt enkelt inte här. Kvar finns två legitima användningar: (a) `contain: layout paint` på scroll-wrappern runt tabellen f…

**Var i Flow:** `app/frontend/css/styles.css` — på wrappers och div-listor, INTE på `table.overview` tr/tbody. För tabellerna: använd windowing (posten ovan) istället.

**Vinst:** Måttlig: kortare style/layout-tid på de div-tunga vyerna. Ingen effekt alls på de stora tabellerna — viktigt att inte tro annat.

**Kallor:** https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/content-visibility · https://www.w3.org/TR/css-contain-2/ · https://web.dev/articles/content-visibility


## AVFARDADE (11)

Passar INTE Flow. Skalet star i klartext - lagg inte tid har.

### Polars som ersättare för pandas

- **Lager:** ? · **Insats:** L · **Risk:** hög

**Vad tekniken ar:** Polars (Rust, Arrow-minne, lazy + streaming engine) är default för nya pipelines 2025-2026: rapporterade 3-16x speedup och upp till ~90 % lägre RAM än pandas; Check Technologies migrerade 100+ Airflow-DAG:ar på en sprint just för att slippa OOM, GitHub körde ett nattligt ETL från 128 GB/90 min till 32 GB/11 min.

**Passar Flow?** Döms ut som generell åtgärd i Flow – av två skäl som repot visar tydligt. (1) Flows heta väg använder inte pandas alls: produktivitet, KPI-scoring, Sankey och Hämta data läser `csv.DictReader` → `list[dict[str,str]]` och kör rena Python-loopar (productivity_service._read_csv_rows_with_headers, person_productivity_cache, sankey_inbound/build.py). En Polars-migration här är inte ett bibliotekbyte utan en total omskrivning – och Sankeys kärna är en *stateful* pall-/plockkö-simulering (build_graph._consume_pick_queue, _event_sort_key), som inte är vektoriserbar över huvud taget. (2) Där pandas faktiskt bor – warehouse_tools/engine_core (allocation.py, hib.py, ordersaldo.py) – är koden låst av ka…

**Var i Flow:** ej tillämplig (ev. framtida: warehouse_tools/engine_core/*)

**Vinst:** Skulle ge minne/fart, men bara efter en omskrivning som paritetstesterna gör dyr. Rekommenderas inte nu.

**Kallor:** https://www.databricks.com/blog/polars-vs-pandas · https://www.kdnuggets.com/pandas-vs-polars-a-complete-comparison-of-syntax-speed-and-memory · https://pythondataengineering.net/projects/polars-vs-pandas-production-pipelines


### np.vectorize-fällan (och den verkliga motsvarigheten i Flow: iterrows/apply(axis=1))

- **Lager:** ? · **Insats:** M · **Risk:** medel

**Vad tekniken ar:** NumPy:s egen dokumentation säger rakt ut att `np.vectorize` finns 'primarily for convenience, not for performance' – implementationen är i praktiken en Python-for-loop, och keyword/excluded-stödet gör den ännu långsammare. Många team tror att namnet betyder SIMD-vektorisering och 'optimerar' sig till oförändrad eller sämre prestanda.

**Passar Flow?** Positivt besked: grep över app/, warehouse_tools/, tools/ och services/ hittar noll användningar av np.vectorize – fällan finns inte i repot, och numpy används knappt alls direkt. Den ekvivalenta fällan finns däremot rikligt: `iterrows()` och `apply(...)` per rad/grupp i warehouse_tools/engine_core/allocation.py (rad 485, 495, 544, 706, 756), hib.py (140, 199, 223, 258, 457-461) och ordersaldo.py (214, 275), plus carrier_clusters.py:193. Detta är exakt mönster B1 som er egen wiki/prestanda-optimeringar.md redan pekar ut. Notera dock: allocation-loopen är delvis en *sekventiell allokeringsalgoritm* (saldo som konsumeras) och därmed inte trivialt vektoriserbar – gå igenom fall för fall, och lu…

**Var i Flow:** ej tillämplig för np.vectorize; mönstret finns i warehouse_tools/engine_core/allocation.py, hib.py, ordersaldo.py och warehouse_tools/carrier_clusters.py:193

**Vinst:** Ingen åtgärd behövs mot np.vectorize. Vinsten ligger i att ersätta iterrows med map/mask/merge där logiken är tillståndslös – men bara med karaktäriseringstesterna (tests/services/test_warehouse_flow_characterization.py) som skydd.

**Kallor:** https://numpy.org/doc/stable/reference/generated/numpy.vectorize.html · https://towardsdatascience.com/dont-assume-numpy-vectorize-is-faster-dd7e455dba2/


### RollingUpdate med maxSurge för noll nedtid — DÖMS UT i nuläget

- **Lager:** ? · **Insats:** L · **Risk:** hög

**Vad tekniken ar:** Standardreceptet för noll-nedtidsdeploy är RollingUpdate med maxSurge: 1 / maxUnavailable: 0 + readiness gate + preStop, så den nya podden är Ready innan den gamla dör. För RWO-PVC:er kräver det att båda poddarna hamnar på SAMMA nod (RWO tillåter flera poddar per nod, till skillnad från ReadWriteOncePod), vilket man tvingar fram med podAffinity mot sig själv.

**Passar Flow?** Går INTE att göra säkert i Flow idag — och kommentaren i k8s/flow.yml rad 6 ("One replica + Recreate because the PVCs are ReadWriteOnce") ger fel skäl. PVC-läget är faktiskt det MINSTA problemet: RWO tillåter två poddar på samma nod, så ren podAffinity skulle tekniskt lösa mount-biten. Den riktiga blockeraren är densamma som för --workers 2: under överlappet kör TVÅ processer mot samma DuckDB-fil på flow-media-PVC:n (app/backend/local_archive_store.py, RW-anslutningar) och mot samma trace-disk-spill (app/backend/sankey_inbound/trace.py rad 61). Dessutom kör den nya podden `alembic upgrade head` (main.py rad 84) mot samma MSSQL medan gamla podden fortfarande servar — schemaändringar måste då …

**Var i Flow:** k8s/flow.yml rad 6 (felaktig kommentar), rad 14-16 (replicas/strategy). Ej tillämplig förrän local_archive_store.py och trace.py är process-säkra.

**Vinst:** På sikt: noll nedtid vid deploy i stället för dagens dokumenterade "några sekunders driftstopp" (wiki/rfid.md rad 114). Men vinsten är inte värd risken förrän DuckDB-låset är löst — och 5 s nedtid på en intern app är billigt.

**Kallor:** https://kubernetes.io/blog/2021/09/13/read-write-once-pod-access-mode-alpha/ · https://blog.sebastian-daschner.com/entries/zero-downtime-updates-kubernetes · https://github.com/kubernetes/ingress-nginx/issues/6105


### PodDisruptionBudget — DÖMS UT (skulle aktivt skada)

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** PDB skyddar mot frivilliga avbrott (node drain, klusteruppgraderingar) genom att kräva att N poddar förblir tillgängliga. Den välkända fällan: en PDB med minAvailable: 1 på en Deployment med replicas: 1 tillåter noll frivilliga evictions — node drain FASTNAR för alltid. Konsensus i k8s-communityn (bl.a. zero-to-jupyterhub #1934): aktivera PDB först vid >= 2 repliker.

**Passar Flow?** Ej tillämplig, och det är rätt att den saknas. k8s/flow.yml har `replicas: 1` (rad 14) och ingen PDB — det är korrekt konfiguration. Skulle ni lägga till `minAvailable: 1` blockeras NoWaste-klusterteamets nodunderhåll av ER app, vilket är ett utmärkt sätt att bli impopulär i ett kluster ni inte äger. Enda meningsfulla PDB:n vid 1 replica är `maxUnavailable: 1`, vilket är en no-op. Slutsats: gör ingenting. Ta upp PDB igen först om ni någon gång kommer till 2+ repliker (vilket kräver att både DuckDB-cachen och PVC-modellen görs delbara — se ovan).

**Var i Flow:** ej tillämplig

**Vinst:** Vinsten är att INTE göra det: undviker att blockera node drains i ett kluster ni har begränsad kontroll över.

**Kallor:** https://kubernetes.io/docs/tasks/run-application/configure-pdb/ · https://github.com/jupyterhub/zero-to-jupyterhub-k8s/issues/1934 · https://oneuptime.com/blog/post/2026-02-20-kubernetes-pod-disruption-budgets/view


### CDN/edge-cache (Cloudflare e.d.) framför ingressen — DÖMS UT

- **Lager:** ? · **Insats:** S · **Risk:** hög

**Vad tekniken ar:** Vanligt mönster: lägg Cloudflare framför k8s-ingressen, cache-rule på hashade/immutable statiska filer, bypass på dynamiska. Gratis-tiern räcker för små team.

**Passar Flow?** Ej tillämplig, och DEPLOY.md rad 248-250 har redan rätt ("Inget CDN behövs"). Skälen håller vid granskning: (1) Flow är en intern app på flow.nowastelogistics.com med en handfull samtidiga användare — cache-hit-rate på edge blir irrelevant. (2) Statiska filer är REDAN optimalt cachade: tools/stamp_asset_versions.py stämplar `?v=<innehållshash>` i Docker-bygget (Dockerfile rad 42-43) och main.py rad 253-256 sätter `public, max-age=31536000, immutable` — plus service worker. Andra requesten kostar noll oavsett CDN. (3) En CDN framför skulle lägga en tredjepart i sessionsflödet (Secure/SameSite=Lax-cookies, main.py rad 118-124) och i den publika uppladdningssidans 256 MB-uppladdningar (ingress …

**Var i Flow:** ej tillämplig

**Vinst:** Ingen. Skulle aktivt bryta den publika 256 MB-uppladdningen.

**Kallor:** https://developers.cloudflare.com/cache/get-started/ · https://oneuptime.com/blog/post/2026-01-08-cloudflare-cdn-ddos-kubernetes/view · https://blog.cloudflare.com/cloudflares-free-cdn-and-you/


### Gemini context caching (implicit + explicit) för Meta-analysen

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** Implicit caching är på som standard för alla Gemini 2.5+ och ger automatisk rabatt när prompten har ett återkommande prefix. Trösklarna är 2 048 tokens (2.5 Flash/Pro) och 4 096 (3.x). Explicit cachedContents debiterar lagring, 4,50 USD per 1M tokens och timme för 2.5 Pro. Best practice: statiskt innehåll först i prompten, dynamiskt sist.

**Passar Flow?** DÖM UT som kostnadsåtgärd för Meta. Två oberoende skäl, båda verifierade i koden. (1) Storlek: META_ANALYSIS_INSTRUCTIONS (rad 133-158) är ~1 200 tecken, alltså ~400 tokens — långt under implicit-tröskeln 2 048. Det finns inget att cacha. (2) Ordning: i _gemini_generate_content() (rad 526-540) ligger file_data FÖRST i parts och texten SIST. Ljudet är unikt per video, så prefixet är per definition unikt varje anrop — även med en 10x större systemprompt skulle cachen aldrig träffa med den ordningen. Explicit cache är dessutom ekonomiskt orimlig för 400 tokens. Enda vettiga åtgärden är hygienisk, inte ekonomisk: flytta META_ANALYSIS_INSTRUCTIONS till systemInstruction (som mcp/chat.py:147 redan…

**Var i Flow:** Ej tillämplig som besparing i app/backend/meta_analysis_service.py:521-552. Endast prompt-hygien: flytta instruktionen till systemInstruction och byt ordning på parts.

**Vinst:** Noll som kostnadsåtgärd i dagens läge. Prompt-hygienen är förberedande.

**Kallor:** https://ai.google.dev/gemini-api/docs/caching · https://developers.googleblog.com/gemini-2-5-models-now-support-implicit-caching/ · https://ai.google.dev/gemini-api/docs/pricing


### 103 Early Hints

- **Lager:** ? · **Insats:** L · **Risk:** hög

**Vad tekniken ar:** Informationssvar som servern skickar MEDAN den fortfarande bygger det riktiga svaret, med Link-headers så att webbläsaren kan preloada/preconnecta under serverns tänktid. Rekommenderas bara över HTTP/2+ av kompatibilitetsskäl.

**Passar Flow?** NEJ — döms ut på två oberoende grunder. (1) Stacken kan inte skicka det: ASGI har en extension `http.response.early_hint`, men Uvicorn implementerar den inte (Uvicorn dokumenterar HTTP/1.1 + WebSockets; extensionen finns inte bland dess stödda extensions — Hypercorn/Gunicorn är de som nämns i sammanhanget). Flow kör uvicorn. (2) Ännu viktigare: även MED stöd finns ingen vinst att hämta. Early Hints existerar för att fylla serverns tänktid innan HTML:en är klar — men Flows HTML serveras av `StaticFiles` (`main.py:512`), alltså en filläsning på under en millisekund. Det finns ingen tänktid att fylla. Preload-scannern i webbläsaren hinner ändå läsa hela dokumentet och hitta alla `<script src>`/…

**Var i Flow:** ej tillämplig

**Vinst:** Ingen. Rekommenderar att inte lägga tid här.

**Kallor:** https://asgi.readthedocs.io/en/latest/extensions.html · https://www.uvicorn.org/ · https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/103


### modulepreload och preconnect

- **Lager:** ? · **Insats:** L · **Risk:** medel

**Vad tekniken ar:** `<link rel=modulepreload>` förladdar ES-modulgrafen; `<link rel=preconnect>` öppnar TCP+TLS mot en tredjepartsorigin i förväg.

**Passar Flow?** NEJ, båda. **modulepreload** kräver `type="module"` — Flow laddar uteslutande klassiska script (`<script src="/js/...">`, 16 st på historik.html, 19 på personer.html, 31 på index.html; noll `type=module` i repot). Att införa moduler skulle betyda ES-modul-migrering av hela frontend, vilket är precis den sortens byggstegs-/arkitekturskuld Flow medvetet undviker. Alternativet `<link rel=preload as=script>` ger nästan ingenting här: preload-scannern hittar redan alla script-taggar när dokumentet parsas, ingressen kör HTTP/2 (default på i ingress-nginx) så de multiplexas på en connection, filerna är `?v=`-stämplade med `max-age=31536000, immutable` (`main.py:255`) OCH cache-first i service worke…

**Var i Flow:** ej tillämplig

**Vinst:** Ingen mätbar. Den låga hängande frukten på laddningssidan är redan plockad (immutable + SW + gzip + ETag).

**Kallor:** https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/rel/modulepreload · https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/configmap/


### navigator.sendBeacon för telemetri

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** Skickar en liten payload utan att blockera unload; överlever sidbyte.

**Passar Flow?** REDAN INFÖRT — ingen åtgärd. `app/frontend/js/common/telemetry.js` (`flushWaitMetrics`) använder redan `navigator.sendBeacon` med en Blob när `keepalive` är satt, med fetch som fallback. Enda förbättringen värd att nämna är att den kön måste buffras under prerender (se posten om document.prerendering), annars skickas vy-öppningar för sidor användaren aldrig besökte.

**Var i Flow:** `app/frontend/js/common/telemetry.js` (flushWaitMetrics) — finns redan

**Vinst:** Redan realiserad.

**Kallor:** https://developer.mozilla.org/en-US/docs/Web/API/Navigator/sendBeacon


### Redis / Valkey som cache-lager

- **Lager:** ? · **Insats:** L · **Risk:** hög

**Vad tekniken ar:** Standardsvaret i FastAPI-världen för delad cache: fastapi-cache2 eller redis-py mot en Redis/Valkey-instans, med TTL per endpoint och invalidering vid skrivning.

**Passar Flow?** DÖMS UT för Flow som det ser ut i dag. Tre skäl, alla verifierade i repot: (1) k8s/deployment.yaml kör `replicas: 1` med `strategy: Recreate` och RWO-volymer — det finns ingen andra process som skulle dela cachen, vilket är hela poängen med Redis. En processlokal dict/lru_cache ger samma träff till noll nätverkskostnad. (2) Flow har redan ett fungerande L2: DuckDB-arkivcachen på PVC (wiki/local-archive-cache.md), gzip-JSON-trace-cachen och den förbyggda overview-report-cachen — alla överlever omstart, vilket en tom Redis inte gör bättre. (3) En Redis-podd blir en ny SPOF och nytt drift-/Octopus-objekt för en app vars flaskhals är DB-rundresor och pandas-compute, inte cache-uppslag. NÄR det b…

**Var i Flow:** ej tillämplig

**Vinst:** Ingen i nuvarande topologi. Skulle addera nätverkshopp + drift utan att lösa något Flow faktiskt har.

**Kallor:** https://github.com/long2ice/fastapi-cache · https://valkey.io/


### uvloop + httptools, 100-continue och chunked responses

- **Lager:** ? · **Insats:** S · **Risk:** låg

**Vad tekniken ar:** uvloop (Cython-loop ovanpå libuv) och httptools (Node.js HTTP-parser-bindningar) är de snabba ersättarna för asyncio-loopen respektive h11. Expect: 100-continue låter klienten vänta på serverns klartecken innan en stor body skickas. Chunked transfer-encoding låter servern strömma svar utan Content-Length.

**Passar Flow?** DÖMS UT — allt tre är redan på plats, ingen åtgärd behövs. (1) app/requirements.txt har `uvicorn[standard]==0.50.2`, och `[standard]` drar in uvloop + httptools; uvicorn väljer dem automatiskt när de är installerade och plattformen är Linux (vilket Dockerfile:n är: python:3.12-slim-bookworm). Att sätta `--loop uvloop --http httptools` explicit i CMD ger noll extra prestanda — bara ett hårdare fel om paketen saknas. (2) 100-continue: uvicorn skickar redan 100 Continue automatiskt när ASGI-appen anropar receive. Dessutom buffrar nginx-ingressen som standard request-bodies och svarar 100 Continue själv i stället för att skicka headern vidare — så uppströms i Flow skulle det ändå aldrig nå uvico…

**Var i Flow:** ej tillämplig (redan aktivt: app/requirements.txt uvicorn[standard], Dockerfile CMD, app/backend/media_store.py)

**Vinst:** Redan realiserad. Att "lägga till" detta skulle vara en no-op — värdet i att undersöka det är att kunna stryka det från listan.

**Kallor:** https://uvicorn.dev/server-behavior/ · https://www.uvicorn.org/settings/ · https://github.com/MagicStack/uvloop


## Kallor

- [Optimeringsplan (sammanfattning)](optimeringsplan.md)
- [Effektiviseringar - taxonomi](effektivisering-taxonomi.md)
- [Prestandaoptimeringar](prestanda-optimeringar.md)
---
title: Prestanda - leveranslagret
status: aktiv
updated: 2026-07-06
tags: [prestanda, cache, gzip, service-worker, latens]
---

# Prestanda: leveranslagret (gzip, cache, ETag, service worker)

Kort svar: appen komprimerar allt själv, statiska filer versionsstämplas med
innehålls-hash i Docker-bygget och cachas i ett år, API-GET-svar revalideras
med ETag/304, och en service worker gör upprepade sidladdningar nästan
nätverksfria. Allt infört 2026-07 utan kvalitetsrisk: ingen optimering ändrar
vilken data användaren ser.

## Lagren, utifrån och in

1. **GZip (backend, `app/backend/main.py`).** `GZipMiddleware`
   (`minimum_size=1024`) läggs ytterst i middleware-kedjan och komprimerar
   både API-JSON och statiska JS/CSS-svar. Starlette undantar
   `text/event-stream` som standard, så SSE-progressströmmarna
   (produktivitet/sankey) påverkas inte — kontraktstestat i
   `tests/services/test_http_delivery.py`. Ingressen behöver INTE gzippa.
2. **Versionsstämplade statiska filer.** `tools/stamp_asset_versions.py` körs
   i Docker-bygget (se `Dockerfile`) och skriver om alla lokala
   script/link-taggar till `?v=<10 tecken sha256 av filinnehållet>`.
   Backendens `static_cache_headers`-middleware svarar i produktion:
   - `.html` och `/` → `no-cache` (revalideras alltid; StaticFiles ETag ger
     billiga 304)
   - `.js/.css/.svg/...` **med** `?v=` → `public, max-age=31536000, immutable`
   - utan `?v=` → `no-cache`
   Innehålls-hash = deterministisk: oförändrade filer behåller sin URL mellan
   deployer och ligger kvar i webbläsarcachen. Repofilerna stämplas aldrig —
   lokal dev (no-store) och desktop läser dem orörda; de handskrivna
   `?v=`-etiketterna i repot är ofarliga rester som bygget skriver över.
   Kontrakt: `tests/tools/test_stamp_asset_versions.py` failar om någon tagg
   skrivs så att stämplingen missar den, eller pekar på en fil som inte finns.
3. **ETag/304 på API-GET.** `api_get_etag`-middlewaren hashar JSON-svar
   (svag ETag) och svarar 304 utan payload vid träff på `If-None-Match`;
   svaren får `private, no-cache`. Oförändrat data kostar en RTT i stället
   för hela överföringen. SSE, filer och no-store-svar lämnas orörda.
4. **Service worker (`app/frontend/sw.js`).** Cache-first ENBART för
   versionsstämplade filer (`?v=` + statiskt suffix) — riskfritt eftersom
   URL:en byter när innehållet byter. HTML, `/api/` och ostämplade filer rörs
   inte. Registreras i `js/common/foundation.js` endast över https (=
   produktion); dev och desktop kör http och läser filerna direkt.
5. **Frontend-datalagret (sedan tidigare).** GET-cache med TTL + prefetch:
   `enqueueVisiblePagePrefetches` i `js/common/demo_prefetch_init.js` körs för
   ALLA användare på varje sidladdning (trots filnamnet) och förhämtar under
   idle det data användarens synliga sidor behöver. In-flight-delning och
   cache-invalidering vid mutationer finns i `js/api.js`.
6. **Beräkningslagret (sedan tidigare).** Produktivitetens snapshot-scheduler
   (halvtimmesvis + daglig backfill) förberäknar tunga vyer — "värmningen"
   finns alltså redan; se [local-archive-cache](local-archive-cache.md) för
   DuckDB-arkivet.

## Latensbudget

`tools/latency_budgets.json` sätter max median-ms per kärnendpoint.
Körs med `python -m tools.api_benchmark ... --budget tools/latency_budgets.json`
(exit 2 vid överträdelse) efter prestandapåverkande releaser — rutin i
`DEPLOY.md`. Budgetarna är generösa startvärden; dra åt dem när riktiga
rapporter finns i `artifacts/api_benchmark/`.

## Workers-beslutet (2026-07-06)

1 uvicorn-worker står fast. Audit fann att sankeys spårnings-cache
(`backend/sankey_inbound/trace.py`, `_TRACE_CACHE`) lagrar trace-tokens i
processminne: med flera workers kan drill-down landa i fel process → 410.
Övriga in-memory-cacher (person-/produktivitetsrapporter, ytgenerering,
sankey source-cache) dupliceras bara (minne/CPU, inte fel). Eskalering:
om Väntetider visar köbildning vid samtidig last → flytta trace-cachen till
DB, sedan `--workers 2` (ledarlåset skyddar redan bakgrundsjobben).

## Fallgropar

- Ta aldrig bort `Cache-Control: no-cache` från SSE-endpoints — det är ett
  tekniskt krav för strömmar, inte ett prestandaval.
- En ny HTML-sida med script-taggar i annan citatstil än `src="..."` fångas
  av kontraktstestet — skriv taggarna som de befintliga sidorna.
- Bumpa `STATIC_CACHE`-namnet i `sw.js` bara vid avsiktligt cache-byte;
  gamla cachar rensas i activate.

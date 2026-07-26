---
title: Test-strategi
status: aktiv
updated: 2026-07-26
tags: [test, pytest, playwright, hypothesis, flake, ci]
---

# Test-strategi: lagren, markörerna och flake-policyn

Kort svar: sviten är lagerindelad med tydliga gates - pre-push kör den snabba
deterministiska delen parallellt, CI är enda gate för browsertesterna (med
begränsade omkörningar), en nattlig flake-jakt hittar instabilitet innan den
blockerar någon, och nya testklasser (behörighetssvep, property-tester,
samtidighets-smoke) skyddar det som exempeltester inte når.

## Lagren

| Lager | Var | Vad de låser |
|---|---|---|
| Service-/routertester | `tests/services/` | Backendlogik via TestClient, in-memory/fil-SQLite |
| Kontraktstester | `tests/tools/` | Arkitekturregler, API-rutter, deploy-probes, terminologi, stämpling |
| Behörighetssvep | `tests/tools/test_api_auth_sweep.py` | Varje /api-rutt avvisar oautentiserat; publika endpoints kräver vitlistning med motivering |
| Golden-karakterisering | `tests/services/test_warehouse_flow_characterization.py` | Motorns utdata byte för byte - privat (lokalt) + syntetiskt (CI), inkl. goods-declaration sedan 2026-07-06 |
| Property-tester (Hypothesis) | `tests/services/test_engine_properties.py` | Egenskaper på genererade indata: "aldrig 'nan' i Plockplats", "chunks == indata", web/desktop-paritet för Dela |
| ETag/samtidighet | `tests/services/test_etag_and_concurrency.py` | Mutation ogiltigförklarar cache; parallella GET ger aldrig 5xx |
| Leveranskontrakt | `tests/services/test_http_delivery.py` | gzip, cache-headers, 304-beteende (se [prestanda-leveranslager](prestanda-leveranslager.md)) |
| Browsertester (Playwright) | `tests/tools/test_*_browser.py` | Riktiga UI-flöden i chromium |
| JS-enhetstester | `tests/tools/test_js_unit_harness.py` | Ren frontendlogik injicerad i tom Playwright-sida (pilot: ISO-veckologik mot Pythons isocalendar) |
| Desktop | `tests/desktop/` + smoke i CI | Qt-skalet och paritetsytor |
| Dialektgates (CI) | `.github/workflows/test.yml` | Alembic från noll mot Postgres OCH MSSQL |

## Markörer och var tester körs

- `browser` - **auto-märks** i `tests/conftest.py` på alla tester som använder
  `chromium_browser`-fixturen (en ny browserfil kan inte glömma markören).
- **Pre-push** (`.githooks/pre-push`): typkontroll + lint + `pytest -m "not
  browser"`. Snabbt och deterministiskt - utvecklarmaskinens dagsform
  (OneDrive-synk, CPU-last) ska inte gate:a pushar.
- **CI** (`test.yml`): icke-browser parallellt (`-n auto`), därefter browser
  med `--reruns 2 --reruns-delay 5`. CI är browsertesternas enda gate.
- **Nattligt** (`nightly-flake-hunt.yml`): browsersviten 3x UTAN omkörningar,
  02:00 UTC; öppnar issue vid fall. Kan triggas manuellt (workflow_dispatch).

## Flake-policyn

1. En omkörning i CI är ett symptom, inte en lösning. Återkommande RERUN på
   samma test = rotorsaka eller karantänsätt (skip med issue-länk) - aldrig
   låta den "vara lite skakig".
2. Rotorsaksexempel 2026-07-06 (`copy_whole_columns`): stilkontrakt läste
   getComputedStyle före stylesheets laddats klart under I/O-last, och
   toast-expecten (5s default) täckte inte kopieringsflödets serverrundresa.
   Åtgärd: `wait_for_load_state("load")` + filens 15s-konvention - innehålls-
   kraven oförändrade. Härda testet, sänk aldrig ribban.
3. Rotorsaksexempel 2026-07-26 (`dedupe empty_input`): `dubbletter.js` band
   knapplyssnarna först efter `await initPage()` (auth-rundresan), medan testet
   bara väntade på att DOM fanns - klick under CI-last kunde landa på en död
   knapp. Åtgärd: bind lyssnarna synkront före `await initPage()` (verktyget är
   helt klientsidigt) plus ett regressionstest som håller `/api/auth/me` öppet
   och klickar ändå. Mönstret "lyssnare efter await initPage" finns på fler
   sidor - de flesta behöver användardata före interaktion, men rent
   klientsidiga verktyg ska binda före await.
4. Playwright-väntetider: följ 15s-konventionen för selector-/URL-väntor och
   för expects vars väg innehåller en serverrundresa.

## Nya tester - var hör de hemma?

- Backendlogik -> service-test. Beteenderegel över tid -> kontraktstest.
- Ny /api-rutt: behörighetssvepet fångar den automatiskt; publik rutt kräver
  vitlistepost med motivering i `test_api_auth_sweep.py`.
- Motorändringar: golden-testerna (kör lokalt mot privat data; syntetiska i
  CI). Regenerera avsiktligt med `FLOW_GOLDEN_UPDATE=1` och granska diffen.
- Ren pur funktion med tydlig invariant -> Hypothesis-property.
- Ren JS-logik -> JS-harnessen (injicera filen, evaluera). UI-flöde -> riktigt
  browsertest.

## Coverage

`pytest-cov` finns i requirements-dev. Ingen CI-gate (siffran är inte målet);
kör vid behov för att hitta mörka hörn:

    python -m pytest -m "not browser" -n auto --cov=app/backend --cov-report=term-missing:skip-covered

Resultatet från engångsanalysen 2026-07-06 och kvarvarande mörka hörn:
se log-posten samma datum.

---
title: Frontend-typning och lint
status: aktiv
updated: 2026-07-06
tags: [frontend, typning, jsdoc, tsc, eslint, kontrakt]
---

# Frontend-typning och lint

Kort svar: frontendens vanilla JS typkontrolleras med JSDoc-kommentarer som
TypeScript-kompilatorn verifierar (`npm run typecheck`) och lintas med ESLint
(`npm run lint`). Ingen build, ingen runtime-paverkan - koden som servas ar
oforandrad ren JS. CI och pre-push-hooken kor bada kontrollerna.

## Varfor

32 000+ rader vanilla JS i 80+ filer utan modulsystem har osynliga kontrakt:
funktioner som antar objektformer och globalt state mellan script-taggar. En
andring i `api.js` sager inte vilka filer som gar sonder. JSDoc + `tsc` gor
kontrakten maskinkontrollerade utan att ge upp buildlosheten (enkel deploy,
QWebEngine laddar filerna rakt av). Forsta korningarna hittade direkt en
global namnkollision och dod kod i tva filer.

## Verktyg och filer

| Fil | Roll |
| --- | --- |
| `package.json` | Dev-verktyg: `typescript` + `eslint`. Inga runtime-deps. |
| `jsconfig.json` | tsc-konfig: `checkJs: false` globalt, filer opt:ar in med `// @ts-check`. |
| `eslint.config.js` | Korrekthetsregler (dupliceringar, oatkomlig kod, konstanta uttryck). Ingen stil. |
| `app/frontend/js/types/flow-globals.d.ts` | Globala typer: `ApiError`, `ApiRequestOptions`, `Window`-ytan (`flowLog`, `api`, ...). Ingen runtime-kod. |

Kommandon (fran repo-roten): `npm install` (en gang per maskin),
`npm run typecheck`, `npm run lint`.

## Regler (samma som AGENTS.md)

1. **Utrullning:** JS-fil som andras vasentligt far `// @ts-check` hogst upp
   och typfelen fixas i samma insats. Tackningen vaxer fil for fil.
2. **Flyktvag:** `@ts-ignore` kraver motivering pa raden. Behandlas som
   radtaksundantag - synligt och ifragasatt.
3. **Backend-synk:** Pydantic-schemaandring i `app/backend/schemas.py` =>
   uppdatera motsvarande typedef/interface i samma arbetsinsats.
4. **Domangranser:** en sida laddar `js/common/` + hogst en domankatalog;
   kontraktet i `test_architecture_contracts.py::ALLOWED_PAGE_DOMAINS`.

## Status for utrullningen

- `// @ts-check` aktivt i: `api.js`, `common/foundation.js`,
  `sankey_inbound_state.js`.
- Kolla aktuellt lage: `grep -rl "^// @ts-check" app/frontend/js`.
- API-svarens former genereras fran backendens OpenAPI-schema till
  `types/api-schema.d.ts` (`python -m tools.generate_api_types`); CI failar om
  filen inte regenererats nar `schemas.py` andrats. Anvands i JSDoc via
  `import("./types/api-schema").components["schemas"]["..."]`.
- Blockerad kandidat: `overview_state.js` deklarerar `state`/`drag`/
  `personOrderDrag` som ocksa finns i `schedule/state.js` (olika sidor, ingen
  runtime-krock). Kraver namnrymdsflytt (t.ex. `overviewState`) i hela
  overview-domanen innan @ts-check kan sla pa dar.
- Nasta kandidater darefter: `common/sidebar.js`, `schedule/state.js`.

## Vad checkarna INTE gor

- Typerna verifierar former, inte logik - Playwright/pytest behovs fortfarande.
- API-typedefs ar pastaenden: om backend andras utan typedef-uppdatering ljuger
  typerna (darfor synkregeln; pa sikt kan typedefs genereras fran OpenAPI).
- ESLint kor med `no-undef` avstanget: globals mellan script-taggar kan inte
  verifieras per fil. Typkontrollen tar det ansvaret nar filer ar `@ts-check`:ade
  (tsc ser hela programmet och kanner alla globals).

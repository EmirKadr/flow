---
title: Dubbletter
status: aktiv
updated: 2026-07-20
tags: [verktyg, dubbletter, excel, klientsidigt, urklipp]
---

# Dubbletter

Kort svar: Verktyget `Dubbletter` gor samma sak som Excels **Ta bort dubbletter**
direkt i Flow. Anvandaren klistrar in varden - en kolumn eller flera
tabbseparerade kolumner fran Excel - och far tillbaka de unika raderna med
forsta forekomsten kvar och ordningen bevarad. Allt sker i webblasaren:
verktyget gor inga API-anrop och ingen data lamnar klienten.

## Anvandarflode

1. Oppna `Verktyg` i sidebaren och valj fliken `Dubbletter` (`/dubbletter.html`).
2. Klistra in vardena i rutan `Indata`. Raknaren visar antal rader och, om
   inklistringen har flera kolumner, hur manga kolumner som hittades.
3. Justera `Jamforelseregler` vid behov. Alla tre ar pa fran borjan:
   trimma blanksteg, ignorera skiftlage och hoppa over tomma rader.
4. Vid flera kolumner visas `Jamfor kolumner`. Kryssa i vilka kolumner som
   avgor om en rad ar en dubblett - precis som kolumnlistan i Excels dialog.
   Som default jamfors hela raden.
5. Klicka `Ta bort dubbletter`. Panelen `Resultat` visar de unika raderna,
   en sammanfattning (`X rader in - Y unika - Z borttagna`) och listan
   `Borttagna dubbletter` med hur manga ganger varje varde forekom.
6. `Kopiera resultat` lagger de unika raderna i urklipp. `Rensa` tommer bada
   rutorna.

Windows-appen serverar samma statiska frontend via sin lokala appyta, sa vyn
beter sig likadant i webb och desktop. Kopieringen gar via `navigator.clipboard`
med en `document.execCommand("copy")`-fallback eftersom QtWebEngine kan sakna
eller neka clipboard-API:t.

## Knappar och kontroller

| Kontroll | Var | Vem far | Vad hander | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- | --- |
| Indata | Panelen `Klistra in varden` | Anvandare med `removeDuplicates=view` | Tar emot inklistrad text; rader delas pa radbrytning, kolumner pa tabb | `dubbletter.html`, `dubbletter.js` | Excel-kopiering ger tabbar - klistrar man in fran ett textdokument blir allt en kolumn. |
| Trimma blanksteg | Jamforelseregler | Samma | Ledande/avslutande blanksteg ignoreras vid jamforelsen. Utdatan behaller originalvardet | `dedupeRowKey` | Excel gor *inte* detta; darfor kan Flow hitta fler dubbletter an Excel pa samma data. |
| Ignorera skiftlage | Jamforelseregler | Samma | `ABC` och `abc` raknas som samma varde | `dedupeRowKey` | Avmarkera nar skiftlaget ar betydelsebarande (t.ex. kod-ID). |
| Hoppa over tomma rader | Jamforelseregler | Samma | Tomma rader tas bort helt i stallet for att bli ett eget varde | `dedupeRows` | Avmarkerad blir tomraden ett varde som i sin tur kan vara dubblett. |
| Jamfor kolumner | Panelen `Jamfor kolumner` | Samma | Valjer vilka kolumner som ingar i dubblettnyckeln. Visas bara vid 2+ kolumner | `dedupeRowKey`, `dedupeRenderColumns` | Utan markerad kolumn blockeras korningen med en warn-toast. |
| Markera alla / Avmarkera alla | Panelen `Jamfor kolumner` | Samma | Snabbval for kolumnkryssrutorna | `dedupeSetColumnsSelection` | - |
| Ta bort dubbletter | Panelen `Klistra in varden` | Samma | Kor dedupen och visar resultatpanelen + toast | `dedupeRun`, control-id `dedupe-run` | Tom indata ger warn-toast `Klistra in varden forst`. |
| Rensa | Panelen `Klistra in varden` | Samma | Tommer indata, resultat och kolumnval | `dedupeClear` | Sparar inget - rensat ar borta. |
| Kopiera resultat | Panelen `Resultat` | Samma | Kopierar de unika raderna till urklipp | `dedupeCopyText`, control-id `dedupe-copy` | Nekas clipboard-behorigheten visas en error-toast som ber anvandaren markera texten manuellt. |

## Regler och kantfall

- **Forsta forekomsten behalls** och radordningen fran indata bevaras, som i Excel.
- **Nyckeln byggs med `JSON.stringify`** av de valda cellerna. Det gor att raden
  `a b` aldrig kolliderar med cellerna `a` + `b`, och att en kort rad inte blir
  samma varde som en langre rad med tomma celler.
- **Radbrytningar normaliseras** (`\r\n` och `\r` -> `\n`) och en avslutande
  radbrytning ger ingen extra tom rad.
- **Utdatan ar originalvardena**, inte de normaliserade - trim och skiftlage
  paverkar bara jamforelsen.
- Listan `Borttagna dubbletter` visar hogst 50 poster och raknar upp resten.

## Behorighet

Vy-id: `removeDuplicates`, etikett `Dubbletter`. Registrerat i
`ROLE_VIEW_ORDER`/`ROLE_VIEW_LABELS` (`app/backend/user_access.py`),
`ROLE_VIEW_IDS` (`foundation.js`), `VIEW_ACCESS_OPTIONS` (`role_access.js`) och
`SIDEBAR_TOOLS_TAB_VIEW_IDS`/`SIDEBAR_VIEW_HREFS` (`access.js`).

Default-atkomst: `edit` for Arbetsledare, Bemanningsansvarig, Administrator,
Demo, Lagerkontorist och Artikelplacerare; `view` for Visning. Super User har
`edit` via rollens lasta niva. Person-only-konton har medvetet ingen atkomst -
deras yta halls minimal. Verktyget skiljer inte pa `view` och `edit` i praktiken
eftersom ingenting sparas; nivan finns bara for att matrisen ska vara konsekvent.

## Audit och Historik

Verktyget ar ett **avsiktligt read-only-undantag**: det gor inga API-anrop, andrar
ingen data och skriver darfor ingen `audit_log`-rad och ingen Historik/Analys-
label. Undantaget testas av
`tests/tools/test_dedupe_frontend.py::test_tool_is_client_only_and_has_no_audit_trail`,
som faller om ett `fetch`/`api.*`-anrop laggs till. Laggs backend-anrop till ska
audit-scope och Historik-label planeras i samma andring (AGENTS.md, Loggregel).

Anvandarfeedback ges i stallet via toast + dokumentlogg: success vid borttagna
dubbletter, info nar inga hittades, warn vid tom indata eller saknat kolumnval,
error nar urklipp nekas.

## Tester

- `tests/tools/test_dedupe_frontend.py` - statiska kontrakt: vy-id registrerat i
  bade klienter, default-access i synk mellan `user_access.py` och
  `foundation.js`, verktygsfliken pa alla tools-sidor, klientsidigt/audit-undantag,
  clipboard-fallback for desktop.
- `tests/tools/test_js_unit_harness.py` (avsnitt Dedupe-karnan) - enhetstester
  for `dedupeParseRows`/`dedupeRows`: ordning, radbrytningar, trim/skiftlage,
  tomma rader, kolumnval, ojamna rader och nyckelkollision.
- `tests/tools/test_dedupe_browser.py` - anvandarflodet: enkolumn, Excel-kolumner
  med kolumnval, blockerat lage utan vald kolumn, tom indata + Rensa, samt
  navigering hit via verktygsfliken.

## Relaterat

- [Etiketter](label-editor.md) - annat fristaende verktyg under samma flikrad.
- [UI-karta](ui-map.md) - var vyn ligger i menyn.

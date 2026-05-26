---
title: Bemanning
status: aktiv
updated: 2026-05-26
tags: [bemanning, schema, ui, knappar]
---

# Bemanning

Kort svar: Bemanning ar huvudmatrisen. Anvandaren valjer ar/vecka/dag och styr omrade med omradesfokus i sidebar. Sedan satter anvandaren aktivitet per person och timme. Andringar sparas direkt till `/api/schedule/*` med versionsskydd.

## Anvandarflode

1. Sidan laddar omraden och aktiviteter.
2. Sidan laddar hela schemadagen for aktuell verksamhet och filtrerar valt omradesfokus direkt i klienten. Om perioden redan finns i lokal all-cache eller exakt omradescache ritas den utan nytt API-anrop.
3. Varje rad ar en person; varje kolumn ar timme 06-23.
4. Anvandaren valjer aktivitet i cellens dropdown, delar cell i halvtimmar vid behov, drar for att fylla flera celler eller anvander copy/paste.
5. Summering och bemanningskalkyl uppdateras efter andringar.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Ar | Valjer ISO-ar | Uppdaterar state och laddar nytt schema | `loadSchedule`, `GET /api/schedule` | Ogiltigt ar faller tillbaka till tidigare state. |
| Vecka | Valjer ISO-vecka 1-53 | Uppdaterar datum och laddar schema | `dateFromYWD`, `loadSchedule` | Fel vecka ger "fel dag" om anvandaren forvantar kalenderdatum. |
| Dag | Valjer mandag-sondag | Uppdaterar veckodag och datum | `onControlChange` | Dag ar ISO-veckodag, inte datum. |
| Datumfalt | Valjer exakt datum | Raknar om ar/vecka/dag och laddar schema | `onDateChange` | Om datum hoppar beror det pa ISO-vecka. |
| Foregaende/nasta dag | Klick pa pilar | Flyttar datum en dag | `stepDay(-1/1)` | Sparar valt datum i `sessionStorage`. |
| Omradesfokus i sidebar | Valjer MG/GG/AS/EH eller Alla | Friskar upp tillgangliga omraden fran sidans `/api/areas`-svar, faller tillbaka till Alla om sparat omrade inte langre finns, och visar cachat all-data eller exakt omradescache nar det finns | `setAreaFocusAreas`, `flow:areaFocusChanged`, `filterScheduleDataForArea`, `prefetchAllSchedule` | `∞` betyder alla synliga omraden; for Super User kan det vara globalt enligt verksamhetsscope. |
| Ovre horisontell scrollbar | Drar tabellen i sidled ovanfor matrisen | Synkar med tabellens vanliga scroll nederst | `setupSyncedHorizontalScroll` | Visas bara nar tabellen ar bredare an ytan. |
| Kopiera dag | Oppnar modal | Kopierar schema fran dag till dag | `POST /api/schedule/copy` | Overskrivning sker bara om checkboxen i modalen ar vald. |
| Rensa dag | Bekraftar med `confirm` | Rensar valt schema/omrade | `POST /api/schedule/clear` | Read-only kan inte rensa. |
| Undo | Angrar senaste lokala schemaandring | Restore av tidigare snapshot | `PUT /api/schedule/hours/restore` | Fungerar bara pa samma dag som andringen gjordes. |
| Redo | Gor om senaste angring | Restore av efter-snapshot | `PUT /api/schedule/hours/restore` | Knappen ar disabled nar redo-stack ar tom. |
| Narvarande | Valjer Alla omraden eller nuvarande omrade och skriver ut | Hamtar narvarolista for vald dag/timme, grupperar Alla per verksamhet och oppnar printdialog | `GET /api/schedule/presence`, `presence_print.js` | Tom lista visas som varning; Windows-appen anvander desktop-printbrygga. |
| Personfilter | Skriver i Person-huvud | Filtrerar synliga rader klient-side | `refreshPersons` | Shift-klick pa header sorterar i stallet. |
| Sortera Person/Hemomrade | Klick pa header | Sorterar rader | `th[data-sort]` | Personheadern har filterinput; klick i input sorterar inte. |
| Dra personnamn | Drar ett namn upp eller ned | Sparar ny personsortering direkt pa personernas `sort_order` | `PUT /api/persons/sort-order` | Kraver `personSortOrder=edit`. Bemanningsansvarig/admin ar begransade till eget omrade; Super User och demo kan sortera alla synliga personer. Rensa personfilter innan sortering. |
| Cell-dropdown | Valjer aktivitet/tomt | Sparar segment direkt | `PUT /api/schedule/cell` | 409 betyder att nagon annan hann andra cellen. |
| Hogerklick cell | Delar hel timme eller slar ihop | Kallar split-endpoint | `PUT /api/schedule/cell/split` | Konflikt om segmentsignatur inte matchar servern. |
| Dubbelklick cell | Alternativ split/merge | Samma som hogerklick | `toggleHourSplit` | I read-only visas varning. |
| Drag over celler | Fyller markerat omrade med kallcellens aktivitet | Bulk-sparar upp till 200 celler/halvor | `POST /api/schedule/cells` med `action=drag_fill` | Lasta celler hoppas over eller ger konflikt. |
| Ctrl+C | Kopierar fokuserad cell/halva | Lagrar aktivitet i lokal clipboard | `copyFocused(false)` | Kraver fokuserad cell. |
| Ctrl+X | Klipper fokuserad cell/halva | Kopierar och tommer kallsegment | `copyFocused(true)`, `PUT /api/schedule/cell` | Kan fa konflikt om cellen andrats. |
| Ctrl+V | Klistrar in | Satter fokuserad cell/halva | `pasteFocused`, `PUT /api/schedule/cell` | Fungerar inte utan kopierat varde och fokus. |
| Bemanningskalkyl | Fyller rader/tid/mal | Raknar behov, timmar och diff klient-side for valt omradesfokus; `∞` visar alla paneler | `calcMetrics` | Decimaler normaliseras enligt svensk input. |

## Kopiera dag-modal

Falt:

- Fran ar, vecka, dag.
- Till ar, vecka, dag.
- Checkbox "Skriv over befintliga celler i malet".
- `Avbryt` stanger utan API.
- `Kopiera` skickar payload till `/api/schedule/copy`.

## Viktiga tekniska regler

- Varje explicit cell/segment har `version`.
- Klienten skickar aktuell version som `expected_version`.
- Vid konflikt returnerar API `409`; klienten visar toast och laddar om dagen.
- Om en person har fast veckomall visas standardaktivitet aven utan explicit cell.
- Om anvandaren tommer en malltimme skapas explicit tom override.
- `lock_foreign_schedule_cells` kan hindra ledare fran att andra celler skapade av annan anvandare.
- Bemanning cachar bara API-svar som redan ar synliga for inloggad anvandare och aktuell verksamhet. Nar cache saknas prioriterar klienten all-data for hela dagen/verksamheten, filtrerar vald area lokalt och fyller bade all-cache och exakt omradescache innan anvandaren togglar vidare. Cachen ogiltigforklaras vid cellandring, split/merge, drag, undo/redo, rensa och kopiera dag sa omradestoggle inte visar gamla data.
- Om ett sparat omradesfokus pekar pa ett omrade som har tagits bort, till exempel ett gammalt `AREA:<id>` i browsern, normaliseras fokus till Alla innan Bemanning skickar API-anrop. Det skyddar mot 404 `Omrade hittades inte` och mot att vyn ser tom ut efter registerandringar.
- Nar en period finns i cache kontrollerar klienten `/api/schedule/revision` tyst i bakgrunden. Aktiv vy kontrollerar ungefär var 10:e sekund, idle-vy ungefär var 30:e sekund, och dold browserflik pausar. Vid ny revision hamtas all-data och bara andrade synliga timmar patchas om anvandaren inte haller pa i just den cellen.
- `Narvarande` raknar pa effektiv bemanning fran vald dag och aktuell klocktimme. En person kommer med om personen har nagon icke-franvaroaktivitet kvar under dagen och har `work` denna eller nasta timme. Nuvarande aktivitet visar bara aktuell timme; om personen tas med tack vare nasta timme visas `Ingen` nar aktuell timme saknar aktivitet.
- Nar anvandaren valjer Alla omraden grupperas utskriften per verksamhet sa Super User inte far blandade verksamheter i samma lista.
- `fill-from-left` finns som API (`POST /api/schedule/fill-from-left`) men har ingen synlig knapp i nuvarande `index.html`/`schedule.js`.
- Personnamn kan dras for att andra personernas sorteringsnummer. Klienten skickar hela synliga ordningen till `/api/persons/sort-order`; backend nekar andra roller, filtrerade/forandrade personlistor och, for vanliga admin/bemanningsansvariga, personer med annat hemomrade. Super User och demo far sortera over omradesgranser nar de har `Personsortering=Redigera`.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor kan jag inte andra cellen?" | Kontrollera om anvandaren ar i visningslage, om cellen ar last av annan anvandare, eller om sidan visade konflikt-toast. |
| "Varfor forsvann min andring?" | Troligen versionskonflikt: nagon annan sparade samma cell forst. Sidan laddar om serverns varde. |
| "Varfor ar undo disabled?" | Det finns ingen lokal andring i undo-stacken for aktuell session/dag. |
| "Varfor fungerar inte Ctrl+C/V?" | En schemacell eller halva maste vara fokuserad forst. |
| "Hur delar jag en timme?" | Hogerklicka eller dubbelklicka pa timcellen. Välj aktivitet for varje halvtimme. |
| "Var ar Fyll fran vanster?" | Backend-endpointen finns, men nuvarande UI visar ingen knapp for den funktionen. |
| "Varfor kan jag inte dra namnet for att sortera?" | Anvandaren maste ha `Personsortering=Redigera`. Bemanningsansvarig/admin maste ha samma omrade som personens hemomrade; Super User och demo kan sortera alla synliga personer. Rensa personfiltret om det ar aktivt. |
| "Varfor sag Bemanning tom ut efter att ett omrade togs bort?" | Browsern kan ha haft ett gammalt omradesfokus sparat. Nu faller sidan tillbaka till Alla nar det sparade omradet inte langre finns. Kontrollera Historik efter 404 `Omrade hittades inte` om felet hande innan fixen. |

## Kallor

- `../app/frontend/index.html`
- `../app/frontend/js/schedule.js`
- `../app/frontend/js/presence_print.js`
- `../app/backend/routers/schedule.py`
- `../app/backend/routers/bulk.py`
- `../app/backend/schedule_locks.py`

---
title: Bemanning
status: aktiv
updated: 2026-06-11
tags: [bemanning, schema, ui, knappar]
---

# Bemanning

Kort svar: Bemanning ar huvudmatrisen. Anvandaren valjer ar/vecka/dag och styr omrade med omradesfokus i sidebar. Sedan satter anvandaren aktivitet per person och timme. Andringar sparas direkt till `/api/schedule/*` med versionsskydd.

## Anvandarflode

1. Sidan laddar omraden och aktiviteter.
2. Sidan laddar hela schemadagen for aktuell verksamhet och filtrerar valt omradesfokus direkt i klienten. En person syns i valt omrade om personen har hemomradet dar, har en schemacell den dagen med en aktivitet som tillhor omradet, eller har en tom lanemarkering (`loan_area_id`) till omradet. Om perioden redan finns i lokal all-cache eller exakt omradescache ritas den utan nytt API-anrop.
3. Varje rad ar en person; fasta kolumner visar person, hemomrade och dagens
   produktivitet, och timkolumnerna visar 06-23.
4. Anvandaren valjer aktivitet i cellens dropdown, delar cell i 2-4 minutdelar vid behov, drar for att fylla flera celler eller anvander copy/paste.
5. Summering och bemanningskalkyl uppdateras efter andringar.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Ar | Valjer ISO-ar | Uppdaterar state och laddar nytt schema | `loadSchedule`, `GET /api/schedule` | Ogiltigt ar faller tillbaka till tidigare state. |
| Vecka | Valjer ISO-vecka 1-53 | Uppdaterar datum och laddar schema | `dateFromYWD`, `loadSchedule` | Fel vecka ger "fel dag" om anvandaren forvantar kalenderdatum. |
| Dag | Valjer mandag-sondag | Uppdaterar veckodag och datum | `onControlChange` | Dag ar ISO-veckodag, inte datum. |
| Datumfalt | Valjer exakt datum | Raknar om ar/vecka/dag och laddar schema | `onDateChange` | Om datum hoppar beror det pa ISO-vecka. |
| Foregaende/nasta dag | Klick pa pilar | Flyttar datum en dag | `stepDay(-1/1)` | Sparar valt datum i `sessionStorage`. |
| Omradesfokus i sidebar | Valjer aktiva omraden fran `/api/areas` eller `∞` nar behorighet/ANNAT tillater det | Friskar upp tillgangliga omraden fran sidans `/api/areas`-svar, normaliserar sparat omrade till ett giltigt databasval och visar cachat all-data eller exakt omradescache nar det finns | `setAreaFocusAreas`, `flow:areaFocusChanged`, `filterScheduleDataForArea`, `prefetchAllSchedule` | Om `/api/areas` misslyckas blir toggleknappen disabled med feltext; gamla Stigamo-varden anvands inte som fallback. |
| Ovre horisontell scrollbar | Drar tabellen i sidled ovanfor matrisen | Synkar med tabellens vanliga scroll nederst | `setupSyncedHorizontalScroll` | Visas bara nar tabellen ar bredare an ytan. |
| Kopiera dag | Oppnar modal | Kopierar schema fran dag till dag | `POST /api/schedule/copy` | Overskrivning sker bara om checkboxen i modalen ar vald. |
| Rensa dag | Bekraftar med `confirm` | Rensar valt schema/omrade | `POST /api/schedule/clear` | Read-only kan inte rensa. |
| Undo | Angrar senaste lokala schemaandring | Restore av tidigare snapshot | `PUT /api/schedule/hours/restore` | Fungerar bara pa samma dag som andringen gjordes. |
| Redo | Gor om senaste angring | Restore av efter-snapshot | `PUT /api/schedule/hours/restore` | Knappen ar disabled nar redo-stack ar tom. |
| Narvarande | Valjer Alla omraden eller nuvarande omrade och skriver ut | Ligger fore Undo/Redo, hamtar narvarolista for vald dag/timme, grupperar Alla per verksamhet och oppnar printdialog | `GET /api/schedule/presence`, `presence_print.js` | Tom lista visas som varning; Windows-appen anvander desktop-printbrygga. |
| Summering per aktivitet | Laser aktiviteternas timmar efter planering | Visar heltal utan decimaler och icke-heltal med upp till tva decimaler, till exempel `1`, `1.5` eller `1.28` | `renderSummaryRows`, `formatHours`, `GET /api/schedule/summary` | Om en delad cell har udda minuter syns decimaler i stallet for avrundat heltal. |
| V+H | Visar eller doljer historiskt snitt i cellernas aktivitetsnamn | Hamtar personens forvantade enheter per timme for valda V+H-aktiviteter fran materialiserad personproduktivitet och visar till exempel `GG Plock(70)` nar laget ar pa | `GET /api/schedule/activity-capacity`, `activityLabelWithCapacity` | Tom parentes visas aldrig. Om aktiviteten inte ar vald i Installningar, eller om personen saknar historik for aktiviteten, visas bara aktivitetsnamnet. |
| Personfilter | Skriver i Person-huvud | Filtrerar synliga rader klient-side | `refreshPersons` | Shift-klick pa header sorterar i stallet. |
| Produktivitet-kolumn | Laser procenten bredvid hemomradet | Hamtar en liten sammanfattning fran `/api/schedule/productivity-summary` for valt datum och raknar bara avslutade KPI-timmar. For idag exkluderas pagaende timme; STOD/absence ger tom cell om ingen avslutad KPI-tid finns. Procenten visas som heltal och fargas rod under 80, orange 80-99 och gron fran 100. | `loadScheduleProductivity`, `buildScheduleProductivityMapFromSummary` | Tom cell betyder att produktivitetsrapport saknas eller att personen inte har avslutad KPI-tid i perioden. |
| Klick pa personrad | Klickar pa namn, hemomrade eller en timcell | Markerar hela personraden diskret i aktuell vy | `selectPersonRow`, `person-row-selected` | Markeringen ar bara visuell och sparas inte i databasen. |
| Sortera Person/Hemomrade | Klick pa header | Sorterar rader | `th[data-sort]` | Personheadern har filterinput; klick i input sorterar inte. |
| Dra personnamn | Drar ett namn upp eller ned | Sparar ny personsortering direkt pa personernas `sort_order` | `PUT /api/persons/sort-order` | Kraver `personSortOrder=edit`. Bemanningsansvarig/admin ar begransade till eget omrade; Super User och demo kan sortera alla synliga personer. Rensa personfilter innan sortering. |
| Hogerklick personnamn | Valjer `Skicka till <omrade>` | Bevarar personens tidigare timmar och gor personens schemalagda timmar fran aktuell eller fokuserad starttimme och framat tomma i malomradet, utan att andra personens hemomrade | `POST /api/schedule/cells` med `action=loan_to_area`, `activity_id=null`, `loan_area_id=<omrade>` | Visas bara som andring om personen har schematimmar/explicita celler fran starttimmen. Om starttimme inte kan avgoras visas varning i stallet for att tomma fran morgonen. Lasta celler hoppas over och read-only far varning. |
| Cell-dropdown | Valjer aktivitet/tomt | Sparar segment direkt | `PUT /api/schedule/cell` | 409 betyder att nagon annan hann andra cellen. |
| Hogerklick cell | Oppnar cellens aktivitetsval | Fokuserar vald timme/del och visar dropdown om browsern tillater det | `openFullHourSelect`, `openSplitSegmentSelect` | Read-only eller last cell visar varning. |
| Dubbelklick cell | Delar hel timme eller slar ihop delad timme | Vid hel timme oppnas `Dela timme` med toggle for `1/2`, `1/3` och `1/4`. `1/2` har `30` forifyllt och markerat. `1/3` har minutstarterna `20` och `40`, och `1/4` har `15`, `30`, `45`. Enter fortsatter med forifyllda eller inskrivna stigande minutstarter. | `requestScheduleSplitMinutes`, `toggleHourSplit`, `PUT /api/schedule/cell/split` | I read-only visas varning. Minutstarter maste vara stigande heltal mellan 1 och 59 och skapa 2-4 sammanhangande delar. |
| Drag over celler | Fyller markerat omrade med kallcellens aktivitet | Bulk-sparar upp till 200 celler/delar | `POST /api/schedule/cells` med `action=drag_fill` | Lasta celler hoppas over eller ger konflikt. |
| Ctrl+C | Kopierar fokuserad cell/del | Lagrar aktivitet i lokal clipboard | `copyFocused(false)` | Kraver fokuserad cell. |
| Ctrl+X | Klipper fokuserad cell/del | Kopierar och tommer kallsegment | `copyFocused(true)`, `PUT /api/schedule/cell` | Kan fa konflikt om cellen andrats. |
| Ctrl+V | Klistrar in | Satter fokuserad cell/del | `pasteFocused`, `PUT /api/schedule/cell` | Fungerar inte utan kopierat varde och fokus. |
| Bemanningskalkyl `Manuell` | Fyller rader/tid/mal | Raknar behov, timmar och diff klient-side. Det finns alltid exakt en manuell kalkyl, aven i Alla-lage. | `calcMetrics` | Decimaler normaliseras enligt svensk input. |
| Plus i Bemanningskalkyl | Lagger till automatisk kalkyl | Oppnar dialog med Namn, Process, Bolag, Zon och Plockdagar. Dialogen stangs bara via `Avbryt` eller `Spara`, inte av klick utanfor rutan. Sparas personligt per anvandare. | `GET/PUT /api/schedule/calculator-profile` | Kraver namn, process, bolag och zon. |
| Hamta fran anvandare | Soker och valjer anvandare | Kopierar den anvandarens automatiska bemanningskalkyler till aktuell anvandare | `POST /api/schedule/calculator-profile/import` | Visar bara anvandare inom atkomligt scope som har sparade kalkyler. |

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
- Implicita malltimmar galler bara fran personens skapandedatum och framat. Gamla datum fore `persons.created_at` visar inga standardtimmar for personen, men explicita schemaceller visas fortfarande.
- Om anvandaren tommer en malltimme skapas explicit tom override.
- `lock_foreign_schedule_cells` kan hindra ledare fran att andra celler skapade av annan anvandare.
- Bemanning cachar bara API-svar som redan ar synliga for inloggad anvandare och aktuell verksamhet. Nar cache saknas prioriterar klienten all-data for hela dagen/verksamheten, filtrerar vald area lokalt och fyller bade all-cache och exakt omradescache innan anvandaren togglar vidare. Cachen ogiltigforklaras vid cellandring, split/merge, drag, undo/redo, rensa och kopiera dag sa omradestoggle inte visar gamla data.
- Om en person med hemomrade GG/AS/EH tilldelas en MG-aktivitet syns personen bade i sitt hemomrade och i MG-vyn for den dagen. Samma regel galler tomma lanemarkeringar: `loan_area_id` gor personen synlig i mottagande omrade utan att skapa aktivitetstimmar.
- Produktivitetskolumnen anvander `/api/schedule/productivity-summary` i stallet
  for hela Produktivitetens dagrapport. Backend laser materialiserade
  `person_productivity_daily`-cellrader: bara `kind=kpi` och slut fore
  cutoff-tiden ingar. For dagens datum ar cutoff startminuten for aktuell timme,
  sa 11:17 raknar till och med 10:59. Den visade procenten ar
  `floor(poang / planpoang * 100)`.
- Summeringen for ett lanat omrade raknar bara de explicita celler som faktiskt har aktivitet i valt omrade. Tomma lanemarkeringar raknas inte som aktivitet, men de tacker malltimmen sa personens hemomradesmall inte raknas in i fel omradessummering.
- Hogerklick pa personnamnet ar en snabbvag for laneregeln. Menyn visar aktiva omraden i personens verksamhet. Nar anvandaren skickar personen skapar klienten tomma schemaceller fran aktuell timme, eller fokuserad timme om dagen inte ar idag, och framat med `loan_area_id` for malomradet; mottagande omrade valjer sedan aktivitet sjalv. Om klienten inte kan avgora starttimmen stoppas flodet med varning sa tidigare timmar inte toms av misstag.
- Om ett sparat omradesfokus pekar pa ett omrade som har tagits bort, till exempel ett gammalt `AREA:<id>` i browsern, normaliseras fokus till Alla innan Bemanning skickar API-anrop. Det skyddar mot 404 `Omrade hittades inte` och mot att vyn ser tom ut efter registerandringar.
- Nar en period finns i cache kontrollerar klienten `/api/schedule/revision` tyst i bakgrunden. Aktiv vy kontrollerar ungefär var 10:e sekund, idle-vy ungefär var 30:e sekund, och dold browserflik pausar. Vid ny revision hamtas all-data och bara andrade synliga timmar patchas om anvandaren inte haller pa i just den cellen.
- `Narvarande` raknar pa effektiv bemanning fran vald dag och aktuell klocktimme. En person kommer med om personen har nagon icke-franvaroaktivitet kvar under dagen och har `work` denna eller nasta timme. Nuvarande aktivitet visar bara aktuell timme; om personen tas med tack vare nasta timme visas `Ingen` nar aktuell timme saknar aktivitet.
- Nar anvandaren valjer Alla omraden grupperas utskriften per verksamhet sa Super User inte far blandade verksamheter i samma lista.
- `V+H` ar en valfri visning for historiskt kapacitetssnitt i bemanningscellerna. Laget sparas i browserns `localStorage`. Nar det ar pa hamtar klienten `/api/schedule/activity-capacity` for vald ISO-dag och visar `Aktivitet(snitt)`, till exempel `GG Plock(70)`, bara for aktiviteterna som ar valda under `Installningar > Bemanning`.
- Kapacitets-API:t anvander aktivitetens `kpi_process_name`, senaste KPI-mal och `kpi_target_rule` for att avgora om processen ska raknas i rader, kolli/paket, pallar eller order. Snittet laser materialiserade processrader i `person_productivity_daily`. Om en historikdag saknar cache byggs den en gang fran global snapshot och ateranvands sedan. Gransen styrs av `staffing_history_hours`, har default 40 timmar och anvands aven av automatisk bemanningskalkyl. Vilka aktiviteter som far visa parentesvarden styrs av `staffing_activity_capacity_activity_ids`: `null` betyder alla KPI-aktiviteter, en lista betyder bara dessa och en tom lista betyder inga.
- `fill-from-left` finns som API (`POST /api/schedule/fill-from-left`) men har ingen synlig knapp i nuvarande `index.html`/`schedule.js`.
- Personnamn kan dras for att andra personernas sorteringsnummer. Klienten skickar hela synliga ordningen till `/api/persons/sort-order`; backend nekar andra roller, filtrerade/forandrade personlistor och, for vanliga admin/bemanningsansvariga, personer med annat hemomrade. Super User och demo far sortera over omradesgranser nar de har `Personsortering=Redigera`.
- Klick pa en personrad markerar raden diskret med `person-row-selected`. Det ar bara ett lokalt visuellt hjalpmedel for att folja en rad over manga timmar och paverkar inte schema, filter eller sparning.
- Automatiska bemanningskalkyler sparas i `staffing_calculator_profiles` per anvandare. Profilen innehaller bara anvandarens automatiska kalkyler; den manuella `Manuell`-panelen ar fast UI och sparas inte per omrade.
- Automatisk kalkyl hamtar `Detalj Kundorder (Alla)` via workflow-kallan `orders` och filtrerar `line_status < 34`, `company=<Bolag>`, `pick_zone=<Zon>` och `order_date=today - Plockdagar`. Exempel: Plockdagar `1` betyder gardagens orderdatum, `0` idag och `-1` morgondagens datum.
- Om Emir ber om `Avancerad filfiltrering` pa filerna/underlagen i nya bemanningskalkylen betyder det Bearbetas filterdialog-monster: per fil/API-kalla, flera villkor, API/Uppladdning-val, personlig sparning och hamta/kopiera fran annan anvandare. Det ska inte tolkas som dagens enkla fasta falt for Bolag, Zon och Plockdagar.
- For automatisk prognos raknas schemalagd tid fran forsta ej paborjade halvtimme. Vid 11:17 borjar berakningen pa 11:30. Varje kvarvarande persons snitt hamtas fran personens senaste schemalagda timmar pa samma KPI-process, enligt `staffing_history_hours` (default 40). Resultatet i UI ar bara `Rader kvar efter schemalagd tid`.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor kan jag inte andra cellen?" | Kontrollera om anvandaren ar i visningslage, om cellen ar last av annan anvandare, eller om sidan visade konflikt-toast. |
| "Varfor forsvann min andring?" | Troligen versionskonflikt: nagon annan sparade samma cell forst. Sidan laddar om serverns varde. |
| "Varfor ar undo disabled?" | Det finns ingen lokal andring i undo-stacken for aktuell session/dag. |
| "Varfor fungerar inte Ctrl+C/V?" | En schemacell eller del maste vara fokuserad forst. |
| "Hur delar jag en timme?" | Dubbelklicka pa timcellen, valj `1/2`, `1/3` eller `1/4`, justera minutstarterna vid behov och tryck Enter. Valj sedan aktivitet for varje del. |
| "Var ar Fyll fran vanster?" | Backend-endpointen finns, men nuvarande UI visar ingen knapp for den funktionen. |
| "Varfor kan jag inte dra namnet for att sortera?" | Anvandaren maste ha `Personsortering=Redigera`. Bemanningsansvarig/admin maste ha samma omrade som personens hemomrade; Super User och demo kan sortera alla synliga personer. Rensa personfiltret om det ar aktivt. |
| "Varfor hander inget nar jag skickar en person till omrade?" | Personen maste ha schemalagda timmar eller explicita celler fran aktuell/startad timme den dagen. Om alla celler ar lasta visas varning och inget skrivs. |
| "Varfor syns inga standardtimmar for en ny person bakat i tiden?" | Personen far implicit veckomall forst fran sitt skapandedatum. Det hindrar att nyanstallda raknas som schemalagda innan de lades till. |
| "Varfor sag Bemanning tom ut efter att ett omrade togs bort?" | Browsern kan ha haft ett gammalt omradesfokus sparat. Nu faller sidan tillbaka till Alla nar det sparade omradet inte langre finns. Kontrollera Historik efter 404 `Omrade hittades inte` om felet hande innan fixen. |
| "Varfor syns en person i tva omraden?" | Personen har sitt hemomrade i det ena omradet men ar tilldelad en aktivitet eller tom lanemarkering som tillhor det andra omradet. Det ar avsiktligt: personen ska synas dar arbetet sker eller ska planeras och dar personen hor hemma. |
| "Varfor ar Produktivitet tom i Bemanning?" | Personen har ingen avslutad KPI-timme i vald period, har bara STOD/absence hittills, saknar materialiserad produktivitetscache for dagen eller sa kunde `/api/schedule/productivity-summary` inte hamtas. |
| "Hur ser jag vad Erik brukar hinna pa aktiviteten?" | Klicka `V+H` i Bemanning eller hall nere V och H samtidigt. Celler med historik visar aktiviteten med snitt i parentes, till exempel `GG Plock(70)`, om aktiviteten ar vald i `Installningar > Bemanning`. Klicka `V+H` igen for att dolja. |
| "Varfor far vissa celler ingen siffra efter V+H?" | Aktiviteten kan vara bortvald i `Installningar > Bemanning`, personen saknar positivt historiskt snitt for den aktivitetens KPI-process, aktiviteten saknar KPI-process, eller produktivitetssnapshots/KPI-mal saknas for historiken. |

## Kallor

- `../app/frontend/index.html`
- `../app/frontend/js/schedule.js`
- `../app/frontend/js/presence_print.js`
- `../app/backend/routers/schedule.py`
- `../app/backend/person_productivity_cache.py`
- `../app/backend/routers/bulk.py`
- `../app/backend/schedule_locks.py`
- `../app/backend/template_service.py`

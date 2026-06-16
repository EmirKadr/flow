---
title: Aktiviteter och omraden
status: aktiv
updated: 2026-06-15
tags: [aktiviteter, omraden, ui, import]
---

# Aktiviteter och omraden

Kort svar: Aktiviteter ar de valbara varden som bemanningsceller kan fa. Varje aktivitet har etikett, verksamhet, farg, omrade, KPI Mal/processnamn, kategori, arbetstyp, sortering och eventuell summeringsaktivitet. KPI Mal kan innehalla flera processnamn separerade med komma.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Ny aktivitet | Oppnar modal | Skapar aktivitet i aktuell eller vald verksamhet | `POST /api/activities` | Etikett kravs. |
| Flera nya aktiviteter | Oppnar tabellmodal | Skapar flera aktiviteter direkt i appen med samma falt som importmallen | `POST /api/activities/import-rows` | Dubbletter, okand verksamhet och okanda omraden/summeringar visas i resultatmodal. |
| Ladda ner importmall | Hamter Excelmall | Laddar ner mall | `GET /api/activities/import-template` | Dold utan `activityImport` edit. |
| Importera Excel | Oppnar filval | Importerar aktiviteter | `POST /api/activities/import` | Max 5 MB; dubblettkod stoppas. |
| Hjalp med import | Oppnar hjalpmodal | Visar importstod | `setupImportHelpButton` | Ingen serverkoppling. |
| Tabellrubriker | Klickar pa t.ex. Etikett, Verksamhet, Omrade, Kategori eller Sortering | Sorterar synliga aktivitetsrader stigande/fallande i klienten | `common.js` klienttabellsortering | Paverkar inte omradesfokus eller sparad sorteringsordning. |
| Redigera | Oppnar modal for befintlig aktivitet | Sparar andringar | `PUT /api/activities/{id}` | Kod kan vara read-only for icke-super-user. |
| KPI Mal-rullista | Bockar i en eller flera KPI-processer i aktivitetsmodalen | Hamter kanda processnamn fran KPI-mal, intern KPI-logik och befintliga aktiviteter och sparar dem kommaseparerat i `kpi_process_name` | `GET /api/activities/kpi-process-options`, `POST/PUT /api/activities` | Om listan inte kan hamtas visas varning; sparning stoppar fortfarande bolagsprefix och varden over 255 tecken. |
| Ta bort | Bekraftar | Inaktiverar aktivitet | `DELETE /api/activities/{id}` | Text sager permanent men beteendet ar soft delete. |

## Aktivitet-modal

Falt:

- Etikett: synligt namn i dropdowns och rapporter.
- Verksamhet: visas bara for Super User nar den inte kan harledas.
- Kod: visas/hanteras bara for anvandare som far se koder.
- Omrade: kopplar aktiviteten till MG/GG/AS/EH eller inget omrade.
- Summeras som: pekar pa annan aktivitet for summering.
- KPI Mal: multival-rullista med checkboxar for kanda processnamn fran KPI-malet, intern KPI-logik och befintliga aktiviteter. Valen sparas som kommaseparerade processnamn, t.ex. `dekant, plock`. Bolag skrivs inte i faltet.
- Farg: anvands i schema och oversikt.
- Kategori: `work` eller `absence`; VAS ska inte laggas som kategori.
- Arbetstyp: `Normal` eller `VAS`. VAS betyder Value Added Services men aktiviteten raknas fortfarande som arbete i schema och produktivitet.
- Sortering: ordning i listor/dropdowns.

Knappar:

- `Avbryt`: stanger utan sparning.
- `Spara`: skickar `POST`/`PUT`.

KPI-rullistan ar read-only metadata. Sjalva skapandet/uppdateringen audit-loggas fortsatt som `activity/create` eller `activity/update`; att bara hamta processlistan skapar ingen sparad audit-rad.

## Omraden

Omraden finns som egen backendresurs (`/api/areas`). Super User administrerar dem under `verksamheter.html`, dar varje verksamhet visar sina omraden. `stallen.html` ar legacy-redirect till `aktiviteter.html`.

`DELETE /api/areas/{area_id}` ar tryggt: tomma omraden hardraderas, men om ett omrade redan anvands av personer, aktiviteter eller anvandare inaktiveras det i stallet.

Omradesfokus i sidebar filtrerar aktivitetslistan per omrade. `∞` visar alla aktiviteter. Nar en ny aktivitet skapas forvalt valt omradesfokus som aktivitetens omrade, men anvandaren kan fortfarande andra omradet i modalen eller valja inget omrade.

## Summeringsaktivitet

`summary_activity_id` gor att en aktivitet kan raknas som en annan i summeringar. Backend ska hindra loopar. Om summering verkar konstig, kontrollera om aktiviteten summeras som annan aktivitet.

## Importregler

- Direktimporten `Flera nya aktiviteter` har samma falt som Excelmallen: verksamhet vid behov, etikett, omrade, summeras som, KPI Mal/processnamn, arbetstyp och sortering.
- Varje kolumn i direkttabellen visar om faltet ar `Obligatoriskt` eller `Frivilligt` i rubriken.
- Vanliga anvandare importerar alltid till egen verksamhet. Super User kan ange verksamhet med kod, namn eller id, eller lata omrade/summeringsaktivitet harleda den.
- KPI Mal ar bara processnamn. Flera processer separeras med komma och normaliseras till `dekant, plock`. Format med bolag, till exempel `GG:decanting`, stoppas eftersom verksamheten redan kommer fran aktiviteten.
- Importerade aktiviteter far vit standardfarg, kategori `work`, arbetstyp `normal` om inget annat anges, och aktiv status. Giltiga arbetstyper ar `normal` och `VAS`.
- Dubbletter i fil, i direkttabellen eller mot befintliga aktiviteter stoppas och visas i resultatmodalen.
- Befintliga aktiviteter fick initiala KPI Mal-processer via engangsmigrationen `0036_activity_kpi_backfill`. Den skapar inga nya aktiviteter och fyller bara tomma falt; efter det andrar anvandarna vardena fritt i Aktiviteter.
- Befintliga aktiviteter fick arbetstyp `normal` via migrationen `0038_activity_work_type`. Att markera en aktivitet som `VAS` andrar inte kategori eller work/absence-berakningar.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor ser jag inte kodkolumnen?" | Endast anvandare med ratt behorighet/super-user-lage ser eller far andra aktivitetskoder. |
| "Varfor kan jag inte skapa aktivitet?" | Anvandaren saknar edit-atkomst till `activities` eller etiketten saknas. |
| "Varfor syns inte KPI-processerna?" | Modalen hamtar dem via `GET /api/activities/kpi-process-options`. Om KPI-malet saknas anvands intern KPI-logik och befintliga aktivitetsvarden som fallback; om anropet misslyckas visas en varning. |
| "Varfor blir summeringen fel?" | Kontrollera `Summeras som`; aktiviteten kan vara mappad till annan summeringsaktivitet. |
| "Ska VAS vara kategori?" | Nej. Lat kategori vara `work` och satt Arbetstyp till `VAS`, sa bemanning och produktivitet fortfarande raknar aktiviteten som arbete. |
| "Varfor hittar jag inte Stallen?" | `stallen.html` redirectar till Aktiviteter. Begreppet har migrerats. |

## Kallor

- `../app/frontend/aktiviteter.html`
- `../app/frontend/stallen.html`
- `../app/frontend/js/activities.js`
- `../app/backend/routers/activities.py`
- `../app/backend/routers/areas.py`
- `../app/backend/productivity_kpi_rules.py`

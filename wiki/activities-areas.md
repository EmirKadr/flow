---
title: Aktiviteter och omraden
status: aktiv
updated: 2026-05-22
tags: [aktiviteter, omraden, ui, import]
---

# Aktiviteter och omraden

Kort svar: Aktiviteter ar de valbara varden som bemanningsceller kan fa. Varje aktivitet har etikett, farg, omrade, kategori, sortering och eventuell summeringsaktivitet.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Ny aktivitet | Oppnar modal | Skapar aktivitet i aktuell eller vald verksamhet | `POST /api/activities` | Etikett kravs. |
| Flera nya aktiviteter | Oppnar tabellmodal | Skapar flera aktiviteter direkt i appen med samma falt som importmallen | `POST /api/activities/import-rows` | Dubbletter, okand verksamhet och okanda omraden/summeringar visas i resultatmodal. |
| Ladda ner importmall | Hamter Excelmall | Laddar ner mall | `GET /api/activities/import-template` | Dold utan `activityImport` edit. |
| Importera Excel | Oppnar filval | Importerar aktiviteter | `POST /api/activities/import` | Max 5 MB; dubblettkod stoppas. |
| Hjalp med import | Oppnar hjalpmodal | Visar importstod | `setupImportHelpButton` | Ingen serverkoppling. |
| Redigera | Oppnar modal for befintlig aktivitet | Sparar andringar | `PUT /api/activities/{id}` | Kod kan vara read-only for icke-super-user. |
| Ta bort | Bekraftar | Inaktiverar aktivitet | `DELETE /api/activities/{id}` | Text sager permanent men beteendet ar soft delete. |

## Aktivitet-modal

Falt:

- Etikett: synligt namn i dropdowns och rapporter.
- Verksamhet: visas bara for Super User nar den inte kan harledas.
- Kod: visas/hanteras bara for anvandare som far se koder.
- Omrade: kopplar aktiviteten till MG/GG/AS/EH eller inget omrade.
- Summeras som: pekar pa annan aktivitet for summering.
- Farg: anvands i schema och oversikt.
- Kategori: t.ex. work/annan kategori enligt UI.
- Sortering: ordning i listor/dropdowns.

Knappar:

- `Avbryt`: stanger utan sparning.
- `Spara`: skickar `POST`/`PUT`.

## Omraden

Omraden finns som egen backendresurs (`/api/areas`). Super User administrerar dem under `verksamheter.html`, dar varje verksamhet visar sina omraden. `stallen.html` ar legacy-redirect till `aktiviteter.html`.

`DELETE /api/areas/{area_id}` ar tryggt: tomma omraden hardraderas, men om ett omrade redan anvands av personer, aktiviteter eller anvandare inaktiveras det i stallet.

Omradesfokus i sidebar filtrerar aktivitetslistan per omrade. `∞` visar alla aktiviteter. Nar en ny aktivitet skapas forvalt valt omradesfokus som aktivitetens omrade, men anvandaren kan fortfarande andra omradet i modalen eller valja inget omrade.

## Summeringsaktivitet

`summary_activity_id` gor att en aktivitet kan raknas som en annan i summeringar. Backend ska hindra loopar. Om summering verkar konstig, kontrollera om aktiviteten summeras som annan aktivitet.

## Importregler

- Direktimporten `Flera nya aktiviteter` har samma falt som Excelmallen: verksamhet vid behov, etikett, omrade, summeras som och sortering.
- Vanliga anvandare importerar alltid till egen verksamhet. Super User kan ange verksamhet med kod, namn eller id, eller lata omrade/summeringsaktivitet harleda den.
- Importerade aktiviteter far vit standardfarg, kategori `work` och aktiv status.
- Dubbletter i fil, i direkttabellen eller mot befintliga aktiviteter stoppas och visas i resultatmodalen.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor ser jag inte kodkolumnen?" | Endast anvandare med ratt behorighet/super-user-lage ser eller far andra aktivitetskoder. |
| "Varfor kan jag inte skapa aktivitet?" | Anvandaren saknar edit-atkomst till `activities` eller etiketten saknas. |
| "Varfor blir summeringen fel?" | Kontrollera `Summeras som`; aktiviteten kan vara mappad till annan summeringsaktivitet. |
| "Varfor hittar jag inte Stallen?" | `stallen.html` redirectar till Aktiviteter. Begreppet har migrerats. |

## Kallor

- `../app/frontend/aktiviteter.html`
- `../app/frontend/stallen.html`
- `../app/frontend/js/activities.js`
- `../app/backend/routers/activities.py`
- `../app/backend/routers/areas.py`

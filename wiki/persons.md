---
title: Personer
status: aktiv
updated: 2026-05-25
tags: [personer, register, ui, import]
---

# Personer

Kort svar: Personer ar registret over alla planerbara personer. Sidan stoder ny person, import, inline-redigering, frivilligt WMS-anvandarnamn via `NoMan`, sortering/filter, mjuk borttagning och personlig veckomall.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Ny person | Oppnar modal | Skapar person med namn, frivilligt `NoMan`, hemomrade, huvudaktivitet, sortering och verksamhet for Super User | `POST /api/persons` | Namn kravs; dubblettnamn stoppas inom verksamheten. |
| Flera nya personer | Oppnar tabellmodal | Skapar flera personer direkt i appen med samma falt som importmallen | `POST /api/persons/import-rows` | Tomma rader ignoreras; dubbletter och okand verksamhet visas i resultatmodal. |
| Ladda ner importmall | Laddar Excelmall | Hamter mall | `GET /api/persons/import-template` | Knappen dolds utan importbehorighet. |
| Importera Excel | Oppnar filval | Skickar vald `.xlsx` | `POST /api/persons/import` | Max 5 MB; dubbletter stoppar import. |
| Hjalp med import | Oppnar hjalpmodal | Visar generell importhjalp | `setupImportHelpButton` | Ingen serverkoppling. |
| Sorteringsrubriker | Klick pa rubrik | Sorterar tabellen | `sortKey/sortAsc` | Bara klient-side. |
| Filterrad | Skriver soktext | Filtrerar tabellen | `passesFilter` | Kombinerar flera filter. |
| Klick pa Namn | Inline-redigera namn | Sparar vid blur/Enter | `PUT /api/persons/{id}` | Escape avbryter; tomt/dubblett kan nekas. |
| Klick pa NoMan | Inline-redigera WMS-anvandarnamn | Sparar frivilligt textfalt vid blur/Enter | `PUT /api/persons/{id}` | Tomt varde rensar faltet. Faltet anvands inte i planering eller forecast annu. |
| Klick pa Hemomrade | Inline-select | Sparar nytt hemomrade | `PUT /api/persons/{id}` | Omrade styr sort/fokus och standardplacering. |
| Klick pa Huvudaktivitet | Inline-select | Sparar huvudaktivitet | `PUT /api/persons/{id}` | Visas i schema som personens standardaktivitet. |
| Klick pa Sortering | Inline-number | Sparar sorteringsnummer | `PUT /api/persons/{id}` | Ctrl+Z kan angra senaste personandring. |
| Dra personnamn i Bemanning/Oversikt | Drar ett namn upp eller ned i planeringsvyn | Uppdaterar samma sorteringsnummer som visas i Personer | `PUT /api/persons/sort-order` | Kraver Personsortering=Redigera. Bemanningsansvarig/admin ar begransade till eget omrade; Super User och demo kan sortera alla synliga personer. |
| Schema | Oppnar veckomallmodal | Hamter/sparar personlig mall | `GET/PUT /api/persons/{id}/schedule` | Tider maste vara 06-24 och start < slut. |
| Ta bort | Bekraftar borttagning | Inaktiverar person | `DELETE /api/persons/{id}` | Texten sager "permanent", men backend anvander soft delete. |
| Ctrl+Z | Angrar senaste inline-personandring | Sparar snapshot tillbaka | `PUT /api/persons/{id}` | Galler lokal session. |

## Ny/redigera person-modal

Falt:

- Namn.
- NoMan, frivilligt WMS-anvandarnamn per person.
- Verksamhet, bara for Super User nar den inte kan harledas.
- Hemomrade.
- Huvudaktivitet.
- Sortering.

Knappar:

- `Avbryt`: stanger modal.
- `Spara`: validerar namn och skickar `POST` eller `PUT`.

## Veckomallmodal

Funktioner:

- Checkbox for timmis/fast schemamall (`has_fixed_schedule`).
- En rad per veckodag.
- Ledig-checkbox per dag.
- Fran/till-tider per dag.
- `Standard 07-16`: fyller standardtider i modalens rader.
- `Avbryt`: stanger utan sparning.
- `Spara`: skickar `PUT /api/persons/{id}/schedule`.

## Importregler

- Direktimporten `Flera nya personer` har samma falt som Excelmallen: verksamhet vid behov, namn, NoMan, hemomrade, huvudaktivitet och sortering.
- Varje kolumn i direkttabellen visar om faltet ar `Obligatoriskt` eller `Frivilligt` i rubriken.
- Excelimport matchar svenska och alternativa rubriker. `NoMan` ar frivilligt och sparas bara pa personen.
- Vanliga anvandare importerar alltid till egen verksamhet. Super User kan ange verksamhet med kod, namn eller id, eller lata omrade/aktivitet harleda den.
- Import skapar aktiva personer.
- Dubbletter i fil, i direkttabellen eller mot befintliga personer stoppar importen.
- Resultatmodal visar skapade och hoppade rader.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor syns inte importknapparna?" | Anvandaren saknar edit-atkomst till `personImport`. |
| "Varfor gick importen inte igenom?" | Kontrollera filstorlek/rubriker vid Excel, eller radfel och dubbletter i resultatmodalen vid direktimport. |
| "Vad anvands NoMan till?" | Det ar ett frivilligt WMS-anvandarnamn pa personen. Det sparas och kan importeras, men anvands inte av planering eller forecast annu. |
| "Varfor kan jag inte spara schema?" | Kontrollera att tider ligger 06-24, att Fran ar mindre an Till och att personen finns. |
| "Varfor forsvann personen?" | Ta bort inaktiverar personen. Hamta med `include_inactive=true` for att se den. |

## Kallor

- `../app/frontend/personer.html`
- `../app/frontend/js/persons.js`
- `../app/backend/routers/persons.py`
- `../app/backend/routers/person_schedules.py`

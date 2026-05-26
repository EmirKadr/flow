---
title: Oversikt
status: aktiv
updated: 2026-05-26
tags: [oversikt, ui, knappar]
---

# Oversikt

Kort svar: Oversikt visar Bemanning pa dag-niva i vecka eller manad. En cell representerar en persons dag och skriver/tommer hela dagen enligt personens veckomall.
Daghuvudena visar bade datum och ISO-vecka, till exempel `Vecka 21`, sa man ser veckobytet direkt aven i manadsvy.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Vy | Valjer Vecka eller Manad | Byter tabellhuvud/body och periodstate | `viewMode`, `load` | Manad doljer veckofaltet. |
| Foregaende/nasta | Klickar pilar | Flyttar vecka eller manad | `shiftPeriod` | Periodtyp beror pa vald vy. |
| Ar | Valjer ar | Laddar aktuell vecka/manad i nytt ar | `GET /api/overview` eller `/month` | ISO-vecka kan ligga over arsskifte. |
| Vecka | Valjer vecka | Laddar veckoversikt | `/api/overview` | Visas bara i veckovy. |
| Manad | Valjer manad | Laddar manadsoversikt | `/api/overview/month` | Visas bara i manadsvy. |
| Omradesfokus i sidebar | Valjer MG/GG/AS/EH eller Alla | Friskar upp tillgangliga omraden fran sidans `/api/areas`-svar, faller tillbaka till Alla om sparat omrade inte langre finns, och visar cachat all-data eller exakt omradescache nar det finns | `setAreaFocusAreas`, `flow:areaFocusChanged`, `filterOverviewDataForArea`, `prefetchAllOverview` | `∞` betyder alla synliga omraden; for Super User kan det vara globalt enligt verksamhetsscope. |
| Ovre horisontell scrollbar | Drar tabellen i sidled ovanfor oversikten | Synkar med tabellens vanliga scroll nederst | `setupSyncedHorizontalScroll` | Visas bara nar tabellen ar bredare an ytan. |
| Undo/Redo | Angra/gor om dagandringar | Restore av snapshots via schema-API | `/api/schedule/hours/restore` | Disabled om stacken ar tom eller read-only. |
| Narvarande | Valjer Alla omraden eller nuvarande omrade och skriver ut | Hamtar narvarolista fran Bemannings schema for vald/klickad dag, grupperar Alla per verksamhet och oppnar printdialog | `GET /api/schedule/presence`, `presence_print.js` | Tom lista visas som varning; Windows-appen anvander desktop-printbrygga. |
| Personfilter | Skriver soktext | Filtrerar personer klient-side | `refreshPersons` | Shift-klick pa header sorterar. |
| Dra personnamn | Drar ett namn upp eller ned | Sparar ny personsortering direkt pa personernas `sort_order` | `PUT /api/persons/sort-order` | Kraver `personSortOrder=edit`. Bemanningsansvarig/admin ar begransade till eget omrade; Super User och demo kan sortera alla synliga personer. Rensa personfilter innan sortering. |
| Dagcell-dropdown | Valjer aktivitet/tomt for hel dag | Skriver/tommer personens schematimmar for dagen | `POST /api/overview/day` | Om dagen ar blandad visas confirm innan overskrivning. |
| Drag over dagceller | Fyller flera dagar/personer | Skickar bulk-dagar | `POST /api/overview/days/bulk` | Max 100 celler. Fel per cell kan rapporteras. |

## Cellbetydelser

- En dominant aktivitet visas om hela dagens effektiva schema summeras till samma aktivitet.
- Blandad dag markeras som mixed.
- Ledig dag visas som off.
- Schemalagd tom dag visas med separat stil.
- Timmar visas som info i cellen.

## Viktiga regler

- Oversikt anvander både explicita celler och kvarvarande malltider.
- Heldagsandring anvander personens veckomall. Om personen saknar fast mall/timmis kan API stoppa andringen.
- Vid blandad dag fragar klienten innan den skriver over med ett enda varde.
- Drag skapar manga heldagsandringar och pushar undo-snapshot for de lyckade.
- Drag pa personnamn andrar inte bemanningsceller utan personernas sorteringsnummer i registret. Samma backendregel som Bemanning anvands: Bemanningsansvarig/admin sorterar eget omrade, medan Super User och demo sorterar alla synliga personer med `Personsortering=Redigera`.
- `Narvarande` anvander schemadagen, inte den aggregerade oversiktscellen. Klickad/fokuserad dag blir printdag; om ingen dag ar fokuserad anvands sidans valda datum/period. Alla omraden grupperas per verksamhet.
- Oversikt cachar bara API-svar som redan ar synliga for inloggad anvandare och aktuell verksamhet. Nar cache saknas prioriterar klienten all-data for hela veckan/manaden i verksamheten, filtrerar valt omrade lokalt och fyller bade all-cache och exakt omradescache innan anvandaren togglar vidare. Cachen ar separat for veckovy och manadsvy och ogiltigforklaras vid dagandring, drag och undo/redo.
- Om ett sparat omradesfokus pekar pa ett borttaget omrade normaliseras fokus till Alla innan Oversikt skickar API-anrop. Det hindrar att gamla browserstate ger 404 `Omrade hittades inte` eller en tom vy.
- Nar en period finns i cache kontrollerar klienten `/api/overview/revision` eller `/api/overview/revision/month` tyst i bakgrunden. Aktiv vy kontrollerar ungefär var 10:e sekund, idle-vy ungefär var 30:e sekund, och dold browserflik pausar. Vid ny revision hamtas all-data och bara andrade synliga dagceller patchas om anvandaren inte haller pa i just den cellen.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor far jag inte andra en dag?" | Anvandaren kan vara read-only, personen kan sakna fast schema, eller API nekade rollen. |
| "Vad betyder randig/blandad dag?" | Dagen innehaller flera aktiviteter eller segment och kan skrivas over med confirm. |
| "Varfor raknas inte timmis som ledig?" | Timmis utan fast mall betraktas inte som en standardledig dag for heldagsandring. |
| "Varfor visar Oversikt andra timmar an Bemanning?" | Kontrollera att samma ar/vecka/dag/omrade anvands och att malltider plus explicita celler raknas. |
| "Varfor gar det inte att sortera med drag?" | Personsortering kraver `Personsortering=Redigera`. Bemanningsansvarig/admin maste ha samma omrade som personens hemomrade; Super User och demo kan sortera alla synliga personer. Personfiltret maste vara tomt. |
| "Varfor sag Oversikt tom ut efter registerandring?" | Om ett tidigare valt omrade tagits bort kan gamla browserflikar ha skickat ett dodt `area_id`. Nu faller vyn tillbaka till Alla nar omradet saknas. |

## Kallor

- `../app/frontend/overblick.html`
- `../app/frontend/js/overview.js`
- `../app/frontend/js/presence_print.js`
- `../app/backend/routers/overview.py`
- `../app/backend/routers/schedule.py`
- `../APP_MIGRATION_PLAN.md`

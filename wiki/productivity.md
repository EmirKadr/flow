---
title: Produktivitet
status: aktiv
updated: 2026-06-14
tags: [produktivitet, kpi, ui, api-snapshot]
---

# Produktivitet

Kort svar: Produktivitet ar nu den tidigare oversiktsvyn, men med Produktivitets
befintliga menyplats, namn och ikon. Vyn visar globalt sparad
produktivitetsdata som ett fokuserbart trad for verksamhet, omrade,
aktivitet, person, timme och processpoang. Produktivitetsdata hamtas inte per
anvandare och laddas inte upp manuellt i vyn.

## Behorighet

Rollen behover minst `productivity=view` for att oppna Produktivitet och lasa
rapporterna. `productivity=edit` kravs bara for manuell drift/test-sync via
`POST /api/productivity/sync`. Den separata vyn/behorigheten
`productivityOverview` finns inte langre. Gamla `/oversikt-produktivitet.html`
ar borttagen och ska inte langre anvandas.

## Vad vyn visar

- Periodval for `Dag`, `Vecka`, `Manad` och `Ar`.
- Datum-/periodruta med foregaende/nasta. I daglage visas datumet, i veckolage
  visas `Vecka N`, i manadslage visas manadens namn och i arslage visas artalet.
- `Helbild`, som fokuserar tradet tillbaka till verksamhetsroten.
- `Exportera flowchart`, som oppnar en dialog for val av exportnivaer och
  laddar ner aktuell fokuserad vy som SVG.
- Noder for verksamhet, omrade, aktivitet, person, timme och processpoang.
- Barnnoder visas som en sammanhangande horisontell tradgren. Nar det finns
  manga barn scrollas tradytan i sidled i stallet for att bryta upp grenlinjen.
- Snittet visas som poang per arbetad timme med en decimal. Stodtid raknas som
  verklig arbetstid i tradets timmar och rullar upp till omrade/helbild, men
  en ren stodnod saknar egen KPI-tid och visar darfor `-` efter likhetstecknet.
  Fargskalan ar rod under 70, orange 70-79,9 och gron fran 80.
- Omradesnivan i tradet bygger pa schemacellens aktivitetomrade, inte
  personens hemomrade. En person med hemomrade Autostore som bemannas pa en
  GG-aktivitet ger darfor KPI-tid och poang under GG.
- En person med bara stodtid syns i tradet under stodaktiviteten med sina
  poang och timmar. Personens egen produktivitetsvy fortsatter daremot att
  visa bara KPI-aktiviteter.

Dagens datum raknas bara till och med senaste avslutade heltimme. Aldre datum i
vald period raknar hela dagen. Innevarande vecka, manad och ar klipps vid dagens
datum sa framtida dagar inte ingar.

## Global snapshot

Nar `DATA_SOURCE_*` och extern datakatalog ar konfigurerade ar serverns globala
API-snapshot primar sanning. Forsta startup-syncen fyller 13 dagar bakat plus
dagens datum. Efter det uppdateras dagens snapshot vid varje hel- och halvtimme
i Europe/Berlin-tid. En global historik-backfill hamtar sedan en aldre dag per
kalenderdag tills historiken ar fylld.

Servern lagrar snapshots under
`compiled_data_root()/productivity_snapshots/` som gzip-CSV plus metadata per
datum. Mappen ar global for programmet, inte per anvandare eller session. Gamla
dagsmappar rensas inte av produktivitetsflodet; dagens filer kan ersattas
atomiskt nar dagens data uppdateras, medan aldre datum ligger kvar.
`backfill.json` i samma rot sparar hur langt den langsamma historikhamtningen
har kommit.

Nar en vy behover snabba person-/dagssvar kan backend materialisera snapshoten
till `person_productivity_daily`. Det ar beraknad cache, inte masterdata pa
personen. Bemanningens cell-hover-snitt och produktivitetskolumn laser denna cache och bygger
om en dag nar snapshot- eller schemasignaturen andras.

Snapshoten innehaller kallorna:

| Nyckel | API-vy | Anvands till |
| --- | --- | --- |
| `pick` | `v_ask_pick_log_full` | Plockrader, kollin och helpallsregler |
| `trans` | `v_ask_trans_log` | Dekantering, HBW, buffer och pafyllnad |
| `pallet` | `v_ask_palletloading_log` / `LOADING_LOG` | Pack/pallastning |
| `receive` | `v_ask_receive_log` | Receiving och buffer update |
| `order_log` | `v_ask_order_log` | Orderlogg for KPI-regler som kopplar order till pall |
| `sort` | `sort_conveyor_log` | Sortering e-com/store |
| `base_pallet` | `v_ask_article_buffertpallet` | Base pallet-/buffertpallsunderlag |
| `kpi` | `v_ask_kpi_target` | KPI-mal och poangkolumner |

KPI-mal hamtas som API-kalla fran `v_ask_kpi_target`. Om just KPI-kallan inte
kan hamtas via API kan permanent KPI-coredata for verksamheten anvandas som
fallback i snapshotbygget. Snapshotens `source_status` visar da `kpi` med
`status=coredata_fallback`; nar API-felet ar kant skickas aven
`fallback_reason`, till exempel HTTP 403 om API-klienten saknar behorighet till
KPI-vyn.

KPI-malet fran `v_ask_kpi_target` ar den enda externa KPI-kallan som kravs for
poang. Hur loggrader klassificeras till processer och matt (rader, kolli,
pallar eller order) ligger i kodens interna standardlogik baserad pa
`referens/kpi.sql`. Det finns ingen anvandaruppladdad separat regelfil i
Produktivitet.

## API-kontrakt

- `GET /api/productivity` returnerar personbaserad dagrapport med `people[]`,
  `summary`, `sync`, `backfill`, `available_dates` och `source_status`.
- `GET /api/productivity/overview` returnerar periodpaketet som
  `produktivitet.html` anvander: `reports[]`, `period`, `summary`,
  `missing_dates`, `source_status`, `sync` och `backfill`. Endpointen laser
  befintliga snapshots for perioden och triggar inte extern historikhamtning vid
  varje periodbyte.
- `GET /api/productivity/persons/{person_id}` returnerar personens snitt per
  aktivitet for `period=week|month|year|custom`. Dagar som inte hunnit
  backfillas returneras i `missing_dates`.
- `GET /api/personal/productivity` anvander samma globala snapshotberakning for
  Min produktivitet, men personrollen far bara se sin egen kopplade person.
- `GET /api/schedule/productivity-summary` returnerar en mindre
  Bemanning-specifik personkarta fran `person_productivity_daily`.
- `POST /api/productivity/sync` kor manuell snapshot-sync for drift/test och
  kraver `productivity=edit`.

Produktivitetsfilroutes ar borttagna: det finns inte langre
`/api/productivity/files`, `/api/productivity/files/raw`,
`/api/productivity/files/{file_type}` eller `/api/productivity/targets`.
Produktivitet laddar inte heller `productivity.js` eller
`productivity_uploads.js`.

## Desktop

Windows-appen anvander central `/api/productivity`,
`/api/productivity/overview`, `/api/productivity/persons/{id}` och
`/api/schedule/productivity-summary` som sanning.
Den lokala desktop-proxyn har inte langre produktivitetsspecifika endpoints for
filregistrering eller produktivitetsfil-sync. Om central server inte kan nas
returnerar desktop-proxyn ett 503-svar som sager att rapporten kraver central
serverdata for schema och KPI-snapshot.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor |
| --- | --- | --- |
| Period | Valjer Dag, Vecka, Manad eller Ar | Hamtar periodpayload fran `/api/productivity/overview` |
| Datum-/periodruta | Valjer ankardatum for rapporten | Visar datum, vecka, manad eller ar beroende pa periodlage |
| Foregaende/nasta datum | Klickar pilar | Hoppar inom tillgangliga datum eller kalenderdagar |
| Helbild | Klickar knappen | Fokuserar tradet tillbaka till verksamhetsroten |
| Nod | Klickar verksamhet, omrade, aktivitet eller person | Flyttar fokus och visar nasta niva i hierarkin |
| Exportera flowchart | Klickar knappen, valjer nivaer och klickar Exportera | Laddar ner aktuell fokuserad vy som SVG med valda nivaer |

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor saknas dagar?" | Historik-backfillen har inte hunnit hamta alla datum an. Saknade dagar visas i `missing_dates`. |
| "Hamtas data varje gang jag oppnar en person?" | Nej. Persondialogen laser sparade globala snapshots och klienten cachar nyligen hamtade perioder kort. Om datum saknas beror det pa att backfill/snapshot inte ar klar. |
| "Varfor ska periodbyte i Produktivitet inte starta en stor API-korning?" | Periodbyte ska bara lasa de snapshots som redan finns. API-syncen sker vid startup, hel-/halvtimme, manuell sync eller historik-backfill. |
| "Varfor gar det inte att ladda upp produktivitetsfiler?" | Den manuella produktivitetsuppladdningen ar borttagen. Produktivitet bygger pa global API-snapshot. |
| "Vilken KPI-fil kravs for poang?" | `v_ask_kpi_target`/`kpi` kravs. Den gamla separata regelfilen anvands inte. |
| "Varfor kan desktop inte visa rapport offline?" | Den nya rapporten kraver central schema- och snapshotdata. |

## Kallor

- `../app/backend/productivity_kpi_rules.py`
- `../app/backend/productivity_sync.py`
- `../app/backend/routers/productivity.py`
- `../app/backend/workflow_data.py`
- `../app/frontend/produktivitet.html`
- `../app/frontend/js/productivity_overview.js`
- `../desktop/local_runtime.py`

---
title: Produktivitet
status: aktiv
updated: 2026-05-26
tags: [produktivitet, filer, kpi, ui]
---

# Produktivitet

Kort svar: Produktivitet analyserar stora lokala CSV-loggar i klienten och kombinerar dem med permanenta KPI-mal fran servern. KPI-malet ar en verksamhetsseparerad karnfil: Stigamo, R3 och framtida verksamheter har samma filtyp men egna data. Tre synliga loggar kravs lokalt: Plocklogg, Translogg och Palllastningslogg. Nar en sadan logg laddas upp uppdaterar backend samtidigt verksamhetens sammanstallda csv.gz-observationer for samma loggtyp. Atkomst styrs via Vybehorigheter for `productivity`, inte via hard Super User-krav.

## Behorighet

Rollen behover minst `productivity=view` for att oppna sidan och lasa status/KPI-mal. `productivity=edit` kravs for serverhanterade produktivitetsfiler, till exempel uppladdning eller rensning av permanent KPI-mal. Super User har fortfarande full atkomst automatiskt.

## Knappar och kontroller pa sidan

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Datum | Valjer rapportdatum | Renderar rapport for datumet | `loadProductivity`, lokal cache | Om filerna saknar datumet visas tom/ingen data. |
| Foregaende/nasta datum | Klickar pilar | Hoppar till narliggande datum som finns i datasetet | `shiftProductivityDate` | Disabled om inget fore/efter-datum finns. |
| Omradesfokus i sidebar | Valjer Alla/GG/AS/EH/MG | Filtrerar rapportsektioner; `∞` visar alla block | `flow:areaFocusChanged`, `preferredProductivityGroupFilter` | Om fel block visas, kontrollera togglen nere i sidebar. |
| Sok | Skriver text | Filtrerar sektioner/rader klient-side | `activeSearch`, `renderContent` | Sokningen ar lokal och paverkar inte datan. |
| Filkrav/dropzoner | Drar filer till kravslot | Sparar lokal fil i IndexedDB | `productivityUploads.saveFiles` | Okand filtyp om namn/header inte matchar. |
| Välj per filslot | Oppnar filval for viss filtyp | Sparar vald fil pa den sloten | IndexedDB `flow-productivity-files` | Vald fel fil kan klassas om targetKey anvands. |
| Rensa per filslot | Klick pa x | Tar bort lokal fil | `deleteFile` | KPI-mal ar permanent och kan inte rensas via x. |

## Filer och identifiering

| Nyckel | Label | Prefix/header-hints | Var sparas |
| --- | --- | --- | --- |
| `pick` | Plocklogg | `v_ask_pick_log_full`, headers `Zon`, `Plockat`, `Anvandare`, `Andrad`, `Bolag` | IndexedDB lokalt + `productivity_pick_observations` |
| `trans` | Translogg | `v_ask_trans_log`, headers `Pallid`, `Fran`, `Till`, `Antal`, `Timestamp` | IndexedDB lokalt + `productivity_trans_observations` |
| `pallet` | Palllastningslogg | `v_ask_palletloading_log`, headers `Plockpallsnr.`, `Palltyp`, `Pallplacering`, `Transnr.`, `Vikt` | IndexedDB lokalt + `productivity_pallet_observations` |
| `kpi` | KPI-mal | `v_ask_kpi_target`, headers `Flodesnamn`, `Processnamn`, `Beskrivning`, `Rader`, `Kollin` | Postgres/permanent verksamhetsdata |

## Sammanstallda loggar

Plocklogg, Translogg och Palllastningslogg har varsin sammanstalld csv.gz-fil i verksamhetens `data/coredata/<verksamhetskod>/`:

- `v_ask_pick_log_full_observations.csv.gz` for Plocklogg.
- `v_ask_trans_log_observations.csv.gz` for Translogg.
- `v_ask_palletloading_log_observations.csv.gz` for Palllastningslogg.

Flodet liknar `artikel_max.csv`: ny uppladdad logg bevaras lokalt for aktuell klient men skickas ocksa till `/api/productivity/files/raw`, dar backend lagger till nya observationer i den verksamhetsscopeade csv.gz-filen. Plocklogg dedupliceras pa `Radid` (katalogens kolumn-id `rowid`) och Translogg pa `Rowid`, inklusive dubbletter i samma upload. Palllastningslogg anvander i stallet en strikt timestamp-grans pa `Ändrad`/`timestamp`: bara rader nyare an senaste timestampen som redan finns laggs till. Nya palllastningsrader med samma timestamp i samma upload far vara dubbletter.

De tre sammanstallda filerna visas under `Sammanstalld data` i Uppladdningar och `/api/coredata/files`. De blandas aldrig mellan verksamheter.

## Karnfiler och verksamhet

- KPI-mal ar permanent serverdata och fungerar som produktivitetens karnfil.
- Backend laser och sparar nya KPI-mal via inloggad anvandares verksamhetskod i Postgres-tabellen `coredata_files`.
- Stigamo, R3 och nyare verksamheter far separata DB-rader per verksamhet och filtyp. Backend materialiserar KPI-raden till en temporar CSV-fil nar produktivitetsmotorn behover lasa den.
- En KPI-fil uppladdad for R3 ska aldrig anvandas for Stigamo, och tvartom.
- Stigamo kan lasa den gamla root-filen i `data/` som bakatkompatibel fallback om ingen Stigamo-scopead KPI-fil finns. Gamla `data/coredata/`-filer kan ocksa vara fallback tills en ny Postgres-rad finns.

## Berakningsgrupper

Rapporten grupperar bland annat:

- Granngarden: plockzon A/B och S.
- Autostore: butik plock AS, dekantering GG/MG.
- E-Handel: GG/MG E-handel plock och pack.
- Mestergruppen: plockzon A/B/N och O.

Vissa anvandare exkluderas hardkodat i frontend/backendlogik for specifika grupper.

## Tekniskt flode

1. `productivity_uploads.js` sparar synliga loggar lokalt i IndexedDB.
2. Samma loggfil skickas ocksa till `/api/productivity/files/raw`; backend uppdaterar ratt sammanstalld csv.gz-fil om filtypen ar Plocklogg, Translogg eller Palllastningslogg.
3. KPI-fil laddas upp via `/api/productivity/files/raw` och sparas som verksamhetens `kpi`-rad i Postgres.
4. `productivity.js` laser lokala filer radvis i browsern, bygger dataset och hamtar verksamhetens KPI-mal via `/api/productivity/targets`.
5. Rapport for vald dag byggs lokalt och cachas. Intilliggande datum kan forhamtas.
6. Backend har motsvarande service for serverklassning/status, permanenta KPI-mal och sammanstallda produktivitetsloggar.
7. Serverhanterade uppladdningar/rensningar via `/api/productivity/files*` auditloggas som `productivity_file` med filtyp, antal forsokta, antal sparade och antal okanda filer. Om uppladdningen kraschar innan svar loggas `upload_failed` med feltyp och eventuell HTTP-status. Privata filnamn sparas inte i auditloggen.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor raknas inte Produktivitet?" | Kontrollera att Plocklogg, Translogg, Palllastningslogg och permanent KPI-mal finns for anvandarens verksamhet. |
| "Varfor ar nasta/foregaende datum disabled?" | Datasetet har inget tillgangligt datum i den riktningen. |
| "Varfor kanner appen inte igen filen?" | Filnamnet maste matcha prefix eller header-raden maste innehalla forvantade kolumner. |
| "Varfor syns KPI inte som fil jag kan rensa?" | KPI-mal ar permanent serverdata for verksamheten, inte lokal loggfil. |
| "Varfor star det 0 nya rader for sammanstalld data?" | Loggen var igenkand, men alla rowid/timestamps fanns redan i verksamhetens sammanstallda fil. |
| "Varfor skiljer Produktivitet fran annan anvandares dator?" | De stora loggfilerna ar lokala per klient; KPI-mal ar gemensamt inom verksamheten. |

## Kallor

- `../app/frontend/produktivitet.html`
- `../app/frontend/js/productivity.js`
- `../app/frontend/js/productivity_uploads.js`
- `../app/backend/productivity_service.py`
- `../app/backend/coredata_service.py`
- `../app/backend/routers/productivity.py`

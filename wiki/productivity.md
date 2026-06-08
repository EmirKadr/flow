---
title: Produktivitet
status: aktiv
updated: 2026-06-08
tags: [produktivitet, filer, kpi, ui]
---

# Produktivitet

Kort svar: Produktivitet ar API-first nar extern datakalla ar konfigurerad. Webben hamtar da Plocklogg Full, Translogg, Pallastningslogg och KPI-mal via backend nar rapporten kors, och lokala filer anvands bara som fallback. Windows-appen hamtar samma temporara CSV-kallor via central server och faller tillbaka pa `localRef`/cache om API:t inte kan nas. KPI-malet ar fortsatt en verksamhetsseparerad karnfil i Postgres nar lokal fallback anvands. Nar en lokal logg laddas upp eller syncas uppdaterar backend samtidigt verksamhetens sammanstallda csv.gz-observationer for samma loggtyp. Atkomst styrs via Vybehorigheter for `productivity`, inte via hard Super User-krav.

## Behorighet

Rollen behover minst `productivity=view` for att oppna sidan och lasa status/KPI-mal. `productivity=edit` kravs for serverhanterade produktivitetsfiler, till exempel uppladdning eller rensning av permanent KPI-mal. Super User har fortfarande full atkomst automatiskt.

## Knappar och kontroller pa sidan

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Datum | Valjer rapportdatum | Renderar rapport for datumet | `loadProductivity`, lokal cache | Om filerna saknar datumet visas tom/ingen data. |
| Foregaende/nasta datum | Klickar pilar | Hoppar till narliggande datum som finns i datasetet | `shiftProductivityDate` | Disabled om inget fore/efter-datum finns. |
| Omradesfokus i sidebar | Valjer Alla/GG/AS/EH/MG | Filtrerar rapportsektioner; `∞` visar alla block | `flow:areaFocusChanged`, `preferredProductivityGroupFilter` | Om fel block visas, kontrollera togglen nere i sidebar. |
| Sok | Skriver text | Filtrerar sektioner/rader klient-side | `activeSearch`, `renderContent` | Sokningen ar lokal och paverkar inte datan. |
| Filkrav/dropzoner | Drar filer till kravslot | Webben sparar fil i IndexedDB; Windows sparar `localRef` och registrerar den hos desktop-servern | `productivityUploads.saveFiles`, `/api/desktop/productivity/files/register` | Okand filtyp om namn/header inte matchar. |
| Välj per filslot | Oppnar filval for viss filtyp | Sparar vald fil pa den sloten | IndexedDB `flow-productivity-files` | Vald fel fil kan klassas om targetKey anvands. |
| Rensa per filslot | Klick pa x | Tar bort lokal fil | `deleteFile` | KPI-mal ar permanent och kan inte rensas via x. |

## Filer och identifiering

| Nyckel | Label | Prefix/header-hints | Var sparas |
| --- | --- | --- | --- |
| `pick` | Plocklogg Full | `v_ask_pick_log_full`, headers `Zon`, `Plockat`, `Anvandare`, `Andrad`, `Bolag` | IndexedDB eller Windows `localRef` + `productivity_pick_observations` |
| `trans` | Translogg | `v_ask_trans_log`, headers `Pallid`, `Fran`, `Till`, `Antal`, `Timestamp` | IndexedDB eller Windows `localRef` + `productivity_trans_observations` |
| `pallet` | Pallastningslogg | `v_ask_palletloading_log`, headers `Plockpallsnr.`, `Palltyp`, `Pallplacering`, `Transnr.`, `Vikt` | IndexedDB eller Windows `localRef` + `productivity_pallet_observations` |
| `kpi` | KPI-mal | `v_ask_kpi_target`, headers `Flodesnamn`, `Processnamn`, `Beskrivning`, `Rader`, `Kollin` | Postgres/permanent verksamhetsdata |

## API-first och fallback

Nar `DATA_SOURCE_*` och extern datakatalog ar konfigurerade visar `/api/productivity/files` `api_first=true`, `ready=true` och filraderna som `Hamtas fran API`. Da behover anvandaren inte lagga in lokala loggfiler innan rapporten kors. `/api/productivity` hamtar hela vyerna utan MiniMax och utan radbegransning:

- `pick` -> `v_ask_pick_log_full`.
- `trans` -> `v_ask_trans_log`.
- `pallet` -> `v_ask_palletloading_log`.
- `kpi` -> `v_ask_kpi_target`.

Om API-hamtningen misslyckas anvands befintliga lokala filer i sessionen, Windows `localRef` eller KPI-cache som fallback. Om ingen fallback finns stoppas rapporten med en anvandartext som sager vilken fil som maste laddas upp. Rapportens svar och audit innehaller `source_status` med `api`, `upload_fallback`, `local_ref_fallback`, `missing` eller `optional_skipped`, men inte URL, headers, nycklar, request body, filnamn eller raddata.

## Sammanstallda loggar

Plocklogg Full, Translogg och Pallastningslogg har varsin sammanstalld csv.gz-fil per verksamhet. I produktion ligger de pa persistent disk via `PRODUCTIVITY_DATA_DIR` eller `MEDIA_STORE_ROOT/flow-data`; repo-vagen `data/coredata/<verksamhetskod>/` ar bara lokal/dev- eller legacy-fallback:

- `v_ask_pick_log_full_observations.csv.gz` for Plocklogg Full.
- `v_ask_trans_log_observations.csv.gz` for Translogg.
- `v_ask_palletloading_log_observations.csv.gz` for Pallastningslogg.

Flodet liknar `artikel_max.csv`: ny uppladdad logg bevaras lokalt for aktuell klient men skickas ocksa till `/api/productivity/files/raw`, dar backend lagger till nya observationer i den verksamhetsscopeade csv.gz-filen. Plocklogg Full dedupliceras pa `Radid` (katalogens kolumn-id `rowid`) och Translogg pa `Rowid`, inklusive dubbletter i samma upload. Pallastningslogg anvander i stallet en strikt timestamp-grans pa `Ändrad`/`timestamp`: bara rader nyare an senaste timestampen som redan finns laggs till. Nya pallastningsrader med samma timestamp i samma upload far vara dubbletter.

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

1. `productivity.js` fragar `/api/productivity/files`. Om svaret ar `api_first` anvands serverrapporten som primar vag.
2. `/api/productivity` hamtar `pick`, `trans`, `pallet` och `kpi` via den gemensamma workflow-resolvern och materialiserar temporara CSV-filer med katalogens kolumnordning.
3. `productivity_uploads.js` sparar synliga loggar lokalt i IndexedDB for webben eller som `localRef` i Windows nar fallback behovs.
4. Windows registrerar refsen hos desktop-servern. Full produktivitetsrapport via `/api/productivity` fangas lokalt; desktop-servern hamtar forst centrala workflow-kallor och bygger annars rapporten av filerna pa disk.
5. Samma loggfil syncas ocksa till `/api/productivity/files/raw` i bakgrundsko; backend uppdaterar ratt sammanstalld csv.gz-fil om filtypen ar Plocklogg Full, Translogg eller Pallastningslogg.
6. KPI-fil syncas via `/api/productivity/files/raw` och sparas som verksamhetens `kpi`-rad i Postgres. I Windows kan en nyvald KPI-ref anvandas direkt lokalt innan syncen ar klar.
7. Nar API-first inte ar aktivt laser webben lokala IndexedDB-filer radvis i browsern och hamtar verksamhetens KPI-mal via `/api/productivity/targets`.
8. Serverhanterade uppladdningar/rensningar via `/api/productivity/files*` auditloggas som `productivity_file`; rapportkorsningar auditloggas som `productivity_report` med sanerad `source_status`. Lokala Windows-korningar auditloggas som `desktop_local_run` med metadata, men utan lokala sokvagar, filnamn eller filinnehall.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor raknas inte Produktivitet?" | Om API-first ar aktivt: kontrollera feltexten for vilken extern kalla som inte gick att hamta. Om fallback kravs: lagg in Plocklogg Full, Translogg, Pallastningslogg och KPI-mal. |
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
- `../app/backend/workflow_data.py`
- `../app/backend/coredata_service.py`
- `../app/backend/routers/productivity.py`
- `../desktop/local_runtime.py`

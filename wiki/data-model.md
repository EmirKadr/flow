---
title: Datamodell
status: aktiv
updated: 2026-07-21
tags: [databas, modeller]
---

# Datamodell

Kort svar: bemanningen bygger pa verksamheter, personer, aktiviteter, omraden, schemaceller, personliga veckomallar, anvandare, auditlogg och verksamhetsspecifika appsettings. Schemaceller ar segmenterade per timme och kan vara hel timme eller 2-4 sammanhangande minutdelar.

## Centrala tabeller

| Tabell | Modell | Syfte | Viktiga falt |
| --- | --- | --- | --- |
| `businesses` | `Business` | Verksamheter/isoleringsniva | `code`, `name`, `company_codes`, `tenant`, `sort_order`, `is_active` |
| `users` | `User` | Inloggning, roller, verksamhet, omrade och eventuell personkoppling | `business_id`, `username`, `password_hash`, `role`, `roles`, `area_id`, `person_id`, `is_active`, `must_change_password` |
| `areas` | `Area` | Omraden/stallen inom en verksamhet | `business_id`, `code`, `name`, `sort_order`, `is_active` |
| `persons` | `Person` | Planerbara personer inom en verksamhet | `business_id`, `name`, `noman`, `rfid_code`, `collar_type`, `home_area_id`, `home_activity_id`, `has_fixed_schedule`, `is_active`, `sort_order` |
| `activities` | `Activity` | Aktiviteter som kan bemannas inom en verksamhet | `business_id`, `code`, `label`, `area_id`, `summary_activity_id`, `kpi_process_name`, `color`, `category`, `work_type`, `sort_order`, `is_active` |
| `schedule_cells` | `ScheduleCell` | Explicita schemaandringar + materialiserad historik | `year`, `week`, `weekday`, `hour`, `minute_start`, `minute_end`, `person_id`, `activity_id`, `empty_override`, `is_template_fill`, `version`, `updated_by` |
| `schedule_freeze_state` | `ScheduleFreezeState` | Singelrad: hur langt schemajournalen stracker sig | `id=1`, `frozen_until`, `elapsed_date`, `elapsed_hour`, `updated_at` |
| `rfid_devices` | `RfidDevice` | Fysiska RFID-moduler kopplade till aktivitet | `business_id`, `device_id`, `module_name`, `activity_id`, `is_active`, `last_seen_at` |
| `rfid_scan_events` | `RfidScanEvent` | Sparade RFID-stamplingar innan/efter Bemanning applicerar dem | `business_id`, `device_identifier`, `module_name`, `tag_code`, `person_id`, `activity_id`, `scan_time`, `status`, `schedule_year/week/weekday/hour/minute`, `applied_by`, `ignored_by` |
| `person_schedule_templates` | `PersonScheduleTemplate` | Personlig veckomall | `person_id`, `weekday`, `start_hour`, `end_hour`, `is_off` |
| `person_productivity_daily` | `PersonProductivityDaily` | Materialiserad personproduktivitet per dag for Bemanning, cell-hover-snitt och framtida personnara snitt | `business_id`, `snapshot_date`, `person_id`, `row_type`, `item_key`, `metric`, `activity_id`, `process_key`, `kpi_points`, `planned_kpi_points`, `kpi_minutes`, `units`, `source_snapshot_at`, `schedule_signature` |
| `audit_log` | `AuditLog` | Historik over muterande handelser | `business_id`, `entity_type`, `entity_id`, `action`, `old_value`, `new_value`, `user_id`, `created_at` |
| `user_wait_metrics` | `UserWaitMetric` | Tyst vantetids- och klientprestanda for Historik/Halsa | `business_id`, `user_id`, `event_type`, `view_id`, `target`, `duration_ms`, `status`, `detail`, `created_at` |
| `user_interaction_events` | `UserInteractionEvent` | Tyst interaction-tracking for Historik > Funktioner/Knappar/Kolumner/Floden/AI-analys | `business_id`, `user_id`, `event_type`, `view_id`, `control_id`, `feature`, `flow_id`, `table_key`, `column_label`, `client_surface`, `detail`, `created_at` |
| `allocation_user_filter_profiles` | `AllocationUserFilterProfile` | Personliga Bearbeta-källval, filtreringar och Ytgenerering-installningar per anvandare | `user_id`, `profile`, `updated_at` |
| `staffing_calculator_profiles` | `StaffingCalculatorProfile` | Personliga automatiska bemanningskalkyler per anvandare | `user_id`, `profile`, `updated_at` |
| `app_settings` | `AppSetting` | Verksamhetsspecifika settings JSON/text | `business_id`, `key`, `value`, `updated_by` |
| `coredata_files` | `CoreDataFile` | Central sanning for uppladdade coredata-karnfiler | `business_code`, `file_type`, `filename`, `content_hash`, `data`, `uploaded_by`, `updated_at` |
| `meta_media_uploads` | `MetaMediaUpload` | Publikt uppladdade bilder/videor for senare LLM-analys | `batch_id`, `original_filename`, `stored_filename`, `content_type`, `media_type`, `size_bytes`, `duration_seconds`, `content_hash`, `data`, `status`, `analysis`, `source`, `created_at` |
| `meta_shipment_observations` | `MetaShipmentObservation` | Analysrader for Meta-videor | `media_upload_id`, `label_image_upload_id`, `video_hash`, `label_image_hash`, `record_hash`, `order_number`, `shipment_number`, `username`, `customer_name`, `pallet_id`, `deviations`, `analysis_status` |

## Verksamheter

- `STIGAMO` ar bakatkompatibel standardverksamhet. Migrationen kopplar befintliga anvandare, omraden, personer, aktiviteter, auditlogg och settings dit nar verksamhetskolumnen infors.
- `R3` skapas som egen verksamhet av migrationen. Lokal/dev-seed kan fylla R3-omrade och franvaroaktiviteter, men seed kor inte i production/live.
- Icke-Super Users filtreras alltid till sin egen `business_id`.
- Super User kan se allt med `∞`, eller filtrera pa `business_id`.
- `Business.company_codes` ar en JSON-lista med bolagskoder som hor till verksamheten. Klienten visar dem som kommaseparerad text i Verksamheter-vyn.
- `Business.tenant` ar en kort slug for extern datakalla. Den anvands nar backend bygger tenant-specifik `DATA_SOURCE_API_BASE_URL` for Hamta data, Bearbeta och Produktivitet.
- Omradeskod, aktivitetskod och liknande registerdubbletter ar scopeade per verksamhet. Anvandarnamn ar fortsatt globalt unikt.
- `Person.rfid_code` ar valfri brickkod. Backend normaliserar den till versaler och stoppar dubbletter inom samma verksamhet.
- `Person.collar_type` ar `blue_collar` eller `white_collar`. Befintliga och nya personer defaultar till `blue_collar`, som visas som `Blue collar` i Personer.
- `RfidDevice.module_name` ar modulens aktivitetsnamn, till exempel `MG Plock`. Vid scan matchas det mot aktiv aktivitets `label` eller `code`; `RfidScanEvent` sparar resultatet som pending, ignored, applied eller konfliktstatus. Gamla `duplicate_ignored`-rader kan finnas kvar som legacy.
- En RFID-stampling blir inte en schemacell forran en anvandare med `schedule=edit` applicerar den i Bemanning. Ignorerade handelser sparas kvar for sparbarhet, men direkta dubbletter for samma person och aktivitet droppas innan ny `RfidScanEvent` skapas.
- Personkonton kan ha `person_id` till `persons`. Auto-skapade `person`-anvandare far `person_id`, `business_id` och `area_id` fran matchande `Person.noman`.
- Schemaceller pekar fortfarande pa person och aktivitet, men writes validerar att person och aktivitet tillhor samma verksamhet.

## Schemaceller

- Timmar ar 06-23 i UI. `hour` ar heltimmen.
- En hel cell har `minute_start=0`, `minute_end=60`.
- En delad cell har 2-4 sammanhangande segment som tacker minuten `0-60`, till exempel `0-30`/`30-60`, `0-17`/`17-60` eller `0-20`/`20-40`/`40-60`.
- `activity_id=null` betyder tomt/ledig.
- `empty_override=true` betyder att anvandaren uttryckligen tomt en schemalagd malltimme.
- `is_template_fill=true` betyder att cellen ar en materialiserad implicit
  malltimme, skriven av schemafrysningen nar timmen passerat (inte av en
  anvandare; `updated_by=null`). Se [Schemahistorikens mutabilitet](schema-historik-mutabilitet.md).
- `activity_area_id` ar det omrade aktiviteten tillhorde nar arbetet
  registrerades. Stamplas av frysningen och laser fore `Activity.area_id` i
  summering och omradesfiltrering.
- `version` anvands som optimistic concurrency-skydd. Klienten skickar aktuell version som `expected_version`.

## Schemafrysning

Schemat ar bade plan och journal: **framtiden ar plan, fortiden journal, idag
en blandning.** `schedule_freeze_state` (en rad, `id=1`) haller gransen:

- `frozen_until` — sista helt materialiserade datumet. Datum <= det ar ren
  journal: veckomallen appliceras inte vid lasning, sa register-/malländringar
  kan inte rora dem.
- `elapsed_date`/`elapsed_hour` — hur langt in i den pagaende dagen journalen
  gar. Timmar fore gransen ar avklarade och skyddade; timmarna darefter ar
  fortfarande plan och foljer mallen.
- Bakgrundsjobbet `schedule_freeze_scheduler` kor var 30:e minut: materialiserar
  ofrysta hela dagar och skriver ut dagens passerade timmar. Forsta korningen
  backfyller hela historiken fran aldsta cell/person.
- Framtida datum projiceras helt fran mallen — de ar en plan.
- `schedule_cells.activity_area_id` stamplas vid frysning med aktivitetens
  omrade da, sa historisk bemanning per stalle inte flyttar med vid en
  omorganisation.

## Personlig veckomall

- Om person saknar egna mallrader visas standarddagar.
- Om person har nagon egen mallrad blir saknade dagar lediga.
- `has_fixed_schedule=false` gor personen till timmis utan fast schema.
- Malltider maste ligga 06-24 och start < slut.

## Produktivitetscache

- `person_productivity_daily` ar beraknad data, inte masterdata pa personen.
- Raderna materialiseras fran global Produktivitet-snapshot, schema och KPI-regler.
- `row_type=person` summerar personen for dagen, `cell` lagrar KPI-/stod-/franvaroceller med minutintervall, `activity` summerar aktivitet och `process` lagrar historiska enheter per KPI-process/metrik for cell-hover-snitt och automatisk bemanningskalkyl.
- `source_snapshot_at` och `schedule_signature` gor att backend kan bygga om en dags cache nar snapshoten eller schemat for dagen andras.

## Borttagning och aktivflaggor

- Personer, aktiviteter och anvandare halls aktiva i normal drift; gamla inaktiva rader backfylldes till aktiva av engangsmigrationer och lokal SQLite-bootstrap. Production-seed och lokal bootstrap ar sparrade mot live.
- **`DELETE` for personer och aktiviteter bevarar historiken (2026-07-21):**
  finns schemaceller fryses forst ofrysta gardagar, framtida celler (datum >
  idag) rensas, och raden inaktiveras i stallet for att tas bort — person far
  `is_active=False`, `has_fixed_schedule=False` och `rfid_code=null`
  (brickan frigors); aktivitet far `is_active=False`. Historiska celler
  behalls orörda sa frysta dagar fortsatter visa hur personen jobbade.
  Person/aktivitet helt utan schemaceller hardraderas som forut.
- `DELETE` for anvandare tar bort raden. Gamla `updated_by`/`audit_log.user_id`-referenser nollas innan kontot tas bort.
- Frysta datum visar aven inaktiva/borttagna personer som har celler den
  dagen (dagvy, summering, Oversikt, narvaro, produktivitetsombyggnad).
- Omraden kan fortfarande inaktiveras nar de har kopplad data; loskopplingen
  av omradets celler ror numera bara framtida datum. Verksamheter har ocksa aktiv-status i Super User-vyn.

## Settings

Viktiga settings:

- `lock_foreign_schedule_cells`: ledare far inte andra celler som annan anvandare fyllt, admin/super user kan passera.
- `staffing_history_hours`: historikfonster i timmar for cell-hover-snitt och automatisk bemanningskalkyl, default 40.
- `staffing_activity_capacity_activity_ids`: aktiviteter som far visa historiskt snitt vid cell-hover. `null` betyder alla KPI-aktiviteter och `[]` betyder inga.
- sidebar-layout: menyordning/rubrik/undervyer per verksamhet.
- role-view-access: matris per verksamhet for rollernas vyatkomst (`none`, `view`, `edit`).

## Coredata

- `coredata_files` lagrar nya coredata-karnfiler som blobbar i Postgres. Nyckeln ar `business_code + file_type`, sa en ny uppladdning ersatter bara samma karnfilstyp i samma verksamhet.
- Kanda filtyper omfattar bland annat `dispatch_template` for dispatchmallar och `trans_agency` for transportors-/agency-underlag.
- `content_hash` ar SHA-256 av filens bytes och anvands for sparbar koppling/spårbarhet. `data` innehaller filen; list-endpointen visar bara metadata.
- Lagerverktygen och Produktivitet behöver fortfarande filvagar internt. Backend materialiserar darfor DB-raden till en temporar serverfil nar ett flode ska lasa den. Den temporara filen ar cache; Postgres-raden ar sanningen.
- Gamla filbaserade coredata-underlag under `data/coredata/` kan fortfarande lasas som fallback tills respektive karnfil laddas upp igen och finns i `coredata_files`.

## Meta-media

- `meta_media_uploads` ar inte verksamhetsscopead i forsta versionen. Den publika uppladdningssidan saknar login och sparar alla media i samma meta-tabell.
- `original_filename` ar namnet fran anvandarens telefon/dator. `stored_filename` ar det namn som visas i Meta och byggs av serverns uppladdningsdatum/timestamp plus originalandelse, till exempel `20260531_120102_123456Z_01.mov`.
- `duration_seconds` ar videons langd nar den kan lasas med `ffprobe` vid uppladdning. Meta-vyn har en browser-fallback som kan visa langd for gamla videor aven om kolumnen saknar varde.
- `content_hash` ar SHA-256 av filens bytes. Backend anvander ett unikt index for att inte spara samma bild/video flera ganger.
- `data` innehaller sjalva bilden/videon som blob. List-endpointen returnerar inte blobben; Super User hamtar/visar en fil via separat content-endpoint.
- Super User kan radera en meta-rad via Meta-vyn. Da tas blobben bort och audit-loggen sparar bara metadata, inte filens bytes.
- `status=pending_analysis` betyder att filen finns redo for ett senare LLM-flode. `analysis` ar reserverat for analysresultat.
- `meta_shipment_observations` skapas for videor. Raden lankar till videon med `media_upload_id` och `video_hash` och har `record_hash` som hash av video-hash, pall-id och avvikelser. Kolumnerna `label_image_upload_id`/`label_image_hash`/`label_frame_time_seconds` ar historiska: stillbildsfunktionen togs bort 2026-07-09 och de fylls aldrig for nya analyser. Ordernummer, sandningsnummer, anvandarnamn och kund ingar inte i hashen eftersom de fylls fran ASK via pall-id.
- Gemini-analysen anvander bara extraherat ljud fran videon och ska fylla `pallet_id` och `deviations`. `order_number`, `shipment_number`, `username` och `customer_name` lamnas tomma. Osakra eller saknade pall-id/avvikelser ger `analysis_status=manual_review`; misslyckad ljudextraktion ger `analysis_status=analysis_failed`.

## Kallor

- `../app/backend/models.py`
- `../app/backend/schedule_freeze.py`
- `../app/alembic/versions/0049_schedule_history_freeze.py`
- `../app/backend/business_scope.py`
- `../app/backend/coredata_service.py`
- `../app/backend/template_service.py`
- `../app/backend/schedule_locks.py`
- `../app/backend/settings_service.py`
- `../app/alembic/versions/0027_meta_shipment_number.py`
- `../app/alembic/versions/0028_coredata_files.py`
- `../app/alembic/versions/0032_user_interaction_events.py`
- `../app/alembic/versions/0034_allocation_user_filter_profiles.py`
- `../app/alembic/versions/0037_staffing_calculator_profiles.py`
- `../app/alembic/versions/0041_company_rfid.py`
- `../app/alembic/versions/0042_rfid_scan_events.py`
- `../app/alembic/versions/0044_business_tenant.py`

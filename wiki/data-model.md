---
title: Datamodell
status: aktiv
updated: 2026-06-14
tags: [databas, modeller]
---

# Datamodell

Kort svar: bemanningen bygger pa verksamheter, personer, aktiviteter, omraden, schemaceller, personliga veckomallar, anvandare, auditlogg och verksamhetsspecifika appsettings. Schemaceller ar segmenterade per timme och kan vara hel timme eller 2-4 sammanhangande minutdelar.

## Centrala tabeller

| Tabell | Modell | Syfte | Viktiga falt |
| --- | --- | --- | --- |
| `businesses` | `Business` | Verksamheter/isoleringsniva | `code`, `name`, `sort_order`, `is_active` |
| `users` | `User` | Inloggning, roller, verksamhet, omrade och eventuell personkoppling | `business_id`, `username`, `password_hash`, `role`, `roles`, `area_id`, `person_id`, `is_active`, `must_change_password` |
| `areas` | `Area` | Omraden/stallen inom en verksamhet | `business_id`, `code`, `name`, `sort_order`, `is_active` |
| `persons` | `Person` | Planerbara personer inom en verksamhet | `business_id`, `name`, `home_area_id`, `home_activity_id`, `has_fixed_schedule`, `is_active`, `sort_order` |
| `activities` | `Activity` | Aktiviteter som kan bemannas inom en verksamhet | `business_id`, `code`, `label`, `area_id`, `summary_activity_id`, `kpi_process_name`, `color`, `category`, `work_type`, `sort_order`, `is_active` |
| `schedule_cells` | `ScheduleCell` | Explicita schemaandringar | `year`, `week`, `weekday`, `hour`, `minute_start`, `minute_end`, `person_id`, `activity_id`, `empty_override`, `version`, `updated_by` |
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
- Omradeskod, aktivitetskod och liknande registerdubbletter ar scopeade per verksamhet. Anvandarnamn ar fortsatt globalt unikt.
- Personkonton kan ha `person_id` till `persons`. Auto-skapade `person`-anvandare far `person_id`, `business_id` och `area_id` fran matchande `Person.noman`.
- Schemaceller pekar fortfarande pa person och aktivitet, men writes validerar att person och aktivitet tillhor samma verksamhet.

## Schemaceller

- Timmar ar 06-23 i UI. `hour` ar heltimmen.
- En hel cell har `minute_start=0`, `minute_end=60`.
- En delad cell har 2-4 sammanhangande segment som tacker minuten `0-60`, till exempel `0-30`/`30-60`, `0-17`/`17-60` eller `0-20`/`20-40`/`40-60`.
- `activity_id=null` betyder tomt/ledig.
- `empty_override=true` betyder att anvandaren uttryckligen tomt en schemalagd malltimme.
- `version` anvands som optimistic concurrency-skydd. Klienten skickar aktuell version som `expected_version`.

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
- `DELETE` for personer, aktiviteter och anvandare tar bort raden. Vid anvandarborttagning nollas gamla `updated_by`/`audit_log.user_id`-referenser innan kontot tas bort.
- Omraden kan fortfarande inaktiveras nar de har kopplad data. Verksamheter har ocksa aktiv-status i Super User-vyn.

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
- `meta_shipment_observations` skapas for videor. Raden lankar till videon med `media_upload_id` och `video_hash`, kan lanka till en best-effort-stillbild med `label_image_upload_id`, och har `record_hash` som hash av video-hash, eventuell stillbild, pall-id och avvikelser. Ordernummer, sandningsnummer, anvandarnamn och kund ingar inte langre i hashen eftersom de ska fyllas fran uppladdad data via pall-id senare.
- Gemini-analysen anvander bara extraherat ljud fran videon och ska fylla `pallet_id` och `deviations`. `order_number`, `shipment_number`, `username` och `customer_name` lamnas tomma. Osakra eller saknade pall-id/avvikelser ger `analysis_status=manual_review`; misslyckad ljudextraktion ger `analysis_status=analysis_failed`.

## Kallor

- `../app/backend/models.py`
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

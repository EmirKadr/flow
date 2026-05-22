---
title: Datamodell
status: aktiv
updated: 2026-05-21
tags: [databas, modeller]
---

# Datamodell

Kort svar: bemanningen bygger pa verksamheter, personer, aktiviteter, omraden, schemaceller, personliga veckomallar, anvandare, auditlogg och verksamhetsspecifika appsettings. Schemaceller ar segmenterade per timme och kan vara hel timme eller tva halvtimmar.

## Centrala tabeller

| Tabell | Modell | Syfte | Viktiga falt |
| --- | --- | --- | --- |
| `businesses` | `Business` | Verksamheter/isoleringsniva | `code`, `name`, `sort_order`, `is_active` |
| `users` | `User` | Inloggning, roller, verksamhet och omrade | `business_id`, `username`, `password_hash`, `role`, `roles`, `area_id`, `is_active`, `must_change_password` |
| `areas` | `Area` | Omraden/stallen inom en verksamhet | `business_id`, `code`, `name`, `sort_order`, `is_active` |
| `persons` | `Person` | Planerbara personer inom en verksamhet | `business_id`, `name`, `home_area_id`, `home_activity_id`, `has_fixed_schedule`, `is_active`, `sort_order` |
| `activities` | `Activity` | Aktiviteter som kan bemannas inom en verksamhet | `business_id`, `code`, `label`, `area_id`, `summary_activity_id`, `color`, `category`, `sort_order`, `is_active` |
| `schedule_cells` | `ScheduleCell` | Explicita schemaandringar | `year`, `week`, `weekday`, `hour`, `minute_start`, `minute_end`, `person_id`, `activity_id`, `empty_override`, `version`, `updated_by` |
| `person_schedule_templates` | `PersonScheduleTemplate` | Personlig veckomall | `person_id`, `weekday`, `start_hour`, `end_hour`, `is_off` |
| `audit_log` | `AuditLog` | Historik over muterande handelser | `business_id`, `entity_type`, `entity_id`, `action`, `old_value`, `new_value`, `user_id`, `created_at` |
| `app_settings` | `AppSetting` | Verksamhetsspecifika settings JSON/text | `business_id`, `key`, `value`, `updated_by` |

## Verksamheter

- `STIGAMO` ar bakatkompatibel standardverksamhet. Migration/seed kopplar befintliga anvandare, omraden, personer, aktiviteter, auditlogg och settings dit.
- `R3` skapas som egen verksamhet med ett aktivt omrade `R3` och egna franvaroaktiviteter, men utan Stigamos personer, anvandare eller arbetsaktiviteter.
- Icke-Super Users filtreras alltid till sin egen `business_id`.
- Super User kan se allt med `∞`, eller filtrera pa `business_id`.
- Omradeskod, aktivitetskod och liknande registerdubbletter ar scopeade per verksamhet. Anvandarnamn ar fortsatt globalt unikt.
- Schemaceller pekar fortfarande pa person och aktivitet, men writes validerar att person och aktivitet tillhor samma verksamhet.

## Schemaceller

- Timmar ar 06-23 i UI. `hour` ar heltimmen.
- En hel cell har `minute_start=0`, `minute_end=60`.
- En delad cell har normalt tva segment: `0-30` och `30-60`.
- `activity_id=null` betyder tomt/ledig.
- `empty_override=true` betyder att anvandaren uttryckligen tomt en schemalagd malltimme.
- `version` anvands som optimistic concurrency-skydd. Klienten skickar aktuell version som `expected_version`.

## Personlig veckomall

- Om person saknar egna mallrader visas standarddagar.
- Om person har nagon egen mallrad blir saknade dagar lediga.
- `has_fixed_schedule=false` gor personen till timmis utan fast schema.
- Malltider maste ligga 06-24 och start < slut.

## Soft delete

- Personer, aktiviteter och anvandare inaktiveras med `is_active=false`.
- UI-texter kan saga "Ta bort", men backend gor normalt mjuk borttagning.
- Felsokningsrad: om nagot "raderat" fortfarande finns i databasen ar det sannolikt avsiktligt. Kontrollera `include_inactive=true`.

## Settings

Viktiga settings:

- `lock_foreign_schedule_cells`: ledare far inte andra celler som annan anvandare fyllt, admin/super user kan passera.
- sidebar-layout: menyordning/rubrik/undervyer per verksamhet.
- role-view-access: matris per verksamhet for rollernas vyatkomst (`none`, `view`, `edit`).

## Kallor

- `../app/backend/models.py`
- `../app/backend/business_scope.py`
- `../app/backend/template_service.py`
- `../app/backend/schedule_locks.py`
- `../app/backend/settings_service.py`

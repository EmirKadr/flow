---
title: Historik och audit
status: aktiv
updated: 2026-05-22
tags: [historik, audit, ui]
---

# Historik och audit

Kort svar: Historik visar auditlogg och enkel analytics. Den ar byggd for super user/roller med vyatkomst och hjalper till att forklara vem som andrade vad och nar.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Period | Valjer 24h, 7d, 30d, all | Raknar `start_at` for query | `periodStartIso`, `/api/audit*` | "All historik" kan bli tung om mycket data finns. |
| Anvandare | Filtrerar pa user | Skickar user-filter | `userFilter` | Listan laddas fran `/api/users?include_inactive=true`. |
| Typ | Filtrerar entity type | Skickar `entity_type` | `entityFilter` | Typnamn ar tekniska, t.ex. `schedule_cell`, `app_setting`, `productivity_file`, `allocation_flow`. |
| Atgard | Skriver action | Skickar action-filter | `actionFilter` | Exempel: `update`, `clear`, `drag_fill`. |
| Objekt-id | Skriver id | Skickar `entity_id` | `entityIdFilter` | Maste vara numeriskt. |
| Uppdatera | Klickar knapp | Hamter summary och rader igen | `GET /api/audit/summary`, `GET /api/audit` | Nekas om saknar super user/vyatkomst. |
| Enter i textfilter | Trycker Enter | Trigger refresh | `keydown` handlers | Change pa select refreshar direkt. |

## Vad som visas

- Statkort: antal handelser i urval, senaste 24 h och unika anvandare.
- Topplistor: topp anvandare, topp atgarder, topp typer.
- Tabell: tid, anvandare, typ, atgard, objekt och detalj.
- Detalj byggs av old/new snapshots och forsoker oversatta person, aktivitet och omrade via lookups.
- Loggade floden omfattar nu register/schema, anvandare/forsta losenord, globala installningar, Hamta data, serverhanterade produktivitetsfiler och korda lagerverktygsfloden.
- Misslyckade filuppladdningar som hinner na backend loggas som `productivity_file/upload_failed`, `allocation_flow/upload_failed` eller `allocation_flow/detect_failed` med steg, feltyp och eventuell HTTP-status.
- Auditpayloadar ska vara felsokningsbara men inte innehalla losenord, API-detaljer, sessionscookies eller privata filnamn.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor kommer jag inte in pa Historik?" | Historik kraver super-user/vyatkomst till `analytics`. |
| "Varfor syns inte min andring?" | Kontrollera periodfilter och att flodet gar via backend. Lokala IndexedDB-handlingar som aldrig skickas till servern kan fortfarande sakna auditrad. |
| "Vad betyder Typ/Atgard?" | Typ ar databasenheten, atgard ar backendens audit-action. |
| "Varfor saknas anvandarnamn?" | Auditloggar kan ha `user_id=null` for system/seed eller gammal data. |

## Kallor

- `../app/frontend/historik.html`
- `../app/frontend/js/analytics.js`
- `../app/backend/routers/audit_logs.py`
- `../app/backend/audit.py`

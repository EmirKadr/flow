---
title: Apphjälpens tools (live-data i chatten)
status: experiment
updated: 2026-07-06
tags: [chat, tools, function-calling, llm, minimax, behorighet]
---

# Apphjälpens tools (live-data i chatten)

Kort svar: Apphjälpen har ett internt register med ~30 read-only-tools
(function calling) som låter chatten svara på live-datafrågor: schema,
personer, områden, aktiviteter, produktivitet, Historik, användare och
systemhälsa. Alla tools är verksamhetsscopade via `business_scope` och kan
aldrig ändra data. Behörighet per tool finns som metadata (vy + nivå) men
enforcement är avstängd tills `ASSISTANT_TOOLS_ENFORCE_VIEW_ACCESS=true`.

Beslutsdatum för experimentet: 2026-08-01 — då ska Emir avgöra om
vybehörighets-enforcement slås på, om tools ska begränsas per roll, eller om
läget förlängs.

## Användarflöde

1. Användaren ställer en datafråga i Apphjälpen, t.ex. "vilka jobbar på GG
   idag?" eller "hur många områden har vi?".
2. Backend skickar frågan till MiniMax tillsammans med tool-deklarationer.
3. Modellen väljer tools; backend kör dem read-only mot databasen, scopat till
   användarens verksamhet, och skickar tillbaka resultaten till modellen.
4. Modellen formulerar svaret. Bubblan visar en liten meta-rad
   "Hämtade live-data (N uppslag)" när tools användes.
5. Wikifrågor ("hur gör jag...?") besvaras som tidigare med wikiutdrag; tools
   används bara för datainnehåll.

## Tool-katalog

Registret ligger i `app/backend/assistant_tools/` och varje tool har
`view_id` + `min_level` som behörighetsmetadata:

| Domän | Tools | view_id |
| --- | --- | --- |
| Grunddata | `list_businesses`, `list_areas`, `list_activities`, `get_activity`, `data_counts`, `resolve_date` | businesses/areas/activities/overview/schedule |
| Personer | `search_persons`, `get_person`, `list_competencies`, `get_person_schedule_template` | persons |
| Schema | `get_schedule_day`, `get_person_schedule`, `schedule_staffing_summary`, `find_scheduled_persons`, `schedule_week_overview` | schedule |
| Schema – analys | `schedule_coverage_gaps`, `person_utilization`, `schedule_period_compare` | schedule |
| Produktivitet | `productivity_summary`, `productivity_person_day`, `productivity_top_persons`, `productivity_process_summary` | productivity |
| Produktivitet – trend/analys | `productivity_trend`, `productivity_person_compare`, `productivity_process_trend`, `productivity_anomalies` | productivity |
| Ekonomi | `finance_summary` (kräver alltid productivityFinance-behörighet i runtime, oavsett enforcement-flaggan) | productivityFinance |
| Historik | `search_audit_log`, `audit_action_stats`, `recent_errors`, `wait_metrics_summary`, `interaction_summary` | analytics |
| Historik – trend/detalj | `error_trend`, `error_top_endpoints`, `audit_entity_history`, `wait_metrics_by_endpoint`, `user_activity_summary`, `rfid_error_summary` | analytics |
| System | `list_users`, `get_role_view_access_matrix`, `list_rfid_devices`, `rfid_scan_stats`, `list_coredata_files`, `healthcheck_summary` | users/roleAccess/analytics/allocationUploads |

Regler som gäller alla tools:

- **Read-only.** Inga handlers muterar data; fel rullas tillbaka.
- **Verksamhetsscope alltid på.** `resolve_business_id` går via
  `visible_business_id`: vanliga användare ser bara sin verksamhet, Super User
  kan välja verksamhet eller se allt.
- **Radtak.** Listor kapas (default 50, max 200) och varje tool-resultat kortas
  till 4000 tecken innan det skickas till modellen.
- **Sanerat.** `list_users` exponerar aldrig lösenordshashar; audit-payloads
  kortas till 300 tecken; kärnfiler listas utan filinnehåll.

## Tekniskt flöde

- `app/backend/assistant_tools/registry.py` — registret, OpenAI-deklarationer,
  `run_tool` (fångar `ToolInputError`/`HTTPException` och returnerar
  `{"error": ...}` till modellen i stället för att krascha anropet).
- `app/backend/assistant_tools/runtime.py` — providerneutral tool-loop:
  max `ASSISTANT_TOOLS_MAX_STEPS` varv (default 4), max
  `ASSISTANT_TOOLS_MAX_CALLS_PER_STEP` anrop per varv (default 5). Sista varvet
  tvingar `tool_choice=none` så användaren alltid får ett textsvar.
- `app/backend/routers/assistant.py` — bygger MiniMax-payload med
  tool-deklarationer, kör loopen i trådpool och auditloggar tool-användning.
- Frontend: `sidebar.js` sparar `toolCalls` per assistant-bubbla och visar
  meta-raden; `analytics.js` visar Historik-labeln.

Inställningar i `config.py`:

| Inställning | Default | Betydelse |
| --- | --- | --- |
| `ASSISTANT_TOOLS_ENABLED` | `true` | Av/på för hela tool-stödet (runtime-toggle; rollback utan deploy). |
| `ASSISTANT_TOOLS_MAX_STEPS` | `4` | Max modellvarv per fråga. |
| `ASSISTANT_TOOLS_MAX_CALLS_PER_STEP` | `5` | Max tool-anrop per varv. |
| `ASSISTANT_TOOLS_ENFORCE_VIEW_ACCESS` | `false` | `true` = filtrera tools per användarens vybehörighet (samma `can_access_view`-regler som sidorna). |

## Historik och audit

Varje chattfråga där modellen körde minst ett tool skriver en auditrad:

- `entity_type="assistant_chat"`, `action="tools_used"`
- Payload: `tool_calls`, `tools_used`, `tool_errors`, `question_chars`,
  `answer_chars`, `page_path` — aldrig frågetext, svarstext eller tool-resultat.
- Label i Historik: `Apphjälp-fråga`, med summering
  "N tool-anrop | Tools: ... | X tecken fråga | Y tecken svar".
- Frågor utan tool-anrop auditloggas inte (medvetet read-only-undantag,
  skyddat av test).

Tester: `tests/services/test_assistant_tools.py` täcker registerkontraktet,
verksamhetsscope, handlers, tool-loopen (inkl. tvingat svar och tool-fel),
endpoint + auditrad samt att payload aldrig innehåller frågetext.
`tests/services/test_assistant_chat.py` skyddar prompt- och sessionbeteendet.

## Felsökningssvar för framtida chat

**"Chatten svarar med gammal eller påhittad data."**
Kontrollera att `ASSISTANT_TOOLS_ENABLED=true` och att svaret har meta-raden
"Hämtade live-data". Utan meta-rad använde modellen inte tools — be användaren
formulera datafrågan tydligare, t.ex. med datum eller områdeskod.

**"Chatten säger att den inte ser en annan verksamhets data."**
Det är avsiktligt. Tools är alltid scopade till användarens verksamhet; bara
Super User kan fråga om andra verksamheter.

**"Svaret säger att tool-anropet gav fel."**
Modellen får `{"error": ...}` i stället för data, t.ex. vid ogiltigt datum
eller okänt område. Felet syns också som `tool_errors` i auditraden
`Apphjälp-fråga` i Historik.

**"Varför ser en användare utan Historik-behörighet audit-data i chatten?"**
Enforcement per vybehörighet är avstängd i experimentläget
(`ASSISTANT_TOOLS_ENFORCE_VIEW_ACCESS=false`). Slå på flaggan för att filtrera
tools med samma regler som sidorna.

## Källor

- `../app/backend/assistant_tools/registry.py`
- `../app/backend/assistant_tools/runtime.py`
- `../app/backend/assistant_tools/common.py`
- `../app/backend/routers/assistant.py`
- `../app/backend/business_scope.py`
- `../app/backend/config.py`
- `../app/frontend/js/common/sidebar.js`
- `../app/frontend/js/analytics.js`
- `../tests/services/test_assistant_tools.py`
- `../tests/services/test_assistant_chat.py`

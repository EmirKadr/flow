---
title: MCP
status: aktiv
updated: 2026-06-25
tags: [mcp, integration, chat-stod, deepseek, gemini]
---

# MCP

Kort svar: MCP-vyn later admin och Super User stalla textfragor till
Noeffect-MCP:n for anvandarens verksamhets-tenant. Flow-backend hamtar
MCP-kontext via read-only resources/prompts nar de finns och exponerar MCP-tools
som function calling till vald LLM-hjarna. Backend kor bara tillatna read-only
tools at modellen och later modellen formulera svaret. Anvandaren kan valja
provider, modell och thinking-lage bland de providers som har API-nyckel i
servermiljon. Frontend ser aldrig token, API-nycklar eller privat serveradress.

## Anvandarflode

1. Oppna `MCP` i sidebaren.
2. Vyn laser `GET /api/mcp/status` och visar om MCP-konfiguration, token och
   vald LLM-hjarna ar redo.
3. Valj `Foretag`, `Modell` och `Thinking mode`. Listorna byggs fran
   serverns konfigurerade API-nycklar och modellistor.
4. Skriv fragan i textrutan och klicka `Skicka`.
5. Svaret visas i panelen `Svar`. Om modellen anvande MCP-tools visar svarsraden
   antal tool-anrop. Panelen `MCP-kontext` visar sanerad metadata om resources,
   prompts och tools som MCP-servern annonserar.

Windows-appen serverar samma statiska frontend via sin lokala appyta och proxar
centrala API-anrop, sa MCP-vyn ska bete sig likadant i webb och desktop sa
lange servermiljon har samma MCP- och LLM-konfiguration.

## Knappar och kontroller

| Kontroll | Var | Vem far | Vad hander | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- | --- |
| Foretag | MCP-panelen | Anvandare med `mcp=view` | Valjer provider: DeepSeek, OpenAI, Gemini eller MiniMax nar respektive API-nyckel finns | `mcp.js`, `GET /api/mcp/status` | Provider saknas om API-nyckeln saknas i servermiljon. |
| Modell | MCP-panelen | Anvandare med `mcp=view` | Valjer modell inom vald provider enligt serverns modellista | `mcp.js`, `GET /api/mcp/status` | Modellistan styrs av env, inte av frontend. |
| Thinking mode | MCP-panelen | Anvandare med `mcp=view` | Valjer `Ingen thinking`, `Thinking` eller `Deep thinking` nar providern stoder det | `mcp.js`, `POST /api/mcp/query` | DeepSeek har thinking-val; ovriga providers visar bara `Ingen thinking` tills stod laggs till. |
| Fraga | MCP-panelen | Anvandare med `mcp=edit` | Tar emot fraga upp till 4000 tecken | `mcp.html`, `mcp.js` | Vid read-only-vyatkomst kan anvandaren se status men inte skicka. |
| Uppdatera | MCP-panelen | Anvandare med `mcp=view` | Laser om MCP-/LLM-status och kontextmetadata | `GET /api/mcp/status` | Anvands efter att token, tenant eller env har andrats. |
| Rensa | MCP-panelen | Anvandare med `mcp=view` | Tommer fraga och doljer aktuellt svar lokalt | `mcp.js` | Raderar ingen historik. |
| Skicka | MCP-panelen | Anvandare med `mcp=edit` | Hamter MCP-kontext, ger LLM-hjarnan read-only MCP-tools och kor valda tool-anrop via backend | `POST /api/mcp/query`, control-id `mcp-query-send` | Disabled vid saknad config, saknat token, saknad provider-nyckel eller pagaende anrop. |

`Ctrl+Enter` eller `Cmd+Enter` skickar ocksa fragan nar textrutan har fokus.

## Tekniskt flode

- `app/frontend/mcp.html` ar sidan och laddar gemensam sidebar/auth-logik.
- `app/frontend/js/mcp.js` initialiserar `initPage("mcp")`, hamtar status,
  skickar fragan med `api.post` och trackar `mcp_query` utan fragetext.
- `GET /api/mcp/status` kraver `mcp=view` och returnerar konfigurationsstatus,
  saknade env-namn, vald provider/modell och sanerad MCP-metadata.
- `POST /api/mcp/query` kraver `mcp=edit`, hamtar MCP-resources/prompts,
  skickar read-only MCP-tools som function declarations och kor de tool-anrop
  modellen valjer via `tools/call`. Svaret innehaller `answer`,
  `tool`, `tool_title`, `model`, `tool_calls`, `tools_used`, `server`, `tenant` och
  `content_items`.
- `app/backend/mcp_service.py` anvander MCP Streamable HTTP med bearer-token,
  initierar session, laser `resources/list`/`resources/read` och frivilligt
  `prompts/list`/`prompts/get`. `tools/list` blir bade metadata och underlag
  for function calling.
- Backend laser serveradress fran `NOEFFECT_MCP_URL_TEMPLATE`, eller lokalt fran
  ignorerad `.codex/config.toml` om den finns. Templatevardet ska innehalla
  `{tenant}` nar varje verksamhet har egen MCP-host.
- Token kommer fran env-namnet i `NOEFFECT_MCP_TOKEN_ENV_TEMPLATE`, default
  `NOEFFECT_{tenant}_TOKEN`. For token-env expanderas tenant till versaler,
  till exempel `frey` -> `NOEFFECT_FREY_TOKEN`. Backend laser forst processens
  miljo och kan sedan falla tillbaka till lokal `.env`/`app/.env` for just det
  dynamiska env-namnet.
- Default-hjarna styrs av `MCP_LLM_PROVIDER`: `auto` (default), `deepseek`,
  `nowaste`, `openai`, `gemini` eller `minimax`. `auto` valjer forsta
  konfigurerade provider i ordningen DeepSeek, NoWaste, OpenAI, Gemini, MiniMax.
- DeepSeek styrs av `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`,
  `DEEPSEEK_API_BASE_URL`, `DEEPSEEK_THINKING_ENABLED` och
  `DEEPSEEK_REASONING_EFFORT`. Default ar `deepseek-v4-pro` med thinking av for
  snabbare MCP-fragor. Thinking kan slas pa med `DEEPSEEK_THINKING_ENABLED=true`;
  `DEEPSEEK_REASONING_EFFORT=high` ar normalniva och `max` kan anvandas for svar
  som kraver mer planering men blir langsammare.
- NoWaste visas som egen provider och styrs av den OpenAI-kompatibla
  konfigurationen `MCP_LLM_OPENAI_API_KEY`, `MCP_LLM_OPENAI_MODEL` och
  `MCP_LLM_OPENAI_API_BASE_URL`. Modellistan for NoWaste ar bara
  `MCP_LLM_OPENAI_MODEL`, normalt `gpt-4o`.
- OpenAI visas separat och styrs av `OPENAI_API_KEY`, `OPENAI_MODEL`,
  `OPENAI_API_BASE_URL` och modellistan `MCP_OPENAI_MODELS`. NoWaste faller
  inte tillbaka till OpenAI-nyckeln, och OpenAI anvander inte NoWaste-nyckeln.
- Gemini styrs fortsatt av `GEMINI_API_KEY`, `GEMINI_MODEL` och
  `GEMINI_API_BASE_URL`.
- MiniMax styrs av `MINIMAX_API_KEY`, `MINIMAX_MODEL` och `MINIMAX_API_URL`.
- Modellistorna i MCP-vyn styrs av `MCP_DEEPSEEK_MODELS`,
  `MCP_OPENAI_MODELS`, `MCP_GEMINI_MODELS` och `MCP_MINIMAX_MODELS` som
  kommaseparerade listor. Provider-defaultmodellen laggs alltid till forst om
  den inte redan finns i listan. OpenAI-listan ar en inbyggd standardlista och
  hamtas inte live fran OpenAI, sa MCP-status inte gor extra provideranrop.
  NoWaste ignorerar `MCP_OPENAI_MODELS` och visar bara sin defaultmodell.
  Provider-nyckeln skickas bara backend-side; frontend far aldrig se den.

Om MCP-servern saknar textresurser och prompts men har tools, ska modellen normalt
borja med `search_views` eller `get_views`, hamta schema/kolumner vid behov och
sedan anvanda `query_view` eller `aggregate_view`. Tool-resultat kortas innan de
skickas tillbaka till hjarnan sa stora MCP-svar inte skickas obegransat.

DeepSeek thinking-mode skickar inte resonemanget till frontend eller audit, men
backend bevarar `reasoning_content` internt mellan tool-anrop eftersom
DeepSeek-API:t kraver det nar thinking och tool calls kombineras.

## Historik och audit

Varje skickforsok som nar backend auditloggas som `mcp_query`.

- Lyckat anrop: `query_success`
- Saknad konfiguration, MCP-fel eller LLM-fel: `query_failed`
- Payload innehaller `server`, `tenant`, `status`, `tool`, `model`,
  `tool_calls`, `tools_used`, `question_chars`, `answer_chars`, `content_items`,
  `missing` eller `error_type` beroende pa lage.
- Payload far inte innehalla fraga, svar, token, privat URL, headers eller
  request body.
- Historik/Analys visar labeln `MCP-fraga` och summerar status, modell,
  hjarna/tool och teckenantal.

Frontendens interaction-tracking skriver ocksa ett sanerat `mcp_query`-event
med `control_id=mcp-query-send`, vald `brain`, modell och antal tecken i
fragan. Sjalva fragan sparas inte.

## Felsokningssvar for framtida chat

**"MCP-vyn syns inte i menyn."**
Rollen saknar troligen `mcp=view`. Be admin eller Super User oppna Anvandare >
Vybehorigheter och ge rollen `view` eller `edit` for `MCP`.

**"Det star att MCP saknar NOEFFECT_FREY_TOKEN."**
Servern har inte token i miljo for tenant `frey`. Satt env-varn som
`NOEFFECT_MCP_TOKEN_ENV_TEMPLATE` pekar pa, default
`NOEFFECT_<TENANT>_TOKEN`, och starta om backend.

**"Det star att MCP saknar NOEFFECT_MCP_URL_TEMPLATE."**
Backend hittar ingen serveradress i miljo och ingen lokal ignorerad
`.codex/config.toml`. Satt `NOEFFECT_MCP_URL_TEMPLATE` i driftmiljon eller lagg
templatevardet i lokal Codex-konfiguration for utveckling.

**"Det star att MCP saknar DEEPSEEK_API_KEY."**
Backend ar i `auto` med DeepSeek vald, eller `MCP_LLM_PROVIDER=deepseek`, men
saknar DeepSeek-nyckel. Lagg `DEEPSEEK_API_KEY` i lokal `.env` eller driftens
secret store och starta om backend.

**"Det star att MCP saknar GEMINI_API_KEY."**
Backend anvander Gemini som fallback eller `MCP_LLM_PROVIDER=gemini`, men saknar
Gemini-nyckel. Lagg `GEMINI_API_KEY` i lokal `.env` eller driftens secret store
och starta om backend. `GEMINI_MODEL=gemini-2.5-flash` valjer Flash.

**"MCP svarade, men ingen textkontext hittades."**
Flow kunde initiera MCP-sessionen men hittade inga lasbara text-resources eller
prompts utan obligatoriska argument. Om det finns tools ska hjarnan anda kunna
hamta data via tool-anrop; om `tool-anrop` star som 0 i svaret anvande modellen
inte toolsen och fragan kan behova vara mer explicit eller modellen bytas.

**"Hjarnan svarar att den saknar data fast MCP-kontexten visar tools."**
Det betyder oftast att modellen inte valde ett tool-anrop. Flow skickar read-only
tools till modellen, men modellen avgor fortfarande vilket tool som ska anvandas.
Skriv till exempel "Anvand search_views forst..." och namnge garna en trolig vy,
till exempel `v_ask_receive_log`. Thinking `high` kan hjalpa for svar som kraver
flera tool-steg men gor anropet segare.

**"DeepSeek/Gemini svarade HTTP 4xx/5xx."**
Flow nadde providern men anropet nekades eller misslyckades. Kontrollera
provider-nyckel, modellnamn, kvot och att nyckeln far anvanda valt API.
Historik > Felkoder/Analys visar bara sanerad status, inte nyckel eller prompt.

## Kallor

- `../app/frontend/mcp.html`
- `../app/frontend/js/mcp.js`
- `../app/backend/routers/mcp.py`
- `../app/backend/mcp_service.py`
- `../app/backend/user_access.py`
- `../app/frontend/js/common/access.js`
- `../app/frontend/js/common/foundation.js`
- `../app/frontend/js/analytics.js`
- `../tools/flow_cli.py`
- `../tests/services/test_mcp_service.py`

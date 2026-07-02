import asyncio

import pytest

from app.backend import mcp_service
from app.backend.mcp import chat as mcp_chat
from app.backend.mcp import protocol as mcp_protocol


def test_mcp_config_uses_tenant_url_and_token_templates(monkeypatch):
    monkeypatch.setattr(mcp_protocol, "_load_project_mcp_entry", lambda: {})
    monkeypatch.setattr(
        mcp_service.settings,
        "NOEFFECT_MCP_URL_TEMPLATE",
        "https://noeffectui-{tenant}-development.example.test/mcp",
    )
    monkeypatch.setattr(mcp_service.settings, "NOEFFECT_MCP_TOKEN_ENV_TEMPLATE", "NOEFFECT_{tenant}_TOKEN")
    monkeypatch.setenv("NOEFFECT_LOKI_TOKEN", "secret-token")

    config = mcp_service.mcp_config("loki")

    assert config.url == "https://noeffectui-loki-development.example.test/mcp"
    assert config.token_env_var == "NOEFFECT_LOKI_TOKEN"
    assert config.token == "secret-token"
    assert config.tenant == "loki"


def test_mcp_config_can_read_local_codex_template_without_token_value(monkeypatch, tmp_path):
    monkeypatch.setattr(
        mcp_protocol,
        "_load_project_mcp_entry",
        lambda: {
            "url": "https://noeffectui-{tenant}-development.example.test/mcp",
            "bearer_token_env_var": "NOEFFECT_{tenant}_TOKEN",
        },
    )
    monkeypatch.setattr(mcp_protocol, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(mcp_service.settings, "NOEFFECT_MCP_URL_TEMPLATE", "")
    monkeypatch.setattr(mcp_service.settings, "NOEFFECT_MCP_TOKEN_ENV_TEMPLATE", "")
    monkeypatch.delenv("NOEFFECT_FREY_TOKEN", raising=False)

    config = mcp_service.mcp_config("frey")

    assert config.url == "https://noeffectui-frey-development.example.test/mcp"
    assert config.token_env_var == "NOEFFECT_FREY_TOKEN"
    assert config.token == ""
    assert config.missing == ["NOEFFECT_FREY_TOKEN"]


def test_mcp_config_reads_dynamic_token_from_app_env_file(monkeypatch, tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    token_env_var = "NOEFFECT_FREY_TOKEN"
    (app_dir / ".env").write_text(f'{token_env_var}="env-file-token"\n', encoding="utf-8")
    monkeypatch.setattr(mcp_protocol, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(mcp_protocol, "_load_project_mcp_entry", lambda: {})
    monkeypatch.setattr(
        mcp_service.settings,
        "NOEFFECT_MCP_URL_TEMPLATE",
        "https://noeffectui-{tenant}-development.example.test/mcp",
    )
    monkeypatch.setattr(mcp_service.settings, "NOEFFECT_MCP_TOKEN_ENV_TEMPLATE", "NOEFFECT_{tenant}_TOKEN")
    monkeypatch.delenv("NOEFFECT_FREY_TOKEN", raising=False)

    config = mcp_service.mcp_config("frey")

    assert config.token_env_var == "NOEFFECT_FREY_TOKEN"
    assert config.token == "env-file-token"


def test_mcp_authorization_header_accepts_raw_or_bearer_token():
    assert mcp_service.mcp_authorization_header("abc.def") == "Bearer abc.def"
    assert mcp_service.mcp_authorization_header("Bearer abc.def") == "Bearer abc.def"
    assert mcp_service.mcp_authorization_header("bearer abc.def") == "bearer abc.def"


def test_mcp_question_tool_rejects_mutating_tool_names():
    tools = [
        {
            "name": "update_record",
            "description": "Update a record from a query",
            "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
        {
            "name": "search_docs",
            "description": "Search documentation",
            "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
    ]

    selected = mcp_service.select_question_tool(tools)

    assert selected["name"] == "search_docs"
    summaries = mcp_service.summarize_tools(tools)
    assert summaries[0]["supports_question"] is False
    assert summaries[1]["supports_question"] is True


def test_mcp_arguments_use_question_field_and_required_defaults():
    tool = {
        "name": "ask_noeffect",
        "inputSchema": {
            "type": "object",
            "required": ["question", "locale"],
            "properties": {
                "question": {"type": "string"},
                "locale": {"type": "string", "default": "sv-SE"},
            },
        },
    }

    assert mcp_service.arguments_for_question(tool, "Vad finns i flodet?") == {
        "question": "Vad finns i flodet?",
        "locale": "sv-SE",
    }


def test_mcp_extract_tool_answer_uses_text_content_first():
    answer, content_items, is_error = mcp_service.extract_tool_answer({
        "content": [
            {"type": "text", "text": "Första raden"},
            {"type": "text", "text": "Andra raden"},
        ],
        "isError": False,
    })

    assert answer == "Första raden\n\nAndra raden"
    assert content_items == 2
    assert is_error is False


def test_mcp_extract_resource_text_uses_text_contents_and_skips_blob():
    answer, content_items = mcp_service.extract_resource_text({
        "contents": [
            {"uri": "mcp://docs/one", "mimeType": "text/plain", "text": "Noeffect-rad"},
            {"uri": "mcp://docs/blob", "mimeType": "application/pdf", "blob": "abcdef"},
        ],
    })

    assert "Noeffect-rad" in answer
    assert "application/pdf hoppades over" in answer
    assert content_items == 2


def test_mcp_extract_gemini_text_reads_first_candidate():
    answer = mcp_service._extract_gemini_text({
        "candidates": [
            {"content": {"parts": [{"text": "Svar från Gemini"}]}},
        ],
    })

    assert answer == "Svar från Gemini"


def test_mcp_gemini_function_declarations_allow_read_only_tools():
    tools = [
        {
            "name": "query_view",
            "description": "Fetches data rows from a view",
            "inputSchema": {
                "type": "object",
                "required": ["viewName"],
                "properties": {"viewName": {"type": "string"}, "limit": {"type": "integer"}},
            },
        },
        {
            "name": "update_record",
            "description": "Update data",
            "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}},
        },
    ]

    declarations = mcp_service.gemini_function_declarations(tools)

    assert [declaration["name"] for declaration in declarations] == ["query_view"]
    assert declarations[0]["parameters"]["required"] == ["viewName"]


def test_mcp_gemini_generate_url_uses_header_safe_path(monkeypatch):
    monkeypatch.setattr(mcp_service.settings, "GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com")
    monkeypatch.setattr(mcp_service.settings, "GEMINI_MODEL", "models/gemini-2.5-flash")

    assert mcp_service._gemini_generate_url().endswith("/v1beta/models/gemini-2.5-flash:generateContent")


def test_mcp_gemini_body_uses_allowed_names_only_for_any_mode():
    declaration = {"name": "get_views", "description": "List views", "parameters": {"type": "object", "properties": {}}}
    any_body = mcp_service._gemini_body(contents=[], declarations=[declaration], force_tool=True)
    auto_body = mcp_service._gemini_body(contents=[], declarations=[declaration], force_tool=False)

    assert any_body["toolConfig"]["functionCallingConfig"]["mode"] == "ANY"
    assert any_body["toolConfig"]["functionCallingConfig"]["allowedFunctionNames"] == ["get_views"]
    assert auto_body["toolConfig"]["functionCallingConfig"] == {"mode": "AUTO"}


def test_mcp_brain_auto_prefers_deepseek_when_key_exists(monkeypatch):
    monkeypatch.setattr(mcp_service.settings, "MCP_LLM_PROVIDER", "auto")
    monkeypatch.setattr(mcp_service.settings, "DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setattr(mcp_service.settings, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(mcp_service.settings, "DEEPSEEK_MODEL", "deepseek-v4-pro")

    assert mcp_service.brain_provider_name() == "deepseek"
    assert mcp_service.brain_configured() is True
    assert mcp_service.brain_model_name() == "deepseek-v4-pro"


def test_mcp_brain_options_include_configured_providers_and_models(monkeypatch):
    monkeypatch.setattr(mcp_service.settings, "DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setattr(mcp_service.settings, "MCP_LLM_OPENAI_API_KEY", "openai-key")
    monkeypatch.setattr(mcp_service.settings, "MCP_LLM_OPENAI_MODEL", "gpt-test")
    monkeypatch.setattr(mcp_service.settings, "MCP_LLM_OPENAI_API_BASE_URL", "https://llm.example.test/openai/v1")
    monkeypatch.setattr(mcp_service.settings, "OPENAI_API_KEY", "global-openai-key")
    monkeypatch.setattr(mcp_service.settings, "OPENAI_MODEL", "gpt-global")
    monkeypatch.setattr(mcp_service.settings, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(mcp_service.settings, "MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setattr(mcp_service.settings, "MCP_OPENAI_MODELS", "gpt-global,gpt-other")

    options = mcp_service.mcp_brain_options()
    ids = [option["id"] for option in options]
    nowaste = next(option for option in options if option["id"] == "nowaste")
    openai = next(option for option in options if option["id"] == "openai")
    deepseek = next(option for option in options if option["id"] == "deepseek")

    assert ids[:5] == ["deepseek", "nowaste", "openai", "gemini", "minimax"]
    assert nowaste["label"] == "NoWaste"
    assert nowaste["models"] == ["gpt-test"]
    assert openai["models"] == ["gpt-global", "gpt-other"]
    assert deepseek["thinking_modes"] == [
        {"value": "none", "label": "Ingen thinking"},
        {"value": "high", "label": "Thinking"},
        {"value": "max", "label": "Deep thinking"},
    ]


def test_mcp_nowaste_uses_mcp_specific_env_not_global_openai(monkeypatch):
    monkeypatch.setattr(mcp_service.settings, "MCP_LLM_OPENAI_API_KEY", "mcp-openai-key")
    monkeypatch.setattr(mcp_service.settings, "MCP_LLM_OPENAI_MODEL", "gpt-4o")
    monkeypatch.setattr(
        mcp_service.settings,
        "MCP_LLM_OPENAI_API_BASE_URL",
        "https://ask-ai-resource.services.ai.azure.com/openai/v1",
    )
    monkeypatch.setattr(mcp_service.settings, "OPENAI_API_KEY", "global-openai-key")
    monkeypatch.setattr(mcp_service.settings, "OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(mcp_service.settings, "OPENAI_API_BASE_URL", "https://api.openai.com/v1")

    assert mcp_service.nowaste_configured() is True
    assert mcp_service.brain_model_name("nowaste") == "gpt-4o"
    assert mcp_service._chat_provider_api_key("nowaste") == "mcp-openai-key"
    assert (
        mcp_service._chat_provider_url("nowaste")
        == "https://ask-ai-resource.services.ai.azure.com/openai/v1/chat/completions"
    )
    assert mcp_service.openai_configured() is True
    assert mcp_service.brain_model_name("openai") == "gpt-4o-mini"
    assert mcp_service._chat_provider_api_key("openai") == "global-openai-key"
    assert mcp_service._chat_provider_url("openai") == "https://api.openai.com/v1/chat/completions"


def test_mcp_nowaste_default_model_is_only_option_even_when_openai_list_exists(monkeypatch):
    monkeypatch.setattr(mcp_service.settings, "MCP_LLM_OPENAI_API_KEY", "mcp-openai-key")
    monkeypatch.setattr(mcp_service.settings, "MCP_LLM_OPENAI_MODEL", "gpt-4o")
    monkeypatch.setattr(
        mcp_service.settings,
        "MCP_LLM_OPENAI_API_BASE_URL",
        "https://ask-ai-resource.services.ai.azure.com/openai/v1",
    )
    monkeypatch.setattr(mcp_service.settings, "MCP_OPENAI_MODELS", "gpt-4o-mini,gpt-4o")

    assert mcp_service.provider_model_options("nowaste") == ["gpt-4o"]


def test_mcp_openai_default_list_includes_newer_models(monkeypatch):
    monkeypatch.setattr(mcp_service.settings, "OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(
        mcp_service.settings,
        "MCP_OPENAI_MODELS",
        "gpt-5.5,gpt-5.4,gpt-5.2,gpt-5,gpt-4o-mini,gpt-4o",
    )

    models = mcp_service.provider_model_options("openai")

    assert models[:4] == ["gpt-4o-mini", "gpt-5.5", "gpt-5.4", "gpt-5.2"]
    assert "gpt-5" in models


def test_mcp_nowaste_does_not_fallback_to_global_openai_key(monkeypatch):
    monkeypatch.setattr(mcp_service.settings, "MCP_LLM_OPENAI_API_KEY", "")
    monkeypatch.setattr(
        mcp_service.settings,
        "MCP_LLM_OPENAI_API_BASE_URL",
        "https://ask-ai-resource.services.ai.azure.com/openai/v1",
    )
    monkeypatch.setattr(mcp_service.settings, "OPENAI_API_KEY", "global-openai-key")

    assert mcp_service.nowaste_configured() is False
    assert mcp_service.brain_missing("nowaste") == [mcp_service.MCP_LLM_OPENAI_API_KEY_ENV]
    assert mcp_service.openai_configured() is True


def test_mcp_nowaste_requires_mcp_base_url(monkeypatch):
    monkeypatch.setattr(mcp_service.settings, "MCP_LLM_OPENAI_API_KEY", "mcp-openai-key")
    monkeypatch.setattr(mcp_service.settings, "MCP_LLM_OPENAI_API_BASE_URL", "")
    monkeypatch.setattr(mcp_service.settings, "OPENAI_API_BASE_URL", "https://api.openai.com/v1")

    assert mcp_service.nowaste_configured() is False
    assert mcp_service.brain_missing("nowaste") == ["MCP_LLM_OPENAI_API_BASE_URL"]


def test_mcp_deepseek_body_enables_thinking_without_temperature(monkeypatch):
    monkeypatch.setattr(mcp_service.settings, "DEEPSEEK_MODEL", "deepseek-v4-pro")
    monkeypatch.setattr(mcp_service.settings, "DEEPSEEK_THINKING_ENABLED", True)
    monkeypatch.setattr(mcp_service.settings, "DEEPSEEK_REASONING_EFFORT", "max")

    body = mcp_service._deepseek_body(messages=[{"role": "user", "content": "Hej"}], tools=[])

    assert body["model"] == "deepseek-v4-pro"
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "max"
    assert "temperature" not in body


def test_mcp_deepseek_body_disables_thinking_with_temperature(monkeypatch):
    monkeypatch.setattr(mcp_service.settings, "DEEPSEEK_MODEL", "deepseek-v4-pro")
    monkeypatch.setattr(mcp_service.settings, "DEEPSEEK_THINKING_ENABLED", False)

    body = mcp_service._deepseek_body(messages=[{"role": "user", "content": "Hej"}], tools=[])

    assert body["thinking"] == {"type": "disabled"}
    assert body["temperature"] == 0.2
    assert "reasoning_effort" not in body


def test_mcp_deepseek_textual_tool_markup_is_blocked():
    answer = mcp_service._tool_exhausted_answer(12, ["search_views", "get_views"])

    assert mcp_service._deepseek_text_has_tool_markup("< | DSML | tool_calls>") is True
    assert "fastnade efter 12 MCP-tool-anrop" in answer
    assert "search_views, get_views" in answer


def test_ask_mcp_requires_gemini_key_before_mcp_calls(monkeypatch):
    monkeypatch.setattr(mcp_service.settings, "MCP_LLM_PROVIDER", "gemini")
    monkeypatch.setattr(mcp_service.settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(
        mcp_service,
        "mcp_config",
        lambda tenant=None: mcp_service.McpConfig(
            url="https://mcp.example.test",
            token_env_var="NOEFFECT_FREY_TOKEN",
            token="secret-token",
            timeout_seconds=1,
            tenant="frey",
        ),
    )

    with pytest.raises(mcp_service.McpConfigError) as exc:
        asyncio.run(mcp_service.ask_mcp("Vad finns?", tenant="frey"))

    assert exc.value.missing == ["GEMINI_API_KEY"]


def test_mcp_status_is_ready_with_gemini_even_without_tools(monkeypatch):
    class FakeSession:
        def __init__(self, config):
            self.config = config

        async def initialize(self):
            return None

        async def list_tools_optional(self):
            return []

        async def list_resources(self):
            return []

        async def list_prompts(self):
            return []

        async def close(self):
            return None

    monkeypatch.setattr(mcp_service.settings, "MCP_LLM_PROVIDER", "gemini")
    monkeypatch.setattr(mcp_service.settings, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(mcp_service.settings, "GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr(
        mcp_service,
        "mcp_config",
        lambda tenant=None: mcp_service.McpConfig(
            url="https://mcp.example.test",
            token_env_var="NOEFFECT_FREY_TOKEN",
            token="secret-token",
            timeout_seconds=1,
            tenant="frey",
        ),
    )
    monkeypatch.setattr(mcp_protocol, "McpHttpSession", FakeSession)

    payload = asyncio.run(mcp_service.list_mcp_tools("frey"))

    assert payload["configured"] is True
    assert payload["brain"] == "gemini"
    assert payload["brain_configured"] is True
    assert payload["model"] == "gemini-2.5-flash"
    assert payload["tools"] == []


def test_mcp_gemini_tool_loop_calls_mcp_tool(monkeypatch):
    calls = []

    async def fake_generate(body, config, *, context_items=0):
        calls.append(body)
        if len(calls) == 1:
            return {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "query_view",
                                        "args": {"viewName": "v_articles", "limit": 5},
                                    }
                                }
                            ],
                        }
                    }
                ]
            }
        return {"candidates": [{"content": {"parts": [{"text": "Fem artiklar hittades."}]}}]}

    class FakeSession:
        async def call_tool(self, name, arguments):
            assert name == "query_view"
            assert arguments["viewName"] == "v_articles"
            return {"content": [{"type": "text", "text": "Artikel 1"}], "isError": False}

    monkeypatch.setattr(mcp_chat, "_gemini_generate_content", fake_generate)
    config = mcp_service.McpConfig(
        url="https://mcp.example.test",
        token_env_var="NOEFFECT_FREY_TOKEN",
        token="secret-token",
        timeout_seconds=1,
        tenant="frey",
    )
    context = mcp_service.McpContext(text="", content_items=0, resources=[], prompts=[], tools=[])
    tools = [
        {
            "name": "query_view",
            "description": "Fetches data rows from a view",
            "inputSchema": {
                "type": "object",
                "properties": {"viewName": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["viewName"],
            },
        }
    ]

    answer, tool_calls, content_items, tools_used = asyncio.run(
        mcp_service.ask_gemini_with_mcp_tools("Hamta artiklar", context, FakeSession(), config, tools)
    )

    assert answer == "Fem artiklar hittades."
    assert tool_calls == 1
    assert content_items == 1
    assert tools_used == ["query_view"]
    assert calls[0]["toolConfig"]["functionCallingConfig"]["mode"] == "ANY"


def test_mcp_deepseek_tool_loop_calls_mcp_tool_and_keeps_reasoning(monkeypatch):
    calls = []

    async def fake_chat(body, config, *, context_items=0):
        calls.append(body)
        if len(calls) == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "reasoning_content": "Jag behover hamta rader.",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "query_view",
                                        "arguments": '{"viewName": "v_articles", "limit": 5}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        assistant_messages = [message for message in body["messages"] if message.get("role") == "assistant"]
        assert assistant_messages[-1]["reasoning_content"] == "Jag behover hamta rader."
        assert body["messages"][-1]["role"] == "tool"
        assert body["messages"][-1]["tool_call_id"] == "call_1"
        return {"choices": [{"message": {"role": "assistant", "content": "Fem artiklar hittades."}}]}

    class FakeSession:
        async def call_tool(self, name, arguments):
            assert name == "query_view"
            assert arguments["viewName"] == "v_articles"
            return {"content": [{"type": "text", "text": "Artikel 1"}], "isError": False}

    monkeypatch.setattr(mcp_chat, "_deepseek_chat_completion", fake_chat)
    config = mcp_service.McpConfig(
        url="https://mcp.example.test",
        token_env_var="NOEFFECT_FREY_TOKEN",
        token="secret-token",
        timeout_seconds=1,
        tenant="frey",
    )
    context = mcp_service.McpContext(text="", content_items=0, resources=[], prompts=[], tools=[])
    tools = [
        {
            "name": "query_view",
            "description": "Fetches data rows from a view",
            "inputSchema": {
                "type": "object",
                "properties": {"viewName": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["viewName"],
            },
        }
    ]

    answer, tool_calls, content_items, tools_used = asyncio.run(
        mcp_service.ask_deepseek_with_mcp_tools("Hamta artiklar", context, FakeSession(), config, tools)
    )

    assert answer == "Fem artiklar hittades."
    assert tool_calls == 1
    assert content_items == 1
    assert tools_used == ["query_view"]
    assert calls[0]["tools"][0]["function"]["name"] == "query_view"

"""LLM-providerkonfiguration för MCP-vyn: DeepSeek, NoWaste, OpenAI, Gemini, MiniMax."""
from __future__ import annotations

import urllib.parse
from typing import Any

from ..config import settings
from .protocol import (
    MCP_LLM_OPENAI_API_KEY_ENV,
    MCP_PROVIDER_LABELS,
    MCP_PROVIDER_ORDER,
)


def gemini_configured() -> bool:
    return bool(settings.GEMINI_API_KEY.strip())


def _csv_values(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _model_options(default_model: str, configured: str) -> list[str]:
    values = [default_model, *_csv_values(configured)]
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def gemini_model_name(model: str | None = None) -> str:
    return (str(model or settings.GEMINI_MODEL).strip() or "gemini-2.5-pro").removeprefix("models/")


def nowaste_api_key() -> str:
    return settings.MCP_LLM_OPENAI_API_KEY.strip()


def nowaste_base_url() -> str:
    return settings.MCP_LLM_OPENAI_API_BASE_URL.strip().rstrip("/")


def openai_configured() -> bool:
    return bool(settings.OPENAI_API_KEY.strip())


def openai_model_name(model: str | None = None) -> str:
    return str(model or settings.OPENAI_MODEL).strip() or "gpt-4o-mini"


def _openai_base_url() -> str:
    return settings.OPENAI_API_BASE_URL.strip().rstrip("/") or "https://api.openai.com/v1"


def nowaste_configured() -> bool:
    return bool(nowaste_api_key() and nowaste_base_url())


def nowaste_model_name(model: str | None = None) -> str:
    return str(model or settings.MCP_LLM_OPENAI_MODEL).strip() or "gpt-4o"


def minimax_configured() -> bool:
    return bool(settings.MINIMAX_API_KEY.strip())


def minimax_model_name(model: str | None = None) -> str:
    return str(model or settings.MINIMAX_MODEL).strip() or "MiniMax-M2.7"


def deepseek_configured() -> bool:
    return bool(settings.DEEPSEEK_API_KEY.strip())


def deepseek_model_name(model: str | None = None) -> str:
    return str(model or settings.DEEPSEEK_MODEL).strip() or "deepseek-v4-pro"


def deepseek_thinking_enabled() -> bool:
    return bool(settings.DEEPSEEK_THINKING_ENABLED)


def deepseek_reasoning_effort() -> str:
    configured = str(settings.DEEPSEEK_REASONING_EFFORT or "").strip().lower()
    if configured in {"max", "xhigh"}:
        return "max"
    return "high"


def _deepseek_base_url() -> str:
    return settings.DEEPSEEK_API_BASE_URL.strip().rstrip("/") or "https://api.deepseek.com"


def _deepseek_chat_url() -> str:
    return f"{_deepseek_base_url()}/chat/completions"


def _provider_configured(provider: str) -> bool:
    if provider == "deepseek":
        return deepseek_configured()
    if provider == "nowaste":
        return nowaste_configured()
    if provider == "openai":
        return openai_configured()
    if provider == "gemini":
        return gemini_configured()
    if provider == "minimax":
        return minimax_configured()
    return False


def _provider_missing(provider: str) -> list[str]:
    if provider == "deepseek":
        return [] if deepseek_configured() else ["DEEPSEEK_API_KEY"]
    if provider == "nowaste":
        missing: list[str] = []
        if not nowaste_api_key():
            missing.append(MCP_LLM_OPENAI_API_KEY_ENV)
        if not nowaste_base_url():
            missing.append("MCP_LLM_OPENAI_API_BASE_URL")
        return missing
    if provider == "openai":
        return [] if openai_configured() else ["OPENAI_API_KEY"]
    if provider == "gemini":
        return [] if gemini_configured() else ["GEMINI_API_KEY"]
    if provider == "minimax":
        return [] if minimax_configured() else ["MINIMAX_API_KEY"]
    return ["MCP_LLM_PROVIDER"]


def _default_provider() -> str:
    configured = str(settings.MCP_LLM_PROVIDER or "auto").strip().lower()
    if configured in MCP_PROVIDER_ORDER:
        return configured
    return next((provider for provider in MCP_PROVIDER_ORDER if _provider_configured(provider)), "deepseek")


def brain_provider_name(requested_provider: str | None = None) -> str:
    requested = str(requested_provider or "").strip().lower().removesuffix("_tools")
    if requested in MCP_PROVIDER_ORDER:
        return requested
    return _default_provider()


def brain_configured(provider: str | None = None) -> bool:
    return _provider_configured(brain_provider_name(provider))


def brain_missing(provider: str | None = None) -> list[str]:
    return _provider_missing(brain_provider_name(provider))


def provider_model_options(provider: str) -> list[str]:
    if provider == "deepseek":
        return _model_options(deepseek_model_name(), settings.MCP_DEEPSEEK_MODELS)
    if provider == "nowaste":
        return _model_options(nowaste_model_name(), "")
    if provider == "openai":
        return _model_options(openai_model_name(), settings.MCP_OPENAI_MODELS)
    if provider == "gemini":
        return _model_options(gemini_model_name(), settings.MCP_GEMINI_MODELS)
    if provider == "minimax":
        return _model_options(minimax_model_name(), settings.MCP_MINIMAX_MODELS)
    return []


def brain_model_name(
    provider: str | None = None,
    requested_model: str | None = None,
) -> str:
    selected_provider = brain_provider_name(provider)
    options = provider_model_options(selected_provider)
    requested = str(requested_model or "").strip()
    if requested and requested in options:
        return requested
    if selected_provider == "deepseek":
        return deepseek_model_name()
    if selected_provider == "nowaste":
        return nowaste_model_name()
    if selected_provider == "openai":
        return openai_model_name()
    if selected_provider == "gemini":
        return gemini_model_name()
    if selected_provider == "minimax":
        return minimax_model_name()
    return options[0] if options else ""


def provider_thinking_modes(provider: str) -> list[dict[str, str]]:
    modes = [{"value": "none", "label": "Ingen thinking"}]
    if provider == "deepseek":
        modes.extend([
            {"value": "high", "label": "Thinking"},
            {"value": "max", "label": "Deep thinking"},
        ])
    return modes


def normalize_thinking_mode(provider: str, requested: str | None = None) -> str:
    if provider != "deepseek":
        return "none"
    text = str(requested or "").strip().lower()
    if text in {"max", "deep", "deep_thinking", "deep-thinking", "xhigh"}:
        return "max"
    if text in {"high", "thinking", "enabled"}:
        return "high"
    if requested is None and deepseek_thinking_enabled():
        return deepseek_reasoning_effort()
    return "none"


def mcp_brain_options() -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for provider in MCP_PROVIDER_ORDER:
        configured = _provider_configured(provider)
        if not configured:
            continue
        default_thinking = normalize_thinking_mode(provider, None)
        options.append({
            "id": provider,
            "label": MCP_PROVIDER_LABELS.get(provider, provider.title()),
            "configured": configured,
            "models": provider_model_options(provider),
            "default_model": brain_model_name(provider),
            "thinking_modes": provider_thinking_modes(provider),
            "default_thinking": default_thinking,
        })
    return options


def _gemini_base_url() -> str:
    return settings.GEMINI_API_BASE_URL.strip().rstrip("/") or "https://generativelanguage.googleapis.com"


def _gemini_generate_url(model: str | None = None) -> str:
    model_path = f"models/{gemini_model_name(model)}"
    return f"{_gemini_base_url()}/v1beta/{urllib.parse.quote(model_path, safe='/')}:generateContent"

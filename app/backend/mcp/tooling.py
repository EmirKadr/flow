"""Summering av MCP-tools/resurser/prompts och insamling av MCP-kontext."""
from __future__ import annotations

import json
from typing import Any

from . import protocol
from .protocol import (
    MCP_CONTEXT_ITEM_CHAR_LIMIT,
    MCP_CONTEXT_PROMPT_LIMIT,
    MCP_CONTEXT_RESOURCE_LIMIT,
    MCP_CONTEXT_TOTAL_CHAR_LIMIT,
    QUESTION_FIELDS,
    READ_ONLY_TOOL_NAME_RE,
    SAFE_TOOL_NAME_RE,
    UNSAFE_TOOL_NAME_RE,
    McpConfig,
    McpContext,
    McpProtocolError,
    McpToolSummary,
)


def _input_schema(tool: dict[str, Any]) -> dict[str, Any]:
    schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    return schema if isinstance(schema, dict) else {}


def _schema_properties(tool: dict[str, Any]) -> dict[str, Any]:
    properties = _input_schema(tool).get("properties") or {}
    return properties if isinstance(properties, dict) else {}


def _tool_title(tool: dict[str, Any]) -> str:
    return str(tool.get("title") or tool.get("name") or "").strip()


def _tool_description(tool: dict[str, Any]) -> str:
    return str(tool.get("description") or "").strip()


def _safe_question_tool(tool: dict[str, Any]) -> bool:
    name = str(tool.get("name") or "")
    text = f"{name} {_tool_description(tool)}"
    if UNSAFE_TOOL_NAME_RE.search(name) and not SAFE_TOOL_NAME_RE.search(name):
        return False
    properties = _schema_properties(tool)
    has_question_field = any(field in properties for field in QUESTION_FIELDS)
    has_safe_name = bool(SAFE_TOOL_NAME_RE.search(text))
    return has_question_field and has_safe_name


def summarize_tool(tool: dict[str, Any]) -> McpToolSummary:
    properties = _schema_properties(tool)
    return McpToolSummary(
        name=str(tool.get("name") or "").strip(),
        title=_tool_title(tool),
        description=_tool_description(tool)[:500],
        input_fields=sorted(str(key) for key in properties)[:20],
        supports_question=_safe_question_tool(tool),
    )


def summarize_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        summary.as_dict()
        for summary in (summarize_tool(tool) for tool in tools)
        if summary.name
    ]


def _read_only_tool(tool: dict[str, Any]) -> bool:
    name = str(tool.get("name") or "")
    text = f"{name} {_tool_description(tool)}"
    if not name:
        return False
    if UNSAFE_TOOL_NAME_RE.search(name) and not READ_ONLY_TOOL_NAME_RE.search(name):
        return False
    return bool(READ_ONLY_TOOL_NAME_RE.search(text))


def _clean_gemini_schema(schema: Any, *, top_level: bool = False) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}} if top_level else {"type": "string"}
    schema_type = schema.get("type") or ("object" if schema.get("properties") else "string")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), schema_type[0] if schema_type else "string")
    schema_type = str(schema_type or "string").lower()
    if top_level and schema_type != "object":
        schema_type = "object"

    cleaned: dict[str, Any] = {"type": schema_type}
    description = str(schema.get("description") or "").strip()
    if description:
        cleaned["description"] = description[:1000]
    if isinstance(schema.get("enum"), list) and schema["enum"]:
        cleaned["enum"] = [item for item in schema["enum"] if isinstance(item, (str, int, float, bool))][:100]
    if schema_type == "object":
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        cleaned["properties"] = {
            str(key): _clean_gemini_schema(value)
            for key, value in properties.items()
            if str(key).strip()
        }
        required = schema.get("required")
        if isinstance(required, list):
            allowed = set(cleaned["properties"])
            cleaned["required"] = [str(item) for item in required if str(item) in allowed]
    elif schema_type == "array":
        cleaned["items"] = _clean_gemini_schema(schema.get("items") if isinstance(schema.get("items"), dict) else {})
    return cleaned


def _gemini_function_declaration(tool: dict[str, Any]) -> dict[str, Any] | None:
    name = str(tool.get("name") or "").strip()
    if not name or not _read_only_tool(tool):
        return None
    schema = _clean_gemini_schema(_input_schema(tool), top_level=True)
    description = _tool_description(tool) or f"MCP read-only tool {name}."
    return {
        "name": name,
        "description": description[:1000],
        "parameters": schema,
    }


def gemini_function_declarations(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    declarations = [
        declaration
        for declaration in (_gemini_function_declaration(tool) for tool in tools)
        if declaration is not None
    ]
    return declarations[:128]


def _resource_title(resource: dict[str, Any]) -> str:
    return str(resource.get("title") or resource.get("name") or resource.get("uri") or "").strip()


def _resource_description(resource: dict[str, Any]) -> str:
    return str(resource.get("description") or "").strip()


def summarize_resource(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _resource_title(resource)[:200],
        "description": _resource_description(resource)[:500],
        "mime_type": str(resource.get("mimeType") or resource.get("mime_type") or "").strip()[:120],
    }


def summarize_resources(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        summary
        for summary in (summarize_resource(resource) for resource in resources)
        if summary["title"] or summary["description"] or summary["mime_type"]
    ]


def _prompt_arguments(prompt: dict[str, Any]) -> list[dict[str, Any]]:
    arguments = prompt.get("arguments")
    return [argument for argument in arguments if isinstance(argument, dict)] if isinstance(arguments, list) else []


def _prompt_supports_empty_arguments(prompt: dict[str, Any]) -> bool:
    return not any(bool(argument.get("required")) for argument in _prompt_arguments(prompt))


def summarize_prompt(prompt: dict[str, Any]) -> dict[str, Any]:
    arguments = _prompt_arguments(prompt)
    return {
        "name": str(prompt.get("name") or "").strip()[:160],
        "title": str(prompt.get("title") or prompt.get("name") or "").strip()[:200],
        "description": str(prompt.get("description") or "").strip()[:500],
        "input_fields": [str(argument.get("name") or "").strip() for argument in arguments if argument.get("name")][:20],
        "supports_empty_arguments": _prompt_supports_empty_arguments(prompt),
    }


def summarize_prompts(prompts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        summary
        for summary in (summarize_prompt(prompt) for prompt in prompts)
        if summary["name"] or summary["title"]
    ]


def _question_tool_score(tool: dict[str, Any]) -> int:
    name = str(tool.get("name") or "")
    text = f"{name} {_tool_description(tool)}"
    properties = _schema_properties(tool)
    score = 0
    if _safe_question_tool(tool):
        score += 100
    if name.lower() in {"ask", "answer", "chat", "query", "search"}:
        score += 20
    if any(field in properties for field in ("question", "query", "prompt")):
        score += 12
    if SAFE_TOOL_NAME_RE.search(text):
        score += 5
    return score


def select_question_tool(tools: list[dict[str, Any]], requested_tool: str | None = None) -> dict[str, Any]:
    safe_tools = [tool for tool in tools if _safe_question_tool(tool)]
    if requested_tool:
        for tool in safe_tools:
            if str(tool.get("name") or "") == requested_tool:
                return tool
        raise McpProtocolError("Valt MCP-verktyg kan inte användas för frågor i den här vyn.")
    if not safe_tools:
        raise McpProtocolError("MCP-servern saknar ett säkert fråga- eller sökverktyg.")
    return max(safe_tools, key=_question_tool_score)


def _schema_default(schema: dict[str, Any]) -> Any:
    if "default" in schema:
        return schema["default"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    return None


def arguments_for_question(tool: dict[str, Any], question: str) -> dict[str, Any]:
    schema = _input_schema(tool)
    properties = _schema_properties(tool)
    required = [str(item) for item in schema.get("required") or []]
    target_field = next((field for field in QUESTION_FIELDS if field in properties), "")
    if not target_field:
        raise McpProtocolError("MCP-verktyget saknar ett textfält för frågan.")

    arguments: dict[str, Any] = {target_field: question}
    missing_required: list[str] = []
    for field in required:
        if field == target_field:
            continue
        prop = properties.get(field)
        default = _schema_default(prop if isinstance(prop, dict) else {})
        if default is None:
            missing_required.append(field)
        else:
            arguments[field] = default
    if missing_required:
        joined = ", ".join(missing_required)
        raise McpProtocolError(f"MCP-verktyget kräver fler fält: {joined}.")
    return arguments


def _content_item_text(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    if isinstance(item.get("text"), str):
        return item["text"]
    if "resource" in item:
        resource = item.get("resource")
        if isinstance(resource, dict):
            if isinstance(resource.get("text"), str):
                return resource["text"]
            if resource.get("uri"):
                return f"Resurs: {resource.get('uri')}"
        return json.dumps(resource, ensure_ascii=False, default=str)
    if "json" in item:
        return json.dumps(item.get("json"), ensure_ascii=False, indent=2, default=str)
    return json.dumps(item, ensure_ascii=False, indent=2, default=str)


def extract_tool_answer(result: dict[str, Any]) -> tuple[str, int, bool]:
    content = result.get("content")
    parts = [_content_item_text(item).strip() for item in content] if isinstance(content, list) else []
    parts = [part for part in parts if part]
    if not parts and isinstance(result.get("structuredContent"), (dict, list)):
        parts.append(json.dumps(result.get("structuredContent"), ensure_ascii=False, indent=2, default=str))
    if not parts and result:
        parts.append(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    answer = "\n\n".join(parts).strip()
    return answer, len(content) if isinstance(content, list) else 0, bool(result.get("isError"))


def _resource_content_text(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item or "").strip()
    if isinstance(item.get("text"), str):
        return item["text"].strip()
    if "blob" in item:
        mime_type = str(item.get("mimeType") or item.get("mime_type") or "binart innehall").strip()
        return f"[{mime_type} hoppades over eftersom MCP-resursen inte ar text.]"
    return _content_item_text(item).strip()


def extract_resource_text(result: dict[str, Any]) -> tuple[str, int]:
    contents = result.get("contents")
    parts = [_resource_content_text(item) for item in contents] if isinstance(contents, list) else []
    parts = [part for part in parts if part]
    if not parts and isinstance(result.get("content"), list):
        parts = [_resource_content_text(item) for item in result["content"]]
        parts = [part for part in parts if part]
    if not parts and isinstance(result.get("text"), str):
        parts.append(result["text"].strip())
    return "\n\n".join(parts).strip(), len(contents) if isinstance(contents, list) else len(parts)


def extract_prompt_text(result: dict[str, Any]) -> tuple[str, int]:
    messages = result.get("messages")
    parts: list[str] = []
    if isinstance(result.get("description"), str):
        parts.append(result["description"].strip())
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").strip()
            content = _content_item_text(message.get("content")).strip()
            if content:
                parts.append(f"{role}: {content}" if role else content)
    return "\n\n".join(part for part in parts if part).strip(), len(messages) if isinstance(messages, list) else len(parts)


def _trim_context_item(text: str, remaining: int) -> str:
    limit = max(0, min(MCP_CONTEXT_ITEM_CHAR_LIMIT, remaining))
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 80)].rstrip()}\n\n[Avkortat i Flow innan LLM-anropet.]"


def _context_label(title: str, fallback: str) -> str:
    text = str(title or fallback or "").strip()
    return text[:200] if text else "MCP-kontext"


async def collect_mcp_context(config: McpConfig) -> McpContext:
    session = protocol.McpHttpSession(config)
    try:
        await session.initialize()
        tools = await session.list_tools_optional()
        resources = await session.list_resources()
        prompts = await session.list_prompts()
        parts: list[str] = []
        content_items = 0
        remaining = MCP_CONTEXT_TOTAL_CHAR_LIMIT

        for resource in resources[:MCP_CONTEXT_RESOURCE_LIMIT]:
            uri = str(resource.get("uri") or "").strip()
            if not uri:
                continue
            result = await session.read_resource(uri)
            text, count = extract_resource_text(result)
            if not text:
                continue
            label = _context_label(_resource_title(resource), "MCP-resurs")
            block = f"### MCP resource: {label}\n{text}"
            trimmed = _trim_context_item(block, remaining)
            if not trimmed:
                break
            parts.append(trimmed)
            remaining -= len(trimmed)
            content_items += max(1, count)
            if remaining <= 0:
                break

        if remaining > 0:
            empty_prompts = [prompt for prompt in prompts if _prompt_supports_empty_arguments(prompt)]
            for prompt in empty_prompts[:MCP_CONTEXT_PROMPT_LIMIT]:
                name = str(prompt.get("name") or "").strip()
                if not name:
                    continue
                result = await session.get_prompt(name)
                text, count = extract_prompt_text(result)
                if not text:
                    continue
                label = _context_label(str(prompt.get("title") or name), "MCP-prompt")
                block = f"### MCP prompt: {label}\n{text}"
                trimmed = _trim_context_item(block, remaining)
                if not trimmed:
                    break
                parts.append(trimmed)
                remaining -= len(trimmed)
                content_items += max(1, count)
                if remaining <= 0:
                    break

        return McpContext(
            text="\n\n".join(parts).strip(),
            content_items=content_items,
            resources=summarize_resources(resources),
            prompts=summarize_prompts(prompts),
            tools=summarize_tools(tools),
        )
    finally:
        await session.close()

"""Browsertester för MCP-frågevyn (mcp.js på mcp.html) — W19.

Vyn hämtar /api/mcp/status och gate:ar frågeformuläret på svaret. Alla
kontrakt nedan mockas via page.route så de är deterministiska oavsett vad
den lokala seeden innehåller:

1. En fullt konfigurerad Gemini-provider (token + url + brain + providers med
   models/thinking_modes) -> statuspillen visar "Redo" och Skicka/fråga är
   aktiverade.
2. Utan token/url (missing) -> pillen visar "Stopp" och Skicka är låst.
3. Byte av provider nollställer modell + thinking mode till den nya providerns
   default.
4. En mockad fråga renderar svarpanelen och en success-toast.
"""
import json

import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


READY_STATUS = {
    "configured": True,
    "token_configured": True,
    "url_configured": True,
    "brain_configured": True,
    "brain": "gemini",
    "model": "gemini-2.5-flash",
    "thinking_mode": "none",
    "missing": [],
    "providers": [
        {
            "id": "gemini",
            "label": "Gemini",
            "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
            "default_model": "gemini-2.5-flash",
            "thinking_modes": [
                {"value": "none", "label": "Ingen thinking"},
                {"value": "balanced", "label": "Balanserad"},
            ],
            "default_thinking": "none",
        },
        {
            "id": "openai",
            "label": "OpenAI",
            "models": ["gpt-4o", "gpt-4o-mini"],
            "default_model": "gpt-4o-mini",
            "thinking_modes": [
                {"value": "none", "label": "Ingen"},
                {"value": "deep", "label": "Djup"},
            ],
            "default_thinking": "deep",
        },
    ],
    "tools": [],
    "resources": [
        {"title": "Körschema", "mime_type": "text/plain", "description": "Aktuellt schema"}
    ],
    "prompts": [],
}

STOPPED_STATUS = {
    "configured": True,
    "token_configured": False,
    "url_configured": False,
    "brain_configured": True,
    "brain": "gemini",
    "missing": ["token", "url"],
    "providers": READY_STATUS["providers"],
    "tools": [],
    "resources": [],
    "prompts": [],
}

QUERY_RESPONSE = {
    "answer": "Svaret fran MCP ar 42.",
    "content_items": 2,
    "tool": "gemini",
    "tool_title": "Gemini",
    "thinking_mode": "none",
    "tool_calls": 0,
    "tools_used": [],
}


@pytest.fixture(scope="module")
def local_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("mcp-browser")
    base_url, server = visual_smoke.start_local_server(output_dir)
    try:
        yield base_url
    finally:
        server.close()


@pytest.fixture(scope="module")
def chromium_browser():
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                pytest.skip("Playwright Chromium is not installed")
            raise
        try:
            yield browser
        finally:
            browser.close()


def login(page, base_url):
    page.goto(f"{base_url}/login.html", wait_until="load")
    page.fill("#username", "admin")
    page.fill("#password", "admin123")
    page.click("button.primary")
    page.wait_for_url("**/index.html", timeout=15000)


def mock_status(page, payload):
    """Fanga /api/mcp/status och svara med den givna payloaden."""
    page.route(
        "**/api/mcp/status**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        ),
    )


def open_mcp(page, base_url, status_payload):
    """Logga in, installera status-mocken och oppna mcp.html."""
    login(page, base_url)
    mock_status(page, status_payload)
    page.goto(f"{base_url}/mcp.html", wait_until="load")
    page.wait_for_selector("#mcpQuestionForm", timeout=15000)


def test_ready_status_enables_asking(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_mcp(page, local_server, READY_STATUS)

        # Pillen slar om till "Redo" nar allt ar konfigurerat.
        expect(page.locator("#mcpStatusPill")).to_have_text("Redo", timeout=15000)
        expect(page.locator("#mcpStatusPill")).to_have_class("mcp-status-pill ok")

        # Skicka + fragefaltet ar aktiverade for en behorig, redo provider.
        expect(page.locator("#mcpSend")).to_be_enabled()
        expect(page.locator("#mcpQuestion")).to_be_enabled()

        # Provider/modell/thinking-kontrollerna speglar mocken.
        expect(page.locator("#mcpProviderSelect")).to_have_value("gemini")
        expect(page.locator("#mcpModelSelect")).to_have_value("gemini-2.5-flash")
        expect(page.locator("#mcpThinkingSelect")).to_have_value("none")

        # Kontextpanelen listar resursen fran statusen.
        expect(page.locator("#mcpToolsPanel")).to_be_visible()
        expect(page.locator("#mcpToolsList")).to_contain_text("Körschema")
    finally:
        context.close()


def test_missing_config_blocks_sending(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_mcp(page, local_server, STOPPED_STATUS)

        # Saknas token/url -> pill "Stopp" och Skicka ar last.
        expect(page.locator("#mcpStatusPill")).to_have_text("Stopp", timeout=15000)
        expect(page.locator("#mcpStatusPill")).to_have_class("mcp-status-pill error")
        expect(page.locator("#mcpSend")).to_be_disabled()
        expect(page.locator("#mcpStatusText")).to_contain_text("Saknar")
    finally:
        context.close()


def test_provider_switch_resets_model_and_thinking(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_mcp(page, local_server, READY_STATUS)
        expect(page.locator("#mcpStatusPill")).to_have_text("Redo", timeout=15000)

        # Utgangslage: gemini med sina defaults.
        expect(page.locator("#mcpModelSelect")).to_have_value("gemini-2.5-flash")
        expect(page.locator("#mcpThinkingSelect")).to_have_value("none")

        # Byt provider -> modell + thinking nollstalls till openai-defaults.
        page.select_option("#mcpProviderSelect", "openai")
        expect(page.locator("#mcpProviderSelect")).to_have_value("openai")
        expect(page.locator("#mcpModelSelect")).to_have_value("gpt-4o-mini")
        expect(page.locator("#mcpThinkingSelect")).to_have_value("deep")
    finally:
        context.close()


def test_question_renders_answer_and_toast(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        open_mcp(page, local_server, READY_STATUS)
        expect(page.locator("#mcpStatusPill")).to_have_text("Redo", timeout=15000)

        # Mocka sjalva fragan sa inget riktigt LLM-anrop gors.
        page.route(
            "**/api/mcp/query**",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(QUERY_RESPONSE),
            ),
        )

        # Svarpanelen ar dold innan man fragar.
        expect(page.locator("#mcpAnswerPanel")).to_be_hidden()

        page.fill("#mcpQuestion", "Vad ar svaret?")
        page.click("#mcpSend")

        # Svaret renderas i panelen och en success-toast dyker upp.
        expect(page.locator("#mcpAnswerPanel")).to_be_visible(timeout=15000)
        expect(page.locator("#mcpAnswer")).to_contain_text("Svaret fran MCP ar 42.")
        expect(page.locator(".toast.success").last).to_contain_text("MCP svarade", timeout=15000)
        expect(page.locator("#mcpAnswerMeta")).to_contain_text("Gemini")
    finally:
        context.close()

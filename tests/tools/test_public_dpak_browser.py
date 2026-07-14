import pytest

from tools import visual_smoke
from tools.terminology_contracts import assert_no_forbidden_terms_in_text, terminology_rule


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="module")
def local_public_dpak_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("public-dpak-browser")
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


def test_public_dpak_empty_state_follows_terminology_contract(local_public_dpak_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        page.goto(f"{local_public_dpak_server}/dpak-fraga.html", wait_until="domcontentloaded")
        prompt = page.locator(".public-dpak-empty strong")
        prompt_rule = terminology_rule("public_dpak_empty_prompt")

        expect(prompt).to_have_text(prompt_rule.canonical_terms[0])
        body_text = page.locator("body").inner_text(timeout=15000)
        assert_no_forbidden_terms_in_text(body_text, context="public D-pak empty state")
    finally:
        context.close()

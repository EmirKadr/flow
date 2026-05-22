import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="module")
def local_allocation_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("allocation-split-browser")
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


def login_admin(page, base_url: str) -> None:
    page.goto(f"{base_url}/login.html", wait_until="networkidle")
    page.fill("#username", "admin")
    page.fill("#password", "admin123")
    page.click("button.primary")
    page.wait_for_url("**/index.html", timeout=15000)
    page.wait_for_selector("#scheduleTable", timeout=15000)


def test_split_values_result_headers_copy_whole_columns(local_allocation_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=local_allocation_server)
    page = context.new_page()
    try:
        login_admin(page, local_allocation_server)
        page.goto(f"{local_allocation_server}/dela.html", wait_until="networkidle")
        page.wait_for_selector('[data-flow-field="values"]', timeout=15000)
        page.fill('[data-flow-field="values"]', "A\nB\nC\nD\nE")
        page.fill('[data-flow-field="chunk_size"]', "2")
        page.click('[data-run-flow="split-values"]')
        page.wait_for_selector(".allocation-result [data-copy-column]", timeout=15000)

        header_text = page.locator(".allocation-result thead").inner_text(timeout=15000)
        assert "Kolumn 1" not in header_text
        assert "Kolumn 2" not in header_text
        assert "Kolumn 3" not in header_text
        copy_buttons = page.locator(".allocation-result [data-copy-column]")
        expect(copy_buttons).to_have_count(3)
        copy_button_contract = copy_buttons.evaluate_all(
            """(buttons) => buttons.map((button) => ({
              aria: button.getAttribute("aria-label"),
              title: button.getAttribute("title"),
              hasIcon: Boolean(button.querySelector("svg")),
              visibleText: button.textContent.trim(),
            }))"""
        )
        assert [item["title"] for item in copy_button_contract] == ["Kopiera kolumn"] * 3
        assert [item["hasIcon"] for item in copy_button_contract] == [True, True, True]
        assert [item["visibleText"] for item in copy_button_contract] == ["", "", ""]
        assert all(item["aria"].startswith("Kopiera kolumn ") for item in copy_button_contract)

        style_contract = copy_buttons.first.evaluate(
            """(button) => {
              const buttonStyle = getComputedStyle(button);
              return {
                display: buttonStyle.display,
                width: buttonStyle.width,
                height: buttonStyle.height,
                padding: buttonStyle.padding,
                textDecorationLine: buttonStyle.textDecorationLine,
              };
            }"""
        )
        assert style_contract.pop("display") in {"inline-flex", "flex"}
        assert style_contract == {
            "width": "28px",
            "height": "28px",
            "padding": "0px",
            "textDecorationLine": "none",
        }

        copy_buttons.nth(1).click()
        expect(page.locator(".toast.success")).to_have_text("Kolumn kopierad")
        copied_text = page.evaluate("navigator.clipboard.readText()")
        assert copied_text.replace("\r\n", "\n") == "C\nD"
    finally:
        context.close()

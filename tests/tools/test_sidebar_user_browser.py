import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="module")
def local_sidebar_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("sidebar-user-browser")
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


def test_sidebar_footer_shows_role_between_name_and_logout(local_sidebar_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        page.goto(f"{local_sidebar_server}/login.html", wait_until="networkidle")
        page.fill("#username", "admin")
        page.fill("#password", "admin123")
        page.click("button.primary")
        page.wait_for_url("**/index.html", timeout=15000)
        page.wait_for_selector(".sidebar-bottom .sidebar-role", timeout=15000)

        expect(page.locator(".sidebar-bottom .who")).to_have_text("Visual Admin")
        expect(page.locator(".sidebar-bottom .sidebar-role")).to_have_text("Super User, Administratör")
        expect(page.locator(".sidebar-bottom .logout")).to_have_text("Logga ut")

        order = page.locator(".sidebar-bottom > div:not(.avatar)").evaluate(
            """(container) => Array.from(container.children).map((child) => child.className || child.id)"""
        )
        assert order == ["who", "sidebar-role", "logout"]
    finally:
        context.close()


def test_sidebar_log_persists_across_view_navigation(local_sidebar_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        page.goto(f"{local_sidebar_server}/login.html", wait_until="networkidle")
        page.fill("#username", "admin")
        page.fill("#password", "admin123")
        page.click("button.primary")
        page.wait_for_url("**/index.html", timeout=15000)
        page.wait_for_selector("#log-toggle", timeout=15000)

        page.evaluate("() => window.clearAppLog()")
        page.evaluate("() => window.flowLog.success('Testlogg sparad över vybyte', 'Test')")
        page.wait_for_selector("#log-toggle.log-signal", timeout=1500)
        page.goto(f"{local_sidebar_server}/personer.html", wait_until="networkidle")
        page.wait_for_selector("#persons-body tr", timeout=15000)
        page.click("#log-toggle")

        expect(page.locator("#log-sidebar")).to_be_visible()
        expect(page.locator("#log-notice")).to_be_hidden()
        expect(page.locator("#log-sidebar")).to_contain_text("Testlogg sparad över vybyte")
        expect(page.locator("#log-sidebar")).not_to_contain_text("Öppnade vy")
        page.click("#log-sidebar-clear")
        expect(page.locator("#log-sidebar")).to_contain_text("Ingen logg")
    finally:
        context.close()


def test_sidebar_zoom_controls_and_shortcuts(local_sidebar_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        page.goto(f"{local_sidebar_server}/login.html", wait_until="networkidle")
        page.fill("#username", "admin")
        page.fill("#password", "admin123")
        page.click("button.primary")
        page.wait_for_url("**/index.html", timeout=15000)
        page.wait_for_selector("#app-zoom-control", timeout=15000)

        expect(page.locator("#app-zoom-control")).to_be_visible()
        expect(page.locator("#app-zoom-out svg")).to_be_visible()
        expect(page.locator("#app-zoom-in svg")).to_be_visible()
        expect(page.locator("#app-zoom-reset")).to_have_count(0)
        expect(page.locator("html")).to_have_attribute("data-app-zoom", "100")

        page.click("#app-zoom-in")
        expect(page.locator("html")).to_have_attribute("data-app-zoom", "110")
        assert page.evaluate("() => localStorage.getItem('flow-app-zoom')") == "110"

        page.keyboard.down("Control")
        page.keyboard.press("-")
        page.keyboard.up("Control")
        expect(page.locator("html")).to_have_attribute("data-app-zoom", "100")

        page.keyboard.down("Control")
        page.keyboard.press("=")
        page.keyboard.up("Control")
        expect(page.locator("html")).to_have_attribute("data-app-zoom", "110")

        page.keyboard.down("Control")
        page.keyboard.press("0")
        page.keyboard.up("Control")
        expect(page.locator("html")).to_have_attribute("data-app-zoom", "100")
    finally:
        context.close()


def test_sidebar_main_menu_context_menus_show_group_tabs(local_sidebar_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        page.goto(f"{local_sidebar_server}/login.html", wait_until="networkidle")
        page.fill("#username", "admin")
        page.fill("#password", "admin123")
        page.click("button.primary")
        page.wait_for_url("**/index.html", timeout=15000)
        page.wait_for_selector('[data-sidebar-view-id="staffing"]', timeout=15000)
        page.wait_for_selector('[data-sidebar-view-id="tools"]', timeout=15000)

        page.locator('[data-sidebar-view-id="tools"]').click(button="right")
        expect(page.locator(".sidebar-context-menu")).to_be_visible()
        tools_items = page.locator(".sidebar-context-menu button").evaluate_all(
            """(nodes) => nodes.map((node) => node.innerText.trim())"""
        )
        # admin ar superuser i testmiljon (SUPER_USER_USERNAMES) och ser aven Arkivstatus.
        assert tools_items == ["Dela", "Etiketter", "MCP", "Hämta data", "Historik", "Meta", "Arkivstatus", "Buggrapporter"]

        page.mouse.click(1, 1)
        expect(page.locator(".sidebar-context-menu")).to_have_count(0)

        page.locator('[data-sidebar-view-id="staffing"]').click(button="right")
        expect(page.locator(".sidebar-context-menu")).to_be_visible()
        staffing_items = page.locator(".sidebar-context-menu button").evaluate_all(
            """(nodes) => nodes.map((node) => node.innerText.trim())"""
        )
        assert staffing_items == [
            "Bemanning",
            "Översikt",
            "Produktivitet",
            "Sankey",
            "Aktiviteter",
            "Personer",
            "Användare",
            "Verksamheter",
            "Mitt schema",
            "Min produktivitet",
        ]

        page.mouse.click(1, 1)
        expect(page.locator(".sidebar-context-menu")).to_have_count(0)

        page.wait_for_selector('[data-sidebar-view-id="allocationSettings"]', timeout=15000)
        page.locator('[data-sidebar-view-id="allocationSettings"]').click(button="right")
        expect(page.locator(".sidebar-context-menu")).to_be_visible()
        settings_items = page.locator(".sidebar-context-menu button").evaluate_all(
            """(nodes) => nodes.map((node) => node.innerText.trim())"""
        )
        assert settings_items == ["Ytkarta", "Bearbeta", "Bemanning", "Intäkt/utgift"]

        page.get_by_role("menuitem", name="Bemanning").click()
        page.wait_for_url("**/installningar.html?tab=staffing", timeout=15000)
        expect(page.locator('[data-settings-tab="staffing"]')).to_have_attribute("aria-selected", "true")
    finally:
        context.close()


def test_area_focus_context_menu_respects_business_scope(local_sidebar_server, chromium_browser):
    admin_context = chromium_browser.new_context(locale="sv-SE")
    admin_page = admin_context.new_page()
    try:
        admin_page.goto(f"{local_sidebar_server}/login.html", wait_until="networkidle")
        admin_page.fill("#username", "admin")
        admin_page.fill("#password", "admin123")
        admin_page.click("button.primary")
        admin_page.wait_for_url("**/index.html", timeout=15000)
        admin_page.wait_for_selector("#area-focus-toggle", timeout=15000)
        expect(admin_page.locator("#area-focus-toggle")).to_be_enabled(timeout=15000)
        admin_page.locator("#area-focus-toggle").click(button="right")
        expect(admin_page.locator(".area-focus-menu")).to_be_visible()
        expect(admin_page.locator(".area-focus-menu button").first).to_be_visible()
        admin_page.locator(".area-focus-menu").evaluate(
            """(menu) => {
                menu.scrollTop = 80;
                menu.dispatchEvent(new Event("scroll", { bubbles: false }));
                menu.dispatchEvent(new MouseEvent("click", { bubbles: true }));
            }"""
        )
        expect(admin_page.locator(".area-focus-menu")).to_be_visible()

        admin_items = admin_page.locator(".area-focus-menu button").evaluate_all(
            """(nodes) => nodes.map((node) => ({ value: node.dataset.value, text: node.innerText }))"""
        )
        admin_text = "\n".join(item["text"] for item in admin_items)
        assert "Granngården" in admin_text
        assert "Mestergruppen" in admin_text
        assert "Autostore" in admin_text
        assert "E-Handel" in admin_text
        assert "R3" in admin_text
        assert "Alla områden" in admin_text

        admin_page.locator(".area-focus-menu button", has_text="Mestergruppen").click()
        expect(admin_page.locator("#area-focus-toggle")).to_have_text("MG")
        assert str(admin_page.evaluate("() => localStorage.getItem('flow-area-focus')")).startswith("AREA:")

        admin_page.evaluate(
            """async () => {
                const businessesResponse = await fetch('/api/businesses?include_inactive=true', { credentials: 'include' });
                const businesses = await businessesResponse.json();
                const r3 = businesses.find((business) => business.code === 'R3');
                const areasResponse = await fetch(`/api/areas?include_inactive=true&business_id=${r3.id}`, { credentials: 'include' });
                const areas = await areasResponse.json();
                const marker = areas.find((area) => area.code === 'ANNAT');
                const payload = { business_id: r3.id, code: 'ANNAT', name: 'Annat', sort_order: 99, is_active: true };
                if (marker) {
                    await fetch(`/api/areas/${marker.id}`, {
                        method: 'PUT',
                        credentials: 'include',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                    });
                } else {
                    await fetch('/api/areas', {
                        method: 'POST',
                        credentials: 'include',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                    });
                }
            }"""
        )
    finally:
        admin_context.close()

    r3_context = chromium_browser.new_context(locale="sv-SE")
    r3_page = r3_context.new_page()
    try:
        r3_page.goto(f"{local_sidebar_server}/login.html", wait_until="networkidle")
        r3_page.fill("#username", "visual_r3_admin")
        r3_page.fill("#password", visual_smoke.VISUAL_PASSWORD)
        r3_page.click("button.primary")
        r3_page.wait_for_url("**/index.html", timeout=15000)
        expect(r3_page.locator("#area-focus-toggle")).to_be_enabled(timeout=15000)
        expect(r3_page.locator("#area-focus-toggle")).to_have_attribute("data-value", "ALLT")

        r3_page.locator("#area-focus-toggle").click(button="right")
        expect(r3_page.locator(".area-focus-menu")).to_be_visible()
        expect(r3_page.locator(".area-focus-menu button").first).to_be_visible()
        r3_items = r3_page.locator(".area-focus-menu button").evaluate_all(
            """(nodes) => nodes.map((node) => ({ value: node.dataset.value, text: node.innerText }))"""
        )
        r3_text = "\n".join(item["text"] for item in r3_items)
        assert "R3" in r3_text
        assert "Alla" in r3_text
        assert any(item["value"].startswith("AREA:") for item in r3_items)
        assert any(item["value"] == "ALLT" for item in r3_items)
    finally:
        r3_context.close()


def test_business_focus_toggle_filters_area_menu_for_super_user(local_sidebar_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        page.goto(f"{local_sidebar_server}/login.html", wait_until="networkidle")
        page.fill("#username", "admin")
        page.fill("#password", "admin123")
        page.click("button.primary")
        page.wait_for_url("**/index.html", timeout=15000)

        toggle = page.locator("#business-focus-toggle")
        expect(toggle).to_be_enabled(timeout=15000)
        expect(toggle).to_have_attribute("data-value", "ALLT")
        expect(toggle).to_have_text("∞")

        # Sätt områdesfokus på ett Stigamo-område först
        expect(page.locator("#area-focus-toggle")).to_be_enabled(timeout=15000)
        page.locator("#area-focus-toggle").click(button="right")
        expect(page.locator(".area-focus-menu")).to_be_visible()
        page.locator(".area-focus-menu button", has_text="Mestergruppen").click()
        expect(page.locator("#area-focus-toggle")).to_have_text("MG")

        # Välj verksamheten R3 i verksamhetsmenyn
        toggle.click(button="right")
        expect(page.locator(".business-focus-menu")).to_be_visible()
        business_items = page.locator(".business-focus-menu button").evaluate_all(
            """(nodes) => nodes.map((node) => ({ value: node.dataset.value, text: node.innerText }))"""
        )
        business_text = "\n".join(item["text"] for item in business_items)
        assert "Alla verksamheter" in business_text
        assert "R3" in business_text
        assert any(item["value"].startswith("BIZ:") for item in business_items)
        page.locator(".business-focus-menu button", has_text="R3").first.click()
        expect(page.locator(".business-focus-menu")).to_have_count(0)
        expect(toggle).to_have_text("R3")
        assert str(page.evaluate("() => localStorage.getItem('flow-business-focus')")).startswith("BIZ:")

        # Områdesfokus på MG hör inte till R3 och ska ha nollställts till ∞
        expect(page.locator("#area-focus-toggle")).to_have_attribute("data-value", "ALLT")

        # Områdesmenyn ska bara visa R3:s områden plus Alla områden
        page.locator("#area-focus-toggle").click(button="right")
        expect(page.locator(".area-focus-menu")).to_be_visible()
        expect(page.locator(".area-focus-menu button").first).to_be_visible()
        area_items = page.locator(".area-focus-menu button").evaluate_all(
            """(nodes) => nodes.map((node) => node.innerText)"""
        )
        area_text = "\n".join(area_items)
        assert "Granngården" not in area_text
        assert "Mestergruppen" not in area_text
        assert "Alla områden" in area_text
        page.keyboard.press("Escape")

        # Tillbaka till alla verksamheter: alla områden ska synas igen
        toggle.click(button="right")
        expect(page.locator(".business-focus-menu")).to_be_visible()
        page.locator(".business-focus-menu button", has_text="Alla verksamheter").click()
        expect(toggle).to_have_attribute("data-value", "ALLT")
        page.locator("#area-focus-toggle").click(button="right")
        expect(page.locator(".area-focus-menu")).to_be_visible()
        all_items = page.locator(".area-focus-menu button").evaluate_all(
            """(nodes) => nodes.map((node) => node.innerText)"""
        )
        assert "Granngården" in "\n".join(all_items)
    finally:
        context.close()


def test_business_focus_toggle_hidden_for_non_super_user(local_sidebar_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        page.goto(f"{local_sidebar_server}/login.html", wait_until="networkidle")
        page.fill("#username", "visual_r3_admin")
        page.fill("#password", visual_smoke.VISUAL_PASSWORD)
        page.click("button.primary")
        page.wait_for_url("**/index.html", timeout=15000)
        expect(page.locator("#area-focus-toggle")).to_be_enabled(timeout=15000)
        expect(page.locator("#business-focus-toggle")).to_have_count(0)
    finally:
        context.close()


def test_area_focus_does_not_fallback_to_hardcoded_areas(local_sidebar_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        page.route(
            "**/api/areas**",
            lambda route: route.fulfill(
                status=503,
                headers={"content-type": "application/json"},
                body='{"detail":"areas unavailable"}',
            ),
        )
        page.goto(f"{local_sidebar_server}/login.html", wait_until="networkidle")
        page.fill("#username", "admin")
        page.fill("#password", "admin123")
        page.click("button.primary")
        page.wait_for_url("**/index.html", timeout=15000)
        toggle = page.locator("#area-focus-toggle")
        expect(toggle).to_be_disabled(timeout=15000)
        expect(toggle).to_have_text("!")
        expect(toggle).to_have_attribute("data-value", "")
        expect(toggle).to_have_attribute("aria-label", "Områdesfokus: Områden kunde inte läsas")
    finally:
        context.close()

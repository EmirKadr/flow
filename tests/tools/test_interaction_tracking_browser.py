import json

import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="module")
def local_tracking_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("interaction-tracking-browser")
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


def captured_interaction_events(batches: list[dict]) -> list[dict]:
    return [item for batch in batches for item in batch.get("items", [])]


def collect_interaction_batches(page, batches: list[dict]) -> None:
    def capture(route):
        body = route.request.post_data or "{}"
        batches.append(json.loads(body))
        route.fulfill(status=204, body="")

    page.route("**/api/audit/interactions", capture)


def seed_tracking_events(page) -> None:
    page.evaluate(
        """async () => {
          const response = await fetch("/api/audit/interactions", {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              items: [
                {
                  event_type: "auto_copy_column",
                  view_id: "allocationProcess",
                  control_id: "allocation-copy-column",
                  control_label: "Kopiera kolumn",
                  feature: "allocation",
                  flow_id: "pafyllnadsprio",
                  table_key: "complete",
                  table_label: "Prioritering",
                  column_index: 0,
                  column_label: "Order",
                  row_count: 8,
                  client_surface: "desktop",
                  detail: { copy_mode: "first_column" }
                },
                {
                  event_type: "copy_column",
                  view_id: "allocationProcess",
                  control_id: "allocation-copy-column",
                  control_label: "Kopiera kolumn",
                  feature: "allocation",
                  flow_id: "pafyllnadsprio",
                  table_key: "complete",
                  table_label: "Prioritering",
                  column_index: 1,
                  column_label: "Kund",
                  row_count: 8,
                  client_surface: "web",
                  detail: { copy_mode: "multi_column" }
                },
                {
                  event_type: "api_request",
                  view_id: "allocationProcess",
                  control_id: "allocation-flow-run",
                  control_label: "Kör flöde",
                  feature: "allocation",
                  flow_id: "forecast",
                  client_surface: "web",
                  status: "error",
                  detail: { api_route: "/api/allokering/flow/forecast", status_code: 400, error_code: "allocation_flow_failed" }
                }
              ]
            })
          });
          if (!response.ok) throw new Error(`seed failed ${response.status}`);
        }"""
    )


def test_click_select_submit_and_api_result_are_tracked(local_tracking_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    batches: list[dict] = []
    try:
        login_admin(page, local_tracking_server)
        collect_interaction_batches(page, batches)
        page.route(
            "**/api/test-tracking",
            lambda route: route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body='{"ok":true}',
            ),
        )

        page.goto(f"{local_tracking_server}/historik.html", wait_until="networkidle")
        page.wait_for_selector("#periodSelect", timeout=15000)
        page.select_option("#periodSelect", "all")
        page.evaluate(
            """() => {
              const form = document.createElement("form");
              form.id = "tracking-test-form";
              form.style.marginTop = "24px";
              form.innerHTML = '<button id="tracking-test-api" type="submit" data-track-id="tracking-test-api" data-track-label="Tracking API test">Kör API-test</button>';
              form.addEventListener("submit", async (event) => {
                event.preventDefault();
                await window.api.post("/api/test-tracking", { privateField: "VALUE_TO_DROP" }, { logUserEvent: false });
              });
              document.querySelector("main")?.appendChild(form);
            }"""
        )

        with page.expect_response("**/api/test-tracking"):
            page.click("#tracking-test-api")
        page.evaluate("() => window.flowFlushInteractions()")
        page.wait_for_timeout(300)

        events = captured_interaction_events(batches)
        assert any(event["event_type"] == "change" and event["control_id"] == "periodSelect" for event in events)
        action_events = [
            event
            for event in events
            if event["event_type"] in {"click", "submit"} and event["control_id"] in {"tracking-test-api", "tracking-test-form"}
        ]
        assert action_events
        api_events = [
            event
            for event in events
            if event["event_type"] == "api_request" and event.get("detail", {}).get("api_route") == "/api/test-tracking"
        ]
        assert len(api_events) == 1
        assert api_events[0]["interaction_id"] in {event["interaction_id"] for event in action_events}
        assert api_events[0]["status"] == "ok"
        assert api_events[0]["detail"]["status_code"] == 200
        assert "VALUE_TO_DROP" not in json.dumps(api_events[0], ensure_ascii=False)
    finally:
        context.close()


def test_download_tracking_links_export_to_current_click(local_tracking_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE", accept_downloads=True)
    page = context.new_page()
    batches: list[dict] = []
    try:
        login_admin(page, local_tracking_server)
        collect_interaction_batches(page, batches)
        page.route(
            "**/api/test-download",
            lambda route: route.fulfill(
                status=200,
                headers={
                    "content-type": "text/csv",
                    "content-disposition": "attachment; filename=test-export.csv",
                },
                body="A,B\n1,2\n",
            ),
        )
        page.goto(f"{local_tracking_server}/historik.html", wait_until="networkidle")
        page.evaluate(
            """() => {
              const button = document.createElement("button");
              button.id = "tracking-test-download";
              button.dataset.trackId = "tracking-test-download";
              button.dataset.trackLabel = "Tracking export test";
              button.textContent = "Exportera test";
              button.style.marginTop = "24px";
              button.addEventListener("click", async () => {
                await window.api.download("/api/test-download", "fallback.csv");
              });
              document.querySelector("main")?.appendChild(button);
            }"""
        )

        with page.expect_response("**/api/test-download"):
            page.click("#tracking-test-download")
        page.evaluate("() => window.flowFlushInteractions()")
        page.wait_for_timeout(300)

        events = captured_interaction_events(batches)
        click = next(event for event in events if event["event_type"] == "click" and event["control_id"] == "tracking-test-download")
        download = next(
            event
            for event in events
            if event["event_type"] == "download" and event.get("detail", {}).get("api_route") == "/api/test-download"
        )
        assert download["interaction_id"] == click["interaction_id"]
        assert download["status"] == "ok"
        assert download["detail"]["status_code"] == 200
        assert "test-export.csv" not in json.dumps(download, ensure_ascii=False)
    finally:
        context.close()


def test_history_tracking_dashboards_render_column_copy_patterns(local_tracking_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login_admin(page, local_tracking_server)
        seed_tracking_events(page)
        page.goto(f"{local_tracking_server}/historik.html", wait_until="networkidle")
        page.wait_for_selector("#auditBody", timeout=15000)

        page.click('[data-history-mode="functions"]')
        expect(page.locator("#trackingTopFeaturesBody")).to_contain_text("allocation", timeout=15000)
        expect(page.locator("#trackingTopSurfacesBody")).to_contain_text("desktop", timeout=15000)

        page.click('[data-history-mode="buttons"]')
        expect(page.locator("#trackingTopControlsBody")).to_contain_text("Kopiera kolumn", timeout=15000)
        expect(page.locator("#trackingButtonCopyPatternsBody")).to_contain_text("first_column", timeout=15000)
        expect(page.locator("#trackingButtonCopyPatternsBody")).to_contain_text("multi_column", timeout=15000)

        page.click('[data-history-mode="columns"]')
        expect(page.locator("#trackingTopColumnsBody")).to_contain_text("Prioritering / Order", timeout=15000)
        expect(page.locator("#trackingTopColumnsBody")).to_contain_text("Prioritering / Kund", timeout=15000)

        page.click('[data-history-mode="flows"]')
        expect(page.locator("#trackingTopFlowsBody")).to_contain_text("pafyllnadsprio", timeout=15000)
        expect(page.locator("#trackingFlowColumnsBody")).to_contain_text("Prioritering / Order", timeout=15000)
    finally:
        context.close()


def test_history_tracking_ai_panel_uses_history_only_endpoint(local_tracking_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    chat_payloads: list[dict] = []
    try:
        login_admin(page, local_tracking_server)

        def answer_chat(route):
            chat_payloads.append(json.loads(route.request.post_data or "{}"))
            route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        "answer": "Påfyllnadsprio kopierar både första och flera kolumner i testdatan.",
                        "event_count": 3,
                    },
                    ensure_ascii=False,
                ),
            )

        page.route("**/api/audit/interactions/chat", answer_chat)
        page.goto(f"{local_tracking_server}/historik.html", wait_until="networkidle")
        page.click('[data-history-mode="tracking-ai"]')
        page.fill("#historyTrackingQuestion", "Kopierar folk första kolumnen i Påfyllnadsprio eller flera?")
        page.click('#historyTrackingChatForm button[type="submit"]')

        expect(page.locator("#historyTrackingChatAnswer")).to_contain_text("Påfyllnadsprio", timeout=15000)
        assert chat_payloads
        assert chat_payloads[0]["question"].startswith("Kopierar folk")
        assert chat_payloads[0]["period"]
    finally:
        context.close()


def test_desktop_surface_marks_web_tracking_as_desktop(local_tracking_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    context.add_init_script(
        """(() => {
          window.qt = { webChannelTransport: {} };
          window.QWebChannel = function (_transport, callback) {
            callback({
              objects: {
                flowDesktopBridge: {
                  chooseFiles: (_accept, _multiple, done) => done([
                    { fileType: "text/csv", localRef: "VALUE_TO_DROP", name: "drop-file.csv", path: "C:/example/drop-file.csv" }
                  ])
                }
              }
            });
          };
        })();"""
    )
    page = context.new_page()
    batches: list[dict] = []
    try:
        login_admin(page, local_tracking_server)
        collect_interaction_batches(page, batches)
        page.goto(f"{local_tracking_server}/uppladdningar.html", wait_until="networkidle")
        page.wait_for_function("() => window.flowDesktop?.isDesktop?.() === true", timeout=15000)
        page.evaluate("""async () => { await window.flowDesktop.pickFiles({ accept: ".csv", multiple: true }); }""")
        page.evaluate("() => window.flowFlushInteractions()")
        page.wait_for_timeout(300)

        events = captured_interaction_events(batches)
        desktop_events = [event for event in events if event.get("client_surface") == "desktop"]
        assert desktop_events
        file_select = next(event for event in desktop_events if event["event_type"] == "desktop_file_select")
        assert file_select["detail"]["file_count"] == 1
        assert file_select["detail"]["file_types"] == ["text/csv"]
        text = json.dumps(file_select, ensure_ascii=False)
        assert "drop-file" not in text
        assert "VALUE_TO_DROP" not in text
        assert "C:/example" not in text
    finally:
        context.close()

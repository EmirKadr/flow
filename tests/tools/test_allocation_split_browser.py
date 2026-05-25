import json

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


def seed_allocation_file_pool(page) -> None:
    page.evaluate(
        """async (entries) => {
          const db = await new Promise((resolve, reject) => {
            const request = indexedDB.open("flow-allokering-files", 1);
            request.onupgradeneeded = () => {
              const db = request.result;
              if (!db.objectStoreNames.contains("files")) {
                db.createObjectStore("files", { keyPath: "key" });
              }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          await new Promise((resolve, reject) => {
            const tx = db.transaction("files", "readwrite");
            const store = tx.objectStore("files");
            for (const entry of entries) {
              const blob = new Blob([entry.content], { type: entry.type });
              store.put({
                key: entry.key,
                name: entry.name,
                size: entry.content.length,
                type: entry.type,
                lastModified: entry.lastModified,
                blob,
              });
            }
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
          });
          db.close();
        }""",
        [
            {
                "key": "orders",
                "name": "v_ask_customer_order_details_all-test.csv",
                "type": "text/csv",
                "lastModified": 1,
                "content": "Artikel\tAntal\nA-1\t1\n",
            },
            {
                "key": "buffer",
                "name": "v_ask_article_buffertpallet-test.csv",
                "type": "text/csv",
                "lastModified": 2,
                "content": "Artikel\tAntal\nA-1\t1\n",
            },
            {
                "key": "overview",
                "name": "v_ask_order_overview-test.csv",
                "type": "text/csv",
                "lastModified": 3,
                "content": "Ordernr\tSändningsnr\nO-1\tS-1\n",
            },
        ],
    )


def seed_upload_store(page, db_name: str, entries: list[dict]) -> None:
    page.evaluate(
        """async ({ dbName, entries }) => {
          const db = await new Promise((resolve, reject) => {
            const request = indexedDB.open(dbName, 1);
            request.onupgradeneeded = () => {
              const db = request.result;
              if (!db.objectStoreNames.contains("files")) {
                db.createObjectStore("files", { keyPath: "key" });
              }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          await new Promise((resolve, reject) => {
            const tx = db.transaction("files", "readwrite");
            const store = tx.objectStore("files");
            for (const entry of entries) {
              const blob = new Blob([entry.content || "x"], { type: entry.type || "text/csv" });
              store.put({
                key: entry.key,
                name: entry.name || `${entry.key}.csv`,
                size: blob.size,
                type: blob.type,
                lastModified: entry.lastModified || 1,
                blob,
              });
            }
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
          });
          db.close();
        }""",
        {"dbName": db_name, "entries": entries},
    )


def upload_store_keys(page, db_name: str) -> list[str]:
    return page.evaluate(
        """async (dbName) => {
          const db = await new Promise((resolve, reject) => {
            const request = indexedDB.open(dbName, 1);
            request.onupgradeneeded = () => {
              const db = request.result;
              if (!db.objectStoreNames.contains("files")) {
                db.createObjectStore("files", { keyPath: "key" });
              }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          const keys = await new Promise((resolve, reject) => {
            const tx = db.transaction("files", "readonly");
            const request = tx.objectStore("files").getAllKeys();
            request.onsuccess = () => resolve(request.result.map(String).sort());
            request.onerror = () => reject(request.error);
          });
          db.close();
          return keys;
        }""",
        db_name,
    )


def mock_forecast_coredata(page) -> None:
    uploaded = {
        key: {
            "uploaded": True,
            "name": f"{key}-test.csv",
            "prefix": key,
            "path": f"coredata/{key}-test.csv",
        }
        for key in (
            "custom",
            "item",
            "item_alias",
            "dimension",
            "pallet_type",
            "item_option",
            "location",
        )
    }
    page.route(
        "**/api/coredata/files",
        lambda route: route.fulfill(
            status=200,
            headers={"content-type": "application/json"},
            body=json.dumps({"files": uploaded}, ensure_ascii=False),
        ),
    )


def test_clear_all_uploads_keeps_core_file_entries(local_allocation_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login_admin(page, local_allocation_server)
        seed_upload_store(
            page,
            "flow-allokering-files",
            [
                {"key": "orders", "name": "orders.csv"},
                {"key": "buffer", "name": "buffer.csv"},
                {"key": "max_csv", "name": "artikel_max.csv"},
                {"key": "item_option", "name": "item_option.csv"},
            ],
        )
        seed_upload_store(
            page,
            "flow-productivity-files",
            [
                {"key": "pick", "name": "v_ask_pick_log_full.csv"},
                {"key": "kpi", "name": "v_ask_kpi_target.csv"},
            ],
        )

        assert page.evaluate("window.clearAllUploadedFiles({ confirmUser: false })") is True

        assert upload_store_keys(page, "flow-allokering-files") == ["item_option", "max_csv"]
        assert upload_store_keys(page, "flow-productivity-files") == ["kpi"]
        expect(page.locator(".toast.success").last).to_contain_text("Kärnfiler ligger kvar")
    finally:
        context.close()


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

        page.goto(f"{local_allocation_server}/index.html", wait_until="networkidle")
        page.wait_for_selector("#scheduleTable", timeout=15000)
        page.goto(f"{local_allocation_server}/dela.html", wait_until="networkidle")
        page.wait_for_selector(".allocation-result [data-copy-column]", timeout=15000)

        expect(page.locator('[data-flow-field="values"]')).to_have_value("A\nB\nC\nD\nE")
        expect(page.locator('[data-flow-field="chunk_size"]')).to_have_value("2")
        expect(page.locator(".allocation-result")).to_contain_text("C")
    finally:
        context.close()


def test_process_result_survives_view_switch(local_allocation_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login_admin(page, local_allocation_server)
        seed_allocation_file_pool(page)
        page.route(
            "**/api/allokering/flow/allocate",
            lambda route: route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        "flow_id": "allocate",
                        "session_id": "persisted-allocate-session",
                        "display_summary": {"Allokerade pallar": 1},
                        "summary": {},
                        "tables": [
                            {
                                "key": "allocated",
                                "label": "Allokerade pallar",
                                "table": {
                                    "columns": ["Order", "Pall"],
                                    "rows": [["O-1", "P-1"]],
                                    "row_count": 1,
                                    "truncated": False,
                                },
                            }
                        ],
                        "log": [],
                    },
                    ensure_ascii=False,
                ),
            ),
        )

        page.goto(f"{local_allocation_server}/bearbeta.html", wait_until="networkidle")
        page.wait_for_selector('button[data-run-flow="allocate"]:not([disabled])', timeout=15000)
        page.click('button[data-run-flow="allocate"]')
        page.wait_for_selector(".allocation-result [data-copy-column]", timeout=15000)
        expect(page.locator(".allocation-result")).to_contain_text("O-1")

        page.goto(f"{local_allocation_server}/historik.html", wait_until="networkidle")
        page.wait_for_selector("#auditBody", timeout=15000)
        page.goto(f"{local_allocation_server}/bearbeta.html", wait_until="networkidle")
        page.wait_for_selector(".allocation-result [data-copy-column]", timeout=15000)

        expect(page.locator(".allocation-result h2")).to_have_text("Resultat - Allokering")
        expect(page.locator(".allocation-result")).to_contain_text("O-1")
        expect(page.locator("#allocationRoot")).to_contain_text("Klart: Allokering")
    finally:
        context.close()


def test_forecast_enables_ytgenerering_button_and_passes_session(local_allocation_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    captured = {}
    try:
        login_admin(page, local_allocation_server)
        seed_allocation_file_pool(page)
        mock_forecast_coredata(page)

        page.route(
            "**/api/allokering/flow/forecast",
            lambda route: route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        "flow_id": "forecast",
                        "session_id": "forecast-session-1",
                        "summary": {"Sändningar": 1, "Predikterade pallplatser": 2.5},
                        "tables": [
                            {
                                "key": "forecast",
                                "label": "Forecast",
                                "table": {
                                    "columns": ["Sändningsnr", "Transportör", "Predikterade pallplatser"],
                                    "rows": [["S-1", "Akeri A", "2.5"]],
                                    "row_count": 1,
                                    "truncated": False,
                                },
                            }
                        ],
                        "log": [],
                        "artifact_keys": ["forecast_json"],
                    },
                    ensure_ascii=False,
                ),
            ),
        )

        def handle_ytgenerering(route):
            post_data = route.request.post_data or ""
            captured["post_data"] = post_data
            route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        "flow_id": "ytgenerering",
                        "session_id": "ytgenerering-session-1",
                        "summary": {"Sändningar": 1, "Använda lagerplatser": 1},
                        "tables": [
                            {
                                "key": "ytgenerering",
                                "label": "Ytgenerering",
                                "table": {
                                    "columns": ["Sändningsnr", "Transportör", "Lagerplats"],
                                    "rows": [["S-1", "Akeri A", "UTL100"]],
                                    "row_count": 1,
                                    "truncated": False,
                                },
                            }
                        ],
                        "log": [],
                    },
                    ensure_ascii=False,
                ),
            )

        page.route("**/api/allokering/flow/ytgenerering", handle_ytgenerering)

        page.goto(f"{local_allocation_server}/bearbeta.html", wait_until="networkidle")
        forecast_button = page.locator('button[data-run-flow="forecast"]')
        ytgenerering_button = page.locator('button[data-run-flow="ytgenerering"]')
        expect(forecast_button).to_be_enabled(timeout=15000)
        expect(ytgenerering_button).to_be_disabled()

        forecast_button.click()
        page.wait_for_selector(".allocation-result [data-copy-column]", timeout=15000)
        expect(page.locator(".allocation-result h2")).to_have_text("Resultat - Forecast")
        expect(page.locator(".allocation-result")).to_contain_text("S-1")
        expect(ytgenerering_button).to_be_enabled(timeout=15000)

        ytgenerering_button.click()
        page.wait_for_selector(".allocation-result [data-copy-column]", timeout=15000)
        expect(page.locator(".allocation-result h2")).to_have_text("Resultat - Ytgenerering")
        expect(page.locator(".allocation-result")).to_contain_text("UTL100")
        assert "forecast-session-1" in captured["post_data"]
        assert 'name="forecast_session_id"' in captured["post_data"]
    finally:
        context.close()

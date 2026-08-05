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
    page.goto(f"{base_url}/login.html", wait_until="domcontentloaded")
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
            "trans_agency",
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

        assert page.evaluate("window.clearAllUploadedFiles({ confirmUser: false })") is True

        assert upload_store_keys(page, "flow-allokering-files") == ["item_option", "max_csv"]
        assert page.evaluate("window.productivityUploads === undefined") is True
        expect(page.locator(".toast.success").last).to_contain_text("Kärnfiler och sammanställd data ligger kvar")
    finally:
        context.close()


def test_uploads_page_does_not_load_productivity_upload_sync(local_allocation_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login_admin(page, local_allocation_server)
        page.goto(f"{local_allocation_server}/uppladdningar.html", wait_until="domcontentloaded")
        page.wait_for_selector("#allocation-clear-all-files", timeout=15000)

        assert page.evaluate("window.productivityUploads === undefined") is True
        assert page.evaluate("typeof window.sharedAllocationUploads?.saveFiles === 'function'") is True
        assert upload_store_keys(page, "flow-allokering-files") == []
    finally:
        context.close()


def test_schedule_cell_right_click_splits_and_double_click_opens_activity_picker(local_allocation_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login_admin(page, local_allocation_server)
        page.wait_for_selector("#scheduleBody tr", timeout=15000)
        cell = page.locator("#scheduleBody td[data-hour][data-split='0']:not(.locked-cell)").filter(
            has=page.locator("select.cell-select:not(:disabled)")
        ).first
        expect(cell).to_be_visible(timeout=15000)
        cell_key = cell.evaluate("""(el) => ({ personId: el.dataset.personId, hour: el.dataset.hour })""")
        cell_selector = f'#scheduleBody td[data-person-id="{cell_key["personId"]}"][data-hour="{cell_key["hour"]}"]'
        cell = page.locator(cell_selector)

        cell.click(button="right")
        expect(page.locator(".schedule-cell-context-menu")).to_be_visible(timeout=15000)
        expect(page.get_by_role("menuitem", name="Dela")).to_be_visible()
        expect(page.get_by_role("menuitem", name="Anmärkning")).to_be_visible()
        page.get_by_role("menuitem", name="Dela").click()
        expect(page.locator("#scheduleSplitContinue")).to_be_visible(timeout=15000)
        page.click("#scheduleSplitCancel")
        expect(page.locator(".modal-backdrop")).to_have_count(0)

        cell.click(button="right")
        page.get_by_role("menuitem", name="Anmärkning").click()
        expect(page.locator("#scheduleRemarkInput")).to_be_visible(timeout=15000)
        page.fill("#scheduleRemarkInput", "Behöver kollas")
        page.click("#scheduleRemarkSave")
        expect(page.locator(".modal-backdrop")).to_have_count(0)
        page.wait_for_function(
            """(selector) => document.querySelector(selector)?.classList.contains("has-remark") === true""",
            arg=cell_selector,
            timeout=15000,
        )

        cell.dblclick()
        cell_handle = cell.element_handle()
        page.wait_for_function(
            """(cell) => cell.querySelector("select.cell-select")?.dataset.activityOptionsLoaded === "1" """,
            arg=cell_handle,
            timeout=15000,
        )
        expect(page.locator(".schedule-cell-context-menu")).to_have_count(0)
        expect(page.locator("#scheduleSplitContinue")).to_have_count(0)
    finally:
        context.close()


@pytest.mark.parametrize("app_zoom", [70, 100, 140])
def test_schedule_context_menu_opens_at_the_pointer_for_every_app_zoom(
    local_allocation_server, chromium_browser, app_zoom
):
    """Menyn ska dyka upp vid högerklicket, inte förskjuten av appzoomen.

    Zoomen ligger som `zoom` på <body> och ärvs av fixed-menyn: skrivs ett
    viewport-värde rakt in i style.left hamnar menyn `zoom` gånger för nära
    origo. Vid 70 % dök menyn upp uppe till vänster om pekaren (2026-08-04).

    Bredare viewport än standard: schemats etikettkolumner är breda, och vid
    140 % ligger även den vänstraste timcellen så långt in att en 215 px bred
    meny inte får plats på de 1280 px Playwright ger som standard. Då mäter
    testet klampning mot kanten i stället för placering vid pekaren. Bredden
    är alltså en förutsättning för att kunna mäta det testet handlar om.
    """
    context = chromium_browser.new_context(
        locale="sv-SE",
        viewport={"width": 1600, "height": 1000},
    )
    page = context.new_page()
    try:
        login_admin(page, local_allocation_server)
        page.wait_for_selector("#scheduleBody tr", timeout=15000)
        page.evaluate("(percent) => applyAppZoom(percent, { persist: false })", app_zoom)

        cells = page.locator("#scheduleBody td[data-hour][data-split='0']:not(.locked-cell)").filter(
            has=page.locator("select.cell-select:not(:disabled)")
        )
        expect(cells.first).to_be_visible(timeout=15000)

        # Zoomen flyttar cellerna: schemats etikettkolumner ar breda, sa vid 140 %
        # borjar forsta timcellen redan runt x=1000 och tabellen scrollar ut langt
        # till hoger. Blint .first gav da en cell sa nara hogerkanten att menyn inte
        # fick plats, och guarden nedan foll innan placeringen ens mattes. Valj
        # darfor cellen langst upp till vanster - den som lamnar mest rum - och lat
        # guarden med den uppmatta menyn avgora om marginalen racker.
        viewport = page.viewport_size

        cell = None
        click_x = click_y = 0.0
        for candidate in cells.all():
            box = candidate.bounding_box()
            if not box:
                continue
            center_x = box["x"] + box["width"] / 2
            center_y = box["y"] + box["height"] / 2
            if cell is None or (center_x, center_y) < (click_x, click_y):
                cell, click_x, click_y = candidate, center_x, center_y

        assert cell is not None, (
            f"zoom {app_zoom}%: hittade ingen klickbar schemacell i viewport {viewport}"
        )
        page.mouse.click(click_x, click_y, button="right")

        menu = page.locator(".schedule-cell-context-menu")
        expect(menu).to_be_visible(timeout=15000)
        menu_box = menu.bounding_box()

        clamped_x = click_x + menu_box["width"] + 8 > viewport["width"]
        clamped_y = click_y + menu_box["height"] + 8 > viewport["height"]
        assert not clamped_x and not clamped_y, (
            "Testcellen ligger for nara kanten for att sarskilja placering fran klampning: "
            f"klick=({click_x:.0f}, {click_y:.0f}) meny={menu_box} viewport={viewport}"
        )
        assert abs(menu_box["x"] - click_x) <= 2, (
            f"zoom {app_zoom}%: menyn hamnade pa x={menu_box['x']:.0f}, klicket var pa {click_x:.0f}"
        )
        assert abs(menu_box["y"] - click_y) <= 2, (
            f"zoom {app_zoom}%: menyn hamnade pa y={menu_box['y']:.0f}, klicket var pa {click_y:.0f}"
        )
    finally:
        context.close()


def test_split_values_result_headers_copy_whole_columns(local_allocation_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=local_allocation_server)
    page = context.new_page()
    try:
        login_admin(page, local_allocation_server)
        page.goto(f"{local_allocation_server}/dela.html", wait_until="domcontentloaded")
        # Stilkontraktet nedan läser getComputedStyle - vänta in stylesheets
        # så CSS-laddningsracet inte ger falska mått på långsam/lastad maskin
        # (rotorsaksanalys 2026-07-06: full-svit-flake under I/O-last).
        page.wait_for_load_state("load")
        page.wait_for_selector('[data-flow-field="values"]', timeout=15000)
        page.fill('[data-flow-field="values"]', "A\nB\nC\nD\nE")
        page.fill('[data-flow-field="chunk_size"]', "2")
        page.click('[data-run-flow="split-values"]')
        page.wait_for_selector(".allocation-result [data-copy-column]", timeout=30000)

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
        # Kopieringen gör en serverrundresa (GET table-column) före toasten -
        # expects 5s-default är för snål på lastad maskin; följ filens
        # 15s-konvention. Innehållskravet är oförändrat.
        expect(page.locator(".toast.success")).to_have_text("Kolumn kopierad", timeout=15000)
        copied_text = page.evaluate("navigator.clipboard.readText()")
        assert copied_text.replace("\r\n", "\n") == "C\nD"

        page.goto(f"{local_allocation_server}/index.html", wait_until="domcontentloaded")
        page.wait_for_selector("#scheduleTable", timeout=15000)
        page.goto(f"{local_allocation_server}/dela.html", wait_until="domcontentloaded")
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

        page.goto(f"{local_allocation_server}/bearbeta.html", wait_until="domcontentloaded")
        page.wait_for_selector('button[data-run-flow="allocate"]:not([disabled])', timeout=15000)
        page.click('button[data-run-flow="allocate"]')
        page.wait_for_selector(".allocation-result [data-copy-column]", timeout=15000)
        expect(page.locator(".allocation-result")).to_contain_text("O-1")

        page.goto(f"{local_allocation_server}/historik.html", wait_until="domcontentloaded")
        page.wait_for_selector("#auditBody", timeout=15000)
        page.goto(f"{local_allocation_server}/bearbeta.html", wait_until="domcontentloaded")
        page.wait_for_selector(".allocation-result [data-copy-column]", timeout=15000)

        expect(page.locator(".allocation-result h2")).to_have_text("Resultat - Allokering")
        expect(page.locator(".allocation-result")).to_contain_text("O-1")
        expect(page.locator("#allocationRoot")).to_contain_text("Klart: Allokering")
    finally:
        context.close()


def test_bearbeta_matrix_is_managed_from_settings(local_allocation_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    captured = {}
    matrix_payload = {
        "areas": [
            {"code": "ALLT", "label": "Alla"},
            {"code": "AS", "label": "Autostore"},
        ],
        "flows": [
            {"id": "allocate", "label": "Allokering", "category": "Allokering"},
            {"id": "ordersaldo", "label": "Ordersaldo", "category": "Kontroll"},
        ],
        "matrix": {
            "ALLT": {"visibleFlowIds": None},
            "AS": {"visibleFlowIds": ["allocate"]},
        },
    }
    try:
        page.route(
            "**/api/allokering/ytgenerering-map-layout**",
            lambda route: route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"version": 1, "can_edit": True, "locations": [], "defaults": [], "available_locations": []}),
            ),
        )
        page.route(
            "**/api/allokering/ytgenerering-location-options**",
            lambda route: route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"available_locations": []}),
            ),
        )

        def handle_process_matrix(route):
            if route.request.method == "PUT":
                captured["payload"] = json.loads(route.request.post_data or "{}")
                matrix_payload["matrix"] = captured["payload"].get("matrix") or {}
            route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(matrix_payload, ensure_ascii=False),
            )

        page.route("**/api/allokering/process-matrix**", handle_process_matrix)
        login_admin(page, local_allocation_server)

        page.goto(f"{local_allocation_server}/bearbeta.html", wait_until="domcontentloaded")
        page.wait_for_selector(".allocation-board", timeout=15000)
        expect(page.locator("#allocation-process-matrix")).to_have_count(0)

        page.goto(f"{local_allocation_server}/installningar.html", wait_until="domcontentloaded")
        page.wait_for_selector('[data-settings-tab="process-matrix"]', timeout=15000)
        page.click('[data-settings-tab="process-matrix"]')
        page.wait_for_selector(".allocation-process-matrix-table", timeout=15000)
        expect(page.locator(".allocation-process-matrix-table")).to_contain_text("Autostore")
        expect(page.locator("#allocation-process-matrix-settings-save")).to_be_visible()

        page.click("#allocation-process-matrix-settings-save")
        expect(page.locator(".toast.success").last).to_contain_text("Bearbeta-matris sparades", timeout=15000)
        assert captured["payload"]["matrix"]["ALLT"]["visibleFlowIds"] is None
        assert captured["payload"]["matrix"]["AS"]["visibleFlowIds"] == ["allocate"]
    finally:
        context.close()


def test_ytgenerering_settings_editor_is_scoped_to_area_toggle(local_allocation_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    captured = {}
    areas = [
        {"id": 101, "code": "AS", "name": "Autostore", "sort_order": 1, "is_active": True},
        {"id": 102, "code": "MG", "name": "Manuell grupp", "sort_order": 2, "is_active": True},
    ]
    profile = {
        "version": 1,
        "flows": {
            "ytgenerering": {
                "settings": {
                    "ytgenerering": {
                        "areas": {
                            "ALLT": {"utlMin": 1, "utlMax": 652},
                            "AS": {"utlMin": 205, "utlMax": 356},
                            "MG": {"utlMin": 300, "utlMax": 330},
                        }
                    }
                }
            }
        },
    }
    process_matrix = {
        "areas": [
            {"code": "ALLT", "label": "Alla"},
            {"code": "AS", "label": "AS"},
            {"code": "MG", "label": "MG"},
        ],
        "flows": [
            {"id": "ytgenerering", "label": "Ytgenerering", "category": "Forecast & yta"},
        ],
        "matrix": {
            "ALLT": {"visibleFlowIds": ["ytgenerering"]},
            "AS": {"visibleFlowIds": ["ytgenerering"]},
            "MG": {"visibleFlowIds": ["ytgenerering"]},
        },
    }
    try:
        page.route(
            "**/api/areas",
            lambda route: route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(areas, ensure_ascii=False),
            ),
        )
        page.route(
            "**/api/coredata/files",
            lambda route: route.fulfill(status=200, headers={"content-type": "application/json"}, body='{"files":{}}'),
        )
        page.route(
            "**/api/allokering/flows",
            lambda route: route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        "flows": [
                            {
                                "id": "ytgenerering",
                                "label": "Ytgenerering",
                                "category": "Forecast & yta",
                                "view": "combined",
                                "description": "Ytgenerering",
                                "inputs": [],
                                "coredata": [],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        page.route(
            "**/api/allokering/process-matrix**",
            lambda route: route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(process_matrix, ensure_ascii=False),
            ),
        )

        def handle_filter_profile(route):
            nonlocal profile
            if route.request.method == "PUT":
                captured["payload"] = json.loads(route.request.post_data or "{}")
                profile = captured["payload"].get("profile") or {}
            route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"profile": profile, "users": []}, ensure_ascii=False),
            )

        page.route("**/api/allokering/filter-profile", handle_filter_profile)

        login_admin(page, local_allocation_server)
        page.goto(f"{local_allocation_server}/bearbeta.html", wait_until="domcontentloaded")
        page.wait_for_selector(".allocation-board", timeout=15000)
        page.evaluate(
            """(areas) => {
              window.setAreaFocusAreas(areas, { is_super_user: true });
              window.writeAreaFocus("AREA:101");
            }""",
            areas,
        )
        page.wait_for_selector('button[data-flow-filter="ytgenerering"]', timeout=15000)
        page.click('button[data-flow-filter="ytgenerering"]')

        rows = page.locator("[data-ytgenerering-utl-area]")
        expect(rows).to_have_count(1)
        expect(page.locator('[data-ytgenerering-utl-area="AS"]')).to_be_visible()
        expect(page.locator(".allocation-ytgenerering-utl-grid")).not_to_contain_text("MG")
        expect(page.locator(".allocation-ytgenerering-utl-grid")).not_to_contain_text("Alla")

        page.fill('[data-ytgenerering-utl-min="AS"]', "220")
        page.fill('[data-ytgenerering-utl-max="AS"]', "240")
        page.click("#allocation-filter-save")
        expect(page.locator(".toast.success").last).to_contain_text("Filtrering sparades", timeout=15000)

        saved_areas = captured["payload"]["profile"]["flows"]["ytgenerering"]["settings"]["ytgenerering"]["areas"]
        assert saved_areas["AS"] == {"utlMin": 220, "utlMax": 240}
        assert saved_areas["MG"] == {"utlMin": 300, "utlMax": 330}
    finally:
        context.close()


def test_staffing_settings_selects_vh_capacity_activities(local_allocation_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    captured = {}
    try:
        page.route(
            "**/api/allokering/ytgenerering-map-layout**",
            lambda route: route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"version": 1, "can_edit": True, "locations": [], "defaults": [], "available_locations": []}),
            ),
        )
        page.route(
            "**/api/allokering/ytgenerering-location-options**",
            lambda route: route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"available_locations": []}),
            ),
        )
        page.route(
            "**/api/allokering/process-matrix**",
            lambda route: route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"areas": [], "flows": [], "matrix": {}}),
            ),
        )

        activities = [
            {"id": 101, "label": "GG Plock", "category": "work", "kpi_process_name": "Manual_Pick", "sort_order": 1, "is_active": True},
            {"id": 102, "label": "Pack", "category": "work", "kpi_process_name": "Pack", "sort_order": 2, "is_active": True},
            {"id": 103, "label": "Frånvaro", "category": "absence", "kpi_process_name": "Absence", "sort_order": 3, "is_active": True},
            {"id": 104, "label": "Stöd", "category": "work", "kpi_process_name": "", "sort_order": 4, "is_active": True},
        ]
        page.route(
            "**/api/activities**",
            lambda route: route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(activities, ensure_ascii=False),
            ),
        )

        def handle_staffing_settings(route):
            if route.request.method == "PUT":
                captured["payload"] = json.loads(route.request.post_data or "{}")
                body = {
                    "history_hours": captured["payload"]["history_hours"],
                    "min_history_hours": 1,
                    "max_history_hours": 240,
                    "activity_capacity_activity_ids": captured["payload"].get("activity_capacity_activity_ids"),
                }
            else:
                body = {
                    "history_hours": 40,
                    "min_history_hours": 1,
                    "max_history_hours": 240,
                    "activity_capacity_activity_ids": None,
                }
            route.fulfill(status=200, headers={"content-type": "application/json"}, body=json.dumps(body))

        page.route("**/api/settings/staffing**", handle_staffing_settings)
        login_admin(page, local_allocation_server)

        page.goto(f"{local_allocation_server}/installningar.html", wait_until="domcontentloaded")
        page.wait_for_selector('[data-settings-tab="staffing"]', timeout=15000)
        page.click('[data-settings-tab="staffing"]')
        page.wait_for_selector("[data-staffing-capacity-all]", timeout=15000)
        panel = page.locator(".allocation-staffing-settings-panel")
        expect(page.locator("[data-staffing-capacity-activity]")).to_have_count(2)
        expect(panel.locator("text=Frånvaro")).to_have_count(0)
        expect(panel.locator("text=Stöd")).to_have_count(0)

        page.uncheck("[data-staffing-capacity-all]")
        page.uncheck('[data-staffing-capacity-activity][value="102"]')
        page.click(".allocation-staffing-settings-panel button.primary")

        expect(page.locator(".toast.success").last).to_contain_text("Bemanningsinställningen sparades", timeout=15000)
        assert captured["payload"] == {"history_hours": 40, "activity_capacity_activity_ids": [101]}
    finally:
        context.close()


def test_ytgenerering_runs_forecast_and_surface_generation_in_one_click(local_allocation_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE", accept_downloads=True)
    page = context.new_page()
    captured = {}
    try:
        login_admin(page, local_allocation_server)
        seed_allocation_file_pool(page)
        mock_forecast_coredata(page)

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
                        "summary": {"Sändningar": 1, "Predikterade pallplatser": 2.5, "Använda lagerplatser": 1},
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
                            },
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
                        "maps": [
                            {
                                "label": "Ytkarta",
                                "locations": [
                                    {"location": "UTL100", "x": 0, "y": 0, "w": 120, "h": 80, "maxPall": 2},
                                    {"location": "UTL101", "x": 140, "y": 0, "w": 120, "h": 80, "maxPall": 3},
                                    {"location": "UTL102", "x": 280, "y": 0, "w": 60, "h": 180, "maxPall": 2},
                                ],
                                "assignments": [
                                    {
                                        "id": "S-1-UTL100",
                                        "shipment": "S-1",
                                        "carrier": "Akeri A",
                                        "cluster": "Freja Test",
                                        "customer": "Kund A",
                                        "location": "UTL100",
                                        "placedPallets": 2,
                                        "shipmentPallets": 2,
                                        "maxPall": 2,
                                        "unusedCapacity": 0,
                                        "placementNo": 1,
                                        "orderNumbers": ["O-1"],
                                        "orderCompanies": {"O-1": "T3"},
                                    }
                                ],
                                "unplaced": [],
                            }
                        ],
                        "auto_downloads": [
                            {
                                "key": "order_set_area_import",
                                "filename": "v_ask_order_overview_order_set_area_execute_command.csv",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
            )

        page.route("**/api/allokering/flow/ytgenerering", handle_ytgenerering)
        page.route(
            "**/api/allokering/download/ytgenerering-session-1/order_set_area_import",
            lambda route: route.fulfill(
                status=200,
                headers={
                    "content-type": "text/csv",
                    "content-disposition": 'attachment; filename="v_ask_order_overview_order_set_area_execute_command.csv"',
                },
                body="area_num\tcompany\torder_num\tpick_zone\nUTL100\tT3\tO-1\tA\n",
            ),
        )

        page.goto(f"{local_allocation_server}/bearbeta.html", wait_until="domcontentloaded")
        ytgenerering_button = page.locator('button[data-run-flow="ytgenerering"]')
        expect(page.locator('button[data-run-flow="forecast"]')).to_have_count(0)
        expect(ytgenerering_button).to_be_enabled(timeout=15000)
        expect(page.locator('button[data-follow-up-flow="ytgenerering"]')).to_have_count(0)

        with page.expect_response("**/api/allokering/download/ytgenerering-session-1/order_set_area_import") as download_response:
            ytgenerering_button.click()
        page.wait_for_selector(".allocation-result [data-copy-column]", timeout=15000)
        expect(page.locator(".allocation-result h2")).to_have_text("Resultat - Ytgenerering")
        expect(page.locator(".allocation-result")).to_contain_text("Forecast")
        expect(page.locator(".allocation-result")).to_contain_text("S-1")
        expect(page.locator(".allocation-result")).to_contain_text("UTL100")
        expect(page.locator("[data-map-metrics]")).to_contain_text("Lediga pallplatser")
        expect(page.locator("[data-map-metrics]")).to_contain_text("5")
        expect(page.locator("[data-map-metrics]")).to_contain_text("Lediga ytor")
        expect(page.locator("[data-map-metrics]")).to_contain_text("2")
        map_text_contract = page.evaluate(
            """() => {
              const assigned = document.querySelector('[data-map-location-group="UTL100"] .allocation-map-label-main');
              const unused = document.querySelector('[data-map-location-group="UTL101"] .allocation-map-label');
              const verticalUnused = document.querySelector('[data-map-location-group="UTL102"] .allocation-map-label');
              if (!assigned || !unused || !verticalUnused) throw new Error("Missing ytgenerering map labels");
              return {
                assignedFont: Number.parseFloat(getComputedStyle(assigned).fontSize),
                unusedFont: Number.parseFloat(getComputedStyle(unused).fontSize),
                unusedText: unused.textContent.trim(),
                verticalUnusedFont: Number.parseFloat(getComputedStyle(verticalUnused).fontSize),
                verticalUnusedTransform: verticalUnused.getAttribute("transform") || "",
              };
            }"""
        )
        assert map_text_contract["unusedText"] == "101"
        assert map_text_contract["unusedFont"] == pytest.approx(map_text_contract["assignedFont"])
        assert map_text_contract["verticalUnusedFont"] == pytest.approx(map_text_contract["assignedFont"])
        assert "rotate(-90" in map_text_contract["verticalUnusedTransform"]
        page.wait_for_function(
            """() => document.querySelector("[data-map-canvas]")?.getAttribute("transform")?.includes("scale")"""
        )
        initial_scale = page.locator("[data-map-canvas]").evaluate(
            """(node) => Number((node.getAttribute("transform") || "").match(/scale\\(([^)]+)\\)/)?.[1] || 0)"""
        )
        page.evaluate(
            """() => {
              const svg = document.querySelector("[data-map-svg]");
              const rect = svg.getBoundingClientRect();
              svg.dispatchEvent(new WheelEvent("wheel", {
                deltaY: 1200,
                clientX: rect.left + rect.width / 2,
                clientY: rect.top + rect.height / 2,
                bubbles: true,
                cancelable: true,
              }));
            }"""
        )
        zoomed_out_scale = page.locator("[data-map-canvas]").evaluate(
            """(node) => Number((node.getAttribute("transform") || "").match(/scale\\(([^)]+)\\)/)?.[1] || 0)"""
        )
        assert zoomed_out_scale == pytest.approx(initial_scale)
        page.evaluate(
            """() => {
              const svg = document.querySelector("[data-map-svg]");
              const rect = svg.getBoundingClientRect();
              svg.dispatchEvent(new WheelEvent("wheel", {
                deltaY: -1200,
                clientX: rect.left + rect.width / 2,
                clientY: rect.top + rect.height / 2,
                bubbles: true,
                cancelable: true,
              }));
            }"""
        )
        zoomed_in_scale = page.locator("[data-map-canvas]").evaluate(
            """(node) => Number((node.getAttribute("transform") || "").match(/scale\\(([^)]+)\\)/)?.[1] || 0)"""
        )
        assert zoomed_in_scale > initial_scale
        with page.expect_download() as adjusted_ask_download:
            page.locator("[data-map-export-ask]").click()
        adjusted_ask = adjusted_ask_download.value
        assert adjusted_ask.suggested_filename == "v_ask_order_overview_order_set_area_execute_command_justerad.csv"
        adjusted_ask_content = adjusted_ask.path().read_text(encoding="utf-8")
        assert adjusted_ask_content == "area_num\tcompany\torder_num\tpick_zone\nUTL100\tT3\tO-1\tA\n"
        assert download_response.value.status == 200
        assert 'name="forecast_session_id"' not in captured["post_data"]
        assert 'name="carrier_clusters_json"' not in captured["post_data"]
    finally:
        context.close()


def test_ytgenerering_map_settings_adds_series_and_saves(local_allocation_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    captured = {}
    base_layout = {
        "version": 1,
        "can_edit": True,
        "locations": [
            {"location": "UTL205", "x": 100, "y": 100, "w": 240, "h": 80, "maxPall": 2},
        ],
        "defaults": [
            {"location": "UTL205", "x": 100, "y": 100, "w": 240, "h": 80, "maxPall": 2},
        ],
        "available_locations": [
            {"location": "UTL205", "maxPall": 2},
            {"location": "UTL206", "maxPall": 3},
            {"location": "UTL207", "maxPall": 3},
            {"location": "UTL208", "maxPall": 7},
            {"location": "UTL209", "maxPall": 3},
        ],
    }
    try:
        login_admin(page, local_allocation_server)

        def handle_map_layout(route):
            if route.request.method == "PUT":
                captured["payload"] = json.loads(route.request.post_data or "{}")
                response_locations = captured["payload"].get("locations") or []
            else:
                response_locations = base_layout["locations"]
            route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        **base_layout,
                        "locations": response_locations,
                    },
                    ensure_ascii=False,
                ),
            )

        page.route("**/api/allokering/ytgenerering-map-layout**", handle_map_layout)
        page.route(
            "**/api/allokering/ytgenerering-location-options**",
            lambda route: route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"available_locations": base_layout["available_locations"]}, ensure_ascii=False),
            ),
        )
        page.goto(f"{local_allocation_server}/installningar.html", wait_until="domcontentloaded")
        page.wait_for_selector(".allocation-map-settings-page-panel", timeout=15000)

        expect(page.locator(".allocation-map-settings-list")).to_contain_text("UTL206")
        expect(page.locator(".allocation-map-settings-list")).not_to_contain_text("UTL205")
        expect(page.locator('[data-map-setting-node="UTL205"] .allocation-map-setting-label')).to_have_text("205")
        page.locator('[data-map-setting-rect="UTL205"]').click()
        page.locator('[data-map-setting-rect="UTL205"]').click(button="right")
        target_box = page.locator('[data-map-setting-rect="UTL205"]').bounding_box()
        menu_box = page.locator(".allocation-map-settings-context-menu").bounding_box()
        assert target_box and menu_box
        target_center_x = target_box["x"] + target_box["width"] / 2
        target_center_y = target_box["y"] + target_box["height"] / 2
        assert abs(menu_box["x"] - target_center_x) < 24
        assert abs(menu_box["y"] - target_center_y) < 24
        page.get_by_role("button", name="Byt riktning").click()
        expect(page.locator(".allocation-map-settings-page-panel")).to_contain_text("riktning vänster")
        initial_viewbox = page.locator("[data-map-settings-svg]").evaluate(
            """(node) => {
                const box = node.viewBox.baseVal;
                return { x: box.x, y: box.y, width: box.width, height: box.height };
            }"""
        )
        page.click("[data-map-zoom-out]")
        zoomed_out_viewbox = page.locator("[data-map-settings-svg]").evaluate(
            """(node) => {
                const box = node.viewBox.baseVal;
                return { x: box.x, y: box.y, width: box.width, height: box.height };
            }"""
        )
        assert zoomed_out_viewbox == pytest.approx(initial_viewbox)
        page.click("[data-map-zoom-in]")
        zoomed_in_viewbox = page.locator("[data-map-settings-svg]").evaluate(
            """(node) => {
                const box = node.viewBox.baseVal;
                return { x: box.x, y: box.y, width: box.width, height: box.height };
            }"""
        )
        assert zoomed_in_viewbox["width"] < initial_viewbox["width"]
        assert zoomed_in_viewbox["height"] < initial_viewbox["height"]
        page.evaluate(
            """() => {
                const svg = document.querySelector("[data-map-settings-svg]");
                const rect = svg.getBoundingClientRect();
                for (let index = 0; index < 20; index += 1) {
                    svg.dispatchEvent(new WheelEvent("wheel", {
                        deltaY: 1200,
                        clientX: rect.left + rect.width / 2,
                        clientY: rect.top + rect.height / 2,
                        bubbles: true,
                        cancelable: true,
                    }));
                }
            }"""
        )
        wheel_zoomed_out_viewbox = page.locator("[data-map-settings-svg]").evaluate(
            """(node) => {
                const box = node.viewBox.baseVal;
                return { x: box.x, y: box.y, width: box.width, height: box.height };
            }"""
        )
        assert wheel_zoomed_out_viewbox == pytest.approx(initial_viewbox)
        page.fill("[data-map-series-start]", "206")
        page.fill("[data-map-series-end]", "207")
        page.fill("[data-map-series-max]", "3")
        page.click("[data-map-add-series]")
        expect(page.locator(".allocation-map-settings-canvas")).to_contain_text("207")
        expect(page.locator(".allocation-map-settings-canvas")).not_to_contain_text("UTL207")
        page.click("[data-map-fit]")
        expect(page.locator("[data-map-selection-count]")).to_have_text("2 valda")
        page.locator('[data-map-setting-rect="UTL206"]').click()
        snap_result = page.evaluate(
            """
            () => {
                const svg = document.querySelector("[data-map-settings-svg]");
                const source = document.querySelector('[data-map-setting-rect="UTL206"]');
                const target = document.querySelector('[data-map-setting-rect="UTL207"]');
                if (!svg || !source || !target) throw new Error("Missing map snap test elements");
                const viewBox = svg.viewBox.baseVal;
                const svgBox = svg.getBoundingClientRect();
                const sourceBox = source.getBoundingClientRect();
                const startX = sourceBox.left + sourceBox.width / 2;
                const startY = sourceBox.top + sourceBox.height / 2;
                const sourceY = Number(source.getAttribute("y"));
                const targetY = Number(target.getAttribute("y"));
                const deltaY = ((targetY - sourceY) / Math.max(1, viewBox.height)) * svgBox.height + 2;
                const pointerId = 41;
                svg.dispatchEvent(new PointerEvent("pointerdown", {
                    bubbles: true,
                    cancelable: true,
                    pointerId,
                    button: 0,
                    buttons: 1,
                    clientX: startX,
                    clientY: startY,
                }));
                svg.dispatchEvent(new PointerEvent("pointermove", {
                    bubbles: true,
                    cancelable: true,
                    pointerId,
                    button: 0,
                    buttons: 1,
                    clientX: startX,
                    clientY: startY + deltaY,
                }));
                const lineCount = document.querySelectorAll("[data-map-snap-guides] .allocation-map-settings-guide-line").length;
                const movedY = source.getAttribute("y");
                svg.dispatchEvent(new PointerEvent("pointerup", {
                    bubbles: true,
                    cancelable: true,
                    pointerId,
                    button: 0,
                    buttons: 0,
                    clientX: startX,
                    clientY: startY + deltaY,
                }));
                return {
                    lineCount,
                    movedY,
                    sourceY,
                    targetY,
                    deltaY,
                };
            }
            """
        )
        assert snap_result["lineCount"] > 0, snap_result
        page.locator('[data-map-setting-rect="UTL206"]').click()
        if page.locator("[data-map-selection-count]").text_content().strip() != "2 valda":
            page.locator('[data-map-setting-rect="UTL207"]').click(modifiers=["Control"])
        expect(page.locator("[data-map-selection-count]")).to_have_text("2 valda")
        page.locator('[data-map-setting-rect="UTL206"]').click(button="right")
        page.get_by_role("button", name="Byt riktning").click()
        expect(page.locator(".allocation-map-settings-page-panel")).to_contain_text("2 ytor: riktning bytt")
        page.locator('[data-map-setting-rect="UTL206"]').dblclick()
        expect(page.locator(".allocation-map-settings-page-panel")).to_contain_text("UTL206: roterad")
        expect(page.locator('[data-map-setting-rect="UTL206"]')).to_have_attribute("width", "80")
        expect(page.locator('[data-map-setting-rect="UTL206"]')).to_have_attribute("height", "360")
        page.locator('[data-map-setting-rect="UTL206"]').click()
        expect(page.locator("[data-map-setting-location]")).to_have_value("UTL206")
        page.locator('[data-map-setting-rect="UTL207"]').click(modifiers=["Control"])
        expect(page.locator("[data-map-setting-location]")).to_have_value("UTL207")
        expect(page.locator("[data-map-selection-count]")).to_have_text("2 valda")
        original_y = float(page.locator('[data-map-setting-rect="UTL206"]').get_attribute("y"))
        page.click("[data-map-zoom-in]")
        page.keyboard.press("ArrowDown")
        moved_y = float(page.locator('[data-map-setting-rect="UTL206"]').get_attribute("y"))
        assert moved_y > original_y
        page.keyboard.press("Alt+ArrowUp")
        fine_y = float(page.locator('[data-map-setting-rect="UTL206"]').get_attribute("y"))
        assert fine_y == moved_y - 1
        page.keyboard.press("Control+Z")
        expect(page.locator('[data-map-setting-rect="UTL206"]')).to_have_attribute("y", str(int(moved_y)))
        page.keyboard.press("Control+Z")
        expect(page.locator('[data-map-setting-rect="UTL206"]')).to_have_attribute("y", str(int(original_y)))
        page.keyboard.press("Control+C")
        page.keyboard.press("Control+V")
        expect(page.locator(".allocation-map-settings-canvas")).to_contain_text("209")
        page.keyboard.press("Control+Z")
        expect(page.locator(".allocation-map-settings-canvas")).not_to_contain_text("209")
        page.locator('[data-map-setting-rect="UTL206"]').click()
        page.locator('[data-map-setting-rect="UTL207"]').click(modifiers=["Control"])
        page.keyboard.press("Delete")
        expect(page.locator(".allocation-map-settings-canvas")).not_to_contain_text("207")
        page.keyboard.press("Control+Z")
        expect(page.locator(".allocation-map-settings-canvas")).to_contain_text("207")
        page.evaluate(
            """
            ({ sourceSelector, targetSelector }) => {
                const source = document.querySelector(sourceSelector);
                const target = document.querySelector(targetSelector);
                if (!source || !target) throw new Error("Missing drag source or target");
                const box = target.getBoundingClientRect();
                const clientX = box.left + box.width * 0.58;
                const clientY = box.top + box.height * 0.46;
                const dataTransfer = new DataTransfer();
                source.dispatchEvent(new DragEvent("dragstart", {
                    bubbles: true,
                    cancelable: true,
                    dataTransfer,
                    clientX,
                    clientY,
                }));
                target.dispatchEvent(new DragEvent("dragover", {
                    bubbles: true,
                    cancelable: true,
                    dataTransfer,
                    clientX,
                    clientY,
                }));
                target.dispatchEvent(new DragEvent("drop", {
                    bubbles: true,
                    cancelable: true,
                    dataTransfer,
                    clientX,
                    clientY,
                }));
                source.dispatchEvent(new DragEvent("dragend", {
                    bubbles: true,
                    cancelable: true,
                    dataTransfer,
                    clientX,
                    clientY,
                }));
            }
            """,
            {
                "sourceSelector": '[data-map-add-location="UTL208"]',
                "targetSelector": ".allocation-map-settings-canvas",
            },
        )
        expect(page.locator(".allocation-map-settings-canvas")).to_contain_text("208")
        expect(page.locator(".allocation-map-settings-list")).not_to_contain_text("UTL208")
        page.click("[data-map-save]")

        expect(page.locator(".allocation-map-settings-page-panel")).to_contain_text("sparade", timeout=15000)
        locations = captured["payload"]["locations"]
        assert [row["location"] for row in locations] == ["UTL205", "UTL206", "UTL207", "UTL208"]
        assert locations[0]["loadDirection"] == "left"
        assert locations[1]["maxPall"] == 3
        assert locations[1]["w"] == 80
        assert locations[1]["h"] == 360
        assert locations[1]["loadDirection"] == "up"
        assert locations[2]["x"] > locations[1]["x"]
        assert locations[2]["w"] == 360
        assert locations[2]["loadDirection"] == "right"
        assert locations[3]["maxPall"] == 7
        assert locations[3]["w"] == 840
        assert locations[3]["h"] == 80
    finally:
        context.close()

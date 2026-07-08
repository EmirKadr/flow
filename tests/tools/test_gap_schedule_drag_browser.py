"""Browsertester för bemanningsdrag (drag-fyll) i schemat.

Kontrakten som skyddas (schedule/editing.js: setupDrag/finishDrag på
#scheduleBody, index.html):

1. Schemagriden renderas: #scheduleBody har person-rader och timceller med
   data-hour/data-row-index/data-col-index, och cellerna är interagerbara.
2. Ett bemanningsdrag från en full-timcell med en effektiv aktivitet markerar
   grannceller med .drag-target och skickar POST /api/schedule/cells där varje
   målcell får källans activity_id — följt av en "Fyllde …"-toast.
3. En delad cell (td[data-split="1"]) startar inte ett full-tim-drag.

Den lokala seeden kan sakna en draggbar källa. Då nöjer vi oss med de
strukturella kontrollerna (kontrakt 1) och skippar dataflödet (kontrakt 2/3)
i stället för att lämna ett rött/flaky test.
"""
import json

import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="module")
def local_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("schedule-drag-browser")
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
    page.goto(f"{base_url}/login.html", wait_until="load")
    page.fill("#username", "admin")
    page.fill("#password", "admin123")
    page.click("button.primary")
    page.wait_for_url("**/index.html", timeout=15000)
    page.wait_for_selector("#scheduleTable", timeout=15000)


def load_schedule_all_areas(page) -> None:
    """Sätt områdesfokus till ALLT och vänta in schemaraderna (samma väg som
    visual_smoke använder för schema-states)."""
    page.evaluate(
        """() => {
            localStorage.setItem('flow-area-focus', 'ALLT');
            localStorage.removeItem('sidebar-collapsed');
        }"""
    )
    page.reload(wait_until="load")
    page.wait_for_selector("#scheduleTable", timeout=15000)
    page.wait_for_selector("#scheduleBody tr[data-person-id]", timeout=15000)
    page.wait_for_timeout(400)


def find_drag_candidate(page):
    """Hitta en full-timcell med en effektiv aktivitet och minst två
    icke-delade grannceller i samma rad. Returnerar None om seeden saknar
    en draggbar källa."""
    return page.evaluate(
        """() => {
            const cellSelector = (row, col) =>
                `#scheduleBody td[data-row-index="${row}"][data-col-index="${col}"]`;
            const cells = Array.from(
                document.querySelectorAll('#scheduleBody td[data-hour][data-col-index]')
            );
            for (const td of cells) {
                if (td.dataset.split === '1') continue;
                if (td.classList.contains('locked-cell')) continue;
                const personId = Number(td.dataset.personId);
                const hour = Number(td.dataset.hour);
                // Effektiv aktivitet (explicit eller schemalagd default).
                const activityId = typeof effectiveActivityIdForRange === 'function'
                    ? effectiveActivityIdForRange(personId, hour, 0, 60)
                    : null;
                if (activityId == null) continue;
                const row = Number(td.dataset.rowIndex);
                const col = Number(td.dataset.colIndex);
                const neighbors = [];
                for (let c = col + 1; c <= col + 3; c++) {
                    const n = document.querySelector(cellSelector(row, c));
                    if (!n || n.dataset.split === '1') break;
                    if (n.classList.contains('locked-cell')) break;
                    neighbors.push({
                        personId: Number(n.dataset.personId),
                        hour: Number(n.dataset.hour),
                        row,
                        col: c,
                    });
                }
                if (neighbors.length >= 2) {
                    return {
                        source: { personId, hour, row, col, activityId: Number(activityId) },
                        neighbors,
                    };
                }
            }
            return null;
        }"""
    )


def cell_locator(page, row: int, col: int):
    return page.locator(f'#scheduleBody td[data-row-index="{row}"][data-col-index="{col}"]')


def center(box):
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def test_schedule_grid_renders_and_cells_are_interactive(local_server, chromium_browser):
    """Kontrakt 1: griden renderas med rader/celler och en cell tar fokus vid
    klick. Rör inga data (klickar bara, sparar inget)."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login_admin(page, local_server)
        load_schedule_all_areas(page)

        rows = page.locator("#scheduleBody tr[data-person-id]")
        assert rows.count() > 0, "väntade minst en person-rad i schemat"

        # Timceller bär de attribut som setupDrag/finishDrag läser.
        cells = page.locator("#scheduleBody td[data-hour][data-col-index]")
        assert cells.count() > 0, "väntade minst en timcell med data-hour/col-index"
        first = cells.first
        assert first.get_attribute("data-row-index") is not None
        assert first.get_attribute("data-person-id")
        assert first.get_attribute("data-hour") is not None

        # Klick på en cell fokuserar den (setupDrag body-click -> focusSegment)
        # och ska inte kasta. Cellen ska markeras som fokuserad.
        first.click()
        page.wait_for_selector("#scheduleBody td.focused, #scheduleBody .hour-segment.focused", timeout=5000)
    finally:
        context.close()


def test_staffing_drag_fills_neighbor_cells(local_server, chromium_browser):
    """Kontrakt 2: drag-fyll markerar grannceller och postar dem med källans
    activity_id. POST:en spioneras och mockas (deterministisk success-toast,
    ingen skarp skrivning mot seeden)."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login_admin(page, local_server)
        load_schedule_all_areas(page)

        candidate = find_drag_candidate(page)
        if not candidate:
            pytest.skip("Seeden saknar en draggbar full-timcell med aktivitet")

        source = candidate["source"]
        neighbors = candidate["neighbors"][:3]

        captured = {}

        def handle_cells(route):
            request = route.request
            if request.method != "POST":
                route.continue_()
                return
            try:
                payload = request.post_data_json
            except Exception:
                payload = json.loads(request.post_data or "{}")
            captured["payload"] = payload
            cells = payload.get("cells", [])
            applied = [
                {
                    "person_id": c["person_id"],
                    "hour": c["hour"],
                    "minute_start": c.get("minute_start", 0),
                    "minute_end": c.get("minute_end", 60),
                    "activity_id": c.get("activity_id"),
                    "version": (c.get("expected_version") or 0) + 1,
                }
                for c in cells
            ]
            route.fulfill(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"applied": applied}, ensure_ascii=False),
            )

        page.route("**/api/schedule/cells", handle_cells)

        src_box = cell_locator(page, source["row"], source["col"]).bounding_box()
        assert src_box, "källcellen saknar bounding box"
        sx, sy = center(src_box)

        page.mouse.move(sx, sy)
        page.mouse.down()
        # Rör musen förbi 5px-tröskeln så draget aktiveras (activateDrag).
        page.mouse.move(sx + 12, sy, steps=4)
        page.wait_for_function("() => document.body.classList.contains('dragging')", timeout=5000)

        last = neighbors[-1]
        for n in neighbors:
            box = cell_locator(page, n["row"], n["col"]).bounding_box()
            assert box, f"granncell r{n['row']} c{n['col']} saknar bounding box"
            cx, cy = center(box)
            page.mouse.move(cx, cy, steps=4)

        # Sista grannen ska nu vara markerad som drag-target.
        page.wait_for_function(
            """(sel) => {
                const td = document.querySelector(sel);
                return td && td.classList.contains('drag-target');
            }""",
            arg=f'#scheduleBody td[data-row-index="{last["row"]}"][data-col-index="{last["col"]}"]',
            timeout=5000,
        )

        page.mouse.up()

        expect(page.locator(".toast").filter(has_text="Fyllde").last).to_contain_text(
            "Fyllde", timeout=15000
        )

        payload = captured.get("payload")
        assert payload is not None, "ingen POST /api/schedule/cells fångades"
        assert payload.get("action") == "drag_fill"
        posted = {(c["person_id"], c["hour"]): c["activity_id"] for c in payload.get("cells", [])}
        for n in neighbors:
            key = (n["personId"], n["hour"])
            assert key in posted, f"granncell {key} saknas i POST-payloaden"
            assert posted[key] == source["activityId"], (
                f"granncell {key} fick activity_id {posted[key]}, "
                f"väntade källans {source['activityId']}"
            )
        # Källcellen ska aldrig skrivas över sig själv.
        assert (source["personId"], source["hour"]) not in posted
    finally:
        page.unroute("**/api/schedule/cells")
        context.close()


def test_split_cell_does_not_start_full_hour_drag(local_server, chromium_browser):
    """Kontrakt 3: mousedown på själva td[data-split="1"] (utanför ett
    .hour-segment) startar inte ett drag. Saknas delade celler i seeden
    skippas kontraktet."""
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        login_admin(page, local_server)
        load_schedule_all_areas(page)

        split = page.locator('#scheduleBody td[data-split="1"]')
        if split.count() == 0:
            pytest.skip("Seeden saknar delade celler (td[data-split='1'])")

        td = split.first
        box = td.bounding_box()
        assert box
        # Nära nedre kanten för att undvika ett segments mittpunkt; drag-start
        # för hela timmen ska ändå inte triggas för en delad cell.
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] - 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 30, y, steps=5)
        page.wait_for_timeout(200)
        started_full_hour = page.evaluate(
            """() => {
                // Ett full-tim-drag skulle sätta body.dragging OCH markera hela
                // grannceller som drag-target. En delad cell får aldrig starta
                // ett full-tim-drag via td-mousedown.
                return document.body.classList.contains('dragging')
                    && Boolean(window.drag) && window.drag.sourceMinuteEnd === 60
                    && window.drag.sourceMinuteStart === 0;
            }"""
        ) if page.evaluate("() => 'drag' in window") else False
        page.mouse.up()
        assert not started_full_hour, "delad cell startade ett full-tim-drag"
    finally:
        context.close()

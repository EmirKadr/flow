"""Frontend-hjälpare (W15) i den buildlösa JS-harnessen.

Tre rena/DOM-nära hjälpare som annars bara nås via drag-, modal- och
formulärinteraktion. Varje källfil injiceras som globalt skript (samma
mönster som test_js_unit_harness.py) och funktionerna anropas direkt.

Täckta kontrakt:
- person_order.js   movedPersonOrderIds(src, target, position, ids)
- data_fetch.js     dataFetchMaxRows / dataFetchValueText / dataFetchErrorDetail
- common/import_tools.js  handleModalEnterKeydown / collectBulkImportRows
"""
from __future__ import annotations

from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
sync_playwright = playwright_api.sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PERSON_ORDER_JS = ROOT / "app" / "frontend" / "js" / "schedule" / "person_order.js"
DATA_FETCH_JS = ROOT / "app" / "frontend" / "js" / "data_fetch.js"
IMPORT_TOOLS_JS = ROOT / "app" / "frontend" / "js" / "common" / "import_tools.js"


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


def _script_page(browser, js_path: Path):
    page = browser.new_page()
    page.goto("about:blank")
    page.add_script_tag(content=js_path.read_text(encoding="utf-8"))
    return page


# ---------------------------------------------------------------------------
# person_order.js: movedPersonOrderIds — flytt före/efter, no-op och ordning.
# Fel här flyttar fel person i sorteringen som PUT:as till servern.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def person_order_page(chromium_browser):
    page = _script_page(chromium_browser, PERSON_ORDER_JS)
    yield page
    page.close()


def _moved(page, source, target, position, ids):
    return page.evaluate(
        "([s, t, p, ids]) => movedPersonOrderIds(s, t, p, ids)",
        [source, target, position, ids],
    )


def test_moved_person_order_before_and_after(person_order_page):
    ids = [1, 2, 3, 4]
    assert _moved(person_order_page, 1, 3, "before", ids) == [2, 1, 3, 4]
    assert _moved(person_order_page, 1, 3, "after", ids) == [2, 3, 1, 4]
    # flytta bakåt-till-fronten: 4 före 1
    assert _moved(person_order_page, 4, 1, "before", ids) == [4, 1, 2, 3]
    assert _moved(person_order_page, 4, 1, "after", ids) == [1, 4, 2, 3]


def test_moved_person_order_noops(person_order_page):
    ids = [1, 2, 3]
    # src == target -> oförändrat
    assert _moved(person_order_page, 2, 2, "after", ids) == [1, 2, 3]
    # target saknas i listan -> oförändrat
    assert _moved(person_order_page, 1, 99, "after", ids) == [1, 2, 3]
    assert _moved(person_order_page, 1, 99, "before", ids) == [1, 2, 3]


def test_moved_person_order_preserves_relative_order(person_order_page):
    # Övriga id:n behåller inbördes ordning oavsett flytt.
    ids = [10, 20, 30, 40, 50]
    assert _moved(person_order_page, 30, 50, "after", ids) == [10, 20, 40, 50, 30]
    assert _moved(person_order_page, 30, 10, "before", ids) == [30, 10, 20, 40, 50]
    # källan tas bort exakt en gång även om det finns dubblettliknande grannvärden
    assert _moved(person_order_page, 20, 40, "before", ids) == [10, 30, 20, 40, 50]


# ---------------------------------------------------------------------------
# data_fetch.js: klampning av maxrader, cellformattering och feldetaljer.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def data_fetch_page(chromium_browser):
    page = _script_page(chromium_browser, DATA_FETCH_JS)
    yield page
    page.close()


def _max_rows(page, raw):
    return page.evaluate(
        """(raw) => {
            let el = document.getElementById("dataFetchMaxRows");
            if (!el) {
                el = document.createElement("input");
                el.id = "dataFetchMaxRows";
                document.body.appendChild(el);
            }
            el.value = raw;
            return dataFetchMaxRows();
        }""",
        raw,
    )


def test_data_fetch_max_rows_clamps(data_fetch_page):
    assert _max_rows(data_fetch_page, "0") == 1          # under min -> 1
    assert _max_rows(data_fetch_page, "-50") == 1        # negativt -> 1
    assert _max_rows(data_fetch_page, "99999") == 5000   # över max -> 5000
    assert _max_rows(data_fetch_page, "2500") == 2500    # inom spann -> oförändrat
    assert _max_rows(data_fetch_page, "5.9") == 5        # floor


def test_data_fetch_max_rows_null_on_empty_or_garbage(data_fetch_page):
    assert _max_rows(data_fetch_page, "") is None
    assert _max_rows(data_fetch_page, "   ") is None     # trimmas till tomt
    assert _max_rows(data_fetch_page, "abc") is None     # ej numeriskt


def test_data_fetch_value_text(data_fetch_page):
    result = data_fetch_page.evaluate(
        """() => ({
            array: dataFetchValueText([1, 2, 3]),
            nested: dataFetchValueText([1, [2, 3]]),
            arrayOfObj: dataFetchValueText([{ a: 1 }, "x"]),
            object: dataFetchValueText({ a: 1, b: "två" }),
            nullish: dataFetchValueText(null),
            undef: dataFetchValueText(undefined),
            number: dataFetchValueText(5),
            text: dataFetchValueText("hej"),
        })"""
    )
    assert result["array"] == "1, 2, 3"
    assert result["nested"] == "1, 2, 3"
    assert result["arrayOfObj"] == '{"a":1}, x'
    assert result["object"] == '{"a":1,"b":"två"}'
    assert result["nullish"] == ""
    assert result["undef"] == ""
    assert result["number"] == "5"
    assert result["text"] == "hej"


def test_data_fetch_error_detail_picks_body_detail(data_fetch_page):
    result = data_fetch_page.evaluate(
        """() => dataFetchErrorDetail(
            { body: { detail: { message: "Trasig vy", error_id: "E1", view: "v_x", view_label: "Vy X" } }, status: 500 },
            "fallback"
        )"""
    )
    assert result == {
        "message": "Trasig vy",
        "errorId": "E1",
        "view": "v_x",
        "viewLabel": "Vy X",
        "status": 500,
    }


def test_data_fetch_error_detail_fallbacks(data_fetch_page):
    result = data_fetch_page.evaluate(
        """() => ({
            detailNoMessage: dataFetchErrorDetail(
                { body: { detail: { error_id: "E2" } }, message: "yttre", status: 400 }, "fb"
            ),
            noDetail: dataFetchErrorDetail({ message: "bara-message" }, "fb"),
            bare: dataFetchErrorDetail({}, "fb"),
            nullError: dataFetchErrorDetail(null, "fb"),
        })"""
    )
    # detail utan message -> faller tillbaka på error.message
    assert result["detailNoMessage"]["message"] == "yttre"
    assert result["detailNoMessage"]["errorId"] == "E2"
    assert result["detailNoMessage"]["status"] == 400
    # inget detail-objekt -> error.message
    assert result["noDetail"]["message"] == "bara-message"
    assert result["noDetail"]["errorId"] == ""
    # tomt error -> fallback
    assert result["bare"]["message"] == "fb"
    assert result["nullError"]["message"] == "fb"
    assert result["nullError"]["status"] == ""


# ---------------------------------------------------------------------------
# common/import_tools.js: Enter-tangent i modal + insamling av ifyllda rader.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def import_tools_page(chromium_browser):
    page = _script_page(chromium_browser, IMPORT_TOOLS_JS)
    yield page
    page.close()


def test_modal_enter_triggers_primary_only_in_plain_field(import_tools_page):
    result = import_tools_page.evaluate(
        """() => {
            document.body.innerHTML = `
              <div class="modal">
                <input id="txt" type="text" />
                <textarea id="ta"></textarea>
                <input id="cb" type="checkbox" />
                <input id="rd" type="radio" />
                <button id="btn">Annan</button>
                <div class="actions"><button class="primary" id="prim">OK</button></div>
              </div>`;
            let clicks = 0;
            document.getElementById("prim").addEventListener("click", () => { clicks += 1; });
            const fire = (id, opts = {}) => {
                const before = clicks;
                document.getElementById(id).dispatchEvent(
                    new KeyboardEvent("keydown", Object.assign({ key: "Enter", bubbles: true }, opts))
                );
                return clicks - before;
            };
            return {
                text: fire("txt"),            // vanligt fält -> triggar .primary
                textarea: fire("ta"),         // ignoreras
                checkbox: fire("cb"),         // ignoreras
                radio: fire("rd"),            // ignoreras
                button: fire("btn"),          // ignoreras (redan knapp)
                shiftText: fire("txt", { shiftKey: true }),  // modifierare -> ignoreras
                repeatText: fire("txt", { repeat: true }),   // repeat -> ignoreras
                otherKey: fire("txt", { key: "a" }),         // ej Enter -> ignoreras
            };
        }"""
    )
    assert result["text"] == 1
    assert result["textarea"] == 0
    assert result["checkbox"] == 0
    assert result["radio"] == 0
    assert result["button"] == 0
    assert result["shiftText"] == 0
    assert result["repeatText"] == 0
    assert result["otherKey"] == 0


def test_modal_enter_ignored_outside_modal(import_tools_page):
    # Fält utanför .modal ska aldrig trigga något.
    result = import_tools_page.evaluate(
        """() => {
            document.body.innerHTML = `
              <input id="loose" type="text" />
              <div class="modal"><div class="actions"><button class="primary" id="prim2">OK</button></div></div>`;
            let clicks = 0;
            document.getElementById("prim2").addEventListener("click", () => { clicks += 1; });
            document.getElementById("loose").dispatchEvent(
                new KeyboardEvent("keydown", { key: "Enter", bubbles: true })
            );
            return clicks;
        }"""
    )
    assert result == 0


def test_collect_bulk_import_rows_only_filled(import_tools_page):
    rows = import_tools_page.evaluate(
        """(cols) => {
            const tbody = document.createElement("tbody");
            const mk = (vals) => {
                const tr = document.createElement("tr");
                cols.forEach((c, i) => {
                    const inp = document.createElement("input");
                    inp.setAttribute("data-bulk-key", c.key);
                    inp.value = vals[i];
                    tr.appendChild(inp);
                });
                tbody.appendChild(tr);
            };
            mk(["Alice", ""]);      // delvis ifylld -> med
            mk(["", ""]);           // tom -> hoppas över
            mk(["", "5"]);          // delvis ifylld -> med
            mk(["  ", "  "]);       // bara whitespace -> trimmas bort -> hoppas över
            document.body.innerHTML = "";
            document.body.appendChild(tbody);
            return collectBulkImportRows(tbody, cols);
        }""",
        [{"key": "name"}, {"key": "qty"}],
    )
    assert rows == [
        {"name": "Alice", "qty": ""},
        {"name": "", "qty": "5"},
    ]

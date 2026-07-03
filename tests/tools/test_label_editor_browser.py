from pathlib import Path
import tempfile
from uuid import uuid4

import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="module")
def local_label_editor_server():
    output_dir = Path(tempfile.gettempdir()) / f"flow-label-editor-browser-{uuid4().hex}"
    output_dir.mkdir(parents=True, exist_ok=True)
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


def set_color_input(page, selector: str, value: str) -> None:
    page.locator(selector).evaluate(
        """(input, color) => {
            input.value = color;
            input.dispatchEvent(new Event("input", { bubbles: true }));
        }""",
        value,
    )


def test_label_editor_keyboard_shortcuts_and_symbol_picker(local_label_editor_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    objects = page.locator("#labelCanvas .label-object")
    try:
        login_admin(page, local_label_editor_server)
        page.goto(f"{local_label_editor_server}/label-editor.html", wait_until="networkidle")
        page.wait_for_selector("#labelCanvas .label-object", timeout=15000)

        expect(page.locator("#labelProfileName")).to_have_count(0)
        page.fill("#labelHeight", "200")
        page.click("#labelSaveProfile")
        expect(page.locator("#labelProfileSelect")).to_contain_text("104 x 200 mm")

        expect(objects).to_have_count(1)
        east_handle = page.locator('#labelCanvas .label-object.selected .label-object-resize-handle[data-resize-direction="e"]')
        expect(east_handle).to_be_visible()
        start_width = float(page.locator("#labelObjectW").input_value())
        handle_box = east_handle.bounding_box()
        assert handle_box
        page.mouse.move(handle_box["x"] + handle_box["width"] / 2, handle_box["y"] + handle_box["height"] / 2)
        page.mouse.down()
        page.mouse.move(handle_box["x"] + handle_box["width"] / 2 + 48, handle_box["y"] + handle_box["height"] / 2, steps=4)
        page.mouse.up()
        resized_width = float(page.locator("#labelObjectW").input_value())
        assert resized_width > start_width + 5
        page.keyboard.press("Control+Z")
        assert float(page.locator("#labelObjectW").input_value()) == pytest.approx(start_width)

        page.keyboard.press("Delete")
        expect(objects).to_have_count(0)
        page.keyboard.press("Control+Z")
        expect(objects).to_have_count(1)

        page.keyboard.press("Control+C")
        page.keyboard.press("Control+V")
        expect(objects).to_have_count(2)
        page.keyboard.press("Control+X")
        expect(objects).to_have_count(1)
        page.keyboard.press("Control+Z")
        expect(objects).to_have_count(2)

        page.keyboard.press("Backspace")
        expect(objects).to_have_count(1)
        page.keyboard.press("Control+Z")
        expect(objects).to_have_count(2)
        page.keyboard.press("Control+Y")
        expect(objects).to_have_count(1)
        page.keyboard.press("Control+Z")
        expect(objects).to_have_count(2)
        page.keyboard.press("Control+Shift+Z")
        expect(objects).to_have_count(1)

        page.click("#labelCanvas .label-object")
        page.fill("#labelObjectValue", "ABC")
        page.focus("#labelObjectValue")
        page.keyboard.press("End")
        page.keyboard.press("Backspace")
        expect(page.locator("#labelObjectValue")).to_have_value("AB")
        expect(objects).to_have_count(1)

        page.get_by_role("button", name="Symbol").click()
        expect(page.locator(".label-symbol-picker")).to_be_visible()
        expect(page.locator(".label-symbol-choice")).to_have_count(40)
        page.get_by_role("button", name="Paket").click()
        expect(objects).to_have_count(2)
        expect(page.locator("#labelCanvas .label-object").last).to_contain_text("📦")
    finally:
        context.close()


def test_label_editor_paint_tools_draw_fill_and_erase(local_label_editor_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    canvas = page.locator("#labelCanvas")
    try:
        login_admin(page, local_label_editor_server)
        page.goto(f"{local_label_editor_server}/label-editor.html", wait_until="networkidle")
        page.wait_for_selector("#labelCanvas .label-object", timeout=15000)

        expect(page.get_by_role("button", name="Penna")).to_be_visible()
        expect(page.get_by_role("button", name="Fyll")).to_be_visible()
        expect(page.get_by_role("button", name="Sudd")).to_be_visible()

        set_color_input(page, "#labelPaintColor", "#22c55e")
        page.fill("#labelPaintSize", "2.4")
        page.get_by_role("button", name="Penna").click()
        box = canvas.bounding_box()
        assert box is not None
        page.mouse.move(box["x"] + 36, box["y"] + 36)
        page.mouse.down()
        page.mouse.move(box["x"] + 88, box["y"] + 62, steps=4)
        page.mouse.up()

        drawing = page.locator('#labelCanvas .label-object[data-object-type="drawing"]')
        expect(drawing).to_have_count(1)
        expect(drawing.locator("path")).to_have_attribute("stroke", "#22c55e")

        set_color_input(page, "#labelPaintColor", "#ef4444")
        page.get_by_role("button", name="Fyll").click()
        box = canvas.bounding_box()
        assert box is not None
        page.mouse.click(box["x"] + box["width"] - 14, box["y"] + box["height"] - 14)

        background = page.locator('#labelCanvas .label-object[data-object-type="background"]')
        expect(background).to_have_count(1)
        background_color = background.locator(".label-object-background-fill").evaluate(
            "element => getComputedStyle(element).backgroundColor"
        )
        assert background_color == "rgb(239, 68, 68)"

        page.fill("#labelPaintSize", "3")
        page.get_by_role("button", name="Sudd").click()
        box = canvas.bounding_box()
        assert box is not None
        page.mouse.move(box["x"] + 48, box["y"] + 48)
        page.mouse.down()
        page.mouse.move(box["x"] + 96, box["y"] + 78, steps=4)
        page.mouse.up()

        eraser = page.locator('#labelCanvas .label-object[data-object-type="eraser"]')
        expect(eraser).to_have_count(1)
        expect(eraser.locator("path")).to_have_attribute("stroke", "#ef4444")

        page.keyboard.press("Control+Z")
        expect(eraser).to_have_count(0)
        expect(background).to_have_count(1)
        expect(drawing).to_have_count(1)
    finally:
        context.close()


def test_label_editor_fill_bucket_fills_closed_pen_shape(local_label_editor_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    canvas = page.locator("#labelCanvas")
    try:
        login_admin(page, local_label_editor_server)
        page.goto(f"{local_label_editor_server}/label-editor.html", wait_until="networkidle")
        page.wait_for_selector("#labelCanvas .label-object", timeout=15000)

        set_color_input(page, "#labelPaintColor", "#111827")
        page.fill("#labelPaintSize", "2.4")
        page.get_by_role("button", name="Penna").click()
        box = canvas.bounding_box()
        assert box is not None
        left = box["x"] + (box["width"] * 0.32)
        right = box["x"] + (box["width"] * 0.68)
        top = box["y"] + (box["height"] * 0.24)
        bottom = box["y"] + (box["height"] * 0.52)
        page.mouse.move(left, top)
        page.mouse.down()
        page.mouse.move(right, top, steps=8)
        page.mouse.move(right, bottom, steps=8)
        page.mouse.move(left, bottom, steps=8)
        page.mouse.move(left, top, steps=8)
        page.mouse.up()

        expect(page.locator('#labelCanvas .label-object[data-object-type="drawing"]')).to_have_count(1)

        set_color_input(page, "#labelPaintColor", "#ef4444")
        page.get_by_role("button", name="Fyll").click()
        page.mouse.click((left + right) / 2, (top + bottom) / 2)

        paint_fill = page.locator('#labelCanvas .label-object[data-object-type="paintFill"]')
        expect(paint_fill).to_have_count(1)
        expect(page.locator('#labelCanvas .label-object[data-object-type="background"]')).to_have_count(0)
        fill_pixels = paint_fill.locator("img").evaluate(
            """img => new Promise((resolve) => {
                const read = () => {
                    const canvas = document.createElement("canvas");
                    canvas.width = img.naturalWidth;
                    canvas.height = img.naturalHeight;
                    const ctx = canvas.getContext("2d");
                    ctx.drawImage(img, 0, 0);
                    const center = Array.from(ctx.getImageData(Math.floor(canvas.width * 0.5), Math.floor(canvas.height * 0.38), 1, 1).data);
                    const corner = Array.from(ctx.getImageData(2, 2, 1, 1).data);
                    resolve({ center, corner });
                };
                if (img.complete && img.naturalWidth) read();
                else img.addEventListener("load", read, { once: true });
            })"""
        )
        assert fill_pixels["center"] == [239, 68, 68, 255]
        assert fill_pixels["corner"][3] == 0

        page.keyboard.press("Control+Z")
        expect(paint_fill).to_have_count(0)
        expect(page.locator('#labelCanvas .label-object[data-object-type="drawing"]')).to_have_count(1)
    finally:
        context.close()

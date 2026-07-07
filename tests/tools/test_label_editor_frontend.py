import re
from pathlib import Path

from app.backend.user_access import ROLE_VIEW_DEFAULT_ACCESS, ROLE_VIEW_LABELS, ROLE_VIEW_ORDER


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "app" / "frontend"


def read_frontend(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def test_label_editor_view_is_registered_as_opt_in_experiment():
    foundation = read_frontend("js/common/foundation.js")
    access = read_frontend("js/common/access.js")
    role_access = read_frontend("js/common/role_access.js")

    assert "labelEditor" in ROLE_VIEW_ORDER
    assert ROLE_VIEW_LABELS["labelEditor"] == "Etiketter"
    assert all("labelEditor" not in role_access for role_access in ROLE_VIEW_DEFAULT_ACCESS.values())
    assert '{ id: "tools" }' in foundation
    assert '{ id: "labelEditor" }' not in foundation
    assert 'href: "/label-editor.html"' in access
    assert 'visible: canViewPage(user, "labelEditor")' in access
    assert 'sidebar: false' in access
    assert '{ id: "labelEditor", label: "Etiketter" }' in role_access


def test_label_editor_page_loads_barcode_editor_contracts():
    html = read_frontend("label-editor.html")
    editor = read_frontend("js/label_editor/editor.js")
    barcodes = read_frontend("js/label_editor/barcodes.js")
    symbols = read_frontend("js/label_editor/symbols.js")
    paint = read_frontend("js/label_editor/paint.js")
    designs = read_frontend("js/label_editor/designs.js")
    styles = read_frontend("css/styles.css")

    assert 'initPage("labelEditor")' in editor
    assert "/js/label_editor/barcodes.js" in html
    assert "/js/label_editor/symbols.js" in html
    assert "/js/label_editor/paint.js" in html
    assert "/js/label_editor/editor.js" in html
    assert 'data-add-label-object="qr"' in html
    assert 'data-add-label-object="code128"' in html
    assert 'id="labelPrint"' in html
    assert 'aria-keyshortcuts="Delete Backspace Control+Z Control+Y Control+Shift+Z Control+C Control+X Control+V"' in html
    assert 'id="labelProfileSelect"' in html
    assert 'id="labelSaveProfile"' in html
    assert 'id="labelDeleteProfile"' in html
    assert 'id="labelProfileName"' not in html
    assert 'id="labelDesignSelect"' in html
    assert 'id="labelSaveDesign"' in html
    assert 'id="labelDeleteDesign"' in html
    assert "/js/label_editor/designs.js" in html
    assert 'LABEL_DESIGN_STORAGE_KEY = "flow-label-editor-designs-v1"' in designs
    assert "window.FlowLabelDesigns = { createLabelDesigns }" in designs
    assert 'dataUrl.startsWith("data:image/")' in designs
    assert "function saveCurrentDesign()" in designs
    assert "function loadDesign(" in designs
    assert "function deleteSelectedDesign()" in designs
    assert 'prompt("Namn på etikettprofilen:", defaultName)' in designs
    assert "window.FlowLabelDesigns.createLabelDesigns({" in editor
    assert 'id="labelWidth" type="number" min="20" max="500"' in html
    assert 'id="labelHeight" type="number" min="10" max="500"' in html
    assert 'data-paint-tool="pencil"' in html
    assert 'data-paint-tool="fill"' in html
    assert 'data-paint-tool="eraser"' in html
    assert 'id="labelPaintColor"' in html
    assert 'id="labelPaintSize"' in html
    assert 'LABEL_PROFILE_STORAGE_KEY = "flow-label-editor-profiles-v1"' in editor
    assert 'LABEL_BACKGROUND_OBJECT_ID = "label-background"' in editor
    assert '{ id: "label-104x199", name: "Etikett 104 x 199", width: 104, height: 199 }' in editor
    assert '{ id: "a4-portrait", name: "A4 stående", width: 210, height: 297 }' in editor
    assert '{ id: "a5-portrait", name: "A5 stående", width: 148, height: 210 }' in editor
    assert '{ id: "a3-portrait", name: "A3 stående", width: 297, height: 420 }' in editor
    assert 'localStorage.setItem(LABEL_PROFILE_STORAGE_KEY' in editor
    assert "const defaultName = `${width} x ${height} mm`.slice(0, 40);" in editor
    assert 'prompt("Namn på storleksprofilen:", defaultName)' in editor
    assert "const name = (input.trim() || defaultName).slice(0, 40);" in editor
    assert 'state.label.width = clamp(width, LABEL_MIN_WIDTH_MM, LABEL_MAX_WIDTH_MM);' in editor
    assert 'state.label.height = clamp(height, LABEL_MIN_HEIGHT_MM, LABEL_MAX_HEIGHT_MM);' in editor
    assert "function setupKeyboardShortcuts()" in editor
    assert "function startPaintStroke" in paint
    assert "function fillBackground" in paint
    assert "function fillClosedRegion" in paint
    assert "function createFloodFillDataUrl" in paint
    assert "function handlePaintPointerDown" in paint
    assert "type: isEraser ? \"eraser\" : \"drawing\"" in paint
    assert 'type: "paintFill"' in paint
    assert "window.FlowLabelPaint = { createPaintTools }" in paint
    assert "label-object-noninteractive" in editor
    assert "paintFill: \"Fyllning\"" in editor
    assert "label-object-paint-fill" in editor
    assert ".label-editor-paint-tools" in styles
    assert ".label-canvas.paint-tool-pencil" in styles
    assert ".label-object-paint-fill" in styles
    assert "SYMBOL_PICKER_GROUPS" in symbols
    assert "window.FlowLabelSymbols" in symbols
    assert "function openSymbolDialog()" in editor
    assert "label-symbol-picker" in editor
    assert 'LABEL_RESIZE_DIRECTIONS = ["nw", "n", "ne", "e", "se", "s", "sw", "w"]' in editor
    assert 'data-resize-direction="${direction}"' in editor
    assert "function startResizeObject(event)" in editor
    assert 'track("resize-object"' in editor
    assert ".label-object-resize-handle" in styles
    assert '.label-object-resize-handle[data-resize-direction="e"]' in styles
    assert 'data-symbol-value="${escapeHtml(item.value)}"' in symbols
    assert '{ value: "emoji-package", label: "Paket", glyph: "📦" }' in symbols
    assert 'key === "delete" || key === "backspace"' in editor
    assert 'shortcut && key === "c"' in editor
    assert 'shortcut && key === "x"' in editor
    assert 'shortcut && key === "v"' in editor
    assert 'shortcut && key === "z"' in editor
    assert 'shortcut && key === "y"' in editor
    assert "closest(\"input, textarea, select, [contenteditable=" in editor
    assert "Inget kopierat etikettobjekt att klistra in" in editor
    assert "Inget objekt är markerat" in editor
    assert "window.FlowLabelBarcodes = { code128Svg, qrSvg }" in barcodes

    code128_patterns = re.search(r"CODE128_PATTERNS = \[(.*?)\];", barcodes, re.S)
    assert code128_patterns, "Code128 pattern table saknas"
    assert len(re.findall(r'"[0-9]{6,7}"', code128_patterns.group(1))) == 107
    assert "QR_VERSIONS_L" in barcodes
    assert "1: { data: 19, ecc: 7, blocks: 1 }" in barcodes
    assert "6: { data: 136, ecc: 18, blocks: 2 }" in barcodes

from pathlib import Path
import re
from tools.frontend_sources import (
    read_overview_frontend,
    read_persons_frontend,
    read_productivity_overview_frontend,
    read_sankey_inbound_frontend,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEDULE_SCRIPT_FILES = [
    "state.js",
    "ui_core.js",
    "activity_capacity.js",
    "loan.js",
    "person_order.js",
    "segments_undo.js",
    "calculator.js",
    "rendering.js",
    "summary.js",
    "editing.js",
    "data.js",
    "copy_modal.js",
    "boot.js",
]


def read_schedule_frontend() -> str:
    frontend = ROOT / "app" / "frontend"
    schedule_dir = frontend / "js" / "schedule"
    parts = [(schedule_dir / filename).read_text(encoding="utf-8") for filename in SCHEDULE_SCRIPT_FILES]
    parts.append((frontend / "js" / "schedule.js").read_text(encoding="utf-8"))
    return "\n".join(parts)


def _function_body(source: str, name: str) -> str:
    match = re.search(rf"function {name}\([^)]*\) {{(?P<body>.*?)\n}}\n", source, re.S)
    assert match, f"Missing function {name}"
    return match.group("body")


def test_persons_view_uses_delete_button_without_active_toggle():
    frontend = ROOT / "app" / "frontend"
    persons_js = read_persons_frontend()
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    assert "person-active-toggle" not in persons_js
    assert "data-active-toggle" not in persons_js
    assert "person-active-toggle.is-active" not in styles
    assert "person-active-toggle.is-inactive" not in styles
    assert "data-delete" in persons_js
    assert "Ta bort personen permanent?" in persons_js
    assert "Inaktivera" not in persons_js
    assert "api.del(`/api/persons/" in persons_js


def test_persons_view_has_ctrl_z_undo_for_person_changes():
    persons_js = read_persons_frontend()

    assert "personUndoStack" in persons_js
    assert "pushPersonUndo" in persons_js
    assert "undoLastPersonAction" in persons_js
    assert "installPersonUndoShortcut()" in persons_js
    assert 'e.key.toLowerCase() !== "z"' in persons_js
    assert "personPayloadFromSnapshot(action.before)" in persons_js


def test_persons_view_has_no_active_inactive_modes():
    frontend = ROOT / "app" / "frontend"
    persons_html = (frontend / "personer.html").read_text(encoding="utf-8")
    persons_js = read_persons_frontend()
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    assert 'data-person-status="active"' not in persons_html
    assert 'data-person-status="inactive"' not in persons_html
    assert 'data-person-status="all"' not in persons_html
    assert 'id="show-inactive"' not in persons_html
    assert "statusMode" not in persons_js
    assert 'api.getSwr(`/api/persons${query ? `?${query}` : ""}`' in persons_js
    assert ".person-status-tabs" not in styles


def test_persons_view_exposes_required_noman_field():
    frontend = ROOT / "app" / "frontend"
    persons_html = (frontend / "personer.html").read_text(encoding="utf-8")
    persons_js = read_persons_frontend()

    assert '<th data-sort="noman">NoMan' in persons_html
    assert 'data-filter="noman"' in persons_html
    assert 'const filters = { name: "", noman: "", rfid_code: "", collar_type: "", business: "", home_area: "", home_activity: "", sort_order: "" }' in persons_js
    assert 'case "noman": return (p.noman || "").toLowerCase();' in persons_js
    assert 'editText(tdNoman, p, "noman", p.noman || "", "NoMan")' in persons_js
    assert '{ key: "noman", label: "NoMan", required: true }' in persons_js
    assert 'noman: /** @type {HTMLInputElement} */ (document.getElementById("m-noman")).value.trim()' in persons_js
    assert 'if (!payload.noman) { showToast("NoMan krävs", "error"); return; }' in persons_js


def test_persons_view_exposes_optional_rfid_field():
    frontend = ROOT / "app" / "frontend"
    persons_html = (frontend / "personer.html").read_text(encoding="utf-8")
    persons_js = read_persons_frontend()

    assert '<th data-sort="rfid_code">RFID' in persons_html
    assert 'data-filter="rfid_code"' in persons_html
    assert 'case "rfid_code": return (p.rfid_code || "").toLowerCase();' in persons_js
    assert 'editText(tdRfid, p, "rfid_code", p.rfid_code || "", "RFID")' in persons_js
    assert '{ key: "rfid_code", label: "RFID", required: false }' in persons_js
    assert 'rfid_code: /** @type {HTMLInputElement} */ (document.getElementById("m-rfid")).value.trim()' in persons_js
    assert 'rfid_code: person.rfid_code ?? null' in persons_js


def test_persons_view_exposes_collar_type_field():
    frontend = ROOT / "app" / "frontend"
    persons_html = (frontend / "personer.html").read_text(encoding="utf-8")
    persons_js = read_persons_frontend()

    assert '<th data-sort="collar_type">Arbetstyp' in persons_html
    assert 'data-filter="collar_type"' in persons_html
    assert 'const PERSON_COLLAR_TYPES = [' in persons_js
    assert '{ value: "blue_collar", label: "Blue collar" }' in persons_js
    assert '{ value: "white_collar", label: "White collar" }' in persons_js
    assert 'case "collar_type": return collarTypeLabel(p.collar_type).toLowerCase();' in persons_js
    assert 'editChoice(tdCollarType, p, "collar_type", p.collar_type || "blue_collar", PERSON_COLLAR_TYPES, "arbetstyp")' in persons_js
    assert '{ key: "collar_type", label: "Arbetstyp", required: false, type: "select", options: PERSON_COLLAR_TYPES }' in persons_js
    assert 'collar_type: /** @type {HTMLInputElement} */ (document.getElementById("m-collar-type")).value || "blue_collar"' in persons_js
    assert 'collar_type: person.collar_type || "blue_collar"' in persons_js


def test_persons_view_shows_business_column():
    frontend = ROOT / "app" / "frontend"
    persons_html = (frontend / "personer.html").read_text(encoding="utf-8")
    persons_js = read_persons_frontend()

    assert '<th data-sort="business">Verksamhet' in persons_html
    assert 'data-filter="business"' in persons_html
    assert "function businessName(id)" in persons_js
    assert "businessName(p.business_id)" in persons_js
    assert 'case "business": return businessName(p.business_id).toLowerCase();' in persons_js
    assert 'tdBusiness.textContent = businessName(p.business_id);' in persons_js


def test_persons_view_opens_productivity_dialog_on_double_click():
    frontend = ROOT / "app" / "frontend"
    persons_js = read_persons_frontend()
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    assert "function openPersonProductivityModal(person)" in persons_js
    assert 'tr.addEventListener("dblclick"' in persons_js
    assert "`/api/productivity/persons/${personId}?${params.toString()}`" in persons_js
    assert "PERSON_PRODUCTIVITY_CACHE_TTL_MS" in persons_js
    assert "cachedPersonProductivity(url)" in persons_js
    assert "cacheTtlMs: PERSON_PRODUCTIVITY_CACHE_TTL_MS" in persons_js
    assert "skipCache: true" not in _function_body(persons_js, "loadPersonProductivityModal")
    assert 'data-period="week"' in persons_js
    assert 'data-period="month"' in persons_js
    assert 'data-period="year"' in persons_js
    assert 'data-period="custom"' in persons_js
    assert ".person-productivity-summary" in styles
    assert ".person-productivity-table" in styles


def test_persons_view_refetches_with_area_focus_to_prevent_super_user_leaks():
    persons_js = read_persons_frontend()

    load_body = _function_body(persons_js, "loadPersons")
    render_body = _function_body(persons_js, "renderRows")
    matches_body = _function_body(persons_js, "matchesAreaFocus")

    # areaFocusListParams skickar area_id vid områdesfokus och business_id vid
    # ∞ + verksamhetsfokus (2026-07-07) — samma läckageskydd, plus verksamhet.
    assert "const params = areaFocusListParams(areas);" in load_body
    assert 'api.getSwr(`/api/persons${query ? `?${query}` : ""}`' in load_body
    assert 'api.get("/api/persons")' not in load_body
    assert "persons.filter(matchesAreaFocus).filter(passesFilter)" in render_body
    assert "Number(person?.home_area_id) === Number(areaId)" in matches_body
    assert "matchesAreaFocusBusiness(person?.business_id)" in matches_body
    assert 'window.addEventListener("flow:areaFocusChanged", () => loadPersons())' in persons_js
    assert 'window.addEventListener("flow:areaFocusChanged", () => renderRows())' not in persons_js


def test_planning_views_drag_person_names_to_persist_sort_order():
    frontend = ROOT / "app" / "frontend"
    schedule_js = read_schedule_frontend()
    overview_js = read_overview_frontend()
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    for source in (schedule_js, overview_js):
        assert "setupPersonOrderDrag()" in source
        assert "setupPersonOrderNameCell" in source
        assert 'canEditPage(user, "personSortOrder")' in source
        assert 'api.put("/api/persons/sort-order"' in source
        # Bemanning använder state, Översikt overviewState efter namnrymdsflytten.
        assert (
            "Number(person?.home_area_id) === Number(state.currentUser?.area_id)" in source
            or "Number(person?.home_area_id) === Number(overviewState.currentUser?.area_id)" in source
        )
        assert "Rensa personfiltret innan du sorterar personer." in source

    assert "person-order-draggable" in styles
    assert "person-order-drop-before" in styles
    assert "person-order-drop-after" in styles


def test_schedule_does_not_infer_home_activity_from_home_area():
    schedule_js = read_schedule_frontend()

    assert "defaultHomeActivityId" not in schedule_js
    assert "return person?.home_activity_id || null;" in _function_body(schedule_js, "homeActivityIdForPerson")
    assert 'td.classList.add("scheduled-empty")' in schedule_js
    assert 'part.classList.add("scheduled-empty-half")' in schedule_js

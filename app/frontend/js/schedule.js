// Bemanningsvy – matris person × timme.

const HOURS = Array.from({ length: 18 }, (_, i) => 6 + i);   // 6..23
const DAYS = { 1: "Måndag", 2: "Tisdag", 3: "Onsdag", 4: "Torsdag", 5: "Fredag", 6: "Lördag", 7: "Söndag" };

const state = {
  year: 0,
  week: 0,
  weekday: 1,
  areaId: null,
  areas: [],
  activities: [],
  activitiesActive: [],
  persons: [],
  cells: new Map(),            // key = `${person_id}:${hour}` → {activity_id, version}
  scheduledHours: {},          // {person_id: Set<hour>}
  focusedCell: null,
  clipboard: null,
};

const drag = {
  active: false,
  sourceTd: null,
  sourceActivityId: null,
  sourceRow: -1,
  sourceCol: -1,
};


// ---- ISO-vecka för "nu" ----
function isoWeek(d = new Date()) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((date - yearStart) / 86400000 + 1) / 7);
  return { year: date.getUTCFullYear(), week, weekday: dayNum };
}


// ---- Rendering ----
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
}

function buildHeader() {
  const header = document.getElementById("headerRow");
  while (header.children.length > 2) header.removeChild(header.lastChild);
  HOURS.forEach((h) => {
    const th = document.createElement("th");
    th.textContent = String(h).padStart(2, "0") + ":00";
    header.appendChild(th);
  });
}

function activityById(id) {
  return state.activities.find((a) => a.id === id);
}

function colorFor(activityId) {
  const a = activityById(activityId);
  return a ? a.color : "#ffffff";
}

function setCellVisual(td, activityId, version) {
  const sel = td.querySelector("select");
  if (sel) {
    sel.value = activityId ? String(activityId) : "";
    sel.dataset.version = version || 0;
    sel.dataset.activityId = activityId || "";
    sel.style.background = activityId ? colorFor(activityId) : "transparent";
  }
  td.dataset.version = version || 0;
  td.dataset.activityId = activityId || "";

  // Bakgrundsfärg: aktivitet > schemalagd-grund > inget
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  const scheduledSet = state.scheduledHours[personId];
  const isScheduled = scheduledSet && scheduledSet.has(hour);

  if (activityId) {
    td.style.background = colorFor(activityId);
    td.classList.remove("scheduled-empty");
  } else if (isScheduled) {
    td.style.background = "";
    td.classList.add("scheduled-empty");
  } else {
    td.style.background = "#fff";
    td.classList.remove("scheduled-empty");
  }

  // Drag-handle – bara på celler med värde
  const existing = td.querySelector(".drag-handle");
  if (activityId) {
    if (!existing) {
      const h = document.createElement("span");
      h.className = "drag-handle";
      h.title = "Dra för att fylla flera celler";
      td.appendChild(h);
    }
  } else if (existing) {
    existing.remove();
  }
}

function buildRows() {
  const body = document.getElementById("scheduleBody");
  body.innerHTML = "";

  state.persons.forEach((person, rowIndex) => {
    const tr = document.createElement("tr");
    tr.dataset.personId = person.id;
    tr.dataset.rowIndex = rowIndex;

    const name = document.createElement("td");
    name.className = "name";
    name.textContent = person.name;
    tr.appendChild(name);

    const base = document.createElement("td");
    base.className = "base";
    const homeArea = state.areas.find((a) => a.id === person.home_area_id);
    base.textContent = homeArea ? homeArea.name : "";
    tr.appendChild(base);

    HOURS.forEach((hour, colIndex) => {
      const td = document.createElement("td");
      td.dataset.personId = person.id;
      td.dataset.hour = hour;
      td.dataset.rowIndex = rowIndex;
      td.dataset.colIndex = colIndex;
      td.tabIndex = -1;  // gör fokuserbart men inte tab-navigerat

      const select = document.createElement("select");
      select.dataset.personId = person.id;
      select.dataset.hour = hour;
      select.dataset.version = 0;
      select.dataset.activityId = "";

      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "–";
      select.appendChild(empty);

      state.activitiesActive.forEach((act) => {
        const opt = document.createElement("option");
        opt.value = String(act.id);
        opt.textContent = act.label;
        opt.style.background = act.color;
        select.appendChild(opt);
      });

      select.addEventListener("change", () => onCellChange(td));
      select.addEventListener("focus", () => focusCell(td));

      td.appendChild(select);
      tr.appendChild(td);
    });

    body.appendChild(tr);
  });

  applyCells();
}

function applyCells() {
  document.querySelectorAll("#scheduleBody td[data-hour]").forEach((td) => {
    setCellVisual(td, null, 0);
  });

  state.cells.forEach((info, key) => {
    const [pid, hour] = key.split(":");
    const td = document.querySelector(
      `#scheduleBody td[data-person-id="${pid}"][data-hour="${hour}"]`
    );
    if (!td) return;
    setCellVisual(td, info.activity_id, info.version);
  });
}


// ---- Cell-update flow ----
async function onCellChange(td) {
  const sel = td.querySelector("select");
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  const expectedVersion = Number(td.dataset.version) || 0;
  const newActivityId = sel.value ? Number(sel.value) : null;

  try {
    const resp = await api.put("/api/schedule/cell", {
      year: state.year, week: state.week, weekday: state.weekday,
      hour, person_id: personId, activity_id: newActivityId,
      expected_version: expectedVersion,
    });
    const c = resp.cell;
    setCellVisual(td, c.activity_id, c.version);
    state.cells.set(`${personId}:${hour}`, { activity_id: c.activity_id, version: c.version });
    refreshSummary();
  } catch (err) {
    if (err.status === 409) {
      showToast("Cellen ändrades av någon annan – läste in på nytt", "warn");
      await loadSchedule();
    } else {
      showToast("Kunde inte spara: " + err.message, "error");
      const stored = state.cells.get(`${personId}:${hour}`);
      setCellVisual(td, stored?.activity_id || null, stored?.version || 0);
    }
  }
}


// ---- Focus + Clipboard ----
function focusCell(td) {
  if (state.focusedCell?.td) state.focusedCell.td.classList.remove("focused");
  state.focusedCell = {
    td,
    personId: Number(td.dataset.personId),
    hour: Number(td.dataset.hour),
  };
  td.classList.add("focused");
  // Tar bort fokus från select så Ctrl+C/V/X-events går till document, inte fångas av select
  if (document.activeElement && document.activeElement.tagName === "SELECT") {
    document.activeElement.blur();
  }
}

function clipboardLabel(activityId) {
  const a = activityById(activityId);
  return a ? a.label : "(tom)";
}

async function copyFocused(cut = false) {
  if (!state.focusedCell) return;
  const { td, personId, hour } = state.focusedCell;
  const activityId = td.dataset.activityId ? Number(td.dataset.activityId) : null;
  state.clipboard = { activity_id: activityId };
  td.classList.add("clipboard-flash");
  setTimeout(() => td.classList.remove("clipboard-flash"), 500);

  if (cut && activityId != null) {
    const expectedVersion = Number(td.dataset.version) || 0;
    try {
      const resp = await api.put("/api/schedule/cell", {
        year: state.year, week: state.week, weekday: state.weekday,
        hour, person_id: personId, activity_id: null,
        expected_version: expectedVersion,
      });
      setCellVisual(td, resp.cell.activity_id, resp.cell.version);
      state.cells.set(`${personId}:${hour}`, { activity_id: resp.cell.activity_id, version: resp.cell.version });
      refreshSummary();
      showToast(`Klippt: ${clipboardLabel(activityId)}`);
    } catch (e) {
      if (e.status === 409) { showToast("Konflikt – läser om", "warn"); await loadSchedule(); }
      else showToast("Kunde inte klippa: " + e.message, "error");
    }
  } else {
    showToast(`Kopierat: ${clipboardLabel(activityId)}`);
  }
}

async function pasteFocused() {
  if (!state.focusedCell || state.clipboard == null) return;
  const { td, personId, hour } = state.focusedCell;
  const expectedVersion = Number(td.dataset.version) || 0;
  try {
    const resp = await api.put("/api/schedule/cell", {
      year: state.year, week: state.week, weekday: state.weekday,
      hour, person_id: personId, activity_id: state.clipboard.activity_id,
      expected_version: expectedVersion,
    });
    setCellVisual(td, resp.cell.activity_id, resp.cell.version);
    state.cells.set(`${personId}:${hour}`, { activity_id: resp.cell.activity_id, version: resp.cell.version });
    refreshSummary();
    showToast(`Klistrade in: ${clipboardLabel(state.clipboard.activity_id)}`);
  } catch (e) {
    if (e.status === 409) { showToast("Konflikt – läser om", "warn"); await loadSchedule(); }
    else showToast("Kunde inte klistra in: " + e.message, "error");
  }
}

function setupKeyboard() {
  document.addEventListener("keydown", (e) => {
    const active = document.activeElement;
    if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) return;
    if (!(e.ctrlKey || e.metaKey)) return;
    const key = e.key.toLowerCase();
    if (!["c", "x", "v"].includes(key)) return;

    if (!state.focusedCell) {
      showToast("Klicka först på en cell för att markera den", "warn");
      return;
    }
    e.preventDefault();
    if (key === "c") copyFocused(false);
    else if (key === "x") copyFocused(true);
    else if (key === "v") pasteFocused();
  });
}


// ---- Drag-to-fill ----
function getDragRect() {
  const r0 = Math.min(drag.sourceRow, drag.currentRow);
  const r1 = Math.max(drag.sourceRow, drag.currentRow);
  const c0 = Math.min(drag.sourceCol, drag.currentCol);
  const c1 = Math.max(drag.sourceCol, drag.currentCol);
  return { r0, r1, c0, c1 };
}

function updateDragTargets() {
  document.querySelectorAll("#scheduleBody td.drag-target").forEach((t) => t.classList.remove("drag-target"));
  if (!drag.active) return;
  const { r0, r1, c0, c1 } = getDragRect();
  document.querySelectorAll("#scheduleBody td[data-row-index]").forEach((td) => {
    const r = Number(td.dataset.rowIndex);
    const c = Number(td.dataset.colIndex);
    if (r >= r0 && r <= r1 && c >= c0 && c <= c1) td.classList.add("drag-target");
  });
}

async function finishDrag() {
  if (!drag.active) return;
  drag.active = false;
  document.body.classList.remove("dragging");
  drag.sourceTd?.classList.remove("drag-source-cell");

  const targets = Array.from(document.querySelectorAll("#scheduleBody td.drag-target"));
  document.querySelectorAll("#scheduleBody td.drag-target").forEach((t) => t.classList.remove("drag-target"));

  if (targets.length === 0 || (targets.length === 1 && targets[0] === drag.sourceTd)) return;
  if (targets.length > 200) { showToast("För många celler (max 200)", "error"); return; }

  const cells = targets
    .filter((td) => td !== drag.sourceTd)
    .map((td) => ({
      year: state.year, week: state.week, weekday: state.weekday,
      hour: Number(td.dataset.hour),
      person_id: Number(td.dataset.personId),
      activity_id: drag.sourceActivityId,
      expected_version: Number(td.dataset.version) || 0,
    }));

  if (cells.length === 0) return;

  try {
    const resp = await api.post("/api/schedule/cells", { cells, atomic: true, action: "drag_fill" });
    resp.applied.forEach((c) => {
      const td = document.querySelector(
        `#scheduleBody td[data-person-id="${c.person_id}"][data-hour="${c.hour}"]`
      );
      if (td) setCellVisual(td, c.activity_id, c.version);
      state.cells.set(`${c.person_id}:${c.hour}`, { activity_id: c.activity_id, version: c.version });
    });
    refreshSummary();
    showToast(`Fyllde ${resp.applied.length} celler`);
  } catch (e) {
    if (e.status === 409) {
      showToast(`${e.body?.conflicts?.length ?? 0} konflikter – läser om`, "warn");
      await loadSchedule();
    } else {
      showToast("Drag misslyckades: " + e.message, "error");
    }
  }
}

function setupDrag() {
  const body = document.getElementById("scheduleBody");

  body.addEventListener("mousedown", (e) => {
    const handle = e.target.closest(".drag-handle");
    if (!handle) return;
    const td = handle.parentElement;
    if (!td.dataset.activityId) return;
    e.preventDefault();
    drag.active = true;
    drag.sourceTd = td;
    drag.sourceActivityId = Number(td.dataset.activityId);
    drag.sourceRow = Number(td.dataset.rowIndex);
    drag.sourceCol = Number(td.dataset.colIndex);
    drag.currentRow = drag.sourceRow;
    drag.currentCol = drag.sourceCol;
    document.body.classList.add("dragging");
    td.classList.add("drag-source-cell");
    updateDragTargets();
  });

  body.addEventListener("mouseover", (e) => {
    if (!drag.active) return;
    const td = e.target.closest("td[data-hour]");
    if (!td) return;
    drag.currentRow = Number(td.dataset.rowIndex);
    drag.currentCol = Number(td.dataset.colIndex);
    updateDragTargets();
  });

  document.addEventListener("mouseup", () => { if (drag.active) finishDrag(); });

  // Klick på cell → focus (även när man klickar på själva td:n)
  body.addEventListener("click", (e) => {
    const td = e.target.closest("td[data-hour]");
    if (td) focusCell(td);
  });

  // När dropdown stänger (blur), behåll fokus på td så Ctrl+C/V/X funkar
  body.addEventListener("change", (e) => {
    const td = e.target.closest("td[data-hour]");
    if (td) {
      focusCell(td);
      setTimeout(() => td.focus(), 0);
    }
  });
}


// ---- Summary ----
async function refreshSummary() {
  const rows = await api.get(
    `/api/schedule/summary?year=${state.year}&week=${state.week}&weekday=${state.weekday}` +
      (state.areaId ? `&area_id=${state.areaId}` : "")
  );
  const tbody = document.getElementById("summaryBody");
  tbody.innerHTML = "";
  rows.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td style="background: ${r.color}; padding: 5px;">${escapeHtml(r.activity_label)}</td>
      <td>${r.hours}</td>
      <td>${r.persons_equiv.toFixed(1)}</td>`;
    tbody.appendChild(tr);
  });
}


// ---- Load ----
async function loadAreasAndActivities() {
  const [areas, activities, activitiesAll] = await Promise.all([
    api.get("/api/areas"),
    api.get("/api/activities"),
    api.get("/api/activities?include_inactive=true"),
  ]);
  state.areas = areas;
  state.activitiesActive = activities;
  state.activities = activitiesAll;

  const sel = document.getElementById("areaSelect");
  sel.innerHTML = "";
  const allOpt = document.createElement("option");
  allOpt.value = "";
  allOpt.textContent = "Alla";
  sel.appendChild(allOpt);
  areas.forEach((a) => {
    const opt = document.createElement("option");
    opt.value = a.id;
    opt.textContent = a.name;
    sel.appendChild(opt);
  });
  if (areas.length > 0) state.areaId = areas[0].id;
  sel.value = state.areaId == null ? "" : String(state.areaId);
}

async function loadSchedule() {
  const data = await api.get(
    `/api/schedule?year=${state.year}&week=${state.week}&weekday=${state.weekday}` +
      (state.areaId ? `&area_id=${state.areaId}` : "")
  );
  state.persons = data.persons;
  state.cells = new Map();
  state.focusedCell = null;
  data.cells.forEach((c) => {
    state.cells.set(`${c.person_id}:${c.hour}`, { activity_id: c.activity_id, version: c.version });
  });
  state.scheduledHours = {};
  Object.entries(data.scheduled_hours || {}).forEach(([pid, hours]) => {
    state.scheduledHours[Number(pid)] = new Set(hours);
  });

  const areaName = state.areaId == null ? "Alla" : (state.areas.find((a) => a.id === state.areaId)?.name || "");
  document.getElementById("sectionTitle").textContent =
    `${DAYS[state.weekday]} – ${areaName} – V${state.week}/${state.year}`;

  buildRows();
  refreshSummary();
}


// ---- Init ----
(async () => {
  await initPage("schedule");
  await loadAreasAndActivities();

  const now = isoWeek();
  state.year = now.year;
  state.week = now.week;
  state.weekday = now.weekday <= 5 ? now.weekday : 1;

  document.getElementById("yearInput").value = state.year;
  document.getElementById("weekInput").value = state.week;
  document.getElementById("daySelect").value = String(state.weekday);

  buildHeader();
  await loadSchedule();
  setupDrag();
  setupKeyboard();

  const onControlChange = async () => {
    state.year = Number(document.getElementById("yearInput").value) || state.year;
    state.week = Number(document.getElementById("weekInput").value) || state.week;
    state.weekday = Number(document.getElementById("daySelect").value);
    const areaVal = document.getElementById("areaSelect").value;
    state.areaId = areaVal === "" ? null : Number(areaVal);
    await loadSchedule();
  };

  document.getElementById("yearInput").addEventListener("change", onControlChange);
  document.getElementById("weekInput").addEventListener("change", onControlChange);
  document.getElementById("daySelect").addEventListener("change", onControlChange);
  document.getElementById("areaSelect").addEventListener("change", onControlChange);
  document.getElementById("reloadBtn").addEventListener("click", onControlChange);

  document.getElementById("fillLeftBtn").addEventListener("click", async () => {
    if (!confirm("Fyll tomma celler från vänster för alla personer i området?")) return;
    try {
      const r = await api.post("/api/schedule/fill-from-left", {
        year: state.year, week: state.week, weekday: state.weekday, area_id: state.areaId,
      });
      showToast(`Fyllde ${r.updated} celler`);
      await loadSchedule();
    } catch (e) { showToast("Fel: " + e.message, "error"); }
  });

  document.getElementById("clearBtn").addEventListener("click", async () => {
    if (!confirm("Rensa hela dagen för det valda området?")) return;
    try {
      const r = await api.post("/api/schedule/clear", {
        year: state.year, week: state.week, weekday: state.weekday, area_id: state.areaId,
      });
      showToast(`Rensade ${r.cleared} celler`);
      await loadSchedule();
    } catch (e) { showToast("Fel: " + e.message, "error"); }
  });

  document.getElementById("copyBtn").addEventListener("click", () => openCopyModal());
})();


function openCopyModal() {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>Kopiera dag</h2>
      <p class="note">Kopierar från en dag till en annan inom området <b>${escapeHtml(state.areas.find(a => a.id === state.areaId)?.name || 'Alla')}</b>.</p>
      <label>Från år</label><input id="cp-fy" type="number" value="${state.year}" />
      <label>Från vecka</label><input id="cp-fw" type="number" value="${state.week}" />
      <label>Från dag</label>
      <select id="cp-fd">${[1,2,3,4,5,6,7].map(d=>`<option value="${d}" ${d===state.weekday?'selected':''}>${DAYS[d]}</option>`).join("")}</select>
      <label>Till år</label><input id="cp-ty" type="number" value="${state.year}" />
      <label>Till vecka</label><input id="cp-tw" type="number" value="${state.week}" />
      <label>Till dag</label>
      <select id="cp-td">${[1,2,3,4,5,6,7].map(d=>`<option value="${d}">${DAYS[d]}</option>`).join("")}</select>
      <label><input id="cp-ow" type="checkbox" /> Skriv över befintliga celler i målet</label>
      <div class="actions">
        <button id="cp-cancel">Avbryt</button>
        <button id="cp-go" class="primary">Kopiera</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  document.getElementById("cp-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("cp-go").addEventListener("click", async () => {
    try {
      const r = await api.post("/api/schedule/copy", {
        from_year: Number(document.getElementById("cp-fy").value),
        from_week: Number(document.getElementById("cp-fw").value),
        from_weekday: Number(document.getElementById("cp-fd").value),
        to_year: Number(document.getElementById("cp-ty").value),
        to_week: Number(document.getElementById("cp-tw").value),
        to_weekday: Number(document.getElementById("cp-td").value),
        area_id: state.areaId,
        overwrite: document.getElementById("cp-ow").checked,
      });
      showToast(`Kopierade ${r.copied} celler`);
      backdrop.remove();
      await loadSchedule();
    } catch (e) { showToast("Fel: " + e.message, "error"); }
  });
}

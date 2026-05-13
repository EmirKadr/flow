// Översikt – vecka eller månad.

const DAY_NAMES = { 1: "Måndag", 2: "Tisdag", 3: "Onsdag", 4: "Torsdag", 5: "Fredag", 6: "Lördag", 7: "Söndag" };
const DAY_SHORT = { 1: "Mån", 2: "Tis", 3: "Ons", 4: "Tor", 5: "Fre", 6: "Lör", 7: "Sön" };

const state = {
  view: "week",        // "week" | "month"
  year: 0,
  week: 0,
  month: 1,
  areaId: null,
  areas: [],
  activities: [],
  activitiesActive: [],
  allPersons: [],      // rå från server
  persons: [],         // filtrerad + sorterad
  cells: [],
  days: [],
  focusedCell: null,
  nameFilter: "",
  sortKey: "sort_order",
  sortAsc: true,
};

const drag = {
  active: false,
  pending: false,
  suppressClick: false,
  sourceCell: null,    // {person_id, activity_id, date|weekday, year, week, weekday}
  sourceTd: null,
  sourceRow: -1,
  sourceCol: -1,
  currentRow: -1,
  currentCol: -1,
  startX: 0,
  startY: 0,
};


// ---- Date helpers ----
function isoWeek(d = new Date()) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((date - yearStart) / 86400000 + 1) / 7);
  return { year: date.getUTCFullYear(), week };
}

function isoWeekToMonday(year, week) {
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const jan4Dow = jan4.getUTCDay() || 7;
  const week1Mon = new Date(jan4);
  week1Mon.setUTCDate(jan4.getUTCDate() - (jan4Dow - 1));
  const monday = new Date(week1Mon);
  monday.setUTCDate(week1Mon.getUTCDate() + (week - 1) * 7);
  return monday;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
}

function activityById(id) {
  return state.activities.find((a) => a.id === id);
}

function personById(id) {
  return state.persons.find((p) => p.id === id) || state.allPersons.find((p) => p.id === id) || null;
}

function colorFor(activityId) {
  const a = activityById(activityId);
  return a ? a.color : "#ffffff";
}

function buildActivitySelect(includeActivityIds = []) {
  const select = document.createElement("select");
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "–";
  select.appendChild(empty);

  const seen = new Set();
  const appendOption = (act) => {
    if (!act || seen.has(act.id)) return;
    seen.add(act.id);
    const opt = document.createElement("option");
    opt.value = String(act.id);
    opt.textContent = act.label;
    opt.style.background = act.color;
    select.appendChild(opt);
  };

  state.activitiesActive.forEach(appendOption);
  includeActivityIds
    .map((id) => Number(id))
    .filter((id) => Number.isInteger(id))
    .forEach((id) => appendOption(activityById(id)));

  return select;
}

function focusNameFilter() {
  const input = document.getElementById("nameFilter");
  if (!input) return;
  input.focus();
  input.select();
}

function refreshPersons() {
  const q = state.nameFilter.toLowerCase().trim();
  let list = state.allPersons;
  if (q) list = list.filter((p) => p.name.toLowerCase().includes(q));
  const getSortVal = (p) => state.sortKey === "name" ? (p.name || "").toLowerCase() : p.sort_order;
  list = [...list].sort((a, b) => {
    const av = getSortVal(a), bv = getSortVal(b);
    if (av < bv) return state.sortAsc ? -1 : 1;
    if (av > bv) return state.sortAsc ? 1 : -1;
    return 0;
  });
  state.persons = list;
  document.querySelectorAll("table.overview th[data-sort]").forEach((th) => {
    const ind = th.querySelector(".sort-ind");
    if (ind) ind.textContent = th.dataset.sort === state.sortKey ? (state.sortAsc ? "▲" : "▼") : "";
  });
}

function focusDayCell(td) {
  if (state.focusedCell?.td) state.focusedCell.td.classList.remove("focused");
  state.focusedCell = {
    td,
    personId: Number(td.dataset.personId),
    year: Number(td.dataset.year),
    week: Number(td.dataset.week),
    weekday: Number(td.dataset.weekday),
    date: td.dataset.date || null,
  };
  td.classList.add("focused");
  if (document.activeElement && document.activeElement.tagName === "SELECT") {
    document.activeElement.blur();
  }
  setTimeout(() => { try { td.focus({ preventScroll: true }); } catch (e) {} }, 0);
}


// ---- Cell rendering ----
function styleCell(td, cell) {
  td.innerHTML = "";
  td.classList.remove("mixed", "is-off", "scheduled-empty");
  td.style.background = "#fff";
  const person = personById(Number(td.dataset.personId));
  const baseActivityId = cell.template_hours > 0 ? (person?.home_activity_id || null) : null;

  const isOff = cell.template_hours === 0;
  if (isOff) {
    td.classList.add("is-off");
    td.textContent = "Ledig";
    return;
  }

  if (cell.mixed) {
    td.classList.add("mixed");
  } else if (cell.activity_id) {
    td.style.background = colorFor(cell.activity_id);
  } else {
    td.classList.add("scheduled-empty");
  }

  const sel = buildActivitySelect([cell.activity_id, baseActivityId]);
  sel.value = cell.activity_id ? String(cell.activity_id) : "";

  sel.addEventListener("change", () => onDayChange(td, sel, cell));
  sel.addEventListener("focus", () => focusDayCell(td));
  sel.addEventListener("mousedown", (e) => {
    const isFocused = state.focusedCell && state.focusedCell.td === td;
    if (!isFocused) {
      e.preventDefault();
      focusDayCell(td);
    }
  });
  td.appendChild(sel);

  const info = document.createElement("div");
  info.className = "hour-info";
  if (cell.mixed) info.textContent = `Blandat (${cell.hours_total}h)`;
  else if (cell.activity_id) info.textContent = `${cell.hours_total}/${cell.template_hours}h`;
  else info.textContent = `Schemalagd (${cell.template_hours}h)`;
  td.appendChild(info);

}


// ---- VECKO-VY ----
function buildWeekHeader() {
  const header = document.getElementById("headerRow");
  while (header.children.length > 1) header.removeChild(header.lastChild);
  const monday = isoWeekToMonday(state.year, state.week);
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday);
    d.setUTCDate(monday.getUTCDate() + i);
    const th = document.createElement("th");
    th.textContent = `${DAY_SHORT[i + 1]} ${d.getUTCDate()}/${d.getUTCMonth() + 1}`;
    header.appendChild(th);
  }
}

function buildWeekBody() {
  const body = document.getElementById("overviewBody");
  body.innerHTML = "";
  const lookup = new Map();
  state.cells.forEach((m) => lookup.set(`${m.person_id}:${m.weekday}`, m));

  state.persons.forEach((p) => {
    const tr = document.createElement("tr");
    tr.dataset.personId = p.id;
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    nameTd.textContent = p.name;
    tr.appendChild(nameTd);

    for (let wd = 1; wd <= 7; wd++) {
      const cell = lookup.get(`${p.id}:${wd}`) || { activity_id: null, mixed: false, hours_total: 0, template_hours: 0 };
      const td = document.createElement("td");
      td.className = "day";
      td.dataset.personId = p.id;
      td.dataset.weekday = wd;
      td.dataset.year = state.year;
      td.dataset.week = state.week;
      td.dataset.activityId = cell.activity_id || "";
      td.dataset.templateHours = cell.template_hours;
      td.tabIndex = -1;
      styleCell(td, cell);
      tr.appendChild(td);
    }
    body.appendChild(tr);
  });
}


// ---- MÅNADS-VY ----
function buildMonthHeader() {
  const header = document.getElementById("headerRow");
  while (header.children.length > 1) header.removeChild(header.lastChild);
  state.days.forEach((d) => {
    const date = new Date(d.date);
    const th = document.createElement("th");
    th.textContent = `${DAY_SHORT[d.weekday]} ${date.getUTCDate()}/${date.getUTCMonth() + 1}`;
    if (d.weekday >= 6) th.style.opacity = "0.7";
    header.appendChild(th);
  });
}

function buildMonthBody() {
  const body = document.getElementById("overviewBody");
  body.innerHTML = "";
  const lookup = new Map();
  state.cells.forEach((m) => lookup.set(`${m.person_id}:${m.date}`, m));

  state.persons.forEach((p) => {
    const tr = document.createElement("tr");
    tr.dataset.personId = p.id;
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    nameTd.textContent = p.name;
    tr.appendChild(nameTd);

    state.days.forEach((dInfo) => {
      const cell = lookup.get(`${p.id}:${dInfo.date}`) || { activity_id: null, mixed: false, hours_total: 0, template_hours: 0 };
      const td = document.createElement("td");
      td.className = "day";
      td.dataset.personId = p.id;
      td.dataset.weekday = dInfo.weekday;
      td.dataset.year = dInfo.year;
      td.dataset.week = dInfo.week;
      td.dataset.date = dInfo.date;
      td.dataset.activityId = cell.activity_id || "";
      td.dataset.templateHours = cell.template_hours;
      td.tabIndex = -1;
      styleCell(td, cell);
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
}


// ---- Cell update ----
async function postDay(personId, year, week, weekday, activityId) {
  return api.post("/api/overview/day", {
    person_id: personId,
    year, week, weekday,
    activity_id: activityId,
  });
}

async function onDayChange(td, sel, cell) {
  const newActivityId = sel.value ? Number(sel.value) : null;
  if (cell.mixed && !confirm("Denna dag har flera olika aktiviteter. Skriv över med samma värde?")) {
    sel.value = cell.activity_id ? String(cell.activity_id) : "";
    return;
  }

  try {
    const resp = await postDay(
      Number(td.dataset.personId),
      Number(td.dataset.year),
      Number(td.dataset.week),
      Number(td.dataset.weekday),
      newActivityId,
    );
    showToast(`Bemannade ${resp.written} h, tog bort ${resp.deleted} h`);
    await load();
  } catch (e) {
    const detail = e.body?.detail || e.message;
    showToast("Kunde inte spara: " + detail, "error");
    sel.value = cell.activity_id ? String(cell.activity_id) : "";
  }
}

function updateDragTargets() {
  document.querySelectorAll("td.day.drag-target").forEach((t) => t.classList.remove("drag-target"));
  if (!drag.active) return;
  const r0 = Math.min(drag.sourceRow, drag.currentRow);
  const r1 = Math.max(drag.sourceRow, drag.currentRow);
  const c0 = Math.min(drag.sourceCol, drag.currentCol);
  const c1 = Math.max(drag.sourceCol, drag.currentCol);

  document.querySelectorAll("#overviewBody td.day").forEach((td) => {
    const r = td.parentElement.rowIndex;
    const c = td.cellIndex;
    if (r >= r0 && r <= r1 && c >= c0 && c <= c1) td.classList.add("drag-target");
  });
}

function resetDragState() {
  document.body.classList.remove("dragging-ov");
  document.querySelectorAll("td.day.drag-target").forEach((t) => t.classList.remove("drag-target"));
  drag.active = false;
  drag.pending = false;
  drag.sourceCell = null;
  drag.sourceTd = null;
  drag.sourceRow = -1;
  drag.sourceCol = -1;
  drag.currentRow = -1;
  drag.currentCol = -1;
  drag.startX = 0;
  drag.startY = 0;
}

function startPendingDrag(td, event) {
  drag.pending = true;
  drag.sourceTd = td;
  drag.sourceCell = {
    activity_id: td.dataset.activityId ? Number(td.dataset.activityId) : null,
  };
  drag.sourceRow = td.parentElement.rowIndex;
  drag.sourceCol = td.cellIndex;
  drag.currentRow = drag.sourceRow;
  drag.currentCol = drag.sourceCol;
  drag.startX = event.clientX;
  drag.startY = event.clientY;
}

function activateDrag() {
  if (!drag.pending || drag.active || !drag.sourceTd) return;
  drag.pending = false;
  drag.active = true;
  document.body.classList.add("dragging-ov");
  if (document.activeElement?.tagName === "SELECT") {
    document.activeElement.blur();
  }
  updateDragTargets();
}

function overviewCellFromPoint(clientX, clientY) {
  const el = document.elementFromPoint(clientX, clientY);
  return el?.closest("#overviewBody td.day") || null;
}


// ---- Drag-to-fill på Översikt ----
function setupDrag() {
  const body = document.getElementById("overviewBody");

  body.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    const td = e.target.closest("td.day");
    if (!td || td.classList.contains("is-off")) return;
    startPendingDrag(td, e);
  });

  document.addEventListener("mousemove", (e) => {
    if (!drag.pending && !drag.active) return;
    const moved = Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY);
    if (!drag.active) {
      if (moved < 5) return;
      activateDrag();
    }
    const td = overviewCellFromPoint(e.clientX, e.clientY);
    if (!td) return;
    drag.currentRow = td.parentElement.rowIndex;
    drag.currentCol = td.cellIndex;
    updateDragTargets();
  });

  document.addEventListener("mouseup", async () => {
    if (drag.pending && !drag.active) {
      resetDragState();
      return;
    }
    if (!drag.active) return;
    drag.suppressClick = true;
    const targets = Array.from(document.querySelectorAll("#overviewBody td.day.drag-target"));
    const sourceActivityId = drag.sourceCell?.activity_id ?? null;
    resetDragState();
    setTimeout(() => { drag.suppressClick = false; }, 0);

    if (targets.length <= 1) return;
    if (targets.length > 100) { showToast("För många celler (max 100)", "error"); return; }

    let written = 0, deleted = 0, errors = 0;
    for (const td of targets) {
      try {
        const r = await postDay(
          Number(td.dataset.personId),
          Number(td.dataset.year),
          Number(td.dataset.week),
          Number(td.dataset.weekday),
          sourceActivityId,
        );
        written += r.written;
        deleted += r.deleted;
      } catch (e) {
        errors++;
      }
    }
    showToast(`Drag klar: skrev ${written} h, tog bort ${deleted} h${errors ? `, ${errors} fel` : ""}`);
    await load();
  });

  document.addEventListener("click", (e) => {
    if (!drag.suppressClick) return;
    if (!e.target.closest("#overviewBody td.day")) return;
    e.preventDefault();
    e.stopPropagation();
    drag.suppressClick = false;
  }, true);

  body.addEventListener("click", (e) => {
    if (drag.suppressClick) return;
    const td = e.target.closest("td.day");
    if (!td || td.classList.contains("is-off")) return;
    focusDayCell(td);
  });

  body.addEventListener("change", (e) => {
    const td = e.target.closest("td.day");
    if (!td) return;
    focusDayCell(td);
    setTimeout(() => { try { td.focus(); } catch (err) {} }, 0);
  });
}


// ---- Load + navigation ----
async function loadInitial() {
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
    opt.value = a.id; opt.textContent = a.name;
    sel.appendChild(opt);
  });
  if (areas.length > 0) state.areaId = areas[0].id;
  sel.value = state.areaId == null ? "" : String(state.areaId);
}

async function load() {
  if (state.view === "week") {
    const data = await api.get(
      `/api/overview?year=${state.year}&week=${state.week}` +
        (state.areaId ? `&area_id=${state.areaId}` : "")
    );
    state.allPersons = data.persons;
    refreshPersons();
    state.cells = data.matrix;
    state.days = [];
    state.focusedCell = null;
    const areaName = state.areaId == null ? "Alla" : (state.areas.find((a) => a.id === state.areaId)?.name || "");
    document.getElementById("sectionTitle").textContent = `Översikt – ${areaName} – V${state.week}/${state.year}`;
    buildWeekHeader();
    buildWeekBody();
  } else {
    const data = await api.get(
      `/api/overview/month?year=${state.year}&month=${state.month}` +
        (state.areaId ? `&area_id=${state.areaId}` : "")
    );
    state.allPersons = data.persons;
    refreshPersons();
    state.cells = data.matrix;
    state.days = data.days;
    state.focusedCell = null;
    const areaName = state.areaId == null ? "Alla" : (state.areas.find((a) => a.id === state.areaId)?.name || "");
    const monthName = document.querySelector(`#monthSelect option[value="${state.month}"]`)?.textContent || state.month;
    document.getElementById("sectionTitle").textContent = `Översikt – ${areaName} – ${monthName} ${state.year}`;
    buildMonthHeader();
    buildMonthBody();
  }
}

function shiftPeriod(delta) {
  if (state.view === "week") {
    state.week += delta;
    if (state.week < 1) { state.year -= 1; state.week = 52; }
    if (state.week > 53) { state.year += 1; state.week = 1; }
    document.getElementById("yearInput").value = state.year;
    document.getElementById("weekInput").value = state.week;
  } else {
    state.month += delta;
    if (state.month < 1) { state.year -= 1; state.month = 12; }
    if (state.month > 12) { state.year += 1; state.month = 1; }
    document.getElementById("yearInput").value = state.year;
    document.getElementById("monthSelect").value = String(state.month);
  }
  load();
}

function updateViewVisibility() {
  const isMonth = state.view === "month";
  document.querySelectorAll(".week-only").forEach((el) => (el.hidden = isMonth));
  document.querySelectorAll(".month-only").forEach((el) => (el.hidden = !isMonth));
}


// ---- Init ----
(async () => {
  await initPage("overview");
  await loadInitial();

  const now = isoWeek();
  state.year = now.year;
  state.week = now.week;
  state.month = new Date().getMonth() + 1;

  document.getElementById("yearInput").value = state.year;
  document.getElementById("weekInput").value = state.week;
  document.getElementById("monthSelect").value = String(state.month);
  updateViewVisibility();

  await load();
  setupDrag();

  const onControlChange = async () => {
    state.year = Number(document.getElementById("yearInput").value) || state.year;
    state.week = Number(document.getElementById("weekInput").value) || state.week;
    state.month = Number(document.getElementById("monthSelect").value) || state.month;
    const areaVal = document.getElementById("areaSelect").value;
    state.areaId = areaVal === "" ? null : Number(areaVal);
    await load();
  };

  document.getElementById("yearInput").addEventListener("change", onControlChange);
  document.getElementById("weekInput").addEventListener("change", onControlChange);
  document.getElementById("monthSelect").addEventListener("change", onControlChange);
  document.getElementById("areaSelect").addEventListener("change", onControlChange);
  document.getElementById("reloadBtn").addEventListener("click", onControlChange);
  document.getElementById("prev").addEventListener("click", () => shiftPeriod(-1));
  document.getElementById("next").addEventListener("click", () => shiftPeriod(1));

  document.getElementById("viewMode").addEventListener("change", (e) => {
    state.view = e.target.value;
    updateViewVisibility();
    load();
  });

  document.getElementById("nameFilter").addEventListener("input", (e) => {
    state.nameFilter = e.target.value;
    refreshPersons();
    if (state.view === "week") buildWeekBody();
    else buildMonthBody();
  });
  document.getElementById("nameFilter").addEventListener("mousedown", (e) => e.stopPropagation());
  document.getElementById("nameFilter").addEventListener("click", (e) => e.stopPropagation());

  // Klick på Person-rubrik → sort
  document.addEventListener("click", (e) => {
    const th = e.target.closest("table.overview th[data-sort]");
    if (!th) return;
    if (th.dataset.filterTrigger && !e.shiftKey) {
      focusNameFilter();
      return;
    }
    const key = th.dataset.sort;
    if (state.sortKey === key) state.sortAsc = !state.sortAsc;
    else { state.sortKey = key; state.sortAsc = true; }
    refreshPersons();
    if (state.view === "week") buildWeekBody();
    else buildMonthBody();
  });
})();

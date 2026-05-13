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
  persons: [],
  cells: [],           // [{person_id, date|weekday, ...}, ...]
  days: [],            // för månadsvy: lista med {date, year, week, weekday}
};

const drag = {
  active: false,
  sourceCell: null,    // {person_id, activity_id, date|weekday, year, week, weekday}
  sourceTd: null,
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
function colorFor(activityId) {
  const a = activityById(activityId);
  return a ? a.color : "#ffffff";
}


// ---- Cell rendering ----
function styleCell(td, cell) {
  td.innerHTML = "";
  td.classList.remove("mixed", "is-off", "scheduled-empty");
  td.style.background = "#fff";

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

  const sel = document.createElement("select");
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "–";
  sel.appendChild(empty);
  state.activitiesActive.forEach((act) => {
    const opt = document.createElement("option");
    opt.value = String(act.id);
    opt.textContent = act.label;
    opt.style.background = act.color;
    sel.appendChild(opt);
  });
  sel.value = cell.activity_id ? String(cell.activity_id) : "";

  sel.addEventListener("change", () => onDayChange(td, sel, cell));
  td.appendChild(sel);

  const info = document.createElement("div");
  info.className = "hour-info";
  if (cell.mixed) info.textContent = `Blandat (${cell.hours_total}h)`;
  else if (cell.activity_id) info.textContent = `${cell.hours_total}/${cell.template_hours}h`;
  else info.textContent = `Schemalagd (${cell.template_hours}h)`;
  td.appendChild(info);

  // Drag-handle
  if (cell.activity_id) {
    const h = document.createElement("span");
    h.className = "ov-drag-handle";
    h.title = "Dra för att fylla flera celler";
    td.appendChild(h);
  }
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


// ---- Drag-to-fill på Översikt ----
function setupDrag() {
  const body = document.getElementById("overviewBody");

  body.addEventListener("mousedown", (e) => {
    const handle = e.target.closest(".ov-drag-handle");
    if (!handle) return;
    const td = handle.parentElement;
    if (!td.dataset.activityId) return;
    e.preventDefault();
    drag.active = true;
    drag.sourceTd = td;
    drag.sourceCell = {
      activity_id: Number(td.dataset.activityId),
    };
    document.body.classList.add("dragging-ov");
    td.classList.add("drag-target");
  });

  body.addEventListener("mouseover", (e) => {
    if (!drag.active) return;
    const td = e.target.closest("td.day");
    if (!td) return;
    // Rektangulär markering med utgångspunkt i source
    const srcRow = drag.sourceTd.parentElement.rowIndex;
    const srcCol = drag.sourceTd.cellIndex;
    const curRow = td.parentElement.rowIndex;
    const curCol = td.cellIndex;
    const r0 = Math.min(srcRow, curRow), r1 = Math.max(srcRow, curRow);
    const c0 = Math.min(srcCol, curCol), c1 = Math.max(srcCol, curCol);

    document.querySelectorAll("td.day.drag-target").forEach((t) => t.classList.remove("drag-target"));
    document.querySelectorAll("#overviewBody td.day").forEach((t) => {
      const r = t.parentElement.rowIndex;
      const c = t.cellIndex;
      if (r >= r0 && r <= r1 && c >= c0 && c <= c1) t.classList.add("drag-target");
    });
  });

  document.addEventListener("mouseup", async () => {
    if (!drag.active) return;
    drag.active = false;
    document.body.classList.remove("dragging-ov");

    const targets = Array.from(document.querySelectorAll("#overviewBody td.day.drag-target"));
    document.querySelectorAll("td.day.drag-target").forEach((t) => t.classList.remove("drag-target"));

    const sourceActivityId = drag.sourceCell.activity_id;
    drag.sourceTd = null;
    drag.sourceCell = null;

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
    state.persons = data.persons;
    state.cells = data.matrix;
    state.days = [];
    const areaName = state.areaId == null ? "Alla" : (state.areas.find((a) => a.id === state.areaId)?.name || "");
    document.getElementById("sectionTitle").textContent = `Översikt – ${areaName} – V${state.week}/${state.year}`;
    buildWeekHeader();
    buildWeekBody();
  } else {
    const data = await api.get(
      `/api/overview/month?year=${state.year}&month=${state.month}` +
        (state.areaId ? `&area_id=${state.areaId}` : "")
    );
    state.persons = data.persons;
    state.cells = data.matrix;
    state.days = data.days;
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
})();

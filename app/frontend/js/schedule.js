// Bemanningsvy – matris person × timme.

const HOURS = Array.from({ length: 18 }, (_, i) => 6 + i);   // 6..23
const DAYS = { 1: "Måndag", 2: "Tisdag", 3: "Onsdag", 4: "Torsdag", 5: "Fredag", 6: "Lördag", 7: "Söndag" };
const FULL_SEGMENT = { minute_start: 0, minute_end: 60 };
const HALF_SEGMENTS = [
  { minute_start: 0, minute_end: 30 },
  { minute_start: 30, minute_end: 60 },
];

const state = {
  year: 0,
  week: 0,
  weekday: 1,
  areaId: null,
  areas: [],
  activities: [],
  activitiesActive: [],
  allPersons: [],
  persons: [],
  cells: new Map(),            // key = `${person_id}:${hour}:${minute_start}` -> segment
  hourCells: new Map(),        // key = `${person_id}:${hour}` -> [segments]
  scheduledHours: {},          // {person_id: Set<hour>}
  focusedCell: null,
  clipboard: null,
  nameFilter: "",
  sortKey: "sort_order",
  sortAsc: true,
};

const drag = {
  active: false,
  pending: false,
  suppressClick: false,
  sourceTd: null,
  sourceActivityId: null,
  sourceRow: -1,
  sourceCol: -1,
  currentRow: -1,
  currentCol: -1,
  startX: 0,
  startY: 0,
};


function isoWeek(d = new Date()) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((date - yearStart) / 86400000 + 1) / 7);
  return { year: date.getUTCFullYear(), week, weekday: dayNum };
}

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

function personById(id) {
  return state.persons.find((p) => p.id === id) || state.allPersons.find((p) => p.id === id) || null;
}

function colorFor(activityId) {
  const a = activityById(activityId);
  return a ? a.color : "#ffffff";
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
  if (q) {
    list = list.filter((p) => {
      const areaName = state.areas.find((a) => a.id === p.home_area_id)?.name || "";
      return p.name.toLowerCase().includes(q) || areaName.toLowerCase().includes(q);
    });
  }
  const getSortVal = (p) => {
    if (state.sortKey === "name") return (p.name || "").toLowerCase();
    if (state.sortKey === "home_area") {
      return (state.areas.find((a) => a.id === p.home_area_id)?.name || "").toLowerCase();
    }
    return p.sort_order;
  };
  list = [...list].sort((a, b) => {
    const av = getSortVal(a), bv = getSortVal(b);
    if (av < bv) return state.sortAsc ? -1 : 1;
    if (av > bv) return state.sortAsc ? 1 : -1;
    return 0;
  });
  state.persons = list;

  document.querySelectorAll("table.matrix th[data-sort]").forEach((th) => {
    const ind = th.querySelector(".sort-ind");
    if (ind) ind.textContent = th.dataset.sort === state.sortKey ? (state.sortAsc ? "▲" : "▼") : "";
  });
}

function segmentKey(personId, hour, minuteStart) {
  return `${personId}:${hour}:${minuteStart}`;
}

function hourKey(personId, hour) {
  return `${personId}:${hour}`;
}

function sortSegments(segments) {
  return [...segments].sort((a, b) => a.minute_start - b.minute_start || a.minute_end - b.minute_end);
}

function setAllSegments(cells) {
  state.cells = new Map();
  state.hourCells = new Map();
  cells.forEach((cell) => {
    const normalized = {
      person_id: Number(cell.person_id),
      hour: Number(cell.hour),
      minute_start: Number(cell.minute_start),
      minute_end: Number(cell.minute_end),
      activity_id: cell.activity_id == null ? null : Number(cell.activity_id),
      version: Number(cell.version) || 0,
      updated_at: cell.updated_at || null,
      updated_by: cell.updated_by == null ? null : Number(cell.updated_by),
    };
    state.cells.set(segmentKey(normalized.person_id, normalized.hour, normalized.minute_start), normalized);
    const hk = hourKey(normalized.person_id, normalized.hour);
    if (!state.hourCells.has(hk)) state.hourCells.set(hk, []);
    state.hourCells.get(hk).push(normalized);
  });
  state.hourCells.forEach((segments, hk) => {
    state.hourCells.set(hk, sortSegments(segments));
  });
}

function segmentsForHour(personId, hour) {
  return state.hourCells.get(hourKey(personId, hour)) || [];
}

function replaceHourSegments(personId, hour, segments) {
  const hk = hourKey(personId, hour);
  const existing = state.hourCells.get(hk) || [];
  existing.forEach((segment) => state.cells.delete(segmentKey(segment.person_id, segment.hour, segment.minute_start)));

  const normalized = sortSegments((segments || []).map((segment) => ({
    person_id: Number(segment.person_id),
    hour: Number(segment.hour),
    minute_start: Number(segment.minute_start),
    minute_end: Number(segment.minute_end),
    activity_id: segment.activity_id == null ? null : Number(segment.activity_id),
    version: Number(segment.version) || 0,
    updated_at: segment.updated_at || null,
    updated_by: segment.updated_by == null ? null : Number(segment.updated_by),
  })));

  if (normalized.length === 0) {
    state.hourCells.delete(hk);
    return;
  }

  normalized.forEach((segment) => {
    state.cells.set(segmentKey(segment.person_id, segment.hour, segment.minute_start), segment);
  });
  state.hourCells.set(hk, normalized);
}

function currentSegment(personId, hour, minuteStart, minuteEnd) {
  const match = segmentsForHour(personId, hour).find(
    (segment) => segment.minute_start === minuteStart && segment.minute_end === minuteEnd
  );
  return match || {
    person_id: personId,
    hour,
    minute_start: minuteStart,
    minute_end: minuteEnd,
    activity_id: null,
    version: 0,
  };
}

function isSplitHour(segments) {
  return (
    segments.length === 2 &&
    segments[0].minute_start === 0 &&
    segments[0].minute_end === 30 &&
    segments[1].minute_start === 30 &&
    segments[1].minute_end === 60
  );
}

function isScheduledHour(personId, hour) {
  const scheduledSet = state.scheduledHours[personId];
  return !!(scheduledSet && scheduledSet.has(hour));
}

function formatHours(value) {
  const num = Number(value) || 0;
  return Number.isInteger(num) ? String(num) : num.toFixed(1).replace(/\.0$/, "");
}

function buildActivitySelect() {
  const select = document.createElement("select");
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
  return select;
}

function clearFocusedCell() {
  if (!state.focusedCell?.focusEl) return;
  state.focusedCell.focusEl.classList.remove("focused");
}

function focusSegment(td, focusEl, minuteStart, minuteEnd) {
  clearFocusedCell();
  state.focusedCell = {
    td,
    focusEl,
    personId: Number(td.dataset.personId),
    hour: Number(td.dataset.hour),
    minuteStart,
    minuteEnd,
  };
  focusEl.classList.add("focused");
  if (document.activeElement && document.activeElement.tagName === "SELECT") {
    document.activeElement.blur();
  }
  setTimeout(() => {
    try {
      focusEl.focus({ preventScroll: true });
    } catch (e) {}
  }, 0);
}

function effectiveActivityIdForTd(td) {
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  const segments = segmentsForHour(personId, hour);
  if (isSplitHour(segments)) return null;
  if (segments.length === 1 && segments[0].activity_id != null) return segments[0].activity_id;
  if (td.dataset.isBase === "1") {
    const person = personById(personId);
    return person?.home_activity_id || null;
  }
  return null;
}

function effectiveActivityIdForFocus() {
  if (!state.focusedCell) return null;
  const { personId, hour, minuteStart, minuteEnd, td } = state.focusedCell;
  const segment = currentSegment(personId, hour, minuteStart, minuteEnd);
  if (segment.activity_id != null) return segment.activity_id;
  if (minuteStart === 0 && minuteEnd === 60 && td?.dataset.isBase === "1") {
    const person = personById(personId);
    return person?.home_activity_id || null;
  }
  return null;
}

function handleFullHourContextMenu(e, td) {
  e.preventDefault();
  e.stopPropagation();
  focusSegment(td, td, 0, 60);
  void splitHourCell(td);
}

function handleSplitSegmentContextMenu(e, td, part, minuteStart, minuteEnd) {
  e.preventDefault();
  e.stopPropagation();
  focusSegment(td, part, minuteStart, minuteEnd);
}

function renderFullHourCell(td, segment, isScheduled) {
  td.dataset.split = "0";
  td.classList.remove("split-hour", "scheduled-empty", "base-value");
  td.style.background = "#fff";
  td.dataset.isBase = "";
  td.oncontextmenu = (e) => handleFullHourContextMenu(e, td);

  const person = personById(Number(td.dataset.personId));
  const explicitActivityId = segment?.activity_id ?? null;
  const effectiveActivityId = explicitActivityId != null
    ? explicitActivityId
    : (isScheduled ? (person?.home_activity_id || null) : null);
  const isBase = explicitActivityId == null && effectiveActivityId != null;

  if (explicitActivityId != null) {
    td.style.background = colorFor(explicitActivityId);
  } else if (isBase) {
    td.style.background = colorFor(effectiveActivityId);
    td.classList.add("base-value");
    td.dataset.isBase = "1";
  } else if (isScheduled) {
    td.classList.add("scheduled-empty");
  }

  const select = buildActivitySelect();
  select.className = "cell-select";
  select.value = explicitActivityId != null ? String(explicitActivityId) : "";
  select.dataset.minuteStart = "0";
  select.dataset.minuteEnd = "60";
  select.dataset.version = String(segment?.version || 0);

  select.addEventListener("change", () => onSegmentChange(td, 0, 60));
  select.addEventListener("focus", () => focusSegment(td, td, 0, 60));
  select.addEventListener("mousedown", (e) => {
    e.stopPropagation();
    const isFocused = state.focusedCell
      && state.focusedCell.td === td
      && state.focusedCell.minuteStart === 0
      && state.focusedCell.minuteEnd === 60;
    if (!isFocused) {
      e.preventDefault();
      focusSegment(td, td, 0, 60);
    }
  });
  select.addEventListener("keydown", (e) => handleSelectClipboardKeys(e), true);
  select.addEventListener("contextmenu", (e) => handleFullHourContextMenu(e, td), true);

  td.appendChild(select);
}

function renderSplitHourCell(td, segments, isScheduled) {
  td.dataset.split = "1";
  td.dataset.isBase = "";
  td.classList.add("split-hour");
  td.classList.remove("scheduled-empty", "base-value");
  td.style.background = "#fff";
  td.oncontextmenu = (e) => {
    const part = e.target.closest(".hour-segment") || td.querySelector(".hour-segment");
    if (!part) return;
    handleSplitSegmentContextMenu(
      e,
      td,
      part,
      Number(part.dataset.minuteStart),
      Number(part.dataset.minuteEnd),
    );
  };

  const wrapper = document.createElement("div");
  wrapper.className = "hour-split";

  HALF_SEGMENTS.forEach(({ minute_start, minute_end }) => {
    const segment = currentSegment(Number(td.dataset.personId), Number(td.dataset.hour), minute_start, minute_end);
    const part = document.createElement("div");
    part.className = "hour-segment";
    part.dataset.minuteStart = String(minute_start);
    part.dataset.minuteEnd = String(minute_end);
    part.tabIndex = -1;

    if (segment.activity_id != null) {
      part.style.background = colorFor(segment.activity_id);
    } else if (isScheduled) {
      part.classList.add("scheduled-empty-half");
    } else {
      part.style.background = "#fff";
    }

    const select = buildActivitySelect();
    select.className = "half-select";
    select.value = segment.activity_id != null ? String(segment.activity_id) : "";
    select.dataset.minuteStart = String(minute_start);
    select.dataset.minuteEnd = String(minute_end);
    select.dataset.version = String(segment.version || 0);

    select.addEventListener("change", () => onSegmentChange(td, minute_start, minute_end));
    select.addEventListener("focus", () => focusSegment(td, part, minute_start, minute_end));
    select.addEventListener("mousedown", (e) => {
      e.stopPropagation();
      const isFocused = state.focusedCell
        && state.focusedCell.td === td
        && state.focusedCell.minuteStart === minute_start
        && state.focusedCell.minuteEnd === minute_end;
      if (!isFocused) {
        e.preventDefault();
        focusSegment(td, part, minute_start, minute_end);
      }
    });
    select.addEventListener("keydown", (e) => handleSelectClipboardKeys(e), true);
    part.addEventListener(
      "contextmenu",
      (e) => handleSplitSegmentContextMenu(e, td, part, minute_start, minute_end),
      true,
    );
    select.addEventListener(
      "contextmenu",
      (e) => handleSplitSegmentContextMenu(e, td, part, minute_start, minute_end),
      true,
    );

    part.appendChild(select);
    wrapper.appendChild(part);
  });

  td.appendChild(wrapper);
}

function renderHourCell(td) {
  td.innerHTML = "";
  clearFocusedCell();

  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  const segments = sortSegments(segmentsForHour(personId, hour));
  const isScheduled = isScheduledHour(personId, hour);

  if (isSplitHour(segments) || segments.some((segment) => segment.minute_end - segment.minute_start === 30)) {
    renderSplitHourCell(td, segments, isScheduled);
    return;
  }

  const segment = segments.length === 1 ? segments[0] : null;
  renderFullHourCell(td, segment, isScheduled);
}

function buildRows() {
  const body = document.getElementById("scheduleBody");
  body.innerHTML = "";
  state.focusedCell = null;

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
      td.tabIndex = -1;
      renderHourCell(td);
      tr.appendChild(td);
    });

    body.appendChild(tr);
  });
}

async function onSegmentChange(td, minuteStart, minuteEnd) {
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  const segment = currentSegment(personId, hour, minuteStart, minuteEnd);
  const selector = td.querySelector(
    `select[data-minute-start="${minuteStart}"][data-minute-end="${minuteEnd}"]`
  );
  const newActivityId = selector?.value ? Number(selector.value) : null;

  try {
    const resp = await api.put("/api/schedule/cell", {
      year: state.year,
      week: state.week,
      weekday: state.weekday,
      hour,
      minute_start: minuteStart,
      minute_end: minuteEnd,
      person_id: personId,
      activity_id: newActivityId,
      expected_version: Number(segment.version) || 0,
    });
    const updated = resp.cell;
    const others = segmentsForHour(personId, hour).filter(
      (item) => !(item.minute_start === minuteStart && item.minute_end === minuteEnd)
    );
    replaceHourSegments(personId, hour, [...others, updated]);
    renderHourCell(td);
    focusMatchingSegment(td, minuteStart, minuteEnd);
    refreshSummary();
  } catch (err) {
    if (err.status === 409) {
      showToast("Cellen ändrades av någon annan – läste in på nytt", "warn");
      await loadSchedule();
    } else {
      showToast("Kunde inte spara: " + err.message, "error");
      renderHourCell(td);
      focusMatchingSegment(td, minuteStart, minuteEnd);
    }
  }
}

function focusMatchingSegment(td, minuteStart, minuteEnd) {
  if (!td) return;
  if (minuteStart === 0 && minuteEnd === 60 && td.dataset.split !== "1") {
    focusSegment(td, td, 0, 60);
    return;
  }
  const part = td.querySelector(
    `.hour-segment[data-minute-start="${minuteStart}"][data-minute-end="${minuteEnd}"]`
  );
  if (part) focusSegment(td, part, minuteStart, minuteEnd);
}

async function splitHourCell(td) {
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  const currentSegments = sortSegments(segmentsForHour(personId, hour));
  if (isSplitHour(currentSegments)) {
    showToast("Cellen är redan delad i två halvtimmar.", "warn");
    return;
  }

  try {
    const resp = await api.put("/api/schedule/cell/split", {
      year: state.year,
      week: state.week,
      weekday: state.weekday,
      hour,
      person_id: personId,
      segments: currentSegments.map((segment) => ({
        minute_start: segment.minute_start,
        minute_end: segment.minute_end,
        expected_version: segment.version,
      })),
    });
    replaceHourSegments(personId, hour, resp.segments || []);
    renderHourCell(td);
    focusMatchingSegment(td, 0, 30);
    refreshSummary();
    showToast("Cellen delades i två halvtimmar.");
  } catch (err) {
    if (err.status === 409) {
      showToast("Cellen ändrades av någon annan – läste in på nytt", "warn");
      await loadSchedule();
    } else {
      showToast("Kunde inte dela cellen: " + err.message, "error");
    }
  }
}

function clipboardLabel(activityId) {
  const a = activityById(activityId);
  return a ? a.label : "(tom)";
}

async function copyFocused(cut = false) {
  if (!state.focusedCell) return;
  const activityId = effectiveActivityIdForFocus();
  state.clipboard = { activity_id: activityId };
  state.focusedCell.focusEl.classList.add("clipboard-flash");
  setTimeout(() => state.focusedCell?.focusEl?.classList.remove("clipboard-flash"), 500);

  if (cut && activityId != null) {
    const { td, personId, hour, minuteStart, minuteEnd } = state.focusedCell;
    const segment = currentSegment(personId, hour, minuteStart, minuteEnd);
    try {
      const resp = await api.put("/api/schedule/cell", {
        year: state.year,
        week: state.week,
        weekday: state.weekday,
        hour,
        minute_start: minuteStart,
        minute_end: minuteEnd,
        person_id: personId,
        activity_id: null,
        expected_version: Number(segment.version) || 0,
      });
      const others = segmentsForHour(personId, hour).filter(
        (item) => !(item.minute_start === minuteStart && item.minute_end === minuteEnd)
      );
      replaceHourSegments(personId, hour, [...others, resp.cell]);
      renderHourCell(td);
      focusMatchingSegment(td, minuteStart, minuteEnd);
      refreshSummary();
      showToast(`Klippt: ${clipboardLabel(activityId)}`);
    } catch (e) {
      if (e.status === 409) {
        showToast("Konflikt – läser om", "warn");
        await loadSchedule();
      } else {
        showToast("Kunde inte klippa: " + e.message, "error");
      }
    }
  } else {
    showToast(`Kopierat: ${clipboardLabel(activityId)}`);
  }
}

async function pasteFocused() {
  if (!state.focusedCell || state.clipboard == null) return;
  const { td, personId, hour, minuteStart, minuteEnd } = state.focusedCell;
  const segment = currentSegment(personId, hour, minuteStart, minuteEnd);
  try {
    const resp = await api.put("/api/schedule/cell", {
      year: state.year,
      week: state.week,
      weekday: state.weekday,
      hour,
      minute_start: minuteStart,
      minute_end: minuteEnd,
      person_id: personId,
      activity_id: state.clipboard.activity_id,
      expected_version: Number(segment.version) || 0,
    });
    const others = segmentsForHour(personId, hour).filter(
      (item) => !(item.minute_start === minuteStart && item.minute_end === minuteEnd)
    );
    replaceHourSegments(personId, hour, [...others, resp.cell]);
    renderHourCell(td);
    focusMatchingSegment(td, minuteStart, minuteEnd);
    refreshSummary();
    showToast(`Klistrade in: ${clipboardLabel(state.clipboard.activity_id)}`);
  } catch (e) {
    if (e.status === 409) {
      showToast("Konflikt – läser om", "warn");
      await loadSchedule();
    } else {
      showToast("Kunde inte klistra in: " + e.message, "error");
    }
  }
}

function handleSelectClipboardKeys(e) {
  if (!(e.ctrlKey || e.metaKey)) return;
  const key = e.key.toLowerCase();
  if (!["c", "x", "v"].includes(key)) return;
  e.preventDefault();
  e.stopPropagation();
  if (!state.focusedCell) return;
  if (key === "c") copyFocused(false);
  else if (key === "x") copyFocused(true);
  else if (key === "v") pasteFocused();
}

function setupKeyboard() {
  const handler = (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    const key = e.key.toLowerCase();
    if (!["c", "x", "v"].includes(key)) return;

    const active = document.activeElement;
    if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) return;
    if (!state.focusedCell) {
      showToast(`Ctrl+${key.toUpperCase()}: klicka först på en cell`, "warn");
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    if (key === "c") copyFocused(false);
    else if (key === "x") copyFocused(true);
    else if (key === "v") pasteFocused();
  };
  window.addEventListener("keydown", handler, true);
  document.addEventListener("keydown", handler, true);
}

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
    if (td.dataset.split === "1") return;
    if (r >= r0 && r <= r1 && c >= c0 && c <= c1) td.classList.add("drag-target");
  });
}

function resetDragState() {
  document.body.classList.remove("dragging");
  drag.sourceTd?.classList.remove("drag-source-cell");
  document.querySelectorAll("#scheduleBody td.drag-target").forEach((t) => t.classList.remove("drag-target"));
  drag.active = false;
  drag.pending = false;
  drag.sourceTd = null;
  drag.sourceActivityId = null;
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
  drag.sourceActivityId = effectiveActivityIdForTd(td);
  drag.sourceRow = Number(td.dataset.rowIndex);
  drag.sourceCol = Number(td.dataset.colIndex);
  drag.currentRow = drag.sourceRow;
  drag.currentCol = drag.sourceCol;
  drag.startX = event.clientX;
  drag.startY = event.clientY;
}

function activateDrag() {
  if (!drag.pending || drag.active || !drag.sourceTd) return;
  drag.pending = false;
  drag.active = true;
  document.body.classList.add("dragging");
  drag.sourceTd.classList.add("drag-source-cell");
  if (document.activeElement?.tagName === "SELECT") {
    document.activeElement.blur();
  }
  updateDragTargets();
}

function scheduleCellFromPoint(clientX, clientY) {
  const el = document.elementFromPoint(clientX, clientY);
  return el?.closest("#scheduleBody td[data-hour]") || null;
}

async function finishDrag() {
  if (!drag.active) return;
  const sourceTd = drag.sourceTd;
  const sourceActivityId = drag.sourceActivityId;
  const targets = Array.from(document.querySelectorAll("#scheduleBody td.drag-target"));
  resetDragState();

  if (targets.length === 0 || (targets.length === 1 && targets[0] === sourceTd)) return;
  if (targets.length > 200) {
    showToast("För många celler (max 200)", "error");
    return;
  }

  const cells = targets
    .filter((td) => td !== sourceTd)
    .map((td) => {
      const personId = Number(td.dataset.personId);
      const hour = Number(td.dataset.hour);
      const segment = currentSegment(personId, hour, 0, 60);
      return {
        year: state.year,
        week: state.week,
        weekday: state.weekday,
        hour,
        minute_start: 0,
        minute_end: 60,
        person_id: personId,
        activity_id: sourceActivityId,
        expected_version: Number(segment.version) || 0,
      };
    });

  if (cells.length === 0) return;

  try {
    const resp = await api.post("/api/schedule/cells", { cells, atomic: true, action: "drag_fill" });
    resp.applied.forEach((segment) => {
      replaceHourSegments(segment.person_id, segment.hour, [segment]);
      const td = document.querySelector(
        `#scheduleBody td[data-person-id="${segment.person_id}"][data-hour="${segment.hour}"]`
      );
      if (td) renderHourCell(td);
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
    if (e.button !== 0) return;
    if (e.target.closest("select")) return;
    const td = e.target.closest("td[data-hour]");
    if (!td || td.dataset.split === "1") return;
    startPendingDrag(td, e);
  });

  body.addEventListener("contextmenu", (e) => {
    const td = e.target.closest("td[data-hour]");
    if (!td) return;
    if (td.dataset.split === "1") {
      const part = e.target.closest(".hour-segment") || td.querySelector(".hour-segment");
      if (part) {
        handleSplitSegmentContextMenu(
          e,
          td,
          part,
          Number(part.dataset.minuteStart),
          Number(part.dataset.minuteEnd),
        );
      }
      return;
    }
    handleFullHourContextMenu(e, td);
  }, true);

  document.addEventListener("mousemove", (e) => {
    if (!drag.pending && !drag.active) return;
    const moved = Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY);
    if (!drag.active) {
      if (moved < 5) return;
      activateDrag();
    }
    const td = scheduleCellFromPoint(e.clientX, e.clientY);
    if (!td || td.dataset.split === "1") return;
    drag.currentRow = Number(td.dataset.rowIndex);
    drag.currentCol = Number(td.dataset.colIndex);
    updateDragTargets();
  });

  document.addEventListener("mouseup", () => {
    if (drag.active) {
      drag.suppressClick = true;
      void finishDrag();
      setTimeout(() => { drag.suppressClick = false; }, 0);
      return;
    }
    if (drag.pending) resetDragState();
  });

  document.addEventListener("click", (e) => {
    if (!drag.suppressClick) return;
    if (!e.target.closest("#scheduleBody td[data-hour]")) return;
    e.preventDefault();
    e.stopPropagation();
    drag.suppressClick = false;
  }, true);

  body.addEventListener("click", (e) => {
    if (drag.suppressClick) return;
    const td = e.target.closest("td[data-hour]");
    if (!td) return;
    if (td.dataset.split === "1") {
      const part = e.target.closest(".hour-segment");
      if (part) {
        focusSegment(td, part, Number(part.dataset.minuteStart), Number(part.dataset.minuteEnd));
      }
      return;
    }
    focusSegment(td, td, 0, 60);
  });

  body.addEventListener("change", (e) => {
    const td = e.target.closest("td[data-hour]");
    if (!td) return;
    if (td.dataset.split === "1") {
      const part = e.target.closest(".hour-segment");
      if (part) {
        focusSegment(td, part, Number(part.dataset.minuteStart), Number(part.dataset.minuteEnd));
      }
      return;
    }
    focusSegment(td, td, 0, 60);
  });
}

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
      <td>${formatHours(r.hours)}</td>
      <td>${Number(r.persons_equiv).toFixed(1)}</td>`;
    tbody.appendChild(tr);
  });
}

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
  state.allPersons = data.persons;
  refreshPersons();
  setAllSegments(data.cells || []);
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
        year: state.year,
        week: state.week,
        weekday: state.weekday,
        area_id: state.areaId,
      });
      showToast(`Fyllde ${r.updated} celler`);
      await loadSchedule();
    } catch (e) {
      showToast("Fel: " + e.message, "error");
    }
  });

  document.getElementById("clearBtn").addEventListener("click", async () => {
    if (!confirm("Rensa hela dagen för det valda området?")) return;
    try {
      const r = await api.post("/api/schedule/clear", {
        year: state.year,
        week: state.week,
        weekday: state.weekday,
        area_id: state.areaId,
      });
      showToast(`Rensade ${r.cleared} celler`);
      await loadSchedule();
    } catch (e) {
      showToast("Fel: " + e.message, "error");
    }
  });

  document.getElementById("copyBtn").addEventListener("click", () => openCopyModal());

  document.getElementById("nameFilter").addEventListener("input", (e) => {
    state.nameFilter = e.target.value;
    refreshPersons();
    buildRows();
  });
  document.getElementById("nameFilter").addEventListener("mousedown", (e) => e.stopPropagation());
  document.getElementById("nameFilter").addEventListener("click", (e) => e.stopPropagation());

  document.querySelectorAll("table.matrix th[data-sort]").forEach((th) => {
    th.addEventListener("click", (e) => {
      if (th.dataset.filterTrigger && !e.shiftKey) {
        focusNameFilter();
        return;
      }
      const key = th.dataset.sort;
      if (state.sortKey === key) state.sortAsc = !state.sortAsc;
      else {
        state.sortKey = key;
        state.sortAsc = true;
      }
      refreshPersons();
      buildRows();
    });
  });
})();


function openCopyModal() {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>Kopiera dag</h2>
      <p class="note">Kopierar från en dag till en annan inom området <b>${escapeHtml(state.areas.find(a => a.id === state.areaId)?.name || "Alla")}</b>.</p>
      <label>Från år</label><input id="cp-fy" type="number" value="${state.year}" />
      <label>Från vecka</label><input id="cp-fw" type="number" value="${state.week}" />
      <label>Från dag</label>
      <select id="cp-fd">${[1,2,3,4,5,6,7].map((d) => `<option value="${d}" ${d === state.weekday ? "selected" : ""}>${DAYS[d]}</option>`).join("")}</select>
      <label>Till år</label><input id="cp-ty" type="number" value="${state.year}" />
      <label>Till vecka</label><input id="cp-tw" type="number" value="${state.week}" />
      <label>Till dag</label>
      <select id="cp-td">${[1,2,3,4,5,6,7].map((d) => `<option value="${d}">${DAYS[d]}</option>`).join("")}</select>
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
    } catch (e) {
      showToast("Fel: " + e.message, "error");
    }
  });
}

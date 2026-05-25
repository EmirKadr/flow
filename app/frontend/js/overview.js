// Översikt – vecka eller månad.

const DAY_NAMES = { 1: "Måndag", 2: "Tisdag", 3: "Onsdag", 4: "Torsdag", 5: "Fredag", 6: "Lördag", 7: "Söndag" };
const DAY_SHORT = { 1: "Mån", 2: "Tis", 3: "Ons", 4: "Tor", 5: "Fre", 6: "Lör", 7: "Sön" };

const state = {
  currentUser: null,
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
  undoStack: [],
  redoStack: [],
  selectedDateParts: null,
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

const personOrderDrag = {
  sourceId: null,
  targetId: null,
  position: "after",
};

const loadState = {
  controller: null,
  requestSeq: 0,
};

const overviewAllCache = new Map();
const overviewAllFetchState = {
  controller: null,
  key: "",
};
const OVERVIEW_ALL_CACHE_LIMIT = 4;
const OVERVIEW_REVALIDATE_ACTIVE_MS = 10000;
const OVERVIEW_REVALIDATE_IDLE_MS = 30000;
const OVERVIEW_REVALIDATE_SOON_MS = 1500;
const OVERVIEW_REVALIDATE_ACTIVE_WINDOW_MS = 60000;
const overviewRevalidateState = {
  timer: null,
  controller: null,
  lastActivityAt: Date.now(),
  errorCount: 0,
  toastAt: 0,
};

function overviewIsReadOnly() {
  if (typeof isReadOnlyUser === "function") return isReadOnlyUser(state.currentUser);
  return state.currentUser?.role === "viewer" && !state.currentUser?.is_super_user;
}

function overviewScopeKey() {
  const user = state.currentUser || {};
  return [
    user.id ?? user.username ?? "anonymous",
    user.is_super_user ? "super" : "scoped",
    user.business_id ?? "global",
  ].join(":");
}

function overviewCacheKey() {
  const period = state.view === "week"
    ? `week:${state.year}:${state.week}`
    : `month:${state.year}:${state.month}`;
  return `${overviewScopeKey()}|${period}`;
}

function overviewUrl(areaId = state.areaId) {
  if (state.view === "week") {
    return `/api/overview?year=${state.year}&week=${state.week}` +
      (areaId ? `&area_id=${areaId}` : "");
  }
  return `/api/overview/month?year=${state.year}&month=${state.month}` +
    (areaId ? `&area_id=${areaId}` : "");
}

function overviewRevisionUrl(areaId = null) {
  if (state.view === "week") {
    return `/api/overview/revision?year=${state.year}&week=${state.week}` +
      (areaId ? `&area_id=${areaId}` : "");
  }
  return `/api/overview/revision/month?year=${state.year}&month=${state.month}` +
    (areaId ? `&area_id=${areaId}` : "");
}

function setOverviewAllCache(key, data) {
  overviewAllCache.delete(key);
  overviewAllCache.set(key, data);
  while (overviewAllCache.size > OVERVIEW_ALL_CACHE_LIMIT) {
    overviewAllCache.delete(overviewAllCache.keys().next().value);
  }
}

function invalidateOverviewAllCache() {
  overviewAllCache.clear();
  overviewAllFetchState.controller?.abort();
  overviewRevalidateState.controller?.abort();
  overviewAllFetchState.controller = null;
  overviewAllFetchState.key = "";
  overviewRevalidateState.controller = null;
  scheduleNextOverviewRevalidate(OVERVIEW_REVALIDATE_SOON_MS);
}

function filterOverviewDataForArea(data, areaId) {
  const source = data || {};
  const persons = Array.isArray(source.persons) ? source.persons : [];
  const matrix = Array.isArray(source.matrix) ? source.matrix : [];
  if (areaId == null) {
    return {
      ...source,
      persons: persons.map((person) => ({ ...person })),
      matrix: matrix.map((cell) => ({ ...cell })),
      days: (source.days || []).map((day) => ({ ...day })),
    };
  }
  const selectedAreaId = Number(areaId);
  const visiblePersons = persons.filter((person) => Number(person.home_area_id) === selectedAreaId);
  const personIds = new Set(visiblePersons.map((person) => Number(person.id)));
  return {
    ...source,
    persons: visiblePersons.map((person) => ({ ...person })),
    matrix: matrix.filter((cell) => personIds.has(Number(cell.person_id))).map((cell) => ({ ...cell })),
    days: (source.days || []).map((day) => ({ ...day })),
  };
}

function setupOverviewHorizontalScroll() {
  if (typeof setupSyncedHorizontalScroll === "function") {
    setupSyncedHorizontalScroll(document.getElementById("overviewTable"));
  }
}

function markOverviewActivity() {
  overviewRevalidateState.lastActivityAt = Date.now();
}

function overviewRevalidateDelay() {
  return Date.now() - overviewRevalidateState.lastActivityAt < OVERVIEW_REVALIDATE_ACTIVE_WINDOW_MS
    ? OVERVIEW_REVALIDATE_ACTIVE_MS
    : OVERVIEW_REVALIDATE_IDLE_MS;
}

function overviewIsBusyForBackgroundUpdate() {
  return drag.active
    || drag.pending
    || personOrderDrag.sourceId != null
    || Boolean(document.querySelector("#overviewBody .pending-save"));
}

function scheduleNextOverviewRevalidate(delay = overviewRevalidateDelay()) {
  clearTimeout(overviewRevalidateState.timer);
  overviewRevalidateState.timer = null;
  if (document.hidden) return;
  overviewRevalidateState.timer = setTimeout(() => {
    overviewRevalidateState.timer = null;
    void revalidateOverview();
  }, delay);
}

function notifyOverviewBackgroundUpdate(changedCount) {
  if (!changedCount) return;
  const now = Date.now();
  if (now - overviewRevalidateState.toastAt < 10000) return;
  overviewRevalidateState.toastAt = now;
  showToast("Översikten uppdaterades i bakgrunden.", "info", 2500);
}

function overviewPersonSignature(persons) {
  return JSON.stringify((persons || []).map((person) => [
    Number(person.id),
    person.name || "",
    Number(person.home_area_id) || 0,
    Number(person.home_activity_id) || 0,
    person.has_fixed_schedule !== false,
    Number(person.sort_order) || 0,
  ]));
}

function overviewDaysSignature(days) {
  return JSON.stringify((days || []).map((day) => [day.date || "", Number(day.year), Number(day.week), Number(day.weekday)]));
}

function overviewCellKey(cell) {
  return state.view === "week"
    ? `${Number(cell.person_id)}:${Number(cell.weekday)}`
    : `${Number(cell.person_id)}:${cell.date || ""}`;
}

function overviewCellSignature(cell) {
  return [
    cell.activity_id == null ? "" : Number(cell.activity_id),
    cell.mixed ? 1 : 0,
    Number(cell.hours_total) || 0,
    Number(cell.template_hours) || 0,
  ].join(":");
}

function overviewMatrixMap(cells) {
  const map = new Map();
  (cells || []).forEach((cell) => map.set(overviewCellKey(cell), cell));
  return map;
}

function overviewTdForCell(cell) {
  if (state.view === "week") {
    return document.querySelector(
      `#overviewBody td.day[data-person-id="${Number(cell.person_id)}"][data-weekday="${Number(cell.weekday)}"]`
    );
  }
  return document.querySelector(
    `#overviewBody td.day[data-person-id="${Number(cell.person_id)}"][data-date="${cell.date || ""}"]`
  );
}

function overviewCellIsFocused(td) {
  return td && state.focusedCell?.td === td && document.activeElement?.closest("#overviewBody");
}

function patchOverviewFromAllData(allData) {
  const data = filterOverviewDataForArea(allData, state.areaId);
  const personsChanged = overviewPersonSignature(state.allPersons) !== overviewPersonSignature(data.persons || []);
  const daysChanged = overviewDaysSignature(state.days) !== overviewDaysSignature(data.days || []);
  if (personsChanged || daysChanged) {
    applyOverviewData(data);
    return { changed: true, patched: false };
  }

  state.allPersons = (data.persons || []).map((person) => ({ ...person }));
  const currentMap = overviewMatrixMap(state.cells);
  const nextMap = overviewMatrixMap(data.matrix || []);
  let changedCount = 0;
  let skippedFocused = false;

  nextMap.forEach((cell, key) => {
    const current = currentMap.get(key);
    if (current && overviewCellSignature(current) === overviewCellSignature(cell)) return;
    const td = overviewTdForCell(cell);
    if (!td) return;
    if (overviewCellIsFocused(td)) {
      skippedFocused = true;
      return;
    }
    renderDayCell(td, cell);
    changedCount += 1;
  });

  state.cells = state.cells.filter((cell) => {
    const keep = nextMap.has(overviewCellKey(cell));
    if (!keep) changedCount += 1;
    return keep;
  });

  if (skippedFocused) scheduleNextOverviewRevalidate(OVERVIEW_REVALIDATE_SOON_MS);
  return { changed: changedCount > 0 || skippedFocused, patched: changedCount > 0, skippedFocused };
}

function showReadOnlyToast() {
  showToast("Visningsläge: du kan se översikten men inte ändra den.", "warn");
}

function applyOverviewReadOnlyMode() {
  const readOnly = overviewIsReadOnly();
  document.body.classList.toggle("read-only-mode", readOnly);
  const note = document.querySelector("main .note");
  if (note && readOnly) {
    note.textContent = "Visningsläge: du kan se bemanningen och översikten, men inte ändra.";
  }
  updateUndoRedoButtons();
}

function preferredAreaIdForCurrentUser() {
  return typeof preferredAreaIdFromFocus === "function" ? preferredAreaIdFromFocus(state.areas) : null;
}


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

function todayYmd() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function todayWeekdayIndex() {
  return new Date().getDay() || 7;
}

function datePartsFromDate(date) {
  return [date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate()];
}

function dateFromParts(parts) {
  if (!Array.isArray(parts) || parts.length !== 3) return null;
  const [year, month, day] = parts.map(Number);
  if (!year || !month || !day) return null;
  return new Date(Date.UTC(year, month - 1, day));
}

function storedDateForCurrentPeriod() {
  const storedDate = dateFromParts(state.selectedDateParts);
  if (!storedDate) return null;
  if (state.view === "month") {
    return storedDate.getUTCFullYear() === state.year && storedDate.getUTCMonth() + 1 === state.month
      ? storedDate
      : null;
  }
  const storedWeek = isoWeek(storedDate);
  return storedWeek.year === state.year && storedWeek.week === state.week ? storedDate : null;
}

function writeOverviewSelectedDate(date) {
  state.selectedDateParts = datePartsFromDate(date);
  writeSelectedDate(state.selectedDateParts[0], state.selectedDateParts[1], state.selectedDateParts[2]);
}

function persistOverviewState() {
  let date = storedDateForCurrentPeriod();
  if (date) {
    writeOverviewSelectedDate(date);
    return;
  }
  if (state.view === "month") {
    const now = new Date();
    const isCurrentMonth = state.year === now.getFullYear() && state.month === now.getMonth() + 1;
    date = isCurrentMonth ? now : new Date(Date.UTC(state.year, state.month - 1, 1));
  } else {
    const monday = isoWeekToMonday(state.year, state.week);
    date = monday;
  }
  writeOverviewSelectedDate(date);
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

  const sortedActivities = typeof compareActivitiesForAreaFocus === "function"
    ? [...state.activitiesActive].sort((a, b) =>
      compareActivitiesForAreaFocus(a, b, state.areas, state.currentUser?.area_id)
    )
    : state.activitiesActive;
  sortedActivities.forEach(appendOption);
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
    if (typeof comparePersonsForAreaFocus === "function") {
      const areaCompare = comparePersonsForAreaFocus(a, b, state.areas);
      if (areaCompare !== 0) return areaCompare;
    }
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

function canUsePersonSortOrder() {
  const user = state.currentUser || {};
  const roles = typeof userRoles === "function" ? userRoles(user) : [user.role];
  const hasAllowedRole = Boolean(user.is_super_user) || roles.includes("admin") || roles.includes("staffing_manager");
  const hasArea = user.area_id != null && Number.isFinite(Number(user.area_id));
  return hasAllowedRole && hasArea && typeof canEditPage === "function" && canEditPage(user, "personSortOrder");
}

function canReorderPerson(person) {
  return canUsePersonSortOrder()
    && Number(person?.home_area_id) === Number(state.currentUser?.area_id);
}

function setupPersonOrderNameCell(cell, person) {
  cell.dataset.personId = person.id;
  if (canReorderPerson(person)) {
    cell.draggable = true;
    cell.classList.add("person-order-draggable");
    cell.title = "Dra namnet för att ändra sorteringen.";
  } else if (canUsePersonSortOrder()) {
    cell.classList.add("person-order-locked");
    cell.title = "Du kan bara sortera personer med samma hemområde som ditt användarområde.";
  }
}

function clearPersonOrderDropMarkers() {
  document
    .querySelectorAll("#overviewBody tr.person-order-drop-before, #overviewBody tr.person-order-drop-after")
    .forEach((row) => row.classList.remove("person-order-drop-before", "person-order-drop-after"));
}

function resetPersonOrderDrag() {
  document.body.classList.remove("dragging-person-order");
  document
    .querySelectorAll("#overviewBody tr.person-order-dragging")
    .forEach((row) => row.classList.remove("person-order-dragging"));
  clearPersonOrderDropMarkers();
  personOrderDrag.sourceId = null;
  personOrderDrag.targetId = null;
  personOrderDrag.position = "after";
}

function updatePersonOrderDropTarget(cell, event) {
  const targetId = Number(cell.dataset.personId);
  if (!Number.isInteger(targetId) || targetId === Number(personOrderDrag.sourceId)) return;
  const rect = cell.getBoundingClientRect();
  const position = event.clientY < rect.top + rect.height / 2 ? "before" : "after";
  clearPersonOrderDropMarkers();
  cell.parentElement.classList.add(position === "before" ? "person-order-drop-before" : "person-order-drop-after");
  personOrderDrag.targetId = targetId;
  personOrderDrag.position = position;
}

function currentAreaPersonIdsForReorder() {
  const areaId = Number(state.currentUser?.area_id);
  return state.persons
    .filter((person) => Number(person.home_area_id) === areaId && person.is_active !== false)
    .map((person) => Number(person.id));
}

function movedPersonOrderIds(sourceId, targetId, position, ids) {
  if (sourceId === targetId) return ids;
  const withoutSource = ids.filter((id) => id !== sourceId);
  let index = withoutSource.indexOf(targetId);
  if (index < 0) return ids;
  if (position === "after") index += 1;
  withoutSource.splice(index, 0, sourceId);
  return withoutSource;
}

function applyPersonOrderResponse(updatedPersons) {
  const byId = new Map((updatedPersons || []).map((person) => [Number(person.id), person]));
  if (!byId.size) return;
  state.allPersons = state.allPersons.map((person) => (
    byId.has(Number(person.id)) ? { ...person, ...byId.get(Number(person.id)) } : person
  ));
  state.sortKey = "sort_order";
  state.sortAsc = true;
  refreshPersons();
  if (state.view === "week") buildWeekBody();
  else buildMonthBody();
  setupOverviewHorizontalScroll();
}

async function savePersonOrder(sourceId, targetId, position) {
  if (!canUsePersonSortOrder()) {
    showToast("Du saknar behörighet att sortera personer.", "error", 5000);
    return;
  }
  if (state.nameFilter.trim()) {
    showToast("Rensa personfiltret innan du sorterar personer.", "warn", 5000);
    return;
  }
  const ids = currentAreaPersonIdsForReorder();
  if (!ids.includes(sourceId) || !ids.includes(targetId)) {
    showToast("Du kan bara sortera personer med samma hemområde som ditt användarområde.", "warn", 5000);
    return;
  }
  const personIds = movedPersonOrderIds(sourceId, targetId, position, ids);
  if (personIds.join(",") === ids.join(",")) return;
  markOverviewActivity();
  try {
    const updatedPersons = await api.put("/api/persons/sort-order", { person_ids: personIds });
    invalidateOverviewAllCache();
    applyPersonOrderResponse(updatedPersons);
    showToast("Personsorteringen sparades.", "success", 2500);
  } catch (error) {
    showToast(error.message || "Kunde inte spara personsorteringen.", "error", 7000);
    if (error.status === 409) await load();
  }
}

function setupPersonOrderDrag() {
  const body = document.getElementById("overviewBody");
  body.addEventListener("dragstart", (event) => {
    const cell = event.target.closest("td.name[data-person-id]");
    if (!cell) return;
    const person = personById(Number(cell.dataset.personId));
    if (!canReorderPerson(person) || state.nameFilter.trim()) {
      event.preventDefault();
      if (state.nameFilter.trim()) showToast("Rensa personfiltret innan du sorterar personer.", "warn", 4000);
      return;
    }
    personOrderDrag.sourceId = Number(cell.dataset.personId);
    document.body.classList.add("dragging-person-order");
    cell.parentElement.classList.add("person-order-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(personOrderDrag.sourceId));
  });

  body.addEventListener("dragover", (event) => {
    if (personOrderDrag.sourceId == null) return;
    const cell = event.target.closest("td.name[data-person-id]");
    if (!cell) return;
    const person = personById(Number(cell.dataset.personId));
    if (!canReorderPerson(person)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    updatePersonOrderDropTarget(cell, event);
  });

  body.addEventListener("drop", (event) => {
    if (personOrderDrag.sourceId == null) return;
    const cell = event.target.closest("td.name[data-person-id]");
    if (!cell) return;
    event.preventDefault();
    const sourceId = Number(personOrderDrag.sourceId);
    const targetId = Number(personOrderDrag.targetId || cell.dataset.personId);
    const position = personOrderDrag.position;
    resetPersonOrderDrag();
    void savePersonOrder(sourceId, targetId, position);
  });

  body.addEventListener("dragend", resetPersonOrderDrag);
  body.addEventListener("dragleave", (event) => {
    if (!body.contains(event.relatedTarget)) clearPersonOrderDropMarkers();
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

function dayRequestKey(personId, year, week, weekday) {
  return `${personId}:${year}:${week}:${weekday}`;
}

function normalizeOverviewCell(cell, td = null) {
  const normalized = {
    person_id: Number(cell?.person_id ?? td?.dataset.personId ?? 0),
    activity_id: cell?.activity_id == null ? null : Number(cell.activity_id),
    mixed: !!cell?.mixed,
    hours_total: Number(cell?.hours_total) || 0,
    template_hours: Number(cell?.template_hours ?? td?.dataset.templateHours ?? 0) || 0,
  };
  if (cell?.date != null || td?.dataset.date) normalized.date = cell?.date ?? td.dataset.date;
  else normalized.weekday = Number(cell?.weekday ?? td?.dataset.weekday ?? 0);
  if (cell?.year != null || td?.dataset.year) normalized.year = Number(cell?.year ?? td?.dataset.year ?? 0);
  if (cell?.week != null || td?.dataset.week) normalized.week = Number(cell?.week ?? td?.dataset.week ?? 0);
  return normalized;
}

function cellRecordIndexForTd(td) {
  if (state.view === "week") {
    const personId = Number(td.dataset.personId);
    const weekday = Number(td.dataset.weekday);
    return state.cells.findIndex((cell) => Number(cell.person_id) === personId && Number(cell.weekday) === weekday);
  }
  const personId = Number(td.dataset.personId);
  const date = td.dataset.date || "";
  return state.cells.findIndex((cell) => Number(cell.person_id) === personId && cell.date === date);
}

function cellRecordForTd(td) {
  const idx = cellRecordIndexForTd(td);
  if (idx >= 0) return normalizeOverviewCell(state.cells[idx], td);
  return normalizeOverviewCell({}, td);
}

function upsertCellRecordForTd(td, cell) {
  const normalized = normalizeOverviewCell(cell, td);
  const idx = cellRecordIndexForTd(td);
  if (idx >= 0) state.cells[idx] = { ...state.cells[idx], ...normalized };
  else state.cells.push(normalized);
  return normalized;
}

function markDayPending(td, pending) {
  td.classList.toggle("pending-save", pending);
  const sel = td.querySelector("select");
  if (sel) sel.disabled = pending || overviewIsReadOnly();
}

function renderDayCell(td, cell) {
  const normalized = upsertCellRecordForTd(td, cell);
  td.dataset.activityId = normalized.activity_id == null ? "" : String(normalized.activity_id);
  td.dataset.templateHours = String(normalized.template_hours);
  styleCell(td, normalized);
  const sel = td.querySelector("select");
  if (sel) sel.disabled = td.classList.contains("pending-save") || overviewIsReadOnly();
  return normalized;
}

function buildOptimisticDayCell(td, activityId) {
  const current = cellRecordForTd(td);
  return normalizeOverviewCell(
    {
      person_id: current.person_id,
      weekday: current.weekday,
      date: current.date,
      year: Number(td.dataset.year),
      week: Number(td.dataset.week),
      activity_id: activityId,
      mixed: false,
      hours_total: activityId == null ? 0 : current.template_hours,
      template_hours: current.template_hours,
    },
    td,
  );
}

function findDayTd(personId, year, week, weekday) {
  return document.querySelector(
    `#overviewBody td.day[data-person-id="${personId}"][data-year="${year}"][data-week="${week}"][data-weekday="${weekday}"]`
  );
}


// ---- Cell rendering ----
function styleCell(td, cell) {
  td.innerHTML = "";
  td.classList.remove("mixed", "is-off", "scheduled-empty");
  td.style.background = "#fff";
  const person = personById(Number(td.dataset.personId));
  const baseActivityId = cell.template_hours > 0 ? (person?.home_activity_id || null) : null;

  const hasFixedSchedule = person?.has_fixed_schedule !== false;
  const isOff = hasFixedSchedule && cell.template_hours === 0;
  if (isOff) {
    td.classList.add("is-off");
    td.textContent = "Ledig";
    return;
  }
  if (!hasFixedSchedule && cell.template_hours === 0 && !cell.activity_id) {
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
    // Left-click never opens the dropdown — only focuses the cell.
    if (e.button === 0) {
      e.preventDefault();
      focusDayCell(td);
    }
  });
  td.addEventListener("contextmenu", (e) => {
    if (sel.disabled) return;
    e.preventDefault();
    focusDayCell(td);
    try {
      sel.showPicker();
    } catch (err) {
      sel.focus();
    }
  });
  td.appendChild(sel);

  const info = document.createElement("div");
  info.className = "hour-info";
  if (cell.mixed) info.textContent = `Blandat (${cell.hours_total}h)`;
  else if (cell.activity_id) info.textContent = `${cell.hours_total}/${cell.template_hours}h`;
  else info.textContent = `Schemalagd (${cell.template_hours}h)`;
  td.appendChild(info);
  if (td.classList.contains("pending-save")) {
    sel.disabled = true;
  }
  if (overviewIsReadOnly()) {
    sel.disabled = true;
  }

}


// ---- VECKO-VY ----
function renderOverviewDayHeader(th, dayLabel, week) {
  th.replaceChildren();
  const dateLabel = document.createElement("span");
  dateLabel.className = "overview-day-date";
  dateLabel.textContent = dayLabel;

  const weekLabel = document.createElement("span");
  weekLabel.className = "overview-week-label";
  weekLabel.textContent = `Vecka ${week}`;

  th.append(dateLabel, weekLabel);
}

function buildWeekHeader() {
  const header = document.getElementById("headerRow");
  while (header.children.length > 1) header.removeChild(header.lastChild);
  const monday = isoWeekToMonday(state.year, state.week);
  const today = todayYmd();
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday);
    d.setUTCDate(monday.getUTCDate() + i);
    const th = document.createElement("th");
    renderOverviewDayHeader(th, `${DAY_SHORT[i + 1]} ${d.getUTCDate()}/${d.getUTCMonth() + 1}`, state.week);
    const ymd = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
    if (ymd === today) th.classList.add("today-col");
    header.appendChild(th);
  }
}

function buildWeekBody() {
  const body = document.getElementById("overviewBody");
  const fragment = document.createDocumentFragment();
  const lookup = new Map();
  state.cells.forEach((m) => lookup.set(`${m.person_id}:${m.weekday}`, m));

  state.persons.forEach((p) => {
    const tr = document.createElement("tr");
    tr.dataset.personId = p.id;
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    nameTd.textContent = p.name;
    setupPersonOrderNameCell(nameTd, p);
    tr.appendChild(nameTd);

    const today = todayYmd();
    const monday = isoWeekToMonday(state.year, state.week);
    for (let wd = 1; wd <= 7; wd++) {
      const cell = lookup.get(`${p.id}:${wd}`) || { activity_id: null, mixed: false, hours_total: 0, template_hours: 0 };
      const td = document.createElement("td");
      td.className = "day";
      td.dataset.personId = p.id;
      td.dataset.weekday = wd;
      td.dataset.year = state.year;
      td.dataset.week = state.week;
      td.tabIndex = -1;
      const dayDate = new Date(monday);
      dayDate.setUTCDate(monday.getUTCDate() + (wd - 1));
      const ymd = `${dayDate.getUTCFullYear()}-${String(dayDate.getUTCMonth() + 1).padStart(2, "0")}-${String(dayDate.getUTCDate()).padStart(2, "0")}`;
      if (ymd === today) td.classList.add("today-col");
      renderDayCell(td, cell);
      tr.appendChild(td);
    }
    fragment.appendChild(tr);
  });

  body.replaceChildren(fragment);
}


// ---- MÅNADS-VY ----
function buildMonthHeader() {
  const header = document.getElementById("headerRow");
  while (header.children.length > 1) header.removeChild(header.lastChild);
  const today = todayYmd();
  state.days.forEach((d) => {
    const date = new Date(d.date);
    const th = document.createElement("th");
    renderOverviewDayHeader(th, `${DAY_SHORT[d.weekday]} ${date.getUTCDate()}/${date.getUTCMonth() + 1}`, d.week);
    if (d.weekday >= 6) th.style.opacity = "0.7";
    if (d.date === today) th.classList.add("today-col");
    header.appendChild(th);
  });
}

function buildMonthBody() {
  const body = document.getElementById("overviewBody");
  const fragment = document.createDocumentFragment();
  const lookup = new Map();
  state.cells.forEach((m) => lookup.set(`${m.person_id}:${m.date}`, m));

  state.persons.forEach((p) => {
    const tr = document.createElement("tr");
    tr.dataset.personId = p.id;
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    nameTd.textContent = p.name;
    setupPersonOrderNameCell(nameTd, p);
    tr.appendChild(nameTd);

    const today = todayYmd();
    state.days.forEach((dInfo) => {
      const cell = lookup.get(`${p.id}:${dInfo.date}`) || { activity_id: null, mixed: false, hours_total: 0, template_hours: 0 };
      const td = document.createElement("td");
      td.className = "day";
      td.dataset.personId = p.id;
      td.dataset.weekday = dInfo.weekday;
      td.dataset.year = dInfo.year;
      td.dataset.week = dInfo.week;
      td.dataset.date = dInfo.date;
      td.tabIndex = -1;
      if (dInfo.date === today) td.classList.add("today-col");
      renderDayCell(td, cell);
      tr.appendChild(td);
    });
    fragment.appendChild(tr);
  });

  body.replaceChildren(fragment);
}


// ---- Cell update ----
async function postDay(personId, year, week, weekday, activityId) {
  return api.post("/api/overview/day", {
    person_id: personId,
    year, week, weekday,
    activity_id: activityId,
  });
}

async function postBulkDays(days, atomic = false) {
  return api.post("/api/overview/days/bulk", { days, atomic });
}

function cloneOverviewSegment(segment) {
  return {
    minute_start: Number(segment.minute_start),
    minute_end: Number(segment.minute_end),
    activity_id: segment.activity_id == null ? null : Number(segment.activity_id),
    empty_override: !!segment.empty_override,
    version: Number(segment.version) || 0,
  };
}

function cloneOverviewHourSnapshot(snapshot) {
  return {
    person_id: Number(snapshot.person_id),
    year: Number(snapshot.year),
    week: Number(snapshot.week),
    weekday: Number(snapshot.weekday),
    hour: Number(snapshot.hour),
    segments: (snapshot.segments || [])
      .map((segment) => cloneOverviewSegment(segment))
      .sort((a, b) => a.minute_start - b.minute_start || a.minute_end - b.minute_end),
  };
}

function cloneOverviewHourSnapshots(snapshots) {
  return (snapshots || []).map((snapshot) => cloneOverviewHourSnapshot(snapshot));
}

function overviewSnapshotSignature(snapshots) {
  return JSON.stringify(cloneOverviewHourSnapshots(snapshots).map((snapshot) => ({
    hour: snapshot.hour,
    segments: snapshot.segments.map((segment) => ({
      minute_start: segment.minute_start,
      minute_end: segment.minute_end,
      activity_id: segment.activity_id,
      empty_override: segment.empty_override,
    })),
  })));
}

function overviewSegmentVersionRefs(segments) {
  return (segments || []).map((segment) => ({
    minute_start: segment.minute_start,
    minute_end: segment.minute_end,
    expected_version: segment.version,
  }));
}

function overviewRestoreSegments(segments) {
  return (segments || []).map((segment) => ({
    minute_start: segment.minute_start,
    minute_end: segment.minute_end,
    activity_id: segment.activity_id,
    empty_override: segment.empty_override,
  }));
}

function updateUndoRedoButtons() {
  const u = document.getElementById("undoBtn");
  const r = document.getElementById("redoBtn");
  const readOnly = overviewIsReadOnly();
  if (u) u.disabled = readOnly || state.undoStack.length === 0;
  if (r) r.disabled = readOnly || state.redoStack.length === 0;
}

function pushOverviewUndo(label, days) {
  const filtered = days
    .map((day) => ({
      person_id: Number(day.person_id),
      year: Number(day.year),
      week: Number(day.week),
      weekday: Number(day.weekday),
      before_hours: cloneOverviewHourSnapshots(day.before_hours),
      after_hours: cloneOverviewHourSnapshots(day.after_hours),
    }))
    .filter((day) => overviewSnapshotSignature(day.before_hours) !== overviewSnapshotSignature(day.after_hours));
  if (!filtered.length) return;
  state.undoStack.push({ label, days: filtered });
  if (state.undoStack.length > 50) state.undoStack.shift();
  state.redoStack = [];
  updateUndoRedoButtons();
}

async function applyOverviewHistory(action, direction) {
  if (overviewIsReadOnly()) {
    showReadOnlyToast();
    return false;
  }
  const targetKey = direction === "undo" ? "before_hours" : "after_hours";
  const expectedKey = direction === "undo" ? "after_hours" : "before_hours";
  const hours = [];
  action.days.forEach((day) => {
    const expectedByHour = new Map((day[expectedKey] || []).map((snapshot) => [snapshot.hour, snapshot]));
    (day[targetKey] || []).forEach((snapshot) => {
      const expected = expectedByHour.get(snapshot.hour);
      hours.push({
        year: snapshot.year,
        week: snapshot.week,
        weekday: snapshot.weekday,
        hour: snapshot.hour,
        person_id: snapshot.person_id,
        expected_segments: overviewSegmentVersionRefs(expected?.segments || []),
        segments: overviewRestoreSegments(snapshot.segments),
      });
    });
  });

  if (!hours.length) return true;
  try {
    await api.put("/api/schedule/hours/restore", { action: "overview_undo_restore", hours });
    invalidateOverviewAllCache();
    await load();
    return true;
  } catch (e) {
    const detail = e.body?.detail || e.message;
    showToast(`Kunde inte ${direction === "undo" ? "ångra" : "göra om"}: ` + detail, "error");
    return false;
  }
}

async function undoLastOverviewAction() {
  if (overviewIsReadOnly()) {
    showReadOnlyToast();
    return;
  }
  const action = state.undoStack[state.undoStack.length - 1];
  if (!action) { showToast("Inget att ångra.", "warn"); return; }
  const ok = await applyOverviewHistory(action, "undo");
  if (ok) {
    state.undoStack.pop();
    state.redoStack.push(action);
    if (state.redoStack.length > 50) state.redoStack.shift();
    showToast(`Ångrade: ${action.label}`);
  }
  updateUndoRedoButtons();
}

async function redoLastOverviewAction() {
  if (overviewIsReadOnly()) {
    showReadOnlyToast();
    return;
  }
  const action = state.redoStack[state.redoStack.length - 1];
  if (!action) { showToast("Inget att göra om.", "warn"); return; }
  const ok = await applyOverviewHistory(action, "redo");
  if (ok) {
    state.redoStack.pop();
    state.undoStack.push(action);
    if (state.undoStack.length > 50) state.undoStack.shift();
    showToast(`Gjorde om: ${action.label}`);
  }
  updateUndoRedoButtons();
}

async function onDayChange(td, sel, cell) {
  if (overviewIsReadOnly()) {
    showReadOnlyToast();
    renderDayCell(td, cellRecordForTd(td));
    return;
  }
  const newActivityId = sel.value ? Number(sel.value) : null;
  const previousCell = cellRecordForTd(td);
  if (previousCell.mixed && !confirm("Denna dag har flera olika aktiviteter. Skriv över med samma värde?")) {
    sel.value = previousCell.activity_id ? String(previousCell.activity_id) : "";
    return;
  }

  markDayPending(td, true);
  renderDayCell(td, buildOptimisticDayCell(td, newActivityId));
  try {
    const resp = await postDay(
      Number(td.dataset.personId),
      Number(td.dataset.year),
      Number(td.dataset.week),
      Number(td.dataset.weekday),
      newActivityId,
    );
    invalidateOverviewAllCache();
    markDayPending(td, false);
    renderDayCell(td, resp.cell);
    pushOverviewUndo("celländring", [{
      person_id: Number(td.dataset.personId),
      year: Number(td.dataset.year),
      week: Number(td.dataset.week),
      weekday: Number(td.dataset.weekday),
      before_hours: resp.before_hours || [],
      after_hours: resp.after_hours || [],
    }]);
    showToast(`Bemannade ${resp.written} h, tog bort ${resp.deleted} h`);
  } catch (e) {
    const detail = e.body?.detail || e.message;
    markDayPending(td, false);
    renderDayCell(td, previousCell);
    showToast("Kunde inte spara: " + detail, "error");
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
  if (overviewIsReadOnly()) return;
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
    if (overviewIsReadOnly()) return;
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
    if (overviewIsReadOnly()) {
      if (drag.pending || drag.active) resetDragState();
      return;
    }
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

    const days = targets.map((td) => ({
      person_id: Number(td.dataset.personId),
      year: Number(td.dataset.year),
      week: Number(td.dataset.week),
      weekday: Number(td.dataset.weekday),
      activity_id: sourceActivityId,
    }));
    const snapshots = new Map();
    targets.forEach((td) => {
      const key = dayRequestKey(
        Number(td.dataset.personId),
        Number(td.dataset.year),
        Number(td.dataset.week),
        Number(td.dataset.weekday),
      );
      snapshots.set(key, cellRecordForTd(td));
      markDayPending(td, true);
      renderDayCell(td, buildOptimisticDayCell(td, sourceActivityId));
    });

    try {
      const resp = await postBulkDays(days, false);
      invalidateOverviewAllCache();
      const handled = new Set();

      (resp.applied || []).forEach((result) => {
        const key = dayRequestKey(result.person_id, result.year, result.week, result.weekday);
        handled.add(key);
        const targetTd = findDayTd(result.person_id, result.year, result.week, result.weekday);
        if (!targetTd) return;
        markDayPending(targetTd, false);
        renderDayCell(targetTd, result);
      });

      (resp.errors || []).forEach((result) => {
        const key = dayRequestKey(result.person_id, result.year, result.week, result.weekday);
        handled.add(key);
        const targetTd = findDayTd(result.person_id, result.year, result.week, result.weekday);
        if (!targetTd) return;
        markDayPending(targetTd, false);
        const snapshot = snapshots.get(key);
        if (snapshot) renderDayCell(targetTd, snapshot);
      });

      targets.forEach((td) => {
        const key = dayRequestKey(
          Number(td.dataset.personId),
          Number(td.dataset.year),
          Number(td.dataset.week),
          Number(td.dataset.weekday),
        );
        if (handled.has(key)) return;
        markDayPending(td, false);
        const snapshot = snapshots.get(key);
        if (snapshot) renderDayCell(td, snapshot);
      });

      const errorCount = resp.errors?.length || 0;
      const undoDays = (resp.applied || []).map((result) => {
        return {
          person_id: result.person_id,
          year: result.year,
          week: result.week,
          weekday: result.weekday,
          before_hours: result.before_hours || [],
          after_hours: result.after_hours || [],
        };
      });
      if (undoDays.length) pushOverviewUndo("drag-bemanning", undoDays);
      showToast(`Drag klar: skrev ${resp.written || 0} h, tog bort ${resp.deleted || 0} h${errorCount ? `, ${errorCount} fel` : ""}`);
    } catch (e) {
      targets.forEach((td) => {
        const key = dayRequestKey(
          Number(td.dataset.personId),
          Number(td.dataset.year),
          Number(td.dataset.week),
          Number(td.dataset.weekday),
        );
        markDayPending(td, false);
        const snapshot = snapshots.get(key);
        if (snapshot) renderDayCell(td, snapshot);
      });
      const detail = e.body?.detail || e.message;
      showToast("Drag misslyckades: " + detail, "error");
    }
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

  state.areaId = preferredAreaIdForCurrentUser();
}

function applyOverviewData(data) {
  state.allPersons = (data.persons || []).map((person) => ({ ...person }));
  refreshPersons();
  state.cells = (data.matrix || []).map((cell) => ({ ...cell }));
  state.days = state.view === "month" ? (data.days || []).map((day) => ({ ...day })) : [];
  state.focusedCell = null;
  const areaName = state.areaId == null ? "Alla" : (state.areas.find((a) => a.id === state.areaId)?.name || "");

  if (state.view === "week") {
    document.getElementById("sectionTitle").textContent = `Översikt – ${areaName} – V${state.week}/${state.year}`;
    buildWeekHeader();
    buildWeekBody();
  } else {
    const monthName = document.querySelector(`#monthSelect option[value="${state.month}"]`)?.textContent || state.month;
    document.getElementById("sectionTitle").textContent = `Översikt – ${areaName} – ${monthName} ${state.year}`;
    buildMonthHeader();
    buildMonthBody();
  }
  setupOverviewHorizontalScroll();
  scheduleNextOverviewRevalidate();
}

function renderOverviewFromAllCache() {
  const cached = overviewAllCache.get(overviewCacheKey());
  if (!cached) return false;
  loadState.controller?.abort();
  loadState.requestSeq += 1;
  applyOverviewData(filterOverviewDataForArea(cached, state.areaId));
  scheduleNextOverviewRevalidate(500);
  return true;
}

async function prefetchAllOverview() {
  const key = overviewCacheKey();
  if (overviewAllCache.has(key) || overviewAllFetchState.key === key) return;
  overviewAllFetchState.controller?.abort();
  const controller = new AbortController();
  overviewAllFetchState.controller = controller;
  overviewAllFetchState.key = key;
  try {
    const data = await api.get(overviewUrl(null), { signal: controller.signal });
    if (controller.signal.aborted) return;
    setOverviewAllCache(key, filterOverviewDataForArea(data, null));
    scheduleNextOverviewRevalidate();
  } catch (err) {
    if (err?.name !== "AbortError") console.warn("Kunde inte forhämta hela översikten", err);
  } finally {
    if (overviewAllFetchState.controller === controller) {
      overviewAllFetchState.controller = null;
      overviewAllFetchState.key = "";
    }
  }
}

async function revalidateOverview() {
  if (document.hidden) return;
  if (overviewIsBusyForBackgroundUpdate()) {
    scheduleNextOverviewRevalidate(OVERVIEW_REVALIDATE_SOON_MS);
    return;
  }

  const key = overviewCacheKey();
  const cached = overviewAllCache.get(key);
  if (!cached) {
    await prefetchAllOverview();
    scheduleNextOverviewRevalidate();
    return;
  }
  const cachedPatch = patchOverviewFromAllData(cached);
  if (cachedPatch.skippedFocused) {
    scheduleNextOverviewRevalidate(OVERVIEW_REVALIDATE_SOON_MS);
    return;
  }
  notifyOverviewBackgroundUpdate(cachedPatch.patched ? 1 : 0);

  overviewRevalidateState.controller?.abort();
  const controller = new AbortController();
  overviewRevalidateState.controller = controller;
  try {
    const revision = await api.get(overviewRevisionUrl(null), { signal: controller.signal });
    if (controller.signal.aborted || key !== overviewCacheKey()) return;
    if (revision?.revision_key && revision.revision_key === cached.revision_key) {
      overviewRevalidateState.errorCount = 0;
      scheduleNextOverviewRevalidate();
      return;
    }

    const fresh = await api.get(overviewUrl(null), { signal: controller.signal });
    if (controller.signal.aborted || key !== overviewCacheKey()) return;
    setOverviewAllCache(key, filterOverviewDataForArea(fresh, null));
    const result = patchOverviewFromAllData(fresh);
    notifyOverviewBackgroundUpdate(result.patched ? 1 : 0);
    overviewRevalidateState.errorCount = 0;
  } catch (err) {
    if (err?.name !== "AbortError") {
      overviewRevalidateState.errorCount += 1;
      console.warn("Kunde inte kontrollera färsk översikt", err);
    }
  } finally {
    if (overviewRevalidateState.controller === controller) {
      overviewRevalidateState.controller = null;
    }
    const backoff = Math.min(overviewRevalidateState.errorCount, 3) * 10000;
    scheduleNextOverviewRevalidate(overviewRevalidateDelay() + backoff);
  }
}

async function load() {
  if (renderOverviewFromAllCache()) {
    void prefetchAllOverview();
    return true;
  }
  const requestSeq = ++loadState.requestSeq;
  loadState.controller?.abort();
  const controller = new AbortController();
  loadState.controller = controller;
  try {

  if (state.view === "week") {
    const data = await api.get(overviewUrl(state.areaId), { signal: controller.signal });
    if (controller.signal.aborted || requestSeq !== loadState.requestSeq) return false;
    if (state.areaId == null) {
      setOverviewAllCache(overviewCacheKey(), filterOverviewDataForArea(data, null));
    }
    applyOverviewData(data);
    void prefetchAllOverview();
    return true;
  } else {
    const data = await api.get(overviewUrl(state.areaId), { signal: controller.signal });
    if (controller.signal.aborted || requestSeq !== loadState.requestSeq) return false;
    if (state.areaId == null) {
      setOverviewAllCache(overviewCacheKey(), filterOverviewDataForArea(data, null));
    }
    applyOverviewData(data);
    void prefetchAllOverview();
    return true;
  }

    return true;
  } catch (err) {
    if (err?.name === "AbortError") return false;
    throw err;
  } finally {
    if (loadState.controller === controller) {
      loadState.controller = null;
    }
  }
}

function shiftPeriod(delta) {
  markOverviewActivity();
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
  persistOverviewState();
  load();
}

function updateViewVisibility() {
  const isMonth = state.view === "month";
  document.querySelectorAll(".week-only").forEach((el) => (el.hidden = isMonth));
  document.querySelectorAll(".month-only").forEach((el) => (el.hidden = !isMonth));
}


// ---- Init ----
(async () => {
  state.currentUser = await initPage("overview");
  if (!state.currentUser) return;
  applyOverviewReadOnlyMode();
  await loadInitial();

  const stored = readSelectedDate();
  if (stored) {
    state.selectedDateParts = stored;
    const [y, m, d] = stored;
    const wk = isoWeek(new Date(Date.UTC(y, m - 1, d)));
    state.year = wk.year;
    state.week = wk.week;
    state.month = m;
  } else {
    const nowDate = new Date();
    state.selectedDateParts = [nowDate.getFullYear(), nowDate.getMonth() + 1, nowDate.getDate()];
    const now = isoWeek(nowDate);
    state.year = now.year;
    state.week = now.week;
    state.month = nowDate.getMonth() + 1;
  }

  document.getElementById("yearInput").value = state.year;
  document.getElementById("weekInput").value = state.week;
  document.getElementById("monthSelect").value = String(state.month);
  updateViewVisibility();

  await load();
  setupDrag();
  setupPersonOrderDrag();
  document.addEventListener("pointerdown", markOverviewActivity, { passive: true });
  document.addEventListener("keydown", markOverviewActivity, { passive: true });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      clearTimeout(overviewRevalidateState.timer);
      overviewRevalidateState.controller?.abort();
      return;
    }
    markOverviewActivity();
    scheduleNextOverviewRevalidate(OVERVIEW_REVALIDATE_SOON_MS);
  });

  const onControlChange = async () => {
    markOverviewActivity();
    state.year = Number(document.getElementById("yearInput").value) || state.year;
    state.week = Number(document.getElementById("weekInput").value) || state.week;
    state.month = Number(document.getElementById("monthSelect").value) || state.month;
    persistOverviewState();
    await load();
  };

  document.getElementById("yearInput").addEventListener("change", onControlChange);
  document.getElementById("weekInput").addEventListener("change", onControlChange);
  document.getElementById("monthSelect").addEventListener("change", onControlChange);
  window.addEventListener("flow:areaFocusChanged", async () => {
    markOverviewActivity();
    state.areaId = preferredAreaIdForCurrentUser();
    await load();
  });
  document.getElementById("prev").addEventListener("click", () => shiftPeriod(-1));
  document.getElementById("next").addEventListener("click", () => shiftPeriod(1));
  document.getElementById("undoBtn").addEventListener("click", () => undoLastOverviewAction());
  document.getElementById("redoBtn").addEventListener("click", () => redoLastOverviewAction());
  updateUndoRedoButtons();

  document.addEventListener("keydown", (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    const key = e.key.toLowerCase();
    if (key !== "z" && key !== "y") return;
    const active = document.activeElement;
    if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.isContentEditable)) return;
    e.preventDefault();
    if (overviewIsReadOnly()) {
      showReadOnlyToast();
      return;
    }
    if (key === "y" || (key === "z" && e.shiftKey)) void redoLastOverviewAction();
    else void undoLastOverviewAction();
  });

  document.getElementById("viewMode").addEventListener("change", (e) => {
    markOverviewActivity();
    state.view = e.target.value;
    updateViewVisibility();
    persistOverviewState();
    load();
  });

  document.getElementById("nameFilter").addEventListener("input", (e) => {
    state.nameFilter = e.target.value;
    refreshPersons();
    if (state.view === "week") buildWeekBody();
    else buildMonthBody();
    setupOverviewHorizontalScroll();
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
    setupOverviewHorizontalScroll();
  });
})();

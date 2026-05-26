// Bemanningsvy – matris person × timme.

const HOURS = Array.from({ length: 18 }, (_, i) => 6 + i);   // 6..23
const DAYS = { 1: "Måndag", 2: "Tisdag", 3: "Onsdag", 4: "Torsdag", 5: "Fredag", 6: "Lördag", 7: "Söndag" };
const FULL_SEGMENT = { minute_start: 0, minute_end: 60 };
const HALF_SEGMENTS = [
  { minute_start: 0, minute_end: 30 },
  { minute_start: 30, minute_end: 60 },
];
const CALC_AREA_FALLBACK_KEYS = ["GG", "MG", "AS", "EH"];

const state = {
  currentUser: null,
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
  scheduledDefaults: {},       // {person_id: Map<hour, activity_id>}
  undoStack: [],
  redoStack: [],
  focusedCell: null,
  clipboard: null,
  nameFilter: "",
  sortKey: "sort_order",
  sortAsc: true,
  summaryRows: [],
  allSummaryRows: [],
  lockForeignScheduleCells: false,
  calcSelection: "",
  calcInputs: {},
};

const drag = {
  active: false,
  pending: false,
  suppressClick: false,
  sourceTd: null,
  sourceActivityId: null,
  sourceMinuteStart: 0,
  sourceMinuteEnd: 60,
  sourceRow: -1,
  sourceCol: -1,
  currentRow: -1,
  currentCol: -1,
  currentTargetMinuteStart: 0,
  currentTargetMinuteEnd: 60,
  targetRangesByCell: new Map(),
  startX: 0,
  startY: 0,
};

const personOrderDrag = {
  sourceId: null,
  targetId: null,
  position: "after",
};

const summaryState = {
  controller: null,
  timer: null,
  requestSeq: 0,
  appliedSeq: 0,
  errorToastAt: 0,
  calcFrame: 0,
};

const scheduleLoadState = {
  controller: null,
  requestSeq: 0,
};

const scheduleAllCache = new Map();
const scheduleAreaCache = new Map();
const scheduleAllFetchState = {
  controller: null,
  key: "",
};
const SCHEDULE_ALL_CACHE_LIMIT = 4;
const SCHEDULE_AREA_CACHE_LIMIT = 24;
const SCHEDULE_REVALIDATE_ACTIVE_MS = 10000;
const SCHEDULE_REVALIDATE_IDLE_MS = 30000;
const SCHEDULE_REVALIDATE_SOON_MS = 1500;
const SCHEDULE_REVALIDATE_ACTIVE_WINDOW_MS = 60000;
const scheduleRevalidateState = {
  timer: null,
  controller: null,
  lastActivityAt: Date.now(),
  errorCount: 0,
  toastAt: 0,
};

function scheduleIsReadOnly() {
  if (typeof isReadOnlyUser === "function") return isReadOnlyUser(state.currentUser);
  return state.currentUser?.role === "viewer" && !state.currentUser?.is_super_user;
}

function scheduleScopeKey() {
  const user = state.currentUser || {};
  return [
    user.id ?? user.username ?? "anonymous",
    user.is_super_user ? "super" : "scoped",
    user.business_id ?? "global",
  ].join(":");
}

function scheduleCacheKey() {
  return `${scheduleScopeKey()}|${state.year}|${state.week}|${state.weekday}`;
}

function scheduleAreaCacheKey(areaId = state.areaId, baseKey = scheduleCacheKey()) {
  return `${baseKey}|area:${areaId == null ? "ALLT" : Number(areaId)}`;
}

function scheduleUrl(areaId = state.areaId) {
  return `/api/schedule?year=${state.year}&week=${state.week}&weekday=${state.weekday}` +
    (areaId ? `&area_id=${areaId}` : "");
}

function scheduleRevisionUrl(areaId = null) {
  return `/api/schedule/revision?year=${state.year}&week=${state.week}&weekday=${state.weekday}` +
    (areaId ? `&area_id=${areaId}` : "");
}

function setScheduleAllCache(key, data) {
  scheduleAllCache.delete(key);
  scheduleAllCache.set(key, data);
  while (scheduleAllCache.size > SCHEDULE_ALL_CACHE_LIMIT) {
    scheduleAllCache.delete(scheduleAllCache.keys().next().value);
  }
}

function setScheduleAreaCache(key, data) {
  scheduleAreaCache.delete(key);
  scheduleAreaCache.set(key, data);
  while (scheduleAreaCache.size > SCHEDULE_AREA_CACHE_LIMIT) {
    scheduleAreaCache.delete(scheduleAreaCache.keys().next().value);
  }
}

function invalidateScheduleAllCache() {
  scheduleAllCache.clear();
  scheduleAreaCache.clear();
  scheduleAllFetchState.controller?.abort();
  scheduleRevalidateState.controller?.abort();
  scheduleAllFetchState.controller = null;
  scheduleAllFetchState.key = "";
  scheduleRevalidateState.controller = null;
  scheduleNextScheduleRevalidate(SCHEDULE_REVALIDATE_SOON_MS);
}

function filterScheduleDataForArea(data, areaId) {
  const source = data || {};
  const persons = Array.isArray(source.persons) ? source.persons : [];
  const cells = Array.isArray(source.cells) ? source.cells : [];
  const copyScheduledFor = (personIds, scheduled) => Object.fromEntries(
    Object.entries(scheduled || {}).filter(([personId]) => personIds.has(Number(personId)))
  );

  if (areaId == null) {
    return {
      ...source,
      area_id: null,
      persons: persons.map((person) => ({ ...person })),
      cells: cells.map((cell) => ({ ...cell })),
      scheduled_hours: { ...(source.scheduled_hours || {}) },
      scheduled_defaults: { ...(source.scheduled_defaults || {}) },
    };
  }

  const selectedAreaId = Number(areaId);
  const visiblePersons = persons.filter((person) => Number(person.home_area_id) === selectedAreaId);
  const personIds = new Set(visiblePersons.map((person) => Number(person.id)));
  return {
    ...source,
    area_id: selectedAreaId,
    persons: visiblePersons.map((person) => ({ ...person })),
    cells: cells.filter((cell) => personIds.has(Number(cell.person_id))).map((cell) => ({ ...cell })),
    scheduled_hours: copyScheduledFor(personIds, source.scheduled_hours),
    scheduled_defaults: copyScheduledFor(personIds, source.scheduled_defaults),
  };
}

function setupScheduleHorizontalScroll() {
  if (typeof setupSyncedHorizontalScroll === "function") {
    setupSyncedHorizontalScroll(document.getElementById("scheduleTable"));
  }
}

function markScheduleActivity() {
  scheduleRevalidateState.lastActivityAt = Date.now();
}

function scheduleRevalidateDelay() {
  return Date.now() - scheduleRevalidateState.lastActivityAt < SCHEDULE_REVALIDATE_ACTIVE_WINDOW_MS
    ? SCHEDULE_REVALIDATE_ACTIVE_MS
    : SCHEDULE_REVALIDATE_IDLE_MS;
}

function scheduleIsBusyForBackgroundUpdate() {
  return drag.active
    || drag.pending
    || personOrderDrag.sourceId != null
    || Boolean(document.querySelector("#scheduleBody .pending-save"));
}

function scheduleNextScheduleRevalidate(delay = scheduleRevalidateDelay()) {
  clearTimeout(scheduleRevalidateState.timer);
  scheduleRevalidateState.timer = null;
  if (document.hidden) return;
  scheduleRevalidateState.timer = setTimeout(() => {
    scheduleRevalidateState.timer = null;
    void revalidateSchedule();
  }, delay);
}

function notifyScheduleBackgroundUpdate(changedCount) {
  if (!changedCount) return;
  const now = Date.now();
  if (now - scheduleRevalidateState.toastAt < 10000) return;
  scheduleRevalidateState.toastAt = now;
  showToast("Bemanningen uppdaterades i bakgrunden.", "info", 2500);
}

function schedulePersonSignature(persons) {
  return JSON.stringify((persons || []).map((person) => [
    Number(person.id),
    person.name || "",
    Number(person.home_area_id) || 0,
    Number(person.home_activity_id) || 0,
    person.has_fixed_schedule !== false,
    Number(person.sort_order) || 0,
  ]));
}

function scheduleMapPayloadSignature() {
  const hours = Object.fromEntries(
    Object.entries(state.scheduledHours || {}).map(([personId, values]) => [
      personId,
      Array.from(values || []).map(Number).sort((a, b) => a - b),
    ])
  );
  const defaults = Object.fromEntries(
    Object.entries(state.scheduledDefaults || {}).map(([personId, values]) => [
      personId,
      Object.fromEntries(Array.from(values || []).sort((a, b) => Number(a[0]) - Number(b[0]))),
    ])
  );
  return JSON.stringify({ hours, defaults });
}

function scheduleDataPayloadSignature(data) {
  return JSON.stringify({
    hours: data?.scheduled_hours || {},
    defaults: data?.scheduled_defaults || {},
  });
}

function normalizeScheduleSegment(segment) {
  return {
    person_id: Number(segment.person_id),
    hour: Number(segment.hour),
    minute_start: Number(segment.minute_start),
    minute_end: Number(segment.minute_end),
    activity_id: segment.activity_id == null ? null : Number(segment.activity_id),
    empty_override: !!segment.empty_override,
    version: Number(segment.version) || 0,
    updated_at: segment.updated_at || null,
    updated_by: segment.updated_by == null ? null : Number(segment.updated_by),
  };
}

function scheduleSegmentSignature(segment) {
  const normalized = normalizeScheduleSegment(segment);
  return [
    normalized.minute_start,
    normalized.minute_end,
    normalized.activity_id ?? "",
    normalized.empty_override ? 1 : 0,
    normalized.version,
    normalized.updated_at || "",
    normalized.updated_by ?? "",
  ].join(":");
}

function scheduleHourSignature(segments) {
  return (segments || [])
    .map((segment) => scheduleSegmentSignature(segment))
    .sort()
    .join("|");
}

function scheduleGroupsFromCells(cells) {
  const groups = new Map();
  (cells || []).forEach((cell) => {
    const normalized = normalizeScheduleSegment(cell);
    const key = hourKey(normalized.person_id, normalized.hour);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(normalized);
  });
  groups.forEach((segments, key) => groups.set(key, sortSegments(segments)));
  return groups;
}

function scheduleHourIsFocused(personId, hour) {
  return Number(state.focusedCell?.personId) === Number(personId)
    && Number(state.focusedCell?.hour) === Number(hour)
    && document.activeElement?.closest("#scheduleBody");
}

function patchScheduleFromAllData(allData) {
  const data = filterScheduleDataForArea(allData, state.areaId);
  const personsChanged = schedulePersonSignature(state.allPersons) !== schedulePersonSignature(data.persons || []);
  const scheduledChanged = scheduleMapPayloadSignature() !== scheduleDataPayloadSignature(data);
  if (personsChanged || scheduledChanged) {
    applyScheduleData(data);
    return { changed: true, patched: false };
  }

  state.allPersons = data.persons || [];
  state.lockForeignScheduleCells = !!data.lock_foreign_schedule_cells;
  const nextGroups = scheduleGroupsFromCells(data.cells || []);
  const keys = new Set([...Array.from(state.hourCells.keys()), ...Array.from(nextGroups.keys())]);
  let changedCount = 0;
  let skippedFocused = false;

  keys.forEach((key) => {
    const [personId, hour] = key.split(":").map(Number);
    const current = state.hourCells.get(key) || [];
    const next = nextGroups.get(key) || [];
    if (scheduleHourSignature(current) === scheduleHourSignature(next)) return;
    if (scheduleHourIsFocused(personId, hour)) {
      skippedFocused = true;
      return;
    }
    replaceHourSegments(personId, hour, next);
    const td = getHourTd(personId, hour);
    if (td) renderHourCell(td);
    changedCount += 1;
  });

  if (changedCount) {
    refreshCurrentHourHighlight();
    scheduleSummaryRefresh(0);
  }
  if (skippedFocused) scheduleNextScheduleRevalidate(SCHEDULE_REVALIDATE_SOON_MS);
  return { changed: changedCount > 0 || skippedFocused, patched: changedCount > 0, skippedFocused };
}

function showReadOnlyToast() {
  showToast("Visningsläge: du kan se bemanningen men inte ändra den.", "warn");
}

function applyScheduleReadOnlyMode() {
  const readOnly = scheduleIsReadOnly();
  document.body.classList.toggle("read-only-mode", readOnly);
  ["copyBtn", "clearBtn"].forEach((id) => {
    const button = document.getElementById(id);
    if (!button) return;
    button.hidden = readOnly;
    button.disabled = readOnly;
  });
  updateUndoRedoButtons();
}

function preferredAreaIdForCurrentUser() {
  return typeof preferredAreaIdFromFocus === "function" ? preferredAreaIdFromFocus(state.areas) : null;
}


function isoWeek(d = new Date()) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((date - yearStart) / 86400000 + 1) / 7);
  return { year: date.getUTCFullYear(), week, weekday: dayNum };
}

// (ISO year, ISO week, weekday 1..7) -> UTC Date pointing at that day at 00:00.
function dateFromYWD(year, week, weekday) {
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const jan4Weekday = jan4.getUTCDay() || 7;
  const week1Monday = new Date(jan4);
  week1Monday.setUTCDate(jan4.getUTCDate() - (jan4Weekday - 1));
  const result = new Date(week1Monday);
  result.setUTCDate(week1Monday.getUTCDate() + (week - 1) * 7 + (weekday - 1));
  return result;
}

function ymdString(date) {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function dateFromYmd(str) {
  const [y, m, d] = String(str).split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(Date.UTC(y, m - 1, d));
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
    th.dataset.hour = h;
    th.textContent = String(h).padStart(2, "0") + ":00";
    header.appendChild(th);
  });
}

function currentHourIfToday() {
  const now = new Date();
  const today = isoWeek(now);
  if (today.year !== state.year || today.week !== state.week || today.weekday !== state.weekday) return null;
  return now.getHours();
}

function refreshCurrentHourHighlight() {
  const hour = currentHourIfToday();
  document.querySelectorAll("table.matrix .now-hour").forEach((el) => el.classList.remove("now-hour"));
  if (hour == null) return;
  document.querySelectorAll(`table.matrix th[data-hour="${hour}"]`).forEach((el) => el.classList.add("now-hour"));
  document.querySelectorAll(`table.matrix td[data-hour="${hour}"]`).forEach((el) => el.classList.add("now-hour"));
}

function activityById(id) {
  return state.activities.find((a) => a.id === id);
}

function activityByCode(code) {
  return state.activities.find((a) => a.code === code);
}

function areaById(id) {
  return state.areas.find((a) => a.id === id);
}

function personById(id) {
  return state.persons.find((p) => p.id === id) || state.allPersons.find((p) => p.id === id) || null;
}

function colorFor(activityId) {
  const a = activityById(activityId);
  return a ? a.color : "#ffffff";
}

function activityLabel(activityId) {
  const a = activityById(activityId);
  return a ? a.label : "";
}

function defaultHomeActivityId(person) {
  if (!person?.home_area_id) return null;
  const homeArea = areaById(person.home_area_id);
  const preferred = homeArea?.code ? activityByCode(`${homeArea.code}_VM`) : null;
  if (preferred) return preferred.id;

  const fallback = state.activities
    .filter((activity) =>
      activity.area_id === person.home_area_id
      && activity.category !== "absence"
    )
    .sort((a, b) => a.sort_order - b.sort_order || a.label.localeCompare(b.label))[0];
  return fallback?.id || null;
}

function homeActivityIdForPerson(person) {
  return person?.home_activity_id || defaultHomeActivityId(person);
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

function canUsePersonSortOrder() {
  const user = state.currentUser || {};
  const roles = typeof userRoles === "function" ? userRoles(user) : [user.role];
  const canCrossAreas = canSortPersonsAcrossAreas();
  const hasAllowedRole = canCrossAreas || roles.includes("admin") || roles.includes("staffing_manager");
  const hasArea = canCrossAreas || (user.area_id != null && Number.isFinite(Number(user.area_id)));
  return hasAllowedRole && hasArea && typeof canEditPage === "function" && canEditPage(user, "personSortOrder");
}

function canSortPersonsAcrossAreas() {
  const user = state.currentUser || {};
  return Boolean(user.is_super_user || user.is_demo);
}

function canReorderPerson(person) {
  return canUsePersonSortOrder()
    && (canSortPersonsAcrossAreas() || Number(person?.home_area_id) === Number(state.currentUser?.area_id));
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
    .querySelectorAll("#scheduleBody tr.person-order-drop-before, #scheduleBody tr.person-order-drop-after")
    .forEach((row) => row.classList.remove("person-order-drop-before", "person-order-drop-after"));
}

function resetPersonOrderDrag() {
  document.body.classList.remove("dragging-person-order");
  document
    .querySelectorAll("#scheduleBody tr.person-order-dragging")
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
  if (canSortPersonsAcrossAreas()) {
    return state.persons
      .filter((person) => person.is_active !== false)
      .map((person) => Number(person.id));
  }
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
  buildRows();
  setupScheduleHorizontalScroll();
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
    const message = canSortPersonsAcrossAreas()
      ? "Personlistan har ändrats. Läs om vyn och försök igen."
      : "Du kan bara sortera personer med samma hemområde som ditt användarområde.";
    showToast(message, "warn", 5000);
    return;
  }
  const personIds = movedPersonOrderIds(sourceId, targetId, position, ids);
  if (personIds.join(",") === ids.join(",")) return;
  markScheduleActivity();
  try {
    const updatedPersons = await api.put("/api/persons/sort-order", { person_ids: personIds });
    invalidateScheduleAllCache();
    applyPersonOrderResponse(updatedPersons);
    showToast("Personsorteringen sparades.", "success", 2500);
  } catch (error) {
    showToast(error.message || "Kunde inte spara personsorteringen.", "error", 7000);
    if (error.status === 409) await loadSchedule();
  }
}

function setupPersonOrderDrag() {
  const body = document.getElementById("scheduleBody");
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
      empty_override: !!cell.empty_override,
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
    empty_override: !!segment.empty_override,
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
    empty_override: false,
    version: 0,
  };
}

function currentUserCanBypassCellLock() {
  if (typeof isAdminUser === "function") return isAdminUser(state.currentUser);
  return state.currentUser?.role === "admin" || state.currentUser?.is_super_user;
}

function isForeignLockedSegment(segment) {
  if (!state.lockForeignScheduleCells || currentUserCanBypassCellLock()) return false;
  if (!segment || segment.updated_by == null || state.currentUser?.id == null) return false;
  return Number(segment.updated_by) !== Number(state.currentUser.id);
}

function isRangeLocked(personId, hour, minuteStart, minuteEnd) {
  const segment = segmentsForHour(personId, hour).find(
    (item) => item.minute_start === minuteStart && item.minute_end === minuteEnd
  );
  return isForeignLockedSegment(segment);
}

function isHourLocked(personId, hour) {
  return segmentsForHour(personId, hour).some((segment) => isForeignLockedSegment(segment));
}

function showLockedCellToast() {
  showToast("Cellen är låst eftersom en annan användare har fyllt i den.", "warn");
}

function cloneSegment(segment) {
  return {
    person_id: Number(segment.person_id),
    hour: Number(segment.hour),
    minute_start: Number(segment.minute_start),
    minute_end: Number(segment.minute_end),
    activity_id: segment.activity_id == null ? null : Number(segment.activity_id),
    empty_override: !!segment.empty_override,
    version: Number(segment.version) || 0,
    updated_at: segment.updated_at || null,
    updated_by: segment.updated_by == null ? null : Number(segment.updated_by),
  };
}

function cloneSegments(segments) {
  return sortSegments((segments || []).map((segment) => cloneSegment(segment)));
}

function getHourTd(personId, hour) {
  return document.querySelector(
    `#scheduleBody td[data-person-id="${personId}"][data-hour="${hour}"]`
  );
}

function snapshotHour(personId, hour) {
  return {
    year: state.year,
    week: state.week,
    weekday: state.weekday,
    personId: Number(personId),
    hour: Number(hour),
    segments: cloneSegments(segmentsForHour(personId, hour)),
  };
}

function snapshotAllExplicitHours() {
  const snapshots = new Map();
  state.hourCells.forEach((segments, key) => {
    if (!segments.length) return;
    const [personId, hour] = key.split(":").map(Number);
    snapshots.set(key, snapshotHour(personId, hour));
  });
  return snapshots;
}

function pushScheduleUndo(label, snapshots) {
  const values = snapshots instanceof Map ? Array.from(snapshots.values()) : snapshots;
  const normalized = (values || [])
    .filter(Boolean)
    .map((snapshot) => ({
      year: Number(snapshot.year ?? state.year),
      week: Number(snapshot.week ?? state.week),
      weekday: Number(snapshot.weekday ?? state.weekday),
      personId: Number(snapshot.personId),
      hour: Number(snapshot.hour),
      segments: cloneSegments(snapshot.segments || []),
    }));

  if (!normalized.length) return;
  state.undoStack.push({ label, snapshots: normalized });
  if (state.undoStack.length > 50) state.undoStack.shift();
  state.redoStack = [];
  updateUndoRedoButtons();
}

function updateUndoRedoButtons() {
  const undoBtn = document.getElementById("undoBtn");
  const redoBtn = document.getElementById("redoBtn");
  const readOnly = scheduleIsReadOnly();
  if (undoBtn) undoBtn.disabled = readOnly || state.undoStack.length === 0;
  if (redoBtn) redoBtn.disabled = readOnly || state.redoStack.length === 0;
}

function segmentVersionRefs(segments) {
  return cloneSegments(segments).map((segment) => ({
    minute_start: segment.minute_start,
    minute_end: segment.minute_end,
    expected_version: segment.version,
  }));
}

function restoreSegmentPayload(segments) {
  return cloneSegments(segments).map((segment) => ({
    minute_start: segment.minute_start,
    minute_end: segment.minute_end,
    activity_id: segment.activity_id,
    empty_override: !!segment.empty_override,
  }));
}

function applyRestoredHours(hours) {
  (hours || []).forEach((item) => {
    const personId = Number(item.person_id);
    const hour = Number(item.hour);
    replaceHourSegments(personId, hour, item.segments || []);
    const td = getHourTd(personId, hour);
    if (!td) return;
    setHourPending(td, false);
    renderHourCell(td);
  });
}

function actionMatchesCurrentDay(action) {
  return (action?.snapshots || []).every((snapshot) =>
    snapshot.year === state.year
    && snapshot.week === state.week
    && snapshot.weekday === state.weekday
  );
}

async function applyHistoryAction(action, { historyLabel, oppositeStack, oppositeLabel }) {
  if (scheduleIsReadOnly()) {
    showReadOnlyToast();
    return false;
  }
  if (!actionMatchesCurrentDay(action)) {
    showToast(`Byt tillbaka till dagen där ändringen gjordes för att ${historyLabel}.`, "warn");
    return false;
  }

  // Capture current state of the affected hours so the opposite action can replay.
  const inverseSnapshots = action.snapshots.map((snapshot) =>
    snapshotHour(snapshot.personId, snapshot.hour)
  );

  const hours = action.snapshots.map((snapshot) => ({
    year: snapshot.year,
    week: snapshot.week,
    weekday: snapshot.weekday,
    hour: snapshot.hour,
    person_id: snapshot.personId,
    expected_segments: segmentVersionRefs(segmentsForHour(snapshot.personId, snapshot.hour)),
    segments: restoreSegmentPayload(snapshot.segments),
  }));

  action.snapshots.forEach((snapshot) => setHourPending(getHourTd(snapshot.personId, snapshot.hour), true));
  try {
    const resp = await api.put("/api/schedule/hours/restore", { action: "undo_restore", hours });
    invalidateScheduleAllCache();
    applyRestoredHours(resp.hours);
    oppositeStack.push({ label: action.label, snapshots: inverseSnapshots });
    if (oppositeStack.length > 50) oppositeStack.shift();
    scheduleSummaryRefresh(0);
    showToast(`${oppositeLabel}: ${action.label}`);
    updateUndoRedoButtons();
    return true;
  } catch (e) {
    action.snapshots.forEach((snapshot) => setHourPending(getHourTd(snapshot.personId, snapshot.hour), false));
    if (e.status === 409) {
      showToast(`Kunde inte ${historyLabel} eftersom dagen ändrats. Läser om.`, "warn");
      await loadSchedule();
    } else {
      showToast(`Kunde inte ${historyLabel}: ` + e.message, "error");
    }
    return false;
  }
}

async function undoLastScheduleAction() {
  if (scheduleIsReadOnly()) {
    showReadOnlyToast();
    return;
  }
  const action = state.undoStack[state.undoStack.length - 1];
  if (!action) {
    showToast("Inget att ångra.", "warn");
    return;
  }
  const ok = await applyHistoryAction(action, {
    historyLabel: "ångra",
    oppositeStack: state.redoStack,
    oppositeLabel: "Ångrade",
  });
  if (ok) state.undoStack.pop();
  updateUndoRedoButtons();
}

async function redoLastScheduleAction() {
  if (scheduleIsReadOnly()) {
    showReadOnlyToast();
    return;
  }
  const action = state.redoStack[state.redoStack.length - 1];
  if (!action) {
    showToast("Inget att göra om.", "warn");
    return;
  }
  const ok = await applyHistoryAction(action, {
    historyLabel: "göra om",
    oppositeStack: state.undoStack,
    oppositeLabel: "Gjorde om",
  });
  if (ok) state.redoStack.pop();
  updateUndoRedoButtons();
}

function setHourPending(td, pending) {
  if (!td) return;
  td.classList.toggle("pending-save", pending);
  td.querySelectorAll("select").forEach((select) => {
    select.disabled = pending || scheduleIsReadOnly();
  });
}

function snapshotHoursFromCells(cells) {
  const snapshots = new Map();
  cells.forEach((cell) => {
    const key = hourKey(cell.person_id, cell.hour);
    if (snapshots.has(key)) return;
    snapshots.set(key, {
      personId: Number(cell.person_id),
      hour: Number(cell.hour),
      segments: cloneSegments(segmentsForHour(cell.person_id, cell.hour)),
    });
  });
  return snapshots;
}

function optimisticSegmentsForHour(personId, hour, items) {
  const current = cloneSegments(segmentsForHour(personId, hour));
  const scheduled = isScheduledHour(personId, hour);
  const needsHalfSegments = items.some(
    (item) => Number(item.minute_end) - Number(item.minute_start) === 30
  );

  if (!needsHalfSegments && items.length === 1 && Number(items[0].minute_start) === 0 && Number(items[0].minute_end) === 60) {
    return [
      {
        person_id: personId,
        hour,
        minute_start: 0,
        minute_end: 60,
        activity_id: items[0].activity_id == null ? null : Number(items[0].activity_id),
        empty_override: items[0].activity_id == null && scheduled,
        version: current[0]?.version || 0,
        updated_at: current[0]?.updated_at || null,
        updated_by: current[0]?.updated_by ?? null,
      },
    ];
  }

  let segments = current;
  if (needsHalfSegments) {
    if (segments.length === 0) {
      segments = HALF_SEGMENTS.map(({ minute_start, minute_end }) => ({
        person_id: personId,
        hour,
        minute_start,
        minute_end,
        activity_id: null,
        empty_override: scheduled,
        version: 0,
        updated_at: null,
        updated_by: null,
      }));
    } else if (
      segments.length === 1 &&
      segments[0].minute_start === 0 &&
      segments[0].minute_end === 60
    ) {
      const source = segments[0];
      segments = HALF_SEGMENTS.map(({ minute_start, minute_end }) => ({
        person_id: personId,
        hour,
        minute_start,
        minute_end,
        activity_id: source.activity_id,
        empty_override: source.empty_override,
        version: source.version,
        updated_at: source.updated_at || null,
        updated_by: source.updated_by ?? null,
      }));
    }
  }

  const byRange = new Map(
    segments.map((segment) => [`${segment.minute_start}:${segment.minute_end}`, cloneSegment(segment)])
  );
  if (needsHalfSegments) {
    HALF_SEGMENTS.forEach(({ minute_start, minute_end }) => {
      const key = `${minute_start}:${minute_end}`;
      if (byRange.has(key)) return;
      byRange.set(key, {
        person_id: personId,
        hour,
        minute_start,
        minute_end,
        activity_id: null,
        empty_override: scheduled,
        version: 0,
        updated_at: null,
        updated_by: null,
      });
    });
  }

  items.forEach((item) => {
    const key = `${item.minute_start}:${item.minute_end}`;
    const existing = byRange.get(key) || {
      person_id: personId,
      hour,
      minute_start: Number(item.minute_start),
      minute_end: Number(item.minute_end),
      activity_id: null,
      empty_override: scheduled,
      version: 0,
      updated_at: null,
      updated_by: null,
    };
    byRange.set(key, {
      ...existing,
      activity_id: item.activity_id == null ? null : Number(item.activity_id),
      empty_override: item.activity_id == null && scheduled,
    });
  });

  return sortSegments(Array.from(byRange.values()));
}

function applySegmentsByHourResponse(applied) {
  const updatedHours = new Map();
  (applied || []).forEach((segment) => {
    const key = hourKey(segment.person_id, segment.hour);
    if (!updatedHours.has(key)) updatedHours.set(key, []);
    updatedHours.get(key).push(segment);
  });

  updatedHours.forEach((segments, key) => {
    const [personId, hour] = key.split(":").map(Number);
    replaceHourSegments(personId, hour, segments);
    const td = getHourTd(personId, hour);
    if (!td) return;
    setHourPending(td, false);
    renderHourCell(td);
  });
}

function restoreHourSnapshots(snapshots) {
  snapshots.forEach((snapshot) => {
    replaceHourSegments(snapshot.personId, snapshot.hour, snapshot.segments);
    const td = getHourTd(snapshot.personId, snapshot.hour);
    if (!td) return;
    setHourPending(td, false);
    renderHourCell(td);
  });
}

function targetMatchesCurrentDay(year, week, weekday) {
  return year === state.year && week === state.week && weekday === state.weekday;
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

function scheduledDefaultActivityId(personId, hour) {
  const byHour = state.scheduledDefaults[personId];
  if (!byHour) return null;
  return byHour.has(hour) ? byHour.get(hour) : null;
}

function formatHours(value) {
  const num = Number(value) || 0;
  return Number.isInteger(num) ? String(num) : num.toFixed(1).replace(/\.0$/, "");
}

function areaCodeById(id) {
  return state.areas.find((area) => area.id === id)?.code || null;
}

function areaNameByCode(code) {
  return state.areas.find((area) => area.code === code)?.name
    || ({ GG: "Granngården", MG: "Mestergruppen", AS: "Autostore", EH: "E-Handel" }[code] || code);
}

function calcAreaKeys() {
  const seen = new Set();
  const keys = [];
  state.areas
    .filter((area) => area?.is_active !== false)
    .sort((a, b) => (Number(a?.sort_order) || 0) - (Number(b?.sort_order) || 0))
    .forEach((area) => {
      const code = String(area?.code || "").trim().toUpperCase();
      if (!code || code === "ANNAT" || seen.has(code)) return;
      seen.add(code);
      keys.push(code);
    });
  return keys.length ? keys : CALC_AREA_FALLBACK_KEYS;
}

function ensureCalcInput(areaKey) {
  if (!state.calcInputs[areaKey]) {
    state.calcInputs[areaKey] = { rows: "", time: "", goal: "" };
  }
  return state.calcInputs[areaKey];
}

function sanitizeNumericInput(value) {
  const cleaned = String(value || "").replace(/[^\d.,]/g, "");
  const firstSep = cleaned.search(/[.,]/);
  if (firstSep === -1) return cleaned;
  return cleaned.slice(0, firstSep + 1) + cleaned.slice(firstSep + 1).replace(/[.,]/g, "");
}

function parseNumericInput(value) {
  if (value == null || value === "") return null;
  const normalized = String(value).replace(",", ".");
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function activityHoursByCode(code) {
  const row = state.allSummaryRows.find((item) => item.activity_code === code);
  return row ? Number(row.hours) || 0 : 0;
}

function calcMetrics(areaKey) {
  const values = ensureCalcInput(areaKey);
  const rows = parseNumericInput(values.rows);
  const time = parseNumericInput(values.time);
  const goal = parseNumericInput(values.goal);
  const plockHours = activityHoursByCode(`${areaKey}_PLOCK`);

  let need = null;
  let hours = null;
  let diff = null;
  if (rows != null && time != null && goal != null && time > 0 && goal > 0) {
    need = (rows / time) / goal;
    hours = need * time;
    diff = plockHours - hours;
  }

  return { plockHours, need, hours, diff };
}

function calcValueText(value) {
  return value == null ? "–" : formatHours(value);
}

function updateCalcPanel(panel, areaKey) {
  const { need, hours, diff } = calcMetrics(areaKey);
  const outputs = {
    need: calcValueText(need),
    hours: calcValueText(hours),
    diff: calcValueText(diff),
  };
  Object.entries(outputs).forEach(([name, text]) => {
    const el = panel.querySelector(`[data-output="${name}"]`);
    if (el) el.textContent = text;
  });
  const diffEl = panel.querySelector('[data-output="diff"]');
  if (diffEl) {
    diffEl.classList.remove("positive", "negative");
    if (diff != null) {
      if (diff > 0) diffEl.classList.add("positive");
      if (diff < 0) diffEl.classList.add("negative");
    }
  }
}

function renderCalculator() {
  const container = document.getElementById("calcPanels");
  if (!container) return;

  const active = document.activeElement;
  let focusState = null;
  if (active && container.contains(active) && active.matches("input[data-field]")) {
    const panel = active.closest(".calc-panel");
    focusState = {
      areaKey: panel?.dataset.areaKey || "",
      field: active.dataset.field || "",
      selectionStart: typeof active.selectionStart === "number" ? active.selectionStart : null,
      selectionEnd: typeof active.selectionEnd === "number" ? active.selectionEnd : null,
    };
  }

  const availableKeys = calcAreaKeys();
  if (state.calcSelection !== "ALL" && !availableKeys.includes(state.calcSelection)) {
    state.calcSelection = "ALL";
  }
  const selectedKeys = state.calcSelection === "ALL" ? availableKeys : [state.calcSelection];
  container.innerHTML = selectedKeys.map((areaKey) => {
    const values = ensureCalcInput(areaKey);
    const metrics = calcMetrics(areaKey);
    return `
      <div class="calc-panel" data-area-key="${areaKey}">
        <div class="calc-panel-title">${escapeHtml(areaNameByCode(areaKey))}</div>
        <table class="calc-table">
          <thead>
            <tr>
              <th>Dagens rader</th>
              <th>Tid kvar</th>
              <th>Mål</th>
              <th>Behov</th>
              <th>Timmar</th>
              <th>Diff</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><input type="text" inputmode="decimal" data-field="rows" value="${escapeHtml(values.rows)}" /></td>
              <td><input type="text" inputmode="decimal" data-field="time" value="${escapeHtml(values.time)}" /></td>
              <td><input type="text" inputmode="decimal" data-field="goal" value="${escapeHtml(values.goal)}" /></td>
              <td class="calc-output" data-output="need">${calcValueText(metrics.need)}</td>
              <td class="calc-output" data-output="hours">${calcValueText(metrics.hours)}</td>
              <td class="calc-output ${metrics.diff > 0 ? "positive" : metrics.diff < 0 ? "negative" : ""}" data-output="diff">${calcValueText(metrics.diff)}</td>
            </tr>
          </tbody>
        </table>
      </div>`;
  }).join("");

  container.querySelectorAll("input[data-field]").forEach((input) => {
    input.addEventListener("input", (e) => {
      const panel = e.target.closest(".calc-panel");
      if (!panel) return;
      const areaKey = panel.dataset.areaKey;
      const field = e.target.dataset.field;
      const sanitized = sanitizeNumericInput(e.target.value);
      if (sanitized !== e.target.value) e.target.value = sanitized;
      state.calcInputs[areaKey][field] = sanitized;
      updateCalcPanel(panel, areaKey);
    });
  });

  if (focusState?.areaKey && focusState.field) {
    const nextInput = container.querySelector(
      `.calc-panel[data-area-key="${focusState.areaKey}"] input[data-field="${focusState.field}"]`
    );
    if (nextInput) {
      nextInput.focus({ preventScroll: true });
      if (focusState.selectionStart != null && focusState.selectionEnd != null) {
        try {
          nextInput.setSelectionRange(focusState.selectionStart, focusState.selectionEnd);
        } catch (err) {}
      }
    }
  }
}

function setupCalculator() {
  if (!state.calcSelection) {
    const currentAreaCode = areaCodeById(state.areaId);
    const availableKeys = calcAreaKeys();
    state.calcSelection = availableKeys.includes(currentAreaCode) ? currentAreaCode : "ALL";
  }

  renderCalculator();
}

function syncCalculatorWithSelectedArea() {
  const currentAreaCode = areaCodeById(state.areaId);
  const availableKeys = calcAreaKeys();
  state.calcSelection = availableKeys.includes(currentAreaCode) ? currentAreaCode : "ALL";
  renderCalculator();
}

function appendActivityOptions(select, includeActivityIds = []) {
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
}

function buildActivitySelect(includeActivityIds = []) {
  const select = document.createElement("select");
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "–";
  select.appendChild(empty);
  appendActivityOptions(select, includeActivityIds);
  return select;
}

function ensureSelectHasActivityOption(select, activityId) {
  if (activityId == null) return;
  const value = String(activityId);
  const exists = Array.from(select.options).some((option) => option.value === value);
  if (exists) return;

  const activity = activityById(activityId);
  if (!activity) return;

  const option = document.createElement("option");
  option.value = value;
  option.textContent = activity.label;
  option.style.background = activity.color;
  select.appendChild(option);
}

function setSelectActivityValue(select, activityId) {
  if (activityId == null) {
    select.value = "";
    return;
  }
  ensureSelectHasActivityOption(select, activityId);
  select.value = String(activityId);
}

function buildDisplayLabel(text, className) {
  const label = document.createElement("div");
  label.className = className;
  label.textContent = text;
  return label;
}

function scheduledActivityIdForHour(personId, hour) {
  const serverDefault = scheduledDefaultActivityId(personId, hour);
  if (serverDefault != null) return serverDefault;
  if (!isScheduledHour(personId, hour)) return null;
  const person = personById(personId);
  return homeActivityIdForPerson(person);
}

function effectiveActivityIdForRange(personId, hour, minuteStart, minuteEnd) {
  const segment = currentSegment(personId, hour, minuteStart, minuteEnd);
  if (segment.activity_id != null) return segment.activity_id;

  const scheduledActivityId = scheduledActivityIdForHour(personId, hour);
  if (scheduledActivityId != null && !segment.empty_override) {
    return scheduledActivityId;
  }
  return null;
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
  if (isSplitHour(segments)) {
    const first = effectiveActivityIdForRange(personId, hour, 0, 30);
    const second = effectiveActivityIdForRange(personId, hour, 30, 60);
    return first != null && first === second ? first : null;
  }
  return effectiveActivityIdForRange(personId, hour, 0, 60);
}

function effectiveActivityIdForFocus() {
  if (!state.focusedCell) return null;
  const { personId, hour, minuteStart, minuteEnd } = state.focusedCell;
  return effectiveActivityIdForRange(personId, hour, minuteStart, minuteEnd);
}

function openSelectPicker(select) {
  if (!select) return;
  try {
    select.focus({ preventScroll: true });
  } catch (e) {
    select.focus();
  }
  try {
    if (typeof select.showPicker === "function") {
      select.showPicker();
      return;
    }
  } catch (e) {}
  try {
    select.click();
  } catch (e) {}
}

function openFullHourSelect(e, td) {
  e.preventDefault();
  e.stopPropagation();
  if (scheduleIsReadOnly()) {
    focusSegment(td, td, 0, 60);
    showReadOnlyToast();
    return;
  }
  if (isHourLocked(Number(td.dataset.personId), Number(td.dataset.hour))) {
    showLockedCellToast();
    return;
  }
  focusSegment(td, td, 0, 60);
  const select = td.querySelector("select.cell-select");
  setTimeout(() => openSelectPicker(select), 0);
}

function openSplitSegmentSelect(e, td, part, minuteStart, minuteEnd) {
  e.preventDefault();
  e.stopPropagation();
  if (scheduleIsReadOnly()) {
    focusSegment(td, part, minuteStart, minuteEnd);
    showReadOnlyToast();
    return;
  }
  if (isRangeLocked(Number(td.dataset.personId), Number(td.dataset.hour), minuteStart, minuteEnd)) {
    showLockedCellToast();
    return;
  }
  focusSegment(td, part, minuteStart, minuteEnd);
  const select = part.querySelector("select.half-select");
  setTimeout(() => openSelectPicker(select), 0);
}

function toggleFullHourSplitFromEvent(e, td) {
  e.preventDefault();
  e.stopPropagation();
  if (scheduleIsReadOnly()) {
    focusSegment(td, td, 0, 60);
    showReadOnlyToast();
    return;
  }
  if (isHourLocked(Number(td.dataset.personId), Number(td.dataset.hour))) {
    showLockedCellToast();
    return;
  }
  focusSegment(td, td, 0, 60);
  void toggleHourSplit(td, 0);
}

function toggleSplitSegmentFromEvent(e, td, part, minuteStart, minuteEnd) {
  e.preventDefault();
  e.stopPropagation();
  if (scheduleIsReadOnly()) {
    focusSegment(td, part, minuteStart, minuteEnd);
    showReadOnlyToast();
    return;
  }
  if (isHourLocked(Number(td.dataset.personId), Number(td.dataset.hour))) {
    showLockedCellToast();
    return;
  }
  focusSegment(td, part, minuteStart, minuteEnd);
  void toggleHourSplit(td, minuteStart);
}

function splitPartFromEvent(td, e) {
  const directPart = e.target.closest?.(".hour-segment");
  if (directPart && td.contains(directPart)) return directPart;

  return splitPartFromPoint(td, e.clientX, e.clientY);
}

function splitPartFromPoint(td, clientX, clientY) {
  const pointEl = document.elementFromPoint(clientX, clientY);
  const pointPart = pointEl?.closest?.(".hour-segment");
  if (pointPart && td.contains(pointPart)) return pointPart;

  const parts = Array.from(td.querySelectorAll(".hour-segment"));
  if (parts.length <= 1) return parts[0] || null;

  const rect = td.getBoundingClientRect();
  return clientX >= rect.left + (rect.width / 2) ? parts[1] : parts[0];
}

function rangeFromSegmentPart(part) {
  if (!part) return null;
  return {
    minute_start: Number(part.dataset.minuteStart),
    minute_end: Number(part.dataset.minuteEnd),
  };
}

function targetRangeFromPoint(td, clientX, clientY) {
  if (!td || td.dataset.split !== "1") return { ...FULL_SEGMENT };
  return rangeFromSegmentPart(splitPartFromPoint(td, clientX, clientY)) || { ...HALF_SEGMENTS[0] };
}

function dragCellKeyForTd(td) {
  return `${td.dataset.personId}:${td.dataset.hour}`;
}

function activityIdForDragSource(td, minuteStart, minuteEnd) {
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  return effectiveActivityIdForRange(personId, hour, minuteStart, minuteEnd);
}

function armFullHourDrag(td, event) {
  if (scheduleIsReadOnly()) return;
  if (event.button !== 0) return;
  if (td.dataset.split === "1") return;
  startPendingDrag(td, event, 0, 60);
}

function armHalfHourDrag(td, minuteStart, minuteEnd, event) {
  if (scheduleIsReadOnly()) return;
  if (event.button !== 0) return;
  startPendingDrag(td, event, minuteStart, minuteEnd);
}

function resetRenderedHourState(td) {
  td.classList.remove("split-hour", "scheduled-empty", "base-value", "with-display-label", "locked-cell");
  td.style.background = "#fff";
  td.dataset.isBase = "";
  td.title = "";
}

function renderFullHourCell(td, segment, isScheduled) {
  td.dataset.split = "0";
  resetRenderedHourState(td);
  td.oncontextmenu = (e) => openFullHourSelect(e, td);

  const personId = Number(td.dataset.personId);
  const hasExplicitSegment = !!segment;
  const explicitActivityId = hasExplicitSegment ? segment.activity_id : null;
  const explicitEmptyOverride = !!segment?.empty_override;
  const scheduledActivityId = isScheduled ? scheduledActivityIdForHour(personId, Number(td.dataset.hour)) : null;
  const showScheduledDefault = explicitActivityId == null && !explicitEmptyOverride && scheduledActivityId != null;
  const locked = isForeignLockedSegment(segment);
  if (locked) {
    td.classList.add("locked-cell");
    td.title = "Låst av annan användare";
  }

  if (explicitActivityId != null) {
    td.style.background = colorFor(explicitActivityId);
  } else if (showScheduledDefault) {
    td.style.background = colorFor(scheduledActivityId);
    td.dataset.isBase = "1";
  } else if (isScheduled) {
    if (scheduledActivityId) {
      // Explicit tömd: subtilt randig version av hemaktivitetens färg
      const c = colorFor(scheduledActivityId);
      td.style.background = `repeating-linear-gradient(45deg, ${c}40 0, ${c}40 2px, var(--surface) 2px, var(--surface) 10px)`;
    } else {
      td.style.background = "";
      td.classList.add("scheduled-empty");
    }
  }

  const select = buildActivitySelect([explicitActivityId, scheduledActivityId]);
  select.className = "cell-select";
  const selectedActivityId = explicitActivityId != null
    ? explicitActivityId
    : (showScheduledDefault ? scheduledActivityId : null);
  setSelectActivityValue(select, selectedActivityId);
  select.dataset.minuteStart = "0";
  select.dataset.minuteEnd = "60";
  select.dataset.version = String(segment?.version || 0);
  select.disabled = locked || scheduleIsReadOnly();

  select.addEventListener("change", () => onSegmentChange(td, 0, 60));
  select.addEventListener("focus", () => focusSegment(td, td, 0, 60));
  select.addEventListener("mousedown", (e) => {
    armFullHourDrag(td, e);
    e.stopPropagation();
    if (e.button === 0) e.preventDefault();
    const isFocused = state.focusedCell
      && state.focusedCell.td === td
      && state.focusedCell.minuteStart === 0
      && state.focusedCell.minuteEnd === 60;
    if (!isFocused) {
      focusSegment(td, td, 0, 60);
    }
  });
  select.addEventListener("keydown", (e) => handleSelectClipboardKeys(e), true);
  select.addEventListener("contextmenu", (e) => openFullHourSelect(e, td), true);

  td.appendChild(select);
  if (showScheduledDefault && scheduledActivityId != null) {
    td.classList.add("with-display-label");
    td.appendChild(buildDisplayLabel(activityLabel(scheduledActivityId), "cell-display-label"));
  }
}

function renderSplitHourCell(td, segments, isScheduled) {
  td.dataset.split = "1";
  resetRenderedHourState(td);
  td.classList.add("split-hour");
  td.oncontextmenu = (e) => {
    const part = splitPartFromEvent(td, e);
    if (!part) return;
    openSplitSegmentSelect(
      e,
      td,
      part,
      Number(part.dataset.minuteStart),
      Number(part.dataset.minuteEnd),
    );
  };

  const wrapper = document.createElement("div");
  wrapper.className = "hour-split";
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  const scheduledActivityId = isScheduled ? scheduledActivityIdForHour(personId, hour) : null;
  if (segments.some((segment) => isForeignLockedSegment(segment))) {
    td.classList.add("locked-cell");
    td.title = "En eller flera halvtimmar är låsta av annan användare";
  }

  HALF_SEGMENTS.forEach(({ minute_start, minute_end }) => {
    const segment = currentSegment(personId, hour, minute_start, minute_end);
    const part = document.createElement("div");
    part.className = "hour-segment";
    part.dataset.minuteStart = String(minute_start);
    part.dataset.minuteEnd = String(minute_end);
    part.tabIndex = -1;
    const locked = isForeignLockedSegment(segment);
    if (locked) {
      part.classList.add("locked-cell");
      part.title = "Låst av annan användare";
    }

    if (segment.activity_id != null) {
      part.style.background = colorFor(segment.activity_id);
    } else if (!segment.empty_override && scheduledActivityId != null) {
      part.style.background = colorFor(scheduledActivityId);
    } else if (isScheduled) {
      if (scheduledActivityId) {
        const c = colorFor(scheduledActivityId);
        part.style.background = `repeating-linear-gradient(45deg, ${c}40 0, ${c}40 2px, var(--surface) 2px, var(--surface) 8px)`;
      } else {
        part.style.background = "";
        part.classList.add("scheduled-empty-half");
      }
    } else {
      part.style.background = "#fff";
    }

    const select = buildActivitySelect([segment.activity_id, scheduledActivityId]);
    select.className = "half-select";
    const selectedActivityId = segment.activity_id != null
      ? segment.activity_id
      : (!segment.empty_override && scheduledActivityId != null ? scheduledActivityId : null);
    setSelectActivityValue(select, selectedActivityId);
    select.dataset.minuteStart = String(minute_start);
    select.dataset.minuteEnd = String(minute_end);
    select.dataset.version = String(segment.version || 0);
    select.disabled = locked || scheduleIsReadOnly();

    select.addEventListener("change", () => onSegmentChange(td, minute_start, minute_end));
    select.addEventListener("focus", () => focusSegment(td, part, minute_start, minute_end));
    select.addEventListener("mousedown", (e) => {
      armHalfHourDrag(td, minute_start, minute_end, e);
      e.stopPropagation();
      if (e.button === 0) e.preventDefault();
      const isFocused = state.focusedCell
        && state.focusedCell.td === td
        && state.focusedCell.minuteStart === minute_start
        && state.focusedCell.minuteEnd === minute_end;
      if (!isFocused) {
        focusSegment(td, part, minute_start, minute_end);
      }
    });
    select.addEventListener("keydown", (e) => handleSelectClipboardKeys(e), true);
    part.addEventListener(
      "contextmenu",
      (e) => openSplitSegmentSelect(e, td, part, minute_start, minute_end),
      true,
    );
    select.addEventListener(
      "contextmenu",
      (e) => openSplitSegmentSelect(e, td, part, minute_start, minute_end),
      true,
    );

    part.appendChild(select);
    if (segment.activity_id == null && !segment.empty_override && scheduledActivityId != null) {
      part.classList.add("with-display-label");
      part.appendChild(buildDisplayLabel(activityLabel(scheduledActivityId), "hour-segment-label"));
    }
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
    if (td.classList.contains("pending-save")) setHourPending(td, true);
    return;
  }

  const segment = segments.length === 1 ? segments[0] : null;
  renderFullHourCell(td, segment, isScheduled);
  if (td.classList.contains("pending-save")) setHourPending(td, true);
}

function buildRows() {
  const body = document.getElementById("scheduleBody");
  const fragment = document.createDocumentFragment();
  state.focusedCell = null;

  state.persons.forEach((person, rowIndex) => {
    const tr = document.createElement("tr");
    tr.dataset.personId = person.id;
    tr.dataset.rowIndex = rowIndex;

    const name = document.createElement("td");
    name.className = "name";
    name.textContent = person.name;
    setupPersonOrderNameCell(name, person);
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

    fragment.appendChild(tr);
  });

  body.replaceChildren(fragment);
}

function clearSummaryRefreshTimer() {
  if (!summaryState.timer) return;
  clearTimeout(summaryState.timer);
  summaryState.timer = null;
}

function setSummaryLoading(loading) {
  const card = document.querySelector(".summary-card");
  if (!card) return;
  card.classList.toggle("loading", loading);
  card.setAttribute("aria-busy", loading ? "true" : "false");
}

function cancelSummaryRefresh({ abortInFlight = false } = {}) {
  clearSummaryRefreshTimer();
  if (!abortInFlight || !summaryState.controller) return;
  summaryState.controller.abort();
  summaryState.controller = null;
  setSummaryLoading(false);
}

function scheduleCalculatorRender() {
  if (summaryState.calcFrame) cancelAnimationFrame(summaryState.calcFrame);
  summaryState.calcFrame = requestAnimationFrame(() => {
    summaryState.calcFrame = 0;
    renderCalculator();
  });
}

function renderSummaryRows(rows) {
  const tbody = document.getElementById("summaryBody");
  if (!tbody) return;

  const fragment = document.createDocumentFragment();
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td style="background: ${row.color}; padding: 5px;">${escapeHtml(row.activity_label)}</td>
      <td>${formatHours(row.hours)}</td>
      <td>${Number(row.persons_equiv).toFixed(1)}</td>`;
    fragment.appendChild(tr);
  });
  tbody.replaceChildren(fragment);
}

function notifySummaryRefreshError(message) {
  const now = Date.now();
  if (now - summaryState.errorToastAt < 5000) return;
  summaryState.errorToastAt = now;
  showToast(message, "warn");
}

function compactSummaryErrorReason(error) {
  const status = Number(error?.status || 0);
  let reason = String(error?.message || "").replace(/\s+/g, " ").trim();
  if (!reason) reason = status ? `HTTP ${status}` : "Okänt fel";
  if (status && !reason.includes(String(status))) reason = `HTTP ${status}: ${reason}`;
  return reason.length > 180 ? `${reason.slice(0, 177)}...` : reason;
}

function summaryRefreshContextLabel() {
  const day = DAYS[state.weekday] || `dag ${state.weekday}`;
  const areaName = state.areaId == null ? "Alla områden" : (areaById(state.areaId)?.name || `område ${state.areaId}`);
  return `${day}, vecka ${state.week}/${state.year}, ${areaName}`;
}

function summaryRefreshErrorMessage(error) {
  return `Summeringen kunde inte uppdateras just nu. Orsak: ${compactSummaryErrorReason(error)}. Kontext: ${summaryRefreshContextLabel()}.`;
}

function scheduleSummaryRefresh(delay = 90) {
  clearSummaryRefreshTimer();
  summaryState.timer = setTimeout(() => {
    summaryState.timer = null;
    void refreshSummary();
  }, delay);
}

async function onSegmentChange(td, minuteStart, minuteEnd) {
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  if (scheduleIsReadOnly()) {
    showReadOnlyToast();
    renderHourCell(td);
    return;
  }
  if (isRangeLocked(personId, hour, minuteStart, minuteEnd)) {
    showLockedCellToast();
    renderHourCell(td);
    return;
  }
  const segment = currentSegment(personId, hour, minuteStart, minuteEnd);
  const undoSnapshot = snapshotHour(personId, hour);
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
    invalidateScheduleAllCache();
    pushScheduleUndo("celländring", [undoSnapshot]);
    replaceHourSegments(personId, hour, [...others, updated]);
    renderHourCell(td);
    focusMatchingSegment(td, minuteStart, minuteEnd);
    scheduleSummaryRefresh();
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

async function toggleHourSplit(td, mergeMinuteStart = 0) {
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  if (scheduleIsReadOnly()) {
    showReadOnlyToast();
    return;
  }
  if (isHourLocked(personId, hour)) {
    showLockedCellToast();
    return;
  }
  const currentSegments = sortSegments(segmentsForHour(personId, hour));
  const undoSnapshot = snapshotHour(personId, hour);

  try {
    const resp = await api.put("/api/schedule/cell/split", {
      year: state.year,
      week: state.week,
      weekday: state.weekday,
      hour,
      person_id: personId,
      merge_minute_start: mergeMinuteStart,
      segments: currentSegments.map((segment) => ({
        minute_start: segment.minute_start,
        minute_end: segment.minute_end,
        expected_version: segment.version,
      })),
    });
    const updatedSegments = resp.segments || [];
    invalidateScheduleAllCache();
    pushScheduleUndo(isSplitHour(updatedSegments) ? "dela timme" : "slå ihop timme", [undoSnapshot]);
    replaceHourSegments(personId, hour, updatedSegments);
    renderHourCell(td);
    if (isSplitHour(updatedSegments)) {
      focusMatchingSegment(td, 0, 30);
      showToast("Cellen delades i två halvtimmar.");
    } else {
      focusMatchingSegment(td, 0, 60);
      showToast("Cellen slogs ihop till en hel timme.");
    }
    scheduleSummaryRefresh();
  } catch (err) {
    if (err.status === 409) {
      showToast("Cellen ändrades av någon annan – läste in på nytt", "warn");
      await loadSchedule();
    } else {
      showToast("Kunde inte ändra delningen: " + err.message, "error");
    }
  }
}

function clipboardLabel(activityId) {
  const a = activityById(activityId);
  return a ? a.label : "(tom)";
}

async function copyFocused(cut = false) {
  if (!state.focusedCell) return;
  if (cut && scheduleIsReadOnly()) {
    showReadOnlyToast();
    return;
  }
  const activityId = effectiveActivityIdForFocus();
  state.clipboard = { activity_id: activityId };
  state.focusedCell.focusEl.classList.add("clipboard-flash");
  setTimeout(() => state.focusedCell?.focusEl?.classList.remove("clipboard-flash"), 500);

  if (cut && activityId != null) {
    const { td, personId, hour, minuteStart, minuteEnd } = state.focusedCell;
    if (isRangeLocked(personId, hour, minuteStart, minuteEnd)) {
      showLockedCellToast();
      return;
    }
    const segment = currentSegment(personId, hour, minuteStart, minuteEnd);
    const undoSnapshot = snapshotHour(personId, hour);
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
      invalidateScheduleAllCache();
      pushScheduleUndo("klipp ut", [undoSnapshot]);
      replaceHourSegments(personId, hour, [...others, resp.cell]);
      renderHourCell(td);
      focusMatchingSegment(td, minuteStart, minuteEnd);
      scheduleSummaryRefresh();
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
  if (scheduleIsReadOnly()) {
    showReadOnlyToast();
    return;
  }
  const { td, personId, hour, minuteStart, minuteEnd } = state.focusedCell;
  if (isRangeLocked(personId, hour, minuteStart, minuteEnd)) {
    showLockedCellToast();
    return;
  }
  const segment = currentSegment(personId, hour, minuteStart, minuteEnd);
  const undoSnapshot = snapshotHour(personId, hour);
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
    invalidateScheduleAllCache();
    pushScheduleUndo("klistra in", [undoSnapshot]);
    replaceHourSegments(personId, hour, [...others, resp.cell]);
    renderHourCell(td);
    focusMatchingSegment(td, minuteStart, minuteEnd);
    scheduleSummaryRefresh();
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
  if (!["c", "x", "v", "z", "y"].includes(key)) return;
  e.preventDefault();
  e.stopPropagation();
  if (scheduleIsReadOnly() && key !== "c") {
    showReadOnlyToast();
    return;
  }
  if (key === "z") {
    if (e.shiftKey) void redoLastScheduleAction();
    else void undoLastScheduleAction();
    return;
  }
  if (key === "y") {
    void redoLastScheduleAction();
    return;
  }
  if (!state.focusedCell) return;
  if (key === "c") copyFocused(false);
  else if (key === "x") copyFocused(true);
  else if (key === "v") pasteFocused();
}

function setupKeyboard() {
  const handler = (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    const key = e.key.toLowerCase();
    if (!["c", "x", "v", "z", "y"].includes(key)) return;

    const active = document.activeElement;
    if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.isContentEditable)) return;
    if (key === "z") {
      e.preventDefault();
      e.stopPropagation();
      if (scheduleIsReadOnly()) {
        showReadOnlyToast();
        return;
      }
      if (e.shiftKey) void redoLastScheduleAction();
      else void undoLastScheduleAction();
      return;
    }
    if (key === "y") {
      e.preventDefault();
      e.stopPropagation();
      if (scheduleIsReadOnly()) {
        showReadOnlyToast();
        return;
      }
      void redoLastScheduleAction();
      return;
    }
    if (!state.focusedCell) {
      showToast(`Ctrl+${key.toUpperCase()}: klicka först på en cell`, "warn");
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    if (scheduleIsReadOnly() && key !== "c") {
      showReadOnlyToast();
      return;
    }
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

function dragTargetTdsInRect() {
  const { r0, r1, c0, c1 } = getDragRect();
  return Array.from(document.querySelectorAll("#scheduleBody td[data-row-index]")).filter((td) => {
    const r = Number(td.dataset.rowIndex);
    const c = Number(td.dataset.colIndex);
    return r >= r0 && r <= r1 && c >= c0 && c <= c1;
  });
}

function updateDragTargets() {
  document.querySelectorAll("#scheduleBody td.drag-target").forEach((t) => t.classList.remove("drag-target"));
  document.querySelectorAll("#scheduleBody .hour-segment.drag-target-segment").forEach((t) => t.classList.remove("drag-target-segment"));
  if (!drag.active) return;
  const targets = dragTargetTdsInRect();
  const isAreaCopy = targets.filter((td) => td !== drag.sourceTd).length > 1;
  targets.forEach((td) => {
    td.classList.add("drag-target");
    if (td.dataset.split !== "1") return;
    if (isAreaCopy) {
      td.querySelectorAll(".hour-segment").forEach((part) => part.classList.add("drag-target-segment"));
      return;
    }
    const range = drag.targetRangesByCell.get(dragCellKeyForTd(td));
    if (range) {
      const part = td.querySelector(
        `.hour-segment[data-minute-start="${range.minute_start}"][data-minute-end="${range.minute_end}"]`
      );
      part?.classList.add("drag-target-segment");
    }
  });
}

function resetDragState() {
  document.body.classList.remove("dragging");
  drag.sourceTd?.classList.remove("drag-source-cell");
  document.querySelectorAll("#scheduleBody td.drag-target").forEach((t) => t.classList.remove("drag-target"));
  document.querySelectorAll("#scheduleBody .hour-segment.drag-target-segment").forEach((t) => t.classList.remove("drag-target-segment"));
  drag.active = false;
  drag.pending = false;
  drag.sourceTd = null;
  drag.sourceActivityId = null;
  drag.sourceMinuteStart = 0;
  drag.sourceMinuteEnd = 60;
  drag.sourceRow = -1;
  drag.sourceCol = -1;
  drag.currentRow = -1;
  drag.currentCol = -1;
  drag.currentTargetMinuteStart = 0;
  drag.currentTargetMinuteEnd = 60;
  drag.targetRangesByCell = new Map();
  drag.startX = 0;
  drag.startY = 0;
}

function startPendingDrag(td, event, minuteStart = 0, minuteEnd = 60) {
  if (scheduleIsReadOnly()) return;
  drag.pending = true;
  drag.sourceTd = td;
  drag.sourceActivityId = activityIdForDragSource(td, minuteStart, minuteEnd);
  drag.sourceMinuteStart = minuteStart;
  drag.sourceMinuteEnd = minuteEnd;
  drag.sourceRow = Number(td.dataset.rowIndex);
  drag.sourceCol = Number(td.dataset.colIndex);
  drag.currentRow = drag.sourceRow;
  drag.currentCol = drag.sourceCol;
  drag.currentTargetMinuteStart = minuteStart;
  drag.currentTargetMinuteEnd = minuteEnd;
  drag.targetRangesByCell = new Map();
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

function targetSegmentsForDragTarget(td, targetRangesByCell, fallbackTargetRange, sourceMinuteStart, isAreaCopy) {
  if (td.dataset.split !== "1") {
    return [{ ...FULL_SEGMENT }];
  }
  if (isAreaCopy) {
    return HALF_SEGMENTS.map((segment) => ({ ...segment }));
  }

  const sourceHalfFallback = sourceMinuteStart >= 30 ? HALF_SEGMENTS[1] : HALF_SEGMENTS[0];
  const fallbackRange = fallbackTargetRange
    && fallbackTargetRange.minute_end - fallbackTargetRange.minute_start === 30
    ? fallbackTargetRange
    : sourceHalfFallback;
  const range = targetRangesByCell.get(dragCellKeyForTd(td)) || fallbackRange;
  return [{ minute_start: range.minute_start, minute_end: range.minute_end }];
}

async function finishDrag() {
  if (!drag.active) return;
  if (scheduleIsReadOnly()) {
    resetDragState();
    showReadOnlyToast();
    return;
  }
  const sourceTd = drag.sourceTd;
  const sourceActivityId = drag.sourceActivityId;
  const sourceMinuteStart = drag.sourceMinuteStart;
  const sourceMinuteEnd = drag.sourceMinuteEnd;
  const targets = Array.from(document.querySelectorAll("#scheduleBody td.drag-target"));
  const targetRangesByCell = new Map(drag.targetRangesByCell);
  const fallbackTargetRange = {
    minute_start: drag.currentTargetMinuteStart,
    minute_end: drag.currentTargetMinuteEnd,
  };
  const targetCount = targets.filter((td) => td !== sourceTd).length;
  const sourceIsSplit = sourceTd?.dataset.split === "1";
  const isAreaCopy = targetCount > 1;
  resetDragState();

  if (targets.length === 0 || (targets.length === 1 && targets[0] === sourceTd && !sourceIsSplit)) return;

  const editableTargets = targets.filter((td) =>
    (td !== sourceTd || sourceIsSplit) && !isHourLocked(Number(td.dataset.personId), Number(td.dataset.hour))
  );
  const lockedTargetCount = targets.filter((td) =>
    (td !== sourceTd || sourceIsSplit) && isHourLocked(Number(td.dataset.personId), Number(td.dataset.hour))
  ).length;
  if (!editableTargets.length) {
    if (lockedTargetCount) showLockedCellToast();
    return;
  }

  const cells = targets
    .filter((td) => editableTargets.includes(td))
    .flatMap((td) => {
      const personId = Number(td.dataset.personId);
      const hour = Number(td.dataset.hour);
      const segments = sortSegments(segmentsForHour(personId, hour));
      const fullSegment = segments.length === 1
        && segments[0].minute_start === 0
        && segments[0].minute_end === 60
        ? segments[0]
        : null;
      const targetSegments = targetSegmentsForDragTarget(
        td,
        targetRangesByCell,
        fallbackTargetRange,
        sourceMinuteStart,
        isAreaCopy,
      );

      return targetSegments
        .filter(({ minute_start, minute_end }) =>
          td !== sourceTd || minute_start !== sourceMinuteStart || minute_end !== sourceMinuteEnd
        )
        .map(({ minute_start, minute_end }) => {
          const matching = segments.find(
            (segment) => segment.minute_start === minute_start && segment.minute_end === minute_end
          );
          const expectedVersion = matching
            ? Number(matching.version) || 0
            : (fullSegment ? Number(fullSegment.version) || 0 : 0);
          return {
            year: state.year,
            week: state.week,
            weekday: state.weekday,
            hour,
            minute_start,
            minute_end,
            person_id: personId,
            activity_id: sourceActivityId,
            expected_version: expectedVersion,
          };
        });
    });

  if (cells.length === 0) return;
  if (cells.length > 200) {
    showToast("För många celler eller halvor (max 200)", "error");
    return;
  }

  const snapshots = snapshotHoursFromCells(cells);
  const optimisticByHour = new Map();
  cells.forEach((cell) => {
    const key = hourKey(cell.person_id, cell.hour);
    if (!optimisticByHour.has(key)) optimisticByHour.set(key, []);
    optimisticByHour.get(key).push(cell);
  });
  optimisticByHour.forEach((items, key) => {
    const [personId, hour] = key.split(":").map(Number);
    replaceHourSegments(personId, hour, optimisticSegmentsForHour(personId, hour, items));
    const td = getHourTd(personId, hour);
    if (!td) return;
    setHourPending(td, true);
    renderHourCell(td);
  });

  try {
    const resp = await api.post("/api/schedule/cells", { cells, atomic: true, action: "drag_fill" });
    invalidateScheduleAllCache();
    pushScheduleUndo("drag-fyll", snapshots);
    applySegmentsByHourResponse(resp.applied);
    scheduleSummaryRefresh(0);
    showToast(
      lockedTargetCount
        ? `Fyllde ${cells.length} celler eller halvor, hoppade över ${lockedTargetCount} låsta`
        : `Fyllde ${cells.length} celler eller halvor`
    );
  } catch (e) {
    restoreHourSnapshots(snapshots);
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
    if (scheduleIsReadOnly()) return;
    if (e.target.closest("select")) return;
    const td = e.target.closest("td[data-hour]");
    if (!td) return;
    const part = e.target.closest(".hour-segment");
    if (part) {
      startPendingDrag(td, e, Number(part.dataset.minuteStart), Number(part.dataset.minuteEnd));
      return;
    }
    if (td.dataset.split === "1") return;
    startPendingDrag(td, e, 0, 60);
  });

  body.addEventListener("contextmenu", (e) => {
    const td = e.target.closest("td[data-hour]");
    if (!td) return;
    if (td.dataset.split === "1") {
      const part = splitPartFromEvent(td, e);
      if (part) {
        openSplitSegmentSelect(
          e,
          td,
          part,
          Number(part.dataset.minuteStart),
          Number(part.dataset.minuteEnd),
        );
      }
      return;
    }
    openFullHourSelect(e, td);
  }, true);

  body.addEventListener("dblclick", (e) => {
    const td = e.target.closest("td[data-hour]");
    if (!td) return;
    if (td.dataset.split === "1") {
      const part = splitPartFromEvent(td, e);
      if (part) {
        toggleSplitSegmentFromEvent(
          e,
          td,
          part,
          Number(part.dataset.minuteStart),
          Number(part.dataset.minuteEnd),
        );
      }
      return;
    }
    toggleFullHourSplitFromEvent(e, td);
  }, true);

  document.addEventListener("mousemove", (e) => {
    if (!drag.pending && !drag.active) return;
    const moved = Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY);
    if (!drag.active) {
      if (moved < 5) return;
      activateDrag();
    }
    const td = scheduleCellFromPoint(e.clientX, e.clientY);
    if (!td) return;
    drag.currentRow = Number(td.dataset.rowIndex);
    drag.currentCol = Number(td.dataset.colIndex);
    const targetRange = targetRangeFromPoint(td, e.clientX, e.clientY);
    drag.currentTargetMinuteStart = targetRange.minute_start;
    drag.currentTargetMinuteEnd = targetRange.minute_end;
    if (td.dataset.split === "1") {
      drag.targetRangesByCell.set(dragCellKeyForTd(td), targetRange);
    }
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
  const filteredUrl = `/api/schedule/summary?year=${state.year}&week=${state.week}&weekday=${state.weekday}` +
    (state.areaId ? `&area_id=${state.areaId}` : "");
  const allUrl = `/api/schedule/summary?year=${state.year}&week=${state.week}&weekday=${state.weekday}`;
  const requestSeq = ++summaryState.requestSeq;
  summaryState.controller?.abort();
  const controller = new AbortController();
  summaryState.controller = controller;
  setSummaryLoading(true);

  try {
    const [rows, allRows] = await Promise.all([
      api.get(filteredUrl, { signal: controller.signal, cacheTtlMs: 15 * 1000 }),
      api.get(allUrl, { signal: controller.signal, cacheTtlMs: 15 * 1000 }),
    ]);
    if (controller.signal.aborted || requestSeq < summaryState.appliedSeq) return;
    summaryState.appliedSeq = requestSeq;
    state.summaryRows = rows;
    state.allSummaryRows = allRows;
    renderSummaryRows(rows);
    scheduleCalculatorRender();
  } catch (err) {
    if (err?.name === "AbortError") return;
    console.error("Kunde inte uppdatera summeringen", err);
    notifySummaryRefreshError(summaryRefreshErrorMessage(err));
  } finally {
    if (summaryState.controller === controller) {
      summaryState.controller = null;
      setSummaryLoading(false);
    }
  }
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

  if (typeof setAreaFocusAreas === "function") {
    setAreaFocusAreas(areas, state.currentUser);
  }
  state.areaId = preferredAreaIdForCurrentUser();
  setupCalculator();
}

function applyScheduleData(data) {
  state.allPersons = data.persons || [];
  state.lockForeignScheduleCells = !!data.lock_foreign_schedule_cells;
  refreshPersons();
  setAllSegments(data.cells || []);
  state.scheduledHours = {};
  Object.entries(data.scheduled_hours || {}).forEach(([pid, hours]) => {
    state.scheduledHours[Number(pid)] = new Set(hours);
  });
  state.scheduledDefaults = {};
  Object.entries(data.scheduled_defaults || {}).forEach(([pid, hours]) => {
    state.scheduledDefaults[Number(pid)] = new Map(
      Object.entries(hours || {}).map(([hour, activityId]) => [Number(hour), Number(activityId)])
    );
  });

  const areaName = state.areaId == null ? "Alla" : (state.areas.find((a) => a.id === state.areaId)?.name || "");
  document.getElementById("sectionTitle").textContent =
  `${DAYS[state.weekday]} – ${areaName} – V${state.week}/${state.year}`;

  buildRows();
  setupScheduleHorizontalScroll();
  refreshCurrentHourHighlight();
  scheduleSummaryRefresh(0);
  scheduleNextScheduleRevalidate();
}

function renderScheduleFromCache() {
  const baseKey = scheduleCacheKey();
  const cachedAll = scheduleAllCache.get(baseKey);
  const cached = cachedAll
    ? filterScheduleDataForArea(cachedAll, state.areaId)
    : scheduleAreaCache.get(scheduleAreaCacheKey(state.areaId, baseKey));
  if (!cached) return false;
  cancelSummaryRefresh({ abortInFlight: true });
  scheduleLoadState.controller?.abort();
  scheduleLoadState.requestSeq += 1;
  applyScheduleData(cached);
  scheduleNextScheduleRevalidate(500);
  return true;
}

async function prefetchAllSchedule() {
  const key = scheduleCacheKey();
  if (scheduleAllCache.has(key) || scheduleAllFetchState.key === key) return;
  scheduleAllFetchState.controller?.abort();
  const controller = new AbortController();
  scheduleAllFetchState.controller = controller;
  scheduleAllFetchState.key = key;
  try {
    const data = await api.get(scheduleUrl(null), { signal: controller.signal, cacheTtlMs: 25 * 1000 });
    if (controller.signal.aborted) return;
    const allData = filterScheduleDataForArea(data, null);
    setScheduleAllCache(key, allData);
    setScheduleAreaCache(scheduleAreaCacheKey(null, key), allData);
    scheduleNextScheduleRevalidate();
  } catch (err) {
    if (err?.name !== "AbortError") console.warn("Kunde inte forhämta hela bemanningen", err);
  } finally {
    if (scheduleAllFetchState.controller === controller) {
      scheduleAllFetchState.controller = null;
      scheduleAllFetchState.key = "";
    }
  }
}

async function revalidateSchedule() {
  if (document.hidden) return;
  if (scheduleIsBusyForBackgroundUpdate()) {
    scheduleNextScheduleRevalidate(SCHEDULE_REVALIDATE_SOON_MS);
    return;
  }

  const key = scheduleCacheKey();
  const cached = scheduleAllCache.get(key);
  if (!cached) {
    await prefetchAllSchedule();
    scheduleNextScheduleRevalidate();
    return;
  }
  const cachedPatch = patchScheduleFromAllData(cached);
  if (cachedPatch.skippedFocused) {
    scheduleNextScheduleRevalidate(SCHEDULE_REVALIDATE_SOON_MS);
    return;
  }
  notifyScheduleBackgroundUpdate(cachedPatch.patched ? 1 : 0);

  scheduleRevalidateState.controller?.abort();
  const controller = new AbortController();
  scheduleRevalidateState.controller = controller;
  try {
    const revision = await api.get(scheduleRevisionUrl(null), { signal: controller.signal });
    if (controller.signal.aborted || key !== scheduleCacheKey()) return;
    if (revision?.revision_key && revision.revision_key === cached.revision_key) {
      scheduleRevalidateState.errorCount = 0;
      scheduleNextScheduleRevalidate();
      return;
    }

    const fresh = await api.get(scheduleUrl(null), { signal: controller.signal, cacheTtlMs: 25 * 1000 });
    if (controller.signal.aborted || key !== scheduleCacheKey()) return;
    const freshAllData = filterScheduleDataForArea(fresh, null);
    setScheduleAllCache(key, freshAllData);
    setScheduleAreaCache(scheduleAreaCacheKey(null, key), freshAllData);
    const result = patchScheduleFromAllData(fresh);
    notifyScheduleBackgroundUpdate(result.patched ? 1 : 0);
    scheduleRevalidateState.errorCount = 0;
  } catch (err) {
    if (err?.name !== "AbortError") {
      scheduleRevalidateState.errorCount += 1;
      console.warn("Kunde inte kontrollera färsk bemanning", err);
    }
  } finally {
    if (scheduleRevalidateState.controller === controller) {
      scheduleRevalidateState.controller = null;
    }
    const backoff = Math.min(scheduleRevalidateState.errorCount, 3) * 10000;
    scheduleNextScheduleRevalidate(scheduleRevalidateDelay() + backoff);
  }
}

async function loadSchedule() {
  if (renderScheduleFromCache()) {
    void prefetchAllSchedule();
    return true;
  }
  cancelSummaryRefresh({ abortInFlight: true });
  const requestSeq = ++scheduleLoadState.requestSeq;
  scheduleLoadState.controller?.abort();
  const controller = new AbortController();
  scheduleLoadState.controller = controller;

  try {
    const requestedAreaId = state.areaId;
    const data = await api.get(scheduleUrl(null), { signal: controller.signal, cacheTtlMs: 25 * 1000 });
    if (controller.signal.aborted || requestSeq !== scheduleLoadState.requestSeq) return false;

    const baseKey = scheduleCacheKey();
    const allData = filterScheduleDataForArea(data, null);
    const cachedData = filterScheduleDataForArea(data, requestedAreaId);
    setScheduleAllCache(baseKey, allData);
    setScheduleAreaCache(scheduleAreaCacheKey(null, baseKey), allData);
    setScheduleAreaCache(scheduleAreaCacheKey(requestedAreaId, baseKey), cachedData);
    applyScheduleData(cachedData);
    return true;
  } catch (err) {
    if (err?.name === "AbortError") return false;
    throw err;
  } finally {
    if (scheduleLoadState.controller === controller) {
      scheduleLoadState.controller = null;
    }
  }
}

(async () => {
  state.currentUser = await initPage("schedule", { requirePlanningView: true, denyRedirect: "/overblick.html" });
  if (!state.currentUser) return;
  applyScheduleReadOnlyMode();
  await loadAreasAndActivities();

  const stored = readSelectedDate();
  if (stored) {
    const [y, m, d] = stored;
    const { year, week, weekday } = isoWeek(new Date(Date.UTC(y, m - 1, d)));
    state.year = year;
    state.week = week;
    state.weekday = weekday;
  } else {
    const now = isoWeek();
    state.year = now.year;
    state.week = now.week;
    state.weekday = now.weekday;
  }

  const persistState = () => {
    const date = dateFromYWD(state.year, state.week, state.weekday);
    writeSelectedDate(date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate());
  };

  const syncDateInputFromState = () => {
    const date = dateFromYWD(state.year, state.week, state.weekday);
    const ymd = ymdString(date);
    const dateInput = document.getElementById("dateInput");
    const dateDisplay = document.getElementById("dateDisplayText");
    if (dateInput) dateInput.value = ymd;
    if (dateDisplay) dateDisplay.textContent = ymd;
  };

  const writeYWDToInputs = () => {
    document.getElementById("yearInput").value = state.year;
    document.getElementById("weekInput").value = state.week;
    document.getElementById("daySelect").value = String(state.weekday);
    syncDateInputFromState();
    persistState();
    refreshCurrentHourHighlight();
  };

  writeYWDToInputs();

  buildHeader();
  await loadSchedule();
  setupDrag();
  setupPersonOrderDrag();
  setupKeyboard();
  document.addEventListener("pointerdown", markScheduleActivity, { passive: true });
  document.addEventListener("keydown", markScheduleActivity, { passive: true });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      clearTimeout(scheduleRevalidateState.timer);
      scheduleRevalidateState.controller?.abort();
      return;
    }
    markScheduleActivity();
    scheduleNextScheduleRevalidate(SCHEDULE_REVALIDATE_SOON_MS);
  });

  const onControlChange = async () => {
    markScheduleActivity();
    state.year = Number(document.getElementById("yearInput").value) || state.year;
    state.week = Number(document.getElementById("weekInput").value) || state.week;
    state.weekday = Number(document.getElementById("daySelect").value);
    syncCalculatorWithSelectedArea();
    syncDateInputFromState();
    persistState();
    refreshCurrentHourHighlight();
    await loadSchedule();
  };

  const onDateChange = async () => {
    markScheduleActivity();
    const date = dateFromYmd(document.getElementById("dateInput").value);
    if (!date) return;
    const { year, week, weekday } = isoWeek(date);
    state.year = year;
    state.week = week;
    state.weekday = weekday;
    writeYWDToInputs();
    await loadSchedule();
  };

  const stepDay = async (delta) => {
    markScheduleActivity();
    const date = dateFromYWD(state.year, state.week, state.weekday);
    date.setUTCDate(date.getUTCDate() + delta);
    const { year, week, weekday } = isoWeek(date);
    state.year = year;
    state.week = week;
    state.weekday = weekday;
    writeYWDToInputs();
    await loadSchedule();
  };

  document.getElementById("yearInput").addEventListener("change", onControlChange);
  document.getElementById("weekInput").addEventListener("change", onControlChange);
  document.getElementById("daySelect").addEventListener("change", onControlChange);
  window.addEventListener("flow:areaFocusChanged", async () => {
    markScheduleActivity();
    state.areaId = preferredAreaIdForCurrentUser();
    syncCalculatorWithSelectedArea();
    await loadSchedule();
  });
  document.getElementById("dateInput").addEventListener("change", onDateChange);
  document.getElementById("prevDayBtn").addEventListener("click", () => stepDay(-1));
  document.getElementById("nextDayBtn").addEventListener("click", () => stepDay(1));

  document.getElementById("clearBtn").addEventListener("click", async () => {
    if (scheduleIsReadOnly()) {
      showReadOnlyToast();
      return;
    }
    const undoSnapshots = snapshotAllExplicitHours();
    if (!confirm("Rensa hela dagen för det valda området?")) return;
    try {
      const r = await api.post("/api/schedule/clear", {
        year: state.year,
        week: state.week,
        weekday: state.weekday,
        area_id: state.areaId,
      });
      invalidateScheduleAllCache();
      if (r.cleared) pushScheduleUndo("rensa dag", undoSnapshots);
      showToast(`Rensade ${r.cleared} celler`);
      await loadSchedule();
    } catch (e) {
      showToast("Fel: " + e.message, "error");
    }
  });

  document.getElementById("copyBtn").addEventListener("click", () => {
    if (scheduleIsReadOnly()) {
      showReadOnlyToast();
      return;
    }
    openCopyModal();
  });
  if (typeof setupPresencePrintButton === "function") {
    setupPresencePrintButton("presenceBtn", {
      getSelection: () => ({
        year: state.year,
        week: state.week,
        weekday: state.weekday,
        areaId: state.areaId,
        areaName: state.areaId == null
          ? "Alla områden"
          : (state.areas.find((area) => area.id === state.areaId)?.name || "Nuvarande område"),
      }),
    });
  }
  document.getElementById("undoBtn").addEventListener("click", () => undoLastScheduleAction());
  document.getElementById("redoBtn").addEventListener("click", () => redoLastScheduleAction());
  updateUndoRedoButtons();

  document.getElementById("nameFilter").addEventListener("input", (e) => {
    state.nameFilter = e.target.value;
    refreshPersons();
    buildRows();
    setupScheduleHorizontalScroll();
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
      setupScheduleHorizontalScroll();
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
      <label class="modal-checkbox"><input id="cp-ow" type="checkbox" /> Skriv över befintliga celler i målet</label>
      <div class="actions">
        <button id="cp-cancel">Avbryt</button>
        <button id="cp-go" class="primary">Kopiera</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  document.getElementById("cp-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("cp-go").addEventListener("click", async () => {
    const copyPayload = {
      from_year: Number(document.getElementById("cp-fy").value),
      from_week: Number(document.getElementById("cp-fw").value),
      from_weekday: Number(document.getElementById("cp-fd").value),
      to_year: Number(document.getElementById("cp-ty").value),
      to_week: Number(document.getElementById("cp-tw").value),
      to_weekday: Number(document.getElementById("cp-td").value),
      area_id: state.areaId,
      overwrite: document.getElementById("cp-ow").checked,
    };
    try {
      const r = await api.post("/api/schedule/copy", copyPayload);
      invalidateScheduleAllCache();
      showToast(`Kopierade ${r.copied} celler`);
      backdrop.remove();
      if (targetMatchesCurrentDay(copyPayload.to_year, copyPayload.to_week, copyPayload.to_weekday)) {
        const undoSnapshots = snapshotHoursFromCells(r.applied || []);
        pushScheduleUndo("kopiera dag", undoSnapshots);
        applySegmentsByHourResponse(r.applied);
        scheduleSummaryRefresh(0);
      }
    } catch (e) {
      showToast("Fel: " + e.message, "error");
    }
  });
}

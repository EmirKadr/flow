// Bemanningsvy – matris person × timme.

const HOURS = Array.from({ length: 18 }, (_, i) => 6 + i);   // 6..23
const DAYS = { 1: "Måndag", 2: "Tisdag", 3: "Onsdag", 4: "Torsdag", 5: "Fredag", 6: "Lördag", 7: "Söndag" };
const FULL_SEGMENT = { minute_start: 0, minute_end: 60 };
const HALF_SEGMENTS = [
  { minute_start: 0, minute_end: 30 },
  { minute_start: 30, minute_end: 60 },
];
const DEFAULT_SPLIT_MINUTES = 30;
const DEFAULT_SPLIT_BOUNDARIES = {
  2: [30],
  3: [20, 40],
  4: [15, 30, 45],
};
const MIN_SPLIT_PARTS = 2;
const MAX_SPLIT_PARTS = 4;
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
  selectedPersonId: null,
  clipboard: null,
  nameFilter: "",
  sortKey: "sort_order",
  sortAsc: true,
  summaryRows: [],
  allSummaryRows: [],
  productivityReport: null,
  productivityByPersonId: new Map(),
  productivityKey: "",
  lockForeignScheduleCells: false,
  calcInputs: { manual: { rows: "", time: "", goal: "" } },
  calculatorProfile: { version: 1, calculators: [] },
  calculatorUsers: [],
  calculatorProcessOptions: [],
  calculatorImportSearch: "",
  automaticCalculatorResults: [],
  automaticCalculatorLoading: false,
  automaticCalculatorError: "",
  scheduleRevisionKey: "",
  activityCapacityVisible: false,
  activityCapacityLoading: false,
  activityCapacityError: "",
  activityCapacityKey: "",
  activityCapacity: { people: {}, activities: {} },
  activityCapacityActivityIds: null,
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

let scheduleLoanMenu = null;

const summaryState = {
  controller: null,
  timer: null,
  requestSeq: 0,
  appliedSeq: 0,
  errorToastAt: 0,
  calcFrame: 0,
};

const automaticCalculatorState = {
  timer: null,
  requestSeq: 0,
  loadedKey: "",
};
const activityCapacityState = {
  controller: null,
  requestSeq: 0,
  pressedKeys: new Set(),
  toggledWhilePressed: false,
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
const scheduleProductivityLoadState = {
  controller: null,
  key: "",
};
const SCHEDULE_ALL_CACHE_LIMIT = 4;
const SCHEDULE_AREA_CACHE_LIMIT = 24;
const SCHEDULE_REVALIDATE_ACTIVE_MS = 10000;
const SCHEDULE_REVALIDATE_IDLE_MS = 30000;
const SCHEDULE_REVALIDATE_SOON_MS = 1500;
const SCHEDULE_REVALIDATE_ACTIVE_WINDOW_MS = 60000;
const SCHEDULE_ACTIVITY_CAPACITY_VISIBLE_KEY = "flow-schedule-activity-capacity-visible";
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
  const selectedAreaCellPersonIds = new Set(
    cells
      .filter((cell) => {
        if (Number(cell.loan_area_id) === selectedAreaId) return true;
        const activity = activityById(Number(cell.activity_id));
        return activity && Number(activity.area_id) === selectedAreaId;
      })
      .map((cell) => Number(cell.person_id))
  );
  const visiblePersons = persons.filter((person) =>
    Number(person.home_area_id) === selectedAreaId
    || selectedAreaCellPersonIds.has(Number(person.id))
  );
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
    loan_area_id: segment.loan_area_id == null ? null : Number(segment.loan_area_id),
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
    normalized.loan_area_id ?? "",
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
  const previousRevisionKey = state.scheduleRevisionKey || "";
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
    scheduleSummaryRefresh(0, { refreshCalculator: true });
  }
  state.scheduleRevisionKey = data.revision_key || "";
  if (changedCount || state.scheduleRevisionKey !== previousRevisionKey) {
    scheduleAutomaticCalculatorRefresh(800);
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

function localYmdString(date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function selectedScheduleYmdString() {
  return ymdString(dateFromYWD(state.year, state.week, state.weekday));
}

function scheduleProductivityKey() {
  return `${scheduleScopeKey()}|${selectedScheduleYmdString()}`;
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
  while (header.children.length > 3) header.removeChild(header.lastChild);
  HOURS.forEach((h) => {
    const th = document.createElement("th");
    th.dataset.hour = h;
    th.textContent = String(h).padStart(2, "0") + ":00";
    header.appendChild(th);
  });
}

function currentHourIfToday() {
  const now = new Date();
  if (selectedScheduleYmdString() !== localYmdString(now)) return null;
  return now.getHours();
}

function scheduleCompletedProductivityCutoffMinute(reportDate) {
  const dateValue = reportDate || selectedScheduleYmdString();
  if (dateValue !== localYmdString()) return 24 * 60;
  return new Date().getHours() * 60;
}

function scheduleProductivityStatusClass(percent) {
  if (percent >= 100) return "good";
  if (percent >= 80) return "warn";
  return "low";
}

function scheduleCompletedProductivity(personReport, reportDate) {
  const cutoffMinute = scheduleCompletedProductivityCutoffMinute(reportDate);
  let points = 0;
  let expectedPoints = 0;
  (personReport?.time_cells || []).forEach((cell) => {
    if (cell?.kind !== "kpi") return;
    if (Number(cell?.end_minute || 0) > cutoffMinute) return;
    const expected = Number(cell?.expected_points || 0);
    if (expected <= 0) return;
    expectedPoints += expected;
    points += Number(cell?.points || 0);
  });
  if (expectedPoints <= 0) return null;
  const percent = Math.floor((points / expectedPoints) * 100);
  return {
    percent,
    points,
    expectedPoints,
    hours: expectedPoints / 100,
    status: scheduleProductivityStatusClass(percent),
  };
}

function buildScheduleProductivityMap(report) {
  const map = new Map();
  const reportDate = report?.date || selectedScheduleYmdString();
  (report?.people || []).forEach((person) => {
    const value = scheduleCompletedProductivity(person, reportDate);
    if (value) map.set(Number(person.person_id), value);
  });
  return map;
}

function buildScheduleProductivityMapFromSummary(summary) {
  const map = new Map();
  Object.values(summary?.people || {}).forEach((person) => {
    const percent = Number(person?.percent);
    if (!Number.isFinite(percent)) return;
    const planned = Number(person?.planned_kpi_points || 0);
    if (planned <= 0) return;
    map.set(Number(person.person_id), {
      percent,
      points: Number(person?.kpi_points || 0),
      expectedPoints: planned,
      hours: Number(person?.kpi_minutes || 0) / 60,
      status: scheduleProductivityStatusClass(percent),
    });
  });
  return map;
}

function updateScheduleProductivityCells() {
  document.querySelectorAll("#scheduleBody td.schedule-productivity[data-person-id]").forEach((td) => {
    const person = personById(Number(td.dataset.personId));
    renderScheduleProductivityCell(td, person);
  });
}

function refreshScheduleProductivityFromReport() {
  if (!state.productivityReport || state.productivityKey !== scheduleProductivityKey()) return;
  state.productivityByPersonId = buildScheduleProductivityMapFromSummary(state.productivityReport);
  updateScheduleProductivityCells();
}

function refreshCurrentHourHighlight() {
  const hour = currentHourIfToday();
  document.querySelectorAll("table.matrix .now-hour").forEach((el) => el.classList.remove("now-hour"));
  if (hour != null) {
    document.querySelectorAll(`table.matrix th[data-hour="${hour}"]`).forEach((el) => el.classList.add("now-hour"));
    document.querySelectorAll(`table.matrix td[data-hour="${hour}"]`).forEach((el) => el.classList.add("now-hour"));
  }
  refreshScheduleProductivityFromReport();
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

function readActivityCapacityVisible() {
  try {
    return localStorage.getItem(SCHEDULE_ACTIVITY_CAPACITY_VISIBLE_KEY) === "1";
  } catch (e) {
    return false;
  }
}

function writeActivityCapacityVisible(visible) {
  try {
    localStorage.setItem(SCHEDULE_ACTIVITY_CAPACITY_VISIBLE_KEY, visible ? "1" : "0");
  } catch (e) {}
}

function activityCapacityRequestKey() {
  return `${scheduleScopeKey()}|${state.year}|${state.week}|${state.weekday}`;
}

function normalizeActivityCapacityActivityIds(value) {
  if (value == null) return null;
  if (!Array.isArray(value)) return null;
  const ids = [];
  value.forEach((item) => {
    const id = Number(item);
    if (Number.isInteger(id) && id > 0 && !ids.includes(id)) ids.push(id);
  });
  return ids;
}

function activityCapacityActivityIsVisible(activityId) {
  if (state.activityCapacityActivityIds == null) return true;
  const id = Number(activityId);
  return Number.isInteger(id) && state.activityCapacityActivityIds.includes(id);
}

function updateActivityCapacityToggleButton() {
  const button = document.getElementById("capacityToggleBtn");
  if (!button) return;
  const active = !!state.activityCapacityVisible;
  button.classList.toggle("active", active);
  button.setAttribute("aria-pressed", active ? "true" : "false");
  button.setAttribute("aria-busy", state.activityCapacityLoading ? "true" : "false");
  button.textContent = state.activityCapacityLoading ? "V+H..." : "V+H";
  button.title = active ? "Dölj historiskt snitt (V+H)" : "Visa historiskt snitt (V+H)";
}

function formatActivityCapacityValue(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "";
  if (number >= 10) return String(Math.round(number));
  return number.toFixed(1).replace(".", ",").replace(",0", "");
}

function activityCapacityFor(personId, activityId) {
  if (!state.activityCapacityVisible || personId == null || activityId == null) return null;
  if (!activityCapacityActivityIsVisible(activityId)) return null;
  const personPayload = state.activityCapacity?.people?.[String(personId)];
  const capacity = personPayload?.[String(activityId)] || null;
  const value = Number(capacity?.value_per_hour);
  return Number.isFinite(value) && value > 0 ? capacity : null;
}

function activityLabelWithCapacity(activityId, personId) {
  const label = activityLabel(activityId);
  const capacity = activityCapacityFor(personId, activityId);
  const value = formatActivityCapacityValue(capacity?.value_per_hour);
  return label && value ? `${label}(${value})` : label;
}

function applyActivityCapacityToSelect(select, personId, activityId) {
  if (!select || activityId == null) return;
  const option = Array.from(select.options).find((item) => item.value === String(activityId));
  if (!option) return;
  option.textContent = activityLabelWithCapacity(activityId, personId);
  const capacity = activityCapacityFor(personId, activityId);
  if (capacity) {
    option.title = `${formatActivityCapacityValue(capacity.value_per_hour)} ${capacity.unit || "enheter"}/timme`;
  }
}

function rerenderScheduleCellsForCapacity() {
  document.querySelectorAll("#scheduleBody td[data-hour]").forEach((td) => renderHourCell(td));
  applySelectedPersonRow();
  refreshCurrentHourHighlight();
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

function scheduleSameBusiness(leftBusinessId, rightBusinessId) {
  if (leftBusinessId == null || rightBusinessId == null || leftBusinessId === "" || rightBusinessId === "") {
    return true;
  }
  const left = Number(leftBusinessId);
  const right = Number(rightBusinessId);
  if (!Number.isFinite(left) || !Number.isFinite(right)) return true;
  return left === right;
}

function scheduleLoanActivityForArea(area, person) {
  const areaId = Number(area?.id);
  if (!Number.isFinite(areaId)) return null;
  const candidates = state.activities
    .filter((activity) =>
      activity?.is_active !== false
      && Number(activity.area_id) === areaId
      && activity.category !== "absence"
      && scheduleSameBusiness(activity.business_id, person?.business_id)
    )
    .sort((a, b) => {
      const aw = a.category === "work" ? 0 : 1;
      const bw = b.category === "work" ? 0 : 1;
      return aw - bw || (Number(a.sort_order) || 0) - (Number(b.sort_order) || 0) || a.label.localeCompare(b.label);
    });
  const preferredCode = area?.code ? `${String(area.code).trim().toUpperCase()}_VM` : "";
  return candidates.find((activity) => String(activity.code || "").trim().toUpperCase() === preferredCode)
    || candidates[0]
    || null;
}

function scheduleLoanTargetOptions(person) {
  const homeAreaId = Number(person?.home_area_id);
  return state.areas
    .filter((area) => {
      const areaId = Number(area?.id);
      if (!Number.isFinite(areaId) || area?.is_active === false) return false;
      if (Number.isFinite(homeAreaId) && areaId === homeAreaId) return false;
      if (typeof isAllAreasMarker === "function" && isAllAreasMarker(area)) return false;
      if (String(area?.code || "").trim().toUpperCase() === "ANNAT") return false;
      return scheduleSameBusiness(area.business_id, person?.business_id);
    })
    .map((area) => ({ area }))
    .sort((a, b) =>
      (Number(a.area.sort_order) || 0) - (Number(b.area.sort_order) || 0)
      || String(a.area.name || a.area.code || "").localeCompare(String(b.area.name || b.area.code || ""))
    );
}

function scheduleLoanHoursForPerson(personId) {
  const scheduled = state.scheduledHours[Number(personId)];
  return HOURS.filter((hour) => scheduled?.has(hour) || segmentsForHour(personId, hour).length > 0);
}

function scheduleLoanStartHour() {
  const current = currentHourIfToday();
  if (current != null) return Math.max(HOURS[0], Math.min(HOURS[HOURS.length - 1], current));
  const focusedHour = Number(state.focusedCell?.hour);
  if (Number.isFinite(focusedHour) && HOURS.includes(focusedHour)) return focusedHour;
  return null;
}

function scheduleLoanHourLabel(hour) {
  if (hour == null || !Number.isFinite(Number(hour))) return "";
  return `${String(hour).padStart(2, "0")}:00`;
}

function scheduleLoanStartHint() {
  const startHour = scheduleLoanStartHour();
  return startHour == null ? "Klicka först på starttimme" : `Tomt från ${scheduleLoanHourLabel(startHour)}`;
}

function scheduleLoanCellsForHour(personId, hour, areaId) {
  const segments = segmentsForHour(personId, hour);
  const fullSegment = segments.find((segment) => segment.minute_start === 0 && segment.minute_end === 60) || null;
  const targetRanges = (isSplitHour(segments) || segments.some((segment) => isPartialRange(segment)))
    ? splitRangesForSegments(segments)
    : [FULL_SEGMENT];
  return targetRanges.map(({ minute_start, minute_end }) => {
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
      person_id: Number(personId),
      activity_id: null,
      loan_area_id: Number(areaId),
      expected_version: expectedVersion,
    };
  });
}

function closeScheduleLoanMenu() {
  if (!scheduleLoanMenu) return;
  scheduleLoanMenu.remove();
  scheduleLoanMenu = null;
  document.removeEventListener("pointerdown", handleScheduleLoanMenuPointerDown);
  document.removeEventListener("keydown", handleScheduleLoanMenuKeydown);
  document.removeEventListener("scroll", handleScheduleLoanMenuScroll, true);
  window.removeEventListener("resize", closeScheduleLoanMenu);
}

function handleScheduleLoanMenuPointerDown(event) {
  if (!scheduleLoanMenu || scheduleLoanMenu.contains(event.target)) return;
  closeScheduleLoanMenu();
}

function handleScheduleLoanMenuKeydown(event) {
  if (event.key === "Escape") closeScheduleLoanMenu();
}

function handleScheduleLoanMenuScroll(event) {
  if (scheduleLoanMenu?.contains(event.target)) return;
  closeScheduleLoanMenu();
}

function openScheduleLoanMenu(event, person) {
  event.preventDefault();
  event.stopPropagation();
  closeScheduleLoanMenu();

  if (scheduleIsReadOnly()) {
    showReadOnlyToast();
    return;
  }

  const options = scheduleLoanTargetOptions(person);
  if (!options.length) {
    showToast("Inga andra aktiva områden finns för personen.", "warn", 5000);
    return;
  }

  const menu = document.createElement("div");
  menu.className = "schedule-loan-menu";
  menu.setAttribute("role", "menu");
  menu.style.left = "0px";
  menu.style.top = "0px";

  const title = document.createElement("div");
  title.className = "schedule-loan-menu-title";
  title.textContent = person?.name || "Person";
  menu.appendChild(title);

  options.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("role", "menuitem");

    const label = document.createElement("span");
    label.textContent = `Skicka till ${option.area.name || option.area.code}`;
    button.appendChild(label);

    const meta = document.createElement("small");
    meta.textContent = scheduleLoanStartHint();
    button.appendChild(meta);

    button.addEventListener("click", () => {
      closeScheduleLoanMenu();
      void sendPersonToArea(person.id, option.area.id);
    });
    menu.appendChild(button);
  });

  document.body.appendChild(menu);
  scheduleLoanMenu = menu;
  const rect = menu.getBoundingClientRect();
  const left = Math.max(8, Math.min(event.clientX, window.innerWidth - rect.width - 8));
  const top = Math.max(8, Math.min(event.clientY, window.innerHeight - rect.height - 8));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;

  window.setTimeout(() => {
    document.addEventListener("pointerdown", handleScheduleLoanMenuPointerDown);
    document.addEventListener("keydown", handleScheduleLoanMenuKeydown);
    document.addEventListener("scroll", handleScheduleLoanMenuScroll, true);
    window.addEventListener("resize", closeScheduleLoanMenu);
  }, 0);
}

async function sendPersonToArea(personId, areaId) {
  if (scheduleIsReadOnly()) {
    showReadOnlyToast();
    return;
  }
  const person = personById(Number(personId));
  const option = scheduleLoanTargetOptions(person).find((item) => Number(item.area.id) === Number(areaId));
  if (!person || !option) {
    showToast("Kunde inte hitta område för utlåningen.", "error", 6000);
    return;
  }

  const startHour = scheduleLoanStartHour();
  if (startHour == null) {
    showToast("Klicka först på timmen där flytten ska börja, eller välj dagens datum så aktuell timme kan användas.", "warn", 7000);
    return;
  }
  const hours = scheduleLoanHoursForPerson(person.id).filter((hour) => hour >= startHour);
  if (!hours.length) {
    showToast(`Personen saknar schemalagda timmar från ${scheduleLoanHourLabel(startHour)} den här dagen.`, "warn", 5000);
    return;
  }

  const lockedHours = [];
  const cells = [];
  hours.forEach((hour) => {
    if (isHourLocked(person.id, hour)) {
      lockedHours.push(hour);
      return;
    }
    cells.push(...scheduleLoanCellsForHour(person.id, hour, option.area.id));
  });

  if (!cells.length) {
    showLockedCellToast();
    return;
  }
  if (cells.length > 200) {
    showToast("För många celler eller delar (max 200)", "error");
    return;
  }

  markScheduleActivity();
  const snapshots = snapshotHoursFromCells(cells);
  const optimisticByHour = new Map();
  cells.forEach((cell) => {
    const key = hourKey(cell.person_id, cell.hour);
    if (!optimisticByHour.has(key)) optimisticByHour.set(key, []);
    optimisticByHour.get(key).push(cell);
  });
  optimisticByHour.forEach((items, key) => {
    const [pid, hour] = key.split(":").map(Number);
    replaceHourSegments(pid, hour, optimisticSegmentsForHour(pid, hour, items));
    const td = getHourTd(pid, hour);
    if (!td) return;
    setHourPending(td, true);
    renderHourCell(td);
  });

  try {
    const resp = await api.post("/api/schedule/cells", { cells, atomic: true, action: "loan_to_area" });
    invalidateScheduleAllCache();
    pushScheduleUndo(`skicka ${person.name} till ${option.area.name || option.area.code}`, snapshots);
    applySegmentsByHourResponse(resp.applied);
    scheduleSummaryRefresh(0, { refreshCalculator: true });
    const changedHours = new Set(cells.map((cell) => hourKey(cell.person_id, cell.hour))).size;
    showToast(
      lockedHours.length
        ? `Skickade ${person.name} till ${option.area.name || option.area.code} från ${scheduleLoanHourLabel(startHour)} (${changedHours} tim), hoppade över ${lockedHours.length} låsta`
        : `Skickade ${person.name} till ${option.area.name || option.area.code} från ${scheduleLoanHourLabel(startHour)} (${changedHours} tim)`,
      "success"
    );
  } catch (error) {
    restoreHourSnapshots(snapshots);
    if (error.status === 409) {
      showToast(`${error.body?.conflicts?.length ?? 0} konflikter – läser om`, "warn");
      await loadSchedule();
    } else {
      showToast("Kunde inte skicka personen: " + error.message, "error");
    }
  }
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
  const loanHint = "Högerklicka för att skicka personen till annat område.";
  cell.addEventListener("contextmenu", (event) => openScheduleLoanMenu(event, person));
  if (!scheduleIsReadOnly()) cell.classList.add("schedule-loan-enabled");
  if (canReorderPerson(person)) {
    cell.draggable = true;
    cell.classList.add("person-order-draggable");
    cell.title = "Dra namnet för att ändra sorteringen.";
  } else if (canUsePersonSortOrder()) {
    cell.classList.add("person-order-locked");
    cell.title = "Du kan bara sortera personer med samma hemområde som ditt användarområde.";
  }
  if (!scheduleIsReadOnly()) {
    cell.title = cell.title ? `${cell.title} ${loanHint}` : loanHint;
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

function isFullRange(range) {
  return Number(range?.minute_start) === 0 && Number(range?.minute_end) === 60;
}

function isPartialRange(range) {
  const start = Number(range?.minute_start);
  const end = Number(range?.minute_end);
  return Number.isFinite(start) && Number.isFinite(end) && start >= 0 && end <= 60 && start < end && !isFullRange(range);
}

function normalizeSplitPartCount(partCount) {
  const parsed = Number.parseInt(String(partCount), 10);
  if (!Number.isInteger(parsed)) return MIN_SPLIT_PARTS;
  return Math.max(MIN_SPLIT_PARTS, Math.min(MAX_SPLIT_PARTS, parsed));
}

function defaultSplitBoundaries(partCount = MIN_SPLIT_PARTS, firstBoundary = DEFAULT_SPLIT_MINUTES) {
  const count = normalizeSplitPartCount(partCount);
  if (count === 2) {
    const first = Math.max(1, Math.min(59, Number.parseInt(String(firstBoundary), 10) || DEFAULT_SPLIT_MINUTES));
    return [first];
  }
  return [...(DEFAULT_SPLIT_BOUNDARIES[count] || DEFAULT_SPLIT_BOUNDARIES[MIN_SPLIT_PARTS])];
}

function orderedSplitBoundariesAreValid(boundaries, partCount = MIN_SPLIT_PARTS) {
  if (!Array.isArray(boundaries) || boundaries.length !== normalizeSplitPartCount(partCount) - 1) return false;
  let previous = 0;
  return boundaries.every((boundary) => {
    const value = Number(boundary);
    const valid = Number.isInteger(value) && value > previous && value < 60;
    previous = value;
    return valid;
  });
}

function splitSegmentsForBoundaries(boundaries, partCount = MIN_SPLIT_PARTS) {
  if (!orderedSplitBoundariesAreValid(boundaries, partCount)) return null;
  return [0, ...boundaries.map((boundary) => Number(boundary)), 60].slice(0, normalizeSplitPartCount(partCount) + 1)
    .map((minute, index, all) => index === all.length - 1 ? null : ({
      minute_start: minute,
      minute_end: all[index + 1],
    }))
    .filter(Boolean);
}

function splitSegmentsForMinute(minutes = DEFAULT_SPLIT_MINUTES) {
  return splitSegmentsForBoundaries(defaultSplitBoundaries(MIN_SPLIT_PARTS, minutes), MIN_SPLIT_PARTS)
    || HALF_SEGMENTS.map((segment) => ({ ...segment }));
}

function isCompleteSplitRangeList(values) {
  if (!Array.isArray(values) || values.length < MIN_SPLIT_PARTS || values.length > MAX_SPLIT_PARTS) return false;
  if (values[0].minute_start !== 0 || values[values.length - 1].minute_end !== 60) return false;
  return values.every((range, index) => (
    range.minute_start >= 0
    && range.minute_end <= 60
    && range.minute_start < range.minute_end
    && (index === 0 || values[index - 1].minute_end === range.minute_start)
  ));
}

function splitRangesFromRanges(ranges) {
  const unique = new Map();
  (ranges || []).forEach((range) => {
    const start = Number(range?.minute_start);
    const end = Number(range?.minute_end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end > 60 || start >= end) return;
    unique.set(`${start}:${end}`, { minute_start: start, minute_end: end });
  });
  const values = Array.from(unique.values()).sort((a, b) => a.minute_start - b.minute_start || a.minute_end - b.minute_end);
  if (isCompleteSplitRangeList(values)) {
    return values;
  }
  const partial = values.find((range) => isPartialRange(range));
  if (partial?.minute_start === 0 && partial.minute_end > 0 && partial.minute_end < 60) {
    return splitSegmentsForMinute(partial.minute_end);
  }
  if (partial?.minute_end === 60 && partial.minute_start > 0 && partial.minute_start < 60) {
    return splitSegmentsForMinute(partial.minute_start);
  }
  return null;
}

function splitRangesForSegments(segments) {
  return splitRangesFromRanges(segments) || HALF_SEGMENTS.map((segment) => ({ ...segment }));
}

function splitRangesForItems(items) {
  return splitRangesFromRanges(items) || HALF_SEGMENTS.map((segment) => ({ ...segment }));
}

function firstSplitRangeForTd(td) {
  const personId = Number(td?.dataset?.personId);
  const hour = Number(td?.dataset?.hour);
  return splitRangesForSegments(segmentsForHour(personId, hour))[0] || { ...HALF_SEGMENTS[0] };
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
      loan_area_id: cell.loan_area_id == null ? null : Number(cell.loan_area_id),
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
    loan_area_id: segment.loan_area_id == null ? null : Number(segment.loan_area_id),
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
    loan_area_id: null,
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
    loan_area_id: segment.loan_area_id == null ? null : Number(segment.loan_area_id),
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
    loan_area_id: segment.loan_area_id,
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
    scheduleSummaryRefresh(0, { refreshCalculator: true });
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
  const needsSplitSegments = items.some((item) => isPartialRange(item));
  const targetSplitRanges = splitRangesForItems(items);

  if (!needsSplitSegments && items.length === 1 && Number(items[0].minute_start) === 0 && Number(items[0].minute_end) === 60) {
    return [
      {
        person_id: personId,
        hour,
        minute_start: 0,
        minute_end: 60,
        activity_id: items[0].activity_id == null ? null : Number(items[0].activity_id),
        loan_area_id: items[0].loan_area_id == null ? null : Number(items[0].loan_area_id),
        empty_override: items[0].activity_id == null && scheduled,
        version: current[0]?.version || 0,
        updated_at: current[0]?.updated_at || null,
        updated_by: current[0]?.updated_by ?? null,
      },
    ];
  }

  let segments = current;
  if (needsSplitSegments) {
    if (segments.length === 0) {
      segments = targetSplitRanges.map(({ minute_start, minute_end }) => ({
        person_id: personId,
        hour,
        minute_start,
        minute_end,
        activity_id: null,
        loan_area_id: null,
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
      segments = targetSplitRanges.map(({ minute_start, minute_end }) => ({
        person_id: personId,
        hour,
        minute_start,
        minute_end,
        activity_id: source.activity_id,
        loan_area_id: source.loan_area_id,
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
  if (needsSplitSegments) {
    targetSplitRanges.forEach(({ minute_start, minute_end }) => {
      const key = `${minute_start}:${minute_end}`;
      if (byRange.has(key)) return;
      byRange.set(key, {
        person_id: personId,
        hour,
        minute_start,
        minute_end,
        activity_id: null,
        loan_area_id: null,
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
      loan_area_id: null,
      empty_override: scheduled,
      version: 0,
      updated_at: null,
      updated_by: null,
    };
    byRange.set(key, {
      ...existing,
      activity_id: item.activity_id == null ? null : Number(item.activity_id),
      loan_area_id: item.loan_area_id == null ? null : Number(item.loan_area_id),
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
  return !!splitRangesFromRanges(segments);
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
  const rounded = Math.round((num + Number.EPSILON) * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2).replace(/\.?0+$/, "");
}

function ensureManualCalcInput() {
  if (!state.calcInputs.manual) {
    state.calcInputs.manual = { rows: "", time: "", goal: "" };
  }
  return state.calcInputs.manual;
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

function manualPlockHours() {
  return (state.summaryRows || []).reduce((sum, item) => {
    const code = String(item.activity_code || "").toUpperCase();
    const label = String(item.activity_label || "").toUpperCase();
    if (!code.includes("PLOCK") && !label.includes("PLOCK")) return sum;
    return sum + (Number(item.hours) || 0);
  }, 0);
}

function calcMetrics() {
  const values = ensureManualCalcInput();
  const rows = parseNumericInput(values.rows);
  const time = parseNumericInput(values.time);
  const goal = parseNumericInput(values.goal);
  const plockHours = manualPlockHours();

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

function updateCalcPanel(panel) {
  const { need, hours, diff } = calcMetrics();
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

function calcResultText(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return formatHours(Number(value));
}

function renderAutomaticCalculatorPanel(result) {
  const calc = (state.calculatorProfile.calculators || []).find((item) => item.id === result.id) || {};
  const isError = result.status === "error";
  const remaining = result.rows_remaining_after_schedule;
  return `
    <div class="calc-panel calc-panel-auto" data-calc-id="${escapeHtml(result.id || "")}">
      <div class="calc-panel-title calc-panel-title-row">
        <span>${escapeHtml(result.name || calc.name || "Automatisk")}</span>
        <span class="calc-panel-actions">
          <button type="button" class="icon-btn" data-calc-edit="${escapeHtml(result.id || "")}" title="Ändra" aria-label="Ändra">✎</button>
          <button type="button" class="icon-btn danger" data-calc-delete="${escapeHtml(result.id || "")}" title="Ta bort" aria-label="Ta bort">×</button>
        </span>
      </div>
      ${isError ? `
        <p class="note error">${escapeHtml(result.message || "Kalkylen kunde inte beräknas.")}</p>
      ` : `
        <table class="calc-table auto-calc-table">
          <thead>
            <tr><th>Rader kvar efter schemalagd tid</th></tr>
          </thead>
          <tbody>
            <tr><td class="calc-output ${remaining > 0 ? "negative" : "positive"}">${calcResultText(remaining)}</td></tr>
          </tbody>
        </table>
        <p class="note">Rader ${calcResultText(result.order_rows)} · schemalagt ${calcResultText(result.scheduled_hours)} h · plan ${calcResultText(result.expected_rows)} rader</p>
      `}
    </div>
  `;
}

function renderCalculator() {
  const container = document.getElementById("calcPanels");
  if (!container) return;

  const active = document.activeElement;
  let focusState = null;
  if (active && container.contains(active) && active.matches("input[data-field]")) {
    focusState = {
      field: active.dataset.field || "",
      selectionStart: typeof active.selectionStart === "number" ? active.selectionStart : null,
      selectionEnd: typeof active.selectionEnd === "number" ? active.selectionEnd : null,
    };
  }

  const values = ensureManualCalcInput();
  const metrics = calcMetrics();
  const automatic = state.automaticCalculatorResults || [];
  container.innerHTML = `
    <div class="calc-panel calc-panel-manual" data-calc-kind="manual">
      <div class="calc-panel-title">Manuell</div>
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
    </div>
    ${state.automaticCalculatorLoading ? `<div class="calc-panel"><div class="calc-panel-title">Automatiska</div><p class="note">Beräknar automatiska kalkyler...</p></div>` : ""}
    ${state.automaticCalculatorError ? `<div class="calc-panel"><div class="calc-panel-title">Automatiska</div><p class="note error">${escapeHtml(state.automaticCalculatorError)}</p></div>` : ""}
    ${automatic.map(renderAutomaticCalculatorPanel).join("")}
  `;

  container.querySelectorAll("input[data-field]").forEach((input) => {
    input.addEventListener("input", (e) => {
      const panel = e.target.closest(".calc-panel");
      if (!panel) return;
      const field = e.target.dataset.field;
      const sanitized = sanitizeNumericInput(e.target.value);
      if (sanitized !== e.target.value) e.target.value = sanitized;
      state.calcInputs.manual[field] = sanitized;
      updateCalcPanel(panel);
    });
  });
  container.querySelectorAll("[data-calc-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const calc = (state.calculatorProfile.calculators || []).find((item) => item.id === button.dataset.calcEdit);
      if (calc) openCalculatorModal(calc);
    });
  });
  container.querySelectorAll("[data-calc-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteAutomaticCalculator(button.dataset.calcDelete);
    });
  });

  if (focusState?.field) {
    const nextInput = container.querySelector(
      `.calc-panel[data-calc-kind="manual"] input[data-field="${focusState.field}"]`
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
  renderCalculator();
}

function syncCalculatorWithSelectedArea() {
  renderCalculator();
}

function normalizeCalculatorProfile(profile) {
  const items = Array.isArray(profile?.calculators) ? profile.calculators : [];
  return {
    version: 1,
    calculators: items
      .map((item) => ({
        id: String(item?.id || `calc-${Date.now()}-${Math.random().toString(16).slice(2)}`),
        name: String(item?.name || "").trim(),
        process: String(item?.process || "").trim(),
        company: String(item?.company || "").trim().toUpperCase(),
        zone: String(item?.zone || "").trim().toUpperCase(),
        pick_days: Number.parseInt(item?.pick_days ?? 0, 10) || 0,
      }))
      .filter((item) => item.name && item.process && item.company && item.zone),
  };
}

function updateCalculatorToolbar() {
  const importUser = document.getElementById("calcImportUser");
  if (!importUser) return;
  const search = String(state.calculatorImportSearch || "").trim().toLowerCase();
  const currentValue = importUser.value;
  const users = (state.calculatorUsers || [])
    .filter((user) => user.has_calculators && !user.is_current)
    .filter((user) => {
      if (!search) return true;
      return `${user.name || ""} ${user.username || ""}`.toLowerCase().includes(search);
    });
  importUser.innerHTML = `
    <option value="">Hämta från användare</option>
    ${users.map((user) => `<option value="${escapeHtml(user.id)}">${escapeHtml(user.name || user.username)} (${escapeHtml(user.calculator_count || 0)})</option>`).join("")}
  `;
  if (users.some((user) => String(user.id) === String(currentValue))) importUser.value = currentValue;
  importUser.disabled = users.length === 0;
  const button = document.getElementById("calcImportBtn");
  if (button) button.disabled = users.length === 0 || !importUser.value;
}

function applyCalculatorProfilePayload(data) {
  state.calculatorProfile = normalizeCalculatorProfile(data?.profile);
  state.calculatorUsers = Array.isArray(data?.users) ? data.users : [];
  state.calculatorProcessOptions = Array.isArray(data?.process_options) ? data.process_options : [];
  updateCalculatorToolbar();
  renderCalculator();
}

async function loadCalculatorProfile() {
  try {
    const data = await api.get("/api/schedule/calculator-profile", { cacheTtlMs: 10 * 1000 });
    applyCalculatorProfilePayload(data);
  } catch (error) {
    console.warn("Kunde inte läsa bemanningskalkyler", error);
    state.calculatorProfile = { version: 1, calculators: [] };
    state.calculatorUsers = [];
    state.calculatorProcessOptions = [];
    updateCalculatorToolbar();
    renderCalculator();
  }
}

async function saveCalculatorProfile(profile) {
  const data = await api.put("/api/schedule/calculator-profile", { profile: normalizeCalculatorProfile(profile) });
  applyCalculatorProfilePayload(data);
  await loadAutomaticCalculatorResults({ force: true });
}

async function importCalculatorProfile(userId) {
  const data = await api.post("/api/schedule/calculator-profile/import", { user_id: Number(userId) });
  applyCalculatorProfilePayload(data);
  showToast("Bemanningskalkyler hämtades", "success");
  await loadAutomaticCalculatorResults({ force: true });
}

function automaticCalculatorProfileKey() {
  return JSON.stringify(normalizeCalculatorProfile(state.calculatorProfile));
}

function automaticCalculatorHalfHourKey() {
  return Math.floor(Date.now() / (30 * 60 * 1000));
}

function automaticCalculatorRequestKey() {
  return [
    scheduleScopeKey(),
    state.year,
    state.week,
    state.weekday,
    state.scheduleRevisionKey || "",
    automaticCalculatorHalfHourKey(),
    automaticCalculatorProfileKey(),
  ].join("|");
}

function scheduleAutomaticCalculatorRefresh(delay = 250, { force = false } = {}) {
  clearTimeout(automaticCalculatorState.timer);
  automaticCalculatorState.timer = setTimeout(() => {
    automaticCalculatorState.timer = null;
    void loadAutomaticCalculatorResults({ force });
  }, delay);
}

async function loadAutomaticCalculatorResults({ force = false } = {}) {
  if (!state.calculatorProfile?.calculators?.length) {
    state.automaticCalculatorResults = [];
    state.automaticCalculatorLoading = false;
    state.automaticCalculatorError = "";
    automaticCalculatorState.loadedKey = automaticCalculatorRequestKey();
    renderCalculator();
    return;
  }
  const requestKey = automaticCalculatorRequestKey();
  if (!force && automaticCalculatorState.loadedKey === requestKey && !state.automaticCalculatorError) {
    renderCalculator();
    return;
  }
  const requestSeq = ++automaticCalculatorState.requestSeq;
  state.automaticCalculatorLoading = true;
  state.automaticCalculatorError = "";
  renderCalculator();
  try {
    const result = await api.get(
      `/api/schedule/calculator/automatic?year=${state.year}&week=${state.week}&weekday=${state.weekday}`,
      { skipCache: true },
    );
    if (requestSeq !== automaticCalculatorState.requestSeq || requestKey !== automaticCalculatorRequestKey()) return;
    state.automaticCalculatorResults = Array.isArray(result.calculators) ? result.calculators : [];
    automaticCalculatorState.loadedKey = requestKey;
  } catch (error) {
    if (requestSeq !== automaticCalculatorState.requestSeq) return;
    state.automaticCalculatorResults = [];
    state.automaticCalculatorError = error.message || "Kunde inte beräkna automatiska kalkyler.";
  } finally {
    if (requestSeq === automaticCalculatorState.requestSeq) {
      state.automaticCalculatorLoading = false;
      renderCalculator();
    }
  }
}

function setupCalculatorToolbar() {
  document.getElementById("calcAddAutomaticBtn")?.addEventListener("click", () => openCalculatorModal());
  document.getElementById("calcImportSearch")?.addEventListener("input", (event) => {
    state.calculatorImportSearch = event.target.value;
    updateCalculatorToolbar();
  });
  document.getElementById("calcImportUser")?.addEventListener("change", () => updateCalculatorToolbar());
  document.getElementById("calcImportBtn")?.addEventListener("click", async () => {
    const select = document.getElementById("calcImportUser");
    const userId = select?.value;
    if (!userId) return;
    try {
      await importCalculatorProfile(userId);
    } catch (error) {
      showToast(error.message || "Kunde inte hämta bemanningskalkyler", "error");
    }
  });
}

function openCalculatorModal(existing = null) {
  const isEdit = Boolean(existing);
  const calc = existing || { name: "", process: "", company: "", zone: "", pick_days: 0 };
  const options = state.calculatorProcessOptions || [];
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Ändra automatisk kalkyl" : "Ny automatisk kalkyl"}</h2>
      <label>Namn
        <input id="calcName" value="${escapeHtml(calc.name || "")}" />
      </label>
      <label>Process
        <select id="calcProcess" ${options.length ? "" : "disabled"}>
          <option value="">Välj process</option>
          ${options.map((option) => `
            <option value="${escapeHtml(option.value)}" ${option.value === calc.process ? "selected" : ""}>${escapeHtml(option.label || option.value)}</option>
          `).join("")}
        </select>
      </label>
      <label>Bolag
        <input id="calcCompany" value="${escapeHtml(calc.company || "")}" />
      </label>
      <label>Zon
        <input id="calcZone" value="${escapeHtml(calc.zone || "")}" />
      </label>
      <label>Plockdagar
        <input id="calcPickDays" type="number" step="1" value="${escapeHtml(calc.pick_days ?? 0)}" />
      </label>
      <div class="actions">
        <button type="button" id="calcCancel">Avbryt</button>
        <button type="button" id="calcSave">Spara</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);
  const close = () => backdrop.remove();
  backdrop.querySelector("#calcCancel").addEventListener("click", close);
  backdrop.querySelector("#calcSave").addEventListener("click", async () => {
    const next = {
      id: existing?.id || `calc-${Date.now()}`,
      name: backdrop.querySelector("#calcName").value.trim(),
      process: backdrop.querySelector("#calcProcess").value.trim(),
      company: backdrop.querySelector("#calcCompany").value.trim().toUpperCase(),
      zone: backdrop.querySelector("#calcZone").value.trim().toUpperCase(),
      pick_days: Number.parseInt(backdrop.querySelector("#calcPickDays").value, 10) || 0,
    };
    if (!next.name || !next.process || !next.company || !next.zone) {
      showToast("Namn, process, bolag och zon krävs", "warn");
      return;
    }
    const calculators = [...(state.calculatorProfile.calculators || [])];
    const index = calculators.findIndex((item) => item.id === next.id);
    if (index >= 0) calculators[index] = next;
    else calculators.push(next);
    try {
      await saveCalculatorProfile({ version: 1, calculators });
      showToast("Bemanningskalkyl sparad", "success");
      close();
    } catch (error) {
      showToast(error.message || "Kunde inte spara kalkylen", "error");
    }
  });
  setTimeout(() => backdrop.querySelector("#calcName")?.focus());
}

async function deleteAutomaticCalculator(calcId) {
  const calc = (state.calculatorProfile.calculators || []).find((item) => item.id === calcId);
  if (!calc) return;
  if (!confirm(`Ta bort kalkylen "${calc.name}"?`)) return;
  const calculators = (state.calculatorProfile.calculators || []).filter((item) => item.id !== calcId);
  try {
    await saveCalculatorProfile({ version: 1, calculators });
    showToast("Bemanningskalkyl borttagen", "success");
  } catch (error) {
    showToast(error.message || "Kunde inte ta bort kalkylen", "error");
  }
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
    const values = splitRangesForSegments(segments).map((range) =>
      effectiveActivityIdForRange(personId, hour, range.minute_start, range.minute_end)
    );
    return values.length > 0 && values.every((value) => value != null && value === values[0]) ? values[0] : null;
  }
  return effectiveActivityIdForRange(personId, hour, 0, 60);
}

function effectiveActivityIdForFocus() {
  if (!state.focusedCell) return null;
  const { personId, hour, minuteStart, minuteEnd } = state.focusedCell;
  return effectiveActivityIdForRange(personId, hour, minuteStart, minuteEnd);
}

function splitDurationsForRanges(ranges) {
  return (ranges || []).map((range) => Number(range.minute_end) - Number(range.minute_start));
}

function formatMinuteList(values) {
  const textValues = (values || []).map((value) => String(value));
  if (textValues.length <= 1) return textValues[0] || "";
  if (textValues.length === 2) return `${textValues[0]} och ${textValues[1]}`;
  return `${textValues.slice(0, -1).join(", ")} och ${textValues[textValues.length - 1]}`;
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

function requestScheduleSplitMinutes(defaultMinutes = DEFAULT_SPLIT_MINUTES) {
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal schedule-split-modal" role="dialog" aria-modal="true" aria-labelledby="scheduleSplitTitle">
        <div class="schedule-split-heading">
          <h2 id="scheduleSplitTitle">Dela timme</h2>
          <div class="schedule-split-mode" role="group" aria-label="Antal delar">
            <button type="button" data-split-parts="2">1/2</button>
            <button type="button" data-split-parts="3">1/3</button>
            <button type="button" data-split-parts="4">1/4</button>
          </div>
        </div>
        <div id="scheduleSplitFields" class="schedule-split-fields"></div>
        <p class="note" id="scheduleSplitHint"></p>
        <div class="actions">
          <button type="button" id="scheduleSplitCancel">Avbryt</button>
          <button type="button" class="primary" data-enter-default id="scheduleSplitContinue">Fortsätt</button>
        </div>
      </div>
    `;
    document.body.appendChild(backdrop);

    let partCount = MIN_SPLIT_PARTS;
    const boundaryValues = new Map(
      [2, 3, 4].map((count) => [
        count,
        defaultSplitBoundaries(count, defaultMinutes).map((value) => String(value)),
      ])
    );
    const fields = backdrop.querySelector("#scheduleSplitFields");
    const hint = backdrop.querySelector("#scheduleSplitHint");
    const modeButtons = Array.from(backdrop.querySelectorAll("[data-split-parts]"));
    const close = (value) => {
      backdrop.remove();
      resolve(value);
    };
    const inputs = () => Array.from(fields.querySelectorAll("input[data-split-boundary]"));
    const parsedBoundaries = () => inputs().map((input) => Number.parseInt(String(input.value || "").trim(), 10));
    const persistValues = () => {
      boundaryValues.set(partCount, inputs().map((input) => String(input.value || "").trim()));
    };
    const focusFirstInput = () => {
      const input = inputs()[0];
      if (!input) return;
      input.focus();
      input.select();
    };
    const updateHint = () => {
      const ranges = splitSegmentsForBoundaries(parsedBoundaries(), partCount);
      hint.textContent = ranges
        ? `Delarna blir ${formatMinuteList(splitDurationsForRanges(ranges))} minuter.`
        : (partCount === 2 ? "Skriv ett heltal mellan 1 och 59." : "Skriv stigande minuter mellan 1 och 59.");
    };
    const renderFields = (selectFirst = false) => {
      modeButtons.forEach((button) => {
        const isActive = Number(button.dataset.splitParts) === partCount;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
      });
      const values = boundaryValues.get(partCount) || defaultSplitBoundaries(partCount).map((value) => String(value));
      if (partCount === 2) {
        fields.innerHTML = `
          <label>Minuter i första delen
            <input id="scheduleSplitMinutesInput" data-split-boundary="0" type="text" inputmode="numeric" autocomplete="off" value="${escapeHtml(values[0] || DEFAULT_SPLIT_MINUTES)}" />
          </label>
        `;
      } else {
        fields.innerHTML = `
          <div class="schedule-split-boundaries">
            ${values.map((value, index) => `
              <label>Början del ${index + 2}
                <input data-split-boundary="${index}" type="text" inputmode="numeric" autocomplete="off" value="${escapeHtml(value)}" />
              </label>
            `).join("")}
          </div>
        `;
      }
      inputs().forEach((input) => input.addEventListener("input", () => {
        persistValues();
        updateHint();
      }));
      updateHint();
      if (selectFirst) setTimeout(focusFirstInput, 0);
    };
    const submit = () => {
      persistValues();
      const ranges = splitSegmentsForBoundaries(parsedBoundaries(), partCount);
      if (!ranges) {
        showToast(
          partCount === 2
            ? "Skriv minuter för första delen, 1-59."
            : "Skriv stigande minutstarter mellan 1 och 59.",
          "warn"
        );
        focusFirstInput();
        updateHint();
        return;
      }
      close(ranges);
    };

    backdrop.querySelector("#scheduleSplitCancel").addEventListener("click", () => close(null));
    backdrop.querySelector("#scheduleSplitContinue").addEventListener("click", submit);
    modeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        persistValues();
        partCount = normalizeSplitPartCount(button.dataset.splitParts);
        renderFields(true);
      });
    });
    backdrop.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close(null);
      }
    });
    renderFields(true);
  });
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

async function toggleFullHourSplitFromEvent(e, td) {
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
  const splitRanges = await requestScheduleSplitMinutes(DEFAULT_SPLIT_MINUTES);
  if (splitRanges == null) return;
  void toggleHourSplit(td, 0, splitRanges);
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

  const ranges = splitRangesForSegments(segmentsForHour(Number(td.dataset.personId), Number(td.dataset.hour)));
  if (ranges.length >= 2) {
    const rect = td.getBoundingClientRect();
    const minuteAtPoint = Math.max(0, Math.min(59.999, ((clientX - rect.left) / Math.max(1, rect.width)) * 60));
    const index = ranges.findIndex((range) => minuteAtPoint >= range.minute_start && minuteAtPoint < range.minute_end);
    return parts[Math.max(0, index)] || parts[0];
  }

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
  return rangeFromSegmentPart(splitPartFromPoint(td, clientX, clientY)) || firstSplitRangeForTd(td);
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
  applyActivityCapacityToSelect(select, personId, selectedActivityId);
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
    td.appendChild(buildDisplayLabel(activityLabelWithCapacity(scheduledActivityId, personId), "cell-display-label"));
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
    td.title = "En eller flera delar är låsta av annan användare";
  }

  splitRangesForSegments(segments).forEach(({ minute_start, minute_end }) => {
    const segment = currentSegment(personId, hour, minute_start, minute_end);
    const part = document.createElement("div");
    part.className = "hour-segment";
    part.dataset.minuteStart = String(minute_start);
    part.dataset.minuteEnd = String(minute_end);
    part.style.flex = `${Math.max(1, minute_end - minute_start)} 1 0`;
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
    applyActivityCapacityToSelect(select, personId, selectedActivityId);
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
      part.appendChild(buildDisplayLabel(activityLabelWithCapacity(scheduledActivityId, personId), "hour-segment-label"));
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

  if (isSplitHour(segments) || segments.some((segment) => isPartialRange(segment))) {
    renderSplitHourCell(td, segments, isScheduled);
    if (td.classList.contains("pending-save")) setHourPending(td, true);
    return;
  }

  const segment = segments.length === 1 ? segments[0] : null;
  renderFullHourCell(td, segment, isScheduled);
  if (td.classList.contains("pending-save")) setHourPending(td, true);
}

function applySelectedPersonRow() {
  const selectedId = Number(state.selectedPersonId);
  document.querySelectorAll("#scheduleBody tr.person-row-selected").forEach((row) => {
    row.classList.remove("person-row-selected");
    row.removeAttribute("aria-selected");
  });
  if (!Number.isInteger(selectedId)) return;
  const row = document.querySelector(`#scheduleBody tr[data-person-id="${selectedId}"]`);
  if (!row) return;
  row.classList.add("person-row-selected");
  row.setAttribute("aria-selected", "true");
}

function selectPersonRow(personId) {
  const nextId = Number(personId);
  if (!Number.isInteger(nextId)) return;
  state.selectedPersonId = nextId;
  applySelectedPersonRow();
}

function renderScheduleProductivityCell(td, person) {
  td.textContent = "";
  td.className = "schedule-productivity";
  td.dataset.personId = String(person?.id || td.dataset.personId || "");
  const value = state.productivityByPersonId.get(Number(person?.id));
  if (!value) {
    td.title = "Ingen avslutad KPI-tid";
    return;
  }
  const span = document.createElement("span");
  span.className = `schedule-productivity-value ${value.status}`;
  span.textContent = `${value.percent}%`;
  td.title = `${Math.round(value.points)} p / ${value.hours.toFixed(1).replace(".", ",")} avslutade KPI-timmar`;
  td.appendChild(span);
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

    const productivity = document.createElement("td");
    productivity.className = "schedule-productivity";
    productivity.dataset.personId = person.id;
    renderScheduleProductivityCell(productivity, person);
    tr.appendChild(productivity);

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
  applySelectedPersonRow();
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

function scheduleSummaryRefresh(delay = 90, { refreshCalculator = false } = {}) {
  clearSummaryRefreshTimer();
  summaryState.timer = setTimeout(() => {
    summaryState.timer = null;
    void refreshSummary();
  }, delay);
  if (refreshCalculator) {
    scheduleAutomaticCalculatorRefresh(Math.max(250, delay), { force: true });
  }
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
    scheduleSummaryRefresh(90, { refreshCalculator: true });
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

async function toggleHourSplit(td, mergeMinuteStart = 0, splitRanges = splitSegmentsForMinute(DEFAULT_SPLIT_MINUTES)) {
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  const requestedSplitRanges = splitRangesFromRanges(splitRanges) || splitSegmentsForMinute(DEFAULT_SPLIT_MINUTES);
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
      split_minute: requestedSplitRanges[0]?.minute_end || DEFAULT_SPLIT_MINUTES,
      split_segments: requestedSplitRanges.map((range) => ({
        minute_start: range.minute_start,
        minute_end: range.minute_end,
      })),
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
      const ranges = splitRangesForSegments(updatedSegments);
      const firstRange = ranges[0] || requestedSplitRanges[0] || HALF_SEGMENTS[0];
      focusMatchingSegment(td, firstRange.minute_start, firstRange.minute_end);
      showToast(`Cellen delades i ${formatMinuteList(splitDurationsForRanges(ranges))} minuter.`);
    } else {
      focusMatchingSegment(td, 0, 60);
      showToast("Cellen slogs ihop till en hel timme.");
    }
    scheduleSummaryRefresh(90, { refreshCalculator: true });
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
      scheduleSummaryRefresh(90, { refreshCalculator: true });
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
    scheduleSummaryRefresh(90, { refreshCalculator: true });
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
  const splitRanges = splitRangesForSegments(segmentsForHour(Number(td.dataset.personId), Number(td.dataset.hour)));
  if (isAreaCopy) {
    return splitRanges.map((segment) => ({ ...segment }));
  }

  const sourceRangeFallback = splitRanges.find((range) => range.minute_start === sourceMinuteStart) || splitRanges[0];
  const fallbackRange = fallbackTargetRange
    && isPartialRange(fallbackTargetRange)
    ? fallbackTargetRange
    : sourceRangeFallback;
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
            loan_area_id: null,
            expected_version: expectedVersion,
          };
        });
    });

  if (cells.length === 0) return;
  if (cells.length > 200) {
    showToast("För många celler eller delar (max 200)", "error");
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
    scheduleSummaryRefresh(0, { refreshCalculator: true });
    showToast(
      lockedTargetCount
        ? `Fyllde ${cells.length} celler eller delar, hoppade över ${lockedTargetCount} låsta`
        : `Fyllde ${cells.length} celler eller delar`
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
    const row = e.target.closest("tr[data-person-id]");
    if (row && body.contains(row)) selectPersonRow(row.dataset.personId);
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

async function loadScheduleProductivity() {
  const key = scheduleProductivityKey();
  scheduleProductivityLoadState.controller?.abort();
  const controller = new AbortController();
  scheduleProductivityLoadState.controller = controller;
  scheduleProductivityLoadState.key = key;
  state.productivityReport = null;
  state.productivityByPersonId = new Map();
  state.productivityKey = key;
  updateScheduleProductivityCells();

  try {
    const report = await api.get(
      `/api/schedule/productivity-summary?year=${state.year}&week=${state.week}&weekday=${state.weekday}`,
      { signal: controller.signal, cacheTtlMs: 60 * 1000 },
    );
    if (controller.signal.aborted || scheduleProductivityLoadState.key !== key) return;
    state.productivityReport = report;
    state.productivityByPersonId = buildScheduleProductivityMapFromSummary(report);
    state.productivityKey = key;
    updateScheduleProductivityCells();
  } catch (err) {
    if (err?.name === "AbortError") return;
    console.warn("Kunde inte hamta produktivitet till bemanningen", err);
    if (scheduleProductivityLoadState.key !== key) return;
    state.productivityReport = null;
    state.productivityByPersonId = new Map();
    state.productivityKey = key;
    updateScheduleProductivityCells();
  } finally {
    if (scheduleProductivityLoadState.controller === controller) {
      scheduleProductivityLoadState.controller = null;
    }
  }
}

async function loadScheduleActivityCapacity({ force = false } = {}) {
  updateActivityCapacityToggleButton();
  if (!state.activityCapacityVisible) {
    activityCapacityState.controller?.abort();
    state.activityCapacityLoading = false;
    state.activityCapacityError = "";
    state.activityCapacityActivityIds = null;
    updateActivityCapacityToggleButton();
    rerenderScheduleCellsForCapacity();
    return;
  }

  const requestKey = activityCapacityRequestKey();
  if (!force && state.activityCapacityKey === requestKey && !state.activityCapacityError) {
    updateActivityCapacityToggleButton();
    rerenderScheduleCellsForCapacity();
    return;
  }

  const requestSeq = ++activityCapacityState.requestSeq;
  activityCapacityState.controller?.abort();
  const controller = new AbortController();
  activityCapacityState.controller = controller;
  state.activityCapacityLoading = true;
  state.activityCapacityError = "";
  state.activityCapacity = { people: {}, activities: {} };
  state.activityCapacityActivityIds = null;
  state.activityCapacityKey = requestKey;
  updateActivityCapacityToggleButton();
  rerenderScheduleCellsForCapacity();

  try {
    const result = await api.get(
      `/api/schedule/activity-capacity?year=${state.year}&week=${state.week}&weekday=${state.weekday}`,
      { signal: controller.signal, skipCache: true },
    );
    if (controller.signal.aborted || requestSeq !== activityCapacityState.requestSeq || requestKey !== activityCapacityRequestKey()) return;
    state.activityCapacity = {
      people: result?.people || {},
      activities: result?.activities || {},
    };
    state.activityCapacityActivityIds = normalizeActivityCapacityActivityIds(result?.visible_activity_ids);
    state.activityCapacityKey = requestKey;
    state.activityCapacityError = "";
    rerenderScheduleCellsForCapacity();
  } catch (error) {
    if (error?.name === "AbortError") return;
    if (requestSeq !== activityCapacityState.requestSeq) return;
    state.activityCapacity = { people: {}, activities: {} };
    state.activityCapacityActivityIds = null;
    state.activityCapacityError = error.message || "Kunde inte hämta historiskt snitt.";
    showToast(state.activityCapacityError, "warn");
    rerenderScheduleCellsForCapacity();
  } finally {
    if (activityCapacityState.controller === controller) {
      activityCapacityState.controller = null;
    }
    if (requestSeq === activityCapacityState.requestSeq) {
      state.activityCapacityLoading = false;
      updateActivityCapacityToggleButton();
    }
  }
}

function toggleScheduleActivityCapacity() {
  state.activityCapacityVisible = !state.activityCapacityVisible;
  writeActivityCapacityVisible(state.activityCapacityVisible);
  updateActivityCapacityToggleButton();
  if (state.activityCapacityVisible) {
    void loadScheduleActivityCapacity({ force: false });
  } else {
    activityCapacityState.controller?.abort();
    state.activityCapacityError = "";
    rerenderScheduleCellsForCapacity();
  }
}

function isActivityCapacityHotkeyEditableTarget(target) {
  if (!target) return false;
  const element = target.nodeType === Node.ELEMENT_NODE ? target : target.parentElement;
  if (!element) return false;
  return Boolean(element.closest("input, textarea, select, [contenteditable='true']"));
}

function setupActivityCapacityToggle() {
  state.activityCapacityVisible = readActivityCapacityVisible();
  updateActivityCapacityToggleButton();
  document.getElementById("capacityToggleBtn")?.addEventListener("click", () => toggleScheduleActivityCapacity());

  document.addEventListener("keydown", (event) => {
    if (event.repeat || isActivityCapacityHotkeyEditableTarget(event.target)) return;
    const key = String(event.key || "").toLowerCase();
    if (key !== "v" && key !== "h") return;
    activityCapacityState.pressedKeys.add(key);
    if (
      activityCapacityState.pressedKeys.has("v")
      && activityCapacityState.pressedKeys.has("h")
      && !activityCapacityState.toggledWhilePressed
    ) {
      event.preventDefault();
      activityCapacityState.toggledWhilePressed = true;
      toggleScheduleActivityCapacity();
    }
  }, true);
  document.addEventListener("keyup", (event) => {
    const key = String(event.key || "").toLowerCase();
    if (key !== "v" && key !== "h") return;
    activityCapacityState.pressedKeys.delete(key);
    if (!activityCapacityState.pressedKeys.has("v") && !activityCapacityState.pressedKeys.has("h")) {
      activityCapacityState.toggledWhilePressed = false;
    }
  }, true);
}

function applyScheduleData(data) {
  state.allPersons = data.persons || [];
  state.lockForeignScheduleCells = !!data.lock_foreign_schedule_cells;
  state.scheduleRevisionKey = data.revision_key || "";
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
  void loadScheduleProductivity();
  scheduleSummaryRefresh(0);
  scheduleAutomaticCalculatorRefresh(800);
  if (state.activityCapacityVisible) void loadScheduleActivityCapacity({ force: false });
  else updateActivityCapacityToggleButton();
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
  setupCalculatorToolbar();
  setupActivityCapacityToggle();

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
  await loadCalculatorProfile();

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
  window.setInterval(() => refreshCurrentHourHighlight(), 60 * 1000);
  window.setInterval(() => {
    if (selectedScheduleYmdString() === localYmdString()) void loadScheduleProductivity();
  }, 5 * 60 * 1000);
  window.setInterval(() => scheduleAutomaticCalculatorRefresh(0), 60 * 1000);

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
        scheduleSummaryRefresh(0, { refreshCalculator: true });
      }
    } catch (e) {
      showToast("Fel: " + e.message, "error");
    }
  });
}

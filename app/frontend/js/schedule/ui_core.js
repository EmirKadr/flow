// @ts-check
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
    remark: segment.remark == null ? null : String(segment.remark),
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
    normalized.remark || "",
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
    /** @type {HTMLInputElement} */ (button).disabled = readOnly;
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
  const week = Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
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
    th.dataset.hour = String(h);
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
    const person = personById(Number(/** @type {HTMLElement} */ (td).dataset.personId));
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


// @ts-check
// Utdelad ur overview.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter overview.js via <script>-tagg.

// Översikt – vecka eller månad.

const DAY_NAMES = { 1: "Måndag", 2: "Tisdag", 3: "Onsdag", 4: "Torsdag", 5: "Fredag", 6: "Lördag", 7: "Söndag" };
const DAY_SHORT = { 1: "Mån", 2: "Tis", 3: "Ons", 4: "Tor", 5: "Fre", 6: "Lör", 7: "Sön" };

const overviewState = {
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
  selectedPersonId: null,
  nameFilter: "",
  sortKey: "sort_order",
  sortAsc: true,
  undoStack: [],
  redoStack: [],
  selectedDateParts: null,
};

const overviewDrag = {
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

const overviewPersonOrderDrag = {
  sourceId: null,
  targetId: null,
  position: "after",
};

const loadState = {
  controller: null,
  requestSeq: 0,
};

const overviewAllCache = new Map();
const overviewAreaCache = new Map();
const overviewAllFetchState = {
  controller: null,
  key: "",
};
const OVERVIEW_ALL_CACHE_LIMIT = 4;
const OVERVIEW_AREA_CACHE_LIMIT = 24;
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
  if (typeof isReadOnlyUser === "function") return isReadOnlyUser(overviewState.currentUser);
  return overviewState.currentUser?.role === "viewer" && !overviewState.currentUser?.is_super_user;
}

function overviewScopeKey() {
  const user = overviewState.currentUser || {};
  return [
    user.id ?? user.username ?? "anonymous",
    user.is_super_user ? "super" : "scoped",
    user.business_id ?? "global",
  ].join(":");
}

function overviewCacheKey() {
  const period = overviewState.view === "week"
    ? `week:${overviewState.year}:${overviewState.week}`
    : `month:${overviewState.year}:${overviewState.month}`;
  return `${overviewScopeKey()}|${period}`;
}

function overviewAreaCacheKey(areaId = overviewState.areaId, baseKey = overviewCacheKey()) {
  return `${baseKey}|area:${areaId == null ? "ALLT" : Number(areaId)}`;
}

function overviewUrl(areaId = overviewState.areaId) {
  if (overviewState.view === "week") {
    return `/api/overview?year=${overviewState.year}&week=${overviewState.week}` +
      (areaId ? `&area_id=${areaId}` : "");
  }
  return `/api/overview/month?year=${overviewState.year}&month=${overviewState.month}` +
    (areaId ? `&area_id=${areaId}` : "");
}

function overviewRevisionUrl(areaId = null) {
  if (overviewState.view === "week") {
    return `/api/overview/revision?year=${overviewState.year}&week=${overviewState.week}` +
      (areaId ? `&area_id=${areaId}` : "");
  }
  return `/api/overview/revision/month?year=${overviewState.year}&month=${overviewState.month}` +
    (areaId ? `&area_id=${areaId}` : "");
}

function setOverviewAllCache(key, data) {
  overviewAllCache.delete(key);
  overviewAllCache.set(key, data);
  while (overviewAllCache.size > OVERVIEW_ALL_CACHE_LIMIT) {
    overviewAllCache.delete(overviewAllCache.keys().next().value);
  }
}

function setOverviewAreaCache(key, data) {
  overviewAreaCache.delete(key);
  overviewAreaCache.set(key, data);
  while (overviewAreaCache.size > OVERVIEW_AREA_CACHE_LIMIT) {
    overviewAreaCache.delete(overviewAreaCache.keys().next().value);
  }
}

function invalidateOverviewAllCache() {
  overviewAllCache.clear();
  overviewAreaCache.clear();
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
  return overviewDrag.active
    || overviewDrag.pending
    || overviewPersonOrderDrag.sourceId != null
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
  return overviewState.view === "week"
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
  if (overviewState.view === "week") {
    return document.querySelector(
      `#overviewBody td.day[data-person-id="${Number(cell.person_id)}"][data-weekday="${Number(cell.weekday)}"]`
    );
  }
  return document.querySelector(
    `#overviewBody td.day[data-person-id="${Number(cell.person_id)}"][data-date="${cell.date || ""}"]`
  );
}

function overviewCellIsFocused(td) {
  return td && overviewState.focusedCell?.td === td && document.activeElement?.closest("#overviewBody");
}

function patchOverviewFromAllData(allData) {
  const data = filterOverviewDataForArea(allData, overviewState.areaId);
  const personsChanged = overviewPersonSignature(overviewState.allPersons) !== overviewPersonSignature(data.persons || []);
  const daysChanged = overviewDaysSignature(overviewState.days) !== overviewDaysSignature(data.days || []);
  if (personsChanged || daysChanged) {
    applyOverviewData(data);
    return { changed: true, patched: false };
  }

  overviewState.allPersons = (data.persons || []).map((person) => ({ ...person }));
  const currentMap = overviewMatrixMap(overviewState.cells);
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

  overviewState.cells = overviewState.cells.filter((cell) => {
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
  return typeof preferredAreaIdFromFocus === "function" ? preferredAreaIdFromFocus(overviewState.areas) : null;
}

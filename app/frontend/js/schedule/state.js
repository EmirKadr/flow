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
  timer: null,
  requestSeq: 0,
  target: null,
  cacheKey: "",
  cache: new Map(),
  tooltip: null,
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
const SCHEDULE_ACTIVITY_CAPACITY_HOVER_DELAY_MS = 250;
const SCHEDULE_ACTIVITY_CAPACITY_CACHE_LIMIT = 240;
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


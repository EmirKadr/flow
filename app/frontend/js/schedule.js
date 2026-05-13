// Bemanningsvy – matris person × timme.

const HOURS = Array.from({ length: 18 }, (_, i) => 6 + i);   // 6..23
const DAYS = { 1: "Måndag", 2: "Tisdag", 3: "Onsdag", 4: "Torsdag", 5: "Fredag", 6: "Lördag", 7: "Söndag" };
const FULL_SEGMENT = { minute_start: 0, minute_end: 60 };
const HALF_SEGMENTS = [
  { minute_start: 0, minute_end: 30 },
  { minute_start: 30, minute_end: 60 },
];
const CALC_AREA_KEYS = ["GG", "MG", "AS"];

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
  summaryRows: [],
  allSummaryRows: [],
  calcSelection: "",
  calcInputs: {
    GG: { rows: "", time: "", goal: "" },
    MG: { rows: "", time: "", goal: "" },
    AS: { rows: "", time: "", goal: "" },
  },
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

function setHourPending(td, pending) {
  if (!td) return;
  td.classList.toggle("pending-save", pending);
  td.querySelectorAll("select").forEach((select) => {
    select.disabled = pending;
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

function formatHours(value) {
  const num = Number(value) || 0;
  return Number.isInteger(num) ? String(num) : num.toFixed(1).replace(/\.0$/, "");
}

function areaCodeById(id) {
  return state.areas.find((area) => area.id === id)?.code || null;
}

function areaNameByCode(code) {
  return state.areas.find((area) => area.code === code)?.name
    || ({ GG: "Granngården", MG: "Mestergruppen", AS: "Autostore" }[code] || code);
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
  const values = state.calcInputs[areaKey] || { rows: "", time: "", goal: "" };
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
  const select = document.getElementById("calcAreaSelect");
  if (!container || !select) return;

  const selectedKeys = state.calcSelection === "ALL" ? CALC_AREA_KEYS : [state.calcSelection];
  container.innerHTML = selectedKeys.map((areaKey) => {
    const values = state.calcInputs[areaKey];
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
}

function setupCalculator() {
  const select = document.getElementById("calcAreaSelect");
  if (!select) return;

  select.innerHTML = [
    '<option value="ALL">Alla</option>',
    ...CALC_AREA_KEYS.map((code) => `<option value="${code}">${escapeHtml(areaNameByCode(code))}</option>`),
  ].join("");

  if (!state.calcSelection) {
    const currentAreaCode = areaCodeById(state.areaId);
    state.calcSelection = CALC_AREA_KEYS.includes(currentAreaCode) ? currentAreaCode : "ALL";
  }

  select.value = state.calcSelection;
  if (select.dataset.bound !== "1") {
    select.addEventListener("change", (e) => {
      state.calcSelection = e.target.value;
      renderCalculator();
    });
    select.dataset.bound = "1";
  }

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

  state.activitiesActive.forEach(appendOption);
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

function scheduledActivityIdForHour(personId, hour) {
  if (!isScheduledHour(personId, hour)) return null;
  const person = personById(personId);
  return person?.home_activity_id || null;
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

function handleFullHourContextMenu(e, td) {
  e.preventDefault();
  e.stopPropagation();
  focusSegment(td, td, 0, 60);
  void toggleHourSplit(td, 0);
}

function handleSplitSegmentContextMenu(e, td, part, minuteStart, minuteEnd) {
  e.preventDefault();
  e.stopPropagation();
  focusSegment(td, part, minuteStart, minuteEnd);
  void toggleHourSplit(td, minuteStart);
}

function splitPartFromEvent(td, e) {
  const directPart = e.target.closest?.(".hour-segment");
  if (directPart && td.contains(directPart)) return directPart;

  const pointEl = document.elementFromPoint(e.clientX, e.clientY);
  const pointPart = pointEl?.closest?.(".hour-segment");
  if (pointPart && td.contains(pointPart)) return pointPart;

  const parts = Array.from(td.querySelectorAll(".hour-segment"));
  if (parts.length <= 1) return parts[0] || null;

  const rect = td.getBoundingClientRect();
  return e.clientX >= rect.left + (rect.width / 2) ? parts[1] : parts[0];
}

function activityIdForDragSource(td, minuteStart, minuteEnd) {
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  return effectiveActivityIdForRange(personId, hour, minuteStart, minuteEnd);
}

function armFullHourDrag(td, event) {
  if (event.button !== 0) return;
  if (td.dataset.split === "1") return;
  startPendingDrag(td, event, 0, 60);
}

function armHalfHourDrag(td, minuteStart, minuteEnd, event) {
  if (event.button !== 0) return;
  startPendingDrag(td, event, minuteStart, minuteEnd);
}

function renderFullHourCell(td, segment, isScheduled) {
  td.dataset.split = "0";
  td.classList.remove("split-hour", "scheduled-empty", "base-value");
  td.style.background = "#fff";
  td.dataset.isBase = "";
  td.oncontextmenu = (e) => handleFullHourContextMenu(e, td);

  const person = personById(Number(td.dataset.personId));
  const hasExplicitSegment = !!segment;
  const explicitActivityId = hasExplicitSegment ? segment.activity_id : null;
  const explicitEmptyOverride = !!segment?.empty_override;
  const scheduledActivityId = isScheduled ? (person?.home_activity_id || null) : null;
  const showScheduledDefault = explicitActivityId == null && !explicitEmptyOverride && scheduledActivityId != null;
  const showExplicitEmptyOnSchedule = explicitEmptyOverride && scheduledActivityId != null;

  if (explicitActivityId != null) {
    td.style.background = colorFor(explicitActivityId);
  } else if (showScheduledDefault) {
    td.style.background = colorFor(scheduledActivityId);
    td.dataset.isBase = "1";
  } else if (showExplicitEmptyOnSchedule) {
    td.style.background = colorFor(scheduledActivityId);
    td.classList.add("base-value");
  } else if (isScheduled) {
    td.classList.add("scheduled-empty");
  }

  const select = buildActivitySelect([explicitActivityId, scheduledActivityId]);
  select.className = "cell-select";
  select.value = explicitActivityId != null
    ? String(explicitActivityId)
    : (showScheduledDefault ? String(scheduledActivityId) : "");
  select.dataset.minuteStart = "0";
  select.dataset.minuteEnd = "60";
  select.dataset.version = String(segment?.version || 0);

  select.addEventListener("change", () => onSegmentChange(td, 0, 60));
  select.addEventListener("focus", () => focusSegment(td, td, 0, 60));
  select.addEventListener("mousedown", (e) => {
    armFullHourDrag(td, e);
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
    const part = splitPartFromEvent(td, e);
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
  const person = personById(Number(td.dataset.personId));
  const scheduledActivityId = isScheduled ? (person?.home_activity_id || null) : null;

  HALF_SEGMENTS.forEach(({ minute_start, minute_end }) => {
    const segment = currentSegment(Number(td.dataset.personId), Number(td.dataset.hour), minute_start, minute_end);
    const part = document.createElement("div");
    part.className = "hour-segment";
    part.dataset.minuteStart = String(minute_start);
    part.dataset.minuteEnd = String(minute_end);
    part.tabIndex = -1;

    if (segment.activity_id != null) {
      part.style.background = colorFor(segment.activity_id);
    } else if (!segment.empty_override && scheduledActivityId != null) {
      part.style.background = colorFor(scheduledActivityId);
    } else if (isScheduled) {
      part.classList.add("scheduled-empty-half");
    } else {
      part.style.background = "#fff";
    }

    const select = buildActivitySelect([segment.activity_id, scheduledActivityId]);
    select.className = "half-select";
    select.value = segment.activity_id != null
      ? String(segment.activity_id)
      : (!segment.empty_override && scheduledActivityId != null ? String(scheduledActivityId) : "");
    select.dataset.minuteStart = String(minute_start);
    select.dataset.minuteEnd = String(minute_end);
    select.dataset.version = String(segment.version || 0);

    select.addEventListener("change", () => onSegmentChange(td, minute_start, minute_end));
    select.addEventListener("focus", () => focusSegment(td, part, minute_start, minute_end));
    select.addEventListener("mousedown", (e) => {
      armHalfHourDrag(td, minute_start, minute_end, e);
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
    if (td.classList.contains("pending-save")) setHourPending(td, true);
    return;
  }

  const segment = segments.length === 1 ? segments[0] : null;
  renderFullHourCell(td, segment, isScheduled);
  if (td.classList.contains("pending-save")) setHourPending(td, true);
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

async function toggleHourSplit(td, mergeMinuteStart = 0) {
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  const currentSegments = sortSegments(segmentsForHour(personId, hour));

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
    replaceHourSegments(personId, hour, updatedSegments);
    renderHourCell(td);
    if (isSplitHour(updatedSegments)) {
      focusMatchingSegment(td, 0, 30);
      showToast("Cellen delades i två halvtimmar.");
    } else {
      focusMatchingSegment(td, 0, 60);
      showToast("Cellen slogs ihop till en hel timme.");
    }
    refreshSummary();
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
  drag.sourceMinuteStart = 0;
  drag.sourceMinuteEnd = 60;
  drag.sourceRow = -1;
  drag.sourceCol = -1;
  drag.currentRow = -1;
  drag.currentCol = -1;
  drag.startX = 0;
  drag.startY = 0;
}

function startPendingDrag(td, event, minuteStart = 0, minuteEnd = 60) {
  drag.pending = true;
  drag.sourceTd = td;
  drag.sourceActivityId = activityIdForDragSource(td, minuteStart, minuteEnd);
  drag.sourceMinuteStart = minuteStart;
  drag.sourceMinuteEnd = minuteEnd;
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
  const sourceMinuteStart = drag.sourceMinuteStart;
  const sourceMinuteEnd = drag.sourceMinuteEnd;
  const targets = Array.from(document.querySelectorAll("#scheduleBody td.drag-target"));
  const targetCount = targets.filter((td) => td !== sourceTd).length;
  resetDragState();

  if (targets.length === 0 || (targets.length === 1 && targets[0] === sourceTd)) return;

  const cells = targets
    .filter((td) => td !== sourceTd)
    .flatMap((td) => {
      const personId = Number(td.dataset.personId);
      const hour = Number(td.dataset.hour);
      const segments = sortSegments(segmentsForHour(personId, hour));
      const fullSegment = segments.length === 1
        && segments[0].minute_start === 0
        && segments[0].minute_end === 60
        ? segments[0]
        : null;
      const targetSegments = (sourceMinuteStart === 0 && sourceMinuteEnd === 60 && td.dataset.split === "1")
        ? HALF_SEGMENTS
        : [{ minute_start: sourceMinuteStart, minute_end: sourceMinuteEnd }];

      return targetSegments.map(({ minute_start, minute_end }) => {
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
    applySegmentsByHourResponse(resp.applied);
    refreshSummary();
    showToast(`Fyllde ${targetCount} celler`);
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
    if (!td) return;
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
  const filteredUrl = `/api/schedule/summary?year=${state.year}&week=${state.week}&weekday=${state.weekday}` +
    (state.areaId ? `&area_id=${state.areaId}` : "");
  const allUrl = `/api/schedule/summary?year=${state.year}&week=${state.week}&weekday=${state.weekday}`;
  const [rows, allRows] = await Promise.all([api.get(filteredUrl), api.get(allUrl)]);
  state.summaryRows = rows;
  state.allSummaryRows = allRows;
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
  renderCalculator();
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
  setupCalculator();
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
      showToast(`Kopierade ${r.copied} celler`);
      backdrop.remove();
      if (targetMatchesCurrentDay(copyPayload.to_year, copyPayload.to_week, copyPayload.to_weekday)) {
        applySegmentsByHourResponse(r.applied);
        refreshSummary();
      }
    } catch (e) {
      showToast("Fel: " + e.message, "error");
    }
  });
}

// @ts-check
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
  state.cells = /** @type {any} */ (new Map());
  state.hourCells = new Map();
  cells.forEach((cell) => {
    const normalized = {
      person_id: Number(cell.person_id),
      hour: Number(cell.hour),
      minute_start: Number(cell.minute_start),
      minute_end: Number(cell.minute_end),
      activity_id: cell.activity_id == null ? null : Number(cell.activity_id),
      loan_area_id: cell.loan_area_id == null ? null : Number(cell.loan_area_id),
      remark: cell.remark == null ? null : String(cell.remark),
      empty_override: !!cell.empty_override,
      version: Number(cell.version) || 0,
      updated_at: cell.updated_at || null,
      updated_by: cell.updated_by == null ? null : Number(cell.updated_by),
    };
    /** @type {any} */ (state.cells).set(segmentKey(normalized.person_id, normalized.hour, normalized.minute_start), normalized);
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
  existing.forEach((segment) => /** @type {any} */ (state.cells).delete(segmentKey(segment.person_id, segment.hour, segment.minute_start)));

  const normalized = sortSegments((segments || []).map((segment) => ({
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
  })));

  if (normalized.length === 0) {
    state.hourCells.delete(hk);
    return;
  }

  normalized.forEach((segment) => {
    /** @type {any} */ (state.cells).set(segmentKey(segment.person_id, segment.hour, segment.minute_start), segment);
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
    remark: null,
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
    remark: segment.remark == null ? null : String(segment.remark),
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
  state.undoStack.push({ kind: "schedule", label, snapshots: normalized });
  if (state.undoStack.length > 50) state.undoStack.shift();
  state.redoStack = [];
  updateUndoRedoButtons();
}

function updateUndoRedoButtons() {
  const undoBtn = document.getElementById("undoBtn");
  const redoBtn = document.getElementById("redoBtn");
  const readOnly = scheduleIsReadOnly();
  const undoAction = state.undoStack[state.undoStack.length - 1];
  const redoAction = state.redoStack[state.redoStack.length - 1];
  if (undoBtn) /** @type {HTMLInputElement} */ (undoBtn).disabled = !undoAction || (readOnly && undoAction.kind !== "summary");
  if (redoBtn) /** @type {HTMLInputElement} */ (redoBtn).disabled = !redoAction || (readOnly && redoAction.kind !== "summary");
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
    remark: segment.remark,
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
    oppositeStack.push({ kind: "schedule", label: action.label, snapshots: inverseSnapshots });
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
  const action = state.undoStack[state.undoStack.length - 1];
  if (!action) {
    showToast("Inget att ångra.", "warn");
    return;
  }
  if (action.kind === "summary") {
    if (applySummaryHistoryAction(action, "undo")) {
      state.undoStack.pop();
      state.redoStack.push(action);
      if (state.redoStack.length > 50) state.redoStack.shift();
    }
    updateUndoRedoButtons();
    return;
  }
  if (scheduleIsReadOnly()) {
    showReadOnlyToast();
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
  const action = state.redoStack[state.redoStack.length - 1];
  if (action?.kind === "summary") {
    if (applySummaryHistoryAction(action, "redo")) {
      state.redoStack.pop();
      state.undoStack.push(action);
      if (state.undoStack.length > 50) state.undoStack.shift();
    }
    updateUndoRedoButtons();
    return;
  }
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
        remark: current[0]?.remark ?? null,
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
        remark: null,
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
        remark: source.remark ?? null,
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
        remark: null,
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
      remark: null,
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


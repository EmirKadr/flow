// @ts-check
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

function historyShortcutAction(key, shiftKey = false) {
  if (key === "z" && !shiftKey) return state.undoStack[state.undoStack.length - 1];
  if (key === "z" && shiftKey) return state.redoStack[state.redoStack.length - 1];
  if (key === "y") return state.redoStack[state.redoStack.length - 1];
  return null;
}

function readOnlyAllowsHistoryShortcut(key, shiftKey = false) {
  return historyShortcutAction(key, shiftKey)?.kind === "summary";
}

function handleSelectClipboardKeys(e) {
  if (!(e.ctrlKey || e.metaKey)) return;
  const key = e.key.toLowerCase();
  if (!["c", "x", "v", "z", "y"].includes(key)) return;
  e.preventDefault();
  e.stopPropagation();
  if (key === "z") {
    if (scheduleIsReadOnly() && !readOnlyAllowsHistoryShortcut(key, e.shiftKey)) {
      showReadOnlyToast();
      return;
    }
    if (e.shiftKey) void redoLastScheduleAction();
    else void undoLastScheduleAction();
    return;
  }
  if (key === "y") {
    if (scheduleIsReadOnly() && !readOnlyAllowsHistoryShortcut(key, e.shiftKey)) {
      showReadOnlyToast();
      return;
    }
    void redoLastScheduleAction();
    return;
  }
  if (scheduleIsReadOnly() && key !== "c") {
    showReadOnlyToast();
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
    if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || /** @type {HTMLElement} */ (active).isContentEditable)) return;
    if (key === "z") {
      e.preventDefault();
      e.stopPropagation();
      if (scheduleIsReadOnly() && !readOnlyAllowsHistoryShortcut(key, e.shiftKey)) {
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
      if (scheduleIsReadOnly() && !readOnlyAllowsHistoryShortcut(key, e.shiftKey)) {
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
    const r = Number(/** @type {HTMLElement} */ (td).dataset.rowIndex);
    const c = Number(/** @type {HTMLElement} */ (td).dataset.colIndex);
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
    if (/** @type {HTMLElement} */ (td).dataset.split !== "1") return;
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
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
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
    (td !== sourceTd || sourceIsSplit) && !isHourLocked(Number(/** @type {HTMLElement} */ (td).dataset.personId), Number(/** @type {HTMLElement} */ (td).dataset.hour))
  );
  const lockedTargetCount = targets.filter((td) =>
    (td !== sourceTd || sourceIsSplit) && isHourLocked(Number(/** @type {HTMLElement} */ (td).dataset.personId), Number(/** @type {HTMLElement} */ (td).dataset.hour))
  ).length;
  if (!editableTargets.length) {
    if (lockedTargetCount) showLockedCellToast();
    return;
  }

  const cells = targets
    .filter((td) => editableTargets.includes(td))
    .flatMap((td) => {
      const personId = Number(/** @type {HTMLElement} */ (td).dataset.personId);
      const hour = Number(/** @type {HTMLElement} */ (td).dataset.hour);
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
    if (/** @type {Element} */ (e.target).closest("select")) return;
    const td = /** @type {Element} */ (e.target).closest("td[data-hour]");
    if (!td) return;
    const part = /** @type {Element} */ (e.target).closest(".hour-segment");
    if (part) {
      startPendingDrag(td, e, Number(/** @type {HTMLElement} */ (part).dataset.minuteStart), Number(/** @type {HTMLElement} */ (part).dataset.minuteEnd));
      return;
    }
    if (/** @type {HTMLElement} */ (td).dataset.split === "1") return;
    startPendingDrag(td, e, 0, 60);
  });

  body.addEventListener("contextmenu", (e) => {
    const td = /** @type {Element} */ (e.target).closest("td[data-hour]");
    if (!td) return;
    if (/** @type {HTMLElement} */ (td).dataset.split === "1") {
      const part = splitPartFromEvent(td, e);
      if (!part) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      if (part) openScheduleCellContextMenu(e, td, part);
      return;
    }
    openScheduleCellContextMenu(e, td);
  }, true);

  body.addEventListener("dblclick", (e) => {
    const td = /** @type {Element} */ (e.target).closest("td[data-hour]");
    if (!td) return;
    if (/** @type {HTMLElement} */ (td).dataset.split === "1") {
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

  document.addEventListener("mousemove", (e) => {
    if (!drag.pending && !drag.active) return;
    const moved = Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY);
    if (!drag.active) {
      if (moved < 5) return;
      activateDrag();
    }
    const td = scheduleCellFromPoint(e.clientX, e.clientY);
    if (!td) return;
    drag.currentRow = Number(/** @type {HTMLElement} */ (td).dataset.rowIndex);
    drag.currentCol = Number(/** @type {HTMLElement} */ (td).dataset.colIndex);
    const targetRange = targetRangeFromPoint(td, e.clientX, e.clientY);
    drag.currentTargetMinuteStart = targetRange.minute_start;
    drag.currentTargetMinuteEnd = targetRange.minute_end;
    if (/** @type {HTMLElement} */ (td).dataset.split === "1") {
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
    if (!/** @type {Element} */ (e.target).closest("#scheduleBody td[data-hour]")) return;
    e.preventDefault();
    e.stopPropagation();
    drag.suppressClick = false;
  }, true);

  body.addEventListener("click", (e) => {
    if (drag.suppressClick) return;
    const row = /** @type {Element} */ (e.target).closest("tr[data-person-id]");
    if (row && body.contains(row)) selectPersonRow(/** @type {HTMLElement} */ (row).dataset.personId);
    const td = /** @type {Element} */ (e.target).closest("td[data-hour]");
    if (!td) return;
    if (/** @type {HTMLElement} */ (td).dataset.split === "1") {
      const part = /** @type {Element} */ (e.target).closest(".hour-segment");
      if (part) {
        focusSegment(td, part, Number(/** @type {HTMLElement} */ (part).dataset.minuteStart), Number(/** @type {HTMLElement} */ (part).dataset.minuteEnd));
      }
      return;
    }
    focusSegment(td, td, 0, 60);
  });

  body.addEventListener("change", (e) => {
    const td = /** @type {Element} */ (e.target).closest("td[data-hour]");
    if (!td) return;
    if (/** @type {HTMLElement} */ (td).dataset.split === "1") {
      const part = /** @type {Element} */ (e.target).closest(".hour-segment");
      if (part) {
        focusSegment(td, part, Number(/** @type {HTMLElement} */ (part).dataset.minuteStart), Number(/** @type {HTMLElement} */ (part).dataset.minuteEnd));
      }
      return;
    }
    focusSegment(td, td, 0, 60);
  });
}


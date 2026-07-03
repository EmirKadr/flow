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
    const row = e.target.closest("tr[data-person-id]");
    if (row && body.contains(row)) selectPersonRow(row.dataset.personId);
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

  if (typeof setAreaFocusAreas === "function") {
    setAreaFocusAreas(areas, state.currentUser);
  }
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

function renderOverviewFromCache() {
  const baseKey = overviewCacheKey();
  const cachedAll = overviewAllCache.get(baseKey);
  const cached = cachedAll
    ? filterOverviewDataForArea(cachedAll, state.areaId)
    : overviewAreaCache.get(overviewAreaCacheKey(state.areaId, baseKey));
  if (!cached) return false;
  loadState.controller?.abort();
  loadState.requestSeq += 1;
  applyOverviewData(cached);
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
    const data = await api.get(overviewUrl(null), { signal: controller.signal, cacheTtlMs: 25 * 1000 });
    if (controller.signal.aborted) return;
    const allData = filterOverviewDataForArea(data, null);
    setOverviewAllCache(key, allData);
    setOverviewAreaCache(overviewAreaCacheKey(null, key), allData);
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

    const fresh = await api.get(overviewUrl(null), { signal: controller.signal, cacheTtlMs: 25 * 1000 });
    if (controller.signal.aborted || key !== overviewCacheKey()) return;
    const freshAllData = filterOverviewDataForArea(fresh, null);
    setOverviewAllCache(key, freshAllData);
    setOverviewAreaCache(overviewAreaCacheKey(null, key), freshAllData);
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
  if (renderOverviewFromCache()) {
    void prefetchAllOverview();
    return true;
  }
  const requestSeq = ++loadState.requestSeq;
  loadState.controller?.abort();
  const controller = new AbortController();
  loadState.controller = controller;
  try {

  if (state.view === "week") {
    const requestedAreaId = state.areaId;
    const data = await api.get(overviewUrl(null), { signal: controller.signal, cacheTtlMs: 25 * 1000 });
    if (controller.signal.aborted || requestSeq !== loadState.requestSeq) return false;
    const baseKey = overviewCacheKey();
    const allData = filterOverviewDataForArea(data, null);
    const cachedData = filterOverviewDataForArea(data, requestedAreaId);
    setOverviewAllCache(baseKey, allData);
    setOverviewAreaCache(overviewAreaCacheKey(null, baseKey), allData);
    setOverviewAreaCache(overviewAreaCacheKey(requestedAreaId, baseKey), cachedData);
    applyOverviewData(cachedData);
    return true;
  } else {
    const requestedAreaId = state.areaId;
    const data = await api.get(overviewUrl(null), { signal: controller.signal, cacheTtlMs: 25 * 1000 });
    if (controller.signal.aborted || requestSeq !== loadState.requestSeq) return false;
    const baseKey = overviewCacheKey();
    const allData = filterOverviewDataForArea(data, null);
    const cachedData = filterOverviewDataForArea(data, requestedAreaId);
    setOverviewAllCache(baseKey, allData);
    setOverviewAreaCache(overviewAreaCacheKey(null, baseKey), allData);
    setOverviewAreaCache(overviewAreaCacheKey(requestedAreaId, baseKey), cachedData);
    applyOverviewData(cachedData);
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
  if (typeof setupPresencePrintButton === "function") {
    setupPresencePrintButton("presenceBtn", {
      getSelection: () => overviewPresenceSelection(),
    });
  }
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

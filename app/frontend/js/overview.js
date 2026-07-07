// @ts-check
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
  if (u) /** @type {HTMLInputElement} */ (u).disabled = readOnly || overviewState.undoStack.length === 0;
  if (r) /** @type {HTMLInputElement} */ (r).disabled = readOnly || overviewState.redoStack.length === 0;
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
  overviewState.undoStack.push({ label, days: filtered });
  if (overviewState.undoStack.length > 50) overviewState.undoStack.shift();
  overviewState.redoStack = [];
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
  const action = overviewState.undoStack[overviewState.undoStack.length - 1];
  if (!action) { showToast("Inget att ångra.", "warn"); return; }
  const ok = await applyOverviewHistory(action, "undo");
  if (ok) {
    overviewState.undoStack.pop();
    overviewState.redoStack.push(action);
    if (overviewState.redoStack.length > 50) overviewState.redoStack.shift();
    showToast(`Ångrade: ${action.label}`);
  }
  updateUndoRedoButtons();
}

async function redoLastOverviewAction() {
  if (overviewIsReadOnly()) {
    showReadOnlyToast();
    return;
  }
  const action = overviewState.redoStack[overviewState.redoStack.length - 1];
  if (!action) { showToast("Inget att göra om.", "warn"); return; }
  const ok = await applyOverviewHistory(action, "redo");
  if (ok) {
    overviewState.redoStack.pop();
    overviewState.undoStack.push(action);
    if (overviewState.undoStack.length > 50) overviewState.undoStack.shift();
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
  document.querySelectorAll("td.day.overviewDrag-target").forEach((t) => t.classList.remove("overviewDrag-target"));
  if (!overviewDrag.active) return;
  const r0 = Math.min(overviewDrag.sourceRow, overviewDrag.currentRow);
  const r1 = Math.max(overviewDrag.sourceRow, overviewDrag.currentRow);
  const c0 = Math.min(overviewDrag.sourceCol, overviewDrag.currentCol);
  const c1 = Math.max(overviewDrag.sourceCol, overviewDrag.currentCol);

  document.querySelectorAll("#overviewBody td.day").forEach((td) => {
    const r = /** @type {HTMLTableRowElement} */ (td.parentElement).rowIndex;
    const c = /** @type {HTMLTableCellElement} */ (td).cellIndex;
    if (r >= r0 && r <= r1 && c >= c0 && c <= c1) td.classList.add("overviewDrag-target");
  });
}

function resetDragState() {
  document.body.classList.remove("dragging-ov");
  document.querySelectorAll("td.day.overviewDrag-target").forEach((t) => t.classList.remove("overviewDrag-target"));
  overviewDrag.active = false;
  overviewDrag.pending = false;
  overviewDrag.sourceCell = null;
  overviewDrag.sourceTd = null;
  overviewDrag.sourceRow = -1;
  overviewDrag.sourceCol = -1;
  overviewDrag.currentRow = -1;
  overviewDrag.currentCol = -1;
  overviewDrag.startX = 0;
  overviewDrag.startY = 0;
}

function startPendingDrag(td, event) {
  if (overviewIsReadOnly()) return;
  overviewDrag.pending = true;
  overviewDrag.sourceTd = td;
  overviewDrag.sourceCell = {
    activity_id: td.dataset.activityId ? Number(td.dataset.activityId) : null,
  };
  overviewDrag.sourceRow = td.parentElement.rowIndex;
  overviewDrag.sourceCol = td.cellIndex;
  overviewDrag.currentRow = overviewDrag.sourceRow;
  overviewDrag.currentCol = overviewDrag.sourceCol;
  overviewDrag.startX = event.clientX;
  overviewDrag.startY = event.clientY;
}

function activateDrag() {
  if (!overviewDrag.pending || overviewDrag.active || !overviewDrag.sourceTd) return;
  overviewDrag.pending = false;
  overviewDrag.active = true;
  document.body.classList.add("dragging-ov");
  if (document.activeElement?.tagName === "SELECT") {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
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
    const td = e.target instanceof Element ? /** @type {HTMLElement | null} */ (e.target.closest("td.day")) : null;
    if (!td || td.classList.contains("is-off")) return;
    startPendingDrag(td, e);
  });

  document.addEventListener("mousemove", (e) => {
    if (!overviewDrag.pending && !overviewDrag.active) return;
    const moved = Math.hypot(e.clientX - overviewDrag.startX, e.clientY - overviewDrag.startY);
    if (!overviewDrag.active) {
      if (moved < 5) return;
      activateDrag();
    }
    const td = overviewCellFromPoint(e.clientX, e.clientY);
    if (!td) return;
    overviewDrag.currentRow = /** @type {HTMLTableRowElement} */ (td.parentElement).rowIndex;
    overviewDrag.currentCol = /** @type {HTMLTableCellElement} */ (td).cellIndex;
    updateDragTargets();
  });

  document.addEventListener("mouseup", async () => {
    if (overviewIsReadOnly()) {
      if (overviewDrag.pending || overviewDrag.active) resetDragState();
      return;
    }
    if (overviewDrag.pending && !overviewDrag.active) {
      resetDragState();
      return;
    }
    if (!overviewDrag.active) return;
    overviewDrag.suppressClick = true;
    const targets = Array.from(document.querySelectorAll("#overviewBody td.day.overviewDrag-target"));
    const sourceActivityId = overviewDrag.sourceCell?.activity_id ?? null;
    resetDragState();
    setTimeout(() => { overviewDrag.suppressClick = false; }, 0);

    if (targets.length <= 1) return;
    if (targets.length > 100) { showToast("För många celler (max 100)", "error"); return; }

    const days = targets.map((td) => ({
      person_id: Number(/** @type {HTMLElement} */ (td).dataset.personId),
      year: Number(/** @type {HTMLElement} */ (td).dataset.year),
      week: Number(/** @type {HTMLElement} */ (td).dataset.week),
      weekday: Number(/** @type {HTMLElement} */ (td).dataset.weekday),
      activity_id: sourceActivityId,
    }));
    const snapshots = new Map();
    targets.forEach((td) => {
      const key = dayRequestKey(
        Number(/** @type {HTMLElement} */ (td).dataset.personId),
        Number(/** @type {HTMLElement} */ (td).dataset.year),
        Number(/** @type {HTMLElement} */ (td).dataset.week),
        Number(/** @type {HTMLElement} */ (td).dataset.weekday),
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
          Number(/** @type {HTMLElement} */ (td).dataset.personId),
          Number(/** @type {HTMLElement} */ (td).dataset.year),
          Number(/** @type {HTMLElement} */ (td).dataset.week),
          Number(/** @type {HTMLElement} */ (td).dataset.weekday),
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
      if (undoDays.length) pushOverviewUndo("overviewDrag-bemanning", undoDays);
      showToast(`Drag klar: skrev ${resp.written || 0} h, tog bort ${resp.deleted || 0} h${errorCount ? `, ${errorCount} fel` : ""}`);
    } catch (e) {
      targets.forEach((td) => {
        const key = dayRequestKey(
          Number(/** @type {HTMLElement} */ (td).dataset.personId),
          Number(/** @type {HTMLElement} */ (td).dataset.year),
          Number(/** @type {HTMLElement} */ (td).dataset.week),
          Number(/** @type {HTMLElement} */ (td).dataset.weekday),
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
    if (!overviewDrag.suppressClick) return;
    if (!(e.target instanceof Element && e.target.closest("#overviewBody td.day"))) return;
    e.preventDefault();
    e.stopPropagation();
    overviewDrag.suppressClick = false;
  }, true);

  body.addEventListener("click", (e) => {
    if (overviewDrag.suppressClick) return;
    const row = e.target instanceof Element ? /** @type {HTMLElement | null} */ (e.target.closest("tr[data-person-id]")) : null;
    if (row && body.contains(row)) selectPersonRow(row.dataset.personId);
    const td = e.target instanceof Element ? /** @type {HTMLElement | null} */ (e.target.closest("td.day")) : null;
    if (!td || td.classList.contains("is-off")) return;
    focusDayCell(td);
  });

  body.addEventListener("change", (e) => {
    const td = e.target instanceof Element ? /** @type {HTMLElement | null} */ (e.target.closest("td.day")) : null;
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
  overviewState.areas = areas;
  overviewState.activitiesActive = activities;
  overviewState.activities = activitiesAll;

  if (typeof setAreaFocusAreas === "function") {
    setAreaFocusAreas(areas, overviewState.currentUser);
  }
  overviewState.areaId = preferredAreaIdForCurrentUser();
}

function applyOverviewData(data) {
  overviewState.allPersons = (data.persons || []).map((person) => ({ ...person }));
  refreshPersons();
  overviewState.cells = (data.matrix || []).map((cell) => ({ ...cell }));
  overviewState.days = overviewState.view === "month" ? (data.days || []).map((day) => ({ ...day })) : [];
  overviewState.focusedCell = null;
  const areaName = overviewState.areaId == null ? "Alla" : (overviewState.areas.find((a) => a.id === overviewState.areaId)?.name || "");

  if (overviewState.view === "week") {
    document.getElementById("sectionTitle").textContent = `Översikt – ${areaName} – V${overviewState.week}/${overviewState.year}`;
    buildWeekHeader();
    buildWeekBody();
  } else {
    const monthName = document.querySelector(`#monthSelect option[value="${overviewState.month}"]`)?.textContent || overviewState.month;
    document.getElementById("sectionTitle").textContent = `Översikt – ${areaName} – ${monthName} ${overviewState.year}`;
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
    ? filterOverviewDataForArea(cachedAll, overviewState.areaId)
    : overviewAreaCache.get(overviewAreaCacheKey(overviewState.areaId, baseKey));
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

  if (overviewState.view === "week") {
    const requestedAreaId = overviewState.areaId;
    // SWR-pilot: måla senaste snapshot direkt (sidbyte) medan färskt data hämtas.
    const snapshot = api.readSwrSnapshot?.(overviewUrl(null));
    if (snapshot) {
      applyOverviewData(filterOverviewDataForArea(snapshot, requestedAreaId));
      api.setSwrRefreshIndicator?.(true);
    }
    const data = await api.get(overviewUrl(null), { signal: controller.signal, cacheTtlMs: 25 * 1000, swrSnapshot: true });
    api.setSwrRefreshIndicator?.(false);
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
    const requestedAreaId = overviewState.areaId;
    const snapshot = api.readSwrSnapshot?.(overviewUrl(null));
    if (snapshot) {
      applyOverviewData(filterOverviewDataForArea(snapshot, requestedAreaId));
      api.setSwrRefreshIndicator?.(true);
    }
    const data = await api.get(overviewUrl(null), { signal: controller.signal, cacheTtlMs: 25 * 1000, swrSnapshot: true });
    api.setSwrRefreshIndicator?.(false);
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
  } catch (err) {
    api.setSwrRefreshIndicator?.(false);
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
  if (overviewState.view === "week") {
    overviewState.week += delta;
    if (overviewState.week < 1) { overviewState.year -= 1; overviewState.week = 52; }
    if (overviewState.week > 53) { overviewState.year += 1; overviewState.week = 1; }
    /** @type {HTMLInputElement} */ (document.getElementById("yearInput")).value = String(overviewState.year);
    /** @type {HTMLInputElement} */ (document.getElementById("weekInput")).value = String(overviewState.week);
  } else {
    overviewState.month += delta;
    if (overviewState.month < 1) { overviewState.year -= 1; overviewState.month = 12; }
    if (overviewState.month > 12) { overviewState.year += 1; overviewState.month = 1; }
    /** @type {HTMLInputElement} */ (document.getElementById("yearInput")).value = String(overviewState.year);
    /** @type {HTMLInputElement} */ (document.getElementById("monthSelect")).value = String(overviewState.month);
  }
  persistOverviewState();
  load();
}

function updateViewVisibility() {
  const isMonth = overviewState.view === "month";
  document.querySelectorAll(".week-only").forEach((el) => (/** @type {HTMLElement} */ (el).hidden = isMonth));
  document.querySelectorAll(".month-only").forEach((el) => (/** @type {HTMLElement} */ (el).hidden = !isMonth));
}


// ---- Init ----
(async () => {
  overviewState.currentUser = await initPage("overview");
  if (!overviewState.currentUser) return;
  applyOverviewReadOnlyMode();
  await loadInitial();

  const stored = readSelectedDate();
  if (stored) {
    overviewState.selectedDateParts = stored;
    const [y, m, d] = stored;
    const wk = isoWeek(new Date(Date.UTC(y, m - 1, d)));
    overviewState.year = wk.year;
    overviewState.week = wk.week;
    overviewState.month = m;
  } else {
    const nowDate = new Date();
    overviewState.selectedDateParts = [nowDate.getFullYear(), nowDate.getMonth() + 1, nowDate.getDate()];
    const now = isoWeek(nowDate);
    overviewState.year = now.year;
    overviewState.week = now.week;
    overviewState.month = nowDate.getMonth() + 1;
  }

  /** @type {HTMLInputElement} */ (document.getElementById("yearInput")).value = String(overviewState.year);
  /** @type {HTMLInputElement} */ (document.getElementById("weekInput")).value = String(overviewState.week);
  /** @type {HTMLInputElement} */ (document.getElementById("monthSelect")).value = String(overviewState.month);
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
    overviewState.year = Number(/** @type {HTMLInputElement} */ (document.getElementById("yearInput")).value) || overviewState.year;
    overviewState.week = Number(/** @type {HTMLInputElement} */ (document.getElementById("weekInput")).value) || overviewState.week;
    overviewState.month = Number(/** @type {HTMLInputElement} */ (document.getElementById("monthSelect")).value) || overviewState.month;
    persistOverviewState();
    await load();
  };

  document.getElementById("yearInput").addEventListener("change", onControlChange);
  document.getElementById("weekInput").addEventListener("change", onControlChange);
  document.getElementById("monthSelect").addEventListener("change", onControlChange);
  window.addEventListener("flow:areaFocusChanged", async () => {
    markOverviewActivity();
    overviewState.areaId = preferredAreaIdForCurrentUser();
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
    if (active instanceof HTMLElement && (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.isContentEditable)) return;
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
    overviewState.view = /** @type {HTMLInputElement} */ (e.target).value;
    updateViewVisibility();
    persistOverviewState();
    load();
  });

  document.getElementById("nameFilter").addEventListener("input", (e) => {
    overviewState.nameFilter = /** @type {HTMLInputElement} */ (e.target).value;
    refreshPersons();
    if (overviewState.view === "week") buildWeekBody();
    else buildMonthBody();
    setupOverviewHorizontalScroll();
  });
  document.getElementById("nameFilter").addEventListener("mousedown", (e) => e.stopPropagation());
  document.getElementById("nameFilter").addEventListener("click", (e) => e.stopPropagation());

  // Klick på Person-rubrik → sort
  document.addEventListener("click", (e) => {
    const th = e.target instanceof Element ? /** @type {HTMLElement | null} */ (e.target.closest("table.overview th[data-sort]")) : null;
    if (!th) return;
    if (th.dataset.filterTrigger && !e.shiftKey) {
      focusNameFilter();
      return;
    }
    const key = th.dataset.sort;
    if (overviewState.sortKey === key) overviewState.sortAsc = !overviewState.sortAsc;
    else { overviewState.sortKey = key; overviewState.sortAsc = true; }
    refreshPersons();
    if (overviewState.view === "week") buildWeekBody();
    else buildMonthBody();
    setupOverviewHorizontalScroll();
  });
})();

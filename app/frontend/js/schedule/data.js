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
  if (typeof loadScheduleRfidEvents === "function") {
    void loadScheduleRfidEvents({ silent: true });
  }
  void loadScheduleProductivity();
  scheduleSummaryRefresh(0);
  scheduleAutomaticCalculatorRefresh(800);
  hideActivityCapacityTooltip({ abort: true });
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


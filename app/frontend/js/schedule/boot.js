// @ts-check
(async () => {
  state.currentUser = await initPage("schedule", { requirePlanningView: true, denyRedirect: "/overblick.html" });
  if (!state.currentUser) return;
  applyScheduleReadOnlyMode();
  await loadAreasAndActivities();
  setupCalculatorToolbar();
  setupActivityCapacityHover();

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
    const dateInput = /** @type {HTMLInputElement | null} */ (document.getElementById("dateInput"));
    const dateDisplay = document.getElementById("dateDisplayText");
    if (dateInput) dateInput.value = ymd;
    if (dateDisplay) dateDisplay.textContent = ymd;
  };

  const writeYWDToInputs = () => {
    /** @type {HTMLInputElement} */ (document.getElementById("yearInput")).value = String(state.year);
    /** @type {HTMLInputElement} */ (document.getElementById("weekInput")).value = String(state.week);
    /** @type {HTMLSelectElement} */ (document.getElementById("daySelect")).value = String(state.weekday);
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
    state.year = Number(/** @type {HTMLInputElement} */ (document.getElementById("yearInput")).value) || state.year;
    state.week = Number(/** @type {HTMLInputElement} */ (document.getElementById("weekInput")).value) || state.week;
    state.weekday = Number(/** @type {HTMLSelectElement} */ (document.getElementById("daySelect")).value);
    syncCalculatorWithSelectedArea();
    syncDateInputFromState();
    persistState();
    refreshCurrentHourHighlight();
    await loadSchedule();
  };

  const onDateChange = async () => {
    markScheduleActivity();
    const date = dateFromYmd(/** @type {HTMLInputElement} */ (document.getElementById("dateInput")).value);
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
  const getSchedulePrintSelection = () => ({
    year: state.year,
    week: state.week,
    weekday: state.weekday,
    date: selectedScheduleYmdString(),
    areaId: state.areaId,
    areaName: state.areaId == null
      ? "Alla områden"
      : (state.areas.find((area) => area.id === state.areaId)?.name || "Nuvarande område"),
  });
  if (typeof setupPresencePrintButton === "function") {
    setupPresencePrintButton("presenceBtn", { getSelection: getSchedulePrintSelection });
  }
  if (typeof setupSchedulePrintButton === "function") {
    setupSchedulePrintButton("printBtn", { getSelection: getSchedulePrintSelection });
  }
  document.getElementById("undoBtn").addEventListener("click", () => undoLastScheduleAction());
  document.getElementById("redoBtn").addEventListener("click", () => redoLastScheduleAction());
  updateUndoRedoButtons();

  document.getElementById("nameFilter").addEventListener("input", (e) => {
    state.nameFilter = e.target instanceof HTMLInputElement ? e.target.value : "";
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

  /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll("table.matrix th[data-sort]")).forEach((th) => {
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


// @ts-check
function homeActivityIdForPerson(person) {
  return person?.home_activity_id || null;
}

function scheduleSameBusiness(leftBusinessId, rightBusinessId) {
  if (leftBusinessId == null || rightBusinessId == null || leftBusinessId === "" || rightBusinessId === "") {
    return true;
  }
  const left = Number(leftBusinessId);
  const right = Number(rightBusinessId);
  if (!Number.isFinite(left) || !Number.isFinite(right)) return true;
  return left === right;
}

function scheduleLoanActivityForArea(area, person) {
  const areaId = Number(area?.id);
  if (!Number.isFinite(areaId)) return null;
  const candidates = state.activities
    .filter((activity) =>
      activity?.is_active !== false
      && Number(activity.area_id) === areaId
      && activity.category !== "absence"
      && scheduleSameBusiness(activity.business_id, person?.business_id)
    )
    .sort((a, b) => {
      const aw = a.category === "work" ? 0 : 1;
      const bw = b.category === "work" ? 0 : 1;
      return aw - bw || (Number(a.sort_order) || 0) - (Number(b.sort_order) || 0) || a.label.localeCompare(b.label);
    });
  const preferredCode = area?.code ? `${String(area.code).trim().toUpperCase()}_VM` : "";
  return candidates.find((activity) => String(activity.code || "").trim().toUpperCase() === preferredCode)
    || candidates[0]
    || null;
}

function scheduleLoanTargetOptions(person) {
  const homeAreaId = Number(person?.home_area_id);
  return state.areas
    .filter((area) => {
      const areaId = Number(area?.id);
      if (!Number.isFinite(areaId) || area?.is_active === false) return false;
      if (Number.isFinite(homeAreaId) && areaId === homeAreaId) return false;
      if (typeof isAllAreasMarker === "function" && isAllAreasMarker(area)) return false;
      if (String(area?.code || "").trim().toUpperCase() === "ANNAT") return false;
      return scheduleSameBusiness(area.business_id, person?.business_id);
    })
    .map((area) => ({ area }))
    .sort((a, b) =>
      (Number(a.area.sort_order) || 0) - (Number(b.area.sort_order) || 0)
      || String(a.area.name || a.area.code || "").localeCompare(String(b.area.name || b.area.code || ""))
    );
}

function scheduleLoanHoursForPerson(personId) {
  const scheduled = state.scheduledHours[Number(personId)];
  return HOURS.filter((hour) => scheduled?.has(hour) || segmentsForHour(personId, hour).length > 0);
}

function scheduleLoanStartHour() {
  const current = currentHourIfToday();
  if (current != null) return Math.max(HOURS[0], Math.min(HOURS[HOURS.length - 1], current));
  const focusedHour = Number(state.focusedCell?.hour);
  if (Number.isFinite(focusedHour) && HOURS.includes(focusedHour)) return focusedHour;
  return null;
}

function scheduleLoanHourLabel(hour) {
  if (hour == null || !Number.isFinite(Number(hour))) return "";
  return `${String(hour).padStart(2, "0")}:00`;
}

function scheduleLoanStartHint() {
  const startHour = scheduleLoanStartHour();
  return startHour == null ? "Klicka först på starttimme" : `Tomt från ${scheduleLoanHourLabel(startHour)}`;
}

function scheduleLoanCellsForHour(personId, hour, areaId) {
  const segments = segmentsForHour(personId, hour);
  const fullSegment = segments.find((segment) => segment.minute_start === 0 && segment.minute_end === 60) || null;
  const targetRanges = (isSplitHour(segments) || segments.some((segment) => isPartialRange(segment)))
    ? splitRangesForSegments(segments)
    : [FULL_SEGMENT];
  return targetRanges.map(({ minute_start, minute_end }) => {
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
      person_id: Number(personId),
      activity_id: null,
      loan_area_id: Number(areaId),
      expected_version: expectedVersion,
    };
  });
}

function closeScheduleLoanMenu() {
  if (!scheduleLoanMenu) return;
  scheduleLoanMenu.remove();
  scheduleLoanMenu = null;
  document.removeEventListener("pointerdown", handleScheduleLoanMenuPointerDown);
  document.removeEventListener("keydown", handleScheduleLoanMenuKeydown);
  document.removeEventListener("scroll", handleScheduleLoanMenuScroll, true);
  window.removeEventListener("resize", closeScheduleLoanMenu);
}

function handleScheduleLoanMenuPointerDown(event) {
  if (!scheduleLoanMenu || scheduleLoanMenu.contains(event.target)) return;
  closeScheduleLoanMenu();
}

function handleScheduleLoanMenuKeydown(event) {
  if (event.key === "Escape") closeScheduleLoanMenu();
}

function handleScheduleLoanMenuScroll(event) {
  if (scheduleLoanMenu?.contains(event.target)) return;
  closeScheduleLoanMenu();
}

function openScheduleLoanMenu(event, person) {
  event.preventDefault();
  event.stopPropagation();
  closeScheduleLoanMenu();

  if (scheduleIsReadOnly()) {
    showReadOnlyToast();
    return;
  }

  const options = scheduleLoanTargetOptions(person);
  if (!options.length) {
    showToast("Inga andra aktiva områden finns för personen.", "warn", 5000);
    return;
  }

  const menu = document.createElement("div");
  menu.className = "schedule-loan-menu";
  menu.setAttribute("role", "menu");
  menu.style.left = "0px";
  menu.style.top = "0px";

  const title = document.createElement("div");
  title.className = "schedule-loan-menu-title";
  title.textContent = person?.name || "Person";
  menu.appendChild(title);

  options.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("role", "menuitem");

    const label = document.createElement("span");
    label.textContent = `Skicka till ${option.area.name || option.area.code}`;
    button.appendChild(label);

    const meta = document.createElement("small");
    meta.textContent = scheduleLoanStartHint();
    button.appendChild(meta);

    button.addEventListener("click", () => {
      closeScheduleLoanMenu();
      void sendPersonToArea(person.id, option.area.id);
    });
    menu.appendChild(button);
  });

  document.body.appendChild(menu);
  scheduleLoanMenu = menu;
  const rect = menu.getBoundingClientRect();
  const left = Math.max(8, Math.min(event.clientX, window.innerWidth - rect.width - 8));
  const top = Math.max(8, Math.min(event.clientY, window.innerHeight - rect.height - 8));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;

  window.setTimeout(() => {
    document.addEventListener("pointerdown", handleScheduleLoanMenuPointerDown);
    document.addEventListener("keydown", handleScheduleLoanMenuKeydown);
    document.addEventListener("scroll", handleScheduleLoanMenuScroll, true);
    window.addEventListener("resize", closeScheduleLoanMenu);
  }, 0);
}

async function sendPersonToArea(personId, areaId) {
  if (scheduleIsReadOnly()) {
    showReadOnlyToast();
    return;
  }
  const person = personById(Number(personId));
  const option = scheduleLoanTargetOptions(person).find((item) => Number(item.area.id) === Number(areaId));
  if (!person || !option) {
    showToast("Kunde inte hitta område för utlåningen.", "error", 6000);
    return;
  }

  const startHour = scheduleLoanStartHour();
  if (startHour == null) {
    showToast("Klicka först på timmen där flytten ska börja, eller välj dagens datum så aktuell timme kan användas.", "warn", 7000);
    return;
  }
  const hours = scheduleLoanHoursForPerson(person.id).filter((hour) => hour >= startHour);
  if (!hours.length) {
    showToast(`Personen saknar schemalagda timmar från ${scheduleLoanHourLabel(startHour)} den här dagen.`, "warn", 5000);
    return;
  }

  const lockedHours = [];
  const cells = [];
  hours.forEach((hour) => {
    if (isHourLocked(person.id, hour)) {
      lockedHours.push(hour);
      return;
    }
    cells.push(...scheduleLoanCellsForHour(person.id, hour, option.area.id));
  });

  if (!cells.length) {
    showLockedCellToast();
    return;
  }
  if (cells.length > 200) {
    showToast("För många celler eller delar (max 200)", "error");
    return;
  }

  markScheduleActivity();
  const snapshots = snapshotHoursFromCells(cells);
  const optimisticByHour = new Map();
  cells.forEach((cell) => {
    const key = hourKey(cell.person_id, cell.hour);
    if (!optimisticByHour.has(key)) optimisticByHour.set(key, []);
    optimisticByHour.get(key).push(cell);
  });
  optimisticByHour.forEach((items, key) => {
    const [pid, hour] = key.split(":").map(Number);
    replaceHourSegments(pid, hour, optimisticSegmentsForHour(pid, hour, items));
    const td = getHourTd(pid, hour);
    if (!td) return;
    setHourPending(td, true);
    renderHourCell(td);
  });

  try {
    const resp = await api.post("/api/schedule/cells", { cells, atomic: true, action: "loan_to_area" });
    invalidateScheduleAllCache();
    pushScheduleUndo(`skicka ${person.name} till ${option.area.name || option.area.code}`, snapshots);
    applySegmentsByHourResponse(resp.applied);
    scheduleSummaryRefresh(0, { refreshCalculator: true });
    const changedHours = new Set(cells.map((cell) => hourKey(cell.person_id, cell.hour))).size;
    showToast(
      lockedHours.length
        ? `Skickade ${person.name} till ${option.area.name || option.area.code} från ${scheduleLoanHourLabel(startHour)} (${changedHours} tim), hoppade över ${lockedHours.length} låsta`
        : `Skickade ${person.name} till ${option.area.name || option.area.code} från ${scheduleLoanHourLabel(startHour)} (${changedHours} tim)`,
      "success"
    );
  } catch (error) {
    restoreHourSnapshots(snapshots);
    if (error.status === 409) {
      showToast(`${error.body?.conflicts?.length ?? 0} konflikter – läser om`, "warn");
      await loadSchedule();
    } else {
      showToast("Kunde inte skicka personen: " + error.message, "error");
    }
  }
}


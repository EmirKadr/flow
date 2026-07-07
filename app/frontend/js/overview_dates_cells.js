// @ts-check
// Utdelad ur overview.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter overview.js via <script>-tagg.

// ---- Date helpers ----
function isoWeek(d = new Date()) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return { year: date.getUTCFullYear(), week, weekday: dayNum };
}

function isoWeekToMonday(year, week) {
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const jan4Dow = jan4.getUTCDay() || 7;
  const week1Mon = new Date(jan4);
  week1Mon.setUTCDate(jan4.getUTCDate() - (jan4Dow - 1));
  const monday = new Date(week1Mon);
  monday.setUTCDate(week1Mon.getUTCDate() + (week - 1) * 7);
  return monday;
}

function todayYmd() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function todayWeekdayIndex() {
  return new Date().getDay() || 7;
}

function datePartsFromDate(date) {
  return [date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate()];
}

function dateFromParts(parts) {
  if (!Array.isArray(parts) || parts.length !== 3) return null;
  const [year, month, day] = parts.map(Number);
  if (!year || !month || !day) return null;
  return new Date(Date.UTC(year, month - 1, day));
}

function dateFromYmdString(value) {
  const parts = String(value || "").split("-").map(Number);
  return dateFromParts(parts);
}

function overviewDateFromCell(td) {
  if (!td) return null;
  if (td.dataset.date) return dateFromYmdString(td.dataset.date);
  const year = Number(td.dataset.year);
  const week = Number(td.dataset.week);
  const weekday = Number(td.dataset.weekday);
  if (!year || !week || !weekday) return null;
  const monday = isoWeekToMonday(year, week);
  monday.setUTCDate(monday.getUTCDate() + weekday - 1);
  return monday;
}

function storedDateForCurrentPeriod() {
  const storedDate = dateFromParts(overviewState.selectedDateParts);
  if (!storedDate) return null;
  if (overviewState.view === "month") {
    return storedDate.getUTCFullYear() === overviewState.year && storedDate.getUTCMonth() + 1 === overviewState.month
      ? storedDate
      : null;
  }
  const storedWeek = isoWeek(storedDate);
  return storedWeek.year === overviewState.year && storedWeek.week === overviewState.week ? storedDate : null;
}

function writeOverviewSelectedDate(date) {
  overviewState.selectedDateParts = datePartsFromDate(date);
  writeSelectedDate(overviewState.selectedDateParts[0], overviewState.selectedDateParts[1], overviewState.selectedDateParts[2]);
}

function persistOverviewState() {
  let date = storedDateForCurrentPeriod();
  if (date) {
    writeOverviewSelectedDate(date);
    return;
  }
  if (overviewState.view === "month") {
    const now = new Date();
    const isCurrentMonth = overviewState.year === now.getFullYear() && overviewState.month === now.getMonth() + 1;
    date = isCurrentMonth ? now : new Date(Date.UTC(overviewState.year, overviewState.month - 1, 1));
  } else {
    const monday = isoWeekToMonday(overviewState.year, overviewState.week);
    date = monday;
  }
  writeOverviewSelectedDate(date);
}

function overviewPresenceSelection() {
  let date = overviewDateFromCell(overviewState.focusedCell?.td) || storedDateForCurrentPeriod();
  if (!date) {
    if (overviewState.view === "month") date = new Date(Date.UTC(overviewState.year, overviewState.month - 1, 1));
    else date = isoWeekToMonday(overviewState.year, overviewState.week);
  }
  const selectedWeek = isoWeek(date);
  return {
    year: selectedWeek.year,
    week: selectedWeek.week,
    weekday: selectedWeek.weekday,
    areaId: overviewState.areaId,
    areaName: overviewState.areaId == null
      ? "Alla områden"
      : (overviewState.areas.find((area) => area.id === overviewState.areaId)?.name || "Nuvarande område"),
  };
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
}

function activityById(id) {
  return overviewState.activities.find((a) => a.id === id);
}

function personById(id) {
  return overviewState.persons.find((p) => p.id === id) || overviewState.allPersons.find((p) => p.id === id) || null;
}

function colorFor(activityId) {
  const a = activityById(activityId);
  return a ? a.color : "#ffffff";
}

function buildActivitySelect(includeActivityIds = []) {
  const select = document.createElement("select");
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "–";
  select.appendChild(empty);

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

  const sortedActivities = typeof compareActivitiesForAreaFocus === "function"
    ? [...overviewState.activitiesActive].sort((a, b) =>
      compareActivitiesForAreaFocus(a, b, overviewState.areas, overviewState.currentUser?.area_id)
    )
    : overviewState.activitiesActive;
  sortedActivities.forEach(appendOption);
  includeActivityIds
    .map((id) => Number(id))
    .filter((id) => Number.isInteger(id))
    .forEach((id) => appendOption(activityById(id)));

  return select;
}

function focusNameFilter() {
  const input = document.getElementById("nameFilter");
  if (!input) return;
  input.focus();
  /** @type {HTMLInputElement} */ (input).select();
}

function refreshPersons() {
  const q = overviewState.nameFilter.toLowerCase().trim();
  let list = overviewState.allPersons;
  if (q) list = list.filter((p) => p.name.toLowerCase().includes(q));
  const getSortVal = (p) => overviewState.sortKey === "name" ? (p.name || "").toLowerCase() : p.sort_order;
  list = [...list].sort((a, b) => {
    if (typeof comparePersonsForAreaFocus === "function") {
      const areaCompare = comparePersonsForAreaFocus(a, b, overviewState.areas);
      if (areaCompare !== 0) return areaCompare;
    }
    const av = getSortVal(a), bv = getSortVal(b);
    if (av < bv) return overviewState.sortAsc ? -1 : 1;
    if (av > bv) return overviewState.sortAsc ? 1 : -1;
    return 0;
  });
  overviewState.persons = list;
  document.querySelectorAll("table.overview th[data-sort]").forEach((th) => {
    const ind = th.querySelector(".sort-ind");
    if (ind) ind.textContent = /** @type {HTMLElement} */ (th).dataset.sort === overviewState.sortKey ? (overviewState.sortAsc ? "▲" : "▼") : "";
  });
}

function canUsePersonSortOrder() {
  const user = overviewState.currentUser || {};
  const roles = typeof userRoles === "function" ? userRoles(user) : [user.role];
  const canCrossAreas = canSortPersonsAcrossAreas();
  const hasAllowedRole = canCrossAreas || roles.includes("admin") || roles.includes("staffing_manager");
  const hasArea = canCrossAreas || (user.area_id != null && Number.isFinite(Number(user.area_id)));
  return hasAllowedRole && hasArea && typeof canEditPage === "function" && canEditPage(user, "personSortOrder");
}

function canSortPersonsAcrossAreas() {
  const user = overviewState.currentUser || {};
  return Boolean(user.is_super_user || user.is_demo);
}

function canReorderPerson(person) {
  return canUsePersonSortOrder()
    && (canSortPersonsAcrossAreas() || Number(person?.home_area_id) === Number(overviewState.currentUser?.area_id));
}

function setupPersonOrderNameCell(cell, person) {
  cell.dataset.personId = person.id;
  if (canReorderPerson(person)) {
    cell.draggable = true;
    cell.classList.add("person-order-draggable");
    cell.title = "Dra namnet för att ändra sorteringen.";
  } else if (canUsePersonSortOrder()) {
    cell.classList.add("person-order-locked");
    cell.title = "Du kan bara sortera personer med samma hemområde som ditt användarområde.";
  }
}

function clearPersonOrderDropMarkers() {
  document
    .querySelectorAll("#overviewBody tr.person-order-drop-before, #overviewBody tr.person-order-drop-after")
    .forEach((row) => row.classList.remove("person-order-drop-before", "person-order-drop-after"));
}

function resetPersonOrderDrag() {
  document.body.classList.remove("dragging-person-order");
  document
    .querySelectorAll("#overviewBody tr.person-order-dragging")
    .forEach((row) => row.classList.remove("person-order-dragging"));
  clearPersonOrderDropMarkers();
  overviewPersonOrderDrag.sourceId = null;
  overviewPersonOrderDrag.targetId = null;
  overviewPersonOrderDrag.position = "after";
}

function updatePersonOrderDropTarget(cell, event) {
  const targetId = Number(cell.dataset.personId);
  if (!Number.isInteger(targetId) || targetId === Number(overviewPersonOrderDrag.sourceId)) return;
  const rect = cell.getBoundingClientRect();
  const position = event.clientY < rect.top + rect.height / 2 ? "before" : "after";
  clearPersonOrderDropMarkers();
  cell.parentElement.classList.add(position === "before" ? "person-order-drop-before" : "person-order-drop-after");
  overviewPersonOrderDrag.targetId = targetId;
  overviewPersonOrderDrag.position = position;
}

function currentAreaPersonIdsForReorder() {
  if (canSortPersonsAcrossAreas()) {
    return overviewState.persons
      .filter((person) => person.is_active !== false)
      .map((person) => Number(person.id));
  }
  const areaId = Number(overviewState.currentUser?.area_id);
  return overviewState.persons
    .filter((person) => Number(person.home_area_id) === areaId && person.is_active !== false)
    .map((person) => Number(person.id));
}

function movedPersonOrderIds(sourceId, targetId, position, ids) {
  if (sourceId === targetId) return ids;
  const withoutSource = ids.filter((id) => id !== sourceId);
  let index = withoutSource.indexOf(targetId);
  if (index < 0) return ids;
  if (position === "after") index += 1;
  withoutSource.splice(index, 0, sourceId);
  return withoutSource;
}

function applyPersonOrderResponse(updatedPersons) {
  const byId = new Map((updatedPersons || []).map((person) => [Number(person.id), person]));
  if (!byId.size) return;
  overviewState.allPersons = overviewState.allPersons.map((person) => (
    byId.has(Number(person.id)) ? { ...person, ...byId.get(Number(person.id)) } : person
  ));
  overviewState.sortKey = "sort_order";
  overviewState.sortAsc = true;
  refreshPersons();
  if (overviewState.view === "week") buildWeekBody();
  else buildMonthBody();
  setupOverviewHorizontalScroll();
}

async function savePersonOrder(sourceId, targetId, position) {
  if (!canUsePersonSortOrder()) {
    showToast("Du saknar behörighet att sortera personer.", "error", 5000);
    return;
  }
  if (overviewState.nameFilter.trim()) {
    showToast("Rensa personfiltret innan du sorterar personer.", "warn", 5000);
    return;
  }
  const ids = currentAreaPersonIdsForReorder();
  if (!ids.includes(sourceId) || !ids.includes(targetId)) {
    const message = canSortPersonsAcrossAreas()
      ? "Personlistan har ändrats. Läs om vyn och försök igen."
      : "Du kan bara sortera personer med samma hemområde som ditt användarområde.";
    showToast(message, "warn", 5000);
    return;
  }
  const personIds = movedPersonOrderIds(sourceId, targetId, position, ids);
  if (personIds.join(",") === ids.join(",")) return;
  markOverviewActivity();
  try {
    const updatedPersons = await api.put("/api/persons/sort-order", { person_ids: personIds });
    invalidateOverviewAllCache();
    applyPersonOrderResponse(updatedPersons);
    showToast("Personsorteringen sparades.", "success", 2500);
  } catch (error) {
    showToast(error.message || "Kunde inte spara personsorteringen.", "error", 7000);
    if (error.status === 409) await load();
  }
}

function setupPersonOrderDrag() {
  const body = document.getElementById("overviewBody");
  body.addEventListener("dragstart", (event) => {
    const cell = /** @type {Element} */ (event.target).closest("td.name[data-person-id]");
    if (!cell) return;
    const person = personById(Number(/** @type {HTMLElement} */ (cell).dataset.personId));
    if (!canReorderPerson(person) || overviewState.nameFilter.trim()) {
      event.preventDefault();
      if (overviewState.nameFilter.trim()) showToast("Rensa personfiltret innan du sorterar personer.", "warn", 4000);
      return;
    }
    overviewPersonOrderDrag.sourceId = Number(/** @type {HTMLElement} */ (cell).dataset.personId);
    document.body.classList.add("dragging-person-order");
    cell.parentElement.classList.add("person-order-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(overviewPersonOrderDrag.sourceId));
  });

  body.addEventListener("dragover", (event) => {
    if (overviewPersonOrderDrag.sourceId == null) return;
    const cell = /** @type {Element} */ (event.target).closest("td.name[data-person-id]");
    if (!cell) return;
    const person = personById(Number(/** @type {HTMLElement} */ (cell).dataset.personId));
    if (!canReorderPerson(person)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    updatePersonOrderDropTarget(cell, event);
  });

  body.addEventListener("drop", (event) => {
    if (overviewPersonOrderDrag.sourceId == null) return;
    const cell = /** @type {Element} */ (event.target).closest("td.name[data-person-id]");
    if (!cell) return;
    event.preventDefault();
    const sourceId = Number(overviewPersonOrderDrag.sourceId);
    const targetId = Number(overviewPersonOrderDrag.targetId || /** @type {HTMLElement} */ (cell).dataset.personId);
    const position = overviewPersonOrderDrag.position;
    resetPersonOrderDrag();
    void savePersonOrder(sourceId, targetId, position);
  });

  body.addEventListener("dragend", resetPersonOrderDrag);
  body.addEventListener("dragleave", (event) => {
    if (!(event.relatedTarget instanceof Node && body.contains(event.relatedTarget))) clearPersonOrderDropMarkers();
  });
}

function focusDayCell(td) {
  if (overviewState.focusedCell?.td) overviewState.focusedCell.td.classList.remove("focused");
  const selectedDate = overviewDateFromCell(td);
  if (selectedDate) writeOverviewSelectedDate(selectedDate);
  overviewState.focusedCell = {
    td,
    personId: Number(td.dataset.personId),
    year: Number(td.dataset.year),
    week: Number(td.dataset.week),
    weekday: Number(td.dataset.weekday),
    date: td.dataset.date || null,
  };
  td.classList.add("focused");
  if (document.activeElement && document.activeElement.tagName === "SELECT") {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
  }
  setTimeout(() => { try { td.focus({ preventScroll: true }); } catch (e) {} }, 0);
}

function dayRequestKey(personId, year, week, weekday) {
  return `${personId}:${year}:${week}:${weekday}`;
}

function normalizeOverviewCell(cell, td = null) {
  const normalized = {
    person_id: Number(cell?.person_id ?? td?.dataset.personId ?? 0),
    activity_id: cell?.activity_id == null ? null : Number(cell.activity_id),
    mixed: !!cell?.mixed,
    hours_total: Number(cell?.hours_total) || 0,
    template_hours: Number(cell?.template_hours ?? td?.dataset.templateHours ?? 0) || 0,
  };
  if (cell?.date != null || td?.dataset.date) normalized.date = cell?.date ?? td.dataset.date;
  else normalized.weekday = Number(cell?.weekday ?? td?.dataset.weekday ?? 0);
  if (cell?.year != null || td?.dataset.year) normalized.year = Number(cell?.year ?? td?.dataset.year ?? 0);
  if (cell?.week != null || td?.dataset.week) normalized.week = Number(cell?.week ?? td?.dataset.week ?? 0);
  return normalized;
}

function cellRecordIndexForTd(td) {
  if (overviewState.view === "week") {
    const personId = Number(td.dataset.personId);
    const weekday = Number(td.dataset.weekday);
    return overviewState.cells.findIndex((cell) => Number(cell.person_id) === personId && Number(cell.weekday) === weekday);
  }
  const personId = Number(td.dataset.personId);
  const date = td.dataset.date || "";
  return overviewState.cells.findIndex((cell) => Number(cell.person_id) === personId && cell.date === date);
}

function cellRecordForTd(td) {
  const idx = cellRecordIndexForTd(td);
  if (idx >= 0) return normalizeOverviewCell(overviewState.cells[idx], td);
  return normalizeOverviewCell({}, td);
}

function upsertCellRecordForTd(td, cell) {
  const normalized = normalizeOverviewCell(cell, td);
  const idx = cellRecordIndexForTd(td);
  if (idx >= 0) overviewState.cells[idx] = { ...overviewState.cells[idx], ...normalized };
  else overviewState.cells.push(normalized);
  return normalized;
}

function markDayPending(td, pending) {
  td.classList.toggle("pending-save", pending);
  const sel = td.querySelector("select");
  if (sel) sel.disabled = pending || overviewIsReadOnly();
}

function renderDayCell(td, cell) {
  const normalized = upsertCellRecordForTd(td, cell);
  td.dataset.activityId = normalized.activity_id == null ? "" : String(normalized.activity_id);
  td.dataset.templateHours = String(normalized.template_hours);
  styleCell(td, normalized);
  const sel = td.querySelector("select");
  if (sel) sel.disabled = td.classList.contains("pending-save") || overviewIsReadOnly();
  return normalized;
}

function buildOptimisticDayCell(td, activityId) {
  const current = cellRecordForTd(td);
  return normalizeOverviewCell(
    {
      person_id: current.person_id,
      weekday: current.weekday,
      date: current.date,
      year: Number(td.dataset.year),
      week: Number(td.dataset.week),
      activity_id: activityId,
      mixed: false,
      hours_total: activityId == null ? 0 : current.template_hours,
      template_hours: current.template_hours,
    },
    td,
  );
}

function findDayTd(personId, year, week, weekday) {
  return document.querySelector(
    `#overviewBody td.day[data-person-id="${personId}"][data-year="${year}"][data-week="${week}"][data-weekday="${weekday}"]`
  );
}


// ---- Cell rendering ----
function styleCell(td, cell) {
  td.innerHTML = "";
  td.classList.remove("mixed", "is-off", "scheduled-empty");
  td.style.background = "#fff";
  const person = personById(Number(td.dataset.personId));
  const baseActivityId = cell.template_hours > 0 ? (person?.home_activity_id || null) : null;

  const hasFixedSchedule = person?.has_fixed_schedule !== false;
  const isOff = hasFixedSchedule && cell.template_hours === 0;
  if (isOff) {
    td.classList.add("is-off");
    td.textContent = "Ledig";
    return;
  }
  if (!hasFixedSchedule && cell.template_hours === 0 && !cell.activity_id) {
    return;
  }

  if (cell.mixed) {
    td.classList.add("mixed");
  } else if (cell.activity_id) {
    td.style.background = colorFor(cell.activity_id);
  } else {
    td.classList.add("scheduled-empty");
  }

  const sel = buildActivitySelect([cell.activity_id, baseActivityId]);
  sel.value = cell.activity_id ? String(cell.activity_id) : "";

  sel.addEventListener("change", () => onDayChange(td, sel, cell));
  sel.addEventListener("focus", () => focusDayCell(td));
  sel.addEventListener("mousedown", (e) => {
    // Left-click never opens the dropdown — only focuses the cell.
    if (e.button === 0) {
      e.preventDefault();
      focusDayCell(td);
    }
  });
  td.addEventListener("contextmenu", (e) => {
    if (sel.disabled) return;
    e.preventDefault();
    focusDayCell(td);
    try {
      sel.showPicker();
    } catch (err) {
      sel.focus();
    }
  });
  td.appendChild(sel);

  const info = document.createElement("div");
  info.className = "hour-info";
  if (cell.mixed) info.textContent = `Blandat (${cell.hours_total}h)`;
  else if (cell.activity_id) info.textContent = `${cell.hours_total}/${cell.template_hours}h`;
  else info.textContent = `Schemalagd (${cell.template_hours}h)`;
  td.appendChild(info);
  if (td.classList.contains("pending-save")) {
    sel.disabled = true;
  }
  if (overviewIsReadOnly()) {
    sel.disabled = true;
  }

}

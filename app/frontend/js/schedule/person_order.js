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

function canUsePersonSortOrder() {
  const user = state.currentUser || {};
  const roles = typeof userRoles === "function" ? userRoles(user) : [user.role];
  const canCrossAreas = canSortPersonsAcrossAreas();
  const hasAllowedRole = canCrossAreas || roles.includes("admin") || roles.includes("staffing_manager");
  const hasArea = canCrossAreas || (user.area_id != null && Number.isFinite(Number(user.area_id)));
  return hasAllowedRole && hasArea && typeof canEditPage === "function" && canEditPage(user, "personSortOrder");
}

function canSortPersonsAcrossAreas() {
  const user = state.currentUser || {};
  return Boolean(user.is_super_user || user.is_demo);
}

function canReorderPerson(person) {
  return canUsePersonSortOrder()
    && (canSortPersonsAcrossAreas() || Number(person?.home_area_id) === Number(state.currentUser?.area_id));
}

function setupPersonOrderNameCell(cell, person) {
  cell.dataset.personId = person.id;
  const loanHint = "Högerklicka för att skicka personen till annat område.";
  cell.addEventListener("contextmenu", (event) => openScheduleLoanMenu(event, person));
  if (!scheduleIsReadOnly()) cell.classList.add("schedule-loan-enabled");
  if (canReorderPerson(person)) {
    cell.draggable = true;
    cell.classList.add("person-order-draggable");
    cell.title = "Dra namnet för att ändra sorteringen.";
  } else if (canUsePersonSortOrder()) {
    cell.classList.add("person-order-locked");
    cell.title = "Du kan bara sortera personer med samma hemområde som ditt användarområde.";
  }
  if (!scheduleIsReadOnly()) {
    cell.title = cell.title ? `${cell.title} ${loanHint}` : loanHint;
  }
}

function clearPersonOrderDropMarkers() {
  document
    .querySelectorAll("#scheduleBody tr.person-order-drop-before, #scheduleBody tr.person-order-drop-after")
    .forEach((row) => row.classList.remove("person-order-drop-before", "person-order-drop-after"));
}

function resetPersonOrderDrag() {
  document.body.classList.remove("dragging-person-order");
  document
    .querySelectorAll("#scheduleBody tr.person-order-dragging")
    .forEach((row) => row.classList.remove("person-order-dragging"));
  clearPersonOrderDropMarkers();
  personOrderDrag.sourceId = null;
  personOrderDrag.targetId = null;
  personOrderDrag.position = "after";
}

function updatePersonOrderDropTarget(cell, event) {
  const targetId = Number(cell.dataset.personId);
  if (!Number.isInteger(targetId) || targetId === Number(personOrderDrag.sourceId)) return;
  const rect = cell.getBoundingClientRect();
  const position = event.clientY < rect.top + rect.height / 2 ? "before" : "after";
  clearPersonOrderDropMarkers();
  cell.parentElement.classList.add(position === "before" ? "person-order-drop-before" : "person-order-drop-after");
  personOrderDrag.targetId = targetId;
  personOrderDrag.position = position;
}

function currentAreaPersonIdsForReorder() {
  if (canSortPersonsAcrossAreas()) {
    return state.persons
      .filter((person) => person.is_active !== false)
      .map((person) => Number(person.id));
  }
  const areaId = Number(state.currentUser?.area_id);
  return state.persons
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
  state.allPersons = state.allPersons.map((person) => (
    byId.has(Number(person.id)) ? { ...person, ...byId.get(Number(person.id)) } : person
  ));
  state.sortKey = "sort_order";
  state.sortAsc = true;
  refreshPersons();
  buildRows();
  setupScheduleHorizontalScroll();
}

async function savePersonOrder(sourceId, targetId, position) {
  if (!canUsePersonSortOrder()) {
    showToast("Du saknar behörighet att sortera personer.", "error", 5000);
    return;
  }
  if (state.nameFilter.trim()) {
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
  markScheduleActivity();
  try {
    const updatedPersons = await api.put("/api/persons/sort-order", { person_ids: personIds });
    invalidateScheduleAllCache();
    applyPersonOrderResponse(updatedPersons);
    showToast("Personsorteringen sparades.", "success", 2500);
  } catch (error) {
    showToast(error.message || "Kunde inte spara personsorteringen.", "error", 7000);
    if (error.status === 409) await loadSchedule();
  }
}

function setupPersonOrderDrag() {
  const body = document.getElementById("scheduleBody");
  body.addEventListener("dragstart", (event) => {
    const cell = event.target.closest("td.name[data-person-id]");
    if (!cell) return;
    const person = personById(Number(cell.dataset.personId));
    if (!canReorderPerson(person) || state.nameFilter.trim()) {
      event.preventDefault();
      if (state.nameFilter.trim()) showToast("Rensa personfiltret innan du sorterar personer.", "warn", 4000);
      return;
    }
    personOrderDrag.sourceId = Number(cell.dataset.personId);
    document.body.classList.add("dragging-person-order");
    cell.parentElement.classList.add("person-order-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(personOrderDrag.sourceId));
  });

  body.addEventListener("dragover", (event) => {
    if (personOrderDrag.sourceId == null) return;
    const cell = event.target.closest("td.name[data-person-id]");
    if (!cell) return;
    const person = personById(Number(cell.dataset.personId));
    if (!canReorderPerson(person)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    updatePersonOrderDropTarget(cell, event);
  });

  body.addEventListener("drop", (event) => {
    if (personOrderDrag.sourceId == null) return;
    const cell = event.target.closest("td.name[data-person-id]");
    if (!cell) return;
    event.preventDefault();
    const sourceId = Number(personOrderDrag.sourceId);
    const targetId = Number(personOrderDrag.targetId || cell.dataset.personId);
    const position = personOrderDrag.position;
    resetPersonOrderDrag();
    void savePersonOrder(sourceId, targetId, position);
  });

  body.addEventListener("dragend", resetPersonOrderDrag);
  body.addEventListener("dragleave", (event) => {
    if (!body.contains(event.relatedTarget)) clearPersonOrderDropMarkers();
  });
}


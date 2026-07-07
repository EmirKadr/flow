// @ts-check
// Utdelad ur persons.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter persons.js via <script>-tagg.

// ---- Filter + sort ----
function passesFilter(p) {
  const match = (val, q) => !q || String(val ?? "").toLowerCase().includes(q.toLowerCase());
  if (!match(p.name, filters.name)) return false;
  if (!match(p.noman, filters.noman)) return false;
  if (!match(p.rfid_code, filters.rfid_code)) return false;
  if (!match(collarTypeLabel(p.collar_type), filters.collar_type)) return false;
  if (!match(businessName(p.business_id), filters.business)) return false;
  if (!match(areaName(p.home_area_id), filters.home_area)) return false;
  if (!match(activityLabel(p.home_activity_id), filters.home_activity)) return false;
  if (!match(p.sort_order, filters.sort_order)) return false;
  return true;
}

function sortKeyValue(p) {
  switch (sortKey) {
    case "name": return (p.name || "").toLowerCase();
    case "noman": return (p.noman || "").toLowerCase();
    case "rfid_code": return (p.rfid_code || "").toLowerCase();
    case "collar_type": return collarTypeLabel(p.collar_type).toLowerCase();
    case "business": return businessName(p.business_id).toLowerCase();
    case "home_area": return areaName(p.home_area_id).toLowerCase();
    case "home_activity": return activityLabel(p.home_activity_id).toLowerCase();
    case "sort_order": return p.sort_order;
    default: return 0;
  }
}


// ---- Inline edit-helpers ----
async function savePersonField(personId, payload) {
  try {
    return await api.put(`/api/persons/${personId}`, payload);
  } catch (e) {
    showToast(e.message || "Kunde inte spara", "error");
    throw e;
  }
}

function snapshotPerson(person) {
  return {
    id: person.id,
    name: person.name,
    noman: person.noman ?? null,
    rfid_code: person.rfid_code ?? null,
    collar_type: person.collar_type || "blue_collar",
    home_area_id: person.home_area_id ?? null,
    home_activity_id: person.home_activity_id ?? null,
    competencies: Array.isArray(person.competencies) ? [...person.competencies] : [],
    comment: person.comment ?? null,
    has_fixed_schedule: person.has_fixed_schedule !== false,
    sort_order: Number(person.sort_order) || 0,
  };
}

function personPayloadFromSnapshot(person) {
  return {
    name: person.name,
    noman: person.noman ?? null,
    rfid_code: person.rfid_code ?? null,
    collar_type: person.collar_type || "blue_collar",
    home_area_id: person.home_area_id,
    home_activity_id: person.home_activity_id,
    competencies: Array.isArray(person.competencies) ? [...person.competencies] : [],
    comment: person.comment,
    has_fixed_schedule: person.has_fixed_schedule,
    sort_order: person.sort_order,
  };
}

function pushPersonUndo(label, before) {
  if (!before || personUndoBusy) return;
  personUndoStack.push({ label, before });
  if (personUndoStack.length > PERSON_UNDO_LIMIT) personUndoStack.shift();
}

async function undoLastPersonAction() {
  if (personUndoBusy) return;
  const action = personUndoStack.pop();
  if (!action) return;

  personUndoBusy = true;
  try {
    await api.put(`/api/persons/${action.before.id}`, personPayloadFromSnapshot(action.before));
    showToast(`Ångrade ${action.label}`, "success", 2500);
    await loadPersons();
  } catch (error) {
    personUndoStack.push(action);
    showToast(error.message || "Kunde inte ångra", "error", 7000);
  } finally {
    personUndoBusy = false;
  }
}

function installPersonUndoShortcut() {
  document.addEventListener("keydown", (e) => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return;
    if (e.key.toLowerCase() !== "z") return;
    if (e.target instanceof Element && e.target.closest("input, textarea, select, [contenteditable='true']")) return;
    if (document.querySelector(".modal-backdrop")) return;
    e.preventDefault();
    void undoLastPersonAction();
  });
}

function editText(td, person, field, currentValue, label = field) {
  if (td.querySelector("input,select")) return;
  td.classList.add("editing");
  const input = document.createElement("input");
  input.type = "text";
  input.className = "inline-input";
  input.value = currentValue || "";
  td.innerHTML = "";
  td.appendChild(input);
  input.focus();
  input.select();

  let done = false;
  const finish = async (commit) => {
    if (done) return; done = true;
    td.classList.remove("editing");
    const newValue = input.value.trim();
    if (commit && newValue !== (currentValue || "")) {
      if (field === "noman" && !newValue) {
        showToast("NoMan krävs", "error");
        await loadPersons();
        return;
      }
      try {
        const before = snapshotPerson(person);
        const value = newValue;
        await savePersonField(person.id, { [field]: value });
        pushPersonUndo(label, before);
        person[field] = value;
      } catch (e) {}
    }
    await loadPersons();
  };
  input.addEventListener("blur", () => finish(true));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); input.blur(); }
    else if (e.key === "Escape") { e.preventDefault(); finish(false); }
  });
}

function editNumber(td, person, field, currentValue) {
  if (td.querySelector("input,select")) return;
  td.classList.add("editing");
  const input = document.createElement("input");
  input.type = "number";
  input.className = "inline-input";
  input.value = currentValue ?? 0;
  input.style.maxWidth = "80px";
  td.innerHTML = "";
  td.appendChild(input);
  input.focus();
  input.select();

  let done = false;
  const finish = async (commit) => {
    if (done) return; done = true;
    td.classList.remove("editing");
    const num = Number(input.value) || 0;
    if (commit && num !== currentValue) {
      try {
        const before = snapshotPerson(person);
        await savePersonField(person.id, { [field]: num });
        pushPersonUndo("sortering", before);
      } catch (e) {}
    }
    await loadPersons();
  };
  input.addEventListener("blur", () => finish(true));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); input.blur(); }
    else if (e.key === "Escape") { e.preventDefault(); finish(false); }
  });
}

function editSelect(td, person, field, currentId, options, getId, getLabel) {
  if (td.querySelector("input,select")) return;
  td.classList.add("editing");
  const select = document.createElement("select");
  select.className = "inline-input";
  select.innerHTML = `<option value="">(inget)</option>` +
    options.map((o) => `<option value="${getId(o)}" ${getId(o) === currentId ? "selected" : ""}>${escapeHtml(getLabel(o))}</option>`).join("");
  td.style.background = "";
  td.innerHTML = "";
  td.appendChild(select);
  select.focus();

  let done = false;
  const finish = async (commit) => {
    if (done) return; done = true;
    td.classList.remove("editing");
    const newId = select.value ? Number(select.value) : null;
    if (commit && newId !== currentId) {
      try {
        const before = snapshotPerson(person);
        await savePersonField(person.id, { [field]: newId });
        pushPersonUndo(field === "home_area_id" ? "hemområde" : "huvudaktivitet", before);
      } catch (e) {}
    }
    await loadPersons();
  };
  select.addEventListener("change", () => select.blur());
  select.addEventListener("blur", () => finish(true));
  select.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); finish(false); }
  });
}

function editChoice(td, person, field, currentValue, options, label) {
  if (td.querySelector("input,select")) return;
  td.classList.add("editing");
  const select = document.createElement("select");
  select.className = "inline-input";
  select.innerHTML = options
    .map((option) => `<option value="${escapeHtml(option.value)}" ${option.value === currentValue ? "selected" : ""}>${escapeHtml(option.label)}</option>`)
    .join("");
  td.innerHTML = "";
  td.appendChild(select);
  select.focus();

  let done = false;
  const finish = async (commit) => {
    if (done) return; done = true;
    td.classList.remove("editing");
    const newValue = select.value || options[0]?.value || "";
    if (commit && newValue !== currentValue) {
      try {
        const before = snapshotPerson(person);
        await savePersonField(person.id, { [field]: newValue });
        pushPersonUndo(label, before);
        person[field] = newValue;
      } catch (e) {}
    }
    await loadPersons();
  };
  select.addEventListener("change", () => select.blur());
  select.addEventListener("blur", () => finish(true));
  select.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); finish(false); }
  });
}


// ---- Rendering ----
function renderRows() {
  const filtered = persons.filter(matchesAreaFocus).filter(passesFilter).sort((a, b) => {
    if (typeof comparePersonsForAreaFocus === "function") {
      const areaCompare = comparePersonsForAreaFocus(a, b, areas);
      if (areaCompare !== 0) return areaCompare;
    }
    const av = sortKeyValue(a);
    const bv = sortKeyValue(b);
    if (av < bv) return sortAsc ? -1 : 1;
    if (av > bv) return sortAsc ? 1 : -1;
    return 0;
  });

  const tbody = document.getElementById("persons-body");
  const canEditPersons = canEditPage(currentUser, "persons");
  tbody.innerHTML = "";
  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="99" class="empty-state">Inga personer matchar filtret. Rensa filterfälten eller byt områdesfokus.</td></tr>';
    return;
  }

  filtered.forEach((p) => {
    const tr = document.createElement("tr");
    tr.dataset.personId = p.id;
    tr.addEventListener("dblclick", (e) => {
      if (/** @type {Element} */ (e.target).closest("button")) return;
      e.preventDefault();
      openPersonProductivityModal(p);
    });

    // Namn
    const tdName = document.createElement("td");
    if (canEditPersons) tdName.className = "editable";
    tdName.textContent = p.name;
    if (canEditPersons) tdName.addEventListener("click", () => editText(tdName, p, "name", p.name, "namn"));
    tr.appendChild(tdName);

    // NoMan
    const tdNoman = document.createElement("td");
    if (canEditPersons) tdNoman.className = "editable";
    tdNoman.textContent = p.noman || "";
    if (canEditPersons) tdNoman.addEventListener("click", () => editText(tdNoman, p, "noman", p.noman || "", "NoMan"));
    tr.appendChild(tdNoman);

    // RFID
    const tdRfid = document.createElement("td");
    if (canEditPersons) tdRfid.className = "editable";
    tdRfid.textContent = p.rfid_code || "";
    if (canEditPersons) tdRfid.addEventListener("click", () => editText(tdRfid, p, "rfid_code", p.rfid_code || "", "RFID"));
    tr.appendChild(tdRfid);

    // Arbetstyp
    const tdCollarType = document.createElement("td");
    if (canEditPersons) tdCollarType.className = "editable";
    tdCollarType.textContent = collarTypeLabel(p.collar_type);
    if (canEditPersons) tdCollarType.addEventListener("click", () =>
      editChoice(tdCollarType, p, "collar_type", p.collar_type || "blue_collar", PERSON_COLLAR_TYPES, "arbetstyp")
    );
    tr.appendChild(tdCollarType);

    // Verksamhet
    const tdBusiness = document.createElement("td");
    tdBusiness.textContent = businessName(p.business_id);
    tr.appendChild(tdBusiness);

    // Hemområde
    const tdArea = document.createElement("td");
    if (canEditPersons) tdArea.className = "editable";
    tdArea.textContent = areaName(p.home_area_id);
    if (canEditPersons) tdArea.addEventListener("click", () =>
      editSelect(tdArea, p, "home_area_id", p.home_area_id, areas, (a) => a.id, (a) => a.name)
    );
    tr.appendChild(tdArea);

    // Huvudaktivitet
    const tdAct = document.createElement("td");
    if (canEditPersons) tdAct.className = "editable";
    if (p.home_activity_id) tdAct.style.background = activityColor(p.home_activity_id);
    tdAct.textContent = activityLabel(p.home_activity_id);
    if (canEditPersons) tdAct.addEventListener("click", () =>
      editSelect(
        tdAct, p, "home_activity_id", p.home_activity_id,
        activitiesActive,
        (a) => a.id,
        (a) => a.label,
      )
    );
    tr.appendChild(tdAct);

    // Sortering
    const tdSort = document.createElement("td");
    if (canEditPersons) tdSort.className = "editable";
    tdSort.textContent = p.sort_order;
    if (canEditPersons) tdSort.addEventListener("click", () => editNumber(tdSort, p, "sort_order", p.sort_order));
    tr.appendChild(tdSort);

    // Åtgärder
    const tdActions = document.createElement("td");
    tdActions.innerHTML = `
      <button data-schedule="${p.id}">Schema</button>
      ${canEditPersons ? `<button data-delete="${p.id}" class="danger">Ta bort</button>` : ""}
    `;
    tr.appendChild(tdActions);

    tbody.appendChild(tr);
  });

  if (canEditPersons) {
    tbody.querySelectorAll("button[data-delete]").forEach((button) =>
      button.addEventListener("click", async (e) => {
        e.stopPropagation();
        const person = persons.find((item) => item.id === Number(/** @type {HTMLElement} */ (button).dataset.delete));
        if (!person || !confirm("Ta bort personen permanent?")) return;
        try {
          await api.del(`/api/persons/${person.id}`);
          await loadPersons();
        } catch (error) {
          showToast(error.message || "Kunde inte ta bort personen", "error", 7000);
        }
      })
    );
  }
  tbody.querySelectorAll("button[data-schedule]").forEach((b) =>
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      openScheduleModal(persons.find((p) => p.id === Number(/** @type {HTMLElement} */ (b).dataset.schedule)));
    })
  );

  document.querySelectorAll("tr.sort-row th[data-sort]").forEach((th) => {
    const ind = th.querySelector(".sort-ind");
    ind.textContent = /** @type {HTMLElement} */ (th).dataset.sort === sortKey ? (sortAsc ? "▲" : "▼") : "";
  });
}


async function loadPersons() {
  const areaId = focusedAreaId();
  const params = new URLSearchParams();
  if (areaId != null) params.set("area_id", String(areaId));
  const query = params.toString();
  // SWR-pilot: visa senaste snapshot direkt vid sidbyte, uppdatera i bakgrunden.
  await api.getSwr(`/api/persons${query ? `?${query}` : ""}`, (data) => {
    persons = data;
    renderRows();
  });
}

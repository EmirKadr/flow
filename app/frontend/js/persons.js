// Personregister – inline-redigering direkt i tabellen.

let areas = [];
let activities = [];
let businesses = [];
let persons = [];
let currentUser = null;
let sortKey = "sort_order";
let sortAsc = true;
const filters = { name: "", home_area: "", home_activity: "", sort_order: "" };
const personUndoStack = [];
const PERSON_UNDO_LIMIT = 50;
let personUndoBusy = false;

async function loadInitial() {
  const requests = [
    api.get("/api/areas"),
    api.get("/api/activities?include_inactive=true"),
  ];
  if (currentUser?.is_super_user) requests.push(api.get("/api/businesses"));
  const [a, act, biz] = await Promise.all(requests);
  areas = a;
  activities = act;
  businesses = biz || [];
}

function areaName(id) {
  const a = areas.find((x) => x.id === id);
  return a ? a.name : "";
}
function activityLabel(id) {
  const a = activities.find((x) => x.id === id);
  return a ? a.label : "";
}
function activityColor(id) {
  const a = activities.find((x) => x.id === id);
  return a ? a.color : "transparent";
}

function businessOptions(selectedId, disabled = false) {
  if (!currentUser?.is_super_user) return "";
  return `
      <label>Verksamhet</label>
      <select id="m-business" ${disabled ? "disabled" : ""}>
        <option value="">Välj verksamhet</option>
        ${businesses.map((business) => `<option value="${business.id}" ${Number(selectedId) === Number(business.id) ? "selected" : ""}>${escapeHtml(business.name)}</option>`).join("")}
      </select>
  `;
}

function businessIdFromArea(areaId) {
  const area = areas.find((item) => Number(item.id) === Number(areaId));
  return area?.business_id ?? null;
}

function businessIdFromActivity(activityId) {
  const activity = activities.find((item) => Number(item.id) === Number(activityId));
  return activity?.business_id ?? null;
}

function inferredPersonBusinessId(person = null) {
  return person?.business_id
    ?? businessIdFromArea(person?.home_area_id)
    ?? businessIdFromActivity(person?.home_activity_id)
    ?? currentUser?.business_id
    ?? businesses[0]?.id
    ?? null;
}

function focusedAreaId() {
  return typeof preferredAreaIdFromFocus === "function" ? preferredAreaIdFromFocus(areas) : null;
}

function matchesAreaFocus(person) {
  const areaId = focusedAreaId();
  return areaId == null || Number(person?.home_area_id) === Number(areaId);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
}


// ---- Filter + sort ----
function passesFilter(p) {
  const match = (val, q) => !q || String(val ?? "").toLowerCase().includes(q.toLowerCase());
  if (!match(p.name, filters.name)) return false;
  if (!match(areaName(p.home_area_id), filters.home_area)) return false;
  if (!match(activityLabel(p.home_activity_id), filters.home_activity)) return false;
  if (!match(p.sort_order, filters.sort_order)) return false;
  return true;
}

function sortKeyValue(p) {
  switch (sortKey) {
    case "name": return (p.name || "").toLowerCase();
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
    if (e.target?.closest?.("input, textarea, select, [contenteditable='true']")) return;
    if (document.querySelector(".modal-backdrop")) return;
    e.preventDefault();
    void undoLastPersonAction();
  });
}

function editText(td, person, field, currentValue) {
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
      try {
        const before = snapshotPerson(person);
        await savePersonField(person.id, { [field]: newValue });
        pushPersonUndo("namn", before);
        person[field] = newValue;
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

  filtered.forEach((p) => {
    const tr = document.createElement("tr");

    // Namn
    const tdName = document.createElement("td");
    if (canEditPersons) tdName.className = "editable";
    tdName.textContent = p.name;
    if (canEditPersons) tdName.addEventListener("click", () => editText(tdName, p, "name", p.name));
    tr.appendChild(tdName);

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
        activities,
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
        const person = persons.find((item) => item.id === Number(button.dataset.delete));
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
      openScheduleModal(persons.find((p) => p.id === Number(b.dataset.schedule)));
    })
  );

  document.querySelectorAll("tr.sort-row th[data-sort]").forEach((th) => {
    const ind = th.querySelector(".sort-ind");
    ind.textContent = th.dataset.sort === sortKey ? (sortAsc ? "▲" : "▼") : "";
  });
}


async function loadPersons() {
  const params = new URLSearchParams();
  const areaId = focusedAreaId();
  if (areaId != null) params.set("area_id", String(areaId));
  const query = params.toString();
  persons = await api.get(`/api/persons${query ? `?${query}` : ""}`);
  renderRows();
}


// ---- Excelimport ----
function openImportResultModal(result) {
  const errors = result.errors || [];
  const shownErrors = errors.slice(0, 25);
  const extra = Math.max(0, errors.length - shownErrors.length);
  const rows = shownErrors.map((entry) => `
    <tr>
      <td>${entry.row}</td>
      <td>${escapeHtml(entry.name || "-")}</td>
      <td>${escapeHtml(entry.error)}</td>
    </tr>`).join("");
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal wide">
      <h2>Importresultat</h2>
      <p class="note">${result.created} skapade, ${result.skipped} hoppades över.</p>
      ${rows ? `
        <div class="modal-table-scroll">
          <table>
            <thead><tr><th>Rad</th><th>Namn</th><th>Fel</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      ` : ""}
      ${extra ? `<p class="note">${extra} fler fel visas inte här.</p>` : ""}
      <div class="actions">
        <button class="primary" id="import-result-close">Stäng</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  document.getElementById("import-result-close").addEventListener("click", () => backdrop.remove());
}

function showImportResult(result) {
  if (result.created && result.skipped) {
    showToast(`${result.created} personer importerades. ${result.skipped} rad(er) hoppades över.`, "warn", 7000);
    openImportResultModal(result);
    return;
  }
  if (result.created) {
    showToast(`${result.created} personer importerades`, "success");
    return;
  }
  if (result.skipped) {
    showToast("Inga personer importerades", "error", 7000);
    openImportResultModal(result);
    return;
  }
  showToast("Importen innehöll inga personer", "warn");
}

async function importPersonFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const importButton = document.getElementById("import-persons");
  importButton.disabled = true;
  try {
    const result = await api.postForm("/api/persons/import", formData);
    showImportResult(result);
    await loadPersons();
  } catch (error) {
    showToast(error.message, "error", 7000);
  } finally {
    importButton.disabled = false;
  }
}

function openBulkPersonsModal() {
  const businessColumn = currentUser?.is_super_user
    ? [{ key: "business", label: "Verksamhet", type: "select", options: businesses.map((business) => ({ value: business.code, label: business.name })) }]
    : [];
  openBulkImportGrid({
    title: "Flera nya personer",
    submitLabel: "Skapa personer",
    initialRows: 10,
    columns: [
      ...businessColumn,
      { key: "name", label: "Namn" },
      { key: "home_area", label: "Hemområde", type: "select", options: areas.map((area) => ({ value: area.name, label: area.name })) },
      { key: "home_activity", label: "Huvudaktivitet", type: "select", options: activities.map((activity) => ({ value: activity.label, label: activity.label })) },
      { key: "sort_order", label: "Sortering", type: "number" },
    ],
    onSubmit: async (rows) => {
      const result = await api.post("/api/persons/import-rows", { rows });
      showImportResult(result);
      await loadPersons();
    },
  });
}

function setupImportControls() {
  const downloadButton = document.getElementById("download-person-template");
  const importButton = document.getElementById("import-persons");
  const bulkButton = document.getElementById("bulk-persons");
  const helpButton = document.getElementById("person-import-help");
  const fileInput = document.getElementById("person-import-file");
  if (!canEditPage(currentUser, "personImport")) {
    downloadButton.hidden = true;
    importButton.hidden = true;
    if (bulkButton) bulkButton.hidden = true;
    if (helpButton) helpButton.hidden = true;
    return;
  }

  if (bulkButton) {
    bulkButton.hidden = false;
    bulkButton.addEventListener("click", openBulkPersonsModal);
  }
  setupImportHelpButton("person-import-help", "Importera personer");
  downloadButton.addEventListener("click", async () => {
    try {
      await api.download("/api/persons/import-template", "personer-importmall.xlsx");
    } catch (error) {
      showToast(error.message || "Kunde inte ladda ner importmallen.", "error", 7000);
    }
  });
  importButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files?.[0];
    fileInput.value = "";
    if (!file) return;
    await importPersonFile(file);
  });
}


// ---- Ny person-modal (kvar för att kunna lägga till) ----
function openModal(person) {
  const isEdit = !!person;
  const selectedAreaId = person?.home_area_id ?? focusedAreaId();
  const selectedBusinessId = isEdit ? inferredPersonBusinessId(person) : (businessIdFromArea(selectedAreaId) ?? inferredPersonBusinessId(person));
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Redigera person" : "Ny person"}</h2>
      ${businessOptions(selectedBusinessId, isEdit)}
      <label>Namn</label>
      <input id="m-name" value="${escapeHtml(person?.name || "")}" />
      <label>Hemområde</label>
      <select id="m-area">
        <option value="">(inget)</option>
        ${areas.map((a) => `<option value="${a.id}" ${Number(selectedAreaId) === Number(a.id) ? "selected" : ""}>${escapeHtml(a.name)}</option>`).join("")}
      </select>
      <label>Huvudaktivitet</label>
      <select id="m-activity">
        <option value="">(inget)</option>
        ${activities.map((a) => `<option value="${a.id}" ${person?.home_activity_id === a.id ? "selected" : ""}>${escapeHtml(a.label)}</option>`).join("")}
      </select>
      <label>Sortering</label>
      <input id="m-sort" type="number" value="${person?.sort_order ?? 0}" />
      <div class="actions">
        <button id="m-cancel">Avbryt</button>
        <button class="primary" id="m-save">Spara</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  document.getElementById("m-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("m-save").addEventListener("click", async () => {
    const payload = {
      name: document.getElementById("m-name").value.trim(),
      home_area_id: document.getElementById("m-area").value ? Number(document.getElementById("m-area").value) : null,
      home_activity_id: document.getElementById("m-activity").value ? Number(document.getElementById("m-activity").value) : null,
      sort_order: Number(document.getElementById("m-sort").value) || 0,
    };
    if (currentUser?.is_super_user && !isEdit) {
      payload.business_id = document.getElementById("m-business").value ? Number(document.getElementById("m-business").value) : null;
    }
    if (!payload.name) { showToast("Namn krävs", "error"); return; }
    try {
      if (isEdit) {
        const before = snapshotPerson(person);
        await api.put(`/api/persons/${person.id}`, payload);
        pushPersonUndo("personändring", before);
      } else {
        await api.post("/api/persons", payload);
      }
      backdrop.remove();
      await loadPersons();
    } catch (e) { showToast(e.message, "error"); }
  });
}


// ---- Schema-modal ----
const DAY_LABELS = { 1: "Måndag", 2: "Tisdag", 3: "Onsdag", 4: "Torsdag", 5: "Fredag", 6: "Lördag", 7: "Söndag" };

async function openScheduleModal(person) {
  let template;
  try {
    template = await api.get(`/api/persons/${person.id}/schedule`);
  } catch (e) {
    showToast("Kunde inte ladda schema: " + e.message, "error");
    return;
  }

  const hoursFromOpts = Array.from({ length: 18 }, (_, i) => 6 + i)
    .map((h) => `<option value="${h}">${String(h).padStart(2, "0")}:00</option>`).join("");
  const hoursToOpts = Array.from({ length: 18 }, (_, i) => 7 + i)
    .map((h) => `<option value="${h}">${String(h).padStart(2, "0")}:00</option>`).join("");
  const isHourlyWorker = !template.has_fixed_schedule;

  const rowFor = (d) => `
    <tr data-weekday="${d.weekday}">
      <td style="padding: 6px 10px; font-weight: bold;">${DAY_LABELS[d.weekday]}</td>
      <td><label><input type="checkbox" class="m-off" ${d.is_off ? "checked" : ""}/> Ledig</label></td>
      <td>Från <select class="m-from">${hoursFromOpts}</select></td>
      <td>Till <select class="m-to">${hoursToOpts}</select></td>
    </tr>`;

  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal" style="min-width: 480px;">
      <h2>Veckomall för ${escapeHtml(person.name)}</h2>
      <p class="note">Mallen används av Översikt och visar huvudaktivitet som bas i bemanningen.</p>
      <label class="modal-checkbox">
        <input id="sch-hourly" type="checkbox" ${isHourlyWorker ? "checked" : ""} />
        Timmis - ingen fast schemamall
      </label>
      <p class="note">När detta är valt har personen ingen fast schemamall. Det räknas inte som ledig tid.</p>
      <table style="margin-top: 12px;">
        <tbody id="sch-body">
          ${template.days.map(rowFor).join("")}
        </tbody>
      </table>
      <div class="actions">
        <button id="sch-default">Standard 07-16</button>
        <button id="sch-cancel">Avbryt</button>
        <button id="sch-save" class="primary">Spara</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  template.days.forEach((d) => {
    const row = backdrop.querySelector(`tr[data-weekday="${d.weekday}"]`);
    row.querySelector(".m-from").value = String(d.start_hour ?? 7);
    row.querySelector(".m-to").value = String(d.end_hour ?? 16);
    updateRowDisabled(row);
  });
  updateScheduleModalDisabled(backdrop);

  backdrop.querySelectorAll(".m-off").forEach((cb) =>
    cb.addEventListener("change", (e) => {
      updateRowDisabled(e.target.closest("tr"));
    })
  );

  document.getElementById("sch-hourly").addEventListener("change", () => updateScheduleModalDisabled(backdrop));

  document.getElementById("sch-default").addEventListener("click", () => {
    document.getElementById("sch-hourly").checked = false;
    backdrop.querySelectorAll("tr[data-weekday]").forEach((row) => {
      const weekday = Number(row.dataset.weekday);
      row.querySelector(".m-off").checked = weekday >= 6;
      row.querySelector(".m-from").value = "7";
      row.querySelector(".m-to").value = "16";
      updateRowDisabled(row);
    });
    updateScheduleModalDisabled(backdrop);
  });

  document.getElementById("sch-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("sch-save").addEventListener("click", async () => {
    const hasFixedSchedule = !document.getElementById("sch-hourly").checked;
    const days = [];
    if (hasFixedSchedule) {
      for (const row of backdrop.querySelectorAll("tr[data-weekday]")) {
        const wd = Number(row.dataset.weekday);
        const isOff = row.querySelector(".m-off").checked;
        if (isOff) { days.push({ weekday: wd, is_off: true, start_hour: null, end_hour: null }); continue; }
        const sh = Number(row.querySelector(".m-from").value);
        const eh = Number(row.querySelector(".m-to").value);
        if (sh >= eh) {
          showToast(`${DAY_LABELS[wd]}: Från måste vara mindre än Till`, "error");
          return;
        }
        days.push({ weekday: wd, is_off: false, start_hour: sh, end_hour: eh });
      }
    }
    try {
      await api.put(`/api/persons/${person.id}/schedule`, { has_fixed_schedule: hasFixedSchedule, days });
      backdrop.remove();
      showToast("Schema sparat");
    } catch (e) { showToast(e.message, "error"); }
  });
}

function updateScheduleModalDisabled(backdrop) {
  const hourly = document.getElementById("sch-hourly").checked;
  backdrop.querySelectorAll("tr[data-weekday]").forEach((row) => {
    const offCheckbox = row.querySelector(".m-off");
    offCheckbox.disabled = hourly;
    updateRowDisabled(row);
  });
}

function updateRowDisabled(row) {
  const off = document.getElementById("sch-hourly")?.checked || row.querySelector(".m-off").checked;
  row.querySelector(".m-from").disabled = off;
  row.querySelector(".m-to").disabled = off;
}


// ---- Init ----
(async () => {
  currentUser = await initPage("persons");
  if (!currentUser) return;
  await loadInitial();
  await loadPersons();
  setupImportControls();
  installPersonUndoShortcut();
  const newPersonButton = document.getElementById("new-person");
  newPersonButton.hidden = !canEditPage(currentUser, "persons");
  if (canEditPage(currentUser, "persons")) newPersonButton.addEventListener("click", () => openModal(null));
  window.addEventListener("flow:areaFocusChanged", () => loadPersons());

  document.querySelectorAll("tr.filter-row input").forEach((inp) => {
    inp.addEventListener("input", () => {
      filters[inp.dataset.filter] = inp.value;
      renderRows();
    });
  });
  document.querySelectorAll("tr.sort-row th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (sortKey === key) sortAsc = !sortAsc;
      else { sortKey = key; sortAsc = true; }
      renderRows();
    });
  });
})();

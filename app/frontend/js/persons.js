// Personregister – inline-redigering direkt i tabellen.

let areas = [];
let activities = [];
let persons = [];
let sortKey = "sort_order";
let sortAsc = true;
const filters = { name: "", home_area: "", home_activity: "", is_active: "", sort_order: "" };

async function loadInitial() {
  const [a, act] = await Promise.all([
    api.get("/api/areas"),
    api.get("/api/activities?include_inactive=true"),
  ]);
  areas = a;
  activities = act;
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
  if (!match(p.is_active ? "ja" : "nej", filters.is_active)) return false;
  if (!match(p.sort_order, filters.sort_order)) return false;
  return true;
}

function sortKeyValue(p) {
  switch (sortKey) {
    case "name": return (p.name || "").toLowerCase();
    case "home_area": return areaName(p.home_area_id).toLowerCase();
    case "home_activity": return activityLabel(p.home_activity_id).toLowerCase();
    case "is_active": return p.is_active ? 1 : 0;
    case "sort_order": return p.sort_order;
    default: return 0;
  }
}


// ---- Inline edit-helpers ----
async function savePersonField(personId, payload) {
  try {
    await api.put(`/api/persons/${personId}`, payload);
  } catch (e) {
    showToast(e.message || "Kunde inte spara", "error");
    throw e;
  }
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
    if (commit && input.value !== currentValue) {
      try {
        await savePersonField(person.id, { [field]: input.value.trim() });
        person[field] = input.value.trim();
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
      try { await savePersonField(person.id, { [field]: num }); } catch (e) {}
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
      try { await savePersonField(person.id, { [field]: newId }); } catch (e) {}
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
  const filtered = persons.filter(passesFilter).sort((a, b) => {
    const av = sortKeyValue(a);
    const bv = sortKeyValue(b);
    if (av < bv) return sortAsc ? -1 : 1;
    if (av > bv) return sortAsc ? 1 : -1;
    return 0;
  });

  const tbody = document.getElementById("persons-body");
  tbody.innerHTML = "";

  filtered.forEach((p) => {
    const tr = document.createElement("tr");

    // Namn
    const tdName = document.createElement("td");
    tdName.className = "editable";
    tdName.textContent = p.name;
    tdName.addEventListener("click", () => editText(tdName, p, "name", p.name));
    tr.appendChild(tdName);

    // Hemområde
    const tdArea = document.createElement("td");
    tdArea.className = "editable";
    tdArea.textContent = areaName(p.home_area_id);
    tdArea.addEventListener("click", () =>
      editSelect(tdArea, p, "home_area_id", p.home_area_id, areas, (a) => a.id, (a) => a.name)
    );
    tr.appendChild(tdArea);

    // Huvudställe
    const tdAct = document.createElement("td");
    tdAct.className = "editable";
    if (p.home_activity_id) tdAct.style.background = activityColor(p.home_activity_id);
    tdAct.textContent = activityLabel(p.home_activity_id);
    tdAct.addEventListener("click", () =>
      editSelect(
        tdAct, p, "home_activity_id", p.home_activity_id,
        activities.filter((a) => a.is_active),
        (a) => a.id,
        (a) => a.label,
      )
    );
    tr.appendChild(tdAct);

    // Aktiv (toggle)
    const tdActive = document.createElement("td");
    tdActive.className = "editable";
    tdActive.textContent = p.is_active ? "Ja" : "Nej";
    tdActive.addEventListener("click", async () => {
      try {
        await savePersonField(p.id, { is_active: !p.is_active });
        await loadPersons();
      } catch (e) {}
    });
    tr.appendChild(tdActive);

    // Sortering
    const tdSort = document.createElement("td");
    tdSort.className = "editable";
    tdSort.textContent = p.sort_order;
    tdSort.addEventListener("click", () => editNumber(tdSort, p, "sort_order", p.sort_order));
    tr.appendChild(tdSort);

    // Åtgärder (Schema + Inaktivera)
    const tdActions = document.createElement("td");
    tdActions.innerHTML = `
      <button data-schedule="${p.id}">Schema</button>
      ${p.is_active ? `<button data-delete="${p.id}" class="danger">Inaktivera</button>` : ""}
    `;
    tr.appendChild(tdActions);

    tbody.appendChild(tr);
  });

  tbody.querySelectorAll("button[data-delete]").forEach((b) =>
    b.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("Inaktivera person?")) return;
      await api.del(`/api/persons/${b.dataset.delete}`);
      await loadPersons();
    })
  );
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
  const includeInactive = document.getElementById("show-inactive").checked;
  persons = await api.get(`/api/persons?include_inactive=${includeInactive}`);
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
  showToast("Excel-filen innehöll inga personer", "warn");
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

function setupImportControls() {
  const downloadButton = document.getElementById("download-person-template");
  const importButton = document.getElementById("import-persons");
  const fileInput = document.getElementById("person-import-file");

  downloadButton.addEventListener("click", () => {
    window.location.href = "/api/persons/import-template";
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
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Redigera person" : "Ny person"}</h2>
      <label>Namn</label>
      <input id="m-name" value="${escapeHtml(person?.name || "")}" />
      <label>Hemområde</label>
      <select id="m-area">
        <option value="">(inget)</option>
        ${areas.map((a) => `<option value="${a.id}" ${person?.home_area_id === a.id ? "selected" : ""}>${escapeHtml(a.name)}</option>`).join("")}
      </select>
      <label>Huvudställe</label>
      <select id="m-activity">
        <option value="">(inget)</option>
        ${activities.filter((a) => a.is_active).map((a) => `<option value="${a.id}" ${person?.home_activity_id === a.id ? "selected" : ""}>${escapeHtml(a.label)}</option>`).join("")}
      </select>
      <label>Sortering</label>
      <input id="m-sort" type="number" value="${person?.sort_order ?? 0}" />
      <label class="modal-checkbox"><input id="m-active" type="checkbox" ${person?.is_active !== false ? "checked" : ""} /> Aktiv</label>
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
      is_active: document.getElementById("m-active").checked,
    };
    if (!payload.name) { showToast("Namn krävs", "error"); return; }
    try {
      if (isEdit) await api.put(`/api/persons/${person.id}`, payload);
      else await api.post("/api/persons", payload);
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
      <p class="note">Mallen används av Översikt + visar huvudställe som bas i bemanningen.</p>
      <table style="margin-top: 12px;">
        <tbody id="sch-body">
          ${template.days.map(rowFor).join("")}
        </tbody>
      </table>
      <div class="actions">
        <button id="sch-default">Återställ alla till 07-16</button>
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

  backdrop.querySelectorAll(".m-off").forEach((cb) =>
    cb.addEventListener("change", (e) => updateRowDisabled(e.target.closest("tr")))
  );

  document.getElementById("sch-default").addEventListener("click", () => {
    backdrop.querySelectorAll("tr[data-weekday]").forEach((row) => {
      row.querySelector(".m-off").checked = false;
      row.querySelector(".m-from").value = "7";
      row.querySelector(".m-to").value = "16";
      updateRowDisabled(row);
    });
  });

  document.getElementById("sch-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("sch-save").addEventListener("click", async () => {
    const days = [];
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
    try {
      await api.put(`/api/persons/${person.id}/schedule`, { days });
      backdrop.remove();
      showToast("Schema sparat");
    } catch (e) { showToast(e.message, "error"); }
  });
}

function updateRowDisabled(row) {
  const off = row.querySelector(".m-off").checked;
  row.querySelector(".m-from").disabled = off;
  row.querySelector(".m-to").disabled = off;
}


// ---- Init ----
(async () => {
  await initPage("persons");
  await loadInitial();
  await loadPersons();
  setupImportControls();
  document.getElementById("new-person").addEventListener("click", () => openModal(null));
  document.getElementById("show-inactive").addEventListener("change", loadPersons);

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

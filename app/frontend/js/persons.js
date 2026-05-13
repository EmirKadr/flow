// Personregister – CRUD-vy med filter + sortering.

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
  return a ? a.color : "#ffffff";
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
}


// ---- Filter + sort ----
function passesFilter(p) {
  const match = (val, q) => {
    if (!q) return true;
    return String(val ?? "").toLowerCase().includes(q.toLowerCase());
  };
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
    const haColor = p.home_activity_id ? activityColor(p.home_activity_id) : "transparent";
    tr.innerHTML = `
      <td>${escapeHtml(p.name)}</td>
      <td>${escapeHtml(areaName(p.home_area_id))}</td>
      <td style="background: ${haColor};">${escapeHtml(activityLabel(p.home_activity_id))}</td>
      <td>${p.is_active ? "Ja" : "Nej"}</td>
      <td>${p.sort_order}</td>
      <td>
        <button data-edit="${p.id}">Redigera</button>
        <button data-schedule="${p.id}">Schema</button>
        ${p.is_active ? `<button data-delete="${p.id}" class="danger">Inaktivera</button>` : ""}
      </td>`;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll("button[data-edit]").forEach((b) =>
    b.addEventListener("click", () => openModal(persons.find((p) => p.id === Number(b.dataset.edit))))
  );
  tbody.querySelectorAll("button[data-delete]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Inaktivera person?")) return;
      await api.del(`/api/persons/${b.dataset.delete}`);
      await loadPersons();
    })
  );
  tbody.querySelectorAll("button[data-schedule]").forEach((b) =>
    b.addEventListener("click", () => openScheduleModal(persons.find((p) => p.id === Number(b.dataset.schedule))))
  );

  // Sortindikator
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


// ---- Modal: redigera/lägg till person ----
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
      <label><input id="m-active" type="checkbox" ${person?.is_active !== false ? "checked" : ""} /> Aktiv</label>
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
    } catch (e) {
      showToast(e.message, "error");
    }
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
  document.getElementById("new-person").addEventListener("click", () => openModal(null));
  document.getElementById("show-inactive").addEventListener("change", loadPersons);

  // Filter
  document.querySelectorAll("tr.filter-row input").forEach((inp) => {
    inp.addEventListener("input", () => {
      filters[inp.dataset.filter] = inp.value;
      renderRows();
    });
  });
  // Sort
  document.querySelectorAll("tr.sort-row th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (sortKey === key) sortAsc = !sortAsc;
      else { sortKey = key; sortAsc = true; }
      renderRows();
    });
  });
})();

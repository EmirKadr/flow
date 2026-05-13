// Ställeregister – CRUD av aktiviteter.

let areas = [];
let activities = [];

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
}

function areaName(id) {
  const a = areas.find((x) => x.id === id);
  return a ? a.name : "";
}

function activityLabel(id) {
  const a = activities.find((x) => x.id === id);
  return a ? a.label : "";
}

async function load() {
  activities = await api.get("/api/activities?include_inactive=true");
  const includeInactive = document.getElementById("show-inactive").checked;
  const acts = includeInactive ? activities : activities.filter((a) => a.is_active);
  const tbody = document.getElementById("acts-body");
  tbody.innerHTML = "";
  acts.forEach((a) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td style="background: ${a.color}; min-width: 40px;"></td>
      <td>${escapeHtml(a.label)}</td>
      <td>${escapeHtml(a.code)}</td>
      <td>${escapeHtml(areaName(a.area_id))}</td>
      <td>${escapeHtml(activityLabel(a.summary_activity_id) || "–")}</td>
      <td>${escapeHtml(a.category)}</td>
      <td>${a.sort_order}</td>
      <td>${a.is_active ? "Ja" : "Nej"}</td>
      <td>
        <button data-edit="${a.id}">Redigera</button>
        ${a.is_active ? `<button data-delete="${a.id}" class="danger">Inaktivera</button>` : ""}
      </td>`;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll("button[data-edit]").forEach((b) =>
    b.addEventListener("click", () => openModal(acts.find((x) => x.id === Number(b.dataset.edit))))
  );
  tbody.querySelectorAll("button[data-delete]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Inaktivera aktivitet?")) return;
      try { await api.del(`/api/activities/${b.dataset.delete}`); load(); }
      catch (e) { showToast(e.message, "error"); }
    })
  );
}

function openModal(act) {
  const isEdit = !!act;
  const summaryOptions = activities
    .filter((item) => !isEdit || item.id !== act.id)
    .map((item) => `<option value="${item.id}" ${act?.summary_activity_id === item.id ? "selected" : ""}>${escapeHtml(item.label)}</option>`)
    .join("");
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Redigera aktivitet" : "Ny aktivitet"}</h2>
      <label>Etikett (visas i celler)</label>
      <input id="m-label" value="${escapeHtml(act?.label || "")}" />
      <label>Kod (unik nyckel, ej synlig)</label>
      <input id="m-code" value="${escapeHtml(act?.code || "")}" />
      <label>Område</label>
      <select id="m-area">
        <option value="">(inget)</option>
        ${areas.map((a) => `<option value="${a.id}" ${act?.area_id === a.id ? "selected" : ""}>${escapeHtml(a.name)}</option>`).join("")}
      </select>
      <label>Summeras som i summering</label>
      <select id="m-summary">
        <option value="">Egen rad</option>
        ${summaryOptions}
      </select>
      <label>Färg (hex)</label>
      <input id="m-color" type="color" value="${act?.color || "#ffffff"}" />
      <label>Kategori</label>
      <select id="m-cat">
        <option value="work" ${act?.category !== 'absence' ? 'selected' : ''}>Arbete</option>
        <option value="absence" ${act?.category === 'absence' ? 'selected' : ''}>Frånvaro</option>
      </select>
      <label>Sortering</label>
      <input id="m-sort" type="number" value="${act?.sort_order ?? 0}" />
      <label><input id="m-active" type="checkbox" ${act?.is_active !== false ? "checked" : ""} /> Aktiv</label>
      <div class="actions">
        <button id="m-cancel">Avbryt</button>
        <button class="primary" id="m-save">Spara</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  document.getElementById("m-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("m-save").addEventListener("click", async () => {
    const payload = {
      code: document.getElementById("m-code").value.trim(),
      label: document.getElementById("m-label").value.trim(),
      area_id: document.getElementById("m-area").value ? Number(document.getElementById("m-area").value) : null,
      summary_activity_id: document.getElementById("m-summary").value ? Number(document.getElementById("m-summary").value) : null,
      color: document.getElementById("m-color").value,
      category: document.getElementById("m-cat").value,
      sort_order: Number(document.getElementById("m-sort").value) || 0,
      is_active: document.getElementById("m-active").checked,
    };

    if (!payload.label || !payload.code) {
      showToast("Etikett och kod krävs", "error");
      return;
    }
    try {
      if (isEdit) await api.put(`/api/activities/${act.id}`, payload);
      else await api.post("/api/activities", payload);
      backdrop.remove();
      load();
    } catch (e) { showToast(e.message, "error"); }
  });
}

(async () => {
  await initPage("stallen");
  areas = await api.get("/api/areas");
  await load();
  document.getElementById("new-act").addEventListener("click", () => openModal(null));
  document.getElementById("show-inactive").addEventListener("change", load);
})();

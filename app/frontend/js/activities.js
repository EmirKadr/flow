// Aktivitetsregister - CRUD av aktiviteter.

let areas = [];
let activities = [];
let businesses = [];
let currentUser = null;

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

function canSeeCodes() {
  return !!currentUser?.is_super_user;
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

function inferredActivityBusinessId(activity = null) {
  return activity?.business_id
    ?? businessIdFromArea(activity?.area_id)
    ?? businessIdFromActivity(activity?.summary_activity_id)
    ?? currentUser?.business_id
    ?? businesses[0]?.id
    ?? null;
}

function focusedAreaId() {
  return typeof preferredAreaIdFromFocus === "function" ? preferredAreaIdFromFocus(areas) : null;
}

function matchesAreaFocus(activity) {
  const areaId = focusedAreaId();
  return areaId == null || Number(activity?.area_id) === Number(areaId);
}

async function load() {
  activities = await api.get("/api/activities");
  const canEditActivities = canEditPage(currentUser, "activities");
  const acts = [...activities]
    .filter(matchesAreaFocus)
    .sort((a, b) => typeof compareActivitiesForAreaFocus === "function"
      ? compareActivitiesForAreaFocus(a, b, areas)
      : ((Number(a.sort_order) || 0) - (Number(b.sort_order) || 0)));
  const tbody = document.getElementById("acts-body");
  document.getElementById("code-column-header").hidden = !canSeeCodes();
  tbody.innerHTML = "";
  acts.forEach((a) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td style="background: ${a.color}; min-width: 40px;"></td>
      <td>${escapeHtml(a.label)}</td>
      ${canSeeCodes() ? `<td>${escapeHtml(a.code)}</td>` : ""}
      <td>${escapeHtml(areaName(a.area_id))}</td>
      <td>${escapeHtml(activityLabel(a.summary_activity_id) || "–")}</td>
      <td>${escapeHtml(a.category)}</td>
      <td>${a.sort_order}</td>
      <td>
        ${canEditActivities ? `
        <button data-edit="${a.id}">Redigera</button>
        <button data-delete="${a.id}" class="danger">Ta bort</button>
        ` : ""}
      </td>`;
    tbody.appendChild(tr);
  });

  if (!canEditActivities) return;
  tbody.querySelectorAll("button[data-edit]").forEach((b) =>
    b.addEventListener("click", () => openModal(acts.find((x) => x.id === Number(b.dataset.edit))))
  );
  tbody.querySelectorAll("button[data-delete]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Ta bort aktiviteten permanent?")) return;
      try { await api.del(`/api/activities/${b.dataset.delete}`); load(); }
      catch (e) { showToast(e.message, "error"); }
    })
  );
}

function openModal(act) {
  const isEdit = !!act;
  const selectedAreaId = act?.area_id ?? focusedAreaId();
  const selectedBusinessId = isEdit ? inferredActivityBusinessId(act) : (businessIdFromArea(selectedAreaId) ?? inferredActivityBusinessId(act));
  const summaryOptions = activities
    .filter((item) => !isEdit || item.id !== act.id)
    .map((item) => `<option value="${item.id}" ${act?.summary_activity_id === item.id ? "selected" : ""}>${escapeHtml(item.label)}</option>`)
    .join("");
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Redigera aktivitet" : "Ny aktivitet"}</h2>
      ${businessOptions(selectedBusinessId, isEdit)}
      <label>Etikett (visas i celler)</label>
      <input id="m-label" value="${escapeHtml(act?.label || "")}" />
      ${canSeeCodes() && act ? `
        <label>Kod (systemnyckel)</label>
        <input value="${escapeHtml(act.code || "")}" readonly />
      ` : ""}
      <label>Område</label>
      <select id="m-area">
        <option value="">(inget)</option>
        ${areas.map((a) => `<option value="${a.id}" ${Number(selectedAreaId) === Number(a.id) ? "selected" : ""}>${escapeHtml(a.name)}</option>`).join("")}
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
      <div class="actions">
        <button id="m-cancel">Avbryt</button>
        <button class="primary" id="m-save">Spara</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  document.getElementById("m-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("m-save").addEventListener("click", async () => {
    const payload = {
      label: document.getElementById("m-label").value.trim(),
      area_id: document.getElementById("m-area").value ? Number(document.getElementById("m-area").value) : null,
      summary_activity_id: document.getElementById("m-summary").value ? Number(document.getElementById("m-summary").value) : null,
      color: document.getElementById("m-color").value,
      category: document.getElementById("m-cat").value,
      sort_order: Number(document.getElementById("m-sort").value) || 0,
    };
    if (currentUser?.is_super_user && !isEdit) {
      payload.business_id = document.getElementById("m-business").value ? Number(document.getElementById("m-business").value) : null;
    }

    if (!payload.label) {
      showToast("Etikett krävs", "error");
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

function openImportResultModal(result) {
  const errors = result.errors || [];
  const shownErrors = errors.slice(0, 25);
  const extra = Math.max(0, errors.length - shownErrors.length);
  const rows = shownErrors.map((entry) => `
    <tr>
      <td>${entry.row}</td>
      <td>${escapeHtml(entry.label || "-")}</td>
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
            <thead><tr><th>Rad</th><th>Etikett</th><th>Fel</th></tr></thead>
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
    showToast(`${result.created} aktiviteter importerades. ${result.skipped} rad(er) hoppades över.`, "warn", 7000);
    openImportResultModal(result);
    return;
  }
  if (result.created) {
    showToast(`${result.created} aktiviteter importerades`, "success");
    return;
  }
  if (result.skipped) {
    showToast("Inga aktiviteter importerades", "error", 7000);
    openImportResultModal(result);
    return;
  }
  showToast("Importen innehöll inga aktiviteter", "warn");
}

async function importActivityFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const importButton = document.getElementById("import-activities");
  importButton.disabled = true;
  try {
    const result = await api.postForm("/api/activities/import", formData);
    showImportResult(result);
    await load();
  } catch (error) {
    showToast(error.message, "error", 7000);
  } finally {
    importButton.disabled = false;
  }
}

function openBulkActivitiesModal() {
  const businessColumn = currentUser?.is_super_user
    ? [{ key: "business", label: "Verksamhet", type: "select", options: businesses.map((business) => ({ value: business.code, label: business.name })) }]
    : [];
  openBulkImportGrid({
    title: "Flera nya aktiviteter",
    submitLabel: "Skapa aktiviteter",
    initialRows: 10,
    columns: [
      ...businessColumn,
      { key: "label", label: "Etikett" },
      { key: "area", label: "Område", type: "select", options: areas.map((area) => ({ value: area.name, label: area.name })) },
      { key: "summary_activity", label: "Summeras som", type: "select", options: activities.map((activity) => ({ value: activity.label, label: activity.label })) },
      { key: "sort_order", label: "Sortering", type: "number" },
    ],
    onSubmit: async (rows) => {
      const result = await api.post("/api/activities/import-rows", { rows });
      showImportResult(result);
      await load();
    },
  });
}

function setupImportControls() {
  const downloadButton = document.getElementById("download-activity-template");
  const importButton = document.getElementById("import-activities");
  const bulkButton = document.getElementById("bulk-activities");
  const helpButton = document.getElementById("activity-import-help");
  const fileInput = document.getElementById("activity-import-file");

  if (!canEditPage(currentUser, "activityImport")) return;

  bulkButton.hidden = false;
  downloadButton.hidden = false;
  importButton.hidden = false;
  helpButton.hidden = false;

  bulkButton.addEventListener("click", openBulkActivitiesModal);
  setupImportHelpButton("activity-import-help", "Importera aktiviteter");
  downloadButton.addEventListener("click", async () => {
    try {
      await api.download("/api/activities/import-template", "aktiviteter-importmall.xlsx");
    } catch (error) {
      showToast(error.message || "Kunde inte ladda ner importmallen.", "error", 7000);
    }
  });
  importButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files?.[0];
    fileInput.value = "";
    if (!file) return;
    await importActivityFile(file);
  });
}

(async () => {
  currentUser = await initPage("activities");
  if (!currentUser) return;
  const requests = [api.get("/api/areas")];
  if (currentUser?.is_super_user) requests.push(api.get("/api/businesses"));
  const [loadedAreas, loadedBusinesses] = await Promise.all(requests);
  areas = loadedAreas;
  businesses = loadedBusinesses || [];
  await load();
  setupImportControls();
  const newActButton = document.getElementById("new-act");
  newActButton.hidden = !canEditPage(currentUser, "activities");
  if (canEditPage(currentUser, "activities")) newActButton.addEventListener("click", () => openModal(null));
  window.addEventListener("flow:areaFocusChanged", () => load());
})();

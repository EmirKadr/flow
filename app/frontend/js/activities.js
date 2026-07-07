// @ts-check
// Sidans script körs i en IIFE så toppnivånamn (currentUser, areas, ...)
// inte kolliderar med andra sidors i TS globala scope. Ingen "use strict"
// — semantiken ska vara exakt densamma som före inpackningen.
(function () {
// Aktivitetsregister - CRUD av aktiviteter.

let areas = [];
let activities = [];
let businesses = [];
let kpiProcessOptions = [];
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

function businessName(id) {
  if (id == null) return "Utan verksamhet";
  const business = businesses.find((item) => Number(item.id) === Number(id));
  if (business) return business.name;
  if (Number(currentUser?.business_id) === Number(id)) {
    return currentUser?.business_name || currentUser?.business_code || "";
  }
  return `Verksamhet #${id}`;
}

function activityLabel(id) {
  const a = activities.find((x) => x.id === id);
  return a ? a.label : "";
}

function activityWorkTypeLabel(value) {
  return String(value || "normal").toLowerCase() === "vas" ? "VAS" : "Normal";
}

function splitKpiProcessNames(value) {
  const seen = new Set();
  const names = [];
  String(value || "").split(",").forEach((part) => {
    const name = part.trim();
    const key = name.toUpperCase();
    if (!name || seen.has(key)) return;
    seen.add(key);
    names.push(name);
  });
  return names;
}

function normalizeKpiProcessOptions(options) {
  const byKey = new Map();
  (Array.isArray(options) ? options : []).forEach((option) => {
    const value = String(option?.value || option?.label || "").trim();
    if (!value || value.includes(":")) return;
    const key = value.toUpperCase();
    if (!byKey.has(key)) byKey.set(key, { value, label: String(option?.label || value).trim() || value });
  });
  return Array.from(byKey.values()).sort((a, b) => a.label.localeCompare(b.label, "sv"));
}

function kpiProcessPickerOptions(selectedNames = []) {
  const byKey = new Map();
  kpiProcessOptions.forEach((option) => byKey.set(option.value.toUpperCase(), option));
  selectedNames.forEach((name) => {
    const value = String(name || "").trim();
    if (value && !byKey.has(value.toUpperCase())) byKey.set(value.toUpperCase(), { value, label: value });
  });
  return Array.from(byKey.values()).sort((a, b) => a.label.localeCompare(b.label, "sv"));
}

function kpiProcessSummary(values) {
  if (!values.length) return "Välj KPI-processer";
  if (values.length <= 2) return values.join(", ");
  return `${values.length} processer valda`;
}

function kpiProcessPickerHtml(value) {
  const selectedNames = splitKpiProcessNames(value);
  const selectedKeys = new Set(selectedNames.map((name) => name.toUpperCase()));
  const options = kpiProcessPickerOptions(selectedNames);
  const empty = !options.length;
  return `
      <label>KPI Mål</label>
      <div class="kpi-process-picker" id="m-kpi-process-picker">
        <button
          type="button"
          id="m-kpi-process-toggle"
          class="kpi-process-picker-toggle"
          aria-haspopup="true"
          aria-expanded="false"
          ${empty ? "disabled" : ""}
        >
          <span id="m-kpi-process-summary">${escapeHtml(empty ? "Inga KPI-processer hittades" : kpiProcessSummary(selectedNames))}</span>
          <span aria-hidden="true">v</span>
        </button>
        <div class="kpi-process-picker-menu" id="m-kpi-process-menu" hidden>
          ${options.map((option) => `
            <label class="modal-checkbox kpi-process-option">
              <input
                type="checkbox"
                data-kpi-process
                value="${escapeHtml(option.value)}"
                ${selectedKeys.has(option.value.toUpperCase()) ? "checked" : ""}
              />
              <span>${escapeHtml(option.label)}</span>
            </label>
          `).join("")}
        </div>
        <input id="m-kpi-process-name" type="hidden" value="${escapeHtml(selectedNames.join(", "))}" />
      </div>
  `;
}

function selectedKpiProcessNames(root = document) {
  return Array.from(root.querySelectorAll("[data-kpi-process]:checked")).map((input) => /** @type {HTMLInputElement} */ (input).value.trim()).filter(Boolean);
}

function syncKpiProcessPicker(root = document) {
  const hidden = root.getElementById ? root.getElementById("m-kpi-process-name") : root.querySelector("#m-kpi-process-name");
  const summary = root.getElementById ? root.getElementById("m-kpi-process-summary") : root.querySelector("#m-kpi-process-summary");
  const values = selectedKpiProcessNames(root);
  if (hidden) /** @type {HTMLInputElement} */ (hidden).value = values.join(", ");
  if (summary) summary.textContent = kpiProcessSummary(values);
}

function setupKpiProcessPicker(backdrop) {
  const picker = backdrop.querySelector("#m-kpi-process-picker");
  const toggle = backdrop.querySelector("#m-kpi-process-toggle");
  const menu = backdrop.querySelector("#m-kpi-process-menu");
  if (!picker || !toggle || !menu) return;
  toggle.addEventListener("click", () => {
    const open = menu.hidden;
    menu.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  });
  picker.querySelectorAll("[data-kpi-process]").forEach((input) => {
    input.addEventListener("change", () => syncKpiProcessPicker(backdrop));
  });
  backdrop.addEventListener("click", (event) => {
    if (picker.contains(event.target)) return;
    menu.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  });
  syncKpiProcessPicker(backdrop);
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
  render();
}

function render() {
  const canEditActivities = canEditPage(currentUser, "activities");
  const acts = [...activities]
    .filter(matchesAreaFocus)
    .sort((a, b) => typeof compareActivitiesForAreaFocus === "function"
      ? compareActivitiesForAreaFocus(a, b, areas)
      : ((Number(a.sort_order) || 0) - (Number(b.sort_order) || 0)));
  const tbody = document.getElementById("acts-body");
  document.getElementById("code-column-header").hidden = !canSeeCodes();
  tbody.innerHTML = "";
  if (!acts.length) {
    tbody.innerHTML = '<tr><td colspan="99" class="empty-state">Inga aktiviteter i valt fokus. Byt områdesfokus eller skapa en ny aktivitet.</td></tr>';
    return;
  }
  acts.forEach((a) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td style="background: ${a.color}; min-width: 40px;"></td>
      <td>${escapeHtml(a.label)}</td>
      ${canSeeCodes() ? `<td>${escapeHtml(a.code)}</td>` : ""}
      <td>${escapeHtml(businessName(a.business_id))}</td>
      <td>${escapeHtml(areaName(a.area_id))}</td>
      <td>${escapeHtml(activityLabel(a.summary_activity_id) || "–")}</td>
      <td>${escapeHtml(a.kpi_process_name || "–")}</td>
      <td>${escapeHtml(a.category)}</td>
      <td>${escapeHtml(activityWorkTypeLabel(a.work_type))}</td>
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
    b.addEventListener("click", () => openModal(acts.find((x) => x.id === Number(/** @type {HTMLElement} */ (b).dataset.edit))))
  );
  tbody.querySelectorAll("button[data-delete]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Ta bort aktiviteten permanent?")) return;
      try { await api.del(`/api/activities/${/** @type {HTMLElement} */ (b).dataset.delete}`); load(); }
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
      ${kpiProcessPickerHtml(act?.kpi_process_name || "")}
      <label>Färg (hex)</label>
      <input id="m-color" type="color" value="${act?.color || "#ffffff"}" />
      <label>Kategori</label>
      <select id="m-cat">
        <option value="work" ${act?.category !== 'absence' ? 'selected' : ''}>Arbete</option>
        <option value="absence" ${act?.category === 'absence' ? 'selected' : ''}>Frånvaro</option>
      </select>
      <label>Arbetstyp</label>
      <select id="m-work-type">
        <option value="normal" ${act?.work_type !== 'vas' ? 'selected' : ''}>Normal</option>
        <option value="vas" ${act?.work_type === 'vas' ? 'selected' : ''}>VAS</option>
      </select>
      <label>Sortering</label>
      <input id="m-sort" type="number" value="${act?.sort_order ?? 0}" />
      <div class="actions">
        <button id="m-cancel">Avbryt</button>
        <button class="primary" id="m-save">Spara</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  const categorySelect = document.getElementById("m-cat");
  const workTypeSelect = document.getElementById("m-work-type");
  const syncWorkTypeState = () => {
    const isAbsence = /** @type {HTMLInputElement} */ (categorySelect).value === "absence";
    if (isAbsence) /** @type {HTMLInputElement} */ (workTypeSelect).value = "normal";
    /** @type {HTMLInputElement} */ (workTypeSelect).disabled = isAbsence;
  };
  categorySelect.addEventListener("change", syncWorkTypeState);
  syncWorkTypeState();
  setupKpiProcessPicker(backdrop);

  document.getElementById("m-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("m-save").addEventListener("click", async () => {
    const category = /** @type {HTMLInputElement} */ (categorySelect).value;
    const payload = {
      label: /** @type {HTMLInputElement} */ (document.getElementById("m-label")).value.trim(),
      area_id: /** @type {HTMLInputElement} */ (document.getElementById("m-area")).value ? Number(/** @type {HTMLInputElement} */ (document.getElementById("m-area")).value) : null,
      summary_activity_id: /** @type {HTMLInputElement} */ (document.getElementById("m-summary")).value ? Number(/** @type {HTMLInputElement} */ (document.getElementById("m-summary")).value) : null,
      kpi_process_name: /** @type {HTMLInputElement} */ (document.getElementById("m-kpi-process-name")).value.trim() || null,
      color: /** @type {HTMLInputElement} */ (document.getElementById("m-color")).value,
      category,
      work_type: category === "absence" ? "normal" : /** @type {HTMLInputElement} */ (workTypeSelect).value,
      sort_order: Number(/** @type {HTMLInputElement} */ (document.getElementById("m-sort")).value) || 0,
    };
    if (currentUser?.is_super_user && !isEdit) {
      payload.business_id = /** @type {HTMLInputElement} */ (document.getElementById("m-business")).value ? Number(/** @type {HTMLInputElement} */ (document.getElementById("m-business")).value) : null;
    }

    if (!payload.label) {
      showToast("Etikett krävs", "error");
      return;
    }
    if (payload.kpi_process_name && payload.kpi_process_name.includes(":")) {
      showToast("KPI Mål ska bara vara processnamn, utan bolag", "error");
      return;
    }
    if (payload.kpi_process_name && payload.kpi_process_name.length > 255) {
      showToast("KPI Mål får vara max 255 tecken", "error");
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
  /** @type {HTMLInputElement} */ (importButton).disabled = true;
  try {
    const result = await api.postForm("/api/activities/import", formData);
    showImportResult(result);
    await load();
  } catch (error) {
    showToast(error.message, "error", 7000);
  } finally {
    /** @type {HTMLInputElement} */ (importButton).disabled = false;
  }
}

function openBulkActivitiesModal() {
  const businessColumn = currentUser?.is_super_user
    ? [{ key: "business", label: "Verksamhet", required: false, type: "select", options: businesses.map((business) => ({ value: business.code, label: business.name })) }]
    : [];
  openBulkImportGrid({
    title: "Flera nya aktiviteter",
    submitLabel: "Skapa aktiviteter",
    initialRows: 10,
    columns: [
      ...businessColumn,
      { key: "label", label: "Etikett", required: true },
      { key: "area", label: "Område", required: false, type: "select", options: areas.map((area) => ({ value: area.name, label: area.name })) },
      { key: "summary_activity", label: "Summeras som", required: false, type: "select", options: activities.map((activity) => ({ value: activity.label, label: activity.label })) },
      { key: "kpi_process_name", label: "KPI Mål", required: false },
      { key: "work_type", label: "Arbetstyp", required: false, type: "select", options: [{ value: "normal", label: "Normal" }, { value: "vas", label: "VAS" }] },
      { key: "sort_order", label: "Sortering", required: false, type: "number" },
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
    const file = /** @type {HTMLInputElement} */ (fileInput).files?.[0];
    /** @type {HTMLInputElement} */ (fileInput).value = "";
    if (!file) return;
    await importActivityFile(file);
  });
}

async function loadKpiProcessOptions() {
  try {
    const payload = await api.get("/api/activities/kpi-process-options", { cacheTtlMs: 5 * 60 * 1000 });
    kpiProcessOptions = normalizeKpiProcessOptions(payload);
  } catch (error) {
    kpiProcessOptions = [];
    console.warn("Kunde inte läsa KPI-processer", error);
    showToast("Kunde inte läsa KPI-processer", "warn", 4500);
  }
}

(async () => {
  currentUser = await initPage("activities");
  if (!currentUser) return;
  const requests = [api.get("/api/areas")];
  if (currentUser?.is_super_user) requests.push(api.get("/api/businesses"));
  const [loadedAreas, loadedBusinesses] = await Promise.all(requests);
  areas = loadedAreas;
  businesses = loadedBusinesses || [];
  await loadKpiProcessOptions();
  await load();
  setupImportControls();
  const newActButton = document.getElementById("new-act");
  newActButton.hidden = !canEditPage(currentUser, "activities");
  if (canEditPage(currentUser, "activities")) newActButton.addEventListener("click", () => openModal(null));
  // Områdesfokus filtrerar bara redan hämtade aktiviteter – rendera om klientside
  // istället för att hämta /api/activities på nytt (samma data).
  window.addEventListener("flow:areaFocusChanged", () => render());
})();
})();

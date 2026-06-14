function normalizeStaffingSettings(payload = {}) {
  const historyHours = Number(payload.history_hours);
  const minHours = Number(payload.min_history_hours);
  const maxHours = Number(payload.max_history_hours);
  return {
    history_hours: Number.isFinite(historyHours) ? historyHours : 40,
    min_history_hours: Number.isFinite(minHours) ? minHours : 1,
    max_history_hours: Number.isFinite(maxHours) ? maxHours : 240,
    activity_capacity_activity_ids: normalizeStaffingActivityCapacityActivityIds(payload.activity_capacity_activity_ids),
  };
}

function normalizeStaffingActivityCapacityActivityIds(value) {
  if (value == null) return null;
  if (!Array.isArray(value)) return null;
  const ids = [];
  value.forEach((item) => {
    const id = Number(item);
    if (Number.isInteger(id) && id > 0 && !ids.includes(id)) ids.push(id);
  });
  return ids;
}

function staffingActivityCapacityOptions() {
  return (allocationState.staffingActivities || [])
    .filter((activity) =>
      activity?.is_active !== false
      && String(activity?.category || "") !== "absence"
      && String(activity?.kpi_process_name || "").trim()
    )
    .sort((a, b) =>
      Number(a?.sort_order || 0) - Number(b?.sort_order || 0)
      || String(a?.label || "").localeCompare(String(b?.label || ""), "sv")
    );
}

async function loadStaffingActivities() {
  if (allocationState.staffingActivitiesLoading) return;
  allocationState.staffingActivitiesLoading = true;
  allocationState.staffingActivitiesError = "";
  renderStaffingSettingsPanel();
  try {
    const path = allocationScopedUrl("/api/activities", { fallbackToUser: true, includeAreaFocus: true });
    const payload = window.api?.get
      ? await window.api.get(path, { skipCache: true })
      : await allocationJson(path, { skipCache: true });
    allocationState.staffingActivities = Array.isArray(payload) ? payload : [];
    allocationState.staffingActivitiesLoaded = true;
  } catch (error) {
    allocationState.staffingActivities = [];
    allocationState.staffingActivitiesLoaded = true;
    allocationState.staffingActivitiesError = error?.message || "Kunde inte läsa aktiviteterna.";
  } finally {
    allocationState.staffingActivitiesLoading = false;
    renderStaffingSettingsPanel();
  }
}

async function loadStaffingSettings() {
  allocationState.staffingSettingsLoading = true;
  allocationState.staffingSettingsError = "";
  renderStaffingSettingsPanel();
  try {
    const path = allocationScopedUrl(STAFFING_SETTINGS_API, { fallbackToUser: true, includeAreaFocus: true });
    const payload = window.api?.get
      ? await window.api.get(path, { skipCache: true })
      : await allocationJson(path, { skipCache: true });
    allocationState.staffingSettings = normalizeStaffingSettings(payload);
  } catch (error) {
    allocationState.staffingSettingsError = error?.message || "Kunde inte läsa bemanningsinställningen.";
  } finally {
    allocationState.staffingSettingsLoading = false;
    renderStaffingSettingsPanel();
  }
}

async function saveStaffingSettings(form) {
  if (!form || !canEditStaffingSettings()) return;
  const input = form.querySelector("[data-staffing-history-hours]");
  const nextValue = Number(String(input?.value ?? "").replace(",", "."));
  const current = normalizeStaffingSettings(allocationState.staffingSettings);
  if (!Number.isFinite(nextValue)) {
    showToast("Ange ett giltigt timvärde.", "error", 3500);
    return;
  }
  if (nextValue < current.min_history_hours || nextValue > current.max_history_hours) {
    const minLabel = current.min_history_hours.toLocaleString("sv-SE", { maximumFractionDigits: 1 });
    const maxLabel = current.max_history_hours.toLocaleString("sv-SE", { maximumFractionDigits: 1 });
    showToast(`Värdet måste vara mellan ${minLabel} och ${maxLabel} timmar.`, "error", 4500);
    return;
  }
  const nextActivityIds = collectStaffingActivityCapacityActivityIds(form);
  const body = {
    history_hours: nextValue,
    activity_capacity_activity_ids: nextActivityIds,
  };
  allocationState.staffingSettingsSaving = true;
  allocationState.staffingSettingsError = "";
  renderStaffingSettingsPanel();
  try {
    const path = allocationScopedUrl(STAFFING_SETTINGS_API, { fallbackToUser: true, includeAreaFocus: true });
    const payload = window.api?.put
      ? await window.api.put(path, body)
      : await allocationJson(path, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
    allocationState.staffingSettings = normalizeStaffingSettings(payload);
    showToast("Bemanningsinställningen sparades.", "success", 2500);
  } catch (error) {
    allocationState.staffingSettingsError = error?.message || "Kunde inte spara bemanningsinställningen.";
    showToast(allocationState.staffingSettingsError, "error", 7000);
  } finally {
    allocationState.staffingSettingsSaving = false;
    renderStaffingSettingsPanel();
  }
}

function collectStaffingActivityCapacityActivityIds(form) {
  if (form.querySelector("[data-staffing-capacity-all]")?.checked) return null;
  const ids = [];
  form.querySelectorAll("[data-staffing-capacity-activity]:checked").forEach((input) => {
    const id = Number(input.value);
    if (Number.isInteger(id) && id > 0 && !ids.includes(id)) ids.push(id);
  });
  return ids;
}

function renderStaffingActivityCapacityControls(settings, disabled) {
  if (allocationState.staffingActivitiesLoading && !allocationState.staffingActivitiesLoaded) {
    return `<div class="staffing-settings-subsection"><p class="allocation-muted">Laddar aktiviteter...</p></div>`;
  }
  if (allocationState.staffingActivitiesError) {
    return `<div class="staffing-settings-subsection"><p class="allocation-status error">${allocationEscape(allocationState.staffingActivitiesError)}</p></div>`;
  }
  const options = staffingActivityCapacityOptions();
  if (!options.length) {
    return `
      <div class="staffing-settings-subsection">
        <h3>Historiskt snitt</h3>
        <p class="allocation-muted">Det finns inga aktiva aktiviteter med KPI-process att välja.</p>
      </div>
    `;
  }
  const selectedIds = settings.activity_capacity_activity_ids;
  const allSelected = selectedIds == null;
  const selectedSet = new Set(selectedIds || []);
  const disabledAttr = disabled ? "disabled" : "";
  const activityDisabledAttr = disabled || allSelected ? "disabled" : "";
  return `
    <div class="staffing-settings-subsection">
      <h3>Historiskt snitt</h3>
      <p class="allocation-muted">Välj vilka aktiviteter som får visa historiskt snitt när användaren håller musen över en bemanningscell.</p>
      <label class="modal-checkbox">
        <input type="checkbox" data-staffing-capacity-all ${allSelected ? "checked" : ""} ${disabledAttr}>
        <span>Visa för alla KPI-aktiviteter</span>
      </label>
      <div class="staffing-capacity-activity-grid">
        ${options.map((activity) => {
          const id = Number(activity.id);
          const checked = allSelected || selectedSet.has(id);
          return `
            <label class="modal-checkbox">
              <input
                type="checkbox"
                data-staffing-capacity-activity
                value="${allocationEscape(id)}"
                ${checked ? "checked" : ""}
                ${activityDisabledAttr}
              >
              <span>${allocationEscape(activity.label || activity.code || id)}</span>
            </label>
          `;
        }).join("")}
      </div>
    </div>
  `;
}


function allocationSettingsTabs() {
  const tabs = [];
  if (canViewAllocationMapSettings()) tabs.push({ id: "map", label: "Ytkarta" });
  if (canViewAllocationProcessMatrix()) tabs.push({ id: "process-matrix", label: "Bearbeta" });
  if (canViewStaffingSettings()) tabs.push({ id: "staffing", label: "Bemanning" });
  return tabs;
}

function allocationEnsureSettingsTab() {
  const tabs = allocationSettingsTabs();
  if (!tabs.some((tab) => tab.id === allocationState.settingsTab)) {
    allocationState.settingsTab = tabs[0]?.id || "";
  }
  return tabs;
}

function renderAllocationProcessMatrixSettingsPanel(panel = document.getElementById("allocation-settings-panel")) {
  if (!panel) return;
  if (!canViewAllocationProcessMatrix()) {
    panel.innerHTML = `<p class="allocation-status error">Saknar behörighet till Bearbeta-matris.</p>`;
    return;
  }
  if (!allocationState.processMatrix && !allocationState.processMatrixLoading) {
    panel.innerHTML = `<p class="allocation-muted">Laddar Bearbeta-matris...</p>`;
    void loadAllocationProcessMatrix().then(() => renderAllocationProcessMatrixSettingsPanel(panel));
    return;
  }
  if (!allocationState.processMatrix && allocationState.processMatrixLoading) {
    panel.innerHTML = `<p class="allocation-muted">Laddar Bearbeta-matris...</p>`;
    return;
  }
  const canEditMatrix = canEditAllocationProcessMatrix();
  let draft = allocationProcessMatrixDraft();
  panel.innerHTML = `
    <section class="allocation-process-matrix-settings-panel">
      <div class="allocation-settings-heading">
        <h2>Bearbeta-matris</h2>
        <p class="allocation-muted">Styr vilka Bearbeta-funktioner som visas per toggle.</p>
      </div>
      ${allocationState.processMatrixError ? `<p class="allocation-status error">${allocationEscape(allocationState.processMatrixError)}</p>` : ""}
      <div id="allocation-process-matrix-settings-editor"></div>
      <div class="actions">
        ${canEditMatrix ? `<button type="button" id="allocation-process-matrix-settings-defaults">Standard</button>` : ""}
        ${canEditMatrix ? `<button type="button" class="primary" id="allocation-process-matrix-settings-save">Spara</button>` : ""}
      </div>
    </section>
  `;
  const editor = panel.querySelector("#allocation-process-matrix-settings-editor");
  const renderEditor = () => renderAllocationProcessMatrixEditor(editor, draft, !canEditMatrix);
  renderEditor();
  panel.querySelector("#allocation-process-matrix-settings-defaults")?.addEventListener("click", () => {
    draft = allocationProcessMatrixDraft(true);
    renderEditor();
  });
  panel.querySelector("#allocation-process-matrix-settings-save")?.addEventListener("click", async () => {
    const button = panel.querySelector("#allocation-process-matrix-settings-save");
    button.disabled = true;
    try {
      const query = allocationScopedQuery({ fallbackToUser: true, includeAreaFocus: true });
      const response = await allocationJson(`${ALLOCATION_API}/process-matrix${query}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matrix: collectAllocationProcessMatrixDraft(editor) }),
      });
      allocationState.processMatrix = normalizeAllocationProcessMatrix(response);
      allocationState.processMatrixError = "";
      cacheAllocationBootData();
      showToast("Bearbeta-matris sparades.", "success", 2500);
      renderAllocationProcessMatrixSettingsPanel(panel);
    } catch (error) {
      button.disabled = false;
      allocationState.processMatrixError = error.message || "Kunde inte spara Bearbeta-matris.";
      showToast(allocationState.processMatrixError, "error", 7000);
    }
  });
}

function renderStaffingSettingsPanel(panel = document.getElementById("allocation-settings-panel")) {
  if (!panel) return;
  if (!canViewStaffingSettings()) {
    panel.innerHTML = `<p class="allocation-status error">Saknar behörighet till bemanningsinställningar.</p>`;
    return;
  }
  if (!allocationState.staffingSettings && !allocationState.staffingSettingsLoading) {
    panel.innerHTML = `<p class="allocation-muted">Laddar bemanningsinställningar...</p>`;
    void loadStaffingSettings();
    return;
  }
  if (!allocationState.staffingSettings && allocationState.staffingSettingsLoading) {
    panel.innerHTML = `<p class="allocation-muted">Laddar bemanningsinställningar...</p>`;
    return;
  }
  if (!allocationState.staffingActivitiesLoaded && !allocationState.staffingActivitiesLoading) {
    void loadStaffingActivities();
  }
  const settings = normalizeStaffingSettings(allocationState.staffingSettings);
  const canEdit = canEditStaffingSettings();
  const disabled = canEdit && !allocationState.staffingSettingsSaving && !allocationState.staffingSettingsLoading ? "" : "disabled";
  const minLabel = settings.min_history_hours.toLocaleString("sv-SE", { maximumFractionDigits: 1 });
  const maxLabel = settings.max_history_hours.toLocaleString("sv-SE", { maximumFractionDigits: 1 });
  panel.innerHTML = `
    <section class="allocation-staffing-settings-panel">
      <div class="allocation-settings-heading">
        <h2>Bemanningskalkyl</h2>
        <p class="allocation-muted">Historiktimmar används av cellernas historiska snitt och automatiska bemanningskalkyler.</p>
      </div>
      ${allocationState.staffingSettingsError ? `<p class="allocation-status error">${allocationEscape(allocationState.staffingSettingsError)}</p>` : ""}
      <form class="staffing-settings-form" data-staffing-settings-form>
        <label>
          <span>Historikfönster</span>
          <input
            data-staffing-history-hours
            type="number"
            min="${allocationEscape(settings.min_history_hours)}"
            max="${allocationEscape(settings.max_history_hours)}"
            step="1"
            value="${allocationEscape(settings.history_hours)}"
            ${disabled}
          />
        </label>
        <span class="allocation-muted">Tillåtet intervall: ${allocationEscape(minLabel)}-${allocationEscape(maxLabel)} timmar.</span>
        ${renderStaffingActivityCapacityControls(settings, Boolean(disabled))}
        <div class="actions">
          <button type="submit" class="primary" ${canEdit ? disabled : "disabled"}>
            ${allocationState.staffingSettingsSaving ? "Sparar..." : "Spara"}
          </button>
        </div>
      </form>
    </section>
  `;
  panel.querySelector("[data-staffing-settings-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    void saveStaffingSettings(event.currentTarget);
  });
  panel.querySelector("[data-staffing-capacity-all]")?.addEventListener("change", (event) => {
    const checked = Boolean(event.currentTarget?.checked);
    panel.querySelectorAll("[data-staffing-capacity-activity]").forEach((input) => {
      input.disabled = checked || Boolean(disabled);
      if (checked) input.checked = true;
    });
  });
}

function renderAllocationMapSettingsView() {
  const tabs = allocationEnsureSettingsTab();
  if (!tabs.length) {
    renderAllocationShell(`
      <section class="allocation-panel">
        <p class="allocation-status error">Saknar behörighet till inställningar.</p>
      </section>
    `);
    return;
  }
  renderAllocationShell(`
    <section class="allocation-settings-page">
      <div class="allocation-settings-tabs" role="tablist" aria-label="Inställningar">
        ${tabs.map((tab) => `
          <button
            type="button"
            class="allocation-settings-tab ${tab.id === allocationState.settingsTab ? "active" : ""}"
            data-settings-tab="${allocationEscape(tab.id)}"
            role="tab"
            aria-selected="${tab.id === allocationState.settingsTab ? "true" : "false"}"
          >${allocationEscape(tab.label)}</button>
        `).join("")}
      </div>
      <div class="allocation-settings-panel" id="allocation-settings-panel" role="tabpanel"></div>
    </section>
  `);
  document.querySelectorAll("[data-settings-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextTab = button.dataset.settingsTab || "";
      if (!tabs.some((tab) => tab.id === nextTab) || nextTab === allocationState.settingsTab) return;
      allocationState.settingsTab = nextTab;
      renderAllocationMapSettingsView();
    });
  });
  const panel = document.getElementById("allocation-settings-panel");
  if (allocationState.settingsTab === "staffing") {
    renderStaffingSettingsPanel(panel);
  } else if (allocationState.settingsTab === "process-matrix") {
    renderAllocationProcessMatrixSettingsPanel(panel);
  } else {
    panel.innerHTML = `
      <section class="allocation-map-settings-page-panel">
        <div id="allocation-map-settings-editor"><p class="allocation-muted">Laddar ytkarta...</p></div>
      </section>
    `;
    void mountAllocationMapSettingsPage(document.getElementById("allocation-map-settings-editor"));
  }
}


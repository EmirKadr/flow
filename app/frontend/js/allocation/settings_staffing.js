// Utdelad ur allocation/settings_view.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter settings_view.js via <script>-tagg.

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

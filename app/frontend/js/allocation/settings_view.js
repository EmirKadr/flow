// @ts-check
function renderProductivityFinanceSettingsPanel(panel = document.getElementById("allocation-settings-panel")) {
  if (!panel) return;
  closeProductivityFinanceContextMenu();
  if (!canViewProductivityFinanceSettings()) {
    panel.innerHTML = `<p class="allocation-status error">Saknar behörighet till intäkt/utgift-inställningar.</p>`;
    return;
  }
  if (!allocationState.productivityFinanceSettings && !allocationState.productivityFinanceSettingsLoading) {
    panel.innerHTML = `<p class="allocation-muted">Laddar intäkt/utgift-inställningar...</p>`;
    void loadProductivityFinanceSettings();
    return;
  }
  if (!allocationState.productivityFinanceSettings && allocationState.productivityFinanceSettingsLoading) {
    panel.innerHTML = `<p class="allocation-muted">Laddar intäkt/utgift-inställningar...</p>`;
    return;
  }
  const settings = normalizeProductivityFinanceSettings(allocationState.productivityFinanceSettings);
  const canEdit = canEditProductivityFinanceSettings();
  const disabled = canEdit && !allocationState.productivityFinanceSettingsSaving && !allocationState.productivityFinanceSettingsLoading ? "" : "disabled";
  const codes = settings.company_codes.slice().sort((a, b) => a.localeCompare(b, "sv"));
  panel.innerHTML = `
    <section class="allocation-productivity-finance-settings-panel">
      <form class="productivity-finance-settings-form" data-productivity-finance-settings-form>
        <div class="allocation-settings-heading productivity-finance-settings-heading">
          <div>
        <h2>Intäkt/utgift</h2>
        <p class="allocation-muted">Kostnad räknas på arbetad tid. VAS-intäkt räknas på VAS-tid per bolag och arbetstyp.</p>
      </div>
          <div class="actions productivity-finance-settings-actions">
            <button type="submit" class="primary" ${canEdit ? disabled : "disabled"}>
              ${allocationState.productivityFinanceSettingsSaving ? "Sparar..." : "Spara"}
            </button>
          </div>
        </div>
        ${allocationState.productivityFinanceSettingsError ? `<p class="allocation-status error">${allocationEscape(allocationState.productivityFinanceSettingsError)}</p>` : ""}
        <label>
          <span>Kostnad per timme</span>
          <input
            data-productivity-finance-hourly-cost
            type="number"
            min="${allocationEscape(settings.min_amount)}"
            max="${allocationEscape(settings.max_amount)}"
            step="0.01"
            value="${allocationEscape(settings.hourly_cost)}"
            ${disabled}
          />
        </label>
        <span class="allocation-muted">Tillåtet intervall: ${allocationEscape(productivityFinanceAmountBoundsText(settings))}.</span>
        <div class="productivity-finance-process-check-controls">
          <button type="button" class="secondary" data-productivity-finance-process-check>Kontrollera int\u00e4kter/processer</button>
        </div>
        <div class="productivity-finance-settings-section">
          <h3>Intäkter per bolag</h3>
          <div class="productivity-finance-company-grid">
            ${codes.length ? codes.map((code) => `
              <section class="productivity-finance-company-row" data-productivity-finance-company-row data-company-code="${allocationEscape(code)}">
                <div class="productivity-finance-invoice-heading">
                  <h3>${allocationEscape(code)}</h3>
                </div>
                <div class="productivity-finance-invoice-table">
                  <div class="productivity-finance-invoice-cell is-header">Tjänst</div>
                  <div class="productivity-finance-invoice-cell is-header">Beskrivning</div>
                  <div class="productivity-finance-invoice-cell is-header">Enhet</div>
                  <div class="productivity-finance-invoice-cell is-header">Pris (SEK)</div>
                  <div class="productivity-finance-invoice-cell is-header">ST / Antal</div>
                  ${renderProductivityFinanceInvoiceRows(settings.invoice_rows_by_company[code] || [], settings, disabled)}
                </div>
              </section>
            `).join("") : `<p class="allocation-muted">Inga bolagskoder finns på verksamheten.</p>`}
          </div>
        </div>
      </form>
    </section>
  `;
  panel.querySelector("[data-productivity-finance-settings-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    void saveProductivityFinanceSettings(event.currentTarget);
  });
  panel.querySelectorAll("[data-productivity-finance-invoice-row]").forEach((row) => {
    row.addEventListener("contextmenu", (event) => openProductivityFinanceContextMenu(event, row));
  });
  panel.querySelector("[data-productivity-finance-process-check]")?.addEventListener("click", (event) => {
    void openProductivityFinanceProcessCheckDialog(/** @type {Element} */ (event.currentTarget).closest("[data-productivity-finance-settings-form]"));
  });
}


function allocationSettingsTabs() {
  const tabs = [];
  if (canViewAllocationMapSettings()) tabs.push({ id: "map", label: "Ytkarta" });
  if (canViewAllocationProcessMatrix()) tabs.push({ id: "process-matrix", label: "Bearbeta" });
  if (canViewStaffingSettings()) tabs.push({ id: "staffing", label: "Bemanning" });
  if (canViewProductivityFinanceSettings()) tabs.push({ id: "productivity-finance", label: "Intäkt/utgift" });
  return tabs;
}

function allocationRequestedSettingsTab() {
  const params = new URLSearchParams(window.location.search || "");
  const normalized = String(params.get("tab") || params.get("settings_tab") || window.location.hash.replace(/^#/, "") || "").trim().toLowerCase();
  const aliases = {
    ytkarta: "map", map: "map",
    bearbeta: "process-matrix", "process-matrix": "process-matrix", process: "process-matrix",
    staffing: "staffing", bemanning: "staffing",
    finance: "productivity-finance", "productivity-finance": "productivity-finance", "intakt-utgift": "productivity-finance", "intäkt-utgift": "productivity-finance",
  };
  return aliases[normalized] || "";
}

function allocationEnsureSettingsTab() {
  const tabs = allocationSettingsTabs();
  if (!allocationState.settingsTab) {
    const requestedTab = allocationRequestedSettingsTab();
    if (tabs.some((tab) => tab.id === requestedTab)) allocationState.settingsTab = requestedTab;
  }
  if (!tabs.some((tab) => tab.id === allocationState.settingsTab)) {
    allocationState.settingsTab = tabs[0]?.id || "";
  }
  return tabs;
}

function allocationReplaceSettingsTabUrl(tabId) {
  const url = new URL(window.location.href);
  url.searchParams.set("tab", tabId);
  window.history?.replaceState?.(null, "", `${url.pathname}${url.search}${url.hash}`);
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
    /** @type {HTMLInputElement} */ (button).disabled = true;
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
      /** @type {HTMLInputElement} */ (button).disabled = false;
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
    const checked = Boolean(/** @type {HTMLInputElement} */ (event.currentTarget)?.checked);
    panel.querySelectorAll("[data-staffing-capacity-activity]").forEach((input) => {
      /** @type {HTMLInputElement} */ (input).disabled = checked || Boolean(disabled);
      if (checked) /** @type {HTMLInputElement} */ (input).checked = true;
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
      const nextTab = /** @type {HTMLElement} */ (button).dataset.settingsTab || "";
      if (!tabs.some((tab) => tab.id === nextTab) || nextTab === allocationState.settingsTab) return;
      allocationState.settingsTab = nextTab;
      allocationReplaceSettingsTabUrl(nextTab);
      renderAllocationMapSettingsView();
    });
  });
  const panel = document.getElementById("allocation-settings-panel");
  if (allocationState.settingsTab === "staffing") {
    renderStaffingSettingsPanel(panel);
  } else if (allocationState.settingsTab === "productivity-finance") {
    renderProductivityFinanceSettingsPanel(panel);
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


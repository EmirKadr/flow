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

function normalizeProductivityFinanceCompanyCode(value) {
  return String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9_-]/g, "")
    .slice(0, 20);
}

function productivityFinanceAmountNumber(value) {
  return Number(String(value ?? "").trim().replace(",", "."));
}

const PRODUCTIVITY_FINANCE_COLLAR_TYPES = [
  { value: "blue_collar", label: "Blue collar" },
  { value: "white_collar", label: "White collar" },
];

const PRODUCTIVITY_FINANCE_VAS_RATE_TYPES = [
  { value: "normal", label: "Normal" },
  { value: "ot_50", label: "ÖT 1 - 50%" },
  { value: "ob1_40", label: "OB1 - 40%" },
  { value: "ob2_70", label: "OB2 - 70%" },
  { value: "ob3_100", label: "OB3 - 100%" },
];

function normalizeProductivityFinanceAmount(value, fallback = 0, minimum = 0, maximum = 10000000) {
  const number = productivityFinanceAmountNumber(value);
  const safe = Number.isFinite(number) ? number : Number(fallback || 0);
  return Math.max(minimum, Math.min(maximum, safe));
}

function normalizeProductivityFinanceVasRateAmounts(value, minAmount, maxAmount) {
  const amounts = {};
  if (value && typeof value === "object" && !Array.isArray(value)) {
    PRODUCTIVITY_FINANCE_VAS_RATE_TYPES.forEach((rateType) => {
      amounts[rateType.value] = normalizeProductivityFinanceAmount(value[rateType.value], 0, minAmount, maxAmount);
    });
    return amounts;
  }
  PRODUCTIVITY_FINANCE_VAS_RATE_TYPES.forEach((rateType) => {
    amounts[rateType.value] = rateType.value === "normal"
      ? normalizeProductivityFinanceAmount(value, 0, minAmount, maxAmount)
      : 0;
  });
  return amounts;
}

function normalizeProductivityFinanceCompanyRates(value, minAmount, maxAmount) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const blueValue = value.blue_collar ?? value.blueCollar ?? value.blue;
    const whiteValue = value.white_collar ?? value.whiteCollar ?? value.white;
    if (blueValue !== undefined || whiteValue !== undefined) {
      return {
        blue_collar: normalizeProductivityFinanceVasRateAmounts(blueValue, minAmount, maxAmount),
        white_collar: normalizeProductivityFinanceVasRateAmounts(whiteValue, minAmount, maxAmount),
      };
    }
    const sharedRates = normalizeProductivityFinanceVasRateAmounts(value, minAmount, maxAmount);
    return {
      blue_collar: { ...sharedRates },
      white_collar: { ...sharedRates },
    };
  }
  const amounts = normalizeProductivityFinanceVasRateAmounts(value, minAmount, maxAmount);
  return {
    blue_collar: { ...amounts },
    white_collar: { ...amounts },
  };
}

function normalizeProductivityFinanceInvoiceRows(value, minAmount, maxAmount) {
  if (!Array.isArray(value)) return [];
  const rows = [];
  const seen = new Set();
  value.forEach((item) => {
    if (!item || typeof item !== "object") return;
    const id = String(item.id || "").trim().slice(0, 80);
    if (!id || seen.has(id)) return;
    seen.add(id);
    rows.push({
      id,
      section: String(item.section || "").trim().slice(0, 80),
      service: String(item.service || "").trim().slice(0, 120),
      description: String(item.description || "").trim().slice(0, 160),
      unit: String(item.unit || "").trim().slice(0, 160),
      price: normalizeProductivityFinanceAmount(item.price, 0, minAmount, maxAmount),
      quantity: normalizeProductivityFinanceAmount(item.quantity, 0, 0, 1000000000),
      calculation_prompt: String(item.calculation_prompt || "").trim().slice(0, 4000),
      calculation_plan: item.calculation_plan && typeof item.calculation_plan === "object" && !Array.isArray(item.calculation_plan) ? item.calculation_plan : null,
      calculation_sql: String(item.calculation_sql || "").trim().slice(0, 8000),
      collar_type: PRODUCTIVITY_FINANCE_COLLAR_TYPES.some((option) => option.value === item.collar_type) ? item.collar_type : null,
      vas_rate_type: PRODUCTIVITY_FINANCE_VAS_RATE_TYPES.some((option) => option.value === item.vas_rate_type) ? item.vas_rate_type : null,
    });
  });
  return rows;
}

function productivityFinanceVasRatesFromInvoiceRows(rows) {
  const rates = {};
  PRODUCTIVITY_FINANCE_COLLAR_TYPES.forEach((collar) => {
    rates[collar.value] = {};
    PRODUCTIVITY_FINANCE_VAS_RATE_TYPES.forEach((rateType) => {
      rates[collar.value][rateType.value] = 0;
    });
  });
  (rows || []).forEach((row) => {
    if (!row.collar_type || !row.vas_rate_type || !rates[row.collar_type]) return;
    rates[row.collar_type][row.vas_rate_type] = normalizeProductivityFinanceAmount(row.price);
  });
  return rates;
}

function productivityFinanceJsonAttribute(value) {
  if (!value) return "";
  try {
    return JSON.stringify(value);
  } catch (_error) {
    return "";
  }
}

function productivityFinanceParseJson(value) {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch (_error) {
    return null;
  }
}

function normalizeProductivityFinanceSettings(payload = {}) {
  const minAmount = Number.isFinite(Number(payload.min_amount)) ? Number(payload.min_amount) : 0;
  const maxAmount = Number.isFinite(Number(payload.max_amount)) ? Number(payload.max_amount) : 10000000;
  const companyCodes = [];
  (payload.company_codes || []).forEach((rawCode) => {
    const code = normalizeProductivityFinanceCompanyCode(rawCode);
    if (code && !companyCodes.includes(code)) companyCodes.push(code);
  });
  const allowedCodes = new Set(companyCodes);
  const vasRates = {};
  const invoiceRowsByCompany = {};
  Object.entries(payload.invoice_rows_by_company || {}).forEach(([rawCode, rows]) => {
    const code = normalizeProductivityFinanceCompanyCode(rawCode);
    if (!code || !allowedCodes.has(code)) return;
    invoiceRowsByCompany[code] = normalizeProductivityFinanceInvoiceRows(rows, minAmount, maxAmount);
    vasRates[code] = productivityFinanceVasRatesFromInvoiceRows(invoiceRowsByCompany[code]);
  });
  Object.entries(payload.vas_hourly_revenue_by_company || {}).forEach(([rawCode, value]) => {
    const code = normalizeProductivityFinanceCompanyCode(rawCode);
    if (!code || !allowedCodes.has(code)) return;
    vasRates[code] = normalizeProductivityFinanceCompanyRates(value, minAmount, maxAmount);
  });
  return {
    hourly_cost: normalizeProductivityFinanceAmount(payload.hourly_cost, 0, minAmount, maxAmount),
    min_amount: minAmount,
    max_amount: maxAmount,
    vas_hourly_revenue_by_company: vasRates,
    invoice_rows_by_company: invoiceRowsByCompany,
    company_codes: companyCodes,
  };
}

async function loadProductivityFinanceSettings() {
  allocationState.productivityFinanceSettingsLoading = true;
  allocationState.productivityFinanceSettingsError = "";
  renderProductivityFinanceSettingsPanel();
  try {
    const path = allocationScopedUrl(PRODUCTIVITY_FINANCE_SETTINGS_API, { fallbackToUser: true, includeAreaFocus: true });
    const payload = window.api?.get
      ? await window.api.get(path, { skipCache: true })
      : await allocationJson(path, { skipCache: true });
    allocationState.productivityFinanceSettings = normalizeProductivityFinanceSettings(payload);
  } catch (error) {
    allocationState.productivityFinanceSettingsError = error?.message || "Kunde inte läsa intäkt/utgift-inställningen.";
  } finally {
    allocationState.productivityFinanceSettingsLoading = false;
    renderProductivityFinanceSettingsPanel();
  }
}

function productivityFinanceAmountBoundsText(settings) {
  const minLabel = settings.min_amount.toLocaleString("sv-SE", { maximumFractionDigits: 2 });
  const maxLabel = settings.max_amount.toLocaleString("sv-SE", { maximumFractionDigits: 2 });
  return `${minLabel}-${maxLabel} kr`;
}

function collectProductivityFinanceSettings(form) {
  const current = normalizeProductivityFinanceSettings(allocationState.productivityFinanceSettings);
  const hourlyCost = productivityFinanceAmountNumber(form.querySelector("[data-productivity-finance-hourly-cost]")?.value);
  if (!Number.isFinite(hourlyCost)) {
    return { error: "Ange en giltig kostnad per timme." };
  }
  if (hourlyCost < current.min_amount || hourlyCost > current.max_amount) {
    return { error: `Kostnad per timme måste vara mellan ${productivityFinanceAmountBoundsText(current)}.` };
  }
  const rates = {};
  const invoiceRowsByCompany = {};
  for (const row of form.querySelectorAll("[data-productivity-finance-company-row]")) {
    const code = normalizeProductivityFinanceCompanyCode(row.dataset.companyCode);
    if (!code) continue;
    const invoiceRows = [];
    for (const invoiceRow of row.querySelectorAll("[data-productivity-finance-invoice-row]")) {
      const value = productivityFinanceAmountNumber(invoiceRow.querySelector("[data-productivity-finance-row-price]")?.value);
      const label = [
        invoiceRow.dataset.service,
        invoiceRow.dataset.description,
        invoiceRow.dataset.unit,
      ].filter(Boolean).join(" ");
      if (!Number.isFinite(value)) {
        return { error: `Ange en giltig intäkt för ${code} ${label}.` };
      }
      if (value < current.min_amount || value > current.max_amount) {
        return { error: `Intäkt för ${code} ${label} måste vara mellan ${productivityFinanceAmountBoundsText(current)}.` };
      }
      invoiceRows.push({
        id: String(invoiceRow.dataset.rowId || ""),
        section: String(invoiceRow.dataset.section || ""),
        service: String(invoiceRow.dataset.service || ""),
        description: String(invoiceRow.dataset.description || ""),
        unit: String(invoiceRow.dataset.unit || ""),
        price: value,
        quantity: normalizeProductivityFinanceAmount(invoiceRow.dataset.quantity || 0, 0, 0, 1000000000),
        calculation_prompt: String(invoiceRow.dataset.calculationPrompt || ""),
        calculation_plan: productivityFinanceParseJson(invoiceRow.dataset.calculationPlan),
        calculation_sql: String(invoiceRow.dataset.calculationSql || ""),
        collar_type: invoiceRow.dataset.collar || null,
        vas_rate_type: invoiceRow.dataset.vasRateType || null,
      });
    }
    invoiceRowsByCompany[code] = invoiceRows;
    rates[code] = productivityFinanceVasRatesFromInvoiceRows(invoiceRows);
  }
  return {
    value: {
      hourly_cost: hourlyCost,
      vas_hourly_revenue_by_company: rates,
      invoice_rows_by_company: invoiceRowsByCompany,
    },
  };
}

async function saveProductivityFinanceSettings(form) {
  if (!form || !canEditProductivityFinanceSettings()) return;
  const collected = collectProductivityFinanceSettings(form);
  if (collected.error) {
    showToast(collected.error, "error", 4500);
    return;
  }
  allocationState.productivityFinanceSettingsSaving = true;
  allocationState.productivityFinanceSettingsError = "";
  renderProductivityFinanceSettingsPanel();
  try {
    const path = allocationScopedUrl(PRODUCTIVITY_FINANCE_SETTINGS_API, { fallbackToUser: true, includeAreaFocus: true });
    const payload = window.api?.put
      ? await window.api.put(path, collected.value)
      : await allocationJson(path, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(collected.value),
        });
    allocationState.productivityFinanceSettings = normalizeProductivityFinanceSettings(payload);
    showToast("Intäkt/utgift-inställningen sparades.", "success", 2500);
  } catch (error) {
    allocationState.productivityFinanceSettingsError = error?.message || "Kunde inte spara intäkt/utgift-inställningen.";
    showToast(allocationState.productivityFinanceSettingsError, "error", 7000);
  } finally {
    allocationState.productivityFinanceSettingsSaving = false;
    renderProductivityFinanceSettingsPanel();
  }
}

function renderProductivityFinanceInvoiceRows(rows, settings, disabled) {
  let currentSection = null;
  return (rows || []).map((row) => {
    const section = String(row.section || "");
    const sectionMarkup = section && section !== currentSection
      ? `<div class="productivity-finance-invoice-section">${allocationEscape(section)}</div>`
      : "";
    currentSection = section;
    const vasAttrs = row.collar_type && row.vas_rate_type
      ? `
        data-productivity-finance-company-rate
        data-productivity-finance-collar="${allocationEscape(row.collar_type)}"
        data-productivity-finance-rate-type="${allocationEscape(row.vas_rate_type)}"
      `
      : "";
    const hasCalculation = Boolean(row.calculation_prompt || row.calculation_sql);
    return `
      ${sectionMarkup}
      <div
        class="productivity-finance-invoice-row"
        data-productivity-finance-invoice-row
        data-row-id="${allocationEscape(row.id)}"
        data-section="${allocationEscape(row.section)}"
        data-service="${allocationEscape(row.service)}"
        data-description="${allocationEscape(row.description)}"
        data-unit="${allocationEscape(row.unit)}"
        data-quantity="${allocationEscape(row.quantity || 0)}"
        data-calculation-prompt="${allocationEscape(row.calculation_prompt || "")}"
        data-calculation-plan="${allocationEscape(productivityFinanceJsonAttribute(row.calculation_plan))}"
        data-calculation-sql="${allocationEscape(row.calculation_sql || "")}"
        data-collar="${allocationEscape(row.collar_type || "")}"
        data-vas-rate-type="${allocationEscape(row.vas_rate_type || "")}"
      >
        <div class="productivity-finance-invoice-cell">${allocationEscape(row.service)}</div>
        <div class="productivity-finance-invoice-cell">${allocationEscape(row.description)}</div>
        <div class="productivity-finance-invoice-cell">${allocationEscape(row.unit)}</div>
        <label class="productivity-finance-invoice-price">
          <span class="sr-only">${allocationEscape(row.service || row.description || row.id)}</span>
          <input
            data-productivity-finance-row-price
            ${vasAttrs}
            type="number"
            min="0"
            max="${allocationEscape(settings.max_amount)}"
            step="0.001"
            value="${allocationEscape(row.price || 0)}"
            ${disabled}
          />
        </label>
        <div class="productivity-finance-invoice-cell is-number" data-productivity-finance-row-quantity>
          ${allocationEscape(Number(row.quantity || 0).toLocaleString("sv-SE", { maximumFractionDigits: 2 }))}
        </div>
        <div class="productivity-finance-invoice-cell">
          <button
            type="button"
            class="ghost productivity-finance-calculation-button${hasCalculation ? " has-calculation" : ""}"
            data-productivity-finance-calculation
            ${disabled}
          >
            Uträkning
          </button>
        </div>
      </div>
    `;
  }).join("");
}

function productivityFinanceStartedMonthOptions() {
  const now = new Date();
  const monthNames = [
    "Januari",
    "Februari",
    "Mars",
    "April",
    "Maj",
    "Juni",
    "Juli",
    "Augusti",
    "September",
    "Oktober",
    "November",
    "December",
  ];
  const currentMonth = now.getMonth() + 1;
  return monthNames.slice(0, currentMonth).map((label, index) => ({ value: index + 1, label }));
}

function updateProductivityFinanceRowCalculation(row, result, prompt) {
  row.dataset.quantity = String(result.quantity || 0);
  row.dataset.calculationPrompt = prompt;
  row.dataset.calculationPlan = productivityFinanceJsonAttribute(result.plan);
  row.dataset.calculationSql = String(result.calculation_sql || "");
  const quantityCell = row.querySelector("[data-productivity-finance-row-quantity]");
  if (quantityCell) {
    quantityCell.textContent = Number(result.quantity || 0).toLocaleString("sv-SE", { maximumFractionDigits: 2 });
  }
  row.querySelector("[data-productivity-finance-calculation]")?.classList.add("has-calculation");
}

function closeProductivityFinanceCalculationDialog(backdrop) {
  backdrop?.remove();
}

function openProductivityFinanceCalculationDialog(row) {
  if (!row) return;
  const form = row.closest("[data-productivity-finance-settings-form]");
  const companyRow = row.closest("[data-productivity-finance-company-row]");
  const companyCode = normalizeProductivityFinanceCompanyCode(companyRow?.dataset.companyCode);
  const rowLabel = [
    row.dataset.service,
    row.dataset.description,
    row.dataset.unit,
  ].filter(Boolean).join(" | ");
  const months = productivityFinanceStartedMonthOptions();
  const initialPrompt = row.dataset.calculationPrompt || "";
  let lastResult = row.dataset.calculationPlan
    ? {
        quantity: normalizeProductivityFinanceAmount(row.dataset.quantity || 0, 0, 0, 1000000000),
        plan: productivityFinanceParseJson(row.dataset.calculationPlan),
        calculation_sql: row.dataset.calculationSql || "",
      }
    : null;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal productivity-finance-calculation-modal" role="dialog" aria-modal="true">
      <h2>Uträkning</h2>
      <p class="allocation-muted">${allocationEscape(companyCode)} · ${allocationEscape(rowLabel)}</p>
      <label>
        <span>Uträkning</span>
        <textarea data-productivity-finance-calculation-prompt rows="4">${allocationEscape(initialPrompt)}</textarea>
      </label>
      <div class="productivity-finance-calculation-test-row">
        <label>
          <span>Testa månad:</span>
          <select data-productivity-finance-calculation-month>
            ${months.map((month) => `<option value="${month.value}" ${month.value === months[months.length - 1]?.value ? "selected" : ""}>${allocationEscape(month.label)}</option>`).join("")}
          </select>
        </label>
        <button type="button" class="secondary" data-productivity-finance-calculation-test>Testa</button>
      </div>
      <div class="productivity-finance-calculation-result" data-productivity-finance-calculation-result>
        ${lastResult ? `ST / Antal: ${allocationEscape(Number(lastResult.quantity || 0).toLocaleString("sv-SE", { maximumFractionDigits: 2 }))}` : ""}
      </div>
      <label>
        <span>SQL/query</span>
        <textarea data-productivity-finance-calculation-sql rows="3" readonly>${allocationEscape(lastResult?.calculation_sql || row.dataset.calculationSql || "")}</textarea>
      </label>
      <div class="actions">
        <button type="button" class="secondary" data-productivity-finance-calculation-cancel>Avbryt</button>
        <button type="button" class="primary" data-productivity-finance-calculation-save ${lastResult ? "" : "disabled"}>Spara</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);
  const promptInput = backdrop.querySelector("[data-productivity-finance-calculation-prompt]");
  const monthSelect = backdrop.querySelector("[data-productivity-finance-calculation-month]");
  const resultBox = backdrop.querySelector("[data-productivity-finance-calculation-result]");
  const sqlBox = backdrop.querySelector("[data-productivity-finance-calculation-sql]");
  const saveButton = backdrop.querySelector("[data-productivity-finance-calculation-save]");
  promptInput?.focus();
  promptInput?.addEventListener("input", () => {
    lastResult = null;
    if (saveButton) saveButton.disabled = true;
  });
  backdrop.querySelector("[data-productivity-finance-calculation-cancel]")?.addEventListener("click", () => closeProductivityFinanceCalculationDialog(backdrop));
  backdrop.querySelector("[data-productivity-finance-calculation-test]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const prompt = String(promptInput?.value || "").trim();
    const month = Number(monthSelect?.value || 0);
    if (!prompt) {
      showToast("Skriv uträkningen först.", "warn", 3500);
      return;
    }
    button.disabled = true;
    if (resultBox) resultBox.textContent = "Testar...";
    try {
      const path = allocationScopedUrl(`${PRODUCTIVITY_FINANCE_SETTINGS_API}/calculation/test`, { fallbackToUser: true, includeAreaFocus: true });
      const requestBody = { prompt, month, company_code: companyCode };
      const response = window.api?.post
        ? await window.api.post(path, requestBody)
        : await allocationJson(path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestBody),
          });
      lastResult = response;
      if (resultBox) {
        resultBox.textContent = `ST / Antal: ${Number(response.quantity || 0).toLocaleString("sv-SE", { maximumFractionDigits: 2 })}`;
      }
      if (sqlBox) sqlBox.value = response.calculation_sql || "";
      if (saveButton) saveButton.disabled = false;
    } catch (error) {
      lastResult = null;
      if (resultBox) resultBox.textContent = error?.message || "Kunde inte testa uträkningen.";
      showToast(error?.message || "Kunde inte testa uträkningen.", "error", 7000);
      if (saveButton) saveButton.disabled = true;
    } finally {
      button.disabled = false;
    }
  });
  saveButton?.addEventListener("click", () => {
    const prompt = String(promptInput?.value || "").trim();
    if (!lastResult || !prompt) return;
    updateProductivityFinanceRowCalculation(row, lastResult, prompt);
    closeProductivityFinanceCalculationDialog(backdrop);
    void saveProductivityFinanceSettings(form);
  });
}

function renderProductivityFinanceSettingsPanel(panel = document.getElementById("allocation-settings-panel")) {
  if (!panel) return;
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
                  <div class="productivity-finance-invoice-cell is-header">Uträkning</div>
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
  panel.querySelectorAll("[data-productivity-finance-calculation]").forEach((button) => {
    button.addEventListener("click", () => openProductivityFinanceCalculationDialog(button.closest("[data-productivity-finance-invoice-row]")));
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


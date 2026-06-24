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

function normalizeProductivityFinanceProcessKey(value) {
  return String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9_ -]/g, "")
    .slice(0, 120);
}

function normalizeProductivityFinanceProcessOptions(options) {
  const byKey = new Map();
  (Array.isArray(options) ? options : []).forEach((option) => {
    const value = String(option?.value || option?.label || "").trim();
    const key = normalizeProductivityFinanceProcessKey(value);
    if (!key || value.includes(":")) return;
    if (!byKey.has(key)) byKey.set(key, { value: key, label: String(option?.label || value).trim() || key });
  });
  return Array.from(byKey.values()).sort((a, b) => a.label.localeCompare(b.label, "sv"));
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
      linked_process_key: normalizeProductivityFinanceProcessKey(item.linked_process_key),
      linked_process_label: String(item.linked_process_label || "").trim().slice(0, 160),
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
        linked_process_key: normalizeProductivityFinanceProcessKey(invoiceRow.dataset.linkedProcessKey || ""),
        linked_process_label: String(invoiceRow.dataset.linkedProcessLabel || "").trim(),
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

function productivityFinanceProcessCheckSummaryCards(result) {
  const summary = result?.summary || {};
  const cards = [
    ["Intäktsrader", summary.revenue_rows],
    ["Matchade", summary.matched_revenue_rows],
    ["Varningar", summary.warning_revenue_rows],
    ["Fel", summary.error_revenue_rows],
    ["Saknas i KPI", summary.missing_in_kpi],
    ["Saknas i intäkt", summary.missing_in_revenue],
    ["Dubbel KPI", summary.duplicate_kpi],
    ["Dubbel intäkt", summary.duplicate_revenue],
  ];
  return cards.map(([label, value]) => `
    <div class="productivity-finance-process-check-card">
      <span>${allocationEscape(label)}</span>
      <strong>${allocationEscape(Number(value || 0).toLocaleString("sv-SE"))}</strong>
    </div>
  `).join("");
}

function productivityFinanceProcessCheckDiagnostics(items) {
  if (!Array.isArray(items) || !items.length) return "";
  return `
    <div class="productivity-finance-process-check-diagnostics">
      ${items.map((item) => {
        const values = item?.values && typeof item.values === "object" ? item.values : {};
        const text = Object.entries(values)
          .map(([key, value]) => `${key}: ${value}`)
          .join(", ");
        return `<span>${allocationEscape(item.count || 0)} st${text ? ` · ${allocationEscape(text)}` : ""}</span>`;
      }).join("")}
    </div>
  `;
}

function productivityFinanceProcessCheckRuleGaps(items) {
  if (!Array.isArray(items) || !items.length) return "";
  return `
    <div class="productivity-finance-process-check-diagnostics">
      ${items.map((item) => {
        const process = item.process || item.process_key || "Process";
        const field = item.field || "Villkor";
        const expected = item.expected || "";
        const actual = item.actual || "";
        return `<span>${allocationEscape(item.count || 0)} st · ${allocationEscape(process)} · ${allocationEscape(field)}: väntat ${allocationEscape(expected)}, hittat ${allocationEscape(actual)}</span>`;
      }).join("")}
    </div>
  `;
}

function productivityFinanceProcessCheckProcessPayload(process) {
  const label = String(process?.process || process?.process_key || "").trim();
  const key = normalizeProductivityFinanceProcessKey(process?.process_key || label);
  return { key, label: label || key };
}

function productivityFinanceProcessCheckProcessAction(process, allowLink = false) {
  const item = productivityFinanceProcessCheckProcessPayload(process);
  if (!item.label) return "";
  if (!allowLink || !item.key) return `<span>${allocationEscape(item.label)}</span>`;
  return `
    <button
      type="button"
      class="productivity-finance-process-check-link-chip"
      data-productivity-finance-check-link-process="${allocationEscape(item.key)}"
      data-process-label="${allocationEscape(item.label)}"
    >${allocationEscape(item.label)}</button>
  `;
}

function productivityFinanceProcessCheckProcessList(processes, status, allowLink = false) {
  if (status === "error") return '<span class="allocation-muted">Kontrollen kunde inte köras</span>';
  if (!Array.isArray(processes) || !processes.length) return '<span class="allocation-muted">Ingen tydlig process</span>';
  return processes.map((process) => productivityFinanceProcessCheckProcessAction(process, allowLink)).join("");
}

function productivityFinanceProcessCheckSameView(processes) {
  if (!Array.isArray(processes) || !processes.length) return "";
  return `
    <div class="productivity-finance-process-check-same-view">
      <strong>Samma vy i KPI-processer</strong>
      <div class="productivity-finance-process-check-diagnostics">
        ${processes.slice(0, 10).map((process) => {
          const name = process.process || process.process_key || "Process";
          const revenueCount = Number(process.revenue_row_count || 0).toLocaleString("sv-SE");
          const processCount = Number(process.process_row_count || 0).toLocaleString("sv-SE");
          const overlapCount = Number(process.overlap_count || 0).toLocaleString("sv-SE");
          const difference = Number(process.count_difference || 0);
          const differenceText = `${difference > 0 ? "+" : ""}${difference.toLocaleString("sv-SE")}`;
          return `<span>${allocationEscape(name)} · intäkt ${allocationEscape(revenueCount)} · process ${allocationEscape(processCount)} · överlapp ${allocationEscape(overlapCount)} · diff ${allocationEscape(differenceText)}</span>`;
        }).join("")}
      </div>
    </div>
  `;
}

function productivityFinanceProcessCheckComparisonUnit(item) {
  const label = String(item?.comparison_key_label || item?.combined_process_coverage?.key_label || "").trim();
  return label && label !== "rad" ? `unika ${label}` : "rader";
}

function productivityFinanceProcessCheckCombinedCoverage(item, allowLink = false) {
  const coverage = item?.combined_process_coverage || null;
  const processes = Array.isArray(coverage?.processes) ? coverage.processes : [];
  if (!coverage || !processes.length) return "";
  const keyLabel = coverage.key_label || item?.comparison_key_label || "rad";
  const revenueCount = Number(coverage.revenue_key_count || 0).toLocaleString("sv-SE");
  const coveredCount = Number(coverage.covered_key_count || 0).toLocaleString("sv-SE");
  const missingCount = Number(coverage.missing_key_count || 0).toLocaleString("sv-SE");
  const extraCount = Number(coverage.extra_key_count || 0).toLocaleString("sv-SE");
  const coveragePct = Number(coverage.coverage_pct || 0).toLocaleString("sv-SE", { maximumFractionDigits: 1 });
  return `
    <div class="productivity-finance-process-check-combination">
      <strong>Processkombination</strong>
      <p>${allocationEscape(coveredCount)} av ${allocationEscape(revenueCount)} ${allocationEscape(keyLabel)} tacks (${allocationEscape(coveragePct)}%). Saknas ${allocationEscape(missingCount)}, extra ${allocationEscape(extraCount)}.</p>
      <div class="productivity-finance-process-check-processes">
        ${processes.map((process) => productivityFinanceProcessCheckProcessAction(process, allowLink)).join("")}
      </div>
    </div>
  `;
}

function productivityFinanceProcessCheckSourceMessages(result) {
  const sources = Array.isArray(result?.sources) ? result.sources : [];
  const sourceMessages = sources
    .filter((source) => ["error", "skipped"].includes(String(source?.status || "")))
    .map((source) => {
      const label = source.view_label || source.view || source.source || "Källa";
      const message = source.message || "Källan kunde inte hämtas.";
      return {
        status: source.status === "error" ? "error" : "warning",
        label: String(label),
        text: `${label}: ${message}`,
      };
    });
  const warningMessages = Array.isArray(result?.warnings)
    ? result.warnings
        .filter((text) => !sourceMessages.some((source) => String(text || "").includes(source.label)))
        .map((text) => ({ status: "warning", text }))
    : [];
  const messages = [...sourceMessages, ...warningMessages];
  if (!messages.length) return "";
  return `
    <div class="productivity-finance-process-check-source-messages">
      ${messages.slice(0, 6).map((item) => `
        <p class="allocation-status ${allocationEscape(item.status)}">${allocationEscape(item.text)}</p>
      `).join("")}
    </div>
  `;
}

function renderProductivityFinanceProcessCheckResult(result, options = {}) {
  const allowProcessLink = Boolean(options.allowProcessLink);
  if (allocationState.productivityFinanceProcessCheckLoading) {
    return `<section class="productivity-finance-process-check-result"><p class="allocation-muted">Kontrollerar intäkter och processer...</p></section>`;
  }
  if (allocationState.productivityFinanceProcessCheckError) {
    return `<section class="productivity-finance-process-check-result"><p class="allocation-status error">${allocationEscape(allocationState.productivityFinanceProcessCheckError)}</p></section>`;
  }
  if (!result) return "";
  const revenueChecks = Array.isArray(result.revenue_checks) ? result.revenue_checks : [];
  const processChecks = Array.isArray(result.process_checks) ? result.process_checks : [];
  const duplicateKpi = Array.isArray(result.duplicates?.kpi) ? result.duplicates.kpi : [];
  const duplicateRevenue = Array.isArray(result.duplicates?.revenue) ? result.duplicates.revenue : [];
  const missingRevenue = processChecks.filter((item) => Number(item.missing_in_revenue_count || 0) > 0).slice(0, 8);
  const targetCheck = Boolean(result.target_row_id);
  const targetLabel = targetCheck && revenueChecks[0]
    ? `${revenueChecks[0].company || ""} · ${revenueChecks[0].label || revenueChecks[0].row_id || ""}`
    : "";
  return `
    <section class="productivity-finance-process-check-result">
      <div class="productivity-finance-process-check-head">
        <div>
          <h3>${targetCheck ? "Kontrollresultat för uträkning" : "Kontrollresultat"}</h3>
          <span class="allocation-muted">${targetLabel ? `${allocationEscape(targetLabel)} · ` : ""}${allocationEscape(result.period?.start_date || "")} - ${allocationEscape(result.period?.end_date || "")}</span>
        </div>
      </div>
      <div class="productivity-finance-process-check-cards">
        ${productivityFinanceProcessCheckSummaryCards(result)}
      </div>
      ${productivityFinanceProcessCheckSourceMessages(result)}
      <div class="productivity-finance-process-check-list">
        ${revenueChecks.slice(0, 12).map((item) => `
          <article class="productivity-finance-process-check-row ${allocationEscape(item.status || "info")}">
            <div>
              <strong>${allocationEscape(item.company || "")} · ${allocationEscape(item.label || item.row_id || "")}</strong>
              <span>${allocationEscape(Number(item.quantity || 0).toLocaleString("sv-SE", { maximumFractionDigits: 2 }))} st · ${allocationEscape(Number(item.revenue || 0).toLocaleString("sv-SE", { maximumFractionDigits: 2 }))} SEK</span>
            </div>
            <div class="productivity-finance-process-check-processes">
              ${productivityFinanceProcessCheckProcessList(item.matched_processes, item.status, allowProcessLink)}
            </div>
            ${productivityFinanceProcessCheckCombinedCoverage(item, allowProcessLink)}
            ${productivityFinanceProcessCheckSameView(item.same_view_processes)}
            ${(item.messages || []).map((message) => `<p>${allocationEscape(message)}</p>`).join("")}
            ${Boolean(Number(item.missing_in_kpi_count || 0) > 0) ? `
              <p>${allocationEscape(item.missing_in_kpi_count)} ${allocationEscape(productivityFinanceProcessCheckComparisonUnit(item))} finns i intakten men saknas i KPI-processerna.</p>
              ${productivityFinanceProcessCheckRuleGaps(item.rule_gaps)}
              ${productivityFinanceProcessCheckDiagnostics(item.missing_in_kpi)}
            ` : ""}
            ${Boolean(Number(item.process_extra_count || 0) > 0) ? `
              <p>${allocationEscape(item.process_extra_count)} extra ${allocationEscape(productivityFinanceProcessCheckComparisonUnit(item))} samlas av matchande processer, men ligger utanfor den har intaktsraden.</p>
              ${productivityFinanceProcessCheckDiagnostics(item.process_extra)}
            ` : ""}
            ${false && Number(item.missing_in_kpi_count || 0) > 0 ? `
              <p>${allocationEscape(item.missing_in_kpi_count)} ${allocationEscape(productivityFinanceProcessCheckComparisonUnit(item))} finns i intÃ¤kten men saknas i KPI-processerna.</p>
              ${productivityFinanceProcessCheckRuleGaps(item.rule_gaps)}
              ${productivityFinanceProcessCheckDiagnostics(item.missing_in_kpi)}
            ` : ""}
            ${false && Number(item.process_extra_count || 0) > 0 ? `
              <p>${allocationEscape(item.process_extra_count)} extra ${allocationEscape(productivityFinanceProcessCheckComparisonUnit(item))} samlas av matchande processer, men ligger utanfÃ¶r den hÃ¤r intÃ¤ktsraden.</p>
              ${productivityFinanceProcessCheckDiagnostics(item.process_extra)}
            ` : ""}
            ${false && Number(item.missing_in_kpi_count || 0) > 0 ? `
              <p>${allocationEscape(item.missing_in_kpi_count)} rader finns i intäkten men saknas i KPI-processerna.</p>
              ${productivityFinanceProcessCheckRuleGaps(item.rule_gaps)}
              ${productivityFinanceProcessCheckDiagnostics(item.missing_in_kpi)}
            ` : ""}
            ${false && Number(item.process_extra_count || 0) > 0 ? `
              <p>${allocationEscape(item.process_extra_count)} KPI-rader räknas också av matchande processer, men ligger utanför den här intäktsraden.</p>
              ${productivityFinanceProcessCheckDiagnostics(item.process_extra)}
            ` : ""}
          </article>
        `).join("") || `<p class="allocation-muted">Inga intäktsrader med sparad uträkning hittades.</p>`}
      </div>
      ${missingRevenue.length ? `
        <div class="productivity-finance-process-check-list">
          <h3>KPI-processer som saknar intäkt</h3>
          ${missingRevenue.map((item) => `
            <article class="productivity-finance-process-check-row warning">
              <strong>${allocationEscape(item.process || item.process_key || "")}</strong>
              <p>${allocationEscape(item.missing_in_revenue_count)} KPI-rader verkar sakna intäktsrad.</p>
              ${productivityFinanceProcessCheckDiagnostics(item.missing_in_revenue)}
            </article>
          `).join("")}
        </div>
      ` : ""}
      ${(duplicateKpi.length || duplicateRevenue.length) ? `
        <div class="productivity-finance-process-check-list">
          <h3>Möjlig dubbelräkning</h3>
          ${duplicateKpi.slice(0, 8).map((item) => `
            <article class="productivity-finance-process-check-row warning">
              <strong>KPI · ${allocationEscape(item.source || "")}</strong>
              <p>${allocationEscape((item.processes || []).map((process) => process.process).join(", "))}</p>
              ${productivityFinanceProcessCheckDiagnostics(item.rows)}
            </article>
          `).join("")}
          ${duplicateRevenue.slice(0, 8).map((item) => `
            <article class="productivity-finance-process-check-row warning">
              <strong>Intäkt · ${allocationEscape(item.source || "")}</strong>
              <p>${allocationEscape((item.revenue_rows || []).join(", "))}</p>
              ${productivityFinanceProcessCheckDiagnostics(item.rows)}
            </article>
          `).join("")}
        </div>
      ` : ""}
    </section>
  `;
}

async function runProductivityFinanceProcessCheck(form, invoiceRow = null) {
  if (!form || allocationState.productivityFinanceProcessCheckLoading) return;
  const month = Number(form.querySelector("[data-productivity-finance-process-check-dialog-month]")?.value || 0);
  const rowCompany = invoiceRow
    ? normalizeProductivityFinanceCompanyCode(invoiceRow.closest("[data-productivity-finance-company-row]")?.dataset.companyCode)
    : "";
  const companyCode = rowCompany || normalizeProductivityFinanceCompanyCode(
    form.querySelector("[data-productivity-finance-process-check-dialog-company]")?.value || ""
  );
  const rowId = invoiceRow ? String(invoiceRow.dataset.rowId || "").trim() : "";
  if (!Number.isInteger(month) || month < 1 || month > 12) {
    showToast("Välj en månad att kontrollera.", "warn", 3500);
    return;
  }
  allocationState.productivityFinanceProcessCheckLoading = true;
  allocationState.productivityFinanceProcessCheckRowId = rowId;
  allocationState.productivityFinanceProcessCheckError = "";
  renderProductivityFinanceSettingsPanel();
  try {
    const path = allocationScopedUrl(`${PRODUCTIVITY_FINANCE_SETTINGS_API}/process-check`, { fallbackToUser: true, includeAreaFocus: true });
    const body = { month, company_code: companyCode || null, row_id: rowId || null };
    const result = window.api?.post
      ? await window.api.post(path, body)
      : await allocationJson(path, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
    allocationState.productivityFinanceProcessCheck = result;
    const errorCount = Number(result?.summary?.error_revenue_rows || 0);
    const reviewCount = Number(result?.summary?.warning_revenue_rows || 0)
      + Number(result?.summary?.missing_in_revenue || 0)
      + Number(result?.summary?.duplicate_kpi || 0)
      + Number(result?.summary?.duplicate_revenue || 0);
    if (errorCount) {
      showToast(`Kontrollen kunde inte läsa ${errorCount} intäktsrader.`, "error", 7000);
    } else {
      showToast(reviewCount ? `Kontrollen hittade ${reviewCount} saker att granska.` : "Kontrollen hittade inga varningar.", reviewCount ? "warn" : "success", 5000);
    }
  } catch (error) {
    allocationState.productivityFinanceProcessCheck = null;
    allocationState.productivityFinanceProcessCheckError = error?.message || "Kunde inte kontrollera intäkter/processer.";
    showToast(allocationState.productivityFinanceProcessCheckError, "error", 7000);
  } finally {
    allocationState.productivityFinanceProcessCheckLoading = false;
    allocationState.productivityFinanceProcessCheckRowId = "";
    renderProductivityFinanceSettingsPanel();
  }
}

async function loadProductivityFinanceProcessOptions() {
  if (allocationState.productivityFinanceProcessOptionsLoaded) return allocationState.productivityFinanceProcessOptions;
  const path = allocationScopedUrl("/api/activities/kpi-process-options", { fallbackToUser: true, includeAreaFocus: true });
  const payload = window.api?.get
    ? await window.api.get(path, { skipCache: true })
    : await allocationJson(path, { skipCache: true });
  allocationState.productivityFinanceProcessOptions = normalizeProductivityFinanceProcessOptions(payload);
  allocationState.productivityFinanceProcessOptionsLoaded = true;
  return allocationState.productivityFinanceProcessOptions;
}

function closeProductivityFinanceContextMenu() {
  allocationState.productivityFinanceContextMenu?.remove();
  allocationState.productivityFinanceContextMenu = null;
}

function productivityFinanceInvoiceRowLabel(row) {
  return [
    row?.dataset?.service,
    row?.dataset?.description,
    row?.dataset?.unit,
  ].filter(Boolean).join(" | ") || row?.dataset?.rowId || "Intäktsrad";
}

function positionProductivityFinanceContextMenu(menu, x, y) {
  const rect = menu.getBoundingClientRect();
  const left = Math.min(Math.max(8, x), Math.max(8, window.innerWidth - rect.width - 8));
  const top = Math.min(Math.max(8, y), Math.max(8, window.innerHeight - rect.height - 8));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

function openProductivityFinanceContextMenu(event, row) {
  event.preventDefault();
  if (!row) return;
  closeProductivityFinanceContextMenu();
  const form = row.closest("[data-productivity-finance-settings-form]");
  const canEdit = canEditProductivityFinanceSettings()
    && !allocationState.productivityFinanceSettingsSaving
    && !allocationState.productivityFinanceSettingsLoading;
  const canCheckCalculation = Boolean(productivityFinanceParseJson(row.dataset.calculationPlan))
    && !row.dataset.collar
    && !row.dataset.vasRateType
    && !allocationState.productivityFinanceProcessCheckLoading;
  const menu = document.createElement("div");
  menu.className = "productivity-finance-row-context-menu";
  menu.setAttribute("role", "menu");
  menu.innerHTML = `
    <button type="button" role="menuitem" data-action="calculation" ${canEdit ? "" : "disabled"}>Uträkning</button>
    <button type="button" role="menuitem" data-action="check" ${canCheckCalculation ? "" : "disabled"}>Kontroll</button>
    <button type="button" role="menuitem" data-action="link-process" ${canEdit ? "" : "disabled"}>Koppla process</button>
  `;
  (row.closest(".allocation-productivity-finance-settings-panel") || document.body).appendChild(menu);
  allocationState.productivityFinanceContextMenu = menu;
  positionProductivityFinanceContextMenu(menu, event.clientX, event.clientY);
  menu.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      const action = button.dataset.action;
      closeProductivityFinanceContextMenu();
      if (action === "calculation") openProductivityFinanceCalculationDialog(row);
      if (action === "check") void openProductivityFinanceProcessCheckDialog(form, row);
      if (action === "link-process") void openProductivityFinanceProcessLinkDialog(row);
    });
  });
  setTimeout(() => {
    document.addEventListener("click", closeProductivityFinanceContextMenu, { once: true });
    document.addEventListener("keydown", (keyEvent) => {
      if (keyEvent.key === "Escape") closeProductivityFinanceContextMenu();
    }, { once: true });
  }, 0);
}

function updateProductivityFinanceRowProcessLink(row, processKey, processLabel) {
  const key = normalizeProductivityFinanceProcessKey(processKey);
  const label = String(processLabel || key).trim();
  row.dataset.linkedProcessKey = key;
  row.dataset.linkedProcessLabel = key ? label : "";
  const badge = row.querySelector("[data-productivity-finance-linked-process]");
  if (badge) {
    badge.textContent = key ? `Process: ${label}` : "";
    badge.hidden = !key;
  }
}

async function saveProductivityFinanceRowProcessLink(row, processKey, processLabel) {
  if (!row) return;
  const form = row.closest("[data-productivity-finance-settings-form]");
  updateProductivityFinanceRowProcessLink(row, processKey, processLabel);
  await saveProductivityFinanceSettings(form);
}

function renderProductivityFinanceProcessLinkOptions(options, selectedKey) {
  return `
    <label class="productivity-finance-process-link-option">
      <input type="radio" name="productivity-finance-process-link" value="" data-label="" ${selectedKey ? "" : "checked"}>
      <span>Ingen koppling</span>
    </label>
    ${options.map((option) => `
      <label class="productivity-finance-process-link-option" data-process-search="${allocationEscape(`${option.label} ${option.value}`.toLowerCase())}">
        <input
          type="radio"
          name="productivity-finance-process-link"
          value="${allocationEscape(option.value)}"
          data-label="${allocationEscape(option.label)}"
          ${option.value === selectedKey ? "checked" : ""}
        >
        <span>${allocationEscape(option.label)}</span>
      </label>
    `).join("")}
  `;
}

function productivityFinanceProcessOptionForValue(options, value) {
  const text = String(value || "").trim();
  const key = normalizeProductivityFinanceProcessKey(text);
  return (options || []).find((option) => (
    normalizeProductivityFinanceProcessKey(option.value) === key
    || normalizeProductivityFinanceProcessKey(option.label) === key
  )) || null;
}

function renderProductivityFinanceProcessDatalist(options, datalistId) {
  return `
    <datalist id="${allocationEscape(datalistId)}">
      ${(options || []).map((option) => `<option value="${allocationEscape(option.label)}">${allocationEscape(option.value)}</option>`).join("")}
    </datalist>
  `;
}

function productivityFinanceProcessInfoFromResult(result, processKey) {
  const key = normalizeProductivityFinanceProcessKey(processKey);
  if (!key || !result) return null;
  const checks = Array.isArray(result.revenue_checks) ? result.revenue_checks : [];
  const candidates = [];
  checks.forEach((check) => {
    candidates.push(...(Array.isArray(check.same_view_processes) ? check.same_view_processes : []));
    candidates.push(...(Array.isArray(check.matched_processes) ? check.matched_processes : []));
  });
  return candidates.find((process) => normalizeProductivityFinanceProcessKey(process.process_key || process.process) === key) || null;
}

function renderProductivityFinanceProcessCheckSqlDetails(row, result, processKey) {
  const check = Array.isArray(result?.revenue_checks) && result.revenue_checks.length ? result.revenue_checks[0] : null;
  const selectedKey = normalizeProductivityFinanceProcessKey(processKey);
  const process = productivityFinanceProcessInfoFromResult(result, selectedKey);
  const prompt = check?.calculation_prompt || row?.dataset?.calculationPrompt || "";
  const revenueSql = check?.calculation_sql || check?.saved_calculation_sql || row?.dataset?.calculationSql || "";
  const processSql = process?.process_sql || "";
  const processFallback = selectedKey
    ? "Kör kontrollen för vald månad för att visa process-SQL."
    : "Välj en process för att visa process-SQL.";
  return `
    <section class="productivity-finance-process-check-sql-panel">
      <h3>Underlag</h3>
      <label>
        <span>Prompt</span>
        <textarea rows="3" readonly>${allocationEscape(prompt)}</textarea>
      </label>
      <label>
        <span>Intäkts-SQL</span>
        <textarea rows="4" readonly>${allocationEscape(revenueSql)}</textarea>
      </label>
      <label>
        <span>Process-SQL</span>
        <textarea rows="5" readonly>${allocationEscape(processSql || processFallback)}</textarea>
      </label>
    </section>
  `;
}

function updateProductivityFinanceProcessCheckSqlDetails(backdrop, row, result, options) {
  const target = backdrop?.querySelector("[data-productivity-finance-process-check-sql-details]");
  if (!target) return;
  const input = backdrop.querySelector("[data-productivity-finance-process-combobox]");
  const option = productivityFinanceProcessOptionForValue(options, input?.value || "");
  const key = option?.value || normalizeProductivityFinanceProcessKey(input?.value || "");
  target.innerHTML = renderProductivityFinanceProcessCheckSqlDetails(row, result, key);
}

async function openProductivityFinanceProcessLinkDialog(row) {
  if (!row) return;
  let options = [];
  try {
    options = await loadProductivityFinanceProcessOptions();
  } catch (error) {
    showToast(error?.message || "Kunde inte läsa KPI-processer.", "error", 7000);
    return;
  }
  const selectedKey = normalizeProductivityFinanceProcessKey(row.dataset.linkedProcessKey);
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal productivity-finance-process-link-modal" role="dialog" aria-modal="true">
      <h2>Koppla process</h2>
      <p class="allocation-muted">${allocationEscape(productivityFinanceInvoiceRowLabel(row))}</p>
      <label>
        <span>Sök</span>
        <input type="search" data-productivity-finance-process-search>
      </label>
      <div class="productivity-finance-process-link-list" data-productivity-finance-process-link-list>
        ${options.length
          ? renderProductivityFinanceProcessLinkOptions(options, selectedKey)
          : `<p class="allocation-muted">Inga KPI-processer hittades.</p>`}
      </div>
      <div class="actions">
        <button type="button" class="secondary" data-productivity-finance-process-link-cancel>Avbryt</button>
        <button type="button" class="primary" data-productivity-finance-process-link-save ${options.length || selectedKey ? "" : "disabled"}>Spara</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);
  const search = backdrop.querySelector("[data-productivity-finance-process-search]");
  search?.focus();
  search?.addEventListener("input", () => {
    const query = String(search.value || "").trim().toLowerCase();
    backdrop.querySelectorAll("[data-process-search]").forEach((option) => {
      option.hidden = query && !String(option.dataset.processSearch || "").includes(query);
    });
  });
  backdrop.querySelector("[data-productivity-finance-process-link-cancel]")?.addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("[data-productivity-finance-process-link-save]")?.addEventListener("click", () => {
    const selected = backdrop.querySelector('input[name="productivity-finance-process-link"]:checked');
    const processKey = selected?.value || "";
    const processLabel = selected?.dataset.label || processKey;
    backdrop.remove();
    void saveProductivityFinanceRowProcessLink(row, processKey, processLabel);
  });
}

async function requestProductivityFinanceProcessCheck({ month, companyCode = "", rowId = "" }) {
  if (!Number.isInteger(month) || month < 1 || month > 12) {
    throw new Error("Välj en månad att kontrollera.");
  }
  const path = allocationScopedUrl(`${PRODUCTIVITY_FINANCE_SETTINGS_API}/process-check`, { fallbackToUser: true, includeAreaFocus: true });
  const body = {
    month,
    company_code: normalizeProductivityFinanceCompanyCode(companyCode) || null,
    row_id: String(rowId || "").trim() || null,
  };
  return window.api?.post
    ? window.api.post(path, body)
    : allocationJson(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
}

function productivityFinanceProcessCheckCompanyOptions(form, selectedCode = "") {
  const selected = normalizeProductivityFinanceCompanyCode(selectedCode);
  const codes = Array.from(form?.querySelectorAll("[data-productivity-finance-company-row]") || [])
    .map((row) => normalizeProductivityFinanceCompanyCode(row.dataset.companyCode))
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right, "sv"));
  return `
    <option value="">Alla bolag</option>
    ${codes.map((code) => `<option value="${allocationEscape(code)}" ${code === selected ? "selected" : ""}>${allocationEscape(code)}</option>`).join("")}
  `;
}

function productivityFinanceProcessCheckLinkedLabel(row) {
  const key = normalizeProductivityFinanceProcessKey(row?.dataset?.linkedProcessKey || "");
  const label = String(row?.dataset?.linkedProcessLabel || key || "").trim();
  return key ? label : "Ingen koppling";
}

function updateProductivityFinanceProcessCheckLinkedLabel(backdrop, row) {
  const target = backdrop?.querySelector("[data-productivity-finance-process-check-linked-label]");
  if (target) target.textContent = productivityFinanceProcessCheckLinkedLabel(row);
}

function syncProductivityFinanceProcessCheckSelection(backdrop, processKey, processLabel = "") {
  const key = normalizeProductivityFinanceProcessKey(processKey);
  const input = backdrop?.querySelector("[data-productivity-finance-process-combobox]");
  if (input) input.value = key ? String(processLabel || key).trim() : "";
}

async function saveProductivityFinanceProcessCheckDialogLink(backdrop, row, processKey, processLabel) {
  if (!row) return;
  const status = backdrop?.querySelector("[data-productivity-finance-process-check-link-status]");
  const buttons = backdrop?.querySelectorAll("[data-productivity-finance-check-link-process], [data-productivity-finance-process-check-link-save]") || [];
  buttons.forEach((button) => { button.disabled = true; });
  if (status) {
    status.className = "allocation-muted";
    status.textContent = "Sparar koppling...";
  }
  syncProductivityFinanceProcessCheckSelection(backdrop, processKey, processLabel);
  await saveProductivityFinanceRowProcessLink(row, processKey, processLabel);
  updateProductivityFinanceProcessCheckLinkedLabel(backdrop, row);
  if (status) {
    const errorText = allocationState.productivityFinanceSettingsError || "";
    status.className = errorText ? "allocation-status error" : "allocation-status success";
    status.textContent = errorText || "Kopplingen sparades.";
  }
  buttons.forEach((button) => { button.disabled = false; });
}

async function openProductivityFinanceProcessCheckDialog(form, invoiceRow = null) {
  if (!form) return;
  const rowCompany = invoiceRow
    ? normalizeProductivityFinanceCompanyCode(invoiceRow.closest("[data-productivity-finance-company-row]")?.dataset.companyCode)
    : "";
  const rowId = invoiceRow ? String(invoiceRow.dataset.rowId || "").trim() : "";
  const rowLabel = invoiceRow ? productivityFinanceInvoiceRowLabel(invoiceRow) : "";
  const months = productivityFinanceStartedMonthOptions();
  const selectedMonth = months[months.length - 1]?.value || 1;
  const canLinkProcess = Boolean(invoiceRow && canEditProductivityFinanceSettings());
  let processOptions = [];
  let processOptionsError = "";
  if (canLinkProcess) {
    try {
      processOptions = await loadProductivityFinanceProcessOptions();
    } catch (error) {
      processOptionsError = error?.message || "Kunde inte läsa KPI-processer.";
      showToast(processOptionsError, "error", 7000);
    }
  }
  const selectedProcessKey = normalizeProductivityFinanceProcessKey(invoiceRow?.dataset?.linkedProcessKey || "");
  const selectedProcessOption = productivityFinanceProcessOptionForValue(processOptions, selectedProcessKey);
  const selectedProcessText = selectedProcessKey
    ? (selectedProcessOption?.label || invoiceRow?.dataset?.linkedProcessLabel || selectedProcessKey)
    : "";
  const processDatalistId = `productivity-finance-process-options-${Date.now()}`;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal productivity-finance-process-check-modal" role="dialog" aria-modal="true">
      <div class="productivity-finance-process-check-modal-head">
        <div>
          <h2>${invoiceRow ? "Kontroll" : "Kontrollera intäkter/processer"}</h2>
          ${invoiceRow ? `<p class="allocation-muted">${allocationEscape(rowCompany)} · ${allocationEscape(rowLabel)}</p>` : ""}
        </div>
        <div class="productivity-finance-process-check-modal-tools">
          <span data-productivity-finance-process-check-dialog-status></span>
          <button type="button" class="productivity-finance-process-check-x" aria-label="Stäng" title="Stäng" data-productivity-finance-process-check-close>×</button>
        </div>
      </div>
      <div class="productivity-finance-process-check-dialog-controls">
        <label>
          <span>Månad</span>
          <select data-productivity-finance-process-check-dialog-month>
            ${months.map((month) => `<option value="${month.value}" ${month.value === selectedMonth ? "selected" : ""}>${allocationEscape(month.label)}</option>`).join("")}
          </select>
        </label>
        ${invoiceRow ? `
          <label>
            <span>Bolag</span>
            <input type="text" value="${allocationEscape(rowCompany)}" disabled>
          </label>
        ` : `
          <label>
            <span>Bolag</span>
            <select data-productivity-finance-process-check-dialog-company>
              ${productivityFinanceProcessCheckCompanyOptions(form)}
            </select>
          </label>
        `}
        <button type="button" class="primary" data-productivity-finance-process-check-dialog-run>Kontrollera</button>
      </div>
      ${canLinkProcess ? `
        <section class="productivity-finance-process-check-link-panel">
          <div class="productivity-finance-process-check-link-head">
            <h3>Koppla process</h3>
            <span data-productivity-finance-process-check-linked-label>${allocationEscape(productivityFinanceProcessCheckLinkedLabel(invoiceRow))}</span>
          </div>
          <label>
            <span>Process</span>
            <input
              type="text"
              list="${allocationEscape(processDatalistId)}"
              value="${allocationEscape(selectedProcessText)}"
              placeholder="Skriv för att söka..."
              data-productivity-finance-process-combobox
            >
            ${renderProductivityFinanceProcessDatalist(processOptions, processDatalistId)}
          </label>
          ${processOptionsError ? `<p class="allocation-status error">${allocationEscape(processOptionsError)}</p>` : ""}
          <div data-productivity-finance-process-check-sql-details>
            ${renderProductivityFinanceProcessCheckSqlDetails(invoiceRow, null, selectedProcessKey)}
          </div>
          <div class="actions productivity-finance-process-check-link-actions">
            <span data-productivity-finance-process-check-link-status></span>
            <button type="button" class="secondary" data-productivity-finance-process-check-link-save ${processOptions.length || selectedProcessKey ? "" : "disabled"}>Spara koppling</button>
          </div>
        </section>
      ` : ""}
      <div data-productivity-finance-process-check-dialog-result></div>
    </div>
  `;
  document.body.appendChild(backdrop);
  const monthSelect = backdrop.querySelector("[data-productivity-finance-process-check-dialog-month]");
  const companySelect = backdrop.querySelector("[data-productivity-finance-process-check-dialog-company]");
  const resultBox = backdrop.querySelector("[data-productivity-finance-process-check-dialog-result]");
  const statusBox = backdrop.querySelector("[data-productivity-finance-process-check-dialog-status]");
  let latestCheckResult = null;
  backdrop.querySelector("[data-productivity-finance-process-check-close]")?.addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("[data-productivity-finance-process-check-dialog-run]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const month = Number(monthSelect?.value || 0);
    const companyCode = rowCompany || normalizeProductivityFinanceCompanyCode(companySelect?.value || "");
    button.disabled = true;
    if (statusBox) {
      statusBox.className = "allocation-muted";
      statusBox.textContent = "Kontrollerar intäkter och processer...";
    }
    if (resultBox) resultBox.innerHTML = "";
    try {
      const result = await requestProductivityFinanceProcessCheck({ month, companyCode, rowId });
      latestCheckResult = result;
      if (statusBox) statusBox.textContent = "";
      if (resultBox) {
        resultBox.innerHTML = renderProductivityFinanceProcessCheckResult(result, { allowProcessLink: canLinkProcess });
      }
      updateProductivityFinanceProcessCheckSqlDetails(backdrop, invoiceRow, latestCheckResult, processOptions);
      const errorCount = Number(result?.summary?.error_revenue_rows || 0);
      const reviewCount = Number(result?.summary?.warning_revenue_rows || 0)
        + Number(result?.summary?.missing_in_revenue || 0)
        + Number(result?.summary?.duplicate_kpi || 0)
        + Number(result?.summary?.duplicate_revenue || 0);
      if (errorCount) {
        showToast(`Kontrollen kunde inte läsa ${errorCount} intäktsrader.`, "error", 7000);
      } else {
        showToast(reviewCount ? `Kontrollen hittade ${reviewCount} saker att granska.` : "Kontrollen hittade inga varningar.", reviewCount ? "warn" : "success", 5000);
      }
    } catch (error) {
      if (statusBox) {
        statusBox.className = "allocation-status error";
        statusBox.textContent = error?.message || "Kunde inte kontrollera intäkter/processer.";
      }
      showToast(error?.message || "Kunde inte kontrollera intäkter/processer.", "error", 7000);
    } finally {
      button.disabled = false;
    }
  });
  backdrop.querySelector("[data-productivity-finance-process-combobox]")?.addEventListener("input", () => {
    updateProductivityFinanceProcessCheckSqlDetails(backdrop, invoiceRow, latestCheckResult, processOptions);
  });
  backdrop.querySelector("[data-productivity-finance-process-check-link-save]")?.addEventListener("click", () => {
    const input = backdrop.querySelector("[data-productivity-finance-process-combobox]");
    const rawValue = String(input?.value || "").trim();
    if (!rawValue) {
      void saveProductivityFinanceProcessCheckDialogLink(backdrop, invoiceRow, "", "");
      return;
    }
    const option = productivityFinanceProcessOptionForValue(processOptions, rawValue);
    if (!option) {
      const status = backdrop.querySelector("[data-productivity-finance-process-check-link-status]");
      if (status) {
        status.className = "allocation-status error";
        status.textContent = "Välj en process i listan.";
      }
      return;
    }
    void saveProductivityFinanceProcessCheckDialogLink(backdrop, invoiceRow, option.value, option.label);
  });
  resultBox?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-productivity-finance-check-link-process]");
    if (!button || !invoiceRow) return;
    syncProductivityFinanceProcessCheckSelection(backdrop, button.dataset.productivityFinanceCheckLinkProcess || "", button.dataset.processLabel || "");
    updateProductivityFinanceProcessCheckSqlDetails(backdrop, invoiceRow, latestCheckResult, processOptions);
    void saveProductivityFinanceProcessCheckDialogLink(backdrop, invoiceRow, button.dataset.productivityFinanceCheckLinkProcess || "", button.dataset.processLabel || "");
  });
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
    const linkedProcessKey = normalizeProductivityFinanceProcessKey(row.linked_process_key);
    const linkedProcessLabel = String(row.linked_process_label || linkedProcessKey || "").trim();
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
        data-linked-process-key="${allocationEscape(linkedProcessKey)}"
        data-linked-process-label="${allocationEscape(linkedProcessLabel)}"
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
          <span>${allocationEscape(Number(row.quantity || 0).toLocaleString("sv-SE", { maximumFractionDigits: 2 }))}</span>
          <small data-productivity-finance-linked-process ${linkedProcessKey ? "" : "hidden"}>
            ${linkedProcessKey ? `Process: ${allocationEscape(linkedProcessLabel)}` : ""}
          </small>
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
    const valueNode = quantityCell.querySelector("span") || quantityCell;
    valueNode.textContent = Number(result.quantity || 0).toLocaleString("sv-SE", { maximumFractionDigits: 2 });
  }
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
    void openProductivityFinanceProcessCheckDialog(event.currentTarget.closest("[data-productivity-finance-settings-form]"));
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


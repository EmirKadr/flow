// Utdelad ur allocation/settings_view.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter settings_view.js via <script>-tagg.

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

// Utdelad ur allocation/settings_finance.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter settings_finance.js via <script>-tagg.

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

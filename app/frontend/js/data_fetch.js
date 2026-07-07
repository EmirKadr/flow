// @ts-check
const dataFetchState = {
  plan: null,
  pendingRemovedColumns: new Set(),
  result: null,
  busy: false,
  catalogReady: false,
  apiReady: false,
  minimaxReady: false,
};

function dataFetchEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function dataFetchValueText(value) {
  if (Array.isArray(value)) return value.map(dataFetchValueText).join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

function dataFetchErrorDetail(error, fallback) {
  const detail = error?.body?.detail;
  if (detail && typeof detail === "object") {
    return {
      message: detail.message || error.message || fallback,
      errorId: detail.error_id || "",
      view: detail.view || "",
      viewLabel: detail.view_label || "",
      status: error.status || "",
    };
  }
  return {
    message: error?.message || fallback,
    errorId: "",
    view: "",
    viewLabel: "",
    status: error?.status || "",
  };
}

function renderDataFetchError(error, fallback) {
  const status = document.getElementById("dataFetchStatus");
  const detail = dataFetchErrorDetail(error, fallback);
  const meta = [
    detail.status ? `HTTP ${detail.status}` : "",
    detail.errorId ? `Fel-id ${detail.errorId}` : "",
    detail.view ? `Vy ${detail.view}` : "",
  ].filter(Boolean).join(" · ");
  status.classList.add("error");
  status.innerHTML = `
    <strong>${dataFetchEscape(detail.message)}</strong>
    ${meta ? `<span>${dataFetchEscape(meta)}</span>` : ""}
  `;
}

function dataFetchColumnLabel(plan, columnId) {
  return plan?.output_column_labels?.[columnId] || columnId;
}

function dataFetchRemainingColumns(plan = dataFetchState.plan) {
  const removed = dataFetchState.pendingRemovedColumns || new Set();
  return (plan?.output_columns || []).filter((columnId) => !removed.has(columnId));
}

function dataFetchMetricLabel(metric) {
  return ({
    count: "Antal rader",
    count_distinct: "Antal unika",
    sum: "Summa",
    avg: "Snitt",
    min: "Min",
    max: "Max",
  })[metric] || "Beräkning";
}

function renderDataFetchCalculationPlan(plan) {
  const calculation = plan?.calculation;
  if (!calculation) return "";
  const field = calculation.field ? dataFetchColumnLabel(plan, calculation.field) : "";
  const distinctBy = (calculation.distinct_by || [])
    .map((columnId) => `<code>${dataFetchEscape(columnId)}</code> ${dataFetchEscape(dataFetchColumnLabel(plan, columnId))}`)
    .join(", ");
  const groupBy = (calculation.group_by || [])
    .map((columnId) => `<code>${dataFetchEscape(columnId)}</code> ${dataFetchEscape(dataFetchColumnLabel(plan, columnId))}`)
    .join(", ");
  const sortBy = calculation.sort_by
    ? `${dataFetchEscape(calculation.sort_by.field || "value")} ${dataFetchEscape(calculation.sort_by.direction || "desc")}`
    : "";
  const details = [
    field ? `Fält: ${dataFetchEscape(field)}` : "",
    distinctBy ? `Unikt per: ${distinctBy}` : "",
    groupBy ? `Gruppera per: ${groupBy}` : "",
    sortBy ? `Sortering: ${sortBy}` : "",
    calculation.limit ? `Max grupper: ${dataFetchEscape(calculation.limit)}` : "",
  ].filter(Boolean);
  return `
    <div class="data-fetch-calculation-plan">
      <strong>${dataFetchEscape(dataFetchMetricLabel(calculation.metric))}</strong>
      ${details.length ? `<ul>${details.map((item) => `<li>${item}</li>`).join("")}</ul>` : ""}
    </div>
  `;
}

function renderDataFetchCalculationResult(result) {
  const calculation = result?.calculation;
  if (!calculation) return "";
  const groupColumns = Array.isArray(calculation.columns) ? calculation.columns : [];
  const groupRows = Array.isArray(calculation.rows) ? calculation.rows : [];
  const groupTable = groupColumns.length && groupRows.length
    ? `
      <div class="data-fetch-table-wrap data-fetch-calculation-table">
        <table>
          <thead><tr>${groupColumns.map((column) => `<th>${dataFetchEscape(column.label)}</th>`).join("")}</tr></thead>
          <tbody>
            ${groupRows.map((row) => `
              <tr>${groupColumns.map((column) => `<td>${dataFetchEscape(dataFetchValueText(row[column.id]))}</td>`).join("")}</tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `
    : "";
  return `
    <div class="data-fetch-calculation-result">
      <div>
        <span>${dataFetchEscape(calculation.label || dataFetchMetricLabel(calculation.metric))}</span>
        <strong>${dataFetchEscape(dataFetchValueText(calculation.value))}</strong>
      </div>
      ${result.calculation_query ? `
        <details>
          <summary>SQL/query</summary>
          <pre>${dataFetchEscape(result.calculation_query)}</pre>
        </details>
      ` : ""}
      ${groupTable}
    </div>
  `;
}

function dataFetchUpdateActions() {
  const planButton = document.getElementById("dataFetchPlan");
  const runButton = document.getElementById("dataFetchRun");
  const exportButton = document.getElementById("dataFetchExport");
  if (planButton) {
    /** @type {HTMLInputElement} */ (planButton).disabled =
      dataFetchState.busy || !dataFetchState.catalogReady || !dataFetchState.minimaxReady;
  }
  if (runButton) {
    /** @type {HTMLInputElement} */ (runButton).disabled =
      dataFetchState.busy
      || !dataFetchState.catalogReady
      || !dataFetchState.apiReady
      || dataFetchState.plan?.status !== "ok";
  }
  if (exportButton) {
    /** @type {HTMLInputElement} */ (exportButton).disabled = dataFetchState.busy || !dataFetchState.result?.session_id;
  }
}

function dataFetchSetBusy(active, text = "") {
  dataFetchState.busy = Boolean(active);
  dataFetchUpdateActions();
  const status = document.getElementById("dataFetchStatus");
  status.classList.remove("error");
  status.textContent = text;
}

function dataFetchMaxRows() {
  const rawValue = /** @type {HTMLInputElement} */ (document.getElementById("dataFetchMaxRows")).value.trim();
  if (!rawValue) return null;
  const value = Number(rawValue);
  if (!Number.isFinite(value)) return null;
  return Math.min(5000, Math.max(1, Math.floor(value)));
}

function dataFetchBusinessId() {
  if (typeof areaFocusBusinessId !== "function") return null;
  const businessId = Number(areaFocusBusinessId());
  return Number.isInteger(businessId) && businessId > 0 ? businessId : null;
}

function updateDataFetchPlanColumns() {
  const plan = dataFetchState.plan;
  if (!plan || plan.status !== "ok" || !dataFetchState.pendingRemovedColumns?.size) return;
  const outputColumns = dataFetchRemainingColumns(plan);
  if (!outputColumns.length) {
    showToast("Minst en kolumn måste vara kvar.", "warn", 5000);
    return;
  }
  const labels = { ...(plan.output_column_labels || {}) };
  outputColumns.forEach((columnId) => {
    labels[columnId] = dataFetchColumnLabel(plan, columnId);
  });
  const updatedPlan = {
    ...plan,
    output_columns: outputColumns,
    output_column_labels: labels,
  };
  dataFetchState.pendingRemovedColumns = new Set();
  renderDataFetchResult(null);
  renderDataFetchPlan(updatedPlan, { keepColumnDraft: true });
  dataFetchSetBusy(false, "Planen är uppdaterad.");
}

function bindDataFetchPlanControls(panel) {
  panel.querySelectorAll("[data-remove-column]").forEach((button) => {
    button.addEventListener("click", () => {
      const columnId = button.dataset.removeColumn;
      if (!columnId) return;
      const removed = dataFetchState.pendingRemovedColumns || new Set();
      if (removed.has(columnId)) {
        removed.delete(columnId);
      } else {
        const remainingCount = dataFetchRemainingColumns().length;
        if (remainingCount <= 1) {
          showToast("Minst en kolumn måste vara kvar.", "warn", 5000);
          return;
        }
        removed.add(columnId);
      }
      dataFetchState.pendingRemovedColumns = removed;
      renderDataFetchPlan(dataFetchState.plan, { keepColumnDraft: true });
    });
  });
  panel.querySelector("[data-update-columns]")?.addEventListener("click", updateDataFetchPlanColumns);
}

function renderDataFetchPlan(plan, options = {}) {
  const panel = document.getElementById("dataFetchPlanPanel");
  if (!options.keepColumnDraft) {
    dataFetchState.pendingRemovedColumns = new Set();
  }
  dataFetchState.plan = plan;
  dataFetchUpdateActions();
  if (!plan) {
    panel.hidden = true;
    panel.innerHTML = "";
    return;
  }
  panel.hidden = false;
  if (plan.status === "needs_clarification") {
    panel.innerHTML = `
      <div class="data-fetch-panel-head">
        <h2>Behöver förtydligande</h2>
      </div>
      <p>${dataFetchEscape(plan.question || "Beskriv vilken vy och vilka filter som ska användas.")}</p>
    `;
    return;
  }
  const removedColumns = dataFetchState.pendingRemovedColumns || new Set();
  const remainingColumns = dataFetchRemainingColumns(plan);
  const updateDisabled = dataFetchState.busy || !removedColumns.size || !remainingColumns.length;
  const filters = (plan.filters || []).map((filter) => `
    <li><code>${dataFetchEscape(filter.id)}</code> ${dataFetchEscape(filter.operator)}
      <strong>${dataFetchEscape(dataFetchValueText(filter.value))}</strong></li>
  `).join("");
  const calculation = renderDataFetchCalculationPlan(plan);
  const columns = (plan.output_columns || []).map((columnId) => `
    <button
      type="button"
      class="data-fetch-chip${removedColumns.has(columnId) ? " is-removing" : ""}"
      data-remove-column="${dataFetchEscape(columnId)}"
      aria-pressed="${removedColumns.has(columnId) ? "true" : "false"}"
      title="${removedColumns.has(columnId) ? "Behåll kolumn" : "Ta bort kolumn"}"
    >
      ${dataFetchEscape(dataFetchColumnLabel(plan, columnId))}
      <code>${dataFetchEscape(columnId)}</code>
      <span aria-hidden="true">×</span>
    </button>
  `).join("");
  panel.innerHTML = `
    <div class="data-fetch-panel-head">
      <div>
        <h2>Plan</h2>
        <p class="note">${dataFetchEscape(plan.view_label || plan.view)} <code>${dataFetchEscape(plan.view)}</code></p>
      </div>
    </div>
    ${plan.reason ? `<p>${dataFetchEscape(plan.reason)}</p>` : ""}
    ${plan.notice ? `<p class="data-fetch-notice" role="status">${dataFetchEscape(plan.notice)}</p>` : ""}
    <div class="data-fetch-column-list">${columns}</div>
    <div class="data-fetch-column-actions">
      <button type="button" data-update-columns ${updateDisabled ? "disabled" : ""}>Uppdatera plan</button>
    </div>
    <div class="data-fetch-filter-list">
      <strong>Filter</strong>
      ${filters ? `<ul>${filters}</ul>` : '<p class="note">Inga filter.</p>'}
    </div>
    ${calculation}
  `;
  bindDataFetchPlanControls(panel);
}

function renderDataFetchResult(result) {
  const panel = document.getElementById("dataFetchResultPanel");
  dataFetchState.result = result;
  dataFetchUpdateActions();
  if (!result || !result.columns?.length) {
    panel.hidden = true;
    panel.innerHTML = "";
    return;
  }
  const header = result.columns.map((column) => `<th>${dataFetchEscape(column.label)}</th>`).join("");
  const rows = (result.rows || []).map((row) => `
    <tr>
      ${result.columns.map((column) => `<td>${dataFetchEscape(dataFetchValueText(row[column.id]))}</td>`).join("")}
    </tr>
  `).join("");
  panel.hidden = false;
  panel.innerHTML = `
    <div class="data-fetch-panel-head">
      <div>
        <h2>Resultat</h2>
        <p class="note">
          Visar ${dataFetchEscape(result.shown_rows ?? result.rows.length)} av ${dataFetchEscape(result.total_rows ?? result.rows.length)} rader.
          ${result.truncated ? "Exporten innehåller samma begränsade radurval." : ""}
        </p>
      </div>
    </div>
    ${renderDataFetchCalculationResult(result)}
    <div class="data-fetch-table-wrap">
      <table>
        <thead><tr>${header}</tr></thead>
        <tbody>${rows || `<tr><td colspan="${result.columns.length}">Inga rader.</td></tr>`}</tbody>
      </table>
    </div>
  `;
}

async function loadDataFetchHealth() {
  const health = document.getElementById("dataFetchHealth");
  try {
    const result = await api.get("/api/query-data/health");
    const catalog = result.catalog || {};
    dataFetchState.catalogReady = Boolean(result.catalog_configured);
    dataFetchState.apiReady = Boolean(result.api_configured);
    dataFetchState.minimaxReady = Boolean(result.minimax_configured);
    const missingApi = Array.isArray(result.api_missing) ? result.api_missing : [];
    const apiText = result.api_configured
      ? " API är konfigurerat."
      : ` API saknar: ${missingApi.length ? missingApi.join(", ") : "miljövärden"}.`;
    if (result.ok) {
      health.hidden = true;
      health.textContent = "";
      health.classList.remove("error-text");
    } else {
      health.hidden = false;
      health.classList.add("error-text");
      health.textContent = `Katalog: ${catalog.views || 0} vyer, ${catalog.columns || 0} kolumner.`
        + apiText
        + (result.minimax_configured ? " MiniMax är konfigurerat." : " MiniMax saknar API-nyckel.")
        + (result.message ? ` ${result.message}` : "");
    }
    dataFetchSetBusy(false);
  } catch (error) {
    dataFetchState.catalogReady = false;
    dataFetchState.apiReady = false;
    dataFetchState.minimaxReady = false;
    renderDataFetchPlan(null);
    renderDataFetchResult(null);
    health.hidden = false;
    health.textContent = error.message || "Kunde inte kontrollera datahämtning.";
    health.classList.add("error-text");
    dataFetchSetBusy(false, "Ingen AI-fråga skickades.");
  }
}

async function planDataFetch() {
  if (!dataFetchState.catalogReady) {
    showToast("Katalogen saknas. Ingen AI-fråga skickades.", "warn", 6000);
    return;
  }
  if (!dataFetchState.minimaxReady) {
    showToast("MiniMax saknar API-nyckel. Ingen AI-fråga skickades.", "warn", 6000);
    return;
  }
  const prompt = /** @type {HTMLInputElement} */ (document.getElementById("dataFetchPrompt")).value.trim();
  if (!prompt) {
    showToast("Skriv vad du vill hämta först.", "warn");
    return;
  }
  dataFetchSetBusy(true, "MiniMax tolkar prompten...");
  renderDataFetchPlan(null);
  renderDataFetchResult(null);
  try {
    const result = await api.post("/api/query-data/plan", { prompt });
    renderDataFetchPlan(result.plan);
    dataFetchSetBusy(false, result.plan?.status === "ok" ? "Planen är klar." : "");
  } catch (error) {
    dataFetchSetBusy(false, "");
    showToast(error.message || "Kunde inte tolka prompten.", "error", 7000);
  }
}

async function runDataFetch() {
  if (!dataFetchState.catalogReady || !dataFetchState.apiReady || !dataFetchState.plan || dataFetchState.plan.status !== "ok") return;
  dataFetchSetBusy(true, "Hämtar data...");
  try {
    const payload = {
      plan: dataFetchState.plan,
      max_rows: dataFetchMaxRows(),
    };
    const businessId = dataFetchBusinessId();
    if (businessId != null) payload.business_id = businessId;
    const result = await api.post("/api/query-data/run", payload);
    renderDataFetchResult(result);
    dataFetchSetBusy(false, "Data hämtad.");
  } catch (error) {
    dataFetchSetBusy(false, "");
    renderDataFetchError(error, "Kunde inte hämta data.");
    showToast(error.message || "Kunde inte hämta data.", "error", 8000);
  }
}

async function exportDataFetch() {
  const sessionId = dataFetchState.result?.session_id;
  if (!sessionId) return;
  try {
    await api.download(`/api/query-data/export/${encodeURIComponent(sessionId)}`, "hamta-data.xlsx");
  } catch (error) {
    showToast(error.message || "Kunde inte exportera Excel.", "error", 7000);
  }
}

function resetDataFetchForPromptEdit() {
  if (!dataFetchState.plan && !dataFetchState.result) return;
  renderDataFetchPlan(null);
  renderDataFetchResult(null);
  dataFetchSetBusy(false, "");
}

async function initDataFetchPage() {
  const user = await initPage("dataFetch");
  if (!user) return;
  if (typeof loadAreaFocusAreas === "function") await loadAreaFocusAreas(user).catch(() => {});
  await loadDataFetchHealth();
  document.getElementById("dataFetchPrompt").addEventListener("input", resetDataFetchForPromptEdit);
  document.getElementById("dataFetchPlan").addEventListener("click", planDataFetch);
  document.getElementById("dataFetchRun").addEventListener("click", runDataFetch);
  document.getElementById("dataFetchExport").addEventListener("click", exportDataFetch);
}

initDataFetchPage();

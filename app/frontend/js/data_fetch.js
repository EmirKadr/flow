const dataFetchState = {
  plan: null,
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

function dataFetchSetBusy(active, text = "") {
  dataFetchState.busy = Boolean(active);
  document.getElementById("dataFetchPlan").disabled =
    dataFetchState.busy || !dataFetchState.catalogReady || !dataFetchState.minimaxReady;
  document.getElementById("dataFetchRun").disabled =
    dataFetchState.busy
      || !dataFetchState.catalogReady
      || !dataFetchState.apiReady
      || dataFetchState.plan?.status !== "ok";
  document.getElementById("dataFetchReloadCatalog").disabled = dataFetchState.busy;
  document.getElementById("dataFetchStatus").textContent = text;
}

function dataFetchMaxRows() {
  const value = Number(document.getElementById("dataFetchMaxRows").value || 500);
  return Math.min(5000, Math.max(1, Number.isFinite(value) ? value : 500));
}

function renderDataFetchPlan(plan) {
  const panel = document.getElementById("dataFetchPlanPanel");
  dataFetchState.plan = plan;
  document.getElementById("dataFetchRun").disabled =
    dataFetchState.busy || !dataFetchState.catalogReady || !dataFetchState.apiReady || plan?.status !== "ok";
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
  const filters = (plan.filters || []).map((filter) => `
    <li><code>${dataFetchEscape(filter.id)}</code> ${dataFetchEscape(filter.operator)}
      <strong>${dataFetchEscape(dataFetchValueText(filter.value))}</strong></li>
  `).join("");
  const columns = (plan.output_columns || []).map((columnId) => `
    <span class="data-fetch-chip">${dataFetchEscape(plan.output_column_labels?.[columnId] || columnId)} <code>${dataFetchEscape(columnId)}</code></span>
  `).join("");
  panel.innerHTML = `
    <div class="data-fetch-panel-head">
      <div>
        <h2>Plan</h2>
        <p class="note">${dataFetchEscape(plan.view_label || plan.view)} <code>${dataFetchEscape(plan.view)}</code></p>
      </div>
    </div>
    ${plan.reason ? `<p>${dataFetchEscape(plan.reason)}</p>` : ""}
    <div class="data-fetch-column-list">${columns}</div>
    <div class="data-fetch-filter-list">
      <strong>Filter</strong>
      ${filters ? `<ul>${filters}</ul>` : '<p class="note">Inga filter.</p>'}
    </div>
  `;
}

function renderDataFetchResult(result) {
  const panel = document.getElementById("dataFetchResultPanel");
  dataFetchState.result = result;
  document.getElementById("dataFetchExport").disabled = !result?.session_id;
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
    health.classList.toggle("error-text", !result.ok);
    health.textContent = `Katalog: ${catalog.views || 0} vyer, ${catalog.columns || 0} kolumner.`
      + apiText
      + (result.minimax_configured ? " MiniMax är konfigurerat." : " MiniMax saknar API-nyckel.")
      + (result.message ? ` ${result.message}` : "");
    dataFetchSetBusy(false);
  } catch (error) {
    dataFetchState.catalogReady = false;
    dataFetchState.apiReady = false;
    dataFetchState.minimaxReady = false;
    renderDataFetchPlan(null);
    renderDataFetchResult(null);
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
  const prompt = document.getElementById("dataFetchPrompt").value.trim();
  if (!prompt) {
    showToast("Skriv vad du vill hämta först.", "warn");
    return;
  }
  dataFetchSetBusy(true, "MiniMax tolkar prompten...");
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
    const result = await api.post("/api/query-data/run", {
      plan: dataFetchState.plan,
      max_rows: dataFetchMaxRows(),
    });
    renderDataFetchResult(result);
    dataFetchSetBusy(false, "Data hämtad.");
  } catch (error) {
    dataFetchSetBusy(false, "");
    showToast(error.message || "Kunde inte hämta data.", "error", 8000);
  }
}

async function reloadDataFetchCatalog() {
  dataFetchSetBusy(true, "Läser om katalog...");
  try {
    await api.post("/api/query-data/catalog/reload", {});
    await loadDataFetchHealth();
    dataFetchSetBusy(false, "Katalogen är omläst.");
  } catch (error) {
    dataFetchSetBusy(false, "");
    showToast(error.message || "Kunde inte läsa om katalogen.", "error", 7000);
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

async function initDataFetchPage() {
  const user = await initPage("dataFetch");
  if (!user) return;
  await loadDataFetchHealth();
  document.getElementById("dataFetchPlan").addEventListener("click", planDataFetch);
  document.getElementById("dataFetchRun").addEventListener("click", runDataFetch);
  document.getElementById("dataFetchExport").addEventListener("click", exportDataFetch);
  document.getElementById("dataFetchReloadCatalog").addEventListener("click", reloadDataFetchCatalog);
}

initDataFetchPage();

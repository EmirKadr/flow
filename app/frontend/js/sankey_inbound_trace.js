// @ts-check
// Utdelad ur sankey_inbound.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter sankey_inbound.js via <script>-tagg.

function renderSankeySummary(payload) {
  const target = document.getElementById("sankeyInboundSummary");
  if (!target) return;
  const summary = payload?.summary || {};
  const currency = payload?.currency || "SEK";
  target.innerHTML = `
    <article class="sankey-inbound-kpi">
      <span>Gross income</span>
      <strong>${sankeyEscapeHtml(sankeyFormatMoney(summary.gross_income, currency))}</strong>
    </article>
    <article class="sankey-inbound-kpi">
      <span>Inbound</span>
      <strong>${sankeyEscapeHtml(sankeyFormatMoney(summary.inbound_income ?? summary.gross_income, currency))}</strong>
    </article>
    <article class="sankey-inbound-kpi">
      <span>Outbound</span>
      <strong>${sankeyEscapeHtml(sankeyFormatMoney(summary.outbound_income, currency))}</strong>
    </article>
    <article class="sankey-inbound-kpi">
      <span>Mottagna etiketter</span>
      <strong>${sankeyEscapeHtml(sankeyFormatNumber(summary.labels_received))}</strong>
    </article>
    <article class="sankey-inbound-kpi">
      <span>Mottagna inköpsrader</span>
      <strong>${sankeyEscapeHtml(sankeyFormatNumber(summary.purchase_lines_received))}</strong>
    </article>
    <article class="sankey-inbound-kpi">
      <span>Förverkade</span>
      <strong>${sankeyEscapeHtml(sankeyFormatNumber(summary.labels_consumed, 2))}</strong>
    </article>
    <article class="sankey-inbound-kpi">
      <span>Öppna</span>
      <strong>${sankeyEscapeHtml(sankeyFormatNumber(summary.labels_open, 2))}</strong>
    </article>
    <article class="sankey-inbound-kpi">
      <span>Outbound orders</span>
      <strong>${sankeyEscapeHtml(sankeyFormatNumber(summary.outbound_picked_orders))}</strong>
    </article>
  `;
}

function sankeyNodeColor(node) {
  if (node.type === "source") return SANKEY_INBOUND_COLORS.source;
  if (String(node.type || "").startsWith("outbound")) {
    return SANKEY_INBOUND_COLORS[node.type] || SANKEY_INBOUND_COLORS.outbound_metric;
  }
  if (node.type === "terminal") {
    return String(node.key || "").includes("consumed") ? SANKEY_INBOUND_COLORS.consumed : SANKEY_INBOUND_COLORS.open;
  }
  const processKey = String(node.key || "").replace("process:", "");
  return SANKEY_INBOUND_COLORS[processKey] || SANKEY_INBOUND_COLORS.terminal;
}

function sankeyLinkColor(link, nodesById) {
  const source = nodesById.get(link.source);
  return sankeyNodeColor(source || {});
}

function sankeyFlowUnitLabel(item) {
  return item?.unit_label || "etiketter";
}

function sankeyNodePrimaryValue(node, currency) {
  if (String(node.type || "").startsWith("outbound")) {
    return `${sankeyFormatMoney(node.value, currency)} · ${sankeyFormatNumber(node.labels, 0)} ${sankeyFlowUnitLabel(node)}`;
  }
  if (node.type === "terminal") return `${sankeyFormatNumber(node.labels, 2)} ${sankeyFlowUnitLabel(node)}`;
  if (node.type === "process") return sankeyFormatMoney(node.revenue, currency);
  return sankeyFormatMoney(node.value, currency);
}

function sankeyNodeTitleValue(node, currency) {
  if (String(node.type || "").startsWith("outbound")) {
    return `outboundintäkt ${sankeyFormatMoney(node.outbound_revenue || node.value, currency)} · ${sankeyFormatNumber(node.labels, 0)} ${sankeyFlowUnitLabel(node)}`;
  }
  if (node.type === "terminal") {
    return `${sankeyFormatNumber(node.labels, 2)} ${sankeyFlowUnitLabel(node)} · statuspott ${sankeyFormatMoney(node.value, currency)}`;
  }
  if (node.type === "process") {
    return `processintäkt ${sankeyFormatMoney(node.revenue, currency)} · genomflöde ${sankeyFormatMoney(node.value, currency)}`;
  }
  return `gross income ${sankeyFormatMoney(node.value, currency)}`;
}

function sankeyRevenueBreakdownRows(item, currency) {
  const outbound = Number(item?.outbound_revenue || 0);
  const outboundRow = outbound
    ? `<div><dt>Outboundintäkt</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(outbound, currency))}</dd></div>`
    : "";
  return `
    <div><dt>Etikettintäkt</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(item?.label_revenue, currency))}</dd></div>
    <div><dt>Inköpsradsintäkt</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(item?.purchase_line_revenue, currency))}</dd></div>
    ${outboundRow}
  `;
}

function sankeyLinkKey(link) {
  return `${link?.source || ""}->${link?.target || ""}`;
}

function appendSankeyTraceFilterParams(params) {
  const filter = sankeyInboundPayload?.trace_filter || {};
  if (filter.company && filter.company !== "ALL") params.set("company", filter.company);
  if (filter.start_date) params.set("start_date", filter.start_date);
  if (filter.end_date) params.set("end_date", filter.end_date);
  if (filter.only_consumed) params.set("only_consumed", "true");
  return params;
}

function sankeyAllTraceScope(payload = sankeyInboundPayload || {}) {
  return { scope: "all", id: null, count: Number(payload.trace_total || 0), name: "alla" };
}

function selectedSankeyTraceScope() {
  // Trace-raderna lazy-laddas – här härleds bara urvalets scope/id + antal (ur trace_counts).
  const payload = sankeyInboundPayload || {};
  const counts = payload.trace_counts || {};
  if (sankeyInboundSelected?.type === "node") {
    const id = sankeyInboundSelected.id;
    const node = (payload.nodes || []).find((item) => item.id === id);
    if (!node) return sankeyAllTraceScope(payload);
    return { scope: "node", id, count: Number((counts.nodes || {})[id] || 0), name: sankeyTraceScopeLabel() };
  }
  if (sankeyInboundSelected?.type === "link") {
    const link = (payload.links || [])[sankeyInboundSelected.index];
    if (!link) return sankeyAllTraceScope(payload);
    const key = sankeyLinkKey(link);
    return { scope: "link", id: key, count: Number((counts.links || {})[key] || 0), name: sankeyTraceScopeLabel() };
  }
  return sankeyAllTraceScope(payload);
}

function sankeyTraceScopeLabel() {
  const payload = sankeyInboundPayload || {};
  if (sankeyInboundSelected?.type === "node") {
    const node = (payload.nodes || []).find((item) => item.id === sankeyInboundSelected.id);
    return node?.label || "nod";
  }
  if (sankeyInboundSelected?.type === "link") {
    const link = (payload.links || [])[sankeyInboundSelected.index];
    const nodes = new Map((payload.nodes || []).map((node) => [node.id, node]));
    const source = nodes.get(link?.source)?.label || link?.source || "flode";
    const target = nodes.get(link?.target)?.label || link?.target || "urval";
    return `${source}-${target}`;
  }
  return "alla";
}

function sankeySafeFilePart(value) {
  return String(value || "urval")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60) || "urval";
}

function exportSankeyTraceDownload(trace, controlId = "sankey-inbound-export-trace") {
  if (!trace?.count) {
    if (typeof showToast === "function") showToast("Det finns inga spårade pallgrenar att exportera i urvalet.", "warn", 4000);
    return;
  }
  const token = sankeyInboundPayload?.trace_token;
  if (!token) {
    if (typeof showToast === "function") showToast("Spårningen har gått ut. Kör om rapporten.", "warn", 5000);
    return;
  }
  const params = new URLSearchParams({
    token,
    scope: trace.scope,
    name: `${sankeyInboundPeriod}-${sankeyDateValue()}-${sankeySafeFilePart(trace.name)}`,
  });
  if (trace.id) params.set("id", trace.id);
  appendSankeyTraceFilterParams(params);
  window.location.href = `/api/sankey/inbound/trace.csv?${params}`;
  if (typeof showToast === "function") showToast(`CSV-exporten startar för ${sankeyFormatNumber(trace.count)} spårade pallgrenar.`, "success", 3000);
  if (typeof flowTrack === "function") {
    flowTrack("download", {
      control_id: controlId,
      view: "sankeyInbound",
      period: sankeyInboundPeriod,
      scope: trace.scope,
      rows: trace.count,
    });
  }
}

function exportSankeyTraceRows() {
  exportSankeyTraceDownload(selectedSankeyTraceScope(), "sankey-inbound-export-trace");
}

function exportAllSankeyTraceRows() {
  exportSankeyTraceDownload(sankeyAllTraceScope(), "sankey-inbound-export-trace-all");
}

function renderSankeyTracePlaceholder(trace) {
  const count = Number(trace?.count || 0);
  const body = count
    ? '<tr><td colspan="5" class="empty-cell">Laddar...</td></tr>'
    : '<tr><td colspan="5" class="empty-cell">Inga spårade pallgrenar i urvalet.</td></tr>';
  const disabled = count === 0 ? " disabled" : "";
  return `
    <div class="sankey-trace-preview">
      <div class="sankey-trace-head">
        <h3>Spårade pallgrenar</h3>
        <button type="button" data-sankey-export-traces${disabled}>Exportera urval</button>
      </div>
      <p>${sankeyEscapeHtml(sankeyFormatNumber(count))} pallgrenar matchar urvalet. Tabellen visar max 8 rader.</p>
      <div class="sankey-trace-table-wrap">
        <table class="sankey-trace-table">
          <thead>
            <tr>
              <th scope="col">Ursprung</th>
              <th scope="col">Nu</th>
              <th scope="col">Artikel</th>
              <th scope="col">Status</th>
              <th scope="col">Väg</th>
            </tr>
          </thead>
          <tbody data-sankey-trace-body>${body}</tbody>
        </table>
      </div>
    </div>
  `;
}

function sankeyTraceRowHtml(row) {
  return `
    <tr>
      <td>${sankeyEscapeHtml(row.origin_pall || row.current_pall || "")}</td>
      <td>${sankeyEscapeHtml(row.current_pall || "")}</td>
      <td>${sankeyEscapeHtml(row.item || "")}</td>
      <td>${sankeyEscapeHtml(row.status_label || "")}</td>
      <td class="sankey-trace-path" title="${sankeyEscapeHtml(row.path || "")}">${sankeyEscapeHtml(row.path || "")}</td>
    </tr>
  `;
}

async function fetchSankeyTraceRows(scope, id, offset, limit) {
  const token = sankeyInboundPayload?.trace_token;
  if (!token) {
    const error = /** @type {Error & { status?: number }} */ (new Error("Spårningen har gått ut. Kör om rapporten."));
    error.status = 410;
    throw error;
  }
  const params = new URLSearchParams({ token, scope, offset, limit });
  if (id) params.set("id", id);
  appendSankeyTraceFilterParams(params);
  return api.get(`/api/sankey/inbound/trace?${params}`);
}

async function hydrateSankeyTracePreview(trace) {
  const seq = ++sankeyTraceHydrateSeq;
  const target = document.getElementById("sankeyInboundDetail");
  const body = target?.querySelector("[data-sankey-trace-body]");
  if (!body || !trace?.count) return;
  try {
    const data = await fetchSankeyTraceRows(trace.scope, trace.id, 0, 8);
    if (seq !== sankeyTraceHydrateSeq) return;
    const rows = Array.isArray(data?.rows) ? data.rows : [];
    body.innerHTML = rows.length
      ? rows.map(sankeyTraceRowHtml).join("")
      : '<tr><td colspan="5" class="empty-cell">Inga spårade pallgrenar i urvalet.</td></tr>';
  } catch (error) {
    if (seq !== sankeyTraceHydrateSeq) return;
    const message = error?.status === 410
      ? "Spårningen har gått ut. Kör om rapporten."
      : "Spårade pallgrenar kunde inte hämtas.";
    body.innerHTML = `<tr><td colspan="5" class="empty-cell">${sankeyEscapeHtml(message)}</td></tr>`;
    if (typeof showToast === "function") showToast(message, error?.status === 410 ? "warn" : "error", 5000);
  }
}

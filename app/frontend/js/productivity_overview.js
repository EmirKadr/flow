function productivityOverviewSourceWarnings(report) {
  const warnings = [];
  const seen = new Set();
  const sourceGroups = Array.isArray(report?.source_status) ? report.source_status : [];
  for (const group of sourceGroups) {
    const sources = Array.isArray(group?.sources)
      ? group.sources
      : (Array.isArray(group) ? group : []);
    for (const source of sources) {
      if (source?.key !== "kpi" || source?.status !== "coredata_fallback") continue;
      const reason = String(source?.fallback_reason || "").trim();
      const message = reason ? `KPI API fallback: ${reason}` : "KPI från coredata";
      if (seen.has(message)) continue;
      seen.add(message);
      warnings.push(message);
    }
  }
  return warnings;
}

function productivityOverviewExportLabel(node) {
  const rate = productivityOverviewPointsPerHour(node);
  const finance = productivityOverviewNodeHasFinance(node)
    ? ` · Resultat ${formatProductivityOverviewMoney(node.financeResult, node.financeCurrency)}`
    : "";
  if (node?.type === "process") return `${formatProductivityOverviewPoints(node.points)}${finance}`;
  return `${formatProductivityOverviewPoints(node.points)} / ${formatProductivityOverviewHours(node.workMinutes)} = ${formatProductivityOverviewRate(rate)}${finance}`;
}

function productivityOverviewExportColor(node) {
  if (node?.type === "process") return "#4f46e5";
  const scoreClass = productivityOverviewScoreClass(productivityOverviewPointsPerHour(node));
  if (scoreClass === "good") return "#16a34a";
  if (scoreClass === "warn") return "#d97706";
  if (scoreClass === "low") return "#dc2626";
  return "#64748b";
}

function productivityOverviewExportWrap(text, maxChars = 24, maxLines = 2) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxChars && current) {
      lines.push(current);
      current = word;
      if (lines.length >= maxLines) break;
    } else {
      current = next;
    }
  }
  if (current && lines.length < maxLines) lines.push(current);
  if (!lines.length) lines.push("-");
  if (lines.length === maxLines && words.join(" ").length > lines.join(" ").length) {
    lines[maxLines - 1] = `${lines[maxLines - 1].slice(0, Math.max(1, maxChars - 1))}…`;
  }
  return lines;
}

function productivityOverviewExportNode(sourceNode, includedTypes = null, forceInclude = false) {
  const allowed = includedTypes instanceof Set ? includedTypes : new Set(PRODUCTIVITY_OVERVIEW_EXPORT_LEVELS.map((level) => level.type));
  const promotedChildren = [];
  for (const child of sourceNode.children || []) {
    const exported = productivityOverviewExportNode(child, allowed, false);
    if (Array.isArray(exported)) promotedChildren.push(...exported);
    else if (exported) promotedChildren.push(exported);
  }
  if (!forceInclude && !allowed.has(sourceNode.type)) return promotedChildren;
  return {
    source: sourceNode,
    children: promotedChildren,
    leafCount: 1,
    maxDepth: 0,
    x: 0,
    y: 0,
  };
}

function measureProductivityOverviewExportNode(node, depth = 0) {
  node.maxDepth = depth;
  if (!node.children.length) {
    node.leafCount = 1;
    return node;
  }
  node.leafCount = 0;
  for (const child of node.children) {
    measureProductivityOverviewExportNode(child, depth + 1);
    node.leafCount += child.leafCount;
    node.maxDepth = Math.max(node.maxDepth, child.maxDepth);
  }
  return node;
}

function assignProductivityOverviewExportPositions(node, state, depth = 0) {
  const width = state.nodeWidth;
  const stepX = state.nodeWidth + state.gapX;
  if (!node.children.length) {
    node.x = state.margin + state.nextLeaf * stepX + width / 2;
    state.nextLeaf += 1;
  } else {
    for (const child of node.children) assignProductivityOverviewExportPositions(child, state, depth + 1);
    node.x = (node.children[0].x + node.children[node.children.length - 1].x) / 2;
  }
  node.y = state.headerHeight + state.margin + depth * (state.nodeHeight + state.gapY) + state.nodeHeight / 2;
}

function flattenProductivityOverviewExportNodes(node, rows = []) {
  rows.push(node);
  for (const child of node.children) flattenProductivityOverviewExportNodes(child, rows);
  return rows;
}

function renderProductivityOverviewExportNode(node, state) {
  const source = node.source;
  const x = node.x - state.nodeWidth / 2;
  const y = node.y - state.nodeHeight / 2;
  const labelLines = productivityOverviewExportWrap(source.label, source.type === "hour" ? 28 : 24, 2);
  const metric = productivityOverviewExportLabel(source);
  const color = productivityOverviewExportColor(source);
  const labelSvg = labelLines.map((line, index) =>
    `<text x="${node.x}" y="${y + 34 + index * 15}" text-anchor="middle" class="node-label">${escapeHtml(line)}</text>`
  ).join("");
  return `
    <g>
      <rect x="${x}" y="${y}" width="${state.nodeWidth}" height="${state.nodeHeight}" rx="8" class="node-box ${escapeHtml(source.type)}" />
      <text x="${node.x}" y="${y + 17}" text-anchor="middle" class="node-type">${escapeHtml(productivityOverviewTypeLabel(source.type))}</text>
      ${labelSvg}
      <text x="${node.x}" y="${y + state.nodeHeight - 14}" text-anchor="middle" class="node-metric" fill="${color}">${escapeHtml(metric)}</text>
    </g>
  `;
}

function buildProductivityOverviewFlowchartSvg(rootNode) {
  const exportTree = measureProductivityOverviewExportNode(rootNode);
  const state = {
    nodeWidth: 238,
    nodeHeight: 86,
    gapX: 34,
    gapY: 78,
    margin: 28,
    headerHeight: 72,
    nextLeaf: 0,
  };
  assignProductivityOverviewExportPositions(exportTree, state);
  const width = Math.max(980, exportTree.leafCount * (state.nodeWidth + state.gapX) + state.margin * 2);
  const height = state.headerHeight + state.margin * 2 + (exportTree.maxDepth + 1) * state.nodeHeight + exportTree.maxDepth * state.gapY;
  const nodes = flattenProductivityOverviewExportNodes(exportTree);
  const edges = nodes.flatMap((node) =>
    node.children.map((child) => {
      const midY = (node.y + child.y) / 2;
      return `<path d="M ${node.x} ${node.y + state.nodeHeight / 2} V ${midY} H ${child.x} V ${child.y - state.nodeHeight / 2}" class="edge" />`;
    })
  ).join("");
  const period = productivityOverviewPeriodLabel(productivityOverviewReport);
  const title = `${rootNode?.source?.label || productivityOverviewRoot?.label || "Verksamhet"} · ${period}`;
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${Math.ceil(width)}" height="${Math.ceil(height)}" viewBox="0 0 ${Math.ceil(width)} ${Math.ceil(height)}" role="img" aria-label="${escapeHtml(title)}">
  <style>
    .title { font: 800 22px Arial, sans-serif; fill: #0f172a; }
    .subtitle { font: 700 13px Arial, sans-serif; fill: #64748b; }
    .edge { fill: none; stroke: #cbd5e1; stroke-width: 1.5; }
    .node-box { fill: #f8fafc; stroke: #cbd5e1; stroke-width: 1.2; }
    .node-box.business { fill: #eef2ff; stroke: #a5b4fc; }
    .node-box.area { fill: #eff6ff; stroke: #bfdbfe; }
    .node-box.activity { fill: #fffbeb; stroke: #fde68a; }
    .node-box.person { fill: #f0fdf4; stroke: #bbf7d0; }
    .node-box.hour { fill: #f8fafc; stroke: #cbd5e1; }
    .node-box.process { fill: #f5f3ff; stroke: #ddd6fe; }
    .node-type { font: 800 10px Arial, sans-serif; fill: #64748b; letter-spacing: .06em; text-transform: uppercase; }
    .node-label { font: 800 13px Arial, sans-serif; fill: #0f172a; }
    .node-metric { font: 800 12px Arial, sans-serif; }
  </style>
  <rect width="100%" height="100%" fill="#ffffff" />
  <text x="${state.margin}" y="31" class="title">${escapeHtml(productivityOverviewRoot?.label || "Produktivitet")}</text>
  <text x="${state.margin}" y="54" class="subtitle">${escapeHtml(period)} · Exporterad ${escapeHtml(formatProductivityOverviewTimestamp(new Date().toISOString()))}</text>
  ${edges}
  ${nodes.map((node) => renderProductivityOverviewExportNode(node, state)).join("")}
</svg>`;
}

function downloadProductivityOverviewText(filename, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function productivityOverviewSubtreeTypes(node, types = new Set()) {
  if (!node) return types;
  types.add(node.type);
  for (const child of node.children || []) productivityOverviewSubtreeTypes(child, types);
  return types;
}

function readProductivityOverviewExportLevels(focusNode) {
  const available = productivityOverviewSubtreeTypes(focusNode);
  let selected = new Set(available);
  try {
    const raw = localStorage.getItem(PRODUCTIVITY_OVERVIEW_EXPORT_LEVELS_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (Array.isArray(parsed)) {
      selected = new Set(parsed.filter((type) => available.has(type)));
    }
  } catch (_error) {}
  if (focusNode?.type) selected.add(focusNode.type);
  return selected;
}

function writeProductivityOverviewExportLevels(types) {
  try {
    localStorage.setItem(PRODUCTIVITY_OVERVIEW_EXPORT_LEVELS_KEY, JSON.stringify([...types]));
  } catch (_error) {}
}

function closeProductivityOverviewExportDialog(backdrop, onKeydown) {
  document.removeEventListener("keydown", onKeydown);
  backdrop?.remove();
}

function performProductivityOverviewFlowchartExport(includedTypes) {
  if (!productivityOverviewRoot) {
    if (typeof showToast === "function") {
      showToast("Det finns ingen produktivitetsöversikt att exportera.", "warn", 4000);
    }
    return;
  }
  const focusNode = productivityOverviewNodeIndex.get(productivityOverviewFocusId) || productivityOverviewRoot;
  const levels = includedTypes instanceof Set
    ? includedTypes
    : new Set(PRODUCTIVITY_OVERVIEW_EXPORT_LEVELS.map((level) => level.type));
  const exportNode = productivityOverviewExportNode(focusNode, levels, true);
  const svg = buildProductivityOverviewFlowchartSvg(exportNode);
  const period = productivityOverviewPeriodValue();
  const datePart = (productivityOverviewReport?.period?.start_date && productivityOverviewReport?.period?.end_date)
    ? `${productivityOverviewReport.period.start_date}_${productivityOverviewReport.period.end_date}`
    : productivityOverviewDateValue();
  const labelPart = String(focusNode.label || "verksamhet").toLowerCase().replace(/[^a-z0-9åäö]+/gi, "-").replace(/^-|-$/g, "") || "verksamhet";
  const filename = `produktivitet-flowchart-${period}-${datePart}-${labelPart}.svg`;
  downloadProductivityOverviewText(filename, svg, "image/svg+xml;charset=utf-8");
  if (typeof showToast === "function") showToast("Flowchart exporterad.", "success", 3000);
  if (typeof flowTrack === "function") {
    flowTrack("download", {
      control_id: "productivity-overview-export-flowchart",
      view: "productivity",
      period,
      focus_type: focusNode.type,
      levels: [...levels].join(","),
    });
  }
}

function openProductivityOverviewExportDialog() {
  if (!productivityOverviewRoot) {
    if (typeof showToast === "function") {
      showToast("Det finns ingen produktivitetsöversikt att exportera.", "warn", 4000);
    }
    return;
  }
  document.querySelector("[data-productivity-export-dialog]")?.remove();
  const focusNode = productivityOverviewNodeIndex.get(productivityOverviewFocusId) || productivityOverviewRoot;
  const available = productivityOverviewSubtreeTypes(focusNode);
  const selected = readProductivityOverviewExportLevels(focusNode);
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.dataset.productivityExportDialog = "true";
  backdrop.innerHTML = `
    <div class="modal productivity-overview-export-modal" role="dialog" aria-modal="true" aria-labelledby="productivityExportTitle">
      <h2 id="productivityExportTitle">Exportera flowchart</h2>
      <form data-productivity-export-form>
        <div class="productivity-overview-export-levels">
          ${PRODUCTIVITY_OVERVIEW_EXPORT_LEVELS.map((level) => {
            const isFocus = level.type === focusNode.type;
            const disabled = !available.has(level.type) || isFocus;
            const checked = selected.has(level.type) || isFocus;
            return `
              <label class="modal-checkbox">
                <input
                  type="checkbox"
                  name="export-level"
                  value="${escapeHtml(level.type)}"
                  ${checked ? "checked" : ""}
                  ${disabled ? "disabled" : ""}
                />
                ${escapeHtml(level.label)}
              </label>
            `;
          }).join("")}
        </div>
        <div class="actions">
          <button type="button" data-productivity-export-cancel>Avbryt</button>
          <button type="submit" class="primary">Exportera</button>
        </div>
      </form>
    </div>
  `;
  const onKeydown = (event) => {
    if (event.key === "Escape") closeProductivityOverviewExportDialog(backdrop, onKeydown);
  };
  document.addEventListener("keydown", onKeydown);
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) closeProductivityOverviewExportDialog(backdrop, onKeydown);
  });
  backdrop.querySelector("[data-productivity-export-cancel]")?.addEventListener("click", () => {
    closeProductivityOverviewExportDialog(backdrop, onKeydown);
  });
  backdrop.querySelector("[data-productivity-export-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const includedTypes = new Set(
      [...backdrop.querySelectorAll('input[name="export-level"]:checked')]
        .map((input) => input.value)
        .filter(Boolean)
    );
    includedTypes.add(focusNode.type);
    writeProductivityOverviewExportLevels(includedTypes);
    closeProductivityOverviewExportDialog(backdrop, onKeydown);
    performProductivityOverviewFlowchartExport(includedTypes);
  });
  document.body.appendChild(backdrop);
  backdrop.querySelector('input[name="export-level"]:not(:disabled)')?.focus();
}

function exportProductivityOverviewFlowchart() {
  openProductivityOverviewExportDialog();
}

function focusProductivityOverviewNode(nodeId) {
  if (!productivityOverviewNodeIndex.has(nodeId)) return;
  productivityOverviewFocusId = nodeId;
  renderProductivityOverviewTree();
}

window.focusProductivityOverviewNode = focusProductivityOverviewNode;
window.exportProductivityOverviewFlowchart = exportProductivityOverviewFlowchart;

function renderProductivityOverviewReport(report) {
  productivityOverviewReport = report;
  if (report?.period?.type) productivityOverviewPeriod = report.period.type;
  const dateInput = document.getElementById("productivityOverviewDate");
  if (dateInput && report?.date) dateInput.value = report.date;
  updateProductivityOverviewDateDisplay();
  updateProductivityOverviewPeriodControls();
  const dates = availableProductivityOverviewDates();
  if (dateInput && dates.length > 1) {
    dateInput.min = dates[0];
    dateInput.max = dates[dates.length - 1];
  }
  updateProductivityOverviewDateNav();

  const cutoffMinute = completedProductivityOverviewCutoffMinute(report?.date);
  productivityOverviewRoot = buildProductivityOverviewTree(report);
  productivityOverviewNodeIndex = indexProductivityOverviewTree(productivityOverviewRoot);
  productivityOverviewFocusId = "root";
  renderProductivityOverviewSummary(productivityOverviewRoot, report);
  renderProductivityOverviewTree();

  const status = document.getElementById("productivityOverviewStatus");
  const updated = formatProductivityOverviewTimestamp(report?.generated_at);
  const periodText = productivityOverviewPeriodLabel(report);
  const dataDays = report?.period?.days_with_data ?? productivityOverviewReports(report).length;
  const requestedDays = report?.period?.requested_days ?? dataDays;
  const daysText = requestedDays > 1 ? ` · ${dataDays}/${requestedDays} dagar` : "";
  const sync = report?.sync || {};
  const syncText = sync?.last_sync_at ? ` · API-sync ${formatProductivityOverviewTimestamp(sync.last_sync_at)}` : "";
  if (status) status.textContent = `${periodText}${daysText}${updated ? ` · uppdaterad ${updated}` : ""}${syncText}`;
  const warningText = productivityOverviewSourceWarnings(report).join(" · ");
  if (status && warningText) status.textContent = `${status.textContent} · ${warningText}`;
}

async function fetchProductivityOverviewReport(dateValue = "") {
  const params = new URLSearchParams();
  if (dateValue) params.set("date", dateValue);
  params.set("period", productivityOverviewPeriodValue());
  const query = params.toString() ? `?${params.toString()}` : "";
  const url = `/api/productivity/overview${query}`;
  const cached = productivityOverviewReportCache.get(url);
  if (cached && cached.expiresAt > Date.now()) return cached.data;
  productivityOverviewReportCache.delete(url);
  const data = await api.get(url, { cacheTtlMs: PRODUCTIVITY_OVERVIEW_CACHE_TTL_MS });
  productivityOverviewReportCache.set(url, {
    data,
    expiresAt: Date.now() + PRODUCTIVITY_OVERVIEW_CACHE_TTL_MS,
  });
  return data;
}

async function shiftProductivityOverviewDate(direction) {
  const input = document.getElementById("productivityOverviewDate");
  if (!input) return;
  const next = adjacentProductivityOverviewDate(direction);
  if (!next || next === input.value) return;
  input.value = next;
  updateProductivityOverviewDateDisplay();
  updateProductivityOverviewDateNav();
  await loadProductivityOverview();
}

function productivityOverviewStreamParams(dateValue) {
  const params = new URLSearchParams();
  if (dateValue) params.set("date", dateValue);
  params.set("period", productivityOverviewPeriodValue());
  return params;
}

function renderProductivityOverviewProgress(state) {
  const el = document.getElementById("productivityOverviewProgress");
  if (!el) return;
  if (!state) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  const items = [...state.steps.values()].sort((a, b) => a.step - b.step);
  const completedValues = items
    .map((item) => Number(item.completed))
    .filter((value) => Number.isFinite(value));
  const currentStep = completedValues.length
    ? Math.max(...completedValues)
    : items.reduce((max, item) => Math.max(max, item.step), 0);
  // En månad = 30+ steg; visa bara de senaste raderna så loggen inte svämmar över.
  const recent = items.slice(-6);
  const rows = recent
    .map((item) => {
      const done = Boolean(item.done);
      const icon = done ? "✓" : "⟳";
      return `<li class="${done ? "is-done" : "is-active"}"><span class="fetch-progress-icon">${icon}</span>${escapeHtml(item.label)}</li>`;
    })
    .join("");
  el.hidden = false;
  el.innerHTML = `
    <div class="fetch-progress-head">Hämtar produktivitet… <strong>${Math.min(currentStep, state.total)}/${state.total}</strong></div>
    <ul class="fetch-progress-list">${rows}</ul>
  `;
}

function applyProductivityOverviewReport(report, loadToken, options = {}) {
  if (loadToken !== productivityOverviewLoadToken) return;
  if (options.cacheUrl) {
    productivityOverviewReportCache.set(options.cacheUrl, {
      data: report,
      expiresAt: Date.now() + PRODUCTIVITY_OVERVIEW_CACHE_TTL_MS,
    });
  }
  renderProductivityOverviewProgress(null);
  renderProductivityOverviewReport(report);
}

function handleProductivityOverviewError(error, loadToken) {
  if (loadToken !== productivityOverviewLoadToken) return;
  renderProductivityOverviewProgress(null);
  productivityOverviewReport = null;
  productivityOverviewRoot = null;
  productivityOverviewNodeIndex = new Map();
  const summary = document.getElementById("productivityOverviewSummary");
  const tree = document.getElementById("productivityOverviewTree");
  const breadcrumbs = document.getElementById("productivityOverviewBreadcrumbs");
  const status = document.getElementById("productivityOverviewStatus");
  if (summary) summary.innerHTML = "";
  if (breadcrumbs) breadcrumbs.innerHTML = "";
  if (tree) tree.innerHTML = '<div class="empty-state">Produktivitet kunde inte hämtas.</div>';
  const detail = error?.message ? ` (${error.message})` : "";
  if (status) status.textContent = `Produktivitet kunde inte hämtas${detail}`;
  if (typeof showToast === "function") {
    showToast(status?.textContent || "Produktivitet kunde inte hämtas", "error", 7000);
  }
}

async function loadProductivityOverviewViaFetch(loadToken) {
  setProductivityOverviewLoading("Hämtar produktivitetsöversikt...");
  try {
    await waitForProductivityOverviewPaint();
    const report = await fetchProductivityOverviewReport(productivityOverviewDateValue());
    if (loadToken !== productivityOverviewLoadToken) return;
    setProductivityOverviewLoading("Beräknar och ritar produktivitet...");
    await waitForProductivityOverviewPaint();
    applyProductivityOverviewReport(report, loadToken);
  } catch (error) {
    handleProductivityOverviewError(error, loadToken);
  } finally {
    if (loadToken === productivityOverviewLoadToken) clearProductivityOverviewLoading();
  }
}

function loadProductivityOverviewViaStream(loadToken) {
  const dateValue = productivityOverviewDateValue();
  const cacheUrl = `/api/productivity/overview?${productivityOverviewStreamParams(dateValue).toString()}`;
  const cached = productivityOverviewReportCache.get(cacheUrl);
  if (cached && cached.expiresAt > Date.now()) {
    setProductivityOverviewLoading("Ritar produktivitet...");
    applyProductivityOverviewReport(cached.data, loadToken);
    clearProductivityOverviewLoading();
    return;
  }
  setProductivityOverviewLoading("Hämtar produktivitetsöversikt...");
  const progressState = { total: 2, steps: new Map() };
  renderProductivityOverviewProgress(progressState);
  const source = new EventSource(`/api/productivity/overview/stream?${productivityOverviewStreamParams(dateValue).toString()}`);
  productivityOverviewEventSource = source;
  let settled = false;
  const detach = () => {
    if (productivityOverviewEventSource === source) productivityOverviewEventSource = null;
  };
  source.onmessage = (event) => {
    if (loadToken !== productivityOverviewLoadToken) {
      settled = true;
      source.close();
      detach();
      return;
    }
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    if (data.type === "start") {
      progressState.total = Number(data.total) || progressState.total;
      renderProductivityOverviewProgress(progressState);
    } else if (data.type === "progress") {
      progressState.total = Number(data.total) || progressState.total;
      progressState.steps.set(Number(data.step), data);
      renderProductivityOverviewProgress(progressState);
    } else if (data.type === "done") {
      settled = true;
      source.close();
      detach();
      applyProductivityOverviewReport(data.payload, loadToken, { cacheUrl });
      clearProductivityOverviewLoading();
    } else if (data.type === "error") {
      settled = true;
      source.close();
      detach();
      handleProductivityOverviewError(new Error(data.message || "Okänt fel"), loadToken);
      clearProductivityOverviewLoading();
    }
  };
  source.onerror = () => {
    if (settled) return;
    settled = true;
    source.close();
    detach();
    // Strömmen gick inte att etablera – fall tillbaka på vanlig GET.
    void loadProductivityOverviewViaFetch(loadToken);
  };
}

function loadProductivityOverview() {
  const loadToken = ++productivityOverviewLoadToken;
  closeProductivityOverviewContextMenu();
  if (productivityOverviewEventSource) {
    productivityOverviewEventSource.close();
    productivityOverviewEventSource = null;
  }
  if (typeof EventSource === "undefined") {
    return loadProductivityOverviewViaFetch(loadToken);
  }
  return loadProductivityOverviewViaStream(loadToken);
}

async function initProductivityOverviewPage() {
  renderProductivityOverviewShell();
  productivityOverviewUser = await initPage("productivity");
  if (!productivityOverviewUser) return;
  const input = document.getElementById("productivityOverviewDate");
  if (input && !input.value) input.value = localProductivityOverviewIsoDate();
  updateProductivityOverviewDateDisplay();
  updateProductivityOverviewPeriodControls();
  document.querySelectorAll(".productivity-overview-period-toggle button[data-period]").forEach((button) => {
    if (["week", "month", "year"].includes(button.dataset.period)) {
      button.title = "Vänsterklick: byt period · Högerklick: välj specifik";
    }
    button.addEventListener("click", () => {
      const nextPeriod = button.dataset.period || "day";
      if (nextPeriod === productivityOverviewPeriod) return;
      productivityOverviewPeriod = nextPeriod;
      updateProductivityOverviewPeriodControls();
      updateProductivityOverviewDateNav();
      void loadProductivityOverview();
    });
    button.addEventListener("contextmenu", (event) => {
      const period = button.dataset.period || "day";
      if (!["week", "month", "year"].includes(period)) return;
      event.preventDefault();
      const input = document.getElementById("productivityOverviewDate");
      window.flowPeriodPicker?.open({
        period,
        anchorEl: button,
        currentIso: productivityOverviewDateValue(),
        onPick: (iso) => {
          if (input) input.value = iso;
          productivityOverviewPeriod = period;
          updateProductivityOverviewDateDisplay();
          updateProductivityOverviewPeriodControls();
          updateProductivityOverviewDateNav();
          void loadProductivityOverview();
        },
      });
    });
  });
  document.getElementById("productivityOverviewPrevDate")?.addEventListener("click", () => {
    void shiftProductivityOverviewDate(-1);
  });
  document.getElementById("productivityOverviewNextDate")?.addEventListener("click", () => {
    void shiftProductivityOverviewDate(1);
  });
  document.getElementById("productivityOverviewRootBtn")?.addEventListener("click", () => {
    focusProductivityOverviewNode("root");
  });
  document.getElementById("productivityOverviewExportFlowchart")?.addEventListener("click", exportProductivityOverviewFlowchart);
  input?.addEventListener("change", () => {
    updateProductivityOverviewDateDisplay();
    void loadProductivityOverview();
  });
  const overviewTree = document.getElementById("productivityOverviewTree");
  overviewTree?.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-node-id]");
    if (!button) return;
    focusProductivityOverviewNode(button.getAttribute("data-node-id"));
  });
  overviewTree?.addEventListener("contextmenu", (event) => {
    const target = event.target.closest?.("[data-node-id]");
    if (!target) return;
    const node = productivityOverviewNodeIndex.get(target.getAttribute("data-node-id"));
    if (!node || node.type !== "business") return;
    event.preventDefault();
    openProductivityOverviewContextMenu(event, node);
  });
  document.addEventListener("click", (event) => {
    if (event.target.closest?.("[data-productivity-overview-context-menu]")) return;
    closeProductivityOverviewContextMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeProductivityOverviewContextMenu();
  });
  document.getElementById("productivityOverviewBreadcrumbs")?.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-node-id]");
    if (!button) return;
    focusProductivityOverviewNode(button.getAttribute("data-node-id"));
  });
  void loadProductivityOverview();
}

document.addEventListener("DOMContentLoaded", () => {
  void initProductivityOverviewPage();
});

// @ts-check
// Utdelad ur productivity_overview.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter productivity_overview.js via <script>-tagg.

function productivityOverviewTypeLabel(type) {
  return {
    business: "Verksamhet",
    area: "Område",
    activity: "Aktivitet",
    person: "Person",
    hour: "Timme",
    process: "Process",
  }[type] || "";
}

function productivityOverviewChildSummary(node) {
  const count = node.children?.length || 0;
  if (!count) return `${formatProductivityOverviewNumber(node.eventCount, 0)} händelser`;
  const unit = {
    business: "områden",
    area: "aktiviteter",
    activity: "personer",
    person: "timmar",
    hour: "processer",
  }[node.type] || "grenar";
  return `${count} ${unit}`;
}

function productivityOverviewAncestors(node) {
  const path = [];
  let current = node;
  while (current) {
    path.unshift(current);
    current = productivityOverviewNodeIndex.get(current.parentId);
  }
  return path;
}

function renderProductivityOverviewBreadcrumbs(focusNode) {
  const target = document.getElementById("productivityOverviewBreadcrumbs");
  if (!target || !focusNode) return;
  const path = productivityOverviewAncestors(focusNode);
  target.innerHTML = path.map((node, index) => `
    <button type="button" class="${node.id === focusNode.id ? "active" : ""}" data-node-id="${escapeHtml(node.id)}">
      ${escapeHtml(index === 0 ? "Helbild" : node.label)}
    </button>
  `).join("");
}

function renderProductivityOverviewNodeMetric(node) {
  if (node?.type === "process") {
    return `<span class="productivity-overview-node-points">${escapeHtml(formatProductivityOverviewPoints(node.points))}</span>`;
  }
  const rate = productivityOverviewPointsPerHour(node);
  const scoreClass = productivityOverviewScoreClass(rate);
  return `
    <span class="productivity-overview-node-formula">
      <span>${escapeHtml(formatProductivityOverviewPoints(node.points))}</span>
      <span>/</span>
      <span>${escapeHtml(formatProductivityOverviewHours(node.workMinutes))}</span>
      <span>=</span>
    </span>
    <span class="productivity-overview-node-rate ${escapeHtml(scoreClass)}">${escapeHtml(formatProductivityOverviewRate(rate))}</span>
  `;
}

function productivityOverviewNodeHasFinance(node) {
  if (!node?.financeVisible) return false;
  return node.type === "business"
    || Number(node.financeWorkMinutes || 0) > 0
    || Math.abs(Number(node.financeRevenue || 0)) > 0.001
    || Math.abs(Number(node.financeCost || 0)) > 0.001
    || Math.abs(Number(node.financeResult || 0)) > 0.001;
}

function productivityOverviewFinanceResultClass(value) {
  const number = Number(value || 0);
  if (number > 0.001) return "good";
  if (number < -0.001) return "low";
  return "";
}

function renderProductivityOverviewFinance(node) {
  if (!productivityOverviewNodeHasFinance(node)) return "";
  const currency = node.financeCurrency || "SEK";
  return `
    <span class="productivity-overview-node-finance">
      <span>Intäkt ${escapeHtml(formatProductivityOverviewMoney(node.financeRevenue, currency))}</span>
      <span>Utgift ${escapeHtml(formatProductivityOverviewMoney(node.financeCost, currency))}</span>
      <span class="${escapeHtml(productivityOverviewFinanceResultClass(node.financeResult))}">Resultat ${escapeHtml(formatProductivityOverviewMoney(node.financeResult, currency))}</span>
    </span>
  `;
}

function renderProductivityOverviewNodeButton(node, options = {}) {
  const canFocus = Boolean(node.children?.length) && !options.staticNode;
  const tag = canFocus ? "button" : "div";
  const attrs = canFocus
    ? `type="button" data-node-id="${escapeHtml(node.id)}"`
    : (options.staticNode ? `data-node-id="${escapeHtml(node.id)}"` : "");
  return `
    <${tag} class="productivity-overview-node ${escapeHtml(node.type)}${canFocus ? " is-clickable" : ""}" ${attrs}>
      <span class="productivity-overview-node-type">${escapeHtml(productivityOverviewTypeLabel(node.type))}</span>
      <strong>${escapeHtml(node.label)}</strong>
      ${renderProductivityOverviewNodeMetric(node)}
      ${renderProductivityOverviewFinance(node)}
      <small>${escapeHtml(productivityOverviewChildSummary(node))}</small>
    </${tag}>
  `;
}

function renderProductivityOverviewProcessList(hourNode) {
  if (!hourNode.children?.length) return "";
  return `
    <div class="productivity-overview-process-list">
      ${hourNode.children.map((processNode) => `
        <div class="productivity-overview-process-row">
          <span>${escapeHtml(processNode.label)}</span>
          <strong>${escapeHtml(formatProductivityOverviewPoints(processNode.points))}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function renderProductivityOverviewPersonHours(personNode) {
  if (!personNode.children?.length) {
    return '<div class="empty-state">Inga processpoäng inom avslutad timme.</div>';
  }
  return `
    <div class="productivity-overview-branches productivity-overview-hours" data-parent-type="person">
      ${personNode.children.map((hourNode) => `
        <article class="productivity-overview-branch productivity-overview-hour-card">
          ${renderProductivityOverviewNodeButton(hourNode)}
          ${renderProductivityOverviewProcessList(hourNode)}
        </article>
      `).join("")}
    </div>
  `;
}

function renderProductivityOverviewBranches(node) {
  if (!node.children?.length) {
    return '<div class="empty-state">Inga poäng att visa inom avslutad timme.</div>';
  }
  if (node.type === "person") return renderProductivityOverviewPersonHours(node);
  return `
    <div class="productivity-overview-branches" data-parent-type="${escapeHtml(node.type)}">
      ${node.children.map((child) => `
        <div class="productivity-overview-branch">
          ${renderProductivityOverviewNodeButton(child)}
        </div>
      `).join("")}
    </div>
  `;
}

function renderProductivityOverviewSummary(root, report) {
  const target = document.getElementById("productivityOverviewSummary");
  if (!target) return;
  const rootRate = productivityOverviewPointsPerHour(root);
  const rootScoreClass = productivityOverviewScoreClass(rootRate);
  const periodText = productivityOverviewPeriodLabel(report);
  const areaCount = root.children.length;
  const activityCount = root.children.reduce((sum, area) => sum + area.children.length, 0);
  const personIds = new Set();
  for (const area of root.children) {
    for (const activity of area.children) {
      for (const person of activity.children) personIds.add(person.personId || person.label);
    }
  }
  const financeCards = root.financeVisible ? `
    <div class="productivity-kpi">
      <span>Intäkt</span>
      <strong>${escapeHtml(formatProductivityOverviewMoney(root.financeRevenue, root.financeCurrency))}</strong>
    </div>
    <div class="productivity-kpi">
      <span>Utgift</span>
      <strong>${escapeHtml(formatProductivityOverviewMoney(root.financeCost, root.financeCurrency))}</strong>
    </div>
    <div class="productivity-kpi">
      <span>Resultat</span>
      <strong class="${escapeHtml(productivityOverviewFinanceResultClass(root.financeResult))}">${escapeHtml(formatProductivityOverviewMoney(root.financeResult, root.financeCurrency))}</strong>
    </div>
  ` : "";
  target.innerHTML = `
    <div class="productivity-kpi">
      <span>Poäng / timmar</span>
      <strong class="productivity-overview-summary-rate ${escapeHtml(rootScoreClass)}">${escapeHtml(formatProductivityOverviewRate(rootRate))}</strong>
      <small class="productivity-overview-summary-formula">${escapeHtml(formatProductivityOverviewPoints(root.points))} / ${escapeHtml(formatProductivityOverviewHours(root.workMinutes))}</small>
    </div>
    ${financeCards}
    <div class="productivity-kpi">
      <span>Områden</span>
      <strong>${formatProductivityOverviewNumber(areaCount, 0)}</strong>
    </div>
    <div class="productivity-kpi">
      <span>Aktiviteter</span>
      <strong>${formatProductivityOverviewNumber(activityCount, 0)}</strong>
    </div>
    <div class="productivity-kpi">
      <span>Personer</span>
      <strong>${formatProductivityOverviewNumber(personIds.size, 0)}</strong>
    </div>
    <div class="productivity-kpi">
      <span>Period</span>
      <strong>${escapeHtml(periodText)}</strong>
    </div>
  `;
}

function renderProductivityOverviewShell() {
  const input = document.getElementById("productivityOverviewDate");
  if (input && !/** @type {HTMLInputElement} */ (input).value) /** @type {HTMLInputElement} */ (input).value = localProductivityOverviewIsoDate();
  updateProductivityOverviewDateDisplay();
  updateProductivityOverviewPeriodControls();
  updateProductivityOverviewDateNav();

  const summary = document.getElementById("productivityOverviewSummary");
  if (summary && !summary.innerHTML.trim()) {
    summary.innerHTML = `
      <div class="productivity-kpi"><span>Poäng / timmar</span><strong>-</strong></div>
      <div class="productivity-kpi"><span>Områden</span><strong>-</strong></div>
      <div class="productivity-kpi"><span>Aktiviteter</span><strong>-</strong></div>
      <div class="productivity-kpi"><span>Personer</span><strong>-</strong></div>
      <div class="productivity-kpi"><span>Period</span><strong>${escapeHtml(productivityOverviewPeriodDisplayLabel(/** @type {HTMLInputElement} */ (input)?.value || ""))}</strong></div>
    `;
  }

  const tree = document.getElementById("productivityOverviewTree");
  if (tree && !tree.innerHTML.trim()) {
    tree.innerHTML = '<div class="empty-state">Produktivitet hämtas i bakgrunden.</div>';
  }

  const status = document.getElementById("productivityOverviewStatus");
  if (status && !status.textContent.trim()) status.textContent = "Redo att hämta produktivitet.";
}

function setProductivityOverviewLoading(message) {
  const status = document.getElementById("productivityOverviewStatus");
  const summary = document.getElementById("productivityOverviewSummary");
  const tree = document.getElementById("productivityOverviewTree");
  const breadcrumbs = document.getElementById("productivityOverviewBreadcrumbs");
  if (status) status.textContent = message;
  summary?.setAttribute("aria-busy", "true");
  tree?.setAttribute("aria-busy", "true");
  if (tree) {
    if (productivityOverviewRoot) {
      tree.classList.add("is-changing");
    } else {
      tree.innerHTML = '<div class="empty-state">Produktivitet hämtas i bakgrunden.</div>';
    }
  }
  if (breadcrumbs && !productivityOverviewRoot) breadcrumbs.innerHTML = "";
}

function clearProductivityOverviewLoading() {
  document.getElementById("productivityOverviewSummary")?.removeAttribute("aria-busy");
  const tree = document.getElementById("productivityOverviewTree");
  tree?.removeAttribute("aria-busy");
  tree?.classList.remove("is-changing");
}

function renderProductivityOverviewTree() {
  const target = document.getElementById("productivityOverviewTree");
  if (!target || !productivityOverviewRoot) return;
  const focusNode = productivityOverviewNodeIndex.get(productivityOverviewFocusId) || productivityOverviewRoot;
  productivityOverviewFocusId = focusNode.id;
  renderProductivityOverviewBreadcrumbs(focusNode);
  target.classList.add("is-changing");
  target.innerHTML = `
    <section class="productivity-overview-camera" data-focus-type="${escapeHtml(focusNode.type)}">
      <div class="productivity-overview-root">
        ${renderProductivityOverviewNodeButton(focusNode, { staticNode: true })}
      </div>
      ${renderProductivityOverviewBranches(focusNode)}
    </section>
  `;
  window.requestAnimationFrame?.(() => target.classList.remove("is-changing"));
}

function closeProductivityOverviewContextMenu() {
  productivityOverviewContextMenu?.remove();
  productivityOverviewContextMenu = null;
}

function positionProductivityOverviewContextMenu(menu, x, y) {
  const margin = 8;
  const rect = menu.getBoundingClientRect();
  const left = Math.max(margin, Math.min(x, window.innerWidth - rect.width - margin));
  const top = Math.max(margin, Math.min(y, window.innerHeight - rect.height - margin));
  positionElementAtViewportPoint(menu, left, top);
}

function openProductivityOverviewContextMenu(event, node) {
  closeProductivityOverviewContextMenu();
  if (!node || node.type !== "business") return;
  const canOpenSankeyInbound = typeof canViewPage === "function" && canViewPage(productivityOverviewUser, "sankeyInbound");
  const menu = document.createElement("div");
  menu.className = "productivity-overview-context-menu";
  menu.dataset.productivityOverviewContextMenu = "true";
  menu.innerHTML = `
    <button type="button" data-productivity-business-summary>
      Summering
    </button>
    ${canOpenSankeyInbound ? `
      <button type="button" data-productivity-sankey-inbound>
        Sankey - Inbound
      </button>
    ` : ""}
  `;
  menu.querySelector("[data-productivity-business-summary]")?.addEventListener("click", () => {
    closeProductivityOverviewContextMenu();
    void openProductivityBusinessSummaryDialog(node);
  });
  menu.querySelector("[data-productivity-sankey-inbound]")?.addEventListener("click", () => {
    closeProductivityOverviewContextMenu();
    const params = productivityOverviewSelectionParams(productivityOverviewDateValue());
    const query = params.toString() ? `?${params.toString()}` : "";
    if (typeof flowTrack === "function") {
      flowTrack("navigate", {
        control_id: "productivity-context-sankey-inbound",
        view: "productivity",
        target_view: "sankeyInbound",
        period: productivityOverviewPeriodValue(),
      });
    }
    window.location.href = `/sankey-inbound.html${query}`;
  });
  document.body.appendChild(menu);
  positionProductivityOverviewContextMenu(menu, event.clientX, event.clientY);
  productivityOverviewContextMenu = menu;
  menu.querySelector("button")?.focus({ preventScroll: true });
}

function productivityOverviewSelectionParams(dateValue = productivityOverviewDateValue()) {
  const params = new URLSearchParams();
  if (dateValue) params.set("date", dateValue);
  params.set("period", productivityOverviewPeriodValue());
  if (productivityOverviewReport?.period?.type === "custom") {
    if (productivityOverviewReport.period.start_date) params.set("start_date", productivityOverviewReport.period.start_date);
    if (productivityOverviewReport.period.end_date) params.set("end_date", productivityOverviewReport.period.end_date);
  }
  return params;
}

async function fetchProductivityBusinessSummary() {
  const params = productivityOverviewSelectionParams(productivityOverviewDateValue());
  const query = params.toString() ? `?${params.toString()}` : "";
  return api.get(`/api/productivity/overview/business-summary${query}`, {
    cacheTtlMs: PRODUCTIVITY_OVERVIEW_CACHE_TTL_MS,
  });
}

function productivityBusinessSummaryPeriodText(payload) {
  const period = payload?.period || productivityOverviewReport?.period || {};
  const label = period.label || productivityOverviewPeriodDisplayLabel(productivityOverviewDateValue());
  const start = period.start_date || productivityOverviewDateValue();
  const end = period.end_date || start;
  return start && end && start !== end ? `${label} ${start} - ${end}` : `${label} ${start || ""}`.trim();
}

function productivityBusinessSummaryMoney(value, currency, visible) {
  return visible ? formatProductivityOverviewMoney(value, currency) : "-";
}

function renderProductivityBusinessSummaryDialogContent(backdrop, payload) {
  const body = backdrop.querySelector("[data-productivity-business-summary-body]");
  if (!body) return;
  const rows = Array.isArray(payload?.companies) ? payload.companies : [];
  const totals = payload?.totals || {};
  const currency = payload?.currency || totals.currency || "SEK";
  const financeVisible = payload?.finance_visible !== false;
  const periodText = productivityBusinessSummaryPeriodText(payload);
  const moneyClass = (value) => escapeHtml(productivityOverviewFinanceResultClass(value));
  const financeNote = financeVisible ? "" : `
    <p class="productivity-overview-summary-note">Ekonomi visas inte för din behörighet.</p>
  `;
  const rowHtml = rows.length ? rows.map((row) => `
    <tr>
      <th scope="row">${escapeHtml(row.company_label || row.company || "Okänt bolag")}</th>
      <td>${escapeHtml(productivityBusinessSummaryMoney(row.revenue, currency, financeVisible))}</td>
      <td>${escapeHtml(productivityBusinessSummaryMoney(row.cost, currency, financeVisible))}</td>
      <td class="${moneyClass(row.result)}">${escapeHtml(productivityBusinessSummaryMoney(row.result, currency, financeVisible))}</td>
      <td>${escapeHtml(formatProductivityOverviewNumber(row.zero_pick_rows || 0, 0))}</td>
    </tr>
  `).join("") : `
    <tr>
      <td colspan="5" class="empty-cell">Inga rader för valt urval.</td>
    </tr>
  `;
  body.innerHTML = `
    <div class="productivity-overview-summary-meta">
      <span>${escapeHtml(periodText)}</span>
      <span>${escapeHtml(formatProductivityOverviewNumber(payload?.period?.days_with_data || 0, 0))}/${escapeHtml(formatProductivityOverviewNumber(payload?.period?.requested_days || 0, 0))} dagar</span>
    </div>
    ${financeNote}
    <div class="productivity-overview-summary-table-wrap">
      <table class="productivity-overview-summary-table">
        <thead>
          <tr>
            <th scope="col">Bolag</th>
            <th scope="col">Intäkt</th>
            <th scope="col">Kostnad</th>
            <th scope="col">Resultat</th>
            <th scope="col">Nollade rader</th>
          </tr>
        </thead>
        <tbody>${rowHtml}</tbody>
        <tfoot>
          <tr>
            <th scope="row">Totalt</th>
            <td>${escapeHtml(productivityBusinessSummaryMoney(totals.revenue, currency, financeVisible))}</td>
            <td>${escapeHtml(productivityBusinessSummaryMoney(totals.cost, currency, financeVisible))}</td>
            <td class="${moneyClass(totals.result)}">${escapeHtml(productivityBusinessSummaryMoney(totals.result, currency, financeVisible))}</td>
            <td>${escapeHtml(formatProductivityOverviewNumber(totals.zero_pick_rows || 0, 0))}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  `;
}

function renderProductivityBusinessSummaryDialogError(backdrop, error) {
  const body = backdrop.querySelector("[data-productivity-business-summary-body]");
  if (!body) return;
  const detail = error?.message ? ` (${error.message})` : "";
  body.innerHTML = `<div class="empty-state">Summering kunde inte hämtas${escapeHtml(detail)}.</div>`;
}

function closeProductivityBusinessSummaryDialog(backdrop, onKeydown) {
  document.removeEventListener("keydown", onKeydown);
  backdrop?.remove();
}

async function openProductivityBusinessSummaryDialog(node) {
  document.querySelector("[data-productivity-business-summary-dialog]")?.remove();
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.dataset.productivityBusinessSummaryDialog = "true";
  backdrop.innerHTML = `
    <div class="modal productivity-overview-summary-modal" role="dialog" aria-modal="true" aria-labelledby="productivityBusinessSummaryTitle">
      <div class="productivity-overview-summary-modal-head">
        <div>
          <h2 id="productivityBusinessSummaryTitle">Summering</h2>
          <p>${escapeHtml(node?.label || productivityOverviewRoot?.label || "Verksamhet")}</p>
        </div>
        <button type="button" class="productivity-overview-summary-close" aria-label="Stäng" title="Stäng" data-productivity-business-summary-close>×</button>
      </div>
      <div data-productivity-business-summary-body>
        <div class="empty-state">Hämtar summering...</div>
      </div>
      <div class="actions">
        <button type="button" data-productivity-business-summary-close>Stäng</button>
      </div>
    </div>
  `;
  const onKeydown = (event) => {
    if (event.key === "Escape") closeProductivityBusinessSummaryDialog(backdrop, onKeydown);
  };
  document.addEventListener("keydown", onKeydown);
  backdrop.querySelectorAll("[data-productivity-business-summary-close]").forEach((button) => {
    button.addEventListener("click", () => closeProductivityBusinessSummaryDialog(backdrop, onKeydown));
  });
  document.body.appendChild(backdrop);
  /** @type {HTMLElement} */ (backdrop.querySelector("[data-productivity-business-summary-close]"))?.focus({ preventScroll: true });
  try {
    const payload = await fetchProductivityBusinessSummary();
    renderProductivityBusinessSummaryDialogContent(backdrop, payload);
  } catch (error) {
    renderProductivityBusinessSummaryDialogError(backdrop, error);
    if (typeof showToast === "function") showToast("Summering kunde inte hämtas.", "error", 5000);
  }
}

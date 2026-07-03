function layoutSankeyNodes(nodes, width, height) {
  const groups = new Map();
  for (const node of nodes) {
    const stage = Number(node.stage || 0);
    if (!groups.has(stage)) groups.set(stage, []);
    groups.get(stage).push(node);
  }
  const stages = [...groups.keys()].sort((a, b) => a - b);
  const stageIndex = new Map(stages.map((stage, index) => [stage, index]));
  const nodeWidth = 14;
  const paddingX = width < 700 ? 34 : 64;
  const paddingY = height < 460 ? 44 : 58;
  const usableWidth = Math.max(180, width - paddingX * 2 - nodeWidth);
  const usableHeight = Math.max(160, height - paddingY * 2);
  const positions = new Map();
  for (const [stage, group] of groups) {
    group.sort((a, b) => Number(b.value || 0) - Number(a.value || 0) || String(a.label).localeCompare(String(b.label), "sv"));
    const x = paddingX + (stageIndex.get(stage) || 0) * (usableWidth / Math.max(1, stages.length - 1));
    for (const [index, node] of group.entries()) {
      const cy = group.length > 1
        ? paddingY + index * (usableHeight / (group.length - 1))
        : height / 2;
      positions.set(node.id, {
        x,
        y: cy - nodeWidth / 2,
        width: nodeWidth,
        height: nodeWidth,
        cy,
      });
    }
  }
  return positions;
}

function renderSankeyCombinedChart(payload) {
  const target = document.getElementById("sankeyInboundChart");
  if (!target) return;
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const links = Array.isArray(payload?.links) ? payload.links : [];
  if (!nodes.length) {
    target.innerHTML = '<div class="empty-state">Inget inboundunderlag i valt urval.</div>';
    return;
  }
  const width = Math.max(360, Math.floor(target.clientWidth || 920));
  const height = Math.max(360, Math.floor(target.clientHeight || 520));
  const positions = layoutSankeyNodes(nodes, width, height);
  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const currency = payload.currency || "SEK";
  const maxLink = Math.max(1, ...links.map((link) => Number(link.value || link.revenue || 0)));
  const linkSvg = links.map((link, index) => {
    const source = positions.get(link.source);
    const targetPos = positions.get(link.target);
    if (!source || !targetPos) return "";
    const stroke = Math.max(2, Math.min(44, (Number(link.value || 0) / maxLink) * 44));
    const x1 = source.x + source.width / 2 + 8;
    const x2 = targetPos.x + targetPos.width / 2 - 8;
    const y1 = source.cy;
    const y2 = targetPos.cy;
    const mid = Math.max(32, Math.abs(x2 - x1) * 0.48);
    const color = sankeyLinkColor(link, nodesById);
    const activeClass = sankeyInboundSelected?.type === "link" && sankeyInboundSelected?.index === index ? " is-active" : "";
    return `
      <path
        class="sankey-inbound-link${activeClass}"
        data-sankey-link-index="${index}"
        d="M ${x1} ${y1} C ${x1 + mid} ${y1}, ${x2 - mid} ${y2}, ${x2} ${y2}"
        stroke="${sankeyEscapeHtml(color)}"
        stroke-width="${stroke.toFixed(2)}"
      >
        <title>${sankeyEscapeHtml(sankeyFormatMoney(link.value, currency))} · ${sankeyEscapeHtml(sankeyFormatNumber(link.labels, 2))} ${sankeyEscapeHtml(sankeyFlowUnitLabel(link))} · etikett ${sankeyEscapeHtml(sankeyFormatMoney(link.label_revenue, currency))} · inköpsrad ${sankeyEscapeHtml(sankeyFormatMoney(link.purchase_line_revenue, currency))} · outbound ${sankeyEscapeHtml(sankeyFormatMoney(link.outbound_revenue, currency))}</title>
      </path>
    `;
  }).join("");
  const nodeSvg = nodes.map((node) => {
    const pos = positions.get(node.id);
    if (!pos) return "";
    const color = sankeyNodeColor(node);
    const cx = pos.x + pos.width / 2;
    const labelX = pos.x < width / 2 ? cx + 14 : cx - 14;
    const anchor = pos.x < width / 2 ? "start" : "end";
    const activeClass = sankeyInboundSelected?.type === "node" && sankeyInboundSelected?.id === node.id ? " is-active" : "";
    return `
      <g class="sankey-inbound-node${activeClass}" data-sankey-node-id="${sankeyEscapeHtml(node.id)}">
        <circle cx="${cx}" cy="${pos.cy}" r="6" fill="${sankeyEscapeHtml(color)}"></circle>
        <text x="${labelX}" y="${pos.cy - 4}" text-anchor="${anchor}" class="sankey-node-label">${sankeyEscapeHtml(node.label)}</text>
        <text x="${labelX}" y="${pos.cy + 13}" text-anchor="${anchor}" class="sankey-node-value">${sankeyEscapeHtml(sankeyNodePrimaryValue(node, currency))}</text>
        <title>${sankeyEscapeHtml(node.company)} · ${sankeyEscapeHtml(node.label)} · ${sankeyEscapeHtml(sankeyNodeTitleValue(node, currency))}</title>
      </g>
    `;
  }).join("");
  target.innerHTML = `
    <svg class="sankey-inbound-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Sankey - Inbound">
      <rect width="${width}" height="${height}" fill="transparent"></rect>
      <g class="sankey-inbound-links">${linkSvg}</g>
      <g class="sankey-inbound-nodes">${nodeSvg}</g>
    </svg>
  `;
  target.querySelectorAll("[data-sankey-node-id]").forEach((nodeEl) => {
    nodeEl.addEventListener("click", () => {
      sankeyInboundSelected = { type: "node", id: nodeEl.getAttribute("data-sankey-node-id") };
      renderSankeyChart(sankeyInboundPayload);
      renderSankeyDetail();
    });
  });
  target.querySelectorAll("[data-sankey-link-index]").forEach((linkEl) => {
    linkEl.addEventListener("click", () => {
      sankeyInboundSelected = { type: "link", index: Number(linkEl.getAttribute("data-sankey-link-index") || 0) };
      renderSankeyChart(sankeyInboundPayload);
      renderSankeyDetail();
    });
  });
}

function sankeyIsOutboundNode(node) {
  return String(node?.type || "").startsWith("outbound");
}

function sankeySplitMaps(payload) {
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const links = Array.isArray(payload?.links) ? payload.links : [];
  const inboundNodes = nodes.filter((node) => !sankeyIsOutboundNode(node));
  const outboundNodes = nodes.filter(sankeyIsOutboundNode);
  const inboundIds = new Set(inboundNodes.map((node) => node.id));
  const outboundIds = new Set(outboundNodes.map((node) => node.id));
  const indexedLinks = links.map((link, index) => ({ link, index }));
  return {
    inbound: {
      nodes: inboundNodes,
      links: indexedLinks.filter(({ link }) => inboundIds.has(link.source) && inboundIds.has(link.target)),
    },
    outbound: {
      nodes: outboundNodes,
      links: indexedLinks.filter(({ link }) => outboundIds.has(link.source) && outboundIds.has(link.target)),
    },
  };
}

function renderSankeyMapSvg(payload, map, options) {
  const nodes = Array.isArray(map?.nodes) ? map.nodes : [];
  const linkEntries = Array.isArray(map?.links) ? map.links : [];
  if (!nodes.length) {
    return `<div class="empty-state">${sankeyEscapeHtml(options.emptyText)}</div>`;
  }
  const width = options.width;
  const height = options.height;
  const positions = layoutSankeyNodes(nodes, width, height);
  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const currency = payload.currency || "SEK";
  const maxLink = Math.max(1, ...linkEntries.map(({ link }) => Number(link.value || link.revenue || 0)));
  const linkSvg = linkEntries.map(({ link, index }) => {
    const source = positions.get(link.source);
    const targetPos = positions.get(link.target);
    if (!source || !targetPos) return "";
    const stroke = Math.max(2, Math.min(44, (Number(link.value || 0) / maxLink) * 44));
    const x1 = source.x + source.width / 2 + 8;
    const x2 = targetPos.x + targetPos.width / 2 - 8;
    const y1 = source.cy;
    const y2 = targetPos.cy;
    const mid = Math.max(32, Math.abs(x2 - x1) * 0.48);
    const color = sankeyLinkColor(link, nodesById);
    const activeClass = sankeyInboundSelected?.type === "link" && sankeyInboundSelected?.index === index ? " is-active" : "";
    return `
      <path
        class="sankey-inbound-link${activeClass}"
        data-sankey-link-index="${index}"
        d="M ${x1} ${y1} C ${x1 + mid} ${y1}, ${x2 - mid} ${y2}, ${x2} ${y2}"
        stroke="${sankeyEscapeHtml(color)}"
        stroke-width="${stroke.toFixed(2)}"
      >
        <title>${sankeyEscapeHtml(sankeyFormatMoney(link.value, currency))} · ${sankeyEscapeHtml(sankeyFormatNumber(link.labels, 2))} ${sankeyEscapeHtml(sankeyFlowUnitLabel(link))} · etikett ${sankeyEscapeHtml(sankeyFormatMoney(link.label_revenue, currency))} · inköpsrad ${sankeyEscapeHtml(sankeyFormatMoney(link.purchase_line_revenue, currency))} · outbound ${sankeyEscapeHtml(sankeyFormatMoney(link.outbound_revenue, currency))}</title>
      </path>
    `;
  }).join("");
  const nodeSvg = nodes.map((node) => {
    const pos = positions.get(node.id);
    if (!pos) return "";
    const color = sankeyNodeColor(node);
    const cx = pos.x + pos.width / 2;
    const labelX = pos.x < width / 2 ? cx + 14 : cx - 14;
    const anchor = pos.x < width / 2 ? "start" : "end";
    const activeClass = sankeyInboundSelected?.type === "node" && sankeyInboundSelected?.id === node.id ? " is-active" : "";
    return `
      <g class="sankey-inbound-node${activeClass}" data-sankey-node-id="${sankeyEscapeHtml(node.id)}">
        <circle cx="${cx}" cy="${pos.cy}" r="6" fill="${sankeyEscapeHtml(color)}"></circle>
        <text x="${labelX}" y="${pos.cy - 4}" text-anchor="${anchor}" class="sankey-node-label">${sankeyEscapeHtml(node.label)}</text>
        <text x="${labelX}" y="${pos.cy + 13}" text-anchor="${anchor}" class="sankey-node-value">${sankeyEscapeHtml(sankeyNodePrimaryValue(node, currency))}</text>
        <title>${sankeyEscapeHtml(node.company)} · ${sankeyEscapeHtml(node.label)} · ${sankeyEscapeHtml(sankeyNodeTitleValue(node, currency))}</title>
      </g>
    `;
  }).join("");
  return `
    <svg class="sankey-inbound-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${sankeyEscapeHtml(options.ariaLabel)}">
      <rect width="${width}" height="${height}" fill="transparent"></rect>
      <g class="sankey-inbound-links">${linkSvg}</g>
      <g class="sankey-inbound-nodes">${nodeSvg}</g>
    </svg>
  `;
}

function renderSankeyChart(payload) {
  const target = document.getElementById("sankeyInboundChart");
  if (!target) return;
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  if (!nodes.length) {
    target.innerHTML = '<div class="empty-state">Inget inboundunderlag i valt urval.</div>';
    return;
  }
  const currency = payload.currency || "SEK";
  const width = Math.max(360, Math.floor(target.clientWidth || 920));
  const baseHeight = Math.max(760, Math.floor(target.clientHeight || 820));
  const split = sankeySplitMaps(payload);
  const inboundHeight = Math.max(360, Math.floor(baseHeight * 0.56));
  const outboundHeight = Math.max(260, Math.floor(baseHeight * 0.32));
  target.innerHTML = `
    <section class="sankey-flow-map sankey-flow-map-inbound" aria-label="Inbound-karta">
      <div class="sankey-flow-map-head">
        <h2>Inbound</h2>
        <span>${sankeyEscapeHtml(sankeyFormatMoney(payload?.summary?.inbound_income ?? payload?.summary?.gross_income, currency))}</span>
      </div>
      ${renderSankeyMapSvg(payload, split.inbound, {
        width,
        height: inboundHeight,
        ariaLabel: "Sankey - Inbound",
        emptyText: "Inget inboundunderlag i valt urval.",
      })}
    </section>
    <section class="sankey-flow-map sankey-flow-map-outbound" aria-label="Outbound-karta">
      <div class="sankey-flow-map-head">
        <h2>Outbound</h2>
        <span>${sankeyEscapeHtml(sankeyFormatMoney(payload?.summary?.outbound_income, currency))}</span>
      </div>
      ${renderSankeyMapSvg(payload, split.outbound, {
        width,
        height: outboundHeight,
        ariaLabel: "Sankey - Outbound",
        emptyText: "Inget outboundunderlag i valt urval.",
      })}
    </section>
  `;
  target.querySelectorAll("[data-sankey-node-id]").forEach((nodeEl) => {
    nodeEl.addEventListener("click", () => {
      sankeyInboundSelected = { type: "node", id: nodeEl.getAttribute("data-sankey-node-id") };
      renderSankeyChart(sankeyInboundPayload);
      renderSankeyDetail();
    });
  });
  target.querySelectorAll("[data-sankey-link-index]").forEach((linkEl) => {
    linkEl.addEventListener("click", () => {
      sankeyInboundSelected = { type: "link", index: Number(linkEl.getAttribute("data-sankey-link-index") || 0) };
      renderSankeyChart(sankeyInboundPayload);
      renderSankeyDetail();
    });
  });
}

function renderSankeyDetail() {
  const target = document.getElementById("sankeyInboundDetail");
  if (!target) return;
  const payload = sankeyInboundPayload || {};
  const currency = payload.currency || "SEK";
  const trace = selectedSankeyTraceScope();
  const tracePreview = renderSankeyTracePlaceholder(trace);
  let html = "";
  if (sankeyInboundSelected?.type === "node") {
    const node = (payload.nodes || []).find((item) => item.id === sankeyInboundSelected.id);
    if (node) {
      if (node.type === "terminal") {
        html = `
          <h2>${sankeyEscapeHtml(node.label)}</h2>
          <dl>
            <div><dt>Bolag</dt><dd>${sankeyEscapeHtml(node.company)}</dd></div>
            <div><dt>Statuspott</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(node.value, currency))}</dd></div>
            ${sankeyRevenueBreakdownRows(node, currency)}
            <div><dt>${sankeyEscapeHtml(sankeyFlowUnitLabel(node))}</dt><dd>${sankeyEscapeHtml(sankeyFormatNumber(node.labels, 2))}</dd></div>
          </dl>
          ${tracePreview}
        `;
      } else if (node.type === "source") {
        html = `
          <h2>${sankeyEscapeHtml(node.label)}</h2>
          <dl>
            <div><dt>Bolag</dt><dd>${sankeyEscapeHtml(node.company)}</dd></div>
            <div><dt>Gross income</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(node.value, currency))}</dd></div>
            ${sankeyRevenueBreakdownRows(node, currency)}
            <div><dt>${sankeyEscapeHtml(sankeyFlowUnitLabel(node))}</dt><dd>${sankeyEscapeHtml(sankeyFormatNumber(node.labels, 2))}</dd></div>
          </dl>
          ${tracePreview}
        `;
      } else {
        html = `
          <h2>${sankeyEscapeHtml(node.label)}</h2>
          <dl>
            <div><dt>Bolag</dt><dd>${sankeyEscapeHtml(node.company)}</dd></div>
            <div><dt>Genomflöde</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(node.value, currency))}</dd></div>
            <div><dt>Processintäkt</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(node.revenue, currency))}</dd></div>
            ${sankeyRevenueBreakdownRows(node, currency)}
            <div><dt>${sankeyEscapeHtml(sankeyFlowUnitLabel(node))}</dt><dd>${sankeyEscapeHtml(sankeyFormatNumber(node.labels, 2))}</dd></div>
            <div><dt>Poäng</dt><dd>${sankeyEscapeHtml(sankeyFormatNumber(node.points, 2))}</dd></div>
          </dl>
          ${tracePreview}
        `;
      }
    }
  }
  if (!html && sankeyInboundSelected?.type === "link") {
    const link = (payload.links || [])[sankeyInboundSelected.index];
    const nodes = new Map((payload.nodes || []).map((node) => [node.id, node]));
    if (link) {
      html = `
        <h2>Flöde</h2>
        <p>${sankeyEscapeHtml(nodes.get(link.source)?.label || link.source)} → ${sankeyEscapeHtml(nodes.get(link.target)?.label || link.target)}</p>
        <dl>
          <div><dt>Bolag</dt><dd>${sankeyEscapeHtml(link.company)}</dd></div>
          <div><dt>Flödespott</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(link.value, currency))}</dd></div>
          ${sankeyRevenueBreakdownRows(link, currency)}
          <div><dt>${sankeyEscapeHtml(sankeyFlowUnitLabel(link))}</dt><dd>${sankeyEscapeHtml(sankeyFormatNumber(link.labels, 2))}</dd></div>
        </dl>
        ${tracePreview}
      `;
    }
  }
  if (!html) {
    const summary = payload.summary || {};
    html = `
      <h2>Urval</h2>
      <dl>
        <div><dt>Gross income</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(summary.gross_income, currency))}</dd></div>
        <div><dt>Inbound</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(summary.inbound_income ?? summary.gross_income, currency))}</dd></div>
        <div><dt>Outbound</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(summary.outbound_income, currency))}</dd></div>
        <div><dt>Etikettintäkt</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(summary.gross_income_labels, currency))}</dd></div>
        <div><dt>Inköpsradsintäkt</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(summary.gross_income_purchase_lines, currency))}</dd></div>
        <div><dt>Etiketter</dt><dd>${sankeyEscapeHtml(sankeyFormatNumber(summary.labels_received))}</dd></div>
        <div><dt>Inköpsrader</dt><dd>${sankeyEscapeHtml(sankeyFormatNumber(summary.purchase_lines_received))}</dd></div>
        <div><dt>Outbound orders</dt><dd>${sankeyEscapeHtml(sankeyFormatNumber(summary.outbound_picked_orders))}</dd></div>
        <div><dt>Grenar</dt><dd>${sankeyEscapeHtml(sankeyFormatNumber(summary.branches))}</dd></div>
        <div><dt>Ofördelad intäkt</dt><dd>${sankeyEscapeHtml(sankeyFormatMoney(summary.unallocated_revenue, currency))}</dd></div>
      </dl>
      ${tracePreview}
    `;
  }
  target.innerHTML = html;
  void hydrateSankeyTracePreview(trace);
}

function renderSankeyProcessTable(payload) {
  const target = document.getElementById("sankeyInboundProcessTable");
  if (!target) return;
  const rows = Array.isArray(payload?.processes) ? payload.processes : [];
  const outboundRows = Array.isArray(payload?.outbound_metrics) ? payload.outbound_metrics : [];
  const currency = payload?.currency || "SEK";
  const body = rows.length ? rows.map((row) => `
    <tr>
      <td>${sankeyEscapeHtml(row.company)}</td>
      <th scope="row">${sankeyEscapeHtml(row.label)}</th>
      <td>${sankeyEscapeHtml(sankeyFormatMoney(row.revenue, currency))}</td>
      <td>${sankeyEscapeHtml(sankeyFormatMoney(row.label_revenue, currency))}</td>
      <td>${sankeyEscapeHtml(sankeyFormatMoney(row.purchase_line_revenue, currency))}</td>
      <td>${sankeyEscapeHtml(sankeyFormatNumber(row.points, 2))}</td>
      <td>${sankeyEscapeHtml(sankeyFormatNumber(row.labels, 2))}</td>
      <td>${sankeyEscapeHtml(sankeyFormatNumber((row.share || 0) * 100, 1))}%</td>
    </tr>
  `).join("") : '<tr><td colspan="8" class="empty-cell">Inga processintäkter i valt urval.</td></tr>';
  const outboundBody = outboundRows.length ? outboundRows.map((row) => `
    <tr>
      <td>${sankeyEscapeHtml(row.company)}</td>
      <td>${sankeyEscapeHtml(row.branch_label)}</td>
      <th scope="row">${sankeyEscapeHtml(row.label)}</th>
      <td>${sankeyEscapeHtml(sankeyFormatNumber(row.count, 2))}</td>
      <td>${sankeyEscapeHtml(row.unit || "st")}</td>
      <td>${sankeyEscapeHtml(sankeyFormatMoney(row.price, currency))}</td>
      <td>${sankeyEscapeHtml(sankeyFormatMoney(row.revenue, currency))}</td>
    </tr>
  `).join("") : '<tr><td colspan="7" class="empty-cell">Inga outboundrader i valt urval.</td></tr>';
  target.innerHTML = `
    <h2>Processintäkt</h2>
    <table class="productivity-overview-summary-table">
      <thead>
        <tr>
          <th scope="col">Bolag</th>
          <th scope="col">Process</th>
          <th scope="col">Intäkt</th>
          <th scope="col">Etikettintäkt</th>
          <th scope="col">Inköpsradsintäkt</th>
          <th scope="col">Poäng</th>
          <th scope="col">Etiketter</th>
          <th scope="col">Andel</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>
    <h2>Outbound</h2>
    <table class="productivity-overview-summary-table">
      <thead>
        <tr>
          <th scope="col">Bolag</th>
          <th scope="col">Gren</th>
          <th scope="col">Rad</th>
          <th scope="col">Antal</th>
          <th scope="col">Enhet</th>
          <th scope="col">Pris</th>
          <th scope="col">Intäkt</th>
        </tr>
      </thead>
      <tbody>${outboundBody}</tbody>
    </table>
  `;
}

function renderSankeyWarnings(payload) {
  const target = document.getElementById("sankeyInboundWarnings");
  if (!target) return;
  const warnings = Array.isArray(payload?.warnings) ? payload.warnings : [];
  if (!warnings.length) {
    target.innerHTML = "";
    return;
  }
  target.innerHTML = `
    <h2>Varningar</h2>
    <ul>
      ${warnings.slice(0, 12).map((warning) => `<li>${sankeyEscapeHtml(sankeyDisplayText(warning.message || warning.code || "Varning"))}</li>`).join("")}
    </ul>
  `;
}

function renderSankeyPayload(payload, options = {}) {
  sankeyInboundPayload = payload;
  if (options.updateCompanyOptions !== false) updateSankeyCompanyOptions(payload);
  renderSankeySummary(payload);
  renderSankeyChart(payload);
  renderSankeyDetail();
  renderSankeyProcessTable(payload);
  renderSankeyWarnings(payload);
  const status = document.getElementById("sankeyInboundStatus");
  const period = payload?.period || {};
  const cache = payload?.cache?.status === "hit" ? " · cache" : "";
  const clientFilter = payload?.cache?.client_filter ? " · lokalt filter" : "";
  const warnings = Array.isArray(payload?.warnings) && payload.warnings.length ? ` · ${payload.warnings.length} varningar` : "";
  const timing = payload?.timing
    ? ` · hämtning ${sankeyFormatNumber(payload.timing.fetch_ms)} ms · bygge ${sankeyFormatNumber(payload.timing.build_ms)} ms`
    : "";
  if (status) {
    status.textContent = `${period.label || ""} ${period.start_date || ""} - ${period.end_date || ""} · följer till ${period.follow_until || ""}${cache}${clientFilter}${timing}${warnings}`.trim();
  }
}

function sankeyStreamParams() {
  const params = new URLSearchParams();
  params.set("period", sankeyInboundPeriod);
  params.set("date", sankeyDateValue());
  params.set("client_schema", SANKEY_INBOUND_CLIENT_SCHEMA);
  const company = sankeyCompanyValue();
  if (company && company !== "ALL") params.set("company", company);
  if (sankeyInboundOnlyConsumed) params.set("only_consumed", "true");
  return params;
}

function renderSankeyProgress(state) {
  const el = document.getElementById("sankeyInboundProgress");
  if (!el) return;
  if (!state) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  const items = [...state.steps.values()].sort((a, b) => a.step - b.step);
  const currentStep = items.reduce((max, item) => Math.max(max, item.step), 0);
  const rows = items
    .map((item) => {
      const done = Boolean(item.done);
      const icon = done ? "✓" : "⟳";
      const rowsText = done && Number.isFinite(Number(item.rows))
        ? ` <span class="fetch-progress-rows">(${sankeyFormatNumber(item.rows)} rader)</span>`
        : "";
      return `<li class="${done ? "is-done" : "is-active"}"><span class="fetch-progress-icon">${icon}</span>${sankeyEscapeHtml(item.label)}${rowsText}</li>`;
    })
    .join("");
  el.hidden = false;
  el.innerHTML = `
    <div class="fetch-progress-head">Hämtar Sankey - Inbound… <strong>${Math.min(currentStep, state.total)}/${state.total}</strong></div>
    <ul class="fetch-progress-list">${rows}</ul>
  `;
}

function handleSankeyLoaded(payload) {
  renderSankeyProgress(null);
  sankeyInboundBasePayload = payload;
  updateSankeyCompanyOptions(payload);
  renderSankeyCurrentView();
  if (typeof flowTrack === "function") {
    flowTrack("filter", {
      control_id: "sankey-inbound-load",
      view: "sankeyInbound",
      period: sankeyInboundPeriod,
      company: sankeyCompanyValue(),
      only_consumed: sankeyInboundOnlyConsumed,
    });
  }
}

function sankeySourceStatusSummary(sourceStatus) {
  const failed = Array.isArray(sourceStatus) ? sourceStatus.filter((item) => item?.status === "error") : [];
  if (!failed.length) return "";
  return failed
    .map((item) => {
      const segment = item.segment ? ` [${item.segment}]` : "";
      const span = item.start ? ` ${item.start}–${item.end || ""}` : "";
      return `${item.key || "?"}/${item.view || "?"}${segment}${span}`;
    })
    .join("; ");
}

function clearSankeyReportAfterError(detail, sourceStatus) {
  sankeyInboundBasePayload = null;
  sankeyInboundPayload = null;
  sankeyInboundSelected = null;
  const summary = document.getElementById("sankeyInboundSummary");
  if (summary) summary.innerHTML = "";
  const chart = document.getElementById("sankeyInboundChart");
  if (chart) chart.innerHTML = '<div class="empty-state">Sankey - Inbound kunde inte hämtas.</div>';
  const detailEl = document.getElementById("sankeyInboundDetail");
  if (detailEl) {
    detailEl.innerHTML = `
      <h2>Urval</h2>
      <div class="empty-state">Ingen rapport laddad.</div>
    `;
  }
  const processTable = document.getElementById("sankeyInboundProcessTable");
  if (processTable) processTable.innerHTML = "";
  const warnings = Array.isArray(sourceStatus) && sourceStatus.length
    ? sourceStatus
        .filter((item) => item?.status === "error")
        .map((item) => ({ message: item.message || `${item.key || "Källa"} / ${item.view || "vy"} kunde inte hämtas.` }))
    : [{ message: detail }];
  renderSankeyWarnings({ warnings });
}

function handleSankeyLoadError(error, sourceStatus) {
  renderSankeyProgress(null);
  const detail = error?.message || "Okänt fel";
  setSankeyStatus(`Sankey - Inbound kunde inte hämtas (${detail})`, false);
  clearSankeyReportAfterError(detail, sourceStatus);
  // Logga full detalj (vilken källa/vy/period som failade) till app-loggen.
  if (typeof appendAppLog === "function") {
    const sources = sankeySourceStatusSummary(sourceStatus);
    appendAppLog(sources ? `${detail} · källor: ${sources}` : detail, "error", "Sankey - Inbound");
  }
  // Visa detaljen i toasten men logga inte igen (vi loggade redan ovan).
  if (typeof showToast === "function") {
    showToast(`Sankey - Inbound kunde inte hämtas: ${detail}`, "error", 9000, { log: false });
  }
  document.getElementById("sankeyInboundChart")?.removeAttribute("aria-busy");
}

async function loadSankeyInboundFallback() {
  sankeyInboundTriedClientFilterRefresh = false;
  setSankeyStatus("Hämtar Sankey - Inbound...", true);
  try {
    const payload = await fetchSankeyInboundPayload();
    handleSankeyLoaded(payload);
  } catch (error) {
    handleSankeyLoadError(error);
  } finally {
    document.getElementById("sankeyInboundChart")?.removeAttribute("aria-busy");
  }
}

function loadSankeyInbound() {
  sankeyInboundTriedClientFilterRefresh = false;
  if (typeof EventSource === "undefined") {
    void loadSankeyInboundFallback();
    return;
  }
  setSankeyStatus("Hämtar Sankey - Inbound...", true);
  const progressState = { total: 7, steps: new Map() };
  renderSankeyProgress(progressState);
  const source = new EventSource(`/api/sankey/inbound/stream?${sankeyStreamParams().toString()}`);
  let settled = false;
  source.onmessage = (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    if (data.type === "start") {
      progressState.total = Number(data.total) || progressState.total;
      renderSankeyProgress(progressState);
    } else if (data.type === "progress") {
      progressState.total = Number(data.total) || progressState.total;
      progressState.steps.set(Number(data.step), data);
      renderSankeyProgress(progressState);
    } else if (data.type === "done") {
      settled = true;
      source.close();
      document.getElementById("sankeyInboundChart")?.removeAttribute("aria-busy");
      handleSankeyLoaded(data.payload);
    } else if (data.type === "error") {
      settled = true;
      source.close();
      document.getElementById("sankeyInboundChart")?.removeAttribute("aria-busy");
      handleSankeyLoadError(new Error(data.message || "Okänt fel"), data.source_status);
    }
  };
  source.onerror = () => {
    if (settled) return;
    settled = true;
    source.close();
    // Strömmen gick inte att etablera (t.ex. proxy utan SSE) – fall tillbaka på vanlig GET.
    void loadSankeyInboundFallback();
  };
}

function exportSankeySvg() {
  const svgs = [...document.querySelectorAll(".sankey-inbound-svg")];
  if (!svgs.length) {
    if (typeof showToast === "function") showToast("Det finns inget Sankeydiagram att exportera.", "warn", 4000);
    return;
  }
  const parts = svgs.map((svg) => {
    const viewBox = String(svg.getAttribute("viewBox") || "").split(/\s+/).map(Number);
    const width = Number.isFinite(viewBox[2]) ? viewBox[2] : Math.max(360, svg.clientWidth || 920);
    const height = Number.isFinite(viewBox[3]) ? viewBox[3] : Math.max(260, svg.clientHeight || 360);
    const title = svg.closest(".sankey-flow-map")?.querySelector("h2")?.textContent || "Sankey";
    return { width, height, title, inner: svg.innerHTML };
  });
  const gap = 36;
  const titleHeight = 28;
  const width = Math.max(360, ...parts.map((part) => part.width));
  let cursor = 0;
  const body = parts.map((part) => {
    const y = cursor;
    cursor += titleHeight + part.height + gap;
    return `
      <text x="12" y="${y + 18}" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#0f172a">${sankeyEscapeHtml(part.title)}</text>
      <g transform="translate(0 ${y + titleHeight})">${part.inner}</g>
    `;
  }).join("");
  const height = Math.max(1, cursor - gap);
  const content = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Sankey - Inbound och Outbound">${body}</svg>`;
  const blob = new Blob([content], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `sankey-inbound-${sankeyInboundPeriod}-${sankeyDateValue()}.svg`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  if (typeof showToast === "function") showToast("Sankey exporterad.", "success", 3000);
  if (typeof flowTrack === "function") {
    flowTrack("download", {
      control_id: "sankey-inbound-export-svg",
      view: "sankeyInbound",
      period: sankeyInboundPeriod,
    });
  }
}

async function initSankeyInboundPage() {
  const params = new URLSearchParams(window.location.search || "");
  sankeyInboundPeriod = ["day", "week", "month", "year"].includes(params.get("period")) ? params.get("period") : "day";
  sankeyInboundUser = await initPage("sankeyInbound");
  if (!sankeyInboundUser) return;
  const input = document.getElementById("sankeyInboundDate");
  if (input) input.value = params.get("date") || sankeyLocalIsoDate();
  const company = params.get("company");
  if (company) document.getElementById("sankeyInboundCompany").value = company.toUpperCase();
  updateSankeyDateDisplay();
  updateSankeyControls();
  document.querySelectorAll("[data-sankey-period]").forEach((button) => {
    if (["week", "month", "year"].includes(button.dataset.sankeyPeriod)) {
      button.title = "Vänsterklick: byt period · Högerklick: välj specifik";
    }
    button.addEventListener("click", () => {
      const next = button.dataset.sankeyPeriod || "day";
      if (next === sankeyInboundPeriod) return;
      sankeyInboundPeriod = next;
      sankeyInboundSelected = null;
      updateSankeyControls();
      applySankeyFilterChange("sankey-inbound-period");
    });
    button.addEventListener("contextmenu", (event) => {
      const period = button.dataset.sankeyPeriod || "day";
      if (!["week", "month", "year"].includes(period)) return;
      event.preventDefault();
      window.flowPeriodPicker?.open({
        period,
        anchorEl: button,
        currentIso: sankeyDateValue(),
        onPick: (iso) => {
          if (input) input.value = iso;
          sankeyInboundPeriod = period;
          sankeyInboundSelected = null;
          updateSankeyDateDisplay();
          updateSankeyControls();
          applySankeyFilterChange("sankey-inbound-period-picker");
        },
      });
    });
  });
  input?.addEventListener("change", () => {
    sankeyInboundSelected = null;
    updateSankeyDateDisplay();
    applySankeyFilterChange("sankey-inbound-date");
  });
  document.getElementById("sankeyInboundPrevDate")?.addEventListener("click", () => {
    if (!input) return;
    input.value = sankeyShiftDate(input.value, -1, sankeyInboundPeriod);
    sankeyInboundSelected = null;
    updateSankeyDateDisplay();
    applySankeyFilterChange("sankey-inbound-prev-date");
  });
  document.getElementById("sankeyInboundNextDate")?.addEventListener("click", () => {
    if (!input) return;
    input.value = sankeyShiftDate(input.value, 1, sankeyInboundPeriod);
    sankeyInboundSelected = null;
    updateSankeyDateDisplay();
    applySankeyFilterChange("sankey-inbound-next-date");
  });
  document.getElementById("sankeyInboundCompany")?.addEventListener("change", () => {
    sankeyInboundSelected = null;
    applySankeyFilterChange("sankey-inbound-company");
  });
  document.getElementById("sankeyInboundOnlyConsumed")?.addEventListener("click", () => {
    sankeyInboundOnlyConsumed = !sankeyInboundOnlyConsumed;
    sankeyInboundSelected = null;
    updateSankeyControls();
    applySankeyFilterChange("sankey-inbound-only-consumed");
  });
  document.getElementById("sankeyInboundReset")?.addEventListener("click", () => {
    sankeyInboundSelected = null;
    renderSankeyChart(sankeyInboundPayload);
    renderSankeyDetail();
  });
  document.getElementById("sankeyInboundExport")?.addEventListener("click", exportSankeySvg);
  document.getElementById("sankeyInboundExportTraceAll")?.addEventListener("click", exportAllSankeyTraceRows);
  document.getElementById("sankeyInboundDetail")?.addEventListener("click", (event) => {
    const targetEl = event.target instanceof Element ? event.target : event.target?.parentElement;
    const button = targetEl?.closest("[data-sankey-export-traces]");
    if (!button) return;
    exportSankeyTraceRows();
  });
  window.addEventListener("resize", () => {
    if (sankeyInboundPayload) renderSankeyChart(sankeyInboundPayload);
  });
  void loadSankeyInbound();
}

document.addEventListener("DOMContentLoaded", () => {
  void initSankeyInboundPage();
});

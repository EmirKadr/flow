function allocationFollowUpFlows(flowId) {
  if (!flowId) return [];
  return allocationState.visibleFlows.filter((flow) => flow?.requiresSessionFlow?.flowId === flowId);
}

function renderResultFollowUpActions(data) {
  const followUps = allocationFollowUpFlows(data?.flow_id);
  const clusterAction = data?.flow_id === "forecast" && allocationHasCarrierClusters(data)
    ? `<button type="button" data-edit-carrier-clusters>Redigera kluster</button>`
    : "";
  if (!followUps.length && !clusterAction) return "";
  return `
    <div class="allocation-result-actions">
      ${clusterAction}
      ${followUps.map((flow) => {
        const missing = missingForFlow(flow);
        const ready = missing.length === 0 && !allocationState.busyId;
        const missingText = allocationMissingRequirementText(missing);
        return `
          <button
            type="button"
            class="primary"
            data-follow-up-flow="${allocationEscape(flow.id)}"
            ${ready ? "" : "disabled"}
            ${missingText ? `title="${allocationEscape(missingText)}"` : ""}
          >Kör ${allocationEscape(flow.label)}</button>
          ${missingText ? `<span class="allocation-follow-up-note">${allocationEscape(missingText)}</span>` : ""}
        `;
      }).join("")}
    </div>
  `;
}

function renderFlowFileList(flow) {
  const fileInputs = (flow?.inputs || []).filter((input) => input.type === "file");
  const coreInputs = flow?.coredata || [];
  const sessionRequirement = flow?.requiresSessionFlow;
  if (!fileInputs.length && !coreInputs.length && !sessionRequirement) return "";
  return `
    <div class="allocation-flow-files">
      ${fileInputs.map((input) => {
        const key = allocationFileInputKey(input);
        const apiReady = input.apiPreferred && !allocationSourceUsesUpload(flow.id, key, input);
        const entry = apiReady ? null : allocationState.files[key];
        const persistentEntry = apiReady || entry ? null : allocationPersistentDataFile(key);
        const displayEntry = apiReady ? null : entry || persistentEntry;
        const cls = displayEntry || apiReady ? "ok" : input.required ? "missing" : "optional";
        const prefix = displayEntry ? "✓" : input.required ? "✗" : "○";
        const suffix = persistentEntry
          ? ` (${allocationEscape(persistentEntry.suffixLabel || persistentEntry.badge.toLowerCase())})`
          : apiReady
            ? " (API)"
          : input.required || displayEntry ? "" : " (valfri)";
        return `
          <div class="allocation-flow-file ${displayEntry || apiReady ? "filled" : ""}">
            <span class="allocation-file-tag ${cls}">${apiReady ? "API" : prefix} ${allocationEscape(allocationSlotLabel(key))}${suffix}</span>
            <span>${displayEntry ? allocationEscape(displayEntry.name) : apiReady ? "H&auml;mtas fr&aring;n API" : "Ingen fil"}</span>
          </div>
        `;
      }).join("")}
      ${coreInputs.map((input) => {
        const apiReady = input.apiPreferred && !allocationSourceUsesUpload(flow.id, input.key, input);
        const entry = apiReady ? null : allocationPersistentStatusFile(input.key);
        const label = input.label || ALLOCATION_PERSISTENT_DATA_LABELS[input.key] || input.key;
        const cls = entry || apiReady ? "ok" : input.required ? "missing" : "optional";
        const prefix = entry ? "✓" : input.required ? "✗" : "○";
        const suffixLabel = allocationDataSuffixLabel(input.key, entry || {});
        return `
          <div class="allocation-flow-file ${entry || apiReady ? "filled" : ""}">
            <span class="allocation-file-tag ${cls}">${apiReady ? "API" : prefix} ${allocationEscape(label)} (${apiReady ? "API" : allocationEscape(suffixLabel)})</span>
            <span>${entry ? allocationEscape(entry.name) : apiReady ? "H&auml;mtas fr&aring;n API" : "Saknas"}</span>
          </div>
        `;
      }).join("")}
      ${sessionRequirement ? (() => {
        const sessionId = allocationRequiredSessionId(flow);
        const label = sessionRequirement.label || "Körning";
        return `
          <div class="allocation-flow-file ${sessionId ? "filled" : ""}">
            <span class="allocation-file-tag ${sessionId ? "ok" : "missing"}">${sessionId ? "✓" : "✗"} ${allocationEscape(label)} körd</span>
            <span>${sessionId ? allocationEscape(allocationState.lastForecastLabel || label) : `Kör ${allocationEscape(label)} först`}</span>
          </div>
        `;
      })() : ""}
    </div>
  `;
}

function renderFieldInputs(flow, extraClass = "") {
  const fields = (flow?.inputs || []).filter((input) => input.type !== "file");
  if (!fields.length) return "";
  return `
    <div class="allocation-fields ${allocationEscape(extraClass)}">
      ${fields.map((input) => `
        <label>
          <span>${allocationEscape(input.label)}${input.required ? " *" : ""}</span>
          ${input.type === "textarea"
            ? `<textarea data-flow-field="${allocationEscape(input.key)}" rows="8">${allocationEscape(allocationState.values[input.key] || "")}</textarea>`
            : `<input data-flow-field="${allocationEscape(input.key)}" type="${input.type === "number" ? "number" : "text"}" value="${allocationEscape(allocationState.values[input.key] ?? input.default ?? "")}" />`
          }
        </label>
      `).join("")}
    </div>
  `;
}

function bindFlowFields(root) {
  root.querySelectorAll("[data-flow-field]").forEach((input) => {
    input.addEventListener("input", () => {
      allocationState.values[input.dataset.flowField] = input.value;
      persistAllocationWorkState();
      refreshAllocationRunButtons(root);
    });
  });
}

function allocationTrack(eventType, details = {}) {
  if (typeof window.flowTrack !== "function") return "";
  const data = allocationState.result?.data || {};
  return window.flowTrack(eventType, {
    view_id: allocationPageActiveName(allocationState.page || "process"),
    feature: "allocation",
    flow_id: details.flow_id || details.flowId || data.flow_id || allocationState.busyId || "",
    status: details.status || "ok",
    table_key: details.table_key || details.tableKey || "",
    table_label: details.table_label || details.tableLabel || "",
    column_index: Number.isInteger(details.column_index) ? details.column_index : Number.isInteger(details.columnIndex) ? details.columnIndex : null,
    column_label: details.column_label || details.columnLabel || "",
    row_count: Number.isFinite(Number(details.row_count ?? details.rowCount)) ? Number(details.row_count ?? details.rowCount) : null,
    control_id: details.control_id || details.controlId || "",
    control_label: details.control_label || details.controlLabel || "",
    interaction_id: details.interaction_id || details.interactionId || "",
    detail: {
      page: allocationState.page || "",
      area_focus: typeof window.readAreaFocus === "function" ? window.readAreaFocus() : "",
      session_id_present: Boolean(data.session_id),
      ...details.detail,
    },
  });
}

function allocationTableEventMeta(tableKey, columnIndex = null) {
  const data = allocationState.result?.data || {};
  const entry = (data.tables || []).find((item) => item.key === tableKey) || {};
  const table = entry.table || {};
  const columns = Array.isArray(table.columns) ? table.columns : [];
  const index = Number(columnIndex);
  return {
    table_key: tableKey || "",
    table_label: entry.label || tableKey || "",
    column_index: Number.isInteger(index) && index >= 0 ? index : null,
    column_label: Number.isInteger(index) && index >= 0 ? (columns[index] || "") : "",
    row_count: Number(table.row_count ?? table.rows?.length ?? 0) || 0,
  };
}

function refreshAllocationRunButtons(root) {
  root.querySelectorAll("[data-run-flow]").forEach((button) => {
    const flow = flowById(button.dataset.runFlow);
    const missing = missingForFlow(flow);
    button.disabled = Boolean(allocationState.busyId) || missing.length > 0;
    button.closest(".allocation-flow-chip")?.classList.toggle("ready", missing.length === 0);
  });
}

async function runAllocationFlow(flow) {
  if (!flow || allocationState.busyId) return;
  const missing = missingForFlow(flow);
  if (missing.length) {
    allocationTrack("flow_blocked_missing_inputs", {
      flow_id: flow.id,
      control_id: "allocation-flow-run",
      control_label: flow.label,
      status: "blocked",
      detail: { missing_count: missing.length, missing_labels: missing.map((item) => item.label || item.key || "") },
    });
    return;
  }
  const runInteractionId = allocationTrack("flow_run_start", {
    flow_id: flow.id,
    control_id: "allocation-flow-run",
    control_label: flow.label,
    detail: {
      input_count: (flow.inputs || []).length,
      file_slots: (flow.inputs || []).filter((input) => input.type === "file").map((input) => input.key),
      param_keys: (flow.inputs || []).filter((input) => input.type !== "file").map((input) => input.key),
    },
  });
  allocationState.busyId = flow.id;
  allocationState.status = flow.id === "split-values" ? "Delar värden..." : `Kör ${flow.label}...`;
  allocationState.result = null;
  persistAllocationWorkState({ status: "", result: null });
  renderAllocationPage();
  const fd = new FormData();
  if (allocationState.page === "process") {
    appendAllocationAreaFocus(fd);
  }
  appendAllocationFilterProfile(fd);
  if (flow.requiresSessionFlow?.flowId === "forecast") {
    fd.append("forecast_session_id", allocationState.lastForecastSessionId || "");
  }
  if (flow.id === "ytgenerering" && allocationState.carrierClusters?.rows?.length) {
    fd.append("carrier_clusters_json", JSON.stringify(allocationState.carrierClusters));
  }
  for (const input of flow.inputs || []) {
    if (input.type === "file") {
      const entry = allocationState.files[allocationFileInputKey(input)];
      appendAllocationFileField(fd, input.key, entry);
    } else {
      const value = allocationState.values[input.key] ?? input.default ?? "";
      if (value !== "") fd.append(input.key, value);
    }
  }
  try {
    const data = await allocationPostForm(`${ALLOCATION_API}/flow/${encodeURIComponent(flow.id)}`, fd);
    allocationState.result = { label: flow.label, data };
    if ((data.flow_id || flow.id) === "forecast" && data.session_id) {
      allocationState.lastForecastSessionId = data.session_id;
      allocationState.lastForecastLabel = `${flow.label} ${new Date().toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" })}`;
      allocationState.carrierClusters = normalizeAllocationCarrierClusters(data.carrier_clusters);
    }
    allocationState.status = `Klart: ${flow.label}`;
    allocationTrack("flow_run_success", {
      flow_id: data.flow_id || flow.id,
      control_id: "allocation-flow-run",
      control_label: flow.label,
      interaction_id: runInteractionId,
      detail: {
        table_count: Array.isArray(data.tables) ? data.tables.length : 0,
        has_session: Boolean(data.session_id),
        auto_downloads: Array.isArray(data.auto_downloads) ? data.auto_downloads.length : 0,
      },
    });
    await copyAutoFlowColumn(data);
    await downloadAllocationAutoDownloads(data);
  } catch (error) {
    allocationTrack("flow_run_error", {
      flow_id: flow.id,
      control_id: "allocation-flow-run",
      control_label: flow.label,
      interaction_id: runInteractionId,
      status: "error",
      detail: { error_type: error?.name || "Error", message: error?.message || "" },
    });
    showToast(error.message, "error");
    allocationState.status = "";
  } finally {
    allocationState.busyId = "";
    persistAllocationWorkState();
    renderAllocationPage();
  }
}

async function downloadAllocationAutoDownloads(data) {
  const downloads = Array.isArray(data?.auto_downloads) ? data.auto_downloads : [];
  const sessionId = data?.session_id;
  if (!downloads.length || !sessionId) return;
  for (const entry of downloads) {
    const key = entry?.key;
    if (!key) continue;
    const filename = entry?.filename || `${key}.csv`;
    try {
      allocationTrack("auto_download", {
        flow_id: data.flow_id || "",
        table_key: key,
        control_id: "allocation-auto-download",
        control_label: "Automatisk nedladdning",
        detail: { filename_extension: String(filename || "").split(".").pop() || "" },
      });
      await api.download(`${ALLOCATION_API}/download/${encodeURIComponent(sessionId)}/${encodeURIComponent(key)}`, filename);
    } catch (error) {
      allocationTrack("auto_download_error", {
        flow_id: data.flow_id || "",
        table_key: key,
        control_id: "allocation-auto-download",
        control_label: "Automatisk nedladdning",
        status: "error",
        detail: { error_type: error?.name || "Error", message: error?.message || "" },
      });
      showToast(error.message || "Kunde inte ladda ner importfilen automatiskt.", "error", 7000);
    }
  }
}

async function copyAutoFlowColumn(data) {
  const rule = ALLOCATION_AUTO_COPY_COLUMN_RULES[data?.flow_id];
  if (!rule) return;
  const targetTable = (data.tables || []).find((entry) => entry.key === rule.tableKey);
  const orderCount = Number(targetTable?.table?.row_count || 0);
  if (!data.session_id || !orderCount) {
    allocationTrack("auto_copy_column_empty", {
      flow_id: data?.flow_id || "",
      ...allocationTableEventMeta(rule.tableKey, 0),
      control_id: "allocation-auto-copy-column",
      control_label: "Automatisk kolumnkopiering",
      status: "empty",
    });
    showToast(rule.emptyToast, "info", 2500);
    return;
  }
  try {
    const columnData = await allocationJson(
      `${ALLOCATION_API}/table-column/${encodeURIComponent(data.session_id)}/${encodeURIComponent(rule.tableKey)}/0`,
    );
    await writeClipboardText(columnData.text || "");
    allocationTrack("auto_copy_column", {
      flow_id: data?.flow_id || "",
      ...allocationTableEventMeta(rule.tableKey, 0),
      control_id: "allocation-auto-copy-column",
      control_label: "Automatisk kolumnkopiering",
      detail: {
        copied_line_count: String(columnData.text || "").split("\n").filter(Boolean).length,
        copy_mode: "first_column",
      },
    });
    showToast(`${orderCount} ${rule.successLabel} kopierade`, "success", 2500);
  } catch (error) {
    allocationTrack("auto_copy_column_error", {
      flow_id: data?.flow_id || "",
      ...allocationTableEventMeta(rule.tableKey, 0),
      control_id: "allocation-auto-copy-column",
      control_label: "Automatisk kolumnkopiering",
      status: "error",
      detail: { error_type: error?.name || "Error", message: error?.message || "" },
    });
    showToast(error.message || rule.errorToast, "error", 7000);
  }
}

function allocationResultSummaryEntries(data) {
  const displaySummary = data.display_summary || null;
  const summary = displaySummary && Object.keys(displaySummary).length ? displaySummary : (data.summary || {});
  return Object.entries(summary);
}

function allocationResultTables(data) {
  return data.tables || [];
}

function allocationResultMaps(data) {
  return Array.isArray(data?.maps) ? data.maps : [];
}

function renderTextResult(text) {
  if (!text) return "";
  return `
    <div class="allocation-text-result-wrap">
      <pre class="allocation-text-result" data-result-text>${allocationEscape(text)}</pre>
      <button type="button" class="allocation-copy-text" data-copy-text-result aria-label="Kopiera text" title="Kopiera text">
        ${ALLOCATION_COPY_ICON}
      </button>
    </div>
  `;
}

function renderResultPanel(result) {
  if (!result?.data) return "";
  const data = result.data;
  const summaryEntries = allocationResultSummaryEntries(data);
  const maps = allocationResultMaps(data);
  const tables = allocationResultTables(data);
  const followUpActions = renderResultFollowUpActions(data);
  return `
    <section class="allocation-panel allocation-result">
      <div class="allocation-panel-head">
        <h2>Resultat - ${allocationEscape(result.label)}</h2>
        ${followUpActions}
      </div>
      ${summaryEntries.length ? `
        <div class="allocation-summary">
          ${summaryEntries.map(([key, value]) => `
            <div><span>${allocationEscape(key)}</span><strong>${allocationEscape(value)}</strong></div>
          `).join("")}
        </div>
      ` : ""}
      ${renderTextResult(data.text)}
      ${maps.map((entry, index) => renderResultMap(entry, index)).join("")}
      ${tables.map((entry) => renderResultTable(data.session_id, entry)).join("")}
      ${data.log?.length ? `<pre class="allocation-log">${allocationEscape(data.log.join("\n"))}</pre>` : ""}
    </section>
  `;
}

function renderResultMap(entry, index) {
  const locationCount = Array.isArray(entry?.locations) ? entry.locations.length : 0;
  const assignmentCount = Array.isArray(entry?.assignments) ? entry.assignments.length : 0;
  const missingCount = Array.isArray(entry?.unplaced) ? entry.unplaced.length : 0;
  return `
    <div class="allocation-map-block" data-allocation-map data-map-index="${index}" tabindex="0" aria-keyshortcuts="Control+C Control+X Control+V Control+Z">
      <div class="allocation-table-head allocation-map-head">
        <h3>${allocationEscape(entry?.label || "Ytkarta")} <span>${assignmentCount} placeringar / ${locationCount} ytor</span></h3>
        <div>
          <button type="button" data-map-fit>Återställ vy</button>
          <button type="button" data-map-rotate>Rotera</button>
          <button type="button" data-map-export-csv>Ladda ner karta CSV</button>
          <button type="button" data-map-export-ask>Ladda ner justerad ASK</button>
        </div>
      </div>
      <div class="allocation-warehouse-map">
        <div class="allocation-map-stage">
          <button type="button" class="allocation-map-missing-toggle${missingCount ? " has-missing" : ""}" data-map-missing aria-pressed="false">
            Saknade kunder${missingCount ? ` (${missingCount})` : ""}
          </button>
          <button type="button" class="allocation-map-fullscreen-button" data-map-fullscreen title="Fullskärm" aria-label="Fullskärm">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M8 4H4v4"></path>
              <path d="M4 4l6 6"></path>
              <path d="M16 4h4v4"></path>
              <path d="M20 4l-6 6"></path>
              <path d="M4 16v4h4"></path>
              <path d="M4 20l6-6"></path>
              <path d="M20 16v4h-4"></path>
              <path d="M20 20l-6-6"></path>
            </svg>
          </button>
          <div class="allocation-map-missing-panel" data-map-missing-panel hidden></div>
          <svg class="allocation-warehouse-map-svg" data-map-svg aria-label="${allocationEscape(entry?.label || "Ytkarta")}">
            <defs>
              <pattern data-map-grid id="allocation-map-grid-${index}" width="80" height="80" patternUnits="userSpaceOnUse">
                <path d="M 80 0 L 0 0 0 80" fill="none" stroke="#d8dee8" stroke-width="0.8"></path>
              </pattern>
            </defs>
            <g data-map-rotate-group>
              <rect width="100%" height="100%" fill="url(#allocation-map-grid-${index})"></rect>
              <g data-map-canvas></g>
            </g>
          </svg>
        </div>
        <aside class="allocation-map-side">
          <div class="allocation-map-metrics" data-map-metrics></div>
          <input class="allocation-map-search" type="search" data-map-search placeholder="Sök UTL, sändning eller transportör" />
          <div class="allocation-map-detail" data-map-detail></div>
          <div class="allocation-map-overview" data-map-overview></div>
        </aside>
      </div>
    </div>
  `;
}

function renderResultTable(sessionId, entry) {
  const table = entry.table || { columns: [], rows: [] };
  return `
    <div class="allocation-table-block">
      <div class="allocation-table-head">
        <h3>${allocationEscape(entry.label)} <span>${allocationEscape(table.row_count || 0)} rader</span></h3>
        <div>
          <button type="button" data-open-excel="${allocationEscape(entry.key)}">Öppna i Excel</button>
          <button type="button" class="button-like" data-download-csv="${allocationEscape(entry.key)}" data-download-label="${allocationEscape(entry.label || entry.key)}">Ladda ner CSV</button>
        </div>
      </div>
      <div class="table-wrap allocation-table-wrap">
        <table>
          <thead><tr>${(table.columns || []).map((column, index) => `
            <th>
              <div class="allocation-column-head">
                <span>${allocationEscape(column)}</span>
                <button type="button" class="allocation-copy-column" data-copy-column="${index}" data-copy-key="${allocationEscape(entry.key)}" data-copy-label="${allocationEscape(column)}" aria-label="Kopiera kolumn ${allocationEscape(column)}" title="Kopiera kolumn">
                  ${ALLOCATION_COPY_ICON}
                </button>
              </div>
            </th>
          `).join("")}</tr></thead>
          <tbody>
            ${(table.rows || []).slice(0, 100).map((row) => `<tr>${row.map((cell) => `<td>${allocationEscape(cell)}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table>
      </div>
      ${table.truncated ? `<p class="allocation-muted">Förhandsvisningen visar de första raderna.</p>` : ""}
    </div>
  `;
}

const ALLOCATION_MAP_NS = "http://www.w3.org/2000/svg";

function allocationMapNumber(value, fallback = 0) {
  const parsed = Number.parseFloat(String(value ?? "").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function allocationMapRound(value) {
  return Math.round(allocationMapNumber(value) * 100) / 100;
}

function allocationMapClamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function allocationMapShortLocation(value) {
  return String(value || "").trim().replace(/^UTL/i, "") || String(value || "").trim();
}

function allocationMapEstimatedTextWidth(text, fontSize) {
  return String(text || "").length * fontSize * 0.56;
}

function allocationMapSafeSvgId(value) {
  return String(value || "").replace(/[^a-zA-Z0-9_-]+/g, "-") || "item";
}

function allocationMapHexToRgb(value) {
  const raw = String(value || "").trim();
  const short = raw.match(/^#([0-9a-f]{3})$/i);
  const long = raw.match(/^#([0-9a-f]{6})$/i);
  const hex = short
    ? short[1].split("").map((part) => `${part}${part}`).join("")
    : long?.[1];
  if (!hex) return null;
  return {
    r: Number.parseInt(hex.slice(0, 2), 16),
    g: Number.parseInt(hex.slice(2, 4), 16),
    b: Number.parseInt(hex.slice(4, 6), 16),
  };
}

function allocationMapMixHexColor(color, target = "#ffffff", amount = 0.5) {
  const sourceRgb = allocationMapHexToRgb(color);
  const targetRgb = allocationMapHexToRgb(target);
  if (!sourceRgb || !targetRgb) return color || target;
  const ratio = allocationMapClamp(amount, 0, 1);
  const channel = (name) => Math.round(sourceRgb[name] * (1 - ratio) + targetRgb[name] * ratio)
    .toString(16)
    .padStart(2, "0");
  return `#${channel("r")}${channel("g")}${channel("b")}`;
}

function allocationMapLabelLines(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return [""];
  const words = text.split(" ");
  if (words.length < 2) return [text];
  let best = [text];
  let bestScore = Number.POSITIVE_INFINITY;
  for (let index = 1; index < words.length; index += 1) {
    const left = words.slice(0, index).join(" ");
    const right = words.slice(index).join(" ");
    const score = Math.max(left.length, right.length) * 2 + Math.abs(left.length - right.length);
    if (score < bestScore) {
      best = [left, right];
      bestScore = score;
    }
  }
  return best;
}

function allocationMapLocationSortValue(value) {
  const match = String(value || "").match(/^UTL(\d+)(.*)$/i);
  if (!match) return [Number.MAX_SAFE_INTEGER, String(value || "")];
  return [Number.parseInt(match[1], 10), match[2] || ""];
}

function allocationMapCompareLocation(a, b) {
  const left = allocationMapLocationSortValue(a);
  const right = allocationMapLocationSortValue(b);
  return left[0] - right[0] || left[1].localeCompare(right[1], "sv");
}

function allocationMapTsvCell(value) {
  return String(value ?? "").replace(/\t/g, " ").replace(/\r?\n/g, " ").trim();
}

function allocationDownloadText(filename, text, type = "text/csv;charset=utf-8") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function initializeAllocationResultMaps(root) {
  const maps = allocationResultMaps(allocationState.result?.data);
  root.querySelectorAll("[data-allocation-map]").forEach((host) => {
    const index = Number.parseInt(host.dataset.mapIndex || "0", 10);
    setupAllocationWarehouseMap(host, maps[index]);
  });
}

function setupAllocationWarehouseMap(host, entry) {
  const svg = host.querySelector("[data-map-svg]");
  const canvas = host.querySelector("[data-map-canvas]");
  const grid = host.querySelector("[data-map-grid]");
  const rotateGroup = host.querySelector("[data-map-rotate-group]");
  const metrics = host.querySelector("[data-map-metrics]");
  const detail = host.querySelector("[data-map-detail]");
  const overview = host.querySelector("[data-map-overview]");
  const search = host.querySelector("[data-map-search]");
  const missingToggle = host.querySelector("[data-map-missing]");
  const missingPanel = host.querySelector("[data-map-missing-panel]");
  if (!svg || !canvas || !entry) return;
  const defs = svg.querySelector("defs");

  const locations = (Array.isArray(entry.locations) ? entry.locations : [])
    .map((loc) => ({
      location: String(loc.location || "").trim().toUpperCase(),
      x: allocationMapNumber(loc.x),
      y: allocationMapNumber(loc.y),
      w: allocationMapNumber(loc.w, 1),
      h: allocationMapNumber(loc.h, 1),
      maxPall: allocationMapRound(loc.maxPall),
      loadDirection: allocationNormalizeMapLoadDirection(
        loc.loadDirection ?? loc.load_direction ?? loc.loadingDirection ?? loc.direction,
        loc,
      ),
    }))
    .filter((loc) => loc.location);
  locations.sort((a, b) => allocationMapCompareLocation(a.location, b.location));
  const locationByName = new Map(locations.map((loc) => [loc.location, loc]));
  const assignments = (Array.isArray(entry.assignments) ? entry.assignments : [])
    .map((assignment, index) => ({
      id: String(assignment.id || `assignment-${index}`),
      shipment: String(assignment.shipment || ""),
      carrier: String(assignment.carrier || "Okänd"),
      cluster: String(assignment.cluster || ""),
      customer: String(assignment.customer || ""),
      customerNum: String(assignment.customerNum || ""),
      company: String(assignment.company || ""),
      location: String(assignment.location || "").trim().toUpperCase(),
      placedPallets: allocationMapRound(assignment.placedPallets),
      shipmentPallets: allocationMapRound(assignment.shipmentPallets),
      maxPall: allocationMapRound(assignment.maxPall),
      unusedCapacity: allocationMapRound(assignment.unusedCapacity),
      placementNo: allocationMapNumber(assignment.placementNo, index + 1),
      orderNumbers: Array.isArray(assignment.orderNumbers) ? assignment.orderNumbers.map((value) => String(value)) : [],
      orderCompanies: assignment.orderCompanies && typeof assignment.orderCompanies === "object"
        ? Object.fromEntries(Object.entries(assignment.orderCompanies).map(([key, value]) => [String(key), String(value || "").trim().toUpperCase()]))
        : {},
    }))
    .filter((assignment) => assignment.location);
  const assignmentByLocation = new Map();
  assignments.forEach((assignment) => {
    assignmentByLocation.set(assignment.location, assignment);
  });
  const mapBounds = entry.bounds && Object.keys(entry.bounds).length
    ? entry.bounds
    : locations.length
      ? {
          minX: Math.min(...locations.map((loc) => loc.x)),
          minY: Math.min(...locations.map((loc) => loc.y)),
          maxX: Math.max(...locations.map((loc) => loc.x + loc.w)),
          maxY: Math.max(...locations.map((loc) => loc.y + loc.h)),
        }
      : { minX: 0, minY: 0, maxX: 1, maxY: 1 };
  const mapMinX = allocationMapNumber(mapBounds.minX);
  const mapMinY = allocationMapNumber(mapBounds.minY);
  const mapMaxX = allocationMapNumber(mapBounds.maxX, mapMinX + 1);
  const mapMaxY = allocationMapNumber(mapBounds.maxY, mapMinY + 1);
  const mapWidth = Math.max(1, mapMaxX - mapMinX);
  const mapHeight = Math.max(1, mapMaxY - mapMinY);
  const fitPadding = 70;

  const clusterColorOverrides = new Map(
    (allocationState.carrierClusters?.rows || [])
      .map((row) => [String(row.alias || row.description || row.carrierNum || ""), row.color])
      .filter(([carrier, color]) => carrier && color),
  );
  const colorMap = allocationClusterColorMap(
    assignments.map((assignment) => ({ carrier: assignment.carrier, cluster: assignment.cluster })),
    clusterColorOverrides,
  );

  const state = {
    transform: { x: 0, y: 0, scale: 1 },
    minScale: 0.05,
    rotation: 0,
    selectedLocation: "",
    clipboard: null,
    history: [],
    pan: null,
    drag: null,
    locElements: new Map(),
  };

  function locationCenter(loc) {
    return { x: loc.x + loc.w / 2, y: loc.y + loc.h / 2 };
  }

  function fittedMapScale(rect) {
    const width = Math.max(1, rect.width - fitPadding * 2);
    const height = Math.max(1, rect.height - fitPadding * 2);
    return Math.max(0.05, Math.min(3, Math.min(width / mapWidth, height / mapHeight)));
  }

  function centerTransformForScale(rect, scale) {
    return {
      x: (rect.width - mapWidth * scale) / 2 - mapMinX * scale,
      y: (rect.height - mapHeight * scale) / 2 - mapMinY * scale,
      scale,
    };
  }

  function clampAxis(value, rectSize, contentMin, contentMax, scale) {
    const scaledSize = (contentMax - contentMin) * scale;
    if (scaledSize + fitPadding * 2 <= rectSize) {
      return (rectSize - scaledSize) / 2 - contentMin * scale;
    }
    const minValue = rectSize - fitPadding - contentMax * scale;
    const maxValue = fitPadding - contentMin * scale;
    return allocationMapClamp(value, minValue, maxValue);
  }

  function clampTransform() {
    const rect = svg.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    state.minScale = fittedMapScale(rect);
    state.transform.scale = allocationMapClamp(state.transform.scale || state.minScale, state.minScale, 5);
    state.transform.x = clampAxis(state.transform.x, rect.width, mapMinX, mapMaxX, state.transform.scale);
    state.transform.y = clampAxis(state.transform.y, rect.height, mapMinY, mapMaxY, state.transform.scale);
  }

  function applyTransform() {
    clampTransform();
    const transform = `translate(${state.transform.x}, ${state.transform.y}) scale(${state.transform.scale})`;
    canvas.setAttribute("transform", transform);
    grid?.setAttribute("patternTransform", transform);
  }

  function applyRotation() {
    const rect = svg.getBoundingClientRect();
    rotateGroup.style.transformOrigin = `${rect.width / 2}px ${rect.height / 2}px`;
    rotateGroup.style.transform = state.rotation ? `rotate(${state.rotation}deg)` : "";
  }

  function fitMap() {
    if (!locations.length) return;
    const rect = svg.getBoundingClientRect();
    if (!rect.width || !rect.height) {
      requestAnimationFrame(fitMap);
      return;
    }
    state.minScale = fittedMapScale(rect);
    state.transform = centerTransformForScale(rect, state.minScale);
    applyTransform();
  }

  function updateAssignmentCapacity(assignment) {
    const loc = locationByName.get(assignment.location);
    if (!loc) return;
    assignment.maxPall = loc.maxPall || assignment.maxPall || 0;
    assignment.unusedCapacity = allocationMapRound(assignment.maxPall - assignment.placedPallets);
  }

  function mapMutationSnapshot() {
    return assignments.map((assignment) => ({
      id: assignment.id,
      location: assignment.location,
      maxPall: assignment.maxPall,
      unusedCapacity: assignment.unusedCapacity,
    }));
  }

  function rememberMapMutation() {
    state.history.push(mapMutationSnapshot());
    if (state.history.length > 50) state.history.shift();
  }

  function restoreMapMutation(snapshot) {
    const byId = new Map((snapshot || []).map((assignment) => [assignment.id, assignment]));
    assignmentByLocation.clear();
    assignments.forEach((assignment) => {
      const previous = byId.get(assignment.id);
      if (!previous) return;
      assignment.location = previous.location;
      assignment.maxPall = previous.maxPall;
      assignment.unusedCapacity = previous.unusedCapacity;
      if (assignment.location && locationByName.has(assignment.location)) {
        updateAssignmentCapacity(assignment);
        assignmentByLocation.set(assignment.location, assignment);
      }
    });
    refreshMap();
  }

  function assignmentById(id) {
    return assignments.find((assignment) => assignment.id === id) || null;
  }

  function assignmentLabel(assignment) {
    return assignment?.customer || assignment?.shipment || assignment?.carrier || assignment?.cluster || "placering";
  }

  function setMapText(elements, loc, assignment) {
    const center = locationCenter(loc);
    const horizontal = loc.w >= loc.h;
    const shortSide = Math.max(1, Math.min(loc.w, loc.h));
    const edgeBand = allocationMapClamp(shortSide * 0.55, 22, 44);
    const loadSide = allocationMapLoadOriginSide(loc.loadDirection, loc);
    const contentRect = { x: loc.x, y: loc.y, w: loc.w, h: loc.h };
    if (assignment) {
      if (loadSide === "left") {
        contentRect.x += edgeBand;
        contentRect.w = Math.max(1, contentRect.w - edgeBand);
      } else if (loadSide === "right") {
        contentRect.w = Math.max(1, contentRect.w - edgeBand);
      } else if (loadSide === "top") {
        contentRect.y += edgeBand;
        contentRect.h = Math.max(1, contentRect.h - edgeBand);
      } else if (loadSide === "bottom") {
        contentRect.h = Math.max(1, contentRect.h - edgeBand);
      }
    }
    const shortLocation = allocationMapShortLocation(loc.location);
    const label = assignment
      ? (assignment.customer || assignment.carrier || assignment.cluster || assignment.shipment)
      : shortLocation;
    const labelLines = assignment ? allocationMapLabelLines(label) : [label];
    const contentX = contentRect.x + contentRect.w / 2;
    const contentY = contentRect.y + contentRect.h / 2;
    const contentWidth = Math.max(18, horizontal ? contentRect.w - 10 : contentRect.h - 10);
    const contentHeight = Math.max(18, horizontal ? contentRect.h - 10 : contentRect.w - 10);
    const mainFont = assignment
      ? allocationMapClamp(contentHeight / (labelLines.length > 1 ? 2.45 : 1.85), 13, 22)
      : allocationMapClamp(shortSide * 0.24, 11, 15);
    const lineHeight = mainFont * 1.1;
    const firstLineY = assignment ? contentY - ((labelLines.length - 1) * lineHeight) / 2 : center.y;

    elements.edgeText.textContent = shortLocation;
    elements.edgeText.style.display = assignment ? "" : "none";
    elements.edgeText.style.fontSize = `${allocationMapClamp(shortSide * 0.34, 11, 22)}px`;
    elements.edgeText.removeAttribute("transform");
    elements.edgeText.removeAttribute("textLength");
    elements.edgeText.removeAttribute("lengthAdjust");
    const edgeFont = Number.parseFloat(elements.edgeText.style.fontSize) || 14;
    const edgeMaxWidth = loadSide === "left" || loadSide === "right" ? loc.h - 6 : loc.w - 6;
    if (allocationMapEstimatedTextWidth(shortLocation, edgeFont) > edgeMaxWidth) {
      elements.edgeText.setAttribute("textLength", String(Math.max(8, Math.round(edgeMaxWidth))));
      elements.edgeText.setAttribute("lengthAdjust", "spacingAndGlyphs");
    }
    if (assignment) {
      if (loadSide === "left") {
        const edgeX = loc.x + edgeBand / 2;
        elements.edgeText.setAttribute("x", edgeX);
        elements.edgeText.setAttribute("y", center.y);
        elements.edgeText.setAttribute("transform", `rotate(-90, ${edgeX}, ${center.y})`);
      } else if (loadSide === "right") {
        const edgeX = loc.x + loc.w - edgeBand / 2;
        elements.edgeText.setAttribute("x", edgeX);
        elements.edgeText.setAttribute("y", center.y);
        elements.edgeText.setAttribute("transform", `rotate(-90, ${edgeX}, ${center.y})`);
      } else if (loadSide === "top") {
        elements.edgeText.setAttribute("x", center.x);
        elements.edgeText.setAttribute("y", loc.y + edgeBand / 2);
      } else {
        elements.edgeText.setAttribute("x", center.x);
        elements.edgeText.setAttribute("y", loc.y + loc.h - edgeBand / 2);
      }
    }

    elements.mainText.textContent = "";
    elements.mainText.setAttribute("x", assignment ? contentX : center.x);
    elements.mainText.setAttribute("y", firstLineY);
    elements.mainText.setAttribute("class", assignment ? "allocation-map-label-main" : "allocation-map-label");
    elements.mainText.style.fontSize = `${mainFont}px`;
    elements.mainText.removeAttribute("transform");
    elements.mainText.removeAttribute("textLength");
    elements.mainText.removeAttribute("lengthAdjust");
    if (assignment && !horizontal) {
      elements.mainText.setAttribute("transform", `rotate(-90, ${contentX}, ${contentY})`);
    }
    labelLines.forEach((line, index) => {
      const span = document.createElementNS(ALLOCATION_MAP_NS, "tspan");
      span.setAttribute("x", assignment ? contentX : center.x);
      span.setAttribute("y", assignment ? firstLineY + index * lineHeight : center.y);
      if (assignment && allocationMapEstimatedTextWidth(line, mainFont) > contentWidth) {
        span.setAttribute("textLength", String(Math.round(contentWidth)));
        span.setAttribute("lengthAdjust", "spacingAndGlyphs");
      }
      span.textContent = line;
      elements.mainText.appendChild(span);
    });

    elements.metaText.textContent = "";
    elements.metaText.style.display = "none";
    elements.metaText.setAttribute("x", contentX);
    elements.metaText.setAttribute("y", contentY);
  }

  function setUnusedCapacityStripe(elements, loc, assignment) {
    const unusedEl = elements.unused;
    unusedEl.style.display = "none";
    if (!assignment || !elements.unusedPatternId) return;
    const capacity = allocationMapNumber(assignment.maxPall || loc.maxPall);
    const placed = allocationMapNumber(assignment.placedPallets);
    if (capacity <= 0 || placed >= capacity) return;
    const fraction = allocationMapClamp((capacity - Math.max(0, placed)) / capacity, 0, 1);
    if (fraction < 0.01) return;
    const color = colorMap.get(assignment.carrier) || "#94a3b8";
    elements.unusedPatternBase?.setAttribute("fill", allocationMapMixHexColor(color, "#ffffff", 0.72));
    elements.unusedPatternBand?.setAttribute("fill", allocationMapMixHexColor(color, "#ffffff", 0.36));
    const loadSide = allocationMapLoadOriginSide(loc.loadDirection, loc);
    let x = loc.x;
    let y = loc.y;
    let w = loc.w;
    let h = loc.h;
    if (loadSide === "left") {
      w = loc.w * fraction;
    } else if (loadSide === "right") {
      w = loc.w * fraction;
      x = loc.x + loc.w - w;
    } else if (loadSide === "top") {
      h = loc.h * fraction;
    } else {
      h = loc.h * fraction;
      y = loc.y + loc.h - h;
    }
    unusedEl.setAttribute("x", x);
    unusedEl.setAttribute("y", y);
    unusedEl.setAttribute("width", w);
    unusedEl.setAttribute("height", h);
    unusedEl.setAttribute("fill", `url(#${elements.unusedPatternId})`);
    unusedEl.style.display = "";
  }

  function updateLocationVisual(location) {
    const loc = locationByName.get(location);
    const elements = state.locElements.get(location);
    if (!loc || !elements) return;
    const assignment = assignmentByLocation.get(location);
    elements.rect.classList.toggle("is-assigned", Boolean(assignment));
    elements.rect.classList.toggle("is-selected", state.selectedLocation === location);
    elements.rect.classList.toggle("is-clipboard-source", state.clipboard?.source === location);
    elements.rect.classList.toggle("is-over-capacity", Boolean(assignment && assignment.unusedCapacity < -0.001));
    elements.rect.style.fill = assignment ? (colorMap.get(assignment.carrier) || "") : "";
    setUnusedCapacityStripe(elements, loc, assignment);
    setMapText(elements, loc, assignment);
  }

  function renderMetrics() {
    if (!metrics) return;
    const placed = allocationMapRound(assignments.reduce((sum, assignment) => sum + assignment.placedPallets, 0));
    const capacity = allocationMapRound(locations.reduce((sum, loc) => sum + loc.maxPall, 0));
    const availablePallets = allocationMapRound(Math.max(0, capacity - placed));
    const placedLocationCount = assignmentByLocation.size;
    const freeLocationCount = Math.max(0, locations.length - placedLocationCount);
    const over = assignments.filter((assignment) => assignment.unusedCapacity < -0.001).length;
    const unplaced = Array.isArray(entry.unplaced) ? entry.unplaced.length : 0;
    metrics.innerHTML = `
      <div><span>Placeringar</span><strong>${assignments.length}</strong></div>
      <div><span>Pallplatser</span><strong>${placed}</strong></div>
      <div><span>Lediga pallplatser</span><strong>${availablePallets}</strong></div>
      <div><span>Kapacitet</span><strong>${capacity}</strong></div>
      <div><span>Lediga ytor</span><strong>${freeLocationCount}</strong></div>
      <div class="${over ? "is-warning" : ""}"><span>Över kapacitet</span><strong>${over}</strong></div>
      <div class="${unplaced ? "is-warning" : ""}"><span>Ej placerade</span><strong>${unplaced}</strong></div>
    `;
  }

  function renderDetail() {
    if (!detail) return;
    const loc = locationByName.get(state.selectedLocation);
    const assignment = assignmentByLocation.get(state.selectedLocation);
    if (!loc) {
      detail.innerHTML = `<p class="allocation-muted">Ingen yta vald.</p>`;
      return;
    }
    detail.innerHTML = `
      <h4>${allocationEscape(loc.location)}</h4>
      <dl>
        <div><dt>Max pall</dt><dd>${allocationEscape(loc.maxPall || "")}</dd></div>
        ${assignment ? `
          <div><dt>Sändning</dt><dd>${allocationEscape(assignment.shipment)}</dd></div>
          ${assignment.customer ? `<div><dt>Kund</dt><dd>${allocationEscape(assignment.customer)}</dd></div>` : ""}
          <div><dt>Transportör</dt><dd>${allocationEscape(assignment.carrier)}</dd></div>
          ${assignment.cluster ? `<div><dt>Kluster</dt><dd>${allocationEscape(assignment.cluster)}</dd></div>` : ""}
          <div><dt>Placerade</dt><dd>${allocationEscape(assignment.placedPallets)}</dd></div>
          <div><dt>Outnyttjat</dt><dd>${allocationEscape(assignment.unusedCapacity)}</dd></div>
        ` : `<div><dt>Status</dt><dd>Ledig</dd></div>`}
      </dl>
    `;
  }

  function renderOverview() {
    if (!overview) return;
    const query = String(search?.value || "").trim().toLowerCase();
    const rows = [...assignments]
      .sort((a, b) => allocationMapCompareLocation(a.location, b.location))
      .filter((assignment) => {
        const haystack = `${assignment.location} ${assignment.shipment} ${assignment.customer} ${assignment.carrier} ${assignment.cluster}`.toLowerCase();
        return !query || haystack.includes(query);
      });
    overview.innerHTML = `
      <table>
        <thead><tr><th>UTL</th><th>Kund</th><th>Pall</th></tr></thead>
        <tbody>
          ${rows.map((assignment) => `
            <tr data-map-overview-location="${allocationEscape(assignment.location)}" class="${assignment.location === state.selectedLocation ? "is-selected" : ""}">
              <td>${allocationEscape(assignment.location)}</td>
              <td>${allocationEscape(assignment.customer || assignment.shipment || assignment.carrier)}</td>
              <td>${allocationEscape(assignment.placedPallets)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  function refreshMap() {
    locations.forEach((loc) => updateLocationVisual(loc.location));
    renderMetrics();
    renderDetail();
    renderOverview();
  }

  function selectLocation(location, center = false) {
    const previous = state.selectedLocation;
    state.selectedLocation = locationByName.has(location) ? location : "";
    if (previous) updateLocationVisual(previous);
    if (state.selectedLocation) updateLocationVisual(state.selectedLocation);
    renderDetail();
    renderOverview();
    if (center && state.selectedLocation) {
      const loc = locationByName.get(state.selectedLocation);
      const centerPoint = locationCenter(loc);
      const rect = svg.getBoundingClientRect();
      state.transform.x = rect.width / 2 - centerPoint.x * state.transform.scale;
      state.transform.y = rect.height / 2 - centerPoint.y * state.transform.scale;
      applyTransform();
    }
  }

  async function copyMapOverviewShipment(location) {
    const assignment = assignmentByLocation.get(location);
    if (!assignment?.shipment) return;
    try {
      await writeClipboardText(assignment.shipment);
      showToast(`Sändningsnummer kopierat: ${assignment.shipment}`, "success", 1800);
    } catch (error) {
      showToast(error.message || "Kunde inte kopiera sändningsnumret.", "error", 5000);
    }
  }

  function clearDragTarget() {
    if (state.drag?.target) {
      state.locElements.get(state.drag.target)?.rect.classList.remove("is-drop-target");
    }
    if (state.drag) state.drag.target = "";
  }

  function setDragTarget(location) {
    if (!state.drag || state.drag.target === location) return;
    clearDragTarget();
    state.drag.target = location;
    if (location) state.locElements.get(location)?.rect.classList.add("is-drop-target");
  }

  function placeAssignment(assignment, target, fallbackSource = "") {
    if (!assignment || !locationByName.has(target)) return false;
    const source = assignment.location;
    if (source === target) return false;
    const targetAssignment = assignmentByLocation.get(target);
    if (source) assignmentByLocation.delete(source);
    if (targetAssignment && targetAssignment !== assignment) {
      const swapLocation = source || fallbackSource;
      if (swapLocation && locationByName.has(swapLocation)) {
        targetAssignment.location = swapLocation;
        updateAssignmentCapacity(targetAssignment);
        assignmentByLocation.set(swapLocation, targetAssignment);
      } else {
        targetAssignment.location = "";
      }
    }
    assignment.location = target;
    updateAssignmentCapacity(assignment);
    assignmentByLocation.set(target, assignment);
    selectLocation(target);
    refreshMap();
    return true;
  }

  function moveAssignment(source, target, options = {}) {
    const sourceAssignment = assignmentByLocation.get(source);
    if (!sourceAssignment || !locationByName.has(target) || source === target) return false;
    if (options.recordHistory !== false) rememberMapMutation();
    const moved = placeAssignment(sourceAssignment, target, source);
    if (moved && options.announce) {
      showToast(`Flyttade ${assignmentLabel(sourceAssignment)} till ${target}.`, "success", 2500);
    }
    return moved;
  }

  function copySelectedAssignment(mode) {
    const source = state.selectedLocation;
    const assignment = assignmentByLocation.get(source);
    if (!source || !assignment) {
      showToast("Välj en placerad yta först.", "error", 3500);
      return;
    }
    state.clipboard = { assignmentId: assignment.id, source, mode };
    refreshMap();
    showToast(
      `${mode === "cut" ? "Klippte ut" : "Kopierade"} ${assignmentLabel(assignment)} från ${source}. Välj målyta och klistra in.`,
      "success",
      3500,
    );
  }

  function pasteMapClipboard() {
    if (!state.clipboard) {
      showToast("Inget karturklipp att klistra in.", "error", 3500);
      return;
    }
    const target = state.selectedLocation;
    if (!target || !locationByName.has(target)) {
      showToast("Välj en målyta innan du klistrar in.", "error", 3500);
      return;
    }
    const assignment = assignmentById(state.clipboard.assignmentId);
    if (!assignment) {
      state.clipboard = null;
      showToast("Karturklippet finns inte kvar.", "error", 3500);
      return;
    }
    if (assignment.location === target) {
      showToast("Placeringen ligger redan på vald yta.", "error", 2500);
      return;
    }
    const clipboardSource = state.clipboard.source;
    const clipboardMode = state.clipboard.mode;
    rememberMapMutation();
    const pasted = placeAssignment(assignment, target, clipboardSource);
    if (!pasted) {
      state.history.pop();
      showToast("Kunde inte klistra in placeringen.", "error", 3500);
      return;
    }
    if (clipboardMode === "cut") state.clipboard = null;
    else state.clipboard.source = assignment.location;
    refreshMap();
    showToast(`Klistrade in ${assignmentLabel(assignment)} på ${target}.`, "success", 2500);
  }

  function undoMapMutation() {
    const snapshot = state.history.pop();
    if (!snapshot) {
      if (state.clipboard) {
        state.clipboard = null;
        refreshMap();
        showToast("Tömde karturklippet.", "success", 2500);
        return;
      }
      showToast("Det finns inget kartdrag att angra.", "error", 2500);
      return;
    }
    restoreMapMutation(snapshot);
    showToast("Ångrade senaste kartändringen.", "success", 2500);
  }

  function isMapShortcutTextTarget(target) {
    const element = target instanceof Element ? target : null;
    return Boolean(element?.closest("input, textarea, select, [contenteditable='true']"));
  }

  function handleMapShortcut(event) {
    if (!(event.ctrlKey || event.metaKey) || event.altKey || isMapShortcutTextTarget(event.target)) return;
    const key = String(event.key || "").toLowerCase();
    if (!["c", "x", "v", "z"].includes(key)) return;
    event.preventDefault();
    event.stopPropagation();
    if (key === "c") copySelectedAssignment("copy");
    if (key === "x") copySelectedAssignment("cut");
    if (key === "v") pasteMapClipboard();
    if (key === "z") undoMapMutation();
  }

  function createGhost(assignment, event) {
    const ghost = document.createElement("div");
    ghost.className = "allocation-map-drag-ghost";
    ghost.textContent = assignment.shipment || assignment.carrier || assignment.location;
    document.body.appendChild(ghost);
    ghost.style.left = `${event.clientX + 14}px`;
    ghost.style.top = `${event.clientY + 14}px`;
    return ghost;
  }

  function renderLocations() {
    canvas.innerHTML = "";
    defs?.querySelectorAll("[data-map-unused-stripes]").forEach((pattern) => pattern.remove());
    state.locElements.clear();
    locations.forEach((loc) => {
      const group = document.createElementNS(ALLOCATION_MAP_NS, "g");
      group.setAttribute("data-map-location-group", loc.location);
      const rect = document.createElementNS(ALLOCATION_MAP_NS, "rect");
      rect.setAttribute("x", loc.x);
      rect.setAttribute("y", loc.y);
      rect.setAttribute("width", loc.w);
      rect.setAttribute("height", loc.h);
      rect.setAttribute("class", "allocation-map-loc");
      rect.dataset.mapLocation = loc.location;
      const unusedPatternId = `allocation-map-unused-stripes-${host.dataset.mapIndex || "0"}-${allocationMapSafeSvgId(loc.location)}`;
      const unusedPattern = document.createElementNS(ALLOCATION_MAP_NS, "pattern");
      unusedPattern.setAttribute("id", unusedPatternId);
      unusedPattern.setAttribute("data-map-unused-stripes", loc.location);
      unusedPattern.setAttribute("width", "18");
      unusedPattern.setAttribute("height", "18");
      unusedPattern.setAttribute("patternUnits", "userSpaceOnUse");
      unusedPattern.setAttribute("patternTransform", "rotate(45)");
      const unusedPatternBase = document.createElementNS(ALLOCATION_MAP_NS, "rect");
      unusedPatternBase.setAttribute("x", "0");
      unusedPatternBase.setAttribute("y", "0");
      unusedPatternBase.setAttribute("width", "18");
      unusedPatternBase.setAttribute("height", "18");
      const unusedPatternBand = document.createElementNS(ALLOCATION_MAP_NS, "rect");
      unusedPatternBand.setAttribute("x", "0");
      unusedPatternBand.setAttribute("y", "0");
      unusedPatternBand.setAttribute("width", "8");
      unusedPatternBand.setAttribute("height", "18");
      unusedPattern.appendChild(unusedPatternBase);
      unusedPattern.appendChild(unusedPatternBand);
      defs?.appendChild(unusedPattern);
      const unused = document.createElementNS(ALLOCATION_MAP_NS, "rect");
      unused.setAttribute("class", "allocation-map-unused");
      const edgeText = document.createElementNS(ALLOCATION_MAP_NS, "text");
      edgeText.setAttribute("class", "allocation-map-label-edge");
      const mainText = document.createElementNS(ALLOCATION_MAP_NS, "text");
      mainText.setAttribute("class", "allocation-map-label-main");
      const metaText = document.createElementNS(ALLOCATION_MAP_NS, "text");
      metaText.setAttribute("class", "allocation-map-label-sub");
      group.appendChild(rect);
      group.appendChild(unused);
      group.appendChild(edgeText);
      group.appendChild(mainText);
      group.appendChild(metaText);
      canvas.appendChild(group);
      state.locElements.set(loc.location, {
        group,
        rect,
        unused,
        unusedPatternId,
        unusedPatternBase,
        unusedPatternBand,
        edgeText,
        mainText,
        metaText,
      });
    });
    refreshMap();
  }

  function exportMapCsv() {
    const header = [
      "Sändningsnr", "Transportör", "Kluster", "Lagerplats", "Max pall", "Placerade pallplatser",
      "Sändningens pallplatser", "Outnyttjad kapacitet", "Placering nr",
    ];
    const rows = assignments.map((assignment) => [
      assignment.shipment,
      assignment.carrier,
      assignment.cluster,
      assignment.location,
      assignment.maxPall,
      assignment.placedPallets,
      assignment.shipmentPallets,
      assignment.unusedCapacity,
      assignment.placementNo,
    ]);
    const text = [header, ...rows].map((row) => row.map(allocationMapTsvCell).join("\t")).join("\n");
    allocationDownloadText("ytgenerering_justerad_karta.csv", `${text}\n`);
  }

  function exportAskCsv() {
    const grouped = new Map();
    assignments.forEach((assignment) => {
      if (!assignment.shipment) return;
      if (!grouped.has(assignment.shipment)) grouped.set(assignment.shipment, []);
      grouped.get(assignment.shipment).push(assignment);
    });
    const rows = [];
    const missingCompanyOrders = [];
    grouped.forEach((group) => {
      const orders = [...new Set(group.flatMap((assignment) => assignment.orderNumbers || []))];
      if (!orders.length) return;
      const areas = group
        .slice()
        .sort((a, b) => a.placementNo - b.placementNo || allocationMapCompareLocation(a.location, b.location))
        .map((assignment) => assignment.location)
        .join(", ");
      orders.forEach((orderNumber) => {
        const company = group
          .map((assignment) => assignment.orderCompanies?.[orderNumber] || assignment.company || "")
          .find((value) => String(value || "").trim());
        if (!company) {
          missingCompanyOrders.push(orderNumber);
          return;
        }
        rows.push([areas, String(company).trim().toUpperCase(), orderNumber, "A"]);
      });
    });
    if (missingCompanyOrders.length) {
      showToast(`Saknar bolag för justerad ASK-export: ${missingCompanyOrders.slice(0, 5).join(", ")}`, "error", 6000);
      return;
    }
    if (!rows.length) {
      showToast("Saknar ordernummer för justerad ASK-export.", "error", 5000);
      return;
    }
    const text = [["area_num", "company", "order_num", "pick_zone"], ...rows]
      .map((row) => row.map(allocationMapTsvCell).join("\t"))
      .join("\n");
    allocationDownloadText("v_ask_order_overview_order_set_area_execute_command_justerad.csv", `${text}\n`);
  }

  renderLocations();
  fitMap();

  svg.addEventListener("wheel", (event) => {
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1;
    const rect = svg.getBoundingClientRect();
    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;
    state.minScale = fittedMapScale(rect);
    const nextScale = allocationMapClamp(state.transform.scale * factor, state.minScale, 5);
    const appliedFactor = nextScale / Math.max(0.001, state.transform.scale);
    state.transform.x = mouseX - (mouseX - state.transform.x) * appliedFactor;
    state.transform.y = mouseY - (mouseY - state.transform.y) * appliedFactor;
    state.transform.scale = nextScale;
    applyTransform();
  }, { passive: false });

  svg.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    host.focus?.({ preventScroll: true });
    const rect = event.target.closest("[data-map-location]");
    if (rect) {
      const location = rect.dataset.mapLocation;
      selectLocation(location);
      const assignment = assignmentByLocation.get(location);
      if (assignment) {
        state.drag = {
          source: location,
          target: "",
          assignment,
          startX: event.clientX,
          startY: event.clientY,
          ghost: null,
          moved: false,
        };
        svg.setPointerCapture?.(event.pointerId);
        event.preventDefault();
      }
      return;
    }
    state.pan = {
      startX: event.clientX,
      startY: event.clientY,
      initX: state.transform.x,
      initY: state.transform.y,
    };
    svg.classList.add("is-panning");
    svg.setPointerCapture?.(event.pointerId);
  });

  svg.addEventListener("pointermove", (event) => {
    if (state.drag) {
      const dx = event.clientX - state.drag.startX;
      const dy = event.clientY - state.drag.startY;
      if (!state.drag.moved && Math.hypot(dx, dy) > 5) {
        state.drag.moved = true;
        state.drag.ghost = createGhost(state.drag.assignment, event);
      }
      if (state.drag.ghost) {
        state.drag.ghost.style.left = `${event.clientX + 14}px`;
        state.drag.ghost.style.top = `${event.clientY + 14}px`;
        const targetEl = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-map-location]");
        const target = targetEl?.dataset.mapLocation || "";
        setDragTarget(target && target !== state.drag.source ? target : "");
      }
      return;
    }
    if (!state.pan) return;
    const dx = event.clientX - state.pan.startX;
    const dy = event.clientY - state.pan.startY;
    state.transform.x = state.pan.initX + dx;
    state.transform.y = state.pan.initY + dy;
    applyTransform();
  });

  svg.addEventListener("pointerup", (event) => {
    if (state.drag) {
      const drag = state.drag;
      const target = drag.target;
      drag.ghost?.remove();
      clearDragTarget();
      state.drag = null;
      svg.releasePointerCapture?.(event.pointerId);
      if (drag.moved && target) moveAssignment(drag.source, target);
      return;
    }
    if (state.pan) {
      state.pan = null;
      svg.classList.remove("is-panning");
      svg.releasePointerCapture?.(event.pointerId);
    }
  });

  overview?.addEventListener("click", (event) => {
    const row = event.target.closest("[data-map-overview-location]");
    if (!row) return;
    const location = row.dataset.mapOverviewLocation;
    host.focus?.({ preventScroll: true });
    selectLocation(location, true);
    void copyMapOverviewShipment(location);
  });
  search?.addEventListener("input", renderOverview);
  host.addEventListener("keydown", handleMapShortcut);
  host.querySelector("[data-map-fit]")?.addEventListener("click", fitMap);
  host.querySelector("[data-map-rotate]")?.addEventListener("click", () => {
    state.rotation = state.rotation ? 0 : 90;
    host.classList.toggle("is-rotated", Boolean(state.rotation));
    applyRotation();
  });
  host.querySelector("[data-map-fullscreen]")?.addEventListener("click", async () => {
    if (document.fullscreenElement === host) {
      await document.exitFullscreen?.();
    } else {
      await host.requestFullscreen?.();
      requestAnimationFrame(fitMap);
    }
  });
  host.querySelector("[data-map-export-csv]")?.addEventListener("click", exportMapCsv);
  host.querySelector("[data-map-export-ask]")?.addEventListener("click", exportAskCsv);

  function renderMissingPanel() {
    if (!missingPanel) return;
    const rows = (Array.isArray(entry.unplaced) ? entry.unplaced : [])
      .map((row) => ({
        customer: String(row.customer || ""),
        carrier: String(row.carrier || ""),
        shipment: String(row.shipment || ""),
        unplacedPallets: allocationMapRound(row.unplacedPallets),
      }))
      .sort((a, b) => b.unplacedPallets - a.unplacedPallets);
    if (!rows.length) {
      missingPanel.innerHTML = `<p class="allocation-muted">Alla sändningar fick plats.</p>`;
      return;
    }
    missingPanel.innerHTML = `
      <h4>Saknade kunder <span>${rows.length}</span></h4>
      <ul class="allocation-map-missing-list">
        ${rows.map((row) => `
          <li>
            <span class="allocation-map-missing-dot" style="background:${colorMap.get(row.carrier) || "#d1d5db"}"></span>
            <span class="allocation-map-missing-name">${allocationEscape(row.customer || row.shipment || row.carrier)}</span>
            <span class="allocation-map-missing-meta">${allocationEscape(row.carrier)} · −${allocationEscape(row.unplacedPallets)} pall</span>
          </li>
        `).join("")}
      </ul>
    `;
  }

  renderMissingPanel();
  missingToggle?.addEventListener("click", () => {
    const open = missingPanel.hidden;
    missingPanel.hidden = !open;
    missingToggle.setAttribute("aria-pressed", String(open));
  });
}

function renderAllocationCarrierClusterEditor(host, clusters, options = {}) {
  const rows = clusters?.rows || [];
  const editableCarrier = Boolean(options.editableCarrier);
  const allowDelete = Boolean(options.allowDelete);
  const colorMap = allocationClusterColorMap(
    rows.map((row) => ({ carrier: row.alias || row.description || row.carrierNum, cluster: row.clusterGroup })),
    new Map(rows.map((row) => [String(row.alias || row.description || row.carrierNum || ""), row.color]).filter(([, color]) => color)),
  );
  host.innerHTML = `
    <div class="modal-table-scroll allocation-carrier-cluster-scroll">
      <table class="allocation-carrier-cluster-table allocation-cluster-advanced-table">
        <thead>
          <tr>
            <th style="width:28px"></th>
            <th style="width:32px"></th>
            <th>Transportör</th>
            <th style="width:74px">ASN</th>
            <th style="width:74px">Arrive</th>
            <th style="width:74px">Depart</th>
            <th style="width:150px">Group</th>
            <th style="width:80px">Start seq</th>
            <th style="width:80px">End seq</th>
            ${allowDelete ? `<th style="width:42px"></th>` : ""}
            <th style="width:54px">Color</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row, index) => {
            const carrier = row.alias || row.description || row.carrierNum || `Rad ${index + 1}`;
            const swatch = row.color || colorMap.get(String(row.alias || row.description || row.carrierNum || "")) || "#d1d5db";
            return `
              <tr data-carrier-cluster-row="${index}" draggable="true">
                <td class="adv-handle" aria-hidden="true">⠿</td>
                <td class="adv-index">${index + 1}</td>
                ${editableCarrier
                  ? `<th class="adv-agency"><input type="text" data-carrier-cluster-field="carrierNum" value="${allocationEscape(row.carrierNum || row.alias || row.description || "")}" placeholder="Transport&ouml;r" /></th>`
                  : `<th class="adv-agency">${allocationEscape(carrier)}</th>`}
                <td><input type="text" data-carrier-cluster-field="asn" value="${allocationEscape(row.asn || "")}" /></td>
                <td><input type="text" data-carrier-cluster-field="arrive" value="${allocationEscape(row.arrive || "")}" /></td>
                <td><input type="text" data-carrier-cluster-field="depart" value="${allocationEscape(row.depart || "")}" /></td>
                <td><input type="text" data-carrier-cluster-field="clusterGroup" value="${allocationEscape(row.clusterGroup || "")}" /></td>
                <td><input type="number" min="1" max="652" step="1" data-carrier-cluster-field="startSeq" value="${allocationEscape(row.startSeq || "")}" /></td>
                <td><input type="number" min="1" max="652" step="1" data-carrier-cluster-field="endSeq" value="${allocationEscape(row.endSeq || "")}" /></td>
                ${allowDelete ? `<td><button type="button" class="danger" data-carrier-cluster-delete="${index}" aria-label="Ta bort transport&ouml;r">x</button></td>` : ""}
                <td><input type="color" class="adv-color" data-carrier-cluster-field="color" value="${allocationEscape(swatch)}" aria-label="Färg ${allocationEscape(carrier)}" /></td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
  if (allowDelete) {
    host.querySelectorAll("[data-carrier-cluster-delete]").forEach((button) => {
      button.addEventListener("click", () => {
        button.closest("[data-carrier-cluster-row]")?.remove();
        [...host.querySelectorAll("[data-carrier-cluster-row]")].forEach((tr, index) => {
          const indexCell = tr.querySelector(".adv-index");
          if (indexCell) indexCell.textContent = index + 1;
        });
      });
    });
  }
  initAllocationCarrierClusterDrag(host.querySelector("tbody"));
}

function initAllocationCarrierClusterDrag(tbody) {
  if (!tbody) return;
  let dragSrc = null;
  tbody.addEventListener("dragstart", (event) => {
    dragSrc = event.target.closest("tr");
    if (!dragSrc) return;
    dragSrc.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
  });
  tbody.addEventListener("dragover", (event) => {
    event.preventDefault();
    const target = event.target.closest("tr");
    if (!target || target === dragSrc || !dragSrc) return;
    const rect = target.getBoundingClientRect();
    const after = event.clientY > rect.top + rect.height / 2;
    tbody.insertBefore(dragSrc, after ? target.nextSibling : target);
  });
  tbody.addEventListener("dragend", () => {
    if (!dragSrc) return;
    dragSrc.classList.remove("dragging");
    dragSrc = null;
    [...tbody.querySelectorAll("tr")].forEach((tr, index) => {
      const indexCell = tr.querySelector(".adv-index");
      if (indexCell) indexCell.textContent = index + 1;
    });
  });
}

function collectAllocationCarrierClusterDraft(host, clusters) {
  const sourceRows = clusters?.rows || [];
  const rows = [];
  host.querySelectorAll("[data-carrier-cluster-row]").forEach((tr, position) => {
    const index = Number.parseInt(tr.dataset.carrierClusterRow || "0", 10);
    const source = Number.isFinite(index) ? sourceRows[index] || {} : {};
    const row = { ...source };
    tr.querySelectorAll("[data-carrier-cluster-field]").forEach((input) => {
      const key = input.dataset.carrierClusterField;
      if (!key) return;
      if (key === "startSeq" || key === "endSeq") {
        row[key] = allocationCarrierClusterNumber(input.value);
      } else {
        row[key] = allocationCarrierClusterText(input.value);
      }
    });
    // Radordningen efter drag bestämmer ordningen.
    row.assignmentOrder = String(position + 1);
    rows.push(row);
  });
  return normalizeAllocationCarrierClusters({ ...clusters, rows });
}

function openAllocationCarrierClusterModal() {
  const clusters = allocationCarrierClustersForResult();
  if (!clusters?.rows?.length) {
    showToast("Forecast-resultatet saknar transportörskluster.", "warn", 3500);
    return;
  }
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal wide allocation-carrier-cluster-modal">
      <h2>Transportörskluster</h2>
      <div id="allocation-carrier-cluster-editor"></div>
      <div class="actions">
        <button type="button" id="allocation-carrier-cluster-cancel">Avbryt</button>
        <button type="button" class="primary" id="allocation-carrier-cluster-save">Spara</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);
  const editor = backdrop.querySelector("#allocation-carrier-cluster-editor");
  renderAllocationCarrierClusterEditor(editor, clusters);
  backdrop.querySelector("#allocation-carrier-cluster-cancel")?.addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("#allocation-carrier-cluster-save")?.addEventListener("click", () => {
    const updated = collectAllocationCarrierClusterDraft(editor, clusters);
    allocationState.carrierClusters = updated;
    if (allocationState.result?.data?.flow_id === "forecast") {
      allocationState.result.data.carrier_clusters = updated;
    }
    persistAllocationWorkState();
    backdrop.remove();
    renderAllocationPage();
    showToast("Transportörskluster sparade för Ytgenerering.", "success", 2500);
  });
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) backdrop.remove();
  });
}

async function writeClipboardText(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (error) {
      // Fallback nedan hanterar webbläsare som visar sidan utan clipboard-rättighet.
    }
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("Urklipp kunde inte användas.");
}

function bindResultActions(root) {
  initializeAllocationResultMaps(root);
  root.querySelector("[data-edit-carrier-clusters]")?.addEventListener("click", () => {
    allocationTrack("settings_modal_open", {
      control_id: "allocation-edit-carrier-clusters",
      control_label: "Transportörskluster",
      detail: { modal: "carrier_clusters" },
    });
    openAllocationCarrierClusterModal();
  });
  root.querySelectorAll("[data-follow-up-flow]").forEach((button) => {
    button.addEventListener("click", async () => {
      allocationTrack("follow_up_flow_start", {
        flow_id: button.dataset.followUpFlow || "",
        control_id: "allocation-follow-up-flow",
        control_label: button.textContent || "Foljdflode",
        detail: { follow_up_flow: button.dataset.followUpFlow || "" },
      });
      await runAllocationFlow(flowById(button.dataset.followUpFlow));
    });
  });
  root.querySelectorAll("[data-copy-text-result]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const text = button.closest(".allocation-text-result-wrap")?.querySelector("[data-result-text]")?.textContent || "";
        await writeClipboardText(text);
        allocationTrack("copy_text", {
          control_id: "allocation-copy-text-result",
          control_label: button.getAttribute("aria-label") || "Kopiera text",
          detail: {
            copied_length: text.length,
            copied_line_count: text ? text.split(/\r?\n/).filter((line) => line.trim()).length : 0,
          },
        });
        showToast("Text kopierad", "success", 2000);
      } catch (error) {
        allocationTrack("copy_text_error", {
          control_id: "allocation-copy-text-result",
          control_label: button.getAttribute("aria-label") || "Kopiera text",
          status: "error",
          detail: { error_type: error?.name || "Error", message: error?.message || "" },
        });
        showToast(error.message || "Kunde inte kopiera texten.", "error", 7000);
      }
    });
  });
  root.querySelectorAll("[data-copy-column]").forEach((button) => {
    button.addEventListener("click", async () => {
      const key = button.dataset.copyKey;
      const columnIndex = button.dataset.copyColumn;
      const columnMeta = allocationTableEventMeta(key, columnIndex);
      try {
        const sessionId = allocationState.result?.data?.session_id;
        if (!sessionId || !key || columnIndex == null) {
          allocationTrack("copy_column_blocked", {
            ...columnMeta,
            control_id: "allocation-copy-column",
            control_label: button.getAttribute("aria-label") || "Kopiera kolumn",
            status: "blocked",
            detail: { reason: "missing_result" },
          });
          throw new Error("Resultatet kunde inte hittas.");
        }
        const data = await allocationJson(
          `${ALLOCATION_API}/table-column/${encodeURIComponent(sessionId)}/${encodeURIComponent(key)}/${encodeURIComponent(columnIndex)}`,
        );
        await writeClipboardText(data.text || "");
        allocationTrack("copy_column", {
          ...columnMeta,
          control_id: "allocation-copy-column",
          control_label: button.getAttribute("aria-label") || "Kopiera kolumn",
          detail: {
            copy_mode: "manual",
            copied_line_count: String(data.text || "").split(/\r?\n/).filter((line) => line.trim()).length,
          },
        });
        showToast("Kolumn kopierad", "success", 2000);
      } catch (error) {
        allocationTrack("copy_column_error", {
          ...columnMeta,
          control_id: "allocation-copy-column",
          control_label: button.getAttribute("aria-label") || "Kopiera kolumn",
          status: "error",
          detail: { error_type: error?.name || "Error", message: error?.message || "" },
        });
        showToast(error.message || "Kunde inte kopiera kolumnen.", "error", 7000);
      }
    });
  });
  root.querySelectorAll("[data-open-excel]").forEach((button) => {
    button.addEventListener("click", async () => {
      const key = button.dataset.openExcel;
      const tableMeta = allocationTableEventMeta(key);
      try {
        await allocationJson(`${ALLOCATION_API}/open-excel`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: allocationState.result.data.session_id, key }),
        });
        allocationTrack("open_excel", {
          ...tableMeta,
          control_id: "allocation-open-excel",
          control_label: button.textContent || "Oppna i Excel",
        });
        showToast("Excel öppnas", "success", 2500);
      } catch (error) {
        allocationTrack("open_excel_error", {
          ...tableMeta,
          control_id: "allocation-open-excel",
          control_label: button.textContent || "Oppna i Excel",
          status: "error",
          detail: { error_type: error?.name || "Error", message: error?.message || "" },
        });
        showToast(error.message, "error");
      }
    });
  });
  root.querySelectorAll("[data-download-csv]").forEach((button) => {
    button.addEventListener("click", async () => {
      const key = button.dataset.downloadCsv;
      const tableMeta = allocationTableEventMeta(key);
      try {
        const sessionId = allocationState.result?.data?.session_id;
        if (!sessionId || !key) {
          allocationTrack("download_blocked", {
            ...tableMeta,
            control_id: "allocation-download-csv",
            control_label: button.textContent || "Ladda ner CSV",
            status: "blocked",
            detail: { reason: "missing_result" },
          });
          throw new Error("Resultatet kunde inte hittas.");
        }
        const filename = `${button.dataset.downloadLabel || key}.csv`;
        await api.download(`${ALLOCATION_API}/download/${encodeURIComponent(sessionId)}/${encodeURIComponent(key)}`, filename);
        allocationTrack("export", {
          ...tableMeta,
          control_id: "allocation-download-csv",
          control_label: button.textContent || "Ladda ner CSV",
          detail: { format: "csv" },
        });
      } catch (error) {
        allocationTrack("download_error", {
          ...tableMeta,
          control_id: "allocation-download-csv",
          control_label: button.textContent || "Ladda ner CSV",
          status: "error",
          detail: { error_type: error?.name || "Error", message: error?.message || "" },
        });
        showToast(error.message || "Kunde inte ladda ner CSV-filen.", "error");
      }
    });
  });
}

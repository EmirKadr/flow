// @ts-check
// Utdelad ur allocation/results.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter results.js via <script>-tagg.

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

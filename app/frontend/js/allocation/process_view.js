
function allocationFilterOperatorOptions(selected) {
  const value = normalizeAllocationFilterOperator(selected);
  return ALLOCATION_FILTER_OPERATORS
    .map((item) => `<option value="${allocationEscape(item.value)}" ${item.value === value ? "selected" : ""}>${allocationEscape(item.label)}</option>`)
    .join("");
}

function allocationFilterColumnControl(source, condition, index) {
  const columns = Array.isArray(source?.columns) ? source.columns : [];
  const selectedId = String(condition?.column || "").trim();
  const selectedLabel = String(condition?.columnLabel || "").trim();
  if (!columns.length) {
    return `<input type="text" data-filter-column="${index}" value="${allocationEscape(selectedLabel || selectedId)}" placeholder="Kolumn" />`;
  }
  const hasSelected = columns.some((column) => String(column.id || "") === selectedId || String(column.label || "") === selectedLabel);
  const selectedFallback = selectedId || selectedLabel;
  return `
    <select data-filter-column="${index}">
      ${selectedFallback && !hasSelected ? `<option value="${allocationEscape(selectedId || selectedFallback)}" data-label="${allocationEscape(selectedLabel || selectedFallback)}" selected>${allocationEscape(selectedLabel || selectedFallback)}</option>` : ""}
      ${columns.map((column) => {
        const columnId = String(column.id || "");
        const columnLabel = String(column.label || columnId);
        const columnType = String(column.type || "").trim();
        const selected = columnId === selectedId || columnLabel === selectedLabel;
        return `<option value="${allocationEscape(columnId)}" data-label="${allocationEscape(columnLabel)}" ${columnType ? `title="${allocationEscape(columnType)}"` : ""} ${selected ? "selected" : ""}>${allocationEscape(columnLabel)}</option>`;
      }).join("")}
    </select>
  `;
}

function defaultAllocationFilterCondition(source) {
  const firstColumn = Array.isArray(source?.columns) ? source.columns[0] : null;
  return {
    column: firstColumn?.id || "",
    columnLabel: firstColumn?.label || "",
    operator: "EQ",
    value: "",
  };
}

function renderAllocationSourceModeToggle(flowId, source, draft) {
  if (!source?.apiPreferred) return "";
  const mode = allocationSourceModeForFile(flowId, source.key, source, draft);
  const apiChecked = mode !== "upload";
  const sourceLabel = allocationEscape(source.label || source.key);
  return `
    <div class="allocation-source-mode-toggle" aria-label="K&auml;lla f&ouml;r ${sourceLabel}">
      <span>K&auml;lla</span>
      <label class="allocation-source-switch" title="V&auml;xla mellan API och uppladdad fil">
        <input
          type="checkbox"
          value="api"
          data-filter-source-mode-toggle
          aria-label="H&auml;mta ${sourceLabel} fr&aring;n API"
          ${apiChecked ? "checked" : ""}
        />
        <span class="allocation-source-switch-track" aria-hidden="true">
          <span class="allocation-source-switch-text allocation-source-switch-text--api">API</span>
          <span class="allocation-source-switch-text allocation-source-switch-text--upload">Fil</span>
          <span class="allocation-source-switch-knob"></span>
        </span>
      </label>
    </div>
  `;
}

function collectAllocationSourceMode(backdrop, draft, flowId, source) {
  if (!source?.apiPreferred) return;
  const toggle = backdrop.querySelector("[data-filter-source-mode-toggle]");
  const selected = toggle ? (toggle.checked ? "api" : "upload") : "api";
  draft.flows = draft.flows || {};
  draft.flows[flowId] = draft.flows[flowId] || {};
  draft.flows[flowId].sources = draft.flows[flowId].sources || {};
  if (selected === "upload") draft.flows[flowId].sources[source.key] = "upload";
  else delete draft.flows[flowId].sources[source.key];
  pruneAllocationDraftFlow(draft, flowId);
}

function allocationYtgenereringSettingsForDraft(draft, flowId) {
  const settings = draft?.flows?.[flowId]?.settings?.ytgenerering;
  return settings ? normalizeAllocationYtgenereringSettings(settings) : allocationDefaultYtgenereringSettings();
}

function setAllocationYtgenereringDraftSettings(draft, flowId, settings) {
  draft.flows = draft.flows || {};
  draft.flows[flowId] = draft.flows[flowId] || {};
  draft.flows[flowId].settings = draft.flows[flowId].settings || {};
  draft.flows[flowId].settings.ytgenerering = normalizeAllocationYtgenereringSettings(settings);
}

function pruneAllocationDraftFlow(draft, flowId) {
  const flow = draft.flows?.[flowId];
  if (!flow) return;
  if (flow.sources && !Object.keys(flow.sources).length) delete flow.sources;
  if (flow.files && !Object.keys(flow.files).length) delete flow.files;
  if (flow.settings && !Object.keys(flow.settings).length) delete flow.settings;
  if (!flow.sources && !flow.files && !flow.settings) delete draft.flows[flowId];
}

function renderAllocationYtgenereringSettingsEditor(host, settings) {
  const normalized = normalizeAllocationYtgenereringSettings(settings);
  const areas = normalizeAllocationYtgenereringAreas(normalized.areas);
  const editableAreas = allocationYtgenereringEditableAreasForCurrentToggle();
  const hasSavedCarrierClusters = Object.prototype.hasOwnProperty.call(normalized, "carrierClusters");
  const carrierClusters = hasSavedCarrierClusters
    ? (normalizeAllocationCarrierClusters(normalized.carrierClusters) || { version: 1, source: { name: "Manuell", rowCount: 0 }, rows: [] })
    : allocationDefaultCarrierClusters();
  host.__allocationYtgenereringBaseAreas = areas;
  host.__allocationYtgenereringCarrierClusters = carrierClusters;
  host.innerHTML = `
    <div class="allocation-ytgenerering-settings">
      <section class="allocation-ytgenerering-settings-section">
        <h4>Utlastningsytor</h4>
        <div class="allocation-ytgenerering-utl-grid">
          ${editableAreas.map((area) => {
            const code = String(area.code || "").trim().toUpperCase();
            const range = normalizeYtgenereringUtlRange(areas[code] || areas.DEFAULT);
            return `
              <div class="allocation-ytgenerering-utl-row" data-ytgenerering-utl-area="${allocationEscape(code)}">
                <strong>${allocationEscape(area.label || code)}</strong>
                <label>
                  <span>Fr&aring;n</span>
                  <input type="number" min="1" max="652" step="1" data-ytgenerering-utl-min="${allocationEscape(code)}" value="${range.min}" />
                </label>
                <label>
                  <span>Till</span>
                  <input type="number" min="1" max="652" step="1" data-ytgenerering-utl-max="${allocationEscape(code)}" value="${range.max}" />
                </label>
              </div>
            `;
          }).join("")}
        </div>
      </section>
      <section class="allocation-ytgenerering-settings-section">
        <div class="allocation-filter-editor-head">
          <h4>Transport&ouml;rskluster</h4>
          <div class="allocation-filter-toolbar-inline">
            <button type="button" data-ytgenerering-carrier-add>L&auml;gg transport&ouml;r</button>
            <button type="button" data-ytgenerering-carrier-defaults>Standard</button>
            <button type="button" data-ytgenerering-carrier-clear>Rensa</button>
          </div>
        </div>
        <div data-ytgenerering-carriers></div>
      </section>
    </div>
  `;
  const carrierHost = host.querySelector("[data-ytgenerering-carriers]");
  renderAllocationCarrierClusterEditor(carrierHost, carrierClusters, { editableCarrier: true, allowDelete: true });
  host.querySelector("[data-ytgenerering-carrier-add]")?.addEventListener("click", () => {
    const current = collectAllocationYtgenereringSettingsDraft(host);
    const rows = [...(current.carrierClusters?.rows || [])];
    rows.push({
      id: `manual-${Date.now()}`,
      carrierNum: `Ny transportor ${rows.length + 1}`,
      description: "",
      alias: "",
      clusterGroup: "",
      assignmentOrder: String(rows.length + 1),
      startSeq: String(ALLOCATION_YTGENERERING_UTL_MIN),
      endSeq: String(ALLOCATION_YTGENERERING_UTL_MAX),
      asn: ALLOCATION_CLUSTER_DEFAULT_TIMES.asn,
      arrive: ALLOCATION_CLUSTER_DEFAULT_TIMES.arrive,
      depart: ALLOCATION_CLUSTER_DEFAULT_TIMES.depart,
      color: allocationHslToHex(ALLOCATION_CLUSTER_HUES[rows.length % ALLOCATION_CLUSTER_HUES.length], 65, 58),
    });
    renderAllocationYtgenereringSettingsEditor(host, { ...current, carrierClusters: { version: 1, source: { name: "Manuell", rowCount: rows.length }, rows } });
  });
  host.querySelector("[data-ytgenerering-carrier-defaults]")?.addEventListener("click", () => {
    const current = collectAllocationYtgenereringSettingsDraft(host);
    renderAllocationYtgenereringSettingsEditor(host, { ...current, carrierClusters: allocationDefaultCarrierClusters() });
  });
  host.querySelector("[data-ytgenerering-carrier-clear]")?.addEventListener("click", () => {
    const current = collectAllocationYtgenereringSettingsDraft(host);
    renderAllocationYtgenereringSettingsEditor(host, { ...current, carrierClusters: { version: 1, source: { name: "Manuell", rowCount: 0 }, rows: [] } });
  });
}

function collectAllocationYtgenereringSettingsDraft(host) {
  const areas = normalizeAllocationYtgenereringAreas(host.__allocationYtgenereringBaseAreas || allocationDefaultYtgenereringAreas());
  host.querySelectorAll("[data-ytgenerering-utl-area]").forEach((row) => {
    const code = String(row.dataset.ytgenereringUtlArea || "").trim().toUpperCase();
    if (!code) return;
    const range = normalizeYtgenereringUtlRange({
      utlMin: row.querySelector(`[data-ytgenerering-utl-min="${code}"]`)?.value,
      utlMax: row.querySelector(`[data-ytgenerering-utl-max="${code}"]`)?.value,
    });
    areas[code] = { utlMin: range.min, utlMax: range.max };
  });
  const carrierHost = host.querySelector("[data-ytgenerering-carriers]");
  const carrierClusters = carrierHost
    ? collectAllocationCarrierClusterDraft(carrierHost, host.__allocationYtgenereringCarrierClusters || allocationDefaultCarrierClusters())
    : null;
  return normalizeAllocationYtgenereringSettings({ areas, carrierClusters });
}

function collectAllocationFilterModalSource(backdrop, draft, flowId, fileKey, source = null) {
  if (!fileKey) return;
  if (fileKey === ALLOCATION_YTGENERERING_SETTINGS_SOURCE) {
    const host = backdrop.querySelector("[data-ytgenerering-settings-editor]");
    if (host) setAllocationYtgenereringDraftSettings(draft, flowId, collectAllocationYtgenereringSettingsDraft(host));
    return;
  }
  collectAllocationSourceMode(backdrop, draft, flowId, source);
  const rows = [...backdrop.querySelectorAll("[data-filter-condition]")];
  const conditions = rows.map((row) => {
    const index = row.dataset.filterCondition;
    const columnControl = row.querySelector(`[data-filter-column="${index}"]`);
    const selectedOption = columnControl?.tagName === "SELECT"
      ? columnControl.options[columnControl.selectedIndex]
      : null;
    return {
      column: columnControl?.value || "",
      columnLabel: selectedOption?.dataset?.label || columnControl?.value || "",
      operator: row.querySelector(`[data-filter-operator="${index}"]`)?.value || "EQ",
      value: row.querySelector(`[data-filter-value="${index}"]`)?.value || "",
    };
  });
  draft.flows = draft.flows || {};
  draft.flows[flowId] = draft.flows[flowId] || { files: {} };
  draft.flows[flowId].files = draft.flows[flowId].files || {};
  if (conditions.length) draft.flows[flowId].files[fileKey] = conditions;
  else delete draft.flows[flowId].files[fileKey];
  pruneAllocationDraftFlow(draft, flowId);
}

function renderAllocationFlowFilterModal(backdrop, flow, draft, selectedKey = "") {
  const sources = allocationFilterSourcesForFlow(flow);
  const selectedSource = sources.find((source) => source.key === selectedKey) || sources[0] || null;
  const currentKey = selectedSource?.key || "";
  const isSettingsSource = selectedSource?.type === "settings";
  const conditions = isSettingsSource ? [] : draft.flows?.[flow.id]?.files?.[currentKey] || [];
  const importUsers = (allocationState.filterUsers || []).filter((user) => user.has_filters && !user.is_current);
  backdrop.innerHTML = `
    <div class="modal wide allocation-filter-modal">
      <h2>Filtreringar - ${allocationEscape(flow.label || flow.id)}</h2>
      <div class="allocation-filter-toolbar">
        <select id="allocation-filter-import-user" ${importUsers.length ? "" : "disabled"}>
          <option value="">H&auml;mta fr&aring;n anv&auml;ndare</option>
          ${importUsers.map((user) => `<option value="${allocationEscape(user.id)}">${allocationEscape(user.name || user.username)} (${allocationEscape(user.filter_count || 0)})</option>`).join("")}
        </select>
        <button type="button" id="allocation-filter-import" ${importUsers.length ? "" : "disabled"}>H&auml;mta</button>
      </div>
      <div class="allocation-filter-layout">
        <div class="allocation-filter-source-list">
          ${sources.map((source) => {
            const count = allocationFilterCountForSource(flow.id, source.key, draft);
            return `
              <button type="button" class="${source.key === currentKey ? "active" : ""}" data-filter-source="${allocationEscape(source.key)}">
                <span>${allocationEscape(source.label || source.key)}</span>
                ${count ? `<strong>${count}</strong>` : ""}
              </button>
            `;
          }).join("") || `<p class="allocation-muted">Inga filer.</p>`}
        </div>
        <div class="allocation-filter-editor">
          ${selectedSource ? `
            <div class="allocation-filter-editor-head">
              <h3>${allocationEscape(selectedSource.label || selectedSource.key)}</h3>
              ${isSettingsSource ? "" : `<button type="button" id="allocation-filter-add">+ Filter</button>`}
            </div>
            ${isSettingsSource ? `
              <div data-ytgenerering-settings-editor></div>
            ` : `
              ${renderAllocationSourceModeToggle(flow.id, selectedSource, draft)}
              <div class="allocation-filter-condition-head">
                <span>Kolumn</span>
                <span>Operator</span>
                <span>V&auml;rde</span>
              </div>
              <div class="allocation-filter-conditions">
                ${conditions.map((condition, index) => `
                  <div class="allocation-filter-condition" data-filter-condition="${index}">
                    ${allocationFilterColumnControl(selectedSource, condition, index)}
                    <select data-filter-operator="${index}">${allocationFilterOperatorOptions(condition.operator)}</select>
                    <textarea rows="3" data-filter-value="${index}">${allocationEscape(allocationFilterConditionValueText(condition))}</textarea>
                    <button type="button" class="danger" data-filter-remove="${index}" aria-label="Ta bort filter">x</button>
                  </div>
                `).join("") || `<p class="allocation-muted">Inga filter sparade f&ouml;r filen.</p>`}
                </div>
            `}
          ` : `<p class="allocation-muted">Inga filer.</p>`}
        </div>
      </div>
      <div class="actions">
        <button type="button" id="allocation-filter-clear-flow">Rensa funktion</button>
        <button type="button" id="allocation-filter-cancel">Avbryt</button>
        <button type="button" class="primary" id="allocation-filter-save">Spara</button>
      </div>
    </div>
  `;

  if (isSettingsSource) {
    const settingsHost = backdrop.querySelector("[data-ytgenerering-settings-editor]");
    if (settingsHost) renderAllocationYtgenereringSettingsEditor(settingsHost, allocationYtgenereringSettingsForDraft(draft, flow.id));
  }

  const rerender = (nextSelectedKey = currentKey) => renderAllocationFlowFilterModal(backdrop, flow, draft, nextSelectedKey);
  backdrop.querySelectorAll("[data-filter-source]").forEach((button) => {
    button.addEventListener("click", () => {
      collectAllocationFilterModalSource(backdrop, draft, flow.id, currentKey, selectedSource);
      rerender(button.dataset.filterSource || "");
    });
  });
  backdrop.querySelector("#allocation-filter-add")?.addEventListener("click", () => {
    collectAllocationFilterModalSource(backdrop, draft, flow.id, currentKey, selectedSource);
    draft.flows = draft.flows || {};
    draft.flows[flow.id] = draft.flows[flow.id] || { files: {} };
    draft.flows[flow.id].files = draft.flows[flow.id].files || {};
    draft.flows[flow.id].files[currentKey] = draft.flows[flow.id].files[currentKey] || [];
    draft.flows[flow.id].files[currentKey].push(defaultAllocationFilterCondition(selectedSource));
    rerender(currentKey);
  });
  backdrop.querySelectorAll("[data-filter-remove]").forEach((button) => {
    button.addEventListener("click", () => {
      collectAllocationFilterModalSource(backdrop, draft, flow.id, currentKey, selectedSource);
      const index = Number(button.dataset.filterRemove);
      draft.flows?.[flow.id]?.files?.[currentKey]?.splice(index, 1);
      rerender(currentKey);
    });
  });
  backdrop.querySelector("#allocation-filter-clear-flow")?.addEventListener("click", () => {
    if (draft.flows) delete draft.flows[flow.id];
    rerender(currentKey);
  });
  backdrop.querySelector("#allocation-filter-cancel")?.addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("#allocation-filter-save")?.addEventListener("click", async () => {
    collectAllocationFilterModalSource(backdrop, draft, flow.id, currentKey, selectedSource);
    const button = backdrop.querySelector("#allocation-filter-save");
    button.disabled = true;
    try {
      await saveAllocationFilterProfile(draft);
      await loadAllocationUploadStateForVisibleFlows();
      backdrop.remove();
      renderAllocationPage();
      showToast("Filtrering sparades.", "success", 2500);
    } catch (error) {
      button.disabled = false;
      showToast(error.message || "Kunde inte spara filtrering.", "error", 7000);
    }
  });
  backdrop.querySelector("#allocation-filter-import")?.addEventListener("click", async () => {
    const userId = backdrop.querySelector("#allocation-filter-import-user")?.value;
    if (!userId) return;
    const button = backdrop.querySelector("#allocation-filter-import");
    button.disabled = true;
    try {
      await importAllocationFilterProfile(userId);
      await loadAllocationUploadStateForVisibleFlows();
      const imported = cloneAllocationFilterProfile();
      Object.keys(draft).forEach((key) => delete draft[key]);
      Object.assign(draft, imported);
      rerender(currentKey);
      showToast("Filtrering hamtad.", "success", 2500);
    } catch (error) {
      button.disabled = false;
      showToast(error.message || "Kunde inte hamta filtrering.", "error", 7000);
    }
  });
}

function openAllocationFlowFilterModal(flow) {
  if (!flow) return;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  document.body.appendChild(backdrop);
  renderAllocationFlowFilterModal(backdrop, flow, cloneAllocationFilterProfile());
}

function renderFlowChip(flow) {
  const missing = missingForFlow(flow);
  const ready = missing.length === 0;
  const running = allocationState.busyId === flow.id;
  const fileList = renderFlowFileList(flow);
  const label = allocationEscape(flow.label);
  const filterCount = allocationFilterCountForFlow(flow.id);
  return `
    <div class="allocation-flow-chip ${ready ? "ready" : ""}" data-allocation-drop data-drop-scope="flow" data-flow-id="${allocationEscape(flow.id)}">
      <div class="allocation-flow-chip-row">
        <button type="button" class="allocation-flow-run" data-run-flow="${allocationEscape(flow.id)}" ${ready && !allocationState.busyId ? "" : "disabled"}>
          ${running ? "Kör…" : label}
        </button>
        <button type="button" class="allocation-flow-filter ${filterCount ? "active" : ""}" data-flow-filter="${allocationEscape(flow.id)}" aria-label="Redigera filtrering f&ouml;r ${label}">
          ${ALLOCATION_EDIT_ICON}
          ${filterCount ? `<span>${allocationEscape(filterCount)}</span>` : ""}
        </button>
        <button type="button" class="allocation-flow-info" data-flow-info="${allocationEscape(flow.id)}" aria-label="Visa information om ${label}">
          <span aria-hidden="true">i</span>
        </button>
      </div>
      <div class="allocation-flow-popover" data-flow-popover="${allocationEscape(flow.id)}" hidden>
        <p>${allocationEscape(flow.description)}</p>
        ${fileList || `<p>Inga filer krävs.</p>`}
      </div>
    </div>
  `;
}

function allocationGroupTitle(name) {
  if (name === "Sökning & prognos") return "Prognos";
  return name;
}

function closeFlowPopovers(root) {
  root.querySelectorAll("[data-flow-popover]").forEach((popover) => { popover.hidden = true; });
  root.querySelectorAll("[data-flow-info].active").forEach((button) => button.classList.remove("active"));
}

function bindFlowInfoToggles(root) {
  root.querySelectorAll("[data-flow-info]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const popover = root.querySelector(`[data-flow-popover="${button.dataset.flowInfo}"]`);
      const wasOpen = popover && !popover.hidden;
      closeFlowPopovers(root);
      if (popover && !wasOpen) {
        popover.hidden = false;
        button.classList.add("active");
      }
    });
  });
}

function bindFlowFilterButtons(root) {
  root.querySelectorAll("[data-flow-filter]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openAllocationFlowFilterModal(flowById(button.dataset.flowFilter));
    });
  });
}

function ensureFlowPopoverDismiss() {
  if (allocationPopoverDismissBound) return;
  allocationPopoverDismissBound = true;
  document.addEventListener("click", (event) => {
    const root = document.getElementById("allocationRoot");
    if (!root) return;
    if (event.target.closest("[data-flow-info]") || event.target.closest("[data-flow-filter]") || event.target.closest("[data-flow-popover]")) return;
    closeFlowPopovers(root);
  });
}

function canViewAllocationProcessMatrix() {
  return Boolean(window.canViewPage?.(allocationState.user, "allocationProcessMatrix") || allocationState.user?.is_super_user);
}

function canEditAllocationProcessMatrix() {
  return Boolean(window.canEditPage?.(allocationState.user, "allocationProcessMatrix") || allocationState.user?.is_super_user);
}

function canViewAllocationMapSettings() {
  return Boolean(window.canViewPage?.(allocationState.user, "allocationSettings") || allocationState.user?.is_super_user);
}

function canEditAllocationMapSettings() {
  return Boolean(window.canEditPage?.(allocationState.user, "allocationSettings") || allocationState.user?.is_super_user);
}

function canViewStaffingSettings() {
  return Boolean(window.canViewPage?.(allocationState.user, "staffingSettings") || allocationState.user?.is_super_user);
}

function canEditStaffingSettings() {
  return Boolean(window.canEditPage?.(allocationState.user, "staffingSettings") || allocationState.user?.is_super_user);
}


function renderCombinedView() {
  const flows = combinedAllocationFlows();
  const groups = [];
  for (const flow of flows) {
    let group = groups.find((item) => item.name === flow.category);
    if (!group) {
      group = { name: flow.category, flows: [] };
      groups.push(group);
    }
    group.flows.push(flow);
  }
  const anyFile = Object.keys(allocationState.files).length > 0;
  const fileActionLabel = anyFile ? "Välj fler filer" : "Välj filer";
  renderAllocationShell(`
    <section class="allocation-panel allocation-panel--compact" data-allocation-drop>
      ${!anyFile ? `<p class="allocation-status">Inga filer inlagda. Dra filer hit eller använd Välj filer.</p>` : ""}
      ${allocationState.status ? `<p class="allocation-status">${allocationEscape(allocationState.status)}</p>` : ""}
      <div class="allocation-board">
        ${groups.map((group) => `
          <div class="allocation-board-col">
            <h3>${allocationEscape(allocationGroupTitle(group.name))}</h3>
            ${group.flows.map((flow) => renderFlowChip(flow)).join("")}
          </div>
        `).join("")}
      </div>
    </section>
    ${renderResultPanel(allocationState.result)}
  `, `
    <label class="button-like" for="allocation-combined-files">${fileActionLabel}</label>
    <input id="allocation-combined-files" type="file" multiple hidden />
  `);
  const input = document.getElementById("allocation-combined-files");
  if (input) input.addEventListener("change", async (event) => routeAllocationFiles(event.target.files, currentAllocationSlots()));
  bindRunButtons();
}

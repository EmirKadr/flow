// @ts-check
function allocationProcessMatrixAreas() {
  return allocationProcessMatrixData().areas || ALLOCATION_PROCESS_AREA_OPTIONS;
}

function allocationYtgenereringEditableAreasForCurrentToggle() {
  const areas = allocationProcessMatrixAreas();
  const focusCode = allocationProcessToggleCode();
  if (!focusCode) return areas;
  const focusedArea = areas.find((area) => String(area.code || "").trim().toUpperCase() === focusCode);
  return [focusedArea || { code: focusCode, label: focusCode }];
}

function allocationProcessMatrixFlows() {
  const savedFlows = allocationProcessMatrixData().flows || [];
  if (savedFlows.length) return savedFlows;
  return allocationState.visibleFlows
    .filter((flow) => flow.view === "combined" && !ALLOCATION_HIDDEN_FLOW_IDS.has(flow.id))
    .map((flow) => ({
      id: String(flow.id || ""),
      label: String(flow.label || flow.id || ""),
      category: String(flow.category || ""),
    }))
    .filter((flow) => flow.id);
}

function cloneAllocationProcessMatrixRules(rules) {
  const cloned = {};
  for (const [code, rule] of Object.entries(rules || {})) {
    cloned[code] = {
      visibleFlowIds: Array.isArray(rule.visibleFlowIds) ? [...rule.visibleFlowIds] : null,
    };
  }
  return cloned;
}

function allocationProcessMatrixDraft(defaults = false) {
  const source = defaults ? allocationProcessFallbackMatrix().matrix : allocationProcessMatrixData().matrix;
  return cloneAllocationProcessMatrixRules(source);
}

function allocationProcessMatrixFlowChecks(code, rule, flows) {
  const allFlows = !Array.isArray(rule.visibleFlowIds);
  const visible = new Set(rule.visibleFlowIds || []);
  return `
    <div class="allocation-process-flow-grid" data-matrix-flow-grid="${allocationEscape(code)}">
      <label class="modal-checkbox allocation-process-flow-all">
        <input type="checkbox" data-matrix-all-flows="${allocationEscape(code)}" ${allFlows ? "checked" : ""} />
        <span>Alla</span>
      </label>
      ${flows.map((flow) => `
        <label class="modal-checkbox allocation-process-flow-check">
          <input
            type="checkbox"
            data-matrix-flow="${allocationEscape(code)}"
            value="${allocationEscape(flow.id)}"
            ${allFlows || visible.has(flow.id) ? "checked" : ""}
            ${allFlows ? "disabled" : ""}
          />
          <span>${allocationEscape(flow.label)}</span>
        </label>
      `).join("")}
    </div>
  `;
}

function renderAllocationProcessMatrixEditor(host, draft, readonly = false) {
  const areas = allocationProcessMatrixAreas();
  const flows = allocationProcessMatrixFlows();
  host.innerHTML = `
    <div class="modal-table-scroll allocation-process-matrix-scroll">
      <table class="allocation-process-matrix-table">
        <thead>
          <tr>
            <th>Toggle</th>
            <th>Funktioner</th>
          </tr>
        </thead>
        <tbody>
          ${areas.map((area) => {
            const code = String(area.code || "").toUpperCase();
            const rule = draft[code] || normalizeAllocationProcessRule(ALLOCATION_PROCESS_MATRIX.DEFAULT);
            return `
              <tr data-matrix-area="${allocationEscape(code)}">
                <th>${allocationEscape(area.label || code)}</th>
                <td>${allocationProcessMatrixFlowChecks(code, rule, flows)}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
  if (readonly) {
    host.querySelectorAll("[data-matrix-all-flows], [data-matrix-flow]").forEach((input) => { input.disabled = true; });
    return;
  }
  host.querySelectorAll("[data-matrix-all-flows]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const grid = checkbox.closest("[data-matrix-flow-grid]");
      grid?.querySelectorAll("[data-matrix-flow]").forEach((item) => {
        item.disabled = checkbox.checked;
        if (checkbox.checked) item.checked = true;
      });
    });
  });
}

function collectAllocationProcessMatrixDraft(host) {
  const matrix = {};
  host.querySelectorAll("[data-matrix-area]").forEach((row) => {
    const code = String(row.dataset.matrixArea || "").trim().toUpperCase();
    if (!code) return;
    const allFlows = row.querySelector("[data-matrix-all-flows]")?.checked;
    const visibleFlowIds = allFlows
      ? null
      : [...row.querySelectorAll("[data-matrix-flow]:checked")].map((input) => input.value);
    matrix[code] = {
      visibleFlowIds,
    };
  });
  return matrix;
}

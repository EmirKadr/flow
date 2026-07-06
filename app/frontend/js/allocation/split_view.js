// @ts-check
function renderSoloFlowView(flowId) {
  const flow = flowById(flowId);
  if (!flow) {
    renderAllocationShell(`<section class="allocation-panel"><p>Vyn kunde inte laddas.</p></section>`);
    return;
  }
  const slots = slotsForFlow(flow);
  const missing = missingForFlow(flow);
  const ready = missing.length === 0 && !allocationState.busyId;
  const compact = false;
  const hasFileSlots = slots.length > 0;
  const hasUploadedFile = slots.some((slot) => allocationDisplayFile(slot.key));
  const fileActionLabel = hasUploadedFile ? "Välj fler filer" : "Välj filer";
  renderAllocationShell(`
    <section class="allocation-panel ${compact ? "allocation-panel--compact" : ""}" data-allocation-drop data-drop-scope="flow" data-flow-id="${allocationEscape(flow.id)}">
      ${compact ? `
        <div class="allocation-solo-compact">
          ${renderFieldInputs(flow, "allocation-fields--compact")}
          <div class="allocation-run-row allocation-run-row--compact">
            ${renderFlowChip(flow)}
            <span>${allocationEscape(allocationState.status)}</span>
          </div>
        </div>
      ` : `
        <div class="allocation-panel-head">
          <h2>${allocationEscape(flow.label)}</h2>
          ${slots.length ? `<label class="button-like" for="allocation-solo-files">Välj filer</label><input id="allocation-solo-files" type="file" multiple hidden />` : ""}
        </div>
        <p class="allocation-muted">${allocationEscape(flow.description)}</p>
        ${slots.length ? `<div class="allocation-file-grid compact">${allocationFileRows(slots)}</div>` : ""}
        ${renderFieldInputs(flow)}
        <div class="allocation-run-row">
          <button type="button" class="primary" data-run-flow="${allocationEscape(flow.id)}" ${ready ? "" : "disabled"}>
            ${allocationState.busyId === flow.id ? "Kör..." : flow.id === "split-values" ? "Dela värden" : `Kör ${allocationEscape(flow.label)}`}
          </button>
          <span>${allocationEscape(allocationState.status)}</span>
        </div>
      `}
      ${missing.length ? `<p class="allocation-muted">Saknas: ${missing.map((item) => allocationEscape(item.label)).join(", ")}</p>` : ""}
    </section>
    ${renderResultPanel(allocationState.result)}
  `, compact && hasFileSlots ? `
    <label class="button-like" for="allocation-solo-files">${fileActionLabel}</label>
    <input id="allocation-solo-files" type="file" multiple hidden />
  ` : "");
  document.getElementById("allocation-solo-files")?.addEventListener("change", async (event) => routeAllocationFiles(event.target instanceof HTMLInputElement ? event.target.files : null, slots));
  bindFlowFields(document.getElementById("allocationRoot"));
  bindRunButtons();
}

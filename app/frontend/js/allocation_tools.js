const ALLOCATION_API = "/api/allokering";
const ALLOCATION_DB_NAME = "bemanning-allokering-files";
const ALLOCATION_DB_VERSION = 1;
const ALLOCATION_STORE = "files";
const ALLOCATION_HIDDEN_FLOW_IDS = new Set(["observations-update", "observations-sync", "update-check"]);
const ALLOCATION_KEY_OVERRIDES = { details: "orders", wms_buffert: "buffer" };
const ALLOCATION_FILE_WORDS = {
  max_csv: ["artikel_max", "article_max"],
  not_putaway: ["not_putaway", "not putaway", "ej_inlag", "ej inlag", "ejinlag"],
  remote_file: ["observations", "observationer"],
  values_file: ["values", "varden", "värden"],
};
const ALLOCATION_SLOT_LABELS = {
  orders: "Beställningslinjer",
  buffer: "Buffertpallar",
  overview: "Orderöversikt",
  dispatch: "Dispatchpallar",
  saldo: "Saldo / automation",
  items: "Item option",
  not_putaway: "Ej inlagrade",
  prognos: "Prognosfil",
  campaign: "Kampanjfil",
  max_csv: "artikel_max.csv",
  wms_receive: "Mottagningslogg",
  wms_booking: "Inlagringslogg",
  wms_trans: "Transaktionslogg",
  wms_pick: "Plocklogg",
  wms_correct: "Korrigeringslogg",
  remote_file: "Observationsfil",
  values_file: "Textfil med värden",
};
const ALLOCATION_SLOT_ORDER = [
  "orders", "buffer", "overview", "dispatch", "saldo", "items", "not_putaway",
  "prognos", "campaign", "max_csv", "wms_receive", "wms_booking", "wms_trans",
  "wms_pick", "wms_correct", "remote_file", "values_file",
];

const allocationState = {
  user: null,
  page: null,
  flows: [],
  visibleFlows: [],
  files: {},
  values: {},
  busyId: "",
  status: "",
  autoStatus: "",
  result: null,
  lastBufferSignature: "",
};

function allocationEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function allocationLogicalKey(key) {
  return ALLOCATION_KEY_OVERRIDES[key] || key;
}

function allocationFileInputKey(input) {
  return allocationLogicalKey(input.pool || input.key);
}

function allocationSlotLabel(key) {
  return ALLOCATION_SLOT_LABELS[allocationLogicalKey(key)] || key;
}

function allocationPrimaryTitle(page) {
  if (page === "uploads") return "Uppladdningar";
  if (page === "process") return "Bearbeta";
  if (page === "split") return "Dela";
  if (page === "trace") return "Härleda";
  return "Allokering";
}

function allocationPageActiveName(page) {
  if (page === "uploads") return "allocationUploads";
  if (page === "process") return "allocationProcess";
  if (page === "split") return "allocationSplit";
  if (page === "trace") return "allocationTrace";
  return "allocationUploads";
}

function allocationDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(ALLOCATION_DB_NAME, ALLOCATION_DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(ALLOCATION_STORE)) db.createObjectStore(ALLOCATION_STORE, { keyPath: "key" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function allocationStore(method, callback) {
  const db = await allocationDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(ALLOCATION_STORE, method);
    const store = tx.objectStore(ALLOCATION_STORE);
    const result = callback(store);
    tx.oncomplete = () => {
      db.close();
      resolve(result);
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

async function loadStoredAllocationFiles() {
  const db = await allocationDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(ALLOCATION_STORE, "readonly");
    const request = tx.objectStore(ALLOCATION_STORE).getAll();
    request.onsuccess = () => {
      const files = {};
      for (const item of request.result || []) {
        const blob = item.blob;
        files[item.key] = {
          key: item.key,
          name: item.name,
          size: item.size || blob?.size || 0,
          type: item.type || blob?.type || "",
          lastModified: item.lastModified || Date.now(),
          blob,
        };
      }
      db.close();
      resolve(files);
    };
    request.onerror = () => {
      db.close();
      reject(request.error);
    };
  });
}

async function saveAllocationFile(key, file) {
  const entry = {
    key,
    name: file.name || key,
    size: file.size || 0,
    type: file.type || "",
    lastModified: file.lastModified || Date.now(),
    blob: file,
  };
  await allocationStore("readwrite", (store) => store.put(entry));
  allocationState.files[key] = entry;
  if (key === "buffer") triggerAllocationObservationsUpdate(entry);
}

async function deleteAllocationFile(key) {
  await allocationStore("readwrite", (store) => store.delete(key));
  delete allocationState.files[key];
}

function allocationFileForForm(entry) {
  if (!entry) return null;
  return entry.blob || entry.file || null;
}

function allocationFileSize(size) {
  if (!size) return "";
  if (size < 1024 * 1024) return `${Math.round(size / 102.4) / 10} kB`;
  return `${Math.round(size / 1024 / 102.4) / 10} MB`;
}

async function allocationJson(path, options = {}) {
  const response = await fetch(path, { credentials: "include", ...options });
  const ct = response.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    let message = body?.detail || body?.message || body?.error || `HTTP ${response.status}`;
    if (typeof message === "object") message = message.message || JSON.stringify(message);
    throw new Error(message);
  }
  return body;
}

async function allocationPostForm(path, formData) {
  return allocationJson(path, { method: "POST", body: formData });
}

async function loadAllocationFlows() {
  const data = await allocationJson(`${ALLOCATION_API}/flows`);
  allocationState.flows = data.flows || [];
  allocationState.visibleFlows = allocationState.flows.filter((flow) => !ALLOCATION_HIDDEN_FLOW_IDS.has(flow.id));
}

function deriveAllocationSlots(flows) {
  const map = new Map();
  for (const flow of flows) {
    for (const input of flow.inputs || []) {
      if (input.type && input.type !== "file") continue;
      const key = allocationFileInputKey(input);
      if (!map.has(key)) {
        map.set(key, { key, label: ALLOCATION_SLOT_LABELS[key] || input.label, detect: new Set(input.detect || []) });
      } else {
        (input.detect || []).forEach((value) => map.get(key).detect.add(value));
      }
    }
  }
  const keys = ALLOCATION_SLOT_ORDER.filter((key) => map.has(key)).concat([...map.keys()].filter((key) => !ALLOCATION_SLOT_ORDER.includes(key)));
  return keys.map((key) => ({ ...map.get(key), detect: [...map.get(key).detect] }));
}

function fallbackAllocationSlot(file, slots, droppedCount) {
  const name = String(file.name || "").toLowerCase();
  const hinted = slots.find((slot) => (ALLOCATION_FILE_WORDS[slot.key] || []).some((word) => name.includes(word)));
  if (hinted) return hinted;
  return droppedCount === 1 && slots.length === 1 ? slots[0] : null;
}

async function detectAllocationFile(file) {
  const fd = new FormData();
  fd.append("file", file, file.name);
  return allocationPostForm(`${ALLOCATION_API}/detect`, fd);
}

async function routeAllocationFiles(files, slots) {
  const dropped = [...(files || [])];
  if (!dropped.length) return;
  window.allocationUploadActivity?.start();
  allocationState.status = "Identifierar filer...";
  renderAllocationPage();
  const assigned = [];
  const unknown = [];
  try {
    for (const file of dropped) {
      let target = null;
      try {
        const result = await detectAllocationFile(file);
        target = slots.find((slot) => (slot.detect || []).includes(result.file_type));
      } catch (e) {
        target = null;
      }
      if (!target) target = fallbackAllocationSlot(file, slots, dropped.length);
      if (target) {
        await saveAllocationFile(target.key, file);
        assigned.push({ file, slot: target });
      } else {
        unknown.push(file.name);
      }
    }
  } finally {
    window.allocationUploadActivity?.finish(assigned.length);
  }
  allocationState.status = assigned.length === 1 ? "1 fil inlagd." : assigned.length > 1 ? `${assigned.length} filer inlagda.` : "";
  if (unknown.length) showToast(`Kunde inte sortera: ${unknown.join(", ")}`, "warn");
  renderAllocationPage();
}

async function triggerAllocationObservationsUpdate(entry) {
  const signature = `${entry.name}:${entry.size}:${entry.lastModified}`;
  if (allocationState.lastBufferSignature === signature) return;
  allocationState.lastBufferSignature = signature;
  allocationState.autoStatus = "Observations uppdateras...";
  renderAllocationPage();
  const file = allocationFileForForm(entry);
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file, entry.name);
  try {
    const result = await allocationPostForm(`${ALLOCATION_API}/observations/update`, fd);
    allocationState.autoStatus = result.new_rows > 0
      ? `Observations uppdaterad: ${result.new_rows} nya pallid.`
      : "Observations kontrollerad.";
  } catch (error) {
    allocationState.lastBufferSignature = "";
    allocationState.autoStatus = "";
  }
  renderAllocationPage();
}

function currentAllocationSlots() {
  return deriveAllocationSlots(allocationState.visibleFlows);
}

function flowById(id) {
  return allocationState.visibleFlows.find((flow) => flow.id === id);
}

function combinedAllocationFlows() {
  return allocationState.visibleFlows.filter((flow) => flow.view === "combined");
}

function allocationFileRows(slots) {
  return slots.map((slot) => {
    const entry = allocationState.files[slot.key];
    const inputId = `allocation-file-${slot.key}`;
    return `
      <div class="allocation-file-slot ${entry ? "filled" : ""}">
        <div>
          <h3>${allocationEscape(slot.label)}</h3>
          <p>${entry ? `${allocationEscape(entry.name)} ${allocationFileSize(entry.size) ? `<span>${allocationEscape(allocationFileSize(entry.size))}</span>` : ""}` : "Ingen fil vald"}</p>
        </div>
        <div class="allocation-file-actions">
          <span class="allocation-file-badge">${entry ? "Inlagd" : "Ej fil"}</span>
          <label class="button-like" for="${inputId}">Välj</label>
          <input id="${inputId}" type="file" hidden data-slot="${allocationEscape(slot.key)}" />
          <button type="button" class="ghost danger" data-clear-slot="${allocationEscape(slot.key)}" ${entry ? "" : "disabled"}>×</button>
        </div>
      </div>
    `;
  }).join("");
}

function renderAllocationShell(content) {
  const root = document.getElementById("allocationRoot");
  if (!root) return;
  root.innerHTML = `
    <div class="section-title">${allocationEscape(allocationPrimaryTitle(allocationState.page))}</div>
    ${content}
  `;
  bindAllocationCommonEvents(root);
}

function bindAllocationCommonEvents(root) {
  root.querySelectorAll("input[type='file'][data-slot]").forEach((input) => {
    input.addEventListener("change", async () => {
      const slot = input.dataset.slot;
      const file = input.files?.[0];
      if (!slot || !file) return;
      window.allocationUploadActivity?.start();
      try {
        await saveAllocationFile(slot, file);
        allocationState.status = "1 fil inlagd.";
      } finally {
        window.allocationUploadActivity?.finish(1);
      }
      renderAllocationPage();
    });
  });
  root.querySelectorAll("[data-clear-slot]").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteAllocationFile(button.dataset.clearSlot);
      renderAllocationPage();
    });
  });
  const dropTargets = root.querySelectorAll("[data-allocation-drop]");
  dropTargets.forEach((target) => {
    target.addEventListener("dragover", (event) => {
      event.preventDefault();
      target.classList.add("drag-over");
    });
    target.addEventListener("dragleave", () => target.classList.remove("drag-over"));
    target.addEventListener("drop", async (event) => {
      event.preventDefault();
      target.classList.remove("drag-over");
      const slots = target.dataset.dropScope === "flow"
        ? slotsForFlow(flowById(target.dataset.flowId))
        : currentAllocationSlots();
      await routeAllocationFiles(event.dataTransfer?.files, slots);
    });
  });
}

function renderUploadsView() {
  const slots = currentAllocationSlots();
  const filled = slots.filter((slot) => allocationState.files[slot.key]).length;
  const productivityPanel = allocationState.user?.is_super_user
    ? '<section id="productivityUploadPanel" class="allocation-panel productivity-upload-panel" data-productivity-upload-panel></section>'
    : "";
  renderAllocationShell(`
    <section class="allocation-panel" data-allocation-drop>
      <div class="allocation-panel-head">
        <h2>Filer</h2>
        <div>
          <span class="allocation-muted">${filled}/${slots.length} inlagda</span>
          <label class="button-like primary" for="allocation-upload-all">Välj filer</label>
          <input id="allocation-upload-all" type="file" multiple hidden />
        </div>
      </div>
      ${allocationState.autoStatus ? `<p class="allocation-status">${allocationEscape(allocationState.autoStatus)}</p>` : ""}
      ${allocationState.status ? `<p class="allocation-status">${allocationEscape(allocationState.status)}</p>` : ""}
      <div class="allocation-file-grid">${allocationFileRows(slots)}</div>
    </section>
    ${productivityPanel}
  `);
  document.getElementById("allocation-upload-all")?.addEventListener("change", async (event) => {
    await routeAllocationFiles(event.target.files, slots);
  });
  const productivityPanelElement = document.querySelector("[data-productivity-upload-panel]");
  if (productivityPanelElement && window.productivityUploads?.setupPanel) {
    void window.productivityUploads.setupPanel(productivityPanelElement);
  }
}

function slotsForFlow(flow) {
  return deriveAllocationSlots(flow ? [flow] : []);
}

function missingForFlow(flow) {
  return (flow?.inputs || []).filter((input) => {
    if (!input.required) return false;
    if (input.type === "file") return !allocationState.files[allocationFileInputKey(input)];
    return !allocationState.values[input.key];
  });
}

function renderFlowFileList(flow) {
  const fileInputs = (flow?.inputs || []).filter((input) => input.type === "file");
  if (!fileInputs.length) return "";
  return `
    <div class="allocation-flow-files">
      ${fileInputs.map((input) => {
        const key = allocationFileInputKey(input);
        const entry = allocationState.files[key];
        const cls = entry ? "ok" : input.required ? "missing" : "optional";
        return `
          <div class="allocation-flow-file ${entry ? "filled" : ""}">
            <span class="allocation-file-tag ${cls}">${entry ? "✓" : input.required ? "✗" : "○"} ${allocationEscape(allocationSlotLabel(key))}${input.required ? "" : " (valfri)"}</span>
            <span>${entry ? allocationEscape(entry.name) : "Ingen fil"}</span>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderFieldInputs(flow) {
  const fields = (flow?.inputs || []).filter((input) => input.type !== "file");
  if (!fields.length) return "";
  return `
    <div class="allocation-fields">
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
      refreshAllocationRunButtons(root);
    });
  });
}

function refreshAllocationRunButtons(root) {
  root.querySelectorAll("[data-run-flow]").forEach((button) => {
    const flow = flowById(button.dataset.runFlow);
    const missing = missingForFlow(flow);
    button.disabled = Boolean(allocationState.busyId) || missing.length > 0;
  });
}

async function runAllocationFlow(flow) {
  if (!flow || allocationState.busyId) return;
  const missing = missingForFlow(flow);
  if (missing.length) return;
  allocationState.busyId = flow.id;
  allocationState.status = flow.id === "split-values" ? "Delar värden..." : `Kör ${flow.label}...`;
  allocationState.result = null;
  renderAllocationPage();
  const fd = new FormData();
  for (const input of flow.inputs || []) {
    if (input.type === "file") {
      const entry = allocationState.files[allocationFileInputKey(input)];
      const file = allocationFileForForm(entry);
      if (entry && file) fd.append(input.key, file, entry.name);
    } else {
      const value = allocationState.values[input.key] ?? input.default ?? "";
      if (value !== "") fd.append(input.key, value);
    }
  }
  try {
    const data = await allocationPostForm(`${ALLOCATION_API}/flow/${encodeURIComponent(flow.id)}`, fd);
    allocationState.result = { label: flow.label, data };
    allocationState.status = `Klart: ${flow.label}`;
  } catch (error) {
    showToast(error.message, "error");
    allocationState.status = "";
  } finally {
    allocationState.busyId = "";
    renderAllocationPage();
  }
}

function renderResultPanel(result) {
  if (!result?.data) return "";
  const data = result.data;
  const summaryEntries = Object.entries(data.summary || {});
  const tables = data.tables || [];
  return `
    <section class="allocation-panel allocation-result">
      <div class="allocation-panel-head">
        <h2>Resultat - ${allocationEscape(result.label)}</h2>
      </div>
      ${summaryEntries.length ? `
        <div class="allocation-summary">
          ${summaryEntries.map(([key, value]) => `
            <div><span>${allocationEscape(key)}</span><strong>${allocationEscape(value)}</strong></div>
          `).join("")}
        </div>
      ` : ""}
      ${data.text ? `<pre class="allocation-text-result">${allocationEscape(data.text)}</pre>` : ""}
      ${tables.map((entry) => renderResultTable(data.session_id, entry)).join("")}
      ${data.log?.length ? `<pre class="allocation-log">${allocationEscape(data.log.join("\n"))}</pre>` : ""}
    </section>
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
          <a class="button-like" href="${ALLOCATION_API}/download/${encodeURIComponent(sessionId)}/${encodeURIComponent(entry.key)}">Ladda ner CSV</a>
        </div>
      </div>
      <div class="table-wrap allocation-table-wrap">
        <table>
          <thead><tr>${(table.columns || []).map((column) => `<th>${allocationEscape(column)}</th>`).join("")}</tr></thead>
          <tbody>
            ${(table.rows || []).slice(0, 100).map((row) => `<tr>${row.map((cell) => `<td>${allocationEscape(cell)}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table>
      </div>
      ${table.truncated ? `<p class="allocation-muted">Förhandsvisningen visar de första raderna.</p>` : ""}
    </div>
  `;
}

function bindResultActions(root) {
  root.querySelectorAll("[data-open-excel]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await allocationJson(`${ALLOCATION_API}/open-excel`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: allocationState.result.data.session_id, key: button.dataset.openExcel }),
        });
      } catch (error) {
        showToast(error.message, "error");
      }
    });
  });
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
  renderAllocationShell(`
    ${!anyFile ? `
      <section class="allocation-upload-prompt" data-allocation-drop>
        <span>Inga filer inlagda.</span>
        <label class="button-like primary" for="allocation-combined-files">Välj filer</label>
        <input id="allocation-combined-files" type="file" multiple hidden />
        <a class="button-like" href="/uppladdningar.html">Uppladdningar</a>
      </section>
    ` : ""}
    <section class="allocation-panel" data-allocation-drop>
      <div class="allocation-panel-head">
        <h2>Körningar</h2>
        ${anyFile ? `<label class="button-like" for="allocation-combined-files">Välj fler filer</label><input id="allocation-combined-files" type="file" multiple hidden />` : ""}
      </div>
      ${allocationState.status ? `<p class="allocation-status">${allocationEscape(allocationState.status)}</p>` : ""}
      ${groups.map((group) => `
        <div class="allocation-action-group">
          <h3>${allocationEscape(group.name)}</h3>
          <div class="allocation-action-grid">
            ${group.flows.map((flow) => {
              const missing = missingForFlow(flow);
              const ready = missing.length === 0;
              return `
                <article class="allocation-action-card ${ready ? "ready" : ""}">
                  <h4>${allocationEscape(flow.label)}</h4>
                  <p>${allocationEscape(flow.description)}</p>
                  ${renderFlowFileList(flow)}
                  <button type="button" class="primary" data-run-flow="${allocationEscape(flow.id)}" ${ready && !allocationState.busyId ? "" : "disabled"}>
                    ${allocationState.busyId === flow.id ? "Kör..." : `Kör ${allocationEscape(flow.label)}`}
                  </button>
                </article>
              `;
            }).join("")}
          </div>
        </div>
      `).join("")}
    </section>
    ${renderResultPanel(allocationState.result)}
  `);
  const input = document.getElementById("allocation-combined-files");
  if (input) input.addEventListener("change", async (event) => routeAllocationFiles(event.target.files, currentAllocationSlots()));
  bindRunButtons();
}

function renderSoloFlowView(flowId) {
  const flow = flowById(flowId);
  if (!flow) {
    renderAllocationShell(`<section class="allocation-panel"><p>Vyn kunde inte laddas.</p></section>`);
    return;
  }
  const slots = slotsForFlow(flow);
  const missing = missingForFlow(flow);
  const ready = missing.length === 0 && !allocationState.busyId;
  renderAllocationShell(`
    <section class="allocation-panel" data-allocation-drop data-drop-scope="flow" data-flow-id="${allocationEscape(flow.id)}">
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
      ${missing.length ? `<p class="allocation-muted">Saknas: ${missing.map((item) => allocationEscape(item.label)).join(", ")}</p>` : ""}
    </section>
    ${renderResultPanel(allocationState.result)}
  `);
  document.getElementById("allocation-solo-files")?.addEventListener("change", async (event) => routeAllocationFiles(event.target.files, slots));
  bindFlowFields(document.getElementById("allocationRoot"));
  bindRunButtons();
}

function bindRunButtons() {
  const root = document.getElementById("allocationRoot");
  root.querySelectorAll("[data-run-flow]").forEach((button) => {
    button.addEventListener("click", () => runAllocationFlow(flowById(button.dataset.runFlow)));
  });
  bindResultActions(root);
}

function renderAllocationPage() {
  if (allocationState.page === "uploads") renderUploadsView();
  else if (allocationState.page === "process") renderCombinedView();
  else if (allocationState.page === "split") renderSoloFlowView("split-values");
  else if (allocationState.page === "trace") renderSoloFlowView("eftersok");
}

function renderAllocationUnavailable(message) {
  renderAllocationShell(`
    <section class="allocation-panel">
      <h2>Allokering kunde inte startas</h2>
      <p class="allocation-muted">${allocationEscape(message)}</p>
    </section>
  `);
}

async function initAllocationPage() {
  const root = document.getElementById("allocationRoot");
  if (!root) return;
  allocationState.page = root.dataset.allocationView || "uploads";
  const pageOptions = { requireAllocationTools: true };
  if (allocationState.page === "process") {
    pageOptions.requireAllocationProcess = true;
    pageOptions.denyRedirect = "/dela.html";
  }
  allocationState.user = await initPage(allocationPageActiveName(allocationState.page), pageOptions);
  if (!allocationState.user) return;
  root.innerHTML = `<div class="section-title">${allocationEscape(allocationPrimaryTitle(allocationState.page))}</div><section class="allocation-panel"><p>Laddar...</p></section>`;
  try {
    allocationState.files = await loadStoredAllocationFiles();
    await loadAllocationFlows();
    renderAllocationPage();
  } catch (error) {
    renderAllocationUnavailable(error.message);
  }
}

document.addEventListener("DOMContentLoaded", initAllocationPage);

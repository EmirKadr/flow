const ALLOCATION_API = "/api/allokering";
const ALLOCATION_DB_NAME = "flow-allokering-files";
const ALLOCATION_DB_VERSION = 1;
const ALLOCATION_STORE = "files";
const ALLOCATION_WORK_STATE_VERSION = 1;
const ALLOCATION_WORK_STATE_PREFIX = "flow-allocation-work-state-v1:";
const ALLOCATION_FILE_METADATA_CACHE_KEY = "flow-allocation-file-metadata-v1";
const ALLOCATION_BOOT_CACHE_KEY = "flow-allocation-boot-cache-v1";
const ALLOCATION_BOOT_CACHE_MAX_AGE_MS = 10 * 60 * 1000;
const ALLOCATION_HIDDEN_FLOW_IDS = new Set(["observations-update", "observations-sync", "update-check"]);
const ALLOCATION_PROCESS_AREA_PARAM = "__process_area_focus";
const ALLOCATION_PROCESS_AREA_OPTIONS = [
  { code: "GG", label: "GG" },
  { code: "MG", label: "MG" },
  { code: "AS", label: "AS" },
  { code: "EH", label: "EH" },
  { code: "R3", label: "R3" },
  { code: "ALLT", label: "Alla" },
];
const ALLOCATION_PROCESS_MATRIX = {
  GG: {
    company: "GG",
    excludeCustomers: ["6005"],
    filterLabel: "Filter: Bolag GG, exkl. kundnr 6005",
    visibleFlowIds: null,
  },
  MG: {
    company: "MG",
    excludeCustomers: ["40002", "90002"],
    filterLabel: "Filter: Bolag MG, exkl. kundnr 40002 och 90002",
    visibleFlowIds: null,
  },
  AS: {
    company: "",
    excludeCustomers: [],
    filterLabel: "",
    visibleFlowIds: null,
  },
  EH: {
    company: "",
    excludeCustomers: [],
    filterLabel: "",
    visibleFlowIds: null,
  },
  R3: {
    company: "",
    excludeCustomers: [],
    filterLabel: "",
    visibleFlowIds: null,
  },
  ALLT: {
    company: "",
    excludeCustomers: [],
    filterLabel: "",
    visibleFlowIds: null,
  },
  DEFAULT: {
    company: "",
    excludeCustomers: [],
    filterLabel: "",
    visibleFlowIds: null,
  },
};
const ALLOCATION_KEY_OVERRIDES = { details: "orders", wms_buffert: "buffer" };
const ALLOCATION_FILE_WORDS = {
  orders: ["v_ask_customer_order_details_all", "customer_order_details_all", "customer_order_details", "detalj kundorder"],
  buffer: ["v_ask_article_buffertpallet", "v_ask_article_bufferpallet", "article_buffertpallet", "article_bufferpallet", "buffertpall", "buffertpallet", "bufferpall", "bufferpallet"],
  overview: ["v_ask_order_overview", "order_overview", "orderoversikt"],
  dispatch: ["v_ask_dispatch_pallet", "dispatch_pallet", "dispatchpall"],
  saldo: ["v_ask_item_summary_stock_automation", "item_summary_stock_automation", "saldo ink", "automation"],
  items: ["item_option", "item option"],
  max_csv: ["artikel_max", "article_max"],
  not_putaway: ["not_putaway", "not putaway", "ej_inlag", "ej inlag", "ejinlag", "ej inlagrade"],
  campaign: ["kampanjplock", "kampanj", "campaign"],
  prognos: ["prognos idag", "prognos", "forecast"],
  wms_booking: ["v_ask_booking_putaway", "booking_putaway", "inlagringslogg"],
  wms_trans: ["v_ask_trans_log", "trans_log", "transaktionslogg"],
  wms_pick: ["v_ask_pick_log_full", "pick_log_full", "plocklogg"],
  productivity_pallet: ["v_ask_palletloading_log", "palletloading_log", "palllastningslogg"],
  remote_file: ["observations", "observationer"],
  values_file: ["values", "varden", "värden"],
};
const ALLOCATION_FILE_TYPE_PRIMARY_SLOT = {
  wms_booking: "wms_booking",
};
const ALLOCATION_SLOT_MIRRORS = {
  wms_booking: ["not_putaway"],
};
const PRODUCTIVITY_SHARED_UPLOAD_WORDS = [
  "v_ask_pick_log_full",
  "v_ask_trans_log",
  "v_ask_palletloading_log",
  "v_ask_kpi_target",
];
const ALLOCATION_SLOT_LABELS = {
  orders: "Detalj Kundorder(alla)",
  buffer: "Buffertpallar",
  overview: "Orderöversikt",
  dispatch: "Dispatchpallar",
  saldo: "Saldo ink. Automation",
  items: "Item option",
  not_putaway: "Ej inlagrade",
  prognos: "Prognosfil",
  campaign: "Kampanjfil",
  max_csv: "artikel_max.csv",
  wms_booking: "Inlagringslogg",
  wms_trans: "Transaktionslogg",
  wms_pick: "Plocklogg",
  productivity_pallet: "Palllastningslogg",
  remote_file: "Observationsfil",
  values_file: "Textfil med värden",
};
const ALLOCATION_SLOT_ORDER = [
  "orders", "buffer", "overview", "dispatch", "saldo", "items", "not_putaway",
  "prognos", "campaign", "max_csv", "wms_booking", "wms_trans", "wms_pick",
  "productivity_pallet", "remote_file", "values_file",
];
const PRODUCTIVITY_UPLOAD_SLOTS = [
  { key: "productivity_pallet", label: "Palllastningslogg", detect: [] },
];
const ALLOCATION_PRODUCTIVITY_KEYS = {
  wms_pick: "pick",
  wms_trans: "trans",
  productivity_pallet: "pallet",
};
const ALLOCATION_COREDATA_UPLOAD_SPECS = [
  { key: "article_max", prefix: "artikel_max" },
  { key: "article_max", prefix: "article_max" },
  { key: "item_attribute", prefix: "item_attribute" },
  { key: "kpi_target_rule", prefix: "kpi_target_rule" },
  { key: "location_cost", prefix: "location_cost" },
  { key: "item_option", prefix: "item_option" },
  { key: "pallet_type", prefix: "pallet_type" },
  { key: "item_alias", prefix: "item_alias" },
  { key: "dimension", prefix: "dimension" },
  { key: "location", prefix: "location" },
  { key: "custom", prefix: "custom" },
  { key: "item", prefix: "item" },
];
const ALLOCATION_COREDATA_SLOT_TYPES = {
  max_csv: "article_max",
  items: "item_option",
  custom: "custom",
  dimension: "dimension",
  item: "item",
  item_alias: "item_alias",
  item_option: "item_option",
  location: "location",
  location_cost: "location_cost",
  pallet_type: "pallet_type",
};
const ALLOCATION_COREDATA_DISPLAY_ORDER = [
  "article_max",
  "custom",
  "dimension",
  "item",
  "item_alias",
  "item_attribute",
  "item_option",
  "kpi_target_rule",
  "location",
  "location_cost",
  "pallet_type",
  "kpi",
];
const ALLOCATION_COREDATA_LABELS = {
  article_max: "artikel_max.csv",
  custom: "Custom",
  dimension: "Dimension",
  item: "Item",
  item_alias: "Item alias",
  item_attribute: "Item attribute",
  item_option: "Item option",
  kpi_target_rule: "KPI target rule",
  location: "Location",
  location_cost: "Location cost",
  pallet_type: "Pallet type",
  kpi: "KPI-Mål",
};
const ALLOCATION_CORE_FILES = {
  max_csv: {
    name: "artikel_max.csv",
    badge: "Kärnfil",
    sizeLabel: "Kärnfil",
  },
};
const ALLOCATION_COPY_ICON = `
  <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
    <rect x="8" y="8" width="10" height="10" rx="2"></rect>
    <path d="M6 16H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
  </svg>
`;

const allocationState = {
  user: null,
  page: null,
  flows: [],
  visibleFlows: [],
  files: {},
  coredata: {},
  processMatrix: null,
  values: {},
  busyId: "",
  status: "",
  autoStatus: "",
  result: null,
  lastBufferSignature: "",
  lastForecastSessionId: "",
  lastForecastLabel: "",
};

let allocationPopoverDismissBound = false;
let allocationUploadsPreloadPromise = null;

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

function allocationCoreDataFile(key) {
  const logicalKey = allocationLogicalKey(key);
  const fileType = ALLOCATION_COREDATA_SLOT_TYPES[logicalKey] || logicalKey;
  const entry = fileType ? allocationState.coredata?.files?.[fileType] : null;
  if (!entry?.uploaded) return null;
  return {
    name: entry.name || `${entry.prefix || fileType}.csv`,
    badge: "KÃ¤rnfil",
    sizeLabel: "KÃ¤rnfil",
  };
}

function allocationCoreDataBackedSlotIsHidden(key) {
  const logicalKey = allocationLogicalKey(key);
  if (allocationState.files[logicalKey]) return false;
  return Boolean(allocationCoreDataFile(logicalKey));
}

function allocationCoreFile(key) {
  const logicalKey = allocationLogicalKey(key);
  return allocationCoreDataFile(logicalKey) || ALLOCATION_CORE_FILES[logicalKey] || null;
}

function allocationDisplayFile(key) {
  const logicalKey = allocationLogicalKey(key);
  return allocationState.files[logicalKey] || allocationCoreFile(logicalKey);
}

function allocationFileMetadata(entry) {
  if (!entry?.key) return null;
  return {
    key: entry.key,
    name: entry.name || entry.key,
    size: Number(entry.size || entry.blob?.size || 0),
    type: entry.type || entry.blob?.type || "",
    lastModified: Number(entry.lastModified || Date.now()),
  };
}

function readCachedAllocationFileMetadata() {
  try {
    const raw = localStorage.getItem(ALLOCATION_FILE_METADATA_CACHE_KEY);
    if (!raw) return {};
    const payload = JSON.parse(raw);
    if (!payload || payload.version !== 1 || !Array.isArray(payload.files)) return {};
    return Object.fromEntries(payload.files.map((entry) => [
      entry.key,
      { ...entry, metadataOnly: true },
    ]).filter(([key]) => key));
  } catch (_error) {
    return {};
  }
}

function cacheAllocationFileMetadata(files = allocationState.files) {
  try {
    const metadata = Object.values(files || {})
      .map(allocationFileMetadata)
      .filter(Boolean)
      .sort((a, b) => String(a.key).localeCompare(String(b.key)));
    localStorage.setItem(ALLOCATION_FILE_METADATA_CACHE_KEY, JSON.stringify({
      version: 1,
      at: Date.now(),
      files: metadata,
    }));
  } catch (_error) {}
}

function readAllocationBootCache() {
  try {
    const raw = localStorage.getItem(ALLOCATION_BOOT_CACHE_KEY);
    if (!raw) return null;
    const payload = JSON.parse(raw);
    if (!payload || payload.version !== 1) return null;
    if (Date.now() - Number(payload.at || 0) > ALLOCATION_BOOT_CACHE_MAX_AGE_MS) return null;
    return payload;
  } catch (_error) {
    return null;
  }
}

function cacheAllocationBootData() {
  try {
    localStorage.setItem(ALLOCATION_BOOT_CACHE_KEY, JSON.stringify({
      version: 1,
      at: Date.now(),
      flows: allocationState.flows || [],
      coredata: allocationState.coredata || {},
      processMatrix: allocationState.processMatrix || null,
    }));
  } catch (_error) {}
}

function restoreAllocationBootData() {
  const boot = readAllocationBootCache();
  if (!boot) return false;
  if (Array.isArray(boot.flows)) {
    allocationState.flows = boot.flows;
    allocationState.visibleFlows = allocationState.flows.filter((flow) => !ALLOCATION_HIDDEN_FLOW_IDS.has(flow.id));
  }
  if (boot.coredata && typeof boot.coredata === "object") allocationState.coredata = boot.coredata;
  if (boot.processMatrix && typeof boot.processMatrix === "object") {
    allocationState.processMatrix = normalizeAllocationProcessMatrix(boot.processMatrix);
  }
  if (allocationState.page === "uploads") {
    allocationState.files = readCachedAllocationFileMetadata();
  }
  return Boolean(allocationState.visibleFlows.length);
}

function allocationRequiredSessionId(flow) {
  const required = flow?.requiresSessionFlow;
  if (!required) return "";
  if (required.flowId === "forecast") return allocationState.lastForecastSessionId || "";
  return "";
}

function allocationPrimaryTitle(page) {
  if (page === "uploads") return "Uppladdningar";
  if (page === "process") return "Bearbeta";
  if (page === "split") return "Dela";
  return "Allokering";
}

function allocationPageActiveName(page) {
  if (page === "uploads") return "allocationUploads";
  if (page === "process") return "allocationProcess";
  if (page === "split") return "allocationSplit";
  return "allocationUploads";
}

function allocationWorkStateKey(page = allocationState.page) {
  if (page !== "process" && page !== "split") return "";
  const userKey = allocationState.user?.id ?? allocationState.user?.username ?? "current";
  const focusKey = page === "process" ? `:${String(window.readAreaFocus?.() || "ALLT")}` : "";
  return `${ALLOCATION_WORK_STATE_PREFIX}${String(userKey)}:${page}${focusKey}`;
}

function allocationProcessAreaCode() {
  return String(window.areaFocusCode?.() || "").trim().toUpperCase();
}

function appendAllocationAreaFocus(formData) {
  const focusCode = allocationProcessAreaCode();
  if (focusCode) formData.append(ALLOCATION_PROCESS_AREA_PARAM, focusCode);
}

function normalizeAllocationProcessRule(rule = {}) {
  const company = String(rule.company || "").trim().toUpperCase();
  const rawExcluded = Array.isArray(rule.excludeCustomers)
    ? rule.excludeCustomers
    : Array.isArray(rule.exclude_customers)
      ? rule.exclude_customers
      : String(rule.excludeCustomers || rule.exclude_customers || "").split(/[,;\s]+/);
  const excludeCustomers = [...new Set(rawExcluded.map((value) => String(value || "").trim()).filter(Boolean))];
  const visibleFlowIds = Array.isArray(rule.visibleFlowIds)
    ? rule.visibleFlowIds.map((value) => String(value || "").trim()).filter(Boolean)
    : Array.isArray(rule.visible_flow_ids)
      ? rule.visible_flow_ids.map((value) => String(value || "").trim()).filter(Boolean)
      : null;
  const filterLabel = typeof rule.filterLabel === "string" ? rule.filterLabel : "";
  return {
    company,
    excludeCustomers,
    filterLabel,
    visibleFlowIds,
  };
}

function allocationProcessFallbackMatrix() {
  const matrix = {};
  for (const [code, rule] of Object.entries(ALLOCATION_PROCESS_MATRIX)) {
    matrix[code] = normalizeAllocationProcessRule(rule);
  }
  return {
    areas: ALLOCATION_PROCESS_AREA_OPTIONS.map((area) => ({ ...area })),
    flows: [],
    matrix,
  };
}

function normalizeAllocationProcessMatrix(data = null) {
  const fallback = allocationProcessFallbackMatrix();
  const matrix = { ...fallback.matrix };
  const incoming = data?.matrix && typeof data.matrix === "object" ? data.matrix : {};
  for (const [code, rule] of Object.entries(incoming)) {
    const areaCode = String(code || "").trim().toUpperCase();
    if (!areaCode) continue;
    matrix[areaCode] = normalizeAllocationProcessRule(rule);
  }
  const areas = Array.isArray(data?.areas) && data.areas.length
    ? data.areas.map((area) => ({
        code: String(area.code || area.value || "").trim().toUpperCase(),
        label: String(area.label || area.code || area.value || "").trim(),
      })).filter((area) => area.code)
    : fallback.areas;
  const flows = Array.isArray(data?.flows)
    ? data.flows.map((flow) => ({
        id: String(flow.id || "").trim(),
        label: String(flow.label || flow.id || "").trim(),
        category: String(flow.category || "").trim(),
      })).filter((flow) => flow.id)
    : [];
  return { areas, flows, matrix };
}

function allocationProcessMatrixData() {
  return allocationState.processMatrix || allocationProcessFallbackMatrix();
}

function allocationProcessRule(code = allocationProcessAreaCode()) {
  const matrix = allocationProcessMatrixData().matrix || {};
  return matrix[code] || matrix.DEFAULT || normalizeAllocationProcessRule(ALLOCATION_PROCESS_MATRIX.DEFAULT);
}

function allocationFlowVisibleForCurrentArea(flow) {
  if (allocationState.page !== "process") return true;
  const visibleFlowIds = allocationProcessRule().visibleFlowIds;
  return !Array.isArray(visibleFlowIds) || visibleFlowIds.includes(flow.id);
}

function allocationFlowsForCurrentView() {
  return allocationState.visibleFlows.filter((flow) => allocationFlowVisibleForCurrentArea(flow));
}

function allocationProcessFilterNotice() {
  if (allocationState.page !== "process") return "";
  return allocationProcessRule().filterLabel || "";
}

function serializableAllocationValues(values) {
  const result = {};
  for (const [key, value] of Object.entries(values || {})) {
    if (value == null) continue;
    result[key] = String(value);
  }
  return result;
}

function persistAllocationWorkState(overrides = {}) {
  const key = allocationWorkStateKey();
  if (!key) return;
  const snapshot = {
    version: ALLOCATION_WORK_STATE_VERSION,
    page: allocationState.page,
    values: serializableAllocationValues(allocationState.values),
    status: allocationState.busyId ? "" : String(allocationState.status || ""),
    result: allocationState.busyId ? null : allocationState.result,
    lastForecastSessionId: allocationState.lastForecastSessionId || "",
    lastForecastLabel: allocationState.lastForecastLabel || "",
    ...overrides,
  };
  try {
    sessionStorage.setItem(key, JSON.stringify(snapshot));
  } catch (error) {
    console.warn("Kunde inte spara lagerverktygets arbetslage.", error);
  }
}

function restoreAllocationWorkState() {
  const key = allocationWorkStateKey();
  if (!key) return;
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return;
    const snapshot = JSON.parse(raw);
    if (
      !snapshot
      || snapshot.version !== ALLOCATION_WORK_STATE_VERSION
      || snapshot.page !== allocationState.page
    ) {
      return;
    }
    if (snapshot.values && typeof snapshot.values === "object" && !Array.isArray(snapshot.values)) {
      allocationState.values = serializableAllocationValues(snapshot.values);
    }
    allocationState.status = typeof snapshot.status === "string" ? snapshot.status : "";
    allocationState.result = snapshot.result && typeof snapshot.result === "object" ? snapshot.result : null;
    allocationState.lastForecastSessionId = typeof snapshot.lastForecastSessionId === "string" ? snapshot.lastForecastSessionId : "";
    allocationState.lastForecastLabel = typeof snapshot.lastForecastLabel === "string" ? snapshot.lastForecastLabel : "";
  } catch (error) {
    try { sessionStorage.removeItem(key); } catch (e) {}
  }
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
      cacheAllocationFileMetadata(files);
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
  cacheAllocationFileMetadata();
  if (key === "buffer") triggerAllocationObservationsUpdate(entry);
}

async function deleteAllocationFile(key) {
  await allocationStore("readwrite", (store) => store.delete(key));
  delete allocationState.files[key];
  cacheAllocationFileMetadata();
  const productivityKey = ALLOCATION_PRODUCTIVITY_KEYS[key];
  if (productivityKey && window.productivityUploads?.deleteFile) {
    await window.productivityUploads.deleteFile(productivityKey);
  }
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

function allocationDisplaySizeLabel(entry, coreEntry) {
  if (entry) return allocationFileSize(entry.size);
  return coreEntry?.sizeLabel || "";
}

function allocationCoreDataItems() {
  const files = allocationState.coredata?.files || {};
  return ALLOCATION_COREDATA_DISPLAY_ORDER.map((key) => {
    const entry = files[key] || {};
    return {
      key,
      label: ALLOCATION_COREDATA_LABELS[key] || entry.label || key,
      uploaded: Boolean(entry.uploaded),
      name: entry.name || "",
      sizeLabel: entry.size_label || "",
    };
  });
}

async function allocationJson(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  if (method === "GET" && window.api?.get) {
    return await window.api.get(path, options);
  }
  let response;
  try {
    response = await fetch(path, { credentials: "include", ...options });
  } catch (error) {
    window.reportApiError?.(path, {
      method,
      status: 0,
      error_code: "network_error",
      message: error?.message || "Kunde inte ansluta till servern.",
    });
    if (method !== "GET" && !String(path).includes("/detect")) {
      window.flowLog?.error(`Bearbeta-anrop misslyckades: ${error?.message || "nätverksfel"}`, "Fel");
    }
    throw error;
  }
  const ct = response.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    let message = body?.detail || body?.message || body?.error || `HTTP ${response.status}`;
    if (typeof message === "object") message = message.message || JSON.stringify(message);
    const error = new Error(message);
    error.status = response.status;
    error.body = body;
    window.reportApiError?.(path, {
      method,
      status: response.status,
      body,
      message,
    });
    if (method !== "GET" && !String(path).includes("/detect")) {
      window.flowLog?.error(`Bearbeta-anrop misslyckades: ${message}`, "Fel");
    }
    throw error;
  }
  if (method !== "GET") window.api?.clearGetCache?.();
  if (method !== "GET" && !String(path).includes("/detect")) {
    const label = String(path).includes("/flow/")
      ? `Bearbeta körd: ${decodeURIComponent(String(path).split("/flow/")[1] || "flöde")}`
      : String(path).includes("/open-excel")
        ? "Excel öppnad"
        : String(path).includes("/process-matrix")
          ? "Bearbeta-matris sparad"
          : "Bearbeta-anrop klart";
    const rows = Array.isArray(body?.tables) ? ` (${body.tables.length} tabeller)` : "";
    window.flowLog?.success(`${label}${rows}`, "Klart");
  }
  return body;
}

async function allocationPostForm(path, formData) {
  return allocationJson(path, { method: "POST", body: formData });
}

async function loadAllocationCoreDataStatus() {
  try {
    allocationState.coredata = await allocationJson("/api/coredata/files");
    cacheAllocationBootData();
  } catch (error) {
    console.warn("Kunde inte lÃ¤sa kÃ¤rnfiler.", error);
    allocationState.coredata = {};
  }
}

async function loadAllocationFlows() {
  const data = await allocationJson(`${ALLOCATION_API}/flows`);
  allocationState.flows = data.flows || [];
  allocationState.visibleFlows = allocationState.flows.filter((flow) => !ALLOCATION_HIDDEN_FLOW_IDS.has(flow.id));
  cacheAllocationBootData();
}

async function loadAllocationProcessMatrix() {
  if (allocationState.page !== "process") return;
  try {
    const data = await allocationJson(`${ALLOCATION_API}/process-matrix`);
    allocationState.processMatrix = normalizeAllocationProcessMatrix(data);
    cacheAllocationBootData();
  } catch (error) {
    console.warn("Kunde inte lasa Bearbeta-matris.", error);
    allocationState.processMatrix = allocationProcessFallbackMatrix();
  }
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

function mergeUploadOnlySlots(slots) {
  if (allocationState.page !== "uploads") return slots;
  const map = new Map(slots.map((slot) => [slot.key, { ...slot }]));
  for (const slot of PRODUCTIVITY_UPLOAD_SLOTS) {
    if (!map.has(slot.key)) map.set(slot.key, { ...slot });
  }
  const keys = ALLOCATION_SLOT_ORDER
    .filter((key) => map.has(key))
    .concat([...map.keys()].filter((key) => !ALLOCATION_SLOT_ORDER.includes(key)));
  return keys.map((key) => map.get(key));
}

function allocationNameHintScore(slot, name) {
  return (ALLOCATION_FILE_WORDS[slot.key] || []).reduce((best, word) => {
    const normalized = String(word || "").toLowerCase();
    return normalized && name.includes(normalized) ? Math.max(best, normalized.length) : best;
  }, 0);
}

function hintedAllocationSlot(file, slots) {
  const name = String(file.name || "").toLowerCase();
  let bestSlot = null;
  let bestScore = 0;
  for (const slot of slots) {
    const score = allocationNameHintScore(slot, name);
    if (score > bestScore) {
      bestSlot = slot;
      bestScore = score;
    }
  }
  return bestSlot;
}

function fallbackAllocationSlot(file, slots, droppedCount, fallbackSlotKey = "") {
  const hinted = hintedAllocationSlot(file, slots);
  if (hinted) return hinted;
  if (fallbackSlotKey && droppedCount === 1) {
    const fallback = slots.find((slot) => slot.key === fallbackSlotKey);
    if (fallback) return fallback;
  }
  return droppedCount === 1 && slots.length === 1 ? slots[0] : null;
}

function allocationSlotsForDetectedType(fileType, slots) {
  const matches = slots.filter((slot) => (slot.detect || []).includes(fileType));
  if (!matches.length) return [];
  const preferredKey = ALLOCATION_FILE_TYPE_PRIMARY_SLOT[fileType];
  const preferred = preferredKey ? matches.find((slot) => slot.key === preferredKey) : null;
  return preferred ? [preferred] : [matches[0]];
}

function expandAllocationTargetSlots(primarySlot, slots) {
  if (!primarySlot) return [];
  const targets = [primarySlot];
  for (const mirrorKey of ALLOCATION_SLOT_MIRRORS[primarySlot.key] || []) {
    const mirror = slots.find((slot) => slot.key === mirrorKey);
    if (mirror && !targets.some((slot) => slot.key === mirror.key)) targets.push(mirror);
  }
  return targets;
}

function productivitySharedUploadCandidates(files) {
  return Array.from(files || []).filter((file) => {
    const name = String(file.name || "").toLowerCase();
    return PRODUCTIVITY_SHARED_UPLOAD_WORDS.some((word) => name.includes(word));
  });
}

function classifyAllocationCoreDataFile(file) {
  const stem = String(file?.name || "").toLowerCase().replace(/\.[^.]+$/, "");
  if (!stem) return null;
  for (const spec of ALLOCATION_COREDATA_UPLOAD_SPECS) {
    if (
      stem === spec.prefix
      || stem.startsWith(`${spec.prefix}-`)
      || stem.startsWith(`${spec.prefix}_`)
      || stem.startsWith(`${spec.prefix}.`)
      || stem.startsWith(`${spec.prefix} `)
    ) {
      return spec.key;
    }
  }
  return null;
}

async function uploadAllocationCoreDataFile(file) {
  return await api.postFile(
    `/api/coredata/files/raw?filename=${encodeURIComponent(file.name || "coredata.csv")}`,
    file,
  );
}

async function routeProductivityFilesFromSharedUpload(files) {
  const candidates = productivitySharedUploadCandidates(files);
  if (!candidates.length || !window.productivityUploads?.saveFiles) {
    return { saved: [], unknown: [], hiddenSaved: 0, recognized: [] };
  }
  try {
    return await window.productivityUploads.saveFiles(candidates, {
      reportUnknown: false,
      showToast: false,
      trackUploadActivity: false,
      syncAllocationUploads: false,
    });
  } catch (error) {
    console.warn("Kunde inte uppdatera produktivitetsfiler.", error);
    return { saved: [], unknown: [], hiddenSaved: 0, recognized: [] };
  }
}

async function detectAllocationFile(file) {
  const fd = new FormData();
  fd.append("file", file, file.name);
  return allocationPostForm(`${ALLOCATION_API}/detect`, fd);
}

async function routeAllocationFiles(files, slots, options = {}) {
  const dropped = [...(files || [])];
  if (!dropped.length) return;
  window.allocationUploadActivity?.start();
  allocationState.status = "Identifierar filer...";
  renderAllocationPage();
  const assigned = [];
  const coredataSaved = [];
  const unknown = [];
  let productivityResult = { saved: [], unknown: [], hiddenSaved: 0, recognized: [] };
  try {
    for (const file of dropped) {
      if (classifyAllocationCoreDataFile(file)) {
        try {
          const result = await uploadAllocationCoreDataFile(file);
          if (result.status) allocationState.coredata = result.status;
          cacheAllocationBootData();
          coredataSaved.push(file.name || "kÃ¤rnfil");
        } catch (error) {
          showToast(error.message || "Kunde inte uppdatera kÃ¤rnfil.", "error", 7000);
        }
        continue;
      }
      let targets = [];
      try {
        const result = await detectAllocationFile(file);
        targets = allocationSlotsForDetectedType(result.file_type, slots);
      } catch (e) {
        targets = [];
      }
      let target = targets[0] || null;
      if (!target) target = fallbackAllocationSlot(file, slots, dropped.length, options.fallbackSlotKey || "");
      targets = expandAllocationTargetSlots(target, slots);
      if (target) {
        for (const slot of targets) {
          await saveAllocationFile(slot.key, file);
          assigned.push({ file, slot });
        }
      } else {
        unknown.push(file.name);
      }
    }
    productivityResult = await routeProductivityFilesFromSharedUpload(dropped);
  } finally {
    const uploadedNames = new Set([
      ...assigned.map((item) => item.file?.name || ""),
      ...coredataSaved,
      ...(productivityResult.recognized || productivityResult.saved || []),
    ].filter(Boolean));
    window.allocationUploadActivity?.finish(uploadedNames.size);
  }
  const productivityNames = new Set(productivityResult.recognized || productivityResult.saved || []);
  const visibleUnknown = unknown.filter((name) => !productivityNames.has(name));
  const uploadedNames = new Set([
    ...assigned.map((item) => item.file?.name || ""),
    ...coredataSaved,
    ...(productivityResult.recognized || productivityResult.saved || []),
  ].filter(Boolean));
  if (uploadedNames.size === 1) allocationState.status = "1 fil inlagd.";
  else if (uploadedNames.size > 1) allocationState.status = `${uploadedNames.size} filer inlagda.`;
  else allocationState.status = "";
  if (visibleUnknown.length) showToast(`Kunde inte sortera: ${visibleUnknown.join(", ")}`, "warn");
  persistAllocationWorkState();
  renderAllocationPage();
}

function observationsUpdateStatusText(result) {
  const newRows = Number(result?.new_rows || 0);
  const sentRows = Number(result?.github_sent_rows || 0);
  const changedMax = Number(result?.article_max_changed_rows || 0);
  const newArticles = Number(result?.article_max_new_rows || 0);
  if (!newRows) {
    return `Observations kontrollerad: 0 nya pallid. artikel_max: ${changedMax} maxvärden ändrade.`;
  }
  const githubText = sentRows
    ? `${sentRows} skickade till GitHub`
    : "GitHub-push ej bekräftad";
  const articleText = newArticles
    ? `${changedMax} maxvärden ändrade, ${newArticles} nya artiklar`
    : `${changedMax} maxvärden ändrade`;
  return `Observations uppdaterad: ${newRows} nya pallid, ${githubText}. artikel_max: ${articleText}.`;
}

function observationsUpdateLogText(result) {
  const lines = [
    `Nya pallid hittade: ${Number(result?.new_rows || 0)}`,
    `Pallid skickade till GitHub: ${Number(result?.github_sent_rows || 0)}`,
    `GitHub-push: ${result?.pushed_to_github ? "bekräftad" : "ej bekräftad"}`,
    `Artikel-max-rader: ${Number(result?.article_max_rows || 0)}`,
    `Ändrade maxvärden: ${Number(result?.article_max_changed_rows || 0)}`,
    `Max upp/ned: ${Number(result?.article_max_increased_rows || 0)} / ${Number(result?.article_max_decreased_rows || 0)}`,
    `Nya artiklar i artikel_max: ${Number(result?.article_max_new_rows || 0)}`,
  ];
  const examples = Array.isArray(result?.article_max_changed_examples)
    ? result.article_max_changed_examples.slice(0, 3)
    : [];
  if (examples.length) {
    lines.push("Exempel:");
    examples.forEach((item) => {
      lines.push(`- ${item.artikelnummer}: ${item.before_max} -> ${item.after_max} (${item.before_pallid} -> ${item.after_pallid})`);
    });
  }
  return lines.join("\n");
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
    allocationState.autoStatus = observationsUpdateStatusText(result);
    window.appendAppLog?.(
      observationsUpdateLogText(result),
      Number(result?.new_rows || 0) && !result.pushed_to_github ? "warn" : "info",
      "Observations",
    );
  } catch (error) {
    allocationState.lastBufferSignature = "";
    allocationState.autoStatus = "";
    window.appendAppLog?.(error.message || "Observations-uppdatering misslyckades.", "error", "Observations");
  }
  renderAllocationPage();
}

function currentAllocationSlots() {
  return mergeUploadOnlySlots(deriveAllocationSlots(allocationFlowsForCurrentView()));
}

function visibleUploadFileSlots(slots) {
  if (allocationState.page !== "uploads") return slots;
  return slots.filter((slot) => !allocationCoreDataBackedSlotIsHidden(slot.key));
}

function flowById(id) {
  return allocationFlowsForCurrentView().find((flow) => flow.id === id);
}

function combinedAllocationFlows() {
  return allocationFlowsForCurrentView().filter((flow) => flow.view === "combined");
}

function allocationFileRows(slots) {
  return slots.map((slot) => {
    const entry = allocationState.files[slot.key];
    const coreEntry = entry ? null : allocationCoreFile(slot.key);
    const displayEntry = entry || coreEntry;
    const sizeLabel = allocationDisplaySizeLabel(entry, coreEntry);
    const inputId = `allocation-file-${slot.key}`;
    return `
      <div class="allocation-file-slot ${displayEntry ? "filled" : ""}" data-allocation-drop data-drop-slot="${allocationEscape(slot.key)}">
        <div>
          <h3>${allocationEscape(slot.label)}</h3>
          <p>${displayEntry ? `${allocationEscape(displayEntry.name)} ${sizeLabel ? `<span>${allocationEscape(sizeLabel)}</span>` : ""}` : "Ingen fil vald"}</p>
        </div>
        <div class="allocation-file-actions">
          <span class="allocation-file-badge">${entry ? "Inlagd" : coreEntry ? coreEntry.badge : "Ej fil"}</span>
          <label class="button-like" for="${inputId}">Välj</label>
          <input id="${inputId}" type="file" hidden data-slot="${allocationEscape(slot.key)}" />
          <button type="button" class="ghost danger" data-clear-slot="${allocationEscape(slot.key)}" ${entry ? "" : "disabled"}>×</button>
        </div>
      </div>
    `;
  }).join("");
}

function renderAllocationShell(content, headerActions = "") {
  const root = document.getElementById("allocationRoot");
  if (!root) return;
  root.innerHTML = `
    <div class="section-title allocation-section-title ${headerActions ? "has-actions" : ""}">
      <span>${allocationEscape(allocationPrimaryTitle(allocationState.page))}</span>
      ${headerActions ? `<div class="allocation-title-actions">${headerActions}</div>` : ""}
    </div>
    ${content}
  `;
  bindAllocationCommonEvents(root);
}

function allocationDropSlotsForTarget(target) {
  const flowScope = target.dataset.dropScope === "flow"
    ? target
    : target.closest("[data-drop-scope='flow']");
  if (flowScope) return slotsForFlow(flowById(flowScope.dataset.flowId));
  return currentAllocationSlots();
}

function bindAllocationCommonEvents(root) {
  root.querySelectorAll("input[type='file'][data-slot]").forEach((input) => {
    input.addEventListener("change", async () => {
      const slot = input.dataset.slot;
      const file = input.files?.[0];
      if (!slot || !file) return;
      const targetSlot = currentAllocationSlots().find((item) => item.key === slot);
      await routeAllocationFiles([file], targetSlot ? [targetSlot] : currentAllocationSlots(), { fallbackSlotKey: slot });
      input.value = "";
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
      event.stopPropagation();
      target.classList.add("drag-over");
    });
    target.addEventListener("dragleave", (event) => {
      event.stopPropagation();
      target.classList.remove("drag-over");
    });
    target.addEventListener("drop", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      target.classList.remove("drag-over");
      await routeAllocationFiles(
        event.dataTransfer?.files,
        allocationDropSlotsForTarget(target),
        { fallbackSlotKey: target.dataset.dropSlot || "" },
      );
    });
  });
}

function renderUploadsView() {
  const allSlots = currentAllocationSlots();
  const slots = visibleUploadFileSlots(allSlots);
  const filled = slots.filter((slot) => allocationDisplayFile(slot.key)).length;
  renderAllocationShell(`
    <section class="allocation-panel" data-allocation-drop>
      <div class="allocation-panel-head">
        <h2>Filer</h2>
        <div>
          <span class="allocation-muted">${filled}/${slots.length} inlagda</span>
          <button type="button" class="danger" id="allocation-clear-all-files">Rensa alla</button>
          <label class="button-like primary" for="allocation-upload-all">Välj filer</label>
          <input id="allocation-upload-all" type="file" multiple hidden />
        </div>
      </div>
      ${allocationState.autoStatus ? `<p class="allocation-status">${allocationEscape(allocationState.autoStatus)}</p>` : ""}
      ${allocationState.status ? `<p class="allocation-status">${allocationEscape(allocationState.status)}</p>` : ""}
      <div class="allocation-file-grid">${allocationFileRows(slots)}</div>
    </section>
    ${renderCoreDataFilesView()}
  `);
  document.getElementById("allocation-upload-all")?.addEventListener("change", async (event) => {
    await routeAllocationFiles(event.target.files, slots);
  });
  document.getElementById("allocation-clear-all-files")?.addEventListener("click", async () => {
    try {
      await window.clearAllUploadedFiles?.();
    } catch (error) {
      showToast(error.message || "Kunde inte rensa filerna.", "error", 7000);
    }
  });
}

function renderCoreDataFilesView() {
  const items = allocationCoreDataItems();
  if (!items.length) return "";
  const uploaded = items.filter((item) => item.uploaded).length;
  return `
    <section class="allocation-panel allocation-coredata-panel" data-allocation-drop>
      <div class="allocation-panel-head">
        <h2>Kärnfiler</h2>
        <div><span class="allocation-muted">${uploaded}/${items.length} finns</span></div>
      </div>
      <div class="allocation-file-grid compact">
        ${items.map((item) => `
          <div class="allocation-file-slot ${item.uploaded ? "filled" : ""}" data-allocation-drop>
            <div>
              <h3>${allocationEscape(item.label)}</h3>
              <p>${item.uploaded
                ? `${allocationEscape(item.name)} ${item.sizeLabel ? `<span>${allocationEscape(item.sizeLabel)}</span>` : ""}`
                : "Ingen kärnfil för verksamheten"}</p>
            </div>
            <div class="allocation-file-actions">
              <span class="allocation-file-badge">${item.uploaded ? "Kärnfil" : "Saknas"}</span>
            </div>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function slotsForFlow(flow) {
  return deriveAllocationSlots(flow ? [flow] : []);
}

function missingForFlow(flow) {
  const missing = (flow?.inputs || []).filter((input) => {
    if (!input.required) return false;
    if (input.type === "file") return !allocationDisplayFile(allocationFileInputKey(input));
    return !allocationState.values[input.key];
  });
  for (const input of flow?.coredata || []) {
    if (input.required && !allocationCoreDataFile(input.key)) missing.push({ ...input, type: "coredata" });
  }
  if (flow?.requiresSessionFlow && !allocationRequiredSessionId(flow)) {
    missing.push({
      key: "__session",
      type: "session",
      label: `${flow.requiresSessionFlow.label || "Körning"} körd`,
    });
  }
  return missing;
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
        const entry = allocationState.files[key];
        const coreEntry = entry ? null : allocationCoreFile(key);
        const displayEntry = entry || coreEntry;
        const cls = displayEntry ? "ok" : input.required ? "missing" : "optional";
        const prefix = displayEntry ? "✓" : input.required ? "✗" : "○";
        const suffix = coreEntry ? " (kärnfil)" : input.required || displayEntry ? "" : " (valfri)";
        return `
          <div class="allocation-flow-file ${displayEntry ? "filled" : ""}">
            <span class="allocation-file-tag ${cls}">${prefix} ${allocationEscape(allocationSlotLabel(key))}${suffix}</span>
            <span>${displayEntry ? allocationEscape(displayEntry.name) : "Ingen fil"}</span>
          </div>
        `;
      }).join("")}
      ${coreInputs.map((input) => {
        const entry = allocationCoreDataFile(input.key);
        const label = input.label || ALLOCATION_COREDATA_LABELS[input.key] || input.key;
        const cls = entry ? "ok" : input.required ? "missing" : "optional";
        const prefix = entry ? "✓" : input.required ? "✗" : "○";
        return `
          <div class="allocation-flow-file ${entry ? "filled" : ""}">
            <span class="allocation-file-tag ${cls}">${prefix} ${allocationEscape(label)} (kärnfil)</span>
            <span>${entry ? allocationEscape(entry.name) : "Saknas"}</span>
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
  if (missing.length) return;
  allocationState.busyId = flow.id;
  allocationState.status = flow.id === "split-values" ? "Delar värden..." : `Kör ${flow.label}...`;
  allocationState.result = null;
  persistAllocationWorkState({ status: "", result: null });
  renderAllocationPage();
  const fd = new FormData();
  if (allocationState.page === "process") {
    appendAllocationAreaFocus(fd);
  }
  if (flow.requiresSessionFlow?.flowId === "forecast") {
    fd.append("forecast_session_id", allocationState.lastForecastSessionId || "");
  }
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
    if ((data.flow_id || flow.id) === "forecast" && data.session_id) {
      allocationState.lastForecastSessionId = data.session_id;
      allocationState.lastForecastLabel = `${flow.label} ${new Date().toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" })}`;
    }
    allocationState.status = `Klart: ${flow.label}`;
    await copyOrdersaldoCompleteOrders(data);
  } catch (error) {
    showToast(error.message, "error");
    allocationState.status = "";
  } finally {
    allocationState.busyId = "";
    persistAllocationWorkState();
    renderAllocationPage();
  }
}

async function copyOrdersaldoCompleteOrders(data) {
  if (data?.flow_id !== "ordersaldo") return;
  const completeTable = (data.tables || []).find((entry) => entry.key === "complete");
  const orderCount = Number(completeTable?.table?.row_count || 0);
  if (!data.session_id || !orderCount) {
    showToast("Inga kompletta ordrar att kopiera", "info", 2500);
    return;
  }
  try {
    const columnData = await allocationJson(
      `${ALLOCATION_API}/table-column/${encodeURIComponent(data.session_id)}/complete/0`,
    );
    await writeClipboardText(columnData.text || "");
    showToast(`${orderCount} kompletta ordrar kopierade`, "success", 2500);
  } catch (error) {
    showToast(error.message || "Kunde inte kopiera kompletta ordrar.", "error", 7000);
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
  const tables = allocationResultTables(data);
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
      ${renderTextResult(data.text)}
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
  root.querySelectorAll("[data-copy-text-result]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const text = button.closest(".allocation-text-result-wrap")?.querySelector("[data-result-text]")?.textContent || "";
        await writeClipboardText(text);
        showToast("Text kopierad", "success", 2000);
      } catch (error) {
        showToast(error.message || "Kunde inte kopiera texten.", "error", 7000);
      }
    });
  });
  root.querySelectorAll("[data-copy-column]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const sessionId = allocationState.result?.data?.session_id;
        const key = button.dataset.copyKey;
        const columnIndex = button.dataset.copyColumn;
        if (!sessionId || !key || columnIndex == null) throw new Error("Resultatet kunde inte hittas.");
        const data = await allocationJson(
          `${ALLOCATION_API}/table-column/${encodeURIComponent(sessionId)}/${encodeURIComponent(key)}/${encodeURIComponent(columnIndex)}`,
        );
        await writeClipboardText(data.text || "");
        showToast("Kolumn kopierad", "success", 2000);
      } catch (error) {
        showToast(error.message || "Kunde inte kopiera kolumnen.", "error", 7000);
      }
    });
  });
  root.querySelectorAll("[data-open-excel]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await allocationJson(`${ALLOCATION_API}/open-excel`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: allocationState.result.data.session_id, key: button.dataset.openExcel }),
        });
        showToast("Excel öppnas", "success", 2500);
      } catch (error) {
        showToast(error.message, "error");
      }
    });
  });
  root.querySelectorAll("[data-download-csv]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const sessionId = allocationState.result?.data?.session_id;
        const key = button.dataset.downloadCsv;
        if (!sessionId || !key) throw new Error("Resultatet kunde inte hittas.");
        const filename = `${button.dataset.downloadLabel || key}.csv`;
        await api.download(`${ALLOCATION_API}/download/${encodeURIComponent(sessionId)}/${encodeURIComponent(key)}`, filename);
      } catch (error) {
        showToast(error.message || "Kunde inte ladda ner CSV-filen.", "error");
      }
    });
  });
}

function renderFlowChip(flow) {
  const missing = missingForFlow(flow);
  const ready = missing.length === 0;
  const running = allocationState.busyId === flow.id;
  const fileList = renderFlowFileList(flow);
  const label = allocationEscape(flow.label);
  return `
    <div class="allocation-flow-chip ${ready ? "ready" : ""}" data-allocation-drop data-drop-scope="flow" data-flow-id="${allocationEscape(flow.id)}">
      <div class="allocation-flow-chip-row">
        <button type="button" class="allocation-flow-run" data-run-flow="${allocationEscape(flow.id)}" ${ready && !allocationState.busyId ? "" : "disabled"}>
          ${running ? "Kör…" : label}
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

function ensureFlowPopoverDismiss() {
  if (allocationPopoverDismissBound) return;
  allocationPopoverDismissBound = true;
  document.addEventListener("click", (event) => {
    const root = document.getElementById("allocationRoot");
    if (!root) return;
    if (event.target.closest("[data-flow-info]") || event.target.closest("[data-flow-popover]")) return;
    closeFlowPopovers(root);
  });
}

function canViewAllocationProcessMatrix() {
  return Boolean(window.canViewPage?.(allocationState.user, "allocationProcessMatrix") || allocationState.user?.is_super_user);
}

function canEditAllocationProcessMatrix() {
  return Boolean(window.canEditPage?.(allocationState.user, "allocationProcessMatrix") || allocationState.user?.is_super_user);
}

function allocationProcessMatrixAreas() {
  return allocationProcessMatrixData().areas || ALLOCATION_PROCESS_AREA_OPTIONS;
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
      company: String(rule.company || ""),
      excludeCustomers: [...(rule.excludeCustomers || [])],
      filterLabel: String(rule.filterLabel || ""),
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
            <th>Bolag</th>
            <th>Exkl. kundnr</th>
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
                <td>
                  <input type="text" data-matrix-company="${allocationEscape(code)}" value="${allocationEscape(rule.company || "")}" aria-label="Bolag ${allocationEscape(code)}" ${readonly ? "disabled" : ""} />
                </td>
                <td>
                  <input type="text" data-matrix-exclude="${allocationEscape(code)}" value="${allocationEscape((rule.excludeCustomers || []).join(", "))}" aria-label="Exkludera kundnr ${allocationEscape(code)}" ${readonly ? "disabled" : ""} />
                </td>
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
    const company = String(row.querySelector("[data-matrix-company]")?.value || "").trim();
    const excludeCustomers = String(row.querySelector("[data-matrix-exclude]")?.value || "")
      .split(/[,;\s]+/)
      .map((value) => value.trim())
      .filter(Boolean);
    const allFlows = row.querySelector("[data-matrix-all-flows]")?.checked;
    const visibleFlowIds = allFlows
      ? null
      : [...row.querySelectorAll("[data-matrix-flow]:checked")].map((input) => input.value);
    matrix[code] = { company, excludeCustomers, visibleFlowIds };
  });
  return matrix;
}

async function openAllocationProcessMatrixModal() {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  let draft = allocationProcessMatrixDraft();
  const canEditMatrix = canEditAllocationProcessMatrix();
  backdrop.innerHTML = `
    <div class="modal wide allocation-process-matrix-modal">
      <h2>Bearbeta-matris</h2>
      <div id="allocation-process-matrix-editor"></div>
      <div class="actions">
        ${canEditMatrix ? `<button type="button" id="allocation-process-matrix-defaults">Standard</button>` : ""}
        <button type="button" id="allocation-process-matrix-cancel">Avbryt</button>
        ${canEditMatrix ? `<button type="button" class="primary" id="allocation-process-matrix-save">Spara</button>` : ""}
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);
  const editor = backdrop.querySelector("#allocation-process-matrix-editor");
  renderAllocationProcessMatrixEditor(editor, draft, !canEditMatrix);

  backdrop.querySelector("#allocation-process-matrix-cancel").addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("#allocation-process-matrix-defaults")?.addEventListener("click", () => {
    draft = allocationProcessMatrixDraft(true);
    renderAllocationProcessMatrixEditor(editor, draft);
  });
  backdrop.querySelector("#allocation-process-matrix-save")?.addEventListener("click", async () => {
    const button = backdrop.querySelector("#allocation-process-matrix-save");
    button.disabled = true;
    try {
      const response = await allocationJson(`${ALLOCATION_API}/process-matrix`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matrix: collectAllocationProcessMatrixDraft(editor) }),
      });
      allocationState.processMatrix = normalizeAllocationProcessMatrix(response);
      backdrop.remove();
      renderAllocationPage();
      showToast("Bearbeta-matris sparades.", "success", 2500);
    } catch (error) {
      button.disabled = false;
      showToast(error.message || "Kunde inte spara Bearbeta-matris.", "error", 7000);
    }
  });
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) backdrop.remove();
  });
}

function renderCombinedView() {
  const flows = combinedAllocationFlows();
  const filterNotice = allocationProcessFilterNotice();
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
  const matrixButton = canViewAllocationProcessMatrix()
    ? `<button type="button" id="allocation-process-matrix">Matris</button>`
    : "";
  renderAllocationShell(`
    <section class="allocation-panel allocation-panel--compact" data-allocation-drop>
      ${!anyFile ? `<p class="allocation-status">Inga filer inlagda. Dra filer hit eller använd Välj filer.</p>` : ""}
      ${filterNotice ? `<p class="allocation-status">${allocationEscape(filterNotice)}</p>` : ""}
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
    ${matrixButton}
    <label class="button-like" for="allocation-combined-files">${fileActionLabel}</label>
    <input id="allocation-combined-files" type="file" multiple hidden />
  `);
  const input = document.getElementById("allocation-combined-files");
  if (input) input.addEventListener("change", async (event) => routeAllocationFiles(event.target.files, currentAllocationSlots()));
  document.getElementById("allocation-process-matrix")?.addEventListener("click", openAllocationProcessMatrixModal);
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
  document.getElementById("allocation-solo-files")?.addEventListener("change", async (event) => routeAllocationFiles(event.target.files, slots));
  bindFlowFields(document.getElementById("allocationRoot"));
  bindRunButtons();
}

function bindRunButtons() {
  const root = document.getElementById("allocationRoot");
  root.querySelectorAll("[data-run-flow]").forEach((button) => {
    button.addEventListener("click", () => runAllocationFlow(flowById(button.dataset.runFlow)));
  });
  bindFlowInfoToggles(root);
  bindResultActions(root);
}

function renderAllocationPage() {
  if (allocationState.page === "uploads") renderUploadsView();
  else if (allocationState.page === "process") renderCombinedView();
  else if (allocationState.page === "split") renderSoloFlowView("split-values");
}

function renderAllocationUnavailable(message) {
  renderAllocationShell(`
    <section class="allocation-panel">
      <h2>Allokering kunde inte startas</h2>
      <p class="allocation-muted">${allocationEscape(message)}</p>
    </section>
  `);
}

function handleAllocationAreaFocusChanged() {
  const root = document.getElementById("allocationRoot");
  if (!root || !allocationState.user || allocationState.page !== "process" || allocationState.busyId) return;
  allocationState.values = {};
  allocationState.status = "";
  allocationState.result = null;
  restoreAllocationWorkState();
  renderAllocationPage();
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
  ensureFlowPopoverDismiss();
  const restoredFromCache = restoreAllocationBootData();
  if (restoredFromCache) renderAllocationPage();
  else root.innerHTML = `<div class="section-title">${allocationEscape(allocationPrimaryTitle(allocationState.page))}</div><section class="allocation-panel"><p>Laddar...</p></section>`;
  try {
    const storedFilesPromise = loadStoredAllocationFiles();
    let workStateRestored = false;
    const restoreWorkStateOnce = () => {
      if (workStateRestored) return;
      restoreAllocationWorkState();
      workStateRestored = true;
    };

    if (allocationState.page === "uploads") {
      const cachedMetadata = Object.keys(allocationState.files || {}).length
        ? allocationState.files
        : readCachedAllocationFileMetadata();
      if (!restoredFromCache && Object.keys(cachedMetadata).length) {
        allocationState.files = cachedMetadata;
      }
      await Promise.all([
        loadAllocationFlows(),
        loadAllocationProcessMatrix(),
        loadAllocationCoreDataStatus(),
      ]);
      if (!restoredFromCache && Object.keys(allocationState.files || {}).length) {
        restoreWorkStateOnce();
        renderAllocationPage();
      }
      allocationState.files = await storedFilesPromise;
    } else {
      const [storedFiles] = await Promise.all([
        storedFilesPromise,
        loadAllocationFlows(),
        loadAllocationProcessMatrix(),
        loadAllocationCoreDataStatus(),
      ]);
      allocationState.files = storedFiles;
    }
    if (allocationState.page === "uploads" && window.productivityUploads?.syncAllocationUploads) {
      void (async () => {
        try {
          await window.productivityUploads.syncAllocationUploads();
          allocationState.files = await loadStoredAllocationFiles();
          cacheAllocationFileMetadata();
          renderAllocationPage();
        } catch (error) {
          console.warn("Kunde inte synka produktivitetsfiler till Uppladdningar.", error);
        }
      })();
    }
    restoreWorkStateOnce();
    renderAllocationPage();
  } catch (error) {
    renderAllocationUnavailable(error.message);
  }
}

window.addEventListener("flow:uploadsCleared", async () => {
  const root = document.getElementById("allocationRoot");
  if (!root || !allocationState.user) return;
  allocationState.files = await loadStoredAllocationFiles();
  cacheAllocationFileMetadata();
  await loadAllocationCoreDataStatus();
  allocationState.status = "Vanliga filval rensade. Kärnfiler ligger kvar.";
  allocationState.autoStatus = "";
  allocationState.lastBufferSignature = "";
  renderAllocationPage();
});

window.addEventListener("flow:allocationFilesChanged", async () => {
  const root = document.getElementById("allocationRoot");
  if (!root || !allocationState.user) return;
  allocationState.files = await loadStoredAllocationFiles();
  cacheAllocationFileMetadata();
  renderAllocationPage();
});

window.addEventListener("flow:areaFocusChanged", handleAllocationAreaFocusChanged);

window.preloadAllocationUploadsData = function preloadAllocationUploadsData() {
  if (allocationUploadsPreloadPromise) return allocationUploadsPreloadPromise;
  allocationUploadsPreloadPromise = Promise.allSettled([
    loadStoredAllocationFiles(),
    loadAllocationFlows(),
    loadAllocationCoreDataStatus(),
  ]).finally(() => {
    cacheAllocationBootData();
    allocationUploadsPreloadPromise = null;
  });
  return allocationUploadsPreloadPromise;
};

document.addEventListener("DOMContentLoaded", initAllocationPage);

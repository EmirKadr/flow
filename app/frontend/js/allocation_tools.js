const ALLOCATION_API = "/api/allokering";
const ALLOCATION_DB_NAME = "flow-allokering-files";
const ALLOCATION_DB_VERSION = 1;
const ALLOCATION_STORE = "files";
const ALLOCATION_WORK_STATE_VERSION = 1;
const ALLOCATION_WORK_STATE_PREFIX = "flow-allocation-work-state-v1:";
const ALLOCATION_FILE_METADATA_CACHE_KEY = "flow-allocation-file-metadata-v1";
const ALLOCATION_BOOT_CACHE_KEY = "flow-allocation-boot-cache-v1";
const ALLOCATION_BOOT_CACHE_MAX_AGE_MS = 10 * 60 * 1000;
const ALLOCATION_FILE_PREVIEW_MAX_BYTES = 256 * 1024;
const ALLOCATION_FILE_PREVIEW_MAX_ROWS = 120;
const ALLOCATION_FILE_PREVIEW_MAX_COLUMNS = 40;
const ALLOCATION_FILE_PREVIEW_BINARY_EXTENSIONS = new Set([
  ".xls", ".xlsx", ".xlsm", ".zip", ".parquet", ".pdf",
]);
const ALLOCATION_HIDDEN_FLOW_IDS = new Set(["observations-update", "observations-sync", "update-check"]);
const ALLOCATION_PROCESS_AREA_PARAM = "__process_area_focus";
const ALLOCATION_YTGENERERING_UTL_MIN = 1;
const ALLOCATION_YTGENERERING_UTL_MAX = 652;
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
    ytgenereringUtlMin: 1,
    ytgenereringUtlMax: 652,
  },
  MG: {
    company: "MG",
    excludeCustomers: ["40002", "90002"],
    filterLabel: "Filter: Bolag MG, exkl. kundnr 40002 och 90002",
    visibleFlowIds: null,
    ytgenereringUtlMin: 205,
    ytgenereringUtlMax: 652,
  },
  AS: {
    company: "",
    excludeCustomers: [],
    filterLabel: "",
    visibleFlowIds: null,
    ytgenereringUtlMin: 1,
    ytgenereringUtlMax: 652,
  },
  EH: {
    company: "",
    excludeCustomers: [],
    filterLabel: "",
    visibleFlowIds: null,
    ytgenereringUtlMin: 1,
    ytgenereringUtlMax: 652,
  },
  R3: {
    company: "",
    excludeCustomers: [],
    filterLabel: "",
    visibleFlowIds: null,
    ytgenereringUtlMin: 1,
    ytgenereringUtlMax: 652,
  },
  ALLT: {
    company: "",
    excludeCustomers: [],
    filterLabel: "",
    visibleFlowIds: null,
    ytgenereringUtlMin: 1,
    ytgenereringUtlMax: 652,
  },
  DEFAULT: {
    company: "",
    excludeCustomers: [],
    filterLabel: "",
    visibleFlowIds: null,
    ytgenereringUtlMin: 1,
    ytgenereringUtlMax: 652,
  },
};
const ALLOCATION_KEY_OVERRIDES = { details: "orders", wms_buffert: "buffer" };
const ALLOCATION_FILE_WORDS = {
  orders: ["v_ask_customer_order_details_all", "customer_order_details_all", "customer_order_details", "detalj kundorder"],
  buffer: ["v_ask_article_buffertpallet", "v_ask_article_bufferpallet", "article_buffertpallet", "article_bufferpallet", "buffertpall", "buffertpallet", "bufferpall", "bufferpallet"],
  overview: ["v_ask_order_overview", "order_overview", "orderoversikt"],
  dispatch: ["v_ask_dispatch_pallet", "dispatch_pallet", "dispatchpall"],
  custom_adr: ["v_ask_custom_adr", "custom_adr", "alternativ leveransadress"],
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
  custom_adr: "Alternativ leveransadress",
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
  "orders", "buffer", "overview", "dispatch", "custom_adr", "saldo", "items", "not_putaway",
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
const ALLOCATION_PERSISTENT_DATA_UPLOAD_SPECS = [
  { key: "article_max", prefix: "artikel_max" },
  { key: "article_max", prefix: "article_max" },
  { key: "dispatch_template", prefix: "dispatch_template" },
  { key: "item_attribute", prefix: "item_attribute" },
  { key: "kpi_target_rule", prefix: "kpi_target_rule" },
  { key: "location_cost", prefix: "location_cost" },
  { key: "item_security_info", prefix: "item_security_info" },
  { key: "item_option", prefix: "item_option" },
  { key: "pallet_type", prefix: "pallet_type" },
  { key: "trans_agency", prefix: "trans_agency" },
  { key: "trans_agency", prefix: "transportorer" },
  { key: "trans_agency", prefix: "transportor" },
  { key: "trans_agency", prefix: "agency" },
  { key: "trans_agency", prefix: "agencies" },
  { key: "item_alias", prefix: "item_alias" },
  { key: "dimension", prefix: "dimension" },
  { key: "location", prefix: "location" },
  { key: "location", prefix: "lagerplats" },
  { key: "location", prefix: "lagerplatser" },
  { key: "custom", prefix: "custom" },
  { key: "item", prefix: "item" },
];
const ALLOCATION_PERSISTENT_DATA_SLOT_TYPES = {
  max_csv: "article_max",
  items: "item_option",
  custom: "custom",
  dimension: "dimension",
  item: "item",
  item_alias: "item_alias",
  item_security_info: "item_security_info",
  item_option: "item_option",
  location: "location",
  location_cost: "location_cost",
  pallet_type: "pallet_type",
};
const ALLOCATION_PERSISTENT_DATA_DISPLAY_ORDER = [
  "article_max",
  "productivity_pick_observations",
  "productivity_trans_observations",
  "productivity_pallet_observations",
  "custom",
  "dimension",
  "dispatch_template",
  "item",
  "item_alias",
  "item_attribute",
  "item_security_info",
  "item_option",
  "kpi_target_rule",
  "location",
  "location_cost",
  "pallet_type",
  "trans_agency",
  "kpi",
];
const ALLOCATION_PERSISTENT_DATA_LABELS = {
  article_max: "artikel_max.csv",
  productivity_pick_observations: "Plocklogg sammanställd data",
  productivity_trans_observations: "Translogg sammanställd data",
  productivity_pallet_observations: "Palllastningslogg sammanställd data",
  custom: "Custom",
  dimension: "Dimension",
  dispatch_template: "Dispatch template",
  item: "Item",
  item_alias: "Item alias",
  item_attribute: "Item attribute",
  item_security_info: "Artikel säkerhetsinformation",
  item_option: "Item option",
  kpi_target_rule: "KPI target rule",
  location: "Location",
  location_cost: "Location cost",
  pallet_type: "Pallet type",
  trans_agency: "Transportörer",
  kpi: "KPI-Mål",
};
const ALLOCATION_COMPILED_DATA_KEYS = new Set([
  "article_max",
  "productivity_pick_observations",
  "productivity_trans_observations",
  "productivity_pallet_observations",
]);
const ALLOCATION_COMPILED_DATA_LABEL = "Sammanställd data";
const ALLOCATION_CORE_DATA_LABEL = "Kärnfil";
const ALLOCATION_AUTO_COPY_COLUMN_RULES = {
  ordersaldo: {
    tableKey: "complete",
    emptyToast: "Inga kompletta ordrar att kopiera",
    successLabel: "kompletta ordrar",
    errorToast: "Kunde inte kopiera kompletta ordrar.",
  },
  "goods-declaration": {
    tableKey: "clear_orders",
    emptyToast: "Inga klara ordernummer att kopiera",
    successLabel: "klara ordernummer",
    errorToast: "Kunde inte kopiera klara ordernummer.",
  },
};
const ALLOCATION_PERSISTENT_DATA_FILES = {
  max_csv: {
    key: "article_max",
    name: "artikel_max.csv",
    badge: ALLOCATION_COMPILED_DATA_LABEL,
    sizeLabel: ALLOCATION_COMPILED_DATA_LABEL,
    suffixLabel: "sammanställd data",
    kind: "compiled_data",
  },
};

function allocationDataKindForKey(key, entry = {}) {
  return entry.kind || (ALLOCATION_COMPILED_DATA_KEYS.has(key) ? "compiled_data" : "coredata");
}

function allocationDataBadge(kind) {
  return kind === "compiled_data" ? ALLOCATION_COMPILED_DATA_LABEL : ALLOCATION_CORE_DATA_LABEL;
}

function allocationDataSuffixLabel(key, entry = {}) {
  return allocationDataKindForKey(key, entry) === "compiled_data" ? "sammanställd data" : "kärnfil";
}

function allocationDataMissingText(kind) {
  return kind === "compiled_data" ? "Ingen sammanställd data för verksamheten" : "Ingen kärnfil för verksamheten";
}

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
  carrierClusters: null,
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

function allocationFileExtension(name) {
  const lower = String(name || "").toLowerCase();
  if (lower.endsWith(".csv.gz")) return ".csv.gz";
  const dot = lower.lastIndexOf(".");
  return dot >= 0 ? lower.slice(dot) : "";
}

function allocationFileLooksBinaryByName(name, type = "") {
  const lowerType = String(type || "").toLowerCase();
  if (lowerType.startsWith("text/") || lowerType.includes("csv") || lowerType.includes("json")) return false;
  return ALLOCATION_FILE_PREVIEW_BINARY_EXTENSIONS.has(allocationFileExtension(name));
}

function allocationBytesLookBinary(bytes) {
  const sampleLength = Math.min(bytes?.length || 0, 2048);
  if (!sampleLength) return false;
  let suspicious = 0;
  for (let index = 0; index < sampleLength; index += 1) {
    const value = bytes[index];
    if (value === 0) return true;
    if (value < 8 || (value > 13 && value < 32)) suspicious += 1;
  }
  return suspicious / sampleLength > 0.15;
}

function allocationDecodePreviewBytes(bytes) {
  try {
    return {
      text: new TextDecoder("utf-8", { fatal: true }).decode(bytes),
      encoding: "utf-8",
    };
  } catch (_error) {
    return {
      text: new TextDecoder("windows-1252").decode(bytes),
      encoding: "windows-1252",
    };
  }
}

function allocationParseDelimitedLine(line, delimiter) {
  const cells = [];
  let cell = "";
  let quoted = false;
  const text = String(line ?? "");
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === '"') {
      if (quoted && text[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === delimiter && !quoted) {
      cells.push(cell);
      cell = "";
    } else {
      cell += char;
    }
  }
  cells.push(cell);
  return cells;
}

function allocationPreviewDelimiter(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n")
    .split("\n")
    .filter((line) => line.trim())
    .slice(0, 20);
  if (!lines.length) return "";
  let bestDelimiter = "";
  let bestScore = 0;
  for (const delimiter of ["\t", ";", ","]) {
    const score = lines.reduce((sum, line) => sum + Math.max(0, allocationParseDelimitedLine(line, delimiter).length - 1), 0);
    if (score > bestScore) {
      bestDelimiter = delimiter;
      bestScore = score;
    }
  }
  return bestScore >= Math.max(1, Math.floor(lines.length / 2)) ? bestDelimiter : "";
}

function allocationPreviewContentHtml(text) {
  const normalized = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  if (!normalized) return `<p class="allocation-file-preview-message">Filen är tom.</p>`;
  const lines = normalized.split("\n").slice(0, ALLOCATION_FILE_PREVIEW_MAX_ROWS);
  const delimiter = allocationPreviewDelimiter(normalized);
  if (!delimiter) {
    return `<pre class="allocation-file-preview-pre">${allocationEscape(lines.join("\n"))}</pre>`;
  }
  const rows = lines
    .map((line) => allocationParseDelimitedLine(line, delimiter).slice(0, ALLOCATION_FILE_PREVIEW_MAX_COLUMNS))
    .filter((row) => row.some((cell) => String(cell || "").trim()));
  if (!rows.length || rows.every((row) => row.length <= 1)) {
    return `<pre class="allocation-file-preview-pre">${allocationEscape(lines.join("\n"))}</pre>`;
  }
  const header = rows[0];
  const bodyRows = rows.slice(1);
  return `
    <table class="allocation-file-preview-table">
      <thead>
        <tr>${header.map((cell, index) => `<th>${allocationEscape(cell || `Kolumn ${index + 1}`)}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${bodyRows.map((row) => `
          <tr>${header.map((_cell, index) => `<td>${allocationEscape(row[index] ?? "")}</td>`).join("")}</tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function openAllocationFilePreviewModal(preview) {
  document.querySelector("[data-allocation-preview-modal]")?.remove();
  const objectUrl = preview.objectUrl || "";
  const meta = [
    preview.sizeLabel || allocationFileSize(preview.size),
    preview.kind === "compiled_data" ? ALLOCATION_COMPILED_DATA_LABEL : preview.kind === "coredata" ? ALLOCATION_CORE_DATA_LABEL : "Vanlig fil",
    preview.encoding ? `Text: ${preview.encoding}` : "",
  ].filter(Boolean);
  const content = preview.unsupported
    ? `<p class="allocation-file-preview-message">Filen kan inte förhandsvisas direkt i appen. Öppna originalet för att se hela filen.</p>`
    : allocationPreviewContentHtml(preview.text || "");
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.dataset.allocationPreviewModal = "true";
  backdrop.innerHTML = `
    <div class="modal wide allocation-file-preview-modal" role="dialog" aria-modal="true" aria-labelledby="allocationFilePreviewTitle">
      <h2 id="allocationFilePreviewTitle">${allocationEscape(preview.title || preview.name || "Fil")}</h2>
      <div class="allocation-file-preview-meta">
        <strong>${allocationEscape(preview.name || preview.title || "Fil")}</strong>
        ${meta.length ? `<span>${allocationEscape(meta.join(" · "))}</span>` : ""}
      </div>
      ${preview.truncated ? `<p class="allocation-status">Visar första delen av filen.</p>` : ""}
      <div class="modal-table-scroll allocation-file-preview-scroll">
        ${content}
      </div>
      <div class="actions">
        ${objectUrl ? `<button type="button" data-open-preview-original>Öppna original</button>` : ""}
        <button type="button" class="primary" data-close-preview>Stäng</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);

  const close = () => {
    document.removeEventListener("keydown", onKeyDown);
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    backdrop.remove();
  };
  function onKeyDown(event) {
    if (event.key === "Escape") close();
  }

  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) close();
  });
  backdrop.querySelectorAll("[data-close-preview]").forEach((button) => button.addEventListener("click", close));
  backdrop.querySelector("[data-open-preview-original]")?.addEventListener("click", () => {
    window.open(objectUrl, "_blank", "noopener");
  });
  document.addEventListener("keydown", onKeyDown);
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

function allocationPersistentStatusFile(key) {
  const logicalKey = allocationLogicalKey(key);
  const fileType = ALLOCATION_PERSISTENT_DATA_SLOT_TYPES[logicalKey] || logicalKey;
  const entry = fileType ? allocationState.coredata?.files?.[fileType] : null;
  if (!entry?.uploaded) return null;
  const kind = allocationDataKindForKey(fileType, entry);
  const badge = allocationDataBadge(kind);
  return {
    key: fileType,
    name: entry.name || `${entry.prefix || fileType}.csv`,
    badge,
    sizeLabel: badge,
    suffixLabel: allocationDataSuffixLabel(fileType, { kind }),
    kind,
  };
}

function allocationPersistentDataBackedSlotIsHidden(key) {
  const logicalKey = allocationLogicalKey(key);
  if (allocationState.files[logicalKey]) return false;
  return Boolean(allocationPersistentStatusFile(logicalKey));
}

function allocationPersistentDataFile(key) {
  const logicalKey = allocationLogicalKey(key);
  return allocationPersistentStatusFile(logicalKey) || ALLOCATION_PERSISTENT_DATA_FILES[logicalKey] || null;
}

function allocationDisplayFile(key) {
  const logicalKey = allocationLogicalKey(key);
  return allocationState.files[logicalKey] || allocationPersistentDataFile(logicalKey);
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
  if (page === "settings") return "Inställningar";
  if (page === "split") return "Dela";
  return "Allokering";
}

function allocationPageActiveName(page) {
  if (page === "uploads") return "allocationUploads";
  if (page === "process") return "allocationProcess";
  if (page === "settings") return "allocationSettings";
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

function normalizeYtgenereringUtlNumber(value, fallback) {
  const parsed = Number.parseInt(String(value ?? "").trim(), 10);
  const number = Number.isFinite(parsed) ? parsed : fallback;
  return Math.max(ALLOCATION_YTGENERERING_UTL_MIN, Math.min(ALLOCATION_YTGENERERING_UTL_MAX, number));
}

function normalizeYtgenereringUtlRange(rule = {}) {
  let min = normalizeYtgenereringUtlNumber(rule.ytgenereringUtlMin ?? rule.ytgenerering_utl_min, ALLOCATION_YTGENERERING_UTL_MIN);
  let max = normalizeYtgenereringUtlNumber(rule.ytgenereringUtlMax ?? rule.ytgenerering_utl_max, ALLOCATION_YTGENERERING_UTL_MAX);
  if (min > max) [min, max] = [max, min];
  return { min, max };
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
  const utlRange = normalizeYtgenereringUtlRange(rule);
  return {
    company,
    excludeCustomers,
    filterLabel,
    visibleFlowIds,
    ytgenereringUtlMin: utlRange.min,
    ytgenereringUtlMax: utlRange.max,
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
    matrix[areaCode] = normalizeAllocationProcessRule({ ...(matrix[areaCode] || matrix.DEFAULT || {}), ...rule });
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

const ALLOCATION_CLUSTER_DEFAULT_TIMES = { asn: "11:00", arrive: "12:00", depart: "14:00" };
const ALLOCATION_CLUSTER_HUES = [350, 265, 150, 40, 210, 320, 175, 285, 25, 130, 195, 300];

function allocationCarrierClusterText(value) {
  const text = String(value ?? "").trim();
  return ["nan", "nat", "none", "null"].includes(text.toLowerCase()) ? "" : text;
}

function allocationHslToHex(h, s, l) {
  const sat = s / 100;
  const light = l / 100;
  const k = (n) => (n + h / 30) % 12;
  const a = sat * Math.min(light, 1 - light);
  const f = (n) => {
    const color = light - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
    return Math.round(255 * color).toString(16).padStart(2, "0");
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

// Bygg transportör -> färg där ett kluster delar basnyans och varje transportör i
// klustret får en egen ljushet. Manuella färger i `overrides` vinner över auto.
function allocationClusterColorMap(entries, overrides) {
  const overrideMap = overrides instanceof Map ? overrides : new Map();
  const clusterCarriers = new Map();
  const clusterOrder = [];
  (entries || []).forEach((entry) => {
    const carrierKey = String(entry.carrier || "Okänd");
    const clusterKey = String(entry.cluster || "").trim() || `__solo__:${carrierKey}`;
    if (!clusterCarriers.has(clusterKey)) {
      clusterCarriers.set(clusterKey, []);
      clusterOrder.push(clusterKey);
    }
    const carriers = clusterCarriers.get(clusterKey);
    if (!carriers.includes(carrierKey)) carriers.push(carrierKey);
  });
  const colorMap = new Map();
  clusterOrder.forEach((clusterKey, clusterIndex) => {
    const hue = ALLOCATION_CLUSTER_HUES[clusterIndex % ALLOCATION_CLUSTER_HUES.length];
    const carriers = clusterCarriers.get(clusterKey);
    const span = carriers.length;
    carriers.forEach((carrierKey, i) => {
      const light = span <= 1 ? 58 : 46 + Math.round((i / (span - 1)) * 26);
      colorMap.set(carrierKey, allocationHslToHex(hue, 65, light));
    });
  });
  overrideMap.forEach((color, carrier) => {
    const key = String(carrier || "");
    if (key && color) colorMap.set(key, color);
  });
  return colorMap;
}

function allocationCarrierClusterNumber(value) {
  const text = allocationCarrierClusterText(value).replace(",", ".");
  if (!text) return "";
  const parsed = Number.parseInt(text, 10);
  return Number.isFinite(parsed) ? String(parsed) : "";
}

function allocationCarrierClusterKey(value) {
  return allocationCarrierClusterText(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

function normalizeAllocationCarrierClusters(payload) {
  if (!payload) return null;
  const rows = Array.isArray(payload)
    ? payload
    : Array.isArray(payload.rows)
      ? payload.rows
      : [];
  const normalizedRows = rows.map((row, index) => {
    const carrierNum = allocationCarrierClusterText(row.carrierNum ?? row.carrier_num ?? row.agencyNum ?? row.agency_num ?? row.AGENCY_NUM);
    const description = allocationCarrierClusterText(row.description ?? row.agencyDesc ?? row.agency_desc ?? row.AGENCY_DESC ?? row.carrier ?? row.transportor);
    const alias = allocationCarrierClusterText(row.alias ?? row.agencyAlias ?? row.agency_alias ?? row.AGENCY_ALIAS);
    const label = alias || description || carrierNum;
    if (!label) return null;
    const asn = allocationCarrierClusterText(row.asn ?? row.agency_asn ?? row.agencyAsn ?? row.ASN);
    const arrive = allocationCarrierClusterText(row.arrive ?? row.agency_arrive ?? row.agencyArrive ?? row.ARRIVE);
    const depart = allocationCarrierClusterText(row.depart ?? row.agency_depart ?? row.agencyDepart ?? row.DEPART);
    return {
      id: allocationCarrierClusterText(row.id) || carrierNum || `row-${index + 1}`,
      carrierNum,
      description,
      alias,
      clusterGroup: allocationCarrierClusterText(row.clusterGroup ?? row.cluster_group ?? row.CLUSTER_GROUP ?? row.cluster),
      assignmentOrder: allocationCarrierClusterNumber(row.assignmentOrder ?? row.assignment_order ?? row.ASSIGNMENT_ORDER ?? row.order),
      startSeq: allocationCarrierClusterNumber(row.startSeq ?? row.start_seq ?? row.START_SEQ ?? row.from ?? row.utlFrom),
      endSeq: allocationCarrierClusterNumber(row.endSeq ?? row.end_seq ?? row.END_SEQ ?? row.to ?? row.utlTo),
      asn: asn || ALLOCATION_CLUSTER_DEFAULT_TIMES.asn,
      arrive: arrive || ALLOCATION_CLUSTER_DEFAULT_TIMES.arrive,
      depart: depart || ALLOCATION_CLUSTER_DEFAULT_TIMES.depart,
      color: allocationCarrierClusterText(row.color ?? row.colour),
    };
  }).filter(Boolean);
  normalizedRows.sort((a, b) => {
    const orderA = a.assignmentOrder === "" ? 10000 : Number(a.assignmentOrder);
    const orderB = b.assignmentOrder === "" ? 10000 : Number(b.assignmentOrder);
    return orderA - orderB || String(a.alias || a.description || a.carrierNum).localeCompare(String(b.alias || b.description || b.carrierNum), "sv");
  });
  const source = payload && !Array.isArray(payload) && typeof payload.source === "object"
    ? payload.source
    : { name: "Transportörer", rowCount: normalizedRows.length };
  return { version: 1, source, rows: normalizedRows };
}

function allocationCarrierClustersFromForecastTable(data) {
  if (data?.flow_id !== "forecast") return null;
  const tableEntry = (data.tables || []).find((entry) => entry.key === "forecast") || (data.tables || [])[0];
  const table = tableEntry?.table || {};
  const columns = Array.isArray(table.columns) ? table.columns : [];
  const carrierIndex = columns.findIndex((column) => {
    const key = allocationCarrierClusterKey(column);
    return key === "transportor" || key === "carrier" || key === "agency";
  });
  if (carrierIndex < 0 || !Array.isArray(table.rows)) return null;
  const seen = new Set();
  const rows = [];
  table.rows.forEach((row) => {
    const carrier = allocationCarrierClusterText(Array.isArray(row) ? row[carrierIndex] : "");
    const key = allocationCarrierClusterKey(carrier);
    if (!key || seen.has(key)) return;
    seen.add(key);
    const order = rows.length + 1;
    rows.push({
      id: `forecast-${order}`,
      description: carrier,
      alias: carrier,
      clusterGroup: carrier,
      assignmentOrder: String(order),
      startSeq: "",
      endSeq: "",
    });
  });
  return normalizeAllocationCarrierClusters({
    version: 1,
    source: { name: "Forecast", rowCount: rows.length, generated: true },
    rows,
  });
}

function allocationCarrierClustersForResult(data = allocationState.result?.data) {
  const fromData = normalizeAllocationCarrierClusters(data?.carrier_clusters);
  if (fromData?.rows?.length) return fromData;
  const fromForecast = allocationCarrierClustersFromForecastTable(data);
  if (fromForecast?.rows?.length) return fromForecast;
  return normalizeAllocationCarrierClusters(allocationState.carrierClusters);
}

function allocationHasCarrierClusters(data = allocationState.result?.data) {
  return Boolean(allocationCarrierClustersForResult(data)?.rows?.length);
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
    carrierClusters: normalizeAllocationCarrierClusters(allocationState.carrierClusters),
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
    allocationState.carrierClusters = normalizeAllocationCarrierClusters(snapshot.carrierClusters);
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

async function loadStoredAllocationFileEntry(key) {
  const db = await allocationDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(ALLOCATION_STORE, "readonly");
    const request = tx.objectStore(ALLOCATION_STORE).get(key);
    request.onsuccess = () => {
      const item = request.result;
      const blob = item?.blob;
      db.close();
      if (!item || !blob) {
        resolve(null);
        return;
      }
      resolve({
        key: item.key,
        name: item.name,
        size: item.size || blob.size || 0,
        type: item.type || blob.type || "",
        lastModified: item.lastModified || Date.now(),
        blob,
      });
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

async function readAllocationLocalFilePreview(entry) {
  const file = allocationFileForForm(entry);
  if (!file) throw new Error("Filen hittades inte lokalt.");
  let unsupported = allocationFileLooksBinaryByName(entry.name, entry.type);
  let text = "";
  let encoding = "";
  let truncated = false;
  if (!unsupported) {
    const buffer = await file.slice(0, ALLOCATION_FILE_PREVIEW_MAX_BYTES + 1).arrayBuffer();
    const bytes = new Uint8Array(buffer);
    truncated = bytes.length > ALLOCATION_FILE_PREVIEW_MAX_BYTES || Number(file.size || 0) > ALLOCATION_FILE_PREVIEW_MAX_BYTES;
    const previewBytes = bytes.slice(0, ALLOCATION_FILE_PREVIEW_MAX_BYTES);
    unsupported = allocationBytesLookBinary(previewBytes);
    if (!unsupported) {
      const decoded = allocationDecodePreviewBytes(previewBytes);
      text = decoded.text;
      encoding = decoded.encoding;
    }
  }
  return {
    name: entry.name,
    title: allocationSlotLabel(entry.key),
    size: entry.size || file.size || 0,
    sizeLabel: allocationFileSize(entry.size || file.size || 0),
    kind: "local",
    text,
    encoding,
    truncated,
    unsupported,
    objectUrl: URL.createObjectURL(file),
  };
}

async function openAllocationLocalFilePreview(slotKey) {
  const key = allocationLogicalKey(slotKey);
  let entry = allocationState.files[key];
  if (!entry || !allocationFileForForm(entry)) {
    entry = await loadStoredAllocationFileEntry(key);
    if (entry) allocationState.files[key] = entry;
  }
  if (!entry) throw new Error("Filen hittades inte lokalt.");
  openAllocationFilePreviewModal(await readAllocationLocalFilePreview(entry));
}

async function openAllocationPersistentFilePreview(fileKey) {
  const key = String(fileKey || "").trim();
  if (!key) return;
  const preview = await allocationJson(`/api/coredata/files/${encodeURIComponent(key)}/preview`, {
    skipCache: true,
    logGetUserEvent: true,
    logLabel: "Filförhandsvisning",
  });
  openAllocationFilePreviewModal({
    title: preview.label || preview.name || key,
    name: preview.name || key,
    size: Number(preview.size || 0),
    sizeLabel: preview.size_label || "",
    kind: preview.kind || "coredata",
    text: preview.text || "",
    encoding: preview.encoding || "",
    truncated: Boolean(preview.truncated),
  });
}

async function handleAllocationPreviewClick(button) {
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Öppnar...";
  try {
    if (button.dataset.previewFileSource === "persistent") {
      await openAllocationPersistentFilePreview(button.dataset.previewFileKey);
    } else {
      await openAllocationLocalFilePreview(button.dataset.previewFileKey);
    }
  } catch (error) {
    showToast(error.message || "Kunde inte öppna filen.", "error", 7000);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

function allocationFileSize(size) {
  if (!size) return "";
  if (size < 1024 * 1024) return `${Math.round(size / 102.4) / 10} kB`;
  return `${Math.round(size / 1024 / 102.4) / 10} MB`;
}

function allocationDisplaySizeLabel(entry, persistentEntry) {
  if (entry) return allocationFileSize(entry.size);
  return persistentEntry?.sizeLabel || "";
}

function allocationPersistentDataItems() {
  const files = allocationState.coredata?.files || {};
  return ALLOCATION_PERSISTENT_DATA_DISPLAY_ORDER.map((key) => {
    const entry = files[key] || {};
    const kind = allocationDataKindForKey(key, entry);
    return {
      key,
      label: ALLOCATION_PERSISTENT_DATA_LABELS[key] || entry.label || key,
      kind,
      badge: allocationDataBadge(kind),
      missingText: allocationDataMissingText(kind),
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
          : String(path).includes("/ytgenerering-map-layout")
            ? "Ytkarta sparad"
            : "Bearbeta-anrop klart";
    const rows = Array.isArray(body?.tables) ? ` (${body.tables.length} tabeller)` : "";
    window.flowLog?.success(`${label}${rows}`, "Klart");
  }
  return body;
}

async function allocationPostForm(path, formData) {
  return allocationJson(path, { method: "POST", body: formData });
}

async function loadAllocationCoreDataStatus(options = {}) {
  try {
    const skipCache = options.skipCache !== false;
    if (skipCache) {
      window.api?.clearGetCache?.((key) => String(key || "").includes("/api/coredata/files"));
    }
    allocationState.coredata = await allocationJson("/api/coredata/files", skipCache ? { skipCache: true } : {});
    cacheAllocationBootData();
  } catch (error) {
    console.warn("Kunde inte läsa kärnfiler.", error);
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
  const stem = String(file?.name || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\.[^.]+$/, "");
  if (!stem) return null;
  for (const spec of ALLOCATION_PERSISTENT_DATA_UPLOAD_SPECS) {
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
          coredataSaved.push(file.name || "kärnfil");
        } catch (error) {
          showToast(error.message || "Kunde inte uppdatera kärnfil.", "error", 7000);
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
    if ((productivityResult.compiledUpdated || []).length) {
      await loadAllocationCoreDataStatus();
    }
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
  const newRows = Number(result?.new_rows || 0);
  const githubState = result?.pushed_to_github
    ? "bekräftad"
    : newRows
      ? "ej bekräftad"
      : "inte aktuell (0 nya pallid)";
  const lines = [
    `Nya pallid hittade: ${newRows}`,
    `Pallid skickade till GitHub: ${Number(result?.github_sent_rows || 0)}`,
    `GitHub-push: ${githubState}`,
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
  appendAllocationAreaFocus(fd);
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
  return slots.filter((slot) => !allocationPersistentDataBackedSlotIsHidden(slot.key));
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
    const persistentEntry = entry ? null : allocationPersistentDataFile(slot.key);
    const displayEntry = entry || persistentEntry;
    const previewKey = entry ? slot.key : persistentEntry?.key || allocationLogicalKey(slot.key);
    const previewSource = entry ? "local" : "persistent";
    const canPreview = allocationState.page === "uploads";
    const sizeLabel = allocationDisplaySizeLabel(entry, persistentEntry);
    const inputId = `allocation-file-${slot.key}`;
    return `
      <div class="allocation-file-slot ${displayEntry ? "filled" : ""}" data-allocation-drop data-drop-slot="${allocationEscape(slot.key)}">
        <div>
          <h3>${allocationEscape(slot.label)}</h3>
          <p>${displayEntry ? `${allocationEscape(displayEntry.name)} ${sizeLabel ? `<span>${allocationEscape(sizeLabel)}</span>` : ""}` : "Ingen fil vald"}</p>
        </div>
        <div class="allocation-file-actions">
          <span class="allocation-file-badge">${entry ? "Inlagd" : persistentEntry ? persistentEntry.badge : "Ej fil"}</span>
          ${displayEntry && canPreview ? `<button type="button" data-preview-file-key="${allocationEscape(previewKey)}" data-preview-file-source="${allocationEscape(previewSource)}">Visa</button>` : ""}
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
  root.querySelectorAll("[data-preview-file-key]").forEach((button) => {
    button.addEventListener("click", () => handleAllocationPreviewClick(button));
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
    ${renderPersistentDataFilesView()}
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

function renderPersistentDataGroup(title, items) {
  const uploaded = items.filter((item) => item.uploaded).length;
  return `
    <section class="allocation-panel allocation-coredata-panel" data-allocation-drop>
      <div class="allocation-panel-head">
        <h2>${allocationEscape(title)}</h2>
        <div><span class="allocation-muted">${uploaded}/${items.length} finns</span></div>
      </div>
      <div class="allocation-file-grid compact">
        ${items.map((item) => `
          <div class="allocation-file-slot ${item.uploaded ? "filled" : ""}" data-allocation-drop>
            <div>
              <h3>${allocationEscape(item.label)}</h3>
              <p>${item.uploaded
                ? `${allocationEscape(item.name)} ${item.sizeLabel ? `<span>${allocationEscape(item.sizeLabel)}</span>` : ""}`
                : allocationEscape(item.missingText)}</p>
            </div>
            <div class="allocation-file-actions">
              <span class="allocation-file-badge">${item.uploaded ? allocationEscape(item.badge) : "Saknas"}</span>
              ${item.uploaded ? `<button type="button" data-preview-file-key="${allocationEscape(item.key)}" data-preview-file-source="persistent">Visa</button>` : ""}
            </div>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function renderPersistentDataFilesView() {
  const items = allocationPersistentDataItems();
  if (!items.length) return "";
  return [
    { title: ALLOCATION_COMPILED_DATA_LABEL, items: items.filter((item) => item.kind === "compiled_data") },
    { title: "Kärnfiler", items: items.filter((item) => item.kind !== "compiled_data") },
  ]
    .filter((group) => group.items.length)
    .map((group) => renderPersistentDataGroup(group.title, group.items))
    .join("");
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
    if (input.required && !allocationPersistentStatusFile(input.key)) missing.push({ ...input, type: "coredata" });
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

function allocationMissingRequirementLabel(item) {
  if (item.type === "session") return item.label || "Körning körd";
  if (item.type === "coredata") return item.label || ALLOCATION_PERSISTENT_DATA_LABELS[item.key] || item.key;
  if (item.type === "file") return allocationSlotLabel(allocationFileInputKey(item));
  return item.label || item.key || "Krav";
}

function allocationMissingRequirementText(missing) {
  const labels = (missing || []).map(allocationMissingRequirementLabel).filter(Boolean);
  return labels.length ? `Saknas: ${labels.join(", ")}` : "";
}

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
        const entry = allocationState.files[key];
        const persistentEntry = entry ? null : allocationPersistentDataFile(key);
        const displayEntry = entry || persistentEntry;
        const cls = displayEntry ? "ok" : input.required ? "missing" : "optional";
        const prefix = displayEntry ? "✓" : input.required ? "✗" : "○";
        const suffix = persistentEntry
          ? ` (${allocationEscape(persistentEntry.suffixLabel || persistentEntry.badge.toLowerCase())})`
          : input.required || displayEntry ? "" : " (valfri)";
        return `
          <div class="allocation-flow-file ${displayEntry ? "filled" : ""}">
            <span class="allocation-file-tag ${cls}">${prefix} ${allocationEscape(allocationSlotLabel(key))}${suffix}</span>
            <span>${displayEntry ? allocationEscape(displayEntry.name) : "Ingen fil"}</span>
          </div>
        `;
      }).join("")}
      ${coreInputs.map((input) => {
        const entry = allocationPersistentStatusFile(input.key);
        const label = input.label || ALLOCATION_PERSISTENT_DATA_LABELS[input.key] || input.key;
        const cls = entry ? "ok" : input.required ? "missing" : "optional";
        const prefix = entry ? "✓" : input.required ? "✗" : "○";
        const suffixLabel = allocationDataSuffixLabel(input.key, entry || {});
        return `
          <div class="allocation-flow-file ${entry ? "filled" : ""}">
            <span class="allocation-file-tag ${cls}">${prefix} ${allocationEscape(label)} (${allocationEscape(suffixLabel)})</span>
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
  if (flow.id === "ytgenerering" && allocationState.carrierClusters?.rows?.length) {
    fd.append("carrier_clusters_json", JSON.stringify(allocationState.carrierClusters));
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
      allocationState.carrierClusters = normalizeAllocationCarrierClusters(data.carrier_clusters);
    }
    allocationState.status = `Klart: ${flow.label}`;
    await copyAutoFlowColumn(data);
    await downloadAllocationAutoDownloads(data);
  } catch (error) {
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
      await api.download(`${ALLOCATION_API}/download/${encodeURIComponent(sessionId)}/${encodeURIComponent(key)}`, filename);
    } catch (error) {
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
    showToast(rule.emptyToast, "info", 2500);
    return;
  }
  try {
    const columnData = await allocationJson(
      `${ALLOCATION_API}/table-column/${encodeURIComponent(data.session_id)}/${encodeURIComponent(rule.tableKey)}/0`,
    );
    await writeClipboardText(columnData.text || "");
    showToast(`${orderCount} ${rule.successLabel} kopierade`, "success", 2500);
  } catch (error) {
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
      location: String(assignment.location || "").trim().toUpperCase(),
      placedPallets: allocationMapRound(assignment.placedPallets),
      shipmentPallets: allocationMapRound(assignment.shipmentPallets),
      maxPall: allocationMapRound(assignment.maxPall),
      unusedCapacity: allocationMapRound(assignment.unusedCapacity),
      placementNo: allocationMapNumber(assignment.placementNo, index + 1),
      orderNumbers: Array.isArray(assignment.orderNumbers) ? assignment.orderNumbers.map((value) => String(value)) : [],
    }))
    .filter((assignment) => assignment.location);
  const assignmentByLocation = new Map();
  assignments.forEach((assignment) => {
    assignmentByLocation.set(assignment.location, assignment);
  });

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

  function applyTransform() {
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
    const bounds = entry.bounds && Object.keys(entry.bounds).length
      ? entry.bounds
      : {
          minX: Math.min(...locations.map((loc) => loc.x)),
          minY: Math.min(...locations.map((loc) => loc.y)),
          maxX: Math.max(...locations.map((loc) => loc.x + loc.w)),
          maxY: Math.max(...locations.map((loc) => loc.y + loc.h)),
        };
    const width = Math.max(1, allocationMapNumber(bounds.maxX) - allocationMapNumber(bounds.minX));
    const height = Math.max(1, allocationMapNumber(bounds.maxY) - allocationMapNumber(bounds.minY));
    const padding = 70;
    state.transform.scale = Math.min((rect.width - padding * 2) / width, (rect.height - padding * 2) / height);
    state.transform.scale = Math.max(0.05, Math.min(3, state.transform.scale));
    state.transform.x = (rect.width - width * state.transform.scale) / 2 - allocationMapNumber(bounds.minX) * state.transform.scale;
    state.transform.y = (rect.height - height * state.transform.scale) / 2 - allocationMapNumber(bounds.minY) * state.transform.scale;
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
    const shortLocation = allocationMapShortLocation(loc.location);
    const label = assignment
      ? (assignment.customer || assignment.carrier || assignment.cluster || assignment.shipment)
      : shortLocation;
    const labelLines = assignment ? allocationMapLabelLines(label) : [label];
    const contentX = horizontal ? loc.x + edgeBand + Math.max(1, loc.w - edgeBand) / 2 : center.x;
    const contentY = horizontal ? center.y : loc.y + edgeBand + Math.max(1, loc.h - edgeBand) / 2;
    const contentWidth = Math.max(18, horizontal ? loc.w - edgeBand - 10 : loc.w - 10);
    const contentHeight = Math.max(18, horizontal ? loc.h - 10 : loc.h - edgeBand - 10);
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
    if (allocationMapEstimatedTextWidth(shortLocation, edgeFont) > shortSide - 6) {
      elements.edgeText.setAttribute("textLength", String(Math.max(8, Math.round(shortSide - 6))));
      elements.edgeText.setAttribute("lengthAdjust", "spacingAndGlyphs");
    }
    if (assignment) {
      if (horizontal) {
        const edgeX = loc.x + edgeBand / 2;
        elements.edgeText.setAttribute("x", edgeX);
        elements.edgeText.setAttribute("y", center.y);
        elements.edgeText.setAttribute("transform", `rotate(-90, ${edgeX}, ${center.y})`);
      } else {
        elements.edgeText.setAttribute("x", center.x);
        elements.edgeText.setAttribute("y", loc.y + edgeBand / 2);
      }
    }

    elements.mainText.textContent = "";
    elements.mainText.setAttribute("x", assignment ? contentX : center.x);
    elements.mainText.setAttribute("y", firstLineY);
    elements.mainText.setAttribute("class", assignment ? "allocation-map-label-main" : "allocation-map-label");
    elements.mainText.style.fontSize = `${mainFont}px`;
    elements.mainText.removeAttribute("textLength");
    elements.mainText.removeAttribute("lengthAdjust");
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
    const horizontal = loc.w >= loc.h;
    unusedEl.setAttribute("x", loc.x);
    unusedEl.setAttribute("y", loc.y);
    unusedEl.setAttribute("width", horizontal ? loc.w * fraction : loc.w);
    unusedEl.setAttribute("height", horizontal ? loc.h : loc.h * fraction);
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
    const over = assignments.filter((assignment) => assignment.unusedCapacity < -0.001).length;
    const unplaced = Array.isArray(entry.unplaced) ? entry.unplaced.length : 0;
    metrics.innerHTML = `
      <div><span>Placeringar</span><strong>${assignments.length}</strong></div>
      <div><span>Pallplatser</span><strong>${placed}</strong></div>
      <div><span>Kapacitet</span><strong>${capacity}</strong></div>
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
    grouped.forEach((group) => {
      const orders = [...new Set(group.flatMap((assignment) => assignment.orderNumbers || []))];
      if (!orders.length) return;
      const areas = group
        .slice()
        .sort((a, b) => a.placementNo - b.placementNo || allocationMapCompareLocation(a.location, b.location))
        .map((assignment) => assignment.location)
        .join(", ");
      orders.forEach((orderNumber) => rows.push([areas, "MG", orderNumber, "A"]));
    });
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
    state.transform.x = mouseX - (mouseX - state.transform.x) * factor;
    state.transform.y = mouseY - (mouseY - state.transform.y) * factor;
    state.transform.scale = Math.max(0.05, Math.min(5, state.transform.scale * factor));
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

function renderAllocationCarrierClusterEditor(host, clusters) {
  const rows = clusters?.rows || [];
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
                <th class="adv-agency">${allocationEscape(carrier)}</th>
                <td><input type="text" data-carrier-cluster-field="asn" value="${allocationEscape(row.asn || "")}" /></td>
                <td><input type="text" data-carrier-cluster-field="arrive" value="${allocationEscape(row.arrive || "")}" /></td>
                <td><input type="text" data-carrier-cluster-field="depart" value="${allocationEscape(row.depart || "")}" /></td>
                <td><input type="text" data-carrier-cluster-field="clusterGroup" value="${allocationEscape(row.clusterGroup || "")}" /></td>
                <td><input type="number" min="1" max="652" step="1" data-carrier-cluster-field="startSeq" value="${allocationEscape(row.startSeq || "")}" /></td>
                <td><input type="number" min="1" max="652" step="1" data-carrier-cluster-field="endSeq" value="${allocationEscape(row.endSeq || "")}" /></td>
                <td><input type="color" class="adv-color" data-carrier-cluster-field="color" value="${allocationEscape(swatch)}" aria-label="Färg ${allocationEscape(carrier)}" /></td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
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
    const source = sourceRows[index] || {};
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
    openAllocationCarrierClusterModal();
  });
  root.querySelectorAll("[data-follow-up-flow]").forEach((button) => {
    button.addEventListener("click", async () => {
      await runAllocationFlow(flowById(button.dataset.followUpFlow));
    });
  });
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

function canViewAllocationMapSettings() {
  return Boolean(window.canViewPage?.(allocationState.user, "allocationSettings") || allocationState.user?.is_super_user);
}

function canEditAllocationMapSettings() {
  return Boolean(window.canEditPage?.(allocationState.user, "allocationSettings") || allocationState.user?.is_super_user);
}

function normalizeAllocationMapLayout(payload) {
  const rows = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.locations)
      ? payload.locations
      : Array.isArray(payload?.rows)
        ? payload.rows
        : [];
  const normalized = rows.map((row) => {
    const location = String(row?.location || row?.lagerplats || row?.name || "").trim().toUpperCase();
    const x = Math.round(allocationMapNumber(row?.x));
    const y = Math.round(allocationMapNumber(row?.y));
    const w = Math.max(1, Math.round(allocationMapNumber(row?.w ?? row?.width, 240)));
    const h = Math.max(1, Math.round(allocationMapNumber(row?.h ?? row?.height, 80)));
    const maxPall = allocationMapRound(row?.maxPall ?? row?.max_pall ?? 2);
    if (!/^UTL\d+[A-ZÅÄÖ]?$/.test(location)) return null;
    return { location, x, y, w, h, maxPall: maxPall > 0 ? maxPall : 2 };
  }).filter(Boolean);
  const byLocation = new Map();
  normalized.forEach((row) => byLocation.set(row.location, row));
  const locations = [...byLocation.values()].sort((a, b) => allocationMapCompareLocation(a.location, b.location));
  const defaults = payload && !Array.isArray(payload) ? normalizeAllocationMapLayout(payload.defaults).locations : [];
  const rawAvailable = payload && !Array.isArray(payload)
    ? (payload.availableLocations || payload.available_locations || [])
    : [];
  const availableLocations = Array.isArray(rawAvailable)
    ? rawAvailable.map((row) => {
        const location = String(row?.location || row?.lagerplats || row?.name || "").trim().toUpperCase();
        if (!/^UTL\d+[A-ZÅÄÖ]?$/.test(location)) return null;
        const maxPall = allocationMapRound(row?.maxPall ?? row?.max_pall ?? 2);
        return { location, maxPall: maxPall > 0 ? maxPall : 2 };
      }).filter(Boolean).sort((a, b) => allocationMapCompareLocation(a.location, b.location))
    : [];
  return { version: 1, locations, defaults, availableLocations, canEdit: Boolean(payload?.can_edit) };
}

async function loadAllocationMapLayout() {
  const focus = allocationProcessAreaCode();
  const query = focus ? `?area_focus=${encodeURIComponent(focus)}` : "";
  return normalizeAllocationMapLayout(await allocationJson(`${ALLOCATION_API}/ytgenerering-map-layout${query}`));
}

function allocationMapLayoutBounds(rows) {
  if (!rows.length) return { minX: 0, minY: 0, maxX: 1200, maxY: 800, width: 1200, height: 800 };
  const minX = Math.min(...rows.map((row) => row.x));
  const minY = Math.min(...rows.map((row) => row.y));
  const maxX = Math.max(...rows.map((row) => row.x + row.w));
  const maxY = Math.max(...rows.map((row) => row.y + row.h));
  const pad = 220;
  return {
    minX: minX - pad,
    minY: minY - pad,
    maxX: maxX + pad,
    maxY: maxY + pad,
    width: Math.max(800, maxX - minX + pad * 2),
    height: Math.max(600, maxY - minY + pad * 2),
  };
}

function allocationMapLayoutNextNumber(rows) {
  const numbers = rows
    .map((row) => String(row.location || "").match(/^UTL(\d+)/i))
    .filter(Boolean)
    .map((match) => Number.parseInt(match[1], 10))
    .filter(Number.isFinite);
  return numbers.length ? Math.max(...numbers) + 1 : 1;
}

function allocationMapLayoutStep(row, direction, gap) {
  if (direction === "left") return { dx: -(row.w + gap), dy: 0 };
  if (direction === "up") return { dx: 0, dy: -(row.h + gap) };
  if (direction === "down") return { dx: 0, dy: row.h + gap };
  return { dx: row.w + gap, dy: 0 };
}

function allocationMapLayoutRectsOverlap(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function allocationMapLayoutAvoidCollision(rows, rect, direction, gap) {
  const step = allocationMapLayoutStep(rect, direction, gap);
  const placed = { ...rect };
  let guard = 0;
  while (rows.some((row) => allocationMapLayoutRectsOverlap(placed, row)) && guard < 300) {
    placed.x += step.dx === 0 && step.dy === 0 ? rect.w + gap : step.dx;
    placed.y += step.dy;
    guard += 1;
  }
  placed.x = Math.round(placed.x / 10) * 10;
  placed.y = Math.round(placed.y / 10) * 10;
  return placed;
}

function allocationMapLayoutSelectedRow(rows, selectedLocation) {
  return rows.find((row) => row.location === selectedLocation) || rows[rows.length - 1] || {
    location: "UTL0",
    x: 0,
    y: 0,
    w: 240,
    h: 80,
    maxPall: 2,
  };
}

function allocationMapLayoutSeriesRows(rows, options) {
  const start = Math.max(1, Number.parseInt(options.start, 10) || allocationMapLayoutNextNumber(rows));
  const end = Math.max(1, Number.parseInt(options.end, 10) || start);
  const direction = options.direction || "right";
  const gap = Math.max(0, Number.parseInt(options.gap, 10) || 20);
  const base = allocationMapLayoutSelectedRow(rows, options.selectedLocation);
  const step = allocationMapLayoutStep(base, direction, gap);
  const existing = new Set(rows.map((row) => row.location));
  const availableByLocation = new Map((options.availableLocations || []).map((row) => [row.location, row]));
  const useAvailableFilter = availableByLocation.size > 0;
  const additions = [];
  const count = Math.abs(end - start) + 1;
  let cursor = { ...base, x: base.x + step.dx, y: base.y + step.dy };
  for (let index = 0; index < count; index += 1) {
    const number = start <= end ? start + index : start - index;
    const location = `UTL${number}`;
    if (existing.has(location)) {
      const existingRow = rows.find((row) => row.location === location);
      if (existingRow) cursor = { ...existingRow, x: existingRow.x + step.dx, y: existingRow.y + step.dy };
      continue;
    }
    const available = availableByLocation.get(location);
    if (useAvailableFilter && !available) continue;
    const draft = {
      location,
      x: cursor.x,
      y: cursor.y,
      w: Math.max(1, Math.round(allocationMapNumber(options.w, base.w))),
      h: Math.max(1, Math.round(allocationMapNumber(options.h, base.h))),
      maxPall: allocationMapRound(options.maxPall || available?.maxPall || base.maxPall || 2),
    };
    const placed = allocationMapLayoutAvoidCollision([...rows, ...additions], draft, direction, gap);
    additions.push(placed);
    existing.add(location);
    cursor = { ...placed, x: placed.x + step.dx, y: placed.y + step.dy };
  }
  return additions;
}

function renderAllocationMapSettingsView() {
  renderAllocationShell(`
    <section class="allocation-map-settings-page-panel">
      <div id="allocation-map-settings-editor"><p class="allocation-muted">Laddar ytkarta...</p></div>
    </section>
  `);
  void mountAllocationMapSettingsPage(document.getElementById("allocation-map-settings-editor"));
}

async function mountAllocationMapSettingsPage(editor) {
  if (!editor) return;
  const canEdit = canEditAllocationMapSettings();
  let layout;
  let rows = [];
  let availableLocations = [];
  let selectedLocation = "";
  let selectedLocations = new Set();
  let clipboardRows = [];
  const undoStack = [];
  let drag = null;
  let pan = null;
  let viewBox = null;
  let statusText = "";
  let ignoreNextMapClick = false;

  try {
    layout = await loadAllocationMapLayout();
    rows = [...(layout.locations || [])];
    availableLocations = [...(layout.availableLocations || [])];
    selectedLocation = rows[0]?.location || "";
    selectedLocations = selectedLocation ? new Set([selectedLocation]) : new Set();
  } catch (error) {
    editor.innerHTML = `<p class="allocation-status error">${allocationEscape(error.message || "Kunde inte läsa ytkartan.")}</p>`;
    return;
  }

  function selectedRow() {
    return rows.find((row) => row.location === selectedLocation) || null;
  }

  function cloneMapRows(sourceRows = rows) {
    return sourceRows.map((row) => ({ ...row }));
  }

  function sortedMapRows(sourceRows = rows) {
    return [...sourceRows].sort((a, b) => allocationMapCompareLocation(a.location, b.location));
  }

  function pushUndoSnapshot() {
    if (!canEdit) return;
    undoStack.push(cloneMapRows());
    if (undoStack.length > 80) undoStack.shift();
  }

  function pruneSelection() {
    const existing = new Set(rows.map((row) => row.location));
    selectedLocations = new Set([...selectedLocations].filter((location) => existing.has(location)));
    if (selectedLocation && !existing.has(selectedLocation)) selectedLocation = "";
    if (!selectedLocation && selectedLocations.size) selectedLocation = [...selectedLocations][0];
    if (!selectedLocations.size && rows.length) {
      selectedLocation = rows[0].location;
      selectedLocations = new Set([selectedLocation]);
    }
  }

  function selectedRows() {
    return rows.filter((row) => selectedLocations.has(row.location));
  }

  function setSelection(location, event = null, options = {}) {
    if (!location || !rows.some((row) => row.location === location)) return;
    const sorted = sortedMapRows();
    if (event?.shiftKey && selectedLocation) {
      const start = sorted.findIndex((row) => row.location === selectedLocation);
      const end = sorted.findIndex((row) => row.location === location);
      if (start >= 0 && end >= 0) {
        const [from, to] = start < end ? [start, end] : [end, start];
        selectedLocations = new Set(sorted.slice(from, to + 1).map((row) => row.location));
      }
    } else if (event?.ctrlKey || event?.metaKey) {
      selectedLocations = new Set(selectedLocations);
      if (selectedLocations.has(location) && selectedLocations.size > 1) selectedLocations.delete(location);
      else selectedLocations.add(location);
    } else if (!(options.keepExisting && selectedLocations.has(location))) {
      selectedLocations = new Set([location]);
    }
    selectedLocation = location;
  }

  function syncSelectionVisuals() {
    editor.querySelectorAll("[data-map-setting-rect]").forEach((item) => {
      item.classList.toggle("is-selected", selectedLocations.has(item.dataset.mapSettingRect || ""));
    });
  }

  function restoreMapRows(snapshot) {
    rows = sortedMapRows(cloneMapRows(snapshot));
    pruneSelection();
    renderEditor();
  }

  function currentBounds() {
    const sourceRows = rows.length ? rows : (layout.defaults || []);
    return allocationMapLayoutBounds(sourceRows);
  }

  function ensureViewBox() {
    if (!viewBox) {
      const bounds = currentBounds();
      viewBox = { x: bounds.minX, y: bounds.minY, width: bounds.width, height: bounds.height };
    }
    return viewBox;
  }

  function setSvgViewBox() {
    const svg = editor.querySelector("[data-map-settings-svg]");
    if (!svg || !viewBox) return;
    svg.setAttribute("viewBox", `${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`);
  }

  function fitView() {
    const bounds = currentBounds();
    viewBox = { x: bounds.minX, y: bounds.minY, width: bounds.width, height: bounds.height };
  }

  function zoomView(factor, event) {
    const svg = editor.querySelector("[data-map-settings-svg]");
    const box = svg?.getBoundingClientRect();
    const current = ensureViewBox();
    const nextWidth = Math.max(260, Math.min(12000, current.width * factor));
    const nextHeight = Math.max(180, Math.min(9000, current.height * factor));
    let anchorX = current.x + current.width / 2;
    let anchorY = current.y + current.height / 2;
    if (box && event) {
      anchorX = current.x + ((event.clientX - box.left) / Math.max(1, box.width)) * current.width;
      anchorY = current.y + ((event.clientY - box.top) / Math.max(1, box.height)) * current.height;
    }
    const rx = (anchorX - current.x) / current.width;
    const ry = (anchorY - current.y) / current.height;
    viewBox = {
      x: anchorX - nextWidth * rx,
      y: anchorY - nextHeight * ry,
      width: nextWidth,
      height: nextHeight,
    };
    setSvgViewBox();
  }

  function availableNotMapped(options = {}) {
    const placed = new Set(rows.map((row) => row.location));
    const search = options.ignoreSearch
      ? ""
      : String(editor.querySelector("[data-map-location-search]")?.value || "").trim().toUpperCase();
    return availableLocations
      .filter((row) => !placed.has(row.location))
      .filter((row) => !search || row.location.includes(search))
      .sort((a, b) => allocationMapCompareLocation(a.location, b.location));
  }

  function updateSelectedFromInputs() {
    const row = selectedRow();
    if (!row || !canEdit) return;
    pushUndoSnapshot();
    const previousLocation = row.location;
    const nextLocation = String(editor.querySelector("[data-map-setting-location]")?.value || row.location).trim().toUpperCase();
    if (/^UTL\d+[A-ZÅÄÖ]?$/.test(nextLocation) && nextLocation !== row.location && !rows.some((item) => item.location === nextLocation)) {
      row.location = nextLocation;
      selectedLocation = nextLocation;
      if (selectedLocations.has(previousLocation)) {
        selectedLocations.delete(previousLocation);
        selectedLocations.add(nextLocation);
      }
    }
    row.x = Math.round(allocationMapNumber(editor.querySelector("[data-map-setting-x]")?.value, row.x));
    row.y = Math.round(allocationMapNumber(editor.querySelector("[data-map-setting-y]")?.value, row.y));
    row.w = Math.max(1, Math.round(allocationMapNumber(editor.querySelector("[data-map-setting-w]")?.value, row.w)));
    row.h = Math.max(1, Math.round(allocationMapNumber(editor.querySelector("[data-map-setting-h]")?.value, row.h)));
    row.maxPall = Math.max(0.1, allocationMapRound(editor.querySelector("[data-map-setting-max]")?.value || row.maxPall));
    rows = sortedMapRows(rows);
    renderEditor();
  }

  function baseRowForPlacement() {
    return selectedRow() || rows[rows.length - 1] || layout.defaults?.[0] || {
      location: "UTL0",
      x: 0,
      y: 0,
      w: 240,
      h: 80,
      maxPall: 2,
    };
  }

  function addLocationRow(locationRow) {
    if (!canEdit || !locationRow || rows.some((row) => row.location === locationRow.location)) return;
    pushUndoSnapshot();
    const base = baseRowForPlacement();
    const direction = editor.querySelector("[data-map-series-direction]")?.value || "right";
    const gap = Math.max(0, Number.parseInt(editor.querySelector("[data-map-series-gap]")?.value, 10) || 20);
    const step = allocationMapLayoutStep(base, direction, gap);
    const draft = {
      location: locationRow.location,
      x: base.x + step.dx,
      y: base.y + step.dy,
      w: base.w,
      h: base.h,
      maxPall: allocationMapRound(locationRow.maxPall || base.maxPall || 2),
    };
    const placed = allocationMapLayoutAvoidCollision(rows, draft, direction, gap);
    rows = sortedMapRows([...rows, placed]);
    selectedLocation = placed.location;
    selectedLocations = new Set([placed.location]);
    statusText = `${placed.location} tillagd.`;
    renderEditor();
  }

  async function saveMapSettings(button) {
    if (!canEdit) return;
    button.disabled = true;
    try {
      const focus = allocationProcessAreaCode();
      const query = focus ? `?area_focus=${encodeURIComponent(focus)}` : "";
      const response = await allocationJson(`${ALLOCATION_API}/ytgenerering-map-layout${query}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ locations: rows }),
      });
      layout = normalizeAllocationMapLayout(response);
      rows = [...layout.locations];
      availableLocations = [...(layout.availableLocations || [])];
      statusText = "Ytkartsinställningar sparade.";
      showToast(statusText, "success", 2500);
      renderEditor();
    } catch (error) {
      button.disabled = false;
      showToast(error.message || "Kunde inte spara ytkartan.", "error", 7000);
    }
  }

  function selectedLocationText() {
    return selectedRows().map((row) => row.location).join("\n");
  }

  function copySelection(mode = "copy") {
    const picked = selectedRows();
    if (!picked.length) return;
    clipboardRows = cloneMapRows(picked);
    void writeClipboardText(selectedLocationText()).catch(() => {});
    statusText = mode === "cut"
      ? `${picked.length} ytor klippta.`
      : `${picked.length} ytor kopierade.`;
    if (mode === "cut" && canEdit) {
      pushUndoSnapshot();
      const cutLocations = new Set(picked.map((row) => row.location));
      rows = rows.filter((row) => !cutLocations.has(row.location));
      selectedLocations = new Set();
      selectedLocation = rows[0]?.location || "";
      if (selectedLocation) selectedLocations.add(selectedLocation);
    }
    renderEditor();
  }

  function pasteSelection() {
    if (!canEdit || !clipboardRows.length) return;
    const free = availableNotMapped({ ignoreSearch: true });
    const existing = new Set(rows.map((row) => row.location));
    const minX = Math.min(...clipboardRows.map((row) => row.x));
    const minY = Math.min(...clipboardRows.map((row) => row.y));
    const base = selectedRow() || rows[rows.length - 1] || clipboardRows[0];
    const additions = [];
    let freeIndex = 0;
    for (const source of clipboardRows) {
      let nextLocation = source.location;
      let nextMaxPall = source.maxPall;
      if (existing.has(nextLocation)) {
        const option = free[freeIndex];
        if (!option) continue;
        freeIndex += 1;
        nextLocation = option.location;
        nextMaxPall = option.maxPall || nextMaxPall;
      }
      const draft = {
        ...source,
        location: nextLocation,
        x: base.x + 40 + (source.x - minX),
        y: base.y + 40 + (source.y - minY),
        maxPall: nextMaxPall,
      };
      const placed = allocationMapLayoutAvoidCollision([...rows, ...additions], draft, "right", 20);
      additions.push(placed);
      existing.add(placed.location);
    }
    if (!additions.length) {
      statusText = "Inga lediga U-platser att klistra in på.";
      renderEditor();
      return;
    }
    pushUndoSnapshot();
    rows = sortedMapRows([...rows, ...additions]);
    selectedLocations = new Set(additions.map((row) => row.location));
    selectedLocation = additions[additions.length - 1].location;
    statusText = `${additions.length} ytor inklistrade.`;
    renderEditor();
  }

  function deleteSelection() {
    if (!canEdit || !selectedLocations.size) return;
    pushUndoSnapshot();
    const deletedCount = selectedLocations.size;
    rows = rows.filter((row) => !selectedLocations.has(row.location));
    selectedLocations = new Set();
    selectedLocation = rows[0]?.location || "";
    if (selectedLocation) selectedLocations.add(selectedLocation);
    statusText = `${deletedCount} ytor borttagna.`;
    renderEditor();
  }

  function undoMapSettings() {
    const snapshot = undoStack.pop();
    if (!snapshot) {
      statusText = "Inget att ångra.";
      renderEditor();
      return;
    }
    statusText = "Ångrat.";
    restoreMapRows(snapshot);
  }

  function moveSelectedRows(dx, dy) {
    if (!canEdit || !selectedLocations.size) return;
    pushUndoSnapshot();
    rows.forEach((row) => {
      if (!selectedLocations.has(row.location)) return;
      row.x = Math.round(row.x + dx);
      row.y = Math.round(row.y + dy);
    });
    statusText = `${selectedLocations.size} ytor flyttade.`;
    renderEditor();
  }

  function selectAllRows() {
    selectedLocations = new Set(rows.map((row) => row.location));
    selectedLocation = rows[rows.length - 1]?.location || "";
    renderEditor();
  }

  function isTextEditingTarget(target) {
    const element = target instanceof Element ? target : null;
    if (!element) return false;
    return Boolean(element.closest("input, textarea, select, [contenteditable='true']"));
  }

  function handleMapSettingsKeydown(event) {
    if (isTextEditingTarget(event.target)) return;
    if (event.allocationMapSettingsHandled) return;
    event.allocationMapSettingsHandled = true;
    const key = String(event.key || "").toLowerCase();
    const shortcut = event.ctrlKey || event.metaKey;
    if (shortcut && key === "c") {
      event.preventDefault();
      copySelection("copy");
      return;
    }
    if (shortcut && key === "x") {
      event.preventDefault();
      copySelection("cut");
      return;
    }
    if (shortcut && key === "v") {
      event.preventDefault();
      pasteSelection();
      return;
    }
    if (shortcut && key === "z") {
      event.preventDefault();
      undoMapSettings();
      return;
    }
    if (shortcut && key === "a") {
      event.preventDefault();
      selectAllRows();
      return;
    }
    if (key === "delete" || key === "backspace") {
      event.preventDefault();
      deleteSelection();
      return;
    }
    const arrowSteps = {
      arrowleft: [-1, 0],
      arrowright: [1, 0],
      arrowup: [0, -1],
      arrowdown: [0, 1],
    };
    const arrow = arrowSteps[key];
    if (arrow) {
      event.preventDefault();
      const step = event.altKey ? 1 : event.shiftKey ? 50 : 10;
      moveSelectedRows(arrow[0] * step, arrow[1] * step);
    }
  }

  function focusMapSettingsWorkspace() {
    editor.querySelector("[data-map-settings-workspace]")?.focus({ preventScroll: true });
  }

  async function toggleMapSettingsFullscreen() {
    const workspace = editor.querySelector("[data-map-settings-workspace]");
    if (!workspace) return;
    try {
      if (document.fullscreenElement === workspace) {
        await document.exitFullscreen?.();
      } else {
        await workspace.requestFullscreen?.();
      }
      focusMapSettingsWorkspace();
    } catch (error) {
      showToast("Kunde inte öppna fullskärm.", "error", 4000);
    }
  }

  const documentKeydownHandler = (event) => {
    if (!editor.isConnected) {
      document.removeEventListener("keydown", documentKeydownHandler, true);
      return;
    }
    handleMapSettingsKeydown(event);
  };
  document.addEventListener("keydown", documentKeydownHandler, true);

  function renderEditor() {
    const shouldRestoreWorkspaceFocus = editor.contains(document.activeElement) && !isTextEditingTarget(document.activeElement);
    pruneSelection();
    const row = selectedRow();
    const pickedCount = selectedLocations.size;
    const nextNumber = allocationMapLayoutNextNumber(rows);
    const current = ensureViewBox();
    const freeLocations = availableNotMapped();
    editor.innerHTML = `
      <div class="allocation-map-settings-workspace" data-map-settings-workspace tabindex="0" aria-keyshortcuts="ArrowUp ArrowDown ArrowLeft ArrowRight Control+C Control+X Control+V Control+Z Delete">
        <div class="allocation-map-settings-toolbar">
          <label><span>Från</span><input type="number" min="1" max="652" step="1" data-map-series-start value="${nextNumber}" ${canEdit ? "" : "disabled"} /></label>
          <label><span>Till</span><input type="number" min="1" max="652" step="1" data-map-series-end value="${nextNumber}" ${canEdit ? "" : "disabled"} /></label>
          <label><span>Riktning</span>
            <select data-map-series-direction ${canEdit ? "" : "disabled"}>
              <option value="right">Höger</option>
              <option value="left">Vänster</option>
              <option value="up">Upp</option>
              <option value="down">Ner</option>
            </select>
          </label>
          <label><span>Gap</span><input type="number" min="0" step="10" data-map-series-gap value="20" ${canEdit ? "" : "disabled"} /></label>
          <label><span>Max pall</span><input type="number" min="0.1" step="0.5" data-map-series-max value="${allocationEscape(row?.maxPall || 2)}" ${canEdit ? "" : "disabled"} /></label>
          <button type="button" data-map-add-series ${canEdit ? "" : "disabled"}>Lägg till serie</button>
          <button type="button" data-map-duplicate ${canEdit && row ? "" : "disabled"}>Lägg till nästa</button>
          <button type="button" data-map-delete ${canEdit && pickedCount ? "" : "disabled"}>Ta bort vald</button>
          <button type="button" data-map-reset-defaults ${canEdit ? "" : "disabled"}>Återställ standard</button>
          <span class="allocation-map-settings-selection" data-map-selection-count>${pickedCount || 0} valda</span>
          <span class="allocation-map-settings-toolbar-spacer"></span>
          <button type="button" data-map-zoom-out>−</button>
          <button type="button" data-map-fit>0</button>
          <button type="button" data-map-zoom-in>+</button>
          ${canEdit ? `<button type="button" class="primary" data-map-save>Spara</button>` : ""}
        </div>
        ${statusText ? `<p class="allocation-status">${allocationEscape(statusText)}</p>` : ""}
        <div class="allocation-map-settings-canvas-grid">
          <div class="allocation-map-settings-canvas">
            <svg class="allocation-map-settings-svg" data-map-settings-svg viewBox="${current.x} ${current.y} ${current.width} ${current.height}" aria-label="Ytkartsinställningar">
              <defs>
                <pattern id="allocation-map-settings-grid" width="80" height="80" patternUnits="userSpaceOnUse">
                  <path d="M 80 0 L 0 0 0 80" fill="none" stroke="#d8dee8" stroke-width="0.8"></path>
                </pattern>
              </defs>
              <rect data-map-pan-surface x="-100000" y="-100000" width="200000" height="200000" fill="url(#allocation-map-settings-grid)"></rect>
              ${rows.map((item) => `
                <g data-map-setting-node="${allocationEscape(item.location)}">
                  <rect class="allocation-map-setting-loc${selectedLocations.has(item.location) ? " is-selected" : ""}" data-map-setting-rect="${allocationEscape(item.location)}" x="${item.x}" y="${item.y}" width="${item.w}" height="${item.h}"></rect>
                  <text class="allocation-map-setting-label" x="${item.x + item.w / 2}" y="${item.y + item.h / 2}">${allocationEscape(item.location)}</text>
                </g>
              `).join("")}
            </svg>
            <button type="button" class="allocation-map-settings-fullscreen-button" data-map-settings-fullscreen title="Fullskärm" aria-label="Fullskärm">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M4 9V4h5"></path>
                <path d="M20 9V4h-5"></path>
                <path d="M4 15v5h5"></path>
                <path d="M20 15v5h-5"></path>
                <path d="M9 4 4 9"></path>
                <path d="m15 4 5 5"></path>
                <path d="m4 15 5 5"></path>
                <path d="m20 15-5 5"></path>
              </svg>
            </button>
          </div>
          <aside class="allocation-map-settings-side">
            ${row ? `
              <div class="allocation-map-settings-fields">
                <label><span>Yta</span><input data-map-setting-location value="${allocationEscape(row.location)}" ${canEdit ? "" : "disabled"} /></label>
                <label><span>X</span><input type="number" step="10" data-map-setting-x value="${row.x}" ${canEdit ? "" : "disabled"} /></label>
                <label><span>Y</span><input type="number" step="10" data-map-setting-y value="${row.y}" ${canEdit ? "" : "disabled"} /></label>
                <label><span>Bredd</span><input type="number" min="1" step="10" data-map-setting-w value="${row.w}" ${canEdit ? "" : "disabled"} /></label>
                <label><span>Höjd</span><input type="number" min="1" step="10" data-map-setting-h value="${row.h}" ${canEdit ? "" : "disabled"} /></label>
                <label><span>Max pall</span><input type="number" min="0.1" step="0.5" data-map-setting-max value="${row.maxPall}" ${canEdit ? "" : "disabled"} /></label>
              </div>
            ` : `<p class="allocation-muted">Ingen yta vald.</p>`}
            <div class="allocation-map-settings-list-head">
              <strong>Lediga U-platser</strong>
              <span>${freeLocations.length}/${availableLocations.length}</span>
            </div>
            <input data-map-location-search class="allocation-map-location-search" placeholder="Sök UTL" value="${allocationEscape(editor.querySelector("[data-map-location-search]")?.value || "")}" />
            <div class="allocation-map-settings-list">
              ${freeLocations.map((item) => `
                <button type="button" data-map-add-location="${allocationEscape(item.location)}" ${canEdit ? "" : "disabled"}>
                  <span>${allocationEscape(item.location)}</span><small>${allocationEscape(item.maxPall)} pall</small>
                </button>
              `).join("") || `<p class="allocation-muted">Inga lediga U-platser.</p>`}
            </div>
          </aside>
        </div>
      </div>
    `;
    bindEditor();
    if (shouldRestoreWorkspaceFocus) {
      editor.querySelector("[data-map-settings-workspace]")?.focus({ preventScroll: true });
    }
  }

  function bindEditor() {
    const workspace = editor.querySelector("[data-map-settings-workspace]");
    workspace?.addEventListener("keydown", handleMapSettingsKeydown);
    workspace?.addEventListener("pointerdown", () => workspace.focus());
    editor.querySelectorAll("[data-map-setting-rect]").forEach((item) => {
      item.addEventListener("click", (event) => {
        if (ignoreNextMapClick) {
          ignoreNextMapClick = false;
          return;
        }
        setSelection(item.dataset.mapSettingRect || "", event);
        renderEditor();
        focusMapSettingsWorkspace();
      });
    });
    editor.querySelectorAll("[data-map-setting-location], [data-map-setting-x], [data-map-setting-y], [data-map-setting-w], [data-map-setting-h], [data-map-setting-max]").forEach((input) => {
      input.addEventListener("change", updateSelectedFromInputs);
    });
    editor.querySelector("[data-map-location-search]")?.addEventListener("input", renderEditor);
    editor.querySelectorAll("[data-map-add-location]").forEach((button) => {
      button.addEventListener("click", () => addLocationRow(availableLocations.find((row) => row.location === button.dataset.mapAddLocation)));
    });
    editor.querySelector("[data-map-add-series]")?.addEventListener("click", () => {
      const base = baseRowForPlacement();
      const additions = allocationMapLayoutSeriesRows(rows, {
        selectedLocation,
        start: editor.querySelector("[data-map-series-start]")?.value,
        end: editor.querySelector("[data-map-series-end]")?.value,
        direction: editor.querySelector("[data-map-series-direction]")?.value,
        gap: editor.querySelector("[data-map-series-gap]")?.value,
        maxPall: editor.querySelector("[data-map-series-max]")?.value,
        w: base.w,
        h: base.h,
        availableLocations,
      });
      if (additions.length) {
        pushUndoSnapshot();
        rows = sortedMapRows([...rows, ...additions]);
        selectedLocations = new Set(additions.map((row) => row.location));
        selectedLocation = additions[additions.length - 1].location;
      }
      statusText = additions.length ? `${additions.length} ytor tillagda.` : "Inga lediga U-platser i intervallet.";
      renderEditor();
    });
    editor.querySelector("[data-map-duplicate]")?.addEventListener("click", () => {
      const firstFree = availableNotMapped()[0];
      if (firstFree) addLocationRow(firstFree);
    });
    editor.querySelector("[data-map-delete]")?.addEventListener("click", deleteSelection);
    editor.querySelector("[data-map-reset-defaults]")?.addEventListener("click", () => {
      pushUndoSnapshot();
      rows = [...(layout.defaults || [])];
      selectedLocation = rows[0]?.location || "";
      selectedLocations = selectedLocation ? new Set([selectedLocation]) : new Set();
      fitView();
      statusText = "Standardytor återställda.";
      renderEditor();
    });
    editor.querySelector("[data-map-save]")?.addEventListener("click", (event) => saveMapSettings(event.currentTarget));
    editor.querySelector("[data-map-zoom-in]")?.addEventListener("click", () => zoomView(0.78));
    editor.querySelector("[data-map-zoom-out]")?.addEventListener("click", () => zoomView(1.28));
    editor.querySelector("[data-map-settings-fullscreen]")?.addEventListener("click", toggleMapSettingsFullscreen);
    editor.querySelector("[data-map-fit]")?.addEventListener("click", () => {
      fitView();
      renderEditor();
    });

    const svg = editor.querySelector("[data-map-settings-svg]");
    svg?.addEventListener("wheel", (event) => {
      event.preventDefault();
      zoomView(event.deltaY < 0 ? 0.88 : 1.12, event);
    }, { passive: false });
    svg?.addEventListener("pointerdown", (event) => {
      const rect = event.target.closest("[data-map-setting-rect]");
      if (rect && canEdit) {
        const row = rows.find((item) => item.location === rect.dataset.mapSettingRect);
        if (!row) return;
        setSelection(row.location, event, { keepExisting: true });
        syncSelectionVisuals();
        const picked = selectedRows();
        const rects = [...editor.querySelectorAll("[data-map-setting-rect]")];
        drag = {
          items: picked.map((pickedRow) => {
            const pickedRect = rects.find((item) => item.dataset.mapSettingRect === pickedRow.location);
            return {
              row: pickedRow,
              rect: pickedRect,
              label: pickedRect?.closest("[data-map-setting-node]")?.querySelector(".allocation-map-setting-label"),
              originalX: pickedRow.x,
              originalY: pickedRow.y,
            };
          }),
          startX: event.clientX,
          startY: event.clientY,
          box: svg.getBoundingClientRect(),
          viewBox: { ...ensureViewBox() },
          snapshot: cloneMapRows(),
          moved: false,
        };
      } else {
        pan = {
          startX: event.clientX,
          startY: event.clientY,
          box: svg.getBoundingClientRect(),
          viewBox: { ...ensureViewBox() },
        };
      }
      svg.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });
    svg?.addEventListener("pointermove", (event) => {
      if (drag) {
        const scaleX = drag.viewBox.width / Math.max(1, drag.box.width);
        const scaleY = drag.viewBox.height / Math.max(1, drag.box.height);
        const dx = (event.clientX - drag.startX) * scaleX;
        const dy = (event.clientY - drag.startY) * scaleY;
        if (Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > 2) drag.moved = true;
        drag.items.forEach((item) => {
          item.row.x = Math.round((item.originalX + dx) / 10) * 10;
          item.row.y = Math.round((item.originalY + dy) / 10) * 10;
          item.rect?.setAttribute("x", item.row.x);
          item.rect?.setAttribute("y", item.row.y);
          item.label?.setAttribute("x", item.row.x + item.row.w / 2);
          item.label?.setAttribute("y", item.row.y + item.row.h / 2);
        });
        return;
      }
      if (pan) {
        const scaleX = pan.viewBox.width / Math.max(1, pan.box.width);
        const scaleY = pan.viewBox.height / Math.max(1, pan.box.height);
        viewBox = {
          ...pan.viewBox,
          x: pan.viewBox.x - (event.clientX - pan.startX) * scaleX,
          y: pan.viewBox.y - (event.clientY - pan.startY) * scaleY,
        };
        setSvgViewBox();
      }
    });
    svg?.addEventListener("pointerup", (event) => {
      svg.releasePointerCapture?.(event.pointerId);
      const hadDrag = drag;
      drag = null;
      pan = null;
      if (hadDrag?.moved) {
        undoStack.push(hadDrag.snapshot);
        if (undoStack.length > 80) undoStack.shift();
        ignoreNextMapClick = true;
        statusText = `${hadDrag.items.length} ytor flyttade.`;
        renderEditor();
      }
    });
    svg?.addEventListener("pointercancel", () => {
      drag = null;
      pan = null;
      renderEditor();
    });
  }

  fitView();
  renderEditor();
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
      ytgenereringUtlMin: normalizeYtgenereringUtlNumber(rule.ytgenereringUtlMin, ALLOCATION_YTGENERERING_UTL_MIN),
      ytgenereringUtlMax: normalizeYtgenereringUtlNumber(rule.ytgenereringUtlMax, ALLOCATION_YTGENERERING_UTL_MAX),
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

function renderYtgenereringUtlInputs(code, rule, readonly = false) {
  const range = normalizeYtgenereringUtlRange(rule);
  return `
    <div class="allocation-process-utl-range">
      <label>
        <span>Fr&aring;n</span>
        <input type="number" min="1" max="652" step="1" data-matrix-utl-min="${allocationEscape(code)}" value="${range.min}" aria-label="Ytgenerering UTL fr&aring;n ${allocationEscape(code)}" ${readonly ? "disabled" : ""} />
      </label>
      <label>
        <span>Till</span>
        <input type="number" min="1" max="652" step="1" data-matrix-utl-max="${allocationEscape(code)}" value="${range.max}" aria-label="Ytgenerering UTL till ${allocationEscape(code)}" ${readonly ? "disabled" : ""} />
      </label>
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
            <th>Ytgenerering UTL</th>
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
                <td>${renderYtgenereringUtlInputs(code, rule, readonly)}</td>
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
    const utlRange = normalizeYtgenereringUtlRange({
      ytgenereringUtlMin: row.querySelector("[data-matrix-utl-min]")?.value,
      ytgenereringUtlMax: row.querySelector("[data-matrix-utl-max]")?.value,
    });
    const allFlows = row.querySelector("[data-matrix-all-flows]")?.checked;
    const visibleFlowIds = allFlows
      ? null
      : [...row.querySelectorAll("[data-matrix-flow]:checked")].map((input) => input.value);
    matrix[code] = {
      company,
      excludeCustomers,
      visibleFlowIds,
      ytgenereringUtlMin: utlRange.min,
      ytgenereringUtlMax: utlRange.max,
    };
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
  else if (allocationState.page === "settings") renderAllocationMapSettingsView();
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
  if (!root || !allocationState.user || allocationState.busyId) return;
  if (allocationState.page === "settings") {
    renderAllocationPage();
    return;
  }
  if (allocationState.page !== "process") return;
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
  await loadAllocationCoreDataStatus({ skipCache: true });
  allocationState.status = "Vanliga filval rensade. Kärnfiler och sammanställd data ligger kvar.";
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

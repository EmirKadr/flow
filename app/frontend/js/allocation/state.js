const ALLOCATION_API = "/api/allokering";
const STAFFING_SETTINGS_API = "/api/settings/staffing";
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
const ALLOCATION_USER_FILTERS_PARAM = "__allocation_user_filters_json";
const ALLOCATION_YTGENERERING_SETTINGS_SOURCE = "__ytgenerering_settings";
const ALLOCATION_YTGENERERING_UTL_MIN = 1;
const ALLOCATION_YTGENERERING_UTL_MAX = 652;
const ALLOCATION_FILTER_OPERATORS = [
  { value: "EQ", label: "=" },
  { value: "NE", label: "!=" },
  { value: "GT", label: ">" },
  { value: "GTE", label: ">=" },
  { value: "LT", label: "<" },
  { value: "LTE", label: "<=" },
  { value: "Between", label: "Between" },
  { value: "In", label: "In" },
  { value: "NotIn", label: "Not In" },
];
const ALLOCATION_PROCESS_AREA_OPTIONS = [
  { code: "ALLT", label: "Alla" },
];
const ALLOCATION_PROCESS_MATRIX = {
  ALLT: {
    visibleFlowIds: null,
  },
  DEFAULT: {
    visibleFlowIds: null,
  },
};
const ALLOCATION_KEY_OVERRIDES = { details: "orders", wms_buffert: "buffer" };
const ALLOCATION_FILE_WORDS = {
  orders: ["v_ask_customer_order_details_all", "customer_order_details_all", "customer_order_details", "detalj kundorder", "detalj kundorder(alla)"],
  buffer: ["v_ask_article_buffertpallet", "v_ask_article_bufferpallet", "article_buffertpallet", "article_bufferpallet", "buffertpall", "buffertpallet", "bufferpall", "bufferpallet"],
  overview: ["v_ask_order_overview", "order_overview", "orderoversikt"],
  dispatch: ["v_ask_dispatch_pallet", "dispatch_pallet", "dispatchpall"],
  custom_adr: ["v_ask_custom_adr", "custom_adr", "alternativ leveransadress"],
  saldo: ["v_ask_item_summary_stock_automation", "item_summary_stock_automation", "saldo ink", "automation"],
  items: ["item_option", "item option"],
  max_csv: ["artikel_max", "article_max"],
  not_putaway: ["not_putaway", "not putaway", "ej_inlag", "ej inlag", "ejinlag", "ej inlagrade", "ej inlagrade artiklar"],
  campaign: ["kampanjplock", "kampanj", "campaign"],
  prognos: ["prognos idag", "prognos", "forecast"],
  wms_booking: ["v_ask_booking_putaway", "booking_putaway", "inlagringslogg"],
  wms_trans: ["v_ask_trans_log", "trans_log", "transaktionslogg"],
  wms_pick: ["v_ask_pick_log_full", "pick_log_full", "plocklogg"],
  remote_file: ["observations", "observationer"],
  values_file: ["values", "varden", "värden"],
};
const ALLOCATION_FILE_TYPE_PRIMARY_SLOT = {
  wms_booking: "wms_booking",
};
const ALLOCATION_SLOT_MIRRORS = {
  wms_booking: ["not_putaway"],
};
const ALLOCATION_SLOT_LABELS = {
  orders: "Detalj Kundorder (Alla)",
  buffer: "Buffertpall",
  overview: "Orderöversikt",
  dispatch: "Dispatchpallar",
  custom_adr: "Alternativ Leveransadress",
  saldo: "Saldo Inkl. Automation",
  items: "Item Option",
  not_putaway: "Ej Inlagrade Artiklar",
  prognos: "Prognosfil",
  campaign: "Kampanjfil",
  max_csv: "artikel_max.csv",
  wms_booking: "Inlagringslogg",
  wms_trans: "Translogg",
  wms_pick: "Plocklogg Full",
  remote_file: "Observationsfil",
  values_file: "Textfil med värden",
};
function allocationSlotAliasKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\.[^.]+$/, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function allocationDesktopAvailable() {
  return Boolean(window.flowDesktop?.isDesktop?.());
}

function allocationIsDesktopEntry(entry) {
  return Boolean(entry?.localRef);
}

function allocationLocalRefValue(entry) {
  return entry?.localRef ? `__flow_local_ref:${entry.localRef}` : "";
}
const ALLOCATION_SLOT_LABEL_ALIASES = Object.fromEntries(
  Object.entries(ALLOCATION_FILE_WORDS).flatMap(([key, words]) => [
    [allocationSlotAliasKey(key), key],
    ...(words || []).map((word) => [allocationSlotAliasKey(word), key]),
  ])
);
const ALLOCATION_SLOT_ORDER = [
  "orders", "buffer", "overview", "dispatch", "custom_adr", "saldo", "items", "not_putaway",
  "prognos", "campaign", "max_csv", "wms_booking", "wms_trans", "wms_pick",
  "remote_file", "values_file",
];
const ALLOCATION_PERSISTENT_DATA_UPLOAD_SPECS = [
  { key: "article_max", prefix: "artikel_max" },
  { key: "article_max", prefix: "article_max" },
  { key: "dispatch_template", prefix: "dispatch_template" },
  { key: "item_attribute", prefix: "item_attribute" },
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
  "custom",
  "dimension",
  "dispatch_template",
  "item",
  "item_alias",
  "item_attribute",
  "item_security_info",
  "item_option",
  "location",
  "location_cost",
  "pallet_type",
  "trans_agency",
  "kpi",
];
const ALLOCATION_PERSISTENT_DATA_LABELS = {
  article_max: "artikel_max.csv",
  custom: "Kund",
  dimension: "Dimensioner",
  dispatch_template: "Avgångsmallar",
  item: "Artiklar (Item)",
  item_alias: "Item Alias",
  item_attribute: "Item Attribute",
  item_security_info: "Artikel Säkerhetsinformation",
  item_option: "Item Option",
  location: "Lagerplatser",
  location_cost: "Lagerplatsavstånd",
  pallet_type: "Palltyp",
  trans_agency: "Transportör",
  kpi: "KPI-Mål",
};
const ALLOCATION_COMPILED_DATA_KEYS = new Set([
  "article_max",
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
const ALLOCATION_EDIT_ICON = `
  <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
    <path d="M12 20h9"></path>
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"></path>
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
  processMatrixLoading: false,
  processMatrixError: "",
  filterProfile: { version: 1, flows: {} },
  filterUsers: [],
  values: {},
  busyId: "",
  status: "",
  autoStatus: "",
  result: null,
  carrierClusters: null,
  lastBufferSignature: "",
  lastForecastSessionId: "",
  lastForecastLabel: "",
  settingsTab: "",
  staffingSettings: null,
  staffingSettingsLoading: false,
  staffingSettingsSaving: false,
  staffingSettingsError: "",
  staffingActivities: [],
  staffingActivitiesLoaded: false,
  staffingActivitiesLoading: false,
  staffingActivitiesError: "",
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

function allocationCanonicalSlotKey(key) {
  const logicalKey = allocationLogicalKey(key);
  return ALLOCATION_SLOT_LABEL_ALIASES[allocationSlotAliasKey(logicalKey)] || logicalKey;
}

function allocationSlotLabel(key) {
  const canonicalKey = allocationCanonicalSlotKey(key);
  return ALLOCATION_SLOT_LABELS[canonicalKey] || key;
}

function allocationUploadSlotLabel(slot) {
  const keyLabel = allocationSlotLabel(slot?.key);
  if (keyLabel && keyLabel !== slot?.key) return keyLabel;
  const rawLabel = slot?.label || "";
  const label = allocationSlotLabel(rawLabel);
  return label && label !== rawLabel ? label : rawLabel || slot?.key || "";
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

function allocationPersistentStatusKey(key) {
  const logicalKey = allocationLogicalKey(key);
  const fileType = ALLOCATION_PERSISTENT_DATA_SLOT_TYPES[logicalKey] || logicalKey;
  return (ALLOCATION_PERSISTENT_DATA_LABELS[fileType] || ALLOCATION_PERSISTENT_DATA_FILES[logicalKey]) ? fileType : "";
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
      scopeKey: allocationBootScopeKey(),
      flows: allocationState.flows || [],
      coredata: allocationState.coredata || {},
      processMatrix: allocationState.processMatrix || null,
    }));
  } catch (_error) {}
}

function restoreAllocationBootData() {
  const boot = readAllocationBootCache();
  if (!boot) return false;
  if (boot.scopeKey !== allocationBootScopeKey()) return false;
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

function allocationRawAreaFocus() {
  return String(window.readAreaFocus?.() || document.getElementById("area-focus-toggle")?.dataset?.value || "").trim().toUpperCase();
}

function allocationPositiveInteger(value) {
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}

function allocationFocusedBusinessId() {
  return allocationPositiveInteger(window.areaFocusBusinessId?.());
}

function allocationUserBusinessId() {
  return allocationPositiveInteger(allocationState.user?.business_id);
}

function allocationSettingsBusinessId() {
  return allocationFocusedBusinessId() || allocationUserBusinessId();
}

function allocationScopedQuery(options = {}) {
  const params = new URLSearchParams();
  const focus = allocationRawAreaFocus();
  const focusedBusinessId = allocationFocusedBusinessId();
  const businessId = focusedBusinessId
    || (options.fallbackToUser && (!focus || focus === "ALLT") ? allocationUserBusinessId() : null);
  if (businessId) params.set("business_id", String(businessId));
  if (options.includeAreaFocus && focus) params.set("area_focus", focus);
  const text = params.toString();
  return text ? `?${text}` : "";
}

function allocationScopedUrl(path, options = {}) {
  return `${path}${allocationScopedQuery(options)}`;
}

function allocationBootScopeKey() {
  const focus = allocationRawAreaFocus() || "ALLT";
  const businessId = allocationFocusedBusinessId();
  if (businessId) return `business:${businessId}`;
  if (allocationState.page === "settings" && (!focus || focus === "ALLT")) {
    const settingsBusinessId = allocationSettingsBusinessId();
    if (settingsBusinessId) return `business:${settingsBusinessId}`;
  }
  return `focus:${focus}`;
}

function resetAllocationBusinessScopedState(options = {}) {
  allocationState.processMatrix = null;
  allocationState.processMatrixError = "";
  allocationState.processMatrixLoading = false;
  if (options.includeStaffing) {
    allocationState.staffingSettings = null;
    allocationState.staffingSettingsError = "";
    allocationState.staffingSettingsLoading = false;
    allocationState.staffingSettingsSaving = false;
    allocationState.staffingActivities = [];
    allocationState.staffingActivitiesLoaded = false;
    allocationState.staffingActivitiesLoading = false;
    allocationState.staffingActivitiesError = "";
  }
}

function allocationProcessToggleCode() {
  const focus = allocationRawAreaFocus();
  if (focus === "ALLT") return "ALLT";
  const focusCode = allocationProcessAreaCode();
  if (focusCode) return focusCode;
  const areaIdMatch = focus.match(/^AREA:(\d+)$/);
  if (areaIdMatch) {
    const area = allocationProcessMatrixAreas()
      .find((item) => String(item.areaId ?? item.area_id ?? "") === areaIdMatch[1]);
    return String(area?.code || "").trim().toUpperCase();
  }
  return /^[A-Z0-9_:-]{1,40}$/.test(focus) ? focus : "";
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
  let min = normalizeYtgenereringUtlNumber(
    rule.utlMin ?? rule.ytgenereringUtlMin ?? rule.ytgenerering_utl_min,
    ALLOCATION_YTGENERERING_UTL_MIN,
  );
  let max = normalizeYtgenereringUtlNumber(
    rule.utlMax ?? rule.ytgenereringUtlMax ?? rule.ytgenerering_utl_max,
    ALLOCATION_YTGENERERING_UTL_MAX,
  );
  if (min > max) [min, max] = [max, min];
  return { min, max };
}

function normalizeAllocationProcessRule(rule = {}) {
  const visibleFlowIds = Array.isArray(rule.visibleFlowIds)
    ? rule.visibleFlowIds.map((value) => String(value || "").trim()).filter(Boolean)
    : Array.isArray(rule.visible_flow_ids)
      ? rule.visible_flow_ids.map((value) => String(value || "").trim()).filter(Boolean)
      : null;
  return {
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

function allocationDefaultYtgenereringAreaRule(code = "DEFAULT") {
  return {
    utlMin: ALLOCATION_YTGENERERING_UTL_MIN,
    utlMax: ALLOCATION_YTGENERERING_UTL_MAX,
  };
}

function allocationDefaultYtgenereringAreas() {
  const areas = {
    DEFAULT: allocationDefaultYtgenereringAreaRule("DEFAULT"),
  };
  allocationProcessMatrixAreas().forEach((area) => {
    const code = String(area.code || "").trim().toUpperCase();
    if (code) areas[code] = allocationDefaultYtgenereringAreaRule(code);
  });
  return areas;
}

function normalizeAllocationYtgenereringAreas(value = {}) {
  const areas = allocationDefaultYtgenereringAreas();
  const rawAreas = value?.areas && typeof value.areas === "object" ? value.areas : value;
  if (!rawAreas || typeof rawAreas !== "object") return areas;
  for (const [code, rule] of Object.entries(rawAreas)) {
    const areaCode = String(code || "").trim().toUpperCase();
    if (!areaCode) continue;
    const range = normalizeYtgenereringUtlRange(rule || {});
    areas[areaCode] = { utlMin: range.min, utlMax: range.max };
  }
  return areas;
}

function normalizeAllocationYtgenereringSettings(value = {}) {
  const raw = value && typeof value === "object" ? value : {};
  const rawCarrierClusters = raw.carrierClusters || raw.carrier_clusters;
  const carrierClusters = normalizeAllocationCarrierClusters(rawCarrierClusters);
  const settings = {
    areas: normalizeAllocationYtgenereringAreas(raw.areas || raw),
  };
  if (carrierClusters?.rows?.length) settings.carrierClusters = carrierClusters;
  else if (rawCarrierClusters && typeof rawCarrierClusters === "object" && Array.isArray(rawCarrierClusters.rows)) {
    settings.carrierClusters = {
      version: 1,
      source: rawCarrierClusters.source || { name: "Manuell", rowCount: 0 },
      rows: [],
    };
  }
  return settings;
}

function allocationDefaultYtgenereringSettings() {
  return normalizeAllocationYtgenereringSettings({
    areas: allocationDefaultYtgenereringAreas(),
    carrierClusters: allocationDefaultCarrierClusters(),
  });
}

const ALLOCATION_CLUSTER_DEFAULT_TIMES = { asn: "11:00", arrive: "12:00", depart: "14:00" };
const ALLOCATION_CLUSTER_HUES = [350, 265, 150, 40, 210, 320, 175, 285, 25, 130, 195, 300];
const ALLOCATION_CARRIER_CLUSTER_DEFAULTS = new Map();

function allocationRegisterCarrierClusterDefaults(carrierNums, defaults) {
  carrierNums.forEach((carrierNum) => {
    ALLOCATION_CARRIER_CLUSTER_DEFAULTS.set(String(carrierNum), { ...defaults });
  });
}

allocationRegisterCarrierClusterDefaults([78, 79], { clusterGroup: "Schenker", assignmentOrder: "0", startSeq: "205", endSeq: "356", asn: "11:00", arrive: "12:00", depart: "14:00", color: "#94a3b8" });
allocationRegisterCarrierClusterDefaults([76, 77], { clusterGroup: "Schenker", assignmentOrder: "1", startSeq: "205", endSeq: "356", asn: "11:00", arrive: "12:00", depart: "14:00", color: "#60a5fa" });
allocationRegisterCarrierClusterDefaults([93, 94], { clusterGroup: "Schenker", assignmentOrder: "2", startSeq: "205", endSeq: "356", asn: "11:00", arrive: "12:00", depart: "14:00", color: "#94a3b8" });
allocationRegisterCarrierClusterDefaults([74, 75], { clusterGroup: "Schenker", assignmentOrder: "3", startSeq: "205", endSeq: "356", asn: "10:00", arrive: "11:00", depart: "13:00", color: "#fb923c" });
allocationRegisterCarrierClusterDefaults([82, 83], { clusterGroup: "Schenker", assignmentOrder: "4", startSeq: "205", endSeq: "356", asn: "11:00", arrive: "12:00", depart: "14:00", color: "#34d399" });
allocationRegisterCarrierClusterDefaults([80, 81], { clusterGroup: "Schenker", assignmentOrder: "5", startSeq: "205", endSeq: "356", asn: "13:00", arrive: "14:00", depart: "16:00", color: "#2dd4bf" });
allocationRegisterCarrierClusterDefaults([41], { assignmentOrder: "6", startSeq: "356", endSeq: "205", asn: "18:00", arrive: "19:00", depart: "23:00", color: "#fcd34d" });
allocationRegisterCarrierClusterDefaults([61, 63, 69], { assignmentOrder: "7", startSeq: "356", endSeq: "205", asn: "17:00", arrive: "19:00", depart: "23:00", color: "#86efac" });
allocationRegisterCarrierClusterDefaults([85], { assignmentOrder: "8", startSeq: "356", endSeq: "205", asn: "16:00", arrive: "19:00", depart: "23:00", color: "#f9a8d4" });
allocationRegisterCarrierClusterDefaults([42, 43], { clusterGroup: "Freja", assignmentOrder: "9", startSeq: "600", endSeq: "652", asn: "09:00", arrive: "11:00", depart: "13:00", color: "#c4b5fd" });
allocationRegisterCarrierClusterDefaults([39, 40], { clusterGroup: "Freja", assignmentOrder: "10", startSeq: "600", endSeq: "652", asn: "09:00", arrive: "11:00", depart: "13:00", color: "#c4b5fd" });
allocationRegisterCarrierClusterDefaults([44, 45], { clusterGroup: "Freja", assignmentOrder: "11", startSeq: "600", endSeq: "652", asn: "09:00", arrive: "11:00", depart: "13:00", color: "#c4b5fd" });
allocationRegisterCarrierClusterDefaults([48, 49], { clusterGroup: "Freja", assignmentOrder: "12", startSeq: "600", endSeq: "652", asn: "09:00", arrive: "11:00", depart: "13:00", color: "#c4b5fd" });
allocationRegisterCarrierClusterDefaults([46, 47], { clusterGroup: "Freja", assignmentOrder: "13", startSeq: "600", endSeq: "652", asn: "09:00", arrive: "11:00", depart: "13:00", color: "#c4b5fd" });
allocationRegisterCarrierClusterDefaults([51], { assignmentOrder: "14", startSeq: "652", endSeq: "600", asn: "13:00", arrive: "14:00", depart: "16:00", color: "#fdba74" });
allocationRegisterCarrierClusterDefaults([53], { clusterGroup: "Sandahls Sundsvall", assignmentOrder: "15", startSeq: "205", endSeq: "652", asn: "13:00", arrive: "14:00", depart: "16:00", color: "#f472b6" });
allocationRegisterCarrierClusterDefaults([55], { clusterGroup: "Sandahls Sundsvall", assignmentOrder: "16", startSeq: "205", endSeq: "652", asn: "13:00", arrive: "14:00", depart: "16:00", color: "#f472b6" });
allocationRegisterCarrierClusterDefaults([57], { clusterGroup: "Sandahls Norrland", assignmentOrder: "17", startSeq: "600", endSeq: "652", asn: "15:00", arrive: "16:00", depart: "17:00", color: "#fb7185" });
allocationRegisterCarrierClusterDefaults([59], { clusterGroup: "Sandahls Norrland", assignmentOrder: "18", startSeq: "600", endSeq: "652", asn: "15:00", arrive: "16:00", depart: "17:00", color: "#fda4af" });
allocationRegisterCarrierClusterDefaults([97], { assignmentOrder: "19", startSeq: "205", endSeq: "652", asn: "13:00", arrive: "14:00", depart: "16:00", color: "#e879f9" });
allocationRegisterCarrierClusterDefaults([65, 67], { assignmentOrder: "20", startSeq: "205", endSeq: "652", asn: "10:00", arrive: "11:00", depart: "13:00", color: "#4ade80" });
allocationRegisterCarrierClusterDefaults([71, 73], { assignmentOrder: "21", startSeq: "205", endSeq: "652", asn: "11:00", arrive: "12:00", depart: "14:00", color: "#fbbf24" });

function allocationDefaultCarrierClusters() {
  const rows = [...ALLOCATION_CARRIER_CLUSTER_DEFAULTS.entries()].map(([carrierNum, defaults], index) => ({
    id: `default-${carrierNum}`,
    carrierNum,
    description: "",
    alias: "",
    clusterGroup: defaults.clusterGroup || "",
    assignmentOrder: defaults.assignmentOrder || String(index + 1),
    startSeq: defaults.startSeq || "",
    endSeq: defaults.endSeq || "",
    asn: defaults.asn || ALLOCATION_CLUSTER_DEFAULT_TIMES.asn,
    arrive: defaults.arrive || ALLOCATION_CLUSTER_DEFAULT_TIMES.arrive,
    depart: defaults.depart || ALLOCATION_CLUSTER_DEFAULT_TIMES.depart,
    color: defaults.color || "",
  }));
  return normalizeAllocationCarrierClusters({
    version: 1,
    source: { name: "Standardtransportorer", rowCount: rows.length },
    rows,
  });
}

function allocationCarrierClusterText(value) {
  const text = String(value ?? "").trim();
  return ["nan", "nat", "none", "null"].includes(text.toLowerCase()) ? "" : text;
}

function allocationCarrierClusterIdentifier(value) {
  const text = allocationCarrierClusterText(value);
  const match = text.match(/^(\d+)\.0+$/);
  return match ? match[1] : text;
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

function allocationCarrierClusterDefaults(carrierNum, alias, description) {
  for (const value of [carrierNum, alias, description]) {
    const key = allocationCarrierClusterText(value);
    if (ALLOCATION_CARRIER_CLUSTER_DEFAULTS.has(key)) {
      return ALLOCATION_CARRIER_CLUSTER_DEFAULTS.get(key);
    }
  }
  return {};
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
    const carrierNum = allocationCarrierClusterIdentifier(row.carrierNum ?? row.carrier_num ?? row.agencyNum ?? row.agency_num ?? row.AGENCY_NUM);
    const description = allocationCarrierClusterText(row.description ?? row.agencyDesc ?? row.agency_desc ?? row.AGENCY_DESC ?? row.carrier ?? row.transportor);
    const alias = allocationCarrierClusterText(row.alias ?? row.agencyAlias ?? row.agency_alias ?? row.AGENCY_ALIAS);
    const label = alias || description || carrierNum;
    if (!label) return null;
    const asn = allocationCarrierClusterText(row.asn ?? row.agency_asn ?? row.agencyAsn ?? row.ASN);
    const arrive = allocationCarrierClusterText(row.arrive ?? row.agency_arrive ?? row.agencyArrive ?? row.ARRIVE);
    const depart = allocationCarrierClusterText(row.depart ?? row.agency_depart ?? row.agencyDepart ?? row.DEPART);
    const defaults = allocationCarrierClusterDefaults(carrierNum, alias, description);
    return {
      id: allocationCarrierClusterText(row.id) || carrierNum || `row-${index + 1}`,
      carrierNum,
      description,
      alias,
      clusterGroup: allocationCarrierClusterText(row.clusterGroup ?? row.cluster_group ?? row.CLUSTER_GROUP ?? row.cluster) || defaults.clusterGroup || "",
      assignmentOrder: allocationCarrierClusterNumber(row.assignmentOrder ?? row.assignment_order ?? row.ASSIGNMENT_ORDER ?? row.order) || defaults.assignmentOrder || "",
      startSeq: allocationCarrierClusterNumber(row.startSeq ?? row.start_seq ?? row.START_SEQ ?? row.from ?? row.utlFrom) || defaults.startSeq || "",
      endSeq: allocationCarrierClusterNumber(row.endSeq ?? row.end_seq ?? row.END_SEQ ?? row.to ?? row.utlTo) || defaults.endSeq || "",
      asn: asn || defaults.asn || ALLOCATION_CLUSTER_DEFAULT_TIMES.asn,
      arrive: arrive || defaults.arrive || ALLOCATION_CLUSTER_DEFAULT_TIMES.arrive,
      depart: depart || defaults.depart || ALLOCATION_CLUSTER_DEFAULT_TIMES.depart,
      color: allocationCarrierClusterText(row.color ?? row.colour) || defaults.color || "",
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
      carrierNum: carrier,
      description: carrier,
      alias: carrier,
      clusterGroup: "",
      assignmentOrder: "",
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

function normalizeAllocationFilterOperator(value) {
  const text = String(value || "").trim();
  if (ALLOCATION_FILTER_OPERATORS.some((item) => item.value === text)) return text;
  if (text === "=" || text.toLowerCase() === "eq") return "EQ";
  if (text === "!=" || text.toLowerCase() === "ne") return "NE";
  if (text === ">") return "GT";
  if (text === ">=") return "GTE";
  if (text === "<") return "LT";
  if (text === "<=") return "LTE";
  if (text.toLowerCase() === "between") return "Between";
  if (["in", "terms"].includes(text.toLowerCase())) return "In";
  if (["not in", "not_in", "notin"].includes(text.toLowerCase())) return "NotIn";
  return "EQ";
}

function allocationFilterValues(value) {
  if (Array.isArray(value)) return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  return String(value ?? "")
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeAllocationFilterCondition(raw = {}) {
  const column = String(raw.column || raw.id || raw.field || "").trim();
  const columnLabel = String(raw.columnLabel || raw.label || "").trim();
  const operator = normalizeAllocationFilterOperator(raw.operator);
  if (!column && !columnLabel) return null;
  let value = raw.value;
  if (operator === "In" || operator === "NotIn") value = allocationFilterValues(value);
  else if (operator === "Between") value = allocationFilterValues(value).slice(0, 2);
  else value = String(value ?? "").trim();
  if (Array.isArray(value) ? value.length === 0 : value === "") return null;
  if (operator === "Between" && value.length < 2) return null;
  return { column, columnLabel, operator, value };
}

function normalizeAllocationSourceMode(value) {
  const text = String(value || "").trim().toLowerCase();
  if (["api", "external", "hamta", "hämta"].includes(text)) return "api";
  if (["upload", "uploaded", "file", "local", "uppladdning", "fil"].includes(text)) return "upload";
  return "";
}

function normalizeAllocationSourceModes(value = {}) {
  if (!value || typeof value !== "object") return {};
  const modes = {};
  for (const [fileKey, rawMode] of Object.entries(value)) {
    const key = String(fileKey || "").trim();
    const mode = normalizeAllocationSourceMode(rawMode);
    if (key && mode) modes[key] = mode;
  }
  return modes;
}

function normalizeAllocationFilterProfile(profile = {}) {
  const rawFlows = profile && typeof profile === "object" && profile.flows && typeof profile.flows === "object"
    ? profile.flows
    : {};
  const flows = {};
  for (const [flowId, flowData] of Object.entries(rawFlows)) {
    const flowPayload = {};
    const sources = normalizeAllocationSourceModes(flowData?.sources || flowData?.sourceModes || {});
    if (Object.keys(sources).length) flowPayload.sources = sources;
    const files = {};
    const rawFiles = flowData?.files && typeof flowData.files === "object" ? flowData.files : {};
    for (const [fileKey, conditions] of Object.entries(rawFiles)) {
      const normalized = (Array.isArray(conditions) ? conditions : [])
        .map(normalizeAllocationFilterCondition)
        .filter(Boolean);
      if (normalized.length) files[fileKey] = normalized;
    }
    if (Object.keys(files).length) flowPayload.files = files;
    if (flowId === "ytgenerering") {
      const rawSettings = flowData?.settings && typeof flowData.settings === "object" ? flowData.settings : {};
      const rawYtgenerering = rawSettings.ytgenerering || flowData?.ytgenerering || null;
      if (rawYtgenerering && typeof rawYtgenerering === "object") {
        flowPayload.settings = { ytgenerering: normalizeAllocationYtgenereringSettings(rawYtgenerering) };
      }
    }
    if (Object.keys(flowPayload).length) flows[flowId] = flowPayload;
  }
  return { version: 1, flows };
}

function cloneAllocationFilterProfile(profile = allocationState.filterProfile) {
  return normalizeAllocationFilterProfile(JSON.parse(JSON.stringify(profile || { version: 1, flows: {} })));
}

function allocationFilterProfileCount(profile = allocationState.filterProfile) {
  const normalized = normalizeAllocationFilterProfile(profile);
  return Object.entries(normalized.flows || {}).reduce((total, [flowId, flow]) => (
    total
    + Object.keys(flow.sources || {}).length
    + Object.values(flow.files || {}).reduce((sum, conditions) => sum + conditions.length, 0)
    + allocationYtgenereringSettingsCount(flowId, flow)
  ), 0);
}

function allocationFilterCountForFlow(flowId, profile = allocationState.filterProfile) {
  const flow = normalizeAllocationFilterProfile(profile).flows?.[flowId];
  return Object.keys(flow?.sources || {}).length
    + Object.values(flow?.files || {}).reduce((sum, conditions) => sum + conditions.length, 0)
    + allocationYtgenereringSettingsCount(flowId, flow);
}

function allocationFilterCountForSource(flowId, fileKey, profile = allocationState.filterProfile) {
  if (fileKey === ALLOCATION_YTGENERERING_SETTINGS_SOURCE) {
    return allocationYtgenereringSettingsCount(flowId, normalizeAllocationFilterProfile(profile).flows?.[flowId]);
  }
  const flow = normalizeAllocationFilterProfile(profile).flows?.[flowId];
  return (flow?.files?.[fileKey]?.length || 0) + (flow?.sources?.[fileKey] ? 1 : 0);
}

function allocationYtgenereringSettingsCount(flowId, flow) {
  if (flowId !== "ytgenerering") return 0;
  const settings = flow?.settings?.ytgenerering;
  return settings ? 1 : 0;
}

function allocationSourceModeForFile(flowId, fileKey, source = null, profile = allocationState.filterProfile) {
  const flow = normalizeAllocationFilterProfile(profile).flows?.[flowId];
  const saved = normalizeAllocationSourceMode(flow?.sources?.[fileKey]);
  if (saved) return saved;
  return source?.apiPreferred ? "api" : "upload";
}

function allocationSourceUsesUpload(flowId, fileKey, source = null, profile = allocationState.filterProfile) {
  return allocationSourceModeForFile(flowId, fileKey, source, profile) === "upload";
}

function allocationFlowNeedsStoredFiles(flow, profile = allocationState.filterProfile) {
  if (!flow?.id) return false;
  return (flow.inputs || []).some((input) =>
    input.type === "file" && allocationSourceUsesUpload(flow.id, allocationFileInputKey(input), input, profile)
  );
}

function allocationFlowNeedsCoreDataStatus(flow, profile = allocationState.filterProfile) {
  if (!flow?.id) return false;
  if ((flow.coredata || []).some((input) => allocationSourceUsesUpload(flow.id, input.key, input, profile))) {
    return true;
  }
  return (flow.inputs || []).some((input) => {
    if (input.type !== "file") return false;
    const key = allocationFileInputKey(input);
    return allocationSourceUsesUpload(flow.id, key, input, profile) && Boolean(allocationPersistentStatusKey(key));
  });
}

function allocationVisibleFlowsNeedStoredFiles(profile = allocationState.filterProfile) {
  return (allocationState.visibleFlows || []).some((flow) => allocationFlowNeedsStoredFiles(flow, profile));
}

function allocationVisibleFlowsNeedCoreDataStatus(profile = allocationState.filterProfile) {
  return (allocationState.visibleFlows || []).some((flow) => allocationFlowNeedsCoreDataStatus(flow, profile));
}

function allocationFilterSourcesForFlow(flow) {
  const sources = [];
  const seen = new Set();
  const addSource = (item, type) => {
    const key = String(item?.key || "").trim();
    if (!key || seen.has(key)) return;
    seen.add(key);
    const apiMeta = item.apiSource || flow?.apiSourceMetadata?.[item.apiSourceKey] || null;
    sources.push({
      key,
      label: item.label || allocationSlotLabel(key),
      type,
      required: Boolean(item.required),
      apiPreferred: Boolean(item.apiPreferred),
      apiSourceKey: item.apiSourceKey || "",
      columns: Array.isArray(apiMeta?.columns) ? apiMeta.columns : [],
    });
  };
  if (flow?.id === "ytgenerering") {
    addSource({ key: ALLOCATION_YTGENERERING_SETTINGS_SOURCE, label: "Ytgenerering" }, "settings");
  }
  (flow?.inputs || []).forEach((item) => {
    if (item.type === "file") addSource(item, "file");
  });
  (flow?.coredata || []).forEach((item) => addSource(item, "coredata"));
  return sources;
}

function allocationFilterConditionValueText(condition) {
  return Array.isArray(condition?.value) ? condition.value.join("\n") : String(condition?.value ?? "");
}

async function loadAllocationFilterProfile() {
  try {
    const data = await allocationJson(`${ALLOCATION_API}/filter-profile`);
    allocationState.filterProfile = normalizeAllocationFilterProfile(data.profile);
    allocationState.filterUsers = Array.isArray(data.users) ? data.users : [];
  } catch (error) {
    allocationState.filterProfile = { version: 1, flows: {} };
    allocationState.filterUsers = [];
    console.warn("Kunde inte lÃ¤sa Bearbeta-filtreringar.", error);
  }
}

async function saveAllocationFilterProfile(profile) {
  const data = await allocationJson(`${ALLOCATION_API}/filter-profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile: normalizeAllocationFilterProfile(profile) }),
  });
  allocationState.filterProfile = normalizeAllocationFilterProfile(data.profile);
  allocationState.filterUsers = Array.isArray(data.users) ? data.users : [];
}

async function importAllocationFilterProfile(userId) {
  const data = await allocationJson(`${ALLOCATION_API}/filter-profile/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: Number(userId) }),
  });
  allocationState.filterProfile = normalizeAllocationFilterProfile(data.profile);
  allocationState.filterUsers = Array.isArray(data.users) ? data.users : [];
}

function appendAllocationFilterProfile(formData) {
  const profile = normalizeAllocationFilterProfile(allocationState.filterProfile);
  if (allocationFilterProfileCount(profile) > 0) {
    formData.append(ALLOCATION_USER_FILTERS_PARAM, JSON.stringify(profile));
  }
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


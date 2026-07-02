const ALLOCATION_API = "/api/allokering";
const STAFFING_SETTINGS_API = "/api/settings/staffing";
const PRODUCTIVITY_FINANCE_SETTINGS_API = "/api/settings/productivity-finance";
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
  productivityFinanceSettings: null,
  productivityFinanceSettingsLoading: false,
  productivityFinanceSettingsSaving: false,
  productivityFinanceSettingsError: "",
  productivityFinanceProcessCheck: null,
  productivityFinanceProcessCheckLoading: false,
  productivityFinanceProcessCheckRowId: "",
  productivityFinanceProcessCheckError: "",
  productivityFinanceProcessOptions: [],
  productivityFinanceProcessOptionsLoaded: false,
  productivityFinanceContextMenu: null,
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
  if (options.includeFinance) {
    allocationState.productivityFinanceSettings = null;
    allocationState.productivityFinanceSettingsError = "";
    allocationState.productivityFinanceSettingsLoading = false;
    allocationState.productivityFinanceSettingsSaving = false;
    allocationState.productivityFinanceProcessCheck = null;
    allocationState.productivityFinanceProcessCheckError = "";
    allocationState.productivityFinanceProcessCheckLoading = false;
    allocationState.productivityFinanceProcessCheckRowId = "";
    allocationState.productivityFinanceProcessOptions = [];
    allocationState.productivityFinanceProcessOptionsLoaded = false;
    allocationState.productivityFinanceContextMenu = null;
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

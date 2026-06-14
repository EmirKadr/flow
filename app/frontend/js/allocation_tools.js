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

function allocationProcessToggleCode() {
  const focus = String(
    window.readAreaFocus?.() || document.getElementById("area-focus-toggle")?.dataset?.value || "",
  ).trim().toUpperCase();
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
          localRef: item.localRef || "",
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
      if (!item || (!blob && !item.localRef)) {
        resolve(null);
        return;
      }
      resolve({
        key: item.key,
        name: item.name,
        size: item.size || blob?.size || 0,
        type: item.type || blob?.type || "",
        lastModified: item.lastModified || blob?.lastModified || Date.now(),
        localRef: item.localRef || "",
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
    localRef: file.localRef || "",
    blob: file.localRef ? null : file,
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
}

function allocationFileForForm(entry) {
  if (!entry) return null;
  if (allocationIsDesktopEntry(entry)) return null;
  return entry.blob || entry.file || null;
}

function appendAllocationFileField(fd, fieldKey, entry) {
  if (!entry) return false;
  if (allocationIsDesktopEntry(entry)) {
    fd.append(fieldKey, allocationLocalRefValue(entry));
    return true;
  }
  const file = allocationFileForForm(entry);
  if (!file) return false;
  fd.append(fieldKey, file, entry.name);
  return true;
}

async function downloadAllocationPersistentFile(fileKey) {
  const key = String(fileKey || "").trim();
  if (!key) return;
  await api.download(`/api/coredata/files/${encodeURIComponent(key)}/download`, `${key}.csv`);
}

async function downloadAllocationLocalFile(slotKey) {
  const key = allocationLogicalKey(slotKey);
  let entry = allocationState.files[key] || await loadStoredAllocationFileEntry(key);
  if (!entry) throw new Error("Filen hittades inte lokalt.");
  if (allocationIsDesktopEntry(entry)) {
    await allocationJson(`/api/desktop/files/${encodeURIComponent(entry.localRef)}/open`, { method: "POST" });
    return;
  }
  const file = allocationFileForForm(entry);
  if (!file) throw new Error("Filen hittades inte lokalt.");
  const url = URL.createObjectURL(file);
  const link = document.createElement("a");
  link.href = url;
  link.download = entry.name || `${key}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function openAllocationDesktopRef(ref, folder = false) {
  if (!ref) return;
  await allocationJson(`/api/desktop/files/${encodeURIComponent(ref)}/${folder ? "open-folder" : "open"}`, { method: "POST" });
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
    const skipCache = options.skipCache === true;
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
  if (allocationState.page !== "process" && !canViewAllocationProcessMatrix()) return;
  allocationState.processMatrixLoading = true;
  allocationState.processMatrixError = "";
  try {
    const data = await allocationJson(`${ALLOCATION_API}/process-matrix`);
    allocationState.processMatrix = normalizeAllocationProcessMatrix(data);
    cacheAllocationBootData();
  } catch (error) {
    console.warn("Kunde inte lasa Bearbeta-matris.", error);
    allocationState.processMatrixError = error?.message || "Kunde inte läsa Bearbeta-matris.";
    if (!allocationState.processMatrix) allocationState.processMatrix = allocationProcessFallbackMatrix();
  } finally {
    allocationState.processMatrixLoading = false;
  }
}

function deriveAllocationSlots(flows) {
  const map = new Map();
  for (const flow of flows) {
    for (const input of flow.inputs || []) {
      if (input.type && input.type !== "file") continue;
      const key = allocationFileInputKey(input);
      if (!map.has(key)) {
        map.set(key, { key, label: allocationUploadSlotLabel({ key, label: input.label }), detect: new Set(input.detect || []) });
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
  if (file?.localRef) {
    return await allocationJson("/api/desktop/sync/coredata", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ localRef: file.localRef, filename: file.name || "coredata.csv" }),
    });
  }
  return await api.postFile(
    `/api/coredata/files/raw?filename=${encodeURIComponent(file.name || "coredata.csv")}`,
    file,
  );
}

async function detectAllocationFile(file) {
  if (file?.localRef) {
    return await allocationJson(`/api/desktop/files/${encodeURIComponent(file.localRef)}/detect`);
  }
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
  } finally {
    const uploadedNames = new Set([
      ...assigned.map((item) => item.file?.name || ""),
      ...coredataSaved,
    ].filter(Boolean));
    window.allocationUploadActivity?.finish(uploadedNames.size);
  }
  const uploadedNames = new Set([
    ...assigned.map((item) => item.file?.name || ""),
    ...coredataSaved,
  ].filter(Boolean));
  if (uploadedNames.size === 1) allocationState.status = "1 fil inlagd.";
  else if (uploadedNames.size > 1) allocationState.status = `${uploadedNames.size} filer inlagda.`;
  else allocationState.status = "";
  if (unknown.length) showToast(`Kunde inte sortera: ${unknown.join(", ")}`, "warn");
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
    const actionKey = entry ? slot.key : persistentEntry?.key || allocationLogicalKey(slot.key);
    const canFileAction = allocationState.page === "uploads";
    const sizeLabel = allocationDisplaySizeLabel(entry, persistentEntry);
    const inputId = `allocation-file-${slot.key}`;
    const fileAction = !displayEntry || !canFileAction
      ? ""
      : entry && allocationIsDesktopEntry(entry)
        ? `<button type="button" data-open-local-ref="${allocationEscape(entry.localRef)}">Öppna fil</button><button type="button" data-open-local-folder="${allocationEscape(entry.localRef)}">Mapp</button>`
        : entry
          ? `<button type="button" data-download-local-file="${allocationEscape(actionKey)}">Ladda ner</button>`
          : `<button type="button" data-download-persistent-file="${allocationEscape(actionKey)}">Ladda ner</button>`;
    return `
      <div class="allocation-file-slot ${displayEntry ? "filled" : ""}" data-allocation-drop data-drop-slot="${allocationEscape(slot.key)}">
        <div>
          <h3>${allocationEscape(allocationUploadSlotLabel(slot))}</h3>
          <p>${displayEntry ? `${allocationEscape(displayEntry.name)} ${sizeLabel ? `<span>${allocationEscape(sizeLabel)}</span>` : ""}` : "Ingen fil vald"}</p>
        </div>
        <div class="allocation-file-actions">
          <span class="allocation-file-badge">${entry ? "Inlagd" : persistentEntry ? persistentEntry.badge : "Ej fil"}</span>
          ${fileAction}
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
  root.querySelectorAll("label[for]").forEach((label) => {
    const input = document.getElementById(label.getAttribute("for") || "");
    if (!input || input.type !== "file") return;
    label.addEventListener("click", async (event) => {
      if (!allocationDesktopAvailable()) return;
      event.preventDefault();
      const entries = await window.flowDesktop.pickFiles({
        accept: input.getAttribute("accept") || "",
        multiple: Boolean(input.multiple),
      });
      if (!entries.length) return;
      const slot = input.dataset.slot || "";
      const targetSlot = slot ? currentAllocationSlots().find((item) => item.key === slot) : null;
      await routeAllocationFiles(
        entries,
        targetSlot ? [targetSlot] : allocationDropSlotsForTarget(input.closest("[data-allocation-drop]") || root),
        { fallbackSlotKey: slot },
      );
    });
  });
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
  root.querySelectorAll("[data-download-persistent-file]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await downloadAllocationPersistentFile(button.dataset.downloadPersistentFile);
      } catch (error) {
        showToast(error.message || "Kunde inte ladda ner filen.", "error", 7000);
      }
    });
  });
  root.querySelectorAll("[data-download-local-file]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await downloadAllocationLocalFile(button.dataset.downloadLocalFile);
      } catch (error) {
        showToast(error.message || "Kunde inte öppna filen.", "error", 7000);
      }
    });
  });
  root.querySelectorAll("[data-open-local-ref]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await openAllocationDesktopRef(button.dataset.openLocalRef, false);
      } catch (error) {
        showToast(error.message || "Kunde inte öppna filen.", "error", 7000);
      }
    });
  });
  root.querySelectorAll("[data-open-local-folder]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await openAllocationDesktopRef(button.dataset.openLocalFolder, true);
      } catch (error) {
        showToast(error.message || "Kunde inte öppna mappen.", "error", 7000);
      }
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
              ${item.uploaded ? `<button type="button" data-download-persistent-file="${allocationEscape(item.key)}">Ladda ner</button>` : ""}
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
    const fileKey = allocationFileInputKey(input);
    if (input.apiPreferred && allocationSourceModeForFile(flow.id, fileKey, input) !== "upload") return false;
    if (input.type === "file") return !allocationDisplayFile(fileKey);
    return !allocationState.values[input.key];
  });
  for (const input of flow?.coredata || []) {
    if (input.apiPreferred && allocationSourceModeForFile(flow.id, input.key, input) !== "upload") continue;
    if (input.required && !allocationPersistentStatusFile(input.key)) missing.push({ ...input, type: "coredata" });
  }
  if (flow?.id === "prognos-report" && !allocationDisplayFile("prognos") && !allocationDisplayFile("campaign")) {
    missing.push({ key: "prognos_or_campaign", label: "Prognosfil eller Kampanjfil", type: "file" });
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

const ALLOCATION_MAP_LOAD_DIRECTIONS = {
  horizontal: ["right", "left"],
  vertical: ["down", "up"],
};

function allocationMapDefaultLoadDirection(row = {}) {
  const w = allocationMapNumber(row.w ?? row.width, 1);
  const h = allocationMapNumber(row.h ?? row.height, 1);
  return w >= h ? "right" : "down";
}

function allocationMapLoadDirectionsForRow(row = {}) {
  const w = allocationMapNumber(row.w ?? row.width, 1);
  const h = allocationMapNumber(row.h ?? row.height, 1);
  return w >= h ? ALLOCATION_MAP_LOAD_DIRECTIONS.horizontal : ALLOCATION_MAP_LOAD_DIRECTIONS.vertical;
}

function allocationNormalizeMapLoadDirection(value, row = {}) {
  const raw = String(value || "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
  const aliases = {
    right: "right",
    hoger: "right",
    east: "right",
    left: "left",
    vanster: "left",
    west: "left",
    up: "up",
    upp: "up",
    north: "up",
    down: "down",
    ner: "down",
    ned: "down",
    south: "down",
  };
  const direction = aliases[raw] || "";
  return allocationMapLoadDirectionsForRow(row).includes(direction) ? direction : allocationMapDefaultLoadDirection(row);
}

function allocationNextMapLoadDirection(value, row = {}) {
  const current = allocationNormalizeMapLoadDirection(value, row);
  const directions = allocationMapLoadDirectionsForRow(row);
  const index = directions.indexOf(current);
  return directions[(index + 1) % directions.length];
}

function allocationRotateMapLoadDirectionLeft(value) {
  const rotated = { right: "up", up: "left", left: "down", down: "right" };
  return rotated[value] || value;
}

function allocationMapLoadDirectionLabel(value) {
  const labels = { right: "höger", down: "ned", left: "vänster", up: "upp" };
  return labels[value] || value;
}

function allocationMapLoadOriginSide(value, row = {}) {
  const direction = allocationNormalizeMapLoadDirection(value, row);
  if (direction === "down") return "top";
  if (direction === "up") return "bottom";
  if (direction === "left") return "right";
  return "left";
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
    return {
      location,
      x,
      y,
      w,
      h,
      maxPall: maxPall > 0 ? maxPall : 2,
      loadDirection: allocationNormalizeMapLoadDirection(
        row?.loadDirection ?? row?.load_direction ?? row?.loadingDirection ?? row?.direction,
        { w, h },
      ),
    };
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

function allocationMapLayoutSaveSignature(items = []) {
  return normalizeAllocationMapLayout({ locations: items }).locations
    .map((row) => [
      row.location,
      row.x,
      row.y,
      row.w,
      row.h,
      row.maxPall,
      row.loadDirection,
    ].join("|"))
    .join("\n");
}

async function loadAllocationMapLayout() {
  const focus = allocationProcessAreaCode();
  const query = focus ? `?area_focus=${encodeURIComponent(focus)}` : "";
  return normalizeAllocationMapLayout(await allocationJson(`${ALLOCATION_API}/ytgenerering-map-layout${query}`));
}

function normalizeStaffingSettings(payload = {}) {
  const historyHours = Number(payload.history_hours);
  const minHours = Number(payload.min_history_hours);
  const maxHours = Number(payload.max_history_hours);
  return {
    history_hours: Number.isFinite(historyHours) ? historyHours : 40,
    min_history_hours: Number.isFinite(minHours) ? minHours : 1,
    max_history_hours: Number.isFinite(maxHours) ? maxHours : 240,
    activity_capacity_activity_ids: normalizeStaffingActivityCapacityActivityIds(payload.activity_capacity_activity_ids),
  };
}

function normalizeStaffingActivityCapacityActivityIds(value) {
  if (value == null) return null;
  if (!Array.isArray(value)) return null;
  const ids = [];
  value.forEach((item) => {
    const id = Number(item);
    if (Number.isInteger(id) && id > 0 && !ids.includes(id)) ids.push(id);
  });
  return ids;
}

function staffingActivityCapacityOptions() {
  return (allocationState.staffingActivities || [])
    .filter((activity) =>
      activity?.is_active !== false
      && String(activity?.category || "") !== "absence"
      && String(activity?.kpi_process_name || "").trim()
    )
    .sort((a, b) =>
      Number(a?.sort_order || 0) - Number(b?.sort_order || 0)
      || String(a?.label || "").localeCompare(String(b?.label || ""), "sv")
    );
}

async function loadStaffingActivities() {
  if (allocationState.staffingActivitiesLoading) return;
  allocationState.staffingActivitiesLoading = true;
  allocationState.staffingActivitiesError = "";
  renderStaffingSettingsPanel();
  try {
    const payload = window.api?.get
      ? await window.api.get("/api/activities", { skipCache: true })
      : await allocationJson("/api/activities", { skipCache: true });
    allocationState.staffingActivities = Array.isArray(payload) ? payload : [];
    allocationState.staffingActivitiesLoaded = true;
  } catch (error) {
    allocationState.staffingActivities = [];
    allocationState.staffingActivitiesLoaded = true;
    allocationState.staffingActivitiesError = error?.message || "Kunde inte läsa aktiviteterna.";
  } finally {
    allocationState.staffingActivitiesLoading = false;
    renderStaffingSettingsPanel();
  }
}

async function loadStaffingSettings() {
  allocationState.staffingSettingsLoading = true;
  allocationState.staffingSettingsError = "";
  renderStaffingSettingsPanel();
  try {
    const payload = window.api?.get
      ? await window.api.get(STAFFING_SETTINGS_API, { skipCache: true })
      : await allocationJson(STAFFING_SETTINGS_API, { skipCache: true });
    allocationState.staffingSettings = normalizeStaffingSettings(payload);
  } catch (error) {
    allocationState.staffingSettingsError = error?.message || "Kunde inte läsa bemanningsinställningen.";
  } finally {
    allocationState.staffingSettingsLoading = false;
    renderStaffingSettingsPanel();
  }
}

async function saveStaffingSettings(form) {
  if (!form || !canEditStaffingSettings()) return;
  const input = form.querySelector("[data-staffing-history-hours]");
  const nextValue = Number(String(input?.value ?? "").replace(",", "."));
  const current = normalizeStaffingSettings(allocationState.staffingSettings);
  if (!Number.isFinite(nextValue)) {
    showToast("Ange ett giltigt timvärde.", "error", 3500);
    return;
  }
  if (nextValue < current.min_history_hours || nextValue > current.max_history_hours) {
    const minLabel = current.min_history_hours.toLocaleString("sv-SE", { maximumFractionDigits: 1 });
    const maxLabel = current.max_history_hours.toLocaleString("sv-SE", { maximumFractionDigits: 1 });
    showToast(`Värdet måste vara mellan ${minLabel} och ${maxLabel} timmar.`, "error", 4500);
    return;
  }
  const nextActivityIds = collectStaffingActivityCapacityActivityIds(form);
  const body = {
    history_hours: nextValue,
    activity_capacity_activity_ids: nextActivityIds,
  };
  allocationState.staffingSettingsSaving = true;
  allocationState.staffingSettingsError = "";
  renderStaffingSettingsPanel();
  try {
    const payload = window.api?.put
      ? await window.api.put(STAFFING_SETTINGS_API, body)
      : await allocationJson(STAFFING_SETTINGS_API, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
    allocationState.staffingSettings = normalizeStaffingSettings(payload);
    showToast("Bemanningsinställningen sparades.", "success", 2500);
  } catch (error) {
    allocationState.staffingSettingsError = error?.message || "Kunde inte spara bemanningsinställningen.";
    showToast(allocationState.staffingSettingsError, "error", 7000);
  } finally {
    allocationState.staffingSettingsSaving = false;
    renderStaffingSettingsPanel();
  }
}

function collectStaffingActivityCapacityActivityIds(form) {
  if (form.querySelector("[data-staffing-capacity-all]")?.checked) return null;
  const ids = [];
  form.querySelectorAll("[data-staffing-capacity-activity]:checked").forEach((input) => {
    const id = Number(input.value);
    if (Number.isInteger(id) && id > 0 && !ids.includes(id)) ids.push(id);
  });
  return ids;
}

function renderStaffingActivityCapacityControls(settings, disabled) {
  if (allocationState.staffingActivitiesLoading && !allocationState.staffingActivitiesLoaded) {
    return `<div class="staffing-settings-subsection"><p class="allocation-muted">Laddar aktiviteter...</p></div>`;
  }
  if (allocationState.staffingActivitiesError) {
    return `<div class="staffing-settings-subsection"><p class="allocation-status error">${allocationEscape(allocationState.staffingActivitiesError)}</p></div>`;
  }
  const options = staffingActivityCapacityOptions();
  if (!options.length) {
    return `
      <div class="staffing-settings-subsection">
        <h3>Historiskt snitt</h3>
        <p class="allocation-muted">Det finns inga aktiva aktiviteter med KPI-process att välja.</p>
      </div>
    `;
  }
  const selectedIds = settings.activity_capacity_activity_ids;
  const allSelected = selectedIds == null;
  const selectedSet = new Set(selectedIds || []);
  const disabledAttr = disabled ? "disabled" : "";
  const activityDisabledAttr = disabled || allSelected ? "disabled" : "";
  return `
    <div class="staffing-settings-subsection">
      <h3>Historiskt snitt</h3>
      <p class="allocation-muted">Välj vilka aktiviteter som får visa historiskt snitt när användaren håller musen över en bemanningscell.</p>
      <label class="modal-checkbox">
        <input type="checkbox" data-staffing-capacity-all ${allSelected ? "checked" : ""} ${disabledAttr}>
        <span>Visa för alla KPI-aktiviteter</span>
      </label>
      <div class="staffing-capacity-activity-grid">
        ${options.map((activity) => {
          const id = Number(activity.id);
          const checked = allSelected || selectedSet.has(id);
          return `
            <label class="modal-checkbox">
              <input
                type="checkbox"
                data-staffing-capacity-activity
                value="${allocationEscape(id)}"
                ${checked ? "checked" : ""}
                ${activityDisabledAttr}
              >
              <span>${allocationEscape(activity.label || activity.code || id)}</span>
            </label>
          `;
        }).join("")}
      </div>
    </div>
  `;
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

function allocationMapSettingLabelAttrs(row) {
  const horizontal = row.w >= row.h;
  const cx = row.x + row.w / 2;
  const cy = row.y + row.h / 2;
  const shortSide = Math.max(1, Math.min(row.w, row.h));
  const longSide = Math.max(1, Math.max(row.w, row.h));
  const label = allocationMapShortLocation(row.location);
  const fontSize = allocationMapClamp(shortSide * 0.58, 16, 48);
  const maxWidth = Math.max(8, longSide - 8);
  const attrs = {
    x: cx,
    y: cy,
    label,
    fontSize,
    textLength: "",
    transform: horizontal ? "" : `rotate(-90, ${cx}, ${cy})`,
  };
  if (allocationMapEstimatedTextWidth(label, fontSize) > maxWidth) {
    attrs.textLength = String(Math.round(maxWidth));
  }
  return attrs;
}

function allocationRenderMapSettingLabel(row) {
  const attrs = allocationMapSettingLabelAttrs(row);
  return `<text class="allocation-map-setting-label" x="${attrs.x}" y="${attrs.y}" style="font-size:${attrs.fontSize}px"${attrs.transform ? ` transform="${attrs.transform}"` : ""}${attrs.textLength ? ` textLength="${attrs.textLength}" lengthAdjust="spacingAndGlyphs"` : ""}>${allocationEscape(attrs.label)}</text>`;
}

function allocationUpdateMapSettingLabelElement(labelElement, row) {
  if (!labelElement) return;
  const attrs = allocationMapSettingLabelAttrs(row);
  labelElement.setAttribute("x", attrs.x);
  labelElement.setAttribute("y", attrs.y);
  labelElement.style.fontSize = `${attrs.fontSize}px`;
  labelElement.textContent = attrs.label;
  if (attrs.transform) labelElement.setAttribute("transform", attrs.transform);
  else labelElement.removeAttribute("transform");
  if (attrs.textLength) {
    labelElement.setAttribute("textLength", attrs.textLength);
    labelElement.setAttribute("lengthAdjust", "spacingAndGlyphs");
  } else {
    labelElement.removeAttribute("textLength");
    labelElement.removeAttribute("lengthAdjust");
  }
}

function allocationMapSettingDirectionMarkerBand(row) {
  const shortSide = Math.max(1, Math.min(row.w, row.h));
  return allocationMapClamp(shortSide * 0.56, 24, 58);
}

function allocationMapSettingDirectionPath(row) {
  const direction = allocationNormalizeMapLoadDirection(row.loadDirection, row);
  const inset = allocationMapClamp(Math.min(row.w, row.h) * 0.08, 4, 10);
  const band = allocationMapSettingDirectionMarkerBand(row);
  const cx = row.x + row.w / 2;
  const cy = row.y + row.h / 2;
  if (direction === "down") {
    return `M${row.x + inset} ${row.y + inset}L${row.x + row.w - inset} ${row.y + inset}L${cx} ${row.y + band}Z`;
  }
  if (direction === "up") {
    return `M${row.x + inset} ${row.y + row.h - inset}L${row.x + row.w - inset} ${row.y + row.h - inset}L${cx} ${row.y + row.h - band}Z`;
  }
  if (direction === "left") {
    return `M${row.x + row.w - inset} ${row.y + inset}L${row.x + row.w - inset} ${row.y + row.h - inset}L${row.x + row.w - band} ${cy}Z`;
  }
  return `M${row.x + inset} ${row.y + inset}L${row.x + inset} ${row.y + row.h - inset}L${row.x + band} ${cy}Z`;
}

function allocationRenderMapSettingDirectionArrow(row) {
  return `<path class="allocation-map-setting-direction-arrow" d="${allocationMapSettingDirectionPath(row)}"></path>`;
}

function allocationUpdateMapSettingDirectionArrowElement(arrowElement, row) {
  arrowElement?.setAttribute("d", allocationMapSettingDirectionPath(row));
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
    loadDirection: "right",
  };
}

function allocationMapLayoutSizeForCapacity(base, maxPall) {
  const baseWidth = Math.max(1, Math.round(allocationMapNumber(base.w ?? base.width, 240)));
  const baseHeight = Math.max(1, Math.round(allocationMapNumber(base.h ?? base.height, 80)));
  const baseCapacity = Math.max(0.1, allocationMapNumber(base.maxPall ?? base.max_pall, 2));
  const nextCapacity = Math.max(0.1, allocationMapNumber(maxPall, baseCapacity));
  const ratio = nextCapacity / baseCapacity;
  if (baseWidth >= baseHeight) {
    return { w: Math.max(1, Math.round(baseWidth * ratio)), h: baseHeight };
  }
  return { w: baseWidth, h: Math.max(1, Math.round(baseHeight * ratio)) };
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
      if (existingRow) {
        const existingStep = allocationMapLayoutStep(existingRow, direction, gap);
        cursor = { ...existingRow, x: existingRow.x + existingStep.dx, y: existingRow.y + existingStep.dy };
      }
      continue;
    }
    const available = availableByLocation.get(location);
    if (useAvailableFilter && !available) continue;
    const maxPall = allocationMapRound(options.maxPall || available?.maxPall || base.maxPall || 2);
    const scaledSize = allocationMapLayoutSizeForCapacity(
      { ...base, w: allocationMapNumber(options.w, base.w), h: allocationMapNumber(options.h, base.h) },
      maxPall,
    );
    const draft = {
      location,
      x: cursor.x,
      y: cursor.y,
      w: scaledSize.w,
      h: scaledSize.h,
      maxPall,
      loadDirection: allocationNormalizeMapLoadDirection(options.loadDirection || base.loadDirection, {
        w: scaledSize.w,
        h: scaledSize.h,
      }),
    };
    const placed = allocationMapLayoutAvoidCollision([...rows, ...additions], draft, direction, gap);
    additions.push(placed);
    existing.add(location);
    const placedStep = allocationMapLayoutStep(placed, direction, gap);
    cursor = { ...placed, x: placed.x + placedStep.dx, y: placed.y + placedStep.dy };
  }
  return additions;
}

function allocationSettingsTabs() {
  const tabs = [];
  if (canViewAllocationMapSettings()) tabs.push({ id: "map", label: "Ytkarta" });
  if (canViewAllocationProcessMatrix()) tabs.push({ id: "process-matrix", label: "Bearbeta" });
  if (canViewStaffingSettings()) tabs.push({ id: "staffing", label: "Bemanning" });
  return tabs;
}

function allocationEnsureSettingsTab() {
  const tabs = allocationSettingsTabs();
  if (!tabs.some((tab) => tab.id === allocationState.settingsTab)) {
    allocationState.settingsTab = tabs[0]?.id || "";
  }
  return tabs;
}

function renderAllocationProcessMatrixSettingsPanel(panel = document.getElementById("allocation-settings-panel")) {
  if (!panel) return;
  if (!canViewAllocationProcessMatrix()) {
    panel.innerHTML = `<p class="allocation-status error">Saknar behörighet till Bearbeta-matris.</p>`;
    return;
  }
  if (!allocationState.processMatrix && !allocationState.processMatrixLoading) {
    panel.innerHTML = `<p class="allocation-muted">Laddar Bearbeta-matris...</p>`;
    void loadAllocationProcessMatrix().then(() => renderAllocationProcessMatrixSettingsPanel(panel));
    return;
  }
  if (!allocationState.processMatrix && allocationState.processMatrixLoading) {
    panel.innerHTML = `<p class="allocation-muted">Laddar Bearbeta-matris...</p>`;
    return;
  }
  const canEditMatrix = canEditAllocationProcessMatrix();
  let draft = allocationProcessMatrixDraft();
  panel.innerHTML = `
    <section class="allocation-process-matrix-settings-panel">
      <div class="allocation-settings-heading">
        <h2>Bearbeta-matris</h2>
        <p class="allocation-muted">Styr vilka Bearbeta-funktioner som visas per toggle.</p>
      </div>
      ${allocationState.processMatrixError ? `<p class="allocation-status error">${allocationEscape(allocationState.processMatrixError)}</p>` : ""}
      <div id="allocation-process-matrix-settings-editor"></div>
      <div class="actions">
        ${canEditMatrix ? `<button type="button" id="allocation-process-matrix-settings-defaults">Standard</button>` : ""}
        ${canEditMatrix ? `<button type="button" class="primary" id="allocation-process-matrix-settings-save">Spara</button>` : ""}
      </div>
    </section>
  `;
  const editor = panel.querySelector("#allocation-process-matrix-settings-editor");
  const renderEditor = () => renderAllocationProcessMatrixEditor(editor, draft, !canEditMatrix);
  renderEditor();
  panel.querySelector("#allocation-process-matrix-settings-defaults")?.addEventListener("click", () => {
    draft = allocationProcessMatrixDraft(true);
    renderEditor();
  });
  panel.querySelector("#allocation-process-matrix-settings-save")?.addEventListener("click", async () => {
    const button = panel.querySelector("#allocation-process-matrix-settings-save");
    button.disabled = true;
    try {
      const response = await allocationJson(`${ALLOCATION_API}/process-matrix`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matrix: collectAllocationProcessMatrixDraft(editor) }),
      });
      allocationState.processMatrix = normalizeAllocationProcessMatrix(response);
      allocationState.processMatrixError = "";
      cacheAllocationBootData();
      showToast("Bearbeta-matris sparades.", "success", 2500);
      renderAllocationProcessMatrixSettingsPanel(panel);
    } catch (error) {
      button.disabled = false;
      allocationState.processMatrixError = error.message || "Kunde inte spara Bearbeta-matris.";
      showToast(allocationState.processMatrixError, "error", 7000);
    }
  });
}

function renderStaffingSettingsPanel(panel = document.getElementById("allocation-settings-panel")) {
  if (!panel) return;
  if (!canViewStaffingSettings()) {
    panel.innerHTML = `<p class="allocation-status error">Saknar behörighet till bemanningsinställningar.</p>`;
    return;
  }
  if (!allocationState.staffingSettings && !allocationState.staffingSettingsLoading) {
    panel.innerHTML = `<p class="allocation-muted">Laddar bemanningsinställningar...</p>`;
    void loadStaffingSettings();
    return;
  }
  if (!allocationState.staffingSettings && allocationState.staffingSettingsLoading) {
    panel.innerHTML = `<p class="allocation-muted">Laddar bemanningsinställningar...</p>`;
    return;
  }
  if (!allocationState.staffingActivitiesLoaded && !allocationState.staffingActivitiesLoading) {
    void loadStaffingActivities();
  }
  const settings = normalizeStaffingSettings(allocationState.staffingSettings);
  const canEdit = canEditStaffingSettings();
  const disabled = canEdit && !allocationState.staffingSettingsSaving && !allocationState.staffingSettingsLoading ? "" : "disabled";
  const minLabel = settings.min_history_hours.toLocaleString("sv-SE", { maximumFractionDigits: 1 });
  const maxLabel = settings.max_history_hours.toLocaleString("sv-SE", { maximumFractionDigits: 1 });
  panel.innerHTML = `
    <section class="allocation-staffing-settings-panel">
      <div class="allocation-settings-heading">
        <h2>Bemanningskalkyl</h2>
        <p class="allocation-muted">Historiktimmar används av cellernas historiska snitt och automatiska bemanningskalkyler.</p>
      </div>
      ${allocationState.staffingSettingsError ? `<p class="allocation-status error">${allocationEscape(allocationState.staffingSettingsError)}</p>` : ""}
      <form class="staffing-settings-form" data-staffing-settings-form>
        <label>
          <span>Historikfönster</span>
          <input
            data-staffing-history-hours
            type="number"
            min="${allocationEscape(settings.min_history_hours)}"
            max="${allocationEscape(settings.max_history_hours)}"
            step="1"
            value="${allocationEscape(settings.history_hours)}"
            ${disabled}
          />
        </label>
        <span class="allocation-muted">Tillåtet intervall: ${allocationEscape(minLabel)}-${allocationEscape(maxLabel)} timmar.</span>
        ${renderStaffingActivityCapacityControls(settings, Boolean(disabled))}
        <div class="actions">
          <button type="submit" class="primary" ${canEdit ? disabled : "disabled"}>
            ${allocationState.staffingSettingsSaving ? "Sparar..." : "Spara"}
          </button>
        </div>
      </form>
    </section>
  `;
  panel.querySelector("[data-staffing-settings-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    void saveStaffingSettings(event.currentTarget);
  });
  panel.querySelector("[data-staffing-capacity-all]")?.addEventListener("change", (event) => {
    const checked = Boolean(event.currentTarget?.checked);
    panel.querySelectorAll("[data-staffing-capacity-activity]").forEach((input) => {
      input.disabled = checked || Boolean(disabled);
      if (checked) input.checked = true;
    });
  });
}

function renderAllocationMapSettingsView() {
  const tabs = allocationEnsureSettingsTab();
  if (!tabs.length) {
    renderAllocationShell(`
      <section class="allocation-panel">
        <p class="allocation-status error">Saknar behörighet till inställningar.</p>
      </section>
    `);
    return;
  }
  renderAllocationShell(`
    <section class="allocation-settings-page">
      <div class="allocation-settings-tabs" role="tablist" aria-label="Inställningar">
        ${tabs.map((tab) => `
          <button
            type="button"
            class="allocation-settings-tab ${tab.id === allocationState.settingsTab ? "active" : ""}"
            data-settings-tab="${allocationEscape(tab.id)}"
            role="tab"
            aria-selected="${tab.id === allocationState.settingsTab ? "true" : "false"}"
          >${allocationEscape(tab.label)}</button>
        `).join("")}
      </div>
      <div class="allocation-settings-panel" id="allocation-settings-panel" role="tabpanel"></div>
    </section>
  `);
  document.querySelectorAll("[data-settings-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextTab = button.dataset.settingsTab || "";
      if (!tabs.some((tab) => tab.id === nextTab) || nextTab === allocationState.settingsTab) return;
      allocationState.settingsTab = nextTab;
      renderAllocationMapSettingsView();
    });
  });
  const panel = document.getElementById("allocation-settings-panel");
  if (allocationState.settingsTab === "staffing") {
    renderStaffingSettingsPanel(panel);
  } else if (allocationState.settingsTab === "process-matrix") {
    renderAllocationProcessMatrixSettingsPanel(panel);
  } else {
    panel.innerHTML = `
      <section class="allocation-map-settings-page-panel">
        <div id="allocation-map-settings-editor"><p class="allocation-muted">Laddar ytkarta...</p></div>
      </section>
    `;
    void mountAllocationMapSettingsPage(document.getElementById("allocation-map-settings-editor"));
  }
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
  let ignoreMapContextClickUntil = 0;
  let lastMapRotationAt = 0;
  const LOCATION_DRAG_TYPE = "application/x-flow-yt-location";
  const MAP_SNAP_SCREEN_PX = 4;
  const MAP_SNAP_MIN_UNITS = 2;

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
    const count = editor.querySelector("[data-map-selection-count]");
    if (count) count.textContent = `${selectedLocations.size || 0} valda`;
    const row = selectedRow();
    if (!row) return;
    const fields = [
      ["[data-map-setting-location]", row.location],
      ["[data-map-setting-x]", row.x],
      ["[data-map-setting-y]", row.y],
      ["[data-map-setting-w]", row.w],
      ["[data-map-setting-h]", row.h],
      ["[data-map-setting-max]", row.maxPall],
    ];
    fields.forEach(([selector, value]) => {
      const input = editor.querySelector(selector);
      if (input) input.value = String(value);
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

  function snapTargetsForDrag() {
    const targets = { x: [], y: [] };
    rows.forEach((row) => {
      if (selectedLocations.has(row.location)) return;
      targets.x.push(row.x, row.x + row.w / 2, row.x + row.w);
      targets.y.push(row.y, row.y + row.h / 2, row.y + row.h);
    });
    return targets;
  }

  function closestSnap(candidates, targets, threshold) {
    let best = null;
    candidates.forEach((candidate) => {
      targets.forEach((target) => {
        const distance = Math.abs(target - candidate);
        if (distance <= threshold && (!best || distance < best.distance)) {
          best = { distance, delta: target - candidate, target };
        }
      });
    });
    return best;
  }

  function updateMapSnapGuides(guides = [], box = ensureViewBox()) {
    const group = editor.querySelector("[data-map-snap-guides]");
    if (!group) return;
    group.innerHTML = guides.map((guide) => {
      if (guide.axis === "x") {
        return `<line class="allocation-map-settings-guide-line" x1="${guide.value}" y1="${box.y}" x2="${guide.value}" y2="${box.y + box.height}"></line>`;
      }
      return `<line class="allocation-map-settings-guide-line" x1="${box.x}" y1="${guide.value}" x2="${box.x + box.width}" y2="${guide.value}"></line>`;
    }).join("");
  }

  function applySnapToDrag(dragState, dx, dy, scaleX, scaleY) {
    const draftRows = dragState.items.map((item) => ({
      row: item.row,
      x: item.originalX + dx,
      y: item.originalY + dy,
      w: item.row.w,
      h: item.row.h,
    }));
    const xCandidates = draftRows.flatMap((item) => [item.x, item.x + item.w / 2, item.x + item.w]);
    const yCandidates = draftRows.flatMap((item) => [item.y, item.y + item.h / 2, item.y + item.h]);
    const xSnap = closestSnap(xCandidates, dragState.snapTargets.x, Math.max(MAP_SNAP_MIN_UNITS, scaleX * MAP_SNAP_SCREEN_PX));
    const ySnap = closestSnap(yCandidates, dragState.snapTargets.y, Math.max(MAP_SNAP_MIN_UNITS, scaleY * MAP_SNAP_SCREEN_PX));
    const guides = [];
    if (xSnap) guides.push({ axis: "x", value: xSnap.target });
    if (ySnap) guides.push({ axis: "y", value: ySnap.target });
    updateMapSnapGuides(guides, dragState.viewBox);
    return { dx: dx + (xSnap?.delta || 0), dy: dy + (ySnap?.delta || 0), snapX: Boolean(xSnap), snapY: Boolean(ySnap) };
  }

  function ensureViewBox() {
    if (!viewBox) {
      const bounds = currentBounds();
      viewBox = { x: bounds.minX, y: bounds.minY, width: bounds.width, height: bounds.height };
    }
    return viewBox;
  }

  function clampMapSettingsViewBox(candidate) {
    const bounds = currentBounds();
    const width = Math.max(260, Math.min(bounds.width, candidate.width));
    const height = Math.max(180, Math.min(bounds.height, candidate.height));
    return {
      x: width >= bounds.width ? bounds.minX : allocationMapClamp(candidate.x, bounds.minX, bounds.maxX - width),
      y: height >= bounds.height ? bounds.minY : allocationMapClamp(candidate.y, bounds.minY, bounds.maxY - height),
      width,
      height,
    };
  }

  function setSvgViewBox() {
    const svg = editor.querySelector("[data-map-settings-svg]");
    if (!svg || !viewBox) return;
    viewBox = clampMapSettingsViewBox(viewBox);
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
    const bounds = currentBounds();
    const nextWidth = Math.max(260, Math.min(bounds.width, current.width * factor));
    const nextHeight = Math.max(180, Math.min(bounds.height, current.height * factor));
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

  function svgPointFromClient(svg, clientX, clientY) {
    const point = svg?.createSVGPoint?.();
    const ctm = svg?.getScreenCTM?.();
    if (point && ctm) {
      point.x = clientX;
      point.y = clientY;
      const mapped = point.matrixTransform(ctm.inverse());
      return { x: mapped.x, y: mapped.y };
    }
    const box = svg?.getBoundingClientRect?.();
    const current = ensureViewBox();
    if (!box) return { x: current.x + current.width / 2, y: current.y + current.height / 2 };
    return {
      x: current.x + ((clientX - box.left) / Math.max(1, box.width)) * current.width,
      y: current.y + ((clientY - box.top) / Math.max(1, box.height)) * current.height,
    };
  }

  function mapSettingRowAtClientPoint(svg, clientX, clientY) {
    const point = svgPointFromClient(svg, clientX, clientY);
    return [...rows].reverse().find((row) => (
      point.x >= row.x
      && point.x <= row.x + row.w
      && point.y >= row.y
      && point.y <= row.y + row.h
    )) || null;
  }

  function hasLocationDrag(event) {
    const types = event.dataTransfer?.types;
    if (!types) return false;
    if (typeof types.includes === "function") return types.includes(LOCATION_DRAG_TYPE);
    if (typeof types.contains === "function") return types.contains(LOCATION_DRAG_TYPE);
    return Array.from(types).includes(LOCATION_DRAG_TYPE);
  }

  function draggedLocationFromEvent(event) {
    return String(
      event.dataTransfer?.getData(LOCATION_DRAG_TYPE)
      || event.dataTransfer?.getData("text/plain")
      || ""
    ).trim().toUpperCase();
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
    row.loadDirection = allocationNormalizeMapLoadDirection(row.loadDirection, row);
    rows = sortedMapRows(rows);
    renderEditor();
  }

  function rotateLocationLeft(location) {
    if (!canEdit) return;
    const row = rows.find((item) => item.location === location);
    if (!row) return;
    pushUndoSnapshot();
    const cx = row.x + row.w / 2;
    const cy = row.y + row.h / 2;
    const nextWidth = row.h;
    const nextHeight = row.w;
    const rotatedDirection = allocationRotateMapLoadDirectionLeft(allocationNormalizeMapLoadDirection(row.loadDirection, row));
    row.x = Math.round(cx - nextWidth / 2);
    row.y = Math.round(cy - nextHeight / 2);
    row.w = nextWidth;
    row.h = nextHeight;
    row.loadDirection = allocationNormalizeMapLoadDirection(rotatedDirection, row);
    selectedLocation = row.location;
    selectedLocations = new Set([row.location]);
    statusText = `${row.location}: roterad v\u00e4nster.`;
    renderEditor();
  }

  function rotateLocationFromMapEvent(location) {
    const now = Date.now();
    if (!location || now - lastMapRotationAt < 240) return;
    lastMapRotationAt = now;
    rotateLocationLeft(location);
    focusMapSettingsWorkspace();
  }

  function cycleSelectedLoadDirections() {
    if (!canEdit || !selectedLocations.size) return;
    const picked = selectedRows();
    if (!picked.length) return;
    pushUndoSnapshot();
    picked.forEach((row) => {
      row.loadDirection = allocationNextMapLoadDirection(row.loadDirection, row);
    });
    if (picked.length === 1) {
      statusText = `${picked[0].location}: riktning ${allocationMapLoadDirectionLabel(picked[0].loadDirection)}.`;
    } else {
      statusText = `${picked.length} ytor: riktning bytt.`;
    }
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
      loadDirection: "right",
    };
  }

  function addLocationRow(locationRow) {
    if (!canEdit || !locationRow || rows.some((row) => row.location === locationRow.location)) return;
    pushUndoSnapshot();
    const base = baseRowForPlacement();
    const direction = editor.querySelector("[data-map-series-direction]")?.value || "right";
    const gap = Math.max(0, Number.parseInt(editor.querySelector("[data-map-series-gap]")?.value, 10) || 20);
    const maxPall = allocationMapRound(locationRow.maxPall || base.maxPall || 2);
    const size = allocationMapLayoutSizeForCapacity(base, maxPall);
    const step = allocationMapLayoutStep(base, direction, gap);
    const draft = {
      location: locationRow.location,
      x: base.x + step.dx,
      y: base.y + step.dy,
      w: size.w,
      h: size.h,
      maxPall,
      loadDirection: allocationNormalizeMapLoadDirection(base.loadDirection, size),
    };
    const placed = allocationMapLayoutAvoidCollision(rows, draft, direction, gap);
    rows = sortedMapRows([...rows, placed]);
    selectedLocation = placed.location;
    selectedLocations = new Set([placed.location]);
    statusText = `${placed.location} tillagd.`;
    renderEditor();
  }

  function addLocationRowAt(locationRow, point) {
    if (!canEdit || !locationRow || rows.some((row) => row.location === locationRow.location)) return;
    pushUndoSnapshot();
    const base = baseRowForPlacement();
    const direction = editor.querySelector("[data-map-series-direction]")?.value || "right";
    const gap = Math.max(0, Number.parseInt(editor.querySelector("[data-map-series-gap]")?.value, 10) || 20);
    const maxPall = allocationMapRound(locationRow.maxPall || base.maxPall || 2);
    const size = allocationMapLayoutSizeForCapacity(
      { ...base, w: allocationMapNumber(locationRow.w, base.w), h: allocationMapNumber(locationRow.h, base.h) },
      maxPall,
    );
    const draft = {
      location: locationRow.location,
      x: Math.round((allocationMapNumber(point?.x, base.x) - size.w / 2) / 10) * 10,
      y: Math.round((allocationMapNumber(point?.y, base.y) - size.h / 2) / 10) * 10,
      w: size.w,
      h: size.h,
      maxPall,
      loadDirection: allocationNormalizeMapLoadDirection(base.loadDirection, size),
    };
    const placed = allocationMapLayoutAvoidCollision(rows, draft, direction, gap);
    rows = sortedMapRows([...rows, placed]);
    selectedLocation = placed.location;
    selectedLocations = new Set([placed.location]);
    statusText = `${placed.location} placerad p\u00e5 kartan.`;
    renderEditor();
  }

  async function saveMapSettings(button) {
    if (!canEdit) return;
    button.disabled = true;
    try {
      const focus = allocationProcessAreaCode();
      const query = focus ? `?area_focus=${encodeURIComponent(focus)}` : "";
      const requestedSignature = allocationMapLayoutSaveSignature(rows);
      const response = await allocationJson(`${ALLOCATION_API}/ytgenerering-map-layout${query}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ locations: rows }),
      });
      const savedLayout = normalizeAllocationMapLayout(response);
      if (allocationMapLayoutSaveSignature(savedLayout.locations) !== requestedSignature) {
        throw new Error("Servern bekräftade inte ytkartsändringarna. Ladda om och försök igen.");
      }
      layout = savedLayout;
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

  function closeMapSettingsContextMenu() {
    document.querySelector(".allocation-map-settings-context-menu")?.remove();
  }

  function positionMapSettingsContextMenu(menu, event) {
    const workspace = editor.querySelector("[data-map-settings-workspace]") || editor;
    const workspaceRect = workspace.getBoundingClientRect();
    const scaleX = workspaceRect.width > 0 ? workspace.clientWidth / workspaceRect.width : 1;
    const scaleY = workspaceRect.height > 0 ? workspace.clientHeight / workspaceRect.height : scaleX;
    const clickX = (event.clientX - workspaceRect.left) * scaleX;
    const clickY = (event.clientY - workspaceRect.top) * scaleY;
    const padding = 8;
    const maxLeft = Math.max(padding, workspace.clientWidth - menu.offsetWidth - padding);
    const maxTop = Math.max(padding, workspace.clientHeight - menu.offsetHeight - padding);
    menu.style.left = `${Math.max(padding, Math.min(clickX, maxLeft))}px`;
    menu.style.top = `${Math.max(padding, Math.min(clickY, maxTop))}px`;
  }

  function openMapSettingsContextMenu(event, location) {
    if (!canEdit || !location || !rows.some((row) => row.location === location)) return;
    event.preventDefault();
    event.stopPropagation();
    closeMapSettingsContextMenu();
    if (!selectedLocations.has(location)) {
      selectedLocations = new Set([location]);
    }
    selectedLocation = location;
    syncSelectionVisuals();

    const menu = document.createElement("div");
    menu.className = "allocation-map-settings-context-menu";
    menu.style.position = "absolute";
    menu.innerHTML = `<button type="button" data-map-context-direction>Byt riktning</button>`;
    menu.addEventListener("click", (clickEvent) => clickEvent.stopPropagation());
    menu.querySelector("[data-map-context-direction]")?.addEventListener("click", () => {
      closeMapSettingsContextMenu();
      cycleSelectedLoadDirections();
      focusMapSettingsWorkspace();
    });
    const workspace = editor.querySelector("[data-map-settings-workspace]") || editor;
    workspace.appendChild(menu);
    positionMapSettingsContextMenu(menu, event);
    window.setTimeout(() => {
      document.addEventListener("click", closeMapSettingsContextMenu, { once: true });
    }, 0);
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
              <g data-map-snap-guides class="allocation-map-settings-guide-layer"></g>
              ${rows.map((item) => `
                <g data-map-setting-node="${allocationEscape(item.location)}">
                  <rect class="allocation-map-setting-loc${selectedLocations.has(item.location) ? " is-selected" : ""}" data-map-setting-rect="${allocationEscape(item.location)}" x="${item.x}" y="${item.y}" width="${item.w}" height="${item.h}"></rect>
                  ${allocationRenderMapSettingLabel(item)}
                  ${allocationRenderMapSettingDirectionArrow(item)}
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
                <button type="button" data-map-add-location="${allocationEscape(item.location)}" draggable="${canEdit ? "true" : "false"}" ${canEdit ? "" : "disabled"}>
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
        if (event.button === 2) return;
        if (event.detail >= 2 && canEdit) {
          rotateLocationFromMapEvent(item.dataset.mapSettingRect || "");
          event.preventDefault();
          return;
        }
        if (Date.now() < ignoreMapContextClickUntil) return;
        if (ignoreNextMapClick) {
          ignoreNextMapClick = false;
          return;
        }
        const location = item.dataset.mapSettingRect || "";
        setSelection(location, event, { keepExisting: true });
        syncSelectionVisuals();
        focusMapSettingsWorkspace();
      });
      item.addEventListener("dblclick", (event) => {
        if (!canEdit || event.button === 2) return;
        rotateLocationFromMapEvent(item.dataset.mapSettingRect || "");
        event.preventDefault();
      });
    });
    editor.querySelectorAll("[data-map-setting-location], [data-map-setting-x], [data-map-setting-y], [data-map-setting-w], [data-map-setting-h], [data-map-setting-max]").forEach((input) => {
      input.addEventListener("change", updateSelectedFromInputs);
    });
    editor.querySelector("[data-map-location-search]")?.addEventListener("input", renderEditor);
    editor.querySelectorAll("[data-map-add-location]").forEach((button) => {
      button.addEventListener("click", () => addLocationRow(availableLocations.find((row) => row.location === button.dataset.mapAddLocation)));
      button.addEventListener("dragstart", (event) => {
        if (!canEdit || !event.dataTransfer) return;
        const location = button.dataset.mapAddLocation || "";
        event.dataTransfer.effectAllowed = "copy";
        event.dataTransfer.setData(LOCATION_DRAG_TYPE, location);
        event.dataTransfer.setData("text/plain", location);
        button.classList.add("is-dragging");
      });
      button.addEventListener("dragend", () => {
        button.classList.remove("is-dragging");
        editor.querySelector(".allocation-map-settings-canvas")?.classList.remove("is-drop-target");
      });
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
        loadDirection: base.loadDirection,
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
    const canvas = editor.querySelector(".allocation-map-settings-canvas");
    canvas?.addEventListener("dragover", (event) => {
      if (!canEdit || !hasLocationDrag(event)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      canvas.classList.add("is-drop-target");
    });
    canvas?.addEventListener("dragleave", (event) => {
      if (event.relatedTarget && canvas.contains(event.relatedTarget)) return;
      canvas.classList.remove("is-drop-target");
    });
    canvas?.addEventListener("drop", (event) => {
      if (!canEdit || !hasLocationDrag(event) || !svg) return;
      event.preventDefault();
      event.stopPropagation();
      canvas.classList.remove("is-drop-target");
      const location = draggedLocationFromEvent(event);
      const locationRow = availableLocations.find((row) => row.location === location);
      addLocationRowAt(locationRow, svgPointFromClient(svg, event.clientX, event.clientY));
      focusMapSettingsWorkspace();
    });
    svg?.addEventListener("wheel", (event) => {
      event.preventDefault();
      zoomView(event.deltaY < 0 ? 0.88 : 1.12, event);
    }, { passive: false });
    svg?.addEventListener("contextmenu", (event) => {
      const node = event.target.closest?.("[data-map-setting-node]");
      const rect = event.target.closest?.("[data-map-setting-rect]") || node?.querySelector("[data-map-setting-rect]");
      const hitRow = rect ? null : mapSettingRowAtClientPoint(svg, event.clientX, event.clientY);
      const location = rect?.dataset.mapSettingRect || hitRow?.location || "";
      if (!location || !canEdit) return;
      openMapSettingsContextMenu(event, location);
    });
    svg?.addEventListener("dblclick", (event) => {
      const node = event.target.closest?.("[data-map-setting-node]");
      const rect = event.target.closest?.("[data-map-setting-rect]") || node?.querySelector("[data-map-setting-rect]");
      const hitRow = rect ? null : mapSettingRowAtClientPoint(svg, event.clientX, event.clientY);
      const location = rect?.dataset.mapSettingRect || hitRow?.location || "";
      if (!location || !canEdit) return;
      rotateLocationFromMapEvent(location);
      event.preventDefault();
    });
    svg?.addEventListener("mousedown", (event) => {
      if (event.button === 2) ignoreMapContextClickUntil = Date.now() + 600;
    }, true);
    svg?.addEventListener("pointerdown", (event) => {
      if (event.button === 2) {
        ignoreMapContextClickUntil = Date.now() + 600;
        return;
      }
      closeMapSettingsContextMenu();
      const node = event.target.closest?.("[data-map-setting-node]");
      const rect = event.target.closest?.("[data-map-setting-rect]") || node?.querySelector("[data-map-setting-rect]");
      const hitRow = rect ? null : mapSettingRowAtClientPoint(svg, event.clientX, event.clientY);
      const location = rect?.dataset.mapSettingRect || hitRow?.location || "";
      if (location && canEdit) {
        const row = rows.find((item) => item.location === location);
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
              arrow: pickedRect?.closest("[data-map-setting-node]")?.querySelector(".allocation-map-setting-direction-arrow"),
              originalX: pickedRow.x,
              originalY: pickedRow.y,
            };
          }),
          startX: event.clientX,
          startY: event.clientY,
          box: svg.getBoundingClientRect(),
          viewBox: { ...ensureViewBox() },
          snapTargets: snapTargetsForDrag(),
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
      try {
        svg.setPointerCapture?.(event.pointerId);
      } catch (_) {
        // Synthetic browser tests do not always create an active pointer first.
      }
      event.preventDefault();
    });
    svg?.addEventListener("pointermove", (event) => {
      if (drag) {
        const scaleX = drag.viewBox.width / Math.max(1, drag.box.width);
        const scaleY = drag.viewBox.height / Math.max(1, drag.box.height);
        const dx = (event.clientX - drag.startX) * scaleX;
        const dy = (event.clientY - drag.startY) * scaleY;
        const snapped = applySnapToDrag(drag, dx, dy, scaleX, scaleY);
        if (Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > 2) drag.moved = true;
        drag.items.forEach((item) => {
          item.row.x = snapped.snapX
            ? Math.round(item.originalX + snapped.dx)
            : Math.round((item.originalX + snapped.dx) / 10) * 10;
          item.row.y = snapped.snapY
            ? Math.round(item.originalY + snapped.dy)
            : Math.round((item.originalY + snapped.dy) / 10) * 10;
          item.rect?.setAttribute("x", item.row.x);
          item.rect?.setAttribute("y", item.row.y);
          allocationUpdateMapSettingLabelElement(item.label, item.row);
          allocationUpdateMapSettingDirectionArrowElement(item.arrow, item.row);
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
      try {
        svg.releasePointerCapture?.(event.pointerId);
      } catch (_) {
        // The pointer may already be released in synthetic browser tests.
      }
      const hadDrag = drag;
      drag = null;
      pan = null;
      updateMapSnapGuides([]);
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
      updateMapSnapGuides([]);
      renderEditor();
    });
  }

  fitView();
  renderEditor();
}

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
  bindFlowFilterButtons(root);
  bindResultActions(root);
}

function renderAllocationPage() {
  if (allocationState.page === "uploads") renderUploadsView();
  else if (allocationState.page === "process") renderCombinedView();
  else if (allocationState.page === "settings") renderAllocationMapSettingsView();
  else if (allocationState.page === "split") renderSoloFlowView("split-values");
}

async function loadAllocationUploadStateForVisibleFlows() {
  const tasks = [];
  if (allocationState.page === "uploads" || allocationVisibleFlowsNeedStoredFiles()) {
    tasks.push(loadStoredAllocationFiles().then((files) => {
      allocationState.files = files;
    }));
  } else if (allocationState.page === "process") {
    allocationState.files = {};
  }
  if (allocationState.page === "uploads" || allocationVisibleFlowsNeedCoreDataStatus()) {
    tasks.push(loadAllocationCoreDataStatus());
  }
  await Promise.all(tasks);
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
  const pageOptions = allocationState.page === "settings"
    ? { anyViewIds: ["allocationSettings", "staffingSettings", "allocationProcessMatrix"] }
    : { requireAllocationTools: true };
  if (allocationState.page === "process") {
    pageOptions.requireAllocationProcess = true;
    pageOptions.denyRedirect = "/dela.html";
  }
  allocationState.user = await initPage(allocationPageActiveName(allocationState.page), pageOptions);
  if (!allocationState.user) return;
  ensureFlowPopoverDismiss();
  if (allocationState.page === "settings") {
    root.innerHTML = `<div class="section-title">${allocationEscape(allocationPrimaryTitle(allocationState.page))}</div><section class="allocation-panel"><p>Laddar...</p></section>`;
    renderAllocationPage();
    return;
  }
  const restoredFromCache = restoreAllocationBootData();
  if (restoredFromCache) renderAllocationPage();
  else root.innerHTML = `<div class="section-title">${allocationEscape(allocationPrimaryTitle(allocationState.page))}</div><section class="allocation-panel"><p>Laddar...</p></section>`;
  try {
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
        loadAllocationFilterProfile(),
      ]);
      await loadAllocationUploadStateForVisibleFlows();
      if (!restoredFromCache && Object.keys(allocationState.files || {}).length) {
        restoreWorkStateOnce();
        renderAllocationPage();
      }
    } else {
      await Promise.all([
        loadAllocationFlows(),
        loadAllocationProcessMatrix(),
        loadAllocationFilterProfile(),
      ]);
      await loadAllocationUploadStateForVisibleFlows();
    }
    if (allocationDesktopAvailable()) {
      void allocationJson("/api/desktop/cache/sync", { method: "POST" }).catch((error) => {
        console.warn("Kunde inte synka lokal desktop-cache.", error);
      });
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
    loadAllocationFilterProfile(),
  ]).finally(() => {
    cacheAllocationBootData();
    allocationUploadsPreloadPromise = null;
  });
  return allocationUploadsPreloadPromise;
};

document.addEventListener("DOMContentLoaded", initAllocationPage);

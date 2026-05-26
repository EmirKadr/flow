// Delade hjälpare: navbar, toast, auth-check.

const THEME_STORAGE_KEY = "flow-theme";
const SIDEBAR_USER_CACHE_KEY = "flow-sidebar-user";
const SIDEBAR_LAYOUT_CACHE_KEY = "flow-sidebar-layout";
const ROLE_VIEW_ACCESS_CACHE_KEY = "flow-role-view-access";
const ALLOCATION_UPLOAD_NOTICE_KEY = "flow-allocation-upload-notice";
const APP_LOG_STORAGE_KEY = "flow-app-log-v1";
const APP_LOG_MAX_ENTRIES = 200;
const COMMON_WAIT_METRIC_REPORT_PATH = "/api/healthcheck/wait-metrics";
const WAIT_METRIC_FLUSH_MS = 10000;
const WAIT_METRIC_MAX_QUEUE = 100;
const FLOW_PAGE_STARTED_AT = typeof performance !== "undefined" && performance.now
  ? performance.now()
  : Date.now();
const ALLOCATION_CORE_UPLOAD_KEYS = [
  "article_max",
  "custom",
  "dimension",
  "item",
  "item_alias",
  "item_attribute",
  "item_option",
  "kpi",
  "kpi_target_rule",
  "location",
  "location_cost",
  "max_csv",
  "pallet_type",
];
const UPLOAD_FILE_STORES = [
  { dbName: "flow-allokering-files", storeName: "files", protectedKeys: ALLOCATION_CORE_UPLOAD_KEYS },
  { dbName: "flow-productivity-files", storeName: "files", protectedKeys: ["kpi"] },
];
const SHARED_ALLOCATION_API = "/api/allokering";
const SHARED_ALLOCATION_DB_NAME = "flow-allokering-files";
const SHARED_ALLOCATION_STORE = "files";
let sharedAllocationMetadataGeneration = 0;
const SHARED_ALLOCATION_FILE_TYPE_KEYS = {
  orders: ["orders"],
  buffer: ["buffer"],
  overview: ["overview"],
  dispatch: ["dispatch"],
  automation: ["saldo"],
  item: ["items"],
  not_putaway: ["not_putaway"],
  prognos: ["prognos"],
  campaign: ["campaign"],
  wms_booking: ["wms_booking"],
  wms_trans: ["wms_trans"],
  wms_pick: ["wms_pick"],
  productivity_pallet: ["productivity_pallet"],
};
const SHARED_ALLOCATION_SLOT_MIRRORS = {
  wms_booking: ["not_putaway"],
};
const SHARED_ALLOCATION_FILE_WORDS = {
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
};
const AREA_FOCUS_STORAGE_KEY = "flow-area-focus";
const AREA_FOCUS_OPTIONS = [
  { value: "MG", label: "MG", title: "Mestergruppen" },
  { value: "GG", label: "GG", title: "Granngården" },
  { value: "AS", label: "AS", title: "Autostore" },
  { value: "EH", label: "EH", title: "E-Handel" },
  { value: "ALLT", label: "∞", title: "Alla områden" },
];
const AREA_FOCUS_FALLBACK_NAMES = {
  MG: "Mestergruppen",
  GG: "Granngården",
  AS: "Autostore",
  EH: "E-Handel",
};
let dynamicAreaFocusOptions = null;
const appLogEntries = readStoredAppLogEntries();
let waitMetricQueue = [];
let waitMetricFlushTimer = null;
let waitMetricInFlight = false;

const THEME_ICONS = {
  light: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4"></circle>
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"></path>
    </svg>
  `,
  dark: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M21 12.8A8.6 8.6 0 1 1 11.2 3a6.8 6.8 0 0 0 9.8 9.8Z"></path>
    </svg>
  `,
};

const DATABASE_ICON = `
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <ellipse cx="12" cy="5" rx="8" ry="3"></ellipse>
    <path d="M4 5v6c0 1.66 3.58 3 8 3s8-1.34 8-3V5"></path>
    <path d="M4 11v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6"></path>
  </svg>
`;

const LOG_ICON = `
  <svg class="log-icon" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M8 3.5h11.5L24 8v20.5H8z"></path>
    <path d="M19.5 3.5V8H24"></path>
    <text x="16" y="17.2" text-anchor="middle" fill="currentColor" stroke="none" font-size="6" font-family="Arial, sans-serif" font-weight="700">LOG</text>
    <path d="M11 22h10"></path>
    <path d="M11 25.5h10"></path>
  </svg>
`;

const ASSISTANT_CHAT_ICON = `
  <svg class="assistant-chat-icon" viewBox="-2 -2 38 36" aria-hidden="true">
    <path fill="currentColor" opacity=".58" d="M12.5 12.2c-5.2 0-9.4 3.2-9.4 7.3 0 1.9.9 3.6 2.5 5l-1 4.2 4.2-2.1c1.1.3 2.4.5 3.7.5 5.2 0 9.4-3.4 9.4-7.5s-4.2-7.4-9.4-7.4Z"></path>
    <path fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" d="M10.7 12.2C11.7 7.4 16.3 4 21.6 4c6.1 0 10.9 4.1 10.9 9.2 0 2.4-1.1 4.6-2.9 6.2l1.2 4.9-4.9-2.3c-1.3.4-2.8.6-4.3.6"></path>
  </svg>
`;

const ASSISTANT_CHAT_STORAGE_KEY = "flow-assistant-chat";
const ASSISTANT_CHAT_OPEN_KEY = "flow-assistant-chat-open";
const ASSISTANT_CHAT_COUNT_KEY = "flow-assistant-chat-count";
const ASSISTANT_CHAT_DRAFT_KEY = "flow-assistant-chat-draft";
const ASSISTANT_CHAT_VERSION_KEY = "flow-assistant-chat-version";
const ASSISTANT_CHAT_STORAGE_VERSION = "2";
const ASSISTANT_CHAT_MAX_QUESTIONS = 10;
let assistantChatPending = false;

const SIDEBAR_MOVE_UP_ICON = `
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="m6 15 6-6 6 6"></path>
  </svg>
`;

const SIDEBAR_MOVE_DOWN_ICON = `
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="m6 9 6 6 6-6"></path>
  </svg>
`;

const SIDEBAR_DEFAULT_LAYOUT = [
  { id: "schedule" },
  { id: "overview" },
  { id: "productivity" },
  { id: "dataFetch" },
  { id: "allocationProcess" },
  { id: "allocationSplit" },
  { id: "persons" },
  { id: "activities" },
  { id: "analytics" },
  { id: "users" },
  { id: "businesses" },
];

const VIEW_ID_ALIASES = {
  stallen: "activities",
  stallenImport: "activityImport",
};

const ROLE_VIEW_IDS = [
  "schedule",
  "overview",
  "productivity",
  "dataFetch",
  "allocationUploads",
  "allocationProcess",
  "allocationProcessMatrix",
  "allocationSplit",
  "persons",
  "personSortOrder",
  "personImport",
  "activities",
  "activityImport",
  "areas",
  "analytics",
  "users",
  "userImport",
  "businesses",
  "appSettings",
  "sidebarLayout",
  "roleAccess",
];

const ROLE_VIEW_ROLES = [
  { value: "super_user", label: "Super User", lockedLevel: "edit" },
  { value: "demo", label: "Demo" },
  { value: "leader", label: "Arbetsledare" },
  { value: "staffing_manager", label: "Bemanningsansvarig" },
  { value: "admin", label: "Administratör" },
  { value: "warehouse_clerk", label: "Lagerkontorist" },
  { value: "article_placer", label: "Artikelplacerare" },
  { value: "viewer", label: "Visning" },
];
const ROLE_VIEW_LEVELS = ["none", "view", "edit"];
const ROLE_VIEW_LEVEL_RANK = { none: 0, view: 1, edit: 2 };
const ROLE_VIEW_DEFAULT_ACCESS = {
  leader: {
    schedule: "edit",
    overview: "edit",
    persons: "edit",
    personImport: "edit",
    activities: "edit",
    activityImport: "edit",
  },
  staffing_manager: {
    schedule: "edit",
    overview: "edit",
    persons: "edit",
    personSortOrder: "edit",
    personImport: "edit",
    activities: "edit",
    activityImport: "edit",
  },
  admin: {
    schedule: "edit",
    overview: "edit",
    persons: "edit",
    personSortOrder: "edit",
    personImport: "edit",
    activities: "edit",
    activityImport: "edit",
    areas: "edit",
    users: "edit",
    appSettings: "edit",
    allocationProcessMatrix: "edit",
  },
  demo: {
    schedule: "edit",
    overview: "edit",
    persons: "edit",
    personSortOrder: "edit",
    personImport: "edit",
    activities: "edit",
    activityImport: "edit",
    areas: "edit",
    users: "edit",
    appSettings: "edit",
    allocationProcessMatrix: "edit",
  },
  warehouse_clerk: {
    allocationUploads: "edit",
    allocationSplit: "edit",
  },
  article_placer: {
    allocationUploads: "edit",
    allocationSplit: "edit",
  },
  viewer: {
    schedule: "view",
    overview: "view",
  },
};

function readTheme() {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "dark" ? "dark" : "light";
  } catch (e) {
    return "light";
  }
}

function updateThemeToggle(theme) {
  const toggle = document.getElementById("theme-toggle");
  if (!toggle) return;
  const isDark = theme === "dark";
  toggle.innerHTML = THEME_ICONS[theme] || THEME_ICONS.light;
  toggle.title = isDark ? "Växla till ljust läge" : "Växla till mörkt läge";
  toggle.setAttribute("aria-label", toggle.title);
  toggle.setAttribute("aria-pressed", isDark ? "true" : "false");
}

function applyTheme(theme, { persist = true } = {}) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = nextTheme;
  if (persist) {
    try { localStorage.setItem(THEME_STORAGE_KEY, nextTheme); } catch (e) {}
  }
  updateThemeToggle(nextTheme);
}

function initThemeToggle() {
  const toggle = document.getElementById("theme-toggle");
  if (!toggle) return;
  updateThemeToggle(readTheme());
  toggle.addEventListener("click", () => {
    applyTheme(readTheme() === "dark" ? "light" : "dark");
  });
}

applyTheme(readTheme(), { persist: false });

function areaFocusOptions() {
  return Array.isArray(dynamicAreaFocusOptions) && dynamicAreaFocusOptions.length
    ? dynamicAreaFocusOptions
    : AREA_FOCUS_OPTIONS;
}

function areaFocusValueForArea(area) {
  const id = Number(area?.id);
  return Number.isInteger(id) ? `AREA:${id}` : "";
}

function buildAreaFocusOptions(areas = [], user = null) {
  const preferredOrder = ["MG", "GG", "AS", "EH", "R3"];
  const visibleAreas = (areas || [])
    .filter((area) => area?.is_active !== false)
    .filter((area) => String(area?.code || "").trim().toUpperCase() !== "ANNAT")
    .slice()
    .sort((a, b) => {
      const ac = String(a?.code || "").trim().toUpperCase();
      const bc = String(b?.code || "").trim().toUpperCase();
      const ai = preferredOrder.includes(ac) ? preferredOrder.indexOf(ac) : 99;
      const bi = preferredOrder.includes(bc) ? preferredOrder.indexOf(bc) : 99;
      return ai - bi || (Number(a?.sort_order) || 0) - (Number(b?.sort_order) || 0) || ac.localeCompare(bc, "sv");
    });
  const options = visibleAreas.map((area) => ({
    value: areaFocusValueForArea(area),
    label: String(area?.code || area?.name || "").trim(),
    title: String(area?.name || area?.code || "").trim(),
    code: String(area?.code || "").trim().toUpperCase(),
    areaId: Number(area?.id),
  })).filter((option) => option.value && option.label);
  const isStigamo = String(user?.business_code || "").toUpperCase() === "STIGAMO";
  if (user?.is_super_user || (isStigamo && options.length > 1)) {
    options.push({ value: "ALLT", label: "∞", title: "Alla områden", code: null, areaId: null });
  }
  return options.length ? options : AREA_FOCUS_OPTIONS;
}

function setAreaFocusAreas(areas = [], user = null) {
  dynamicAreaFocusOptions = buildAreaFocusOptions(areas, user);
  const current = readAreaFocus();
  try { localStorage.setItem(AREA_FOCUS_STORAGE_KEY, current); } catch (e) {}
  updateAreaFocusToggle(current);
  return dynamicAreaFocusOptions;
}

function normalizeAreaFocus(value) {
  const normalized = String(value || "").trim().toUpperCase();
  const options = areaFocusOptions();
  const exact = options.find((option) => String(option.value || "").toUpperCase() === normalized);
  if (exact) return exact.value;
  const byCode = options.find((option) => option.code && option.code === normalized);
  if (byCode) return byCode.value;
  const allOption = options.find((option) => option.value === "ALLT");
  return allOption ? allOption.value : (options[0]?.value || "ALLT");
}

function areaFocusOption(value) {
  const normalized = normalizeAreaFocus(value);
  const options = areaFocusOptions();
  return options.find((option) => option.value === normalized) || options[options.length - 1];
}

function nextAreaFocus(value = readAreaFocus()) {
  const normalized = normalizeAreaFocus(value);
  const options = areaFocusOptions();
  const index = options.findIndex((option) => option.value === normalized);
  return options[(index + 1) % options.length].value;
}

function readAreaFocus() {
  try {
    return normalizeAreaFocus(localStorage.getItem(AREA_FOCUS_STORAGE_KEY));
  } catch (e) {
    return "ALLT";
  }
}

function writeAreaFocus(value) {
  const normalized = normalizeAreaFocus(value);
  try { localStorage.setItem(AREA_FOCUS_STORAGE_KEY, normalized); } catch (e) {}
  updateAreaFocusToggle(normalized);
  window.dispatchEvent(new CustomEvent("flow:areaFocusChanged", { detail: { value: normalized } }));
  return normalized;
}

function areaFocusCode() {
  const focus = readAreaFocus();
  if (focus === "ALLT") return null;
  return areaFocusOption(focus)?.code || null;
}

function findAreaByCode(areas, code) {
  const wanted = String(code || "").trim().toUpperCase();
  if (!wanted) return null;
  return (areas || []).find((area) => String(area.code || "").trim().toUpperCase() === wanted) || null;
}

function preferredAreaIdFromFocus(areas) {
  const focus = readAreaFocus();
  if (focus === "ALLT") return null;
  const visibleAreas = Array.isArray(areas)
    ? areas.filter((area) => area?.is_active !== false)
    : null;
  const option = areaFocusOption(focus);
  if (option?.areaId != null) {
    const areaId = Number(option.areaId);
    if (!visibleAreas || visibleAreas.some((area) => Number(area?.id) === areaId)) {
      return areaId;
    }
    writeAreaFocus("ALLT");
    return null;
  }
  const areaIdMatch = String(focus || "").match(/^AREA:(\d+)$/i);
  if (areaIdMatch) {
    const areaId = Number(areaIdMatch[1]);
    if (!visibleAreas || visibleAreas.some((area) => Number(area?.id) === areaId)) {
      return areaId;
    }
    writeAreaFocus("ALLT");
    return null;
  }
  const area = findAreaByCode(visibleAreas || areas, option?.code || focus);
  if (area) return Number(area.id);
  if (visibleAreas) writeAreaFocus("ALLT");
  return null;
}

function areaFocusAreaId(areas) {
  return preferredAreaIdFromFocus(areas);
}

function areaFocusName(areas, value = readAreaFocus()) {
  const focus = normalizeAreaFocus(value);
  if (focus === "ALLT") return "Alla områden";
  const option = areaFocusOption(focus);
  if (option?.title) return option.title;
  const area = findAreaByCode(areas || [], option?.code || focus);
  return area?.name || AREA_FOCUS_FALLBACK_NAMES[option?.code || focus] || focus;
}

function activityAreaCode(activity, areas) {
  const area = (areas || []).find((item) => Number(item.id) === Number(activity?.area_id));
  return String(area?.code || "").trim().toUpperCase();
}

function normalizeExistingAreaId(value, areas) {
  if (value == null || value === "") return null;
  const id = Number(value);
  if (!Number.isInteger(id)) return null;
  if ((areas || []).length && !(areas || []).some((area) => Number(area.id) === id)) return null;
  return id;
}

function preferredActivityAreaId(areas, userAreaId = null) {
  return preferredAreaIdFromFocus(areas);
}

function activityFocusRank(activity, areas, userAreaId = null) {
  const preferredAreaId = preferredActivityAreaId(areas, userAreaId);
  if (preferredAreaId == null) return 0;
  if (activity?.category === "absence") return 1;
  return Number(activity?.area_id) === preferredAreaId ? 0 : 2;
}

function compareActivitiesForAreaFocus(a, b, areas, userAreaId = null) {
  const preferredAreaId = preferredActivityAreaId(areas, userAreaId);
  if (preferredAreaId != null) {
    const rank = activityFocusRank(a, areas, userAreaId) - activityFocusRank(b, areas, userAreaId);
    if (rank !== 0) return rank;
  }
  return (Number(a?.sort_order) || 0) - (Number(b?.sort_order) || 0)
    || String(a?.label || "").localeCompare(String(b?.label || ""), "sv");
}

function comparePersonsForAreaFocus(a, b, areas) {
  const focus = areaFocusCode();
  if (!focus) return 0;
  const focusedArea = findAreaByCode(areas || [], focus);
  if (!focusedArea) return 0;
  const aFocused = Number(a?.home_area_id) === Number(focusedArea.id) ? 0 : 1;
  const bFocused = Number(b?.home_area_id) === Number(focusedArea.id) ? 0 : 1;
  return aFocused - bFocused;
}

function updateAreaFocusToggle(value = readAreaFocus()) {
  const toggle = document.getElementById("area-focus-toggle");
  if (!toggle) return;
  const normalized = normalizeAreaFocus(value);
  const option = areaFocusOption(normalized);
  toggle.dataset.value = normalized;
  toggle.textContent = option.label;
  toggle.classList.toggle("infinity", normalized === "ALLT");
  toggle.title = `Områdesfokus: ${areaFocusName([], normalized)}`;
  toggle.setAttribute("aria-label", toggle.title);
  toggle.setAttribute("aria-pressed", normalized === "ALLT" ? "false" : "true");
}

function initAreaFocusToggle(user = null) {
  const toggle = document.getElementById("area-focus-toggle");
  if (!toggle) return;
  updateAreaFocusToggle(readAreaFocus());
  api.get("/api/areas")
    .then((areas) => setAreaFocusAreas(areas, user))
    .catch(() => {});
  toggle.addEventListener("click", () => writeAreaFocus(nextAreaFocus()));
}

window.addEventListener("storage", (event) => {
  if (event.key !== AREA_FOCUS_STORAGE_KEY) return;
  const value = normalizeAreaFocus(event.newValue);
  updateAreaFocusToggle(value);
  window.dispatchEvent(new CustomEvent("flow:areaFocusChanged", { detail: { value } }));
});

function setupSyncedHorizontalScroll(target) {
  const element = typeof target === "string" ? document.querySelector(target) : target;
  const wrap = element?.classList?.contains("table-wrap") ? element : element?.closest?.(".table-wrap");
  if (!wrap?.parentNode) return null;

  let top = wrap.previousElementSibling;
  if (!top || !top.classList?.contains("synced-scrollbar-top")) {
    top = document.createElement("div");
    top.className = "synced-scrollbar-top";
    top.setAttribute("aria-hidden", "true");
    const spacer = document.createElement("div");
    spacer.className = "synced-scrollbar-spacer";
    top.appendChild(spacer);
    wrap.parentNode.insertBefore(top, wrap);
  }

  const spacer = top.querySelector(".synced-scrollbar-spacer") || top.appendChild(document.createElement("div"));
  spacer.classList.add("synced-scrollbar-spacer");

  if (wrap.__flowSyncedHorizontalScroll) {
    wrap.__flowSyncedHorizontalScroll.update();
    return top;
  }

  let syncing = false;
  const update = () => {
    const scrollWidth = wrap.scrollWidth || 0;
    spacer.style.width = `${scrollWidth}px`;
    top.hidden = scrollWidth <= wrap.clientWidth + 1;
    if (!top.hidden) top.scrollLeft = wrap.scrollLeft;
  };
  const syncFromTop = () => {
    if (syncing) return;
    syncing = true;
    wrap.scrollLeft = top.scrollLeft;
    syncing = false;
  };
  const syncFromWrap = () => {
    if (syncing) return;
    syncing = true;
    top.scrollLeft = wrap.scrollLeft;
    syncing = false;
  };

  top.addEventListener("scroll", syncFromTop, { passive: true });
  wrap.addEventListener("scroll", syncFromWrap, { passive: true });

  let observer = null;
  if ("ResizeObserver" in window) {
    observer = new ResizeObserver(update);
    observer.observe(wrap);
    Array.from(wrap.children || []).forEach((child) => observer.observe(child));
  } else {
    window.addEventListener("resize", update);
  }

  wrap.__flowSyncedHorizontalScroll = { update, observer };
  requestAnimationFrame(update);
  return top;
}

async function loadCurrentUser() {
  try {
    return await api.get("/api/auth/me");
  } catch (e) {
    return null;
  }
}

function queueToast(message, kind = "info", durationMs = 4000) {
  sessionStorage.setItem("queued-toast", JSON.stringify({ message, kind, durationMs }));
}

function toastLogTitle(kind) {
  if (kind === "success") return "Klart";
  if (kind === "error") return "Fel";
  if (kind === "warn") return "Varning";
  return "Info";
}

function showToast(message, kind = "info", durationMs = 4000, options = {}) {
  const el = document.createElement("div");
  el.className = "toast" + (kind ? " " + kind : "");
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), durationMs);
  if (options.log !== false) {
    appendAppLog(message, kind || "info", options.logTitle || toastLogTitle(kind));
  }
}

function flushQueuedToast() {
  const raw = sessionStorage.getItem("queued-toast");
  if (!raw) return;
  sessionStorage.removeItem("queued-toast");
  try {
    const toast = JSON.parse(raw);
    showToast(toast.message, toast.kind, toast.durationMs);
  } catch (e) {
    // Ignorera trasig sessionStorage-data.
  }
}

function initials(name) {
  return String(name || "?")
    .split(/\s+/).filter(Boolean).slice(0, 2)
    .map((part) => part[0].toUpperCase()).join("");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function renderAssistantInlineMarkdown(value) {
  let html = escapeHtml(value);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return html;
}

function isMarkdownTableLine(line) {
  return /^\s*\|.*\|\s*$/.test(line);
}

function isMarkdownTableSeparator(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function markdownTableCells(line) {
  return String(line || "")
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderAssistantMarkdownTable(lines) {
  const rows = lines
    .filter((line) => !isMarkdownTableSeparator(line))
    .map(markdownTableCells)
    .filter((row) => row.length);
  if (!rows.length) return "";
  const header = rows[0];
  const body = rows.slice(1);
  return `
    <div class="assistant-chat-table-wrap">
      <table class="assistant-chat-table">
        <thead>
          <tr>${header.map((cell) => `<th>${renderAssistantInlineMarkdown(cell)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${body.map((row) => `
            <tr>${row.map((cell) => `<td>${renderAssistantInlineMarkdown(cell)}</td>`).join("")}</tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderAssistantMarkdown(content) {
  const lines = String(content || "").replace(/\r\n/g, "\n").trim().split("\n");
  const html = [];
  let listType = "";

  const closeList = () => {
    if (!listType) return;
    html.push(`</${listType}>`);
    listType = "";
  };

  const openList = (type) => {
    if (listType === type) return;
    closeList();
    listType = type;
    html.push(`<${type}>`);
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      continue;
    }

    if (isMarkdownTableLine(line)) {
      const tableLines = [];
      while (index < lines.length && isMarkdownTableLine(lines[index])) {
        tableLines.push(lines[index]);
        index += 1;
      }
      index -= 1;
      closeList();
      html.push(renderAssistantMarkdownTable(tableLines));
      continue;
    }

    const heading = trimmed.match(/^#{1,4}\s+(.+)$/);
    if (heading) {
      closeList();
      html.push(`<p class="assistant-chat-heading">${renderAssistantInlineMarkdown(heading[1])}</p>`);
      continue;
    }

    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      openList("ul");
      html.push(`<li>${renderAssistantInlineMarkdown(bullet[1])}</li>`);
      continue;
    }

    const numbered = trimmed.match(/^\d+\.\s+(.+)$/);
    if (numbered) {
      openList("ol");
      html.push(`<li>${renderAssistantInlineMarkdown(numbered[1])}</li>`);
      continue;
    }

    closeList();
    html.push(`<p>${renderAssistantInlineMarkdown(trimmed)}</p>`);
  }

  closeList();
  return html.join("");
}

function renderAppLogEntries() {
  const body = document.querySelector("#log-sidebar .log-sidebar-body");
  if (!body) return;
  if (!appLogEntries.length) {
    body.innerHTML = '<p class="log-sidebar-empty">Ingen logg att visa ännu.</p>';
    return;
  }
  body.innerHTML = appLogEntries.map((entry) => `
    <div class="log-entry ${escapeHtml(entry.kind)}">
      <div class="log-entry-meta">${escapeHtml(entry.time)} · ${escapeHtml(entry.title)}</div>
      <div class="log-entry-message">${escapeHtml(entry.message)}</div>
    </div>
  `).join("");
}

function normalizeAppLogKind(kind) {
  const value = String(kind || "info").trim().toLowerCase();
  return ["info", "success", "warn", "error"].includes(value) ? value : "info";
}

function storedAppLogEntry(entry) {
  if (!entry || typeof entry !== "object") return null;
  const message = String(entry.message || "").replace(/\s+/g, " ").trim();
  if (!message) return null;
  const title = String(entry.title || "System").slice(0, 80);
  if (title === "Vy" || message.startsWith("Öppnade vy:")) return null;
  return {
    time: String(entry.time || new Date().toLocaleString("sv-SE")),
    kind: normalizeAppLogKind(entry.kind),
    title,
    message: message.slice(0, 600),
  };
}

function readStoredAppLogEntries() {
  try {
    const raw = sessionStorage.getItem(APP_LOG_STORAGE_KEY);
    if (!raw) return [];
    const payload = JSON.parse(raw);
    const rows = Array.isArray(payload?.entries) ? payload.entries : Array.isArray(payload) ? payload : [];
    return rows.map(storedAppLogEntry).filter(Boolean).slice(0, APP_LOG_MAX_ENTRIES);
  } catch (_error) {
    return [];
  }
}

function persistAppLogEntries() {
  try {
    sessionStorage.setItem(APP_LOG_STORAGE_KEY, JSON.stringify({
      version: 1,
      entries: appLogEntries.slice(0, APP_LOG_MAX_ENTRIES),
    }));
  } catch (_error) {}
}

function appendAppLog(message, kind = "info", title = "System") {
  const entry = storedAppLogEntry({
    time: new Date().toLocaleString("sv-SE"),
    kind,
    title,
    message,
  });
  if (!entry) return;
  appLogEntries.unshift(entry);
  if (appLogEntries.length > APP_LOG_MAX_ENTRIES) appLogEntries.length = APP_LOG_MAX_ENTRIES;
  persistAppLogEntries();
  renderAppLogEntries();
  console.info(`[${title}] ${entry.message}`);
}

function clearAppLog() {
  appLogEntries.length = 0;
  persistAppLogEntries();
  renderAppLogEntries();
}

function waitMetricNow() {
  return typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
}

function waitMetricPath(value) {
  try {
    const url = new URL(value || window.location?.pathname || "/", window.location.origin);
    return url.pathname || "/";
  } catch (_error) {
    return String(value || "/").split("?")[0].split("#")[0] || "/";
  }
}

function sanitizeWaitMetricText(value, maxLength = 160) {
  if (value == null) return null;
  const text = String(value).replace(/\s+/g, " ").trim();
  if (!text) return null;
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
}

function sanitizeWaitMetricDetail(detail) {
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return null;
  const cleaned = {};
  Object.entries(detail).slice(0, 20).forEach(([key, value]) => {
    const safeKey = sanitizeWaitMetricText(key, 80);
    if (!safeKey) return;
    if (typeof value === "number" || typeof value === "boolean") {
      cleaned[safeKey] = value;
    } else {
      cleaned[safeKey] = sanitizeWaitMetricText(value, 300);
    }
  });
  return Object.keys(cleaned).length ? cleaned : null;
}

function activeWaitMetricViewId() {
  return sanitizeWaitMetricText(document.body?.dataset.activePage || window.flowActivePage || "", 80);
}

function scheduleWaitMetricFlush() {
  if (waitMetricFlushTimer || waitMetricInFlight || !waitMetricQueue.length) return;
  waitMetricFlushTimer = setTimeout(() => {
    waitMetricFlushTimer = null;
    void flushWaitMetrics();
  }, WAIT_METRIC_FLUSH_MS);
}

async function flushWaitMetrics({ keepalive = false } = {}) {
  if (waitMetricFlushTimer) {
    clearTimeout(waitMetricFlushTimer);
    waitMetricFlushTimer = null;
  }
  if (waitMetricInFlight || !waitMetricQueue.length) return;
  const items = waitMetricQueue.splice(0, WAIT_METRIC_MAX_QUEUE);
  const body = JSON.stringify({ items });
  if (keepalive && navigator.sendBeacon) {
    try {
      const blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon(COMMON_WAIT_METRIC_REPORT_PATH, blob)) return;
    } catch (_error) {}
  }
  waitMetricInFlight = true;
  try {
    await fetch(COMMON_WAIT_METRIC_REPORT_PATH, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: keepalive && body.length < 60000,
    });
  } catch (_error) {
    // Telemetri far aldrig sega ner anvandaren. Misslyckade batches slapps.
  } finally {
    waitMetricInFlight = false;
    if (waitMetricQueue.length) scheduleWaitMetricFlush();
  }
}

function recordWaitMetric(metric = {}) {
  const duration = Number(metric.duration_ms ?? metric.durationMs ?? 0);
  if (!Number.isFinite(duration) || duration < 0) return;
  waitMetricQueue.push({
    event_type: sanitizeWaitMetricText(metric.event_type || metric.eventType || "interaction", 80) || "interaction",
    view_id: sanitizeWaitMetricText(metric.view_id || metric.viewId || activeWaitMetricViewId(), 80),
    target: sanitizeWaitMetricText(metric.target || waitMetricPath(window.location?.pathname || "/"), 160),
    duration_ms: Math.round(duration),
    status: sanitizeWaitMetricText(metric.status || "ok", 20) || "ok",
    detail: sanitizeWaitMetricDetail(metric.detail),
  });
  if (waitMetricQueue.length > WAIT_METRIC_MAX_QUEUE) {
    waitMetricQueue = waitMetricQueue.slice(-WAIT_METRIC_MAX_QUEUE);
  }
  if (waitMetricQueue.length >= 20) {
    void flushWaitMetrics();
  } else {
    scheduleWaitMetricFlush();
  }
}

function reportPageLoadWaitMetric(activePage) {
  if (!activePage || activePage === "passwordSetup") return;
  recordWaitMetric({
    event_type: "view_load",
    view_id: activePage,
    target: waitMetricPath(window.location?.pathname || "/"),
    duration_ms: waitMetricNow() - FLOW_PAGE_STARTED_AT,
    status: "ok",
    detail: { source: "initPage" },
  });
}

window.addEventListener("pagehide", () => {
  void flushWaitMetrics({ keepalive: true });
});

try {
  if ("PerformanceObserver" in window && PerformanceObserver.supportedEntryTypes?.includes("longtask")) {
    const waitLongTaskObserver = new PerformanceObserver((list) => {
      list.getEntries().forEach((entry) => {
        if (Number(entry.duration || 0) < 75) return;
        recordWaitMetric({
          event_type: "client_long_task",
          view_id: activeWaitMetricViewId(),
          target: "main_thread",
          duration_ms: entry.duration,
          status: "warn",
          detail: { name: entry.name || "longtask" },
        });
      });
    });
    waitLongTaskObserver.observe({ entryTypes: ["longtask"] });
  }
} catch (_error) {}

const CLIENT_RUNTIME_LOGGED_MESSAGES = new Set();

function logClientRuntimeIssue(message, title = "Klientfel") {
  const text = String(message || "Oväntat klientfel.").replace(/\s+/g, " ").trim();
  if (!text) return;
  const key = `${title}:${text}`.slice(0, 300);
  if (CLIENT_RUNTIME_LOGGED_MESSAGES.has(key)) return;
  CLIENT_RUNTIME_LOGGED_MESSAGES.add(key);
  if (CLIENT_RUNTIME_LOGGED_MESSAGES.size > 50) {
    CLIENT_RUNTIME_LOGGED_MESSAGES.clear();
    CLIENT_RUNTIME_LOGGED_MESSAGES.add(key);
  }
  appendAppLog(text, "error", title);
}

window.addEventListener("error", (event) => {
  logClientRuntimeIssue(event.message || event.error?.message, "Klientfel");
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason;
  logClientRuntimeIssue(reason?.message || reason, "Klientfel");
});

function userRoles(user) {
  const rawRoles = Array.isArray(user?.roles) && user.roles.length ? user.roles : [user?.role];
  return [...new Set(rawRoles.map((role) => String(role || "").trim()).filter(Boolean))];
}

function roleDisplayName(role) {
  if (role === "super_user") return "Super User";
  if (role === "demo") return "Demo";
  return ROLE_VIEW_ROLES.find((option) => option.value === role)?.label || role;
}

function sidebarRoleLabel(user) {
  const labels = userRoles(user).map(roleDisplayName);
  if (user?.is_super_user && !labels.includes("Super User")) labels.unshift("Super User");
  return [...new Set(labels)].join(", ");
}

function roleViewDefaultAccess() {
  return Object.fromEntries(ROLE_VIEW_ROLES.map((role) => [
    role.value,
    role.lockedLevel
      ? Object.fromEntries(ROLE_VIEW_IDS.map((viewId) => [viewId, role.lockedLevel]))
      : { ...(ROLE_VIEW_DEFAULT_ACCESS[role.value] || {}) },
  ]));
}

function normalizeViewId(viewId) {
  const value = String(viewId || "").trim();
  return VIEW_ID_ALIASES[value] || value;
}

function normalizeRoleViewAccess(access = {}) {
  const defaults = roleViewDefaultAccess();
  const normalized = roleViewDefaultAccess();
  const roles = new Set(ROLE_VIEW_ROLES.map((role) => role.value));
  const views = new Set(ROLE_VIEW_IDS);
  const incoming = access && typeof access === "object" ? access : {};

  for (const [role, roleAccess] of Object.entries(incoming)) {
    if (!roles.has(role) || !roleAccess || typeof roleAccess !== "object") continue;
    if (ROLE_VIEW_ROLES.find((option) => option.value === role)?.lockedLevel) continue;
    normalized[role] = { ...(defaults[role] || {}) };
    for (const [viewId, level] of Object.entries(roleAccess)) {
      const normalizedViewId = normalizeViewId(viewId);
      if (!views.has(normalizedViewId)) continue;
      normalized[role][normalizedViewId] = ROLE_VIEW_LEVELS.includes(level) ? level : "none";
    }
  }
  return normalized;
}

function readCachedRoleViewAccess() {
  try {
    const raw = localStorage.getItem(ROLE_VIEW_ACCESS_CACHE_KEY);
    return raw ? normalizeRoleViewAccess(JSON.parse(raw)) : roleViewDefaultAccess();
  } catch (e) {
    return roleViewDefaultAccess();
  }
}

function cacheRoleViewAccess(access) {
  const normalized = normalizeRoleViewAccess(access);
  try { localStorage.setItem(ROLE_VIEW_ACCESS_CACHE_KEY, JSON.stringify(normalized)); } catch (e) {}
  return normalized;
}

function roleViewAccessForRender() {
  return readCachedRoleViewAccess();
}

function roleViewAccessPayload(access) {
  return normalizeRoleViewAccess(access);
}

function roleViewAccessLevel(user, viewId) {
  if (user?.is_super_user) return "edit";
  const access = roleViewAccessForRender();
  const normalizedViewId = normalizeViewId(viewId);
  let best = "none";
  const roles = userRoles(user);
  if (user?.is_demo && !roles.includes("demo")) roles.push("demo");
  for (const role of roles) {
    const level = access[role]?.[normalizedViewId] || "none";
    if ((ROLE_VIEW_LEVEL_RANK[level] || 0) > (ROLE_VIEW_LEVEL_RANK[best] || 0)) best = level;
  }
  return best;
}

function canViewPage(user, viewId) {
  return (ROLE_VIEW_LEVEL_RANK[roleViewAccessLevel(user, viewId)] || 0) >= ROLE_VIEW_LEVEL_RANK.view;
}

function canEditPage(user, viewId) {
  return roleViewAccessLevel(user, viewId) === "edit";
}

function isAdminUser(user) {
  const roles = userRoles(user);
  return roles.includes("admin") || user?.is_super_user;
}

function isReadOnlyUser(user) {
  const roles = userRoles(user);
  return roles.includes("viewer") && !roles.includes("leader") && !roles.includes("staffing_manager") && !roles.includes("admin") && !user?.is_super_user;
}

function canEditPlanning(user) {
  return canEditPage(user, "schedule") || canEditPage(user, "overview");
}

function canViewPlanning(user) {
  return canViewPage(user, "schedule") || canViewPage(user, "overview");
}

function canUseAllocationTools(user) {
  return (
    canViewPage(user, "allocationUploads")
    || canViewPage(user, "allocationSplit")
    || canViewPage(user, "allocationProcess")
  );
}

function canUseAllocationProcess(user) {
  return canViewPage(user, "allocationProcess");
}

function sidebarDefaultLayout() {
  return SIDEBAR_DEFAULT_LAYOUT.map((item) => ({
    id: item.id,
    heading: item.heading || "",
    parentId: item.parentId || null,
  }));
}

function sidebarPageDefinitions(user, activePage) {
  return [
    {
      id: "schedule",
      label: "Bemanning",
      href: "/index.html",
      icon: "📋",
      visible: canViewPage(user, "schedule"),
      active: activePage === "schedule",
    },
    {
      id: "overview",
      label: "Översikt",
      href: "/overblick.html",
      icon: "🗓️",
      visible: canViewPage(user, "overview"),
      active: activePage === "overview",
    },
    {
      id: "productivity",
      label: "Produktivitet",
      href: "/produktivitet.html",
      icon: "📈",
      visible: canViewPage(user, "productivity"),
      active: activePage === "productivity",
    },
    {
      id: "dataFetch",
      label: "Hämta data",
      href: "/hamta-data.html",
      icon: "⇩",
      visible: canViewPage(user, "dataFetch"),
      active: activePage === "dataFetch",
    },
    {
      id: "allocationProcess",
      label: "Bearbeta",
      href: "/bearbeta.html",
      icon: "🧮",
      visible: canViewPage(user, "allocationProcess"),
      active: activePage === "allocationProcess",
    },
    {
      id: "allocationSplit",
      label: "Dela",
      href: "/dela.html",
      icon: "✂",
      visible: canViewPage(user, "allocationSplit"),
      active: activePage === "allocationSplit",
    },
    {
      id: "persons",
      label: "Personer",
      href: "/personer.html",
      icon: "👥",
      visible: canViewPage(user, "persons"),
      active: activePage === "persons",
    },
    {
      id: "activities",
      label: "Aktiviteter",
      href: "/aktiviteter.html",
      icon: "📍",
      visible: canViewPage(user, "activities"),
      active: activePage === "activities",
    },
    {
      id: "analytics",
      label: "Historik",
      href: "/historik.html",
      icon: "📊",
      visible: canViewPage(user, "analytics"),
      active: activePage === "analytics",
    },
    {
      id: "users",
      label: "Användare",
      href: "/anvandare.html",
      icon: "👤",
      visible: canViewPage(user, "users"),
      active: activePage === "users",
    },
    {
      id: "businesses",
      label: "Verksamheter",
      href: "/verksamheter.html",
      icon: "⌘",
      visible: Boolean(user?.is_super_user),
      active: activePage === "businesses",
    },
  ];
}

function normalizeSidebarLayout(items = []) {
  const defaults = sidebarDefaultLayout();
  const knownIds = new Set(defaults.map((item) => item.id));
  const normalized = [];
  const seen = new Set();
  const incoming = Array.isArray(items) ? items : [];

  for (const item of incoming) {
    const id = normalizeViewId(item?.id);
    if (!knownIds.has(id) || seen.has(id)) continue;
    seen.add(id);
    const parentId = normalizeViewId(item.parent_id || item.parentId || "");
    normalized.push({
      id,
      heading: String(item.heading || "").trim().slice(0, 80),
      parentId: knownIds.has(parentId) && parentId !== id ? parentId : null,
    });
  }
  for (const item of defaults) {
    if (!seen.has(item.id)) normalized.push(item);
  }

  const byId = Object.fromEntries(normalized.map((item) => [item.id, item]));
  for (const item of normalized) {
    if (!item.parentId || !byId[item.parentId]) {
      item.parentId = null;
      continue;
    }
    const visited = new Set([item.id]);
    let parent = byId[item.parentId];
    while (parent?.parentId) {
      if (visited.has(parent.id)) {
        item.parentId = null;
        break;
      }
      visited.add(parent.id);
      parent = byId[parent.parentId];
    }
    if (item.parentId && byId[item.parentId]?.parentId) item.parentId = null;
  }
  return normalized;
}

function sidebarLayoutSignature(layout) {
  return JSON.stringify(normalizeSidebarLayout(layout).map((item) => ({
    id: item.id,
    heading: item.heading || "",
    parentId: item.parentId || null,
  })));
}

function readCachedSidebarLayout() {
  try {
    const raw = localStorage.getItem(SIDEBAR_LAYOUT_CACHE_KEY);
    return raw ? normalizeSidebarLayout(JSON.parse(raw)) : sidebarDefaultLayout();
  } catch (e) {
    return sidebarDefaultLayout();
  }
}

function cacheSidebarLayout(layout) {
  const normalized = normalizeSidebarLayout(layout);
  try { localStorage.setItem(SIDEBAR_LAYOUT_CACHE_KEY, JSON.stringify(normalized)); } catch (e) {}
  return normalized;
}

function sidebarLayoutForRender() {
  return readCachedSidebarLayout();
}

function sidebarLayoutPayload(layout) {
  return normalizeSidebarLayout(layout).map((item) => ({
    id: item.id,
    heading: item.heading || "",
    parent_id: item.parentId || null,
  }));
}

async function refreshSidebarLayout(user, activePage) {
  const before = sidebarLayoutSignature(sidebarLayoutForRender());
  try {
    const response = await api.get("/api/settings/sidebar");
    const next = cacheSidebarLayout(response?.items || []);
    if (sidebarLayoutSignature(next) !== before) renderSidebar(user, activePage);
  } catch (e) {
    // Menyn har alltid en lokal standardlayout, så ett inställningsfel ska inte blockera sidan.
  }
}

async function refreshRoleViewAccess(user, activePage) {
  const before = JSON.stringify(roleViewAccessForRender());
  try {
    const response = await api.get("/api/settings/role-access");
    const next = cacheRoleViewAccess(response?.access || {});
    if (JSON.stringify(next) !== before) renderSidebar(user, activePage);
  } catch (e) {
    // Standardbehörigheter räcker för att appen ska kunna fortsätta.
  }
}

async function refreshRoleViewAccessForRouting() {
  try {
    const response = await api.get("/api/settings/role-access");
    cacheRoleViewAccess(response?.access || {});
    return true;
  } catch (e) {
    // Om servern inte svarar anvands cache/standard, men redirect ska aldrig loopa.
    return false;
  }
}

function firstAccessiblePageHref(user, activePage = "") {
  const pages = sidebarPageDefinitions(user, activePage);
  const currentPath = window.location?.pathname || "";
  const visiblePage = pages.find((page) => page.visible && page.href && page.href !== currentPath);
  return visiblePage?.href || "";
}

function renderAccessDeniedFallback(message) {
  document.body.classList.remove("with-sidebar");
  document.body.innerHTML = `
    <main class="access-denied-page">
      <section class="card access-denied-card">
        <h1>Ingen behörig vy</h1>
        <p>${escapeHtml(message || "Ditt konto saknar behörighet till den här sidan.")}</p>
        <button type="button" id="access-denied-logout">Logga ut</button>
      </section>
    </main>`;
  document.getElementById("access-denied-logout")?.addEventListener("click", () => {
    window.location.href = "/login.html";
  });
}

function redirectAfterDeniedAccess(user, message, activePage = "") {
  const href = firstAccessiblePageHref(user, activePage);
  if (href) {
    queueToast(message, "error");
    window.location.href = href;
    return true;
  }
  renderAccessDeniedFallback(message);
  return true;
}

function clearAuthNavigationCache() {
  clearCachedSidebarUser();
  try { localStorage.removeItem(ROLE_VIEW_ACCESS_CACHE_KEY); } catch (e) {}
}

async function resolvePostAuthPage(user) {
  if (user?.must_change_password) return "/set-password.html";
  clearAuthNavigationCache();
  await refreshRoleViewAccessForRouting();
  return firstAccessiblePageHref(user, "") || "/index.html";
}

function renderSidebarLink(page, { active = false, subview = false } = {}) {
  const classes = [
    "sidebar-link",
    page.className || "",
    active ? "active" : "",
    subview ? "sidebar-subview" : "",
  ].filter(Boolean).join(" ");
  const idAttr = page.linkId ? ` id="${page.linkId}"` : "";
  const icon = page.iconHtml || escapeHtml(page.icon || "");
  return `
    <a href="${page.href}"${idAttr} class="${classes}" title="${escapeHtml(page.label)}">
      <span class="icon" aria-hidden="true">${icon}${page.trailingHtml || ""}</span>
      <span>${escapeHtml(page.label)}</span>
    </a>
  `;
}

function renderAllocationUploadUtility(user, activePage) {
  if (!canViewPage(user, "allocationUploads")) return "";
  const activeClass = activePage === "allocationUploads" ? " active" : "";
  return `
        <a href="/uppladdningar.html" class="database-toggle${activeClass}" id="allocation-upload-link" title="Uppladdningar" aria-label="Uppladdningar" aria-haspopup="menu">
          ${DATABASE_ICON}
          <span class="upload-arrow" aria-hidden="true">&uarr;</span>
          <span class="upload-notice" id="allocation-upload-notice" hidden></span>
        </a>
  `;
}

function renderLogUtility() {
  return `
        <button class="log-toggle" id="log-toggle" type="button" title="Logg" aria-label="Öppna logg" aria-controls="log-sidebar" aria-expanded="false">
          ${LOG_ICON}
        </button>
  `;
}

function setLogSidebarOpen(open) {
  const panel = document.getElementById("log-sidebar");
  const toggle = document.getElementById("log-toggle");
  if (!panel) return;
  panel.hidden = !open;
  panel.classList.toggle("is-open", open);
  toggle?.classList.toggle("active", open);
  toggle?.setAttribute("aria-expanded", open ? "true" : "false");
}

function ensureLogSidebar(app) {
  if (!app) return;
  let panel = document.getElementById("log-sidebar");
  if (!panel) {
    panel = document.createElement("aside");
    panel.id = "log-sidebar";
    panel.className = "log-sidebar";
    panel.hidden = true;
    app.appendChild(panel);
  }
  panel.innerHTML = `
    <div class="log-sidebar-head">
      <h2>Logg</h2>
      <button type="button" class="log-sidebar-close" id="log-sidebar-close" aria-label="Stäng logg">&times;</button>
    </div>
    <div class="log-sidebar-body">
      <p class="log-sidebar-empty">Ingen logg att visa ännu.</p>
    </div>
  `;
  panel.querySelector("#log-sidebar-close")?.insertAdjacentHTML(
    "beforebegin",
    '<button type="button" class="log-sidebar-clear" id="log-sidebar-clear">Rensa</button>',
  );
  panel.querySelector("#log-sidebar-clear").addEventListener("click", clearAppLog);
  panel.querySelector("#log-sidebar-close").addEventListener("click", () => setLogSidebarOpen(false));
  renderAppLogEntries();
}

function initLogSidebarToggle() {
  const toggle = document.getElementById("log-toggle");
  if (!toggle) return;
  toggle.addEventListener("click", () => {
    const panel = document.getElementById("log-sidebar");
    setLogSidebarOpen(panel?.hidden);
  });
}

function renderAssistantUtility() {
  return `
        <button class="assistant-toggle" id="assistant-toggle" type="button" title="Apphjälp" aria-label="Öppna apphjälp" aria-controls="assistant-chat-panel" aria-expanded="false">
          ${ASSISTANT_CHAT_ICON}
        </button>
  `;
}

function safeSessionGet(key) {
  try {
    return sessionStorage.getItem(key);
  } catch (e) {
    return null;
  }
}

function safeSessionSet(key, value) {
  try {
    sessionStorage.setItem(key, value);
  } catch (e) {}
}

function safeSessionRemove(key) {
  try {
    sessionStorage.removeItem(key);
  } catch (e) {}
}

function clearAssistantLocalSession(options = {}) {
  safeSessionRemove(ASSISTANT_CHAT_STORAGE_KEY);
  if (!options.keepOpenState) safeSessionRemove(ASSISTANT_CHAT_OPEN_KEY);
  safeSessionRemove(ASSISTANT_CHAT_COUNT_KEY);
  safeSessionRemove(ASSISTANT_CHAT_DRAFT_KEY);
  if (!options.keepStorageVersion) safeSessionRemove(ASSISTANT_CHAT_VERSION_KEY);
  assistantChatPending = false;
}

function ensureAssistantLocalSessionVersion() {
  if (safeSessionGet(ASSISTANT_CHAT_VERSION_KEY) === ASSISTANT_CHAT_STORAGE_VERSION) return;
  clearAssistantLocalSession();
  safeSessionSet(ASSISTANT_CHAT_VERSION_KEY, ASSISTANT_CHAT_STORAGE_VERSION);
}

function normalizeAssistantMessages(value) {
  return (Array.isArray(value) ? value : [])
    .filter((message) => message && (message.role === "user" || message.role === "assistant"))
    .map((message) => ({
      role: message.role,
      content: String(message.content || "").trim().slice(0, 4000),
    }))
    .filter((message) => message.content)
    .slice(-21);
}

function readAssistantMessages() {
  try {
    return normalizeAssistantMessages(JSON.parse(safeSessionGet(ASSISTANT_CHAT_STORAGE_KEY) || "[]"));
  } catch (e) {
    return [];
  }
}

function writeAssistantMessages(messages) {
  safeSessionSet(ASSISTANT_CHAT_STORAGE_KEY, JSON.stringify(normalizeAssistantMessages(messages)));
}

function readAssistantQuestionCount() {
  const raw = safeSessionGet(ASSISTANT_CHAT_COUNT_KEY);
  const parsed = Number(raw);
  if (Number.isFinite(parsed) && parsed >= 0) return Math.min(ASSISTANT_CHAT_MAX_QUESTIONS, parsed);
  return Math.min(
    ASSISTANT_CHAT_MAX_QUESTIONS,
    readAssistantMessages().filter((message) => message.role === "user").length
  );
}

function writeAssistantQuestionCount(count) {
  const safeCount = Math.max(0, Math.min(ASSISTANT_CHAT_MAX_QUESTIONS, Number(count) || 0));
  safeSessionSet(ASSISTANT_CHAT_COUNT_KEY, String(safeCount));
  return safeCount;
}

function isAssistantChatOpen() {
  return safeSessionGet(ASSISTANT_CHAT_OPEN_KEY) === "1";
}

function writeAssistantChatOpen(open) {
  safeSessionSet(ASSISTANT_CHAT_OPEN_KEY, open ? "1" : "0");
}

function assistantFriendlyError(error) {
  if (error?.status === 429) {
    return "Du har använt 10 frågor i den här sessionen. Klicka Rensa dialog för att börja om.";
  }
  if (error?.status === 500 && error?.body?.detail) {
    return String(error.body.detail);
  }
  if (error?.status === 502 && error?.body?.detail) {
    return String(error.body.detail);
  }
  if (error?.status === 503) {
    return error.message || "Appchatten är inte konfigurerad på servern ännu.";
  }
  if (error?.status === 504) {
    return "MiniMax svarade inte i tid. Prova igen om en stund.";
  }
  if (error?.status === 0) {
    return "Jag kan inte nå servern just nu. Kontrollera att appen är öppnad via rätt adress och att backend är igång.";
  }
  return error?.message || "Jag kunde inte hämta ett svar just nu.";
}

function renderAssistantMessages() {
  const list = document.getElementById("assistant-chat-messages");
  const counter = document.getElementById("assistant-chat-counter");
  const send = document.getElementById("assistant-chat-send");
  const statusEl = document.getElementById("assistant-chat-status");
  if (!list) return;

  const messages = readAssistantMessages();
  const used = readAssistantQuestionCount();
  if (counter) counter.textContent = `${used}/${ASSISTANT_CHAT_MAX_QUESTIONS} frågor i sessionen`;
  if (send) send.disabled = used >= ASSISTANT_CHAT_MAX_QUESTIONS || assistantChatPending;
  if (statusEl) {
    if (used >= ASSISTANT_CHAT_MAX_QUESTIONS) statusEl.textContent = "Max nått. Rensa dialog för att fortsätta.";
    else if (!assistantChatPending) statusEl.textContent = "";
  }

  if (!messages.length) {
    list.innerHTML = `
      <div class="assistant-chat-empty">
        Fråga om knappar, feltexter, behörigheter, import, schema, produktivitet eller lagerverktyg.
      </div>
    `;
    return;
  }
  list.innerHTML = messages.map((message) => `
    <div class="assistant-chat-message ${message.role}">
      ${message.role === "assistant" ? renderAssistantMarkdown(message.content) : escapeHtml(message.content).replace(/\n/g, "<br>")}
    </div>
  `).join("");
  if (assistantChatPending) {
    list.insertAdjacentHTML("beforeend", `
      <div class="assistant-chat-message assistant assistant-chat-loading" aria-label="Apphjälpen hämtar svar">
        <span class="assistant-chat-spinner" aria-hidden="true"></span>
        <span>Hämtar svar</span>
      </div>
    `);
  }
  list.scrollTop = list.scrollHeight;
}

function setAssistantChatPending(pending) {
  assistantChatPending = Boolean(pending);
  const send = document.getElementById("assistant-chat-send");
  const textarea = document.getElementById("assistant-chat-input");
  const statusEl = document.getElementById("assistant-chat-status");
  if (send) {
    send.disabled = assistantChatPending || readAssistantQuestionCount() >= ASSISTANT_CHAT_MAX_QUESTIONS;
    send.textContent = pending ? "Skickar..." : "Skicka";
  }
  if (textarea) textarea.disabled = assistantChatPending;
  if (statusEl) statusEl.textContent = assistantChatPending ? "Hämtar svar..." : "";
  renderAssistantMessages();
}

function setAssistantChatOpen(open) {
  const panel = document.getElementById("assistant-chat-panel");
  const toggle = document.getElementById("assistant-toggle");
  if (!panel) return;
  panel.hidden = !open;
  panel.classList.toggle("is-open", open);
  toggle?.classList.toggle("active", open);
  toggle?.setAttribute("aria-expanded", open ? "true" : "false");
  toggle?.setAttribute("aria-label", open ? "Stäng apphjälp" : "Öppna apphjälp");
  writeAssistantChatOpen(open);
  if (open) {
    renderAssistantMessages();
    setTimeout(() => document.getElementById("assistant-chat-input")?.focus(), 0);
  }
}

async function clearAssistantChat() {
  clearAssistantLocalSession({ keepOpenState: true, keepStorageVersion: true });
  const input = document.getElementById("assistant-chat-input");
  if (input) input.value = "";
  try {
    await api.post("/api/assistant/clear", {});
  } catch (error) {
    showToast(error.message || "Dialogen rensades lokalt, men serverkvoten kunde inte nollställas.", "warn", 7000);
  }
  renderAssistantMessages();
}

async function submitAssistantQuestion(event) {
  event.preventDefault();
  if (assistantChatPending) return;
  const input = document.getElementById("assistant-chat-input");
  const statusEl = document.getElementById("assistant-chat-status");
  const question = String(input?.value || "").trim();
  if (!question) return;
  if (readAssistantQuestionCount() >= ASSISTANT_CHAT_MAX_QUESTIONS) {
    if (statusEl) statusEl.textContent = "Max 10 frågor. Rensa dialog för att börja om.";
    return;
  }

  const messages = readAssistantMessages();
  messages.push({ role: "user", content: question });
  writeAssistantMessages(messages);
  safeSessionRemove(ASSISTANT_CHAT_DRAFT_KEY);
  if (input) input.value = "";
  renderAssistantMessages();
  setAssistantChatPending(true);

  try {
    const response = await api.post("/api/assistant/chat", {
      messages: readAssistantMessages(),
      page_path: window.location.pathname || "",
    });
    const nextMessages = readAssistantMessages();
    nextMessages.push({ role: "assistant", content: response?.answer || "Jag fick inget textinnehåll tillbaka." });
    writeAssistantMessages(nextMessages);
    if (typeof response?.remaining_questions === "number") {
      writeAssistantQuestionCount(ASSISTANT_CHAT_MAX_QUESTIONS - response.remaining_questions);
    } else {
      writeAssistantQuestionCount(readAssistantQuestionCount() + 1);
    }
  } catch (error) {
    const nextMessages = readAssistantMessages();
    nextMessages.push({ role: "assistant", content: assistantFriendlyError(error) });
    writeAssistantMessages(nextMessages);
    if (error?.status === 429) writeAssistantQuestionCount(ASSISTANT_CHAT_MAX_QUESTIONS);
    showToast(error.message || "Kunde inte hämta chattsvar.", "error", 7000);
  } finally {
    setAssistantChatPending(false);
    renderAssistantMessages();
    document.getElementById("assistant-chat-input")?.focus();
  }
}

function ensureAssistantChatPanel(app) {
  if (!app) return;
  ensureAssistantLocalSessionVersion();
  let panel = document.getElementById("assistant-chat-panel");
  if (!panel) {
    panel = document.createElement("aside");
    panel.id = "assistant-chat-panel";
    panel.className = "assistant-chat-panel";
    app.appendChild(panel);
  }
  panel.hidden = !isAssistantChatOpen();
  panel.innerHTML = `
    <div class="assistant-chat-head">
      <div>
        <h2>Apphjälp</h2>
        <div class="assistant-chat-counter" id="assistant-chat-counter">0/${ASSISTANT_CHAT_MAX_QUESTIONS} frågor i sessionen</div>
      </div>
      <button type="button" class="assistant-chat-clear" id="assistant-chat-clear">Rensa dialog</button>
    </div>
    <div class="assistant-chat-messages" id="assistant-chat-messages" role="log" aria-live="polite"></div>
    <form class="assistant-chat-form" id="assistant-chat-form">
      <textarea id="assistant-chat-input" rows="2" maxlength="1200" placeholder="Ställ en fråga om appen...">${escapeHtml(safeSessionGet(ASSISTANT_CHAT_DRAFT_KEY) || "")}</textarea>
      <div class="assistant-chat-actions">
        <span class="assistant-chat-status" id="assistant-chat-status" aria-live="polite"></span>
        <button type="submit" class="primary" id="assistant-chat-send">Skicka</button>
      </div>
    </form>
  `;
  panel.querySelector("#assistant-chat-form")?.addEventListener("submit", submitAssistantQuestion);
  panel.querySelector("#assistant-chat-clear")?.addEventListener("click", () => {
    void clearAssistantChat();
  });
  panel.querySelector("#assistant-chat-input")?.addEventListener("input", (event) => {
    safeSessionSet(ASSISTANT_CHAT_DRAFT_KEY, event.target.value);
  });
  panel.querySelector("#assistant-chat-input")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    panel.querySelector("#assistant-chat-form")?.requestSubmit();
  });
  renderAssistantMessages();
}

function initAssistantChatToggle() {
  const toggle = document.getElementById("assistant-toggle");
  if (!toggle) return;
  toggle.addEventListener("click", () => {
    setAssistantChatOpen(!isAssistantChatOpen());
  });
  setAssistantChatOpen(isAssistantChatOpen());
}

function renderSidebarNav(user, activePage) {
  const pages = sidebarPageDefinitions(user, activePage);
  const pageById = Object.fromEntries(pages.map((page) => [page.id, page]));
  const visibleIds = new Set(pages.filter((page) => page.visible).map((page) => page.id));
  const layout = normalizeSidebarLayout(sidebarLayoutForRender())
    .filter((item) => visibleIds.has(item.id))
    .map((item) => ({
      ...item,
      parentId: visibleIds.has(item.parentId) ? item.parentId : null,
    }));
  const childrenByParent = {};
  for (const item of layout) {
    if (!item.parentId) continue;
    if (!childrenByParent[item.parentId]) childrenByParent[item.parentId] = [];
    childrenByParent[item.parentId].push(item);
  }

  return layout
    .filter((item) => !item.parentId)
    .map((item) => {
      const page = pageById[item.id];
      if (!page) return "";
      const children = childrenByParent[item.id] || [];
      const childActive = children.some((child) => pageById[child.id]?.active);
      const heading = item.heading
        ? `<div class="sidebar-heading">${escapeHtml(item.heading)}</div>`
        : "";
      const childHtml = children.length
        ? `<div class="sidebar-subviews">${children.map((child) => renderSidebarLink(pageById[child.id], { active: pageById[child.id]?.active, subview: true })).join("")}</div>`
        : "";
      return `${heading}${renderSidebarLink(page, { active: page.active || childActive })}${childHtml}`;
    })
    .join("");
}

function openSidebarEditor(user, activePage) {
  const pages = sidebarPageDefinitions(user, activePage).filter((page) => page.visible);
  const pageById = Object.fromEntries(pages.map((page) => [page.id, page]));
  let draft = normalizeSidebarLayout(sidebarLayoutForRender()).filter((item) => pageById[item.id]);

  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal wide sidebar-editor-modal">
      <h2>Redigera meny</h2>
      <p class="note">Rubriker och undervyer visas bara när sidomenyn är utfälld.</p>
      <div class="sidebar-editor-list" id="sidebar-editor-list"></div>
      <div class="actions">
        <button type="button" id="sidebar-editor-reset">Standard</button>
        <button type="button" id="sidebar-editor-cancel">Avbryt</button>
        <button type="button" class="primary" id="sidebar-editor-save">Spara</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);

  const list = backdrop.querySelector("#sidebar-editor-list");
  const parentOptionsFor = (item) => [
    '<option value="">Ingen</option>',
    ...draft
      .filter((candidate) => candidate.id !== item.id)
      .map((candidate) => `<option value="${candidate.id}" ${item.parentId === candidate.id ? "selected" : ""}>${escapeHtml(pageById[candidate.id]?.label || candidate.id)}</option>`),
  ].join("");

  const renderRows = () => {
    list.innerHTML = draft.map((item, index) => {
      const page = pageById[item.id];
      return `
        <div class="sidebar-editor-row ${item.parentId ? "is-child" : ""}" data-index="${index}">
          <div class="sidebar-editor-view">
            <span class="sidebar-editor-icon">${page.iconHtml || escapeHtml(page.icon || "")}</span>
            <strong>${escapeHtml(page.label)}</strong>
          </div>
          <div class="sidebar-editor-move">
            <button type="button" data-move="-1" ${index === 0 ? "disabled" : ""} aria-label="Flytta upp" title="Flytta upp">${SIDEBAR_MOVE_UP_ICON}</button>
            <button type="button" data-move="1" ${index === draft.length - 1 ? "disabled" : ""} aria-label="Flytta ner" title="Flytta ner">${SIDEBAR_MOVE_DOWN_ICON}</button>
          </div>
          <label class="sidebar-editor-field">
            <span>Rubrik ovanför</span>
            <input data-heading value="${escapeHtml(item.heading || "")}" maxlength="80" />
          </label>
          <label class="sidebar-editor-field">
            <span>Under</span>
            <select data-parent>${parentOptionsFor(item)}</select>
          </label>
        </div>
      `;
    }).join("");

    list.querySelectorAll("[data-move]").forEach((button) => {
      button.addEventListener("click", () => {
        const row = button.closest(".sidebar-editor-row");
        const index = Number(row.dataset.index);
        const nextIndex = index + Number(button.dataset.move);
        if (nextIndex < 0 || nextIndex >= draft.length) return;
        const [item] = draft.splice(index, 1);
        draft.splice(nextIndex, 0, item);
        renderRows();
      });
    });
    list.querySelectorAll("[data-heading]").forEach((input) => {
      input.addEventListener("input", () => {
        draft[Number(input.closest(".sidebar-editor-row").dataset.index)].heading = input.value;
      });
    });
    list.querySelectorAll("[data-parent]").forEach((select) => {
      select.addEventListener("change", () => {
        draft[Number(select.closest(".sidebar-editor-row").dataset.index)].parentId = select.value || null;
        draft = normalizeSidebarLayout(draft).filter((item) => pageById[item.id]);
        renderRows();
      });
    });
  };

  backdrop.querySelector("#sidebar-editor-cancel").addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("#sidebar-editor-reset").addEventListener("click", () => {
    draft = sidebarDefaultLayout().filter((item) => pageById[item.id]);
    renderRows();
  });
  backdrop.querySelector("#sidebar-editor-save").addEventListener("click", async () => {
    const saveButton = backdrop.querySelector("#sidebar-editor-save");
    saveButton.disabled = true;
    try {
      const response = await api.put("/api/settings/sidebar", { items: sidebarLayoutPayload(draft) });
      cacheSidebarLayout(response?.items || draft);
      backdrop.remove();
      renderSidebar(user, activePage);
      showToast("Menyn sparades för alla.", "success", 2500);
    } catch (error) {
      saveButton.disabled = false;
      showToast(error.message || "Kunde inte spara menyn.", "error", 7000);
    }
  });
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) backdrop.remove();
  });
  renderRows();
}

function sidebarUserSnapshot(user) {
  if (!user) return null;
  return {
    username: user.username || "",
    display_name: user.display_name || "",
    role: user.role || "",
    roles: userRoles(user),
    is_super_user: Boolean(user.is_super_user),
    must_change_password: Boolean(user.must_change_password),
  };
}

function cacheSidebarUser(user) {
  try {
    const snapshot = sidebarUserSnapshot(user);
    if (snapshot) {
      const serialized = JSON.stringify(snapshot);
      sessionStorage.setItem(SIDEBAR_USER_CACHE_KEY, serialized);
      localStorage.setItem(SIDEBAR_USER_CACHE_KEY, serialized);
    }
  } catch (e) {}
}

function readCachedSidebarUser() {
  try {
    const raw = sessionStorage.getItem(SIDEBAR_USER_CACHE_KEY) || localStorage.getItem(SIDEBAR_USER_CACHE_KEY);
    if (!raw) return null;
    const user = JSON.parse(raw);
    return user?.username || user?.display_name ? user : null;
  } catch (e) {
    return null;
  }
}

function clearCachedSidebarUser() {
  try { sessionStorage.removeItem(SIDEBAR_USER_CACHE_KEY); } catch (e) {}
  try { localStorage.removeItem(SIDEBAR_USER_CACHE_KEY); } catch (e) {}
}

function pageAccessAllowed(user, activePage, options = {}) {
  if (!user || user.must_change_password) return false;
  if (activePage && activePage !== "passwordSetup" && !canViewPage(user, activePage)) return false;
  if (options.requireAdmin && !isAdminUser(user)) return false;
  if (options.requireSuperUser && !canViewPage(user, activePage)) return false;
  if (options.requirePlanningView && !canViewPage(user, activePage || "schedule")) return false;
  if (options.requireEditor && !canEditPage(user, activePage)) return false;
  if (options.requireAllocationTools && !canViewPage(user, activePage)) return false;
  if (options.requireAllocationProcess && !canViewPage(user, activePage)) return false;
  return true;
}

function cachedUserCanRenderPage(user, activePage, options = {}) {
  return pageAccessAllowed(user, activePage, options);
}

function readAllocationUploadNotice() {
  try {
    const raw = sessionStorage.getItem(ALLOCATION_UPLOAD_NOTICE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function writeAllocationUploadNotice(notice) {
  try {
    if (notice) sessionStorage.setItem(ALLOCATION_UPLOAD_NOTICE_KEY, JSON.stringify(notice));
    else sessionStorage.removeItem(ALLOCATION_UPLOAD_NOTICE_KEY);
  } catch (e) {}
}

function isAllocationUploadsPage() {
  return window.location.pathname.endsWith("/uppladdningar.html")
    || document.getElementById("allocation-upload-link")?.classList.contains("active");
}

function addAllocationUploadNotice(count = 0) {
  const numericCount = Math.max(0, Number(count) || 0);
  if (!numericCount) return;
  if (isAllocationUploadsPage()) {
    clearAllocationUploadNotice();
    return;
  }
  const existing = readAllocationUploadNotice();
  const nextCount = Math.min(999, (Number(existing?.count) || 0) + numericCount);
  writeAllocationUploadNotice({ count: nextCount, at: Date.now() });
}

function updateAllocationUploadIndicator() {
  const button = document.getElementById("allocation-upload-link");
  const noticeEl = document.getElementById("allocation-upload-notice");
  if (!button || !noticeEl) return;
  const notice = readAllocationUploadNotice();
  if (notice?.count) {
    noticeEl.textContent = String(notice.count);
    noticeEl.hidden = false;
    button.title = notice.count === 1 ? "1 fil uppladdad" : `${notice.count} filer uppladdade`;
  } else {
    noticeEl.hidden = true;
    noticeEl.textContent = "";
    button.title = "Uppladdningar";
  }
}

function clearAllocationUploadNotice() {
  writeAllocationUploadNotice(null);
  updateAllocationUploadIndicator();
}

function clearUploadIndexedDbStore(dbName, storeName, { protectedKeys = [] } = {}) {
  return new Promise((resolve, reject) => {
    const protectedKeySet = new Set((protectedKeys || []).map((key) => String(key)));
    const request = indexedDB.open(dbName, 1);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(storeName)) database.createObjectStore(storeName, { keyPath: "key" });
    };
    request.onsuccess = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(storeName)) {
        database.close();
        resolve({ deleted: 0, kept: 0 });
        return;
      }
      let deleted = 0;
      let kept = 0;
      const tx = database.transaction(storeName, "readwrite");
      const store = tx.objectStore(storeName);
      const cursorRequest = store.openCursor();
      cursorRequest.onsuccess = () => {
        const cursor = cursorRequest.result;
        if (!cursor) return;
        const key = String(cursor.key ?? cursor.value?.key ?? "");
        if (protectedKeySet.has(key)) {
          kept += 1;
          cursor.continue();
          return;
        }
        cursor.delete();
        deleted += 1;
        cursor.continue();
      };
      cursorRequest.onerror = () => {
        database.close();
        reject(cursorRequest.error);
      };
      tx.oncomplete = () => {
        database.close();
        resolve({ deleted, kept });
      };
      tx.onerror = () => {
        database.close();
        reject(tx.error);
      };
    };
    request.onerror = () => reject(request.error);
  });
}

function sharedAllocationDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(SHARED_ALLOCATION_DB_NAME, 1);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(SHARED_ALLOCATION_STORE)) {
        database.createObjectStore(SHARED_ALLOCATION_STORE, { keyPath: "key" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function warmSharedAllocationMetadataCache() {
  const metadataGeneration = sharedAllocationMetadataGeneration;
  const database = await sharedAllocationDb();
  return new Promise((resolve, reject) => {
    const tx = database.transaction(SHARED_ALLOCATION_STORE, "readonly");
    const request = tx.objectStore(SHARED_ALLOCATION_STORE).getAll();
    request.onsuccess = () => {
      const files = (request.result || []).map((item) => ({
        key: item.key,
        name: item.name || item.key,
        size: Number(item.size || item.blob?.size || 0),
        type: item.type || item.blob?.type || "",
        lastModified: Number(item.lastModified || Date.now()),
      })).filter((item) => item.key);
      if (metadataGeneration === sharedAllocationMetadataGeneration) {
        try {
          localStorage.setItem("flow-allocation-file-metadata-v1", JSON.stringify({
            version: 1,
            at: Date.now(),
            files,
          }));
        } catch (_error) {}
      }
      database.close();
      resolve(files);
    };
    request.onerror = () => {
      database.close();
      reject(request.error);
    };
  });
}

async function storeSharedAllocationFile(key, file) {
  const database = await sharedAllocationDb();
  return new Promise((resolve, reject) => {
    const tx = database.transaction(SHARED_ALLOCATION_STORE, "readwrite");
    const entry = {
      key,
      name: file.name || key,
      size: file.size || 0,
      type: file.type || "",
      lastModified: file.lastModified || Date.now(),
      blob: file,
    };
    tx.objectStore(SHARED_ALLOCATION_STORE).put(entry);
    tx.oncomplete = () => {
      database.close();
      resolve(entry);
    };
    tx.onerror = () => {
      database.close();
      reject(tx.error);
    };
  });
}

async function detectSharedAllocationFile(file) {
  const fd = new FormData();
  fd.append("file", file, file.name);
  try {
    const response = await fetch(`${SHARED_ALLOCATION_API}/detect`, {
      method: "POST",
      body: fd,
      credentials: "include",
    });
    if (!response.ok) return "";
    const result = await response.json();
    return result?.file_type || "";
  } catch (_error) {
    return "";
  }
}

function sharedAllocationNameHintScore(slotKey, name) {
  return (SHARED_ALLOCATION_FILE_WORDS[slotKey] || []).reduce((best, word) => {
    const normalized = String(word || "").toLowerCase();
    return normalized && name.includes(normalized) ? Math.max(best, normalized.length) : best;
  }, 0);
}

function hintedSharedAllocationKeys(file) {
  const name = String(file?.name || "").toLowerCase();
  let bestKey = "";
  let bestScore = 0;
  for (const key of Object.keys(SHARED_ALLOCATION_FILE_WORDS)) {
    const score = sharedAllocationNameHintScore(key, name);
    if (score > bestScore) {
      bestKey = key;
      bestScore = score;
    }
  }
  return bestKey ? [bestKey] : [];
}

function expandSharedAllocationKeys(keys) {
  const result = [];
  for (const key of keys || []) {
    if (!result.includes(key)) result.push(key);
    for (const mirror of SHARED_ALLOCATION_SLOT_MIRRORS[key] || []) {
      if (!result.includes(mirror)) result.push(mirror);
    }
  }
  return result;
}

function sharedAllocationKeysForType(fileType) {
  return expandSharedAllocationKeys(SHARED_ALLOCATION_FILE_TYPE_KEYS[fileType] || []);
}

async function saveSharedAllocationFiles(files) {
  const incoming = Array.from(files || []);
  if (incoming.length) sharedAllocationMetadataGeneration += 1;
  const saved = [];
  const recognized = [];
  const unknown = [];
  let mappings = 0;
  for (const file of incoming) {
    const fileType = await detectSharedAllocationFile(file);
    const targetKeys = sharedAllocationKeysForType(fileType);
    const keys = targetKeys.length ? targetKeys : expandSharedAllocationKeys(hintedSharedAllocationKeys(file));
    if (!keys.length) {
      unknown.push(file.name || "okand fil");
      continue;
    }
    recognized.push(file.name || keys[0]);
    for (const key of keys) {
      await storeSharedAllocationFile(key, file);
      mappings += 1;
    }
    saved.push(file.name || keys[0]);
  }
  if (mappings) {
    void warmSharedAllocationMetadataCache();
    window.dispatchEvent(new CustomEvent("flow:allocationFilesChanged", {
      detail: { saved: saved.length, mappings },
    }));
  }
  return { saved, recognized, unknown, mappings };
}

async function clearAllUploadedFiles({ confirmUser = true } = {}) {
  sharedAllocationMetadataGeneration += 1;
  if (confirmUser && !confirm("Rensa alla vanliga filval i Uppladdningar? Kärnfiler ligger kvar.")) return false;
  const results = await Promise.all(
    UPLOAD_FILE_STORES.map((item) => clearUploadIndexedDbStore(
      item.dbName,
      item.storeName,
      { protectedKeys: item.protectedKeys || [] },
    )),
  );
  const deleted = results.reduce((sum, item) => sum + (Number(item?.deleted) || 0), 0);
  const kept = results.reduce((sum, item) => sum + (Number(item?.kept) || 0), 0);
  try { localStorage.removeItem("flow-allocation-file-metadata-v1"); } catch (_error) {}
  clearAllocationUploadNotice();
  window.dispatchEvent(new CustomEvent("flow:uploadsCleared", {
    detail: { deleted, keptProtected: kept },
  }));
  showToast(
    deleted
      ? "Vanliga filval är rensade. Kärnfiler ligger kvar."
      : "Inga vanliga filval att rensa. Kärnfiler ligger kvar.",
    "success",
    3000,
  );
  return true;
}

function closeUploadContextMenu() {
  document.querySelector(".upload-context-menu")?.remove();
}

function openUploadContextMenu(event) {
  event.preventDefault();
  event.stopPropagation();
  closeUploadContextMenu();

  const menu = document.createElement("div");
  menu.className = "upload-context-menu";
  menu.setAttribute("role", "menu");
  menu.innerHTML = '<button type="button" role="menuitem">Rensa filer</button>';
  document.body.appendChild(menu);

  const left = Math.min(event.clientX, window.innerWidth - menu.offsetWidth - 8);
  const top = Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 8);
  menu.style.left = `${Math.max(8, left)}px`;
  menu.style.top = `${Math.max(8, top)}px`;

  menu.querySelector("button").addEventListener("click", async () => {
    closeUploadContextMenu();
    try {
      await clearAllUploadedFiles();
    } catch (error) {
      showToast(error.message || "Kunde inte rensa filerna.", "error", 7000);
    }
  });

  setTimeout(() => {
    document.addEventListener("click", closeUploadContextMenu, { once: true });
    document.addEventListener("keydown", (keyEvent) => {
      if (keyEvent.key === "Escape") closeUploadContextMenu();
    }, { once: true });
  }, 0);
}

function setAllocationUploading(active) {
  const button = document.getElementById("allocation-upload-link");
  if (!button) return;
  button.classList.toggle("uploading", Boolean(active));
}

function startAllocationUploadActivity() {
  setAllocationUploading(true);
}

function finishAllocationUploadActivity(count = 0) {
  setAllocationUploading(false);
  if (count > 0) {
    addAllocationUploadNotice(count);
    const text = count === 1 ? "1 fil uppladdad" : `${count} filer uppladdade`;
    showToast(text, "success", 2500);
  }
  updateAllocationUploadIndicator();
}

function finishSidebarInitialRender(app) {
  if (!app?.classList.contains("sidebar-initializing")) return;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => app.classList.remove("sidebar-initializing"));
  });
}

function renderSidebar(user, activePage) {
  let sidebar = document.querySelector(".sidebar");
  let app = document.querySelector(".app");
  if (!sidebar) {
    const body = document.body;
    const topbar = document.querySelector(".topbar");
    if (topbar) topbar.remove();

    const main = document.createElement("main");
    main.className = "main";
    Array.from(body.children).forEach((el) => {
      if (el.tagName === "SCRIPT") return;
      main.appendChild(el);
    });

    sidebar = document.createElement("aside");
    sidebar.className = "sidebar";

    app = document.createElement("div");
    app.className = "app";
    app.classList.add("sidebar-initializing");
    app.appendChild(sidebar);
    app.appendChild(main);
    body.insertBefore(app, body.firstChild);
  }

  const navHtml = renderSidebarNav(user, activePage);
  const editButton = canEditPage(user, "sidebarLayout")
    ? `
      <button class="sidebar-edit" id="sidebar-edit" type="button" title="Redigera meny" aria-label="Redigera meny">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 20h9"></path>
          <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z"></path>
        </svg>
      </button>
    `
    : "";
  const uploadUtility = renderAllocationUploadUtility(user, activePage);
  const logUtility = renderLogUtility();
  const assistantUtility = renderAssistantUtility();
  const userName = user?.display_name || user?.username || "";
  const roleLabel = sidebarRoleLabel(user);

  sidebar.innerHTML = `
    <div class="sidebar-top-row">
      <button class="sidebar-toggle" id="sidebar-toggle" title="Visa/dölj meny" aria-label="Visa/dölj meny">
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round">
          <path d="M4 6h14M4 11h14M4 16h14"/>
        </svg>
      </button>
      ${editButton}
    </div>
    <nav>
      ${navHtml}
    </nav>
    <div class="sidebar-footer">
      <div class="sidebar-utility">
        <button class="area-focus-toggle" id="area-focus-toggle" type="button" title="Områdesfokus" aria-label="Områdesfokus"></button>
        ${assistantUtility}
        ${logUtility}
        ${uploadUtility}
        <button class="theme-toggle" id="theme-toggle" type="button"></button>
      </div>
      <div class="sidebar-bottom">
        <div class="avatar">${initials(user?.display_name || user?.username)}</div>
        <div>
          <div class="who">${escapeHtml(userName)}</div>
          ${roleLabel ? `<div class="sidebar-role">${escapeHtml(roleLabel)}</div>` : ""}
          <a href="#" class="logout" id="logout-link">Logga ut</a>
        </div>
      </div>
    </div>
  `;

  initAreaFocusToggle(user);
  initThemeToggle();
  ensureLogSidebar(app);
  initLogSidebarToggle();
  ensureAssistantChatPanel(app);
  initAssistantChatToggle();
  updateAllocationUploadIndicator();
  document.body.classList.add("sidebar-hydrated");
  const allocationUploadLink = document.getElementById("allocation-upload-link");
  if (allocationUploadLink) {
    allocationUploadLink.addEventListener("click", () => clearAllocationUploadNotice());
    allocationUploadLink.addEventListener("contextmenu", openUploadContextMenu);
  }
  const sidebarEdit = document.getElementById("sidebar-edit");
  if (sidebarEdit) {
    sidebarEdit.addEventListener("click", () => openSidebarEditor(user, activePage));
  }

  const logout = document.getElementById("logout-link");
  if (logout) {
    logout.addEventListener("click", async (e) => {
      e.preventDefault();
      await api.post("/api/auth/logout");
      clearAssistantLocalSession();
      clearCachedSidebarUser();
      try {
        sessionStorage.removeItem("flow-demo-tour-handled");
        sessionStorage.removeItem("flow-demo-tour-state");
      } catch (err) {}
      window.location.href = "/login.html";
    });
  }

  // Toggle collapsed state – hamburger fortsätter rotera åt samma håll vid varje klick
  const toggleBtn = document.getElementById("sidebar-toggle");
  app = app || document.querySelector(".app");
  let togglerRotation = 0;
  const svgIcon = toggleBtn?.querySelector("svg");

  const setCollapsed = (collapsed, animateIcon = false) => {
    sidebar.classList.toggle("collapsed", collapsed);
    if (app) app.classList.toggle("sidebar-collapsed", collapsed);
    if (animateIcon && svgIcon) {
      togglerRotation += 90;
      svgIcon.style.transform = `rotate(${togglerRotation}deg)`;
    }
    try { localStorage.setItem("sidebar-collapsed", collapsed ? "1" : "0"); } catch (e) {}
  };

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      setCollapsed(!sidebar.classList.contains("collapsed"), true);
    });
  }

  try {
    if (localStorage.getItem("sidebar-collapsed") === "1") {
      // Återställ utan animation – håll ikonens rotation i synk med läget
      togglerRotation = 90;
      if (svgIcon) svgIcon.style.transform = `rotate(${togglerRotation}deg)`;
      setCollapsed(true, false);
    }
  } catch (e) {}
  finishSidebarInitialRender(app);
}

// Bakåtkompatibilitet
function renderTopbar(user, activePage) {
  renderSidebar(user, activePage);
}

// === Demo-läge: banner + valbar guidad rundtur ===

const DEMO_TOUR_HANDLED_KEY = "flow-demo-tour-handled";
const DEMO_TOUR_STATE_KEY = "flow-demo-tour-state";

const DEMO_TOUR_DESCRIPTIONS = {
  schedule:
    "Bemanning är hjärtat i flow — här planerar du vem som gör vad timme för timme.<br><br>"
    + "<strong>Vänsterklick</strong> på en cell fokuserar den så du kan välja aktivitet i listan som dyker upp.<br>"
    + "<strong>Högerklick</strong> öppnar samma aktivitetsval direkt i en kontextmeny.<br>"
    + "<strong>Dubbelklick</strong> delar timmen i två halvor om du behöver två aktiviteter inom samma timme.<br>"
    + "<strong>Dra</strong> över flera celler för att fylla dem med samma aktivitet på en gång.<br>"
    + "Knapparna högst upp: <strong>Föregående/Nästa dag</strong>, <strong>Kopiera dag</strong> (klona en dag till en annan), <strong>Rensa dag</strong>, <strong>Närvarande</strong> för utskriftslista samt <strong>Ångra</strong> och <strong>Gör om</strong> för dina senaste ändringar.<br>"
    + "Drag i personnamnen till vänster för att ändra sorteringsordningen (om rollen tillåter det).",
  overview:
    "Översikt visar bemanningen i ett kondenserat format — bra för att se helbilden över veckan eller månaden.<br><br>"
    + "Växla mellan <strong>vecka</strong> och <strong>månad</strong> högst upp.<br>"
    + "<strong>Vänsterklick</strong> på en dag öppnar aktivitetsval för heldagen.<br>"
    + "<strong>Dra</strong> över flera dagar för att sätta samma heldagsaktivitet snabbt.<br>"
    + "<strong>Närvarande</strong> skriver ut vald dags bemannade personer och <strong>Ångra/Gör om</strong> fungerar som i Bemanning.",
  productivity:
    "Produktivitet räknar ut KPI per process och bolag baserat på pick/trans/pallet-loggar plus KPI-mål.<br><br>"
    + "Välj <strong>period</strong> och <strong>verksamhet</strong> i topbaren.<br>"
    + "Klicka på rubriker för att <strong>sortera</strong> tabellen.<br>"
    + "Klicka på en rad för att <strong>borra ner</strong> i detaljer per timme.<br>"
    + "Färgerna i cellerna visar om KPI-målet nås (grönt över, rött under).",
  dataFetch:
    "Hämta data låter dig ladda ner valfri vy från det externa lagersystemet, filtrera och exportera till Excel.<br><br>"
    + "Välj <strong>vy</strong> i listan till vänster — sökrutan hjälper dig hitta rätt.<br>"
    + "Kryssa i de <strong>kolumner</strong> du vill ha med.<br>"
    + "Lägg in <strong>filter</strong> per kolumn för att begränsa raderna.<br>"
    + "Klicka <strong>Hämta</strong> för att förhandsgranska och <strong>Exportera till Excel</strong> för att ladda ner.",
  allocationProcess:
    "Bearbeta hjälper dig planera artikelplacering och köra de stora flödena i lagret.<br><br>"
    + "<strong>Matris</strong>-knappen styr per zon vilka filter (bolag, kundnummer) och flöden som visas.<br>"
    + "Knapparna under varje rubrik kör delflödena — Ordersaldo, LYX, Påfyllnadsprio, Allokering osv.<br>"
    + "<strong>Vänsterklick</strong> kör flödet med dina valda filer.<br>"
    + "Resultat visas i en tabell — klicka på cellerna för att <strong>kopiera</strong> värden, och använd <strong>Exportera Excel</strong> för att spara resultatet.",
  allocationSplit:
    "Dela är verktyget för när du har en <strong>lång lista värden</strong> i en kolumn och behöver dela upp dem i flera mindre delar.<br><br>"
    + "Vanligt exempel: ASK klagar att du klistrat in för många värden samtidigt. Då tar du värdena, klistrar in dem här och Dela ger dig dem uppdelade så att du kan klistra in en bit i taget.<br><br>"
    + "<strong>Klistra in</strong> värdena i textrutan (ett per rad) eller ladda upp en textfil.<br>"
    + "Sätt <strong>Antal per kolumn</strong> (standard 2000).<br>"
    + "Klicka <strong>Dela värden</strong> för att få resultatet uppdelat i kolumner som du kan kopiera en åt gången.",
  persons:
    "Personer är registret över alla som ska kunna bemannas.<br><br>"
    + "<strong>Ny person</strong> öppnar modal för att lägga till en person.<br>"
    + "<strong>Flera nya personer</strong> öppnar tabellmodal för bulk-skapande.<br>"
    + "<strong>Importera Excel</strong> låter dig ladda upp en mall.<br>"
    + "<strong>Vänsterklick</strong> i en cell för att redigera namn, hemområde eller huvudaktivitet inline.<br>"
    + "<strong>Schema</strong>-knappen öppnar veckomallen (vilka timmar personen jobbar).<br>"
    + "<strong>Ta bort</strong> raderar personen permanent (kräver bekräftelse).",
  activities:
    "Aktiviteter definierar vad personer kan tilldelas: plock, lots, VAS osv — med färg, kategori och summering.<br><br>"
    + "<strong>Ny aktivitet</strong> skapar en aktivitet med kod, etikett, område, färg och sortering.<br>"
    + "<strong>Vänsterklick</strong> på en rad för att redigera inline.<br>"
    + "<strong>Summeras som</strong> låter dig gruppera flera koder under en huvudaktivitet i rapporter.<br>"
    + "Färgen syns sedan direkt i Bemanningens celler.",
  analytics:
    "Historik visar audit-loggen och statistik över alla ändringar.<br><br>"
    + "Tre lägen i toppen: <strong>Användarhistorik</strong> (vem ändrade vad), <strong>Analys</strong> (sammanställningar) och <strong>Felkoder</strong> (API-fel).<br>"
    + "<strong>Filter</strong>-fält per kolumn för att hitta specifika händelser.<br>"
    + "Klicka på en rad för att <strong>se gamla och nya värden</strong> sida vid sida.",
  users:
    "Användarvyn är där admin skapar konton, sätter roller och vybehörigheter.<br><br>"
    + "<strong>Ny användare</strong> öppnar modal för konto + roll + område.<br>"
    + "<strong>Flera nya användare</strong> för bulk-skapande med en roll per rad.<br>"
    + "<strong>Vybehörigheter</strong>-knappen öppnar rollmatrisen där du sätter per roll vilka vyer som är Ingen/Visa/Redigera.<br>"
    + "<strong>Redigera</strong> ändrar enskilt konto. <strong>Ta bort</strong> raderar det.<br>"
    + "Checkboxen <strong>Lås bemanningsceller</strong> styr om arbetsledare kan ändra varandras celler.",
  businesses:
    "Verksamheter är Super Users översikt över Stigamo, R3 och deras områden.<br><br>"
    + "<strong>Ny verksamhet</strong> + <strong>Redigera</strong> för att hantera verksamhetskoder/namn.<br>"
    + "Under varje verksamhet listas dess områden med egna <strong>Nytt område</strong>, <strong>Redigera</strong> och <strong>Ta bort</strong>-knappar.",
};

function ensureDemoBanner() {
  if (document.getElementById("demo-mode-banner")) return;
  const banner = document.createElement("div");
  banner.id = "demo-mode-banner";
  banner.className = "demo-banner";
  banner.innerHTML = `
    <span class="demo-banner-dot"></span>
    <strong>DEMO-läge</strong>
    <span>Ändringar sparas inte. Allt nollställs när du loggar ut.</span>
  `;
  const body = document.body;
  if (body.firstChild) body.insertBefore(banner, body.firstChild);
  else body.appendChild(banner);
}

function _demoTourSteps(user, activePage) {
  const pageSteps = sidebarPageDefinitions(user, activePage)
    .filter((page) => page.visible)
    .map((page) => ({
      view_id: page.id,
      label: page.label,
      href: page.href,
      body: DEMO_TOUR_DESCRIPTIONS[page.id] || "Använd vyn fritt — alla ändringar sparas bara i demo-sandlådan.",
    }));
  const utilityStep = {
    view_id: "__utility",
    label: "Verktygsraden längst ner i sidebaren",
    href: null,
    highlights: [
      "area-focus-toggle",
      "assistant-toggle",
      "allocation-upload-link",
      "log-toggle",
      "theme-toggle",
    ],
    body:
      "Längst ner i sidebaren finns en rad små verktygsknappar — jag ringar in dem nu så du ser var.<br><br>"
      + "<strong>MG / GG / ∞ (områdesfokus)</strong> — visar och byter vilket lagerområde du tittar på. Klicka för att cykla mellan dina områden eller välj <strong>∞</strong> för att se alla. Filtrerar Bemanning, Översikt, Personer m.fl.<br><br>"
      + "<strong>Pratbubblan (apphjälp)</strong> — öppnar inbyggd LLM-chatt som kan svara på frågor om appen, knappar och flöden. Bra om du undrar var en funktion finns.<br><br>"
      + "<strong>Databas-ikonen (uppladdningar)</strong> — snabb genväg till uppladdningssidan. <em>Högerklick</em> öppnar en meny med olika uppladdningsalternativ.<br><br>"
      + "<strong>Dokument-ikonen (LOG)</strong> — öppnar en logg-panel som visar vad som hänt i appen under sessionen (toasts, fel m.m.). Bra felsökningsverktyg.<br><br>"
      + "<strong>Sol/måne-ikonen</strong> — växlar mellan ljust och mörkt tema. Inställningen sparas per webbläsare.",
  };
  return [...pageSteps, utilityStep];
}

function _clearDemoTourHighlights() {
  document.querySelectorAll(".demo-tour-highlight").forEach((el) => {
    el.classList.remove("demo-tour-highlight");
  });
}

function _applyDemoTourHighlights(ids) {
  _clearDemoTourHighlights();
  if (!Array.isArray(ids) || ids.length === 0) return;
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.classList.add("demo-tour-highlight");
  });
}

function _readDemoTourState() {
  try {
    const raw = sessionStorage.getItem(DEMO_TOUR_STATE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.steps)) return null;
    return parsed;
  } catch (err) {
    return null;
  }
}

function _writeDemoTourState(state) {
  try {
    if (state === null) {
      sessionStorage.removeItem(DEMO_TOUR_STATE_KEY);
    } else {
      sessionStorage.setItem(DEMO_TOUR_STATE_KEY, JSON.stringify(state));
    }
  } catch (err) {}
}

function _markDemoTourHandled() {
  try { sessionStorage.setItem(DEMO_TOUR_HANDLED_KEY, "1"); } catch (err) {}
}

function _renderDemoTourCard(state) {
  const existing = document.getElementById("demo-tour-card");
  if (existing) existing.remove();
  const step = state.steps[state.currentIndex];
  if (!step) {
    _clearDemoTourHighlights();
    return;
  }
  _applyDemoTourHighlights(step.highlights);
  const card = document.createElement("div");
  card.id = "demo-tour-card";
  card.className = "demo-tour-card";
  card.innerHTML = `
    <div class="demo-tour-header">
      <span class="demo-tour-counter">${state.currentIndex + 1} / ${state.steps.length}</span>
      <strong>${escapeForDemo(step.label)}</strong>
    </div>
    <div class="demo-tour-body">${step.body}</div>
    <div class="demo-tour-actions">
      <button class="demo-tour-skip" type="button">Avsluta rundtur</button>
      <button class="demo-tour-next primary" type="button">${state.currentIndex + 1 < state.steps.length ? "Nästa" : "Klar"}</button>
    </div>
  `;
  document.body.appendChild(card);
  card.querySelector(".demo-tour-skip").addEventListener("click", () => {
    _writeDemoTourState(null);
    _clearDemoTourHighlights();
    card.remove();
  });
  card.querySelector(".demo-tour-next").addEventListener("click", () => {
    const next = state.currentIndex + 1;
    if (next >= state.steps.length) {
      _writeDemoTourState(null);
      _clearDemoTourHighlights();
      card.remove();
      showToast("Rundtur klar. Utforska gärna vyerna fritt.", "success", 4000);
      return;
    }
    const nextStep = state.steps[next];
    _writeDemoTourState({ steps: state.steps, currentIndex: next });
    card.remove();
    _clearDemoTourHighlights();
    if (nextStep.href && window.location.pathname !== nextStep.href) {
      window.location.href = nextStep.href;
    } else {
      _renderDemoTourCard({ steps: state.steps, currentIndex: next });
    }
  });
}

function escapeForDemo(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function _showDemoTourPrompt(user, activePage) {
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal demo-tour-welcome">
        <h2>Välkommen till demo-läget av flow</h2>
        <p>Du ser samma data som finns i produktion just nu. Du kan ändra, skapa, ta bort — <strong>inget sparas till den riktiga databasen</strong> och allt nollställs när du loggar ut.</p>
        <p>Vill du se en kort rundtur av vyerna först, med konkreta tips per vy?</p>
        <div class="actions">
          <button id="demo-tour-no" type="button">Nej tack, jag klickar runt själv</button>
          <button id="demo-tour-yes" class="primary" type="button">Ja, visa rundtur</button>
        </div>
      </div>`;
    document.body.appendChild(backdrop);
    const finish = (start) => {
      _markDemoTourHandled();
      backdrop.remove();
      if (start) {
        const steps = _demoTourSteps(user, activePage);
        if (steps.length > 0) {
          const startIndex = Math.max(0, steps.findIndex((step) => step.view_id === activePage));
          _writeDemoTourState({ steps, currentIndex: startIndex });
          _renderDemoTourCard({ steps, currentIndex: startIndex });
        }
      }
      resolve();
    };
    backdrop.querySelector("#demo-tour-yes").addEventListener("click", () => finish(true));
    backdrop.querySelector("#demo-tour-no").addEventListener("click", () => finish(false));
  });
}

async function maybeShowDemoTourPrompt(user, activePage) {
  if (!user?.is_demo) return;
  let state = _readDemoTourState();
  if (state) {
    // Pågående rundtur — visa kort för aktiv sida om den matchar, annars för rätt steg
    const matchIndex = state.steps.findIndex((step) => step.view_id === activePage);
    if (matchIndex >= 0 && matchIndex !== state.currentIndex) {
      state = { steps: state.steps, currentIndex: matchIndex };
      _writeDemoTourState(state);
    }
    _renderDemoTourCard(state);
    return;
  }
  let handled = false;
  try { handled = sessionStorage.getItem(DEMO_TOUR_HANDLED_KEY) === "1"; } catch (err) {}
  if (handled) return;
  await _showDemoTourPrompt(user, activePage);
}

const BACKGROUND_PREFETCH_TTL_MS = 60 * 1000;
const BACKGROUND_PREFETCH_DELAY_MS = 250;
const backgroundPrefetchState = {
  queue: [],
  seen: new Set(),
  running: false,
  waiters: [],
};

function currentIsoWeekParts(date = new Date()) {
  const target = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = target.getUTCDay() || 7;
  target.setUTCDate(target.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(target.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((target - yearStart) / 86400000) + 1) / 7);
  return { year: target.getUTCFullYear(), week, weekday: day };
}

function enqueueBackgroundPrefetch(path, ttlMs = BACKGROUND_PREFETCH_TTL_MS) {
  if (!path || !window.api?.prefetchGet) return;
  const key = String(path);
  if (backgroundPrefetchState.seen.has(key)) return;
  backgroundPrefetchState.seen.add(key);
  backgroundPrefetchState.queue.push({ path: key, ttlMs });
}

function enqueueBackgroundWork(key, run) {
  if (!key || typeof run !== "function") return;
  const normalizedKey = String(key);
  if (backgroundPrefetchState.seen.has(normalizedKey)) return;
  backgroundPrefetchState.seen.add(normalizedKey);
  backgroundPrefetchState.queue.push({ key: normalizedKey, run });
}

function backgroundPrefetchStatus() {
  return {
    queue: backgroundPrefetchState.queue.length,
    running: backgroundPrefetchState.running,
    seen: backgroundPrefetchState.seen.size,
  };
}

function resolveBackgroundPrefetchWaiters() {
  if (backgroundPrefetchState.running || backgroundPrefetchState.queue.length) return;
  const waiters = backgroundPrefetchState.waiters.splice(0);
  waiters.forEach((resolve) => resolve(backgroundPrefetchStatus()));
}

function waitForBackgroundPrefetchIdle(timeoutMs = 12000) {
  if (!backgroundPrefetchState.running && !backgroundPrefetchState.queue.length) {
    return Promise.resolve(backgroundPrefetchStatus());
  }
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      const index = backgroundPrefetchState.waiters.indexOf(done);
      if (index >= 0) backgroundPrefetchState.waiters.splice(index, 1);
      resolve(backgroundPrefetchStatus());
    }, Math.max(500, Number(timeoutMs) || 12000));
    const done = (status) => {
      clearTimeout(timer);
      resolve(status);
    };
    backgroundPrefetchState.waiters.push(done);
  });
}

function scheduleNextBackgroundPrefetch() {
  if (backgroundPrefetchState.running || !backgroundPrefetchState.queue.length) return;
  backgroundPrefetchState.running = true;
  const run = async () => {
    const item = backgroundPrefetchState.queue.shift();
    if (item) {
      try {
        if (typeof item.run === "function") await item.run();
        else await window.api.prefetchGet(item.path, {
          cacheTtlMs: item.ttlMs,
          telemetryEventType: "background_prefetch",
          telemetrySource: "idle_prefetch",
        });
      } catch (error) {
        appendAppLog(
          `Bakgrundsladdning misslyckades: ${item.path || item.key || "okänt underlag"}${error?.message ? ` (${error.message})` : ""}`,
          "warn",
          "Bakgrund",
        );
      }
    }
    backgroundPrefetchState.running = false;
    if (backgroundPrefetchState.queue.length) {
      setTimeout(scheduleNextBackgroundPrefetch, BACKGROUND_PREFETCH_DELAY_MS);
    } else {
      resolveBackgroundPrefetchWaiters();
    }
  };
  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(run, { timeout: 2000 });
  } else {
    setTimeout(run, BACKGROUND_PREFETCH_DELAY_MS);
  }
}

function enqueueVisiblePagePrefetches(user, activePage) {
  if (!user || !window.api?.prefetchGet) return;
  const { year, week, weekday } = currentIsoWeekParts();
  const areaId = areaFocusAreaId();
  const areaQuery = areaId != null ? `&area_id=${areaId}` : "";

  enqueueBackgroundPrefetch("/api/settings/sidebar", 5 * 60 * 1000);
  enqueueBackgroundPrefetch("/api/settings/role-access", 5 * 60 * 1000);

  if (canViewPage(user, "schedule")) {
    enqueueBackgroundPrefetch("/api/areas");
    enqueueBackgroundPrefetch("/api/activities");
    enqueueBackgroundPrefetch("/api/activities?include_inactive=true");
    if (areaQuery) {
      enqueueBackgroundPrefetch(`/api/schedule?year=${year}&week=${week}&weekday=${weekday}`, 25 * 1000);
      enqueueBackgroundPrefetch(`/api/schedule/summary?year=${year}&week=${week}&weekday=${weekday}`, 25 * 1000);
    }
    enqueueBackgroundPrefetch(`/api/schedule?year=${year}&week=${week}&weekday=${weekday}${areaQuery}`, 25 * 1000);
    enqueueBackgroundPrefetch(`/api/schedule/summary?year=${year}&week=${week}&weekday=${weekday}${areaQuery}`, 25 * 1000);
  }
  if (canViewPage(user, "overview")) {
    enqueueBackgroundPrefetch("/api/areas");
    enqueueBackgroundPrefetch("/api/activities");
    enqueueBackgroundPrefetch("/api/activities?include_inactive=true");
    if (areaQuery) {
      enqueueBackgroundPrefetch(`/api/overview?year=${year}&week=${week}`, 25 * 1000);
    }
    enqueueBackgroundPrefetch(`/api/overview?year=${year}&week=${week}${areaQuery}`, 25 * 1000);
  }
  if (canViewPage(user, "productivity")) {
    enqueueBackgroundPrefetch("/api/areas");
    enqueueBackgroundPrefetch("/api/productivity/files", 20 * 1000);
    enqueueBackgroundPrefetch("/api/productivity/targets", 60 * 1000);
  }
  if (canViewPage(user, "allocationUploads") || canViewPage(user, "allocationProcess") || canViewPage(user, "allocationSplit")) {
    enqueueBackgroundPrefetch("/api/allokering/flows", 60 * 1000);
    enqueueBackgroundPrefetch("/api/coredata/files", 20 * 1000);
    enqueueBackgroundWork("allocation-upload-metadata", warmSharedAllocationMetadataCache);
  }
  if (canViewPage(user, "allocationProcessMatrix")) {
    enqueueBackgroundPrefetch("/api/allokering/process-matrix", 30 * 1000);
  }
  if (canViewPage(user, "persons")) {
    enqueueBackgroundPrefetch(`/api/persons${areaId != null ? `?area_id=${areaId}` : ""}`, 30 * 1000);
    enqueueBackgroundPrefetch("/api/areas");
    enqueueBackgroundPrefetch("/api/activities");
    enqueueBackgroundPrefetch("/api/activities?include_inactive=true");
  }
  if (canViewPage(user, "activities")) {
    enqueueBackgroundPrefetch("/api/activities", 30 * 1000);
    enqueueBackgroundPrefetch("/api/areas");
  }
  if (canViewPage(user, "analytics")) {
    enqueueBackgroundPrefetch("/api/users", 30 * 1000);
    enqueueBackgroundPrefetch("/api/persons?include_inactive=true", 30 * 1000);
    enqueueBackgroundPrefetch("/api/activities?include_inactive=true", 30 * 1000);
    enqueueBackgroundPrefetch("/api/areas?include_inactive=true", 30 * 1000);
  }
  if (canViewPage(user, "users")) {
    enqueueBackgroundPrefetch("/api/users", 30 * 1000);
    enqueueBackgroundPrefetch("/api/settings", 60 * 1000);
    enqueueBackgroundPrefetch("/api/areas", 30 * 1000);
  }
  if (user?.is_super_user || canViewPage(user, "businesses")) {
    enqueueBackgroundPrefetch("/api/businesses", 60 * 1000);
    enqueueBackgroundPrefetch("/api/businesses?include_inactive=true", 60 * 1000);
    enqueueBackgroundPrefetch("/api/areas?include_inactive=true", 60 * 1000);
  }

  if (activePage === "allocationUploads" && window.preloadAllocationUploadsData) {
    window.preloadAllocationUploadsData();
  }
  scheduleNextBackgroundPrefetch();
}

function reportPageOpen(user, activePage) {
  if (!activePage || activePage === "passwordSetup") return;
  const openedPage = sidebarPageDefinitions(user, activePage).find((page) => page.id === activePage);
  const viewLabel = openedPage?.label || activePage;
  if (typeof window.reportClientEvent === "function") {
    window.reportClientEvent("view_open", {
      view_id: activePage,
      view_label: viewLabel,
      page_path: window.location?.pathname || "/",
    });
  } else if (typeof window.api?.reportClientEvent === "function") {
    window.api.reportClientEvent("view_open", {
      view_id: activePage,
      view_label: viewLabel,
      page_path: window.location?.pathname || "/",
    });
  }
}

async function initPage(activePage, options = {}) {
  window.flowActivePage = activePage || "";
  if (document.body) document.body.dataset.activePage = activePage || "";
  const cachedUser = readCachedSidebarUser();
  if (cachedUserCanRenderPage(cachedUser, activePage, options)) {
    renderSidebar(cachedUser, activePage);
  }

  const user = await loadCurrentUser();
  if (!user) {
    clearCachedSidebarUser();
    window.location.href = "/login.html";
    return null;
  }
  if (user.must_change_password && activePage !== "passwordSetup") {
    window.location.href = "/set-password.html";
    return null;
  }
  if (activePage !== "passwordSetup") {
    await refreshRoleViewAccessForRouting();
  }
  if (options.requireAdmin && !isAdminUser(user)) {
    queueToast("Sidan kräver administratörsbehörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  if (activePage !== "passwordSetup" && !canViewPage(user, activePage)) {
    redirectAfterDeniedAccess(user, "Sidan kräver behörighet", activePage);
    return null;
  }
  if (options.requireSuperUser && !canViewPage(user, activePage)) {
    queueToast("Sidan kräver Super User-behörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  if (options.requirePlanningView && !canViewPage(user, activePage || "schedule")) {
    redirectAfterDeniedAccess(user, "Sidan kräver planerings- eller visningsbehörighet", activePage);
    return null;
  }
  if (options.requireEditor && !canEditPage(user, activePage)) {
    redirectAfterDeniedAccess(user, "Sidan kräver redigeringsbehörighet", activePage);
    return null;
  }
  if (options.requireAllocationTools && !canViewPage(user, activePage)) {
    redirectAfterDeniedAccess(user, "Sidan kräver rollen Lagerkontorist eller Artikelplacerare", activePage);
    return null;
  }
  if (options.requireAllocationProcess && !canViewPage(user, activePage)) {
    redirectAfterDeniedAccess(user, "Bearbeta kräver behörighet", activePage);
    return null;
  }
  cacheSidebarUser(user);
  renderSidebar(user, activePage);
  reportPageOpen(user, activePage);
  reportPageLoadWaitMetric(activePage);
  void refreshRoleViewAccess(user, activePage);
  void refreshSidebarLayout(user, activePage);
  void enqueueVisiblePagePrefetches(user, activePage);
  if (activePage === "allocationUploads") clearAllocationUploadNotice();
  flushQueuedToast();
  if (user.is_demo) {
    document.body.classList.add("demo-mode");
    if (typeof ensureDemoBanner === "function") ensureDemoBanner();
    if (typeof maybeShowDemoTourPrompt === "function") {
      void maybeShowDemoTourPrompt(user, activePage);
    }
  }
  return user;
}

function openImportHelpModal(title = "Importera") {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${title}</h2>
      <p class="note">Importen kan göras via Excel-mallen eller direkt i vyn.</p>
      <ol class="import-help-list">
        <li>Excel: ladda ner mallen, fyll i värdena utan att ändra rubrikerna och välj filen med Importera Excel.</li>
        <li>Direkt i vyn: öppna flera nya rader, fyll tabellen och skapa.</li>
      </ol>
      <p class="note">Efter importen visas hur många rader som skapades och vilka rader som hoppades över.</p>
      <div class="actions">
        <button class="primary" id="import-help-close">Stäng</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  backdrop.querySelector("#import-help-close").addEventListener("click", () => backdrop.remove());
}

function setupImportHelpButton(buttonId, title = "Importera") {
  const button = document.getElementById(buttonId);
  if (!button) return;
  button.addEventListener("click", () => openImportHelpModal(title));
}

function modalEnterTargetButton(modal) {
  return modal.querySelector("[data-enter-default]:not(:disabled)")
    || modal.querySelector(".actions button.primary:not(:disabled)")
    || modal.querySelector("button.primary:not(:disabled)");
}

function shouldIgnoreModalEnterTarget(target) {
  if (!target) return true;
  if (target.closest("button, [role='button'], a[href]")) return true;
  if (target.closest("[contenteditable='true']")) return true;
  if (target.matches("textarea")) return true;
  if (target.matches("input[type='checkbox'], input[type='radio']")) return true;
  return false;
}

function handleModalEnterKeydown(event) {
  if (event.key !== "Enter" || event.repeat || event.isComposing) return;
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  const modal = event.target?.closest?.(".modal");
  if (!modal || shouldIgnoreModalEnterTarget(event.target)) return;
  const button = modalEnterTargetButton(modal);
  if (!button) return;
  event.preventDefault();
  button.click();
}

document.addEventListener("keydown", handleModalEnterKeydown);

function bulkImportOptionHtml(option) {
  const normalized = typeof option === "string" ? { value: option, label: option } : option;
  return `<option value="${escapeHtml(normalized.value ?? "")}">${escapeHtml(normalized.label ?? normalized.value ?? "")}</option>`;
}

function bulkImportControlHtml(column) {
  const key = escapeHtml(column.key);
  const requirement = bulkImportRequirementMeta(column);
  const label = escapeHtml(`${column.label || column.key} (${requirement.label.toLowerCase()})`);
  const requiredAttrs = requirement.required ? ' required aria-required="true"' : ' aria-required="false"';
  if (column.type === "select") {
    return `
      <select data-bulk-key="${key}" aria-label="${label}"${requiredAttrs}>
        <option value=""></option>
        ${(column.options || []).map(bulkImportOptionHtml).join("")}
      </select>
    `;
  }
  if (column.type === "number") {
    return `<input data-bulk-key="${key}" type="number" step="${escapeHtml(column.step || 1)}" aria-label="${label}"${requiredAttrs} />`;
  }
  return `<input data-bulk-key="${key}" type="text" autocomplete="off" aria-label="${label}"${requiredAttrs} />`;
}

function bulkImportRequirementMeta(column) {
  const required = column.required === true;
  return {
    label: required ? "Obligatoriskt" : "Frivilligt",
    className: required ? "is-required" : "is-optional",
    required,
  };
}

function bulkImportRequirementLabel(column) {
  return bulkImportRequirementMeta(column).label;
}

function bulkImportHeaderHtml(column) {
  const label = escapeHtml(column.label || column.key);
  const requirement = bulkImportRequirementMeta(column);
  return `
    <th>
      <span class="bulk-import-head-label">${label}</span>
      <span class="bulk-import-head-requirement ${requirement.className}">${requirement.label}</span>
    </th>
  `;
}

function collectBulkImportRows(tbody, columns) {
  const rows = [];
  tbody.querySelectorAll("tr").forEach((tr) => {
    const row = {};
    let hasValue = false;
    columns.forEach((column) => {
      const input = tr.querySelector(`[data-bulk-key="${column.key}"]`);
      const value = String(input?.value || "").trim();
      row[column.key] = value;
      if (value) hasValue = true;
    });
    if (hasValue) rows.push(row);
  });
  return rows;
}

function refreshBulkImportRowNumbers(tbody) {
  tbody.querySelectorAll("tr").forEach((tr, index) => {
    const cell = tr.querySelector(".bulk-import-row-number");
    if (cell) cell.textContent = String(index + 1);
  });
}

function openBulkImportGrid({ title, columns, submitLabel = "Skapa", initialRows = 8, onSubmit }) {
  const safeColumns = Array.isArray(columns) ? columns : [];
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal wide bulk-import-modal">
      <h2>${escapeHtml(title || "Flera nya rader")}</h2>
      <div class="modal-table-scroll bulk-import-scroll">
        <table class="bulk-import-table">
          <thead>
            <tr>
              <th class="bulk-import-row-number">#</th>
              ${safeColumns.map(bulkImportHeaderHtml).join("")}
              <th class="bulk-import-actions"></th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="actions bulk-import-footer">
        <div class="bulk-import-actions-left">
          <button type="button" id="bulk-import-add">+ Lägg till rad</button>
          <button type="button" id="bulk-import-prune">Ta bort tomma</button>
        </div>
        <button type="button" id="bulk-import-cancel">Avbryt</button>
        <button type="button" class="primary" id="bulk-import-submit">${escapeHtml(submitLabel)}</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  const tbody = backdrop.querySelector("tbody");
  const addRow = () => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="bulk-import-row-number"></td>
      ${safeColumns.map((column) => `<td>${bulkImportControlHtml(column)}</td>`).join("")}
      <td class="bulk-import-actions">
        <button type="button" class="bulk-import-remove" title="Ta bort rad" aria-label="Ta bort rad">&times;</button>
      </td>
    `;
    tbody.appendChild(tr);
    tr.querySelector(".bulk-import-remove").addEventListener("click", () => {
      if (tbody.querySelectorAll("tr").length <= 1) return;
      tr.remove();
      refreshBulkImportRowNumbers(tbody);
    });
    refreshBulkImportRowNumbers(tbody);
  };

  for (let index = 0; index < Math.max(1, Number(initialRows) || 8); index += 1) {
    addRow();
  }

  backdrop.querySelector("#bulk-import-add").addEventListener("click", addRow);
  backdrop.querySelector("#bulk-import-prune").addEventListener("click", () => {
    tbody.querySelectorAll("tr").forEach((tr) => {
      const hasValue = safeColumns.some((column) => {
        const input = tr.querySelector(`[data-bulk-key="${column.key}"]`);
        return String(input?.value || "").trim();
      });
      if (!hasValue && tbody.querySelectorAll("tr").length > 1) tr.remove();
    });
    refreshBulkImportRowNumbers(tbody);
  });
  backdrop.querySelector("#bulk-import-cancel").addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("#bulk-import-submit").addEventListener("click", async () => {
    const submitButton = backdrop.querySelector("#bulk-import-submit");
    const rows = collectBulkImportRows(tbody, safeColumns);
    if (!rows.length) {
      showToast("Fyll minst en rad.", "warn", 3000);
      return;
    }
    submitButton.disabled = true;
    try {
      await onSubmit(rows);
      backdrop.remove();
    } catch (error) {
      showToast(error.message || "Kunde inte importera raderna.", "error", 7000);
      submitButton.disabled = false;
    }
  });
}

// ---- Date-selection persistence (sessionStorage) ----
// Tabs hold their own selection across page navigation; login clears it so
// the next session starts on today's date.
const YWD_STORAGE_KEY = "flow-selected-date";

function readSelectedDate() {
  try {
    const raw = sessionStorage.getItem(YWD_STORAGE_KEY);
    if (!raw) return null;
    const parts = raw.split("-").map(Number);
    if (parts.length !== 3 || parts.some((n) => !Number.isFinite(n))) return null;
    return parts;  // [year, month, day]
  } catch (e) {
    return null;
  }
}

function writeSelectedDate(year, month, day) {
  try {
    const y = String(year);
    const m = String(month).padStart(2, "0");
    const d = String(day).padStart(2, "0");
    sessionStorage.setItem(YWD_STORAGE_KEY, `${y}-${m}-${d}`);
  } catch (e) { /* ignore quota errors */ }
}

function clearSelectedDate() {
  try { sessionStorage.removeItem(YWD_STORAGE_KEY); } catch (e) {}
}

window.showToast = showToast;
window.initPage = initPage;
window.queueToast = queueToast;
window.userRoles = userRoles;
window.isAdminUser = isAdminUser;
window.isReadOnlyUser = isReadOnlyUser;
window.ROLE_VIEW_ROLES = ROLE_VIEW_ROLES;
window.ROLE_VIEW_LEVELS = ROLE_VIEW_LEVELS;
window.ROLE_VIEW_IDS = ROLE_VIEW_IDS;
window.SIDEBAR_DEFAULT_LAYOUT = SIDEBAR_DEFAULT_LAYOUT;
window.roleViewDefaultAccess = roleViewDefaultAccess;
window.normalizeViewId = normalizeViewId;
window.normalizeRoleViewAccess = normalizeRoleViewAccess;
window.cacheRoleViewAccess = cacheRoleViewAccess;
window.roleViewAccessPayload = roleViewAccessPayload;
window.canViewPage = canViewPage;
window.canEditPage = canEditPage;
window.canEditPlanning = canEditPlanning;
window.canViewPlanning = canViewPlanning;
window.canUseAllocationTools = canUseAllocationTools;
window.canUseAllocationProcess = canUseAllocationProcess;
window.readAreaFocus = readAreaFocus;
window.writeAreaFocus = writeAreaFocus;
window.areaFocusCode = areaFocusCode;
window.areaFocusAreaId = areaFocusAreaId;
window.areaFocusName = areaFocusName;
window.setAreaFocusAreas = setAreaFocusAreas;
window.preferredAreaIdFromFocus = preferredAreaIdFromFocus;
window.compareActivitiesForAreaFocus = compareActivitiesForAreaFocus;
window.comparePersonsForAreaFocus = comparePersonsForAreaFocus;
window.setupSyncedHorizontalScroll = setupSyncedHorizontalScroll;
window.setupImportHelpButton = setupImportHelpButton;
window.openBulkImportGrid = openBulkImportGrid;
window.appendAppLog = appendAppLog;
window.clearAppLog = clearAppLog;
window.flowRecordWaitMetric = recordWaitMetric;
window.flowFlushWaitMetrics = flushWaitMetrics;
window.flowLog = {
  append: appendAppLog,
  info: (message, title = "Info") => appendAppLog(message, "info", title),
  success: (message, title = "Klart") => appendAppLog(message, "success", title),
  warn: (message, title = "Varning") => appendAppLog(message, "warn", title),
  error: (message, title = "Fel") => appendAppLog(message, "error", title),
  clear: clearAppLog,
};
window.clearAllUploadedFiles = clearAllUploadedFiles;
window.sharedAllocationUploads = {
  saveFiles: saveSharedAllocationFiles,
};
window.flowBackgroundPrefetch = {
  status: backgroundPrefetchStatus,
  waitForIdle: waitForBackgroundPrefetchIdle,
};
window.allocationUploadActivity = {
  start: startAllocationUploadActivity,
  finish: finishAllocationUploadActivity,
  clear: clearAllocationUploadNotice,
};
window.readSelectedDate = readSelectedDate;
window.writeSelectedDate = writeSelectedDate;
window.clearSelectedDate = clearSelectedDate;

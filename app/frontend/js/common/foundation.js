// Delade hjälpare: navbar, toast, auth-check.

const THEME_STORAGE_KEY = "flow-theme";
const APP_ZOOM_STORAGE_KEY = "flow-app-zoom";
const SIDEBAR_USER_CACHE_KEY = "flow-sidebar-user";
const SIDEBAR_LAYOUT_CACHE_KEY = "flow-sidebar-layout";
const ROLE_VIEW_ACCESS_CACHE_KEY = "flow-role-view-access";
const ALLOCATION_UPLOAD_NOTICE_KEY = "flow-allocation-upload-notice";
const APP_LOG_STORAGE_KEY = "flow-app-log-v1";
const APP_LOG_UNREAD_STORAGE_KEY = "flow-app-log-unread-v1";
const APP_LOG_MAX_ENTRIES = 200;
const COMMON_WAIT_METRIC_REPORT_PATH = "/api/healthcheck/wait-metrics";
const COMMON_INTERACTION_EVENT_REPORT_PATH = "/api/audit/interactions";
const COMMON_PUBLIC_INTERACTION_EVENT_REPORT_PATH = "/api/audit/interactions/public";
const WAIT_METRIC_FLUSH_MS = 10000;
const WAIT_METRIC_MAX_QUEUE = 100;
const INTERACTION_FLUSH_MS = 5000;
const INTERACTION_MAX_QUEUE = 100;
const INTERACTION_CONTEXT_MS = 3500;
const FLOW_PAGE_STARTED_AT = typeof performance !== "undefined" && performance.now
  ? performance.now()
  : Date.now();
const APP_ZOOM_DEFAULT = 100;
const APP_ZOOM_MIN = 70;
const APP_ZOOM_MAX = 140;
const APP_ZOOM_STEP = 10;
const ALLOCATION_PROTECTED_UPLOAD_KEYS = [
  "article_max",
  "custom",
  "dimension",
  "dispatch_template",
  "item",
  "item_alias",
  "item_attribute",
  "item_security_info",
  "item_option",
  "kpi",
  "location",
  "location_cost",
  "max_csv",
  "pallet_type",
  "trans_agency",
];
const UPLOAD_FILE_STORES = [
  { dbName: "flow-allokering-files", storeName: "files", protectedKeys: ALLOCATION_PROTECTED_UPLOAD_KEYS },
];
const SHARED_ALLOCATION_API = "/api/allokering";
const SHARED_ALLOCATION_DB_NAME = "flow-allokering-files";
const SHARED_ALLOCATION_STORE = "files";
let sharedAllocationMetadataGeneration = 0;
let uploadClearGeneration = 0;
const SHARED_ALLOCATION_FILE_TYPE_KEYS = {
  orders: ["orders"],
  buffer: ["buffer"],
  overview: ["overview"],
  dispatch: ["dispatch"],
  custom_adr: ["custom_adr"],
  automation: ["saldo"],
  item: ["items"],
  not_putaway: ["not_putaway"],
  prognos: ["prognos"],
  campaign: ["campaign"],
  wms_booking: ["wms_booking"],
  wms_trans: ["wms_trans"],
  wms_pick: ["wms_pick"],
};
const SHARED_ALLOCATION_SLOT_MIRRORS = {
  wms_booking: ["not_putaway"],
};
const SHARED_ALLOCATION_FILE_WORDS = {
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
};
const AREA_FOCUS_STORAGE_KEY = "flow-area-focus";
const AREA_FOCUS_ALL_OPTION = { value: "ALLT", label: "∞", title: "Alla områden", code: null, areaId: null };
let dynamicAreaFocusOptions = null;
let areaFocusLoadState = "idle";
let areaFocusAreasRequest = null;
let appLogEntries = [];
let appLogSignalTimer = null;
let waitMetricQueue = [];
let waitMetricFlushTimer = null;
let waitMetricInFlight = false;
let interactionQueue = [];
let interactionFlushTimer = null;
let interactionInFlight = false;
let lastInteractionContext = null;

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

const MY_SCHEDULE_ICON = `
  <svg class="sidebar-line-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M8 2v3"></path>
    <path d="M16 2v3"></path>
    <path d="M4 8h16"></path>
    <rect x="3" y="4" width="18" height="17" rx="3"></rect>
    <circle cx="9" cy="13" r="1.7"></circle>
    <path d="M13 13h4"></path>
    <path d="M8 17h8"></path>
  </svg>
`;

const MY_PRODUCTIVITY_ICON = `
  <svg class="sidebar-line-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <circle cx="7.5" cy="7" r="3"></circle>
    <path d="M3.5 20c.5-3 2-5 4-5s3.5 2 4 5"></path>
    <path d="M14 19V9"></path>
    <path d="M18 19v-6"></path>
    <path d="M22 19v-9"></path>
  </svg>
`;

const MCP_ICON = `
  <svg class="sidebar-line-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <circle cx="6" cy="12" r="2.4"></circle>
    <circle cx="18" cy="6.5" r="2.4"></circle>
    <circle cx="18" cy="17.5" r="2.4"></circle>
    <path d="M8.2 11.1 15.8 7.4"></path>
    <path d="M8.2 12.9 15.8 16.6"></path>
  </svg>
`;

const LABEL_EDITOR_ICON = `
  <svg class="sidebar-line-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M4 5.8A2.8 2.8 0 0 1 6.8 3h7.7L20 8.5v9.7a2.8 2.8 0 0 1-2.8 2.8H6.8A2.8 2.8 0 0 1 4 18.2Z"></path>
    <path d="M14.5 3v5.5H20"></path>
    <path d="M8 13h4"></path>
    <path d="M8 17h8"></path>
    <path d="M15.5 12h.01"></path>
  </svg>
`;

const TOOLS_ICON = `
  <svg class="sidebar-line-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M9 6V4.8A1.8 1.8 0 0 1 10.8 3h2.4A1.8 1.8 0 0 1 15 4.8V6"></path>
    <path d="M4 9.5h16"></path>
    <rect x="3" y="6" width="18" height="15" rx="3"></rect>
    <path d="M8 13h.01"></path>
    <path d="M12 13h.01"></path>
    <path d="M16 13h.01"></path>
    <path d="M8 17h8"></path>
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
  { id: "staffing" },
  { id: "tools" },
  { id: "allocationProcess" },
  { id: "allocationSettings" },
];

const VIEW_ID_ALIASES = {
  stallen: "activities",
  stallenImport: "activityImport",
};

const ROLE_VIEW_IDS = [
  "mySchedule",
  "myProductivity",
  "schedule",
  "overview",
  "productivity",
  "sankeyInbound",
  "productivityFinance",
  "dataFetch",
  "mcp",
  "labelEditor",
  "allocationUploads",
  "allocationProcess",
  "allocationProcessMatrix",
  "allocationSettings",
  "allocationSplit",
  "staffingSettings",
  "productivityFinanceSettings",
  "persons",
  "personSortOrder",
  "personImport",
  "activities",
  "activityImport",
  "areas",
  "analytics",
  "meta",
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
  { value: "person", label: "Person" },
  { value: "viewer", label: "Visning" },
];
const ROLE_VIEW_LEVELS = ["none", "view", "edit"];
const ROLE_VIEW_LEVEL_RANK = { none: 0, view: 1, edit: 2 };
const PERSONAL_VIEW_IDS = new Set(["mySchedule", "myProductivity"]);
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
    mcp: "edit",
    staffingSettings: "edit",
    allocationProcessMatrix: "edit",
    allocationSettings: "edit",
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
    mcp: "edit",
    staffingSettings: "edit",
    allocationProcessMatrix: "edit",
    allocationSettings: "edit",
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
  person: {
    mySchedule: "view",
    myProductivity: "view",
  },
};


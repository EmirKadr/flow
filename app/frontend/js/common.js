// Delade hjälpare: navbar, toast, auth-check.

const THEME_STORAGE_KEY = "bemanning-theme";
const SIDEBAR_USER_CACHE_KEY = "bemanning-sidebar-user";
const SIDEBAR_LAYOUT_CACHE_KEY = "bemanning-sidebar-layout";
const ROLE_VIEW_ACCESS_CACHE_KEY = "bemanning-role-view-access";
const ALLOCATION_UPLOAD_NOTICE_KEY = "bemanning-allocation-upload-notice";
const UPLOAD_FILE_STORES = [
  { dbName: "bemanning-allokering-files", storeName: "files" },
  { dbName: "bemanning-productivity-files", storeName: "files" },
];
const SHARED_ALLOCATION_API = "/api/allokering";
const SHARED_ALLOCATION_DB_NAME = "bemanning-allokering-files";
const SHARED_ALLOCATION_STORE = "files";
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
  wms_receive: ["wms_receive"],
  wms_booking: ["wms_booking"],
  wms_trans: ["wms_trans"],
  wms_pick: ["wms_pick"],
  wms_correct: ["wms_correct"],
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
  wms_receive: ["v_ask_receive_log", "receive_log", "mottagningslogg"],
  wms_booking: ["v_ask_booking_putaway", "booking_putaway", "inlagringslogg"],
  wms_trans: ["v_ask_trans_log", "trans_log", "transaktionslogg"],
  wms_pick: ["v_ask_pick_log_full", "pick_log_full", "plocklogg"],
  wms_correct: ["v_ask_correct_log", "correct_log", "korrigeringslogg"],
  productivity_pallet: ["v_ask_palletloading_log", "palletloading_log", "palllastningslogg"],
};
const AREA_FOCUS_STORAGE_KEY = "bemanning-area-focus";
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
const appLogEntries = [];

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

const ASSISTANT_CHAT_STORAGE_KEY = "bemanning-assistant-chat";
const ASSISTANT_CHAT_OPEN_KEY = "bemanning-assistant-chat-open";
const ASSISTANT_CHAT_COUNT_KEY = "bemanning-assistant-chat-count";
const ASSISTANT_CHAT_DRAFT_KEY = "bemanning-assistant-chat-draft";
const ASSISTANT_CHAT_VERSION_KEY = "bemanning-assistant-chat-version";
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
  { id: "allocationTrace" },
  { id: "persons" },
  { id: "activities" },
  { id: "analytics" },
  { id: "users" },
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
  "allocationSplit",
  "allocationTrace",
  "persons",
  "personImport",
  "activities",
  "activityImport",
  "areas",
  "analytics",
  "users",
  "userImport",
  "appSettings",
  "sidebarLayout",
  "roleAccess",
];

const ROLE_VIEW_ROLES = [
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
    personImport: "edit",
    activities: "edit",
    activityImport: "edit",
  },
  admin: {
    schedule: "edit",
    overview: "edit",
    persons: "edit",
    personImport: "edit",
    activities: "edit",
    activityImport: "edit",
    areas: "edit",
    users: "edit",
    appSettings: "edit",
  },
  warehouse_clerk: {
    allocationUploads: "edit",
    allocationSplit: "edit",
    allocationTrace: "edit",
  },
  article_placer: {
    allocationUploads: "edit",
    allocationSplit: "edit",
    allocationTrace: "edit",
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

function normalizeAreaFocus(value) {
  const normalized = String(value || "").trim().toUpperCase();
  return AREA_FOCUS_OPTIONS.some((option) => option.value === normalized) ? normalized : "ALLT";
}

function areaFocusOption(value) {
  const normalized = normalizeAreaFocus(value);
  return AREA_FOCUS_OPTIONS.find((option) => option.value === normalized) || AREA_FOCUS_OPTIONS[AREA_FOCUS_OPTIONS.length - 1];
}

function nextAreaFocus(value = readAreaFocus()) {
  const normalized = normalizeAreaFocus(value);
  const index = AREA_FOCUS_OPTIONS.findIndex((option) => option.value === normalized);
  return AREA_FOCUS_OPTIONS[(index + 1) % AREA_FOCUS_OPTIONS.length].value;
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
  window.dispatchEvent(new CustomEvent("bemanning:areaFocusChanged", { detail: { value: normalized } }));
  return normalized;
}

function areaFocusCode() {
  const focus = readAreaFocus();
  return focus === "ALLT" ? null : focus;
}

function findAreaByCode(areas, code) {
  const wanted = String(code || "").trim().toUpperCase();
  if (!wanted) return null;
  return (areas || []).find((area) => String(area.code || "").trim().toUpperCase() === wanted) || null;
}

function preferredAreaIdFromFocus(areas) {
  const focus = areaFocusCode();
  if (!focus) return null;
  const area = findAreaByCode(areas, focus);
  return area ? Number(area.id) : null;
}

function areaFocusName(areas, value = readAreaFocus()) {
  const focus = normalizeAreaFocus(value);
  if (focus === "ALLT") return "Alla områden";
  const area = findAreaByCode(areas || [], focus);
  return area?.name || AREA_FOCUS_FALLBACK_NAMES[focus] || focus;
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
  const focusedAreaId = preferredAreaIdFromFocus(areas);
  return focusedAreaId != null ? focusedAreaId : normalizeExistingAreaId(userAreaId, areas);
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

function initAreaFocusToggle() {
  const toggle = document.getElementById("area-focus-toggle");
  if (!toggle) return;
  updateAreaFocusToggle(readAreaFocus());
  toggle.addEventListener("click", () => writeAreaFocus(nextAreaFocus()));
}

window.addEventListener("storage", (event) => {
  if (event.key !== AREA_FOCUS_STORAGE_KEY) return;
  const value = normalizeAreaFocus(event.newValue);
  updateAreaFocusToggle(value);
  window.dispatchEvent(new CustomEvent("bemanning:areaFocusChanged", { detail: { value } }));
});

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

function showToast(message, kind = "info", durationMs = 4000) {
  const el = document.createElement("div");
  el.className = "toast" + (kind ? " " + kind : "");
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), durationMs);
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

function appendAppLog(message, kind = "info", title = "System") {
  const entry = {
    time: new Date().toLocaleString("sv-SE"),
    kind,
    title,
    message: String(message || ""),
  };
  appLogEntries.unshift(entry);
  if (appLogEntries.length > 100) appLogEntries.length = 100;
  renderAppLogEntries();
  console.info(`[${title}] ${entry.message}`);
}

function userRoles(user) {
  const rawRoles = Array.isArray(user?.roles) && user.roles.length ? user.roles : [user?.role];
  return [...new Set(rawRoles.map((role) => String(role || "").trim()).filter(Boolean))];
}

function roleDisplayName(role) {
  if (role === "super_user") return "Super User";
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
    { ...(ROLE_VIEW_DEFAULT_ACCESS[role.value] || {}) },
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
  for (const role of userRoles(user)) {
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
    || canViewPage(user, "allocationTrace")
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
      id: "allocationTrace",
      label: "Härleda",
      href: "/harleda.html",
      icon: "⌕",
      visible: canViewPage(user, "allocationTrace"),
      active: activePage === "allocationTrace",
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

function clearUploadIndexedDbStore(dbName, storeName) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(dbName, 1);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(storeName)) database.createObjectStore(storeName, { keyPath: "key" });
    };
    request.onsuccess = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(storeName)) {
        database.close();
        resolve();
        return;
      }
      const tx = database.transaction(storeName, "readwrite");
      tx.objectStore(storeName).clear();
      tx.oncomplete = () => {
        database.close();
        resolve();
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
    window.dispatchEvent(new CustomEvent("bemanning:allocationFilesChanged", {
      detail: { saved: saved.length, mappings },
    }));
  }
  return { saved, recognized, unknown, mappings };
}

async function clearAllUploadedFiles({ confirmUser = true } = {}) {
  if (confirmUser && !confirm("Rensa alla valda filer i Uppladdningar?")) return false;
  await Promise.all(UPLOAD_FILE_STORES.map((item) => clearUploadIndexedDbStore(item.dbName, item.storeName)));
  clearAllocationUploadNotice();
  window.dispatchEvent(new CustomEvent("bemanning:uploadsCleared"));
  showToast("Filvalen är rensade.", "success", 2500);
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
      if (el.tagName === "SCRIPT" || el.classList.contains("tips-fab")) return;
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

  initAreaFocusToggle();
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

async function initPage(activePage, options = {}) {
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
  if (options.requireAdmin && !isAdminUser(user)) {
    queueToast("Sidan kräver administratörsbehörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  if (activePage !== "passwordSetup" && !canViewPage(user, activePage)) {
    queueToast("Sidan kräver behörighet", "error");
    window.location.href = options.denyRedirect || "/index.html";
    return null;
  }
  if (options.requireSuperUser && !canViewPage(user, activePage)) {
    queueToast("Sidan kräver Super User-behörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  if (options.requirePlanningView && !canViewPage(user, activePage || "schedule")) {
    queueToast("Sidan kräver planerings- eller visningsbehörighet", "error");
    window.location.href = options.denyRedirect || "/overblick.html";
    return null;
  }
  if (options.requireEditor && !canEditPage(user, activePage)) {
    queueToast("Sidan kräver redigeringsbehörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  if (options.requireAllocationTools && !canViewPage(user, activePage)) {
    queueToast("Sidan kräver rollen Lagerkontorist eller Artikelplacerare", "error");
    window.location.href = "/index.html";
    return null;
  }
  if (options.requireAllocationProcess && !canViewPage(user, activePage)) {
    queueToast("Bearbeta kräver Super User-behörighet", "error");
    window.location.href = options.denyRedirect || "/dela.html";
    return null;
  }
  cacheSidebarUser(user);
  renderSidebar(user, activePage);
  void refreshRoleViewAccess(user, activePage);
  void refreshSidebarLayout(user, activePage);
  if (activePage === "allocationUploads") clearAllocationUploadNotice();
  flushQueuedToast();
  return user;
}

function openImportHelpModal(title = "Importera") {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${title}</h2>
      <p class="note">Importen görs via Excel-mallen som hör till vyn.</p>
      <ol class="import-help-list">
        <li>Ladda ner importmallen.</li>
        <li>Fyll i värdena i filen utan att ändra rubrikerna.</li>
        <li>Spara Excel-filen.</li>
        <li>Klicka på Importera Excel och välj filen.</li>
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

// ---- Date-selection persistence (sessionStorage) ----
// Tabs hold their own selection across page navigation; login clears it so
// the next session starts on today's date.
const YWD_STORAGE_KEY = "bemanning-selected-date";

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
window.areaFocusName = areaFocusName;
window.preferredAreaIdFromFocus = preferredAreaIdFromFocus;
window.compareActivitiesForAreaFocus = compareActivitiesForAreaFocus;
window.comparePersonsForAreaFocus = comparePersonsForAreaFocus;
window.setupImportHelpButton = setupImportHelpButton;
window.appendAppLog = appendAppLog;
window.clearAllUploadedFiles = clearAllUploadedFiles;
window.sharedAllocationUploads = {
  saveFiles: saveSharedAllocationFiles,
};
window.allocationUploadActivity = {
  start: startAllocationUploadActivity,
  finish: finishAllocationUploadActivity,
  clear: clearAllocationUploadNotice,
};
window.readSelectedDate = readSelectedDate;
window.writeSelectedDate = writeSelectedDate;
window.clearSelectedDate = clearSelectedDate;

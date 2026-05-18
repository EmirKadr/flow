// Delade hjälpare: navbar, toast, auth-check.

const THEME_STORAGE_KEY = "bemanning-theme";
const SIDEBAR_USER_CACHE_KEY = "bemanning-sidebar-user";
const ALLOCATION_UPLOAD_NOTICE_KEY = "bemanning-allocation-upload-notice";
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

function activityFocusRank(activity, areas) {
  const focus = areaFocusCode();
  if (!focus) return 0;
  if (activity?.category === "absence") return 1;
  return activityAreaCode(activity, areas) === focus ? 0 : 2;
}

function compareActivitiesForAreaFocus(a, b, areas) {
  const focus = areaFocusCode();
  if (focus) {
    const rank = activityFocusRank(a, areas) - activityFocusRank(b, areas);
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

function userRoles(user) {
  const rawRoles = Array.isArray(user?.roles) && user.roles.length ? user.roles : [user?.role];
  return [...new Set(rawRoles.map((role) => String(role || "").trim()).filter(Boolean))];
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
  const roles = userRoles(user);
  return roles.includes("leader") || roles.includes("staffing_manager") || roles.includes("admin") || user?.is_super_user;
}

function canViewPlanning(user) {
  const roles = userRoles(user);
  return roles.includes("viewer") || canEditPlanning(user);
}

function canUseAllocationTools(user) {
  const roles = userRoles(user);
  return roles.includes("warehouse_clerk") || roles.includes("article_placer") || user?.is_super_user;
}

function canUseAllocationProcess(user) {
  return Boolean(user?.is_super_user);
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

function cachedUserCanRenderPage(user, options = {}) {
  if (!user || user.must_change_password) return false;
  if (options.requireAdmin && !isAdminUser(user)) return false;
  if (options.requireSuperUser && !user.is_super_user) return false;
  if (options.requirePlanningView && !canViewPlanning(user)) return false;
  if (options.requireEditor && !canEditPlanning(user)) return false;
  if (options.requireAllocationTools && !canUseAllocationTools(user)) return false;
  if (options.requireAllocationProcess && !canUseAllocationProcess(user)) return false;
  return true;
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
    writeAllocationUploadNotice({ count, at: Date.now() });
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

  const adminLink = isAdminUser(user)
    ? `<a href="/anvandare.html" class="${activePage === "users" ? "active" : ""}"><span class="icon" aria-hidden="true">👤</span><span>Användare</span></a>`
    : "";
  const analyticsLink = user?.is_super_user
    ? `<a href="/historik.html" class="${activePage === "analytics" ? "active" : ""}"><span class="icon" aria-hidden="true">📊</span><span>Historik</span></a>`
    : "";
  const productivityLink = user?.is_super_user
    ? `<a href="/produktivitet.html" class="${activePage === "productivity" ? "active" : ""}"><span class="icon" aria-hidden="true">📈</span><span>Produktivitet</span></a>`
    : "";
  const scheduleLink = canViewPlanning(user)
    ? `<a href="/index.html" class="${activePage === "schedule" ? "active" : ""}"><span class="icon" aria-hidden="true">📋</span><span>Bemanning</span></a>`
    : "";
  const allocationProcessLink = canUseAllocationProcess(user)
    ? `<a href="/bearbeta.html" class="${activePage === "allocationProcess" ? "active" : ""}"><span class="icon" aria-hidden="true">🧮</span><span>Bearbeta</span></a>`
    : "";
  const allocationLinks = canUseAllocationTools(user)
    ? `
      ${allocationProcessLink}
      <a href="/dela.html" class="${activePage === "allocationSplit" ? "active" : ""}"><span class="icon" aria-hidden="true">✂</span><span>Dela</span></a>
      <a href="/harleda.html" class="${activePage === "allocationTrace" ? "active" : ""}"><span class="icon" aria-hidden="true">⌕</span><span>Härleda</span></a>
    `
    : "";

  const editorLinks = canEditPlanning(user)
    ? `
      <a href="/personer.html" class="${activePage === "persons" ? "active" : ""}"><span class="icon" aria-hidden="true">👥</span><span>Personer</span></a>
      <a href="/stallen.html" class="${activePage === "stallen" ? "active" : ""}"><span class="icon" aria-hidden="true">📍</span><span>Ställen</span></a>
    `
    : "";

  sidebar.innerHTML = `
    <button class="sidebar-toggle" id="sidebar-toggle" title="Visa/dölj meny" aria-label="Visa/dölj meny">
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round">
        <path d="M4 6h14M4 11h14M4 16h14"/>
      </svg>
    </button>
    <nav>
      ${scheduleLink}
      <a href="/overblick.html" class="${activePage === "overview" ? "active" : ""}"><span class="icon" aria-hidden="true">📅</span><span>Översikt</span></a>
      ${productivityLink}
      ${allocationLinks}
      ${editorLinks}
      ${analyticsLink}
      ${adminLink}
    </nav>
    <div class="sidebar-footer">
      <div class="sidebar-utility">
        <button class="area-focus-toggle" id="area-focus-toggle" type="button" title="Områdesfokus" aria-label="Områdesfokus"></button>
        ${canUseAllocationTools(user) ? `
          <a href="/uppladdningar.html" class="database-toggle ${activePage === "allocationUploads" ? "active" : ""}" id="allocation-upload-link" title="Uppladdningar" aria-label="Uppladdningar">
            ${DATABASE_ICON}
            <span class="upload-arrow" aria-hidden="true">↑</span>
            <span class="upload-notice" id="allocation-upload-notice" hidden></span>
          </a>
        ` : ""}
        <button class="theme-toggle" id="theme-toggle" type="button"></button>
      </div>
      <div class="sidebar-bottom">
        <div class="avatar">${initials(user?.display_name || user?.username)}</div>
        <div>
          <div class="who">${user?.display_name || user?.username || ""}</div>
          <a href="#" class="logout" id="logout-link">Logga ut</a>
        </div>
      </div>
    </div>
  `;

  initAreaFocusToggle();
  initThemeToggle();
  updateAllocationUploadIndicator();
  document.body.classList.add("sidebar-hydrated");
  const allocationUploadLink = document.getElementById("allocation-upload-link");
  if (allocationUploadLink) {
    allocationUploadLink.addEventListener("click", () => clearAllocationUploadNotice());
  }

  const logout = document.getElementById("logout-link");
  if (logout) {
    logout.addEventListener("click", async (e) => {
      e.preventDefault();
      await api.post("/api/auth/logout");
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
  if (cachedUserCanRenderPage(cachedUser, options)) {
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
  if (options.requireSuperUser && !user.is_super_user) {
    queueToast("Sidan kräver Super User-behörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  if (options.requirePlanningView && !canViewPlanning(user)) {
    queueToast("Sidan kräver planerings- eller visningsbehörighet", "error");
    window.location.href = options.denyRedirect || "/overblick.html";
    return null;
  }
  if (options.requireEditor && !canEditPlanning(user)) {
    queueToast("Sidan kräver redigeringsbehörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  if (options.requireAllocationTools && !canUseAllocationTools(user)) {
    queueToast("Sidan kräver rollen Lagerkontorist eller Artikelplacerare", "error");
    window.location.href = "/index.html";
    return null;
  }
  if (options.requireAllocationProcess && !canUseAllocationProcess(user)) {
    queueToast("Bearbeta kräver Super User-behörighet", "error");
    window.location.href = options.denyRedirect || "/dela.html";
    return null;
  }
  cacheSidebarUser(user);
  renderSidebar(user, activePage);
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
window.allocationUploadActivity = {
  start: startAllocationUploadActivity,
  finish: finishAllocationUploadActivity,
  clear: clearAllocationUploadNotice,
};
window.readSelectedDate = readSelectedDate;
window.writeSelectedDate = writeSelectedDate;
window.clearSelectedDate = clearSelectedDate;

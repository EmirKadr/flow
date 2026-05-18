// Delade hjälpare: navbar, toast, auth-check.

const THEME_STORAGE_KEY = "bemanning-theme";
const SIDEBAR_USER_CACHE_KEY = "bemanning-sidebar-user";

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

function isAdminUser(user) {
  return user?.role === "admin" || user?.is_super_user;
}

function isReadOnlyUser(user) {
  return user?.role === "viewer" && !user?.is_super_user;
}

function canEditPlanning(user) {
  return !isReadOnlyUser(user);
}

function sidebarUserSnapshot(user) {
  if (!user) return null;
  return {
    username: user.username || "",
    display_name: user.display_name || "",
    role: user.role || "",
    is_super_user: Boolean(user.is_super_user),
    must_change_password: Boolean(user.must_change_password),
  };
}

function cacheSidebarUser(user) {
  try {
    const snapshot = sidebarUserSnapshot(user);
    if (snapshot) sessionStorage.setItem(SIDEBAR_USER_CACHE_KEY, JSON.stringify(snapshot));
  } catch (e) {}
}

function readCachedSidebarUser() {
  try {
    const raw = sessionStorage.getItem(SIDEBAR_USER_CACHE_KEY);
    if (!raw) return null;
    const user = JSON.parse(raw);
    return user?.username || user?.display_name ? user : null;
  } catch (e) {
    return null;
  }
}

function clearCachedSidebarUser() {
  try { sessionStorage.removeItem(SIDEBAR_USER_CACHE_KEY); } catch (e) {}
}

function cachedUserCanRenderPage(user, options = {}) {
  if (!user || user.must_change_password) return false;
  if (options.requireAdmin && user.role !== "admin" && !user.is_super_user) return false;
  if (options.requireSuperUser && !user.is_super_user) return false;
  if (options.requireEditor && !canEditPlanning(user)) return false;
  return true;
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
      <a href="/index.html" class="${activePage === "schedule" ? "active" : ""}"><span class="icon" aria-hidden="true">📋</span><span>Bemanning</span></a>
      <a href="/overblick.html" class="${activePage === "overview" ? "active" : ""}"><span class="icon" aria-hidden="true">📅</span><span>Översikt</span></a>
      ${productivityLink}
      ${editorLinks}
      ${analyticsLink}
      ${adminLink}
    </nav>
    <div class="sidebar-footer">
      <div class="sidebar-theme">
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

  initThemeToggle();

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
  if (options.requireAdmin && user.role !== "admin" && !user.is_super_user) {
    queueToast("Sidan kräver administratörsbehörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  if (options.requireSuperUser && !user.is_super_user) {
    queueToast("Sidan kräver Super User-behörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  if (options.requireEditor && !canEditPlanning(user)) {
    queueToast("Sidan kräver redigeringsbehörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  cacheSidebarUser(user);
  renderSidebar(user, activePage);
  flushQueuedToast();
  return user;
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
window.isReadOnlyUser = isReadOnlyUser;
window.canEditPlanning = canEditPlanning;
window.readSelectedDate = readSelectedDate;
window.writeSelectedDate = writeSelectedDate;
window.clearSelectedDate = clearSelectedDate;

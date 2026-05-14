// Delade hjälpare: navbar, toast, auth-check.

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

function renderSidebar(user, activePage) {
  let sidebar = document.querySelector(".sidebar");
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

    const app = document.createElement("div");
    app.className = "app";
    app.appendChild(sidebar);
    app.appendChild(main);
    body.insertBefore(app, body.firstChild);
  }

  const adminLink = (user?.role === "admin" || user?.role === "super_admin")
    ? `<a href="/anvandare.html" class="${activePage === "users" ? "active" : ""}"><span class="icon" aria-hidden="true">👤</span><span>Användare</span></a>`
    : "";
  const analyticsLink = user?.is_super_admin
    ? `<a href="/historik.html" class="${activePage === "analytics" ? "active" : ""}"><span class="icon" aria-hidden="true">📊</span><span>Historik</span></a>`
    : "";

  sidebar.innerHTML = `
    <button class="sidebar-toggle" id="sidebar-toggle" title="Visa/dölj meny" aria-label="Visa/dölj meny">
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round">
        <path d="M4 6h14M4 11h14M4 16h14"/>
      </svg>
    </button>
    <div class="brand">
      <div class="brand-dot">B</div>
      <div>
        <div class="brand-name">Bemanning</div>
        <div class="brand-sub">Stigamo</div>
      </div>
    </div>
    <nav>
      <a href="/index.html" class="${activePage === "schedule" ? "active" : ""}"><span class="icon" aria-hidden="true">📋</span><span>Bemanning</span></a>
      <a href="/overblick.html" class="${activePage === "overview" ? "active" : ""}"><span class="icon" aria-hidden="true">📅</span><span>Översikt</span></a>
      <a href="/personer.html" class="${activePage === "persons" ? "active" : ""}"><span class="icon" aria-hidden="true">👥</span><span>Personer</span></a>
      <a href="/stallen.html" class="${activePage === "stallen" ? "active" : ""}"><span class="icon" aria-hidden="true">📍</span><span>Ställen</span></a>
      ${analyticsLink}
      ${adminLink}
    </nav>
    <div class="sidebar-bottom">
      <div class="avatar">${initials(user?.display_name || user?.username)}</div>
      <div>
        <div class="who">${user?.display_name || user?.username || ""}</div>
        <a href="#" class="logout" id="logout-link">Logga ut</a>
      </div>
    </div>
  `;

  const logout = document.getElementById("logout-link");
  if (logout) {
    logout.addEventListener("click", async (e) => {
      e.preventDefault();
      await api.post("/api/auth/logout");
      window.location.href = "/login.html";
    });
  }

  // Toggle collapsed state – hamburger fortsätter rotera åt samma håll vid varje klick
  const toggleBtn = document.getElementById("sidebar-toggle");
  const app = document.querySelector(".app");
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
}

// Bakåtkompatibilitet
function renderTopbar(user, activePage) {
  renderSidebar(user, activePage);
}

async function initPage(activePage, options = {}) {
  const user = await loadCurrentUser();
  if (!user) {
    window.location.href = "/login.html";
    return null;
  }
  if (options.requireAdmin && user.role !== "admin" && user.role !== "super_admin") {
    queueToast("Sidan kräver administratörsbehörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  if (options.requireSuperAdmin && !user.is_super_admin) {
    queueToast("Sidan kräver super admin-behörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  renderSidebar(user, activePage);
  flushQueuedToast();
  return user;
}

window.showToast = showToast;
window.initPage = initPage;
window.queueToast = queueToast;

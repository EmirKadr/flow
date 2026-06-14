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
  if (PERSONAL_VIEW_IDS.has(normalizedViewId)) {
    return userRoles(user).includes("person") ? "view" : "none";
  }
  let best = "none";
  const roles = userRoles(user);
  if (user?.is_demo && !roles.includes("demo")) roles.push("demo");
  for (const role of roles) {
    let level = access[role]?.[normalizedViewId];
    level = level || "none";
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
    || canViewPage(user, "allocationProcessMatrix")
    || canViewPage(user, "allocationSettings")
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
      id: "mySchedule",
      label: "Mitt schema",
      href: "/mitt-schema.html",
      iconHtml: MY_SCHEDULE_ICON,
      visible: canViewPage(user, "mySchedule"),
      active: activePage === "mySchedule",
    },
    {
      id: "myProductivity",
      label: "Min produktivitet",
      href: "/min-produktivitet.html",
      iconHtml: MY_PRODUCTIVITY_ICON,
      visible: canViewPage(user, "myProductivity"),
      active: activePage === "myProductivity",
    },
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
      id: "allocationSettings",
      label: "Inställningar",
      href: "/installningar.html",
      icon: "⚙",
      visible: canViewPage(user, "allocationSettings") || canViewPage(user, "staffingSettings") || canViewPage(user, "allocationProcessMatrix"),
      active: activePage === "allocationSettings",
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
      id: "meta",
      label: "Meta",
      href: "/meta.html",
      icon: "M",
      visible: Boolean(user?.is_super_user),
      active: activePage === "meta",
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

function isPersonOnlyAccount(user) {
  const roles = userRoles(user);
  return !user?.is_super_user && roles.length === 1 && roles[0] === "person";
}

function preferredPostAuthPage(user) {
  if (isPersonOnlyAccount(user) && canViewPage(user, "mySchedule")) return "/mitt-schema.html";
  if (canViewPage(user, "schedule")) return "/index.html";
  return firstAccessiblePageHref(user, "") || "/index.html";
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
  return preferredPostAuthPage(user);
}


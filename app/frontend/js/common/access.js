// @ts-check
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

function hasCachedRoleViewAccess() {
  try {
    return Boolean(localStorage.getItem(ROLE_VIEW_ACCESS_CACHE_KEY));
  } catch (e) {
    return false;
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
    || canViewPage(user, "productivityFinanceSettings")
  );
}

function canUseAllocationProcess(user) {
  return canViewPage(user, "allocationProcess");
}

const SIDEBAR_TOOLS_TAB_VIEW_IDS = ["allocationSplit", "labelEditor", "removeDuplicates", "mcp", "dataFetch", "analytics", "meta", "archiveStatus", "bugReports"];
const SIDEBAR_STAFFING_TAB_VIEW_IDS = [
  "schedule",
  "overview",
  "productivity",
  "sankeyInbound",
  "activities",
  "persons",
  "users",
  "businesses",
  "mySchedule",
  "myProductivity",
];
const SIDEBAR_SETTINGS_TAB_VIEW_IDS = [
  "allocationMapSettings",
  "allocationProcessMatrix",
  "staffingSettings",
  "productivityFinanceSettings",
];
const SIDEBAR_VIEW_HREFS = {
  allocationSplit: "/dela.html",
  labelEditor: "/label-editor.html",
  removeDuplicates: "/dubbletter.html",
  mcp: "/mcp.html",
  dataFetch: "/hamta-data.html",
  analytics: "/historik.html",
  meta: "/meta.html",
  archiveStatus: "/arkiv-status.html",
  bugReports: "/bug-rapporter.html",
  schedule: "/index.html",
  overview: "/overblick.html",
  productivity: "/produktivitet.html",
  sankeyInbound: "/sankey-inbound.html",
  activities: "/aktiviteter.html",
  persons: "/personer.html",
  users: "/anvandare.html",
  businesses: "/verksamheter.html",
  mySchedule: "/mitt-schema.html",
  myProductivity: "/min-produktivitet.html",
  allocationMapSettings: "/installningar.html?tab=map",
  allocationProcessMatrix: "/installningar.html?tab=process-matrix",
  staffingSettings: "/installningar.html?tab=staffing",
  productivityFinanceSettings: "/installningar.html?tab=productivity-finance",
};

function sidebarDefaultLayout() {
  return SIDEBAR_DEFAULT_LAYOUT.map((item) => ({
    id: item.id,
    heading: item.heading || "",
    parentId: item.parentId || null,
  }));
}

function sidebarTabTargetVisible(user, viewId) {
  if (viewId === "meta" || viewId === "businesses" || viewId === "archiveStatus") return Boolean(user?.is_super_user);
  return canViewPage(user, viewId);
}

function sidebarGroupVisible(user, viewIds) {
  return viewIds.some((viewId) => sidebarTabTargetVisible(user, viewId));
}

function sidebarFirstGroupHref(user, viewIds) {
  const viewId = viewIds.find((candidate) => sidebarTabTargetVisible(user, candidate));
  return viewId ? SIDEBAR_VIEW_HREFS[viewId] || "#" : "#";
}

function sidebarGroupActive(activePage, groupId, viewIds) {
  return activePage === groupId || viewIds.includes(activePage);
}

function sidebarSettingsTabVisible(user, viewId) {
  const permissionViewId = viewId === "allocationMapSettings" ? "allocationSettings" : viewId;
  return canViewPage(user, permissionViewId);
}

function sidebarSettingsHref(user) {
  const viewId = SIDEBAR_SETTINGS_TAB_VIEW_IDS.find((candidate) => sidebarSettingsTabVisible(user, candidate));
  return viewId ? SIDEBAR_VIEW_HREFS[viewId] || "/installningar.html" : "/installningar.html";
}

function sidebarToolsHref(user) {
  return sidebarFirstGroupHref(user, SIDEBAR_TOOLS_TAB_VIEW_IDS);
}

function sidebarStaffingHref(user) {
  return sidebarFirstGroupHref(user, SIDEBAR_STAFFING_TAB_VIEW_IDS);
}

function sidebarPageDefinitions(user, activePage) {
  const toolsVisible = sidebarGroupVisible(user, SIDEBAR_TOOLS_TAB_VIEW_IDS);
  const toolsActive = sidebarGroupActive(activePage, "tools", SIDEBAR_TOOLS_TAB_VIEW_IDS);
  const staffingVisible = sidebarGroupVisible(user, SIDEBAR_STAFFING_TAB_VIEW_IDS);
  const staffingActive = sidebarGroupActive(activePage, "staffing", SIDEBAR_STAFFING_TAB_VIEW_IDS);
  return [
    {
      id: "staffing",
      label: "Bemanning",
      href: sidebarStaffingHref(user),
      icon: "📋",
      visible: staffingVisible,
      active: staffingActive,
      contextMenuViewIds: SIDEBAR_STAFFING_TAB_VIEW_IDS,
    },
    {
      id: "mySchedule",
      label: "Mitt schema",
      href: "/mitt-schema.html",
      iconHtml: MY_SCHEDULE_ICON,
      visible: canViewPage(user, "mySchedule"),
      active: activePage === "mySchedule",
      sidebar: false,
    },
    {
      id: "myProductivity",
      label: "Min produktivitet",
      href: "/min-produktivitet.html",
      iconHtml: MY_PRODUCTIVITY_ICON,
      visible: canViewPage(user, "myProductivity"),
      active: activePage === "myProductivity",
      sidebar: false,
    },
    {
      id: "schedule",
      label: "Bemanning",
      href: "/index.html",
      icon: "📋",
      visible: canViewPage(user, "schedule"),
      active: activePage === "schedule",
      sidebar: false,
    },
    {
      id: "overview",
      label: "Översikt",
      href: "/overblick.html",
      icon: "🗓️",
      visible: canViewPage(user, "overview"),
      active: activePage === "overview",
      sidebar: false,
    },
    {
      id: "productivity",
      label: "Produktivitet",
      href: "/produktivitet.html",
      icon: "📈",
      visible: canViewPage(user, "productivity"),
      active: activePage === "productivity",
      sidebar: false,
    },
    {
      id: "sankeyInbound",
      label: "Sankey",
      href: "/sankey-inbound.html",
      icon: "S",
      visible: canViewPage(user, "sankeyInbound"),
      active: activePage === "sankeyInbound",
      sidebar: false,
    },
    {
      id: "dataFetch",
      label: "Hämta data",
      href: "/hamta-data.html",
      icon: "⇩",
      visible: canViewPage(user, "dataFetch"),
      active: activePage === "dataFetch",
      sidebar: false,
    },
    {
      id: "mcp",
      label: "MCP",
      href: "/mcp.html",
      iconHtml: MCP_ICON,
      visible: canViewPage(user, "mcp"),
      active: activePage === "mcp",
      sidebar: false,
    },
    {
      id: "removeDuplicates",
      label: "Dubbletter",
      href: "/dubbletter.html",
      icon: "⧉",
      visible: canViewPage(user, "removeDuplicates"),
      active: activePage === "removeDuplicates",
      sidebar: false,
    },
    {
      id: "tools",
      label: "Verktyg",
      href: sidebarToolsHref(user),
      iconHtml: TOOLS_ICON,
      visible: toolsVisible,
      active: toolsActive,
      contextMenuViewIds: SIDEBAR_TOOLS_TAB_VIEW_IDS,
    },
    {
      id: "labelEditor",
      label: "Etiketter",
      href: "/label-editor.html",
      iconHtml: LABEL_EDITOR_ICON,
      visible: canViewPage(user, "labelEditor"),
      active: activePage === "labelEditor",
      sidebar: false,
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
      href: sidebarSettingsHref(user),
      icon: "⚙",
      visible: canViewPage(user, "allocationSettings")
        || canViewPage(user, "staffingSettings")
        || canViewPage(user, "allocationProcessMatrix")
        || canViewPage(user, "productivityFinanceSettings"),
      active: activePage === "allocationSettings",
      contextMenuViewIds: SIDEBAR_SETTINGS_TAB_VIEW_IDS,
    },
    {
      id: "allocationMapSettings",
      label: "Ytkarta",
      href: SIDEBAR_VIEW_HREFS.allocationMapSettings,
      icon: "⚙",
      visible: canViewPage(user, "allocationSettings"),
      active: false,
      sidebar: false,
    },
    {
      id: "allocationProcessMatrix",
      label: "Bearbeta",
      href: SIDEBAR_VIEW_HREFS.allocationProcessMatrix,
      icon: "⚙",
      visible: canViewPage(user, "allocationProcessMatrix"),
      active: false,
      sidebar: false,
    },
    {
      id: "staffingSettings",
      label: "Bemanning",
      href: SIDEBAR_VIEW_HREFS.staffingSettings,
      icon: "⚙",
      visible: canViewPage(user, "staffingSettings"),
      active: false,
      sidebar: false,
    },
    {
      id: "productivityFinanceSettings",
      label: "Intäkt/utgift",
      href: SIDEBAR_VIEW_HREFS.productivityFinanceSettings,
      icon: "⚙",
      visible: canViewPage(user, "productivityFinanceSettings"),
      active: false,
      sidebar: false,
    },
    {
      id: "allocationSplit",
      label: "Dela",
      href: "/dela.html",
      icon: "✂",
      visible: canViewPage(user, "allocationSplit"),
      active: activePage === "allocationSplit",
      sidebar: false,
    },
    {
      id: "persons",
      label: "Personer",
      href: "/personer.html",
      icon: "👥",
      visible: canViewPage(user, "persons"),
      active: activePage === "persons",
      sidebar: false,
    },
    {
      id: "activities",
      label: "Aktiviteter",
      href: "/aktiviteter.html",
      icon: "📍",
      visible: canViewPage(user, "activities"),
      active: activePage === "activities",
      sidebar: false,
    },
    {
      id: "analytics",
      label: "Historik",
      href: "/historik.html",
      icon: "📊",
      visible: canViewPage(user, "analytics"),
      active: activePage === "analytics",
      sidebar: false,
    },
    {
      id: "meta",
      label: "Meta",
      href: "/meta.html",
      icon: "M",
      visible: Boolean(user?.is_super_user),
      active: activePage === "meta",
      sidebar: false,
    },
    {
      id: "archiveStatus",
      label: "Arkivstatus",
      href: "/arkiv-status.html",
      icon: "🗄",
      visible: Boolean(user?.is_super_user),
      active: activePage === "archiveStatus",
      sidebar: false,
    },
    {
      id: "bugReports",
      label: "Buggrapporter",
      href: "/bug-rapporter.html",
      icon: "🐞",
      visible: canViewPage(user, "bugReports"),
      active: activePage === "bugReports",
      sidebar: false,
    },
    {
      id: "users",
      label: "Användare",
      href: "/anvandare.html",
      icon: "👤",
      visible: canViewPage(user, "users"),
      active: activePage === "users",
      sidebar: false,
    },
    {
      id: "businesses",
      label: "Verksamheter",
      href: "/verksamheter.html",
      icon: "⌘",
      visible: Boolean(user?.is_super_user),
      active: activePage === "businesses",
      sidebar: false,
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
    const response = await api.get("/api/settings/sidebar", { cacheTtlMs: 5 * 60 * 1000 });
    const next = cacheSidebarLayout(response?.items || []);
    if (sidebarLayoutSignature(next) !== before) renderSidebar(user, activePage);
  } catch (e) {
    // Menyn har alltid en lokal standardlayout, så ett inställningsfel ska inte blockera sidan.
  }
}

async function refreshRoleViewAccess(user, activePage) {
  const before = JSON.stringify(roleViewAccessForRender());
  try {
    const response = await api.get("/api/settings/role-access", { cacheTtlMs: 5 * 60 * 1000 });
    const next = cacheRoleViewAccess(response?.access || {});
    if (JSON.stringify(next) !== before) renderSidebar(user, activePage);
  } catch (e) {
    // Standardbehörigheter räcker för att appen ska kunna fortsätta.
  }
}

async function refreshRoleViewAccessForRouting() {
  try {
    const response = await api.get("/api/settings/role-access", { cacheTtlMs: 5 * 60 * 1000 });
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
  const visiblePage = pages.find((page) => page.visible && page.sidebar !== false && page.href && page.href !== currentPath);
  return visiblePage?.href || "";
}

function syncTabGroup(user, tabs, navs, datasetKey) {
  if (!tabs.length) return;
  const pages = sidebarPageDefinitions(user, window.flowActivePage || document.body?.dataset.activePage || "");
  const pageById = Object.fromEntries(pages.map((page) => [page.id, page]));
  let visibleCount = 0;
  tabs.forEach((tab) => {
    const viewId = normalizeViewId(tab.dataset[datasetKey]);
    const visible = Boolean(pageById[viewId]?.visible);
    tab.hidden = !visible;
    if (visible) visibleCount += 1;
  });
  navs.forEach((nav) => {
    nav.hidden = visibleCount <= 1;
  });
}

function syncViewTabs(user) {
  syncTabGroup(
    user,
    Array.from(document.querySelectorAll("[data-tools-tab-view]")),
    Array.from(document.querySelectorAll(".tools-tabs")),
    "toolsTabView",
  );
  syncTabGroup(
    user,
    Array.from(document.querySelectorAll("[data-staffing-tab-view]")),
    Array.from(document.querySelectorAll(".staffing-tabs")),
    "staffingTabView",
  );
}

function syncToolsTabs(user) {
  syncViewTabs(user);
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


// Delade hjälpare: navbar, toast, auth-check.

const THEME_STORAGE_KEY = "bemanning-theme";
const SIDEBAR_USER_CACHE_KEY = "bemanning-sidebar-user";
const SIDEBAR_LAYOUT_CACHE_KEY = "bemanning-sidebar-layout";
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
  { id: "allocationUploads" },
  { id: "allocationProcess" },
  { id: "allocationSplit" },
  { id: "allocationTrace" },
  { id: "persons" },
  { id: "stallen" },
  { id: "analytics" },
  { id: "users" },
];

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

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
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
      visible: canViewPlanning(user),
      active: activePage === "schedule",
    },
    {
      id: "overview",
      label: "Översikt",
      href: "/overblick.html",
      icon: "🗓️",
      visible: true,
      active: activePage === "overview",
    },
    {
      id: "productivity",
      label: "Produktivitet",
      href: "/produktivitet.html",
      icon: "📈",
      visible: Boolean(user?.is_super_user),
      active: activePage === "productivity",
    },
    {
      id: "allocationUploads",
      label: "Uppladdningar",
      href: "/uppladdningar.html",
      iconHtml: DATABASE_ICON,
      visible: canUseAllocationTools(user),
      active: activePage === "allocationUploads",
      linkId: "allocation-upload-link",
      className: "sidebar-upload-link",
      trailingHtml: `
        <span class="upload-arrow" aria-hidden="true">↑</span>
        <span class="upload-notice" id="allocation-upload-notice" hidden></span>
      `,
    },
    {
      id: "allocationProcess",
      label: "Bearbeta",
      href: "/bearbeta.html",
      icon: "🧮",
      visible: canUseAllocationProcess(user),
      active: activePage === "allocationProcess",
    },
    {
      id: "allocationSplit",
      label: "Dela",
      href: "/dela.html",
      icon: "✂",
      visible: canUseAllocationTools(user),
      active: activePage === "allocationSplit",
    },
    {
      id: "allocationTrace",
      label: "Härleda",
      href: "/harleda.html",
      icon: "⌕",
      visible: canUseAllocationTools(user),
      active: activePage === "allocationTrace",
    },
    {
      id: "persons",
      label: "Personer",
      href: "/personer.html",
      icon: "👥",
      visible: canEditPlanning(user),
      active: activePage === "persons",
    },
    {
      id: "stallen",
      label: "Ställen",
      href: "/stallen.html",
      icon: "📍",
      visible: canEditPlanning(user),
      active: activePage === "stallen",
    },
    {
      id: "analytics",
      label: "Historik",
      href: "/historik.html",
      icon: "📊",
      visible: Boolean(user?.is_super_user),
      active: activePage === "analytics",
    },
    {
      id: "users",
      label: "Användare",
      href: "/anvandare.html",
      icon: "👤",
      visible: isAdminUser(user),
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
    const id = String(item?.id || "").trim();
    if (!knownIds.has(id) || seen.has(id)) continue;
    seen.add(id);
    const parentId = String(item.parent_id || item.parentId || "").trim();
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

  const navHtml = renderSidebarNav(user, activePage);
  const editButton = user?.is_super_user
    ? `
      <button class="sidebar-edit" id="sidebar-edit" type="button" title="Redigera meny" aria-label="Redigera meny">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 20h9"></path>
          <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z"></path>
        </svg>
      </button>
    `
    : "";

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
  const sidebarEdit = document.getElementById("sidebar-edit");
  if (sidebarEdit) {
    sidebarEdit.addEventListener("click", () => openSidebarEditor(user, activePage));
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

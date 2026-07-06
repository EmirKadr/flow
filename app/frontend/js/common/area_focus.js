// @ts-check
function areaFocusOptions() {
  return Array.isArray(dynamicAreaFocusOptions) ? dynamicAreaFocusOptions : [];
}

function areaFocusValueForArea(area) {
  const id = Number(area?.id);
  return Number.isInteger(id) ? `AREA:${id}` : "";
}

function isAllAreasMarker(area) {
  return String(area?.code || "").trim().toUpperCase() === "ANNAT";
}

function hasAllAreasMarker(areas = []) {
  return (areas || []).some((area) => area?.is_active !== false && isAllAreasMarker(area));
}

function buildAreaFocusOptions(areas = [], user = null) {
  const activeAreas = (areas || [])
    .filter((area) => area?.is_active !== false);
  const focusBusinessId = user?.is_super_user ? businessFocusBusinessId() : null;
  const visibleAreas = activeAreas
    .filter((area) => !isAllAreasMarker(area))
    .filter((area) => focusBusinessId == null || Number(area?.business_id) === focusBusinessId)
    .slice()
    .sort((a, b) => {
      const sortDiff = (Number(a?.sort_order) || 0) - (Number(b?.sort_order) || 0);
      if (sortDiff !== 0) return sortDiff;
      return String(a?.name || a?.code || "").localeCompare(String(b?.name || b?.code || ""), "sv");
    });
  const options = visibleAreas.map((area) => ({
    value: areaFocusValueForArea(area),
    label: String(area?.code || area?.name || "").trim(),
    title: String(area?.name || area?.code || "").trim(),
    code: String(area?.code || "").trim().toUpperCase(),
    areaId: Number(area?.id),
    businessId: Number.isInteger(Number(area?.business_id)) ? Number(area.business_id) : null,
  })).filter((option) => option.value && option.label);
  if (user?.is_super_user || hasAllAreasMarker(activeAreas)) {
    options.push({ ...AREA_FOCUS_ALL_OPTION });
  }
  return options;
}

function setAreaFocusAreas(areas = [], user = null) {
  areaFocusAreasCache = Array.isArray(areas) ? areas : [];
  if (user !== null) areaFocusUserCache = user;
  dynamicAreaFocusOptions = buildAreaFocusOptions(areas, areaFocusUserCache);
  areaFocusLoadState = "ready";
  const current = readAreaFocus();
  try {
    if (current) localStorage.setItem(AREA_FOCUS_STORAGE_KEY, current);
    else localStorage.removeItem(AREA_FOCUS_STORAGE_KEY);
  } catch (e) {}
  updateAreaFocusToggle(current);
  return dynamicAreaFocusOptions;
}

function loadAreaFocusAreas(user = null) {
  if (areaFocusAreasRequest) return areaFocusAreasRequest;
  areaFocusLoadState = "loading";
  dynamicAreaFocusOptions = [];
  updateAreaFocusToggle();
  areaFocusAreasRequest = api.get("/api/areas")
    .then((areas) => setAreaFocusAreas(areas, user))
    .catch((error) => {
      areaFocusLoadState = "error";
      dynamicAreaFocusOptions = [];
      updateAreaFocusToggle();
      throw error;
    })
    .finally(() => {
      areaFocusAreasRequest = null;
    });
  return areaFocusAreasRequest;
}

function areaFocusMenuOptions() {
  return Array.isArray(dynamicAreaFocusOptions) ? dynamicAreaFocusOptions : [];
}

function normalizeAreaFocus(value) {
  const normalized = String(value || "").trim().toUpperCase();
  const options = areaFocusOptions();
  if (!options.length) return "";
  const exact = options.find((option) => String(option.value || "").toUpperCase() === normalized);
  if (exact) return exact.value;
  const byCode = options.find((option) => option.code && option.code === normalized);
  if (byCode) return byCode.value;
  const allOption = options.find((option) => option.value === "ALLT");
  return allOption ? allOption.value : (options[0]?.value || "");
}

function areaFocusOption(value) {
  const normalized = normalizeAreaFocus(value);
  const options = areaFocusOptions();
  return options.find((option) => option.value === normalized) || options[0] || null;
}

function nextAreaFocus(value = readAreaFocus()) {
  const normalized = normalizeAreaFocus(value);
  const options = areaFocusOptions();
  if (!options.length) return "";
  const index = options.findIndex((option) => option.value === normalized);
  return options[(Math.max(0, index) + 1) % options.length].value;
}

function readAreaFocus() {
  try {
    return normalizeAreaFocus(localStorage.getItem(AREA_FOCUS_STORAGE_KEY));
  } catch (e) {
    return normalizeAreaFocus("");
  }
}

function writeAreaFocus(value) {
  const normalized = normalizeAreaFocus(value);
  if (!normalized) {
    updateAreaFocusToggle("");
    return "";
  }
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
  if (!focus || focus === "ALLT") return null;
  const visibleAreas = Array.isArray(areas)
    ? areas.filter((area) => area?.is_active !== false)
    : null;
  const option = areaFocusOption(focus);
  if (option?.areaId != null) {
    const areaId = Number(option.areaId);
    if (!visibleAreas || visibleAreas.some((area) => Number(area?.id) === areaId)) {
      return areaId;
    }
    writeAreaFocus(normalizeAreaFocus(""));
    return null;
  }
  const areaIdMatch = String(focus || "").match(/^AREA:(\d+)$/i);
  if (areaIdMatch) {
    const areaId = Number(areaIdMatch[1]);
    if (!visibleAreas || visibleAreas.some((area) => Number(area?.id) === areaId)) {
      return areaId;
    }
    writeAreaFocus(normalizeAreaFocus(""));
    return null;
  }
  const area = findAreaByCode(visibleAreas || areas, option?.code || focus);
  if (area) return Number(area.id);
  if (visibleAreas) writeAreaFocus(normalizeAreaFocus(""));
  return null;
}

function areaFocusAreaId(areas) {
  return preferredAreaIdFromFocus(areas);
}

function areaFocusBusinessId(value = readAreaFocus()) {
  const focus = normalizeAreaFocus(value);
  if (focus && focus !== "ALLT") {
    const businessId = Number(areaFocusOption(focus)?.businessId);
    if (Number.isInteger(businessId) && businessId > 0) return businessId;
  }
  // Super User med valt verksamhetsfokus: låt verksamheten gälla även när
  // områdesfokus är ∞ eller saknar verksamhetskoppling.
  if (areaFocusUserCache?.is_super_user) return businessFocusBusinessId();
  return null;
}

function areaFocusName(areas, value = readAreaFocus()) {
  const focus = normalizeAreaFocus(value);
  if (focus === "ALLT") return "Alla områden";
  if (!focus) {
    if (areaFocusLoadState === "error") return "Områden kunde inte läsas";
    if (areaFocusLoadState === "loading") return "Läser områden";
    return "Inga områden";
  }
  const option = areaFocusOption(focus);
  if (option?.title) return option.title;
  const area = findAreaByCode(areas || [], option?.code || focus);
  return area?.name || focus;
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
  const toggle = /** @type {HTMLButtonElement | null} */ (document.getElementById("area-focus-toggle"));
  if (!toggle) return;
  const normalized = normalizeAreaFocus(value);
  const option = areaFocusOption(normalized);
  toggle.dataset.value = normalized;
  const disabled = !option;
  toggle.textContent = option?.label || (areaFocusLoadState === "loading" ? "..." : "!");
  toggle.classList.toggle("infinity", normalized === "ALLT");
  toggle.classList.toggle("is-error", areaFocusLoadState === "error" && !option);
  toggle.classList.toggle("is-disabled", disabled);
  toggle.title = `Områdesfokus: ${areaFocusName([], normalized)}`;
  toggle.setAttribute("aria-label", toggle.title);
  toggle.setAttribute("aria-pressed", normalized === "ALLT" || disabled ? "false" : "true");
  toggle.disabled = disabled;
}

function closeAreaFocusMenu() {
  document.querySelector(".area-focus-menu")?.remove();
  document.removeEventListener("click", handleAreaFocusMenuDocumentClick);
  document.removeEventListener("keydown", handleAreaFocusMenuKeydown);
  window.removeEventListener("resize", closeAreaFocusMenu);
  window.removeEventListener("scroll", handleAreaFocusMenuWindowScroll, true);
}

function handleAreaFocusMenuKeydown(event) {
  if (event.key === "Escape") closeAreaFocusMenu();
}

function handleAreaFocusMenuDocumentClick(event) {
  const menu = document.querySelector(".area-focus-menu");
  const target = event.target;
  if (menu && target?.nodeType && menu.contains(target)) return;
  closeAreaFocusMenu();
}

function handleAreaFocusMenuWindowScroll(event) {
  const menu = document.querySelector(".area-focus-menu");
  const target = event.target;
  if (menu && target?.nodeType && menu.contains(target)) return;
  closeAreaFocusMenu();
}

function positionAreaFocusMenu(menu, event, anchor) {
  const rect = anchor?.getBoundingClientRect?.();
  const fallbackX = rect ? rect.right + 8 : 8;
  const fallbackY = rect ? rect.top : 8;
  const x = Number(event?.clientX) || fallbackX;
  const y = Number(event?.clientY) || fallbackY;
  const left = Math.min(x, window.innerWidth - menu.offsetWidth - 8);
  const top = Math.min(y, window.innerHeight - menu.offsetHeight - 8);
  menu.style.left = `${Math.max(8, left)}px`;
  menu.style.top = `${Math.max(8, top)}px`;
}

function renderAreaFocusMenuItems(menu, options = [], state = "ready") {
  menu.textContent = "";
  if (state === "loading") {
    const item = document.createElement("div");
    item.className = "area-focus-menu-empty";
    item.textContent = "Läser områden...";
    menu.appendChild(item);
    return;
  }
  if (state === "error") {
    const item = document.createElement("div");
    item.className = "area-focus-menu-empty error";
    item.textContent = "Kunde inte läsa områden.";
    menu.appendChild(item);
    return;
  }
  if (!options.length) {
    const item = document.createElement("div");
    item.className = "area-focus-menu-empty";
    item.textContent = "Inga områden";
    menu.appendChild(item);
    return;
  }

  const current = readAreaFocus();
  options.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("role", "menuitemradio");
    button.setAttribute("aria-checked", option.value === current ? "true" : "false");
    button.dataset.value = option.value;

    const code = document.createElement("span");
    code.className = "area-focus-menu-code";
    code.textContent = option.value === "ALLT" ? "∞" : option.label;
    button.appendChild(code);

    const name = document.createElement("span");
    name.className = "area-focus-menu-name";
    name.textContent = option.value === "ALLT" ? "Alla områden" : (option.title || option.label);
    button.appendChild(name);

    button.addEventListener("click", () => {
      writeAreaFocus(option.value);
      closeAreaFocusMenu();
    });
    menu.appendChild(button);
  });
}

function openAreaFocusMenu(event, user = null) {
  event.preventDefault();
  event.stopPropagation();
  const anchor = event.currentTarget || document.getElementById("area-focus-toggle");
  closeAreaFocusMenu();
  closeBusinessFocusMenu();

  const menu = document.createElement("div");
  menu.className = "area-focus-menu";
  menu.setAttribute("role", "menu");
  menu.setAttribute("aria-label", "Välj områdesfokus");
  menu.addEventListener("click", (event) => event.stopPropagation());
  menu.addEventListener("pointerdown", (event) => event.stopPropagation());
  menu.addEventListener("wheel", (event) => event.stopPropagation(), { passive: true });
  document.body.appendChild(menu);

  const options = areaFocusMenuOptions();
  renderAreaFocusMenuItems(menu, options, options.length ? "ready" : "loading");
  positionAreaFocusMenu(menu, event, anchor);

  if (!options.length) {
    loadAreaFocusAreas(user)
      .then((loadedOptions) => {
        if (!menu.isConnected) return;
        renderAreaFocusMenuItems(menu, loadedOptions || areaFocusMenuOptions());
        positionAreaFocusMenu(menu, event, anchor);
      })
      .catch(() => {
        if (!menu.isConnected) return;
        renderAreaFocusMenuItems(menu, [], "error");
        positionAreaFocusMenu(menu, event, anchor);
      });
  }

  setTimeout(() => {
    document.addEventListener("click", handleAreaFocusMenuDocumentClick);
    document.addEventListener("keydown", handleAreaFocusMenuKeydown);
    window.addEventListener("resize", closeAreaFocusMenu);
    window.addEventListener("scroll", handleAreaFocusMenuWindowScroll, true);
  });
}

function initAreaFocusToggle(user = null) {
  const toggle = document.getElementById("area-focus-toggle");
  if (!toggle) return;
  updateAreaFocusToggle(readAreaFocus());
  loadAreaFocusAreas(user).catch(() => {});
  toggle.setAttribute("aria-haspopup", "menu");
  toggle.addEventListener("click", () => writeAreaFocus(nextAreaFocus()));
  toggle.addEventListener("contextmenu", (event) => openAreaFocusMenu(event, user));
  toggle.addEventListener("keydown", (event) => {
    if (event.key !== "ContextMenu" && !(event.shiftKey && event.key === "F10")) return;
    openAreaFocusMenu(event, user);
  });
}

// --- Verksamhetsfokus (endast Super User) ---
// Egen toggle bredvid områdesfokus som filtrerar vilka områden som visas i
// områdestogglen. Vanliga användare är redan verksamhetsscopeade av backend.

function businessFocusOptions() {
  return Array.isArray(dynamicBusinessFocusOptions) ? dynamicBusinessFocusOptions : [];
}

function buildBusinessFocusOptions(businesses = []) {
  const options = (businesses || [])
    .filter((business) => business?.is_active !== false)
    .slice()
    .sort((a, b) => {
      const sortDiff = (Number(a?.sort_order) || 0) - (Number(b?.sort_order) || 0);
      if (sortDiff !== 0) return sortDiff;
      return String(a?.name || a?.code || "").localeCompare(String(b?.name || b?.code || ""), "sv");
    })
    .map((business) => {
      const id = Number(business?.id);
      return {
        value: Number.isInteger(id) && id > 0 ? `BIZ:${id}` : "",
        label: String(business?.code || business?.name || "").trim().toUpperCase(),
        title: String(business?.name || business?.code || "").trim(),
        businessId: Number.isInteger(id) && id > 0 ? id : null,
      };
    })
    .filter((option) => option.value && option.label);
  options.push({ ...BUSINESS_FOCUS_ALL_OPTION });
  return options;
}

function setBusinessFocusBusinesses(businesses = []) {
  dynamicBusinessFocusOptions = buildBusinessFocusOptions(businesses);
  businessFocusLoadState = "ready";
  const current = readBusinessFocus();
  try {
    if (current) localStorage.setItem(BUSINESS_FOCUS_STORAGE_KEY, current);
    else localStorage.removeItem(BUSINESS_FOCUS_STORAGE_KEY);
  } catch (e) {}
  updateBusinessFocusToggle(current);
  refreshAreaFocusOptionsForBusinessFocus();
  return dynamicBusinessFocusOptions;
}

function loadBusinessFocusBusinesses() {
  if (businessFocusBusinessesRequest) return businessFocusBusinessesRequest;
  businessFocusLoadState = "loading";
  dynamicBusinessFocusOptions = [];
  updateBusinessFocusToggle();
  businessFocusBusinessesRequest = api.get("/api/businesses")
    .then((businesses) => setBusinessFocusBusinesses(businesses))
    .catch((error) => {
      businessFocusLoadState = "error";
      dynamicBusinessFocusOptions = [];
      updateBusinessFocusToggle();
      throw error;
    })
    .finally(() => {
      businessFocusBusinessesRequest = null;
    });
  return businessFocusBusinessesRequest;
}

function normalizeBusinessFocus(value) {
  const normalized = String(value || "").trim().toUpperCase();
  const options = businessFocusOptions();
  if (!options.length) return "";
  const exact = options.find((option) => String(option.value || "").toUpperCase() === normalized);
  if (exact) return exact.value;
  const byLabel = options.find((option) => option.label && option.label === normalized);
  if (byLabel) return byLabel.value;
  const allOption = options.find((option) => option.value === "ALLT");
  return allOption ? allOption.value : (options[0]?.value || "");
}

function businessFocusOption(value) {
  const normalized = normalizeBusinessFocus(value);
  const options = businessFocusOptions();
  return options.find((option) => option.value === normalized) || null;
}

function nextBusinessFocus(value = readBusinessFocus()) {
  const normalized = normalizeBusinessFocus(value);
  const options = businessFocusOptions();
  if (!options.length) return "";
  const index = options.findIndex((option) => option.value === normalized);
  return options[(Math.max(0, index) + 1) % options.length].value;
}

function readBusinessFocus() {
  try {
    return normalizeBusinessFocus(localStorage.getItem(BUSINESS_FOCUS_STORAGE_KEY));
  } catch (e) {
    return normalizeBusinessFocus("");
  }
}

function writeBusinessFocus(value) {
  const normalized = normalizeBusinessFocus(value);
  if (!normalized) {
    updateBusinessFocusToggle("");
    return "";
  }
  try { localStorage.setItem(BUSINESS_FOCUS_STORAGE_KEY, normalized); } catch (e) {}
  updateBusinessFocusToggle(normalized);
  window.dispatchEvent(new CustomEvent("flow:businessFocusChanged", { detail: { value: normalized } }));
  refreshAreaFocusOptionsForBusinessFocus();
  return normalized;
}

// Läser råvärdet direkt så filtreringen fungerar även innan /api/businesses
// har svarat. Anropare ansvarar för Super User-gaten.
function businessFocusBusinessId() {
  let raw = "";
  try { raw = String(localStorage.getItem(BUSINESS_FOCUS_STORAGE_KEY) || ""); } catch (e) {}
  const match = raw.trim().toUpperCase().match(/^BIZ:(\d+)$/);
  if (!match) return null;
  const id = Number(match[1]);
  return Number.isInteger(id) && id > 0 ? id : null;
}

function businessFocusName(value = readBusinessFocus()) {
  const focus = normalizeBusinessFocus(value);
  if (focus === "ALLT") return "Alla verksamheter";
  if (!focus) {
    if (businessFocusLoadState === "error") return "Verksamheter kunde inte läsas";
    if (businessFocusLoadState === "loading") return "Läser verksamheter";
    return "Inga verksamheter";
  }
  const option = businessFocusOption(focus);
  return option?.title || option?.label || focus;
}

// Bygger om områdesalternativen från cachen när verksamhetsfokus ändras.
// Om aktuellt områdesfokus inte längre finns kvar normaliseras det (till ∞).
function refreshAreaFocusOptionsForBusinessFocus() {
  if (!Array.isArray(areaFocusAreasCache)) return;
  const before = readAreaFocus();
  dynamicAreaFocusOptions = buildAreaFocusOptions(areaFocusAreasCache, areaFocusUserCache);
  const after = readAreaFocus();
  try {
    if (after) localStorage.setItem(AREA_FOCUS_STORAGE_KEY, after);
    else localStorage.removeItem(AREA_FOCUS_STORAGE_KEY);
  } catch (e) {}
  updateAreaFocusToggle(after);
  if (after !== before) {
    window.dispatchEvent(new CustomEvent("flow:areaFocusChanged", { detail: { value: after } }));
  }
}

function businessFocusToggleLabel(option) {
  if (!option) return "";
  if (option.value === "ALLT") return "∞";
  return String(option.label || "").slice(0, 4);
}

function updateBusinessFocusToggle(value = readBusinessFocus()) {
  const toggle = /** @type {HTMLButtonElement | null} */ (document.getElementById("business-focus-toggle"));
  if (!toggle) return;
  const normalized = normalizeBusinessFocus(value);
  const option = businessFocusOption(normalized);
  toggle.dataset.value = normalized;
  const disabled = !option;
  toggle.textContent = option
    ? businessFocusToggleLabel(option)
    : (businessFocusLoadState === "loading" ? "..." : "!");
  toggle.classList.toggle("infinity", normalized === "ALLT");
  toggle.classList.toggle("is-error", businessFocusLoadState === "error" && !option);
  toggle.classList.toggle("is-disabled", disabled);
  toggle.title = `Verksamhetsfokus: ${businessFocusName(normalized)}`;
  toggle.setAttribute("aria-label", toggle.title);
  toggle.setAttribute("aria-pressed", normalized === "ALLT" || disabled ? "false" : "true");
  toggle.disabled = disabled;
}

function closeBusinessFocusMenu() {
  document.querySelector(".business-focus-menu")?.remove();
  document.removeEventListener("click", handleBusinessFocusMenuDocumentClick);
  document.removeEventListener("keydown", handleBusinessFocusMenuKeydown);
  window.removeEventListener("resize", closeBusinessFocusMenu);
  window.removeEventListener("scroll", handleBusinessFocusMenuWindowScroll, true);
}

function handleBusinessFocusMenuKeydown(event) {
  if (event.key === "Escape") closeBusinessFocusMenu();
}

function handleBusinessFocusMenuDocumentClick(event) {
  const menu = document.querySelector(".business-focus-menu");
  const target = event.target;
  if (menu && target?.nodeType && menu.contains(target)) return;
  closeBusinessFocusMenu();
}

function handleBusinessFocusMenuWindowScroll(event) {
  const menu = document.querySelector(".business-focus-menu");
  const target = event.target;
  if (menu && target?.nodeType && menu.contains(target)) return;
  closeBusinessFocusMenu();
}

function renderBusinessFocusMenuItems(menu, options = [], state = "ready") {
  menu.textContent = "";
  if (state === "loading") {
    const item = document.createElement("div");
    item.className = "area-focus-menu-empty";
    item.textContent = "Läser verksamheter...";
    menu.appendChild(item);
    return;
  }
  if (state === "error") {
    const item = document.createElement("div");
    item.className = "area-focus-menu-empty error";
    item.textContent = "Kunde inte läsa verksamheter.";
    menu.appendChild(item);
    return;
  }
  if (!options.length) {
    const item = document.createElement("div");
    item.className = "area-focus-menu-empty";
    item.textContent = "Inga verksamheter";
    menu.appendChild(item);
    return;
  }

  const current = readBusinessFocus();
  options.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("role", "menuitemradio");
    button.setAttribute("aria-checked", option.value === current ? "true" : "false");
    button.dataset.value = option.value;

    const code = document.createElement("span");
    code.className = "area-focus-menu-code";
    code.textContent = option.value === "ALLT" ? "∞" : option.label;
    button.appendChild(code);

    const name = document.createElement("span");
    name.className = "area-focus-menu-name";
    name.textContent = option.value === "ALLT" ? "Alla verksamheter" : (option.title || option.label);
    button.appendChild(name);

    button.addEventListener("click", () => {
      writeBusinessFocus(option.value);
      closeBusinessFocusMenu();
    });
    menu.appendChild(button);
  });
}

function openBusinessFocusMenu(event) {
  event.preventDefault();
  event.stopPropagation();
  const anchor = event.currentTarget || document.getElementById("business-focus-toggle");
  closeBusinessFocusMenu();
  closeAreaFocusMenu();

  const menu = document.createElement("div");
  menu.className = "area-focus-menu business-focus-menu";
  menu.setAttribute("role", "menu");
  menu.setAttribute("aria-label", "Välj verksamhetsfokus");
  menu.addEventListener("click", (event) => event.stopPropagation());
  menu.addEventListener("pointerdown", (event) => event.stopPropagation());
  menu.addEventListener("wheel", (event) => event.stopPropagation(), { passive: true });
  document.body.appendChild(menu);

  const options = businessFocusOptions();
  renderBusinessFocusMenuItems(menu, options, options.length ? "ready" : "loading");
  positionAreaFocusMenu(menu, event, anchor);

  if (!options.length) {
    loadBusinessFocusBusinesses()
      .then((loadedOptions) => {
        if (!menu.isConnected) return;
        renderBusinessFocusMenuItems(menu, loadedOptions || businessFocusOptions());
        positionAreaFocusMenu(menu, event, anchor);
      })
      .catch(() => {
        if (!menu.isConnected) return;
        renderBusinessFocusMenuItems(menu, [], "error");
        positionAreaFocusMenu(menu, event, anchor);
      });
  }

  setTimeout(() => {
    document.addEventListener("click", handleBusinessFocusMenuDocumentClick);
    document.addEventListener("keydown", handleBusinessFocusMenuKeydown);
    window.addEventListener("resize", closeBusinessFocusMenu);
    window.addEventListener("scroll", handleBusinessFocusMenuWindowScroll, true);
  });
}

function initBusinessFocusToggle(user = null) {
  const toggle = document.getElementById("business-focus-toggle");
  if (!toggle) return;
  if (!user?.is_super_user) {
    toggle.remove();
    return;
  }
  if (user !== null) areaFocusUserCache = user;
  updateBusinessFocusToggle(readBusinessFocus());
  loadBusinessFocusBusinesses().catch(() => {});
  toggle.setAttribute("aria-haspopup", "menu");
  toggle.addEventListener("click", () => writeBusinessFocus(nextBusinessFocus()));
  toggle.addEventListener("contextmenu", (event) => openBusinessFocusMenu(event));
  toggle.addEventListener("keydown", (event) => {
    if (event.key !== "ContextMenu" && !(event.shiftKey && event.key === "F10")) return;
    openBusinessFocusMenu(event);
  });
}

window.addEventListener("storage", (event) => {
  if (event.key !== AREA_FOCUS_STORAGE_KEY) return;
  const value = normalizeAreaFocus(event.newValue);
  updateAreaFocusToggle(value);
  window.dispatchEvent(new CustomEvent("flow:areaFocusChanged", { detail: { value } }));
});

window.addEventListener("storage", (event) => {
  if (event.key !== BUSINESS_FOCUS_STORAGE_KEY) return;
  const value = normalizeBusinessFocus(event.newValue);
  updateBusinessFocusToggle(value);
  window.dispatchEvent(new CustomEvent("flow:businessFocusChanged", { detail: { value } }));
  refreshAreaFocusOptionsForBusinessFocus();
});


// @ts-check
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

function normalizeAppZoom(value) {
  if (value === null || value === undefined || value === "") return APP_ZOOM_DEFAULT;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return APP_ZOOM_DEFAULT;
  const stepped = Math.round(numeric / APP_ZOOM_STEP) * APP_ZOOM_STEP;
  return Math.min(APP_ZOOM_MAX, Math.max(APP_ZOOM_MIN, stepped));
}

function readAppZoom() {
  try {
    return normalizeAppZoom(localStorage.getItem(APP_ZOOM_STORAGE_KEY));
  } catch (e) {
    return APP_ZOOM_DEFAULT;
  }
}

function updateAppZoomControls(percent = readAppZoom()) {
  const normalized = normalizeAppZoom(percent);
  document.documentElement.dataset.appZoom = String(normalized);
  document.querySelectorAll("[data-app-zoom-value]").forEach((node) => {
    node.textContent = `${normalized}%`;
  });

  const out = document.getElementById("app-zoom-out");
  const input = document.getElementById("app-zoom-in");
  if (out instanceof HTMLButtonElement) {
    out.disabled = normalized <= APP_ZOOM_MIN;
    out.title = `Zooma ut (Ctrl+-), nu ${normalized}%`;
    out.setAttribute("aria-label", out.title);
  }
  if (input instanceof HTMLButtonElement) {
    input.disabled = normalized >= APP_ZOOM_MAX;
    input.title = `Zooma in (Ctrl++), nu ${normalized}%`;
    input.setAttribute("aria-label", input.title);
  }
}

function applyAppZoom(percent, { persist = true } = {}) {
  const normalized = normalizeAppZoom(percent);
  const target = document.body || document.documentElement;
  target.style.zoom = String(normalized / 100);
  document.documentElement.dataset.appZoom = String(normalized);
  if (persist) {
    try { localStorage.setItem(APP_ZOOM_STORAGE_KEY, String(normalized)); } catch (e) {}
  }
  updateAppZoomControls(normalized);
  return normalized;
}

function changeAppZoom(deltaSteps) {
  applyAppZoom(readAppZoom() + (deltaSteps * APP_ZOOM_STEP));
}

function resetAppZoom() {
  applyAppZoom(APP_ZOOM_DEFAULT);
}

function renderAppZoomControls() {
  return `
      <div class="app-zoom-control" id="app-zoom-control" role="group" aria-label="Appzoom">
        <button type="button" id="app-zoom-out">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="10.5" cy="10.5" r="6.5"></circle>
            <path d="M15.5 15.5 21 21"></path>
            <path d="M7.5 10.5h6"></path>
          </svg>
        </button>
        <button type="button" id="app-zoom-in">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="10.5" cy="10.5" r="6.5"></circle>
            <path d="M15.5 15.5 21 21"></path>
            <path d="M7.5 10.5h6"></path>
            <path d="M10.5 7.5v6"></path>
          </svg>
        </button>
      </div>
  `;
}

function initAppZoomControls() {
  applyAppZoom(readAppZoom(), { persist: false });
  document.getElementById("app-zoom-out")?.addEventListener("click", () => changeAppZoom(-1));
  document.getElementById("app-zoom-in")?.addEventListener("click", () => changeAppZoom(1));
  updateAppZoomControls();
}

function initAppZoomShortcuts() {
  document.addEventListener("keydown", (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
    const key = String(event.key || "").toLowerCase();
    if (key === "+" || key === "=") {
      event.preventDefault();
      changeAppZoom(1);
    } else if (key === "-" || key === "_") {
      event.preventDefault();
      changeAppZoom(-1);
    } else if (key === "0") {
      event.preventDefault();
      resetAppZoom();
    }
  });
  window.addEventListener("wheel", (event) => {
    if (!(event.ctrlKey || event.metaKey)) return;
    event.preventDefault();
    changeAppZoom(event.deltaY < 0 ? 1 : -1);
  }, { passive: false });
}

applyAppZoom(readAppZoom(), { persist: false });
initAppZoomShortcuts();


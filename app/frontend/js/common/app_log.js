// @ts-check
appLogEntries = readStoredAppLogEntries();

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

function normalizeAppLogKind(kind) {
  const value = String(kind || "info").trim().toLowerCase();
  return ["info", "success", "warn", "error"].includes(value) ? value : "info";
}

function storedAppLogEntry(entry) {
  if (!entry || typeof entry !== "object") return null;
  const message = String(entry.message || "").replace(/\s+/g, " ").trim();
  if (!message) return null;
  const title = String(entry.title || "System").slice(0, 80);
  if (title === "Vy" || message.startsWith("Öppnade vy:")) return null;
  return {
    time: String(entry.time || new Date().toLocaleString("sv-SE")),
    kind: normalizeAppLogKind(entry.kind),
    title,
    message: message.slice(0, 600),
  };
}

function readStoredAppLogEntries() {
  try {
    const raw = sessionStorage.getItem(APP_LOG_STORAGE_KEY);
    if (!raw) return [];
    const payload = JSON.parse(raw);
    const rows = Array.isArray(payload?.entries) ? payload.entries : Array.isArray(payload) ? payload : [];
    return rows.map(storedAppLogEntry).filter(Boolean).slice(0, APP_LOG_MAX_ENTRIES);
  } catch (_error) {
    return [];
  }
}

function persistAppLogEntries() {
  try {
    sessionStorage.setItem(APP_LOG_STORAGE_KEY, JSON.stringify({
      version: 1,
      entries: appLogEntries.slice(0, APP_LOG_MAX_ENTRIES),
    }));
  } catch (_error) {}
}

function updateAppLogNotice() {
  const notice = document.getElementById("log-notice");
  const toggle = document.getElementById("log-toggle");
  if (!notice) return;
  try { sessionStorage.removeItem(APP_LOG_UNREAD_STORAGE_KEY); } catch (_error) {}
  notice.hidden = true;
  notice.textContent = "";
  toggle?.classList.remove("has-log-notice", "log-signal");
  toggle?.setAttribute("aria-label", "Öppna logg");
}

function clearAppLogNotice() {
  if (appLogSignalTimer) {
    window.clearTimeout(appLogSignalTimer);
    appLogSignalTimer = null;
  }
  updateAppLogNotice();
}

function triggerAppLogSignal() {
  const notice = document.getElementById("log-notice");
  const toggle = document.getElementById("log-toggle");
  if (!notice || !toggle) return;
  try { sessionStorage.removeItem(APP_LOG_UNREAD_STORAGE_KEY); } catch (_error) {}
  if (appLogSignalTimer) window.clearTimeout(appLogSignalTimer);
  notice.hidden = false;
  notice.textContent = "";
  toggle.classList.remove("log-signal");
  void toggle.offsetWidth;
  toggle.classList.add("log-signal");
  toggle.setAttribute("aria-label", "Öppna logg, ny händelse loggad");
  appLogSignalTimer = window.setTimeout(() => {
    notice.hidden = true;
    toggle.classList.remove("log-signal");
    toggle.setAttribute("aria-label", "Öppna logg");
    appLogSignalTimer = null;
  }, 980);
}

function appendAppLog(message, kind = "info", title = "System") {
  const entry = storedAppLogEntry({
    time: new Date().toLocaleString("sv-SE"),
    kind,
    title,
    message,
  });
  if (!entry) return;
  appLogEntries.unshift(entry);
  if (appLogEntries.length > APP_LOG_MAX_ENTRIES) appLogEntries.length = APP_LOG_MAX_ENTRIES;
  persistAppLogEntries();
  renderAppLogEntries();
  triggerAppLogSignal();
  console.info(`[${title}] ${entry.message}`);
}

function clearAppLog() {
  appLogEntries.length = 0;
  persistAppLogEntries();
  renderAppLogEntries();
  clearAppLogNotice();
}


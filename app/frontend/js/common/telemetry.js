function waitMetricNow() {
  return typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
}

function waitMetricPath(value) {
  try {
    const url = new URL(value || window.location?.pathname || "/", window.location.origin);
    return url.pathname || "/";
  } catch (_error) {
    return String(value || "/").split("?")[0].split("#")[0] || "/";
  }
}

function sanitizeWaitMetricText(value, maxLength = 160) {
  if (value == null) return null;
  const text = String(value).replace(/\s+/g, " ").trim();
  if (!text) return null;
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
}

function sanitizeWaitMetricDetail(detail) {
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return null;
  const cleaned = {};
  Object.entries(detail).slice(0, 20).forEach(([key, value]) => {
    const safeKey = sanitizeWaitMetricText(key, 80);
    if (!safeKey) return;
    if (typeof value === "number" || typeof value === "boolean") {
      cleaned[safeKey] = value;
    } else {
      cleaned[safeKey] = sanitizeWaitMetricText(value, 300);
    }
  });
  return Object.keys(cleaned).length ? cleaned : null;
}

function activeWaitMetricViewId() {
  return sanitizeWaitMetricText(document.body?.dataset.activePage || window.flowActivePage || "", 80);
}

function scheduleWaitMetricFlush() {
  if (waitMetricFlushTimer || waitMetricInFlight || !waitMetricQueue.length) return;
  waitMetricFlushTimer = setTimeout(() => {
    waitMetricFlushTimer = null;
    void flushWaitMetrics();
  }, WAIT_METRIC_FLUSH_MS);
}

async function flushWaitMetrics({ keepalive = false } = {}) {
  if (waitMetricFlushTimer) {
    clearTimeout(waitMetricFlushTimer);
    waitMetricFlushTimer = null;
  }
  if (waitMetricInFlight || !waitMetricQueue.length) return;
  const items = waitMetricQueue.splice(0, WAIT_METRIC_MAX_QUEUE);
  const body = JSON.stringify({ items });
  if (keepalive && navigator.sendBeacon) {
    try {
      const blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon(COMMON_WAIT_METRIC_REPORT_PATH, blob)) return;
    } catch (_error) {}
  }
  waitMetricInFlight = true;
  try {
    await fetch(COMMON_WAIT_METRIC_REPORT_PATH, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: keepalive && body.length < 60000,
    });
  } catch (_error) {
    // Telemetri far aldrig sega ner anvandaren. Misslyckade batches slapps.
  } finally {
    waitMetricInFlight = false;
    if (waitMetricQueue.length) scheduleWaitMetricFlush();
  }
}

function recordWaitMetric(metric = {}) {
  const duration = Number(metric.duration_ms ?? metric.durationMs ?? 0);
  if (!Number.isFinite(duration) || duration < 0) return;
  waitMetricQueue.push({
    event_type: sanitizeWaitMetricText(metric.event_type || metric.eventType || "interaction", 80) || "interaction",
    view_id: sanitizeWaitMetricText(metric.view_id || metric.viewId || activeWaitMetricViewId(), 80),
    target: sanitizeWaitMetricText(metric.target || waitMetricPath(window.location?.pathname || "/"), 160),
    duration_ms: Math.round(duration),
    status: sanitizeWaitMetricText(metric.status || "ok", 20) || "ok",
    detail: sanitizeWaitMetricDetail(metric.detail),
  });
  if (waitMetricQueue.length > WAIT_METRIC_MAX_QUEUE) {
    waitMetricQueue = waitMetricQueue.slice(-WAIT_METRIC_MAX_QUEUE);
  }
  if (waitMetricQueue.length >= 20) {
    void flushWaitMetrics();
  } else {
    scheduleWaitMetricFlush();
  }
}

function reportPageLoadWaitMetric(activePage) {
  if (!activePage || activePage === "passwordSetup") return;
  recordWaitMetric({
    event_type: "view_load",
    view_id: activePage,
    target: waitMetricPath(window.location?.pathname || "/"),
    duration_ms: waitMetricNow() - FLOW_PAGE_STARTED_AT,
    status: "ok",
    detail: { source: "initPage" },
  });
}

window.addEventListener("pagehide", () => {
  void flushWaitMetrics({ keepalive: true });
});

try {
  if ("PerformanceObserver" in window && PerformanceObserver.supportedEntryTypes?.includes("longtask")) {
    const waitLongTaskObserver = new PerformanceObserver((list) => {
      list.getEntries().forEach((entry) => {
        if (Number(entry.duration || 0) < 75) return;
        recordWaitMetric({
          event_type: "client_long_task",
          view_id: activeWaitMetricViewId(),
          target: "main_thread",
          duration_ms: entry.duration,
          status: "warn",
          detail: { name: entry.name || "longtask" },
        });
      });
    });
    waitLongTaskObserver.observe({ entryTypes: ["longtask"] });
  }
} catch (_error) {}

function interactionNow() {
  return typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
}

function interactionUuid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `i-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function interactionPath(value) {
  try {
    const url = new URL(value || window.location?.pathname || "/", window.location.origin);
    return url.pathname || "/";
  } catch (_error) {
    return String(value || "/").split("?")[0].split("#")[0] || "/";
  }
}

function interactionText(value, maxLength = 180) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
}

function interactionClientSurface() {
  if (window.flowDesktop?.isDesktop?.() || window.flowDesktopBridge || window.qt?.webChannelTransport) return "desktop";
  if (window.location?.pathname?.includes("meta-upload")) return "public";
  return "web";
}

function interactionViewId() {
  return interactionText(document.body?.dataset.activePage || window.flowActivePage || "", 80)
    || (window.location?.pathname?.includes("meta-upload") ? "metaUpload" : "");
}

function interactionDetailValue(value) {
  if (value == null || typeof value === "boolean" || typeof value === "number") return value;
  if (typeof value === "string") return interactionText(value, 500);
  if (Array.isArray(value)) return value.slice(0, 30).map(interactionDetailValue);
  if (typeof value === "object") {
    const result = {};
    Object.entries(value).slice(0, 50).forEach(([key, item]) => {
      const safeKey = interactionText(key, 80);
      if (safeKey) result[safeKey] = interactionDetailValue(item);
    });
    return result;
  }
  return interactionText(value, 200);
}

function interactionCleanDetail(detail) {
  if (!detail || typeof detail !== "object") return null;
  const cleaned = {};
  Object.entries(detail).slice(0, 60).forEach(([key, value]) => {
    const safeKey = interactionText(key, 80);
    if (!safeKey) return;
    cleaned[safeKey] = interactionDetailValue(value);
  });
  return Object.keys(cleaned).length ? cleaned : null;
}

function interactionControlLabel(element) {
  if (!element) return "";
  const direct = element.getAttribute?.("data-track-label")
    || element.getAttribute?.("aria-label")
    || element.getAttribute?.("title")
    || element.labels?.[0]?.textContent
    || element.textContent
    || element.value;
  return interactionText(direct, 180);
}

function interactionControlId(element) {
  if (!element) return "";
  const dataset = element.dataset || {};
  const dataKey = dataset.trackId || dataset.runFlow || dataset.copyColumn || dataset.openExcel || dataset.downloadCsv
    || dataset.historyMode || dataset.flowField || dataset.bulkKey || dataset.copyTextResult;
  return interactionText(
    element.id || dataKey || element.name || element.getAttribute?.("aria-label") || element.className || element.tagName,
    160,
  );
}

function interactionFeatureForElement(element) {
  if (!element) return "";
  const dataset = element.dataset || {};
  if (dataset.runFlow || dataset.followUpFlow || dataset.copyColumn || dataset.openExcel || dataset.downloadCsv) return "allocation";
  if (dataset.historyMode || interactionViewId() === "analytics") return "history";
  if (element.closest?.(".sidebar")) return "sidebar";
  return interactionViewId();
}

function interactionRoleForElement(element) {
  if (!element) return "";
  const role = element.getAttribute?.("role");
  const tag = String(element.tagName || "").toLowerCase();
  const type = String(element.type || "").toLowerCase();
  return role || (tag === "input" ? `input:${type || "text"}` : tag);
}

function interactionValueMeta(element) {
  if (!element) return {};
  const tag = String(element.tagName || "").toLowerCase();
  const type = String(element.type || "").toLowerCase();
  if (type === "password" || type === "hidden") return {};
  if (type === "file") return { file_count: element.files?.length || 0 };
  if (type === "checkbox" || type === "radio") return { checked: Boolean(element.checked) };
  if (tag === "select") {
    const selected = element.selectedOptions?.[0];
    return {
      selected_index: element.selectedIndex,
      selected_option_label: interactionText(selected?.textContent || "", 180),
      value_sample: interactionText(element.value || "", 300),
    };
  }
  const value = typeof element.value === "string" ? element.value : "";
  return {
    value_length: value.length,
    value_sample: interactionText(value, 300),
  };
}

function scheduleInteractionFlush() {
  if (interactionFlushTimer || interactionInFlight || !interactionQueue.length) return;
  interactionFlushTimer = setTimeout(() => {
    interactionFlushTimer = null;
    void flushInteractions();
  }, INTERACTION_FLUSH_MS);
}

async function flushInteractions({ keepalive = false, publicOnly = false } = {}) {
  if (interactionFlushTimer) {
    clearTimeout(interactionFlushTimer);
    interactionFlushTimer = null;
  }
  if (interactionInFlight || !interactionQueue.length) return;
  const items = interactionQueue.splice(0, INTERACTION_MAX_QUEUE);
  const isPublic = publicOnly || interactionClientSurface() === "public";
  const body = JSON.stringify({ items });
  const path = isPublic ? COMMON_PUBLIC_INTERACTION_EVENT_REPORT_PATH : COMMON_INTERACTION_EVENT_REPORT_PATH;
  if (keepalive && navigator.sendBeacon) {
    try {
      const blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon(path, blob)) return;
    } catch (_error) {}
  }
  interactionInFlight = true;
  try {
    await fetch(path, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: keepalive && body.length < 60000,
    });
  } catch (_error) {
    // Tracking far aldrig blockera anvandaren. Misslyckade batches slapps.
  } finally {
    interactionInFlight = false;
    if (interactionQueue.length) scheduleInteractionFlush();
  }
}

function flowTrack(eventType, details = {}) {
  const interactionId = details.interaction_id || details.interactionId || interactionUuid();
  const item = {
    event_type: interactionText(eventType || details.event_type || "interaction", 80) || "interaction",
    view_id: interactionText(details.view_id || details.viewId || interactionViewId(), 80),
    page_path: interactionPath(details.page_path || details.pagePath || window.location?.pathname || "/"),
    control_id: interactionText(details.control_id || details.controlId || "", 160),
    control_label: interactionText(details.control_label || details.controlLabel || "", 180),
    control_role: interactionText(details.control_role || details.controlRole || "", 80),
    feature: interactionText(details.feature || interactionFeatureForElement(details.element), 80),
    flow_id: interactionText(details.flow_id || details.flowId || "", 120),
    table_key: interactionText(details.table_key || details.tableKey || "", 120),
    table_label: interactionText(details.table_label || details.tableLabel || "", 160),
    column_index: Number.isInteger(details.column_index) ? details.column_index : Number.isInteger(details.columnIndex) ? details.columnIndex : null,
    column_label: interactionText(details.column_label || details.columnLabel || "", 180),
    row_count: Number.isFinite(Number(details.row_count ?? details.rowCount)) ? Number(details.row_count ?? details.rowCount) : null,
    client_surface: interactionText(details.client_surface || details.clientSurface || interactionClientSurface(), 40),
    interaction_id: interactionText(interactionId, 80),
    status: interactionText(details.status || "ok", 20) || "ok",
    detail: interactionCleanDetail(details.detail || {}),
  };
  interactionQueue.push(item);
  if (interactionQueue.length > INTERACTION_MAX_QUEUE) interactionQueue = interactionQueue.slice(-INTERACTION_MAX_QUEUE);
  if (item.event_type !== "api_request" && item.event_type !== "download") {
    lastInteractionContext = {
      interaction_id: item.interaction_id,
      event_type: item.event_type,
      control_id: item.control_id,
      control_label: item.control_label,
      feature: item.feature,
      at: interactionNow(),
    };
  }
  if (interactionQueue.length >= 20) void flushInteractions();
  else scheduleInteractionFlush();
  return item.interaction_id;
}

function currentInteractionContext() {
  if (!lastInteractionContext) return null;
  if (interactionNow() - lastInteractionContext.at > INTERACTION_CONTEXT_MS) return null;
  return { ...lastInteractionContext };
}

function shouldIgnoreAutoInteraction(element) {
  if (!element) return true;
  if (element.closest?.("[data-track-ignore]")) return true;
  const type = String(element.type || "").toLowerCase();
  if (type === "password" || type === "hidden") return true;
  return false;
}

function trackElementInteraction(eventType, element, extraDetail = {}) {
  if (shouldIgnoreAutoInteraction(element)) return;
  const dataset = element.dataset || {};
  flowTrack(eventType, {
    element,
    control_id: interactionControlId(element),
    control_label: interactionControlLabel(element),
    control_role: interactionRoleForElement(element),
    feature: interactionFeatureForElement(element),
    flow_id: dataset.runFlow || dataset.followUpFlow || "",
    table_key: dataset.copyKey || dataset.openExcel || dataset.downloadCsv || "",
    column_index: dataset.copyColumn != null ? Number(dataset.copyColumn) : null,
    column_label: dataset.copyLabel || "",
    detail: {
      tag: String(element.tagName || "").toLowerCase(),
      type: element.type || "",
      ...interactionValueMeta(element),
      ...extraDetail,
    },
  });
}

function initInteractionAutoCapture() {
  document.addEventListener("click", (event) => {
    const element = event.target?.closest?.("button, a[href], [role='button'], input[type='button'], input[type='submit'], summary, [data-track-click]");
    if (!element) return;
    trackElementInteraction("click", element, { href: interactionPath(element.getAttribute?.("href") || "") });
  }, true);
  document.addEventListener("contextmenu", (event) => {
    const element = event.target?.closest?.("button, a[href], [role='button'], td, th, .allocation-map-location, [data-track-context]");
    if (!element) return;
    trackElementInteraction("contextmenu", element);
  }, true);
  document.addEventListener("change", (event) => {
    const element = event.target?.closest?.("input, select, textarea");
    if (!element) return;
    trackElementInteraction("change", element);
  }, true);
  document.addEventListener("submit", (event) => {
    const element = event.target?.closest?.("form");
    if (!element) return;
    trackElementInteraction("submit", element);
  }, true);
  window.addEventListener("pagehide", () => {
    void flushInteractions({ keepalive: true });
  });
}

initInteractionAutoCapture();

const CLIENT_RUNTIME_LOGGED_MESSAGES = new Set();

function logClientRuntimeIssue(message, title = "Klientfel") {
  const text = String(message || "Oväntat klientfel.").replace(/\s+/g, " ").trim();
  if (!text) return;
  const key = `${title}:${text}`.slice(0, 300);
  if (CLIENT_RUNTIME_LOGGED_MESSAGES.has(key)) return;
  CLIENT_RUNTIME_LOGGED_MESSAGES.add(key);
  if (CLIENT_RUNTIME_LOGGED_MESSAGES.size > 50) {
    CLIENT_RUNTIME_LOGGED_MESSAGES.clear();
    CLIENT_RUNTIME_LOGGED_MESSAGES.add(key);
  }
  appendAppLog(text, "error", title);
}

window.addEventListener("error", (event) => {
  logClientRuntimeIssue(event.message || event.error?.message, "Klientfel");
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason;
  logClientRuntimeIssue(reason?.message || reason, "Klientfel");
});


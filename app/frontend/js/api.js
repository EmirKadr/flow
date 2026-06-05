// Tunn fetch-wrapper. Skickar med session-cookie. 401 -> /login.html.

function isAuthPath(path) {
  return (
    path.startsWith("/api/auth/login") ||
    path.startsWith("/api/auth/me") ||
    path.startsWith("/api/auth/logout") ||
    path.startsWith("/api/auth/set-password")
  );
}

function connectionError(path, originalError) {
  const protocol = window.location?.protocol || "";
  const message = protocol === "file:"
    ? "Appen måste öppnas via servern, inte direkt från fil. Öppna https://stigamo.nu eller starta lokal testmiljö."
    : "Kunde inte ansluta till servern. Kontrollera att appen öppnas via rätt adress och att backend är igång.";
  const err = new Error(message);
  err.status = 0;
  err.path = path;
  err.originalError = originalError;
  return err;
}

const HTTP_STATUS_LABELS = {
  400: "Bad Request",
  401: "Unauthorized",
  403: "Forbidden",
  404: "Not Found",
  409: "Conflict",
  413: "Request Entity Too Large",
  422: "Validation Error",
  429: "Too Many Requests",
  500: "Server Error",
  502: "Bad Gateway",
  503: "Service Unavailable",
  504: "Gateway Timeout",
};

function httpStatusLabel(status) {
  const code = Number(status || 0);
  if (!code) return "serverfel";
  const label = HTTP_STATUS_LABELS[code];
  return label ? `HTTP ${code} (${label})` : `HTTP ${code}`;
}

function isLikelyHtmlDocument(value) {
  const text = String(value || "").trim().slice(0, 1000).toLowerCase();
  return (
    text.startsWith("<!doctype html") ||
    text.startsWith("<html") ||
    /<html[\s>]/.test(text) ||
    /<body[\s>]/.test(text)
  );
}

function htmlErrorMessage(status) {
  return `Servern svarade med ${httpStatusLabel(status)}.`;
}

function errorMessageFromBody(body, status) {
  const detail = body?.detail ?? body?.error;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    if (typeof detail.message === "string") return detail.message;
    try {
      return JSON.stringify(detail);
    } catch (_error) {
      return `HTTP ${status}`;
    }
  }
  if (typeof body === "string" && body.trim()) {
    if (isLikelyHtmlDocument(body)) return htmlErrorMessage(status);
    return truncateErrorText(body, 500) || httpStatusLabel(status);
  }
  return httpStatusLabel(status);
}

const CLIENT_ERROR_REPORT_PATH = "/api/audit/client-error";
const CLIENT_EVENT_REPORT_PATH = "/api/audit/client-event";
const WAIT_METRIC_REPORT_PATH = "/api/healthcheck/wait-metrics";
const INTERACTION_EVENT_REPORT_PATH = "/api/audit/interactions";
const PUBLIC_INTERACTION_EVENT_REPORT_PATH = "/api/audit/interactions/public";
const API_PREFETCH_DEFAULT_TTL_MS = 45 * 1000;
const API_GET_CACHE_STORAGE_PREFIX = "flow-api-get-cache-v1:";
const API_NETWORK_ERROR_REPORT_DEDUPE_MS = 60 * 1000;
const apiGetCache = new Map();
const apiGetInFlight = new Map();
const apiNetworkErrorReportLastAt = new Map();
let apiGetCacheGeneration = 0;

function isAbortError(error) {
  return error?.name === "AbortError";
}

function cloneApiCacheValue(value) {
  if (value == null) return value;
  if (typeof structuredClone === "function") {
    try { return structuredClone(value); } catch (_error) {}
  }
  try {
    return JSON.parse(JSON.stringify(value));
  } catch (_error) {
    return value;
  }
}

function apiCacheKey(path) {
  return String(path || "");
}

function apiStorageCacheKey(path) {
  return `${API_GET_CACHE_STORAGE_PREFIX}${apiCacheKey(path)}`;
}

function readApiGetPersistentCache(path) {
  try {
    const storageKey = apiStorageCacheKey(path);
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return null;
    const entry = JSON.parse(raw);
    if (!entry || Number(entry.expiresAt || 0) <= Date.now()) {
      sessionStorage.removeItem(storageKey);
      return null;
    }
    apiGetCache.set(apiCacheKey(path), {
      body: cloneApiCacheValue(entry.body),
      expiresAt: Number(entry.expiresAt),
    });
    return cloneApiCacheValue(entry.body);
  } catch (_error) {
    return null;
  }
}

function readApiGetCache(path) {
  const entry = apiGetCache.get(apiCacheKey(path));
  if (!entry || entry.expiresAt <= Date.now()) {
    apiGetCache.delete(apiCacheKey(path));
    return readApiGetPersistentCache(path);
  }
  return cloneApiCacheValue(entry.body);
}

function writeApiGetCache(path, body, ttlMs = API_PREFETCH_DEFAULT_TTL_MS) {
  const ttl = Math.max(0, Number(ttlMs) || 0);
  if (!ttl) return;
  apiGetCache.set(apiCacheKey(path), {
    body: cloneApiCacheValue(body),
    expiresAt: Date.now() + ttl,
  });
  try {
    sessionStorage.setItem(apiStorageCacheKey(path), JSON.stringify({
      body: cloneApiCacheValue(body),
      expiresAt: Date.now() + ttl,
    }));
  } catch (_error) {}
}

function clearApiGetPersistentCache(predicate = null) {
  try {
    const keys = [];
    for (let index = 0; index < sessionStorage.length; index += 1) {
      const storageKey = sessionStorage.key(index);
      if (!storageKey?.startsWith(API_GET_CACHE_STORAGE_PREFIX)) continue;
      const cacheKey = storageKey.slice(API_GET_CACHE_STORAGE_PREFIX.length);
      if (typeof predicate !== "function" || predicate(cacheKey)) keys.push(storageKey);
    }
    for (const key of keys) sessionStorage.removeItem(key);
  } catch (_error) {}
}

function clearApiGetCache(predicate = null) {
  apiGetCacheGeneration += 1;
  clearApiGetPersistentCache(predicate);
  if (typeof predicate !== "function") {
    apiGetCache.clear();
    apiGetInFlight.clear();
    return;
  }
  for (const key of [...apiGetCache.keys()]) {
    if (predicate(key)) apiGetCache.delete(key);
  }
  for (const key of [...apiGetInFlight.keys()]) {
    if (predicate(key)) apiGetInFlight.delete(key);
  }
}

function truncateErrorText(value, maxLength = 500) {
  if (value == null) return null;
  const text = String(value).replace(/\s+/g, " ").trim();
  if (!text) return null;
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
}

function pathWithoutQuery(path) {
  try {
    const url = new URL(path, window.location.origin);
    return url.pathname || "/";
  } catch (_error) {
    return String(path || "").split("?")[0].split("#")[0] || "/";
  }
}

function errorDetailForReport(body, status = 0) {
  const detail = body?.detail ?? body?.error;
  if (typeof detail === "string") return truncateErrorText(detail);
  if (Array.isArray(detail)) return `${detail.length} valideringsfel`;
  if (detail && typeof detail === "object") {
    if (typeof detail.message === "string") return truncateErrorText(detail.message);
    const keys = Object.keys(detail).slice(0, 6).join(", ");
    return keys ? `Detaljfält: ${keys}` : null;
  }
  if (typeof body === "string") {
    if (isLikelyHtmlDocument(body)) return `HTML-felsida fran servern: ${httpStatusLabel(status)}`;
    return truncateErrorText(body);
  }
  return null;
}

function errorCodeForReport(body, status) {
  const detail = body?.detail;
  if (detail && typeof detail === "object") {
    const candidate = detail.error_code || detail.code || detail.error;
    if (typeof candidate === "string") return truncateErrorText(candidate, 120);
  }
  if (typeof body?.error_code === "string") return truncateErrorText(body.error_code, 120);
  if (typeof body?.error === "string" && body.error.length <= 80) return truncateErrorText(body.error, 120);
  return status ? `HTTP ${status}` : "network_error";
}

function shouldReportApiError(path, status) {
  const safePath = pathWithoutQuery(path);
  if (!safePath.startsWith("/api/")) return false;
  if (safePath === CLIENT_ERROR_REPORT_PATH) return false;
  if (safePath === CLIENT_EVENT_REPORT_PATH) return false;
  if (safePath === WAIT_METRIC_REPORT_PATH) return false;
  if (safePath === INTERACTION_EVENT_REPORT_PATH) return false;
  if (safePath === PUBLIC_INTERACTION_EVENT_REPORT_PATH) return false;
  if (safePath === "/api/auth/me") return false;
  if (status === 401) return false;
  return true;
}

function apiTelemetryNow() {
  return typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
}

function shouldRecordApiWaitMetric(path, options = {}) {
  if (options.telemetryEnabled === false) return false;
  const safePath = pathWithoutQuery(path);
  if (!safePath.startsWith("/api/")) return false;
  if (safePath === CLIENT_ERROR_REPORT_PATH) return false;
  if (safePath === CLIENT_EVENT_REPORT_PATH) return false;
  if (safePath === WAIT_METRIC_REPORT_PATH) return false;
  if (safePath === INTERACTION_EVENT_REPORT_PATH) return false;
  if (safePath === PUBLIC_INTERACTION_EVENT_REPORT_PATH) return false;
  if (safePath === "/api/auth/me") return false;
  return typeof window.flowRecordWaitMetric === "function";
}

function reportApiWaitMetric(path, method, startedAt, status, options = {}, detail = {}) {
  if (!shouldRecordApiWaitMetric(path, options)) return;
  const safePath = pathWithoutQuery(path);
  window.flowRecordWaitMetric({
    event_type: options.telemetryEventType || "api_request",
    target: `${String(method || "GET").toUpperCase()} ${safePath}`,
    duration_ms: apiTelemetryNow() - startedAt,
    status: status || "ok",
    detail: {
      source: options.telemetrySource || "foreground",
      status_code: detail.status_code || 0,
      cache_hit: Boolean(detail.cache_hit),
      shared_in_flight: Boolean(detail.shared_in_flight),
      error_code: detail.error_code || "",
    },
  });
}

function reportApiError(path, details = {}) {
  const status = Number(details.status || 0);
  if (!shouldReportApiError(path, status)) return;

  const payload = {
    path: pathWithoutQuery(path),
    method: String(details.method || "GET").toUpperCase().slice(0, 10),
    status,
    error_code: truncateErrorText(details.error_code || errorCodeForReport(details.body, status), 120),
    message: truncateErrorText(details.message),
    detail: errorDetailForReport(details.body, status) || truncateErrorText(details.detail),
    page_path: pathWithoutQuery(window.location?.pathname || "/"),
  };
  if (status === 0) {
    const key = `${payload.method}|${payload.path}|${payload.error_code || "network_error"}|${payload.page_path}`;
    const now = Date.now();
    const lastAt = apiNetworkErrorReportLastAt.get(key) || 0;
    if (now - lastAt < API_NETWORK_ERROR_REPORT_DEDUPE_MS) return;
    apiNetworkErrorReportLastAt.set(key, now);
  }
  const body = JSON.stringify(payload);
  fetch(CLIENT_ERROR_REPORT_PATH, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: body.length < 60000,
  }).catch(() => {});
}

function reportClientEvent(eventType, details = {}) {
  const payload = {
    event_type: String(eventType || "client_event").slice(0, 80),
    view_id: details.view_id ? String(details.view_id).slice(0, 80) : null,
    view_label: details.view_label ? String(details.view_label).slice(0, 120) : null,
    page_path: pathWithoutQuery(details.page_path || window.location?.pathname || "/"),
  };
  const body = JSON.stringify(payload);
  fetch(CLIENT_EVENT_REPORT_PATH, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: body.length < 60000,
  }).catch(() => {});
}

function shouldTrackApiInteraction(path, method, options = {}) {
  if (options.trackInteraction === false) return false;
  const safePath = pathWithoutQuery(path);
  if (!safePath.startsWith("/api/")) return false;
  if (safePath === CLIENT_ERROR_REPORT_PATH) return false;
  if (safePath === CLIENT_EVENT_REPORT_PATH) return false;
  if (safePath === WAIT_METRIC_REPORT_PATH) return false;
  if (safePath === INTERACTION_EVENT_REPORT_PATH) return false;
  if (safePath === PUBLIC_INTERACTION_EVENT_REPORT_PATH) return false;
  if (safePath === "/api/auth/me") return false;
  if (String(method || "GET").toUpperCase() === "GET" && !options.logGetUserEvent && options.trackGetInteraction !== true) {
    return false;
  }
  return typeof window.flowTrack === "function";
}

function reportApiInteraction(path, method, status, options = {}, detail = {}) {
  if (!shouldTrackApiInteraction(path, method, options)) return;
  const safePath = pathWithoutQuery(path);
  const context = typeof window.flowCurrentInteractionContext === "function"
    ? window.flowCurrentInteractionContext()
    : null;
  window.flowTrack(options.telemetryEventType === "download" ? "download" : "api_request", {
    interaction_id: context?.interaction_id,
    control_id: context?.control_id || `api:${String(method || "GET").toUpperCase()}:${safePath}`,
    control_label: context?.control_label || apiActionLabel(path, method),
    feature: context?.feature || "api",
    status: status || "ok",
    detail: {
      api_route: safePath,
      method: String(method || "GET").toUpperCase(),
      status_code: detail.status_code || 0,
      error_code: detail.error_code || "",
      cache_hit: Boolean(detail.cache_hit),
      shared_in_flight: Boolean(detail.shared_in_flight),
      source: options.telemetrySource || "foreground",
    },
  });
}

function apiLogTarget() {
  return window.flowLog?.append || window.appendAppLog || null;
}

function apiUserLog(message, kind = "info", title = "System") {
  const target = apiLogTarget();
  if (typeof target === "function") {
    target(message, kind, title);
  }
}

function apiFlowName(path) {
  const match = pathWithoutQuery(path).match(/^\/api\/allokering\/flow\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]).replace(/[-_]/g, " ") : "";
}

function apiActionLabel(path, method = "GET") {
  const safePath = pathWithoutQuery(path);
  const verb = String(method || "GET").toUpperCase();
  const flowName = apiFlowName(safePath);
  if (safePath === CLIENT_ERROR_REPORT_PATH) return "";
  if (safePath === CLIENT_EVENT_REPORT_PATH) return "";
  if (safePath === WAIT_METRIC_REPORT_PATH) return "";
  if (safePath === INTERACTION_EVENT_REPORT_PATH) return "";
  if (safePath === PUBLIC_INTERACTION_EVENT_REPORT_PATH) return "";
  if (safePath === "/api/auth/logout") return "Utloggning";
  if (safePath.startsWith("/api/assistant/chat")) return "Apphjälp";
  if (safePath.startsWith("/api/assistant/clear")) return "Apphjälpsdialog";
  if (safePath.startsWith("/api/query-data/plan")) return "Hämta data: plan";
  if (safePath.startsWith("/api/query-data/run")) return "Hämta data: körning";
  if (safePath.startsWith("/api/query-data/export/")) return "Hämta data: Excel";
  if (safePath.startsWith("/api/allokering/flow/")) return `Bearbeta: ${flowName || "flöde"}`;
  if (safePath.startsWith("/api/allokering/download/")) return "Bearbeta: CSV";
  if (safePath.startsWith("/api/allokering/open-excel/")) return "Bearbeta: Excel";
  if (safePath.startsWith("/api/coredata/files")) {
    const lowerPath = String(path || "").toLowerCase();
    return lowerPath.includes("artikel_max") || lowerPath.includes("article_max") ? "Sammanställd data" : "Kärnfil";
  }
  if (safePath.startsWith("/api/productivity/files")) return "Produktivitetsfil";
  if (safePath.startsWith("/api/productivity/report")) return "Produktivitet";
  if (safePath === "/api/meta/uploads") return verb === "POST" ? "Meta-uppladdning" : "Meta";
  if (safePath.startsWith("/api/meta/shipment-observations")) return "Meta-sändningsanalys";
  if (/^\/api\/meta\/uploads\/\d+\/analyze$/.test(safePath)) return "Meta-analys";
  if (/^\/api\/meta\/uploads\/\d+\/content$/.test(safePath)) return "Meta-fil";
  if (/^\/api\/meta\/uploads\/\d+$/.test(safePath)) return verb === "DELETE" ? "Meta-fil borttagen" : "Meta-fil";
  if (safePath.startsWith("/api/schedule/cells")) return "Bemanning: flera celler";
  if (safePath.startsWith("/api/schedule/cell")) return "Bemanning: cell";
  if (safePath.startsWith("/api/schedule/copy")) return "Bemanning: kopiera dag";
  if (safePath.startsWith("/api/schedule/clear")) return "Bemanning: rensa dag";
  if (safePath.startsWith("/api/schedule/hours/restore")) return "Bemanning: ångra/gör om";
  if (safePath.startsWith("/api/overview/days")) return "Översikt: flera dagar";
  if (safePath.startsWith("/api/overview/day")) return "Översikt: dag";
  if (safePath.startsWith("/api/persons/import-template")) return "Personimportmall";
  if (safePath.startsWith("/api/persons/import")) return "Personimport";
  if (safePath.startsWith("/api/persons/sort-order")) return "Personsortering";
  if (/^\/api\/persons\/\d+\/schedule$/.test(safePath)) return "Personschema";
  if (safePath.startsWith("/api/persons")) return verb === "DELETE" ? "Person borttagen" : verb === "POST" ? "Person skapad" : "Person uppdaterad";
  if (safePath.startsWith("/api/users/import-template")) return "Användarimportmall";
  if (safePath.startsWith("/api/users/import")) return "Användarimport";
  if (safePath.startsWith("/api/users")) return verb === "DELETE" ? "Användare borttagen" : verb === "POST" ? "Användare skapad" : "Användare uppdaterad";
  if (safePath.startsWith("/api/activities/import-template")) return "Aktivitetsimportmall";
  if (safePath.startsWith("/api/activities/import")) return "Aktivitetsimport";
  if (safePath.startsWith("/api/activities")) return verb === "DELETE" ? "Aktivitet borttagen" : verb === "POST" ? "Aktivitet skapad" : "Aktivitet uppdaterad";
  if (safePath.startsWith("/api/businesses")) return verb === "POST" ? "Verksamhet skapad" : "Verksamhet uppdaterad";
  if (safePath.startsWith("/api/areas")) return verb === "DELETE" ? "Område borttaget" : verb === "POST" ? "Område skapat" : "Område uppdaterat";
  if (safePath.startsWith("/api/settings/sidebar")) return "Menyinställning";
  if (safePath.startsWith("/api/settings/role-access")) return "Vybehörighet";
  if (safePath.startsWith("/api/settings")) return "Inställning";
  return `${verb} ${safePath}`;
}

function apiResultSummary(body) {
  if (!body || typeof body !== "object") return "";
  const parts = [];
  const labels = {
    created: "skapade",
    updated: "uppdaterade",
    deleted: "borttagna",
    cleared: "rensade",
    copied: "kopierade",
    written: "skrivna",
    skipped: "hoppade",
  };
  for (const key of Object.keys(labels)) {
    if (body[key] != null) parts.push(`${labels[key]}: ${body[key]}`);
  }
  if (Array.isArray(body.saved)) parts.push(`sparade: ${body.saved.length}`);
  if (Array.isArray(body.unknown) && body.unknown.length) parts.push(`okända: ${body.unknown.length}`);
  if (body.status?.files && typeof body.status.files === "object") {
    const uploaded = Object.values(body.status.files).filter((entry) => entry?.uploaded).length;
    parts.push(`filer: ${uploaded}`);
  }
  if (body.summary && typeof body.summary === "object") {
    const summaryParts = Object.entries(body.summary).slice(0, 3).map(([key, value]) => `${key}: ${value}`);
    parts.push(...summaryParts);
  }
  if (!parts.length && Array.isArray(body.tables)) parts.push(`tabeller: ${body.tables.length}`);
  return parts.length ? ` (${parts.join(", ")})` : "";
}

function shouldLogApiUserEvent(path, method, options = {}) {
  if (options.logUserEvent === false) return false;
  const safePath = pathWithoutQuery(path);
  if (safePath === CLIENT_ERROR_REPORT_PATH) return false;
  if (safePath === CLIENT_EVENT_REPORT_PATH) return false;
  if (safePath === WAIT_METRIC_REPORT_PATH) return false;
  if (safePath === INTERACTION_EVENT_REPORT_PATH) return false;
  if (safePath === PUBLIC_INTERACTION_EVENT_REPORT_PATH) return false;
  if (safePath === "/api/auth/me") return false;
  if (String(method || "GET").toUpperCase() === "GET") return Boolean(options.logGetUserEvent);
  return true;
}

function logApiSuccess(path, method, body, options = {}) {
  if (!shouldLogApiUserEvent(path, method, options) || options.logSuccess === false) return;
  const label = options.logLabel || apiActionLabel(path, method);
  if (!label) return;
  apiUserLog(`${label} klar${apiResultSummary(body)}`, "success", "Klart");
}

function logApiFailure(path, method, error, options = {}) {
  if (!shouldLogApiUserEvent(path, method, options) || options.logFailure === false) return;
  const label = options.logLabel || apiActionLabel(path, method);
  if (!label) return;
  apiUserLog(`${label} misslyckades${error?.message ? `: ${error.message}` : ""}`, "error", "Fel");
}

async function request(path, options = {}) {
  const {
    headers = {},
    cacheTtlMs = 0,
    skipCache = false,
    logLabel = "",
    logUserEvent = undefined,
    logGetUserEvent = false,
    logSuccess = true,
    logFailure = true,
    telemetryEnabled = true,
    telemetryEventType = "api_request",
    telemetrySource = "",
    ...rest
  } = options;
  const logOptions = { logLabel, logUserEvent, logGetUserEvent, logSuccess, logFailure };
  const telemetryOptions = { telemetryEnabled, telemetryEventType, telemetrySource };
  const interactionOptions = { ...options, logGetUserEvent, telemetryEventType, telemetrySource };
  const isFormData = typeof FormData !== "undefined" && rest.body instanceof FormData;
  const requestHeaders = isFormData ? headers : { "Content-Type": "application/json", ...headers };
  const method = String(rest.method || "GET").toUpperCase();
  const useGetCache = method === "GET" && !skipCache;
  const useSharedInFlight = useGetCache && !rest.signal;
  const requestCacheGeneration = apiGetCacheGeneration;
  const requestStartedAt = apiTelemetryNow();
  if (useGetCache) {
    const cached = readApiGetCache(path);
    if (cached !== null) {
      reportApiWaitMetric(path, method, requestStartedAt, "ok", telemetryOptions, { cache_hit: true });
      reportApiInteraction(path, method, "ok", interactionOptions, { cache_hit: true });
      return cached;
    }
    if (useSharedInFlight) {
      const inFlight = apiGetInFlight.get(apiCacheKey(path));
      if (inFlight) {
        const body = await inFlight;
        reportApiWaitMetric(path, method, requestStartedAt, "ok", telemetryOptions, { shared_in_flight: true });
        reportApiInteraction(path, method, "ok", interactionOptions, { shared_in_flight: true });
        return cloneApiCacheValue(body);
      }
    }
  }

  const run = async () => {
    let resp;
    try {
      resp = await fetch(path, {
        credentials: "include",
        headers: requestHeaders,
        ...rest,
      });
    } catch (error) {
      if (isAbortError(error)) throw error;
      const err = connectionError(path, error);
      reportApiError(path, {
        method,
        status: 0,
        error_code: "network_error",
        message: err.message,
      });
      reportApiWaitMetric(path, method, requestStartedAt, "error", telemetryOptions, {
        status_code: 0,
        error_code: "network_error",
      });
      reportApiInteraction(path, method, "error", interactionOptions, {
        status_code: 0,
        error_code: "network_error",
      });
      logApiFailure(path, method, err, logOptions);
      throw err;
    }

    if (resp.status === 204) {
      reportApiWaitMetric(path, method, requestStartedAt, "ok", telemetryOptions, { status_code: 204 });
      reportApiInteraction(path, method, "ok", interactionOptions, { status_code: 204 });
      logApiSuccess(path, method, null, logOptions);
      return null;
    }

    const ct = resp.headers.get("content-type") || "";
    const body = ct.includes("application/json") ? await resp.json() : await resp.text();

    if (resp.status === 401 && !isAuthPath(path)) {
      reportApiWaitMetric(path, method, requestStartedAt, "error", telemetryOptions, { status_code: 401 });
      if (!window.location.pathname.endsWith("/login.html")) {
        window.location.href = "/login.html";
      }
      throw new Error("Unauthorized");
    }

    if (resp.status === 403 && body?.detail === "password_setup_required" && !isAuthPath(path)) {
      reportApiWaitMetric(path, method, requestStartedAt, "error", telemetryOptions, { status_code: 403 });
      if (!window.location.pathname.endsWith("/set-password.html")) {
        window.location.href = "/set-password.html";
      }
      throw new Error("password_setup_required");
    }

    if (!resp.ok) {
      const err = new Error(errorMessageFromBody(body, resp.status));
      err.status = resp.status;
      err.body = body;
      reportApiError(path, {
        method,
        status: resp.status,
        body,
        message: err.message,
      });
      reportApiWaitMetric(path, method, requestStartedAt, "error", telemetryOptions, {
        status_code: resp.status,
        error_code: errorCodeForReport(body, resp.status),
      });
      reportApiInteraction(path, method, "error", interactionOptions, {
        status_code: resp.status,
        error_code: errorCodeForReport(body, resp.status),
      });
      logApiFailure(path, method, err, logOptions);
      throw err;
    }
    if (useGetCache && cacheTtlMs && requestCacheGeneration === apiGetCacheGeneration) {
      writeApiGetCache(path, body, cacheTtlMs);
    }
    reportApiWaitMetric(path, method, requestStartedAt, "ok", telemetryOptions, { status_code: resp.status });
    reportApiInteraction(path, method, "ok", interactionOptions, { status_code: resp.status });
    logApiSuccess(path, method, body, logOptions);
    return body;
  };

  if (!useSharedInFlight) return run();
  const promise = run().finally(() => apiGetInFlight.delete(apiCacheKey(path)));
  apiGetInFlight.set(apiCacheKey(path), promise);
  return cloneApiCacheValue(await promise);
}

async function prefetchGet(path, options = {}) {
  const cacheTtlMs = Number(options.cacheTtlMs || options.ttlMs || API_PREFETCH_DEFAULT_TTL_MS);
  const cached = readApiGetCache(path);
  if (cached !== null) return cached;
  return request(path, { ...options, method: "GET", cacheTtlMs });
}

function filenameFromContentDisposition(value) {
  const header = String(value || "");
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) return decodeURIComponent(utf8Match[1].trim().replace(/^"|"$/g, ""));
  const match = header.match(/filename="?([^";]+)"?/i);
  return match ? match[1].trim() : "";
}

function isHtmlContentType(value) {
  return String(value || "").toLowerCase().includes("text/html");
}

function clickDownloadLink(path, filename) {
  const link = document.createElement("a");
  link.href = path;
  link.download = filename || "download";
  link.rel = "noopener";
  link.dataset.trackIgnore = "true";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  setTimeout(() => link.remove(), 1000);
}

async function downloadDirect(path, fallbackFilename = "download") {
  const method = "GET";
  const requestStartedAt = apiTelemetryNow();
  const telemetryOptions = { telemetryEventType: "download", telemetrySource: "foreground" };
  const interactionOptions = { logGetUserEvent: true, telemetryEventType: "download", telemetrySource: "foreground", trackGetInteraction: true };
  let resp;
  try {
    resp = await fetch(path, { method: "HEAD", credentials: "include" });
  } catch (error) {
    if (isAbortError(error)) throw error;
    const err = connectionError(path, error);
    reportApiError(path, {
      method,
      status: 0,
      error_code: "network_error",
      message: err.message,
    });
    reportApiWaitMetric(path, method, requestStartedAt, "error", telemetryOptions, {
      status_code: 0,
      error_code: "network_error",
    });
    reportApiInteraction(path, method, "error", interactionOptions, {
      status_code: 0,
      error_code: "network_error",
    });
    logApiFailure(path, method, err, { logGetUserEvent: true });
    throw err;
  }

  if (resp.status === 401 && !isAuthPath(path)) {
    reportApiWaitMetric(path, method, requestStartedAt, "error", telemetryOptions, { status_code: 401 });
    if (!window.location.pathname.endsWith("/login.html")) {
      window.location.href = "/login.html";
    }
    throw new Error("Unauthorized");
  }

  const ct = resp.headers.get("content-type") || "";
  if (!resp.ok || isHtmlContentType(ct)) {
    const err = new Error(resp.ok ? htmlErrorMessage(resp.status) : httpStatusLabel(resp.status));
    err.status = resp.status;
    reportApiError(path, {
      method,
      status: resp.status,
      body: isHtmlContentType(ct) ? "<html>" : null,
      message: err.message,
    });
    reportApiWaitMetric(path, method, requestStartedAt, "error", telemetryOptions, {
      status_code: resp.status,
      error_code: resp.ok ? "html_response" : `HTTP ${resp.status}`,
    });
    reportApiInteraction(path, method, "error", interactionOptions, {
      status_code: resp.status,
      error_code: resp.ok ? "html_response" : `HTTP ${resp.status}`,
    });
    logApiFailure(path, method, err, { logGetUserEvent: true });
    throw err;
  }

  const filename = filenameFromContentDisposition(resp.headers.get("content-disposition")) || fallbackFilename;
  clickDownloadLink(path, filename);
  reportApiWaitMetric(path, method, requestStartedAt, "ok", telemetryOptions, { status_code: resp.status });
  reportApiInteraction(path, method, "ok", interactionOptions, { status_code: resp.status });
  apiUserLog(`Nedladdning startad: ${apiActionLabel(path, method)} (${filename})`, "success", "Klart");
  return { filename, direct: true };
}

async function download(path, fallbackFilename = "download", options = {}) {
  if (options.direct) return downloadDirect(path, fallbackFilename);
  const method = "GET";
  const requestStartedAt = apiTelemetryNow();
  const telemetryOptions = { telemetryEventType: "download", telemetrySource: "foreground" };
  const interactionOptions = { logGetUserEvent: true, telemetryEventType: "download", telemetrySource: "foreground", trackGetInteraction: true };
  let resp;
  try {
    resp = await fetch(path, { credentials: "include" });
  } catch (error) {
    if (isAbortError(error)) throw error;
    const err = connectionError(path, error);
    reportApiError(path, {
      method,
      status: 0,
      error_code: "network_error",
      message: err.message,
    });
    reportApiWaitMetric(path, method, requestStartedAt, "error", telemetryOptions, {
      status_code: 0,
      error_code: "network_error",
    });
    reportApiInteraction(path, method, "error", interactionOptions, {
      status_code: 0,
      error_code: "network_error",
    });
    logApiFailure(path, method, err, { logGetUserEvent: true });
    throw err;
  }

  if (resp.status === 401 && !isAuthPath(path)) {
    reportApiWaitMetric(path, method, requestStartedAt, "error", telemetryOptions, { status_code: 401 });
    if (!window.location.pathname.endsWith("/login.html")) {
      window.location.href = "/login.html";
    }
    throw new Error("Unauthorized");
  }

  const ct = resp.headers.get("content-type") || "";
  if (!resp.ok) {
    const body = ct.includes("application/json") ? await resp.json() : await resp.text();
    const err = new Error(errorMessageFromBody(body, resp.status));
    err.status = resp.status;
    err.body = body;
    reportApiError(path, {
      method,
      status: resp.status,
      body,
      message: err.message,
    });
    reportApiWaitMetric(path, method, requestStartedAt, "error", telemetryOptions, {
      status_code: resp.status,
      error_code: errorCodeForReport(body, resp.status),
    });
    reportApiInteraction(path, method, "error", interactionOptions, {
      status_code: resp.status,
      error_code: errorCodeForReport(body, resp.status),
    });
    logApiFailure(path, method, err, { logGetUserEvent: true });
    throw err;
  }

  const blob = await resp.blob();
  const filename = filenameFromContentDisposition(resp.headers.get("content-disposition")) || fallbackFilename;
  const objectUrl = URL.createObjectURL(blob);
  clickDownloadLink(objectUrl, filename);
  setTimeout(() => {
    URL.revokeObjectURL(objectUrl);
  }, 1000);
  reportApiWaitMetric(path, method, requestStartedAt, "ok", telemetryOptions, { status_code: resp.status });
  reportApiInteraction(path, method, "ok", interactionOptions, { status_code: resp.status });
  apiUserLog(`Nedladdning klar: ${apiActionLabel(path, method)} (${filename})`, "success", "Klart");
  return { filename };
}

const api = {
  get: (path, options = {}) => request(path, options),
  post: (path, data, options = {}) =>
    request(path, { ...options, method: "POST", body: JSON.stringify(data) }).finally(() => clearApiGetCache()),
  postForm: (path, formData, options = {}) =>
    request(path, { ...options, method: "POST", body: formData }).finally(() => clearApiGetCache()),
  postFile: (path, file, options = {}) => {
    const headers = {
      "Content-Type": file?.type || "application/octet-stream",
      ...(options.headers || {}),
    };
    return request(path, { ...options, method: "POST", headers, body: file }).finally(() => clearApiGetCache());
  },
  put: (path, data, options = {}) =>
    request(path, { ...options, method: "PUT", body: JSON.stringify(data) }).finally(() => clearApiGetCache()),
  del: (path, options = {}) => request(path, { ...options, method: "DELETE" }).finally(() => clearApiGetCache()),
  prefetchGet,
  clearGetCache: clearApiGetCache,
  download,
  reportClientEvent,
};

window.api = api;
window.reportApiError = reportApiError;
window.reportClientEvent = reportClientEvent;

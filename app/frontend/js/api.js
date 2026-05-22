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
  if (typeof body === "string" && body.trim()) return body;
  return `HTTP ${status}`;
}

const CLIENT_ERROR_REPORT_PATH = "/api/audit/client-error";

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

function errorDetailForReport(body) {
  const detail = body?.detail ?? body?.error;
  if (typeof detail === "string") return truncateErrorText(detail);
  if (Array.isArray(detail)) return `${detail.length} valideringsfel`;
  if (detail && typeof detail === "object") {
    if (typeof detail.message === "string") return truncateErrorText(detail.message);
    const keys = Object.keys(detail).slice(0, 6).join(", ");
    return keys ? `Detaljfält: ${keys}` : null;
  }
  if (typeof body === "string") return truncateErrorText(body);
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
  if (safePath === "/api/auth/me") return false;
  if (status === 401) return false;
  return true;
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
    detail: errorDetailForReport(details.body) || truncateErrorText(details.detail),
    page_path: pathWithoutQuery(window.location?.pathname || "/"),
  };
  const body = JSON.stringify(payload);
  fetch(CLIENT_ERROR_REPORT_PATH, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: body.length < 60000,
  }).catch(() => {});
}

async function request(path, options = {}) {
  const { headers = {}, ...rest } = options;
  const isFormData = typeof FormData !== "undefined" && rest.body instanceof FormData;
  const requestHeaders = isFormData ? headers : { "Content-Type": "application/json", ...headers };
  const method = String(rest.method || "GET").toUpperCase();

  let resp;
  try {
    resp = await fetch(path, {
      credentials: "include",
      headers: requestHeaders,
      ...rest,
    });
  } catch (error) {
    const err = connectionError(path, error);
    reportApiError(path, {
      method,
      status: 0,
      error_code: "network_error",
      message: err.message,
    });
    throw err;
  }

  if (resp.status === 204) return null;

  const ct = resp.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await resp.json() : await resp.text();

  if (resp.status === 401 && !isAuthPath(path)) {
    if (!window.location.pathname.endsWith("/login.html")) {
      window.location.href = "/login.html";
    }
    throw new Error("Unauthorized");
  }

  if (resp.status === 403 && body?.detail === "password_setup_required" && !isAuthPath(path)) {
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
    throw err;
  }
  return body;
}

function filenameFromContentDisposition(value) {
  const header = String(value || "");
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) return decodeURIComponent(utf8Match[1].trim().replace(/^"|"$/g, ""));
  const match = header.match(/filename="?([^";]+)"?/i);
  return match ? match[1].trim() : "";
}

async function download(path, fallbackFilename = "download") {
  const method = "GET";
  let resp;
  try {
    resp = await fetch(path, { credentials: "include" });
  } catch (error) {
    const err = connectionError(path, error);
    reportApiError(path, {
      method,
      status: 0,
      error_code: "network_error",
      message: err.message,
    });
    throw err;
  }

  if (resp.status === 401 && !isAuthPath(path)) {
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
    throw err;
  }

  const blob = await resp.blob();
  const filename = filenameFromContentDisposition(resp.headers.get("content-disposition")) || fallbackFilename;
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  setTimeout(() => {
    URL.revokeObjectURL(objectUrl);
    link.remove();
  }, 1000);
  return { filename };
}

const api = {
  get: (path, options = {}) => request(path, options),
  post: (path, data, options = {}) =>
    request(path, { ...options, method: "POST", body: JSON.stringify(data) }),
  postForm: (path, formData, options = {}) =>
    request(path, { ...options, method: "POST", body: formData }),
  postFile: (path, file, options = {}) => {
    const headers = {
      "Content-Type": file?.type || "application/octet-stream",
      ...(options.headers || {}),
    };
    return request(path, { ...options, method: "POST", headers, body: file });
  },
  put: (path, data, options = {}) =>
    request(path, { ...options, method: "PUT", body: JSON.stringify(data) }),
  del: (path, options = {}) => request(path, { ...options, method: "DELETE" }),
  download,
};

window.api = api;

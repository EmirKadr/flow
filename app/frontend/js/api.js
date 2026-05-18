// Tunn fetch-wrapper. Skickar med session-cookie. 401 -> /login.html.

function isAuthPath(path) {
  return (
    path.startsWith("/api/auth/login") ||
    path.startsWith("/api/auth/me") ||
    path.startsWith("/api/auth/logout") ||
    path.startsWith("/api/auth/set-password")
  );
}

async function request(path, options = {}) {
  const { headers = {}, ...rest } = options;
  const isFormData = typeof FormData !== "undefined" && rest.body instanceof FormData;
  const requestHeaders = isFormData ? headers : { "Content-Type": "application/json", ...headers };

  const resp = await fetch(path, {
    credentials: "include",
    headers: requestHeaders,
    ...rest,
  });

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
    const err = new Error(body?.detail || body?.error || `HTTP ${resp.status}`);
    err.status = resp.status;
    err.body = body;
    throw err;
  }
  return body;
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
};

window.api = api;

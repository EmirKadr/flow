function allocationDefaultGetCacheTtlMs(path, options = {}) {
  if (options.skipCache || options.cacheTtlMs) return 0;
  const text = String(path || "");
  if (text.includes("/api/allokering/process-matrix")) return 30 * 1000;
  if (text.includes("/api/allokering/ytgenerering-map-layout")) return 30 * 1000;
  if (text.includes("/api/allokering/ytgenerering-location-options")) return 30 * 1000;
  if (text.includes("/api/allokering/flows")) return 60 * 1000;
  if (text.includes("/api/coredata/files")) return 20 * 1000;
  return 0;
}

async function allocationJson(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  if (method === "GET" && window.api?.get) {
    const cacheTtlMs = allocationDefaultGetCacheTtlMs(path, options);
    return await window.api.get(path, cacheTtlMs ? { ...options, cacheTtlMs } : options);
  }
  let response;
  try {
    response = await fetch(path, { credentials: "include", ...options });
  } catch (error) {
    window.reportApiError?.(path, {
      method,
      status: 0,
      error_code: "network_error",
      message: error?.message || "Kunde inte ansluta till servern.",
    });
    if (method !== "GET" && !String(path).includes("/detect")) {
      window.flowLog?.error(`Bearbeta-anrop misslyckades: ${error?.message || "nätverksfel"}`, "Fel");
    }
    throw error;
  }
  const ct = response.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    let message = body?.detail || body?.message || body?.error || `HTTP ${response.status}`;
    if (typeof message === "object") message = message.message || JSON.stringify(message);
    const error = new Error(message);
    error.status = response.status;
    error.body = body;
    window.reportApiError?.(path, {
      method,
      status: response.status,
      body,
      message,
    });
    if (method !== "GET" && !String(path).includes("/detect")) {
      window.flowLog?.error(`Bearbeta-anrop misslyckades: ${message}`, "Fel");
    }
    throw error;
  }
  if (method !== "GET") window.api?.clearGetCache?.();
  if (method !== "GET" && !String(path).includes("/detect")) {
    const label = String(path).includes("/flow/")
      ? `Bearbeta körd: ${decodeURIComponent(String(path).split("/flow/")[1] || "flöde")}`
      : String(path).includes("/open-excel")
        ? "Excel öppnad"
        : String(path).includes("/process-matrix")
          ? "Bearbeta-matris sparad"
          : String(path).includes("/ytgenerering-map-layout")
            ? "Ytkarta sparad"
            : "Bearbeta-anrop klart";
    const rows = Array.isArray(body?.tables) ? ` (${body.tables.length} tabeller)` : "";
    window.flowLog?.success(`${label}${rows}`, "Klart");
  }
  return body;
}

async function allocationPostForm(path, formData) {
  return allocationJson(path, { method: "POST", body: formData });
}

async function loadAllocationCoreDataStatus(options = {}) {
  try {
    const skipCache = options.skipCache === true;
    if (skipCache) {
      window.api?.clearGetCache?.((key) => String(key || "").includes("/api/coredata/files"));
    }
    allocationState.coredata = await allocationJson("/api/coredata/files", skipCache ? { skipCache: true } : {});
    cacheAllocationBootData();
  } catch (error) {
    console.warn("Kunde inte läsa kärnfiler.", error);
    allocationState.coredata = {};
  }
}

async function loadAllocationFlows() {
  const data = await allocationJson(`${ALLOCATION_API}/flows`);
  allocationState.flows = data.flows || [];
  allocationState.visibleFlows = allocationState.flows.filter((flow) => !ALLOCATION_HIDDEN_FLOW_IDS.has(flow.id));
  cacheAllocationBootData();
}

async function loadAllocationProcessMatrix() {
  if (allocationState.page !== "process" && !canViewAllocationProcessMatrix()) return;
  allocationState.processMatrixLoading = true;
  allocationState.processMatrixError = "";
  try {
    const query = allocationScopedQuery({
      fallbackToUser: allocationState.page === "settings",
      includeAreaFocus: true,
    });
    const data = await allocationJson(`${ALLOCATION_API}/process-matrix${query}`);
    allocationState.processMatrix = normalizeAllocationProcessMatrix(data);
    cacheAllocationBootData();
  } catch (error) {
    console.warn("Kunde inte lasa Bearbeta-matris.", error);
    allocationState.processMatrixError = error?.message || "Kunde inte läsa Bearbeta-matris.";
    if (!allocationState.processMatrix) allocationState.processMatrix = allocationProcessFallbackMatrix();
  } finally {
    allocationState.processMatrixLoading = false;
  }
}


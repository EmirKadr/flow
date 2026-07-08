// @ts-check
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

function allocationRandomTraceHex(bytes) {
  const array = new Uint8Array(bytes);
  if (window.crypto?.getRandomValues) {
    window.crypto.getRandomValues(array);
  } else {
    for (let index = 0; index < bytes; index += 1) array[index] = Math.floor(Math.random() * 256);
  }
  return Array.from(array, (value) => value.toString(16).padStart(2, "0")).join("");
}

function allocationTraceParent() {
  let traceId = allocationRandomTraceHex(16);
  if (/^0+$/.test(traceId)) traceId = `1${traceId.slice(1)}`;
  let spanId = allocationRandomTraceHex(8);
  if (/^0+$/.test(spanId)) spanId = `1${spanId.slice(1)}`;
  return `00-${traceId}-${spanId}-01`;
}

function allocationTraceId(traceparent) {
  const match = String(traceparent || "").toLowerCase().match(/^00-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$/);
  return match ? match[1] : "";
}

function allocationDebugSuffix(error) {
  const traceId = error?.trace_id || "";
  const operationId = error?.operation_id || "";
  if (operationId && traceId && operationId !== traceId) return ` Felsöknings-ID: ${operationId} / ${traceId}`;
  if (operationId || traceId) return ` Felsöknings-ID: ${operationId || traceId}`;
  return "";
}

async function allocationJson(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  if (method === "GET" && window.api?.get) {
    const cacheTtlMs = allocationDefaultGetCacheTtlMs(path, options);
    return await window.api.get(path, cacheTtlMs ? { ...options, cacheTtlMs } : options);
  }
  const traceparent = allocationTraceParent();
  const traceId = allocationTraceId(traceparent);
  const operationId = window.createFlowOperationId?.(`allocation-${method.toLowerCase()}`) || traceId;
  const headers = {
    ...(options.headers || {}),
    traceparent,
    "X-Flow-Trace-Id": traceId,
    "X-Flow-Operation-Id": operationId,
  };
  let response;
  try {
    response = await fetch(path, { credentials: "include", ...options, headers });
  } catch (error) {
    window.reportApiError?.(path, {
      method,
      status: 0,
      error_code: "network_error",
      message: error?.message || "Kunde inte ansluta till servern.",
      trace_id: traceId,
      operation_id: operationId,
    });
    if (error && typeof error === "object") {
      error.trace_id = traceId;
      error.operation_id = operationId;
    }
    if (method !== "GET" && !String(path).includes("/detect")) {
      window.flowLog?.error(`Bearbeta-anrop misslyckades: ${error?.message || "nätverksfel"}${allocationDebugSuffix(error)}`, "Fel");
    }
    throw error;
  }
  const responseTraceId = response.headers.get("x-flow-trace-id") || traceId;
  const responseOperationId = response.headers.get("x-flow-operation-id") || operationId;
  window.flowLastTraceContext = { trace_id: responseTraceId, operation_id: responseOperationId, at: Date.now() };
  const ct = response.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    let message = body?.detail || body?.message || body?.error || `HTTP ${response.status}`;
    if (typeof message === "object") message = message.message || JSON.stringify(message);
    const error = /** @type {Error & { status?: number, body?: unknown, trace_id?: string, operation_id?: string }} */ (new Error(message));
    error.status = response.status;
    error.body = body;
    error.trace_id = responseTraceId;
    error.operation_id = responseOperationId;
    window.reportApiError?.(path, {
      method,
      status: response.status,
      body,
      message,
      trace_id: responseTraceId,
      operation_id: responseOperationId,
    });
    if (method !== "GET" && !String(path).includes("/detect")) {
      window.flowLog?.error(`Bearbeta-anrop misslyckades: ${message}${allocationDebugSuffix(error)}`, "Fel");
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


// Utdelad ur allocation/state.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter state.js via <script>-tagg.

function allocationProcessMatrixData() {
  return allocationState.processMatrix || allocationProcessFallbackMatrix();
}

function allocationProcessRule(code = allocationProcessAreaCode()) {
  const matrix = allocationProcessMatrixData().matrix || {};
  return matrix[code] || matrix.DEFAULT || normalizeAllocationProcessRule(ALLOCATION_PROCESS_MATRIX.DEFAULT);
}

function allocationFlowVisibleForCurrentArea(flow) {
  if (allocationState.page !== "process") return true;
  const visibleFlowIds = allocationProcessRule().visibleFlowIds;
  return !Array.isArray(visibleFlowIds) || visibleFlowIds.includes(flow.id);
}

function allocationFlowsForCurrentView() {
  return allocationState.visibleFlows.filter((flow) => allocationFlowVisibleForCurrentArea(flow));
}

function normalizeAllocationFilterOperator(value) {
  const text = String(value || "").trim();
  if (ALLOCATION_FILTER_OPERATORS.some((item) => item.value === text)) return text;
  if (text === "=" || text.toLowerCase() === "eq") return "EQ";
  if (text === "!=" || text.toLowerCase() === "ne") return "NE";
  if (text === ">") return "GT";
  if (text === ">=") return "GTE";
  if (text === "<") return "LT";
  if (text === "<=") return "LTE";
  if (text.toLowerCase() === "between") return "Between";
  if (["in", "terms"].includes(text.toLowerCase())) return "In";
  if (["not in", "not_in", "notin"].includes(text.toLowerCase())) return "NotIn";
  return "EQ";
}

function allocationFilterValues(value) {
  if (Array.isArray(value)) return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  return String(value ?? "")
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeAllocationFilterCondition(raw = {}) {
  const column = String(raw.column || raw.id || raw.field || "").trim();
  const columnLabel = String(raw.columnLabel || raw.label || "").trim();
  const operator = normalizeAllocationFilterOperator(raw.operator);
  if (!column && !columnLabel) return null;
  let value = raw.value;
  if (operator === "In" || operator === "NotIn") value = allocationFilterValues(value);
  else if (operator === "Between") value = allocationFilterValues(value).slice(0, 2);
  else value = String(value ?? "").trim();
  if (Array.isArray(value) ? value.length === 0 : value === "") return null;
  if (operator === "Between" && value.length < 2) return null;
  return { column, columnLabel, operator, value };
}

function normalizeAllocationSourceMode(value) {
  const text = String(value || "").trim().toLowerCase();
  if (["api", "external", "hamta", "hämta"].includes(text)) return "api";
  if (["upload", "uploaded", "file", "local", "uppladdning", "fil"].includes(text)) return "upload";
  return "";
}

function normalizeAllocationSourceModes(value = {}) {
  if (!value || typeof value !== "object") return {};
  const modes = {};
  for (const [fileKey, rawMode] of Object.entries(value)) {
    const key = String(fileKey || "").trim();
    const mode = normalizeAllocationSourceMode(rawMode);
    if (key && mode) modes[key] = mode;
  }
  return modes;
}

function normalizeAllocationFilterProfile(profile = {}) {
  const rawFlows = profile && typeof profile === "object" && profile.flows && typeof profile.flows === "object"
    ? profile.flows
    : {};
  const flows = {};
  for (const [flowId, flowData] of Object.entries(rawFlows)) {
    const flowPayload = {};
    const sources = normalizeAllocationSourceModes(flowData?.sources || flowData?.sourceModes || {});
    if (Object.keys(sources).length) flowPayload.sources = sources;
    const files = {};
    const rawFiles = flowData?.files && typeof flowData.files === "object" ? flowData.files : {};
    for (const [fileKey, conditions] of Object.entries(rawFiles)) {
      const normalized = (Array.isArray(conditions) ? conditions : [])
        .map(normalizeAllocationFilterCondition)
        .filter(Boolean);
      if (normalized.length) files[fileKey] = normalized;
    }
    if (Object.keys(files).length) flowPayload.files = files;
    if (flowId === "ytgenerering") {
      const rawSettings = flowData?.settings && typeof flowData.settings === "object" ? flowData.settings : {};
      const rawYtgenerering = rawSettings.ytgenerering || flowData?.ytgenerering || null;
      if (rawYtgenerering && typeof rawYtgenerering === "object") {
        flowPayload.settings = { ytgenerering: normalizeAllocationYtgenereringSettings(rawYtgenerering) };
      }
    }
    if (Object.keys(flowPayload).length) flows[flowId] = flowPayload;
  }
  return { version: 1, flows };
}

function cloneAllocationFilterProfile(profile = allocationState.filterProfile) {
  return normalizeAllocationFilterProfile(JSON.parse(JSON.stringify(profile || { version: 1, flows: {} })));
}

function allocationFilterProfileCount(profile = allocationState.filterProfile) {
  const normalized = normalizeAllocationFilterProfile(profile);
  return Object.entries(normalized.flows || {}).reduce((total, [flowId, flow]) => (
    total
    + Object.keys(flow.sources || {}).length
    + Object.values(flow.files || {}).reduce((sum, conditions) => sum + conditions.length, 0)
    + allocationYtgenereringSettingsCount(flowId, flow)
  ), 0);
}

function allocationFilterCountForFlow(flowId, profile = allocationState.filterProfile) {
  const flow = normalizeAllocationFilterProfile(profile).flows?.[flowId];
  return Object.keys(flow?.sources || {}).length
    + Object.values(flow?.files || {}).reduce((sum, conditions) => sum + conditions.length, 0)
    + allocationYtgenereringSettingsCount(flowId, flow);
}

function allocationFilterCountForSource(flowId, fileKey, profile = allocationState.filterProfile) {
  if (fileKey === ALLOCATION_YTGENERERING_SETTINGS_SOURCE) {
    return allocationYtgenereringSettingsCount(flowId, normalizeAllocationFilterProfile(profile).flows?.[flowId]);
  }
  const flow = normalizeAllocationFilterProfile(profile).flows?.[flowId];
  return (flow?.files?.[fileKey]?.length || 0) + (flow?.sources?.[fileKey] ? 1 : 0);
}

function allocationYtgenereringSettingsCount(flowId, flow) {
  if (flowId !== "ytgenerering") return 0;
  const settings = flow?.settings?.ytgenerering;
  return settings ? 1 : 0;
}

function allocationSourceModeForFile(flowId, fileKey, source = null, profile = allocationState.filterProfile) {
  const flow = normalizeAllocationFilterProfile(profile).flows?.[flowId];
  const saved = normalizeAllocationSourceMode(flow?.sources?.[fileKey]);
  if (saved) return saved;
  return source?.apiPreferred ? "api" : "upload";
}

function allocationSourceUsesUpload(flowId, fileKey, source = null, profile = allocationState.filterProfile) {
  return allocationSourceModeForFile(flowId, fileKey, source, profile) === "upload";
}

function allocationFlowNeedsStoredFiles(flow, profile = allocationState.filterProfile) {
  if (!flow?.id) return false;
  return (flow.inputs || []).some((input) =>
    input.type === "file" && allocationSourceUsesUpload(flow.id, allocationFileInputKey(input), input, profile)
  );
}

function allocationFlowNeedsCoreDataStatus(flow, profile = allocationState.filterProfile) {
  if (!flow?.id) return false;
  if ((flow.coredata || []).some((input) => allocationSourceUsesUpload(flow.id, input.key, input, profile))) {
    return true;
  }
  return (flow.inputs || []).some((input) => {
    if (input.type !== "file") return false;
    const key = allocationFileInputKey(input);
    return allocationSourceUsesUpload(flow.id, key, input, profile) && Boolean(allocationPersistentStatusKey(key));
  });
}

function allocationVisibleFlowsNeedStoredFiles(profile = allocationState.filterProfile) {
  return (allocationState.visibleFlows || []).some((flow) => allocationFlowNeedsStoredFiles(flow, profile));
}

function allocationVisibleFlowsNeedCoreDataStatus(profile = allocationState.filterProfile) {
  return (allocationState.visibleFlows || []).some((flow) => allocationFlowNeedsCoreDataStatus(flow, profile));
}

function allocationFilterSourcesForFlow(flow) {
  const sources = [];
  const seen = new Set();
  const addSource = (item, type) => {
    const key = String(item?.key || "").trim();
    if (!key || seen.has(key)) return;
    seen.add(key);
    const apiMeta = item.apiSource || flow?.apiSourceMetadata?.[item.apiSourceKey] || null;
    sources.push({
      key,
      label: item.label || allocationSlotLabel(key),
      type,
      required: Boolean(item.required),
      apiPreferred: Boolean(item.apiPreferred),
      apiSourceKey: item.apiSourceKey || "",
      columns: Array.isArray(apiMeta?.columns) ? apiMeta.columns : [],
    });
  };
  if (flow?.id === "ytgenerering") {
    addSource({ key: ALLOCATION_YTGENERERING_SETTINGS_SOURCE, label: "Ytgenerering" }, "settings");
  }
  (flow?.inputs || []).forEach((item) => {
    if (item.type === "file") addSource(item, "file");
  });
  (flow?.coredata || []).forEach((item) => addSource(item, "coredata"));
  return sources;
}

function allocationFilterConditionValueText(condition) {
  return Array.isArray(condition?.value) ? condition.value.join("\n") : String(condition?.value ?? "");
}

async function loadAllocationFilterProfile() {
  try {
    const data = await allocationJson(`${ALLOCATION_API}/filter-profile`);
    allocationState.filterProfile = normalizeAllocationFilterProfile(data.profile);
    allocationState.filterUsers = Array.isArray(data.users) ? data.users : [];
  } catch (error) {
    allocationState.filterProfile = { version: 1, flows: {} };
    allocationState.filterUsers = [];
    console.warn("Kunde inte lÃ¤sa Bearbeta-filtreringar.", error);
  }
}

async function saveAllocationFilterProfile(profile) {
  const data = await allocationJson(`${ALLOCATION_API}/filter-profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile: normalizeAllocationFilterProfile(profile) }),
  });
  allocationState.filterProfile = normalizeAllocationFilterProfile(data.profile);
  allocationState.filterUsers = Array.isArray(data.users) ? data.users : [];
}

async function importAllocationFilterProfile(userId) {
  const data = await allocationJson(`${ALLOCATION_API}/filter-profile/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: Number(userId) }),
  });
  allocationState.filterProfile = normalizeAllocationFilterProfile(data.profile);
  allocationState.filterUsers = Array.isArray(data.users) ? data.users : [];
}

function appendAllocationFilterProfile(formData) {
  const profile = normalizeAllocationFilterProfile(allocationState.filterProfile);
  if (allocationFilterProfileCount(profile) > 0) {
    formData.append(ALLOCATION_USER_FILTERS_PARAM, JSON.stringify(profile));
  }
}

function serializableAllocationValues(values) {
  const result = {};
  for (const [key, value] of Object.entries(values || {})) {
    if (value == null) continue;
    result[key] = String(value);
  }
  return result;
}

function persistAllocationWorkState(overrides = {}) {
  const key = allocationWorkStateKey();
  if (!key) return;
  const snapshot = {
    version: ALLOCATION_WORK_STATE_VERSION,
    page: allocationState.page,
    values: serializableAllocationValues(allocationState.values),
    status: allocationState.busyId ? "" : String(allocationState.status || ""),
    result: allocationState.busyId ? null : allocationState.result,
    carrierClusters: normalizeAllocationCarrierClusters(allocationState.carrierClusters),
    lastForecastSessionId: allocationState.lastForecastSessionId || "",
    lastForecastLabel: allocationState.lastForecastLabel || "",
    ...overrides,
  };
  try {
    sessionStorage.setItem(key, JSON.stringify(snapshot));
  } catch (error) {
    console.warn("Kunde inte spara lagerverktygets arbetslage.", error);
  }
}

function restoreAllocationWorkState() {
  const key = allocationWorkStateKey();
  if (!key) return;
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return;
    const snapshot = JSON.parse(raw);
    if (
      !snapshot
      || snapshot.version !== ALLOCATION_WORK_STATE_VERSION
      || snapshot.page !== allocationState.page
    ) {
      return;
    }
    if (snapshot.values && typeof snapshot.values === "object" && !Array.isArray(snapshot.values)) {
      allocationState.values = serializableAllocationValues(snapshot.values);
    }
    allocationState.status = typeof snapshot.status === "string" ? snapshot.status : "";
    allocationState.result = snapshot.result && typeof snapshot.result === "object" ? snapshot.result : null;
    allocationState.carrierClusters = normalizeAllocationCarrierClusters(snapshot.carrierClusters);
    allocationState.lastForecastSessionId = typeof snapshot.lastForecastSessionId === "string" ? snapshot.lastForecastSessionId : "";
    allocationState.lastForecastLabel = typeof snapshot.lastForecastLabel === "string" ? snapshot.lastForecastLabel : "";
  } catch (error) {
    try { sessionStorage.removeItem(key); } catch (e) {}
  }
}

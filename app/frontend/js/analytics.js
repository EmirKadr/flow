let currentUser = null;
let users = [];
let persons = [];
let activities = [];
let areas = [];
let currentHistoryMode = "history";

const ENTITY_LABELS = {
  schedule_cell: "Schema",
  person: "Person",
  person_schedule_template: "Standardschema",
  activity: "Aktivitet",
  area: "Område",
  user: "Användare",
  app_setting: "Inställning",
  client_error: "Felkod",
  data_fetch: "Hämta data",
  productivity_file: "Produktivitetsfil",
  allocation_flow: "Lagerverktyg",
};

const SETTING_LABELS = {
  lock_foreign_schedule_cells: "Lås bemanningsceller",
  sidebar_layout: "Meny",
  role_view_access: "Vybehörigheter",
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function formatTimestamp(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("sv-SE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function userLabel(entry) {
  if (entry.display_name) return `${entry.display_name} (${entry.username || "okänd"})`;
  if (entry.username) return entry.username;
  return "System";
}

function entityLabel(entityType) {
  return ENTITY_LABELS[entityType] || entityType || "";
}

function personName(personId) {
  const person = persons.find((item) => item.id === Number(personId));
  return person ? person.name : `Person #${personId}`;
}

function activityLabel(activityId) {
  if (activityId == null) return "-";
  const activity = activities.find((item) => item.id === Number(activityId));
  return activity ? activity.label : `Aktivitet #${activityId}`;
}

function areaName(areaId) {
  if (areaId == null) return "-";
  const area = areas.find((item) => item.id === Number(areaId));
  return area ? area.name : `Område #${areaId}`;
}

function formatFieldValue(key, value) {
  if (value == null) return "-";
  if (key === "home_area_id" || key === "area_id") return areaName(value);
  if (key === "home_activity_id" || key === "activity_id" || key === "summary_activity_id") return activityLabel(value);
  if (key === "is_active" || key === "is_off" || key === "empty_override") return value ? "Ja" : "Nej";
  if (Array.isArray(value)) return value.join(", ") || "-";
  return String(value);
}

function summarizeChanges(oldValue, newValue) {
  const before = oldValue || {};
  const after = newValue || {};
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)]));
  const changed = keys
    .filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
    .slice(0, 6);
  if (!changed.length) return "Ingen detalj";
  return changed
    .map((key) => `${key}: ${formatFieldValue(key, before[key])} -> ${formatFieldValue(key, after[key])}`)
    .join(" | ");
}

function settingLabel(key) {
  return SETTING_LABELS[key] || key || "Inställning";
}

function formatSettingValue(key, value) {
  if (!value) return "-";
  if (key === "lock_foreign_schedule_cells") {
    return value.lock_foreign_schedule_cells ? "Ja" : "Nej";
  }
  if (key === "sidebar_layout" && Array.isArray(value.items)) {
    return `${value.items.length} menyval`;
  }
  if (key === "role_view_access" && value.access && typeof value.access === "object") {
    return `${Object.keys(value.access).length} roller`;
  }
  return summarizeChanges(null, value);
}

function objectSummary(entry) {
  const snapshot = entry.new_value || entry.old_value || {};
  if (entry.entity_type === "person") return snapshot.name || `Person #${entry.entity_id}`;
  if (entry.entity_type === "activity") return snapshot.label || snapshot.code || `Aktivitet #${entry.entity_id}`;
  if (entry.entity_type === "area") return snapshot.name || snapshot.code || `Område #${entry.entity_id}`;
  if (entry.entity_type === "user") return snapshot.username || `Användare #${entry.entity_id}`;
  if (entry.entity_type === "app_setting") return settingLabel(snapshot.key);
  if (entry.entity_type === "schedule_cell") {
    const person = snapshot.person_id ? personName(snapshot.person_id) : `Cell #${entry.entity_id}`;
    const hour = snapshot.hour != null ? ` ${String(snapshot.hour).padStart(2, "0")}:00` : "";
    return person + hour;
  }
  if (entry.entity_type === "person_schedule_template") {
    const weekday = snapshot.weekday != null ? `Dag ${snapshot.weekday}` : `Mall #${entry.entity_id}`;
    return weekday;
  }
  if (entry.entity_type === "data_fetch") {
    return snapshot.view_label || snapshot.view || "Hämta data";
  }
  if (entry.entity_type === "client_error") {
    return snapshot.path || snapshot.page_path || "Felkod";
  }
  if (entry.entity_type === "productivity_file") {
    return snapshot.file_type || (snapshot.saved_types || []).join(", ") || "Produktivitetsfil";
  }
  if (entry.entity_type === "allocation_flow") {
    return snapshot.flow_id || "Lagerverktyg";
  }
  return `${entityLabel(entry.entity_type)} #${entry.entity_id}`;
}

function detailSummary(entry) {
  const snapshot = entry.new_value || entry.old_value || {};
  if (entry.entity_type === "schedule_cell") {
    const minuteStart = snapshot.minute_start ?? 0;
    const minuteEnd = snapshot.minute_end ?? 60;
    const activity = snapshot.activity_id == null ? "-" : activityLabel(snapshot.activity_id);
    const emptyFlag = snapshot.empty_override ? " (tom override)" : "";
    return `${String(snapshot.hour ?? "?").padStart(2, "0")}:00 ${minuteStart}-${minuteEnd}, aktivitet: ${activity}${emptyFlag}`;
  }
  if (entry.entity_type === "person_schedule_template") {
    if (snapshot.is_off) return `Dag ${snapshot.weekday}: ledig`;
    return `Dag ${snapshot.weekday}: ${snapshot.start_hour ?? "-"}-${snapshot.end_hour ?? "-"}`;
  }
  if (entry.entity_type === "data_fetch") {
    const parts = [];
    if (snapshot.message) parts.push(String(snapshot.message));
    if (snapshot.status_code) parts.push(`HTTP ${snapshot.status_code}`);
    if (snapshot.error_id) parts.push(`Fel-id ${snapshot.error_id}`);
    if (snapshot.total_rows != null) parts.push(`${snapshot.total_rows} rader`);
    return parts.join(" | ") || "Hämta data";
  }
  if (entry.entity_type === "client_error") {
    const parts = [];
    if (snapshot.error_code) parts.push(String(snapshot.error_code));
    if (snapshot.status_code != null) parts.push(`HTTP ${snapshot.status_code}`);
    if (snapshot.method && snapshot.path) parts.push(`${snapshot.method} ${snapshot.path}`);
    if (snapshot.message) parts.push(String(snapshot.message));
    if (snapshot.detail) parts.push(String(snapshot.detail));
    return parts.join(" | ") || "Felkod";
  }
  if (entry.entity_type === "app_setting") {
    const key = entry.new_value?.key || entry.old_value?.key;
    return `${formatSettingValue(key, entry.old_value?.value)} -> ${formatSettingValue(key, entry.new_value?.value)}`;
  }
  if (entry.entity_type === "productivity_file") {
    const parts = [];
    if (snapshot.saved_count != null) parts.push(`${snapshot.saved_count} sparade`);
    if (snapshot.saved_types?.length) parts.push(`Typ: ${snapshot.saved_types.join(", ")}`);
    if (snapshot.file_type) parts.push(`Typ: ${snapshot.file_type}`);
    if (snapshot.scope) parts.push(`Läge: ${snapshot.scope}`);
    if (snapshot.unknown_count) parts.push(`${snapshot.unknown_count} okända`);
    if (snapshot.attempted_count != null) parts.push(`${snapshot.attempted_count} försökta`);
    if (snapshot.status_code) parts.push(`HTTP ${snapshot.status_code}`);
    if (snapshot.error_type) parts.push(`Fel: ${snapshot.error_type}`);
    return parts.join(" | ") || "Produktivitetsfil";
  }
  if (entry.entity_type === "allocation_flow") {
    const parts = [];
    if (snapshot.business_code) parts.push(`Verksamhet: ${snapshot.business_code}`);
    if (snapshot.area_focus) parts.push(`Toggle: ${snapshot.area_focus}`);
    if (snapshot.stage) parts.push(`Steg: ${snapshot.stage}`);
    if (snapshot.file_keys?.length) parts.push(`${snapshot.file_keys.length} filslotar`);
    if (snapshot.param_keys?.length) parts.push(`${snapshot.param_keys.length} parametrar`);
    if (snapshot.table_count != null) parts.push(`${snapshot.table_count} tabeller`);
    if (snapshot.status_code) parts.push(`HTTP ${snapshot.status_code}`);
    if (snapshot.error_code) parts.push(`Felkod: ${snapshot.error_code}`);
    if (snapshot.error_type) parts.push(`Fel: ${snapshot.error_type}`);
    if (snapshot.message) parts.push(String(snapshot.message));
    if (snapshot.technical_message) parts.push(`Tekniskt: ${snapshot.technical_message}`);
    if (snapshot.filter_log?.length) parts.push(snapshot.filter_log.join(" | "));
    return parts.join(" | ") || "Lagerverktyg";
  }
  return summarizeChanges(entry.old_value, entry.new_value);
}

function periodStartIso(period) {
  const now = new Date();
  if (period === "24h") return new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
  if (period === "7d") return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString();
  if (period === "30d") return new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString();
  return null;
}

function currentParams(limit = 200) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));

  const period = document.getElementById("periodSelect").value;
  const fromAt = periodStartIso(period);
  if (fromAt) params.set("from_at", fromAt);

  const userId = document.getElementById("userFilter").value;
  if (userId) params.set("user_id", userId);

  const entityType = document.getElementById("entityFilter").value.trim();
  if (entityType) params.set("entity_type", entityType);

  const action = document.getElementById("actionFilter").value.trim();
  if (action) params.set("action", action);

  const entityId = document.getElementById("entityIdFilter").value.trim();
  if (entityId) params.set("entity_id", entityId);

  return params;
}

function renderBuckets(bodyId, buckets) {
  const body = document.getElementById(bodyId);
  body.innerHTML = "";
  if (!buckets.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="2" class="muted-cell">Inga poster</td>`;
    body.appendChild(tr);
    return;
  }

  buckets.forEach((bucket) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(bucket.label)}</td>
      <td>${escapeHtml(bucket.count)}</td>`;
    body.appendChild(tr);
  });
}

function renderSummary(summary) {
  document.getElementById("totalEvents").textContent = String(summary.total_events || 0);
  document.getElementById("recentEvents").textContent = String(summary.events_last_24h || 0);
  document.getElementById("uniqueUsers").textContent = String(summary.unique_users || 0);
  renderBuckets("topUsersBody", summary.top_users || []);
  renderBuckets("topActionsBody", summary.top_actions || []);
  renderBuckets("topEntitiesBody", summary.top_entities || []);
}

function renderAuditRows(entries) {
  const body = document.getElementById("auditBody");
  body.innerHTML = "";

  if (!entries.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="6" class="muted-cell">Ingen historik matchade filtret.</td>`;
    body.appendChild(tr);
    return;
  }

  entries.forEach((entry) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(formatTimestamp(entry.created_at))}</td>
      <td>${escapeHtml(userLabel(entry))}</td>
      <td>${escapeHtml(entityLabel(entry.entity_type))}</td>
      <td>${escapeHtml(entry.action)}</td>
      <td>${escapeHtml(objectSummary(entry))}</td>
      <td class="log-detail">${escapeHtml(detailSummary(entry))}</td>`;
    body.appendChild(tr);
  });
}

function setHistoryMode(mode) {
  currentHistoryMode = mode || "history";
  document.querySelectorAll("[data-history-mode]").forEach((button) => {
    const active = button.dataset.historyMode === currentHistoryMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll("[data-history-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.historyPanel !== currentHistoryMode;
  });
}

function statusLabel(value) {
  if (value == null) return "-";
  const status = Number(value);
  return Number.isFinite(status) && status > 0 ? `HTTP ${status}` : "-";
}

function renderErrorRows(entries) {
  const body = document.getElementById("recentErrorBody");
  body.innerHTML = "";

  if (!entries.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="7" class="muted-cell">Inga felkoder matchade filtret.</td>`;
    body.appendChild(tr);
    return;
  }

  entries.forEach((entry) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(formatTimestamp(entry.created_at))}</td>
      <td>${escapeHtml(userLabel(entry))}</td>
      <td>${escapeHtml(entry.error_code || entry.error_type || entry.action)}</td>
      <td>${escapeHtml(statusLabel(entry.status_code))}</td>
      <td>${escapeHtml(entry.path || "-")}</td>
      <td>${escapeHtml(entry.action || "-")}</td>
      <td class="log-detail">${escapeHtml(entry.message || "-")}</td>`;
    body.appendChild(tr);
  });
}

function renderErrorDashboard(summary) {
  document.getElementById("totalErrors").textContent = String(summary.total_errors || 0);
  document.getElementById("recentErrors").textContent = String(summary.events_last_24h || 0);
  document.getElementById("errorUsers").textContent = String(summary.unique_users || 0);
  const scanned = summary.scanned_events || 0;
  document.getElementById("errorScanLabel").textContent = summary.truncated
    ? `Unika användare (${scanned} skannade)`
    : "Unika användare";
  renderBuckets("topErrorCodesBody", summary.top_error_codes || []);
  renderBuckets("topErrorPathsBody", summary.top_paths || []);
  renderBuckets("topErrorActionsBody", summary.top_actions || []);
  renderErrorRows(summary.recent || []);
}

function fillUserFilter() {
  const select = document.getElementById("userFilter");
  select.innerHTML = '<option value="">Alla</option>';
  users.forEach((user) => {
    const option = document.createElement("option");
    option.value = String(user.id);
    option.textContent = user.display_name || user.username;
    select.appendChild(option);
  });
}

async function loadLookups() {
  const [usersResp, personsResp, activitiesResp, areasResp] = await Promise.all([
    api.get("/api/users"),
    api.get("/api/persons?include_inactive=true"),
    api.get("/api/activities?include_inactive=true"),
    api.get("/api/areas?include_inactive=true"),
  ]);
  users = usersResp;
  persons = personsResp;
  activities = activitiesResp;
  areas = areasResp;
  fillUserFilter();
}

async function refreshAnalytics() {
  const params = currentParams();
  const [summary, entries, errorSummary] = await Promise.all([
    api.get(`/api/audit/summary?${params.toString()}`),
    api.get(`/api/audit?${params.toString()}`),
    api.get(`/api/audit/errors?${params.toString()}`),
  ]);
  renderSummary(summary);
  renderAuditRows(entries);
  renderErrorDashboard(errorSummary);
}

(async () => {
  currentUser = await initPage("analytics", { requireSuperUser: true });
  if (!currentUser) return;

  await loadLookups();
  setHistoryMode(currentHistoryMode);
  await refreshAnalytics();

  document.getElementById("refreshAuditBtn").addEventListener("click", refreshAnalytics);
  document.querySelectorAll("[data-history-mode]").forEach((button) => {
    button.addEventListener("click", () => setHistoryMode(button.dataset.historyMode));
  });
  ["periodSelect", "userFilter", "entityFilter"].forEach((id) => {
    document.getElementById(id).addEventListener("change", refreshAnalytics);
  });
  ["actionFilter", "entityIdFilter"].forEach((id) => {
    document.getElementById(id).addEventListener("keydown", (event) => {
      if (event.key === "Enter") void refreshAnalytics();
    });
  });
})();

// @ts-check
// Sidans script körs i en IIFE så toppnivånamn (currentUser, areas, ...)
// inte kolliderar med andra sidors i TS globala scope. Ingen "use strict"
// — semantiken ska vara exakt densamma som före inpackningen.
(function () {
let metaItems = [];
let shipmentItems = [];
let currentUser = null;
let metaSearchTerm = "";
let metaSortState = { key: "updated_at", direction: "desc" };
const META_DOWNLOAD_CONCURRENCY = 1;
let activeMetaDownloads = 0;
const metaDownloadQueue = [];

const SHIPMENT_STATUS_LABELS = {
  needs_configuration: "LLM saknas",
  queued: "Köad",
  analyzing: "Analyserar",
  analyzed: "Klar",
  manual_review: "Kontrollera",
  analysis_failed: "Fel",
  pending_analysis: "Väntar",
};

// Ordning i status-dropdownen: de vanliga mänskliga besluten först, sedan
// system-/pipelinestatusar. Måste matcha EDITABLE_SHIPMENT_STATUSES i
// app/backend/routers/meta_uploads.py.
const SHIPMENT_STATUS_OPTIONS = [
  "analyzed",
  "manual_review",
  "queued",
  "pending_analysis",
  "analyzing",
  "analysis_failed",
  "needs_configuration",
];

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function formatTimestamp(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("sv-SE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatDuration(seconds) {
  if (seconds == null || seconds === "") return "-";
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "-";
  const total = Math.round(value);
  const sec = total % 60;
  const minutesTotal = Math.floor(total / 60);
  const min = minutesTotal % 60;
  const hours = Math.floor(minutesTotal / 60);
  if (hours > 0) return `${hours}:${String(min).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${min}:${String(sec).padStart(2, "0")}`;
}

function formatBytes(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value <= 0) return "-";
  if (value >= 1024 * 1024 * 1024) return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} kB`;
  return `${Math.round(value)} B`;
}

function shortHash(value) {
  return String(value || "").slice(0, 10);
}

function appendQuery(url, params = {}) {
  const entries = Object.entries(params).filter(([_key, value]) => value != null && value !== false && value !== "");
  if (!entries.length) return url;
  const query = new URLSearchParams();
  entries.forEach(([key, value]) => query.set(key, value === true ? "1" : String(value)));
  return `${url}${String(url).includes("?") ? "&" : "?"}${query.toString()}`;
}

function shipmentMediaFilename(item, fallback = "meta-fil") {
  const hash = String(item?.video_hash || "").slice(0, 10);
  return hash ? `${fallback}-${hash}` : fallback;
}

function setMetaDownloadButtonState(button, state) {
  if (!button) return;
  button.classList.toggle("is-download-queued", state === "queued");
  button.classList.toggle("is-download-running", state === "running");
  button.disabled = state === "queued" || state === "running";
}

function runNextMetaDownload() {
  if (activeMetaDownloads >= META_DOWNLOAD_CONCURRENCY || !metaDownloadQueue.length) return;
  const entry = metaDownloadQueue.shift();
  activeMetaDownloads += 1;
  setMetaDownloadButtonState(entry.button, "running");
  Promise.resolve()
    .then(entry.task)
    .catch((error) => {
      showToast(error.message || "Kunde inte ladda ner filen.", "error", 7000);
    })
    .finally(() => {
      activeMetaDownloads = Math.max(0, activeMetaDownloads - 1);
      setMetaDownloadButtonState(entry.button, "idle");
      runNextMetaDownload();
    });
}

function enqueueMetaDownload(task, button = null) {
  metaDownloadQueue.push({ task, button });
  setMetaDownloadButtonState(button, "queued");
  runNextMetaDownload();
}

async function downloadShipmentMedia(item, button = null) {
  const url = item?.video_url
    ? appendQuery(item.video_url, { download: "1", variant: "playable" })
    : null;
  if (!url) return;
  enqueueMetaDownload(
    () => api.download(url, shipmentMediaFilename(item, "meta-video")),
    button
  );
}

async function analyzeShipmentVideo(item, button = null) {
  if (!item?.media_upload_id) return;
  if (button) button.disabled = true;
  try {
    const response = await api.post(`/api/meta/uploads/${encodeURIComponent(item.media_upload_id)}/analyze`, {}, {
      logLabel: "Meta-analys",
    });
    if (response?.status === "needs_configuration") {
      showToast("Meta-analys saknar LLM-konfiguration.", "warn", 7000);
    } else if (response?.status === "analysis_failed") {
      showToast(response.message || "Meta-analysen misslyckades.", "error", 7000);
    } else {
      showToast("Meta-analys uppdaterad.", "success", 2500);
    }
    await loadMetaItems(false);
  } catch (error) {
    showToast(error.message || "Kunde inte analysera videon.", "error", 7000);
  } finally {
    if (button) button.disabled = false;
  }
}

async function changeShipmentStatus(item, newStatus, select = null) {
  if (!item?.id || !newStatus || newStatus === item.analysis_status) return;
  const previous = item.analysis_status || "pending_analysis";
  if (select) select.disabled = true;
  try {
    await api.patch(
      `/api/meta/shipment-observations/${encodeURIComponent(item.id)}/status`,
      { status: newStatus },
      { logLabel: "Meta-status" }
    );
    showToast(`Status ändrad till ${statusLabel(newStatus)}.`, "success", 2500);
    await loadMetaItems(false);
  } catch (error) {
    showToast(error.message || "Kunde inte ändra status.", "error", 7000);
    if (select) select.value = previous;
    if (select) select.disabled = false;
  }
}

function confirmDeleteShipment(item) {
  if (!item?.media_upload_id) return;
  document.getElementById("meta-delete-backdrop")?.remove();
  const videoTitle = item.video_filename || `Video ${item.media_upload_id}`;
  const backdrop = document.createElement("div");
  backdrop.id = "meta-delete-backdrop";
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="meta-delete-title">
      <h3 id="meta-delete-title">Radera video permanent</h3>
      <p>${escapeHtml(videoTitle)} och alla spår (sändningsrad och videofil) tas bort permanent. Detta går inte att ångra.</p>
      <div class="modal-actions">
        <button type="button" class="secondary" id="meta-delete-cancel">Avbryt</button>
        <button type="button" class="danger" id="meta-delete-confirm">Radera</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);

  const close = () => {
    document.removeEventListener("keydown", onKeydown);
    backdrop.remove();
  };
  const confirm = () => {
    close();
    void deleteShipmentUpload(item);
  };
  function onKeydown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "Enter") {
      event.preventDefault();
      confirm();
    }
  }

  document.getElementById("meta-delete-cancel")?.addEventListener("click", close);
  document.getElementById("meta-delete-confirm")?.addEventListener("click", confirm);
  document.addEventListener("keydown", onKeydown);
  document.getElementById("meta-delete-confirm")?.focus();
}

async function deleteShipmentUpload(item) {
  if (!item?.media_upload_id) return;
  try {
    await api.del(`/api/meta/uploads/${encodeURIComponent(item.media_upload_id)}`);
    showToast("Videon och alla spår raderades.", "success", 2500);
    await loadMetaItems(false);
  } catch (error) {
    showToast(error.message || "Kunde inte radera videon.", "error", 7000);
  }
}

function statusSelect(item) {
  const current = item.analysis_status || "pending_analysis";
  const values = SHIPMENT_STATUS_OPTIONS.includes(current)
    ? SHIPMENT_STATUS_OPTIONS
    : [current, ...SHIPMENT_STATUS_OPTIONS];
  const options = values
    .map((value) => `<option value="${escapeHtml(value)}"${value === current ? " selected" : ""}>${escapeHtml(statusLabel(value))}</option>`)
    .join("");
  return `<select class="meta-status-select" data-status-for="${escapeHtml(item.id)}" title="Byt status" aria-label="Byt status">${options}</select>`;
}

function renderSummary() {
  const total = metaItems.length;
  const videos = metaItems.filter((item) => item.media_type === "video").length;
  const images = metaItems.filter((item) => item.media_type === "image").length;
  const videoBytes = metaItems
    .filter((item) => item.media_type === "video")
    .reduce((sum, item) => sum + (Number(item.size_bytes) || 0), 0);
  const videoSize = videos ? ` (${formatBytes(videoBytes)})` : "";
  document.getElementById("metaSummary").textContent = `${total} filer - ${videos} videor${videoSize} - ${images} bilder`;
}

function statusLabel(status) {
  return SHIPMENT_STATUS_LABELS[status] || status || "-";
}

function iconButton({ className = "", dataset, label, icon, disabled = false }) {
  const dataAttrs = Object.entries(dataset || {})
    .map(([key, value]) => `data-${key}="${escapeHtml(value)}"`)
    .join(" ");
  return `<button type="button" class="meta-icon-button ${className}" ${dataAttrs} title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}" ${disabled ? "disabled" : ""}><span aria-hidden="true">${escapeHtml(icon)}</span></button>`;
}

function normalizedText(value) {
  if (Array.isArray(value)) return value.join(" ");
  return String(value ?? "").toLocaleLowerCase("sv-SE");
}

function shipmentSearchText(item) {
  return normalizedText([
    item.id,
    item.order_number,
    item.shipment_number,
    item.username,
    item.customer_name,
    item.pallet_id,
    ...(Array.isArray(item.deviations) ? item.deviations : []),
    item.uncertainty_notes,
    statusLabel(item.analysis_status),
    item.video_filename,
    item.video_original_filename,
    item.video_size_label,
    item.video_size_bytes,
    item.video_hash,
    item.record_hash,
  ]);
}

function sortValue(item, key) {
  if (key === "id") {
    const value = Number(item.id);
    return Number.isFinite(value) ? value : -1;
  }
  if (key === "deviations") return Array.isArray(item.deviations) ? item.deviations.join(", ") : "";
  if (key === "analysis_status") return statusLabel(item.analysis_status);
  if (key === "updated_at") {
    const parsed = Date.parse(item.updated_at || item.created_at || "");
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  if (key === "video_duration_seconds") {
    const value = Number(item.video_duration_seconds);
    return Number.isFinite(value) ? value : -1;
  }
  if (key === "video_size_bytes") {
    const value = Number(item.video_size_bytes);
    return Number.isFinite(value) ? value : -1;
  }
  return item[key] ?? "";
}

function compareShipmentItems(left, right) {
  const key = metaSortState.key;
  const direction = metaSortState.direction === "asc" ? 1 : -1;
  const leftValue = sortValue(left.item, key);
  const rightValue = sortValue(right.item, key);
  let result = 0;
  if (typeof leftValue === "number" && typeof rightValue === "number") {
    result = leftValue - rightValue;
  } else {
    result = String(leftValue || "").localeCompare(String(rightValue || ""), "sv-SE", {
      numeric: true,
      sensitivity: "base",
    });
  }
  if (result === 0) result = left.index - right.index;
  return result * direction;
}

function filteredShipmentItems() {
  const term = normalizedText(metaSearchTerm).trim();
  return shipmentItems
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => !term || shipmentSearchText(item).includes(term))
    .sort(compareShipmentItems)
    .map(({ item }) => item);
}

function updateExportButtons(visibleItems) {
  const exportFiltered = document.getElementById("metaExportFiltered");
  const exportAll = document.getElementById("metaExportAll");
  if (exportFiltered) /** @type {HTMLInputElement} */ (exportFiltered).disabled = !visibleItems.length;
  if (exportAll) /** @type {HTMLInputElement} */ (exportAll).disabled = !shipmentItems.length;
}

function renderSortIndicators() {
  document.querySelectorAll("[data-sort-key]").forEach((button) => {
    if (!/** @type {HTMLElement} */ (button).dataset.sortLabel) /** @type {HTMLElement} */ (button).dataset.sortLabel = button.textContent.trim();
    const active = /** @type {HTMLElement} */ (button).dataset.sortKey === metaSortState.key;
    button.classList.toggle("active", active);
    button.textContent = active
      ? `${/** @type {HTMLElement} */ (button).dataset.sortLabel} ${metaSortState.direction === "asc" ? "↑" : "↓"}`
      : /** @type {HTMLElement} */ (button).dataset.sortLabel;
    button.setAttribute("aria-label", active ? `${/** @type {HTMLElement} */ (button).dataset.sortLabel}, sorterad` : `Sortera på ${/** @type {HTMLElement} */ (button).dataset.sortLabel}`);
  });
}

function renderShipmentRows() {
  const tbody = document.getElementById("metaShipmentRows");
  const summary = document.getElementById("metaShipmentSummary");
  if (!tbody || !summary) return;
  const visibleItems = filteredShipmentItems();
  updateExportButtons(visibleItems);
  renderSortIndicators();
  summary.textContent = metaSearchTerm.trim()
    ? `${visibleItems.length} av ${shipmentItems.length} sändningsrader`
    : `${shipmentItems.length} sändningsrader`;
  if (!shipmentItems.length) {
    tbody.innerHTML = '<tr><td colspan="14" class="meta-admin-empty-cell">Inga sändningsanalyser ännu.</td></tr>';
    return;
  }
  if (!visibleItems.length) {
    tbody.innerHTML = '<tr><td colspan="14" class="meta-admin-empty-cell">Inga rader matchar sökningen.</td></tr>';
    return;
  }

  tbody.innerHTML = visibleItems.map((item) => {
    const deviations = Array.isArray(item.deviations) && item.deviations.length
      ? item.deviations.join(", ")
      : "-";
    const status = item.analysis_status || "pending_analysis";
    const hashTitle = `Video: ${item.video_hash || "-"}\nRad: ${item.record_hash || "-"}`;
    const videoTitle = item.video_filename || `Video ${item.media_upload_id || ""}`.trim();
    const videoHash = shortHash(item.video_hash);
    const videoSize = item.video_size_label || formatBytes(item.video_size_bytes);
    const videoDownloadLabel = `Ladda ner ${videoTitle || "video"}`;
    const timestamp = formatTimestamp(item.updated_at || item.created_at);
    const timestampTitle = `Skapad: ${formatTimestamp(item.created_at)}\nUppdaterad: ${formatTimestamp(item.updated_at)}`;
    const analysisId = item.id == null ? "-" : `#${item.id}`;
    return `
      <tr>
        <td class="meta-admin-observation-id">${escapeHtml(analysisId)}</td>
        <td>${escapeHtml(item.order_number || "")}</td>
        <td>${escapeHtml(item.shipment_number || "")}</td>
        <td>${escapeHtml(item.username || "")}</td>
        <td>${escapeHtml(item.customer_name || "")}</td>
        <td>${escapeHtml(item.pallet_id || "-")}</td>
        <td title="${escapeHtml(deviations)}">${escapeHtml(deviations)}</td>
        <td>
          <span class="meta-status-pill ${escapeHtml(status)}">${escapeHtml(statusLabel(status))}</span>
          ${item.uncertainty_notes ? `<div class="meta-admin-note" title="${escapeHtml(item.uncertainty_notes)}">Osäkert</div>` : ""}
        </td>
        <td class="meta-admin-timestamp" title="${escapeHtml(timestampTitle)}">${escapeHtml(timestamp)}</td>
        <td class="meta-admin-video-ref" title="${escapeHtml(item.video_original_filename || videoTitle || "-")}">
          <div class="meta-admin-primary">${escapeHtml(videoTitle || "-")}</div>
          <div class="meta-admin-subtle" title="${escapeHtml(item.video_hash || "-")}">#${escapeHtml(videoHash || "-")}</div>
        </td>
        <td data-duration-for="${escapeHtml(item.media_upload_id || "")}">${escapeHtml(formatDuration(item.video_duration_seconds))}</td>
        <td>${escapeHtml(videoSize)}</td>
        <td class="meta-admin-hash" title="${escapeHtml(hashTitle)}">${escapeHtml(shortHash(item.record_hash) || "-")}</td>
        <td>
          <div class="meta-admin-table-actions">
            ${statusSelect(item)}
            ${iconButton({ dataset: { "download-shipment-video": item.id }, label: videoDownloadLabel, icon: "↓", disabled: !item.video_url })}
            ${iconButton({ className: "primary", dataset: { "analyze-upload": item.id }, label: "Analysera", icon: "AI", disabled: status === "analyzing" })}
            ${iconButton({ className: "danger", dataset: { "delete-upload": item.id }, label: "Radera video permanent", icon: "🗑", disabled: !item.media_upload_id })}
          </div>
        </td>
      </tr>
    `;
  }).join("");

  tbody.querySelectorAll("[data-download-shipment-video]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = shipmentItems.find((entry) => Number(entry.id) === Number(/** @type {HTMLElement} */ (button).dataset.downloadShipmentVideo));
      void downloadShipmentMedia(item, button);
    });
  });
  tbody.querySelectorAll("[data-analyze-upload]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = shipmentItems.find((entry) => Number(entry.id) === Number(/** @type {HTMLElement} */ (button).dataset.analyzeUpload));
      void analyzeShipmentVideo(item, button);
    });
  });
  tbody.querySelectorAll("[data-delete-upload]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = shipmentItems.find((entry) => Number(entry.id) === Number(/** @type {HTMLElement} */ (button).dataset.deleteUpload));
      confirmDeleteShipment(item);
    });
  });
  tbody.querySelectorAll("[data-status-for]").forEach((select) => {
    select.addEventListener("change", () => {
      const element = /** @type {HTMLSelectElement} */ (select);
      const item = shipmentItems.find((entry) => Number(entry.id) === Number(element.dataset.statusFor));
      void changeShipmentStatus(item, element.value, element);
    });
  });
}

function renderMetaItems() {
  renderSummary();
  renderShipmentRows();
}

async function exportShipmentRows(filtered) {
  const params = new URLSearchParams();
  if (filtered) {
    const ids = filteredShipmentItems().map((item) => item.id).filter(Boolean);
    if (!ids.length) {
      showToast("Det finns inga filtrerade rader att exportera.", "warn", 4000);
      return;
    }
    params.set("ids", ids.join(","));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const filename = filtered ? "meta-sandningsanalys-filtrerad.xlsx" : "meta-sandningsanalys.xlsx";
  try {
    await api.download(`/api/meta/shipment-observations/export${suffix}`, filename);
  } catch (error) {
    showToast(error.message || "Kunde inte exportera sändningsanalysen.", "error", 7000);
  }
}

async function loadMetaItems(showDone = false) {
  const params = new URLSearchParams({ limit: "200" });
  const [response, shipmentResponse] = await Promise.all([
    api.get(`/api/meta/uploads?${params.toString()}`, {
      skipCache: true,
      logGetUserEvent: false,
    }),
    api.get("/api/meta/shipment-observations?limit=200", {
      skipCache: true,
      logGetUserEvent: false,
    }),
  ]);
  metaItems = response.items || [];
  shipmentItems = shipmentResponse.items || [];
  renderMetaItems();
  if (showDone) showToast("Meta uppdaterad.", "success", 2000);
}

document.addEventListener("DOMContentLoaded", async () => {
  currentUser = await initPage("meta", { requireSuperUser: true });
  if (!currentUser) return;

  document.getElementById("metaRefresh").addEventListener("click", () => loadMetaItems(true));
  document.getElementById("metaSearch").addEventListener("input", (event) => {
    metaSearchTerm = (event.target instanceof HTMLInputElement ? event.target.value : "") || "";
    renderShipmentRows();
  });
  document.querySelectorAll("[data-sort-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = /** @type {HTMLElement} */ (button).dataset.sortKey;
      if (metaSortState.key === key) {
        metaSortState = { key, direction: metaSortState.direction === "asc" ? "desc" : "asc" };
      } else {
        metaSortState = { key, direction: key === "updated_at" ? "desc" : "asc" };
      }
      renderShipmentRows();
    });
  });
  document.getElementById("metaExportFiltered").addEventListener("click", () => {
    void exportShipmentRows(true);
  });
  document.getElementById("metaExportAll").addEventListener("click", () => {
    void exportShipmentRows(false);
  });
  await loadMetaItems();
});
})();

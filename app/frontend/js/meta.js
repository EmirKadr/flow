let metaItems = [];
let shipmentItems = [];
let currentUser = null;
const mediaDurationById = new Map();
const pendingDurationLoads = new Set();

const SHIPMENT_STATUS_LABELS = {
  needs_configuration: "LLM saknas",
  queued: "Köad",
  analyzing: "Analyserar",
  analyzed: "Klar",
  manual_review: "Kontrollera",
  analysis_failed: "Fel",
  pending_analysis: "Väntar",
};

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

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} kB`;
  return `${value} B`;
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

function shortHash(value) {
  return String(value || "").slice(0, 10);
}

function mediaDurationSeconds(mediaId, fallback = null) {
  const key = Number(mediaId);
  if (mediaDurationById.has(key)) return mediaDurationById.get(key);
  return fallback;
}

function setKnownDuration(mediaId, seconds) {
  const key = Number(mediaId);
  if (!key || !Number.isFinite(Number(seconds))) return;
  mediaDurationById.set(key, Number(seconds));
  metaItems.forEach((item) => {
    if (Number(item.id) === key) item.duration_seconds = Number(seconds);
  });
  shipmentItems.forEach((item) => {
    if (Number(item.media_upload_id) === key) item.video_duration_seconds = Number(seconds);
  });
  document.querySelectorAll(`[data-duration-for="${key}"]`).forEach((node) => {
    node.textContent = formatDuration(seconds);
  });
}

function hydrateVideoDurations() {
  const candidates = new Map();
  metaItems.forEach((item) => {
    if (item.media_type === "video") {
      candidates.set(Number(item.id), {
        url: mediaUrl(item),
        duration: item.duration_seconds,
      });
    }
  });
  shipmentItems.forEach((item) => {
    if (item.media_upload_id && item.video_url) {
      candidates.set(Number(item.media_upload_id), {
        url: item.video_url,
        duration: item.video_duration_seconds,
      });
    }
  });

  candidates.forEach(({ url, duration }, mediaId) => {
    if (!mediaId) return;
    if (Number.isFinite(Number(duration))) {
      setKnownDuration(mediaId, Number(duration));
      return;
    }
    if (mediaDurationById.has(mediaId) || pendingDurationLoads.has(mediaId) || !url) return;
    pendingDurationLoads.add(mediaId);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.muted = true;
    video.playsInline = true;
    const cleanup = () => {
      pendingDurationLoads.delete(mediaId);
      video.removeAttribute("src");
      video.load();
    };
    video.addEventListener("loadedmetadata", () => {
      setKnownDuration(mediaId, video.duration);
      cleanup();
    }, { once: true });
    video.addEventListener("error", cleanup, { once: true });
    video.src = url;
  });
}

function appendQuery(url, params = {}) {
  const entries = Object.entries(params).filter(([_key, value]) => value != null && value !== false && value !== "");
  if (!entries.length) return url;
  const query = new URLSearchParams();
  entries.forEach(([key, value]) => query.set(key, value === true ? "1" : String(value)));
  return `${url}${String(url).includes("?") ? "&" : "?"}${query.toString()}`;
}

function mediaUrl(item, options = {}) {
  return appendQuery(`/api/meta/uploads/${encodeURIComponent(item.id)}/content`, {
    download: options.download ? "1" : "",
    variant: options.variant || "",
  });
}

function shipmentMediaFilename(item, fallback = "meta-fil") {
  const hash = String(item?.video_hash || item?.label_image_hash || "").slice(0, 10);
  return hash ? `${fallback}-${hash}` : fallback;
}

async function downloadMetaItem(item) {
  if (!item) return;
  try {
    await api.download(mediaUrl(item, { download: true }), item.filename || "meta-upload", { direct: true });
  } catch (error) {
    showToast(error.message || "Kunde inte ladda ner filen.", "error", 7000);
  }
}

async function downloadShipmentMedia(item, kind) {
  const baseUrl = kind === "label" ? item?.label_still_url : item?.video_url;
  const url = baseUrl
    ? appendQuery(baseUrl, { download: "1", variant: kind === "video" ? "playable" : "" })
    : null;
  if (!url) return;
  const fallback = kind === "label" ? "etikett.jpg" : "meta-video";
  try {
    await api.download(url, shipmentMediaFilename(item, fallback), { direct: true });
  } catch (error) {
    showToast(error.message || "Kunde inte ladda ner filen.", "error", 7000);
  }
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

async function deleteMetaItem(item, button = null) {
  if (!item) return;
  const filename = item.filename || item.original_filename || "filen";
  if (!confirm(`Radera ${filename}? Det går inte att ångra.`)) return;
  if (button) button.disabled = true;
  try {
    await api.del(`/api/meta/uploads/${encodeURIComponent(item.id)}`, {
      logLabel: "Meta-fil borttagen",
    });
    metaItems = metaItems.filter((entry) => Number(entry.id) !== Number(item.id));
    renderMetaItems();
    showToast("Meta-fil raderad.", "success", 2500);
  } catch (error) {
    if (button) button.disabled = false;
    showToast(error.message || "Kunde inte radera filen.", "error", 7000);
  }
}

function renderSummary() {
  const total = metaItems.length;
  const videos = metaItems.filter((item) => item.media_type === "video").length;
  const images = metaItems.filter((item) => item.media_type === "image").length;
  document.getElementById("metaSummary").textContent = `${total} filer - ${videos} videor - ${images} bilder`;
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

function renderShipmentRows() {
  const tbody = document.getElementById("metaShipmentRows");
  const summary = document.getElementById("metaShipmentSummary");
  if (!tbody || !summary) return;
  summary.textContent = `${shipmentItems.length} sändningsrader`;
  if (!shipmentItems.length) {
    tbody.innerHTML = '<tr><td colspan="12" class="meta-admin-empty-cell">Inga sändningsanalyser ännu.</td></tr>';
    return;
  }

  tbody.innerHTML = shipmentItems.map((item) => {
    const deviations = Array.isArray(item.deviations) && item.deviations.length
      ? item.deviations.join(", ")
      : "-";
    const status = item.analysis_status || "pending_analysis";
    const hashTitle = `Video: ${item.video_hash || "-"}\nRad: ${item.record_hash || "-"}`;
    const videoTitle = item.video_filename || `Video ${item.media_upload_id || ""}`.trim();
    const videoHash = shortHash(item.video_hash);
    const duration = mediaDurationSeconds(item.media_upload_id, item.video_duration_seconds);
    const videoDownloadLabel = `Ladda ner ${videoTitle || "video"}`;
    const labelDownloadLabel = `Ladda ner stillbild för ${videoTitle || "video"}`;
    return `
      <tr>
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
        <td class="meta-admin-video-ref" title="${escapeHtml(item.video_original_filename || videoTitle || "-")}">
          <div class="meta-admin-primary">${escapeHtml(videoTitle || "-")}</div>
          <div class="meta-admin-subtle" title="${escapeHtml(item.video_hash || "-")}">#${escapeHtml(videoHash || "-")}</div>
        </td>
        <td data-duration-for="${escapeHtml(item.media_upload_id || "")}">${escapeHtml(formatDuration(duration))}</td>
        <td>${item.label_still_url ? "Finns" : "-"}</td>
        <td class="meta-admin-hash" title="${escapeHtml(hashTitle)}">${escapeHtml(shortHash(item.record_hash) || "-")}</td>
        <td>
          <div class="meta-admin-table-actions">
            ${iconButton({ dataset: { "download-shipment-video": item.id }, label: videoDownloadLabel, icon: "↓", disabled: !item.video_url })}
            ${iconButton({ dataset: { "download-shipment-label": item.id }, label: labelDownloadLabel, icon: "▧", disabled: !item.label_still_url })}
            ${iconButton({ className: "primary", dataset: { "analyze-upload": item.id }, label: "Analysera", icon: "AI", disabled: status === "analyzing" })}
          </div>
        </td>
      </tr>
    `;
  }).join("");

  tbody.querySelectorAll("[data-download-shipment-video]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = shipmentItems.find((entry) => Number(entry.id) === Number(button.dataset.downloadShipmentVideo));
      void downloadShipmentMedia(item, "video");
    });
  });
  tbody.querySelectorAll("[data-download-shipment-label]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = shipmentItems.find((entry) => Number(entry.id) === Number(button.dataset.downloadShipmentLabel));
      void downloadShipmentMedia(item, "label");
    });
  });
  tbody.querySelectorAll("[data-analyze-upload]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = shipmentItems.find((entry) => Number(entry.id) === Number(button.dataset.analyzeUpload));
      void analyzeShipmentVideo(item, button);
    });
  });
}

function renderMetaItems() {
  const grid = document.getElementById("metaGrid");
  renderSummary();
  renderShipmentRows();
  if (!metaItems.length) {
    grid.innerHTML = '<div class="meta-admin-empty">Inga uppladdningar hittades.</div>';
    hydrateVideoDurations();
    return;
  }

  grid.innerHTML = metaItems.map((item) => {
    const isVideo = item.media_type === "video";
    const itemHash = shortHash(item.content_hash);
    const duration = mediaDurationSeconds(item.id, item.duration_seconds);
    return `
      <article class="meta-admin-card">
        <div class="meta-admin-thumb ${escapeHtml(item.media_type)}">
          <span>${isVideo ? "Video" : "Bild"}</span>
        </div>
        <div class="meta-admin-card-body">
          <h3 title="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</h3>
          <dl class="meta-admin-details">
            <div><dt>Uppladdad</dt><dd>${escapeHtml(formatTimestamp(item.created_at))}</dd></div>
            <div><dt>Storlek</dt><dd>${escapeHtml(item.size_label || formatBytes(item.size_bytes))}</dd></div>
            ${isVideo ? `<div><dt>Längd</dt><dd data-duration-for="${escapeHtml(item.id)}">${escapeHtml(formatDuration(duration))}</dd></div>` : ""}
            <div><dt>${isVideo ? "Video-ID" : "Hash"}</dt><dd title="${escapeHtml(item.content_hash || "-")}">#${escapeHtml(itemHash || "-")}</dd></div>
            <div><dt>Original</dt><dd title="${escapeHtml(item.original_filename)}">${escapeHtml(item.original_filename || "-")}</dd></div>
            <div><dt>Status</dt><dd>${escapeHtml(item.status || "-")}</dd></div>
          </dl>
          <div class="meta-admin-actions">
            ${iconButton({ className: "primary", dataset: { "open-media": item.id }, label: `Visa ${item.filename || "fil"}`, icon: "⤢" })}
            ${iconButton({ dataset: { "download-media": item.id }, label: `Ladda ner ${item.filename || "fil"}`, icon: "↓" })}
            ${iconButton({ className: "danger", dataset: { "delete-media": item.id }, label: `Radera ${item.filename || "fil"}`, icon: "×" })}
          </div>
        </div>
      </article>
    `;
  }).join("");

  grid.querySelectorAll("[data-open-media]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = metaItems.find((entry) => Number(entry.id) === Number(button.dataset.openMedia));
      if (item) openMediaModal(item);
    });
  });
  grid.querySelectorAll("[data-download-media]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = metaItems.find((entry) => Number(entry.id) === Number(button.dataset.downloadMedia));
      void downloadMetaItem(item);
    });
  });
  grid.querySelectorAll("[data-delete-media]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = metaItems.find((entry) => Number(entry.id) === Number(button.dataset.deleteMedia));
      void deleteMetaItem(item, button);
    });
  });
  hydrateVideoDurations();
}

function openMediaModal(item) {
  const isVideo = item.media_type === "video";
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal wide meta-preview-modal">
      <h2>${escapeHtml(item.filename)}</h2>
      <div class="meta-preview-frame">
        ${isVideo
          ? `<video src="${mediaUrl(item)}" controls autoplay playsinline></video>`
          : `<img src="${mediaUrl(item)}" alt="${escapeHtml(item.filename)}" />`}
      </div>
      <div class="actions">
        <button type="button" data-download-media="${item.id}">Ladda ner</button>
        <button type="button" class="primary" id="metaPreviewClose">Stäng</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);
  backdrop.querySelector("[data-download-media]")?.addEventListener("click", () => {
    void downloadMetaItem(item);
  });
  backdrop.querySelector("#metaPreviewClose").addEventListener("click", () => backdrop.remove());
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) backdrop.remove();
  });
}

async function loadMetaItems(showDone = false) {
  const mediaType = document.getElementById("metaMediaType").value;
  const params = new URLSearchParams({ limit: "200" });
  if (mediaType) params.set("media_type", mediaType);
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
  document.getElementById("metaMediaType").addEventListener("change", () => loadMetaItems());
  await loadMetaItems();
});

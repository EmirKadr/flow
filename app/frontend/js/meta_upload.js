const form = document.getElementById("metaUploadForm");
const input = document.getElementById("metaFiles");
const dropzone = document.getElementById("metaDropzone");
const fileList = document.getElementById("metaFileList");
const progressPanel = document.getElementById("metaProgress");
const progressLabel = document.getElementById("metaProgressLabel");
const progressPercent = document.getElementById("metaProgressPercent");
const progressBar = document.getElementById("metaProgressBar");
const progressRemaining = document.getElementById("metaProgressRemaining");
const statusBox = document.getElementById("metaStatus");

const META_UPLOAD_FILES_PER_REQUEST = 1;
let selectedFiles = [];
let fileUploadStates = [];
let uploading = false;
const selectedVideoDurations = new WeakMap();
let durationProbeGeneration = 0;

function formatBytes(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${bytes} B`;
}

function formatDuration(seconds) {
  if (seconds == null || seconds === "") return "";
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "";
  const total = Math.round(value);
  const sec = total % 60;
  const minutesTotal = Math.floor(total / 60);
  const min = minutesTotal % 60;
  const hours = Math.floor(minutesTotal / 60);
  if (hours > 0) return `${hours}:${String(min).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${min}:${String(sec).padStart(2, "0")}`;
}

function isVideoFile(file) {
  const type = String(file?.type || "").toLowerCase();
  const name = String(file?.name || "").toLowerCase();
  return type.startsWith("video/") || /\.(3g2|3gp|avi|m4v|mov|mp4|mpeg|mpg|webm)$/.test(name);
}

function setStatus(message, type = "") {
  statusBox.textContent = message || "";
  statusBox.className = `meta-status${type ? ` ${type}` : ""}`;
}

function totalSelectedBytes() {
  return selectedFiles.reduce((sum, file) => sum + (Number(file.size) || 0), 0);
}

function fileOffsets() {
  let offset = 0;
  return selectedFiles.map((file) => {
    const start = offset;
    offset += Number(file.size) || 0;
    return { start, end: offset };
  });
}

function renderFiles() {
  fileList.textContent = "";
  selectedFiles.forEach((file, index) => {
    const item = document.createElement("div");
    item.className = "meta-file-item";

    const name = document.createElement("div");
    name.className = "meta-file-name";
    name.textContent = file.name || "Namnlös fil";
    item.appendChild(name);

    const size = document.createElement("div");
    size.className = "meta-file-size";
    const duration = selectedVideoDurations.has(file) ? formatDuration(selectedVideoDurations.get(file)) : "";
    size.textContent = duration ? `${formatBytes(file.size || 0)} - ${duration}` : formatBytes(file.size || 0);
    size.dataset.fileDurationLabel = String(index);
    item.appendChild(size);

    const state = document.createElement("div");
    const uploadState = fileUploadStates[index] || {};
    state.className = `meta-file-state${uploadState.type ? ` ${uploadState.type}` : ""}`;
    state.dataset.fileState = String(index);
    state.textContent = uploadState.label || (uploading ? "Väntar" : "Vald");
    item.appendChild(state);

    const track = document.createElement("div");
    track.className = "meta-file-progress";
    track.innerHTML = `<div class="meta-file-progress-bar" data-file-progress="${index}"></div>`;
    item.appendChild(track);

    fileList.appendChild(item);
  });
}

function setFileUploadState(index, label, type = "") {
  fileUploadStates[index] = { label, type };
  const node = fileList.querySelector(`[data-file-state="${index}"]`);
  if (!node) return;
  node.textContent = label;
  node.className = `meta-file-state${type ? ` ${type}` : ""}`;
}

function updateFileDurationLabel(index, file) {
  const node = fileList.querySelector(`[data-file-duration-label="${index}"]`);
  if (!node) return;
  const duration = selectedVideoDurations.has(file) ? formatDuration(selectedVideoDurations.get(file)) : "";
  node.textContent = duration ? `${formatBytes(file.size || 0)} - ${duration}` : formatBytes(file.size || 0);
}

function readSelectedVideoDuration(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.muted = true;
    video.playsInline = true;
    let settled = false;
    const cleanup = () => {
      URL.revokeObjectURL(url);
      video.removeAttribute("src");
      video.load();
    };
    const finish = (duration = null) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeout);
      cleanup();
      resolve(duration);
    };
    const timeout = window.setTimeout(() => finish(null), 8000);
    video.addEventListener("loadedmetadata", () => {
      finish(video.duration);
    }, { once: true });
    video.addEventListener("error", () => finish(null), { once: true });
    video.src = url;
  });
}

async function loadSelectedVideoDurations() {
  const generation = ++durationProbeGeneration;
  for (let index = 0; index < selectedFiles.length; index += 1) {
    const file = selectedFiles[index];
    if (generation !== durationProbeGeneration) return;
    if (!isVideoFile(file) || selectedVideoDurations.has(file)) continue;
    const duration = await readSelectedVideoDuration(file);
    if (generation === durationProbeGeneration && selectedFiles[index] === file && duration != null) {
      selectedVideoDurations.set(file, duration);
      updateFileDurationLabel(index, file);
    }
  }
}

function setUploadControlsLocked(locked) {
  uploading = locked;
  input.disabled = locked;
  dropzone.classList.toggle("uploading", locked);
  dropzone.setAttribute("aria-busy", locked ? "true" : "false");
}

function resetProgress() {
  progressPanel.hidden = true;
  progressBar.style.width = "0%";
  progressPercent.textContent = "0%";
  progressLabel.textContent = "Laddar upp";
  progressRemaining.textContent = "";
}

function updateProgress(loadedBytes, totalBytes = totalSelectedBytes()) {
  const total = Math.max(Number(totalBytes) || totalSelectedBytes(), 1);
  const loaded = Math.min(Math.max(Number(loadedBytes) || 0, 0), total);
  const percent = Math.min(100, Math.round((loaded / total) * 100));
  const remaining = Math.max(0, total - loaded);
  const offsets = fileOffsets();
  let activeIndex = offsets.findIndex((item) => loaded >= item.start && loaded < item.end);
  if (activeIndex === -1 && loaded >= total && offsets.length) activeIndex = offsets.length - 1;

  progressPanel.hidden = false;
  progressBar.style.width = `${percent}%`;
  progressPercent.textContent = `${percent}%`;
  progressRemaining.textContent = remaining > 0
    ? `${formatBytes(remaining)} kvar av ${formatBytes(total)}`
    : `${formatBytes(total)} uppladdat`;
  progressLabel.textContent = activeIndex >= 0
    ? `Laddar upp ${selectedFiles[activeIndex]?.name || "fil"}`
    : "Laddar upp";

  offsets.forEach((item, index) => {
    const file = selectedFiles[index];
    const fileSize = Math.max(Number(file?.size) || 0, 1);
    const fileLoaded = Math.min(Math.max(loaded - item.start, 0), fileSize);
    const filePercent = Math.min(100, Math.round((fileLoaded / fileSize) * 100));
    const bar = fileList.querySelector(`[data-file-progress="${index}"]`);
    const state = fileList.querySelector(`[data-file-state="${index}"]`);
    if (bar) bar.style.width = `${filePercent}%`;
    if (state) {
      const uploadState = fileUploadStates[index] || {};
      if (uploadState.type === "success" || uploadState.type === "error") {
        state.textContent = uploadState.label;
        state.className = `meta-file-state ${uploadState.type}`;
        return;
      }
      state.textContent = filePercent >= 100
        ? "Klar"
        : index === activeIndex ? `${filePercent}%` : "Väntar";
    }
  });
}

function setFiles(files) {
  if (uploading) return;
  selectedFiles = Array.from(files || []).filter(Boolean);
  fileUploadStates = selectedFiles.map(() => ({ label: "Vald", type: "" }));
  resetProgress();
  renderFiles();
  void loadSelectedVideoDurations();
  setStatus(selectedFiles.length ? `${selectedFiles.length} filer valda. Startar uppladdning...` : "");
  if (selectedFiles.length) void startUpload();
}

input.addEventListener("change", () => setFiles(input.files));

["dragenter", "dragover"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
  });
});

dropzone.addEventListener("drop", (event) => {
  setFiles(event.dataTransfer?.files);
});

async function startUpload() {
  if (!selectedFiles.length || uploading) return;

  setUploadControlsLocked(true);
  fileUploadStates = selectedFiles.map(() => ({ label: "Väntar", type: "" }));
  renderFiles();
  updateProgress(0);
  setStatus("Laddar upp...");
  const totalBytes = totalSelectedBytes();
  let uploadedBeforeBytes = 0;
  let savedTotal = 0;
  let skippedTotal = 0;
  const failed = [];
  try {
    for (let start = 0; start < selectedFiles.length; start += META_UPLOAD_FILES_PER_REQUEST) {
      const batch = selectedFiles.slice(start, start + META_UPLOAD_FILES_PER_REQUEST);
      const batchBytes = batch.reduce((sum, file) => sum + (Number(file.size) || 0), 0);
      batch.forEach((_file, offset) => setFileUploadState(start + offset, "Laddar upp", ""));
      try {
        const payload = await uploadWithProgress(batch, (loadedBytes, eventTotalBytes) => {
          const loadedInBatch = Math.min(Math.max(Number(loadedBytes) || 0, 0), eventTotalBytes || batchBytes || 1);
          updateProgress(uploadedBeforeBytes + loadedInBatch, totalBytes);
        });
        const savedCount = Number(payload.saved_count || 0);
        const skippedCount = Number(payload.skipped_count || 0);
        savedTotal += savedCount;
        skippedTotal += skippedCount;
        batch.forEach((_file, offset) => {
          const index = start + offset;
          setFileUploadState(index, skippedCount ? "Dubblett" : "Klar", "success");
        });
      } catch (error) {
        const message = error.message || "Uppladdningen misslyckades.";
        failed.push({ index: start, message });
        batch.forEach((_file, offset) => setFileUploadState(start + offset, "Fel", "error"));
      }
      uploadedBeforeBytes += batchBytes;
      updateProgress(uploadedBeforeBytes, totalBytes);
    }
    input.value = "";
    if (failed.length) {
      const completedParts = [];
      if (savedTotal) completedParts.push(`${savedTotal} filer uppladdade`);
      if (skippedTotal) completedParts.push(`${skippedTotal} dubbletter hoppades över`);
      const successText = completedParts.length ? `${completedParts.join(". ")}. ` : "";
      setStatus(`${successText}${failed.length} filer misslyckades. Försök igen med de filerna.`, "error");
    } else if (skippedTotal && savedTotal) {
      setStatus(`${savedTotal} filer uppladdade. ${skippedTotal} dubbletter hoppades över.`, "success");
      selectedFiles = [];
      fileUploadStates = [];
      renderFiles();
    } else if (skippedTotal) {
      setStatus(`Inga nya filer sparades. ${skippedTotal} dubbletter fanns redan.`, "success");
      selectedFiles = [];
      fileUploadStates = [];
      renderFiles();
    } else {
      setStatus(`${savedTotal} filer uppladdade.`, "success");
      selectedFiles = [];
      fileUploadStates = [];
      renderFiles();
    }
  } catch (error) {
    setUploadControlsLocked(false);
    input.value = "";
    renderFiles();
    setStatus(error.message || "Uppladdningen misslyckades.", "error");
    return;
  }
  setUploadControlsLocked(false);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  void startUpload();
});

function uploadWithProgress(files, onProgress = () => {}) {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file, file.name));
    const batchBytes = files.reduce((sum, file) => sum + (Number(file.size) || 0), 0);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/meta/uploads");
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onProgress(event.loaded, event.total);
      } else {
        onProgress(event.loaded, batchBytes);
      }
    });
    xhr.addEventListener("load", () => {
      let payload = {};
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : {};
      } catch (_error) {
        payload = {};
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        const detail = typeof payload.detail === "string"
          ? payload.detail
          : typeof payload.message === "string"
            ? payload.message
            : "";
        reject(new Error(detail || `HTTP ${xhr.status}`));
        return;
      }
      resolve(payload);
    });
    xhr.addEventListener("error", () => reject(new Error("Kunde inte ansluta till servern.")));
    xhr.addEventListener("abort", () => reject(new Error("Uppladdningen avbröts.")));
    xhr.send(formData);
  });
}

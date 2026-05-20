(() => {
  const DB_NAME = "bemanning-productivity-files";
  const DB_VERSION = 1;
  const STORE = "files";

  const SOURCE_SPECS = [
    {
      key: "pick",
      label: "Plocklogg",
      prefix: "v_ask_pick_log_full",
      required: true,
      visible: true,
      headerHints: ["Zon", "Plockat", "Användare", "Ändrad", "Bolag"],
    },
    {
      key: "trans",
      label: "Translogg",
      prefix: "v_ask_trans_log",
      required: true,
      visible: true,
      headerHints: ["Pallid", "Från", "Till", "Antal", "Timestamp"],
    },
    {
      key: "pallet",
      label: "Palllastningslogg",
      prefix: "v_ask_palletloading_log",
      required: true,
      visible: true,
      headerHints: ["Plockpallsnr.", "Palltyp", "Pallplacering", "Transnr.", "Vikt"],
    },
    {
      key: "kpi",
      label: "KPI-Mål",
      prefix: "v_ask_kpi_target",
      required: true,
      visible: false,
      headerHints: ["Flödesnamn", "Processnamn", "Beskrivning", "Rader", "Kollin"],
    },
  ];

  const VISIBLE_SPECS = SOURCE_SPECS.filter((spec) => spec.visible);
  const SOURCE_BY_KEY = Object.fromEntries(SOURCE_SPECS.map((spec) => [spec.key, spec]));
  const registeredPanels = new Set();
  let lastAllocationSyncSignature = "";

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
    );
  }

  function formatFileSize(size) {
    if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    if (size >= 1024) return `${(size / 1024).toFixed(1)} kB`;
    return `${size || 0} B`;
  }

  function escapeRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function normalizeHeader(value) {
    return String(value ?? "").trim().replace(/^\ufeff/, "").toLowerCase();
  }

  function detectDelimiter(text) {
    const firstLine = String(text || "").split(/\r?\n/).find((line) => line.trim()) || "";
    const candidates = ["\t", ";", ","];
    return candidates
      .map((delimiter) => ({ delimiter, count: (firstLine.match(new RegExp(escapeRegExp(delimiter), "g")) || []).length }))
      .sort((a, b) => b.count - a.count)[0]?.delimiter || "\t";
  }

  function parseDelimitedLine(line, delimiter) {
    const values = [];
    let current = "";
    let inQuotes = false;
    for (let index = 0; index < line.length; index += 1) {
      const char = line[index];
      if (char === '"') {
        if (inQuotes && line[index + 1] === '"') {
          current += '"';
          index += 1;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (char === delimiter && !inQuotes) {
        values.push(current);
        current = "";
      } else {
        current += char;
      }
    }
    values.push(current);
    return values;
  }

  function db() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains(STORE)) database.createObjectStore(STORE, { keyPath: "key" });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function store(method, callback) {
    const database = await db();
    return new Promise((resolve, reject) => {
      const tx = database.transaction(STORE, method);
      const objectStore = tx.objectStore(STORE);
      const result = callback(objectStore);
      tx.oncomplete = () => {
        database.close();
        resolve(result);
      };
      tx.onerror = () => {
        database.close();
        reject(tx.error);
      };
    });
  }

  function entryFromStoredItem(item) {
    const blob = item.blob;
    const file = blob instanceof File
      ? blob
      : new File([blob], item.name || item.key, { type: item.type || blob?.type || "", lastModified: item.lastModified || Date.now() });
    return {
      key: item.key,
      file,
      name: item.name || file.name,
      size: item.size || file.size || 0,
      type: item.type || file.type || "",
      lastModified: item.lastModified || file.lastModified || Date.now(),
    };
  }

  async function loadFiles() {
    const database = await db();
    return new Promise((resolve, reject) => {
      const tx = database.transaction(STORE, "readonly");
      const request = tx.objectStore(STORE).getAll();
      request.onsuccess = () => {
        const files = {};
        for (const item of request.result || []) {
          const entry = entryFromStoredItem(item);
          files[entry.key] = entry;
        }
        database.close();
        resolve(files);
      };
      request.onerror = () => {
        database.close();
        reject(request.error);
      };
    });
  }

  async function saveFile(key, file) {
    const entry = {
      key,
      name: file.name || key,
      size: file.size || 0,
      type: file.type || "",
      lastModified: file.lastModified || Date.now(),
      blob: file,
    };
    await store("readwrite", (objectStore) => objectStore.put(entry));
    return entry;
  }

  async function deleteFile(key) {
    await store("readwrite", (objectStore) => objectStore.delete(key));
  }

  async function clearFiles() {
    await store("readwrite", (objectStore) => objectStore.clear());
  }

  async function readFileSample(file) {
    return await file.slice(0, 8192).text();
  }

  function classifyFileFromSample(file, sample) {
    const name = String(file?.name || "").toLowerCase();
    for (const spec of SOURCE_SPECS) {
      if (name.startsWith(spec.prefix.toLowerCase())) return spec.key;
    }

    const firstLine = String(sample || "").split(/\r?\n/).find((line) => line.trim()) || "";
    if (!firstLine) return null;
    const delimiter = detectDelimiter(firstLine);
    const headers = new Set(parseDelimitedLine(firstLine, delimiter).map((header) => normalizeHeader(header)));
    for (const spec of SOURCE_SPECS) {
      if (spec.headerHints.every((hint) => headers.has(normalizeHeader(hint)))) return spec.key;
    }
    return null;
  }

  async function classifyFile(file) {
    return classifyFileFromSample(file, await readFileSample(file));
  }

  function dragContainsFiles(event) {
    return Array.from(event.dataTransfer?.types || []).includes("Files");
  }

  function updateDropDepth(target, delta) {
    const nextDepth = Math.max(0, Number(target.dataset.productivityDragDepth || 0) + delta);
    target.dataset.productivityDragDepth = String(nextDepth);
    return nextDepth;
  }

  function clearDropHighlights() {
    document.querySelectorAll("[data-productivity-drop-bound='1']").forEach((target) => {
      target.dataset.productivityDragDepth = "0";
      target.classList.remove("is-dragging", "is-file-dragging", "drag-over");
    });
  }

  async function uploadPermanentKpiFile(file) {
    return await api.postFile(
      `/api/productivity/files/raw?filename=${encodeURIComponent(file.name)}`,
      file,
    );
  }

  function localStatus(files, serverStatus = {}) {
    const visibleFiles = Object.fromEntries(VISIBLE_SPECS.map((spec) => {
      const entry = files[spec.key];
      const file = entry?.file;
      return [spec.key, {
        key: spec.key,
        label: spec.label,
        required: spec.required,
        visible: spec.visible,
        uploaded: Boolean(file),
        name: entry?.name || file?.name || null,
        modified_at: entry?.lastModified ? new Date(entry.lastModified).toISOString() : null,
        size: entry?.size || file?.size || null,
        size_label: file ? formatFileSize(entry?.size || file.size) : null,
      }];
    }));
    const missing = Object.values(visibleFiles)
      .filter((file) => file.required && !file.uploaded)
      .map((file) => file.key);
    const kpiLoaded = Boolean(serverStatus.kpi_loaded);
    return {
      ready: missing.length === 0 && kpiLoaded,
      missing,
      files: visibleFiles,
      kpi_loaded: kpiLoaded,
    };
  }

  function statusItems(status) {
    const files = Object.values(status?.files || {});
    const kpiSpec = SOURCE_BY_KEY.kpi || { key: "kpi", label: "KPI-Mål", required: true };
    return [
      ...files.map((file) => ({ ...file, permanent: false })),
      {
        key: "kpi",
        label: kpiSpec.label,
        required: true,
        visible: true,
        uploaded: Boolean(status?.kpi_loaded),
        name: status?.kpi_loaded ? "Permanent målfil inlagd" : null,
        modified_at: null,
        size: null,
        size_label: null,
        permanent: true,
      },
    ];
  }

  async function fileStatus() {
    const [files, serverStatus] = await Promise.all([
      loadFiles(),
      api.get("/api/productivity/files"),
    ]);
    return localStatus(files, serverStatus);
  }

  function renderStatus(panel, status) {
    const files = statusItems(status);
    const filled = files.filter((file) => file.uploaded).length;
    const required = files.filter((file) => file.required).length;
    panel.querySelector("#productivityUploadCount").textContent = `${filled}/${required} inlagda`;
    panel.querySelector("#productivityFileSlots").innerHTML = files.map((file) => {
      const cls = file.uploaded ? "ok" : file.required ? "missing" : "optional";
      const prefix = file.uploaded ? "✓" : file.required ? "✗" : "○";
      return `
      <div class="productivity-file-slot ${file.uploaded ? "is-uploaded" : ""}" data-file-key="${escapeHtml(file.key)}">
        <div class="productivity-file-main">
          <div class="productivity-file-label">
            <span class="allocation-file-tag ${cls}">${prefix} ${escapeHtml(file.label)}${file.required ? "" : " (valfri)"}</span>
          </div>
          <div class="productivity-file-name">
            ${file.uploaded ? escapeHtml(file.name) : '<span class="muted">Ingen fil vald</span>'}
          </div>
          ${file.uploaded && file.size_label ? `<div class="productivity-file-meta">${escapeHtml(file.size_label)}</div>` : ""}
        </div>
        <div class="productivity-file-actions">
          <button type="button" class="btn-sm productivity-slot-upload" data-file-key="${escapeHtml(file.key)}">Välj</button>
          <button type="button" class="btn-sm danger productivity-slot-clear" data-file-key="${escapeHtml(file.key)}" ${file.uploaded && !file.permanent ? "" : "disabled"}>&times;</button>
        </div>
      </div>
    `;
    }).join("");

    const uploadStatus = panel.querySelector("#productivityUploadStatus");
    uploadStatus.textContent = status.ready
      ? "Alla produktivitetsunderlag är valda."
      : "Produktivitet räknas när de markerade filerna är valda.";
    if (!status.kpi_loaded) {
      uploadStatus.textContent = "Saknar permanent KPI-mål i bakgrunden.";
    }
  }

  async function refreshPanel(panel) {
    renderStatus(panel, await fileStatus());
    panel.querySelectorAll(".productivity-file-slot[data-file-key]").forEach((slot) => {
      setupDropTarget(slot, (files) => handleFiles(panel, files, slot.dataset.fileKey || ""));
    });
    panel.querySelectorAll(".productivity-slot-upload").forEach((button) => {
      button.addEventListener("click", () => {
        const input = panel.querySelector("#productivityUploadInput");
        input.dataset.targetKey = button.dataset.fileKey || "";
        input.click();
      });
    });
    panel.querySelectorAll(".productivity-slot-clear").forEach((button) => {
      button.addEventListener("click", async () => {
        await deleteFile(button.dataset.fileKey);
        await refreshPanel(panel);
      });
    });
  }

  async function refreshPanels() {
    for (const panel of Array.from(registeredPanels)) {
      if (!document.body.contains(panel)) {
        registeredPanels.delete(panel);
        continue;
      }
      await refreshPanel(panel);
    }
  }

  function storedFilesSignature(files) {
    return Object.values(files || {})
      .map((entry) => {
        const file = entry?.file;
        return file ? `${entry.key}:${file.name}:${file.size}:${file.lastModified}` : "";
      })
      .filter(Boolean)
      .sort()
      .join("|");
  }

  async function syncAllocationUploadsFromStore(files = null) {
    if (!window.sharedAllocationUploads?.saveFiles) return { saved: [], recognized: [], unknown: [], mappings: 0 };
    const stored = files || await loadFiles();
    const signature = storedFilesSignature(stored);
    if (!signature || signature === lastAllocationSyncSignature) {
      return { saved: [], recognized: [], unknown: [], mappings: 0 };
    }
    const fileList = Object.values(stored).map((entry) => entry?.file).filter(Boolean);
    const result = await window.sharedAllocationUploads.saveFiles(fileList);
    lastAllocationSyncSignature = signature;
    return result;
  }

  async function saveFiles(files, options = {}) {
    const targetKey = options.targetKey || "";
    const statusElement = options.statusElement || options.panel?.querySelector("#productivityUploadStatus") || null;
    const reportUnknown = options.reportUnknown !== false;
    const showResultToast = options.showToast !== false;
    const trackUploadActivity = options.trackUploadActivity !== false;
    const syncAllocationUploads = options.syncAllocationUploads !== false;
    const incoming = Array.from(files || []);
    if (!incoming.length) return { saved: [], unknown: [], hiddenSaved: 0, recognized: [], message: "Ingen fil uppdaterades." };

    if (statusElement) statusElement.textContent = "Läser filval...";
    const saved = [];
    const unknown = [];
    const recognized = [];
    let allocationResult = { saved: [], unknown: [], hiddenSaved: 0, recognized: [] };
    let hiddenSaved = 0;
    let activityCount = 0;
    if (trackUploadActivity) window.allocationUploadActivity?.start();

    try {
    for (const file of incoming) {
      const fileType = targetKey || await classifyFile(file);
      if (!fileType || !SOURCE_BY_KEY[fileType]) {
        if (reportUnknown) unknown.push(file.name || "okänd fil");
        continue;
      }
      recognized.push(file.name || fileType);
      if (fileType === "kpi") {
        if (statusElement) statusElement.textContent = `Uppdaterar KPI-mål: ${file.name}`;
        const result = await uploadPermanentKpiFile(file);
        hiddenSaved += (result.saved || []).length;
        if (reportUnknown) unknown.push(...(result.unknown || []));
        continue;
      }
      await saveFile(fileType, file);
      saved.push(file.name);
    }

    if (syncAllocationUploads && window.sharedAllocationUploads?.saveFiles) {
      allocationResult = await window.sharedAllocationUploads.saveFiles(incoming);
    }

    if (options.panel) await refreshPanel(options.panel);
    else if (saved.length || hiddenSaved) await refreshPanels();
    const activityNames = new Set([
      ...recognized,
      ...(allocationResult.recognized || []),
    ].filter(Boolean));
    activityCount = activityNames.size;
    const parts = [];
    if (saved.length) parts.push(`${saved.length} fil(er) valda`);
    if (allocationResult.saved?.length) parts.push(`${allocationResult.saved.length} fil(er) synkade till Uppladdningar`);
    if (hiddenSaved) parts.push("KPI-mål uppdaterat i bakgrunden");
    if (reportUnknown && unknown.length) parts.push(`Okänd filtyp: ${unknown.join(", ")}`);
    const message = parts.join(". ") || "Ingen fil uppdaterades.";
    if (statusElement) statusElement.textContent = message;
    if (showResultToast && (saved.length || hiddenSaved || allocationResult.saved?.length)) showToast(message, "success", 3500);
    else if (showResultToast && reportUnknown && unknown.length) showToast(message, "warn", 7000);
    return { saved, unknown, hiddenSaved, recognized, message, allocationSaved: allocationResult.saved || [] };
    } finally {
      if (trackUploadActivity) window.allocationUploadActivity?.finish(activityCount);
    }
  }

  async function handleFiles(panel, files, targetKey = "") {
    return await saveFiles(files, { panel, targetKey });
  }

  function setupDropTarget(target, onDrop, options = {}) {
    if (!target || target.dataset.productivityDropBound === "1") return;
    target.dataset.productivityDropBound = "1";
    const dragClass = options.dragClass || "is-dragging";
    target.addEventListener("dragenter", (event) => {
      if (!dragContainsFiles(event)) return;
      event.preventDefault();
      event.stopPropagation();
      updateDropDepth(target, 1);
      target.classList.add(dragClass);
    });
    target.addEventListener("dragover", (event) => {
      if (!dragContainsFiles(event)) return;
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = "copy";
    });
    target.addEventListener("dragleave", (event) => {
      event.stopPropagation();
      if (updateDropDepth(target, -1) === 0) target.classList.remove(dragClass);
    });
    target.addEventListener("drop", (event) => {
      if (!dragContainsFiles(event)) return;
      event.preventDefault();
      event.stopPropagation();
      clearDropHighlights();
      void onDrop(event.dataTransfer.files, event);
    });
  }

  function setupDropzone(panel) {
    setupDropTarget(panel, (files) => handleFiles(panel, files));
  }

  async function setupPanel(panel) {
    if (!panel) return;
    registeredPanels.add(panel);
    await syncAllocationUploadsFromStore();
    panel.innerHTML = `
      <div class="productivity-upload-head">
        <h3>Produktivitet</h3>
        <div>
          <span id="productivityUploadCount"></span>
          <label class="button-like primary" for="productivityUploadInput">Välj CSV-filer</label>
          <input id="productivityUploadInput" type="file" accept=".csv,.txt" multiple hidden />
        </div>
      </div>
      <div id="productivityFileSlots" class="productivity-file-slots"></div>
      <div id="productivityUploadStatus" class="productivity-upload-status"></div>
    `;
    setupDropzone(panel);
    const input = panel.querySelector("#productivityUploadInput");
    panel.querySelector('label[for="productivityUploadInput"]').addEventListener("click", () => {
      input.dataset.targetKey = "";
    });
    input.addEventListener("change", async () => {
      const targetKey = input.dataset.targetKey || "";
      input.dataset.targetKey = "";
      await handleFiles(panel, input.files, targetKey);
      input.value = "";
    });
    await refreshPanel(panel);
  }

  window.addEventListener("bemanning:uploadsCleared", refreshPanels);

  window.addEventListener("dragend", clearDropHighlights);

  window.productivityUploads = {
    visibleSpecs: () => VISIBLE_SPECS.map((spec) => ({ ...spec })),
    loadFiles,
    clearFiles,
    deleteFile,
    fileStatus,
    saveFiles,
    handleFiles,
    refreshPanels,
    syncAllocationUploads: syncAllocationUploadsFromStore,
    setupDropTarget,
    setupPanel,
  };
})();

// @ts-check
function readAllocationUploadNotice() {
  try {
    const raw = sessionStorage.getItem(ALLOCATION_UPLOAD_NOTICE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function writeAllocationUploadNotice(notice) {
  try {
    if (notice) sessionStorage.setItem(ALLOCATION_UPLOAD_NOTICE_KEY, JSON.stringify(notice));
    else sessionStorage.removeItem(ALLOCATION_UPLOAD_NOTICE_KEY);
  } catch (e) {}
}

function isAllocationUploadsPage() {
  return window.location.pathname.endsWith("/uppladdningar.html")
    || document.getElementById("allocation-upload-link")?.classList.contains("active");
}

function addAllocationUploadNotice(count = 0) {
  const numericCount = Math.max(0, Number(count) || 0);
  if (!numericCount) return;
  if (isAllocationUploadsPage()) {
    clearAllocationUploadNotice();
    return;
  }
  const existing = readAllocationUploadNotice();
  const nextCount = Math.min(999, (Number(existing?.count) || 0) + numericCount);
  writeAllocationUploadNotice({ count: nextCount, at: Date.now() });
}

function updateAllocationUploadIndicator() {
  const button = document.getElementById("allocation-upload-link");
  const noticeEl = document.getElementById("allocation-upload-notice");
  if (!button || !noticeEl) return;
  const notice = readAllocationUploadNotice();
  if (notice?.count) {
    noticeEl.textContent = String(notice.count);
    noticeEl.hidden = false;
    button.title = notice.count === 1 ? "1 fil uppladdad" : `${notice.count} filer uppladdade`;
  } else {
    noticeEl.hidden = true;
    noticeEl.textContent = "";
    button.title = "Uppladdningar";
  }
}

function clearAllocationUploadNotice() {
  writeAllocationUploadNotice(null);
  updateAllocationUploadIndicator();
}

function clearUploadIndexedDbStore(dbName, storeName, { protectedKeys = [] } = {}) {
  return new Promise((resolve, reject) => {
    const protectedKeySet = new Set((protectedKeys || []).map((key) => String(key)));
    const request = indexedDB.open(dbName, 1);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(storeName)) database.createObjectStore(storeName, { keyPath: "key" });
    };
    request.onsuccess = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(storeName)) {
        database.close();
        resolve({ deleted: 0, kept: 0 });
        return;
      }
      let deleted = 0;
      let kept = 0;
      const tx = database.transaction(storeName, "readwrite");
      const store = tx.objectStore(storeName);
      const cursorRequest = store.openCursor();
      cursorRequest.onsuccess = () => {
        const cursor = cursorRequest.result;
        if (!cursor) return;
        const key = String(cursor.key ?? cursor.value?.key ?? "");
        if (protectedKeySet.has(key)) {
          kept += 1;
          cursor.continue();
          return;
        }
        cursor.delete();
        deleted += 1;
        cursor.continue();
      };
      cursorRequest.onerror = () => {
        database.close();
        reject(cursorRequest.error);
      };
      tx.oncomplete = () => {
        database.close();
        resolve({ deleted, kept });
      };
      tx.onerror = () => {
        database.close();
        reject(tx.error);
      };
    };
    request.onerror = () => reject(request.error);
  });
}

function sharedAllocationDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(SHARED_ALLOCATION_DB_NAME, 1);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(SHARED_ALLOCATION_STORE)) {
        database.createObjectStore(SHARED_ALLOCATION_STORE, { keyPath: "key" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function warmSharedAllocationMetadataCache() {
  const metadataGeneration = sharedAllocationMetadataGeneration;
  const database = await sharedAllocationDb();
  return new Promise((resolve, reject) => {
    const tx = database.transaction(SHARED_ALLOCATION_STORE, "readonly");
    const request = tx.objectStore(SHARED_ALLOCATION_STORE).getAll();
    request.onsuccess = () => {
      const files = (request.result || []).map((item) => ({
        key: item.key,
        name: item.name || item.key,
        size: Number(item.size || item.blob?.size || 0),
        type: item.type || item.blob?.type || "",
        lastModified: Number(item.lastModified || Date.now()),
      })).filter((item) => item.key);
      if (metadataGeneration === sharedAllocationMetadataGeneration) {
        try {
          localStorage.setItem("flow-allocation-file-metadata-v1", JSON.stringify({
            version: 1,
            at: Date.now(),
            files,
          }));
        } catch (_error) {}
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

async function storeSharedAllocationFile(key, file) {
  const database = await sharedAllocationDb();
  return new Promise((resolve, reject) => {
    const tx = database.transaction(SHARED_ALLOCATION_STORE, "readwrite");
    const entry = {
      key,
      name: file.name || key,
      size: file.size || 0,
      type: file.type || "",
      lastModified: file.lastModified || Date.now(),
      blob: file,
    };
    tx.objectStore(SHARED_ALLOCATION_STORE).put(entry);
    tx.oncomplete = () => {
      database.close();
      resolve(entry);
    };
    tx.onerror = () => {
      database.close();
      reject(tx.error);
    };
  });
}

async function detectSharedAllocationFile(file) {
  const fd = new FormData();
  fd.append("file", file, file.name);
  try {
    const response = await fetch(`${SHARED_ALLOCATION_API}/detect`, {
      method: "POST",
      body: fd,
      credentials: "include",
    });
    if (!response.ok) return "";
    const result = await response.json();
    return result?.file_type || "";
  } catch (_error) {
    return "";
  }
}

function sharedAllocationNameHintScore(slotKey, name) {
  return (SHARED_ALLOCATION_FILE_WORDS[slotKey] || []).reduce((best, word) => {
    const normalized = String(word || "").toLowerCase();
    return normalized && name.includes(normalized) ? Math.max(best, normalized.length) : best;
  }, 0);
}

function hintedSharedAllocationKeys(file) {
  const name = String(file?.name || "").toLowerCase();
  let bestKey = "";
  let bestScore = 0;
  for (const key of Object.keys(SHARED_ALLOCATION_FILE_WORDS)) {
    const score = sharedAllocationNameHintScore(key, name);
    if (score > bestScore) {
      bestKey = key;
      bestScore = score;
    }
  }
  return bestKey ? [bestKey] : [];
}

function expandSharedAllocationKeys(keys) {
  const result = [];
  for (const key of keys || []) {
    if (!result.includes(key)) result.push(key);
    for (const mirror of SHARED_ALLOCATION_SLOT_MIRRORS[key] || []) {
      if (!result.includes(mirror)) result.push(mirror);
    }
  }
  return result;
}

function sharedAllocationKeysForType(fileType) {
  return expandSharedAllocationKeys(SHARED_ALLOCATION_FILE_TYPE_KEYS[fileType] || []);
}

function sharedAllocationClearGeneration() {
  return uploadClearGeneration;
}

function sharedAllocationSaveIsStale(expectedClearGeneration) {
  return Number.isInteger(expectedClearGeneration) && expectedClearGeneration !== uploadClearGeneration;
}

async function saveSharedAllocationFiles(files, options = {}) {
  const expectedClearGeneration = Number.isInteger(options?.clearGeneration) ? options.clearGeneration : null;
  const incoming = Array.from(files || []);
  if (incoming.length) sharedAllocationMetadataGeneration += 1;
  const saved = [];
  const recognized = [];
  const unknown = [];
  let mappings = 0;
  const staleResult = () => ({ saved, recognized, unknown, mappings, stale: true });
  for (const file of incoming) {
    if (sharedAllocationSaveIsStale(expectedClearGeneration)) return staleResult();
    const fileType = await detectSharedAllocationFile(file);
    if (sharedAllocationSaveIsStale(expectedClearGeneration)) return staleResult();
    const targetKeys = sharedAllocationKeysForType(fileType);
    const keys = targetKeys.length ? targetKeys : expandSharedAllocationKeys(hintedSharedAllocationKeys(file));
    if (!keys.length) {
      unknown.push(file.name || "okand fil");
      continue;
    }
    recognized.push(file.name || keys[0]);
    for (const key of keys) {
      if (sharedAllocationSaveIsStale(expectedClearGeneration)) return staleResult();
      await storeSharedAllocationFile(key, file);
      mappings += 1;
    }
    saved.push(file.name || keys[0]);
  }
  if (mappings) {
    void warmSharedAllocationMetadataCache();
    window.dispatchEvent(new CustomEvent("flow:allocationFilesChanged", {
      detail: { saved: saved.length, mappings },
    }));
  }
  return { saved, recognized, unknown, mappings };
}

async function clearAllUploadedFiles({ confirmUser = true } = {}) {
  if (confirmUser && !confirm("Rensa alla vanliga filval i Uppladdningar? Kärnfiler och sammanställd data ligger kvar.")) return false;
  uploadClearGeneration += 1;
  sharedAllocationMetadataGeneration += 1;
  const results = await Promise.all(
    UPLOAD_FILE_STORES.map((item) => clearUploadIndexedDbStore(
      item.dbName,
      item.storeName,
      { protectedKeys: item.protectedKeys || [] },
    )),
  );
  const deleted = results.reduce((sum, item) => sum + (Number(item?.deleted) || 0), 0);
  const kept = results.reduce((sum, item) => sum + (Number(item?.kept) || 0), 0);
  try { localStorage.removeItem("flow-allocation-file-metadata-v1"); } catch (_error) {}
  clearAllocationUploadNotice();
  window.dispatchEvent(new CustomEvent("flow:uploadsCleared", {
    detail: { deleted, keptProtected: kept },
  }));
  showToast(
    deleted
      ? "Vanliga filval är rensade. Kärnfiler och sammanställd data ligger kvar."
      : "Inga vanliga filval att rensa. Kärnfiler och sammanställd data ligger kvar.",
    "success",
    3000,
  );
  return true;
}

function closeUploadContextMenu() {
  document.querySelector(".upload-context-menu")?.remove();
}

function openUploadContextMenu(event) {
  event.preventDefault();
  event.stopPropagation();
  closeUploadContextMenu();

  const menu = document.createElement("div");
  menu.className = "upload-context-menu";
  menu.setAttribute("role", "menu");
  menu.innerHTML = '<button type="button" role="menuitem">Rensa filer</button>';
  document.body.appendChild(menu);

  const left = Math.min(event.clientX, window.innerWidth - menu.offsetWidth - 8);
  const top = Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 8);
  menu.style.left = `${Math.max(8, left)}px`;
  menu.style.top = `${Math.max(8, top)}px`;

  menu.querySelector("button").addEventListener("click", async () => {
    closeUploadContextMenu();
    try {
      await clearAllUploadedFiles();
    } catch (error) {
      showToast(error.message || "Kunde inte rensa filerna.", "error", 7000);
    }
  });

  setTimeout(() => {
    document.addEventListener("click", closeUploadContextMenu, { once: true });
    document.addEventListener("keydown", (keyEvent) => {
      if (keyEvent.key === "Escape") closeUploadContextMenu();
    }, { once: true });
  }, 0);
}

function setAllocationUploading(active) {
  const button = document.getElementById("allocation-upload-link");
  if (!button) return;
  button.classList.toggle("uploading", Boolean(active));
}

function startAllocationUploadActivity() {
  setAllocationUploading(true);
}

function finishAllocationUploadActivity(count = 0) {
  setAllocationUploading(false);
  if (count > 0) {
    addAllocationUploadNotice(count);
    const text = count === 1 ? "1 fil uppladdad" : `${count} filer uppladdade`;
    showToast(text, "success", 2500);
  }
  updateAllocationUploadIndicator();
}


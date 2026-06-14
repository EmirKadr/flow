function allocationDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(ALLOCATION_DB_NAME, ALLOCATION_DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(ALLOCATION_STORE)) db.createObjectStore(ALLOCATION_STORE, { keyPath: "key" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function allocationStore(method, callback) {
  const db = await allocationDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(ALLOCATION_STORE, method);
    const store = tx.objectStore(ALLOCATION_STORE);
    const result = callback(store);
    tx.oncomplete = () => {
      db.close();
      resolve(result);
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

async function loadStoredAllocationFiles() {
  const db = await allocationDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(ALLOCATION_STORE, "readonly");
    const request = tx.objectStore(ALLOCATION_STORE).getAll();
    request.onsuccess = () => {
      const files = {};
      for (const item of request.result || []) {
        const blob = item.blob;
        files[item.key] = {
          key: item.key,
          name: item.name,
          size: item.size || blob?.size || 0,
          type: item.type || blob?.type || "",
          lastModified: item.lastModified || Date.now(),
          localRef: item.localRef || "",
          blob,
        };
      }
      db.close();
      cacheAllocationFileMetadata(files);
      resolve(files);
    };
    request.onerror = () => {
      db.close();
      reject(request.error);
    };
  });
}

async function loadStoredAllocationFileEntry(key) {
  const db = await allocationDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(ALLOCATION_STORE, "readonly");
    const request = tx.objectStore(ALLOCATION_STORE).get(key);
    request.onsuccess = () => {
      const item = request.result;
      const blob = item?.blob;
      db.close();
      if (!item || (!blob && !item.localRef)) {
        resolve(null);
        return;
      }
      resolve({
        key: item.key,
        name: item.name,
        size: item.size || blob?.size || 0,
        type: item.type || blob?.type || "",
        lastModified: item.lastModified || blob?.lastModified || Date.now(),
        localRef: item.localRef || "",
        blob,
      });
    };
    request.onerror = () => {
      db.close();
      reject(request.error);
    };
  });
}

async function saveAllocationFile(key, file) {
  const entry = {
    key,
    name: file.name || key,
    size: file.size || 0,
    type: file.type || "",
    lastModified: file.lastModified || Date.now(),
    localRef: file.localRef || "",
    blob: file.localRef ? null : file,
  };
  await allocationStore("readwrite", (store) => store.put(entry));
  allocationState.files[key] = entry;
  cacheAllocationFileMetadata();
  if (key === "buffer") triggerAllocationObservationsUpdate(entry);
}

async function deleteAllocationFile(key) {
  await allocationStore("readwrite", (store) => store.delete(key));
  delete allocationState.files[key];
  cacheAllocationFileMetadata();
}

function allocationFileForForm(entry) {
  if (!entry) return null;
  if (allocationIsDesktopEntry(entry)) return null;
  return entry.blob || entry.file || null;
}

function appendAllocationFileField(fd, fieldKey, entry) {
  if (!entry) return false;
  if (allocationIsDesktopEntry(entry)) {
    fd.append(fieldKey, allocationLocalRefValue(entry));
    return true;
  }
  const file = allocationFileForForm(entry);
  if (!file) return false;
  fd.append(fieldKey, file, entry.name);
  return true;
}

async function downloadAllocationPersistentFile(fileKey) {
  const key = String(fileKey || "").trim();
  if (!key) return;
  await api.download(`/api/coredata/files/${encodeURIComponent(key)}/download`, `${key}.csv`);
}

async function downloadAllocationLocalFile(slotKey) {
  const key = allocationLogicalKey(slotKey);
  let entry = allocationState.files[key] || await loadStoredAllocationFileEntry(key);
  if (!entry) throw new Error("Filen hittades inte lokalt.");
  if (allocationIsDesktopEntry(entry)) {
    await allocationJson(`/api/desktop/files/${encodeURIComponent(entry.localRef)}/open`, { method: "POST" });
    return;
  }
  const file = allocationFileForForm(entry);
  if (!file) throw new Error("Filen hittades inte lokalt.");
  const url = URL.createObjectURL(file);
  const link = document.createElement("a");
  link.href = url;
  link.download = entry.name || `${key}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function openAllocationDesktopRef(ref, folder = false) {
  if (!ref) return;
  await allocationJson(`/api/desktop/files/${encodeURIComponent(ref)}/${folder ? "open-folder" : "open"}`, { method: "POST" });
}

function allocationFileSize(size) {
  if (!size) return "";
  if (size < 1024 * 1024) return `${Math.round(size / 102.4) / 10} kB`;
  return `${Math.round(size / 1024 / 102.4) / 10} MB`;
}

function allocationDisplaySizeLabel(entry, persistentEntry) {
  if (entry) return allocationFileSize(entry.size);
  return persistentEntry?.sizeLabel || "";
}

function allocationPersistentDataItems() {
  const files = allocationState.coredata?.files || {};
  return ALLOCATION_PERSISTENT_DATA_DISPLAY_ORDER.map((key) => {
    const entry = files[key] || {};
    const kind = allocationDataKindForKey(key, entry);
    return {
      key,
      label: ALLOCATION_PERSISTENT_DATA_LABELS[key] || entry.label || key,
      kind,
      badge: allocationDataBadge(kind),
      missingText: allocationDataMissingText(kind),
      uploaded: Boolean(entry.uploaded),
      name: entry.name || "",
      sizeLabel: entry.size_label || "",
    };
  });
}


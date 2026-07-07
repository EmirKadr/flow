// @ts-check
// Stale-while-revalidate-snapshots (pilot: Personer + Översikt).
// Laddas EFTER js/api.js på pilotsidorna — globala script delar scope, så
// modulen använder api.js interna hjälpare (request, cloneApiCacheValue,
// apiCacheKey) och registrerar sina exports på window.api när den laddats.
// ---- Stale-while-revalidate-snapshots (pilot: Personer + Översikt) ----
// Skillnaden mot GET-cachen ovan: snapshots har ingen TTL vid läsning —
// de är MENADE att vara inaktuella och visas direkt vid sidbyte medan
// färskt data hämtas i bakgrunden. Verksamhets-/områdesfokus bakas in i
// nyckeln så ett scope-byte aldrig kan visa fel verksamhets data, och
// varje mutation rensar snapshots via clearApiGetCache.
const API_SWR_STORAGE_PREFIX = "flow-api-swr:";

function swrScopeSuffix() {
  try {
    return `${localStorage.getItem(AREA_FOCUS_STORAGE_KEY_FALLBACK) || ""}|${localStorage.getItem(BUSINESS_FOCUS_STORAGE_KEY_FALLBACK) || ""}`;
  } catch (_error) {
    return "";
  }
}

const AREA_FOCUS_STORAGE_KEY_FALLBACK = "flow-area-focus";
const BUSINESS_FOCUS_STORAGE_KEY_FALLBACK = "flow-business-focus";

function swrStorageKey(path) {
  return `${API_SWR_STORAGE_PREFIX}${apiCacheKey(path)}::${swrScopeSuffix()}`;
}

function readSwrSnapshot(path) {
  try {
    const raw = sessionStorage.getItem(swrStorageKey(path));
    if (!raw) return null;
    const entry = JSON.parse(raw);
    return entry && "body" in entry ? entry.body : null;
  } catch (_error) {
    return null;
  }
}

function writeSwrSnapshot(path, body) {
  try {
    sessionStorage.setItem(
      swrStorageKey(path),
      JSON.stringify({ body: cloneApiCacheValue(body), savedAt: Date.now() })
    );
  } catch (_error) {} // kvotfel m.m. — snapshoten är alltid bara en bonus
}

function clearSwrSnapshots(predicate = null) {
  try {
    const keys = [];
    for (let index = 0; index < sessionStorage.length; index += 1) {
      const storageKey = sessionStorage.key(index);
      if (!storageKey?.startsWith(API_SWR_STORAGE_PREFIX)) continue;
      const cacheKey = storageKey.slice(API_SWR_STORAGE_PREFIX.length).split("::")[0];
      if (typeof predicate !== "function" || predicate(cacheKey)) keys.push(storageKey);
    }
    for (const key of keys) sessionStorage.removeItem(key);
  } catch (_error) {}
}

function setSwrRefreshIndicator(active) {
  if (!document?.body) return;
  let pill = document.getElementById("swr-refresh-indicator");
  if (!active) {
    pill?.remove();
    return;
  }
  if (pill) return;
  pill = document.createElement("div");
  pill.id = "swr-refresh-indicator";
  pill.className = "swr-refresh-indicator";
  pill.setAttribute("role", "status");
  pill.textContent = "Uppdaterar…";
  document.body.appendChild(pill);
}

async function getSwr(path, onData, options = {}) {
  const snapshot = readSwrSnapshot(path);
  let servedText = null;
  if (snapshot !== null) {
    servedText = JSON.stringify(snapshot);
    onData(cloneApiCacheValue(snapshot), { fromCache: true });
    setSwrRefreshIndicator(true);
  }
  try {
    const fresh = await request(path, { ...options, method: "GET" });
    writeSwrSnapshot(path, fresh);
    if (servedText === null || JSON.stringify(fresh) !== servedText) {
      onData(cloneApiCacheValue(fresh), { fromCache: false });
    }
    return fresh;
  } catch (error) {
    // Visades en snapshot har användaren redan data; request() har redan
    // loggat/toastat felet. Utan snapshot ska felet upp till sidan som förr.
    if (servedText === null) throw error;
    return snapshot;
  } finally {
    setSwrRefreshIndicator(false);
  }
}


// Exports på window.api (api.js har redan skapat objektet).
if (window.api) {
  window.api.getSwr = getSwr;
  window.api.readSwrSnapshot = readSwrSnapshot;
  window.api.setSwrRefreshIndicator = setSwrRefreshIndicator;
}

function bindRunButtons() {
  const root = document.getElementById("allocationRoot");
  root.querySelectorAll("[data-run-flow]").forEach((button) => {
    button.addEventListener("click", () => runAllocationFlow(flowById(button.dataset.runFlow)));
  });
  bindFlowInfoToggles(root);
  bindFlowFilterButtons(root);
  bindResultActions(root);
}

function renderAllocationPage() {
  if (allocationState.page === "uploads") renderUploadsView();
  else if (allocationState.page === "process") renderCombinedView();
  else if (allocationState.page === "settings") renderAllocationMapSettingsView();
  else if (allocationState.page === "split") renderSoloFlowView("split-values");
}

async function loadAllocationUploadStateForVisibleFlows() {
  const tasks = [];
  if (allocationState.page === "uploads" || allocationVisibleFlowsNeedStoredFiles()) {
    tasks.push(loadStoredAllocationFiles().then((files) => {
      allocationState.files = files;
    }));
  } else if (allocationState.page === "process") {
    allocationState.files = {};
  }
  if (allocationState.page === "uploads" || allocationVisibleFlowsNeedCoreDataStatus()) {
    tasks.push(loadAllocationCoreDataStatus());
  }
  await Promise.all(tasks);
}

function renderAllocationUnavailable(message) {
  renderAllocationShell(`
    <section class="allocation-panel">
      <h2>Allokering kunde inte startas</h2>
      <p class="allocation-muted">${allocationEscape(message)}</p>
    </section>
  `);
}

function handleAllocationAreaFocusChanged() {
  const root = document.getElementById("allocationRoot");
  if (!root || !allocationState.user || allocationState.busyId) return;
  if (allocationState.page === "settings") {
    renderAllocationPage();
    return;
  }
  if (allocationState.page !== "process") return;
  allocationState.values = {};
  allocationState.status = "";
  allocationState.result = null;
  restoreAllocationWorkState();
  renderAllocationPage();
}

async function initAllocationPage() {
  const root = document.getElementById("allocationRoot");
  if (!root) return;
  allocationState.page = root.dataset.allocationView || "uploads";
  const pageOptions = allocationState.page === "settings"
    ? { anyViewIds: ["allocationSettings", "staffingSettings", "allocationProcessMatrix"] }
    : { requireAllocationTools: true };
  if (allocationState.page === "process") {
    pageOptions.requireAllocationProcess = true;
    pageOptions.denyRedirect = "/dela.html";
  }
  allocationState.user = await initPage(allocationPageActiveName(allocationState.page), pageOptions);
  if (!allocationState.user) return;
  ensureFlowPopoverDismiss();
  if (allocationState.page === "settings") {
    root.innerHTML = `<div class="section-title">${allocationEscape(allocationPrimaryTitle(allocationState.page))}</div><section class="allocation-panel"><p>Laddar...</p></section>`;
    renderAllocationPage();
    return;
  }
  const restoredFromCache = restoreAllocationBootData();
  if (restoredFromCache) renderAllocationPage();
  else root.innerHTML = `<div class="section-title">${allocationEscape(allocationPrimaryTitle(allocationState.page))}</div><section class="allocation-panel"><p>Laddar...</p></section>`;
  try {
    let workStateRestored = false;
    const restoreWorkStateOnce = () => {
      if (workStateRestored) return;
      restoreAllocationWorkState();
      workStateRestored = true;
    };

    if (allocationState.page === "uploads") {
      const cachedMetadata = Object.keys(allocationState.files || {}).length
        ? allocationState.files
        : readCachedAllocationFileMetadata();
      if (!restoredFromCache && Object.keys(cachedMetadata).length) {
        allocationState.files = cachedMetadata;
      }
      await Promise.all([
        loadAllocationFlows(),
        loadAllocationProcessMatrix(),
        loadAllocationFilterProfile(),
      ]);
      await loadAllocationUploadStateForVisibleFlows();
      if (!restoredFromCache && Object.keys(allocationState.files || {}).length) {
        restoreWorkStateOnce();
        renderAllocationPage();
      }
    } else {
      await Promise.all([
        loadAllocationFlows(),
        loadAllocationProcessMatrix(),
        loadAllocationFilterProfile(),
      ]);
      await loadAllocationUploadStateForVisibleFlows();
    }
    if (allocationDesktopAvailable()) {
      void allocationJson("/api/desktop/cache/sync", { method: "POST" }).catch((error) => {
        console.warn("Kunde inte synka lokal desktop-cache.", error);
      });
    }
    restoreWorkStateOnce();
    renderAllocationPage();
  } catch (error) {
    renderAllocationUnavailable(error.message);
  }
}

window.addEventListener("flow:uploadsCleared", async () => {
  const root = document.getElementById("allocationRoot");
  if (!root || !allocationState.user) return;
  allocationState.files = await loadStoredAllocationFiles();
  cacheAllocationFileMetadata();
  await loadAllocationCoreDataStatus({ skipCache: true });
  allocationState.status = "Vanliga filval rensade. Kärnfiler och sammanställd data ligger kvar.";
  allocationState.autoStatus = "";
  allocationState.lastBufferSignature = "";
  renderAllocationPage();
});

window.addEventListener("flow:allocationFilesChanged", async () => {
  const root = document.getElementById("allocationRoot");
  if (!root || !allocationState.user) return;
  allocationState.files = await loadStoredAllocationFiles();
  cacheAllocationFileMetadata();
  renderAllocationPage();
});

window.addEventListener("flow:areaFocusChanged", handleAllocationAreaFocusChanged);

window.preloadAllocationUploadsData = function preloadAllocationUploadsData() {
  if (allocationUploadsPreloadPromise) return allocationUploadsPreloadPromise;
  allocationUploadsPreloadPromise = Promise.allSettled([
    loadStoredAllocationFiles(),
    loadAllocationFlows(),
    loadAllocationCoreDataStatus(),
    loadAllocationFilterProfile(),
  ]).finally(() => {
    cacheAllocationBootData();
    allocationUploadsPreloadPromise = null;
  });
  return allocationUploadsPreloadPromise;
};

document.addEventListener("DOMContentLoaded", initAllocationPage);

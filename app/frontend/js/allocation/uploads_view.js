function deriveAllocationSlots(flows) {
  const map = new Map();
  for (const flow of flows) {
    for (const input of flow.inputs || []) {
      if (input.type && input.type !== "file") continue;
      const key = allocationFileInputKey(input);
      if (!map.has(key)) {
        map.set(key, { key, label: allocationUploadSlotLabel({ key, label: input.label }), detect: new Set(input.detect || []) });
      } else {
        (input.detect || []).forEach((value) => map.get(key).detect.add(value));
      }
    }
  }
  const keys = ALLOCATION_SLOT_ORDER.filter((key) => map.has(key)).concat([...map.keys()].filter((key) => !ALLOCATION_SLOT_ORDER.includes(key)));
  return keys.map((key) => ({ ...map.get(key), detect: [...map.get(key).detect] }));
}

function mergeUploadOnlySlots(slots) {
  if (allocationState.page !== "uploads") return slots;
  const map = new Map(slots.map((slot) => [slot.key, { ...slot }]));
  const keys = ALLOCATION_SLOT_ORDER
    .filter((key) => map.has(key))
    .concat([...map.keys()].filter((key) => !ALLOCATION_SLOT_ORDER.includes(key)));
  return keys.map((key) => map.get(key));
}

function allocationNameHintScore(slot, name) {
  return (ALLOCATION_FILE_WORDS[slot.key] || []).reduce((best, word) => {
    const normalized = String(word || "").toLowerCase();
    return normalized && name.includes(normalized) ? Math.max(best, normalized.length) : best;
  }, 0);
}

function hintedAllocationSlot(file, slots) {
  const name = String(file.name || "").toLowerCase();
  let bestSlot = null;
  let bestScore = 0;
  for (const slot of slots) {
    const score = allocationNameHintScore(slot, name);
    if (score > bestScore) {
      bestSlot = slot;
      bestScore = score;
    }
  }
  return bestSlot;
}

function fallbackAllocationSlot(file, slots, droppedCount, fallbackSlotKey = "") {
  const hinted = hintedAllocationSlot(file, slots);
  if (hinted) return hinted;
  if (fallbackSlotKey && droppedCount === 1) {
    const fallback = slots.find((slot) => slot.key === fallbackSlotKey);
    if (fallback) return fallback;
  }
  return droppedCount === 1 && slots.length === 1 ? slots[0] : null;
}

function allocationSlotsForDetectedType(fileType, slots) {
  const matches = slots.filter((slot) => (slot.detect || []).includes(fileType));
  if (!matches.length) return [];
  const preferredKey = ALLOCATION_FILE_TYPE_PRIMARY_SLOT[fileType];
  const preferred = preferredKey ? matches.find((slot) => slot.key === preferredKey) : null;
  return preferred ? [preferred] : [matches[0]];
}

function expandAllocationTargetSlots(primarySlot, slots) {
  if (!primarySlot) return [];
  const targets = [primarySlot];
  for (const mirrorKey of ALLOCATION_SLOT_MIRRORS[primarySlot.key] || []) {
    const mirror = slots.find((slot) => slot.key === mirrorKey);
    if (mirror && !targets.some((slot) => slot.key === mirror.key)) targets.push(mirror);
  }
  return targets;
}

function classifyAllocationCoreDataFile(file) {
  const stem = String(file?.name || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\.[^.]+$/, "");
  if (!stem) return null;
  for (const spec of ALLOCATION_PERSISTENT_DATA_UPLOAD_SPECS) {
    if (
      stem === spec.prefix
      || stem.startsWith(`${spec.prefix}-`)
      || stem.startsWith(`${spec.prefix}_`)
      || stem.startsWith(`${spec.prefix}.`)
      || stem.startsWith(`${spec.prefix} `)
    ) {
      return spec.key;
    }
  }
  return null;
}

async function uploadAllocationCoreDataFile(file) {
  if (file?.localRef) {
    return await allocationJson("/api/desktop/sync/coredata", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ localRef: file.localRef, filename: file.name || "coredata.csv" }),
    });
  }
  return await api.postFile(
    `/api/coredata/files/raw?filename=${encodeURIComponent(file.name || "coredata.csv")}`,
    file,
  );
}

async function detectAllocationFile(file) {
  if (file?.localRef) {
    return await allocationJson(`/api/desktop/files/${encodeURIComponent(file.localRef)}/detect`);
  }
  const fd = new FormData();
  fd.append("file", file, file.name);
  return allocationPostForm(`${ALLOCATION_API}/detect`, fd);
}

async function routeAllocationFiles(files, slots, options = {}) {
  const dropped = [...(files || [])];
  if (!dropped.length) return;
  window.allocationUploadActivity?.start();
  allocationState.status = "Identifierar filer...";
  renderAllocationPage();
  const assigned = [];
  const coredataSaved = [];
  const unknown = [];
  try {
    for (const file of dropped) {
      if (classifyAllocationCoreDataFile(file)) {
        try {
          const result = await uploadAllocationCoreDataFile(file);
          if (result.status) allocationState.coredata = result.status;
          cacheAllocationBootData();
          coredataSaved.push(file.name || "kärnfil");
        } catch (error) {
          showToast(error.message || "Kunde inte uppdatera kärnfil.", "error", 7000);
        }
        continue;
      }
      let targets = [];
      try {
        const result = await detectAllocationFile(file);
        targets = allocationSlotsForDetectedType(result.file_type, slots);
      } catch (e) {
        targets = [];
      }
      let target = targets[0] || null;
      if (!target) target = fallbackAllocationSlot(file, slots, dropped.length, options.fallbackSlotKey || "");
      targets = expandAllocationTargetSlots(target, slots);
      if (target) {
        for (const slot of targets) {
          await saveAllocationFile(slot.key, file);
          assigned.push({ file, slot });
        }
      } else {
        unknown.push(file.name);
      }
    }
  } finally {
    const uploadedNames = new Set([
      ...assigned.map((item) => item.file?.name || ""),
      ...coredataSaved,
    ].filter(Boolean));
    window.allocationUploadActivity?.finish(uploadedNames.size);
  }
  const uploadedNames = new Set([
    ...assigned.map((item) => item.file?.name || ""),
    ...coredataSaved,
  ].filter(Boolean));
  if (uploadedNames.size === 1) allocationState.status = "1 fil inlagd.";
  else if (uploadedNames.size > 1) allocationState.status = `${uploadedNames.size} filer inlagda.`;
  else allocationState.status = "";
  if (unknown.length) showToast(`Kunde inte sortera: ${unknown.join(", ")}`, "warn");
  persistAllocationWorkState();
  renderAllocationPage();
}

function observationsUpdateStatusText(result) {
  const newRows = Number(result?.new_rows || 0);
  const sentRows = Number(result?.github_sent_rows || 0);
  const changedMax = Number(result?.article_max_changed_rows || 0);
  const newArticles = Number(result?.article_max_new_rows || 0);
  if (!newRows) {
    return `Observations kontrollerad: 0 nya pallid. artikel_max: ${changedMax} maxvärden ändrade.`;
  }
  const githubText = sentRows
    ? `${sentRows} skickade till GitHub`
    : "GitHub-push ej bekräftad";
  const articleText = newArticles
    ? `${changedMax} maxvärden ändrade, ${newArticles} nya artiklar`
    : `${changedMax} maxvärden ändrade`;
  return `Observations uppdaterad: ${newRows} nya pallid, ${githubText}. artikel_max: ${articleText}.`;
}

function observationsUpdateLogText(result) {
  const newRows = Number(result?.new_rows || 0);
  const githubState = result?.pushed_to_github
    ? "bekräftad"
    : newRows
      ? "ej bekräftad"
      : "inte aktuell (0 nya pallid)";
  const lines = [
    `Nya pallid hittade: ${newRows}`,
    `Pallid skickade till GitHub: ${Number(result?.github_sent_rows || 0)}`,
    `GitHub-push: ${githubState}`,
    `Artikel-max-rader: ${Number(result?.article_max_rows || 0)}`,
    `Ändrade maxvärden: ${Number(result?.article_max_changed_rows || 0)}`,
    `Max upp/ned: ${Number(result?.article_max_increased_rows || 0)} / ${Number(result?.article_max_decreased_rows || 0)}`,
    `Nya artiklar i artikel_max: ${Number(result?.article_max_new_rows || 0)}`,
  ];
  const examples = Array.isArray(result?.article_max_changed_examples)
    ? result.article_max_changed_examples.slice(0, 3)
    : [];
  if (examples.length) {
    lines.push("Exempel:");
    examples.forEach((item) => {
      lines.push(`- ${item.artikelnummer}: ${item.before_max} -> ${item.after_max} (${item.before_pallid} -> ${item.after_pallid})`);
    });
  }
  return lines.join("\n");
}

async function triggerAllocationObservationsUpdate(entry) {
  const signature = `${entry.name}:${entry.size}:${entry.lastModified}`;
  if (allocationState.lastBufferSignature === signature) return;
  allocationState.lastBufferSignature = signature;
  allocationState.autoStatus = "Observations uppdateras...";
  renderAllocationPage();
  const file = allocationFileForForm(entry);
  if (!file) return;
  const fd = new FormData();
  appendAllocationAreaFocus(fd);
  fd.append("file", file, entry.name);
  try {
    const result = await allocationPostForm(`${ALLOCATION_API}/observations/update`, fd);
    allocationState.autoStatus = observationsUpdateStatusText(result);
    window.appendAppLog?.(
      observationsUpdateLogText(result),
      Number(result?.new_rows || 0) && !result.pushed_to_github ? "warn" : "info",
      "Observations",
    );
  } catch (error) {
    allocationState.lastBufferSignature = "";
    allocationState.autoStatus = "";
    window.appendAppLog?.(error.message || "Observations-uppdatering misslyckades.", "error", "Observations");
  }
  renderAllocationPage();
}

function currentAllocationSlots() {
  return mergeUploadOnlySlots(deriveAllocationSlots(allocationFlowsForCurrentView()));
}

function visibleUploadFileSlots(slots) {
  if (allocationState.page !== "uploads") return slots;
  return slots.filter((slot) => !allocationPersistentDataBackedSlotIsHidden(slot.key));
}

function flowById(id) {
  return allocationFlowsForCurrentView().find((flow) => flow.id === id);
}

function combinedAllocationFlows() {
  return allocationFlowsForCurrentView().filter((flow) => flow.view === "combined");
}

function allocationFileRows(slots) {
  return slots.map((slot) => {
    const entry = allocationState.files[slot.key];
    const persistentEntry = entry ? null : allocationPersistentDataFile(slot.key);
    const displayEntry = entry || persistentEntry;
    const actionKey = entry ? slot.key : persistentEntry?.key || allocationLogicalKey(slot.key);
    const canFileAction = allocationState.page === "uploads";
    const sizeLabel = allocationDisplaySizeLabel(entry, persistentEntry);
    const inputId = `allocation-file-${slot.key}`;
    const fileAction = !displayEntry || !canFileAction
      ? ""
      : entry && allocationIsDesktopEntry(entry)
        ? `<button type="button" data-open-local-ref="${allocationEscape(entry.localRef)}">Öppna fil</button><button type="button" data-open-local-folder="${allocationEscape(entry.localRef)}">Mapp</button>`
        : entry
          ? `<button type="button" data-download-local-file="${allocationEscape(actionKey)}">Ladda ner</button>`
          : `<button type="button" data-download-persistent-file="${allocationEscape(actionKey)}">Ladda ner</button>`;
    return `
      <div class="allocation-file-slot ${displayEntry ? "filled" : ""}" data-allocation-drop data-drop-slot="${allocationEscape(slot.key)}">
        <div>
          <h3>${allocationEscape(allocationUploadSlotLabel(slot))}</h3>
          <p>${displayEntry ? `${allocationEscape(displayEntry.name)} ${sizeLabel ? `<span>${allocationEscape(sizeLabel)}</span>` : ""}` : "Ingen fil vald"}</p>
        </div>
        <div class="allocation-file-actions">
          <span class="allocation-file-badge">${entry ? "Inlagd" : persistentEntry ? persistentEntry.badge : "Ej fil"}</span>
          ${fileAction}
          <label class="button-like" for="${inputId}">Välj</label>
          <input id="${inputId}" type="file" hidden data-slot="${allocationEscape(slot.key)}" />
          <button type="button" class="ghost danger" data-clear-slot="${allocationEscape(slot.key)}" ${entry ? "" : "disabled"}>×</button>
        </div>
      </div>
    `;
  }).join("");
}

function renderAllocationShell(content, headerActions = "") {
  const root = document.getElementById("allocationRoot");
  if (!root) return;
  root.innerHTML = `
    <div class="section-title allocation-section-title ${headerActions ? "has-actions" : ""}">
      <span>${allocationEscape(allocationPrimaryTitle(allocationState.page))}</span>
      ${headerActions ? `<div class="allocation-title-actions">${headerActions}</div>` : ""}
    </div>
    ${content}
  `;
  bindAllocationCommonEvents(root);
}

function allocationDropSlotsForTarget(target) {
  const flowScope = target.dataset.dropScope === "flow"
    ? target
    : target.closest("[data-drop-scope='flow']");
  if (flowScope) return slotsForFlow(flowById(flowScope.dataset.flowId));
  return currentAllocationSlots();
}

function bindAllocationCommonEvents(root) {
  root.querySelectorAll("label[for]").forEach((label) => {
    const input = document.getElementById(label.getAttribute("for") || "");
    if (!input || input.type !== "file") return;
    label.addEventListener("click", async (event) => {
      if (!allocationDesktopAvailable()) return;
      event.preventDefault();
      const entries = await window.flowDesktop.pickFiles({
        accept: input.getAttribute("accept") || "",
        multiple: Boolean(input.multiple),
      });
      if (!entries.length) return;
      const slot = input.dataset.slot || "";
      const targetSlot = slot ? currentAllocationSlots().find((item) => item.key === slot) : null;
      await routeAllocationFiles(
        entries,
        targetSlot ? [targetSlot] : allocationDropSlotsForTarget(input.closest("[data-allocation-drop]") || root),
        { fallbackSlotKey: slot },
      );
    });
  });
  root.querySelectorAll("input[type='file'][data-slot]").forEach((input) => {
    input.addEventListener("change", async () => {
      const slot = input.dataset.slot;
      const file = input.files?.[0];
      if (!slot || !file) return;
      const targetSlot = currentAllocationSlots().find((item) => item.key === slot);
      await routeAllocationFiles([file], targetSlot ? [targetSlot] : currentAllocationSlots(), { fallbackSlotKey: slot });
      input.value = "";
    });
  });
  root.querySelectorAll("[data-clear-slot]").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteAllocationFile(button.dataset.clearSlot);
      renderAllocationPage();
    });
  });
  root.querySelectorAll("[data-download-persistent-file]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await downloadAllocationPersistentFile(button.dataset.downloadPersistentFile);
      } catch (error) {
        showToast(error.message || "Kunde inte ladda ner filen.", "error", 7000);
      }
    });
  });
  root.querySelectorAll("[data-download-local-file]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await downloadAllocationLocalFile(button.dataset.downloadLocalFile);
      } catch (error) {
        showToast(error.message || "Kunde inte öppna filen.", "error", 7000);
      }
    });
  });
  root.querySelectorAll("[data-open-local-ref]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await openAllocationDesktopRef(button.dataset.openLocalRef, false);
      } catch (error) {
        showToast(error.message || "Kunde inte öppna filen.", "error", 7000);
      }
    });
  });
  root.querySelectorAll("[data-open-local-folder]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await openAllocationDesktopRef(button.dataset.openLocalFolder, true);
      } catch (error) {
        showToast(error.message || "Kunde inte öppna mappen.", "error", 7000);
      }
    });
  });
  const dropTargets = root.querySelectorAll("[data-allocation-drop]");
  dropTargets.forEach((target) => {
    target.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.stopPropagation();
      target.classList.add("drag-over");
    });
    target.addEventListener("dragleave", (event) => {
      event.stopPropagation();
      target.classList.remove("drag-over");
    });
    target.addEventListener("drop", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      target.classList.remove("drag-over");
      await routeAllocationFiles(
        event.dataTransfer?.files,
        allocationDropSlotsForTarget(target),
        { fallbackSlotKey: target.dataset.dropSlot || "" },
      );
    });
  });
}

function renderUploadsView() {
  const allSlots = currentAllocationSlots();
  const slots = visibleUploadFileSlots(allSlots);
  const filled = slots.filter((slot) => allocationDisplayFile(slot.key)).length;
  renderAllocationShell(`
    <section class="allocation-panel" data-allocation-drop>
      <div class="allocation-panel-head">
        <h2>Filer</h2>
        <div>
          <span class="allocation-muted">${filled}/${slots.length} inlagda</span>
          <button type="button" class="danger" id="allocation-clear-all-files">Rensa alla</button>
          <label class="button-like primary" for="allocation-upload-all">Välj filer</label>
          <input id="allocation-upload-all" type="file" multiple hidden />
        </div>
      </div>
      ${allocationState.autoStatus ? `<p class="allocation-status">${allocationEscape(allocationState.autoStatus)}</p>` : ""}
      ${allocationState.status ? `<p class="allocation-status">${allocationEscape(allocationState.status)}</p>` : ""}
      <div class="allocation-file-grid">${allocationFileRows(slots)}</div>
    </section>
    ${renderPersistentDataFilesView()}
  `);
  document.getElementById("allocation-upload-all")?.addEventListener("change", async (event) => {
    await routeAllocationFiles(event.target.files, slots);
  });
  document.getElementById("allocation-clear-all-files")?.addEventListener("click", async () => {
    try {
      await window.clearAllUploadedFiles?.();
    } catch (error) {
      showToast(error.message || "Kunde inte rensa filerna.", "error", 7000);
    }
  });
}

function renderPersistentDataGroup(title, items) {
  const uploaded = items.filter((item) => item.uploaded).length;
  return `
    <section class="allocation-panel allocation-coredata-panel" data-allocation-drop>
      <div class="allocation-panel-head">
        <h2>${allocationEscape(title)}</h2>
        <div><span class="allocation-muted">${uploaded}/${items.length} finns</span></div>
      </div>
      <div class="allocation-file-grid compact">
        ${items.map((item) => `
          <div class="allocation-file-slot ${item.uploaded ? "filled" : ""}" data-allocation-drop>
            <div>
              <h3>${allocationEscape(item.label)}</h3>
              <p>${item.uploaded
                ? `${allocationEscape(item.name)} ${item.sizeLabel ? `<span>${allocationEscape(item.sizeLabel)}</span>` : ""}`
                : allocationEscape(item.missingText)}</p>
            </div>
            <div class="allocation-file-actions">
              <span class="allocation-file-badge">${item.uploaded ? allocationEscape(item.badge) : "Saknas"}</span>
              ${item.uploaded ? `<button type="button" data-download-persistent-file="${allocationEscape(item.key)}">Ladda ner</button>` : ""}
            </div>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function renderPersistentDataFilesView() {
  const items = allocationPersistentDataItems();
  if (!items.length) return "";
  return [
    { title: ALLOCATION_COMPILED_DATA_LABEL, items: items.filter((item) => item.kind === "compiled_data") },
    { title: "Kärnfiler", items: items.filter((item) => item.kind !== "compiled_data") },
  ]
    .filter((group) => group.items.length)
    .map((group) => renderPersistentDataGroup(group.title, group.items))
    .join("");
}

function slotsForFlow(flow) {
  return deriveAllocationSlots(flow ? [flow] : []);
}

function missingForFlow(flow) {
  const missing = (flow?.inputs || []).filter((input) => {
    if (!input.required) return false;
    const fileKey = allocationFileInputKey(input);
    if (input.apiPreferred && allocationSourceModeForFile(flow.id, fileKey, input) !== "upload") return false;
    if (input.type === "file") return !allocationDisplayFile(fileKey);
    return !allocationState.values[input.key];
  });
  for (const input of flow?.coredata || []) {
    if (input.apiPreferred && allocationSourceModeForFile(flow.id, input.key, input) !== "upload") continue;
    if (input.required && !allocationPersistentStatusFile(input.key)) missing.push({ ...input, type: "coredata" });
  }
  if (flow?.id === "prognos-report" && !allocationDisplayFile("prognos") && !allocationDisplayFile("campaign")) {
    missing.push({ key: "prognos_or_campaign", label: "Prognosfil eller Kampanjfil", type: "file" });
  }
  if (flow?.requiresSessionFlow && !allocationRequiredSessionId(flow)) {
    missing.push({
      key: "__session",
      type: "session",
      label: `${flow.requiresSessionFlow.label || "Körning"} körd`,
    });
  }
  return missing;
}

function allocationMissingRequirementLabel(item) {
  if (item.type === "session") return item.label || "Körning körd";
  if (item.type === "coredata") return item.label || ALLOCATION_PERSISTENT_DATA_LABELS[item.key] || item.key;
  if (item.type === "file") return allocationSlotLabel(allocationFileInputKey(item));
  return item.label || item.key || "Krav";
}

function allocationMissingRequirementText(missing) {
  const labels = (missing || []).map(allocationMissingRequirementLabel).filter(Boolean);
  return labels.length ? `Saknas: ${labels.join(", ")}` : "";
}


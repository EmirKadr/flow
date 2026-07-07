// @ts-check
// ---- Excelimport ----
function openImportResultModal(result) {
  const errors = result.errors || [];
  const shownErrors = errors.slice(0, 25);
  const extra = Math.max(0, errors.length - shownErrors.length);
  const rows = shownErrors.map((entry) => `
    <tr>
      <td>${entry.row}</td>
      <td>${escapeHtml(entry.name || "-")}</td>
      <td>${escapeHtml(entry.error)}</td>
    </tr>`).join("");
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal wide">
      <h2>Importresultat</h2>
      <p class="note">${result.created} skapade, ${result.skipped} hoppades över.</p>
      ${rows ? `
        <div class="modal-table-scroll">
          <table>
            <thead><tr><th>Rad</th><th>Namn</th><th>Fel</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      ` : ""}
      ${extra ? `<p class="note">${extra} fler fel visas inte här.</p>` : ""}
      <div class="actions">
        <button class="primary" id="import-result-close">Stäng</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  document.getElementById("import-result-close").addEventListener("click", () => backdrop.remove());
}

function showImportResult(result) {
  if (result.created && result.skipped) {
    showToast(`${result.created} personer importerades. ${result.skipped} rad(er) hoppades över.`, "warn", 7000);
    openImportResultModal(result);
    return;
  }
  if (result.created) {
    showToast(`${result.created} personer importerades`, "success");
    return;
  }
  if (result.skipped) {
    showToast("Inga personer importerades", "error", 7000);
    openImportResultModal(result);
    return;
  }
  showToast("Importen innehöll inga personer", "warn");
}

async function importPersonFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const importButton = document.getElementById("import-persons");
  /** @type {HTMLInputElement} */ (importButton).disabled = true;
  try {
    const result = await api.postForm("/api/persons/import", formData);
    showImportResult(result);
    await loadPersons();
  } catch (error) {
    showToast(error.message, "error", 7000);
  } finally {
    /** @type {HTMLInputElement} */ (importButton).disabled = false;
  }
}

function openBulkPersonsModal() {
  const businessColumn = currentUser?.is_super_user
    ? [{ key: "business", label: "Verksamhet", required: false, type: "select", options: businesses.map((business) => ({ value: business.code, label: business.name })) }]
    : [];
  openBulkImportGrid({
    title: "Flera nya personer",
    submitLabel: "Skapa personer",
    initialRows: 10,
    columns: [
      ...businessColumn,
      { key: "name", label: "Namn", required: true },
      { key: "noman", label: "NoMan", required: true },
      { key: "rfid_code", label: "RFID", required: false },
      { key: "collar_type", label: "Arbetstyp", required: false, type: "select", options: PERSON_COLLAR_TYPES },
      { key: "home_area", label: "Hemområde", required: false, type: "select", options: areas.map((area) => ({ value: area.name, label: area.name })) },
      { key: "home_activity", label: "Huvudaktivitet", required: false, type: "select", options: activitiesActive.map((activity) => ({ value: activity.label, label: activity.label })) },
      { key: "sort_order", label: "Sortering", required: false, type: "number" },
    ],
    onSubmit: async (rows) => {
      const result = await api.post("/api/persons/import-rows", { rows });
      showImportResult(result);
      await loadPersons();
    },
  });
}

function setupImportControls() {
  const downloadButton = document.getElementById("download-person-template");
  const importButton = document.getElementById("import-persons");
  const bulkButton = document.getElementById("bulk-persons");
  const helpButton = document.getElementById("person-import-help");
  const fileInput = document.getElementById("person-import-file");
  if (!canEditPage(currentUser, "personImport")) {
    downloadButton.hidden = true;
    importButton.hidden = true;
    if (bulkButton) bulkButton.hidden = true;
    if (helpButton) helpButton.hidden = true;
    return;
  }

  if (bulkButton) {
    bulkButton.hidden = false;
    bulkButton.addEventListener("click", openBulkPersonsModal);
  }
  setupImportHelpButton("person-import-help", "Importera personer");
  downloadButton.addEventListener("click", async () => {
    try {
      await api.download("/api/persons/import-template", "personer-importmall.xlsx");
    } catch (error) {
      showToast(error.message || "Kunde inte ladda ner importmallen.", "error", 7000);
    }
  });
  importButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    const file = /** @type {HTMLInputElement} */ (fileInput).files?.[0];
    /** @type {HTMLInputElement} */ (fileInput).value = "";
    if (!file) return;
    await importPersonFile(file);
  });
}


// ---- Ny person-modal (kvar för att kunna lägga till) ----
function openModal(person) {
  const isEdit = !!person;
  const selectedAreaId = person?.home_area_id ?? focusedAreaId();
  const selectedBusinessId = isEdit ? inferredPersonBusinessId(person) : (businessIdFromArea(selectedAreaId) ?? inferredPersonBusinessId(person));
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Redigera person" : "Ny person"}</h2>
      ${businessOptions(selectedBusinessId, isEdit)}
      <label>Namn</label>
      <input id="m-name" value="${escapeHtml(person?.name || "")}" />
      <label>NoMan</label>
      <input id="m-noman" value="${escapeHtml(person?.noman || "")}" required />
      <label>RFID</label>
      <input id="m-rfid" value="${escapeHtml(person?.rfid_code || "")}" />
      <label>Arbetstyp</label>
      <select id="m-collar-type">
        ${PERSON_COLLAR_TYPES.map((option) => `<option value="${option.value}" ${(person?.collar_type || "blue_collar") === option.value ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}
      </select>
      <label>Hemområde</label>
      <select id="m-area">
        <option value="">(inget)</option>
        ${areas.map((a) => `<option value="${a.id}" ${Number(selectedAreaId) === Number(a.id) ? "selected" : ""}>${escapeHtml(a.name)}</option>`).join("")}
      </select>
      <label>Huvudaktivitet</label>
      <select id="m-activity">
        <option value="">(inget)</option>
        ${activitiesActive.map((a) => `<option value="${a.id}" ${person?.home_activity_id === a.id ? "selected" : ""}>${escapeHtml(a.label)}</option>`).join("")}
      </select>
      <label>Sortering</label>
      <input id="m-sort" type="number" value="${person?.sort_order ?? 0}" />
      <div class="actions">
        <button id="m-cancel">Avbryt</button>
        <button class="primary" id="m-save">Spara</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  document.getElementById("m-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("m-save").addEventListener("click", async () => {
    const payload = {
      name: /** @type {HTMLInputElement} */ (document.getElementById("m-name")).value.trim(),
      noman: /** @type {HTMLInputElement} */ (document.getElementById("m-noman")).value.trim(),
      rfid_code: /** @type {HTMLInputElement} */ (document.getElementById("m-rfid")).value.trim(),
      collar_type: /** @type {HTMLInputElement} */ (document.getElementById("m-collar-type")).value || "blue_collar",
      home_area_id: /** @type {HTMLInputElement} */ (document.getElementById("m-area")).value ? Number(/** @type {HTMLInputElement} */ (document.getElementById("m-area")).value) : null,
      home_activity_id: /** @type {HTMLInputElement} */ (document.getElementById("m-activity")).value ? Number(/** @type {HTMLInputElement} */ (document.getElementById("m-activity")).value) : null,
      sort_order: Number(/** @type {HTMLInputElement} */ (document.getElementById("m-sort")).value) || 0,
    };
    if (currentUser?.is_super_user && !isEdit) {
      payload.business_id = /** @type {HTMLInputElement} */ (document.getElementById("m-business")).value ? Number(/** @type {HTMLInputElement} */ (document.getElementById("m-business")).value) : null;
    }
    if (!payload.name) { showToast("Namn krävs", "error"); return; }
    if (!payload.noman) { showToast("NoMan krävs", "error"); return; }
    try {
      if (isEdit) {
        const before = snapshotPerson(person);
        await api.put(`/api/persons/${person.id}`, payload);
        pushPersonUndo("personändring", before);
      } else {
        await api.post("/api/persons", payload);
      }
      backdrop.remove();
      await loadPersons();
    } catch (e) { showToast(e.message, "error"); }
  });
}


// ---- Schema-modal ----
const DAY_LABELS = { 1: "Måndag", 2: "Tisdag", 3: "Onsdag", 4: "Torsdag", 5: "Fredag", 6: "Lördag", 7: "Söndag" };

async function openScheduleModal(person) {
  let template;
  try {
    template = await api.get(`/api/persons/${person.id}/schedule`);
  } catch (e) {
    showToast("Kunde inte ladda schema: " + e.message, "error");
    return;
  }

  const hoursFromOpts = Array.from({ length: 18 }, (_, i) => 6 + i)
    .map((h) => `<option value="${h}">${String(h).padStart(2, "0")}:00</option>`).join("");
  const hoursToOpts = Array.from({ length: 18 }, (_, i) => 7 + i)
    .map((h) => `<option value="${h}">${String(h).padStart(2, "0")}:00</option>`).join("");
  const isHourlyWorker = !template.has_fixed_schedule;

  const rowFor = (d) => `
    <tr data-weekday="${d.weekday}">
      <td style="padding: 6px 10px; font-weight: bold;">${DAY_LABELS[d.weekday]}</td>
      <td><label><input type="checkbox" class="m-off" ${d.is_off ? "checked" : ""}/> Ledig</label></td>
      <td>Från <select class="m-from">${hoursFromOpts}</select></td>
      <td>Till <select class="m-to">${hoursToOpts}</select></td>
    </tr>`;

  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal" style="min-width: 480px;">
      <h2>Veckomall för ${escapeHtml(person.name)}</h2>
      <p class="note">Mallen används av Översikt och visar huvudaktivitet som bas i bemanningen.</p>
      <label class="modal-checkbox">
        <input id="sch-hourly" type="checkbox" ${isHourlyWorker ? "checked" : ""} />
        Timmis - ingen fast schemamall
      </label>
      <p class="note">När detta är valt har personen ingen fast schemamall. Det räknas inte som ledig tid.</p>
      <table style="margin-top: 12px;">
        <tbody id="sch-body">
          ${template.days.map(rowFor).join("")}
        </tbody>
      </table>
      <div class="actions">
        <button id="sch-default">Standard 07-16</button>
        <button id="sch-cancel">Avbryt</button>
        <button id="sch-save" class="primary">Spara</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  template.days.forEach((d) => {
    const row = backdrop.querySelector(`tr[data-weekday="${d.weekday}"]`);
    /** @type {HTMLInputElement} */ (row.querySelector(".m-from")).value = String(d.start_hour ?? 7);
    /** @type {HTMLInputElement} */ (row.querySelector(".m-to")).value = String(d.end_hour ?? 16);
    updateRowDisabled(row);
  });
  updateScheduleModalDisabled(backdrop);

  backdrop.querySelectorAll(".m-off").forEach((cb) =>
    cb.addEventListener("change", (e) => {
      updateRowDisabled(/** @type {Element} */ (e.target).closest("tr"));
    })
  );

  document.getElementById("sch-hourly").addEventListener("change", () => updateScheduleModalDisabled(backdrop));

  document.getElementById("sch-default").addEventListener("click", () => {
    /** @type {HTMLInputElement} */ (document.getElementById("sch-hourly")).checked = false;
    backdrop.querySelectorAll("tr[data-weekday]").forEach((row) => {
      const weekday = Number(/** @type {HTMLElement} */ (row).dataset.weekday);
      /** @type {HTMLInputElement} */ (row.querySelector(".m-off")).checked = weekday >= 6;
      /** @type {HTMLInputElement} */ (row.querySelector(".m-from")).value = "7";
      /** @type {HTMLInputElement} */ (row.querySelector(".m-to")).value = "16";
      updateRowDisabled(row);
    });
    updateScheduleModalDisabled(backdrop);
  });

  document.getElementById("sch-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("sch-save").addEventListener("click", async () => {
    const hasFixedSchedule = !/** @type {HTMLInputElement} */ (document.getElementById("sch-hourly")).checked;
    const days = [];
    if (hasFixedSchedule) {
      for (const row of backdrop.querySelectorAll("tr[data-weekday]")) {
        const wd = Number(/** @type {HTMLElement} */ (row).dataset.weekday);
        const isOff = /** @type {HTMLInputElement} */ (row.querySelector(".m-off")).checked;
        if (isOff) { days.push({ weekday: wd, is_off: true, start_hour: null, end_hour: null }); continue; }
        const sh = Number(/** @type {HTMLInputElement} */ (row.querySelector(".m-from")).value);
        const eh = Number(/** @type {HTMLInputElement} */ (row.querySelector(".m-to")).value);
        if (sh >= eh) {
          showToast(`${DAY_LABELS[wd]}: Från måste vara mindre än Till`, "error");
          return;
        }
        days.push({ weekday: wd, is_off: false, start_hour: sh, end_hour: eh });
      }
    }
    try {
      await api.put(`/api/persons/${person.id}/schedule`, { has_fixed_schedule: hasFixedSchedule, days });
      backdrop.remove();
      showToast("Schema sparat");
    } catch (e) { showToast(e.message, "error"); }
  });
}

function updateScheduleModalDisabled(backdrop) {
  const hourly = /** @type {HTMLInputElement} */ (document.getElementById("sch-hourly")).checked;
  backdrop.querySelectorAll("tr[data-weekday]").forEach((row) => {
    const offCheckbox = row.querySelector(".m-off");
    offCheckbox.disabled = hourly;
    updateRowDisabled(row);
  });
}

function updateRowDisabled(row) {
  const off = /** @type {HTMLInputElement | null} */ (document.getElementById("sch-hourly"))?.checked || row.querySelector(".m-off").checked;
  row.querySelector(".m-from").disabled = off;
  row.querySelector(".m-to").disabled = off;
}


// ---- Init ----
(async () => {
  currentUser = await initPage("persons");
  if (!currentUser) return;
  await loadInitial();
  await loadPersons();
  setupImportControls();
  installPersonUndoShortcut();
  const newPersonButton = document.getElementById("new-person");
  newPersonButton.hidden = !canEditPage(currentUser, "persons");
  if (canEditPage(currentUser, "persons")) newPersonButton.addEventListener("click", () => openModal(null));
  window.addEventListener("flow:areaFocusChanged", () => loadPersons());

  document.querySelectorAll("tr.filter-row input").forEach((inp) => {
    inp.addEventListener("input", () => {
      filters[/** @type {HTMLElement} */ (inp).dataset.filter] = /** @type {HTMLInputElement} */ (inp).value;
      renderRows();
    });
  });
  document.querySelectorAll("tr.sort-row th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = /** @type {HTMLElement} */ (th).dataset.sort;
      if (sortKey === key) sortAsc = !sortAsc;
      else { sortKey = key; sortAsc = true; }
      renderRows();
    });
  });
})();

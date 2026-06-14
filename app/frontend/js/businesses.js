let businesses = [];
let areas = [];
let allAreas = [];
let currentUser = null;
let businessSort = { key: "sort_order", direction: "asc" };
let areaSort = { key: "sort_order", direction: "asc" };

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function includeInactive() {
  return Boolean(document.getElementById("show-inactive")?.checked);
}

function isAllAreasMarker(area) {
  return String(area?.code || "").trim().toUpperCase() === "ANNAT";
}

function allAreasMarkerForBusiness(business) {
  return allAreas.find((area) =>
    Number(area.business_id) === Number(business.id) && isAllAreasMarker(area)
  ) || null;
}

function syncVisibleAreas() {
  areas = includeInactive() ? allAreas : allAreas.filter((area) => area.is_active !== false);
}

function sortValue(item, key) {
  if (key === "sort_order") return Number(item?.sort_order) || 0;
  if (key === "is_active") return item?.is_active !== false ? 1 : 0;
  if (key === "company_codes") return companyCodesText(item);
  return String(item?.[key] ?? "").trim().toLocaleLowerCase("sv");
}

function compareSortValues(a, b) {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), "sv", { numeric: true, sensitivity: "base" });
}

function sortByState(list, state, fallback) {
  const direction = state.direction === "desc" ? -1 : 1;
  return list.slice().sort((a, b) => {
    const result = compareSortValues(sortValue(a, state.key), sortValue(b, state.key));
    if (result !== 0) return result * direction;
    return fallback(a, b);
  });
}

function sortedBusinesses() {
  const visible = includeInactive() ? businesses : businesses.filter((business) => business.is_active !== false);
  return sortByState(visible, businessSort, (a, b) =>
    (Number(a.sort_order) || 0) - (Number(b.sort_order) || 0)
    || String(a.name || "").localeCompare(String(b.name || ""), "sv")
    || Number(a.id) - Number(b.id)
  );
}

function areasForBusiness(business) {
  const visible = areas.filter((area) => Number(area.business_id) === Number(business.id));
  return sortByState(visible, areaSort, (a, b) =>
    (Number(a.sort_order) || 0) - (Number(b.sort_order) || 0)
    || String(a.name || "").localeCompare(String(b.name || ""), "sv")
    || Number(a.id) - Number(b.id)
  );
}

function sortIndicator(state, key) {
  if (state.key !== key) return "";
  return state.direction === "asc" ? "▲" : "▼";
}

function sortButton(label, key, state, scope) {
  return `
    <button type="button" class="table-sort-button" data-${scope}-sort="${key}" aria-label="Sortera efter ${escapeHtml(label)}">
      ${escapeHtml(label)} <span class="sort-ind">${sortIndicator(state, key)}</span>
    </button>
  `;
}

function updateBusinessSortHeader() {
  document.querySelectorAll("[data-business-sort]").forEach((button) => {
    const key = button.dataset.businessSort;
    button.closest("th")?.setAttribute(
      "aria-sort",
      businessSort.key === key ? (businessSort.direction === "asc" ? "ascending" : "descending") : "none"
    );
    const indicator = button.querySelector(".sort-ind");
    if (indicator) indicator.textContent = sortIndicator(businessSort, key);
  });
}

function toggleSort(state, key) {
  if (state.key === key) {
    state.direction = state.direction === "asc" ? "desc" : "asc";
    return;
  }
  state.key = key;
  state.direction = "asc";
}

function findRecord(entityType, id) {
  const rows = entityType === "business" ? businesses : allAreas;
  return rows.find((item) => Number(item.id) === Number(id)) || null;
}

function cellLabel(entityType, field) {
  const labels = {
    business: {
      code: "Verksamhetskod",
      name: "Verksamhetsnamn",
      company_codes: "Bolag",
      sort_order: "Verksamhetssortering",
      is_active: "Verksamhet aktiv",
    },
    area: {
      code: "Områdeskod",
      name: "Områdesnamn",
      sort_order: "Områdessortering",
      is_active: "Område aktivt",
    },
  };
  return labels[entityType]?.[field] || field;
}

function displayEditableValue(entityType, record, field) {
  if (entityType === "business" && field === "company_codes") {
    return escapeHtml(companyCodesText(record));
  }
  const value = record?.[field];
  if (entityType === "area" && field === "code" && isAllAreasMarker(record)) {
    return `<span class="business-infinity-mark">∞</span><span>${escapeHtml(value)}</span>`;
  }
  return escapeHtml(value);
}

function companyCodesText(record) {
  const codes = Array.isArray(record?.company_codes) ? record.company_codes : [];
  return codes.filter(Boolean).join(", ");
}

function codePart(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_+/g, "_");
}

function normalizeCompanyCodes(rawValue) {
  const codes = [];
  const seen = new Set();
  String(rawValue || "")
    .split(/[,;\n\r]+/)
    .forEach((part) => {
      if (!part.trim()) return;
      const code = codePart(part).slice(0, 20);
      if (!code) throw new Error("Bolagskod saknar giltiga tecken.");
      if (seen.has(code)) return;
      seen.add(code);
      codes.push(code);
    });
  if (codes.length > 50) throw new Error("Max 50 bolag per verksamhet.");
  return codes;
}

function inlineInputValue(entityType, record, field) {
  if (entityType === "business" && field === "company_codes") return companyCodesText(record);
  return record?.[field] ?? "";
}

function inlineValueChanged(entityType, field, nextValue, originalValue) {
  if (entityType === "business" && field === "company_codes") {
    const originalCodes = Array.isArray(originalValue) ? originalValue : [];
    return JSON.stringify(nextValue) !== JSON.stringify(originalCodes);
  }
  return String(nextValue) !== String(originalValue ?? "");
}

function editableCell(entityType, record, field, kind = "text") {
  return `
    <td
      class="editable-cell"
      tabindex="0"
      title="Klicka för att ändra"
      data-inline-edit="${entityType}"
      data-id="${record.id}"
      data-field="${field}"
      data-kind="${kind}"
    >${displayEditableValue(entityType, record, field)}</td>
  `;
}

function activeCell(entityType, record) {
  const checked = record.is_active !== false ? "checked" : "";
  const label = record.is_active !== false ? "Ja" : "Nej";
  return `
    <td>
      <label class="inline-active-toggle">
        <input type="checkbox" data-inline-boolean="${entityType}" data-id="${record.id}" data-field="is_active" ${checked} />
        <span>${label}</span>
      </label>
    </td>
  `;
}

function allAreasControl(business) {
  const marker = allAreasMarkerForBusiness(business);
  if (marker?.is_active !== false) {
    return `<span class="business-areas-pill"><span class="business-infinity-mark">∞</span> aktiv</span>`;
  }
  const label = marker ? "Återaktivera ∞" : "Lägg till ∞";
  return `<button type="button" data-add-all-areas="${business.id}">${label}</button>`;
}

function renderAreasTable(business) {
  const rows = areasForBusiness(business).map((area) => `
    <tr class="${isAllAreasMarker(area) ? "all-areas-marker-row" : ""}">
      ${editableCell("area", area, "code")}
      ${editableCell("area", area, "name")}
      ${editableCell("area", area, "sort_order", "number")}
      ${activeCell("area", area)}
      <td class="business-area-actions">
        <button type="button" class="danger" data-delete-area="${area.id}">Ta bort</button>
      </td>
    </tr>
  `).join("");
  if (!rows) {
    return `<div class="business-areas-empty">Inga områden</div>`;
  }
  return `
    <div class="business-areas-table-wrap">
      <table class="business-areas-table">
        <thead>
          <tr>
            <th>${sortButton("Kod", "code", areaSort, "area")}</th>
            <th>${sortButton("Namn", "name", areaSort, "area")}</th>
            <th>${sortButton("Sortering", "sort_order", areaSort, "area")}</th>
            <th>${sortButton("Aktiv", "is_active", areaSort, "area")}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderBusinesses() {
  const body = document.getElementById("businesses-body");
  body.innerHTML = sortedBusinesses().map((business) => `
    <tr class="business-row">
      ${editableCell("business", business, "code")}
      ${editableCell("business", business, "name")}
      ${editableCell("business", business, "company_codes")}
      ${editableCell("business", business, "sort_order", "number")}
      ${activeCell("business", business)}
    </tr>
    <tr class="business-areas-row">
      <td colspan="5">
        <div class="business-areas-header">
          <span>Områden</span>
          <span class="business-areas-header-actions">
            ${allAreasControl(business)}
            <button type="button" data-new-area="${business.id}">+ Nytt område</button>
          </span>
        </div>
        ${renderAreasTable(business)}
      </td>
    </tr>
  `).join("");
  updateBusinessSortHeader();
  bindBusinessEvents(body);
}

function normalizeInlineValue(entityType, field, kind, rawValue) {
  if (kind === "number") {
    const value = Number(String(rawValue || "").replace(",", "."));
    if (!Number.isFinite(value)) {
      return { ok: false, message: `${cellLabel(entityType, field)} måste vara ett tal.` };
    }
    return { ok: true, value: Math.trunc(value) };
  }
  const value = String(rawValue ?? "").trim();
  if (entityType === "business" && field === "company_codes") {
    try {
      return { ok: true, value: normalizeCompanyCodes(value) };
    } catch (error) {
      return { ok: false, message: error.message || "Bolag kunde inte tolkas." };
    }
  }
  if ((field === "code" || field === "name") && !value) {
    return { ok: false, message: field === "code" ? "Kod krävs." : "Namn krävs." };
  }
  return { ok: true, value };
}

function updateLocalArea(updated) {
  allAreas = allAreas.map((area) => Number(area.id) === Number(updated.id) ? updated : area);
  if (!allAreas.some((area) => Number(area.id) === Number(updated.id))) {
    allAreas.push(updated);
  }
  syncVisibleAreas();
  if (typeof setAreaFocusAreas === "function") setAreaFocusAreas(allAreas, currentUser);
}

async function saveEntityField(entityType, id, field, value) {
  const record = findRecord(entityType, id);
  if (!record) return;
  const payload = { [field]: value };
  if (entityType === "business") {
    const updated = await api.put(`/api/businesses/${record.id}`, payload);
    businesses = businesses.map((business) => Number(business.id) === Number(updated.id) ? updated : business);
    showToast(`${cellLabel(entityType, field)} sparades.`, "success", 2500);
    renderBusinesses();
    return;
  }
  const updated = await api.put(`/api/areas/${record.id}`, payload);
  updateLocalArea(updated);
  showToast(`${cellLabel(entityType, field)} sparades.`, "success", 2500);
  renderBusinesses();
}

function startInlineEdit(cell) {
  if (cell.querySelector("input")) return;
  const entityType = cell.dataset.inlineEdit;
  const id = Number(cell.dataset.id);
  const field = cell.dataset.field;
  const kind = cell.dataset.kind || "text";
  const record = findRecord(entityType, id);
  if (!record) return;
  const original = record[field];
  const input = document.createElement("input");
  input.className = "inline-table-input";
  input.type = kind === "number" ? "number" : "text";
  input.value = inlineInputValue(entityType, record, field);
  if (field === "code") input.maxLength = 20;
  if (field === "name") input.maxLength = 100;

  let settled = false;
  const cancel = () => {
    settled = true;
    renderBusinesses();
  };
  const save = async () => {
    if (settled) return;
    settled = true;
    const normalized = normalizeInlineValue(entityType, field, kind, input.value);
    if (!normalized.ok) {
      showToast(normalized.message, "warn", 3000);
      renderBusinesses();
      return;
    }
    const nextValue = normalized.value;
    if (!inlineValueChanged(entityType, field, nextValue, original)) {
      renderBusinesses();
      return;
    }
    cell.classList.add("is-saving");
    input.disabled = true;
    try {
      await saveEntityField(entityType, id, field, nextValue);
    } catch (error) {
      showToast(error.message || "Kunde inte spara ändringen.", "error", 7000);
      renderBusinesses();
    }
  };

  cell.classList.add("is-editing");
  cell.textContent = "";
  cell.appendChild(input);
  input.focus();
  input.select();
  input.addEventListener("blur", save);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      input.blur();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancel();
    }
  });
}

async function saveBooleanField(input) {
  const entityType = input.dataset.inlineBoolean;
  const id = Number(input.dataset.id);
  const field = input.dataset.field;
  const value = input.checked;
  input.disabled = true;
  try {
    await saveEntityField(entityType, id, field, value);
  } catch (error) {
    showToast(error.message || "Kunde inte spara ändringen.", "error", 7000);
    renderBusinesses();
  }
}

async function ensureAllAreasMarker(business) {
  const existing = allAreasMarkerForBusiness(business);
  const payload = {
    code: "ANNAT",
    name: existing?.name || "Annat",
    sort_order: Number(existing?.sort_order) || 99,
    is_active: true,
  };
  try {
    const updated = existing
      ? await api.put(`/api/areas/${existing.id}`, payload)
      : await api.post("/api/areas", { ...payload, business_id: Number(business.id) });
    updateLocalArea(updated);
    showToast("∞ Alla områden aktiverades för verksamheten.", "success", 3000);
    renderBusinesses();
  } catch (error) {
    showToast(error.message || "Kunde inte aktivera ∞.", "error", 7000);
  }
}

function bindBusinessEvents(body) {
  body.querySelectorAll("[data-new-area]").forEach((button) => {
    button.addEventListener("click", () => {
      const business = businesses.find((item) => Number(item.id) === Number(button.dataset.newArea));
      openAreaModal(business);
    });
  });
  body.querySelectorAll("[data-add-all-areas]").forEach((button) => {
    button.addEventListener("click", () => {
      const business = businesses.find((item) => Number(item.id) === Number(button.dataset.addAllAreas));
      if (business) ensureAllAreasMarker(business);
    });
  });
  body.querySelectorAll("[data-delete-area]").forEach((button) => {
    button.addEventListener("click", async () => {
      const area = allAreas.find((item) => Number(item.id) === Number(button.dataset.deleteArea));
      if (!area) return;
      if (!confirm("Ta bort området? Om det används inaktiveras det i stället.")) return;
      try {
        await api.del(`/api/areas/${area.id}`);
        showToast("Området togs bort eller inaktiverades.", "success", 3000);
        await loadBusinesses();
      } catch (error) {
        showToast(error.message || "Kunde inte ta bort området.", "error", 7000);
      }
    });
  });
  body.querySelectorAll("[data-area-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      toggleSort(areaSort, button.dataset.areaSort);
      renderBusinesses();
    });
  });
  body.querySelectorAll("[data-inline-edit]").forEach((cell) => {
    cell.addEventListener("click", () => startInlineEdit(cell));
    cell.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      startInlineEdit(cell);
    });
  });
  body.querySelectorAll("[data-inline-boolean]").forEach((input) => {
    input.addEventListener("change", () => saveBooleanField(input));
  });
}

async function loadBusinesses() {
  const includeInactive = document.getElementById("show-inactive").checked;
  const [loadedBusinesses, loadedAreas] = await Promise.all([
    api.get(`/api/businesses?include_inactive=${includeInactive}`),
    api.get("/api/areas?include_inactive=true"),
  ]);
  businesses = loadedBusinesses;
  allAreas = loadedAreas;
  syncVisibleAreas();
  if (typeof setAreaFocusAreas === "function") setAreaFocusAreas(loadedAreas, currentUser);
  renderBusinesses();
}

function openBusinessModal() {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>Ny verksamhet</h2>
      <label>Namn <input id="m-name" maxlength="100" /></label>
      <label>Bolag <input id="m-company-codes" maxlength="300" /></label>
      <label>Sortering <input id="m-sort" type="number" value="0" /></label>
      <label class="modal-checkbox"><input id="m-active" type="checkbox" checked /> Aktiv</label>
      <div class="actions">
        <button type="button" id="cancel">Avbryt</button>
        <button type="button" class="primary" id="save" data-enter-default>Spara</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);
  backdrop.querySelector("#cancel").addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("#save").addEventListener("click", async () => {
    let companyCodes = [];
    try {
      companyCodes = normalizeCompanyCodes(document.getElementById("m-company-codes").value);
    } catch (error) {
      showToast(error.message || "Bolag kunde inte tolkas.", "warn", 3000);
      return;
    }
    const payload = {
      name: document.getElementById("m-name").value.trim(),
      company_codes: companyCodes,
      sort_order: Number(document.getElementById("m-sort").value) || 0,
      is_active: document.getElementById("m-active").checked,
    };
    if (!payload.name) {
      showToast("Namn krävs.", "warn", 3000);
      return;
    }
    try {
      await api.post("/api/businesses", payload);
      backdrop.remove();
      await loadBusinesses();
    } catch (error) {
      showToast(error.message || "Kunde inte skapa verksamheten.", "error", 7000);
    }
  });
}

function openAreaModal(business) {
  if (!business) return;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>Nytt område</h2>
      <label>Verksamhet <input value="${escapeHtml(business.name)}" disabled /></label>
      <label>Namn <input id="m-area-name" maxlength="100" /></label>
      <label>Sortering <input id="m-area-sort" type="number" value="0" /></label>
      <label class="modal-checkbox"><input id="m-area-active" type="checkbox" checked /> Aktiv</label>
      <div class="actions">
        <button type="button" id="area-cancel">Avbryt</button>
        <button type="button" class="primary" id="area-save" data-enter-default>Spara</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);
  backdrop.querySelector("#area-cancel").addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("#area-save").addEventListener("click", async () => {
    const payload = {
      business_id: Number(business.id),
      name: document.getElementById("m-area-name").value.trim(),
      sort_order: Number(document.getElementById("m-area-sort").value) || 0,
      is_active: document.getElementById("m-area-active").checked,
    };
    if (!payload.name) {
      showToast("Namn krävs.", "warn", 3000);
      return;
    }
    try {
      await api.post("/api/areas", payload);
      backdrop.remove();
      await loadBusinesses();
    } catch (error) {
      showToast(error.message || "Kunde inte spara området.", "error", 7000);
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  currentUser = await initPage("businesses", { requireSuperUser: true });
  if (!currentUser) return;
  document.getElementById("new-business").addEventListener("click", () => openBusinessModal());
  document.getElementById("show-inactive").addEventListener("change", loadBusinesses);
  document.querySelectorAll("[data-business-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      toggleSort(businessSort, button.dataset.businessSort);
      renderBusinesses();
    });
  });
  updateBusinessSortHeader();
  await loadBusinesses();
});

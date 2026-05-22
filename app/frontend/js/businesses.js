let businesses = [];
let areas = [];
let currentUser = null;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function areasForBusiness(business) {
  return areas
    .filter((area) => Number(area.business_id) === Number(business.id))
    .sort((a, b) =>
      (Number(a.sort_order) || 0) - (Number(b.sort_order) || 0)
      || String(a.name || "").localeCompare(String(b.name || ""), "sv")
    );
}

function renderAreasTable(business) {
  const rows = areasForBusiness(business).map((area) => `
    <tr>
      <td>${escapeHtml(area.code)}</td>
      <td>${escapeHtml(area.name)}</td>
      <td>${Number(area.sort_order) || 0}</td>
      <td>${area.is_active ? "Ja" : "Nej"}</td>
      <td class="business-area-actions">
        <button type="button" data-edit-area="${area.id}">Redigera</button>
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
            <th>Kod</th>
            <th>Namn</th>
            <th>Sortering</th>
            <th>Aktiv</th>
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
  body.innerHTML = businesses.map((business) => `
    <tr class="business-row">
      <td>${escapeHtml(business.code)}</td>
      <td>${escapeHtml(business.name)}</td>
      <td>${Number(business.sort_order) || 0}</td>
      <td>${business.is_active ? "Ja" : "Nej"}</td>
      <td><button type="button" data-edit-business="${business.id}">Redigera</button></td>
    </tr>
    <tr class="business-areas-row">
      <td colspan="5">
        <div class="business-areas-header">
          <span>Områden</span>
          <button type="button" data-new-area="${business.id}">+ Nytt område</button>
        </div>
        ${renderAreasTable(business)}
      </td>
    </tr>
  `).join("");
  body.querySelectorAll("[data-edit-business]").forEach((button) => {
    button.addEventListener("click", () => {
      const business = businesses.find((item) => Number(item.id) === Number(button.dataset.editBusiness));
      openBusinessModal(business);
    });
  });
  body.querySelectorAll("[data-new-area]").forEach((button) => {
    button.addEventListener("click", () => {
      const business = businesses.find((item) => Number(item.id) === Number(button.dataset.newArea));
      openAreaModal(business);
    });
  });
  body.querySelectorAll("[data-edit-area]").forEach((button) => {
    button.addEventListener("click", () => {
      const area = areas.find((item) => Number(item.id) === Number(button.dataset.editArea));
      const business = businesses.find((item) => Number(item.id) === Number(area?.business_id));
      openAreaModal(business, area);
    });
  });
  body.querySelectorAll("[data-delete-area]").forEach((button) => {
    button.addEventListener("click", async () => {
      const area = areas.find((item) => Number(item.id) === Number(button.dataset.deleteArea));
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
}

async function loadBusinesses() {
  const includeInactive = document.getElementById("show-inactive").checked;
  const [loadedBusinesses, loadedAreas] = await Promise.all([
    api.get(`/api/businesses?include_inactive=${includeInactive}`),
    api.get("/api/areas?include_inactive=true"),
  ]);
  businesses = loadedBusinesses;
  areas = includeInactive ? loadedAreas : loadedAreas.filter((area) => area.is_active !== false);
  if (typeof setAreaFocusAreas === "function") setAreaFocusAreas(loadedAreas, currentUser);
  renderBusinesses();
}

function openBusinessModal(business = null) {
  const isEdit = Boolean(business);
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Redigera verksamhet" : "Ny verksamhet"}</h2>
      <label>Kod <input id="m-code" value="${escapeHtml(business?.code || "")}" ${isEdit ? "disabled" : ""} maxlength="20" /></label>
      <label>Namn <input id="m-name" value="${escapeHtml(business?.name || "")}" maxlength="100" /></label>
      <label>Sortering <input id="m-sort" type="number" value="${Number(business?.sort_order) || 0}" /></label>
      <label class="table-checkbox-label"><input id="m-active" type="checkbox" ${business?.is_active !== false ? "checked" : ""} /> Aktiv</label>
      <div class="actions">
        <button type="button" id="cancel">Avbryt</button>
        <button type="button" class="primary" id="save" data-enter-default>Spara</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);
  backdrop.querySelector("#cancel").addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("#save").addEventListener("click", async () => {
    const payload = {
      code: document.getElementById("m-code").value.trim(),
      name: document.getElementById("m-name").value.trim(),
      sort_order: Number(document.getElementById("m-sort").value) || 0,
      is_active: document.getElementById("m-active").checked,
    };
    if (!payload.code || !payload.name) {
      showToast("Kod och namn krävs.", "warn", 3000);
      return;
    }
    if (isEdit) {
      delete payload.code;
      await api.put(`/api/businesses/${business.id}`, payload);
    } else {
      await api.post("/api/businesses", payload);
    }
    backdrop.remove();
    await loadBusinesses();
  });
}

function openAreaModal(business, area = null) {
  if (!business) return;
  const isEdit = Boolean(area);
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Redigera område" : "Nytt område"}</h2>
      <label>Verksamhet <input value="${escapeHtml(business.name)}" disabled /></label>
      <label>Kod <input id="m-area-code" value="${escapeHtml(area?.code || "")}" maxlength="20" /></label>
      <label>Namn <input id="m-area-name" value="${escapeHtml(area?.name || "")}" maxlength="100" /></label>
      <label>Sortering <input id="m-area-sort" type="number" value="${Number(area?.sort_order) || 0}" /></label>
      <label class="table-checkbox-label"><input id="m-area-active" type="checkbox" ${area?.is_active !== false ? "checked" : ""} /> Aktiv</label>
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
      code: document.getElementById("m-area-code").value.trim().toUpperCase(),
      name: document.getElementById("m-area-name").value.trim(),
      sort_order: Number(document.getElementById("m-area-sort").value) || 0,
      is_active: document.getElementById("m-area-active").checked,
    };
    if (!payload.code || !payload.name) {
      showToast("Kod och namn krävs.", "warn", 3000);
      return;
    }
    try {
      if (isEdit) {
        await api.put(`/api/areas/${area.id}`, payload);
      } else {
        payload.business_id = Number(business.id);
        await api.post("/api/areas", payload);
      }
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
  await loadBusinesses();
});

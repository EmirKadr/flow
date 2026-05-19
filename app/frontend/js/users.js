let currentUser = null;
let users = [];
let areas = [];
let appSettings = {
  lock_foreign_schedule_cells: false,
};
let roleViewAccess = {};

const ROLE_OPTIONS = [
  { value: "leader", label: "Arbetsledare" },
  { value: "staffing_manager", label: "Bemanningsansvarig" },
  { value: "admin", label: "Administratör" },
  { value: "warehouse_clerk", label: "Lagerkontorist" },
  { value: "article_placer", label: "Artikelplacerare" },
  { value: "viewer", label: "Visning" },
];
const ROLE_ACCESS_LEVEL_OPTIONS = [
  { value: "none", label: "Ingen" },
  { value: "view", label: "Visa" },
  { value: "edit", label: "Redigera" },
];
const VIEW_ACCESS_OPTIONS = [
  { id: "schedule", label: "Bemanning" },
  { id: "overview", label: "Översikt" },
  { id: "productivity", label: "Produktivitet" },
  { id: "allocationUploads", label: "Uppladdningar" },
  { id: "allocationProcess", label: "Bearbeta" },
  { id: "allocationSplit", label: "Dela" },
  { id: "allocationTrace", label: "Härleda" },
  { id: "persons", label: "Personer" },
  { id: "stallen", label: "Ställen" },
  { id: "analytics", label: "Historik" },
  { id: "users", label: "Användare" },
];

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function rolesForUser(user) {
  const rawRoles = Array.isArray(user?.roles) && user.roles.length ? user.roles : [user?.role || "leader"];
  const roles = [...new Set(rawRoles.map((role) => String(role || "").trim()).filter(Boolean))];
  return roles.length ? roles : ["leader"];
}

function primaryRoleFromRoles(roles) {
  if (roles.includes("admin")) return "admin";
  if (roles.includes("staffing_manager")) return "staffing_manager";
  if (roles.includes("leader")) return "leader";
  if (roles.includes("warehouse_clerk")) return "warehouse_clerk";
  if (roles.includes("article_placer")) return "article_placer";
  if (roles.includes("viewer")) return "viewer";
  return "leader";
}

function roleLabel(user) {
  const labels = rolesForUser(user).map((role) => ROLE_OPTIONS.find((option) => option.value === role)?.label || role);
  if (user?.is_super_user) labels.unshift("Super User");
  return [...new Set(labels)].join(", ");
}

function areaName(areaId) {
  if (areaId == null) return "-";
  const area = areas.find((item) => Number(item.id) === Number(areaId));
  return area ? area.name : `Avdelning #${areaId}`;
}

function passwordStatus(user) {
  return user?.must_change_password ? "Väntar" : "Skapat";
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("sv-SE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function loadUsers() {
  const includeInactive = document.getElementById("show-inactive").checked;
  users = await api.get(`/api/users?include_inactive=${includeInactive}`);
  renderUsers();
}

async function loadSettings() {
  appSettings = await api.get("/api/settings");
  document.getElementById("lock-foreign-schedule-cells").checked = !!appSettings.lock_foreign_schedule_cells;
}

async function loadRoleViewAccess() {
  const response = await api.get("/api/settings/role-access");
  roleViewAccess = normalizeRoleViewAccess(response?.access || {});
  cacheRoleViewAccess(roleViewAccess);
}

async function loadAreas() {
  areas = await api.get("/api/areas?include_inactive=true");
}

function setupSettingsControls() {
  const checkbox = document.getElementById("lock-foreign-schedule-cells");
  checkbox.addEventListener("change", async () => {
    const previous = !checkbox.checked;
    try {
      appSettings = await api.put("/api/settings", {
        lock_foreign_schedule_cells: checkbox.checked,
      });
      checkbox.checked = !!appSettings.lock_foreign_schedule_cells;
      showToast("Inställning sparad", "success", 2000);
    } catch (error) {
      checkbox.checked = previous;
      showToast(error.message, "error");
    }
  });
}

function roleAccessSelect(role, viewId) {
  const value = roleViewAccess?.[role]?.[viewId] || "none";
  return `
    <select data-role="${escapeHtml(role)}" data-view="${escapeHtml(viewId)}">
      ${ROLE_ACCESS_LEVEL_OPTIONS.map((option) => `
        <option value="${option.value}" ${value === option.value ? "selected" : ""}>${escapeHtml(option.label)}</option>
      `).join("")}
    </select>
  `;
}

function renderRoleAccessTable(container) {
  const roles = window.ROLE_VIEW_ROLES || ROLE_OPTIONS;
  container.innerHTML = `
    <div class="modal-table-scroll role-access-scroll">
      <table class="role-access-table">
        <thead>
          <tr>
            <th>Vy</th>
            ${roles.map((role) => `<th>${escapeHtml(role.label)}</th>`).join("")}
          </tr>
        </thead>
        <tbody>
          ${VIEW_ACCESS_OPTIONS.map((view) => `
            <tr>
              <th>${escapeHtml(view.label)}</th>
              ${roles.map((role) => `<td>${roleAccessSelect(role.value, view.id)}</td>`).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

async function openRoleAccessModal() {
  try {
    await loadRoleViewAccess();
  } catch (error) {
    showToast(error.message || "Kunde inte läsa vybehörigheter.", "error", 7000);
    return;
  }

  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal wide role-access-modal">
      <h2>Vybehörigheter</h2>
      <p class="note">Super User har alltid full åtkomst. Övriga roller kan få ingen åtkomst, bara visa eller redigera per vy.</p>
      <div id="role-access-table"></div>
      <div class="actions">
        <button type="button" id="role-access-defaults">Standard</button>
        <button type="button" id="role-access-cancel">Avbryt</button>
        <button type="button" class="primary" id="role-access-save">Spara</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);
  const tableHost = backdrop.querySelector("#role-access-table");
  renderRoleAccessTable(tableHost);

  backdrop.querySelector("#role-access-cancel").addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("#role-access-defaults").addEventListener("click", () => {
    roleViewAccess = roleViewDefaultAccess();
    renderRoleAccessTable(tableHost);
  });
  backdrop.querySelector("#role-access-save").addEventListener("click", async () => {
    const saveButton = backdrop.querySelector("#role-access-save");
    saveButton.disabled = true;
    const next = roleViewDefaultAccess();
    tableHost.querySelectorAll("select[data-role][data-view]").forEach((select) => {
      next[select.dataset.role][select.dataset.view] = select.value;
    });
    try {
      const response = await api.put("/api/settings/role-access", { access: roleViewAccessPayload(next) });
      roleViewAccess = normalizeRoleViewAccess(response?.access || next);
      cacheRoleViewAccess(roleViewAccess);
      backdrop.remove();
      showToast("Vybehörigheter sparades.", "success", 2500);
    } catch (error) {
      saveButton.disabled = false;
      showToast(error.message || "Kunde inte spara vybehörigheter.", "error", 7000);
    }
  });
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) backdrop.remove();
  });
}

function renderUsers() {
  const tbody = document.getElementById("users-body");
  tbody.innerHTML = "";

  users.forEach((user) => {
    const tr = document.createElement("tr");
    const selfLabel = user.id === currentUser.id ? " (du)" : "";
    tr.innerHTML = `
      <td>${escapeHtml(user.username)}${escapeHtml(selfLabel)}</td>
      <td>${escapeHtml(user.display_name || "-")}</td>
      <td>${escapeHtml(roleLabel(user))}</td>
      <td>${escapeHtml(areaName(user.area_id))}</td>
      <td>${user.is_active ? "Ja" : "Nej"}</td>
      <td>${escapeHtml(passwordStatus(user))}</td>
      <td>${escapeHtml(formatDate(user.created_at))}</td>
      <td>
        <button data-edit="${user.id}">Redigera</button>
        ${user.is_active ? `<button data-toggle="${user.id}" class="danger">Inaktivera</button>` : `<button data-toggle="${user.id}">Aktivera</button>`}
      </td>`;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll("button[data-edit]").forEach((button) =>
    button.addEventListener("click", () => openModal(users.find((user) => user.id === Number(button.dataset.edit))))
  );
  tbody.querySelectorAll("button[data-toggle]").forEach((button) =>
    button.addEventListener("click", async () => {
      const user = users.find((item) => item.id === Number(button.dataset.toggle));
      if (!user) return;
      const nextActive = !user.is_active;
      const confirmText = nextActive ? "Aktivera användaren?" : "Inaktivera användaren?";
      if (!confirm(confirmText)) return;
      try {
        await api.put(`/api/users/${user.id}`, { is_active: nextActive });
        await loadUsers();
      } catch (error) {
        showToast(error.message, "error");
      }
    })
  );
}

function openModal(user) {
  const isEdit = !!user;
  const selectedRoles = rolesForUser(user);
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Redigera användare" : "Ny användare"}</h2>
      <label>Användarnamn</label>
      <input id="m-username" autocomplete="username" value="${escapeHtml(user?.username || "")}" />
      <label>Visningsnamn</label>
      <input id="m-display-name" value="${escapeHtml(user?.display_name || "")}" />
      <label>Roller</label>
      <div class="role-checks" id="m-roles">
        ${ROLE_OPTIONS.map((option) => `
          <label class="role-check">
            <input type="checkbox" name="m-role" value="${option.value}" ${selectedRoles.includes(option.value) ? "checked" : ""} />
            <span>${escapeHtml(option.label)}</span>
          </label>
        `).join("")}
      </div>
      <label>Avdelning</label>
      <select id="m-area">
        <option value="">Ingen förinställning</option>
        ${areas.map((area) => `<option value="${area.id}" ${Number(user?.area_id) === Number(area.id) ? "selected" : ""}>${escapeHtml(area.name)}</option>`).join("")}
      </select>
      <label>${isEdit ? "Nytt lösenord" : "Lösenord"}</label>
      <input id="m-password" type="password" autocomplete="new-password" />
      <p class="note">${isEdit ? "Lämna lösenord tomt om det inte ska ändras." : "Lämna tomt om användaren ska skapa sitt lösenord vid första inloggningen. Annars minst 8 tecken."}</p>
      <label class="modal-checkbox"><input id="m-active" type="checkbox" ${user?.is_active !== false ? "checked" : ""} /> Aktiv</label>
      <div class="actions">
        <button id="m-cancel">Avbryt</button>
        <button class="primary" id="m-save">Spara</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  document.getElementById("m-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("m-save").addEventListener("click", async () => {
    const password = document.getElementById("m-password").value;
    const roles = Array.from(document.querySelectorAll('input[name="m-role"]:checked')).map((input) => input.value);
    const payload = {
      username: document.getElementById("m-username").value.trim(),
      display_name: document.getElementById("m-display-name").value.trim() || null,
      role: primaryRoleFromRoles(roles),
      roles,
      area_id: document.getElementById("m-area").value ? Number(document.getElementById("m-area").value) : null,
      is_active: document.getElementById("m-active").checked,
    };

    if (!payload.username) {
      showToast("Användarnamn krävs", "error");
      return;
    }
    if (roles.length === 0) {
      showToast("Välj minst en roll", "error");
      return;
    }
    if (password && password.length < 8) {
      showToast("Lösenord måste vara minst 8 tecken", "error");
      return;
    }
    if (password) payload.password = password;

    try {
      if (isEdit) {
        await api.put(`/api/users/${user.id}`, payload);
      } else {
        await api.post("/api/users", payload);
      }
      backdrop.remove();
      await loadUsers();
    } catch (error) {
      showToast(error.message, "error");
    }
  });
}

function openImportResultModal(result) {
  const errors = result.errors || [];
  const shownErrors = errors.slice(0, 25);
  const extra = Math.max(0, errors.length - shownErrors.length);
  const rows = shownErrors.map((entry) => `
    <tr>
      <td>${entry.row}</td>
      <td>${escapeHtml(entry.username || "-")}</td>
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
            <thead><tr><th>Rad</th><th>Användarnamn</th><th>Fel</th></tr></thead>
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
    showToast(`${result.created} användare importerades. ${result.skipped} rad(er) hoppades över.`, "warn", 7000);
    openImportResultModal(result);
    return;
  }
  if (result.created) {
    showToast(`${result.created} användare importerades`, "success");
    return;
  }
  if (result.skipped) {
    showToast("Inga användare importerades", "error", 7000);
    openImportResultModal(result);
    return;
  }
  showToast("Excel-filen innehöll inga användare", "warn");
}

async function importUserFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const importButton = document.getElementById("import-users");
  importButton.disabled = true;
  try {
    const result = await api.postForm("/api/users/import", formData);
    showImportResult(result);
    await loadUsers();
  } catch (error) {
    showToast(error.message, "error", 7000);
  } finally {
    importButton.disabled = false;
  }
}

function setupImportControls() {
  const downloadButton = document.getElementById("download-user-template");
  const importButton = document.getElementById("import-users");
  const roleAccessButton = document.getElementById("role-view-access");
  const helpButton = document.getElementById("user-import-help");
  const fileInput = document.getElementById("user-import-file");

  if (!currentUser?.is_super_user) return;

  downloadButton.hidden = false;
  importButton.hidden = false;
  roleAccessButton.hidden = false;
  helpButton.hidden = false;

  setupImportHelpButton("user-import-help", "Importera användare");
  downloadButton.addEventListener("click", () => {
    window.location.href = "/api/users/import-template";
  });
  importButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files?.[0];
    fileInput.value = "";
    if (!file) return;
    await importUserFile(file);
  });
  roleAccessButton.addEventListener("click", openRoleAccessModal);
}

(async () => {
  currentUser = await initPage("users", { requireAdmin: true });
  if (!currentUser) return;

  setupImportControls();
  setupSettingsControls();
  await loadSettings();
  await loadAreas();
  await loadUsers();
  document.getElementById("new-user").addEventListener("click", () => openModal(null));
  document.getElementById("show-inactive").addEventListener("change", loadUsers);
})();

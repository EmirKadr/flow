let currentUser = null;
let users = [];
let areas = [];
let businesses = [];
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
const SUPER_USER_ROLE_OPTION = { value: "super_user", label: "Super User" };
const USER_ROLE_OPTIONS = [...ROLE_OPTIONS, SUPER_USER_ROLE_OPTION];

const ROLE_ACCESS_LEVEL_OPTIONS = [
  { value: "none", label: "Ingen" },
  { value: "view", label: "Visa" },
  { value: "edit", label: "Redigera" },
];
const ROLE_ACCESS_LEVEL_ORDER = ROLE_ACCESS_LEVEL_OPTIONS.map((option) => option.value);
const VIEW_ACCESS_OPTIONS = [
  { id: "schedule", label: "Bemanning" },
  { id: "overview", label: "Översikt" },
  { id: "productivity", label: "Produktivitet" },
  { id: "dataFetch", label: "Hämta data" },
  { id: "allocationUploads", label: "Uppladdningar" },
  { id: "allocationProcess", label: "Bearbeta" },
  { id: "allocationProcessMatrix", label: "Bearbeta-matris" },
  { id: "allocationSplit", label: "Dela" },
  { id: "persons", label: "Personer" },
  { id: "personSortOrder", label: "Personsortering" },
  { id: "personImport", label: "Personimport" },
  { id: "activities", label: "Aktiviteter" },
  { id: "activityImport", label: "Aktivitetsimport" },
  { id: "areas", label: "Områden" },
  { id: "analytics", label: "Historik" },
  { id: "users", label: "Användare" },
  { id: "userImport", label: "Användarimport" },
  { id: "businesses", label: "Verksamheter" },
  { id: "appSettings", label: "Appinställningar" },
  { id: "sidebarLayout", label: "Menyordning" },
  { id: "roleAccess", label: "Vybehörigheter" },
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
  if (roles.includes("super_user")) return "super_user";
  if (roles.includes("admin")) return "admin";
  if (roles.includes("staffing_manager")) return "staffing_manager";
  if (roles.includes("leader")) return "leader";
  if (roles.includes("warehouse_clerk")) return "warehouse_clerk";
  if (roles.includes("article_placer")) return "article_placer";
  if (roles.includes("viewer")) return "viewer";
  return "leader";
}

function roleLabel(user) {
  const labels = rolesForUser(user).map((role) => USER_ROLE_OPTIONS.find((option) => option.value === role)?.label || role);
  if (user?.is_super_user) labels.unshift("Super User");
  return [...new Set(labels)].join(", ");
}

function editableRoleOptions() {
  return currentUser?.is_super_user ? USER_ROLE_OPTIONS : ROLE_OPTIONS;
}

function roleSelectOptionsHtml(options, selectedValue = "") {
  return [
    '<option value="">Välj roll</option>',
    ...options.map((option) => (
      `<option value="${escapeHtml(option.value)}" ${option.value === selectedValue ? "selected" : ""}>${escapeHtml(option.label)}</option>`
    )),
  ].join("");
}

function roleFieldHtml({ isEdit, isDemoTarget, selectedRoles, roleOptions }) {
  if (!isEdit) {
    return `
      <label>Roll</label>
      <select id="m-role">
        ${roleSelectOptionsHtml(roleOptions)}
      </select>
    `;
  }
  return `
      <label>Roller</label>
      <div class="role-checks" id="m-roles">
        ${roleOptions.map((option) => `
          <label class="role-check">
            <input type="checkbox" name="m-role" value="${option.value}" ${selectedRoles.includes(option.value) ? "checked" : ""} ${isDemoTarget ? "disabled" : ""} />
            <span>${escapeHtml(option.label)}</span>
          </label>
        `).join("")}
      </div>
    `;
}

function areaName(areaId) {
  if (areaId == null) return "-";
  const area = areas.find((item) => Number(item.id) === Number(areaId));
  return area ? area.name : `Område #${areaId}`;
}

function businessOptions(selectedId) {
  if (!currentUser?.is_super_user) return "";
  return `
      <label>Verksamhet</label>
      <select id="m-business">
        <option value="">Välj verksamhet</option>
        ${businesses.map((business) => `<option value="${business.id}" ${Number(selectedId) === Number(business.id) ? "selected" : ""}>${escapeHtml(business.name)}</option>`).join("")}
      </select>
  `;
}

function businessIdFromArea(areaId) {
  const area = areas.find((item) => Number(item.id) === Number(areaId));
  return area?.business_id ?? null;
}

function inferredUserBusinessId(user = null, areaId = null) {
  return user?.business_id
    ?? businessIdFromArea(areaId ?? user?.area_id)
    ?? currentUser?.business_id
    ?? businesses[0]?.id
    ?? null;
}

function focusedAreaId() {
  return typeof preferredAreaIdFromFocus === "function" ? preferredAreaIdFromFocus(areas) : null;
}

function matchesAreaFocus(user) {
  const areaId = focusedAreaId();
  return areaId == null || Number(user?.area_id) === Number(areaId);
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
  users = await api.get("/api/users");
  renderUsers();
}

async function loadSettings() {
  if (!canViewPage(currentUser, "appSettings")) return;
  appSettings = await api.get("/api/settings");
  document.getElementById("lock-foreign-schedule-cells").checked = !!appSettings.lock_foreign_schedule_cells;
}

async function loadRoleViewAccess() {
  const response = await api.get("/api/settings/role-access");
  roleViewAccess = normalizeRoleViewAccess(response?.access || {});
  cacheRoleViewAccess(roleViewAccess);
}

async function loadAreas() {
  areas = await api.get("/api/areas");
}

async function loadBusinesses() {
  businesses = currentUser?.is_super_user ? await api.get("/api/businesses") : [];
}

function setupSettingsControls() {
  const checkbox = document.getElementById("lock-foreign-schedule-cells");
  const wrapper = checkbox.closest(".controls-checkbox");
  if (!canViewPage(currentUser, "appSettings")) {
    if (wrapper) wrapper.hidden = true;
    return;
  }
  checkbox.disabled = !canEditPage(currentUser, "appSettings");
  if (!canEditPage(currentUser, "appSettings")) return;
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

function roleAccessLevelOption(value) {
  return ROLE_ACCESS_LEVEL_OPTIONS.find((option) => option.value === value) || ROLE_ACCESS_LEVEL_OPTIONS[0];
}

function nextRoleAccessLevel(value) {
  const index = ROLE_ACCESS_LEVEL_ORDER.indexOf(value);
  return ROLE_ACCESS_LEVEL_ORDER[(index + 1) % ROLE_ACCESS_LEVEL_ORDER.length];
}

function applyRoleAccessToggleState(button, value) {
  const option = roleAccessLevelOption(value);
  button.dataset.level = option.value;
  button.textContent = option.label;
  button.className = `role-access-toggle is-${option.value}`;
  button.setAttribute("aria-label", `Behörighet: ${option.label}`);
  button.title = `Klicka för att byta från ${option.label}`;
}

function roleAccessToggle(role, viewId, lockedLevel = "") {
  const value = lockedLevel || roleViewAccess?.[role]?.[viewId] || "none";
  const option = roleAccessLevelOption(value);
  const disabled = lockedLevel ? " disabled aria-disabled=\"true\"" : "";
  const title = lockedLevel ? "Super User har alltid full åtkomst" : `Klicka för att byta från ${option.label}`;
  return `
    <button type="button" class="role-access-toggle is-${escapeHtml(option.value)}" data-role="${escapeHtml(role)}" data-view="${escapeHtml(viewId)}" data-level="${escapeHtml(option.value)}" aria-label="Behörighet: ${escapeHtml(option.label)}" title="${escapeHtml(title)}"${disabled}>${escapeHtml(option.label)}</button>
  `;
}

function bindRoleAccessToggles(container) {
  container.querySelectorAll(".role-access-toggle[data-role][data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      applyRoleAccessToggleState(button, nextRoleAccessLevel(button.dataset.level || "none"));
    });
  });
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
              ${roles.map((role) => `<td>${roleAccessToggle(role.value, view.id, role.lockedLevel || "")}</td>`).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
  bindRoleAccessToggles(container);
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
      <p class="note">Super User visas som låst Redigera eftersom rollen alltid har full åtkomst. Demo styr demo-kontots extra vybehörighet. Övriga roller kan få ingen åtkomst, bara visa eller redigera per vy.</p>
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
    tableHost.querySelectorAll(".role-access-toggle[data-role][data-view]").forEach((button) => {
      if (button.disabled) return;
      next[button.dataset.role][button.dataset.view] = button.dataset.level || "none";
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
  const canEditUsers = canEditPage(currentUser, "users");
  tbody.innerHTML = "";

  users.filter(matchesAreaFocus).forEach((user) => {
    const tr = document.createElement("tr");
    const selfLabel = user.id === currentUser.id ? " (du)" : "";
    const demoLabel = user.is_demo ? ' <span class="demo-user-pill">DEMO</span>' : "";
    const canDelete = user.id !== currentUser.id && !user.is_demo;
    tr.innerHTML = `
      <td>${escapeHtml(user.username)}${escapeHtml(selfLabel)}${demoLabel}</td>
      <td>${escapeHtml(user.display_name || "-")}</td>
      <td>${escapeHtml(roleLabel(user))}</td>
      <td>${escapeHtml(areaName(user.area_id))}</td>
      <td>${escapeHtml(passwordStatus(user))}</td>
      <td>${escapeHtml(formatDate(user.created_at))}</td>
      <td>
        ${canEditUsers ? `
        <button data-edit="${user.id}">Redigera</button>
        ${canDelete ? `<button data-delete="${user.id}" class="danger">Ta bort</button>` : ""}
        ` : ""}
      </td>`;
    tbody.appendChild(tr);
  });

  if (!canEditUsers) return;
  tbody.querySelectorAll("button[data-edit]").forEach((button) =>
    button.addEventListener("click", () => openModal(users.find((user) => user.id === Number(button.dataset.edit))))
  );
  tbody.querySelectorAll("button[data-delete]").forEach((button) =>
    button.addEventListener("click", async () => {
      const user = users.find((item) => item.id === Number(button.dataset.delete));
      if (!user) return;
      if (!confirm("Ta bort användaren permanent?")) return;
      try {
        await api.del(`/api/users/${user.id}`);
        await loadUsers();
      } catch (error) {
        showToast(error.message, "error");
      }
    })
  );
}

function openModal(user) {
  const isEdit = !!user;
  const isDemoTarget = !!user?.is_demo;
  const selectedRoles = rolesForUser(user);
  const roleOptions = editableRoleOptions();
  const selectedAreaId = user?.area_id ?? focusedAreaId();
  const selectedBusinessId = inferredUserBusinessId(user, selectedAreaId);
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Redigera användare" : "Ny användare"}</h2>
      ${isDemoTarget ? '<p class="note">Demo-användaren är låst: namn, roll och aktiv-status kan inte ändras. Lösenord, visningsnamn och område får roteras.</p>' : ""}
      <label>Användarnamn</label>
      <input id="m-username" autocomplete="username" value="${escapeHtml(user?.username || "")}" ${isDemoTarget ? "disabled" : ""} />
      <label>Visningsnamn</label>
      <input id="m-display-name" value="${escapeHtml(user?.display_name || "")}" />
      ${businessOptions(selectedBusinessId)}
      ${roleFieldHtml({ isEdit, isDemoTarget, selectedRoles, roleOptions })}
      <label>Område</label>
      <select id="m-area">
        <option value="">Ingen förinställning</option>
        ${areas.map((area) => `<option value="${area.id}" ${Number(selectedAreaId) === Number(area.id) ? "selected" : ""}>${escapeHtml(area.name)}</option>`).join("")}
      </select>
      <label>${isEdit ? "Nytt lösenord" : "Lösenord"}</label>
      <input id="m-password" type="password" autocomplete="new-password" />
      <p class="note">${isEdit ? "Lämna lösenord tomt om det inte ska ändras." : "Lämna tomt om användaren ska skapa sitt lösenord vid första inloggningen. Annars minst 8 tecken."}</p>
      <div class="actions">
        <button id="m-cancel">Avbryt</button>
        <button class="primary" id="m-save">Spara</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  document.getElementById("m-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("m-save").addEventListener("click", async () => {
    const password = document.getElementById("m-password").value;
    const roleSelect = document.getElementById("m-role");
    const checkedRoles = Array.from(document.querySelectorAll('input[name="m-role"]:checked')).map((input) => input.value);
    const roles = roleSelect
      ? (roleSelect.value ? [roleSelect.value] : [])
      : ((!currentUser?.is_super_user && selectedRoles.includes("super_user") && !checkedRoles.includes("super_user"))
        ? [...checkedRoles, "super_user"]
        : checkedRoles);
    const payload = {
      username: document.getElementById("m-username").value.trim(),
      display_name: document.getElementById("m-display-name").value.trim() || null,
      role: primaryRoleFromRoles(roles),
      roles,
      area_id: document.getElementById("m-area").value ? Number(document.getElementById("m-area").value) : null,
    };
    if (currentUser?.is_super_user) {
      payload.business_id = document.getElementById("m-business").value ? Number(document.getElementById("m-business").value) : null;
    }

    if (!payload.username) {
      showToast("Användarnamn krävs", "error");
      return;
    }
    if (roles.length === 0) {
      showToast(isEdit ? "Välj minst en roll" : "Välj en roll", "error");
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
  showToast("Importen innehöll inga användare", "warn");
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

async function openBulkUsersModal() {
  try {
    if (!areas.length) {
      await loadAreas();
    }
    if (currentUser?.is_super_user && !businesses.length) {
      await loadBusinesses();
    }
  } catch (error) {
    showToast(error.message || "Kunde inte läsa områden.", "error", 7000);
    return;
  }
  const businessColumn = currentUser?.is_super_user
    ? [{ key: "business", label: "Verksamhet", required: false, type: "select", options: businesses.map((business) => ({ value: business.code, label: business.name })) }]
    : [];
  openBulkImportGrid({
    title: "Flera nya användare",
    submitLabel: "Skapa användare",
    initialRows: 10,
    columns: [
      ...businessColumn,
      { key: "username", label: "Användarnamn", required: true },
      { key: "display_name", label: "Visningsnamn", required: false },
      { key: "role", label: "Roll", required: true, type: "select", options: ROLE_OPTIONS },
      { key: "area", label: "Område", required: false, type: "select", options: areas.map((area) => ({ value: area.name, label: area.name })) },
    ],
    onSubmit: async (rows) => {
      const result = await api.post("/api/users/import-rows", { rows });
      showImportResult(result);
      await loadUsers();
    },
  });
}

function setupImportControls() {
  const downloadButton = document.getElementById("download-user-template");
  const importButton = document.getElementById("import-users");
  const bulkButton = document.getElementById("bulk-users");
  const roleAccessButton = document.getElementById("role-view-access");
  const helpButton = document.getElementById("user-import-help");
  const fileInput = document.getElementById("user-import-file");

  if (canEditPage(currentUser, "userImport")) {
    bulkButton.hidden = false;
    downloadButton.hidden = false;
    importButton.hidden = false;
    helpButton.hidden = false;

    bulkButton.addEventListener("click", openBulkUsersModal);
    setupImportHelpButton("user-import-help", "Importera användare");
    downloadButton.addEventListener("click", async () => {
      try {
        await api.download("/api/users/import-template", "anvandare-importmall.xlsx");
      } catch (error) {
        showToast(error.message || "Kunde inte ladda ner importmallen.", "error", 7000);
      }
    });
    importButton.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files?.[0];
      fileInput.value = "";
      if (!file) return;
      await importUserFile(file);
    });
  }
  if (canEditPage(currentUser, "roleAccess")) {
    roleAccessButton.hidden = false;
    roleAccessButton.addEventListener("click", openRoleAccessModal);
  }
}

(async () => {
  currentUser = await initPage("users");
  if (!currentUser) return;

  await loadRoleViewAccess();
  const newUserButton = document.getElementById("new-user");
  newUserButton.hidden = !canEditPage(currentUser, "users");
  setupImportControls();
  setupSettingsControls();
  await loadSettings();
  await loadAreas();
  await loadBusinesses();
  await loadUsers();
  if (canEditPage(currentUser, "users")) newUserButton.addEventListener("click", () => openModal(null));
  window.addEventListener("flow:areaFocusChanged", renderUsers);
})();

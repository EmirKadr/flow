let currentUser = null;
let users = [];
let areas = [];
let appSettings = {
  lock_foreign_schedule_cells: false,
};

const ROLE_OPTIONS = [
  { value: "leader", label: "Arbetsledare" },
  { value: "admin", label: "Administratör" },
  { value: "warehouse_clerk", label: "Lagerkontorist" },
  { value: "article_placer", label: "Artikelplacerare" },
  { value: "viewer", label: "Visning" },
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
  const fileInput = document.getElementById("user-import-file");

  if (!currentUser?.is_super_user) return;

  downloadButton.hidden = false;
  importButton.hidden = false;

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

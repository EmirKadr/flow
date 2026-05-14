let currentUser = null;
let users = [];
let appSettings = {
  lock_foreign_schedule_cells: false,
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function roleLabel(user) {
  if (user?.is_super_admin) return "Super admin";
  const role = user?.role;
  return role === "admin" ? "Administratör" : "Arbetsledare";
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

function setupSettingsControls() {
  document.getElementById("save-settings").addEventListener("click", async () => {
    const payload = {
      lock_foreign_schedule_cells: document.getElementById("lock-foreign-schedule-cells").checked,
    };
    try {
      appSettings = await api.put("/api/settings", payload);
      document.getElementById("lock-foreign-schedule-cells").checked = !!appSettings.lock_foreign_schedule_cells;
      showToast("Inställningar sparade", "success");
    } catch (error) {
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
  const selectedRole = user?.role === "admin" || user?.role === "super_admin" ? "admin" : "leader";
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Redigera användare" : "Ny användare"}</h2>
      <label>Användarnamn</label>
      <input id="m-username" autocomplete="username" value="${escapeHtml(user?.username || "")}" />
      <label>Visningsnamn</label>
      <input id="m-display-name" value="${escapeHtml(user?.display_name || "")}" />
      <label>Roll</label>
      <select id="m-role">
        <option value="leader" ${selectedRole === "leader" ? "selected" : ""}>Arbetsledare</option>
        <option value="admin" ${selectedRole === "admin" ? "selected" : ""}>Administratör</option>
      </select>
      <label>${isEdit ? "Nytt lösenord" : "Lösenord"}</label>
      <input id="m-password" type="password" autocomplete="new-password" />
      <p class="note">${isEdit ? "Lämna lösenord tomt om det inte ska ändras." : "Lämna tomt om användaren ska skapa sitt lösenord vid första inloggningen. Annars minst 8 tecken."}</p>
      <label><input id="m-active" type="checkbox" ${user?.is_active !== false ? "checked" : ""} /> Aktiv</label>
      <div class="actions">
        <button id="m-cancel">Avbryt</button>
        <button class="primary" id="m-save">Spara</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  document.getElementById("m-cancel").addEventListener("click", () => backdrop.remove());
  document.getElementById("m-save").addEventListener("click", async () => {
    const password = document.getElementById("m-password").value;
    const payload = {
      username: document.getElementById("m-username").value.trim(),
      display_name: document.getElementById("m-display-name").value.trim() || null,
      role: document.getElementById("m-role").value,
      is_active: document.getElementById("m-active").checked,
    };

    if (!payload.username) {
      showToast("Användarnamn krävs", "error");
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

  if (!currentUser?.is_super_admin) return;

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
  await loadUsers();
  document.getElementById("new-user").addEventListener("click", () => openModal(null));
  document.getElementById("show-inactive").addEventListener("change", loadUsers);
})();

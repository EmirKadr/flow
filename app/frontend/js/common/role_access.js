// @ts-check
// Vybehörighetsmatrisen (roll × vy, Ingen/Visa/Redigera). Delat common-lager
// som Inställningar-vyn renderar i fliken Vybehörigheter. Flyttad hit från
// Användare-vyns modal 2026-07-07. Bygger på common-globalerna
// roleViewDefaultAccess/normalizeRoleViewAccess/cacheRoleViewAccess/
// roleViewAccessPayload och feature-registryt för labels.
(function () {
  let ROLE_ACCESS_LEVEL_OPTIONS = [
    { value: "none", label: "Ingen" },
    { value: "view", label: "Visa" },
    { value: "edit", label: "Redigera" },
  ];
  let ROLE_ACCESS_LEVEL_ORDER = ROLE_ACCESS_LEVEL_OPTIONS.map((option) => option.value);
  let VIEW_ACCESS_OPTIONS = [
    { id: "mySchedule", label: "Mitt schema" },
    { id: "myProductivity", label: "Min produktivitet" },
    { id: "schedule", label: "Bemanning" },
    { id: "overview", label: "Översikt" },
    { id: "productivity", label: "Produktivitet" },
    { id: "sankeyInbound", label: "Sankey - Inbound" },
    { id: "productivityFinance", label: "Intäkt/utgift" },
    { id: "dataFetch", label: "Hämta data" },
    { id: "mcp", label: "MCP" },
    { id: "labelEditor", label: "Etiketter" },
    { id: "allocationUploads", label: "Uppladdningar" },
    { id: "allocationProcess", label: "Bearbeta" },
    { id: "allocationProcessMatrix", label: "Bearbeta-matris" },
    { id: "allocationSettings", label: "Inställningar" },
    { id: "allocationSplit", label: "Dela" },
    { id: "staffingSettings", label: "Bemanningsinställningar" },
    { id: "productivityFinanceSettings", label: "Intäkt/utgift-inställningar" },
    { id: "persons", label: "Personer" },
    { id: "personSortOrder", label: "Personsortering" },
    { id: "personImport", label: "Personimport" },
    { id: "activities", label: "Aktiviteter" },
    { id: "activityImport", label: "Aktivitetsimport" },
    { id: "areas", label: "Områden" },
    { id: "analytics", label: "Historik" },
    { id: "meta", label: "Meta" },
    { id: "archiveStatus", label: "Arkivstatus" },
    { id: "bugReports", label: "Buggrapporter" },
    { id: "users", label: "Användare" },
    { id: "userImport", label: "Användarimport" },
    { id: "businesses", label: "Verksamheter" },
    { id: "appSettings", label: "Appinställningar" },
    { id: "sidebarLayout", label: "Menyordning" },
    { id: "roleAccess", label: "Vybehörigheter" },
  ];
  let matrixRoles = null;
  let roleViewAccess = {};

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
    );
  }

  function applyRoleAccessRegistry(payload) {
    if (!payload || typeof payload !== "object") return;
    const roles = Array.isArray(payload.roles)
      ? payload.roles
          .map((role) => ({
            value: String(role?.value || "").trim(),
            label: String(role?.label || role?.value || "").trim(),
            ...(role?.lockedLevel ? { lockedLevel: String(role.lockedLevel) } : {}),
          }))
          .filter((role) => role.value && role.label)
      : [];
    const views = Array.isArray(payload.views)
      ? payload.views
          .map((view) => ({
            id: String(view?.id || "").trim(),
            label: String(view?.label || view?.id || "").trim(),
          }))
          .filter((view) => view.id && view.label)
      : [];
    const levels = Array.isArray(payload.levels)
      ? payload.levels
          .map((level) => ({
            value: String(level?.value || "").trim(),
            label: String(level?.label || level?.value || "").trim(),
          }))
          .filter((level) => level.value && level.label)
      : [];
    if (roles.length) matrixRoles = roles;
    if (views.length) VIEW_ACCESS_OPTIONS = views;
    if (levels.length) {
      ROLE_ACCESS_LEVEL_OPTIONS = levels;
      ROLE_ACCESS_LEVEL_ORDER = levels.map((option) => option.value);
    }
  }

  async function loadRoleAccessRegistry() {
    try {
      const payload = await api.get("/api/settings/feature-registry", { cacheTtlMs: 5 * 60 * 1000 });
      applyRoleAccessRegistry(payload);
    } catch (error) {
      console.warn("Kunde inte läsa feature-registret.", error);
    }
  }

  async function loadRoleViewAccessState() {
    const response = await api.get("/api/settings/role-access");
    roleViewAccess = normalizeRoleViewAccess(response?.access || {});
    cacheRoleViewAccess(roleViewAccess);
  }

  function roleAccessRoles() {
    return matrixRoles || window.ROLE_VIEW_ROLES || [];
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

  function roleAccessToggle(role, viewId, lockedLevel = "", canEdit = true) {
    const value = lockedLevel || roleViewAccess?.[role]?.[viewId] || "none";
    const option = roleAccessLevelOption(value);
    const disabled = lockedLevel || !canEdit ? " disabled aria-disabled=\"true\"" : "";
    const title = lockedLevel
      ? "Super User har alltid full åtkomst"
      : (canEdit ? `Klicka för att byta från ${option.label}` : "Du har visningsåtkomst – ändringar är låsta");
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

  function renderRoleAccessTable(container, canEdit) {
    const roles = roleAccessRoles();
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
                ${roles.map((role) => `<td>${roleAccessToggle(role.value, view.id, role.lockedLevel || "", canEdit)}</td>`).join("")}
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
    if (canEdit) bindRoleAccessToggles(container);
  }

  async function renderRoleAccessPanel(container, options = {}) {
    if (!container) return;
    const canEdit = Boolean(options.canEdit);
    container.innerHTML = '<p class="note">Laddar vybehörigheter…</p>';
    try {
      await loadRoleAccessRegistry();
      await loadRoleViewAccessState();
    } catch (error) {
      container.innerHTML = `<p class="note">${escapeHtml(error.message || "Kunde inte läsa vybehörigheter.")}</p>`;
      return;
    }
    container.innerHTML = `
      <section class="role-access-panel">
        <p class="note">Super User visas som låst Redigera eftersom rollen alltid har full åtkomst. Demo styr demo-kontots extra vybehörighet. Övriga roller kan få ingen åtkomst, bara visa eller redigera per vy.${canEdit ? "" : " Du har visningsåtkomst – ändringar är låsta."}</p>
        <div id="role-access-table"></div>
        <div class="actions">
          <button type="button" id="role-access-defaults"${canEdit ? "" : " disabled"}>Standard</button>
          <button type="button" class="primary" id="role-access-save"${canEdit ? "" : " disabled"}>Spara</button>
        </div>
      </section>
    `;
    const tableHost = container.querySelector("#role-access-table");
    renderRoleAccessTable(tableHost, canEdit);
    container.querySelector("#role-access-defaults")?.addEventListener("click", () => {
      roleViewAccess = roleViewDefaultAccess();
      renderRoleAccessTable(tableHost, canEdit);
    });
    container.querySelector("#role-access-save")?.addEventListener("click", async () => {
      const saveButton = /** @type {HTMLButtonElement} */ (container.querySelector("#role-access-save"));
      saveButton.disabled = true;
      const next = roleViewDefaultAccess();
      tableHost.querySelectorAll(".role-access-toggle[data-role][data-view]").forEach((button) => {
        if (/** @type {HTMLButtonElement} */ (button).disabled) return;
        next[/** @type {HTMLElement} */ (button).dataset.role][/** @type {HTMLElement} */ (button).dataset.view] = /** @type {HTMLElement} */ (button).dataset.level || "none";
      });
      try {
        const response = await api.put("/api/settings/role-access", { access: roleViewAccessPayload(next) });
        roleViewAccess = normalizeRoleViewAccess(response?.access || next);
        cacheRoleViewAccess(roleViewAccess);
        showToast("Vybehörigheter sparades.", "success", 2500);
      } catch (error) {
        showToast(error.message || "Kunde inte spara vybehörigheter.", "error", 7000);
      } finally {
        saveButton.disabled = false;
      }
    });
  }

  window.flowRoleAccess = { renderRoleAccessPanel };
})();

// @ts-check
function formatHours(value) {
  const num = Number(value) || 0;
  const rounded = Math.round((num + Number.EPSILON) * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2).replace(/\.?0+$/, "");
}

function ensureManualCalcInput() {
  if (!state.calcInputs.manual) {
    state.calcInputs.manual = { rows: "", time: "", goal: "" };
  }
  return state.calcInputs.manual;
}

function sanitizeNumericInput(value) {
  const cleaned = String(value || "").replace(/[^\d.,]/g, "");
  const firstSep = cleaned.search(/[.,]/);
  if (firstSep === -1) return cleaned;
  return cleaned.slice(0, firstSep + 1) + cleaned.slice(firstSep + 1).replace(/[.,]/g, "");
}

function parseNumericInput(value) {
  if (value == null || value === "") return null;
  const normalized = String(value).replace(",", ".");
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function manualPlockHours() {
  return (state.summaryRows || []).reduce((sum, item) => {
    const code = String(item.activity_code || "").toUpperCase();
    const label = String(item.activity_label || "").toUpperCase();
    if (!code.includes("PLOCK") && !label.includes("PLOCK")) return sum;
    return sum + (Number(item.hours) || 0);
  }, 0);
}

function calcMetrics() {
  const values = ensureManualCalcInput();
  const rows = parseNumericInput(values.rows);
  const time = parseNumericInput(values.time);
  const goal = parseNumericInput(values.goal);
  const plockHours = manualPlockHours();

  let need = null;
  let hours = null;
  let diff = null;
  if (rows != null && time != null && goal != null && time > 0 && goal > 0) {
    need = (rows / time) / goal;
    hours = need * time;
    diff = plockHours - hours;
  }

  return { plockHours, need, hours, diff };
}

function calcValueText(value) {
  return value == null ? "–" : formatHours(value);
}

function updateCalcPanel(panel) {
  const { need, hours, diff } = calcMetrics();
  const outputs = {
    need: calcValueText(need),
    hours: calcValueText(hours),
    diff: calcValueText(diff),
  };
  Object.entries(outputs).forEach(([name, text]) => {
    const el = panel.querySelector(`[data-output="${name}"]`);
    if (el) el.textContent = text;
  });
  const diffEl = panel.querySelector('[data-output="diff"]');
  if (diffEl) {
    diffEl.classList.remove("positive", "negative");
    if (diff != null) {
      if (diff > 0) diffEl.classList.add("positive");
      if (diff < 0) diffEl.classList.add("negative");
    }
  }
}

function calcResultText(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return formatHours(Number(value));
}

function renderAutomaticCalculatorPanel(result) {
  const calc = (state.calculatorProfile.calculators || []).find((item) => item.id === result.id) || {};
  const isError = result.status === "error";
  const remaining = result.rows_remaining_after_schedule;
  return `
    <div class="calc-panel calc-panel-auto" data-calc-id="${escapeHtml(result.id || "")}">
      <div class="calc-panel-title calc-panel-title-row">
        <span>${escapeHtml(result.name || calc.name || "Automatisk")}</span>
        <span class="calc-panel-actions">
          <button type="button" class="icon-btn" data-calc-edit="${escapeHtml(result.id || "")}" title="Ändra" aria-label="Ändra">✎</button>
          <button type="button" class="icon-btn danger" data-calc-delete="${escapeHtml(result.id || "")}" title="Ta bort" aria-label="Ta bort">×</button>
        </span>
      </div>
      ${isError ? `
        <p class="note error">${escapeHtml(result.message || "Kalkylen kunde inte beräknas.")}</p>
      ` : `
        <table class="calc-table auto-calc-table">
          <thead>
            <tr><th>Rader kvar efter schemalagd tid</th></tr>
          </thead>
          <tbody>
            <tr><td class="calc-output ${remaining > 0 ? "negative" : "positive"}">${calcResultText(remaining)}</td></tr>
          </tbody>
        </table>
        <p class="note">Rader ${calcResultText(result.order_rows)} · schemalagt ${calcResultText(result.scheduled_hours)} h · plan ${calcResultText(result.expected_rows)} rader</p>
      `}
    </div>
  `;
}

function renderCalculator() {
  const container = document.getElementById("calcPanels");
  if (!container) return;

  const active = document.activeElement;
  let focusState = null;
  if (active && container.contains(active) && active.matches("input[data-field]")) {
    focusState = {
      field: /** @type {HTMLElement} */ (active).dataset.field || "",
      selectionStart: typeof /** @type {HTMLInputElement} */ (active).selectionStart === "number" ? /** @type {HTMLInputElement} */ (active).selectionStart : null,
      selectionEnd: typeof /** @type {HTMLInputElement} */ (active).selectionEnd === "number" ? /** @type {HTMLInputElement} */ (active).selectionEnd : null,
    };
  }

  const values = ensureManualCalcInput();
  const metrics = calcMetrics();
  const automatic = state.automaticCalculatorResults || [];
  container.innerHTML = `
    <div class="calc-panel calc-panel-manual" data-calc-kind="manual">
      <div class="calc-panel-title">Manuell</div>
      <table class="calc-table">
        <thead>
          <tr>
            <th>Dagens rader</th>
            <th>Tid kvar</th>
            <th>Mål</th>
            <th>Behov</th>
            <th>Timmar</th>
            <th>Diff</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><input type="text" inputmode="decimal" data-field="rows" value="${escapeHtml(values.rows)}" /></td>
            <td><input type="text" inputmode="decimal" data-field="time" value="${escapeHtml(values.time)}" /></td>
            <td><input type="text" inputmode="decimal" data-field="goal" value="${escapeHtml(values.goal)}" /></td>
            <td class="calc-output" data-output="need">${calcValueText(metrics.need)}</td>
            <td class="calc-output" data-output="hours">${calcValueText(metrics.hours)}</td>
            <td class="calc-output ${metrics.diff > 0 ? "positive" : metrics.diff < 0 ? "negative" : ""}" data-output="diff">${calcValueText(metrics.diff)}</td>
          </tr>
        </tbody>
      </table>
    </div>
    ${state.automaticCalculatorLoading ? `<div class="calc-panel"><div class="calc-panel-title">Automatiska</div><p class="note">Beräknar automatiska kalkyler...</p></div>` : ""}
    ${state.automaticCalculatorError ? `<div class="calc-panel"><div class="calc-panel-title">Automatiska</div><p class="note error">${escapeHtml(state.automaticCalculatorError)}</p></div>` : ""}
    ${automatic.map(renderAutomaticCalculatorPanel).join("")}
  `;

  container.querySelectorAll("input[data-field]").forEach((input) => {
    input.addEventListener("input", (e) => {
      const panel = /** @type {Element} */ (e.target).closest(".calc-panel");
      if (!panel) return;
      const field = /** @type {HTMLElement} */ (e.target).dataset.field;
      const sanitized = sanitizeNumericInput(/** @type {HTMLInputElement} */ (e.target).value);
      if (sanitized !== /** @type {HTMLInputElement} */ (e.target).value) /** @type {HTMLInputElement} */ (e.target).value = sanitized;
      state.calcInputs.manual[field] = sanitized;
      updateCalcPanel(panel);
    });
  });
  container.querySelectorAll("[data-calc-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const calc = (state.calculatorProfile.calculators || []).find((item) => item.id === /** @type {HTMLElement} */ (button).dataset.calcEdit);
      if (calc) openCalculatorModal(calc);
    });
  });
  container.querySelectorAll("[data-calc-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteAutomaticCalculator(/** @type {HTMLElement} */ (button).dataset.calcDelete);
    });
  });

  if (focusState?.field) {
    const nextInput = container.querySelector(
      `.calc-panel[data-calc-kind="manual"] input[data-field="${focusState.field}"]`
    );
    if (nextInput) {
      /** @type {HTMLElement} */ (nextInput).focus({ preventScroll: true });
      if (focusState.selectionStart != null && focusState.selectionEnd != null) {
        try {
          /** @type {HTMLInputElement} */ (nextInput).setSelectionRange(focusState.selectionStart, focusState.selectionEnd);
        } catch (err) {}
      }
    }
  }
}

function setupCalculator() {
  renderCalculator();
}

function syncCalculatorWithSelectedArea() {
  renderCalculator();
}

function normalizeCalculatorProfile(profile) {
  const items = Array.isArray(profile?.calculators) ? profile.calculators : [];
  return {
    version: 1,
    calculators: items
      .map((item) => ({
        id: String(item?.id || `calc-${Date.now()}-${Math.random().toString(16).slice(2)}`),
        name: String(item?.name || "").trim(),
        process: String(item?.process || "").trim(),
        company: String(item?.company || "").trim().toUpperCase(),
        zone: String(item?.zone || "").trim().toUpperCase(),
        pick_days: Number.parseInt(item?.pick_days ?? 0, 10) || 0,
      }))
      .filter((item) => item.name && item.process && item.company && item.zone),
  };
}

function updateCalculatorToolbar() {
  const importUser = document.getElementById("calcImportUser");
  if (!importUser) return;
  const search = String(state.calculatorImportSearch || "").trim().toLowerCase();
  const currentValue = /** @type {HTMLInputElement} */ (importUser).value;
  const users = (state.calculatorUsers || [])
    .filter((user) => user.has_calculators && !user.is_current)
    .filter((user) => {
      if (!search) return true;
      return `${user.name || ""} ${user.username || ""}`.toLowerCase().includes(search);
    });
  importUser.innerHTML = `
    <option value="">Hämta från användare</option>
    ${users.map((user) => `<option value="${escapeHtml(user.id)}">${escapeHtml(user.name || user.username)} (${escapeHtml(user.calculator_count || 0)})</option>`).join("")}
  `;
  if (users.some((user) => String(user.id) === String(currentValue))) /** @type {HTMLInputElement} */ (importUser).value = currentValue;
  /** @type {HTMLInputElement} */ (importUser).disabled = users.length === 0;
  const button = document.getElementById("calcImportBtn");
  if (button) /** @type {HTMLInputElement} */ (button).disabled = users.length === 0 || !/** @type {HTMLInputElement} */ (importUser).value;
}

function applyCalculatorProfilePayload(data) {
  state.calculatorProfile = normalizeCalculatorProfile(data?.profile);
  state.calculatorUsers = Array.isArray(data?.users) ? data.users : [];
  state.calculatorProcessOptions = Array.isArray(data?.process_options) ? data.process_options : [];
  updateCalculatorToolbar();
  renderCalculator();
}

async function loadCalculatorProfile() {
  try {
    const data = await api.get("/api/schedule/calculator-profile", { cacheTtlMs: 10 * 1000 });
    applyCalculatorProfilePayload(data);
  } catch (error) {
    console.warn("Kunde inte läsa bemanningskalkyler", error);
    state.calculatorProfile = { version: 1, calculators: [] };
    state.calculatorUsers = [];
    state.calculatorProcessOptions = [];
    updateCalculatorToolbar();
    renderCalculator();
  }
}

async function saveCalculatorProfile(profile) {
  const data = await api.put("/api/schedule/calculator-profile", { profile: normalizeCalculatorProfile(profile) });
  applyCalculatorProfilePayload(data);
  await loadAutomaticCalculatorResults({ force: true });
}

async function importCalculatorProfile(userId) {
  const data = await api.post("/api/schedule/calculator-profile/import", { user_id: Number(userId) });
  applyCalculatorProfilePayload(data);
  showToast("Bemanningskalkyler hämtades", "success");
  await loadAutomaticCalculatorResults({ force: true });
}

function automaticCalculatorProfileKey() {
  return JSON.stringify(normalizeCalculatorProfile(state.calculatorProfile));
}

function automaticCalculatorHalfHourKey() {
  return Math.floor(Date.now() / (30 * 60 * 1000));
}

function automaticCalculatorRequestKey() {
  return [
    scheduleScopeKey(),
    state.year,
    state.week,
    state.weekday,
    state.scheduleRevisionKey || "",
    automaticCalculatorHalfHourKey(),
    automaticCalculatorProfileKey(),
  ].join("|");
}

function scheduleAutomaticCalculatorRefresh(delay = 250, { force = false } = {}) {
  clearTimeout(automaticCalculatorState.timer);
  automaticCalculatorState.timer = setTimeout(() => {
    automaticCalculatorState.timer = null;
    void loadAutomaticCalculatorResults({ force });
  }, delay);
}

async function loadAutomaticCalculatorResults({ force = false } = {}) {
  if (!state.calculatorProfile?.calculators?.length) {
    state.automaticCalculatorResults = [];
    state.automaticCalculatorLoading = false;
    state.automaticCalculatorError = "";
    automaticCalculatorState.loadedKey = automaticCalculatorRequestKey();
    renderCalculator();
    return;
  }
  const requestKey = automaticCalculatorRequestKey();
  if (!force && automaticCalculatorState.loadedKey === requestKey && !state.automaticCalculatorError) {
    renderCalculator();
    return;
  }
  const requestSeq = ++automaticCalculatorState.requestSeq;
  state.automaticCalculatorLoading = true;
  state.automaticCalculatorError = "";
  renderCalculator();
  try {
    const result = await api.get(
      `/api/schedule/calculator/automatic?year=${state.year}&week=${state.week}&weekday=${state.weekday}`,
      { skipCache: true },
    );
    if (requestSeq !== automaticCalculatorState.requestSeq || requestKey !== automaticCalculatorRequestKey()) return;
    state.automaticCalculatorResults = Array.isArray(result.calculators) ? result.calculators : [];
    automaticCalculatorState.loadedKey = requestKey;
  } catch (error) {
    if (requestSeq !== automaticCalculatorState.requestSeq) return;
    state.automaticCalculatorResults = [];
    state.automaticCalculatorError = error.message || "Kunde inte beräkna automatiska kalkyler.";
  } finally {
    if (requestSeq === automaticCalculatorState.requestSeq) {
      state.automaticCalculatorLoading = false;
      renderCalculator();
    }
  }
}

function setupCalculatorToolbar() {
  document.getElementById("calcAddAutomaticBtn")?.addEventListener("click", () => openCalculatorModal());
  document.getElementById("calcImportSearch")?.addEventListener("input", (event) => {
    state.calculatorImportSearch = /** @type {HTMLInputElement} */ (event.target).value;
    updateCalculatorToolbar();
  });
  document.getElementById("calcImportUser")?.addEventListener("change", () => updateCalculatorToolbar());
  document.getElementById("calcImportBtn")?.addEventListener("click", async () => {
    const select = document.getElementById("calcImportUser");
    const userId = /** @type {HTMLInputElement} */ (select)?.value;
    if (!userId) return;
    try {
      await importCalculatorProfile(userId);
    } catch (error) {
      showToast(error.message || "Kunde inte hämta bemanningskalkyler", "error");
    }
  });
}

function openCalculatorModal(existing = null) {
  const isEdit = Boolean(existing);
  const calc = existing || { name: "", process: "", company: "", zone: "", pick_days: 0 };
  const options = state.calculatorProcessOptions || [];
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Ändra automatisk kalkyl" : "Ny automatisk kalkyl"}</h2>
      <label>Namn
        <input id="calcName" value="${escapeHtml(calc.name || "")}" />
      </label>
      <label>Process
        <select id="calcProcess" ${options.length ? "" : "disabled"}>
          <option value="">Välj process</option>
          ${options.map((option) => `
            <option value="${escapeHtml(option.value)}" ${option.value === calc.process ? "selected" : ""}>${escapeHtml(option.label || option.value)}</option>
          `).join("")}
        </select>
      </label>
      <label>Bolag
        <input id="calcCompany" value="${escapeHtml(calc.company || "")}" />
      </label>
      <label>Zon
        <input id="calcZone" value="${escapeHtml(calc.zone || "")}" />
      </label>
      <label>Plockdagar
        <input id="calcPickDays" type="number" step="1" value="${escapeHtml(calc.pick_days ?? 0)}" />
      </label>
      <div class="actions">
        <button type="button" id="calcCancel">Avbryt</button>
        <button type="button" id="calcSave">Spara</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);
  const close = () => backdrop.remove();
  backdrop.querySelector("#calcCancel").addEventListener("click", close);
  backdrop.querySelector("#calcSave").addEventListener("click", async () => {
    const next = {
      id: existing?.id || `calc-${Date.now()}`,
      name: /** @type {HTMLInputElement} */ (backdrop.querySelector("#calcName")).value.trim(),
      process: /** @type {HTMLInputElement} */ (backdrop.querySelector("#calcProcess")).value.trim(),
      company: /** @type {HTMLInputElement} */ (backdrop.querySelector("#calcCompany")).value.trim().toUpperCase(),
      zone: /** @type {HTMLInputElement} */ (backdrop.querySelector("#calcZone")).value.trim().toUpperCase(),
      pick_days: Number.parseInt(/** @type {HTMLInputElement} */ (backdrop.querySelector("#calcPickDays")).value, 10) || 0,
    };
    if (!next.name || !next.process || !next.company || !next.zone) {
      showToast("Namn, process, bolag och zon krävs", "warn");
      return;
    }
    const calculators = [...(state.calculatorProfile.calculators || [])];
    const index = calculators.findIndex((item) => item.id === next.id);
    if (index >= 0) calculators[index] = next;
    else calculators.push(next);
    try {
      await saveCalculatorProfile({ version: 1, calculators });
      showToast("Bemanningskalkyl sparad", "success");
      close();
    } catch (error) {
      showToast(error.message || "Kunde inte spara kalkylen", "error");
    }
  });
  setTimeout(() => /** @type {HTMLElement} */ (backdrop.querySelector("#calcName"))?.focus());
}

async function deleteAutomaticCalculator(calcId) {
  const calc = (state.calculatorProfile.calculators || []).find((item) => item.id === calcId);
  if (!calc) return;
  if (!confirm(`Ta bort kalkylen "${calc.name}"?`)) return;
  const calculators = (state.calculatorProfile.calculators || []).filter((item) => item.id !== calcId);
  try {
    await saveCalculatorProfile({ version: 1, calculators });
    showToast("Bemanningskalkyl borttagen", "success");
  } catch (error) {
    showToast(error.message || "Kunde inte ta bort kalkylen", "error");
  }
}

function appendActivityOptions(select, includeActivityIds = []) {
  const seen = new Set();
  const appendOption = (act) => {
    if (!act || seen.has(act.id)) return;
    seen.add(act.id);
    const opt = document.createElement("option");
    opt.value = String(act.id);
    opt.textContent = act.label;
    opt.style.background = act.color;
    select.appendChild(opt);
  };

  const sortedActivities = typeof compareActivitiesForAreaFocus === "function"
    ? [...state.activitiesActive].sort((a, b) =>
      compareActivitiesForAreaFocus(a, b, state.areas, state.currentUser?.area_id)
    )
    : state.activitiesActive;
  sortedActivities.forEach(appendOption);
  includeActivityIds
    .map((id) => Number(id))
    .filter((id) => Number.isInteger(id))
    .forEach((id) => appendOption(activityById(id)));
}

function buildActivitySelect(includeActivityIds = []) {
  const select = document.createElement("select");
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "-";
  select.appendChild(empty);
  includeActivityIds
    .map((id) => Number(id))
    .filter((id) => Number.isInteger(id))
    .forEach((id) => ensureSelectHasActivityOption(select, id));
  select.dataset.activityOptionsLoaded = "0";
  select.dataset.includeActivityIds = includeActivityIds.join(",");
  return select;
}

function ensureActivitySelectOptionsLoaded(select) {
  if (!select || select.dataset.activityOptionsLoaded === "1") return;
  const value = select.value;
  const includeIds = String(select.dataset.includeActivityIds || "")
    .split(",")
    .map((id) => Number(id))
    .filter((id) => Number.isInteger(id));
  if (value) includeIds.push(Number(value));

  select.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "-";
  select.appendChild(empty);
  appendActivityOptions(select, includeIds);
  select.dataset.activityOptionsLoaded = "1";
  select.value = value || "";
}

function ensureSelectHasActivityOption(select, activityId) {
  if (activityId == null) return;
  const value = String(activityId);
  const exists = Array.from(select.options).some((option) => option.value === value);
  if (exists) return;

  const activity = activityById(activityId);
  if (!activity) return;

  const option = document.createElement("option");
  option.value = value;
  option.textContent = activity.label;
  option.style.background = activity.color;
  select.appendChild(option);
}

function setSelectActivityValue(select, activityId) {
  if (activityId == null) {
    select.value = "";
    return;
  }
  ensureSelectHasActivityOption(select, activityId);
  select.value = String(activityId);
}


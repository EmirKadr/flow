// @ts-check
// Utdelad ur persons.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter persons.js via <script>-tagg.

// Personregister – inline-redigering direkt i tabellen.

let areas = [];
let activities = [];
let activitiesActive = [];
let businesses = [];
let persons = [];
let currentUser = null;
let sortKey = "sort_order";
let sortAsc = true;
const filters = { name: "", noman: "", rfid_code: "", collar_type: "", business: "", home_area: "", home_activity: "", sort_order: "" };
const PERSON_COLLAR_TYPES = [
  { value: "blue_collar", label: "Blue collar" },
  { value: "white_collar", label: "White collar" },
];
const personUndoStack = [];
const PERSON_UNDO_LIMIT = 50;
let personUndoBusy = false;
const PERSON_PRODUCTIVITY_CACHE_TTL_MS = 2 * 60 * 1000;
const personProductivityCache = new Map();

async function loadInitial() {
  const requests = [
    api.get("/api/areas"),
    api.get("/api/activities"),
    api.get("/api/activities?include_inactive=true"),
  ];
  if (currentUser?.is_super_user) requests.push(api.get("/api/businesses"));
  const [a, activeAct, act, biz] = await Promise.all(requests);
  areas = a;
  activitiesActive = activeAct;
  activities = act;
  businesses = biz || [];
}

function areaName(id) {
  const a = areas.find((x) => x.id === id);
  return a ? a.name : "";
}
function activityLabel(id) {
  const a = activities.find((x) => x.id === id);
  return a ? a.label : "";
}
function activityColor(id) {
  const a = activities.find((x) => x.id === id);
  return a ? a.color : "transparent";
}

function businessName(id) {
  if (id == null) return "Utan verksamhet";
  const business = businesses.find((item) => Number(item.id) === Number(id));
  if (business) return business.name;
  if (Number(currentUser?.business_id) === Number(id)) {
    return currentUser?.business_name || currentUser?.business_code || "";
  }
  return `Verksamhet #${id}`;
}

function collarTypeLabel(value) {
  const option = PERSON_COLLAR_TYPES.find((item) => item.value === value);
  return option ? option.label : "Blue collar";
}

function businessOptions(selectedId, disabled = false) {
  if (!currentUser?.is_super_user) return "";
  return `
      <label>Verksamhet</label>
      <select id="m-business" ${disabled ? "disabled" : ""}>
        <option value="">Välj verksamhet</option>
        ${businesses.map((business) => `<option value="${business.id}" ${Number(selectedId) === Number(business.id) ? "selected" : ""}>${escapeHtml(business.name)}</option>`).join("")}
      </select>
  `;
}

function businessIdFromArea(areaId) {
  const area = areas.find((item) => Number(item.id) === Number(areaId));
  return area?.business_id ?? null;
}

function businessIdFromActivity(activityId) {
  const activity = activities.find((item) => Number(item.id) === Number(activityId));
  return activity?.business_id ?? null;
}

function inferredPersonBusinessId(person = null) {
  return person?.business_id
    ?? businessIdFromArea(person?.home_area_id)
    ?? businessIdFromActivity(person?.home_activity_id)
    ?? currentUser?.business_id
    ?? businesses[0]?.id
    ?? null;
}

function focusedAreaId() {
  return typeof preferredAreaIdFromFocus === "function" ? preferredAreaIdFromFocus(areas) : null;
}

function matchesAreaFocus(person) {
  const areaId = focusedAreaId();
  return areaId == null || Number(person?.home_area_id) === Number(areaId);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
}

function localDateInputValue(date = new Date()) {
  const value = new Date(date);
  value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
  return value.toISOString().slice(0, 10);
}

function formatPersonProductivityPct(value) {
  const num = Number(value);
  return Number.isFinite(num) ? `${Math.round(num * 100)}%` : "-";
}

function formatPersonProductivityNumber(value, decimals = 1) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "-";
  return num.toLocaleString("sv-SE", { maximumFractionDigits: decimals, minimumFractionDigits: decimals });
}

function personProductivityScoreClass(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "";
  if (num < 0.8) return "low";
  if (num < 1) return "warn";
  return "good";
}

function personProductivityUrl(personId, state) {
  const params = new URLSearchParams();
  params.set("period", state.period);
  if (state.period === "custom") {
    params.set("start_date", state.startDate);
    params.set("end_date", state.endDate);
  } else {
    params.set("date", state.anchorDate);
  }
  return `/api/productivity/persons/${personId}?${params.toString()}`;
}

function cachedPersonProductivity(url) {
  const entry = personProductivityCache.get(url);
  if (!entry || entry.expiresAt <= Date.now()) {
    personProductivityCache.delete(url);
    return null;
  }
  return entry.data;
}

function storePersonProductivity(url, data) {
  personProductivityCache.set(url, {
    data,
    expiresAt: Date.now() + PERSON_PRODUCTIVITY_CACHE_TTL_MS,
  });
}

function renderPersonProductivityRows(data) {
  const rows = data.activities || [];
  if (!rows.length) {
    return `
      <tr>
        <td colspan="7" class="person-productivity-empty">Ingen aktivitetsdata hittades för perioden.</td>
      </tr>`;
  }
  return rows.map((row) => {
    const scoreClass = personProductivityScoreClass(row.productivity_pct);
    return `
      <tr>
        <td>${escapeHtml(row.activity)}</td>
        <td><strong class="person-productivity-score ${scoreClass}">${formatPersonProductivityPct(row.productivity_pct)}</strong></td>
        <td>${formatPersonProductivityNumber(row.points_per_hour, 1)}</td>
        <td>${formatPersonProductivityNumber(row.kpi_hours, 1)}</td>
        <td>${formatPersonProductivityNumber(row.kpi_points, 1)}</td>
        <td>${Number(row.periods || 0)}</td>
        <td>${Number(row.diff_count || 0)}</td>
      </tr>`;
  }).join("");
}

function updatePersonProductivityModal(backdrop, data) {
  const summary = data.summary || {};
  const period = data.period || {};
  const missingCount = (data.missing_dates || []).length;
  const status = backdrop.querySelector("#person-productivity-status");
  const summaryEl = backdrop.querySelector("#person-productivity-summary");
  const body = backdrop.querySelector("#person-productivity-body");
  status.textContent = missingCount
    ? `${missingCount} dag(ar) saknar global snapshot och fylls av bakgrundshämtningen.`
    : `Period ${period.start_date || ""} - ${period.end_date || ""}`;
  status.className = missingCount ? "note warn" : "note";
  summaryEl.innerHTML = `
    <div class="person-productivity-stat">
      <span>Snitt</span>
      <strong class="${personProductivityScoreClass(summary.productivity_pct)}">${formatPersonProductivityPct(summary.productivity_pct)}</strong>
    </div>
    <div class="person-productivity-stat">
      <span>Poäng/tim</span>
      <strong>${formatPersonProductivityNumber(summary.points_per_hour, 1)}</strong>
    </div>
    <div class="person-productivity-stat">
      <span>KPI-timmar</span>
      <strong>${formatPersonProductivityNumber(summary.kpi_hours, 1)}</strong>
    </div>
    <div class="person-productivity-stat">
      <span>Dagar</span>
      <strong>${Number(summary.days_with_activity || 0)} / ${Number(period.requested_days || 0)}</strong>
    </div>`;
  body.innerHTML = renderPersonProductivityRows(data);
}

async function loadPersonProductivityModal(backdrop, person, state) {
  const status = backdrop.querySelector("#person-productivity-status");
  const body = backdrop.querySelector("#person-productivity-body");
  const url = personProductivityUrl(person.id, state);
  const cached = cachedPersonProductivity(url);
  if (cached) {
    updatePersonProductivityModal(backdrop, cached);
    return;
  }
  status.className = "note";
  status.textContent = "Hämtar produktivitet...";
  body.innerHTML = `
    <tr>
      <td colspan="7" class="person-productivity-empty">Hämtar...</td>
    </tr>`;
  try {
    const data = await api.get(url, {
      cacheTtlMs: PERSON_PRODUCTIVITY_CACHE_TTL_MS,
      logGetUserEvent: true,
      logLabel: "Personproduktivitet",
      trackGetInteraction: true,
    });
    storePersonProductivity(url, data);
    updatePersonProductivityModal(backdrop, data);
  } catch (error) {
    status.className = "note error";
    status.textContent = error.message || "Kunde inte hämta personens produktivitet.";
    body.innerHTML = `
      <tr>
        <td colspan="7" class="person-productivity-empty">Kunde inte hämta data.</td>
      </tr>`;
    showToast(error.message || "Kunde inte hämta personens produktivitet", "error", 7000);
  }
}

function openPersonProductivityModal(person) {
  if (!person) return;
  const today = localDateInputValue();
  const state = {
    period: "week",
    anchorDate: today,
    startDate: today,
    endDate: today,
  };
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal wide person-productivity-modal">
      <h2>Produktivitet för ${escapeHtml(person.name)}</h2>
      <div class="person-productivity-controls">
        <div class="person-productivity-periods" role="tablist">
          <button type="button" class="active" data-period="week">Vecka</button>
          <button type="button" data-period="month">Månad</button>
          <button type="button" data-period="year">År</button>
          <button type="button" data-period="custom">Datum</button>
        </div>
        <label class="person-productivity-date person-productivity-anchor">
          Datum
          <input id="person-productivity-anchor-date" type="date" value="${today}" />
        </label>
        <div class="person-productivity-custom" hidden>
          <label class="person-productivity-date">
            Från
            <input id="person-productivity-start-date" type="date" value="${today}" />
          </label>
          <label class="person-productivity-date">
            Till
            <input id="person-productivity-end-date" type="date" value="${today}" />
          </label>
        </div>
      </div>
      <p class="note" id="person-productivity-status">Hämtar produktivitet...</p>
      <div class="person-productivity-summary" id="person-productivity-summary"></div>
      <div class="modal-table-scroll">
        <table class="person-productivity-table">
          <thead>
            <tr>
              <th>Aktivitet</th>
              <th>Snitt</th>
              <th>Poäng/tim</th>
              <th>KPI-timmar</th>
              <th>Poäng</th>
              <th>Perioder</th>
              <th>Diffar</th>
            </tr>
          </thead>
          <tbody id="person-productivity-body"></tbody>
        </table>
      </div>
      <div class="actions">
        <button id="person-productivity-close">Stäng</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  const setCustomVisibility = () => {
    /** @type {HTMLElement} */ (backdrop.querySelector(".person-productivity-anchor")).hidden = state.period === "custom";
    /** @type {HTMLElement} */ (backdrop.querySelector(".person-productivity-custom")).hidden = state.period !== "custom";
  };
  backdrop.querySelector("#person-productivity-close").addEventListener("click", () => backdrop.remove());
  backdrop.querySelectorAll("[data-period]").forEach((button) => {
    button.addEventListener("click", () => {
      state.period = /** @type {HTMLElement} */ (button).dataset.period || "week";
      backdrop.querySelectorAll("[data-period]").forEach((item) => item.classList.toggle("active", item === button));
      setCustomVisibility();
      void loadPersonProductivityModal(backdrop, person, state);
    });
  });
  backdrop.querySelector("#person-productivity-anchor-date").addEventListener("change", (event) => {
    state.anchorDate = /** @type {HTMLInputElement} */ (event.target).value || today;
    void loadPersonProductivityModal(backdrop, person, state);
  });
  backdrop.querySelector("#person-productivity-start-date").addEventListener("change", (event) => {
    state.startDate = /** @type {HTMLInputElement} */ (event.target).value || today;
    void loadPersonProductivityModal(backdrop, person, state);
  });
  backdrop.querySelector("#person-productivity-end-date").addEventListener("change", (event) => {
    state.endDate = /** @type {HTMLInputElement} */ (event.target).value || state.startDate || today;
    void loadPersonProductivityModal(backdrop, person, state);
  });
  setCustomVisibility();
  void loadPersonProductivityModal(backdrop, person, state);
}

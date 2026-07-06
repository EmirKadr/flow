// @ts-check
// Utdelad ur sankey_inbound.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter sankey_inbound.js via <script>-tagg.

const SANKEY_INBOUND_CACHE_TTL_MS = 5 * 60 * 1000;
const SANKEY_INBOUND_CLIENT_SCHEMA = "client-filter-v4";
const SANKEY_INBOUND_COLORS = {
  source: "#2563eb",
  RECEIVING: "#0f766e",
  DECANTING: "#7c3aed",
  HBW: "#0369a1",
  MANUAL_BUFFER: "#b45309",
  PUTAWAY_PICK: "#be123c",
  BUFFER_UPDATE: "#4d7c0f",
  terminal: "#475569",
  consumed: "#16a34a",
  open: "#64748b",
  outbound_source: "#0891b2",
  outbound_branch: "#0f766e",
  outbound_metric: "#9333ea",
};

let sankeyInboundUser = null;
let sankeyInboundPeriod = "day";
let sankeyInboundOnlyConsumed = false;
let sankeyInboundBasePayload = null;
let sankeyInboundPayload = null;
let sankeyInboundSelected = null;
let sankeyInboundClientFilterRefreshInFlight = false;
let sankeyInboundTriedClientFilterRefresh = false;
let sankeyTraceHydrateSeq = 0;

function sankeyNormalizeCompany(value) {
  const text = String(value || "").trim().toUpperCase();
  return text && text !== "ALL" ? text : "ALL";
}

function sankeyEscapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function sankeyDisplayText(value) {
  let text = String(value ?? "");
  const replacements = [
    ["Ã¥", "å"], ["Ã¤", "ä"], ["Ã¶", "ö"],
    ["Ã…", "Å"], ["Ã„", "Ä"], ["Ã–", "Ö"],
    ["â€“", "–"], ["â€”", "—"], ["â€¦", "…"],
    ["â€¹", "‹"], ["â€º", "›"], ["Â·", "·"], ["Â ", " "],
  ];
  for (const [broken, fixed] of replacements) {
    text = text.split(broken).join(fixed);
  }
  return text;
}

function sankeyLocalIsoDate(date = new Date()) {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

function sankeyParseIsoDate(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
}

function sankeyFormatDate(date) {
  return date.toISOString().slice(0, 10);
}

function sankeyPeriodStartDate(period, value) {
  const date = sankeyParseIsoDate(value) || sankeyParseIsoDate(sankeyLocalIsoDate());
  if (!date) return value || "";
  const normalized = String(period || "day").toLowerCase();
  if (normalized === "year") {
    date.setUTCMonth(0, 1);
  } else if (normalized === "month") {
    date.setUTCDate(1);
  } else if (normalized === "week") {
    const weekday = date.getUTCDay() || 7;
    date.setUTCDate(date.getUTCDate() - (weekday - 1));
  }
  return sankeyFormatDate(date);
}

function sankeyClientViewKey(period, dateValue, company, onlyConsumed) {
  return [
    String(period || "day").toLowerCase(),
    sankeyPeriodStartDate(period, dateValue),
    sankeyNormalizeCompany(company),
    onlyConsumed ? "1" : "0",
  ].join("|");
}

function sankeyShiftDate(value, direction, period) {
  const date = sankeyParseIsoDate(value) || sankeyParseIsoDate(sankeyLocalIsoDate());
  if (!date) return value;
  if (period === "week") date.setUTCDate(date.getUTCDate() + direction * 7);
  else if (period === "month") date.setUTCMonth(date.getUTCMonth() + direction);
  else if (period === "year") date.setUTCFullYear(date.getUTCFullYear() + direction);
  else date.setUTCDate(date.getUTCDate() + direction);
  return sankeyFormatDate(date);
}

function sankeyFormatMoney(value, currency = "SEK") {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("sv-SE", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

function sankeyFormatNumber(value, digits = 0) {
  return new Intl.NumberFormat("sv-SE", {
    maximumFractionDigits: digits,
  }).format(Number(value || 0));
}

function sankeyDateInput() {
  return /** @type {HTMLInputElement|null} */ (document.getElementById("sankeyInboundDate"));
}

function sankeyDateValue() {
  return sankeyDateInput()?.value || sankeyLocalIsoDate();
}

function sankeyCompanySelect() {
  return /** @type {HTMLSelectElement|null} */ (document.getElementById("sankeyInboundCompany"));
}

function sankeyCompanyValue() {
  return sankeyNormalizeCompany(sankeyCompanySelect()?.value || "ALL");
}

function updateSankeyDateDisplay() {
  const input = sankeyDateInput();
  const display = document.getElementById("sankeyInboundDateDisplayText");
  if (display) display.textContent = input?.value || sankeyLocalIsoDate();
}

function updateSankeyControls() {
  /** @type {NodeListOf<HTMLElement>} */ (
    document.querySelectorAll("[data-sankey-period]")
  ).forEach((button) => {
    button.classList.toggle("active", button.dataset.sankeyPeriod === sankeyInboundPeriod);
  });
  const consumedButton = document.getElementById("sankeyInboundOnlyConsumed");
  if (consumedButton) {
    consumedButton.classList.toggle("active", sankeyInboundOnlyConsumed);
    consumedButton.setAttribute("aria-pressed", sankeyInboundOnlyConsumed ? "true" : "false");
  }
}

function setSankeyStatus(text, busy = false) {
  const status = document.getElementById("sankeyInboundStatus");
  if (status) status.textContent = text || "";
  const chart = document.getElementById("sankeyInboundChart");
  if (chart) {
    if (busy) chart.setAttribute("aria-busy", "true");
    else chart.removeAttribute("aria-busy");
  }
}

function updateSankeyCompanyOptions(payload) {
  const select = sankeyCompanySelect();
  if (!select) return;
  const current = select.value || "ALL";
  const codes = [
    ...(payload?.business?.company_codes || []),
    ...(payload?.companies || []).map((item) => item.company),
  ]
    .map((value) => String(value || "").trim().toUpperCase())
    .filter(Boolean);
  const unique = [...new Set(codes)];
  select.innerHTML = `
    <option value="ALL">Alla bolag</option>
    ${unique.map((code) => `<option value="${sankeyEscapeHtml(code)}">${sankeyEscapeHtml(code)}</option>`).join("")}
  `;
  select.value = unique.includes(current) ? current : "ALL";
}

function sankeyPayloadMatchesClientState(basePayload, period, dateValue, company, onlyConsumed) {
  if (!basePayload) return false;
  const filters = basePayload.filters || {};
  const payloadPeriod = basePayload.period || {};
  return (
    String(payloadPeriod.type || "").toLowerCase() === String(period || "").toLowerCase()
    && String(payloadPeriod.start_date || "") === sankeyPeriodStartDate(period, dateValue)
    && sankeyNormalizeCompany(filters.company) === sankeyNormalizeCompany(company)
    && Boolean(filters.only_consumed) === Boolean(onlyConsumed)
  );
}

function sankeyHydrateClientPayload(basePayload, viewPayload, period, dateValue, company, onlyConsumed) {
  const variant = viewPayload || {};
  return {
    ...basePayload,
    ...variant,
    period: variant.period || basePayload.period,
    filters: {
      ...(basePayload.filters || {}),
      ...(variant.filters || {}),
      company: sankeyNormalizeCompany(company),
      only_consumed: Boolean(onlyConsumed),
    },
    client_filters: basePayload.client_filters || {},
    warnings: basePayload.warnings || [],
    source_status: basePayload.source_status || [],
    cache: {
      ...(basePayload.cache || {}),
      client_filter: !sankeyPayloadMatchesClientState(basePayload, period, dateValue, company, onlyConsumed),
    },
    timing: basePayload.timing,
  };
}

function sankeyPayloadForClientState(basePayload, options = {}) {
  if (!basePayload) return null;
  const period = options.period || sankeyInboundPeriod;
  const dateValue = options.date || sankeyDateValue();
  const company = sankeyNormalizeCompany(options.company || sankeyCompanyValue());
  const onlyConsumed = Boolean(options.onlyConsumed ?? sankeyInboundOnlyConsumed);
  if (sankeyPayloadMatchesClientState(basePayload, period, dateValue, company, onlyConsumed)) {
    return sankeyHydrateClientPayload(basePayload, basePayload, period, dateValue, company, onlyConsumed);
  }

  const viewKey = sankeyClientViewKey(period, dateValue, company, onlyConsumed);
  const view = basePayload.client_filters?.views?.[viewKey];
  if (view) {
    return sankeyHydrateClientPayload(basePayload, view, period, dateValue, company, onlyConsumed);
  }

  const samePeriodAndCompany = sankeyPayloadMatchesClientState(
    {
      ...basePayload,
      filters: {
        ...(basePayload.filters || {}),
        only_consumed: Boolean(basePayload.filters?.only_consumed),
      },
    },
    period,
    dateValue,
    company,
    Boolean(basePayload.filters?.only_consumed),
  );
  if (!samePeriodAndCompany) return null;

  const baseOnlyConsumed = Boolean(basePayload.filters?.only_consumed);
  if (baseOnlyConsumed === Boolean(onlyConsumed)) {
    return sankeyHydrateClientPayload(basePayload, basePayload, period, dateValue, company, onlyConsumed);
  }
  const variants = basePayload.client_filters || {};
  const variant = onlyConsumed ? variants.only_consumed : variants.all;
  if (!variant) return null;
  return sankeyHydrateClientPayload(basePayload, variant, period, dateValue, company, onlyConsumed);
}

function sankeyPayloadForConsumedState(basePayload, onlyConsumed) {
  return sankeyPayloadForClientState(basePayload, { onlyConsumed });
}

function renderSankeyCurrentView(options = {}) {
  const payload = sankeyPayloadForClientState(sankeyInboundBasePayload);
  if (!payload) {
    if (options.fetchIfMissing !== false) {
      void loadSankeyInbound();
    }
    return false;
  }
  renderSankeyPayload(payload, { updateCompanyOptions: false });
  return true;
}

function applySankeyFilterChange(controlId) {
  const renderedLocally = renderSankeyCurrentView();
  if (renderedLocally && typeof flowTrack === "function") {
    flowTrack("filter", {
      control_id: controlId,
      view: "sankeyInbound",
      period: sankeyInboundPeriod,
      company: sankeyCompanyValue(),
      only_consumed: sankeyInboundOnlyConsumed,
      local_client_filter: Boolean(sankeyInboundPayload?.cache?.client_filter),
    });
  }
}

function clearSankeyInboundGetCache() {
  const predicate = (key) => String(key || "").includes("/api/sankey/inbound");
  if (typeof api !== "undefined" && typeof api.clearGetCache === "function") {
    api.clearGetCache(predicate);
  } else if (typeof clearApiGetCache === "function") {
    clearApiGetCache(predicate);
  }
}

async function refreshSankeyPayloadForClientFilters() {
  if (!sankeyInboundBasePayload || sankeyInboundClientFilterRefreshInFlight) return;
  if (sankeyInboundTriedClientFilterRefresh) {
    if (typeof showToast === "function") showToast("Förverkad-vyn saknas fortfarande i hämtad Sankey-data. Ladda om sidan en gång.", "warn", 5000);
    return;
  }
  sankeyInboundTriedClientFilterRefresh = true;
  sankeyInboundClientFilterRefreshInFlight = true;
  clearSankeyInboundGetCache();
  setSankeyStatus("Uppdaterar Sankey-filter...", true);
  try {
    const payload = await fetchSankeyInboundPayload({ cacheBust: true });
    sankeyInboundClientFilterRefreshInFlight = false;
    handleSankeyLoaded(payload);
  } catch (error) {
    handleSankeyLoadError(error);
  } finally {
    sankeyInboundClientFilterRefreshInFlight = false;
    document.getElementById("sankeyInboundChart")?.removeAttribute("aria-busy");
  }
}

async function fetchSankeyInboundPayload(options = {}) {
  const params = new URLSearchParams();
  params.set("period", sankeyInboundPeriod);
  params.set("date", sankeyDateValue());
  params.set("client_schema", SANKEY_INBOUND_CLIENT_SCHEMA);
  if (options.cacheBust) params.set("_", String(Date.now()));
  const company = sankeyCompanyValue();
  if (company && company !== "ALL") params.set("company", company);
  if (sankeyInboundOnlyConsumed) params.set("only_consumed", "true");
  const query = `?${params.toString()}`;
  return api.get("/api/sankey/inbound" + query, { cacheTtlMs: options.cacheBust ? 0 : SANKEY_INBOUND_CACHE_TTL_MS });
}

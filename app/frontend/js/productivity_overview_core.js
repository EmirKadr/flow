// Utdelad ur productivity_overview.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter productivity_overview.js via <script>-tagg.

let productivityOverviewReport = null;
let productivityOverviewUser = null;
let productivityOverviewRoot = null;
let productivityOverviewNodeIndex = new Map();
let productivityOverviewFocusId = "root";
let productivityOverviewPeriod = "day";
let productivityOverviewLoadToken = 0;
let productivityOverviewContextMenu = null;
let productivityOverviewEventSource = null;
const PRODUCTIVITY_OVERVIEW_CACHE_TTL_MS = 2 * 60 * 1000;
const PRODUCTIVITY_OVERVIEW_EXPORT_LEVELS_KEY = "flow-productivity-overview-export-levels";
const PRODUCTIVITY_OVERVIEW_EXPORT_LEVELS = [
  { type: "business", label: "Verksamhet" },
  { type: "area", label: "Område" },
  { type: "activity", label: "Aktivitet" },
  { type: "person", label: "Person" },
  { type: "hour", label: "Timme" },
  { type: "process", label: "Processpoäng" },
];
const productivityOverviewReportCache = new Map();

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function formatProductivityOverviewNumber(value, decimals = 1) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString("sv-SE", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatProductivityOverviewPoints(value) {
  return `${formatProductivityOverviewNumber(value, 1)} p`;
}

function formatProductivityOverviewHours(minutes) {
  const hours = Number(minutes || 0) / 60;
  const decimals = Math.abs(hours - Math.round(hours)) < 0.01 ? 0 : 1;
  return `${formatProductivityOverviewNumber(hours, decimals)} h`;
}

function formatProductivityOverviewMoney(value, currency = "SEK") {
  const amount = Number(value || 0);
  const decimals = Math.abs(amount - Math.round(amount)) < 0.01 ? 0 : 2;
  return amount.toLocaleString("sv-SE", {
    style: "currency",
    currency: currency || "SEK",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function productivityOverviewPointsPerHour(node) {
  if (Number(node?.kpiMinutes || 0) <= 0) return null;
  const hours = Number(node?.workMinutes || 0) / 60;
  if (hours <= 0) return null;
  return Number(node?.points || 0) / hours;
}

function productivityOverviewScoreClass(value) {
  if (value == null || Number.isNaN(Number(value))) return "";
  if (Number(value) >= 80) return "good";
  if (Number(value) >= 70) return "warn";
  return "low";
}

function formatProductivityOverviewRate(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return formatProductivityOverviewNumber(value, 1);
}

function formatProductivityOverviewTimestamp(value) {
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

function localProductivityOverviewIsoDate(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function waitForProductivityOverviewPaint() {
  return new Promise((resolve) => {
    if (typeof requestAnimationFrame !== "function") {
      window.setTimeout(resolve, 0);
      return;
    }
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  });
}

function addProductivityOverviewDays(isoDate, days) {
  if (!isoDate) return "";
  const [year, month, day] = isoDate.split("-").map(Number);
  if (![year, month, day].every(Number.isFinite)) return "";
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function addProductivityOverviewMonths(isoDate, months) {
  if (!isoDate) return "";
  const [year, month, day] = isoDate.split("-").map(Number);
  if (![year, month, day].every(Number.isFinite)) return "";
  const date = new Date(Date.UTC(year, month - 1 + months, 1));
  const lastDay = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate();
  date.setUTCDate(Math.min(day, lastDay));
  return date.toISOString().slice(0, 10);
}

function addProductivityOverviewYears(isoDate, years) {
  if (!isoDate) return "";
  const [year, month, day] = isoDate.split("-").map(Number);
  if (![year, month, day].every(Number.isFinite)) return "";
  const date = new Date(Date.UTC(year + years, month - 1, 1));
  const lastDay = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate();
  date.setUTCDate(Math.min(day, lastDay));
  return date.toISOString().slice(0, 10);
}

function productivityOverviewIsoWeekParts(isoDate) {
  if (!isoDate) return null;
  const [year, month, day] = isoDate.split("-").map(Number);
  if (![year, month, day].every(Number.isFinite)) return null;
  const date = new Date(Date.UTC(year, month - 1, day));
  const weekday = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - weekday);
  const weekYear = date.getUTCFullYear();
  const yearStart = new Date(Date.UTC(weekYear, 0, 1));
  const week = Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
  return { year: weekYear, week };
}

function productivityOverviewPeriodDisplayLabel(isoDate, period = productivityOverviewPeriodValue()) {
  if (!isoDate) {
    if (period === "week") return "Vecka";
    if (period === "month") return "Månad";
    if (period === "year") return "År";
    return "YYYY-MM-DD";
  }
  const [year, month] = isoDate.split("-").map(Number);
  if (period === "week") {
    const parts = productivityOverviewIsoWeekParts(isoDate);
    return parts ? `Vecka ${parts.week}` : "Vecka";
  }
  if (period === "month" && Number.isFinite(year) && Number.isFinite(month)) {
    const date = new Date(Date.UTC(year, month - 1, 1));
    const monthLabel = date.toLocaleDateString("sv-SE", { month: "long" });
    return monthLabel ? monthLabel.charAt(0).toLocaleUpperCase("sv-SE") + monthLabel.slice(1) : "Månad";
  }
  if (period === "year" && Number.isFinite(year)) return String(year);
  return isoDate;
}

function productivityOverviewDateValue() {
  return document.getElementById("productivityOverviewDate")?.value || productivityOverviewReport?.date || "";
}

function productivityOverviewPeriodValue() {
  return productivityOverviewPeriod || document.querySelector(".productivity-overview-period-toggle button.active")?.dataset?.period || "day";
}

function updateProductivityOverviewDateDisplay() {
  const input = document.getElementById("productivityOverviewDate");
  const display = document.getElementById("productivityOverviewDateDisplayText");
  const value = input?.value || productivityOverviewReport?.date || "";
  const label = productivityOverviewPeriodDisplayLabel(value);
  if (display) {
    display.textContent = label;
    display.closest(".date-display-wrap")?.setAttribute("title", value ? `Välj ankardatum för ${label}` : "Välj datum");
  }
  if (input) input.setAttribute("aria-label", value ? `Välj ankardatum för ${label}` : "Välj datum");
}

function updateProductivityOverviewPeriodControls() {
  document.querySelectorAll(".productivity-overview-period-toggle button[data-period]").forEach((button) => {
    const active = button.dataset.period === productivityOverviewPeriodValue();
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function availableProductivityOverviewDates() {
  return Array.from(new Set(productivityOverviewReport?.available_dates || []))
    .filter(Boolean)
    .sort();
}

function adjacentProductivityOverviewDate(direction) {
  const current = productivityOverviewDateValue();
  const period = productivityOverviewPeriodValue();
  if (period === "week") return addProductivityOverviewDays(current, direction * 7);
  if (period === "month") return addProductivityOverviewMonths(current, direction);
  if (period === "year") return addProductivityOverviewYears(current, direction);
  if (period === "day") return addProductivityOverviewDays(current, direction);
  const dates = availableProductivityOverviewDates();
  if (dates.length > 1) {
    const index = dates.indexOf(current);
    if (index >= 0) return dates[index + direction] || "";
    return direction < 0 ? dates[dates.length - 1] : dates[0];
  }
  return addProductivityOverviewDays(current, direction);
}

function updateProductivityOverviewDateNav() {
  const prev = document.getElementById("productivityOverviewPrevDate");
  const next = document.getElementById("productivityOverviewNextDate");
  updateProductivityOverviewDateDisplay();
  if (!prev || !next) return;
  const current = productivityOverviewDateValue();
  prev.disabled = !current;
  next.disabled = !current;
}

function completedProductivityOverviewCutoffMinute(reportDate) {
  if (reportDate === localProductivityOverviewIsoDate()) {
    return new Date().getHours() * 60;
  }
  return 24 * 60;
}

function formatProductivityOverviewCutoff(cutoffMinute) {
  if (cutoffMinute >= 24 * 60) return "hela dagen";
  const hour = Math.max(0, Math.floor(cutoffMinute / 60));
  return `t.o.m. ${String(hour).padStart(2, "0")}:00`;
}

function productivityOverviewReports(report) {
  const reports = Array.isArray(report?.reports) ? report.reports : [];
  return reports.length ? reports : report ? [report] : [];
}

function productivityOverviewPeriodLabel(report) {
  const period = report?.period;
  if (!period) return formatProductivityOverviewCutoff(completedProductivityOverviewCutoffMinute(report?.date));
  const start = period.start_date || report?.date || "";
  const end = period.end_date || start;
  const label = period.label || "Period";
  if (!start || start === end) {
    const cutoff = formatProductivityOverviewCutoff(completedProductivityOverviewCutoffMinute(start));
    return `${label} ${start}${cutoff ? ` (${cutoff})` : ""}`;
  }
  return `${label} ${start} - ${end}`;
}

function productivityOverviewKey(value) {
  return String(value ?? "").trim().toLowerCase() || "unknown";
}

function normalizeProductivityOverviewProcessKey(value) {
  return String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9_ -]/g, "");
}

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

function createProductivityOverviewNode(type, id, label, parentId = null) {
  return {
    id,
    type,
    label: label || "Okänt",
    parentId,
    points: 0,
    workMinutes: 0,
    kpiMinutes: 0,
    eventCount: 0,
    financeVisible: false,
    financeCurrency: "SEK",
    financeRevenue: 0,
    financeCost: 0,
    financeResult: 0,
    financeWorkMinutes: 0,
    financeVasMinutes: 0,
    children: [],
    childMap: new Map(),
    cells: [],
  };
}

function ensureProductivityOverviewChild(parent, type, key, label) {
  const id = `${parent.id}/${type}:${encodeURIComponent(productivityOverviewKey(key))}`;
  let child = parent.childMap.get(id);
  if (!child) {
    child = createProductivityOverviewNode(type, id, label, parent.id);
    parent.childMap.set(id, child);
    parent.children.push(child);
  }
  return child;
}

function addProductivityOverviewPoints(node, points, eventCount = 0) {
  node.points = Math.round((Number(node.points || 0) + Number(points || 0)) * 100) / 100;
  node.eventCount += Number(eventCount || 0);
}

function addProductivityOverviewWorkMinutes(node, minutes) {
  node.workMinutes = Math.round((Number(node.workMinutes || 0) + Number(minutes || 0)) * 100) / 100;
}

function addProductivityOverviewKpiMinutes(node, minutes) {
  node.kpiMinutes = Math.round((Number(node.kpiMinutes || 0) + Number(minutes || 0)) * 100) / 100;
}

function roundProductivityOverviewMoney(value) {
  return Math.round(Number(value || 0) * 100) / 100;
}

function addProductivityOverviewFinance(node, finance) {
  if (!finance?.visible) return;
  node.financeVisible = true;
  node.financeCurrency = finance.currency || node.financeCurrency || "SEK";
  node.financeRevenue = roundProductivityOverviewMoney(Number(node.financeRevenue || 0) + Number(finance.revenue || 0));
  node.financeCost = roundProductivityOverviewMoney(Number(node.financeCost || 0) + Number(finance.cost || 0));
  node.financeResult = roundProductivityOverviewMoney(Number(node.financeResult || 0) + Number(finance.result || 0));
  node.financeWorkMinutes = Math.round((Number(node.financeWorkMinutes || 0) + Number(finance.work_minutes || 0)) * 100) / 100;
  node.financeVasMinutes = Math.round((Number(node.financeVasMinutes || 0) + Number(finance.vas_minutes || 0)) * 100) / 100;
}

function addProductivityOverviewFinanceToAncestors(node, finance, index) {
  let current = node;
  while (current) {
    addProductivityOverviewFinance(current, finance);
    current = index.get(current.parentId);
  }
}

function productivityOverviewFinanceVisible(report) {
  if (report?.finance?.visible) return true;
  return productivityOverviewReports(report).some((dayReport) => dayReport?.finance?.visible);
}

function productivityOverviewFinanceForProcess(cellFinance, share) {
  const ratio = Math.max(0, Math.min(1, Number(share || 0)));
  if (!cellFinance?.visible || ratio <= 0) return null;
  return {
    visible: true,
    currency: cellFinance.currency || "SEK",
    revenue: roundProductivityOverviewMoney(Number(cellFinance.revenue || 0) * ratio),
    cost: roundProductivityOverviewMoney(Number(cellFinance.cost || 0) * ratio),
    result: roundProductivityOverviewMoney(Number(cellFinance.result || 0) * ratio),
    work_minutes: Math.round(Number(cellFinance.work_minutes || 0) * ratio * 100) / 100,
    vas_minutes: Math.round(Number(cellFinance.vas_minutes || 0) * ratio * 100) / 100,
  };
}

function productivityOverviewCellWorkMinutes(cell) {
  if (cell?.kind === "kpi") return Number(cell?.minutes || 0);
  if (cell?.kind === "support") return Number(cell?.minutes || 0);
  if (Number(cell?.expected_points || 0) > 0) return Number(cell?.minutes || 0);
  return 0;
}

function productivityOverviewCellKpiMinutes(cell) {
  if (cell?.kind === "kpi") return Number(cell?.minutes || 0);
  if (Number(cell?.expected_points || 0) > 0) return Number(cell?.minutes || 0);
  return 0;
}

function productivityOverviewActivityLabel(cell) {
  return cell?.activity_label || cell?.display || "Okänd aktivitet";
}

function productivityOverviewAreaLabelForCell(cell) {
  return cell?.activity_area_name || cell?.activity_area_code || "Utan område";
}

function productivityOverviewAreaKeyForCell(cell) {
  return cell?.activity_area_id || cell?.activity_area_code || productivityOverviewAreaLabelForCell(cell);
}

function productivityOverviewIncludedCells(person, cutoffMinute) {
  return (person?.time_cells || [])
    .filter((cell) => Number(cell?.end_minute || 0) <= cutoffMinute)
    .filter((cell) => Number(cell?.points || 0) !== 0 || productivityOverviewCellWorkMinutes(cell) > 0);
}

function minuteFromProductivityOverviewTimestamp(value) {
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) return date.getHours() * 60 + date.getMinutes();
  const match = String(value || "").match(/(?:T|\s)(\d{1,2}):(\d{2})/);
  if (!match) return null;
  return Number(match[1]) * 60 + Number(match[2]);
}

function timeLabelFromProductivityOverviewMinute(minute) {
  const clamped = Math.max(0, Math.min(24 * 60, Number(minute || 0)));
  const hour = Math.floor(clamped / 60);
  const rest = clamped % 60;
  return `${String(hour).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

function productivityOverviewUnscheduledDiffCells(person, cutoffMinute, reportDate = "") {
  return (person?.diffs || [])
    .filter((diff) => String(diff?.scheduled_display || diff?.scheduled_activity || "") === "Ej schemalagd")
    .map((diff) => {
      const minute = minuteFromProductivityOverviewTimestamp(diff.time);
      if (minute == null) return null;
      const hourStart = Math.floor(minute / 60) * 60;
      const hourEnd = Math.min(24 * 60, hourStart + 60);
      if (hourEnd > cutoffMinute) return null;
      const process = diff.actual_process || "Okänd process";
      const points = Number(diff.points || 0);
      const processKey = normalizeProductivityOverviewProcessKey(process);
      return {
        hour: Math.floor(hourStart / 60),
        start: timeLabelFromProductivityOverviewMinute(hourStart),
        end: timeLabelFromProductivityOverviewMinute(hourEnd),
        start_minute: hourStart,
        end_minute: hourEnd,
        date: reportDate,
        activity_label: "Ej schemalagd",
        display: "Ej schemalagd",
        kind: "unscheduled",
        minutes: 0,
        expected_points: 0,
        points,
        event_count: 1,
        process_points: [{ process, process_key: processKey, points, event_count: 1 }],
      };
    })
    .filter(Boolean);
}

function processPointsForProductivityOverviewCell(cell) {
  const rows = Array.isArray(cell?.process_points) ? cell.process_points : [];
  const filtered = rows
    .map((item) => ({
      process: item?.process || "Okänd process",
      processKey: normalizeProductivityOverviewProcessKey(item?.process_key || item?.process || "Okänd process"),
      points: Number(item?.points || 0),
      eventCount: Number(item?.event_count || 0),
    }))
    .filter((item) => item.points !== 0);
  if (filtered.length) return filtered;
  const points = Number(cell?.points || 0);
  return points
    ? [{ process: "Poäng", processKey: "POANG", points, eventCount: Number(cell?.event_count || 0) }]
    : [];
}

function buildProductivityOverviewPersonHours(personNode) {
  const sortedCells = personNode.cells
    .slice()
    .sort((left, right) => {
      const dateDiff = String(left.reportDate || "").localeCompare(String(right.reportDate || ""), "sv");
      if (dateDiff) return dateDiff;
      return Number(left.cell?.start_minute || 0) - Number(right.cell?.start_minute || 0);
    });
  const multiDay = new Set(sortedCells.map((entry) => entry.reportDate).filter(Boolean)).size > 1;
  for (const entry of sortedCells) {
    const cell = entry.cell || {};
    const timeLabel = `${cell.start || ""}-${cell.end || ""}`.replace(/^-|-$/g, "") || "Okänd tid";
    const hourLabel = multiDay && entry.reportDate ? `${entry.reportDate} ${timeLabel}` : timeLabel;
    const hourNode = ensureProductivityOverviewChild(
      personNode,
      "hour",
      `${entry.reportDate || ""}-${cell.start_minute}-${cell.end_minute}`,
      hourLabel
    );
    hourNode.reportDate = entry.reportDate || "";
    hourNode.startMinute = Number(cell.start_minute || 0);
    const cellPoints = Number(cell.points || 0);
    addProductivityOverviewWorkMinutes(hourNode, productivityOverviewCellWorkMinutes(cell));
    addProductivityOverviewKpiMinutes(hourNode, productivityOverviewCellKpiMinutes(cell));
    addProductivityOverviewPoints(hourNode, cellPoints, Number(cell.event_count || 0));
    addProductivityOverviewFinance(hourNode, cell.finance);
    const processPoints = processPointsForProductivityOverviewCell(cell);
    const processPointTotal = processPoints.reduce((sum, item) => sum + Math.abs(Number(item.points || 0)), 0);
    for (const processPoint of processPoints) {
      const processNode = ensureProductivityOverviewChild(
        hourNode,
        "process",
        processPoint.processKey || processPoint.process,
        processPoint.process
      );
      processNode.processKey = processPoint.processKey || normalizeProductivityOverviewProcessKey(processPoint.process);
      addProductivityOverviewPoints(processNode, processPoint.points, processPoint.eventCount);
      if (cell.finance?.visible && processPointTotal > 0) {
        addProductivityOverviewFinance(
          processNode,
          productivityOverviewFinanceForProcess(cell.finance, Math.abs(Number(processPoint.points || 0)) / processPointTotal)
        );
      }
    }
  }
}

function productivityOverviewProcessRevenueRows(report) {
  const rows = Array.isArray(report?.finance?.process_revenues) ? report.finance.process_revenues : [];
  return rows
    .map((row) => ({
      ...row,
      processKey: normalizeProductivityOverviewProcessKey(row?.process_key || row?.process_label),
      revenue: Number(row?.revenue || 0),
      currency: row?.currency || report?.finance?.currency || "SEK",
    }))
    .filter((row) => row.processKey && Math.abs(row.revenue) > 0.001);
}

function applyProductivityOverviewProcessRevenues(root, report) {
  const rows = productivityOverviewProcessRevenueRows(report);
  if (!rows.length) return;
  const index = indexProductivityOverviewTree(root, new Map());
  const processNodes = Array.from(index.values()).filter((node) => node.type === "process");
  rows.forEach((row) => {
    const matches = processNodes.filter((node) => normalizeProductivityOverviewProcessKey(node.processKey || node.label) === row.processKey);
    if (!matches.length) {
      addProductivityOverviewFinance(root, {
        visible: true,
        currency: row.currency,
        revenue: row.revenue,
        cost: 0,
        result: row.revenue,
      });
      return;
    }
    const totalPoints = matches.reduce((sum, node) => sum + Math.abs(Number(node.points || 0)), 0);
    matches.forEach((node) => {
      const share = totalPoints > 0 ? Math.abs(Number(node.points || 0)) / totalPoints : 1 / matches.length;
      const revenue = roundProductivityOverviewMoney(row.revenue * share);
      addProductivityOverviewFinanceToAncestors(node, {
        visible: true,
        currency: row.currency,
        revenue,
        cost: 0,
        result: revenue,
      }, index);
    });
  });
}

function sortProductivityOverviewTree(node) {
  if (node.type === "person") {
    node.children.sort((left, right) => {
      const dateDiff = String(left.reportDate || "").localeCompare(String(right.reportDate || ""), "sv");
      if (dateDiff) return dateDiff;
      return Number(left.startMinute || 0) - Number(right.startMinute || 0);
    });
  } else {
    node.children.sort((left, right) => {
      const pointsDiff = Number(right.points || 0) - Number(left.points || 0);
      if (Math.abs(pointsDiff) > 0.001) return pointsDiff;
      return String(left.label || "").localeCompare(String(right.label || ""), "sv");
    });
  }
  for (const child of node.children) sortProductivityOverviewTree(child);
}

function indexProductivityOverviewTree(node, index = new Map()) {
  index.set(node.id, node);
  for (const child of node.children) indexProductivityOverviewTree(child, index);
  return index;
}

function buildProductivityOverviewTree(report) {
  const businessLabel = productivityOverviewUser?.business_name || productivityOverviewUser?.business_code || "Verksamheten";
  const root = createProductivityOverviewNode("business", "root", businessLabel);
  root.financeVisible = productivityOverviewFinanceVisible(report);
  root.financeCurrency = report?.finance?.currency || "SEK";
  for (const dayReport of productivityOverviewReports(report)) {
    const reportDate = dayReport?.date || "";
    const cutoffMinute = completedProductivityOverviewCutoffMinute(reportDate);
    for (const person of dayReport?.people || []) {
      const cells = [
        ...productivityOverviewIncludedCells(person, cutoffMinute),
        ...productivityOverviewUnscheduledDiffCells(person, cutoffMinute, reportDate),
      ];
      if (!cells.length) continue;
      for (const cell of cells) {
        const points = Number(cell.points || 0);
        const eventCount = Number(cell.event_count || 0);
        const workMinutes = productivityOverviewCellWorkMinutes(cell);
        const kpiMinutes = productivityOverviewCellKpiMinutes(cell);
        const areaLabel = productivityOverviewAreaLabelForCell(cell);
        const areaNode = ensureProductivityOverviewChild(root, "area", productivityOverviewAreaKeyForCell(cell), areaLabel);
        const activityLabel = productivityOverviewActivityLabel(cell);
        const activityNode = ensureProductivityOverviewChild(areaNode, "activity", activityLabel, activityLabel);
        const personNode = ensureProductivityOverviewChild(
          activityNode,
          "person",
          person.person_id || person.name,
          person.name || "Okänd person"
        );
        personNode.personId = person.person_id;
        personNode.cells.push({ person, cell, reportDate });
        addProductivityOverviewWorkMinutes(root, workMinutes);
        addProductivityOverviewWorkMinutes(areaNode, workMinutes);
        addProductivityOverviewWorkMinutes(activityNode, workMinutes);
        addProductivityOverviewWorkMinutes(personNode, workMinutes);
        addProductivityOverviewKpiMinutes(root, kpiMinutes);
        addProductivityOverviewKpiMinutes(areaNode, kpiMinutes);
        addProductivityOverviewKpiMinutes(activityNode, kpiMinutes);
        addProductivityOverviewKpiMinutes(personNode, kpiMinutes);
        addProductivityOverviewPoints(root, points, eventCount);
        addProductivityOverviewPoints(areaNode, points, eventCount);
        addProductivityOverviewPoints(activityNode, points, eventCount);
        addProductivityOverviewPoints(personNode, points, eventCount);
        addProductivityOverviewFinance(root, cell.finance);
        addProductivityOverviewFinance(areaNode, cell.finance);
        addProductivityOverviewFinance(activityNode, cell.finance);
        addProductivityOverviewFinance(personNode, cell.finance);
      }
    }
  }

  for (const area of root.children) {
    for (const activity of area.children) {
      for (const person of activity.children) buildProductivityOverviewPersonHours(person);
    }
  }
  applyProductivityOverviewProcessRevenues(root, report);
  sortProductivityOverviewTree(root);
  return root;
}

function productivityOverviewTypeLabel(type) {
  return {
    business: "Verksamhet",
    area: "Område",
    activity: "Aktivitet",
    person: "Person",
    hour: "Timme",
    process: "Process",
  }[type] || "";
}

function productivityOverviewChildSummary(node) {
  const count = node.children?.length || 0;
  if (!count) return `${formatProductivityOverviewNumber(node.eventCount, 0)} händelser`;
  const unit = {
    business: "områden",
    area: "aktiviteter",
    activity: "personer",
    person: "timmar",
    hour: "processer",
  }[node.type] || "grenar";
  return `${count} ${unit}`;
}

function productivityOverviewAncestors(node) {
  const path = [];
  let current = node;
  while (current) {
    path.unshift(current);
    current = productivityOverviewNodeIndex.get(current.parentId);
  }
  return path;
}

function renderProductivityOverviewBreadcrumbs(focusNode) {
  const target = document.getElementById("productivityOverviewBreadcrumbs");
  if (!target || !focusNode) return;
  const path = productivityOverviewAncestors(focusNode);
  target.innerHTML = path.map((node, index) => `
    <button type="button" class="${node.id === focusNode.id ? "active" : ""}" data-node-id="${escapeHtml(node.id)}">
      ${escapeHtml(index === 0 ? "Helbild" : node.label)}
    </button>
  `).join("");
}

function renderProductivityOverviewNodeMetric(node) {
  if (node?.type === "process") {
    return `<span class="productivity-overview-node-points">${escapeHtml(formatProductivityOverviewPoints(node.points))}</span>`;
  }
  const rate = productivityOverviewPointsPerHour(node);
  const scoreClass = productivityOverviewScoreClass(rate);
  return `
    <span class="productivity-overview-node-formula">
      <span>${escapeHtml(formatProductivityOverviewPoints(node.points))}</span>
      <span>/</span>
      <span>${escapeHtml(formatProductivityOverviewHours(node.workMinutes))}</span>
      <span>=</span>
    </span>
    <span class="productivity-overview-node-rate ${escapeHtml(scoreClass)}">${escapeHtml(formatProductivityOverviewRate(rate))}</span>
  `;
}

function productivityOverviewNodeHasFinance(node) {
  if (!node?.financeVisible) return false;
  return node.type === "business"
    || Number(node.financeWorkMinutes || 0) > 0
    || Math.abs(Number(node.financeRevenue || 0)) > 0.001
    || Math.abs(Number(node.financeCost || 0)) > 0.001
    || Math.abs(Number(node.financeResult || 0)) > 0.001;
}

function productivityOverviewFinanceResultClass(value) {
  const number = Number(value || 0);
  if (number > 0.001) return "good";
  if (number < -0.001) return "low";
  return "";
}

function renderProductivityOverviewFinance(node) {
  if (!productivityOverviewNodeHasFinance(node)) return "";
  const currency = node.financeCurrency || "SEK";
  return `
    <span class="productivity-overview-node-finance">
      <span>Intäkt ${escapeHtml(formatProductivityOverviewMoney(node.financeRevenue, currency))}</span>
      <span>Utgift ${escapeHtml(formatProductivityOverviewMoney(node.financeCost, currency))}</span>
      <span class="${escapeHtml(productivityOverviewFinanceResultClass(node.financeResult))}">Resultat ${escapeHtml(formatProductivityOverviewMoney(node.financeResult, currency))}</span>
    </span>
  `;
}

function renderProductivityOverviewNodeButton(node, options = {}) {
  const canFocus = Boolean(node.children?.length) && !options.staticNode;
  const tag = canFocus ? "button" : "div";
  const attrs = canFocus
    ? `type="button" data-node-id="${escapeHtml(node.id)}"`
    : (options.staticNode ? `data-node-id="${escapeHtml(node.id)}"` : "");
  return `
    <${tag} class="productivity-overview-node ${escapeHtml(node.type)}${canFocus ? " is-clickable" : ""}" ${attrs}>
      <span class="productivity-overview-node-type">${escapeHtml(productivityOverviewTypeLabel(node.type))}</span>
      <strong>${escapeHtml(node.label)}</strong>
      ${renderProductivityOverviewNodeMetric(node)}
      ${renderProductivityOverviewFinance(node)}
      <small>${escapeHtml(productivityOverviewChildSummary(node))}</small>
    </${tag}>
  `;
}

function renderProductivityOverviewProcessList(hourNode) {
  if (!hourNode.children?.length) return "";
  return `
    <div class="productivity-overview-process-list">
      ${hourNode.children.map((processNode) => `
        <div class="productivity-overview-process-row">
          <span>${escapeHtml(processNode.label)}</span>
          <strong>${escapeHtml(formatProductivityOverviewPoints(processNode.points))}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function renderProductivityOverviewPersonHours(personNode) {
  if (!personNode.children?.length) {
    return '<div class="empty-state">Inga processpoäng inom avslutad timme.</div>';
  }
  return `
    <div class="productivity-overview-branches productivity-overview-hours" data-parent-type="person">
      ${personNode.children.map((hourNode) => `
        <article class="productivity-overview-branch productivity-overview-hour-card">
          ${renderProductivityOverviewNodeButton(hourNode)}
          ${renderProductivityOverviewProcessList(hourNode)}
        </article>
      `).join("")}
    </div>
  `;
}

function renderProductivityOverviewBranches(node) {
  if (!node.children?.length) {
    return '<div class="empty-state">Inga poäng att visa inom avslutad timme.</div>';
  }
  if (node.type === "person") return renderProductivityOverviewPersonHours(node);
  return `
    <div class="productivity-overview-branches" data-parent-type="${escapeHtml(node.type)}">
      ${node.children.map((child) => `
        <div class="productivity-overview-branch">
          ${renderProductivityOverviewNodeButton(child)}
        </div>
      `).join("")}
    </div>
  `;
}

function renderProductivityOverviewSummary(root, report) {
  const target = document.getElementById("productivityOverviewSummary");
  if (!target) return;
  const rootRate = productivityOverviewPointsPerHour(root);
  const rootScoreClass = productivityOverviewScoreClass(rootRate);
  const periodText = productivityOverviewPeriodLabel(report);
  const areaCount = root.children.length;
  const activityCount = root.children.reduce((sum, area) => sum + area.children.length, 0);
  const personIds = new Set();
  for (const area of root.children) {
    for (const activity of area.children) {
      for (const person of activity.children) personIds.add(person.personId || person.label);
    }
  }
  const financeCards = root.financeVisible ? `
    <div class="productivity-kpi">
      <span>Intäkt</span>
      <strong>${escapeHtml(formatProductivityOverviewMoney(root.financeRevenue, root.financeCurrency))}</strong>
    </div>
    <div class="productivity-kpi">
      <span>Utgift</span>
      <strong>${escapeHtml(formatProductivityOverviewMoney(root.financeCost, root.financeCurrency))}</strong>
    </div>
    <div class="productivity-kpi">
      <span>Resultat</span>
      <strong class="${escapeHtml(productivityOverviewFinanceResultClass(root.financeResult))}">${escapeHtml(formatProductivityOverviewMoney(root.financeResult, root.financeCurrency))}</strong>
    </div>
  ` : "";
  target.innerHTML = `
    <div class="productivity-kpi">
      <span>Poäng / timmar</span>
      <strong class="productivity-overview-summary-rate ${escapeHtml(rootScoreClass)}">${escapeHtml(formatProductivityOverviewRate(rootRate))}</strong>
      <small class="productivity-overview-summary-formula">${escapeHtml(formatProductivityOverviewPoints(root.points))} / ${escapeHtml(formatProductivityOverviewHours(root.workMinutes))}</small>
    </div>
    ${financeCards}
    <div class="productivity-kpi">
      <span>Områden</span>
      <strong>${formatProductivityOverviewNumber(areaCount, 0)}</strong>
    </div>
    <div class="productivity-kpi">
      <span>Aktiviteter</span>
      <strong>${formatProductivityOverviewNumber(activityCount, 0)}</strong>
    </div>
    <div class="productivity-kpi">
      <span>Personer</span>
      <strong>${formatProductivityOverviewNumber(personIds.size, 0)}</strong>
    </div>
    <div class="productivity-kpi">
      <span>Period</span>
      <strong>${escapeHtml(periodText)}</strong>
    </div>
  `;
}

function renderProductivityOverviewShell() {
  const input = document.getElementById("productivityOverviewDate");
  if (input && !input.value) input.value = localProductivityOverviewIsoDate();
  updateProductivityOverviewDateDisplay();
  updateProductivityOverviewPeriodControls();
  updateProductivityOverviewDateNav();

  const summary = document.getElementById("productivityOverviewSummary");
  if (summary && !summary.innerHTML.trim()) {
    summary.innerHTML = `
      <div class="productivity-kpi"><span>Poäng / timmar</span><strong>-</strong></div>
      <div class="productivity-kpi"><span>Områden</span><strong>-</strong></div>
      <div class="productivity-kpi"><span>Aktiviteter</span><strong>-</strong></div>
      <div class="productivity-kpi"><span>Personer</span><strong>-</strong></div>
      <div class="productivity-kpi"><span>Period</span><strong>${escapeHtml(productivityOverviewPeriodDisplayLabel(input?.value || ""))}</strong></div>
    `;
  }

  const tree = document.getElementById("productivityOverviewTree");
  if (tree && !tree.innerHTML.trim()) {
    tree.innerHTML = '<div class="empty-state">Produktivitet hämtas i bakgrunden.</div>';
  }

  const status = document.getElementById("productivityOverviewStatus");
  if (status && !status.textContent.trim()) status.textContent = "Redo att hämta produktivitet.";
}

function setProductivityOverviewLoading(message) {
  const status = document.getElementById("productivityOverviewStatus");
  const summary = document.getElementById("productivityOverviewSummary");
  const tree = document.getElementById("productivityOverviewTree");
  const breadcrumbs = document.getElementById("productivityOverviewBreadcrumbs");
  if (status) status.textContent = message;
  summary?.setAttribute("aria-busy", "true");
  tree?.setAttribute("aria-busy", "true");
  if (tree) {
    if (productivityOverviewRoot) {
      tree.classList.add("is-changing");
    } else {
      tree.innerHTML = '<div class="empty-state">Produktivitet hämtas i bakgrunden.</div>';
    }
  }
  if (breadcrumbs && !productivityOverviewRoot) breadcrumbs.innerHTML = "";
}

function clearProductivityOverviewLoading() {
  document.getElementById("productivityOverviewSummary")?.removeAttribute("aria-busy");
  const tree = document.getElementById("productivityOverviewTree");
  tree?.removeAttribute("aria-busy");
  tree?.classList.remove("is-changing");
}

function renderProductivityOverviewTree() {
  const target = document.getElementById("productivityOverviewTree");
  if (!target || !productivityOverviewRoot) return;
  const focusNode = productivityOverviewNodeIndex.get(productivityOverviewFocusId) || productivityOverviewRoot;
  productivityOverviewFocusId = focusNode.id;
  renderProductivityOverviewBreadcrumbs(focusNode);
  target.classList.add("is-changing");
  target.innerHTML = `
    <section class="productivity-overview-camera" data-focus-type="${escapeHtml(focusNode.type)}">
      <div class="productivity-overview-root">
        ${renderProductivityOverviewNodeButton(focusNode, { staticNode: true })}
      </div>
      ${renderProductivityOverviewBranches(focusNode)}
    </section>
  `;
  window.requestAnimationFrame?.(() => target.classList.remove("is-changing"));
}

function closeProductivityOverviewContextMenu() {
  productivityOverviewContextMenu?.remove();
  productivityOverviewContextMenu = null;
}

function positionProductivityOverviewContextMenu(menu, x, y) {
  const margin = 8;
  const rect = menu.getBoundingClientRect();
  const left = Math.max(margin, Math.min(x, window.innerWidth - rect.width - margin));
  const top = Math.max(margin, Math.min(y, window.innerHeight - rect.height - margin));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

function openProductivityOverviewContextMenu(event, node) {
  closeProductivityOverviewContextMenu();
  if (!node || node.type !== "business") return;
  const canOpenSankeyInbound = typeof canViewPage === "function" && canViewPage(productivityOverviewUser, "sankeyInbound");
  const menu = document.createElement("div");
  menu.className = "productivity-overview-context-menu";
  menu.dataset.productivityOverviewContextMenu = "true";
  menu.innerHTML = `
    <button type="button" data-productivity-business-summary>
      Summering
    </button>
    ${canOpenSankeyInbound ? `
      <button type="button" data-productivity-sankey-inbound>
        Sankey - Inbound
      </button>
    ` : ""}
  `;
  menu.querySelector("[data-productivity-business-summary]")?.addEventListener("click", () => {
    closeProductivityOverviewContextMenu();
    void openProductivityBusinessSummaryDialog(node);
  });
  menu.querySelector("[data-productivity-sankey-inbound]")?.addEventListener("click", () => {
    closeProductivityOverviewContextMenu();
    const params = productivityOverviewSelectionParams(productivityOverviewDateValue());
    const query = params.toString() ? `?${params.toString()}` : "";
    if (typeof flowTrack === "function") {
      flowTrack("navigate", {
        control_id: "productivity-context-sankey-inbound",
        view: "productivity",
        target_view: "sankeyInbound",
        period: productivityOverviewPeriodValue(),
      });
    }
    window.location.href = `/sankey-inbound.html${query}`;
  });
  document.body.appendChild(menu);
  positionProductivityOverviewContextMenu(menu, event.clientX, event.clientY);
  productivityOverviewContextMenu = menu;
  menu.querySelector("button")?.focus({ preventScroll: true });
}

function productivityOverviewSelectionParams(dateValue = productivityOverviewDateValue()) {
  const params = new URLSearchParams();
  if (dateValue) params.set("date", dateValue);
  params.set("period", productivityOverviewPeriodValue());
  if (productivityOverviewReport?.period?.type === "custom") {
    if (productivityOverviewReport.period.start_date) params.set("start_date", productivityOverviewReport.period.start_date);
    if (productivityOverviewReport.period.end_date) params.set("end_date", productivityOverviewReport.period.end_date);
  }
  return params;
}

async function fetchProductivityBusinessSummary() {
  const params = productivityOverviewSelectionParams(productivityOverviewDateValue());
  const query = params.toString() ? `?${params.toString()}` : "";
  return api.get(`/api/productivity/overview/business-summary${query}`, {
    cacheTtlMs: PRODUCTIVITY_OVERVIEW_CACHE_TTL_MS,
  });
}

function productivityBusinessSummaryPeriodText(payload) {
  const period = payload?.period || productivityOverviewReport?.period || {};
  const label = period.label || productivityOverviewPeriodDisplayLabel(productivityOverviewDateValue());
  const start = period.start_date || productivityOverviewDateValue();
  const end = period.end_date || start;
  return start && end && start !== end ? `${label} ${start} - ${end}` : `${label} ${start || ""}`.trim();
}

function productivityBusinessSummaryMoney(value, currency, visible) {
  return visible ? formatProductivityOverviewMoney(value, currency) : "-";
}

function renderProductivityBusinessSummaryDialogContent(backdrop, payload) {
  const body = backdrop.querySelector("[data-productivity-business-summary-body]");
  if (!body) return;
  const rows = Array.isArray(payload?.companies) ? payload.companies : [];
  const totals = payload?.totals || {};
  const currency = payload?.currency || totals.currency || "SEK";
  const financeVisible = payload?.finance_visible !== false;
  const periodText = productivityBusinessSummaryPeriodText(payload);
  const moneyClass = (value) => escapeHtml(productivityOverviewFinanceResultClass(value));
  const financeNote = financeVisible ? "" : `
    <p class="productivity-overview-summary-note">Ekonomi visas inte för din behörighet.</p>
  `;
  const rowHtml = rows.length ? rows.map((row) => `
    <tr>
      <th scope="row">${escapeHtml(row.company_label || row.company || "Okänt bolag")}</th>
      <td>${escapeHtml(productivityBusinessSummaryMoney(row.revenue, currency, financeVisible))}</td>
      <td>${escapeHtml(productivityBusinessSummaryMoney(row.cost, currency, financeVisible))}</td>
      <td class="${moneyClass(row.result)}">${escapeHtml(productivityBusinessSummaryMoney(row.result, currency, financeVisible))}</td>
      <td>${escapeHtml(formatProductivityOverviewNumber(row.zero_pick_rows || 0, 0))}</td>
    </tr>
  `).join("") : `
    <tr>
      <td colspan="5" class="empty-cell">Inga rader för valt urval.</td>
    </tr>
  `;
  body.innerHTML = `
    <div class="productivity-overview-summary-meta">
      <span>${escapeHtml(periodText)}</span>
      <span>${escapeHtml(formatProductivityOverviewNumber(payload?.period?.days_with_data || 0, 0))}/${escapeHtml(formatProductivityOverviewNumber(payload?.period?.requested_days || 0, 0))} dagar</span>
    </div>
    ${financeNote}
    <div class="productivity-overview-summary-table-wrap">
      <table class="productivity-overview-summary-table">
        <thead>
          <tr>
            <th scope="col">Bolag</th>
            <th scope="col">Intäkt</th>
            <th scope="col">Kostnad</th>
            <th scope="col">Resultat</th>
            <th scope="col">Nollade rader</th>
          </tr>
        </thead>
        <tbody>${rowHtml}</tbody>
        <tfoot>
          <tr>
            <th scope="row">Totalt</th>
            <td>${escapeHtml(productivityBusinessSummaryMoney(totals.revenue, currency, financeVisible))}</td>
            <td>${escapeHtml(productivityBusinessSummaryMoney(totals.cost, currency, financeVisible))}</td>
            <td class="${moneyClass(totals.result)}">${escapeHtml(productivityBusinessSummaryMoney(totals.result, currency, financeVisible))}</td>
            <td>${escapeHtml(formatProductivityOverviewNumber(totals.zero_pick_rows || 0, 0))}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  `;
}

function renderProductivityBusinessSummaryDialogError(backdrop, error) {
  const body = backdrop.querySelector("[data-productivity-business-summary-body]");
  if (!body) return;
  const detail = error?.message ? ` (${error.message})` : "";
  body.innerHTML = `<div class="empty-state">Summering kunde inte hämtas${escapeHtml(detail)}.</div>`;
}

function closeProductivityBusinessSummaryDialog(backdrop, onKeydown) {
  document.removeEventListener("keydown", onKeydown);
  backdrop?.remove();
}

async function openProductivityBusinessSummaryDialog(node) {
  document.querySelector("[data-productivity-business-summary-dialog]")?.remove();
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.dataset.productivityBusinessSummaryDialog = "true";
  backdrop.innerHTML = `
    <div class="modal productivity-overview-summary-modal" role="dialog" aria-modal="true" aria-labelledby="productivityBusinessSummaryTitle">
      <div class="productivity-overview-summary-modal-head">
        <div>
          <h2 id="productivityBusinessSummaryTitle">Summering</h2>
          <p>${escapeHtml(node?.label || productivityOverviewRoot?.label || "Verksamhet")}</p>
        </div>
        <button type="button" class="productivity-overview-summary-close" aria-label="Stäng" title="Stäng" data-productivity-business-summary-close>×</button>
      </div>
      <div data-productivity-business-summary-body>
        <div class="empty-state">Hämtar summering...</div>
      </div>
      <div class="actions">
        <button type="button" data-productivity-business-summary-close>Stäng</button>
      </div>
    </div>
  `;
  const onKeydown = (event) => {
    if (event.key === "Escape") closeProductivityBusinessSummaryDialog(backdrop, onKeydown);
  };
  document.addEventListener("keydown", onKeydown);
  backdrop.querySelectorAll("[data-productivity-business-summary-close]").forEach((button) => {
    button.addEventListener("click", () => closeProductivityBusinessSummaryDialog(backdrop, onKeydown));
  });
  document.body.appendChild(backdrop);
  backdrop.querySelector("[data-productivity-business-summary-close]")?.focus({ preventScroll: true });
  try {
    const payload = await fetchProductivityBusinessSummary();
    renderProductivityBusinessSummaryDialogContent(backdrop, payload);
  } catch (error) {
    renderProductivityBusinessSummaryDialogError(backdrop, error);
    if (typeof showToast === "function") showToast("Summering kunde inte hämtas.", "error", 5000);
  }
}

function productivityOverviewSourceWarnings(report) {
  const warnings = [];
  const seen = new Set();
  const sourceGroups = Array.isArray(report?.source_status) ? report.source_status : [];
  for (const group of sourceGroups) {
    const sources = Array.isArray(group?.sources)
      ? group.sources
      : (Array.isArray(group) ? group : []);
    for (const source of sources) {
      if (source?.key !== "kpi" || source?.status !== "coredata_fallback") continue;
      const reason = String(source?.fallback_reason || "").trim();
      const message = reason ? `KPI API fallback: ${reason}` : "KPI från coredata";
      if (seen.has(message)) continue;
      seen.add(message);
      warnings.push(message);
    }
  }
  return warnings;
}

function productivityOverviewExportLabel(node) {
  const rate = productivityOverviewPointsPerHour(node);
  const finance = productivityOverviewNodeHasFinance(node)
    ? ` · Resultat ${formatProductivityOverviewMoney(node.financeResult, node.financeCurrency)}`
    : "";
  if (node?.type === "process") return `${formatProductivityOverviewPoints(node.points)}${finance}`;
  return `${formatProductivityOverviewPoints(node.points)} / ${formatProductivityOverviewHours(node.workMinutes)} = ${formatProductivityOverviewRate(rate)}${finance}`;
}

function productivityOverviewExportColor(node) {
  if (node?.type === "process") return "#4f46e5";
  const scoreClass = productivityOverviewScoreClass(productivityOverviewPointsPerHour(node));
  if (scoreClass === "good") return "#16a34a";
  if (scoreClass === "warn") return "#d97706";
  if (scoreClass === "low") return "#dc2626";
  return "#64748b";
}

function productivityOverviewExportWrap(text, maxChars = 24, maxLines = 2) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxChars && current) {
      lines.push(current);
      current = word;
      if (lines.length >= maxLines) break;
    } else {
      current = next;
    }
  }
  if (current && lines.length < maxLines) lines.push(current);
  if (!lines.length) lines.push("-");
  if (lines.length === maxLines && words.join(" ").length > lines.join(" ").length) {
    lines[maxLines - 1] = `${lines[maxLines - 1].slice(0, Math.max(1, maxChars - 1))}…`;
  }
  return lines;
}

function productivityOverviewExportNode(sourceNode, includedTypes = null, forceInclude = false) {
  const allowed = includedTypes instanceof Set ? includedTypes : new Set(PRODUCTIVITY_OVERVIEW_EXPORT_LEVELS.map((level) => level.type));
  const promotedChildren = [];
  for (const child of sourceNode.children || []) {
    const exported = productivityOverviewExportNode(child, allowed, false);
    if (Array.isArray(exported)) promotedChildren.push(...exported);
    else if (exported) promotedChildren.push(exported);
  }
  if (!forceInclude && !allowed.has(sourceNode.type)) return promotedChildren;
  return {
    source: sourceNode,
    children: promotedChildren,
    leafCount: 1,
    maxDepth: 0,
    x: 0,
    y: 0,
  };
}

function measureProductivityOverviewExportNode(node, depth = 0) {
  node.maxDepth = depth;
  if (!node.children.length) {
    node.leafCount = 1;
    return node;
  }
  node.leafCount = 0;
  for (const child of node.children) {
    measureProductivityOverviewExportNode(child, depth + 1);
    node.leafCount += child.leafCount;
    node.maxDepth = Math.max(node.maxDepth, child.maxDepth);
  }
  return node;
}

function assignProductivityOverviewExportPositions(node, state, depth = 0) {
  const width = state.nodeWidth;
  const stepX = state.nodeWidth + state.gapX;
  if (!node.children.length) {
    node.x = state.margin + state.nextLeaf * stepX + width / 2;
    state.nextLeaf += 1;
  } else {
    for (const child of node.children) assignProductivityOverviewExportPositions(child, state, depth + 1);
    node.x = (node.children[0].x + node.children[node.children.length - 1].x) / 2;
  }
  node.y = state.headerHeight + state.margin + depth * (state.nodeHeight + state.gapY) + state.nodeHeight / 2;
}

function flattenProductivityOverviewExportNodes(node, rows = []) {
  rows.push(node);
  for (const child of node.children) flattenProductivityOverviewExportNodes(child, rows);
  return rows;
}

function renderProductivityOverviewExportNode(node, state) {
  const source = node.source;
  const x = node.x - state.nodeWidth / 2;
  const y = node.y - state.nodeHeight / 2;
  const labelLines = productivityOverviewExportWrap(source.label, source.type === "hour" ? 28 : 24, 2);
  const metric = productivityOverviewExportLabel(source);
  const color = productivityOverviewExportColor(source);
  const labelSvg = labelLines.map((line, index) =>
    `<text x="${node.x}" y="${y + 34 + index * 15}" text-anchor="middle" class="node-label">${escapeHtml(line)}</text>`
  ).join("");
  return `
    <g>
      <rect x="${x}" y="${y}" width="${state.nodeWidth}" height="${state.nodeHeight}" rx="8" class="node-box ${escapeHtml(source.type)}" />
      <text x="${node.x}" y="${y + 17}" text-anchor="middle" class="node-type">${escapeHtml(productivityOverviewTypeLabel(source.type))}</text>
      ${labelSvg}
      <text x="${node.x}" y="${y + state.nodeHeight - 14}" text-anchor="middle" class="node-metric" fill="${color}">${escapeHtml(metric)}</text>
    </g>
  `;
}

function buildProductivityOverviewFlowchartSvg(rootNode) {
  const exportTree = measureProductivityOverviewExportNode(rootNode);
  const state = {
    nodeWidth: 238,
    nodeHeight: 86,
    gapX: 34,
    gapY: 78,
    margin: 28,
    headerHeight: 72,
    nextLeaf: 0,
  };
  assignProductivityOverviewExportPositions(exportTree, state);
  const width = Math.max(980, exportTree.leafCount * (state.nodeWidth + state.gapX) + state.margin * 2);
  const height = state.headerHeight + state.margin * 2 + (exportTree.maxDepth + 1) * state.nodeHeight + exportTree.maxDepth * state.gapY;
  const nodes = flattenProductivityOverviewExportNodes(exportTree);
  const edges = nodes.flatMap((node) =>
    node.children.map((child) => {
      const midY = (node.y + child.y) / 2;
      return `<path d="M ${node.x} ${node.y + state.nodeHeight / 2} V ${midY} H ${child.x} V ${child.y - state.nodeHeight / 2}" class="edge" />`;
    })
  ).join("");
  const period = productivityOverviewPeriodLabel(productivityOverviewReport);
  const title = `${rootNode?.source?.label || productivityOverviewRoot?.label || "Verksamhet"} · ${period}`;
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${Math.ceil(width)}" height="${Math.ceil(height)}" viewBox="0 0 ${Math.ceil(width)} ${Math.ceil(height)}" role="img" aria-label="${escapeHtml(title)}">
  <style>
    .title { font: 800 22px Arial, sans-serif; fill: #0f172a; }
    .subtitle { font: 700 13px Arial, sans-serif; fill: #64748b; }
    .edge { fill: none; stroke: #cbd5e1; stroke-width: 1.5; }
    .node-box { fill: #f8fafc; stroke: #cbd5e1; stroke-width: 1.2; }
    .node-box.business { fill: #eef2ff; stroke: #a5b4fc; }
    .node-box.area { fill: #eff6ff; stroke: #bfdbfe; }
    .node-box.activity { fill: #fffbeb; stroke: #fde68a; }
    .node-box.person { fill: #f0fdf4; stroke: #bbf7d0; }
    .node-box.hour { fill: #f8fafc; stroke: #cbd5e1; }
    .node-box.process { fill: #f5f3ff; stroke: #ddd6fe; }
    .node-type { font: 800 10px Arial, sans-serif; fill: #64748b; letter-spacing: .06em; text-transform: uppercase; }
    .node-label { font: 800 13px Arial, sans-serif; fill: #0f172a; }
    .node-metric { font: 800 12px Arial, sans-serif; }
  </style>
  <rect width="100%" height="100%" fill="#ffffff" />
  <text x="${state.margin}" y="31" class="title">${escapeHtml(productivityOverviewRoot?.label || "Produktivitet")}</text>
  <text x="${state.margin}" y="54" class="subtitle">${escapeHtml(period)} · Exporterad ${escapeHtml(formatProductivityOverviewTimestamp(new Date().toISOString()))}</text>
  ${edges}
  ${nodes.map((node) => renderProductivityOverviewExportNode(node, state)).join("")}
</svg>`;
}

function downloadProductivityOverviewText(filename, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function productivityOverviewSubtreeTypes(node, types = new Set()) {
  if (!node) return types;
  types.add(node.type);
  for (const child of node.children || []) productivityOverviewSubtreeTypes(child, types);
  return types;
}

function readProductivityOverviewExportLevels(focusNode) {
  const available = productivityOverviewSubtreeTypes(focusNode);
  let selected = new Set(available);
  try {
    const raw = localStorage.getItem(PRODUCTIVITY_OVERVIEW_EXPORT_LEVELS_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (Array.isArray(parsed)) {
      selected = new Set(parsed.filter((type) => available.has(type)));
    }
  } catch (_error) {}
  if (focusNode?.type) selected.add(focusNode.type);
  return selected;
}

function writeProductivityOverviewExportLevels(types) {
  try {
    localStorage.setItem(PRODUCTIVITY_OVERVIEW_EXPORT_LEVELS_KEY, JSON.stringify([...types]));
  } catch (_error) {}
}

function closeProductivityOverviewExportDialog(backdrop, onKeydown) {
  document.removeEventListener("keydown", onKeydown);
  backdrop?.remove();
}

function performProductivityOverviewFlowchartExport(includedTypes) {
  if (!productivityOverviewRoot) {
    if (typeof showToast === "function") {
      showToast("Det finns ingen produktivitetsöversikt att exportera.", "warn", 4000);
    }
    return;
  }
  const focusNode = productivityOverviewNodeIndex.get(productivityOverviewFocusId) || productivityOverviewRoot;
  const levels = includedTypes instanceof Set
    ? includedTypes
    : new Set(PRODUCTIVITY_OVERVIEW_EXPORT_LEVELS.map((level) => level.type));
  const exportNode = productivityOverviewExportNode(focusNode, levels, true);
  const svg = buildProductivityOverviewFlowchartSvg(exportNode);
  const period = productivityOverviewPeriodValue();
  const datePart = (productivityOverviewReport?.period?.start_date && productivityOverviewReport?.period?.end_date)
    ? `${productivityOverviewReport.period.start_date}_${productivityOverviewReport.period.end_date}`
    : productivityOverviewDateValue();
  const labelPart = String(focusNode.label || "verksamhet").toLowerCase().replace(/[^a-z0-9åäö]+/gi, "-").replace(/^-|-$/g, "") || "verksamhet";
  const filename = `produktivitet-flowchart-${period}-${datePart}-${labelPart}.svg`;
  downloadProductivityOverviewText(filename, svg, "image/svg+xml;charset=utf-8");
  if (typeof showToast === "function") showToast("Flowchart exporterad.", "success", 3000);
  if (typeof flowTrack === "function") {
    flowTrack("download", {
      control_id: "productivity-overview-export-flowchart",
      view: "productivity",
      period,
      focus_type: focusNode.type,
      levels: [...levels].join(","),
    });
  }
}

function openProductivityOverviewExportDialog() {
  if (!productivityOverviewRoot) {
    if (typeof showToast === "function") {
      showToast("Det finns ingen produktivitetsöversikt att exportera.", "warn", 4000);
    }
    return;
  }
  document.querySelector("[data-productivity-export-dialog]")?.remove();
  const focusNode = productivityOverviewNodeIndex.get(productivityOverviewFocusId) || productivityOverviewRoot;
  const available = productivityOverviewSubtreeTypes(focusNode);
  const selected = readProductivityOverviewExportLevels(focusNode);
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.dataset.productivityExportDialog = "true";
  backdrop.innerHTML = `
    <div class="modal productivity-overview-export-modal" role="dialog" aria-modal="true" aria-labelledby="productivityExportTitle">
      <h2 id="productivityExportTitle">Exportera flowchart</h2>
      <form data-productivity-export-form>
        <div class="productivity-overview-export-levels">
          ${PRODUCTIVITY_OVERVIEW_EXPORT_LEVELS.map((level) => {
            const isFocus = level.type === focusNode.type;
            const disabled = !available.has(level.type) || isFocus;
            const checked = selected.has(level.type) || isFocus;
            return `
              <label class="modal-checkbox">
                <input
                  type="checkbox"
                  name="export-level"
                  value="${escapeHtml(level.type)}"
                  ${checked ? "checked" : ""}
                  ${disabled ? "disabled" : ""}
                />
                ${escapeHtml(level.label)}
              </label>
            `;
          }).join("")}
        </div>
        <div class="actions">
          <button type="button" data-productivity-export-cancel>Avbryt</button>
          <button type="submit" class="primary">Exportera</button>
        </div>
      </form>
    </div>
  `;
  const onKeydown = (event) => {
    if (event.key === "Escape") closeProductivityOverviewExportDialog(backdrop, onKeydown);
  };
  document.addEventListener("keydown", onKeydown);
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) closeProductivityOverviewExportDialog(backdrop, onKeydown);
  });
  backdrop.querySelector("[data-productivity-export-cancel]")?.addEventListener("click", () => {
    closeProductivityOverviewExportDialog(backdrop, onKeydown);
  });
  backdrop.querySelector("[data-productivity-export-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const includedTypes = new Set(
      [...backdrop.querySelectorAll('input[name="export-level"]:checked')]
        .map((input) => input.value)
        .filter(Boolean)
    );
    includedTypes.add(focusNode.type);
    writeProductivityOverviewExportLevels(includedTypes);
    closeProductivityOverviewExportDialog(backdrop, onKeydown);
    performProductivityOverviewFlowchartExport(includedTypes);
  });
  document.body.appendChild(backdrop);
  backdrop.querySelector('input[name="export-level"]:not(:disabled)')?.focus();
}

function exportProductivityOverviewFlowchart() {
  openProductivityOverviewExportDialog();
}

function focusProductivityOverviewNode(nodeId) {
  if (!productivityOverviewNodeIndex.has(nodeId)) return;
  productivityOverviewFocusId = nodeId;
  renderProductivityOverviewTree();
}

window.focusProductivityOverviewNode = focusProductivityOverviewNode;
window.exportProductivityOverviewFlowchart = exportProductivityOverviewFlowchart;

function renderProductivityOverviewReport(report) {
  productivityOverviewReport = report;
  if (report?.period?.type) productivityOverviewPeriod = report.period.type;
  const dateInput = document.getElementById("productivityOverviewDate");
  if (dateInput && report?.date) dateInput.value = report.date;
  updateProductivityOverviewDateDisplay();
  updateProductivityOverviewPeriodControls();
  const dates = availableProductivityOverviewDates();
  if (dateInput && dates.length > 1) {
    dateInput.min = dates[0];
    dateInput.max = dates[dates.length - 1];
  }
  updateProductivityOverviewDateNav();

  const cutoffMinute = completedProductivityOverviewCutoffMinute(report?.date);
  productivityOverviewRoot = buildProductivityOverviewTree(report);
  productivityOverviewNodeIndex = indexProductivityOverviewTree(productivityOverviewRoot);
  productivityOverviewFocusId = "root";
  renderProductivityOverviewSummary(productivityOverviewRoot, report);
  renderProductivityOverviewTree();

  const status = document.getElementById("productivityOverviewStatus");
  const updated = formatProductivityOverviewTimestamp(report?.generated_at);
  const periodText = productivityOverviewPeriodLabel(report);
  const dataDays = report?.period?.days_with_data ?? productivityOverviewReports(report).length;
  const requestedDays = report?.period?.requested_days ?? dataDays;
  const daysText = requestedDays > 1 ? ` · ${dataDays}/${requestedDays} dagar` : "";
  const sync = report?.sync || {};
  const syncText = sync?.last_sync_at ? ` · API-sync ${formatProductivityOverviewTimestamp(sync.last_sync_at)}` : "";
  if (status) status.textContent = `${periodText}${daysText}${updated ? ` · uppdaterad ${updated}` : ""}${syncText}`;
  const warningText = productivityOverviewSourceWarnings(report).join(" · ");
  if (status && warningText) status.textContent = `${status.textContent} · ${warningText}`;
}

async function fetchProductivityOverviewReport(dateValue = "") {
  const params = new URLSearchParams();
  if (dateValue) params.set("date", dateValue);
  params.set("period", productivityOverviewPeriodValue());
  const query = params.toString() ? `?${params.toString()}` : "";
  const url = `/api/productivity/overview${query}`;
  const cached = productivityOverviewReportCache.get(url);
  if (cached && cached.expiresAt > Date.now()) return cached.data;
  productivityOverviewReportCache.delete(url);
  const data = await api.get(url, { cacheTtlMs: PRODUCTIVITY_OVERVIEW_CACHE_TTL_MS });
  productivityOverviewReportCache.set(url, {
    data,
    expiresAt: Date.now() + PRODUCTIVITY_OVERVIEW_CACHE_TTL_MS,
  });
  return data;
}

async function shiftProductivityOverviewDate(direction) {
  const input = document.getElementById("productivityOverviewDate");
  if (!input) return;
  const next = adjacentProductivityOverviewDate(direction);
  if (!next || next === input.value) return;
  input.value = next;
  updateProductivityOverviewDateDisplay();
  updateProductivityOverviewDateNav();
  await loadProductivityOverview();
}

function productivityOverviewStreamParams(dateValue) {
  const params = new URLSearchParams();
  if (dateValue) params.set("date", dateValue);
  params.set("period", productivityOverviewPeriodValue());
  return params;
}

function renderProductivityOverviewProgress(state) {
  const el = document.getElementById("productivityOverviewProgress");
  if (!el) return;
  if (!state) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  const items = [...state.steps.values()].sort((a, b) => a.step - b.step);
  const currentStep = items.reduce((max, item) => Math.max(max, item.step), 0);
  // En månad = 30+ steg; visa bara de senaste raderna så loggen inte svämmar över.
  const recent = items.slice(-6);
  const rows = recent
    .map((item) => {
      const done = Boolean(item.done);
      const icon = done ? "✓" : "⟳";
      return `<li class="${done ? "is-done" : "is-active"}"><span class="fetch-progress-icon">${icon}</span>${escapeHtml(item.label)}</li>`;
    })
    .join("");
  el.hidden = false;
  el.innerHTML = `
    <div class="fetch-progress-head">Hämtar produktivitet… <strong>${Math.min(currentStep, state.total)}/${state.total}</strong></div>
    <ul class="fetch-progress-list">${rows}</ul>
  `;
}

function applyProductivityOverviewReport(report, loadToken, options = {}) {
  if (loadToken !== productivityOverviewLoadToken) return;
  if (options.cacheUrl) {
    productivityOverviewReportCache.set(options.cacheUrl, {
      data: report,
      expiresAt: Date.now() + PRODUCTIVITY_OVERVIEW_CACHE_TTL_MS,
    });
  }
  renderProductivityOverviewProgress(null);
  renderProductivityOverviewReport(report);
}

function handleProductivityOverviewError(error, loadToken) {
  if (loadToken !== productivityOverviewLoadToken) return;
  renderProductivityOverviewProgress(null);
  productivityOverviewReport = null;
  productivityOverviewRoot = null;
  productivityOverviewNodeIndex = new Map();
  const summary = document.getElementById("productivityOverviewSummary");
  const tree = document.getElementById("productivityOverviewTree");
  const breadcrumbs = document.getElementById("productivityOverviewBreadcrumbs");
  const status = document.getElementById("productivityOverviewStatus");
  if (summary) summary.innerHTML = "";
  if (breadcrumbs) breadcrumbs.innerHTML = "";
  if (tree) tree.innerHTML = '<div class="empty-state">Produktivitet kunde inte hämtas.</div>';
  const detail = error?.message ? ` (${error.message})` : "";
  if (status) status.textContent = `Produktivitet kunde inte hämtas${detail}`;
  if (typeof showToast === "function") {
    showToast(status?.textContent || "Produktivitet kunde inte hämtas", "error", 7000);
  }
}

async function loadProductivityOverviewViaFetch(loadToken) {
  setProductivityOverviewLoading("Hämtar produktivitetsöversikt...");
  try {
    await waitForProductivityOverviewPaint();
    const report = await fetchProductivityOverviewReport(productivityOverviewDateValue());
    if (loadToken !== productivityOverviewLoadToken) return;
    setProductivityOverviewLoading("Beräknar och ritar produktivitet...");
    await waitForProductivityOverviewPaint();
    applyProductivityOverviewReport(report, loadToken);
  } catch (error) {
    handleProductivityOverviewError(error, loadToken);
  } finally {
    if (loadToken === productivityOverviewLoadToken) clearProductivityOverviewLoading();
  }
}

function loadProductivityOverviewViaStream(loadToken) {
  const dateValue = productivityOverviewDateValue();
  const cacheUrl = `/api/productivity/overview?${productivityOverviewStreamParams(dateValue).toString()}`;
  const cached = productivityOverviewReportCache.get(cacheUrl);
  if (cached && cached.expiresAt > Date.now()) {
    setProductivityOverviewLoading("Ritar produktivitet...");
    applyProductivityOverviewReport(cached.data, loadToken);
    clearProductivityOverviewLoading();
    return;
  }
  setProductivityOverviewLoading("Hämtar produktivitetsöversikt...");
  const progressState = { total: 2, steps: new Map() };
  renderProductivityOverviewProgress(progressState);
  const source = new EventSource(`/api/productivity/overview/stream?${productivityOverviewStreamParams(dateValue).toString()}`);
  productivityOverviewEventSource = source;
  let settled = false;
  const detach = () => {
    if (productivityOverviewEventSource === source) productivityOverviewEventSource = null;
  };
  source.onmessage = (event) => {
    if (loadToken !== productivityOverviewLoadToken) {
      settled = true;
      source.close();
      detach();
      return;
    }
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    if (data.type === "start") {
      progressState.total = Number(data.total) || progressState.total;
      renderProductivityOverviewProgress(progressState);
    } else if (data.type === "progress") {
      progressState.total = Number(data.total) || progressState.total;
      progressState.steps.set(Number(data.step), data);
      renderProductivityOverviewProgress(progressState);
    } else if (data.type === "done") {
      settled = true;
      source.close();
      detach();
      applyProductivityOverviewReport(data.payload, loadToken, { cacheUrl });
      clearProductivityOverviewLoading();
    } else if (data.type === "error") {
      settled = true;
      source.close();
      detach();
      handleProductivityOverviewError(new Error(data.message || "Okänt fel"), loadToken);
      clearProductivityOverviewLoading();
    }
  };
  source.onerror = () => {
    if (settled) return;
    settled = true;
    source.close();
    detach();
    // Strömmen gick inte att etablera – fall tillbaka på vanlig GET.
    void loadProductivityOverviewViaFetch(loadToken);
  };
}

function loadProductivityOverview() {
  const loadToken = ++productivityOverviewLoadToken;
  closeProductivityOverviewContextMenu();
  if (productivityOverviewEventSource) {
    productivityOverviewEventSource.close();
    productivityOverviewEventSource = null;
  }
  if (typeof EventSource === "undefined") {
    return loadProductivityOverviewViaFetch(loadToken);
  }
  return loadProductivityOverviewViaStream(loadToken);
}

async function initProductivityOverviewPage() {
  renderProductivityOverviewShell();
  productivityOverviewUser = await initPage("productivity");
  if (!productivityOverviewUser) return;
  const input = document.getElementById("productivityOverviewDate");
  if (input && !input.value) input.value = localProductivityOverviewIsoDate();
  updateProductivityOverviewDateDisplay();
  updateProductivityOverviewPeriodControls();
  document.querySelectorAll(".productivity-overview-period-toggle button[data-period]").forEach((button) => {
    if (["week", "month", "year"].includes(button.dataset.period)) {
      button.title = "Vänsterklick: byt period · Högerklick: välj specifik";
    }
    button.addEventListener("click", () => {
      const nextPeriod = button.dataset.period || "day";
      if (nextPeriod === productivityOverviewPeriod) return;
      productivityOverviewPeriod = nextPeriod;
      updateProductivityOverviewPeriodControls();
      updateProductivityOverviewDateNav();
      void loadProductivityOverview();
    });
    button.addEventListener("contextmenu", (event) => {
      const period = button.dataset.period || "day";
      if (!["week", "month", "year"].includes(period)) return;
      event.preventDefault();
      const input = document.getElementById("productivityOverviewDate");
      window.flowPeriodPicker?.open({
        period,
        anchorEl: button,
        currentIso: productivityOverviewDateValue(),
        onPick: (iso) => {
          if (input) input.value = iso;
          productivityOverviewPeriod = period;
          updateProductivityOverviewDateDisplay();
          updateProductivityOverviewPeriodControls();
          updateProductivityOverviewDateNav();
          void loadProductivityOverview();
        },
      });
    });
  });
  document.getElementById("productivityOverviewPrevDate")?.addEventListener("click", () => {
    void shiftProductivityOverviewDate(-1);
  });
  document.getElementById("productivityOverviewNextDate")?.addEventListener("click", () => {
    void shiftProductivityOverviewDate(1);
  });
  document.getElementById("productivityOverviewRootBtn")?.addEventListener("click", () => {
    focusProductivityOverviewNode("root");
  });
  document.getElementById("productivityOverviewExportFlowchart")?.addEventListener("click", exportProductivityOverviewFlowchart);
  input?.addEventListener("change", () => {
    updateProductivityOverviewDateDisplay();
    void loadProductivityOverview();
  });
  const overviewTree = document.getElementById("productivityOverviewTree");
  overviewTree?.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-node-id]");
    if (!button) return;
    focusProductivityOverviewNode(button.getAttribute("data-node-id"));
  });
  overviewTree?.addEventListener("contextmenu", (event) => {
    const target = event.target.closest?.("[data-node-id]");
    if (!target) return;
    const node = productivityOverviewNodeIndex.get(target.getAttribute("data-node-id"));
    if (!node || node.type !== "business") return;
    event.preventDefault();
    openProductivityOverviewContextMenu(event, node);
  });
  document.addEventListener("click", (event) => {
    if (event.target.closest?.("[data-productivity-overview-context-menu]")) return;
    closeProductivityOverviewContextMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeProductivityOverviewContextMenu();
  });
  document.getElementById("productivityOverviewBreadcrumbs")?.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-node-id]");
    if (!button) return;
    focusProductivityOverviewNode(button.getAttribute("data-node-id"));
  });
  void loadProductivityOverview();
}

document.addEventListener("DOMContentLoaded", () => {
  void initProductivityOverviewPage();
});

// @ts-check
// Utdelad ur productivity_overview.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter productivity_overview.js via <script>-tagg.

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

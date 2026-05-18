let productivityReport = null;
let productivityFileStatus = null;
let productivityTargets = null;
let productivityTargetsSignature = "";
let productivityDataset = null;
let productivityDatasetSignature = "";
let productivityDatasetPromise = null;

const productivityReportCache = new Map();
const productivityReportRequests = new Map();
const productivityLocalFiles = {};

const PRODUCTIVITY_HOURS = Array.from({ length: 18 }, (_, index) => index + 6);
const PRODUCTIVITY_SOURCE_SPECS = [
  {
    key: "pick",
    label: "Plocklogg",
    prefix: "v_ask_pick_log_full",
    required: true,
    visible: true,
    headerHints: ["Zon", "Plockat", "Anv\u00e4ndare", "\u00c4ndrad", "Bolag"],
  },
  {
    key: "trans",
    label: "Translogg",
    prefix: "v_ask_trans_log",
    required: true,
    visible: true,
    headerHints: ["Pallid", "Fr\u00e5n", "Till", "Antal", "Timestamp"],
  },
  {
    key: "pallet",
    label: "Palllastningslogg",
    prefix: "v_ask_palletloading_log",
    required: true,
    visible: true,
    headerHints: ["Plockpallsnr.", "Palltyp", "Pallplacering", "Transnr.", "Vikt"],
  },
  {
    key: "kpi",
    label: "KPI-M\u00e5l",
    prefix: "v_ask_kpi_target",
    required: true,
    visible: false,
    headerHints: ["Fl\u00f6desnamn", "Processnamn", "Beskrivning", "Rader", "Kollin"],
  },
];
const VISIBLE_PRODUCTIVITY_SOURCE_SPECS = PRODUCTIVITY_SOURCE_SPECS.filter((spec) => spec.visible);
const PRODUCTIVITY_SOURCE_BY_KEY = Object.fromEntries(PRODUCTIVITY_SOURCE_SPECS.map((spec) => [spec.key, spec]));
const PRODUCTIVITY_GROUPS = [
  { id: "gg", title: "Granng\u00e5rden" },
  { id: "autostore", title: "Autostore och e-handel" },
  { id: "mg", title: "Mestergruppen" },
];
const PRODUCTIVITY_GROUP_TITLES = Object.fromEntries(PRODUCTIVITY_GROUPS.map((group) => [group.id, group.title]));
const EXCLUDED_GG_USERS = new Set(["FILI10", "SEBA80"]);
const EXCLUDED_MG_USERS = new Set(["ANTO87", "HUGO49"]);

const PRODUCTIVITY_SECTION_SPECS = [
  {
    id: "gg_pick_ab",
    group_id: "gg",
    title: "Plockzon A/B",
    source: "pick",
    process: "Manual_Pick",
    target_company: "GG",
    target_metric: "rader",
    total_source: "pick",
    predicate: (event) => (
      companyContains(event, "GG")
      && ["A", "B"].includes(event.zone)
      && !EXCLUDED_GG_USERS.has(event.user)
    ),
  },
  {
    id: "gg_pick_s",
    group_id: "gg",
    title: "Plockzon S",
    source: "pick",
    process: "Bulky_Pick",
    target_company: "GG",
    target_metric: "rader",
    total_source: "pick",
    predicate: (event) => (
      companyContains(event, "GG")
      && event.zone === "S"
      && !EXCLUDED_GG_USERS.has(event.user)
    ),
  },
  {
    id: "as_store_pick",
    group_id: "autostore",
    title: "Butik Plock AS - GG + MG",
    source: "pick",
    process: "Autostore",
    target_company: "GG",
    target_metric: "rader",
    total_source: "pick",
    predicate: (event) => event.zone === "R",
  },
  {
    id: "gg_decanting",
    group_id: "autostore",
    title: "Granng\u00e5rden Dekantering",
    source: "trans",
    process: "Decanting",
    target_company: "GG",
    target_metric: "rader",
    total_source: "trans",
    predicate: (event) => companyIs(event, "GG") && String(event.to || "").toUpperCase().startsWith("AS"),
  },
  {
    id: "gg_ecom_pick",
    group_id: "autostore",
    title: "Granng\u00e5rden E-Handel Plock",
    source: "pick",
    process: "E_Commerce",
    target_company: "GG",
    target_metric: "rader",
    total_source: "pick",
    predicate: (event) => companyContains(event, "GG") && event.zone === "E",
  },
  {
    id: "gg_ecom_pack",
    group_id: "autostore",
    title: "Granng\u00e5rden E-Handel Pack",
    source: "pallet",
    process: "Ecom_pack",
    target_company: "GG",
    target_metric: "pallar",
    total_source: "none",
    predicate: (event) => (
      companyIs(event, "GG")
      && String(event.type || "").trim() === "220"
      && event.user !== "swisslogautostoreintegration"
    ),
  },
  {
    id: "mg_decanting",
    group_id: "autostore",
    title: "Mestergruppen Dekantering",
    source: "trans",
    process: "Decanting",
    target_company: "MG",
    target_metric: "rader",
    total_source: "trans",
    predicate: (event) => companyIs(event, "MG") && String(event.to || "").toUpperCase().startsWith("AS"),
  },
  {
    id: "mg_ecom_pick",
    group_id: "autostore",
    title: "Mestergruppen E-Handel Plock",
    source: "pick",
    process: "E_Commerce",
    target_company: "MG",
    target_metric: "rader",
    total_source: "pick",
    predicate: (event) => companyContains(event, "MG") && event.zone === "Q",
  },
  {
    id: "mg_ecom_pack",
    group_id: "autostore",
    title: "Mestergruppen E-Handel Pack",
    source: "pallet",
    process: "Ecom_pack",
    target_company: "MG",
    target_metric: "pallar",
    total_source: "none",
    predicate: (event) => (
      companyIs(event, "MG")
      && String(event.type || "").trim() === "220"
      && event.user !== "swisslogautostoreintegration"
    ),
  },
  {
    id: "mg_pick_abn",
    group_id: "mg",
    title: "Plockzon A/B/N",
    source: "pick",
    process: "Manual_Pick",
    target_company: "MG",
    target_metric: "rader",
    total_source: "pick",
    predicate: (event) => (
      companyContains(event, "MG")
      && ["A", "B", "N"].includes(event.zone)
      && !EXCLUDED_MG_USERS.has(event.user)
    ),
  },
  {
    id: "mg_pick_o",
    group_id: "mg",
    title: "Plockzon O",
    source: "pick",
    process: "Bulky_Pick",
    target_company: "MG",
    target_metric: "rader",
    total_source: "pick",
    predicate: (event) => (
      companyContains(event, "MG")
      && event.zone === "O"
      && !EXCLUDED_MG_USERS.has(event.user)
    ),
  },
];

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function formatNumber(value, decimals = 0) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString("sv-SE", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatMetric(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  const decimals = Math.abs(Number(value)) < 10 && !Number.isInteger(Number(value)) ? 1 : 0;
  return formatNumber(value, decimals);
}

function formatPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return (Number(value) * 100).toLocaleString("sv-SE", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }) + " %";
}

function formatTimestamp(value) {
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

function addDays(isoDate, days) {
  if (!isoDate) return "";
  const [year, month, day] = isoDate.split("-").map(Number);
  if (![year, month, day].every(Number.isFinite)) return "";
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function formatFileSize(size) {
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  if (size >= 1024) return `${(size / 1024).toFixed(1)} kB`;
  return `${size || 0} B`;
}

function metricClass(value) {
  if (value == null) return "";
  if (value >= 1) return " good";
  if (value >= 0.85) return " warn";
  return " low";
}

function clearProductivityReportCache() {
  productivityReportCache.clear();
  productivityReportRequests.clear();
}

function resetLocalProductivityDataset() {
  productivityDataset = null;
  productivityDatasetSignature = "";
  productivityDatasetPromise = null;
  clearProductivityReportCache();
}

function activeGroupFilter() {
  return document.getElementById("productivityGroupFilter").value;
}

function activeSearch() {
  return document.getElementById("productivitySearch").value.trim().toLowerCase();
}

function sectionMatches(section, search) {
  if (!search) return true;
  if (section.title.toLowerCase().includes(search)) return true;
  return section.rows.some((row) => row.user.toLowerCase().includes(search));
}

function filteredRows(section, search) {
  if (!search || section.title.toLowerCase().includes(search)) return section.rows;
  return section.rows.filter((row) => row.user.toLowerCase().includes(search));
}

function normalizeHeader(value) {
  return String(value ?? "").trim().replace(/^\ufeff/, "").toLowerCase();
}

function detectDelimiter(text) {
  const firstLine = String(text || "").split(/\r?\n/).find((line) => line.trim()) || "";
  const candidates = ["\t", ";", ","];
  return candidates
    .map((delimiter) => ({ delimiter, count: (firstLine.match(new RegExp(escapeRegExp(delimiter), "g")) || []).length }))
    .sort((a, b) => b.count - a.count)[0]?.delimiter || "\t";
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function parseDelimitedLine(line, delimiter) {
  const values = [];
  let current = "";
  let inQuotes = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === '"') {
      if (inQuotes && line[index + 1] === '"') {
        current += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === delimiter && !inQuotes) {
      values.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  values.push(current);
  return values;
}

function forEachTextLine(text, callback) {
  let start = 0;
  for (let index = 0; index <= text.length; index += 1) {
    if (index !== text.length && text[index] !== "\n") continue;
    let line = text.slice(start, index);
    if (line.endsWith("\r")) line = line.slice(0, -1);
    callback(line);
    start = index + 1;
  }
}

function parseProductivityCsv(text, onRow) {
  const delimiter = detectDelimiter(text);
  let lookup = null;
  let rows = 0;

  forEachTextLine(text, (line) => {
    if (!line.trim()) return;
    const values = parseDelimitedLine(line, delimiter);
    if (!lookup) {
      lookup = Object.fromEntries(values.map((header, index) => [normalizeHeader(header), index]));
      return;
    }
    rows += 1;
    onRow(lookup, values);
  });

  return rows;
}

function csvCell(values, lookup, ...names) {
  for (const name of names) {
    const index = lookup[normalizeHeader(name)];
    if (index != null && index < values.length) return String(values[index] ?? "").trim();
  }
  return "";
}

function parseNumber(value) {
  const text = String(value || "").trim().replace(/\u00a0/g, "").replace(/\s+/g, "").replace(",", ".");
  if (!text) return 0;
  const number = Number(text);
  return Number.isFinite(number) ? number : 0;
}

function parseTimestampParts(value) {
  const text = String(value || "").trim();
  if (!text) return null;

  let match = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  if (!match) {
    match = text.match(/^(\d{4})(\d{2})(\d{2})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?/);
  }
  if (!match) return null;

  const [, year, month, day, hour = "0"] = match;
  return {
    date: `${year}-${month}-${day}`,
    hour: Number(hour),
  };
}

function cleanUser(value) {
  return String(value || "").trim();
}

function companyContains(event, company) {
  return String(event.company || "").toUpperCase().includes(company.toUpperCase());
}

function companyIs(event, company) {
  return String(event.company || "").trim().toUpperCase() === company.toUpperCase();
}

function localFilesSignature() {
  return VISIBLE_PRODUCTIVITY_SOURCE_SPECS
    .map((spec) => {
      const file = productivityLocalFiles[spec.key]?.file;
      return file ? `${spec.key}:${file.name}:${file.size}:${file.lastModified}` : `${spec.key}:missing`;
    })
    .join("|");
}

async function readFileSample(file) {
  return await file.slice(0, 8192).text();
}

function classifyProductivityLocalFile(file, sample) {
  const name = String(file?.name || "").toLowerCase();
  for (const spec of PRODUCTIVITY_SOURCE_SPECS) {
    if (name.startsWith(spec.prefix.toLowerCase())) return spec.key;
  }

  const firstLine = String(sample || "").split(/\r?\n/).find((line) => line.trim()) || "";
  if (!firstLine) return null;
  const delimiter = detectDelimiter(firstLine);
  const headers = new Set(parseDelimitedLine(firstLine, delimiter).map((header) => normalizeHeader(header)));
  for (const spec of PRODUCTIVITY_SOURCE_SPECS) {
    if (spec.headerHints.every((hint) => headers.has(normalizeHeader(hint)))) return spec.key;
  }
  return null;
}

function buildLocalFileStatus(serverStatus = {}) {
  const files = Object.fromEntries(VISIBLE_PRODUCTIVITY_SOURCE_SPECS.map((spec) => {
    const entry = productivityLocalFiles[spec.key];
    const file = entry?.file;
    return [spec.key, {
      key: spec.key,
      label: spec.label,
      required: spec.required,
      visible: spec.visible,
      uploaded: Boolean(file),
      name: file?.name || null,
      modified_at: file?.lastModified ? new Date(file.lastModified).toISOString() : null,
      size: file?.size || null,
      size_label: file ? formatFileSize(file.size) : null,
    }];
  }));
  const missing = Object.values(files)
    .filter((file) => file.required && !file.uploaded)
    .map((file) => file.key);
  const kpiLoaded = Boolean(serverStatus.kpi_loaded);
  return {
    ready: missing.length === 0 && kpiLoaded,
    missing,
    files,
    kpi_loaded: kpiLoaded,
  };
}

function createDataset() {
  return {
    rawCounts: { pick: 0, trans: 0, pallet: 0 },
    dates: new Set(),
    sectionBuckets: {},
    pickTotals: {},
    transTotals: {},
  };
}

function ensureNested(root, ...keys) {
  let current = root;
  for (const key of keys) {
    if (!current[key]) current[key] = {};
    current = current[key];
  }
  return current;
}

function addDate(dataset, dateValue) {
  if (dateValue) dataset.dates.add(dateValue);
}

function incrementSectionBucket(dataset, event, spec) {
  if (!event.date || !PRODUCTIVITY_HOURS.includes(event.hour)) return;
  const userBucket = ensureNested(dataset.sectionBuckets, event.date, spec.id, event.user);
  userBucket[event.hour] = (userBucket[event.hour] || 0) + 1;
}

function addSectionEvent(dataset, event, source) {
  if (!event.date) return;
  addDate(dataset, event.date);
  for (const spec of PRODUCTIVITY_SECTION_SPECS) {
    if (spec.source === source && spec.predicate(event)) {
      incrementSectionBucket(dataset, event, spec);
    }
  }
}

function parsePickEvent(values, lookup) {
  const user = cleanUser(csvCell(values, lookup, "Anv\u00e4ndare", "Anvandare"));
  if (!user) return null;
  const timestamp = parseTimestampParts(csvCell(values, lookup, "\u00c4ndrad", "Andrad"));
  return {
    user,
    zone: csvCell(values, lookup, "Zon").toUpperCase(),
    company: csvCell(values, lookup, "Bolag"),
    date: timestamp?.date || null,
    hour: timestamp?.hour ?? null,
    kolli: parseNumber(csvCell(values, lookup, "Plockat")),
    vikt: parseNumber(csvCell(values, lookup, "Vikt")),
  };
}

function parseTransEvent(values, lookup) {
  const user = cleanUser(csvCell(values, lookup, "Anv\u00e4ndare", "Anvandare"));
  if (!user) return null;
  const timestamp = parseTimestampParts(csvCell(values, lookup, "Timestamp"));
  return {
    user,
    company: csvCell(values, lookup, "Bolag"),
    to: csvCell(values, lookup, "Till"),
    date: timestamp?.date || null,
    hour: timestamp?.hour ?? null,
    antal: parseNumber(csvCell(values, lookup, "Antal")),
  };
}

function parsePalletEvent(values, lookup) {
  const user = cleanUser(csvCell(values, lookup, "Anv\u00e4ndare", "Anvandare"));
  if (!user) return null;
  const timestamp = parseTimestampParts(csvCell(values, lookup, "\u00c4ndrad", "Andrad"));
  return {
    user,
    company: csvCell(values, lookup, "Bolag"),
    type: csvCell(values, lookup, "Typ"),
    date: timestamp?.date || null,
    hour: timestamp?.hour ?? null,
  };
}

async function parseProductivityFile(dataset, key) {
  const entry = productivityLocalFiles[key];
  if (!entry?.file) throw new Error(`Saknar ${PRODUCTIVITY_SOURCE_BY_KEY[key].label}`);
  document.getElementById("productivityStatus").textContent = `L\u00e4ser ${entry.file.name} lokalt...`;
  await new Promise((resolve) => setTimeout(resolve, 0));

  const text = await entry.file.text();
  const rows = parseProductivityCsv(text, (lookup, values) => {
    if (key === "pick") {
      const event = parsePickEvent(values, lookup);
      if (!event?.date) return;
      addDate(dataset, event.date);
      const totals = ensureNested(dataset.pickTotals, event.date, event.user);
      totals.kolli = (totals.kolli || 0) + event.kolli;
      totals.vikt = (totals.vikt || 0) + event.vikt;
      addSectionEvent(dataset, event, "pick");
    } else if (key === "trans") {
      const event = parseTransEvent(values, lookup);
      if (!event?.date) return;
      addDate(dataset, event.date);
      const totals = ensureNested(dataset.transTotals, event.date, event.user);
      totals.antal = (totals.antal || 0) + event.antal;
      addSectionEvent(dataset, event, "trans");
    } else if (key === "pallet") {
      const event = parsePalletEvent(values, lookup);
      if (!event?.date) return;
      addDate(dataset, event.date);
      addSectionEvent(dataset, event, "pallet");
    }
  });
  dataset.rawCounts[key] = rows;
}

async function getProductivityDataset() {
  const signature = localFilesSignature();
  if (productivityDataset && productivityDatasetSignature === signature) return productivityDataset;
  if (productivityDatasetPromise && productivityDatasetSignature === signature) return productivityDatasetPromise;

  productivityDatasetSignature = signature;
  productivityDatasetPromise = (async () => {
    const dataset = createDataset();
    for (const spec of VISIBLE_PRODUCTIVITY_SOURCE_SPECS) {
      await parseProductivityFile(dataset, spec.key);
    }
    productivityDataset = dataset;
    return dataset;
  })().finally(() => {
    productivityDatasetPromise = null;
  });
  return productivityDatasetPromise;
}

async function loadProductivityTargets() {
  if (productivityTargets) return productivityTargets;
  const response = await api.get("/api/productivity/targets");
  const map = {};
  for (const target of response.targets || []) {
    const key = `${String(target.company || "").toUpperCase()}||${String(target.process || "").toUpperCase()}`;
    map[key] = {
      description: target.description || "",
      rader: Number(target.rader) || 0,
      kollin: Number(target.kollin) || 0,
      pallar: Number(target.pallar) || 0,
    };
  }
  productivityTargets = {
    map,
    source: response.source || null,
    rows: (response.targets || []).length,
  };
  productivityTargetsSignature = response.source
    ? `${response.source.name}:${response.source.rows}:${response.source.modified_at}`
    : `${Date.now()}`;
  return productivityTargets;
}

function targetValue(targets, company, process, metric) {
  const target = targets.map[`${String(company).toUpperCase()}||${String(process).toUpperCase()}`];
  if (!target) return null;
  const value = Number(target[String(metric).toLowerCase()] || 0);
  return value || null;
}

function rowsFromBuckets({ spec, buckets, targets, pickTotals, transTotals }) {
  return Object.keys(buckets || {})
    .sort((a, b) => a.toUpperCase().localeCompare(b.toUpperCase(), "sv"))
    .map((user) => {
      const hourly = buckets[user] || {};
      const totalRows = Object.values(hourly).reduce((sum, value) => sum + Number(value || 0), 0);
      if (totalRows <= 0) return null;
      const workedHours = PRODUCTIVITY_HOURS.filter((hour) => Number(hourly[hour] || 0) > 0).length;
      const rowsPerHour = workedHours ? totalRows / workedHours : null;
      const target = targetValue(targets, spec.target_company, spec.process, spec.target_metric);
      const productivityPct = rowsPerHour != null && target ? rowsPerHour / target : null;

      let totalKolli = null;
      let totalWeight = null;
      if (spec.total_source === "pick") {
        totalKolli = pickTotals[user]?.kolli || 0;
        totalWeight = pickTotals[user]?.vikt || 0;
      } else if (spec.total_source === "trans") {
        totalKolli = transTotals[user]?.antal || 0;
      }

      return {
        user,
        hourly: Object.fromEntries(PRODUCTIVITY_HOURS
          .filter((hour) => hourly[hour])
          .map((hour) => [String(hour), hourly[hour]])),
        total_rows: totalRows,
        total_kolli: totalKolli,
        total_weight: totalWeight,
        worked_hours: workedHours,
        rows_per_hour: rowsPerHour,
        correction: 0,
        target_per_hour: target,
        target_metric: spec.target_metric,
        productivity_pct: productivityPct,
      };
    })
    .filter(Boolean);
}

function localSourcePayload(key, rows) {
  const spec = PRODUCTIVITY_SOURCE_BY_KEY[key];
  const file = productivityLocalFiles[key]?.file;
  return {
    key,
    label: spec.label,
    visible: spec.visible,
    name: file?.name || spec.label,
    rows,
    modified_at: file?.lastModified ? new Date(file.lastModified).toISOString() : null,
  };
}

function buildProductivityReportFromLocalDataset(dataset, targets, requestedDate) {
  const dates = Array.from(dataset.dates).sort();
  if (!dates.length) throw new Error("Produktivitetsunderlagen saknar datum");
  const selectedDate = requestedDate || dates[dates.length - 1];
  if (!dates.includes(selectedDate)) throw new Error(`Saknar produktivitetsdata f\u00f6r ${selectedDate}`);

  const sectionBucketsForDate = dataset.sectionBuckets[selectedDate] || {};
  const pickTotals = dataset.pickTotals[selectedDate] || {};
  const transTotals = dataset.transTotals[selectedDate] || {};
  const sectionsByGroup = {};
  let sectionCount = 0;
  let totalRows = 0;
  let totalWorkedHours = 0;
  const productivityValues = [];

  for (const spec of PRODUCTIVITY_SECTION_SPECS) {
    const rows = rowsFromBuckets({
      spec,
      buckets: sectionBucketsForDate[spec.id] || {},
      targets,
      pickTotals,
      transTotals,
    });
    const sectionTotalRows = rows.reduce((sum, row) => sum + row.total_rows, 0);
    const sectionWorkedHours = rows.reduce((sum, row) => sum + row.worked_hours, 0);
    const sectionTarget = targetValue(targets, spec.target_company, spec.process, spec.target_metric);
    const sectionRowsPerHour = sectionWorkedHours ? sectionTotalRows / sectionWorkedHours : null;
    const sectionProductivity = sectionRowsPerHour != null && sectionTarget
      ? sectionRowsPerHour / sectionTarget
      : null;
    if (sectionProductivity != null) productivityValues.push(sectionProductivity);
    totalRows += sectionTotalRows;
    totalWorkedHours += sectionWorkedHours;
    sectionCount += 1;

    if (!sectionsByGroup[spec.group_id]) sectionsByGroup[spec.group_id] = [];
    sectionsByGroup[spec.group_id].push({
      id: spec.id,
      title: spec.title,
      source: spec.source,
      process: spec.process,
      target_company: spec.target_company,
      target_metric: spec.target_metric,
      target_per_hour: sectionTarget,
      total_rows: sectionTotalRows,
      worked_hours: sectionWorkedHours,
      rows_per_hour: sectionRowsPerHour,
      productivity_pct: sectionProductivity,
      rows,
    });
  }

  const groups = PRODUCTIVITY_GROUPS.map((group) => ({
    id: group.id,
    title: PRODUCTIVITY_GROUP_TITLES[group.id],
    sections: sectionsByGroup[group.id] || [],
  }));
  const users = new Set(groups.flatMap((group) =>
    group.sections.flatMap((section) => section.rows.map((row) => row.user))
  ));

  return {
    generated_at: new Date().toISOString(),
    date: selectedDate,
    available_dates: dates,
    hours: PRODUCTIVITY_HOURS,
    sources: {
      pick: localSourcePayload("pick", dataset.rawCounts.pick),
      trans: localSourcePayload("trans", dataset.rawCounts.trans),
      pallet: localSourcePayload("pallet", dataset.rawCounts.pallet),
      kpi: {
        ...(targets.source || {}),
        key: "kpi",
        label: "KPI-M\u00e5l",
        visible: false,
        rows: targets.rows,
      },
    },
    summary: {
      sections: sectionCount,
      users: users.size,
      total_rows: totalRows,
      worked_hours: totalWorkedHours,
      rows_per_hour: totalWorkedHours ? totalRows / totalWorkedHours : null,
      average_productivity_pct: productivityValues.length
        ? productivityValues.reduce((sum, value) => sum + value, 0) / productivityValues.length
        : null,
    },
    groups,
  };
}

function renderSummary(report) {
  const summary = report.summary || {};
  const items = [
    ["Rader", formatNumber(summary.total_rows)],
    ["Timmar", formatNumber(summary.worked_hours)],
    ["Rader/tim", formatMetric(summary.rows_per_hour)],
    ["Snitt mot m\u00e5l", formatPercent(summary.average_productivity_pct)],
  ];

  document.getElementById("productivitySummary").innerHTML = items.map(([label, value]) => `
    <div class="productivity-kpi">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function renderSources(report) {
  const sources = Object.values(report.sources || {}).filter((source) => source.visible !== false);
  document.getElementById("productivitySources").innerHTML = sources.map((source) => `
    <div class="productivity-source">
      <span>${escapeHtml(source.label)}</span>
      <strong>${escapeHtml(source.name)}</strong>
      <small>${formatNumber(source.rows)} rader</small>
    </div>
  `).join("");
}

function renderFileStatus(status) {
  productivityFileStatus = status;
  const files = Object.values(status.files || {});
  const filled = files.filter((file) => file.uploaded).length;
  const required = files.filter((file) => file.required).length;
  document.getElementById("productivityUploadCount").textContent = `${filled}/${required} valda`;

  document.getElementById("productivityFileSlots").innerHTML = files.map((file) => `
    <div class="productivity-file-slot ${file.uploaded ? "is-uploaded" : ""}">
      <div class="productivity-file-main">
        <div class="productivity-file-label">${escapeHtml(file.label)}${file.required ? '<span class="req">*</span>' : ""}</div>
        <div class="productivity-file-name">
          ${file.uploaded ? escapeHtml(file.name) : '<span class="muted">Ingen fil vald</span>'}
        </div>
        ${file.uploaded ? `<div class="productivity-file-meta">${escapeHtml(file.size_label || "")}</div>` : ""}
      </div>
      <div class="productivity-file-actions">
        <span class="status-pill ${file.uploaded ? "ok" : "none"}">${file.uploaded ? "Vald" : "Ej fil"}</span>
        <button type="button" class="btn-sm productivity-slot-upload" data-file-key="${escapeHtml(file.key)}">V\u00e4lj</button>
        <button type="button" class="btn-sm danger productivity-slot-clear" data-file-key="${escapeHtml(file.key)}" ${file.uploaded ? "" : "disabled"}>&times;</button>
      </div>
    </div>
  `).join("");

  document.querySelectorAll(".productivity-slot-upload").forEach((button) => {
    button.addEventListener("click", () => document.getElementById("productivityUploadInput").click());
  });
  document.querySelectorAll(".productivity-slot-clear").forEach((button) => {
    button.addEventListener("click", () => clearProductivityFile(button.dataset.fileKey));
  });

  const uploadStatus = document.getElementById("productivityUploadStatus");
  uploadStatus.textContent = status.ready
    ? "Alla produktivitetsunderlag \u00e4r valda."
    : "Produktivitet r\u00e4knas n\u00e4r de markerade filerna \u00e4r valda.";
  if (!status.kpi_loaded) {
    uploadStatus.textContent = "Saknar permanent KPI-m\u00e5l i bakgrunden.";
  }
}

function clearReportContent() {
  productivityReport = null;
  document.getElementById("productivitySummary").innerHTML = "";
  document.getElementById("productivitySources").innerHTML = "";
  document.getElementById("productivityContent").innerHTML = "";
}

async function loadProductivityFileStatus() {
  const serverStatus = await api.get("/api/productivity/files");
  const status = buildLocalFileStatus(serverStatus);
  renderFileStatus(status);
  return status;
}

function setProductivityWaitingStatus(fileStatus) {
  clearReportContent();
  document.getElementById("productivityStatus").textContent = fileStatus?.ready
    ? "Underlagen \u00e4r valda. Ber\u00e4knar produktivitet..."
    : "Saknar produktivitetsunderlag.";
}

async function initializeProductivityPage() {
  const status = document.getElementById("productivityStatus");
  status.textContent = "Kontrollerar underlag...";
  try {
    const fileStatus = await loadProductivityFileStatus();
    if (fileStatus.ready) {
      await loadProductivity();
    } else {
      setProductivityWaitingStatus(fileStatus);
    }
  } catch (error) {
    status.textContent = error.message || "Kunde inte kontrollera underlag.";
    showToast(status.textContent, "error", 7000);
  }
}

function cacheReport(report) {
  if (report?.date) productivityReportCache.set(`${localFilesSignature()}|${productivityTargetsSignature}|${report.date}`, report);
  return report;
}

async function fetchProductivityReport(dateValue = "") {
  const cacheKey = `${localFilesSignature()}|${productivityTargetsSignature}|${dateValue || "latest"}`;
  if (dateValue && productivityReportCache.has(cacheKey)) {
    return productivityReportCache.get(cacheKey);
  }
  if (productivityReportRequests.has(cacheKey)) {
    return productivityReportRequests.get(cacheKey);
  }

  const request = (async () => {
    const [dataset, targets] = await Promise.all([
      getProductivityDataset(),
      loadProductivityTargets(),
    ]);
    return cacheReport(buildProductivityReportFromLocalDataset(dataset, targets, dateValue));
  })().finally(() => productivityReportRequests.delete(cacheKey));

  productivityReportRequests.set(cacheKey, request);
  return request;
}

function renderProductivityReport(report) {
  productivityReport = report;
  const dateInput = document.getElementById("productivityDate");
  if (productivityReport.date) dateInput.value = productivityReport.date;
  const dates = productivityReport.available_dates || [];
  if (dates.length) {
    dateInput.min = dates[0];
    dateInput.max = dates[dates.length - 1];
  }
  renderGroupFilter(productivityReport);
  renderSummary(productivityReport);
  renderSources(productivityReport);
  renderContent();
  document.getElementById("productivityStatus").textContent =
    `${productivityReport.date} \u00b7 uppdaterad ${formatTimestamp(productivityReport.generated_at)}`;
}

function prefetchAdjacentReports(report) {
  const dates = new Set(report?.available_dates || []);
  const selected = report?.date || "";
  [addDays(selected, -1), addDays(selected, 1)]
    .filter((dateValue) => dateValue && dates.has(dateValue))
    .forEach((dateValue) => {
      fetchProductivityReport(dateValue).catch(() => {});
    });
}

function renderGroupFilter(report) {
  const select = document.getElementById("productivityGroupFilter");
  const current = select.value || "all";
  select.innerHTML = '<option value="all">Alla</option>' + (report.groups || [])
    .map((group) => `<option value="${escapeHtml(group.id)}">${escapeHtml(group.title)}</option>`)
    .join("");
  select.value = Array.from(select.options).some((option) => option.value === current) ? current : "all";
}

function renderSection(section, hours, search) {
  const rows = filteredRows(section, search);
  const hourHeaders = hours.map((hour) => `<th>${String(hour).padStart(2, "0")}</th>`).join("");
  const emptyRow = `
    <tr>
      <td colspan="${hours.length + 9}" class="muted-cell">Inga rader</td>
    </tr>`;

  const body = rows.length ? rows.map((row) => {
    const hourCells = hours.map((hour) => {
      const value = row.hourly[String(hour)] || "";
      return `<td class="${value ? "has-work" : ""}">${value ? escapeHtml(value) : ""}</td>`;
    }).join("");
    return `
      <tr>
        <td class="name">${escapeHtml(row.user)}</td>
        ${hourCells}
        <td>${formatNumber(row.total_rows)}</td>
        <td>${row.total_kolli == null ? "-" : formatNumber(row.total_kolli)}</td>
        <td>${row.total_weight == null ? "-" : formatNumber(row.total_weight, 1)}</td>
        <td>${formatMetric(row.rows_per_hour)}</td>
        <td>${formatMetric(row.worked_hours)}</td>
        <td>${formatMetric(row.target_per_hour)}</td>
        <td class="productivity-pct${metricClass(row.productivity_pct)}">${formatPercent(row.productivity_pct)}</td>
      </tr>`;
  }).join("") : emptyRow;

  return `
    <section class="productivity-panel">
      <div class="productivity-panel-header">
        <div>
          <h3>${escapeHtml(section.title)}</h3>
          <span>${escapeHtml(section.target_company)} \u00b7 ${escapeHtml(section.process)}</span>
        </div>
        <div class="productivity-panel-score${metricClass(section.productivity_pct)}">
          ${formatPercent(section.productivity_pct)}
        </div>
      </div>
      <div class="table-wrap productivity-table-wrap">
        <table class="productivity-table">
          <thead>
            <tr>
              <th class="name">Anv\u00e4ndare</th>
              ${hourHeaders}
              <th>Rader</th>
              <th>Kolli</th>
              <th>Vikt</th>
              <th>Rad/tim</th>
              <th>Timmar</th>
              <th>M\u00e5l</th>
              <th>%</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </section>`;
}

function renderContent() {
  if (!productivityReport) return;
  const content = document.getElementById("productivityContent");
  const groupFilter = activeGroupFilter();
  const search = activeSearch();
  const hours = productivityReport.hours || [];

  const groups = (productivityReport.groups || [])
    .filter((group) => groupFilter === "all" || group.id === groupFilter)
    .map((group) => ({
      ...group,
      sections: group.sections.filter((section) => sectionMatches(section, search)),
    }))
    .filter((group) => group.sections.length);

  if (!groups.length) {
    content.innerHTML = '<div class="empty-state">Ingen produktivitet matchade filtret.</div>';
    return;
  }

  content.innerHTML = groups.map((group) => `
    <section class="productivity-group">
      <h2>${escapeHtml(group.title)}</h2>
      <div class="productivity-section-list">
        ${group.sections.map((section) => renderSection(section, hours, search)).join("")}
      </div>
    </section>
  `).join("");
}

async function loadProductivity() {
  const status = document.getElementById("productivityStatus");
  const dateInput = document.getElementById("productivityDate");
  status.textContent = "Kontrollerar underlag...";
  try {
    const fileStatus = await loadProductivityFileStatus();
    if (!fileStatus.ready) {
      clearReportContent();
      status.textContent = "Saknar produktivitetsunderlag.";
      return;
    }
    status.textContent = "Ber\u00e4knar produktivitet lokalt...";
    const report = await fetchProductivityReport(dateInput.value);
    renderProductivityReport(report);
    prefetchAdjacentReports(report);
  } catch (error) {
    productivityReport = null;
    document.getElementById("productivitySummary").innerHTML = "";
    document.getElementById("productivitySources").innerHTML = "";
    document.getElementById("productivityContent").innerHTML = "";
    status.textContent = error.message || "Kunde inte l\u00e4sa produktivitet.";
    showToast(status.textContent, "error", 7000);
  }
}

async function uploadPermanentKpiFile(file) {
  const result = await api.postFile(
    `/api/productivity/files/raw?filename=${encodeURIComponent(file.name)}`,
    file,
  );
  productivityTargets = null;
  productivityTargetsSignature = "";
  clearProductivityReportCache();
  return result;
}

async function uploadProductivityFiles(files) {
  const incoming = Array.from(files || []);
  if (!incoming.length) return;

  const uploadStatus = document.getElementById("productivityUploadStatus");
  uploadStatus.textContent = "L\u00e4ser filval...";
  try {
    const saved = [];
    const unknown = [];
    let hiddenSaved = 0;
    let localChanged = false;

    for (const file of incoming) {
      const sample = await readFileSample(file);
      const fileType = classifyProductivityLocalFile(file, sample);
      if (!fileType) {
        unknown.push(file.name || "ok\u00e4nd fil");
        continue;
      }
      if (fileType === "kpi") {
        uploadStatus.textContent = `Uppdaterar KPI-m\u00e5l: ${file.name}`;
        const result = await uploadPermanentKpiFile(file);
        hiddenSaved += (result.saved || []).length;
        unknown.push(...(result.unknown || []));
        continue;
      }

      productivityLocalFiles[fileType] = { file };
      saved.push({ key: fileType, name: file.name, visible: true });
      localChanged = true;
    }

    if (localChanged) resetLocalProductivityDataset();
    const latestStatus = await loadProductivityFileStatus();
    const parts = [];
    if (saved.length) parts.push(`${saved.length} fil(er) valda lokalt`);
    if (hiddenSaved) parts.push("KPI-m\u00e5l uppdaterat i bakgrunden");
    if (unknown.length) parts.push(`Ok\u00e4nd filtyp: ${unknown.join(", ")}`);
    const message = parts.join(". ") || "Ingen fil uppdaterades.";
    uploadStatus.textContent = message;

    if (latestStatus.ready) {
      await loadProductivity();
    } else {
      setProductivityWaitingStatus(latestStatus);
      uploadStatus.textContent = message;
    }
  } catch (error) {
    uploadStatus.textContent = error.message || "Kunde inte l\u00e4sa filer.";
    showToast(uploadStatus.textContent, "error", 7000);
  }
}

async function clearProductivityFile(fileKey) {
  if (!fileKey) return;
  if (productivityLocalFiles[fileKey]) {
    delete productivityLocalFiles[fileKey];
    resetLocalProductivityDataset();
  }
  try {
    const status = await loadProductivityFileStatus();
    clearReportContent();
    document.getElementById("productivityStatus").textContent = status.ready
      ? "Underlagen \u00e4r valda. Ber\u00e4knar produktivitet..."
      : "Saknar produktivitetsunderlag.";
    if (status.ready) await loadProductivity();
  } catch (error) {
    showToast(error.message || "Kunde inte rensa filen.", "error", 7000);
  }
}

function setupUploadDropzone() {
  const panel = document.getElementById("productivityUploadPanel");
  let dragDepth = 0;

  panel.addEventListener("dragenter", (event) => {
    if (!Array.from(event.dataTransfer?.types || []).includes("Files")) return;
    event.preventDefault();
    dragDepth += 1;
    panel.classList.add("is-dragging");
  });
  panel.addEventListener("dragover", (event) => {
    if (!Array.from(event.dataTransfer?.types || []).includes("Files")) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  });
  panel.addEventListener("dragleave", () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) panel.classList.remove("is-dragging");
  });
  panel.addEventListener("drop", (event) => {
    if (!Array.from(event.dataTransfer?.types || []).includes("Files")) return;
    event.preventDefault();
    dragDepth = 0;
    panel.classList.remove("is-dragging");
    uploadProductivityFiles(event.dataTransfer.files);
  });
}

(async () => {
  const user = await initPage("productivity", { requireSuperUser: true });
  if (!user) return;

  document.getElementById("productivityUploadBtn").addEventListener("click", () => {
    document.getElementById("productivityUploadInput").click();
  });
  document.getElementById("productivityUploadInput").addEventListener("change", (event) => {
    uploadProductivityFiles(event.target.files);
    event.target.value = "";
  });
  document.getElementById("productivityDate").addEventListener("change", loadProductivity);
  document.getElementById("productivityGroupFilter").addEventListener("change", renderContent);
  document.getElementById("productivitySearch").addEventListener("input", renderContent);
  setupUploadDropzone();
  await initializeProductivityPage();
})();

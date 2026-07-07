// @ts-check
// Utdelad ur allocation/state.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter state.js via <script>-tagg.

const ALLOCATION_CLUSTER_DEFAULT_TIMES = { asn: "11:00", arrive: "12:00", depart: "14:00" };
const ALLOCATION_CLUSTER_HUES = [350, 265, 150, 40, 210, 320, 175, 285, 25, 130, 195, 300];
const ALLOCATION_CARRIER_CLUSTER_DEFAULTS = new Map();

function allocationRegisterCarrierClusterDefaults(carrierNums, defaults) {
  carrierNums.forEach((carrierNum) => {
    ALLOCATION_CARRIER_CLUSTER_DEFAULTS.set(String(carrierNum), { ...defaults });
  });
}

allocationRegisterCarrierClusterDefaults([78, 79], { clusterGroup: "Schenker", assignmentOrder: "0", startSeq: "205", endSeq: "356", asn: "11:00", arrive: "12:00", depart: "14:00", color: "#94a3b8" });
allocationRegisterCarrierClusterDefaults([76, 77], { clusterGroup: "Schenker", assignmentOrder: "1", startSeq: "205", endSeq: "356", asn: "11:00", arrive: "12:00", depart: "14:00", color: "#60a5fa" });
allocationRegisterCarrierClusterDefaults([93, 94], { clusterGroup: "Schenker", assignmentOrder: "2", startSeq: "205", endSeq: "356", asn: "11:00", arrive: "12:00", depart: "14:00", color: "#94a3b8" });
allocationRegisterCarrierClusterDefaults([74, 75], { clusterGroup: "Schenker", assignmentOrder: "3", startSeq: "205", endSeq: "356", asn: "10:00", arrive: "11:00", depart: "13:00", color: "#fb923c" });
allocationRegisterCarrierClusterDefaults([82, 83], { clusterGroup: "Schenker", assignmentOrder: "4", startSeq: "205", endSeq: "356", asn: "11:00", arrive: "12:00", depart: "14:00", color: "#34d399" });
allocationRegisterCarrierClusterDefaults([80, 81], { clusterGroup: "Schenker", assignmentOrder: "5", startSeq: "205", endSeq: "356", asn: "13:00", arrive: "14:00", depart: "16:00", color: "#2dd4bf" });
allocationRegisterCarrierClusterDefaults([41], { assignmentOrder: "6", startSeq: "356", endSeq: "205", asn: "18:00", arrive: "19:00", depart: "23:00", color: "#fcd34d" });
allocationRegisterCarrierClusterDefaults([61, 63, 69], { assignmentOrder: "7", startSeq: "356", endSeq: "205", asn: "17:00", arrive: "19:00", depart: "23:00", color: "#86efac" });
allocationRegisterCarrierClusterDefaults([85], { assignmentOrder: "8", startSeq: "356", endSeq: "205", asn: "16:00", arrive: "19:00", depart: "23:00", color: "#f9a8d4" });
allocationRegisterCarrierClusterDefaults([42, 43], { clusterGroup: "Freja", assignmentOrder: "9", startSeq: "600", endSeq: "652", asn: "09:00", arrive: "11:00", depart: "13:00", color: "#c4b5fd" });
allocationRegisterCarrierClusterDefaults([39, 40], { clusterGroup: "Freja", assignmentOrder: "10", startSeq: "600", endSeq: "652", asn: "09:00", arrive: "11:00", depart: "13:00", color: "#c4b5fd" });
allocationRegisterCarrierClusterDefaults([44, 45], { clusterGroup: "Freja", assignmentOrder: "11", startSeq: "600", endSeq: "652", asn: "09:00", arrive: "11:00", depart: "13:00", color: "#c4b5fd" });
allocationRegisterCarrierClusterDefaults([48, 49], { clusterGroup: "Freja", assignmentOrder: "12", startSeq: "600", endSeq: "652", asn: "09:00", arrive: "11:00", depart: "13:00", color: "#c4b5fd" });
allocationRegisterCarrierClusterDefaults([46, 47], { clusterGroup: "Freja", assignmentOrder: "13", startSeq: "600", endSeq: "652", asn: "09:00", arrive: "11:00", depart: "13:00", color: "#c4b5fd" });
allocationRegisterCarrierClusterDefaults([51], { assignmentOrder: "14", startSeq: "652", endSeq: "600", asn: "13:00", arrive: "14:00", depart: "16:00", color: "#fdba74" });
allocationRegisterCarrierClusterDefaults([53], { clusterGroup: "Sandahls Sundsvall", assignmentOrder: "15", startSeq: "205", endSeq: "652", asn: "13:00", arrive: "14:00", depart: "16:00", color: "#f472b6" });
allocationRegisterCarrierClusterDefaults([55], { clusterGroup: "Sandahls Sundsvall", assignmentOrder: "16", startSeq: "205", endSeq: "652", asn: "13:00", arrive: "14:00", depart: "16:00", color: "#f472b6" });
allocationRegisterCarrierClusterDefaults([57], { clusterGroup: "Sandahls Norrland", assignmentOrder: "17", startSeq: "600", endSeq: "652", asn: "15:00", arrive: "16:00", depart: "17:00", color: "#fb7185" });
allocationRegisterCarrierClusterDefaults([59], { clusterGroup: "Sandahls Norrland", assignmentOrder: "18", startSeq: "600", endSeq: "652", asn: "15:00", arrive: "16:00", depart: "17:00", color: "#fda4af" });
allocationRegisterCarrierClusterDefaults([97], { assignmentOrder: "19", startSeq: "205", endSeq: "652", asn: "13:00", arrive: "14:00", depart: "16:00", color: "#e879f9" });
allocationRegisterCarrierClusterDefaults([65, 67], { assignmentOrder: "20", startSeq: "205", endSeq: "652", asn: "10:00", arrive: "11:00", depart: "13:00", color: "#4ade80" });
allocationRegisterCarrierClusterDefaults([71, 73], { assignmentOrder: "21", startSeq: "205", endSeq: "652", asn: "11:00", arrive: "12:00", depart: "14:00", color: "#fbbf24" });

function allocationDefaultCarrierClusters() {
  const rows = [...ALLOCATION_CARRIER_CLUSTER_DEFAULTS.entries()].map(([carrierNum, defaults], index) => ({
    id: `default-${carrierNum}`,
    carrierNum,
    description: "",
    alias: "",
    clusterGroup: defaults.clusterGroup || "",
    assignmentOrder: defaults.assignmentOrder || String(index + 1),
    startSeq: defaults.startSeq || "",
    endSeq: defaults.endSeq || "",
    asn: defaults.asn || ALLOCATION_CLUSTER_DEFAULT_TIMES.asn,
    arrive: defaults.arrive || ALLOCATION_CLUSTER_DEFAULT_TIMES.arrive,
    depart: defaults.depart || ALLOCATION_CLUSTER_DEFAULT_TIMES.depart,
    color: defaults.color || "",
  }));
  return normalizeAllocationCarrierClusters({
    version: 1,
    source: { name: "Standardtransportorer", rowCount: rows.length },
    rows,
  });
}

function allocationCarrierClusterText(value) {
  const text = String(value ?? "").trim();
  return ["nan", "nat", "none", "null"].includes(text.toLowerCase()) ? "" : text;
}

function allocationCarrierClusterIdentifier(value) {
  const text = allocationCarrierClusterText(value);
  const match = text.match(/^(\d+)\.0+$/);
  return match ? match[1] : text;
}

function allocationHslToHex(h, s, l) {
  const sat = s / 100;
  const light = l / 100;
  const k = (n) => (n + h / 30) % 12;
  const a = sat * Math.min(light, 1 - light);
  const f = (n) => {
    const color = light - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
    return Math.round(255 * color).toString(16).padStart(2, "0");
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

// Bygg transportör -> färg där ett kluster delar basnyans och varje transportör i
// klustret får en egen ljushet. Manuella färger i `overrides` vinner över auto.
function allocationClusterColorMap(entries, overrides) {
  const overrideMap = overrides instanceof Map ? overrides : new Map();
  const clusterCarriers = new Map();
  const clusterOrder = [];
  (entries || []).forEach((entry) => {
    const carrierKey = String(entry.carrier || "Okänd");
    const clusterKey = String(entry.cluster || "").trim() || `__solo__:${carrierKey}`;
    if (!clusterCarriers.has(clusterKey)) {
      clusterCarriers.set(clusterKey, []);
      clusterOrder.push(clusterKey);
    }
    const carriers = clusterCarriers.get(clusterKey);
    if (!carriers.includes(carrierKey)) carriers.push(carrierKey);
  });
  const colorMap = new Map();
  clusterOrder.forEach((clusterKey, clusterIndex) => {
    const hue = ALLOCATION_CLUSTER_HUES[clusterIndex % ALLOCATION_CLUSTER_HUES.length];
    const carriers = clusterCarriers.get(clusterKey);
    const span = carriers.length;
    carriers.forEach((carrierKey, i) => {
      const light = span <= 1 ? 58 : 46 + Math.round((i / (span - 1)) * 26);
      colorMap.set(carrierKey, allocationHslToHex(hue, 65, light));
    });
  });
  overrideMap.forEach((color, carrier) => {
    const key = String(carrier || "");
    if (key && color) colorMap.set(key, color);
  });
  return colorMap;
}

function allocationCarrierClusterNumber(value) {
  const text = allocationCarrierClusterText(value).replace(",", ".");
  if (!text) return "";
  const parsed = Number.parseInt(text, 10);
  return Number.isFinite(parsed) ? String(parsed) : "";
}

function allocationCarrierClusterDefaults(carrierNum, alias, description) {
  for (const value of [carrierNum, alias, description]) {
    const key = allocationCarrierClusterText(value);
    if (ALLOCATION_CARRIER_CLUSTER_DEFAULTS.has(key)) {
      return ALLOCATION_CARRIER_CLUSTER_DEFAULTS.get(key);
    }
  }
  return {};
}

function allocationCarrierClusterKey(value) {
  return allocationCarrierClusterText(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

function normalizeAllocationCarrierClusters(payload) {
  if (!payload) return null;
  const rows = Array.isArray(payload)
    ? payload
    : Array.isArray(payload.rows)
      ? payload.rows
      : [];
  const normalizedRows = rows.map((row, index) => {
    const carrierNum = allocationCarrierClusterIdentifier(row.carrierNum ?? row.carrier_num ?? row.agencyNum ?? row.agency_num ?? row.AGENCY_NUM);
    const description = allocationCarrierClusterText(row.description ?? row.agencyDesc ?? row.agency_desc ?? row.AGENCY_DESC ?? row.carrier ?? row.transportor);
    const alias = allocationCarrierClusterText(row.alias ?? row.agencyAlias ?? row.agency_alias ?? row.AGENCY_ALIAS);
    const label = alias || description || carrierNum;
    if (!label) return null;
    const asn = allocationCarrierClusterText(row.asn ?? row.agency_asn ?? row.agencyAsn ?? row.ASN);
    const arrive = allocationCarrierClusterText(row.arrive ?? row.agency_arrive ?? row.agencyArrive ?? row.ARRIVE);
    const depart = allocationCarrierClusterText(row.depart ?? row.agency_depart ?? row.agencyDepart ?? row.DEPART);
    const defaults = allocationCarrierClusterDefaults(carrierNum, alias, description);
    return {
      id: allocationCarrierClusterText(row.id) || carrierNum || `row-${index + 1}`,
      carrierNum,
      description,
      alias,
      clusterGroup: allocationCarrierClusterText(row.clusterGroup ?? row.cluster_group ?? row.CLUSTER_GROUP ?? row.cluster) || defaults.clusterGroup || "",
      assignmentOrder: allocationCarrierClusterNumber(row.assignmentOrder ?? row.assignment_order ?? row.ASSIGNMENT_ORDER ?? row.order) || defaults.assignmentOrder || "",
      startSeq: allocationCarrierClusterNumber(row.startSeq ?? row.start_seq ?? row.START_SEQ ?? row.from ?? row.utlFrom) || defaults.startSeq || "",
      endSeq: allocationCarrierClusterNumber(row.endSeq ?? row.end_seq ?? row.END_SEQ ?? row.to ?? row.utlTo) || defaults.endSeq || "",
      asn: asn || defaults.asn || ALLOCATION_CLUSTER_DEFAULT_TIMES.asn,
      arrive: arrive || defaults.arrive || ALLOCATION_CLUSTER_DEFAULT_TIMES.arrive,
      depart: depart || defaults.depart || ALLOCATION_CLUSTER_DEFAULT_TIMES.depart,
      color: allocationCarrierClusterText(row.color ?? row.colour) || defaults.color || "",
    };
  }).filter(Boolean);
  normalizedRows.sort((a, b) => {
    const orderA = a.assignmentOrder === "" ? 10000 : Number(a.assignmentOrder);
    const orderB = b.assignmentOrder === "" ? 10000 : Number(b.assignmentOrder);
    return orderA - orderB || String(a.alias || a.description || a.carrierNum).localeCompare(String(b.alias || b.description || b.carrierNum), "sv");
  });
  const source = payload && !Array.isArray(payload) && typeof payload.source === "object"
    ? payload.source
    : { name: "Transportörer", rowCount: normalizedRows.length };
  return { version: 1, source, rows: normalizedRows };
}

function allocationCarrierClustersFromForecastTable(data) {
  if (data?.flow_id !== "forecast") return null;
  const tableEntry = (data.tables || []).find((entry) => entry.key === "forecast") || (data.tables || [])[0];
  const table = tableEntry?.table || {};
  const columns = Array.isArray(table.columns) ? table.columns : [];
  const carrierIndex = columns.findIndex((column) => {
    const key = allocationCarrierClusterKey(column);
    return key === "transportor" || key === "carrier" || key === "agency";
  });
  if (carrierIndex < 0 || !Array.isArray(table.rows)) return null;
  const seen = new Set();
  const rows = [];
  table.rows.forEach((row) => {
    const carrier = allocationCarrierClusterText(Array.isArray(row) ? row[carrierIndex] : "");
    const key = allocationCarrierClusterKey(carrier);
    if (!key || seen.has(key)) return;
    seen.add(key);
    const order = rows.length + 1;
    rows.push({
      id: `forecast-${order}`,
      carrierNum: carrier,
      description: carrier,
      alias: carrier,
      clusterGroup: "",
      assignmentOrder: "",
      startSeq: "",
      endSeq: "",
    });
  });
  return normalizeAllocationCarrierClusters({
    version: 1,
    source: { name: "Forecast", rowCount: rows.length, generated: true },
    rows,
  });
}

function allocationCarrierClustersForResult(data = allocationState.result?.data) {
  const fromData = normalizeAllocationCarrierClusters(data?.carrier_clusters);
  if (fromData?.rows?.length) return fromData;
  const fromForecast = allocationCarrierClustersFromForecastTable(data);
  if (fromForecast?.rows?.length) return fromForecast;
  return normalizeAllocationCarrierClusters(allocationState.carrierClusters);
}

function allocationHasCarrierClusters(data = allocationState.result?.data) {
  return Boolean(allocationCarrierClustersForResult(data)?.rows?.length);
}

// Utdelad ur allocation/results.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter results.js via <script>-tagg.

const ALLOCATION_MAP_NS = "http://www.w3.org/2000/svg";

function allocationMapNumber(value, fallback = 0) {
  const parsed = Number.parseFloat(String(value ?? "").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function allocationMapRound(value) {
  return Math.round(allocationMapNumber(value) * 100) / 100;
}

function allocationMapClamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function allocationMapShortLocation(value) {
  return String(value || "").trim().replace(/^UTL/i, "") || String(value || "").trim();
}

function allocationMapEstimatedTextWidth(text, fontSize) {
  return String(text || "").length * fontSize * 0.56;
}

function allocationMapSafeSvgId(value) {
  return String(value || "").replace(/[^a-zA-Z0-9_-]+/g, "-") || "item";
}

function allocationMapHexToRgb(value) {
  const raw = String(value || "").trim();
  const short = raw.match(/^#([0-9a-f]{3})$/i);
  const long = raw.match(/^#([0-9a-f]{6})$/i);
  const hex = short
    ? short[1].split("").map((part) => `${part}${part}`).join("")
    : long?.[1];
  if (!hex) return null;
  return {
    r: Number.parseInt(hex.slice(0, 2), 16),
    g: Number.parseInt(hex.slice(2, 4), 16),
    b: Number.parseInt(hex.slice(4, 6), 16),
  };
}

function allocationMapMixHexColor(color, target = "#ffffff", amount = 0.5) {
  const sourceRgb = allocationMapHexToRgb(color);
  const targetRgb = allocationMapHexToRgb(target);
  if (!sourceRgb || !targetRgb) return color || target;
  const ratio = allocationMapClamp(amount, 0, 1);
  const channel = (name) => Math.round(sourceRgb[name] * (1 - ratio) + targetRgb[name] * ratio)
    .toString(16)
    .padStart(2, "0");
  return `#${channel("r")}${channel("g")}${channel("b")}`;
}

function allocationMapLabelLines(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return [""];
  const words = text.split(" ");
  if (words.length < 2) return [text];
  let best = [text];
  let bestScore = Number.POSITIVE_INFINITY;
  for (let index = 1; index < words.length; index += 1) {
    const left = words.slice(0, index).join(" ");
    const right = words.slice(index).join(" ");
    const score = Math.max(left.length, right.length) * 2 + Math.abs(left.length - right.length);
    if (score < bestScore) {
      best = [left, right];
      bestScore = score;
    }
  }
  return best;
}

function allocationMapLocationSortValue(value) {
  const match = String(value || "").match(/^UTL(\d+)(.*)$/i);
  if (!match) return [Number.MAX_SAFE_INTEGER, String(value || "")];
  return [Number.parseInt(match[1], 10), match[2] || ""];
}

function allocationMapCompareLocation(a, b) {
  const left = allocationMapLocationSortValue(a);
  const right = allocationMapLocationSortValue(b);
  return left[0] - right[0] || left[1].localeCompare(right[1], "sv");
}

function allocationMapTsvCell(value) {
  return String(value ?? "").replace(/\t/g, " ").replace(/\r?\n/g, " ").trim();
}

function allocationDownloadText(filename, text, type = "text/csv;charset=utf-8") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function initializeAllocationResultMaps(root) {
  const maps = allocationResultMaps(allocationState.result?.data);
  root.querySelectorAll("[data-allocation-map]").forEach((host) => {
    const index = Number.parseInt(host.dataset.mapIndex || "0", 10);
    setupAllocationWarehouseMap(host, maps[index]);
  });
}

function setupAllocationWarehouseMap(host, entry) {
  const svg = host.querySelector("[data-map-svg]");
  const canvas = host.querySelector("[data-map-canvas]");
  const grid = host.querySelector("[data-map-grid]");
  const rotateGroup = host.querySelector("[data-map-rotate-group]");
  const metrics = host.querySelector("[data-map-metrics]");
  const detail = host.querySelector("[data-map-detail]");
  const overview = host.querySelector("[data-map-overview]");
  const search = host.querySelector("[data-map-search]");
  const missingToggle = host.querySelector("[data-map-missing]");
  const missingPanel = host.querySelector("[data-map-missing-panel]");
  if (!svg || !canvas || !entry) return;
  const defs = svg.querySelector("defs");

  const locations = (Array.isArray(entry.locations) ? entry.locations : [])
    .map((loc) => ({
      location: String(loc.location || "").trim().toUpperCase(),
      x: allocationMapNumber(loc.x),
      y: allocationMapNumber(loc.y),
      w: allocationMapNumber(loc.w, 1),
      h: allocationMapNumber(loc.h, 1),
      maxPall: allocationMapRound(loc.maxPall),
      loadDirection: allocationNormalizeMapLoadDirection(
        loc.loadDirection ?? loc.load_direction ?? loc.loadingDirection ?? loc.direction,
        loc,
      ),
    }))
    .filter((loc) => loc.location);
  locations.sort((a, b) => allocationMapCompareLocation(a.location, b.location));
  const locationByName = new Map(locations.map((loc) => [loc.location, loc]));
  const assignments = (Array.isArray(entry.assignments) ? entry.assignments : [])
    .map((assignment, index) => ({
      id: String(assignment.id || `assignment-${index}`),
      shipment: String(assignment.shipment || ""),
      carrier: String(assignment.carrier || "Okänd"),
      cluster: String(assignment.cluster || ""),
      customer: String(assignment.customer || ""),
      customerNum: String(assignment.customerNum || ""),
      company: String(assignment.company || ""),
      location: String(assignment.location || "").trim().toUpperCase(),
      placedPallets: allocationMapRound(assignment.placedPallets),
      shipmentPallets: allocationMapRound(assignment.shipmentPallets),
      maxPall: allocationMapRound(assignment.maxPall),
      unusedCapacity: allocationMapRound(assignment.unusedCapacity),
      placementNo: allocationMapNumber(assignment.placementNo, index + 1),
      orderNumbers: Array.isArray(assignment.orderNumbers) ? assignment.orderNumbers.map((value) => String(value)) : [],
      orderCompanies: assignment.orderCompanies && typeof assignment.orderCompanies === "object"
        ? Object.fromEntries(Object.entries(assignment.orderCompanies).map(([key, value]) => [String(key), String(value || "").trim().toUpperCase()]))
        : {},
    }))
    .filter((assignment) => assignment.location);
  const assignmentByLocation = new Map();
  assignments.forEach((assignment) => {
    assignmentByLocation.set(assignment.location, assignment);
  });
  const mapBounds = entry.bounds && Object.keys(entry.bounds).length
    ? entry.bounds
    : locations.length
      ? {
          minX: Math.min(...locations.map((loc) => loc.x)),
          minY: Math.min(...locations.map((loc) => loc.y)),
          maxX: Math.max(...locations.map((loc) => loc.x + loc.w)),
          maxY: Math.max(...locations.map((loc) => loc.y + loc.h)),
        }
      : { minX: 0, minY: 0, maxX: 1, maxY: 1 };
  const mapMinX = allocationMapNumber(mapBounds.minX);
  const mapMinY = allocationMapNumber(mapBounds.minY);
  const mapMaxX = allocationMapNumber(mapBounds.maxX, mapMinX + 1);
  const mapMaxY = allocationMapNumber(mapBounds.maxY, mapMinY + 1);
  const mapWidth = Math.max(1, mapMaxX - mapMinX);
  const mapHeight = Math.max(1, mapMaxY - mapMinY);
  const fitPadding = 70;

  const clusterColorOverrides = new Map(
    (allocationState.carrierClusters?.rows || [])
      .map((row) => [String(row.alias || row.description || row.carrierNum || ""), row.color])
      .filter(([carrier, color]) => carrier && color),
  );
  const colorMap = allocationClusterColorMap(
    assignments.map((assignment) => ({ carrier: assignment.carrier, cluster: assignment.cluster })),
    clusterColorOverrides,
  );

  const state = {
    transform: { x: 0, y: 0, scale: 1 },
    minScale: 0.05,
    rotation: 0,
    selectedLocation: "",
    clipboard: null,
    history: [],
    pan: null,
    drag: null,
    locElements: new Map(),
  };

  function locationCenter(loc) {
    return { x: loc.x + loc.w / 2, y: loc.y + loc.h / 2 };
  }

  function fittedMapScale(rect) {
    const width = Math.max(1, rect.width - fitPadding * 2);
    const height = Math.max(1, rect.height - fitPadding * 2);
    return Math.max(0.05, Math.min(3, Math.min(width / mapWidth, height / mapHeight)));
  }

  function centerTransformForScale(rect, scale) {
    return {
      x: (rect.width - mapWidth * scale) / 2 - mapMinX * scale,
      y: (rect.height - mapHeight * scale) / 2 - mapMinY * scale,
      scale,
    };
  }

  function clampAxis(value, rectSize, contentMin, contentMax, scale) {
    const scaledSize = (contentMax - contentMin) * scale;
    if (scaledSize + fitPadding * 2 <= rectSize) {
      return (rectSize - scaledSize) / 2 - contentMin * scale;
    }
    const minValue = rectSize - fitPadding - contentMax * scale;
    const maxValue = fitPadding - contentMin * scale;
    return allocationMapClamp(value, minValue, maxValue);
  }

  function clampTransform() {
    const rect = svg.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    state.minScale = fittedMapScale(rect);
    state.transform.scale = allocationMapClamp(state.transform.scale || state.minScale, state.minScale, 5);
    state.transform.x = clampAxis(state.transform.x, rect.width, mapMinX, mapMaxX, state.transform.scale);
    state.transform.y = clampAxis(state.transform.y, rect.height, mapMinY, mapMaxY, state.transform.scale);
  }

  function applyTransform() {
    clampTransform();
    const transform = `translate(${state.transform.x}, ${state.transform.y}) scale(${state.transform.scale})`;
    canvas.setAttribute("transform", transform);
    grid?.setAttribute("patternTransform", transform);
  }

  function applyRotation() {
    const rect = svg.getBoundingClientRect();
    rotateGroup.style.transformOrigin = `${rect.width / 2}px ${rect.height / 2}px`;
    rotateGroup.style.transform = state.rotation ? `rotate(${state.rotation}deg)` : "";
  }

  function fitMap() {
    if (!locations.length) return;
    const rect = svg.getBoundingClientRect();
    if (!rect.width || !rect.height) {
      requestAnimationFrame(fitMap);
      return;
    }
    state.minScale = fittedMapScale(rect);
    state.transform = centerTransformForScale(rect, state.minScale);
    applyTransform();
  }

  function updateAssignmentCapacity(assignment) {
    const loc = locationByName.get(assignment.location);
    if (!loc) return;
    assignment.maxPall = loc.maxPall || assignment.maxPall || 0;
    assignment.unusedCapacity = allocationMapRound(assignment.maxPall - assignment.placedPallets);
  }

  function mapMutationSnapshot() {
    return assignments.map((assignment) => ({
      id: assignment.id,
      location: assignment.location,
      maxPall: assignment.maxPall,
      unusedCapacity: assignment.unusedCapacity,
    }));
  }

  function rememberMapMutation() {
    state.history.push(mapMutationSnapshot());
    if (state.history.length > 50) state.history.shift();
  }

  function restoreMapMutation(snapshot) {
    const byId = new Map((snapshot || []).map((assignment) => [assignment.id, assignment]));
    assignmentByLocation.clear();
    assignments.forEach((assignment) => {
      const previous = byId.get(assignment.id);
      if (!previous) return;
      assignment.location = previous.location;
      assignment.maxPall = previous.maxPall;
      assignment.unusedCapacity = previous.unusedCapacity;
      if (assignment.location && locationByName.has(assignment.location)) {
        updateAssignmentCapacity(assignment);
        assignmentByLocation.set(assignment.location, assignment);
      }
    });
    refreshMap();
  }

  function assignmentById(id) {
    return assignments.find((assignment) => assignment.id === id) || null;
  }

  function assignmentLabel(assignment) {
    return assignment?.customer || assignment?.shipment || assignment?.carrier || assignment?.cluster || "placering";
  }

  function setMapText(elements, loc, assignment) {
    const center = locationCenter(loc);
    const horizontal = loc.w >= loc.h;
    const shortSide = Math.max(1, Math.min(loc.w, loc.h));
    const edgeBand = allocationMapClamp(shortSide * 0.55, 22, 44);
    const loadSide = allocationMapLoadOriginSide(loc.loadDirection, loc);
    const contentRect = { x: loc.x, y: loc.y, w: loc.w, h: loc.h };
    if (assignment) {
      if (loadSide === "left") {
        contentRect.x += edgeBand;
        contentRect.w = Math.max(1, contentRect.w - edgeBand);
      } else if (loadSide === "right") {
        contentRect.w = Math.max(1, contentRect.w - edgeBand);
      } else if (loadSide === "top") {
        contentRect.y += edgeBand;
        contentRect.h = Math.max(1, contentRect.h - edgeBand);
      } else if (loadSide === "bottom") {
        contentRect.h = Math.max(1, contentRect.h - edgeBand);
      }
    }
    const shortLocation = allocationMapShortLocation(loc.location);
    const label = assignment
      ? (assignment.customer || assignment.carrier || assignment.cluster || assignment.shipment)
      : shortLocation;
    const labelLines = assignment ? allocationMapLabelLines(label) : [label];
    const contentX = contentRect.x + contentRect.w / 2;
    const contentY = contentRect.y + contentRect.h / 2;
    const contentWidth = Math.max(18, horizontal ? contentRect.w - 10 : contentRect.h - 10);
    const contentHeight = Math.max(18, horizontal ? contentRect.h - 10 : contentRect.w - 10);
    const mainFont = allocationMapClamp(contentHeight / (labelLines.length > 1 ? 2.45 : 1.85), 13, 22);
    const lineHeight = mainFont * 1.1;
    const firstLineY = contentY - ((labelLines.length - 1) * lineHeight) / 2;

    elements.edgeText.textContent = shortLocation;
    elements.edgeText.style.display = assignment ? "" : "none";
    elements.edgeText.style.fontSize = `${allocationMapClamp(shortSide * 0.34, 11, 22)}px`;
    elements.edgeText.removeAttribute("transform");
    elements.edgeText.removeAttribute("textLength");
    elements.edgeText.removeAttribute("lengthAdjust");
    const edgeFont = Number.parseFloat(elements.edgeText.style.fontSize) || 14;
    const edgeMaxWidth = loadSide === "left" || loadSide === "right" ? loc.h - 6 : loc.w - 6;
    if (allocationMapEstimatedTextWidth(shortLocation, edgeFont) > edgeMaxWidth) {
      elements.edgeText.setAttribute("textLength", String(Math.max(8, Math.round(edgeMaxWidth))));
      elements.edgeText.setAttribute("lengthAdjust", "spacingAndGlyphs");
    }
    if (assignment) {
      if (loadSide === "left") {
        const edgeX = loc.x + edgeBand / 2;
        elements.edgeText.setAttribute("x", edgeX);
        elements.edgeText.setAttribute("y", center.y);
        elements.edgeText.setAttribute("transform", `rotate(-90, ${edgeX}, ${center.y})`);
      } else if (loadSide === "right") {
        const edgeX = loc.x + loc.w - edgeBand / 2;
        elements.edgeText.setAttribute("x", edgeX);
        elements.edgeText.setAttribute("y", center.y);
        elements.edgeText.setAttribute("transform", `rotate(-90, ${edgeX}, ${center.y})`);
      } else if (loadSide === "top") {
        elements.edgeText.setAttribute("x", center.x);
        elements.edgeText.setAttribute("y", loc.y + edgeBand / 2);
      } else {
        elements.edgeText.setAttribute("x", center.x);
        elements.edgeText.setAttribute("y", loc.y + loc.h - edgeBand / 2);
      }
    }

    elements.mainText.textContent = "";
    elements.mainText.setAttribute("x", contentX);
    elements.mainText.setAttribute("y", firstLineY);
    elements.mainText.setAttribute("class", assignment ? "allocation-map-label-main" : "allocation-map-label");
    elements.mainText.style.fontSize = `${mainFont}px`;
    elements.mainText.removeAttribute("transform");
    elements.mainText.removeAttribute("textLength");
    elements.mainText.removeAttribute("lengthAdjust");
    if (!horizontal) {
      elements.mainText.setAttribute("transform", `rotate(-90, ${contentX}, ${contentY})`);
    }
    labelLines.forEach((line, index) => {
      const span = document.createElementNS(ALLOCATION_MAP_NS, "tspan");
      span.setAttribute("x", contentX);
      span.setAttribute("y", firstLineY + index * lineHeight);
      if (allocationMapEstimatedTextWidth(line, mainFont) > contentWidth) {
        span.setAttribute("textLength", String(Math.round(contentWidth)));
        span.setAttribute("lengthAdjust", "spacingAndGlyphs");
      }
      span.textContent = line;
      elements.mainText.appendChild(span);
    });

    elements.metaText.textContent = "";
    elements.metaText.style.display = "none";
    elements.metaText.setAttribute("x", contentX);
    elements.metaText.setAttribute("y", contentY);
  }

  function setUnusedCapacityStripe(elements, loc, assignment) {
    const unusedEl = elements.unused;
    unusedEl.style.display = "none";
    if (!assignment || !elements.unusedPatternId) return;
    const capacity = allocationMapNumber(assignment.maxPall || loc.maxPall);
    const placed = allocationMapNumber(assignment.placedPallets);
    if (capacity <= 0 || placed >= capacity) return;
    const fraction = allocationMapClamp((capacity - Math.max(0, placed)) / capacity, 0, 1);
    if (fraction < 0.01) return;
    const color = colorMap.get(assignment.carrier) || "#94a3b8";
    elements.unusedPatternBase?.setAttribute("fill", allocationMapMixHexColor(color, "#ffffff", 0.72));
    elements.unusedPatternBand?.setAttribute("fill", allocationMapMixHexColor(color, "#ffffff", 0.36));
    const loadSide = allocationMapLoadOriginSide(loc.loadDirection, loc);
    let x = loc.x;
    let y = loc.y;
    let w = loc.w;
    let h = loc.h;
    if (loadSide === "left") {
      w = loc.w * fraction;
    } else if (loadSide === "right") {
      w = loc.w * fraction;
      x = loc.x + loc.w - w;
    } else if (loadSide === "top") {
      h = loc.h * fraction;
    } else {
      h = loc.h * fraction;
      y = loc.y + loc.h - h;
    }
    unusedEl.setAttribute("x", x);
    unusedEl.setAttribute("y", y);
    unusedEl.setAttribute("width", w);
    unusedEl.setAttribute("height", h);
    unusedEl.setAttribute("fill", `url(#${elements.unusedPatternId})`);
    unusedEl.style.display = "";
  }

  function updateLocationVisual(location) {
    const loc = locationByName.get(location);
    const elements = state.locElements.get(location);
    if (!loc || !elements) return;
    const assignment = assignmentByLocation.get(location);
    elements.rect.classList.toggle("is-assigned", Boolean(assignment));
    elements.rect.classList.toggle("is-selected", state.selectedLocation === location);
    elements.rect.classList.toggle("is-clipboard-source", state.clipboard?.source === location);
    elements.rect.classList.toggle("is-over-capacity", Boolean(assignment && assignment.unusedCapacity < -0.001));
    elements.rect.style.fill = assignment ? (colorMap.get(assignment.carrier) || "") : "";
    setUnusedCapacityStripe(elements, loc, assignment);
    setMapText(elements, loc, assignment);
  }

  function renderMetrics() {
    if (!metrics) return;
    const placed = allocationMapRound(assignments.reduce((sum, assignment) => sum + assignment.placedPallets, 0));
    const capacity = allocationMapRound(locations.reduce((sum, loc) => sum + loc.maxPall, 0));
    const availablePallets = allocationMapRound(Math.max(0, capacity - placed));
    const placedLocationCount = assignmentByLocation.size;
    const freeLocationCount = Math.max(0, locations.length - placedLocationCount);
    const over = assignments.filter((assignment) => assignment.unusedCapacity < -0.001).length;
    const unplaced = Array.isArray(entry.unplaced) ? entry.unplaced.length : 0;
    metrics.innerHTML = `
      <div><span>Placeringar</span><strong>${assignments.length}</strong></div>
      <div><span>Pallplatser</span><strong>${placed}</strong></div>
      <div><span>Lediga pallplatser</span><strong>${availablePallets}</strong></div>
      <div><span>Kapacitet</span><strong>${capacity}</strong></div>
      <div><span>Lediga ytor</span><strong>${freeLocationCount}</strong></div>
      <div class="${over ? "is-warning" : ""}"><span>Över kapacitet</span><strong>${over}</strong></div>
      <div class="${unplaced ? "is-warning" : ""}"><span>Ej placerade</span><strong>${unplaced}</strong></div>
    `;
  }

  function renderDetail() {
    if (!detail) return;
    const loc = locationByName.get(state.selectedLocation);
    const assignment = assignmentByLocation.get(state.selectedLocation);
    if (!loc) {
      detail.innerHTML = `<p class="allocation-muted">Ingen yta vald.</p>`;
      return;
    }
    detail.innerHTML = `
      <h4>${allocationEscape(loc.location)}</h4>
      <dl>
        <div><dt>Max pall</dt><dd>${allocationEscape(loc.maxPall || "")}</dd></div>
        ${assignment ? `
          <div><dt>Sändning</dt><dd>${allocationEscape(assignment.shipment)}</dd></div>
          ${assignment.customer ? `<div><dt>Kund</dt><dd>${allocationEscape(assignment.customer)}</dd></div>` : ""}
          <div><dt>Transportör</dt><dd>${allocationEscape(assignment.carrier)}</dd></div>
          ${assignment.cluster ? `<div><dt>Kluster</dt><dd>${allocationEscape(assignment.cluster)}</dd></div>` : ""}
          <div><dt>Placerade</dt><dd>${allocationEscape(assignment.placedPallets)}</dd></div>
          <div><dt>Outnyttjat</dt><dd>${allocationEscape(assignment.unusedCapacity)}</dd></div>
        ` : `<div><dt>Status</dt><dd>Ledig</dd></div>`}
      </dl>
    `;
  }

  function renderOverview() {
    if (!overview) return;
    const query = String(search?.value || "").trim().toLowerCase();
    const rows = [...assignments]
      .sort((a, b) => allocationMapCompareLocation(a.location, b.location))
      .filter((assignment) => {
        const haystack = `${assignment.location} ${assignment.shipment} ${assignment.customer} ${assignment.carrier} ${assignment.cluster}`.toLowerCase();
        return !query || haystack.includes(query);
      });
    overview.innerHTML = `
      <table>
        <thead><tr><th>UTL</th><th>Kund</th><th>Pall</th></tr></thead>
        <tbody>
          ${rows.map((assignment) => `
            <tr data-map-overview-location="${allocationEscape(assignment.location)}" class="${assignment.location === state.selectedLocation ? "is-selected" : ""}">
              <td>${allocationEscape(assignment.location)}</td>
              <td>${allocationEscape(assignment.customer || assignment.shipment || assignment.carrier)}</td>
              <td>${allocationEscape(assignment.placedPallets)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  function refreshMap() {
    locations.forEach((loc) => updateLocationVisual(loc.location));
    renderMetrics();
    renderDetail();
    renderOverview();
  }

  function selectLocation(location, center = false) {
    const previous = state.selectedLocation;
    state.selectedLocation = locationByName.has(location) ? location : "";
    if (previous) updateLocationVisual(previous);
    if (state.selectedLocation) updateLocationVisual(state.selectedLocation);
    renderDetail();
    renderOverview();
    if (center && state.selectedLocation) {
      const loc = locationByName.get(state.selectedLocation);
      const centerPoint = locationCenter(loc);
      const rect = svg.getBoundingClientRect();
      state.transform.x = rect.width / 2 - centerPoint.x * state.transform.scale;
      state.transform.y = rect.height / 2 - centerPoint.y * state.transform.scale;
      applyTransform();
    }
  }

  async function copyMapOverviewShipment(location) {
    const assignment = assignmentByLocation.get(location);
    if (!assignment?.shipment) return;
    try {
      await writeClipboardText(assignment.shipment);
      showToast(`Sändningsnummer kopierat: ${assignment.shipment}`, "success", 1800);
    } catch (error) {
      showToast(error.message || "Kunde inte kopiera sändningsnumret.", "error", 5000);
    }
  }

  function clearDragTarget() {
    if (state.drag?.target) {
      state.locElements.get(state.drag.target)?.rect.classList.remove("is-drop-target");
    }
    if (state.drag) state.drag.target = "";
  }

  function setDragTarget(location) {
    if (!state.drag || state.drag.target === location) return;
    clearDragTarget();
    state.drag.target = location;
    if (location) state.locElements.get(location)?.rect.classList.add("is-drop-target");
  }

  function placeAssignment(assignment, target, fallbackSource = "") {
    if (!assignment || !locationByName.has(target)) return false;
    const source = assignment.location;
    if (source === target) return false;
    const targetAssignment = assignmentByLocation.get(target);
    if (source) assignmentByLocation.delete(source);
    if (targetAssignment && targetAssignment !== assignment) {
      const swapLocation = source || fallbackSource;
      if (swapLocation && locationByName.has(swapLocation)) {
        targetAssignment.location = swapLocation;
        updateAssignmentCapacity(targetAssignment);
        assignmentByLocation.set(swapLocation, targetAssignment);
      } else {
        targetAssignment.location = "";
      }
    }
    assignment.location = target;
    updateAssignmentCapacity(assignment);
    assignmentByLocation.set(target, assignment);
    selectLocation(target);
    refreshMap();
    return true;
  }

  function moveAssignment(source, target, options = {}) {
    const sourceAssignment = assignmentByLocation.get(source);
    if (!sourceAssignment || !locationByName.has(target) || source === target) return false;
    if (options.recordHistory !== false) rememberMapMutation();
    const moved = placeAssignment(sourceAssignment, target, source);
    if (moved && options.announce) {
      showToast(`Flyttade ${assignmentLabel(sourceAssignment)} till ${target}.`, "success", 2500);
    }
    return moved;
  }

  function copySelectedAssignment(mode) {
    const source = state.selectedLocation;
    const assignment = assignmentByLocation.get(source);
    if (!source || !assignment) {
      showToast("Välj en placerad yta först.", "error", 3500);
      return;
    }
    state.clipboard = { assignmentId: assignment.id, source, mode };
    refreshMap();
    showToast(
      `${mode === "cut" ? "Klippte ut" : "Kopierade"} ${assignmentLabel(assignment)} från ${source}. Välj målyta och klistra in.`,
      "success",
      3500,
    );
  }

  function pasteMapClipboard() {
    if (!state.clipboard) {
      showToast("Inget karturklipp att klistra in.", "error", 3500);
      return;
    }
    const target = state.selectedLocation;
    if (!target || !locationByName.has(target)) {
      showToast("Välj en målyta innan du klistrar in.", "error", 3500);
      return;
    }
    const assignment = assignmentById(state.clipboard.assignmentId);
    if (!assignment) {
      state.clipboard = null;
      showToast("Karturklippet finns inte kvar.", "error", 3500);
      return;
    }
    if (assignment.location === target) {
      showToast("Placeringen ligger redan på vald yta.", "error", 2500);
      return;
    }
    const clipboardSource = state.clipboard.source;
    const clipboardMode = state.clipboard.mode;
    rememberMapMutation();
    const pasted = placeAssignment(assignment, target, clipboardSource);
    if (!pasted) {
      state.history.pop();
      showToast("Kunde inte klistra in placeringen.", "error", 3500);
      return;
    }
    if (clipboardMode === "cut") state.clipboard = null;
    else state.clipboard.source = assignment.location;
    refreshMap();
    showToast(`Klistrade in ${assignmentLabel(assignment)} på ${target}.`, "success", 2500);
  }

  function undoMapMutation() {
    const snapshot = state.history.pop();
    if (!snapshot) {
      if (state.clipboard) {
        state.clipboard = null;
        refreshMap();
        showToast("Tömde karturklippet.", "success", 2500);
        return;
      }
      showToast("Det finns inget kartdrag att angra.", "error", 2500);
      return;
    }
    restoreMapMutation(snapshot);
    showToast("Ångrade senaste kartändringen.", "success", 2500);
  }

  function isMapShortcutTextTarget(target) {
    const element = target instanceof Element ? target : null;
    return Boolean(element?.closest("input, textarea, select, [contenteditable='true']"));
  }

  function handleMapShortcut(event) {
    if (!(event.ctrlKey || event.metaKey) || event.altKey || isMapShortcutTextTarget(event.target)) return;
    const key = String(event.key || "").toLowerCase();
    if (!["c", "x", "v", "z"].includes(key)) return;
    event.preventDefault();
    event.stopPropagation();
    if (key === "c") copySelectedAssignment("copy");
    if (key === "x") copySelectedAssignment("cut");
    if (key === "v") pasteMapClipboard();
    if (key === "z") undoMapMutation();
  }

  function createGhost(assignment, event) {
    const ghost = document.createElement("div");
    ghost.className = "allocation-map-drag-ghost";
    ghost.textContent = assignment.shipment || assignment.carrier || assignment.location;
    document.body.appendChild(ghost);
    ghost.style.left = `${event.clientX + 14}px`;
    ghost.style.top = `${event.clientY + 14}px`;
    return ghost;
  }

  function renderLocations() {
    canvas.innerHTML = "";
    defs?.querySelectorAll("[data-map-unused-stripes]").forEach((pattern) => pattern.remove());
    state.locElements.clear();
    locations.forEach((loc) => {
      const group = document.createElementNS(ALLOCATION_MAP_NS, "g");
      group.setAttribute("data-map-location-group", loc.location);
      const rect = document.createElementNS(ALLOCATION_MAP_NS, "rect");
      rect.setAttribute("x", loc.x);
      rect.setAttribute("y", loc.y);
      rect.setAttribute("width", loc.w);
      rect.setAttribute("height", loc.h);
      rect.setAttribute("class", "allocation-map-loc");
      rect.dataset.mapLocation = loc.location;
      const unusedPatternId = `allocation-map-unused-stripes-${host.dataset.mapIndex || "0"}-${allocationMapSafeSvgId(loc.location)}`;
      const unusedPattern = document.createElementNS(ALLOCATION_MAP_NS, "pattern");
      unusedPattern.setAttribute("id", unusedPatternId);
      unusedPattern.setAttribute("data-map-unused-stripes", loc.location);
      unusedPattern.setAttribute("width", "18");
      unusedPattern.setAttribute("height", "18");
      unusedPattern.setAttribute("patternUnits", "userSpaceOnUse");
      unusedPattern.setAttribute("patternTransform", "rotate(45)");
      const unusedPatternBase = document.createElementNS(ALLOCATION_MAP_NS, "rect");
      unusedPatternBase.setAttribute("x", "0");
      unusedPatternBase.setAttribute("y", "0");
      unusedPatternBase.setAttribute("width", "18");
      unusedPatternBase.setAttribute("height", "18");
      const unusedPatternBand = document.createElementNS(ALLOCATION_MAP_NS, "rect");
      unusedPatternBand.setAttribute("x", "0");
      unusedPatternBand.setAttribute("y", "0");
      unusedPatternBand.setAttribute("width", "8");
      unusedPatternBand.setAttribute("height", "18");
      unusedPattern.appendChild(unusedPatternBase);
      unusedPattern.appendChild(unusedPatternBand);
      defs?.appendChild(unusedPattern);
      const unused = document.createElementNS(ALLOCATION_MAP_NS, "rect");
      unused.setAttribute("class", "allocation-map-unused");
      const edgeText = document.createElementNS(ALLOCATION_MAP_NS, "text");
      edgeText.setAttribute("class", "allocation-map-label-edge");
      const mainText = document.createElementNS(ALLOCATION_MAP_NS, "text");
      mainText.setAttribute("class", "allocation-map-label-main");
      const metaText = document.createElementNS(ALLOCATION_MAP_NS, "text");
      metaText.setAttribute("class", "allocation-map-label-sub");
      group.appendChild(rect);
      group.appendChild(unused);
      group.appendChild(edgeText);
      group.appendChild(mainText);
      group.appendChild(metaText);
      canvas.appendChild(group);
      state.locElements.set(loc.location, {
        group,
        rect,
        unused,
        unusedPatternId,
        unusedPatternBase,
        unusedPatternBand,
        edgeText,
        mainText,
        metaText,
      });
    });
    refreshMap();
  }

  function exportMapCsv() {
    const header = [
      "Sändningsnr", "Transportör", "Kluster", "Lagerplats", "Max pall", "Placerade pallplatser",
      "Sändningens pallplatser", "Outnyttjad kapacitet", "Placering nr",
    ];
    const rows = assignments.map((assignment) => [
      assignment.shipment,
      assignment.carrier,
      assignment.cluster,
      assignment.location,
      assignment.maxPall,
      assignment.placedPallets,
      assignment.shipmentPallets,
      assignment.unusedCapacity,
      assignment.placementNo,
    ]);
    const text = [header, ...rows].map((row) => row.map(allocationMapTsvCell).join("\t")).join("\n");
    allocationDownloadText("ytgenerering_justerad_karta.csv", `${text}\n`);
  }

  function exportAskCsv() {
    const grouped = new Map();
    assignments.forEach((assignment) => {
      if (!assignment.shipment) return;
      if (!grouped.has(assignment.shipment)) grouped.set(assignment.shipment, []);
      grouped.get(assignment.shipment).push(assignment);
    });
    const rows = [];
    const missingCompanyOrders = [];
    grouped.forEach((group) => {
      const orders = [...new Set(group.flatMap((assignment) => assignment.orderNumbers || []))];
      if (!orders.length) return;
      const areas = group
        .slice()
        .sort((a, b) => a.placementNo - b.placementNo || allocationMapCompareLocation(a.location, b.location))
        .map((assignment) => assignment.location)
        .join(", ");
      orders.forEach((orderNumber) => {
        const company = group
          .map((assignment) => assignment.orderCompanies?.[orderNumber] || assignment.company || "")
          .find((value) => String(value || "").trim());
        if (!company) {
          missingCompanyOrders.push(orderNumber);
          return;
        }
        rows.push([areas, String(company).trim().toUpperCase(), orderNumber, "A"]);
      });
    });
    if (missingCompanyOrders.length) {
      showToast(`Saknar bolag för justerad ASK-export: ${missingCompanyOrders.slice(0, 5).join(", ")}`, "error", 6000);
      return;
    }
    if (!rows.length) {
      showToast("Saknar ordernummer för justerad ASK-export.", "error", 5000);
      return;
    }
    const text = [["area_num", "company", "order_num", "pick_zone"], ...rows]
      .map((row) => row.map(allocationMapTsvCell).join("\t"))
      .join("\n");
    allocationDownloadText("v_ask_order_overview_order_set_area_execute_command_justerad.csv", `${text}\n`);
  }

  renderLocations();
  fitMap();

  svg.addEventListener("wheel", (event) => {
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1;
    const rect = svg.getBoundingClientRect();
    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;
    state.minScale = fittedMapScale(rect);
    const nextScale = allocationMapClamp(state.transform.scale * factor, state.minScale, 5);
    const appliedFactor = nextScale / Math.max(0.001, state.transform.scale);
    state.transform.x = mouseX - (mouseX - state.transform.x) * appliedFactor;
    state.transform.y = mouseY - (mouseY - state.transform.y) * appliedFactor;
    state.transform.scale = nextScale;
    applyTransform();
  }, { passive: false });

  svg.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    host.focus?.({ preventScroll: true });
    const rect = event.target.closest("[data-map-location]");
    if (rect) {
      const location = rect.dataset.mapLocation;
      selectLocation(location);
      const assignment = assignmentByLocation.get(location);
      if (assignment) {
        state.drag = {
          source: location,
          target: "",
          assignment,
          startX: event.clientX,
          startY: event.clientY,
          ghost: null,
          moved: false,
        };
        svg.setPointerCapture?.(event.pointerId);
        event.preventDefault();
      }
      return;
    }
    state.pan = {
      startX: event.clientX,
      startY: event.clientY,
      initX: state.transform.x,
      initY: state.transform.y,
    };
    svg.classList.add("is-panning");
    svg.setPointerCapture?.(event.pointerId);
  });

  svg.addEventListener("pointermove", (event) => {
    if (state.drag) {
      const dx = event.clientX - state.drag.startX;
      const dy = event.clientY - state.drag.startY;
      if (!state.drag.moved && Math.hypot(dx, dy) > 5) {
        state.drag.moved = true;
        state.drag.ghost = createGhost(state.drag.assignment, event);
      }
      if (state.drag.ghost) {
        state.drag.ghost.style.left = `${event.clientX + 14}px`;
        state.drag.ghost.style.top = `${event.clientY + 14}px`;
        const targetEl = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-map-location]");
        const target = targetEl?.dataset.mapLocation || "";
        setDragTarget(target && target !== state.drag.source ? target : "");
      }
      return;
    }
    if (!state.pan) return;
    const dx = event.clientX - state.pan.startX;
    const dy = event.clientY - state.pan.startY;
    state.transform.x = state.pan.initX + dx;
    state.transform.y = state.pan.initY + dy;
    applyTransform();
  });

  svg.addEventListener("pointerup", (event) => {
    if (state.drag) {
      const drag = state.drag;
      const target = drag.target;
      drag.ghost?.remove();
      clearDragTarget();
      state.drag = null;
      svg.releasePointerCapture?.(event.pointerId);
      if (drag.moved && target) moveAssignment(drag.source, target);
      return;
    }
    if (state.pan) {
      state.pan = null;
      svg.classList.remove("is-panning");
      svg.releasePointerCapture?.(event.pointerId);
    }
  });

  overview?.addEventListener("click", (event) => {
    const row = event.target.closest("[data-map-overview-location]");
    if (!row) return;
    const location = row.dataset.mapOverviewLocation;
    host.focus?.({ preventScroll: true });
    selectLocation(location, true);
    void copyMapOverviewShipment(location);
  });
  search?.addEventListener("input", renderOverview);
  host.addEventListener("keydown", handleMapShortcut);
  host.querySelector("[data-map-fit]")?.addEventListener("click", fitMap);
  host.querySelector("[data-map-rotate]")?.addEventListener("click", () => {
    state.rotation = state.rotation ? 0 : 90;
    host.classList.toggle("is-rotated", Boolean(state.rotation));
    applyRotation();
  });
  host.querySelector("[data-map-fullscreen]")?.addEventListener("click", async () => {
    if (document.fullscreenElement === host) {
      await document.exitFullscreen?.();
    } else {
      await host.requestFullscreen?.();
      requestAnimationFrame(fitMap);
    }
  });
  host.querySelector("[data-map-export-csv]")?.addEventListener("click", exportMapCsv);
  host.querySelector("[data-map-export-ask]")?.addEventListener("click", exportAskCsv);

  function renderMissingPanel() {
    if (!missingPanel) return;
    const rows = (Array.isArray(entry.unplaced) ? entry.unplaced : [])
      .map((row) => ({
        customer: String(row.customer || ""),
        carrier: String(row.carrier || ""),
        shipment: String(row.shipment || ""),
        unplacedPallets: allocationMapRound(row.unplacedPallets),
      }))
      .sort((a, b) => b.unplacedPallets - a.unplacedPallets);
    if (!rows.length) {
      missingPanel.innerHTML = `<p class="allocation-muted">Alla sändningar fick plats.</p>`;
      return;
    }
    missingPanel.innerHTML = `
      <h4>Saknade kunder <span>${rows.length}</span></h4>
      <ul class="allocation-map-missing-list">
        ${rows.map((row) => `
          <li>
            <span class="allocation-map-missing-dot" style="background:${colorMap.get(row.carrier) || "#d1d5db"}"></span>
            <span class="allocation-map-missing-name">${allocationEscape(row.customer || row.shipment || row.carrier)}</span>
            <span class="allocation-map-missing-meta">${allocationEscape(row.carrier)} · −${allocationEscape(row.unplacedPallets)} pall</span>
          </li>
        `).join("")}
      </ul>
    `;
  }

  renderMissingPanel();
  missingToggle?.addEventListener("click", () => {
    const open = missingPanel.hidden;
    missingPanel.hidden = !open;
    missingToggle.setAttribute("aria-pressed", String(open));
  });
}

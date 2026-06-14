const ALLOCATION_MAP_LOAD_DIRECTIONS = {
  horizontal: ["right", "left"],
  vertical: ["down", "up"],
};

function allocationMapDefaultLoadDirection(row = {}) {
  const w = allocationMapNumber(row.w ?? row.width, 1);
  const h = allocationMapNumber(row.h ?? row.height, 1);
  return w >= h ? "right" : "down";
}

function allocationMapLoadDirectionsForRow(row = {}) {
  const w = allocationMapNumber(row.w ?? row.width, 1);
  const h = allocationMapNumber(row.h ?? row.height, 1);
  return w >= h ? ALLOCATION_MAP_LOAD_DIRECTIONS.horizontal : ALLOCATION_MAP_LOAD_DIRECTIONS.vertical;
}

function allocationNormalizeMapLoadDirection(value, row = {}) {
  const raw = String(value || "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
  const aliases = {
    right: "right",
    hoger: "right",
    east: "right",
    left: "left",
    vanster: "left",
    west: "left",
    up: "up",
    upp: "up",
    north: "up",
    down: "down",
    ner: "down",
    ned: "down",
    south: "down",
  };
  const direction = aliases[raw] || "";
  return allocationMapLoadDirectionsForRow(row).includes(direction) ? direction : allocationMapDefaultLoadDirection(row);
}

function allocationNextMapLoadDirection(value, row = {}) {
  const current = allocationNormalizeMapLoadDirection(value, row);
  const directions = allocationMapLoadDirectionsForRow(row);
  const index = directions.indexOf(current);
  return directions[(index + 1) % directions.length];
}

function allocationRotateMapLoadDirectionLeft(value) {
  const rotated = { right: "up", up: "left", left: "down", down: "right" };
  return rotated[value] || value;
}

function allocationMapLoadDirectionLabel(value) {
  const labels = { right: "höger", down: "ned", left: "vänster", up: "upp" };
  return labels[value] || value;
}

function allocationMapLoadOriginSide(value, row = {}) {
  const direction = allocationNormalizeMapLoadDirection(value, row);
  if (direction === "down") return "top";
  if (direction === "up") return "bottom";
  if (direction === "left") return "right";
  return "left";
}

function normalizeAllocationMapLayout(payload) {
  const rows = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.locations)
      ? payload.locations
      : Array.isArray(payload?.rows)
        ? payload.rows
        : [];
  const normalized = rows.map((row) => {
    const location = String(row?.location || row?.lagerplats || row?.name || "").trim().toUpperCase();
    const x = Math.round(allocationMapNumber(row?.x));
    const y = Math.round(allocationMapNumber(row?.y));
    const w = Math.max(1, Math.round(allocationMapNumber(row?.w ?? row?.width, 240)));
    const h = Math.max(1, Math.round(allocationMapNumber(row?.h ?? row?.height, 80)));
    const maxPall = allocationMapRound(row?.maxPall ?? row?.max_pall ?? 2);
    if (!/^UTL\d+[A-ZÅÄÖ]?$/.test(location)) return null;
    return {
      location,
      x,
      y,
      w,
      h,
      maxPall: maxPall > 0 ? maxPall : 2,
      loadDirection: allocationNormalizeMapLoadDirection(
        row?.loadDirection ?? row?.load_direction ?? row?.loadingDirection ?? row?.direction,
        { w, h },
      ),
    };
  }).filter(Boolean);
  const byLocation = new Map();
  normalized.forEach((row) => byLocation.set(row.location, row));
  const locations = [...byLocation.values()].sort((a, b) => allocationMapCompareLocation(a.location, b.location));
  const defaults = payload && !Array.isArray(payload) ? normalizeAllocationMapLayout(payload.defaults).locations : [];
  const rawAvailable = payload && !Array.isArray(payload)
    ? (payload.availableLocations || payload.available_locations || [])
    : [];
  const availableLocations = Array.isArray(rawAvailable)
    ? rawAvailable.map((row) => {
        const location = String(row?.location || row?.lagerplats || row?.name || "").trim().toUpperCase();
        if (!/^UTL\d+[A-ZÅÄÖ]?$/.test(location)) return null;
        const maxPall = allocationMapRound(row?.maxPall ?? row?.max_pall ?? 2);
        return { location, maxPall: maxPall > 0 ? maxPall : 2 };
      }).filter(Boolean).sort((a, b) => allocationMapCompareLocation(a.location, b.location))
    : [];
  return { version: 1, locations, defaults, availableLocations, canEdit: Boolean(payload?.can_edit) };
}

function allocationMapLayoutSaveSignature(items = []) {
  return normalizeAllocationMapLayout({ locations: items }).locations
    .map((row) => [
      row.location,
      row.x,
      row.y,
      row.w,
      row.h,
      row.maxPall,
      row.loadDirection,
    ].join("|"))
    .join("\n");
}

function allocationMapSettingsQuery(options = {}) {
  const query = allocationScopedQuery({ fallbackToUser: true, includeAreaFocus: true });
  const params = new URLSearchParams(query.startsWith("?") ? query.slice(1) : "");
  if (Object.prototype.hasOwnProperty.call(options, "includeOptions")) {
    params.set("include_options", options.includeOptions ? "true" : "false");
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

async function loadAllocationMapLayout(options = {}) {
  const query = allocationMapSettingsQuery({ includeOptions: options.includeOptions !== false });
  return normalizeAllocationMapLayout(await allocationJson(`${ALLOCATION_API}/ytgenerering-map-layout${query}`));
}

async function loadAllocationMapLocationOptions() {
  const query = allocationMapSettingsQuery();
  const payload = await allocationJson(`${ALLOCATION_API}/ytgenerering-location-options${query}`);
  return normalizeAllocationMapLayout({ available_locations: payload?.available_locations || [] }).availableLocations;
}


function allocationMapLayoutBounds(rows) {
  if (!rows.length) return { minX: 0, minY: 0, maxX: 1200, maxY: 800, width: 1200, height: 800 };
  const minX = Math.min(...rows.map((row) => row.x));
  const minY = Math.min(...rows.map((row) => row.y));
  const maxX = Math.max(...rows.map((row) => row.x + row.w));
  const maxY = Math.max(...rows.map((row) => row.y + row.h));
  const pad = 220;
  return {
    minX: minX - pad,
    minY: minY - pad,
    maxX: maxX + pad,
    maxY: maxY + pad,
    width: Math.max(800, maxX - minX + pad * 2),
    height: Math.max(600, maxY - minY + pad * 2),
  };
}

function allocationMapLayoutNextNumber(rows) {
  const numbers = rows
    .map((row) => String(row.location || "").match(/^UTL(\d+)/i))
    .filter(Boolean)
    .map((match) => Number.parseInt(match[1], 10))
    .filter(Number.isFinite);
  return numbers.length ? Math.max(...numbers) + 1 : 1;
}

function allocationMapSettingLabelAttrs(row) {
  const horizontal = row.w >= row.h;
  const cx = row.x + row.w / 2;
  const cy = row.y + row.h / 2;
  const shortSide = Math.max(1, Math.min(row.w, row.h));
  const longSide = Math.max(1, Math.max(row.w, row.h));
  const label = allocationMapShortLocation(row.location);
  const fontSize = allocationMapClamp(shortSide * 0.58, 16, 48);
  const maxWidth = Math.max(8, longSide - 8);
  const attrs = {
    x: cx,
    y: cy,
    label,
    fontSize,
    textLength: "",
    transform: horizontal ? "" : `rotate(-90, ${cx}, ${cy})`,
  };
  if (allocationMapEstimatedTextWidth(label, fontSize) > maxWidth) {
    attrs.textLength = String(Math.round(maxWidth));
  }
  return attrs;
}

function allocationRenderMapSettingLabel(row) {
  const attrs = allocationMapSettingLabelAttrs(row);
  return `<text class="allocation-map-setting-label" x="${attrs.x}" y="${attrs.y}" style="font-size:${attrs.fontSize}px"${attrs.transform ? ` transform="${attrs.transform}"` : ""}${attrs.textLength ? ` textLength="${attrs.textLength}" lengthAdjust="spacingAndGlyphs"` : ""}>${allocationEscape(attrs.label)}</text>`;
}

function allocationUpdateMapSettingLabelElement(labelElement, row) {
  if (!labelElement) return;
  const attrs = allocationMapSettingLabelAttrs(row);
  labelElement.setAttribute("x", attrs.x);
  labelElement.setAttribute("y", attrs.y);
  labelElement.style.fontSize = `${attrs.fontSize}px`;
  labelElement.textContent = attrs.label;
  if (attrs.transform) labelElement.setAttribute("transform", attrs.transform);
  else labelElement.removeAttribute("transform");
  if (attrs.textLength) {
    labelElement.setAttribute("textLength", attrs.textLength);
    labelElement.setAttribute("lengthAdjust", "spacingAndGlyphs");
  } else {
    labelElement.removeAttribute("textLength");
    labelElement.removeAttribute("lengthAdjust");
  }
}

function allocationMapSettingDirectionMarkerBand(row) {
  const shortSide = Math.max(1, Math.min(row.w, row.h));
  return allocationMapClamp(shortSide * 0.56, 24, 58);
}

function allocationMapSettingDirectionPath(row) {
  const direction = allocationNormalizeMapLoadDirection(row.loadDirection, row);
  const inset = allocationMapClamp(Math.min(row.w, row.h) * 0.08, 4, 10);
  const band = allocationMapSettingDirectionMarkerBand(row);
  const cx = row.x + row.w / 2;
  const cy = row.y + row.h / 2;
  if (direction === "down") {
    return `M${row.x + inset} ${row.y + inset}L${row.x + row.w - inset} ${row.y + inset}L${cx} ${row.y + band}Z`;
  }
  if (direction === "up") {
    return `M${row.x + inset} ${row.y + row.h - inset}L${row.x + row.w - inset} ${row.y + row.h - inset}L${cx} ${row.y + row.h - band}Z`;
  }
  if (direction === "left") {
    return `M${row.x + row.w - inset} ${row.y + inset}L${row.x + row.w - inset} ${row.y + row.h - inset}L${row.x + row.w - band} ${cy}Z`;
  }
  return `M${row.x + inset} ${row.y + inset}L${row.x + inset} ${row.y + row.h - inset}L${row.x + band} ${cy}Z`;
}

function allocationRenderMapSettingDirectionArrow(row) {
  return `<path class="allocation-map-setting-direction-arrow" d="${allocationMapSettingDirectionPath(row)}"></path>`;
}

function allocationUpdateMapSettingDirectionArrowElement(arrowElement, row) {
  arrowElement?.setAttribute("d", allocationMapSettingDirectionPath(row));
}

function allocationMapLayoutStep(row, direction, gap) {
  if (direction === "left") return { dx: -(row.w + gap), dy: 0 };
  if (direction === "up") return { dx: 0, dy: -(row.h + gap) };
  if (direction === "down") return { dx: 0, dy: row.h + gap };
  return { dx: row.w + gap, dy: 0 };
}

function allocationMapLayoutRectsOverlap(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function allocationMapLayoutAvoidCollision(rows, rect, direction, gap) {
  const step = allocationMapLayoutStep(rect, direction, gap);
  const placed = { ...rect };
  let guard = 0;
  while (rows.some((row) => allocationMapLayoutRectsOverlap(placed, row)) && guard < 300) {
    placed.x += step.dx === 0 && step.dy === 0 ? rect.w + gap : step.dx;
    placed.y += step.dy;
    guard += 1;
  }
  placed.x = Math.round(placed.x / 10) * 10;
  placed.y = Math.round(placed.y / 10) * 10;
  return placed;
}

function allocationMapLayoutSelectedRow(rows, selectedLocation) {
  return rows.find((row) => row.location === selectedLocation) || rows[rows.length - 1] || {
    location: "UTL0",
    x: 0,
    y: 0,
    w: 240,
    h: 80,
    maxPall: 2,
    loadDirection: "right",
  };
}

function allocationMapLayoutSizeForCapacity(base, maxPall) {
  const baseWidth = Math.max(1, Math.round(allocationMapNumber(base.w ?? base.width, 240)));
  const baseHeight = Math.max(1, Math.round(allocationMapNumber(base.h ?? base.height, 80)));
  const baseCapacity = Math.max(0.1, allocationMapNumber(base.maxPall ?? base.max_pall, 2));
  const nextCapacity = Math.max(0.1, allocationMapNumber(maxPall, baseCapacity));
  const ratio = nextCapacity / baseCapacity;
  if (baseWidth >= baseHeight) {
    return { w: Math.max(1, Math.round(baseWidth * ratio)), h: baseHeight };
  }
  return { w: baseWidth, h: Math.max(1, Math.round(baseHeight * ratio)) };
}

function allocationMapLayoutSeriesRows(rows, options) {
  const start = Math.max(1, Number.parseInt(options.start, 10) || allocationMapLayoutNextNumber(rows));
  const end = Math.max(1, Number.parseInt(options.end, 10) || start);
  const direction = options.direction || "right";
  const gap = Math.max(0, Number.parseInt(options.gap, 10) || 20);
  const base = allocationMapLayoutSelectedRow(rows, options.selectedLocation);
  const step = allocationMapLayoutStep(base, direction, gap);
  const existing = new Set(rows.map((row) => row.location));
  const availableByLocation = new Map((options.availableLocations || []).map((row) => [row.location, row]));
  const useAvailableFilter = availableByLocation.size > 0;
  const additions = [];
  const count = Math.abs(end - start) + 1;
  let cursor = { ...base, x: base.x + step.dx, y: base.y + step.dy };
  for (let index = 0; index < count; index += 1) {
    const number = start <= end ? start + index : start - index;
    const location = `UTL${number}`;
    if (existing.has(location)) {
      const existingRow = rows.find((row) => row.location === location);
      if (existingRow) {
        const existingStep = allocationMapLayoutStep(existingRow, direction, gap);
        cursor = { ...existingRow, x: existingRow.x + existingStep.dx, y: existingRow.y + existingStep.dy };
      }
      continue;
    }
    const available = availableByLocation.get(location);
    if (useAvailableFilter && !available) continue;
    const maxPall = allocationMapRound(options.maxPall || available?.maxPall || base.maxPall || 2);
    const scaledSize = allocationMapLayoutSizeForCapacity(
      { ...base, w: allocationMapNumber(options.w, base.w), h: allocationMapNumber(options.h, base.h) },
      maxPall,
    );
    const draft = {
      location,
      x: cursor.x,
      y: cursor.y,
      w: scaledSize.w,
      h: scaledSize.h,
      maxPall,
      loadDirection: allocationNormalizeMapLoadDirection(options.loadDirection || base.loadDirection, {
        w: scaledSize.w,
        h: scaledSize.h,
      }),
    };
    const placed = allocationMapLayoutAvoidCollision([...rows, ...additions], draft, direction, gap);
    additions.push(placed);
    existing.add(location);
    const placedStep = allocationMapLayoutStep(placed, direction, gap);
    cursor = { ...placed, x: placed.x + placedStep.dx, y: placed.y + placedStep.dy };
  }
  return additions;
}


async function mountAllocationMapSettingsPage(editor) {
  if (!editor) return;
  const canEdit = canEditAllocationMapSettings();
  let layout;
  let rows = [];
  let availableLocations = [];
  let availableLocationsLoading = false;
  let availableLocationsLoaded = false;
  let availableLocationsError = "";
  let selectedLocation = "";
  let selectedLocations = new Set();
  let clipboardRows = [];
  const undoStack = [];
  let drag = null;
  let pan = null;
  let viewBox = null;
  let statusText = "";
  let ignoreNextMapClick = false;
  let ignoreMapContextClickUntil = 0;
  let lastMapRotationAt = 0;
  const LOCATION_DRAG_TYPE = "application/x-flow-yt-location";
  const MAP_SNAP_SCREEN_PX = 4;
  const MAP_SNAP_MIN_UNITS = 2;

  try {
    layout = await loadAllocationMapLayout({ includeOptions: false });
    rows = [...(layout.locations || [])];
    availableLocations = [...(layout.availableLocations || [])];
    selectedLocation = rows[0]?.location || "";
    selectedLocations = selectedLocation ? new Set([selectedLocation]) : new Set();
  } catch (error) {
    editor.innerHTML = `<p class="allocation-status error">${allocationEscape(error.message || "Kunde inte läsa ytkartan.")}</p>`;
    return;
  }

  async function loadAvailableLocations() {
    if (availableLocationsLoading || availableLocationsLoaded) return;
    availableLocationsLoading = true;
    availableLocationsError = "";
    renderEditor();
    try {
      availableLocations = await loadAllocationMapLocationOptions();
      availableLocationsLoaded = true;
    } catch (error) {
      availableLocationsError = error.message || "Kunde inte lÃ¤sa lediga U-platser.";
    } finally {
      availableLocationsLoading = false;
      renderEditor();
    }
  }

  function selectedRow() {
    return rows.find((row) => row.location === selectedLocation) || null;
  }

  function cloneMapRows(sourceRows = rows) {
    return sourceRows.map((row) => ({ ...row }));
  }

  function sortedMapRows(sourceRows = rows) {
    return [...sourceRows].sort((a, b) => allocationMapCompareLocation(a.location, b.location));
  }

  function pushUndoSnapshot() {
    if (!canEdit) return;
    undoStack.push(cloneMapRows());
    if (undoStack.length > 80) undoStack.shift();
  }

  function pruneSelection() {
    const existing = new Set(rows.map((row) => row.location));
    selectedLocations = new Set([...selectedLocations].filter((location) => existing.has(location)));
    if (selectedLocation && !existing.has(selectedLocation)) selectedLocation = "";
    if (!selectedLocation && selectedLocations.size) selectedLocation = [...selectedLocations][0];
    if (!selectedLocations.size && rows.length) {
      selectedLocation = rows[0].location;
      selectedLocations = new Set([selectedLocation]);
    }
  }

  function selectedRows() {
    return rows.filter((row) => selectedLocations.has(row.location));
  }

  function setSelection(location, event = null, options = {}) {
    if (!location || !rows.some((row) => row.location === location)) return;
    const sorted = sortedMapRows();
    if (event?.shiftKey && selectedLocation) {
      const start = sorted.findIndex((row) => row.location === selectedLocation);
      const end = sorted.findIndex((row) => row.location === location);
      if (start >= 0 && end >= 0) {
        const [from, to] = start < end ? [start, end] : [end, start];
        selectedLocations = new Set(sorted.slice(from, to + 1).map((row) => row.location));
      }
    } else if (event?.ctrlKey || event?.metaKey) {
      selectedLocations = new Set(selectedLocations);
      if (selectedLocations.has(location) && selectedLocations.size > 1) selectedLocations.delete(location);
      else selectedLocations.add(location);
    } else if (!(options.keepExisting && selectedLocations.has(location))) {
      selectedLocations = new Set([location]);
    }
    selectedLocation = location;
  }

  function syncSelectionVisuals() {
    editor.querySelectorAll("[data-map-setting-rect]").forEach((item) => {
      item.classList.toggle("is-selected", selectedLocations.has(item.dataset.mapSettingRect || ""));
    });
    const count = editor.querySelector("[data-map-selection-count]");
    if (count) count.textContent = `${selectedLocations.size || 0} valda`;
    const row = selectedRow();
    if (!row) return;
    const fields = [
      ["[data-map-setting-location]", row.location],
      ["[data-map-setting-x]", row.x],
      ["[data-map-setting-y]", row.y],
      ["[data-map-setting-w]", row.w],
      ["[data-map-setting-h]", row.h],
      ["[data-map-setting-max]", row.maxPall],
    ];
    fields.forEach(([selector, value]) => {
      const input = editor.querySelector(selector);
      if (input) input.value = String(value);
    });
  }

  function restoreMapRows(snapshot) {
    rows = sortedMapRows(cloneMapRows(snapshot));
    pruneSelection();
    renderEditor();
  }

  function currentBounds() {
    const sourceRows = rows.length ? rows : (layout.defaults || []);
    return allocationMapLayoutBounds(sourceRows);
  }

  function snapTargetsForDrag() {
    const targets = { x: [], y: [] };
    rows.forEach((row) => {
      if (selectedLocations.has(row.location)) return;
      targets.x.push(row.x, row.x + row.w / 2, row.x + row.w);
      targets.y.push(row.y, row.y + row.h / 2, row.y + row.h);
    });
    return targets;
  }

  function closestSnap(candidates, targets, threshold) {
    let best = null;
    candidates.forEach((candidate) => {
      targets.forEach((target) => {
        const distance = Math.abs(target - candidate);
        if (distance <= threshold && (!best || distance < best.distance)) {
          best = { distance, delta: target - candidate, target };
        }
      });
    });
    return best;
  }

  function updateMapSnapGuides(guides = [], box = ensureViewBox()) {
    const group = editor.querySelector("[data-map-snap-guides]");
    if (!group) return;
    group.innerHTML = guides.map((guide) => {
      if (guide.axis === "x") {
        return `<line class="allocation-map-settings-guide-line" x1="${guide.value}" y1="${box.y}" x2="${guide.value}" y2="${box.y + box.height}"></line>`;
      }
      return `<line class="allocation-map-settings-guide-line" x1="${box.x}" y1="${guide.value}" x2="${box.x + box.width}" y2="${guide.value}"></line>`;
    }).join("");
  }

  function applySnapToDrag(dragState, dx, dy, scaleX, scaleY) {
    const draftRows = dragState.items.map((item) => ({
      row: item.row,
      x: item.originalX + dx,
      y: item.originalY + dy,
      w: item.row.w,
      h: item.row.h,
    }));
    const xCandidates = draftRows.flatMap((item) => [item.x, item.x + item.w / 2, item.x + item.w]);
    const yCandidates = draftRows.flatMap((item) => [item.y, item.y + item.h / 2, item.y + item.h]);
    const xSnap = closestSnap(xCandidates, dragState.snapTargets.x, Math.max(MAP_SNAP_MIN_UNITS, scaleX * MAP_SNAP_SCREEN_PX));
    const ySnap = closestSnap(yCandidates, dragState.snapTargets.y, Math.max(MAP_SNAP_MIN_UNITS, scaleY * MAP_SNAP_SCREEN_PX));
    const guides = [];
    if (xSnap) guides.push({ axis: "x", value: xSnap.target });
    if (ySnap) guides.push({ axis: "y", value: ySnap.target });
    updateMapSnapGuides(guides, dragState.viewBox);
    return { dx: dx + (xSnap?.delta || 0), dy: dy + (ySnap?.delta || 0), snapX: Boolean(xSnap), snapY: Boolean(ySnap) };
  }

  function ensureViewBox() {
    if (!viewBox) {
      const bounds = currentBounds();
      viewBox = { x: bounds.minX, y: bounds.minY, width: bounds.width, height: bounds.height };
    }
    return viewBox;
  }

  function clampMapSettingsViewBox(candidate) {
    const bounds = currentBounds();
    const width = Math.max(260, Math.min(bounds.width, candidate.width));
    const height = Math.max(180, Math.min(bounds.height, candidate.height));
    return {
      x: width >= bounds.width ? bounds.minX : allocationMapClamp(candidate.x, bounds.minX, bounds.maxX - width),
      y: height >= bounds.height ? bounds.minY : allocationMapClamp(candidate.y, bounds.minY, bounds.maxY - height),
      width,
      height,
    };
  }

  function setSvgViewBox() {
    const svg = editor.querySelector("[data-map-settings-svg]");
    if (!svg || !viewBox) return;
    viewBox = clampMapSettingsViewBox(viewBox);
    svg.setAttribute("viewBox", `${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`);
  }

  function fitView() {
    const bounds = currentBounds();
    viewBox = { x: bounds.minX, y: bounds.minY, width: bounds.width, height: bounds.height };
  }

  function zoomView(factor, event) {
    const svg = editor.querySelector("[data-map-settings-svg]");
    const box = svg?.getBoundingClientRect();
    const current = ensureViewBox();
    const bounds = currentBounds();
    const nextWidth = Math.max(260, Math.min(bounds.width, current.width * factor));
    const nextHeight = Math.max(180, Math.min(bounds.height, current.height * factor));
    let anchorX = current.x + current.width / 2;
    let anchorY = current.y + current.height / 2;
    if (box && event) {
      anchorX = current.x + ((event.clientX - box.left) / Math.max(1, box.width)) * current.width;
      anchorY = current.y + ((event.clientY - box.top) / Math.max(1, box.height)) * current.height;
    }
    const rx = (anchorX - current.x) / current.width;
    const ry = (anchorY - current.y) / current.height;
    viewBox = {
      x: anchorX - nextWidth * rx,
      y: anchorY - nextHeight * ry,
      width: nextWidth,
      height: nextHeight,
    };
    setSvgViewBox();
  }

  function svgPointFromClient(svg, clientX, clientY) {
    const point = svg?.createSVGPoint?.();
    const ctm = svg?.getScreenCTM?.();
    if (point && ctm) {
      point.x = clientX;
      point.y = clientY;
      const mapped = point.matrixTransform(ctm.inverse());
      return { x: mapped.x, y: mapped.y };
    }
    const box = svg?.getBoundingClientRect?.();
    const current = ensureViewBox();
    if (!box) return { x: current.x + current.width / 2, y: current.y + current.height / 2 };
    return {
      x: current.x + ((clientX - box.left) / Math.max(1, box.width)) * current.width,
      y: current.y + ((clientY - box.top) / Math.max(1, box.height)) * current.height,
    };
  }

  function mapSettingRowAtClientPoint(svg, clientX, clientY) {
    const point = svgPointFromClient(svg, clientX, clientY);
    return [...rows].reverse().find((row) => (
      point.x >= row.x
      && point.x <= row.x + row.w
      && point.y >= row.y
      && point.y <= row.y + row.h
    )) || null;
  }

  function hasLocationDrag(event) {
    const types = event.dataTransfer?.types;
    if (!types) return false;
    if (typeof types.includes === "function") return types.includes(LOCATION_DRAG_TYPE);
    if (typeof types.contains === "function") return types.contains(LOCATION_DRAG_TYPE);
    return Array.from(types).includes(LOCATION_DRAG_TYPE);
  }

  function draggedLocationFromEvent(event) {
    return String(
      event.dataTransfer?.getData(LOCATION_DRAG_TYPE)
      || event.dataTransfer?.getData("text/plain")
      || ""
    ).trim().toUpperCase();
  }

  function availableNotMapped(options = {}) {
    const placed = new Set(rows.map((row) => row.location));
    const search = options.ignoreSearch
      ? ""
      : String(editor.querySelector("[data-map-location-search]")?.value || "").trim().toUpperCase();
    return availableLocations
      .filter((row) => !placed.has(row.location))
      .filter((row) => !search || row.location.includes(search))
      .sort((a, b) => allocationMapCompareLocation(a.location, b.location));
  }

  function updateSelectedFromInputs() {
    const row = selectedRow();
    if (!row || !canEdit) return;
    pushUndoSnapshot();
    const previousLocation = row.location;
    const nextLocation = String(editor.querySelector("[data-map-setting-location]")?.value || row.location).trim().toUpperCase();
    if (/^UTL\d+[A-ZÅÄÖ]?$/.test(nextLocation) && nextLocation !== row.location && !rows.some((item) => item.location === nextLocation)) {
      row.location = nextLocation;
      selectedLocation = nextLocation;
      if (selectedLocations.has(previousLocation)) {
        selectedLocations.delete(previousLocation);
        selectedLocations.add(nextLocation);
      }
    }
    row.x = Math.round(allocationMapNumber(editor.querySelector("[data-map-setting-x]")?.value, row.x));
    row.y = Math.round(allocationMapNumber(editor.querySelector("[data-map-setting-y]")?.value, row.y));
    row.w = Math.max(1, Math.round(allocationMapNumber(editor.querySelector("[data-map-setting-w]")?.value, row.w)));
    row.h = Math.max(1, Math.round(allocationMapNumber(editor.querySelector("[data-map-setting-h]")?.value, row.h)));
    row.maxPall = Math.max(0.1, allocationMapRound(editor.querySelector("[data-map-setting-max]")?.value || row.maxPall));
    row.loadDirection = allocationNormalizeMapLoadDirection(row.loadDirection, row);
    rows = sortedMapRows(rows);
    renderEditor();
  }

  function rotateLocationLeft(location) {
    if (!canEdit) return;
    const row = rows.find((item) => item.location === location);
    if (!row) return;
    pushUndoSnapshot();
    const cx = row.x + row.w / 2;
    const cy = row.y + row.h / 2;
    const nextWidth = row.h;
    const nextHeight = row.w;
    const rotatedDirection = allocationRotateMapLoadDirectionLeft(allocationNormalizeMapLoadDirection(row.loadDirection, row));
    row.x = Math.round(cx - nextWidth / 2);
    row.y = Math.round(cy - nextHeight / 2);
    row.w = nextWidth;
    row.h = nextHeight;
    row.loadDirection = allocationNormalizeMapLoadDirection(rotatedDirection, row);
    selectedLocation = row.location;
    selectedLocations = new Set([row.location]);
    statusText = `${row.location}: roterad v\u00e4nster.`;
    renderEditor();
  }

  function rotateLocationFromMapEvent(location) {
    const now = Date.now();
    if (!location || now - lastMapRotationAt < 240) return;
    lastMapRotationAt = now;
    rotateLocationLeft(location);
    focusMapSettingsWorkspace();
  }

  function cycleSelectedLoadDirections() {
    if (!canEdit || !selectedLocations.size) return;
    const picked = selectedRows();
    if (!picked.length) return;
    pushUndoSnapshot();
    picked.forEach((row) => {
      row.loadDirection = allocationNextMapLoadDirection(row.loadDirection, row);
    });
    if (picked.length === 1) {
      statusText = `${picked[0].location}: riktning ${allocationMapLoadDirectionLabel(picked[0].loadDirection)}.`;
    } else {
      statusText = `${picked.length} ytor: riktning bytt.`;
    }
    renderEditor();
  }

  function baseRowForPlacement() {
    return selectedRow() || rows[rows.length - 1] || layout.defaults?.[0] || {
      location: "UTL0",
      x: 0,
      y: 0,
      w: 240,
      h: 80,
      maxPall: 2,
      loadDirection: "right",
    };
  }

  function addLocationRow(locationRow) {
    if (!canEdit || !locationRow || rows.some((row) => row.location === locationRow.location)) return;
    pushUndoSnapshot();
    const base = baseRowForPlacement();
    const direction = editor.querySelector("[data-map-series-direction]")?.value || "right";
    const gap = Math.max(0, Number.parseInt(editor.querySelector("[data-map-series-gap]")?.value, 10) || 20);
    const maxPall = allocationMapRound(locationRow.maxPall || base.maxPall || 2);
    const size = allocationMapLayoutSizeForCapacity(base, maxPall);
    const step = allocationMapLayoutStep(base, direction, gap);
    const draft = {
      location: locationRow.location,
      x: base.x + step.dx,
      y: base.y + step.dy,
      w: size.w,
      h: size.h,
      maxPall,
      loadDirection: allocationNormalizeMapLoadDirection(base.loadDirection, size),
    };
    const placed = allocationMapLayoutAvoidCollision(rows, draft, direction, gap);
    rows = sortedMapRows([...rows, placed]);
    selectedLocation = placed.location;
    selectedLocations = new Set([placed.location]);
    statusText = `${placed.location} tillagd.`;
    renderEditor();
  }

  function addLocationRowAt(locationRow, point) {
    if (!canEdit || !locationRow || rows.some((row) => row.location === locationRow.location)) return;
    pushUndoSnapshot();
    const base = baseRowForPlacement();
    const direction = editor.querySelector("[data-map-series-direction]")?.value || "right";
    const gap = Math.max(0, Number.parseInt(editor.querySelector("[data-map-series-gap]")?.value, 10) || 20);
    const maxPall = allocationMapRound(locationRow.maxPall || base.maxPall || 2);
    const size = allocationMapLayoutSizeForCapacity(
      { ...base, w: allocationMapNumber(locationRow.w, base.w), h: allocationMapNumber(locationRow.h, base.h) },
      maxPall,
    );
    const draft = {
      location: locationRow.location,
      x: Math.round((allocationMapNumber(point?.x, base.x) - size.w / 2) / 10) * 10,
      y: Math.round((allocationMapNumber(point?.y, base.y) - size.h / 2) / 10) * 10,
      w: size.w,
      h: size.h,
      maxPall,
      loadDirection: allocationNormalizeMapLoadDirection(base.loadDirection, size),
    };
    const placed = allocationMapLayoutAvoidCollision(rows, draft, direction, gap);
    rows = sortedMapRows([...rows, placed]);
    selectedLocation = placed.location;
    selectedLocations = new Set([placed.location]);
    statusText = `${placed.location} placerad p\u00e5 kartan.`;
    renderEditor();
  }

  async function saveMapSettings(button) {
    if (!canEdit) return;
    button.disabled = true;
    try {
      const query = allocationMapSettingsQuery({ includeOptions: false });
      const requestedSignature = allocationMapLayoutSaveSignature(rows);
      const response = await allocationJson(`${ALLOCATION_API}/ytgenerering-map-layout${query}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ locations: rows }),
      });
      const savedLayout = normalizeAllocationMapLayout(response);
      if (allocationMapLayoutSaveSignature(savedLayout.locations) !== requestedSignature) {
        throw new Error("Servern bekräftade inte ytkartsändringarna. Ladda om och försök igen.");
      }
      layout = savedLayout;
      rows = [...layout.locations];
      statusText = "Ytkartsinställningar sparade.";
      showToast(statusText, "success", 2500);
      renderEditor();
    } catch (error) {
      button.disabled = false;
      showToast(error.message || "Kunde inte spara ytkartan.", "error", 7000);
    }
  }

  function selectedLocationText() {
    return selectedRows().map((row) => row.location).join("\n");
  }

  function copySelection(mode = "copy") {
    const picked = selectedRows();
    if (!picked.length) return;
    clipboardRows = cloneMapRows(picked);
    void writeClipboardText(selectedLocationText()).catch(() => {});
    statusText = mode === "cut"
      ? `${picked.length} ytor klippta.`
      : `${picked.length} ytor kopierade.`;
    if (mode === "cut" && canEdit) {
      pushUndoSnapshot();
      const cutLocations = new Set(picked.map((row) => row.location));
      rows = rows.filter((row) => !cutLocations.has(row.location));
      selectedLocations = new Set();
      selectedLocation = rows[0]?.location || "";
      if (selectedLocation) selectedLocations.add(selectedLocation);
    }
    renderEditor();
  }

  function pasteSelection() {
    if (!canEdit || !clipboardRows.length) return;
    const free = availableNotMapped({ ignoreSearch: true });
    const existing = new Set(rows.map((row) => row.location));
    const minX = Math.min(...clipboardRows.map((row) => row.x));
    const minY = Math.min(...clipboardRows.map((row) => row.y));
    const base = selectedRow() || rows[rows.length - 1] || clipboardRows[0];
    const additions = [];
    let freeIndex = 0;
    for (const source of clipboardRows) {
      let nextLocation = source.location;
      let nextMaxPall = source.maxPall;
      if (existing.has(nextLocation)) {
        const option = free[freeIndex];
        if (!option) continue;
        freeIndex += 1;
        nextLocation = option.location;
        nextMaxPall = option.maxPall || nextMaxPall;
      }
      const draft = {
        ...source,
        location: nextLocation,
        x: base.x + 40 + (source.x - minX),
        y: base.y + 40 + (source.y - minY),
        maxPall: nextMaxPall,
      };
      const placed = allocationMapLayoutAvoidCollision([...rows, ...additions], draft, "right", 20);
      additions.push(placed);
      existing.add(placed.location);
    }
    if (!additions.length) {
      statusText = "Inga lediga U-platser att klistra in på.";
      renderEditor();
      return;
    }
    pushUndoSnapshot();
    rows = sortedMapRows([...rows, ...additions]);
    selectedLocations = new Set(additions.map((row) => row.location));
    selectedLocation = additions[additions.length - 1].location;
    statusText = `${additions.length} ytor inklistrade.`;
    renderEditor();
  }

  function deleteSelection() {
    if (!canEdit || !selectedLocations.size) return;
    pushUndoSnapshot();
    const deletedCount = selectedLocations.size;
    rows = rows.filter((row) => !selectedLocations.has(row.location));
    selectedLocations = new Set();
    selectedLocation = rows[0]?.location || "";
    if (selectedLocation) selectedLocations.add(selectedLocation);
    statusText = `${deletedCount} ytor borttagna.`;
    renderEditor();
  }

  function undoMapSettings() {
    const snapshot = undoStack.pop();
    if (!snapshot) {
      statusText = "Inget att ångra.";
      renderEditor();
      return;
    }
    statusText = "Ångrat.";
    restoreMapRows(snapshot);
  }

  function moveSelectedRows(dx, dy) {
    if (!canEdit || !selectedLocations.size) return;
    pushUndoSnapshot();
    rows.forEach((row) => {
      if (!selectedLocations.has(row.location)) return;
      row.x = Math.round(row.x + dx);
      row.y = Math.round(row.y + dy);
    });
    statusText = `${selectedLocations.size} ytor flyttade.`;
    renderEditor();
  }

  function selectAllRows() {
    selectedLocations = new Set(rows.map((row) => row.location));
    selectedLocation = rows[rows.length - 1]?.location || "";
    renderEditor();
  }

  function isTextEditingTarget(target) {
    const element = target instanceof Element ? target : null;
    if (!element) return false;
    return Boolean(element.closest("input, textarea, select, [contenteditable='true']"));
  }

  function handleMapSettingsKeydown(event) {
    if (isTextEditingTarget(event.target)) return;
    if (event.allocationMapSettingsHandled) return;
    event.allocationMapSettingsHandled = true;
    const key = String(event.key || "").toLowerCase();
    const shortcut = event.ctrlKey || event.metaKey;
    if (shortcut && key === "c") {
      event.preventDefault();
      copySelection("copy");
      return;
    }
    if (shortcut && key === "x") {
      event.preventDefault();
      copySelection("cut");
      return;
    }
    if (shortcut && key === "v") {
      event.preventDefault();
      pasteSelection();
      return;
    }
    if (shortcut && key === "z") {
      event.preventDefault();
      undoMapSettings();
      return;
    }
    if (shortcut && key === "a") {
      event.preventDefault();
      selectAllRows();
      return;
    }
    if (key === "delete" || key === "backspace") {
      event.preventDefault();
      deleteSelection();
      return;
    }
    const arrowSteps = {
      arrowleft: [-1, 0],
      arrowright: [1, 0],
      arrowup: [0, -1],
      arrowdown: [0, 1],
    };
    const arrow = arrowSteps[key];
    if (arrow) {
      event.preventDefault();
      const step = event.altKey ? 1 : event.shiftKey ? 50 : 10;
      moveSelectedRows(arrow[0] * step, arrow[1] * step);
    }
  }

  function focusMapSettingsWorkspace() {
    editor.querySelector("[data-map-settings-workspace]")?.focus({ preventScroll: true });
  }

  function closeMapSettingsContextMenu() {
    document.querySelector(".allocation-map-settings-context-menu")?.remove();
  }

  function positionMapSettingsContextMenu(menu, event) {
    const workspace = editor.querySelector("[data-map-settings-workspace]") || editor;
    const workspaceRect = workspace.getBoundingClientRect();
    const scaleX = workspaceRect.width > 0 ? workspace.clientWidth / workspaceRect.width : 1;
    const scaleY = workspaceRect.height > 0 ? workspace.clientHeight / workspaceRect.height : scaleX;
    const clickX = (event.clientX - workspaceRect.left) * scaleX;
    const clickY = (event.clientY - workspaceRect.top) * scaleY;
    const padding = 8;
    const maxLeft = Math.max(padding, workspace.clientWidth - menu.offsetWidth - padding);
    const maxTop = Math.max(padding, workspace.clientHeight - menu.offsetHeight - padding);
    menu.style.left = `${Math.max(padding, Math.min(clickX, maxLeft))}px`;
    menu.style.top = `${Math.max(padding, Math.min(clickY, maxTop))}px`;
  }

  function openMapSettingsContextMenu(event, location) {
    if (!canEdit || !location || !rows.some((row) => row.location === location)) return;
    event.preventDefault();
    event.stopPropagation();
    closeMapSettingsContextMenu();
    if (!selectedLocations.has(location)) {
      selectedLocations = new Set([location]);
    }
    selectedLocation = location;
    syncSelectionVisuals();

    const menu = document.createElement("div");
    menu.className = "allocation-map-settings-context-menu";
    menu.style.position = "absolute";
    menu.innerHTML = `<button type="button" data-map-context-direction>Byt riktning</button>`;
    menu.addEventListener("click", (clickEvent) => clickEvent.stopPropagation());
    menu.querySelector("[data-map-context-direction]")?.addEventListener("click", () => {
      closeMapSettingsContextMenu();
      cycleSelectedLoadDirections();
      focusMapSettingsWorkspace();
    });
    const workspace = editor.querySelector("[data-map-settings-workspace]") || editor;
    workspace.appendChild(menu);
    positionMapSettingsContextMenu(menu, event);
    window.setTimeout(() => {
      document.addEventListener("click", closeMapSettingsContextMenu, { once: true });
    }, 0);
  }

  async function toggleMapSettingsFullscreen() {
    const workspace = editor.querySelector("[data-map-settings-workspace]");
    if (!workspace) return;
    try {
      if (document.fullscreenElement === workspace) {
        await document.exitFullscreen?.();
      } else {
        await workspace.requestFullscreen?.();
      }
      focusMapSettingsWorkspace();
    } catch (error) {
      showToast("Kunde inte öppna fullskärm.", "error", 4000);
    }
  }

  const documentKeydownHandler = (event) => {
    if (!editor.isConnected) {
      document.removeEventListener("keydown", documentKeydownHandler, true);
      return;
    }
    handleMapSettingsKeydown(event);
  };
  document.addEventListener("keydown", documentKeydownHandler, true);

  function renderEditor() {
    const shouldRestoreWorkspaceFocus = editor.contains(document.activeElement) && !isTextEditingTarget(document.activeElement);
    pruneSelection();
    const row = selectedRow();
    const pickedCount = selectedLocations.size;
    const nextNumber = allocationMapLayoutNextNumber(rows);
    const current = ensureViewBox();
    const freeLocations = availableNotMapped();
    editor.innerHTML = `
      <div class="allocation-map-settings-workspace" data-map-settings-workspace tabindex="0" aria-keyshortcuts="ArrowUp ArrowDown ArrowLeft ArrowRight Control+C Control+X Control+V Control+Z Delete">
        <div class="allocation-map-settings-toolbar">
          <label><span>Från</span><input type="number" min="1" max="652" step="1" data-map-series-start value="${nextNumber}" ${canEdit ? "" : "disabled"} /></label>
          <label><span>Till</span><input type="number" min="1" max="652" step="1" data-map-series-end value="${nextNumber}" ${canEdit ? "" : "disabled"} /></label>
          <label><span>Riktning</span>
            <select data-map-series-direction ${canEdit ? "" : "disabled"}>
              <option value="right">Höger</option>
              <option value="left">Vänster</option>
              <option value="up">Upp</option>
              <option value="down">Ner</option>
            </select>
          </label>
          <label><span>Gap</span><input type="number" min="0" step="10" data-map-series-gap value="20" ${canEdit ? "" : "disabled"} /></label>
          <label><span>Max pall</span><input type="number" min="0.1" step="0.5" data-map-series-max value="${allocationEscape(row?.maxPall || 2)}" ${canEdit ? "" : "disabled"} /></label>
          <button type="button" data-map-add-series ${canEdit ? "" : "disabled"}>Lägg till serie</button>
          <button type="button" data-map-duplicate ${canEdit && row ? "" : "disabled"}>Lägg till nästa</button>
          <button type="button" data-map-delete ${canEdit && pickedCount ? "" : "disabled"}>Ta bort vald</button>
          <button type="button" data-map-reset-defaults ${canEdit ? "" : "disabled"}>Återställ standard</button>
          <span class="allocation-map-settings-selection" data-map-selection-count>${pickedCount || 0} valda</span>
          <span class="allocation-map-settings-toolbar-spacer"></span>
          <button type="button" data-map-zoom-out>−</button>
          <button type="button" data-map-fit>0</button>
          <button type="button" data-map-zoom-in>+</button>
          ${canEdit ? `<button type="button" class="primary" data-map-save>Spara</button>` : ""}
        </div>
        ${statusText ? `<p class="allocation-status">${allocationEscape(statusText)}</p>` : ""}
        <div class="allocation-map-settings-canvas-grid">
          <div class="allocation-map-settings-canvas">
            <svg class="allocation-map-settings-svg" data-map-settings-svg viewBox="${current.x} ${current.y} ${current.width} ${current.height}" aria-label="Ytkartsinställningar">
              <defs>
                <pattern id="allocation-map-settings-grid" width="80" height="80" patternUnits="userSpaceOnUse">
                  <path d="M 80 0 L 0 0 0 80" fill="none" stroke="#d8dee8" stroke-width="0.8"></path>
                </pattern>
              </defs>
              <rect data-map-pan-surface x="-100000" y="-100000" width="200000" height="200000" fill="url(#allocation-map-settings-grid)"></rect>
              <g data-map-snap-guides class="allocation-map-settings-guide-layer"></g>
              ${rows.map((item) => `
                <g data-map-setting-node="${allocationEscape(item.location)}">
                  <rect class="allocation-map-setting-loc${selectedLocations.has(item.location) ? " is-selected" : ""}" data-map-setting-rect="${allocationEscape(item.location)}" x="${item.x}" y="${item.y}" width="${item.w}" height="${item.h}"></rect>
                  ${allocationRenderMapSettingLabel(item)}
                  ${allocationRenderMapSettingDirectionArrow(item)}
                </g>
              `).join("")}
            </svg>
            <button type="button" class="allocation-map-settings-fullscreen-button" data-map-settings-fullscreen title="Fullskärm" aria-label="Fullskärm">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M4 9V4h5"></path>
                <path d="M20 9V4h-5"></path>
                <path d="M4 15v5h5"></path>
                <path d="M20 15v5h-5"></path>
                <path d="M9 4 4 9"></path>
                <path d="m15 4 5 5"></path>
                <path d="m4 15 5 5"></path>
                <path d="m20 15-5 5"></path>
              </svg>
            </button>
          </div>
          <aside class="allocation-map-settings-side">
            ${row ? `
              <div class="allocation-map-settings-fields">
                <label><span>Yta</span><input data-map-setting-location value="${allocationEscape(row.location)}" ${canEdit ? "" : "disabled"} /></label>
                <label><span>X</span><input type="number" step="10" data-map-setting-x value="${row.x}" ${canEdit ? "" : "disabled"} /></label>
                <label><span>Y</span><input type="number" step="10" data-map-setting-y value="${row.y}" ${canEdit ? "" : "disabled"} /></label>
                <label><span>Bredd</span><input type="number" min="1" step="10" data-map-setting-w value="${row.w}" ${canEdit ? "" : "disabled"} /></label>
                <label><span>Höjd</span><input type="number" min="1" step="10" data-map-setting-h value="${row.h}" ${canEdit ? "" : "disabled"} /></label>
                <label><span>Max pall</span><input type="number" min="0.1" step="0.5" data-map-setting-max value="${row.maxPall}" ${canEdit ? "" : "disabled"} /></label>
              </div>
            ` : `<p class="allocation-muted">Ingen yta vald.</p>`}
            <div class="allocation-map-settings-list-head">
              <strong>Lediga U-platser</strong>
              <span>${availableLocationsLoading ? "..." : `${freeLocations.length}/${availableLocations.length}`}</span>
            </div>
            <input data-map-location-search class="allocation-map-location-search" placeholder="Sök UTL" value="${allocationEscape(editor.querySelector("[data-map-location-search]")?.value || "")}" />
            <div class="allocation-map-settings-list">
              ${availableLocationsLoading
                ? `<p class="allocation-muted">Laddar lediga U-platser...</p>`
                : availableLocationsError
                  ? `<p class="allocation-status error">${allocationEscape(availableLocationsError)}</p>`
                  : freeLocations.map((item) => `
                <button type="button" data-map-add-location="${allocationEscape(item.location)}" draggable="${canEdit ? "true" : "false"}" ${canEdit ? "" : "disabled"}>
                  <span>${allocationEscape(item.location)}</span><small>${allocationEscape(item.maxPall)} pall</small>
                </button>
              `).join("") || `<p class="allocation-muted">Inga lediga U-platser.</p>`}
            </div>
          </aside>
        </div>
      </div>
    `;
    bindEditor();
    if (shouldRestoreWorkspaceFocus) {
      editor.querySelector("[data-map-settings-workspace]")?.focus({ preventScroll: true });
    }
  }

  function bindEditor() {
    const workspace = editor.querySelector("[data-map-settings-workspace]");
    workspace?.addEventListener("keydown", handleMapSettingsKeydown);
    workspace?.addEventListener("pointerdown", () => workspace.focus());
    editor.querySelectorAll("[data-map-setting-rect]").forEach((item) => {
      item.addEventListener("click", (event) => {
        if (event.button === 2) return;
        if (event.detail >= 2 && canEdit) {
          rotateLocationFromMapEvent(item.dataset.mapSettingRect || "");
          event.preventDefault();
          return;
        }
        if (Date.now() < ignoreMapContextClickUntil) return;
        if (ignoreNextMapClick) {
          ignoreNextMapClick = false;
          return;
        }
        const location = item.dataset.mapSettingRect || "";
        setSelection(location, event, { keepExisting: true });
        syncSelectionVisuals();
        focusMapSettingsWorkspace();
      });
      item.addEventListener("dblclick", (event) => {
        if (!canEdit || event.button === 2) return;
        rotateLocationFromMapEvent(item.dataset.mapSettingRect || "");
        event.preventDefault();
      });
    });
    editor.querySelectorAll("[data-map-setting-location], [data-map-setting-x], [data-map-setting-y], [data-map-setting-w], [data-map-setting-h], [data-map-setting-max]").forEach((input) => {
      input.addEventListener("change", updateSelectedFromInputs);
    });
    editor.querySelector("[data-map-location-search]")?.addEventListener("input", renderEditor);
    editor.querySelectorAll("[data-map-add-location]").forEach((button) => {
      button.addEventListener("click", () => addLocationRow(availableLocations.find((row) => row.location === button.dataset.mapAddLocation)));
      button.addEventListener("dragstart", (event) => {
        if (!canEdit || !event.dataTransfer) return;
        const location = button.dataset.mapAddLocation || "";
        event.dataTransfer.effectAllowed = "copy";
        event.dataTransfer.setData(LOCATION_DRAG_TYPE, location);
        event.dataTransfer.setData("text/plain", location);
        button.classList.add("is-dragging");
      });
      button.addEventListener("dragend", () => {
        button.classList.remove("is-dragging");
        editor.querySelector(".allocation-map-settings-canvas")?.classList.remove("is-drop-target");
      });
    });
    editor.querySelector("[data-map-add-series]")?.addEventListener("click", () => {
      const base = baseRowForPlacement();
      const additions = allocationMapLayoutSeriesRows(rows, {
        selectedLocation,
        start: editor.querySelector("[data-map-series-start]")?.value,
        end: editor.querySelector("[data-map-series-end]")?.value,
        direction: editor.querySelector("[data-map-series-direction]")?.value,
        gap: editor.querySelector("[data-map-series-gap]")?.value,
        maxPall: editor.querySelector("[data-map-series-max]")?.value,
        w: base.w,
        h: base.h,
        loadDirection: base.loadDirection,
        availableLocations,
      });
      if (additions.length) {
        pushUndoSnapshot();
        rows = sortedMapRows([...rows, ...additions]);
        selectedLocations = new Set(additions.map((row) => row.location));
        selectedLocation = additions[additions.length - 1].location;
      }
      statusText = additions.length ? `${additions.length} ytor tillagda.` : "Inga lediga U-platser i intervallet.";
      renderEditor();
    });
    editor.querySelector("[data-map-duplicate]")?.addEventListener("click", () => {
      const firstFree = availableNotMapped()[0];
      if (firstFree) addLocationRow(firstFree);
    });
    editor.querySelector("[data-map-delete]")?.addEventListener("click", deleteSelection);
    editor.querySelector("[data-map-reset-defaults]")?.addEventListener("click", () => {
      pushUndoSnapshot();
      rows = [...(layout.defaults || [])];
      selectedLocation = rows[0]?.location || "";
      selectedLocations = selectedLocation ? new Set([selectedLocation]) : new Set();
      fitView();
      statusText = "Standardytor återställda.";
      renderEditor();
    });
    editor.querySelector("[data-map-save]")?.addEventListener("click", (event) => saveMapSettings(event.currentTarget));
    editor.querySelector("[data-map-zoom-in]")?.addEventListener("click", () => zoomView(0.78));
    editor.querySelector("[data-map-zoom-out]")?.addEventListener("click", () => zoomView(1.28));
    editor.querySelector("[data-map-settings-fullscreen]")?.addEventListener("click", toggleMapSettingsFullscreen);
    editor.querySelector("[data-map-fit]")?.addEventListener("click", () => {
      fitView();
      renderEditor();
    });

    const svg = editor.querySelector("[data-map-settings-svg]");
    const canvas = editor.querySelector(".allocation-map-settings-canvas");
    canvas?.addEventListener("dragover", (event) => {
      if (!canEdit || !hasLocationDrag(event)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      canvas.classList.add("is-drop-target");
    });
    canvas?.addEventListener("dragleave", (event) => {
      if (event.relatedTarget && canvas.contains(event.relatedTarget)) return;
      canvas.classList.remove("is-drop-target");
    });
    canvas?.addEventListener("drop", (event) => {
      if (!canEdit || !hasLocationDrag(event) || !svg) return;
      event.preventDefault();
      event.stopPropagation();
      canvas.classList.remove("is-drop-target");
      const location = draggedLocationFromEvent(event);
      const locationRow = availableLocations.find((row) => row.location === location);
      addLocationRowAt(locationRow, svgPointFromClient(svg, event.clientX, event.clientY));
      focusMapSettingsWorkspace();
    });
    svg?.addEventListener("wheel", (event) => {
      event.preventDefault();
      zoomView(event.deltaY < 0 ? 0.88 : 1.12, event);
    }, { passive: false });
    svg?.addEventListener("contextmenu", (event) => {
      const node = event.target.closest?.("[data-map-setting-node]");
      const rect = event.target.closest?.("[data-map-setting-rect]") || node?.querySelector("[data-map-setting-rect]");
      const hitRow = rect ? null : mapSettingRowAtClientPoint(svg, event.clientX, event.clientY);
      const location = rect?.dataset.mapSettingRect || hitRow?.location || "";
      if (!location || !canEdit) return;
      openMapSettingsContextMenu(event, location);
    });
    svg?.addEventListener("dblclick", (event) => {
      const node = event.target.closest?.("[data-map-setting-node]");
      const rect = event.target.closest?.("[data-map-setting-rect]") || node?.querySelector("[data-map-setting-rect]");
      const hitRow = rect ? null : mapSettingRowAtClientPoint(svg, event.clientX, event.clientY);
      const location = rect?.dataset.mapSettingRect || hitRow?.location || "";
      if (!location || !canEdit) return;
      rotateLocationFromMapEvent(location);
      event.preventDefault();
    });
    svg?.addEventListener("mousedown", (event) => {
      if (event.button === 2) ignoreMapContextClickUntil = Date.now() + 600;
    }, true);
    svg?.addEventListener("pointerdown", (event) => {
      if (event.button === 2) {
        ignoreMapContextClickUntil = Date.now() + 600;
        return;
      }
      closeMapSettingsContextMenu();
      const node = event.target.closest?.("[data-map-setting-node]");
      const rect = event.target.closest?.("[data-map-setting-rect]") || node?.querySelector("[data-map-setting-rect]");
      const hitRow = rect ? null : mapSettingRowAtClientPoint(svg, event.clientX, event.clientY);
      const location = rect?.dataset.mapSettingRect || hitRow?.location || "";
      if (location && canEdit) {
        const row = rows.find((item) => item.location === location);
        if (!row) return;
        setSelection(row.location, event, { keepExisting: true });
        syncSelectionVisuals();
        const picked = selectedRows();
        const rects = [...editor.querySelectorAll("[data-map-setting-rect]")];
        drag = {
          items: picked.map((pickedRow) => {
            const pickedRect = rects.find((item) => item.dataset.mapSettingRect === pickedRow.location);
            return {
              row: pickedRow,
              rect: pickedRect,
              label: pickedRect?.closest("[data-map-setting-node]")?.querySelector(".allocation-map-setting-label"),
              arrow: pickedRect?.closest("[data-map-setting-node]")?.querySelector(".allocation-map-setting-direction-arrow"),
              originalX: pickedRow.x,
              originalY: pickedRow.y,
            };
          }),
          startX: event.clientX,
          startY: event.clientY,
          box: svg.getBoundingClientRect(),
          viewBox: { ...ensureViewBox() },
          snapTargets: snapTargetsForDrag(),
          snapshot: cloneMapRows(),
          moved: false,
        };
      } else {
        pan = {
          startX: event.clientX,
          startY: event.clientY,
          box: svg.getBoundingClientRect(),
          viewBox: { ...ensureViewBox() },
        };
      }
      try {
        svg.setPointerCapture?.(event.pointerId);
      } catch (_) {
        // Synthetic browser tests do not always create an active pointer first.
      }
      event.preventDefault();
    });
    svg?.addEventListener("pointermove", (event) => {
      if (drag) {
        const scaleX = drag.viewBox.width / Math.max(1, drag.box.width);
        const scaleY = drag.viewBox.height / Math.max(1, drag.box.height);
        const dx = (event.clientX - drag.startX) * scaleX;
        const dy = (event.clientY - drag.startY) * scaleY;
        const snapped = applySnapToDrag(drag, dx, dy, scaleX, scaleY);
        if (Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > 2) drag.moved = true;
        drag.items.forEach((item) => {
          item.row.x = snapped.snapX
            ? Math.round(item.originalX + snapped.dx)
            : Math.round((item.originalX + snapped.dx) / 10) * 10;
          item.row.y = snapped.snapY
            ? Math.round(item.originalY + snapped.dy)
            : Math.round((item.originalY + snapped.dy) / 10) * 10;
          item.rect?.setAttribute("x", item.row.x);
          item.rect?.setAttribute("y", item.row.y);
          allocationUpdateMapSettingLabelElement(item.label, item.row);
          allocationUpdateMapSettingDirectionArrowElement(item.arrow, item.row);
        });
        return;
      }
      if (pan) {
        const scaleX = pan.viewBox.width / Math.max(1, pan.box.width);
        const scaleY = pan.viewBox.height / Math.max(1, pan.box.height);
        viewBox = {
          ...pan.viewBox,
          x: pan.viewBox.x - (event.clientX - pan.startX) * scaleX,
          y: pan.viewBox.y - (event.clientY - pan.startY) * scaleY,
        };
        setSvgViewBox();
      }
    });
    svg?.addEventListener("pointerup", (event) => {
      try {
        svg.releasePointerCapture?.(event.pointerId);
      } catch (_) {
        // The pointer may already be released in synthetic browser tests.
      }
      const hadDrag = drag;
      drag = null;
      pan = null;
      updateMapSnapGuides([]);
      if (hadDrag?.moved) {
        undoStack.push(hadDrag.snapshot);
        if (undoStack.length > 80) undoStack.shift();
        ignoreNextMapClick = true;
        statusText = `${hadDrag.items.length} ytor flyttade.`;
        renderEditor();
      }
    });
    svg?.addEventListener("pointercancel", () => {
      drag = null;
      pan = null;
      updateMapSnapGuides([]);
      renderEditor();
    });
  }

  fitView();
  renderEditor();
  void loadAvailableLocations();
}


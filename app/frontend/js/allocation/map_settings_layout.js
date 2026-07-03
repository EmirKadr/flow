// Utdelad ur allocation/map_settings.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter map_settings.js via <script>-tagg.

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

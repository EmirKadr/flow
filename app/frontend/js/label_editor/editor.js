(function () {
  const SYMBOLS = {
    check: {
      label: "Check",
      svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    },
    warning: {
      label: "Varning",
      svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 22 20H2Z" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/><path d="M12 8v6M12 17h.01" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/></svg>',
    },
    arrowRight: {
      label: "Pil höger",
      svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h15M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    },
    cross: {
      label: "Kryss",
      svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round"/></svg>',
    },
    box: {
      label: "Kolli",
      svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8 12 4l8 4v9l-8 4-8-4Z" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linejoin="round"/><path d="m4 8 8 4 8-4M12 12v9" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linejoin="round"/></svg>',
    },
    temp: {
      label: "Temperatur",
      svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 14.5V5a3 3 0 1 1 6 0v9.5a5 5 0 1 1-6 0Z" fill="none" stroke="currentColor" stroke-width="2.1"/><path d="M13 7v9" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round"/></svg>',
    },
  };
  const SYMBOL_PICKER_GROUPS = [
    {
      label: "Symboler",
      items: [
        { value: "check", label: SYMBOLS.check.label, svg: SYMBOLS.check.svg },
        { value: "warning", label: SYMBOLS.warning.label, svg: SYMBOLS.warning.svg },
        { value: "arrowRight", label: SYMBOLS.arrowRight.label, svg: SYMBOLS.arrowRight.svg },
        { value: "cross", label: SYMBOLS.cross.label, svg: SYMBOLS.cross.svg },
        { value: "box", label: SYMBOLS.box.label, svg: SYMBOLS.box.svg },
        { value: "temp", label: SYMBOLS.temp.label, svg: SYMBOLS.temp.svg },
      ],
    },
    {
      label: "Lager",
      items: [
        { value: "emoji-package", label: "Paket", glyph: "📦" },
        { value: "emoji-label", label: "Etikett", glyph: "🏷️" },
        { value: "emoji-truck", label: "Lastbil", glyph: "🚚" },
        { value: "emoji-pallet", label: "Pall", glyph: "🧱" },
        { value: "emoji-pin", label: "Plats", glyph: "📍" },
        { value: "emoji-magnifier", label: "Sök", glyph: "🔍" },
        { value: "emoji-lock", label: "Låst", glyph: "🔒" },
        { value: "emoji-unlock", label: "Upplåst", glyph: "🔓" },
      ],
    },
    {
      label: "Status",
      items: [
        { value: "emoji-ok", label: "OK", glyph: "✅" },
        { value: "emoji-no", label: "Nej", glyph: "❌" },
        { value: "emoji-stop", label: "Stopp", glyph: "⛔" },
        { value: "emoji-info", label: "Info", glyph: "ℹ️" },
        { value: "emoji-star", label: "Stjärna", glyph: "⭐" },
        { value: "emoji-fire", label: "Bråttom", glyph: "🔥" },
        { value: "emoji-snow", label: "Kylt", glyph: "❄️" },
        { value: "emoji-clock", label: "Tid", glyph: "⏱️" },
        { value: "emoji-calendar", label: "Datum", glyph: "📅" },
        { value: "emoji-note", label: "Notis", glyph: "📝" },
      ],
    },
    {
      label: "Riktning",
      items: [
        { value: "emoji-up", label: "Upp", glyph: "⬆️" },
        { value: "emoji-down", label: "Ned", glyph: "⬇️" },
        { value: "emoji-left", label: "Vänster", glyph: "⬅️" },
        { value: "emoji-right", label: "Höger", glyph: "➡️" },
        { value: "emoji-turn-left", label: "Sväng vänster", glyph: "↩️" },
        { value: "emoji-turn-right", label: "Sväng höger", glyph: "↪️" },
        { value: "emoji-recycle", label: "Återbruk", glyph: "♻️" },
        { value: "emoji-target", label: "Mål", glyph: "🎯" },
      ],
    },
    {
      label: "Markörer",
      items: [
        { value: "emoji-one", label: "1", glyph: "①" },
        { value: "emoji-two", label: "2", glyph: "②" },
        { value: "emoji-three", label: "3", glyph: "③" },
        { value: "emoji-four", label: "4", glyph: "④" },
        { value: "emoji-five", label: "5", glyph: "⑤" },
        { value: "emoji-plus", label: "Plus", glyph: "➕" },
        { value: "emoji-minus", label: "Minus", glyph: "➖" },
        { value: "emoji-heart", label: "Hjärta", glyph: "❤️" },
      ],
    },
  ];
  const SYMBOL_CHOICES = SYMBOL_PICKER_GROUPS.flatMap((group) => group.items);
  const SYMBOL_CHOICE_BY_VALUE = new Map(SYMBOL_CHOICES.map((choice) => [choice.value, choice]));
  const LABEL_PROFILE_STORAGE_KEY = "flow-label-editor-profiles-v1";
  const LABEL_MIN_WIDTH_MM = 20;
  const LABEL_MAX_WIDTH_MM = 500;
  const LABEL_MIN_HEIGHT_MM = 10;
  const LABEL_MAX_HEIGHT_MM = 500;
  const LABEL_HISTORY_LIMIT = 80;
  const LABEL_PASTE_OFFSET_MM = 4;
  const BUILTIN_LABEL_PROFILES = [
    { id: "label-104x199", name: "Etikett 104 x 199", width: 104, height: 199 },
    { id: "label-100x150", name: "Etikett 100 x 150", width: 100, height: 150 },
    { id: "label-102x152", name: "Etikett 102 x 152", width: 102, height: 152 },
    { id: "a6-portrait", name: "A6 stående", width: 105, height: 148 },
    { id: "a6-landscape", name: "A6 liggande", width: 148, height: 105 },
    { id: "a5-portrait", name: "A5 stående", width: 148, height: 210 },
    { id: "a5-landscape", name: "A5 liggande", width: 210, height: 148 },
    { id: "a4-portrait", name: "A4 stående", width: 210, height: 297 },
    { id: "a4-landscape", name: "A4 liggande", width: 297, height: 210 },
    { id: "a3-portrait", name: "A3 stående", width: 297, height: 420 },
    { id: "a3-landscape", name: "A3 liggande", width: 420, height: 297 },
  ];
  const state = {
    label: { width: 104, height: 199 },
    objects: [],
    selectedId: "",
    scale: 4,
    nextId: 1,
    undoStack: [],
    redoStack: [],
    clipboard: null,
  };
  let suppressInspector = false;

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]
    ));
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, Number(value) || 0));
  }

  function selectedObject() {
    return state.objects.find((item) => item.id === state.selectedId) || null;
  }

  function cloneObject(object) {
    return { ...object };
  }

  function snapshotState() {
    return {
      label: { ...state.label },
      objects: state.objects.map(cloneObject),
      selectedId: state.selectedId,
      nextId: state.nextId,
    };
  }

  function snapshotsEqual(left, right) {
    return JSON.stringify(left) === JSON.stringify(right);
  }

  function pushUndoSnapshot(snapshot = snapshotState()) {
    state.undoStack.push(snapshot);
    if (state.undoStack.length > LABEL_HISTORY_LIMIT) state.undoStack.shift();
    state.redoStack = [];
  }

  function restoreSnapshot(snapshot) {
    state.label = { ...snapshot.label };
    state.objects = snapshot.objects.map(cloneObject);
    state.selectedId = snapshot.selectedId || "";
    state.nextId = Number(snapshot.nextId) || (state.objects.length + 1);
    $("labelWidth").value = state.label.width;
    $("labelHeight").value = state.label.height;
    renderProfileSelect();
    renderCanvas();
  }

  function mmToPx(value) {
    return value * state.scale;
  }

  function objectName(type) {
    return {
      text: "Text",
      qr: "QR",
      code128: "Code128",
      rect: "Rektangel",
      ellipse: "Ellips",
      line: "Linje",
      symbol: "Symbol",
    }[type] || type;
  }

  function track(action, detail = {}) {
    if (typeof window.flowTrack === "function") {
      window.flowTrack("label_editor", {
        control_id: `label-editor-${action}`,
        feature: "labelEditor",
        detail: {
          action,
          object_type: detail.objectType || "",
          object_count: state.objects.length,
          label_width_mm: state.label.width,
          label_height_mm: state.label.height,
        },
      });
    }
  }

  function logInfo(message, kind = "info") {
    if (window.flowLog?.append) window.flowLog.append(message, kind, kind === "error" ? "Fel" : "Etiketter");
  }

  function safeProfile(profile) {
    if (!profile || typeof profile !== "object") return null;
    const width = clamp(profile.width, LABEL_MIN_WIDTH_MM, LABEL_MAX_WIDTH_MM);
    const height = clamp(profile.height, LABEL_MIN_HEIGHT_MM, LABEL_MAX_HEIGHT_MM);
    const name = String(profile.name || "").trim().slice(0, 40);
    const id = String(profile.id || "").trim().slice(0, 80);
    if (!name || !id) return null;
    return { id, name, width, height, custom: true };
  }

  function readCustomProfiles() {
    try {
      const parsed = JSON.parse(localStorage.getItem(LABEL_PROFILE_STORAGE_KEY) || "[]");
      if (!Array.isArray(parsed)) return [];
      const profiles = parsed.map(safeProfile).filter(Boolean);
      return profiles.filter((profile, index, list) => (
        list.findIndex((candidate) => candidate.id === profile.id) === index
      )).slice(0, 30);
    } catch (_error) {
      return [];
    }
  }

  function writeCustomProfiles(profiles) {
    const safeProfiles = profiles.map(safeProfile).filter(Boolean).slice(0, 30);
    try {
      localStorage.setItem(LABEL_PROFILE_STORAGE_KEY, JSON.stringify(safeProfiles));
    } catch (_error) {}
    return safeProfiles;
  }

  function profileValue(profile) {
    return `${profile.custom ? "custom" : "builtin"}:${profile.id}`;
  }

  function allProfiles() {
    return [
      ...BUILTIN_LABEL_PROFILES.map((profile) => ({ ...profile, custom: false })),
      ...readCustomProfiles(),
    ];
  }

  function selectedProfileValue(preferredValue = "") {
    const preferred = profileFromValue(preferredValue);
    if (
      preferred
      && Number(preferred.width) === Number(state.label.width)
      && Number(preferred.height) === Number(state.label.height)
    ) {
      return preferredValue;
    }
    const exact = allProfiles().find((profile) => (
      Number(profile.width) === Number(state.label.width)
      && Number(profile.height) === Number(state.label.height)
    ));
    return exact ? profileValue(exact) : "custom-size";
  }

  function profileFromValue(value) {
    return allProfiles().find((profile) => profileValue(profile) === value) || null;
  }

  function profileNameForCurrentSize() {
    const width = Math.round(state.label.width * 10) / 10;
    const height = Math.round(state.label.height * 10) / 10;
    return `${width} x ${height} mm`;
  }

  function renderProfileSelect(preferredValue = "") {
    const select = $("labelProfileSelect");
    if (!select) return;
    const previousValue = preferredValue || select.value;
    const customProfiles = readCustomProfiles();
    select.innerHTML = `
      <option value="custom-size">Egen storlek</option>
      <optgroup label="Vanliga storlekar">
        ${BUILTIN_LABEL_PROFILES.map((profile) => `<option value="${profileValue(profile)}">${escapeHtml(profile.name)} (${profile.width} x ${profile.height} mm)</option>`).join("")}
      </optgroup>
      ${customProfiles.length ? `
        <optgroup label="Sparade profiler">
          ${customProfiles.map((profile) => `<option value="${profileValue(profile)}">${escapeHtml(profile.name)} (${profile.width} x ${profile.height} mm)</option>`).join("")}
        </optgroup>
      ` : ""}
    `;
    select.value = selectedProfileValue(previousValue);
    const selected = profileFromValue(select.value);
    const deleteButton = $("labelDeleteProfile");
    if (deleteButton) deleteButton.disabled = !selected?.custom;
    const nameInput = $("labelProfileName");
    if (nameInput && document.activeElement !== nameInput) {
      nameInput.value = selected?.custom ? selected.name : profileNameForCurrentSize();
    }
  }

  function applyLabelSize(width, height, options = {}) {
    const previous = snapshotState();
    state.label.width = clamp(width, LABEL_MIN_WIDTH_MM, LABEL_MAX_WIDTH_MM);
    state.label.height = clamp(height, LABEL_MIN_HEIGHT_MM, LABEL_MAX_HEIGHT_MM);
    $("labelWidth").value = state.label.width;
    $("labelHeight").value = state.label.height;
    state.objects.forEach(fitObject);
    if (!options.skipHistory && !snapshotsEqual(previous, snapshotState())) {
      pushUndoSnapshot(previous);
    }
    renderCanvas();
    if (!options.skipProfiles) renderProfileSelect();
  }

  function saveCurrentProfile() {
    const width = clamp($("labelWidth").value, LABEL_MIN_WIDTH_MM, LABEL_MAX_WIDTH_MM);
    const height = clamp($("labelHeight").value, LABEL_MIN_HEIGHT_MM, LABEL_MAX_HEIGHT_MM);
    const rawName = $("labelProfileName").value.trim();
    const name = (rawName || `${width} x ${height} mm`).slice(0, 40);
    const profiles = readCustomProfiles();
    const existingIndex = profiles.findIndex((profile) => profile.name.toLowerCase() === name.toLowerCase());
    const profile = {
      id: existingIndex >= 0 ? profiles[existingIndex].id : `custom-${Date.now()}`,
      name,
      width,
      height,
      custom: true,
    };
    if (existingIndex >= 0) profiles[existingIndex] = profile;
    else profiles.push(profile);
    writeCustomProfiles(profiles);
    applyLabelSize(width, height, { skipProfiles: true });
    renderProfileSelect(profileValue(profile));
    logInfo("Profilen sparades.", "success");
    track("save-profile");
  }

  function deleteSelectedProfile() {
    const profile = profileFromValue($("labelProfileSelect").value);
    if (!profile?.custom) return;
    if (!confirm("Ta bort sparad profil?")) return;
    writeCustomProfiles(readCustomProfiles().filter((candidate) => candidate.id !== profile.id));
    renderProfileSelect();
    logInfo("Profilen togs bort.", "info");
    track("delete-profile");
  }

  function defaultObject(type) {
    const base = {
      id: `label-object-${state.nextId++}`,
      type,
      x: 5,
      y: 5,
      w: 35,
      h: 15,
      value: "",
      color: "#111827",
      fill: "transparent",
      stroke: "#111827",
      strokeWidth: 0.4,
      fontSize: 5,
      symbol: "check",
    };
    if (type === "text") return { ...base, w: 55, h: 12, value: "Text" };
    if (type === "qr") return { ...base, w: 26, h: 26, value: "FLOW" };
    if (type === "code128") return { ...base, w: 72, h: 20, value: "1234567890" };
    if (type === "ellipse") return { ...base, w: 28, h: 18, fill: "#ffffff" };
    if (type === "line") return { ...base, w: 42, h: 4, strokeWidth: 0.8 };
    if (type === "symbol") return { ...base, w: 16, h: 16 };
    return { ...base, w: 34, h: 18, fill: "#ffffff" };
  }

  function fitObject(object) {
    object.w = clamp(object.w, 2, state.label.width);
    object.h = clamp(object.h, 2, state.label.height);
    object.x = clamp(object.x, 0, Math.max(0, state.label.width - object.w));
    object.y = clamp(object.y, 0, Math.max(0, state.label.height - object.h));
    return object;
  }

  function positionElement(element, object) {
    element.style.left = `${mmToPx(object.x)}px`;
    element.style.top = `${mmToPx(object.y)}px`;
    element.style.width = `${mmToPx(object.w)}px`;
    element.style.height = `${mmToPx(object.h)}px`;
  }

  function shapeSvg(object) {
    const strokeWidth = Math.max(0.1, Number(object.strokeWidth) || 0.4);
    const stroke = escapeHtml(object.stroke || object.color || "#111827");
    const fill = escapeHtml(object.fill || "transparent");
    if (object.type === "ellipse") {
      return `<svg viewBox="0 0 100 100" preserveAspectRatio="none"><ellipse cx="50" cy="50" rx="48" ry="48" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth * 4}"/></svg>`;
    }
    if (object.type === "line") {
      return `<svg viewBox="0 0 100 100" preserveAspectRatio="none"><path d="M3 50h94" fill="none" stroke="${stroke}" stroke-width="${strokeWidth * 8}" stroke-linecap="round"/></svg>`;
    }
    return `<svg viewBox="0 0 100 100" preserveAspectRatio="none"><rect x="2" y="2" width="96" height="96" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth * 4}"/></svg>`;
  }

  function symbolChoice(value) {
    return SYMBOL_CHOICE_BY_VALUE.get(value) || SYMBOL_CHOICE_BY_VALUE.get("check");
  }

  function symbolMarkup(object) {
    const choice = symbolChoice(object.symbol);
    if (choice?.svg) return choice.svg;
    const glyph = choice?.glyph || "✓";
    const fontSize = Math.max(10, Math.min(mmToPx(object.w), mmToPx(object.h)) * 0.78);
    return `<span class="label-object-symbol-glyph" style="font-size:${fontSize}px">${escapeHtml(glyph)}</span>`;
  }

  function objectHtml(object) {
    try {
      if (object.type === "qr") return window.FlowLabelBarcodes.qrSvg(object.value, { color: object.color });
      if (object.type === "code128") return window.FlowLabelBarcodes.code128Svg(object.value, { color: object.color });
    } catch (error) {
      return `<div class="label-object-error">${escapeHtml(error.message)}</div>`;
    }
    if (object.type === "text") {
      return `<div class="label-object-text" style="font-size:${mmToPx(object.fontSize)}px;color:${escapeHtml(object.color)};">${escapeHtml(object.value).replace(/\n/g, "<br>")}</div>`;
    }
    if (object.type === "symbol") {
      return `<div class="label-object-symbol" style="color:${escapeHtml(object.color)}">${symbolMarkup(object)}</div>`;
    }
    return shapeSvg(object);
  }

  function updateScale() {
    const workspace = $("labelEditorWorkspace");
    const maxWidth = Math.max(260, (workspace?.clientWidth || 900) - 56);
    const maxHeight = Math.max(220, window.innerHeight - 260);
    state.scale = clamp(Math.min(maxWidth / state.label.width, maxHeight / state.label.height), 1.8, 8);
  }

  function updatePrintSize() {
    let style = $("labelPrintPageStyle");
    if (!style) {
      style = document.createElement("style");
      style.id = "labelPrintPageStyle";
      document.head.appendChild(style);
    }
    style.textContent = `@page { size: ${state.label.width}mm ${state.label.height}mm; margin: 0; }`;
    const canvas = $("labelCanvas");
    if (canvas) {
      canvas.style.setProperty("--label-print-width", `${state.label.width}mm`);
      canvas.style.setProperty("--label-print-height", `${state.label.height}mm`);
    }
  }

  function renderCanvas() {
    updateScale();
    updatePrintSize();
    const canvas = $("labelCanvas");
    if (!canvas) return;
    canvas.style.width = `${mmToPx(state.label.width)}px`;
    canvas.style.height = `${mmToPx(state.label.height)}px`;
    canvas.innerHTML = state.objects.map((object) => `
      <div class="label-object ${object.id === state.selectedId ? "selected" : ""}" data-object-id="${object.id}" data-object-type="${object.type}" role="button" tabindex="0" aria-label="${escapeHtml(objectName(object.type))}">
        ${objectHtml(object)}
      </div>
    `).join("");
    canvas.querySelectorAll(".label-object").forEach((element) => {
      const object = state.objects.find((item) => item.id === element.dataset.objectId);
      if (!object) return;
      positionElement(element, object);
      element.addEventListener("pointerdown", startDragObject);
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        selectObject(object.id);
      });
      element.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectObject(object.id);
        }
      });
    });
    updateInspector();
  }

  function selectObject(id) {
    state.selectedId = id || "";
    renderCanvas();
  }

  function addObject(type, options = {}) {
    if (type === "symbol" && !options.symbol) {
      openSymbolDialog();
      return;
    }
    const object = fitObject(defaultObject(type));
    if (type === "symbol" && options.symbol) object.symbol = options.symbol;
    pushUndoSnapshot();
    state.objects.push(object);
    state.selectedId = object.id;
    renderCanvas();
    logInfo(`${objectName(type)} lades till.`, "success");
    track("add", { objectType: type });
  }

  function updateInspector() {
    if (suppressInspector) return;
    const object = selectedObject();
    const hasObject = Boolean(object);
    const selectedType = object?.type || "";
    $("labelSelectedName").textContent = hasObject ? objectName(selectedType) : "Inget valt";
    document.querySelectorAll("[data-selected-field]").forEach((field) => {
      field.disabled = !hasObject;
    });
    document.querySelectorAll("[data-visible-for]").forEach((group) => {
      const types = group.dataset.visibleFor.split(",");
      group.hidden = !hasObject || !types.includes(selectedType);
    });
    if (!hasObject) return;
    suppressInspector = true;
    const setField = (id, value) => {
      const field = $(id);
      if (document.activeElement !== field) field.value = value;
    };
    setField("labelObjectX", object.x);
    setField("labelObjectY", object.y);
    setField("labelObjectW", object.w);
    setField("labelObjectH", object.h);
    setField("labelObjectValue", object.value || "");
    setField("labelObjectFontSize", object.fontSize || 5);
    setField("labelObjectColor", object.color || "#111827");
    setField("labelObjectFill", object.fill === "transparent" ? "#ffffff" : object.fill || "#ffffff");
    setField("labelObjectStroke", object.stroke || "#111827");
    setField("labelObjectStrokeWidth", object.strokeWidth || 0.4);
    setField("labelObjectSymbol", object.symbol || "check");
    suppressInspector = false;
  }

  function applyInspectorChange() {
    if (suppressInspector) return;
    const object = selectedObject();
    if (!object) return;
    const previous = snapshotState();
    object.x = Number($("labelObjectX").value);
    object.y = Number($("labelObjectY").value);
    object.w = Number($("labelObjectW").value);
    object.h = Number($("labelObjectH").value);
    object.value = $("labelObjectValue").value;
    object.fontSize = Number($("labelObjectFontSize").value) || 5;
    object.color = $("labelObjectColor").value || "#111827";
    object.fill = $("labelObjectFill").value || "#ffffff";
    object.stroke = $("labelObjectStroke").value || "#111827";
    object.strokeWidth = Number($("labelObjectStrokeWidth").value) || 0.4;
    object.symbol = $("labelObjectSymbol").value || "check";
    fitObject(object);
    if (!snapshotsEqual(previous, snapshotState())) {
      pushUndoSnapshot(previous);
    }
    renderCanvas();
  }

  function startDragObject(event) {
    if (event.button !== 0) return;
    const object = state.objects.find((item) => item.id === event.currentTarget.dataset.objectId);
    if (!object) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.focus({ preventScroll: true });
    state.selectedId = object.id;
    const element = event.currentTarget;
    const startX = event.clientX;
    const startY = event.clientY;
    const initial = { x: object.x, y: object.y };
    let moved = false;
    const move = (moveEvent) => {
      if (!moved && Math.hypot(moveEvent.clientX - startX, moveEvent.clientY - startY) > 1) {
        pushUndoSnapshot();
        moved = true;
      }
      object.x = clamp(initial.x + (moveEvent.clientX - startX) / state.scale, 0, state.label.width - object.w);
      object.y = clamp(initial.y + (moveEvent.clientY - startY) / state.scale, 0, state.label.height - object.h);
      positionElement(element, object);
      updateInspector();
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      renderCanvas();
      if (moved) track("move", { objectType: object.type });
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
  }

  function bindInspector() {
    [
      "labelObjectX", "labelObjectY", "labelObjectW", "labelObjectH", "labelObjectValue",
      "labelObjectFontSize", "labelObjectColor", "labelObjectFill", "labelObjectStroke",
      "labelObjectStrokeWidth", "labelObjectSymbol",
    ].forEach((id) => $(id)?.addEventListener("input", applyInspectorChange));
  }

  function setupDimensions() {
    $("labelWidth").value = state.label.width;
    $("labelHeight").value = state.label.height;
    renderProfileSelect();
    const update = () => {
      applyLabelSize($("labelWidth").value, $("labelHeight").value);
      track("resize-label");
    };
    $("labelWidth").addEventListener("change", update);
    $("labelHeight").addEventListener("change", update);
    $("labelProfileSelect").addEventListener("change", (event) => {
      const profile = profileFromValue(event.target.value);
      if (!profile) {
        renderProfileSelect();
        return;
      }
      applyLabelSize(profile.width, profile.height);
      logInfo("Profilen valdes.", "info");
      track("select-profile");
    });
    $("labelSaveProfile").addEventListener("click", saveCurrentProfile);
    $("labelDeleteProfile").addEventListener("click", deleteSelectedProfile);
  }

  function deleteSelected() {
    const object = selectedObject();
    if (!object) return;
    pushUndoSnapshot();
    state.objects = state.objects.filter((item) => item.id !== object.id);
    state.selectedId = "";
    renderCanvas();
    logInfo(`${objectName(object.type)} togs bort.`, "info");
    track("delete", { objectType: object.type });
  }

  function duplicateSelected() {
    const object = selectedObject();
    if (!object) return;
    pushUndoSnapshot();
    const copy = fitObject({ ...object, id: `label-object-${state.nextId++}`, x: object.x + 4, y: object.y + 4 });
    state.objects.push(copy);
    state.selectedId = copy.id;
    renderCanvas();
    logInfo(`${objectName(object.type)} duplicerades.`, "success");
    track("duplicate", { objectType: object.type });
  }

  function copySelected() {
    const object = selectedObject();
    if (!object) return false;
    state.clipboard = cloneObject(object);
    logInfo(`${objectName(object.type)} kopierades.`, "success");
    track("copy", { objectType: object.type });
    return true;
  }

  function cutSelected() {
    const object = selectedObject();
    if (!object) return false;
    state.clipboard = cloneObject(object);
    pushUndoSnapshot();
    state.objects = state.objects.filter((item) => item.id !== object.id);
    state.selectedId = "";
    renderCanvas();
    logInfo(`${objectName(object.type)} klipptes ut.`, "info");
    track("cut", { objectType: object.type });
    return true;
  }

  function pasteClipboard() {
    if (!state.clipboard) return false;
    const source = cloneObject(state.clipboard);
    const anchor = selectedObject() || source;
    pushUndoSnapshot();
    const pasted = fitObject({
      ...source,
      id: `label-object-${state.nextId++}`,
      x: Number(anchor.x || 0) + LABEL_PASTE_OFFSET_MM,
      y: Number(anchor.y || 0) + LABEL_PASTE_OFFSET_MM,
    });
    state.objects.push(pasted);
    state.selectedId = pasted.id;
    renderCanvas();
    logInfo(`${objectName(pasted.type)} klistrades in.`, "success");
    track("paste", { objectType: pasted.type });
    return true;
  }

  function undoLabelAction() {
    const snapshot = state.undoStack.pop();
    if (!snapshot) return false;
    state.redoStack.push(snapshotState());
    if (state.redoStack.length > LABEL_HISTORY_LIMIT) state.redoStack.shift();
    restoreSnapshot(snapshot);
    logInfo("Senaste ändringen ångrades.", "info");
    track("undo");
    return true;
  }

  function redoLabelAction() {
    const snapshot = state.redoStack.pop();
    if (!snapshot) return false;
    state.undoStack.push(snapshotState());
    if (state.undoStack.length > LABEL_HISTORY_LIMIT) state.undoStack.shift();
    restoreSnapshot(snapshot);
    logInfo("Senaste ändringen gjordes om.", "info");
    track("redo");
    return true;
  }

  function clearLabel() {
    if (!state.objects.length) return;
    if (!confirm("Rensa etiketten?")) return;
    pushUndoSnapshot();
    state.objects = [];
    state.selectedId = "";
    renderCanvas();
    logInfo("Etiketten rensades.", "info");
    track("clear");
  }

  function printLabel() {
    state.selectedId = "";
    renderCanvas();
    document.body.classList.add("label-printing");
    logInfo("Utskrift startad.", "success");
    track("print");
    setTimeout(() => window.print(), 60);
  }

  function setupActions() {
    document.querySelectorAll("[data-add-label-object]").forEach((button) => {
      button.addEventListener("click", () => addObject(button.dataset.addLabelObject));
    });
    $("labelDeleteObject").addEventListener("click", deleteSelected);
    $("labelDuplicateObject").addEventListener("click", duplicateSelected);
    $("labelClear").addEventListener("click", clearLabel);
    $("labelPrint").addEventListener("click", printLabel);
    $("labelCanvas").addEventListener("pointerdown", (event) => {
      if (event.target === event.currentTarget) event.currentTarget.focus({ preventScroll: true });
    });
    $("labelCanvas").addEventListener("click", (event) => {
      event.currentTarget.focus({ preventScroll: true });
      selectObject("");
    });
    window.addEventListener("resize", renderCanvas);
    window.addEventListener("afterprint", () => document.body.classList.remove("label-printing"));
  }

  function isTextEditingTarget(target) {
    const element = target instanceof Element ? target : null;
    if (!element) return false;
    return Boolean(element.closest("input, textarea, select, [contenteditable='true']"));
  }

  function isLabelEditorShortcutScope(target) {
    const element = target instanceof Element ? target : document.activeElement;
    if (!element || element === document.body || element === document.documentElement) return true;
    return Boolean(element.closest(".label-editor-page"));
  }

  function handleKeyboardShortcuts(event) {
    if (event.labelEditorHandled || isTextEditingTarget(event.target) || !isLabelEditorShortcutScope(event.target)) return;
    const key = String(event.key || "").toLowerCase();
    const shortcut = event.ctrlKey || event.metaKey;
    if (shortcut && key === "c") {
      if (!selectedObject()) return;
      event.preventDefault();
      event.labelEditorHandled = true;
      copySelected();
      return;
    }
    if (shortcut && key === "x") {
      if (!selectedObject()) return;
      event.preventDefault();
      event.labelEditorHandled = true;
      cutSelected();
      return;
    }
    if (shortcut && key === "v") {
      if (!state.clipboard) return;
      event.preventDefault();
      event.labelEditorHandled = true;
      pasteClipboard();
      return;
    }
    if (shortcut && key === "z") {
      event.preventDefault();
      event.labelEditorHandled = true;
      if (event.shiftKey) redoLabelAction();
      else undoLabelAction();
      return;
    }
    if (shortcut && key === "y") {
      event.preventDefault();
      event.labelEditorHandled = true;
      redoLabelAction();
      return;
    }
    if (key === "delete" || key === "backspace") {
      event.preventDefault();
      event.labelEditorHandled = true;
      deleteSelected();
    }
  }

  function setupKeyboardShortcuts() {
    document.addEventListener("keydown", handleKeyboardShortcuts);
  }

  function setupSymbolOptions() {
    $("labelObjectSymbol").innerHTML = SYMBOL_PICKER_GROUPS
      .map((group) => `
        <optgroup label="${escapeHtml(group.label)}">
          ${group.items.map((choice) => `<option value="${escapeHtml(choice.value)}">${escapeHtml(choice.label)}</option>`).join("")}
        </optgroup>
      `)
      .join("");
  }

  function symbolChoiceButton(choice) {
    const preview = choice.svg
      ? `<span class="label-symbol-choice-mark label-symbol-choice-svg">${choice.svg}</span>`
      : `<span class="label-symbol-choice-mark label-symbol-choice-emoji">${escapeHtml(choice.glyph || "")}</span>`;
    return `
      <button type="button" class="label-symbol-choice" data-symbol-value="${escapeHtml(choice.value)}" aria-label="${escapeHtml(choice.label)}">
        ${preview}
        <span class="label-symbol-choice-label">${escapeHtml(choice.label)}</span>
      </button>
    `;
  }

  function openSymbolDialog() {
    document.querySelector(".label-symbol-picker-backdrop")?.remove();
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop label-symbol-picker-backdrop";
    backdrop.innerHTML = `
      <div class="modal wide label-symbol-picker" role="dialog" aria-modal="true" aria-labelledby="labelSymbolPickerTitle">
        <div class="label-symbol-picker-head">
          <h2 id="labelSymbolPickerTitle">Välj symbol</h2>
          <button type="button" class="label-symbol-picker-close" aria-label="Stäng">×</button>
        </div>
        <div class="label-symbol-picker-groups">
          ${SYMBOL_PICKER_GROUPS.map((group) => `
            <section class="label-symbol-picker-group" aria-label="${escapeHtml(group.label)}">
              <h3>${escapeHtml(group.label)}</h3>
              <div class="label-symbol-picker-grid">
                ${group.items.map(symbolChoiceButton).join("")}
              </div>
            </section>
          `).join("")}
        </div>
      </div>
    `;
    const close = () => {
      document.removeEventListener("keydown", handleEscape);
      backdrop.remove();
    };
    const choose = (value) => {
      close();
      addObject("symbol", { symbol: value });
    };
    const handleEscape = (event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      close();
    };
    backdrop.querySelector(".label-symbol-picker-close")?.addEventListener("click", close);
    backdrop.querySelectorAll("[data-symbol-value]").forEach((button) => {
      button.addEventListener("click", () => choose(button.dataset.symbolValue || "check"));
    });
    document.addEventListener("keydown", handleEscape);
    document.body.appendChild(backdrop);
    backdrop.querySelector("[data-symbol-value]")?.focus({ preventScroll: true });
    track("open-symbol-picker");
  }

  async function boot() {
    const user = await initPage("labelEditor");
    if (!user) return;
    setupSymbolOptions();
    setupDimensions();
    bindInspector();
    setupActions();
    setupKeyboardShortcuts();
    const object = fitObject(defaultObject("text"));
    state.objects.push(object);
    state.selectedId = object.id;
    renderCanvas();
  }

  boot();
})();

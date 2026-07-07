// @ts-check
(function () {
  const LABEL_DESIGN_STORAGE_KEY = "flow-label-editor-designs-v1";
  const LABEL_DESIGN_LIMIT = 20;
  const LABEL_DESIGN_OBJECT_LIMIT = 400;
  const LABEL_DESIGN_VALUE_MAX_LENGTH = 2000;
  const LABEL_DESIGN_DATA_URL_MAX_LENGTH = 4000000;
  const LABEL_DESIGN_OBJECT_TYPES = [
    "text", "qr", "code128", "rect", "ellipse", "line", "symbol",
    "drawing", "eraser", "paintFill", "background",
  ];

  function createLabelDesigns(deps) {
    const {
      $, state, backgroundObjectId, clamp, fitObject, pushUndoSnapshot,
      renderCanvas, renderProfileSelect, logInfo, track, escapeHtml, limits,
    } = deps;

    function safeText(value, maxLength) {
      return String(value ?? "").slice(0, maxLength);
    }

    function safeDesignObject(object) {
      if (!object || typeof object !== "object") return null;
      const type = LABEL_DESIGN_OBJECT_TYPES.includes(object.type) ? object.type : "";
      if (!type) return null;
      const safe = {
        type,
        x: Number(object.x) || 0,
        y: Number(object.y) || 0,
        w: Number(object.w) || 0,
        h: Number(object.h) || 0,
        value: safeText(object.value, LABEL_DESIGN_VALUE_MAX_LENGTH),
        color: safeText(object.color, 40),
        fill: safeText(object.fill, 40),
        stroke: safeText(object.stroke, 40),
        strokeWidth: Number(object.strokeWidth) || 0.4,
        fontSize: Number(object.fontSize) || 5,
        symbol: safeText(object.symbol, 80),
      };
      if (Array.isArray(object.points)) {
        safe.points = object.points.slice(0, 4000).map((point) => ({
          x: Number(point?.x) || 0,
          y: Number(point?.y) || 0,
        }));
      }
      const dataUrl = safeText(object.dataUrl, LABEL_DESIGN_DATA_URL_MAX_LENGTH);
      if (dataUrl.startsWith("data:image/")) safe.dataUrl = dataUrl;
      if (type === "paintFill" && !safe.dataUrl) return null;
      return safe;
    }

    function safeDesign(design) {
      if (!design || typeof design !== "object") return null;
      const id = safeText(design.id, 80).trim();
      const name = safeText(design.name, 40).trim();
      if (!id || !name) return null;
      return {
        id,
        name,
        width: clamp(design.width, limits.minWidth, limits.maxWidth),
        height: clamp(design.height, limits.minHeight, limits.maxHeight),
        objects: (Array.isArray(design.objects) ? design.objects : [])
          .map(safeDesignObject)
          .filter(Boolean)
          .slice(0, LABEL_DESIGN_OBJECT_LIMIT),
      };
    }

    function readDesigns() {
      try {
        const parsed = JSON.parse(localStorage.getItem(LABEL_DESIGN_STORAGE_KEY) || "[]");
        if (!Array.isArray(parsed)) return [];
        return parsed.map(safeDesign).filter(Boolean).filter((design, index, list) => (
          list.findIndex((candidate) => candidate.id === design.id) === index
        )).slice(0, LABEL_DESIGN_LIMIT);
      } catch (_error) {
        return [];
      }
    }

    function writeDesigns(designs) {
      const safeDesigns = designs.map(safeDesign).filter(Boolean).slice(0, LABEL_DESIGN_LIMIT);
      try {
        localStorage.setItem(LABEL_DESIGN_STORAGE_KEY, JSON.stringify(safeDesigns));
        return true;
      } catch (_error) {
        return false;
      }
    }

    function renderDesignSelect(preferredId = "") {
      const select = $("labelDesignSelect");
      if (!select) return;
      const previous = preferredId || select.value;
      const designs = readDesigns();
      select.innerHTML = `
        <option value="">Välj etikettprofil…</option>
        ${designs.map((design) => `<option value="${escapeHtml(design.id)}">${escapeHtml(design.name)} (${design.width} x ${design.height} mm)</option>`).join("")}
      `;
      select.value = designs.some((design) => design.id === previous) ? previous : "";
      const deleteButton = $("labelDeleteDesign");
      if (deleteButton) deleteButton.disabled = !select.value;
    }

    function saveCurrentDesign() {
      const designs = readDesigns();
      const selected = designs.find((design) => design.id === $("labelDesignSelect")?.value) || null;
      const defaultName = selected?.name || `Etikett ${designs.length + 1}`;
      const input = prompt("Namn på etikettprofilen:", defaultName);
      if (input === null) return;
      const name = safeText(input, 40).trim() || defaultName;
      const existingIndex = designs.findIndex((design) => design.name.toLowerCase() === name.toLowerCase());
      const design = safeDesign({
        id: existingIndex >= 0 ? designs[existingIndex].id : `design-${Date.now()}`,
        name,
        width: state.label.width,
        height: state.label.height,
        objects: state.objects,
      });
      if (!design) return;
      if (existingIndex >= 0) designs[existingIndex] = design;
      else designs.push(design);
      if (designs.length > LABEL_DESIGN_LIMIT) {
        logInfo(`Max ${LABEL_DESIGN_LIMIT} etikettprofiler kan sparas. Ta bort en profil och försök igen.`, "error");
        return;
      }
      if (!writeDesigns(designs)) {
        logInfo("Etikettprofilen kunde inte sparas – webbläsarens lokala lagring är full. Ta bort en profil och försök igen.", "error");
        return;
      }
      renderDesignSelect(design.id);
      logInfo(`Etikettprofilen "${design.name}" sparades.`, "success");
      track("save-design");
    }

    function loadDesign(id) {
      const design = readDesigns().find((candidate) => candidate.id === id);
      if (!design) return;
      pushUndoSnapshot();
      state.label.width = design.width;
      state.label.height = design.height;
      $("labelWidth").value = design.width;
      $("labelHeight").value = design.height;
      state.objects = design.objects.map((object) => fitObject({
        ...object,
        id: object.type === "background" ? backgroundObjectId : `label-object-${state.nextId++}`,
      }));
      state.selectedId = "";
      renderCanvas();
      renderProfileSelect();
      logInfo(`Etikettprofilen "${design.name}" laddades. Ångra med Ctrl+Z.`, "success");
      track("load-design");
    }

    function deleteSelectedDesign() {
      const design = readDesigns().find((candidate) => candidate.id === $("labelDesignSelect")?.value);
      if (!design) return;
      if (!confirm(`Ta bort etikettprofilen "${design.name}"?`)) return;
      writeDesigns(readDesigns().filter((candidate) => candidate.id !== design.id));
      renderDesignSelect();
      logInfo("Etikettprofilen togs bort.", "info");
      track("delete-design");
    }

    function setupDesigns() {
      renderDesignSelect();
      $("labelDesignSelect")?.addEventListener("change", (event) => {
        const id = /** @type {HTMLSelectElement} */ (event.target).value;
        const deleteButton = $("labelDeleteDesign");
        if (deleteButton) deleteButton.disabled = !id;
        if (id) loadDesign(id);
      });
      $("labelSaveDesign")?.addEventListener("click", saveCurrentDesign);
      $("labelDeleteDesign")?.addEventListener("click", deleteSelectedDesign);
    }

    return { setupDesigns, renderDesignSelect };
  }

  window.FlowLabelDesigns = { createLabelDesigns };
})();

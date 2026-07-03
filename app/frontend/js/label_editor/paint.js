(function () {
  const PAINT_FILL_RASTER_SCALE = 4;
  const PAINT_FILL_MAX_PIXELS = 2200000;
  const PAINT_FILL_BOUNDARY_ALPHA = 24;
  const PAINT_FILL_MIN_REGION_PIXELS = 6;

  function createPaintTools(deps) {
    const {
      $, state, backgroundObjectId, clamp, positionElement, drawingSvg, fitObject,
      snapshotState, pushUndoSnapshot, renderCanvas, track,
    } = deps;

    function readPaintState() {
      const color = $("labelPaintColor")?.value || state.paintColor || "#111827";
      const size = clamp($("labelPaintSize")?.value || state.paintSize, 0.2, 20);
      state.paintColor = color;
      state.paintSize = size;
      return { color, size };
    }

    function labelBackgroundColor() {
      return state.objects.find((item) => item.id === backgroundObjectId)?.fill || "#ffffff";
    }

    function colorToRgb(color) {
      const value = String(color || "").trim();
      const short = /^#([0-9a-f]{3})$/i.exec(value);
      if (short) {
        return {
          r: parseInt(short[1][0] + short[1][0], 16),
          g: parseInt(short[1][1] + short[1][1], 16),
          b: parseInt(short[1][2] + short[1][2], 16),
        };
      }
      const full = /^#([0-9a-f]{6})$/i.exec(value);
      if (full) {
        return {
          r: parseInt(full[1].slice(0, 2), 16),
          g: parseInt(full[1].slice(2, 4), 16),
          b: parseInt(full[1].slice(4, 6), 16),
        };
      }
      return { r: 17, g: 24, b: 39 };
    }

    function fillRasterMetrics() {
      const widthMm = Math.max(1, Number(state.label.width) || 1);
      const heightMm = Math.max(1, Number(state.label.height) || 1);
      const maxScale = Math.sqrt(PAINT_FILL_MAX_PIXELS / (widthMm * heightMm));
      const scale = Math.max(1.5, Math.min(PAINT_FILL_RASTER_SCALE, maxScale));
      return {
        scale,
        width: Math.max(1, Math.ceil(widthMm * scale)),
        height: Math.max(1, Math.ceil(heightMm * scale)),
      };
    }

    function drawStrokeBoundary(ctx, object, scale) {
      const points = Array.isArray(object.points) ? object.points : [];
      if (!points.length) return;
      const strokeWidth = Math.max(2, ((Number(object.strokeWidth) || state.paintSize || 1.2) * scale) + 1);
      ctx.save();
      ctx.globalCompositeOperation = object.type === "eraser" ? "destination-out" : "source-over";
      ctx.strokeStyle = "#000000";
      ctx.fillStyle = "#000000";
      ctx.lineWidth = strokeWidth;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.beginPath();
      if (points.length === 1) {
        ctx.arc(points[0].x * scale, points[0].y * scale, strokeWidth / 2, 0, Math.PI * 2);
        ctx.fill();
      } else {
        points.forEach((point, index) => {
          const x = point.x * scale;
          const y = point.y * scale;
          if (index === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();
      }
      ctx.restore();
    }

    function paintBoundaryCanvas(metrics) {
      const canvas = document.createElement("canvas");
      canvas.width = metrics.width;
      canvas.height = metrics.height;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return null;
      state.objects.forEach((object) => {
        if (object.type === "drawing" || object.type === "eraser") {
          drawStrokeBoundary(ctx, object, metrics.scale);
        }
      });
      return canvas;
    }

    function createFloodFillDataUrl(point, color) {
      if (!state.objects.some((object) => object.type === "drawing")) return null;
      const metrics = fillRasterMetrics();
      const boundary = paintBoundaryCanvas(metrics);
      if (!boundary) return null;
      const boundaryCtx = boundary.getContext("2d", { willReadFrequently: true });
      if (!boundaryCtx) return null;
      const width = metrics.width;
      const height = metrics.height;
      const startX = clamp(Math.floor(point.x * metrics.scale), 0, width - 1);
      const startY = clamp(Math.floor(point.y * metrics.scale), 0, height - 1);
      const startIndex = startY * width + startX;
      const boundaryData = boundaryCtx.getImageData(0, 0, width, height).data;
      if (boundaryData[(startIndex * 4) + 3] > PAINT_FILL_BOUNDARY_ALPHA) return null;

      const total = width * height;
      const queue = new Int32Array(total);
      const visited = new Uint8Array(total);
      let head = 0;
      let tail = 0;
      let count = 0;
      let touchesEdge = false;
      queue[tail++] = startIndex;
      visited[startIndex] = 1;

      const enqueue = (index) => {
        if (visited[index] || boundaryData[(index * 4) + 3] > PAINT_FILL_BOUNDARY_ALPHA) return;
        visited[index] = 1;
        queue[tail++] = index;
      };

      while (head < tail) {
        const index = queue[head++];
        const x = index % width;
        const y = (index - x) / width;
        count += 1;
        if (x === 0 || y === 0 || x === width - 1 || y === height - 1) touchesEdge = true;
        if (x > 0) enqueue(index - 1);
        if (x < width - 1) enqueue(index + 1);
        if (y > 0) enqueue(index - width);
        if (y < height - 1) enqueue(index + width);
      }

      if (touchesEdge || count < PAINT_FILL_MIN_REGION_PIXELS) return null;

      const fillCanvas = document.createElement("canvas");
      fillCanvas.width = width;
      fillCanvas.height = height;
      const fillCtx = fillCanvas.getContext("2d");
      if (!fillCtx) return null;
      const fillImage = fillCtx.createImageData(width, height);
      const rgb = colorToRgb(color);
      for (let index = 0; index < total; index += 1) {
        if (!visited[index]) continue;
        const offset = index * 4;
        fillImage.data[offset] = rgb.r;
        fillImage.data[offset + 1] = rgb.g;
        fillImage.data[offset + 2] = rgb.b;
        fillImage.data[offset + 3] = 255;
      }
      fillCtx.putImageData(fillImage, 0, 0);
      return {
        dataUrl: fillCanvas.toDataURL("image/png"),
        width,
        height,
      };
    }

    function insertPaintFillObject(object) {
      const insertAt = state.objects.findIndex((item) => item.type !== "background" && item.type !== "paintFill");
      if (insertAt === -1) state.objects.push(object);
      else state.objects.splice(insertAt, 0, object);
    }

    function fillClosedRegion(point, color) {
      const region = createFloodFillDataUrl(point, color);
      if (!region) return false;
      const previous = snapshotState();
      const object = fitObject({
        id: `label-object-${state.nextId++}`,
        type: "paintFill",
        x: 0,
        y: 0,
        w: state.label.width,
        h: state.label.height,
        dataUrl: region.dataUrl,
        rasterWidth: region.width,
        rasterHeight: region.height,
        fill: color,
        color,
        stroke: "transparent",
        strokeWidth: 0,
      });
      insertPaintFillObject(object);
      state.selectedId = "";
      pushUndoSnapshot(previous);
      renderCanvas();
      track("fill-region");
      return true;
    }

    function setPaintTool(tool) {
      state.paintTool = ["select", "pencil", "fill", "eraser"].includes(tool) ? tool : "select";
      document.querySelectorAll("[data-paint-tool]").forEach((button) => {
        const active = button.dataset.paintTool === state.paintTool;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
      renderCanvas();
    }

    function canvasPointFromEvent(event) {
      const canvas = $("labelCanvas");
      const rect = canvas.getBoundingClientRect();
      return {
        x: clamp((event.clientX - rect.left) / state.scale, 0, state.label.width),
        y: clamp((event.clientY - rect.top) / state.scale, 0, state.label.height),
      };
    }

    function appendStrokePoint(points, point) {
      const previous = points[points.length - 1];
      if (previous && Math.hypot(point.x - previous.x, point.y - previous.y) < 0.25) return;
      points.push(point);
    }

    function previewPaintStroke(object) {
      let preview = $("labelPaintPreview");
      const canvas = $("labelCanvas");
      if (!preview) {
        preview = document.createElement("div");
        preview.id = "labelPaintPreview";
        preview.className = "label-object label-paint-preview label-object-noninteractive";
        canvas.appendChild(preview);
      }
      positionElement(preview, object);
      preview.innerHTML = drawingSvg(object);
    }

    function removePaintPreview() {
      $("labelPaintPreview")?.remove();
    }

    function startPaintStroke(event) {
      const isEraser = state.paintTool === "eraser";
      const { color, size } = readPaintState();
      const points = [];
      const object = fitObject({
        id: `label-object-${state.nextId++}`,
        type: isEraser ? "eraser" : "drawing",
        x: 0,
        y: 0,
        w: state.label.width,
        h: state.label.height,
        points,
        color: isEraser ? labelBackgroundColor() : color,
        stroke: isEraser ? labelBackgroundColor() : color,
        strokeWidth: isEraser ? Math.max(1.2, size * 2.2) : size,
      });
      const previous = snapshotState();
      appendStrokePoint(points, canvasPointFromEvent(event));
      previewPaintStroke(object);

      const move = (moveEvent) => {
        moveEvent.preventDefault();
        appendStrokePoint(points, canvasPointFromEvent(moveEvent));
        previewPaintStroke(object);
      };
      const stop = (upEvent) => {
        upEvent?.preventDefault?.();
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", stop);
        removePaintPreview();
        if (points.length) {
          pushUndoSnapshot(previous);
          state.objects.push(object);
          state.selectedId = "";
          renderCanvas();
          track(isEraser ? "erase" : "draw");
        } else {
          state.nextId = Math.max(1, state.nextId - 1);
        }
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", stop, { once: true });
    }

    function fillBackground(color) {
      const previous = snapshotState();
      let object = state.objects.find((item) => item.id === backgroundObjectId);
      if (object && object.fill === color) return false;
      if (!object) {
        object = {
          id: backgroundObjectId,
          type: "background",
          x: 0,
          y: 0,
          w: state.label.width,
          h: state.label.height,
          fill: color,
          stroke: "transparent",
          strokeWidth: 0,
          color,
        };
        state.objects.unshift(object);
      } else {
        object.fill = color;
        object.color = color;
      }
      fitObject(object);
      pushUndoSnapshot(previous);
      renderCanvas();
      track("fill-background");
      return true;
    }

    function fillObject(object, color) {
      const previous = snapshotState();
      if (object.type === "rect" || object.type === "ellipse") {
        if (object.fill === color) return false;
        object.fill = color;
      } else if (object.type === "line" || object.type === "drawing" || object.type === "eraser") {
        if (object.color === color && object.stroke === color) return false;
        object.color = color;
        object.stroke = color;
      } else {
        if (object.color === color) return false;
        object.color = color;
      }
      pushUndoSnapshot(previous);
      renderCanvas();
      track("fill-object", { objectType: object.type });
      return true;
    }

    function applyPaintFill(event) {
      const { color } = readPaintState();
      const objectElement = event.target instanceof Element ? event.target.closest(".label-object") : null;
      const object = objectElement
        ? state.objects.find((item) => item.id === objectElement.dataset.objectId)
        : null;
      if (object && object.type !== "background") {
        fillObject(object, color);
        return;
      }
      if (fillClosedRegion(canvasPointFromEvent(event), color)) return;
      fillBackground(color);
    }

    function handlePaintPointerDown(event) {
      if (state.paintTool === "select" || event.button !== 0) return;
      const canvas = $("labelCanvas");
      if (!canvas || !canvas.contains(event.target)) return;
      event.preventDefault();
      event.stopPropagation();
      canvas.focus({ preventScroll: true });
      state.selectedId = "";
      if (state.paintTool === "fill") {
        applyPaintFill(event);
        return;
      }
      startPaintStroke(event);
    }

    function setupPaintTools() {
      document.querySelectorAll("[data-paint-tool]").forEach((button) => {
        button.addEventListener("click", () => setPaintTool(button.dataset.paintTool));
      });
      $("labelPaintColor")?.addEventListener("input", readPaintState);
      $("labelPaintSize")?.addEventListener("input", readPaintState);
      readPaintState();
      setPaintTool(state.paintTool);
    }

    return {
      handlePaintPointerDown,
      setupPaintTools,
    };
  }

  window.FlowLabelPaint = { createPaintTools };
})();

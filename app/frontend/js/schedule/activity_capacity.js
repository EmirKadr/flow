function formatActivityCapacityValue(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "";
  if (number >= 10) return String(Math.round(number));
  return number.toFixed(1).replace(".", ",").replace(",0", "");
}

function formatActivityCapacityHours(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "";
  if (number >= 10) return String(Math.round(number));
  return number.toFixed(1).replace(".", ",").replace(",0", "");
}

function activitySupportsCapacity(activityId) {
  const activity = activityById(activityId);
  if (!activity || String(activity.category || "") === "absence") return false;
  return String(activity.kpi_process_name || "").trim().length > 0;
}

function activityCapacityHoverKey(personId, activityId) {
  return `${scheduleScopeKey()}|${state.year}|${state.week}|${state.weekday}|${personId}|${activityId}`;
}

function activityCapacityCellUrl(personId, activityId) {
  const params = new URLSearchParams({
    year: String(state.year),
    week: String(state.week),
    weekday: String(state.weekday),
    person_id: String(personId),
    activity_id: String(activityId),
  });
  return `/api/schedule/activity-capacity/cell?${params.toString()}`;
}

function setActivityCapacityCache(key, payload) {
  activityCapacityState.cache.set(key, payload);
  while (activityCapacityState.cache.size > SCHEDULE_ACTIVITY_CAPACITY_CACHE_LIMIT) {
    const firstKey = activityCapacityState.cache.keys().next().value;
    activityCapacityState.cache.delete(firstKey);
  }
}

function ensureActivityCapacityTooltip() {
  if (activityCapacityState.tooltip) return activityCapacityState.tooltip;
  const tooltip = document.createElement("div");
  tooltip.className = "schedule-capacity-tooltip";
  tooltip.setAttribute("role", "status");
  tooltip.hidden = true;
  document.body.appendChild(tooltip);
  activityCapacityState.tooltip = tooltip;
  return tooltip;
}

function activityCapacityEmptyText(reason) {
  if (reason === "activity_hidden") return "Aktiviteten är inte vald för historiskt snitt.";
  if (reason === "activity_without_kpi") return "Aktiviteten saknar KPI-process.";
  if (reason === "person_missing") return "Personen saknar historikunderlag.";
  return "Inget historiskt snitt hittades.";
}

function positionActivityCapacityTooltip(target) {
  const tooltip = ensureActivityCapacityTooltip();
  if (!target || tooltip.hidden) return;
  const rect = target.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1024;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 768;
  const left = Math.min(
    viewportWidth - 12 - tooltipRect.width / 2,
    Math.max(12 + tooltipRect.width / 2, rect.left + rect.width / 2),
  );
  const preferTop = rect.bottom + 10 + tooltipRect.height > viewportHeight && rect.top - tooltipRect.height - 10 > 0;
  const top = preferTop ? rect.top - tooltipRect.height - 10 : rect.bottom + 10;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${Math.max(8, top)}px`;
}

function renderActivityCapacityTooltip(target, payload) {
  const tooltip = ensureActivityCapacityTooltip();
  tooltip.replaceChildren();
  tooltip.classList.toggle("is-error", payload.status === "error");
  tooltip.classList.toggle("is-empty", payload.status === "empty");

  const title = document.createElement("div");
  title.className = "schedule-capacity-tooltip-title";
  title.textContent = payload.title || "Historiskt snitt";
  tooltip.appendChild(title);

  const value = document.createElement("div");
  value.className = "schedule-capacity-tooltip-value";
  value.textContent = payload.value || "";
  tooltip.appendChild(value);

  if (payload.meta) {
    const meta = document.createElement("div");
    meta.className = "schedule-capacity-tooltip-meta";
    meta.textContent = payload.meta;
    tooltip.appendChild(meta);
  }

  tooltip.hidden = false;
  positionActivityCapacityTooltip(target);
}

function activityCapacityTooltipPayload(result, personId, activityId) {
  const person = personById(personId);
  const activity = activityById(activityId);
  const title = `${person?.name || "Person"} · ${activity?.label || result?.activity_label || "Aktivitet"}`;
  const capacity = result?.capacity || null;
  const value = formatActivityCapacityValue(capacity?.value_per_hour);
  if (!capacity || !value) {
    return {
      status: "empty",
      title,
      value: activityCapacityEmptyText(result?.reason),
      meta: "",
    };
  }
  const unit = capacity.unit || "enheter";
  const hours = formatActivityCapacityHours(capacity.hours);
  return {
    status: "ok",
    title,
    value: `${value} ${unit}/timme`,
    meta: hours ? `Baserat på ${hours} h historik` : "",
  };
}

function hideActivityCapacityTooltip({ abort = true } = {}) {
  if (activityCapacityState.timer) {
    clearTimeout(activityCapacityState.timer);
    activityCapacityState.timer = null;
  }
  activityCapacityState.target = null;
  activityCapacityState.cacheKey = "";
  if (abort) {
    activityCapacityState.controller?.abort();
    activityCapacityState.controller = null;
  }
  if (activityCapacityState.tooltip) {
    activityCapacityState.tooltip.hidden = true;
  }
}

async function loadActivityCapacityTooltip(target, personId, activityId, cacheKey) {
  const cached = activityCapacityState.cache.get(cacheKey);
  if (cached) {
    renderActivityCapacityTooltip(target, cached);
    return;
  }

  renderActivityCapacityTooltip(target, {
    status: "loading",
    title: `${personById(personId)?.name || "Person"} · ${activityLabel(activityId) || "Aktivitet"}`,
    value: "Hämtar historiskt snitt...",
    meta: "",
  });

  const requestSeq = ++activityCapacityState.requestSeq;
  activityCapacityState.controller?.abort();
  const controller = new AbortController();
  activityCapacityState.controller = controller;

  try {
    const result = await api.get(activityCapacityCellUrl(personId, activityId), {
      signal: controller.signal,
      skipCache: true,
    });
    const payload = activityCapacityTooltipPayload(result, personId, activityId);
    setActivityCapacityCache(cacheKey, payload);
    if (
      controller.signal.aborted
      || requestSeq !== activityCapacityState.requestSeq
      || activityCapacityState.cacheKey !== cacheKey
    ) return;
    renderActivityCapacityTooltip(target, payload);
  } catch (error) {
    if (error?.name === "AbortError") return;
    if (requestSeq !== activityCapacityState.requestSeq || activityCapacityState.cacheKey !== cacheKey) return;
    renderActivityCapacityTooltip(target, {
      status: "error",
      title: `${personById(personId)?.name || "Person"} · ${activityLabel(activityId) || "Aktivitet"}`,
      value: error.message || "Kunde inte hämta historiskt snitt.",
      meta: "",
    });
  } finally {
    if (activityCapacityState.controller === controller) {
      activityCapacityState.controller = null;
    }
  }
}

function scheduleActivityCapacityHover(target, personId, activityId, delayMs = SCHEDULE_ACTIVITY_CAPACITY_HOVER_DELAY_MS) {
  if (!target || personId == null || activityId == null || !activitySupportsCapacity(activityId)) {
    hideActivityCapacityTooltip();
    return;
  }
  const cacheKey = activityCapacityHoverKey(personId, activityId);
  if (activityCapacityState.timer) clearTimeout(activityCapacityState.timer);
  activityCapacityState.target = target;
  activityCapacityState.cacheKey = cacheKey;
  activityCapacityState.timer = setTimeout(() => {
    activityCapacityState.timer = null;
    if (activityCapacityState.target !== target || activityCapacityState.cacheKey !== cacheKey) return;
    void loadActivityCapacityTooltip(target, personId, activityId, cacheKey);
  }, Math.max(0, delayMs));
}

function attachActivityCapacityHover(target, personId, activityId) {
  if (!target || personId == null || activityId == null || !activitySupportsCapacity(activityId)) return;
  const show = () => scheduleActivityCapacityHover(target, personId, activityId);
  const showNow = () => scheduleActivityCapacityHover(target, personId, activityId, 0);
  const hide = () => {
    if (activityCapacityState.target === target) hideActivityCapacityTooltip();
  };
  target.addEventListener("pointerenter", show);
  target.addEventListener("pointerleave", hide);
  target.addEventListener("pointercancel", hide);
  target.addEventListener("focusin", showNow);
  target.addEventListener("focusout", hide);
}

function setupActivityCapacityHover() {
  window.addEventListener("resize", () => hideActivityCapacityTooltip({ abort: false }));
  document.addEventListener("scroll", () => hideActivityCapacityTooltip({ abort: false }), true);
}


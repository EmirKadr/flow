// @ts-check
const SCHEDULE_RFID_REFRESH_MS = 7000;

function scheduleRfidKey() {
  return `${state.year}|${state.week}|${state.weekday}|${state.areaId || ""}`;
}

function scheduleRfidUrl() {
  return `/api/rfid/events?year=${state.year}&week=${state.week}&weekday=${state.weekday}` +
    (state.areaId ? `&area_id=${state.areaId}` : "");
}

function scheduleRfidHourKey(personId, hour) {
  return `${Number(personId)}:${Number(hour)}`;
}

function normalizeRfidEvent(event) {
  return {
    ...event,
    id: Number(event.id),
    person_id: event.person_id == null ? null : Number(event.person_id),
    activity_id: event.activity_id == null ? null : Number(event.activity_id),
    hour: Number(event.hour),
    minute: Number(event.minute),
    status: String(event.status || ""),
  };
}

function setScheduleRfidEvents(events) {
  state.rfidEvents = (events || []).map(normalizeRfidEvent);
  const byHour = new Map();
  state.rfidEvents.forEach((event) => {
    if (event.person_id == null || !Number.isFinite(event.hour)) return;
    const key = scheduleRfidHourKey(event.person_id, event.hour);
    if (!byHour.has(key)) byHour.set(key, []);
    byHour.get(key).push(event);
  });
  byHour.forEach((items, key) => {
    byHour.set(key, items.sort((left, right) => Number(left.minute) - Number(right.minute) || Number(left.id) - Number(right.id)));
  });
  state.rfidEventsByHour = byHour;
}

function rfidEventsForHour(personId, hour) {
  return state.rfidEventsByHour.get(scheduleRfidHourKey(personId, hour)) || [];
}

function scheduleRfidStatusLabel(status) {
  if (status === "pending") return "Väntar";
  if (status === "applied") return "Applicerad";
  if (status === "ignored") return "Ignorerad";
  if (status === "duplicate_ignored") return "Dubblett";
  if (status === "unknown_person") return "Okänd bricka";
  if (status === "unknown_activity") return "Okänd modul";
  if (status === "conflict") return "Konflikt";
  return status || "RFID";
}

function scheduleRfidEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function scheduleRfidEventTitle(event) {
  const person = event.person_name || "Okänd person";
  const activity = event.activity_label || event.module_name || "Okänd aktivitet";
  const statusLabel = scheduleRfidStatusLabel(event.status);
  return `${person} stämplade ${activity} ${event.local_time || ""} · ${statusLabel}`;
}

function closeScheduleRfidPopover() {
  document.querySelector("[data-schedule-rfid-popover]")?.remove();
  document.removeEventListener("keydown", scheduleRfidEscapeHandler, true);
}

function scheduleRfidEscapeHandler(event) {
  if (event.key === "Escape") closeScheduleRfidPopover();
}

function updateScheduleRfidEvent(nextEvent) {
  const normalized = normalizeRfidEvent(nextEvent);
  const index = state.rfidEvents.findIndex((event) => Number(event.id) === Number(normalized.id));
  if (index >= 0) {
    state.rfidEvents.splice(index, 1, normalized);
  } else {
    state.rfidEvents.push(normalized);
  }
  setScheduleRfidEvents(state.rfidEvents);
  renderScheduleRfidMarkers();
}

function applyRfidSegments(segments) {
  if (!Array.isArray(segments) || !segments.length) return;
  const personId = Number(segments[0].person_id);
  const hour = Number(segments[0].hour);
  const undoSnapshot = typeof snapshotHour === "function" ? snapshotHour(personId, hour) : null;
  if (typeof invalidateScheduleAllCache === "function") invalidateScheduleAllCache();
  if (typeof pushScheduleUndo === "function") pushScheduleUndo("RFID-stämpel", [undoSnapshot]);
  replaceHourSegments(personId, hour, segments);
  const td = getHourTd(personId, hour);
  if (td) renderHourCell(td);
  scheduleSummaryRefresh(0, { refreshCalculator: true });
  scheduleAutomaticCalculatorRefresh(800);
  void loadScheduleProductivity();
}

async function applyScheduleRfidEvent(eventId) {
  const response = await api.post(`/api/rfid/events/${eventId}/apply`, {}, { logLabel: "RFID-stämpel" });
  if (response?.event) updateScheduleRfidEvent(response.event);
  if (response?.segments) applyRfidSegments(response.segments);
  closeScheduleRfidPopover();
  showToast("RFID-stämpeln applicerades i Bemanning.", "success", 3000);
}

async function ignoreScheduleRfidEvent(eventId) {
  const response = await api.post(`/api/rfid/events/${eventId}/ignore`, {}, { logLabel: "RFID-stämpel" });
  if (response?.event) updateScheduleRfidEvent(response.event);
  closeScheduleRfidPopover();
  showToast("RFID-stämpeln ignorerades men ligger kvar.", "info", 3500);
}

function openScheduleRfidPopover(event, anchor) {
  closeScheduleRfidPopover();
  const rect = anchor.getBoundingClientRect();
  const popover = document.createElement("div");
  popover.className = "schedule-rfid-popover";
  popover.dataset.scheduleRfidPopover = "true";
  const canAct = event.status === "pending" && !scheduleIsReadOnly();
  popover.innerHTML = `
    <div class="schedule-rfid-popover-title">${scheduleRfidEscape(event.person_name || "Okänd person")}</div>
    <div class="schedule-rfid-popover-meta">${scheduleRfidEscape(event.local_time || "")} · ${scheduleRfidEscape(event.activity_label || event.module_name || "Okänd aktivitet")}</div>
    <div class="schedule-rfid-popover-status ${scheduleRfidEscape(event.status)}">${scheduleRfidEscape(scheduleRfidStatusLabel(event.status))}</div>
    ${event.status_reason ? `<div class="schedule-rfid-popover-reason">${scheduleRfidEscape(event.status_reason)}</div>` : ""}
    ${canAct ? `
      <div class="schedule-rfid-popover-actions">
        <button type="button" class="primary" data-rfid-apply>OK</button>
        <button type="button" data-rfid-ignore>Ignorera</button>
      </div>
    ` : ""}
  `;
  document.body.appendChild(popover);
  const left = Math.min(window.innerWidth - popover.offsetWidth - 12, Math.max(12, rect.left));
  const top = Math.min(window.innerHeight - popover.offsetHeight - 12, rect.bottom + 8);
  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
  popover.querySelector("[data-rfid-apply]")?.addEventListener("click", () => {
    void applyScheduleRfidEvent(event.id).catch((error) => showToast(error.message || "Kunde inte applicera RFID-stämpeln.", "error", 6000));
  });
  popover.querySelector("[data-rfid-ignore]")?.addEventListener("click", () => {
    void ignoreScheduleRfidEvent(event.id).catch((error) => showToast(error.message || "Kunde inte ignorera RFID-stämpeln.", "error", 6000));
  });
  document.addEventListener("keydown", scheduleRfidEscapeHandler, true);
  window.setTimeout(() => {
    document.addEventListener("click", closeScheduleRfidPopover, { once: true });
  }, 0);
}

function decorateRfidHourCell(td) {
  td.querySelector(".schedule-rfid-markers")?.remove();
  td.classList.remove("has-rfid-event");
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  const events = rfidEventsForHour(personId, hour);
  if (!events.length) return;
  td.classList.add("has-rfid-event");
  const wrap = document.createElement("div");
  wrap.className = "schedule-rfid-markers";
  events.forEach((event, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `schedule-rfid-marker ${event.status}`;
    button.title = scheduleRfidEventTitle(event);
    button.style.left = `calc(${Math.max(0, Math.min(59, Number(event.minute || 0))) / 60 * 100}% + ${index * 3}px)`;
    button.setAttribute("aria-label", button.title);
    button.addEventListener("click", (clickEvent) => {
      clickEvent.preventDefault();
      clickEvent.stopPropagation();
      openScheduleRfidPopover(event, button);
    });
    wrap.appendChild(button);
  });
  td.appendChild(wrap);
}

function renderScheduleRfidMarkers() {
  document.querySelectorAll("#scheduleBody td[data-person-id][data-hour]").forEach((td) => {
    decorateRfidHourCell(td);
  });
}

function scheduleNextRfidRefresh(delay = SCHEDULE_RFID_REFRESH_MS) {
  window.clearTimeout(scheduleRfidLoadState.timer);
  scheduleRfidLoadState.timer = window.setTimeout(() => {
    if (document.hidden) {
      scheduleNextRfidRefresh();
      return;
    }
    void loadScheduleRfidEvents({ silent: true });
  }, delay);
}

async function loadScheduleRfidEvents(options = {}) {
  if (!state.year || !state.week || !state.weekday) return;
  const key = scheduleRfidKey();
  scheduleRfidLoadState.controller?.abort();
  const controller = new AbortController();
  scheduleRfidLoadState.controller = controller;
  scheduleRfidLoadState.key = key;
  try {
    const payload = await api.get(scheduleRfidUrl(), {
      signal: controller.signal,
      skipCache: true,
      logGetUserEvent: false,
      telemetrySource: options.silent ? "background" : "foreground",
    });
    if (controller.signal.aborted || scheduleRfidLoadState.key !== key) return;
    state.rfidKey = key;
    setScheduleRfidEvents(payload?.events || []);
    renderScheduleRfidMarkers();
  } catch (error) {
    if (error?.name !== "AbortError" && !options.silent) {
      showToast(error.message || "Kunde inte hämta RFID-stämplingar.", "error", 5000);
    }
  } finally {
    if (scheduleRfidLoadState.controller === controller) {
      scheduleRfidLoadState.controller = null;
    }
    scheduleNextRfidRefresh();
  }
}

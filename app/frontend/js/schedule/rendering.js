function buildDisplayLabel(text, className) {
  const label = document.createElement("div");
  label.className = className;
  label.textContent = text;
  return label;
}

function scheduledActivityIdForHour(personId, hour) {
  const serverDefault = scheduledDefaultActivityId(personId, hour);
  if (serverDefault != null) return serverDefault;
  if (!isScheduledHour(personId, hour)) return null;
  const person = personById(personId);
  return homeActivityIdForPerson(person);
}

function effectiveActivityIdForRange(personId, hour, minuteStart, minuteEnd) {
  const segment = currentSegment(personId, hour, minuteStart, minuteEnd);
  if (segment.activity_id != null) return segment.activity_id;

  const scheduledActivityId = scheduledActivityIdForHour(personId, hour);
  if (scheduledActivityId != null && !segment.empty_override) {
    return scheduledActivityId;
  }
  return null;
}

function clearFocusedCell() {
  if (!state.focusedCell?.focusEl) return;
  state.focusedCell.focusEl.classList.remove("focused");
}

function focusSegment(td, focusEl, minuteStart, minuteEnd) {
  clearFocusedCell();
  state.focusedCell = {
    td,
    focusEl,
    personId: Number(td.dataset.personId),
    hour: Number(td.dataset.hour),
    minuteStart,
    minuteEnd,
  };
  focusEl.classList.add("focused");
  if (document.activeElement && document.activeElement.tagName === "SELECT") {
    document.activeElement.blur();
  }
  setTimeout(() => {
    try {
      focusEl.focus({ preventScroll: true });
    } catch (e) {}
  }, 0);
}

function effectiveActivityIdForTd(td) {
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  const segments = segmentsForHour(personId, hour);
  if (isSplitHour(segments)) {
    const values = splitRangesForSegments(segments).map((range) =>
      effectiveActivityIdForRange(personId, hour, range.minute_start, range.minute_end)
    );
    return values.length > 0 && values.every((value) => value != null && value === values[0]) ? values[0] : null;
  }
  return effectiveActivityIdForRange(personId, hour, 0, 60);
}

function effectiveActivityIdForFocus() {
  if (!state.focusedCell) return null;
  const { personId, hour, minuteStart, minuteEnd } = state.focusedCell;
  return effectiveActivityIdForRange(personId, hour, minuteStart, minuteEnd);
}

function splitDurationsForRanges(ranges) {
  return (ranges || []).map((range) => Number(range.minute_end) - Number(range.minute_start));
}

function formatMinuteList(values) {
  const textValues = (values || []).map((value) => String(value));
  if (textValues.length <= 1) return textValues[0] || "";
  if (textValues.length === 2) return `${textValues[0]} och ${textValues[1]}`;
  return `${textValues.slice(0, -1).join(", ")} och ${textValues[textValues.length - 1]}`;
}

function openSelectPicker(select) {
  if (!select) return;
  try {
    select.focus({ preventScroll: true });
  } catch (e) {
    select.focus();
  }
  try {
    if (typeof select.showPicker === "function") {
      select.showPicker();
      return;
    }
  } catch (e) {}
  try {
    select.click();
  } catch (e) {}
}

function requestScheduleSplitMinutes(defaultMinutes = DEFAULT_SPLIT_MINUTES) {
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal schedule-split-modal" role="dialog" aria-modal="true" aria-labelledby="scheduleSplitTitle">
        <div class="schedule-split-heading">
          <h2 id="scheduleSplitTitle">Dela timme</h2>
          <div class="schedule-split-mode" role="group" aria-label="Antal delar">
            <button type="button" data-split-parts="2">1/2</button>
            <button type="button" data-split-parts="3">1/3</button>
            <button type="button" data-split-parts="4">1/4</button>
          </div>
        </div>
        <div id="scheduleSplitFields" class="schedule-split-fields"></div>
        <p class="note" id="scheduleSplitHint"></p>
        <div class="actions">
          <button type="button" id="scheduleSplitCancel">Avbryt</button>
          <button type="button" class="primary" data-enter-default id="scheduleSplitContinue">Fortsätt</button>
        </div>
      </div>
    `;
    document.body.appendChild(backdrop);

    let partCount = MIN_SPLIT_PARTS;
    const boundaryValues = new Map(
      [2, 3, 4].map((count) => [
        count,
        defaultSplitBoundaries(count, defaultMinutes).map((value) => String(value)),
      ])
    );
    const fields = backdrop.querySelector("#scheduleSplitFields");
    const hint = backdrop.querySelector("#scheduleSplitHint");
    const modeButtons = Array.from(backdrop.querySelectorAll("[data-split-parts]"));
    const close = (value) => {
      backdrop.remove();
      resolve(value);
    };
    const inputs = () => Array.from(fields.querySelectorAll("input[data-split-boundary]"));
    const parsedBoundaries = () => inputs().map((input) => Number.parseInt(String(input.value || "").trim(), 10));
    const persistValues = () => {
      boundaryValues.set(partCount, inputs().map((input) => String(input.value || "").trim()));
    };
    const focusFirstInput = () => {
      const input = inputs()[0];
      if (!input) return;
      input.focus();
      input.select();
    };
    const updateHint = () => {
      const ranges = splitSegmentsForBoundaries(parsedBoundaries(), partCount);
      hint.textContent = ranges
        ? `Delarna blir ${formatMinuteList(splitDurationsForRanges(ranges))} minuter.`
        : (partCount === 2 ? "Skriv ett heltal mellan 1 och 59." : "Skriv stigande minuter mellan 1 och 59.");
    };
    const renderFields = (selectFirst = false) => {
      modeButtons.forEach((button) => {
        const isActive = Number(button.dataset.splitParts) === partCount;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
      });
      const values = boundaryValues.get(partCount) || defaultSplitBoundaries(partCount).map((value) => String(value));
      if (partCount === 2) {
        fields.innerHTML = `
          <label>Minuter i första delen
            <input id="scheduleSplitMinutesInput" data-split-boundary="0" type="text" inputmode="numeric" autocomplete="off" value="${escapeHtml(values[0] || DEFAULT_SPLIT_MINUTES)}" />
          </label>
        `;
      } else {
        fields.innerHTML = `
          <div class="schedule-split-boundaries">
            ${values.map((value, index) => `
              <label>Början del ${index + 2}
                <input data-split-boundary="${index}" type="text" inputmode="numeric" autocomplete="off" value="${escapeHtml(value)}" />
              </label>
            `).join("")}
          </div>
        `;
      }
      inputs().forEach((input) => input.addEventListener("input", () => {
        persistValues();
        updateHint();
      }));
      updateHint();
      if (selectFirst) setTimeout(focusFirstInput, 0);
    };
    const submit = () => {
      persistValues();
      const ranges = splitSegmentsForBoundaries(parsedBoundaries(), partCount);
      if (!ranges) {
        showToast(
          partCount === 2
            ? "Skriv minuter för första delen, 1-59."
            : "Skriv stigande minutstarter mellan 1 och 59.",
          "warn"
        );
        focusFirstInput();
        updateHint();
        return;
      }
      close(ranges);
    };

    backdrop.querySelector("#scheduleSplitCancel").addEventListener("click", () => close(null));
    backdrop.querySelector("#scheduleSplitContinue").addEventListener("click", submit);
    modeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        persistValues();
        partCount = normalizeSplitPartCount(button.dataset.splitParts);
        renderFields(true);
      });
    });
    backdrop.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close(null);
      }
    });
    renderFields(true);
  });
}

function openFullHourSelect(e, td) {
  e.preventDefault();
  e.stopPropagation();
  if (scheduleIsReadOnly()) {
    focusSegment(td, td, 0, 60);
    showReadOnlyToast();
    return;
  }
  if (isHourLocked(Number(td.dataset.personId), Number(td.dataset.hour))) {
    showLockedCellToast();
    return;
  }
  focusSegment(td, td, 0, 60);
  const select = td.querySelector("select.cell-select");
  if (typeof ensureActivitySelectOptionsLoaded === "function") ensureActivitySelectOptionsLoaded(select);
  setTimeout(() => openSelectPicker(select), 0);
}

function openSplitSegmentSelect(e, td, part, minuteStart, minuteEnd) {
  e.preventDefault();
  e.stopPropagation();
  if (scheduleIsReadOnly()) {
    focusSegment(td, part, minuteStart, minuteEnd);
    showReadOnlyToast();
    return;
  }
  if (isRangeLocked(Number(td.dataset.personId), Number(td.dataset.hour), minuteStart, minuteEnd)) {
    showLockedCellToast();
    return;
  }
  focusSegment(td, part, minuteStart, minuteEnd);
  const select = part.querySelector("select.half-select");
  if (typeof ensureActivitySelectOptionsLoaded === "function") ensureActivitySelectOptionsLoaded(select);
  setTimeout(() => openSelectPicker(select), 0);
}

async function toggleFullHourSplitFromEvent(e, td) {
  e.preventDefault();
  e.stopPropagation();
  if (scheduleIsReadOnly()) {
    focusSegment(td, td, 0, 60);
    showReadOnlyToast();
    return;
  }
  if (isHourLocked(Number(td.dataset.personId), Number(td.dataset.hour))) {
    showLockedCellToast();
    return;
  }
  focusSegment(td, td, 0, 60);
  const splitRanges = await requestScheduleSplitMinutes(DEFAULT_SPLIT_MINUTES);
  if (splitRanges == null) return;
  void toggleHourSplit(td, 0, splitRanges);
}

function toggleSplitSegmentFromEvent(e, td, part, minuteStart, minuteEnd) {
  e.preventDefault();
  e.stopPropagation();
  if (scheduleIsReadOnly()) {
    focusSegment(td, part, minuteStart, minuteEnd);
    showReadOnlyToast();
    return;
  }
  if (isHourLocked(Number(td.dataset.personId), Number(td.dataset.hour))) {
    showLockedCellToast();
    return;
  }
  focusSegment(td, part, minuteStart, minuteEnd);
  void toggleHourSplit(td, minuteStart);
}

function splitPartFromEvent(td, e) {
  const directPart = e.target.closest?.(".hour-segment");
  if (directPart && td.contains(directPart)) return directPart;

  return splitPartFromPoint(td, e.clientX, e.clientY);
}

function splitPartFromPoint(td, clientX, clientY) {
  const pointEl = document.elementFromPoint(clientX, clientY);
  const pointPart = pointEl?.closest?.(".hour-segment");
  if (pointPart && td.contains(pointPart)) return pointPart;

  const parts = Array.from(td.querySelectorAll(".hour-segment"));
  if (parts.length <= 1) return parts[0] || null;

  const ranges = splitRangesForSegments(segmentsForHour(Number(td.dataset.personId), Number(td.dataset.hour)));
  if (ranges.length >= 2) {
    const rect = td.getBoundingClientRect();
    const minuteAtPoint = Math.max(0, Math.min(59.999, ((clientX - rect.left) / Math.max(1, rect.width)) * 60));
    const index = ranges.findIndex((range) => minuteAtPoint >= range.minute_start && minuteAtPoint < range.minute_end);
    return parts[Math.max(0, index)] || parts[0];
  }

  const rect = td.getBoundingClientRect();
  return clientX >= rect.left + (rect.width / 2) ? parts[1] : parts[0];
}

function rangeFromSegmentPart(part) {
  if (!part) return null;
  return {
    minute_start: Number(part.dataset.minuteStart),
    minute_end: Number(part.dataset.minuteEnd),
  };
}

function targetRangeFromPoint(td, clientX, clientY) {
  if (!td || td.dataset.split !== "1") return { ...FULL_SEGMENT };
  return rangeFromSegmentPart(splitPartFromPoint(td, clientX, clientY)) || firstSplitRangeForTd(td);
}

function dragCellKeyForTd(td) {
  return `${td.dataset.personId}:${td.dataset.hour}`;
}

function activityIdForDragSource(td, minuteStart, minuteEnd) {
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  return effectiveActivityIdForRange(personId, hour, minuteStart, minuteEnd);
}

function armFullHourDrag(td, event) {
  if (scheduleIsReadOnly()) return;
  if (event.button !== 0) return;
  if (td.dataset.split === "1") return;
  startPendingDrag(td, event, 0, 60);
}

function armHalfHourDrag(td, minuteStart, minuteEnd, event) {
  if (scheduleIsReadOnly()) return;
  if (event.button !== 0) return;
  startPendingDrag(td, event, minuteStart, minuteEnd);
}

function resetRenderedHourState(td) {
  td.classList.remove("split-hour", "scheduled-empty", "base-value", "with-display-label", "locked-cell");
  td.style.background = "#fff";
  td.dataset.isBase = "";
  td.title = "";
}

function renderFullHourCell(td, segment, isScheduled) {
  td.dataset.split = "0";
  resetRenderedHourState(td);
  td.oncontextmenu = (e) => openFullHourSelect(e, td);

  const personId = Number(td.dataset.personId);
  const hasExplicitSegment = !!segment;
  const explicitActivityId = hasExplicitSegment ? segment.activity_id : null;
  const explicitEmptyOverride = !!segment?.empty_override;
  const scheduledActivityId = isScheduled ? scheduledActivityIdForHour(personId, Number(td.dataset.hour)) : null;
  const showScheduledDefault = explicitActivityId == null && !explicitEmptyOverride && scheduledActivityId != null;
  const locked = isForeignLockedSegment(segment);
  if (locked) {
    td.classList.add("locked-cell");
    td.title = "Låst av annan användare";
  }

  if (explicitActivityId != null) {
    td.style.background = colorFor(explicitActivityId);
  } else if (showScheduledDefault) {
    td.style.background = colorFor(scheduledActivityId);
    td.dataset.isBase = "1";
  } else if (isScheduled) {
    if (scheduledActivityId) {
      // Explicit tömd: subtilt randig version av hemaktivitetens färg
      const c = colorFor(scheduledActivityId);
      td.style.background = `repeating-linear-gradient(45deg, ${c}40 0, ${c}40 2px, var(--surface) 2px, var(--surface) 10px)`;
    } else {
      td.style.background = "";
      td.classList.add("scheduled-empty");
    }
  }

  const select = buildActivitySelect([explicitActivityId, scheduledActivityId]);
  select.className = "cell-select";
  const selectedActivityId = explicitActivityId != null
    ? explicitActivityId
    : (showScheduledDefault ? scheduledActivityId : null);
  setSelectActivityValue(select, selectedActivityId);
  select.dataset.minuteStart = "0";
  select.dataset.minuteEnd = "60";
  select.dataset.version = String(segment?.version || 0);
  select.disabled = locked || scheduleIsReadOnly();

  select.addEventListener("change", () => onSegmentChange(td, 0, 60));
  select.addEventListener("focus", () => {
    if (typeof ensureActivitySelectOptionsLoaded === "function") ensureActivitySelectOptionsLoaded(select);
    focusSegment(td, td, 0, 60);
  });
  select.addEventListener("mousedown", (e) => {
    if (typeof ensureActivitySelectOptionsLoaded === "function") ensureActivitySelectOptionsLoaded(select);
    armFullHourDrag(td, e);
    e.stopPropagation();
    if (e.button === 0) e.preventDefault();
    const isFocused = state.focusedCell
      && state.focusedCell.td === td
      && state.focusedCell.minuteStart === 0
      && state.focusedCell.minuteEnd === 60;
    if (!isFocused) {
      focusSegment(td, td, 0, 60);
    }
  });
  select.addEventListener("keydown", (e) => handleSelectClipboardKeys(e), true);
  select.addEventListener("contextmenu", (e) => openFullHourSelect(e, td), true);

  td.appendChild(select);
  if (showScheduledDefault && scheduledActivityId != null) {
    td.classList.add("with-display-label");
    td.appendChild(buildDisplayLabel(activityLabel(scheduledActivityId), "cell-display-label"));
  }
  attachActivityCapacityHover(td, personId, selectedActivityId);
}

function renderSplitHourCell(td, segments, isScheduled) {
  td.dataset.split = "1";
  resetRenderedHourState(td);
  td.classList.add("split-hour");
  td.oncontextmenu = (e) => {
    const part = splitPartFromEvent(td, e);
    if (!part) return;
    openSplitSegmentSelect(
      e,
      td,
      part,
      Number(part.dataset.minuteStart),
      Number(part.dataset.minuteEnd),
    );
  };

  const wrapper = document.createElement("div");
  wrapper.className = "hour-split";
  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  const scheduledActivityId = isScheduled ? scheduledActivityIdForHour(personId, hour) : null;
  if (segments.some((segment) => isForeignLockedSegment(segment))) {
    td.classList.add("locked-cell");
    td.title = "En eller flera delar är låsta av annan användare";
  }

  splitRangesForSegments(segments).forEach(({ minute_start, minute_end }) => {
    const segment = currentSegment(personId, hour, minute_start, minute_end);
    const part = document.createElement("div");
    part.className = "hour-segment";
    part.dataset.minuteStart = String(minute_start);
    part.dataset.minuteEnd = String(minute_end);
    part.style.flex = `${Math.max(1, minute_end - minute_start)} 1 0`;
    part.tabIndex = -1;
    const locked = isForeignLockedSegment(segment);
    if (locked) {
      part.classList.add("locked-cell");
      part.title = "Låst av annan användare";
    }

    if (segment.activity_id != null) {
      part.style.background = colorFor(segment.activity_id);
    } else if (!segment.empty_override && scheduledActivityId != null) {
      part.style.background = colorFor(scheduledActivityId);
    } else if (isScheduled) {
      if (scheduledActivityId) {
        const c = colorFor(scheduledActivityId);
        part.style.background = `repeating-linear-gradient(45deg, ${c}40 0, ${c}40 2px, var(--surface) 2px, var(--surface) 8px)`;
      } else {
        part.style.background = "";
        part.classList.add("scheduled-empty-half");
      }
    } else {
      part.style.background = "#fff";
    }

    const select = buildActivitySelect([segment.activity_id, scheduledActivityId]);
    select.className = "half-select";
    const selectedActivityId = segment.activity_id != null
      ? segment.activity_id
      : (!segment.empty_override && scheduledActivityId != null ? scheduledActivityId : null);
    setSelectActivityValue(select, selectedActivityId);
    select.dataset.minuteStart = String(minute_start);
    select.dataset.minuteEnd = String(minute_end);
    select.dataset.version = String(segment.version || 0);
    select.disabled = locked || scheduleIsReadOnly();

    select.addEventListener("change", () => onSegmentChange(td, minute_start, minute_end));
    select.addEventListener("focus", () => {
      if (typeof ensureActivitySelectOptionsLoaded === "function") ensureActivitySelectOptionsLoaded(select);
      focusSegment(td, part, minute_start, minute_end);
    });
    select.addEventListener("mousedown", (e) => {
      if (typeof ensureActivitySelectOptionsLoaded === "function") ensureActivitySelectOptionsLoaded(select);
      armHalfHourDrag(td, minute_start, minute_end, e);
      e.stopPropagation();
      if (e.button === 0) e.preventDefault();
      const isFocused = state.focusedCell
        && state.focusedCell.td === td
        && state.focusedCell.minuteStart === minute_start
        && state.focusedCell.minuteEnd === minute_end;
      if (!isFocused) {
        focusSegment(td, part, minute_start, minute_end);
      }
    });
    select.addEventListener("keydown", (e) => handleSelectClipboardKeys(e), true);
    part.addEventListener(
      "contextmenu",
      (e) => openSplitSegmentSelect(e, td, part, minute_start, minute_end),
      true,
    );
    select.addEventListener(
      "contextmenu",
      (e) => openSplitSegmentSelect(e, td, part, minute_start, minute_end),
      true,
    );

    part.appendChild(select);
    if (segment.activity_id == null && !segment.empty_override && scheduledActivityId != null) {
      part.classList.add("with-display-label");
      part.appendChild(buildDisplayLabel(activityLabel(scheduledActivityId), "hour-segment-label"));
    }
    attachActivityCapacityHover(part, personId, selectedActivityId);
    wrapper.appendChild(part);
  });

  td.appendChild(wrapper);
}

function renderHourCell(td) {
  td.innerHTML = "";
  clearFocusedCell();

  const personId = Number(td.dataset.personId);
  const hour = Number(td.dataset.hour);
  const segments = sortSegments(segmentsForHour(personId, hour));
  const isScheduled = isScheduledHour(personId, hour);

  if (isSplitHour(segments) || segments.some((segment) => isPartialRange(segment))) {
    renderSplitHourCell(td, segments, isScheduled);
    if (td.classList.contains("pending-save")) setHourPending(td, true);
    if (typeof decorateRfidHourCell === "function") decorateRfidHourCell(td);
    return;
  }

  const segment = segments.length === 1 ? segments[0] : null;
  renderFullHourCell(td, segment, isScheduled);
  if (td.classList.contains("pending-save")) setHourPending(td, true);
  if (typeof decorateRfidHourCell === "function") decorateRfidHourCell(td);
}

function applySelectedPersonRow() {
  const selectedId = Number(state.selectedPersonId);
  document.querySelectorAll("#scheduleBody tr.person-row-selected").forEach((row) => {
    row.classList.remove("person-row-selected");
    row.removeAttribute("aria-selected");
  });
  if (!Number.isInteger(selectedId)) return;
  const row = document.querySelector(`#scheduleBody tr[data-person-id="${selectedId}"]`);
  if (!row) return;
  row.classList.add("person-row-selected");
  row.setAttribute("aria-selected", "true");
}

function selectPersonRow(personId) {
  const nextId = Number(personId);
  if (!Number.isInteger(nextId)) return;
  state.selectedPersonId = nextId;
  applySelectedPersonRow();
}

function shouldShowScheduleProductivityValue(value) {
  const percent = Math.round(Number(value?.percent));
  return Number.isFinite(percent) && percent > 0;
}

function renderScheduleProductivityCell(td, person) {
  td.textContent = "";
  td.className = "schedule-productivity";
  td.dataset.personId = String(person?.id || td.dataset.personId || "");
  const value = state.productivityByPersonId.get(Number(person?.id));
  if (!value || !shouldShowScheduleProductivityValue(value)) {
    td.title = "Ingen avslutad KPI-tid";
    return;
  }
  const displayPercent = Math.round(Number(value.percent));
  const span = document.createElement("span");
  span.className = `schedule-productivity-value ${value.status}`;
  span.textContent = `${displayPercent}%`;
  td.title = `${Math.round(value.points)} p / ${value.hours.toFixed(1).replace(".", ",")} avslutade KPI-timmar`;
  td.appendChild(span);
}

function buildRows() {
  const body = document.getElementById("scheduleBody");
  const fragment = document.createDocumentFragment();
  state.focusedCell = null;

  state.persons.forEach((person, rowIndex) => {
    const tr = document.createElement("tr");
    tr.dataset.personId = person.id;
    tr.dataset.rowIndex = rowIndex;

    const name = document.createElement("td");
    name.className = "name";
    name.textContent = person.name;
    setupPersonOrderNameCell(name, person);
    tr.appendChild(name);

    const base = document.createElement("td");
    base.className = "base";
    const homeArea = state.areas.find((a) => a.id === person.home_area_id);
    base.textContent = homeArea ? homeArea.name : "";
    tr.appendChild(base);

    const productivity = document.createElement("td");
    productivity.className = "schedule-productivity";
    productivity.dataset.personId = person.id;
    renderScheduleProductivityCell(productivity, person);
    tr.appendChild(productivity);

    HOURS.forEach((hour, colIndex) => {
      const td = document.createElement("td");
      td.dataset.personId = person.id;
      td.dataset.hour = hour;
      td.dataset.rowIndex = rowIndex;
      td.dataset.colIndex = colIndex;
      td.tabIndex = -1;
      renderHourCell(td);
      tr.appendChild(td);
    });

    fragment.appendChild(tr);
  });

  body.replaceChildren(fragment);
  applySelectedPersonRow();
}


// @ts-check
function clearSummaryRefreshTimer() {
  if (!summaryState.timer) return;
  clearTimeout(summaryState.timer);
  summaryState.timer = null;
}

function setSummaryLoading(loading) {
  const card = document.querySelector(".summary-card");
  if (!card) return;
  card.classList.toggle("loading", loading);
  card.setAttribute("aria-busy", loading ? "true" : "false");
}

function cancelSummaryRefresh({ abortInFlight = false } = {}) {
  clearSummaryRefreshTimer();
  if (!abortInFlight || !summaryState.controller) return;
  summaryState.controller.abort();
  summaryState.controller = null;
  setSummaryLoading(false);
}

function scheduleCalculatorRender() {
  if (summaryState.calcFrame) cancelAnimationFrame(summaryState.calcFrame);
  summaryState.calcFrame = requestAnimationFrame(() => {
    summaryState.calcFrame = 0;
    renderCalculator();
  });
}

const SUMMARY_HOURS_PER_PERSON_DAY = 8;
const summaryDragSelection = {
  active: false,
  additive: false,
  startIndex: -1,
  baseKeys: new Set(),
  dragged: false,
  suppressClick: false,
};

function summaryScopeKey() {
  const areaKey = state.areaId == null ? "ALLT" : String(Number(state.areaId));
  return `${scheduleScopeKey()}|${selectedScheduleYmdString()}|area:${areaKey}`;
}

function nextSummaryGroupId() {
  state.summaryGroupSeq += 1;
  return `summary-${Date.now()}-${state.summaryGroupSeq}`;
}

function summarySourceKey(row) {
  const activityId = Number(row?.activity_id);
  if (Number.isInteger(activityId)) return `activity:${activityId}`;
  const code = String(row?.activity_code || "").trim();
  if (code) return `code:${code}`;
  return `label:${String(row?.activity_label || "").trim()}`;
}

function summaryRowSourceKeys(row) {
  if (Array.isArray(row?._summarySourceKeys)) return row._summarySourceKeys;
  const key = summarySourceKey(row);
  return key ? [key] : [];
}

function normalizeSummaryRow(row) {
  const key = summarySourceKey(row);
  return {
    ...row,
    _summaryKey: key,
    _summarySourceKeys: key ? [key] : [],
    _summaryIsGroup: false,
    _summaryGroupId: "",
  };
}

function cloneSummaryGroups(groups) {
  return (groups || [])
    .map((group) => ({
      id: String(group?.id || ""),
      sourceKeys: Array.from(new Set((group?.sourceKeys || []).map((key) => String(key)).filter(Boolean))),
    }))
    .filter((group) => group.id && group.sourceKeys.length >= 2);
}

function summaryGroupsForScope(scopeKey = summaryScopeKey()) {
  return cloneSummaryGroups(state.summaryGroupsByScope.get(scopeKey) || []);
}

function setSummaryGroupsForScope(scopeKey, groups) {
  const normalized = cloneSummaryGroups(groups);
  if (normalized.length) state.summaryGroupsByScope.set(scopeKey, normalized);
  else state.summaryGroupsByScope.delete(scopeKey);
}

function ensureSummarySelectionScope(scopeKey = summaryScopeKey()) {
  if (state.summarySelectionScopeKey === scopeKey) return;
  state.summarySelectionScopeKey = scopeKey;
  state.summarySelectedKeys = new Set();
  state.summaryLastSelectedIndex = -1;
}

function summaryGroupLabel(members) {
  const labels = members.map((row) => String(row.activity_label || "").trim()).filter(Boolean);
  if (labels.length <= 3) return labels.join(" + ");
  return `${labels.slice(0, 3).join(" + ")} + ${labels.length - 3} till`;
}

function buildGroupedSummaryRow(group, members) {
  const hours = members.reduce((sum, row) => sum + (Number(row.hours) || 0), 0);
  return {
    activity_id: null,
    activity_code: "SUMMERAD",
    activity_label: summaryGroupLabel(members),
    color: members[0]?.color || "#f3f4f6",
    hours,
    persons_equiv: Math.round(((hours / SUMMARY_HOURS_PER_PERSON_DAY) + Number.EPSILON) * 10) / 10,
    _summaryKey: `group:${group.id}`,
    _summarySourceKeys: members.map((row) => row._summaryKey),
    _summaryIsGroup: true,
    _summaryGroupId: group.id,
  };
}

function displaySummaryRows(rows) {
  const baseRows = (rows || []).map(normalizeSummaryRow).filter((row) => row._summaryKey);
  const sourceByKey = new Map(baseRows.map((row) => [row._summaryKey, row]));
  const indexByKey = new Map(baseRows.map((row, index) => [row._summaryKey, index]));
  const consumed = new Set();
  const groupByFirstIndex = new Map();

  summaryGroupsForScope().forEach((group) => {
    const members = group.sourceKeys
      .map((key) => sourceByKey.get(key))
      .filter((row) => row && !consumed.has(row._summaryKey));
    if (members.length < 2) return;
    const firstIndex = Math.min(...members.map((row) => indexByKey.get(row._summaryKey)));
    members.forEach((row) => consumed.add(row._summaryKey));
    groupByFirstIndex.set(firstIndex, buildGroupedSummaryRow(group, members));
  });

  const displayRows = [];
  baseRows.forEach((row, index) => {
    if (groupByFirstIndex.has(index)) displayRows.push(groupByFirstIndex.get(index));
    if (!consumed.has(row._summaryKey)) displayRows.push(row);
  });
  return displayRows;
}

function summarySelectionSetEquals(keys, groupKeys) {
  if (keys.size !== groupKeys.length) return false;
  return groupKeys.every((key) => keys.has(key));
}

function selectedVisibleSummaryKeys() {
  const visible = new Set((state.summaryRenderedRows || []).flatMap((row) => summaryRowSourceKeys(row)));
  return new Set([...state.summarySelectedKeys].filter((key) => visible.has(key)));
}

function summarySelectionAlreadySingleGroup(keys) {
  return summaryGroupsForScope().some((group) => summarySelectionSetEquals(keys, group.sourceKeys));
}

function summaryGroupIntersectsKeys(group, keys) {
  return group.sourceKeys.some((key) => keys.has(key));
}

function orderedVisibleSourceKeys(keys) {
  return (state.summaryRows || [])
    .map((row) => summarySourceKey(row))
    .filter((key) => key && keys.has(key));
}

function rowIsSummarySelected(row) {
  const keys = summaryRowSourceKeys(row);
  return keys.length > 0 && keys.every((key) => state.summarySelectedKeys.has(key));
}

function applySummarySelectionStyles() {
  document.querySelectorAll("#summaryBody tr[data-summary-index]").forEach((tr) => {
    const row = state.summaryRenderedRows[Number(/** @type {HTMLElement} */ (tr).dataset.summaryIndex)];
    const selected = row ? rowIsSummarySelected(row) : false;
    tr.classList.toggle("summary-row-selected", selected);
    if (selected) tr.setAttribute("aria-selected", "true");
    else tr.removeAttribute("aria-selected");
  });
}

function selectSummaryRow(row, index, event = {}) {
  ensureSummarySelectionScope();
  const rowKeys = summaryRowSourceKeys(row);
  if (!rowKeys.length) return;
  const additive = !!(event.ctrlKey || event.metaKey);

  if (event.shiftKey && state.summaryLastSelectedIndex >= 0) {
    if (!additive) state.summarySelectedKeys = new Set();
    const from = Math.min(state.summaryLastSelectedIndex, index);
    const to = Math.max(state.summaryLastSelectedIndex, index);
    (state.summaryRenderedRows || []).slice(from, to + 1).forEach((item) => {
      summaryRowSourceKeys(item).forEach((key) => state.summarySelectedKeys.add(key));
    });
  } else if (additive) {
    const selected = rowKeys.every((key) => state.summarySelectedKeys.has(key));
    rowKeys.forEach((key) => {
      if (selected) state.summarySelectedKeys.delete(key);
      else state.summarySelectedKeys.add(key);
    });
  } else {
    state.summarySelectedKeys = new Set(rowKeys);
  }

  state.summaryLastSelectedIndex = index;
  applySummarySelectionStyles();
}

function selectSummaryRowRange(fromIndex, toIndex, { additive = false, baseKeys = null } = {}) {
  ensureSummarySelectionScope();
  const from = Math.max(0, Math.min(fromIndex, toIndex));
  const to = Math.min((state.summaryRenderedRows || []).length - 1, Math.max(fromIndex, toIndex));
  const next = new Set(additive ? (baseKeys || state.summarySelectedKeys) : []);
  (state.summaryRenderedRows || []).slice(from, to + 1).forEach((item) => {
    summaryRowSourceKeys(item).forEach((key) => next.add(key));
  });
  state.summarySelectedKeys = next;
  state.summaryLastSelectedIndex = fromIndex;
  applySummarySelectionStyles();
}

async function writeSummaryClipboardText(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (error) {
      // Fallback below covers browsers without granted clipboard permission.
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = String(text);
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("Clipboard nekades av webbläsaren.");
}

async function copySummaryHours(row, target) {
  const text = formatHours(row.hours);
  try {
    await writeSummaryClipboardText(text);
    target?.classList.add("clipboard-flash");
    setTimeout(() => target?.classList.remove("clipboard-flash"), 500);
    showToast(`Kopierade ${text} timmar.`, "success");
  } catch (error) {
    showToast(`Kunde inte kopiera timmar: ${error.message || error}`, "error");
  }
}

function pushSummaryUndo(label, beforeGroups, afterGroups) {
  const scopeKey = summaryScopeKey();
  state.undoStack.push({
    kind: "summary",
    label,
    scopeKey,
    beforeGroups: cloneSummaryGroups(beforeGroups),
    afterGroups: cloneSummaryGroups(afterGroups),
  });
  if (state.undoStack.length > 50) state.undoStack.shift();
  state.redoStack = [];
  updateUndoRedoButtons();
}

function applySummaryHistoryAction(action, direction) {
  if (action?.kind !== "summary") return false;
  if (action.scopeKey !== summaryScopeKey()) {
    showToast(`Byt tillbaka till dagen där summeringen gjordes för att ${direction === "redo" ? "göra om" : "ångra"}.`, "warn");
    return false;
  }
  const groups = direction === "redo" ? action.afterGroups : action.beforeGroups;
  setSummaryGroupsForScope(action.scopeKey, groups);
  state.summarySelectedKeys = new Set();
  state.summaryLastSelectedIndex = -1;
  renderSummaryRows(state.summaryRows);
  showToast(`${direction === "redo" ? "Gjorde om" : "Ångrade"}: ${action.label}`);
  updateUndoRedoButtons();
  return true;
}

function summarizeSelectedSummaryRows() {
  ensureSummarySelectionScope();
  const selectedKeys = selectedVisibleSummaryKeys();
  if (selectedKeys.size < 2) {
    showToast("Markera minst två aktiviteter att summera.", "warn");
    return;
  }
  if (summarySelectionAlreadySingleGroup(selectedKeys)) {
    showToast("Aktiviteterna är redan summerade.", "warn");
    return;
  }

  const beforeGroups = summaryGroupsForScope();
  const orderedKeys = orderedVisibleSourceKeys(selectedKeys);
  const afterGroups = beforeGroups.filter((group) => !summaryGroupIntersectsKeys(group, selectedKeys));
  afterGroups.push({ id: nextSummaryGroupId(), sourceKeys: orderedKeys });
  setSummaryGroupsForScope(summaryScopeKey(), afterGroups);
  state.summarySelectedKeys = new Set(orderedKeys);
  renderSummaryRows(state.summaryRows);
  pushSummaryUndo("summera aktiviteter", beforeGroups, afterGroups);
  showToast(`Summerade ${orderedKeys.length} aktiviteter.`);
}

function splitSummaryGroup(groupId) {
  const beforeGroups = summaryGroupsForScope();
  const group = beforeGroups.find((item) => item.id === groupId);
  if (!group) return;
  const afterGroups = beforeGroups.filter((item) => item.id !== groupId);
  setSummaryGroupsForScope(summaryScopeKey(), afterGroups);
  state.summarySelectedKeys = new Set(group.sourceKeys);
  renderSummaryRows(state.summaryRows);
  pushSummaryUndo("dela summering", beforeGroups, afterGroups);
  showToast("Summeringen delades.");
}

function closeSummaryContextMenu() {
  document.querySelector(".summary-context-menu")?.remove();
}

function summaryContextMenuHost(anchor) {
  return anchor?.closest?.(".summary-card") || document.body;
}

function positionSummaryContextMenu(menu, event, anchor, host = summaryContextMenuHost(anchor)) {
  const padding = 8;
  const menuRect = menu.getBoundingClientRect();
  const hostRect = host === document.body
    ? { left: 0, top: 0, width: document.documentElement.clientWidth || window.innerWidth }
    : host.getBoundingClientRect();
  const anchorRect = anchor?.getBoundingClientRect?.();
  const rawClientX = Number(event?.clientX);
  const clientX = Number.isFinite(rawClientX)
    ? rawClientX
    : (anchorRect ? anchorRect.left + 16 : hostRect.left + padding);
  // Appzoomen skalar menyns egna px, medan rect/clientX mäts i viewporten.
  // Scrollvärden är redan i elementets egen skala för en scrollbar host, men i
  // viewportskala för sidscrollen - därför räknas bara den om.
  const hostScrollLeft = host === document.body
    ? viewportPxToElementPx(menu, window.scrollX)
    : (host.scrollLeft || 0);
  const hostScrollTop = host === document.body
    ? viewportPxToElementPx(menu, window.scrollY)
    : (host.scrollTop || 0);
  const hostWidth = host === document.body
    ? viewportPxToElementPx(menu, document.documentElement.clientWidth || window.innerWidth)
    : (host.clientWidth || viewportPxToElementPx(menu, hostRect.width));

  const localX = viewportPxToElementPx(menu, clientX - hostRect.left) + hostScrollLeft;
  const localY = anchorRect
    ? viewportPxToElementPx(menu, anchorRect.bottom - hostRect.top) + hostScrollTop + 4
    : viewportPxToElementPx(menu, Number(event?.clientY) - hostRect.top) + hostScrollTop;
  const maxLeft = Math.max(padding, hostWidth - viewportPxToElementPx(menu, menuRect.width) - padding);
  menu.style.left = `${Math.max(padding, Math.min(localX, maxLeft))}px`;
  menu.style.top = `${Math.max(padding, localY)}px`;
}

function openSummaryContextMenu(event, row, anchor) {
  closeSummaryContextMenu();
  const selectedKeys = selectedVisibleSummaryKeys();
  const canSummarize = selectedKeys.size >= 2 && !summarySelectionAlreadySingleGroup(selectedKeys);
  const canSplit = !!row?._summaryIsGroup;

  const menu = document.createElement("div");
  menu.className = "summary-context-menu";
  menu.setAttribute("role", "menu");
  menu.style.left = "0px";
  menu.style.top = "0px";

  if (canSummarize) {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("role", "menuitem");
    button.textContent = `Summera ${selectedKeys.size} aktiviteter`;
    button.addEventListener("click", () => {
      closeSummaryContextMenu();
      summarizeSelectedSummaryRows();
    });
    menu.appendChild(button);
  }

  if (canSplit) {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("role", "menuitem");
    button.textContent = "Dela";
    button.addEventListener("click", () => {
      closeSummaryContextMenu();
      splitSummaryGroup(row._summaryGroupId);
    });
    menu.appendChild(button);
  }

  if (!menu.children.length) {
    const button = document.createElement("button");
    button.type = "button";
    button.disabled = true;
    button.textContent = "Markera minst två aktiviteter";
    menu.appendChild(button);
  }

  const host = summaryContextMenuHost(anchor);
  host.appendChild(menu);
  positionSummaryContextMenu(menu, event, anchor, host);
  /** @type {HTMLElement} */ (menu.querySelector("button:not(:disabled)"))?.focus({ preventScroll: true });
}

function summaryRowForEventTarget(target) {
  const tr = target?.closest?.("#summaryBody tr[data-summary-index]");
  if (!tr) return null;
  const index = Number(tr.dataset.summaryIndex);
  return {
    tr,
    index,
    row: state.summaryRenderedRows[index],
  };
}

function handleSummaryClick(event) {
  if (summaryDragSelection.suppressClick) {
    event.preventDefault();
    event.stopPropagation();
    return;
  }
  const found = summaryRowForEventTarget(event.target);
  if (!found?.row) return;
  closeSummaryContextMenu();

  const hoursCell = event.target.closest?.("[data-summary-hours]");
  if (hoursCell) {
    event.preventDefault();
    void copySummaryHours(found.row, hoursCell);
    return;
  }

  selectSummaryRow(found.row, found.index, event);
}

function handleSummaryMouseDown(event) {
  if (event.button !== 0) return;
  if (event.target.closest?.("[data-summary-hours]")) return;
  const found = summaryRowForEventTarget(event.target);
  if (!found?.row) return;
  closeSummaryContextMenu();
  summaryDragSelection.active = true;
  summaryDragSelection.additive = !!(event.ctrlKey || event.metaKey);
  summaryDragSelection.startIndex = found.index;
  summaryDragSelection.baseKeys = new Set(state.summarySelectedKeys);
  summaryDragSelection.dragged = false;
  event.preventDefault();
  selectSummaryRowRange(found.index, found.index, {
    additive: summaryDragSelection.additive,
    baseKeys: summaryDragSelection.baseKeys,
  });
}

function handleSummaryMouseOver(event) {
  if (!summaryDragSelection.active) return;
  const found = summaryRowForEventTarget(event.target);
  if (!found?.row) return;
  if (found.index !== summaryDragSelection.startIndex) summaryDragSelection.dragged = true;
  selectSummaryRowRange(summaryDragSelection.startIndex, found.index, {
    additive: summaryDragSelection.additive,
    baseKeys: summaryDragSelection.baseKeys,
  });
}

function finishSummaryDragSelection() {
  if (!summaryDragSelection.active) return;
  summaryDragSelection.active = false;
  summaryDragSelection.startIndex = -1;
  summaryDragSelection.baseKeys = new Set();
  if (summaryDragSelection.dragged) {
    summaryDragSelection.suppressClick = true;
    setTimeout(() => { summaryDragSelection.suppressClick = false; }, 0);
  }
  summaryDragSelection.dragged = false;
}

function handleSummaryContextMenu(event) {
  finishSummaryDragSelection();
  const found = summaryRowForEventTarget(event.target);
  if (!found?.row) return;
  event.preventDefault();
  if (!rowIsSummarySelected(found.row)) selectSummaryRow(found.row, found.index);
  openSummaryContextMenu(event, found.row, found.tr);
}

function setupSummaryInteractions(tbody) {
  if (state.summaryInteractionsReady) return;
  state.summaryInteractionsReady = true;
  tbody.addEventListener("mousedown", handleSummaryMouseDown);
  tbody.addEventListener("mouseover", handleSummaryMouseOver);
  tbody.addEventListener("click", handleSummaryClick);
  tbody.addEventListener("contextmenu", handleSummaryContextMenu);
  document.addEventListener("mouseup", finishSummaryDragSelection);
  document.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest(".summary-context-menu")) return;
    closeSummaryContextMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSummaryContextMenu();
  });
}

function renderSummaryRows(rows) {
  const tbody = document.getElementById("summaryBody");
  if (!tbody) return;

  ensureSummarySelectionScope();
  const displayRows = displaySummaryRows(rows);
  state.summaryRenderedRows = displayRows;
  const fragment = document.createDocumentFragment();
  displayRows.forEach((row, index) => {
    const tr = document.createElement("tr");
    tr.dataset.summaryIndex = String(index);
    tr.tabIndex = 0;
    if (row._summaryIsGroup) tr.classList.add("summary-row-grouped");

    const activity = document.createElement("td");
    activity.className = "summary-activity-cell";
    activity.style.background = row.color || "";
    activity.style.padding = "5px";
    activity.textContent = row.activity_label;
    tr.appendChild(activity);

    const hours = document.createElement("td");
    hours.className = "summary-hours-cell";
    hours.dataset.summaryHours = "1";
    hours.title = "Klicka för att kopiera";
    hours.textContent = formatHours(row.hours);
    tr.appendChild(hours);

    const persons = document.createElement("td");
    persons.textContent = Number(row.persons_equiv).toFixed(1);
    tr.appendChild(persons);
    fragment.appendChild(tr);
  });
  tbody.replaceChildren(fragment);
  setupSummaryInteractions(tbody);
  applySummarySelectionStyles();
}

function notifySummaryRefreshError(message) {
  const now = Date.now();
  if (now - summaryState.errorToastAt < 5000) return;
  summaryState.errorToastAt = now;
  showToast(message, "warn");
}

function compactSummaryErrorReason(error) {
  const status = Number(error?.status || 0);
  let reason = String(error?.message || "").replace(/\s+/g, " ").trim();
  if (!reason) reason = status ? `HTTP ${status}` : "Okänt fel";
  if (status && !reason.includes(String(status))) reason = `HTTP ${status}: ${reason}`;
  return reason.length > 180 ? `${reason.slice(0, 177)}...` : reason;
}

function summaryRefreshContextLabel() {
  const day = DAYS[state.weekday] || `dag ${state.weekday}`;
  const areaName = state.areaId == null ? "Alla områden" : (areaById(state.areaId)?.name || `område ${state.areaId}`);
  return `${day}, vecka ${state.week}/${state.year}, ${areaName}`;
}

function summaryRefreshErrorMessage(error) {
  return `Summeringen kunde inte uppdateras just nu. Orsak: ${compactSummaryErrorReason(error)}. Kontext: ${summaryRefreshContextLabel()}.`;
}

function scheduleSummaryRefresh(delay = 90, { refreshCalculator = false } = {}) {
  clearSummaryRefreshTimer();
  summaryState.timer = setTimeout(() => {
    summaryState.timer = null;
    void refreshSummary();
  }, delay);
  if (refreshCalculator) {
    scheduleAutomaticCalculatorRefresh(Math.max(250, delay), { force: true });
  }
}


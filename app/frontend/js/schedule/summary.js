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

function renderSummaryRows(rows) {
  const tbody = document.getElementById("summaryBody");
  if (!tbody) return;

  const fragment = document.createDocumentFragment();
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td style="background: ${row.color}; padding: 5px;">${escapeHtml(row.activity_label)}</td>
      <td>${formatHours(row.hours)}</td>
      <td>${Number(row.persons_equiv).toFixed(1)}</td>`;
    fragment.appendChild(tr);
  });
  tbody.replaceChildren(fragment);
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


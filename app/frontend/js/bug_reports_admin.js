// @ts-check
// Buggrapporter-vyn: lista inskickade rapporter, spela upp rrweb-inspelningen
// och sätt status (sedd/klar). Nås via Verktyg-menyn (vy-id bugReports).
(function () {
  /** @type {{ activeId: number | null, replayer: any, events: any[] }} */
  const state = { activeId: null, replayer: null, events: [] };

  function statusLabel(status) {
    if (status === "seen") return '<span class="bug-status-seen">Sedd</span>';
    if (status === "done") return '<span class="bug-status-done">Klar</span>';
    return '<span class="bug-status-new">Ny</span>';
  }

  function formatBytes(bytes) {
    const value = Number(bytes || 0);
    if (value > 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
    if (value > 1024) return `${Math.round(value / 1024)} kB`;
    return `${value} B`;
  }

  function formatStamp(iso) {
    if (!iso) return "";
    return String(iso).replace("T", " ").slice(0, 16);
  }

  async function loadReports() {
    const body = document.getElementById("bugReportsBody");
    if (!body) return;
    try {
      const response = await window.api.get("/api/bug-reports");
      const reports = response?.reports || [];
      if (!reports.length) {
        body.innerHTML = '<tr><td colspan="6">Inga buggrapporter ännu. När användare klickar på 🐞-knappen hamnar rapporterna här.</td></tr>';
        return;
      }
      body.innerHTML = reports
        .map(
          (report) => `
            <tr data-report-id="${report.id}">
              <td>${formatStamp(report.created_at)}</td>
              <td>${escapeHtml(report.username || "okänd")}</td>
              <td>${escapeHtml(report.view_id || report.page_path || "")}</td>
              <td>${escapeHtml(report.note || "")}</td>
              <td>${statusLabel(report.status)}</td>
              <td>${formatBytes(report.events_bytes)}</td>
            </tr>
          `
        )
        .join("");
      body.querySelectorAll("tr[data-report-id]").forEach((row) => {
        row.addEventListener("click", () => {
          if (!(row instanceof HTMLElement)) return;
          body.querySelectorAll("tr").forEach((tr) => tr.classList.remove("active"));
          row.classList.add("active");
          void openReport(Number(row.dataset.reportId));
        });
      });
    } catch (error) {
      body.innerHTML = `<tr><td colspan="6">${escapeHtml(error instanceof Error ? error.message : "Kunde inte hämta buggrapporter.")}</td></tr>`;
    }
  }

  function playEvents() {
    const container = document.getElementById("bugReportPlayer");
    if (!container || !window.rrweb || !state.events.length) return;
    container.innerHTML = "";
    try {
      state.replayer = new window.rrweb.Replayer(state.events, {
        root: container,
        skipInactive: true,
      });
      state.replayer.play();
    } catch (error) {
      container.textContent = "Inspelningen kunde inte spelas upp i den här webbläsaren.";
      window.flowLog?.error?.(String(error), "Buggrapporter");
    }
  }

  async function openReport(reportId) {
    if (!reportId) return;
    state.activeId = reportId;
    const detail = document.getElementById("bugReportDetail");
    const title = document.getElementById("bugReportTitle");
    const meta = document.getElementById("bugReportMeta");
    const contextBox = document.getElementById("bugReportContext");
    if (!detail || !title || !meta) return;
    detail.hidden = false;
    title.textContent = `Rapport #${reportId}`;
    meta.textContent = "Laddar inspelning …";
    try {
      const report = await window.api.get(`/api/bug-reports/${reportId}`);
      state.events = JSON.parse(report.events_json || "[]");
      meta.textContent = [
        `Skickad ${formatStamp(report.created_at)} av ${report.username || "okänd"}`,
        report.view_id ? `vy: ${report.view_id}` : "",
        report.page_path ? `sida: ${report.page_path}` : "",
        report.note ? `notis: ${report.note}` : "",
      ]
        .filter(Boolean)
        .join(" | ");
      if (contextBox) {
        const context = report.context || {};
        const errors = [
          ...(context.console_errors || []).map((line) => `console: ${line}`),
          ...(context.js_errors || []).map((line) => `js: ${line}`),
        ];
        contextBox.hidden = errors.length === 0;
        contextBox.textContent = errors.join("\n");
      }
      playEvents();
    } catch (error) {
      meta.textContent = error instanceof Error ? error.message : "Kunde inte hämta rapporten.";
    }
  }

  async function setStatus(newStatus) {
    if (!state.activeId) return;
    try {
      await window.api.patch(`/api/bug-reports/${state.activeId}/status`, { status: newStatus });
      showToast(newStatus === "done" ? "Rapporten markerad som klar." : "Rapporten markerad som sedd.", "success", 2500);
      await loadReports();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Kunde inte uppdatera status.", "error", 6000);
    }
  }

  function init() {
    document.getElementById("bugReportReplay")?.addEventListener("click", playEvents);
    document.getElementById("bugReportMarkSeen")?.addEventListener("click", () => void setStatus("seen"));
    document.getElementById("bugReportMarkDone")?.addEventListener("click", () => void setStatus("done"));
    void loadReports();
  }

  (async () => {
    const user = await initPage("bugReports");
    if (!user) return;
    if (!(user.is_super_user || canViewPage(user, "bugReports"))) {
      window.location.href = "/index.html";
      return;
    }
    init();
  })();
})();

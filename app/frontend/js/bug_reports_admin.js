// @ts-check
// Buggrapporter-vyn: lista inskickade rapporter, spela upp rrweb-inspelningen,
// sätt status (Ny/Att göra/Klar) och ta bort rapporter — både per rad och i
// detaljpanelen. Nås via Verktyg-menyn (vy-id bugReports).
(function () {
  /** @type {{ activeId: number | null, replayer: any, events: any[] }} */
  const state = { activeId: null, replayer: null, events: [] };

  const STATUS_LABELS = { new: "Ny", seen: "Att göra", done: "Klar" };
  const STATUS_ORDER = ["new", "seen", "done"];

  function statusLabel(status) {
    if (status === "seen") return '<span class="bug-status-seen">Att göra</span>';
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

  function statusSelectHtml(report) {
    const options = STATUS_ORDER.map(
      (value) =>
        `<option value="${value}"${value === report.status ? " selected" : ""}>${STATUS_LABELS[value]}</option>`
    ).join("");
    return `<select class="bug-report-status-select" data-report-id="${report.id}" aria-label="Status för rapport #${report.id}">${options}</select>`;
  }

  async function loadReports() {
    const body = document.getElementById("bugReportsBody");
    if (!body) return;
    try {
      const response = await window.api.get("/api/bug-reports");
      const reports = response?.reports || [];
      if (!reports.length) {
        body.innerHTML = '<tr><td colspan="8">Inga buggrapporter ännu. När användare klickar på 🐞-knappen hamnar rapporterna här.</td></tr>';
        return;
      }
      body.innerHTML = reports
        .map(
          (report) => `
            <tr data-report-id="${report.id}">
              <td class="bug-report-id">#${report.id}</td>
              <td>${formatStamp(report.created_at)}</td>
              <td>${escapeHtml(report.username || "okänd")}</td>
              <td>${escapeHtml(report.view_id || report.page_path || "")}</td>
              <td>${escapeHtml(report.note || "")}</td>
              <td>${statusLabel(report.status)}</td>
              <td>${formatBytes(report.events_bytes)}</td>
              <td class="bug-report-actions">
                ${statusSelectHtml(report)}
                <button type="button" class="danger bug-report-delete" data-report-id="${report.id}">Ta bort</button>
              </td>
            </tr>
          `
        )
        .join("");
      body.querySelectorAll("tr[data-report-id]").forEach((row) => {
        row.addEventListener("click", (event) => {
          if (!(row instanceof HTMLElement)) return;
          // Klick på radens egna kontroller ska inte öppna uppspelningen.
          if (event.target instanceof Element && event.target.closest(".bug-report-actions")) return;
          body.querySelectorAll("tr").forEach((tr) => tr.classList.remove("active"));
          row.classList.add("active");
          void openReport(Number(row.dataset.reportId));
        });
      });
      body.querySelectorAll("select.bug-report-status-select").forEach((select) => {
        select.addEventListener("change", () => {
          if (!(select instanceof HTMLSelectElement)) return;
          void setStatus(Number(select.dataset.reportId), select.value);
        });
      });
      body.querySelectorAll("button.bug-report-delete").forEach((button) => {
        button.addEventListener("click", () => {
          if (!(button instanceof HTMLElement)) return;
          confirmDelete(Number(button.dataset.reportId));
        });
      });
    } catch (error) {
      body.innerHTML = `<tr><td colspan="7">${escapeHtml(error instanceof Error ? error.message : "Kunde inte hämta buggrapporter.")}</td></tr>`;
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

  function closeDetail() {
    state.activeId = null;
    state.events = [];
    const detail = document.getElementById("bugReportDetail");
    if (detail) detail.hidden = true;
    const player = document.getElementById("bugReportPlayer");
    if (player) player.innerHTML = "";
  }

  async function setStatus(reportId, newStatus) {
    if (!reportId) return;
    try {
      await window.api.patch(`/api/bug-reports/${reportId}/status`, { status: newStatus });
      showToast(`Rapport #${reportId} markerad som ${STATUS_LABELS[newStatus]?.toLowerCase() || newStatus}.`, "success", 2500);
      await loadReports();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Kunde inte uppdatera status.", "error", 6000);
      await loadReports();
    }
  }

  function confirmDelete(reportId) {
    if (!reportId) return;
    document.getElementById("bug-report-delete-backdrop")?.remove();
    const backdrop = document.createElement("div");
    backdrop.id = "bug-report-delete-backdrop";
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="bug-report-delete-title">
        <h3 id="bug-report-delete-title">Ta bort buggrapport</h3>
        <p>Rapport #${reportId} och dess inspelning tas bort permanent. Detta går inte att ångra.</p>
        <div class="modal-actions">
          <button type="button" class="secondary" id="bug-report-delete-cancel">Avbryt</button>
          <button type="button" class="danger" id="bug-report-delete-confirm">Ta bort</button>
        </div>
      </div>
    `;
    document.body.appendChild(backdrop);
    document.getElementById("bug-report-delete-cancel")?.addEventListener("click", () => backdrop.remove());
    document.getElementById("bug-report-delete-confirm")?.addEventListener("click", () => {
      backdrop.remove();
      void deleteReport(reportId);
    });
  }

  async function deleteReport(reportId) {
    try {
      await window.api.del(`/api/bug-reports/${reportId}`);
      showToast(`Rapport #${reportId} borttagen.`, "success", 2500);
      if (state.activeId === reportId) closeDetail();
      await loadReports();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Kunde inte ta bort rapporten.", "error", 6000);
    }
  }

  function init() {
    document.getElementById("bugReportReplay")?.addEventListener("click", playEvents);
    document.getElementById("bugReportMarkSeen")?.addEventListener("click", () => {
      if (state.activeId) void setStatus(state.activeId, "seen");
    });
    document.getElementById("bugReportMarkDone")?.addEventListener("click", () => {
      if (state.activeId) void setStatus(state.activeId, "done");
    });
    document.getElementById("bugReportDelete")?.addEventListener("click", () => {
      if (state.activeId) confirmDelete(state.activeId);
    });
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

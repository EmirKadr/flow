let productivityReport = null;
let productivityFileStatus = null;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function formatNumber(value, decimals = 0) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString("sv-SE", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatMetric(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  const decimals = Math.abs(Number(value)) < 10 && !Number.isInteger(Number(value)) ? 1 : 0;
  return formatNumber(value, decimals);
}

function formatPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return (Number(value) * 100).toLocaleString("sv-SE", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }) + " %";
}

function formatTimestamp(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("sv-SE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function metricClass(value) {
  if (value == null) return "";
  if (value >= 1) return " good";
  if (value >= 0.85) return " warn";
  return " low";
}

function activeGroupFilter() {
  return document.getElementById("productivityGroupFilter").value;
}

function activeSearch() {
  return document.getElementById("productivitySearch").value.trim().toLowerCase();
}

function sectionMatches(section, search) {
  if (!search) return true;
  if (section.title.toLowerCase().includes(search)) return true;
  return section.rows.some((row) => row.user.toLowerCase().includes(search));
}

function filteredRows(section, search) {
  if (!search || section.title.toLowerCase().includes(search)) return section.rows;
  return section.rows.filter((row) => row.user.toLowerCase().includes(search));
}

function renderSummary(report) {
  const summary = report.summary || {};
  const items = [
    ["Rader", formatNumber(summary.total_rows)],
    ["Timmar", formatNumber(summary.worked_hours)],
    ["Rader/tim", formatMetric(summary.rows_per_hour)],
    ["Snitt mot mål", formatPercent(summary.average_productivity_pct)],
  ];

  document.getElementById("productivitySummary").innerHTML = items.map(([label, value]) => `
    <div class="productivity-kpi">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function renderSources(report) {
  const sources = Object.values(report.sources || {}).filter((source) => source.visible !== false);
  document.getElementById("productivitySources").innerHTML = sources.map((source) => `
    <div class="productivity-source">
      <span>${escapeHtml(source.label)}</span>
      <strong>${escapeHtml(source.name)}</strong>
      <small>${formatNumber(source.rows)} rader</small>
    </div>
  `).join("");
}

function renderFileStatus(status) {
  productivityFileStatus = status;
  const files = Object.values(status.files || {});
  const filled = files.filter((file) => file.uploaded).length;
  const required = files.filter((file) => file.required).length;
  document.getElementById("productivityUploadCount").textContent = `${filled}/${required} uppladdade`;

  document.getElementById("productivityFileSlots").innerHTML = files.map((file) => `
    <div class="productivity-file-slot ${file.uploaded ? "is-uploaded" : ""}">
      <div class="productivity-file-main">
        <div class="productivity-file-label">${escapeHtml(file.label)}${file.required ? '<span class="req">*</span>' : ""}</div>
        <div class="productivity-file-name">
          ${file.uploaded ? escapeHtml(file.name) : '<span class="muted">Ingen fil vald</span>'}
        </div>
        ${file.uploaded ? `<div class="productivity-file-meta">${escapeHtml(file.size_label || "")}</div>` : ""}
      </div>
      <div class="productivity-file-actions">
        <span class="status-pill ${file.uploaded ? "ok" : "none"}">${file.uploaded ? "Uppladdad" : "Ej fil"}</span>
        <button type="button" class="btn-sm productivity-slot-upload" data-file-key="${escapeHtml(file.key)}">Välj</button>
        <button type="button" class="btn-sm danger productivity-slot-clear" data-file-key="${escapeHtml(file.key)}" ${file.uploaded ? "" : "disabled"}>×</button>
      </div>
    </div>
  `).join("");

  document.querySelectorAll(".productivity-slot-upload").forEach((button) => {
    button.addEventListener("click", () => document.getElementById("productivityUploadInput").click());
  });
  document.querySelectorAll(".productivity-slot-clear").forEach((button) => {
    button.addEventListener("click", () => clearProductivityFile(button.dataset.fileKey));
  });

  const uploadStatus = document.getElementById("productivityUploadStatus");
  uploadStatus.textContent = status.ready
    ? "Alla produktivitetsunderlag är uppladdade."
    : "Produktivitet kan räknas när de markerade filerna är uppladdade.";
}

function clearReportContent() {
  productivityReport = null;
  document.getElementById("productivitySummary").innerHTML = "";
  document.getElementById("productivitySources").innerHTML = "";
  document.getElementById("productivityContent").innerHTML = "";
}

async function loadProductivityFileStatus() {
  const status = await api.get("/api/productivity/files");
  renderFileStatus(status);
  return status;
}

function setProductivityWaitingStatus(fileStatus) {
  clearReportContent();
  document.getElementById("productivityStatus").textContent = fileStatus?.ready
    ? "Underlagen är uppladdade. Klicka Uppdatera för att beräkna produktivitet."
    : "Saknar produktivitetsunderlag.";
}

async function initializeProductivityPage() {
  const status = document.getElementById("productivityStatus");
  status.textContent = "Kontrollerar underlag...";
  try {
    const fileStatus = await loadProductivityFileStatus();
    setProductivityWaitingStatus(fileStatus);
  } catch (error) {
    status.textContent = error.message || "Kunde inte kontrollera underlag.";
    showToast(status.textContent, "error", 7000);
  }
}

function renderGroupFilter(report) {
  const select = document.getElementById("productivityGroupFilter");
  const current = select.value || "all";
  select.innerHTML = '<option value="all">Alla</option>' + (report.groups || [])
    .map((group) => `<option value="${escapeHtml(group.id)}">${escapeHtml(group.title)}</option>`)
    .join("");
  select.value = Array.from(select.options).some((option) => option.value === current) ? current : "all";
}

function renderSection(section, hours, search) {
  const rows = filteredRows(section, search);
  const hourHeaders = hours.map((hour) => `<th>${String(hour).padStart(2, "0")}</th>`).join("");
  const emptyRow = `
    <tr>
      <td colspan="${hours.length + 9}" class="muted-cell">Inga rader</td>
    </tr>`;

  const body = rows.length ? rows.map((row) => {
    const hourCells = hours.map((hour) => {
      const value = row.hourly[String(hour)] || "";
      return `<td class="${value ? "has-work" : ""}">${value ? escapeHtml(value) : ""}</td>`;
    }).join("");
    return `
      <tr>
        <td class="name">${escapeHtml(row.user)}</td>
        ${hourCells}
        <td>${formatNumber(row.total_rows)}</td>
        <td>${row.total_kolli == null ? "-" : formatNumber(row.total_kolli)}</td>
        <td>${row.total_weight == null ? "-" : formatNumber(row.total_weight, 1)}</td>
        <td>${formatMetric(row.rows_per_hour)}</td>
        <td>${formatMetric(row.worked_hours)}</td>
        <td>${formatMetric(row.target_per_hour)}</td>
        <td class="productivity-pct${metricClass(row.productivity_pct)}">${formatPercent(row.productivity_pct)}</td>
      </tr>`;
  }).join("") : emptyRow;

  return `
    <section class="productivity-panel">
      <div class="productivity-panel-header">
        <div>
          <h3>${escapeHtml(section.title)}</h3>
          <span>${escapeHtml(section.target_company)} · ${escapeHtml(section.process)}</span>
        </div>
        <div class="productivity-panel-score${metricClass(section.productivity_pct)}">
          ${formatPercent(section.productivity_pct)}
        </div>
      </div>
      <div class="table-wrap productivity-table-wrap">
        <table class="productivity-table">
          <thead>
            <tr>
              <th class="name">Användare</th>
              ${hourHeaders}
              <th>Rader</th>
              <th>Kolli</th>
              <th>Vikt</th>
              <th>Rad/tim</th>
              <th>Timmar</th>
              <th>Mål</th>
              <th>%</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </section>`;
}

function renderContent() {
  if (!productivityReport) return;
  const content = document.getElementById("productivityContent");
  const groupFilter = activeGroupFilter();
  const search = activeSearch();
  const hours = productivityReport.hours || [];

  const groups = (productivityReport.groups || [])
    .filter((group) => groupFilter === "all" || group.id === groupFilter)
    .map((group) => ({
      ...group,
      sections: group.sections.filter((section) => sectionMatches(section, search)),
    }))
    .filter((group) => group.sections.length);

  if (!groups.length) {
    content.innerHTML = '<div class="empty-state">Ingen produktivitet matchade filtret.</div>';
    return;
  }

  content.innerHTML = groups.map((group) => `
    <section class="productivity-group">
      <h2>${escapeHtml(group.title)}</h2>
      <div class="productivity-section-list">
        ${group.sections.map((section) => renderSection(section, hours, search)).join("")}
      </div>
    </section>
  `).join("");
}

async function loadProductivity() {
  const status = document.getElementById("productivityStatus");
  const dateInput = document.getElementById("productivityDate");
  status.textContent = "Kontrollerar underlag...";
  try {
    const fileStatus = await loadProductivityFileStatus();
    if (!fileStatus.ready) {
      clearReportContent();
      status.textContent = "Saknar produktivitetsunderlag.";
      return;
    }
    status.textContent = "Läser produktivitet...";
    const params = new URLSearchParams();
    if (dateInput.value) params.set("date", dateInput.value);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    productivityReport = await api.get(`/api/productivity${suffix}`);
    if (productivityReport.date) dateInput.value = productivityReport.date;
    const dates = productivityReport.available_dates || [];
    if (dates.length) {
      dateInput.min = dates[0];
      dateInput.max = dates[dates.length - 1];
    }
    renderGroupFilter(productivityReport);
    renderSummary(productivityReport);
    renderSources(productivityReport);
    renderContent();
    status.textContent = `${productivityReport.date} · uppdaterad ${formatTimestamp(productivityReport.generated_at)}`;
  } catch (error) {
    productivityReport = null;
    document.getElementById("productivitySummary").innerHTML = "";
    document.getElementById("productivitySources").innerHTML = "";
    document.getElementById("productivityContent").innerHTML = "";
    status.textContent = error.message || "Kunde inte läsa produktivitet.";
    showToast(status.textContent, "error", 7000);
  }
}

async function uploadProductivityFiles(files) {
  const incoming = Array.from(files || []);
  if (!incoming.length) return;

  const uploadStatus = document.getElementById("productivityUploadStatus");
  uploadStatus.textContent = "Laddar upp filer...";
  try {
    const saved = [];
    const unknown = [];
    let latestStatus = null;
    for (const [index, file] of incoming.entries()) {
      uploadStatus.textContent = `Laddar upp ${index + 1}/${incoming.length}: ${file.name}`;
      const result = await api.postFile(
        `/api/productivity/files/raw?filename=${encodeURIComponent(file.name)}`,
        file,
      );
      saved.push(...(result.saved || []));
      unknown.push(...(result.unknown || []));
      latestStatus = result.status;
      renderFileStatus(result.status);
    }

    const visibleSaved = saved.filter((file) => file.visible !== false).length;
    const hiddenSaved = saved.filter((file) => file.visible === false).length;
    const parts = [];
    if (visibleSaved) parts.push(`${visibleSaved} fil(er) uppladdade`);
    if (hiddenSaved) parts.push("KPI-mål uppdaterat i bakgrunden");
    if (unknown.length) parts.push(`Okänd filtyp: ${unknown.join(", ")}`);
    const message = parts.join(". ") || "Ingen fil uppdaterades.";
    if (latestStatus) setProductivityWaitingStatus(latestStatus);
    uploadStatus.textContent = message;
  } catch (error) {
    uploadStatus.textContent = error.message || "Kunde inte ladda upp filer.";
    showToast(uploadStatus.textContent, "error", 7000);
  }
}

async function clearProductivityFile(fileKey) {
  if (!fileKey) return;
  try {
    const status = await api.del(`/api/productivity/files/${encodeURIComponent(fileKey)}`);
    renderFileStatus(status);
    clearReportContent();
    document.getElementById("productivityStatus").textContent = "Saknar produktivitetsunderlag.";
  } catch (error) {
    showToast(error.message || "Kunde inte rensa filen.", "error", 7000);
  }
}

function setupUploadDropzone() {
  const panel = document.getElementById("productivityUploadPanel");
  let dragDepth = 0;

  panel.addEventListener("dragenter", (event) => {
    if (!Array.from(event.dataTransfer?.types || []).includes("Files")) return;
    event.preventDefault();
    dragDepth += 1;
    panel.classList.add("is-dragging");
  });
  panel.addEventListener("dragover", (event) => {
    if (!Array.from(event.dataTransfer?.types || []).includes("Files")) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  });
  panel.addEventListener("dragleave", () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) panel.classList.remove("is-dragging");
  });
  panel.addEventListener("drop", (event) => {
    if (!Array.from(event.dataTransfer?.types || []).includes("Files")) return;
    event.preventDefault();
    dragDepth = 0;
    panel.classList.remove("is-dragging");
    uploadProductivityFiles(event.dataTransfer.files);
  });
}

(async () => {
  const user = await initPage("productivity", { requireSuperUser: true });
  if (!user) return;

  document.getElementById("refreshProductivityBtn").addEventListener("click", loadProductivity);
  document.getElementById("productivityUploadBtn").addEventListener("click", () => {
    document.getElementById("productivityUploadInput").click();
  });
  document.getElementById("productivityUploadInput").addEventListener("change", (event) => {
    uploadProductivityFiles(event.target.files);
    event.target.value = "";
  });
  document.getElementById("productivityDate").addEventListener("change", loadProductivity);
  document.getElementById("productivityGroupFilter").addEventListener("change", renderContent);
  document.getElementById("productivitySearch").addEventListener("input", renderContent);
  setupUploadDropzone();
  await initializeProductivityPage();
})();

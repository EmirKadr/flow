// @ts-check
// Arkivstatus: superuser-dashboard för arkiv-cachen (DuckDB) + produktivitetsbygget.
// Läs-bara vy som pollar /api/data-fetch/archive-cache/status.

const ARCHIVE_STATUS_REFRESH_MS = 30_000;

function archiveEsc(value) {
  return String(value ?? "–").replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

function archiveCoverageClass(view) {
  if (view.fully_covered) return "cov-ok";
  if (view.seeded) return "cov-warn";
  return "cov-err";
}

function renderArchiveStatus(payload) {
  const summary = document.getElementById("archiveCacheSummary");
  const table = document.getElementById("archiveCoverageTable");
  const body = document.getElementById("archiveCoverageBody");
  const logBox = document.getElementById("archiveSyncLog");

  if (!payload.enabled) {
    summary.textContent = "Arkiv-cachen är avstängd (ARCHIVE_CACHE_ENABLED är av) – allt läses via API/dblog.";
    table.hidden = true;
    logBox.textContent = "–";
  } else {
    const tenants = payload.tenants || [];
    const total = tenants.reduce((acc, t) => acc + (t.views || []).length, 0);
    const done = tenants.reduce((acc, t) => acc + (t.views || []).filter((v) => v.fully_covered).length, 0);
    summary.textContent = `Idag ${payload.today} · ${tenants.length} tenant(er) · ${done}/${total} vyer fullt täckta.`;

    const rows = [];
    for (const tenant of tenants) {
      for (const view of tenant.views || []) {
        const cls = archiveCoverageClass(view);
        const state = view.fully_covered ? "täckt" : (view.seeded ? `${view.missing_days} saknas` : "ej seedad");
        rows.push(`<tr>
          <td>${archiveEsc(tenant.tenant)}</td>
          <td>${archiveEsc(view.view)}</td>
          <td>${archiveEsc(view.ingested_start)}</td>
          <td>${archiveEsc(view.ingested_end)}</td>
          <td>${archiveEsc(view.covered_end)}</td>
          <td class="${cls}">${archiveEsc(state)}</td>
          <td>${view.deep_backfill_remaining_days ? `${archiveEsc(view.deep_backfill_remaining_days)} dgr kvar bakåt` : "klar bakåt"}</td>
        </tr>`);
      }
      for (const snap of tenant.snapshots || []) {
        rows.push(`<tr>
          <td>${archiveEsc(tenant.tenant)}</td>
          <td>${archiveEsc(snap.view || snap.name)} (snapshot)</td>
          <td colspan="3">${archiveEsc(snap.refreshed_at || snap.updated_at || "aldrig uppdaterad")}</td>
          <td class="${snap.rows ? "cov-ok" : "cov-warn"}">${archiveEsc(snap.rows ?? "–")} rader</td>
          <td></td>
        </tr>`);
      }
    }
    body.innerHTML = rows.join("");
    table.hidden = rows.length === 0;

    const logRows = [];
    for (const tenant of tenants) {
      for (const entry of tenant.recent_syncs || []) {
        logRows.push(
          `<div><strong>${archiveEsc(entry.ts)}</strong> · ${archiveEsc(tenant.tenant)} · ${archiveEsc(entry.view)} · ` +
          `${archiveEsc(entry.source)} ${archiveEsc(entry.start_date)}–${archiveEsc(entry.end_date)} · ` +
          `${archiveEsc(entry.rows)} rader · ${archiveEsc(entry.status)}</div>`
        );
      }
    }
    logBox.innerHTML = logRows.length ? logRows.join("") : "Inga synkar loggade ännu.";
  }

  const prod = payload.productivity || {};
  const prodSummary = document.getElementById("productivitySummary");
  const prodBody = document.getElementById("productivityBody");
  const snaps = prod.snapshots || {};
  const today = prod.today || {};
  const backfill = prod.backfill || {};
  const prebuild = prod.prebuild || {};
  prodSummary.textContent = snaps.days != null
    ? `${snaps.days} snapshotdagar på disk (${snaps.first ?? "–"} → ${snaps.last ?? "–"}), ${snaps.overview_reports ?? 0} förbyggda översiktsrapporter.`
    : "Kunde inte läsa snapshotkatalogen.";
  prodBody.innerHTML = [
    ["Dagens snapshot", today.ready ? `klar (senast synkad ${today.last_sync_at ?? "?"})` : (today.last_sync_at ? `ej klar, senast ${today.last_sync_at}` : "ingen ännu")],
    ["Historisk backfill", backfill.next_cursor_date ? `nere på ${backfill.next_cursor_date} (senast körd ${backfill.last_run_date ?? "?"})` : "ingen körning loggad"],
    ["Nattligt förbygge", prebuild.last_run_date ? `senast ${prebuild.last_run_date} (${(prebuild.dates || []).length} dagar byggda)` : "ingen körning loggad"],
  ].map(([label, value]) => `<tr><th>${archiveEsc(label)}</th><td>${archiveEsc(value)}</td></tr>`).join("");
}

async function refreshArchiveStatus() {
  const info = document.getElementById("archiveRefreshInfo");
  try {
    const payload = await api.get("/api/query-data/archive-cache/status");
    renderArchiveStatus(payload);
    info.textContent = `Uppdaterad ${new Date().toLocaleTimeString("sv-SE")} · uppdateras var 30 s.`;
  } catch (error) {
    info.textContent = `Kunde inte hämta status: ${error?.message || error}`;
  }
}

(async () => {
  const user = await initPage("archiveStatus");
  if (!user?.is_super_user) {
    window.location.href = "/index.html";
    return;
  }
  await refreshArchiveStatus();
  setInterval(refreshArchiveStatus, ARCHIVE_STATUS_REFRESH_MS);
})();

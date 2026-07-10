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

// ===========================================================================
// ASK-vy-diagnostik (mätverktyg). Live-test av alla arkiv-/live-vyer × valda
// tenants mot 1–3 bas-URL:er via /api/query-data/archive-cache/diagnostics/*.
// ===========================================================================

const DIAG_CONCURRENCY = 4;
let diagConfig = null;
let diagBuilt = false;
const diagResults = { 1: new Map(), 2: new Map(), 3: new Map() };
const diagRunning = { 1: false, 2: false, 3: false };

function diagSafeId(value) {
  return String(value).replace(/[^A-Za-z0-9_-]/g, "_");
}

function diagCellId(urlIndex, view, tenant) {
  return `diagc-${urlIndex}-${diagSafeId(view)}-${diagSafeId(tenant)}`;
}

function diagKindLabel(kind) {
  return kind === "archive" ? "Arkiv" : kind === "live" ? "Live" : "Övrigt";
}

function diagSelectedTenants() {
  return Array.from(document.querySelectorAll(".diag-tenant:checked")).map(
    (el) => /** @type {HTMLInputElement} */ (el).value
  );
}

async function diagLoadConfig() {
  if (!diagConfig) {
    diagConfig = await api.get("/api/query-data/archive-cache/diagnostics/config");
  }
  return diagConfig;
}

function diagClassify(res) {
  if (res.ok) return { cls: "diag-c-ok", text: `OK·${res.row_count}` };
  const code = res.http_status;
  if (code === 403) return { cls: "diag-c-warn", text: "403" };
  if (code === 404) return { cls: "diag-c-gray", text: "404" };
  if (code) return { cls: "diag-c-err", text: String(code) };
  const err = res.error || "fel";
  const short = /timeout/i.test(err) ? "TIMEOUT" : /anslut|connect/i.test(err) ? "nås ej" : "fel";
  return { cls: "diag-c-err", text: short };
}

function diagPanelHtml(url) {
  const varLine = url.configured
    ? `URL-mönster: <b>${archiveEsc(url.pattern)}</b>`
    : "<b>Ej konfigurerad</b> – sätt variabeln i Octopus för att kunna testa denna URL.";
  return `
    <div class="diag-var">Variabel: <b>${archiveEsc(url.env_name)}</b><br>${varLine}</div>
    <div class="diag-actions">
      <button type="button" class="diag-btn diag-run" ${url.configured ? "" : "disabled"}>▶ Kör test</button>
      <button type="button" class="diag-btn diag-download" disabled>⬇ Ladda ner rapport (HTML)</button>
      <span class="diag-progress"></span>
    </div>
    <div class="diag-sum"></div>
    <div class="diag-matrix-wrap" style="overflow-x:auto"></div>`;
}

function diagBuildUI(cfg) {
  document.getElementById("diagMeta").textContent =
    `Idag ${cfg.today} · ${cfg.views.length} vyer · ${cfg.tenants.length} tenants · ` +
    "arkiv- och live-vyer testas på olika datum (arkiv äldre än sin retention, live = igår).";

  const tbox = document.getElementById("diagTenants");
  tbox.innerHTML =
    `<label><input type="checkbox" id="diagAllTenants" checked> <b>Markera alla</b></label>` +
    cfg.tenants
      .map((t) => `<label><input type="checkbox" class="diag-tenant" value="${archiveEsc(t)}" checked> ${archiveEsc(t)}</label>`)
      .join("");
  document.getElementById("diagAllTenants").addEventListener("change", (e) => {
    const checked = /** @type {HTMLInputElement} */ (e.target).checked;
    document.querySelectorAll(".diag-tenant").forEach((cb) => {
      /** @type {HTMLInputElement} */ (cb).checked = checked;
    });
  });

  const tabsBox = document.getElementById("diagTabs");
  const panelsBox = document.getElementById("diagPanels");
  tabsBox.innerHTML = "";
  panelsBox.innerHTML = "";
  cfg.urls.forEach((url, i) => {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = "diag-tab" + (i === 0 ? " active" : "") + (url.configured ? "" : " unset");
    tab.textContent = url.env_name + (url.configured ? "" : " (ej satt)");
    tab.dataset.url = String(url.index);
    tab.addEventListener("click", () => diagActivateTab(url.index));
    tabsBox.appendChild(tab);

    const panel = document.createElement("div");
    panel.className = "diag-panel" + (i === 0 ? " active" : "");
    panel.dataset.url = String(url.index);
    panel.innerHTML = diagPanelHtml(url);
    panelsBox.appendChild(panel);
    panel.querySelector(".diag-run").addEventListener("click", () => diagRun(url.index));
    panel.querySelector(".diag-download").addEventListener("click", () => diagDownload(url.index));
  });
  diagBuilt = true;
}

function diagActivateTab(urlIndex) {
  const want = String(urlIndex);
  document.querySelectorAll(".diag-tab").forEach((t) =>
    t.classList.toggle("active", /** @type {HTMLElement} */ (t).dataset.url === want)
  );
  document.querySelectorAll(".diag-panel").forEach((p) =>
    p.classList.toggle("active", /** @type {HTMLElement} */ (p).dataset.url === want)
  );
}

function diagRenderSkeleton(panel, views, tenants, urlIndex) {
  const head =
    `<tr><th>Vy</th><th>Typ</th><th>Datumkol</th><th>Provdag</th>` +
    tenants.map((t) => `<th>${archiveEsc(t)}</th>`).join("") + `</tr>`;
  const rows = views
    .map((v) => {
      const cells = tenants
        .map((t) => `<td id="${diagCellId(urlIndex, v.id, t)}" class="diag-c-pend">…</td>`)
        .join("");
      return `<tr><td class="dv">${archiveEsc(v.id)}</td><td class="dk">${diagKindLabel(v.kind)}</td>` +
        `<td class="dk">${archiveEsc(v.date_column || "—")}</td><td class="dk">${archiveEsc(v.date || "—")}</td>${cells}</tr>`;
    })
    .join("");
  panel.querySelector(".diag-matrix-wrap").innerHTML =
    `<table class="diag-matrix"><thead>${head}</thead><tbody>${rows}</tbody></table>`;
}

function diagFillCell(cell, res) {
  const { cls, text } = diagClassify(res);
  cell.className = cls;
  const ms = res.elapsed_ms != null ? `${res.elapsed_ms} ms` : "";
  cell.innerHTML = `${archiveEsc(text)}<div style="font-size:9px;opacity:.7">${archiveEsc(ms)}</div>`;
  cell.title = `${res.view || ""} @ ${res.tenant || ""}\n${text}${ms ? " · " + ms : ""}${res.error ? "\n" + res.error : ""}`;
}

function diagRenderSummary(panel, views, tenants, urlIndex) {
  const map = diagResults[urlIndex];
  panel.querySelector(".diag-sum").innerHTML = tenants
    .map((t) => {
      let ok = 0, err = 0, warn = 0, gray = 0;
      for (const v of views) {
        const r = map.get(`${v.id}|${t}`);
        if (!r) continue;
        const cls = diagClassify(r).cls;
        if (cls === "diag-c-ok") ok++;
        else if (cls === "diag-c-warn") warn++;
        else if (cls === "diag-c-gray") gray++;
        else err++;
      }
      return `<span class="chip"><b>${archiveEsc(t)}</b> ${ok}/${err}` +
        `${warn ? `/${warn}·403` : ""}${gray ? `/${gray}·404` : ""}</span>`;
    })
    .join("");
}

async function diagPool(items, limit, worker) {
  let cursor = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (cursor < items.length) {
      const idx = cursor++;
      await worker(items[idx]);
    }
  });
  await Promise.all(runners);
}

async function diagRun(urlIndex) {
  if (diagRunning[urlIndex]) return;
  const cfg = diagConfig;
  const tenants = diagSelectedTenants();
  const panel = document.querySelector(`.diag-panel[data-url="${urlIndex}"]`);
  const progress = panel.querySelector(".diag-progress");
  const runBtn = /** @type {HTMLButtonElement} */ (panel.querySelector(".diag-run"));
  const dlBtn = /** @type {HTMLButtonElement} */ (panel.querySelector(".diag-download"));
  if (!tenants.length) { progress.textContent = "Välj minst en tenant."; return; }

  diagRunning[urlIndex] = true;
  runBtn.disabled = true;
  dlBtn.disabled = true;
  diagResults[urlIndex] = new Map();
  diagRenderSkeleton(panel, cfg.views, tenants, urlIndex);

  const jobs = [];
  for (const v of cfg.views) for (const t of tenants) jobs.push({ view: v.id, tenant: t });
  let done = 0;
  progress.textContent = `0/${jobs.length} klara …`;

  await diagPool(jobs, DIAG_CONCURRENCY, async (job) => {
    let res;
    try {
      res = await api.get(
        `/api/query-data/archive-cache/diagnostics/probe?url=${urlIndex}` +
        `&tenant=${encodeURIComponent(job.tenant)}&view=${encodeURIComponent(job.view)}`
      );
    } catch (e) {
      res = { ok: false, error: e?.message || String(e), http_status: null, row_count: null, elapsed_ms: null };
    }
    res.view = res.view || job.view;
    res.tenant = res.tenant || job.tenant;
    diagResults[urlIndex].set(`${job.view}|${job.tenant}`, res);
    const cell = document.getElementById(diagCellId(urlIndex, job.view, job.tenant));
    if (cell) diagFillCell(cell, res);
    done++;
    progress.textContent = `${done}/${jobs.length} klara …`;
  });

  progress.textContent = `Klart: ${done}/${jobs.length} anrop mot ${cfg.urls.find((u) => u.index === urlIndex)?.env_name}.`;
  diagRenderSummary(panel, cfg.views, tenants, urlIndex);
  dlBtn.disabled = false;
  runBtn.disabled = false;
  diagRunning[urlIndex] = false;
}

function diagBuildReportHtml(urlIndex) {
  const cfg = diagConfig;
  const url = cfg.urls.find((u) => u.index === urlIndex);
  const tenants = diagSelectedTenants();
  const map = diagResults[urlIndex];
  const esc = archiveEsc;

  const stats = tenants
    .map((t) => {
      let ok = 0, err = 0, warn = 0, gray = 0;
      for (const v of cfg.views) {
        const r = map.get(`${v.id}|${t}`);
        if (!r) continue;
        const cls = diagClassify(r).cls;
        if (cls === "diag-c-ok") ok++;
        else if (cls === "diag-c-warn") warn++;
        else if (cls === "diag-c-gray") gray++;
        else err++;
      }
      return `<div class="stat"><b>${esc(t)}</b><span class="s-ok">${ok}</span>/<span class="s-err">${err}</span>` +
        `${warn ? `/<span class="s-warn">${warn}·403</span>` : ""}${gray ? `/<span class="s-gray">${gray}·404</span>` : ""}</div>`;
    })
    .join("");

  const head = `<tr><th>Vy</th><th>Typ</th><th>Datumkol</th><th>Provdag</th>${tenants.map((t) => `<th>${esc(t)}</th>`).join("")}</tr>`;
  const rows = cfg.views
    .map((v) => {
      const cells = tenants
        .map((t) => {
          const r = map.get(`${v.id}|${t}`);
          if (!r) return `<td class="gray">–</td>`;
          const { cls, text } = diagClassify(r);
          const short = cls.replace("diag-c-", "");
          const ms = r.elapsed_ms != null ? `<div class="ms">${r.elapsed_ms} ms</div>` : "";
          return `<td class="${short}" title="${esc(r.error || "")}">${esc(text)}${ms}</td>`;
        })
        .join("");
      return `<tr><td class="v">${esc(v.id)}</td><td class="k">${diagKindLabel(v.kind)}</td>` +
        `<td class="c">${esc(v.date_column || "—")}</td><td class="c">${esc(v.date || "—")}</td>${cells}</tr>`;
    })
    .join("");

  return `<!doctype html><html lang="sv"><head><meta charset="utf-8">
<title>ASK-diagnostik — ${esc(url.env_name)} — ${esc(cfg.today)}</title>
<style>
body{margin:0;padding:24px;background:#f6f7f9;color:#1c2330;font:13px/1.5 "Segoe UI",system-ui,sans-serif}
h1{font-size:20px;margin:0 0 4px}.sub{color:#5b6572;margin:0 0 6px}
.var{font-family:Consolas,monospace;background:#eef1f5;border:1px solid #d0d7e2;border-radius:6px;padding:8px 10px;margin:8px 0 14px;word-break:break-all}
.stats{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px;font-size:12px}
.stat{background:#fff;border:1px solid #d0d7e2;border-radius:8px;padding:5px 9px}.stat b{margin-right:6px}
.s-ok{color:#1a7f5c}.s-err{color:#c0392b}.s-warn{color:#8a6d1f}.s-gray{color:#8792a2}
table{border-collapse:collapse;font-size:12px;background:#fff}
th,td{text-align:center;padding:5px 8px;border:1px solid #d0d7e2;white-space:nowrap}
th{color:#5b6572;font-size:11px}td.v{font-family:Consolas,monospace;text-align:left}
td.k,td.c{color:#5b6572;text-align:left;font-size:11px}
td.ok{color:#1a7f5c;background:#e9f6f0}td.err{color:#c0392b;background:#fbeeec;font-weight:600}
td.warn{color:#8a6d1f;background:#fbf4e4}td.gray{color:#8792a2;background:#eef1f5}
.ms{font-size:9px;opacity:.7}.note{color:#5b6572;font-size:12px;margin-top:12px}
</style></head><body>
<h1>ASK-vy-diagnostik</h1>
<p class="sub">Bas-URL-variabel: <b>${esc(url.env_name)}</b> · genererad ${esc(cfg.today)} · ${tenants.length} tenants × ${cfg.views.length} vyer.</p>
<div class="var">${url.configured ? esc(url.pattern) : "(ej konfigurerad)"}</div>
<div class="stats">${stats}</div>
<table><thead>${head}</thead><tbody>${rows}</tbody></table>
<p class="note">Arkiv-vyer (dblog_*) testas på en dag äldre än sin retention; live-vyer (v_ask_* m.fl.) på gårdagen – de kan därför inte dela datum. Format: <b>OK·rader</b> / HTTP-kod / TIMEOUT / nås ej, med svarstid i ms. Provdag per vy visas i kolumnen "Provdag".</p>
</body></html>`;
}

function diagDownload(urlIndex) {
  const html = diagBuildReportHtml(urlIndex);
  const blob = new Blob([html], { type: "text/html" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  const env = diagConfig.urls.find((u) => u.index === urlIndex)?.env_name || `url${urlIndex}`;
  link.download = `ask-diagnostik-${env}-${diagConfig.today}.html`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

function diagOpen() {
  document.getElementById("diagOverlay").classList.add("open");
  diagLoadConfig()
    .then((cfg) => { if (!diagBuilt) diagBuildUI(cfg); })
    .catch((e) => {
      document.getElementById("diagMeta").textContent = `Kunde inte ladda konfiguration: ${e?.message || e}`;
    });
}

function diagClose() {
  document.getElementById("diagOverlay").classList.remove("open");
}

(async () => {
  const user = await initPage("archiveStatus");
  if (!user?.is_super_user) {
    window.location.href = "/index.html";
    return;
  }
  document.getElementById("diagOpenBtn")?.addEventListener("click", diagOpen);
  document.getElementById("diagCloseBtn")?.addEventListener("click", diagClose);
  document.getElementById("diagOverlay")?.addEventListener("click", (e) => {
    if (/** @type {HTMLElement} */ (e.target).id === "diagOverlay") diagClose();
  });
  await refreshArchiveStatus();
  setInterval(refreshArchiveStatus, ARCHIVE_STATUS_REFRESH_MS);
})();

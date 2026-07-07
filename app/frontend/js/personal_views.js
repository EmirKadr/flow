// @ts-check
(function () {
  const state = {
    view: document.getElementById("personalApp")?.dataset.personalView || document.body?.dataset.personalView || "schedule",
    user: null,
    persons: [],
    personId: null,
    year: null,
    week: null,
    date: localDateString(new Date()),
  };
  const PERSONAL_SCHEDULE_CACHE_TTL_MS = 25 * 1000;
  const PERSONAL_PRODUCTIVITY_CACHE_TTL_MS = 25 * 1000;

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
    );
  }

  function localDateString(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function parseDate(value) {
    const [year, month, day] = String(value || "").split("-").map(Number);
    return new Date(year, (month || 1) - 1, day || 1);
  }

  function addDays(value, days) {
    const date = parseDate(value);
    date.setDate(date.getDate() + days);
    return localDateString(date);
  }

  function isoWeekParts(date = new Date()) {
    const utc = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const day = utc.getUTCDay() || 7;
    utc.setUTCDate(utc.getUTCDate() + 4 - day);
    const yearStart = new Date(Date.UTC(utc.getUTCFullYear(), 0, 1));
    const week = Math.ceil((((utc.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
    return { year: utc.getUTCFullYear(), week, weekday: day };
  }

  function dateFromIsoWeek(year, week, weekday) {
    const simple = new Date(Date.UTC(year, 0, 1 + (week - 1) * 7));
    const simpleDay = simple.getUTCDay() || 7;
    const monday = new Date(simple);
    if (simpleDay <= 4) {
      monday.setUTCDate(simple.getUTCDate() - simpleDay + 1);
    } else {
      monday.setUTCDate(simple.getUTCDate() + 8 - simpleDay);
    }
    monday.setUTCDate(monday.getUTCDate() + weekday - 1);
    return monday;
  }

  function shiftWeek(delta) {
    const monday = dateFromIsoWeek(state.year, state.week, 1);
    monday.setUTCDate(monday.getUTCDate() + delta * 7);
    const parts = isoWeekParts(new Date(monday.getUTCFullYear(), monday.getUTCMonth(), monday.getUTCDate()));
    state.year = parts.year;
    state.week = parts.week;
  }

  function hoursText(minutes) {
    const value = Number(minutes || 0) / 60;
    return `${value.toLocaleString("sv-SE", { maximumFractionDigits: 1 })} h`;
  }

  function formatNumber(value, decimals = 0) {
    if (value == null || Number.isNaN(Number(value))) return "-";
    return Number(value).toLocaleString("sv-SE", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  function formatPercent(value) {
    if (value == null || Number.isNaN(Number(value))) return "-";
    return `${(Number(value) * 100).toLocaleString("sv-SE", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    })} %`;
  }

  function productivityScoreClass(value) {
    if (value == null || Number.isNaN(Number(value))) return "";
    if (Number(value) >= 1) return " good";
    if (Number(value) >= 0.85) return " warn";
    return " low";
  }

  function weekdayShort(label) {
    return String(label || "").slice(0, 3);
  }

  function selectedPerson() {
    return state.persons.find((person) => Number(person.id) === Number(state.personId)) || state.persons[0] || null;
  }

  function personQuery() {
    return state.personId ? `&person_id=${encodeURIComponent(state.personId)}` : "";
  }

  async function loadPersons() {
    state.persons = await api.get("/api/personal/persons");
    if (!state.personId) {
      state.personId = state.user?.person_id || state.persons[0]?.id || null;
    }
  }

  function personSelectorHtml() {
    if (!state.user?.is_super_user || state.persons.length <= 1) {
      const person = selectedPerson();
      return `<div class="personal-person-chip">${escapeHtml(person?.name || "Person")}</div>`;
    }
    return `
      <label class="personal-person-select">
        <span>Person</span>
        <select id="personalPersonSelect">
          ${state.persons.map((person) => `
            <option value="${person.id}" ${Number(person.id) === Number(state.personId) ? "selected" : ""}>
              ${escapeHtml(person.name)}${person.noman ? ` (${escapeHtml(person.noman)})` : ""}
            </option>
          `).join("")}
        </select>
      </label>
    `;
  }

  function summaryCard(label, value, detail = "", valueClass = "") {
    return `
      <div class="personal-stat">
        <span>${escapeHtml(label)}</span>
        <strong class="${escapeHtml(valueClass)}">${escapeHtml(value)}</strong>
        ${detail ? `<small>${escapeHtml(detail)}</small>` : ""}
      </div>
    `;
  }

  function segmentHtml(segment) {
    const color = segment.color || "#d8e3f0";
    return `
      <div class="personal-segment personal-segment-${escapeHtml(segment.source)}" style="--segment-color: ${escapeHtml(color)}">
        <div>
          <strong>${escapeHtml(segment.label)}</strong>
          <span>${escapeHtml(segment.start)}-${escapeHtml(segment.end)}</span>
        </div>
        <small>${hoursText(segment.minutes)}</small>
      </div>
    `;
  }

  function activitiesHtml(activities) {
    if (!activities?.length) {
      return `<p class="personal-muted">Inga aktiviteter registrerade.</p>`;
    }
    return `
      <div class="personal-activity-list">
        ${activities.map((activity) => `
          <div class="personal-activity-row" style="--activity-color: ${escapeHtml(activity.color || "#d8e3f0")}">
            <span>${escapeHtml(activity.label)}</span>
            <strong>${hoursText(activity.minutes)}</strong>
          </div>
        `).join("")}
      </div>
    `;
  }

  function productivityStatusNote(stats) {
    if (!stats) return `<p class="personal-muted">Produktivitetsdata saknas.</p>`;
    if (stats.status === "unavailable") {
      return `<p class="personal-muted">Global produktivitetsdata ar inte aktiv.</p>`;
    }
    const missing = stats.missing_dates?.length || 0;
    if (missing > 0) {
      return `<p class="personal-muted">${missing} dagar saknar snapshot och fylls av historiken.</p>`;
    }
    if (stats.status === "missing") {
      return `<p class="personal-muted">Ingen produktivitetsdata finns for perioden.</p>`;
    }
    return "";
  }

  function productivityActivityTable(stats) {
    const rows = stats?.activities || [];
    if (!rows.length) {
      return productivityStatusNote(stats) || `<p class="personal-muted">Inga KPI-aktiviteter registrerade.</p>`;
    }
    return `
      ${productivityStatusNote(stats)}
      <div class="personal-productivity-table-wrap">
        <table class="personal-productivity-table">
          <thead>
            <tr>
              <th>Aktivitet</th>
              <th>Snitt</th>
              <th>Poang/tim</th>
              <th>KPI-tid</th>
              <th>Poang</th>
              <th>Diff</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row) => `
              <tr>
                <td>${escapeHtml(row.activity || "-")}</td>
                <td class="personal-productivity-score${productivityScoreClass(row.productivity_pct)}">${escapeHtml(formatPercent(row.productivity_pct))}</td>
                <td>${escapeHtml(formatNumber(row.points_per_hour, 1))}</td>
                <td>${escapeHtml(formatNumber(row.kpi_hours, 1))} h</td>
                <td>${escapeHtml(formatNumber(row.kpi_points, 1))} / ${escapeHtml(formatNumber(row.planned_kpi_points, 1))}</td>
                <td>${escapeHtml(formatNumber(row.diff_count, 0))}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function productivityPeriodDetail(stats) {
    const period = stats?.period || {};
    const daysWithData = Number(stats?.summary?.days_with_data || 0);
    const range = period.start_date && period.end_date && period.start_date !== period.end_date
      ? `${period.start_date} - ${period.end_date}`
      : period.start_date || "";
    return [range, daysWithData ? `${daysWithData} dagar med data` : ""].filter(Boolean).join(" - ");
  }

  function currentSegment(schedule) {
    const today = localDateString(new Date());
    const now = new Date();
    const minutesNow = now.getHours() * 60 + now.getMinutes();
    const day = schedule.days.find((item) => item.date === today);
    if (!day) return null;
    return day.segments.find((segment) => {
      const start = Number(segment.hour) * 60 + Number(segment.minute_start);
      const end = Number(segment.hour) * 60 + Number(segment.minute_end);
      return minutesNow >= start && minutesNow < end;
    }) || null;
  }

  function scheduleControlsHtml(schedule) {
    return `
      <div class="personal-toolbar">
        ${personSelectorHtml()}
        <div class="personal-date-controls">
          <button type="button" id="personalPrevWeek" aria-label="Föregående vecka">‹</button>
          <button type="button" id="personalToday">Idag</button>
          <button type="button" id="personalNextWeek" aria-label="Nästa vecka">›</button>
        </div>
      </div>
      <div class="personal-week-label">Vecka ${schedule.week}, ${schedule.year}</div>
    `;
  }

  function renderSchedule(schedule) {
    const app = document.getElementById("personalApp");
    const today = localDateString(new Date());
    const current = currentSegment(schedule);
    const todayDay = schedule.days.find((day) => day.date === today);
    app.innerHTML = `
      <section class="personal-header">
        <div>
          <p>Mitt schema</p>
          <h1>${escapeHtml(schedule.person.name)}</h1>
          <span>${escapeHtml(schedule.person.home_area || schedule.person.business_name || "")}</span>
        </div>
        ${scheduleControlsHtml(schedule)}
      </section>

      <section class="personal-summary">
        ${summaryCard("Idag", todayDay ? hoursText(todayDay.total_minutes) : "-", todayDay?.status || "Utanför vald vecka")}
        ${summaryCard("Just nu", current?.label || "Ingen aktuell aktivitet", current ? `${current.start}-${current.end}` : "")}
        ${summaryCard("Veckan", hoursText(schedule.summary.total_minutes), `${schedule.summary.scheduled_days} planerade dagar`)}
      </section>

      <section class="personal-week">
        ${schedule.days.map((day) => `
          <article class="personal-day-card ${day.date === today ? "is-today" : ""}">
            <header>
              <div>
                <span>${escapeHtml(weekdayShort(day.weekday_label))}</span>
                <h2>${escapeHtml(day.weekday_label)}</h2>
              </div>
              <div>
                <strong>${hoursText(day.total_minutes)}</strong>
                <small>${escapeHtml(day.status)}</small>
              </div>
            </header>
            <div class="personal-day-date">${escapeHtml(day.date)}</div>
            <div class="personal-timeline">
              ${day.segments.length ? day.segments.map(segmentHtml).join("") : `<p class="personal-muted">Ingen planerad tid.</p>`}
            </div>
            ${activitiesHtml(day.activities)}
          </article>
        `).join("")}
      </section>
    `;
    bindCommonControls(() => loadSchedule());
    document.getElementById("personalPrevWeek")?.addEventListener("click", () => {
      shiftWeek(-1);
      loadSchedule();
    });
    document.getElementById("personalNextWeek")?.addEventListener("click", () => {
      shiftWeek(1);
      loadSchedule();
    });
    document.getElementById("personalToday")?.addEventListener("click", () => {
      const parts = isoWeekParts(new Date());
      state.year = parts.year;
      state.week = parts.week;
      loadSchedule();
    });
  }

  function productivityControlsHtml() {
    return `
      <div class="personal-toolbar">
        ${personSelectorHtml()}
        <div class="personal-date-controls">
          <button type="button" id="personalPrevDate" aria-label="Föregående dag">‹</button>
          <input id="personalDateInput" type="date" value="${escapeHtml(state.date)}" aria-label="Datum" />
          <button type="button" id="personalNextDate" aria-label="Nästa dag">›</button>
          <button type="button" id="personalToday">Idag</button>
        </div>
      </div>
    `;
  }

  function renderProductivity(payload) {
    const app = document.getElementById("personalApp");
    const day = payload.day;
    const dayStats = payload.productivity?.day || null;
    const weekStats = payload.productivity?.week || null;
    const daySummary = dayStats?.summary || {};
    const weekSummary = weekStats?.summary || {};
    app.innerHTML = `
      <section class="personal-header">
        <div>
          <p>Min produktivitet</p>
          <h1>${escapeHtml(payload.person.name)}</h1>
          <span>${escapeHtml(day.weekday_label)} ${escapeHtml(payload.date)}</span>
        </div>
        ${productivityControlsHtml()}
      </section>

      <section class="personal-summary">
        ${summaryCard("Idag", formatPercent(daySummary.productivity_pct), `${formatNumber(daySummary.kpi_points, 1)} / ${formatNumber(daySummary.planned_kpi_points, 1)} KPI-poang`, productivityScoreClass(daySummary.productivity_pct))}
        ${summaryCard("Poang/tim", formatNumber(daySummary.points_per_hour, 1), `${formatNumber(daySummary.kpi_hours, 1)} KPI-timmar`)}
        ${summaryCard("Veckosnitt", formatPercent(weekSummary.productivity_pct), `${formatNumber(weekSummary.kpi_points, 1)} / ${formatNumber(weekSummary.planned_kpi_points, 1)} KPI-poang`, productivityScoreClass(weekSummary.productivity_pct))}
        ${summaryCard("Planerad tid", hoursText(day.total_minutes), day.status)}
      </section>

      <section class="personal-productivity-grid">
        <article class="personal-panel">
          <h2>Dagens produktivitet</h2>
          <p class="personal-panel-meta">${escapeHtml(productivityPeriodDetail(dayStats))}</p>
          ${productivityActivityTable(dayStats)}
        </article>
        <article class="personal-panel">
          <h2>Dagens pass</h2>
          <div class="personal-timeline">
            ${day.segments.length ? day.segments.map(segmentHtml).join("") : `<p class="personal-muted">Ingen tid registrerad.</p>`}
          </div>
        </article>
        <article class="personal-panel">
          <h2>Veckans produktivitet</h2>
          <p class="personal-panel-meta">${escapeHtml(productivityPeriodDetail(weekStats))}</p>
          ${productivityActivityTable(weekStats)}
        </article>
      </section>
    `;
    bindCommonControls(() => loadProductivity());
    document.getElementById("personalPrevDate")?.addEventListener("click", () => {
      state.date = addDays(state.date, -1);
      loadProductivity();
    });
    document.getElementById("personalNextDate")?.addEventListener("click", () => {
      state.date = addDays(state.date, 1);
      loadProductivity();
    });
    document.getElementById("personalToday")?.addEventListener("click", () => {
      state.date = localDateString(new Date());
      loadProductivity();
    });
    document.getElementById("personalDateInput")?.addEventListener("change", (event) => {
      state.date = /** @type {HTMLInputElement} */ (event.target).value || localDateString(new Date());
      loadProductivity();
    });
  }

  function bindCommonControls(onReload) {
    document.getElementById("personalPersonSelect")?.addEventListener("change", (event) => {
      state.personId = Number(/** @type {HTMLInputElement} */ (event.target).value);
      onReload();
    });
  }

  async function loadSchedule() {
    const app = document.getElementById("personalApp");
    app.classList.add("is-loading");
    try {
      const schedule = await api.get(
        `/api/personal/schedule?year=${state.year}&week=${state.week}${personQuery()}`,
        { cacheTtlMs: PERSONAL_SCHEDULE_CACHE_TTL_MS },
      );
      state.personId = schedule.person.id;
      renderSchedule(schedule);
    } catch (error) {
      renderError(error);
    } finally {
      app.classList.remove("is-loading");
    }
  }

  async function loadProductivity() {
    const app = document.getElementById("personalApp");
    app.classList.add("is-loading");
    try {
      const payload = await api.get(
        `/api/personal/productivity?date=${encodeURIComponent(state.date)}${personQuery()}`,
        { cacheTtlMs: PERSONAL_PRODUCTIVITY_CACHE_TTL_MS },
      );
      state.personId = payload.person.id;
      renderProductivity(payload);
    } catch (error) {
      renderError(error);
    } finally {
      app.classList.remove("is-loading");
    }
  }

  function renderError(error) {
    const app = document.getElementById("personalApp");
    app.innerHTML = `
      <section class="personal-error">
        <h1>Kunde inte ladda vyn</h1>
        <p>${escapeHtml(error?.message || "Försök igen om en stund.")}</p>
        <button type="button" id="personalRetry">Försök igen</button>
      </section>
    `;
    document.getElementById("personalRetry")?.addEventListener("click", () => {
      if (state.view === "productivity") loadProductivity();
      else loadSchedule();
    });
  }

  async function boot() {
    const parts = isoWeekParts(new Date());
    state.year = parts.year;
    state.week = parts.week;
    const pageId = state.view === "productivity" ? "myProductivity" : "mySchedule";
    state.user = await initPage(pageId);
    if (!state.user) return;
    await loadPersons();
    if (state.view === "productivity") await loadProductivity();
    else await loadSchedule();
  }

  document.addEventListener("DOMContentLoaded", () => {
    boot().catch(renderError);
  });
})();

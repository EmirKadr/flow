// @ts-check
const PRESENCE_API_PATH = "/api/schedule/presence";

function presenceEscapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]
  ));
}

function presenceFormatDateTime(value) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("sv-SE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function presenceTotalRows(data) {
  return (data?.groups || []).reduce((sum, group) => sum + (group.rows || []).length, 0);
}

function presenceQuery(selection, scope) {
  const params = new URLSearchParams({
    year: String(selection.year),
    week: String(selection.week),
    weekday: String(selection.weekday),
    hour: String(new Date().getHours()),
  });
  if (scope === "current" && selection.areaId != null) {
    params.set("area_id", String(selection.areaId));
  }
  if (selection.businessId != null) {
    params.set("business_id", String(selection.businessId));
  }
  return `${PRESENCE_API_PATH}?${params.toString()}`;
}

function openPresenceScopeDialog(selection) {
  return new Promise((resolve) => {
    const hasArea = selection.areaId != null;
    const areaName = selection.areaName || "nuvarande område";
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal presence-scope-modal">
        <h2>Närvarande</h2>
        <label class="modal-checkbox">
          <input type="radio" name="presence-scope" value="all" checked />
          Alla områden
        </label>
        ${hasArea ? `
          <label class="modal-checkbox">
            <input type="radio" name="presence-scope" value="current" />
            ${presenceEscapeHtml(areaName)}
          </label>
        ` : ""}
        <div class="actions">
          <button type="button" id="presence-cancel">Avbryt</button>
          <button type="button" id="presence-print" class="primary" data-enter-default>Skriv ut</button>
        </div>
      </div>`;
    document.body.appendChild(backdrop);
    const close = (value) => {
      backdrop.remove();
      resolve(value);
    };
    backdrop.querySelector("#presence-cancel")?.addEventListener("click", () => close(null));
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) close(null);
    });
    backdrop.querySelector("#presence-print")?.addEventListener("click", () => {
      const scope = /** @type {HTMLInputElement} */ (backdrop.querySelector('input[name="presence-scope"]:checked'))?.value || "all";
      close(scope);
    });
  });
}

function renderPresencePrintRoot(data, selection, scope) {
  document.getElementById("presence-print-root")?.remove();
  const root = document.createElement("div");
  root.id = "presence-print-root";
  root.className = "presence-print-root";
  const scopeLabel = scope === "current" && selection.areaName ? selection.areaName : "Alla områden";
  const generatedAt = presenceFormatDateTime(data.generated_at);
  const groups = data.groups || [];
  root.innerHTML = `
    <div class="presence-print-head">
      <h1>Närvarande</h1>
      <div>${presenceEscapeHtml(data.date)} · ${String(data.hour).padStart(2, "0")}:00 · ${presenceEscapeHtml(scopeLabel)}</div>
      <div>Skapad ${presenceEscapeHtml(generatedAt)}</div>
    </div>
    ${groups.map((group) => `
      <section class="presence-print-group">
        <h2>${presenceEscapeHtml(group.business_name || "Verksamhet")}</h2>
        <table>
          <thead>
            <tr>
              <th>Namn</th>
              <th>Hemområde</th>
              <th>Nuvarande aktivitet</th>
            </tr>
          </thead>
          <tbody>
            ${(group.rows || []).map((row) => `
              <tr>
                <td>${presenceEscapeHtml(row.name)}</td>
                <td>${presenceEscapeHtml(row.home_area || "")}</td>
                <td>${presenceEscapeHtml(row.current_activity || "Ingen")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </section>
    `).join("")}`;
  document.body.appendChild(root);
  return root;
}

function printPresenceRoot(root) {
  const cleanup = () => {
    document.body.classList.remove("presence-printing");
    root.remove();
  };
  document.body.classList.add("presence-printing");
  window.addEventListener("afterprint", cleanup, { once: true });
  setTimeout(() => {
    if (document.body.contains(root)) cleanup();
  }, 60000);
  setTimeout(() => window.print(), 0);
}

function validPresenceSelection(selection) {
  return selection
    && Number.isInteger(Number(selection.year))
    && Number.isInteger(Number(selection.week))
    && Number.isInteger(Number(selection.weekday));
}

function setupPresencePrintButton(buttonId, options) {
  const button = document.getElementById(buttonId);
  if (!button || !options || typeof options.getSelection !== "function") return;
  button.addEventListener("click", async () => {
    const selection = options.getSelection();
    if (!validPresenceSelection(selection)) {
      showToast("Välj en giltig dag innan du skriver ut närvarolistan.", "warn", 6000, { logTitle: "Närvarande" });
      return;
    }
    const scope = await openPresenceScopeDialog(selection);
    if (!scope) return;
    try {
      showToast("Hämtar närvarolista...", "info", 2500, { logTitle: "Närvarande" });
      const data = await api.get(presenceQuery(selection, scope), { skipCache: true });
      const total = presenceTotalRows(data);
      if (!total) {
        showToast("Inga närvarande hittades för den valda dagen och tiden.", "warn", 7000, { logTitle: "Närvarande" });
        return;
      }
      const root = renderPresencePrintRoot(data, selection, scope);
      showToast(`Närvarolista öppnas för utskrift (${total} personer).`, "success", 3000, { logTitle: "Närvarande" });
      printPresenceRoot(root);
    } catch (error) {
      showToast(error.message || "Kunde inte skapa närvarolistan.", "error", 7000, { logTitle: "Närvarande" });
    }
  });
}

function schedulePrintHours() {
  return typeof HOURS !== "undefined" && Array.isArray(HOURS) && HOURS.length
    ? HOURS
    : Array.from({ length: 18 }, (_, i) => 6 + i);
}

function schedulePrintDayName(weekday) {
  if (typeof DAYS !== "undefined" && DAYS[weekday]) return DAYS[weekday];
  return `Dag ${weekday}`;
}

function schedulePrintSelectedHour() {
  const hours = schedulePrintHours();
  const todayHour = typeof currentHourIfToday === "function" ? currentHourIfToday() : null;
  const candidate = todayHour == null ? new Date().getHours() : todayHour;
  if (hours.includes(candidate)) return candidate;
  return Math.max(hours[0], Math.min(hours[hours.length - 1], candidate));
}

function schedulePrintHourLabel(hour) {
  return `${String(hour).padStart(2, "0")}:00`;
}

function schedulePrintMinuteLabel(hour, minute) {
  const endHour = minute >= 60 ? hour + 1 : hour;
  const endMinute = minute >= 60 ? 0 : minute;
  return `${String(endHour).padStart(2, "0")}:${String(endMinute).padStart(2, "0")}`;
}

function schedulePrintRangeLabel(hour, minuteStart, minuteEnd) {
  if (Number(minuteStart) === 0 && Number(minuteEnd) === 60) return schedulePrintHourLabel(hour);
  return `${schedulePrintMinuteLabel(hour, minuteStart)}-${schedulePrintMinuteLabel(hour, minuteEnd)}`;
}

function schedulePrintSelectionTitle(selection) {
  const date = selection.date || (typeof selectedScheduleYmdString === "function" ? selectedScheduleYmdString() : "");
  return `${schedulePrintDayName(selection.weekday)} ${presenceEscapeHtml(date)} · V${presenceEscapeHtml(selection.week)}/${presenceEscapeHtml(selection.year)}`;
}

function schedulePrintAreaLabel(selection) {
  return selection.areaName || "Alla områden";
}

function schedulePrintActivityForRange(person, hour, range) {
  const personId = Number(person?.id);
  if (!Number.isFinite(personId)) return null;
  const segment = typeof currentSegment === "function"
    ? currentSegment(personId, hour, Number(range.minute_start), Number(range.minute_end))
    : null;
  const explicitActivityId = segment?.activity_id == null ? null : Number(segment.activity_id);
  const scheduled = typeof isScheduledHour === "function" && isScheduledHour(personId, hour);
  const scheduledActivityId = scheduled && typeof scheduledActivityIdForHour === "function"
    ? scheduledActivityIdForHour(personId, hour)
    : null;
  const activityId = explicitActivityId != null
    ? explicitActivityId
    : (!segment?.empty_override ? scheduledActivityId : null);
  if (activityId == null || typeof activityById !== "function") return null;
  const activity = activityById(Number(activityId));
  if (!activity) return null;
  return {
    id: Number(activity.id),
    code: activity.code || "",
    label: activity.label || "",
    category: activity.category || "",
    color: activity.color || "",
  };
}

function schedulePrintRangesForHour(person, hour) {
  const personId = Number(person?.id);
  const segments = typeof segmentsForHour === "function" ? segmentsForHour(personId, hour) : [];
  const hasSplit = (typeof isSplitHour === "function" && isSplitHour(segments))
    || (typeof isPartialRange === "function" && segments.some((segment) => isPartialRange(segment)));
  if (hasSplit && typeof splitRangesForSegments === "function") {
    return splitRangesForSegments(segments);
  }
  return [{ minute_start: 0, minute_end: 60 }];
}

function schedulePrintHourItems(person, hour) {
  return schedulePrintRangesForHour(person, hour).map((range) => ({
    ...range,
    activity: schedulePrintActivityForRange(person, hour, range),
  }));
}

function schedulePrintUniqueActivities(items) {
  const unique = [];
  const seen = new Set();
  (items || []).forEach((item) => {
    const activity = item.activity;
    if (!activity?.label) return;
    const key = `${activity.id}:${activity.label}`;
    if (seen.has(key)) return;
    seen.add(key);
    unique.push({ ...item, activity });
  });
  return unique;
}

function schedulePrintActivityText(activity) {
  return `${activity?.code || ""} ${activity?.label || ""}`.toLowerCase();
}

function schedulePrintIsLunchActivity(activity) {
  const text = schedulePrintActivityText(activity);
  return text.includes("lunch") || text.includes("rast");
}

function schedulePrintHourHasWork(person, hour) {
  return schedulePrintHourItems(person, hour).some((item) => item.activity && item.activity.category !== "absence");
}

function schedulePrintPersonHasDayValue(person) {
  const personId = Number(person?.id);
  if (!Number.isFinite(personId)) return false;
  return schedulePrintHours().some((hour) => (
    (typeof isScheduledHour === "function" && isScheduledHour(personId, hour))
    || (typeof segmentsForHour === "function" && segmentsForHour(personId, hour).length > 0)
  ));
}

function schedulePrintIsInferredLunch(person, hour) {
  if (schedulePrintUniqueActivities(schedulePrintHourItems(person, hour)).length) return false;
  const hours = schedulePrintHours();
  const hasWorkBefore = hours.some((candidate) => candidate < hour && schedulePrintHourHasWork(person, candidate));
  const hasWorkAfter = hours.some((candidate) => candidate > hour && schedulePrintHourHasWork(person, candidate));
  return hasWorkBefore && hasWorkAfter;
}

function schedulePrintHourText(person, hour, { inferLunch = true, includeSplitTimes = false } = {}) {
  const items = schedulePrintHourItems(person, hour);
  const activities = schedulePrintUniqueActivities(items);
  if (!activities.length) return inferLunch && schedulePrintIsInferredLunch(person, hour) ? "Lunch" : "";
  if (activities.some((item) => schedulePrintIsLunchActivity(item.activity))) return "Lunch";
  if (activities.length === 1) return activities[0].activity.label;
  if (!includeSplitTimes) return activities.map((item) => item.activity.label).join(" / ");
  return activities.map((item) => (
    `${schedulePrintRangeLabel(hour, item.minute_start, item.minute_end)} ${item.activity.label}`
  )).join(" / ");
}

function schedulePrintCellColor(person, hour) {
  const activity = schedulePrintUniqueActivities(schedulePrintHourItems(person, hour))[0]?.activity;
  const color = String(activity?.color || "").trim();
  return /^#[0-9a-f]{3,8}$/i.test(color) ? color : "";
}

function schedulePrintHomeArea(person) {
  const area = typeof areaById === "function" ? areaById(Number(person?.home_area_id)) : null;
  return area?.name || "";
}

function schedulePrintPersonsForDay() {
  const hasState = typeof state !== "undefined";
  const source = (hasState && Array.isArray(state.allPersons) && state.allPersons.length)
    ? state.allPersons
    : ((hasState && Array.isArray(state.persons)) ? state.persons : []);
  const relevant = source.filter((person) => schedulePrintPersonHasDayValue(person));
  return relevant.length ? relevant : source;
}

function schedulePrintTimeline(person) {
  const entries = schedulePrintHours().map((hour) => ({
    hour,
    label: schedulePrintHourText(person, hour, { inferLunch: true, includeSplitTimes: true }),
  })).filter((entry) => entry.label);
  const ranges = [];
  entries.forEach((entry) => {
    const previous = ranges[ranges.length - 1];
    if (previous && previous.label === entry.label && previous.end === entry.hour) {
      previous.end = entry.hour + 1;
      return;
    }
    ranges.push({ start: entry.hour, end: entry.hour + 1, label: entry.label });
  });
  return ranges.map((entry) => (
    `${schedulePrintHourLabel(entry.start)}-${schedulePrintHourLabel(entry.end)} ${entry.label}`
  )).join(", ");
}

function openSchedulePrintDialog() {
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal schedule-print-modal">
        <h2>Skriv ut</h2>
        <label class="modal-checkbox">
          <input type="radio" name="schedule-print-type" value="staffing" checked />
          Bemanning
        </label>
        <label class="modal-checkbox">
          <input type="radio" name="schedule-print-type" value="evacuation" />
          Utrymning
        </label>
        <div class="actions">
          <button type="button" id="schedule-print-cancel">Avbryt</button>
          <button type="button" id="schedule-print-submit" class="primary" data-enter-default>Skriv ut</button>
        </div>
      </div>`;
    document.body.appendChild(backdrop);
    const close = (value) => {
      backdrop.remove();
      resolve(value);
    };
    backdrop.querySelector("#schedule-print-cancel")?.addEventListener("click", () => close(null));
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) close(null);
    });
    backdrop.querySelector("#schedule-print-submit")?.addEventListener("click", () => {
      close(/** @type {HTMLInputElement} */ (backdrop.querySelector('input[name="schedule-print-type"]:checked'))?.value || "staffing");
    });
  });
}

function createSchedulePrintRoot(kind) {
  document.getElementById("schedule-print-root")?.remove();
  document.getElementById("presence-print-root")?.remove();
  const root = document.createElement("div");
  root.id = "schedule-print-root";
  root.className = `presence-print-root schedule-print-root schedule-print-${kind}`;
  document.body.appendChild(root);
  return root;
}

function renderScheduleStaffingPrintRoot(selection, persons) {
  const root = createSchedulePrintRoot("staffing");
  const hours = schedulePrintHours();
  root.innerHTML = `
    <div class="presence-print-head schedule-print-head">
      <h1>Bemanning</h1>
      <div>${schedulePrintSelectionTitle(selection)} · ${presenceEscapeHtml(schedulePrintAreaLabel(selection))}</div>
      <div>Skapad ${presenceEscapeHtml(presenceFormatDateTime(new Date()))}</div>
    </div>
    <table class="schedule-print-table schedule-print-matrix">
      <thead>
        <tr>
          <th>Person</th>
          <th>Hemområde</th>
          ${hours.map((hour) => `<th>${schedulePrintHourLabel(hour)}</th>`).join("")}
        </tr>
      </thead>
      <tbody>
        ${persons.map((person) => `
          <tr>
            <td><span class="schedule-print-cell-text">${presenceEscapeHtml(person.name)}</span></td>
            <td><span class="schedule-print-cell-text">${presenceEscapeHtml(schedulePrintHomeArea(person))}</span></td>
            ${hours.map((hour) => {
              const label = schedulePrintHourText(person, hour, { inferLunch: true, includeSplitTimes: false }) || "-";
              const color = schedulePrintCellColor(person, hour);
              const style = color ? ` style="background: ${presenceEscapeHtml(color)};"` : "";
              return `<td${style}><span class="schedule-print-cell-text">${presenceEscapeHtml(label)}</span></td>`;
            }).join("")}
          </tr>
        `).join("")}
      </tbody>
    </table>`;
  return root;
}

function schedulePrintEvacuationStatus(person, hour) {
  const items = schedulePrintHourItems(person, hour);
  const activities = schedulePrintUniqueActivities(items).map((item) => item.activity);
  const label = schedulePrintHourText(person, hour, { inferLunch: false, includeSplitTimes: false });
  const lunchActivity = activities.find((activity) => schedulePrintIsLunchActivity(activity));
  if (lunchActivity || schedulePrintIsInferredLunch(person, hour)) {
    return { status: "Lunch", activity: lunchActivity?.label || "Lunch", className: "lunch" };
  }
  const absence = activities.find((activity) => activity.category === "absence");
  if (absence) {
    const text = schedulePrintActivityText(absence);
    const isSick = text.includes("sjuk");
    return {
      status: isSick ? "Sjuk" : (absence.label || "Frånvaro"),
      activity: label || absence.label || "Frånvaro",
      className: isSick ? "sick" : "absence",
    };
  }
  const hasWork = activities.some((activity) => activity.category !== "absence");
  if (hasWork) return { status: "Här", activity: label || "Arbete", className: "present" };
  if (schedulePrintPersonHasDayValue(person)) return { status: "Ej här nu", activity: "", className: "away" };
  return { status: "Ej schemalagd", activity: "", className: "off" };
}

function schedulePrintEvacuationSummary(rows) {
  const labels = [
    ["present", "Här"],
    ["lunch", "Lunch"],
    ["sick", "Sjuk"],
    ["absence", "Frånvaro"],
    ["away", "Ej här nu"],
  ];
  return labels.map(([key, label]) => ({
    label,
    count: rows.filter((row) => row.className === key).length,
  }));
}

function renderScheduleEvacuationPrintRoot(selection, persons) {
  const root = createSchedulePrintRoot("evacuation");
  const hour = schedulePrintSelectedHour();
  const rows = persons.map((person) => ({
    person,
    timeline: schedulePrintTimeline(person),
    ...schedulePrintEvacuationStatus(person, hour),
  }));
  const summary = schedulePrintEvacuationSummary(rows);
  root.innerHTML = `
    <div class="presence-print-head schedule-print-head">
      <h1>Utrymning</h1>
      <div>${schedulePrintSelectionTitle(selection)} · Status ${schedulePrintHourLabel(hour)} · ${presenceEscapeHtml(schedulePrintAreaLabel(selection))}</div>
      <div>Skapad ${presenceEscapeHtml(presenceFormatDateTime(new Date()))}</div>
    </div>
    <div class="schedule-print-summary">
      ${summary.map((item) => `
        <div>
          <strong>${presenceEscapeHtml(item.count)}</strong>
          <span>${presenceEscapeHtml(item.label)}</span>
        </div>
      `).join("")}
    </div>
    <table class="schedule-print-table schedule-print-evacuation-table">
      <thead>
        <tr>
          <th class="schedule-print-check">✓</th>
          <th>Namn</th>
          <th>Hemområde</th>
          <th>Status</th>
          <th>Nuvarande aktivitet</th>
          <th>Dagen</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td class="schedule-print-check"></td>
            <td>${presenceEscapeHtml(row.person.name)}</td>
            <td>${presenceEscapeHtml(schedulePrintHomeArea(row.person))}</td>
            <td class="schedule-print-status ${presenceEscapeHtml(row.className)}">${presenceEscapeHtml(row.status)}</td>
            <td>${presenceEscapeHtml(row.activity || "-")}</td>
            <td>${presenceEscapeHtml(row.timeline || "-")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>`;
  return root;
}

function setupSchedulePrintButton(buttonId, options) {
  const button = document.getElementById(buttonId);
  if (!button || !options || typeof options.getSelection !== "function") return;
  button.addEventListener("click", async () => {
    const selection = options.getSelection();
    if (!validPresenceSelection(selection)) {
      showToast("Välj en giltig dag innan du skriver ut.", "warn", 6000, { logTitle: "Skriv ut" });
      return;
    }
    const type = await openSchedulePrintDialog();  // dialogen tar inga argument; urvalet lases i getSelection-callbacken
    if (!type) return;
    const persons = schedulePrintPersonsForDay();
    if (!persons.length) {
      showToast("Det finns inga personer att skriva ut för den valda dagen.", "warn", 7000, { logTitle: "Skriv ut" });
      return;
    }
    const root = type === "evacuation"
      ? renderScheduleEvacuationPrintRoot(selection, persons)
      : renderScheduleStaffingPrintRoot(selection, persons);
    showToast(
      `${type === "evacuation" ? "Utrymningslista" : "Bemanning"} öppnas för utskrift (${persons.length} personer).`,
      "success",
      3000,
      { logTitle: "Skriv ut" },
    );
    printPresenceRoot(root);
  });
}

window.setupPresencePrintButton = setupPresencePrintButton;
window.setupSchedulePrintButton = setupSchedulePrintButton;

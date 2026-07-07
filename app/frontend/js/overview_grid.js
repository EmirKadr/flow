// @ts-check
// Utdelad ur overview.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter overview.js via <script>-tagg.

// ---- VECKO-VY ----
function renderOverviewDayHeader(th, dayLabel, week) {
  th.replaceChildren();
  const dateLabel = document.createElement("span");
  dateLabel.className = "overview-day-date";
  dateLabel.textContent = dayLabel;

  const weekLabel = document.createElement("span");
  weekLabel.className = "overview-week-label";
  weekLabel.textContent = `Vecka ${week}`;

  th.append(dateLabel, weekLabel);
}

function buildWeekHeader() {
  const header = document.getElementById("headerRow");
  while (header.children.length > 1) header.removeChild(header.lastChild);
  const monday = isoWeekToMonday(overviewState.year, overviewState.week);
  const today = todayYmd();
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday);
    d.setUTCDate(monday.getUTCDate() + i);
    const th = document.createElement("th");
    renderOverviewDayHeader(th, `${DAY_SHORT[i + 1]} ${d.getUTCDate()}/${d.getUTCMonth() + 1}`, overviewState.week);
    const ymd = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
    if (ymd === today) th.classList.add("today-col");
    header.appendChild(th);
  }
}

function applySelectedPersonRow() {
  const selectedId = Number(overviewState.selectedPersonId);
  document.querySelectorAll("#overviewBody tr.person-row-selected").forEach((row) => {
    row.classList.remove("person-row-selected");
    row.removeAttribute("aria-selected");
  });
  if (!Number.isInteger(selectedId)) return;
  const row = document.querySelector(`#overviewBody tr[data-person-id="${selectedId}"]`);
  if (!row) return;
  row.classList.add("person-row-selected");
  row.setAttribute("aria-selected", "true");
}

function selectPersonRow(personId) {
  const nextId = Number(personId);
  if (!Number.isInteger(nextId)) return;
  overviewState.selectedPersonId = nextId;
  applySelectedPersonRow();
}

function buildWeekBody() {
  const body = document.getElementById("overviewBody");
  const fragment = document.createDocumentFragment();
  const lookup = new Map();
  overviewState.cells.forEach((m) => lookup.set(`${m.person_id}:${m.weekday}`, m));

  overviewState.persons.forEach((p) => {
    const tr = document.createElement("tr");
    tr.dataset.personId = p.id;
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    nameTd.textContent = p.name;
    setupPersonOrderNameCell(nameTd, p);
    tr.appendChild(nameTd);

    const today = todayYmd();
    const monday = isoWeekToMonday(overviewState.year, overviewState.week);
    for (let wd = 1; wd <= 7; wd++) {
      const cell = lookup.get(`${p.id}:${wd}`) || { activity_id: null, mixed: false, hours_total: 0, template_hours: 0 };
      const td = document.createElement("td");
      td.className = "day";
      td.dataset.personId = String(p.id);
      td.dataset.weekday = String(wd);
      td.dataset.year = String(overviewState.year);
      td.dataset.week = String(overviewState.week);
      td.tabIndex = -1;
      const dayDate = new Date(monday);
      dayDate.setUTCDate(monday.getUTCDate() + (wd - 1));
      const ymd = `${dayDate.getUTCFullYear()}-${String(dayDate.getUTCMonth() + 1).padStart(2, "0")}-${String(dayDate.getUTCDate()).padStart(2, "0")}`;
      if (ymd === today) td.classList.add("today-col");
      renderDayCell(td, cell);
      tr.appendChild(td);
    }
    fragment.appendChild(tr);
  });

  body.replaceChildren(fragment);
  applySelectedPersonRow();
}


// ---- MÅNADS-VY ----
function buildMonthHeader() {
  const header = document.getElementById("headerRow");
  while (header.children.length > 1) header.removeChild(header.lastChild);
  const today = todayYmd();
  overviewState.days.forEach((d) => {
    const date = new Date(d.date);
    const th = document.createElement("th");
    renderOverviewDayHeader(th, `${DAY_SHORT[d.weekday]} ${date.getUTCDate()}/${date.getUTCMonth() + 1}`, d.week);
    if (d.weekday >= 6) th.style.opacity = "0.7";
    if (d.date === today) th.classList.add("today-col");
    header.appendChild(th);
  });
}

function buildMonthBody() {
  const body = document.getElementById("overviewBody");
  const fragment = document.createDocumentFragment();
  const lookup = new Map();
  overviewState.cells.forEach((m) => lookup.set(`${m.person_id}:${m.date}`, m));

  overviewState.persons.forEach((p) => {
    const tr = document.createElement("tr");
    tr.dataset.personId = p.id;
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    nameTd.textContent = p.name;
    setupPersonOrderNameCell(nameTd, p);
    tr.appendChild(nameTd);

    const today = todayYmd();
    overviewState.days.forEach((dInfo) => {
      const cell = lookup.get(`${p.id}:${dInfo.date}`) || { activity_id: null, mixed: false, hours_total: 0, template_hours: 0 };
      const td = document.createElement("td");
      td.className = "day";
      td.dataset.personId = p.id;
      td.dataset.weekday = dInfo.weekday;
      td.dataset.year = dInfo.year;
      td.dataset.week = dInfo.week;
      td.dataset.date = dInfo.date;
      td.tabIndex = -1;
      if (dInfo.date === today) td.classList.add("today-col");
      renderDayCell(td, cell);
      tr.appendChild(td);
    });
    fragment.appendChild(tr);
  });

  body.replaceChildren(fragment);
  applySelectedPersonRow();
}

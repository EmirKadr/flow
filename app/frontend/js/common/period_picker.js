// @ts-check
// period_picker.js — högerklicksväljare för en specifik vecka/månad/år.
// Används av både Sankey - Inbound och Produktivitetsöversikt. Väljaren ändrar
// bara ankardatumet; respektive vy avgör vilken period datumet tillhör.
(function () {
  let openMenu = null;

  function closeMenu() {
    if (openMenu) {
      openMenu.remove();
      openMenu = null;
    }
    document.removeEventListener("pointerdown", onOutsidePointer, true);
  }

  function onOutsidePointer(event) {
    if (openMenu && !openMenu.contains(event.target)) {
      closeMenu();
    }
  }

  function pad2(value) {
    return String(value).padStart(2, "0");
  }

  function isoFromDate(date) {
    return date.toISOString().slice(0, 10);
  }

  // ISO-8601: vecka 1 är veckan som innehåller 4 januari. Returnerar måndagen.
  function mondayOfIsoWeek(year, week) {
    const jan4 = new Date(Date.UTC(year, 0, 4));
    const day = jan4.getUTCDay() || 7;
    const monday = new Date(jan4);
    monday.setUTCDate(jan4.getUTCDate() - day + 1 + (week - 1) * 7);
    return monday;
  }

  function normalizeIso(value) {
    return /^\d{4}-\d{2}-\d{2}$/.test(String(value || "")) ? value : new Date().toISOString().slice(0, 10);
  }

  function openYearMenu(anchorEl, currentYear, onPick) {
    closeMenu();
    const menu = document.createElement("div");
    menu.className = "period-picker-menu";
    const thisYear = new Date().getFullYear();
    const years = [];
    for (let year = thisYear; year >= thisYear - 7; year -= 1) years.push(year);
    menu.innerHTML = years
      .map((year) => `<button type="button" data-year="${year}"${year === currentYear ? ' class="is-current"' : ""}>${year}</button>`)
      .join("");
    document.body.appendChild(menu);
    const rect = anchorEl.getBoundingClientRect();
    const left = Math.min(Math.round(rect.left), window.innerWidth - menu.offsetWidth - 8);
    menu.style.left = `${Math.max(8, left)}px`;
    menu.style.top = `${Math.round(rect.bottom + 4)}px`;
    menu.querySelectorAll("[data-year]").forEach((button) => {
      button.addEventListener("click", () => {
        const year = Number(button.getAttribute("data-year"));
        closeMenu();
        onPick(`${year}-01-01`);
      });
    });
    openMenu = menu;
    window.setTimeout(() => document.addEventListener("pointerdown", onOutsidePointer, true), 0);
  }

  function openNativePicker(anchorEl, type, presetValue, onValue) {
    const input = document.createElement("input");
    input.type = type;
    if (presetValue) input.value = presetValue;
    const rect = anchorEl.getBoundingClientRect();
    Object.assign(input.style, {
      position: "fixed",
      left: `${Math.round(rect.left)}px`,
      top: `${Math.round(rect.bottom + 4)}px`,
      width: "1px",
      height: "1px",
      opacity: "0",
      border: "0",
      padding: "0",
      margin: "0",
      zIndex: "2000",
    });
    document.body.appendChild(input);
    let removed = false;
    const remove = () => {
      if (!removed) {
        removed = true;
        input.remove();
      }
    };
    input.addEventListener("change", () => {
      const value = input.value;
      remove();
      if (value) onValue(value);
    });
    input.addEventListener("blur", () => window.setTimeout(remove, 250));
    if (typeof input.showPicker === "function") {
      try {
        input.showPicker();
      } catch (error) {
        input.focus();
      }
    } else {
      input.focus();
      input.click();
    }
  }

  // open({ period, anchorEl, currentIso, onPick }) — onPick(anchorIso) körs vid val.
  function openPeriodPicker(options) {
    const period = options && options.period;
    const anchorEl = options && options.anchorEl;
    const onPick = options && options.onPick;
    if (!anchorEl || typeof onPick !== "function") return;
    const iso = normalizeIso(options.currentIso);
    const [year, month] = iso.split("-");
    if (period === "year") {
      openYearMenu(anchorEl, Number(year), onPick);
      return;
    }
    if (period === "month") {
      openNativePicker(anchorEl, "month", `${year}-${month}`, (value) => onPick(`${value}-01`));
      return;
    }
    if (period === "week") {
      openNativePicker(anchorEl, "week", "", (value) => {
        const match = value.match(/^(\d{4})-W(\d{2})$/);
        if (match) onPick(isoFromDate(mondayOfIsoWeek(Number(match[1]), Number(match[2]))));
      });
      return;
    }
    openNativePicker(anchorEl, "date", iso, (value) => onPick(value));
  }

  window.flowPeriodPicker = { open: openPeriodPicker, close: closeMenu };
})();

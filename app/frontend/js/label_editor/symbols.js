// @ts-check
(function () {
  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]
    ));
  }

  const SYMBOLS = {
    check: {
      label: "Check",
      svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    },
    warning: {
      label: "Varning",
      svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 22 20H2Z" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/><path d="M12 8v6M12 17h.01" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/></svg>',
    },
    arrowRight: {
      label: "Pil höger",
      svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h15M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    },
    cross: {
      label: "Kryss",
      svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round"/></svg>',
    },
    box: {
      label: "Kolli",
      svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8 12 4l8 4v9l-8 4-8-4Z" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linejoin="round"/><path d="m4 8 8 4 8-4M12 12v9" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linejoin="round"/></svg>',
    },
    temp: {
      label: "Temperatur",
      svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 14.5V5a3 3 0 1 1 6 0v9.5a5 5 0 1 1-6 0Z" fill="none" stroke="currentColor" stroke-width="2.1"/><path d="M13 7v9" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round"/></svg>',
    },
  };
  const SYMBOL_PICKER_GROUPS = [
    {
      label: "Symboler",
      items: [
        { value: "check", label: SYMBOLS.check.label, svg: SYMBOLS.check.svg },
        { value: "warning", label: SYMBOLS.warning.label, svg: SYMBOLS.warning.svg },
        { value: "arrowRight", label: SYMBOLS.arrowRight.label, svg: SYMBOLS.arrowRight.svg },
        { value: "cross", label: SYMBOLS.cross.label, svg: SYMBOLS.cross.svg },
        { value: "box", label: SYMBOLS.box.label, svg: SYMBOLS.box.svg },
        { value: "temp", label: SYMBOLS.temp.label, svg: SYMBOLS.temp.svg },
      ],
    },
    {
      label: "Lager",
      items: [
        { value: "emoji-package", label: "Paket", glyph: "📦" },
        { value: "emoji-label", label: "Etikett", glyph: "🏷️" },
        { value: "emoji-truck", label: "Lastbil", glyph: "🚚" },
        { value: "emoji-pallet", label: "Pall", glyph: "🧱" },
        { value: "emoji-pin", label: "Plats", glyph: "📍" },
        { value: "emoji-magnifier", label: "Sök", glyph: "🔍" },
        { value: "emoji-lock", label: "Låst", glyph: "🔒" },
        { value: "emoji-unlock", label: "Upplåst", glyph: "🔓" },
      ],
    },
    {
      label: "Status",
      items: [
        { value: "emoji-ok", label: "OK", glyph: "✅" },
        { value: "emoji-no", label: "Nej", glyph: "❌" },
        { value: "emoji-stop", label: "Stopp", glyph: "⛔" },
        { value: "emoji-info", label: "Info", glyph: "ℹ️" },
        { value: "emoji-star", label: "Stjärna", glyph: "⭐" },
        { value: "emoji-fire", label: "Bråttom", glyph: "🔥" },
        { value: "emoji-snow", label: "Kylt", glyph: "❄️" },
        { value: "emoji-clock", label: "Tid", glyph: "⏱️" },
        { value: "emoji-calendar", label: "Datum", glyph: "📅" },
        { value: "emoji-note", label: "Notis", glyph: "📝" },
      ],
    },
    {
      label: "Riktning",
      items: [
        { value: "emoji-up", label: "Upp", glyph: "⬆️" },
        { value: "emoji-down", label: "Ned", glyph: "⬇️" },
        { value: "emoji-left", label: "Vänster", glyph: "⬅️" },
        { value: "emoji-right", label: "Höger", glyph: "➡️" },
        { value: "emoji-turn-left", label: "Sväng vänster", glyph: "↩️" },
        { value: "emoji-turn-right", label: "Sväng höger", glyph: "↪️" },
        { value: "emoji-recycle", label: "Återbruk", glyph: "♻️" },
        { value: "emoji-target", label: "Mål", glyph: "🎯" },
      ],
    },
    {
      label: "Markörer",
      items: [
        { value: "emoji-one", label: "1", glyph: "①" },
        { value: "emoji-two", label: "2", glyph: "②" },
        { value: "emoji-three", label: "3", glyph: "③" },
        { value: "emoji-four", label: "4", glyph: "④" },
        { value: "emoji-five", label: "5", glyph: "⑤" },
        { value: "emoji-plus", label: "Plus", glyph: "➕" },
        { value: "emoji-minus", label: "Minus", glyph: "➖" },
        { value: "emoji-heart", label: "Hjärta", glyph: "❤️" },
      ],
    },
  ];
  const SYMBOL_CHOICES = SYMBOL_PICKER_GROUPS.flatMap((group) => /** @type {any[]} */ (group.items));
  const SYMBOL_CHOICE_BY_VALUE = new Map(SYMBOL_CHOICES.map((choice) => [choice.value, choice]));

  function choice(value) {
    return SYMBOL_CHOICE_BY_VALUE.get(value) || SYMBOL_CHOICE_BY_VALUE.get("check");
  }

  function markup(value, fontSize) {
    const selected = choice(value);
    if (selected.svg) return selected.svg;
    const size = Number(fontSize) || 48;
    return `<span class="label-object-symbol-glyph" style="font-size:${size}px">${escapeHtml(selected.glyph || "")}</span>`;
  }

  function selectOptionsHtml() {
    return SYMBOL_PICKER_GROUPS.map((group) => `
      <optgroup label="${escapeHtml(group.label)}">
        ${group.items.map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join("")}
      </optgroup>
    `).join("");
  }

  function choiceButtonHtml(item) {
    const preview = item.svg
      ? `<span class="label-symbol-choice-mark label-symbol-choice-svg">${item.svg}</span>`
      : `<span class="label-symbol-choice-mark label-symbol-choice-emoji">${escapeHtml(item.glyph || "")}</span>`;
    return `
      <button type="button" class="label-symbol-choice" data-symbol-value="${escapeHtml(item.value)}" aria-label="${escapeHtml(item.label)}">
        ${preview}
        <span class="label-symbol-choice-label">${escapeHtml(item.label)}</span>
      </button>
    `;
  }

  function dialogGroupsHtml() {
    return SYMBOL_PICKER_GROUPS.map((group) => `
      <section class="label-symbol-picker-group" aria-label="${escapeHtml(group.label)}">
        <h3>${escapeHtml(group.label)}</h3>
        <div class="label-symbol-picker-grid">
          ${group.items.map(choiceButtonHtml).join("")}
        </div>
      </section>
    `).join("");
  }

  window.FlowLabelSymbols = {
    groups: SYMBOL_PICKER_GROUPS,
    choices: SYMBOL_CHOICES,
    choice,
    markup,
    selectOptionsHtml,
    dialogGroupsHtml,
  };
})();

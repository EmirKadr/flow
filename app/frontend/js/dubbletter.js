// @ts-check
// Verktyget "Ta bort dubbletter": klistra in värden (en kolumn eller flera
// tabbseparerade kolumner från Excel) och få tillbaka unika rader. Helt
// klientsidigt - inga API-anrop, ingen data lämnar webbläsaren.

const dedupeState = {
  user: null,
  /** @type {string[][]} */
  rows: [],
  columnCount: 0,
  /** @type {boolean[]} */
  selectedColumns: [],
  lastOutput: "",
};

const DEDUPE_MAX_REMOVED_SHOWN = 50;

function dedupeEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

/** @returns {HTMLTextAreaElement | null} */
function dedupeInputEl() {
  return /** @type {HTMLTextAreaElement | null} */ (document.getElementById("dedupeInput"));
}

/** @returns {HTMLTextAreaElement | null} */
function dedupeOutputEl() {
  return /** @type {HTMLTextAreaElement | null} */ (document.getElementById("dedupeOutput"));
}

/**
 * @param {string} id
 * @returns {boolean}
 */
function dedupeChecked(id) {
  const el = /** @type {HTMLInputElement | null} */ (document.getElementById(id));
  return Boolean(el?.checked);
}

/**
 * Delar inklistrad text i rader och tabbseparerade celler. Windows- och
 * Mac-radbrytningar normaliseras så att klistring från Excel beter sig lika.
 * @param {string} text
 * @returns {string[][]}
 */
function dedupeParseRows(text) {
  const normalized = String(text ?? "").replace(/\r\n?/g, "\n");
  if (!normalized) return [];
  const lines = normalized.split("\n");
  // En avslutande radbrytning ska inte bli en extra tom rad.
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  return lines.map((line) => line.split("\t"));
}

/**
 * @param {string[]} row
 * @returns {boolean}
 */
function dedupeRowIsEmpty(row) {
  return row.every((cell) => String(cell ?? "").trim() === "");
}

/**
 * Nyckeln avgör om två rader räknas som dubbletter. Bara valda kolumner ingår.
 * @param {string[]} row
 * @param {{ trim: boolean, ignoreCase: boolean, columns: boolean[] }} options
 * @returns {string}
 */
function dedupeRowKey(row, options) {
  const parts = [];
  const count = Math.max(row.length, options.columns.length);
  for (let index = 0; index < count; index += 1) {
    if (options.columns.length && !options.columns[index]) continue;
    let cell = String(row[index] ?? "");
    if (options.trim) cell = cell.trim();
    if (options.ignoreCase) cell = cell.toLocaleLowerCase("sv-SE");
    parts.push(cell);
  }
  // JSON i stället för en join-separator: raden "a b" får aldrig samma nyckel
  // som cellerna "a" + "b", och en kortare rad kolliderar inte med en längre.
  return JSON.stringify(parts);
}

/**
 * Behåller första förekomsten av varje nyckel och bevarar ordningen, precis
 * som Excels "Ta bort dubbletter".
 * @param {string[][]} rows
 * @param {{ trim: boolean, ignoreCase: boolean, skipEmpty: boolean, columns: boolean[] }} options
 * @returns {{ unique: string[][], removedCount: number, skippedEmpty: number, duplicates: Array<{ label: string, count: number }> }}
 */
function dedupeRows(rows, options) {
  /** @type {Map<string, { label: string, count: number }>} */
  const seen = new Map();
  /** @type {string[][]} */
  const unique = [];
  let removedCount = 0;
  let skippedEmpty = 0;

  for (const row of rows) {
    if (options.skipEmpty && dedupeRowIsEmpty(row)) {
      skippedEmpty += 1;
      continue;
    }
    const key = dedupeRowKey(row, options);
    const hit = seen.get(key);
    if (hit) {
      hit.count += 1;
      removedCount += 1;
      continue;
    }
    seen.set(key, { label: row.join("\t"), count: 1 });
    unique.push(row);
  }

  const duplicates = [...seen.values()]
    .filter((entry) => entry.count > 1)
    .sort((a, b) => b.count - a.count);

  return { unique, removedCount, skippedEmpty, duplicates };
}

function dedupeCurrentOptions() {
  return {
    trim: dedupeChecked("dedupeTrim"),
    ignoreCase: dedupeChecked("dedupeIgnoreCase"),
    skipEmpty: dedupeChecked("dedupeSkipEmpty"),
    columns: dedupeState.selectedColumns,
  };
}

function dedupeRenderColumns() {
  const box = document.getElementById("dedupeColumnsBox");
  const list = document.getElementById("dedupeColumns");
  if (!box || !list) return;

  if (dedupeState.columnCount < 2) {
    box.hidden = true;
    list.innerHTML = "";
    return;
  }

  box.hidden = false;
  list.innerHTML = dedupeState.selectedColumns
    .map((selected, index) =>
      `<label class="dedupe-check"><input type="checkbox" data-dedupe-column="${index}"${selected ? " checked" : ""} /> Kolumn ${index + 1}</label>`
    )
    .join("");

  list.querySelectorAll("input[data-dedupe-column]").forEach((input) => {
    input.addEventListener("change", (event) => {
      const target = /** @type {HTMLInputElement} */ (event.currentTarget);
      const index = Number(target.dataset.dedupeColumn);
      if (Number.isInteger(index)) dedupeState.selectedColumns[index] = target.checked;
    });
  });
}

/**
 * Läser indata på nytt och håller kolumnkryssrutorna i synk. Tidigare val
 * behålls så länge kolumnantalet är oförändrat.
 */
function dedupeSyncInput() {
  const input = dedupeInputEl();
  dedupeState.rows = dedupeParseRows(input?.value || "");
  const columnCount = dedupeState.rows.reduce((max, row) => Math.max(max, row.length), 0);

  if (columnCount !== dedupeState.columnCount) {
    dedupeState.columnCount = columnCount;
    dedupeState.selectedColumns = Array.from({ length: columnCount }, () => true);
    dedupeRenderColumns();
  }

  const counter = document.getElementById("dedupeInputCount");
  if (counter) {
    const rowCount = dedupeState.rows.length;
    const columnText = columnCount > 1 ? `, ${columnCount} kolumner` : "";
    counter.textContent = `${rowCount} ${rowCount === 1 ? "rad" : "rader"}${columnText}`;
  }
}

/**
 * @param {Array<{ label: string, count: number }>} duplicates
 */
function dedupeRenderRemoved(duplicates) {
  const box = document.getElementById("dedupeRemovedBox");
  const list = document.getElementById("dedupeRemoved");
  if (!box || !list) return;

  if (!duplicates.length) {
    box.hidden = true;
    list.innerHTML = "";
    return;
  }

  const shown = duplicates.slice(0, DEDUPE_MAX_REMOVED_SHOWN);
  const rest = duplicates.length - shown.length;
  const rows = shown
    .map((entry) => {
      const label = entry.label.replace(/\t/g, " | ").trim();
      return `<div class="dedupe-removed-row"><span>${dedupeEscape(label || "(tom rad)")}</span><span class="dedupe-removed-count">${entry.count} ggr</span></div>`;
    })
    .join("");
  const more = rest > 0 ? `<p class="note">... och ${rest} till.</p>` : "";
  box.hidden = false;
  list.innerHTML = `${rows}${more}`;
}

function dedupeRun() {
  dedupeSyncInput();
  const panel = document.getElementById("dedupeResultPanel");
  const output = dedupeOutputEl();
  const summary = document.getElementById("dedupeSummary");

  if (!dedupeState.rows.length) {
    if (panel) panel.hidden = true;
    dedupeState.lastOutput = "";
    showToast("Klistra in värden först.", "warn");
    return;
  }

  const options = dedupeCurrentOptions();
  if (dedupeState.columnCount > 1 && !options.columns.some(Boolean)) {
    showToast("Välj minst en kolumn att jämföra.", "warn");
    return;
  }

  const result = dedupeRows(dedupeState.rows, options);
  const text = result.unique.map((row) => row.join("\t")).join("\n");
  dedupeState.lastOutput = text;
  if (output) output.value = text;
  if (panel) panel.hidden = false;

  const parts = [
    `${dedupeState.rows.length} ${dedupeState.rows.length === 1 ? "rad" : "rader"} in`,
    `${result.unique.length} unika`,
    `${result.removedCount} borttagna`,
  ];
  if (result.skippedEmpty) parts.push(`${result.skippedEmpty} tomma överhoppade`);
  if (summary) summary.textContent = parts.join(" · ");

  dedupeRenderRemoved(result.duplicates);

  const message = result.removedCount
    ? `Tog bort ${result.removedCount} ${result.removedCount === 1 ? "dubblett" : "dubbletter"} - ${result.unique.length} unika kvar.`
    : `Inga dubbletter hittades - alla ${result.unique.length} rader är unika.`;
  showToast(message, result.removedCount ? "success" : "info");
}

function dedupeClear() {
  const input = dedupeInputEl();
  const output = dedupeOutputEl();
  const panel = document.getElementById("dedupeResultPanel");
  if (input) input.value = "";
  if (output) output.value = "";
  if (panel) panel.hidden = true;
  dedupeState.lastOutput = "";
  dedupeState.columnCount = 0;
  dedupeState.selectedColumns = [];
  dedupeRenderColumns();
  dedupeSyncInput();
  input?.focus();
}

/**
 * Kopierar resultatet. Windows-appen kör QtWebEngine där navigator.clipboard
 * kan saknas eller nekas, därför finns execCommand-fallbacken.
 * @param {string} text
 * @returns {Promise<boolean>}
 */
async function dedupeCopyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (error) {
    // Faller igenom till markera-och-kopiera nedan.
  }
  const output = dedupeOutputEl();
  if (!output) return false;
  try {
    output.focus();
    output.select();
    const copied = document.execCommand("copy");
    output.setSelectionRange(0, 0);
    return copied;
  } catch (error) {
    return false;
  }
}

async function dedupeCopyResult() {
  if (!dedupeState.lastOutput) {
    showToast("Det finns inget resultat att kopiera.", "warn");
    return;
  }
  const copied = await dedupeCopyText(dedupeState.lastOutput);
  if (copied) {
    showToast("Resultatet kopierat till urklipp.", "success");
    return;
  }
  showToast("Kunde inte kopiera automatiskt - markera texten och kopiera manuellt.", "error");
}

function dedupeSetColumnsSelection(selected) {
  dedupeState.selectedColumns = dedupeState.selectedColumns.map(() => selected);
  dedupeRenderColumns();
}

async function initDedupePage() {
  // Verktyget är helt klientsidigt, så knapparna binds synkront före
  // auth-anropet i initPage - annars är sidan död tills nätverkssvaret
  // kommit, vilket både drabbar snabba användare och gör browsertesterna
  // beroende av tajming.
  document.getElementById("dedupeRun")?.addEventListener("click", dedupeRun);
  document.getElementById("dedupeClear")?.addEventListener("click", dedupeClear);
  document.getElementById("dedupeCopy")?.addEventListener("click", dedupeCopyResult);
  document.getElementById("dedupeColumnsAll")?.addEventListener("click", () => dedupeSetColumnsSelection(true));
  document.getElementById("dedupeColumnsNone")?.addEventListener("click", () => dedupeSetColumnsSelection(false));
  dedupeInputEl()?.addEventListener("input", dedupeSyncInput);
  dedupeSyncInput();

  const user = await initPage("removeDuplicates");
  if (!user) return;
  dedupeState.user = user;
}

initDedupePage();

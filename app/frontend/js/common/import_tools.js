// @ts-check
function openImportHelpModal(title = "Importera") {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${title}</h2>
      <p class="note">Importen kan göras via Excel-mallen eller direkt i vyn.</p>
      <ol class="import-help-list">
        <li>Excel: ladda ner mallen, fyll i värdena utan att ändra rubrikerna och välj filen med Importera Excel.</li>
        <li>Direkt i vyn: öppna flera nya rader, fyll tabellen och skapa.</li>
      </ol>
      <p class="note">Efter importen visas hur många rader som skapades och vilka rader som hoppades över.</p>
      <div class="actions">
        <button class="primary" id="import-help-close">Stäng</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  backdrop.querySelector("#import-help-close").addEventListener("click", () => backdrop.remove());
}

function setupImportHelpButton(buttonId, title = "Importera") {
  const button = document.getElementById(buttonId);
  if (!button) return;
  button.addEventListener("click", () => openImportHelpModal(title));
}

function modalEnterTargetButton(modal) {
  return modal.querySelector("[data-enter-default]:not(:disabled)")
    || modal.querySelector(".actions button.primary:not(:disabled)")
    || modal.querySelector("button.primary:not(:disabled)");
}

function shouldIgnoreModalEnterTarget(target) {
  if (!target) return true;
  if (target.closest("button, [role='button'], a[href]")) return true;
  if (target.closest("[contenteditable='true']")) return true;
  if (target.matches("textarea")) return true;
  if (target.matches("input[type='checkbox'], input[type='radio']")) return true;
  return false;
}

function handleModalEnterKeydown(event) {
  if (event.key !== "Enter" || event.repeat || event.isComposing) return;
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  const modal = event.target?.closest?.(".modal");
  if (!modal || shouldIgnoreModalEnterTarget(event.target)) return;
  const button = modalEnterTargetButton(modal);
  if (!button) return;
  event.preventDefault();
  button.click();
}

document.addEventListener("keydown", handleModalEnterKeydown);

function bulkImportOptionHtml(option) {
  const normalized = typeof option === "string" ? { value: option, label: option } : option;
  return `<option value="${escapeHtml(normalized.value ?? "")}">${escapeHtml(normalized.label ?? normalized.value ?? "")}</option>`;
}

function bulkImportControlHtml(column) {
  const key = escapeHtml(column.key);
  const requirement = bulkImportRequirementMeta(column);
  const label = escapeHtml(`${column.label || column.key} (${requirement.label.toLowerCase()})`);
  const requiredAttrs = requirement.required ? ' required aria-required="true"' : ' aria-required="false"';
  if (column.type === "select") {
    return `
      <select data-bulk-key="${key}" aria-label="${label}"${requiredAttrs}>
        <option value=""></option>
        ${(column.options || []).map(bulkImportOptionHtml).join("")}
      </select>
    `;
  }
  if (column.type === "number") {
    return `<input data-bulk-key="${key}" type="number" step="${escapeHtml(column.step || 1)}" aria-label="${label}"${requiredAttrs} />`;
  }
  return `<input data-bulk-key="${key}" type="text" autocomplete="off" aria-label="${label}"${requiredAttrs} />`;
}

function bulkImportRequirementMeta(column) {
  const required = column.required === true;
  return {
    label: required ? "Obligatoriskt" : "Frivilligt",
    className: required ? "is-required" : "is-optional",
    required,
  };
}

function bulkImportRequirementLabel(column) {
  return bulkImportRequirementMeta(column).label;
}

function bulkImportHeaderHtml(column) {
  const label = escapeHtml(column.label || column.key);
  const requirement = bulkImportRequirementMeta(column);
  return `
    <th>
      <span class="bulk-import-head-label">${label}</span>
      <span class="bulk-import-head-requirement ${requirement.className}">${requirement.label}</span>
    </th>
  `;
}

function collectBulkImportRows(tbody, columns) {
  const rows = [];
  tbody.querySelectorAll("tr").forEach((tr) => {
    const row = {};
    let hasValue = false;
    columns.forEach((column) => {
      const input = tr.querySelector(`[data-bulk-key="${column.key}"]`);
      const value = String(input?.value || "").trim();
      row[column.key] = value;
      if (value) hasValue = true;
    });
    if (hasValue) rows.push(row);
  });
  return rows;
}

function refreshBulkImportRowNumbers(tbody) {
  tbody.querySelectorAll("tr").forEach((tr, index) => {
    const cell = tr.querySelector(".bulk-import-row-number");
    if (cell) cell.textContent = String(index + 1);
  });
}

function openBulkImportGrid({ title, columns, submitLabel = "Skapa", initialRows = 8, onSubmit }) {
  const safeColumns = Array.isArray(columns) ? columns : [];
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal wide bulk-import-modal">
      <h2>${escapeHtml(title || "Flera nya rader")}</h2>
      <div class="modal-table-scroll bulk-import-scroll">
        <table class="bulk-import-table">
          <thead>
            <tr>
              <th class="bulk-import-row-number">#</th>
              ${safeColumns.map(bulkImportHeaderHtml).join("")}
              <th class="bulk-import-actions"></th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="actions bulk-import-footer">
        <div class="bulk-import-actions-left">
          <button type="button" id="bulk-import-add">+ Lägg till rad</button>
          <button type="button" id="bulk-import-prune">Ta bort tomma</button>
        </div>
        <button type="button" id="bulk-import-cancel">Avbryt</button>
        <button type="button" class="primary" id="bulk-import-submit">${escapeHtml(submitLabel)}</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  const tbody = backdrop.querySelector("tbody");
  const addRow = () => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="bulk-import-row-number"></td>
      ${safeColumns.map((column) => `<td>${bulkImportControlHtml(column)}</td>`).join("")}
      <td class="bulk-import-actions">
        <button type="button" class="bulk-import-remove" title="Ta bort rad" aria-label="Ta bort rad">&times;</button>
      </td>
    `;
    tbody.appendChild(tr);
    tr.querySelector(".bulk-import-remove").addEventListener("click", () => {
      if (tbody.querySelectorAll("tr").length <= 1) return;
      tr.remove();
      refreshBulkImportRowNumbers(tbody);
    });
    refreshBulkImportRowNumbers(tbody);
  };

  for (let index = 0; index < Math.max(1, Number(initialRows) || 8); index += 1) {
    addRow();
  }

  backdrop.querySelector("#bulk-import-add").addEventListener("click", addRow);
  backdrop.querySelector("#bulk-import-prune").addEventListener("click", () => {
    tbody.querySelectorAll("tr").forEach((tr) => {
      const hasValue = safeColumns.some((column) => {
        const input = /** @type {HTMLInputElement | HTMLSelectElement | null} */ (
          tr.querySelector(`[data-bulk-key="${column.key}"]`)
        );
        return String(input?.value || "").trim();
      });
      if (!hasValue && tbody.querySelectorAll("tr").length > 1) tr.remove();
    });
    refreshBulkImportRowNumbers(tbody);
  });
  backdrop.querySelector("#bulk-import-cancel").addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("#bulk-import-submit").addEventListener("click", async () => {
    const submitButton = /** @type {HTMLButtonElement} */ (backdrop.querySelector("#bulk-import-submit"));
    const rows = collectBulkImportRows(tbody, safeColumns);
    if (!rows.length) {
      showToast("Fyll minst en rad.", "warn", 3000);
      return;
    }
    submitButton.disabled = true;
    try {
      await onSubmit(rows);
      backdrop.remove();
    } catch (error) {
      showToast(error.message || "Kunde inte importera raderna.", "error", 7000);
      submitButton.disabled = false;
    }
  });
}

// ---- Generic client-side table sorting ----

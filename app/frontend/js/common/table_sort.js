const CLIENT_TABLE_SORT_EXCLUDE_SELECTOR = [
  "table.matrix",
  "table.overview",
  "table.businesses-table",
  "table.business-areas-table",
  "table.bulk-import-table",
  "table.role-access-table",
  "table.meta-admin-table",
  "table.assistant-chat-table",
  "table.calc-table",
  "[data-client-sortable='false']",
].join(",");

function clientTableText(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function clientTableHeaderText(th) {
  const clone = th.cloneNode(true);
  clone.querySelectorAll(".sort-ind").forEach((node) => node.remove());
  return clientTableText(clone.textContent);
}

function clientTableVisibleCells(row) {
  return Array.from(row.children).filter((cell) =>
    !cell.hidden && window.getComputedStyle(cell).display !== "none"
  );
}

function clientTableVisibleHeaders(headerRow) {
  return Array.from(headerRow?.children || []).filter((th) =>
    !th.hidden && window.getComputedStyle(th).display !== "none"
  );
}

function clientTableHeaderIsSortable(th) {
  if (!th || th.dataset.clientSortDisabled === "true") return false;
  if (th.colSpan && th.colSpan > 1) return false;
  if (th.closest("tr.filter-row")) return false;
  if (th.querySelector("button, input, select, textarea, a")) return false;
  return Boolean(clientTableHeaderText(th));
}

function shouldSetupClientSortableTable(table) {
  if (!table || table.dataset.clientSortableBound === "true") return false;
  if (table.matches(CLIENT_TABLE_SORT_EXCLUDE_SELECTOR)) return false;
  if (table.closest(".modal, [class*='allocation-']")) return false;
  if (table.querySelector("tr.sort-row")) return false;
  if (!table.tHead || !table.tBodies.length) return false;
  return Array.from(table.tHead.querySelectorAll("th")).some(clientTableHeaderIsSortable);
}

function clientTableSortToken(cell) {
  let raw = clientTableText(cell?.dataset?.sortValue ?? cell?.textContent ?? "");
  if (!raw && cell?.style) raw = clientTableText(cell.style.background || cell.style.backgroundColor);
  if (!raw && cell) {
    const background = window.getComputedStyle(cell).backgroundColor;
    if (background && background !== "transparent" && background !== "rgba(0, 0, 0, 0)") {
      raw = background;
    }
  }
  if (!raw || raw === "-") return { type: "empty", value: "" };

  const numeric = raw.replace(/\s/g, "").replace(",", ".");
  if (/^-?\d+(\.\d+)?%?$/.test(numeric)) {
    return { type: "number", value: Number(numeric.replace("%", "")) };
  }

  const parsedDate = Date.parse(raw.replace(",", ""));
  if (/^\d{4}-\d{2}-\d{2}/.test(raw) && !Number.isNaN(parsedDate)) {
    return { type: "number", value: parsedDate };
  }

  return { type: "text", value: raw.toLocaleLowerCase("sv-SE") };
}

function compareClientTableSortTokens(left, right) {
  if (left.type === "empty" && right.type === "empty") return 0;
  if (left.type === "empty") return 1;
  if (right.type === "empty") return -1;
  if (left.type === "number" && right.type === "number") return left.value - right.value;
  return String(left.value).localeCompare(String(right.value), "sv-SE", {
    numeric: true,
    sensitivity: "base",
  });
}

function updateClientTableSortHeaders(table, activeHeader = null, direction = "") {
  table.querySelectorAll("thead th").forEach((th) => {
    const sortable = clientTableHeaderIsSortable(th);
    th.classList.toggle("client-sortable-header", sortable);
    if (!sortable) return;

    th.tabIndex = 0;
    th.title = th.title || "Klicka f\u00f6r att sortera";
    let indicator = Array.from(th.children).find((child) => child.classList?.contains("sort-ind"));
    if (!indicator) {
      indicator = document.createElement("span");
      indicator.className = "sort-ind";
      th.appendChild(document.createTextNode(" "));
      th.appendChild(indicator);
    }
    const active = th === activeHeader;
    indicator.textContent = active ? (direction === "asc" ? "▲" : "▼") : "";
    th.setAttribute(
      "aria-sort",
      active ? (direction === "asc" ? "ascending" : "descending") : "none"
    );
  });
}

function applyClientTableSort(table, th, direction) {
  if (!clientTableHeaderIsSortable(th)) return;
  const headerRow = th.parentElement;
  const visibleHeaders = clientTableVisibleHeaders(headerRow);
  const columnIndex = visibleHeaders.indexOf(th);
  if (columnIndex < 0) return;

  const columnKey = th.dataset.clientSortKey || String(columnIndex);
  const multiplier = direction === "asc" ? 1 : -1;

  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows).map((row, index) => ({ row, index }));
  const sortableRows = [];
  const pinnedRows = [];
  rows.forEach((entry) => {
    if (entry.row.querySelector("td[colspan], th[colspan]")) {
      pinnedRows.push(entry);
      return;
    }
    const cell = clientTableVisibleCells(entry.row)[columnIndex];
    if (!cell) {
      pinnedRows.push(entry);
      return;
    }
    sortableRows.push({ ...entry, token: clientTableSortToken(cell) });
  });

  sortableRows.sort((left, right) => {
    const result = compareClientTableSortTokens(left.token, right.token);
    if (result !== 0) return result * multiplier;
    return left.index - right.index;
  });

  table.dataset.clientSortKey = columnKey;
  table.dataset.clientSortDirection = direction;
  table.dataset.clientSortApplying = "true";
  [...sortableRows, ...pinnedRows].forEach((entry) => tbody.appendChild(entry.row));
  window.setTimeout(() => { delete table.dataset.clientSortApplying; }, 0);
  updateClientTableSortHeaders(table, th, direction);
}

function sortClientTableByHeader(table, th) {
  if (!clientTableHeaderIsSortable(th)) return;
  const visibleHeaders = clientTableVisibleHeaders(th.parentElement);
  const columnIndex = visibleHeaders.indexOf(th);
  if (columnIndex < 0) return;
  const columnKey = th.dataset.clientSortKey || String(columnIndex);
  const previousKey = table.dataset.clientSortKey || "";
  const previousDirection = table.dataset.clientSortDirection || "asc";
  const direction = previousKey === columnKey && previousDirection === "asc" ? "desc" : "asc";
  applyClientTableSort(table, th, direction);
}

function activeClientTableSortHeader(table) {
  const key = table.dataset.clientSortKey || "";
  if (!key) return null;
  return Array.from(table.tHead?.querySelectorAll("th") || []).find((th) => {
    if (!clientTableHeaderIsSortable(th)) return false;
    const visibleHeaders = clientTableVisibleHeaders(th.parentElement);
    const columnIndex = visibleHeaders.indexOf(th);
    return columnIndex >= 0 && (th.dataset.clientSortKey || String(columnIndex)) === key;
  }) || null;
}

function scheduleClientTableResort(table) {
  if (!table?.dataset.clientSortKey || table.dataset.clientSortApplying === "true") return;
  if (table.dataset.clientSortPending === "true") return;
  table.dataset.clientSortPending = "true";
  window.requestAnimationFrame(() => {
    delete table.dataset.clientSortPending;
    const th = activeClientTableSortHeader(table);
    if (!th) return;
    applyClientTableSort(table, th, table.dataset.clientSortDirection || "asc");
  });
}

function setupClientSortableTable(table) {
  if (!shouldSetupClientSortableTable(table)) return;
  table.dataset.clientSortableBound = "true";
  table.classList.add("client-sortable-table");
  updateClientTableSortHeaders(table);

  table.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : event.target?.parentElement;
    const th = target?.closest("th");
    if (!th || !table.tHead?.contains(th)) return;
    sortClientTableByHeader(table, th);
  });
  table.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const target = event.target instanceof Element ? event.target : event.target?.parentElement;
    const th = target?.closest("th");
    if (!th || !table.tHead?.contains(th)) return;
    event.preventDefault();
    sortClientTableByHeader(table, th);
  });
}

function setupClientSortableTables(root = document) {
  const tables = [];
  if (root instanceof HTMLTableElement) tables.push(root);
  if (root.querySelectorAll) tables.push(...root.querySelectorAll("table"));
  tables.forEach(setupClientSortableTable);
}

function initClientSortableTables() {
  setupClientSortableTables(document);
  if (!window.MutationObserver || !document.body) return;
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        setupClientSortableTables(node);
        scheduleClientTableResort(node.closest?.("table.client-sortable-table"));
      });
    });
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initClientSortableTables);
} else {
  initClientSortableTables();
}

// ---- Date-selection persistence (sessionStorage) ----
// Tabs hold their own selection across page navigation; login clears it so
// the next session starts on today's date.

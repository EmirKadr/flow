// Utdelad ur allocation/results.js for radtaket i arkitektur-kontraktet.
// Globala symboler, laddas efter results.js via <script>-tagg.

function renderAllocationCarrierClusterEditor(host, clusters, options = {}) {
  const rows = clusters?.rows || [];
  const editableCarrier = Boolean(options.editableCarrier);
  const allowDelete = Boolean(options.allowDelete);
  const colorMap = allocationClusterColorMap(
    rows.map((row) => ({ carrier: row.alias || row.description || row.carrierNum, cluster: row.clusterGroup })),
    new Map(rows.map((row) => [String(row.alias || row.description || row.carrierNum || ""), row.color]).filter(([, color]) => color)),
  );
  host.innerHTML = `
    <div class="modal-table-scroll allocation-carrier-cluster-scroll">
      <table class="allocation-carrier-cluster-table allocation-cluster-advanced-table">
        <thead>
          <tr>
            <th style="width:28px"></th>
            <th style="width:32px"></th>
            <th>Transportör</th>
            <th style="width:74px">ASN</th>
            <th style="width:74px">Arrive</th>
            <th style="width:74px">Depart</th>
            <th style="width:150px">Group</th>
            <th style="width:80px">Start seq</th>
            <th style="width:80px">End seq</th>
            ${allowDelete ? `<th style="width:42px"></th>` : ""}
            <th style="width:54px">Color</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row, index) => {
            const carrier = row.alias || row.description || row.carrierNum || `Rad ${index + 1}`;
            const swatch = row.color || colorMap.get(String(row.alias || row.description || row.carrierNum || "")) || "#d1d5db";
            return `
              <tr data-carrier-cluster-row="${index}" draggable="true">
                <td class="adv-handle" aria-hidden="true">⠿</td>
                <td class="adv-index">${index + 1}</td>
                ${editableCarrier
                  ? `<th class="adv-agency"><input type="text" data-carrier-cluster-field="carrierNum" value="${allocationEscape(row.carrierNum || row.alias || row.description || "")}" placeholder="Transport&ouml;r" /></th>`
                  : `<th class="adv-agency">${allocationEscape(carrier)}</th>`}
                <td><input type="text" data-carrier-cluster-field="asn" value="${allocationEscape(row.asn || "")}" /></td>
                <td><input type="text" data-carrier-cluster-field="arrive" value="${allocationEscape(row.arrive || "")}" /></td>
                <td><input type="text" data-carrier-cluster-field="depart" value="${allocationEscape(row.depart || "")}" /></td>
                <td><input type="text" data-carrier-cluster-field="clusterGroup" value="${allocationEscape(row.clusterGroup || "")}" /></td>
                <td><input type="number" min="1" max="652" step="1" data-carrier-cluster-field="startSeq" value="${allocationEscape(row.startSeq || "")}" /></td>
                <td><input type="number" min="1" max="652" step="1" data-carrier-cluster-field="endSeq" value="${allocationEscape(row.endSeq || "")}" /></td>
                ${allowDelete ? `<td><button type="button" class="danger" data-carrier-cluster-delete="${index}" aria-label="Ta bort transport&ouml;r">x</button></td>` : ""}
                <td><input type="color" class="adv-color" data-carrier-cluster-field="color" value="${allocationEscape(swatch)}" aria-label="Färg ${allocationEscape(carrier)}" /></td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
  if (allowDelete) {
    host.querySelectorAll("[data-carrier-cluster-delete]").forEach((button) => {
      button.addEventListener("click", () => {
        button.closest("[data-carrier-cluster-row]")?.remove();
        [...host.querySelectorAll("[data-carrier-cluster-row]")].forEach((tr, index) => {
          const indexCell = tr.querySelector(".adv-index");
          if (indexCell) indexCell.textContent = index + 1;
        });
      });
    });
  }
  initAllocationCarrierClusterDrag(host.querySelector("tbody"));
}

function initAllocationCarrierClusterDrag(tbody) {
  if (!tbody) return;
  let dragSrc = null;
  tbody.addEventListener("dragstart", (event) => {
    dragSrc = event.target.closest("tr");
    if (!dragSrc) return;
    dragSrc.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
  });
  tbody.addEventListener("dragover", (event) => {
    event.preventDefault();
    const target = event.target.closest("tr");
    if (!target || target === dragSrc || !dragSrc) return;
    const rect = target.getBoundingClientRect();
    const after = event.clientY > rect.top + rect.height / 2;
    tbody.insertBefore(dragSrc, after ? target.nextSibling : target);
  });
  tbody.addEventListener("dragend", () => {
    if (!dragSrc) return;
    dragSrc.classList.remove("dragging");
    dragSrc = null;
    [...tbody.querySelectorAll("tr")].forEach((tr, index) => {
      const indexCell = tr.querySelector(".adv-index");
      if (indexCell) indexCell.textContent = index + 1;
    });
  });
}

function collectAllocationCarrierClusterDraft(host, clusters) {
  const sourceRows = clusters?.rows || [];
  const rows = [];
  host.querySelectorAll("[data-carrier-cluster-row]").forEach((tr, position) => {
    const index = Number.parseInt(tr.dataset.carrierClusterRow || "0", 10);
    const source = Number.isFinite(index) ? sourceRows[index] || {} : {};
    const row = { ...source };
    tr.querySelectorAll("[data-carrier-cluster-field]").forEach((input) => {
      const key = input.dataset.carrierClusterField;
      if (!key) return;
      if (key === "startSeq" || key === "endSeq") {
        row[key] = allocationCarrierClusterNumber(input.value);
      } else {
        row[key] = allocationCarrierClusterText(input.value);
      }
    });
    // Radordningen efter drag bestämmer ordningen.
    row.assignmentOrder = String(position + 1);
    rows.push(row);
  });
  return normalizeAllocationCarrierClusters({ ...clusters, rows });
}

function openAllocationCarrierClusterModal() {
  const clusters = allocationCarrierClustersForResult();
  if (!clusters?.rows?.length) {
    showToast("Forecast-resultatet saknar transportörskluster.", "warn", 3500);
    return;
  }
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal wide allocation-carrier-cluster-modal">
      <h2>Transportörskluster</h2>
      <div id="allocation-carrier-cluster-editor"></div>
      <div class="actions">
        <button type="button" id="allocation-carrier-cluster-cancel">Avbryt</button>
        <button type="button" class="primary" id="allocation-carrier-cluster-save">Spara</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);
  const editor = backdrop.querySelector("#allocation-carrier-cluster-editor");
  renderAllocationCarrierClusterEditor(editor, clusters);
  backdrop.querySelector("#allocation-carrier-cluster-cancel")?.addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("#allocation-carrier-cluster-save")?.addEventListener("click", () => {
    const updated = collectAllocationCarrierClusterDraft(editor, clusters);
    allocationState.carrierClusters = updated;
    if (allocationState.result?.data?.flow_id === "forecast") {
      allocationState.result.data.carrier_clusters = updated;
    }
    persistAllocationWorkState();
    backdrop.remove();
    renderAllocationPage();
    showToast("Transportörskluster sparade för Ytgenerering.", "success", 2500);
  });
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) backdrop.remove();
  });
}

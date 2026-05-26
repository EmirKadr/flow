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
      const scope = backdrop.querySelector('input[name="presence-scope"]:checked')?.value || "all";
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

window.setupPresencePrintButton = setupPresencePrintButton;

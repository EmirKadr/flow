const publicDpakState = {
  messages: [],
  busy: false,
  status: null,
};

const publicDpakParams = new URLSearchParams(window.location.search);
const publicDpakToken = publicDpakParams.get("token") || "";
const publicDpakBusiness = publicDpakParams.get("business") || "";
const publicDpakStorageKey = `flow-public-dpak-chat:${publicDpakBusiness || "default"}:${publicDpakToken ? publicDpakToken.slice(0, 16) : "open"}`;

function publicDpakEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function publicDpakValue(value) {
  if (Array.isArray(value)) return value.map(publicDpakValue).join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

function publicDpakLoadMessages() {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(publicDpakStorageKey) || "[]");
    publicDpakState.messages = Array.isArray(parsed) ? parsed : [];
  } catch (_error) {
    publicDpakState.messages = [];
  }
}

function publicDpakSaveMessages() {
  try {
    sessionStorage.setItem(publicDpakStorageKey, JSON.stringify(publicDpakState.messages));
  } catch (_error) {
    // Private browsing can block storage; the chat still works for the current page load.
  }
}

async function publicDpakFetch(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  let body = null;
  try {
    body = await response.json();
  } catch (_error) {
    body = null;
  }
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : "Kunde inte hämta svar.";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
}

function publicDpakConversationPayload() {
  return publicDpakState.messages
    .filter((message) => message.role === "user" || message.role === "assistant")
    .map((message) => ({ role: message.role, content: message.content }));
}

function publicDpakStatusUrl() {
  const params = new URLSearchParams();
  if (publicDpakToken) params.set("token", publicDpakToken);
  if (publicDpakBusiness) params.set("business_code", publicDpakBusiness);
  const suffix = params.toString();
  return `/api/public/dpak-chat/status${suffix ? `?${suffix}` : ""}`;
}

function publicDpakStatusText(status) {
  if (!status) return "Underlag saknas.";
  const chunks = status.chunks || {};
  const chunkText = Object.keys(chunks).length
    ? ` Chunks: ${Object.entries(chunks).map(([key, value]) => `${key} ${value}`).join(", ")}.`
    : "";
  if (status.ready) {
    const coverage = status.target_start && status.target_end
      ? `${status.target_start} till ${status.target_end}`
      : status.coverage_start && status.coverage_end
        ? `${status.coverage_start} till ${status.coverage_end}`
        : "okänt datumintervall";
    return `Underlag klart: ${coverage}. ${Number(status.pick_rows || 0).toLocaleString("sv-SE")} plockrader.`;
  }
  if (status.status === "syncing") return `Underlag synkas.${chunkText}`;
  if (status.status === "error") return `Underlag har synkfel.${chunkText}`;
  return `Underlag är inte klart.${chunkText}`;
}

function publicDpakRenderTable(rows) {
  if (!Array.isArray(rows) || !rows.length) return "";
  const columns = Array.from(
    rows.reduce((set, row) => {
      Object.keys(row || {}).forEach((key) => set.add(key));
      return set;
    }, new Set())
  );
  if (!columns.length) return "";
  const header = columns.map((column) => `<th>${publicDpakEscape(column)}</th>`).join("");
  const body = rows.map((row) => `
    <tr>
      ${columns.map((column) => `<td>${publicDpakEscape(publicDpakValue(row?.[column]))}</td>`).join("")}
    </tr>
  `).join("");
  return `
    <div class="public-dpak-table-wrap">
      <table>
        <thead><tr>${header}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

function publicDpakRenderMessages() {
  const list = document.getElementById("publicDpakMessages");
  if (!list) return;
  if (!publicDpakState.messages.length) {
    list.innerHTML = `
      <div class="public-dpak-empty">
        <strong>Fråga på svenska.</strong>
        <span>Exempel: hur många D-pak sålde vi i juni?</span>
      </div>
    `;
    return;
  }
  list.innerHTML = publicDpakState.messages.map((message) => {
    if (message.role === "loading") {
      return `<div class="public-dpak-message assistant loading"><span></span> Räknar...</div>`;
    }
    return `
      <article class="public-dpak-message ${message.role}">
        <p>${publicDpakEscape(message.content).replace(/\n/g, "<br>")}</p>
        ${publicDpakRenderTable(message.table)}
      </article>
    `;
  }).join("");
  list.scrollTop = list.scrollHeight;
}

function publicDpakSetBusy(active) {
  publicDpakState.busy = Boolean(active);
  const send = document.getElementById("publicDpakSend");
  const input = document.getElementById("publicDpakInput");
  if (send) send.disabled = publicDpakState.busy;
  if (input) input.disabled = publicDpakState.busy;
}

async function publicDpakLoadStatus() {
  const statusEl = document.getElementById("publicDpakStatus");
  try {
    const status = await publicDpakFetch(publicDpakStatusUrl(), { method: "GET" });
    publicDpakState.status = status;
    if (statusEl) {
      statusEl.textContent = publicDpakStatusText(status);
      statusEl.classList.toggle("is-ready", Boolean(status.ready));
      statusEl.classList.toggle("is-error", status.status === "error" || status.status === "missing");
    }
  } catch (error) {
    if (statusEl) {
      statusEl.textContent = error.message || "Kunde inte kontrollera underlaget.";
      statusEl.classList.add("is-error");
    }
  }
}

async function publicDpakSubmit(event) {
  event.preventDefault();
  if (publicDpakState.busy) return;
  const input = document.getElementById("publicDpakInput");
  const question = input?.value.trim() || "";
  if (!question) return;
  publicDpakState.messages.push({ role: "user", content: question });
  publicDpakState.messages.push({ role: "loading", content: "" });
  if (input) input.value = "";
  publicDpakSetBusy(true);
  publicDpakRenderMessages();

  try {
    const result = await publicDpakFetch("/api/public/dpak-chat/message", {
      method: "POST",
      body: JSON.stringify({
        token: publicDpakToken || null,
        business_code: publicDpakBusiness || null,
        messages: publicDpakConversationPayload(),
      }),
    });
    publicDpakState.messages = publicDpakState.messages.filter((message) => message.role !== "loading");
    publicDpakState.messages.push({
      role: "assistant",
      content: result.answer || "Jag hittade inget svar.",
      table: result.table || [],
    });
    if (result.status) {
      publicDpakState.status = result.status;
      const statusEl = document.getElementById("publicDpakStatus");
      if (statusEl) {
        statusEl.textContent = publicDpakStatusText(result.status);
        statusEl.classList.toggle("is-ready", Boolean(result.status.ready));
        statusEl.classList.toggle("is-error", result.status.status === "error" || result.status.status === "missing");
      }
    }
    publicDpakSaveMessages();
  } catch (error) {
    publicDpakState.messages = publicDpakState.messages.filter((message) => message.role !== "loading");
    publicDpakState.messages.push({
      role: "assistant",
      content: error.message || "Kunde inte hämta svar.",
      table: [],
    });
  } finally {
    publicDpakSetBusy(false);
    publicDpakRenderMessages();
    document.getElementById("publicDpakInput")?.focus();
  }
}

function publicDpakClear() {
  publicDpakState.messages = [];
  publicDpakSaveMessages();
  publicDpakRenderMessages();
  document.getElementById("publicDpakInput")?.focus();
}

function publicDpakInit() {
  publicDpakLoadMessages();
  publicDpakRenderMessages();
  publicDpakLoadStatus();
  document.getElementById("publicDpakForm")?.addEventListener("submit", publicDpakSubmit);
  document.getElementById("publicDpakClear")?.addEventListener("click", publicDpakClear);
}

publicDpakInit();

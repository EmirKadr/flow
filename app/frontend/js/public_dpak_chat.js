const publicDpakState = {
  messages: [],
  busy: false,
  status: null,
  voice: {
    recording: false,
    supported: Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder),
    recognitionSupported: Boolean(window.SpeechRecognition || window.webkitSpeechRecognition),
    recorder: null,
    recognition: null,
    stream: null,
    chunks: [],
    startedAt: 0,
    transcript: "",
    pending: null,
  },
};
const publicDpakTables = new Map();
const publicDpakMaxVoiceBytes = 3 * 1024 * 1024;

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

function publicDpakSetVoiceStatus(text, tone = "") {
  const statusEl = document.getElementById("publicDpakVoiceStatus");
  if (!statusEl) return;
  statusEl.textContent = text || "";
  statusEl.classList.toggle("is-error", tone === "error");
  statusEl.classList.toggle("is-ready", tone === "ready");
}

function publicDpakPreferredAudioMime() {
  if (!window.MediaRecorder?.isTypeSupported) return "";
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

function publicDpakVoiceSeconds(durationMs) {
  return Math.max(1, Math.round(Number(durationMs || 0) / 1000));
}

function publicDpakSetVoiceButtonLabel(button, label) {
  button.setAttribute("aria-label", label);
  button.setAttribute("title", label);
  const labelEl = button.querySelector(".public-dpak-voice-label");
  if (labelEl) {
    labelEl.textContent = label;
  } else {
    button.textContent = label;
  }
}

function publicDpakSetVoiceControls() {
  const button = document.getElementById("publicDpakVoice");
  if (!button) return;
  const voice = publicDpakState.voice;
  button.disabled = publicDpakState.busy || !voice.supported;
  button.classList.toggle("is-recording", voice.recording);
  button.classList.toggle("has-pending", Boolean(voice.pending) && !voice.recording);
  button.setAttribute("aria-pressed", voice.recording ? "true" : "false");
  if (!voice.supported) {
    publicDpakSetVoiceButtonLabel(button, "Mikrofon saknas");
  } else if (voice.recording) {
    publicDpakSetVoiceButtonLabel(button, "Stoppa röstinspelning");
  } else if (voice.pending) {
    publicDpakSetVoiceButtonLabel(button, "Spela in ny röst");
  } else {
    publicDpakSetVoiceButtonLabel(button, "Spela in röst");
  }
}

function publicDpakClearPendingVoice() {
  publicDpakState.voice.pending = null;
  publicDpakState.voice.transcript = "";
  publicDpakSetVoiceStatus("");
  publicDpakSetVoiceControls();
}

function publicDpakResetVoice() {
  const voice = publicDpakState.voice;
  if (voice.recorder && voice.recording) {
    try {
      voice.recorder.onstop = null;
      voice.recorder.stop();
    } catch (_error) {
      // The recorder can already be stopped when the page loses focus.
    }
  }
  publicDpakStopVoiceRecognition();
  publicDpakStopVoiceStream();
  voice.recorder = null;
  voice.chunks = [];
  voice.startedAt = 0;
  voice.recording = false;
  publicDpakClearPendingVoice();
}

function publicDpakStopVoiceStream() {
  const voice = publicDpakState.voice;
  if (voice.stream) {
    voice.stream.getTracks().forEach((track) => track.stop());
  }
  voice.stream = null;
}

function publicDpakStopVoiceRecognition() {
  const recognition = publicDpakState.voice.recognition;
  publicDpakState.voice.recognition = null;
  if (!recognition) return;
  try {
    recognition.onend = null;
    recognition.stop();
  } catch (_error) {
    // Some browsers throw if recognition has already ended.
  }
}

function publicDpakBlobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || "");
      resolve(value.includes(",") ? value.split(",").pop() : value);
    };
    reader.onerror = () => reject(reader.error || new Error("Kunde inte läsa röstinspelningen."));
    reader.readAsDataURL(blob);
  });
}

function publicDpakStartVoiceRecognition() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) return null;

  const recognition = new Recognition();
  recognition.lang = "sv-SE";
  recognition.continuous = true;
  recognition.interimResults = true;

  let finalTranscript = "";
  recognition.onresult = (event) => {
    let interimTranscript = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const text = event.results[index]?.[0]?.transcript || "";
      if (event.results[index]?.isFinal) {
        finalTranscript = `${finalTranscript} ${text}`.trim();
      } else {
        interimTranscript = `${interimTranscript} ${text}`.trim();
      }
    }
    publicDpakState.voice.transcript = `${finalTranscript} ${interimTranscript}`.trim();
    if (publicDpakState.voice.transcript) {
      publicDpakSetVoiceStatus(`Lyssnar: ${publicDpakState.voice.transcript}`);
    }
  };
  recognition.onerror = () => {
    publicDpakSetVoiceStatus("Spelar in ljud. Skriv frågan om texttolkningen inte fylls i.", "error");
  };
  recognition.onend = () => {
    publicDpakState.voice.recognition = null;
  };

  try {
    recognition.start();
    publicDpakState.voice.recognition = recognition;
  } catch (_error) {
    return null;
  }
  return recognition;
}

async function publicDpakFinalizeVoice(blob, durationMs) {
  publicDpakStopVoiceStream();
  publicDpakStopVoiceRecognition();
  publicDpakState.voice.recorder = null;
  publicDpakState.voice.recording = false;
  publicDpakSetVoiceControls();

  if (!blob.size) {
    publicDpakState.voice.pending = null;
    publicDpakSetVoiceStatus("Ingen röst fångades.", "error");
    return;
  }
  if (blob.size > publicDpakMaxVoiceBytes) {
    publicDpakState.voice.pending = null;
    publicDpakSetVoiceStatus("Röstinspelningen är för stor. Försök med en kortare fråga.", "error");
    return;
  }

  try {
    const dataBase64 = await publicDpakBlobToBase64(blob);
    const transcript = (publicDpakState.voice.transcript || "").trim();
    publicDpakState.voice.pending = {
      mime_type: blob.type || "audio/webm",
      data_base64: dataBase64,
      duration_ms: Math.max(0, Math.round(durationMs || 0)),
      transcript: transcript || null,
      byte_size: blob.size,
    };
    const input = document.getElementById("publicDpakInput");
    if (transcript && input && !input.value.trim()) input.value = transcript;
    const seconds = publicDpakVoiceSeconds(durationMs);
    publicDpakSetVoiceStatus(
      transcript
        ? `Röst klar (${seconds} s). Texten kan redigeras innan du skickar.`
        : `Röst klar (${seconds} s). Skriv frågan i fältet innan du skickar.`,
      "ready"
    );
  } catch (error) {
    publicDpakState.voice.pending = null;
    publicDpakSetVoiceStatus(error.message || "Kunde inte läsa röstinspelningen.", "error");
  } finally {
    publicDpakSetVoiceControls();
  }
}

async function publicDpakStartVoice() {
  const voice = publicDpakState.voice;
  if (publicDpakState.busy || voice.recording) return;
  if (!voice.supported) {
    publicDpakSetVoiceStatus("Webbläsaren stödjer inte röstinspelning här.", "error");
    return;
  }

  publicDpakClearPendingVoice();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = publicDpakPreferredAudioMime();
    const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    voice.stream = stream;
    voice.recorder = recorder;
    voice.chunks = [];
    voice.startedAt = Date.now();
    voice.transcript = "";
    voice.recording = true;
    recorder.ondataavailable = (event) => {
      if (event.data?.size) voice.chunks.push(event.data);
    };
    recorder.onerror = () => {
      publicDpakSetVoiceStatus("Röstinspelningen avbröts.", "error");
      publicDpakStopVoice();
    };
    recorder.onstop = () => {
      const durationMs = Date.now() - voice.startedAt;
      const type = recorder.mimeType || mimeType || "audio/webm";
      const blob = new Blob(voice.chunks, { type });
      void publicDpakFinalizeVoice(blob, durationMs);
    };
    recorder.start();
    publicDpakStartVoiceRecognition();
    publicDpakSetVoiceStatus(
      voice.recognitionSupported
        ? "Spelar in och tolkar svenska..."
        : "Spelar in ljud. Skriv frågan i fältet innan du skickar.",
      voice.recognitionSupported ? "" : "error"
    );
  } catch (_error) {
    publicDpakStopVoiceStream();
    voice.recorder = null;
    voice.recording = false;
    publicDpakSetVoiceStatus("Mikrofonen kunde inte startas.", "error");
  } finally {
    publicDpakSetVoiceControls();
  }
}

function publicDpakStopVoice() {
  const voice = publicDpakState.voice;
  if (!voice.recording || !voice.recorder) return;
  voice.recording = false;
  publicDpakSetVoiceStatus("Bearbetar röstinspelningen...");
  publicDpakSetVoiceControls();
  publicDpakStopVoiceRecognition();
  try {
    voice.recorder.stop();
  } catch (_error) {
    publicDpakStopVoiceStream();
    voice.recorder = null;
    publicDpakSetVoiceStatus("Röstinspelningen kunde inte stoppas.", "error");
    publicDpakSetVoiceControls();
  }
}

function publicDpakToggleVoice() {
  if (publicDpakState.voice.recording) {
    publicDpakStopVoice();
  } else {
    void publicDpakStartVoice();
  }
}

function publicDpakVoicePayload() {
  const pending = publicDpakState.voice.pending;
  if (!pending) return null;
  return {
    mime_type: pending.mime_type,
    data_base64: pending.data_base64,
    duration_ms: pending.duration_ms,
    transcript: pending.transcript,
  };
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

function publicDpakTableSpec(rows) {
  if (!Array.isArray(rows) || !rows.length) return "";
  const columns = Array.from(
    rows.reduce((set, row) => {
      Object.keys(row || {}).forEach((key) => set.add(key));
      return set;
    }, new Set())
  );
  if (!columns.length) return null;
  return { rows, columns };
}

function publicDpakTableHtml(rows) {
  const spec = publicDpakTableSpec(rows);
  if (!spec) return "";
  const { columns } = spec;
  const header = columns.map((column) => `<th>${publicDpakEscape(column)}</th>`).join("");
  const body = rows.map((row) => `
    <tr>
      ${columns.map((column) => `<td>${publicDpakEscape(publicDpakValue(row?.[column]))}</td>`).join("")}
    </tr>
  `).join("");
  return `
    <table>
      <thead><tr>${header}</tr></thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function publicDpakRenderTable(rows, tableKey) {
  const spec = publicDpakTableSpec(rows);
  if (!spec) return "";
  publicDpakTables.set(String(tableKey), rows);
  const rowCount = rows.length.toLocaleString("sv-SE");
  return `
    <div class="public-dpak-table-shell">
      <div class="public-dpak-table-toolbar">
        <span>${rowCount} rader</span>
        <button type="button" class="public-dpak-table-expand" data-public-dpak-open-table="${publicDpakEscape(tableKey)}">Öppna helskärm</button>
      </div>
      <div class="public-dpak-table-wrap">
        ${publicDpakTableHtml(rows)}
      </div>
    </div>
  `;
}

function publicDpakOpenTable(tableKey) {
  const rows = publicDpakTables.get(String(tableKey));
  const modal = document.getElementById("publicDpakTableModal");
  const body = document.getElementById("publicDpakTableModalBody");
  if (!rows || !modal || !body) return;
  body.innerHTML = `<div class="public-dpak-table-wrap">${publicDpakTableHtml(rows)}</div>`;
  modal.hidden = false;
  document.body.classList.add("public-dpak-modal-open");
  document.getElementById("publicDpakCloseTable")?.focus();
}

function publicDpakCloseTable() {
  const modal = document.getElementById("publicDpakTableModal");
  const body = document.getElementById("publicDpakTableModalBody");
  if (modal) modal.hidden = true;
  if (body) body.innerHTML = "";
  document.body.classList.remove("public-dpak-modal-open");
}

function publicDpakRenderMessages() {
  const list = document.getElementById("publicDpakMessages");
  if (!list) return;
  publicDpakTables.clear();
  if (!publicDpakState.messages.length) {
    list.innerHTML = `
      <div class="public-dpak-empty">
        <strong>Fråga på svenska.</strong>
        <span>Exempel: hur många D-pak sålde vi i juni?</span>
      </div>
    `;
    return;
  }
  list.innerHTML = publicDpakState.messages.map((message, index) => {
    if (message.role === "loading") {
      return `<div class="public-dpak-message assistant loading"><span></span> Räknar...</div>`;
    }
    return `
      <article class="public-dpak-message ${message.role}">
        <p>${publicDpakEscape(message.content).replace(/\n/g, "<br>")}</p>
        ${publicDpakRenderTable(message.table, index)}
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
  publicDpakSetVoiceControls();
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
  if (publicDpakState.voice.recording) {
    publicDpakSetVoiceStatus("Stoppa inspelningen innan du skickar.", "error");
    return;
  }
  const input = document.getElementById("publicDpakInput");
  const voicePayload = publicDpakVoicePayload();
  const question = input?.value.trim() || voicePayload?.transcript?.trim() || "";
  if (!question) {
    publicDpakSetVoiceStatus("Skriv frågan i fältet innan du skickar.", "error");
    return;
  }
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
        voice: voicePayload,
      }),
    });
    publicDpakClearPendingVoice();
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
  publicDpakResetVoice();
  publicDpakSaveMessages();
  publicDpakRenderMessages();
  document.getElementById("publicDpakInput")?.focus();
}

function publicDpakInit() {
  publicDpakLoadMessages();
  publicDpakRenderMessages();
  publicDpakLoadStatus();
  publicDpakSetVoiceControls();
  document.getElementById("publicDpakForm")?.addEventListener("submit", publicDpakSubmit);
  document.getElementById("publicDpakVoice")?.addEventListener("click", publicDpakToggleVoice);
  document.getElementById("publicDpakClear")?.addEventListener("click", publicDpakClear);
  document.getElementById("publicDpakMessages")?.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest("[data-public-dpak-open-table]");
    if (!button) return;
    publicDpakOpenTable(button.getAttribute("data-public-dpak-open-table"));
  });
  document.getElementById("publicDpakCloseTable")?.addEventListener("click", publicDpakCloseTable);
  document.getElementById("publicDpakTableModal")?.addEventListener("click", (event) => {
    if (event.target?.id === "publicDpakTableModal") publicDpakCloseTable();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") publicDpakCloseTable();
  });
  document.getElementById("publicDpakInput")?.addEventListener("keydown", (event) => {
    const shortcut = event.ctrlKey || event.metaKey;
    if (shortcut && ["z", "x", "c", "v"].includes(event.key.toLowerCase())) {
      event.stopPropagation();
      return;
    }
    if (event.key !== "Enter" || event.shiftKey || event.altKey || shortcut || event.isComposing) return;
    event.preventDefault();
    document.getElementById("publicDpakForm")?.requestSubmit();
  });
}

publicDpakInit();

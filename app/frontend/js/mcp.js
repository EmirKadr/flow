// @ts-check
const mcpState = {
  user: null,
  tools: [],
  resources: [],
  prompts: [],
  providers: [],
  model: "",
  brain: "gemini",
  thinkingMode: "none",
  busy: false,
  ready: false,
  canAsk: false,
};

function mcpEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function mcpBrainLabel(value) {
  if (value === "deepseek") return "DeepSeek";
  if (value === "nowaste") return "NoWaste";
  if (value === "openai") return "OpenAI";
  if (value === "gemini") return "Gemini";
  if (value === "minimax") return "MiniMax";
  return "LLM";
}

function mcpCurrentProvider() {
  return (mcpState.providers || []).find((provider) => provider.id === mcpState.brain) || null;
}

function mcpRenderBrainControls() {
  const providerSelect = document.getElementById("mcpProviderSelect");
  const modelSelect = document.getElementById("mcpModelSelect");
  const thinkingSelect = document.getElementById("mcpThinkingSelect");
  const providers = Array.isArray(mcpState.providers) ? mcpState.providers : [];
  if (!providerSelect || !modelSelect || !thinkingSelect) return;

  if (!providers.length) {
    providerSelect.innerHTML = `<option value="">Ingen provider</option>`;
    modelSelect.innerHTML = `<option value="">Ingen modell</option>`;
    thinkingSelect.innerHTML = `<option value="none">Ingen thinking</option>`;
    /** @type {HTMLInputElement} */ (providerSelect).disabled = true;
    /** @type {HTMLInputElement} */ (modelSelect).disabled = true;
    /** @type {HTMLInputElement} */ (thinkingSelect).disabled = true;
    return;
  }

  if (!providers.some((provider) => provider.id === mcpState.brain)) {
    mcpState.brain = providers[0].id;
  }
  const provider = mcpCurrentProvider() || providers[0];
  const models = Array.isArray(provider.models) && provider.models.length ? provider.models : [provider.default_model].filter(Boolean);
  if (!models.includes(mcpState.model)) {
    mcpState.model = provider.default_model || models[0] || "";
  }
  const thinkingModes = Array.isArray(provider.thinking_modes) && provider.thinking_modes.length
    ? provider.thinking_modes
    : [{ value: "none", label: "Ingen thinking" }];
  if (!thinkingModes.some((mode) => mode.value === mcpState.thinkingMode)) {
    mcpState.thinkingMode = provider.default_thinking || thinkingModes[0].value || "none";
  }

  providerSelect.innerHTML = providers.map((item) =>
    `<option value="${mcpEscape(item.id)}"${item.id === mcpState.brain ? " selected" : ""}>${mcpEscape(item.label || mcpBrainLabel(item.id))}</option>`
  ).join("");
  modelSelect.innerHTML = models.map((model) =>
    `<option value="${mcpEscape(model)}"${model === mcpState.model ? " selected" : ""}>${mcpEscape(model)}</option>`
  ).join("");
  thinkingSelect.innerHTML = thinkingModes.map((mode) =>
    `<option value="${mcpEscape(mode.value)}"${mode.value === mcpState.thinkingMode ? " selected" : ""}>${mcpEscape(mode.label || mode.value)}</option>`
  ).join("");
  /** @type {HTMLInputElement} */ (providerSelect).disabled = mcpState.busy;
  /** @type {HTMLInputElement} */ (modelSelect).disabled = mcpState.busy || models.length <= 1;
  /** @type {HTMLInputElement} */ (thinkingSelect).disabled = mcpState.busy || thinkingModes.length <= 1;
}

function mcpSetBusy(busy, message = "") {
  mcpState.busy = Boolean(busy);
  const send = document.getElementById("mcpSend");
  const refresh = document.getElementById("mcpRefresh");
  const question = document.getElementById("mcpQuestion");
  const statusText = document.getElementById("mcpStatusText");
  if (send) /** @type {HTMLInputElement} */ (send).disabled = mcpState.busy || !mcpState.ready || !mcpState.canAsk;
  if (refresh) /** @type {HTMLInputElement} */ (refresh).disabled = mcpState.busy;
  if (question) /** @type {HTMLInputElement} */ (question).disabled = mcpState.busy || !mcpState.canAsk;
  if (statusText && message) statusText.textContent = message;
  if (send) send.textContent = mcpState.busy ? "Skickar..." : "Skicka";
  mcpRenderBrainControls();
}

function mcpRenderStatus(payload = {}) {
  const pill = document.getElementById("mcpStatusPill");
  const statusText = document.getElementById("mcpStatusText");
  const missing = Array.isArray(payload.missing) ? payload.missing : [];
  if (Array.isArray(payload.tools)) mcpState.tools = payload.tools;
  if (Array.isArray(payload.resources)) mcpState.resources = payload.resources;
  if (Array.isArray(payload.prompts)) mcpState.prompts = payload.prompts;
  if (Array.isArray(payload.providers)) mcpState.providers = payload.providers;
  mcpState.brain = String(payload.brain || mcpState.brain || "gemini");
  mcpState.model = String(payload.model || mcpState.model || mcpState.brain);
  mcpState.thinkingMode = String(payload.thinking_mode || mcpState.thinkingMode || "none");
  const brainLabel = mcpBrainLabel(mcpState.brain);

  const hasError = Boolean(payload.error);
  const contextCount = (mcpState.resources || []).length + (mcpState.prompts || []).length;
  mcpState.ready = Boolean(
    payload.configured &&
    payload.token_configured &&
    payload.url_configured &&
    payload.brain_configured &&
    !hasError
  );
  if (!mcpState.canAsk && mcpState.ready) {
    mcpState.ready = false;
  }

  mcpRenderBrainControls();

  if (pill) {
    pill.className = "mcp-status-pill";
    if (mcpState.ready) {
      pill.classList.add("ok");
      pill.textContent = "Redo";
    } else if (hasError || missing.length) {
      pill.classList.add("error");
      pill.textContent = "Stopp";
    } else {
      pill.classList.add("warn");
      pill.textContent = "Väntar";
    }
  }

  if (statusText) {
    if (hasError) {
      statusText.textContent = payload.error;
    } else if (missing.length) {
      statusText.textContent = `Saknar ${missing.join(", ")}.`;
    } else if (!mcpState.canAsk) {
      statusText.textContent = "Du kan se vyn men inte skicka frågor.";
    } else if (!contextCount) {
      statusText.textContent = `${brainLabel} ${mcpState.model} är kopplad. MCP svarade, men ingen textkontext hittades.`;
    } else {
      statusText.textContent = `${brainLabel} ${mcpState.model} är kopplad till MCP. ${contextCount} kontextdelar hittades.`;
    }
  }

  mcpRenderContext(payload.tools || [], payload.resources || [], payload.prompts || []);
  mcpSetBusy(false);
}

function mcpRenderContext(tools = [], resources = [], prompts = []) {
  const panel = document.getElementById("mcpToolsPanel");
  const meta = document.getElementById("mcpToolsMeta");
  const list = document.getElementById("mcpToolsList");
  if (!panel || !list) return;

  const items = [
    ...(resources || []).map((resource) => ({
      title: resource.title || "MCP-resurs",
      code: resource.mime_type || "resource",
      badge: "Resurs",
      description: resource.description || "",
      detail: "",
      ready: true,
    })),
    ...(prompts || []).map((prompt) => ({
      title: prompt.title || prompt.name || "MCP-prompt",
      code: prompt.name || "prompt",
      badge: prompt.supports_empty_arguments ? "Prompt" : "Prompt med input",
      description: prompt.description || "",
      detail: (prompt.input_fields || []).join(", "),
      ready: Boolean(prompt.supports_empty_arguments),
    })),
    ...(tools || []).map((tool) => ({
      title: tool.title || tool.name || "MCP-tool",
      code: tool.name || "tool",
      badge: tool.supports_question ? "Tool" : "Tool",
      description: tool.description || "",
      detail: (tool.input_fields || []).join(", "),
      ready: Boolean(tool.supports_question),
    })),
  ];

  panel.hidden = !items.length;
  if (meta) {
    meta.textContent = `${(resources || []).length} resurser, ${(prompts || []).length} prompts, ${(tools || []).length} tools.`;
  }
  list.innerHTML = items.map((item) => `
    <article class="mcp-tool${item.ready ? " is-ready" : ""}">
      <div>
        <strong>${mcpEscape(item.title)}</strong>
        <code>${mcpEscape(item.code)}</code>
      </div>
      <span>${mcpEscape(item.badge)}</span>
      ${item.description ? `<p>${mcpEscape(item.description)}</p>` : ""}
      ${item.detail ? `<small>${mcpEscape(item.detail)}</small>` : ""}
    </article>
  `).join("");
}

function mcpRenderAnswer(response) {
  const panel = document.getElementById("mcpAnswerPanel");
  const meta = document.getElementById("mcpAnswerMeta");
  const answer = document.getElementById("mcpAnswer");
  if (!panel || !answer) return;
  panel.hidden = false;
  if (meta) {
    const title = response.tool_title || response.tool || "MCP";
    const toolCalls = Number(response.tool_calls || 0);
    const toolsUsed = Array.isArray(response.tools_used) ? response.tools_used.filter(Boolean).slice(0, 4) : [];
    const thinking = response.thinking_mode && response.thinking_mode !== "none" ? ` · ${response.thinking_mode}` : "";
    const toolText = toolCalls ? ` · ${toolCalls} tool-anrop${toolsUsed.length ? ` (${toolsUsed.join(", ")})` : ""}` : "";
    meta.textContent = `${title}${thinking} · ${response.content_items || 0} kontextdelar${toolText}`;
  }
  answer.innerHTML = typeof renderAssistantMarkdown === "function"
    ? renderAssistantMarkdown(response.answer || "")
    : mcpEscape(response.answer || "").replace(/\n/g, "<br>");
}

function mcpClearAnswer() {
  const panel = document.getElementById("mcpAnswerPanel");
  const answer = document.getElementById("mcpAnswer");
  const meta = document.getElementById("mcpAnswerMeta");
  if (panel) panel.hidden = true;
  if (answer) answer.innerHTML = "";
  if (meta) meta.textContent = "";
}

async function loadMcpStatus() {
  mcpSetBusy(true, "Kontrollerar MCP...");
  try {
    const payload = await api.get("/api/mcp/status", { cacheTtlMs: 0, logGetUserEvent: false });
    mcpState.tools = Array.isArray(payload.tools) ? payload.tools : [];
    mcpState.resources = Array.isArray(payload.resources) ? payload.resources : [];
    mcpState.prompts = Array.isArray(payload.prompts) ? payload.prompts : [];
    mcpRenderStatus(payload);
  } catch (error) {
    mcpState.tools = [];
    mcpState.resources = [];
    mcpState.prompts = [];
    mcpState.providers = [];
    mcpState.ready = false;
    mcpRenderStatus({
      configured: false,
      brain_configured: false,
      deepseek_configured: false,
      gemini_configured: false,
      tools: [],
      resources: [],
      prompts: [],
      error: error.message || "Kunde inte läsa MCP-status.",
    });
  }
}

async function submitMcpQuestion(event) {
  event.preventDefault();
  if (mcpState.busy || !mcpState.canAsk) return;
  const questionEl = document.getElementById("mcpQuestion");
  const question = String(/** @type {HTMLInputElement} */ (questionEl)?.value || "").trim();
  if (!question) {
    showToast("Skriv en fråga först.", "warn", 3000);
    return;
  }
  if (!mcpState.ready) {
    showToast("MCP är inte redo.", "warn", 5000);
    return;
  }

  mcpClearAnswer();
  mcpSetBusy(true, "Skickar fråga...");
  try {
    window.flowTrack?.("mcp_query", {
      view_id: "mcp",
      control_id: "mcp-query-send",
      feature: "mcp",
      status: "start",
      detail: {
        brain: mcpState.brain,
        model: mcpState.model,
        thinking_mode: mcpState.thinkingMode,
        question_chars: question.length,
      },
    });
    const response = await api.post("/api/mcp/query", {
      question,
      tool: mcpState.brain,
      provider: mcpState.brain,
      model: mcpState.model,
      thinking_mode: mcpState.thinkingMode,
    }, { logLabel: "MCP-fråga" });
    mcpRenderAnswer(response);
    showToast("MCP svarade.", "success", 2500);
  } catch (error) {
    showToast(error.message || "MCP-frågan misslyckades.", "error", 7000);
  } finally {
    mcpSetBusy(false);
    questionEl?.focus();
  }
}

async function initMcpPage() {
  const user = await initPage("mcp");
  if (!user) return;
  mcpState.user = user;
  mcpState.canAsk = canEditPage(user, "mcp");
  document.getElementById("mcpQuestionForm")?.addEventListener("submit", submitMcpQuestion);
  document.getElementById("mcpProviderSelect")?.addEventListener("change", (event) => {
    mcpState.brain = String(/** @type {HTMLInputElement} */ (event.target).value || "");
    const provider = mcpCurrentProvider();
    mcpState.model = provider?.default_model || (provider?.models || [])[0] || "";
    mcpState.thinkingMode = provider?.default_thinking || (provider?.thinking_modes || [])[0]?.value || "none";
    mcpRenderBrainControls();
  });
  document.getElementById("mcpModelSelect")?.addEventListener("change", (event) => {
    mcpState.model = String(/** @type {HTMLInputElement} */ (event.target).value || "");
  });
  document.getElementById("mcpThinkingSelect")?.addEventListener("change", (event) => {
    mcpState.thinkingMode = String(/** @type {HTMLInputElement} */ (event.target).value || "none");
  });
  document.getElementById("mcpRefresh")?.addEventListener("click", loadMcpStatus);
  document.getElementById("mcpClear")?.addEventListener("click", () => {
    /** @type {HTMLInputElement} */ (document.getElementById("mcpQuestion")).value = "";
    mcpClearAnswer();
  });
  document.getElementById("mcpQuestion")?.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      /** @type {HTMLFormElement | null} */ (document.getElementById("mcpQuestionForm"))?.requestSubmit();
    }
  });
  await loadMcpStatus();
}

initMcpPage();

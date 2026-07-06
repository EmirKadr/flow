let sidebarProductivityContextMenu = null;
let sidebarProductivityContextMenuListenersInstalled = false;
let sidebarContextMenu = null;
let sidebarContextMenuListenersInstalled = false;

function renderSidebarLink(page, { active = false, subview = false } = {}) {
  const classes = [
    "sidebar-link",
    page.className || "",
    active ? "active" : "",
    subview ? "sidebar-subview" : "",
  ].filter(Boolean).join(" ");
  const idAttr = page.linkId ? ` id="${page.linkId}"` : "";
  const icon = page.iconHtml || escapeHtml(page.icon || "");
  const contextMenuAttr = Array.isArray(page.contextMenuViewIds) && page.contextMenuViewIds.length
    ? ' data-sidebar-context-menu="true" aria-haspopup="menu"'
    : "";
  return `
    <a href="${page.href}"${idAttr} class="${classes}" title="${escapeHtml(page.label)}" data-sidebar-view-id="${escapeHtml(page.id || "")}"${contextMenuAttr}>
      <span class="icon" aria-hidden="true">${icon}${page.trailingHtml || ""}</span>
      <span>${escapeHtml(page.label)}</span>
    </a>
  `;
}

function closeSidebarContextMenu() {
  sidebarContextMenu?.remove();
  sidebarContextMenu = null;
}

function positionSidebarContextMenu(menu, x, y) {
  const margin = 8;
  const rect = menu.getBoundingClientRect();
  const left = Math.max(margin, Math.min(x, window.innerWidth - rect.width - margin));
  const top = Math.max(margin, Math.min(y, window.innerHeight - rect.height - margin));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

function openSidebarContextMenu(event, user, activePage, pageId) {
  const pages = sidebarPageDefinitions(user, activePage);
  const pageById = Object.fromEntries(pages.map((page) => [page.id, page]));
  const sourcePage = pageById[pageId];
  const items = (sourcePage?.contextMenuViewIds || [])
    .map((viewId) => pageById[viewId])
    .filter((page) => page?.visible && page.href && page.href !== "#");
  if (!items.length) return;

  event.preventDefault();
  event.stopPropagation();
  closeSidebarContextMenu();
  closeSidebarProductivityContextMenu();

  const menu = document.createElement("div");
  menu.className = "sidebar-context-menu";
  menu.dataset.sidebarContextMenu = "true";
  menu.setAttribute("role", "menu");
  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("role", "menuitem");
    button.dataset.sidebarContextTarget = item.id;
    button.textContent = item.label;
    button.classList.toggle("active", Boolean(item.active));
    button.addEventListener("click", () => {
      closeSidebarContextMenu();
      if (typeof flowTrack === "function") {
        flowTrack("navigate", {
          control_id: `sidebar-${pageId}-${item.id}`,
          view: "sidebar",
          target_view: item.id,
        });
      }
      window.location.href = item.href;
    });
    menu.appendChild(button);
  });

  document.body.appendChild(menu);
  positionSidebarContextMenu(menu, event.clientX, event.clientY);
  sidebarContextMenu = menu;
  menu.querySelector("button")?.focus({ preventScroll: true });
}

function ensureSidebarContextMenuListeners() {
  if (sidebarContextMenuListenersInstalled) return;
  document.addEventListener("click", (event) => {
    if (event.target.closest?.("[data-sidebar-context-menu]")) return;
    closeSidebarContextMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSidebarContextMenu();
  });
  window.addEventListener("blur", closeSidebarContextMenu);
  sidebarContextMenuListenersInstalled = true;
}

function initSidebarContextMenus(user, activePage) {
  closeSidebarContextMenu();
  ensureSidebarContextMenuListeners();
  document.querySelectorAll("[data-sidebar-context-menu]").forEach((link) => {
    link.addEventListener("contextmenu", (event) => {
      openSidebarContextMenu(event, user, activePage, link.dataset.sidebarViewId);
    });
  });
}

function closeSidebarProductivityContextMenu() {
  sidebarProductivityContextMenu?.remove();
  sidebarProductivityContextMenu = null;
}

function positionSidebarProductivityContextMenu(menu, x, y) {
  const margin = 8;
  const rect = menu.getBoundingClientRect();
  const left = Math.max(margin, Math.min(x, window.innerWidth - rect.width - margin));
  const top = Math.max(margin, Math.min(y, window.innerHeight - rect.height - margin));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

function sidebarTodayIsoDate() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function sidebarSankeyInboundPeriodValue() {
  const params = new URLSearchParams(window.location.search || "");
  const period = document.querySelector(".productivity-overview-period-toggle button.active")?.dataset?.period
    || params.get("period")
    || "day";
  return ["day", "week", "month", "year"].includes(period) ? period : "day";
}

function sidebarSankeyInboundDateValue() {
  const params = new URLSearchParams(window.location.search || "");
  return document.querySelector("[data-flow-context-date]")?.value
    || params.get("date")
    || sidebarTodayIsoDate();
}

function sidebarSankeyInboundUrl() {
  const params = new URLSearchParams();
  params.set("period", sidebarSankeyInboundPeriodValue());
  const date = sidebarSankeyInboundDateValue();
  if (date) params.set("date", date);
  return `/sankey-inbound.html?${params.toString()}`;
}

function openSidebarProductivityContextMenu(event, user) {
  if (!(typeof canViewPage === "function" && canViewPage(user, "sankeyInbound"))) return;
  event.preventDefault();
  event.stopPropagation();
  closeSidebarProductivityContextMenu();

  const menu = document.createElement("div");
  menu.className = "productivity-overview-context-menu";
  menu.dataset.sidebarProductivityContextMenu = "true";
  menu.innerHTML = `
    <button type="button" data-sidebar-sankey-inbound>
      Sankey - Inbound
    </button>
  `;
  menu.querySelector("[data-sidebar-sankey-inbound]")?.addEventListener("click", () => {
    closeSidebarProductivityContextMenu();
    if (typeof flowTrack === "function") {
      flowTrack("navigate", {
        control_id: "sidebar-productivity-sankey-inbound",
        view: "sidebar",
        target_view: "sankeyInbound",
        period: sidebarSankeyInboundPeriodValue(),
      });
    }
    window.location.href = sidebarSankeyInboundUrl();
  });

  document.body.appendChild(menu);
  positionSidebarProductivityContextMenu(menu, event.clientX, event.clientY);
  sidebarProductivityContextMenu = menu;
  menu.querySelector("button")?.focus({ preventScroll: true });
}

function ensureSidebarProductivityContextMenuListeners() {
  if (sidebarProductivityContextMenuListenersInstalled) return;
  document.addEventListener("click", (event) => {
    if (event.target.closest?.("[data-sidebar-productivity-context-menu]")) return;
    closeSidebarProductivityContextMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSidebarProductivityContextMenu();
  });
  window.addEventListener("blur", closeSidebarProductivityContextMenu);
  sidebarProductivityContextMenuListenersInstalled = true;
}

function initSidebarProductivityContextMenu(user) {
  closeSidebarProductivityContextMenu();
  if (!(typeof canViewPage === "function" && canViewPage(user, "sankeyInbound"))) return;
  ensureSidebarProductivityContextMenuListeners();
  const link = document.querySelector('[data-sidebar-view-id="productivity"]');
  link?.addEventListener("contextmenu", (event) => openSidebarProductivityContextMenu(event, user));
}

function renderAllocationUploadUtility(user, activePage) {
  if (!canViewPage(user, "allocationUploads")) return "";
  const activeClass = activePage === "allocationUploads" ? " active" : "";
  return `
        <a href="/uppladdningar.html" class="database-toggle${activeClass}" id="allocation-upload-link" title="Uppladdningar" aria-label="Uppladdningar" aria-haspopup="menu">
          ${DATABASE_ICON}
          <span class="upload-arrow" aria-hidden="true">&uarr;</span>
          <span class="upload-notice" id="allocation-upload-notice" hidden></span>
        </a>
  `;
}

function renderLogUtility() {
  return `
        <button class="log-toggle" id="log-toggle" type="button" title="Logg" aria-label="Öppna logg" aria-controls="log-sidebar" aria-expanded="false">
          ${LOG_ICON}
          <span class="log-arrow" aria-hidden="true">&uarr;</span>
          <span class="log-notice" id="log-notice" hidden></span>
        </button>
  `;
}

function setLogSidebarOpen(open) {
  const panel = document.getElementById("log-sidebar");
  const toggle = document.getElementById("log-toggle");
  if (!panel) return;
  panel.hidden = !open;
  panel.classList.toggle("is-open", open);
  toggle?.classList.toggle("active", open);
  toggle?.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) clearAppLogNotice();
}

function ensureLogSidebar(app) {
  if (!app) return;
  let panel = document.getElementById("log-sidebar");
  if (!panel) {
    panel = document.createElement("aside");
    panel.id = "log-sidebar";
    panel.className = "log-sidebar";
    panel.hidden = true;
    app.appendChild(panel);
  }
  panel.innerHTML = `
    <div class="log-sidebar-head">
      <h2>Logg</h2>
      <button type="button" class="log-sidebar-close" id="log-sidebar-close" aria-label="Stäng logg">&times;</button>
    </div>
    <div class="log-sidebar-body">
      <p class="log-sidebar-empty">Ingen logg att visa ännu.</p>
    </div>
  `;
  panel.querySelector("#log-sidebar-close")?.insertAdjacentHTML(
    "beforebegin",
    '<button type="button" class="log-sidebar-clear" id="log-sidebar-clear">Rensa</button>',
  );
  panel.querySelector("#log-sidebar-clear").addEventListener("click", clearAppLog);
  panel.querySelector("#log-sidebar-close").addEventListener("click", () => setLogSidebarOpen(false));
  renderAppLogEntries();
  updateAppLogNotice();
}

function initLogSidebarToggle() {
  const toggle = document.getElementById("log-toggle");
  if (!toggle) return;
  toggle.addEventListener("click", () => {
    const panel = document.getElementById("log-sidebar");
    setLogSidebarOpen(panel?.hidden);
  });
  updateAppLogNotice();
}

function renderAssistantUtility() {
  return `
        <button class="assistant-toggle" id="assistant-toggle" type="button" title="Apphjälp" aria-label="Öppna apphjälp" aria-controls="assistant-chat-panel" aria-expanded="false">
          ${ASSISTANT_CHAT_ICON}
        </button>
  `;
}

function safeSessionGet(key) {
  try {
    return sessionStorage.getItem(key);
  } catch (e) {
    return null;
  }
}

function safeSessionSet(key, value) {
  try {
    sessionStorage.setItem(key, value);
  } catch (e) {}
}

function safeSessionRemove(key) {
  try {
    sessionStorage.removeItem(key);
  } catch (e) {}
}

function clearAssistantLocalSession(options = {}) {
  safeSessionRemove(ASSISTANT_CHAT_STORAGE_KEY);
  if (!options.keepOpenState) safeSessionRemove(ASSISTANT_CHAT_OPEN_KEY);
  safeSessionRemove(ASSISTANT_CHAT_COUNT_KEY);
  safeSessionRemove(ASSISTANT_CHAT_DRAFT_KEY);
  if (!options.keepStorageVersion) safeSessionRemove(ASSISTANT_CHAT_VERSION_KEY);
  assistantChatPending = false;
}

function ensureAssistantLocalSessionVersion() {
  if (safeSessionGet(ASSISTANT_CHAT_VERSION_KEY) === ASSISTANT_CHAT_STORAGE_VERSION) return;
  clearAssistantLocalSession();
  safeSessionSet(ASSISTANT_CHAT_VERSION_KEY, ASSISTANT_CHAT_STORAGE_VERSION);
}

function normalizeAssistantMessages(value) {
  return (Array.isArray(value) ? value : [])
    .filter((message) => message && (message.role === "user" || message.role === "assistant"))
    .map((message) => {
      const toolCalls = Number(message.toolCalls) || 0;
      return {
        role: message.role,
        content: String(message.content || "").trim().slice(0, 4000),
        ...(toolCalls > 0 ? { toolCalls } : {}),
      };
    })
    .filter((message) => message.content)
    .slice(-21);
}

function readAssistantMessages() {
  try {
    return normalizeAssistantMessages(JSON.parse(safeSessionGet(ASSISTANT_CHAT_STORAGE_KEY) || "[]"));
  } catch (e) {
    return [];
  }
}

function writeAssistantMessages(messages) {
  safeSessionSet(ASSISTANT_CHAT_STORAGE_KEY, JSON.stringify(normalizeAssistantMessages(messages)));
}

function readAssistantQuestionCount() {
  const raw = safeSessionGet(ASSISTANT_CHAT_COUNT_KEY);
  const parsed = Number(raw);
  if (Number.isFinite(parsed) && parsed >= 0) return Math.min(ASSISTANT_CHAT_MAX_QUESTIONS, parsed);
  return Math.min(
    ASSISTANT_CHAT_MAX_QUESTIONS,
    readAssistantMessages().filter((message) => message.role === "user").length
  );
}

function writeAssistantQuestionCount(count) {
  const safeCount = Math.max(0, Math.min(ASSISTANT_CHAT_MAX_QUESTIONS, Number(count) || 0));
  safeSessionSet(ASSISTANT_CHAT_COUNT_KEY, String(safeCount));
  return safeCount;
}

function isAssistantChatOpen() {
  return safeSessionGet(ASSISTANT_CHAT_OPEN_KEY) === "1";
}

function writeAssistantChatOpen(open) {
  safeSessionSet(ASSISTANT_CHAT_OPEN_KEY, open ? "1" : "0");
}

function assistantFriendlyError(error) {
  if (error?.status === 429) {
    return "Du har använt 10 frågor i den här sessionen. Klicka Rensa dialog för att börja om.";
  }
  if (error?.status === 500 && error?.body?.detail) {
    return String(error.body.detail);
  }
  if (error?.status === 502 && error?.body?.detail) {
    return String(error.body.detail);
  }
  if (error?.status === 503) {
    return error.message || "Appchatten är inte konfigurerad på servern ännu.";
  }
  if (error?.status === 504) {
    return "MiniMax svarade inte i tid. Prova igen om en stund.";
  }
  if (error?.status === 0) {
    return "Jag kan inte nå servern just nu. Kontrollera att appen är öppnad via rätt adress och att backend är igång.";
  }
  return error?.message || "Jag kunde inte hämta ett svar just nu.";
}

function renderAssistantMessages() {
  const list = document.getElementById("assistant-chat-messages");
  const counter = document.getElementById("assistant-chat-counter");
  const send = document.getElementById("assistant-chat-send");
  const statusEl = document.getElementById("assistant-chat-status");
  if (!list) return;

  const messages = readAssistantMessages();
  const used = readAssistantQuestionCount();
  if (counter) counter.textContent = `${used}/${ASSISTANT_CHAT_MAX_QUESTIONS} frågor i sessionen`;
  if (send) send.disabled = used >= ASSISTANT_CHAT_MAX_QUESTIONS || assistantChatPending;
  if (statusEl) {
    if (used >= ASSISTANT_CHAT_MAX_QUESTIONS) statusEl.textContent = "Max nått. Rensa dialog för att fortsätta.";
    else if (!assistantChatPending) statusEl.textContent = "";
  }

  if (!messages.length) {
    list.innerHTML = `
      <div class="assistant-chat-empty">
        Fråga om knappar, feltexter, behörigheter, import, schema, produktivitet eller lagerverktyg.
      </div>
    `;
    return;
  }
  list.innerHTML = messages.map((message) => `
    <div class="assistant-chat-message ${message.role}">
      ${message.role === "assistant" ? renderAssistantMarkdown(message.content) : escapeHtml(message.content).replace(/\n/g, "<br>")}
      ${message.role === "assistant" && message.toolCalls > 0
        ? `<div class="assistant-chat-meta">Hämtade live-data (${message.toolCalls} uppslag)</div>`
        : ""}
    </div>
  `).join("");
  if (assistantChatPending) {
    list.insertAdjacentHTML("beforeend", `
      <div class="assistant-chat-message assistant assistant-chat-loading" aria-label="Apphjälpen hämtar svar">
        <span class="assistant-chat-spinner" aria-hidden="true"></span>
        <span>Hämtar svar</span>
      </div>
    `);
  }
  list.scrollTop = list.scrollHeight;
}

function setAssistantChatPending(pending) {
  assistantChatPending = Boolean(pending);
  const send = document.getElementById("assistant-chat-send");
  const textarea = document.getElementById("assistant-chat-input");
  const statusEl = document.getElementById("assistant-chat-status");
  if (send) {
    send.disabled = assistantChatPending || readAssistantQuestionCount() >= ASSISTANT_CHAT_MAX_QUESTIONS;
    send.textContent = pending ? "Skickar..." : "Skicka";
  }
  if (textarea) textarea.disabled = assistantChatPending;
  if (statusEl) statusEl.textContent = assistantChatPending ? "Hämtar svar..." : "";
  renderAssistantMessages();
}

function setAssistantChatOpen(open) {
  const panel = document.getElementById("assistant-chat-panel");
  const toggle = document.getElementById("assistant-toggle");
  if (!panel) return;
  panel.hidden = !open;
  panel.classList.toggle("is-open", open);
  toggle?.classList.toggle("active", open);
  toggle?.setAttribute("aria-expanded", open ? "true" : "false");
  toggle?.setAttribute("aria-label", open ? "Stäng apphjälp" : "Öppna apphjälp");
  writeAssistantChatOpen(open);
  if (open) {
    renderAssistantMessages();
    setTimeout(() => document.getElementById("assistant-chat-input")?.focus(), 0);
  }
}

async function clearAssistantChat() {
  clearAssistantLocalSession({ keepOpenState: true, keepStorageVersion: true });
  const input = document.getElementById("assistant-chat-input");
  if (input) input.value = "";
  try {
    await api.post("/api/assistant/clear", {});
  } catch (error) {
    showToast(error.message || "Dialogen rensades lokalt, men serverkvoten kunde inte nollställas.", "warn", 7000);
  }
  renderAssistantMessages();
}

async function submitAssistantQuestion(event) {
  event.preventDefault();
  if (assistantChatPending) return;
  const input = document.getElementById("assistant-chat-input");
  const statusEl = document.getElementById("assistant-chat-status");
  const question = String(input?.value || "").trim();
  if (!question) return;
  if (readAssistantQuestionCount() >= ASSISTANT_CHAT_MAX_QUESTIONS) {
    if (statusEl) statusEl.textContent = "Max 10 frågor. Rensa dialog för att börja om.";
    return;
  }

  const messages = readAssistantMessages();
  messages.push({ role: "user", content: question });
  writeAssistantMessages(messages);
  safeSessionRemove(ASSISTANT_CHAT_DRAFT_KEY);
  if (input) input.value = "";
  renderAssistantMessages();
  setAssistantChatPending(true);

  try {
    const response = await api.post("/api/assistant/chat", {
      messages: readAssistantMessages(),
      page_path: window.location.pathname || "",
    });
    const nextMessages = readAssistantMessages();
    nextMessages.push({
      role: "assistant",
      content: response?.answer || "Jag fick inget textinnehåll tillbaka.",
      toolCalls: Number(response?.tool_calls) || 0,
    });
    writeAssistantMessages(nextMessages);
    if (typeof response?.remaining_questions === "number") {
      writeAssistantQuestionCount(ASSISTANT_CHAT_MAX_QUESTIONS - response.remaining_questions);
    } else {
      writeAssistantQuestionCount(readAssistantQuestionCount() + 1);
    }
  } catch (error) {
    const nextMessages = readAssistantMessages();
    nextMessages.push({ role: "assistant", content: assistantFriendlyError(error) });
    writeAssistantMessages(nextMessages);
    if (error?.status === 429) writeAssistantQuestionCount(ASSISTANT_CHAT_MAX_QUESTIONS);
    showToast(error.message || "Kunde inte hämta chattsvar.", "error", 7000);
  } finally {
    setAssistantChatPending(false);
    renderAssistantMessages();
    document.getElementById("assistant-chat-input")?.focus();
  }
}

function ensureAssistantChatPanel(app) {
  if (!app) return;
  ensureAssistantLocalSessionVersion();
  let panel = document.getElementById("assistant-chat-panel");
  if (!panel) {
    panel = document.createElement("aside");
    panel.id = "assistant-chat-panel";
    panel.className = "assistant-chat-panel";
    app.appendChild(panel);
  }
  panel.hidden = !isAssistantChatOpen();
  panel.innerHTML = `
    <div class="assistant-chat-head">
      <div>
        <h2>Apphjälp</h2>
        <div class="assistant-chat-counter" id="assistant-chat-counter">0/${ASSISTANT_CHAT_MAX_QUESTIONS} frågor i sessionen</div>
      </div>
      <button type="button" class="assistant-chat-clear" id="assistant-chat-clear">Rensa dialog</button>
    </div>
    <div class="assistant-chat-messages" id="assistant-chat-messages" role="log" aria-live="polite"></div>
    <form class="assistant-chat-form" id="assistant-chat-form">
      <textarea id="assistant-chat-input" rows="2" maxlength="1200" placeholder="Ställ en fråga om appen...">${escapeHtml(safeSessionGet(ASSISTANT_CHAT_DRAFT_KEY) || "")}</textarea>
      <div class="assistant-chat-actions">
        <span class="assistant-chat-status" id="assistant-chat-status" aria-live="polite"></span>
        <button type="submit" class="primary" id="assistant-chat-send">Skicka</button>
      </div>
    </form>
  `;
  panel.querySelector("#assistant-chat-form")?.addEventListener("submit", submitAssistantQuestion);
  panel.querySelector("#assistant-chat-clear")?.addEventListener("click", () => {
    void clearAssistantChat();
  });
  panel.querySelector("#assistant-chat-input")?.addEventListener("input", (event) => {
    safeSessionSet(ASSISTANT_CHAT_DRAFT_KEY, event.target.value);
  });
  panel.querySelector("#assistant-chat-input")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    panel.querySelector("#assistant-chat-form")?.requestSubmit();
  });
  renderAssistantMessages();
}

function initAssistantChatToggle() {
  const toggle = document.getElementById("assistant-toggle");
  if (!toggle) return;
  toggle.addEventListener("click", () => {
    setAssistantChatOpen(!isAssistantChatOpen());
  });
  setAssistantChatOpen(isAssistantChatOpen());
}

function renderSidebarNav(user, activePage) {
  const pages = sidebarPageDefinitions(user, activePage);
  const pageById = Object.fromEntries(pages.map((page) => [page.id, page]));
  const visibleIds = new Set(pages.filter((page) => page.visible && page.sidebar !== false).map((page) => page.id));
  const layout = normalizeSidebarLayout(sidebarLayoutForRender())
    .filter((item) => visibleIds.has(item.id))
    .map((item) => ({
      ...item,
      parentId: visibleIds.has(item.parentId) ? item.parentId : null,
    }));
  const childrenByParent = {};
  for (const item of layout) {
    if (!item.parentId) continue;
    if (!childrenByParent[item.parentId]) childrenByParent[item.parentId] = [];
    childrenByParent[item.parentId].push(item);
  }

  return layout
    .filter((item) => !item.parentId)
    .map((item) => {
      const page = pageById[item.id];
      if (!page) return "";
      const children = childrenByParent[item.id] || [];
      const childActive = children.some((child) => pageById[child.id]?.active);
      const heading = item.heading
        ? `<div class="sidebar-heading">${escapeHtml(item.heading)}</div>`
        : "";
      const childHtml = children.length
        ? `<div class="sidebar-subviews">${children.map((child) => renderSidebarLink(pageById[child.id], { active: pageById[child.id]?.active, subview: true })).join("")}</div>`
        : "";
      return `${heading}${renderSidebarLink(page, { active: page.active || childActive })}${childHtml}`;
    })
    .join("");
}

function openSidebarEditor(user, activePage) {
  const pages = sidebarPageDefinitions(user, activePage).filter((page) => page.visible && page.sidebar !== false);
  const pageById = Object.fromEntries(pages.map((page) => [page.id, page]));
  let draft = normalizeSidebarLayout(sidebarLayoutForRender()).filter((item) => pageById[item.id]);

  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal wide sidebar-editor-modal">
      <h2>Redigera meny</h2>
      <p class="note">Rubriker och undervyer visas bara när sidomenyn är utfälld.</p>
      <div class="sidebar-editor-list" id="sidebar-editor-list"></div>
      <div class="actions">
        <button type="button" id="sidebar-editor-reset">Standard</button>
        <button type="button" id="sidebar-editor-cancel">Avbryt</button>
        <button type="button" class="primary" id="sidebar-editor-save">Spara</button>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);

  const list = backdrop.querySelector("#sidebar-editor-list");
  const parentOptionsFor = (item) => [
    '<option value="">Ingen</option>',
    ...draft
      .filter((candidate) => candidate.id !== item.id)
      .map((candidate) => `<option value="${candidate.id}" ${item.parentId === candidate.id ? "selected" : ""}>${escapeHtml(pageById[candidate.id]?.label || candidate.id)}</option>`),
  ].join("");

  const renderRows = () => {
    list.innerHTML = draft.map((item, index) => {
      const page = pageById[item.id];
      return `
        <div class="sidebar-editor-row ${item.parentId ? "is-child" : ""}" data-index="${index}">
          <div class="sidebar-editor-view">
            <span class="sidebar-editor-icon">${page.iconHtml || escapeHtml(page.icon || "")}</span>
            <strong>${escapeHtml(page.label)}</strong>
          </div>
          <div class="sidebar-editor-move">
            <button type="button" data-move="-1" ${index === 0 ? "disabled" : ""} aria-label="Flytta upp" title="Flytta upp">${SIDEBAR_MOVE_UP_ICON}</button>
            <button type="button" data-move="1" ${index === draft.length - 1 ? "disabled" : ""} aria-label="Flytta ner" title="Flytta ner">${SIDEBAR_MOVE_DOWN_ICON}</button>
          </div>
          <label class="sidebar-editor-field">
            <span>Rubrik ovanför</span>
            <input data-heading value="${escapeHtml(item.heading || "")}" maxlength="80" />
          </label>
          <label class="sidebar-editor-field">
            <span>Under</span>
            <select data-parent>${parentOptionsFor(item)}</select>
          </label>
        </div>
      `;
    }).join("");

    list.querySelectorAll("[data-move]").forEach((button) => {
      button.addEventListener("click", () => {
        const row = button.closest(".sidebar-editor-row");
        const index = Number(row.dataset.index);
        const nextIndex = index + Number(button.dataset.move);
        if (nextIndex < 0 || nextIndex >= draft.length) return;
        const [item] = draft.splice(index, 1);
        draft.splice(nextIndex, 0, item);
        renderRows();
      });
    });
    list.querySelectorAll("[data-heading]").forEach((input) => {
      input.addEventListener("input", () => {
        draft[Number(input.closest(".sidebar-editor-row").dataset.index)].heading = input.value;
      });
    });
    list.querySelectorAll("[data-parent]").forEach((select) => {
      select.addEventListener("change", () => {
        draft[Number(select.closest(".sidebar-editor-row").dataset.index)].parentId = select.value || null;
        draft = normalizeSidebarLayout(draft).filter((item) => pageById[item.id]);
        renderRows();
      });
    });
  };

  backdrop.querySelector("#sidebar-editor-cancel").addEventListener("click", () => backdrop.remove());
  backdrop.querySelector("#sidebar-editor-reset").addEventListener("click", () => {
    draft = sidebarDefaultLayout().filter((item) => pageById[item.id]);
    renderRows();
  });
  backdrop.querySelector("#sidebar-editor-save").addEventListener("click", async () => {
    const saveButton = backdrop.querySelector("#sidebar-editor-save");
    saveButton.disabled = true;
    try {
      const response = await api.put("/api/settings/sidebar", { items: sidebarLayoutPayload(draft) });
      cacheSidebarLayout(response?.items || draft);
      backdrop.remove();
      renderSidebar(user, activePage);
      showToast("Menyn sparades för alla.", "success", 2500);
    } catch (error) {
      saveButton.disabled = false;
      showToast(error.message || "Kunde inte spara menyn.", "error", 7000);
    }
  });
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) backdrop.remove();
  });
  renderRows();
}

function sidebarUserSnapshot(user) {
  if (!user) return null;
  return {
    username: user.username || "",
    display_name: user.display_name || "",
    role: user.role || "",
    roles: userRoles(user),
    is_super_user: Boolean(user.is_super_user),
    must_change_password: Boolean(user.must_change_password),
  };
}

function cacheSidebarUser(user) {
  try {
    const snapshot = sidebarUserSnapshot(user);
    if (snapshot) {
      const serialized = JSON.stringify(snapshot);
      sessionStorage.setItem(SIDEBAR_USER_CACHE_KEY, serialized);
      localStorage.setItem(SIDEBAR_USER_CACHE_KEY, serialized);
    }
  } catch (e) {}
}

function readCachedSidebarUser() {
  try {
    const raw = sessionStorage.getItem(SIDEBAR_USER_CACHE_KEY) || localStorage.getItem(SIDEBAR_USER_CACHE_KEY);
    if (!raw) return null;
    const user = JSON.parse(raw);
    return user?.username || user?.display_name ? user : null;
  } catch (e) {
    return null;
  }
}

function clearCachedSidebarUser() {
  try { sessionStorage.removeItem(SIDEBAR_USER_CACHE_KEY); } catch (e) {}
  try { localStorage.removeItem(SIDEBAR_USER_CACHE_KEY); } catch (e) {}
}

function pageAccessAllowed(user, activePage, options = {}) {
  if (!user || user.must_change_password) return false;
  const allowedViewIds = [activePage, ...(options.anyViewIds || [])].filter(Boolean);
  const hasViewAccess = allowedViewIds.some((viewId) => canViewPage(user, viewId));
  if (activePage && activePage !== "passwordSetup" && !hasViewAccess) return false;
  if (options.requireAdmin && !isAdminUser(user)) return false;
  if (options.requireSuperUser && !user?.is_super_user) return false;
  if (options.requirePlanningView && !canViewPage(user, activePage || "schedule")) return false;
  if (options.requireEditor && !canEditPage(user, activePage)) return false;
  if (options.requireAllocationTools && !canViewPage(user, activePage)) return false;
  if (options.requireAllocationProcess && !canViewPage(user, activePage)) return false;
  return true;
}

function cachedUserCanRenderPage(user, activePage, options = {}) {
  return pageAccessAllowed(user, activePage, options);
}


function finishSidebarInitialRender(app) {
  if (!app?.classList.contains("sidebar-initializing")) return;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => app.classList.remove("sidebar-initializing"));
  });
}

function renderSidebar(user, activePage) {
  let sidebar = document.querySelector(".sidebar");
  let app = document.querySelector(".app");
  if (!sidebar) {
    const body = document.body;
    const topbar = document.querySelector(".topbar");
    if (topbar) topbar.remove();

    const main = document.createElement("main");
    main.className = "main";
    Array.from(body.children).forEach((el) => {
      if (el.tagName === "SCRIPT") return;
      main.appendChild(el);
    });

    sidebar = document.createElement("aside");
    sidebar.className = "sidebar";

    app = document.createElement("div");
    app.className = "app";
    app.classList.add("sidebar-initializing");
    app.appendChild(sidebar);
    app.appendChild(main);
    body.insertBefore(app, body.firstChild);
  }

  const navHtml = renderSidebarNav(user, activePage);
  const editButton = canEditPage(user, "sidebarLayout")
    ? `
      <button class="sidebar-edit" id="sidebar-edit" type="button" title="Redigera meny" aria-label="Redigera meny">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 20h9"></path>
          <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z"></path>
        </svg>
      </button>
    `
    : "";
  const uploadUtility = renderAllocationUploadUtility(user, activePage);
  const logUtility = renderLogUtility();
  const assistantUtility = renderAssistantUtility();
  const zoomControls = renderAppZoomControls();
  const userName = user?.display_name || user?.username || "";
  const roleLabel = sidebarRoleLabel(user);

  sidebar.innerHTML = `
    <div class="sidebar-top-row">
      <button class="sidebar-toggle" id="sidebar-toggle" title="Visa/dölj meny" aria-label="Visa/dölj meny">
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round">
          <path d="M4 6h14M4 11h14M4 16h14"/>
        </svg>
      </button>
      ${zoomControls}
      ${editButton}
    </div>
    <nav>
      ${navHtml}
    </nav>
    <div class="sidebar-footer">
      <div class="sidebar-utility">
        <button class="area-focus-toggle" id="area-focus-toggle" type="button" title="Områdesfokus" aria-label="Områdesfokus"></button>
        ${assistantUtility}
        ${logUtility}
        ${uploadUtility}
        <button class="theme-toggle" id="theme-toggle" type="button"></button>
      </div>
      <div class="sidebar-bottom">
        <div class="avatar">${initials(user?.display_name || user?.username)}</div>
        <div>
          <div class="who">${escapeHtml(userName)}</div>
          ${roleLabel ? `<div class="sidebar-role">${escapeHtml(roleLabel)}</div>` : ""}
          <a href="#" class="logout" id="logout-link">Logga ut</a>
        </div>
      </div>
    </div>
  `;

  initAppZoomControls();
  initAreaFocusToggle(user);
  initThemeToggle();
  ensureLogSidebar(app);
  initLogSidebarToggle();
  ensureAssistantChatPanel(app);
  initAssistantChatToggle();
  updateAllocationUploadIndicator();
  document.body.classList.add("sidebar-hydrated");
  initSidebarContextMenus(user, activePage);
  initSidebarProductivityContextMenu(user);
  const allocationUploadLink = document.getElementById("allocation-upload-link");
  if (allocationUploadLink) {
    allocationUploadLink.addEventListener("click", () => clearAllocationUploadNotice());
    allocationUploadLink.addEventListener("contextmenu", openUploadContextMenu);
  }
  const sidebarEdit = document.getElementById("sidebar-edit");
  if (sidebarEdit) {
    sidebarEdit.addEventListener("click", () => openSidebarEditor(user, activePage));
  }

  const logout = document.getElementById("logout-link");
  if (logout) {
    logout.addEventListener("click", async (e) => {
      e.preventDefault();
      await api.post("/api/auth/logout");
      clearAssistantLocalSession();
      clearCachedSidebarUser();
      try {
        sessionStorage.removeItem("flow-demo-tour-handled");
        sessionStorage.removeItem("flow-demo-tour-state");
      } catch (err) {}
      window.location.href = "/login.html";
    });
  }

  // Toggle collapsed state – hamburger fortsätter rotera åt samma håll vid varje klick
  const toggleBtn = document.getElementById("sidebar-toggle");
  app = app || document.querySelector(".app");
  let togglerRotation = 0;
  const svgIcon = toggleBtn?.querySelector("svg");

  const setCollapsed = (collapsed, animateIcon = false) => {
    sidebar.classList.toggle("collapsed", collapsed);
    if (app) app.classList.toggle("sidebar-collapsed", collapsed);
    if (animateIcon && svgIcon) {
      togglerRotation += 90;
      svgIcon.style.transform = `rotate(${togglerRotation}deg)`;
    }
    try { localStorage.setItem("sidebar-collapsed", collapsed ? "1" : "0"); } catch (e) {}
  };

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      setCollapsed(!sidebar.classList.contains("collapsed"), true);
    });
  }

  try {
    if (localStorage.getItem("sidebar-collapsed") === "1") {
      // Återställ utan animation – håll ikonens rotation i synk med läget
      togglerRotation = 90;
      if (svgIcon) svgIcon.style.transform = `rotate(${togglerRotation}deg)`;
      setCollapsed(true, false);
    }
  } catch (e) {}
  finishSidebarInitialRender(app);
}

// Bakåtkompatibilitet
function renderTopbar(user, activePage) {
  renderSidebar(user, activePage);
}

// === Demo-läge: banner + valbar guidad rundtur ===

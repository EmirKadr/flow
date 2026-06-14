function setupSyncedHorizontalScroll(target) {
  const element = typeof target === "string" ? document.querySelector(target) : target;
  const wrap = element?.classList?.contains("table-wrap") ? element : element?.closest?.(".table-wrap");
  if (!wrap?.parentNode) return null;

  let top = wrap.previousElementSibling;
  if (!top || !top.classList?.contains("synced-scrollbar-top")) {
    top = document.createElement("div");
    top.className = "synced-scrollbar-top";
    top.setAttribute("aria-hidden", "true");
    const spacer = document.createElement("div");
    spacer.className = "synced-scrollbar-spacer";
    top.appendChild(spacer);
    wrap.parentNode.insertBefore(top, wrap);
  }

  const spacer = top.querySelector(".synced-scrollbar-spacer") || top.appendChild(document.createElement("div"));
  spacer.classList.add("synced-scrollbar-spacer");

  if (wrap.__flowSyncedHorizontalScroll) {
    wrap.__flowSyncedHorizontalScroll.update();
    return top;
  }

  let syncing = false;
  const update = () => {
    const scrollWidth = wrap.scrollWidth || 0;
    spacer.style.width = `${scrollWidth}px`;
    top.hidden = scrollWidth <= wrap.clientWidth + 1;
    if (!top.hidden) top.scrollLeft = wrap.scrollLeft;
  };
  const syncFromTop = () => {
    if (syncing) return;
    syncing = true;
    wrap.scrollLeft = top.scrollLeft;
    syncing = false;
  };
  const syncFromWrap = () => {
    if (syncing) return;
    syncing = true;
    top.scrollLeft = wrap.scrollLeft;
    syncing = false;
  };

  top.addEventListener("scroll", syncFromTop, { passive: true });
  wrap.addEventListener("scroll", syncFromWrap, { passive: true });

  let observer = null;
  if ("ResizeObserver" in window) {
    observer = new ResizeObserver(update);
    observer.observe(wrap);
    Array.from(wrap.children || []).forEach((child) => observer.observe(child));
  } else {
    window.addEventListener("resize", update);
  }

  wrap.__flowSyncedHorizontalScroll = { update, observer };
  requestAnimationFrame(update);
  return top;
}

async function loadCurrentUser() {
  try {
    return await api.get("/api/auth/me");
  } catch (e) {
    return null;
  }
}

function queueToast(message, kind = "info", durationMs = 4000) {
  sessionStorage.setItem("queued-toast", JSON.stringify({ message, kind, durationMs }));
}

function toastLogTitle(kind) {
  if (kind === "success") return "Klart";
  if (kind === "error") return "Fel";
  if (kind === "warn") return "Varning";
  return "Info";
}

function showToast(message, kind = "info", durationMs = 4000, options = {}) {
  const el = document.createElement("div");
  el.className = "toast" + (kind ? " " + kind : "");
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), durationMs);
  if (options.log !== false) {
    appendAppLog(message, kind || "info", options.logTitle || toastLogTitle(kind));
  }
}

function flushQueuedToast() {
  const raw = sessionStorage.getItem("queued-toast");
  if (!raw) return;
  sessionStorage.removeItem("queued-toast");
  try {
    const toast = JSON.parse(raw);
    showToast(toast.message, toast.kind, toast.durationMs);
  } catch (e) {
    // Ignorera trasig sessionStorage-data.
  }
}

function initials(name) {
  return String(name || "?")
    .split(/\s+/).filter(Boolean).slice(0, 2)
    .map((part) => part[0].toUpperCase()).join("");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function renderAssistantInlineMarkdown(value) {
  let html = escapeHtml(value);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return html;
}

function isMarkdownTableLine(line) {
  return /^\s*\|.*\|\s*$/.test(line);
}

function isMarkdownTableSeparator(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function markdownTableCells(line) {
  return String(line || "")
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderAssistantMarkdownTable(lines) {
  const rows = lines
    .filter((line) => !isMarkdownTableSeparator(line))
    .map(markdownTableCells)
    .filter((row) => row.length);
  if (!rows.length) return "";
  const header = rows[0];
  const body = rows.slice(1);
  return `
    <div class="assistant-chat-table-wrap">
      <table class="assistant-chat-table">
        <thead>
          <tr>${header.map((cell) => `<th>${renderAssistantInlineMarkdown(cell)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${body.map((row) => `
            <tr>${row.map((cell) => `<td>${renderAssistantInlineMarkdown(cell)}</td>`).join("")}</tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderAssistantMarkdown(content) {
  const lines = String(content || "").replace(/\r\n/g, "\n").trim().split("\n");
  const html = [];
  let listType = "";

  const closeList = () => {
    if (!listType) return;
    html.push(`</${listType}>`);
    listType = "";
  };

  const openList = (type) => {
    if (listType === type) return;
    closeList();
    listType = type;
    html.push(`<${type}>`);
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      continue;
    }

    if (isMarkdownTableLine(line)) {
      const tableLines = [];
      while (index < lines.length && isMarkdownTableLine(lines[index])) {
        tableLines.push(lines[index]);
        index += 1;
      }
      index -= 1;
      closeList();
      html.push(renderAssistantMarkdownTable(tableLines));
      continue;
    }

    const heading = trimmed.match(/^#{1,4}\s+(.+)$/);
    if (heading) {
      closeList();
      html.push(`<p class="assistant-chat-heading">${renderAssistantInlineMarkdown(heading[1])}</p>`);
      continue;
    }

    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      openList("ul");
      html.push(`<li>${renderAssistantInlineMarkdown(bullet[1])}</li>`);
      continue;
    }

    const numbered = trimmed.match(/^\d+\.\s+(.+)$/);
    if (numbered) {
      openList("ol");
      html.push(`<li>${renderAssistantInlineMarkdown(numbered[1])}</li>`);
      continue;
    }

    closeList();
    html.push(`<p>${renderAssistantInlineMarkdown(trimmed)}</p>`);
  }

  closeList();
  return html.join("");
}


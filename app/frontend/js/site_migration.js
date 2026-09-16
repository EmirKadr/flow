// Also handle cached pages and desktop clients configured with the old origin.
(() => {
  const path = window.location.pathname;
  if (["/d-pak", "/d-pak/", "/dpak-fraga.html"].includes(path)) return;
  const host = window.location.hostname.toLowerCase().replace(/\.$/, "");
  if (!["stigamo.nu", "www.stigamo.nu", "localhost", "127.0.0.1", "[::1]"].includes(host)) return;

  let timer;
  let checking = false;
  let moving = false;

  function moveToNewSite(origin) {
    if (moving) return;
    const target = new URL(origin);
    if (target.protocol !== "https:" || target.origin === window.location.origin) return;
    target.pathname = window.location.pathname;
    target.search = window.location.search;
    target.hash = window.location.hash;
    moving = true;
    const notice = document.createElement("div");
    notice.setAttribute("role", "alert");
    notice.style.cssText = "position:fixed;inset:0;z-index:2147483647;background:#fff;color:#162234;display:grid;place-content:center;padding:24px;font:18px system-ui;gap:16px";
    const heading = document.createElement("strong");
    heading.textContent = "flow har flyttat";
    const link = document.createElement("a");
    link.href = target.href;
    link.textContent = `Fortsätt till ${target.hostname}`;
    notice.append(heading, link);
    document.body.append(notice);
    window.flowLog?.info?.("flow har flyttat. Öppnar den nya adressen.", "Adressbyte");
    window.location.replace(target.href);
  }

  async function checkMigration() {
    if (checking || moving) return;
    checking = true;
    clearTimeout(timer);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch("/api/site-migration", {
        cache: "no-store", credentials: "same-origin", signal: controller.signal,
      });
      if (!response.ok) throw new Error("Migration status unavailable");
      const state = await response.json();
      if (state.active) {
        moveToNewSite(state.target_origin);
      }
    } catch (_error) {
      // A transient network failure must not permanently disable the cutover.
      timer = setTimeout(checkMigration, 30000);
    } finally {
      clearTimeout(timeout);
      checking = false;
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) checkMigration();
  });
  window.addEventListener("pageshow", checkMigration);
  checkMigration();
})();

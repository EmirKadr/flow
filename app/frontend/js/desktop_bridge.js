(function () {
  const state = {
    ready: false,
    bridge: null,
    waiters: [],
  };

  function resolveReady() {
    state.ready = true;
    for (const waiter of state.waiters.splice(0)) waiter(state.bridge);
  }

  function desktopTrack(eventType, detail = {}) {
    const send = () => {
      if (typeof window.flowTrack !== "function") return false;
      window.flowTrack(eventType, {
        view_id: window.flowCurrentViewId || "",
        feature: "desktop",
        control_id: detail.control_id || "desktop-shell",
        control_label: detail.control_label || "Windows-app",
        client_surface: "desktop",
        status: detail.status || "ok",
        detail,
      });
      return true;
    };
    if (send()) return;
    window.setTimeout(send, 500);
  }

  function loadWebChannelScript() {
    return new Promise((resolve, reject) => {
      if (typeof window.QWebChannel === "function") {
        resolve();
        return;
      }
      const script = document.createElement("script");
      script.src = "qrc:///qtwebchannel/qwebchannel.js";
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  async function initialize() {
    if (!window.qt?.webChannelTransport) return;
    try {
      await loadWebChannelScript();
      new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
        state.bridge = channel.objects.flowDesktopBridge || null;
        if (state.bridge) {
          window.flowDesktopBridge = state.bridge;
          window.dispatchEvent(new CustomEvent("flow:desktop-ready"));
          resolveReady();
          desktopTrack("desktop_app_ready", { control_id: "desktop-ready", control_label: "Windows-app startad" });
        }
      });
    } catch (_error) {
      state.ready = false;
    }
  }

  window.flowDesktop = {
    isDesktop: () => Boolean(state.bridge || window.qt?.webChannelTransport),
    ready: () => {
      if (state.bridge) return Promise.resolve(state.bridge);
      return new Promise((resolve) => state.waiters.push(resolve));
    },
    pickFiles: async ({ accept = "", multiple = true } = {}) => {
      const bridge = await window.flowDesktop.ready();
      return await new Promise((resolve) => {
        bridge.chooseFiles(String(accept || ""), Boolean(multiple), (entries) => {
          const safeEntries = Array.isArray(entries) ? entries : [];
          desktopTrack("desktop_file_select", {
            control_id: "desktop-file-picker",
            control_label: "Valj lokala filer",
            file_count: safeEntries.length,
            file_types: [...new Set(safeEntries.map((entry) => String(entry.fileType || entry.file_type || "").slice(0, 80)).filter(Boolean))],
            accept: String(accept || "").slice(0, 120),
            multiple: Boolean(multiple),
          });
          resolve(safeEntries);
        });
      });
    },
  };

  initialize();
})();

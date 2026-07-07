// @ts-check
// Buggrapportering: 30 sekunders DOM-inspelning (rrweb) från Bugg-knappen i
// sidebar-footern. Laddas lazy av sidebar.js först när användaren klickar —
// vanliga sidladdningar betalar aldrig för rrweb-bundeln.
//
// Integritet: inspelningen visar bara det användaren själv såg i appen,
// lösenordsfält maskas alltid, och ingen inspelning startar utan OK i popupen.
(function () {
  const RECORD_SECONDS = 30;
  const VENDOR_SRC = "/js/vendor/rrweb.min.js";
  // Sidbytesräddning: Flow är en multi-page-app, så ett sidbyte kastar
  // inspelningsläget i minnet. Vid pagehide sparas det som hunnit spelas in
  // här (sessionStorage = per flik) och skickas av nästa sidladdning.
  // sendBeacon/keepalive går inte: 64 kB-taket är mindre än en inspelning.
  const SALVAGE_KEY = "flow-bug-report-salvage";
  const SALVAGE_MAX_AGE_MS = 5 * 60 * 1000;

  /** @type {{ stop: null | (() => void), events: any[], consoleErrors: string[], jsErrors: string[], timer: number | null, deadline: number, note: string, restoreConsole: null | (() => void) }} */
  const state = {
    stop: null,
    events: [],
    consoleErrors: [],
    jsErrors: [],
    timer: null,
    deadline: 0,
    note: "",
    restoreConsole: null,
  };

  function loadVendor() {
    return new Promise((resolve, reject) => {
      if (window.rrweb && typeof window.rrweb.record === "function") {
        resolve(undefined);
        return;
      }
      const script = document.createElement("script");
      script.src = VENDOR_SRC;
      script.onload = () => resolve(undefined);
      script.onerror = () => reject(new Error("Kunde inte ladda inspelningsmodulen."));
      document.head.appendChild(script);
    });
  }

  function closeModal() {
    document.getElementById("bug-report-backdrop")?.remove();
  }

  function openConsentModal() {
    closeModal();
    const backdrop = document.createElement("div");
    backdrop.id = "bug-report-backdrop";
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal bug-report-modal" role="dialog" aria-modal="true" aria-labelledby="bug-report-title">
        <h3 id="bug-report-title">Rapportera bugg</h3>
        <p>
          När du klickar på <strong>Starta inspelning</strong> spelas de kommande
          ${RECORD_SECONDS} sekunderna av vad du ser och gör i appen in och skickas
          till administratören tillsammans med tekniska fel. Återskapa buggen under
          inspelningen. Lösenord maskas alltid och inget utanför appen spelas in.
        </p>
        <label for="bug-report-note">Vad hände? (valfritt)</label>
        <textarea id="bug-report-note" rows="3" maxlength="2000"
          placeholder="T.ex. Jag klickade på Spara och inget hände."></textarea>
        <div class="modal-actions">
          <button type="button" class="secondary" id="bug-report-cancel">Avbryt</button>
          <button type="button" id="bug-report-start">Starta inspelning (${RECORD_SECONDS} s)</button>
        </div>
      </div>
    `;
    document.body.appendChild(backdrop);
    // Dialogregeln: modalen har textarea — ingen backdrop-klick-stängning.
    document.getElementById("bug-report-cancel")?.addEventListener("click", closeModal);
    document.getElementById("bug-report-start")?.addEventListener("click", () => {
      const note = document.getElementById("bug-report-note");
      state.note = note instanceof HTMLTextAreaElement ? note.value.trim() : "";
      closeModal();
      void startRecording();
    });
    document.getElementById("bug-report-note")?.focus();
  }

  function hookErrorCapture() {
    const originalError = console.error;
    console.error = (...args) => {
      try {
        state.consoleErrors.push(args.map((arg) => String(arg)).join(" ").slice(0, 500));
        if (state.consoleErrors.length > 20) state.consoleErrors.shift();
      } catch (_ignored) { /* fångst får aldrig störa loggningen */ }
      originalError.apply(console, args);
    };
    const onError = (/** @type {ErrorEvent} */ event) => {
      state.jsErrors.push(String(event.message || "okänt fel").slice(0, 500));
    };
    const onRejection = (/** @type {PromiseRejectionEvent} */ event) => {
      state.jsErrors.push(`unhandledrejection: ${String(event.reason || "")}`.slice(0, 500));
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    state.restoreConsole = () => {
      console.error = originalError;
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }

  function renderIndicator() {
    removeIndicator();
    const pill = document.createElement("div");
    pill.id = "bug-report-indicator";
    pill.className = "bug-report-indicator";
    pill.innerHTML = `
      <span class="bug-report-dot" aria-hidden="true"></span>
      <span id="bug-report-countdown">Spelar in bugg… ${RECORD_SECONDS} s</span>
      <button type="button" id="bug-report-stop">Stoppa och skicka</button>
    `;
    document.body.appendChild(pill);
    document.getElementById("bug-report-stop")?.addEventListener("click", () => {
      void finishRecording();
    });
  }

  function removeIndicator() {
    document.getElementById("bug-report-indicator")?.remove();
  }

  function updateCountdown() {
    const left = Math.max(0, Math.ceil((state.deadline - Date.now()) / 1000));
    const label = document.getElementById("bug-report-countdown");
    if (label) label.textContent = `Spelar in bugg… ${left} s`;
    if (left <= 0) {
      void finishRecording();
    }
  }

  async function startRecording() {
    if (state.stop) return;
    try {
      await loadVendor();
    } catch (error) {
      window.showToast?.(error instanceof Error ? error.message : "Kunde inte starta inspelningen.", "error", 7000);
      return;
    }
    state.events = [];
    state.consoleErrors = [];
    state.jsErrors = [];
    hookErrorCapture();
    const rrweb = window.rrweb;
    state.stop = rrweb.record({
      emit: (/** @type {any} */ event) => state.events.push(event),
      maskInputOptions: { password: true },
    }) || null;
    if (!state.stop) {
      state.restoreConsole?.();
      state.restoreConsole = null;
      window.showToast?.("Inspelningen kunde inte starta.", "error", 7000);
      return;
    }
    state.deadline = Date.now() + RECORD_SECONDS * 1000;
    renderIndicator();
    state.timer = window.setInterval(updateCountdown, 250);
    window.flowTrack?.("bug_report_recording_started", {
      control_id: "bug-report-toggle",
      control_label: "Rapportera bugg",
    });
  }

  function buildPayload(note = state.note) {
    return {
      events_json: JSON.stringify(state.events),
      note: note || null,
      view_id: document.body?.dataset.activePage || window.flowActivePage || null,
      page_path: window.location.pathname,
      context: {
        console_errors: state.consoleErrors,
        js_errors: state.jsErrors.slice(0, 20),
        user_agent: String(navigator.userAgent || "").slice(0, 200),
        viewport: `${window.innerWidth}x${window.innerHeight}`,
      },
    };
  }

  function stopRecordingSilently() {
    if (!state.stop) return false;
    const stop = state.stop;
    state.stop = null;
    if (state.timer !== null) {
      window.clearInterval(state.timer);
      state.timer = null;
    }
    removeIndicator();
    try {
      stop();
    } catch (_ignored) { /* rrweb-stopp får inte blockera inskicket */ }
    state.restoreConsole?.();
    state.restoreConsole = null;
    return true;
  }

  async function finishRecording() {
    if (!stopRecordingSilently()) return;

    if (!state.events.length) {
      window.showToast?.("Ingen inspelning att skicka.", "warn", 4000);
      return;
    }
    const payload = buildPayload();
    state.events = [];
    try {
      await window.api.post("/api/bug-reports", payload);
      window.showToast?.("Tack! Buggrapporten är skickad till administratören.", "success", 5000);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Buggrapporten kunde inte skickas.";
      window.showToast?.(message, "error", 8000);
    }
  }

  // Sidbyte under inspelning: spara det inspelade så nästa sidladdning kan
  // skicka det i stället för att allt tyst försvinner med sidan.
  window.addEventListener("pagehide", () => {
    if (!state.stop) return;
    const note = state.note;
    stopRecordingSilently();
    if (!state.events.length) return;
    const marker = "(inspelningen avbröts av sidbyte)";
    const payload = buildPayload(note ? `${note} ${marker}` : marker);
    state.events = [];
    try {
      sessionStorage.setItem(SALVAGE_KEY, JSON.stringify({ savedAt: Date.now(), payload }));
    } catch (_ignored) { /* kvotfullt: räddningen är best effort */ }
  });

  // Varning vid navigering under inspelning: länkar fångas i capture-fasen
  // så användaren väljer aktivt mellan att stanna kvar eller byta sida (och
  // få det inspelade skickat via räddningen). JS-navigering utan länk täcks
  // ändå av pagehide-räddningen ovan.
  function openNavigationWarningModal(targetHref) {
    document.getElementById("bug-report-nav-backdrop")?.remove();
    const backdrop = document.createElement("div");
    backdrop.id = "bug-report-nav-backdrop";
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="bug-report-nav-title">
        <h3 id="bug-report-nav-title">Inspelning pågår</h3>
        <p>
          Sidbytet stoppar inspelningen. Det som hunnit spelas in skickas som
          buggrapport direkt efter sidbytet.
        </p>
        <div class="modal-actions">
          <button type="button" class="secondary" id="bug-report-nav-cancel">Stanna kvar</button>
          <button type="button" id="bug-report-nav-continue">Byt sida och skicka</button>
        </div>
      </div>
    `;
    document.body.appendChild(backdrop);
    document.getElementById("bug-report-nav-cancel")?.addEventListener("click", () => backdrop.remove());
    document.getElementById("bug-report-nav-continue")?.addEventListener("click", () => {
      backdrop.remove();
      window.location.href = targetHref;
    });
  }

  document.addEventListener(
    "click",
    (event) => {
      if (!state.stop) return;
      const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(anchor instanceof HTMLAnchorElement)) return;
      const href = anchor.getAttribute("href") || "";
      if (!href || href.startsWith("#")) return;
      event.preventDefault();
      event.stopPropagation();
      openNavigationWarningModal(anchor.href);
    },
    true
  );

  // Skickar en räddad inspelning från förra sidan. Anropas vid sidladdning
  // (sidebar.js eagerladdar modulen när räddningsflaggan finns).
  async function sendSalvagedReport() {
    let saved = null;
    try {
      const raw = sessionStorage.getItem(SALVAGE_KEY);
      sessionStorage.removeItem(SALVAGE_KEY);
      saved = raw ? JSON.parse(raw) : null;
    } catch (_ignored) {
      return;
    }
    if (!saved?.payload?.events_json) return;
    if (!Number.isFinite(saved.savedAt) || Date.now() - saved.savedAt > SALVAGE_MAX_AGE_MS) return;
    try {
      await window.api.post("/api/bug-reports", saved.payload);
      window.showToast?.("Buggrapporten skickades – inspelningen avbröts av sidbytet.", "success", 6000);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Den avbrutna buggrapporten kunde inte skickas.";
      window.showToast?.(message, "error", 8000);
    }
  }

  window.flowBugReport = {
    open: openConsentModal,
    isRecording: () => Boolean(state.stop),
    sendSalvaged: sendSalvagedReport,
  };

  // Modulen laddas eagert av sidebar.js när en räddad inspelning väntar.
  void sendSalvagedReport();
})();

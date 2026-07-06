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

  async function finishRecording() {
    if (!state.stop) return;
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

    if (!state.events.length) {
      window.showToast?.("Ingen inspelning att skicka.", "warn", 4000);
      return;
    }
    const payload = {
      events_json: JSON.stringify(state.events),
      note: state.note || null,
      view_id: document.body?.dataset.activePage || window.flowActivePage || null,
      page_path: window.location.pathname,
      context: {
        console_errors: state.consoleErrors,
        js_errors: state.jsErrors.slice(0, 20),
        user_agent: String(navigator.userAgent || "").slice(0, 200),
        viewport: `${window.innerWidth}x${window.innerHeight}`,
      },
    };
    state.events = [];
    try {
      await window.api.post("/api/bug-reports", payload);
      window.showToast?.("Tack! Buggrapporten är skickad till administratören.", "success", 5000);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Buggrapporten kunde inte skickas.";
      window.showToast?.(message, "error", 8000);
    }
  }

  window.flowBugReport = {
    open: openConsentModal,
    isRecording: () => Boolean(state.stop),
  };
})();

// @ts-check
// Buggrapportering: 30 sekunders DOM-inspelning (rrweb) från Bugg-knappen i
// sidebar-footern. Laddas lazy av sidebar.js först när användaren klickar —
// vanliga sidladdningar betalar aldrig för rrweb-bundeln.
//
// Inspelningen överlever sidbyten (2026-07-07): Flow är en multi-page-app,
// så vid pagehide sparas sidans segment i sessionStorage och nästa sida
// återupptar inspelningen med en ny full snapshot (sidebar.js eagerladdar
// modulen när en session väntar). Uppspelningen får ett "scenbyte" per sida
// och allt skickas som EN rapport vid stopp/deadline. sendBeacon/keepalive
// valdes bort: deras 64 kB-tak är mindre än en inspelning.
//
// Integritet: inspelningen visar bara det användaren själv såg i appen,
// lösenordsfält maskas alltid, och ingen inspelning startar utan OK i popupen.
(function () {
  if (window.flowBugReport?.__moduleLoaded) return;
  const RECORD_SECONDS = 30;
  const VENDOR_SRC = "/js/vendor/rrweb.min.js";
  const SESSION_KEY = "flow-bug-report-session";
  const SESSION_MAX_AGE_MS = 5 * 60 * 1000; // övergiven session förfaller

  /** @type {{ stop: null | (() => void), events: any[], segments: any[][], consoleErrors: string[], jsErrors: string[], timer: number | null, deadline: number, note: string, viewId: string | null, pagePath: string | null, restoreConsole: null | (() => void) }} */
  const state = {
    stop: null,
    events: [],
    segments: [],
    consoleErrors: [],
    jsErrors: [],
    timer: null,
    deadline: 0,
    note: "",
    viewId: null,
    pagePath: null,
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
          inspelningen — den fortsätter även om du byter sida i appen. Lösenord
          maskas alltid och inget utanför appen spelas in.
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

  // Startar rrweb och indikatorn för aktuellt state — delas av nystart och
  // återupptagning efter sidbyte.
  async function beginCapture() {
    await loadVendor();
    state.events = [];
    hookErrorCapture();
    const rrweb = window.rrweb;
    state.stop = rrweb.record({
      emit: (/** @type {any} */ event) => state.events.push(event),
      maskInputOptions: { password: true },
    }) || null;
    if (!state.stop) {
      state.restoreConsole?.();
      state.restoreConsole = null;
      throw new Error("Inspelningen kunde inte starta.");
    }
    renderIndicator();
    state.timer = window.setInterval(updateCountdown, 250);
    updateCountdown();
  }

  async function startRecording() {
    if (state.stop) return;
    state.segments = [];
    state.consoleErrors = [];
    state.jsErrors = [];
    state.viewId = document.body?.dataset.activePage || window.flowActivePage || null;
    state.pagePath = window.location.pathname;
    state.deadline = Date.now() + RECORD_SECONDS * 1000;
    try {
      await beginCapture();
    } catch (error) {
      window.showToast?.(error instanceof Error ? error.message : "Kunde inte starta inspelningen.", "error", 7000);
      return;
    }
    window.flowTrack?.("bug_report_recording_started", {
      control_id: "bug-report-toggle",
      control_label: "Rapportera bugg",
    });
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

  function combinedEvents() {
    return [...state.segments.flat(), ...state.events];
  }

  function buildPayload(events) {
    return {
      events_json: JSON.stringify(events),
      note: state.note || null,
      view_id: state.viewId,
      page_path: state.pagePath,
      context: {
        console_errors: state.consoleErrors,
        js_errors: state.jsErrors.slice(0, 20),
        flow_trace_context: window.flowLastTraceContext || null,
        user_agent: String(navigator.userAgent || "").slice(0, 200),
        viewport: `${window.innerWidth}x${window.innerHeight}`,
      },
    };
  }

  async function submitReport(events) {
    const payload = buildPayload(events);
    state.segments = [];
    state.events = [];
    try {
      await window.api.post("/api/bug-reports", payload);
      window.showToast?.("Tack! Buggrapporten är skickad till administratören.", "success", 5000);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Buggrapporten kunde inte skickas.";
      window.showToast?.(message, "error", 8000);
    }
  }

  async function finishRecording() {
    if (!stopRecordingSilently()) return;
    const events = combinedEvents();
    if (!events.length) {
      window.showToast?.("Ingen inspelning att skicka.", "warn", 4000);
      return;
    }
    await submitReport(events);
  }

  // Sidbyte under inspelning: spara sessionen så nästa sidladdning kan
  // återuppta inspelningen (eller skicka den om tiden hann gå ut).
  window.addEventListener("pagehide", () => {
    if (!state.stop) return;
    stopRecordingSilently();
    const session = {
      savedAt: Date.now(),
      deadline: state.deadline,
      note: state.note,
      viewId: state.viewId,
      pagePath: state.pagePath,
      segments: state.events.length ? [...state.segments, state.events] : state.segments,
      consoleErrors: state.consoleErrors,
      jsErrors: state.jsErrors,
    };
    state.segments = [];
    state.events = [];
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } catch (_ignored) { /* kvotfullt: fortsättningen är best effort */ }
  });

  function takeStoredSession() {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      sessionStorage.removeItem(SESSION_KEY);
      const session = raw ? JSON.parse(raw) : null;
      if (!session || !Array.isArray(session.segments)) return null;
      if (!Number.isFinite(session.savedAt) || Date.now() - session.savedAt > SESSION_MAX_AGE_MS) return null;
      return session;
    } catch (_ignored) {
      return null;
    }
  }

  function restoreSessionState(session) {
    state.segments = session.segments.filter((segment) => Array.isArray(segment) && segment.length);
    state.consoleErrors = Array.isArray(session.consoleErrors) ? session.consoleErrors : [];
    state.jsErrors = Array.isArray(session.jsErrors) ? session.jsErrors : [];
    state.note = typeof session.note === "string" ? session.note : "";
    state.viewId = session.viewId ?? null;
    state.pagePath = session.pagePath ?? null;
    state.deadline = Number(session.deadline) || 0;
  }

  // Återupptar en inspelning som avbröts av ett sidbyte. Nya sidan får en
  // egen full snapshot — uppspelningen visar det som ett scenbyte.
  async function resumeStoredSession() {
    const session = takeStoredSession();
    if (!session) return;
    restoreSessionState(session);
    if (Date.now() < state.deadline) {
      try {
        await beginCapture();
        return;
      } catch (_ignored) {
        // rrweb gick inte att ladda på nya sidan — skicka det som finns.
      }
    }
    const events = combinedEvents();
    if (events.length) await submitReport(events);
  }

  window.flowBugReport = {
    __moduleLoaded: true,
    open: openConsentModal,
    isRecording: () => Boolean(state.stop),
  };

  // Modulen laddas eagert av sidebar.js när en inspelningssession väntar.
  void resumeStoredSession();
})();

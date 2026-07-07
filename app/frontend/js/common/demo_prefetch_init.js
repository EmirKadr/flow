// @ts-check
const DEMO_TOUR_HANDLED_KEY = "flow-demo-tour-handled";
const DEMO_TOUR_STATE_KEY = "flow-demo-tour-state";

const DEMO_TOUR_DESCRIPTIONS = {
  schedule:
    "Bemanning är hjärtat i flow — här planerar du vem som gör vad timme för timme.<br><br>"
    + "<strong>Vänsterklick</strong> på en cell fokuserar den så du kan välja aktivitet i listan som dyker upp.<br>"
    + "<strong>Högerklick</strong> öppnar samma aktivitetsval direkt i en kontextmeny.<br>"
    + "<strong>Dubbelklick</strong> delar timmen i två halvor om du behöver två aktiviteter inom samma timme.<br>"
    + "<strong>Dra</strong> över flera celler för att fylla dem med samma aktivitet på en gång.<br>"
    + "Knapparna högst upp: <strong>Föregående/Nästa dag</strong>, <strong>Kopiera dag</strong> (klona en dag till en annan), <strong>Rensa dag</strong>, <strong>Närvarande</strong> för utskriftslista samt <strong>Ångra</strong> och <strong>Gör om</strong> för dina senaste ändringar.<br>"
    + "Drag i personnamnen till vänster för att ändra sorteringsordningen (om rollen tillåter det).",
  overview:
    "Översikt visar bemanningen i ett kondenserat format — bra för att se helbilden över veckan eller månaden.<br><br>"
    + "Växla mellan <strong>vecka</strong> och <strong>månad</strong> högst upp.<br>"
    + "<strong>Vänsterklick</strong> på en dag öppnar aktivitetsval för heldagen.<br>"
    + "<strong>Dra</strong> över flera dagar för att sätta samma heldagsaktivitet snabbt.<br>"
    + "<strong>Närvarande</strong> skriver ut vald dags bemannade personer och <strong>Ångra/Gör om</strong> fungerar som i Bemanning.",
  productivity:
    "Produktivitet visar den globala produktivitetsöversikten som ett fokuserbart träd.<br><br>"
    + "Välj <strong>dag</strong>, <strong>vecka</strong>, <strong>månad</strong> eller <strong>år</strong> högst upp.<br>"
    + "Klicka verksamhet, område, aktivitet eller person för att gå djupare i hierarkin.<br>"
    + "<strong>Helbild</strong> tar dig tillbaka till roten och <strong>Exportera flowchart</strong> låter dig välja nivåer innan SVG-filen laddas ner.",
  dataFetch:
    "Hämta data låter dig ladda ner valfri vy från det externa lagersystemet, filtrera och exportera till Excel.<br><br>"
    + "Välj <strong>vy</strong> i listan till vänster — sökrutan hjälper dig hitta rätt.<br>"
    + "Kryssa i de <strong>kolumner</strong> du vill ha med.<br>"
    + "Lägg in <strong>filter</strong> per kolumn för att begränsa raderna.<br>"
    + "Klicka <strong>Hämta</strong> för att förhandsgranska och <strong>Exportera till Excel</strong> för att ladda ner.",
  allocationProcess:
    "Bearbeta hjälper dig planera artikelplacering och köra de stora flödena i lagret.<br><br>"
    + "Knapparna under varje rubrik kör delflödena — Ordersaldo, LYX, Påfyllnadsprio, Allokering osv.<br>"
    + "Vilka delflöden som visas per toggle styrs i <strong>Inställningar</strong> under Bearbeta-fliken.<br>"
    + "<strong>Vänsterklick</strong> kör flödet med dina valda filer.<br>"
    + "Resultat visas i en tabell — klicka på cellerna för att <strong>kopiera</strong> värden, och använd <strong>Exportera Excel</strong> för att spara resultatet.",
  allocationSplit:
    "Dela är verktyget för när du har en <strong>lång lista värden</strong> i en kolumn och behöver dela upp dem i flera mindre delar.<br><br>"
    + "Vanligt exempel: ASK klagar att du klistrat in för många värden samtidigt. Då tar du värdena, klistrar in dem här och Dela ger dig dem uppdelade så att du kan klistra in en bit i taget.<br><br>"
    + "<strong>Klistra in</strong> värdena i textrutan (ett per rad) eller ladda upp en textfil.<br>"
    + "Sätt <strong>Antal per kolumn</strong> (standard 2000).<br>"
    + "Klicka <strong>Dela värden</strong> för att få resultatet uppdelat i kolumner som du kan kopiera en åt gången.",
  persons:
    "Personer är registret över alla som ska kunna bemannas.<br><br>"
    + "<strong>Ny person</strong> öppnar modal för att lägga till en person.<br>"
    + "<strong>Flera nya personer</strong> öppnar tabellmodal för bulk-skapande.<br>"
    + "<strong>Importera Excel</strong> låter dig ladda upp en mall.<br>"
    + "<strong>Vänsterklick</strong> i en cell för att redigera namn, hemområde eller huvudaktivitet inline.<br>"
    + "<strong>Schema</strong>-knappen öppnar veckomallen (vilka timmar personen jobbar).<br>"
    + "<strong>Ta bort</strong> raderar personen permanent (kräver bekräftelse).",
  activities:
    "Aktiviteter definierar vad personer kan tilldelas: plock, lots, VAS osv — med färg, kategori, arbetstyp och summering.<br><br>"
    + "<strong>Ny aktivitet</strong> skapar en aktivitet med kod, etikett, område, arbetstyp, färg och sortering.<br>"
    + "<strong>Vänsterklick</strong> på en rad för att redigera inline.<br>"
    + "<strong>Summeras som</strong> låter dig gruppera flera koder under en huvudaktivitet i rapporter.<br>"
    + "Färgen syns sedan direkt i Bemanningens celler.",
  analytics:
    "Historik visar audit-loggen och statistik över alla ändringar.<br><br>"
    + "Tre lägen i toppen: <strong>Användarhistorik</strong> (vem ändrade vad), <strong>Analys</strong> (sammanställningar) och <strong>Felkoder</strong> (API-fel).<br>"
    + "<strong>Filter</strong>-fält per kolumn för att hitta specifika händelser.<br>"
    + "Klicka på en rad för att <strong>se gamla och nya värden</strong> sida vid sida.",
  users:
    "Användarvyn är där admin skapar konton och sätter roller.<br><br>"
    + "<strong>Ny användare</strong> öppnar modal för konto + roll + område.<br>"
    + "<strong>Flera nya användare</strong> för bulk-skapande med en roll per rad.<br>"
    + "Rollmatrisen <strong>Vybehörigheter</strong> (Ingen/Visa/Redigera per vy) ligger under <strong>Inställningar</strong>.<br>"
    + "<strong>Redigera</strong> ändrar enskilt konto. <strong>Ta bort</strong> raderar det.<br>"
    + "Checkboxen <strong>Lås bemanningsceller</strong> styr om arbetsledare kan ändra varandras celler.",
  businesses:
    "Verksamheter är Super Users översikt över Stigamo, R3 och deras områden.<br><br>"
    + "<strong>Ny verksamhet</strong> + <strong>Redigera</strong> för att hantera verksamhetskoder/namn.<br>"
    + "Under varje verksamhet listas dess områden med egna <strong>Nytt område</strong>, <strong>Redigera</strong> och <strong>Ta bort</strong>-knappar.",
};

function ensureDemoBanner() {
  if (document.getElementById("demo-mode-banner")) return;
  const banner = document.createElement("div");
  banner.id = "demo-mode-banner";
  banner.className = "demo-banner";
  banner.innerHTML = `
    <span class="demo-banner-dot"></span>
    <strong>DEMO-läge</strong>
    <span>Ändringar sparas inte. Allt nollställs när du loggar ut.</span>
  `;
  const body = document.body;
  if (body.firstChild) body.insertBefore(banner, body.firstChild);
  else body.appendChild(banner);
}

function _demoTourSteps(user, activePage) {
  const pageSteps = sidebarPageDefinitions(user, activePage)
    .filter((page) => page.visible && page.sidebar !== false)
    .map((page) => ({
      view_id: page.id,
      label: page.label,
      href: page.href,
      body: DEMO_TOUR_DESCRIPTIONS[page.id] || "Använd vyn fritt — alla ändringar sparas bara i demo-sandlådan.",
    }));
  const utilityStep = {
    view_id: "__utility",
    label: "Verktygsraden längst ner i sidebaren",
    href: null,
    highlights: [
      "area-focus-toggle",
      "assistant-toggle",
      "allocation-upload-link",
      "log-toggle",
      "theme-toggle",
    ],
    body:
      "Längst ner i sidebaren finns en rad små verktygsknappar — jag ringar in dem nu så du ser var.<br><br>"
      + "<strong>MG / GG / ∞ (områdesfokus)</strong> — visar och byter vilket lagerområde du tittar på. Klicka för att cykla mellan dina områden eller välj <strong>∞</strong> för att se alla. Filtrerar Bemanning, Översikt, Personer m.fl.<br><br>"
      + "<strong>Pratbubblan (apphjälp)</strong> — öppnar inbyggd LLM-chatt som kan svara på frågor om appen, knappar och flöden. Bra om du undrar var en funktion finns.<br><br>"
      + "<strong>Databas-ikonen (uppladdningar)</strong> — snabb genväg till uppladdningssidan. <em>Högerklick</em> öppnar en meny med olika uppladdningsalternativ.<br><br>"
      + "<strong>Dokument-ikonen (LOG)</strong> — öppnar en logg-panel som visar vad som hänt i appen under sessionen (toasts, fel m.m.). Bra felsökningsverktyg.<br><br>"
      + "<strong>Sol/måne-ikonen</strong> — växlar mellan ljust och mörkt tema. Inställningen sparas per webbläsare.",
  };
  return [...pageSteps, utilityStep];
}

function _clearDemoTourHighlights() {
  document.querySelectorAll(".demo-tour-highlight").forEach((el) => {
    el.classList.remove("demo-tour-highlight");
  });
}

function _applyDemoTourHighlights(ids) {
  _clearDemoTourHighlights();
  if (!Array.isArray(ids) || ids.length === 0) return;
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.classList.add("demo-tour-highlight");
  });
}

function _readDemoTourState() {
  try {
    const raw = sessionStorage.getItem(DEMO_TOUR_STATE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.steps)) return null;
    return parsed;
  } catch (err) {
    return null;
  }
}

function _writeDemoTourState(state) {
  try {
    if (state === null) {
      sessionStorage.removeItem(DEMO_TOUR_STATE_KEY);
    } else {
      sessionStorage.setItem(DEMO_TOUR_STATE_KEY, JSON.stringify(state));
    }
  } catch (err) {}
}

function _markDemoTourHandled() {
  try { sessionStorage.setItem(DEMO_TOUR_HANDLED_KEY, "1"); } catch (err) {}
}

function _renderDemoTourCard(state) {
  const existing = document.getElementById("demo-tour-card");
  if (existing) existing.remove();
  const step = state.steps[state.currentIndex];
  if (!step) {
    _clearDemoTourHighlights();
    return;
  }
  _applyDemoTourHighlights(step.highlights);
  const card = document.createElement("div");
  card.id = "demo-tour-card";
  card.className = "demo-tour-card";
  card.innerHTML = `
    <div class="demo-tour-header">
      <span class="demo-tour-counter">${state.currentIndex + 1} / ${state.steps.length}</span>
      <strong>${escapeForDemo(step.label)}</strong>
    </div>
    <div class="demo-tour-body">${step.body}</div>
    <div class="demo-tour-actions">
      <button class="demo-tour-skip" type="button">Avsluta rundtur</button>
      <button class="demo-tour-next primary" type="button">${state.currentIndex + 1 < state.steps.length ? "Nästa" : "Klar"}</button>
    </div>
  `;
  document.body.appendChild(card);
  card.querySelector(".demo-tour-skip").addEventListener("click", () => {
    _writeDemoTourState(null);
    _clearDemoTourHighlights();
    card.remove();
  });
  card.querySelector(".demo-tour-next").addEventListener("click", () => {
    const next = state.currentIndex + 1;
    if (next >= state.steps.length) {
      _writeDemoTourState(null);
      _clearDemoTourHighlights();
      card.remove();
      showToast("Rundtur klar. Utforska gärna vyerna fritt.", "success", 4000);
      return;
    }
    const nextStep = state.steps[next];
    _writeDemoTourState({ steps: state.steps, currentIndex: next });
    card.remove();
    _clearDemoTourHighlights();
    if (nextStep.href && window.location.pathname !== nextStep.href) {
      window.location.href = nextStep.href;
    } else {
      _renderDemoTourCard({ steps: state.steps, currentIndex: next });
    }
  });
}

function escapeForDemo(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
}

function _showDemoTourPrompt(user, activePage) {
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal demo-tour-welcome">
        <h2>Välkommen till demo-läget av flow</h2>
        <p>Du ser samma data som finns i produktion just nu. Du kan ändra, skapa, ta bort — <strong>inget sparas till den riktiga databasen</strong> och allt nollställs när du loggar ut.</p>
        <p>Vill du se en kort rundtur av vyerna först, med konkreta tips per vy?</p>
        <div class="actions">
          <button id="demo-tour-no" type="button">Nej tack, jag klickar runt själv</button>
          <button id="demo-tour-yes" class="primary" type="button">Ja, visa rundtur</button>
        </div>
      </div>`;
    document.body.appendChild(backdrop);
    const finish = (start) => {
      _markDemoTourHandled();
      backdrop.remove();
      if (start) {
        const steps = _demoTourSteps(user, activePage);
        if (steps.length > 0) {
          const startIndex = Math.max(0, steps.findIndex((step) => step.view_id === activePage));
          _writeDemoTourState({ steps, currentIndex: startIndex });
          _renderDemoTourCard({ steps, currentIndex: startIndex });
        }
      }
      resolve();
    };
    backdrop.querySelector("#demo-tour-yes").addEventListener("click", () => finish(true));
    backdrop.querySelector("#demo-tour-no").addEventListener("click", () => finish(false));
  });
}

async function maybeShowDemoTourPrompt(user, activePage) {
  if (!user?.is_demo) return;
  let state = _readDemoTourState();
  if (state) {
    // Pågående rundtur — visa kort för aktiv sida om den matchar, annars för rätt steg
    const matchIndex = state.steps.findIndex((step) => step.view_id === activePage);
    if (matchIndex >= 0 && matchIndex !== state.currentIndex) {
      state = { steps: state.steps, currentIndex: matchIndex };
      _writeDemoTourState(state);
    }
    _renderDemoTourCard(state);
    return;
  }
  let handled = false;
  try { handled = sessionStorage.getItem(DEMO_TOUR_HANDLED_KEY) === "1"; } catch (err) {}
  if (handled) return;
  await _showDemoTourPrompt(user, activePage);
}

const BACKGROUND_PREFETCH_TTL_MS = 60 * 1000;
const BACKGROUND_PREFETCH_DELAY_MS = 250;
const BACKGROUND_PREFETCH_INITIAL_DELAY_MS = 1000;
const BACKGROUND_PREFETCH_ERROR_DEDUPE_MS = 60 * 1000;
const backgroundPrefetchState = {
  queue: [],
  seen: new Set(),
  running: false,
  waiters: [],
  lastErrorLogAt: new Map(),
};

function currentIsoWeekParts(date = new Date()) {
  const target = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = target.getUTCDay() || 7;
  target.setUTCDate(target.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(target.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((target.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return { year: target.getUTCFullYear(), week, weekday: day };
}

function enqueueBackgroundPrefetch(path, ttlMs = BACKGROUND_PREFETCH_TTL_MS) {
  if (!path || !window.api?.prefetchGet) return;
  const key = String(path);
  if (backgroundPrefetchState.seen.has(key)) return;
  backgroundPrefetchState.seen.add(key);
  backgroundPrefetchState.queue.push({ path: key, ttlMs });
}

function enqueueBackgroundWork(key, run) {
  if (!key || typeof run !== "function") return;
  const normalizedKey = String(key);
  if (backgroundPrefetchState.seen.has(normalizedKey)) return;
  backgroundPrefetchState.seen.add(normalizedKey);
  backgroundPrefetchState.queue.push({ key: normalizedKey, run });
}

function backgroundPrefetchStatus() {
  return {
    queue: backgroundPrefetchState.queue.length,
    running: backgroundPrefetchState.running,
    seen: backgroundPrefetchState.seen.size,
  };
}

function resolveBackgroundPrefetchWaiters() {
  if (backgroundPrefetchState.running || backgroundPrefetchState.queue.length) return;
  const waiters = backgroundPrefetchState.waiters.splice(0);
  waiters.forEach((resolve) => resolve(backgroundPrefetchStatus()));
}

function waitForBackgroundPrefetchIdle(timeoutMs = 12000) {
  if (!backgroundPrefetchState.running && !backgroundPrefetchState.queue.length) {
    return Promise.resolve(backgroundPrefetchStatus());
  }
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      const index = backgroundPrefetchState.waiters.indexOf(done);
      if (index >= 0) backgroundPrefetchState.waiters.splice(index, 1);
      resolve(backgroundPrefetchStatus());
    }, Math.max(500, Number(timeoutMs) || 12000));
    const done = (status) => {
      clearTimeout(timer);
      resolve(status);
    };
    backgroundPrefetchState.waiters.push(done);
  });
}

function backgroundPrefetchErrorKey(error) {
  const status = Number(error?.status || 0);
  const message = String(error?.message || error?.name || "unknown").trim();
  return `${status || "unknown"}|${message || "unknown"}`;
}

function shouldLogBackgroundPrefetchError(error) {
  const key = backgroundPrefetchErrorKey(error);
  const now = Date.now();
  const lastAt = backgroundPrefetchState.lastErrorLogAt.get(key) || 0;
  if (now - lastAt < BACKGROUND_PREFETCH_ERROR_DEDUPE_MS) return false;
  backgroundPrefetchState.lastErrorLogAt.set(key, now);
  return true;
}

function backgroundPrefetchErrorMessage(item, error) {
  const target = item?.path || item?.key || "okänt underlag";
  const detail = error?.message ? `. ${error.message}` : ".";
  return `Bakgrundsladdning misslyckades: ${target}${detail} Liknande bakgrundsfel döljs en stund för att hålla loggen läsbar.`;
}

function scheduleNextBackgroundPrefetch() {
  if (backgroundPrefetchState.running || !backgroundPrefetchState.queue.length) return;
  backgroundPrefetchState.running = true;
  const run = async () => {
    const item = backgroundPrefetchState.queue.shift();
    if (item) {
      try {
        if (typeof item.run === "function") await item.run();
        else await window.api.prefetchGet(item.path, {
          cacheTtlMs: item.ttlMs,
          telemetryEventType: "background_prefetch",
          telemetrySource: "idle_prefetch",
        });
      } catch (error) {
        if (shouldLogBackgroundPrefetchError(error)) {
          appendAppLog(backgroundPrefetchErrorMessage(item, error), "warn", "Bakgrund");
        } else {
          console.warn("Bakgrundsladdning misslyckades", item.path || item.key, error);
        }
      }
    }
    backgroundPrefetchState.running = false;
    if (backgroundPrefetchState.queue.length) {
      setTimeout(scheduleNextBackgroundPrefetch, BACKGROUND_PREFETCH_DELAY_MS);
    } else {
      resolveBackgroundPrefetchWaiters();
    }
  };
  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(run, { timeout: 2000 });
  } else {
    setTimeout(run, BACKGROUND_PREFETCH_DELAY_MS);
  }
}

function enqueueVisiblePagePrefetches(user, activePage) {
  if (!user || !window.api?.prefetchGet) return;
  const { year, week, weekday } = currentIsoWeekParts();
  const areaId = areaFocusAreaId();
  const areaQuery = areaId != null ? `&area_id=${areaId}` : "";

  enqueueBackgroundPrefetch("/api/settings/sidebar", 5 * 60 * 1000);
  enqueueBackgroundPrefetch("/api/settings/role-access", 5 * 60 * 1000);
  enqueueBackgroundPrefetch("/api/settings/feature-registry", 5 * 60 * 1000);

  if (canViewPage(user, "mySchedule") || canViewPage(user, "myProductivity")) {
    enqueueBackgroundPrefetch("/api/personal/persons", 30 * 1000);
  }
  if (canViewPage(user, "mySchedule")) {
    enqueueBackgroundPrefetch(`/api/personal/schedule?year=${year}&week=${week}`, 25 * 1000);
  }

  if (canViewPage(user, "schedule")) {
    enqueueBackgroundPrefetch("/api/areas");
    enqueueBackgroundPrefetch("/api/activities");
    enqueueBackgroundPrefetch("/api/activities?include_inactive=true");
    if (areaQuery) {
      enqueueBackgroundPrefetch(`/api/schedule?year=${year}&week=${week}&weekday=${weekday}`, 25 * 1000);
      enqueueBackgroundPrefetch(`/api/schedule/summary?year=${year}&week=${week}&weekday=${weekday}`, 25 * 1000);
    }
    enqueueBackgroundPrefetch(`/api/schedule?year=${year}&week=${week}&weekday=${weekday}${areaQuery}`, 25 * 1000);
    enqueueBackgroundPrefetch(`/api/schedule/summary?year=${year}&week=${week}&weekday=${weekday}${areaQuery}`, 25 * 1000);
  }
  if (canViewPage(user, "overview")) {
    enqueueBackgroundPrefetch("/api/areas");
    enqueueBackgroundPrefetch("/api/activities");
    enqueueBackgroundPrefetch("/api/activities?include_inactive=true");
    if (areaQuery) {
      enqueueBackgroundPrefetch(`/api/overview?year=${year}&week=${week}`, 25 * 1000);
    }
    enqueueBackgroundPrefetch(`/api/overview?year=${year}&week=${week}${areaQuery}`, 25 * 1000);
  }
  if (canViewPage(user, "productivity")) {
    enqueueBackgroundPrefetch("/api/areas");
  }
  if (canViewPage(user, "allocationUploads") || canViewPage(user, "allocationProcess") || canViewPage(user, "allocationSettings") || canViewPage(user, "allocationProcessMatrix") || canViewPage(user, "allocationSplit")) {
    enqueueBackgroundPrefetch("/api/allokering/flows", 60 * 1000);
  }
  if (activePage === "allocationUploads" && canViewPage(user, "allocationUploads")) {
    enqueueBackgroundPrefetch("/api/coredata/files", 20 * 1000);
    enqueueBackgroundWork("allocation-upload-metadata", warmSharedAllocationMetadataCache);
  }
  if (canViewPage(user, "allocationSettings")) {
    enqueueBackgroundPrefetch("/api/allokering/ytgenerering-map-layout?include_options=false", 30 * 1000);
  }
  if (canViewPage(user, "allocationProcessMatrix")) {
    enqueueBackgroundPrefetch("/api/allokering/process-matrix", 30 * 1000);
  }
  if (canViewPage(user, "persons")) {
    enqueueBackgroundPrefetch(`/api/persons${areaId != null ? `?area_id=${areaId}` : ""}`, 30 * 1000);
    enqueueBackgroundPrefetch("/api/areas");
    enqueueBackgroundPrefetch("/api/activities");
    enqueueBackgroundPrefetch("/api/activities?include_inactive=true");
  }
  if (canViewPage(user, "activities")) {
    enqueueBackgroundPrefetch("/api/activities", 30 * 1000);
    enqueueBackgroundPrefetch("/api/areas");
  }
  if (canViewPage(user, "analytics")) {
    enqueueBackgroundPrefetch("/api/users", 30 * 1000);
    enqueueBackgroundPrefetch("/api/persons?include_inactive=true", 30 * 1000);
    enqueueBackgroundPrefetch("/api/activities?include_inactive=true", 30 * 1000);
    enqueueBackgroundPrefetch("/api/areas?include_inactive=true", 30 * 1000);
  }
  if (user?.is_super_user) {
    enqueueBackgroundPrefetch("/api/meta/uploads", 30 * 1000);
  }
  if (canViewPage(user, "users")) {
    enqueueBackgroundPrefetch("/api/users", 30 * 1000);
    enqueueBackgroundPrefetch("/api/settings", 60 * 1000);
    enqueueBackgroundPrefetch("/api/areas", 30 * 1000);
  }
  if (user?.is_super_user || canViewPage(user, "businesses")) {
    enqueueBackgroundPrefetch("/api/businesses", 60 * 1000);
    enqueueBackgroundPrefetch("/api/businesses?include_inactive=true", 60 * 1000);
    enqueueBackgroundPrefetch("/api/areas?include_inactive=true", 60 * 1000);
  }

  if (activePage === "allocationUploads" && window.preloadAllocationUploadsData) {
    window.preloadAllocationUploadsData();
  }
  setTimeout(scheduleNextBackgroundPrefetch, BACKGROUND_PREFETCH_INITIAL_DELAY_MS);
}

function reportPageOpen(user, activePage) {
  if (!activePage || activePage === "passwordSetup") return;
  const openedPage = sidebarPageDefinitions(user, activePage).find((page) => page.id === activePage);
  const viewLabel = openedPage?.label || activePage;
  if (typeof window.reportClientEvent === "function") {
    window.reportClientEvent("view_open", {
      view_id: activePage,
      view_label: viewLabel,
      page_path: window.location?.pathname || "/",
    });
  } else if (typeof window.api?.reportClientEvent === "function") {
    window.api.reportClientEvent("view_open", {
      view_id: activePage,
      view_label: viewLabel,
      page_path: window.location?.pathname || "/",
    });
  }
}

async function initPage(activePage, options = {}) {
  window.flowActivePage = activePage || "";
  if (document.body) document.body.dataset.activePage = activePage || "";
  const cachedUser = readCachedSidebarUser();
  if (cachedUserCanRenderPage(cachedUser, activePage, options)) {
    renderSidebar(cachedUser, activePage);
    syncToolsTabs(cachedUser);
  }

  const user = await loadCurrentUser();
  if (!user) {
    clearCachedSidebarUser();
    window.location.href = "/login.html";
    return null;
  }
  if (user.must_change_password && activePage !== "passwordSetup") {
    window.location.href = "/set-password.html";
    return null;
  }
  const shouldBlockForRoleAccess = activePage !== "passwordSetup"
    && typeof hasCachedRoleViewAccess === "function"
    && !hasCachedRoleViewAccess();
  if (shouldBlockForRoleAccess) {
    await refreshRoleViewAccessForRouting();
  } else if (activePage !== "passwordSetup") {
    void refreshRoleViewAccessForRouting();
  }
  if (options.requireAdmin && !isAdminUser(user)) {
    queueToast("Sidan kräver administratörsbehörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  const allowedViewIds = [activePage, ...(options.anyViewIds || [])].filter(Boolean);
  const hasViewAccess = allowedViewIds.some((viewId) => canViewPage(user, viewId));
  if (activePage !== "passwordSetup" && !hasViewAccess) {
    redirectAfterDeniedAccess(user, "Sidan kräver behörighet", activePage);
    return null;
  }
  if (options.requireSuperUser && !user?.is_super_user) {
    queueToast("Sidan kräver Super User-behörighet", "error");
    window.location.href = "/index.html";
    return null;
  }
  if (options.requirePlanningView && !canViewPage(user, activePage || "schedule")) {
    redirectAfterDeniedAccess(user, "Sidan kräver planerings- eller visningsbehörighet", activePage);
    return null;
  }
  if (options.requireEditor && !canEditPage(user, activePage)) {
    redirectAfterDeniedAccess(user, "Sidan kräver redigeringsbehörighet", activePage);
    return null;
  }
  if (options.requireAllocationTools && !canViewPage(user, activePage)) {
    redirectAfterDeniedAccess(user, "Sidan kräver rollen Lagerkontorist eller Artikelplacerare", activePage);
    return null;
  }
  if (options.requireAllocationProcess && !canViewPage(user, activePage)) {
    redirectAfterDeniedAccess(user, "Bearbeta kräver behörighet", activePage);
    return null;
  }
  cacheSidebarUser(user);
  renderSidebar(user, activePage);
  syncToolsTabs(user);
  reportPageOpen(user, activePage);
  reportPageLoadWaitMetric(activePage);
  void refreshRoleViewAccess(user, activePage);
  void refreshSidebarLayout(user, activePage);
  void enqueueVisiblePagePrefetches(user, activePage);
  if (activePage === "allocationUploads") clearAllocationUploadNotice();
  flushQueuedToast();
  if (user.is_demo) {
    document.body.classList.add("demo-mode");
    if (typeof ensureDemoBanner === "function") ensureDemoBanner();
    if (typeof maybeShowDemoTourPrompt === "function") {
      void maybeShowDemoTourPrompt(user, activePage);
    }
  }
  return user;
}


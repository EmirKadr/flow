---
title: Buggrapporter
status: experiment
updated: 2026-07-07
tags: [bugg, inspelning, rrweb, experiment]
---

# Buggrapporter: 30 sekunders inspelning från Bugg-knappen

Kort svar: alla inloggade användare kan klicka på 🐞-knappen i sidebar-footern
(bredvid områdes-/verksamhetstogglarna), godkänna i en popup och spela in 30
sekunder av vad de ser och gör i appen. Rapporten (DOM-inspelning via vendrad
rrweb + tekniska fel) skickas till backend och kan spelas upp av behöriga i
vyn **Buggrapporter**. Ingen inspelning startar utan OK i popupen; lösenords-
fält maskas alltid; rapporter raderas efter 30 dagar.

Beslutsdatum för experimentet: **2026-08-07** — då avgör Emir: släpp bredare
(vy-behörighet via matrisen), förläng, eller ta bort.

## Användarflöde

1. Klick på 🐞 i sidebar-footern → popup förklarar att kommande 30 sekunder
   spelas in och skickas till administratören, med valfritt fält "Vad hände?".
   Popupen stängs bara via knapparna (dialogregeln — den har textarea).
2. OK → rrweb + rapportlogiken lazy-laddas (vanliga sidladdningar betalar
   aldrig för bundeln), inspelning startar, röd indikator med nedräkning och
   "Stoppa och skicka nu" visas.
3. Vid stopp/30 s: händelserna + kontext (konsolfel, JS-fel, user agent,
   viewport) POST:as till `/api/bug-reports`. Toast bekräftar.
4. Behörig användare (vy-id `bugReports`, default endast Super User) öppnar
   **Buggrapporter** i Verktyg-menyn: lista → klick → uppspelning i
   rrweb-Replayer + kontext. Status (Ny/Att göra/Klar) sätts via dropdown
   direkt på raden eller knappar i detaljpanelen; **Ta bort** (per rad och i
   detaljpanelen) raderar rapporten permanent efter bekräftelsemodal.
   DB-värdena är oförändrade `new`/`seen`/`done` — `seen` visas som
   "Att göra" sedan 2026-07-07.

## Teknik

- **Inspelning**: `js/common/bug_report.js` (lazy-laddad av sidebar.js) +
  vendrad `js/vendor/rrweb.min.js` (UMD, npm-paketet rrweb; uppdateras via
  npm + kopiering, bevakas av dependabot/npm audit). DOM-replay — ingen
  `getDisplayMedia`-dialog, inget utanför appfliken kan spelas in.
- **Maskering**: `maskInputOptions: { password: true }`; inspelningen visar
  i övrigt samma data som användaren själv såg i sin verksamhet.
- **Backend**: `routers/bug_reports.py`, tabell `bug_reports`
  (migration 0047). Blobben lagras som rå JSON-text (`events_json`) —
  medvetet inte JSON-kolumn: den ska aldrig frågas på.
- **Skyddsräcken**: storlekstak `BUG_REPORTS_MAX_EVENTS_BYTES` (4 MB),
  rate limit `BUG_REPORTS_RATE_LIMIT_PER_HOUR` (3/användare/timme,
  DB-räknad — fungerar oavsett antal workers), retention
  `BUG_REPORTS_RETENTION_DAYS` (30, städas vid uppstartsjobbet
  `bug_reports_retention_purge` och vid varje inskick), av/på via
  `BUG_REPORTS_ENABLED`.
- **Behörighet**: skapa = alla inloggade; lista/spela upp = vy `bugReports`
  (view), status och ta bort = `bugReports` (edit). Vyn är inte i någon rolls default —
  bara Super User ser den tills den delas ut i vybehörighetsmatrisen.
  Verksamhetsscope via `visible_business_id`.
- **Uppspelning**: `bug-rapporter.html` + `js/bug_reports_admin.js` +
  `css/vendor-rrweb.min.css`; rrweb.Replayer direkt (ingen rrweb-player).
  Sidan laddar vendor-bundeln statiskt — medvetet undantag
  `{"vendor"}` i ALLOWED_PAGE_DOMAINS.

## Historik och audit

- `bug_report`/`create`: view_id, page_path, notislängd, events_bytes,
  event_count — aldrig inspelningsinnehåll eller notistext.
- `bug_report`/`status_change`: gammal/ny status.
- `bug_report`/`delete`: status, view_id, page_path, events_bytes vid
  borttagning — aldrig inspelningsinnehåll.
- Frontend trackar `bug_report_recording_started` via flowTrack.

## Agent-påminnelse

Agenter som börjar en arbetsinsats i repot kör
`python -m tools.bug_reports_status` och påminner Emir om öppna rapporter
(status `new`/`seen`). Verktyget återanvänder healthcheck-cookiejaren
(`.flow-cli-cookies.txt`), är best effort och hoppar mjukt över sig självt
utan inloggning. Regeln står i `AGENTS.md` ("Buggrapport-påminnelse vid
arbetsstart").

## Felsökningssvar för framtida chat

**"Jag klickade på skalbaggen men inget händer."**
Kontrollera att `BUG_REPORTS_ENABLED=true` och att popupen inte blockeras.
Rapportlogiken lazy-laddas — nätverksfel vid laddning ger en fel-toast.

**"Användaren fick 'redan skickat flera buggrapporter'."**
Rate limit: max `BUG_REPORTS_RATE_LIMIT_PER_HOUR` per användare och timme.

**"Uppspelningen är tom/trasig."**
Inspelningar från äldre appversioner kan sakna full snapshot. Kontrollera
`events_bytes` i listan; mycket små inspelningar (<5 kB) saknar ofta
fullsnapshot för att inspelningen stoppades direkt.

**"Vem kan se rapporterna?"**
Endast Super User tills vyn `bugReports` delas ut per roll i
vybehörighetsmatrisen. Rapporter är verksamhetsscopade för icke-superusers.

## Källor

- `../app/frontend/js/common/bug_report.js`
- `../app/frontend/js/bug_reports_admin.js`
- `../app/frontend/bug-rapporter.html`
- `../app/backend/routers/bug_reports.py`
- `../app/alembic/versions/0047_bug_reports.py`
- `../tests/services/test_bug_reports.py`

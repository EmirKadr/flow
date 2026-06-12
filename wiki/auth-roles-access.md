---
title: Roller och behorighet
status: aktiv
updated: 2026-06-11
tags: [auth, roller, behorighet]
---

# Roller och behorighet

Kort svar: inloggning ar sessionsbaserad. Roller styr vad anvandaren ser och far redigera, och verksamhet styr vilken data anvandaren ens kan se. Nyare klienter anvander `roles` som lista, men `role` finns kvar for bakatkompatibilitet.

## Inloggningsflode

1. Anvandaren skickar anvandarnamn och losenord till `/api/auth/login`.
2. Backend accepterar bara aktiv anvandare.
3. Om anvandarnamnet saknas som anvandare men matchar en aktiv persons `noman`, skapas ett aktivt `person`-konto automatiskt med `person_id`, verksamhet och hemomrade fran personen.
4. Auto-skapade personkonton loggar in forsta gangen med tomt losenord och skickas sedan till `set-password.html`.
5. Om anvandaren saknar/far satt forsta losenord markeras `must_change_password`.
6. Klienten skickar anvandaren till `set-password.html` om losenord maste skapas.
7. Varje skyddad sida anropar `/api/auth/me` via `initPage`.
8. `/api/auth/me` returnerar aven `business_id`, verksamhetskod, verksamhetsnamn, `person_id` och Super User-status.
9. `401` leder till `login.html`; `403 password_setup_required` leder till `set-password.html`.

## Verksamhetsscope

- Alla icke-Super Users, aven admins, ar lasta till sin egen verksamhet.
- Vanliga anvandare ser sin verksamhets data och omraden. Om verksamheten har aktivt omrade med kod `ANNAT` far anvandaren `∞`, som betyder alla omraden i den verksamheten.
- R3-anvandare ser bara R3 och far bara R3-toggle tills `ANNAT` laggs till for R3 i Verksamheter-vyn.
- Super User kan se alla verksamheter. I sidebar betyder `∞` globalt allt for Super User.
- Vid skapande/import behover vanliga anvandare inte ange verksamhet; backend anvander anvandarens verksamhet. Super User maste valja verksamhet om den inte kan harledas fran omrade, person eller aktivitet.
- API ska svara 404/403 for frammande id utan att exponera den andra verksamhetens data.

## Roller

| Roll | Svensk etikett | Typisk atkomst |
| --- | --- | --- |
| `leader` | Arbetsledare | Redigera Bemanning/Oversikt och normalt Personer/Aktiviteter |
| `staffing_manager` | Bemanningsansvarig | Liknar arbetsledare med planeringsansvar |
| `admin` | Administrator | Register, anvandare och settings, men inte automatiskt super user |
| `super_user` | Super User | Kravs for historik, Meta, verksamheter och vissa kodandringar; kan alltid redigera vyer |
| `warehouse_clerk` | Lagerkontorist | Lagerverktyg, framfor allt uppladdning och Dela |
| `article_placer` | Artikelplacerare | Lagerverktyg med liknande sjalvservicebehov |
| `person` | Person | Egenvy for Mitt schema och Min produktivitet |
| `viewer` | Visning | Laslage for Bemanning/Oversikt |

Utöver rollerna finns det fasta `demo`-kontot (username = `demo`, admin-roll mot Stigamo) som triggar [demo-laget](demo-mode.md): en privat SQLite-snapshot per inloggning som städas vid utloggning. `is_demo`-flaggan i `UserOut`/`UserAdminOut` styr DEMO-bannern, guidad rundtur och låsning av kontot i Användare-vyn.

## Vyatkomst

`common.js` och backendens `require_view_access` anvander samma koncept: varje roll kan ha `none`, `view` eller `edit` per vy. Vybehorigheter ar globala for rollen och galler over verksamheter. Super User visas i matrisen som last `edit` och har alltid full atkomst via serverregeln. Det fasta demo-kontot far dessutom den virtuella rollen `demo`, sa Demo-kolumnen i matrisen kan ge extra vyatkomst for presentationslaget.

Viktigt for support/chat: att "kontrollera Vybehorigheter" ar inte en atgard en vanlig anvandare kan gora sjalv. Knappen `Vybehorigheter` finns pa Anvandare-sidan och kraver atkomst till skyddade admin/installningsvyer. Svara darfor: "Be en admin eller Super User kontrollera Vybehorigheter", inte "ga till Vybehorigheter" om anvandaren sjalv saknar den atkomsten.

Apphjalpens LLM-prompt far en begransad supportkontext om inloggad anvandare: roll, roller, Super User-status, omrade och effektiva vybehorigheter per vy (`edit`, `view`, `none`). Den kontexten ska anvandas for direkta svar om saknade menyer/knappar. Känslig information som losenord, hash, sessioncookies, API-nycklar och tokens skickas inte.

Vyer som kan styras:

- `schedule`, `overview`, `productivity`, `dataFetch`
- `mySchedule`, `myProductivity`
- `allocationUploads`, `allocationProcess`, `allocationProcessMatrix`, `allocationSplit`
- `allocationSettings`, `staffingSettings`
- `persons`, `personSortOrder`, `personImport`
- `activities`, `activityImport`, `areas`
- `analytics`, `meta`, `users`, `userImport`
- `appSettings`, `sidebarLayout`, `roleAccess`, `businesses`

## Read-only-lage

Om anvandaren bara har `view`:

- Bemanning visar celler men sparar inte andringar.
- Oversikt visar dagar men sparar inte andringar.
- Knappar som kopiera/rensa kan vara disabled eller ge varning.
- Toasten forklarar: "Visningslage: du kan se ... men inte andra den."

## Vanliga orsaker till nekad funktion

- Vyn syns inte i sidebar: rollen har `none` for vyn eller sidan filtreras bort.
- Knappen syns men fungerar inte: anvandaren har `view`, inte `edit`.
- Importknapp ar dold: importvyn saknar edit-atkomst.
- Drag-sortering av personnamn i Bemanning/Oversikt fungerar inte: rollen saknar `personSortOrder=edit`, personfiltret ar aktivt, eller listan har andrats. Bemanningsansvarig/admin ar begransade till eget omrade; Super User och demo kan sortera alla synliga personer.
- Historik eller Meta nekas: kraver Super User. Produktivitet nekas: rollen saknar `productivity` i vyatkomst.
- Hamta data saknas eller nekas: `dataFetch` saknas i vyatkomst. Eftersom vyn kan hamta data fran extern datakalla har inga basroller standardatkomst; Super User kan oppna den.
- Bearbeta saknas eller nekas: rollen saknar `allocationProcess=edit` i vyatkomst. Lagerroller har som standard Uppladdningar och Dela, men kan fa Bearbeta via Vybehorigheter.
- Bearbeta-fliken i Installningar saknas eller Bearbeta-matrisen kan inte sparas: rollen saknar `allocationProcessMatrix=view` eller `allocationProcessMatrix=edit`. Med `view` visas matrisen lasande; med `edit` kan den sparas. Admin har `edit` som standard och Super User har alltid full atkomst.
- Installningar saknas eller Ytgenereringens ytkarta inte kan sparas: rollen saknar `allocationSettings=view` eller `allocationSettings=edit`. Admin har `edit` som standard och Super User har alltid full atkomst.
- Bemanning-fliken i Installningar saknas eller historiktimmar inte kan sparas: rollen saknar `staffingSettings=view` eller `staffingSettings=edit`. Admin har `edit` som standard och Super User har alltid full atkomst.
- Mitt schema eller Min produktivitet saknas: kontot saknar rollen `person` och ar inte Super User. Person-konton kan bara se sin egen `person_id`; Super User kan valja person i vyernas rullista.

## Kallor

- `../app/backend/deps.py`
- `../app/backend/business_scope.py`
- `../app/backend/user_access.py`
- `../app/frontend/js/common.js`
- `../app/frontend/js/users.js`
- `../APP_MIGRATION_PLAN.md`

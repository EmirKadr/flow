---
title: Roller och behorighet
status: aktiv
updated: 2026-05-21
tags: [auth, roller, behorighet]
---

# Roller och behorighet

Kort svar: inloggning ar sessionsbaserad. Roller styr vad anvandaren ser och far redigera. Nyare klienter anvander `roles` som lista, men `role` finns kvar for bakatkompatibilitet.

## Inloggningsflode

1. Anvandaren skickar anvandarnamn och losenord till `/api/auth/login`.
2. Backend accepterar bara aktiv anvandare.
3. Om anvandaren saknar/far satt forsta losenord markeras `must_change_password`.
4. Klienten skickar anvandaren till `set-password.html` om losenord maste skapas.
5. Varje skyddad sida anropar `/api/auth/me` via `initPage`.
6. `401` leder till `login.html`; `403 password_setup_required` leder till `set-password.html`.

## Roller

| Roll | Svensk etikett | Typisk atkomst |
| --- | --- | --- |
| `leader` | Arbetsledare | Redigera Bemanning/Oversikt och normalt Personer/Aktiviteter |
| `staffing_manager` | Bemanningsansvarig | Liknar arbetsledare med planeringsansvar |
| `admin` | Administrator | Register, anvandare och settings, men inte automatiskt super user |
| `super_user` | Super User | Kravs for historik och produktivitet enligt skyddade vyer/API |
| `warehouse_clerk` | Lagerkontorist | Lagerverktyg, framfor allt uppladdning, Dela och Harleda |
| `article_placer` | Artikelplacerare | Lagerverktyg med liknande sjalvservicebehov |
| `viewer` | Visning | Laslage for Bemanning/Oversikt |

## Vyatkomst

`common.js` och backendens `require_view_access` anvander samma koncept: varje roll kan ha `none`, `view` eller `edit` per vy. Super user kan fa extra vyer beroende pa installning och serverregler.

Viktigt for support/chat: att "kontrollera Vybehorigheter" ar inte en atgard en vanlig anvandare kan gora sjalv. Knappen `Vybehorigheter` finns pa Anvandare-sidan och kraver atkomst till skyddade admin/installningsvyer. Svara darfor: "Be en admin eller Super User kontrollera Vybehorigheter", inte "ga till Vybehorigheter" om anvandaren sjalv saknar den atkomsten.

Apphjalpens LLM-prompt far en begransad supportkontext om inloggad anvandare: roll, roller, Super User-status, omrade och effektiva vybehorigheter per vy (`edit`, `view`, `none`). Den kontexten ska anvandas for direkta svar om saknade menyer/knappar. Känslig information som losenord, hash, sessioncookies, API-nycklar och tokens skickas inte.

Vyer som kan styras:

- `schedule`, `overview`, `productivity`, `dataFetch`
- `allocationUploads`, `allocationProcess`, `allocationSplit`, `allocationTrace`
- `persons`, `personImport`
- `activities`, `activityImport`, `areas`
- `analytics`, `users`, `userImport`
- `appSettings`, `sidebarLayout`, `roleAccess`

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
- Historik/Produktivitet nekas: kraver super user/vyatkomst.
- Hamta data saknas eller nekas: `dataFetch` saknas i vyatkomst. Eftersom vyn kan hamta data fran extern datakalla har inga basroller standardatkomst; Super User kan oppna den.
- Bearbeta saknas eller nekas: `allocationProcess` saknas i vyatkomst eller anvandaren ar inte Super User. Lagerroller har som standard Uppladdningar, Dela och Harleda, men inte Bearbeta.

## Kallor

- `../app/backend/deps.py`
- `../app/backend/user_access.py`
- `../app/frontend/js/common.js`
- `../app/frontend/js/users.js`
- `../APP_MIGRATION_PLAN.md`

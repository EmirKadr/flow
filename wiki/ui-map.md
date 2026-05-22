---
title: UI-karta och alla kontroller
status: aktiv
updated: 2026-05-22
tags: [ui, knappar, funktioner, chat-stod]
---

# UI-karta och alla kontroller

Kort svar: de flesta sidor delar sidebar, omradesfokus, tema, logg och auth-guard fran `common.js`. Varje funktionssida har egna kontroller som ar dokumenterade mer detaljerat pa respektive sida.

## Gemensamma kontroller pa skyddade sidor

| Kontroll | Var | Vem ser/far | Vad hander | Vanliga fel/fragor |
| --- | --- | --- | --- | --- |
| Sidebar-lankar | Vanster meny | Filtreras per vybehorighet | Navigerar till Bemanning, Oversikt, Produktivitet, Hamta data, Bearbeta, Dela, Personer, Aktiviteter, Historik, Anvandare | Om en vy saknas har rollen troligen `none` for vyn. Be admin/Super User kontrollera `Vybehorigheter`; vanlig anvandare kan ofta inte gora det sjalv. |
| Hamburgare | Sidebar topp | Alla inloggade | Faller ihop/oppnar sidebar och sparar `sidebar-collapsed` i `localStorage` | Om menyn ser "for liten" ut ar den troligen hopfallen. |
| Redigera meny | Sidebar topp, pennikon | Anvandare med edit pa `sidebarLayout` | Oppnar modal dar menyordning, rubriker och undervyer kan andras for aktuell verksamhet | Andringen galler aktuell verksamhet efter sparning. |
| Omradesfokus | Sidebar footer | Alla inloggade | Byggs dynamiskt fran synliga omraden. Stigamo visar Stigamo-omraden plus `∞`, R3 visar bara R3, och Super User kan anvanda `∞` globalt. Filtrerar Bemanning, Oversikt, Produktivitet, Aktiviteter och Anvandare. | Om "fel" omrade visas kan fokus ligga pa annat omrade eller verksamhet an forvantat. Gammalt lokalt fokus migreras fran kod till omrades-id. |
| Apphjalp/pratbubblor | Sidebar footer, direkt under omradesfokus/infinity | Alla inloggade | Oppnar/stanger en liten chattpanel. Dialog, oppet lage och utkast sparas i aktuell session. | Max 10 lyckade fragor per session. `Rensa dialog` nollstaller dialog och kvot. Se [Apphjalp och LLM-chatt](app-chat.md). |
| Logg | Sidebar footer | Alla inloggade | Oppnar sidopanel med app-logg for t.ex. observations-uppdatering | Tom logg betyder bara att inget har loggats i aktuell session. |
| Uppladdningar/databasikon | Sidebar utility | Roller med `allocationUploads` | Genvag till `uppladdningar.html`; visar badge nar filer lagts in | Hogerklick pa ikonen visar "Rensa filer". |
| Tema | Sidebar footer | Alla inloggade | Växlar ljust/morkt tema och sparar `flow-theme` | Tema ar lokalt for webblasaren/desktopprofilen. |
| Logga ut | Sidebar botten | Alla inloggade | `POST /api/auth/logout`, rensar sidebar-user-cache, gar till login | Om sessionen redan ar dod skickas anvandaren anda till login. |
| Toast | Globalt | Alla | Korta status-/felmeddelanden fran JS | Viktig for chatt: be anvandaren citera toasten exakt. |
| Enter i dialogruta | Alla modaler | Alla | Klickar modalens primara knapp, t.ex. `Spara`, `Skapa` eller `Stang` | Galler inte flerradiga textfalt, checkboxar eller knappar som redan har fokus. |

## Sidor och huvudkontroller

| Sida | Fil | Huvudkontroller | Mer info |
| --- | --- | --- | --- |
| Login | `login.html` | Anvandarnamn, losenord, Logga in | [Roller och behorighet](auth-roles-access.md) |
| Skapa losenord | `set-password.html` | Nytt losenord, Bekrafta, Spara losenord | [Roller och behorighet](auth-roles-access.md) |
| Bemanning | `index.html` | Ar, vecka, dag, datum, Kopiera dag, Rensa dag, undo/redo, celler, tips, kalkyl | [Bemanning](bemanning-schedule.md) |
| Oversikt | `overblick.html` | Vy vecka/manad, prev/next, ar, vecka/manad, undo/redo, dagceller | [Oversikt](overview-page.md) |
| Personer | `personer.html` | Ny person, Flera nya personer, importmall, importera Excel, hjalp, filter/sortering, Schema, Ta bort | [Personer](persons.md) |
| Aktiviteter | `aktiviteter.html` | Ny aktivitet, Flera nya aktiviteter, importmall, importera Excel, hjalp, Redigera, Ta bort | [Aktiviteter och omraden](activities-areas.md) |
| Anvandare | `anvandare.html` | Ny anvandare, Flera nya anvandare, importmall, importera Excel, Vybehorigheter, cell-las, Visa inaktiva | [Anvandare och installningar](users-settings.md) |
| Verksamheter | `verksamheter.html` | Ny verksamhet, Redigera, Visa inaktiva, Nytt omrade, Redigera/Ta bort omrade | [Anvandare och installningar](users-settings.md) |
| Historik | `historik.html` | Vy-toggle, period, anvandare, typ, atgard, objekt-id, Uppdatera | [Historik och audit](history-audit.md) |
| Hamta data | `hamta-data.html` | Prompt, max rader, Tolka, Hamta data, Exportera Excel | [Hamta data](data-fetch.md) |
| Produktivitet | `produktivitet.html` | Datum, prev/next, sok, filkrav/drag-drop | [Produktivitet](productivity.md) |
| Uppladdningar | `uppladdningar.html` | Valj filer, Rensa alla, per-slot Valj/rensa, drag-drop | [Lagerverktyg](warehouse-tools.md) |
| Bearbeta | `bearbeta.html` | Valj filer, flodesknappar, info, resultat, Excel/CSV | [Lagerverktyg](warehouse-tools.md) |
| Dela | `dela.html` | Textfil/textarea, antal per kolumn, Dela varden | [Lagerverktyg](warehouse-tools.md) |

## Generella UI-regler

- Om en knapp ar dold beror det oftast pa vybehorighet.
- Om en knapp ar disabled beror det oftast pa read-only-lage, saknat underlag, pagaende korning eller tom undo/redo-stack.
- Om en andring inte sparas ska toast och Network/API-status avgora nasta felsokningssteg.
- Webben och Windows-appen ska ha samma anvandarbeteende. Om de skiljer sig, kontrollera desktop-proxyn och cachad frontend.

## Kodkallor

- `../app/frontend/js/common.js`
- `../app/frontend/js/api.js`
- `../app/frontend/*.html`

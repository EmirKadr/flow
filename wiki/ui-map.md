---
title: UI-karta och alla kontroller
status: aktiv
updated: 2026-07-02
tags: [ui, knappar, funktioner, chat-stod]
---

# UI-karta och alla kontroller

Kort svar: de flesta skyddade sidor delar sidebar, omradesfokus, tema, logg och auth-guard fran `common.js`. Publika specialvyer, som Meta-uppladdning, kan vara fristaende utan sidebar. Varje funktionssida har egna kontroller som ar dokumenterade mer detaljerat pa respektive sida.

Sidebaren ar fast i vansterkanten och byter inte position nar sidans innehall skrollas. Om det finns manga menyval skrollar bara menylistan inne i sidebaren; footer med omradesfokus, hjalp/logg/tema och utloggning ligger kvar.

## Gemensamma kontroller pa skyddade sidor

| Kontroll | Var | Vem ser/far | Vad hander | Vanliga fel/fragor |
| --- | --- | --- | --- | --- |
| Sidebar-lankar | Vanster meny | Filtreras per vybehorighet | Visar huvudmenyer som `Bemanning`, `Verktyg`, `Bearbeta` och `Installningar`. `Bemanning`, `Verktyg` och `Installningar` leder till forsta atkomliga flik i respektive grupp. | Om en vy saknas har rollen troligen `none` for vyn. Be admin/Super User kontrollera `Vybehorigheter`; vanlig anvandare kan ofta inte gora det sjalv. |
| Hogerklick pa `Bemanning`, `Verktyg` eller `Installningar` i sidebar | Vanster meny | Filtreras per vybehorighet | Oppnar en snabbmeny med gruppens flikar. `Bemanning` visar Bemanning, Oversikt, Produktivitet, Sankey, Aktiviteter, Personer, Anvandare, Verksamheter, Mitt schema och Min produktivitet. `Verktyg` visar Dela, Etiketter, MCP, Hamta data, Historik och Meta. `Installningar` visar Ytkarta, Bearbeta, Bemanning och Intakt/utgift. | Om bara en delmangd syns saknar rollen atkomst till ovriga vyer. |
| Hamburgare | Sidebar topp | Alla inloggade | Faller ihop/oppnar sidebar och sparar `sidebar-collapsed` i `localStorage` | Om menyn ser "for liten" ut ar den troligen hopfallen. |
| Appzoom | Sidebar topp, forstoringsglas med minus/plus | Alla inloggade | Zoomar hela appytan ut/in. Reset finns pa `Ctrl+0`; zoom kan ocksa andras med `Ctrl+-`, `Ctrl++` och `Ctrl+scroll`, och sparas lokalt i `flow-app-zoom`. | Om tabeller eller text kanns for stora/sma kan anvandaren justera utan webblasarmenyn. |
| Redigera meny | Sidebar topp, pennikon | Anvandare med edit pa `sidebarLayout` | Oppnar modal dar menyordning, rubriker och undervyer kan andras for aktuell verksamhet | Andringen galler aktuell verksamhet efter sparning. |
| Omradesfokus | Sidebar footer | Alla inloggade | Byggs dynamiskt fran synliga omraden. Vanligt klick stegar mellan fokuslagen; hogerklick oppnar en meny dar anvandaren kan valja omrade direkt. Menyn kan scrollas utan att stangas nar manga omraden finns. Vanliga anvandare ser omraden i egen verksamhet och far `∞` om verksamheten har aktivt `ANNAT`; Super User ser alla aktiva omraden plus globalt `∞`, filtrerat av verksamhetsfokus-togglen nar en specifik verksamhet ar vald dar. Filtrerar Bemanning, Oversikt, Personer, Aktiviteter och Anvandare. Produktivitet visar alla personer i verksamheten. | Om "fel" omrade visas kan fokus ligga pa annat omrade eller verksamhet an forvantat. Gammalt lokalt fokus migreras fran kod till omrades-id. |
| Verksamhetsfokus | Sidebar footer, bredvid omradesfokus | Endast Super User | Egen toggle som byggs fran `/api/businesses`. Vanligt klick stegar mellan verksamheterna och `∞` (alla verksamheter); hogerklick oppnar en meny med alla aktiva verksamheter. Valet sparas i `flow-business-focus` och filtrerar omradestogglens alternativ till vald verksamhets omraden. Om aktuellt omradesfokus inte tillhor vald verksamhet nollstalls det till `∞`. Nar omradesfokus ar `∞` anvander lagerverktyg/Hamta data vald verksamhet i stallet for kontots egen. | Syns inte for vanliga anvandare - de ar redan lasta till egen verksamhet. Visar `!` om verksamheterna inte kunde lasas. |
| Rapportera bugg (🐞) | Sidebar footer, i fokusraden | Alla inloggade | Oppnar consent-popup; OK startar 30 s DOM-inspelning (rrweb, lazy-laddad) med nedrakningsindikator och "Stoppa och skicka nu". Rapporten skickas till POST /api/bug-reports och granskas i vyn Buggrapporter. Se [Buggrapporter](bug-reports.md). | Inspelning startar aldrig utan OK. Losenordsfalt maskas. Max 3 rapporter/timme och anvandare. |
| Apphjalp/pratbubblor | Sidebar footer, direkt under omradesfokus/infinity | Alla inloggade | Oppnar/stanger en liten chattpanel. Dialog, oppet lage och utkast sparas i aktuell session. | Max 10 lyckade fragor per session. `Rensa dialog` nollstaller dialog och kvot. Se [Apphjalp och LLM-chatt](app-chat.md). |
| Logg | Sidebar footer | Alla inloggade | Oppnar sidopanel med app-logg for t.ex. observations-uppdatering. Ikonen visar en kort pil- och bubbelsignal varje gang nagot loggas, utan att spara eller visa en raknare efterat. | Tom logg betyder bara att inget har loggats i aktuell session. Sjalva loggraderna sparas i aktuell browserflik tills anvandaren rensar loggen. |
| Uppladdningar/databasikon | Sidebar utility | Roller med `allocationUploads` | Genvag till `uppladdningar.html`; visar badge nar filer lagts in | Hogerklick pa ikonen visar "Rensa filer". |
| Tema | Sidebar footer | Alla inloggade | Växlar ljust/morkt tema och sparar `flow-theme` | Tema ar lokalt for webblasaren/desktopprofilen. |
| Logga ut | Sidebar botten | Alla inloggade | `POST /api/auth/logout`, rensar sidebar-user-cache, gar till login | Om sessionen redan ar dod skickas anvandaren anda till login. |
| Toast | Globalt | Alla | Korta status-/felmeddelanden fran JS | Viktig for chatt: be anvandaren citera toasten exakt. |
| Tabellrubriker | Vanliga list- och rapporttabeller | Alla som ser tabellen | Klick sorterar synliga rader stigande/fallande klient-side. Matristabeller, inline-edit-tabeller, importmodaler och tabeller med egen specialsortering anvander sitt eget beteende. | Sorteringen skickar inte nytt API-filter och paverkar bara raderna som redan ar synliga. |
| Enter i dialogruta | Alla modaler | Alla | Klickar modalens primara knapp, t.ex. `Spara`, `Skapa` eller `Stang` | Galler inte flerradiga textfalt, checkboxar eller knappar som redan har fokus. |
| Interaction-tracking | Globalt via `common.js` | Inloggade vyer, samt allowlistad Meta-uppladdning | Auto-capturar klick, submit, select/checkbox/file-change, contextmenu och kopplar API-resultat till senaste interaction | Syns i Historik > Funktioner/Knappar/Kolumner/Floden. Klartextprover sparas bara om `TRACKING_ALLOW_VALUE_SAMPLES=true`; secrets, filnamn och sokvagar sparas aldrig. |

## Sidor och huvudkontroller

| Sida | Fil | Huvudkontroller | Mer info |
| --- | --- | --- | --- |
| Login | `login.html` | Anvandarnamn, losenord, Logga in | [Roller och behorighet](auth-roles-access.md) |
| Skapa losenord | `set-password.html` | Nytt losenord, Bekrafta, Spara losenord | [Roller och behorighet](auth-roles-access.md) |
| Mitt schema | `mitt-schema.html` | Veckonavigering, personval for Super User, dagens status, just nu, veckans dagar och aktiviteter | [Roller och behorighet](auth-roles-access.md) |
| Min produktivitet | `min-produktivitet.html` | Datumnavigering, personval for Super User, dagens produktivitetssnitt, pass och veckans produktivitet per aktivitet | [Roller och behorighet](auth-roles-access.md) |
| Bemanning | `index.html` | Ar, vecka, dag, datum, Produktivitet-kolumn, historiskt snitt vid cell-hover, Kopiera dag, Rensa dag, undo/redo, celler, tips, manuell/automatisk kalkyl och kalkylimport | [Bemanning](bemanning-schedule.md) |
| Oversikt | `overblick.html` | Vy vecka/manad, prev/next, ar, vecka/manad, undo/redo, dagceller | [Oversikt](overview-page.md) |
| Personer | `personer.html` | Ny person, Flera nya personer, importmall, importera Excel, hjalp, filter/sortering, Schema, Ta bort | [Personer](persons.md) |
| Aktiviteter | `aktiviteter.html` | Ny aktivitet, Flera nya aktiviteter, importmall, importera Excel, hjalp, Redigera, Ta bort | [Aktiviteter och omraden](activities-areas.md) |
| Anvandare | `anvandare.html` | Ny anvandare, Flera nya anvandare, importmall, importera Excel, cell-las, Visa inaktiva | [Anvandare och installningar](users-settings.md) |
| Verksamheter | `verksamheter.html` | Ny verksamhet, klickbara celler, rubriksortering, Visa inaktiva, Nytt omrade, Lagg till `∞`, Ta bort omrade | [Anvandare och installningar](users-settings.md) |
| Historik | `historik.html` | Vy-toggle, period, verksamhet, anvandare, typ, atgard, objekt-id, Uppdatera, Funktioner, Knappar, Kolumner, Floden, AI-analys | [Historik och audit](history-audit.md) |
| Hamta data | `hamta-data.html` | Prompt, max rader, Tolka, Hamta data, Exportera Excel | [Hamta data](data-fetch.md) |
| MCP | `mcp.html` | Status, LLM-hjarna, fraga, Uppdatera, Rensa, Skicka, svar och MCP-kontext | [MCP](mcp.md) |
| Etiketter | `label-editor.html` | Profil, bredd/höjd i mm, spara/ta bort profil, Text, QR, Code128, Rektangel, Ellips, Linje, Symbol, Penna/Fyll/Sudd, dra objekt, dra kanter/hörn, Duplicera, Ta bort, Delete/Backspace, Ctrl+C/X/V, Ctrl+Z/Y, Rensa, Skriv ut | [Etiketter](label-editor.md) |
| Produktivitet | `produktivitet.html` | Periodval Dag/Vecka/Manad/Ar, datumankare, prev/next, Helbild, Exportera flowchart med nivaval, hierarkitrad for verksamhet, omrade, aktivitet, person, timme och processpoang | [Produktivitet](productivity.md) |
| Sankey - Inbound | `sankey-inbound.html` | Periodval Dag/Vecka/Manad/Ar, datum, bolag, Visa endast forverkade, Aterstall vy, Exportera SVG, Exportera sparning, klickbara Sankey-noder och lankar med pallgrenstabell/export i detaljpanelen, outboundtabell for Butik/E-handel | [Sankey - Inbound](sankey-inbound.md) |
| Uppladdningar | `uppladdningar.html` | Valj filer, Rensa alla, per-slot Valj/rensa, drag-drop | [Lagerverktyg](warehouse-tools.md) |
| Bearbeta | `bearbeta.html` | Valj filer, flodesknappar, info, resultat, Excel/CSV | [Lagerverktyg](warehouse-tools.md) |
| Installningar | `installningar.html` | Ytgenereringens ytkarta, Bearbeta-matris, zoom/pan, lediga U-platser, spara global kartlayout, Bemanning-flik for historiktimmar till hover-snitt/automatisk kalkyl och val av aktiviteter med historiskt snitt, Vybehorigheter-flik (rollmatrisen, flyttad fran Anvandare 2026-07-07) | [Lagerverktyg](warehouse-tools.md), [Bemanning](bemanning-schedule.md), [Anvandare och installningar](users-settings.md) |
| Dela | `dela.html` | Textfil/textarea, antal per kolumn, Dela varden | [Lagerverktyg](warehouse-tools.md) |
| Meta | `meta.html` | Sok, Uppdatera, export, Sandningsanalys med ordernummer, sandningsnummer, Video-ID/langd/storlek, Analysera och nedladdning av video | [Meta-uppladdning](meta-upload.md) |
| Meta-uppladdning | `meta-upload.html` | Valj flera bilder/videor, visa vald videolangd nar metadata finns, automatisk uppladdning | [Meta-uppladdning](meta-upload.md) |

## Generella UI-regler

- Om en knapp ar dold beror det oftast pa vybehorighet.
- Om en knapp ar disabled beror det oftast pa read-only-lage, saknat underlag, pagaende korning eller tom undo/redo-stack.
- Om en andring inte sparas ska toast och Network/API-status avgora nasta felsokningssteg.
- Webben och Windows-appen ska ha samma anvandarbeteende. Om de skiljer sig, kontrollera desktop-proxyn och cachad frontend.

## Kodkallor

- `../app/frontend/js/common.js`
- `../app/frontend/js/api.js`
- `../app/frontend/*.html`

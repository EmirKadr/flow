---
title: flow wiki-index
status: aktiv
updated: 2026-07-03
tags: [wiki, index]
---

# flow wiki-index

Kort svar: flow ar en FastAPI/vanilla-JS webbapp och PyQt-baserad Windows-app for planering av flow, register, historik, produktivitet och lagerverktyg. Den har wikin ar agentens forsta stopp innan kodlasning.

## Starta har

- [Projektoversikt](overview.md) - vad produkten gor och vilka delar som finns.
- [Arkitektur](architecture.md) - webb, backend, databas, desktop och deployment.
- [Datamodell](data-model.md) - tabeller, relationer och viktiga invariants.
- [Roller och behorighet](auth-roles-access.md) - session, roller, vyatkomst och read-only.
- [UI-karta och alla kontroller](ui-map.md) - snabbkarta over knappar, menyer och generella UI-funktioner.
- [API-karta](api.md) - endpoints grupperade efter funktion.
- [Test och release](testing-release.md) - hur en agent verifierar andringar.
- [E2E-undersökningsverktyg](e2e-investigation.md) - `python -m tools.e2e` loggar in mot en körande miljö och kör scenarier (skärmbilder, konsol-/nätverksfelsfångst, DOM-inspektion) med agent-läsbar rapport.
- [Frontend-typning och lint](frontend-typing.md) - JSDoc + tsc --checkJs och ESLint utan byggsteg; utrullningsregler och domangranser.
- [Kallkodshantering och release (NoWaste)](nowaste-git-release.md) - branchmodell, Octopus-releaser (`release/*` bygger automatiskt) och deploy till development/production.
- [Prestandaoptimeringar - monster och revisionschecklista](prestanda-optimeringar.md) - kunskapsbas over prestandamonster vi tjanat sekunder/ms pa (ladda-och-reducera-i-Python, N+1, over-fetch, saknat index, pandas-loop, blocking-in-async, omrakning, compute-then-filter) med grep-signaturer for att svepa koden och uppmatta vinster med datum.
- [Prestanda - leveranslagret](prestanda-leveranslager.md) - gzip, versionsstamplade statiska filer med immutable-cache, ETag/304 pa API-GET, service worker, latensbudget och workers-beslutet.
- [Effektiviseringar - taxonomi over vara missar och losningar](effektivisering-taxonomi.md) - meta-nivan ovanfor prestandasidorna: 476 kartlagda andringar (86 uppmatta) klassade pa feltyp och losningstyp. Vilka missar vi ar benagna att gora (manuellt steg, omrakning, konfig-antagande, fel lager, inget tak, ingen matning) och vilka fem grepp som loser dem - plus varfor `guardrail` ar var vanligaste losningstyp.
- [Optimeringsplan - verifierad kandidatlista](optimeringsplan.md) - 52 kodkandidater, var och en granskad av en egen skeptiker: **20 bekraftade, 17 osakra, 15 avfardade**. Plus 49 omvarldstekniker (35 tillampliga, 11 avfardade). Innehaller uppmatta vinster (`fifo_for_art` 1,63 s -> 0,02 s; HIB 3,3 s -> 0,5 s), forkravskedjor (startupProbe maste komma fore alla uppstartsfixar; gzip fore orjson) och en avfardad-lista med skal. Inget byggt an. **Kalla pa den med `/optimering`.**
- [Optimeringsplan - detaljbilaga](optimeringsplan-detalj.md) - fullstandig radata: varje kandidats hela skeptikergranskning, justerade vinst, exakta matning och forutsattningar, plus alla 49 omvarldstekniker i fulltext. Slå upp den post du ska bygga - las inte hela filen.
- [Begrepp och agentordlista](terminology.md) - namngivna produktbegrepp som
  ska tolkas konsekvent i framtida chattar.
- [Schemahistorikens mutabilitet](schema-historik-mutabilitet.md) - skeptikergranskad analys (2026-07-21) av att historiska schemadagar var en live-projektion som skrevs om av register-/malländringar — plus losningen: schemafrysningen (`schedule_freeze`) som materialiserar gardagens malltimmar till explicita celler vid dygnsskiftet och gor att raderingar bara rensar framtiden. Byggd 2026-07-21 pa `feature/historik-frys`.

## Funktionssidor

- [Bemanning](bemanning-schedule.md) - matrisen, celler, split, drag, kopiera, rensa, undo/redo och kalkyl.
- [RFID-stamplingar](rfid.md) - fysisk ESP32/RDM6300-scan till Bemanning, OK/Ignorera och dubblettregler.
- [Oversikt](overview-page.md) - vecka/manad, heldagsbemanning, drag och undo/redo.
- [Personer](persons.md) - personregister, inline-edit, import och veckomall.
- [Aktiviteter och omraden](activities-areas.md) - aktivitetsregister, kod, summering och legacy-stalle.
- [Anvandare och installningar](users-settings.md) - anvandare, verksamheter, roller, vybehorigheter, meny och cell-las.
- [Verksamheter och isolering](businesses.md) - Stigamo/R3-scope, Super User, toggles och testkontrakt.
- [Demo-läge](demo-mode.md) - Demo-konto med privat sandbox-DB och guidad rundtur för säljpresentationer.
- [Historik och audit](history-audit.md) - filter, statistik, auditlogg, felkoder, vantetider och Halsa.
- [Hämta data](data-fetch.md) - MiniMax-tolkad extern data-export med publicerbar katalog och Excel-export.
- [MCP](mcp.md) - fråga/svar-vy där backend hämtar tenant-baserad Noeffect-MCP-kontext och vald LLM-hjärna svarar.
- [Etiketter](label-editor.md) - experimentell lokal label editor för QR, Code128, text, former, symboler och utskrift.
- [Dubbletter](dubbletter.md) - klientsidigt verktyg som gör Excels "Ta bort dubbletter" på inklistrade värden, med jämförelseregler och kolumnval.
- [ASK datalagring](ask-datalagring.md) - hur länge ASK/WMan-tabeller behålls (rensning vs arkivering) och vad det betyder för historisk data per vy.
- [Lokal arkiv-cache (DuckDB)](local-archive-cache.md) - per-tenant DuckDB som speglar dblog_*-arkiven så Sankey/Produktivitet/Hämta data läser historik från disk (lokalt och deployat sedan 2026-07-04, dblog kvar som fallback); inkl. förbyggd `overview-report`-cache för Produktivitets periodöversikt.
- [ASK statuskoder](ask-statuskoder.md) - hur `status`, `type` och andra kodvarden i ASK/Nowaste-vyer ska forklaras och anvandas i Hamta data, pallspårning och framtida chat.
- [Meta-uppladdning](meta-upload.md) - publik fristaende mobilvy for att ladda upp bilder och videor till senare LLM-analys.
- [Buggrapporter](bug-reports.md) - (experiment, beslut 2026-08-07) Bugg-knappen i sidebar-footern: 30 s DOM-inspelning (rrweb) som behöriga spelar upp i vyn Buggrapporter.
- [Produktivitet](productivity.md) - global API-snapshot, periodtrad, personaktivitetssnitt och vanliga stopp; dagens dag forbyggs for alla aktiva bolag varje 30-min-pass (on-demand kvar som matbar fallback).
- [Sankey - Inbound](sankey-inbound.md) - bolagsindelat Sankeydiagram som foljer inbound-intakt fran mottagna etiketter till plock/oppna floden.
- [Lagerverktyg](warehouse-tools.md) - Uppladdningar, Bearbeta, Dela och allokeringsfloden.

## Chat- och felsokningsstod

- [Anvandarhandbok](user-guide.md) - hur man anvander programmet roll for roll och vy for vy.
- [Anvandarhandelser](user-events.md) - allt anvandaren kan se: laddning, tomma lagen, disabled knappar, confirm, toastar och redirect.
- [Felkoder och felmeddelanden](error-reference.md) - HTTP-koder, vanliga serverfel, klientfel och vad de betyder.
- [Apphjalp och LLM-chatt](app-chat.md) - pratbubbelknappen, sessionsdialog, 10-fragorsgrans och MiniMax-konfiguration.
- [Apphjalpens tools](assistant-tools.md) - read-only function calling i chatten: live-data for schema, personer, produktivitet, Historik m.m. med verksamhetsscope och behorighetsmetadata.
- [Felsokning och framtida LLM-chat](troubleshooting-chat.md) - fragor/svar och symptom till rotorsak.
- [Kallmanifest](sources.md) - vilka filer som anvandes nar wikin skapades.
- [Logg](log.md) - append-only historik over wikiarbete.

## Funktionslivscykel

Varje funktionssidas `status`-falt i frontmattern ar funktionens livscykelbeslut,
inte bara wikisidans status. Tillatna varden:

- `aktiv` - fullt underhallen, paritetsregeln galler fullt ut.
- `experiment` - under utprovning, normalt bara synlig for Super User eller
  pilotanvandare. Ska fa ett beslutsdatum i sidan: slappa eller slanga.
- `frys` - buggfixar men inga nya features. Nya onskemal ska ifragasattas.
- `avveckla` - pa vag bort. Inga andringar utom borttagning; notera ersattare.

Nar en funktions status andras ska sidan, denna lista och `log.md` uppdateras
i samma arbete. Experiment som statt stilla lange ska lyftas till Emir for
beslut i stallet for att ligga kvar tyst.

## Underhallsregel

Las [Wiki-agentregler](AGENTS.md) innan du uppdaterar wikin. Nar kod eller produktbeteende andras ska relevanta sidor och `log.md` uppdateras i samma arbete.

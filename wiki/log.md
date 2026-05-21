---
title: Wiki-logg
status: aktiv
updated: 2026-05-21
tags: [wiki, logg]
---

# Wiki-logg

## [2026-05-21] ingest | Initial projektwiki

Skapade forsta LLM-wikin for Bemanningsfil enligt Karpathy-modellen: index, agentregler, kallmanifest, arkitektur, datamodell, rollmodell, API-karta, UI- och funktionssidor samt felsokningssida for framtida LLM-chat.

Kallor som lastes: `AGENTS.md`, `app/README.md`, `API_ROUTES.md`, `APP_MIGRATION_PLAN.md`, `TESTPROTOCOL.md`, frontend-HTML, frontend-JS, backend-routers, datamodeller, lagerverktygskatalog och produktivitetsservice. Karpathy-gisten anvandes som strukturmonster for persistent wiki, index och logg.

## [2026-05-21] expand | Anvandarhandbok, handelser och felkoder

Lade till `user-guide.md`, `user-events.md` och `error-reference.md` med mer detaljer om hur programmet anvands, vad anvandaren kan se i olika lagen, vanliga toastar/confirm-dialoger, HTTP-statuskoder och backendens viktigaste felmeddelanden. Uppdaterade `index.md` och `troubleshooting-chat.md` sa framtida LLM-chat hittar materialet.

## [2026-05-21] feature | Apphjalp och MiniMax-chatt

Dokumenterade den nya pratbubbelknappen under omradesfokus/infinity, sessionssparad dialog, 10-fragorsgrans, `Rensa dialog`, MiniMax-konfiguration och nya API-vagar i `app-chat.md`. Uppdaterade index, UI-karta, API-karta, anvandarhandelser, felreferens och felsokningssidan sa framtida LLM-chat kan forklara hur apphjalpen fungerar och varfor den kan stoppa.

## [2026-05-21] polish | Chattformat i smal panel

Uppdaterade apphjalpens prompt och frontendrendering sa svaren passar den lilla dialogrutan battre. Modellen instrueras att undvika markdown-tabeller och skriva korta block/listor; frontend renderar enklare Markdown som rubriker, fetstil, kod, listor och tabeller snyggare om det anda kommer.

## [2026-05-21] polish | Chattikon och laddning

Justerade apphjalpens pratbubbel-SVG sa den inte klipps i sidebarens 40px-knapp och lade till en rund spinner i chattflodet medan API-svar hamtas.

## [2026-05-21] policy | Hardare chattsanning och repo-sok

Skarpte apphjalpens prompt: wikin ar normalfragornas grans, sa om wikin inte sager att en funktion finns ska chatten svara nej/inte dokumenterat i stallet for att spekulera. Lade till repo-sok-kontext nar anvandaren invander eller ber chatten kolla koden, samt instruktion om korrekt svenska med `å`, `ä` och `ö`.

## [2026-05-21] fix | Tydligare SQLite-lås vid lokal start

Uppdaterade lokal databasforberedelse sa `PermissionError` vid ersattning av `app/bemanning_local.db` blir ett tydligt meddelande om gammal `start_local.bat`/`uvicorn` i stallet for en lang Python-traceback. Dokumenterade handelsen i `user-events.md`.

## [2026-05-21] polish | Behorighetsrad och chattraknare

Fortydligade att `Vybehorigheter`, rollandringar och Super User-kontroller kraver admin-/Super User-atkomst och inte ska beskrivas som sjalvservice for vanliga anvandare. Dokumenterade ocksa att apphjalpens `x/10`-raknare visar anvanda fragor i hela aktuell server-/browser-session, inte bara fragorna som syns i panelen.

## [2026-05-21] fix | Rensa apphjalp vid logout

Frontend rensar nu apphjalpens lokala `sessionStorage` vid logout, inklusive dialog, utkast, oppet lage och lokal frageraknare. Detta matchar backendens `request.session.clear()` sa ny inloggning inte visar gammal lokal `6/10`-raknare. Lokal chattdata har ocksa en versionsnyckel sa gammal sessiondata fran tidigare implementation rensas automatiskt vid nasta sidladdning.

## [2026-05-21] feature | Anvandarkontext i apphjalpen

Apphjalpens backend skickar nu begransad supportkontext om inloggad anvandare till MiniMax: visningsnamn, anvandarnamn, roller, Super User-status, omrade och effektiva vybehorigheter per vy. Syftet ar att chatten ska kunna saga exakt om anvandaren saknar `Harleda`, bara har `view` eller saknar `Bearbeta`. Känslig information som losenord, hashes, sessioncookies, tokens och API-nycklar skickas inte.

## [2026-05-21] feature | Hamta data via extern datakalla och MiniMax

Lade till `Hamta data` som skyddad vy och API-flode for promptstyrd extern dataexport. MiniMax far bara vy-/kolumnkatalog och planformat; URL, endpointmall, headernamn, API-nycklar och klientnycklar ligger i servermiljon. Dokumenterade `data-fetch.md`, nya API-vagar, vybehorigheten `dataFetch`, katalogbyggnad och Excel-export.

## [2026-05-21] hardening | Gommer privata dataflodets leverantorsdetaljer

Bytte Hämta data-flodet till generiska `DATA_SOURCE_*`-miljovariabler, neutral API-route `/api/query-data`, generisk klient `external_data_client.py` och katalogfil `data/external_data_catalog.json`. Endpointmall och headernamn ligger nu i env i stallet for kod/wiki, och dokumentationen beskriver bara extern datakalla.

## [2026-05-21] fix | Spärrar Hämta data utan konfiguration

Hämta data-health returnerar nu status utan att kasta 503 nar katalog/env saknas. Frontend spärrar `Tolka med MiniMax` och `Hämta data` tills katalog, MiniMax och extern API-konfiguration finns, sa saknad katalog inte kan skapa AI-usage eller en missvisande arbetsyta.

## [2026-05-21] config | Publicerar Hämta data-katalogen

Katalogen `data/external_data_catalog.json` bedomdes inte vara hemlig och ska commitas sa Render har vy-/kolumnstruktur direkt. API-nycklar, URL:er, headernamn och endpointmallar stannar fortsatt i `.env`/Render secrets.

## [2026-05-21] support | Stoppa lokal server

Lade till `stop_local.bat` for att stanga gamla lokala `start_local.bat`/uvicorn-processer och frigora port `8000` nar `app/bemanning_local.db` ar last. Uppdaterade README och anvandarhandelser med kommandot.

---
title: Wiki-agentregler
status: aktiv
updated: 2026-05-21
tags: [wiki, agent, arbetsflode]
---

# Wiki-agentregler

Denna mapp ar en LLM-underhallen projektwiki enligt Karpathy-modellen for en persistent wiki: kod, befintliga markdownfiler och dataunderlag ar kallor; `wiki/` ar den sammanstallda kunskapen som en agent ska lasa forst och underhalla nar projektet andras.

## Lasordning for agenter

1. Las `../AGENTS.md` for repo-reglerna om strikt paritet mellan `app/` och `desktop/`.
2. Las `index.md` for att hitta ratt wiki-sidor.
3. Las relevanta wiki-sidor innan du laser kod.
4. Las koden som kallas ut under "Kallor" pa respektive sida innan du andrar beteende.
5. Om uppgiften ror CSV/XLS/XLSX eller lagerunderlag: las `../ALLOKERING_FILKUNSKAP.md` i workspace-roten innan du antar kolumner.

## Sanning och kallprioritet

1. Kod och migrationsfiler ar hogsta sanning for faktiskt beteende.
2. Befintliga projektdokument som `app/README.md`, `API_ROUTES.md`, `APP_MIGRATION_PLAN.md` och `TESTPROTOCOL.md` ar design- och testkontrakt.
3. Wiki-sidorna ar en syntes. Om wiki och kod motsager varandra ska du lita pa kod, uppdatera wikin och notera det i `log.md`.

## Nar wikin ska uppdateras

Uppdatera wikin nar du:

- lagger till, tar bort eller andrar en knapp, meny, modal, vy eller tangentbordsgenvag
- andrar API-kontrakt, behorigheter, roller eller settings
- andrar bemanningslogik, veckomallar, oversikt, produktivitet eller lagerverktyg
- lagger till nya felmeddelanden, toastar eller konfliktfall
- upptacker att dokumentationen ar fel eller for vag

Nar du lagger till eller andrar ett Bearbeta-flode ska du ocksa uppdatera
`warehouse-tools.md`, `testing-release.md` och `log.md`. Dokumentera vilka
lokala filer, karnfiler, sessioner/artifacts och knappar som kravs, samt hur en
anvandare ser att flodet ar redo eller blockerat.

For Bearbeta-floden med beroenden mellan knappar, till exempel Forecast som
maste koras fore Ytgenerering, ska wikin beskriva bade anvandarflodet och
sessionkontraktet. Testerna ska tacka minst ett backend-/kontraktstest och ett
anvandarnara test som verifierar knappens enabled/disabled-lage eller inskickad
session-parameter.

Varje uppdatering ska ocksa laggas append-only i `log.md` med formatet:

`## [YYYY-MM-DD] typ | kort titel`

## Sidformat

Nya eller uppdaterade sidor ska helst ha:

- kort frontmatter med `title`, `status`, `updated`, `tags`
- "Kort svar" for snabb agentorientering
- "Anvandarflode" om sidan har UI
- "Knappar och kontroller" med tabell: kontroll, var, vem far, vad hander, API/kod, vanliga fel
- "Tekniskt flode" for API, databas och viktig JS/backend-kod
- "Felsokningssvar for framtida chat" med konkreta anvandarfragor och svar
- "Kallor" med relativa filvagar till kod/dokument

## Viktigt for framtida LLM-chat

Wikin ska vara skriven sa att en senare chattfunktion kan svara anvandare pa fragor som:

- Varfor kan jag inte klicka pa detta?
- Varfor sparades inte min andring?
- Vad betyder den har varningen?
- Hur gor jag for att importera, kopiera, rensa, andra roll eller valja filer?
- Varfor syns inte en vy i menyn?
- Varfor skiljer webben och Windows-appen sig?

Skriv darfor alltid beteende i anvandartermer forst och teknisk detalj efterat.

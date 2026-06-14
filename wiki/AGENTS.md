---
title: Wiki-agentregler
status: aktiv
updated: 2026-06-14
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

Nar uppgiften ror API-/CSV-kolumner ska tekniskt katalog-id kontrolleras fore
svenska eller engelska labels. Labels ar presentation eller legacy-CSV-rubrik;
om en gammal motor kraver en rubrik ska mappningen fran tekniskt id till rubrik
dokumenteras explicit i kod och wiki.

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
- andrar anvandarsynlig loggning, bakgrundsladdning, cache eller auditbeteende
- andrar Halsa, Vantetider, driftkontroller eller `tools.healthcheck`
- upptacker att dokumentationen ar fel eller for vag

Nar en andring ror interaction-tracking ska wikin beskriva bade vad som trackas
och vad som inte far sparas. Klartext-vardeprov ar bara tillatet for uttryckligt
trackade anvandarinteraktioner och bara nar backend-flaggan
`TRACKING_ALLOW_VALUE_SAMPLES=true` ar satt. Losenord, cookies, tokens,
API-nycklar, privata URL:er, filnamn, filvagar, request bodies och
provider-detaljer far aldrig sparas som trackingpayload.

Nar du lagger till eller andrar ett Bearbeta-flode ska du ocksa uppdatera
`warehouse-tools.md`, `testing-release.md` och `log.md`. Dokumentera vilka
lokala filer, karnfiler, sessioner/artifacts och knappar som kravs, samt hur en
anvandare ser att flodet ar redo eller blockerat.

For Bearbeta-floden med beroenden mellan knappar, till exempel Forecast som
maste koras fore Ytgenerering, ska wikin beskriva bade anvandarflodet och
sessionkontraktet. Testerna ska tacka minst ett backend-/kontraktstest och ett
anvandarnara test som verifierar knappens enabled/disabled-lage eller inskickad
session-parameter.

Halsa och Vantetider ar en del av arbetsmetoden. Nar en agent andrar drift,
databas, Render, cache, bakgrundsladdning, import/export, Bearbeta-floden eller
releasefiler ska `AGENTS.md`, `TESTPROTOCOL.md` och `testing-release.md` hallas
i synk om healthcheck-regeln paverkas. Efter storre push/deploy ska agenten
normalt kora eller verifiera `tools.healthcheck report` och
`tools.healthcheck waits`. Kvarvarande `warn`/`error` ska dokumenteras i
slutrapporten om det inte kan fixas direkt.

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
Nar ett flode loggar nagot ska wikin beskriva vad anvandaren ser i dokumentloggen
och vad som hamnar i Historik/audit, sa framtida chattar kan skilja pa snabb
sessionfeedback och sparad felsokningshistorik.

Nar en ny anvandarsynlig handelse, integration, fysisk enhet eller
bakgrundshandelse laggs till ska wikin ocksa beskriva dess Historik/Analys-spar:
vilken `audit_log.entity_type` och `action` som skrivs, vilken anvandarlabel den
far, vilka detaljer som ar sanerade och vilka tester som bevisar att raden syns
begripligt. Om en handelse kan fastna fore backend ska felsokningssvaret
beskriva den observerbara signal som skiljer hardvara/natverk fran appfel.

Nar ett nytt flode skapar, andrar, synkar eller tar emot data ska audit och
Historik/Analys-labels beskrivas som obligatoriska delar av beteendet, inte som
extra dokumentation. Wikin ska namna vilken sparad auditrad som skapas, hur
labeln/summaryn ser ut for anvandaren och vilket test som skyddar kedjan. Om
flodet ar read-only och medvetet saknar audit ska den avvikelsen namnas
uttryckligt.

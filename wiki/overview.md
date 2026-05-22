---
title: Projektoversikt
status: aktiv
updated: 2026-05-22
tags: [produkt, oversikt]
---

# Projektoversikt

Kort svar: flow ersatter en Excel-bemanningsfil med en gemensam webbapp och Windows-app. Arbetsledare planerar personer mot aktiviteter per dag/timme, admin hanterar register och roller, super users kan se historik och produktivitet, och lagerroller kan anvanda lokala lagerverktyg.

## Produktens huvuddelar

- Bemanning: dagsmatris med personer som rader och timmar 06-23 som kolumner. Celler sparas automatiskt.
- Oversikt: vecka/manad per person dar hela dagar kan bemannas enligt personens veckomall.
- Personer: register med hemomrade, huvudaktivitet, sortering och veckomall.
- Aktiviteter: register over bemanningsaktiviteter, farger, omraden, kategori och summeringsaktivitet.
- Anvandare: roller, omrade, aktiv/inaktiv, forsta losenord, vybehorigheter och settings.
- Historik: auditlogg, enkel analytics och felkodsdashboard over anvandartraffade API-fel.
- Hamta data: promptstyrd extern data-export via MiniMax-planering, backendvalidering och Excel-export.
- Produktivitet: lokal analys av stora WMS-loggar mot centrala KPI-mal.
- Lagerverktyg: uppladdning, allokering/orderkontroller och dela varden.

## Viktiga produktprinciper

- Webb och Windows ar samma produkt. En beteendeforandring i `app/` maste bedomas mot `desktop/`.
- Databasen ar den centrala sanningen for anvandare, roller, schema, personer, aktiviteter, historik, settings och KPI-mal.
- Stora produktivitetsloggar ar lokala i klienten for att undvika tunga serveruppladdningar.
- Schemaceller har versioner for att upptacka samtidiga andringar.
- Soft delete anvands for personer, aktiviteter och anvandare: de inaktiveras, inte tas fysiskt bort.

## Mental modell for agenten

Tanka appen som tre lager:

1. UI-lager: statiska HTML-sidor och vanilla JS i `app/frontend`.
2. API-lager: FastAPI-routers i `app/backend/routers`.
3. Data-/domanlager: SQLAlchemy-modeller, services, lagerverktygsbrygga och lokala IndexedDB-filval.

Nar en anvandare sager "knappen funkar inte" ska agenten forst hitta vyn i [UI-karta och alla kontroller](ui-map.md), sedan lasa funktionssidan och sist verifiera aktuell JS/API-kod.

## Kallor

- `../app/README.md`
- `../AGENTS.md`
- `../APP_MIGRATION_PLAN.md`
- `../app/frontend/js/common.js`

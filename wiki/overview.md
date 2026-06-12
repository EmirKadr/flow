---
title: Projektoversikt
status: aktiv
updated: 2026-06-08
tags: [produkt, oversikt]
---

# Projektoversikt

Kort svar: flow ersatter en Excel-bemanningsfil med en gemensam webbapp och Windows-app. Arbetsledare planerar personer mot aktiviteter per dag/timme, admin hanterar register och roller, Super User kan se historik och verksamheter, Produktivitet styrs via vybehorigheter och lagerroller kan anvanda lokala lagerverktyg.

## Produktens huvuddelar

- Bemanning: dagsmatris med personer som rader och timmar 06-23 som kolumner. Celler sparas automatiskt.
- Oversikt: vecka/manad per person dar hela dagar kan bemannas enligt personens veckomall.
- Personer: register med hemomrade, huvudaktivitet, sortering och veckomall.
- Aktiviteter: register over bemanningsaktiviteter, farger, omraden, kategori och summeringsaktivitet.
- Anvandare: roller, omrade, forsta losenord, vybehorigheter, settings och borttagning.
- Historik: auditlogg, enkel analytics och felkodsdashboard over anvandartraffade API-fel.
- Hamta data: promptstyrd extern data-export via MiniMax-planering, backendvalidering och Excel-export.
- Produktivitet: personbaserad dags-KPI fran schema, KPI-mal och serverns API-snapshot.
- Lagerverktyg: uppladdning, allokering/orderkontroller och dela varden.

## Viktiga produktprinciper

- Webb och Windows ar samma produkt. En beteendeforandring i `app/` maste bedomas mot `desktop/`.
- Databasen ar den centrala sanningen for anvandare, roller, schema, personer, aktiviteter, historik, settings och KPI-mal.
- Produktivitetens rapport byggs centralt fran dagens API-snapshot nar extern datakalla finns; lokala filer finns kvar som fallback/filhantering.
- Schemaceller har versioner for att upptacka samtidiga andringar.
- Personer, aktiviteter och anvandare tas bort via delete-floden; anvandare som finns kvar ar alltid aktiva.

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

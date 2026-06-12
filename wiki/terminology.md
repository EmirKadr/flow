---
title: Begrepp och agentordlista
status: aktiv
updated: 2026-06-10
tags: [begrepp, agent, ui, filter]
---

# Begrepp och agentordlista

Kort svar: den har sidan namnger produktbegrepp som Emir kan anvanda i chatten
och som en agent ska tolka konsekvent i kod, UI och dokumentation.

## Avancerad filfiltrering

`Avancerad filfiltrering` betyder Bearbetas befintliga filterdialog fran
edit-ikonen pa varje Bearbeta-funktion, inte en enkel hardkodad filterrad.

Nar Emir ber om `Avancerad filfiltrering` pa nya filer eller underlag ska
agenten ateranvanda samma koncept som i Bearbeta:

- per funktion/flode och per fil, coredata eller API-kalla
- val mellan `API` och `Uppladdning` for API-first-kallor
- flera filtervillkor med kolumn, operator och varde
- personlig sparning per anvandare
- mojlighet att hamta/kopiera annan anvandares sparade filterprofil
- filtrering pa temporara kopior efter API-first/fallback, utan att skriva om
  originalfilen i cache, IndexedDB eller lokal disk
- sanerad logg/audit som sparar radantal och antal villkor, inte privata
  filtervarden eller raddata

Kodkontraktet i nuvarande Bearbeta-implementation ar:

- frontendmodal: `openAllocationFlowFilterModal`
- huvud-CSS: `.allocation-filter-modal`
- profilparameter vid korning: `__allocation_user_filters_json`
- profil-API: `GET/PUT /api/allokering/filter-profile`
- import-API: `POST /api/allokering/filter-profile/import`
- backendapplicering: `allocation_bridge.apply_user_flow_filters`

Om samma begrepp ska anvandas i Bemanningskalkylens automatiska underlag ska
det alltsa betyda att kalkylens filer/API-kallor far motsvarande dialog och
personliga profiler, inte bara dagens fasta falt for Bolag, Zon och Plockdagar.

## Kallor

- `warehouse-tools.md`
- `bemanning-schedule.md`
- `../app/frontend/js/allocation_tools.js`
- `../app/frontend/css/styles.css`
- `../app/backend/allocation_bridge.py`

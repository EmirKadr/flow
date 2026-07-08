---
title: E2E-undersökningsverktyg (tools/e2e)
status: aktiv
updated: 2026-07-07
tags: [verktyg, e2e, playwright, undersokning, agent, felsokning]
---

# E2E-undersökningsverktyg: `python -m tools.e2e`

Kort svar: `tools/e2e/` är ett browser-baserat undersökningsverktyg som loggar
in mot en **körande** Flow-miljö (development/production/lokal) och kör namngivna
scenarier — skärmbilder, konsol- och nätverksfelsfångst, DOM-inspektion och
assertions — och skriver en **agent-läsbar rapport** (`report.md` + `report.json`).
Tanken: en agent kan verifiera att UI:t faktiskt fungerar live, inte bara att
testerna är gröna. Skapat 2026-07-07 efter release 2026.28.7.

## Snabbstart

1. Fyll i inloggning i `app/.env` (gitignorerad — committas aldrig):
   ```
   FLOW_E2E_BASE_URL=https://flow-development.nowastelogistics.com
   FLOW_E2E_USERNAME=<en Super User för att se allt>
   FLOW_E2E_PASSWORD=<lösenord>
   ```
2. Kör ett scenario:
   ```
   python -m tools.e2e --list                 # lista scenarier
   python -m tools.e2e smoke                   # nya funktionerna + skärmbilder
   python -m tools.e2e inspect --page /overblick.html
   python -m tools.e2e sweep                   # hälsosvep över standarduppsättning sidor
   python -m tools.e2e sweep --pages index.html,personer.html
   python -m tools.e2e business-filter --headed
   python -m tools.e2e sweep --base-url https://flow.nowastelogistics.com
   ```
3. Resultatet hamnar i `artifacts/e2e/<scenario>/` (gitignorerad): PNG-skärmbilder
   + `report.md` (läs den) + `report.json`. Agenten läser PNG:erna och rapporten
   för att verifiera visuellt och hitta konsol-/nätverksfel.

## Scenarier

| Scenario | Vad det gör |
| --- | --- |
| `smoke` | Loggar in, går igenom de nya funktionerna (fokustogglar, Buggrapporter Ta bort/status, Vybehörigheter) med skärmbilder och assertions. |
| `inspect` | Inspekterar EN sida (`--page /x.html`): skärmbild, konsolfel, nätverksfel, timing och ett textutdrag agenten kan läsa. Den generella "undersök vad som helst". |
| `sweep` | Hälsosvep över flera sidor (`--pages` eller standarduppsättningen): konsolfel, nätverksfel och laddtid per sida. Bra för att hitta trasiga vyer app-brett. |
| `bug-reports` | Fördjupning i Buggrapporter-vyn: lista, status-dropdown, detaljpanel. |
| `role-access` | Vybehörigheter-panelen under Inställningar (roll × vy-matris). |
| `business-filter` | Verksamhetsfiltret vid ∞ områden: fotar personlistan före/efter verksamhetsbyte. |

## Arkitektur

- `tools/e2e/env.py` — läser `FLOW_E2E_*` ur `.env`/`app/.env` (hoppar över tomma
  värden så placeholders inte skuggar ifyllda; riktiga miljövariabler vinner).
  `Credentials.redacted()` läcker aldrig lösenordet.
- `tools/e2e/session.py` — `FlowSession` wrappar en Playwright-sida: `login`,
  `goto` (med timing), `screenshot` (hel sida eller element), interaktioner
  (`click/fill/select/hover/press`), läsning (`exists/count/text/page_text`) och
  löpande fångst av konsolmeddelanden + misslyckade nätverkssvar (4xx/5xx/failed),
  som kan "dräneras" per sida.
- `tools/e2e/report.py` — `Report` samlar skärmbilder, konsol, nätverk, timing,
  assertions och fynd och skriver `report.md` + `report.json`.
- `tools/e2e/scenarios.py` — `SCENARIOS`-registret + `capture_page`-hjälparen.
  Nya scenarier läggs till här och plockas upp av CLI:t automatiskt.
- `tools/e2e/__main__.py` — CLI. Sätter stdout till UTF-8 (Windows-konsolen är
  cp1252 och kraschar annars på åäö/∞).
- `tools/e2e_screenshots.py` — bakåtkompatibel genväg som kör `smoke`.

## Skriva egna scenarier

Lägg en funktion `(session, report, args)` i `scenarios.py` och registrera den i
`SCENARIOS`. Använd `capture_page(session, report, path, name)` för grund
(timing + konsol + nätverk + skärmbild), och `report.add_assertion(...)` /
`report.add_finding(...)` för slutsatser. Se `scenario_smoke` som mall.

## Säkerhet och gränser

- Lösenordet läses bara ur `app/.env` vid körning och loggas/committas aldrig.
  `.env`/`app/.env` och `artifacts/` är gitignorerade.
- Verktyget kör read-only-undersökningar; det ska inte trigga destruktiva
  åtgärder. Buggrapport-scenariot öppnar bara consent-popupen, aldrig en
  inspelning, och tar aldrig bort rapporter.
- Playwright (`requirements-dev.txt`, `playwright install chromium`) krävs.
- Non-browser-logiken (env, rapport, registry, CLI-vägar) täcks av
  `tests/tools/test_e2e_investigation.py`; själva browserflödena verifieras
  genom att köra scenarierna mot en miljö.

## Källor

- `../tools/e2e/` (env, session, report, scenarios, __main__)
- `../tests/tools/test_e2e_investigation.py`

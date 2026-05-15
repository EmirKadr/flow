# Testprotokoll

Det har protokollet beskriver hur en agent ska testa Bemanning efter andringar.
Appen finns i tva klienter som ska hallas i paritet:

- `app/` ar webbappen.
- `desktop/` ar Windows-appen som visar samma webbapp i ett PyQt-skal.

## Grundregel

Varje andring som paverkar anvandarupplevelsen ska testas i bade webbappen och
Windows-appen. Webbscreenshots granskar sjalva produktvyerna. Desktop-screenshots
granskar Windows-skalet runt webbappen.

## Snabbtest

Kor detta fore commit nar andringen inte ar rent dokumentar:

```powershell
python -m pytest
Get-ChildItem -Path app\frontend\js -Filter *.js | ForEach-Object { node --check $_.FullName }
python desktop\main.py --smoke-test
```

For release eller desktop-andringar:

```powershell
cmd /c build_windows.bat
```

## Automatiska tester som finns

- `tests/services/` testar backendregler, roller, import, schema, mallar,
  updater och public API.
- `tests/desktop/test_app.py` testar Windows-skalets health check,
  fellage och uppdateringsflode.
- `tests/tools/test_visual_tools.py` testar att visuella verktyg fortfarande
  tacker viktiga vyer och att ikon-/manifest-assets finns pa alla HTML-sidor.

## Visuellt webbscreeningverktyg

Verktyg:

```powershell
python -m tools.visual_smoke
```

Det gor detta:

1. Skapar en temporar SQLite-databas under `artifacts/visual/<timestamp>/`.
2. Kor lokal schema/bootstrap och `tools.visual_data`.
3. Startar en lokal FastAPI-server pa ledig port.
4. Loggar in som testroller.
5. Tar screenshots i desktop- och mobilstorlek.
6. Skriver `summary.json` med alla filer som skapades.

Forsta gangen pa en ny maskin kan Playwright behova installeras:

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
```

Vanliga varianter:

```powershell
python -m tools.visual_smoke --roles public,admin
python -m tools.visual_smoke --base-url http://127.0.0.1:8000 --roles admin
python -m tools.visual_smoke --output artifacts\visual\manual-check
```

Bas-screenshots som ska granskas:

- Login.
- Bemanning i admin-, arbetsledar- och visningsroll.
- Oversikt i admin-, arbetsledar- och visningsroll.
- Personer.
- Stallen.
- Historik.
- Anvandare.

Scenario-screenshots som ska granskas:

- Bemanning med Alla avdelningar.
- Bemanning med Mestergruppen.
- Bemanning med Autostore.
- Bemanning med tomt personfilter.
- Kopiera dag-modal.
- Bemanningskalkyl med Alla.
- Kompakt/sidebar-collapse.
- Oversikt med Mestergruppen.
- Oversikt i manadslage.
- Oversikt i manadslage med Mestergruppen.
- Oversikt med tomt personfilter.
- Veckomall-modal.
- Ny person-modal.
- Ny aktivitet-modal.
- Redigera aktivitet-modal.
- Ny anvandare-modal.
- Redigera anvandare-modal.
- Historik med filter.
- Nekad atkomst for visningsroll till Personer, Stallen, Anvandare och Historik.
- Nekad atkomst for arbetsledare till Anvandare och Historik.

Granska visuellt att:

- Text inte kapas eller overlappar.
- Sidebar, kontroller och tabeller ligger ratt i desktop och mobil.
- Rollerna visar ratt navigation och ratt vyer.
- Otillgangliga sidor skickar anvandaren till Bemanning och visar feltoast.
- Farger, halvceller, schemalagda/lediga celler och kalkyl syns begripligt.
- Modaler far plats och har fungerande primar/sekundar-knappar.

## Interaktivt E2E-verktyg for webben

Verktyg:

```powershell
python -m tools.interactive_e2e
```

Det har ar verktyget som en agent ska anvanda nar den behover testa att det gar
att klicka runt och faktiskt gora saker i appen. Det skapar en temporar databas,
startar en lokal server, kor Playwright och sparar screenshots + `report.json`
under `artifacts/interactive/<timestamp>/`.

Det testar bland annat:

- Logga in som admin.
- Skapa och redigera anvandare, inklusive roll och avdelning.
- Skapa och redigera stalle/aktivitet.
- Skapa person, redigera namn inline och andra veckomall.
- Andra bemanningscell, dela halvcell och kopiera/klistra in cell.
- Kopiera dag, rensa dag, angra och gor om.
- Andra i Oversikt och byta till manadsvy.
- Filtrera Historik.
- Logga in som visningsroll och verifiera att den ar read-only.
- Verifiera att visningsroll och arbetsledare stoppas fran otillatna sidor.

Vanliga varianter:

```powershell
python -m tools.interactive_e2e --headful
python -m tools.interactive_e2e --base-url http://127.0.0.1:8000 --output artifacts\interactive\manual
```

Nar verktyget faller ska agenten oppna screenshoten narmast felet och lasa
`report.json` for att se sista lyckade steg.

## Visuella Windows-skalbilder

Verktyg:

```powershell
python -m tools.desktop_shell_screens
```

Det skapar screenshots under `artifacts/desktop-shell/`:

- `desktop-loading.png`
- `desktop-error.png`
- `desktop-loaded-shell.png`

De bilderna visar desktop-specifika tillstand. Sjalva bemanningsvyerna testas
med `tools.visual_smoke`, eftersom Windows-appen visar samma webbyta.

## Desktop-app-probe

Verktyg:

```powershell
python -m tools.desktop_app_probe
```

Detta testar Windows-appens PyQt-skal mot en riktig lokal testserver utan att
krava att Qt WebEngine kan rendera i en headless agent-session. Det verifierar
att desktop-skalet:

- visar laddning
- visar anslutningsfel
- laddar den konfigurerade webbappen nar servern ar frisk
- sparar `report.json` och screenshots under `artifacts/desktop-app/<timestamp>/`

Pa en maskin dar Qt WebEngine kan rendera kan agenten aven kora:

```powershell
python -m tools.desktop_app_probe --real-webengine
```

Om `--real-webengine` misslyckas i en agentmiljo ska det rapporteras tydligt,
men det blockerar inte de vanliga webbarbetsflodena. Anvand da:

1. `python -m tools.interactive_e2e` for alla webbfloden.
2. `python -m tools.desktop_app_probe` for Windows-skalet.
3. En manuell Windows-korning om felet specifikt verkar handla om WebEngine.

## Testdata for visuella tester

`tools.visual_data` lagger in:

- admin, arbetsledare och visningsroll
- personer i flera avdelningar
- veckomallar med ledig helg
- schemaceller med heldagar och halvtimmar
- auditlogg for Historik

Verktyget ska bara koras mot en lokal eller temporar databas. `tools.visual_smoke`
gor detta automatiskt.

## Nar nagot ser fel ut

1. Spara screenshot-mappen som bevis.
2. Ange filnamn, viewport och roll fran `summary.json`.
3. Beskriv faktisk vy och onskat lage.
4. Korrigera kod.
5. Kor snabbtesterna igen.
6. Kor om relevant screenshot-urval, till exempel:

```powershell
python -m tools.visual_smoke --roles admin --output artifacts\visual\recheck
```

## Releasekontroll

Innan ny release:

1. `python -m pytest`
2. JS-syntaxkontroll
3. `python desktop\main.py --smoke-test`
4. `python -m tools.visual_smoke --roles public,admin,leader,viewer`
5. `python -m tools.interactive_e2e`
6. `python -m tools.desktop_shell_screens`
7. `python -m tools.desktop_app_probe`
8. `cmd /c build_windows.bat`
9. Skapa och pusha release-tagg enligt `RELEASE.md`.

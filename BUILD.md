# Bygga Windows-app

Det har projektet bygger en tunn Windows-klient ovanpa den centrala
Bemanning-webbappen. Klienten paketeras med PyInstaller till en fristaende
Windows-appmapp.

Builden kors i en temporar lokal mapp for att undvika OneDrive- och
Windows-lasningar.

## Snabbbygge

Kor i CMD fran projektroten:

```bat
build_windows.bat
```

Resultat:

- `release\Bemanning\Bemanning.exe`
- `release\Bemanning-0.1.0-win64.zip`
- `release\Bemanning-0.1.0-Setup.exe` om Inno Setup 6 finns installerat

Zip-filen kan delas till anvandare utan Python. Den innehaller appen,
`Installera Bemanning.bat`, avinstallation och en kort anvandar-README.

Om Inno Setup 6 finns installerat skapas aven en riktig `Setup.exe`.

## Installer

Inno Setup-mallen finns i:

```text
packaging\windows\Bemanning.iss
```

Nar Inno Setup 6 finns installerat bygger `build_windows.bat` en riktig
`Setup.exe` fran den redan byggda `release\Bemanning`-mappen. Det gar ocksa att
kora:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\windows\build_setup.ps1
```

Installeraren ar per-user och kraver inte administratorsrattigheter. Den
installeras i anvandarens `%LOCALAPPDATA%\Bemanning`, skapar genvagar och
registrerar avinstallation.

## Uppdateringar

Appen har `Hjalp -> Sok efter uppdateringar` och gor aven en tyst kontroll vid
start. Den laser senaste GitHub Release fran `EmirKadr/Bemanning`, letar efter
en asset som slutar pa `Setup.exe`, laddar ner den och startar installeraren.

Eftersom installeraren ar per-user behovs inga admin-rattigheter vid
uppdatering. Nar anvandaren godkanner en uppdatering kors installeraren tyst.

Versionsnumret finns i `core/app_info.py`. Hoj `APP_VERSION`, skapa en tagg som
`v0.2.0` och pusha taggen for att skapa en ny release-build.

## Central drift

Desktop-klienten startar en lokal app-yta pa `127.0.0.1` och servar den
paketerade frontendkoden fran `app/frontend`. Alla `/api/*`-anrop proxas vidare
till den centrala driftsatta servern via `SERVER_BASE_URL` i `core/app_info.py`.
Standardvardet ar `https://stigamo.nu`.

Det betyder att appen inte langre behover rendera hemsidan direkt, men den delar
fortfarande samma centrala PostgreSQL-sanning som hemsidan. Klienten innehaller
ingen lokal databas. Standardporten ar `8766` och kan andras med
`BEMANNING_DESKTOP_PORT`.

## GitHub artifact

Workflowen `.github/workflows/windows-release.yml` bygger Windows-paketet
manuellt via GitHub Actions (`workflow_dispatch`) eller nar en tagg som
`v0.1.0` pushas. Den laddar upp zippen och `Setup.exe` som artifacts. Vid
tagg-push laddas samma filer ocksa upp pa GitHub Release sa appens updater kan
hitta dem.

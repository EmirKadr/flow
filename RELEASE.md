# Releaseprocess

Den har filen beskriver hur vi publicerar en ny version av flow sa att
installeraren hamnar pa GitHub Releases och anvandare kan uppdatera appen.

## Viktig regel

Skapa inte en ny release for varje andring.

Vanliga kodandringar ska normalt bara commitas och pushas till `main`. En
release ska bara goras nar Emir uttryckligen ber om det, till exempel:

- "gor en release"
- "slapp version 0.2.0"
- "tagga och publicera ny version"
- "nu ska kollegan fa en uppdatering"

AI-agenter ska aldrig skapa release-tagg eller publicera GitHub Release utan en
sa tydlig instruktion.

## Vad som hander vid release

Nar en tagg som `v0.2.0` pushas startar GitHub Actions-workflowen
`.github/workflows/windows-release.yml`.

Workflowen bygger:

- `flow-0.2.0-win64.zip`
- `flow-0.2.0-Setup.exe`

Vid tagg-push laddas filerna aven upp pa GitHub Release. Appens updater laser
senaste GitHub Release och letar efter `Setup.exe`. Om versionen dar ar hogre
an anvandarens installerade version far anvandaren fragan att uppdatera.

## Steg for ny release

Byt ut `0.2.0` mot versionsnumret som ska slappas.

1. Kontrollera att alla andringar ar klara.

2. Hoj versionsnumret i `core/app_info.py`:

   ```py
   APP_VERSION = "0.2.0"
   ```

3. Kor tester:

   ```bat
   python -m pip install -r requirements-dev.txt
   pytest
   ```

4. Bygg och smoke-testa installeraren lokalt:

   ```bat
   scripts\build_windows.bat
   ```

   Forvantade filer:

   ```text
   release\flow-0.2.0-win64.zip
   release\flow-0.2.0-Setup.exe
   ```

5. Committa versionshojningen och eventuella andringar:

   ```bat
   git status --ignore-submodules=all
   git add .
   git commit -m "Release 0.2.0"
   git push
   ```

6. Skapa och pusha release-taggen:

   ```bat
   git tag v0.2.0
   git push origin v0.2.0
   ```

7. Kontrollera GitHub Actions och GitHub Release:

   - Actions ska bli gron.
   - Releasen `v0.2.0` ska ha `Setup.exe` och zip som assets.

## Efter release

Anvandare far uppdateringen genom:

- automatisk kontroll vid appstart
- eller `Hjalp -> Sok efter uppdateringar`

Installeraren ar per-user och kraver inte administratorsrattigheter. Nar
anvandaren godkanner uppdateringen laddar appen ner `Setup.exe`, startar den
tyst och stanger appen medan uppdateringen installeras.

## Gor inte detta

- Skapa inte tagg/release for sma mellanandringar.
- Pusha inte en tagg utan att forst hoja `APP_VERSION`.
- Ateranvand inte samma versionsnummer for olika installerare.
- Force-pusha inte release-taggar utan att uttryckligen diskutera det forst.
- Ladda inte upp en lokal installer manuellt om den inte matchar exakt version i
  `core/app_info.py`.

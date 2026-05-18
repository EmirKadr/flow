@echo off
setlocal
cd /d "%~dp0"

set "BUILD_ROOT=%LOCALAPPDATA%\BemanningBuild"
if "%LOCALAPPDATA%"=="" set "BUILD_ROOT=%TEMP%\BemanningBuild"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMddHHmmss"') do set "BUILD_ID=%%i-%RANDOM%"
for /f %%i in ('python -c "from core.app_info import APP_VERSION; print(APP_VERSION)"') do set "APP_VERSION=%%i"
set "WORK_ROOT=%BUILD_ROOT%\work-%BUILD_ID%"
set "DIST_ROOT=%BUILD_ROOT%\dist-%BUILD_ID%"
set "APP_DIST_DIR=%DIST_ROOT%\Bemanning"

echo Installing build requirements...
python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1

echo Building Bemanning.exe...
python -m PyInstaller --noconfirm --workpath "%WORK_ROOT%" --distpath "%DIST_ROOT%" Bemanning.spec
if errorlevel 1 exit /b 1

echo Smoke testing built app...
"%APP_DIST_DIR%\Bemanning.exe" --smoke-test
if errorlevel 1 exit /b 1

echo Creating release zip...
powershell -NoProfile -ExecutionPolicy Bypass -File "packaging\windows\make_release_zip.ps1" -DistDir "%APP_DIST_DIR%" -Version "%APP_VERSION%"
if errorlevel 1 exit /b 1

echo Building Setup.exe if Inno Setup is installed...
powershell -NoProfile -ExecutionPolicy Bypass -File "packaging\windows\build_setup.ps1" -Version "%APP_VERSION%"
if errorlevel 1 exit /b 1

echo Validating release artifacts...
python -m tools.release_check --version "%APP_VERSION%"
if errorlevel 1 exit /b 1

echo.
echo Done. See the release folder.
echo Build folder: "%APP_DIST_DIR%"

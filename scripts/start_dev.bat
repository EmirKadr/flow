@echo off
setlocal
cd /d "%~dp0..\app"

set "DATABASE_URL=sqlite:///./flow_local.db"
set "SECRET_KEY=dev-only-change-me"
set "ENVIRONMENT=development"
set "SUPER_USER_USERNAMES=admin,emikad,mikhal"
set "EXCEL_API_TOKEN=dev-token"
set "FLOW_SYNC_LIVE_ON_START=0"

echo Forbereder lokal SQLite-databas for utvecklingslage...
python -m backend.prepare_local_database || goto :error

echo Startar RFID-bryggor for ESP32 via USB/COM: COM9=MG Plock, COM10=MG VM...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\tools\start_rfid_bridges.ps1" || echo Varning: RFID-bryggor kunde inte startas automatiskt.

echo Startar lokal dev-server med reload. RFID-moduler laser via COM9/COM10.
start "" "http://localhost:8000"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
goto :eof

:error
echo.
echo Fel vid uppstart. Tryck en tangent for att stanga.
pause >nul
exit /b 1

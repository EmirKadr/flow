@echo off
setlocal
cd /d "%~dp0..\app"

set "DATABASE_URL=sqlite:///./flow_local.db"
set "SECRET_KEY=dev-only-change-me"
set "ENVIRONMENT=development"
set "SUPER_USER_USERNAMES=admin,emikad,mikhal"
set "EXCEL_API_TOKEN=dev-token"
set "FLOW_SYNC_LIVE_ON_START=0"

echo Forbereder lokal SQLite-databas for snabbstart...
python -m backend.prepare_local_database || goto :error

echo Startar lokal server pa localhost. RFID-moduler postar direkt via WiFi.
start "" "http://localhost:8000"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
goto :eof

:error
echo.
echo Fel vid uppstart. Tryck en tangent for att stanga.
pause >nul
exit /b 1

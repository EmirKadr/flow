@echo off
setlocal
cd /d "%~dp0app"

set "DATABASE_URL=sqlite:///./flow_local.db"
set "SECRET_KEY=dev-only-change-me"
set "ENVIRONMENT=development"
set "SUPER_USER_USERNAMES=admin,emikad,mikhal"
set "EXCEL_API_TOKEN=dev-token"

echo Forbereder lokal SQLite-databas...
python -m backend.prepare_local_database || goto :error

echo Startar lokal server pa localhost och WiFi/LAN. ESP32 ska anvanda datorns WiFi-IP med port 8000.
start "" "http://localhost:8000"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
goto :eof

:error
echo.
echo Fel vid uppstart. Tryck en tangent for att stanga.
pause >nul
exit /b 1

@echo off
setlocal
cd /d "%~dp0app"

set "DATABASE_URL=sqlite:///./flow_local.db"
set "SECRET_KEY=dev-only-change-me"
set "ENVIRONMENT=development"
set "SUPER_USER_USERNAMES=admin,emikad,mikhal"
set "EXCEL_API_TOKEN=dev-token"
set "FLOW_SYNC_LIVE_ON_START=1"

echo Synkar live-data till lokal SQLite. Stang start_local.bat/uvicorn innan du kor detta.
python -m backend.prepare_local_database || goto :error
echo Klar. Starta sedan start_local.bat.
goto :eof

:error
echo.
echo Fel vid live-sync. Stang gamla lokala servrar och prova igen.
pause >nul
exit /b 1

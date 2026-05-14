@echo off
setlocal
cd /d "%~dp0app"

set "DATABASE_URL=sqlite:///./bemanning_local.db"
set "SECRET_KEY=dev-only-change-me"
set "ENVIRONMENT=development"
set "SUPER_ADMIN_USERNAMES=emikad"
set "EXCEL_API_TOKEN=dev-token"

if not exist "bemanning_local.db" (
    echo Skapar lokal databas...
    python -m alembic upgrade head || goto :error
    python -m backend.seed || goto :error
)

start "" "http://localhost:8000"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
goto :eof

:error
echo.
echo Fel vid uppstart. Tryck en tangent for att stanga.
pause >nul
exit /b 1

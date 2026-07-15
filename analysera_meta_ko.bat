@echo off
setlocal

cd /d "%~dp0"

python -m tools.flow_cli --base-url https://flow-development.nowastelogistics.com meta process-queue --status=queued --local-dispatch-lookup
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
  echo Kommandot misslyckades med felkod %EXITCODE%.
) else (
  echo Klart.
)
pause
exit /b %EXITCODE%

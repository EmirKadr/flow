@echo off
setlocal
cd /d "%~dp0"

echo Stanger lokal Bemanning-server...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = (Resolve-Path '.').Path.TrimEnd('\');" ^
  "$pids = New-Object System.Collections.Generic.HashSet[int];" ^
  "$allProcesses = @(Get-CimInstance Win32_Process);" ^
  "$allProcesses | Where-Object { $_.CommandLine -and $_.CommandLine -like ('*' + $root + '*start_local.bat*') } | ForEach-Object { [void]$pids.Add([int]$_.ProcessId) };" ^
  "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { [void]$pids.Add([int]$_.OwningProcess) };" ^
  "$changed = $true; while ($changed) { $changed = $false; foreach ($process in $allProcesses) { if ($pids.Contains([int]$process.ParentProcessId) -and -not $pids.Contains([int]$process.ProcessId)) { [void]$pids.Add([int]$process.ProcessId); $changed = $true } } };" ^
  "$targets = @($pids | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue });" ^
  "if ($targets.Count -eq 0) { Write-Host 'Ingen lokal Bemanning-server hittades.'; exit 0 };" ^
  "foreach ($targetPid in $targets) { try { Stop-Process -Id $targetPid -Force -ErrorAction Stop; Write-Host ('Stoppade PID ' + $targetPid) } catch { Write-Host ('PID ' + $targetPid + ' kunde inte stoppas eller finns inte langre.') } };" ^
  "Start-Sleep -Seconds 1; exit 0"

exit /b 0

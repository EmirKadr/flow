$ErrorActionPreference = "Continue"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $Root "artifacts\rfid_bridge"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Bridges = @(
    @{
        Port = "COM9"
        ModuleName = "MG Plock"
        DeviceId = "usb-rfid-mg-plock"
        LogName = "mg_plock_com9"
    },
    @{
        Port = "COM10"
        ModuleName = "MG VM"
        DeviceId = "usb-rfid-mg-vm"
        LogName = "mg_vm_com10"
    }
)

foreach ($Bridge in $Bridges) {
    $Port = $Bridge.Port
    $Existing = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
        Where-Object {
            $_.CommandLine -like "*tools.rfid_serial_bridge*" -and
            $_.CommandLine -like "*--port $Port*"
        }

    if ($Existing) {
        Write-Host "RFID-brygga for $Port kor redan."
        continue
    }

    $OutLog = Join-Path $LogDir "$($Bridge.LogName).out.log"
    $ErrLog = Join-Path $LogDir "$($Bridge.LogName).err.log"
    $Arguments = '-u -m tools.rfid_serial_bridge --port {0} --module-name "{1}" --force-module-name --device-id {2} --base-url http://127.0.0.1:8000 --retry-open --dedupe-window 3' -f $Bridge.Port, $Bridge.ModuleName, $Bridge.DeviceId

    try {
        Start-Process `
            -WindowStyle Hidden `
            -FilePath python `
            -ArgumentList $Arguments `
            -WorkingDirectory $Root `
            -RedirectStandardOutput $OutLog `
            -RedirectStandardError $ErrLog | Out-Null
        Write-Host "Startade RFID-brygga $($Bridge.ModuleName) pa $Port."
    } catch {
        Write-Host "Kunde inte starta RFID-brygga pa ${Port}: $($_.Exception.Message)"
    }
}

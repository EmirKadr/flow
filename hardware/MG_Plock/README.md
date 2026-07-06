# RFID ESP32 till flow

Den har sketchen laser EM4100/125 kHz-brickor via RDM6300 och skriver
stamplingen pa USB/Serial sa Flow kan lasa den via COM-port.

Den har modulmappen ar satt till `MG Plock`, vilket matchar aktiviteten med
samma namn eller koden `MG_PLOCK` i flow.

## Konfiguration

`MG_Plock.ino` ar lokal och git-ignorerad. Den innehaller ingen WiFi,
serveradress eller token. Ladda upp sketchen direkt till ESP32:

- `DEVICE_ID`: `esp32-mg-plock-01`
- `MODULE_NAME`: `MG Plock`
- Serial baudrate: `115200`
- RDM6300 baudrate: `9600`

Sketchen skriver rader i formatet:

```text
[MG Plock] RFID HEX=00A1B2C3 DEC=10597059 count=1
```

Flow laser dessa rader via `tools.rfid_serial_bridge` och postar sedan till
`POST /api/rfid/scans` lokalt.

## Automatisk COM-brygga

`scripts\start_local.bat` och `scripts\start_dev.bat` startar bryggan automatiskt:

```powershell
COM9 -> MG Plock
COM10 -> MG VM
```

Du ska alltsa normalt bara starta Flow och lata ESP32 sitta i ratt USB-port.
Arduino Serial Monitor maste vara stangd, eftersom bara ett program kan lasa
samma COM-port samtidigt.

Loggar hamnar i `artifacts/rfid_bridge/`.

## Koppling

| RDM6300 | ESP32 |
| --- | --- |
| TX | GPIO16, helst via spanningsdelare till 3,3 V |
| VCC | 5V/VIN |
| GND | GND |

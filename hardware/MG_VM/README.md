# RFID ESP32 till flow

Den har sketchen laser EM4100/125 kHz-brickor via RDM6300 och postar scanen
direkt over WiFi till Flow, ingen USB-brygga kravs.

Den har modulmappen ar satt till `MG VM`, vilket matchar aktiviteten med samma
namn eller koden `MG_VM` i flow.

## Konfiguration

`MG_VM.ino` ar lokal och git-ignorerad eftersom den innehaller riktiga
WiFi-uppgifter, serveradress och token. Fyll i overst i sketchen innan
uppladdning:

- `WIFI_SSID` / `WIFI_PASSWORD`: WiFi-natet ESP32 och Flow-servern nas fran.
- `SERVER_URL`: Flow-miljons adress, till exempel
  `https://flow-development.nowastelogistics.com/api/rfid/scans`.
- `DEVICE_TOKEN`: samma varde som Octopus-variabeln `RFID_DEVICE_TOKEN` for
  den miljon. Tom strang fungerar bara om variabeln ar tom/osatt i den miljon.
- `DEVICE_ID`: `esp32-mg-vm-01`
- `MODULE_NAME`: `MG VM`
- Serial baudrate: `115200`
- RDM6300 baudrate: `9600`

Sketchen skriver samma scanrader pa Serial som forut (for felsokning i Serial
Monitor) och postar sedan direkt till `POST /api/rfid/scans`:

```text
[MG VM] RFID HEX=00A1B2C3 DEC=10597059 count=1
POST 201: {...}
```

## WiFi och natverk

ESP32 och Flow-servern maste kunna na varandra over natverket. Kontrollera
vid felsokning:

- Att WiFi-natet ar samma som ESP32 fick i `WiFi OK, IP: ...`-raden.
- Att `SERVER_URL` pekar pa ratt Flow-miljo (rätt domän/IP, inte en gammal
  lokal adress).
- Att `DEVICE_TOKEN` matchar den senast deployade releasens
  `RFID_DEVICE_TOKEN`. Octopus snapshotar variabler nar en release skapas,
  inte vid omdeploy av en befintlig release - en variabelandring kraver
  darfor en ny release for att sla igenom.
- Arduino Serial Monitor (115200 baud) visar WiFi-status och POST-svar
  (`POST 201/200`, `POST 401` for feltoken, `POST-fel` for natverksfel).

## Koppling

| RDM6300 | ESP32 |
| --- | --- |
| TX | GPIO16, helst via spanningsdelare till 3,3 V |
| VCC | 5V/VIN |
| GND | GND |

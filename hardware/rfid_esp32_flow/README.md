# RFID ESP32 till flow

Den har sketchen laser EM4100/125 kHz-brickor via RDM6300 och skickar
stamplingen till flow:

`POST /api/rfid/scans`

Standardmodulen ar satt till `MG Plock`, vilket matchar aktiviteten med samma
namn i flow. Andra fysiska moduler kan flashas med samma kod men unikt
`DEVICE_ID` och nytt `MODULE_NAME`.

## Konfiguration

Hemligheter och lokal serveradress ska inte skrivas i `rfid_esp32_flow.ino`.
Kopiera i stallet:

```text
rfid_esp32_flow.local.example.h -> rfid_esp32_flow.local.h
```

Fyll sedan i `rfid_esp32_flow.local.h`:

- `WIFI_SSID`
- `WIFI_PASSWORD`
- `FLOW_BASE_URL`, till exempel datorns WiFi-IP med port 8000
- `RFID_TOKEN` om `RFID_DEVICE_TOKEN` ar satt i backend
- `DEVICE_ID` och `MODULE_NAME` om du flashar fler fysiska moduler

ESP32 kan inte posta till `localhost` pa din dator. Anvand datorns IP-adress pa
samma WiFi.

`rfid_esp32_flow.local.h` ar git-ignorerad. Den committade `.ino` har bara
generiska fallback-varden.

## Koppling

| RDM6300 | ESP32 |
| --- | --- |
| TX | GPIO16, helst via spanningsdelare till 3,3 V |
| VCC | 5V/VIN |
| GND | GND |

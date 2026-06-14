---
title: RFID-stamplingar
status: aktiv
updated: 2026-06-14
tags: [rfid, bemanning, hardvara]
---

# RFID-stamplingar

Kort svar: RFID-moduler kan posta scan events till Flow. Varje modul representerar en aktivitet, till exempel `MG Plock`. Bemanning visar stampeln som en markering pa personens timcell. En anvandare kan klicka `OK` for att andra cellen fran scannad minut, eller `Ignorera` for att lata stampeln ligga kvar utan schemaandring.

## Anvandarflode

1. Personen scannar sin bricka pa en fysisk modul vid aktiviteten.
2. Modulen skickar `device_id`, `module_name`, brickkod och scanraknare till `POST /api/rfid/scans`.
3. Backend matchar `module_name` mot aktiviteten och brickkoden mot `Person.rfid_code`.
4. Bemanning hamtar stampeln via `GET /api/rfid/events` och visar en liten markering i ratt timcell.
5. `OK` applicerar aktiviteten fran scannad minut till timslut och bevarar tidigare minuter i timmen.
6. `Ignorera` sparar statusen `ignored`, men raderar inte stampeln.

## Regler

- Modulnamn matchas mot aktivitetens `label` eller `code`. Testmodulen ar satt till `MG Plock`.
- Person matchas med `Person.rfid_code`; hex/dec-koder normaliseras innan jamforelse.
- Om samma person scannar samma aktivitet tva ganger i rad sparas den andra som `duplicate_ignored` och kan inte appliceras.
- Okand bricka blir `unknown_person`; okand modul/aktivitet blir `unknown_activity`.
- Om stampeln ligger utanfor Bemanningens timmar 06-23 blir applicering konflikt.
- Device-endpointen kan skyddas med `RFID_DEVICE_TOKEN`. Om den ar satt maste ESP32 skicka samma varde i headern `X-Flow-RFID-Token`.

## Hårdvara

Flow har en firmware-mapp for ESP32/RDM6300. `rfid_esp32_flow.ino` ar lokal och
git-ignorerad eftersom den innehaller WiFi, serveradress och eventuell token.
`FLOW_BASE_URL` ska vara datorns LAN-adress, inte `localhost`, eftersom ESP32
inte ligger pa samma process som browsern. Lokal server maste lyssna pa LAN;
`start_local.bat` startar darfor uvicorn med `--host 0.0.0.0` men oppnar
browsern pa `localhost`.

Bemanning pollar `GET /api/rfid/events` var 7:e sekund nar fliken ar synlig.
Om en scan nar backend syns den forst som `POST /api/rfid/scans` i
`start_local.bat`-fonstret och sedan som markering i ratt person/timme.

Om datorn saknar adminrattigheter och Windows-brandvaggen stoppar ESP32 fran
att posta over WiFi kan man kora `tools.rfid_serial_bridge` i stallet. Da ar
ESP32 ansluten med USB, bryggan laser serialraden som Arduino Serial Monitor
annars visar och postar scannen till `http://127.0.0.1:8000/api/rfid/scans`.
Det kraver ingen inbound firewall-regel. Arduino Serial Monitor maste vara
stangd medan bryggan kor, eftersom serieporten bara kan lasas av ett program i
taget.

Aktuell testkonfiguration:

- `MODULE_NAME`: `MG Plock`
- `DEVICE_ID`: `esp32-mg-plock-01`
- API: `POST /api/rfid/scans`

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor syns ingen stampel i Bemanning?" | Om `start_local.bat` inte visar `POST /api/rfid/scans` har scannen inte natt backend: kontrollera ESP32 WiFi, `FLOW_BASE_URL`, att servern startats om efter LAN-host-andringen och eventuell Windows-brandvagg. Om `POST` syns men ingen markering visas, kontrollera modulnamn, personens `rfid_code`, vald dag och omradesfokus. |
| "Jag har inte admin for brandvaggsregel, hur testar jag?" | Kor via USB-bryggan: `python -m pip install --user pyserial`, stang Arduino Serial Monitor och starta `python -m tools.rfid_serial_bridge --port COM5 --module-name "MG Plock"`. Byt `COM5` mot ESP32-porten. Nar bryggan visar `HTTP 201` har backend tagit emot scannen. |
| "Maste jag ladda upp firmware igen for USB-bryggan?" | Nej, inte om Arduino redan skriver serialrader med `RFID HEX=... DEC=... count=...`. USB-bryggan ateranvander den signalen och postar lokalt fran datorn. |
| "Varfor ligger stampeln kvar efter Ignorera?" | Ignorera raderar inte handelsen. Den byter status sa stampeln fortsatt kan ses och granskas. |
| "Varfor blev andra scannen dubblett?" | Senaste sparade RFID-aktiviteten for samma person var samma aktivitet. Backend sparar da andra stampeln som `duplicate_ignored`. |
| "Varfor andrades bara sista delen av timmen?" | RFID-OK galler fran scannad minut till timslut. Tidigare minuter i samma timme bevaras. |
| "Ska modulen ha riktiga WiFi-varden i git?" | Nej. `rfid_esp32_flow.ino` ar lokal och git-ignorerad, sa riktiga WiFi/server/token-varden ska bara finnas dar lokalt. |

## Kallor

- `../hardware/rfid_esp32_flow/rfid_esp32_flow.ino`
- `../hardware/rfid_esp32_flow/README.md`
- `../tools/rfid_serial_bridge.py`
- `../app/backend/routers/rfid.py`
- `../app/backend/models.py`
- `../app/frontend/js/schedule/rfid.js`
- `../app/alembic/versions/0042_rfid_scan_events.py`

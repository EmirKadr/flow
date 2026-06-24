---
title: RFID-stamplingar
status: aktiv
updated: 2026-06-17
tags: [rfid, bemanning, hardvara]
---

# RFID-stamplingar

Kort svar: RFID-moduler kan posta scan events till Flow. Varje modul representerar en aktivitet, till exempel `MG Plock` eller `MG VM`. Bemanning visar stampeln som en markering pa personens timcell. En anvandare kan klicka `OK` for att andra cellen fran scannad minut, eller `Ignorera` for att lata stampeln ligga kvar utan schemaandring.

## Anvandarflode

1. Personen scannar sin bricka pa en fysisk modul vid aktiviteten.
2. Modulen skickar `device_id`, `module_name`, brickkod och scanraknare till `POST /api/rfid/scans`.
3. Backend matchar `module_name` mot aktiviteten och brickkoden mot `Person.rfid_code`.
4. Bemanning hamtar stampeln via `GET /api/rfid/events` och visar en liten markering i ratt timcell.
5. `OK` applicerar aktiviteten fran scannad minut till timslut och bevarar tidigare minuter i timmen.
6. `Ignorera` sparar statusen `ignored`, men raderar inte stampeln.

## Regler

- Modulnamn matchas mot aktivitetens `label` eller `code`. Lokala testmoduler finns for `MG Plock` och `MG VM`.
- Person matchas med `Person.rfid_code`; hex/dec-koder normaliseras innan jamforelse.
- Om samma person scannar samma aktivitet tva ganger i rad droppas den andra innan `rfid_scan_events`; den skapar ingen markering och ingen Historik-rad.
- Okand bricka blir `unknown_person`; okand modul/aktivitet blir `unknown_activity`.
- Om stampeln ligger utanfor Bemanningens timmar 06-23 blir applicering konflikt.
- Device-endpointen kan skyddas med `RFID_DEVICE_TOKEN`. Om den ar satt maste ESP32 skicka samma varde i headern `X-Flow-RFID-Token`.

## Hårdvara

Flow har firmware-mappar for ESP32/RDM6300, till exempel `hardware/MG_Plock`
och `hardware/MG_VM`. `.ino`-filerna ar lokala och git-ignorerade, men de
innehaller ingen WiFi, serveradress eller token. Sketchen laser RDM6300 och
skriver bara serialrader i formatet `[MG VM] RFID HEX=... DEC=... count=...`.

`start_local.bat` och `start_dev.bat` startar automatiskt
`tools/start_rfid_bridges.ps1`, som i sin tur startar serialbryggor for
`COM9 -> MG Plock` och `COM10 -> MG VM`. Bryggorna laser ESP32:ornas USB/Serial
och postar sedan lokalt till `http://127.0.0.1:8000/api/rfid/scans`. Samma tagg
pa samma modul filtreras i bryggan inom ett kort debounce-fonster, sa en bricka
som ligger kvar vid lasaren inte skapar ett regn av lokala POST-anrop. Om en
COM-port ar upptagen vid start ligger bryggan kvar och provar igen tills porten
slapps.

Bemanning pollar `GET /api/rfid/events` var 7:e sekund nar fliken ar synlig.
Om en scan nar backend syns den forst som `POST /api/rfid/scans` i
`start_local.bat`-fonstret och sedan som markering i ratt person/timme.

Arduino Serial Monitor maste vara stangd medan USB-bryggan kor, eftersom
serieporten bara kan lasas av ett program i taget.

Aktuella lokala moduler:

| Modul | Aktivitet | Device-id | USB-brygga |
| --- | --- | --- | --- |
| `MG Plock` | `MG Plock` / `MG_PLOCK` | `esp32-mg-plock-01` | autostart via `COM9` |
| `MG VM` | `MG VM` / `MG_VM` | `esp32-mg-vm-01` | autostart via `COM10` |

RDM6300 `TX` kopplas till ESP32 `GPIO16`. API:t ar `POST /api/rfid/scans`.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor syns ingen stampel i Bemanning?" | Kontrollera att ESP32 sitter i ratt USB-port (`COM9` for MG Plock, `COM10` for MG VM), att Arduino Serial Monitor ar stangd och att `artifacts/rfid_bridge/*.log` visar en RFID-rad eller ett portfel. Om `POST /api/rfid/scans` syns men ingen markering visas, kontrollera modulnamn, personens `rfid_code`, vald dag och omradesfokus. |
| "Jag har inte admin for brandvaggsregel, hur testar jag?" | Ingen brandvaggsregel behovs i USB-laget. Starta Flow med `start_local.bat`, hall ESP32 anslutna pa COM9/COM10 och titta i `artifacts/rfid_bridge/` vid felsokning. |
| "Kan modulen ha flera WiFi?" | Nej, de lokala MG-sketcherna ar USB/Serial-only och anvander inte WiFi. |
| "USB-bryggan sager att COM-porten ar upptagen eller blockerad" | Ratt COM-port kan vara last av Arduino Serial Monitor/Serial Plotter. Stang serialfonstret; autostartade bryggor ligger kvar och provar igen. |
| "Maste jag ladda upp firmware igen for USB-bryggan?" | Ladda upp de nya USB-only-sketcherna om ESP32 fortfarande forsoker ansluta till WiFi. Efter det racker det att starta Flow. |
| "Varfor ligger stampeln kvar efter Ignorera?" | Ignorera raderar inte handelsen. Den byter status sa stampeln fortsatt kan ses och granskas. |
| "Varfor syns inte andra scannen?" | Senaste sparade RFID-aktiviteten for samma person var samma aktivitet. Backend droppar da andra scannen utan att skapa ny markering eller Historik-rad. |
| "Varfor andrades bara sista delen av timmen?" | RFID-OK galler fran scannad minut till timslut. Tidigare minuter i samma timme bevaras. |
| "Ska modulen ha riktiga WiFi-varden i git?" | Nej. De lokala MG-sketcherna ska inte ha WiFi/server/token-varden alls. |

## Kallor

- `../hardware/MG_Plock/README.md`
- `../hardware/MG_VM/README.md`
- `../tools/rfid_serial_bridge.py`
- `../app/backend/routers/rfid.py`
- `../app/backend/models.py`
- `../app/frontend/js/schedule/rfid.js`
- `../app/alembic/versions/0042_rfid_scan_events.py`

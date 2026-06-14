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

Flow har en ny firmware-mapp for ESP32/RDM6300. Den innehaller bara generiska placeholders for WiFi, serveradress och token. `FLOW_BASE_URL` ska vara datorns LAN-adress, inte `localhost`, eftersom ESP32 inte ligger pa samma process som browsern.

Aktuell testkonfiguration:

- `MODULE_NAME`: `MG Plock`
- `DEVICE_ID`: `esp32-mg-plock-01`
- API: `POST /api/rfid/scans`

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor syns ingen stampel i Bemanning?" | Kontrollera att ESP32 postar mot ratt LAN-adress, att modulen heter som en aktiv aktivitet, att personen har `rfid_code`, och att vald dag/omrade matchar stampelns tid. |
| "Varfor ligger stampeln kvar efter Ignorera?" | Ignorera raderar inte handelsen. Den byter status sa stampeln fortsatt kan ses och granskas. |
| "Varfor blev andra scannen dubblett?" | Senaste sparade RFID-aktiviteten for samma person var samma aktivitet. Backend sparar da andra stampeln som `duplicate_ignored`. |
| "Varfor andrades bara sista delen av timmen?" | RFID-OK galler fran scannad minut till timslut. Tidigare minuter i samma timme bevaras. |
| "Ska modulen ha riktiga WiFi-varden i git?" | Nej. Firmwarefilen i repo:t ska bara ha placeholders. Riktiga varder fylls lokalt innan uppladdning till ESP32. |

## Kallor

- `../hardware/rfid_esp32_flow/rfid_esp32_flow.ino`
- `../hardware/rfid_esp32_flow/README.md`
- `../app/backend/routers/rfid.py`
- `../app/backend/models.py`
- `../app/frontend/js/schedule/rfid.js`
- `../app/alembic/versions/0042_rfid_scan_events.py`

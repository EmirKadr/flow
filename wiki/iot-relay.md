---
title: IoT-rela
status: aktiv
updated: 2026-07-13
tags: [iot, rela, gps, integration]
---

# IoT-rela

Kort svar: en tunn, helt fristaende brevlada dar IoT-enheter (ESP32 GPS-trackers
pa truckar, sensorer) POSTar sina handelser, och det separata projektet
**IoT-Dashboard** (lokalt kord app hos Emir) pollar hem dem. flow visar ingen
egen UI for detta — relaet finns har enbart for att stigamo.nu ar always-on
med stabil URL, till skillnad fran en lokalt kord backend bakom tillfalliga
tunnlar.

## Delar

- `app/backend/routers/iot_relay.py` — hela modulen: POST `/api/iot-relay/gps`,
  POST `/api/iot-relay/reading`, GET `/api/iot-relay/events` (id-stigande
  cursor, tail-lage utan `since`) samt kommandobrevladan at andra hallet:
  POST `/api/iot-relay/command` (allowlist: `wifi-locate`) och
  GET `/api/iot-relay/commands?deviceId=` som truckdatorernas bryggor pollar.
- `IotRelayEvent` + `IotRelayCommand` i `models.py`, migrationer
  `0051_iot_relay_events` och `0052_iot_relay_commands` — inga FK:er till
  bemanningsdomanen. Bada stadas automatiskt efter 48 h
  (sannolikhetsstyrt vid insert).
- Auth: `IOT_RELAY_TOKEN` (env, `generateValue` i render.yaml) — obligatorisk,
  503 om okonfigurerad, 401 vid fel. POST tar token via header
  `X-IoT-Device-Token` eller `?token=`; GET via `?token=`. Samma idiom som
  `EXCEL_API_TOKEN` i [public-endpoints](api.md).

## Kontrakt och konsument

Kontraktet ags av IoT-Dashboard-repot
(`projects/IoT-Dashboard/docs/API.md`, avsnittet "Rela via stigamo.nu") —
POST-bodyn ar identisk med det projektets egna ingest-API, sa dess poller
spelar in posterna raat i sin befintliga pipeline. Andra aldrig svarsformatet
har utan att uppdatera kontraktet dar forst.

## Avgransning

Medvetet INGEN koppling till persons/businesses/schedule — truckar ar inte en
del av bemanningsdomanen. Jamfor det ofardiga RFID-sparet (migration
0041/0042, tabeller utan kod) som varnande exempel: den har modulen ska vara
komplett och sjalvstandig eller inte finnas alls.

## Test

`tests/services/test_iot_relay.py` — token-matris (503/401/header/query),
faltvalidering, tail/since/limit-cursor, retention-stadning.

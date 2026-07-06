---
title: RFID-stamplingar
status: aktiv
updated: 2026-07-06
tags: [rfid, bemanning, hardvara, wifi]
---

# RFID-stamplingar

Kort svar: RFID-moduler postar scan events direkt over WiFi till Flow, ingen
USB-brygga eller COM-port kravs (beslut 2026-07-06, ersatte den tidigare
USB/Serial-losningen). Varje modul representerar en aktivitet, till exempel
`MG Plock` eller `MG VM`. Bemanning visar stampeln som en markering pa
personens timcell. En anvandare kan klicka `OK` for att andra cellen fran
scannad minut, eller `Ignorera` for att lata stampeln ligga kvar utan
schemaandring.

## Anvandarflode

1. Personen scannar sin bricka pa en fysisk modul vid aktiviteten.
2. ESP32 lasare postar direkt over WiFi: `device_id`, `module_name`, brickkod
   och scanraknare till `POST /api/rfid/scans` pa Flow-miljon (t.ex.
   `https://flow-development.nowastelogistics.com`).
3. Backend matchar `module_name` mot aktiviteten och brickkoden mot
   `Person.rfid_code`.
4. Bemanning hamtar stampeln via `GET /api/rfid/events` och visar en liten
   markering i ratt timcell.
5. `OK` applicerar aktiviteten fran scannad minut till timslut och bevarar
   tidigare minuter i timmen.
6. `Ignorera` sparar statusen `ignored`, men raderar inte stampeln.

## Regler

- Modulnamn matchas mot aktivitetens `label` eller `code`. Lokala testmoduler
  finns for `MG Plock` och `MG VM`.
- Person matchas med `Person.rfid_code`; hex/dec-koder normaliseras innan
  jamforelse.
- Om samma person scannar samma aktivitet tva ganger i rad droppas den andra
  innan `rfid_scan_events`; den skapar ingen markering och ingen Historik-rad.
- Okand bricka blir `unknown_person` (status + orsak sparas anda i
  `rfid_scan_events` och loggas till Historik, se nedan); okand modul/aktivitet
  blir `unknown_activity`. En okand-person-scan skapar ingen markering i
  Bemanning eftersom det inte finns nagon `person_id` att fasta den pa.
- Om stampeln ligger utanfor Bemanningens timmar 06-23 blir applicering
  konflikt.
- Device-endpointen skyddas av `RFID_DEVICE_TOKEN`: ett delat hemligt varde
  per miljo, inte per enhet. Om variabeln ar satt till ett icke-tomt varde
  maste varje ESP32 skicka exakt samma varde i headern `X-Flow-RFID-Token`,
  annars svarar servern `401`. Ar variabeln tom/osatt krav ingen header alls.

## Hardvara och WiFi

Flow har firmware-mappar for ESP32/RDM6300, `hardware/MG_Plock` och
`hardware/MG_VM`. `.ino`-filerna ar lokala och git-ignorerade eftersom de
innehaller riktiga WiFi-uppgifter (`WIFI_SSID`/`WIFI_PASSWORD`), Flow-miljons
`SERVER_URL` och `DEVICE_TOKEN` i klartext. Sketchen laser RDM6300 via
`GPIO16`/`GPIO17`, skriver samma felsokningsrader som forut pa Serial
(`[MG Plock] RFID HEX=... DEC=... count=...`) och postar sedan direkt med
`WiFiClientSecure`/`HTTPClient` till `POST /api/rfid/scans`. Samma tagg pa
samma modul filtreras i sketchen inom ett 3-sekunders debounce-fonster
(`DEDUPE_WINDOW_MS`), sa en bricka som ligger kvar vid lasaren inte skapar ett
regn av POST-anrop.

Ingen lokal brygga eller autostart-skript behovs langre:
`scripts\start_local.bat` och `scripts\start_dev.bat` startar backend med
`--host 0.0.0.0` sa ESP32 kan na den over natverket, men startar inte langre
nagon COM-brygga. Den tidigare USB-losningen (`tools/rfid_serial_bridge.py`,
`tools/start_rfid_bridges.ps1`, COM9/COM10-autostart) togs bort 2026-07-06 nar
WiFi blev den enda vagen framat.

Bemanning pollar `GET /api/rfid/events` var 7:e sekund nar fliken ar synlig.

Aktuella moduler:

| Modul | Aktivitet | Device-id | Uppkoppling |
| --- | --- | --- | --- |
| `MG Plock` | `MG Plock` / `MG_PLOCK` | `esp32-mg-plock-01` | WiFi, postar direkt |
| `MG VM` | `MG VM` / `MG_VM` | `esp32-mg-vm-01` | WiFi, postar direkt |

RDM6300 `TX` kopplas till ESP32 `GPIO16`. API:t ar `POST /api/rfid/scans`.

## Octopus-token: viktig fallgrop

`RFID_DEVICE_TOKEN` satts som en Octopus-variabel i k8s-manifestet
([../k8s/flow.yml](../k8s/flow.yml)). Tva saker overraskar latt:

1. **Variabeln injiceras bara i podden vid deploy**, inte live. Att spara ett
   nytt variabelvarde i Octopus racker inte - podden fortsatter kora med det
   gamla vardet tills en ny deploy kor.
2. **Octopus snapshotar variabelvarden nar en release skapas, inte vid
   omdeploy.** En omdeploy av en befintlig, aldre release later fortfarande
   det gamla variabelvardet - en ny release (t.ex. genom att merga `main` in i
   en `release/*`-branch, se [nowaste-git-release.md](nowaste-git-release.md))
   kravs for att en ny `RFID_DEVICE_TOKEN` ska sla igenom.

Snabbaste satt att verifiera om servern faktiskt anvander det token du tror:
posta direkt med `curl`/`Invoke-RestMethod` mot
`POST https://<miljo>/api/rfid/scans` med headern `X-Flow-RFID-Token` satt
till det du forvantar - det isolerar om felet ar i ESP32-koden eller i vad
servern faktiskt kor.

`k8s/flow.yml` anvander `strategy: type: Recreate` (kravs eftersom PVC:erna ar
ReadWriteOnce), sa en deploy stanger ner gamla podden helt innan den nya
startar. Under de nagra sekunderna kan aktiva webblasarflikar fa
`network_error`/`HTTP 0` i Historik - det ar forvantat vid en pagaende
omdeploy, inte ett nytt fel.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor syns ingen stampel i Bemanning?" | Kolla Serial Monitor (115200 baud): star det `WiFi OK, IP: ...`? Postades scannen (`POST 201/200`)? Om POST syns men ingen markering, kontrollera modulnamn, personens `rfid_code`, vald dag och omradesfokus. |
| "POST 401: RFID-token saknas eller stammer inte" | `DEVICE_TOKEN` i sketchen matchar inte det Octopus-variabeln `RFID_DEVICE_TOKEN` faktiskt levererar just nu. Kontrollera att variabeln verkligen sparats (inte bara skriven i ett oppet redigeringsfalt) och att en NY release skapats och deployats efter andringen - en omdeploy av en gammal release racker inte. |
| "Jag ser network_error/HTTP 0 i Historik precis efter en Octopus-deploy" | Forvantat med `strategy: Recreate` - gamla podden stangs helt innan den nya startar, nagra sekunders driftstopp. Inget att felsoka om det bara skedde runt deploy-tidpunkten. |
| "ESP32 kraver att jag trycker pa en knapp for att Serial Monitor ska visa nagot" | Hardvaruquirk i USB-serial-chippets auto-reset-krets pa vissa klonkort, helt oberoende av WiFi/servertillstand. Har ingen effekt pa om servern tar emot POST-anrop. |
| "Maste jag ladda upp firmware igen efter en tokenandring?" | Ja - `DEVICE_TOKEN` ar en compile-time-konstant i sketchen. Bara Upload i Arduino IDE skriver om chippet, att spara `.ino`-filen racker inte. |
| "Kan jag testa utan fysisk ESP32?" | Ja, posta direkt med curl/Invoke-RestMethod mot `POST /api/rfid/scans` med samma JSON-falt och ev. token-header. Bra for att isolera server- fran klientfel. |
| "Varfor ligger stampeln kvar efter Ignorera?" | Ignorera raderar inte handelsen. Den byter status sa stampeln fortsatt kan ses och granskas. |
| "Varfor syns inte andra scannen?" | Senaste sparade RFID-aktiviteten for samma person var samma aktivitet. Backend droppar da andra scannen utan att skapa ny markering eller Historik-rad. |
| "Varfor andrades bara sista delen av timmen?" | RFID-OK galler fran scannad minut till timslut. Tidigare minuter i samma timme bevaras. |
| "En okand bricka scannades, syns det nagonstans?" | Ja, i Historik med Typ = RFID-stämpel, Åtgärd = receive, status `unknown_person` - men aldrig som markering i Bemanning eftersom ingen person ar kopplad. |
| "Ska WiFi-losenord/token ligga i git?" | Nej. `.ino`-filerna ar gitignorerade just for att de innehaller riktiga WiFi-uppgifter, servernamn och token i klartext. |
| "Delar MG Plock och MG VM samma token?" | Ja - `RFID_DEVICE_TOKEN` ar en enda global variabel per miljo, inte en per enhet/modul. `RfidDevice`-modellen har inget eget hemligt falt per enhet. |

## Kallor

- `../hardware/MG_Plock/README.md`
- `../hardware/MG_VM/README.md`
- `../app/backend/routers/rfid.py`
- `../app/backend/models.py`
- `../app/frontend/js/schedule/rfid.js`
- `../app/alembic/versions/0042_rfid_scan_events.py`
- `../k8s/flow.yml`
- `nowaste-git-release.md`

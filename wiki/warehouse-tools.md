---
title: Lagerverktyg
status: aktiv
updated: 2026-05-22
tags: [lagerverktyg, allokering, filer, ui]
---

# Lagerverktyg

Kort svar: Lagerverktygen ar fyra vyer ovanpa `warehouse_tools`: Uppladdningar for gemensamma lokala filer, Bearbeta for floden, Dela for listdelning och Harleda for WMS-eftersok. Filer sparas lokalt i IndexedDB och skickas till API nar ett flode kors.

## Vyer

| Vy | Fil | Syfte | Behorighet |
| --- | --- | --- | --- |
| Uppladdningar | `uppladdningar.html` | Lagg in ASK/WMS/Excel-filer i lokalt filpool | `allocationUploads` |
| Bearbeta | `bearbeta.html` | Kor kombinerade lagerfloden som Allokering, Ordersaldo, kontroller | `allocationProcess` |
| Dela | `dela.html` | Dela lang lista i kolumner | `allocationSplit` |
| Harleda | `harleda.html` | Eftersok inkop/artikel genom WMS-loggar | `allocationTrace` |

## Gemensamma filkontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Välj filer | Valjer en eller flera filer | Identifierar filtyp, mappar till slot, sparar i IndexedDB | `POST /api/allokering/detect` | Okand filtyp om namn/header inte matchar. |
| Drag-drop | Drar filer till panel/slot/flode | Samma som Välj filer, med fallback till slot | `routeAllocationFiles` | Om flera filer okanda visas toast "Kunde inte sortera". |
| Välj per slot | Valjer fil for en specifik slot | Forsoker detektera men fallbackar till sloten | `fallbackSlotKey` | Bra nar automatisk identifiering missar. |
| X per slot | Rensar slot | Tar bort lokal IndexedDB-post | `deleteAllocationFile` | Karnfil som `artikel_max.csv` kan visas utan att vara uppladdad. |
| Rensa alla | Rensar alla lokala uppladdningar | Rensar både allokerings- och produktivitetsstores | `clearAllUploadedFiles` | Bekraftelse visas om anropas via gemensam funktion. |
| Uppladdningsbadge | Visar antal nya filer | Lagrar notice i sessionStorage | `allocationUploadActivity` | Badge rensas nar Uppladdningar oppnas. |

## Bearbeta-floden

Bearbeta ar en egen sidebar-vy (`bearbeta.html`). Den ska inte beskrivas som en flik inne i Dela eller Harleda. Om anvandaren inte ser Bearbeta i menyn beror det normalt pa att rollen saknar `allocationProcess` i vyatkomst eller att anvandaren inte ar Super User. Vanliga lagerroller ser som standard Uppladdningar, Dela och Harleda.

Att andra `allocationProcess` eller `Vybehorigheter` kraver admin-/Super User-atkomst till Anvandare/installningar. En vanlig anvandare ska kontakta admin eller Super User, inte sjalv ga till Vybehorigheter.

| Flode | Kraver | Resultat |
| --- | --- | --- |
| Allokering | Detalj Kundorder, Buffertpallar; valfritt Saldo, Item option, Ej inlagrade | Resultat, near-miss, refill, pallplatser |
| Ordersaldo | Detalj Kundorder; valfritt Saldo | Kompletta ordrar och underskott |
| LYX-artiklar | Saldofil; valfritt `artikel_max.csv` | Lista LYX-artiklar |
| Pafyllnadsprio | Detalj Kundorder; valfritt Saldo, Orderoversikt, `artikel_max.csv` | Pafyllnadsprio, ev. lastningsfonster |
| HIB-koppling | Detalj Kundorder, Orderoversikt | Andringar och missade avgangar |
| Orderoversiktkontroll | Orderoversikt; valfritt Detalj Kundorder | Sändnings-/HIB-kontroller |
| Dispatchkontroll | Orderoversikt, Dispatchpallar; valfritt Detalj Kundorder | Dispatchavvikelser |
| Vecka 27-kontroll | Detalj Kundorder | Avvikelser/text |
| Prognosrapport | Prognos eller kampanj, samt Saldo; valfritt Buffert | Prognos vs Autoplock |

Dolda/tekniska floden finns for observations-update, observations-sync och update-check. Observations kan aven triggas automatiskt nar ny buffertfil laggs in.

## Dela

Kontroller:

- Textarea "Varden" for en rad per varde.
- Alternativ filslot for textfil.
- Antal per kolumn.
- Knappen "Dela varden".

API: `POST /api/allokering/flow/split-values`.

## Harleda

Kontroller:

- Inkopsnummer.
- Artikelnummer.
- Mottagningslogg kravs.
- Inlagringslogg, Buffertpallar, Transaktionslogg, Plocklogg och Korrigeringslogg ar valfria men ger rikare spar.
- Flodesknappen kor Eftersok.

API: `POST /api/allokering/flow/eftersok`.

Korda lagerverktygsfloden auditloggas i Historik som `allocation_flow`. Loggen sparar flodes-id, vilka filslotar/parameternamn som anvandes och hur manga resultattabeller som skapades, men inte filnamn eller inskickade listvarden. Om uppladdningen inte kan sparas, multipart-formularet inte kan lasas eller filen inte kan bearbetas loggas `upload_failed` med steg och feltyp. Om automatisk filidentifiering kraschar loggas `detect_failed`.

## Resultatkontroller

| Kontroll | Vad hander |
| --- | --- |
| Flodesknapp | Disabled tills kravda filer/falt finns. Visar "Kor..." medan API jobbar. |
| Info `i` | Visar flodesbeskrivning och kravda filer i popover. |
| Oppna i Excel | Skickar session_id och tabellnyckel till `/api/allokering/open-excel`. |
| Ladda ner CSV | Hamter `/api/allokering/download/{session_id}/{key}`. |

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor ar flodesknappen gra?" | Kravda filer eller textfalt saknas, eller ett annat flode kor. Klicka `i` for att se krav. |
| "Varfor hamnar filen i fel ruta?" | Automatisk detektion bygger pa filnamn/header. Anvand Välj pa exakt slot for att styra. |
| "Varfor kan jag inte Bearbeta men kan Harleda?" | Lagerroller utan processbehorighet far bara sjalvservicefloden som Eftersok och Dela. |
| "Varfor ser jag inte Bearbeta i menyn?" | Rollen saknar normalt `allocationProcess` eller Super User. Be admin/Super User kontrollera roll och Vybehorigheter. |
| "Varfor oppnas inte Excel?" | Funktionen kraver lokal desktop/OS-stod och servern maste ha kvar resultat-sessionen. Testa Ladda ner CSV. |
| "Vad betyder artikel_max karnfil?" | `artikel_max.csv` kan finnas som intern karnfil aven om anvandaren inte laddat upp den. |

## Kallor

- `../app/frontend/js/allocation_tools.js`
- `../app/backend/routers/allocation.py`
- `../app/backend/allocation_bridge.py`
- `../warehouse_tools/catalog.py`
- `../warehouse_tools/flows.py`
- `../../ALLOKERING_FILKUNSKAP.md`

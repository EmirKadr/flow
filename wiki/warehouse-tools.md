---
title: Lagerverktyg
status: aktiv
updated: 2026-05-25
tags: [lagerverktyg, allokering, filer, ui]
---

# Lagerverktyg

Kort svar: Lagerverktygen ar tre vyer ovanpa `warehouse_tools`: Uppladdningar for gemensamma lokala filer, Bearbeta for floden och Dela for listdelning. Filer sparas lokalt i IndexedDB och skickas till API nar ett flode kors. Bearbeta och Dela behaller faltvarden, status och senaste resultat i aktuell browser-/desktop-session nar anvandaren byter vy och kommer tillbaka. Backend ateranvander samma uppladdade fil via innehallshash och cachar inlasta tabeller i processen for snabbare upprepade Bearbeta-korning.

## Vyer

| Vy | Fil | Syfte | Behorighet |
| --- | --- | --- | --- |
| Uppladdningar | `uppladdningar.html` | Lagg in ASK/WMS/Excel-filer i lokalt filpool | `allocationUploads` |
| Bearbeta | `bearbeta.html` | Kor kombinerade lagerfloden som Allokering, Ordersaldo, kontroller | `allocationProcess` |
| Dela | `dela.html` | Dela lang lista i kolumner | `allocationSplit` |

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

Bearbeta ar en egen sidebar-vy (`bearbeta.html`). Den ska inte beskrivas som en flik inne i Dela. Om anvandaren inte ser Bearbeta i menyn, eller ser vyn men inte kan kora floden, beror det normalt pa att rollen saknar `allocationProcess=edit` i vyatkomst. Vanliga lagerroller ser som standard Uppladdningar och Dela, men kan fa Bearbeta via Vybehorigheter.

Att andra `allocationProcess` eller `Vybehorigheter` kraver admin-/Super User-atkomst till Anvandare/installningar. En vanlig anvandare ska kontakta admin eller Super User, inte sjalv ga till Vybehorigheter.

| Flode | Kraver | Resultat |
| --- | --- | --- |
| Allokering | Detalj Kundorder, Buffertpallar; valfritt Saldo, Item option, Ej inlagrade | Allokerade pallar, near-miss, refill, pallplatser |
| Ordersaldo | Detalj Kundorder; valfritt Saldo, verksamhetens `artikel_max.csv` | Kompletta ordrar kopieras automatiskt och underskott visas med Antal pa Helpall |
| LYX-artiklar | Saldofil; valfritt verksamhetens `artikel_max.csv` | Lista LYX-artiklar |
| Pafyllnadsprio | Detalj Kundorder; valfritt Saldo, Orderoversikt, verksamhetens `artikel_max.csv` | Pafyllnadsprio, ev. lastningsfonster |
| HIB-koppling | Detalj Kundorder, Orderoversikt | Andringar och missade avgangar |
| Orderoversiktkontroll | Orderoversikt; valfritt Detalj Kundorder | Sändnings-/HIB-kontroller |
| Dispatchkontroll | Orderoversikt, Dispatchpallar; valfritt Detalj Kundorder | Dispatchavvikelser |
| Vecka 27-kontroll | Detalj Kundorder | Avvikelser/text |
| Prognosrapport | Prognos eller kampanj, samt Saldo; valfritt Buffert | Prognos vs Autoplock |

Dolda/tekniska floden finns for observations-update, observations-sync och update-check. Observations kan aven triggas automatiskt nar ny buffertfil laggs in. Observations och den framraknade karnfilen `artikel_max.csv` ar verksamhetsseparerade: Stigamo anvander legacy-filerna i `lowfreqdata/buffertpall/`, medan R3 anvander egna filer under `lowfreqdata/buffertpall/r3/`. En R3-uppladdning ska darfor inte andra Stigamos observations- eller artikel_max-underlag, och tvartom.

Allokering anvander bara orderrader med status 33 eller lagre. Orderrader med status over 33 ignoreras innan pallar matchas. Buffertpallar filtreras separat till status 29, 30 och 32 for allokering, och refill anvander status 29 och 30.

## Dela

Kontroller:

- Textarea "Varden" for en rad per varde.
- Alternativ filslot for textfil.
- Antal per kolumn.
- Knappen "Dela varden".

API: `POST /api/allokering/flow/split-values`.

Korda lagerverktygsfloden auditloggas i Historik som `allocation_flow`. Loggen sparar flodes-id, vilka filslotar/parameternamn som anvandes och hur manga resultattabeller som skapades, men inte filnamn eller inskickade listvarden. Om uppladdningen inte kan sparas, multipart-formularet inte kan lasas eller filen inte kan bearbetas loggas `upload_failed` med steg och feltyp. Om automatisk filidentifiering kraschar loggas `detect_failed`.

Bearbeta-uppladdningar sparas content-addressed i serverns temporara cachekatalog utan originalfilnamn. Nar samma fil skickas igen far den samma sokvag, och `warehouse_tools.flows` ateranvander inlast DataFrame sa lange filens storlek och modifieringstid ar oforandrade. Cachelagret rensas opportunistiskt, behaller bara ett begransat antal filer och ska bara paverka hastighet, inte resultat eller verksamhetsscope. Om samma anvandare laddar upp samma slot/filnamn med nytt innehall ersatts den tidigare cacheposten direkt.

Bearbeta-resultat lagras som temporara serversessioner. Sessionen binds till anvandaren som korde flodet, sa `Oppna i Excel`, `Ladda ner CSV` och kolumnkopiering inte kan hamta en annan anvandares resultat aven om ett session-id skulle delas.

Bearbeta och Dela sparar samtidigt arbetslaget klient-side i `sessionStorage` per inloggad anvandare och vy. Det gor att Dela-listan, antal per kolumn, Bearbetas senaste status och den senaste resultatpreviewn finns kvar nar anvandaren gar till en annan vy och sedan tillbaka i samma session. Fulla Excel-/CSV- och kolumnhamtningar anvander fortfarande serverns temporara `session_id`; om servern har startats om kan previewn synas men export/kolumnkopiering krava ny korning.

## Resultatkontroller

| Kontroll | Vad hander |
| --- | --- |
| Flodesknapp | Disabled tills kravda filer/falt finns. Visar "Kor..." medan API jobbar. |
| Info `i` | Visar flodesbeskrivning och kravda filer i popover. |
| Kopiera text | Fritextrutor, till exempel Vecka 27-rapporten, har en kopieringsikon uppe till hoger som kopierar hela rutans text och visar toasten "Text kopierad". |
| Resultattabell | Visar kolumnnamn i headern och en kopieringsikon per kolumn. Orderoversiktkontroll behaller `Avvikelsetyp` for samma Excel-/CSV-kontrakt som Allokera. |
| Oppna i Excel | Skickar session_id och tabellnyckel till `/api/allokering/open-excel`. Vid lyckad OS-start visas toasten "Excel oppnas"; om Windows/Excel inte kan oppna filen visas feltoast. |
| Ladda ner CSV | Hamter `/api/allokering/download/{session_id}/{key}`. Exporten normaliserar cellvarden som preview/Excel, t.ex. `1.0` skrivs som `1` och tomma NaN-varden blir tomma celler. |

For Allokering visas huvudtabellen `Allokerade pallar` som en vanlig resultattabell med `Oppna i Excel` och `Ladda ner CSV`, samma session som near-miss, refill och pallplatser.

Pallplatser foljer Allokeras berakning: zon `R` raknas som `autostore`, zon `F` raknas separat som `HIB` med 20 rader per toppall, och `Topp Pallar`, `Totalt Pallar` och `Pallplatser` inkluderar HIB-delen.

For Ordersaldo kopieras listan `Kompletta ordrar` till urklipp direkt nar flodet ar klart. Tabellen `Underskott` far kolumnen `Antal pa Helpall` fran `artikel_max.csv`; om anvandaren inte laddar upp en egen fil anvands karnfilen for anvandarens verksamhet.

## CLI och paritytester

Bearbeta och Dela kan koras pa tva satt fran terminalen:

- `python -m warehouse_tools.cli ...` kor flodena direkt mot `warehouse_tools/flows.py` utan server, browser, IndexedDB eller cookies. Kommandot har `list-flows`, `schema`, `detect`, `run`, `run-scenario`, `validate-scenario` och egna subcommands for varje flode, till exempel `allocate` och `split-values`.
- `python -m tools.flow_cli allocation ...` kor samma `/api/allokering`-endpoints som webb/desktop. Det anvander CLI:ns cookie jar, kan logga in med `auth login`, kor floden med multipart-filer och laddar ner fulla resultat-CSV:er fran sessionen.

Vanliga regressionskommandon:

```powershell
python -m warehouse_tools.cli list-flows
python -m warehouse_tools.cli allocate --auto-file orders.csv --auto-file buffer.csv --auto-file item_option.csv --format both --out artifacts\allocate
python -m warehouse_tools.cli split-values --values "A`nB`nC" --chunk-size 2 --out artifacts\split
python -m tools.flow_cli allocation run allocate --file orders=orders.csv --file buffer=buffer.csv --file items=item_option.csv --out artifacts\api-allocate
python -m tools.compare_warehouse_results --left .\Resultat.csv --right .\tmp6jj8twk6_allocated_orders.xlsx
```

`tools.compare_warehouse_results` normaliserar exportbrus innan jamforelse: `1.0` jamfors som `1`, och NaN/None/tomma celler blir tomma strängar. Det gor Flow-CSV mot Allokera-XLSX anvandbart som sanningskontroll.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor ar flodesknappen gra?" | Kravda filer eller textfalt saknas, eller ett annat flode kor. Klicka `i` for att se krav. |
| "Varfor hamnar filen i fel ruta?" | Automatisk detektion bygger pa filnamn/header. Anvand Välj pa exakt slot for att styra. |
| "Varfor ser jag inte Bearbeta i menyn?" | Rollen saknar normalt `allocationProcess=edit`. Be admin/Super User kontrollera Vybehorigheter. |
| "Varfor oppnas inte Excel?" | Funktionen kraver lokal desktop/OS-stod och servern maste ha kvar resultat-sessionen. Om servern startade om med `--reload`, kor flodet igen. Om Windows/Excel inte kan oppna filen automatiskt visas feltoast; testa Ladda ner CSV. |
| "Vad betyder artikel_max karnfil?" | `artikel_max.csv` kan finnas som intern karnfil aven om anvandaren inte laddat upp den. |

## Kallor

- `../app/frontend/js/allocation_tools.js`
- `../app/backend/routers/allocation.py`
- `../app/backend/allocation_bridge.py`
- `../warehouse_tools/catalog.py`
- `../warehouse_tools/cli.py`
- `../warehouse_tools/flows.py`
- `../warehouse_tools/vendor/allokering12.1.py`
- `../tools/flow_cli.py`
- `../tools/compare_warehouse_results.py`
- `../../ALLOKERING_FILKUNSKAP.md`

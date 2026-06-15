---
title: ASK datalagring (rensning och arkivering)
status: aktiv
updated: 2026-06-15
tags: [ask, datalagring, historik, rensning, arkivering, vyer]
---

# ASK datalagring (rensning och arkivering)

Kort svar: ASK/WMan kör ett schemalagt jobb som **rensar** (raderar) eller
**arkiverar** (flyttar till en separat logg-databas) tabeller i WManFrey efter ett
visst antal dagar. Det avgör hur långt bak i tiden historisk data finns kvar för
varje `v_ask_*`-vy. Reglerna ligger i
[`../vyer & kolumner/ask_rensning_och_arkivering.xml`](../vyer%20%26%20kolumner/ask_rensning_och_arkivering.xml).
Den här sidan ska läsas innan någon agent lovar historik längre bak än
retentionen tillåter, eller felsöker varför gammal data "saknas".

## Varför detta är viktigt för historisk data

`Hämta data`, `Bearbeta` och `Produktivitet` läser `v_ask_*`-vyer som i sin tur
sitter ovanpå WManFrey-tabellerna. Jobbet sätter alltså ett tak för hur långt
bak en fråga kan ge träffar:

- **`archive="true"`** – raden flyttas från `WManFrey.dbo` till
  `log_wmanfrey.dbo` efter `days` dagar. Historiken finns kvar, men i
  arkiv-databasen, och rensas där efter ~**800 dagar** (vissa kortare). En vy som
  bara läser den operativa tabellen ser då bara de senaste `days` dagarna; äldre
  data måste hämtas ur logg-databasen.
- **`archive="false"`** – raden **raderas permanent** efter `days` dagar. Ingen
  återställning. Det här är den vanligaste orsaken till att "gammal data inte
  går att hämta".
- **`noTimeColumn="true"`** – tabellen har ingen tidskolumn och beskärs inte på
  tid (rensas på annat sätt eller inte alls i tidsled).
- **`timeColumn="..."`** – anger vilken kolumn som styr åldern när den inte är
  standardkolumnen.

Tumregel: tillgänglig historik = `days` i den operativa tabellen för
read-only-vyer; för arkiverade tabeller finns djupare historik i
`log_wmanfrey` (~800 dagar) om frågan riktas dit.

## Två databaser

| Databas | Roll | Retention |
| --- | --- | --- |
| `WManFrey.dbo` | Operativ databas. Vyerna `v_ask_*` läser primärt härifrån. | Rensas eller arkiveras efter `days` per tabell. |
| `log_wmanfrey.dbo` | Arkiv-/loggdatabas. Hit flyttas `archive="true"`-tabeller. | Rensas efter ~800 dagar (PALLET_RENT_LOG_RAW: 120). |

## Retention för tabeller bakom flows ASK-vyer

De vyer flow faktiskt använder och deras underliggande retention:

| Vy (flow) | WManFrey-tabell | Operativ retention | Arkiveras? | Historik totalt |
| --- | --- | --- | --- | --- |
| `v_ask_pick_log_full` | `PICK_LOG` | 40 dagar | Ja → `log_wmanfrey` | ~800 dagar i arkivet |
| `v_ask_trans_log` | `TRANS_LOG` | 60 dagar | Ja → `log_wmanfrey` | ~800 dagar i arkivet |
| `v_ask_palletloading_log` | `LOADING_LOG` | 60 dagar | Ja → `log_wmanfrey` | ~800 dagar i arkivet |
| `v_ask_order_log` | `ORDER_LOG` | 80 dagar | Ja → `log_wmanfrey` | ~800 dagar i arkivet |
| `v_ask_pick_location_log` | `PICKLOCATION_LOG` | **40 dagar** | **Nej (endast rensning)** | **Endast 40 dagar – raderas permanent** |

> Obs: `PICKLOCATION_LOG` (plockplatsbyten) är `archive="false"`. Plockplats-
> historik finns alltså bara **40 dagar** bak och går inte att återskapa. Detta
> är viktigt för platsanalys och all historisk plockplatsuppföljning.

## Hur man läser konfigfilen

Filen är en XML-konfiguration (filändelsen var ursprungligen `.html` men
innehållet är `<table .../>`-element). Den är indelad i tre block via kommentarer:

1. `<!-- Tables that should be archived -->` – `archive="true"`, flyttas till logg-DB.
2. `<!-- Tables that should only be cleaned -->` – `archive="false"`, raderas.
3. `<!-- Clear log database -->` – retention i `log_wmanfrey` (oftast 800 dagar).

Varje rad: `server`, `database`, `schema`, `name` (tabell), `days` (ålder innan
åtgärd), `archive` (true/false), och valfritt `timeColumn`/`noTimeColumn`.

## Felsökningssvar för framtida chat

Fråga: Varför hittar jag ingen plockdata äldre än ~40 dagar i en `v_ask_pick_log_full`-fråga?
Svar: `PICK_LOG` rensas/arkiveras ur den operativa databasen efter 40 dagar. Äldre rader ligger kvar i `log_wmanfrey` i ~800 dagar men måste hämtas därifrån, inte ur den operativa vyn.

Fråga: Går det att få tillbaka plockplatsbyten från i fjol?
Svar: Nej. `PICKLOCATION_LOG` är `archive="false"` med 40 dagars retention och raderas permanent. Ingen arkivkopia finns.

Fråga: Hur långt bak kan jag i praktiken analysera plock och transporter?
Svar: Operativt så långt som tabellens `days` (t.ex. PICK_LOG 40, TRANS_LOG 60, ORDER_LOG 80). För arkiverade tabeller finns ~800 dagar i `log_wmanfrey`. För `archive="false"`-tabeller finns inget bortom `days`.

Fråga: Var ser jag exakt vilken tabell som har vilken retention?
Svar: I [`../vyer & kolumner/ask_rensning_och_arkivering.xml`](../vyer%20%26%20kolumner/ask_rensning_och_arkivering.xml). `days` + `archive` per tabell.

## Källor

- `../vyer & kolumner/ask_rensning_och_arkivering.xml` – själva rensnings-/arkiveringskonfigurationen för WMan.
- [data-fetch.md](data-fetch.md) – hur `v_ask_*`-vyer hämtas via katalog och MiniMax.
- `../vyer & kolumner/views_summary_20260521_154102.xlsx` – vy-katalog.
- `../vyer & kolumner/views_swedish_columns_commands_20260521_155519.xlsx` – kolumn-katalog.

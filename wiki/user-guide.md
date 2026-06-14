---
title: Anvandarhandbok
status: aktiv
updated: 2026-06-14
tags: [handbok, anvandare, support, chat]
---

# Anvandarhandbok

Kort svar: denna sida beskriver hur en vanlig anvandare faktiskt anvander flow. Den ar skriven for framtida LLM-chat: svara forst med vad anvandaren ska gora, sedan med varfor systemet beter sig som det gor.

## Roller i praktiken

| Roll | Vad personen normalt gor | Viktiga begransningar |
| --- | --- | --- |
| Visning | Tittar pa Bemanning och Oversikt | Kan inte spara, rensa, dra, kopiera eller andra celler. |
| Arbetsledare | Planerar dag/vecka, andrar celler, personer och aktiviteter om rollen har edit | Kan stoppas av cell-las om annan anvandare fyllt cellen. |
| Bemanningsansvarig | Samma planeringsfloden som arbetsledare, ofta bredare ansvar | Beror pa vybehorigheter. |
| Administrator | Skapar anvandare, personer, aktiviteter och settings | Kan inte automatiskt allt som Super User om rollen saknas. |
| Super User | Historik, verksamheter, avancerade importer och vissa kodandringar | Ska anvandas varsamt eftersom rollen kan andra mer. Produktivitet styrs via vybehorigheter. |
| Lagerkontorist | Uppladdningar och Dela | Bearbeta-floden kan vara blockerade utan processbehorighet. |
| Artikelplacerare | Lagerverktyg for artikel-/lagerarbete | Samma princip som lagerkontorist. |

## Kom igang

1. Oppna appen via webbadress eller Windows-appen.
2. Logga in med anvandarnamn och losenord.
3. Om det ar forsta inloggningen och kontot saknar losenord: lamna losenord tomt pa login, ga vidare till "Skapa losenord" och valj ett losenord pa minst 8 tecken.
4. Kontrollera omradesfokus nere i sidomenyn. Det styr vilka omraden som visas i vyer med omradesdata; `∞` visar alla.
5. Anvand sidomenyn for att ga till ratt vy.

## Min produktivitet

1. Ga till `Min produktivitet`.
2. Valj datum. Personrollen ser sin egen person; Super User kan valja person i rullistan.
3. Las `Idag`, `Poang/tim` och `Veckosnitt` for faktisk KPI-produktivitet fran den globala produktivitetshistoriken.
4. Granska `Dagens produktivitet` och `Veckans produktivitet` for snitt per aktivitet.
5. Om statusen sager att snapshots saknas fylls datumen av den globala historik-backfillen nar den hinner dit.

## Bemanning: planera en dag

1. Ga till `Bemanning`.
2. Valj ar, vecka och dag eller klicka datumet och valj datum direkt.
3. Vaxla omradesfokus i sidebar om du vill byta omrade eller visa alla.
4. Hitta personen med personfiltret i rubriken.
5. Las `Produktivitet`-kolumnen for en snabb procent fram till senaste avslutade KPI-timme. Tom cell betyder oftast att personen bara haft STOD/absence hittills eller saknar avslutad KPI-tid.
6. Klicka i cellens dropdown och valj aktivitet.
7. Hall musen over cellen om du vill se personens historiska snitt for aktiviteten, till exempel `70 rader/timme`. Vilka aktiviteter som far visa snitt styrs i `Installningar > Bemanning`.
8. Hogerklicka eller dubbelklicka pa en timme om den ska delas i tva halvtimmar.
9. Dra fran en cell for att fylla flera celler med samma aktivitet.
10. Anvand `Ctrl+C`, `Ctrl+X`, `Ctrl+V` nar en cell/halva ar fokuserad.
11. Anvand `Kopiera dag...` for att kopiera fran en dag till en annan.
12. Anvand `Rensa dag` bara nar hela valt datum/omrade ska tommas.
13. Titta pa `Summering per aktivitet` och `Bemanningskalkyl` efter planeringen.
14. I `Bemanningskalkyl` finns alltid `Manuell`. Klicka plus for en automatisk kalkyl, eller sok/hamta fran annan anvandare om du vill kopiera sparade automatiska kalkyler.

Viktigt: celler sparas automatiskt. Det finns ingen separat Spara-knapp.

## Oversikt: planera pa dag-niva

1. Ga till `Oversikt`.
2. Valj `Vecka` eller `Manad`.
3. Valj ar och vecka/manad.
4. Vaxla omradesfokus i sidebar om du vill filtrera omrade eller visa alla.
5. I en dagcell: valj aktivitet for att bemanna hela dagen enligt personens veckomall.
6. Om dagen ar blandad fragar systemet innan den skrivs over.
7. Dra over flera dagceller om samma aktivitet ska fyllas pa flera personer/dagar.
8. Anvand undo/redo om du angrar en oversiktsandring.

Oversikt ar grovplanering. Om du behover halvtimmar eller exakt timme: ga till Bemanning.

## Personer: lagg till och underhall personal

1. Ga till `Personer`.
2. Klicka `Ny person` for en enskild person.
3. Fyll namn, hemomrade, huvudaktivitet och sortering.
4. Klicka `Schema` for att ange veckomall.
5. Anvand `Standard 07-16` om personen normalt jobbar standarddag.
6. Markera dagar som lediga om personen inte ska ha malltid.
7. Om personen ar timmis utan fast schema: stang av fast schema i modalens checkbox.
8. For flera nya personer: klicka `Flera nya personer` och fyll tabellen direkt, eller ladda ner importmall, fyll Excel och klicka `Importera Excel`.

Inline-redigering: klicka direkt pa namn, hemomrade, huvudaktivitet eller sortering i tabellen. Andringen sparas nar faltet tappar fokus eller Enter anvands.

## Aktiviteter: skapa valbara aktiviteter

1. Ga till `Aktiviteter`.
2. Klicka `Ny aktivitet`.
3. Fyll etikett, omrade, farg, kategori och sortering.
4. Valj `Summeras som` om aktiviteten ska raknas ihop med en annan aktivitet i summeringar.
5. Satt `Arbetstyp` till `VAS` for Value Added Services. Lat `Kategori` vara arbete om personen jobbar; VAS ar inte en franvarokategori.
6. Super User kan hantera aktivitetskoder; andra ser normalt kod som read-only eller inte alls.
7. For flera aktiviteter: klicka `Flera nya aktiviteter` och fyll tabellen direkt, eller anvand importmall pa samma satt som Personer.

Tips: om en aktivitet inte dyker upp dar anvandaren forvantar sig, kontrollera omrade, aktiv-status och vy/omradesfokus.

## Anvandare och behorigheter

1. Ga till `Anvandare`.
2. Klicka `Ny anvandare`.
3. Fyll anvandarnamn, visningsnamn, roller, omrade och eventuellt losenord.
4. Om losenord lamnas tomt maste anvandaren skapa losenord vid forsta inloggning.
5. Anvand `Vybehorigheter` for att styra vilka roller som far se/redigera olika vyer.
6. For flera nya konton: klicka `Flera nya anvandare` och fyll anvandarnamn, visningsnamn, roller och omrade direkt i tabellen, eller anvand importmall.
7. Anvand checkboxen `Las bemanningsceller som andra anvandare har fyllt i` for att hindra arbetsledare fran att skriva over varandras celler.
8. `Ta bort` tar bort anvandare som inte ska finnas kvar.

Sista administratören i en verksamhet kan inte tas bort eller nedgraderas.

## Historik

1. Ga till `Historik`.
2. Valj om du vill se `Anvandarhistorik`, `Analys`, `Felkoder`, `Vantetider` eller `Halsa`.
3. Valj period.
4. Filtrera pa verksamhet, anvandare, typ, atgard eller objekt-id.
5. Klicka `Uppdatera`.
6. Anvand tabellen, analysen, felkodsdashboarden eller vantetiderna for att forklara vad som hande.

Felkodsvyn ar en felsokningsvy ovanpa auditloggen. Den visar klientrapporterade API-fel och backendfloden som auditloggats som misslyckade.

## Hamta data

1. Ga till `Hamta data`.
2. Skriv vilken extern data-vy du vill hamta, vilka kolumner du vill se och vilka filter som ska anvandas.
3. Klicka `Tolka`.
4. Kontrollera planen: vy, kolumner och filter visas innan data hamtas.
5. Lamna `Max rader` tomt for alla rader, eller fyll i ett tal om du vill begransa resultatet.
6. Klicka `Hamta data`.
7. Granska tabellpreviewn och klicka `Exportera Excel` om resultatet ska sparas.

MiniMax far bara vy-/kolumnstruktur och exempel pa fragor. API-lank och nycklar ligger i servermiljon och skickas inte till modellen.

## Produktivitet

Behorighet till vyn styrs via `Vybehorigheter` for `Produktivitet`. Visa racker for att oppna rapporten; Redigera anvands bara for manuell drift/test-sync av global snapshot.

1. Ga till `Produktivitet`.
2. Valj `Dag`, `Vecka`, `Manad` eller `Ar`.
3. Valj datumankare.
4. Las snittet pa verksamhet och omraden.
5. Klicka omrade, aktivitet eller person for att ga djupare.
6. Klicka `Exportera flowchart`, valj nivaer och exportera om aktuell vy ska sparas som SVG.
7. Klicka `Helbild` eller breadcrumbs for att backa upp i tradet.

Nar central server ar nabar anvander webb och Windows samma personrapport fran `/api/productivity`. Produktivitet bygger pa sparade globala API-snapshots och har ingen manuell produktivitetsfiluppladdning.

I `Personer` kan en anvandare med produktivitetsatkomst dubbelklicka en personrad
for att se personens aktivitetssnitt. Dialogen startar pa aktuell vecka och kan
byta till manad, ar eller egen datumperiod.

## Produktivitet

`Produktivitet` visar ett utzoomat hierarkitrad med samma globala snapshotdata
som personrapporten. Valj `Dag`, `Vecka`, `Manad` eller `Ar`; datumet ar
ankaret for perioden. Dagens poang raknas bara till och med senaste avslutade
heltimme, samma avgransning som Produktivitet-kolumnen i Bemanning.

1. Ga till `Produktivitet`.
2. Valj period och datum.
3. Las `totalpoang / KPI-timmar = snitt` pa verksamhet och omraden.
4. Las fargerna i oversikten: rod under 70, orange 70-79,9 och gron fran 80.
5. Klicka ett omrade for att se aktiviteter.
6. Klicka en aktivitet for att se personer som bidragit.
7. Klicka en person for att se timme for timme vilka processer som gav poang.
8. Klicka `Exportera flowchart`, valj nivaer och exportera for att ladda ner aktuell vy som SVG.
9. Klicka `Helbild` eller breadcrumbs for att backa upp i tradet.

Periodbyte laser sparade snapshots. Om du vaxlar tillbaka till en nyligen
hamtad period visas den fran kort cache i samma flik; saknade dagar fylls av
global backfill eller manuell sync, inte av varje knapptryck.

## Lagerverktyg

1. Ga till `Uppladdningar` och lagg in relevanta ASK/WMS-filer.
2. Ga till `Bearbeta` for allokering, ordersaldo och kontroller.
3. Klicka `i` pa ett flode for att se vilka filer som kravs.
4. Flodesknappen blir aktiv nar alla kravda underlag finns.
5. Efter korning kan resultat oppnas i Excel eller laddas ner som CSV.
6. Ga till `Dela` for att dela en lang lista i kolumner.

Om filen inte sorteras automatiskt: anvand `Valj` pa exakt filruta.

## Windows-appen

Windows-appen visar samma appyta men genom ett lokalt PyQt-skal. Den kan visa:

- laddningsvy medan servern kontrolleras
- felvy om servern inte kan nas
- uppdateringsdialog om ny release finns
- samma login, sidebar och produktvyer som webben nar allt ar friskt

Om webben fungerar men Windows inte gor det, felsok desktopprofil, lokal appserver/proxy, appversion och natverk.

## Kallor

- `../app/frontend/*.html`
- `../app/frontend/js/common.js`
- `../app/frontend/js/schedule.js`
- `../app/frontend/js/overview.js`
- `../app/frontend/js/persons.js`
- `../app/frontend/js/activities.js`
- `../app/frontend/js/users.js`
- `../app/frontend/js/data_fetch.js`
- `../app/frontend/js/productivity_overview.js`
- `../app/frontend/js/allocation_tools.js`

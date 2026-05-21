---
title: Anvandarhandbok
status: aktiv
updated: 2026-05-21
tags: [handbok, anvandare, support, chat]
---

# Anvandarhandbok

Kort svar: denna sida beskriver hur en vanlig anvandare faktiskt anvander Bemanning. Den ar skriven for framtida LLM-chat: svara forst med vad anvandaren ska gora, sedan med varfor systemet beter sig som det gor.

## Roller i praktiken

| Roll | Vad personen normalt gor | Viktiga begransningar |
| --- | --- | --- |
| Visning | Tittar pa Bemanning och Oversikt | Kan inte spara, rensa, dra, kopiera eller andra celler. |
| Arbetsledare | Planerar dag/vecka, andrar celler, personer och aktiviteter om rollen har edit | Kan stoppas av cell-las om annan anvandare fyllt cellen. |
| Bemanningsansvarig | Samma planeringsfloden som arbetsledare, ofta bredare ansvar | Beror pa vybehorigheter. |
| Administrator | Skapar anvandare, personer, aktiviteter och settings | Kan inte automatiskt allt som Super User om rollen saknas. |
| Super User | Historik, produktivitet, avancerade importer och vissa kodandringar | Ska anvandas varsamt eftersom rollen kan andra mer. |
| Lagerkontorist | Uppladdningar, Dela och Harleda | Bearbeta-floden kan vara blockerade utan processbehorighet. |
| Artikelplacerare | Lagerverktyg for artikel-/lagerarbete | Samma princip som lagerkontorist. |

## Kom igang

1. Oppna appen via webbadress eller Windows-appen.
2. Logga in med anvandarnamn och losenord.
3. Om det ar forsta inloggningen och kontot saknar losenord: lamna losenord tomt pa login, ga vidare till "Skapa losenord" och valj ett losenord pa minst 8 tecken.
4. Kontrollera omradesfokus nere i sidomenyn. Det paverkar vilka omraden som prioriteras i flera vyer.
5. Anvand sidomenyn for att ga till ratt vy.

## Bemanning: planera en dag

1. Ga till `Bemanning`.
2. Valj ar, vecka och dag eller klicka datumet och valj datum direkt.
3. Valj omrade. Tomt/Alla visar alla personer.
4. Hitta personen med personfiltret i rubriken.
5. Klicka i cellens dropdown och valj aktivitet.
6. Hogerklicka eller dubbelklicka pa en timme om den ska delas i tva halvtimmar.
7. Dra fran en cell for att fylla flera celler med samma aktivitet.
8. Anvand `Ctrl+C`, `Ctrl+X`, `Ctrl+V` nar en cell/halva ar fokuserad.
9. Anvand `Kopiera dag...` for att kopiera fran en dag till en annan.
10. Anvand `Rensa dag` bara nar hela valt datum/omrade ska tommas.
11. Titta pa `Summering per aktivitet` och `Bemanningskalkyl` efter planeringen.

Viktigt: celler sparas automatiskt. Det finns ingen separat Spara-knapp.

## Oversikt: planera pa dag-niva

1. Ga till `Oversikt`.
2. Valj `Vecka` eller `Manad`.
3. Valj ar och vecka/manad.
4. Valj omrade om du vill filtrera.
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
8. For massimport: ladda ner importmall, fyll Excel och klicka `Importera Excel`.

Inline-redigering: klicka direkt pa namn, hemomrade, huvudaktivitet eller sortering i tabellen. Andringen sparas nar faltet tappar fokus eller Enter anvands.

## Aktiviteter: skapa valbara aktiviteter

1. Ga till `Aktiviteter`.
2. Klicka `Ny aktivitet`.
3. Fyll etikett, omrade, farg, kategori och sortering.
4. Valj `Summeras som` om aktiviteten ska raknas ihop med en annan aktivitet i summeringar.
5. Super User kan hantera aktivitetskoder; andra ser normalt kod som read-only eller inte alls.
6. Import fungerar med mall pa samma satt som Personer.

Tips: om en aktivitet inte dyker upp dar anvandaren forvantar sig, kontrollera omrade, aktiv-status och vy/omradesfokus.

## Anvandare och behorigheter

1. Ga till `Anvandare`.
2. Klicka `Ny anvandare`.
3. Fyll anvandarnamn, visningsnamn, roller, omrade och eventuellt losenord.
4. Om losenord lamnas tomt maste anvandaren skapa losenord vid forsta inloggning.
5. Anvand `Vybehorigheter` for att styra vilka roller som far se/redigera olika vyer.
6. Anvand checkboxen `Las bemanningsceller som andra anvandare har fyllt i` for att hindra arbetsledare fran att skriva over varandras celler.
7. `Visa inaktiva` visar anvandare som annars ar dolda.

Sista aktiva administratören kan inte inaktiveras eller nedgraderas.

## Historik

1. Ga till `Historik`.
2. Valj period.
3. Filtrera pa anvandare, typ, atgard eller objekt-id.
4. Klicka `Uppdatera`.
5. Anvand tabellen for att forklara vem som andrade objektet och nar.

Historik ar inte en generell "fel-logg"; den visar auditlogg for muterande appfloden.

## Hamta data

1. Ga till `Hamta data`.
2. Skriv vilken extern data-vy du vill hamta, vilka kolumner du vill se och vilka filter som ska anvandas.
3. Klicka `Tolka med MiniMax`.
4. Kontrollera planen: vy, kolumner och filter visas innan data hamtas.
5. Klicka `Hamta data`.
6. Granska tabellpreviewn och klicka `Exportera Excel` om resultatet ska sparas.

MiniMax far bara vy-/kolumnstruktur och exempel pa fragor. API-lank och nycklar ligger i servermiljon och skickas inte till modellen.

## Produktivitet

1. Ga till `Produktivitet`.
2. Lagg in Plocklogg, Translogg och Palllastningslogg via dropzoner eller filval.
3. Kontrollera att KPI-mal finns. KPI ar permanent serverdata.
4. Valj datum.
5. Filtrera med `Block` och `Sok`.
6. Byt datum med pilarna om datasetet har narliggande datum.

Stora loggfiler ar lokala per dator/browserprofil. Tva anvandare kan darfor ha olika produktivitetsunderlag men samma KPI-mal.

## Lagerverktyg

1. Ga till `Uppladdningar` och lagg in relevanta ASK/WMS-filer.
2. Ga till `Bearbeta` for allokering, ordersaldo och kontroller.
3. Klicka `i` pa ett flode for att se vilka filer som kravs.
4. Flodesknappen blir aktiv nar alla kravda underlag finns.
5. Efter korning kan resultat oppnas i Excel eller laddas ner som CSV.
6. Ga till `Dela` for att dela en lang lista i kolumner.
7. Ga till `Harleda` for att soka inkop/artikel genom WMS-loggar.

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
- `../app/frontend/js/productivity.js`
- `../app/frontend/js/allocation_tools.js`

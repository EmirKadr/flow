---
title: Felsokning och framtida LLM-chat
status: aktiv
updated: 2026-05-22
tags: [felsokning, chat, support]
---

# Felsokning och framtida LLM-chat

Kort svar: nar en anvandare fragar "varfor funkar inte X?" ska chatten oversatta symptom till vy, knapp, behorighet, dataunderlag och API-fel. Fraga alltid efter exakt vy, knapp och toast/feltext om svaret inte ar uppenbart.

## Snabb triage

1. Vilken vy ar anvandaren pa?
2. Vilken knapp/kontroll anvands?
3. Ar knappen dold, disabled, eller klickbar men ger fel?
4. Vilken roll har anvandaren?
5. Finns toast/felmeddelande?
6. Galler det webb eller Windows-app?
7. Om filimport: vad heter filen och vilka rubriker har den?
8. Om API/statuskod syns: sla upp den i [Felkoder och felmeddelanden](error-reference.md).

## Symptom till rotorsak

| Symptom | Trolig rotorsak | Svar/atgard |
| --- | --- | --- |
| Vy saknas i menyn | Rollens vyatkomst ar `none` | Be admin/Super User kontrollera Anvandare -> Vybehorigheter. Skriv inte att anvandaren sjalv ska gora det om de saknar adminatkomst. |
| Knapp for import saknas | Importvyn saknar edit-atkomst | Kontrollera `personImport`, `activityImport` eller `userImport`. |
| Cell i Bemanning gar inte att andra | Read-only, cell-las, konflikt eller saknad edit-roll | Kontrollera toast; admin kan passera cell-las, viewer kan aldrig redigera. |
| "Cellen andrades av nagon annan" | Versionskonflikt | Serverns senaste varde vann; gor andringen igen efter omladdning. |
| Undo/redo fungerar inte | Tom stack eller fel dag | Undo/redo ar lokal och knuten till dagen/perioden dar andringen gjordes. |
| Produktivitet visar inte rapport | Saknade lokala loggar eller KPI-mal | Lagg in Plocklogg, Translogg, Palllastningslogg och KPI-mal. |
| Lagerflode ar disabled | Kravda filer/falt saknas | Klicka `i` pa flodet eller se filtaggar med kryss. |
| Bearbeta saknas | Rollen saknar `allocationProcess` eller Super User | Bearbeta ar egen vy. Be admin/Super User kontrollera roll och Vybehorigheter. Vanlig lagerroll ser oftast Dela men inte Bearbeta. |
| Fil hamnar inte i ratt slot | Filnamn/header matchar inte detektion | Anvand Välj pa specifik slot eller kontrollera filens rubriker. |
| Anvandare maste skapa losenord | Kontot saknar password_hash/must_change_password | Ga via `set-password.html`; losenord minst 8 tecken. |
| Kan inte inaktivera admin | Sista aktiva admin skyddas | Skapa/aktivera annan admin forst. |
| Apphjalpen svarar inte | MiniMax-nyckel saknas, timeout, 10-fragorskvot eller session saknas | Las feltexten i chattpanelen. Vid kvot: `Rensa dialog`. Vid `MINIMAX_API_KEY`: admin konfigurerar servern. |
| Apphjalpen minns gamla fragor | Dialogen skickas med for foljdfragor och sparas i sessionen | Klicka `Rensa dialog` om sammanhanget ska starta om. |
| Enter sparar inte en dialog | Fokus ligger pa knapp/checkbox/flerradigt textfalt, eller primarknappen ar disabled | Klicka primarknappen eller flytta fokus till ett vanligt falt. Enter i vanliga modalfalt ska klicka `Spara`/`Skapa`/`Stang`. |
| Desktop visar gammalt/annat beteende | Cachad lokal frontend/proxy eller inte uppdaterad build | Testa webben, desktop-proxy och version; jamfor mot `APP_MIGRATION_PLAN.md`. |

## Rekommenderade chattsvar

### "Varfor kan jag inte klicka?"

Kontrollera forst om knappen ar disabled. Om den ar disabled brukar det bero pa saknad behorighet, saknat underlag eller att en annan operation pagar. Om den ar helt borta ar det nastan alltid roll-/vybehorighet.

### "Hur importerar jag Excel?"

Ga till ratt register, ladda ner importmallen, fyll filen med samma rubriker, klicka Importera Excel och valj `.xlsx`. Om anvandaren inte vill anvanda Excel kan de klicka `Flera nya ...` i Personer, Aktiviteter eller Anvandare och fylla samma falt direkt i tabellen. Om resultatmodalen visar hoppade rader, lasa radfelen och korrigera dubbletter/rubriker.

### "Hur lagger jag in flera utan Excel?"

Ga till Personer, Aktiviteter eller Anvandare och klicka knappen `Flera nya ...`. Fyll en rad per nytt objekt och klicka skapa. Tomma rader ignoreras, och resultatmodalen visar dubbletter, okanda omraden eller andra radfel.

### "Varfor syns inte min andring i historik?"

Kontrollera period, anvandare, typ och atgard. Historik visar bara floden som faktiskt auditloggas. Vissa system-/seedhandelser kan sakna anvandare.

### "Hur vet jag om problemet ar webben eller Windows-appen?"

Testa samma anvandare och samma data i webben. Om webben fungerar men Windows inte gor det, fokusera pa desktop local appserver, cookies/session, cachad frontend och appversion. Om båda faller ar felet sannolikt API/data/behorighet.

## Sidor att lasa for djupare svar

- [Anvandarhandbok](user-guide.md)
- [Anvandarhandelser](user-events.md)
- [Felkoder och felmeddelanden](error-reference.md)
- [Apphjalp och LLM-chatt](app-chat.md)
- [UI-karta och alla kontroller](ui-map.md)
- [Bemanning](bemanning-schedule.md)
- [Oversikt](overview-page.md)
- [Personer](persons.md)
- [Aktiviteter och omraden](activities-areas.md)
- [Anvandare och installningar](users-settings.md)
- [Produktivitet](productivity.md)
- [Lagerverktyg](warehouse-tools.md)

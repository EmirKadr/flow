---
title: Anvandarhandelser
status: aktiv
updated: 2026-05-26
tags: [anvandare, handelser, toast, state, chat]
---

# Anvandarhandelser

Kort svar: denna sida listar vad anvandaren kan se eller raka ut for: redirect, laddning, tomma lagen, disabled knappar, confirm-dialoger, success/warn/error-toastar och konflikter.

## Globala handelser

| Handelse | Anvandaren ser | Orsak | Ratt svar |
| --- | --- | --- | --- |
| Inte inloggad | Skickas till login | API svarar 401 pa skyddad sida | Logga in igen. Sessionen saknas eller har gatt forlorad. |
| Forsta losenord kravs | Skickas till `Skapa losenord` | API svarar 403 `password_setup_required` | Skapa losenord minst 8 tecken. |
| Saknar vybehorighet | Toast "Sidan kraver behorighet" och redirect | Rollen har inte `view` pa vyn | Be admin/Super User andra Vybehorigheter. Vanlig anvandare kan normalt inte gora det sjalv. |
| Saknar redigeringsbehorighet | Knapp dold/disabled eller toast | Rollen har bara `view` | Be om `edit` for vyn eller anvand laslage. |
| Server kan inte nas | "Kunde inte ansluta till servern..." | Backend nere, fel adress eller appen oppnad som fil | Oppna ratt URL/starta lokal server/kontrollera natverk. |
| API-fel loggas | Ingen extra UI-storning | Frontend far 4xx/5xx eller natverksfel fran API | Felet rapporteras tyst som `client_error` nar anvandaren ar inloggad, sa Super User kan felsoka i Historik > Felkoder. Galler aven Bearbeta. |
| Vy oppnas | Ingen rad i dokumentloggen | Sidan rapporterar tyst `view/open` till Historik | Anvands for sparad audit, inte for snabb felsokningslogg. |
| Dokument-logg fylls | Dokument-ikonen visar success/info/varning/fel och kan rensas | Funktioner, importer, exporter, bakgrundsvarningar och API-wrappern skriver till en sessionlagrad loggpanel | Oppna dokument-ikonen for snabb felsokning; loggen foljer med vid sidbyte i samma browserflik men ska inte fyllas av vanliga sidbyten. Anvand Historik for sparad audit. |
| Bakgrundsladdning misslyckas | Warn-rad i dokumentloggen | En forvarmning/cachehamtning kunde inte hamtas utan att stoppa vyn | Fortsatt jobba; om samma varning upprepas, ladda om eller kontrollera backend/natverk. |
| Tema andras | Ikon/vy byter ljust/morkt | Tema sparas lokalt | Inget fel; per enhet/browser. |
| Sidebar kollapsas | Bara ikoner syns | Anvandaren klickade hamburgare | Klicka hamburgare igen. |
| Omradesfokus andras | Berorda vyer filtreras till valt omrade eller alla | MG/GG/AS/EH/Alla toggle | Vaxla fokus nere i sidebar. Bemanning och Oversikt anvander bakgrundscache for snabb vaxling nar perioden redan ar hamtad. `∞` visar alla synliga omraden. |
| Enter i dialogruta | Primar knapp klickas | Fokus ligger i en modal och anvandaren trycker Enter | Anvands for att spara, skapa eller stanga. Shift+Enter och flerradiga textfalt paverkas inte. |
| Apphjalp oppnas/stangs | Liten chattpanel visas eller doljs | Anvandaren klickar pratbubbelikonen under omradesfokus | Panelen kan vara oppen medan anvandaren navigerar. |
| Apphjalp skickar fraga | Fragan laggs i dialogen och svar hamtas | Anvandaren trycker Enter i textfaltet eller klickar `Skicka` | `Shift+Enter` ger ny rad om anvandaren vill skriva flera rader. |

## Login och losenord

| Handelse | Text | Betydelse | Atgard |
| --- | --- | --- | --- |
| Fel login | "Felaktigt anvandarnamn eller losenord" | Namn finns inte, kontot ar borttaget eller losenord fel | Kontrollera konto/losenord. |
| Forsta login med ifyllt losenord | "Lamna losenordet tomt vid forsta inloggningen" | Kontot har inget losenord an | Logga in med tomt losenord och skapa nytt. |
| For kort nytt losenord | "Losenord maste vara minst 8 tecken" | Klientvalidering | Ange minst 8 tecken. |
| Losenord matchar inte | "Losenorden matchar inte" | Bekraftelse skiljer sig | Skriv samma losenord i bada falt. |
| Losenord redan skapat | "Losenord ar redan skapat" | Konto forsoker set-password trots att det redan finns | Logga in vanligt eller aterstall via adminflode. |

## Bemanning

| Handelse | Text/reaktion | Orsak | Atgard |
| --- | --- | --- | --- |
| Read-only | "Visningslage: du kan se bemanningen men inte andra den." | Rollen har bara `view` | Be admin ge edit eller anvand vyn som laslage. |
| Last cell | "Cellen ar last eftersom en annan anvandare har fyllt i den." | `lock_foreign_schedule_cells` aktiv och annan anvandare ager cellen | Admin kan andra; annars be agaren/admin. |
| Versionskonflikt | "Cellen andrades av nagon annan - laste in pa nytt" | Nagon sparade samma cell forst | Upprepa andringen efter omladdning. |
| Split lyckas | "Cellen delades i tva halvtimmar." | Hogerklick/dubbelklick pa hel cell | Välj aktivitet per halva. |
| Merge lyckas | "Cellen slogs ihop till en hel timme." | Hogerklick/dubbelklick pa delad cell | Kontrollera aktivitet efter sammanslagning. |
| Drag for stort | "For manga celler eller halvor (max 200)" | Dragmarkerade for mycket | Dela upp i mindre drag. |
| Drag konflikt | "X konflikter - laser om" | Nagra celler hann andras | Kontrollera resultat och gor om vid behov. |
| Ctrl utan fokus | "Ctrl+C: klicka forst pa en cell" | Ingen fokuserad cell | Klicka/fokusera cell och prova igen. |
| Undo fel dag | "Byt tillbaka till dagen..." | Undo-stackens andring hor till annan dag | Ga tillbaka till dag dar andringen gjordes. |
| Rensa confirm | "Rensa hela dagen for det valda omradet?" | Skydd mot massandring | Avbryt om du ar osaker; annars OK. |
| Narvarande hamtas | "Hamtar narvarolista..." och sedan "Narvarolista oppnas for utskrift (X personer)." | Anvandaren klickar `Narvarande` och valjer omfang | Printdialogen oppnas; Alla omraden skrivs ut per verksamhet. |
| Narvarande tom | "Inga narvarande hittades for den valda dagen och tiden." | Ingen person uppfyller work/icke-franvaro-reglerna | Kontrollera dag, tid och omradesval. |

## Oversikt

| Handelse | Text/reaktion | Orsak | Atgard |
| --- | --- | --- | --- |
| Read-only | "Visningslage: du kan se oversikten men inte andra den." | Rollen har bara `view` | Be om edit-atkomst. |
| Blandad dag confirm | "Denna dag har flera olika aktiviteter. Skriv over med samma varde?" | Dagen har flera aktiviteter/segment | OK skriver over hela dagen; Avbryt bevarar. |
| Drag for stort | "For manga celler (max 100)" | For manga dagceller markerade | Dela upp draget. |
| Heldag sparad | "Bemannade X h, tog bort Y h" | Oversikt skrev/tomde dag enligt mall | Kontrollera Bemanning om timmarna ser ovantade ut. |
| Drag klar med fel | "Drag klar: skrev X h, tog bort Y h, Z fel" | Bulk gjorde vissa dagar men inte alla | Kontrollera dagarna som inte andrades. |
| Narvarande | Samma toastar som i Bemanning | Knappen anvander Bemannings schema for vald/klickad dag | Klicka ratt dag i Oversikt innan utskrift om perioden visar flera dagar. |

## Register: personer, aktiviteter, anvandare

| Handelse | Text/reaktion | Orsak | Atgard |
| --- | --- | --- | --- |
| Namn kravs | "Namn kravs" | Ny/redigera person saknar namn | Fyll namn. |
| Etikett kravs | "Etikett kravs" | Ny/redigera aktivitet saknar etikett | Fyll etikett. |
| Anvandarnamn kravs | "Anvandarnamn kravs" | Konto saknar anvandarnamn | Fyll anvandarnamn. |
| Välj minst en roll | "Valj minst en roll" | Konto saknar roll | Kryssa i roll. |
| Kort losenord | "Losenord maste vara minst 8 tecken" | Admin anger for kort losenord | Ange minst 8 tecken eller lamna tomt. |
| Import skapade rader | "X importerades" | Import lyckades | Kontrollera listan. |
| Import hoppade rader | "X importerades. Y rad(er) hoppades over." | Delvis import med radfel | Oppna resultatmodal och korrigera. |
| Direktimport utan rader | "Fyll minst en rad." | Anvandaren klickade skapa i direkttabellen utan ifyllda rader | Fyll minst en rad eller avbryt. |
| Import tom | "Importen inneholl inga..." | Filen eller direkttabellen hade inga giltiga rader | Kontrollera rubrikrad/innehall eller fyll direkttabellen. |
| Ta bort confirm | "Ta bort ... permanent?" | UI-confirm fore borttagning | Personer, aktiviteter och anvandare tas bort; omraden kan inaktiveras om de har kopplad data. |
| Sista admin stoppas | "Det maste finnas minst en administrator kvar" | Skyddsregel | Skapa eller ge adminroll till en annan anvandare forst. |

## Produktivitet

| Handelse | Text/reaktion | Orsak | Atgard |
| --- | --- | --- | --- |
| Saknar underlag | "Saknar produktivitetsunderlag." | En eller flera lokala loggar saknas | Lagg in Plocklogg, Translogg och Palllastningslogg. |
| Beraknar lokalt | "Beraknar produktivitet lokalt..." | Browsern laser stora filer | Vanta; byt inte fil mitt i lasning. |
| Saknar datum | "Produktivitetsunderlagen saknar datum" | Loggarna kunde inte ge datumnycklar | Kontrollera filtyp/header/datumkolumner. |
| Saknar data for datum | "Saknar produktivitetsdata for YYYY-MM-DD" | Vald dag finns inte i loggarna | Valj datum som finns i underlaget. |
| Filuppladdning saknas | "Filuppladdningen ar inte laddad." | `productivityUploads` saknas/JS laddade inte | Ladda om sidan, kontrollera JS-fel. |
| Okand filtyp | Toast med okand fil | Filnamn/header matchar inte | Anvand ratt exportfil eller slot. |

## Apphjalp

| Handelse | Text/reaktion | Orsak | Atgard |
| --- | --- | --- | --- |
| Dialog sparas | Gamla fragor/svar syns efter sidbyte | `sessionStorage` bevarar dialogen i aktuell session | Normalt beteende; klicka `Rensa dialog` for att borja om. |
| Max fragor | "Max natt. Rensa dialog for att fortsatta." | 10 lyckade fragor ar anvanda | Klicka `Rensa dialog`. |
| Skickar | Skicka-knappen visar "Skickar..." och textfaltet ar disabled | Ett MiniMax-anrop pagar | Vanta pa svar. |
| API-nyckel saknas | Feltext namner `MINIMAX_API_KEY` | Servern saknar MiniMax-nyckel | Admin satter nyckeln i servermiljon. |
| Timeout | "MiniMax svarade inte i tid" | Modell-API eller natverk tog for lang tid | Forsok igen senare. |

## Lagerverktyg

| Handelse | Text/reaktion | Orsak | Atgard |
| --- | --- | --- | --- |
| Fil kunde inte sorteras | "Kunde inte sortera: filnamn" | Detektion missade filtyp | Anvand `Valj` pa ratt slot eller kontrollera rubriker. |
| Flode disabled | Knapp ar gra | Kravda filer/falt saknas eller flode kor | Klicka `i` for krav och lagg in saknade filer. |
| Okant flode | "Okant flode: ..." | Frontend/backend-katalog ur synk | Ladda om, kontrollera deploy/version. |
| Forecast utan rader | "Flodet fick inga rader att sammanstalla..." | Forecast/underlaget gav inga rader efter inlagda filer och vald GG/MG/annan toggle/filter | Kontrollera att ratt orderdetalj och coredata finns och att vald toggle inte filtrerar bort allt. Historik > Felkoder visar tekniskt meddelande, t.ex. `No objects to concatenate`. |
| Resultatet hittades inte | "Resultatet hittades inte (kor flodet igen)" | Resultatsession saknas/stadad | Kor flodet igen. |
| Saknar Excel-skrivare | "Saknar Excel-skrivare..." | Servermiljo saknar openpyxl/xlsxwriter | Anvand CSV eller installera beroende. |
| Excel oppnas | "Excel oppnas" | `/open-excel` skapade filen och skickade oppningskommando till OS | Vanta pa Excel eller kontrollera aktivitetsfaltet. |
| Excel kunde inte oppnas | "Kunde inte oppna Excel-filen automatiskt..." | OS/Excel kunde inte starta filen eller exporten misslyckades | Kor om flodet, kontrollera lokal Excel-installation eller anvand CSV. |
| Dela saknar varden | "Inga varden angivna..." | Tom textarea/fil | Klistra in varden eller valj textfil. |

## Desktop

| Handelse | Anvandaren ser | Orsak | Atgard |
| --- | --- | --- | --- |
| Laddningsvy | Appen startar men visar laddning | Health check/appserver startar | Vanta nagra sekunder. |
| Anslutningsfel | Felvy i Windows-skalet | Servern kan inte nas | Kontrollera internet/server eller testa webben. |
| "Ansluten till servern" | Statusbar | Health check OK | Fortsatt anvand appen. |
| Uppdatering finns | Dialog | GitHub Releases har ny Setup.exe | Ladda ner/installera om det ar forvantat. |
| Lokal SQLite-sync stoppas | Text om att `flow_local.db` anvands av annan process | Gammal `start_local.bat`/`uvicorn` haller databasen oppen | Kor `stop_local.bat`, vanta nagon sekund och starta sedan igen. |

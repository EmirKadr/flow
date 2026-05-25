---
title: Apphjalp och LLM-chatt
status: aktiv
updated: 2026-05-22
tags: [chat, llm, minimax, support, sidebar]
---

# Apphjalp och LLM-chatt

Kort svar: Apphjalpen ar en liten chattpanel i sidomenyn. Knappen sitter direkt under omradesfokus/infinity-markeringen. Den kan vara oppen medan anvandaren navigerar mellan sidor och dialogen sparas i aktuell browser-/desktop-session.

## Anvandarflode

1. Anvandaren klickar pratbubbelikonen under infinity-/omradesfokusknappen i sidebar.
2. En liten panel med rubriken `Apphjalp` oppnas utan modal-backdrop. Resten av appen gar fortfarande att anvanda.
3. Anvandaren skriver en fraga i textfaltet och klickar `Skicka` eller trycker Enter. `Shift+Enter` ger ny rad.
4. Frontend visar en liten rund laddningsanimation i chattflodet och skickar hela dialogen till `POST /api/assistant/chat`, tillsammans med aktuell `page_path`.
5. Backend bygger en systemprompt med wikiutdrag och skickar fragan till MiniMax.
6. Svaret laggs in i dialogen och sparas i `sessionStorage`.
7. Om anvandaren byter sida i samma session oppnas panelen igen om den var oppen, med samma dialog.
8. Anvandaren stanger panelen genom att klicka pratbubbelikonen igen.

## Knappar och kontroller

| Kontroll | Var | Vem far | Vad hander | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- | --- |
| Apphjalp/pratbubblor | Sidebar utility, under omradesfokus/infinity | Alla inloggade anvandare | Vaxlar panelen oppen/stangd och sparar oppet lage i sessionen | `common.js`, `assistant-toggle` | Om knappen saknas ar sidan inte skyddad/inloggad eller `common.js` laddades inte. |
| Textfalt | Chattpanelens botten | Alla inloggade | Sparar utkast i sessionen. Enter skickar fragan, `Shift+Enter` ger ny rad | `assistant-chat-input` | Tom fraga skickas inte. Max 1200 tecken i UI, max 4000 per rad i API. |
| Skicka | Chattpanelen | Alla inloggade under kvoten | Skickar hela dialogen plus aktuell sida till backend | `POST /api/assistant/chat` | Disabled vid pagaende fraga eller nar 10 fragor ar anvanda. |
| Rensa dialog | Chattpanelen | Alla inloggade | Rensar lokal dialog, utkast och frageraknare; nollstaller serverns sessionskvot | `POST /api/assistant/clear` | Om servern inte nas rensas UI lokalt men kvoten kan finnas kvar pa servern tills sessionen byts. |

## Sessionsregler

- Dialogen sparas i `sessionStorage` under aktuell browserflik eller desktop-webbvy.
- Under pagaende API-anrop visas en assistant-bubbla med spinner och texten `Hamtar svar`.
- Oppet/stangt lage sparas i `flow-assistant-chat-open`.
- Dialograder sparas i `flow-assistant-chat`.
- Utkast sparas i `flow-assistant-chat-draft`.
- Lokal frageraknare sparas i `flow-assistant-chat-count`.
- Lokal chattdata versioneras med `flow-assistant-chat-version`; nar lagringsformatet andras rensar frontend gammal lokal data vid nasta sidladdning.
- Backend har ocksa en sessionskvot i server-sessionen: max 10 lyckade MiniMax-fragor.
- Raknaren visar anvanda fragor i hela aktuell session, inte bara synliga fragor i panelen. Om panelen visar `5/10 fragor i sessionen` efter en synlig fraga betyder det normalt att fyra lyckade fragor redan har skickats tidigare i samma server-/browser-session.
- `Rensa dialog` nollstaller lokal dialog, lokalt utkast, lokal raknare och backendens kvot for aktuell session, men haller panelen oppen.
- Logout rensar server-sessionen eftersom `/api/auth/logout` gor `request.session.clear()` och frontend rensar samtidigt apphjalpens lokala `sessionStorage`. Efter ny inloggning ska raknaren starta pa `0/10`.

## Teknisk prompt och kunskapsbas

Backendens systemprompt sager att modellen ar `Apphjalpen for flow`, ska svara pa svenska med korrekta `å`, `ä` och `ö`, vara konkret, inte gissa utan wiki-stod och be om exakt vy/knapp/feltext nar information saknas.

Backend lagger in en begransad anvandarkontext i prompten for att chatten ska kunna svara pa behorighetsfragor utan att gissa. Kontexten innehaller:

- visningsnamn och anvandarnamn
- primar roll och alla roller
- om anvandaren ar Super User
- om anvandaren ar aktiv och om losenordsskapande fortfarande kravs
- anvandarens omrade om det finns
- effektiva vybehorigheter grupperade som `edit`, `view` och `none`
- aktuell sidas vybehorighet, till exempel `Dela (allocationSplit) = none`

Kanslig information skickas inte till MiniMax: inga losenord, password hashes, sessioncookies, API-nycklar, tokens eller hemliga env-varden. Chatten ska anvanda anvandarkontexten for att ge direkta svar som "du saknar `Dela`" eller "du har bara `view`, inte `edit`", men den ska fortfarande saga att admin/Super User maste andrar `Vybehorigheter`.

Svar ska formateras for en smal chattpanel: korta stycken, korta punktlistor, fet kort rubrik hellre an `##`, och inga markdown-tabeller om det gar att undvika. Frontend kan rendera enklare Markdown som fetstil, inline-kod, listor, rubriker och tabeller, men tabeller blir snabbt tranga.

Wikin ar hard grans for normalfragor: om wikin inte sager att en funktion, knapp, vy eller export finns ska chatten svara nej/inte dokumenterat och inte foresla troliga API-vagar, Swagger eller generiska exportknappar. Om anvandaren invander, till exempel "jo det finns visst" eller "kolla hela repot", lagger backend till en begransad textsokning i repo:t som extra kontext sa chatten kan ge ett tydligare ja/nej.

Behorighetsrad ska skrivas fran vanlig anvandares perspektiv. Om losningen kraver `Anvandare`, `Vybehorigheter`, rollandring, admin eller Super User ska chatten inte saga att anvandaren sjalv ska ga dit. Skriv i stallet: "Be en admin eller Super User kontrollera ..." och forklara vad admin ska kontrollera. Exempel: om Bearbeta saknas ska chatten saga att Bearbeta ar en egen sidebar-vy och att admin/Super User behover kontrollera att rollen har `allocationProcess=edit`.

Kunskapen kommer fran `wiki/*.md`. Backend laser alltid basdokument:

- `index.md`
- `user-guide.md`
- `user-events.md`
- `error-reference.md`
- `troubleshooting-chat.md`
- `ui-map.md`

Backend lagger dessutom till sidrelevant dokument, till exempel:

- `/index.html` -> `bemanning-schedule.md`
- `/overblick.html` -> `overview-page.md`
- `/personer.html` -> `persons.md`
- `/anvandare.html` -> `users-settings.md`
- `/produktivitet.html` -> `productivity.md`
- `/uppladdningar.html`, `/bearbeta.html`, `/dela.html` -> `warehouse-tools.md`

Darefter rankas fler wiki-filer efter ord i anvandarens senaste fraga. Modellen far alltsa inte direkt kora egen reposokning, men den far en kuraterad wiki-kontext byggd fran repot. Det ar avsiktligt for att inte skicka hemligheter eller hela kodbasen till modellen.

Vid invandningar eller uttryckliga kodkontroller kor backend en textsokning i repo:t over tillatna textfiler. Hemliga filer som `.env`, databaser, buildkataloger och virtuella miljoer exkluderas.

## API och konfiguration

| Inställning | Standard | Betydelse |
| --- | --- | --- |
| `MINIMAX_API_KEY` | tom | Obligatorisk serverhemlighet. Om den saknas svarar chatten 503. |
| `MINIMAX_API_URL` | `https://api.minimax.io/v1/chat/completions` | MiniMax OpenAI-kompatibel endpoint. |
| `MINIMAX_MODEL` | `MiniMax-M2.7` | Modellnamn som skickas i payload. |
| `MINIMAX_MAX_TOKENS` | `700` | Max svarslangd fran modellen. |
| `MINIMAX_TIMEOUT_SECONDS` | `30` | Timeout mot MiniMax. |

Backend anropar MiniMax server-side med `Authorization: Bearer ...` sa API-nyckeln aldrig hamnar i frontend.

## Fel och anvandarsvar

| Status/text | Orsak | Bra chattsvar |
| --- | --- | --- |
| `503 Appchatten saknar MINIMAX_API_KEY...` | Servern saknar API-nyckel | "Chatten ar inte aktiverad pa servern. Be admin satta `MINIMAX_API_KEY` och starta om." |
| `504 MiniMax kunde inte nas inom timeout.` | Modell-API svarade inte i tid | "Prova igen om en stund. Om det upprepas, kontrollera natverk eller MiniMax-status." |
| `502 MiniMax svarade HTTP ...` | MiniMax nekade eller gav fel payload | "Kopiera feltexten. Admin behover kontrollera API-nyckel, kvot, modellnamn och MiniMax-svar." |
| `429 Max 10 fragor per session...` | Backendens sessionskvot ar slut | "Klicka Rensa dialog om du vill borja om och nollstalla kvoten." |
| `400 Den senaste dialograden maste vara en anvandarfraga.` | Frontend skickade fel dialogformat | "Ladda om sidan. Om det fortsatter ar det ett frontendfel." |
| `401/403` | Session saknas eller forsta losenord kravs | Logga in igen eller skapa losenord. |

## Felsokningssvar for framtida chat

### "Varfor far jag inte svar?"

Kontrollera om panelen visar en feltext. Om texten namner `MINIMAX_API_KEY` ar chatten inte konfigurerad pa servern. Om den namner timeout kan MiniMax eller natverket vara segt. Om du blev skickad till login har sessionen gatt ut.

### "Varfor kan jag bara fraga 10 ganger?"

Chatten har en sessionsgrans pa 10 lyckade fragor for att halla kostnad och fel-loopar under kontroll. Klicka `Rensa dialog` for att nollstalla dialogen och borja om i samma session.

### "Varfor star raknaren pa 5/10 fast jag bara stallt en fraga?"

Raknaren kommer fran sessionen, inte bara det som syns i panelen. Om anvandaren inte har klickat `Rensa dialog` eller om frontend hade gammal lokal `sessionStorage` kan gamla fragor synas i raknaren. Efter logout/login ska frontend numera rensa lokal apphjalpsdata. Gammal lokal chattdata rensas ocksa automatiskt nar ny lagringsversion laddas. Om det anda ser fel ut: klicka `Rensa dialog` och ladda om sidan.

### "Varfor kommer gamla meddelanden med?"

Det ar medvetet. Varje ny fraga skickar hela dialogen sa modellen forstar foljdfragor. Rensa dialogen om sammanhanget blivit fel.

### "Varfor ar svaret osakert?"

Modellen far framst wikiutdrag. Om wikin saknar detaljer ska den be om vy, knapp och exakt feltext i stallet for att gissa.

## Kallor

- `../app/frontend/js/common.js`
- `../app/frontend/css/styles.css`
- `../app/backend/routers/assistant.py`
- `../app/backend/config.py`
- `../API_ROUTES.md`

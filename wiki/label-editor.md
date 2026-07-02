---
title: Etiketter
status: experiment
updated: 2026-07-02
tags: [etiketter, label, utskrift, qr, code128]
---

# Etiketter

Kort svar: Etiketter är en lokal label editor där användaren väljer etikettens
storlek från vanliga profiler som `104 x 199`, A3, A4 och A5, eller anger egna
bredd-/höjdmått i millimeter. Egna mått kan sparas som lokala profiler för
framtida användning. Därefter lägger användaren in text, QR, Code128, former och
symboler, drar objekten till rätt plats och skriver ut etiketten via
webbläsarens skrivardialog.

## Användarflöde

1. Öppna `Etiketter` i sidebaren.
2. Välj en profil, till exempel `Etikett 104 x 199`, `A4 stående` eller
   `A5 liggande`, eller ange bredd och höjd i millimeter.
3. Spara ofta använda egna mått med `Profilnamn` + `Spara`.
4. Lägg till objekt med verktygsknapparna. `Symbol` öppnar en dialog med
   symboler och emojis innan objektet läggs in.
5. Klicka eller dra objekt på etiketten.
6. Ändra valt objekts position, storlek, värde och färger i sidopanelen.
7. Använd `Delete`/`Backspace` för att ta bort valt objekt och
   `Ctrl+C`/`Ctrl+X`/`Ctrl+V` samt `Ctrl+Z`/`Ctrl+Y` för lokal
   kopiera/klipp ut/klistra in och ångra/gör om.
8. Klicka `Skriv ut` för att skriva ut bara etiketten i valt mått.

Kortkommandon gäller när fokus ligger i etikettytan eller på sidan. När fokus
ligger i ett textfält, textarea, färgväljare eller select används webbläsarens
vanliga textredigering i stället, så `Backspace` och `Ctrl+C/V/X/Z` inte
raderar objekt av misstag.

Vyn är ett experiment och har ingen standardåtkomst för basroller. Super User
kan alltid öppna den, och andra roller kan få `labelEditor=view/edit` via
Vybehörigheter.

## Knappar och kontroller

| Kontroll | Var | Vem får | Vad händer | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- | --- |
| Profil | Måttpanel | `labelEditor` | Väljer standardprofil eller sparad egen profil och sätter bredd/höjd | `label_editor/editor.js`, `localStorage` | Om en egen profil saknas används en annan browser/profil eller lokal lagring har rensats. |
| Bredd/Höjd mm | Måttpanel | `labelEditor` | Ändrar etikettytans mått och håller objekt innanför ytan | `label_editor/editor.js` | Mycket små/stora värden klampas till tillåtna gränser. |
| Profilnamn + Spara | Måttpanel | `labelEditor` | Sparar aktuellt bredd-/höjdmått som lokal profil | `flow-label-editor-profiles-v1` i `localStorage` | Sparas bara i aktuell browser/desktopprofil, inte på servern. |
| Ta bort | Måttpanel | `labelEditor` | Tar bort vald sparad profil | `flow-label-editor-profiles-v1` i `localStorage` | Standardprofiler kan inte tas bort. |
| Text | Verktyg | `labelEditor` | Lägger till ett textobjekt som kan dras och ändras | `label_editor/editor.js` | Lång text kan behöva större ruta eller mindre textstorlek. |
| QR | Verktyg | `labelEditor` | Skapar en QR-kod som SVG lokalt i browsern | `label_editor/barcodes.js` | För långt värde ger fel i objektet; korta texten. |
| Code128 | Verktyg | `labelEditor` | Skapar en Code128-B-streckkod som SVG lokalt i browsern | `label_editor/barcodes.js` | Code128 stöder ASCII 32-126; å/ä/ö eller andra tecken ger fel. |
| Rektangel/Ellips/Linje | Verktyg | `labelEditor` | Lägger till former med valbar linje/fyllnad | `label_editor/editor.js` | Fyllda former kan täcka andra objekt. |
| Symbol | Verktyg | `labelEditor` | Öppnar en dialog med SVG-symboler och emojis; valt objekt läggs in på etiketten | `label_editor/editor.js` | Dialogen stängs med `Stäng` eller Escape. Byt symbol i egenskapspanelen efteråt. |
| Duplicera/Ta bort | Vald objektpanel | `labelEditor` | Kopierar eller tar bort valt objekt | `label_editor/editor.js` | Knapparna är låsta tills ett objekt är valt. |
| Delete/Backspace | Etikettyta | `labelEditor` | Tar bort valt objekt och kan ångras med `Ctrl+Z` | `label_editor/editor.js` | Kortkommandot ignoreras i input/textarea/select så textredigering fungerar normalt. |
| Ctrl+C/Ctrl+X/Ctrl+V | Etikettyta | `labelEditor` | Kopierar, klipper ut och klistrar in valt objekt med lokal intern clipboard | `label_editor/editor.js` | Objektdata skickas inte till system-clipboard; textfält behåller webbläsarens vanliga clipboard. |
| Ctrl+Z/Ctrl+Y/Ctrl+Shift+Z | Etikettyta | `labelEditor` | Ångrar och gör om lokala ändringar som tillägg, borttagning, flytt, storlek och klipp/klistra | `label_editor/editor.js` | Historiken är lokal för aktuell sidladdning. |
| Rensa | Sidopanel | `labelEditor` | Rensar etiketten efter bekräftelse och kan ångras lokalt | `label_editor/editor.js` | Rensning sparas inte på servern. |
| Skriv ut | Sidopanel | `labelEditor` | Döljer appens övriga UI och öppnar skrivardialogen med `@page` i valt mm-mått | `label_editor/editor.js`, `styles.css` | Skrivaren kan kräva rätt labelstorlek/marginalfri utskrift i drivrutinen. |

## Tekniskt flöde

- `label-editor.html` är en skyddad statisk frontend-vy.
- `initPage("labelEditor")` sköter login, sidebar och vyåtkomst.
- Backendens `feature_registry_payload()` inkluderar `labelEditor` så
  Användare > Vybehörigheter kan styra åtkomst.
- Standardprofilerna ligger i `BUILTIN_LABEL_PROFILES`. Egna profiler sparas
  lokalt i `localStorage` under `flow-label-editor-profiles-v1`; de synkas inte
  mellan användare, browserprofiler eller datorer.
- QR och Code128 ritas som lokala SVG-fragment. Symbolväljaren bygger på en
  lokal `SYMBOL_PICKER_GROUPS`-lista med SVG-symboler och emojis. Ingen
  etikettdata skickas till backend när användaren redigerar, drar, väljer
  symbol eller skriver ut.
- Synlig sessionfeedback går till dokumentloggen vid tillägg, borttagning,
  kopiera/klipp ut/klistra in, ångra/gör om, symbolväljare, rensning och utskrift.
  Interaction tracking skickar bara handling, objekttyp, antal objekt och
  etikettmått, inte streckkodsvärden eller textinnehåll.
- Eftersom flödet är lokalt/read-only och inte sparar eller ändrar data finns
  ingen sparad `audit_log`-rad för själva etikettlayouten. Sidöppning loggas som
  vanlig `view_open` client event.

## Felsökningssvar för framtida chat

- "Varför syns inte Etiketter?" Rollen saknar `labelEditor` i
  Vybehörigheter. Be admin eller Super User kontrollera vyn.
- "Varför blir Code128 röd/fel?" Värdet innehåller tecken utanför ASCII
  32-126, till exempel å/ä/ö. Använd ett ASCII-id eller QR för fri text.
- "Varför skrivs inte exakt rätt storlek?" Kontrollera att både bredd/höjd i
  vyn och skrivardrivrutinens labelstorlek/marginaler matchar.
- "Varför finns inte min sparade profil?" Sparade profiler ligger i lokal
  browserlagring. De följer inte med till en annan dator, annan browserprofil
  eller efter rensad webbplatsdata.
- "Varför finns inte etiketten kvar efter omladdning?" Vyn sparar inte
  etikettdata på servern i experimentläget.
- "Hur lägger jag in emojis?" Klicka `Symbol`, välj en symbol eller emoji i
  dialogen och justera sedan storlek/färg i egenskapspanelen.
- "Varför tog Backspace inte bort objektet?" Fokus ligger troligen i ett
  textfält eller annan redigerbar kontroll. Klicka objektet eller etikettytan
  först och tryck sedan `Backspace` eller `Delete`.
- "Varför klistras inte objektet in i ett annat program?" Etikettobjektens
  `Ctrl+C/X/V` är en intern editor-clipboard för att inte läcka etikettvärden
  till operativsystemets urklipp.

## Källor

- `../app/frontend/label-editor.html`
- `../app/frontend/js/label_editor/editor.js`
- `../app/frontend/js/label_editor/barcodes.js`
- `../app/frontend/css/styles.css`
- `../app/backend/user_access.py`
- `../tests/tools/test_label_editor_frontend.py`
- `../tests/tools/test_label_editor_browser.py`

---
title: Felkoder och felmeddelanden
status: aktiv
updated: 2026-06-10
tags: [felkoder, http, support, api, chat]
---

# Felkoder och felmeddelanden

Kort svar: frontend visar oftast serverns JSON-`detail` direkt, men sanerar HTML-felsidor fran server/proxy till kort status som `HTTP 502 (Bad Gateway)`. I chatten ska statuskod + text oversattas till enkel atgard. Super User kan se vanliga anvandartraffade fel i Historik > Felkoder.

## HTTP/statuskoder i appen

| Kod | Namn | Typisk betydelse i flow | Vad anvandaren ska gora |
| --- | --- | --- | --- |
| 0 | Klientens anslutningsfel | Fetch misslyckades innan servern svarade | Kontrollera adress, natverk, backend eller att appen inte oppnats direkt som fil. |
| 200 | OK | Hamta/uppdatera lyckades | Ingen atgard. |
| 201 | Created | Ny person/aktivitet/anvandare skapades | Kontrollera att raden syns. |
| 204 | No Content | Logout eller delete/inaktivering lyckades utan body | Ingen atgard; UI laddar om/uppdaterar. |
| 400 | Bad Request | Fel input, ogiltig fil, ogiltigt segment, for manga/fel parametrar | Ratta falt, fil eller val. |
| 401 | Unauthorized | Inte inloggad, fel login eller inaktiv anvandare | Logga in igen; admin kontrollerar konto om det fortsatter. |
| 403 | Forbidden | Rollen saknar behorighet eller forsta losenord kravs | Kontrollera roll/vyatkomst eller skapa losenord. |
| 404 | Not Found | Objekt, resultat, aktivitet, person, omrade eller fil hittades inte | Ladda om, kontrollera att objektet finns, eller kor flodet igen. |
| 409 | Conflict | Samtidig cellandring, dubblett, sista-admin-skydd, summeringsloop | Ladda om/byt varde/skapa annan admin/rensa dubblett. |
| 429 | Too Many Requests | Apphjalpens sessionskvot ar slut | Klicka `Rensa dialog` for att borja om eller vanta pa ny session. |
| 413 | Request Entity Too Large | Excelimport ar for stor | Minska filen, dela upp importen. |
| 422 | Validation Error | Pydantic/API-validering: fel typ, saknat falt, losenordslangd | Ratta formulardata eller API-payload. |
| 500 | Server Error | Ohanterat serverfel, berakning eller datalasning misslyckades | Rapportera med exakt text, tidpunkt och vy. |
| 502 | Bad Gateway | Proxy/server kunde inte na backend, ofta vid Render-omstart/OOM, eller extern modell/API gav fel svar, t.ex. MiniMax | Om flera vanliga API:er visar 502: kontrollera Render-events, minne, deploy och serverstatus. Om det bara galler modellflode: kontrollera API-nyckel, modellnamn, kvot och serverlogg. |
| 503 | Service Unavailable | Lagerverktyg/offentlig token/beroende saknas eller appchatten saknar API-nyckel | Kontrollera serverkonfiguration eller forsok senare. |
| 504 | Gateway Timeout | Extern modell/API svarade inte i tid | Forsok igen och kontrollera natverk/MiniMax om det upprepas. |

## Klientgenererade fel

| Text | Var | Betyder | Atgard |
| --- | --- | --- | --- |
| "Appen maste oppnas via servern..." | `api.js` | Sidan oppnades som `file://` | Oppna via `https://stigamo.nu` eller lokal server. |
| "Kunde inte ansluta till servern..." | `api.js` | Fetch kunde inte na backend | Kontrollera adress, backend och natverk. |
| "Unauthorized" | `api.js` | 401 pa skyddad API-vag | Logga in igen. |
| "password_setup_required" | `api.js` | API kraver forsta losenord | Skapa losenord. |
| "Servern svarade med HTTP NNN (...)" | `api.js` | Server/proxy svarade med text eller HTML utan JSON-detail | Be anvandaren ange statuskod, vy och tidpunkt. Raw HTML visas inte langre i dokumentloggen eller Felkoder. |
| "HTTP NNN" | `api.js`/lager | Server svarade utan tydligt detail | Be anvandaren ange Network-status och vy. |

## Meta-uppladdning

| Status | Text | Orsak | Atgard |
| --- | --- | --- | --- |
| 400 | "Bara bilder och videor..." eller "Inga filer skickades" | Publika uppladdningen fick fel filtyp eller saknade filer | Valj bilder/videor igen. |
| 413 | "Uppladdningen ar storre..." | En fil eller hela batchen ar for stor | Dela upp uppladdningen eller minska filerna. |
| 500 | "Uppladdningen misslyckades pa servern..." | Backend tog emot requesten men kunde inte spara/analysera uppladdningen. Tidigare kunde en stor multipart-batch ge for tung request; publika klienten skickar nu filerna en och en. | Sok `meta_media_upload/upload_failed` i Historik > Felkoder. Om raden saknas kan felet ha stoppats innan backend tog emot requesten. |

## Auth och behorighet

| Status | Detail/text | Orsak | Atgard |
| --- | --- | --- | --- |
| 401 | "Felaktigt anvandarnamn eller losenord" | Fel login eller borttaget konto | Kontrollera username/losenord eller skapa kontot igen. |
| 401 | "Lamna losenordet tomt vid forsta inloggningen" | Konto saknar losenord men anvandaren skrev ett | Logga in med tomt losenord och skapa nytt. |
| 401 | "Not authenticated" | Ingen session | Logga in. |
| 401 | "User inactive" | Gammal datarad har inaktivt konto | Lokal bootstrap/migration ska gora konton aktiva; kontrollera databasversion. |
| 403 | "password_setup_required" | Konto maste skapa losenord | Ga till `set-password.html`. |
| 403 | "Admin required" | Endpoint kraver admin | Ge roll eller lat admin gora atgarden. |
| 403 | "Super User required" | Endpoint kraver super user | Ge super-user-roll/vyatkomst. |
| 403 | "Sidan kraver ..." | Rollens vyatkomst racker inte | Be admin/Super User andra Vybehorigheter; vanlig anvandare kan normalt inte gora det sjalv. |
| 403 | "Visningsrollen kan inte andra bemanningen" | Viewer forsoker spara | Anvand edit-roll. |
| 403 | "Bearbeta kraver behorighet" | Lagerprocessflode utan `allocationProcess=edit` | Be admin/Super User kontrollera Vybehorigheter eller anvand Dela om det racker. |

## Bemanning och schema

| Status | Text | Orsak | Atgard |
| --- | --- | --- | --- |
| 400 | "Timme maste vara 6-23" | Hour utanfor tillatna tider | Anvand synliga timmar 06-23. |
| 400 | "Ogiltigt segment..." | Segment ligger inte inom 0-60 eller startar inte fore slut | Dela/merge via UI, skicka inte eget segment. |
| 400 | "Duplicerade segment i samma timme." | Flera segment har samma start/slut | Ladda om, undvik dubbel bulk. |
| 400 | "Delningen maste ha 2-4 sammanhangande delar..." | Split-payload har for fa/manga delar, glapp, overlapp eller minut utanfor 0-60 | Dela via UI och anvand stigande minutstarter mellan 1 och 59. |
| 400 | "Kan bara dela en tom timme eller en hel timcell." | Split begard pa ogiltig cell | Ladda om eller merge forst. |
| 400 | "Cellen ar redan delad eller har ogiltigt segmentformat." | Merge/split stammer inte med serverns segment | Ladda om dagen. |
| 400 | "For manga celler (max 200)" | Bulk/drag for stort | Dela upp draget. |
| 400 | "For manga timmar (max 200)" | Undo/restore for stor payload | Gora mindre operationer. |
| 400 | "Undo kan bara aterstalla..." | Undo-snapshot har ogiltigt segmentformat | Ladda om; rapportera om det upprepas. |
| 403 | Cell-last detail | Annan anvandare har fyllt cellen och lasning ar aktiv | Admin eller cellens agare far andra. |
| 404 | "Person hittades inte" | Personen ar borttagen/inaktuell i state | Ladda om sidan. |
| 404 | "Aktivitet hittades inte" | Aktiviteten saknas/inaktuell i state | Ladda om aktiviteter/sidan. |
| 409 | Conflict med aktuell cell | Version eller segmentsignatur matchar inte | Servern vann; ladda om och gor om. |

## RFID i Bemanning

| Status | Text | Orsak | Atgard |
| --- | --- | --- | --- |
| 400 | "module_name kravs" | ESP32 skickade tomt modulnamn | Satt `MODULE_NAME` i firmware, till exempel `MG Plock`. |
| 400 | "tag_hex eller tag_dec kravs" | ESP32 skickade ingen brickkod | Kontrollera RDM6300-koppling och seriell lasning. |
| 401 | "RFID-token saknas eller stammer inte" | Backend har `RFID_DEVICE_TOKEN`, men modulen skickar fel eller saknar header | Satt samma token lokalt i firmware som i servermiljon. |
| 404 | "RFID-handelse hittades inte" | UI forsoker applicera/ignorera en handelse som inte finns eller inte ar synlig i anvandarens verksamhet | Ladda om Bemanning och kontrollera verksamhet/omrade. |
| 409 | "RFID-handelsen ar redan applicerad" | Anvandaren forsoker applicera/ignorera en redan applicerad stampel | Ladda om Bemanning; schemaandringen ar redan gjord. |
| 409 | "Dubblettscanningar appliceras inte" | Samma person stampade samma aktivitet tva ganger i rad | Ingen atgard behovs om forsta stampeln ar ratt; annars kontrollera senaste stampel for personen. |
| 409 | "RFID-scanningen ligger utanfor Bemanningens timmar." | Stampeln ar fore 06 eller efter 23 | Justera arbetstid eller hantera manuellt. |

## Oversikt

| Status | Text | Orsak | Atgard |
| --- | --- | --- | --- |
| 400 | Dag/person saknar schematimmar | Heldagsandring pa person utan mall/timmis | Satt veckomall eller planera i Bemanning. |
| 400 | "For manga dagar (max 100)" | Drag over for manga dagceller | Dela upp draget. |
| 404 | "Person ... hittades inte" | Person saknas | Ladda om. |
| 404 | "Aktivitet ... hittades inte" | Aktivitet saknas | Ladda om. |
| 500 | "Serverfel: ..." | Ohanterat fel i oversiktsberakning | Rapportera exakt text och period. |

## Import och register

| Omrade | Status | Text | Orsak | Atgard |
| --- | --- | --- | --- | --- |
| Personimport | 400 | "Excel-filen saknar rubrikrad" | Tom/felaktig Excel | Anvand importmallen. |
| Personimport | 400 | "Excel-filen maste ha kolumnen namn" | Obligatorisk rubrik saknas | Lagg till `namn`. |
| Personimport | 400 | "Excel-filen kunde inte lasas" | Fel format/skadad fil | Spara om som `.xlsx`. |
| Personimport | 413 | "Excel-filen ar for stor" | Over maxstorlek | Dela upp filen. |
| Personimport | Resultatmodal | "Dubblett i tabellen" | Samma namn finns flera ganger i direktimporten | Ta bort eller andra en av raderna. |
| Personer | 409 | "Person med samma namn finns redan" | Dubblett | Andra namn eller uppdatera befintlig. |
| Aktivitetsimport | 400 | "Excel-filen maste ha kolumnen etikett" | Obligatorisk rubrik saknas | Anvand mall. |
| Aktivitetsimport | Resultatmodal | "Dubblett i tabellen" | Samma etikett finns flera ganger i direktimporten | Ta bort eller andra en av raderna. |
| Aktiviteter | 403 | "Endast Super User kan ange/andra aktivitetskod" | Icke-super-user forsoker kod | Lat Super User andra kod. |
| Aktiviteter | 400 | "Aktivitetskod saknar giltiga tecken" | Kod blir tom/ogiltig efter normalisering | Anvand bokstaver/siffror/giltiga tecken. |
| Aktiviteter | 409 | "Aktivitet med samma kod finns redan" | Kod dubblett | Valj annan kod. |
| Aktiviteter | 404 | "Summeringsaktivitet hittades inte" | Vald summering saknas | Ladda om och valj aktiv aktivitet. |
| Aktiviteter | 409 | "Summeringskoppling skapar en loop" | A summeras som B och B tillbaka till A | Bryt kedjan. |
| Omraden | 409 | "Omrade med samma kod finns redan" | Dubblettkod | Valj annan kod. |
| Anvandare | 400 | "Excel-filen maste ha kolumnerna anvandarnamn, namn och roll" | Importmall foljs inte | Anvand mall. |
| Anvandare | Resultatmodal | "Dubblett i tabellen" | Samma anvandarnamn finns flera ganger i direktimporten | Ta bort eller andra en av raderna. |
| Anvandare | 403 | "Endast Super User kan andra Super User-rollen" | Icke-super-user andrar super_user | Lat Super User gora andringen. |
| Anvandare | 409 | "Anvandarnamnet anvands redan" | Dubblett username | Valj annat anvandarnamn. |
| Anvandare | 409 | "Det maste finnas minst en aktiv administrator kvar" | Sista admin skyddas | Skapa/aktivera annan admin forst. |
| Veckomall | 400 | "Dag X: start_hour och end_hour kravs" | Arbetsdag saknar tider | Fyll fran/till. |
| Veckomall | 400 | "Dag X: ogiltigt tidsintervall A-B" | Utanfor 06-24 eller start >= end | Ratta tiden. |
| Veckomall | 400 | "Dag X: timmar maste vara null nar is_off=true" | Ledig dag skickar tider | Ladda om modal eller rensa tider. |
| Veckomall | 400 | "Dubbel weekday X" | Samma dag finns tva ganger | Ladda om, rapportera om UI skapade detta. |

## Produktivitet

| Status | Text | Orsak | Atgard |
| --- | --- | --- | --- |
| 403 | "Sidan kraver behorighet" | Rollen saknar `productivity` | Be admin/Super User kontrollera Vybehorigheter for Produktivitet. |
| 400 | "Inga filer skickades" | Upload utan filer | Valj fil igen. |
| 404 | "Produktivitetsmappen finns inte..." | Serverns data-dir saknas | Kontrollera serverkonfiguration. |
| 404 | "Saknar referensfil med prefix..." | KPI eller referensfil saknas | Ladda upp KPI eller kontrollera data-dir. |
| 404 | "Saknar produktivitetsunderlag: ..." | Kravda loggar saknas | Lagg in saknade loggar. |
| 200 med `source_status.kpi.status=coredata_fallback` | `fallback_reason` kan visa t.ex. "Extern datakalla svarade med HTTP 403" | API-klienten nekas `v_ask_kpi_target`, sa snapshoten anvander lokal KPI-coredata | Ge API-klienten behorighet till KPI-vyn eller uppdatera lokal KPI-coredata. |
| 502 | "Extern datakalla kunde inte synkas." | API-snapshot for Produktivitet kunde inte uppdateras | Kontrollera extern datakalla och `DATA_SOURCE_*`; senaste lyckade snapshot ska ligga kvar om den finns. |
| 503 | "Produktivitetsrapporten kraver central serverdata..." | Windows desktop ar offline fran central server | Oppna central server/webben eller kontrollera natverk; lokal desktop bygger inte langre personrapporten. |
| 404 | "Produktivitetsunderlagen saknar datum" | Datum kunde inte tolkas | Kontrollera CSV/header. |
| 404 | "Saknar produktivitetsdata for YYYY-MM-DD" | Vald dag finns inte | Valj annat datum. |
| 500 | "Kunde inte lasa KPI-mal..." | KPI-filen finns men kan inte lasas | Kontrollera filformat. |
| 500 | "Kunde inte lasa produktivitetsunderlag..." | Loggar finns men kan inte lasas | Kontrollera filformat/encoding. |
| 500 | "Kunde inte berakna produktivitet..." | Berakningsfel | Rapportera med filer/datum. |

## Hamta data

| Status | Text | Orsak | Atgard |
| --- | --- | --- | --- |
| 400 | "MiniMax-planen..." eller "Kolumnen ... finns inte" | Modellen valde okand vy/kolumn/operator eller svarade med fel JSON | Andra prompten eller kontrollera katalogen. Backend anropar inte extern datakälla nar planen ar ogiltig. |
| 403 | "Sidan kraver behorighet" | Rollen saknar `dataFetch` | Be admin/Super User kontrollera Vybehorigheter. |
| 404 | "Resultatet hittades inte..." | Export-sessionen saknas | Kor datahamtningen igen. |
| 502 | "Extern datakälla kunde inte nås." | Extern datakälla svarade inte, URL/sökvägsmall var fel eller TLS-certifikatet kunde inte verifieras | Kontrollera serverns `DATA_SOURCE_*`-miljovarden, API-status och eventuell `DATA_SOURCE_CA_BUNDLE`/`DATA_SOURCE_VERIFY_SSL`. |
| 502 | "Extern datakälla svarade med HTTP ..." | Extern datakälla nekade eller failade anropet | Använd fel-id i Hämta data-panelen och sök samma id i Render-loggen. |
| 500 | "Datahämtningen stoppades..." | Oväntat backendfel i datahämtningen | Använd fel-id i Hämta data-panelen och sök samma id i Render-loggen. |
| 503 | "Extern datakatalog saknas..." | Katalogfil/env saknas | Kontrollera att `data/external_data_catalog.json` ar deployad eller satt katalog som env-override. |
| 503 | "Saknar DATA_SOURCE_..." | Ett eller flera externa API-env saknas i servermiljon | Satt alla `DATA_SOURCE_*`-varden som health-raden listar i Render/env. Provider-specifik endpointmall, headernamn, URL och nycklar ska inte ligga i git. |
| 503 | "Datahamtning saknar MINIMAX_API_KEY..." | MiniMax-nyckel saknas | Satt `MINIMAX_API_KEY` i servermiljon. |

## Lagerverktyg/allokering

| Status | Text | Orsak | Atgard |
| --- | --- | --- | --- |
| 400 | `message` fran flode | Flodet saknar input eller data ar fel | Las texten och kontrollera kravda filer/falt. |
| 403 | "Bearbeta kraver behorighet" | Roll saknar processatkomst | Ge rollen `allocationProcess=edit` eller anvand Dela. |
| 404 | "Okant flode: ..." | Flode saknas i backend | Ladda om, kontrollera version. |
| 404 | "Resultatet hittades inte..." | Resultatsession saknas | Kor flodet igen. |
| 404 | "Kolumnen hittades inte." | Tabellen saknar begard kolumn | Ladda om/kor om flode. |
| 500 | "Kunde inte oppna Excel-filen automatiskt..." | Excel-filen kunde skapas men OS/Excel-starten misslyckades, eller Excel-exporten stoppades av fil-/bladnamn/beroende | Las feltoast/serverlogg, kor om flodet och testa CSV om Excel inte kan startas lokalt. |
| 503 | Lagerverktyg unavailable payload | Motor/beroenden kunde inte laddas | Kontrollera serverlogg och `warehouse_tools`. |
| Runtime | "Saknar Excel-skrivare..." | `openpyxl`/`xlsxwriter` saknas | Ladda ner CSV eller installera beroende. |
| Flode | "Ange minst en prognosfil eller en kampanjfil." | Prognosrapport saknar input | Lagg in prognos/kampanj. |
| Flode | "Saldo/automation kravs..." | Prognosrapport saknar saldo | Lagg in Saldo ink. Automation. |
| Flode | "Extern datakalla kunde inte nas... Ladda upp ..." | API-first kunde inte hamta en Bearbeta-kalla och ingen uppladdad/localRef fallback finns | Ladda upp den namnda filen och kor igen, eller kontrollera extern datakalla. |
| Flode | "Inga varden angivna..." | Dela saknar lista | Klistra in eller ladda textfil. |

## Apphjalp och LLM-chatt

| Status | Text | Orsak | Atgard |
| --- | --- | --- | --- |
| 400 | "Den senaste dialograden maste vara en anvandarfraga." | Frontend skickade dialog dar sista raden inte var `user` | Ladda om sidan; rapportera om det upprepas. |
| 429 | "Max 10 fragor per session..." | Sessionskvoten ar slut | Klicka `Rensa dialog` i apphjalpen. |
| 502 | "MiniMax svarade HTTP ..." | MiniMax nekade, kvot saknas, modellnamn fel eller API-fel | Admin kontrollerar MiniMax-konfiguration och serverlogg. |
| 502 | "MiniMax svar saknade textinnehall." | MiniMax svarade i ovantat format | Rapportera feltexten och payloadtidpunkt. |
| 503 | "Appchatten saknar MINIMAX_API_KEY..." | Servern saknar API-nyckel | Satt `MINIMAX_API_KEY` i servermiljon och starta om. |
| 504 | "MiniMax kunde inte nas inom timeout." | Timeout eller natverksfel mot MiniMax | Forsok igen senare; kontrollera natverk/API-status. |

## Nar chatten ska be om mer information

Be anvandaren skicka:

- exakt vy och knapp
- exakt toast/feltext
- om felet sker i webb eller Windows
- roll/anvandarnamn eller rolltyp
- datum/vecka/omrade/person/aktivitet som anvandes
- filnamn och forsta rubrikraden vid filfel
- om fler anvandare arbetade samtidigt vid 409-konflikt

## Kallor

- `../app/frontend/js/api.js`
- `../app/backend/deps.py`
- `../app/backend/routers/*.py`
- `../app/backend/routers/rfid.py`
- `../app/backend/routers/data_fetch.py`
- `../app/backend/productivity_service.py`
- `../app/backend/productivity_sync.py`
- `../app/backend/allocation_bridge.py`
- `../warehouse_tools/flows.py`

---
title: Anvandare och installningar
status: aktiv
updated: 2026-06-17
tags: [anvandare, settings, roller, ui]
---

# Anvandare och installningar

Kort svar: Anvandare-sidan hanterar konton, verksamhet, roller, omrade, forsta losenord, verksamhetsspecifik cell-lasning och rollernas globala vyatkomst. Installningar-sidan samlar lager-, bemannings- och produktivitetsinstallningar: Ytkarta, Bearbeta-matris, Bemanningens historiska snitt och Produktivitetens intakt/utgift. Anvandare ar alltid aktiva; konton som inte ska finnas kvar tas bort. Super User har dessutom vyn Verksamheter dar verksamheter och deras omraden administreras.

Hogerklick pa `Installningar` i sidebaren visar samma installningsflikar som
sidan: Ytkarta, Bearbeta, Bemanning och Intakt/utgift, filtrerat efter rollens
vybehorighet.

Omradesfokus i sidebar filtrerar anvandarlistan inom anvandarens verksamhet. `∞` visar alla omraden i den verksamheten nar verksamheten har aktivt `ANNAT`; for Super User betyder `∞` globalt allt. Nar en ny anvandare skapas forvalt valt omradesfokus som anvandarens omrade, men omradet kan fortfarande andras i modalen eller lamnas tomt.

## Knappar och kontroller

| Kontroll | Vad anvandaren gor | Vad systemet gor | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- |
| Ny anvandare | Oppnar modal | Skapar konto med en roll | `POST /api/users` | Anvandarnamn och en roll kravs. |
| Flera nya anvandare | Oppnar tabellmodal | Skapar flera konton direkt i appen med en roll per rad | `POST /api/users/import-rows` | Dubbletter, okanda roller och okanda omraden visas i resultatmodal. |
| Ladda ner importmall | Hamter Excelmall | Laddar ner mall | `GET /api/users/import-template` | Kräver `userImport` edit/super user enligt backend. |
| Importera Excel | Oppnar filval | Importerar anvandare | `POST /api/users/import` | Importerade utan losenord far `must_change_password=true`. |
| Vybehorigheter | Oppnar rollmatris | Sparar global vyatkomst for roller | `GET/PUT /api/settings/role-access` | Fel matris kan dolja vyer for rollen i alla verksamheter. |
| Import-hjalp | Oppnar hjalpmodal | Visar importstod | `setupImportHelpButton` | Ingen serverkoppling. |
| Las bemanningsceller... | Checkbox | Sparar setting per verksamhet | `PUT /api/settings` | Nar aktiv kan ledare stoppas fran celler andra fyllt i aktuell verksamhet. |
| Bemanningsinställningar | Flik under `installningar.html` | Sparar `staffing_history_hours` och vilka aktiviteter som far visa historiskt snitt vid cell-hover per verksamhet | `GET/PUT /api/settings/staffing`, `GET /api/activities` med `business_id`/`area_focus` | Kräver `staffingSettings`; utan edit kan rollen bara se värdena. |
| Intakt/utgift | Flik under `installningar.html` | Sparar kostnad per timme, intaktsunderlag per bolag fran Verksamheter-vyns `company_codes` och valfri processkoppling per intaktsrad; `GG` ar forifyllt med hela Grann-garden-underlaget och `MG` bara med VAS + IT | `GET/PUT /api/settings/productivity-finance` med `business_id`/`area_focus` | Kraver `productivityFinanceSettings`; utan edit kan rollen bara se vardena. Endast Super User har standardatkomst just nu. |
| Bearbeta-matris | Flik under `installningar.html` | Styr vilka Bearbeta-funktioner som visas per toggle for vald verksamhet | `GET/PUT /api/allokering/process-matrix` med `business_id`/`area_focus` | Kraver `allocationProcessMatrix`; `view` kan lasa och `edit` kan spara. |
| Tabellrubriker | Klickar pa t.ex. Anvandarnamn, Verksamhet, Roll, Omrade eller Skapad | Sorterar synliga anvandarrader stigande/fallande i klienten | `common.js` klienttabellsortering | Paverkar inte omradesfokus, roller eller serverdata. |
| Redigera | Oppnar modal | Uppdaterar konto | `PUT /api/users/{id}` | Sista admin kan inte nedgraderas. |
| Ta bort | Bekraftar borttagning | Tar bort konto permanent och nollar gamla `updated_by`/audit-referenser | `DELETE /api/users/{id}` | Eget konto, sista admin i en verksamhet och demo-användaren skyddas. |
| Verksamheter | Sidebar-vy for Super User | Skapar verksamheter, deras bolagskoder, Tenant och omraden, redigerar celler inline och kan lagga till `∞`/`ANNAT` per verksamhet | `GET/POST/PUT /api/businesses`, `GET/POST/PUT/DELETE /api/areas` | Vanliga anvandare ser inte vyn. Omraden med kopplad data inaktiveras i stallet for att hardraderas. |

Andringar i anvandare, forsta losenord och verksamhetens installningar skrivs till Historik. Loggen visar till exempel `user/set_password`, `app_setting/update_lock`, `app_setting/update_sidebar_layout` och `app_setting/update_role_access`, men aldrig sjalva losenordet.

## Ny/redigera anvandare-modal

Falt:

- Anvandarnamn.
- Visningsnamn.
- Roll som ett val nar kontot skapas.
- Roller som checkboxar nar ett befintligt konto redigeras.
- Omrade.
- Verksamhet visas bara for Super User nar den inte kan harledas.
- Losenord.

Validering:

- Anvandarnamn kravs.
- En roll kravs vid skapande. Vid redigering kravs minst en roll.
- Losenord, om ifyllt, maste vara minst 8 tecken.
- Super-user-rollandring skyddas av backendregler.
- Vanliga admins kan bara skapa/andra anvandare i sin egen verksamhet. Super User maste valja verksamhet eller ett omrade som harleder verksamheten.
- `is_active=false` accepteras inte vid uppdatering; ta bort kontot i stallet.

Knappar:

- `Avbryt`: stanger utan att spara.
- `Spara`: skickar `POST` eller `PUT`.

### Demo-anvandaren

Det fasta `demo`-kontot (se [demo-laget](demo-mode.md)) visas med en `DEMO`-pill i listan, har dold delete-knapp och har disablade `Anvandarnamn` + `Roller` i edit-modalen. Lösenord, visningsnamn och omrade kan fortfarande andras av super_user — backend nekar 409 om någon försoker dopa om, ta bort admin-rollen eller inaktivera kontot. Kontot skapas inte längre automatiskt vid production-deploy; det måste redan finnas eller skapas via kontrollerad bootstrap.

## Vybehorigheter-modal

Rollmatrisen visar vyer som rader och roller som kolumner. Matrisen ar global, sa samma roll far samma vyatkomst i Stigamo och R3. Super User-kolumnen visas som last `Redigera` eftersom rollen alltid har full atkomst. Demo-kolumnen styr extra vyatkomst for det fasta `demo`-kontot, som fortfarande ar skyddat som admin-konto. Varje vanlig knapp cyklar:

`Ingen` -> `Visa` -> `Redigera` -> `Ingen`

Raden `Personsortering` (`personSortOrder`) styr om Bemanningsansvarig/admin kan dra personnamn i Bemanning och Oversikt for att uppdatera sorteringsnumret i Personer. Super User har alltid edit via backendens Super User-regel, men sorteringen kraver fortfarande att anvandaren har ett omrade och att personen har samma hemomrade.

Raden `Bemanningsinställningar` (`staffingSettings`) styr fliken Bemanning pa `installningar.html`. `view` far lasa historikfonstret for historiskt snitt/automatisk bemanningskalkyl och vilka KPI-aktiviteter som far visa hover-snitt. `edit` far andra bada. Admin och demo har `edit` som standard, Super User har alltid full atkomst.

Raden `Intakt/utgift` (`productivityFinance`) styr om Produktivitet visar belopp pa hierarkikorten. `view` racker for att se intakt, utgift och resultat. Inga vanliga roller har standardatkomst; Super User har alltid full atkomst.

Raden `Intakt/utgift-installningar` (`productivityFinanceSettings`) styr fliken Intakt/utgift pa `installningar.html`. `view` far lasa kostnad per timme och intaktsunderlag per bolag. `Spara` ligger hogst upp i fliken sa man inte behover scrolla forbi hela intaktstabellen. Varje bolagsruta har rubriken som bolagskod, till exempel `GG`, och `GG` ar forifyllt med Grann-garden-rader for Inbound, BUTIK, E-handel, VAS, IT och Ovrigt. `GG` har ocksa forifyllda utrakningar for `Mottagna etiketter`, `Mottagna artikelrader`, BUTIK-raderna `Plockade orders`, `Plockade rader`, `Antal helpallar` och `Utlastade pallar`, samt E-handel-raderna `Plockade orders`, `Plockade rader` och `Antal helpallar`. `Utlastade pallar` raknar Dispatchpallslogg (`dispatch_pallet_log` och vid aldre perioder `dblog_dispatch_pallet_log`) dar `parent_pick_pall_num` ar tomt. `MG` far bara VAS-raderna, med samma VAS-varden som `GG`, och IT-raden som defaultar till 0 kr i repot och kan overlayas fran lokal/secret prisfil. VAS-raderna sparar Blue collar och White collar med Normal/OT/OB-rader. Varje rad har `ST / Antal`; radkommandon oppnas med hogerklick pa raden. `Utrakning` later admin skriva hur antalet ska raknas, testa mot en startad manad i innevarande ar via samma MiniMax/Hamta data-plan som `hamta-data.html`, och spara prompt, validerad plan och SQL/querytext pa raden. `Kontroll` oppnar en dialog dar admin valjer kontrollmanad, kor radens processkontroll och ser resultatet utan inline-panel i installningsvyn. I samma kontroll-dialog kan admin ocksa koppla raden till en KPI-process via en sokbar rullista och se radens prompt, intakts-SQL samt vald process-SQL. Kontrollresultatet visar dessutom en processkombination: om utrakningen raknar `count_distinct`, till exempel unika `order_num`, jamfors KPI-processernas samlade nycklar mot samma intaktsnycklar i stallet for bara enskilda loggrader. `Koppla process` oppnar fortsatt en separat dialog med alla KPI-processer och sparar kopplingen sa radens intakt visas i Produktivitetens processnoder. Den sparade planen kan innehalla whitelistad `calculation` som `count`, `count_distinct`, `sum`, `avg`, `min` eller `max`; till exempel raknas "ta bort dubletter per inkop och artikel" som `count_distinct` pa `book_num` + `item_num`. Testet skickar alltid med bolagsrutans kod och backend lagger pa `company`/Bolag-filter nar den valda ASK-vyn har en bolagskolumn. Dialogen stangs med `Avbryt` eller efter sparning, inte av backdrop-klick, sa textmarkering i rutan inte stanger den. Bolagsraderna hamtas fran Verksamheter-vyns `company_codes`, inte fran omraden. `edit` far spara. Inga vanliga roller har standardatkomst; Super User har alltid full atkomst.

Knappen `Kontrollera intakter/processer` ligger i samma flik och kraver
`productivityFinanceSettings=view`. Den oppnar en dialog dar anvandaren valjer
manad och bolag innan sparade intaktsplaner och KPI-processregler kors mot
samma kallrader. Resultatet visas i dialogen och visar vilka intaktsrader som
verkar matcha vilka KPI-processer, vilka
intaktsrader som har rader utan KPI-process, vilka KPI-processrader som saknar
intakt och var KPI eller intakt verkar dubbelrakna. Resultatet visar bara
sanerade kontrollvarden som bolag, lager, zon, typ och status. En intaktsrad kan
vara godkand nar flera KPI-processer tillsammans tacker den. Om en matchande
KPI-process ocksa tacker fler rader an intaktsraden visas det som granskningsnotis.
For `count_distinct`-utrakningar visar kontrollen ocksa hur manga unika
berakningsnycklar, till exempel `order_num`, som tacks av processkombinationen,
hur manga som saknas och hur manga extra nycklar processerna samlar.
Backend skriver
audit `productivity_finance_process_check/run` med period, bolag och summerade
raknetal.

Raden `Bearbeta-matris` (`allocationProcessMatrix`) styr fliken Bearbeta pa `installningar.html`. `view` far oppna matrisen lasande och `edit` far spara vilka Bearbeta-funktioner som ska synas per toggle i vald verksamhet. Admin och demo har `edit` som standard, Super User har alltid full atkomst. Bearbeta-vyn anvander fortsatt matrisen nar floden visas, men sjalva redigeringen ligger i Installningar.

Installningar foljer sidebarens omradesfokus for verksamhetsscope. Nar fokus ar ett omrade i T3 eller R3 hamtar och sparar Ytkarta, Bearbeta-matris, Bemanning-fliken och Intakt/utgift-fliken den verksamhetens egna `app_settings`-rader. Nar fokus ar `∞` pa Installningar faller klienten tillbaka till anvandarens egen verksamhet, normalt Stigamo for Super User. Vybehorigheter ar undantaget: rollmatrisen ar fortsatt global for alla verksamheter.

Knappar:

- `Standard`: aterstaller modalens draft till defaultmatris.
- `Avbryt`: stanger utan att spara.
- `Spara`: skickar `PUT /api/settings/role-access` och galler alla verksamheter.

## Importregler

- Direktimporten `Flera nya anvandare` har falten anvandarnamn, visningsnamn, roll, omrade och vid behov verksamhet. Roll ar ett dropdown-val och bara en roll kan valjas per ny anvandare.
- Varje kolumn i direkttabellen visar om faltet ar `Obligatoriskt` eller `Frivilligt` i rubriken.
- Excelimporten accepterar fortfarande samma svenska rollnamn och kan lasa flera roller separerade med komma.
- Importerade anvandare skapas aktiva utan losenord och far `must_change_password=true`.
- Dubbletter i fil, i direkttabellen eller mot befintliga anvandare stoppas och visas i resultatmodalen. Anvandarnamn ar globalt unika aven over verksamheter.

## Verksamheter-vy

Vyn finns bara for Super User och visar `code`, `name`, `company_codes`, `tenant`, `sort_order` och aktiv-status for verksamheter. Under varje verksamhet visas dess omraden. Rubrikerna sorterar listan visuellt, och celler for kod, namn, bolag, Tenant, sortering och aktiv-status kan andras direkt i tabellen.

Knappar:

- `Ny verksamhet`: oppnar modal och skapar via `POST /api/businesses`; kod skapas automatiskt från namnet, bolag sparas som `company_codes` och Tenant sparas som kort slug for extern datakalla.
- Klick i verksamhetscell: uppdaterar kod, namn, bolag, Tenant, sortering eller aktiv-status via `PUT /api/businesses/{business_id}`.
- `Nytt omrade`: skapar omrade pa vald verksamhet via `POST /api/areas` med `business_id`; kod skapas automatiskt från namnet.
- `Lagg till ∞`: skapar eller ateraktiverar omradet `ANNAT`/`Annat` for vald verksamhet. Nar det ar aktivt far vanliga anvandare i verksamheten `∞` som alla-omraden-lage.
- Klick i omradescell: uppdaterar kod, namn, sortering eller aktiv-status via `PUT /api/areas/{area_id}`.
- `Ta bort` under Omraden: anropar `DELETE /api/areas/{area_id}`. Tomma omraden tas bort; omradet inaktiveras om personer, aktiviteter eller anvandare redan ar kopplade till det.
- `Visa inaktiva`: laddar aven inaktiva verksamheter och omraden.

Supportregel: vanliga anvandare ska inte veta att andra verksamheter finns. Om en Stigamo- eller R3-anvandare saknar Verksamheter-vyn ar det korrekt beteende.

## Menyeditor per verksamhet

Denna finns i sidebar, inte i `anvandare.html`, men hor till settings:

- Pennikonen oppnar "Redigera meny".
- Varje rad har flytta upp/ned, rubrik ovanfor och "Under" for undervy.
- `Standard` aterstaller defaultlayout.
- `Spara` skickar `PUT /api/settings/sidebar` och galler aktuell verksamhet. Super User kan styra annan verksamhet genom API-filter.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor syns inte en sida for en roll?" | Kontrollera `Vybehorigheter`; vyn kan sta pa `Ingen` globalt for rollen. |
| "Varfor finns ingen aktiv-checkbox?" | Anvandare ar alltid aktiva. Konton som inte ska vara kvar tas bort med `Ta bort`. |
| "Varfor kan jag inte ta bort anvandaren?" | Backend hindrar borttagning av eget konto och sista admin i en verksamhet. |
| "Varfor maste anvandaren skapa losenord?" | Kontot skapades/importerades utan losenord och har `must_change_password=true`. |
| "Varfor kan arbetsledare inte andra vissa bemanningsceller?" | Settingen `Las bemanningsceller som andra anvandare har fyllt i` ar troligen aktiv. |
| "Varfor ser jag inte Verksamheter?" | Vyn finns bara for Super User. Vanliga anvandare ska bara se sin egen verksamhet. |

## Kallor

- `../app/frontend/anvandare.html`
- `../app/frontend/js/users.js`
- `../app/frontend/js/businesses.js`
- `../app/frontend/js/common.js`
- `../app/backend/routers/users.py`
- `../app/backend/routers/businesses.py`
- `../app/backend/routers/settings.py`
- `../app/backend/settings_service.py`

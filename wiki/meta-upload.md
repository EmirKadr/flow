---
title: Meta-uppladdning
status: aktiv
updated: 2026-06-04
tags: [meta, media, publik, uppladdning]
---

# Meta-uppladdning

Audio-only-andringen 2026-06-04: Meta-analysen anvander bara rosten. Backend extraherar en temporar ljudfil fran videon, skickar ljudet till Gemini och fyller endast `pallet_id` och `deviations`. Ordernummer, sandningsnummer, anvandarnamn och kund finns kvar som kolumner men lamnas tomma tills de kan hamtas via pall-id fran uppladdad data. Originalvideon med ljud sparas och strommas fortsatt som tidigare.

Kort svar: `meta-upload.html` ar en fristaende publik mobilvy utan sidebar och utan inloggning. Den ar till for att snabbt ladda upp flera bilder och videor fran Android, iPhone eller desktop. Filerna sparas i databastabellen `meta_media_uploads` med tidsstamplat `stored_filename`, SHA-256-baserat `content_hash`, eventuell `duration_seconds` och status `pending_analysis` for senare Gemini-analys. Exakta dubbletter sparas inte igen. Super User ser en skyddad sidebarvy `meta.html` med alla uppladdningar och en analystabell med tomma framtida lookup-kolumner, pall-id, avvikelser, video och eventuell etikettstillbild.

## Anvandarflode

1. Anvandaren oppnar `/meta` eller `/meta-upload.html`.
2. Sidan visar bara en enkel uppladdningsyta, ingen sidebar och ingen inloggningskontroll.
3. Anvandaren trycker `Valj bilder eller videor` och kan markera flera bilder/videor i mobilens fil- eller bildvaljare.
4. Valda filer listas med namn, storlek och videolangd nar browsern kan lasa metadata.
5. Uppladdningen startar automatiskt direkt efter filval eller drag/drop. Anvandaren kan valja hela kon pa en gang utan Flow-satt klientgrans, men klienten skickar filerna sekventiellt till `/api/meta/uploads` i sma requestar for att undvika tunga multipart-batchar.
6. Under uppladdningen visas total progress, aktuell fil, filnummer i kon, kvarvarande mangd, estimerad tid och status per fil.
7. Vid lyckad uppladdning visas hur manga filer som sparades och hur manga dubbletter som hoppades over. Vid fel visas ett kort felmeddelande pa sidan. Fel som hinner na backend audit-loggas som `meta_media_upload/upload_failed`, aven nar anvandaren inte ar inloggad.
8. For varje ny video skapas en sändningsrad med video-hash och radhash.
9. Om `GEMINI_API_KEY` finns koas videon for analys. Backend extraherar en temporar ljudfil och skickar bara rosten till Gemini. Analysen fyller ett tydligast hort pall-id och avvikelser; ordernummer, sandningsnummer, anvandarnamn och kund lamnas tomma.
10. Super User kan oppna `Meta` i sidebaren, filtrera pa alla/videor/bilder, följa sändningstabellen och klicka ikonknappar for `Visa`, `Ladda ner`, `Analysera` eller `Radera`.

## Knappar och kontroller

| Kontroll | Var | Vem far | Vad hander | API/kod | Vanliga fel |
| --- | --- | --- | --- | --- | --- |
| Valj bilder eller videor | `meta-upload.html` | Alla med lank | Oppnar enhetens filvaljare med `accept="image/*,video/*"` och `multiple` | `meta-upload.html`, `meta_upload.js` | Vissa mobiler kan visa olika valjare beroende pa browser. |
| Automatisk uppladdning | `meta-upload.html` | Alla med lank | Startar direkt efter filval/drag-drop, skickar valda filer en och en som multipart till backend och visar total progress via `XMLHttpRequest.upload` | `POST /api/meta/uploads`, `meta_upload.js` | Nekas om inga filer skickas, om filtypen inte ar bild/video eller om maxstorlek passeras. Exakta dubbletter sparas inte igen utan visas som overhoppade. Om en fil misslyckas fortsatter klienten med nasta och visar slutlig sammanfattning. |
| Typ | `meta.html` | Super User | Filtrerar Meta-listan pa alla, videor eller bilder | `GET /api/meta/uploads?media_type=...` | Visar tomt lage om urvalet saknar uppladdningar. |
| Uppdatera | `meta.html` | Super User | Laddar om listan och visar toast nar det ar klart | `meta.js`, `api.get` | API-fel visas via standardlogg/toast. |
| Visa | `meta.html` | Super User | Oppnar modal med video eller bild via ikonknapp | `GET /api/meta/uploads/{upload_id}/content` | Stora videor strommas med byte-range men hamtas fran databasen. |
| Ladda ner | `meta.html` | Super User | Laddar ner mediafilen med serverns tidsstamplade filnamn via ikonknapp | `GET /api/meta/uploads/{upload_id}/content`, `api.download` | 403 om anvandaren inte ar Super User. |
| Radera | `meta.html` | Super User | Bekraftar och raderar media-raden inklusive blobben via ikonknapp | `DELETE /api/meta/uploads/{upload_id}` | Gar inte att angra. 404 om filen redan ar borttagen. |
| Sändningsanalys | `meta.html` | Super User | Visar tomma framtida lookup-kolumner for ordernummer, sandningsnummer, anvandarnamn och kund, samt rosttolkat pall-id, avvikelser, status, video, videolangd, stillbild och hash | `GET /api/meta/shipment-observations` | Tom eller `LLM saknas` om Gemini inte ar konfigurerad. |
| Analysera | `meta.html` | Super User | Extraherar ljud fran videon och skickar bara rosten till Gemini for pall-id och avvikelser. | `POST /api/meta/uploads/{upload_id}/analyze` | Kraver `GEMINI_API_KEY`. Osakra svar hamnar i `Kontrollera`. |

## Tekniskt flode

- `app/frontend/meta-upload.html` laddar bara `css/meta-upload.css` och `js/meta_upload.js`; den laddar inte `common.js` och far darfor ingen sidebar/auth-guard.
- `app/backend/routers/meta_uploads.py` accepterar flera `UploadFile` i faltet `files`.
- Backend tillater bild- och videofiler via MIME-typ eller kand filandelse.
- Om en klient skickar en `.mp4`/videoandelse med ljud-MIME, till exempel `audio/mp4`, normaliserar backend raden och content-endpointen till video-MIME sa nedladdningen fortfarande blir en videofil. Videopilen i analystabellen anvander dessutom `variant=playable`, som transkodar temporart till H.264/AAC for Windows-/browser-spelbar MP4.
- Publika uppladdningsfel loggas server-side som `meta_media_upload/upload_failed` med sanerad payload: metod, path, HTTP-status, feltyp, antal valda/accepterade/overhoppade filer och total uppladdad storlek. Filnamn, filinnehall, request body och privata anvandaruppgifter sparas inte. Raden syns i Historik > Felkoder som systemhandelse eftersom den publika sidan saknar login.
- `meta_upload.js` anvander `XMLHttpRequest` i stallet for `fetch` for att kunna visa upload-progress. Anvandaren kan valja manga filer samtidigt, men `META_UPLOAD_FILES_PER_REQUEST` ar `1`, sa klienten skickar en fil per request och fortsatter sekventiellt. Totalraden visar filnummer, kvarvarande bytes och ETA beraknad fran hittills uppladdade bytes. Filraderna far individuella progressbarer beraknade fran filernas storlek och total `loaded`; for valda videor forsoker browsern ocksa lasa videolangd fran metadata sekventiellt sa mobilen inte skapar manga video-prober samtidigt. Det finns ingen separat uppladdningsknapp: `setFiles` startar `startUpload` direkt nar minst en fil valts.
- Standard `META_UPLOAD_RATE_LIMIT_PER_MINUTE` ar `0` sa en legitim lang ko inte stoppas efter ett visst antal filer per minut. Om drift vill lagga pa publik throttling kan miljovariabeln sattas, men klienten fortsatter alltid att bara skicka en fil i taget.
- Varje uppladdning far ett gemensamt `batch_id`. Varje fil sparas som egen rad i `meta_media_uploads`.
- Tabellen sparar `original_filename`, `stored_filename`, `content_type`, `media_type`, `size_bytes`, eventuell `duration_seconds`, `content_hash`, binar `data`, `status`, `analysis`, `source` och `created_at`.
- `stored_filename` byggs av serverns UTC-datum/timestamp och filens ordning i batchen, till exempel `20260531_120102_123456Z_01.mov`.
- `content_hash` ar SHA-256 av filens bytes. Backend kollar bade redan sparade filer och filer i samma batch. Om hash finns sedan tidigare sparas inte blobben igen, och svaret far `skipped_count` samt poster med `reason=duplicate`.
- Ny media far status `pending_analysis`. For videor skapas `meta_shipment_observations` med `video_hash` och `record_hash`. Meta-vyn visar samma korta Video-ID i videokortet och i sändningstabellen sa Super User kan se vilken rad som tillhor vilken video.
- Gemini-konfigurationen ligger i `GEMINI_API_KEY`, `GEMINI_MODEL` och `GEMINI_API_BASE_URL`. Standardmodell ar `gemini-2.5-pro`. Backend extraherar ljud fran videon med ffmpeg eller `imageio-ffmpeg` och skickar bara den temporara ljudfilen via Gemini Files API.
- Autoanalys ar lagbelastad: `META_ANALYSIS_MAX_CONCURRENCY=1`, `META_ANALYSIS_START_DELAY_SECONDS=30` och `META_ANALYSIS_SPACING_SECONDS=15` gor att videor koas och analyseras en i taget med paus.
- Stillbilden ar best-effort och tas fran videon vid `META_LABEL_STILL_TIME_SECONDS` (standard 1.0 sekund). Saknad stillbild blockerar inte en lyckad rostanalys.
- Analys-prompten sager uttryckligen att Gemini inte ska tolka videobild, etiketter, transportetiketter eller innehallsforteckningar. Den ska bara anvanda rosten for ett tydligast hort pall-id och avvikelser. Om flera pall-id hors ska bara det tydligaste sparas och osakerheten skrivas i `uncertainty_notes`.
- Backend forsoker ta ut en etikettstillbild vid `META_LABEL_STILL_TIME_SECONDS` med `ffmpeg` eller `imageio-ffmpeg`. Om bilden inte kan extraheras kan rostanalysen anda bli `Klar`.
- `record_hash` raknas pa video-hash, eventuell label-still-hash, pall-id och avvikelser. Ordernummer, sandningsnummer, anvandarnamn och kund ingar inte langre eftersom de ska fyllas fran uppladdad data senare.
- `GET /api/meta/uploads`, `GET /api/meta/uploads/{upload_id}/content`, `GET /api/meta/shipment-observations`, `POST /api/meta/uploads/{upload_id}/analyze` och `DELETE /api/meta/uploads/{upload_id}` kraver Super User. `meta.html` anvander `initPage("meta", { requireSuperUser: true })` och visas bara for Super User i sidebaren.
- Radering audit-loggas som `entity_type=meta_media_upload` utan blobbinnehall i audit-vardet.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor ser jag ingen meny?" | Meta-uppladdningen ar en fristaende publik sida utan sidebar. Det ar avsiktligt. |
| "Kan jag valja flera filer pa mobilen?" | Ja, inputen har `multiple` och `accept="image/*,video/*"`. Exakt valjarvy beror pa iOS/Android och browser. |
| "Behöver jag trycka Ladda upp?" | Nej. Uppladdningen startar automatiskt direkt nar du har valt en eller flera filer. |
| "Kan jag valja manga videos pa en gang?" | Ja. Klienten tar emot hela valet men skickar filerna en och en till backend, sa stora val inte behover bli en enda tung request. Flow har ingen egen klientgrans for antal valda filer, men enheten/browsern kan ha praktiska gransningar. |
| "Hur vet jag att det laddar upp?" | Sidan visar total progress, aktuell fil, filnummer, kvarvarande mangd, ungefarlig tid kvar och status per fil medan uppladdningen pagar. |
| "Varfor heter videon datum och siffror?" | Backend doper sparade filer med uppladdningsdatum och timestamp sa varje fil blir unik och latt att sortera i Meta. Originalnamnet sparas separat. |
| "Hur ser jag vilken tabellrad som hor till vilken video?" | Jamfor Video-ID i sändningstabellen med Video-ID i videokortet. Bada bygger pa samma `video_hash`, och tabellen visar ocksa videons filnamn och langd. |
| "Varfor ar ordernummer, sandningsnummer, anvandarnamn och kund tomma?" | De hamtas inte langre fran videon. De ska fyllas fran uppladdad data via pall-id i ett senare steg. |
| "Vad analyserar Gemini nu?" | Bara rosten. Den ska hitta tydligast hort pall-id och avvikelser, inte lasa etiketten. |
| "Var hittar Super User uppladdade videos?" | I sidebarvyn `Meta`. Dar kan Super User filtrera pa videor, visa, ladda ner eller radera varje fil. |
| "Varför står analysen som LLM saknas?" | Servern saknar `GEMINI_API_KEY`. Lägg Gemini-nyckeln i `.env` lokalt eller Render secrets. |
| "Vad händer om Gemini är osäker?" | Raden får status `Kontrollera` och visar osäkerhetsanteckning. Appen ska inte gissa när video och ljud inte räcker. |
| "Varför saknas stillbild?" | Backend forsokte ta en enkel frame vid standardtiden men kunde inte extrahera bilden. Rostanalysen kan anda vara klar. |
| "Varfor sparades inte alla filer?" | Om en fil ar exakt samma som en redan sparad fil hoppas den over som dubblett for att inte ta onodigt databas-utrymme. Sidan visar hur manga som hoppades over. |
| "Varfor gick inte filen upp?" | Sidan accepterar bara bilder och videor. Backend kan ocksa neka tomma filer eller for stora batchar. |
| "Varfor syns inte anvandaren i Felkoder?" | Den publika Meta-uppladdningen kraver inte login. Backend loggar darfor misslyckade uppladdningar som systemhandelser utan anvandarnamn. |
| "Analyseras filerna direkt?" | Nya videor koas automatiskt nar `GEMINI_API_KEY` finns och `META_ANALYSIS_AUTO_START=true`, men analysen vantar enligt delay/spacing-settings och kors en video i taget. Bilder sparas bara som media. |

## Kallor

- `../app/frontend/meta-upload.html`
- `../app/frontend/meta.html`
- `../app/frontend/js/meta_upload.js`
- `../app/frontend/js/meta.js`
- `../app/frontend/css/meta-upload.css`
- `../app/backend/routers/meta_uploads.py`
- `../app/backend/meta_analysis_service.py`
- `../app/backend/models.py`
- `../app/alembic/versions/0022_meta_media_uploads.py`
- `../app/alembic/versions/0023_meta_upload_stored_filename.py`
- `../app/alembic/versions/0024_meta_upload_content_hash.py`
- `../app/alembic/versions/0025_meta_shipment_observations.py`
- `../app/alembic/versions/0026_meta_media_duration.py`
- `../app/alembic/versions/0027_meta_shipment_number.py`

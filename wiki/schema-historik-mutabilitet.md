---
title: Schemahistorikens mutabilitet
status: aktiv
updated: 2026-07-22
tags: [bemanning, historik, veckomall, datamodell, bugg, frysning]
---

# Schemahistorikens mutabilitet

**ÅTGÄRDAT (feature/historik-frys, 2026-07-21/22):** schemahistoriken fryses nu
per dygn — hoppa till [Losningen: schemafrysning](#losningen-schemafrysning-byggd-2026-07-21)
om du bara vill veta hur det fungerar idag. Analysen som följer beskriver läget
FÖRE fixen och gäller fortfarande för alla releaser t.o.m. `2026.30.1`.

Kort svar (före fixen): historiska schemadagar ar INTE en logg utan en live-projektion.
Endast explicita `schedule_cells` lagras per datum; allt annat (vilka personer
som syns, implicita malltimmar, standardaktivitet, etiketter/farger,
omradestillhorighet) beraknas vid lasning fran NUVARANDE masterdata. Darfor
andrar storre registerandringar (ta bort person, andra veckomall, byta
huvudaktivitet, ta bort aktivitet) retroaktivt bade uppgifter och timmar i
historiken. Detta ar INTE fixat i nagon release (2026-07-21): beteendet ar
identiskt fran aldsta `release/2026.26.1` till nyaste `release/2026.30.1`, sa
en uppgradering hjalper inte. Analysen nedan ar skeptikergranskad pastaende for
pastaende (arbetsflode 2026-07-21).

## Bekraftade retroaktivitetsvagar

Alla pastaenden nedan ar verifierade mot kod med `file:line`-referenser.

1. **Veckomallsandring** — `person_schedule_templates` har exakt en rad per
   `(person_id, weekday)` (`models.py:233-235`), ingen giltighetsperiod.
   `PUT /api/persons/{id}/schedule` muterar raderna pa plats
   (`person_schedules.py:147-150`). `get_template_hours_map_for_dates`
   (`template_service.py:160-206`) laser dem utan datumpredikat, sa en
   malländring idag ritar om alla forflutna dagar fran `persons.created_at`
   och framat. Extra falla: en person utan mallrader far koddefault 07-16
   minus lunch (`template_service.py:61-67`); forsta sparade mallrad byter
   darfor retroaktivt forflutna dagar fran default till mallen, och veckodagar
   utan rad blir retroaktivt lediga.
2. **`has_fixed_schedule` av/pa** — flaggan lases live
   (`template_service.py:84-85`); av = alla implicita timmar forsvinner ur hela
   historiken direkt, utan nagon datumvakt alls (infort 4647858, 2026-05-17).
3. **Byte av huvudaktivitet** — implicita malltimmar visas och summeras under
   personens NUVARANDE `home_activity_id`; ett byte idag flyttar historikens
   timmar till den nya aktiviteten i alla vyer.
4. **Ta bort person** — `DELETE /api/persons/{id}` hardraderar ALLA
   `schedule_cells` + mallrader (`persons.py:845-849`) och personens hela
   `person_productivity_daily` via FK `ON DELETE CASCADE`. Personens historik
   forstors permanent; enda sparet ar person-snapshoten i auditloggen (inte
   cellerna). Ingen varning om historikforlust i UI (endast generisk confirm).
   Regressionen infordes i 7d55584 (2026-05-21) som bytte fran
   soft-deactivate (`is_active=False`) till hard delete.
5. **Inaktivera person** — alla schemavyer filtrerar pa `Person.is_active`
   (`schedule_shared.py:75`, `overview.py`, `personal.py`) utan datumkansla,
   och celler hamtas bara for synliga personer — aven personens ororda
   explicita celler slutar visas i historiken.
6. **Ta bort aktivitet** — `DELETE /api/activities/{id}` skriver om explicit
   historik pa plats: alla historiska celler far `activity_id=NULL` +
   `empty_override=True` (`activities.py:841-844`), och
   `Person.home_activity_id` nollas. Forflutna arbetade timmar blir
   "uttryckligen tomma". Aven omradesradering gor samma sak for omradets
   aktiviteter (`areas.py:94-97`).
7. **Byta namn/farg/summeringsgrupp pa aktivitet** — celler lagrar bara
   `activity_id`; etikett, farg och `summary_activity_id`-kedjan slas upp i
   nuvarande `activities` vid lasning, sa presentation och bucketering av
   forfluten tid andras retroaktivt.
8. **Omradesscope** — historiska vyers person-/omradesfiltrering anvander
   nuvarande `home_area_id` och nuvarande `Activity.area_id`; flytt av
   person/aktivitet mellan omraden flyttar historiken mellan omradesvyer.

Drabbade ytor (alla anropar samma `get_template_hours_map_for_dates` med
nuvarande data): Bemanning-dagvyn, `/api/schedule/summary` (summeringen
adderar implicita malltimmar for forflutna datum), Oversikt vecka/manad
(`hours_total`, dominant aktivitet, "Ledig"), Mitt schema, publika API:t,
Narvarande-utskriften och produktivitetens KPI-segment.

## Produktivitetscachen

- `person_productivity_daily.schedule_signature` speglar ENBART explicita
  celler (antal, max `updated_at`, versionssumma) — mall-/flagg-/
  huvudaktivitetsandringar ar osynliga for den. Sa lange ingen ror dagens
  celler serveras gamla cacherader ofarandrade: ett oavsiktligt, skort skydd.
- Vid varje invalidering (celledit/RFID pa dagen, personradering som andrar
  signaturen, snapshot-omsynk, force-warm) raderas dagens cache och byggs om
  fran DAGENS veckomall — aktiviteter, tider och `planned_kpi_points` for
  forfluten tid skrivs om tyst. Planerade varden ar alltsa aldrig "vad som
  var planerat da".
- En personradering andrar signaturen for varje historisk dag personen hade
  celler → nasta lasning bygger om hela dagen for ALLA personer med dagens
  mallar, och den raderade personen forsvinner ur ombyggnaden.

## Befintliga skydd (enda tre)

1. **`persons.created_at`-vakten** (`template_service.py:47-58`): inga
   implicita malltimmar fore personens skapandedatum. Infort i b884bb9
   (2026-06-08), forsta release v0.1.6 (2026-06-09). Skyddar INTE mot
   andringar efter skapandet.
2. **`empty_override`-celler**: uttryckligen tomda timmar aterfylls inte av
   mallen — men bara timmar som nagon aktivt tomt har en sadan rad.
3. **Explicita cellers foretrade**: timmar med explicit cell behaller sin
   aktivitet vid malländringar — men skrivs anda om av person-/aktivitets-/
   omradesradering (punkt 4/6 ovan).

## Releasestatus (verifierad 2026-07-21)

- Beteendet ar byte-identiskt i historikrelevant kod over alla 36
  `release/*`-branchar (2026.26.1 → 2026.30.1); enda mellanliggande commit ar
  den icke-beteendemassiga MSSQL-truthy-fixen aaf8290.
- **Uppgradering fixar alltsa INTE den rapporterade buggen.**
- Endast fore-v0.1.6-byggen (taggar v0.1.1–v0.1.5, 2026-05-14–2026-06-02)
  saknar dessutom `created_at`-vakten (dar far nya personer fiktiv historik
  bakat). Fran v0.1.6 och framat ar det specifika symptomet fixat.

## Domanmodellen: plan, journal och dagens blandning

Emirs beskrivning 2026-07-22, som styr hela designen:

> Det ar ett bemanningsprogram. Arbetsledare pillar med det varje dag for att
> fylla i vad varje person har gjort under varje period. Vi vill kunna lagga
> schema for att ofta gor personer samma sak. Andrar vi personens schema ska
> det inte paverka hur de har jobbat. Arbetsledarna vill kunna ga tillbaka i
> tiden och kolla hur och vad personalen gjort och hur mycket vi bemannade pa
> varje stalle. Detta ar dyrbar information som vi inte kan paverka i efterhand.
>
> Det ar bade en plan och en journal: **framtiden ar en plan, fortiden ar en
> journal, idag ar en mix av bada.**

Tre konsekvenser som all kod har att folja:

1. **Veckomallen ar en bekvamlighet, inte sanningen.** Den finns for att folk
   ofta gor samma sak. Sanningen om en passerad timme ar vad arbetsledaren
   fyllde i — eller, om hen lat mallen sta, vad mallen sa **da**.
2. **Granulariteten ar timme, inte dygn.** Dagens formiddag ar journal medan
   eftermiddagen fortfarande ar plan. En malländring kl 15 far andra kvallen
   men aldrig formiddagen.
3. **"Hur mycket vi bemannade pa varje stalle"** ar en av de dyrbara
   fragorna. Alltsa maste aven omradestillhorigheten frysas, inte bara timmar
   och uppgift.

## Losningen: schemafrysning (byggd 2026-07-21/22)

Beslut av Emir: **(a) materialisering** plus **"ta bort framtida men behall
historiska"** for raderingar. Schemaandringar ska bara paverka planen —
journalen ska visa hur en person faktiskt har jobbat.

Sa fungerar det (`app/backend/schedule_freeze.py`):

1. **Materialisering**: bakgrundsjobbet `schedule_freeze_scheduler` (30-min
   pass, bakom ledarlaset) skriver vid dygnsskifte gardagens implicita
   malltimmar som explicita `schedule_cells` med `is_template_fill=True`.
   Timme med huvudaktivitet → cell med den aktiviteten; timme utan →
   `empty_override=True` (fryst som "schemalagd men tom"). Befintliga rader
   blockerar alltid insattning (ingen unik-nyckelkrock).
2. **Frysgrans**: `schedule_freeze_state.frozen_until` (singelrad). Alla
   `template_service`-uppslag returnerar None for datum <= gransen, sa
   mall-/flagg-/hemaktivitetsandringar ALDRIG paverkar frysta datum. Forsta
   korningen backfyller hela historiken fran aldsta cell/person.
2b. **Dagens skarning** (`elapsed_date`/`elapsed_hour`, infort 2026-07-22):
   samma jobb skriver ocksa ut dagens **redan passerade** malltimmar och
   flyttar fram en timgrans. `_apply_elapsed_cutoff` tar bort timmar fore
   gransen ur mallens svar for det datumet. Darfor kan en malländring kl 15
   inte rita om formiddagen — men kvallen, som fortfarande ar plan, foljer
   andringen. Gransen gar vid borjan av innevarande timme, samma skarning som
   Produktivitet anvander for "avslutade timmar".
2c. **Fryst omradestillhorighet** (`schedule_cells.activity_area_id`, infort
   2026-07-22): frysningen stamplar vilket omrade cellens aktivitet tillhorde
   da. Summeringen och omradesfiltreringen laser stampeln fore
   `Activity.area_id`, sa en omorganisation inte flyttar historisk bemanning
   mellan stallen. Ostamplade celler (framtid, eller redigerade efter
   frysning) faller tillbaka pa aktivitetens nuvarande omrade.
3. **Radering bevarar historik**: `DELETE person` fryser forst ofrysta
   gardagar, **skriver ut dagens malltimmar som celler** (annars skulle en
   borttagning kl 16 radera personens redan arbetade timmar ur dagens vy),
   rensar personens FRAMTIDA celler (datum > idag), inaktiverar personen
   (`is_active=False`, `has_fixed_schedule=False`, `rfid_code` frigors) och
   behaller alla celler t.o.m. idag. `DELETE aktivitet` tommer bara framtida
   celler och inaktiverar aktiviteten; historiska celler behaller
   `activity_id`. Omradesradering rensar bara framtida lan-/aktivitetsceller.
   **Undantag:** en person som skapats idag och aldrig fatt en schemacell ar
   ett felskapat register, inte historik - den hardraderas som forut
   (`person_predates_today`). Detsamma galler aktivitet utan celler.
4. **Historiska lasvagar visar borttagna personer**: dagvyn, summeringen,
   Oversikt, narvarolistan och produktivitetsombyggnaden inkluderar inaktiva
   personer som har celler pa frysta datum. Frontend loser etiketter via
   `include_inactive`-listorna som redan hamtas.
5. **Dagens datum ar fortfarande live**: idag projiceras fran mallen som
   forut och fryses forst vid dygnsskiftet. En malländring idag paverkar
   alltsa idag + framtid, aldrig gardagen och bakat.
6. **Mitt schema**: fill-celler visas som "Standardtid" (source `standard`),
   och frysta schemalagda-men-tomma timmar fortsatter raknas som Standardtid.
7. **Audit**: varje fryst dag skriver `schedule_freeze/materialize` med datum
   och antal celler (systemrad utan anvandare). Person-/aktivitetsradering
   med bevarad historik skriver `delete` med `mode=history_preserved`.

Manuell drift: `python -m app.backend.schedule_freeze --status` (visa grans)
eller utan flagga (kor ikapp). Tester: `tests/services/test_schedule_freeze.py`.

### Hur "schemalagd" havdas nar mallen inte langre svarar

Pa ett fryst datum returnerar `template_service` None, sa alla vyer som
byggde pa mallen maste harleda samma information ur cellerna i stallet.
Definitionen ar **timmar med innehall**: aktivitet, `empty_override` eller
`is_template_fill`.

- **Oversikt** (`_template_hours_count`): utan detta blir `template_hours=0`,
  och klienten ritar `template_hours === 0` som **"Ledig"** — hela historiken
  hade sett tom ut. Fangat i granskningen 2026-07-21, regressionstestat.
- **Bemanning dagvy** (`scheduled_hours`): behaller den diskreta
  schemalagd-markeringen for timmar utan aktivitet.
- **Cellredigering** (`_is_scheduled_hour`, `_empty_override_for_template`):
  nar en anvandare rattar en historisk cell avgor timmens befintliga celler
  om den var schemalagd, sa markeringen inte tappas vid rattningen.
- **Kopiera dag** hoppar over `is_template_fill`-celler, sa den beter sig
  exakt som fore frysningen (bara riktiga celler kopieras) och maldagen inte
  lases mot mottagarens egen mall.

### Guardrails mot tyst haveri

- **Radlas pa singelraden** (`_lock_freeze_state`): bakgrundsjobbet och en
  request-vag kan kora samtidigt vid forsta deployen. Kontroll och insattning
  sker i samma lasta transaktion, sa tva processer kan aldrig skriva
  fill-celler for samma dag och krocka pa unik-nyckeln. Singelraden skapas i
  migrationen sa det alltid finns nagot att lasa.
  **Fallgrop (fangad 2026-07-21):** MSSQL saknar `FOR UPDATE` och SQLAlchemy
  tystar bort `with_for_update()` helt dar - laset kompilerade till ingenting
  i drift. Losningen ar tabellhinten
  `.with_hint(ScheduleFreezeState, "WITH (UPDLOCK, HOLDLOCK)", "mssql")`
  vid sidan av `with_for_update()` (som tacker Postgres). Skyddat av ett test
  som kompilerar fragan mot bada dialekterna. Dessutom finns ett skyddsnat:
  `IntegrityError` per dag fangas, rullas tillbaka och hoppas over i stallet
  for att stanna hela frysningen.
- **Ingen IDENTITY pa frysraden**: `id` ar `autoincrement=False`, annars gor
  MSSQL kolumnen till IDENTITY och migrationens `INSERT ... VALUES (1, NULL)`
  avvisas - hela deployen hade fallit. Eget kompileringstest.

### Sa validerar du en migration mot MSSQL utan server (aterbrukbar teknik)

Den lokala testsviten bygger schemat med `Base.metadata.create_all` och kor
alltsa **aldrig** migrationsfilerna; hela alembic-kedjan gar dessutom inte pa
SQLite (en aldre migration anvander PG-syntax). En migration kan darfor vara
trasig lokalt gron. Rendera den i offline-lage i stallet - det ar exakt den
SQL deployen kor:

```
cd app
DATABASE_URL="mssql+pyodbc://u:p@host/db?driver=ODBC+Driver+18+for+SQL+Server" \
  python -m alembic -c alembic.ini upgrade <forra>:<din> --sql
```

Offline-laget ansluter inte, sa uppgifterna i URL:en spelar ingen roll. For
0049 avslojade det bade IDENTITY-fallgropen och att
`ALTER TABLE ... ADD ... BIT NOT NULL DEFAULT 0` ar metadata-only pa SQL
Server (alltsa snabb aven pa en stor `schedule_cells`).
- **Tak i request-vagen** (`REQUEST_PATH_MAX_DAYS = 3`): ligger fler dagar och
  vantar lamnas backfillen till bakgrundsjobbet, sa en registerandring aldrig
  drar igang en flerminuters backfill inne i ett HTTP-anrop.
- **Halsa-check "Schemafrysning"**: bakgrundsjobbet fangar sina egna fel och
  forblir `running`, sa ett trasigt frysjobb hade annars varit osynligt medan
  veckomallen ater borjade rita om gardagen. Checken varnar nar `frozen_until`
  halkar efter gardagen, eller saknas trots att schemadata finns (tom databas
  ger `info`). Utan den vore frysningen en guardrail som ar teater.
- **Midnattsfonstret**: bakgrundsjobbet fryser gardagen inom 30 minuter, men
  mellan midnatt och forsta passet vore gardagen annars fortfarande live.
  Darfor kallar mall-, person-, aktivitets- och omradesandringar
  `freeze_pending_for_request` fore sin mutation.

Kanda begransningar:

- **Innevarande timme ar plan, inte journal.** Skarningen gar vid timmens
  borjan, sa en andring kl 15:40 kan andra hela timmen 15. Samma konvention
  som Produktivitets "avslutade timmar".
- **Mellan tva jobbpass** (max 30 min) kan en nyss passerad timme annu vara
  omarkerad. Register- och mall-andringar kallar darfor
  `freeze_pending_for_request` forst, sa just de vagarna alltid ser en
  aktuell grans. En ren lasning kan daremot visa en nyss passerad timme som
  plan tills nasta pass.
- **Omradesstampeln satts vid frysning**, inte vid skrivning. En cell som
  skapas idag stamplas nar dagen fryses; en cell som redigeras pa en redan
  fryst dag far ingen stampel och faller tillbaka pa aktivitetens nuvarande
  omrade.
- Explicita cellredigeringar pa frysta dagar ar fortsatt tillatna (medvetna
  historikkorrigeringar, auditloggas som vanligt). Rensa dag pa fryst datum
  tar aven bort fill-celler och lamnar dagen tom — mallen aterfyller inte.
- Person-dragsortering pa en fryst dag med borttagna personer i vyn kan nekas
  av backend (sorteringen jamfor mot aktiva personer).
- Aktivitetsradering nollar fortfarande `summary_activity_id`-pekare mot den
  raderade aktiviteten, sa historisk summering visar da originalaktiviteterna
  ogrupperade i stallet.
- Aktivitetsetikett och farg slas fortfarande upp i nuvarande register, sa ett
  namnbyte syns aven bakat. Det ar avsiktligt (samma aktivitet, nytt namn) —
  men ateranvand aldrig en aktivitetskod for nagot annat, da omtolkas historik.
- Oversiktens `x/yh` kan visa en hogre namnare an fore frysningen for dagar med
  overtid, eftersom namnaren da ar timmar-med-innehall i stallet for malltimmar.
- `get_template_hours_map` (datumlos) saknar bade frysgrans och
  `created_at`-vakt och far aldrig anvandas i en lasvag som visar ett datum.
- **Personens hemomrade** styr fortfarande vilken omradesvy hen listas i, aven
  bakat: flyttas en person fran GG till AS forsvinner hen ur GG:s historiska
  personlista (men timmarna ligger kvar i det omrade dar arbetet utfordes,
  tack vare `activity_area_id`). Hemomradet ar en tillhorighet, inte en
  uppgift, sa det bedomdes som ratt avvagning.
- **Demo-lage** kor mot en egen sandbox-databas som bakgrundsjobbet inte ror,
  sa demo-historik forblir en live-projektion. Medvetet: sandboxarna ar
  kortlivade.

## Fixriktningar (historik: beslutet foll pa a + framtidsrensning)

- **(a) Materialisering/frysning** — VALD. Se ovan.
- **(b) Versionerade mallar**: `valid_from`/`valid_to` pa mallrader plus
  historik for `has_fixed_schedule`/`home_activity_id`; relationellt renare
  men ror 10+ lasstallen och produktivitetsombyggnaden. Avfardad som mer
  invasiv.
- **(c) Soft-delete**: delvis vald i formen "ta bort framtida men behall
  historiska" — radering blir deaktivering nar historik finns.

## Felsokningssvar for framtida chat

| Fraga | Svar |
| --- | --- |
| "Varfor andrades timmarna for en gammal vecka?" | Nagon andrade en veckomall, `has_fixed_schedule`, huvudaktivitet eller raderade person/aktivitet efterat — historiska dagar raknas om fran nuvarande register. Kontrollera Historik pa `person_schedule_template`/`person`/`activity` runt tidpunkten. |
| "Varfor forsvann en person ur gamla scheman?" | Personen raderades (all historik hardraderad) eller inaktiverades (filtreras bort ur alla datum). |
| "Varfor visar en gammal dag fel uppgift?" | Implicita malltimmar visar personens NUVARANDE huvudaktivitet; explicita celler visar nuvarande aktivitetsetikett for sitt `activity_id`. |
| "Hjalper det att uppgradera releasen?" | Till releaser t.o.m. 2026.30.1: nej — beteendet ar identiskt i alla. Fran releasen som innehaller feature/historik-frys (byggd efter 2026-07-21): ja, historiken fryses framat. Redan intraffade omskrivningar kan inte aterskapas, men befintlig historik fryses som den ser ut vid forsta backfillen. |
| "Vilka timmar ar sakra i historiken?" | Timmar med explicit cell (inkl. empty_override) star sig vid mallandringar — men forstors av person-/aktivitetsradering. |

## Kallor

- `../app/backend/template_service.py` (rad 47-58, 61-67, 84-85, 160-206)
- `../app/backend/routers/person_schedules.py` (rad 82-174)
- `../app/backend/routers/persons.py` (rad 838-859)
- `../app/backend/routers/activities.py` (rad 833-855)
- `../app/backend/routers/areas.py` (rad 65-102)
- `../app/backend/routers/schedule_query_routes.py` (rad 186-226)
- `../app/backend/routers/schedule_summary_routes.py` (rad 77-91)
- `../app/backend/routers/schedule_shared.py` (rad 75, 287, 544)
- `../app/backend/routers/overview.py` (rad 599-903)
- `../app/backend/routers/personal.py` (rad 70, 215-366)
- `../app/backend/person_productivity_cache.py`
- `../app/backend/models.py` (rad 147-167, 231-246)
- `../app/backend/schedule_freeze.py`
- `../app/backend/healthcheck_service.py` (`collect_schedule_freeze`)
- `../app/alembic/versions/0049_schedule_history_freeze.py`
- `../tests/services/test_schedule_freeze.py`
- Git: b884bb9 (created_at-vakt), 7d55584 (hard delete person), 4647858
  (has_fixed_schedule), aaf8290 (MSSQL truthy)

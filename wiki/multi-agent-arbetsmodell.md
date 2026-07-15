# Multi-agent-arbetsmodell (plan, ej genomförd)

Status 2026-07-09: **beslutad plan, väntar på genomförande.** Framtagen efter
9-agenters rekognosering + panelutvärdering (fork vs worktree vs klon).

## Beslutet

**Nej till forks. Ja till flytt ur OneDrive. En git-worktree per agent på
samma repo — med förberedd väg till fulla kloner vid 8–10 agenter.**

Panelbetyg: fork 3/10, worktree 8/10, klon 7/10.

- **Fork förkastad:** löser en förtroendegräns som inte finns (Emir har admin
  på origin, agenterna kör som honom) och löser noll lokala kollisioner.
  Dessutom: `EmirKadr/flow` är **produktionsinfrastruktur** — desktop-appens
  auto-updater läser releaser därifrån (`core/app_info.py:11`) och appen
  synkar observationsdata till `data/community-observations`. En `v*`-tagg
  dit skickar en desktopuppdatering till riktiga användare. `flow-docker.yml`
  kräver org-secrets som saknas i forks → röda builds.
- **OneDrive-flytt obligatorisk:** under själva rekognoseringen flappade
  `tests/conftest.py`:s innehåll mellan läsningar, `.githooks/` visade sig tom
  i ett skal och full i ett annat, `git status` hoppade från rent till ~10
  ändrade filer. Reproducerat live, inte teori.

## Målbild

```
C:\dev\flow\                     ← kanoniskt repo. Emirs. Ingen agent redigerar här.
   ├─ (tung gitignorerad data bor bara här: local_media 1.7G,
   │   testdata 227M, data 202M, referens 170M)
   └─ .git  ← delas av alla worktrees
C:\dev\flow-agents\
   ├─ a1\   ← worktree, branch feature/a1-<ämne>
   └─ ...
```

Kort rotsökväg är krav: checkout hard-failar (`Filename too long`) vid
~174-teckens rot; `core.longpaths` är inte satt.

## Fas 0 — Flytta ur OneDrive (engång, ~15 min)

1. Committa/pusha allt. Stäng alla agentsessioner, IDE, Obsidian (håller
   filhandtag i `wiki/.obsidian`), ev. dev-server.
2. Högerklick på repomappen → "Behåll alltid på den här enheten", vänta,
   **pausa sedan OneDrive-synken**.
3. Inventera det som förlorar sin enda backup: `git status --ignored` —
   säkra `app/.env`, `data/*.local.json`, `.secret-patterns.local`,
   `testdata/`, `referens/` separat (molnkopian raderas när mappen lämnar
   OneDrive).
4. `Move-Item` → `C:\dev\flow`. Verifiera: `git fsck` (ren baslinje fanns
   2026-07-08), `git log`, testa pre-push-hooken.
5. Kopiera Claude Code-projektdatan
   (`~/.claude/projects/C--Users-emikad-OneDrive---...` → `C--dev-flow`)
   så minne/historik följer med. Öppna om Obsidian-vaulten på nya sökvägen.

## Fas 1 — Provisioneringsskript `scripts/new_agent_workspace.ps1`

Fyra säkerhetsgater degraderar **tyst** i en oprovisionerad arbetskatalog:

| Saknas | Tyst konsekvens |
|---|---|
| `node_modules` | pre-push hoppar över tsc + eslint utan att blockera |
| `.secret-patterns.local` | pre-commits secret-värdesskanning av |
| `.flow-cli-cookies.txt` | `bug_reports_status` soft-exitar → buggrapportpåminnelsen slutar fungera |
| `testdata/` + `tests/services/golden/` | warehouse-regressionstester skippas → falskt grönt. Golden **kopieras alltid, regenereras aldrig** (regenerering förstör baslinjen) |

Skriptet gör:

1. `git worktree add C:\dev\flow-agents\<n> -b feature/<n>-<ämne>` (~16 MB, 5 s)
2. Kopiera: `app\.env`, `.flow-cli-cookies.txt`, `.secret-patterns.local`,
   `data\productivity_finance_prices.local.json`, `tests\services\golden\`
3. `mklink /J <worktree>\testdata C:\dev\flow\testdata` (junction, 0 MB)
4. `npm ci` (package.json/lock är spårade — verifierat; ~65 MB, ~1 min)
5. Verifieringsgrind: `git config core.hooksPath` == `.githooks`,
   `python -m tools.bug_reports_status` svarar

Kostnad per agent: ~100 MB, 1–2 min. Hooks + agent-audit-config ärvs gratis
(delad `.git/config`). Rivning: `git worktree remove` + branch-städning.

## Fas 2 — Regler in i AGENTS.md

Insättningspunkt: efter "Källkodshantering och release" (~rad 95), före
"Buggrapport-påminnelse". Innehåll:

1. **Regel #0: ingen agent redigerar i `C:\dev\flow`.** Allt agentarbete i
   egen worktree via provisioneringsskriptet.
2. **En agent = en worktree = en branch** (`feature/<agent>-<ämne>`, buggar
   `bug_report_<id>`). Git vägrar dubbel utcheckning — delvis självverkställande.
3. **Förbjudet i worktrees:** `git gc`, `git worktree prune`,
   `git config`-ändringar (delad config), `pip install` (global interpreter,
   ingen venv — mutation drabbar alla), `scripts/stop_local.bat` (dödar allt
   på port 8000 oavsett ägare), `sync_live_local.bat`.
4. **Dev-server i worktree:** aldrig `.bat`-launchers (hårdkodar 8000) —
   `uvicorn --port 87NN` per agent + egen `MEDIA_STORE_ROOT` (default är
   maskindelad `%TEMP%\flow_media_store`).
5. **Release-operationer och `main`-pushar är Emir-exklusiva.**
6. **Rebase före push för wiki-filer** — `wiki/log.md`/`index.md` är
   garanterade konflikthotspots.

## Fas 3 — Strukturella spärrar

`main`s GitHub branch protection är nästan tom, och en agent pushade rakt
till main 2026-07-08 — konvention räcker inte:

- **Branch protection på `main`:** kräv PR + `Tests` som required status check.
- **`.gitattributes`: `wiki/log.md merge=union`** — appendkonflikts löses automatiskt.
- **`gc.auto=0`** i kanoniska repot + schemalagd `git maintenance run`
  (auto-gc kan annars låsa alla worktrees samtidigt).
- Överväg smalare trigger för `flow-docker.yml` (bygger idag Docker-image med
  org-secrets på varje push till varje icke-main-branch som rör `app/**`).

## Skalning till 10 agenter

Maskinen håller (16C/32T, 96 GB RAM, 3,3 TB fritt — 10 parallella testsviter
är ~40 % trådutnyttjande). Det som brister, i ordning:

1. **Pre-push-stormar** (~1000 seriella tester/push; rebase → köra om) →
   CI-som-gate: sanktionera `FLOW_SKIP_PREPUSH_TESTS=1` på feature-branchar
   när branch protection kräver grön CI; ev. lokal semafor (max 3–4 sviter).
2. **Delad `.git` får låskontention** → konvertera aktivaste agenterna till
   lokala hardlink-kloner (4 s, ~20 MB) + **obligatoriskt**
   `git config core.hooksPath .githooks` per klon (annars tyst av).
3. **Per-agent-venv** (~2–4 GB st) när "ingen pip install"-disciplin brister.
4. **Verkliga taket är review-bandbredd:** 10 agenter ger 10–20 PR/dag, en
   människa granskar 4–6 paritetsstora. Kräver task-partitionering (disjunkta
   filområden), agentförgranskning, små/icke-överlappande uppgifter.

## Behövs INTE (explicit avfärdat)

- **Containers / databas-per-agent:** testsviten är redan självisolerad
  (in-memory-SQLite per test, alla testservrar binder port 0, pytest-tmp är
  parallellsäkert). Ingen delad test-DB existerar.
- **Forks** — se ovan.
- **Kopiera tung data per agent:** 95 % av dagens 5,4 GB är lokala artefakter;
  spårade repot är 14 MB.

## Implementationsordning

Fas 0 (flytt) → Fas 1 (skript) → Fas 2 (AGENTS.md) → Fas 3 (spärrar).
Allt utom flytten kan förberedas i förväg som feature-branch.

---
title: Källkodshantering och release (NoWaste)
status: aktiv
updated: 2026-07-06
tags: [git, release, octopus, deploy, nowaste, agent]
---

# Källkodshantering och release (NoWaste)

Kort svar: Flow har officiellt flyttat till NoWaste-servern (2026-07). Koden
ligger i GitHub-orgen `nowastelogistics`, deployas via Octopus-projektet
**Flow** till företagets Kubernetes, och NoWaste har en dokumenterad
branch- och releasemodell. Emir behöver inte följa processen till punkt och
pricka i detta repo, men agenter ska känna till den, använda dess begrepp
korrekt och kunna hjälpa till när releaser görs mot NoWaste-miljöerna.

## Viktigaste operativa regeln (Octopus)

**Alla commits till en `release/*`-branch bygger automatiskt en release i
Octopus.** Det är hela triggern — ingen manuell "create release" behövs:

Två hårda regler för agenter (beslut 2026-07-03, se `AGENTS.md`):

- **Nytt arbete = ny feature-branch.** Committa aldrig direkt på `main`.
- **Ny deploy = ny `release/*`-branch** (`release/{år}.{vecka}.{sekvens}`,
  nästa lediga sekvens). Återanvänd aldrig en gammal release-branch.

- Feature-ändring: merga feature-branchen till en `release/*`-branch → release byggs.
- Ändring som redan ligger i `main`/`master`: merga `main` till `release/*`-branchen → release byggs.

Releasen dyker sedan upp i Octopus-projektets dashboard (Projects → Övrigt →
Flow) och deployas därifrån till **development** (live) och, senare,
**production** (finns ännu inte — se miljötabellen i
[architecture.md](architecture.md)). Releasenamnen följer `år.vecka.sekvens`,
t.ex. `2026.26.1-rc00046`.

### Fallgrop: buntad push hoppar över imagebygget (lärt 2026-07-06)

Det som faktiskt bygger imagen och skapar Octopus-releasen är GitHub-workflowen
**`Flow Docker`** (`.github/workflows/flow-docker.yml`), som anropar NoWastes
gemensamma `procedures/docker.yml` och där får `octopus_server_url` +
`octopus_server_apikey`. Den har ett **`paths`-filter** (`app/**`, `Dockerfile`,
`.dockerignore`, `data/**`, `warehouse_tools/**`, `k8s/**`).

**Pushar man flera nya branchar i ett enda `git push`** (t.ex.
`git push origin feature/x release/y main`) och de delar samma commits, ser
GitHub inga *nya* ändrade filer unika för release-refen — de finns redan i
repot via de andra refsen i samma push — och **hoppar över Flow Docker-bygget**
för release-branchen. Resultat: grön push, men **ingen Octopus-release**. Det
inträffade med `release/2026.28.2` (byggdes aldrig), medan `release/2026.28.1`
byggdes korrekt eftersom den pushades för sig.

Två konsekvenser att internalisera:

- **Pusha release-branchen separat**, inte buntad med feature + main.
- **Grön `Tests`-workflow ≠ imagen byggd.** `Tests` saknar paths-filter och
  triggar alltid; `Flow Docker` har paths-filter och kan hoppas över. Att
  Tests är grön säger inget om att releasen finns i Octopus.

**Verifiera efter varje release-push:**

    gh run list --workflow=flow-docker.yml

Det ska finnas en körning för release-refen. Saknas den — eller finns bara en
röd — är releasen inte byggd.

**Återställning (sanktionerad):** kör bygget manuellt via workflow_dispatch:

    gh workflow run flow-docker.yml --ref release/<ver>

…eller Actions → Flow Docker → *Run workflow* → välj release-branchen.
`release/2026.27.4` skapades exakt så. Att bygga releasen deployar inget — du
klickar deploy i Octopus efteråt som vanligt.

## NoWaste branchmodell

| Branch | Från/till | Används för |
| --- | --- | --- |
| `master` | — | Huvudbranch; det som kör i produktion just nu. |
| `develop` | — | Kod inför nästa släpp. Får ej ligga efter `master` — allt som mergas till `master` ska även in i `develop`. Ingen halvfärdig kod: allt i `develop` ska vara redo för `master`. |
| `feature/{ärende}-{beskrivning}` | från/till `develop` | Ny funktionalitet, t.ex. `feature/nwl-1821-move_pallet`. Små bokstäver och bindestreck. |
| `release/x.y.z` (eller `release/{år}-{vecka}-{sekvens}`) | från `develop`, till `master` | Test och produktionsförberedelse. Commits hit bygger Octopus-releaser. |
| `hotfix/{beskrivning}` | från/till `master` | Kritiska produktionsfel. |
| `patch/x.y.z` | till/från `master` (eller från annan patch) | Planerat underhåll, mindre features, omfattande buggfixar. |

Grundregler:

- Varje feature får en egen branch (underlättar review).
- Feature-branch mergas inte till release-branch förrän PR/review är klar,
  och inte till `develop` förrän den är klar för live-push.
- Merga alltid med merge-commit (`git merge --no-ff`), inte fast-forward.
- Kör alltid `pull --rebase` (`git config --global pull.rebase true`) för att
  slippa onödiga merge-commits.
- Granska hela diffen innan commit; blanda inte autoformatering/upprensning
  med riktiga ändringar i samma commit.
- Patch-merge till `master` taggas: `git tag x.y.z -m "x.y.z"` +
  `git push --follow-tags`.

## Releaseflöde steg för steg

1. **Förberedelser** — checka ut `develop`, `git pull`, skapa
   `feature/{ärendenummer}-{kort-beskrivning}`.
2. **Utveckling** — ändra, testa lokalt, commit + push till `origin`,
   verifiera att GitHub Actions bygger.
3. **PR till `develop`** — kontrollera att PR:en är mot `develop`, inte
   `master`. Lägg PR-länk i ärendet, sätt status *Ready for review*.
   Mergas inte innan ärendet är testat och godkänt.
4. **Release-branch** — skapa `release/{år}-{vecka}-{sekvens}` från `develop`,
   merga in senaste release-branchen, merga in din feature-branch och pusha
   (→ Octopus bygger release automatiskt). Verifiera Actions och versionsnummer.
5. **Deploy till development (test)** — pusha releasen till *development* via
   Octopus. Skriv i push-chatten: projekt, miljö, version,
   ärendebeskrivning + länk. Uppdatera ärendet (*Testing by customer* när
   review är klar).
6. **Efter testning (Avengers)** — vid underkänt: fixa, merga till
   release-branchen igen, ny Octopus-deploy till development. Vid godkänt:
   merga PR till `develop`.
7. **Merge till `master`** — PR `develop` → `master`. Vissa projekt (CapI,
   WMan.Api) kräver extra code review.
8. **Release-tag** — GitHub → Code → Releases → *Draft a new release*, tagg i
   sekvensen `år.vecka.sekvens`, *Generate release notes*, publicera,
   verifiera Actions.
9. **Deploy till production** — pusha releasen till *production* via Octopus.
   Vid fel: kontrollera/byt deploy target.
10. **Avslutning** — skriv i push-chatten (projekt, miljö, version med länk
    till release notes, ärende) och sätt ärendet i *Test in production*.

## Vad som gäller specifikt för Flow-repot

- Flow-repots huvudbranch heter `main` (inte `master`) och repot har hittills
  jobbat med feature-branchar direkt mot `main`. NoWaste-modellen ovan är
  organisationens standard — agenter ska inte tvinga in Flow i den utan
  instruktion, men ska använda den när Emir jobbar mot NoWaste-flödet
  (release-branchar, Octopus-deployer, taggar).
- Deploy sker via Octopus-projektet **Flow** till företagets k8s
  (namespace `flow`, manifest i [../k8s/](../k8s/)). Development-miljön är
  `flow-development.nowastelogistics.com`.
- Render-driften är avvecklad sedan 2026-07-03; se [architecture.md](architecture.md) och
  [testing-release.md](testing-release.md).

## Felsökningssvar för framtida chat

- **"Hur gör jag en release?"** — committa/merga till en `release/*`-branch;
  Octopus bygger releasen automatiskt. Deploya sedan från Octopus-dashboarden
  till rätt miljö.
- **"Min release syns inte i Octopus"** — kontrollera i tur och ordning: (1)
  branchen heter faktiskt `release/...`; (2) det finns en **`Flow Docker`**-
  körning för refen (`gh run list --workflow=flow-docker.yml`) — INTE bara en
  grön `Tests`-körning, de är olika workflows; (3) om körningen saknas byggdes
  imagen aldrig (vanligast: release pushad buntad med andra refs, se fallgropen
  ovan) → kör `gh workflow run flow-docker.yml --ref release/<ver>`; (4) om
  körningen är röd, läs byggloggen. Grön push ≠ byggd image.
- **"Ska PR:en gå mot master?"** — nej, feature-PR:ar går mot `develop`;
  `develop` → `master` är en egen PR i steg 7.
- **"Vad ska taggen heta?"** — `år.vecka.sekvens`, t.ex. `2026.26.2`. Välj
  nästa lediga sekvensnummer.

## Källor

- `NOWASTE-Källkodshantering (GitHub)-030726-120937.pdf` (internt
  NoWaste-dokument, ingestat 2026-07-03; PDF:en ej incheckad i repot)
- Muntlig instruktion 2026-07-03: commits till `release/*` skapar automatiskt
  Octopus-releaser; main kan mergas till release-branch för ändringar som
  redan är i main.
- `../k8s/README.md`

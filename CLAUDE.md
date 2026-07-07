# CLAUDE.md

Projektets fullstandiga agentregler ligger i [AGENTS.md](AGENTS.md) — las den
forst. Den galler for alla agenter (Claude, Codex m.fl.) och innehaller bl.a.
paritetsregeln webb/desktop, hemlighets- och commitregler, test-, logg- och
halsoregler samt arkitekturkontrakt.

Snabborientering:

- Projektwiki i `wiki/` (LLM-underhallen): borja med `wiki/index.md`, folj
  `wiki/AGENTS.md` vid uppdateringar, logga i `wiki/log.md`.
- Drift sedan 2026-07: NoWaste-servern — k8s (`k8s/`), Octopus-projektet
  Flow, MSSQL. Commits till `release/*`-branchar bygger automatiskt releaser
  i Octopus. Se `wiki/nowaste-git-release.md`. Render-driften ar avvecklad
  (juli 2026) och dess filer borttagna ur repot.
- Huvudbranch: `main`.
- Vid arbetsstart: kor `python -m tools.bug_reports_status` och paminn Emir
  om oppna buggrapporter (regeln "Buggrapport-paminnelse" i AGENTS.md).

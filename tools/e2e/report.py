"""Agent-läsbar rapport för e2e-undersökningar.

Samlar skärmbilder, konsolfel, nätverksfel, timingar, assertions och
fynd, och skriver en Markdown-rapport (som agenten läser) plus JSON
(maskinläsbart). Ingen känslig data loggas.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Report:
    out_dir: Path
    title: str = "E2E-undersokning"
    base_url: str = ""
    screenshots: list[dict[str, Any]] = field(default_factory=list)
    console: list[dict[str, Any]] = field(default_factory=list)
    network: list[dict[str, Any]] = field(default_factory=list)
    timings: list[dict[str, Any]] = field(default_factory=list)
    assertions: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)

    def add_screenshot(self, name: str, path: Path, note: str = "") -> None:
        self.screenshots.append({"name": name, "path": str(path), "note": note})

    def add_console(self, page: str, entries: list[dict[str, Any]]) -> None:
        for entry in entries:
            self.console.append({"page": page, **entry})

    def add_network(self, page: str, failures: list[dict[str, Any]]) -> None:
        for failure in failures:
            self.network.append({"page": page, **failure})

    def add_timing(self, page: str, ms: float | None) -> None:
        self.timings.append({"page": page, "ms": ms})

    def add_assertion(self, name: str, ok: bool, detail: str = "") -> None:
        self.assertions.append({"name": name, "ok": bool(ok), "detail": detail})

    def add_finding(self, level: str, message: str) -> None:
        # level: info | warn | error
        self.findings.append({"level": level, "message": message})

    # --- sammanfattning ---
    def counts(self) -> dict[str, int]:
        return {
            "screenshots": len(self.screenshots),
            "console_errors": sum(1 for c in self.console if c.get("level") in ("error", "warning")),
            "network_failures": len(self.network),
            "assertions_failed": sum(1 for a in self.assertions if not a["ok"]),
            "assertions_total": len(self.assertions),
            "findings_error": sum(1 for f in self.findings if f["level"] == "error"),
        }

    def ok(self) -> bool:
        c = self.counts()
        return c["assertions_failed"] == 0 and c["findings_error"] == 0

    # --- skrivning ---
    def _markdown(self) -> str:
        c = self.counts()
        lines = [
            f"# {self.title}",
            "",
            f"- Miljo: `{self.base_url}`",
            f"- Skarmbilder: {c['screenshots']}",
            f"- Konsolfel/varningar: {c['console_errors']}",
            f"- Natverksfel (4xx/5xx/failed): {c['network_failures']}",
            f"- Assertions: {c['assertions_total'] - c['assertions_failed']}/{c['assertions_total']} OK",
            f"- Status: {'OK' if self.ok() else 'PROBLEM'}",
            "",
        ]
        if self.findings:
            lines += ["## Fynd", ""]
            for f in self.findings:
                marker = {"error": "[FEL]", "warn": "[VARN]", "info": "[info]"}.get(f["level"], "[info]")
                lines.append(f"- {marker} {f['message']}")
            lines.append("")
        if self.assertions:
            lines += ["## Assertions", ""]
            for a in self.assertions:
                lines.append(f"- {'OK ' if a['ok'] else 'FEL'} {a['name']}" + (f" — {a['detail']}" if a["detail"] else ""))
            lines.append("")
        if self.screenshots:
            lines += ["## Skarmbilder", ""]
            for s in self.screenshots:
                note = f" — {s['note']}" if s["note"] else ""
                lines.append(f"- `{Path(s['path']).name}`{note}")
            lines.append("")
        if self.timings:
            lines += ["## Laddtider", ""]
            for t in self.timings:
                ms = f"{t['ms']:.0f} ms" if t["ms"] is not None else "-"
                lines.append(f"- {t['page']}: {ms}")
            lines.append("")
        if self.console:
            lines += ["## Konsol (fel/varningar)", ""]
            for entry in self.console:
                if entry.get("level") in ("error", "warning"):
                    lines.append(f"- [{entry['level']}] {entry['page']}: {entry.get('text', '')[:300]}")
            lines.append("")
        if self.network:
            lines += ["## Natverksfel", ""]
            for n in self.network:
                lines.append(f"- {n['page']}: {n.get('status', '?')} {n.get('url', '')[:200]}")
            lines.append("")
        return "\n".join(lines)

    def write(self) -> tuple[Path, Path]:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        md_path = self.out_dir / "report.md"
        json_path = self.out_dir / "report.json"
        md_path.write_text(self._markdown(), encoding="utf-8")
        json_path.write_text(
            json.dumps(
                {
                    "title": self.title,
                    "base_url": self.base_url,
                    "counts": self.counts(),
                    "ok": self.ok(),
                    "screenshots": self.screenshots,
                    "console": self.console,
                    "network": self.network,
                    "timings": self.timings,
                    "assertions": self.assertions,
                    "findings": self.findings,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return md_path, json_path

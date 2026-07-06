"""Stämplar ?v=<innehålls-hash> på lokala script/link-taggar i frontend-HTML.

Körs i Docker-bygget (se Dockerfile) så att produktions-HTML pekar på
versionsstämplade URL:er. Backendens static_cache_headers-middleware ger
?v=-URL:er ett års immutable-cache — hashen byter när filinnehållet byter,
så webbläsare kan aldrig köra gammal JS/CSS mot nytt API.

Repofilerna stämplas ALDRIG av det här verktyget i det vanliga arbetsflödet:
lokal utveckling och desktop-appen läser filerna direkt (dev-läget svarar
no-store), och de handskrivna ?v=-etiketterna i repot fungerar som vanligt.
Innehålls-hash kräver inga build-args och är deterministisk: oförändrade
filer behåller sin hash mellan deployer och ligger kvar i webbläsarcachen.

Användning:
    python -m tools.stamp_asset_versions [--frontend-dir PATH] [--check]

--check skriver ingenting; avslutar med kod 1 om någon tagg skulle ändras.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FRONTEND_DIR = ROOT / "app" / "frontend"

# Lokala (rotrelativa) script-src och stylesheet-href, med eller utan query.
_ASSET_TAG_RE = re.compile(
    r"""(?P<prefix>(?:src|href)=")(?P<path>/[^"?]+\.(?:js|css))(?:\?[^"]*)?(?P<suffix>")""",
)

_HASH_LENGTH = 10


def _content_hash(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()[:_HASH_LENGTH]


def stamp_html(html: str, frontend_dir: Path, html_name: str) -> tuple[str, list[str]]:
    """Returnerar (ny HTML, lista med fel för taggar vars fil saknas)."""
    errors: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        asset_path = match.group("path")
        target = frontend_dir / asset_path.lstrip("/")
        if not target.is_file():
            errors.append(f"{html_name}: {asset_path} finns inte under {frontend_dir}")
            return match.group(0)
        return f"{match.group('prefix')}{asset_path}?v={_content_hash(target)}{match.group('suffix')}"

    return _ASSET_TAG_RE.sub(_replace, html), errors


def stamp_frontend(frontend_dir: Path, check_only: bool) -> int:
    html_files = sorted(frontend_dir.glob("*.html"))
    if not html_files:
        print(f"Inga HTML-filer i {frontend_dir}", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    changed: list[str] = []
    for html_file in html_files:
        original = html_file.read_text(encoding="utf-8")
        stamped, errors = stamp_html(original, frontend_dir, html_file.name)
        all_errors.extend(errors)
        if stamped != original:
            changed.append(html_file.name)
            if not check_only:
                html_file.write_text(stamped, encoding="utf-8", newline="")

    for error in all_errors:
        print(f"FEL: {error}", file=sys.stderr)
    if all_errors:
        return 1
    if check_only:
        if changed:
            print(f"{len(changed)} HTML-filer skulle stämplas om: {', '.join(changed)}")
            return 1
        print("Alla taggar redan stämplade.")
        return 0
    print(f"Stämplade {len(changed)} av {len(html_files)} HTML-filer med innehålls-hash.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frontend-dir", default=str(DEFAULT_FRONTEND_DIR))
    parser.add_argument("--check", action="store_true", help="Skriv inget; avsluta med 1 om något skulle ändras.")
    args = parser.parse_args()
    return stamp_frontend(Path(args.frontend_dir), check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate Windows release artifacts after build_windows.bat."""
from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

from core.app_info import APP_VERSION


ROOT = Path(__file__).resolve().parent.parent


def _frontend_package_files() -> tuple[str, ...]:
    frontend_dir = ROOT / "app" / "frontend"
    if not frontend_dir.is_dir():
        return ()
    return tuple(
        f"_internal/app/frontend/{path.relative_to(frontend_dir).as_posix()}"
        for path in sorted(frontend_dir.rglob("*"))
        if path.is_file()
    )


REQUIRED_PACKAGE_FILES = (
    "flow.exe",
    *_frontend_package_files(),
    "_internal/desktop/assets/flow_icon.ico",
    "_internal/desktop/assets/flow_icon.svg",
    "_internal/warehouse_tools/vendor/allokering12.1.py",
    "_internal/warehouse_tools/vendor/wms_sok79.py",
    "_internal/warehouse_tools/vendor/lowfreqdata/buffertpall/artikel_max.csv",
    "_internal/warehouse_tools/vendor/lowfreqdata/buffertpall/observations.csv.gz",
)


def _normalize_zip_name(name: str) -> str:
    return name.replace("\\", "/").lstrip("/")


def _expected_zip_entries() -> set[str]:
    return set(REQUIRED_PACKAGE_FILES)


def check_release_artifacts(
    *,
    release_dir: Path,
    version: str,
    require_setup: bool = False,
    smoke: bool = True,
) -> list[str]:
    errors: list[str] = []
    package_dir = release_dir / "flow"
    zip_path = release_dir / f"flow-{version}-win64.zip"
    setup_path = release_dir / f"flow-{version}-Setup.exe"

    if not package_dir.is_dir():
        errors.append(f"Saknar release-mapp: {package_dir}")
    else:
        for relative in REQUIRED_PACKAGE_FILES:
            if not (package_dir / Path(relative)).is_file():
                errors.append(f"Saknar fil i release-mapp: {relative}")

    if not zip_path.is_file():
        errors.append(f"Saknar zip: {zip_path}")
    else:
        try:
            with zipfile.ZipFile(zip_path) as archive:
                names = {_normalize_zip_name(info.filename) for info in archive.infolist()}
        except zipfile.BadZipFile:
            errors.append(f"Ogiltig zip: {zip_path}")
        else:
            for expected in _expected_zip_entries():
                if expected not in names:
                    errors.append(f"Saknar fil i zip: {expected}")

    if require_setup and not setup_path.is_file():
        errors.append(f"Saknar Setup.exe: {setup_path}")
    if setup_path.exists() and setup_path.stat().st_size <= 0:
        errors.append(f"Setup.exe ar tom: {setup_path}")

    exe_path = package_dir / "flow.exe"
    if smoke and exe_path.is_file():
        result = subprocess.run(
            [str(exe_path), "--smoke-test"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            errors.append(
                "Release-exe smoke-test misslyckades: "
                f"exit {result.returncode}\n{result.stdout}\n{result.stderr}"
            )

    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, default=ROOT / "release")
    parser.add_argument("--version", default=APP_VERSION)
    parser.add_argument("--require-setup", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors = check_release_artifacts(
        release_dir=args.release_dir,
        version=args.version,
        require_setup=args.require_setup,
        smoke=not args.skip_smoke,
    )
    if errors:
        for error in errors:
            print(f"[release-check] {error}", file=sys.stderr)
        return 1
    print(f"Release artifacts OK for flow {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

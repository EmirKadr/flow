# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for Bemanning."""
from pathlib import Path


project_root = Path(SPECPATH)
app_icon = project_root / "desktop" / "assets" / "app_icon.ico"
frontend_dir = project_root / "app" / "frontend"

a = Analysis(
    ["desktop/main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(app_icon), "desktop/assets"),
        (str(frontend_dir), "app/frontend"),
    ],
    hiddenimports=[
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtPrintSupport",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tests"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Bemanning",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(app_icon),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Bemanning",
)

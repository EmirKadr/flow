# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for flow."""
from pathlib import Path


project_root = Path(SPECPATH)
app_icon_ico = project_root / "desktop" / "assets" / "flow_icon.ico"
app_icon_svg = project_root / "desktop" / "assets" / "flow_icon.svg"
frontend_dir = project_root / "app" / "frontend"
warehouse_vendor_dir = project_root / "warehouse_tools" / "vendor"
forecast_training = project_root / "warehouse_tools" / "mg_forecast" / "training.parquet"

# Träningscachen är lokal utvecklardata och inte committad. Inkludera den
# bara i bygget om den finns på disk, annars hoppas den över utan att
# spec:en kraschar.
_optional_datas = []
if forecast_training.exists():
    _optional_datas.append((str(forecast_training), "warehouse_tools/mg_forecast"))

a = Analysis(
    ["desktop/main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(app_icon_ico), "desktop/assets"),
        (str(app_icon_svg), "desktop/assets"),
        (str(frontend_dir), "app/frontend"),
        (str(warehouse_vendor_dir), "warehouse_tools/vendor"),
        *_optional_datas,
    ],
    hiddenimports=[
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtPrintSupport",
        "PyQt6.QtSvg",
        "lightgbm",
        "numpy",
        "pyarrow",
        "pyarrow.parquet",
        "xgboost",
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
    name="flow",
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
    icon=str(app_icon_ico),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="flow",
)

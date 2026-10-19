# PyInstaller onedir configuration. Only public application assets are added.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(SPEC).parent.parent
hiddenimports = collect_submodules("hcmus_hub")

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "dashboard"), "dashboard"),
        (str(ROOT / "config" / "sources.json"), "config"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="HCMUS-Hub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="HCMUS-Hub",
)

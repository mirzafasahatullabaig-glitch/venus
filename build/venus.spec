# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Venus brain — one-file venus.exe.

Build from the repo root:
    .venv\\Scripts\\pyinstaller.exe build\\venus.spec --distpath dist --workpath build\\_work --clean --noconfirm

Bundles web/ and personas/ (read via _MEIPASS) plus config.example.toml so the
exe can seed a config.toml beside itself on first run. config.toml itself is NOT
bundled — it lives next to the exe and the user edits it.
"""
import os
from PyInstaller.utils.hooks import collect_submodules

BRAIN = os.path.abspath(os.path.join(SPECPATH, "..", "brain"))

datas = [
    (os.path.join(BRAIN, "web"), "web"),
    (os.path.join(BRAIN, "personas"), "personas"),
    (os.path.join(BRAIN, "config.example.toml"), "."),
]

# uvicorn loads its loop/protocol implementations dynamically; pull them all in.
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("httptools")
    + collect_submodules("websockets")
)

a = Analysis(
    [os.path.join(BRAIN, "serve.py")],
    pathex=[BRAIN],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
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
    name="venus",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for AppTrackr. Build from the repository root:
#   pyinstaller packaging/apptrackr.spec

import os

ROOT = os.path.abspath(os.getcwd())
PKG = os.path.join(ROOT, "apptrackr")

a = Analysis(
    [os.path.join(PKG, "__main__.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(PKG, "data", "schema.sql"), os.path.join("apptrackr", "data")),
        (os.path.join(PKG, "assets"), os.path.join("apptrackr", "assets")),
    ],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtNetwork", "pynput.mouse._win32"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AppTrackr",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(ROOT, "packaging", "apptrackr.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AppTrackr",
)

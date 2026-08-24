# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [("ui.html", "."), ("icon/512.png", "icon"), ("icon/app.ico", "icon")]
hiddenimports = []
for package in ("webview", "pystray"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    hiddenimports += package_hidden

a = Analysis(
    ["widget_v2.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AI-CLI-Control-Center",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="icon/app.ico",
    version="packaging/windows-version.txt",
)

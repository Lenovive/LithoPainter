# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Lithopainter.
# Invoked by ..\build_exe.ps1. Outputs go to ..\dist\Lithopainter\.

import os

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

block_cipher = None

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'lithopainter_gui.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        (os.path.join(PROJECT_ROOT, 'lithopainter.jar'), '.'),
        (os.path.join(PROJECT_ROOT, 'resources', 'filament-palette-0.10mm.json'), 'resources'),
        (os.path.join(PROJECT_ROOT, 'resources', 'bambu_template'), os.path.join('resources', 'bambu_template')),
    ],
    hiddenimports=['bambu_3mf'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc', 'doctest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Lithopainter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    windowed=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Lithopainter',
)

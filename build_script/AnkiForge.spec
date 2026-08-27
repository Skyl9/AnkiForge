# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files

# 1. COLLECTE DES DÉPENDANCES CACHÉES
hidden_imports = [
    'peewee',
    'jinja2.ext',
    'genanki',
    'qtawesome',
    'platformdirs',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
]

# 2. COLLECTE DES RESSOURCES (ASSETS)
datas = collect_data_files('qtawesome')

# 3. COLLECTE DES FICHIERS BINAIRES COMPILÉS (EXTENSION C)
binaries = [
    ('../src/ankiforge/c_ext/levenshtein_distance.so', 'ankiforge/c_ext')
]

a = Analysis(
    ['../src/ankiforge/__main__.py'],
    pathex=['..'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AnkiForge',
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
    # icon='../src/ankiforge/resources/icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AnkiForge',
)

# CONFIGURATION MAC
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='AnkiForge.app',
        icon=None,
        bundle_identifier='com.ankiforge.app',
        version='0.2.0',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'NSRequiresAquaSystemAppearance': 'False',
        },
    )

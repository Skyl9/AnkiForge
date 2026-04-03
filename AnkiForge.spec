# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 1. COLLECTE DES DÉPENDANCES CACHÉES
# PyInstaller a parfois du mal à voir ce que Jinja2 ou QTAwesome utilisent en arrière-plan.
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
# On s'assure que les polices de QTAwesome (FontAwesome) sont bien copiées dans l'exécutable
datas = collect_data_files('qtawesome')

# Si tu as un dossier d'icônes ou un logo spécifique à toi dans src/ankiforge/resources,
# il faudrait l'ajouter ici :
# datas.append(('src/ankiforge/resources', 'ankiforge/resources'))

a = Analysis(
    ['src/ankiforge/__main__.py'], # Ton point d'entrée refactorisé
    pathex=[],
    binaries=[],
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
    upx=True, # Compresse l'exécutable si UPX est installé
    console=True, # 🚨 CONSEIL SENIOR : Laisse sur True pour le premier test !
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='src/ankiforge/resources/icon.ico', # Décommente quand tu auras une icône
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

# CONFIGURATION MAC (Si tu compiles sur macOS)
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='AnkiForge.app',
        icon=None,
        bundle_identifier='com.ton_nom.ankiforge',
        version='0.2.0',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'NSRequiresAquaSystemAppearance': 'False',
        },
    )
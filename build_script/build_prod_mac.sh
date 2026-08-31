#!/bin/bash
# Script de compilation Nuitka optimisé pour macOS
set -euo pipefail

cd "$(dirname "$0")/.."

echo "🧹 Nettoyage du dossier de production..."
rm -rf dist_prod/
mkdir -p dist_prod

echo "⚙️ Compilation de l'extension C native Levenshtein (Universal 2)..."
clang -O3 -flto -shared -fPIC -arch arm64 -arch x86_64 -o src/ankiforge/c_ext/levenshtein_distance.so src/ankiforge/c_ext/levenshtein_distance.c || true

echo "🚀 Démarrage de la compilation avec Nuitka..."

export CFLAGS="-O2"
export CXXFLAGS="-O2"

uv run --no-sync python -m nuitka \
    --standalone \
    --macos-create-app-bundle \
    --macos-app-name="AnkiForge" \
    --macos-app-version="0.2.0" \
    --enable-plugin=pyside6 \
    --include-package=ankiforge \
    --nofollow-import-to=google \
    --nofollow-import-to=faiss \
    --nofollow-import-to=tkinter \
    --nofollow-import-to=matplotlib \
    --nofollow-import-to=docutils \
    --include-package-data=qtawesome \
    --include-data-dir=src/ankiforge/c_ext=src/ankiforge/c_ext \
    --low-memory \
    --lto=no \
    --output-dir=dist_prod \
    --output-filename=AnkiForge \
    --assume-yes-for-downloads \
    src/ankiforge/__main__.py

# Harmonisation du bundle .app
if [ -d "dist_prod/__main__.app" ]; then
    rm -rf dist_prod/AnkiForge.app
    mv dist_prod/__main__.app dist_prod/AnkiForge.app
fi

if [ -f "dist_prod/AnkiForge.app/Contents/MacOS/__main__" ]; then
    mv dist_prod/AnkiForge.app/Contents/MacOS/__main__ dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge
elif [ -f "dist_prod/AnkiForge.app/Contents/MacOS/__main__.bin" ]; then
    mv dist_prod/AnkiForge.app/Contents/MacOS/__main__.bin dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge
elif [ -f "dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge.bin" ]; then
    mv dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge.bin dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge
fi

chmod +x dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge || true

echo "📦 Copie des dépendances non compilées en C et des ressources..."
# Copie des ressources dans Resources et MacOS (compatibilité get_resource_path)
mkdir -p dist_prod/AnkiForge.app/Contents/Resources/src
mkdir -p dist_prod/AnkiForge.app/Contents/MacOS/src
cp -r src/ressources dist_prod/AnkiForge.app/Contents/Resources/src/
cp -r src/ressources dist_prod/AnkiForge.app/Contents/MacOS/src/

# Copie des packages purs / dynamiques
uv run --no-sync python -c "import google, shutil, pathlib; shutil.copytree(pathlib.Path(google.__file__).parent, 'dist_prod/AnkiForge.app/Contents/MacOS/google', dirs_exist_ok=True)" 2>/dev/null || true
uv run --no-sync python -c "import faiss, shutil, pathlib; shutil.copytree(pathlib.Path(faiss.__file__).parent, 'dist_prod/AnkiForge.app/Contents/MacOS/faiss', dirs_exist_ok=True)" 2>/dev/null || true

echo "🔒 Signature de code Ad-Hoc du bundle macOS..."
codesign --force --deep -s - dist_prod/AnkiForge.app

echo "✅ Compilation macOS terminée avec succès !"
echo "📁 Bundle produit : dist_prod/AnkiForge.app"

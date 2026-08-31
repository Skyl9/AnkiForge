#!/bin/bash
# Script de compilation Nuitka optimisé pour Linux
set -euo pipefail

cd "$(dirname "$0")/.."

echo "🧹 Nettoyage du dossier de production..."
rm -rf dist_prod/
mkdir -p dist_prod

echo "⚙️ Compilation de l'extension C native Levenshtein..."
gcc -O3 -flto -shared -o src/ankiforge/c_ext/levenshtein_distance.so -fPIC src/ankiforge/c_ext/levenshtein_distance.c || true

echo "🚀 Démarrage de la compilation avec Nuitka..."

export CFLAGS="-O2"
export CXXFLAGS="-O2"

uv run --no-sync python -m nuitka \
    --standalone \
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

# Harmonisation du nom de dossier généré
if [ -d "dist_prod/__main__.dist" ]; then
    rm -rf dist_prod/AnkiForge.dist
    mv dist_prod/__main__.dist dist_prod/AnkiForge.dist
fi

if [ -f "dist_prod/AnkiForge.dist/__main__.bin" ]; then
    mv dist_prod/AnkiForge.dist/__main__.bin dist_prod/AnkiForge.dist/AnkiForge
elif [ -f "dist_prod/AnkiForge.dist/__main__" ]; then
    mv dist_prod/AnkiForge.dist/__main__ dist_prod/AnkiForge.dist/AnkiForge
elif [ -f "dist_prod/AnkiForge.dist/AnkiForge.bin" ]; then
    mv dist_prod/AnkiForge.dist/AnkiForge.bin dist_prod/AnkiForge.dist/AnkiForge
fi

chmod +x dist_prod/AnkiForge.dist/AnkiForge || true

echo "📦 Copie des dépendances non compilées en C et des ressources..."
# Copie des ressources
mkdir -p dist_prod/AnkiForge.dist/src
cp -r src/ressources dist_prod/AnkiForge.dist/src/

# Copie des packages purs / dynamiques
uv run --no-sync python -c "import google, shutil, pathlib; shutil.copytree(pathlib.Path(google.__file__).parent, 'dist_prod/AnkiForge.dist/google', dirs_exist_ok=True)" 2>/dev/null || true
uv run --no-sync python -c "import faiss, shutil, pathlib; shutil.copytree(pathlib.Path(faiss.__file__).parent, 'dist_prod/AnkiForge.dist/faiss', dirs_exist_ok=True)" 2>/dev/null || true

echo "✅ Compilation Linux terminée avec succès !"
echo "📁 Dossier de distribution : dist_prod/AnkiForge.dist"

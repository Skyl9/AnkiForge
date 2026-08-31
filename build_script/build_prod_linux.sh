#!/bin/bash
# Script de compilation Nuitka optimise pour Linux
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[INFO] Nettoyage du dossier de production..."
rm -rf dist_prod/
mkdir -p dist_prod

echo "[INFO] Compilation de l'extension C native Levenshtein..."
mkdir -p src/ankiforge/c_ext
gcc -O3 -flto -shared -o src/ankiforge/c_ext/levenshtein_distance.so -fPIC src/ankiforge/c_ext/levenshtein_distance.c || true

echo "[INFO] Demarrage de la compilation avec Nuitka..."

export CFLAGS="-O2"
export CXXFLAGS="-O2"
NCPUS=$(nproc || echo 4)

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
    --low-memory \
    --jobs="${NCPUS}" \
    --lto=no \
    --output-dir=dist_prod \
    --output-filename=AnkiForge \
    --assume-yes-for-downloads \
    src/ankiforge/__main__.py

# Harmonisation du nom de dossier genere
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

echo "[INFO] Copie des dependances, ressources et extensions C..."
# Copie des ressources
mkdir -p dist_prod/AnkiForge.dist/src/ressources
cp -r src/ressources/* dist_prod/AnkiForge.dist/src/ressources/

# Copie de l'extension C
mkdir -p dist_prod/AnkiForge.dist/src/ankiforge/c_ext
cp -r src/ankiforge/c_ext/* dist_prod/AnkiForge.dist/src/ankiforge/c_ext/

# Copie des packages purs / dynamiques
uv run --no-sync python -c "import google, shutil, pathlib; shutil.copytree(pathlib.Path(google.__file__).parent, 'dist_prod/AnkiForge.dist/google', dirs_exist_ok=True)" 2>/dev/null || true
uv run --no-sync python -c "import faiss, shutil, pathlib; shutil.copytree(pathlib.Path(faiss.__file__).parent, 'dist_prod/AnkiForge.dist/faiss', dirs_exist_ok=True)" 2>/dev/null || true

echo "[SUCCESS] Compilation Linux terminee avec succes !"
echo "[INFO] Dossier de distribution : dist_prod/AnkiForge.dist"

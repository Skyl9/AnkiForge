#!/bin/bash
# Script de compilation Nuitka optimise pour macOS (Mode Fast Standalone)
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[INFO] Nettoyage du dossier de production..."
rm -rf dist_prod/
mkdir -p dist_prod

echo "[INFO] Compilation de l'extension C native Levenshtein (Universal 2)..."
mkdir -p c_ext
clang -O3 -flto -shared -fPIC -arch arm64 -arch x86_64 -o c_ext/levenshtein_distance.so c_ext/levenshtein_distance.c || true

echo "[INFO] Demarrage de la compilation avec Nuitka (Noyau AnkiForge)..."

export CFLAGS="-O2"
export CXXFLAGS="-O2"
NCPUS=$(sysctl -n hw.logicalcpu || echo 4)

uv run --no-sync python -m nuitka \
    --standalone \
    --macos-create-app-bundle \
    --macos-app-name="AnkiForge" \
    --macos-app-version="0.2.0" \
    --macos-app-icon=none \
    --enable-plugin=pyside6 \
    --include-package=ankiforge \
    --no-deployment-flag=excluded-module-usage \
    --nofollow-import-to=google \
    --nofollow-import-to=faiss \
    --nofollow-import-to=openai \
    --nofollow-import-to=pydantic \
    --nofollow-import-to=babel \
    --nofollow-import-to=dateparser \
    --nofollow-import-to=trafilatura \
    --nofollow-import-to=docx \
    --nofollow-import-to=pptx \
    --nofollow-import-to=pypdf \
    --nofollow-import-to=jinja2 \
    --nofollow-import-to=bs4 \
    --nofollow-import-to=urllib3 \
    --nofollow-import-to=httpx \
    --nofollow-import-to=httpcore \
    --nofollow-import-to=jsonschema \
    --nofollow-import-to=cryptography \
    --nofollow-import-to=peewee_migrate \
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

echo "[INFO] Copie des dépendances runtime, ressources et extensions C..."
# Copie de l'intégralité des modules et packages tiers runtime
uv run --no-sync python script/copy_runtime_dependencies.py dist_prod/AnkiForge.app/Contents/MacOS

# Copie des ressources
mkdir -p dist_prod/AnkiForge.app/Contents/Resources/src/ressources
mkdir -p dist_prod/AnkiForge.app/Contents/MacOS/src/ressources
cp -r src/ressources/* dist_prod/AnkiForge.app/Contents/Resources/src/ressources/
cp -r src/ressources/* dist_prod/AnkiForge.app/Contents/MacOS/src/ressources/

# Copie de l'extension C
mkdir -p dist_prod/AnkiForge.app/Contents/Resources/c_ext
mkdir -p dist_prod/AnkiForge.app/Contents/MacOS/c_ext
cp -r c_ext/* dist_prod/AnkiForge.app/Contents/Resources/c_ext/ || true
cp -r c_ext/* dist_prod/AnkiForge.app/Contents/MacOS/c_ext/ || true
cp -f c_ext/levenshtein_distance.so dist_prod/AnkiForge.app/Contents/MacOS/ || true

echo "[INFO] Signature de code Ad-Hoc du bundle macOS..."
codesign --force --deep -s - dist_prod/AnkiForge.app

echo "[SUCCESS] Compilation macOS terminee avec succes !"
echo "[INFO] Bundle produit : dist_prod/AnkiForge.app"

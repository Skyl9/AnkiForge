#!/bin/bash
# Script de compilation Nuitka optimise pour Linux (Mode Fast Standalone)
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[INFO] Nettoyage du dossier de production..."
rm -rf dist_prod/
mkdir -p dist_prod

echo "[INFO] Compilation de l'extension C native Levenshtein..."
mkdir -p c_ext
gcc -O3 -flto -shared -o c_ext/levenshtein_distance.so -fPIC c_ext/levenshtein_distance.c || true

echo "[INFO] Demarrage de la compilation avec Nuitka (Noyau AnkiForge)..."

export CFLAGS="-O2"
export CXXFLAGS="-O2"
NCPUS=$(nproc || echo 4)

uv run --no-sync python -m nuitka \
    --standalone \
    --enable-plugin=pyside6 \
    --include-package=ankiforge \
    --include-package=playhouse \
    --include-package=peewee_migrate \
    --include-package=unittest \
    --include-package=zoneinfo \
    --include-package-data=zoneinfo \
    --include-package=websockets \
    --include-package=mcp \
    --include-package=starlette \
    --include-package=uvicorn \
    --include-package=anyio \
    --include-package=sniffio \
    --include-package=urllib \
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
    --nofollow-import-to=tkinter \
    --nofollow-import-to=matplotlib \
    --linux-icon=src/ressources/icons/ankiforge.png \
    --low-memory \
    --jobs="${NCPUS}" \
    --lto=no \
    --output-dir=dist_prod \
    --output-filename=AnkiForge \
    --assume-yes-for-downloads \
    src/ankiforge

# Harmonisation du nom de dossier genere
if [ -d "dist_prod/ankiforge.dist" ] && [ ! -d "dist_prod/AnkiForge.dist" ]; then
    mv dist_prod/ankiforge.dist dist_prod/AnkiForge.dist
elif [ -d "dist_prod/__main__.dist" ] && [ ! -d "dist_prod/AnkiForge.dist" ]; then
    mv dist_prod/__main__.dist dist_prod/AnkiForge.dist
fi

if [ -f "dist_prod/AnkiForge.dist/ankiforge.bin" ]; then
    mv dist_prod/AnkiForge.dist/ankiforge.bin dist_prod/AnkiForge.dist/AnkiForge
elif [ -f "dist_prod/AnkiForge.dist/ankiforge" ]; then
    mv dist_prod/AnkiForge.dist/ankiforge dist_prod/AnkiForge.dist/AnkiForge
elif [ -f "dist_prod/AnkiForge.dist/__main__.bin" ]; then
    mv dist_prod/AnkiForge.dist/__main__.bin dist_prod/AnkiForge.dist/AnkiForge
elif [ -f "dist_prod/AnkiForge.dist/__main__" ]; then
    mv dist_prod/AnkiForge.dist/__main__ dist_prod/AnkiForge.dist/AnkiForge
elif [ -f "dist_prod/AnkiForge.dist/AnkiForge.bin" ]; then
    mv dist_prod/AnkiForge.dist/AnkiForge.bin dist_prod/AnkiForge.dist/AnkiForge
fi

chmod +x dist_prod/AnkiForge.dist/AnkiForge || true

echo "[INFO] Copie des dépendances runtime, ressources et extensions C..."
# Copie de l'intégralité des modules et packages tiers runtime
uv run --no-sync python script/copy_runtime_dependencies.py dist_prod/AnkiForge.dist

# Copie des ressources
mkdir -p dist_prod/AnkiForge.dist/src/ressources
cp -r src/ressources/* dist_prod/AnkiForge.dist/src/ressources/

# Copie des scripts de migration SQL
mkdir -p dist_prod/AnkiForge.dist/migrations
mkdir -p dist_prod/AnkiForge.dist/src/ankiforge/database/migrations
cp -r src/ankiforge/database/migrations/* dist_prod/AnkiForge.dist/migrations/
cp -r src/ankiforge/database/migrations/* dist_prod/AnkiForge.dist/src/ankiforge/database/migrations/

# Copie de l'extension C
mkdir -p dist_prod/AnkiForge.dist/c_ext
cp -r c_ext/* dist_prod/AnkiForge.dist/c_ext/ || true
cp -f c_ext/levenshtein_distance.so dist_prod/AnkiForge.dist/ || true

# Allègement des symboles de débogage C
echo "[INFO] Allègement des symboles binaires C (strip)..."
strip --strip-unneeded dist_prod/AnkiForge.dist/*.so dist_prod/AnkiForge.dist/AnkiForge 2>/dev/null || true

echo "[SUCCESS] Compilation Linux terminee avec succes !"
echo "[INFO] Dossier de distribution : dist_prod/AnkiForge.dist"

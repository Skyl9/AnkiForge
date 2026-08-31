#!/bin/bash
# Script de compilation Nuitka pour Linux à lancer depuis la racine du projet

cd "$(dirname "$0")/.." || exit

echo "Nettoyage du dossier de production..."
rm -rf dist_prod/

echo "Compilation de l'extension C native Levenshtein..."
gcc -shared -o src/ankiforge/c_ext/levenshtein_distance.so -fPIC src/ankiforge/c_ext/levenshtein_distance.c || true

echo "Démarrage de la compilation avec Nuitka..."

export CFLAGS="-O2"
export CXXFLAGS="-O2"

uv run --no-sync python -m nuitka \
    --standalone \
    --enable-plugin=pyside6 \
    --noinclude-default-mode=nofollow \
    --noinclude-pytest-mode=nofollow \
    --noinclude-IPython-mode=nofollow \
    --noinclude-setuptools-mode=nofollow \
    --noinclude-dask-mode=nofollow \
    --noinclude-numba-mode=nofollow \
    --nofollow-import-to=tkinter \
    --nofollow-import-to=matplotlib \
    --nofollow-import-to=docutils \
    --nofollow-import-to=faiss \
    --include-package-data=qtawesome \
    --include-data-dir=src/ressources=src/ressources \
    --include-data-dir=src/ankiforge/c_ext=src/ankiforge/c_ext \
    --low-memory \
    --lto=no \
    --output-dir=dist_prod \
    --output-folder-name=AnkiForge \
    --output-filename=AnkiForge \
    --assume-yes-for-downloads \
    src/ankiforge/__main__.py

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

# Copie du package faiss autonome (non compilé en C)
uv run --no-sync python -c "import faiss, shutil, pathlib; shutil.copytree(pathlib.Path(faiss.__file__).parent, 'dist_prod/AnkiForge.dist/faiss', dirs_exist_ok=True)" 2>/dev/null || true

echo "Compilation Nuitka terminée avec succès !"
echo "L'application de production se trouve dans le dossier dist_prod/AnkiForge.dist"

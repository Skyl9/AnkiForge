#!/bin/bash

cd "$(dirname "$0")/.." || exit

echo "Nettoyage du dossier de production..."
rm -rf dist_prod/

echo "Compilation de l'extension C native Levenshtein..."
clang -O3 -flto -shared -fPIC -arch arm64 -arch x86_64 -o src/ankiforge/c_ext/levenshtein_distance.so src/ankiforge/c_ext/levenshtein_distance.c || true

echo "Démarrage de la compilation avec Nuitka..."

export CFLAGS="-O2"
export CXXFLAGS="-O2"

uv run python -m nuitka \
    --standalone \
    --macos-create-app-bundle \
    --macos-app-name="AnkiForge" \
    --macos-app-version="0.2.0" \
    --enable-plugin=pyside6 \
    --enable-plugin=anti-bloat \
    --noinclude-default-mode=nofollow \
    --noinclude-pytest-mode=nofollow \
    --noinclude-unittest-mode=nofollow \
    --noinclude-IPython-mode=nofollow \
    --noinclude-setuptools-mode=nofollow \
    --noinclude-dask-mode=nofollow \
    --noinclude-numba-mode=nofollow \
    --noinclude-custom-mode=tkinter:nofollow \
    --noinclude-custom-mode=matplotlib:nofollow \
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

echo "Compilation Nuitka terminée avec succès !"
echo "L'application de production se trouve dans le dossier dist_prod/AnkiForge.app"

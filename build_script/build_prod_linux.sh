#!/bin/bash
# Script de compilation Nuitka pour Linux à lancer depuis la racine du projet

cd "$(dirname "$0")/.." || exit

echo "Nettoyage du dossier de production..."
rm -rf dist_prod/

echo "Compilation de l'extension C native Levenshtein..."
gcc -shared -o src/ankiforge/c_ext/levenshtein_distance.so -fPIC src/ankiforge/c_ext/levenshtein_distance.c || true

echo "Démarrage de la compilation avec Nuitka..."

export CFLAGS="-O2 -fno-slp-vectorize -fno-vectorize"
export CXXFLAGS="-O2 -fno-slp-vectorize -fno-vectorize"

uv run python -m nuitka \
    --standalone \
    --enable-plugin=pyside6 \
    --include-package-data=qtawesome \
    --include-data-dir=src/ressources=src/ressources \
    --include-data-dir=src/ressources=ressources \
    --include-data-dir=src/ankiforge/c_ext=src/ankiforge/c_ext \
    --include-data-dir=src/ankiforge/c_ext=ankiforge/c_ext \
    --low-memory \
    --lto=no \
    --output-dir=dist_prod \
    --output-filename=AnkiForge \
    --assume-yes-for-downloads \
    src/ankiforge/__main__.py

if [ -d "dist_prod/__main__.dist" ]; then
    rm -rf dist_prod/AnkiForge.dist
    mv dist_prod/__main__.dist dist_prod/AnkiForge.dist
fi

echo "Compilation Nuitka terminée avec succès !"
echo "L'application de production se trouve dans le dossier dist_prod/AnkiForge.dist"

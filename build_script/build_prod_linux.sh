#!/bin/bash
# Script de compilation Nuitka pour Linux à lancer depuis la racine du projet

cd "$(dirname "$0")/.." || exit

echo "Nettoyage du dossier de production..."
rm -rf dist_prod/

echo "Compilation de l'extension C native Levenshtein..."
gcc -shared -o src/ankiforge/c_ext/levenshtein_distance.so -fPIC src/ankiforge/c_ext/levenshtein_distance.c || true

echo "Démarrage de la compilation avec Nuitka..."
uv run python -m nuitka \
    --standalone \
    --enable-plugin=pyside6 \
    --include-package-data=qtawesome \
    --include-data-dir=src/ankiforge/c_ext=ankiforge/c_ext \
    --output-dir=dist_prod \
    --output-filename=AnkiForge \
    --assume-yes-for-downloads \
    src/ankiforge/__main__.py

echo "Compilation Nuitka terminée."
echo "L'application de production se trouve dans le dossier dist_prod/AnkiForge.dist"

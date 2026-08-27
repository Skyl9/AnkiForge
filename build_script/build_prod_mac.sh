#!/bin/bash

cd "$(dirname "$0")/.." || exit

echo "Nettoyage du dossier de production..."
rm -rf dist_prod/

echo "Compilation de l'extension C native Levenshtein..."
gcc -shared -o src/ankiforge/c_ext/levenshtein_distance.so -fPIC src/ankiforge/c_ext/levenshtein_distance.c || true

echo "Démarrage de la compilation avec Nuitka (Cela peut prendre 5 à 15 minutes)..."

uv run python -m nuitka \
    --standalone \
    --macos-create-app-bundle \
    --macos-app-name="AnkiForge" \
    --macos-app-version="0.2.0" \
    --enable-plugin=pyside6 \
    --include-package-data=qtawesome \
    --include-data-dir=src/ressources=src/ressources \
    --include-data-dir=src/ressources=ressources \
    --include-data-dir=src/ankiforge/c_ext=src/ankiforge/c_ext \
    --include-data-dir=src/ankiforge/c_ext=ankiforge/c_ext \
    --output-dir=dist_prod \
    --assume-yes-for-downloads \
    src/ankiforge/__main__.py

echo "Compilation Nuitka terminée."
echo "L'application de production se trouve dans le dossier dist_prod/AnkiForge.app"

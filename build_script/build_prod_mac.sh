#!/bin/bash

cd "$(dirname "$0")/.." || exit

echo "Nettoyage du dossier de production..."
rm -rf dist_prod/

echo "Démarrage de la compilation avec Nuitka (Cela peut prendre 5 à 15 minutes)..."

uv run python -m nuitka \
    --standalone \
    --macos-create-app-bundle \
    --macos-app-name="AnkiForge" \
    --macos-app-version="0.2.0" \
    --enable-plugin=pyside6 \
    --include-package-data=qtawesome \
    --include-data-file=src/ankiforge/c_ext/levenshtein_distance.so=ankiforge/c_ext/levenshtein_distance.so \
    --output-dir=dist_prod \
    --assume-yes-for-downloads \
    src/ankiforge/__main__.py

echo "Compilation Nuitka terminée."
echo "L'application de production se trouve dans le dossier dist_prod/AnkiForge.app"
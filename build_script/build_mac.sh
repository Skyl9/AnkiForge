#!/bin/bash
# Script de compilation rapide pour macOS via PyInstaller à lancer depuis la racine du projet

cd "$(dirname "$0")/.." || exit

echo "Nettoyage des dossiers de build précédents..."
rm -rf build/ dist/

echo " Génération de l'application avec PyInstaller..."
uv run pyinstaller build_script/ankiforge_obsidian.spec --noconfirm

echo "Compilation terminée."
echo "L'application exécutable se trouve dans le dossier dist/AnkiForge.app"
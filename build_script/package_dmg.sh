#!/bin/bash
# Script de création d'image disque .dmg pour macOS
set -euo pipefail

cd "$(dirname "$0")/.."

echo "📦 Préparation du dossier temporaire DMG..."
rm -rf dist_prod/dmg_temp AnkiForge-macos-arm64.dmg
mkdir -p dist_prod/dmg_temp

cp -R dist_prod/AnkiForge.app dist_prod/dmg_temp/
ln -s /Applications dist_prod/dmg_temp/Applications

echo "🚀 Création de l'image disque .dmg avec hdiutil..."
hdiutil create -volname "AnkiForge" -srcfolder dist_prod/dmg_temp -ov -format UDZO AnkiForge-macos-arm64.dmg
rm -rf dist_prod/dmg_temp

echo "🔒 Signature Ad-Hoc du fichier DMG..."
codesign --force -s - AnkiForge-macos-arm64.dmg || true

echo "✅ DMG macOS généré avec succès : AnkiForge-macos-arm64.dmg"

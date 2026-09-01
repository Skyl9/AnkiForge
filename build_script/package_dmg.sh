#!/bin/bash
# Script de creation d'image disque .dmg pour macOS
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[INFO] Preparation du dossier temporaire DMG..."
rm -rf dist_prod/dmg_temp AnkiForge-macos-arm64.dmg
mkdir -p dist_prod/dmg_temp

cp -R dist_prod/AnkiForge.app dist_prod/dmg_temp/
ln -s /Applications dist_prod/dmg_temp/Applications
xattr -cr dist_prod/dmg_temp

echo "[INFO] Creation de l'image disque .dmg avec hdiutil..."
hdiutil create -volname "AnkiForge" -srcfolder dist_prod/dmg_temp -ov -format UDZO AnkiForge-macos-arm64.dmg
rm -rf dist_prod/dmg_temp

echo "[INFO] Signature Ad-Hoc du fichier DMG..."
codesign --force -s - AnkiForge-macos-arm64.dmg || true

echo "[SUCCESS] DMG macOS genere avec succes : AnkiForge-macos-arm64.dmg"

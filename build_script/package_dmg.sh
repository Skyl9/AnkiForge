#!/bin/bash
# Script de création d'image disque .dmg personnalisée pour macOS (AnkiForge)
set -euo pipefail

cd "$(dirname "$0")/.."

APP_PATH="dist_prod/AnkiForge.app"
OUTPUT_DMG="${1:-AnkiForge-macos-arm64.dmg}"
SETTINGS_FILE="build_script/dmg_settings.py"
BG_1X="build_script/assets/dmg_background.png"
BG_2X="build_script/assets/dmg_background@2x.png"

echo "[INFO] Vérification de l'application compilée..."
if [ ! -d "$APP_PATH" ]; then
  echo "[ERREUR] L'application $APP_PATH est introuvable."
  echo "Veuillez compiler l'application au préalable avec : ./build_script/build_prod_mac.sh"
  exit 1
fi

echo "[INFO] Vérification des assets visuels du DMG..."
if [ ! -f "$BG_1X" ] || [ ! -f "$BG_2X" ]; then
  echo "[INFO] Régénération des assets d'arrière-plan Retina..."
  uv run python build_script/generate_dmg_background.py
fi

echo "[INFO] Nettoyage des anciens artefacts DMG..."
rm -f "$OUTPUT_DMG" "dist_prod/$OUTPUT_DMG"
xattr -cr "$APP_PATH"

echo "[INFO] Construction de l'image disque stylisée avec dmgbuild..."
uv run dmgbuild \
  -s "$SETTINGS_FILE" \
  -D app_path="$(pwd)/$APP_PATH" \
  "AnkiForge" \
  "$OUTPUT_DMG"

echo "[INFO] Signature Ad-Hoc du fichier DMG..."
codesign --force -s - "$OUTPUT_DMG" || true

# Copie miroir dans dist_prod pour compatibilité avec tous les workflows CI
cp "$OUTPUT_DMG" "dist_prod/$OUTPUT_DMG"

DMG_SIZE=$(du -h "$OUTPUT_DMG" | cut -f1)
echo "[SUCCESS] Image disque macOS générée avec succès : $OUTPUT_DMG ($DMG_SIZE)"

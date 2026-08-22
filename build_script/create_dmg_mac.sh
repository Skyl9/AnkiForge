#!/bin/bash
# Script de génération du fichier .dmg pour ankiforge_obsidian

# 1. On se place à la racine du projet
cd "$(dirname "$0")/.." || exit

APP_NAME="__main__"
APP_PATH="dist_prod/${APP_NAME}.app"
DMG_NAME="dist_prod/${APP_NAME}_Installer.dmg"

# 2. Vérification de l'existence de l'application compilée
if [ ! -d "$APP_PATH" ]; then
  echo "Erreur : L'application $APP_PATH est introuvable."
  echo "Veuillez d'abord compiler l'application avec le script Nuitka."
  exit 1
fi

# 3. Nettoyage de l'ancien fichier DMG s'il existe
rm -f "$DMG_NAME"

echo "Création de l'image disque .dmg..."

# 4. Exécution de create-dmg avec les paramètres visuels
create-dmg \
  --volname "${APP_NAME} Installer" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --icon "${APP_NAME}.app" 150 190 \
  --hide-extension "${APP_NAME}.app" \
  --app-drop-link 450 190 \
  "$DMG_NAME" \
  "$APP_PATH"

echo "Terminé."
echo "Le fichier d'installation se trouve ici : $DMG_NAME"

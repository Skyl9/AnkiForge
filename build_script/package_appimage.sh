#!/bin/bash
# Script d'empaquetage AppImage pour Linux
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[INFO] Preparation du dossier AppDir..."
rm -rf dist_prod/AppDir
mkdir -p dist_prod/AppDir/usr/bin
mkdir -p dist_prod/AppDir/usr/share/icons/hicolor/scalable/apps

# Copie des fichiers de distribution Nuitka
cp -r dist_prod/AnkiForge.dist/* dist_prod/AppDir/usr/bin/

# Copie de l'icône de l'application
cp src/ressources/icons/logo.svg dist_prod/AppDir/ankiforge.svg
cp src/ressources/icons/logo.svg dist_prod/AppDir/usr/share/icons/hicolor/scalable/apps/ankiforge.svg

# Création du fichier .desktop
cat << 'DESKTOP_EOF' > dist_prod/AppDir/ankiforge.desktop
[Desktop Entry]
Type=Application
Name=AnkiForge
Exec=AnkiForge %F
Icon=ankiforge
Comment=Generateur de cartes Anki assiste par IA
Categories=Education;Utility;Qt;
Terminal=false
StartupWMClass=AnkiForge
DESKTOP_EOF

# Création du script AppRun
cat << 'APPRUN_EOF' > dist_prod/AppDir/AppRun
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/bin:${LD_LIBRARY_PATH:-}"
exec "${HERE}/usr/bin/AnkiForge" "$@"
APPRUN_EOF

chmod +x dist_prod/AppDir/AppRun
chmod +x dist_prod/AppDir/usr/bin/AnkiForge

echo "[INFO] Telechargement d'appimagetool..."
if [ ! -f "dist_prod/appimagetool" ]; then
    curl -fsSL -o dist_prod/appimagetool https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x dist_prod/appimagetool
fi

echo "[INFO] Generation de l'AppImage..."
ARCH=x86_64 ./dist_prod/appimagetool --appimage-extract-and-run dist_prod/AppDir AnkiForge-x86_64.AppImage

echo "[SUCCESS] AppImage generee avec succes : AnkiForge-x86_64.AppImage"

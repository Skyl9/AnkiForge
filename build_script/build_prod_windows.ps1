# Script PowerShell de compilation Nuitka pour Windows
# À lancer depuis la racine du projet

$ErrorActionPreference = "Stop"

Write-Host "Nettoyage du dossier de production..."
if (Test-Path "dist_prod") {
    Remove-Item -Recurse -Force "dist_prod"
}

Write-Host "Compilation de l'extension C native Levenshtein..."
gcc -shared -o src/ankiforge/c_ext/levenshtein_distance.dll src/ankiforge/c_ext/levenshtein_distance.c

Write-Host "Démarrage de la compilation avec Nuitka..."
uv run python -m nuitka `
    --standalone `
    --windows-console-mode=disable `
    --enable-plugin=pyside6 `
    --include-package-data=qtawesome `
    --include-data-dir=src/ressources=src/ressources `
    --include-data-dir=src/ressources=ressources `
    --include-data-dir=src/ankiforge/c_ext=src/ankiforge/c_ext `
    --include-data-dir=src/ankiforge/c_ext=ankiforge/c_ext `
    --output-dir=dist_prod `
    --output-filename=AnkiForge.exe `
    --assume-yes-for-downloads `
    src/ankiforge/__main__.py

Write-Host "Compilation Nuitka terminée."
Write-Host "L'application de production se trouve dans le dossier dist_prod/AnkiForge.dist"

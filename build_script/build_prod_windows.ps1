# Script PowerShell de compilation Nuitka pour Windows
# À lancer depuis la racine du projet

$ErrorActionPreference = "Stop"

Write-Host "Nettoyage du dossier de production..."
if (Test-Path "dist_prod") {
    Remove-Item -Recurse -Force "dist_prod"
}

Write-Host "Compilation de l'extension C native Levenshtein..."
try {
    gcc -shared -o src/ankiforge/c_ext/levenshtein_distance.dll src/ankiforge/c_ext/levenshtein_distance.c
} catch {
    Write-Host "Extension C Levenshtein non compilée sous Windows (repli automatique sur le module difflib Python)."
}

Write-Host "Démarrage de la compilation avec Nuitka..."
$env:_CL_ = "/bigobj"
uv run python -m nuitka `
    --standalone `
    --windows-console-mode=disable `
    --enable-plugin=pyside6 `
    --noinclude-default-mode=nofollow `
    --noinclude-pytest-mode=nofollow `
    --noinclude-unittest-mode=nofollow `
    --noinclude-IPython-mode=nofollow `
    --noinclude-setuptools-mode=nofollow `
    --noinclude-dask-mode=nofollow `
    --noinclude-numba-mode=nofollow `
    --nofollow-import-to=tkinter `
    --nofollow-import-to=matplotlib `
    --nofollow-import-to=docutils `
    --include-package-data=qtawesome `
    --include-data-dir=src/ressources=src/ressources `
    --include-data-dir=src/ankiforge/c_ext=src/ankiforge/c_ext `
    --low-memory `
    --jobs=2 `
    --msvc=latest `
    --lto=no `
    --output-dir=dist_prod `
    --output-folder-name=AnkiForge `
    --output-filename=AnkiForge.exe `
    --assume-yes-for-downloads `
    src/ankiforge/__main__.py

if (Test-Path "dist_prod/__main__.dist") {
    if (Test-Path "dist_prod/AnkiForge.dist") { Remove-Item -Recurse -Force "dist_prod/AnkiForge.dist" }
    Rename-Item -Path "dist_prod/__main__.dist" -NewName "AnkiForge.dist"
}

if (Test-Path "dist_prod/AnkiForge.dist/__main__.exe") {
    if (Test-Path "dist_prod/AnkiForge.dist/AnkiForge.exe") { Remove-Item -Force "dist_prod/AnkiForge.dist/AnkiForge.exe" }
    Rename-Item -Path "dist_prod/AnkiForge.dist/__main__.exe" -NewName "AnkiForge.exe"
}

Write-Host "Compilation Nuitka terminée avec succès !"
Write-Host "L'application de production se trouve dans le dossier dist_prod/AnkiForge.dist"

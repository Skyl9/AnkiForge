# Script PowerShell de compilation Nuitka pour Windows
# À lancer depuis la racine du projet

$ErrorActionPreference = "Stop"

Write-Host "🧹 Nettoyage du dossier de production..."
if (Test-Path "dist_prod") {
    Remove-Item -Recurse -Force "dist_prod"
}
New-Item -ItemType Directory -Force -Path "dist_prod" | Out-Null

Write-Host "⚙️ Compilation de l'extension C native Levenshtein..."
try {
    gcc -O3 -flto -shared -o src/ankiforge/c_ext/levenshtein_distance.dll src/ankiforge/c_ext/levenshtein_distance.c
} catch {
    Write-Host "ℹ️ Extension C Levenshtein non compilée sous Windows (repli automatique sur difflib Python)."
}

Write-Host "🚀 Démarrage de la compilation avec Nuitka..."
$env:_CL_ = "/bigobj"

uv run --no-sync python -m nuitka `
    --standalone `
    --windows-console-mode=disable `
    --enable-plugin=pyside6 `
    --include-package=ankiforge `
    --nofollow-import-to=google `
    --nofollow-import-to=faiss `
    --nofollow-import-to=tkinter `
    --nofollow-import-to=matplotlib `
    --nofollow-import-to=docutils `
    --include-package-data=qtawesome `
    --include-data-dir=src/ankiforge/c_ext=src/ankiforge/c_ext `
    --low-memory `
    --jobs=2 `
    --msvc=latest `
    --lto=no `
    --output-dir=dist_prod `
    --output-filename=AnkiForge.exe `
    --assume-yes-for-downloads `
    src/ankiforge/__main__.py

if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ Échec critique de la compilation Nuitka (Code de sortie: $LASTEXITCODE)"
    exit $LASTEXITCODE
}

# Harmonisation des noms de dossiers et fichiers
if (Test-Path "dist_prod/__main__.dist") {
    if (Test-Path "dist_prod/AnkiForge.dist") { Remove-Item -Recurse -Force "dist_prod/AnkiForge.dist" }
    Rename-Item -Path "dist_prod/__main__.dist" -NewName "AnkiForge.dist"
}

if (Test-Path "dist_prod/AnkiForge.dist/__main__.exe") {
    if (Test-Path "dist_prod/AnkiForge.dist/AnkiForge.exe") { Remove-Item -Force "dist_prod/AnkiForge.dist/AnkiForge.exe" }
    Rename-Item -Path "dist_prod/AnkiForge.dist/__main__.exe" -NewName "AnkiForge.exe"
}

Write-Host "📦 Copie des dépendances non compilées en C et des ressources..."
# Copie des ressources
New-Item -ItemType Directory -Force -Path "dist_prod\AnkiForge.dist\src" | Out-Null
Copy-Item -Path "src\ressources" -Destination "dist_prod\AnkiForge.dist\src\ressources" -Recurse -Force

# Copie des packages purs / dynamiques
try {
    uv run --no-sync python -c "import google, shutil, pathlib; shutil.copytree(pathlib.Path(google.__file__).parent, 'dist_prod/AnkiForge.dist/google', dirs_exist_ok=True)"
} catch {
    Write-Host "Avertissement : google non copié dans AnkiForge.dist."
}

try {
    uv run --no-sync python -c "import faiss, shutil, pathlib; shutil.copytree(pathlib.Path(faiss.__file__).parent, 'dist_prod/AnkiForge.dist/faiss', dirs_exist_ok=True)"
} catch {
    Write-Host "Avertissement : faiss non copié dans AnkiForge.dist."
}

Write-Host "✅ Compilation Windows terminée avec succès !"
Write-Host "📁 Dossier de distribution : dist_prod/AnkiForge.dist"

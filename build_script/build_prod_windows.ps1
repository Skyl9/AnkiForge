# Script PowerShell de compilation Nuitka pour Windows (Mode Fast Standalone)
# A lancer depuis la racine du projet

$ErrorActionPreference = "Stop"

Write-Host "[INFO] Nettoyage du dossier de production..."
if (Test-Path "dist_prod") {
    Remove-Item -Recurse -Force "dist_prod"
}
New-Item -ItemType Directory -Force -Path "dist_prod" | Out-Null

# Desactivation du scan temps reel Windows Defender sur le dossier de build
try {
    Add-MpPreference -ExclusionPath (Get-Location).Path, $env:TEMP, $env:LOCALAPPDATA -ErrorAction SilentlyContinue
} catch {}

Write-Host "[INFO] Compilation de l'extension C native Levenshtein..."
New-Item -ItemType Directory -Force -Path "c_ext" | Out-Null
try {
    gcc -O3 -flto -shared -o c_ext/levenshtein_distance.dll c_ext/levenshtein_distance.c
} catch {
    Write-Host "[WARNING] Extension C Levenshtein non compilee sous Windows (repli automatique sur difflib Python)."
}

Write-Host "[INFO] Demarrage de la compilation avec Nuitka (Noyau AnkiForge)..."
$env:_CL_ = "/bigobj"

uv run --no-sync python -m nuitka `
    --standalone `
    --windows-console-mode=disable `
    --enable-plugin=pyside6 `
    --include-package=ankiforge `
    --include-package=playhouse `
    --include-package=peewee_migrate `
    --include-package=unittest `
    --include-package=zoneinfo `
    --include-package-data=zoneinfo `
    --no-deployment-flag=excluded-module-usage `
    --nofollow-import-to=google `
    --nofollow-import-to=faiss `
    --nofollow-import-to=openai `
    --nofollow-import-to=pydantic `
    --nofollow-import-to=babel `
    --nofollow-import-to=dateparser `
    --nofollow-import-to=trafilatura `
    --nofollow-import-to=docx `
    --nofollow-import-to=pptx `
    --nofollow-import-to=pypdf `
    --nofollow-import-to=jinja2 `
    --nofollow-import-to=bs4 `
    --nofollow-import-to=urllib3 `
    --nofollow-import-to=httpx `
    --nofollow-import-to=httpcore `
    --nofollow-import-to=jsonschema `
    --nofollow-import-to=cryptography `
    --nofollow-import-to=tkinter `
    --nofollow-import-to=matplotlib `
    --nofollow-import-to=docutils `
    --include-package-data=qtawesome `
    --low-memory `
    --jobs=4 `
    --msvc=latest `
    --lto=no `
    --output-dir=dist_prod `
    --output-filename=AnkiForge.exe `
    --assume-yes-for-downloads `
    src/ankiforge

if ($LASTEXITCODE -ne 0) {
    Write-Error "[ERROR] Echec critique de la compilation Nuitka (Code de sortie: $LASTEXITCODE)"
    exit $LASTEXITCODE
}

# Harmonisation des noms de dossiers et fichiers (Renommage securise pour NTFS)
if (Test-Path "dist_prod\ankiforge.dist") {
    Rename-Item -Path "dist_prod\ankiforge.dist" -NewName "ankiforge_temp.dist" -Force
    Rename-Item -Path "dist_prod\ankiforge_temp.dist" -NewName "AnkiForge.dist" -Force
} elseif (Test-Path "dist_prod\__main__.dist") {
    Rename-Item -Path "dist_prod\__main__.dist" -NewName "ankiforge_temp.dist" -Force
    Rename-Item -Path "dist_prod\ankiforge_temp.dist" -NewName "AnkiForge.dist" -Force
}

if (Test-Path "dist_prod\AnkiForge.dist\ankiforge.exe") {
    Rename-Item -Path "dist_prod\AnkiForge.dist\ankiforge.exe" -NewName "AnkiForge.exe" -Force
} elseif (Test-Path "dist_prod\AnkiForge.dist\__main__.exe") {
    Rename-Item -Path "dist_prod\AnkiForge.dist\__main__.exe" -NewName "AnkiForge.exe" -Force
}

Write-Host "[INFO] Copie des dépendances runtime, ressources et extensions C..."
# Copie de l'intégralité des modules et packages tiers runtime
uv run --no-sync python script\copy_runtime_dependencies.py dist_prod\AnkiForge.dist

# Copie des ressources
New-Item -ItemType Directory -Force -Path "dist_prod\AnkiForge.dist\src\ressources" | Out-Null
Copy-Item -Path "src\ressources\*" -Destination "dist_prod\AnkiForge.dist\src\ressources" -Recurse -Force

# Copie de l'extension C
New-Item -ItemType Directory -Force -Path "dist_prod\AnkiForge.dist\c_ext" | Out-Null
Copy-Item -Path "c_ext\*" -Destination "dist_prod\AnkiForge.dist\c_ext" -Recurse -Force
if (Test-Path "c_ext\levenshtein_distance.dll") {
    Copy-Item -Path "c_ext\levenshtein_distance.dll" -Destination "dist_prod\AnkiForge.dist\levenshtein_distance.dll" -Force
}

Write-Host "[SUCCESS] Compilation Windows terminee avec succes !"
Write-Host "[INFO] Dossier de distribution : dist_prod/AnkiForge.dist"

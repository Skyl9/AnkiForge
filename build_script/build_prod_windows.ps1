# Script PowerShell de compilation Nuitka pour Windows (Pilote Universel)
# A lancer depuis la racine du projet
param (
    [string]$Version = "",
    [string]$Channel = "stable"
)

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

Write-Host "[INFO] Execution du pilote de compilation universel..."
$env:_CL_ = "/bigobj"
$buildArgs = @("--target-os=windows")
if ($Version) {
    $buildArgs += @("--version", $Version)
} elseif ($env:BUILD_VERSION) {
    $buildArgs += @("--version", $env:BUILD_VERSION)
}
if ($Channel) {
    $buildArgs += @("--channel", $Channel)
}
$buildArgs += $args
uv run python script/build_standalone.py @buildArgs

# Creation de l'installeur Windows si Inno Setup est installe
if (Test-Path "C:\Program Files (x86)\Inno Setup 6\ISCC.exe") {
    Write-Host "[INFO] Creation de l'installeur Inno Setup..."
    & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build_script/windows_installer.iss
}

Write-Host "[SUCCESS] Compilation Windows terminee avec succes !"
Write-Host "[INFO] Dossier de distribution : dist_prod/AnkiForge.dist"

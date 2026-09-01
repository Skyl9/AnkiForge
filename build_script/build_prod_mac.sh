#!/bin/bash
# Script de compilation Nuitka optimise pour macOS (Pilote Universel)
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[INFO] Nettoyage du dossier de production..."
rm -rf dist_prod/
mkdir -p dist_prod

echo "[INFO] Compilation de l'extension C native Levenshtein (Universal 2)..."
mkdir -p c_ext
clang -O3 -flto -shared -fPIC -arch arm64 -arch x86_64 -o c_ext/levenshtein_distance.so c_ext/levenshtein_distance.c 2>/dev/null || true

echo "[INFO] Execution du pilote de compilation universel..."
uv run python script/build_standalone.py --target-os=darwin

echo "[SUCCESS] Compilation macOS terminee avec succes !"
echo "[INFO] Bundle produit : dist_prod/AnkiForge.app"

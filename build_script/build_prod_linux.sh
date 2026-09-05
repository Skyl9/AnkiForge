#!/bin/bash
# Script de compilation Nuitka optimise pour Linux (Pilote Universel)
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[INFO] Nettoyage du dossier de production..."
rm -rf dist_prod/
mkdir -p dist_prod

echo "[INFO] Compilation de l'extension C native Levenshtein..."
mkdir -p c_ext
gcc -O3 -flto -shared -o c_ext/levenshtein_distance.so -fPIC c_ext/levenshtein_distance.c 2>/dev/null || true

echo "[INFO] Execution du pilote de compilation universel..."
BUILD_ARGS=(--target-os=linux)
if [[ -n "${BUILD_VERSION:-}" && "$*" != *"--version"* ]]; then
  BUILD_ARGS+=(--version "$BUILD_VERSION")
fi
uv run python script/build_standalone.py "${BUILD_ARGS[@]}" "$@"

echo "[SUCCESS] Compilation Linux terminee avec succes !"
echo "[INFO] Dossier de distribution : dist_prod/AnkiForge.dist"

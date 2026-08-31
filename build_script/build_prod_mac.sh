#!/bin/bash
# Script de compilation Nuitka optimise pour macOS (Mode Fast Standalone)
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[INFO] Nettoyage du dossier de production..."
rm -rf dist_prod/
mkdir -p dist_prod

echo "[INFO] Compilation de l'extension C native Levenshtein (Universal 2)..."
mkdir -p c_ext
clang -O3 -flto -shared -fPIC -arch arm64 -arch x86_64 -o c_ext/levenshtein_distance.so c_ext/levenshtein_distance.c || true

echo "[INFO] Demarrage de la compilation avec Nuitka (Noyau AnkiForge)..."

export CFLAGS="-O2"
export CXXFLAGS="-O2"
NCPUS=$(sysctl -n hw.logicalcpu || echo 4)

uv run --no-sync python -m nuitka \
    --standalone \
    --macos-create-app-bundle \
    --macos-app-name="AnkiForge" \
    --macos-app-version="0.2.0" \
    --macos-app-icon=none \
    --enable-plugin=pyside6 \
    --include-package=ankiforge \
    --include-package=playhouse \
    --include-package=peewee_migrate \
    --include-package=unittest \
    --include-package=zoneinfo \
    --include-package-data=zoneinfo \
    --include-package=websockets \
    --include-package=mcp \
    --include-package=starlette \
    --include-package=uvicorn \
    --include-package=anyio \
    --include-package=sniffio \
    --no-deployment-flag=excluded-module-usage \
    --nofollow-import-to=google \
    --nofollow-import-to=faiss \
    --nofollow-import-to=openai \
    --nofollow-import-to=pydantic \
    --nofollow-import-to=babel \
    --nofollow-import-to=dateparser \
    --nofollow-import-to=trafilatura \
    --nofollow-import-to=docx \
    --nofollow-import-to=pptx \
    --nofollow-import-to=pypdf \
    --nofollow-import-to=jinja2 \
    --nofollow-import-to=bs4 \
    --nofollow-import-to=urllib3 \
    --nofollow-import-to=httpx \
    --nofollow-import-to=httpcore \
    --nofollow-import-to=jsonschema \
    --nofollow-import-to=cryptography \
    --nofollow-import-to=tkinter \
    --nofollow-import-to=matplotlib \
    --nofollow-import-to=docutils \
    --include-package-data=qtawesome \
    --low-memory \
    --jobs="${NCPUS}" \
    --lto=no \
    --output-dir=dist_prod \
    --output-filename=AnkiForge \
    --assume-yes-for-downloads \
    src/ankiforge

# Harmonisation du bundle .app
if [ -d "dist_prod/ankiforge.app" ] && [ ! -d "dist_prod/AnkiForge.app" ]; then
    mv dist_prod/ankiforge.app dist_prod/AnkiForge.app
elif [ -d "dist_prod/__main__.app" ] && [ ! -d "dist_prod/AnkiForge.app" ]; then
    mv dist_prod/__main__.app dist_prod/AnkiForge.app
fi

if [ -f "dist_prod/AnkiForge.app/Contents/MacOS/ankiforge.bin" ]; then
    mv dist_prod/AnkiForge.app/Contents/MacOS/ankiforge.bin dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge
elif [ -f "dist_prod/AnkiForge.app/Contents/MacOS/ankiforge" ]; then
    mv dist_prod/AnkiForge.app/Contents/MacOS/ankiforge dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge
elif [ -f "dist_prod/AnkiForge.app/Contents/MacOS/__main__.bin" ]; then
    mv dist_prod/AnkiForge.app/Contents/MacOS/__main__.bin dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge
elif [ -f "dist_prod/AnkiForge.app/Contents/MacOS/__main__" ]; then
    mv dist_prod/AnkiForge.app/Contents/MacOS/__main__ dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge
elif [ -f "dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge.bin" ]; then
    mv dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge.bin dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge
fi

chmod +x dist_prod/AnkiForge.app/Contents/MacOS/AnkiForge || true

echo "[INFO] Copie des dépendances runtime, ressources et extensions C..."
# Copie de l'intégralité des modules et packages tiers runtime
uv run --no-sync python script/copy_runtime_dependencies.py dist_prod/AnkiForge.app/Contents/MacOS

# Harmonisation Mach-O des dylibs pour Apple codesign (faiss, PIL, etc.)
echo "[INFO] Harmonisation Mach-O des dylibs pour Apple codesign..."
python3 - <<'EOF'
import pathlib
import shutil
import subprocess

macos_dir = pathlib.Path("dist_prod/AnkiForge.app/Contents/MacOS")
if macos_dir.exists():
    # 1. Renommer .dylibs -> dylibs
    for dot_dir in list(macos_dir.rglob(".dylibs")):
        target_dir = dot_dir.parent / "dylibs"
        target_dir.mkdir(parents=True, exist_ok=True)
        for f in dot_dir.iterdir():
            shutil.copy2(f, target_dir / f.name)
            shutil.copy2(f, dot_dir.parent / f.name)
        shutil.rmtree(dot_dir)

    # 2. Patcher les chemins Mach-O dans tous les .so et .dylib
    for bin_file in macos_dir.rglob("*"):
        if bin_file.is_file() and bin_file.suffix in (".so", ".dylib"):
            res = subprocess.run(["otool", "-L", str(bin_file)], capture_output=True, text=True)
            for line in res.stdout.splitlines():
                line = line.strip()
                if "@loader_path/.dylibs/" in line:
                    old_path = line.split()[0]
                    new_path = old_path.replace("@loader_path/.dylibs/", "@loader_path/dylibs/")
                    subprocess.run(["install_name_tool", "-change", old_path, new_path, str(bin_file)], check=False)
            subprocess.run(["codesign", "--force", "-s", "-", str(bin_file)], check=False)
EOF

# Copie des ressources
mkdir -p dist_prod/AnkiForge.app/Contents/Resources/src/ressources
mkdir -p dist_prod/AnkiForge.app/Contents/MacOS/src/ressources
cp -r src/ressources/* dist_prod/AnkiForge.app/Contents/Resources/src/ressources/
cp -r src/ressources/* dist_prod/AnkiForge.app/Contents/MacOS/src/ressources/

# Copie de l'extension C
mkdir -p dist_prod/AnkiForge.app/Contents/Resources/c_ext
mkdir -p dist_prod/AnkiForge.app/Contents/MacOS/c_ext
cp -r c_ext/* dist_prod/AnkiForge.app/Contents/Resources/c_ext/ || true
cp -r c_ext/* dist_prod/AnkiForge.app/Contents/MacOS/c_ext/ || true
cp -f c_ext/levenshtein_distance.so dist_prod/AnkiForge.app/Contents/MacOS/ || true

echo "[INFO] Signature de code Ad-Hoc du bundle macOS..."
find dist_prod/AnkiForge.app -type f \( -name "*.dylib" -o -name "*.so" \) -exec codesign --force -s - {} + 2>/dev/null || true
codesign --force --deep -s - dist_prod/AnkiForge.app

echo "[SUCCESS] Compilation macOS terminee avec succes !"
echo "[INFO] Bundle produit : dist_prod/AnkiForge.app"

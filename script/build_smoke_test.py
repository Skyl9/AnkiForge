#!/usr/bin/env python3
"""Script de Smoke Test de Compilation Binaire pour AnkiForge.

Construit un bundle exécutable avec PyInstaller et vérifie son bon
démarrage en environnement headless (validation des bindings Qt, C et
assets).
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"🚀 Exécution : {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Erreur ({result.returncode}) :\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
        sys.exit(result.returncode)
    print(f"✅ Succès ({result.stdout.strip()[:100]}...)")


def main() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    dist_dir = root_dir / "dist"

    print("=" * 60)

    print("🛠️  AnkiForge Binary Build & Smoke Test")
    print("=" * 60)

    # 1. Compilation de l'extension C si manquante
    c_source = root_dir / "c_ext" / "levenshtein_distance.c"
    c_so = root_dir / "c_ext" / "levenshtein_distance.so"
    if c_source.exists() and not c_so.exists() and sys.platform != "win32":
        print("⚙️ Compilation de l'extension C Levenshtein...")
        subprocess.run(["gcc", "-shared", "-o", str(c_so), "-fPIC", str(c_source)], check=False)

    # 2. Construction PyInstaller onedir rapide
    entrypoint = root_dir / "src" / "ankiforge" / "__main__.py"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=ankiforge",
        "--onedir",
        "--noconfirm",
        "--clean",
        f"--paths={root_dir / 'src'}",
        "--hidden-import=ankiforge",
        "--hidden-import=peewee",
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui",
        "--hidden-import=PySide6.QtWidgets",
        "--hidden-import=PySide6.QtMultimedia",
        "--hidden-import=zstandard",
        str(entrypoint),
    ]

    run_command(cmd, cwd=root_dir)

    # 3. Localisation du binaire produit
    if sys.platform == "win32":
        executable = dist_dir / "ankiforge" / "ankiforge.exe"
    elif sys.platform == "darwin":
        # macOS onedir produit dist/ankiforge/ankiforge ou dist/ankiforge.app/Contents/MacOS/ankiforge
        executable = dist_dir / "ankiforge" / "ankiforge"
        if not executable.exists():
            executable = dist_dir / "ankiforge.app" / "Contents" / "MacOS" / "ankiforge"
    else:
        executable = dist_dir / "ankiforge" / "ankiforge"

    if not executable.exists():
        print(f"❌ Exécutable introuvable à l'emplacement : {executable}")
        sys.exit(1)

    print(f"📦 Binaire produit avec succès : {executable} ({executable.stat().st_size / (1024 * 1024):.2f} Mo)")

    # 4. Smoke Test Headless
    print("🧪 Exécution du Smoke Test sur le binaire packagé...")
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

    smoke_res = subprocess.run([str(executable), "--smoke-test"], capture_output=True, text=True, env=env)

    if smoke_res.returncode != 0:
        print(f"❌ Échec du Smoke Test !\nSTDOUT:\n{smoke_res.stdout}\nSTDERR:\n{smoke_res.stderr}")
        sys.exit(smoke_res.returncode)

    print(f"🎉 Smoke Test validé avec succès ! Sortie : {smoke_res.stdout.strip()}")
    print("=" * 60)


if __name__ == "__main__":
    main()

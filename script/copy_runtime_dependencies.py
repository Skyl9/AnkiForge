#!/usr/bin/env python3
"""Script utilitaire pour copier les packages tiers purs/dynamiques dans le bundle de distribution."""

import pathlib
import shutil
import sys


def copy_runtime_deps(target_dist: pathlib.Path) -> None:
    # 1. Localisation de site-packages dans le venv actif
    if sys.platform == "win32":
        site_packages = pathlib.Path(sys.prefix) / "Lib" / "site-packages"
    else:
        site_packages = pathlib.Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"

    if not site_packages.exists():
        print(f"[WARNING] site-packages introuvable à {site_packages}")
        return

    # Modules et fichiers à ne PAS copier (déjà gérés par le plugin PySide6 de Nuitka ou internes au build)
    skip_names = {
        "PySide6",
        "shiboken6",
        "shiboken6_generator",
        "nuitka",
        "ankiforge",
        "peewee",
        "playhouse",
        "peewee_migrate",
        "unittest",
        "zoneinfo",
        "_zoneinfo",
        "websockets",
        "mcp",
        "starlette",
        "uvicorn",
        "anyio",
        "sniffio",
        "__pycache__",
        "pip",
        "setuptools",
        "wheel",
        "_distutils_hack",
        "pytest",
        "_pytest",
        "pytest_qt",
        "pytest_cov",
        "coverage",
        "mypy",
        "ruff",
    }

    target_dist.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Copie des dépendances runtime depuis {site_packages} vers {target_dist}...")
    copied_count = 0

    for item in site_packages.iterdir():
        if item.name.startswith(".") or item.name in skip_names or item.suffix in (".egg-info", ".pth"):
            continue
        # Exclure uniquement les .dist-info des outils de dev/tests
        if item.suffix == ".dist-info" and any(item.name.lower().startswith(p) for p in ("pytest", "mypy", "ruff", "coverage", "pip", "setuptools", "wheel")):
            continue

        dest = target_dist / item.name
        try:
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            elif item.is_file():
                shutil.copy2(item, dest)
            copied_count += 1
        except Exception as err:
            print(f"[WARNING] Erreur lors de la copie de {item.name}: {err}")

    print(f"[SUCCESS] {copied_count} packages/modules tiers copiés avec succès dans {target_dist}.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: copy_runtime_dependencies.py <target_dist_dir>")
        sys.exit(1)
    copy_runtime_deps(pathlib.Path(sys.argv[1]).resolve())

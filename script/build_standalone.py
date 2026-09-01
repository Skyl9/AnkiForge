"""Pilote de compilation universel AnkiForge avec Nuitka (Single Source of Truth).

Lit la configuration centralisée depuis build_script/nuitka_config.json,
calibre dynamiquement les cœurs CPU et orchestre les étapes de packaging.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from copy_runtime_dependencies import copy_runtime_deps

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AnkiForgeBuilder")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "build_script" / "nuitka_config.json"


def load_config() -> dict[str, Any]:
    """Charge la configuration centralisée Nuitka."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Fichier de configuration Nuitka introuvable : {CONFIG_PATH}")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def build_nuitka_command(config: dict[str, Any], target_os: str, jobs: int) -> list[str]:
    """Construit la liste des arguments de la commande Nuitka à partir de la configuration."""
    common = config.get("common", {})
    platforms = config.get("platforms", {})
    plat_cfg = platforms.get(target_os, {})

    cmd: list[str] = [sys.executable, "-m", "nuitka"]

    # 1. Flags standards
    for flag in common.get("standard_flags", []):
        cmd.append(flag)

    # 2. Plugins
    for plugin in common.get("plugins", []):
        cmd.append(f"--enable-plugin={plugin}")

    # 3. Packages inclus
    for pkg in common.get("include_packages", []):
        cmd.append(f"--include-package={pkg}")

    # 4. Données de package incluses
    for pkg_data in common.get("include_package_data", []):
        cmd.append(f"--include-package-data={pkg_data}")

    # 5. Drapeaux no-deployment
    for nd in common.get("no_deployment_flags", []):
        cmd.append(f"--no-deployment-flag={nd}")

    # 6. Exclusions (--nofollow-import-to)
    for nofollow in common.get("nofollow_imports", []):
        cmd.append(f"--nofollow-import-to={nofollow}")

    # 7. Flags spécifiques à la plateforme
    if target_os == "darwin":
        app_name = plat_cfg.get("app_name", "AnkiForge")
        cmd.append(f"--macos-app-name={app_name}")
        icon = plat_cfg.get("icon")
        if icon and (PROJECT_ROOT / icon).exists():
            cmd.append(f"--macos-app-icon={icon}")
    elif target_os == "windows":
        icon = plat_cfg.get("icon")
        if icon and (PROJECT_ROOT / icon).exists():
            cmd.append(f"--windows-icon-from-ico={icon}")
    elif target_os == "linux":
        icon = plat_cfg.get("icon")
        if icon and (PROJECT_ROOT / icon).exists():
            cmd.append(f"--linux-icon={icon}")

    for extra in plat_cfg.get("extra_flags", []):
        cmd.append(extra)

    out_dir = plat_cfg.get("output_dir", "dist_prod")
    out_file = plat_cfg.get("output_filename", "AnkiForge")
    cmd.append(f"--output-dir={out_dir}")
    cmd.append(f"--output-filename={out_file}")

    # 8. Allocation CPU multi-cœurs
    cmd.append(f"--jobs={jobs}")

    # 9. Point d'entrée de l'application
    cmd.append("src/ankiforge")

    return cmd


def copy_migrations_to_bundle(dist_dir: Path, target_os: str) -> None:
    """Copie les scripts de migration SQL SQLite dans les emplacements attendus par l'application."""
    migrations_src = PROJECT_ROOT / "src" / "ankiforge" / "database" / "migrations"
    if not migrations_src.exists():
        logger.warning("Dossier de migrations source introuvable : %s", migrations_src)
        return

    logger.info("Copie des scripts de migration SQL SQLite...")
    if target_os == "darwin":
        # Sur macOS, les ressources doivent être dans Contents/Resources
        res_dir = dist_dir / "Contents" / "Resources"
        target_migrations = res_dir / "migrations"
        target_migrations_py = res_dir / "src" / "ankiforge" / "database" / "migrations"
        shutil.copytree(migrations_src, target_migrations, dirs_exist_ok=True)
        shutil.copytree(migrations_src, target_migrations_py, dirs_exist_ok=True)
    else:
        target_migrations = dist_dir / "migrations"
        target_migrations_py = dist_dir / "src" / "ankiforge" / "database" / "migrations"
        shutil.copytree(migrations_src, target_migrations, dirs_exist_ok=True)
        shutil.copytree(migrations_src, target_migrations_py, dirs_exist_ok=True)


def copy_app_resources_to_bundle(dist_dir: Path, target_os: str) -> None:
    """Copie l'intégralité des ressources graphiques, icônes Phosphor, traductions et templates (src/ressources)."""
    ressources_src = PROJECT_ROOT / "src" / "ressources"
    if not ressources_src.exists():
        logger.warning("Dossier de ressources source introuvable : %s", ressources_src)
        return

    logger.info("Copie des ressources applicatives (icônes Phosphor, logo, templates, traductions)...")
    if target_os == "darwin":
        res_dir = dist_dir / "Contents" / "Resources"
        target_res = res_dir / "ressources"
        target_src_res = res_dir / "src" / "ressources"
        shutil.copytree(ressources_src, target_res, dirs_exist_ok=True)
        shutil.copytree(ressources_src, target_src_res, dirs_exist_ok=True)
    else:
        target_res = dist_dir / "ressources"
        target_src_res = dist_dir / "src" / "ressources"
        shutil.copytree(ressources_src, target_res, dirs_exist_ok=True)
        shutil.copytree(ressources_src, target_src_res, dirs_exist_ok=True)


def strip_binary_symbols(dist_dir: Path, target_os: str) -> None:
    """Allège les binaires en supprimant les symboles de débogage inutiles (strip)."""
    logger.info("Allègement des symboles binaires C (strip)...")
    if target_os == "linux":
        try:
            for so_file in dist_dir.glob("*.so"):
                subprocess.run(["strip", "--strip-unneeded", str(so_file)], check=False)
            main_bin = dist_dir / "AnkiForge"
            if main_bin.exists():
                subprocess.run(["strip", "--strip-unneeded", str(main_bin)], check=False)
        except Exception as err:
            logger.warning("Échec partiel du stripping Linux : %s", err)
    elif target_os == "darwin":
        try:
            macos_dir = dist_dir / "Contents" / "MacOS"
            if macos_dir.exists():
                for binary in macos_dir.iterdir():
                    if binary.is_file() and not binary.name.startswith("."):
                        subprocess.run(["strip", "-x", str(binary)], check=False)
        except Exception as err:
            logger.warning("Échec partiel du stripping macOS : %s", err)


def isolate_macos_binaries_and_resources(dist_dir: Path) -> None:
    """Sépare strictement les exécutables Mach-O (Contents/MacOS) des ressources de données (Contents/Resources).

    Indispensable pour respecter les spécifications Apple App Bundle et passer la validation codesign sans erreur.
    """
    macos_dir = dist_dir / "Contents" / "MacOS"
    res_dir = dist_dir / "Contents" / "Resources"
    res_dir.mkdir(parents=True, exist_ok=True)

    if not macos_dir.exists():
        return

    # 1. Déplacer les dossiers de données (non-binaires) vers Resources
    for item in list(macos_dir.iterdir()):
        if item.is_dir() and item.name not in ("PySide6", "shiboken6", "websockets"):
            target = res_dir / item.name
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.move(str(item), str(target))

    # 2. Déplacer les fichiers de données non Mach-O vers Resources
    for ext in ("*.dat", "*.pak", "*.bin", "*.conf", "*.xcprivacy", "*.plist", "*.json", "*.txt", "*.qm"):
        for file_path in macos_dir.glob(ext):
            target = res_dir / file_path.name
            if target.exists():
                target.unlink()
            shutil.move(str(file_path), str(target))


def sign_macos_bundle(dist_dir: Path) -> None:
    """Signe le bundle macOS selon les règles strictes Apple Leaf-to-Root (de l'intérieur vers l'extérieur)."""
    isolate_macos_binaries_and_resources(dist_dir)

    logger.info("Nettoyage des fichiers temporaires, bytecode et anciens scellages...")
    for pycache in dist_dir.rglob("__pycache__"):
        if pycache.is_dir():
            shutil.rmtree(pycache, ignore_errors=True)
    for pyc in dist_dir.rglob("*.pyc"):
        try:
            pyc.unlink()
        except Exception:
            pass

    code_sig = dist_dir / "Contents" / "_CodeSignature"
    if code_sig.exists():
        shutil.rmtree(code_sig, ignore_errors=True)

    logger.info("Nettoyage des attributs étendus (quarantine, provenance)...")
    subprocess.run(["xattr", "-cr", str(dist_dir)], check=False)

    logger.info("Signature Ad-Hoc de chaque binaire individuel (.dylib, .so)...")
    binaries: list[str] = []
    for ext in ("*.dylib", "*.so"):
        binaries.extend([str(p) for p in dist_dir.rglob(ext) if p.is_file()])

    for binary_path in binaries:
        subprocess.run(["codesign", "--force", "-s", "-", binary_path], check=False)

    # Signature des Frameworks PySide6/Qt
    frameworks_dir = dist_dir / "Contents" / "Frameworks"
    if frameworks_dir.exists():
        for fw in frameworks_dir.rglob("*.framework"):
            if fw.is_dir():
                subprocess.run(["codesign", "--force", "-s", "-", str(fw)], check=False)

    # Signature de chaque exécutable Mach-O dans Contents/MacOS
    macos_dir = dist_dir / "Contents" / "MacOS"
    if macos_dir.exists():
        for exe in macos_dir.iterdir():
            if exe.is_file() and not exe.name.startswith("."):
                subprocess.run(["codesign", "--force", "-s", "-", str(exe)], check=False)

    # Signature du bundle racine .app (SANS --deep pour ne pas corrompre le scellage)
    subprocess.run(["codesign", "--force", "-s", "-", str(dist_dir)], check=False)

    # Validation
    verify = subprocess.run(["codesign", "-vvv", str(dist_dir)], capture_output=True, text=True, check=False)
    if verify.returncode == 0:
        logger.info("✅ Signature Ad-Hoc du bundle macOS validée avec succès !")
    else:
        logger.warning("Avertissement de signature macOS : %s", verify.stderr)


def main() -> None:
    """Point d'entrée principal du pilote de compilation."""
    parser = argparse.ArgumentParser(description="Pilote de compilation Nuitka multi-plateformes AnkiForge.")
    parser.add_argument("--dry-run", action="store_true", help="Affiche la commande Nuitka générée sans l'exécuter.")
    parser.add_argument("--jobs", type=int, default=0, help="Nombre de cœurs CPU (0 = auto-détection).")
    parser.add_argument("--target-os", choices=["darwin", "linux", "windows"], default="", help="OS cible forcé.")
    args = parser.parse_args()

    # Détection de la plateforme
    target_os = args.target_os or platform.system().lower()
    if target_os == "darwin":
        pass
    elif "win" in target_os:
        target_os = "windows"
    else:
        target_os = "linux"

    # Calcul adaptatif des cœurs CPU
    jobs = args.jobs or min(os.cpu_count() or 4, 8)

    config = load_config()
    cmd = build_nuitka_command(config, target_os, jobs)

    if args.dry_run:
        print("\n=== Commande Nuitka Générée (Dry Run) ===")
        print(" ".join(cmd))
        print(f"OS cible : {target_os} | CPU Jobs : {jobs}\n")
        return

    logger.info("Démarrage de la compilation AnkiForge pour %s (Jobs: %d)...", target_os, jobs)
    os.chdir(PROJECT_ROOT)

    # 1. Exécution de la compilation Nuitka
    ret = subprocess.run(cmd, check=False)
    if ret.returncode != 0:
        logger.error("Échec de la compilation Nuitka (Code retour: %d)", ret.returncode)
        sys.exit(ret.returncode)

    # Détermination du dossier produit
    if target_os == "darwin":
        lower_app = PROJECT_ROOT / "dist_prod" / "ankiforge.app"
        upper_app = PROJECT_ROOT / "dist_prod" / "AnkiForge.app"
        if lower_app.exists() and not upper_app.exists():
            temp_app = PROJECT_ROOT / "dist_prod" / "temp_ankiforge.app"
            lower_app.rename(temp_app)
            temp_app.rename(upper_app)
        dist_dir = upper_app if upper_app.exists() else lower_app
        target_site_packages = dist_dir / "Contents" / "Resources"
    else:
        # Nuitka nomme par défaut le dossier de distribution 'ankiforge.dist' (minuscules).
        # On le normalise vers 'AnkiForge.dist' pour compatibilité avec tous les scripts et la CI.
        lower_dist = PROJECT_ROOT / "dist_prod" / "ankiforge.dist"
        upper_dist = PROJECT_ROOT / "dist_prod" / "AnkiForge.dist"
        if lower_dist.exists() and not upper_dist.exists():
            logger.info("Normalisation du dossier : %s -> %s", lower_dist.name, upper_dist.name)
            lower_dist.rename(upper_dist)
        dist_dir = upper_dist if upper_dist.exists() else lower_dist
        target_site_packages = dist_dir

    # 2. Copie et élagage des dépendances runtime
    logger.info("Copie et élagage des dépendances tierces dans %s...", target_site_packages)
    copy_runtime_deps(target_site_packages)

    # 3. Copie des scripts de migration SQL et des ressources applicatives
    copy_migrations_to_bundle(dist_dir, target_os)
    copy_app_resources_to_bundle(dist_dir, target_os)

    # 4. Stripping des symboles
    strip_binary_symbols(dist_dir, target_os)

    # 5. Signature Ad-Hoc macOS si applicable
    if target_os == "darwin":
        sign_macos_bundle(dist_dir)

    logger.info("✨ Compilation et empaquetage achevés avec succès pour %s dans %s !", target_os, dist_dir)


if __name__ == "__main__":
    main()

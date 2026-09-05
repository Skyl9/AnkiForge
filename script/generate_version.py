#!/usr/bin/env python3
"""Générateur de métadonnées de version figées (_version.py) pour le build et la CI/CD AnkiForge."""

from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess  # nosec: B404
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_git_commit() -> str:
    """Récupère le SHA court du commit actuel."""
    # 1. Variable d'environnement CI (GitHub Actions)
    ci_sha = os.environ.get("GITHUB_SHA")
    if ci_sha:
        return ci_sha[:8]

    # 2. Git CLI local
    try:
        res = subprocess.run(  # nosec: B603, B607
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "dev"


def read_pyproject_version() -> str:
    """Lit la version déclarée dans pyproject.toml."""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    if pyproject_path.exists():
        content = pyproject_path.read_text(encoding="utf-8")
        match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
    return "1.0.5"


def generate_version_file(
    version: str | None = None,
    channel: str | None = None,
    commit: str | None = None,
    build_date: str | None = None,
) -> Path:
    """Génère le fichier src/ankiforge/_version.py."""
    # Résolution de la version
    if not version:
        env_ver = os.environ.get("BUILD_VERSION") or os.environ.get("ANKIFORGE_BUILD_VERSION") or ""
        if env_ver:
            version = env_ver
        else:
            ref_name = os.environ.get("GITHUB_REF_NAME", "")
            version = ref_name if (ref_name.startswith(("v", "V")) and "." in ref_name) else read_pyproject_version()

    # Normalisation stricte vx.x.x -> x.x.x pour la constante interne
    clean_version = str(version).strip().lstrip("vV").strip()
    if not clean_version:
        clean_version = read_pyproject_version()

    # Résolution du canal
    if not channel:
        channel = "nightly" if (os.environ.get("GITHUB_WORKFLOW") == "Nightly" or "nightly" in str(clean_version).lower()) else "stable"

    # Résolution du commit
    if not commit:
        commit = get_git_commit()

    # Résolution de la date
    if not build_date:
        build_date = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    target_file = PROJECT_ROOT / "src" / "ankiforge" / "_version.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)

    content = f'''"""Fichier généré automatiquement lors du build/packaging d'AnkiForge.
Ne pas modifier manuellement.
"""

VERSION: str = "{clean_version}"
COMMIT_HASH: str = "{commit}"
BUILD_DATE: str = "{build_date}"
BUILD_CHANNEL: str = "{channel}"
'''

    target_file.write_text(content, encoding="utf-8")
    print(f"[SUCCESS] _version.py généré avec succès : v{clean_version} ({commit}) [{channel}]")
    return target_file


def sync_project_files(version: str) -> None:
    """Synchronise la version dans pyproject.toml et windows_installer.iss."""
    clean_version = str(version).strip().lstrip("vV").strip()
    # 1. pyproject.toml
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    if pyproject_path.exists():
        txt = pyproject_path.read_text(encoding="utf-8")
        updated_txt = re.sub(r'version\s*=\s*["\'][^"\']+["\']', f'version = "{clean_version}"', txt, count=1)
        pyproject_path.write_text(updated_txt, encoding="utf-8")
        print(f"[INFO] Synchronisé pyproject.toml -> {clean_version}")

    # 2. windows_installer.iss
    iss_path = PROJECT_ROOT / "build_script" / "windows_installer.iss"
    if iss_path.exists():
        txt = iss_path.read_text(encoding="utf-8")
        updated_txt = re.sub(r'#define\s+MyAppVersion\s+["\'][^"\']+["\']', f'#define MyAppVersion "{clean_version}"', txt)
        iss_path.write_text(updated_txt, encoding="utf-8")
        print(f"[INFO] Synchronisé windows_installer.iss -> {clean_version}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Générateur de métadonnées de version AnkiForge")
    parser.add_argument("--version", default=None, help="Version sémantique (ex: v1.1.0 ou 1.1.0)")
    parser.add_argument("--channel", default=None, choices=["stable", "nightly", "dev"], help="Canal de distribution")
    parser.add_argument("--commit", default=None, help="Hash du commit Git")
    parser.add_argument("--date", default=None, help="Date ISO du build")
    parser.add_argument("--sync-all", action="store_true", help="Synchronise aussi pyproject.toml et Inno Setup")

    args = parser.parse_args()

    generate_version_file(
        version=args.version,
        channel=args.channel,
        commit=args.commit,
        build_date=args.date,
    )

    if args.sync_all and args.version:
        sync_project_files(args.version)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Script d'assistance pour le skill session-retrospective.

Analyse l'état de l'arbre de travail Git (repo racine et sous-repo ankiforge_obsidian),
vérifie l'absence de modifications concurrentes non synchronisées et contrôle les garde-fous.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _print(msg: str = "") -> None:
    """Sortie console sans print() pour respecter la règle T20."""
    sys.stdout.write(f"{msg}\n")


def check_git_status(path: Path, repo_label: str) -> bool:
    """Vérifie l'état de travail d'un dépôt Git."""
    _print(f"── Contrôle Git : {repo_label} ({path}) ──")
    try:
        res = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        output = res.stdout.strip()
        if not output:
            _print("  ✅ Répertoire de travail propre (Working tree clean).")
            return True

        _print("  ⚠️ Modifications non validées détectées :")
        for line in output.splitlines():
            _print(f"     {line}")
        return False
    except Exception as exc:
        _print(f"  ❌ Erreur lors du contrôle Git : {exc}")
        return False


def main() -> int:
    repo_root = Path(__file__).resolve().parents[4]
    obsidian_root = repo_root / "ankiforge_obsidian"

    _print("============================================================")
    _print("🔍 Rétrospective de Session — Diagnostic de l'Espace de Travail")
    _print("============================================================")

    clean_root = check_git_status(repo_root, "Dépôt Principal AnkiForge")
    clean_obsidian = check_git_status(obsidian_root, "Sous-Dépôt Obsidian Vault")

    _print("\n── Synthèse des Garde-Fous ──")
    if clean_root and clean_obsidian:
        _print("  ✅ Tous les dépôts sont propres et synchronisés.")
        _print("============================================================\n")
        return 0

    _print("  ℹ️ Des modifications subsistent dans les dépôts.")
    _print("     Vérifiez les diffs avant toute clôture ou changement de tâche.")
    _print("============================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

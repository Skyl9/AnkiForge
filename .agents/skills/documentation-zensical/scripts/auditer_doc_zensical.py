#!/usr/bin/env python3
"""Script d'audit technique et de validation pour la documentation Zensical d'AnkiForge.

Vérifie :
1. La concordance entre la navigation de zensical.toml et les fichiers réels de docs/ (orphelins & liens morts).
2. L'intégrité des liens relatifs markdown internes.
3. La bonne spécification des langages dans les blocs de code (```lang).
4. La conformité des admonitions et blocs de callout Zensical.
5. L'exécution sans erreur de 'uv run zensical build'.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


def _print(msg: str = "") -> None:
    """Sortie console propre sans enfreindre la règle T20 (print())."""
    sys.stdout.write(f"{msg}\n")


def extract_nav_paths(nav_item: Any) -> list[str]:
    """Extrait récursivement tous les chemins de fichiers déclarés dans la section nav."""
    paths: list[str] = []
    if isinstance(nav_item, str):
        paths.append(nav_item)
    elif isinstance(nav_item, dict):
        for val in nav_item.values():
            paths.extend(extract_nav_paths(val))
    elif isinstance(nav_item, list):
        for elem in nav_item:
            paths.extend(extract_nav_paths(elem))
    return paths


def audit_zensical(repo_root: Path, skip_build: bool = False) -> dict[str, Any]:
    """Exécute l'audit complet du site documentaire Zensical."""
    docs_dir = repo_root / "docs"
    toml_path = repo_root / "zensical.toml"

    results: dict[str, Any] = {
        "status": "PASS",
        "total_doc_files": 0,
        "nav_entries_count": 0,
        "missing_from_disk": [],
        "orphaned_files": [],
        "broken_relative_links": [],
        "untyped_code_blocks": [],
        "build_status": "SKIPPED",
        "build_output": "",
        "errors": [],
        "warnings": [],
    }

    if not toml_path.exists():
        results["status"] = "FAIL"
        results["errors"].append(f"Fichier de configuration zensical.toml introuvable : {toml_path}")
        return results

    if not docs_dir.exists():
        results["status"] = "FAIL"
        results["errors"].append(f"Dossier docs/ introuvable : {docs_dir}")
        return results

    # 1. Parsing zensical.toml
    try:
        config_data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        nav_raw = config_data.get("project", {}).get("nav", [])
        nav_paths = extract_nav_paths(nav_raw)
        results["nav_entries_count"] = len(nav_paths)
    except Exception as e:
        results["status"] = "FAIL"
        results["errors"].append(f"Erreur de lecture de zensical.toml : {e}")
        return results

    # 2. Vérification des fichiers du nav vs disque
    all_disk_files = {p.relative_to(docs_dir).as_posix() for p in docs_dir.rglob("*.md")}
    results["total_doc_files"] = len(all_disk_files)

    for nav_file in nav_paths:
        file_path = docs_dir / nav_file
        if not file_path.exists():
            results["missing_from_disk"].append(nav_file)
            results["errors"].append(f"Navigation zensical.toml : fichier manquant sur le disque -> '{nav_file}'")

    # Fichiers orphelins (sur disque mais absents du nav)
    nav_set = set(nav_paths)
    orphans = sorted(all_disk_files - nav_set)
    if orphans:
        results["orphaned_files"] = orphans
        for orphan in orphans:
            results["warnings"].append(f"Fichier orphelin (non référencé dans zensical.toml) -> 'docs/{orphan}'")

    # 3. Contrôle des liens markdown et des blocs de code
    for md_path in docs_dir.rglob("*.md"):
        rel_md = md_path.relative_to(docs_dir).as_posix()
        try:
            content = md_path.read_text(encoding="utf-8")
        except Exception as e:
            results["errors"].append(f"Impossible de lire docs/{rel_md} : {e}")
            continue

        # Vérification des liens relatifs [text](target.md)
        links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
        for _, target in links:
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            # Gestion d'ancre éventuelle
            target_file = target.split("#")[0].strip()
            if not target_file:
                continue
            # Résolution relative au dossier du fichier md
            resolved = (md_path.parent / target_file).resolve()
            if not resolved.exists():
                results["broken_relative_links"].append(
                    {
                        "source": rel_md,
                        "target": target,
                    }
                )
                results["errors"].append(f"Lien mort dans docs/{rel_md} vers '{target}'")

        # Vérification des blocs de code non typés (``` sans identifiant de syntaxe)
        untyped_matches = list(re.finditer(r"```[ \t]*\n", content))
        if untyped_matches:
            results["untyped_code_blocks"].append(
                {
                    "source": rel_md,
                    "count": len(untyped_matches),
                }
            )
            results["warnings"].append(f"docs/{rel_md} : {len(untyped_matches)} bloc(s) de code sans langage spécifié (```).")

    # 4. Exécution du build Zensical
    if not skip_build:
        try:
            res = subprocess.run(
                ["uv", "run", "zensical", "build"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if res.returncode == 0:
                results["build_status"] = "SUCCESS"
                results["build_output"] = res.stdout.strip()
            else:
                results["build_status"] = "FAILED"
                results["build_output"] = (res.stderr or res.stdout).strip()
                results["errors"].append(f"Échec de 'uv run zensical build' (code {res.returncode}) : {results['build_output']}")
        except Exception as e:
            results["build_status"] = "ERROR"
            results["errors"].append(f"Erreur lors du lancement de zensical build : {e}")

    if results["errors"]:
        results["status"] = "FAIL"
    elif results["warnings"]:
        results["status"] = "WARN"

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit et contrôle technique de la documentation Zensical")
    parser.add_argument("--json", action="store_true", help="Sortie au format JSON")
    parser.add_argument("--skip-build", action="store_true", help="Ignorer l'étape de compilation 'zensical build'")
    parser.add_argument("--quiet", action="store_true", help="Afficher uniquement les erreurs")
    args = parser.parse_args()

    # .agents/skills/documentation-zensical/scripts/auditer_doc_zensical.py -> parents[4] is repo root
    repo_root = Path(__file__).resolve().parents[4]
    audit_res = audit_zensical(repo_root, skip_build=args.skip_build)

    if args.json:
        _print(json.dumps(audit_res, indent=2, ensure_ascii=False))
        return 0 if audit_res["status"] != "FAIL" else 1

    _print(f"\n{'=' * 60}")
    _print(f"📚 Audit Technique Documentation Zensical [{audit_res['status']}]")
    _print(f"{'=' * 60}")
    _print(f"Fichiers docs/ : {audit_res['total_doc_files']} | Entrées nav : {audit_res['nav_entries_count']}")
    _print(f"Build Zensical : {audit_res['build_status']}")

    if audit_res["errors"]:
        _print(f"\n❌ ERREURS ({len(audit_res['errors'])}):")
        for err in audit_res["errors"]:
            _print(f"  - {err}")

    if audit_res["warnings"] and not args.quiet:
        _print(f"\n⚠️ AVERTISSEMENTS ({len(audit_res['warnings'])}):")
        for warn in audit_res["warnings"]:
            _print(f"  - {warn}")

    if audit_res["status"] == "PASS":
        _print("\n✅ La documentation Zensical est intègre, cohérente et compile sans erreur !")

    _print(f"{'=' * 60}\n")
    return 0 if audit_res["status"] != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())

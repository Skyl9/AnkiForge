#!/usr/bin/env python3
"""Script de synchronisation et de vérification d'intégrité des instructions agents.

Assure la projection déterministe des fragments canoniques (.agents/instructions/*.md)
vers les adaptateurs cibles (GEMINI.md, AGENTS.md, CLAUDE.md, .github/copilot-instructions.md)
par transclusion délimitée entre balises :
    <!-- CANONICAL:START:<nom_bloc> -->
    ...
    <!-- CANONICAL:END:<nom_bloc> -->

Utilisation :
    uv run python script/sync_agent_instructions.py --check   # Vérifie la dérive (fail-fast, exit 1 si désynchronisé)
    uv run python script/sync_agent_instructions.py           # Synchronise et réécrit les adaptateurs sur disque
    uv run python script/sync_agent_instructions.py --write   # Idem (explicite)
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_INSTRUCTIONS_DIR = REPO_ROOT / ".agents" / "instructions"

BLOCK_HEADER_TEMPLATE = "<!-- ⚠️ BLOC AUTO-GÉNÉRÉ DEPUIS .agents/instructions/{block_name}.md - NE PAS MODIFIER MANUELLEMENT -->"


def _print(msg: str = "") -> None:
    """Sortie console propre conforme à la règle Ruff T20 (pas de print())."""
    sys.stdout.write(f"{msg}\n")


@dataclass(frozen=True)
class TargetAdapter:
    """Représentation d'un adaptateur cible d'instructions agent."""

    path: str
    expected_blocks: list[str]


TARGET_ADAPTERS: list[TargetAdapter] = [
    TargetAdapter(
        path="GEMINI.md",
        expected_blocks=["commandes", "regles_ingenierie", "architecture_points_cles", "catalogue_skills"],
    ),
    TargetAdapter(
        path="AGENTS.md",
        expected_blocks=["commandes", "regles_ingenierie", "architecture_points_cles", "catalogue_skills"],
    ),
    TargetAdapter(
        path="CLAUDE.md",
        expected_blocks=["commandes", "regles_ingenierie", "architecture_points_cles"],
    ),
    TargetAdapter(
        path=".github/copilot-instructions.md",
        expected_blocks=["commandes", "regles_ingenierie", "architecture_points_cles"],
    ),
]


def extract_canonical_blocks(instructions_dir: Path) -> dict[str, str]:
    """Charge l'ensemble des fragments Markdown présents dans le répertoire canonique."""
    blocks: dict[str, str] = {}
    if not instructions_dir.is_dir():
        return blocks

    for file_path in sorted(instructions_dir.glob("*.md")):
        block_name = file_path.stem
        content = file_path.read_text(encoding="utf-8").strip()
        blocks[block_name] = content
    return blocks


def generate_initial_adapter_template(adapter_path: str, expected_blocks: list[str]) -> str:
    """Génère le gabarit initial pour un adaptateur absent sur disque."""
    title_by_file: dict[str, str] = {
        "CLAUDE.md": "# Instructions Anthropic Claude Code — AnkiForge\n\nCe document fournit les règles d'ingénierie et le contexte de référence pour l'agent CLI Anthropic Claude Code.\n",
        "AGENTS.md": "# AGENTS.md — Référence Multi-Agents AnkiForge\n\nGuide opérationnel et aide-mémoire canonique pour les agents de développement.\n",
        "GEMINI.md": "# 🤖 Instructions Agentiques (System Prompt) - AnkiForge Orchestrator\n\nSystem Prompt orchestrateur et référentiel pour les modèles Google Antigravity / Gemini.\n",
        ".github/copilot-instructions.md": "# AnkiForge Copilot Instructions\n\nInstructions d'assistance et de complétion de code pour GitHub Copilot dans AnkiForge.\n",
    }
    header = title_by_file.get(adapter_path, f"# Instructions pour {adapter_path}\n\n")
    blocks_stubs = "\n\n".join(f"<!-- CANONICAL:START:{b} -->\n<!-- CANONICAL:END:{b} -->" for b in expected_blocks)
    return f"{header}\n{blocks_stubs}\n"


def render_adapter_content(existing_content: str, adapter: TargetAdapter, blocks: dict[str, str]) -> tuple[str, list[str]]:
    """Injecte les blocs canoniques délimités dans le contenu de l'adaptateur cible."""
    content = existing_content
    issues: list[str] = []

    for block_name in adapter.expected_blocks:
        if block_name not in blocks:
            issues.append(f"Fragment source introuvable pour '{block_name}'")
            continue

        pattern = re.compile(
            rf"(<!--\s*CANONICAL:START:{re.escape(block_name)}\s*-->)(.*?)(<!--\s*CANONICAL:END:{re.escape(block_name)}\s*-->)",
            re.DOTALL,
        )

        match = pattern.search(content)
        if not match:
            issues.append(f"Balise manquante pour '{block_name}' dans {adapter.path}")
            continue

        block_body = blocks[block_name]
        header = BLOCK_HEADER_TEMPLATE.format(block_name=block_name)
        replacement = f"\\1\n{header}\n\n{block_body}\n\\3"
        content = pattern.sub(replacement, content)

    return content, issues


def check_adapters_drift(repo_root: Path, adapters: list[TargetAdapter], instructions_dir: Path) -> tuple[bool, dict[str, str]]:
    """Vérifie si les adaptateurs sur disque diffèrent de leur projection canonique."""
    blocks = extract_canonical_blocks(instructions_dir)
    diffs: dict[str, str] = {}
    is_ok = True

    for adapter in adapters:
        target_file = repo_root / adapter.path
        if not target_file.is_file():
            diffs[adapter.path] = f"Fichier cible manquant sur disque : {adapter.path}"
            is_ok = False
            continue

        current_content = target_file.read_text(encoding="utf-8")
        rendered_content, issues = render_adapter_content(current_content, adapter, blocks)

        if issues:
            diffs[adapter.path] = "Problèmes de balisage : " + "; ".join(issues)
            is_ok = False
            continue

        if current_content != rendered_content:
            diff = "".join(
                difflib.unified_diff(
                    current_content.splitlines(keepends=True),
                    rendered_content.splitlines(keepends=True),
                    fromfile=f"a/{adapter.path}",
                    tofile=f"b/{adapter.path}",
                )
            )
            diffs[adapter.path] = diff or "Différences de contenu ou d'espacement détectées"
            is_ok = False

    return is_ok, diffs


def sync_all_adapters(repo_root: Path, adapters: list[TargetAdapter], instructions_dir: Path) -> tuple[list[str], list[str]]:
    """Génère ou met à jour l'ensemble des adaptateurs sur disque."""
    blocks = extract_canonical_blocks(instructions_dir)
    synced: list[str] = []
    errors: list[str] = []

    for adapter in adapters:
        target_file = repo_root / adapter.path
        if not target_file.is_file():
            # Initialisation depuis le gabarit
            current_content = generate_initial_adapter_template(adapter.path, adapter.expected_blocks)
            target_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            current_content = target_file.read_text(encoding="utf-8")

        rendered_content, issues = render_adapter_content(current_content, adapter, blocks)
        if issues:
            errors.append(f"Erreur sur {adapter.path} : {'; '.join(issues)}")
            continue

        target_file.write_text(rendered_content, encoding="utf-8")
        synced.append(adapter.path)

    return synced, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synchronisation et contrôle des instructions agents")
    parser.add_argument("--check", action="store_true", help="Vérifie la dérive sans modifier les fichiers sur disque")
    parser.add_argument("--write", action="store_true", help="Applique la synchronisation sur les fichiers cibles")
    parser.add_argument("--quiet", action="store_true", help="N'affiche que les erreurs")
    args = parser.parse_args(argv)

    if args.check:
        is_ok, diffs = check_adapters_drift(repo_root=REPO_ROOT, adapters=TARGET_ADAPTERS, instructions_dir=CANONICAL_INSTRUCTIONS_DIR)
        if is_ok:
            if not args.quiet:
                _print("✅ Tous les adaptateurs d'instructions sont synchronisés avec la source canonique.")
            return 0

        _print("❌ Dérive détectée sur les adaptateurs d'instructions agents :")
        for path, diff_text in diffs.items():
            _print(f"\n--- Dérive sur {path} ---")
            _print(diff_text)
        _print("\n👉 Exécutez 'uv run python script/sync_agent_instructions.py' ou 'uv run python script/verify.py --fix' pour resynchroniser.")
        return 1

    # Mode synchronisation / écriture
    synced, errors = sync_all_adapters(repo_root=REPO_ROOT, adapters=TARGET_ADAPTERS, instructions_dir=CANONICAL_INSTRUCTIONS_DIR)

    if errors:
        for err in errors:
            _print(f"❌ {err}")
        return 1

    if not args.quiet:
        _print(f"✅ {len(synced)} adaptateurs d'instructions synchronisés avec succès : {', '.join(synced)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

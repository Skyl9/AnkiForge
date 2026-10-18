#!/usr/bin/env python3
"""Script de contrôle de dérive et de régénération de la documentation des raccourcis clavier.

Génère la page de référence Zensical (docs/guides/raccourcis_clavier.md) directement depuis
le catalogue central déclaratif (src/ankiforge/ui/shortcuts/catalog.py) conformément à l'ADR 0032.

Utilisation :
    uv run python script/check_shortcuts_drift.py --check   # Vérifie la dérive (exit 1 si dérive)
    uv run python script/check_shortcuts_drift.py --fix     # Régénère la page sur disque
"""

from __future__ import annotations

import argparse
import difflib
import sys
from collections import defaultdict
from pathlib import Path

from ankiforge.ui.shortcuts.catalog import get_shortcut_catalog
from ankiforge.ui.shortcuts.models import (
    ShortcutCategory,
    ShortcutDefinition,
    ShortcutId,
    ShortcutScope,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_SHORTCUTS_PATH = REPO_ROOT / "docs" / "guides" / "raccourcis_clavier.md"


def _print(msg: str = "") -> None:
    """Sortie console standard sans print direct (règle Ruff T20)."""
    sys.stdout.write(f"{msg}\n")


def format_scope_label(scope: ShortcutScope) -> str:
    """Convertit une portée d'énumération en libellé lisible en français."""
    match scope:
        case ShortcutScope.APPLICATION:
            return "Application"
        case ShortcutScope.VUE:
            return "Vue"
        case ShortcutScope.WIDGET:
            return "Widget"
        case ShortcutScope.DIALOGUE:
            return "Dialogue"
        case _:
            return str(scope.name).capitalize()


def format_sequence_badge(sequence: str, allow_bare_key: bool = False) -> str:
    """Formate une séquence de touches sous balises HTML <kbd>."""
    clean = sequence.strip()
    if not clean:
        return "—"
    badge = f"<kbd>{clean}</kbd>"
    if allow_bare_key:
        badge += " *(touche nue)*"
    return badge


def generate_shortcuts_markdown(catalog: dict[ShortcutId, ShortcutDefinition] | None = None) -> str:
    """Génère le document Markdown complet pour la référence des raccourcis clavier."""
    effective_catalog = catalog if catalog is not None else get_shortcut_catalog()

    # Regroupement par catégorie
    by_category: dict[ShortcutCategory, list[ShortcutDefinition]] = defaultdict(list)
    for defn in effective_catalog.values():
        by_category[defn.category].append(defn)

    lines: list[str] = [
        "# Référence des Raccourcis Clavier ⌨️",
        "",
        "<!-- ⚠️ DOCUMENT AUTO-GÉNÉRÉ DEPUIS src/ankiforge/ui/shortcuts/catalog.py - NE PAS MODIFIER MANUELLEMENT -->",
        "<!-- Exécutez 'uv run python script/check_shortcuts_drift.py --fix' pour régénérer -->",
        "",
        (
            "Cette page constitue la **référence officielle et exhaustive** de l'ensemble des raccourcis clavier d'AnkiForge, "
            "issue du registre central déclaratif (`src/ankiforge/ui/shortcuts/`) conformément à l'**ADR 0032**."
        ),
        "",
        "> [!NOTE]",
        "> Tous les raccourcis listés ci-dessous peuvent être visualisés, recherchés et personnalisés dans l'application via les **Paramètres (Ctrl+,) > onglet Clavier**.",
        "",
        "---",
        "",
        "## 🏛️ Architecture & Règles Clavier",
        "",
        "1. **Hiérarchie stricte des portées (4 paliers)** :",
        "    - **Dialogue** : priorité absolue lors d'une boîte de dialogue modale ouverte.",
        "    - **Widget** : actif uniquement lorsque le composant spécifique (table, liste, canvas) a le focus.",
        "    - **Vue** : actif dans la vue courante affichée du classeur principal.",
        "    - **Application** : global à l'ensemble du logiciel (palette de commandes, navigation, paramètres).",
        (
            "2. **Priorité absolue à la saisie de texte** : lorsqu'un champ de saisie (`QLineEdit`, `QTextEdit`, KaTeX) a le focus, "
            "les touches nues et commandes d'édition ne déclenchent jamais d'action de carte intempestive."
        ),
        (
            "3. **Séquences protégées** : les raccourcis système indispensables (`Ctrl+C`, `Ctrl+V`, `Ctrl+Z`, `Ctrl+A`, `Ctrl+W`, `Ctrl+Q`) "
            "ne sont pas réassignables pour prévenir toute corruption ergonomique."
        ),
        "",
        "---",
        "",
    ]

    total_actions = len(effective_catalog)
    lines.append(f"## 📋 Inventaire des Raccourcis ({total_actions} actions)")
    lines.append("")

    for cat in ShortcutCategory:
        definitions = by_category.get(cat, [])
        if not definitions:
            continue

        lines.append(f"### {cat.value}")
        lines.append("")
        lines.append("| Action | Séquence par défaut | Portée | Description | Identifiant |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")

        for d in definitions:
            seq_badge = format_sequence_badge(d.default_sequence, d.allow_bare_key)
            scope_str = format_scope_label(d.scope)
            desc = d.description or "—"
            # Nettoyage des pipes éventuels dans le libellé ou la description
            title_clean = d.title.replace("|", "\\|")
            desc_clean = desc.replace("|", "\\|")
            lines.append(f"| **{title_clean}** | {seq_badge} | `{scope_str}` | {desc_clean} | `{d.id.value}` |")

        lines.append("")

    return "\n".join(lines).strip() + "\n"


def check_shortcuts_drift(
    doc_path: Path = DOCS_SHORTCUTS_PATH,
    catalog: dict[ShortcutId, ShortcutDefinition] | None = None,
) -> tuple[bool, str]:
    """Contrôle si la documentation des raccourcis sur disque correspond fidèlement au catalogue."""
    if not doc_path.is_file():
        return False, f"Fichier de documentation introuvable sur disque : {doc_path}"

    expected_content = generate_shortcuts_markdown(catalog)
    actual_content = doc_path.read_text(encoding="utf-8")

    if actual_content == expected_content:
        return True, ""

    diff = "".join(
        difflib.unified_diff(
            actual_content.splitlines(keepends=True),
            expected_content.splitlines(keepends=True),
            fromfile=f"a/{doc_path.name}",
            tofile=f"b/{doc_path.name}",
        )
    )
    return False, diff or "Différences détectées entre le catalogue et la documentation."


def write_shortcuts_doc(
    doc_path: Path = DOCS_SHORTCUTS_PATH,
    catalog: dict[ShortcutId, ShortcutDefinition] | None = None,
) -> None:
    """Régénère le fichier de documentation des raccourcis sur le disque."""
    content = generate_shortcuts_markdown(catalog)
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(content, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Contrôle et synchronisation de la documentation des raccourcis clavier")
    parser.add_argument("--check", action="store_true", help="Vérifie la dérive sans modifier la documentation")
    parser.add_argument("--fix", "--write", action="store_true", dest="fix", help="Régénère la page de documentation sur disque")
    parser.add_argument("--quiet", action="store_true", help="N'affiche que les erreurs")
    args = parser.parse_args(argv)

    if args.check:
        is_ok, diff_or_msg = check_shortcuts_drift(DOCS_SHORTCUTS_PATH)
        if is_ok:
            if not args.quiet:
                _print("✅ La page de référence des raccourcis clavier est synchronisée avec le catalogue.")
            return 0

        _print("❌ Dérive détectée sur la documentation des raccourcis clavier (docs/guides/raccourcis_clavier.md) :")
        _print(diff_or_msg)
        _print("\n👉 Exécutez 'uv run python script/check_shortcuts_drift.py --fix' ou 'uv run python script/verify.py --fix' pour la régénérer.")
        return 1

    # Mode fix / régénération
    write_shortcuts_doc(DOCS_SHORTCUTS_PATH)
    if not args.quiet:
        _print(f"✅ Documentation des raccourcis clavier régénérée avec succès : {DOCS_SHORTCUTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

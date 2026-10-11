#!/usr/bin/env python3
"""Script d'analyse statique pour recenser les icônes Phosphor utilisées dans AnkiForge.

Parcourt l'AST Python (appels à load_phosphor_icon, load_on_accent_icon, IconButton,
ActionButton, SubTabButton, dictionnaires d'icônes, etc.) ainsi que les préfixes ph.*
pour produire le manifeste canonique ``src/ressources/icons_manifest.txt``.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "src" / "ressources" / "icons_manifest.txt"
DEFAULT_SVG_DIR = PROJECT_ROOT / "src" / "ressources" / "phosphor-icons" / "SVGs"

# Fonctions et constructeurs connus acceptant des identifiants d'icônes Phosphor
KNOWN_ICON_CALLS: dict[str, dict[str, Any]] = {
    "load_phosphor_icon": {"name_arg": 0, "name_kw": "name", "weight_arg": 2, "weight_kw": "weight"},
    "load_on_accent_icon": {"name_arg": 0, "name_kw": "name", "weight_arg": 1, "weight_kw": "weight"},
    "IconButton": {"name_arg": 0, "name_kw": "icon_name"},
    "ActionButton": {"name_arg": 0, "name_kw": "icon_name"},
    "SubTabButton": {"name_arg": 1, "name_kw": "icon_name"},
    "PremiumActionCard": {"name_arg": 0, "name_kw": "icon_name"},
    "LayoutThumbnailCard": {"name_arg": 3, "name_kw": "icon_name"},
    "SidebarItem": {"name_arg": 1, "name_kw": "icon_name"},
    "register_command": {"name_arg": 2, "name_kw": "icon_name"},
    "Badge": {"name_kw": "icon_name"},
    "OptionToggleRow": {"name_kw": "icon_name"},
    "StatusBadge": {"name_kw": "icon_name"},
}

ICON_KEYWORD_NAMES = frozenset({"icon", "icon_name", "icon_ph"})

# Icônes résolues dynamiquement (ex: mapping de ToastLevel vers icônes pleines 'fill')
DYNAMIC_ICON_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("check-circle", "fill"),
        ("info", "fill"),
        ("warning", "fill"),
        ("warning-octagon", "fill"),
        ("cards", "fill"),
        ("folder", "fill"),
        ("images", "fill"),
        ("file-pdf", "fill"),
        ("book-open", "fill"),
        ("presentation", "fill"),
        ("waveform", "fill"),
        ("file-code", "fill"),
        ("file-text", "fill"),
        ("coins", "fill"),
        ("sparkle", "fill"),
        ("check-circle", "bold"),
        ("plus", "bold"),
    }
)


def clean_icon_name(raw: str) -> str:
    """Normalise un identifiant d'icône (supprime préfixes ph./phosphor. et extension .svg)."""
    s = raw.strip()
    for prefix in ("ph.", "ph:", "phosphor.", "phosphor:"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    if s.endswith(".svg"):
        s = s[:-4]
    return s.strip()


class CodeIconVisitor(ast.NodeVisitor):
    """Visiteur AST extrayant les noms d'icônes et leurs poids depuis le code source."""

    def __init__(self) -> None:
        self.found_icons: set[tuple[str, str]] = set()

    def visit_Call(self, node: ast.Call) -> None:
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name in KNOWN_ICON_CALLS:
            spec = KNOWN_ICON_CALLS[func_name]
            name: str | None = None
            weight = "regular"

            name_idx = spec.get("name_arg")
            if name_idx is not None and len(node.args) > name_idx:
                arg_val = node.args[name_idx]
                if isinstance(arg_val, ast.Constant) and isinstance(arg_val.value, str):
                    name = arg_val.value
            if not name and "name_kw" in spec:
                for kw in node.keywords:
                    if kw.arg == spec["name_kw"] and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        name = kw.value.value

            weight_idx = spec.get("weight_arg")
            if weight_idx is not None and len(node.args) > weight_idx:
                w_val = node.args[weight_idx]
                if isinstance(w_val, ast.Constant) and isinstance(w_val.value, str):
                    weight = w_val.value
            if "weight_kw" in spec:
                for kw in node.keywords:
                    if kw.arg == spec["weight_kw"] and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        weight = kw.value.value

            if name:
                cleaned = clean_icon_name(name)
                if cleaned:
                    self.found_icons.add((cleaned, weight.lower().strip() or "regular"))

        # Détection des arguments mots-clés d'icône génériques
        for kw in node.keywords:
            if kw.arg in ICON_KEYWORD_NAMES and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                cleaned = clean_icon_name(kw.value.value)
                if cleaned:
                    self.found_icons.add((cleaned, "regular"))

        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for k, v in zip(node.keys, node.values, strict=False):
            if isinstance(k, ast.Constant) and isinstance(k.value, str) and k.value in ICON_KEYWORD_NAMES and isinstance(v, ast.Constant) and isinstance(v.value, str):
                cleaned = clean_icon_name(v.value)
                if cleaned:
                    self.found_icons.add((cleaned, "regular"))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            val = node.value.strip()
            if val.startswith(("ph.", "ph:", "phosphor.", "phosphor:")):
                cleaned = clean_icon_name(val)
                if cleaned:
                    self.found_icons.add((cleaned, "regular"))
        self.generic_visit(node)


def scan_icons_in_codebase(root_dirs: list[Path] | None = None) -> set[tuple[str, str]]:
    """Scanne les répertoires spécifiés (par défaut ``src/`` et ``tests/``) et retourne les couples ``(nom, poids)``."""
    if root_dirs is None:
        root_dirs = [PROJECT_ROOT / "src", PROJECT_ROOT / "tests"]

    visitor = CodeIconVisitor()
    for root_dir in root_dirs:
        if not root_dir.exists():
            continue
        for py_path in root_dir.rglob("*.py"):
            try:
                content = py_path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(py_path))
                visitor.visit(tree)
            except Exception as err:
                print(f"[scan_used_icons] Avertissement lors de l'analyse de {py_path}: {err}", file=sys.stderr)

    icons = set(visitor.found_icons)
    icons.update(DYNAMIC_ICON_PAIRS)
    return icons


def resolve_svg_relpaths(
    scanned_icons: set[tuple[str, str]],
    svg_base_dir: Path | None = None,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Résout les couples (nom, poids) en chemins relatifs SVGs/<poids>/<fichier>.svg.

    Retourne:
        tuple[list[str], list[tuple[str, str]]]:
            - Chemins relatifs normalisés triés (ex: 'SVGs/regular/house.svg').
            - Liste des icônes introuvables (nom, poids) le cas échéant.
    """
    svg_dir = svg_base_dir or DEFAULT_SVG_DIR
    resolved_paths: set[str] = set()
    unresolved: list[tuple[str, str]] = []

    for name, weight in sorted(scanned_icons):
        if not name or name == "non_existent_icon_xyz_123":
            continue

        weight = weight.lower().strip() or "regular"
        suffix = f"-{weight}" if weight != "regular" else ""
        filename = f"{name}{suffix}.svg"
        candidate_rel = f"SVGs/{weight}/{filename}"
        regular_rel = f"SVGs/regular/{name}.svg"

        target_exists = (svg_dir / weight / filename).exists() if svg_dir.exists() else True
        regular_exists = (svg_dir / "regular" / f"{name}.svg").exists() if svg_dir.exists() else True

        if target_exists:
            resolved_paths.add(candidate_rel)
            # Si le poids est non-regular, inclure aussi le repli regular s'il existe
            if weight != "regular" and regular_exists:
                resolved_paths.add(regular_rel)
        elif regular_exists:
            # Repli direct sur regular
            resolved_paths.add(regular_rel)
        else:
            unresolved.append((name, weight))

    return sorted(resolved_paths), unresolved


def generate_manifest_text(relpaths: list[str]) -> str:
    """Génère le contenu textuel canonique pour ``icons_manifest.txt``."""
    lines = [
        "# Manifeste canonique des icônes Phosphor requises par AnkiForge",
        "# Généré par script/scan_used_icons.py",
        f"# Total : {len(relpaths)} fichiers SVG",
        "",
    ]
    lines.extend(relpaths)
    lines.append("")
    return "\n".join(lines)


def parse_manifest_file(manifest_path: Path) -> list[str]:
    """Lit un fichier manifeste existant et retourne la liste triée des chemins relatifs."""
    if not manifest_path.is_file():
        return []
    lines: list[str] = []
    for raw_line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return sorted(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyse statique et génération du manifeste d'icônes Phosphor.")
    parser.add_argument("--check", action="store_true", help="Vérifie si le manifeste actuel est synchrone avec le code.")
    parser.add_argument("--output", type=Path, default=DEFAULT_MANIFEST_PATH, help="Chemin du manifeste de sortie.")
    args = parser.parse_args()

    print("[scan_used_icons] Analyse du code source AnkiForge (src/ et tests/)...")
    scanned = scan_icons_in_codebase()
    relpaths, unresolved = resolve_svg_relpaths(scanned)

    if unresolved:
        print(f"[scan_used_icons] Attention : {len(unresolved)} icône(s) introuvable(s) dans le dossier SVG source :")
        for name, weight in unresolved:
            print(f"  - {name} (poids: {weight})")

    print(f"[scan_used_icons] {len(relpaths)} fichiers SVG résolus.")

    if args.check:
        current = parse_manifest_file(args.output)
        if current == relpaths:
            print(f"[scan_used_icons] OK : Le manifeste {args.output.name} est parfaitement à jour.")
            return 0
        else:
            diff_add = set(relpaths) - set(current)
            diff_sub = set(current) - set(relpaths)
            print(f"[scan_used_icons] ERREUR : Le manifeste n'est pas synchronisé ({len(diff_add)} ajouts, {len(diff_sub)} retraits).", file=sys.stderr)
            return 1

    manifest_text = generate_manifest_text(relpaths)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(manifest_text, encoding="utf-8")
    print(f"[scan_used_icons] Manifeste écrit avec succès dans : {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

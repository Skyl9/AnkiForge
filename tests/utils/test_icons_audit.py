"""Audit de non-régression des icônes Phosphor : aucune icône appelée ne doit manquer.

Vérifie que :
1. Le fichier ``icons_manifest.txt`` existe et contient des chemins valides.
2. Tout fichier SVG déclaré dans le manifeste existe physiquement sur le disque.
3. Aucun SVG orphelin/non-déclaré ne persiste dans ``src/ressources/phosphor-icons/SVGs/``.
4. Toute icône Phosphor appelée dans le code source (Python/AST) figure dans le manifeste.
5. ``load_phosphor_icon`` charge sans erreur les icônes du manifeste.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Ajout du dossier script/ pour importer scan_used_icons
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = PROJECT_ROOT / "script"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from scan_used_icons import (  # noqa: E402
    parse_manifest_file,
    resolve_svg_relpaths,
    scan_icons_in_codebase,
)

from ankiforge.utils.icon_loader import clear_icon_cache, load_phosphor_icon  # noqa: E402

pytestmark = pytest.mark.unit

MANIFEST_PATH = PROJECT_ROOT / "src" / "ressources" / "icons_manifest.txt"
PHOSPHOR_DIR = PROJECT_ROOT / "src" / "ressources" / "phosphor-icons"
SVG_ROOT = PHOSPHOR_DIR / "SVGs"


def test_manifest_file_exists_and_populated() -> None:
    """Le manifeste icons_manifest.txt doit exister et déclarer des icônes."""
    assert MANIFEST_PATH.is_file(), f"Le fichier manifeste {MANIFEST_PATH} est introuvable."
    entries = parse_manifest_file(MANIFEST_PATH)
    assert len(entries) > 50, f"Le manifeste semble anormalement vide ({len(entries)} icônes)."


def test_all_manifest_icons_exist_on_disk() -> None:
    """Chaque SVG déclaré dans le manifeste doit exister physiquement sur le disque."""
    entries = parse_manifest_file(MANIFEST_PATH)
    missing: list[str] = []
    for relpath in entries:
        full_path = PHOSPHOR_DIR / relpath
        if not full_path.is_file():
            missing.append(relpath)

    assert not missing, f"Icônes déclarées dans le manifeste mais absentes du disque ({len(missing)}) :\n" + "\n".join(missing[:20])


def test_no_unmanifested_svg_icons_in_repository() -> None:
    """Aucun SVG non déclaré ne doit subsister dans src/ressources/phosphor-icons/SVGs/."""
    manifest_entries = set(parse_manifest_file(MANIFEST_PATH))
    unmanifested: list[str] = []
    for svg_file in SVG_ROOT.rglob("*.svg"):
        rel = svg_file.relative_to(PHOSPHOR_DIR).as_posix()
        if rel not in manifest_entries:
            unmanifested.append(rel)

    assert not unmanifested, (
        f"Des fichiers SVG non déclarés subsistent sur le disque ({len(unmanifested)}) :\n"
        + "\n".join(unmanifested[:20])
        + "\nExécutez 'uv run python script/sync_icons.py' pour élaguer les icônes orphelines."
    )


def test_all_codebase_icons_are_manifested() -> None:
    """Toute icône Phosphor référencée dans le code doit figurer dans le manifeste."""
    manifest_entries = set(parse_manifest_file(MANIFEST_PATH))
    scanned_icons = scan_icons_in_codebase()
    code_relpaths, unresolved = resolve_svg_relpaths(scanned_icons, svg_base_dir=SVG_ROOT)

    assert not unresolved, "Icônes appelées dans le code mais introuvables dans Phosphor :\n" + "\n".join(f"{n} ({w})" for n, w in unresolved)

    missing_from_manifest = set(code_relpaths) - manifest_entries
    assert not missing_from_manifest, (
        f"Icônes utilisées dans le code mais absentes du manifeste ({len(missing_from_manifest)}) :\n"
        + "\n".join(sorted(missing_from_manifest)[:20])
        + "\nExécutez 'uv run python script/scan_used_icons.py' pour mettre à jour le manifeste."
    )


def test_icon_loader_loads_manifest_sample(qapp: Any) -> None:
    """Vérifie que load_phosphor_icon charge avec succès un échantillon d'icônes du manifeste."""
    clear_icon_cache()
    sample_icons = [
        ("house", "regular"),
        ("cards", "fill"),
        ("sparkle", "fill"),
        ("check-circle", "bold"),
        ("plus", "bold"),
        ("file-text", "regular"),
        ("gear", "regular"),
        ("trash", "regular"),
    ]
    for name, weight in sample_icons:
        icon = load_phosphor_icon(name, weight=weight)
        assert not icon.isNull(), f"Échec de chargement de l'icône '{name}' avec le poids '{weight}'"
        assert len(icon.availableSizes()) > 0

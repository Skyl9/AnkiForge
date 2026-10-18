"""Tests unitaires et de non-régression pour la dérive de la documentation des raccourcis clavier (T8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ankiforge.ui.shortcuts.catalog import get_shortcut_catalog
from script.check_shortcuts_drift import (
    DOCS_SHORTCUTS_PATH,
    check_shortcuts_drift,
    generate_shortcuts_markdown,
    main,
    write_shortcuts_doc,
)

pytestmark = pytest.mark.unit


def test_generate_shortcuts_markdown_contains_all_actions() -> None:
    """La génération markdown doit inventorier 100% des raccourcis du catalogue."""
    catalog = get_shortcut_catalog()
    assert len(catalog) > 0, "Le catalogue ne doit pas être vide"

    md = generate_shortcuts_markdown(catalog)

    # Titre et en-tête d'auto-génération
    assert "# Référence des Raccourcis Clavier" in md
    assert "AUTO-GÉNÉRÉ" in md or "auto-généré" in md.lower()

    # Vérification de chaque entrée du catalogue
    for sc_id, defn in catalog.items():
        assert sc_id.value in md, f"L'identifiant {sc_id.value} doit figurer dans la documentation"
        assert defn.default_sequence in md, f"La séquence {defn.default_sequence} doit figurer dans la documentation"
        assert defn.category.value in md, f"La catégorie {defn.category.value} doit figurer dans la documentation"


def test_generate_shortcuts_markdown_contains_scopes_and_formatting() -> None:
    """La documentation doit afficher les portées hiérarchiques et des balises kbd."""
    catalog = get_shortcut_catalog()
    md = generate_shortcuts_markdown(catalog)

    assert "<kbd>" in md and "</kbd>" in md
    assert "Application" in md
    assert "Vue" in md
    assert "Widget" in md
    assert "Dialogue" in md


def test_check_shortcuts_drift_detects_missing_file(tmp_path: Path) -> None:
    """Un fichier inexistant doit être signalé comme une dérive."""
    missing_file = tmp_path / "missing_shortcuts.md"
    is_ok, diff_or_msg = check_shortcuts_drift(missing_file)
    assert not is_ok
    assert "introuvable" in diff_or_msg.lower() or "manquant" in diff_or_msg.lower()


def test_check_shortcuts_drift_detects_outdated_content(tmp_path: Path) -> None:
    """Un fichier au contenu obsolète ou incomplet doit être signalé avec un diff."""
    outdated_file = tmp_path / "outdated_shortcuts.md"
    outdated_file.write_text("# Raccourcis Obsolètes\nContenu incomplet", encoding="utf-8")

    is_ok, diff_or_msg = check_shortcuts_drift(outdated_file)
    assert not is_ok
    assert len(diff_or_msg) > 0


def test_write_and_check_shortcuts_idempotence(tmp_path: Path) -> None:
    """L'écriture via write_shortcuts_doc doit produire un fichier en succès immédiat de check."""
    target_file = tmp_path / "test_shortcuts.md"
    catalog = get_shortcut_catalog()

    write_shortcuts_doc(target_file, catalog)
    assert target_file.is_file()

    is_ok, diff_or_msg = check_shortcuts_drift(target_file, catalog)
    assert is_ok, f"Le check doit réussir après écriture : {diff_or_msg}"


def test_cli_check_and_fix_workflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie le cycle CLI --check (échoue sur dérive) puis --fix (corrige) puis --check (succès)."""
    target_file = tmp_path / "raccourcis.md"
    target_file.write_text("Dérive intentionnelle", encoding="utf-8")

    # Monkeypatch de DOCS_SHORTCUTS_PATH pour opérer dans tmp_path
    monkeypatch.setattr("script.check_shortcuts_drift.DOCS_SHORTCUTS_PATH", target_file)

    # 1. --check doit échouer
    code_check_1 = main(["--check"])
    assert code_check_1 != 0

    # 2. --fix doit réussir et régénérer le fichier
    code_fix = main(["--fix"])
    assert code_fix == 0
    assert target_file.is_file()
    assert "# Référence des Raccourcis Clavier" in target_file.read_text(encoding="utf-8")

    # 3. --check doit maintenant réussir
    code_check_2 = main(["--check"])
    assert code_check_2 == 0


def test_official_shortcuts_doc_is_in_sync() -> None:
    """La page officielle docs/guides/raccourcis_clavier.md doit être strictement synchronisée."""
    is_ok, diff_or_msg = check_shortcuts_drift(DOCS_SHORTCUTS_PATH)
    assert is_ok, f"La documentation officielle est désynchronisée du catalogue : {diff_or_msg}"
